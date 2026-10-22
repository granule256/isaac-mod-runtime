#pragma once
#include "runtime_constants.hpp"
#include <cstdint>
#include <array>
namespace isaac::runtime::api100_core {
inline constexpr std::uintptr_t kBloodExplodeEntry=0x5C938;
inline constexpr std::array<std::uint8_t,16> kBloodExplodeGuard={0xff,0x83,0x04,0xd1,0xef,0x3b,0x08,0x6d,0xed,0x33,0x09,0x6d,0xeb,0x2b,0x0a,0x6d};
inline constexpr std::uintptr_t kGetLastParentEntry=0x58BE8;
inline constexpr std::array<std::uint8_t,16> kGetLastParentGuard={0xe8,0x03,0x00,0xaa,0x00,0xc8,0x41,0xf9,0xc0,0xff,0xff,0xb5,0xe0,0x03,0x08,0xaa};
inline constexpr std::uintptr_t kGetLastChildEntry=0x58BFC;
inline constexpr std::array<std::uint8_t,16> kGetLastChildGuard={0xe8,0x03,0x00,0xaa,0x00,0xcc,0x41,0xf9,0xc0,0xff,0xff,0xb5,0xe0,0x03,0x08,0xaa};
inline constexpr std::uintptr_t kHasFullHealthEntry=0x5A234;
inline constexpr std::array<std::uint8_t,16> kHasFullHealthGuard={0x00,0x54,0x43,0xbd,0x01,0x58,0x43,0xbd,0x00,0x20,0x21,0x1e,0xe0,0xb7,0x9f,0x1a};
inline constexpr std::uintptr_t kIsFrameEntry=0x5C780;
inline constexpr std::array<std::uint8_t,16> kIsFrameGuard={0xfd,0x7b,0xbd,0xa9,0xf5,0x0b,0x00,0xf9,0xfd,0x03,0x00,0x91,0xf4,0x4f,0x02,0xa9};
static_assert(kBloodExplodeEntry==::kApi100EntityBloodExplodeOffset);
static_assert(kBloodExplodeGuard==::kApi100EntityBloodExplodeExpectedBytes);
static_assert(kGetLastParentEntry==::kApi100EntityGetLastParentOffset);
static_assert(kGetLastParentGuard==::kApi100EntityGetLastParentExpectedBytes);
static_assert(kGetLastChildEntry==::kApi100EntityGetLastChildOffset);
static_assert(kGetLastChildGuard==::kApi100EntityGetLastChildExpectedBytes);
static_assert(kHasFullHealthEntry==::kApi100EntityHasFullHealthOffset);
static_assert(kHasFullHealthGuard==::kApi100EntityHasFullHealthExpectedBytes);
static_assert(kIsFrameEntry==::kApi100EntityIsFrameOffset);
static_assert(kIsFrameGuard==::kApi100EntityIsFrameExpectedBytes);
}
