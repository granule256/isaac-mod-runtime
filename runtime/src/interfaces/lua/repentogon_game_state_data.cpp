#include "interfaces/lua/repentogon_game_state_data.hpp"
#include "interfaces/lua/mod_api.hpp"
#include "interfaces/lua/owner_binding.hpp"
#include "lua_runtime.hpp"
extern "C" {
#include <lauxlib.h>
}
namespace isaac::runtime {
namespace {
lua_State* g_State{};
bool g_HasData{};
constexpr char kRegistry[]="IsaacRuntime.GameStateData";
// Match the in-memory SSM/TableUtils contract: scalar keys, serializable
// values, cycles and shared sub-tables. Disk serialization is not involved.
constexpr char kSnapshotModule[]=R"lua(
local owner = ...
local mods = {}
local function copy(value, memo)
  if memo[value] then return memo[value] end
  local result = {}; memo[value] = result
  for key, item in pairs(value) do
    local kt, vt = type(key), type(item)
    if (kt == 'string' or kt == 'number' or kt == 'boolean') then
      if vt == 'table' then result[key] = copy(item, memo)
      elseif vt == 'string' or vt == 'number' or vt == 'boolean' then result[key] = item end
    end
  end
  return result
end
local function entry(mod)
  local key = owner(mod)
  if not mods[key] then mods[key] = {data = {}, states = {}} end
  return mods[key]
end
return {
 get = function(mod) return entry(mod).data end,
 clear = function(mod) entry(mod).data = {} end,
 store = function(slot)
   for _, value in pairs(mods) do value.states[slot] = copy(value.data, {}) end
 end,
 cleanup = function() for _, value in pairs(mods) do value.data = {} end end,
 restore = function(slot)
   for _, value in pairs(mods) do value.data = copy(value.states[slot] or {}, {}) end
 end
}
)lua";
int Owner(lua_State* state) {
    const auto owner=ModObjectOwner(state,1);
    if(!owner)return luaL_argerror(state,1,"ModReference expected");
    lua_pushinteger(state,owner);return 1;
}
int Call(lua_State* state,const char* name,int arguments,int results) {
    lua_getfield(state,LUA_REGISTRYINDEX,kRegistry);
    lua_getfield(state,-1,name);lua_remove(state,-2);
    lua_insert(state,1);
    lua_call(state,arguments,results);
    return results;
}
int SnapshotProtected(lua_State* state) {
    const auto* operation=lua_tostring(state,1);
    lua_getfield(state,LUA_REGISTRYINDEX,kRegistry);
    lua_getfield(state,-1,operation);lua_pushvalue(state,2);
    lua_call(state,1,0);return 0;
}
void Snapshot(const char* operation,int slot) noexcept {
    auto* state=g_State;
    if(!state||!g_HasData||!LuaRuntime::IsOnGameThread())return;
    const auto top=lua_gettop(state);
    if(!lua_checkstack(state,6)){LuaRuntime::ReportCallbackError(nullptr);return;}
    lua_pushcfunction(state,SnapshotProtected);lua_pushstring(state,operation);
    lua_pushinteger(state,slot);
    if(lua_pcall(state,2,0,0)!=LUA_OK)LuaRuntime::ReportCallbackError(state);
    lua_settop(state,top);
}
}
int RegisterRepentogonGameStateData(lua_State* state) {
    if(luaL_loadbuffer(state,kSnapshotModule,sizeof(kSnapshotModule)-1,
                       "@runtime-game-state-data.lua")!=LUA_OK)return lua_error(state);
    lua_pushcfunction(state,Owner);lua_call(state,1,1);
    lua_setfield(state,LUA_REGISTRYINDEX,kRegistry);
    g_State=state;g_HasData=false;
    lua_newtable(state);
    static_cast<void>(AttachOwnerMethods(state,"SaveStateManager",nullptr,0));
    lua_setglobal(state,"SaveStateManager");
    return 0;
}
void ResetRepentogonGameStateData() noexcept {g_State=nullptr;g_HasData=false;}
void RepentogonStoreGameStateData(int slot) noexcept {Snapshot("store",slot);}
void RepentogonRestoreGameStateData(int slot) noexcept {Snapshot("restore",slot);}
void RepentogonCleanupGameStateData() noexcept {Snapshot("cleanup",0);}
int RepentogonSaveStateManagerGetGameData(lua_State* state) {
    if(!LuaRuntime::IsOnGameThread())return luaL_error(state,"SaveStateManager requires the game thread");
    lua_settop(state,1);const auto results=Call(state,"get",1,1);g_HasData=true;return results;
}
int RepentogonSaveStateManagerClearGameData(lua_State* state) {
    if(!LuaRuntime::IsOnGameThread())return luaL_error(state,"SaveStateManager requires the game thread");
    lua_settop(state,1);Call(state,"clear",1,0);g_HasData=true;return 0;
}
}
