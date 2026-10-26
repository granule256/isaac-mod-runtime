#pragma once
#include "domain/callback/use_item_scope.hpp"
#include "relay/internal_hook.hpp"
namespace isaac::runtime {
struct UseItemNativeBoundaryBinding { bool defaultDischarge{};bool reloadCacheFlags{}; };
enum class UseItemAnimationEvent { TammyLaser, FlipReplace };
struct UseItemAnimationEventBinding {
    std::uintptr_t original{}, resume{};
    UseItemAnimationEvent event{};
};
std::uint32_t UseItemAnimationEventCallback(relay::InternalHookContext&,const void*) noexcept;
// 只能由游戏线程维护；其它线程不得读取或改写这条栈链。
UseItemCallFrame*& ActiveUseItemFrame() noexcept;
std::uint32_t UseItemNativeBoundaryCallback(relay::InternalHookContext&,const void*) noexcept;
}

// 调用点资格依赖原始LR；禁止把此入口内联到其它调用者。
extern "C" void EntryRelayUseCardCallback(void*,std::uint32_t,std::uint32_t) __attribute__((noinline));
