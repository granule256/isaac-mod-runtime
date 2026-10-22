#pragma once
#include "relay/internal_hook.hpp"
#include "ports/hook_port.hpp"
namespace isaac::runtime {
struct EntityRemoveNativeBindings {
    using BaseRemove = void (*)(void*);
    using RngDestroy = void (*)(void*);
    BaseRemove remove{};
    RngDestroy destroyRng{};
};
void RunEntityRemoveIntercept(const EntityRemoveNativeBindings*, void* entity) noexcept;
std::uint32_t EntityDestructorRemoveInternalCallback(relay::InternalHookContext&, const void*) noexcept;
Status InstallEntityRemovePointerHooks(const HookTarget&) noexcept;
}
