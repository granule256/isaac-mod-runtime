#include "notice_integrity_native.hpp"

extern "C" { std::uint32_t g_NoticeIntegrityState[16]{}; }

#if defined(__SWITCH__) && !defined(EXL_DIAGNOSTIC_STAGE) && !defined(EXL_STARTUP_PROBE_STAGE)
#include "notice_integrity.hpp"
#include "title_notice_generated.hpp"
#include "module_finder.hpp"
#include "runtime_constants.hpp"
#include "infrastructure/call/engine_call_access.hpp"
#include "infrastructure/memory/engine_field_access.hpp"
#include "interfaces/lua/runtime_perf.hpp"
#include <algorithm>
#include <cstring>

namespace isaac::runtime::notice::integrity {
std::atomic<unsigned> g_ValidationState{kUnchecked};
extern "C" { extern const Digest g_NoticeIntegrityExpectedRoot = kIntegrityManifestDigest; }
namespace {
namespace memory = isaac::runtime::engine_memory;
namespace calls = isaac::runtime::engine_call;

struct Reader {
    std::uint32_t (*open)(std::uint64_t*, const char*, int){};
    std::uint32_t (*size)(std::int64_t*, std::uint64_t){};
    std::uint32_t (*read)(std::uint64_t*, std::uint64_t, std::int64_t, void*, std::size_t){};
    void (*close)(std::uint64_t){};
    std::uint64_t handle{}, position{};
    bool opened{};
    alignas(0x1000) unsigned char buffer[kReadChunk]{};
};
Reader g_Reader{};
Manifest g_Manifest{};

ReadStatus Map(std::uint32_t result, unsigned operation) noexcept {
    g_NoticeIntegrityState[9] = result;
    g_NoticeIntegrityState[10] = operation;
    if (!result) return ReadStatus::Ok;
    if (result == 0x202 || result == 0x2EE02 || result == 0x35F202) return ReadStatus::NotFound;
    return ReadStatus::IoError;
}

void Close(void* context) noexcept {
    auto& reader = *static_cast<Reader*>(context);
    if (reader.opened) reader.close(reader.handle);
    reader.opened = false;
}

ReadStatus Open(void* context, const char* path, std::uint64_t* size) noexcept {
    auto& reader = *static_cast<Reader*>(context);
    Close(context);
    const auto opened = Map(reader.open(&reader.handle, path, 1), 1);
    if (opened != ReadStatus::Ok) return opened;
    reader.opened = true;
    reader.position = 0;
    std::int64_t length{};
    const auto sized = Map(reader.size(&length, reader.handle), 2);
    if (sized != ReadStatus::Ok || length < 0) {
        Close(context);
        return ReadStatus::IoError;
    }
    *size = static_cast<std::uint64_t>(length);
    return ReadStatus::Ok;
}

ReadStatus Read(void* context, void* target, std::size_t capacity, std::size_t* bytes) noexcept {
    auto& reader = *static_cast<Reader*>(context);
    *bytes = 0;
    if (!reader.opened || !target) return ReadStatus::IoError;
    // Native ReadFile uses a page-aligned staging buffer even if the portable
    // verifier asks for a partial read into an unaligned manifest destination.
    const auto wanted = std::min(capacity, sizeof(reader.buffer));
    std::uint64_t got{};
    const auto result = Map(reader.read(&got, reader.handle,
        static_cast<std::int64_t>(reader.position), reader.buffer, wanted), 3);
    if (result != ReadStatus::Ok || got > wanted) return ReadStatus::IoError;
    std::memcpy(target, reader.buffer, static_cast<std::size_t>(got));
    reader.position += got;
    *bytes = static_cast<std::size_t>(got);
    return ReadStatus::Ok;
}

ReadPort Port() noexcept { return {&g_Reader, &Open, &Read, &Close}; }

bool Resolve(const TargetModule& module) noexcept {
    g_Reader.open = calls::ResolveFunction<decltype(g_Reader.open)>(module.base, module.textSize,
        kFilesysOpenFileThunkOffset, kFilesysOpenFileThunkExpectedBytes, &memory::EngineMemoryReadable);
    g_Reader.size = calls::ResolveFunction<decltype(g_Reader.size)>(module.base, module.textSize,
        kFilesysGetFileSizeThunkOffset, kFilesysGetFileSizeThunkExpectedBytes, &memory::EngineMemoryReadable);
    g_Reader.read = calls::ResolveFunction<decltype(g_Reader.read)>(module.base, module.textSize,
        kFilesysReadFileThunkOffset, kFilesysReadFileThunkExpectedBytes, &memory::EngineMemoryReadable);
    g_Reader.close = calls::ResolveFunction<decltype(g_Reader.close)>(module.base, module.textSize,
        kFilesysCloseFileThunkOffset, kFilesysCloseFileThunkExpectedBytes, &memory::EngineMemoryReadable);
    return g_Reader.open && g_Reader.size && g_Reader.read && g_Reader.close;
}

void Publish(const Verdict& verdict, std::uint64_t started) noexcept {
    const unsigned state = verdict.failure == Failure::None ? kValid : kBlocked;
    g_NoticeIntegrityState[0] = state;
    g_NoticeIntegrityState[1] = static_cast<unsigned>(verdict.failure);
    g_NoticeIntegrityState[2] = verdict.entryIndex;
    g_NoticeIntegrityState[3] = verdict.failure == Failure::None ? g_Manifest.count : verdict.entryIndex;
    g_NoticeIntegrityState[4] = static_cast<std::uint32_t>(verdict.bytesRead);
    g_NoticeIntegrityState[5] = static_cast<std::uint32_t>(verdict.bytesRead >> 32);
    const auto frequency = RuntimePerfTicksPerSecond();
    const auto micros = frequency ? (RuntimePerfTick() - started) * 1000000ULL / frequency : 0;
    g_NoticeIntegrityState[6] = static_cast<std::uint32_t>(micros);
    g_NoticeIntegrityState[12] = static_cast<std::uint32_t>(micros >> 32);
    g_NoticeIntegrityState[11] = g_Manifest.count;
    g_ValidationState.store(state, std::memory_order_release);
}
}

bool Ensure(const TargetModule& module) noexcept {
    if (RuntimeAllowed()) return true;
    if (Blocked()) return false;
    g_ValidationState.store(kChecking, std::memory_order_release);
    const auto started = RuntimePerfTick();
    ++g_NoticeIntegrityState[7];
    const auto verdict = Resolve(module) ? VerifyPackage(Port(), kIntegrityManifestPath,
        g_NoticeIntegrityExpectedRoot, kVersion, kIntegrityEntryCount, g_Manifest)
        : Verdict{Failure::InvalidPort, 0, 0};
    Publish(verdict, started);
    return RuntimeAllowed();
}

bool VerifyLocale(unsigned language) noexcept {
    if (!RuntimeAllowed()) return false;
    const auto started = RuntimePerfTick();
    ++g_NoticeIntegrityState[8];
    if (language >= kLocaleCount) {
        Publish({Failure::ManifestFormat, 0, 0}, started);
        return false;
    }
    const char* animation = kLocaleAssets[language].assetPath;
    char image[kPathBytes]{};
    const auto length = std::strlen(animation);
    if (length < 5 || length >= sizeof(image)) {
        Publish({Failure::ManifestFormat, 0, 0}, started);
        return false;
    }
    std::memcpy(image, animation, length - 5);
    std::memcpy(image + length - 5, ".pcx", 5);
    std::uint64_t bytes{};
    unsigned checked{};
    for (unsigned i = 0; i < g_Manifest.count; ++i) {
        const auto& entry = g_Manifest.entries[i];
        const auto size = std::strlen(entry.path);
        const auto matches = [&](const char* suffix) {
            const auto n = std::strlen(suffix);
            return size >= n && std::strcmp(entry.path + size - n, suffix) == 0;
        };
        if (!matches(animation) && !matches(image)) continue;
        auto result = VerifyEntry(Port(), entry, i);
        bytes += result.bytesRead;
        if (result.failure != Failure::None) { result.bytesRead = bytes; Publish(result, started); return false; }
        ++checked;
    }
    const unsigned expected = language == 0 ? 2 : 4;
    if (checked != expected) {
        Publish({Failure::ManifestFormat, 0, bytes}, started);
        return false;
    }
    return true;
}
}
#endif
