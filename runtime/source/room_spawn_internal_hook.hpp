#pragma once
#include "relay/internal_hook.hpp"

namespace isaac::runtime {
struct RoomSpawnNativeBindings {
    using Construct = void (*)(void*, std::uint32_t, std::uint32_t);
    using Random = std::uint32_t (*)(void*, std::uint32_t);
    using Next = std::uint32_t (*)(void*);
    using GetCard = std::uint32_t (*)(const void*, std::uint32_t, bool, bool, bool);
    Next next{};
    GetCard getCard{};
    Construct construct{};
    Random random{};
    std::uintptr_t gameGotSlot{};
};
// 返回绑定中续接点索引：0=原常规修正，1=原RNG析构（仍回到Roomspawn调用方）。
std::uint32_t RoomSpawnInternalCallback(relay::InternalHookContext& context,
    const void* nativeBindings) noexcept;
// 生产入口是原RNG构造的BL；先执行原必要预处理，再到71真实阶段。
std::uint32_t RoomFixSpawnCtorInternalCallback(relay::InternalHookContext& context,
    const void* nativeBindings) noexcept;
} // namespace isaac::runtime
