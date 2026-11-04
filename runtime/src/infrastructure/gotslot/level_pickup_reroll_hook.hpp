#pragma once

#include "ports/hook_port.hpp"

#include <array>
#include <cstdint>

namespace isaac::runtime {

Status InstallLevelPickupRerollPointerHook(HookId id, const HookTarget& target) noexcept;

namespace level_pickup_reroll {
// Unique R_AARCH64_JUMP_SLOT relocations for Game::RerollLevelPickups(unsigned)
// and Game::RerollLevelCollectibles(); their native callers use these PLT stubs.
inline constexpr std::uintptr_t kPickupsGotOffset = 0xa9f4f8;
inline constexpr std::uintptr_t kPickupsPltOffset = 0x672b20;
inline constexpr std::array<std::uint8_t, 16> kPickupsPltBytes = {
    0x70, 0x21, 0x00, 0xb0, 0x11, 0x7e, 0x42, 0xf9,
    0x10, 0xe2, 0x13, 0x91, 0x20, 0x02, 0x1f, 0xd6
};
inline constexpr std::uintptr_t kCollectiblesGotOffset = 0xa9f500;
inline constexpr std::uintptr_t kCollectiblesPltOffset = 0x672b30;
inline constexpr std::array<std::uint8_t, 16> kCollectiblesPltBytes = {
    0x70, 0x21, 0x00, 0xb0, 0x11, 0x82, 0x42, 0xf9,
    0x10, 0x02, 0x14, 0x91, 0x20, 0x02, 0x1f, 0xd6
};
} // namespace level_pickup_reroll
} // namespace isaac::runtime
