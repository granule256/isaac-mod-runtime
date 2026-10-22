#include "interfaces/lua/api300_world.hpp"
#include "interfaces/lua/api300_world.guards.hpp"
#include "interfaces/lua/api100_native.hpp"
#include "interfaces/lua/isaac_api.hpp"
#include "interfaces/lua/field_api.hpp"
#include "infrastructure/memory/engine_field_access.hpp"
#include "lua_runtime.hpp"
#include "lua_object_handles.hpp"
#include <cstring>
#include "interfaces/lua/bitset128_api.hpp"
#include "interfaces/lua/vector_api.hpp"
#include "interfaces/lua/api100_strings.hpp"
#include "infrastructure/call/engine_call_access.hpp"
#include "runtime_constants.hpp"
extern "C" {
#include <lauxlib.h>
}
namespace isaac::runtime {
namespace {
namespace guard=api300_world;
enum class Owner:unsigned char{Level,PathFinder,Seeds};
enum class Operation:unsigned char{I32,Bool,True,SetBool,U32,AddFloat,Float,Zero,Nonzero,CountU32};
struct Field{std::uintptr_t offset;Owner owner;Operation operation;};
constexpr Field kFields[]={
{0x21510,Owner::Level,Operation::I32},
{0x9,Owner::Level,Operation::Bool},
{0x9,Owner::Level,Operation::True},
{0x10,Owner::Level,Operation::True},
{0x10,Owner::Level,Operation::Bool},
{0x11,Owner::Level,Operation::SetBool},
{0x21580,Owner::Level,Operation::U32},
{0x21538,Owner::Level,Operation::AddFloat},
{0x21538,Owner::Level,Operation::Float},
{0x730,Owner::PathFinder,Operation::Bool},
{0x740,Owner::PathFinder,Operation::I32},
{0x73c,Owner::PathFinder,Operation::SetBool},
{0x4,Owner::Seeds,Operation::Zero},
{0x4,Owner::Seeds,Operation::Nonzero},
{0x50,Owner::Seeds,Operation::U32},
{0x68,Owner::Seeds,Operation::CountU32},
};
api100_native::Cache g_Layouts[3]{};
constexpr api100_native::Entry kLayoutEntries[]={
 {guard::kLevelLayoutEntry,guard::kLevelLayoutGuard.data()},
 {guard::kPathFinderLayoutEntry,guard::kPathFinderLayoutGuard.data()},
 {guard::kSeedsLayoutEntry,guard::kSeedsLayoutGuard.data()}};
template<class T>__attribute__((noinline)) T Read(lua_State*L,std::uintptr_t p,std::uintptr_t o){T value{};if(!engine_memory::ReadField(p,o,&value,engine_memory::EngineMemoryReadable))luaL_error(L,"api300 field unavailable");return value;}
template<class T>__attribute__((noinline)) void Write(lua_State*L,std::uintptr_t p,std::uintptr_t o,const T&value){if(!engine_memory::WriteField(p,o,value,engine_memory::EngineMemoryWritable))luaL_error(L,"api300 field is not writable");}
__attribute__((noinline)) std::uintptr_t Receiver(lua_State*L,Owner owner){const char*meta=nullptr;FieldReceipt receipt=FieldReceipt::Level;
 switch(owner){case Owner::Level:meta=LuaRuntime::kLevelMetatable;break;case Owner::PathFinder:meta=LuaRuntime::kPathFinderMetatable;receipt=FieldReceipt::PathFinder;break;case Owner::Seeds:meta=LuaRuntime::kSeedsMetatable;receipt=FieldReceipt::Seeds;break;}
 luaL_checkudata(L,1,meta);const auto p=ResolveEngineReceiver(L,receipt,1);if(!p)luaL_error(L,"api300 reference is no longer available");const auto i=static_cast<unsigned>(owner);static_cast<void>(api100_native::Resolve(L,kLayoutEntries[i],g_Layouts[i],0));return p;}
__attribute__((noinline)) int WorldField(lua_State*L,unsigned index){const auto&r=kFields[index];const auto p=Receiver(L,r.owner);
 switch(r.operation){
  case Operation::I32:lua_pushinteger(L,Read<std::int32_t>(L,p,r.offset));return 1;
  case Operation::Bool:lua_pushboolean(L,Read<std::uint8_t>(L,p,r.offset)!=0);return 1;
  case Operation::True:Write(L,p,r.offset,std::uint8_t{1});return 0;
  case Operation::SetBool:Write(L,p,r.offset,static_cast<std::uint8_t>(lua_toboolean(L,2)!=0));return 0;
  case Operation::U32:lua_pushinteger(L,Read<std::uint32_t>(L,p,r.offset));return 1;
  case Operation::AddFloat:{const float amount=static_cast<float>(luaL_checknumber(L,2));const float value=Read<float>(L,p,r.offset)+amount;Write(L,p,r.offset,value);return 0;}
  case Operation::Float:lua_pushnumber(L,Read<float>(L,p,r.offset));return 1;
  case Operation::Zero:Write(L,p,r.offset,std::uint32_t{0});return 0;
  case Operation::Nonzero:lua_pushboolean(L,Read<std::uint32_t>(L,p,r.offset)!=0);return 1;
  case Operation::CountU32:lua_pushinteger(L,static_cast<std::uint32_t>(Read<std::uint64_t>(L,p,r.offset)));return 1;
 }
 return luaL_error(L,"invalid api300 field operation");
}
}
int Api300LevelGetRoomCount(lua_State*L){return WorldField(L,0);}
int Api300LevelIsDevilRoomDisabled(lua_State*L){return WorldField(L,1);}
int Api300LevelDisableDevilRoom(lua_State*L){return WorldField(L,2);}
int Api300LevelSetHeartPicked(lua_State*L){return WorldField(L,3);}
int Api300LevelGetHeartPicked(lua_State*L){return WorldField(L,4);}
int Api300LevelSetCanSeeEverything(lua_State*L){return WorldField(L,5);}
int Api300LevelGetDungeonPlacementSeed(lua_State*L){return WorldField(L,6);}
int Api300LevelAddAngelRoomChance(lua_State*L){return WorldField(L,7);}
int Api300LevelGetAngelRoomChance(lua_State*L){return WorldField(L,8);}
int Api300PathFinderHasDirectPath(lua_State*L){return WorldField(L,9);}
int Api300PathFinderGetEvadeMovementCountdown(lua_State*L){return WorldField(L,10);}
int Api300PathFinderSetCanCrushRocks(lua_State*L){return WorldField(L,11);}
int Api300SeedsClearStartSeed(lua_State*L){return WorldField(L,12);}
int Api300SeedsIsInitialized(lua_State*L){return WorldField(L,13);}
int Api300SeedsGetPlayerInitSeed(lua_State*L){return WorldField(L,14);}
int Api300SeedsCountSeedEffects(lua_State*L){return WorldField(L,15);}
namespace {
using Vec=LuaRuntime::VectorHandle;
constexpr api100_native::Entry kNativeEntries[]={
{guard::kEntityEffectIsPlayerCreepEntry,guard::kEntityEffectIsPlayerCreepGuard.data()},
{guard::kItemConfigIsValidCollectibleEntry,guard::kItemConfigIsValidCollectibleGuard.data()},
{guard::kEntityNPCCalcTargetPositionEntry,guard::kEntityNPCCalcTargetPositionGuard.data()},
{guard::kEntityNPCCanBeDamagedFromVelocityEntry,guard::kEntityNPCCanBeDamagedFromVelocityGuard.data()},
{guard::kEntityNPCCanRerollEntry,guard::kEntityNPCCanRerollGuard.data()},
{guard::kEntityNPCGetAliveEnemyCountEntry,guard::kEntityNPCGetAliveEnemyCountGuard.data()},
{guard::kEntityKnifeGetRenderZEntry,guard::kEntityKnifeGetRenderZGuard.data()},
{guard::kEntityLaserGetRenderZEntry,guard::kEntityLaserGetRenderZGuard.data()},
{guard::kTearFlagsSetterEntry,guard::kTearFlagsSetterGuard.data()},
{guard::kBombFlagsSetterEntry,guard::kBombFlagsSetterGuard.data()},
{guard::kSeed2StringEntry,guard::kSeed2StringGuard.data()},
{guard::kSeedTreeDestroyEntry,guard::kSeedTreeDestroyGuard.data()},
{guard::kEntityGetRenderZEntry,guard::kEntityGetRenderZGuard.data()},
{guard::kSeedComboLayoutEntry,guard::kSeedComboLayoutGuard.data()},
};
api100_native::Cache g_NativeCache[14]{};
#if !defined(__SWITCH__)
Api300WorldNativeTestBindings g_NativeTests{};
#endif
template<class Fn>Fn Native(lua_State*L,unsigned index){std::uintptr_t host{};
#if !defined(__SWITCH__)
 if(index<13)host=g_NativeTests.methods[index];
#endif
 return engine_call::AsFunction<Fn>(api100_native::Resolve(L,kNativeEntries[index],g_NativeCache[index],host));}
std::int32_t Integer(lua_State*L,int index){const auto bits=static_cast<std::uint32_t>(luaL_checkinteger(L,index));std::int32_t value{};std::memcpy(&value,&bits,4);return value;}
__attribute__((noinline)) std::uintptr_t EntitySelf(lua_State*L,const char*meta,CallbackEntityClass kind){luaL_checkudata(L,1,meta);const auto p=ResolveEngineReceiver(L,FieldReceipt::Entity,1);if(!p||ClassifyCallbackEntity(p)!=kind)luaL_error(L,"api300 entity expired or wrong family");return p;}
BitSet128Value Flags(lua_State*L,bool clear,bool*numeric){BitSet128Value value{};*numeric=false;if(ReadBitSet128(L,2,&value))return value;if(lua_type(L,2)==LUA_TNUMBER||(clear&&lua_type(L,2)==LUA_TSTRING&&lua_isnumber(L,2))){value.low=static_cast<std::uint64_t>(luaL_checkinteger(L,2));*numeric=true;return value;}luaL_argerror(L,2,"BitSet128 or integer expected");return value;}
__attribute__((noinline)) int TearFlags(lua_State*L,const char*meta,CallbackEntityClass kind,std::uintptr_t offset,bool clear){const auto p=EntitySelf(L,meta,kind);bool numeric{};const auto mask=Flags(L,clear,&numeric);const auto current=Read<BitSet128Value>(L,p,offset);if(!clear){lua_pushboolean(L,(current.low&mask.low)||(current.high&mask.high));return 1;}
 const BitSet128Value value{current.low&~mask.low,numeric?0:(current.high&~mask.high)};if(kind==CallbackEntityClass::Tear||kind==CallbackEntityClass::Bomb){const unsigned index=kind==CallbackEntityClass::Tear?8U:9U;Native<void(*)(void*,BitSet128Value)>(L,index)(engine_memory::AsObject(p),value);}else Write(L,p,offset,value);return 0;}
__attribute__((noinline)) int VirtualRenderZ(lua_State*L,const char*meta,CallbackEntityClass kind){const auto p=EntitySelf(L,meta,kind);const auto vptr=Read<std::uintptr_t>(L,p,0);const auto target=Read<std::uintptr_t>(L,vptr,0x68);const auto base=LuaRuntime::EngineModuleBase();unsigned index=14;for(unsigned i:{6U,7U,12U})if(base<=UINTPTR_MAX-kNativeEntries[i].offset&&target==base+kNativeEntries[i].offset){index=i;break;}
 if(index==14){return luaL_error(L,"GetRenderZ virtual binding unavailable");}
 lua_pushinteger(L,Native<std::uint32_t(*)(void*)>(L,index)(engine_memory::AsObject(p)));return 1;}
struct SeedTextContext{std::uint32_t seed;Api100NativeString(*fn)(std::uint32_t);};
Api100NativeString SeedText(void*context){const auto*c=static_cast<SeedTextContext*>(context);return c->fn(c->seed);}
}
#if !defined(__SWITCH__)
void SetApi300WorldNativeTestBindings(Api300WorldNativeTestBindings value)noexcept{g_NativeTests=value;}
#endif
int Api300EntityEffectIsPlayerCreep(lua_State*L){const auto value=Integer(L,1);lua_pushboolean(L,Native<bool(*)(std::int32_t)>(L,0)(value));return 1;}
int Api300ItemConfigIsValidCollectible(lua_State*L){const auto value=Integer(L,1);lua_pushboolean(L,Native<bool(*)(std::int32_t)>(L,1)(value));return 1;}
int Api300EntityNPCCalcTargetPosition(lua_State*L){const auto p=EntitySelf(L,LuaRuntime::kEntityNPCMetatable,CallbackEntityClass::Npc);const float limit=static_cast<float>(luaL_checknumber(L,2));const auto v=Native<Vec(*)(void*,float)>(L,2)(engine_memory::AsObject(p),limit);PushLuaVector(L,v.x,v.y);return 1;}
int Api300EntityNPCCanBeDamagedFromVelocity(lua_State*L){const auto p=EntitySelf(L,LuaRuntime::kEntityNPCMetatable,CallbackEntityClass::Npc);const auto v=*RequireVectorArgument(L,2);lua_pushboolean(L,Native<bool(*)(void*,Vec)>(L,3)(engine_memory::AsObject(p),v));return 1;}
int Api300EntityNPCCanReroll(lua_State*L){const auto p=EntitySelf(L,LuaRuntime::kEntityNPCMetatable,CallbackEntityClass::Npc);lua_pushboolean(L,Native<bool(*)(void*)>(L,4)(engine_memory::AsObject(p)));return 1;}
int Api300EntityNPCGetAliveEnemyCount(lua_State*L){const auto p=EntitySelf(L,LuaRuntime::kEntityNPCMetatable,CallbackEntityClass::Npc);lua_pushinteger(L,Native<std::int32_t(*)(void*)>(L,5)(engine_memory::AsObject(p)));return 1;}
int Api300EntityKnifeGetRenderZ(lua_State*L){return VirtualRenderZ(L,LuaRuntime::kEntityKnifeMetatable,CallbackEntityClass::Knife);}
int Api300EntityLaserGetRenderZ(lua_State*L){return VirtualRenderZ(L,LuaRuntime::kEntityLaserMetatable,CallbackEntityClass::Laser);}
int Api300SeedsClearSeedEffects(lua_State*L){const auto p=Receiver(L,Owner::Seeds);const auto root=Read<std::uintptr_t>(L,p,0x60);Native<void(*)(void*,void*)>(L,11)(engine_memory::AsObject(p+0x58),engine_memory::AsObject(root));struct Header{std::uintptr_t begin,root;std::uint64_t size;};const Header empty{p+0x60,0,0};Write(L,p,0x58,empty);return 0;}
int Api300SeedsGetStartSeedString(lua_State*L){const auto p=Receiver(L,Owner::Seeds);SeedTextContext context{Read<std::uint32_t>(L,p,4),Native<Api100NativeString(*)(std::uint32_t)>(L,10)};return PushApi100NativeStringResult(L,SeedText,&context);}
int Api300SeedsIsSeedComboBanned(lua_State*L){static_cast<void>(Receiver(L,Owner::Seeds));const auto first=Integer(L,2),second=Integer(L,3);static_cast<void>(Native<void(*)()>(L,13));const auto base=LuaRuntime::EngineModuleBase();if(base>UINTPTR_MAX-0xabd828)return luaL_error(L,"seed combo vector unavailable");const auto vector=base+0xabd828;struct Bounds{std::uintptr_t begin,end;};const auto bounds=Read<Bounds>(L,vector,0);if(bounds.end<bounds.begin||(bounds.end-bounds.begin)%24||first<0||static_cast<std::uint64_t>(first)>=(bounds.end-bounds.begin)/24)return luaL_error(L,"seed combo index outside initialized vector");const auto tree=bounds.begin+static_cast<std::uintptr_t>(first)*24;auto node=Read<std::uintptr_t>(L,tree,8);const auto count=Read<std::uint64_t>(L,tree,16);std::uint64_t visited{};
 while(node){if(++visited>count)return luaL_error(L,"seed combo tree unavailable");const auto key=Read<std::int32_t>(L,node,0x1c);if(second==key){lua_pushboolean(L,1);return 1;}node=Read<std::uintptr_t>(L,node,second<key?0:8);}lua_pushboolean(L,0);return 1;}
int Api300EntityTearClearTearFlags(lua_State*L){return TearFlags(L,LuaRuntime::kEntityTearMetatable,CallbackEntityClass::Tear,kEntityTearFlagsOffset,true);}
int Api300EntityTearHasTearFlags(lua_State*L){return TearFlags(L,LuaRuntime::kEntityTearMetatable,CallbackEntityClass::Tear,kEntityTearFlagsOffset,false);}
int Api300EntityBombClearTearFlags(lua_State*L){return TearFlags(L,LuaRuntime::kEntityBombMetatable,CallbackEntityClass::Bomb,kEntityBombTearFlagsOffset,true);}
int Api300EntityBombHasTearFlags(lua_State*L){return TearFlags(L,LuaRuntime::kEntityBombMetatable,CallbackEntityClass::Bomb,kEntityBombTearFlagsOffset,false);}
int Api300EntityKnifeClearTearFlags(lua_State*L){return TearFlags(L,LuaRuntime::kEntityKnifeMetatable,CallbackEntityClass::Knife,kEntityKnifeTearFlagsOffset,true);}
int Api300EntityKnifeHasTearFlags(lua_State*L){return TearFlags(L,LuaRuntime::kEntityKnifeMetatable,CallbackEntityClass::Knife,kEntityKnifeTearFlagsOffset,false);}
int Api300EntityLaserClearTearFlags(lua_State*L){return TearFlags(L,LuaRuntime::kEntityLaserMetatable,CallbackEntityClass::Laser,kEntityLaserTearFlagsOffset,true);}
int Api300EntityLaserHasTearFlags(lua_State*L){return TearFlags(L,LuaRuntime::kEntityLaserMetatable,CallbackEntityClass::Laser,kEntityLaserTearFlagsOffset,false);}

}
