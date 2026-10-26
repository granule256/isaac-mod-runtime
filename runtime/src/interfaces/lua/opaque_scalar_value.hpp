#pragma once
#include <type_traits>
#include "interfaces/lua/object_identity_registry.hpp"
#include "infrastructure/memory/engine_field_access.hpp"
extern "C" {
#include <lauxlib.h>
}
namespace isaac::runtime {
template<class T> std::uintptr_t OpaqueScalarIdentity(lua_State* L,int index) noexcept {
    return lua_rawlen(L,index)==sizeof(T)
        ?engine_memory::AddressOf(lua_touserdata(L,index)):0;
}
// PC LuaBridge把未公开枚举按值复制进userdata；不借用源对象，也不公开伪造的数值成员。
template<class T> void PushOpaqueScalarValue(lua_State* L,const char* metatable,const char* type,T value) {
    static_assert(std::is_integral_v<T>);
    *static_cast<T*>(lua_newuserdata(L,sizeof(T)))=value;
    if(luaL_newmetatable(L,metatable)) {
        if(!RegisterNativeObjectIdentity(L,-1,OpaqueScalarIdentity<T>))
            luaL_error(L,"enum native identity resolver conflicts");
        lua_pushstring(L,type);lua_setfield(L,-2,"__type");
        lua_pushstring(L,type);lua_setfield(L,-2,"__name");
        lua_pushvalue(L,-1);lua_setfield(L,-2,"__class");
    }
    lua_setmetatable(L,-2);
}
template<class T> T RequireOpaqueScalarValue(lua_State* L,int index,const char* metatable) {
    const auto* value=static_cast<const T*>(luaL_checkudata(L,index,metatable));
    if(lua_rawlen(L,index)!=sizeof(T))luaL_argerror(L,index,"invalid enum value size");
    return *value;
}
}
