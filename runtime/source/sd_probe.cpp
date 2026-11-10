// SD 卡读写探针（2026-11-09）。
//
// 来历与判据写在 `sd_probe.hpp` 顶部。这里只强调三条落地约束：
//
// 1. **只在 `EXL_SD_PROBE` 打开时编译**；默认运行时里一行都不存在（`#if` 包住整份文件）。
// 2. **只在游戏线程上跑**：nnSdk 的文件 API 要求线程在游戏自己的线程体系里
//    （历史上我们自己的 `svcCreateThread` 线程调 `nn::fs` 必崩，见 docs 续「442190」）。
//    调用点因此是 `ManagerUpdateHook::Callback`（每帧、游戏线程）。
// 3. **不靠日志**：结果写进一个**导出**的结构体（`g_IsaacSdProbeState`），
//    设备侧用 NxConduit 按"模块基址 + 符号偏移"直接读内存，没有文件通道也能拿到读数。
//
// 判据顺序与星露谷 SSCL 的实现对齐（`SSCL/source/public/nativ/game_bindings/config_store.cpp`
// 与 `nativ/game_entry/module_lookup.cpp`）：
//   扫模块 → 在 nnSdk 的**动态符号表**里按名字找 `nn::fs::MountSdCard` 等 →
//   挂载 → 建目录 → 建/写文件 → 重新打开读回 → 比对。

#if defined(EXL_SD_PROBE)

#include "sd_probe.hpp"

#include "lib/nx/nx.h"
#include "rtld.hpp"

#include <cstdint>
#include <cstring>

