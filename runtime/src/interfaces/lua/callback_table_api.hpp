#pragma once
#include <cstdint>
extern "C" {
#include <lua.h>
}
namespace isaac::runtime {
// 关闭VM后清空外部的内建回调位图及诊断计数，不访问旧registry。
void ResetCallbackRuntimeState() noexcept;
void RegisterCallbackBootstrap(lua_State* state, lua_CFunction invoke);
int CallCallbackTableApi(lua_State* state, const char* name);
int GetBuiltInCallbackState(lua_State* state);
int SetBuiltInCallbackState(lua_State* state);
void PushCallbackRunner(lua_State* state, bool ownerOnly = false);
void PushModUnloader(lua_State* state);
void RefreshCallbackDiagnostics(lua_State* state);
bool BuiltinCallbackEnabled(std::uint32_t id) noexcept;
std::uint32_t CountLuaCallbacks(lua_State* state, std::uint32_t id) noexcept;
extern std::uint32_t g_CallbackDiagnosticViewIncomplete;
extern std::uint32_t g_CallbackDiagnosticViewOverflow;
}
