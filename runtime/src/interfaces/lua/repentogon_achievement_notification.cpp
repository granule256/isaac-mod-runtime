#include "interfaces/lua/repentogon_achievement_notification.hpp"

#include "infrastructure/call/engine_call_access.hpp"
#include "infrastructure/memory/engine_field_access.hpp"
#include "interfaces/lua/engine_method_lookup.hpp"
#include "interfaces/lua/repentogon_callbacks.hpp"
#include "interfaces/lua/sprite_api.hpp"
#include "lua_runtime.hpp"
#include "ports/save_file_port.hpp"
#include "program/xml_data_store.hpp"
#include "runtime_constants.hpp"

#include <algorithm>
#include <array>
#include <cstdint>
#include <cstdio>
#include <deque>
#include <string>
#include <string_view>
#include <utility>

extern "C" {
#include <lauxlib.h>
}

namespace isaac::runtime {
namespace {
// NS build 91C73FDD...: Manager::ShowAchievement reads manager+0x36509
// (popup enabled), forwards manager+0x2d338 to AchievementOverlay::Show, and
// Show enqueues then immediately calls Update. A zero state with an empty
// native deque is therefore the only safe point to start the dummy notification.
// Show/Update use deque size +0x28, displayed id +0x30, state +0x38, ANM2 +0x40.
#if defined(__SWITCH__)
constexpr std::uintptr_t kManagerShowAchievementOffset = 0x3FA150;
#endif
constexpr std::uintptr_t kManagerPopupEnabledOffset = 0x36509;
constexpr std::uintptr_t kManagerAchievementOverlayOffset = 0x2D338;
constexpr std::uintptr_t kAchievementOverlayQueueSizeOffset = 0x28;
constexpr std::uintptr_t kAchievementOverlayDisplayedIdOffset = 0x30;
constexpr std::uintptr_t kAchievementOverlayStateOffset = 0x38;
constexpr std::uintptr_t kAchievementOverlaySpriteOffset = 0x40;
constexpr int kDummyAchievementId = 2;
constexpr char kDefaultBackground[] = "gfx/ui/achievement/Paper.png";
constexpr char kNativeLockedLayer[] = "gfx/ui/achievement/achievement_locked.png";

#if defined(__SWITCH__)
constexpr std::array<std::uint8_t, 16> kShowAchievementGuard = {
    0x28, 0xA1, 0x8C, 0x52, 0x68, 0x00, 0xA0, 0x72,
    0x08, 0x68, 0x68, 0x38, 0xA8, 0x00, 0x00, 0x34,
};
#endif

struct NotificationIdentity {
    ISaveFilePort* port{};
    unsigned slot{};
};

struct PendingNotification {
    NotificationIdentity identity{};
    int id{};
    std::string gfx;
    std::string background;
};

struct ActiveNotification {
    NotificationIdentity identity{};
    int id{};
    bool restorePending{};
};

struct NotificationState {
    std::deque<PendingNotification> pending;
    ActiveNotification active;
    std::uintptr_t manager{};
    RepentogonAchievementNotificationDiagnostics diagnostics;
};

NotificationState g_Notifications;

#if !defined(__SWITCH__)
RepentogonAchievementNotificationTestBindings g_TestBindings{};
#endif

bool SameIdentity(const NotificationIdentity& left,
                  const NotificationIdentity& right) noexcept {
    return left.port == right.port && left.slot == right.slot;
}

bool CurrentIdentity(NotificationIdentity* identity) noexcept {
    auto* port = SessionSaveFilePort();
    if (port == nullptr) return false;
    unsigned slot = 0;
    const auto status = port->GetSaveSlot(&slot);
    if (!status.ok()) return false;
    if (slot == 0) slot = 1;
    if (slot > 3) return false;
    identity->port = port;
    identity->slot = slot;
    return true;
}

const xml_data::XmlAttribute* Attribute(const xml_data::XmlRecord& record,
                                        const char* name) noexcept {
    return record.FindAttribute(name);
}

std::string Path(const xml_data::XmlRecord& record, const xml_data::XmlAttribute& leaf) {
    const auto* root = Attribute(record, "gfxroot");
    std::string result(root ? root->value : "");
    result.append(leaf.value);
    return result;
}

bool Visible(const xml_data::XmlRecord& record) noexcept {
    const auto* hidden = Attribute(record, "hidden");
    return hidden == nullptr || hidden->value == "false";
}

std::uintptr_t ResolveManager() noexcept {
#if !defined(__SWITCH__)
    if (g_TestBindings.manager != 0) return g_TestBindings.manager;
#endif
    const auto base = LuaRuntime::EngineModuleBase();
    if (base == 0) return 0;
    std::uintptr_t slot = 0;
    if (!engine_memory::ReadField(base, kGameManagerGlobalSlotOffset, &slot,
                                  engine_memory::EngineMemoryReadable) ||
        slot == 0) {
        return 0;
    }
    std::uintptr_t manager = 0;
    if (!engine_memory::ReadField(slot, 0, &manager,
                                  engine_memory::EngineMemoryReadable)) {
        return 0;
    }
    return manager;
}

std::uintptr_t Overlay(std::uintptr_t manager) noexcept {
    if (manager == 0 || manager > UINTPTR_MAX - kManagerAchievementOverlayOffset) return 0;
    const auto overlay = manager + kManagerAchievementOverlayOffset;
    if (!engine_memory::EngineMemoryReadable(
            overlay, kAchievementOverlaySpriteOffset + kSpriteObjectSize)) {
        return 0;
    }
    return overlay;
}

bool ShowDummyAchievement(std::uintptr_t manager) noexcept {
#if !defined(__SWITCH__)
    if (g_TestBindings.showAchievement != nullptr) {
        g_TestBindings.showAchievement(manager, kDummyAchievementId);
        return true;
    }
    return false;
#else
    const auto method = EngineOffsetAddress<engine_memory::EngineMemoryReadable>(
        kManagerShowAchievementOffset);
    if (method == 0 ||
        !engine_call::VerifyEntryBytes(method, kShowAchievementGuard.data(),
                                       kShowAchievementGuard.size(),
                                       &engine_memory::EngineMemoryReadable)) {
        return false;
    }
    engine_call::AsFunction<void (*)(std::uintptr_t, int)>(method)(
        manager, kDummyAchievementId);
    return true;
#endif
}

bool ReadOverlayState(std::uintptr_t overlay, std::int32_t* state,
                      std::uint64_t* queueSize, std::int32_t* displayedId) noexcept {
    return engine_memory::ReadField(overlay, kAchievementOverlayStateOffset, state,
                                    engine_memory::EngineMemoryReadable) &&
           engine_memory::ReadField(overlay, kAchievementOverlayQueueSizeOffset, queueSize,
                                    engine_memory::EngineMemoryReadable) &&
           engine_memory::ReadField(overlay, kAchievementOverlayDisplayedIdOffset, displayedId,
                                    engine_memory::EngineMemoryReadable);
}

bool PopupEnabled(std::uintptr_t manager, bool* enabled) noexcept {
    std::uint8_t value = 0;
    if (!engine_memory::ReadField(manager, kManagerPopupEnabledOffset, &value,
                                  engine_memory::EngineMemoryReadable)) {
        return false;
    }
    *enabled = value != 0;
    return true;
}

void SetError(char* error, std::size_t capacity, const char* text) noexcept {
    if (error == nullptr || capacity == 0) return;
    std::snprintf(error, capacity, "%s", text != nullptr ? text : "unknown failure");
}

void CopyLuaError(lua_State* state, char* error, std::size_t capacity,
                  const char* fallback) noexcept {
    const char* text = lua_type(state, -1) == LUA_TSTRING ? lua_tostring(state, -1) : nullptr;
    SetError(error, capacity, text != nullptr ? text : fallback);
    lua_pop(state, 1);
}

bool PushOverlaySprite(lua_State* state, std::uintptr_t overlay, int* spriteIndex,
                       char* error, std::size_t errorCapacity) noexcept {
    const auto sprite = overlay + kAchievementOverlaySpriteOffset;
    if (!repentogon::HasSpriteValidator() || !repentogon::CallbackSpriteAlive(sprite)) {
        SetError(error, errorCapacity, "interaction sprite lifetime is unavailable");
        return false;
    }
    if (!lua_checkstack(state, 12)) {
        SetError(error, errorCapacity, "Lua stack cannot hold the interaction sprite");
        return false;
    }
    PushCallbackSpriteHandle(state, sprite, LUA_NOREF);
    if (lua_isnil(state, -1)) {
        lua_pop(state, 1);
        SetError(error, errorCapacity, "interaction sprite handle is unavailable");
        return false;
    }
    *spriteIndex = lua_gettop(state);
    return true;
}

bool ReplaceSpritesheet(lua_State* state, int sprite, int layer,
                        std::string_view path, char* error,
                        std::size_t errorCapacity) noexcept {
    if (!lua_checkstack(state, 5)) {
        SetError(error, errorCapacity, "Lua stack cannot hold ReplaceSpritesheet");
        return false;
    }
    lua_getfield(state, sprite, "ReplaceSpritesheet");
    if (!lua_isfunction(state, -1)) {
        lua_pop(state, 1);
        SetError(error, errorCapacity, "ReplaceSpritesheet is unavailable");
        return false;
    }
    lua_pushvalue(state, sprite);
    lua_pushinteger(state, layer);
    lua_pushlstring(state, path.data(), path.size());
    if (lua_pcall(state, 3, 0, 0) == LUA_OK) return true;
    CopyLuaError(state, error, errorCapacity, "ReplaceSpritesheet failed");
    return false;
}

bool CallSpriteVoid(lua_State* state, int sprite, const char* method,
                    char* error, std::size_t errorCapacity) noexcept {
    if (!lua_checkstack(state, 3)) {
        SetError(error, errorCapacity, "Lua stack cannot hold the Sprite method");
        return false;
    }
    lua_getfield(state, sprite, method);
    if (!lua_isfunction(state, -1)) {
        lua_pop(state, 1);
        SetError(error, errorCapacity, method);
        return false;
    }
    lua_pushvalue(state, sprite);
    if (lua_pcall(state, 1, 0, 0) == LUA_OK) return true;
    CopyLuaError(state, error, errorCapacity, method);
    return false;
}

bool ApplyCustomSprites(lua_State* state, int sprite,
                        const PendingNotification& notification,
                        char* error, std::size_t errorCapacity) noexcept {
    return ReplaceSpritesheet(state, sprite, 2, notification.background,
                              error, errorCapacity) &&
           ReplaceSpritesheet(state, sprite, 3, notification.gfx,
                              error, errorCapacity) &&
           CallSpriteVoid(state, sprite, "LoadGraphics", error, errorCapacity) &&
           CallSpriteVoid(state, sprite, "Update", error, errorCapacity);
}

bool RestoreNativeSprites(lua_State* state, int sprite,
                          char* error, std::size_t errorCapacity) noexcept {
    return ReplaceSpritesheet(state, sprite, 2, kDefaultBackground,
                              error, errorCapacity) &&
           ReplaceSpritesheet(state, sprite, 3, kNativeLockedLayer,
                              error, errorCapacity) &&
           CallSpriteVoid(state, sprite, "LoadGraphics", error, errorCapacity) &&
           CallSpriteVoid(state, sprite, "Update", error, errorCapacity);
}

bool RestoreActiveOnce(lua_State* state, std::uintptr_t manager,
                       const ActiveNotification& active, char* error,
                       std::size_t errorCapacity) noexcept {
    if (!active.restorePending) return true;
    if (manager == 0) {
        SetError(error, errorCapacity, "manager is unavailable");
        return false;
    }
    const auto overlay = Overlay(manager);
    if (overlay == 0) {
        SetError(error, errorCapacity, "achievement overlay is unavailable");
        return false;
    }
    const int top = lua_gettop(state);
    int sprite = 0;
    const bool pushed = PushOverlaySprite(state, overlay, &sprite, error, errorCapacity);
    const bool restored = pushed && RestoreNativeSprites(state, sprite, error, errorCapacity);
    lua_settop(state, top);
    return restored;
}

const char* FailureName(RepentogonAchievementNotificationFailure failure) noexcept {
    switch (failure) {
        case RepentogonAchievementNotificationFailure::OverlayStart:
            return "OverlayStart";
        case RepentogonAchievementNotificationFailure::ApplyCustom:
            return "ApplyCustom";
        case RepentogonAchievementNotificationFailure::RestoreNative:
            return "RestoreNative";
        case RepentogonAchievementNotificationFailure::IdentityChangeRestore:
            return "IdentityChangeRestore";
        case RepentogonAchievementNotificationFailure::None:
            break;
    }
    return "None";
}

int Fail(lua_State* state, int baseTop, RepentogonAchievementNotificationFailure failure,
         int achievementId, const char* detail) noexcept {
    auto& diagnostics = g_Notifications.diagnostics;
    if (failure == RepentogonAchievementNotificationFailure::OverlayStart) {
        ++diagnostics.startFailures;
    } else if (failure == RepentogonAchievementNotificationFailure::ApplyCustom) {
        ++diagnostics.applyFailures;
    } else if (failure == RepentogonAchievementNotificationFailure::RestoreNative ||
               failure == RepentogonAchievementNotificationFailure::IdentityChangeRestore) {
        ++diagnostics.restoreFailures;
    }
    diagnostics.lastFailure = failure;
    diagnostics.lastFailureId = achievementId;

    char message[512]{};
    std::snprintf(message, sizeof(message), "%s achievement %d: %s",
                  FailureName(failure), achievementId,
                  detail != nullptr && detail[0] != '\0' ? detail : "failed");
    lua_settop(state, baseTop);
    lua_pushlstring(state, message, std::char_traits<char>::length(message));
    return -1;
}

bool PurgeDifferentPending(const NotificationIdentity& identity) {
    const auto before = g_Notifications.pending.size();
    g_Notifications.pending.erase(
        std::remove_if(g_Notifications.pending.begin(), g_Notifications.pending.end(),
                       [&](const PendingNotification& notification) {
                           return !SameIdentity(notification.identity, identity);
                       }),
        g_Notifications.pending.end());
    return g_Notifications.pending.size() != before;
}

void ClearActive() noexcept {
    g_Notifications.active = {};
}

bool ClearAllBookkeeping() noexcept {
    const bool had = !g_Notifications.pending.empty() || g_Notifications.active.id != 0;
    g_Notifications.pending.clear();
    g_Notifications.active = {};
    return had;
}

int FinishActive(lua_State* state, int baseTop, std::uintptr_t manager) noexcept {
    auto& active = g_Notifications.active;
    const auto overlay = Overlay(manager);
    if (overlay == 0) return 0;
    std::int32_t overlayState = 0;
    std::uint64_t queueSize = 0;
    std::int32_t displayedId = 0;
    if (!ReadOverlayState(overlay, &overlayState, &queueSize, &displayedId) ||
        overlayState != 0) {
        return 0;
    }

    char error[256]{};
    const int id = active.id;
    const bool restored = RestoreActiveOnce(state, manager, active, error, sizeof(error));
    active = {};
    if (!restored) {
        return Fail(state, baseTop, RepentogonAchievementNotificationFailure::RestoreNative,
                    id, error);
    }
    return 1;
}
}  // namespace

void ResetRepentogonAchievementNotifications() noexcept {
    g_Notifications.pending.clear();
    g_Notifications.active = {};
    g_Notifications.manager = 0;
    g_Notifications.diagnostics = {};
}

bool HasPendingRepentogonAchievementNotifications() noexcept {
    return g_Notifications.active.id != 0 || !g_Notifications.pending.empty();
}

RepentogonAchievementNotificationDiagnostics
SnapshotRepentogonAchievementNotificationDiagnostics() noexcept {
    return g_Notifications.diagnostics;
}

bool QueueRepentogonAchievementNotification(int achievementId) {
    if (achievementId < xml_data::kFirstCustomAchievementId) return false;
    const auto* record = xml_data::FindEntryById(xml_data::XmlNodeType::Achievement,
                                                  achievementId);
    if (record == nullptr || !Visible(*record)) return false;
    const auto* gfx = Attribute(*record, "gfx");
    if (gfx == nullptr || gfx->value.empty()) return false;

    NotificationIdentity identity;
    if (!CurrentIdentity(&identity)) return false;

    const auto manager = ResolveManager();
    if (manager != 0 && g_Notifications.manager != 0 &&
        manager != g_Notifications.manager) {
        if (ClearAllBookkeeping()) ++g_Notifications.diagnostics.identityResets;
    }
    if (manager != 0) g_Notifications.manager = manager;

    if (PurgeDifferentPending(identity)) {
        ++g_Notifications.diagnostics.identityResets;
    }
    if (g_Notifications.active.id == achievementId &&
        SameIdentity(g_Notifications.active.identity, identity)) {
        return false;
    }
    for (const auto& pending : g_Notifications.pending) {
        if (pending.id == achievementId && SameIdentity(pending.identity, identity)) {
            return false;
        }
    }

    PendingNotification notification;
    notification.identity = identity;
    notification.id = achievementId;
    notification.gfx = Path(*record, *gfx);
    const auto* background = Attribute(*record, "gfxback");
    notification.background = background ? Path(*record, *background) : kDefaultBackground;
    g_Notifications.pending.push_back(std::move(notification));
    return true;
}

int PumpRepentogonAchievementNotifications(lua_State* state) {
    if (g_Notifications.active.id == 0 && g_Notifications.pending.empty()) return 0;
    if (state == nullptr || !LuaRuntime::IsOnGameThread()) return 0;

    const int baseTop = lua_gettop(state);
    const auto manager = ResolveManager();
    if (manager != 0 && g_Notifications.manager != 0 &&
        manager != g_Notifications.manager) {
        const bool changed = ClearAllBookkeeping();
        g_Notifications.manager = manager;
        if (changed) ++g_Notifications.diagnostics.identityResets;
        return changed ? 1 : 0;
    }
    if (manager != 0) g_Notifications.manager = manager;

    NotificationIdentity identity;
    if (!CurrentIdentity(&identity)) {
        char error[256]{};
        const int activeId = g_Notifications.active.id;
        bool restored = true;
        if (g_Notifications.active.id != 0) {
            restored = RestoreActiveOnce(state, manager, g_Notifications.active,
                                         error, sizeof(error));
        }
        const bool changed = ClearAllBookkeeping();
        if (changed) ++g_Notifications.diagnostics.identityResets;
        if (!restored) {
            return Fail(state, baseTop,
                        RepentogonAchievementNotificationFailure::IdentityChangeRestore,
                        activeId, error);
        }
        return changed ? 1 : 0;
    }

    const bool pendingChanged = PurgeDifferentPending(identity);
    bool activeChanged = false;
    if (g_Notifications.active.id != 0 &&
        !SameIdentity(g_Notifications.active.identity, identity)) {
        char error[256]{};
        const int activeId = g_Notifications.active.id;
        const bool restored = RestoreActiveOnce(
            state, manager, g_Notifications.active, error, sizeof(error));
        ClearActive();
        activeChanged = true;
        if (!restored) {
            ++g_Notifications.diagnostics.identityResets;
            return Fail(state, baseTop,
                        RepentogonAchievementNotificationFailure::IdentityChangeRestore,
                        activeId, error);
        }
    }
    if (pendingChanged || activeChanged) {
        ++g_Notifications.diagnostics.identityResets;
    }
    if (activeChanged) return 1;
    if (g_Notifications.active.id == 0 && g_Notifications.pending.empty()) {
        return pendingChanged ? 1 : 0;
    }
    if (manager == 0) return 0;

    if (g_Notifications.active.id != 0) {
        return FinishActive(state, baseTop, manager);
    }

    const auto overlay = Overlay(manager);
    if (overlay == 0) return 0;

    bool enabled = false;
    if (!PopupEnabled(manager, &enabled)) return 0;
    if (!enabled) {
        g_Notifications.pending.clear();
        return 1;
    }

    std::int32_t overlayState = 0;
    std::uint64_t nativeQueueSize = 0;
    std::int32_t displayedId = 0;
    if (!ReadOverlayState(overlay, &overlayState, &nativeQueueSize, &displayedId) ||
        overlayState != 0 || nativeQueueSize != 0) {
        return 0;
    }

    int sprite = 0;
    char error[256]{};
    if (!PushOverlaySprite(state, overlay, &sprite, error, sizeof(error))) {
        lua_settop(state, baseTop);
        return 0;
    }
    if (!ShowDummyAchievement(manager)) {
        lua_settop(state, baseTop);
        return 0;
    }

    if (!ReadOverlayState(overlay, &overlayState, &nativeQueueSize, &displayedId) ||
        overlayState != 1 || nativeQueueSize != 0 || displayedId != kDummyAchievementId) {
        PendingNotification notification = std::move(g_Notifications.pending.front());
        g_Notifications.pending.pop_front();
        g_Notifications.active = {notification.identity, notification.id, true};
        return Fail(state, baseTop,
                    RepentogonAchievementNotificationFailure::OverlayStart,
                    notification.id, "dummy overlay did not enter state 1");
    }

    PendingNotification notification = std::move(g_Notifications.pending.front());
    g_Notifications.pending.pop_front();
    g_Notifications.active = {notification.identity, notification.id, true};
    if (!ApplyCustomSprites(state, sprite, notification, error, sizeof(error))) {
        return Fail(state, baseTop,
                    RepentogonAchievementNotificationFailure::ApplyCustom,
                    notification.id, error);
    }
    lua_settop(state, baseTop);
    return 1;
}

#if !defined(__SWITCH__)
void SetRepentogonAchievementNotificationTestBindings(
    RepentogonAchievementNotificationTestBindings bindings) noexcept {
    g_TestBindings = bindings;
}
#endif

}  // namespace isaac::runtime
