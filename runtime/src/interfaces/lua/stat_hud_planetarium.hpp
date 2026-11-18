#pragma once

#include "infrastructure/memory/engine_field_access.hpp"

#include <algorithm>
#include <cstdint>

namespace isaac::runtime::stat_hud {

// StatHUD::Render reads player pointers at self+slot*0xD0+0x158 and the
// per-player Stat array at self+0x160+slot*0xD0. Planetarium is Stat[8].
inline constexpr std::uintptr_t kStatArrayOffset = 0x160;
inline constexpr std::uintptr_t kPlayerSlotStride = 0xd0;
inline constexpr std::uintptr_t kPlayerPointerOffset = 0x158;
inline constexpr std::uintptr_t kStatEntryStride = 0x14;
inline constexpr std::uintptr_t kPlanetariumStatIndex = 8;
inline constexpr std::uintptr_t kPlanetariumStatValueOffset =
    kPlanetariumStatIndex * kStatEntryStride;
inline constexpr std::uintptr_t kStatTimerOffset = 0x10;
inline constexpr std::uintptr_t kDualityFlagOffset = 0x2f8;
inline constexpr std::uintptr_t kRowSpacingSelectorOffset = 0x228;
inline constexpr int kPlanetariumAnimationFrame = 8;
inline constexpr int kLastPlainIconFrame = 7;
inline constexpr float kNormalRowSpacing = 12.0F;
inline constexpr float kAlternateRowSpacing = 14.0F;
static_assert(kRowSpacingSelectorOffset ==
              kPlayerPointerOffset + kPlayerSlotStride);

struct Vector2 {
    float x{};
    float y{};
};

struct NativeSpriteCalls {
    void (*setFrame)(void*, int){};
    void (*render)(void*, const void*, const void*, const void*){};
};

struct NativeCalls {
    void* game{};
    void* persistentGameData{};
    float (*planetariumChance)(void*){};
    bool (*unlocked)(void*, std::uint32_t){};
    std::uint32_t gameFrame{};
    bool gameFrameValid{};
    bool foundHud{};
    bool foundHudValid{};
};

struct FrameState {
    bool enabled{};
    float chancePercent{};
};

struct FrameCache {
    void* self{};
    void* game{};
    void* persistentGameData{};
    std::uint32_t gameFrame{};
    bool optionEnabled{};
    bool foundHud{};
    bool valid{};
    bool enabled{};
    float chancePercent{};
};

inline FrameState g_frame{};
inline FrameCache g_frameCache{};

inline bool PrepareFrame(void* self, bool optionEnabled, const NativeCalls& native) noexcept {
    g_frame = {};
    if (self == nullptr) return false;
    FrameState next{};
    bool cached = false;
    if (native.gameFrameValid) {
        cached = g_frameCache.valid && g_frameCache.self == self &&
                 g_frameCache.game == native.game &&
                 g_frameCache.persistentGameData == native.persistentGameData &&
                 g_frameCache.gameFrame == native.gameFrame &&
                 g_frameCache.optionEnabled == optionEnabled &&
                 g_frameCache.foundHud == native.foundHud;
    }
    if (cached) {
        next.enabled = g_frameCache.enabled;
        next.chancePercent = g_frameCache.chancePercent;
    } else {
        next.enabled = optionEnabled && native.foundHudValid && native.foundHud &&
                       native.persistentGameData != nullptr &&
                       native.unlocked != nullptr &&
                       native.unlocked(native.persistentGameData, 406);
        if (next.enabled && native.game != nullptr && native.planetariumChance != nullptr) {
            const float raw = native.planetariumChance(native.game);
            if (raw > 0.0F) {
                next.chancePercent = (raw >= 1.0F ? 1.0F : raw) * 100.0F;
            }
        }
        if (native.gameFrameValid) {
            g_frameCache = {self, native.game, native.persistentGameData,
                            native.gameFrame, optionEnabled, native.foundHud, true,
                            next.enabled, next.chancePercent};
        }
    }
    const auto base = engine_memory::AddressOf(self);
    if (base == 0 || base > UINTPTR_MAX -
            (kStatArrayOffset + kPlayerSlotStride + kPlanetariumStatValueOffset)) {
        return false;
    }
    for (std::uintptr_t slot = 0; slot < 2; ++slot) {
        const std::uintptr_t slotBase = base + slot * kPlayerSlotStride;
        std::uintptr_t player{};
        if (!engine_memory::ReadField(slotBase, kPlayerPointerOffset, &player,
                                      engine_memory::EngineMemoryReadable) ||
            player == 0) {
            continue;
        }
        if (!next.enabled || cached) continue;
        const std::uintptr_t statBase =
            base + kStatArrayOffset + slot * kPlayerSlotStride;
        const std::uintptr_t statValue =
            statBase + kPlanetariumStatValueOffset;
        const float noChange = 0.0F;
        std::uint32_t noTimer = 0;
        if (!engine_memory::WriteField(statValue, 0, next.chancePercent,
                                       engine_memory::EngineMemoryWritable) ||
            !engine_memory::WriteField(statValue, sizeof(float), noChange,
                                       engine_memory::EngineMemoryWritable) ||
            !engine_memory::WriteField(statValue, kStatTimerOffset, noTimer,
                                       engine_memory::EngineMemoryWritable)) {
            return false;
        }
    }
    g_frame = next;
    return true;
}

inline bool RenderNoDualityPlanetariumIcon(void* self, const void* renderOffset,
                                           const NativeSpriteCalls& native) noexcept {
    if (!g_frame.enabled || self == nullptr || renderOffset == nullptr ||
        native.setFrame == nullptr || native.render == nullptr) {
        return false;
    }
    const auto base = engine_memory::AddressOf(self);
    if (base == 0) return false;
    std::uint8_t duality = 0;
    if (!engine_memory::ReadField(base, kDualityFlagOffset, &duality,
                                  engine_memory::EngineMemoryReadable) ||
        duality != 0) {
        return false;
    }
    std::uintptr_t spacingSelector = 0;
    std::uintptr_t player = 0;
    if (!engine_memory::ReadField(base, kRowSpacingSelectorOffset, &spacingSelector,
                                  engine_memory::EngineMemoryReadable) ||
        !engine_memory::ReadField(base, kPlayerPointerOffset, &player,
                                  engine_memory::EngineMemoryReadable) ||
        (player == 0 && spacingSelector == 0)) {
        return false;
    }
    Vector2 position{};
    if (!engine_memory::ReadAt(engine_memory::AddressOf(renderOffset), &position,
                               engine_memory::EngineMemoryReadable)) {
        return false;
    }
    position.y += static_cast<float>(kPlanetariumAnimationFrame) *
                  (spacingSelector == 0 ? kNormalRowSpacing : kAlternateRowSpacing);
    constexpr Vector2 zero{};
    native.setFrame(self, kPlanetariumAnimationFrame);
    native.render(self, &position, &zero, &zero);
    native.setFrame(self, kLastPlainIconFrame);
    return true;
}

inline void RestoreFrame(void*, const FrameState&) noexcept {
    g_frame = {};
}

inline bool Enabled() noexcept {
    return g_frame.enabled;
}

constexpr std::uint32_t IconResumeIndex(bool originalTaken, bool enabled) noexcept {
    if (!originalTaken) return 0;
    return enabled ? 0U : 1U;
}

constexpr std::uint32_t TextResumeIndex(std::uint32_t compared,
                                        std::uint32_t index,
                                        bool enabled) noexcept {
    if (compared >= 2) return 0;
    if (index == 9) return 1;
    // Resume 2 is the general text path, not the index-7-only branch.
    if (index == 8) return enabled ? 2U : 1U;
    return 1;
}

}  // namespace isaac::runtime::stat_hud
