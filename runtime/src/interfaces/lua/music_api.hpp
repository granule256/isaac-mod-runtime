#pragma once

#include <cstddef>

extern "C" {
#include <lua.h>
}

namespace isaac::runtime {

// Registers the `MusicManager` owner methods (GetCurrentMusicID / Pause /
// Resume) from the API catalog.
//
// Slice 8 of the per-family split: the binding table and the handler bodies
// live here. Resolving the native Music object still needs the legacy
// translation unit (callback Manager slot and method byte guards), so the
// handlers call the transitional accessors in `lua_runtime_state.hpp` instead
// of touching that file's internals.
//
// Returns how many methods were attached.
[[nodiscard]] std::size_t AttachMusicMethods(lua_State* state) noexcept;
// 批次 045：`SFXManager()` 的方法表与构造器（元表/全局由中枢建）。
[[nodiscard]] std::size_t AttachSfxManagerMethods(lua_State* state) noexcept;
int SfxManagerCtor(lua_State* state);

} // namespace isaac::runtime
