#pragma once
struct lua_State;
namespace isaac::runtime {
int RegisterRepentogonGameStateData(lua_State*);
void ResetRepentogonGameStateData() noexcept;
void RepentogonStoreGameStateData(int slot) noexcept;
void RepentogonRestoreGameStateData(int slot) noexcept;
void RepentogonCleanupGameStateData() noexcept;
int RepentogonSaveStateManagerGetGameData(lua_State*);
int RepentogonSaveStateManagerClearGameData(lua_State*);
}
