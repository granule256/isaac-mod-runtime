#include "anm2_load_override_hook.hpp"

#include "infrastructure/call/engine_call_access.hpp"      // 引擎调用层：ResolveFunction
#include "infrastructure/memory/engine_memory_guard.hpp"  // ReadAt / EngineMemoryReadable：绝不盲读
#include "interfaces/lua/runtime_perf.hpp"  // 批次 384：`RuntimePerfTick()`（记"中继首次被调"的时刻）
#include "module_finder.hpp"       // TargetModule（安装时按模块基址核对入口）
#include "runtime_constants.hpp"    // 本批的偏移与守卫（复用 kSpriteLoad*，见该文件说明）

#include <cstddef>
#include <cstdint>
#include <cstring>

// ============================================================================
// 批次 363：`ANM2::Load` 入口中继的实现（设计说明见头文件）
// ============================================================================
//
// 这个回调跑在引擎的**加载路径**上（每次 `Sprite:Load` 都会经过），所以第一原则是
// **默认什么都不做**：只有"这条路径现在归模组层、且缓存里确实还有本体旧条目"时才动手。
// 其余情况最多一次前缀比较 + 一次解析器查询就返回。

namespace isaac::runtime::bridge {

// ★ 这一个**刻意放在匿名命名空间之外**（外部链接）：读数工具按符号名
// `g_Anm2LoadOverrideState` 读它，字段顺序必须与头文件的 `Anm2LoadOverrideState` 一致。
// 契约两边同步改（`tools/read_device_state_via_gdb.py` 的 `SYM_ELF_NAMES`）。
Anm2LoadOverrideState g_Anm2LoadOverrideState{};

namespace {

namespace engine_call = isaac::runtime::engine_call;
namespace engine_memory = isaac::runtime::engine_memory;

// ---------------------------------------------------------------------------
// 诊断面（只加不减；读数工具按符号名读）
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// 引擎侧绑定（安装时核对一次，之后只读用）
// ---------------------------------------------------------------------------
struct Bindings {
    // ★ 前三个字段必须与 `Anm2LoadBindingsView` **逐字段同布局**（回调按视图读它们）。
    using GetMountedFn = char* (*)(void*, const char*);
    GetMountedFn getMounted{nullptr};        // `IContentManager::GetMountedFilePath`
    void* contentManager{nullptr};           // `g_ContentManager` 对象
    using FreePathFn = void (*)(void*);      // 引擎自己的 `operator delete[]`
    FreePathFn freePath{nullptr};
    // 下面这些只在本 TU 内部用。
    void* anmCache{nullptr};                 // `g_AnmCache` 对象（map 本体）
    std::uintptr_t mountPointsVector{0};     // `g_ContentMountPoints`（vector 对象地址）
    // ★ 批次 369 起**不再使用**（它会把活引用减掉 ⇒ 释放后使用 ⇒ 真机崩溃，见回调里的说明）。
    //   绑定仍然解析出来（安装期一次性），只是没有任何调用点 —— 留着是为了让"为什么不用它"
    //   这件事连同偏移与守卫一起留在代码里，而不是把证据删掉。
    using RemoveRefFn = void (*)(void*, const void*);   // `AnmCache::RemoveReference(string const&)`
    RemoveRefFn removeReference{nullptr};
    using FreeEntriesFn = void (*)(void*);              // `AnmCache::FreeUnreferencedEntries()`
    FreeEntriesFn freeUnreferencedEntries{nullptr};
    std::uintptr_t fallbackEntry{0};         // 回退入口（跑原函数）
};
Bindings g_Bindings{};

// ---------------------------------------------------------------------------
// libc++ 的 24 字节 `std::string` 读取（布局有实测依据，见 runtime_constants.hpp）
// ---------------------------------------------------------------------------
//: 短串：内联数据从对象 +1 开始（首字节 = `size << 1`，最低位是 long 标志）。
//: 长串：数据指针在对象 +16，且**是引擎分配器给的**（我们只读，不释放）。
bool ReadNativeString(const void* object, char* out, std::size_t capacity,
                      std::size_t* outLength) {
    if (object == nullptr || out == nullptr || capacity == 0) {
        return false;
    }
    const std::uintptr_t address = engine_memory::AddressOf(object);
    std::uint8_t header = 0;
    if (!engine_memory::ReadAt(address, &header, &engine_memory::EngineMemoryReadable)) {
        return false;
    }
    const char* data = nullptr;
    std::size_t length = 0;
    if ((header & kLibcxxStringLongFlag) != 0) {
        std::uintptr_t buffer = 0;
        if (!engine_memory::ReadAt(address + kLibcxxStringDataOffset, &buffer,
                                   &engine_memory::EngineMemoryReadable) ||
            buffer == 0) {
            return false;
        }
        data = static_cast<const char*>(engine_memory::AsObject(buffer));
        // 长串的长度在对象 +8（libc++ 的 `__long::__size_`）。
        std::uint64_t size = 0;
        if (!engine_memory::ReadAt(address + 8, &size, &engine_memory::EngineMemoryReadable)) {
            return false;
        }
        length = static_cast<std::size_t>(size);
    } else {
        data = static_cast<const char*>(
            engine_memory::AsObject(address + kLibcxxStringShortDataOffset));
        length = static_cast<std::size_t>(header >> 1);
    }
    if (length + 1 > capacity) {
        return false;  // 超容量：**不截断**（截断出来的路径会指向别的资源，比不做更糟）
    }
    if (length == 0) {
        out[0] = '\0';
        if (outLength != nullptr) {
            *outLength = 0;
        }
        return true;
    }
    // 访问层只提供"定长类型"读（裸数组读被刻意 `= delete`，见 `engine_field_access.hpp`），
    // 所以这里逐字节读。路径最长 255，代价可忽略；读不到就如实失败。
    const std::uintptr_t base = engine_memory::AddressOf(data);
    for (std::size_t i = 0; i < length; ++i) {
        char byte = 0;
        if (!engine_memory::ReadAt(base + i, &byte, &engine_memory::EngineMemoryReadable)) {
            return false;
        }
        out[i] = byte;
    }
    out[length] = '\0';
    if (outLength != nullptr) {
        *outLength = length;
    }
    return true;
}

//: 引擎自己的哈希（`KAGE::Filesys::FileManager::HashDJB2`，djb2 变体：`h = h*33 + c`）。
//: 我们用**同一个算法**算候选键，因为缓存键就是它算出来的。
std::uint32_t HashDjb2(const char* text) {
    std::uint32_t hash = 5381;
    for (const char* p = text; *p != '\0'; ++p) {
        hash = hash * 33u + static_cast<std::uint8_t>(*p);
    }
    return hash;
}

// ---------------------------------------------------------------------------
// 挂载点表读取（`g_ContentMountPoints` = `std::vector<const char*>`，**每项 8 字节指针**）
// ---------------------------------------------------------------------------
// ★★★ 2026-10-05（批次 366）：**这一段的元素类型整整读错了一轮**。反汇编三处互证
//   （`Repentance.nro`；命令与原文见
//   `docs/分析-ANM2覆盖链静默失效根因-挂载点表元素类型与两处ABI-20261005.md`）：
//     `AnmCache::Load2`           0xF638 `add x19, x19, #0x8` + 0xF644 `ldr x2, [x19]`
//     `AnmCache::AddReference`    0x14BA0 同形
//     `AnmCache::RemoveReference` 0x14D68 同形
//   取出来的元素**直接**喂给 `strncpy_s(buf, 256, 元素, 256)` ⇒ 元素就是一条 C 串的首地址。
//   读错的后果是**静默**的：每个前缀都读不出来 ⇒ 候选键一个都算不出 ⇒ 回调在"绝不猜"的
//   早退里返回（真机读数里 `问解析器` 恒 0、`找到本体旧条目` 恒 0）。
//   门禁：`runtime/tests/test_anm2_load_override_hook.py` 直接从 NRO 反汇编钉住这个形状。
constexpr std::size_t kMountPointEntrySize = 8;
constexpr std::size_t kMaxMountPoints = 64;
//: 单个挂载点前缀的长度上限（引擎自己用 256 字节缓冲拼键；我们只读，够用即可）。
constexpr std::size_t kMaxMountPointText = 190;

struct MountPointList {
    std::uintptr_t begin{0};
    std::uintptr_t end{0};
};

//: 读一条**由引擎持有的** C 串（挂载点前缀就是这种）。逐字节读：读不到就如实失败。
bool ReadEngineCString(std::uintptr_t address, char* out, std::size_t capacity,
                       std::size_t* outLength) {
    if (address == 0 || out == nullptr || capacity < 2) {
        return false;
    }
    for (std::size_t i = 0; i + 1 < capacity; ++i) {
        char byte = 0;
        if (!engine_memory::ReadAt(address + i, &byte, &engine_memory::EngineMemoryReadable)) {
            return false;
        }
        out[i] = byte;
        if (byte == '\0') {
            if (outLength != nullptr) {
                *outLength = i;
            }
            return true;
        }
    }
    return false;  // 没有 NUL 结尾（超长）⇒ **不截断**，如实失败（截断出来的路径会指向别的资源）
}

//: 从**给定的** `std::vector<const char*>` 对象地址读 `[begin, end)`（批次 370 起抽出来：
//: 中继用 `g_Bindings.mountPointsVector`，而"提前挂载那一步只读一次表"用的是当场读到的 GOT 槽，
//: 两者**必须走同一份读法** —— 元素 8 字节那条口径只许有一份，见上面那一大段注释）。
bool ReadMountPointsAt(std::uintptr_t vector, MountPointList* out) {
    if (out == nullptr || vector == 0) {
        return false;
    }
    std::uintptr_t begin = 0;
    std::uintptr_t end = 0;
    if (!engine_memory::ReadAt(vector, &begin, &engine_memory::EngineMemoryReadable) ||
        !engine_memory::ReadAt(vector + sizeof(std::uintptr_t), &end,
                               &engine_memory::EngineMemoryReadable)) {
        return false;
    }
    if (begin == 0 || end < begin) {
        return false;
    }
    const std::size_t count = (end - begin) / kMountPointEntrySize;
    if (count == 0 || count > kMaxMountPoints) {
        return false;
    }
    out->begin = begin;
    out->end = end;
    return true;
}

bool ReadMountPoints(MountPointList* out) {
    return ReadMountPointsAt(g_Bindings.mountPointsVector, out);
}

//: 从挂载点表的一项里取出前缀文本（一项 = 一个 `const char*`）。
bool ReadMountPointAt(std::uintptr_t entry, char* out, std::size_t capacity,
                      std::size_t* outLength) {
    std::uintptr_t text = 0;
    if (!engine_memory::ReadAt(entry, &text, &engine_memory::EngineMemoryReadable) || text == 0) {
        return false;
    }
    return ReadEngineCString(text, out, capacity, outLength);
}

// ---------------------------------------------------------------------------
// 缓存只读遍历：找"本条路径在别的挂载点前缀下的键"，并读它的引用计数
// ---------------------------------------------------------------------------
//: `std::__1::map<uint32_t, Entry2>`（`g_AnmCache` 对象 `+0x00` 起）的布局 —— 三处反汇编互证
//: （`docs/分析-ANM2覆盖链静默失效根因-挂载点表元素类型与两处ABI-20261005.md`）：
//:   * map 对象：`+0x00` = `__begin_node_`（最左节点）；**`+0x08` 就是"结束哨兵"本身**，
//:     它的 `__left_`（也就是我们直接读 `[map+0x08]` 得到的那个值）**就是根节点指针**；
//:     树为空时它指向自己（`[map+8] == map+8`）。
//:   * 节点：`+0x00` 左、`+0x08` 右、`+0x10` 父、`+0x20` 键（u32 哈希）、`+0x88` 引用计数（u32）。
//: 出处：`AnmCache::Load2` `0xF6D0`/`0xF6E0`/`0xF6F0`（查找循环）、
//:       `AnmCache::AddReference` `0x14C34`–`0x14C7C`（同一形状 + 命中时 `[x8+0x88]++`）、
//:       `AnmCache::FreeUnreferencedEntries` `0x14FAC`–`0x15048`（`[x21+0x88]` 判 0、中序走 `+8`/`+0x10`）。
//
// ★★★ 2026-10-05（批次 367）：**这里原来多解引用了一层** —— 把 `[map+0x08]`（已经是**根节点**）
//   当成"哨兵对象"，又去读 `[哨兵+0x00]` 当根 ⇒ 查找从**根的左孩子**开始、永远不比较根自己，
//   大多数键因此查不到 ⇒ 真机表现为"中继被调 178 次、问解析器 0 次"（修好挂载点表元素类型之后
//   仍然如此，读数 `dist/gdb-read-20261005-115405.txt`）。
bool FindEntryRefCount(std::uint32_t key, std::uint32_t* outCount) {
    if (outCount == nullptr || g_Bindings.anmCache == nullptr) {
        return false;
    }
    const std::uintptr_t map = engine_memory::AddressOf(g_Bindings.anmCache);
    // "结束哨兵"是**地址** `map+8`（引擎自己 `cmp x26, x27` 比的就是这个地址），
    // 而 `[map+8]` 是它的 `__left_` = **根节点**。
    const std::uintptr_t endNode = map + kAnmCacheMapRootSentinelOffset;
    std::uintptr_t node = 0;
    if (!engine_memory::ReadAt(endNode, &node, &engine_memory::EngineMemoryReadable) ||
        node == 0) {
        return false;  // 空树
    }
    // 标准 `std::map` 查找（引擎的形状：`nodeKey < key` ⇒ 走右，否则走左；深度上限防环）。
    for (std::size_t depth = 0; depth < 64; ++depth) {
        if (node == 0 || node == endNode) {
            return false;  // 没这一条
        }
        std::uint32_t nodeKey = 0;
        if (!engine_memory::ReadAt(node + kAnmCacheNodeKeyOffset, &nodeKey,
                                   &engine_memory::EngineMemoryReadable)) {
            return false;
        }
        if (nodeKey == key) {
            std::uint32_t count = 0;
            if (!engine_memory::ReadAt(node + kAnmCacheNodeRefCountOffset, &count,
                                       &engine_memory::EngineMemoryReadable)) {
                return false;
            }
            *outCount = count;
            return true;
        }
        const std::size_t childOffset =
            key < nodeKey ? kAnmCacheNodeLeftOffset : kAnmCacheNodeRightOffset;
        if (!engine_memory::ReadAt(node + childOffset, &node,
                                   &engine_memory::EngineMemoryReadable)) {
            return false;
        }
    }
    return false;
}

// ---------------------------------------------------------------------------
// "同一路径本会话已作废过"的记忆（防空转）
// ---------------------------------------------------------------------------
// 作废之后引擎会重新开文件，并把模组那份按"**最后一次迭代的键**"重新缓存起来 ——
// 那一格的内容**已经是模组那份**了；再作废一次只会白开一次文件（批次 363 的设计里明确要躲开
// 这种"空转"）。所以每条路径**每会话最多作废一次**：宁可漏一次，也不每次空转。
// 表很小（8 条）：会走到作废这一步的只有"解析器答模组层、且缓存里真的有压着它的条目"的路径，
// 在真机上是个位数到几十条的规模。
constexpr std::size_t kEvictedPathMemory = 8;
std::uint32_t g_EvictedPathHashes[kEvictedPathMemory] = {};
std::size_t g_EvictedPathCount = 0;

bool AlreadyEvictedThisSession(std::uint32_t key) noexcept {
    if (key == 0) {
        return false;
    }
    const std::size_t count =
        g_EvictedPathCount < kEvictedPathMemory ? g_EvictedPathCount : kEvictedPathMemory;
    for (std::size_t i = 0; i < count; ++i) {
        if (g_EvictedPathHashes[i] == key) {
            return true;
        }
    }
    return false;
}

void RememberEvicted(std::uint32_t key) noexcept {
    if (key == 0 || AlreadyEvictedThisSession(key)) {
        return;
    }
    if (g_EvictedPathCount < kEvictedPathMemory) {
        g_EvictedPathHashes[g_EvictedPathCount++] = key;
        return;
    }
    for (std::size_t i = 1; i < kEvictedPathMemory; ++i) {
        g_EvictedPathHashes[i - 1] = g_EvictedPathHashes[i];
    }
    g_EvictedPathHashes[kEvictedPathMemory - 1] = key;
}

// ---------------------------------------------------------------------------
// 核心判定
// ---------------------------------------------------------------------------
//: 路径是不是我们该管的形状：`gfx/` 开头的**相对**内容路径。
//: 绝对路径（`rom:/...`）是引擎内部已经解析过的形态，交给原函数即可。
bool IsContentRelativePath(const char* path, std::size_t length) {
    return length > 4 && std::memcmp(path, "gfx/", 4) == 0;
}

//: 解析器给出的挂载路径是不是**模组层**（`isaac_mods`）。
bool IsModLayerPath(const char* mounted) {
    if (mounted == nullptr) {
        return false;
    }
    return std::strstr(mounted, "isaac_mods") != nullptr;
}

//: 逐个挂载点前缀算候选键，回答"这条路径在缓存里有几份、其中几份不是模组层那份"。
//: `mode`：0 = 只看（不写），1 = 把"不是 owner 前缀"的那几份作废。
//:
//: ★ 为什么要有 `ownerPrefix`：**只作废"压住模组的那一份"，绝不作废模组自己那一份。**
//: 少了这一条，每次加载都会把模组那份也作废掉（引用计数减到 0、条目被回收）⇒ 下一次加载
//: 变成"不命中 ⇒ 重新开文件"，等于**每次都用文件读换掉一次缓存命中**，把缓存白设了。
//: `ownerPrefix` 由解析器给出的挂载路径反推（挂载路径一定以它开头）。
struct ScanResult {
    bool anyEntry{false};        // 缓存里至少有一份
    bool anyNonOwnerEntry{false};  // 其中至少有一份**不是** owner 前缀下的（= 会压住模组的那一份）
    bool anyZeroCount{false};    // 其中至少有一份计数已经是 0（⇒ 只能回收、**不能**减计数）
    std::uint32_t firstKey{0};
};

//: ★★ 2026-10-05（批次 366）：**只读扫描**，不再在这里改任何东西。
//: 作废那一动作搬回回调里、并且必须拿**引擎自己给的那个 `std::string`**（`ANM2::Load` 的第一个
//: 参数）去调 `AnmCache::RemoveReference` —— 因为那个函数**自己**会对每个挂载点前缀拼一次
//: "前缀+路径"（反汇编 `0x14D84`/`0x14DA0`），而且它要的是 libc++ 的 24 字节串对象。
//: 从前在这里传 `&buffer`（一个 `char[256]`、内容还是已经拼好的"前缀+路径"）**两样都错**。
ScanResult ScanCandidateEntries(const char* path, std::size_t length, const char* ownerPrefix,
                                bool* sawModPrefix = nullptr) {
    ScanResult result{};
    MountPointList mounts{};
    if (!ReadMountPoints(&mounts)) {
        return result;  // 挂载点表读不到 ⇒ 算不出候选键 ⇒ **什么都不做**（绝不猜）
    }
    // 候选键 = 每个挂载点前缀 + 本条路径（`.png` → `.pcx` 的改写与引擎一致）。
    // 这里只算键、不遍历缓存里的字符串 —— 于是不可能误伤别的资源。
    char buffer[256];
    for (std::uintptr_t item = mounts.begin; item + kMountPointEntrySize <= mounts.end;
         item += kMountPointEntrySize) {
        char prefix[kMaxMountPointText + 1];
        std::size_t prefixLength = 0;
        if (!ReadMountPointAt(item, prefix, sizeof(prefix), &prefixLength)) {
            continue;
        }
        // ★★★ 2026-10-05（批次 368）：**空前缀绝不能跳过。** 设备实测（`dist/gdb-read-20261005-1208*`）：
        //   引擎那张挂载点表有 7 项，**最后一项就是空串**；而 `AnmCache::Load2` 每次迭代都按
        //   `buf = 前缀 + 路径` 算键（`0xF654` `strncpy_s` 空串 + `0xF670` `strcat_s` 路径），
        //   最后一次迭代算出来的键就是**裸路径** `HashDJB2(<路径>)`；而 `Preload2` 建条目用的是
        //   **最后一次迭代的那个键**（`0xF734` 把 `w25` 交给 `Preload2`）⇒ **开机时缓存缺席、
        //   落盘加载出来的那一条（正是本体那份小地图）就存在这个"裸路径键"上**。
        //   从前这里 `continue` 掉空前缀 ⇒ 我们永远算不出那个键 ⇒ 扫描恒 `anyEntry = false`
        //   ⇒ 中继静默早退（真机：中继被调 178 次、问解析器 0 次）。
        if (prefixLength + length + 1 > sizeof(buffer)) {
            continue;
        }
        if (prefixLength != 0 && std::strstr(prefix, "isaac_mods") != nullptr &&
            sawModPrefix != nullptr) {
            *sawModPrefix = true;  // 这张表里到底有没有模组层（读数用）
        }
        std::memcpy(buffer, prefix, prefixLength);
        std::memcpy(buffer + prefixLength, path, length + 1);
        // `.png` → `.pcx`：★ 引擎（`Load2` 0xF6B8、`AddReference`、`RemoveReference`）除了把那
        //   4 字节改掉，还会在 `+4` 处**写 NUL 截断**（`strb wzr,[x0,#4]`）⇒ 我们也要截断，
        //   否则".png"后面还有字符的路径（例如 `x.png.foo`）算出来的键与引擎不同。
        if (char* png = std::strstr(buffer, ".png"); png != nullptr) {
            std::memcpy(png, ".pcx", 4);
            png[4] = '\0';
        }
        const std::uint32_t key = HashDjb2(buffer);
        std::uint32_t count = 0;
        if (!FindEntryRefCount(key, &count)) {
            continue;  // 这个前缀下没有条目 —— 正常（模组层自己那条一开始就还没有）
        }
        result.anyEntry = true;
        if (count == 0) {
            result.anyZeroCount = true;
        }
        if (result.firstKey == 0) {
            result.firstKey = key;
        }
        // 这一份是不是"owner 前缀下的"（= 模组自己那份，动不得）？
        // ★ 判据是**与 owner 前缀逐字节相等**，不是"owner 以它开头"：挂载点表里可能存在
        //   "一长一短且短的正好是长的开头"两项（例如模组目录与它下面的 `resources`），
        //   用"开头匹配"会把短那一项也当成 owner 而漏掉——那一项下的条目同样是会压住模组的。
        //   `ownerPrefix` 本身就是从**同一张挂载点表**里选出来的 ⇒ 相等判定是精确的。
        const bool underOwner = ownerPrefix != nullptr && ownerPrefix[0] != '\0' &&
                                prefixLength == std::strlen(ownerPrefix) &&
                                std::memcmp(prefix, ownerPrefix, prefixLength) == 0;
        if (!underOwner) {
            result.anyNonOwnerEntry = true;
        }
    }
    return result;
}

//: 从解析器给的挂载路径反推"owner 前缀"：**取最长的、确实是它前缀的那一项**。
//: 为什么取最长：短前缀可能只是长前缀的一部分（`resources` 是
//: `rom:/isaac_mods/mods/x/resources` 的子串），取最长才不会把模组自己那份误判成"别人的"。
bool FindOwnerPrefix(const char* mounted, char* out, std::size_t capacity) {
    if (mounted == nullptr || out == nullptr || capacity == 0) {
        return false;
    }
    MountPointList mounts{};
    if (!ReadMountPoints(&mounts)) {
        return false;
    }
    const std::size_t mountedLength = std::strlen(mounted);
    std::size_t best = 0;
    for (std::uintptr_t item = mounts.begin; item + kMountPointEntrySize <= mounts.end;
         item += kMountPointEntrySize) {
        char prefix[kMaxMountPointText + 1];
        std::size_t prefixLength = 0;
        if (!ReadMountPointAt(item, prefix, sizeof(prefix), &prefixLength)) {
            continue;
        }
        if (prefixLength == 0 || prefixLength > mountedLength || prefixLength >= capacity) {
            continue;
        }
        if (std::memcmp(prefix, mounted, prefixLength) != 0) {
            continue;
        }
        if (prefixLength > best) {
            std::memcpy(out, prefix, prefixLength);
            out[prefixLength] = '\0';
            best = prefixLength;
        }
    }
    return best != 0;
}

}  // namespace

// ---------------------------------------------------------------------------
// 读数接口
// ---------------------------------------------------------------------------
void NoteAnm2LoadRelayInstalled(bool installed, unsigned failureCode) noexcept {
    g_Anm2LoadOverrideState.relayState = installed ? 1U : 2U;
    g_Anm2LoadOverrideState.relayFailure = failureCode;
}

void NoteAnm2LoadRelayCallbackFired() noexcept {
    ++g_Anm2LoadOverrideState.callbackCount;
    // ★★★ 批次 384（2026-10-06）：**只看第一次** —— 记下本条中继首次被引擎调用的时刻。
    //   判据与理由见头文件那个字段的注释：把它与 `g_EarlyMountState.callbackFirstFiredTicks`
    //   （`Game::Init` 被调的时刻，同源同单位）比大小，就能直接回答
    //   "引擎第一次读共享资源时，我们的中继到底装了没有"。
    //   ★ 只在 0 时写 ⇒ 一次写入、之后不动（避免被后来的调用覆盖成"看起来更晚"）。
    if (g_Anm2LoadOverrideState.callbackFirstTicks == 0) {
        g_Anm2LoadOverrideState.callbackFirstTicks =
            static_cast<std::uint32_t>(isaac::runtime::RuntimePerfTick());
    }
}

void NoteAnm2LoadResolverAsked() noexcept { ++g_Anm2LoadOverrideState.resolverAsked; }

void NoteAnm2LoadOverrideDecision(std::uint32_t pathHash, bool staleFound,
                                  bool evicted) noexcept {
    g_Anm2LoadOverrideState.lastPathHash = pathHash;
    if (staleFound) {
        ++g_Anm2LoadOverrideState.staleFound;
    }
    if (evicted) {
        ++g_Anm2LoadOverrideState.evicted;
    }
}

Anm2LoadOverrideState Anm2LoadOverrideSnapshot() noexcept { return g_Anm2LoadOverrideState; }

// ---------------------------------------------------------------------------
// 批次 370（2026-10-05）：只读一次引擎那张挂载点表 —— "我们提前挂的挂载点进表了吗"
// ---------------------------------------------------------------------------
//
// 与中继那条路**分开的入口**：中继用的是安装时缓存下来的 `g_Bindings.mountPointsVector`，
// 而"提前挂载"那一步跑在**挂钩安装之前** —— 那时绑定还没解析，所以这里当场读一次 GOT 槽
// （`kContentMountPointsGotSlotOffset`），再走上**同一份** `ReadMountPointsAt` / `ReadMountPointAt`
// （元素 8 字节 `const char*` 那条 2026-10-05 定案的口径，见本文件上面那一大段）。
// 任何一步读不出来 ⇒ 返回 false（"没看到"），绝不猜。
bool EngineMountPointListHasModPrefix(const TargetModule& module) noexcept {
    if (module.size < sizeof(std::uintptr_t) ||
        kContentMountPointsGotSlotOffset > module.size - sizeof(std::uintptr_t)) {
        return false;
    }
    std::uintptr_t vector = 0;
    if (!engine_memory::ReadAt(module.base + kContentMountPointsGotSlotOffset, &vector,
                               &engine_memory::EngineMemoryReadable) ||
        vector == 0) {
        return false;
    }
    MountPointList list{};
    if (!ReadMountPointsAt(vector, &list)) {
        return false;
    }
    for (std::uintptr_t item = list.begin; item < list.end; item += kMountPointEntrySize) {
        char prefix[kMaxMountPointText];
        std::size_t length = 0;
        if (!ReadMountPointAt(item, prefix, sizeof(prefix), &length)) {
            continue;   // 单项读不出来：跳过它，不影响其余项（"看到有一条模组前缀"仍然算看到）
        }
        if (length != 0 && std::strstr(prefix, "isaac_mods") != nullptr) {
            return true;
        }
    }
    return false;
}

// ---------------------------------------------------------------------------
// 安装
// ---------------------------------------------------------------------------
//: 安装时把引擎侧绑定核对一遍（每个入口都逐字节核对序言，绝不把没核对过的地址变成能调的东西）。
bool PrepareAnm2LoadOverride(const TargetModule& module) {
    if (g_Bindings.fallbackEntry == 0) {
        return false;  // 中继本身没装上 ⇒ 不准备绑定（没��回退入口就没有"跑原函数"这一步）
    }
    bool ok = true;
    // ① 作废原语（两个入口都要）。
    g_Bindings.removeReference = engine_call::ResolveFunction<Bindings::RemoveRefFn>(
        module.base, module.size, kAnmCacheRemoveReferenceOffset,
        kAnmCacheRemoveReferenceExpectedBytes, &engine_memory::EngineMemoryReadable);
    g_Bindings.freeUnreferencedEntries = engine_call::ResolveFunction<Bindings::FreeEntriesFn>(
        module.base, module.size, kAnmCacheFreeUnreferencedEntriesOffset,
        kAnmCacheFreeUnreferencedEntriesExpectedBytes, &engine_memory::EngineMemoryReadable);
    ok = ok && g_Bindings.removeReference != nullptr &&
         g_Bindings.freeUnreferencedEntries != nullptr;
    // ② `g_AnmCache` / `g_ContentMountPoints` 两个 GOT 槽（读一次就是对象地址）。
    {
        std::uintptr_t cache = 0;
        std::uintptr_t mounts = 0;
        const auto slotReadable = &engine_memory::EngineMemoryReadable;
        ok = ok && module.size >= sizeof(std::uintptr_t) &&
             kAnmCacheGotSlotOffset <= module.size - sizeof(std::uintptr_t) &&
             engine_memory::ReadAt(module.base + kAnmCacheGotSlotOffset, &cache, slotReadable) &&
             cache != 0 &&
             kContentMountPointsGotSlotOffset <= module.size - sizeof(std::uintptr_t) &&
             engine_memory::ReadAt(module.base + kContentMountPointsGotSlotOffset, &mounts,
                                   slotReadable) &&
             mounts != 0;
        g_Bindings.anmCache = engine_memory::AsObject(cache);
        g_Bindings.mountPointsVector = mounts;
    }
    // ③ 解析器与它要的两个东西（内容管理器 + 引擎自己的 `delete[]`）。
    //    解析器入口**可能已经被贴图桥改写成跳转**（`HookId::ContentGetMountedFilePath`），
    //    所以这里**不**做逐字节守卫 —— 直接用它的入口地址（跳转桩会把控制权交回我们的桥，
    //    桥再调原函数，语义不变）。这一点与 `native_mods_menu_probe.cpp` 的处理一致。
    g_Bindings.getMounted =
        engine_call::AsFunction<Bindings::GetMountedFn>(module.base + kContentGetMountedFilePathOffset);
    g_Bindings.freePath = engine_call::ResolveFunction<Bindings::FreePathFn>(
        module.base, module.size, kGameOperatorDeleteArrayOffset,
        kGameOperatorDeleteArrayExpectedBytes, &engine_memory::EngineMemoryReadable);
    {
        std::uintptr_t manager = 0;
        const auto slotReadable = &engine_memory::EngineMemoryReadable;
        ok = ok && kContentManagerGotSlotOffset <= module.size - sizeof(std::uintptr_t) &&
             engine_memory::ReadAt(module.base + kContentManagerGotSlotOffset, &manager,
                                   slotReadable) &&
             manager != 0;
        g_Bindings.contentManager = engine_memory::AsObject(manager);
    }
    ok = ok && g_Bindings.freePath != nullptr;
    if (!ok) {
        // 绑定不齐 ⇒ **绝不半套使用**（宁可回到"共享路径仍吃本体那份"，也不冒误伤的风险）。
        g_Bindings = Bindings{};
        return false;
    }
    return true;
}

const Anm2LoadBindingsView& Anm2LoadBindings() noexcept {
    // 视图是**每次现填**的，不做类型双关（`-Werror=strict-aliasing` 挡的就是那种写法）：
    // 绑定结构里的三个字段直接拷进这块静态视图。字段很少，代价可忽略。
    static Anm2LoadBindingsView view{};
    view.getMounted = g_Bindings.getMounted;
    view.contentManager = g_Bindings.contentManager;
    view.freePath = g_Bindings.freePath;
    return view;
}

std::uintptr_t Anm2LoadFallbackEntry() noexcept { return g_Bindings.fallbackEntry; }

void PublishAnm2LoadFallbackEntry(std::uintptr_t entry) noexcept {
    g_Bindings.fallbackEntry = entry;
}

}  // namespace isaac::runtime::bridge

