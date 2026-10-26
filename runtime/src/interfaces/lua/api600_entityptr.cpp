#include "interfaces/lua/api600_entityptr.hpp"
#include "interfaces/lua/api600_entityptr.guards.hpp"
#include "infrastructure/call/engine_call_access.hpp"
#include "infrastructure/memory/engine_field_access.hpp"
#include <cstddef>
#include "interfaces/lua/isaac_api.hpp"
#include "interfaces/lua/field_api.hpp"
#include "interfaces/lua/entity_lifetime.hpp"
#include "interfaces/lua/class_metadata.hpp"
#include "interfaces/lua/object_identity_registry.hpp"
#include "lua_runtime.hpp"
#include "lua_object_handles.hpp"
#include <cstring>
extern "C" {
#include <lauxlib.h>
}
namespace isaac::runtime {
namespace {
constexpr char kPtr[]="IsaacRuntime.EntityPtr";
struct Ptr {std::uintptr_t entity,module;LuaRuntime::EntityLifetimeToken*lifetime;std::uintptr_t destroy;};
static_assert(offsetof(Ptr,entity)==0);
// 身份是交给原生SetReference的拥有弱引用槽；Ref清空/目标退役不销毁槽自身。
std::uintptr_t Identity(lua_State*L,int index) noexcept {
 return lua_rawlen(L,index)==sizeof(Ptr)?engine_memory::AddressOf(lua_touserdata(L,index)):0;
}
api100_native::Cache g_SetCache{},g_DestroyCache{};
#if !defined(__SWITCH__)
std::uintptr_t g_TestSet{},g_TestDestroy{};
#endif
using SetReferenceFn=void(*)(void*,void*);
using DestroyFn=void(*)(void*);
std::uintptr_t ResolveNative(lua_State* L,bool destroy) {
    std::uintptr_t host{};
#if !defined(__SWITCH__)
    host=destroy?g_TestDestroy:g_TestSet;
#endif
    return api100_native::Resolve(L,destroy?api600_entityptr::kDestroy:api600_entityptr::kSet,
                                   destroy?g_DestroyCache:g_SetCache,host);
}
int Gc(lua_State* L) {
    auto* p=static_cast<Ptr*>(luaL_testudata(L,1,kPtr));
    if (!p) return 0;
    // 析构地址在登记之前已经核对；GC路径不分配、不再执行会抛错的入口解析。
    if (p->entity && p->module==LuaRuntime::EngineModuleBase() &&
        EntityLifetimeAlive(p->lifetime) && p->destroy) {
        engine_call::AsFunction<DestroyFn>(p->destroy)(p);
    }
    *p={};
    return 0;
}
Ptr* Check(lua_State*L,int index=1){return static_cast<Ptr*>(luaL_checkudata(L,index,kPtr));}
void Set(lua_State*L,int target,int source){
 target=lua_absindex(L,target);source=lua_absindex(L,source);auto*p=Check(L,target);
 if(LuaRuntime::ClosingForModReload()&&!lua_isnil(L,source))
  luaL_error(L,"EntityPtr cannot register references during mod reload shutdown");
 // PC wrapper只把显式nil当空引用；缺参/错误类型仍经过Entity类型检查。
 const auto entity=lua_isnil(L,source)?0:ResolveEngineReceiver(L,FieldReceipt::Entity,source);
 LuaRuntime::EntityLifetimeToken*token{};
 if(entity)token=PushEntityLifetimeToken(L,entity);else lua_pushnil(L);
 // 原生ClearReferences先于D2清弱指针，不能只等lifetime的D2通知。
 const auto module=LuaRuntime::EngineModuleBase();
 if(p->module!=module||!EntityLifetimeAlive(p->lifetime))p->entity=0;
 if(p->entity||entity) {
  const auto set=engine_call::AsFunction<SetReferenceFn>(ResolveNative(L,false));
  const auto destroy=ResolveNative(L,true); // 在任何登记之前验证GC所需的释放入口。
  set(p,engine_memory::AsObject(entity));
  p->destroy=destroy;
 }
 p->module=module;p->lifetime=token;lua_setuservalue(L,target);
}
int Create(lua_State*L){
 if(LuaRuntime::ClosingForModReload()&&!lua_isnil(L,2))return luaL_error(L,"EntityPtr cannot register references during mod reload shutdown");
 const int source=2; // __call的第1格是类表，PC constructor855CB0同形。
 // 在push userdata前先检查缺参，避免新userdata占据本应缺失的第2格。
 if(lua_isnone(L,source))return luaL_argerror(L,source,"expected Entity or nil");
 auto*p=static_cast<Ptr*>(lua_newuserdata(L,sizeof(Ptr)));*p={};luaL_getmetatable(L,kPtr);lua_setmetatable(L,-2);const int target=lua_gettop(L);Set(L,target,source);return 1;
}
int Index(lua_State*L){const auto*p=Check(L);const auto*n=lua_tostring(L,2);
 if(n&&n[0]=='R'&&n[1]=='e'&&!std::strcmp(n,"Ref")){
  if(p->entity&&p->module==LuaRuntime::EngineModuleBase()&&p->lifetime&&EntityLifetimeAlive(p->lifetime)&&IsLiveEntityPointer(p->entity))PushEntityCallbackArgument(L,p->entity);else lua_pushnil(L);return 1;
 }
 if(n&&n[0]=='S'&&n[1]=='e'&&!std::strcmp(n,"SetReference")){lua_pushcfunction(L,Api600EntityPtrSetReference);return 1;}
 lua_pushnil(L);return 1;
}
int NewIndex(lua_State*L){static_cast<void>(Check(L));return luaL_error(L,"EntityPtr.Ref is read-only; use SetReference");}
}
int Api600EntityPtrConstructor(lua_State*L){return Create(L);}
int Api600EntityPtrSetReference(lua_State*L){static_cast<void>(Check(L));if(lua_isnone(L,2))return luaL_argerror(L,2,"expected Entity or nil");Set(L,1,2);return 0;}
void RegisterApi600EntityPtr(lua_State*L){luaL_newmetatable(L,kPtr);if(!RegisterNativeObjectIdentity(L,-1,Identity))luaL_error(L,"EntityPtr identity resolver conflicts");lua_pushcfunction(L,Index);lua_setfield(L,-2,"__index");lua_pushcfunction(L,NewIndex);lua_setfield(L,-2,"__newindex");lua_pushcfunction(L,Gc);lua_setfield(L,-2,"__gc");lua_newtable(L);lua_pushcfunction(L,Api600EntityPtrSetReference);lua_setfield(L,-2,"SetReference");lua_setfield(L,-2,"__methods");lua_pop(L,1);PublishNativeClass(L,"EntityPtr",kPtr);lua_getglobal(L,"EntityPtr");lua_getmetatable(L,-1);lua_pushcfunction(L,Api600EntityPtrConstructor);lua_setfield(L,-2,"__call");lua_pop(L,2);}
}

#if !defined(__SWITCH__)
namespace isaac::runtime {
void SetApi600EntityPtrNativeTestBindings(std::uintptr_t setReference,std::uintptr_t destroy) noexcept {
    g_TestSet=setReference;g_TestDestroy=destroy;g_SetCache={};g_DestroyCache={};
}
}
#endif
