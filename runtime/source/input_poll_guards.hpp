#pragma once

#include <array>
#include <cstdint>

namespace isaac::runtime::input_poll {
// KAGE::Input::Manager::Poll(), its PLT stub, and the stub's pointer slot.
inline constexpr std::uintptr_t kPollOffset = 0x4FBAE8;
inline constexpr std::array<std::uint8_t, 16> kPollBytes = {
    0xFD, 0x7B, 0xBC, 0xA9, 0xF7, 0x0B, 0x00, 0xF9,
    0xFD, 0x03, 0x00, 0x91, 0xF6, 0x57, 0x02, 0xA9,
};
inline constexpr std::uintptr_t kPltOffset = 0x67ABF0;
inline constexpr std::array<std::uint8_t, 16> kPltBytes = {
    0x50, 0x21, 0x00, 0xB0, 0x11, 0xB2, 0x42, 0xF9,
    0x10, 0x82, 0x15, 0x91, 0x20, 0x02, 0x1F, 0xD6,
};
inline constexpr std::uintptr_t kGotOffset = 0xAA3560;
} // namespace isaac::runtime::input_poll
