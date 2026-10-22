#include "interfaces/lua/api600_entityptr.hpp"
#include "interfaces/lua/isaac_api.hpp"
#include "interfaces/lua/field_api.hpp"
#include "interfaces/lua/entity_lifetime.hpp"
#include "interfaces/lua/class_metadata.hpp"
#include "lua_runtime.hpp"
#include "lua_object_handles.hpp"
#include <cstring>
extern "C" {
#include <lauxlib.h>
}
namespace isaac::runtime {
namespace {
constexpr char kPtr[]="IsaacRuntime.EntityPtr";
struct Ptr {std::uintptr_t entity,module;LuaRuntime::EntityLifetimeToken*lifetime;};
Ptr* Check(lua_State*L,int index=1){return static_cast<Ptr*>(luaL_checkudata(L,index,kPtr));}
void Set(lua_State*L,int target,int source){
 target=lua_absindex(L,target);source=lua_absindex(L,source);auto*p=Check(L,target);
 // PC wrapper只把显式nil当空引用；缺参/错误类型仍经过Entity类型检查。
 const auto entity=lua_isnil(L,source)?0:ResolveEngineReceiver(L,FieldReceipt::Entity,source);
 LuaRuntime::EntityLifetimeToken*token{};
 if(entity)token=PushEntityLifetimeToken(L,entity);else lua_pushnil(L);
 // 分配成功后再替换旧身份，uservalue强持token防止GC/地址复用。
 *p={entity,LuaRuntime::EngineModuleBase(),token};lua_setuservalue(L,target);
}
int Create(lua_State*L){const int source=2; // __call的第1格是类表，PC constructor855CB0同形。
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
void RegisterApi600EntityPtr(lua_State*L){luaL_newmetatable(L,kPtr);lua_pushcfunction(L,Index);lua_setfield(L,-2,"__index");lua_pushcfunction(L,NewIndex);lua_setfield(L,-2,"__newindex");lua_newtable(L);lua_pushcfunction(L,Api600EntityPtrSetReference);lua_setfield(L,-2,"SetReference");lua_setfield(L,-2,"__methods");lua_pop(L,1);PublishNativeClass(L,"EntityPtr",kPtr);lua_getglobal(L,"EntityPtr");lua_getmetatable(L,-1);lua_pushcfunction(L,Api600EntityPtrConstructor);lua_setfield(L,-2,"__call");lua_pop(L,2);}
}
