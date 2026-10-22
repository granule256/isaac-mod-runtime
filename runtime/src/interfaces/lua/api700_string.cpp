#include "interfaces/lua/api700_string.hpp"
#include "interfaces/lua/api500_config.guards.hpp"
#include "interfaces/lua/api100_native.hpp"
#include "infrastructure/memory/engine_field_access.hpp"
#include "infrastructure/call/engine_call_access.hpp"
#include "lua_runtime.hpp"
#include <cstring>
#include <new>
extern "C" {
#include <lauxlib.h>
}
namespace isaac::runtime {
namespace {
constexpr char kTemp[]="IsaacRuntime.NativeStringInput";
struct Temp{alignas(8)unsigned char bytes[24]{};LuaRuntime::GameOperatorDeleteFn release{};};
api100_native::Cache g_AssignCache{};
#if !defined(__SWITCH__)
Api700StringAssign g_Assign{};
#endif
void Release(Temp*t){if(!t||!t->release)return;if(t->bytes[0]&1U){void*p{};std::memcpy(&p,t->bytes+16,8);if(p)t->release(p);}std::memset(t->bytes,0,24);t->release=nullptr;}
int Collect(lua_State*L){Release(static_cast<Temp*>(lua_touserdata(L,1)));return 0;}
}
#if !defined(__SWITCH__)
void SetApi700StringAssignForTesting(Api700StringAssign f)noexcept{g_Assign=f;}
#endif
void AssignApi700NativeString(lua_State*L,std::uintptr_t address,int index){
 std::size_t size{};const auto*text=luaL_checklstring(L,index,&size);
 struct Borrowed{std::uint64_t capacity,length;const char*data;};
 const Borrowed source{(static_cast<std::uint64_t>(size)+1U)|1U,size,text};
 if(!engine_memory::EngineMemoryWritable(address,24)){luaL_error(L,"native string destination is not writable");}
 std::uintptr_t host{};
#if !defined(__SWITCH__)
 host=engine_call::AddressOfFunction(g_Assign);
 if(!host){luaL_error(L,"native string assignment host binding unavailable");}
#endif
 const auto entry=api100_native::Resolve(L,{api500_config::kStringAssignOffset,api500_config::kStringAssignGuard.data()},g_AssignCache,host);
 engine_call::AsFunction<void*(*)(void*,const void*)>(entry)(engine_memory::AsObject(address),&source);
}
int WithApi700NativeString(lua_State*L,int index,Api700StringConsumer fn,void*context){
 index=lua_absindex(L,index);luaL_checklstring(L,index,nullptr);
 const auto release=LuaRuntime::GameOperatorDeleteThunk();
 if(!release){return luaL_error(L,"native string allocator is unavailable");}
 if(luaL_newmetatable(L,kTemp)){lua_pushcfunction(L,Collect);lua_setfield(L,-2,"__gc");}
 auto*t=new(lua_newuserdata(L,sizeof(Temp)))Temp{};const int owner=lua_gettop(L);
 lua_pushvalue(L,-2);lua_setmetatable(L,-2);lua_remove(L,-2);const int position=owner-1;t->release=release;
 AssignApi700NativeString(L,engine_memory::AddressOf(t->bytes),index);
 const int result=fn(L,t->bytes,context);Release(t);lua_remove(L,position);return result;
}
}
