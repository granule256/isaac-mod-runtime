#include "runtime_constants.hpp"
#include "interfaces/lua/api700_grid.hpp"
#include "interfaces/lua/api700_containers.hpp"
#include "interfaces/lua/mod_api.hpp"
#include "interfaces/lua/engine_method_api.hpp"
#include "interfaces/lua/field_api.hpp"
#include "interfaces/lua/api700_player.hpp"
#include "interfaces/lua/api700_bindings.hpp"
#include "interfaces/lua/api700_world.hpp"
#include "interfaces/lua/owner_binding.hpp"
#include <cstring>
extern "C" {
#include <lauxlib.h>
}
namespace isaac::runtime{
namespace {constexpr LuaHandlerBinding kBindings[]={
{0x040117B0,&Api700RoomGetEnemyDamageInflicted},
{0x020117A9,&Api700GameSpawnEntityDesc},
{0x0E0117D0,&Api700GridPoopReduceSpawnRate},

{0x0E0117A7,&Api700IsaacScreenToWorldDistance},
{0x0E0117A8,&Api700IsaacGetScreenPointScale},

{0x0E0117C0,&Api700LaserGetSamples},
{0x0E0117C1,&Api700LaserGetNonOptimizedSamples},
{0x0E0117C2,&Api700NPCQueryType},
{0x0E0117C3,&Api700NPCQuerySpawnerType},
{0x0E0117C4,&Api700NPCQueryGroup},
{0x040117C5,&Api700RoomGetEntities},
{0x0E0117C6,&Api700EntityListGet},
{0x0E0117C7,&Api700EntityListLen},
{0x0E0117C8,&Api700VectorListGet},
{0x0E0117C9,&Api700VectorListLen},

{0x020117A3,&Api700GameShowFortune},
{0x020117A4,&Api700GameShowRule},
{0x0E0117A5,&Api700IsaacRemoveModData},
{0x0E0117A6,&Api700IsaacGetCurseIdByName},

{0x0201178A,&Api700GameGetFont},
{0x0201178B,&Api700GameGetAmbush},
{0x0201178C,&Api700GameGetItemOverlay},

{0x0E011700,&Api700EntityPlayerAnimatePill},
{0x0E011701,&Api700EntityPlayerAnimateTrinket},
{0x0E011702,&Api700EntityPlayerSwapActiveItems},
{0x0E011703,&Api700EntityPlayerTryRemoveCollectibleCostume},
{0x0E011704,&Api700EntityPlayerGetCostumeNullPos},
{0x0E011705,&Api700EntityPlayerReplaceCostumeSprite},
{0x0E011706,&Api700EntityPlayerQueueExtraAnimation},
{0x0E011707,&Api700EntityPlayerGetLastDamageSource},
{0x0E011708,&Api700EntityPlayerGetPocketItem},
{0x04011780,&Api700RoomScreenWrapPosition},
{0x0E011781,&Api700EntityLaserCalculateEndPoint},
{0x0F011782,&Api700SeedsGetSeedEffect},
{0x0F011783,&Api700SeedsIsSpecialSeed},
{0x0E011784,&Api700IsaacAddPillEffectToPool},
{0x0E011785,&Api700IsaacWorldToScreenDistance},
{0x04011786,&Api700RoomGetLRoomAreaDesc},
{0x04011787,&Api700RoomGetLRoomTileDesc},
{0x05011788,&Api700ItemPoolAddRoomBlacklist},
{0x03011789,&Api700LevelGetDevilAngelRoomRNG},
};
constexpr EngineMethodRow kEngineRows[]={
{0x0E0117A0,MakeEngineVtableRowOffset(kApi700EntityRenderVtableSlot),0,FieldReceipt::Entity,EngineCallShape::VoidVector2Ref,1,0xff},
{0x0E0117A1,MakeEngineVtableRowOffset(kApi700EntityPostRenderVtableSlot),0,FieldReceipt::Entity,EngineCallShape::Void0,0,0xff},
{0x0E0117A2,MakeEngineVtableRowOffset(kApi700GridEntityRenderVtableSlot),0,FieldReceipt::GridEntity,EngineCallShape::VoidVector2Ref,1,0xff},
};}
std::size_t AttachApi700Methods(lua_State*L,const char*owner)noexcept{return AttachOwnerMethods(L,owner,kBindings,sizeof(kBindings)/sizeof(kBindings[0]),nullptr,0,kEngineRows,sizeof(kEngineRows)/sizeof(kEngineRows[0]));}
void PublishApi700Statics(lua_State*L,const char*owner){
 const char*names[2]{};unsigned count{};
 if(!std::strcmp(owner,"Seeds")){names[0]="GetSeedEffect";names[1]="IsSpecialSeed";count=2;}
 else if(!std::strcmp(owner,"EntityLaser")){names[0]="CalculateEndPoint";count=1;}
 if(!count)return;
 lua_getglobal(L,owner);if(!lua_istable(L,-1)){lua_pop(L,1);return;}
 const auto destination=lua_gettop(L);if(!lua_getmetatable(L,destination)){lua_pop(L,1);return;}
 lua_getfield(L,-1,"__class");for(unsigned i=0;i<count;++i){lua_getfield(L,-1,names[i]);lua_setfield(L,destination,names[i]);}lua_pop(L,3);
}
}
