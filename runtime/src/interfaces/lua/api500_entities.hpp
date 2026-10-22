#pragma once
#include <cstdint>
struct lua_State;
namespace isaac::runtime {
int TryPushApi500EntityField(lua_State*,std::uintptr_t,const char*);
bool TryWriteApi500EntityField(lua_State*,std::uintptr_t,const char*);
}
