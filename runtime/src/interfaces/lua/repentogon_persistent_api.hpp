#pragma once
#include <cstdint>

extern "C" {
#include <lua.h>
}

namespace isaac::runtime {
int RepentogonPersistentGameDataGetEventCounter(lua_State* state);
int RepentogonPersistentGameDataIsItemInCollection(lua_State* state);
int RepentogonPersistentGameDataUnlocked(lua_State* state);
int RepentogonPersistentGameDataTryUnlock(lua_State* state);
void ResetRepentogonAchievementState() noexcept;
#if !defined(__SWITCH__)
struct RepentogonAchievementNativeTestBindings {
    std::uintptr_t unlocked{}, tryUnlock{};
};
void SetRepentogonAchievementNativeTestBindings(RepentogonAchievementNativeTestBindings) noexcept;
#endif
}