// ---------------------------------------------------------------------------
// 中继回调本身（`extern "C"`：形状 = 目标函数的 ABI）
// ---------------------------------------------------------------------------
//: `void ANM2::Load(std::string const& name, bool loadGraphics)`：
//: x0 = ANM2*、x1 = libc++ 串对象、w2 = loadGraphics。入口桩��**尾调用**，
//: 所以这里 `ret` 直接回到游戏调用方；跑原函数要靠回退入口。
extern "C" void EntryRelayAnm2LoadCallback(void* anm2, const void* name,
                                           std::uint32_t loadGraphics) {
    using namespace isaac::runtime;
    using namespace isaac::runtime::bridge;
    NoteAnm2LoadRelayCallbackFired();
    const auto original =
        engine_call::AsFunction<void (*)(void*, const void*, std::uint32_t)>(Anm2LoadFallbackEntry());
    if (original == nullptr) {
        return;  // 没有回退入口 ⇒ 什么都不做（绝不假装跑过原函数）
    }
    char path[256];
    std::size_t length = 0;
    if (!ReadNativeString(name, path, sizeof(path), &length) ||
        !IsContentRelativePath(path, length)) {
        original(anm2, name, loadGraphics);
        return;
    }
    // ① 先只读地看一眼缓存（**不**问解析器）：这条路径在缓存里到底有没有条目。
    //    真正的未命中在这里就返回 —— 那是绝大多数情况，而且引擎自己马上会去问解析器，
    //    我们不必替它问一遍。
    bool sawModPrefix = false;
    ScanResult scan = ScanCandidateEntries(path, length, nullptr, &sawModPrefix);
    if (!sawModPrefix) {
        // 引擎那张表是**开机快照**（设备实测：7 项全是本体层、没有一条 `isaac_mods`）⇒ 记下来，
        // 读数里一眼可见"我们面对的是一张不含模组层的老表"。
        g_Anm2LoadOverrideState.mountListFlags |= kMountListNoModPrefixBit;
    }
    if (!scan.anyEntry) {
        original(anm2, name, loadGraphics);
        return;
    }
    // ② 确实有"压着模组的那一份" ⇒ 现在才问解析器：这条路径到底归谁。
    const Anm2LoadBindingsView& bindings = Anm2LoadBindings();
    if (bindings.getMounted == nullptr || bindings.contentManager == nullptr ||
        bindings.freePath == nullptr) {
        original(anm2, name, loadGraphics);
        return;
    }
    NoteAnm2LoadResolverAsked();
    char* mounted = bindings.getMounted(bindings.contentManager, path);
    const bool modLayer = IsModLayerPath(mounted);
    // 从挂载路径反推"owner 前缀"（= 模组自己那份所在的挂载点），**必须在释放 mounted 之前**做。
    char ownerPrefix[kMaxMountPointText + 1];
    const bool haveOwner = modLayer && FindOwnerPrefix(mounted, ownerPrefix, sizeof(ownerPrefix));
    if (mounted != nullptr) {
        bindings.freePath(mounted);  // 引擎用 `new[]` 分配的，只能用引擎自己的 `delete[]`
    }
    if (!modLayer) {
        // 解析器说这条路径归本体层 ⇒ 缓存里那份是对的，**一份都不动**。
        original(anm2, name, loadGraphics);
        return;
    }
    if (!haveOwner) {
        // ★★ 2026-10-05（批次 368）：从前这里是"反推不出 owner 前缀 ⇒ 什么都不做"。
        //   设备实测证明那个前提**不成立**：引擎那张挂载点表是开机快照（7 项全是本体层、
        //   最后一项还是空串），**一条 `isaac_mods` 都没有** ⇒ 从它反推模组自己的前缀无从谈起。
        //   此时**不能**因此放弃：解析器已经答"这条路径归模组层"，而我们能算出来的每一个候选键
        //   都必然是本层/裸路径的键 —— 那正是压着模组的那一份。
        //   `ownerPrefix` 置空 ⇒ 扫描把"每个存在的键"都算作压着模组的（见 `underOwner` 的判据）。
        ownerPrefix[0] = '\0';
        g_Anm2LoadOverrideState.mountListFlags |= kMountListNoModPrefixBit;
    }
    // ③ 作废"压着模组的那几份"。
    //
    // ★★ 2026-10-05（批次 366）这里整段重写过，改动都是"改成引擎的形状"：
    //
    //   ③-a 用 owner 前缀扫一遍（只读）：这条路径在**不是** owner 前缀的地方还有没有条目。
    //        只剩模组自己那一份 ⇒ 已经是我们想要的状态，**一份都不动**
    //        （否则每次加载都白开一次文件，把缓存白设了）。
    //   ③-b 若其中**有计数已经是 0 的**条目，先调 `FreeUnreferencedEntries` 回收掉 ——
    //        那是引擎自己的原语，**只删计数为 0 的条目、一个计数都不减** ⇒ 不会下溢。
    //        这一步单独就能治好最常见的那种形态："本体条目早就没人引用、却还赖在 map 里"。
    //   ③-c 回收之后若还有"压着模组、计数 > 0"的条目，才调一次 `RemoveReference`：
    //        ★ 入参必须用**引擎自己交给我们那个 `std::string` 对象**（`ANM2::Load` 的第一个参数
    //        `name`，内容就是**相对路径**）—— 因为 `AnmCache::RemoveReference` 内部会对
    //        **每个**挂载点前缀各拼一次"前缀+路径"（反汇编 `0x14D84`/`0x14DA0`），
    //        而且它要的是 libc++ 的 24 字节串对象。从前传 `&buffer`（一个 `char[256]`、
    //        内容还是已经拼好的"前缀+路径"）**两样都错** ⇒ 一条计数也减不到（那是死代码）。
    //        ★ 它的语义是"把这条路径在**每个**前缀下的计数各减 1"（含模组自己那份）⇒
    //        所以**必须**先确认所有候选项计数都 > 0（否则那一格会下溢成 0xFFFFFFFF）。
    //        模组那份若因此被减到 0 而被回收，下一次 `Load` 会重新开文件拿到模组那份 ——
    //        结果正确，代价只是多一次文件读。
    ScanResult stale = ScanCandidateEntries(path, length, ownerPrefix);
    if (!stale.anyNonOwnerEntry) {
        NoteAnm2LoadOverrideDecision(stale.firstKey, false, false);
        original(anm2, name, loadGraphics);
        return;
    }
    if (AlreadyEvictedThisSession(stale.firstKey)) {
        // 这条路径本会话已经修过一次了（那一格现在装的就是模组那份）⇒ 不再动它。
        g_Anm2LoadOverrideState.mountListFlags |= kMountListRepeatSkipBit;
        NoteAnm2LoadOverrideDecision(stale.firstKey, true, false);
        original(anm2, name, loadGraphics);
        return;
    }
    bool evicted = false;
    if (stale.anyZeroCount) {
        // ③ 只回收**引用计数已经是 0** 的条目（引擎自己的原语，**一个计数都不减**）。
        //
        // ★★★ 2026-10-05（批次 369）：「减活引用来作废旧条目」这条路**被真机崩溃否决了**。
        //   批次 368 上卡后进一局：minimapi 的两行红字确实消失（说明模组那份赢了），
        //   但紧接着 **Data Abort**，落在引擎自己的 `ANM2::AnimationLayer::RenderFrame`
        //   （`Repentance.nrs + 0x8828`、故障地址 0），调用链是
        //   `Minimap::Render → ANM2::Render → AnimationLayer::RenderFrame`
        //   （崩溃报告：`dist/crash-20261005-1259/crash.log`）。
        //   机理：命中缓存时 `Load2` 建出来的是**指向该条目 `LayerData` 的 LayerState**
        //   （`0xF794` 起 `LayerState::Reset(LayerData*)`）⇒ **引擎自己的小地图 ANM2
        //   手里仍指着那条被我们回收掉的条目** ⇒ 释放后使用 ⇒ 下一次渲染就崩。
        //   ⇒ 批次 363 注释里那句"Load2 把数据拷进调用者的 ANM2 ⇒ 作废是安全的"**被这条崩溃证伪**。
        //   ⇒ 从此**一律不调用 `RemoveReference`**（它会把活引用减掉）；只做"回收计数为 0 的条目"，
        //     那是引擎自己在换语言 / 重置时也走的路（`0x14F64`），按定义不会动到活条目。
        g_Bindings.freeUnreferencedEntries(g_Bindings.anmCache);
        evicted = true;
        stale = ScanCandidateEntries(path, length, ownerPrefix);  // 回收之后再确认一次
    }
    if (evicted) {
        RememberEvicted(stale.firstKey);
    }
    NoteAnm2LoadOverrideDecision(stale.firstKey, true, evicted);
    original(anm2, name, loadGraphics);
}
