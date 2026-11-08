#pragma once

#include "ports/save_file_port.hpp"

namespace isaac::runtime {

inline constexpr char kRepentogonSettingsFile[] = "isaac-repentogon-state.txt";

// Desired configuration is persisted independently of installed Mod directories.
// The startup snapshot survives Lua reloads; changing it requires a game restart.
class RepentogonSettings {
public:
    [[nodiscard]] Status LoadOnce(ISaveFilePort* files) noexcept;
    [[nodiscard]] Status SetEnabled(ISaveFilePort* files, bool enabled) noexcept;
    [[nodiscard]] bool Requested() const noexcept { return requested_; }
    [[nodiscard]] bool StartupEnabled() const noexcept { return startup_; }
    [[nodiscard]] bool NeedsRestart() const noexcept { return requested_ != startup_; }
    [[nodiscard]] Status LoadStatus() const noexcept { return loadStatus_; }

private:
    bool loaded_{};
    bool requested_{};
    bool startup_{};
    Status loadStatus_{};
};

// Access only on the game thread, after the session save port is available.
inline RepentogonSettings g_RepentogonSettings{};

} // namespace isaac::runtime
