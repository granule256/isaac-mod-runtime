#include "interfaces/lua/repentogon_entity_config_api.hpp"
#include "interfaces/lua/isaac_api.hpp"
#include "interfaces/lua/api500_config.hpp"
#include "interfaces/lua/owner_binding.hpp"
#include "infrastructure/call/engine_call_access.hpp"
#include "infrastructure/memory/engine_field_access.hpp"
#include "lua_runtime.hpp"
extern "C" {
#include <lauxlib.h>
}

namespace isaac::runtime {
namespace {
constexpr char kEntityMt[]="IsaacRuntime.EntityConfigEntity";
constexpr char kPlayerMt[]="IsaacRuntime.EntityConfigPlayer";
constexpr std::uint8_t kEntityGuard[]={0x0a,0x8c,0x40,0xf8,0x29,0x2c,0x0c,0x53,0xca,0x02,0x00,0xb4,0x28,0x21,0x02,0x2a};
constexpr std::uint8_t kPlayerGuard[]={0x81,0x01,0xf8,0x37,0x08,0xa4,0x41,0xa9,0x29,0x01,0x08,0xcb,0x29,0xfd,0x43,0xd3};
struct View {
    std::uintptr_t config{},record{},base{};
    std::int32_t type{};
    std::uint32_t variant{},subtype{};
};
#if !defined(__SWITCH__)
RepentogonEntityConfigNativeTestBindings g_Host{};
#endif
void Thread(lua_State* L) {
    if(!LuaRuntime::IsOnGameThread())luaL_error(L,"EntityConfig native access requires the game thread");
}
std::uintptr_t Config(lua_State* L) {
    Thread(L);
    const auto config=ResolveContentConfigRoot(true);
    if(!config)luaL_error(L,"EntityConfig is no longer available");
    return config;
}
std::uintptr_t Lookup(lua_State* L,std::uintptr_t config,std::int32_t type,
                       std::uint32_t variant,std::uint32_t subtype,bool player) {
    const auto base=LuaRuntime::EngineModuleBase();
    const auto offset=player?0x700ccU:0x68684U;
    if(!base||base>UINTPTR_MAX-offset-16||
       !engine_call::VerifyEntryBytes(base+offset,player?kPlayerGuard:kEntityGuard,16,
                                      engine_memory::EngineMemoryReadable))
        luaL_error(L,"EntityConfig native lookup guard mismatch");
    using EntityFn=void*(*)(void*,std::int32_t,std::uint32_t,std::uint32_t);
    using PlayerFn=void*(*)(void*,std::int32_t);
    auto entityFn=engine_call::AsFunction<EntityFn>(base+offset);
    auto playerFn=engine_call::AsFunction<PlayerFn>(base+offset);
#if !defined(__SWITCH__)
    entityFn=g_Host.getEntity;playerFn=g_Host.getPlayer;
    if((player&&!playerFn)||(!player&&!entityFn))luaL_error(L,"EntityConfig host lookup is unavailable");
#endif
    auto* self=engine_memory::AsObject(config);
    return engine_memory::AddressOf(player?playerFn(self,type):entityFn(self,type,variant,subtype));
}
std::uintptr_t Record(lua_State* L,bool player) {
    const auto config=Config(L);
    auto* view=static_cast<View*>(luaL_checkudata(L,1,player?kPlayerMt:kEntityMt));
    if(lua_rawlen(L,1)!=sizeof(View)||view->config!=config||view->base!=LuaRuntime::EngineModuleBase()||
       !view->record||Lookup(L,config,view->type,view->variant,view->subtype,player)!=view->record)
        luaL_error(L,"EntityConfig record is no longer available");
    return view->record;
}
int Push(lua_State* L,std::uintptr_t config,std::int32_t type,std::uint32_t variant,
         std::uint32_t subtype,bool player) {
    const auto record=Lookup(L,config,type,variant,subtype,player);
    if(!record){lua_pushnil(L);return 1;}
    if(!engine_memory::PointerUsable(record,engine_memory::EngineMemoryReadable))
        return luaL_error(L,"EntityConfig returned an unreadable record");
    auto* view=static_cast<View*>(lua_newuserdata(L,sizeof(View)));
    *view={config,record,LuaRuntime::EngineModuleBase(),type,variant,subtype};
    luaL_getmetatable(L,player?kPlayerMt:kEntityMt);lua_setmetatable(L,-2);return 1;
}
template<class T>T Read(lua_State* L,std::uintptr_t record,std::uintptr_t offset) {
    T value{};
    if(!engine_memory::ReadField(record,offset,&value,engine_memory::EngineMemoryReadable))
        luaL_error(L,"EntityConfig record field is unreadable");
    return value;
}
int Path(lua_State* L,std::uintptr_t offset) {
    const auto record=Record(L,true);
    if(record>UINTPTR_MAX-offset)return luaL_error(L,"EntityConfig path address is invalid");
    return Api500PushConfigString(L,record+offset);
}
void Metatable(lua_State* L,const char* name,const char* owner) {
    luaL_newmetatable(L,name);
    lua_pushstring(L,owner);lua_setfield(L,-2,"__type");
    lua_pushvalue(L,-1);lua_setfield(L,-2,"__class");
    lua_pushvalue(L,-1);lua_setfield(L,-2,"__index");
    static_cast<void>(AttachOwnerMethods(L,owner,nullptr,0));lua_pop(L,1);
}
}
void RegisterRepentogonEntityConfigViews(lua_State* L) {
    lua_getglobal(L,"EntityConfig");
    if(lua_isnil(L,-1)){lua_pop(L,1);lua_newtable(L);}
    if(!lua_istable(L,-1))luaL_error(L,"EntityConfig owner is not a table");
    static_cast<void>(AttachOwnerMethods(L,"EntityConfig",nullptr,0));lua_setglobal(L,"EntityConfig");
    Metatable(L,kEntityMt,"EntityConfigEntity");Metatable(L,kPlayerMt,"EntityConfigPlayer");
}
int RepentogonEntityConfigGetEntity(lua_State* L) {
    const auto config=Config(L);
    const auto type=static_cast<std::int32_t>(luaL_checkinteger(L,1));
    const auto variant=static_cast<std::uint32_t>(luaL_optinteger(L,2,-1));
    const auto subtype=static_cast<std::uint32_t>(luaL_optinteger(L,3,-1));
    return Push(L,config,type,variant,subtype,false);
}
int RepentogonEntityConfigGetPlayer(lua_State* L) {
    const auto config=Config(L);
    return Push(L,config,static_cast<std::int32_t>(luaL_checkinteger(L,1)),0,0,true);
}
// Load parses an Entity at sp+0x110 then assigns it unchanged to the config map.
int RepentogonEntityConfigEntityCanBeChampion(lua_State* L) {lua_pushboolean(L,Read<std::uint8_t>(L,Record(L,false),0x38)!=0);return 1;}
int RepentogonEntityConfigEntityGetStageHP(lua_State* L) {lua_pushnumber(L,Read<float>(L,Record(L,false),0x58));return 1;}
int RepentogonEntityConfigEntityGetCollisionRadius(lua_State* L) {lua_pushnumber(L,Read<float>(L,Record(L,false),0x3c));return 1;}
// LoadPlayers' sp+0x130 record: nameimage+0x20, portrait+0x38, extraportrait+0x80.
int RepentogonEntityConfigPlayerGetPortraitPath(lua_State* L) {return Path(L,0x38);}
int RepentogonEntityConfigPlayerGetExtraPortraitPath(lua_State* L) {return Path(L,0x80);}
int RepentogonEntityConfigPlayerGetNameImagePath(lua_State* L) {return Path(L,0x20);}
#if !defined(__SWITCH__)
void SetRepentogonEntityConfigNativeTestBindings(RepentogonEntityConfigNativeTestBindings value) noexcept {g_Host=value;}
#endif
}
