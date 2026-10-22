#pragma once
#include <cstdint>
struct lua_State;
namespace isaac::runtime {
int TryPushApi700Option(lua_State*,const char*);
bool TryWriteApi700Option(lua_State*,const char*);
#if !defined(__SWITCH__)
void SetApi700OptionNativeTestBindings(std::uintptr_t music,std::uintptr_t sound)noexcept;
#endif
}
