#pragma once
#include <cstdint>

namespace isaac::runtime {
enum class HookId : std::uint8_t;
struct HookTarget;
class Status;
inline constexpr bool IsNpcInitializationType(std::int32_t type) noexcept {
    return type >= 10 && type != 1000;
}
enum class NativeEntityInitKind { Base, Tear, Effect, Pickup };
struct EntityInitNativeBindings {
    using Init = void (*)(void*, std::uint32_t, std::uint32_t, std::uint32_t, std::uint32_t);
    Init init{};
};
// One call corresponds to one actual native Init, including repeated Init of a
// live object. Base completion clears GetData; derived completion publishes Lua.
void RunNativeEntityInit(const EntityInitNativeBindings*, NativeEntityInitKind, void*,
    std::uint32_t, std::uint32_t, std::uint32_t, std::uint32_t) noexcept;
Status InstallEntityInitPointerHooks(HookId, const HookTarget&) noexcept;
}

namespace LuaRuntime {
// Actual base Init starts a fresh NPC lifetime, even at a reused address.
void ResetNpcInitialization(std::uintptr_t entity) noexcept;
// Actual derived Init completion, before SpawnEx calls Room::AddEntity.
void DispatchNativeTearInit(std::uintptr_t tear) noexcept;
void DispatchNativeEffectInit(std::uintptr_t effect) noexcept;
void DispatchNativePickupInit(std::uintptr_t pickup) noexcept;
}
