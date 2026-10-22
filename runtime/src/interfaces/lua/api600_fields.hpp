#pragma once
#include <cstdint>
struct lua_State;
namespace isaac::runtime {
int TryPushApi600EntityField(lua_State*,std::uintptr_t,const char*);
bool TryWriteApi600EntityField(lua_State*,std::uintptr_t,const char*);
}
