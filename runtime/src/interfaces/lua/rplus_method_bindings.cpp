#include "interfaces/lua/rplus_method_bindings.hpp"
#include "interfaces/lua/rplus_methods_api.hpp"
#include "interfaces/lua/owner_binding.hpp"
namespace isaac::runtime {
static constexpr LuaHandlerBinding kBindings[] = {
    {0x0E011040, &RPlusEntityAddBurn},
    {0x0E011041, &RPlusEntityAddConfusion},
    {0x0E011042, &RPlusEntityAddMidasFreeze},
    {0x0E011043, &RPlusEntityAddShrink},
    {0x0E011044, &RPlusEntityAddSlowing},
    {0x0E011045, &RPlusEntityHasMortalDamage},
    {0x0E011046, &RPlusBombAddTearFlags},
    {0x0E011047, &RPlusKnifeAddTearFlags},
    {0x0E011048, &RPlusLaserAddTearFlags},
    {0x0E011049, &RPlusTearAddTearFlags},
    {0x0E01104A, &RPlusBombSetExplosionCountdown},
    {0x0E01104B, &RPlusPlayerAddCostume},
    {0x0E01104C, &RPlusPlayerAddWisp},
    {0x0E01104D, &RPlusPlayerAnimateCard},
    {0x0E01104E, &RPlusPlayerAnimatePickup},
    {0x0E01104F, &RPlusPlayerCanPickupItem},
    {0x0E011050, &RPlusPlayerFireBomb},
    {0x0E011051, &RPlusPlayerFlushQueueItem},
    {0x0E011052, &RPlusPlayerFullCharge},
    {0x0E011053, &RPlusPlayerGetAimDirection},
    {0x0E011054, &RPlusPlayerGetMaxTrinkets},
    {0x0E011055, &RPlusPlayerGetTearMovementInheritance},
    {0x0E011056, &RPlusPlayerRemoveCostume},
    {0x0E011057, &RPlusPlayerSetPill},
    {0x0E011058, &RPlusPlayerSetPocketActiveItem},
    {0x0E011059, &RPlusPlayerThrowBlueSpider},
    {0x0E01105A, &RPlusPlayerWillPlayerRevive},
    {0x0E01105B, &RPlusProjectileHasProjectileFlags},
    {0x0201105C, &RPlusGameClearStagesWithoutHeartsPicked},
    {0x0201105D, &RPlusGameFart},
    {0x0201105E, &RPlusGameShakeScreen},
    {0x0E01105F, &RPlusGridSetVariant},
    {0x0E011060, &RPlusDoorBar},
    {0x0E011061, &RPlusPathFindGridPath},
    {0x04011062, &RPlusRoomGetAwardSeed},
};
std::size_t AttachRPlusMethods(lua_State* state,const char* owner) noexcept {
    return AttachOwnerMethods(state,owner,kBindings,sizeof(kBindings)/sizeof(kBindings[0]));
}
}
