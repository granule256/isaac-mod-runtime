#pragma once

#include <array>
#include <bit>
#include <cstddef>
#include <cstdint>

namespace isaac::runtime {

// Only Lua sounds started during the game-over screen belong to this scope.
template<std::size_t MaxSounds> class GameOverSfx {
public:
    void Begin() noexcept { active_ = true; }
    [[nodiscard]] bool Active() const noexcept { return active_; }
    void Played(int id) noexcept {
        if (active_ && Valid(id)) words_[id / 64] |= Mask(id);
    }
    void Stopped(int id) noexcept {
        if (active_ && Valid(id)) words_[id / 64] &= ~Mask(id);
    }

    template<class Stop> bool End(Stop stop) {
        if (!active_) return false;
        active_ = false;
        for (std::size_t i = 0; i < words_.size(); ++i) {
            auto bits = words_[i];
            words_[i] = 0;
            while (bits) {
                stop(static_cast<int>(i * 64 + std::countr_zero(bits)));
                bits &= bits - 1;
            }
        }
        return true;
    }

private:
    static bool Valid(int id) noexcept { return id >= 0 && static_cast<std::size_t>(id) < MaxSounds; }
    static std::uint64_t Mask(int id) noexcept { return std::uint64_t{1} << (id % 64); }
    std::array<std::uint64_t, (MaxSounds + 63) / 64> words_{};
    bool active_{};
};

} // namespace isaac::runtime
