#include "infrastructure/persistence/sd_save_file_adapter.hpp"
#include <algorithm>
#include <cstdio>
#include <cstring>

namespace isaac::runtime {
namespace {
constexpr std::size_t kPathCapacity = 400;
Status StatusFromSd(std::uint32_t rc) noexcept {
    return rc == 0 ? Status::Ok() : Status{rc == 0x202 ? StatusCode::NotFound : StatusCode::IoFailure};
}
Status RemoveIfPresent(const SdFileApi& api, const char* path) noexcept {
    const auto status = StatusFromSd(api.remove(path));
    return status.code() == StatusCode::NotFound ? Status::Ok() : status;
}
void Suffix(char* out, const char* path, const char* suffix) noexcept {
    std::snprintf(out, kPathCapacity, "%s%s", path, suffix);
}
}

alignas(0x1000) char SdSaveFileAdapter::buffer_[0x4000];

Status SdSaveFileAdapter::Configure(const SdFileApi& api, const char* root,
                                  ThreadCheck check, void* context) noexcept {
    if (!api.create || !api.open || !api.close || !api.size || !api.read || !api.write ||
        !api.flush || !api.remove || !api.rename || !root || !check) return Status{StatusCode::InvalidArgument};
    const auto n = std::strlen(root);
    if (!n || n >= sizeof(root_) || root[n - 1] != '/') return Status{StatusCode::InvalidArgument};
    std::memcpy(root_, root, n + 1); api_ = api; thread_ = check; context_ = context;
    return Status::Ok();
}

bool SdSaveFileAdapter::Path(std::string_view name, char* out, const char* suffix) const noexcept {
    if (name.empty() || name.size() > 160 || name == "." || name == "..") return false;
    // Flat names belong to the port. Reject embedded NUL and temporary suffixes
    // so a consumer cannot overwrite another file's recovery state.
    for (const auto c : name) if (c == '\0' || c == '/' || c == '\\' || c == ':' ||
                                static_cast<unsigned char>(c) < 32) return false;
    for (const auto reserved : {std::string_view{".tmp"}, std::string_view{".bak"}, std::string_view{".deleted"}})
        if (name.size() >= reserved.size() && name.substr(name.size() - reserved.size()) == reserved) return false;
    const auto n = std::strlen(root_);
    std::memcpy(out, root_, n); std::memcpy(out + n, name.data(), name.size());
    std::strcpy(out + n + name.size(), suffix);
    return true;
}

Status SdSaveFileAdapter::Recover(const char* path) noexcept {
    std::uint64_t handle{};
    auto status = StatusFromSd(api_.open(&handle, path, 1));
    if (status.ok()) { api_.close(handle); return status; }
    if (status.code() != StatusCode::NotFound) return status;
    char backup[kPathCapacity]{}; Suffix(backup, path, ".bak");
    status = StatusFromSd(api_.rename(backup, path));
    return status;
}

Status SdSaveFileAdapter::Size(const char* path, std::size_t* size) noexcept {
    *size = 0;
    const auto recovered = Recover(path);
    if (!recovered.ok()) return recovered;
    std::uint64_t handle{};
    auto status = StatusFromSd(api_.open(&handle, path, 1));
    if (!status.ok()) return status;
    std::int64_t length{}; status = StatusFromSd(api_.size(&length, handle)); api_.close(handle);
    if (!status.ok()) return status;
    if (length < 0 || static_cast<std::uint64_t>(length) > SIZE_MAX) return Status{StatusCode::Corrupted};
    *size = static_cast<std::size_t>(length); return Status::Ok();
}

Status SdSaveFileAdapter::ReadPath(const char* path, char* out, std::size_t capacity, std::size_t* size) noexcept {
    auto status = Size(path, size);
    if (!status.ok()) return status;
    if (*size > capacity) return Status{StatusCode::CapacityExceeded};
    const auto length = *size; *size = 0;
    std::uint64_t handle{}; status = StatusFromSd(api_.open(&handle, path, 1));
    if (!status.ok()) return status;
    for (std::size_t offset = 0; status.ok() && offset < length;) {
        const auto chunk = std::min(sizeof(buffer_), length - offset);
        std::uint64_t read{}; status = StatusFromSd(api_.read(&read, handle, offset, buffer_, chunk));
        if (status.ok() && (!read || read > chunk)) status = Status{StatusCode::IoFailure};
        if (!status.ok()) break;
        std::memcpy(out + offset, buffer_, read); offset += read;
    }
    api_.close(handle);
    if (status.ok()) *size = length;
    return status;
}

Status SdSaveFileAdapter::WritePath(const char* path, std::string_view data) noexcept {
    if (data.size() > INT64_MAX) return Status{StatusCode::CapacityExceeded};
    const auto recovered = Recover(path);
    if (!recovered.ok() && recovered.code() != StatusCode::NotFound) return recovered;
    char temporary[kPathCapacity]{}, backup[kPathCapacity]{};
    Suffix(temporary, path, ".tmp"); Suffix(backup, path, ".bak");
    auto status = RemoveIfPresent(api_, temporary);
    if (!status.ok()) return status;
    status = StatusFromSd(api_.create(temporary, data.size(), 0));
    if (!status.ok()) return status;
    std::uint64_t handle{}; status = StatusFromSd(api_.open(&handle, temporary, 2));
    if (!status.ok()) return status;
    const std::uint32_t option = 0;
    for (std::size_t offset = 0; status.ok() && offset < data.size();) {
        const auto chunk = std::min(sizeof(buffer_), data.size() - offset);
        std::memcpy(buffer_, data.data() + offset, chunk);
        status = StatusFromSd(api_.write(handle, offset, buffer_, chunk, &option)); offset += chunk;
    }
    if (status.ok()) status = StatusFromSd(api_.flush(handle));
    api_.close(handle);
    if (!status.ok()) return status;
    status = RemoveIfPresent(api_, backup);
    if (!status.ok()) return status;
    if (recovered.ok()) {
        status = StatusFromSd(api_.rename(path, backup));
        if (!status.ok()) return status;
    }
    status = StatusFromSd(api_.rename(temporary, path));
    if (!status.ok()) return status; // The old file remains recoverable in .bak.
    return RemoveIfPresent(api_, backup);
}

Status SdSaveFileAdapter::Deleted(std::string_view name, bool* deleted) noexcept {
    char path[kPathCapacity]{};
    if (!Path(name, path, ".deleted")) return Status{StatusCode::InvalidArgument};
    std::size_t size{}; const auto status = Size(path, &size);
    *deleted = status.ok();
    return status.code() == StatusCode::NotFound ? Status::Ok() : status;
}

Status SdSaveFileAdapter::Read(std::string_view name, char* out, std::size_t capacity, std::size_t* size) noexcept {
    if (!out || !size) return Status{StatusCode::InvalidArgument};
    *size = 0;
    if (!Allowed()) return Status{StatusCode::Unsupported};
    bool deleted{}; auto status = Deleted(name, &deleted);
    if (!status.ok() || deleted) return deleted ? Status{StatusCode::NotFound} : status;
    char path[kPathCapacity]{};
    if (!Path(name, path)) return Status{StatusCode::InvalidArgument};
    status = ReadPath(path, out, capacity, size);
    if (status.code() != StatusCode::NotFound) return status;
    status = legacy_.Read(name, out, capacity, size);
    if (!status.ok()) return status;
    // Returning success only after the unchanged bytes are durable on SD keeps
    // migration failure visible to the caller and preserves the legacy original.
    return WritePath(path, std::string_view(out, *size));
}

Status SdSaveFileAdapter::GetSize(std::string_view name, std::size_t* size) noexcept {
    if (!size) return Status{StatusCode::InvalidArgument};
    *size = 0;
    if (!Allowed()) return Status{StatusCode::Unsupported};
    bool deleted{}; auto status = Deleted(name, &deleted);
    if (!status.ok() || deleted) return deleted ? Status{StatusCode::NotFound} : status;
    char path[kPathCapacity]{};
    if (!Path(name, path)) return Status{StatusCode::InvalidArgument};
    status = Size(path, size);
    return status.code() == StatusCode::NotFound ? legacy_.GetSize(name, size) : status;
}

Status SdSaveFileAdapter::GetSaveSlot(unsigned* slot) noexcept {
    if (!Allowed()) return Status{StatusCode::Unsupported};
    return legacy_.GetSaveSlot(slot);
}

Status SdSaveFileAdapter::Write(std::string_view name, std::string_view data) noexcept {
    if (!Allowed()) return Status{StatusCode::Unsupported};
    char path[kPathCapacity]{};
    if (!Path(name, path)) return Status{StatusCode::InvalidArgument};
    auto status = WritePath(path, data);
    if (!status.ok()) return status;
    Path(name, path, ".deleted");
    char backup[kPathCapacity]{}; Suffix(backup, path, ".bak");
    status = RemoveIfPresent(api_, backup);
    if (!status.ok()) return status;
    return RemoveIfPresent(api_, path);
}

Status SdSaveFileAdapter::Remove(std::string_view name) noexcept {
    if (!Allowed()) return Status{StatusCode::Unsupported};
    char path[kPathCapacity]{};
    if (!Path(name, path, ".deleted")) return Status{StatusCode::InvalidArgument};
    auto status = WritePath(path, "");
    if (!status.ok()) return status;
    Path(name, path); status = RemoveIfPresent(api_, path);
    if (!status.ok()) return status;
    char backup[kPathCapacity]{}; Suffix(backup, path, ".bak");
    return RemoveIfPresent(api_, backup);
}

Status SdSaveFileAdapter::Exists(const char* path, bool* exists) noexcept {
    if (!Allowed()) return Status{StatusCode::Unsupported};
    return legacy_.Exists(path, exists);
}

} // namespace isaac::runtime
