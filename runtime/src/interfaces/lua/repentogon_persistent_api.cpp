#include "interfaces/lua/repentogon_persistent_api.hpp"

#include "interfaces/lua/repentogon_achievement_notification.hpp"
#include "interfaces/lua/isaac_api.hpp"
#include "interfaces/lua/lua_integer_argument.hpp"
#include "infrastructure/memory/engine_field_access.hpp"
#include "lua_runtime.hpp"
#include "application/repentogon/achievement_state.hpp"
#include "interfaces/lua/api100_native.hpp"
#include "infrastructure/call/engine_call_access.hpp"
#include "program/xml_data_store.hpp"
#include "runtime_constants.hpp"

#include <cstdint>

extern "C" {
#include <lauxlib.h>
}

namespace isaac::runtime {
namespace {
constexpr std::uint32_t kPersistentGameDataCounterOffset = 0x2a8;
constexpr std::uint32_t kPersistentGameDataCollectionOffset = 0xa68;
constexpr std::uint32_t kEventCounterMax = 522;
constexpr std::uint32_t kCollectibleMax = 732;
AchievementState g_Achievements;
api100_native::Cache g_UnlockedEntry{}, g_TryUnlockEntry{};
#if !defined(__SWITCH__)
RepentogonAchievementNativeTestBindings g_AchievementNativeTest{};
#endif
constexpr std::uint8_t kTryUnlockGuard[16] = {
    0xfd,0x7b,0xbd,0xa9,0xf5,0x0b,0x00,0xf9,
    0xfd,0x03,0x00,0x91,0xf4,0x4f,0x02,0xa9};

const char* Attribute(const xml_data::XmlRecord& record, const char* key) noexcept {
    const auto* value = record.FindAttribute(key);
    return value ? value->value.c_str() : "";
}

std::uintptr_t PersistentObject(lua_State* state) {
    if (!LuaRuntime::IsOnGameThread())
        luaL_error(state, "PersistentGameData access requires the game thread");
    const auto object = PersistentGameDataObjectArgument(state, 1);
    if (object == 0) luaL_error(state, "PersistentGameData is no longer available");
    return object;
}

int UnlockCustomAchievement(lua_State* state, int id,
                            const xml_data::XmlRecord& record) {
    bool unlocked{};
    auto status = g_Achievements.Unlocked(SessionSaveFilePort(),
        Attribute(record, "name"), Attribute(record, "sourceid"), &unlocked);
    if (!status.ok()) return luaL_error(state, "Custom achievement state read failed (%d)",
                                        static_cast<int>(status.code()));
    if (unlocked) {
        lua_pushboolean(state, false);
        return 1;
    }
    const bool skipPopup = lua_isboolean(state, 3) && lua_toboolean(state, 3);
    const auto* hidden = record.FindAttribute("hidden");
    const bool visible = !hidden || hidden->value == "false";
    bool changed{};
    status = g_Achievements.Unlock(SessionSaveFilePort(), Attribute(record, "name"),
                                   Attribute(record, "sourceid"), &changed);
    if (!status.ok()) return luaL_error(state, "Custom achievement state write failed (%d)",
                                        static_cast<int>(status.code()));
    if (changed && !skipPopup && visible) {
        // Persistence succeeded first. The native overlay may be busy, in which
        // case Pump keeps this notification queued for the protected frame hook.
        static_cast<void>(QueueRepentogonAchievementNotification(id));
        if (PumpRepentogonAchievementNotifications(state) < 0) {
            // Pump has returned, so its std::string locals are already gone.
            // The error object is the only extra value on the Lua stack.
            return lua_error(state);
        }
    }
    lua_pushboolean(state, changed);
    return 1;
}
}

void ResetRepentogonAchievementState() noexcept {
    g_Achievements.Reset();
    ResetRepentogonAchievementNotifications();
}
#if !defined(__SWITCH__)
void SetRepentogonAchievementNativeTestBindings(RepentogonAchievementNativeTestBindings value) noexcept {
    g_AchievementNativeTest = value;
    g_UnlockedEntry = {};
    g_TryUnlockEntry = {};
}
#endif

int RepentogonPersistentGameDataUnlocked(lua_State* state) {
    const auto object = PersistentObject(state);
    const int id = static_cast<int>(luaL_checkinteger(state, 2));
    if (id < xml_data::kFirstCustomAchievementId) {
        const auto entry = api100_native::Resolve(state,
            {kPersistentGameDataUnlockedOffset, kPersistentGameDataUnlockedExpectedBytes.data()},
            g_UnlockedEntry
#if !defined(__SWITCH__)
            , g_AchievementNativeTest.unlocked
#endif
        );
        const auto call = engine_call::AsFunction<bool (*)(std::uintptr_t, int)>(entry);
        lua_pushboolean(state, call(object, id));
        return 1;
    }
    const auto* record = xml_data::FindEntryById(xml_data::XmlNodeType::Achievement, id);
    bool unlocked{};
    if (record) {
        const auto status = g_Achievements.Unlocked(SessionSaveFilePort(),
            Attribute(*record, "name"), Attribute(*record, "sourceid"), &unlocked);
        if (!status.ok()) return luaL_error(state, "Custom achievement state read failed (%d)",
                                            static_cast<int>(status.code()));
    }
    lua_pushboolean(state, unlocked);
    return 1;
}

int RepentogonPersistentGameDataTryUnlock(lua_State* state) {
    const auto object = PersistentObject(state);
    const int id = static_cast<int>(luaL_checkinteger(state, 2));
    if (id <= 0 || (id > 637 && id < xml_data::kFirstCustomAchievementId)) {
        lua_pushboolean(state, false);
        return 1;
    }
    if (id < xml_data::kFirstCustomAchievementId) {
        const auto entry = api100_native::Resolve(state, {0x4393d0, kTryUnlockGuard}, g_TryUnlockEntry
#if !defined(__SWITCH__)
            , g_AchievementNativeTest.tryUnlock
#endif
        );
        const auto call = engine_call::AsFunction<bool (*)(std::uintptr_t, int)>(entry);
        lua_pushboolean(state, call(object, id));
        return 1;
    }
    const auto* record = xml_data::FindEntryById(xml_data::XmlNodeType::Achievement, id);
    std::uint8_t readonly{};
    if (!engine_memory::ReadField(object, 1, &readonly, engine_memory::EngineMemoryReadable))
        return luaL_error(state, "PersistentGameData readonly flag is unavailable");
    if (!record || readonly) {
        lua_pushboolean(state, false);
        return 1;
    }
    return UnlockCustomAchievement(state, id, *record);
}

int RepentogonPersistentGameDataUnlock(lua_State* state) {
    static_cast<void>(PersistentObject(state));
    const int id = static_cast<int>(luaL_checkinteger(state, 2));
    if (id >= 1 && id <= 637) {
        return luaL_error(
            state, "PersistentGameData:Unlock native force-unlock is unavailable");
    }
    if (id < xml_data::kFirstCustomAchievementId) {
        lua_pushboolean(state, false);
        return 1;
    }
    const auto* record = xml_data::FindEntryById(xml_data::XmlNodeType::Achievement, id);
    if (!record) {
        lua_pushboolean(state, false);
        return 1;
    }

    return UnlockCustomAchievement(state, id, *record);
}

int RepentogonPersistentGameDataGetEventCounter(lua_State* state) {
    const auto object = PersistentObject(state);
    lua_Integer requested = 0;
    if (lua_gettop(state) != 2 || !IntegerArgumentAt(state, 2, &requested) ||
        requested < 0 || static_cast<std::uint64_t>(requested) > kEventCounterMax)
        return luaL_argerror(state, 2, "EventCounter must be between 0 and 522");
    std::int32_t value = 0;
    if (!engine_memory::ReadField(
            object,
            kPersistentGameDataCounterOffset + static_cast<std::uintptr_t>(requested) * 4,
            &value, engine_memory::EngineMemoryReadable))
        return luaL_error(state, "PersistentGameData event counter is not readable");
    lua_pushinteger(state, value);
    return 1;
}

int RepentogonPersistentGameDataIsItemInCollection(lua_State* state) {
    const auto object = PersistentObject(state);
    lua_Integer requested = 0;
    if (lua_gettop(state) != 2 || !IntegerArgumentAt(state, 2, &requested) ||
        requested < 0 || static_cast<std::uint64_t>(requested) > kCollectibleMax)
        return luaL_argerror(state, 2, "CollectibleType must be between 0 and 732");
    std::uint8_t present = 0;
    if (!engine_memory::ReadField(
            object,
            kPersistentGameDataCollectionOffset + static_cast<std::uintptr_t>(requested),
            &present, engine_memory::EngineMemoryReadable))
        return luaL_error(state, "PersistentGameData collection is not readable");
    lua_pushboolean(state, requested != 0 && present != 0);
    return 1;
}
}
