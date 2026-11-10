#include "infrastructure/persistence/sd_storage.hpp"
#include "infrastructure/persistence/sdk_image.hpp"
#include "module_finder.hpp"
#include "lib.hpp"
#include "lib/nx/nx.h"

#include <atomic>
#include <cstdio>
#include <cstring>

namespace isaac::runtime {

SdStorageState g_SdStorageState{};

namespace {
SdFileApi g_api{};
std::atomic<bool> g_sdMods{false};
using OpenDirectoryFn = std::uint32_t (*)(std::uint64_t*, const char*, int);
using CreateFileFn = std::uint32_t (*)(const char*, std::int64_t);
OpenDirectoryFn g_openDirectory{};
CreateFileFn g_createFile{};

bool Memory(std::uintptr_t address, std::size_t size, MemoryInfo* out = nullptr) noexcept {
    MemoryInfo info{}; u32 page{};
    if (!size || address > UINTPTR_MAX - size ||
        R_FAILED(svcQueryMemory(&info, &page, address)) || !info.size ||
        address < info.addr || address - info.addr > info.size ||
        size > info.size - (address - info.addr) || !(info.perm & Perm_R)) return false;
    if (out) *out = info;
    return true;
}

bool ModuleType(const MemoryInfo& info) noexcept {
    const auto type = info.type & MemState_Type;
    return type == MemType_CodeStatic || type == MemType_CodeMutable ||
        type == MemType_ModuleCodeStatic || type == MemType_ModuleCodeMutable;
}

bool ImageAt(std::uintptr_t anchor, SdkImage* out) noexcept {
    MemoryInfo text{};
    if (!Memory(anchor, 4, &text) || text.perm != Perm_Rx || !ModuleType(text) ||
        text.addr > UINTPTR_MAX - text.size || text.size > 0x10000000) return false;
    SdkImage image{}; image.base = text.addr;
    image.ranges[image.count++] = {text.addr, text.size, true};
    auto end = text.addr + text.size;
    // Only the first RX range followed by its RO/RW ranges is eligible. A new
    // executable mapping, unreadable gap or excessive span ends the module.
    for (unsigned i = 0; i < 7; ++i) {
        MemoryInfo next{};
        if (!Memory(end, 1, &next) || next.addr != end || !ModuleType(next) ||
            (next.perm & Perm_X) || next.size > 0x10000000 ||
            end - image.base > 0x10000000 - next.size) break;
        image.ranges[image.count++] = {next.addr, next.size, false};
        end += next.size;
    }
    if (!image.Parse()) return false;
    *out = image; return true;
}

template<std::size_t N>
bool Import(const TargetModule& module, std::uintptr_t offset, const std::array<u8, N>& expected,
            std::uintptr_t* slot, std::uintptr_t* target) noexcept {
    const auto entry = module.base + offset;
    if (N != 16 || !module.Contains(entry, N) || !Memory(entry, N) ||
        std::memcmp(reinterpret_cast<const void*>(entry), expected.data(), N)) return false;
    std::uint32_t instructions[4]{}; std::memcpy(instructions, expected.data(), 16);
    *slot = SdkImage::ImportSlot(entry, instructions);
    if (!*slot || (*slot & 7) || !Memory(*slot, 8)) return false;
    *target = __atomic_load_n(reinterpret_cast<const std::uintptr_t*>(*slot), __ATOMIC_ACQUIRE);
    return *target != 0;
}

bool Owner(void*) noexcept {
    u64 thread{};
    return R_SUCCEEDED(svcGetThreadId(&thread, CUR_THREAD_HANDLE)) &&
        thread == g_SdStorageState.ownerThread;
}

const char* ModPath(const char* path, char* translated) noexcept {
    constexpr char prefix[] = "rom:/isaac_mods";
    if (!g_sdMods.load(std::memory_order_acquire) || !path ||
        std::strncmp(path, prefix, sizeof(prefix) - 1) ||
        (path[sizeof(prefix) - 1] != '/' && path[sizeof(prefix) - 1] != '\0')) return path;
    const auto n = std::strlen(path);
    // The SDK enforces the same path capacity; never truncate a request into a
    // different existing file. Returning nullptr produces an explicit failure.
    if (n > 700) return nullptr;
    std::memcpy(translated, "isaacsd:/", 9);
    std::size_t used = 9;
    for (std::size_t start = 5; start < n;) {
        std::size_t end = start;
        while (end < n && path[end] != '/') ++end;
        const auto length = end - start;
        if (length == 2 && path[start] == '.' && path[start + 1] == '.') {
            if (used == 9) return path;
            while (used > 9 && translated[used - 1] != '/') --used;
            if (used > 9) --used;
        } else if (length && !(length == 1 && path[start] == '.')) {
            if (used != 9) translated[used++] = '/';
            std::memcpy(translated + used, path + start, length); used += length;
        }
        start = end + 1;
    }
    translated[used] = '\0';
    // Classify the normalised path, so ../ cannot change filesystem ownership.
    if (std::strncmp(translated + 9, "isaac_mods", 10) ||
        (translated[19] != '/' && translated[19] != '\0')) return path;
    if (n && path[n - 1] == '/') { translated[used++] = '/'; translated[used] = '\0'; }
    return translated;
}

std::uint32_t OpenModFile(std::uint64_t* handle, const char* path, int mode) noexcept {
    char translated[768]; path = ModPath(path, translated);
    return path ? g_api.open(handle, path, mode) : 0x2ee802;
}
std::uint32_t OpenModDirectory(std::uint64_t* handle, const char* path, int mode) noexcept {
    char translated[768]; path = ModPath(path, translated);
    return path ? g_openDirectory(handle, path, mode) : 0x2ee802;
}
std::uint32_t CreateModFile(const char* path, std::int64_t size) noexcept {
    char translated[768]; path = ModPath(path, translated);
    return path ? g_createFile(path, size) : 0x2ee802;
}
std::uint32_t DeleteModFile(const char* path) noexcept {
    char translated[768]; path = ModPath(path, translated);
    return path ? g_api.remove(path) : 0x2ee802;
}

bool PatchSlot(std::uintptr_t slot, std::uintptr_t expected, std::uintptr_t target) noexcept {
    MemoryInfo info{};
    if (!Memory(slot, 8, &info) ||
        __atomic_load_n(reinterpret_cast<const std::uintptr_t*>(slot), __ATOMIC_ACQUIRE) != expected) return false;
    if (info.perm & Perm_W) {
        __atomic_store_n(reinterpret_cast<std::uintptr_t*>(slot), target, __ATOMIC_RELEASE);
    } else {
        exl::util::RwPages pages(slot, 8);
        __atomic_store_n(reinterpret_cast<std::uintptr_t*>(pages.GetRw()), target, __ATOMIC_RELEASE);
        pages.Flush();
    }
    return __atomic_load_n(reinterpret_cast<const std::uintptr_t*>(slot), __ATOMIC_ACQUIRE) == target;
}

Status InstallModPaths(const TargetModule& module, const SdkImage& sdk) noexcept {
    std::uintptr_t slots[4]{}, targets[4]{};
    if (!Import(module, kFilesysOpenFileThunkOffset, kFilesysOpenFileThunkExpectedBytes, &slots[0], &targets[0]) ||
        !Import(module, kFilesysOpenDirectoryThunkOffset, kFilesysOpenDirectoryThunkExpectedBytes, &slots[1], &targets[1]) ||
        !Import(module, kFilesysCreateFileThunkOffset, kFilesysCreateFileThunkExpectedBytes, &slots[2], &targets[2]) ||
        !Import(module, kFilesysDeleteFileThunkOffset, kFilesysDeleteFileThunkExpectedBytes, &slots[3], &targets[3]))
        return Status{StatusCode::Unsupported};
    const char* const names[]{"_ZN2nn2fs8OpenFileEPNS0_10FileHandleEPKci",
        "_ZN2nn2fs13OpenDirectoryEPNS0_15DirectoryHandleEPKci", "_ZN2nn2fs10CreateFileEPKcl", "_ZN2nn2fs10DeleteFileEPKc"};
    // The supported NRO's PLT0. Unused CreateFile/DeleteFile imports still point
    // here at Game::Init. Verify it, but call only the independent SDK export.
    constexpr std::uintptr_t kResolverOffset = 0x66faa0;
    constexpr unsigned char kResolverBytes[]{0xf0,0x7b,0xbf,0xa9,0x70,0x21,0x00,0xd0,
                                            0x11,0x62,0x46,0xf9,0x10,0x02,0x33,0x91};
    const auto resolver = module.base + kResolverOffset;
    const bool resolverVerified = module.Contains(resolver, sizeof(kResolverBytes)) &&
        Memory(resolver, sizeof(kResolverBytes)) &&
        std::memcmp(reinterpret_cast<const void*>(resolver), kResolverBytes, sizeof(kResolverBytes)) == 0;
    std::uintptr_t functions[4]{};
    for (unsigned i = 0; i < 4; ++i) {
        functions[i] = sdk.FindFunction(names[i]);
        if (!SdkImage::ImportTargetAllowed(targets[i], functions[i], resolverVerified ? resolver : 0))
            return Status{StatusCode::Rejected};
    }
    g_openDirectory = reinterpret_cast<OpenDirectoryFn>(functions[1]);
    g_createFile = reinterpret_cast<CreateFileFn>(functions[2]);
    const std::uintptr_t callbacks[]{reinterpret_cast<std::uintptr_t>(&OpenModFile),
        reinterpret_cast<std::uintptr_t>(&OpenModDirectory), reinterpret_cast<std::uintptr_t>(&CreateModFile),
        reinterpret_cast<std::uintptr_t>(&DeleteModFile)};
    unsigned done = 0;
    for (; done < 4; ++done) if (!PatchSlot(slots[done], targets[done], callbacks[done])) break;
    if (done != 4) {
        for (unsigned i = 0; i < done; ++i) (void)PatchSlot(slots[i], callbacks[i], targets[i]);
        return Status{StatusCode::IoFailure};
    }
    g_sdMods.store(true, std::memory_order_release);
    g_SdStorageState.modsOnSd = 1;
    return Status::Ok();
}
}

Status InitializeSdStorage(SdSaveFileAdapter& port) noexcept {
    static bool attempted = false;
    static Status result{StatusCode::Unsupported};
    if (attempted) return result;
    attempted = true;
    auto fail = [&](StatusCode code, std::uint32_t rc = 0) {
        g_SdStorageState.result = rc ? rc : 0x80000000u | static_cast<std::uint32_t>(code);
        result = Status{code}; return result;
    };
    u64 thread{};
    if (R_FAILED(svcGetThreadId(&thread, CUR_THREAD_HANDLE))) return fail(StatusCode::Unsupported);
    g_SdStorageState.ownerThread = thread; g_SdStorageState.stage = 1;
    const auto module = FindTargetModule();
    std::uintptr_t slot{}, open{}, size{};
    if (!module || module->buildId != kTargetBuildId ||
        !Import(*module, kFilesysOpenFileThunkOffset, kFilesysOpenFileThunkExpectedBytes, &slot, &open) ||
        !Import(*module, kFilesysGetFileSizeThunkOffset, kFilesysGetFileSizeThunkExpectedBytes, &slot, &size))
        return fail(StatusCode::Unsupported);
    SdkImage sdk{};
    if (!ImageAt(open, &sdk) || sdk.FindFunction("_ZN2nn2fs8OpenFileEPNS0_10FileHandleEPKci") != open ||
        sdk.FindFunction("_ZN2nn2fs11GetFileSizeEPlNS0_10FileHandleE") != size) return fail(StatusCode::Rejected);
    g_SdStorageState.sdkBase = sdk.base; g_SdStorageState.stage = 2;
#define SD_BIND(field, symbol) g_api.field = reinterpret_cast<decltype(g_api.field)>(sdk.FindFunction(symbol)); if (!g_api.field) return fail(StatusCode::Unsupported)
    SD_BIND(create, "_ZN2nn2fs10CreateFileEPKcli");
    SD_BIND(open, "_ZN2nn2fs8OpenFileEPNS0_10FileHandleEPKci");
    SD_BIND(close, "_ZN2nn2fs9CloseFileENS0_10FileHandleE");
    SD_BIND(size, "_ZN2nn2fs11GetFileSizeEPlNS0_10FileHandleE");
    SD_BIND(read, "_ZN2nn2fs8ReadFileEPmNS0_10FileHandleElPvm");
    SD_BIND(write, "_ZN2nn2fs9WriteFileENS0_10FileHandleElPKvmRKNS0_11WriteOptionE");
    SD_BIND(flush, "_ZN2nn2fs9FlushFileENS0_10FileHandleE");
    SD_BIND(remove, "_ZN2nn2fs10DeleteFileEPKc");
    SD_BIND(rename, "_ZN2nn2fs10RenameFileEPKcS2_");
#undef SD_BIND
    const auto mount = reinterpret_cast<std::uint32_t (*)(const char*)>(sdk.FindFunction("_ZN2nn2fs11MountSdCardEPKc"));
    const auto mkdir = reinterpret_cast<std::uint32_t (*)(const char*)>(sdk.FindFunction("_ZN2nn2fs15CreateDirectoryEPKc"));
    const auto type = reinterpret_cast<std::uint32_t (*)(std::int32_t*, const char*)>(sdk.FindFunction("_ZN2nn2fs12GetEntryTypeEPNS0_18DirectoryEntryTypeEPKc"));
    struct Uid { std::uint64_t low, high; };
    const auto user = reinterpret_cast<std::uint32_t (*)(Uid*)>(sdk.FindFunction("_ZN2nn7account17GetLastOpenedUserEPNS0_3UidE"));
    if (!mount || !mkdir || !type || !user) return fail(StatusCode::Unsupported);
    // Own this mount only after our call succeeds. A pre-existing mount name is
    // not assumed to refer to SD, even if it has an apparently familiar path.
    auto rc = mount("isaacsd");
    if (rc) return fail(StatusCode::IoFailure, rc);
    g_SdStorageState.stage = 3;
    Uid uid{}; rc = user(&uid);
    if (rc || (!uid.low && !uid.high)) return fail(StatusCode::IoFailure, rc);
    char root[160]{};
    std::snprintf(root, sizeof(root), "isaacsd:/switch/isaac-runtime/users/%016llx%016llx/",
        static_cast<unsigned long long>(uid.high), static_cast<unsigned long long>(uid.low));
    for (std::size_t i = 9; root[i]; ++i) {
        if (root[i] != '/') continue;
        root[i] = '\0'; std::int32_t entryType{}; rc = type(&entryType, root);
        if (rc == 0x202) { rc = mkdir(root); entryType = 0; }
        root[i] = '/';
        if (rc || entryType != 0) return fail(StatusCode::IoFailure, rc);
    }
    result = port.Configure(g_api, root, Owner, nullptr);
    if (!result.ok()) return result;
    g_SdStorageState.stage = 4;
    std::int32_t modsType{}; rc = type(&modsType, "isaacsd:/isaac_mods/mods");
    if (rc != 0x202 && (rc || modsType != 0)) return fail(StatusCode::IoFailure, rc);
    if (!rc) {
        result = InstallModPaths(*module, sdk);
        if (!result.ok()) return fail(result.code());
    }
    g_SdStorageState.stage = 5; result = Status::Ok(); return result;
}

} // namespace isaac::runtime
