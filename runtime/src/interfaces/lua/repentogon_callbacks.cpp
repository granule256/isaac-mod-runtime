#include "interfaces/lua/repentogon_callbacks.hpp"
#include "interfaces/lua/repentogon_environment.hpp"
#include "interfaces/lua/rng_api.hpp"
#include "interfaces/lua/procedural_item_api.hpp"
#include "interfaces/lua/repentogon_world_api.hpp"
#include "interfaces/lua/repentogon_runtime_api.hpp"
#include "application/callback/extended_callback_runtime.hpp"
#include "lua_runtime.hpp"
#include <array>
extern "C" {
#include <lauxlib.h>
}

namespace isaac::runtime::repentogon {
namespace {
const NativePort* g_NativePort{};
constexpr RepentogonCallbackBinding kCallbacks[]={
    {1020,"MC_HUD_UPDATE"},
    {1021,"MC_POST_HUD_UPDATE"},
    {1022,"MC_HUD_RENDER"},
    {1024,"MC_POST_HUD_RENDER"},
    {1026,"MC_PRE_UPDATE"},
    {1030,"MC_PRE_SFX_PLAY"},
    {1031,"MC_POST_SFX_PLAY"},
    {1060,"MC_PRE_LEVEL_INIT"},
    {1080,"MC_PRE_FAMILIAR_RENDER"},
    {1081,"MC_PRE_NPC_RENDER"},
    {1082,"MC_PRE_PLAYER_RENDER"},
    {1083,"MC_PRE_PICKUP_RENDER"},
    {1084,"MC_PRE_TEAR_RENDER"},
    {1085,"MC_PRE_PROJECTILE_RENDER"},
    {1086,"MC_PRE_KNIFE_RENDER"},
    {1087,"MC_PRE_EFFECT_RENDER"},
    {1088,"MC_PRE_BOMB_RENDER"},
    {1089,"MC_PRE_SLOT_RENDER"},
    {1090,"MC_POST_SLOT_RENDER"},
    {1121,"MC_POST_SLOT_INIT"},
    {1122,"MC_POST_SLOT_UPDATE"},
    {1160,"MC_PRE_PLAYER_UPDATE"},
    {1161,"MC_PRE_TEAR_UPDATE"},
    {1162,"MC_PRE_FAMILIAR_UPDATE"},
    {1163,"MC_PRE_BOMB_UPDATE"},
    {1164,"MC_PRE_PICKUP_UPDATE"},
    {1165,"MC_PRE_KNIFE_UPDATE"},
    {1166,"MC_PRE_PROJECTILE_UPDATE"},
    {1167,"MC_PRE_LASER_UPDATE"},
    {1168,"MC_PRE_EFFECT_UPDATE"},
    {1169,"MC_PRE_SLOT_UPDATE"},
    {1210,"MC_POST_MODS_LOADED"},
    {1218,"MC_PRE_PAUSE_SCREEN_RENDER"},
    {1219,"MC_POST_PAUSE_SCREEN_RENDER"},
    {1231,"MC_POST_PLAYER_COLLISION"},
    {1233,"MC_POST_TEAR_COLLISION"},
    {1235,"MC_POST_FAMILIAR_COLLISION"},
    {1237,"MC_POST_BOMB_COLLISION"},
    {1239,"MC_POST_PICKUP_COLLISION"},
    {1270,"MC_POST_BOSS_INTRO_SHOW"},
    {1400,"MC_PRE_GRID_ENTITY_DECORATION_UPDATE"},
    {1401,"MC_POST_GRID_ENTITY_DECORATION_UPDATE"},
    {1402,"MC_PRE_GRID_ENTITY_DOOR_UPDATE"},
    {1403,"MC_POST_GRID_ENTITY_DOOR_UPDATE"},
    {1404,"MC_PRE_GRID_ENTITY_FIRE_UPDATE"},
    {1405,"MC_POST_GRID_ENTITY_FIRE_UPDATE"},
    {1406,"MC_PRE_GRID_ENTITY_GRAVITY_UPDATE"},
    {1407,"MC_POST_GRID_ENTITY_GRAVITY_UPDATE"},
    {1408,"MC_PRE_GRID_ENTITY_LOCK_UPDATE"},
    {1409,"MC_POST_GRID_ENTITY_LOCK_UPDATE"},
    {1410,"MC_PRE_GRID_ENTITY_PIT_UPDATE"},
    {1411,"MC_POST_GRID_ENTITY_PIT_UPDATE"},
    {1412,"MC_PRE_GRID_ENTITY_POOP_UPDATE"},
    {1413,"MC_POST_GRID_ENTITY_POOP_UPDATE"},
    {1414,"MC_PRE_GRID_ENTITY_PRESSUREPLATE_UPDATE"},
    {1415,"MC_POST_GRID_ENTITY_PRESSUREPLATE_UPDATE"},
    {1416,"MC_PRE_GRID_ENTITY_ROCK_UPDATE"},
    {1417,"MC_POST_GRID_ENTITY_ROCK_UPDATE"},
    {1418,"MC_PRE_GRID_ENTITY_SPIKES_UPDATE"},
    {1419,"MC_POST_GRID_ENTITY_SPIKES_UPDATE"},
    {1420,"MC_PRE_GRID_ENTITY_STAIRCASE_UPDATE"},
    {1421,"MC_POST_GRID_ENTITY_STAIRCASE_UPDATE"},
    {1422,"MC_PRE_GRID_ENTITY_STATUE_UPDATE"},
    {1423,"MC_POST_GRID_ENTITY_STATUE_UPDATE"},
    {1424,"MC_PRE_GRID_ENTITY_TELEPORTER_UPDATE"},
    {1425,"MC_POST_GRID_ENTITY_TELEPORTER_UPDATE"},
    {1426,"MC_PRE_GRID_ENTITY_TRAPDOOR_UPDATE"},
    {1427,"MC_POST_GRID_ENTITY_TRAPDOOR_UPDATE"},
    {1428,"MC_PRE_GRID_ENTITY_WEB_UPDATE"},
    {1429,"MC_POST_GRID_ENTITY_WEB_UPDATE"},
    {1430,"MC_PRE_GRID_ENTITY_TNT_UPDATE"},
    {1431,"MC_POST_GRID_ENTITY_TNT_UPDATE"},
    {1432,"MC_PRE_GRID_ENTITY_SPIKES_RENDER"},
    {1433,"MC_POST_GRID_ENTITY_SPIKES_RENDER"},
    {1434,"MC_PRE_GRID_ENTITY_WEB_RENDER"},
    {1435,"MC_POST_GRID_ENTITY_WEB_RENDER"},
    {1436,"MC_PRE_GRID_ENTITY_TNT_RENDER"},
    {1437,"MC_POST_GRID_ENTITY_TNT_RENDER"},
    {1438,"MC_PRE_GRID_ENTITY_TRAPDOOR_RENDER"},
    {1439,"MC_POST_GRID_ENTITY_TRAPDOOR_RENDER"},
    {1440,"MC_PRE_GRID_ENTITY_STAIRCASE_RENDER"},
    {1441,"MC_POST_GRID_ENTITY_STAIRCASE_RENDER"},
    {1444,"MC_PRE_GRID_ENTITY_DECORATION_RENDER"},
    {1445,"MC_POST_GRID_ENTITY_DECORATION_RENDER"},
    {1446,"MC_PRE_GRID_ENTITY_DOOR_RENDER"},
    {1447,"MC_POST_GRID_ENTITY_DOOR_RENDER"},
    {1448,"MC_PRE_GRID_ENTITY_FIRE_RENDER"},
    {1449,"MC_POST_GRID_ENTITY_FIRE_RENDER"},
    {1450,"MC_PRE_GRID_ENTITY_LOCK_RENDER"},
    {1451,"MC_POST_GRID_ENTITY_LOCK_RENDER"},
    {1452,"MC_PRE_GRID_ENTITY_TELEPORTER_RENDER"},
    {1453,"MC_POST_GRID_ENTITY_TELEPORTER_RENDER"},
    {1454,"MC_PRE_GRID_ENTITY_PIT_RENDER"},
    {1455,"MC_POST_GRID_ENTITY_PIT_RENDER"},
    {1456,"MC_PRE_GRID_ENTITY_POOP_RENDER"},
    {1457,"MC_POST_GRID_ENTITY_POOP_RENDER"},
    {1458,"MC_PRE_GRID_ENTITY_ROCK_RENDER"},
    {1459,"MC_POST_GRID_ENTITY_ROCK_RENDER"},
    {1460,"MC_PRE_GRID_ENTITY_PRESSUREPLATE_RENDER"},
    {1461,"MC_POST_GRID_ENTITY_PRESSUREPLATE_RENDER"},
    {1462,"MC_PRE_GRID_ENTITY_WALL_RENDER"},
    {1463,"MC_POST_GRID_ENTITY_WALL_RENDER"},
};
static_assert(sizeof(kCallbacks)/sizeof(kCallbacks[0])==102);
constexpr RepentogonEnumBinding kAliases[]={{"ModCallbacks","MC_HUD_POST_UPDATE",1021}};
constexpr RepentogonApiBinding kApis[]={
    {{0x07020001,ApiDomain::Rng,"RNG","SetSeed",{},0,ThreadAffinity::ManagedCallback,
      ApiMaturity::Experimental},RepentogonRngSetSeed,nullptr,nullptr,true},
    {{0x03020001,ApiDomain::Level,"Level","GetDimension",{},0,ThreadAffinity::ManagedCallback,
      ApiMaturity::Experimental},RepentogonLevelGetDimension},
    {{0x0E020001,ApiDomain::Isaac,"GridEntity","ToTrapDoor",{},0,ThreadAffinity::ManagedCallback,
      ApiMaturity::Experimental},RepentogonGridToTrapDoor},
    {{0x0E020002,ApiDomain::Isaac,"Isaac","IsInGame",{},0,ThreadAffinity::ManagedCallback,
      ApiMaturity::Experimental},RepentogonIsaacIsInGame,nullptr,nullptr,true},
    {{0x04020001,ApiDomain::Room,"Room","SetWaterAmount",{},0,ThreadAffinity::ManagedCallback,
      ApiMaturity::Experimental},RepentogonRoomSetWaterAmount},
    {{0x04020002,ApiDomain::Room,"Room","SetWaterCurrent",{},0,ThreadAffinity::ManagedCallback,
      ApiMaturity::Experimental},RepentogonRoomSetWaterCurrent},
    {{0x0E020100,ApiDomain::Isaac,"ProceduralItemManager","GetProceduralItem",{},0,ThreadAffinity::ManagedCallback,
      ApiMaturity::Experimental},ProceduralItemManagerGetProceduralItem},
    {{0x0E020101,ApiDomain::Isaac,"ProceduralItem","GetTargetItem",{},0,ThreadAffinity::ManagedCallback,
      ApiMaturity::Experimental},ProceduralItemGetTargetItem},
    {{0x0E020102,ApiDomain::Isaac,"ProceduralItem","GetEffectCount",{},0,ThreadAffinity::ManagedCallback,
      ApiMaturity::Experimental},ProceduralItemGetEffectCount},
    {{0x0E020103,ApiDomain::Isaac,"ProceduralItem","GetEffect",{},0,ThreadAffinity::ManagedCallback,
      ApiMaturity::Experimental},ProceduralItemGetEffect},
    {{0x0E020104,ApiDomain::Isaac,"ProceduralItem","GetSpeed",{},0,ThreadAffinity::ManagedCallback,
      ApiMaturity::Experimental},ProceduralItemGetSpeed},
    {{0x0E020105,ApiDomain::Isaac,"ProceduralItem","GetFireDelay",{},0,ThreadAffinity::ManagedCallback,
      ApiMaturity::Experimental},ProceduralItemGetFireDelay},
    {{0x0E020106,ApiDomain::Isaac,"ProceduralItem","GetDamage",{},0,ThreadAffinity::ManagedCallback,
      ApiMaturity::Experimental},ProceduralItemGetDamage},
    {{0x0E020107,ApiDomain::Isaac,"ProceduralItem","GetRange",{},0,ThreadAffinity::ManagedCallback,
      ApiMaturity::Experimental},ProceduralItemGetRange},
    {{0x0E020108,ApiDomain::Isaac,"ProceduralItem","GetShotSpeed",{},0,ThreadAffinity::ManagedCallback,
      ApiMaturity::Experimental},ProceduralItemGetShotSpeed},
    {{0x0E020109,ApiDomain::Isaac,"ProceduralItem","GetLuck",{},0,ThreadAffinity::ManagedCallback,
      ApiMaturity::Experimental},ProceduralItemGetLuck},
    {{0x0E02010A,ApiDomain::Isaac,"ProceduralEffect","GetConditionType",{},0,ThreadAffinity::ManagedCallback,
      ApiMaturity::Experimental},ProceduralEffectGetConditionType},
    {{0x0E02010B,ApiDomain::Isaac,"ProceduralEffect","GetConditionProperty",{},0,ThreadAffinity::ManagedCallback,
      ApiMaturity::Experimental},ProceduralEffectGetConditionProperty},
    {{0x0E02010C,ApiDomain::Isaac,"ProceduralEffect","GetActionType",{},0,ThreadAffinity::ManagedCallback,
      ApiMaturity::Experimental},ProceduralEffectGetActionType},
    {{0x0E02010D,ApiDomain::Isaac,"ProceduralEffect","GetActionProperty",{},0,ThreadAffinity::ManagedCallback,
      ApiMaturity::Experimental},ProceduralEffectGetActionProperty},
};
// A bounded read-only ID map addresses the 102 cached states, not the ordinary ID array.
constexpr auto MakeStateIndices() noexcept {
    std::array<std::uint8_t,1464-1020> indices{};
    for(auto& index:indices)index=255;
    for(std::size_t i=0;i<102;++i)indices[kCallbacks[i].id-1020]=static_cast<std::uint8_t>(i);
    return indices;
}
constexpr auto kStateIndices=MakeStateIndices();
std::array<ExtendedCallbackState*,102> g_States{};
void Reset() noexcept {g_States.fill(nullptr);}

bool Ready() noexcept {
    return g_NativePort&&g_NativePort->ready&&g_NativePort->install&&g_NativePort->ready();
}
int Initialize(lua_State* state) {
    for(std::size_t i=0;i<g_States.size();++i) {
        g_States[i]=FindExtendedCallback(kCallbacks[i].id);
        if(!g_States[i])return luaL_error(state,"REPENTOGON callback state unavailable");
    }
    if(!g_NativePort||!g_NativePort->install||!g_NativePort->install())
        return luaL_error(state,"REPENTOGON callback hooks unavailable");
    RegisterProceduralItemApi(state);
    return 0;
}
}
void SetNativePort(const NativePort* port) noexcept { g_NativePort=port; }
bool UpdatePaused() noexcept {
    return g_ExtendedCallbackDelivery&&g_NativePort&&g_NativePort->updatePaused&&g_NativePort->updatePaused();
}
bool HasSpriteValidator() noexcept {return g_NativePort&&g_NativePort->spriteAlive;}
bool CallbackSpriteAlive(std::uintptr_t address) noexcept {
    return address&&HasSpriteValidator()&&g_NativePort->spriteAlive(address);
}
bool HasNativePort() noexcept { return g_NativePort!=nullptr; }
constinit const RepentogonBatch kCallbackBatch{"callbacks",kApis,sizeof(kApis)/sizeof(kApis[0]),kAliases,1,kCallbacks,102,Initialize,Reset,Ready};
const RepentogonBatch& CallbackBatch() noexcept {return kCallbackBatch;}
const ExtendedCallbackState* FindCallbackState(std::uint32_t id) noexcept {
    if(id>=1020&&id<1464) {
        const auto index=kStateIndices[id-1020];
        if(index!=255&&g_States[index])return g_States[index];
    }
    return FindExtendedCallback(id);
}
bool Listening(std::uint32_t id) noexcept {
    if(!g_ExtendedCallbackDelivery||!g_ExtendedCallbackEnabledCount)return false;
    const auto* state=FindCallbackState(id);
    return state&&state->enabled;
}
Result Dispatch(const Event& event) noexcept {
    if(!Listening(event.id))return {};
    return LuaRuntime::DispatchRepentogonCallback(event);
}
} // namespace isaac::runtime::repentogon
