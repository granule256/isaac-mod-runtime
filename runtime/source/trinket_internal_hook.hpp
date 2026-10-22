#pragma once

#include "relay/internal_hook.hpp"

namespace isaac::runtime {
struct TrinketNativeBindings {
    using Random = std::uint32_t (*)(void*, std::uint32_t);
    using Unlocked = bool (*)(const void*, std::uint32_t);
    Random random{};
    Unlocked unlocked{};
    std::uintptr_t managerGotSlot{}; // GOT -> g_Manager 变量 -> 当前 Manager
};
// 仅替换首 RNG.Random BL：重放原输入，x21 携带对齐 pool 地址与原 DontAdvance bit0。
std::uint32_t TrinketFirstRandomInternalCallback(relay::InternalHookContext& context,
    const void* nativeBindings) noexcept;
// 黄金前 Unlocked BL：0=原黄金逻辑，1=原两个 RNG 析构/epilogue。
std::uint32_t TrinketSelectedInternalCallback(relay::InternalHookContext& context,
    const void* nativeBindings) noexcept;
} // namespace isaac::runtime
