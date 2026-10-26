#include "interfaces/lua/object_pointer_identity.hpp"
#include "interfaces/lua/isaac_api.hpp"
#include "interfaces/lua/object_identity_registry.hpp"
#include "interfaces/lua/font_api.hpp"
#include "interfaces/lua/bitset128_api.hpp"
#include "interfaces/lua/field_api.hpp"
#include "interfaces/lua/remaining_api.hpp"
#include "interfaces/lua/rng_api.hpp"
#include "interfaces/lua/sprite_api.hpp"
#include "infrastructure/memory/engine_field_access.hpp"
#include "lua_object_handles.hpp"
#include "runtime_constants.hpp"
#include <cstddef>
extern "C" {
#include <lauxlib.h>
}

namespace isaac::runtime {
namespace {
std::uintptr_t ReadableIdentity(std::uintptr_t address) noexcept {
    return address && engine_memory::EngineMemoryReadable(address,1)?address:0;
}
struct CurrentObject {
    const char* metatable;
    FieldReceipt receipt;
    std::uintptr_t offset;
};
// 占位句柄不含原生指针，必须与公开方法共用当前对象解析，不能读userdata首字。
constexpr CurrentObject kCurrentObjects[]{
    {LuaRuntime::kGameMetatable,FieldReceipt::Level,0},
    {LuaRuntime::kLevelMetatable,FieldReceipt::Level,0},
    {LuaRuntime::kRoomMetatable,FieldReceipt::Room,0},
    {LuaRuntime::kSeedsMetatable,FieldReceipt::Seeds,0},
    {LuaRuntime::kItemPoolMetatable,FieldReceipt::ItemPool,0},
    {LuaRuntime::kMusicMetatable,FieldReceipt::Music,0},
    {LuaRuntime::kHudMetatable,FieldReceipt::Level,kGameHudObjectOffset},
};
template<FieldReceipt Receipt,std::uintptr_t Offset=0,std::size_t Minimum=1>
std::uintptr_t ReceiverIdentity(lua_State* state,int index) noexcept {
    if(lua_rawlen(state,index)<Minimum)return 0;
    const auto address=ResolveEngineReceiver(state,Receipt,index);
    return address && address<=UINTPTR_MAX-Offset?ReadableIdentity(address+Offset):0;
}
template<class Value> std::uintptr_t OwnedValueIdentity(lua_State* state,int index) noexcept {
    // 这里是对象自有值的存储，不是借用对象包装头；不解引用其第一字、也不造地址缓存。
    return lua_rawlen(state,index)==sizeof(Value)?engine_memory::AddressOf(lua_touserdata(state,index)):0;
}
std::uintptr_t FontIdentity(lua_State* state,int index) noexcept {
    return engine_memory::AddressOf(TryResolveFontArgument(state,index));
}
std::uintptr_t RngIdentity(lua_State* state,int index) noexcept {
    if(lua_rawlen(state,index)<sizeof(LuaRuntime::RngHandle))return 0;
    return engine_memory::AddressOf(TryResolveRngObject(
        static_cast<LuaRuntime::RngHandle*>(lua_touserdata(state,index)),false));
}
std::uintptr_t SpriteIdentity(lua_State* state,int index) noexcept {
    return engine_memory::AddressOf(TryResolveSpriteArgument(state,index));
}
void RegisterIdentity(lua_State* state,const char* metatable,NativeObjectIdentityResolver resolver) {
    luaL_getmetatable(state,metatable);
    if(lua_istable(state,-1) && !RegisterNativeObjectIdentity(state,-1,resolver))
        luaL_error(state,"native identity resolver conflicts for %s",metatable);
    lua_pop(state,1);
}

}

void RegisterCoreObjectPointerIdentities(lua_State* state) {
    using namespace LuaRuntime;
    RegisterIdentity(state,kGameMetatable,&ReceiverIdentity<FieldReceipt::Level>);
    RegisterIdentity(state,kLevelMetatable,&ReceiverIdentity<FieldReceipt::Level>);
    RegisterIdentity(state,kRoomMetatable,&ReceiverIdentity<FieldReceipt::Room>);
    RegisterIdentity(state,kSeedsMetatable,&ReceiverIdentity<FieldReceipt::Seeds>);
    RegisterIdentity(state,kItemPoolMetatable,&ReceiverIdentity<FieldReceipt::ItemPool>);
    RegisterIdentity(state,kMusicMetatable,&ReceiverIdentity<FieldReceipt::Music>);
    RegisterIdentity(state,"IsaacRuntime.SFXManager",&ReceiverIdentity<FieldReceipt::Music,
        kManagerSoundEffectsOffset-kManagerMusicOffset,sizeof(int)>);
    RegisterIdentity(state,kHudMetatable,&ReceiverIdentity<FieldReceipt::Level,kGameHudObjectOffset>);
    RegisterIdentity(state,kGridEntityMetatable,&ReceiverIdentity<FieldReceipt::GridEntity,0,sizeof(GridEntityHandle)>);
    RegisterIdentity(state,kGridEntityDoorMetatable,&ReceiverIdentity<FieldReceipt::GridEntity,0,sizeof(DoorHandle)>);
    RegisterIdentity(state,kPathFinderMetatable,&ReceiverIdentity<FieldReceipt::PathFinder,0,sizeof(PathFinderHandle)>);
    RegisterIdentity(state,kTemporaryEffectsMetatable,&ReceiverIdentity<FieldReceipt::TemporaryEffects,0,sizeof(TemporaryEffectsHandle)>);
    RegisterIdentity(state,kItemConfigItemMetatable,&ReceiverIdentity<FieldReceipt::ItemConfigItem,0,sizeof(ItemConfigItemHandle)>);
    RegisterIdentity(state,kVectorMetatable,&OwnedValueIdentity<VectorHandle>);
    RegisterIdentity(state,kColorMetatable,&OwnedValueIdentity<ColorHandle>);
    RegisterIdentity(state,kEntityRefMetatable,&OwnedValueIdentity<EntityRefHandle>);
    RegisterIdentity(state,kBitSet128Metatable,&OwnedValueIdentity<BitSet128Value>);
    RegisterIdentity(state,kFontMetatable,&FontIdentity);
    RegisterIdentity(state,kRngMetatable,&RngIdentity);
    RegisterIdentity(state,kSpriteMetatable,&SpriteIdentity);
}

std::uintptr_t ResolveNonEntityPointerIdentity(lua_State* state,int index) noexcept {
    // 保持既有描述符快路径；失效描述符也在本族收口，不继续扫其它对象类型。
    const auto descriptor=ResolveRoomDescriptorArgument(state,index);
    if (descriptor || luaL_testudata(state,index,LuaRuntime::kRoomDescriptorMetatable)) return descriptor;
    bool recognized{};
    const auto registered=ResolveRegisteredObjectIdentity(state,index,&recognized);
    if(recognized)return registered;
    // 保留旧局部注册宿主的解析路径；正式初始化已逐类登记，不在热查询循环类型。
    for (const auto& row:kCurrentObjects) {
        if (!luaL_testudata(state,index,row.metatable)) continue;
        const auto address=ResolveEngineReceiver(state,row.receipt,index);
        if (!address || address>UINTPTR_MAX-row.offset) return 0;
        return ReadableIdentity(address+row.offset);
    }
    if (auto* rng=static_cast<LuaRuntime::RngHandle*>(luaL_testudata(state,index,LuaRuntime::kRngMetatable))) {
        if (lua_rawlen(state,index)<sizeof(LuaRuntime::RngHandle)) return 0;
        return engine_memory::AddressOf(TryResolveRngObject(rng,false));
    }
    if (luaL_testudata(state,index,LuaRuntime::kSpriteMetatable)) {
        return engine_memory::AddressOf(TryResolveSpriteArgument(state,index));
    }
    return 0;
}
}
