#include "interfaces/lua/callback_table_api.hpp"
#include "application/callback/callback_registry.hpp"
#include "interfaces/lua/mod_api.hpp"
#include "lua_runtime_state.hpp"
#include "program/callback_bootstrap.hpp"
#include <array>
extern "C" {
#include <lauxlib.h>
}
namespace isaac::runtime {
std::uint32_t g_CallbackDiagnosticViewIncomplete{0};
std::uint32_t g_CallbackDiagnosticViewOverflow{0};
namespace {
constexpr char kStateKey[]="IsaacRuntime.CallbackTableState";
struct TableState {int runRef;int tableRef;int ownerRunRef;int unloadRef;
    int functionSlots[CallbackRegistry::kCapacity];int modSlots[CallbackRegistry::kCapacity];};
std::array<std::uint32_t,3> g_BuiltinCallbackStates{};
TableState* State(lua_State* state) {
    lua_getfield(state,LUA_REGISTRYINDEX,kStateKey);
    auto* result=static_cast<TableState*>(lua_touserdata(state,-1));lua_pop(state,1);return result;
}
void RawField(lua_State* state,int index,const char* name) {
    index=lua_absindex(state,index);lua_pushstring(state,name);lua_rawget(state,index);
}
std::uint32_t Owner(lua_State* state,int index) {
    if(!lua_istable(state,index)||!lua_getmetatable(state,index))return 0;
    RawField(state,-1,"__handle");
    const auto* handle=static_cast<LuaRuntime::ModHandle*>(luaL_testudata(state,-1,LuaRuntime::kModMetatable));
    const auto owner=handle?handle->ownerPacked:0;lua_pop(state,2);return owner;
}
int RefreshDiagnostics(lua_State* state) {
    g_CallbackDiagnosticViewIncomplete=1;
    const auto* stored=State(state);if(!stored)return 0;
    if (lua_type(state, 1) == LUA_TNUMBER && lua_toboolean(state, 2)) {
        int integral = 0;
        const auto id = lua_tointegerx(state, 1, &integral);
        if (integral && id >= 0 && id <= kCallbackMaximumId) {
            RecordCallbackTableRegistration(static_cast<std::uint32_t>(id));
        }
    }
    auto& registry=LuaRuntime::ManagedCallbackRegistry();
    // 初始化已预留所有诊断引用槽；刷新只替换值，不新分配luaL_ref。
    for(std::size_t i=0;i<CallbackRegistry::kCapacity;++i) {
        lua_pushboolean(state,0);lua_rawseti(state,LUA_REGISTRYINDEX,stored->functionSlots[i]);
        lua_pushboolean(state,0);lua_rawseti(state,LUA_REGISTRYINDEX,stored->modSlots[i]);
    }
    registry.Reset();g_CallbackDiagnosticViewOverflow=0;
    lua_rawgeti(state,LUA_REGISTRYINDEX,stored->tableRef);const int all=lua_gettop(state);
    for(std::uint32_t id=0;id<=kCallbackMaximumId;++id) {
        lua_rawgeti(state,all,id);const int list=lua_gettop(state);
        if(!lua_istable(state,list)){lua_pop(state,1);continue;}
        for(lua_Integer i=1;;++i) {
            lua_rawgeti(state,list,i);if(lua_isnil(state,-1)){lua_pop(state,1);break;}
            const int entry=lua_gettop(state);
            if(!lua_istable(state,entry)){lua_pop(state,1);continue;}
            if(registry.Count()>=CallbackRegistry::kCapacity){++g_CallbackDiagnosticViewOverflow;lua_pop(state,1);continue;}
            RawField(state,entry,"Mod");const auto owner=Owner(state,-1);
            if(!owner){lua_pop(state,2);continue;}
            const auto slot=registry.Count();
            const int modRef=stored->modSlots[slot];lua_rawseti(state,LUA_REGISTRYINDEX,modRef);
            RawField(state,entry,"Function");
            if(!lua_isfunction(state,-1)){lua_pop(state,1);lua_pushboolean(state,0);lua_rawseti(state,LUA_REGISTRYINDEX,modRef);lua_pop(state,1);continue;}
            const int functionRef=stored->functionSlots[slot];lua_rawseti(state,LUA_REGISTRYINDEX,functionRef);
            RawField(state,entry,"Priority");
            const CallbackPriorityValue priority=lua_isinteger(state,-1)
                ? CallbackPriorityValue{static_cast<std::int64_t>(lua_tointeger(state,-1))}
                : CallbackPriorityValue{static_cast<double>(lua_tonumber(state,-1))};lua_pop(state,1);
            RawField(state,entry,"Param");
            const auto filter=lua_isinteger(state,-1)?static_cast<std::int64_t>(lua_tointeger(state,-1)):CallbackRegistry::kNoCallbackFilter;lua_pop(state,1);
            CallbackDescriptor d{};d.id=id;d.owner=LuaRuntime::UnpackModOwner(owner);
            d.affinity=ThreadAffinity::Any;d.luaReference=functionRef;d.modReference=modRef;
            if(!registry.Register(d,filter,priority).ok()) {
                lua_pushboolean(state,0);lua_rawseti(state,LUA_REGISTRYINDEX,functionRef);
                lua_pushboolean(state,0);lua_rawseti(state,LUA_REGISTRYINDEX,modRef);
                ++g_CallbackDiagnosticViewOverflow;
            }
            lua_pop(state,1);
        }
        lua_pop(state,1);
    }
    // 共享表可随时直接改；快照和整数Param视图永不冒称执行权威或完整统计。
    g_CallbackDiagnosticViewIncomplete=1;
    return 0;
}
int MatchOwner(lua_State* state) {
    lua_pushboolean(state,Owner(state,1)==static_cast<std::uint32_t>(luaL_checkinteger(state,2)));return 1;
}
}
bool BuiltinCallbackEnabled(std::uint32_t id) noexcept {
    return id<=kCallbackMaximumId&&(g_BuiltinCallbackStates[id>>5]&(std::uint32_t{1}<<(id&31)))!=0;
}
void ResetCallbackRuntimeState() noexcept {
    g_BuiltinCallbackStates={};
    g_CallbackDiagnosticViewIncomplete=0;
    g_CallbackDiagnosticViewOverflow=0;
}
int GetBuiltInCallbackState(lua_State* state) {
    const auto id=static_cast<std::uint32_t>(luaL_checkinteger(state,1));
    lua_pushboolean(state,BuiltinCallbackEnabled(id));return 1;
}
int SetBuiltInCallbackState(lua_State* state) {
    const bool enabled=lua_toboolean(state,2)!=0;
    const auto id=static_cast<std::uint32_t>(luaL_checkinteger(state,1));
    if(id<=kCallbackMaximumId) {
        const auto bit=std::uint32_t{1}<<(id&31);
        if(enabled)g_BuiltinCallbackStates[id>>5]|=bit;else g_BuiltinCallbackStates[id>>5]&=~bit;
    }
    return 0;
}
void RegisterCallbackBootstrap(lua_State* state,lua_CFunction invoke) {
    ResetCallbackRuntimeState();
    auto* stored=static_cast<TableState*>(lua_newuserdata(state,sizeof(TableState)));
    *stored={};stored->runRef=LUA_NOREF;stored->tableRef=LUA_NOREF;stored->ownerRunRef=LUA_NOREF;
    lua_setfield(state,LUA_REGISTRYINDEX,kStateKey);
    for(std::size_t i=0;i<CallbackRegistry::kCapacity;++i) {
        lua_pushboolean(state,0);stored->functionSlots[i]=luaL_ref(state,LUA_REGISTRYINDEX);
        lua_pushboolean(state,0);stored->modSlots[i]=luaL_ref(state,LUA_REGISTRYINDEX);
    }
    lua_getglobal(state,"Isaac");
    lua_pushcfunction(state,GetBuiltInCallbackState);lua_setfield(state,-2,"GetBuiltInCallbackState");
    lua_pushcfunction(state,SetBuiltInCallbackState);lua_setfield(state,-2,"SetBuiltInCallbackState");lua_pop(state,1);
    if(luaL_loadbuffer(state,kPcCallbackBootstrap,sizeof(kPcCallbackBootstrap)-1,"@pc/callbacks.lua")!=LUA_OK)lua_error(state);
    lua_pushcfunction(state,invoke);lua_pushcfunction(state,RefreshDiagnostics);lua_pushcfunction(state,MatchOwner);lua_call(state,3,4);
    lua_pushvalue(state,-4);stored->runRef=luaL_ref(state,LUA_REGISTRYINDEX);
    lua_pushvalue(state,-3);stored->tableRef=luaL_ref(state,LUA_REGISTRYINDEX);
    lua_pushvalue(state,-2);stored->unloadRef=luaL_ref(state,LUA_REGISTRYINDEX);
    lua_pushvalue(state,-1);stored->ownerRunRef=luaL_ref(state,LUA_REGISTRYINDEX);
    lua_pop(state,4);lua_pushnil(state);lua_setglobal(state,"_RunCallback");lua_pushnil(state);lua_setglobal(state,"_UnloadMod");
}
void PushCallbackRunner(lua_State* state, bool ownerOnly) {
    const auto* stored=State(state);if(stored)lua_rawgeti(state,LUA_REGISTRYINDEX,ownerOnly?stored->ownerRunRef:stored->runRef);else lua_pushnil(state);
}
void PushModUnloader(lua_State* state) {
    const auto* stored=State(state);
    if(stored)lua_rawgeti(state,LUA_REGISTRYINDEX,stored->unloadRef);else lua_pushnil(state);
}
void RefreshCallbackDiagnostics(lua_State* state) {
    static_cast<void>(RefreshDiagnostics(state));
}
int CallCallbackTableApi(lua_State* state,const char* name) {
    if(!State(state))return luaL_error(state,"PC callback table is not initialized");
    const int count=lua_gettop(state);lua_getglobal(state,"Isaac");lua_getfield(state,-1,name);lua_remove(state,-2);
    lua_insert(state,1);lua_call(state,count,LUA_MULTRET);return lua_gettop(state);
}
std::uint32_t CountLuaCallbacks(lua_State* state,std::uint32_t id) noexcept {
    if(!state||!lua_checkstack(state,3))return 0;
    const int top=lua_gettop(state);const auto* stored=State(state);
    if(!stored){lua_settop(state,top);return 0;}
    lua_rawgeti(state,LUA_REGISTRYINDEX,stored->tableRef);lua_rawgeti(state,-1,id);
    const auto count=lua_istable(state,-1)?static_cast<std::uint32_t>(lua_rawlen(state,-1)):0;
    lua_settop(state,top);return count;
}
}
