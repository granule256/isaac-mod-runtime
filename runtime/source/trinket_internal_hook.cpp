#include "trinket_internal_hook.hpp"
#include "lua_runtime.hpp"
#include "runtime_constants.hpp"
#include "infrastructure/memory/engine_field_access.hpp"

#include <array>

namespace isaac::runtime {
namespace {
std::uintptr_t PoolRngAddress(std::uintptr_t pool) noexcept {
    if (pool == 0 || (pool & (alignof(std::uintptr_t)-1)) != 0) return 0;
    return engine_memory::FieldAddress(pool, kItemPoolTrinketRngOffset, kRngObjectSize, alignof(std::uint32_t),
        engine_memory::EngineMemoryReadable);
}
std::uintptr_t ReadRequiredPointer(std::uintptr_t address) noexcept {
    std::uintptr_t value{};
    if (!engine_memory::ReadField(address,0,&value,engine_memory::EngineMemoryReadable) || value==0)
        __builtin_trap();
    return value;
}
}

std::uint32_t TrinketFirstRandomInternalCallback(relay::InternalHookContext& context,
    const void* nativeBindings) noexcept {
    const auto& native = *static_cast<const TrinketNativeBindings*>(nativeBindings);
    if (native.random == nullptr) __builtin_trap();
    const auto pool = context.x[20];
    const auto dontAdvance = context.x[21] & 1U;
    // 首点前 x20 仍是 this；首点后原函数只消费 x21 bit0，epilogue 恢复 caller x21。
    // 非自然对齐/不可读只留下原 bool；第二点拒绝派发，原生调用仍照常执行。
    context.x[21] = PoolRngAddress(pool) != 0 ? pool | dontAdvance : dontAdvance;
    context.x[0] = native.random(engine_memory::AsObject(context.x[0]),
        static_cast<std::uint32_t>(context.x[1]));
    return 0;
}

std::uint32_t TrinketSelectedInternalCallback(relay::InternalHookContext& context,
    const void* nativeBindings) noexcept {
    const auto& native = *static_cast<const TrinketNativeBindings*>(nativeBindings);
    const auto pool = context.x[21] & ~std::uintptr_t{1};
    const auto rng = PoolRngAddress(pool);
    if (rng != 0) {
        std::array<std::uint8_t,kRngObjectSize> snapshot{};
        if (engine_memory::ReadField(rng,0,&snapshot,engine_memory::EngineMemoryReadable)) {
            const auto selected = static_cast<std::int32_t>(static_cast<std::uint32_t>(context.x[20]));
            const auto replacement = LuaRuntime::DispatchGetTrinket(selected,snapshot);
            if (replacement != 0) {
                context.x[20] = replacement; // 写 w20 的零扩展语义；非零覆盖不走黄金处理。
                return 1; // 0x3C78AC 保留原两 RNG 析构和 epilogue。
            }
        }
    }
    if (native.unlocked == nullptr) __builtin_trap();
    // PC 的判定发生于 Lua 回调之后；回调/嵌套可能改变 Manager，不能复用旧 x0。
    const auto variable = ReadRequiredPointer(native.managerGotSlot);
    const auto manager = ReadRequiredPointer(variable);
    const auto pgd = engine_memory::FieldAddress(manager,0x18,1,0,
        engine_memory::EngineMemoryReadable);
    if (pgd==0) __builtin_trap();
    context.x[0] = native.unlocked(engine_memory::AsObject(pgd),617) ? 1U : 0U;
    return 0; // 0x3C7850 继续原黄金 RNG/析构；仅装第二点的 x21=0/1 同样走这里。
}
} // namespace isaac::runtime
