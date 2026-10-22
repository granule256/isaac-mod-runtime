#pragma once
#include <cstdint>
struct lua_State;
namespace isaac::runtime {
int TryPushApi400EntityField(lua_State*,std::uintptr_t entity,const char*name);
bool TryWriteApi400EntityField(lua_State*,std::uintptr_t entity,const char*name);
}
