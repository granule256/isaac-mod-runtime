#pragma once

struct lua_State;

namespace isaac::runtime {

// Parent calls this once after EntityPlayer's metatable exists. It installs
// AddCustomCacheTag and GetCustomCacheValue without changing the API catalog.
int RegisterCustomCacheApi(lua_State* state);

int CustomCacheAddTag(lua_State* state);
int CustomCacheGetValue(lua_State* state);

}  // namespace isaac::runtime
