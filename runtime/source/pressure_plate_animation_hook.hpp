#pragma once
#include "relay/internal_hook.hpp"
namespace isaac::runtime {
struct PressurePlateNativeBindings {void(*destroyRng)(std::uintptr_t){};};
std::uint32_t PressurePlateDestructorInternalCallback(relay::InternalHookContext&,const void*)noexcept;
void MarkPressurePlateDestructorHookInstalled(bool deleting)noexcept;
bool PressurePlateDestructorHooksReady()noexcept;
}
namespace LuaRuntime {void DispatchPressurePlateAnimationPinEvent(std::uintptr_t,bool)noexcept;}
