#pragma once

#include <array>
#include <cstddef>
#include <cstdint>
#include <cstring>

namespace isaac::runtime::player_damage_boundary {

inline constexpr std::array<std::uint8_t, 32> kBuildId = {
    0x91,0xC7,0x3F,0xDD,0x57,0x50,0x61,0x31,0x8D,0x68,0x88,0x63,0x16,0xAF,0xEA,0xC7,
    0x23,0x88,0xB2,0xAB,0,0,0,0,0,0,0,0,0,0,0,0};
// Fixed NRO dynamic symbol: Entity_Player::TakeDamage, size 0x6208.
inline constexpr std::uintptr_t kFunction = 0x2A34D0, kLength = 0x6208;
inline constexpr std::uint64_t kFunctionHash = 0xAB7104CCC3D1B99DULL;
inline constexpr std::uintptr_t kSource = 0x2A4B00, kAllow = 0x2A4B04, kCancel = 0x2A35E4;
inline constexpr std::uint32_t kOriginal = 0x940F4EB4U;
inline constexpr std::uintptr_t kAstralPlt = 0x6785D0;
inline constexpr std::array<std::uint8_t, 16> kAstralPltGuard = {
    0x50,0x21,0x00,0xD0,0x11,0x2A,0x41,0xF9,0x10,0x42,0x09,0x91,0x20,0x02,0x1F,0xD6};
// ProjectileInit owns CE20..CE48; the legacy PreGetCollectible slot starts CE58.
inline constexpr std::uintptr_t kVeneer = 0x68CE48;

inline bool ImageMatches(const std::uint8_t* image, std::size_t size) noexcept {
    if (image == nullptr || size < kVeneer + 16 || size < kFunction + kLength ||
        size < kAstralPlt + kAstralPltGuard.size() ||
        std::memcmp(image + 0x40, kBuildId.data(), kBuildId.size()) != 0 ||
        std::memcmp(image + kAstralPlt, kAstralPltGuard.data(), kAstralPltGuard.size()) != 0)
        return false;
    const std::array<std::uint8_t, 16> empty{};
    if (std::memcmp(image + kVeneer, empty.data(), empty.size()) != 0) return false;
    std::uint64_t hash = 14695981039346656037ULL;
    for (std::size_t i = 0; i < kLength; ++i)
        hash = (hash ^ image[kFunction + i]) * 1099511628211ULL;
    return hash == kFunctionHash;
}

// PC 73DBA1 dispatches callback 11 immediately before try_end_astral_projection.
// The NS counterpart is this BL, after native invincibility/cooldown/shield gates.
// x16 is dead on both resumes: the replaced PLT call overwrites x16 before use;
// 2A4B04 tests w0 then reloads/cmp's player type, and 2A35E4 enters the epilogue.

} // namespace isaac::runtime::player_damage_boundary
