#include "interfaces/lua/api100_core.hpp"
#include "interfaces/lua/api100_native.hpp"
#include "interfaces/lua/api100_core.guards.hpp"
#include "interfaces/lua/isaac_api.hpp"
#include "interfaces/lua/field_api.hpp"
#include "infrastructure/memory/engine_field_access.hpp"
#include "infrastructure/call/engine_call_access.hpp"
#include "lua_runtime.hpp"
#include <cstring>
extern "C" {
#include <lauxlib.h>
}
namespace isaac::runtime {
namespace {
namespace guards=api100_core;
using Entry=api100_native::Entry;
constexpr Entry kEntries[]={
{guards::kBloodExplodeEntry,guards::kBloodExplodeGuard.data()},
{guards::kGetLastParentEntry,guards::kGetLastParentGuard.data()},
{guards::kGetLastChildEntry,guards::kGetLastChildGuard.data()},
{guards::kHasFullHealthEntry,guards::kHasFullHealthGuard.data()},
{guards::kIsFrameEntry,guards::kIsFrameGuard.data()},
};
using Cache=api100_native::Cache;Cache g_Cache[5]{};
#if !defined(__SWITCH__)
Api100CoreNativeTestBindings g_Tests{};
#endif
void* Entity(lua_State*state){auto p=ResolveEngineReceiver(state,FieldReceipt::Entity,1);if(!p)luaL_error(state,"Entity reference is no longer available");return engine_memory::AsObject(p);}
std::int32_t Integer(lua_State*state,int index){const auto bits=static_cast<std::uint32_t>(luaL_checkinteger(state,index));std::int32_t value{};std::memcpy(&value,&bits,4);return value;}
template<class Fn>Fn Native(lua_State*state,Api100CoreNative method){
 const auto index=static_cast<unsigned>(method);
 if(index>=5){luaL_error(state,"invalid api100 native method");return nullptr;}
 std::uintptr_t host{};
#if !defined(__SWITCH__)
 host=g_Tests.methods[index];
#endif
 return engine_call::AsFunction<Fn>(api100_native::Resolve(state,kEntries[index],g_Cache[index],host));
}
int Relative(lua_State*state,Api100CoreNative method){auto*p=Entity(state);auto*result=Native<void*(*)(void*)>(state,method)(p);PushEntityCallbackArgument(state,engine_memory::AddressOf(result));return 1;}
}
#if !defined(__SWITCH__)
void SetApi100CoreNativeTestBindings(Api100CoreNativeTestBindings value)noexcept{g_Tests=value;}
#endif
int Api100EntityBloodExplode(lua_State*state){auto*p=Entity(state);Native<void(*)(void*)>(state,Api100CoreNative::BloodExplode)(p);return 0;}
int Api100EntityGetLastParent(lua_State*state){return Relative(state,Api100CoreNative::GetLastParent);}
int Api100EntityGetLastChild(lua_State*state){return Relative(state,Api100CoreNative::GetLastChild);}
int Api100EntityHasFullHealth(lua_State*state){auto*p=Entity(state);lua_pushboolean(state,Native<bool(*)(void*)>(state,Api100CoreNative::HasFullHealth)(p));return 1;}
int Api100EntityIsFrame(lua_State*state){auto*p=Entity(state);const auto frame=Integer(state,2);const auto offset=Integer(state,3);lua_pushboolean(state,Native<bool(*)(void*,std::int32_t,std::int32_t)>(state,Api100CoreNative::IsFrame)(p,frame,offset));return 1;}
}
