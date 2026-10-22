#pragma once
#include "runtime_constants.hpp"
#include <cstdint>
#include <array>
namespace isaac::runtime::api100_strings {
inline constexpr std::uintptr_t kGetCurseNameEntry=0x3E3FA8;
inline constexpr std::array<std::uint8_t,16> kGetCurseNameGuard={0xff,0x03,0x02,0xd1,0xfd,0x7b,0x03,0xa9,0xfd,0xc3,0x00,0x91,0xfa,0x67,0x04,0xa9};
inline constexpr std::uintptr_t kGetNameEntry=0x3E3DC8;
inline constexpr std::array<std::uint8_t,16> kGetNameGuard={0xfd,0x7b,0xbc,0xa9,0xf7,0x0b,0x00,0xf9,0xfd,0x03,0x00,0x91,0xf6,0x57,0x02,0xa9};
static_assert(kGetCurseNameEntry==::kApi100LevelGetCurseNameOffset);
static_assert(kGetCurseNameGuard==::kApi100LevelGetCurseNameExpectedBytes);
static_assert(kGetNameEntry==::kApi100LevelGetNameOffset);
static_assert(kGetNameGuard==::kApi100LevelGetNameExpectedBytes);
}
