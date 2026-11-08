#pragma once

#include "application/repentogon/repentogon_settings.hpp"

namespace isaac::runtime {

inline const char* RepentogonMenuLabel(const RepentogonSettings& settings,bool active) noexcept {
    if (settings.NeedsRestart()) return settings.Requested()
        ? "REPENTOGON: ON [RESTART]" : "REPENTOGON: OFF [RESTART]";
    if (!settings.Requested()) return "REPENTOGON: OFF";
    return active ? "REPENTOGON: ON" : "REPENTOGON: ON [EMPTY]";
}

} // namespace isaac::runtime
