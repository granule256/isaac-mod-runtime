#pragma once
#include <cstdint>

namespace LuaRuntime {
// 原生玩家Init返回边界；必须早于引擎第一次死亡判定。
void DispatchNativePlayerInit(std::uintptr_t player) noexcept;
}
