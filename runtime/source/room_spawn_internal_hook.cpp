#include "room_spawn_internal_hook.hpp"
#include "lua_runtime.hpp"
#include "infrastructure/memory/engine_field_access.hpp"

namespace isaac::runtime {
namespace {
template<class T> T ReadRequired(std::uintptr_t base, std::uintptr_t offset) {
    T value{};
    if (!engine_memory::ReadField(base, offset, &value, engine_memory::EngineMemoryReadable))
        __builtin_trap();
    return value;
}
template<class T> void WriteRequired(std::uintptr_t base, std::uintptr_t offset, T value) {
    if (!engine_memory::WriteField(base, offset, value, engine_memory::EngineMemoryWritable))
        __builtin_trap();
}
}

std::uint32_t RoomSpawnInternalCallback(relay::InternalHookContext& context,
    const void* nativeBindings) noexcept {
    const auto& native = *static_cast<const RoomSpawnNativeBindings*>(nativeBindings);
    const auto entry = context.x[19];
    auto type = ReadRequired<std::int32_t>(entry, 0);
    auto variant = ReadRequired<std::uint16_t>(entry, 4);
    auto subType = ReadRequired<std::uint16_t>(entry, 6);
    // 1410原入口AA8的两条被覆盖指令；AB0/AB4保留供常规修正的五条原入边。
    // 普通9C8路径的1410早已被452998分到AA8，因此只会在特殊入口看到1410。
    if (type == 1410) {
        type = 33; variant = 1;
        WriteRequired(entry, 0, type);
        WriteRequired(entry, 4, variant);
    }
    const auto result = LuaRuntime::DispatchPreRoomEntitySpawnModifying(type, variant, subType,
        static_cast<std::uint32_t>(context.x[25]), static_cast<std::uint32_t>(context.x[23]));
    type = result.type; variant = result.variant; subType = result.subType;
    WriteRequired(entry, 0, type);
    WriteRequired(entry, 4, variant);
    WriteRequired(entry, 6, subType);
    // 搬移必要的301预处理；仍用同一个真实栈RNG、同一个原生ItemPool及原生函数。
    // 原9DC..A18：先写300，再Next，再GetCard(seed,false,true,true)，最后STRH。
    if (type == 5 && variant == 301) {
        WriteRequired(entry, 4, std::uint16_t{300});
        const auto game = ReadRequired<std::uintptr_t>(context.x[28], 0);
        const auto pool = engine_memory::FieldAddress(game, 0x242C0, 1, 0,
            engine_memory::EngineMemoryReadable);
        if (pool == 0 || context.x[29] < 0x10 || native.next == nullptr || native.getCard == nullptr)
            __builtin_trap();
        const auto seed = native.next(engine_memory::AsObject(context.x[29] - 0x10));
        const auto card = native.getCard(engine_memory::AsObject(pool), seed, false, true, true);
        WriteRequired(entry, 6, static_cast<std::uint16_t>(card));
    }
    // 原A14重新读取Type；即使helper/嵌套回调动了真实条目也不能沿用旧缓存。
    context.x[8] = static_cast<std::uint32_t>(ReadRequired<std::int32_t>(entry, 0));
    return result.present ? 1U : 0U;
}

std::uint32_t RoomFixSpawnCtorInternalCallback(relay::InternalHookContext& context,
    const void* nativeBindings) noexcept {
    const auto& native = *static_cast<const RoomSpawnNativeBindings*>(nativeBindings);
    if (context.x[29] < 0x10 || native.construct == nullptr || native.random == nullptr)
        __builtin_trap();
    void* rng = engine_memory::AsObject(context.x[29] - 0x10);
    // 原452974..984已把RNG/Seed/7放进x0/w1/w2；逐项核仍是同一真实输入。
    if (context.x[0] != context.x[29]-0x10 ||
        static_cast<std::uint32_t>(context.x[1]) != static_cast<std::uint32_t>(context.x[23]) ||
        static_cast<std::uint32_t>(context.x[2]) != 7) __builtin_trap();
    native.construct(rng, static_cast<std::uint32_t>(context.x[23]), 7);
    // 原298C/2994加载的是g_Game变量的地址（GOT槽中保存），不是Game对象本身。
    context.x[28] = ReadRequired<std::uintptr_t>(native.gameGotSlot, 0);
    const auto entry = context.x[19];
    if (ReadRequired<std::int32_t>(entry,0) == 1400) {
        WriteRequired(entry,0,std::int32_t{33});
        const auto value = native.random(rng,40);
        WriteRequired(entry,4,static_cast<std::uint16_t>(value == 0 ? 1 : 0));
    }
    // 1410由共享71桥先写33/1；原常规路径到AB0/AB4的入边从未改写。
    return RoomSpawnInternalCallback(context,nativeBindings);
}
} // namespace isaac::runtime
