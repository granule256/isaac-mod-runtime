#pragma once
#include <cstddef>
#include <cstdint>
#include <cstring>

namespace isaac::runtime {
// 固定容量，无Lua引用和动态分配；文本指针仅选组，身份与复制内容共同判定命中。
struct FontWidthCache {
    static constexpr std::size_t kMaxText = 128;
    struct Key {
        const void* state;
        const void* owner;
        const void* font;
        std::uintptr_t method;
        std::uint64_t generation;
        bool unicode;
    };
    struct Entry {
        Key key;
        std::size_t length;
        int width;
        bool valid;
        char text[kMaxText];
    };
    Entry entries[16][4]{};
    unsigned char next[16]{};

    static std::size_t Group(const Key& key, const char* text) noexcept {
        const auto address = reinterpret_cast<std::uintptr_t>(text);
        const auto object = reinterpret_cast<std::uintptr_t>(key.font);
        return ((address >> 3) ^ (address >> 11) ^ (object >> 4)) & 15;
    }
    static bool Same(const Key& a, const Key& b) noexcept {
        return a.state == b.state && a.owner == b.owner && a.font == b.font &&
               a.method == b.method && a.generation == b.generation && a.unicode == b.unicode;
    }
    bool Find(const Key& key, const char* text, std::size_t length, int* width) const noexcept {
        if (length > kMaxText) return false;
        for (const auto& entry : entries[Group(key, text)]) {
            if (entry.valid && entry.length == length && Same(entry.key, key) &&
                std::memcmp(entry.text, text, length) == 0) {
                *width = entry.width;
                return true;
            }
        }
        return false;
    }
    void Insert(const Key& key, const char* text, std::size_t length, int width) noexcept {
        if (length > kMaxText) return;
        const auto group = Group(key, text);
        auto& entry = entries[group][next[group]];
        next[group] = (next[group] + 1) & 3;
        entry.key = key;
        entry.length = length;
        entry.width = width;
        std::memcpy(entry.text, text, length);
        entry.valid = true;
    }
    void Invalidate(const void* state, const void* owner) noexcept {
        for (auto& group : entries) for (auto& entry : group) {
            if (entry.valid && entry.key.state == state && entry.key.owner == owner)
                entry.valid = false;
        }
    }
};
} // namespace isaac::runtime
