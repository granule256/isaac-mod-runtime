#pragma once
#include <cstdint>
struct lua_State;
namespace isaac::runtime {
// GetPtrHash的非实体分支：返回真实对象地址；未知或失效对象返回0，不改变对象状态。
void RegisterCoreObjectPointerIdentities(lua_State* state);
std::uintptr_t ResolveNonEntityPointerIdentity(lua_State* state,int index) noexcept;
}
