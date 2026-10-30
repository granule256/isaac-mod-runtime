#include "notice_integrity.hpp"
#include <cstring>
#include <limits>

namespace isaac::runtime::notice::integrity {
namespace {
// No heap allocation or large game-stack objects. Startup/language changes are
// serialized; the caller must not invoke either verifier from read callbacks.
char manifestBytes[kMaxManifestBytes];
unsigned char readChunk[kReadChunk];
bool ValidPort(const ReadPort& port) noexcept { return port.open && port.read && port.close; }
struct OpenFile {
    const ReadPort& port;
    ~OpenFile() { port.close(port.context); }
};
bool Consume(const char*& pos, const char* end, const char* text) noexcept {
    const char* cursor = pos;
    while (*text) {
        if (cursor == end || *cursor != *text) return false;
        ++cursor; ++text;
    }
    pos = cursor;
    return true;
}
int Hex(char c) noexcept {
    if (c >= '0' && c <= '9') return c - '0';
    if (c >= 'a' && c <= 'f') return c - 'a' + 10;
    return -1;
}
bool Language(const char* code) noexcept {
    constexpr const char* codes[] = {"en", "de", "es", "fr", "jp", "kr", "ru", "zh"};
    for (auto* candidate : codes)
        if (code[0] == candidate[0] && code[1] == candidate[1]) return true;
    return false;
}
bool ValidPath(const char* path) noexcept {
    const char* pos = path;
    const char* end = path + std::strlen(path);
    if (!Consume(pos, end, "rom:/rp_patch/resources")) return false;
    char mirror[2]{};
    if (pos != end && *pos == '.') {
        if (end - pos < 3) return false;
        mirror[0] = pos[1]; mirror[1] = pos[2]; pos += 3;
        if (!Language(mirror) || (mirror[0] == 'e' && mirror[1] == 'n')) return false;
    }
    if (!Consume(pos, end, "/gfx/ui/main menu/isaac-switch/nnotice_")) return false;
    if (end - pos < 2 || !Language(pos)) return false;
    if (mirror[0] && (mirror[0] != pos[0] || mirror[1] != pos[1])) return false;
    pos += 2;
    return Consume(pos, end, ".pcx") ? pos == end : (Consume(pos, end, ".anm2") && pos == end);
}
bool Parse(const char* bytes, std::size_t size, const char* version,
           unsigned count, Manifest& output) noexcept {
    output.count = 0;
    if (!version || !count || count > kMaxEntries) return false;
    const char* pos = bytes;
    const char* end = bytes + size;
    if (!Consume(pos, end, "ISAAC-NOTICE/1\n") || !Consume(pos, end, version)
        || !Consume(pos, end, "\n")) return false;
    while (pos != end && output.count < count) {
        auto& entry = output.entries[output.count];
        entry.size = 0;
        unsigned digits = 0;
        bool leadingZero = pos != end && *pos == '0';
        while (pos != end && *pos >= '0' && *pos <= '9') {
            const unsigned digit = static_cast<unsigned>(*pos++ - '0');
            if (entry.size > (std::numeric_limits<std::uint64_t>::max() - digit) / 10) return false;
            entry.size = entry.size * 10 + digit;
            ++digits;
        }
        if (!digits || (leadingZero && digits != 1) || !Consume(pos, end, "\t")) return false;
        for (auto& value : entry.digest) {
            if (end - pos < 2) return false;
            const int high = Hex(pos[0]), low = Hex(pos[1]);
            if (high < 0 || low < 0) return false;
            value = static_cast<std::uint8_t>((high << 4) | low); pos += 2;
        }
        if (!Consume(pos, end, "\t")) return false;
        std::size_t length = 0;
        while (pos != end && *pos != '\n') {
            const unsigned char c = static_cast<unsigned char>(*pos++);
            if (c < 32 || c > 126 || c == '\\' || length >= kPathBytes - 1) return false;
            entry.path[length++] = static_cast<char>(c);
        }
        entry.path[length] = 0;
        if (!Consume(pos, end, "\n") || !ValidPath(entry.path)) return false;
        if (output.count && std::strcmp(output.entries[output.count - 1].path, entry.path) >= 0) return false;
        ++output.count;
    }
    return pos == end && output.count == count;
}
}
Verdict VerifyEntry(const ReadPort& port, const Entry& entry, unsigned index) noexcept {
    if (!ValidPort(port)) return {Failure::InvalidPort, index, 0};
    std::uint64_t size = 0;
    const auto status = port.open(port.context, entry.path, &size);
    if (status != ReadStatus::Ok)
        return {status == ReadStatus::NotFound ? Failure::ResourceMissing : Failure::ResourceRead, index, 0};
    OpenFile file{port};
    if (size != entry.size) return {Failure::ResourceSize, index, 0};
    Sha256 sha;
    std::uint64_t done = 0;
    while (done < size) {
        const auto request = static_cast<std::size_t>(size - done < kReadChunk ? size - done : kReadChunk);
        std::size_t got = 0;
        const auto read = port.read(port.context, readChunk, request, &got);
        if (read != ReadStatus::Ok || !got || got > request) return {Failure::ResourceRead, index, done};
        sha.Update(readChunk, got);
        done += got;
    }
    return {sha.Finish() == entry.digest ? Failure::None : Failure::ResourceDigest, index, done};
}
Verdict VerifyPackage(const ReadPort& port, const char* manifestPath,
                      const Digest& expectedManifest, const char* expectedVersion,
                      unsigned expectedCount, Manifest& output) noexcept {
    output.count = 0;
    if (!ValidPort(port) || !manifestPath || !expectedVersion) return {Failure::InvalidPort, 0, 0};
    std::uint64_t size = 0, done = 0;
    const auto opened = port.open(port.context, manifestPath, &size);
    if (opened != ReadStatus::Ok)
        return {opened == ReadStatus::NotFound ? Failure::ManifestMissing : Failure::ManifestRead, 0, 0};
    {
        OpenFile file{port};
        if (size > kMaxManifestBytes) return {Failure::ManifestRead, 0, 0};
        Sha256 sha;
        while (done < size) {
            const auto request = static_cast<std::size_t>(size - done < kReadChunk ? size - done : kReadChunk);
            std::size_t got = 0;
            const auto read = port.read(port.context, manifestBytes + done, request, &got);
            if (read != ReadStatus::Ok || !got || got > request) return {Failure::ManifestRead, 0, done};
            sha.Update(manifestBytes + done, got);
            done += got;
        }
        if (sha.Finish() != expectedManifest) return {Failure::ManifestDigest, 0, done};
    }
    if (!Parse(manifestBytes, static_cast<std::size_t>(size), expectedVersion, expectedCount, output)) {
        output.count = 0;
        return {Failure::ManifestFormat, 0, done};
    }
    for (unsigned i = 0; i < output.count; ++i) {
        auto verdict = VerifyEntry(port, output.entries[i], i);
        done += verdict.bytesRead;
        if (verdict.failure != Failure::None) return {verdict.failure, i, done};
    }
    return {Failure::None, 0, done};
}
}
