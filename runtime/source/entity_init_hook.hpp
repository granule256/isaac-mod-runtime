#pragma once
#include <cstdint>

namespace isaac::runtime {
enum class HookId : std::uint8_t;
struct HookTarget;
class Status;
enum class NativeEntityInitKind { Base, Tear, Effect };
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
// Actual derived Init completion, before SpawnEx calls Room::AddEntity.
void DispatchNativeTearInit(std::uintptr_t tear) noexcept;
void DispatchNativeEffectInit(std::uintptr_t effect) noexcept;
}
