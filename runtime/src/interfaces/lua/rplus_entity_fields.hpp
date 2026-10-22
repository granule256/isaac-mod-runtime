#pragma once
#include <cstdint>
#include "interfaces/lua/bitset128_api.hpp"
struct lua_State;
namespace isaac::runtime {
int TryPushRPlusEntityField(lua_State*,std::uintptr_t,const char*);
bool TryWriteRPlusEntityField(lua_State*,std::uintptr_t,const char*);
#if !defined(__SWITCH__)
struct RPlusEntityFieldNativeTestBindings {
 void (*tearFlags)(void*,BitSet128Value){};
 void (*bombFlags)(void*,BitSet128Value){};
 void (*collisionDamage)(void*,float){};
};
void SetRPlusEntityFieldNativeTestBindings(RPlusEntityFieldNativeTestBindings) noexcept;
#endif
}
