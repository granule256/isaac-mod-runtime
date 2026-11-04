#include "interfaces/lua/api200_game.hpp"
#include "interfaces/lua/api200_game.guards.hpp"
#include "interfaces/lua/minimap_pickup_cache.hpp"
#include "interfaces/lua/api100_native.hpp"
#include "interfaces/lua/isaac_api.hpp"
#include "interfaces/lua/field_api.hpp"
#include "interfaces/lua/vector_api.hpp"
#include "infrastructure/memory/engine_field_access.hpp"
#include "infrastructure/call/engine_call_access.hpp"
#include "lua_runtime.hpp"
#include "lua_object_handles.hpp"
#include <cstring>
#include <type_traits>
extern "C" {
#include <lauxlib.h>
}
namespace isaac::runtime {
namespace {
using Vec2=LuaRuntime::VectorHandle;
namespace guards=api200_game;
constexpr api100_native::Entry kEntries[]={
 {guards::kAddEncounteredBossEntry,guards::kAddEncounteredBossGuard.data()},
 {guards::kButterBeanFartEntry,guards::kButterBeanFartGuard.data()},
 {guards::kDonateAngelEntry,guards::kDonateAngelGuard.data()},
 {guards::kDonateGreedEntry,guards::kDonateGreedGuard.data()},
 {guards::kEndEntry,guards::kEndGuard.data()},
 {guards::kFadeinEntry,guards::kFadeinGuard.data()},
 {guards::kFadeoutEntry,guards::kFadeoutGuard.data()},
 {guards::kFinishChallengeEntry,guards::kFinishChallengeGuard.data()},
 {guards::kGetGreedWavesNumEntry,guards::kGetGreedWavesNumGuard.data()},
 {guards::kGetNearestPlayerEntry,guards::kGetNearestPlayerGuard.data()},
 {guards::kGetRandomPlayerEntry,guards::kGetRandomPlayerGuard.data()},
 {guards::kHasEncounteredBossEntry,guards::kHasEncounteredBossGuard.data()},
 {guards::kMakeShockwaveEntry,guards::kMakeShockwaveGuard.data()},
 {guards::kNextVictoryLapEntry,guards::kNextVictoryLapGuard.data()},
 {guards::kRerollEnemyEntry,guards::kRerollEnemyGuard.data()},
 {guards::kRerollLevelCollectiblesEntry,guards::kRerollLevelCollectiblesGuard.data()},
 {guards::kRerollLevelPickupsEntry,guards::kRerollLevelPickupsGuard.data()},
 {guards::kStartStageTransitionEntry,guards::kStartStageTransitionGuard.data()},
};
constexpr unsigned kCount=static_cast<unsigned>(Api200GameNative::Count);
static_assert(sizeof(kEntries)/sizeof(kEntries[0])==kCount);
static_assert(std::is_trivial_v<api100_native::Cache>);
api100_native::Cache g_Cache[kCount]{};
#if !defined(__SWITCH__)
Api200GameNativeTestBindings g_Tests{};
#endif
void* Game(lua_State*state){
 luaL_checkudata(state,1,LuaRuntime::kGameMetatable);
 const auto p=ResolveEngineReceiver(state,FieldReceipt::Level,1);
 if(!p)luaL_error(state,"Game reference is no longer available");
 return engine_memory::AsObject(p);
}
std::int32_t Int(lua_State*state,int index){const auto bits=static_cast<std::uint32_t>(luaL_checkinteger(state,index));std::int32_t value{};std::memcpy(&value,&bits,4);return value;}
bool Bool(lua_State*state,int index){return lua_toboolean(state,index)!=0;}
float Number(lua_State*state,int index){return static_cast<float>(luaL_checknumber(state,index));}
const Vec2& Vector(lua_State*state,int index){return *RequireVectorArgument(state,index);}
void* Entity(lua_State*state,int index){
 if(lua_isnil(state,index))return nullptr;
 const auto p=EntityPointerArgument(state,index);
 if(!p)luaL_argerror(state,index,"live Entity or nil expected");
 return engine_memory::AsObject(p);
}
void* OptionalPlayer(lua_State*state,int index){
 // NS StageTransition::Start对NULL选择当前玩家列表首个；不传PC包装未填的栈值。
 if(lua_isnoneornil(state,index))return nullptr;
 luaL_checkudata(state,index,LuaRuntime::kEntityPlayerMetatable);
 const auto p=ResolveEngineReceiver(state,FieldReceipt::EntityPlayer,index);
 if(!p)luaL_argerror(state,index,"live EntityPlayer or nil expected");
 return engine_memory::AsObject(p);
}
template<class Fn>Fn Native(lua_State*state,Api200GameNative method){
 const auto index=static_cast<unsigned>(method);std::uintptr_t host{};
#if !defined(__SWITCH__)
 host=g_Tests.methods[index];
#endif
 return engine_call::AsFunction<Fn>(api100_native::Resolve(state,kEntries[index],g_Cache[index],host));
}
}
#if !defined(__SWITCH__)
void SetApi200GameNativeTestBindings(Api200GameNativeTestBindings value) noexcept{g_Tests=value;}
#endif
int Api200GameAddEncounteredBoss(lua_State*state){
 auto*p=Game(state);
 std::int32_t a0=Int(state,2);
 std::uint32_t a1=static_cast<std::uint32_t>(Int(state,3));
 Native<void(*)(void*,std::int32_t,std::uint32_t)>(state,Api200GameNative::AddEncounteredBoss)(p,a0,a1);return 0;
}
int Api200GameButterBeanFart(lua_State*state){
 auto*p=Game(state);
 const Vec2& a0=Vector(state,2);
 float a1=Number(state,3);
 void* a2=Entity(state,4);
 bool a3=Bool(state,5);
 bool a4=Bool(state,6);
 Native<void(*)(void*,const Vec2&,float,void*,bool,bool)>(state,Api200GameNative::ButterBeanFart)(p,a0,a1,a2,a3,a4);return 0;
}
int Api200GameDonateAngel(lua_State*state){
 auto*p=Game(state);
 std::int32_t a0=Int(state,2);
 Native<void(*)(void*,std::int32_t)>(state,Api200GameNative::DonateAngel)(p,a0);return 0;
}
int Api200GameDonateGreed(lua_State*state){
 auto*p=Game(state);
 std::int32_t a0=Int(state,2);
 Native<void(*)(void*,std::int32_t)>(state,Api200GameNative::DonateGreed)(p,a0);return 0;
}
int Api200GameEnd(lua_State*state){
 auto*p=Game(state);
 std::int32_t a0=Int(state,2);
 Native<void(*)(void*,std::int32_t)>(state,Api200GameNative::End)(p,a0);return 0;
}
int Api200GameFadein(lua_State*state){
 auto*p=Game(state);
 float a0=Number(state,2);
 Native<void(*)(void*,float)>(state,Api200GameNative::Fadein)(p,a0);return 0;
}
int Api200GameFadeout(lua_State*state){
 auto*p=Game(state);
 float a0=Number(state,2);
 std::int32_t a1=Int(state,3);
 Native<void(*)(void*,float,std::int32_t)>(state,Api200GameNative::Fadeout)(p,a0,a1);return 0;
}
int Api200GameFinishChallenge(lua_State*state){
 auto*p=Game(state);
 Native<void(*)(void*)>(state,Api200GameNative::FinishChallenge)(p);return 0;
}
int Api200GameGetGreedWavesNum(lua_State*state){
 auto*p=Game(state);
 lua_pushinteger(state,static_cast<lua_Integer>(Native<std::uint32_t(*)(void*)>(state,Api200GameNative::GetGreedWavesNum)(p)));return 1;
}
int Api200GameGetNearestPlayer(lua_State*state){
 auto*p=Game(state);
 const Vec2& a0=Vector(state,2);
 const auto result=Native<void*(*)(void*,const Vec2&)>(state,Api200GameNative::GetNearestPlayer)(p,a0);if(result)PushEntityCallbackArgument(state,engine_memory::AddressOf(result));else lua_pushnil(state);return 1;
}
int Api200GameGetRandomPlayer(lua_State*state){
 auto*p=Game(state);
 const Vec2& a0=Vector(state,2);
 float a1=Number(state,3);
 const auto result=Native<void*(*)(void*,const Vec2&,float)>(state,Api200GameNative::GetRandomPlayer)(p,a0,a1);if(result)PushEntityCallbackArgument(state,engine_memory::AddressOf(result));else lua_pushnil(state);return 1;
}
int Api200GameHasEncounteredBoss(lua_State*state){
 auto*p=Game(state);
 std::int32_t a0=Int(state,2);
 std::uint32_t a1=static_cast<std::uint32_t>(Int(state,3));
 lua_pushboolean(state,Native<bool(*)(void*,std::int32_t,std::uint32_t)>(state,Api200GameNative::HasEncounteredBoss)(p,a0,a1));return 1;
}
int Api200GameMakeShockwave(lua_State*state){
 auto*p=Game(state);
 const Vec2& a0=Vector(state,2);
 float a1=Number(state,3);
 float a2=Number(state,4);
 std::int32_t a3=Int(state,5);
 Native<void(*)(void*,const Vec2&,float,float,std::int32_t)>(state,Api200GameNative::MakeShockwave)(p,a0,a1,a2,a3);return 0;
}
int Api200GameNextVictoryLap(lua_State*state){
 auto*p=Game(state);
 Native<void(*)(void*)>(state,Api200GameNative::NextVictoryLap)(p);return 0;
}
int Api200GameRerollEnemy(lua_State*state){
 auto*p=Game(state);
 void* a0=Entity(state,2);
 bool a1=Bool(state,3);
 lua_pushboolean(state,Native<bool(*)(void*,void*,bool)>(state,Api200GameNative::RerollEnemy)(p,a0,a1));return 1;
}
int Api200GameRerollLevelCollectibles(lua_State*state){
 auto*p=Game(state);
 Native<void(*)(void*)>(state,Api200GameNative::RerollLevelCollectibles)(p);
 NoteMinimapPickupReroll(MinimapPickupReroll::Collectibles);return 0;
}
int Api200GameRerollLevelPickups(lua_State*state){
 auto*p=Game(state);
 std::uint32_t a0=static_cast<std::uint32_t>(Int(state,2));
 Native<void(*)(void*,std::uint32_t)>(state,Api200GameNative::RerollLevelPickups)(p,a0);
 NoteMinimapPickupReroll(MinimapPickupReroll::Pickups);return 0;
}
int Api200GameStartStageTransition(lua_State*state){
 auto*p=Game(state);
 bool a0=Bool(state,2);
 std::int32_t a1=Int(state,3);
 void* a2=OptionalPlayer(state,4);
 Native<void(*)(void*,bool,std::int32_t,void*)>(state,Api200GameNative::StartStageTransition)(p,a0,a1,a2);return 0;
}
}
