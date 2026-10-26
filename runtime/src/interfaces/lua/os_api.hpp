#pragma once
struct lua_State;
namespace isaac::runtime {
// 使用随项目固定的Lua5.3.3语义，只注册兼容层公开的六个os成员。
void RegisterOsLibrary(lua_State* state);
void InitializeOsClock() noexcept;
}
