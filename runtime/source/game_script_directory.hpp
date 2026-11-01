#pragma once

#include "script_path_resolver.hpp"

#include <cstddef>
#include <cstdint>
#include <cstring>

namespace GameFileReader {

// Calls the game's existing nn::fs imports, without creating an fs session or
// using ContentManager::get_directory_entries (which aborts on a missing path).
struct GameScriptDirectory {
    struct Entry {
        char name[0x301];
        std::uint8_t padding[3];
        std::uint8_t type;
        std::uint8_t padding2[3];
        std::int64_t fileSize;
    };
    static_assert(offsetof(Entry, type) == 0x304);
    static_assert(offsetof(Entry, fileSize) == 0x308);
    static_assert(sizeof(Entry) == 0x310);

    using OpenFn = std::uint32_t (*)(std::uint64_t*, const char*, int);
    using ReadFn = std::uint32_t (*)(std::int64_t*, Entry*, std::uint64_t, std::int64_t);
    using CloseFn = void (*)(std::uint64_t);
    OpenFn open{nullptr};
    ReadFn read{nullptr};
    CloseFn close{nullptr};

    bool FindName(const char* parent, const char* requested, bool directory,
                  char* actual, std::size_t capacity) const noexcept {
        if (open == nullptr || read == nullptr || close == nullptr || parent == nullptr ||
            requested == nullptr || actual == nullptr || capacity == 0) return false;
        std::uint64_t handle{};
        // Filtering in the SDK avoids relying on an entry's type field.
        if (open(&handle, parent, directory ? 1 : 2) != 0) return false;
        char candidate[sizeof(Entry::name)]{};
        bool found = false;
        bool valid = true;
        constexpr std::int64_t kBatchEntries = 8;
        Entry entries[kBatchEntries]{};
        for (;;) {
            std::int64_t count{};
            if (read(&count, entries, handle, kBatchEntries) != 0 ||
                count < 0 || count > kBatchEntries) {
                valid = false;
                break;
            }
            if (count == 0) break;
            bool exact = false;
            for (std::int64_t index = 0; index < count; ++index) {
                const auto& name = entries[index].name;
                std::size_t length = 0;
                while (length < sizeof(name) && name[length] != '\0') ++length;
                if (length == sizeof(name) || length + 1 > capacity ||
                    !ScriptPathResolver::EqualAsciiCase(requested, name)) continue;
                exact = std::strcmp(requested, name) == 0;
                if (!found || exact) {
                    std::memcpy(candidate, name, length + 1);
                    found = true;
                }
                if (exact) break;
            }
            if (exact) break;
        }
        close(handle);
        if (!valid || !found) return false;
        std::memcpy(actual, candidate, std::strlen(candidate) + 1);
        return true;
    }

    static bool Find(void* context, const char* parent, const char* requested,
                     bool directory, char* actual, std::size_t capacity) noexcept {
        return context != nullptr && static_cast<const GameScriptDirectory*>(context)->FindName(
            parent, requested, directory, actual, capacity);
    }
};

} // namespace GameFileReader
