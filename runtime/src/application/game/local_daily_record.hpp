#pragma once

#include "ports/save_file_port.hpp"

#include <array>
#include <cstddef>
#include <cstdint>

namespace isaac::runtime::local_daily {

inline constexpr std::size_t kScoreBytes = 0x140;

struct Record {
    std::uint32_t date{};
    bool attempted{};
    bool hasScore{};
    std::array<std::uint8_t, kScoreBytes> score{};
};

[[nodiscard]] bool ValidDate(std::uint32_t yyyymmdd) noexcept;

[[nodiscard]] Status LoadRecord(ISaveFilePort* port, unsigned slot, std::uint32_t date,
                                Record* out) noexcept;

[[nodiscard]] Status SaveRecord(ISaveFilePort* port, unsigned slot,
                                const Record& record) noexcept;

} // namespace isaac::runtime::local_daily