namespace {

// 探针状态魔数（设备侧读回时先认这个字，认不到就是读错了地址）。
constexpr std::uint64_t kStateMagic = 0x3154425053445341ULL;  // "ASDSPBT1"

// 请求基址的时间窗：最早 ~4 秒后开始看（等引擎把 nnSdk 用过一轮），最晚 ~5 分钟
// （超时就把 finished 置 1，这一局不再做任何事）。
constexpr std::uint32_t kWaitMinFrames = 240;
constexpr std::uint32_t kWaitMaxFrames = 18000;
constexpr char kMountName[] = "isaacsd";
constexpr char kDirectoryPath[] = "isaacsd:/switch/isaac-runtime";
constexpr char kFilePath[] = "isaacsd:/switch/isaac-runtime/sd-probe.txt";
constexpr char kFileText[] = "ISAAC-SWITCH-SD-PROBE-OK\n";

// nnSdk 的返回码（只用来区分"为什么没成"，不改变成败语义）。
constexpr std::uint32_t kResultSuccess = 0;
constexpr std::uint32_t kResultAlreadyExists = 0x402;

enum HashKind : std::uint32_t {
    HashKind_None = 0,
    HashKind_SysV = 1,
    HashKind_Gnu = 2,
};

// 每一步的读数都落在这张表里；设备侧按字段偏移读。
struct SdProbeState {
    std::uint64_t magic;
    std::uint32_t version;
    std::uint32_t frames;       // 进门次数（证明回调真的在跑）
    std::uint32_t stage;        // 最后完成的阶段
    std::uint32_t moduleCount;  // 模块表里走了几条
    std::uint32_t sdkIndex;     // 认定是 nnSdk 的那个模块序号（1 起）
    std::uint32_t sdkPathLength;  // 保留字段（本轮不再填，恒 0）
    char sdkPath[32];             // 保留字段（本轮不再填，恒 0）
    std::uint32_t hashKind;       // 0 无哈希表 / 1 SysV / 2 GNU
    std::uint32_t symbolCount;    // 动态符号条数（SyS 哈希的 nchain）
    std::uint64_t sdkBase;
    std::uint64_t sdkSize;        // 该模块 dynstr 的长度（只作身份旁证）
    std::uint64_t dynsym;
    std::uint64_t dynstr;
    std::uint64_t mountFunction;
    std::uint64_t createDirectoryFunction;
    std::uint64_t createFileFunction;
    std::uint64_t openFileFunction;
    std::uint64_t writeFileFunction;
    std::uint64_t readFileFunction;
    std::uint64_t getFileSizeFunction;
    std::uint64_t closeFileFunction;
    std::uint32_t mountResult;
    std::uint32_t directoryResult;
    std::uint32_t createFileResult;
    std::uint32_t openForWriteResult;
    std::uint32_t writeResult;
    std::uint32_t openForReadResult;
    std::uint32_t sizeResult;
    std::uint64_t fileSize;
    std::uint32_t readResult;
    std::uint64_t bytesRead;
    std::uint32_t verifyResult;  // 0 = 内容比对通过，其他 = 不通过
    std::uint32_t finished;
    // ↓ 本轮新增：外部（PC 侧 NxConduit）写进来的 nnSdk 模块基址。
    //   探针自己没有可靠的模块发现路径（扫内存只认出 2 个；走游戏的模块表走了 65 条也没认对），
    //   而 PC 侧用 gdb 的 `monitor get info` 能拿到权威基址 ⇒ 让 PC 把它写进来，探针只做解析与调用。
    std::uint64_t requestBase;
    std::uint64_t sdkTextSize;  // 该基址那一段可执行映射的长度（内核给的，不是猜的）
    // ↓ 解析失败时的分步读数（只为定位"卡在哪一步"，正常路径不填）
    std::uint32_t queryResult;
    std::uint32_t diagStage;
    std::uint64_t diagTextAddr;
    std::uint64_t diagTextSize;
    std::uint64_t diagSpanEnd;
    std::uint64_t diagMod0;
    std::uint64_t diagDynamic;
    std::uint64_t diagNextAddr;
    std::uint32_t diagNextType;
    std::uint32_t diagNextRc;
};

extern "C" {
__attribute__((visibility("default"))) SdProbeState g_IsaacSdProbeState = {
    kStateMagic, 1, 0, 0, 0, 0, 0, 0, {}, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0};
}

enum Stage : std::uint32_t {
    Stage_Idle = 0,
    Stage_Scanned = 1,
    Stage_SdkNotFound = 2,
    Stage_DynamicsUnreadable = 3,
    Stage_DynamicsReady = 12,
    Stage_SymbolsFound = 4,
    Stage_MountSdCardMissing = 5,
    Stage_FileApiMissing = 6,
    Stage_Mounted = 7,
    Stage_DirectoryReady = 8,
    Stage_Written = 9,
    Stage_ReadBack = 10,
    Stage_Done = 11,
};

struct FileHandle {
    std::uint64_t value;
};

struct WriteOption {
    std::uint32_t flags;
};

using MountSdCardFn = std::uint32_t (*)(const char*);
using CreateDirectoryFn = std::uint32_t (*)(const char*);
using CreateFileFn = std::uint32_t (*)(const char*, std::int64_t, std::int32_t);
using OpenFileFn = std::uint32_t (*)(FileHandle*, const char*, std::int32_t);
using WriteFileFn = std::uint32_t (*)(FileHandle, std::int64_t, const void*, std::uint64_t,
                                      const WriteOption*);
using ReadFileFn = std::uint32_t (*)(std::uint64_t*, FileHandle, std::int64_t, void*,
                                     std::uint64_t);
using GetFileSizeFn = std::uint32_t (*)(std::int64_t*, FileHandle);
using CloseFileFn = void (*)(FileHandle);

constexpr std::uint32_t kMod0Magic = 0x30444F4D;  // MOD0

struct DynInfo {
    uintptr_t base{};
    uintptr_t end{};
    uintptr_t strings{};
    std::size_t stringsSize{};
    uintptr_t symbols{};
    std::size_t symbolCount{};
    std::uint32_t hashKind{HashKind_None};
};

bool Inside(const DynInfo& d, uintptr_t address, std::size_t length) {
    if (d.base == 0 || d.end <= d.base || address < d.base) return false;
    const uintptr_t offset = address - d.base;
    const uintptr_t span = d.end - d.base;
    return offset <= span && length <= span - offset;
}

// 从基址那段可执行映射开始，沿相邻的模块映射往后走，得到整块模块的末端。
uintptr_t ModuleSpanEnd(uintptr_t base) {
    MemoryInfo text{};
    std::uint32_t pageInfo = 0;
    const auto rc = svcQueryMemory(&text, &pageInfo, base);
    g_IsaacSdProbeState.queryResult = static_cast<std::uint32_t>(rc);
    g_IsaacSdProbeState.diagTextAddr = text.addr;
    g_IsaacSdProbeState.diagTextSize = text.size;
    if (R_FAILED(rc) || text.size == 0) return 0;
    uintptr_t end = text.addr + text.size;
    for (std::uint32_t step = 0; step < 8; ++step) {
        MemoryInfo next{};
        uintptr_t probe = end;
        auto nextRc = svcQueryMemory(&next, &pageInfo, probe);
        if (R_SUCCEEDED(nextRc) && next.size != 0 && next.addr + next.size <= probe) {
            // 内核在边界上可能仍返回"前一段"（区间是 [start,end)），退回一步再问一次。
            probe = next.addr + next.size;
            nextRc = svcQueryMemory(&next, &pageInfo, probe);
        }
        if (step == 0) {
            g_IsaacSdProbeState.diagNextRc = static_cast<std::uint32_t>(nextRc);
            g_IsaacSdProbeState.diagNextAddr = next.addr;
            g_IsaacSdProbeState.diagNextType = next.type;
        }
        if (R_FAILED(nextRc) || next.size == 0 || next.addr != probe) break;
        // ★ 真机实测：内核给 nnSdk 的段标的是 `CodeStatic(3)` / `CodeMutable(4)`，
        //   不是 `ModuleCodeStatic(8)` / `ModuleCodeMutable(9)`（那两种是 NRO/动态模块
        //   经 `svcMapProcessCodeMemory` 映射时才用的）。第一版只认 8/9 ⇒ 走到 text 末尾就停，
        //   跨度只有 0x5D5000，动态段（0xCD4278）直接被判出界（stage=3、diagNextType=3）。
        const auto type = next.type & MemState_Type;
        const bool moduleMapping = type == MemType_CodeStatic || type == MemType_CodeMutable ||
                                   type == MemType_ModuleCodeStatic ||
                                   type == MemType_ModuleCodeMutable;
        if (!moduleMapping) break;
        end = next.addr + next.size;
    }
    return end;
}

u64 ResolveValue(const DynInfo& d, std::uint64_t value) {
    if (value >= d.base && value < d.end) return value;
    if (value < d.end - d.base) return d.base + value;
    return 0;
}

bool ReadGnuSymbolCount(const DynInfo& d, uintptr_t gnuHash, std::size_t* count) {
    if (!Inside(d, gnuHash, 16)) return false;
    const auto* header = reinterpret_cast<const std::uint32_t*>(gnuHash);
    const std::uint32_t buckets = header[0];
    const std::uint32_t symbolOffset = header[1];
    const std::uint32_t bloomSize = header[2];
    if (buckets == 0 || buckets > 0x100000 || bloomSize == 0 || bloomSize > 0x100000 ||
        (bloomSize & (bloomSize - 1)) != 0) {
        return false;
    }
    const uintptr_t bucketTable = gnuHash + 16 + static_cast<std::size_t>(bloomSize) * 8;
    const uintptr_t chainTable = bucketTable + static_cast<std::size_t>(buckets) * 4;
    if (!Inside(d, bucketTable, static_cast<std::size_t>(buckets) * 4)) return false;
    std::uint32_t last = 0;
    for (std::uint32_t index = 0; index < buckets; ++index) {
        const std::uint32_t bucket = *reinterpret_cast<const std::uint32_t*>(bucketTable + index * 4);
        if (bucket == 0) continue;
        if (bucket < symbolOffset || bucket > 0x100000) return false;
        if (bucket > last) last = bucket;
    }
    if (last == 0) {
        *count = symbolOffset;
        return true;
    }
    for (std::uint32_t index = last; index < 0x100000; ++index) {
        const uintptr_t entry = chainTable + static_cast<std::size_t>(index - symbolOffset) * 4;
        if (!Inside(d, entry, 4)) return false;
        const std::uint32_t chain = *reinterpret_cast<const std::uint32_t*>(entry);
        if ((chain & 1u) != 0) {
            *count = static_cast<std::size_t>(index) + 1;
            return true;
        }
    }
    return false;
}

// 基址 → MOD0 → 动态段 → dynsym/dynstr。所有读取都先过"落在内核给的那段映射里"。
bool ReadDynamics(uintptr_t base, DynInfo* out) {
    DynInfo d{};
    d.base = base;
    d.end = ModuleSpanEnd(base);
    g_IsaacSdProbeState.diagSpanEnd = d.end;
    if (d.end <= d.base || d.end - d.base > 0x10000000) return false;
    if (!Inside(d, base + 8, 8)) return false;
    g_IsaacSdProbeState.diagMod0 = *reinterpret_cast<const std::uint32_t*>(base + 8);
    if (*reinterpret_cast<const std::uint32_t*>(base + 8) != kMod0Magic) return false;
    const auto dynamicOffset = *reinterpret_cast<const std::int32_t*>(base + 12);
    const std::uint64_t sum = 8 + static_cast<std::uint64_t>(static_cast<std::int64_t>(dynamicOffset));
    if (sum > d.end - d.base) return false;
    const uintptr_t dynamic = d.base + static_cast<uintptr_t>(sum);
    g_IsaacSdProbeState.diagDynamic = dynamic;

    std::uint64_t rawStrings = 0, rawSymbols = 0, rawHash = 0, rawGnuHash = 0;
    std::size_t stringsSize = 0, entrySize = 0;
    bool terminated = false;
    for (std::uint32_t index = 0; index < 256; ++index) {
        if (!Inside(d, dynamic + index * 16, 16)) return false;
        const auto tag = *reinterpret_cast<const std::int64_t*>(dynamic + index * 16);
        const auto value = *reinterpret_cast<const std::uint64_t*>(dynamic + index * 16 + 8);
        if (tag == 0) {
            terminated = true;
            break;
        }
        if (tag == 4) rawHash = value;
        else if (tag == 5) rawStrings = value;
        else if (tag == 6) rawSymbols = value;
        else if (tag == 10) stringsSize = static_cast<std::size_t>(value);
        else if (tag == 11) entrySize = static_cast<std::size_t>(value);
        else if (tag == 0x6ffffef5) rawGnuHash = value;
    }
    if (!terminated || entrySize != 24 || stringsSize == 0) {
        g_IsaacSdProbeState.diagStage = 1;
        return false;
    }

    const uintptr_t strings = ResolveValue(d, rawStrings);
    const uintptr_t symbols = ResolveValue(d, rawSymbols);
    if (strings == 0 || symbols == 0 || !Inside(d, strings, stringsSize) ||
        !Inside(d, symbols, 24)) {
        g_IsaacSdProbeState.diagStage = 2;
        return false;
    }

    std::size_t count = 0;
    std::uint32_t kind = HashKind_None;
    const uintptr_t hash = ResolveValue(d, rawHash);
    if (hash != 0 && Inside(d, hash, 8)) {
        const auto chains = *reinterpret_cast<const std::uint32_t*>(hash + 4);
        if (chains != 0 && chains <= 0x100000 && Inside(d, symbols, chains * 24)) {
            count = chains;
            kind = HashKind_SysV;
        }
    }
    if (count == 0) {
        const uintptr_t gnu = ResolveValue(d, rawGnuHash);
        if (gnu == 0 || !ReadGnuSymbolCount(d, gnu, &count) || count == 0 || count > 0x100000 ||
            !Inside(d, symbols, count * 24)) {
            g_IsaacSdProbeState.diagStage = 3;
            return false;
        }
        kind = HashKind_Gnu;
    }

    d.strings = strings;
    d.stringsSize = stringsSize;
    d.symbols = symbols;
    d.symbolCount = count;
    d.hashKind = kind;
    *out = d;
    return true;
}

uintptr_t FindFunction(const DynInfo& d, const char* name) {
    const auto length = std::strlen(name);
    if (d.stringsSize <= length) return 0;
    const char* strings = reinterpret_cast<const char*>(d.strings);
    std::size_t nameOffset = 0;
    bool found = false;
    for (std::size_t offset = 0; offset + length < d.stringsSize; ++offset) {
        if (strings[offset] != name[0]) continue;
        if (std::memcmp(strings + offset, name, length + 1) != 0) continue;
        nameOffset = offset;
        found = true;
        break;
    }
    if (!found) return 0;
    for (std::size_t index = 1; index < d.symbolCount; ++index) {
        const uintptr_t record = d.symbols + index * 24;
        const auto symbolName = *reinterpret_cast<const std::uint32_t*>(record);
        if (symbolName != nameOffset) continue;
        const auto info = *reinterpret_cast<const std::uint8_t*>(record + 4);
        const auto section = *reinterpret_cast<const std::uint16_t*>(record + 6);
        const auto value = *reinterpret_cast<const std::uint64_t*>(record + 8);
        const auto bind = static_cast<std::uint8_t>(info >> 4);
        if (section == 0 || (info & 0xf) != 2 || (bind != 1 && bind != 2) || value == 0) continue;
        return d.base + static_cast<uintptr_t>(value);
    }
    return 0;
}

} // namespace

