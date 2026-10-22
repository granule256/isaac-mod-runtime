#pragma once
#include <cstdint>
struct lua_State;
namespace isaac::runtime {
using Api700StringConsumer=int(*)(lua_State*,const void*,void*);
int WithApi700NativeString(lua_State*,int,Api700StringConsumer,void*);
void AssignApi700NativeString(lua_State*,std::uintptr_t,int);
#if !defined(__SWITCH__)
using Api700StringAssign=void*(*)(void*,const void*);
void SetApi700StringAssignForTesting(Api700StringAssign)noexcept;
#endif
}
