#include "interfaces/lua/entity_lifetime.hpp"
#include "infrastructure/relay/entry_relay_binding.hpp"
#include "infrastructure/memory/engine_field_access.hpp"

namespace isaac::runtime {
// Every native reinitialization goes through the base Init, including Morph.
// Clear at its return, before the derived initializer can notify Lua consumers.
extern "C" void EntryRelayEntityInitCallback(void* entity, std::uint32_t type,
    std::uint32_t variant, std::uint32_t subtype, std::uint32_t seed) {
    using Init = void (*)(void*, std::uint32_t, std::uint32_t, std::uint32_t, std::uint32_t);
    const auto original = Original<Init>(HookId::EntityInit);
    if (original == nullptr) __builtin_trap();
    original(entity, type, variant, subtype, seed);
    ReinitializeEntityLifetime(engine_memory::AddressOf(entity));
}
}
