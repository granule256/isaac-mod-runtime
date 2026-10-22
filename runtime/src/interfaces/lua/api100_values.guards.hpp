#pragma once
#include <array>
#include <cstdint>
#include "runtime_constants.hpp"
namespace isaac::runtime::api100_values {
constexpr bool Equal(const std::array<std::uint8_t,16>&a,const std::array<std::uint8_t,16>&b){for(unsigned i=0;i<16;++i)if(a[i]!=b[i])return false;return true;}
inline constexpr std::uintptr_t kColorSetOffsetEntry=0x37870;
inline constexpr std::array<std::uint8_t,16> kColorSetOffsetGuard={0x00,0x20,0x00,0xBD,0x01,0x24,0x00,0xBD,0x02,0x28,0x00,0xBD,0xC0,0x03,0x5F,0xD6};
static_assert(kColorSetOffsetEntry==kApi100ColorSetOffsetOffset);
static_assert(Equal(kColorSetOffsetGuard,kApi100ColorSetOffsetExpectedBytes));
inline constexpr std::uintptr_t kColorSetTintEntry=0x37848;
inline constexpr std::array<std::uint8_t,16> kColorSetTintGuard={0x00,0x00,0x00,0xBD,0x01,0x04,0x00,0xBD,0x02,0x08,0x00,0xBD,0x03,0x0C,0x00,0xBD};
static_assert(kColorSetTintEntry==kApi100ColorSetTintOffset);
static_assert(Equal(kColorSetTintGuard,kApi100ColorSetTintExpectedBytes));
inline constexpr std::uintptr_t kColorResetEntry=0x37830;
inline constexpr std::array<std::uint8_t,16> kColorResetGuard={0xE8,0x1B,0x09,0xB2,0x08,0x20,0x00,0xA9,0x1F,0x10,0x00,0xF9,0x1F,0x28,0x00,0xB9};
static_assert(kColorResetEntry==kApi100ColorResetOffset);
static_assert(Equal(kColorResetGuard,kApi100ColorResetExpectedBytes));
inline constexpr std::uintptr_t kSpriteReloadEntry=0xCB74;
inline constexpr std::array<std::uint8_t,16> kSpriteReloadGuard={0xFD,0x7B,0xBE,0xA9,0xF4,0x4F,0x01,0xA9,0xFD,0x03,0x00,0x91,0x08,0x00,0x40,0x39};
static_assert(kSpriteReloadEntry==kApi100SpriteReloadOffset);
static_assert(Equal(kSpriteReloadGuard,kApi100SpriteReloadExpectedBytes));
inline constexpr std::uintptr_t kSpriteRemoveOverlayEntry=0xAFFC;
inline constexpr std::array<std::uint8_t,16> kSpriteRemoveOverlayGuard={0x00,0x80,0x01,0x91,0xE1,0x03,0x1F,0xAA,0x37,0x94,0x19,0x14,0xFD,0x7B,0xBE,0xA9};
static_assert(kSpriteRemoveOverlayEntry==kApi100SpriteRemoveOverlayOffset);
static_assert(Equal(kSpriteRemoveOverlayGuard,kApi100SpriteRemoveOverlayExpectedBytes));
inline constexpr std::uintptr_t kMusicManagerFadeinEntry=0x4275E4;
inline constexpr std::array<std::uint8_t,16> kMusicManagerFadeinGuard={0xE9,0x23,0xBD,0x6D,0xFD,0x7B,0x01,0xA9,0xFD,0x43,0x00,0x91,0xF3,0x13,0x00,0xF9};
static_assert(kMusicManagerFadeinEntry==kApi100MusicManagerFadeinOffset);
static_assert(Equal(kMusicManagerFadeinGuard,kApi100MusicManagerFadeinExpectedBytes));
inline constexpr std::uintptr_t kMusicManagerFadeoutEntry=0x427630;
inline constexpr std::array<std::uint8_t,16> kMusicManagerFadeoutGuard={0x08,0x00,0x80,0xB9,0x09,0x3C,0x80,0x52,0x08,0x01,0x09,0x9B,0x1F,0xD9,0x01,0xB9};
static_assert(kMusicManagerFadeoutEntry==kApi100MusicManagerFadeoutOffset);
static_assert(Equal(kMusicManagerFadeoutGuard,kApi100MusicManagerFadeoutExpectedBytes));
}
