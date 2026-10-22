#include "interfaces/lua/api400_seeds.hpp"
#include "interfaces/lua/api400_seeds.guards.hpp"
#include "interfaces/lua/api100_native.hpp"
#include "interfaces/lua/api100_strings.hpp"
#include "interfaces/lua/owner_binding.hpp"
#include "infrastructure/call/engine_call_access.hpp"
#include "infrastructure/console/console_bridge.hpp"
extern "C" {
#include <lauxlib.h>
}
namespace isaac::runtime {
namespace {
api100_native::Cache g_Caches[3]{};
constexpr api100_native::Entry kEntries[]={
{api400_seeds::kSeed2StringEntry,api400_seeds::kSeed2StringGuard.data()},
{api400_seeds::kString2SeedEntry,api400_seeds::kString2SeedGuard.data()},
{api400_seeds::kIsStringValidSeedEntry,api400_seeds::kIsStringValidSeedGuard.data()}};
#if !defined(__SWITCH__)
std::uintptr_t g_Host[3]{};
#endif
std::uintptr_t Native(lua_State*L,unsigned id){std::uintptr_t host{};
#if !defined(__SWITCH__)
host=g_Host[id];
#endif
return api100_native::Resolve(L,kEntries[id],g_Caches[id],host);}
struct SeedContext{std::uintptr_t fn;std::uint32_t seed;};
Api100NativeString Encode(void*context){const auto&c=*static_cast<SeedContext*>(context);return engine_call::AsFunction<Api100NativeString(*)(std::uint32_t)>(c.fn)(c.seed);}
}
#if !defined(__SWITCH__)
void SetApi400SeedsNativeTestBindings(std::uintptr_t toString,std::uintptr_t toSeed,std::uintptr_t isValid)noexcept{g_Host[0]=toString;g_Host[1]=toSeed;g_Host[2]=isValid;}
#endif
int Api400SeedsSeed2String(lua_State*L){const auto seed=static_cast<std::uint32_t>(luaL_checkinteger(L,1));SeedContext context{Native(L,0),seed};return PushApi100NativeStringResult(L,Encode,&context);}
int Api400SeedsString2Seed(lua_State*L){std::size_t length{};const auto*text=luaL_checklstring(L,1,&length);alignas(8) unsigned char header[24];
// The complete native String2Seed only reads its const string input; Lua pins
// text on the argument stack, including embedded NUL and long-string length.
if(!console::BuildBorrowedCommandString(text,length,header))return luaL_argerror(L,1,"invalid seed string");
const auto result=engine_call::AsFunction<std::uint32_t(*)(const void*)>(Native(L,1))(header);lua_pushinteger(L,result);return 1;}
int Api400SeedsIsStringValidSeed(lua_State*L){std::size_t length{};const auto*text=luaL_checklstring(L,1,&length);alignas(8) unsigned char header[24];
// The complete native String2Seed only reads its const string input; Lua pins
// text on the argument stack, including embedded NUL and long-string length.
if(!console::BuildBorrowedCommandString(text,length,header))return luaL_argerror(L,1,"invalid seed string");
const auto result=engine_call::AsFunction<bool(*)(const void*)>(Native(L,2))(header);lua_pushboolean(L,result);return 1;}
void PublishApi400SeedsStatics(lua_State*L){lua_getglobal(L,"Seeds");if(!lua_istable(L,-1)){lua_pop(L,1);lua_newtable(L);lua_pushvalue(L,-1);lua_setglobal(L,"Seeds");}
PushHandler(L,Api400SeedsSeed2String,0,0x0F011525);lua_setfield(L,-2,"Seed2String");PushHandler(L,Api400SeedsString2Seed,0,0x0F011526);lua_setfield(L,-2,"String2Seed");PushHandler(L,Api400SeedsIsStringValidSeed,0,0x0F011527);lua_setfield(L,-2,"IsStringValidSeed");lua_pop(L,1);}
}
