#include "interfaces/lua/api100_strings.hpp"
#include "interfaces/lua/api100_native.hpp"
#include "interfaces/lua/api100_strings.guards.hpp"
#include "interfaces/lua/isaac_api.hpp"
#include "interfaces/lua/field_api.hpp"
#include "infrastructure/memory/engine_field_access.hpp"
#include "infrastructure/call/engine_call_access.hpp"
#include "lua_runtime.hpp"
#include "lua_runtime_state.hpp"
#include "lua_object_handles.hpp"
#include <cstring>
#include <new>
#include <type_traits>
extern "C" {
#include <lauxlib.h>
}
namespace isaac::runtime {
Api100NativeString::Api100NativeString(const Api100NativeString& other)noexcept{std::memcpy(bytes,other.bytes,24);}
namespace {
constexpr char kResultMetatable[]="IsaacRuntime.NativeStringResult";
struct Result {Api100NativeString value;LuaRuntime::GameOperatorDeleteFn release;};
using Cache=api100_native::Cache;
Cache g_Cache[2]{};
#if !defined(__SWITCH__)
Api100StringNativeTestBindings g_Tests{};
#endif
void Release(Result* result)noexcept{
 if(!result||!result->release)return;
 if(result->value.bytes[0]&1U){void* p=nullptr;std::memcpy(&p,result->value.bytes+16,8);if(p)result->release(p);}
 std::memset(result->value.bytes,0,24);result->release=nullptr;
}
int Collect(lua_State*state){Release(static_cast<Result*>(lua_touserdata(state,1)));return 0;}
int Read(lua_State*state,unsigned index){
 luaL_checkudata(state,1,LuaRuntime::kLevelMetatable);
 auto receiver=ResolveEngineReceiver(state,FieldReceipt::Level,1);
 if(!receiver)return luaL_error(state,"Level reference is no longer available");
 namespace guards=api100_strings;
 const auto offset=index==0?guards::kGetNameEntry:guards::kGetCurseNameEntry;
 const auto* bytes=index==0?guards::kGetNameGuard.data():guards::kGetCurseNameGuard.data();
 std::uintptr_t host{};
#if !defined(__SWITCH__)
 host=index==0?g_Tests.getName:g_Tests.getCurseName;
#endif
 const auto entry=api100_native::Resolve(state,{offset,bytes},g_Cache[index],host);
 return PushApi100NativeStringResult(state,engine_call::AsFunction<Api100NativeStringCallback>(entry),engine_memory::AsObject(receiver));
}
}
int PushApi100NativeStringResult(lua_State*state,Api100NativeStringCallback fn,void*context){
 // Acquire the engine allocator before creating a string. A missing release path must not leak.
 const auto release=LuaRuntime::GameOperatorDeleteThunk();
 if(!release)return luaL_error(state,"Level string native allocator is unavailable");
 // Attach __gc before the native allocation; lua_pushlstring may longjmp on OOM.
 if(luaL_newmetatable(state,kResultMetatable)){lua_pushcfunction(state,Collect);lua_setfield(state,-2,"__gc");}
 auto*result=new(lua_newuserdata(state,sizeof(Result))) Result{};
 lua_pushvalue(state,-2);lua_setmetatable(state,-2);lua_remove(state,-2);
 result->release=release;
 new(&result->value) Api100NativeString(fn(context));
 EngineStringView view{};
 if(!ResolveEngineStringView(engine_memory::AddressOf(result->value.bytes),&view)){
  Release(result);return luaL_error(state,"Level returned an invalid native string");
 }
 lua_pushlstring(state,view.size?static_cast<const char*>(engine_memory::AsObject(view.data)):"",view.size);
 Release(result);lua_remove(state,-2);return 1;
}

#if !defined(__SWITCH__)
void SetApi100StringNativeTestBindings(Api100StringNativeTestBindings value)noexcept{g_Tests=value;}
#endif
int Api100LevelGetName(lua_State*state){return Read(state,0);}
int Api100LevelGetCurseName(lua_State*state){return Read(state,1);}
}
