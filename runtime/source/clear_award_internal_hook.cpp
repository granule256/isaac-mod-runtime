#include "clear_award_internal_hook.hpp"
#include "lua_runtime.hpp"
#include "infrastructure/memory/engine_field_access.hpp"
#include <array>
#include <cstring>

namespace isaac::runtime {
std::uint32_t ClearAwardInternalCallback(relay::InternalHookContext& context,
                                         const void* nativeBindings) noexcept {
    const auto& native = *static_cast<const ClearAwardNativeBindings*>(nativeBindings);
    if (native.constructVector == nullptr || context.x[29] < 0x30) __builtin_trap();
    float x{}, y{};
    std::memcpy(&x, &context.q[0].low, sizeof(x));
    std::memcpy(&y, &context.q[1].low, sizeof(y));
    // 重放被替换的VectorCtor，原函数只store两float，x0和s0/s1原值不变。
    native.constructVector(engine_memory::AsObject(context.x[0]), x, y);
    const auto rngAddress = context.x[29] - 0x28;
    const auto positionAddress = context.x[29] - 0x30;
    std::array<std::uint8_t, 16> snapshot{};
    std::array<float, 2> position{};
    if (!engine_memory::ReadField(rngAddress, 0, &snapshot, engine_memory::EngineMemoryReadable) ||
        !engine_memory::ReadField(positionAddress, 0, &position, engine_memory::EngineMemoryReadable))
        __builtin_trap(); // 已守卫的原函数自身局部栈，不能制造实参。
    if (!LuaRuntime::DispatchPreSpawnCleanAward(snapshot, position[0], position[1])) return 0;
    context.x[0] = rngAddress;
    return 1;
}
}
