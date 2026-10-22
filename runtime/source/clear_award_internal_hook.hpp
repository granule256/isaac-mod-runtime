#pragma once
#include "relay/internal_hook.hpp"

namespace isaac::runtime {
struct ClearAwardNativeBindings {
    using VectorConstructor = void (*)(void*, float, float);
    VectorConstructor constructVector{};
};
// 0续45698C奖励逻辑；1续458170析构，取消时不写回seed。
std::uint32_t ClearAwardInternalCallback(relay::InternalHookContext& context,
                                         const void* nativeBindings) noexcept;
}
