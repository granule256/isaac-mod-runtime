#pragma once
#include <array>
#include <cstddef>
#include <cstdint>
namespace isaac::runtime {
// 固定256位逐模组状态；稳定的8个小端u32诊断布局，无堆分配。
struct ModBits {
    std::array<std::uint32_t, 8> words{};
    [[nodiscard]] bool Test(std::size_t index) const noexcept {
        return index < 256 && (words[index / 32] & (std::uint32_t{1} << (index % 32))) != 0;
    }
    bool Set(std::size_t index, bool on = true) noexcept {
        if (index >= 256) return false;
        const auto bit = std::uint32_t{1} << (index % 32);
        if (on) words[index / 32] |= bit; else words[index / 32] &= ~bit;
        return true;
    }
    [[nodiscard]] bool Empty() const noexcept {
        for (auto word : words) if (word) return false;
        return true;
    }
    [[nodiscard]] bool Contains(const ModBits& other) const noexcept {
        for (std::size_t i = 0; i < words.size(); ++i)
            if ((other.words[i] & ~words[i]) != 0) return false;
        return true;
    }
};
static_assert(sizeof(ModBits) == 32);
} // namespace isaac::runtime
