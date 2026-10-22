#pragma once

extern "C" {
#include <lua.h>
#include <lauxlib.h>
}

namespace isaac::runtime {
// PC类全局与实例使用同一个元表。仅初始化时复制原方法，供CHAPI保存后替换__index。
inline void CopyClassMethods(lua_State* state, int destination, int methods) {
    destination=lua_absindex(state,destination);methods=lua_absindex(state,methods);
    lua_pushnil(state);
    while(lua_next(state,methods)!=0) {
        lua_pushvalue(state,-2);lua_pushvalue(state,-2);lua_rawset(state,destination);
        lua_pop(state,1);
    }
}
inline void PublishNativeClass(lua_State* state,const char* name,const char* metatable,
                               const char* base=nullptr) {
    luaL_getmetatable(state,metatable);const int cls=lua_gettop(state);
    if(base) {
        luaL_getmetatable(state,base);lua_getfield(state,-1,"__methods");
        if(lua_istable(state,-1))CopyClassMethods(state,cls,-1);
        lua_pop(state,2);
    }
    lua_getfield(state,cls,"__methods");
    if(lua_istable(state,-1))CopyClassMethods(state,cls,-1);
    lua_pop(state,1);
    lua_pushstring(state,name);lua_setfield(state,cls,"__type");
    lua_pushvalue(state,cls);lua_setfield(state,cls,"__class");
    lua_getglobal(state,name);
    if(!lua_istable(state,-1)){lua_pop(state,1);lua_newtable(state);}
    lua_newtable(state);lua_pushvalue(state,cls);lua_setfield(state,-2,"__class");
    lua_setmetatable(state,-2);lua_setglobal(state,name);lua_pop(state,1);
}
// 没有字段的原生类同样提供可包装的函数__index，原方法表独立保留。
inline int NativeClassMethodIndex(lua_State* state) {
    if(!lua_getmetatable(state,1)){lua_pushnil(state);return 1;}
    lua_getfield(state,-1,"__methods");
    if(!lua_istable(state,-1)){lua_pushnil(state);return 1;}
    lua_pushvalue(state,2);lua_rawget(state,-2);return 1;
}
}
