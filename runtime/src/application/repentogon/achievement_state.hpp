#pragma once

#include "ports/save_file_port.hpp"
#include <string>
#include <unordered_set>

namespace isaac::runtime {

// Only compatibility-layer achievement state. The port owns account isolation;
// filenames select the native save slot. Numeric XML IDs are never persisted.
class AchievementState {
public:
    void Reset() noexcept;
    [[nodiscard]] Status Unlocked(ISaveFilePort*, std::string_view name,
                                  std::string_view source, bool* value) noexcept;
    [[nodiscard]] Status Unlock(ISaveFilePort*, std::string_view name,
                                std::string_view source, bool* changed) noexcept;
private:
    Status Load(ISaveFilePort*) noexcept;
    ISaveFilePort* files_{};
    unsigned slot_{};
    bool loaded_{};
    Status status_{};
    std::unordered_set<std::string> unlocked_;
};

} // namespace isaac::runtime
