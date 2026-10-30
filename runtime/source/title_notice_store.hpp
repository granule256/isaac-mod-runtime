#pragma once

#include "ports/save_file_port.hpp"
#include <cstring>

namespace isaac::runtime::notice {

inline constexpr char kSeenFile[] = "isaac-switch-notice-version.txt";

inline Status ReadSeenVersion(ISaveFilePort& files, std::string_view version,
                              bool* seen) noexcept {
    if (seen == nullptr || version.empty() || version.size() >= 63)
        return Status{StatusCode::InvalidArgument};
    *seen = false;
    char record[64]{};
    std::size_t size = 0;
    const auto status = files.Read(kSeenFile, record, sizeof(record), &size);
    if (status.code() == StatusCode::NotFound || status.code() == StatusCode::CapacityExceeded)
        return Status::Ok(); // Missing, stale or malformed records need acknowledgement.
    if (!status.ok()) return status;
    *seen = size == version.size() + 1 && size <= sizeof(record) &&
            std::memcmp(record, version.data(), version.size()) == 0 &&
            record[version.size()] == '\n';
    return Status::Ok();
}

inline Status WriteSeenVersion(ISaveFilePort& files, std::string_view version) noexcept {
    if (version.empty() || version.size() >= 63) return Status{StatusCode::InvalidArgument};
    char record[64]{};
    std::memcpy(record, version.data(), version.size());
    record[version.size()] = '\n';
    return files.Write(kSeenFile, {record, version.size() + 1});
}

} // namespace isaac::runtime::notice
