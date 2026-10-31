#pragma once
#include <array>
#include <cstddef>
#include <cstdint>

namespace isaac::runtime::notice::integrity {
using Digest = std::array<std::uint8_t, 32>;
class Sha256 {
public:
    Sha256() noexcept;
    void Update(const void*, std::size_t) noexcept;
    Digest Finish() noexcept;
private:
    alignas(16) unsigned char storage_[256]{};
};
enum class ReadStatus { Ok, NotFound, IoError };
struct ReadPort {
    void* context;
    ReadStatus (*open)(void*, const char*, std::uint64_t*);
    ReadStatus (*read)(void*, void*, std::size_t, std::size_t*);
    void (*close)(void*);
};
inline constexpr std::size_t kMaxEntries = 64, kMaxManifestBytes = 16384,
                             kPathBytes = 256, kReadChunk = 8192;
struct Entry { std::uint64_t size; Digest digest; char path[kPathBytes]; };
struct Manifest { unsigned count; Entry entries[kMaxEntries]; };
enum class Failure {
    None, InvalidPort, ManifestMissing, ManifestRead, ManifestDigest,
    ManifestFormat, ResourceMissing, ResourceSize, ResourceRead, ResourceDigest,
    CodeIntegrity
};
struct Verdict { Failure failure; unsigned entryIndex; std::uint64_t bytesRead; };
// Calls are serialized on the game thread. Both operations share fixed static
// scratch and are nonreentrant. Keep the caller-owned Manifest in static storage.
Verdict VerifyPackage(const ReadPort&, const char* manifestPath,
                      const Digest& expectedManifest, const char* expectedVersion,
                      unsigned expectedCount, Manifest& output) noexcept;
Verdict VerifyEntry(const ReadPort&, const Entry&, unsigned index = 0) noexcept;
}