namespace isaac::runtime::sdprobe {

void Tick() noexcept {
    auto& state = g_IsaacSdProbeState;
    if (state.finished != 0) return;
    const std::uint32_t frames = state.frames + 1;
    state.frames = frames;
    if (frames < kWaitMinFrames) return;

    // 模块基址由 PC 侧写进来（见 `requestBase` 字段的注释）。没写就继续等，最多等到 kWaitMaxFrames：
    // 过了上限就把 finished 置 1（这一局不再做任何 I/O，也不拖帧）。
    if (state.requestBase == 0) {
        if (frames >= kWaitMaxFrames) state.finished = 1;
        return;
    }
    state.finished = 1;  // 只跑一次

    // ---- 1. 从给定基址解析 nnSdk 的动态符号 ----
    DynInfo dyn{};
    state.sdkBase = state.requestBase;
    if (!ReadDynamics(static_cast<uintptr_t>(state.requestBase), &dyn)) {
        state.stage = Stage_DynamicsUnreadable;
        return;
    }
    state.sdkTextSize = static_cast<std::uint64_t>(dyn.end - dyn.base);
    state.dynsym = dyn.symbols;
    state.dynstr = dyn.strings;
    state.hashKind = dyn.hashKind;
    state.symbolCount = static_cast<std::uint32_t>(dyn.symbolCount);
    state.stage = Stage_DynamicsReady;

    // ---- 2. 按名字找函数 ----
    const auto mountSdCard = FindFunction(dyn, "_ZN2nn2fs11MountSdCardEPKc");
    const auto createDirectory = FindFunction(dyn, "_ZN2nn2fs15CreateDirectoryEPKc");
    const auto createFile = FindFunction(dyn, "_ZN2nn2fs10CreateFileEPKcli");
    const auto openFile = FindFunction(dyn, "_ZN2nn2fs8OpenFileEPNS0_10FileHandleEPKci");
    const auto writeFile =
        FindFunction(dyn, "_ZN2nn2fs9WriteFileENS0_10FileHandleElPKvmRKNS0_11WriteOptionE");
    const auto readFile = FindFunction(dyn, "_ZN2nn2fs8ReadFileEPmNS0_10FileHandleElPvm");
    const auto getFileSize = FindFunction(dyn, "_ZN2nn2fs11GetFileSizeEPlNS0_10FileHandleE");
    const auto closeFile = FindFunction(dyn, "_ZN2nn2fs9CloseFileENS0_10FileHandleE");
    state.mountFunction = mountSdCard;
    state.createDirectoryFunction = createDirectory;
    state.createFileFunction = createFile;
    state.openFileFunction = openFile;
    state.writeFileFunction = writeFile;
    state.readFileFunction = readFile;
    state.getFileSizeFunction = getFileSize;
    state.closeFileFunction = closeFile;
    state.stage = Stage_SymbolsFound;
    if (mountSdCard == 0) {
        state.stage = Stage_MountSdCardMissing;
        return;
    }
    if (createDirectory == 0 || createFile == 0 || openFile == 0 || writeFile == 0 ||
        readFile == 0 || getFileSize == 0 || closeFile == 0) {
        state.stage = Stage_FileApiMissing;
        return;
    }

    // ---- 3. 挂载 SD 卡 ----
    state.mountResult = reinterpret_cast<MountSdCardFn>(mountSdCard)(kMountName);
    if (state.mountResult != kResultSuccess && state.mountResult != kResultAlreadyExists) return;
    state.stage = Stage_Mounted;

    // ---- 4. 建目录（父目录不存在时 SDK 不会替我们建）----
    state.directoryResult = reinterpret_cast<CreateDirectoryFn>(createDirectory)(kDirectoryPath);
    if (state.directoryResult != kResultSuccess && state.directoryResult != kResultAlreadyExists) {
        return;
    }
    state.stage = Stage_DirectoryReady;

    // ---- 5. 建文件 + 写 ----
    const auto openFileCall = reinterpret_cast<OpenFileFn>(openFile);
    const auto closeFileCall = reinterpret_cast<CloseFileFn>(closeFile);
    constexpr std::uint64_t kTextSize = sizeof(kFileText) - 1;
    state.createFileResult =
        reinterpret_cast<CreateFileFn>(createFile)(kFilePath, static_cast<std::int64_t>(kTextSize), 0);
    FileHandle handle{0};
    state.openForWriteResult = openFileCall(&handle, kFilePath, 2);
    if (state.openForWriteResult != kResultSuccess) return;
    WriteOption option{1};  // 1 = 写完即刷（Flush）
    state.writeResult = reinterpret_cast<WriteFileFn>(writeFile)(handle, 0, kFileText, kTextSize,
                                                               &option);
    closeFileCall(handle);
    if (state.writeResult != kResultSuccess) return;
    state.stage = Stage_Written;

    // ---- 6. 重新打开读回并比对 ----
    FileHandle readHandle{0};
    state.openForReadResult = openFileCall(&readHandle, kFilePath, 1);
    if (state.openForReadResult != kResultSuccess) return;
    std::int64_t size = 0;
    state.sizeResult = reinterpret_cast<GetFileSizeFn>(getFileSize)(&size, readHandle);
    if (state.sizeResult == kResultSuccess && size > 0) {
        state.fileSize = static_cast<std::uint64_t>(size);
        char buffer[64]{};
        const std::uint64_t capacity =
            size < static_cast<std::int64_t>(sizeof(buffer)) ? static_cast<std::uint64_t>(size)
                                                            : sizeof(buffer);
        std::uint64_t read = 0;
        state.readResult =
            reinterpret_cast<ReadFileFn>(readFile)(&read, readHandle, 0, buffer, capacity);
        state.bytesRead = read;
        state.verifyResult =
            (state.readResult == kResultSuccess && read == kTextSize &&
             std::memcmp(buffer, kFileText, kTextSize) == 0)
                ? 0u
                : 1u;
    }
    closeFileCall(readHandle);
    state.stage = Stage_ReadBack;
    if (state.sizeResult != kResultSuccess) return;
    state.stage = Stage_Done;
}

} // namespace isaac::runtime::sdprobe

#endif
