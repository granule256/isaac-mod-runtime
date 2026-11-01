#pragma once

#include <cstddef>
#include <cstring>

namespace GameFileReader {

// Used only after an exact script open fails, on the game thread. The backend
// returns the original entry name; path keys and file bytes are never folded.
struct ScriptPathResolver {
    static constexpr std::size_t kPathCapacity = 512;
    static constexpr std::size_t kCacheEntries = 16;
    using FindNameFn = bool (*)(void*, const char* parent, const char* requested,
                                bool directory, char* actual, std::size_t capacity);
    FindNameFn findName{nullptr};
    void* context{nullptr};

    static bool EqualAsciiCase(const char* left, const char* right) noexcept {
        while (*left != '\0' && *right != '\0') {
            const auto fold = [](unsigned char value) {
                return value >= 'A' && value <= 'Z' ? value + ('a' - 'A') : value;
            };
            if (fold(static_cast<unsigned char>(*left++)) !=
                fold(static_cast<unsigned char>(*right++))) return false;
        }
        return *left == *right;
    }

    bool Resolve(const char* requested, char* actual, std::size_t capacity) noexcept {
        if (findName == nullptr || requested == nullptr || actual == nullptr || capacity == 0)
            return false;
        std::size_t length = 0;
        while (length < kPathCapacity && requested[length] != '\0') ++length;
        if (length >= kPathCapacity || length + 1 > capacity ||
            std::strncmp(requested, "rom:/", 5) != 0 || length <= 5) return false;
        // Validate the whole input before any I/O, including uncached paths.
        for (std::size_t start = 5; start < length;) {
            std::size_t end = start;
            while (end < length && requested[end] != '/') ++end;
            const std::size_t count = end - start;
            if (count == 0 || (count == 1 && requested[start] == '.') ||
                (count == 2 && requested[start] == '.' && requested[start + 1] == '.') ||
                (end < length && end + 1 == length)) return false;
            start = end + 1;
        }
        for (const auto& entry : cache_) {
            if (std::strcmp(entry.requested, requested) == 0) {
                std::memcpy(actual, entry.actual, std::strlen(entry.actual) + 1);
                return true;
            }
        }
        char resolved[kPathCapacity] = "rom:/";
        std::size_t used = 5;
        for (std::size_t start = 5; start < length;) {
            std::size_t end = start;
            while (end < length && requested[end] != '/') ++end;
            char component[kPathCapacity]{};
            std::memcpy(component, requested + start, end - start);
            char name[kPathCapacity]{};
            if (!findName(context, resolved, component, end < length, name, sizeof(name)))
                return false;
            std::size_t nameLength = 0;
            while (nameLength < sizeof(name) && name[nameLength] != '\0') ++nameLength;
            if (nameLength == 0 || nameLength == sizeof(name) ||
                !EqualAsciiCase(component, name) || used + nameLength + 1 > sizeof(resolved))
                return false;
            if (used != 5) {
                if (used + nameLength + 2 > sizeof(resolved)) return false;
                resolved[used++] = '/';
            }
            std::memcpy(resolved + used, name, nameLength + 1);
            used += nameLength;
            start = end + 1;
        }
        CacheEntry& entry = cache_[next_++ % kCacheEntries];
        std::memcpy(entry.requested, requested, length + 1);
        std::memcpy(entry.actual, resolved, used + 1);
        std::memcpy(actual, resolved, used + 1);
        return true;
    }

private:
    struct CacheEntry {
        char requested[kPathCapacity]{};
        char actual[kPathCapacity]{};
    };
    CacheEntry cache_[kCacheEntries]{};
    std::size_t next_{};
};

} // namespace GameFileReader
