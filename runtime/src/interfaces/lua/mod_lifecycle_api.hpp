#pragma once
#include <cstddef>
extern "C" {
#include <lua.h>
}
namespace isaac::runtime {
void TrackLoadedMod(lua_State* state, int mod, const char* root, bool embedded);
// 必须从lua_pcall保护内进入；新RegisterMod写入下一代，不参与本次卸载。
int UnloadTrackedMods(lua_State* state);
int UnloadTrackedModRoot(lua_State* state);
int FindTrackedModRoot(lua_State* state);
bool CopyCallingModRoot(lua_State*,char*,std::size_t,std::size_t*,const char* throughGlobal=nullptr);
void TrackRequiredModule(lua_State*,const char* root,const char* name,int value);
void ClearTrackedRequireModules(lua_State*,const char* root);
}
