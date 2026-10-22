#pragma once

#include <cstddef>

extern "C" {
#include <lua.h>
}

namespace LuaRuntime { struct RngHandle; }

namespace isaac::runtime {

// 在交给原生方法前统一复核引用身份与读写权限，失效抛Lua错误。
[[nodiscard]] void* ResolveRngObject(lua_State* state, LuaRuntime::RngHandle* handle, bool writable);

// Registers the `RNG` owner methods (SetSeed / Next) from the API catalog.
//
// Slice 8 of the per-family split: the binding table and the handler bodies
// live here. The RNG object is the Lua userdata itself, so the handlers only
// need the method byte-guard verdict from `lua_runtime_state.hpp`.
//
// Returns how many methods were attached.
[[nodiscard]] std::size_t AttachRngMethods(lua_State* state) noexcept;

} // namespace isaac::runtime
