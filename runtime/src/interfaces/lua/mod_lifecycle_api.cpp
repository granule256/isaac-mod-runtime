#include "interfaces/lua/mod_lifecycle_api.hpp"
#include "interfaces/lua/callback_table_api.hpp"
#include "interfaces/lua/api700_grid.hpp"
#include <cstring>
extern "C" {
#include <lauxlib.h>
}
namespace isaac::runtime {
namespace {
constexpr char kLoadedMods[] = "IsaacRuntime.LoadedModObjects";
void PushRecords(lua_State* state) {
    lua_getfield(state,LUA_REGISTRYINDEX,kLoadedMods);
    if (lua_istable(state,-1)) return;
    lua_pop(state,1);lua_newtable(state);lua_pushvalue(state,-1);
    lua_setfield(state,LUA_REGISTRYINDEX,kLoadedMods);
}
}
void TrackLoadedMod(lua_State* state,int mod,const char* root,bool embedded) {
    char callingRoot[1024]{};std::size_t callingLength{};
    if(CopyCallingModRoot(state,callingRoot,sizeof(callingRoot),&callingLength))root=callingRoot;
    mod=lua_absindex(state,mod);PushRecords(state);
    const auto next=static_cast<lua_Integer>(lua_rawlen(state,-1))+1;
    lua_createtable(state,3,0);
    lua_pushvalue(state,mod);lua_rawseti(state,-2,1);
    lua_pushstring(state,root?root:"");lua_rawseti(state,-2,2);
    lua_pushboolean(state,embedded);lua_rawseti(state,-2,3);
    lua_rawseti(state,-2,next);lua_pop(state,1);
}
namespace {
void CollectRecords(lua_State* state,int source,int pending,int keep,int seen,const char* root) {
    if(!lua_istable(state,source))return;
    const auto count=lua_rawlen(state,source);
    for(lua_Unsigned i=1;i<=count;++i) {
        lua_rawgeti(state,source,static_cast<lua_Integer>(i));const int entry=lua_gettop(state);
        if(!lua_istable(state,entry)){lua_pop(state,1);continue;}
        lua_rawgeti(state,entry,1);const int mod=lua_gettop(state);
        lua_pushvalue(state,mod);lua_rawget(state,seen);const bool exists=lua_toboolean(state,-1)!=0;lua_pop(state,1);
        if(!exists) {
            lua_pushvalue(state,mod);lua_pushboolean(state,1);lua_rawset(state,seen);
            lua_rawgeti(state,entry,3);const bool embedded=lua_toboolean(state,-1)!=0;lua_pop(state,1);
            bool selected=!embedded;
            if(root){lua_rawgeti(state,entry,2);const auto* path=lua_tostring(state,-1);selected=selected&&path&&!std::strcmp(path,root);lua_pop(state,1);}
            const int target=selected?pending:keep;
            lua_pushvalue(state,entry);lua_rawseti(state,target,static_cast<lua_Integer>(lua_rawlen(state,target))+1);
        }
        lua_pop(state,2);
    }
}
}
namespace {
int UnloadRecords(lua_State* state,const char* root) {
    PushRecords(state);const int loaded=lua_gettop(state);
    lua_getfield(state,LUA_REGISTRYINDEX,"IsaacRuntime.PendingModUnload");const int prior=lua_gettop(state);
    lua_newtable(state);const int pending=lua_gettop(state);
    lua_newtable(state);const int keep=lua_gettop(state);
    lua_newtable(state);const int seen=lua_gettop(state);
    CollectRecords(state,prior,pending,keep,seen,root);CollectRecords(state,loaded,pending,keep,seen,root);
    // 在任何模组回调前强持本代；OOM/回调错误后仍可追踪，不丢失未卸载对象。
    lua_pushvalue(state,pending);lua_setfield(state,LUA_REGISTRYINDEX,"IsaacRuntime.PendingModUnload");
    lua_pushvalue(state,keep);lua_setfield(state,LUA_REGISTRYINDEX,kLoadedMods);
    lua_pushnil(state);const int firstError=lua_gettop(state);
    const auto count=lua_rawlen(state,pending);
    for(lua_Unsigned i=1;i<=count;++i) {
        lua_rawgeti(state,pending,static_cast<lua_Integer>(i));const int entry=lua_gettop(state);
        PushModUnloader(state);lua_rawgeti(state,entry,1);
        if(lua_pcall(state,1,0,0)!=LUA_OK) {
            if(lua_isnil(state,firstError))lua_copy(state,-1,firstError);
            lua_pop(state,1); // 保留失败Mod；PC_UnloadMod抛错时本来就不会执行它的后续清理。
        } else {
            lua_rawgeti(state,entry,2);const auto* modRoot=lua_tostring(state,-1);
            if(modRoot&&*modRoot)RestorePressurePlateAnimationPins(state,modRoot);
            lua_pop(state,1);
            lua_pushboolean(state,0);lua_rawseti(state,pending,static_cast<lua_Integer>(i));
        }
        lua_pop(state,1);
    }
    RefreshCallbackDiagnostics(state);
    lua_pushboolean(state,lua_isnil(state,firstError));lua_pushvalue(state,firstError);
    return 2;
}

}
int UnloadTrackedMods(lua_State* state){return UnloadRecords(state,nullptr);}
int UnloadTrackedModRoot(lua_State* state){return UnloadRecords(state,luaL_checkstring(state,1));}

bool CopyCallingModRoot(lua_State* state,char* out,std::size_t capacity,std::size_t* length,const char* throughGlobal){
 constexpr char prefix[]="rom:/isaac_mods/mods/";
 lua_Debug frame{};
 int first=1;
 if(throughGlobal){
  // require/include可能被其它Mod用Lua适配器包裹；根属于适配器的调用者。
  // 比较函数身份而不是硬编码模组名，也不把RegisterMod归属改成最外层。
  const int top=lua_gettop(state);lua_getglobal(state,throughGlobal);const int global=lua_gettop(state);
  for(int level=0;lua_getstack(state,level,&frame);++level){
   if(!lua_getinfo(state,"f",&frame))continue;
   const bool same=lua_rawequal(state,global,-1);lua_pop(state,1);
   if(same){first=level+1;break;}
  }
  lua_settop(state,top);
 }
 for(int level=first;lua_getstack(state,level,&frame);++level){
  if(!lua_getinfo(state,"S",&frame)||!frame.source)continue;
  const char* source=frame.source;if(source[0]=='@')++source;
  if(std::strncmp(source,prefix,sizeof(prefix)-1))continue;
  const char* end=std::strchr(source+sizeof(prefix)-1,'/');if(!end)continue;
  const auto n=static_cast<std::size_t>(end-source);
  if(n>=capacity)return false;
  std::memcpy(out,source,n);out[n]=0;*length=n;return true;
 }
 return false;
}
namespace {
bool EqualName(const char* a,const char* b){
 if(!a||!b)return false;
 for(;;++a,++b){unsigned char x=*a,y=*b;if(x>='A'&&x<='Z')x+=32;if(y>='A'&&y<='Z')y+=32;if(x!=y)return false;if(!x)return true;}
}
constexpr char kRequireOwners[]="IsaacRuntime.RequireOwners";
}
int FindTrackedModRoot(lua_State* state){
 const auto* wanted=luaL_checkstring(state,1);PushRecords(state);const int loaded=lua_gettop(state);
 lua_getfield(state,LUA_REGISTRYINDEX,"IsaacRuntime.PendingModUnload");const int pending=lua_gettop(state);
 lua_pushnil(state);const int selected=lua_gettop(state);
 for(unsigned pass=0;pass<2;++pass){
  for(unsigned source=0;source<2;++source){
   const int records=source?pending:loaded;if(!lua_istable(state,records))continue;
   for(lua_Unsigned i=1;i<=lua_rawlen(state,records);++i){
   const int top=lua_gettop(state);lua_rawgeti(state,records,i);const int entry=lua_gettop(state);
   if(!lua_istable(state,entry)){lua_settop(state,top);continue;}
   lua_rawgeti(state,entry,3);const bool embedded=lua_toboolean(state,-1)!=0;lua_pop(state,1);
   lua_rawgeti(state,entry,2);const int rootIndex=lua_gettop(state);const auto* root=lua_tostring(state,rootIndex);
   if(embedded||!root||!*root){lua_settop(state,top);continue;}
   bool matches=false;
   if(pass==0){const auto* slash=std::strrchr(root,'/');matches=EqualName(slash?slash+1:root,wanted);}
   else{lua_rawgeti(state,entry,1);if(lua_istable(state,-1)){lua_getfield(state,-1,"Name");matches=EqualName(lua_tostring(state,-1),wanted);}}
   if(matches){
    if(!lua_isnil(state,selected)&&std::strcmp(lua_tostring(state,selected),root))return luaL_error(state,"luamod name is ambiguous; use its directory");
    lua_pushvalue(state,rootIndex);lua_copy(state,-1,selected);
   }
   lua_settop(state,top);
  }
  }
  if(!lua_isnil(state,selected)){lua_pushvalue(state,selected);return 1;}
 }
 return luaL_error(state,"luamod: loaded mod not found: %s",wanted);
}
void TrackRequiredModule(lua_State* state,const char* root,const char* name,int value){
 value=lua_absindex(state,value);luaL_getsubtable(state,LUA_REGISTRYINDEX,kRequireOwners);const int owners=lua_gettop(state);
 lua_getfield(state,owners,root);
 if(!lua_istable(state,-1)){lua_pop(state,1);lua_newtable(state);lua_pushvalue(state,-1);lua_setfield(state,owners,root);}
 lua_pushvalue(state,value);lua_setfield(state,-2,name);lua_pop(state,2);
}
void ClearTrackedRequireModules(lua_State* state,const char* root){
 const int top=lua_gettop(state);lua_getfield(state,LUA_REGISTRYINDEX,kRequireOwners);const int owners=lua_gettop(state);
 if(!lua_istable(state,owners)){lua_settop(state,top);return;}
 lua_getfield(state,owners,root);const int modules=lua_gettop(state);
 if(!lua_istable(state,modules)){lua_settop(state,top);return;}
 luaL_getsubtable(state,LUA_REGISTRYINDEX,"_LOADED");const int cache=lua_gettop(state);
 lua_pushnil(state);
 while(lua_next(state,modules)){
  lua_pushvalue(state,-2);lua_rawget(state,cache);const bool same=lua_rawequal(state,-1,-2);lua_pop(state,1);
  if(same){lua_pushvalue(state,-2);lua_pushnil(state);lua_rawset(state,cache);}
  lua_pop(state,1);
 }
 lua_pushnil(state);lua_setfield(state,owners,root);lua_settop(state,top);
}
}
