#pragma once

#include <cstddef>

extern "C" {
#include <lua.h>
}

namespace isaac::runtime {

// Registers the `Input` owner methods (IsButtonTriggered / IsButtonPressed /
// GetButtonValue / IsActionTriggered / IsActionPressed / GetActionValue) from
// the API catalog.
//
// Slice 8 of the per-family split: the binding table and the handler bodies
// live here. The handlers are neutral stubs: they validate the argument shape
// and answer "not pressed" / `0.0` until the native input tables have evidence.
//
// Returns how many methods were attached.
[[nodiscard]] std::size_t AttachInputMethods(lua_State* state) noexcept;

// `Input.IsActionTriggered` 的上升沿表是会话级状态（与 `ManagedFrameClock` 同一口径），
// 新建 Lua 会话时要清空 —— 不清的话上一次会话"按住过"的记录会让新会话的第一次询问凭空报一次"刚按下"。
void ResetInputEdgeState() noexcept;

} // namespace isaac::runtime
