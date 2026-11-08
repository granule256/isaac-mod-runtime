#include "interfaces/lua/repentogon_environment.hpp"

#include "application/callback/extended_callback_runtime.hpp"
#include "interfaces/lua/api_catalog.hpp"
#include "interfaces/lua/owner_binding.hpp"
#include <algorithm>
#include <cstring>
#include <limits>
#include <new>
#include <string_view>
extern "C" {
#include <lauxlib.h>
}

namespace isaac::runtime {
namespace {
lua_State* g_State{};
const RepentogonCatalog* g_Catalog{};
ExtendedCallbackState* g_CallbackStorage{};
bool* g_AttachedApis{};
std::size_t g_Initialized{};
bool g_Building{}, g_Active{};
constexpr char kOwnerTargets[]="IsaacRuntime.RepentogonOwnerTargets";

bool Text(const char* value) noexcept { return value&&value[0]; }
bool Same(const char* a,const char* b) noexcept { return a&&b&&!std::strcmp(a,b); }

// Numeric dotted versions, optionally followed by an alphabetic release suffix.
// Validate every component even when an earlier component decides the order.
bool VersionComponent(std::string_view& value,std::uint64_t& number) noexcept {
    number=0;
    if(value.empty()||value.front()<'0'||value.front()>'9')return false;
    do {
        const unsigned digit=static_cast<unsigned>(value.front()-'0');
        if(number>(std::numeric_limits<std::uint64_t>::max()-digit)/10)return false;
        number=number*10+digit;value.remove_prefix(1);
    } while(!value.empty()&&value.front()>='0'&&value.front()<='9');
    return true;
}
bool VersionCompare(std::string_view current,std::string_view target,int& order) noexcept {
    order=0;
    bool moreCurrent=true,moreTarget=true;
    while(moreCurrent||moreTarget) {
        std::uint64_t a{},b{};
        if((moreCurrent&&!VersionComponent(current,a))||(moreTarget&&!VersionComponent(target,b)))return false;
        if(!order&&a!=b)order=a>b?1:-1;
        moreCurrent=!current.empty()&&current.front()=='.';
        moreTarget=!target.empty()&&target.front()=='.';
        if(moreCurrent)current.remove_prefix(1);
        if(moreTarget)target.remove_prefix(1);
    }
    for(auto suffix:{current,target})for(char c:suffix)
        if(!((c>='a'&&c<='z')||(c>='A'&&c<='Z')))return false;
    if(!order&&!target.empty())order=current.compare(target);
    return true;
}
int MeetsVersion(lua_State* state) {
    std::size_t size{};const char* target=luaL_checklstring(state,1,&size);
    const char* current=lua_tostring(state,lua_upvalueindex(1));
    int order{};
    if(!VersionCompare(current,{target,size},order))return luaL_error(state,"invalid REPENTOGON version");
    lua_pushboolean(state,order>=0);return 1;
}

void Validate(lua_State* state,const RepentogonCatalog& catalog) {
    if(!catalog.batches)luaL_error(state,"REPENTOGON batch catalog is missing");
    if(catalog.identityVersion) {
        int order{};
        if(!VersionCompare(catalog.identityVersion,catalog.identityVersion,order))
            luaL_error(state,"invalid REPENTOGON baseline version");
    }
    const auto& base=ApiCatalog::Default();
    for(std::size_t i=0;i<catalog.count;++i) {
        const auto& batch=catalog.batches[i];
        if(!Text(batch.name)||(batch.apiCount&&!batch.apis)||
           (batch.enumCount&&!batch.enums)||(batch.callbackCount&&!batch.callbacks))
            luaL_error(state,"invalid REPENTOGON batch descriptor");
        if(batch.ready&&!batch.ready())luaL_error(state,"REPENTOGON prerequisites unavailable: %s",batch.name);
        for(std::size_t j=0;j<i;++j)if(Same(batch.name,catalog.batches[j].name))
            luaL_error(state,"duplicate REPENTOGON batch: %s",batch.name);
        for(std::size_t a=0;a<batch.apiCount;++a) {
            const auto& api=batch.apis[a];const auto& d=api.descriptor;
            const int implementations=(api.handler?1:0)+(api.field?1:0)+(api.method?1:0);
            if(!ApiCatalog{&d,1}.Validate().ok()||implementations!=1||base.Find(d.id)||
               (api.field&&api.field->id!=d.id)||(api.method&&api.method->id!=d.id)||
               (base.Find(d.owner,d.name)&&!api.replaceExisting))
                luaL_error(state,"invalid REPENTOGON API in %s",batch.name);
            for(std::size_t j=0;j<=i;++j) {
                const auto& other=catalog.batches[j];
                const auto count=j==i?a:other.apiCount;
                for(std::size_t b=0;b<count;++b) {
                    const auto& previous=other.apis[b].descriptor;
                    if(previous.id==d.id||(Same(previous.owner,d.owner)&&Same(previous.name,d.name)))
                        luaL_error(state,"duplicate REPENTOGON API: %s.%s",d.owner,d.name);
                }
            }
        }
        for(std::size_t a=0;a<batch.callbackCount;++a) {
            const auto& callback=batch.callbacks[a];
            if(callback.id<1000||!Text(callback.name))luaL_error(state,"invalid REPENTOGON callback");
            for(std::size_t j=0;j<=i;++j) {
                const auto& other=catalog.batches[j];
                const auto count=j==i?a:other.callbackCount;
                for(std::size_t b=0;b<count;++b)
                    if(other.callbacks[b].id==callback.id||Same(other.callbacks[b].name,callback.name))
                        luaL_error(state,"duplicate REPENTOGON callback: %s",callback.name);
            }
        }
    }
}

void PublishEnum(lua_State* state,const char* table,const char* name,lua_Integer value) {
    if(!Text(table)||!Text(name))luaL_error(state,"invalid REPENTOGON enum");
    lua_getglobal(state,table);
    if(lua_isnil(state,-1)) {lua_pop(state,1);lua_newtable(state);lua_pushvalue(state,-1);lua_setglobal(state,table);}
    if(!lua_istable(state,-1))luaL_error(state,"REPENTOGON enum owner is not a table: %s",table);
    lua_getfield(state,-1,name);
    if(!lua_isnil(state,-1))luaL_error(state,"duplicate REPENTOGON enum: %s.%s",table,name);
    lua_pop(state,1);lua_pushinteger(state,value);lua_setfield(state,-2,name);lua_pop(state,1);
}
const LuaApiDescriptor* FindDescriptor(std::uint32_t id) noexcept {
    if(!g_Catalog)return nullptr;
    for(std::size_t i=0;i<g_Catalog->count;++i) {
        const auto& batch=g_Catalog->batches[i];
        for(std::size_t j=0;j<batch.apiCount;++j)
            if(batch.apis[j].descriptor.id==id)return &batch.apis[j].descriptor;
    }
    return nullptr;
}
constexpr LuaApiExtension kApiExtension{AttachRepentogonOwnerMethods,FindDescriptor};

bool MatchesApi(lua_State* state,int index,const RepentogonApiBinding& api) {
    index=lua_absindex(state,index);
    if(!lua_iscfunction(state,index))return false;
    const auto expected=api.handler?api.handler:(api.field?FieldApiHandler:EngineMethodHandler);
    if(lua_tocfunction(state,index)!=expected) {
#if PERF_API_WRAPPER
        if(!lua_getupvalue(state,index,1))return false;
        const bool same=MatchesApi(state,-1,api);lua_pop(state,1);return same;
#else
        return false;
#endif
    }
    if(api.handler)return true;
    if(!lua_getupvalue(state,index,1))return false;
    const void* row=api.field?static_cast<const void*>(api.field):static_cast<const void*>(api.method);
    const bool same=lua_touserdata(state,-1)==row;lua_pop(state,1);return same;
}

void TrackOwner(lua_State* state,const char* owner) {
    const int target=lua_absindex(state,-1);
    lua_getfield(state,LUA_REGISTRYINDEX,kOwnerTargets);
    lua_getfield(state,-1,owner);
    if(lua_isnil(state,-1)) {
        lua_pop(state,1);lua_newtable(state);
        lua_newtable(state);lua_pushliteral(state,"k");lua_setfield(state,-2,"__mode");lua_setmetatable(state,-2);
        lua_pushvalue(state,-1);lua_setfield(state,-3,owner);
    }
    lua_pushvalue(state,target);lua_pushboolean(state,1);lua_rawset(state,-3);
    lua_pop(state,2);
}

void ReapplyOwnerBindings(lua_State* state) {
    lua_getfield(state,LUA_REGISTRYINDEX,kOwnerTargets);
    lua_pushnil(state);
    while(lua_next(state,-2)) {
        const char* owner=lua_tostring(state,-2);
        lua_pushnil(state);
        while(lua_next(state,-2)) {
            lua_pushvalue(state,-2);
            static_cast<void>(AttachRepentogonOwnerMethods(state,owner));
            lua_pop(state,2);
        }
        lua_pop(state,1);
    }
    lua_pop(state,1);
}
}

const RepentogonCatalog& DefaultRepentogonCatalog() noexcept {
    // Add independently restored batches here. Infrastructure alone must not
    // advertise an upstream version or send existing Mods into unsupported code.
    static constexpr RepentogonCatalog catalog{};
    return catalog;
}

void BeginRepentogonEnvironment(lua_State* state,bool requested,const RepentogonCatalog& catalog) {
    if(g_State)luaL_error(state,"REPENTOGON environment already belongs to a VM");
    g_State=state;g_Catalog=&catalog;
    if(!requested||!catalog.count)return;
    Validate(state,catalog);
    std::size_t count{},apiCount{};
    for(std::size_t i=0;i<catalog.count;++i) {
        if(catalog.batches[i].callbackCount>std::numeric_limits<std::size_t>::max()/sizeof(ExtendedCallbackState)-count)
            luaL_error(state,"REPENTOGON callback catalog is too large");
        count+=catalog.batches[i].callbackCount;
        if(catalog.batches[i].apiCount>std::numeric_limits<std::size_t>::max()-apiCount)
            luaL_error(state,"REPENTOGON API catalog is too large");
        apiCount+=catalog.batches[i].apiCount;
    }
    if(apiCount) {
        g_AttachedApis=new(std::nothrow) bool[apiCount]{};
        if(!g_AttachedApis)luaL_error(state,"cannot allocate REPENTOGON API state");
    }
    if(count) {
        g_CallbackStorage=new(std::nothrow) ExtendedCallbackState[count]{};
        if(!g_CallbackStorage)luaL_error(state,"cannot allocate REPENTOGON callback state");
        std::size_t index{};
        for(std::size_t i=0;i<catalog.count;++i)for(std::size_t j=0;j<catalog.batches[i].callbackCount;++j)
            g_CallbackStorage[index++].id=catalog.batches[i].callbacks[j].id;
        std::sort(g_CallbackStorage,g_CallbackStorage+count,[](const auto& a,const auto& b){return a.id<b.id;});
    }
    g_ExtendedCallbacks=g_CallbackStorage;g_ExtendedCallbackCount=count;
    lua_newtable(state);lua_setfield(state,LUA_REGISTRYINDEX,kOwnerTargets);
    g_LuaApiExtension=&kApiExtension;
    g_Building=true;
}

std::size_t AttachRepentogonOwnerMethods(lua_State* state,const char* owner) {
    if(state!=g_State||(!g_Building&&!g_Active))return 0;
    std::size_t attached{},index{};
    bool tracked{};
    for(std::size_t i=0;i<g_Catalog->count;++i) {
        const auto& batch=g_Catalog->batches[i];
        for(std::size_t j=0;j<batch.apiCount;++j,++index) {
            const auto& api=batch.apis[j];const auto& d=api.descriptor;
            if(!Same(d.owner,owner))continue;
            if(!tracked){TrackOwner(state,owner);tracked=true;}
            lua_getfield(state,-1,d.name);
            const bool exists=!lua_isnil(state,-1);
            const bool same=MatchesApi(state,-1,api);lua_pop(state,1);
            if(same){g_AttachedApis[index]=true;continue;}
            if(exists&&!api.replaceExisting)luaL_error(state,"REPENTOGON API would replace %s.%s",owner,d.name);
            if(api.handler)PushHandler(state,api.handler,0,d.id);
            else if(api.field) {
                lua_pushlightuserdata(state,const_cast<FieldApiRow*>(api.field));
                PushHandler(state,FieldApiHandler,1,d.id);
            } else {
                lua_pushlightuserdata(state,const_cast<EngineMethodRow*>(api.method));
                PushHandler(state,EngineMethodHandler,1,d.id);
            }
            lua_setfield(state,-2,d.name);g_AttachedApis[index]=true;++attached;
        }
    }
    return attached;
}

void CompleteRepentogonEnvironment(lua_State* state) {
    if(state!=g_State||!g_Building)return;
    for(std::size_t i=0;i<g_Catalog->count;++i) {
        const auto& batch=g_Catalog->batches[i];
        g_Initialized=i+1;
        for(std::size_t j=0;j<batch.enumCount;++j) {
            const auto& e=batch.enums[j];PublishEnum(state,e.table,e.name,e.value);
        }
        for(std::size_t j=0;j<batch.callbackCount;++j) {
            const auto& c=batch.callbacks[j];PublishEnum(state,"ModCallbacks",c.name,c.id);
        }
        if(batch.initialize){lua_pushcfunction(state,batch.initialize);lua_call(state,0,0);}
    }
    // Ordinary families may compose bindings after their first attachment.
    // Finish all registrations before enforcing explicit extension overrides.
    ReapplyOwnerBindings(state);
    std::size_t index{};
    for(std::size_t i=0;i<g_Catalog->count;++i) {
        const auto& batch=g_Catalog->batches[i];
        for(std::size_t j=0;j<batch.apiCount;++j,++index) {
            if(!g_AttachedApis[index])luaL_error(state,"REPENTOGON API owner was not registered: %s.%s",
                batch.apis[j].descriptor.owner,batch.apis[j].descriptor.name);
        }
    }
    if(g_Catalog->identityVersion) {
        lua_newtable(state);
        lua_pushliteral(state,"REPENTOGON");lua_setfield(state,-2,"Name");
        lua_pushstring(state,g_Catalog->identityVersion);lua_setfield(state,-2,"Version");
        lua_pushstring(state,g_Catalog->identityVersion);lua_pushcclosure(state,MeetsVersion,1);lua_setfield(state,-2,"MeetsVersion");
        lua_setglobal(state,"REPENTOGON");
    }
    g_Building=false;g_Active=true;g_ExtendedCallbackDelivery=true;
}

void SuspendRepentogonEnvironment(lua_State* state) noexcept {
    if(state!=g_State)return;
    g_Active=false;g_Building=false;g_ExtendedCallbackDelivery=false;
}
void EndRepentogonEnvironment(lua_State* state) noexcept {
    if(state!=g_State)return;
    SuspendRepentogonEnvironment(state);
    while(g_Initialized) {
        const auto& batch=g_Catalog->batches[--g_Initialized];
        if(batch.reset)batch.reset();
    }
    g_ExtendedCallbacks=nullptr;g_ExtendedCallbackCount=0;
    delete[] g_CallbackStorage;g_CallbackStorage=nullptr;
    delete[] g_AttachedApis;g_AttachedApis=nullptr;
    g_State=nullptr;g_Catalog=nullptr;
    g_LuaApiExtension=nullptr;
}
bool RepentogonEnvironmentActive() noexcept {return g_Active;}

} // namespace isaac::runtime
