#include "interfaces/lua/api400_bindings.hpp"
#include "interfaces/lua/api400_entities.hpp"
#include "interfaces/lua/api400_params.hpp"
#include "interfaces/lua/api400_seeds.hpp"
#include "interfaces/lua/owner_binding.hpp"
#include "interfaces/lua/isaac_api.hpp"
#include <cstring>
namespace isaac::runtime {
namespace {constexpr LuaHandlerBinding kBindings[]={
{0x0E011500,&Api400EntityPlayerRenderGlow},
{0x0E011501,&Api400EntityNPCKillUnique},
{0x0E011502,&Api400EntityNPCMakeChampion},
{0x0E011503,&Api400EntityNPCMakeSplat},
{0x0E011504,&Api400EntityPickupTryOpenChest},
{0x0E011505,&Api400EntityGetBossID},
{0x0E011506,&Api400EntitySetSpriteOverlayFrame},
{0x0E011507,&Api400EntityEffectFollowParent},
{0x0E011508,&Api400EntityEffectSetDamageSource},
{0x0E011509,&Api400EntityEffectSetRadii},
{0x0E01150A,&Api400EntityEffectSetTimeout},
{0x0E01150B,&Api400EntityKnifeGetKnifeDistance},
{0x0E01150C,&Api400EntityKnifeGetKnifeVelocity},
{0x0E01150D,&Api400EntityKnifeSetPathFollowSpeed},
{0x0E01150E,&Api400EntityLaserGetEndPoint},
{0x0E01150F,&Api400EntityLaserIsCircleLaser},
{0x0E011510,&Api400EntityLaserIsSampleLaser},
{0x0E011511,&Api400EntityLaserSetBlackHpDropChance},
{0x0E011512,&Api400EntityLaserSetHomingType},
{0x0E011513,&Api400EntityLaserSetMultidimensionalTouched},
{0x0E011514,&Api400EntityLaserSetOneHit},
{0x0E011515,&Api400EntityLaserSetTimeout},
{0x0E011516,&Api400EntityNPCResetPathFinderTarget},
{0x0E011517,&Api400EntityPlayerRenderTop},
{0x0E011518,&Api400EntityRenderShadowLayer},
{0x0E011519,&Api400EntityProjectileAddChangeFlags},
{0x0E01151A,&Api400EntityProjectileAddFallingAccel},
{0x0E01151B,&Api400EntityProjectileAddFallingSpeed},
{0x0E01151C,&Api400EntityProjectileAddHeight},
{0x0E01151D,&Api400EntityProjectileAddProjectileFlags},
{0x0E01151E,&Api400EntityProjectileAddScale},
{0x0E01151F,&Api400EntityProjectileClearProjectileFlags},
{0x0E011520,&Api400EntityTearSetKnockbackMultiplier},
{0x0E011521,&Api400EntityTearSetParentOffset},
{0x0E011522,&Api400EntityTearSetWaitFrames},
{0x0E011523,&Api400EntityNPCFireProjectiles},
{0x0E011524,&Api400EntityNPCFireBossProjectiles},
{0x0F011525,&Api400SeedsSeed2String},
{0x0F011526,&Api400SeedsString2Seed},
{0x0F011527,&Api400SeedsIsStringValidSeed},
{0x0E011528,&Api400EntityKnifeIsFlying},
};}
std::size_t AttachApi400Methods(lua_State*L,const char*owner)noexcept{return AttachOwnerMethods(L,owner,kBindings,sizeof(kBindings)/sizeof(kBindings[0]));}
// Effects currently use the base Entity view. Only reveal their own methods
// after a name match and live family check; do not publish them on other entities.
int TryPushApi400EffectMethod(lua_State*L,std::uintptr_t entity,const char*name){if(!name||!((name[0]=='F'&&name[1]=='o')||(name[0]=='S'&&name[1]=='e'))){return 0;}
std::uint32_t id{};lua_CFunction handler{};
if(!std::strcmp(name,"FollowParent")){id=0x0E011507;handler=&Api400EntityEffectFollowParent;}
if(!std::strcmp(name,"SetDamageSource")){id=0x0E011508;handler=&Api400EntityEffectSetDamageSource;}
if(!std::strcmp(name,"SetRadii")){id=0x0E011509;handler=&Api400EntityEffectSetRadii;}
if(!std::strcmp(name,"SetTimeout")){id=0x0E01150A;handler=&Api400EntityEffectSetTimeout;}
if(!handler||ClassifyCallbackEntity(entity)!=CallbackEntityClass::Effect){return 0;}
PushHandler(L,handler,0,id);return 1;}
}
