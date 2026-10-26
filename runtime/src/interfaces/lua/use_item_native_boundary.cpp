#include "use_item_internal_hook.hpp"
#include "lua_runtime.hpp"
#include "infrastructure/call/engine_call_access.hpp"
#include "infrastructure/memory/engine_field_access.hpp"
namespace isaac::runtime {
namespace { UseItemCallFrame* g_ActiveUseItemFrame{}; }
UseItemCallFrame*& ActiveUseItemFrame() noexcept { return g_ActiveUseItemFrame; }
std::uint32_t UseItemNativeBoundaryCallback(relay::InternalHookContext& ctx,const void* opaque) noexcept {
    if (!LuaRuntime::IsOnGameThread()) return 0;
    auto* frame=ActiveUseItemFrame();
    if (!TryClaimUseItemBoundary(frame,ctx.x[27])) return 0;
    const auto& binding=*static_cast<const UseItemNativeBoundaryBinding*>(opaque);
    const auto native=(ctx.x[20]&1U)<<8 | static_cast<std::uint64_t>(binding.defaultDischarge);
    const auto outcome=LuaRuntime::DispatchUseItemAtNativeBoundary(frame->player,frame->postItem,
        static_cast<std::int32_t>(frame->flags),frame->slot,frame->custom,native,frame->animationAllowed);
    const auto result=outcome.Apply(native);
    // 317318这条特殊路径在回调前已载入CacheFlags，PC则在回调后才读。
    // 其它四条路径由原生LDR重读，不增加重复工作。
    if(binding.reloadCacheFlags){
        std::uint32_t flags{};
        if(!engine_memory::ReadAt(ctx.x[23]+0x54,&flags,engine_memory::EngineMemoryReadable))__builtin_trap();
        ctx.x[8]=flags;
    }
    // PC先消费回调及内部Remove，再判断最新ItemState；不可沿用回调前寄存器。
    std::uint32_t itemState{};
    if (!engine_memory::ReadAt(frame->player+0x19d4,&itemState,engine_memory::EngineMemoryReadable)) __builtin_trap();
    ctx.x[20]=(result>>8)&1U;
    ctx.x[22]=(result&1U)!=0 && (itemState==0 || itemState==47);
    return 0;
}
std::uint32_t UseItemAnimationEventCallback(relay::InternalHookContext& ctx,const void* opaque) noexcept {
    const auto& native=*static_cast<const UseItemAnimationEventBinding*>(opaque);
    if (LuaRuntime::IsOnGameThread()) {
        auto* frame=ActiveUseItemFrame();
        if (frame && !frame->dispatched) {
            if (native.event==UseItemAnimationEvent::TammyLaser && frame->item==38 && frame->player==ctx.x[27])
                frame->animationAllowed=false;
            if (native.event==UseItemAnimationEvent::FlipReplace && frame->item==711 &&
                frame->player==ctx.x[1] && ctx.x[20]!=0)
                frame->animationAllowed=false;
        }
    }
    // 两个点都替换void BL，原生参数及副作用不能省掉；续接不消费volatile返回值。
    if (native.event==UseItemAnimationEvent::TammyLaser) {
        using Fn=void(*)(std::uintptr_t,std::int32_t);
        engine_call::AsFunction<Fn>(native.original)(ctx.x[0],static_cast<std::int32_t>(ctx.x[1]));
    } else {
        using Fn=void(*)(std::uintptr_t,std::uintptr_t,std::uintptr_t);
        engine_call::AsFunction<Fn>(native.original)(ctx.x[0],ctx.x[1],ctx.x[2]);
    }
    ctx.x[30]=native.resume;
    return 0;
}
}
