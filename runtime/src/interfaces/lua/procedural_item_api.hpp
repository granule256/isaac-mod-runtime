#pragma once

#include <cstddef>
#include <cstdint>

extern "C" {
#include <lua.h>
}

namespace isaac::runtime {

// The fourteen methods used by EID's TMTRAINER description path.
int ProceduralItemManagerGetProceduralItem(lua_State* state);
int ProceduralItemGetTargetItem(lua_State* state);
int ProceduralItemGetEffectCount(lua_State* state);
int ProceduralItemGetEffect(lua_State* state);
int ProceduralItemGetSpeed(lua_State* state);
int ProceduralItemGetFireDelay(lua_State* state);
int ProceduralItemGetDamage(lua_State* state);
int ProceduralItemGetRange(lua_State* state);
int ProceduralItemGetShotSpeed(lua_State* state);
int ProceduralItemGetLuck(lua_State* state);
int ProceduralEffectGetConditionType(lua_State* state);
int ProceduralEffectGetConditionProperty(lua_State* state);
int ProceduralEffectGetActionType(lua_State* state);
int ProceduralEffectGetActionProperty(lua_State* state);

// These attach through the REPENTOGON extension descriptors. They do not
// embed a second catalog in this translation unit.
[[nodiscard]] std::size_t AttachProceduralItemManagerMethods(lua_State* state) noexcept;
[[nodiscard]] std::size_t AttachProceduralItemMethods(lua_State* state) noexcept;
[[nodiscard]] std::size_t AttachProceduralEffectMethods(lua_State* state) noexcept;

// Creates ProceduralItemManager and the object metatables. It is intended for
// RepentogonBatch::initialize, after the ordinary Lua types already exist.
int RegisterProceduralItemApi(lua_State* state);

// O(1) identity check used by the ItemConfig userdata bridge. It resolves the
// current manager -> items[index] -> wrapper+0x18 chain; no pointer scan.
[[nodiscard]] bool ValidateProceduralTargetItem(std::uintptr_t manager,
                                                std::uintptr_t wrapper,
                                                std::uint32_t index,
                                                std::uint64_t worldEpoch,
                                                std::uintptr_t item) noexcept;

#if !defined(__SWITCH__)
// Host tests have no installed engine singleton. Device builds use GameOwnerSlot.
void SetProceduralItemManagerForHostTesting(std::uintptr_t manager) noexcept;
#endif

}  // namespace isaac::runtime
