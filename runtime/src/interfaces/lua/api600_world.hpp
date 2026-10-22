#pragma once
#include <cstdint>
struct lua_State;
namespace isaac::runtime {
bool IsApi600WorldField(const char*,const char*)noexcept;
int TryPushApi600WorldField(lua_State*,std::uintptr_t,const char*,const char*);
bool TryWriteApi600WorldField(lua_State*,std::uintptr_t,const char*,const char*);
int TryPushApi600GridField(lua_State*,std::uintptr_t,const char*);
bool TryWriteApi600GridField(lua_State*,std::uintptr_t,const char*);
}
