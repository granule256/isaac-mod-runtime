#include "application/repentogon/repentogon_settings.hpp"

namespace isaac::runtime {
namespace {
constexpr std::string_view kOff = "isaac-repentogon 1\nenabled 0\n";
constexpr std::string_view kOn = "isaac-repentogon 1\nenabled 1\n";
}

Status RepentogonSettings::LoadOnce(ISaveFilePort* files) noexcept {
    if (loaded_) return loadStatus_;
    if (!files) return loadStatus_ = Status{StatusCode::Unsupported};
    char buffer[64]{};
    std::size_t size{};
    loadStatus_ = files->Read(kRepentogonSettingsFile, buffer, sizeof(buffer), &size);
    // The first Lua VM can be created before the session save port is
    // published. An unavailable port is transient, so it must not freeze the
    // startup snapshot at OFF for the rest of the game process.
    if (loadStatus_.code() == StatusCode::Unsupported) return loadStatus_;
    loaded_ = true;
    if (loadStatus_.code() == StatusCode::NotFound) return loadStatus_ = Status::Ok();
    if (!loadStatus_.ok()) return loadStatus_;
    if (size > sizeof(buffer)) return loadStatus_ = Status{StatusCode::Corrupted};
    const std::string_view value{buffer, size};
    if (value != kOn && value != kOff) return loadStatus_ = Status{StatusCode::Corrupted};
    startup_ = requested_ = value == kOn;
    return Status::Ok();
}

Status RepentogonSettings::SetEnabled(ISaveFilePort* files, bool enabled) noexcept {
    if (!loaded_) return Status{StatusCode::InvalidState};
    if (!files) return Status{StatusCode::Unsupported};
    const Status saved = files->Write(kRepentogonSettingsFile, enabled ? kOn : kOff);
    if (saved.ok()) requested_ = enabled;
    return saved;
}

} // namespace isaac::runtime
