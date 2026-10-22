#include "pressure_plate_animation_hook.hpp"
#include "infrastructure/relay/entry_relay_binding.hpp"
#include <atomic>
#include "infrastructure/memory/engine_field_access.hpp"
namespace isaac::runtime {
namespace {std::atomic<std::uint32_t> g_DestructorMask{};}
void MarkPressurePlateDestructorHookInstalled(bool deleting)noexcept{
 g_DestructorMask.fetch_or(deleting?2U:1U,std::memory_order_release);
}
bool PressurePlateDestructorHooksReady()noexcept{
 return g_DestructorMask.load(std::memory_order_acquire)==3;
}
std::uint32_t PressurePlateDestructorInternalCallback(relay::InternalHookContext&ctx,const void*user)noexcept{
 const auto* native=static_cast<const PressurePlateNativeBindings*>(user);
 LuaRuntime::DispatchPressurePlateAnimationPinEvent(ctx.x[19],true);
 native->destroyRng(ctx.x[0]);return 0;
}
}
extern "C" void EntryRelayPressurePlateAnimationCallback(void* grid,bool instant){
 using Original=void(*)(void*,bool);
 isaac::runtime::Original<Original>(isaac::runtime::HookId::PressurePlateAnimationWriter)(grid,instant);
 LuaRuntime::DispatchPressurePlateAnimationPinEvent(isaac::runtime::engine_memory::AddressOf(grid),false);
}
