#include "application/game/local_daily_record.hpp"

#include <algorithm>
#include <array>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <string_view>

namespace isaac::runtime::local_daily {
namespace {

constexpr std::array<std::uint8_t, 8> kMagic{
    'I', 'S', 'A', 'D', 'L', 'Y', '0', '1'};
constexpr std::size_t kVersionOffset = kMagic.size();
constexpr std::size_t kDateOffset = kVersionOffset + 2;
constexpr std::size_t kFlagsOffset = kDateOffset + 4;
constexpr std::size_t kScoreOffset = kFlagsOffset + 1;
constexpr std::size_t kChecksumOffset = kScoreOffset + kScoreBytes;
constexpr std::size_t kFileBytes = kChecksumOffset + 4;
constexpr std::uint16_t kFormatVersion = 1;
constexpr std::uint8_t kAttemptedFlag = 1u << 0;
constexpr std::uint8_t kHasScoreFlag = 1u << 1;
constexpr std::uint8_t kKnownFlags = kAttemptedFlag | kHasScoreFlag;
constexpr std::size_t kFileNameBytes = 32;

std::uint16_t ReadLe16(const std::uint8_t* bytes) noexcept {
    return static_cast<std::uint16_t>(bytes[0]) |
           static_cast<std::uint16_t>(static_cast<std::uint16_t>(bytes[1]) << 8);
}

std::uint32_t ReadLe32(const std::uint8_t* bytes) noexcept {
    return static_cast<std::uint32_t>(bytes[0]) |
           (static_cast<std::uint32_t>(bytes[1]) << 8) |
           (static_cast<std::uint32_t>(bytes[2]) << 16) |
           (static_cast<std::uint32_t>(bytes[3]) << 24);
}

void WriteLe16(std::uint8_t* bytes, std::uint16_t value) noexcept {
    bytes[0] = static_cast<std::uint8_t>(value & 0xFFu);
    bytes[1] = static_cast<std::uint8_t>((value >> 8) & 0xFFu);
}

void WriteLe32(std::uint8_t* bytes, std::uint32_t value) noexcept {
    bytes[0] = static_cast<std::uint8_t>(value & 0xFFu);
    bytes[1] = static_cast<std::uint8_t>((value >> 8) & 0xFFu);
    bytes[2] = static_cast<std::uint8_t>((value >> 16) & 0xFFu);
    bytes[3] = static_cast<std::uint8_t>((value >> 24) & 0xFFu);
}

std::uint32_t Checksum(const std::uint8_t* bytes, std::size_t size) noexcept {
    std::uint32_t crc = 0xFFFFFFFFu;
    for (std::size_t index = 0; index < size; ++index) {
        crc ^= bytes[index];
        for (unsigned bit = 0; bit < 8; ++bit) {
            const std::uint32_t mask = 0u - (crc & 1u);
            crc = (crc >> 1) ^ (0xEDB88320u & mask);
        }
    }
    return ~crc;
}

bool MakeFileName(unsigned slot, std::uint32_t date,
                  std::array<char, kFileNameBytes>* name) noexcept {
    const int written = std::snprintf(name->data(), name->size(),
                                      "local_daily_%u_%08u.bin", slot,
                                      static_cast<unsigned>(date));
    return written > 0 && static_cast<std::size_t>(written) < name->size();
}

std::array<std::uint8_t, kFileBytes> Encode(const Record& record) noexcept {
    std::array<std::uint8_t, kFileBytes> bytes{};
    std::copy(kMagic.begin(), kMagic.end(), bytes.begin());
    WriteLe16(bytes.data() + kVersionOffset, kFormatVersion);
    WriteLe32(bytes.data() + kDateOffset, record.date);
    std::uint8_t flags = 0;
    if (record.attempted) {
        flags |= kAttemptedFlag;
    }
    if (record.hasScore) {
        flags |= kHasScoreFlag;
    }
    bytes[kFlagsOffset] = flags;
    std::copy(record.score.begin(), record.score.end(), bytes.begin() + kScoreOffset);
    WriteLe32(bytes.data() + kChecksumOffset, Checksum(bytes.data(), kChecksumOffset));
    return bytes;
}

Status Decode(std::string_view bytes, std::uint32_t requestedDate, Record* out) noexcept {
    if (bytes.size() != kFileBytes) {
        return Status{StatusCode::Corrupted};
    }
    const auto* raw = reinterpret_cast<const std::uint8_t*>(bytes.data());
    if (!std::equal(kMagic.begin(), kMagic.end(), raw)) {
        return Status{StatusCode::Corrupted};
    }
    if (ReadLe16(raw + kVersionOffset) != kFormatVersion) {
        return Status{StatusCode::Corrupted};
    }
    if (ReadLe32(raw + kDateOffset) != requestedDate) {
        return Status{StatusCode::Corrupted};
    }
    const std::uint8_t flags = raw[kFlagsOffset];
    if ((flags & static_cast<std::uint8_t>(~kKnownFlags)) != 0) {
        return Status{StatusCode::Corrupted};
    }
    const bool attempted = (flags & kAttemptedFlag) != 0;
    const bool hasScore = (flags & kHasScoreFlag) != 0;
    if (hasScore && !attempted) {
        return Status{StatusCode::Corrupted};
    }
    if (ReadLe32(raw + kChecksumOffset) != Checksum(raw, kChecksumOffset)) {
        return Status{StatusCode::Corrupted};
    }

    Record decoded{};
    decoded.date = requestedDate;
    decoded.attempted = attempted;
    decoded.hasScore = hasScore;
    std::copy_n(raw + kScoreOffset, kScoreBytes, decoded.score.begin());
    *out = decoded;
    return Status::Ok();
}

} // namespace

bool ValidDate(std::uint32_t yyyymmdd) noexcept {
    const std::uint32_t year = yyyymmdd / 10000u;
    const std::uint32_t month = (yyyymmdd / 100u) % 100u;
    const std::uint32_t day = yyyymmdd % 100u;
    if (year < 2000u || year > 9999u || month < 1u || month > 12u || day < 1u) {
        return false;
    }

    constexpr std::array<std::uint32_t, 12> kDaysPerMonth{
        31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31};
    std::uint32_t limit = kDaysPerMonth[month - 1u];
    if (month == 2u && year % 4u == 0u &&
        (year % 100u != 0u || year % 400u == 0u)) {
        limit = 29;
    }
    return day <= limit;
}

Status LoadRecord(ISaveFilePort* port, unsigned slot, std::uint32_t date,
                  Record* out) noexcept {
    if (port == nullptr || out == nullptr || slot < 1 || slot > 3 || !ValidDate(date)) {
        return Status{StatusCode::InvalidArgument};
    }

    std::array<char, kFileNameBytes> name{};
    if (!MakeFileName(slot, date, &name)) {
        return Status{StatusCode::InvalidArgument};
    }
    std::array<std::uint8_t, kFileBytes> bytes{};
    std::size_t size = 0;
    const Status read = port->Read(name.data(), reinterpret_cast<char*>(bytes.data()),
                                   bytes.size(), &size);
    if (read.code() == StatusCode::NotFound) {
        Record empty{};
        empty.date = date;
        *out = empty;
        return Status::Ok();
    }
    if (!read.ok()) {
        return read;
    }

    return Decode(
        std::string_view(reinterpret_cast<const char*>(bytes.data()), size), date, out);
}

Status SaveRecord(ISaveFilePort* port, unsigned slot, const Record& record) noexcept {
    if (port == nullptr || slot < 1 || slot > 3 || !ValidDate(record.date) ||
        (record.hasScore && !record.attempted)) {
        return Status{StatusCode::InvalidArgument};
    }

    std::array<char, kFileNameBytes> name{};
    if (!MakeFileName(slot, record.date, &name)) {
        return Status{StatusCode::InvalidArgument};
    }
    const auto bytes = Encode(record);
    return port->Write(
        name.data(),
        std::string_view(reinterpret_cast<const char*>(bytes.data()), bytes.size()));
}

} // namespace isaac::runtime::local_daily
