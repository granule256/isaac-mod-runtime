#pragma once
#include <cstdint>
struct lua_State;
namespace LuaRuntime { struct EntityLifetimeToken; }
namespace isaac::runtime {
// 留下token userdata在栈顶；创建/挂接只在Lua保护内执行。
LuaRuntime::EntityLifetimeToken* PushEntityLifetimeToken(lua_State*, std::uintptr_t entity);
bool EntityLifetimeAlive(const LuaRuntime::EntityLifetimeToken*) noexcept;
bool EntityTearInitialized(std::uintptr_t entity) noexcept;
void MarkEntityTearInitialized(std::uintptr_t entity) noexcept;
bool EntityEffectInitialized(std::uintptr_t entity) noexcept;
void MarkEntityEffectInitialized(std::uintptr_t entity) noexcept;
int PushEntityLifetimeData(lua_State*, std::uintptr_t entity);
// Native清理不分配、不扩栈、不调用Lua代码；Remove清data，D2使token失效。
void ClearEntityLifetimeData(std::uintptr_t entity) noexcept;
// Native Init/Morph starts fresh data and INIT claims while preserving live aliases.
void ReinitializeEntityLifetime(std::uintptr_t entity) noexcept;
void RetireEntityLifetime(std::uintptr_t entity) noexcept;
void ResetEntityLifetimeState() noexcept;
}
