#include "entity_init_hook.hpp"
#include "interfaces/lua/entity_lifetime.hpp"
#include "infrastructure/memory/engine_field_access.hpp"

namespace isaac::runtime {
// Every native reinitialization goes through the base Init, including Morph.
// Clear at its return, before the derived initializer can notify Lua consumers.
void RunNativeEntityInit(const EntityInitNativeBindings* native, NativeEntityInitKind kind,
    void* entity, std::uint32_t type, std::uint32_t variant,
    std::uint32_t subtype, std::uint32_t seed) noexcept {
    if (native == nullptr || native->init == nullptr) __builtin_trap();
    native->init(entity, type, variant, subtype, seed);
    const auto address = engine_memory::AddressOf(entity);
    switch (kind) {
        case NativeEntityInitKind::Base: ReinitializeEntityLifetime(address); break;
        case NativeEntityInitKind::Tear: LuaRuntime::DispatchNativeTearInit(address); break;
        case NativeEntityInitKind::Effect: LuaRuntime::DispatchNativeEffectInit(address); break;
    }
}
}
