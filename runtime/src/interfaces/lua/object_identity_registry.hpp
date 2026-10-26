#pragma once
#include <cstdint>

struct lua_State;

namespace isaac::runtime {
// 每族自行验证寿命、所属对象和原生布局；失效返回0，不得抛Lua错误或调用Lua代码。
using NativeObjectIdentityResolver = std::uintptr_t (*)(lua_State*, int) noexcept;

// 仅接受实际栈上的table；相同解析器幂等，不同解析器拒绝覆盖。
// 每类首次登记创建一个sizeof(resolver)的userdata；元表hash应在初始化时预留容量，
// 否则Lua自己的rawsetp也可能扩容。创建userdata须位于调用方的Lua保护初始化流程内。
// 两入口保持栈高度，支持正负栈索引；调用方提供至少2个空API栈槽，查询不扩栈。
[[nodiscard]] bool RegisterNativeObjectIdentity(
    lua_State*, int metatableIndex, NativeObjectIdentityResolver) noexcept;

// 仅接受full userdata，只查该对象自己的元表，不扫描族/调用Lua/分配或缓存对象。
// 已登记但对象失效：返回0且recognized=true；未知对象：返回0且recognized=false。
[[nodiscard]] std::uintptr_t ResolveRegisteredObjectIdentity(
    lua_State*, int objectIndex, bool* recognized) noexcept;
} // namespace isaac::runtime
