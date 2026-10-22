#pragma once
#include <cstddef>
#include <cstdint>
struct lua_State;
namespace isaac::runtime {
std::size_t AttachApi400Methods(lua_State*,const char*)noexcept;
int TryPushApi400EffectMethod(lua_State*,std::uintptr_t,const char*);
}
