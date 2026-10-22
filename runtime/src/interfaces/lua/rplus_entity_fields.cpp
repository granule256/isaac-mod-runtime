#include "interfaces/lua/rplus_entity_fields.hpp"
#include "interfaces/lua/isaac_api.hpp"
#include "infrastructure/memory/engine_field_access.hpp"
#include "infrastructure/call/engine_call_access.hpp"
#include "runtime_constants.hpp"
#include "lua_runtime.hpp"
#include <cstring>
extern "C" {
#include <lauxlib.h>
}
namespace isaac::runtime {
namespace {
#if !defined(__SWITCH__)
RPlusEntityFieldNativeTestBindings g_TestFields{};
#endif
bool SupportedFieldName(const char* name,bool writing) noexcept {
    // 热路径：方法/普通字段在一字节分派后退出，不读取实体/虚表、不分类、不分配。
    switch(name[0]) {
        case 'T':return !std::strcmp(name,"TearFlags");
        case 'F':return !std::strcmp(name,"Flags")||!std::strcmp(name,"FallingSpeed")||!std::strcmp(name,"FallingAcceleration");
        case 'A':return !std::strcmp(name,"AutoUpdatePrice");
        case 'C':return !std::strcmp(name,"CollisionDamage");
        case 'P':return writing&&!std::strcmp(name,"ProjectileFlags");
        default:return false;
    }
}
std::uintptr_t FlagsOffset(CallbackEntityClass kind,const char* name) {
    if(kind==CallbackEntityClass::Bomb && std::strcmp(name,"Flags")==0)return kEntityBombTearFlagsOffset;
    if(std::strcmp(name,"TearFlags"))return 0;
    if(kind==CallbackEntityClass::Tear)return kEntityTearFlagsOffset;
    if(kind==CallbackEntityClass::Laser)return kEntityLaserTearFlagsOffset;
    if(kind==CallbackEntityClass::Knife)return kEntityKnifeTearFlagsOffset;
    return 0;
}
template<class T>T Read(lua_State* state,std::uintptr_t entity,std::uintptr_t offset) {
    T value{};if(!engine_memory::ReadField(entity,offset,&value,engine_memory::EngineMemoryReadable))
        luaL_error(state,"Entity field is no longer readable");
    return value;
}
template<class T>void Write(lua_State* state,std::uintptr_t entity,std::uintptr_t offset,T value) {
    if(!engine_memory::WriteField(entity,offset,value,engine_memory::EngineMemoryWritable))
        luaL_error(state,"Entity field is no longer writable");
}
std::uintptr_t FloatOffset(CallbackEntityClass kind,const char* field) {
    if(!std::strcmp(field,"CollisionDamage"))return kEntityCollisionDamageOffset;
    if(kind!=CallbackEntityClass::Tear&&kind!=CallbackEntityClass::Projectile)return 0;
    if(!std::strcmp(field,"FallingSpeed"))return kEntityTearFallingSpeedOffset;
    if(!std::strcmp(field,"FallingAcceleration"))return kEntityTearFallingAccelerationOffset;
    return 0;
}
}
#if !defined(__SWITCH__)
void SetRPlusEntityFieldNativeTestBindings(RPlusEntityFieldNativeTestBindings bindings) noexcept {g_TestFields=bindings;}
#endif
int TryPushRPlusEntityField(lua_State* state,std::uintptr_t entity,const char* field) {
    if(!SupportedFieldName(field,false))return 0;
    const auto kind=ClassifyCallbackEntity(entity);
    if(const auto offset=FlagsOffset(kind,field)) {
        PushBitSet128(state,Read<BitSet128Value>(state,entity,offset));return 1;
    }
    if(const auto offset=FloatOffset(kind,field)){lua_pushnumber(state,Read<float>(state,entity,offset));return 1;}
    if(kind==CallbackEntityClass::Pickup&&!std::strcmp(field,"AutoUpdatePrice")) {
        lua_pushboolean(state,Read<std::uint8_t>(state,entity,kEntityPickupAutoUpdatePriceOffset)!=0);return 1;
    }
    return 0;
}
bool TryWriteRPlusEntityField(lua_State* state,std::uintptr_t entity,const char* field) {
    if(!SupportedFieldName(field,true))return false;
    const auto kind=ClassifyCallbackEntity(entity);
    if(const auto offset=FlagsOffset(kind,field)) {
        BitSet128Value value{};if(!ReadBitSet128(state,3,&value))luaL_argerror(state,3,"BitSet128 expected");
        if(kind==CallbackEntityClass::Knife||kind==CallbackEntityClass::Laser){Write(state,entity,offset,value);return true;}
        using Fn=void(*)(void*,BitSet128Value);Fn fn=nullptr;
#if !defined(__SWITCH__)
        fn=kind==CallbackEntityClass::Tear?g_TestFields.tearFlags:g_TestFields.bombFlags;
#endif
        if(!fn){const auto entry=kind==CallbackEntityClass::Tear?kEntityTearSetTearFlagsOffset:kEntityBombSetTearFlagsOffset;
            const auto& guard=kind==CallbackEntityClass::Tear?kEntityTearSetTearFlagsExpectedBytes:kEntityBombSetTearFlagsExpectedBytes;
            const auto base=LuaRuntime::EngineModuleBase();
            if(!base||base>UINTPTR_MAX-entry||!engine_call::VerifyEntryBytes(base+entry,guard.data(),guard.size(),engine_memory::EngineMemoryReadable))
                luaL_error(state,"Entity flags native setter is unavailable");
            fn=engine_call::AsFunction<Fn>(base+entry);
        }
        fn(engine_memory::AsObject(entity),value);return true;
    }
    if(const auto offset=FloatOffset(kind,field)) {
        const auto value=static_cast<float>(luaL_checknumber(state,3));
        if(!std::strcmp(field,"CollisionDamage")) {
            using Fn=void(*)(void*,float);Fn fn=nullptr;
#if !defined(__SWITCH__)
            fn=g_TestFields.collisionDamage;
#endif
            if(!fn){const auto vtable=Read<std::uintptr_t>(state,entity,0);
                const auto target=Read<std::uintptr_t>(state,vtable,kEntitySetCollisionDamageVtableSlot);
                const auto base=LuaRuntime::EngineModuleBase();
                if(target!=base+kEntitySetCollisionDamageOffset && target!=base+kEntityTearSetCollisionDamageOffset)
                    luaL_error(state,"Entity.CollisionDamage virtual setter is unavailable");
                fn=engine_call::AsFunction<Fn>(target);
            }
            fn(engine_memory::AsObject(entity),value);
        }else Write(state,entity,offset,value);
        return true;
    }
    if(kind==CallbackEntityClass::Pickup&&!std::strcmp(field,"AutoUpdatePrice")) {
        Write(state,entity,kEntityPickupAutoUpdatePriceOffset,static_cast<std::uint8_t>(lua_toboolean(state,3)!=0));return true;
    }
    if(kind==CallbackEntityClass::Projectile&&!std::strcmp(field,"ProjectileFlags")) {
        Write(state,entity,kEntityProjectileFlagsOffset,static_cast<std::uint64_t>(luaL_checkinteger(state,3)));return true;
    }
    return false;
}
}
