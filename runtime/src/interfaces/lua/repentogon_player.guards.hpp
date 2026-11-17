#pragma once

#include <array>
#include <cstdint>

namespace isaac::runtime::repentogon::player {

// Original Repentance.nro build 91C73FDD575061318D68886316AFEAC72388B2AB.
// dynsym: _ZN15IsaacRepentance13Entity_Player17shoot_blue_candleERKN4KAGE4Math7Vector2E
inline constexpr std::uintptr_t kShootBlueCandleOffset = 0x2F200C;
inline constexpr std::array<std::uint8_t, 16> kShootBlueCandleGuard = {
    0xFF, 0x43, 0x03, 0xD1, 0xFD, 0x7B, 0x0A, 0xA9,
    0xFD, 0x83, 0x02, 0x91, 0xF6, 0x57, 0x0B, 0xA9,
};
// shoot_blue_candle's normal epilogue is patched to publish the spawned effect.
// Accept only the final B-to-island and the complete 12-byte island image.
inline constexpr std::uintptr_t kShootBlueCandleReturnSourceOffset = 0x2F215C;
inline constexpr std::array<std::uint8_t, 4> kShootBlueCandleReturnSourceGuard = {
    0x91, 0x6B, 0x0E, 0x14,
};
inline constexpr std::uintptr_t kShootBlueCandleReturnIslandOffset = 0x68CFA0;
inline constexpr std::array<std::uint8_t, 12> kShootBlueCandleReturnIslandGuard = {
    0xE0, 0x03, 0x14, 0xAA, 0xF4, 0x4F, 0x4C, 0xA9,
    0x6E, 0x94, 0xF1, 0x17,
};

// dynsym: _ZN15IsaacRepentance13Entity_Player17FireBrimstoneBallERKN4KAGE4Math7Vector2ES5_S5_jjPNS_6EntityE
inline constexpr std::uintptr_t kFireBrimstoneBallOffset = 0x2F7A64;
inline constexpr std::array<std::uint8_t, 16> kFireBrimstoneBallGuard = {
    0xFF, 0x03, 0x03, 0xD1, 0xFD, 0x7B, 0x07, 0xA9,
    0xFD, 0xC3, 0x01, 0x91, 0xF9, 0x43, 0x00, 0xF9,
};

// Entity_Player fields used by Lua_PlayerSetHeadDirection. NRO
// Weapon::SetHeadDirection writes the direction at +0x19FC and the libc++ string
// at +0x1698; Weapon::SetHeadLockTime writes +0x16B4. The PC layout has the
// same fields at +0x161C, +0x1320 and +0x133C respectively.
inline constexpr std::uintptr_t kHeadDirectionOffset = 0x19FC;
inline constexpr std::uintptr_t kHeadAnimOffset = 0x1698;
inline constexpr std::uintptr_t kHeadDirectionTimeOffset = 0x16B4;

}  // namespace isaac::runtime::repentogon::player
