#pragma once
struct lua_State;
namespace isaac::runtime {
void RegisterApi600ConfigLists(lua_State*);
int Api600ItemConfigGetCards(lua_State*);
int Api600ItemConfigGetPillEffects(lua_State*);
int Api600ItemConfigGetNullItems(lua_State*);
int Api600ItemConfigItemIsNull(lua_State*);
int Api600ItemConfigShouldAddCostumeOnPickup(lua_State*);
int Api600CardConfigListGet(lua_State*);
int Api600CardConfigListLen(lua_State*);
int Api600PillConfigListGet(lua_State*);
int Api600PillConfigListLen(lua_State*);
}
