#include "application/repentogon/achievement_state.hpp"
#include <cstdio>
#include <cstring>
#include <memory>
#include <new>

namespace isaac::runtime {
namespace {
constexpr std::string_view kHeader = "ISACH1\n";
constexpr std::size_t kMaximumBytes = 1024U * 1024U;
std::string Key(std::string_view name, std::string_view source) {
    std::string key(name);
    key.push_back('\0');
    key.append(source);
    return key;
}
void FileName(unsigned slot, char (&out)[48]) noexcept {
    std::snprintf(out, sizeof(out), "repentogon-achievements-%u.dat", slot);
}
void AppendRecord(std::string& out, const std::string& key) {
    const auto size = static_cast<std::uint32_t>(key.size());
    for (unsigned shift = 0; shift < 32; shift += 8) out.push_back(static_cast<char>(size >> shift));
    out.append(key);
}
}

void AchievementState::Reset() noexcept {
    files_ = nullptr;
    slot_ = 0;
    loaded_ = false;
    status_ = Status::Ok();
    unlocked_.clear();
}

Status AchievementState::Load(ISaveFilePort* files) noexcept {
    if (!files) return Status{StatusCode::Unsupported};
    unsigned slot{};
    auto result = files->GetSaveSlot(&slot);
    if (!result.ok()) return result;
    if (slot > 3) return Status{StatusCode::InvalidState};
    if (slot == 0) slot = 1; // Upstream also uses slot 1 before selection.
    if (loaded_ && files_ == files && slot_ == slot) return status_;
    Reset();
    files_ = files;
    slot_ = slot;
    loaded_ = true;
    char file[48]{};
    FileName(slot_, file);
    std::size_t capacity{};
    status_ = files->GetSize(file, &capacity);
    if (status_.code() == StatusCode::NotFound) return status_ = Status::Ok();
    if (status_.code() == StatusCode::Unsupported) capacity = kMaximumBytes;
    else if (!status_.ok()) return status_;
    if (capacity > kMaximumBytes) return status_ = Status{StatusCode::CapacityExceeded};
    if (capacity < kHeader.size()) return status_ = Status{StatusCode::Corrupted};
    // Production supplies the exact length, so missing or small files do not
    // allocate the full bound. Older read-only ports use the bounded fallback.
    std::unique_ptr<char[]> buffer(new (std::nothrow) char[capacity]);
    if (!buffer) return status_ = Status{StatusCode::CapacityExceeded};
    std::size_t size{};
    status_ = files->Read(file, buffer.get(), capacity, &size);
    if (status_.code() == StatusCode::NotFound) return status_ = Status::Ok();
    if (!status_.ok()) return status_;
    if (size > capacity || size < kHeader.size() ||
        std::memcmp(buffer.get(), kHeader.data(), kHeader.size()) != 0)
        return status_ = Status{StatusCode::Corrupted};
    std::unordered_set<std::string> parsed;
    for (std::size_t offset = kHeader.size(); offset < size;) {
        if (size - offset < 4) return status_ = Status{StatusCode::Corrupted};
        std::uint32_t length{};
        for (unsigned shift = 0; shift < 32; shift += 8)
            length |= static_cast<std::uint32_t>(static_cast<unsigned char>(buffer[offset++])) << shift;
        if (length < 3 || length > size - offset) return status_ = Status{StatusCode::Corrupted};
        std::string key(buffer.get() + offset, length);
        const auto separator = key.find('\0');
        if (separator == 0 || separator == std::string::npos || separator + 1 == key.size() ||
            key.find('\0', separator + 1) != std::string::npos || !parsed.insert(key).second)
            return status_ = Status{StatusCode::Corrupted};
        offset += length;
    }
    unlocked_ = std::move(parsed);
    return status_;
}

Status AchievementState::Unlocked(ISaveFilePort* files, std::string_view name,
                                  std::string_view source, bool* value) noexcept {
    if (!value || name.empty() || source.empty() || name.find('\0') != name.npos ||
        source.find('\0') != source.npos) return Status{StatusCode::InvalidArgument};
    *value = false;
    const auto result = Load(files);
    if (result.ok()) *value = unlocked_.find(Key(name, source)) != unlocked_.end();
    return result;
}

Status AchievementState::Unlock(ISaveFilePort* files, std::string_view name,
                                std::string_view source, bool* changed) noexcept {
    if (!changed) return Status{StatusCode::InvalidArgument};
    *changed = false;
    bool present{};
    const auto result = Unlocked(files, name, source, &present);
    if (!result.ok() || present) return result;
    const auto key = Key(name, source);
    std::string bytes(kHeader);
    for (const auto& entry : unlocked_) {
        if (entry.size() + 4 > kMaximumBytes - bytes.size()) return Status{StatusCode::CapacityExceeded};
        AppendRecord(bytes, entry);
    }
    if (key.size() + 4 > kMaximumBytes - bytes.size()) return Status{StatusCode::CapacityExceeded};
    AppendRecord(bytes, key);
    char file[48]{};
    FileName(slot_, file);
    const auto saved = files->Write(file, bytes);
    if (!saved.ok()) return saved;
    unlocked_.insert(key);
    *changed = true;
    return Status::Ok();
}

} // namespace isaac::runtime
