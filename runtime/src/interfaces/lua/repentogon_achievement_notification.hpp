#pragma once

#include <cstdint>

struct lua_State;

namespace isaac::runtime {

enum class RepentogonAchievementNotificationFailure : int {
    None,
    OverlayStart,
    ApplyCustom,
    RestoreNative,
    IdentityChangeRestore,
};

struct RepentogonAchievementNotificationDiagnostics {
    std::uint32_t startFailures{};
    std::uint32_t applyFailures{};
    std::uint32_t restoreFailures{};
    std::uint32_t identityResets{};
    int lastFailureId{};
    RepentogonAchievementNotificationFailure lastFailure{
        RepentogonAchievementNotificationFailure::None};
};

// Frame hook contract: HasPending is an O(1) in-memory check. Pump performs
// no XML/file I/O; if the native overlay is busy, the FIFO entry stays queued.
void ResetRepentogonAchievementNotifications() noexcept;
[[nodiscard]] bool HasPendingRepentogonAchievementNotifications() noexcept;
[[nodiscard]] RepentogonAchievementNotificationDiagnostics
SnapshotRepentogonAchievementNotificationDiagnostics() noexcept;
// Call only after custom achievement state has committed successfully.
[[nodiscard]] bool QueueRepentogonAchievementNotification(int achievementId);
// Direct frame-hook entry, not a Lua C closure. 1 = advanced/cleared, 0 =
// idle/busy/retry. -1 leaves exactly one Lua error at the top of the stack;
// the protected caller must invoke lua_error only after this function returns.
int PumpRepentogonAchievementNotifications(lua_State* state);

#if !defined(__SWITCH__)
struct RepentogonAchievementNotificationTestBindings {
    std::uintptr_t manager{};
    void (*showAchievement)(std::uintptr_t, int) noexcept{};
};
void SetRepentogonAchievementNotificationTestBindings(
    RepentogonAchievementNotificationTestBindings bindings) noexcept;
#endif

}  // namespace isaac::runtime
