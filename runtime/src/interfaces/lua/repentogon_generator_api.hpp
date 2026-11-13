#pragma once

#include <cstdint>

struct lua_State;

namespace isaac::runtime {

inline constexpr char kLevelGeneratorMetatable[] = "IsaacRuntime.LevelGenerator";
inline constexpr char kLevelGeneratorRoomMetatable[] =
    "IsaacRuntime.LevelGeneratorRoom";
inline constexpr char kBossPoolMetatable[] = "IsaacRuntime.BossPool";

struct LevelGeneratorHandle {
    void* generator;
    std::uintptr_t moduleBase;
};

struct LevelGeneratorRoomHandle {
    void* generator;
    void* room;
    std::uintptr_t moduleBase;
};

struct BossPoolHandle {
    void* pool;
    std::uintptr_t moduleBase;
};

void PushRepentogonLevelGeneratorHandle(lua_State* state, void* generator);
void PushRepentogonLevelGeneratorRoomHandle(lua_State* state, void* generator,
                                            void* room);
void PushRepentogonBossPoolPoolHandle(lua_State* state, void* pool);

void RegisterRepentogonGeneratorViews(lua_State* state);

int RepentogonLevelGeneratorGetAllRooms(lua_State* state);
int RepentogonLevelGeneratorGetDeadEnds(lua_State* state);
int RepentogonLevelGeneratorGetNonDeadEnds(lua_State* state);
int RepentogonLevelGeneratorRoomGenerationIndex(lua_State* state);
int RepentogonLevelGeneratorRoomDoorMask(lua_State* state);
int RepentogonLevelGeneratorRoomColumn(lua_State* state);
int RepentogonLevelGeneratorRoomLine(lua_State* state);
int RepentogonLevelGeneratorRoomShape(lua_State* state);
int RepentogonLevelGeneratorRoomNeighbors(lua_State* state);
int RepentogonLevelGeneratorRoomIsDeadEnd(lua_State* state);
int RepentogonBossPoolGetName(lua_State* state);
int RepentogonBossPoolGetEntries(lua_State* state);
int RepentogonBossPoolGetWeight(lua_State* state);
int RepentogonBossPoolGetRNG(lua_State* state);
int RepentogonBossPoolGetDoubleTroubleRoomVariantStart(lua_State* state);

}  // namespace isaac::runtime
