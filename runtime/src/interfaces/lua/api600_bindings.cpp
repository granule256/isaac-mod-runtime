#include "interfaces/lua/api600_containers.hpp"
#include "interfaces/lua/api600_values.hpp"
#include "interfaces/lua/api600_room_state.hpp"
#include "interfaces/lua/api600_grid_methods.hpp"
#include "interfaces/lua/api600_game.hpp"
#include "interfaces/lua/api600_entityptr.hpp"
#include "interfaces/lua/api600_config.hpp"
#include "interfaces/lua/api600_bindings.hpp"
#include "interfaces/lua/api600_player.hpp"
#include "interfaces/lua/owner_binding.hpp"
namespace isaac::runtime {
namespace {constexpr LuaHandlerBinding kBindings[]={
{0x0E011640,&Api600EntityPlayerGetTearHitParams},
{0x0E011601,&Api600EntityPlayerGetActiveSubCharge},
{0x0E011602,&Api600EntityPlayerGetBombVariant},
{0x0E011603,&Api600EntityPlayerAreOpposingShootDirectionsPressed},
{0x0E011604,&Api600EntityPlayerHasWeaponType},
{0x0E011605,&Api600EntityPlayerGetMultiShotParams},
{0x0E011606,&Api600EntityPlayerGetMultiShotPositionVelocity},
{0x0E011617,&Api600ItemConfigGetCards},
{0x0E011618,&Api600ItemConfigGetPillEffects},
{0x0E011619,&Api600ItemConfigGetNullItems},
{0x0E01161A,&Api600ItemConfigItemIsNull},
{0x0E01161B,&Api600ItemConfigShouldAddCostumeOnPickup},
{0x0E01161C,&Api600CardConfigListGet},
{0x0E01161D,&Api600CardConfigListLen},
{0x0E01161E,&Api600PillConfigListGet},
{0x0E01161F,&Api600PillConfigListLen},
{0x0E011621,&Api600EntityPtrSetReference},
{0x02011622,&Api600GameBombDamage},
{0x02011623,&Api600GameBombExplosionEffects},
{0x02011624,&Api600GameBombTearflagEffects},
{0x02011625,&Api600GameUpdateStrangeAttractor},
{0x02011626,&Api600GameRender},
{0x04011627,&Api600RoomRender},
{0x0E011628,&Api600GridEntityDoorIsBusted},
{0x0E011629,&Api600GridEntityDoorIsLocked},
{0x0E01162A,&Api600GridEntityDoorIsKeyFamiliarTarget},
{0x0E01162B,&Api600GridEntityDoorGetSpriteOffset},
{0x0E01162C,&Api600GridEntityRockGetRubbleAnim},
{0x0201162D,&Api600GameGetLastDevilRoomStage},
{0x0201162E,&Api600GameGetLastLevelWithDamage},
{0x0201162F,&Api600GameGetLastLevelWithoutHalfHp},
{0x04011630,&Api600RoomGetShopLevel},
{0x04011631,&Api600RoomGetLavaIntensity},
{0x04011632,&Api600RoomHasSlowDown},
{0x04011633,&Api600RoomSetSlowDown},
{0x04011634,&Api600RoomIsFirstEnemyDead},
{0x04011635,&Api600RoomSetFirstEnemyDead},
{0x04011636,&Api600RoomInvalidatePickupVision},
{0x04011637,&Api600RoomEmitBloodFromWalls},
{0x0D011638,&Api600SpriteGetOverlayAnimation},
{0x0D011639,&Api600SpriteSetOverlayRenderPriority},
{0x0001163A,&Api600RandomVector},
{0x0E01163B,&Api600RoomConfigEntriesGet},
{0x0E01163C,&Api600RoomConfigEntriesLen},
{0x0E01163D,&Api600RoomConfigSpawnsLen},
{0x0401163E,&Api600RoomGetDeliriumDistance},
};}
std::size_t AttachApi600Methods(lua_State*L,const char*owner)noexcept{return AttachOwnerMethods(L,owner,kBindings,sizeof(kBindings)/sizeof(kBindings[0]));}
}
