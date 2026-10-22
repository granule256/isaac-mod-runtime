#include "cold_callbacks_internal_hook.hpp"
#include "lua_runtime.hpp"
#include "runtime_constants.hpp"
#include "infrastructure/memory/engine_field_access.hpp"
namespace isaac::runtime {
std::uint32_t LevelCurseFirstRandomInternalCallback(relay::InternalHookContext& ctx,const void* user) noexcept {
    const auto& n=*static_cast<const ColdCallbackNativeBindings*>(user);
    if (n.random==nullptr) __builtin_trap();
    ctx.x[0]=n.random(engine_memory::AsObject(ctx.x[0]),static_cast<std::uint32_t>(ctx.x[1]));
    // 此BL仅可从PC相同资格路径到达；后续至common没有x21读写，callee-saved隔离嵌套。
    ctx.x[21]|=0x100000000ULL;
    return 0;
}
std::uint32_t LevelCurseEvaluateInternalCallback(relay::InternalHookContext& ctx,const void*) noexcept {
    const bool eligible=(ctx.x[21]&0x100000000ULL)!=0;
    ctx.x[21]&=0xffffffffULL;
    if (eligible) {
        std::uint32_t flags{};
        if (!engine_memory::ReadAt(ctx.x[19]+kLevelCursesOffset,&flags,engine_memory::EngineMemoryReadable)) __builtin_trap();
        flags=LuaRuntime::DispatchPostCurseEval(flags);
        if (!engine_memory::WriteAt(ctx.x[19]+kLevelCursesOffset,flags,engine_memory::EngineMemoryWritable)) __builtin_trap();
    }
    return 0; // gate+16真正重放LDR x9,[x24]，随后才本体追加特殊诅咒。
}
std::uint32_t PickupSelectionInternalCallback(relay::InternalHookContext& ctx,const void*) noexcept {
    if (ctx.x[29]<8) __builtin_trap();
    auto* variant=static_cast<std::uint32_t*>(engine_memory::AsObject(ctx.x[29]-4));
    auto* subtype=static_cast<std::uint32_t*>(engine_memory::AsObject(ctx.x[29]-8));
    if (!engine_memory::EngineMemoryReadable(ctx.x[29]-8,8)||
        !engine_memory::EngineMemoryWritable(ctx.x[29]-8,8)) __builtin_trap();
    LuaRuntime::DispatchPostPickupSelection(ctx.x[19],variant,subtype);
    ctx.x[20]=*variant; // PC在wrapper之后重读variant，不能沿用进入回调前的寄存器。
    return 0; // gate+16实际CMP重建NZCV，再续原conditional branch。
}
}
