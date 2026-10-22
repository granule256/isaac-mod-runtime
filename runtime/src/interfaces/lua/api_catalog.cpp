#include "interfaces/lua/api_catalog.hpp"

#include <cstring>

namespace isaac::runtime {
namespace {

constexpr std::uint32_t MakeId(ApiDomain domain, std::uint8_t ownerGroup,
                               std::uint16_t sequence) noexcept {
    return (static_cast<std::uint32_t>(domain) << 24) |
           (static_cast<std::uint32_t>(ownerGroup) << 16) |
           static_cast<std::uint32_t>(sequence);
}

constexpr ApiVersion kV1{1, 0};

bool SameText(const char* left, const char* right) noexcept {
    if (left == nullptr || right == nullptr) {
        return false;
    }
    return std::strcmp(left, right) == 0;
}

bool EmptyText(const char* text) noexcept {
    return text == nullptr || text[0] == '\0';
}

// The table is the single list of Lua APIs this Runtime exposes. Maturity is
// deliberately conservative: only APIs with hardware evidence are marked
// HardwareVerified, and persistence stays Experimental while Stage145 is open.
constexpr LuaApiDescriptor kDefaultApis[] = {
    // 第七批：固定PC版本真实缺口，按实际数量计数。
    {MakeId(ApiDomain::Game,1,0x17A9),ApiDomain::Game,"Game","SpawnEntityDesc",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x17D0),ApiDomain::Isaac,"GridEntityPoop","ReduceSpawnRate",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x17A7),ApiDomain::Isaac,"Isaac","ScreenToWorldDistance",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x17A8),ApiDomain::Isaac,"Isaac","GetScreenPointScale",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x17C0),ApiDomain::Isaac,"EntityLaser","GetSamples",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x17C1),ApiDomain::Isaac,"EntityLaser","GetNonOptimizedSamples",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x17C2),ApiDomain::Isaac,"EntityNPC","QueryNPCsType",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x17C3),ApiDomain::Isaac,"EntityNPC","QueryNPCsSpawnerType",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x17C4),ApiDomain::Isaac,"EntityNPC","QueryNPCsGroup",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Room,1,0x17C5),ApiDomain::Room,"Room","GetEntities",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x17C6),ApiDomain::Isaac,"EntityList","Get",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x17C7),ApiDomain::Isaac,"EntityList","__len",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x17C8),ApiDomain::Isaac,"VectorList","Get",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x17C9),ApiDomain::Isaac,"VectorList","__len",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Game,1,0x17A3),ApiDomain::Game,"Game","ShowFortune",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Game,1,0x17A4),ApiDomain::Game,"Game","ShowRule",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x17A5),ApiDomain::Isaac,"Isaac","RemoveModData",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x17A6),ApiDomain::Isaac,"Isaac","GetCurseIdByName",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x17A0),ApiDomain::Isaac,"Entity","Render",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x17A1),ApiDomain::Isaac,"Entity","PostRender",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x17A2),ApiDomain::Isaac,"GridEntity","Render",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Game,1,0x178A),ApiDomain::Game,"Game","GetFont",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Game,1,0x178B),ApiDomain::Game,"Game","GetAmbush",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Game,1,0x178C),ApiDomain::Game,"Game","GetItemOverlay",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x1700),ApiDomain::Isaac,"EntityPlayer","AnimatePill",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x1701),ApiDomain::Isaac,"EntityPlayer","AnimateTrinket",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x1702),ApiDomain::Isaac,"EntityPlayer","SwapActiveItems",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x1703),ApiDomain::Isaac,"EntityPlayer","TryRemoveCollectibleCostume",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x1704),ApiDomain::Isaac,"EntityPlayer","GetCostumeNullPos",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x1705),ApiDomain::Isaac,"EntityPlayer","ReplaceCostumeSprite",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x1706),ApiDomain::Isaac,"EntityPlayer","QueueExtraAnimation",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x1707),ApiDomain::Isaac,"EntityPlayer","GetLastDamageSource",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x1708),ApiDomain::Isaac,"EntityPlayer","GetPocketItem",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Room,1,0x1780),ApiDomain::Room,"Room","ScreenWrapPosition",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x1781),ApiDomain::Isaac,"EntityLaser","CalculateEndPoint",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Seed,1,0x1782),ApiDomain::Seed,"Seeds","GetSeedEffect",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Seed,1,0x1783),ApiDomain::Seed,"Seeds","IsSpecialSeed",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x1784),ApiDomain::Isaac,"Isaac","AddPillEffectToPool",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x1785),ApiDomain::Isaac,"Isaac","WorldToScreenDistance",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Room,1,0x1786),ApiDomain::Room,"Room","GetLRoomAreaDesc",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Room,1,0x1787),ApiDomain::Room,"Room","GetLRoomTileDesc",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::ItemPool,1,0x1788),ApiDomain::ItemPool,"ItemPool","AddRoomBlacklist",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Level,1,0x1789),ApiDomain::Level,"Level","GetDevilAngelRoomRNG",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Room,1,0x163E),ApiDomain::Room,"Room","GetDeliriumDistance",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x163B),ApiDomain::Isaac,"RoomConfigEntries","Get",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x163C),ApiDomain::Isaac,"RoomConfigEntries","__len",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x163D),ApiDomain::Isaac,"RoomConfigSpawns","__len",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Sprite,1,0x1638),ApiDomain::Sprite,"Sprite","GetOverlayAnimation",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Sprite,1,0x1639),ApiDomain::Sprite,"Sprite","SetOverlayRenderPriority",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Global,1,0x163A),ApiDomain::Global,"Global","RandomVector",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Room,1,0x1630),ApiDomain::Room,"Room","GetShopLevel",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Room,1,0x1631),ApiDomain::Room,"Room","GetLavaIntensity",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Room,1,0x1632),ApiDomain::Room,"Room","HasSlowDown",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Room,1,0x1633),ApiDomain::Room,"Room","SetSlowDown",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Room,1,0x1634),ApiDomain::Room,"Room","IsFirstEnemyDead",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Room,1,0x1635),ApiDomain::Room,"Room","SetFirstEnemyDead",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Room,1,0x1636),ApiDomain::Room,"Room","InvalidatePickupVision",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Room,1,0x1637),ApiDomain::Room,"Room","EmitBloodFromWalls",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x1628),ApiDomain::Isaac,"GridEntityDoor","IsBusted",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x1629),ApiDomain::Isaac,"GridEntityDoor","IsLocked",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x162A),ApiDomain::Isaac,"GridEntityDoor","IsKeyFamiliarTarget",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x162B),ApiDomain::Isaac,"GridEntityDoor","GetSpriteOffset",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x162C),ApiDomain::Isaac,"GridEntityRock","GetRubbleAnim",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Game,1,0x162D),ApiDomain::Game,"Game","GetLastDevilRoomStage",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Game,1,0x162E),ApiDomain::Game,"Game","GetLastLevelWithDamage",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Game,1,0x162F),ApiDomain::Game,"Game","GetLastLevelWithoutHalfHp",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Game,1,0x1622),ApiDomain::Game,"Game","BombDamage",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Game,1,0x1623),ApiDomain::Game,"Game","BombExplosionEffects",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Game,1,0x1624),ApiDomain::Game,"Game","BombTearflagEffects",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Game,1,0x1625),ApiDomain::Game,"Game","UpdateStrangeAttractor",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Game,1,0x1626),ApiDomain::Game,"Game","Render",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Room,1,0x1627),ApiDomain::Room,"Room","Render",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x1621),ApiDomain::Isaac,"EntityPtr","SetReference",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x1617),ApiDomain::Isaac,"ItemConfig","GetCards",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x1618),ApiDomain::Isaac,"ItemConfig","GetPillEffects",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x1619),ApiDomain::Isaac,"ItemConfig","GetNullItems",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x161A),ApiDomain::Isaac,"ItemConfig_Item","IsNull",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x161B),ApiDomain::Isaac,"ItemConfig","ShouldAddCostumeOnPickup",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x161C),ApiDomain::Isaac,"CardConfigList","Get",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x161D),ApiDomain::Isaac,"CardConfigList","__len",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x161E),ApiDomain::Isaac,"PillConfigList","Get",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x161F),ApiDomain::Isaac,"PillConfigList","__len",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x1640),ApiDomain::Isaac,"EntityPlayer","GetTearHitParams",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x1601),ApiDomain::Isaac,"EntityPlayer","GetActiveSubCharge",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x1602),ApiDomain::Isaac,"EntityPlayer","GetBombVariant",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x1603),ApiDomain::Isaac,"EntityPlayer","AreOpposingShootDirectionsPressed",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x1604),ApiDomain::Isaac,"EntityPlayer","HasWeaponType",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x1605),ApiDomain::Isaac,"EntityPlayer","GetMultiShotParams",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x1606),ApiDomain::Isaac,"EntityPlayer","GetMultiShotPositionVelocity",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x1600),ApiDomain::Isaac,"ItemConfigCard","IsCard",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::ItemPool,1,0x1601),ApiDomain::ItemPool,"ItemPool","IdentifyPill",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    // 第四批主审更正：40方法+60字段；未证明的CurveStrength另留候选。
    {MakeId(ApiDomain::Seed,1,0x1527),ApiDomain::Seed,"Seeds","IsStringValidSeed",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    // 第四批40新方法；60个公共字段单列布局/消费清单，全部Experimental。
    {MakeId(ApiDomain::Isaac,1,0x1500),ApiDomain::Isaac,"EntityPlayer","RenderGlow",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x1501),ApiDomain::Isaac,"EntityNPC","KillUnique",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x1502),ApiDomain::Isaac,"EntityNPC","MakeChampion",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x1503),ApiDomain::Isaac,"EntityNPC","MakeSplat",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x1504),ApiDomain::Isaac,"EntityPickup","TryOpenChest",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x1505),ApiDomain::Isaac,"Entity","GetBossID",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x1506),ApiDomain::Isaac,"Entity","SetSpriteOverlayFrame",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x1507),ApiDomain::Isaac,"EntityEffect","FollowParent",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x1508),ApiDomain::Isaac,"EntityEffect","SetDamageSource",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x1509),ApiDomain::Isaac,"EntityEffect","SetRadii",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x150A),ApiDomain::Isaac,"EntityEffect","SetTimeout",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x150B),ApiDomain::Isaac,"EntityKnife","GetKnifeDistance",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x150C),ApiDomain::Isaac,"EntityKnife","GetKnifeVelocity",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x150D),ApiDomain::Isaac,"EntityKnife","SetPathFollowSpeed",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x150E),ApiDomain::Isaac,"EntityLaser","GetEndPoint",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x150F),ApiDomain::Isaac,"EntityLaser","IsCircleLaser",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x1510),ApiDomain::Isaac,"EntityLaser","IsSampleLaser",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x1511),ApiDomain::Isaac,"EntityLaser","SetBlackHpDropChance",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x1512),ApiDomain::Isaac,"EntityLaser","SetHomingType",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x1513),ApiDomain::Isaac,"EntityLaser","SetMultidimensionalTouched",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x1514),ApiDomain::Isaac,"EntityLaser","SetOneHit",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x1515),ApiDomain::Isaac,"EntityLaser","SetTimeout",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x1516),ApiDomain::Isaac,"EntityNPC","ResetPathFinderTarget",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x1517),ApiDomain::Isaac,"EntityPlayer","RenderTop",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x1518),ApiDomain::Isaac,"Entity","RenderShadowLayer",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x1519),ApiDomain::Isaac,"EntityProjectile","AddChangeFlags",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x151A),ApiDomain::Isaac,"EntityProjectile","AddFallingAccel",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x151B),ApiDomain::Isaac,"EntityProjectile","AddFallingSpeed",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x151C),ApiDomain::Isaac,"EntityProjectile","AddHeight",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x151D),ApiDomain::Isaac,"EntityProjectile","AddProjectileFlags",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x151E),ApiDomain::Isaac,"EntityProjectile","AddScale",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x151F),ApiDomain::Isaac,"EntityProjectile","ClearProjectileFlags",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x1520),ApiDomain::Isaac,"EntityTear","SetKnockbackMultiplier",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x1521),ApiDomain::Isaac,"EntityTear","SetParentOffset",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x1522),ApiDomain::Isaac,"EntityTear","SetWaitFrames",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x1523),ApiDomain::Isaac,"EntityNPC","FireProjectiles",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x1524),ApiDomain::Isaac,"EntityNPC","FireBossProjectiles",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Seed,1,0x1525),ApiDomain::Seed,"Seeds","Seed2String",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Seed,1,0x1526),ApiDomain::Seed,"Seeds","String2Seed",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},

    // 第三批其余50，完整原件/实际行为约束，全Experimental。
    {MakeId(ApiDomain::Isaac,1,0x1400),ApiDomain::Isaac,"EntityPlayer","CanShoot",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x1401),ApiDomain::Isaac,"EntityPlayer","CanTurnHead",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x1402),ApiDomain::Isaac,"EntityPlayer","RenderBody",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x1403),ApiDomain::Isaac,"EntityPlayer","GetActiveWeaponEntity",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x1404),ApiDomain::Isaac,"EntityPlayer","GetBatteryCharge",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x1405),ApiDomain::Isaac,"EntityPlayer","GetBodyColor",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x1406),ApiDomain::Isaac,"EntityPlayer","GetHeadColor",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x1407),ApiDomain::Isaac,"EntityPlayer","GetItemState",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x1408),ApiDomain::Isaac,"EntityPlayer","GetJarFlies",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x1409),ApiDomain::Isaac,"EntityPlayer","GetLastActionTriggers",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x140A),ApiDomain::Isaac,"EntityPlayer","GetLastDamageFlags",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x140B),ApiDomain::Isaac,"EntityPlayer","GetLastDirection",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x140C),ApiDomain::Isaac,"EntityPlayer","GetMovementVector",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x140D),ApiDomain::Isaac,"EntityPlayer","GetNumBlueFlies",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x140E),ApiDomain::Isaac,"EntityPlayer","GetNumBlueSpiders",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x140F),ApiDomain::Isaac,"EntityPlayer","GetNumGigaBombs",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x1410),ApiDomain::Isaac,"EntityPlayer","GetRecentMovementVector",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x1411),ApiDomain::Isaac,"EntityPlayer","GetSmoothBodyRotation",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x1412),ApiDomain::Isaac,"EntityPlayer","GetTearPoisonDamage",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x1413),ApiDomain::Isaac,"EntityPlayer","GetTearRangeModifier",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x1414),ApiDomain::Isaac,"EntityPlayer","GetTotalDamageTaken",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x1415),ApiDomain::Isaac,"EntityPlayer","GetTractorBeam",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x1416),ApiDomain::Isaac,"EntityPlayer","GetVelocityBeforeUpdate",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x1417),ApiDomain::Isaac,"EntityPlayer","HasCurseMistEffect",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x1418),ApiDomain::Isaac,"EntityPlayer","IsItemQueueEmpty",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x1419),ApiDomain::Isaac,"EntityPlayer","IsP2Appearing",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x141A),ApiDomain::Isaac,"EntityPlayer","SetBloodCharge",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x141B),ApiDomain::Isaac,"EntityPlayer","SetSoulCharge",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x141C),ApiDomain::Isaac,"EntityPlayer","RenderHead",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x141D),ApiDomain::Isaac,"EntityPlayer","AddControlsCooldown",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x141E),ApiDomain::Isaac,"EntityPlayer","AreControlsEnabled",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x142A),ApiDomain::Isaac,"EntityKnife","GetRenderZ",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x142B),ApiDomain::Isaac,"EntityLaser","GetRenderZ",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x142C),ApiDomain::Isaac,"EntityNPC","GetAliveEnemyCount",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x1437),ApiDomain::Isaac,"EntityTear","ClearTearFlags",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x1438),ApiDomain::Isaac,"EntityTear","HasTearFlags",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x143A),ApiDomain::Isaac,"EntityBomb","ClearTearFlags",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x143D),ApiDomain::Isaac,"EntityBomb","HasTearFlags",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x143F),ApiDomain::Isaac,"EntityKnife","ClearTearFlags",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x1441),ApiDomain::Isaac,"EntityLaser","ClearTearFlags",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x1447),ApiDomain::Isaac,"EntityLaser","HasTearFlags",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x144A),ApiDomain::Isaac,"EntityKnife","HasTearFlags",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Seed,1,0x1450),ApiDomain::Seed,"Seeds","ClearSeedEffects",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Seed,1,0x1453),ApiDomain::Seed,"Seeds","GetStartSeedString",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Seed,1,0x1455),ApiDomain::Seed,"Seeds","IsSeedComboBanned",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x145F),ApiDomain::Isaac,"EntityEffect","IsPlayerCreep",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x1460),ApiDomain::Isaac,"ItemConfig","IsValidCollectible",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x1461),ApiDomain::Isaac,"EntityNPC","CalcTargetPosition",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x1462),ApiDomain::Isaac,"EntityNPC","CanBeDamagedFromVelocity",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x1463),ApiDomain::Isaac,"EntityNPC","CanReroll",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},

    // 第三批World16实际字段，完整PC/NS同状态锚与布局指纹。
    {MakeId(ApiDomain::Level,1,0x145B),ApiDomain::Level,"Level","GetRoomCount",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Level,1,0x145C),ApiDomain::Level,"Level","IsDevilRoomDisabled",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Level,1,0x1457),ApiDomain::Level,"Level","DisableDevilRoom",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Level,1,0x145E),ApiDomain::Level,"Level","SetHeartPicked",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Level,1,0x145A),ApiDomain::Level,"Level","GetHeartPicked",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Level,1,0x145D),ApiDomain::Level,"Level","SetCanSeeEverything",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Level,1,0x1459),ApiDomain::Level,"Level","GetDungeonPlacementSeed",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Level,1,0x1456),ApiDomain::Level,"Level","AddAngelRoomChance",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Level,1,0x1458),ApiDomain::Level,"Level","GetAngelRoomChance",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x144D),ApiDomain::Isaac,"PathFinder","HasDirectPath",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x144C),ApiDomain::Isaac,"PathFinder","GetEvadeMovementCountdown",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x144E),ApiDomain::Isaac,"PathFinder","SetCanCrushRocks",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Seed,1,0x1451),ApiDomain::Seed,"Seeds","ClearStartSeed",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Seed,1,0x1454),ApiDomain::Seed,"Seeds","IsInitialized",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Seed,1,0x1452),ApiDomain::Seed,"Seeds","GetPlayerInitSeed",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Seed,1,0x144F),ApiDomain::Seed,"Seeds","CountSeedEffects",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},

    // 第三批Room13，已核原件字段/状态位/网格运算。
    {MakeId(ApiDomain::Room,1,0x1442),ApiDomain::Room,"Room","IsInitialized",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Room,1,0x1444),ApiDomain::Room,"Room","KeepDoorsClosed",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Room,1,0x143C),ApiDomain::Room,"Room","GetSecondBossID",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Room,1,0x143B),ApiDomain::Room,"Room","GetRedHeartDamage",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Room,1,0x1448),ApiDomain::Room,"Room","SetRedHeartDamage",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Room,1,0x1440),ApiDomain::Room,"Room","HasTriggerPressurePlates",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Room,1,0x143E),ApiDomain::Room,"Room","GetWaterCurrent",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Room,1,0x144B),ApiDomain::Room,"Room","StopRain",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Room,1,0x1446),ApiDomain::Room,"Room","SetCardAgainstHumanity",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Room,1,0x1445),ApiDomain::Room,"Room","SetAmbushDone",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Room,1,0x1449),ApiDomain::Room,"Room","SetSacrificeDone",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Room,1,0x1443),ApiDomain::Room,"Room","IsSacrificeDone",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Room,1,0x1439),ApiDomain::Room,"Room","GetGridPathFromPos",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},

    // 第三批已核PC/NS实际字段与运算，本阶段Game21。
    {MakeId(ApiDomain::Game,1,0x1433),ApiDomain::Game,"Game","SetLastDevilRoomStage",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Game,1,0x1422),ApiDomain::Game,"Game","AddTreasureRoomsVisited",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Game,1,0x1431),ApiDomain::Game,"Game","GetTreasureRoomVisitCount",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Game,1,0x1421),ApiDomain::Game,"Game","AddStageWithoutHeartsPicked",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Game,1,0x142F),ApiDomain::Game,"Game","GetStagesWithoutHeartsPicked",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Game,1,0x1420),ApiDomain::Game,"Game","AddStageWithoutDamage",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Game,1,0x1425),ApiDomain::Game,"Game","ClearStagesWithoutDamage",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Game,1,0x142E),ApiDomain::Game,"Game","GetStagesWithoutDamage",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Game,1,0x1427),ApiDomain::Game,"Game","GetDevilRoomDeals",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Game,1,0x1429),ApiDomain::Game,"Game","GetDonationModGreed",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Game,1,0x1428),ApiDomain::Game,"Game","GetDonationModAngel",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Game,1,0x1424),ApiDomain::Game,"Game","ClearDonationModGreed",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Game,1,0x1423),ApiDomain::Game,"Game","ClearDonationModAngel",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Game,1,0x1434),ApiDomain::Game,"Game","SetLastLevelWithDamage",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Game,1,0x142D),ApiDomain::Game,"Game","GetNumEncounteredBosses",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Game,1,0x1435),ApiDomain::Game,"Game","SetLastLevelWithoutHalfHp",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Game,1,0x1436),ApiDomain::Game,"Game","GetScreenShakeCountdown",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Game,1,0x1426),ApiDomain::Game,"Game","GetDarknessModifier",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Game,1,0x1430),ApiDomain::Game,"Game","GetTargetDarkness",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Game,1,0x141F),ApiDomain::Game,"Game","AddPixelation",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Game,1,0x1432),ApiDomain::Game,"Game","HasHallucination",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},

    // 2026-10-14：100API第一组20，PC/NS原件及行为见player20/report.md。
    {MakeId(ApiDomain::Isaac, 1, 0x1200), ApiDomain::Isaac, "EntityPlayer", "AddBombs", kV1, 0, ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x1201), ApiDomain::Isaac, "EntityPlayer", "AddGigaBombs", kV1, 0, ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x1202), ApiDomain::Isaac, "EntityPlayer", "AddJarFlies", kV1, 0, ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x1203), ApiDomain::Isaac, "EntityPlayer", "AddPoopMana", kV1, 0, ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x1204), ApiDomain::Isaac, "EntityPlayer", "AddDeadEyeCharge", kV1, 0, ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x1205), ApiDomain::Isaac, "EntityPlayer", "ClearDeadEyeCharge", kV1, 0, ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x1206), ApiDomain::Isaac, "EntityPlayer", "ClearCostumes", kV1, 0, ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x1207), ApiDomain::Isaac, "EntityPlayer", "ClearTemporaryEffects", kV1, 0, ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x1208), ApiDomain::Isaac, "EntityPlayer", "GetEffectiveBloodCharge", kV1, 0, ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x1209), ApiDomain::Isaac, "EntityPlayer", "GetEffectiveSoulCharge", kV1, 0, ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x120A), ApiDomain::Isaac, "EntityPlayer", "GetMaxPocketItems", kV1, 0, ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x120B), ApiDomain::Isaac, "EntityPlayer", "GetMaxPoopMana", kV1, 0, ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x120C), ApiDomain::Isaac, "EntityPlayer", "HasTimedItem", kV1, 0, ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x120D), ApiDomain::Isaac, "EntityPlayer", "IsHeldItemVisible", kV1, 0, ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x120E), ApiDomain::Isaac, "EntityPlayer", "RemoveBlueFly", kV1, 0, ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x120F), ApiDomain::Isaac, "EntityPlayer", "RemoveBlueSpider", kV1, 0, ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x1210), ApiDomain::Isaac, "EntityPlayer", "CanAddCollectible", kV1, 0, ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x1211), ApiDomain::Isaac, "EntityPlayer", "AnimateLightTravel", kV1, 0, ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x1212), ApiDomain::Isaac, "EntityPlayer", "TryUseKey", kV1, 0, ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x1213), ApiDomain::Isaac, "EntityPlayer", "GetGreedDonationBreakChance", kV1, 0, ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},

    // 2026-10-14：42个房间/楼层/物品池真实调用，证据main80。
    {MakeId(ApiDomain::ItemPool, 1, 0x1231), ApiDomain::ItemPool, "ItemPool", "AddBibleUpgrade", kV1, 0, ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::ItemPool, 1, 0x1232), ApiDomain::ItemPool, "ItemPool", "ForceAddPillEffect", kV1, 0, ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::ItemPool, 1, 0x1233), ApiDomain::ItemPool, "ItemPool", "GetCard", kV1, 0, ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::ItemPool, 1, 0x1234), ApiDomain::ItemPool, "ItemPool", "GetPill", kV1, 0, ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::ItemPool, 1, 0x1235), ApiDomain::ItemPool, "ItemPool", "GetTrinket", kV1, 0, ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::ItemPool, 1, 0x1236), ApiDomain::ItemPool, "ItemPool", "RemoveTrinket", kV1, 0, ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::ItemPool, 1, 0x1237), ApiDomain::ItemPool, "ItemPool", "ResetRoomBlacklist", kV1, 0, ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::ItemPool, 1, 0x1238), ApiDomain::ItemPool, "ItemPool", "ResetTrinkets", kV1, 0, ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Level, 1, 0x1239), ApiDomain::Level, "Level", "ApplyBlueMapEffect", kV1, 0, ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Level, 1, 0x123A), ApiDomain::Level, "Level", "ApplyCompassEffect", kV1, 0, ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Level, 1, 0x123B), ApiDomain::Level, "Level", "ApplyMapEffect", kV1, 0, ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Level, 1, 0x123C), ApiDomain::Level, "Level", "CanOpenChallengeRoom", kV1, 0, ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Level, 1, 0x123D), ApiDomain::Level, "Level", "CanSpawnDevilRoom", kV1, 0, ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Level, 1, 0x123E), ApiDomain::Level, "Level", "CanStageHaveCurseOfLabyrinth", kV1, 0, ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Level, 1, 0x123F), ApiDomain::Level, "Level", "ChangeRoom", kV1, 0, ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Level, 1, 0x1242), ApiDomain::Level, "Level", "InitializeDevilAngelRoom", kV1, 0, ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Level, 1, 0x1243), ApiDomain::Level, "Level", "MakeRedRoomDoor", kV1, 0, ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Level, 1, 0x1244), ApiDomain::Level, "Level", "RemoveCompassEffect", kV1, 0, ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Level, 1, 0x1245), ApiDomain::Level, "Level", "SetRedHeartDamage", kV1, 0, ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Level, 1, 0x1246), ApiDomain::Level, "Level", "ShowMap", kV1, 0, ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Level, 1, 0x1247), ApiDomain::Level, "Level", "ShowName", kV1, 0, ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Level, 1, 0x1248), ApiDomain::Level, "Level", "UncoverHiddenDoor", kV1, 0, ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Room, 1, 0x1249), ApiDomain::Room, "Room", "DamageGrid", kV1, 0, ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Room, 1, 0x124A), ApiDomain::Room, "Room", "GetBrokenWatchState", kV1, 0, ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Room, 1, 0x124B), ApiDomain::Room, "Room", "GetDevilRoomChance", kV1, 0, ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Room, 1, 0x124C), ApiDomain::Room, "Room", "GetDungeonRockIdx", kV1, 0, ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Room, 1, 0x124D), ApiDomain::Room, "Room", "GetLightingAlpha", kV1, 0, ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Room, 1, 0x124E), ApiDomain::Room, "Room", "GetRandomTileIndex", kV1, 0, ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Room, 1, 0x124F), ApiDomain::Room, "Room", "HasLava", kV1, 0, ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Room, 1, 0x1250), ApiDomain::Room, "Room", "HasWater", kV1, 0, ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Room, 1, 0x1251), ApiDomain::Room, "Room", "IsLShapedRoom", kV1, 0, ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Room, 1, 0x1252), ApiDomain::Room, "Room", "RespawnEnemies", kV1, 0, ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Room, 1, 0x1253), ApiDomain::Room, "Room", "SetBrokenWatchState", kV1, 0, ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Room, 1, 0x1254), ApiDomain::Room, "Room", "ShopReshuffle", kV1, 0, ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Room, 1, 0x1255), ApiDomain::Room, "Room", "ShopRestockFull", kV1, 0, ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Room, 1, 0x1256), ApiDomain::Room, "Room", "ShopRestockPartial", kV1, 0, ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Room, 1, 0x1257), ApiDomain::Room, "Room", "TriggerClear", kV1, 0, ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Room, 1, 0x1258), ApiDomain::Room, "Room", "TrySpawnBlueWombDoor", kV1, 0, ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Room, 1, 0x1259), ApiDomain::Room, "Room", "TrySpawnBossRushDoor", kV1, 0, ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Room, 1, 0x125A), ApiDomain::Room, "Room", "TrySpawnMegaSatanRoomDoor", kV1, 0, ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Room, 1, 0x125B), ApiDomain::Room, "Room", "TrySpawnSecretExit", kV1, 0, ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Room, 1, 0x125C), ApiDomain::Room, "Room", "TrySpawnTheVoidDoor", kV1, 0, ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},

    {MakeId(ApiDomain::Level, 1, 0x1240), ApiDomain::Level, "Level", "GetCurseName", kV1, 0, ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Level, 1, 0x1241), ApiDomain::Level, "Level", "GetName", kV1, 0, ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x1214), ApiDomain::Isaac, "Entity", "BloodExplode", kV1, 0, ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x1215), ApiDomain::Isaac, "Entity", "GetLastParent", kV1, 0, ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x1216), ApiDomain::Isaac, "Entity", "GetLastChild", kV1, 0, ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x1217), ApiDomain::Isaac, "Entity", "HasFullHealth", kV1, 0, ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x1218), ApiDomain::Isaac, "Entity", "IsFrame", kV1, 0, ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x1219), ApiDomain::Isaac, "EntityFamiliar", "AddCoins", kV1, 0, ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x121A), ApiDomain::Isaac, "EntityFamiliar", "AddHearts", kV1, 0, ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x121B), ApiDomain::Isaac, "EntityFamiliar", "AddKeys", kV1, 0, ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x121C), ApiDomain::Isaac, "EntityFamiliar", "RemoveFromFollowers", kV1, 0, ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x121D), ApiDomain::Isaac, "EntityFamiliar", "RemoveFromDelayed", kV1, 0, ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x121E), ApiDomain::Isaac, "EntityFamiliar", "AddToDelayed", kV1, 0, ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x121F), ApiDomain::Isaac, "EntityFamiliar", "MoveDelayed", kV1, 0, ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x1220), ApiDomain::Isaac, "EntityFamiliar", "MoveDiagonally", kV1, 0, ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x1221), ApiDomain::Isaac, "EntityFamiliar", "PlayChargeAnim", kV1, 0, ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x1222), ApiDomain::Isaac, "EntityFamiliar", "PlayFloatAnim", kV1, 0, ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x1223), ApiDomain::Isaac, "EntityFamiliar", "PlayShootAnim", kV1, 0, ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x1224), ApiDomain::Isaac, "EntityFamiliar", "Shoot", kV1, 0, ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x1225), ApiDomain::Isaac, "EntityPickup", "PlayPickupSound", kV1, 0, ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x1226), ApiDomain::Isaac, "EntityPickup", "PlayDropSound", kV1, 0, ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x1227), ApiDomain::Isaac, "EntityPickup", "AppearFast", kV1, 0, ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x1228), ApiDomain::Isaac, "EntityPickup", "GetCoinValue", kV1, 0, ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x1229), ApiDomain::Isaac, "GridEntity", "Hurt", kV1, 0, ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x122A), ApiDomain::Isaac, "GridEntityDoor", "CanBlowOpen", kV1, 0, ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x122B), ApiDomain::Isaac, "GridEntityDoor", "SetLocked", kV1, 0, ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x122C), ApiDomain::Isaac, "GridEntityDoor", "SetRoomTypes", kV1, 0, ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x122D), ApiDomain::Isaac, "GridEntityDoor", "SpawnDust", kV1, 0, ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x122E), ApiDomain::Isaac, "GridEntityRock", "GetBigRockFrame", kV1, 0, ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x122F), ApiDomain::Isaac, "GridEntityRock", "SetBigRockFrame", kV1, 0, ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x1230), ApiDomain::Isaac, "GridEntityRock", "UpdateAnimFrame", kV1, 0, ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x125D), ApiDomain::Isaac, "Color", "SetOffset", kV1, 0, ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x125E), ApiDomain::Isaac, "Color", "SetTint", kV1, 0, ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x125F), ApiDomain::Isaac, "Color", "Reset", kV1, 0, ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Sprite, 1, 0x1260), ApiDomain::Sprite, "Sprite", "Reload", kV1, 0, ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Sprite, 1, 0x1261), ApiDomain::Sprite, "Sprite", "RemoveOverlay", kV1, 0, ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Music, 1, 0x1262), ApiDomain::Music, "MusicManager", "Fadein", kV1, 0, ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Music, 1, 0x1263), ApiDomain::Music, "MusicManager", "Fadeout", kV1, 0, ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    // 2026-10-14第二批100，证据dist/apis200-20261014。
    {MakeId(ApiDomain::Isaac,1,0x1300),ApiDomain::Isaac,"Entity","HasCommonParentWithEntity",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x1301),ApiDomain::Isaac,"Entity","SetSize",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x1302),ApiDomain::Isaac,"EntityFamiliar","GetOrbitDistance",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x1303),ApiDomain::Isaac,"EntityFamiliar","PickEnemyTarget",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x1304),ApiDomain::Isaac,"EntityKnife","Reset",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x1305),ApiDomain::Isaac,"EntityKnife","Shoot",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x1306),ApiDomain::Isaac,"EntityPlayer","AddCurseMistEffect",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x1307),ApiDomain::Isaac,"EntityPlayer","AddDollarBillEffect",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x1308),ApiDomain::Isaac,"EntityPlayer","AddPlayerFormCostume",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x1309),ApiDomain::Isaac,"EntityPlayer","AnimatePitfallIn",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x130A),ApiDomain::Isaac,"EntityPlayer","AnimatePitfallOut",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x130B),ApiDomain::Isaac,"EntityPlayer","AnimateTeleport",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x130C),ApiDomain::Isaac,"EntityPlayer","DoZitEffect",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x130D),ApiDomain::Isaac,"EntityPlayer","DropPocketItem",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x130E),ApiDomain::Isaac,"EntityPlayer","FireBrimstone",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x130F),ApiDomain::Isaac,"EntityPlayer","FireDelayedBrimstone",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x1310),ApiDomain::Isaac,"EntityPlayer","FireKnife",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x1311),ApiDomain::Isaac,"EntityPlayer","FireTechXLaser",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x1312),ApiDomain::Isaac,"EntityPlayer","GetBombFlags",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x1313),ApiDomain::Isaac,"EntityPlayer","GetFlyingOffset",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x1314),ApiDomain::Isaac,"EntityPlayer","GetLaserOffset",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x1315),ApiDomain::Isaac,"EntityPlayer","GetNPCTarget",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x1316),ApiDomain::Isaac,"EntityPlayer","HasInvincibility",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x1317),ApiDomain::Isaac,"EntityPlayer","InitBabySkin",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x1318),ApiDomain::Isaac,"EntityPlayer","IsFullSpriteRendering",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x1319),ApiDomain::Isaac,"EntityPlayer","IsPosInSpotLight",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x131A),ApiDomain::Isaac,"EntityPlayer","PlayExtraAnimation",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x131B),ApiDomain::Isaac,"EntityPlayer","QueueItem",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x131C),ApiDomain::Isaac,"EntityPlayer","RemoveCurseMistEffect",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x131D),ApiDomain::Isaac,"EntityPlayer","RemoveSkinCostume",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x131E),ApiDomain::Isaac,"EntityPlayer","ResetItemState",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x131F),ApiDomain::Isaac,"EntityPlayer","RespawnFamiliars",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x1320),ApiDomain::Isaac,"EntityPlayer","ShootRedCandle",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x1321),ApiDomain::Isaac,"EntityPlayer","SpawnMawOfVoid",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x1322),ApiDomain::Isaac,"EntityPlayer","ThrowFriendlyDip",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x1323),ApiDomain::Isaac,"EntityPlayer","TriggerBookOfVirtues",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x1324),ApiDomain::Isaac,"EntityPlayer","TryHoldEntity",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x1325),ApiDomain::Isaac,"EntityPlayer","TryHoldTrinket",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x1326),ApiDomain::Isaac,"EntityPlayer","UpdateCanShoot",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x1327),ApiDomain::Isaac,"EntityPlayer","UsePoopSpell",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x1328),ApiDomain::Isaac,"EntityTear","SetDeadEyeIntensity",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Game,1,0x1329),ApiDomain::Game,"Game","AddEncounteredBoss",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Game,1,0x132A),ApiDomain::Game,"Game","ButterBeanFart",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Game,1,0x132B),ApiDomain::Game,"Game","DonateAngel",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Game,1,0x132C),ApiDomain::Game,"Game","DonateGreed",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Game,1,0x132D),ApiDomain::Game,"Game","End",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Game,1,0x132E),ApiDomain::Game,"Game","Fadein",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Game,1,0x132F),ApiDomain::Game,"Game","Fadeout",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Game,1,0x1330),ApiDomain::Game,"Game","FinishChallenge",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Game,1,0x1331),ApiDomain::Game,"Game","GetGreedWavesNum",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Game,1,0x1332),ApiDomain::Game,"Game","GetNearestPlayer",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Game,1,0x1333),ApiDomain::Game,"Game","GetRandomPlayer",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Game,1,0x1334),ApiDomain::Game,"Game","HasEncounteredBoss",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Game,1,0x1335),ApiDomain::Game,"Game","MakeShockwave",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Game,1,0x1336),ApiDomain::Game,"Game","NextVictoryLap",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Game,1,0x1337),ApiDomain::Game,"Game","RerollEnemy",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Game,1,0x1338),ApiDomain::Game,"Game","RerollLevelCollectibles",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Game,1,0x1339),ApiDomain::Game,"Game","RerollLevelPickups",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Game,1,0x133A),ApiDomain::Game,"Game","StartStageTransition",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x133B),ApiDomain::Isaac,"GridEntityDoor","TryBlowOpen",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x133C),ApiDomain::Isaac,"GridEntityDoor","TryUnlock",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x133D),ApiDomain::Isaac,"GridEntityPit","MakeBridge",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x133E),ApiDomain::Isaac,"GridEntityPit","SetLadder",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x133F),ApiDomain::Isaac,"GridEntityPit","UpdateCollision",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x1340),ApiDomain::Isaac,"GridEntityPoop","RespawnRedPoop",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x1341),ApiDomain::Isaac,"GridEntityPressurePlate","Reward",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Hud,1,0x1342),ApiDomain::Hud,"HUD","AssignPlayerHUDs",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Hud,1,0x1343),ApiDomain::Hud,"HUD","FlashChargeBar",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Hud,1,0x1344),ApiDomain::Hud,"HUD","InvalidateActiveItem",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Hud,1,0x1345),ApiDomain::Hud,"HUD","InvalidateCraftingItem",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Hud,1,0x1346),ApiDomain::Hud,"HUD","PostUpdate",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Hud,1,0x1347),ApiDomain::Hud,"HUD","Update",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x1348),ApiDomain::Isaac,"ItemConfig","GetNullItem",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Level,1,0x1349),ApiDomain::Level,"Level","ForceHorsemanBoss",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Level,1,0x134A),ApiDomain::Level,"Level","GetEnterPosition",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Level,1,0x134B),ApiDomain::Level,"Level","GetNonCompleteRoomIndex",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x134C),ApiDomain::Isaac,"PathFinder","EvadeTarget",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x134D),ApiDomain::Isaac,"PathFinder","GetGridIndex",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x134E),ApiDomain::Isaac,"PathFinder","MoveRandomly",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x134F),ApiDomain::Isaac,"PathFinder","MoveRandomlyAxisAligned",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x1350),ApiDomain::Isaac,"PathFinder","MoveRandomlyBoss",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x1351),ApiDomain::Isaac,"PathFinder","Reset",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x1352),ApiDomain::Isaac,"PathFinder","ResetMovementTarget",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac,1,0x1353),ApiDomain::Isaac,"PathFinder","UpdateGridIndex",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Room,1,0x1354),ApiDomain::Room,"Room","CheckLine",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Room,1,0x1355),ApiDomain::Room,"Room","GetClampedGridIndex",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Room,1,0x1356),ApiDomain::Room,"Room","GetLaserTarget",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Room,1,0x1357),ApiDomain::Room,"Room","GetSeededCollectible",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Room,1,0x1358),ApiDomain::Room,"Room","MamaMegaExplosion",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Room,1,0x1359),ApiDomain::Room,"Room","TryMakeBridge",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Room,1,0x135A),ApiDomain::Room,"Room","TrySpawnDevilRoomDoor",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Room,1,0x135B),ApiDomain::Room,"Room","TrySpawnSecretShop",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Room,1,0x135C),ApiDomain::Room,"Room","TrySpawnSpecialQuestDoor",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Seed,1,0x135D),ApiDomain::Seed,"Seeds","CanAddSeedEffect",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Seed,1,0x135E),ApiDomain::Seed,"Seeds","CountUnlockedSeedEffects",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Seed,1,0x135F),ApiDomain::Seed,"Seeds","InitSeedInfo",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Seed,1,0x1360),ApiDomain::Seed,"Seeds","RemoveBlockingSeedEffects",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Seed,1,0x1361),ApiDomain::Seed,"Seeds","Reset",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Seed,1,0x1362),ApiDomain::Seed,"Seeds","Restart",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    {MakeId(ApiDomain::Sprite,1,0x1363),ApiDomain::Sprite,"Sprite","SetOverlayAnimation",kV1,0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},
    // Global surface.
    {MakeId(ApiDomain::Global, 1, 0x0001), ApiDomain::Global, "Global", "RegisterMod", kV1, 0,
     ThreadAffinity::MainUpdate, ApiMaturity::HardwareVerified},
    {MakeId(ApiDomain::Global, 1, 0x0002), ApiDomain::Global, "Global", "require", kV1, 0,
     ThreadAffinity::MainUpdate, ApiMaturity::HostVerified},
    // `load`/`loadstring`：**2026-09-18 批次 034 从 Disabled 改成真实现**（PC 是 LuaJIT 5.1，
    // 两个都有；我们以前把 `load` 置空，卡上的可调用性探针因此整批 skipped，见
    // `docs/问题与解决记录.md` 续五十九）。成熟度 `HostVerified`：宿主门禁
    // `test_lua_require_stage13` 的 `success` 场景**实测**了编译成功/失败形状、读取函数形式与
    // `env` 形式；真机侧由探针报告里的 `load=function loadstring=function` 作存在性证据。
    {MakeId(ApiDomain::Global, 1, 0x0003), ApiDomain::Global, "Global", "load", kV1, 0,
     ThreadAffinity::Any, ApiMaturity::HostVerified},
    // `loadstring` 是 Lua 5.1 的名字（PC 的 LuaJIT 就是 5.1）⇒ 模组里用到的是这一个。
    {MakeId(ApiDomain::Global, 1, 0x0006), ApiDomain::Global, "Global", "loadstring", kV1, 0,
     ThreadAffinity::Any, ApiMaturity::HostVerified},
    // `include(path)`（批次 042）：PC 提供给模组的全局（`analysis/isaacdocs-snapshot/docs/Globals.md:189`），
    // 语义 = **不缓存**（每次重新读盘执行）+ **只在当前模组目录里解析** + 返回 chunk 的返回值。
    // 真机证据待补（GoodTrip 装机后能加载即为存在性证据）；宿主上已由
    // `test_lua_require_stage13` 的 `success` 场景**实测**（含"不缓存"：读盘计数 3 次）。
    {MakeId(ApiDomain::Global, 1, 0x0007), ApiDomain::Global, "Global", "include", kV1, 0,
     ThreadAffinity::MainUpdate, ApiMaturity::HostVerified},
    // 批次 045：`CallbackPriority`（PC 枚举表；**值型条目** —— 没有 C 函数 ⇒ 不进绑定表，
    // 与 `Options` 的字段同例）。
    {MakeId(ApiDomain::Global, 1, 0x0008), ApiDomain::Global, "Global", "CallbackPriority", kV1, 0,
     ThreadAffinity::Any, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Global, 1, 0x0004), ApiDomain::Global, "Global", "loadfile", kV1, 0,
     ThreadAffinity::Any, ApiMaturity::Disabled},
    {MakeId(ApiDomain::Global, 1, 0x0005), ApiDomain::Global, "Global", "dofile", kV1, 0,
     ThreadAffinity::Any, ApiMaturity::Disabled},
    {MakeId(ApiDomain::Global, 1, 0x0010), ApiDomain::Global, "Global", "Game", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::HardwareVerified},
    {MakeId(ApiDomain::Global, 1, 0x0011), ApiDomain::Global, "Global", "MusicManager", kV1, 0,
     ThreadAffinity::MainRender, ApiMaturity::HardwareVerified},
    {MakeId(ApiDomain::Global, 1, 0x0012), ApiDomain::Global, "Global", "RNG", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::HostVerified},
    {MakeId(ApiDomain::Global, 1, 0x0013), ApiDomain::Global, "Global", "ModCallbacks", kV1, 0,
     ThreadAffinity::Any, ApiMaturity::HardwareVerified},
    // 版本判定全局：PC 引擎在忏悔版里定义 `REPENTANCE`，Mod 用它选代码分支（EID 就是靠它
    // 决定走 Repentance 还是 AB+）。Switch 版 1.7.9b 就是忏悔版，所以恒为 `true` 的布尔值，
    // 没有 `lua_CFunction`；`REPENTANCE_PLUS` 刻意不提供（PC 专属更新，Mod 会按非 Plus 处理）。
    {MakeId(ApiDomain::Global, 1, 0x001D), ApiDomain::Global, "Global", "REPENTANCE", kV1, 0,
     ThreadAffinity::Any, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Global, 1, 0x001A), ApiDomain::Global, "Global", "KColor", kV1, 0,
     ThreadAffinity::MainRender, ApiMaturity::HardwareVerified},
    // 批次 065：全局 `EntityRef(entity)` —— PC 的实体引用值类型。GoodTrip 的诅咒房过路费
    // （`scripts/trip.lua:70`）直接 `EntityRef(player)`；缺它时那句报
    // "attempt to call a nil value (global 'EntityRef')"。实现是"替 Lua 持有引擎那块缓冲区"，
    // 布局证据见 `interfaces/lua/entity_ref_api.hpp`。
    {MakeId(ApiDomain::Global, 1, 0x0009), ApiDomain::Global, "Global", "EntityRef", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Global, 1, 0x001B), ApiDomain::Global, "Global", "Vector", kV1, 0,
     ThreadAffinity::MainRender, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Global, 1, 0x001C), ApiDomain::Global, "Global", "Sprite", kV1, 0,
     ThreadAffinity::MainRender, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Global, 1, 0x0014), ApiDomain::Global, "Global", "Music", kV1, 0,
     ThreadAffinity::Any, ApiMaturity::HostVerified},
    {MakeId(ApiDomain::Global, 1, 0x0015), ApiDomain::Global, "Global", "Input", kV1, 0,
     ThreadAffinity::Any, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Global, 1, 0x0016), ApiDomain::Global, "Global", "Keyboard", kV1, 0,
     ThreadAffinity::Any, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Global, 1, 0x0017), ApiDomain::Global, "Global", "ButtonAction", kV1, 0,
     ThreadAffinity::Any, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Global, 1, 0x0018), ApiDomain::Global, "Global", "InputHook", kV1, 0,
     ThreadAffinity::Any, ApiMaturity::Experimental},
    // The `Font` constructor builds an object this Runtime owns (see
    // `interfaces/lua/font_api.cpp`); it runs wherever a Mod callback runs.
    {MakeId(ApiDomain::Global, 1, 0x0019), ApiDomain::Global, "Global", "Font", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    // 全局 `Color(...)`：PC 的 `Color` 与 `KColor` 是同一个类（`KColor` 是别名之一），
    // 所以这里把**同一个类表**再挂一个全局名（`lua_runtime.cpp` 的 `RegisterColorApi`），
    // 七个参数的重载 `Color(R,G,B[,A[,RO,GO,BO]])` 由 `color_api.cpp` 的
    // `CreateColorHandle` 实现（EID 的 `renderIcon` 用的就是七参形式）。
    {MakeId(ApiDomain::Global, 1, 0x001E), ApiDomain::Global, "Global", "Color", kV1, 0,
     ThreadAffinity::MainRender, ApiMaturity::Experimental},
    // 全局 `GetPtrHash(object)`：PC 的"把对象指针变成稳定整数"（`GlobalFunctions.md:143`），
    // EID 用它做实体身份比较（`main.lua:492`/`527`/`1473`，`features/eid_api.lua:2387`）。
    // 我们只持有 `Entity`/`EntityPlayer`/`EntityPickup` 三种**原生指针**句柄
    // （`Game`/`Level`/`Room` 的句柄是占位符，见 `lua_object_handles.hpp`），所以只对它们返回
    // 真实指针整数，其余返回 0（见 `isaac_api.cpp` 的 `GlobalGetPtrHash`）。
    {MakeId(ApiDomain::Global, 1, 0x001F), ApiDomain::Global, "Global", "GetPtrHash", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},

    {MakeId(ApiDomain::Global, 1, 0x0020), ApiDomain::Global, "Global", "BitSet128", kV1, 0,
     ThreadAffinity::Any, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Global, 1, 0x0021), ApiDomain::Global, "Global", "Random", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Global, 2, 0x000A), ApiDomain::Global, "Global", "TearFlags", kV1, 0,
     ThreadAffinity::Any, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x010C), ApiDomain::Isaac, "BitSet128", "Get", kV1, 0,
     ThreadAffinity::Any, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x010D), ApiDomain::Isaac, "BitSet128", "Set", kV1, 0,
     ThreadAffinity::Any, ApiMaturity::Experimental},

    // Mod surface.
    {MakeId(ApiDomain::Mod, 1, 0x0001), ApiDomain::Mod, "Mod", "AddCallback", kV1, 0,
     ThreadAffinity::MainUpdate, ApiMaturity::HardwareVerified},
    // 0x0002 `Mod.RemoveCallback` —— **真实现**（2026-09-18）：回调表由**我们自己**维护
    // （`CallbackRegistry`），所以这条完全是运行时侧的事，没有引擎底座可接。
    // 语义要点：按**函数身份**摘掉该 (id, owner) 上的这一条（同 id 其余登记必须留下），
    // 详见 `mod_api.cpp` 的 `ModRemoveCallback`。EID 在真机上真的会调它
    // （`features/eid_repentogon.lua:53/126/168`、`features/eid_bagofcrafting_search.lua:96`），
    // 缺它时那几处报 "attempt to call a nil value (method 'RemoveCallback')"。
    // id 取法：**先扫遍整个 Mod 域**再定（该域此前只有 0x0001 一条 ⇒ 0x0002 空着）。
    {MakeId(ApiDomain::Mod, 1, 0x0002), ApiDomain::Mod, "Mod", "RemoveCallback", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    // 批次 045（GoodTrip）：`Mod:AddPriorityCallback`。**优先级排序暂未实现**（只校验、登记行为同
    // `AddCallback`）—— 真排序要在 `CallbackRegistry` 加并行优先级数组；偏差写在实现处注释里。
    {MakeId(ApiDomain::Mod, 1, 0x0003), ApiDomain::Mod, "Mod", "AddPriorityCallback", kV1, 0,
     ThreadAffinity::MainUpdate, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Persistence, 1, 0x0001), ApiDomain::Persistence, "Mod", "SaveData", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Persistence, 1, 0x0002), ApiDomain::Persistence, "Mod", "LoadData", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Persistence, 1, 0x0003), ApiDomain::Persistence, "Mod", "HasData", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Persistence, 1, 0x0004), ApiDomain::Persistence, "Mod", "RemoveData", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},

    // Game surface.
    {MakeId(ApiDomain::Game, 1, 0x0001), ApiDomain::Game, "Game", "IsPaused", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::HardwareVerified},
    {MakeId(ApiDomain::Game, 1, 0x0002), ApiDomain::Game, "Game", "IsGreedMode", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::HostVerified},
    {MakeId(ApiDomain::Game, 1, 0x0003), ApiDomain::Game, "Game", "GetLevel", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::HostVerified},
    {MakeId(ApiDomain::Game, 1, 0x0004), ApiDomain::Game, "Game", "GetItemPool", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::HostVerified},
    {MakeId(ApiDomain::Game, 1, 0x0005), ApiDomain::Game, "Game", "GetRoom", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::HostVerified},
    // 批次 3：EID 的 `OnRender` 早期就要用到的两个 Game 方法。
    // `GetNumPlayers` 读 `players` 向量（与 `Isaac.GetPlayer` 同一条指针链）：
    // `EID:setPlayer()`（`main.lua:1062`）用它决定单人快速路径还是多人分支。
    // `GetFrameCount` 读引擎自己的帧计数 `Game + 0x24F99C`（`Game::Update` 每帧 +1，
    // 见 `runtime_constants.hpp`），`main.lua:1210`/`1044`/`955` 都在用；拿不到时退化为
    // 本 Runtime 的 `ManagedFrameClock`（近似值，注释里写明）。
    {MakeId(ApiDomain::Game, 1, 0x0006), ApiDomain::Game, "Game", "GetNumPlayers", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::HostVerified},
    {MakeId(ApiDomain::Game, 1, 0x0007), ApiDomain::Game, "Game", "GetFrameCount", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::HostVerified},
    // `Game:GetSeeds()` / `Game:GetVictoryLap()`（2026-09-12 第五轮，真机报告 `01789210180`）。
    //
    // EID 的 `features/eid_api.lua:2046` 写的是
    //   `if not game:GetSeeds():IsCustomRun() and not EID:PlayersHaveCollectible(...) then`
    // —— `GetSeeds()` 返回 nil 就整条 update 回调报错、被派发器静默摘除（屏幕全空）。
    // 这两个访问器在 Switch 符号表里没有对应方法（`IsaacRepentance::Game` 类没有
    // `GetSeeds`/`GetVictoryLap`），说明 PC 那条 Lua 访问器是**字段直读**，而字段偏移尚未定位；
    // 因此先给"有对象、有方法、值自洽"的最小实现，成熟度 `Experimental`。
    {MakeId(ApiDomain::Game, 1, 0x0008), ApiDomain::Game, "Game", "GetSeeds", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Game, 1, 0x0009), ApiDomain::Game, "Game", "GetVictoryLap", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    // 批次 140（2026-09-26）：`Game:GetPlayer(int Index)` —— PC 契约 `tools/pc_contract_docs/Game.md:337`
    // （`.alldlc`，正文见 `game_api.cpp` 的实现处注释）。真机证据：The Specialist for Good Items 的
    // `main.lua:447` 在 `MC_POST_NEW_ROOM` 里调它，报 `attempt to call a nil value (method 'GetPlayer')`
    // ⇒ 整条回调被摘 ⇒ 用户看到"没音乐也不跳舞"。id 取域内下一个空号（Game 域此前用到 0x000B）。
    {MakeId(ApiDomain::Game, 1, 0x000C), ApiDomain::Game, "Game", "GetPlayer", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    // 批次 207（2026-09-29）：`Game:GetHUD()` —— MCM 每次**开/关菜单**都要用它拿 HUD 再
    // `hud:SetVisible(false/true)` 把血条藏起来（`scripts/modconfig.lua:2939/2961` 是
    // `OpenConfigMenu`/`CloseConfigMenu` 的必经之路，`1199` 还读 `hud:IsVisible()`）。
    // 缺它就是 "attempt to call a nil value (method 'GetHUD')" ⇒ 整条关菜单回调被摘。
    // PC 契约 `tools/pc_contract_docs/Game.md`（`HUD GetHUD ( )`）。
    // 底座：`HUD` 是 `Game` 里**内嵌**的子对象 —— `Game* + 0xE8468`
    // （`Game::Game() @ 0x34B3F8` 逐个构造，取证见 `runtime_constants.hpp` 的 `kGameHudObjectOffset`）。
    // id 取域内下一个空号 0x000D。
    {MakeId(ApiDomain::Game, 1, 0x000D), ApiDomain::Game, "Game", "GetHUD", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    // 0x000A `Game:ChangeRoom(int, int)` —— **直接调引擎方法**（批次 050，2026-09-19）。
    // 底座 `Game::ChangeRoom(int,int)` @ `0x353FE0`（模块基址 + 偏移 + 入口指纹，见
    // `runtime_constants.hpp` 的批次 050 段）。GoodTrip 的传送主路径就是它
    // （`scripts/trip.lua` 6 处 `Game():ChangeRoom(目标格, -1)`），也是"能选房并传送"这条
    // 验收标准的必经之路。id 取域内下一个空号（Game 域此前用到 0x0009）。
    {MakeId(ApiDomain::Game, 1, 0x000A), ApiDomain::Game, "Game", "ChangeRoom", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    // 0x000B `Game:StartRoomTransition(int, Direction, RoomTransitionAnim, EntityPlayer, int)`
    // —— 批次 055，2026-09-19。GoodTrip 的传送**默认路径**（`scripts/trip.lua:207`；
    // `cfg.FastTransition` 默认 false ⇒ 走的就是这一条，缺它时模组报
    // "attempt to call a nil value (method 'StartRoomTransition')"）。
    // 底座 `Game::StartRoomTransition` @ `0x353CBC`（模块基址 + 偏移 + 入口指纹，见
    // `runtime_constants.hpp` 的批次 055 段）；5 个参数里第 4 个是玩家实体指针，
    // 由 `EngineCallShape::VoidIntIntIntHandleInt` 描述符接手。
    {MakeId(ApiDomain::Game, 1, 0x000B), ApiDomain::Game, "Game", "StartRoomTransition", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    // `Seeds` 家族（`Game:GetSeeds()` 的返回值）。EID 只用到这两个：
    //   * `IsCustomRun()` —— PC 语义"挑战局或带种子的局"（IsaacDocs 原文）；
    //   * `GetStartSeed()` —— EID 拿它当缓存键（`eid_bagofcrafting.lua:822`、
    //     `eid_api.lua:2887`），值自洽即可，不参与任何显示内容。
    {MakeId(ApiDomain::Seed, 1, 0x0001), ApiDomain::Seed, "Seeds", "IsCustomRun", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    // 批次 214：MCM 的 `OpenConfigMenu()`/`CloseConfigMenu()` 用这三条（英文版与中文版都缺）——
    // `seeds:AddSeedEffect(SeedEffect.SEED_NO_HUD)` 就在**开菜单**那条路径上、**不在 `pcall` 里**。
    // ★ `HasSeedEffect` 走引擎那棵 `std::set<eSeedEffect>`（`Seeds+0x58+8` 是根，结点键在 `+0x1c`）
    //   —— 生效中的种子效果**不是位图**；
    // ★ `Add`/`Remove` 我们给的是"**不抛错的空实现**"（次数进探针）：引擎里唯一的增删入口吃的是
    //   **名字字符串**，而"枚举 → 名字"那条函数是非静态成员（要一个 `Menu_SpecialSeed` 实例），
    //   镜像里也搜不到那批名字串 ⇒ 没有可信实现路径。口径与证据写进 `api_deviation.cpp`。
    {MakeId(ApiDomain::Seed, 1, 0x0004), ApiDomain::Seed, "Seeds", "HasSeedEffect", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Seed, 1, 0x0005), ApiDomain::Seed, "Seeds", "AddSeedEffect", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Seed, 1, 0x0006), ApiDomain::Seed, "Seeds", "RemoveSeedEffect", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    // 批次 274（2026-10-02）：`Seeds:ForgetStageSeed(stage)`（取号 = 域内下一个空号 0x0007）。
    // 引擎入口 `Seeds::ForgetStageLevel(eLevelStage)` @ 0x4A1228；`this` 是 `Game + 0x25D40`
    // 现算（Seeds 内嵌在 Game 里，与 Seeds:GetStartSeed 同一条思路）。
    {MakeId(ApiDomain::Seed, 1, 0x0007), ApiDomain::Seed, "Seeds", "ForgetStageSeed", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Seed, 1, 0x0002), ApiDomain::Seed, "Seeds", "GetStartSeed", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    // 批次 306（2026-10-03）：`Seeds` 再加两条（取号 = 域内接着的两个空号 0x0008 / 0x0009）。
    //   * `GetStageSeed(LevelStage)` —— 契约 `Seeds.md:71/73`，读 `Seeds + 0x18 + 4*stage` 的 u32。
    //     语料：`BOIStageAPI15` 拿它当 `StageRNG:SetSeed(...)` 的参数（3 处）、`MusicModCallback` 挑曲目。
    //   * `GetNextSeed()` —— 契约 `Seeds.md:56/58`，**调引擎的 `RNG::Next()`**（`this` = `Seeds + 0x8`
    //     那个内嵌 RNG）、返回新种子；PC 是把这一步内联在绑定本体里的。
    //     语料：`TBOI_Better-Voiding` 当 `Game:Spawn` 的种子、`IsaacOnTwitchReloaded`
    //     当 `MakeChampion(seed)` 的参数（3 处）。★ 这条**会推进引擎的种子 RNG**（与 PC 一致）。
    // 两条的偏移/证据（Switch 构造函数 + `Seeds::ForgetStageLevel` + PC 对照）见
    // `runtime_constants.hpp` 的批次 306 段。
    {MakeId(ApiDomain::Seed, 1, 0x0008), ApiDomain::Seed, "Seeds", "GetStageSeed", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Seed, 1, 0x0009), ApiDomain::Seed, "Seeds", "GetNextSeed", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    // ---- 批次 335（2026-10-03）：`Seeds:SetStartSeed(int)`（取号 = 域内下一个空号 0x000A）----
    // PC 契约 `tools/pc_contract_docs/Seeds.md:170/172`：逐字 `#### void SetStartSeed ( string StartSeed )`
    // 加一句 "Empty string means we will pick a new random seed."。
    // ★ 契约写 `string`、语料给**数字**（`IsaacOnTwitchReloaded/scripts/events.lua:1433`/`:1465`
    //   传的是 `seeds:GetNextSeed()` 的返回值）⇒ 引擎里有**两个重载**，
    //   本行调的是数字版 `Seeds::SetStartSeed(unsigned int)` @ `0x4A1114`
    //   （字符串版 @ `0x4A10E8` 只是 `String2Seed()` 之后**尾调**它）。
    // ★ 形状复用现成的 `EngineCallShape::Void1`（`void(this, i32)`）—— **本批零新形状**；
    //   接收者是本批新开的 `FieldReceipt::Seeds`（= `Game + kGameSeedsObjectOffset`）。
    //   逐条证据（两个 mangled 名、尾调关系、数字版的分支）见 `runtime_constants.hpp` 批次 335 段。
    {MakeId(ApiDomain::Seed, 1, 0x000A), ApiDomain::Seed, "Seeds", "SetStartSeed", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    // `HUD` 家族（`Game:GetHUD()` 的返回值，2026-09-29 批次 207）。MCM 两个方向都用到：
    //   * `IsVisible()` —— `modconfig.lua:1202/1206` 判"要不要改"，PC 契约 `HUD.md:41/43`；
    //   * `SetVisible(bool Visible = false)` —— `modconfig.lua:1203/1207/2940/2962`，
    //     PC 契约 `HUD.md:54/56`（**注意 PC 的缺省值是 `false`**，所以省略参数时按 false 处理）。
    // 两者读/写的是同一个字节 `HUD + 0xC53FA`（`HUD::Render()` 开头 `ldrb` 后 `cbz` 跳过整段渲染，
    // 取证见 `runtime_constants.hpp` 的 `kHudVisibleFlagOffset`）。
    {MakeId(ApiDomain::Hud, 1, 0x0001), ApiDomain::Hud, "HUD", "IsVisible", kV1, 0,
     ThreadAffinity::MainRender, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Hud, 1, 0x0002), ApiDomain::Hud, "HUD", "SetVisible", kV1, 0,
     ThreadAffinity::MainRender, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Hud, 1, 0x0003), ApiDomain::Hud, "HUD", "Render", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Hud, 1, 0x0004), ApiDomain::Hud, "HUD", "ShowItemText", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Hud, 1, 0x0005), ApiDomain::Hud, "HUD", "ShowFortuneText", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Level, 1, 0x0001), ApiDomain::Level, "Level", "GetStage", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::HardwareVerified},
    {MakeId(ApiDomain::Level, 1, 0x0002), ApiDomain::Level, "Level", "IsAscent", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::HostVerified},
    // 批次 4：`Level:GetCurses()`。`Level` **内嵌在 `Game` 起始处**（同一地址），所以读的是
    // `Game + 0x0C`（u32 诅咒位掩码）。**语义偏差**见 `remaining_api.cpp` 的注释：PC 是
    // `curses | 永久诅咒 & ~禁用诅咒` 三步，那两次调用的函数地址本轮未定位，这里**只返回字段值**。
    {MakeId(ApiDomain::Level, 1, 0x0003), ApiDomain::Level, "Level", "GetCurses", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    // 批次 8（2026-09-15）：EID 在**描述构建**路径上无条件调用、此前整条缺失的四个 `Level` 成员。
    // 缺口来自 `tools/eid_api_gap_report.py` 的高置信表（`missing_in_runtime`）；底座依据见
    // `docs/PC-Lua-API-对照清单.md`（该表 §3.3 已证明 `file_offset` 等于运行时模块偏移）：
    //   * `GetAbsoluteStage()` —— Switch 有符号 `_ZNK15IsaacRepentance5Level16GetAbsoluteStageEv`
    //     @ `0x3E7F3C`，安装期按 16 字节守卫校验后直接调用；
    //   * `IsNextStageAvailable()` —— 符号 @ `0x3DBDBC`，同上；
    //   * `GetCurrentRoomIndex()` —— 字段读 `Level + 0x21558`，依据是固定 NRO 里
    //     `Level::GetCurrentRoomDesc` 的反汇编：它把这个字段当 `Level::GetRoomByIdx(int,int)`
    //     的第一个实参（`docs/PC-Mod-兼容矩阵.md` 的 Stage104 条目）；
    //   * `GetCurrentRoom()` —— PC 语义就是"当前 `Room`"，与 `Game:GetRoom()` 是同一个对象
    //     （都读 `Game + 0x21550`），所以直接复用那条**已上机验证**的读取链 ⇒ 成熟度与
    //     `Game:GetRoom` 同级记 `HostVerified`，其余三条记为待真机确认的 `Experimental`。
    {MakeId(ApiDomain::Level, 1, 0x0004), ApiDomain::Level, "Level", "GetCurrentRoomIndex", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Level, 1, 0x0005), ApiDomain::Level, "Level", "GetCurrentRoom", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::HostVerified},
    // 批次 106：`Level:GetStartingRoomIndex()`（EID 的 `eid_holdmapdesc.lua:35` 每帧都在等它）。
    // ★ 与上面几条不同：引擎里**没有**这个符号/字段（符号表、Ghidra 类型库、镜像字符串、
    // `RoomDescriptor` 的 24 个标志、`RoomConfig::Room` 的字段、`Level/Game` 的 0x215xx 全镜像扫描
    // —— 都查过了），所以取值是**派生**的（本层第一次被看到的房间索引）。
    // 成熟度记 `Experimental`：逻辑在宿主上全验过，但**真机语义**（尤其"运行时在层中途加载"那种
    // 情形）还没上机。偏离已登记 `api_deviation.cpp` 的 0x03010011。
    {MakeId(ApiDomain::Level, 1, 0x0011), ApiDomain::Level, "Level", "GetStartingRoomIndex", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Level, 1, 0x0006), ApiDomain::Level, "Level", "GetAbsoluteStage", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Level, 1, 0x0007), ApiDomain::Level, "Level", "IsNextStageAvailable", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    // 地基二期（2026-09-15）：EID 的物品预测与背包合成要用房间描述符。
    // 描述符字段偏移**不是从 PC 抄的**，而是"布局表 + 真机行为验证"（`tools/layout_tables/room_descriptor` 那张布局表里每条都带可复核证据）：数组内联在 `Level` 里（基址 +0x18、步长 0x100、
    // 个数在 +0x21510），字段 `+0x00` GridIndex、`+0x04` SafeGridIndex、`+0x08` ListIndex、
    // `+0x10` Data（`Data+0x8` = Type）、`+0x4c` VisitedCount、`+0x50` Clear（清房瞬间 0→1，真机实测）。
    // 成熟度按规矩记 `Experimental`：偏移已上机验证，但**这三条 API 的返回路径本身**还没上机。
    {MakeId(ApiDomain::Level, 1, 0x0008), ApiDomain::Level, "Level", "GetCurrentRoomDesc", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Level, 1, 0x0009), ApiDomain::Level, "Level", "GetRoomByIdx", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Level, 1, 0x000A), ApiDomain::Level, "Level", "GetRooms", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    // 批次 11（2026-09-16）：`Level` 的关卡类型三条。字段证据见 `runtime_constants.hpp` 的
    // `kLevelStageTypeOffset`（`Level::SetStage` 把两个参数连着写进 `+0x00`/`+0x04`）。
    {MakeId(ApiDomain::Level, 1, 0x000B), ApiDomain::Level, "Level", "GetStageType", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::HardwareVerified},
    {MakeId(ApiDomain::Level, 1, 0x000C), ApiDomain::Level, "Level", "IsAltStage", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::HardwareVerified},
    {MakeId(ApiDomain::Level, 1, 0x000D), ApiDomain::Level, "Level", "IsPreAscent", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::HardwareVerified},
    // 批次 028：`Level:GetLastRoomDesc()`（EID 链式缺口）。引擎那条函数本身就是
    // "取 `Level + 0x2155C`/`+0x21564`（上一个房间的索引/维度）→ 尾调用 `GetRoomByIdx`"，
    // 我们直接调引擎并把返回的 `RoomDescriptor*` 交给现成的 `PushRoomDescriptor`。
    {MakeId(ApiDomain::Level, 1, 0x000E), ApiDomain::Level, "Level", "GetLastRoomDesc", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    // 0x000F / 0x0010（批次 051）`Level:AddCurse(int,bool)` / `Level:RemoveCurses(int)` ——
    // 走**引擎方法数据行**（16 字节只读、0 字节代码）。底座 `Level::AddCurse(eLevelCurse,bool)`
    // @ `0x3E7E08`、`Level::RemoveCurses(unsigned)` @ `0x3D8EC4`；GoodTrip 用它们临时加/撤
    // "迷宫诅咒"（`scripts/trip.lua:26`/`126`）。
    {MakeId(ApiDomain::Level, 1, 0x000F), ApiDomain::Level, "Level", "AddCurse", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Level, 1, 0x0010), ApiDomain::Level, "Level", "RemoveCurses", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Room, 1, 0x0001), ApiDomain::Room, "Room", "GetType", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::HostVerified},
    // 批次 7（2026-09-12）：EID 在网格/寻路路径上无条件调用的一批 `Room` 成员
    // （`eid_api.lua:3351` 的 `EvaluateLocation`、`3371` 的 `HasPathToPosition`、`2593` 的
    // 网格实体查询）。缺任何一个都是"调 nil"、整条回调被摘除。
    //
    // ★ 批次 098（2026-09-20）：**从"保守占位"改成真实现** —— 起因是用户报"走到地上药丸/
    //   卡片旁边只显示一个问号"。旧口径 `GetGridPath` 恒返 1000（> EID 的 900 阈值）⇒
    //   地上每一颗药丸、每一张卡片都被判"够不到"、只画问号（当时只评估成"不画路径提示"，
    //   漏看了它在药丸/卡片上等于藏掉整条描述）。现在读真值：宽 `Room + 0x14`、
    //   高 `+0x18`、通行代价表 `+0xE98`（int32/格、下标 `W*y + x`）、格坐标按
    //   `Room::GetGridIndex(Vector2) @ 0x459e3c` 的算术；证据与宿主判据见
    //   `runtime_constants.hpp` 与 `runtime/tests/test_lua_room_grid.py`。
    //   成熟度给 `HostVerified`：宿主门禁（含 EID 自己的寻路器）通过，
    //   **真机读数确认后再升 `HardwareVerified`**。
    {MakeId(ApiDomain::Room, 1, 0x0002), ApiDomain::Room, "Room", "GetGridWidth", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::HostVerified},
    {MakeId(ApiDomain::Room, 1, 0x0003), ApiDomain::Room, "Room", "GetGridHeight", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::HostVerified},
    {MakeId(ApiDomain::Room, 1, 0x0004), ApiDomain::Room, "Room", "GetGridSize", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::HostVerified},
    {MakeId(ApiDomain::Room, 1, 0x0005), ApiDomain::Room, "Room", "GetGridIndex", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::HostVerified},
    {MakeId(ApiDomain::Room, 1, 0x0006), ApiDomain::Room, "Room", "GetGridPath", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::HostVerified},
    {MakeId(ApiDomain::Room, 1, 0x0007), ApiDomain::Room, "Room", "GetGridEntity", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    // ---- 批次 307（2026-10-03）：`Room:GetGridEntityFromPos(Vector)`（语料 4 处）----
    // PC 契约 `Room.md:352/354`（**同页带 `data-altreturn='nil'`** ⇒ 找不到就是 nil）。
    // ★ 它 = `Room:GetGridIndex(Vector)` 与 `Room:GetGridEntity(index)` **两步的合成**：
    //   PC 的绑定本体（`0x447F80`）把"世界坐标 → 格坐标"内联了（`(x−40)/40+0.5`、
    //   `(y−120)/40+0.5`、向零截断，再 `width*gy+gx`），然后读**同一张**网格实体表。
    //   ★★ 同一套算术在 Switch 侧有独立符号 `Room::GetGridIndex(Vector2) @ 0x459E3C`
    //   （常量 -40.0 / 40.0 / 0.5 / -120.0 与 `madd` 逐句对上）—— 而那段我们**早就**复刻进了
    //   `RoomGridCoordinateFromWorld` ⇒ **本条零新增引擎偏移**。
    {MakeId(ApiDomain::Room, 1, 0x0033), ApiDomain::Room, "Room", "GetGridEntityFromPos", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    // ---- 批次 310（2026-10-03，★ 批次 311 修正归属）：`Room:GetAliveBossesCount()`（语料 2 处）----
    // PC 契约 `Room.md:86/88`（`#### int GetAliveBossesCount ( )`）。
    // ★ 语料：`BOIStageAPI15` 判"这一波 Boss 打完没"（`GetAliveBossesCount() < 1 or Room:IsClear()`）、
    //   `BossRushWaveCounter` 数"这波还剩几个 Boss"。
    // ★★ 引擎侧 = `max(0, *(i32*)(Room + 0x1A60) + *(i32*)(Room + 0x1A64))`：
    //   PC 的绑定本体（`Room:GetAliveBossesCount @ 0x448020`）是 `mov edx,[ecx+0x12CC]`
    //   + `mov ecx,[ecx+0x12C8]` + `add` + `test` + **`cmovg`**（有符号求和、负数清 0）。
    //   Switch 侧同一段模板在 `0x1447C4` 处**与敌人那条并列出现**（各带同一个夹下限、随后相减）
    //   —— 逐条证据见 `runtime_constants.hpp` 的 `kRoomAliveBossesCountOffset` 段。
    // ★★★ **批次 310 原先把这两条搞反了**（把敌人对 `+0x1A58` 当成 Boss）⇒ 批次 311 已改指
    //   `+0x1A60`；前一对（`+0x1A58`）归下面 0x35 的 `Room:GetAliveEnemiesCount()`。
    // ★ 为什么手写：PC 是「有符号求和 + 负数清 0」而既有 `Sum2U32` 无符号、不夹下限
    //   （出负值时会给出巨大的无符号数）⇒ 不复用；为一个 API 新开 kind 比手写更贵（306/308 同一笔账）。
    {MakeId(ApiDomain::Room, 1, 0x0034), ApiDomain::Room, "Room", "GetAliveBossesCount", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    // ---- 批次 311（2026-10-03）：`Room:GetAliveEnemiesCount()`（语料 1 处，`BOIStageAPI15`）----
    // PC 契约 `Room.md:93`（`#### int GetAliveEnemiesCount ( )`）。
    // ★★ 与上一条是**孪生**：PC 上两条紧邻、**同一段模板**（`add` + `test` + `cmovg` + `ret`），
    //   只有偏移不同 —— 敌人 `0x12C0`/`0x12C4`（`@ 0x448000`）、Boss `0x12C8`/`0x12CC`（`@ 0x448020`）。
    // ★★ Switch 侧 `Room + 0x1A58`/`+0x1A5C` 这一对的归属由**具名函数**
    //   `Entity_NPC::get_alive_enemy_count() @ 0x122768` 钉死（函数名自己写着 enemy）。
    {MakeId(ApiDomain::Room, 1, 0x0035), ApiDomain::Room, "Room", "GetAliveEnemiesCount", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    // ---- 批次 327（2026-10-03）：`Room:IsDoorSlotAllowed(DoorSlot)`（语料 2 处，`IsaacOnTwitchReloaded`）----
    // PC 契约 `Room.md:655`（`#### boolean IsDoorSlotAllowed ( DoorSlot Slot )`）——
    // "Returns whether or not the supplied door slot is valid for the current room. This is
    //  contingent on the room definition in the STB/XML file ... The value returned by this
    //  method is **independent of whether or not a door currently exists** at the given slot."
    // ⇒ 语义 = **房间定义（XML）里这一个门位合不合法** ⇒ 读的是 `RoomConfig::Room.Doors`
    //   （PC 文档 `RoomConfig_Room.md:29` 逐字给出 `DoorSlotFlag` 的 `1 << DoorSlot.*`）。
    // ★ 引擎里**没有同名访问器**（Switch 侧连符号都没有）⇒ 走**字段读取型数据行**
    //   （`remaining_api.cpp` 的 `kRoomFieldApis`，`FieldKind::BoolBitArrayOfArg` + 既有的
    //   `FieldReceipt::RoomConfigData`；`Data+0x40` 按 64 位读 ⇒ 元素宽度 8）—— **0 字节代码**。
    //   偏移与四条独立证据（十余处门逻辑同形、`Level::precalc_allowed_doors` 逐位测、
    //   `Level::get_room_neighbor_pos` 函数名即语义、`Room::TrySpawnSecretExitEbb` 的先后关系）
    //   见 `runtime_constants.hpp` 的批次 327 段与布局表 `room_descriptor.json` 的 `Data.Doors` 行。
    {MakeId(ApiDomain::Room, 1, 0x0036), ApiDomain::Room, "Room", "IsDoorSlotAllowed", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    // ---- 批次 336（2026-10-03 深夜）：`Room:GetTintedRockIdx()`（1 处；取号 = 域内下一个空号 0x0037）----
    // PC 契约 `Room.md:559/561`：逐字 `#### int GetTintedRockIdx ( )`（只有签名、没有散文）。
    // PC 绑定本体 `0x427750` = `mov eax,[ecx+0x764]; ret`（**纯读一个 i32、没有守卫**）
    // ⇒ 只读字段、走 `field_row`（数据行在 `remaining_api.cpp` 的 `kRoomFieldApis`，
    //   偏移 `Room+0xE90`，**0 字节代码**；接收者是既有的 `FieldReceipt::Room`）。
    // ★ 定案的三条独立证据（写入点 / 具名消费者 / PC 侧同族顺序）见 `runtime_constants.hpp`
    //   的批次 336 段；布局表是 `room.json` 的 `TintedRockIdx` 行（`confirmed`）。
    {MakeId(ApiDomain::Room, 1, 0x0037), ApiDomain::Room, "Room", "GetTintedRockIdx", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    // ---- 批次 347（2026-10-04）：一条（Room 域取号 **0x0038**）----
    // `RoomConfigSpawn:PickEntry(float r)`（**2 处** / 2 个模组）：**手写处理器**。
    // PC 契约 `tools/pc_contract_docs/RoomConfig_Spawn.md:28`（逐字 `const RoomConfigEntry
    // PickEntry(float r)`）；真身 `_ZNK15IsaacRepentance10RoomConfig5Spawn9PickEntryEf @ 0x494910`
    // （入口字 `0xA9BE7BFD`）。连同本批新开的四件前置：`Data.Spawns` 换**真容器**、
    // `RoomConfigSpawn` / `RoomConfigEntry` 两个视图、以及那一条 `Partial/design` 偏离。
    // ★ 为什么手写而不是数据行：数据行要同时新开 `EngineReturnKind` + `EngineCallShape` +
    // `FieldReceipt` 三处枚举，而 `RoomConfigSpawn` **只有这一个方法**。
    {MakeId(ApiDomain::Room, 1, 0x0038), ApiDomain::Room, "RoomConfigSpawn", "PickEntry", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    // 2026-09-15：`Room:GetRenderScrollOffset()` —— EID 用到而运行时里没有的一条。
    // 偏移 `+0x1938` 的证据在布局表 `tools/layout_tables/room`（引擎自己的
    // `Room::WorldToScreenPosition` 就把这个字段的地址交给 `Vector2::operator+`，
    // `build_layout_table.py --verify` 会重新反汇编核对）。
    {MakeId(ApiDomain::Room, 1, 0x0008), ApiDomain::Room, "Room", "GetRenderScrollOffset", kV1,
     0, ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    // 批次 10（2026-09-15）：`Room:WorldToScreenPosition(Vector)`。换算方式来自引擎自己的
    // `Room::WorldToScreenPosition @ 0x489354`：`GetRenderPosition(世界坐标, true)`
    // 加上房间滚动偏移、再加上 Game 的调整量（三个常量的证据见 `runtime_constants.hpp`）。
    {MakeId(ApiDomain::Room, 1, 0x0009), ApiDomain::Room, "Room", "WorldToScreenPosition", kV1,
     0, ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    // 批次 14（2026-09-16）：`Room:GetFrameCount()` —— "这个房间已经活动了多少帧"。
    // EID 的背包合成渲染路径无条件调它（`features/eid_bagofcrafting.lua:967` 的 `< 2`），
    // 之前完全没有 ⇒ 拿着背包合成时每帧抛错、描述渲染整段被打断（真机 `g_LastLuaErrorText` 坐实）。
    // 实现是调引擎自己的 `Room::GetFrameCount()`（`0x470B0C`，安装期 16 字节守卫），
    // 所以成熟度先记 `HostVerified`（宿主夹具覆盖"调到/绑定不可用"两条路），真机验收后再上 `HardwareVerified`。
    {MakeId(ApiDomain::Room, 1, 0x000A), ApiDomain::Room, "Room", "GetFrameCount", kV1,
     0, ThreadAffinity::ManagedCallback, ApiMaturity::HardwareVerified},
    // 0x000B `Room.IsMirrorWorld` —— **真实现**（2026-09-18）：判据是"当前房间的维度 == 1"，
    // 读 `Level + 0x21560`（引擎判"当前房间属于哪个维度"的那个字，我们为判换房早已在读它）。
    // 维度枚举的含义出自 PC 文档快照 `RoomDescriptor.md`（1 = 次级维度 = Downpour/Dross 的镜子维度）。
    // EID 在 `main.lua:839` 无条件调它（`level:GetCurrentRoom():IsMirrorWorld()`），
    // 缺它时那一行报 "attempt to call a nil value"。
    // ⚠️ 已知过宽：矿坑逃脱序列也用维度 1 ⇒ 那一幕也会答 true（见实现处注释）。
    // id 取法：**先扫遍整个 Room 域**再定（该域此前用到 0x000A ⇒ 0x000B 空着）。
    {MakeId(ApiDomain::Room, 1, 0x000B), ApiDomain::Room, "Room", "IsMirrorWorld", kV1,
     0, ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    // 批次 046（GoodTrip 运行期）：`Room:GetDoor(slot)` —— **方法存在、恒返回 nil**（如实降级）。
    // 缺它时 `floor.lua:223` 报 "attempt to call a nil value (method 'GetDoor')"，模组的运行期
    // 回调每帧抛错、整块功能被摘掉；PC 上这条**本来就可以返回 nil**（没有门的槽位）⇒ 先对齐形状。
    // 取证后再换真实现（**不编造门对象**：假门会让模组画出错误连通图，比"暂时没有门"更糟）。
    {MakeId(ApiDomain::Room, 1, 0x000C), ApiDomain::Room, "Room", "GetDoor", kV1,
     0, ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    // 0x000D（批次 051）`Room:PlayMusic()` —— 走**引擎方法数据行**（16 字节只读、0 字节代码）。
    // 底座 `Room::PlayMusic()` @ `0x451834`；GoodTrip 传送到没有音乐的房间后补一次
    // （`scripts/trip.lua:202`）。⚠️ 它的 `this` 是**当前房间**，所以数据行的 `receipt` 用 `Room`。
    {MakeId(ApiDomain::Room, 1, 0x000D), ApiDomain::Room, "Room", "PlayMusic", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    // 批次 207（2026-09-29）：`Room:IsClear()` —— MCM 判"这个房间能不能开菜单/传送"
    // （`scripts/modconfig.lua:231`：`if room:IsClear() and not roomHasDanger then return true end`）。
    // PC 契约 `tools/pc_contract_docs/Room.md:642/644`：`#### boolean IsClear ( )`。
    // 判据 = `[Room + 0x8] + 0x50` 的 **bit0**（`Room::TriggerClear(bool)` @ `0x470B58` 前五条指令
    // 就是 `orr …, #0x1` 写这一位，取证见 `runtime_constants.hpp` 的 `kRoomClearFlagBit`）。
    // id 取域内下一个空号 0x000E（0x000D 已被 `PlayMusic` 占）。
    {MakeId(ApiDomain::Room, 1, 0x000E), ApiDomain::Room, "Room", "IsClear", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::ItemPool, 1, 0x0001), ApiDomain::ItemPool, "ItemPool", "GetCollectible", kV1,
     0, ThreadAffinity::ManagedCallback, ApiMaturity::HostVerified},
    {MakeId(ApiDomain::ItemPool, 1, 0x0002), ApiDomain::ItemPool, "ItemPool", "GetLastPool", kV1,
     0, ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    // 批次 13（2026-09-16）：`ItemPool:IsPillIdentified(PillColor)` —— EID 用它决定"没识别过的
    // 药丸要不要泄底"（`main.lua:1649`、`eid_itemprediction.lua:339`、`eid_holdmapdesc.lua:575`）。
    // 底座是 `ItemPool + 0xa68 + color` 的每色一字节"已识别"表（15 项，紧跟在 `+0xa2c` 的药丸
    // 效果表之后）；证据见 `runtime_constants.hpp` 的 `kItemPoolPillIdentifiedOffset`。
    {MakeId(ApiDomain::ItemPool, 1, 0x0003), ApiDomain::ItemPool, "ItemPool", "IsPillIdentified",
     kV1, 0, ThreadAffinity::ManagedCallback, ApiMaturity::HardwareVerified},
    // 批次 028（2026-09-18 夜）：两条 EID 真的在调、而我们缺的 ItemPool 成员。
    // `GetPillEffect` 最急：EID 在 `features/eid_api.lua:881` 调它，真机报
    // `attempt to call a nil value (method 'GetPillEffect')` ⇒ 那颗药的描述整条消失。
    // 成熟度按项目口径先记 `Experimental`（有宿主测试与真机报错做判据，但还没在真机上
    // 逐值核对返回的 PillEffect 编号）。
    {MakeId(ApiDomain::ItemPool, 1, 0x0004), ApiDomain::ItemPool, "ItemPool", "GetPillEffect", kV1,
     0, ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::ItemPool, 1, 0x0005), ApiDomain::ItemPool, "ItemPool", "GetPoolForRoom", kV1,
     0, ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    // ---- 批次 254（2026-10-01）：`ItemPool:RemoveCollectible`（走数据行；域内序号取 0x0006）。
    // ★ 本批**先补了 PC 契约页** `tools/pc_contract_docs/ItemPool.md`（G2 闸门：写不出
    //   `页:行号` 就不许写代码）—— 该页第 96 行是 `boolean RemoveCollectible ( CollectibleType
    //   Collectible )`。★ 引擎符号是 3 格（`…eCollectibleTypeEbb`）⇒ 按**符号**取形状
    //   （G3 口径），省略的两个 `bool` 保持 0 恰好就是 PC 正文描述的行为。
    // ★ 接收者是本批新增的 `FieldReceipt::ItemPool`（**不从 Lua 栈上取**，按
    //   `ReadCurrentGameItemPool` 现查 —— 与手写 `ItemPoolGetCollectible` 同一条链）。
    {MakeId(ApiDomain::ItemPool, 1, 0x0006), ApiDomain::ItemPool, "ItemPool", "RemoveCollectible",
     kV1, 0, ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},

    // Music surface.
    {MakeId(ApiDomain::Music, 1, 0x0001), ApiDomain::Music, "MusicManager", "GetCurrentMusicID",
     kV1, 0, ThreadAffinity::MainRender, ApiMaturity::HardwareVerified},
    {MakeId(ApiDomain::Music, 1, 0x0002), ApiDomain::Music, "MusicManager", "Pause", kV1, 0,
     ThreadAffinity::MainRender, ApiMaturity::HardwareVerified},
    {MakeId(ApiDomain::Music, 1, 0x0003), ApiDomain::Music, "MusicManager", "Resume", kV1, 0,
     ThreadAffinity::MainRender, ApiMaturity::HardwareVerified},
    // 批次 137（2026-09-26）：`MusicManager:UpdateVolume()` —— The Specialist for Good Items
    // 的"捡到四级物品跳 Specialist 舞 + 放歌"要用它（放歌之后把音量同步到选项菜单的设置）。
    // 底座 `Music::UpdateVolume()` @ `0x427908`（符号 + 16 字节入口守卫见 `runtime_constants.hpp`），
    // 走与 `Pause`/`Resume` 同一条"回调 Manager 派生的 Music 对象 + 守卫"链（**手写**，不是数据行：
    // 接收者不是从栈上那个占位句柄来的，`FieldReceipt` 那套解不出 Music 对象）。
    {MakeId(ApiDomain::Music, 1, 0x0006), ApiDomain::Music, "MusicManager", "UpdateVolume", kV1, 0,
     ThreadAffinity::MainRender, ApiMaturity::Experimental},
    // 批次 138（2026-09-26）：`MusicManager:Play(ID, Volume = 1)` —— The Specialist for Good Items
    // "放歌"的**主路径**（`main.lua:483/489/494`）。底座 `Music::Play(eMusic, float)` @ `0x427238`
    // （与 `kStage48MusicPlayOffset` 同址；PC 契约 `MusicManager.md:102` 的
    // `void Play ( Music ID, float Volume = 1 )`）。与 `Pause`/`Resume`/`UpdateVolume` 同一条
    // "回调 Manager 派生的 Music 对象 + 16 字节守卫"链（**手写**，不是数据行）。
    {MakeId(ApiDomain::Music, 1, 0x0007), ApiDomain::Music, "MusicManager", "Play", kV1, 0,
     ThreadAffinity::MainRender, ApiMaturity::Experimental},
    // ---- 批次 239（2026-09-30）：`MusicManager` 的 7 条**引擎方法数据行**。
    // ★ 与上面 `Pause`/`Resume`/`Play`/`UpdateVolume` 的区别：那 4 条写在数据行机制（批次 051）
    //   之前、各带一份手写核对；这 7 条走 `kMusicEngineRows`（`music_api.cpp`），
    //   接收者 = `FieldReceipt::Music`（从 `Manager + kManagerMusicOffset` 解析，不读 Lua 栈上
    //   那个占位句柄）⇒ 每条只花 16 字节只读数据、0 字节代码。
    // 域内序号取 0x0008 起（该域下一个空号），逐条证据见 `runtime_constants.hpp` 批次 239 段。
    {MakeId(ApiDomain::Music, 1, 0x0008), ApiDomain::Music, "MusicManager", "DisableLayer", kV1, 0,
     ThreadAffinity::MainRender, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Music, 1, 0x0009), ApiDomain::Music, "MusicManager", "IsLayerEnabled", kV1, 0,
     ThreadAffinity::MainRender, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Music, 1, 0x000A), ApiDomain::Music, "MusicManager", "EnableLayer", kV1, 0,
     ThreadAffinity::MainRender, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Music, 1, 0x000B), ApiDomain::Music, "MusicManager", "VolumeSlide", kV1, 0,
     ThreadAffinity::MainRender, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Music, 1, 0x000C), ApiDomain::Music, "MusicManager", "GetQueuedMusicID", kV1, 0,
     ThreadAffinity::MainRender, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Music, 1, 0x000D), ApiDomain::Music, "MusicManager", "PitchSlide", kV1, 0,
     ThreadAffinity::MainRender, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Music, 1, 0x000E), ApiDomain::Music, "MusicManager", "ResetPitch", kV1, 0,
     ThreadAffinity::MainRender, ApiMaturity::Experimental},
    // ---- 批次 252（2026-10-01）：`MusicManager` 再加 2 条（走 `kMusicEngineRows` 数据行）。
    // 逐条的偏移/入口指纹/契约/语料实参见 `runtime_constants.hpp` 的批次 252 段。
    {MakeId(ApiDomain::Music, 1, 0x000F), ApiDomain::Music, "MusicManager", "Queue", kV1, 0,
     ThreadAffinity::MainRender, ApiMaturity::Experimental},
    // ---- 批次 305（2026-10-03）：`MusicManager` 的"启用"三兄弟（各 1 处 = 3 处）----
    // PC 侧三条绑定紧挨着、各只一条指令，都在 `Music + 0x328` 的**一个字节**上：
    // `Disable` = 写 0（`0x7FAC30`）、`Enable` = 写 1（`0x7FAC20`）、`IsEnabled` = 读它（`0x7FAC40`）。
    // ★ Switch 侧那一格是 `Music + 0x3F0`（构造函数写 1 = 默认启用；`Music::Update` 读它当闸）
    //   —— 数值不许平移（布局差异），取证见 `runtime_constants.hpp` 的批次 305 段。
    // ★ 前两条走**新种类 `FieldKind::BoolWriteConst`**（写常量、**不收实参**、返回 0 个值）、
    //   第三条走既有的 `FieldKind::Bool`；三条都是**字段数据行**（0 字节代码），
    //   接收者复用 `FieldReceipt::Music`。
    // 契约：`tools/pc_contract_docs/MusicManager.md` 的 40/42（`Disable`）、50/52（`Enable`）、
    //       80/82（`IsEnabled`）—— 三条都在同一页里。
    // ★ 线程亲和写 `ManagedCallback`（与同族 `MainRender` **不同**，这是刻意的）：
    //   同族那几条是"调引擎函数"（必须在渲染阶段那一档里发出去），而这三条**不碰引擎函数** ——
    //   只是读/写 `Music` 上的一个字节，且接收者由全局 `Manager` 槽算出（不依赖当前回调）。
    //   `ManagedCallback` = "托管回调里都能用、不隐含帧阶段"（`Font` 一族同一口径），
    //   比 `MainRender` 更宽 ⇒ 模组在 `MC_POST_UPDATE` 里调也说得过去。
    {MakeId(ApiDomain::Music, 1, 0x0011), ApiDomain::Music, "MusicManager", "Disable", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Music, 1, 0x0012), ApiDomain::Music, "MusicManager", "Enable", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Music, 1, 0x0013), ApiDomain::Music, "MusicManager", "IsEnabled", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Music, 1, 0x0010), ApiDomain::Music, "MusicManager", "Crossfade", kV1, 0,
     ThreadAffinity::MainRender, ApiMaturity::Experimental},
    // 批次 045（GoodTrip）：`SFXManager()` 返回对象的两个方法 —— **`Play` 是明确的空实现**
    // （引擎音效单例与 `Play` 地址未取证）、`IsPlaying` 恒 false。形状与 PC 一致是硬要求：
    // 缺它时模组整个加载失败（真机实测 `goodtripfixed/scripts/trip.lua:8`）。
    {MakeId(ApiDomain::Music, 1, 0x0004), ApiDomain::Music, "SFXManager", "Play", kV1, 0,
     ThreadAffinity::MainUpdate, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Music, 1, 0x0005), ApiDomain::Music, "SFXManager", "IsPlaying", kV1, 0,
     ThreadAffinity::MainUpdate, ApiMaturity::Experimental},

    {MakeId(ApiDomain::Music, 1, 0x0020), ApiDomain::Music, "SFXManager", "AdjustPitch", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Music, 1, 0x0021), ApiDomain::Music, "SFXManager", "AdjustVolume", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Music, 1, 0x0022), ApiDomain::Music, "SFXManager", "GetAmbientSoundVolume", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Music, 1, 0x0023), ApiDomain::Music, "SFXManager", "Preload", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Music, 1, 0x0024), ApiDomain::Music, "SFXManager", "SetAmbientSound", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Music, 1, 0x0025), ApiDomain::Music, "SFXManager", "Stop", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Music, 1, 0x0026), ApiDomain::Music, "SFXManager", "StopLoopingSounds", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},

    // RNG surface.
    {MakeId(ApiDomain::Rng, 1, 0x0001), ApiDomain::Rng, "RNG", "SetSeed", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::HardwareVerified},
    {MakeId(ApiDomain::Rng, 1, 0x0002), ApiDomain::Rng, "RNG", "Next", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::HostVerified},
    // 批次 13（2026-09-16）：`RNG:GetSeed()` —— EID 的 `spikes:GetRNG():GetSeed()` 链上少不了
    // 这一环（缺它就是 "attempt to call a nil value"）。种子就是 RNG 对象头 4 字节
    // （`RNG::SetSeed @ 0x44E3C0` 的第一条存值 `str w1, [x0]`），所以这是纯读、不走引擎调用。
    {MakeId(ApiDomain::Rng, 1, 0x0003), ApiDomain::Rng, "RNG", "GetSeed", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::HardwareVerified},
    // 批次 195（2026-09-29）：`RNG:RandomInt(int Max)` / `RNG:RandomFloat()` ——
    // **本批的四条 `Get*RNG` 落地之后，链上最后一环**。语料里的 Trinity 写的是
    // `GetCollectibleRNG(CollectibleType.BIRTHRIGHT):RandomFloat()`（`analysis/mod-corpus/Trinity/main.lua:173`），
    // 缺这两条就是 `attempt to call a nil value`（回调被派发器整条摘掉）；PC 契约
    // `analysis/isaacdocs-snapshot/docs/RNG.md:101-104`（RandomFloat）与 `:124-127`（RandomInt）
    // 都明写它们**会推进** RNG 对象。引擎底座 `RNG::Random(uint)` @ `0x44E3E8` /
    // `RNG::Random()` @ `0x44E4C0`（16 字节入口指纹见 `runtime_constants.hpp`）。
    // 成熟度 `Experimental`：宿主上是注入的宿主实现（`SetRngRandomBindings`），**还没上真机**。
    {MakeId(ApiDomain::Rng, 1, 0x0004), ApiDomain::Rng, "RNG", "RandomInt", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Rng, 1, 0x0005), ApiDomain::Rng, "RNG", "RandomFloat", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},

    // Input surface: reachability was probed, the edge timing is still unproven.
    {MakeId(ApiDomain::Input, 1, 0x0001), ApiDomain::Input, "Input", "IsButtonTriggered", kV1, 0,
     ThreadAffinity::MainUpdate, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Input, 1, 0x0002), ApiDomain::Input, "Input", "IsButtonPressed", kV1, 0,
     ThreadAffinity::MainUpdate, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Input, 1, 0x0003), ApiDomain::Input, "Input", "GetButtonValue", kV1, 0,
     ThreadAffinity::MainUpdate, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Input, 1, 0x0004), ApiDomain::Input, "Input", "IsActionTriggered", kV1, 0,
     ThreadAffinity::MainUpdate, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Input, 1, 0x0005), ApiDomain::Input, "Input", "IsActionPressed", kV1, 0,
     ThreadAffinity::MainUpdate, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Input, 1, 0x0006), ApiDomain::Input, "Input", "GetActionValue", kV1, 0,
     ThreadAffinity::MainUpdate, ApiMaturity::Experimental},
    // 批次 041（GoodTrip）：鼠标两条。**Switch 上没有鼠标** ⇒ 处理器是"明确降级"
    // （`Input.GetMousePosition` 恒返回 (0,0)、`Input.IsMouseBtnPressed` 恒 false），
    // 判据与后果写在 `input_api.cpp` 那两个处理器的注释里（GoodTrip 每帧都调前者，
    // 所以"不抛错"是硬要求）。成熟度只能是 Experimental：本机没有鼠标输入源。
    {MakeId(ApiDomain::Input, 1, 0x0007), ApiDomain::Input, "Input", "GetMousePosition", kV1, 0,
     ThreadAffinity::MainUpdate, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Input, 1, 0x0008), ApiDomain::Input, "Input", "IsMouseBtnPressed", kV1, 0,
     ThreadAffinity::MainUpdate, ApiMaturity::Experimental},

    // Font surface. `Font` is the first family whose native object the Runtime allocates itself
    // (`~Font()` does not delete `this`), so every entry point here is a call into a game function
    // with a pointer this Runtime owns. Loading reads through KAGE's file manager and the metrics
    // read the loaded glyph tables; nothing here renders, and Lua only ever runs on the game
    // thread inside the Runtime's callback scope, so `ManagedCallback` is the honest affinity and
    // no frame phase is implied.
    //
    // All nine rows share owner group 2 of the Global domain: the group field is what separates
    // `Font` owns a domain of its own, matching every other object family (`Rng`, `Input`, ...):
    // the domain byte is part of the wire id, so reusing `Global` would make the ids collide with
    // the global table's own sequence.
    {MakeId(ApiDomain::Font, 1, 0x0001), ApiDomain::Font, "Font", "Load", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::HardwareVerified},
    {MakeId(ApiDomain::Font, 1, 0x0002), ApiDomain::Font, "Font", "Unload", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::HardwareVerified},
    {MakeId(ApiDomain::Font, 1, 0x0003), ApiDomain::Font, "Font", "IsLoaded", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::HardwareVerified},
    {MakeId(ApiDomain::Font, 1, 0x0004), ApiDomain::Font, "Font", "GetStringWidth", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::HardwareVerified},
    {MakeId(ApiDomain::Font, 1, 0x0005), ApiDomain::Font, "Font", "GetStringWidthUTF8", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Font, 1, 0x0006), ApiDomain::Font, "Font", "GetLineHeight", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Font, 1, 0x0007), ApiDomain::Font, "Font", "GetBaselineHeight", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Font, 1, 0x0008), ApiDomain::Font, "Font", "GetCharacterWidth", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Font, 1, 0x0009), ApiDomain::Font, "Font", "SetMissingCharacter", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Font, 1, 0x000A), ApiDomain::Font, "Font", "DrawString", kV1, 0,
     ThreadAffinity::MainRender, ApiMaturity::HardwareVerified},
    {MakeId(ApiDomain::Font, 1, 0x000B), ApiDomain::Font, "Font", "DrawStringScaled", kV1, 0,
     ThreadAffinity::MainRender, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Font, 1, 0x000C), ApiDomain::Font, "Font", "DrawStringUTF8", kV1, 0,
     ThreadAffinity::MainRender, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Font, 1, 0x000D), ApiDomain::Font, "Font", "DrawStringScaledUTF8", kV1, 0,
     ThreadAffinity::MainRender, ApiMaturity::Experimental},


    // `Vector` = `KAGE::Math::Vector2`（8 字节 `{float X, float Y}`，无虚表）。整族都是纯算术，
    // 不需要任何原生入口，所以全部为 Experimental，等真机验收后再提升成熟度。
    // `X`/`Y` 是字段（走 `__index`/`__newindex`），运算符在元表里，两者都不占 catalog 行。
    {MakeId(ApiDomain::Vector, 1, 0x0001), ApiDomain::Vector, "Vector", "Length", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Vector, 1, 0x0002), ApiDomain::Vector, "Vector", "LengthSquared", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Vector, 1, 0x0003), ApiDomain::Vector, "Vector", "Distance", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Vector, 1, 0x0004), ApiDomain::Vector, "Vector", "DistanceSquared", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Vector, 1, 0x0005), ApiDomain::Vector, "Vector", "Dot", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Vector, 1, 0x0006), ApiDomain::Vector, "Vector", "Cross", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Vector, 1, 0x0007), ApiDomain::Vector, "Vector", "GetAngleDegrees", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Vector, 1, 0x0008), ApiDomain::Vector, "Vector", "Normalize", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Vector, 1, 0x0009), ApiDomain::Vector, "Vector", "Normalized", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Vector, 1, 0x000A), ApiDomain::Vector, "Vector", "Resize", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Vector, 1, 0x000B), ApiDomain::Vector, "Vector", "Resized", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Vector, 1, 0x000C), ApiDomain::Vector, "Vector", "Rotated", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Vector, 1, 0x000D), ApiDomain::Vector, "Vector", "Clamp", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Vector, 1, 0x000E), ApiDomain::Vector, "Vector", "Clamped", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Vector, 1, 0x000F), ApiDomain::Vector, "Vector", "Lerp", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Vector, 1, 0x0010), ApiDomain::Vector, "Vector", "FromAngle", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},


    // Lua 的 `Sprite` = 引擎的 `IsaacRepentance::ANM2`。第二步补上需要 libc++ `std::string` 的三个
    // 入口（`Load`/`LoadGraphics`/`ReplaceSpritesheet`）；它们的路径串由运行时借游戏自己导入的
    // `basic_string::assign(char const*)` 代建。
    {MakeId(ApiDomain::Sprite, 1, 0x0001), ApiDomain::Sprite, "Sprite", "Play", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Sprite, 1, 0x0002), ApiDomain::Sprite, "Sprite", "SetAnimation", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Sprite, 1, 0x0003), ApiDomain::Sprite, "Sprite", "SetFrame", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Sprite, 1, 0x0004), ApiDomain::Sprite, "Sprite", "GetFrame", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Sprite, 1, 0x0005), ApiDomain::Sprite, "Sprite", "SetLayerFrame", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Sprite, 1, 0x0006), ApiDomain::Sprite, "Sprite", "GetLayerFrame", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Sprite, 1, 0x0007), ApiDomain::Sprite, "Sprite", "Update", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Sprite, 1, 0x0008), ApiDomain::Sprite, "Sprite", "IsPlaying", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Sprite, 1, 0x0009), ApiDomain::Sprite, "Sprite", "IsFinished", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Sprite, 1, 0x000A), ApiDomain::Sprite, "Sprite", "PlayRandom", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Sprite, 1, 0x000B), ApiDomain::Sprite, "Sprite", "Render", kV1, 0,
     ThreadAffinity::MainRender, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Sprite, 1, 0x000C), ApiDomain::Sprite, "Sprite", "RenderLayer", kV1, 0,
     ThreadAffinity::MainRender, ApiMaturity::Experimental},
    // `Sprite:GetTexel`（2026-09-12，真机报告 `01789211565`）：EID 的 `IsAltChoice`
    // （`main.lua:230`）用它逐像素比对底座贴图；方法不存在就是"调 nil"、整条渲染链被摘除。
    // 当前是常量实现（Switch 的 `ANM2` 没有 `GetTexel`，真实像素链路未定位），成熟度
    // 因此标 `Experimental` —— 详见 `sprite_api.cpp` 里该函数的注释。
    {MakeId(ApiDomain::Sprite, 1, 0x0012), ApiDomain::Sprite, "Sprite", "GetTexel", kV1, 0,
     ThreadAffinity::MainRender, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Sprite, 1, 0x000D), ApiDomain::Sprite, "Sprite", "IsLoaded", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Sprite, 1, 0x000E), ApiDomain::Sprite, "Sprite", "Load", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Sprite, 1, 0x000F), ApiDomain::Sprite, "Sprite", "LoadGraphics", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Sprite, 1, 0x0010), ApiDomain::Sprite, "Sprite", "ReplaceSpritesheet", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    // 批次 5：`Sprite:GetAnimation()` —— 纯读 `ANM2+0x38`（引擎自己的 `ANM2::IsPlaying` 读的是
    // 同一处布局），没有引擎调用，宿主测试可完整覆盖。
    // 批次 214：中文版 MCM（`!!Mod Config Menu Chinese`）的 `scripts/filepathhelper.lua` 要的三条 ——
    // 它用 `anm2Tester:GetDefaultAnimationName() ~= "" or anm2Tester:GetLayerCount() > 0` 探测
    // "这条路径是不是一个真 anm2"（给自己的中文字体找路径），紧接着 `anm2Tester:Reset()`；
    // **那三行不在 `pcall` 里** ⇒ 缺任一条都会抛错、把调用方整条回调打断。
    // ★ 三条 PC 文档里都没有（`mod_api_gap_report` 报 `PC 状态=unknown`）= REPENTOGON 一侧的 API；
    //   语义按引擎自己的实现取证（`ANM2::Reset @0x4A4724`、`ANM2+0xB0` 层数、动画表 `+0x98`）。
    {MakeId(ApiDomain::Sprite, 1, 0x0013), ApiDomain::Sprite, "Sprite", "Reset", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Sprite, 1, 0x0014), ApiDomain::Sprite, "Sprite", "GetLayerCount", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Sprite, 1, 0x0015), ApiDomain::Sprite, "Sprite", "GetDefaultAnimationName", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    // ---- 批次 279（2026-10-02）：overlay 三条（域内序号 0x16..0x18）。
    // 引擎符号都在 `ANM2` 上（Lua 的 `Sprite` 就是 ANM2），且都走 `char const*` 重载
    // ⇒ 落在这张绑定表的「第一步」里，不需要 libc++ `std::string` 桥。
    {MakeId(ApiDomain::Sprite, 1, 0x0016), ApiDomain::Sprite, "Sprite", "PlayOverlay", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Sprite, 1, 0x0017), ApiDomain::Sprite, "Sprite", "SetLastFrame", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Sprite, 1, 0x0018), ApiDomain::Sprite, "Sprite", "SetOverlayFrame", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    // ---- 批次 280（2026-10-02）：`GetDefaultAnimation`（契约说与 `…Name` 同一件事 ⇒ 共用一份读法）
    // 与 `Stop`（`ANM2::Stop()` @ 0xA8E4）。域内序号 0x19、0x1A。
    {MakeId(ApiDomain::Sprite, 1, 0x0019), ApiDomain::Sprite, "Sprite", "GetDefaultAnimation", kV1,
     0, ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Sprite, 1, 0x001A), ApiDomain::Sprite, "Sprite", "Stop", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    // ---- 批次 283（2026-10-02）：四条「按名字查询」（域内序号 0x1B~0x1E）。
    // 引擎侧统一 `bool ANM2::Xxx(std::string const&) const`（**只有 `std::string` 重载**，
    // 没有 `char const*` 可选）⇒ 走 libc++ 字符串桥，与 `Load` / `ReplaceSpritesheet` 同一族。
    // 语料 6 处（`BOIStageAPI15`），此前报 `attempt to call a nil value`。
    {MakeId(ApiDomain::Sprite, 1, 0x001B), ApiDomain::Sprite, "Sprite", "IsOverlayPlaying", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Sprite, 1, 0x001C), ApiDomain::Sprite, "Sprite", "IsOverlayFinished", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Sprite, 1, 0x001D), ApiDomain::Sprite, "Sprite", "IsEventTriggered", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Sprite, 1, 0x001E), ApiDomain::Sprite, "Sprite", "WasEventTriggered", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    // ---- 批次 309（2026-10-03）：`Sprite:GetFilename()`（语料 4 处，取号 = 域内空号 0x1F）----
    // PC 契约 `Sprite.md:68/70`（`#### string GetFilename ( )`；同页 `:79` 的例子给出返回值形如
    // `gfx/001.000_Player.anm2`）。★ 语料用法：`BOIStageAPI15` 拿它当**字典键**
    // （`StageAPI.NonOverrideTrapdoors[grid:GetSprite():GetFilename()]`）与 `== ""` 判断、
    // `ChallengeAPI` 把它喂给 `Sprite:Load(path, true)`。
    // ★★ 引擎侧就是 `Sprite + 0x08` 那个 libc++ `std::string`：两处具名证据（`Sprite::LoadAnimationsFile
    //   @ 0x4A48B4` 把路径 `assign` 进去、构造函数 `stp x8, xzr, [x0]` 清成空串）见
    //   `runtime_constants.hpp` 的 `kSpriteFilenameOffset` 段；读法复用 `sprite_api.cpp` 里
    //   唯一那份 `ReadLibcxxStringAt`。★ **读不到 ⇒ 返回空串 `""`**（不是 nil，与 `GetAnimation` 同口径）。
    {MakeId(ApiDomain::Sprite, 1, 0x001F), ApiDomain::Sprite, "Sprite", "GetFilename", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Sprite, 1, 0x0011), ApiDomain::Sprite, "Sprite", "GetAnimation", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},

    // `Isaac` 门面：PC Mod 的第一句常常就是 `Isaac.GetItemConfig()`（EID 正是如此），
    // 所以这一族先保证**存在且被调用时不报 Lua 错误**。
    //
    // 有真实行为的成员：`GetFrameCount` 读 Runtime 自己的帧计数、`GetTime` 读**系统毫秒时钟**
    // （`cntpct_el0`，批次 108 起；以前是"帧数/30 的整数秒"，单位差 1000 倍把 EID 的翻页闸死了）；
    // `DebugString` 走 Lua `print` 的同一个输出通道、`IsInGame` 读托管回调作用域、
    // `RunCallback` 走 Runtime 自己的回调注册表，以及批次 2 起的 `GetPlayer`（引擎基址 →
    // `Game*` → `players` 向量 → `Entity_Player`，带 vptr 校验）；其余是安全 stub——返回安全
    // 默认值，并在同一个输出通道上每个成员每会话告警一次。引擎数据（ItemConfig、
    // FindByType ...）要等引擎结构偏移定位后再接，因此整族一律 `Experimental`。
    {MakeId(ApiDomain::Isaac, 1, 0x0001), ApiDomain::Isaac, "Isaac", "GetFrameCount", kV1, 0,
     ThreadAffinity::MainUpdate, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x0002), ApiDomain::Isaac, "Isaac", "GetTime", kV1, 0,
     ThreadAffinity::MainUpdate, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x0003), ApiDomain::Isaac, "Isaac", "DebugString", kV1, 0,
     ThreadAffinity::Any, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x0004), ApiDomain::Isaac, "Isaac", "IsInGame", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x0005), ApiDomain::Isaac, "Isaac", "RunCallback", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x0006), ApiDomain::Isaac, "Isaac", "GetPlayer", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x0007), ApiDomain::Isaac, "Isaac", "GetItemConfig", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x0008), ApiDomain::Isaac, "Isaac", "FindByType", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x0009), ApiDomain::Isaac, "Isaac", "FindInRadius", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x000A), ApiDomain::Isaac, "Isaac", "CountEnemies", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x000B), ApiDomain::Isaac, "Isaac", "CountBosses", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    // `Isaac.WorldToScreen` / `Isaac.WorldToRenderPosition`（批次 195 起**真实现**）：
    // 两条都调引擎 `GetRenderPosition(pos, true)`（PLT 桩 `0x670FA0`，入口 16 字节指纹已在
    // `runtime_constants.hpp`），差别只有"要不要再加 `Room[0x1938] + Game[0x24F9B0]`"。
    // 证据逐条见 `analysis/api-restore-transforms/` 的规格文件（PC 处理函数反汇编 +
    // `Room::WorldToScreenPosition @ 0x489354`）。旧实现是恒等变换 + 每会话一次告警。
    {MakeId(ApiDomain::Isaac, 1, 0x000C), ApiDomain::Isaac, "Isaac", "WorldToScreen", kV1, 0,
     ThreadAffinity::MainRender, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x000D), ApiDomain::Isaac, "Isaac", "WorldToRenderPosition", kV1,
     0, ThreadAffinity::MainRender, ApiMaturity::Experimental},
    // 批次 195（2026-09-29）**新增**：`Isaac.ScreenToWorld(Vector)`。PC 契约
    // `tools/pc_contract_docs/Isaac.md:604/606`；Switch 引擎里**没有**这个方向的入口
    // （穷举见规格的 `no_engine_screen_to_world`），PC 自己也是就地算 ⇒ 我们照 PC 的四步算式算，
    // `WIDTH`/`HEIGHT`/`POINTSCALE` 从引擎 GOT 槽运行期读（写死 480/270 会在掌机上算错）。
    // ★ id 取域内 **max+1 = 0x005F**：规格建议的"空位 0x0014"早已被 `Entity:ToPlayer` 占用
    //   （0x0001..0x005E 无空洞），本项目既有习惯是"id 不复用、接着往下取"。
    {MakeId(ApiDomain::Isaac, 1, 0x005F), ApiDomain::Isaac, "Isaac", "ScreenToWorld", kV1, 0,
     ThreadAffinity::MainRender, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x000E), ApiDomain::Isaac, "Isaac", "GetPersistentGameData", kV1,
     0, ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x000F), ApiDomain::Isaac, "Isaac", "GetTrinketIdByName", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x0010), ApiDomain::Isaac, "Isaac", "GetCallbacks", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x0011), ApiDomain::Isaac, "Isaac", "LoadModData", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x0012), ApiDomain::Isaac, "Isaac", "SaveModData", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    // `Isaac.RenderScaledText`（批次 026 真实现；**2026-09-18 批次 036 升为 HardwareVerified**）：
    // 真机验收链见 `docs/问题与解决记录.md` 续六十一 —— 探针每帧画两行 ASCII 对照
    // （我们自己的字体 vs 这条 API），用户目视**两行都在**；报告里 `RenderScaledText=ok`。
    {MakeId(ApiDomain::Isaac, 1, 0x0013), ApiDomain::Isaac, "Isaac", "RenderScaledText", kV1, 0,
     ThreadAffinity::MainRender, ApiMaturity::HardwareVerified},

    // ==== 批次 207（2026-09-29）：为恢复 MCM（Mod Config Menu）补的 7 条 ====================
    //
    // **为什么是这几条**：权威工具 `tools/mod_api_gap_report.py --mod
    // analysis/mod-corpus/isaac-mod-config-menu` 把 MCM 用到的 192 条 API 逐条对过运行时，
    // 报出 `missing_in_runtime`。这 7 条是其中「引擎里有真实现、我们能接」的那部分；
    // 其余（例如 `Seeds:HasSeedEffect`）走 `if REPENTANCE then … else` 的 **else 支路**、
    // 运行时里 `REPENTANCE` 恒为真 ⇒ **无消费者、不用补**。
    //
    // id 全取域内 **max+1 起连续**：0x0001..0x005F 无空洞（`Entity:ToPlayer` 占了 0x0014），
    // 本项目既有习惯是"id 不复用、接着往下取"。
    //
    // `Entity:IsActiveEnemy([bool includeDead])` —— MCM 的 `RoomIsSafe()` 用它判"房间里有没有活敌人"
    // （`scripts/modconfig.lua:206`，不传参）。PC 契约 `tools/pc_contract_docs/Entity.md:454/456`。
    // ★ 尾部参数可省（MCM 不传、RepentancePlus 传 `false`）⇒ 数据行形状 `BoolOpt1`，
    //   实现是 `kEntityEngineRows` 的一行、**0 字节代码**。
    {MakeId(ApiDomain::Isaac, 1, 0x0060), ApiDomain::Isaac, "Entity", "IsActiveEnemy", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    // `Entity:HasEntityFlags(int Flags)` —— MCM 用 `entity:HasEntityFlags(EntityFlag.FLAG_FRIENDLY)`
    // 把"友方敌人"从危险里排除（`modconfig.lua:207`）。PC 契约 `Entity.md:425/427`：
    // `#### boolean HasEntityFlags ( int Flags )`，正文 "Returns true if the entity has **all**
    // named EntityFlags set." ⇒ 判据是 `(字段 & 实参) == 实参`，不是"任意一位"。
    // 数据行（字段路径）+ 一个新 `FieldKind`，仍 **0 字节代码**。
    {MakeId(ApiDomain::Isaac, 1, 0x0061), ApiDomain::Isaac, "Entity", "HasEntityFlags", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    // `Entity:ToProjectile()` —— MCM 用它把"这发子弹"换成投射物视图再读 `ProjectileFlags`
    // （`modconfig.lua:220`）。PC 契约 `Entity.md:651/653`（转换失败返回 `nil`）。
    // 判据与既有 `ToPickup`/`ToPlayer`/`ToFamiliar` 同类：`Type == 9` **且** vptr 精确等于
    // `Entity_Projectile` 的 vtable ⇒ 手写处理器（要交回**另一种视图**的句柄，数据行的返回种类覆盖不了）。
    {MakeId(ApiDomain::Isaac, 1, 0x0062), ApiDomain::Isaac, "Entity", "ToProjectile", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    // `Isaac.GetScreenWidth()` / `GetScreenHeight()` —— MCM 的 `screenhelper.lua:55/56` 用它们
    // 把界面按屏幕尺寸摆位。PC 契约 `tools/pc_contract_docs/Isaac.md:419/399`，返回 float。
    // 实现 = 读引擎 GOT 槽 `0xAAC650`/`0xAAC658`（**已有消费者**：`Isaac.WorldToScreen` 那一路
    // 读的就是这两个槽，只是没包成 Lua 方法）⇒ 复用同一个读取助手、不新增引擎偏移。
    {MakeId(ApiDomain::Isaac, 1, 0x0063), ApiDomain::Isaac, "Isaac", "GetScreenWidth", kV1, 0,
     ThreadAffinity::MainRender, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x0064), ApiDomain::Isaac, "Isaac", "GetScreenHeight", kV1, 0,
     ThreadAffinity::MainRender, ApiMaturity::Experimental},
    // `Isaac.GetEntityTypeByName(string)` / `GetEntityVariantByName(string)` —— MCM 在
    // `PostGameStarted` 里查 `"Potato Dummy"`（`modconfig.lua:260/261`）。
    // PC 契约 `Isaac.md:218`（找不到返回 `0`）/ `Isaac.md:235`（找不到返回 `-1`）。
    // ★ 如实说明：`Potato Dummy` **既不在本体 `resources/entities2.xml`（763 条）也不在
    //   `rp_patch/resources/entities2.xml`（1337 条）里**（本轮逐条扫过）⇒ 接口补全后这两条调用
    //   仍会返回 `0` / `-1`，与 PC 上"这个实体不存在"的表现**一致**。补它的意义是"接口存在、
    //   名字表按本体的 763 条真查"，不是"让 MCM 的那个特判生效"。
    {MakeId(ApiDomain::Isaac, 1, 0x0065), ApiDomain::Isaac, "Isaac", "GetEntityTypeByName", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x0066), ApiDomain::Isaac, "Isaac", "GetEntityVariantByName", kV1,
     0, ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},

    // 批次 2：引擎实体只读视图。`Isaac.GetPlayer`（条目 `0x0E010006`，id 不变）从批次 2 起是
    // 真实现（读引擎内存）；另外四个方法挂在 `Entity` / `EntityPlayer` 的元表上（owner 就是元表名）。
    //
    // 域仍是 `Isaac`（都是引擎门面这一族），sequence 从 0x0014 继续，id 不复用。
    // `EntityPlayer` 的字段（`Position`/`Type`/`Variant`/`SubType`/`Index`/`PlayerType`/`Size`）
    // **不占 catalog 行**：它们是 `__index` 里的名字、没有独立的 `lua_CFunction`，
    // 与 `Vector` 的 `X`/`Y` 同例（Catalog 门禁要求"登记了就必须真的被注册"）。
    // 2026-10-10：GetData按实体寿命保留Lua表，Remove后清、D2退役；宿主已验证。
    {MakeId(ApiDomain::Isaac, 1, 0x0014), ApiDomain::Isaac, "Entity", "ToPlayer", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x0015), ApiDomain::Isaac, "EntityPlayer", "HasCollectible", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::HardwareVerified},
    {MakeId(ApiDomain::Isaac, 1, 0x0016), ApiDomain::Isaac, "EntityPlayer", "GetPlayerType", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x0017), ApiDomain::Isaac, "EntityPlayer", "GetData", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::HostVerified},

    // 批次 2b：`ItemConfig` 只读视图。`Isaac.GetItemConfig`（条目 `0x0E010007`，id 不变）从批次 2b
    // 起是真实现（`IC = Manager + 0x36538` 的内嵌对象），另外七个方法挂在 `ItemConfig` /
    // `ItemConfig_Item` 的元表上（owner 就是元表名）。
    //
    // 域仍是 `Isaac`，sequence 从 0x0018 继续，id 不复用。条目的字段
    // （`ID`/`Type`/`Name`/`Description`）与 `EntityPlayer` 的 `Position` 同例：`__index` 里的名字、
    // 没有独立的 `lua_CFunction`，所以**不占 catalog 行**（Catalog 门禁要求"登记了就必须真的被注册"）。
    // `HasTags` 两条在**批次 195（2026-09-29）从"存在但恒假"改成真实现**：
    // tags 位掩码已定位在 `ItemConfig::Item + 0xC0`（**8 字节、33 位**，写点唯一 + 三个读者 +
    // 8 字节清零，逐条见 `runtime_constants.hpp` 的 `kItemConfigItemTagsOffset`），
    // 口径 = 引擎自己三处同形的"任一命中" `(Tags & mask) != 0`。
    // ⚠️ 旧常量指的 `+0x58` 其实是 items.xml 的 `maxhearts=`（所以旧实现读的是"加多少心"）。
    // PC 里 `HasTags` 挂在条目上（`item:HasTags(tag)`），本批次两处都给：`ItemConfig:HasTags(id, mask)`
    // 是门面级的便捷形式（**PC 上没有这条**，id 按收藏品向量索引 —— 签名由我们定义），
    // `ItemConfig_Item:HasTags(mask)` 与 PC 签名一致（`tools/pc_contract_docs/ItemConfig_Item.md:23`）。
    {MakeId(ApiDomain::Isaac, 1, 0x0018), ApiDomain::Isaac, "ItemConfig", "GetCollectible", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x0019), ApiDomain::Isaac, "ItemConfig", "GetTrinket", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x001A), ApiDomain::Isaac, "ItemConfig", "GetCard", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x001B), ApiDomain::Isaac, "ItemConfig", "GetPillEffect", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x001C), ApiDomain::Isaac, "ItemConfig", "IsCollectible", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x001D), ApiDomain::Isaac, "ItemConfig", "HasTags", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x001E), ApiDomain::Isaac, "ItemConfig_Item", "HasTags", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},

    // 批次 3：EID 的**渲染**路径在 `EID:setPlayer()`（`main.lua:1061`）与描述文本构建里
    // 直接调用的成员。前四条挂在 `EntityPlayer` 元表上（owner 就是元表名），
    // `ControllerIndex` **不占 catalog 行**（`__index` 里的名字，与 `Position` 同例）。
    //
    // 偏移与证据（`runtime_constants.hpp` 的 Entity_Player 段）：
    //   * `GetOtherTwin`：真机单人场景返回 nil（PC 文档：非双人角色返回 nil）；
    //   * `GetEffectiveMaxHearts` / `GetSoulHearts` / `GetBrokenHearts`：读 `+0x16B8`
    //     （+ 骨心 `+0x2450`）、`+0x16C4`、`+0x2470`，**恒返回数字**（EID 对它们做算术，
    //     返回 nil 会变成 "attempt to perform arithmetic on a nil value"）；
    //   * `ControllerIndex`：`+0x19EC`，`SetControllerIndex` 的第一条存值指令。
    //
    // `ItemConfig_Item.IsCollectible()`（**无参**，挂在条目上）：EID 在
    // `main.lua:669`/`738`/`757` 直接写 `itemConfig:IsCollectible()`，缺了它那些描述构建
    // 会在调用处报 "attempt to call a nil value"。
    {MakeId(ApiDomain::Isaac, 1, 0x001F), ApiDomain::Isaac, "EntityPlayer", "GetOtherTwin", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x0020), ApiDomain::Isaac, "EntityPlayer",
     "GetEffectiveMaxHearts", kV1, 0, ThreadAffinity::ManagedCallback,
     ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x0021), ApiDomain::Isaac, "EntityPlayer", "GetSoulHearts", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x0022), ApiDomain::Isaac, "EntityPlayer", "GetBrokenHearts", kV1,
     0, ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x0023), ApiDomain::Isaac, "ItemConfig_Item", "IsCollectible",
     kV1, 0, ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},

    // 批次 7（2026-09-15）：补齐 EID 用到但**运行时里完全没有**的两条（缺了就是
    // "attempt to call a nil value"，落在条件回调里会让整条描述静默消失）：
    //
    //   0x004F `EntityPlayer.GetCollectibleCount()` —— 收藏品容器（`+0x1AB8`/`+0x1AC0` 的
    //          begin/end 对）里的格子数。EID 的背包合成（`eid_bagofcrafting.lua:489`/`492`）
    //          拿它当"收藏品数量变了没"的信号。
    //   0x0050 `ItemConfig_Item.IsTrinket()` —— `Type == ITEM_TRINKET`（`kItemTypeTrinket = 2`），
    //          与既有的 `IsCollectible()` 同一形状。
    {MakeId(ApiDomain::Isaac, 1, 0x004F), ApiDomain::Isaac, "EntityPlayer", "GetCollectibleCount",
     kV1, 0, ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x0050), ApiDomain::Isaac, "ItemConfig_Item", "IsTrinket",
     kV1, 0, ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},

    // 批次"IsAvailable 一族"（2026-09-16）：EID 在 `features/eid_api.lua:1988`/`:2013` 与
    // `eid_bagofcrafting.lua:826` 上**无保护**地调 `item:IsAvailable()`（收藏品条目），
    // 缺它就是"attempt to call a nil value"，整条回调被摘 ⇒ Spindown Dice / 背包合成失效。
    // 语义：PC 文档"true = 已解锁；false = 没解锁或被 tags 挡掉"；实现按条目所属向量分派引擎的
    // `Item`/`Card`/`PillEffect::IsAvailable`，其中 `Item` 那条的 `flags` 是我们的兼容层定义
    // （已登记偏离）。取证见 `docs/问题与解决记录.md` 续十二。
    {MakeId(ApiDomain::Isaac, 1, 0x0055), ApiDomain::Isaac, "ItemConfig_Item", "IsAvailable",
     kV1, 0, ThreadAffinity::ManagedCallback, ApiMaturity::HardwareVerified},

    // 批次 242（2026-09-30）：`ItemConfig_Item:IsRune()`（域内序号 0x007E = 上一个 max 0x007D + 1）。
    // ★ 为什么补：EID 有三处**无保护**地调 `EID.itemConfig:GetCard(id):IsRune()`
    //   （`eid_bagofcrafting.lua:102` / `eid_itemprediction.lua:327` / `eid_modifiers.lua:1277`）
    //   ⇒ 缺它时每帧抛 `attempt to call a nil value (method 'IsRune')`；真机读数里 EID 的
    //   `MC_POST_RENDER` 因此占到全部托管回调时间的 **90%**（用户看到"进 EID 配置页卡到 20~30 帧"）。
    // ★ 契约与类名：PC 文档把这条放在 **`ItemConfig_Card`** 类下（IsaacDocs
    //   `ItemConfig_Card.md:29`，带 `.reporplus` = REPENTOGON 一侧）；我们这边卡牌条目与
    //   `ItemConfig_Item` 族共用同一张元表（`ItemConfig:GetCard()` 返回的就是它），所以目录行写在
    //   `ItemConfig_Item` 名下 —— 模组调用形态与 PC 完全一致（`GetCard(id):IsRune()`）。
    // ★ 真值来源：直读引擎的**卡类型**一格（`ItemConfig::Card+0x58`，== 2 ⇒ 符文），
    //   出处是引擎自己在 `UseActiveItem` 里对 `CLEAR_RUNE` 的判定（见 `runtime_constants.hpp`
    //   的 `kItemConfigCardTypeOffset` / `kItemConfigCardTypeRune`）。
    {MakeId(ApiDomain::Isaac, 1, 0x007E), ApiDomain::Isaac, "ItemConfig_Item", "IsRune",
     kV1, 0, ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},

    // 批次 9（2026-09-15）：`Entity:ToFamiliar()` —— EID 用到而运行时里没有的一条。
    // 判据同 `Entity:ToPickup()`：`Type == ENTITY_FAMILIAR(3)` 且 vptr 精确等于
    // `base + 0xA35728`（`_ZTVN15IsaacRepentance15Entity_FamiliarE` @ `0xA35718` 加 `0x10`，
    // 与既有两个 vtable 常量同一条规则、互为交叉验证）。
    {MakeId(ApiDomain::Isaac, 1, 0x0051), ApiDomain::Isaac, "Entity", "ToFamiliar", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    // 批次 12（2026-09-16）：`GridEntity` 族两条 —— EID 的网格描述用 `entity:GetVariant()`
    // 与具体 variant 比较。前置是"网格实体视图"这一族本身：`Room:GetGridEntity()` 过去恒返回
    // nil（登记在案的偏离），表已定位（`Room + 0x30`，证据见 `runtime_constants.hpp`）。
    {MakeId(ApiDomain::Isaac, 1, 0x0052), ApiDomain::Isaac, "GridEntity", "GetVariant", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::HardwareVerified},
    {MakeId(ApiDomain::Isaac, 1, 0x0053), ApiDomain::Isaac, "GridEntity", "GetType", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::HardwareVerified},
    // 批次 13（2026-09-16）：`GridEntity:GetRNG()` —— EID 的
    // `features/eid_itemprediction.lua:120` 直接 `spikes:GetRNG():GetSeed()`（血契尖刺的种子）。
    // 实体自己的 RNG 在 `GridEntity + 0x30`（证据：`GridEntity::hurt_func` 里
    // `add x0, x19, #0x30; bl RNG::Next`，以及 `GridEntity_Spikes::InitSubclass` 里
    // `add x0, x19, #0x30; RNG::SetSeed(…, 35)`；见 `runtime_constants.hpp`）。
    // ★ 交回 Lua 的是**调用瞬间的 16 字节快照**（PC 返回活引用），已登记为偏离。
    {MakeId(ApiDomain::Isaac, 1, 0x0054), ApiDomain::Isaac, "GridEntity", "GetRNG", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::HardwareVerified},
    // 批次 272（2026-10-02）：`GridEntity:Init(int Seed)`（域内序号 0x0095，语料 15 处）。
    // 引擎入口 `GridEntity::Init(unsigned)` @ `0x37E438`（arity 1）；同址另有
    // `Init(Desc const&)` @ `0x37E4BC` —— **只接契约里那一参重载**。
    // ★ 它把种子写进 `GridEntity + 0x18`，与批次 262 为 `Isaac.GridSpawn` 记下的那一格互证。
    {MakeId(ApiDomain::Isaac, 1, 0x0095), ApiDomain::Isaac, "GridEntity", "Init", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    // ---- 批次 276（2026-10-02）：`GridEntity` 的 `GetGridIndex` + 7 条子类转换（域内序号 0xAB..0xB2）。
    // ★ `GetGridIndex` 读的是 `GridEntity + 0x28`（早有取证的 `kGridEntityGridIndexOffset`）。
    // ★ 7 条转换走与 `Entity:ToPlayer()` 一族**同一条 vtable 判据** —— vtable 常量按
    //   「`_ZTV` 符号地址 + 0x10」算（该式子用既有常量验证过，见 `runtime_constants.hpp` 批次 276 段）。
    //   命中给**基类 `GridEntity` 视图**（子类视图还不存在，与 `Entity:ToFamiliar()` 同一先例）。
    {MakeId(ApiDomain::Isaac, 1, 0x00AB), ApiDomain::Isaac, "GridEntity", "GetGridIndex", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x00AC), ApiDomain::Isaac, "GridEntity", "ToPit", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x00AD), ApiDomain::Isaac, "GridEntity", "ToRock", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x00AE), ApiDomain::Isaac, "GridEntity", "ToDoor", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x00AF), ApiDomain::Isaac, "GridEntity", "ToTNT", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x00B0), ApiDomain::Isaac, "GridEntity", "ToPoop", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x00B1), ApiDomain::Isaac, "GridEntity", "ToPressurePlate", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x00B2), ApiDomain::Isaac, "GridEntity", "ToSpikes", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},

    // 批次 4：房间实体枚举（`Isaac.FindInRadius`/`FindByType`/`CountEnemies` 从 stub 变成
    // 真实现，id 不变）与实体视图补全。
    //
    //   0x0024 `Entity.ToPickup`      —— `Type==5` 且 vptr == `base+0xA36E28` → `EntityPickup` 视图
    //   0x0025 `Entity.GetData`       —— Runtime 自管的稳定 Lua 表（引擎**没有**这个字段）
    //   0x0026 `EntityPlayer.GetActiveItem` / 0x0027 `GetTrinket` / 0x0028 `GetBabySkin`
    //
    // `EntityPlayer.GetData`（0x0017）**语义改变**：批次 2 起它返回 nil（"ModData 结构还没有
    // 证据"），批次 4 起返回 Runtime 自管的那张稳定表（同一实体每次都拿到同一张表），因为
    // EID 真的往它里面写（`features/eid_api.lua:2229`：`entity:GetData()[str] = value`）。
    // 字段（`Price`/`ShopItemId`/…）走 `__index`，不占 catalog 行。
    {MakeId(ApiDomain::Isaac, 1, 0x0024), ApiDomain::Isaac, "Entity", "ToPickup", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    // 批次 063：`Entity:IsFlying()` —— PC 在基类 `Entity` 上（`Entity.md`），
    // 而 `EntityPlayer` 继承基类方法。GoodTrip 的诅咒房判定（`scripts/trip.lua:90`）要用它，
    // 没有它时刺房（type 10）整条传送路径报 "attempt to call a nil value (method 'IsFlying')"。
    // id 取域内下一个空号（0x002E）。
    {MakeId(ApiDomain::Isaac, 1, 0x002E), ApiDomain::Isaac, "Entity", "IsFlying", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    // 批次 065：`Entity:TakeDamage(Damage, DamageFlags, Source, CountdownFrames)` ——
    // GoodTrip 的诅咒房过路费（`scripts/trip.lua:70`）要用它（配合全局 `EntityRef(entity)`）。
    // **手写**：签名里有 float + 一个按引用交给引擎的 `EntityRef` 句柄，还要按接收者种类选入口
    // （玩家用 `Entity_Player::TakeDamage`、其余用基类），数据行那套形状覆盖不了 —— 理由写在
    // 实现处。**已知偏离**：`DamageFlags` 在引擎侧没有对应形参，这一版被忽略（伤害照常造成）。
    {MakeId(ApiDomain::Isaac, 1, 0x002F), ApiDomain::Isaac, "Entity", "TakeDamage", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x0025), ApiDomain::Isaac, "Entity", "GetData", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::HostVerified},
    {MakeId(ApiDomain::Isaac, 1, 0x0026), ApiDomain::Isaac, "EntityPlayer", "GetActiveItem", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x0027), ApiDomain::Isaac, "EntityPlayer", "GetTrinket", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x0028), ApiDomain::Isaac, "EntityPlayer", "GetBabySkin", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    // 批次 6（2026-09-12）：EID 在逐帧路径上调用的一批 `EntityPlayer` 成员。
    //
    // 真机报告 `01789210946` 的 `features/eid_api.lua:2606` 是 `player:GetPill(0)`：
    // 缺一个方法就是 "attempt to call a nil value"，**整条 update 回调**被派发器
    // 静默摘除（屏幕全空、游戏不崩）。所以这一批先把名字补齐、返回类型正确的默认值，
    // 具体数值等引擎字段偏移定位后再逐个换成真实现 —— 成熟度因此统一标 `Experimental`，
    // 默认值的选取规则见 `isaac_api.cpp` 里这一批实现开头的长注释。
    {MakeId(ApiDomain::Isaac, 1, 0x0030), ApiDomain::Isaac, "EntityPlayer", "GetPill", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x0031), ApiDomain::Isaac, "EntityPlayer", "GetCard", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x0032), ApiDomain::Isaac, "EntityPlayer", "GetMainTwin", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x0033), ApiDomain::Isaac, "EntityPlayer", "GetCollectibleRNG", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x0034), ApiDomain::Isaac, "EntityPlayer", "GetTrinketRNG", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x0035), ApiDomain::Isaac, "EntityPlayer", "GetCardRNG", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x0036), ApiDomain::Isaac, "EntityPlayer", "GetPillRNG", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x0037), ApiDomain::Isaac, "EntityPlayer", "GetNumKeys", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x0038), ApiDomain::Isaac, "EntityPlayer", "GetNumBombs", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x0039), ApiDomain::Isaac, "EntityPlayer", "GetNumCoins", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x003A), ApiDomain::Isaac, "EntityPlayer", "GetHearts", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x003B), ApiDomain::Isaac, "EntityPlayer", "GetMaxHearts", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x003C), ApiDomain::Isaac, "EntityPlayer", "GetSoulCharge", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x003D), ApiDomain::Isaac, "EntityPlayer", "GetBloodCharge", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x003E), ApiDomain::Isaac, "EntityPlayer", "GetPoopMana", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x003F), ApiDomain::Isaac, "EntityPlayer", "GetPoopSpell", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x0040), ApiDomain::Isaac, "EntityPlayer", "GetZodiacEffect", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x0041), ApiDomain::Isaac, "EntityPlayer", "GetModelingClayEffect", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x0042), ApiDomain::Isaac, "EntityPlayer", "GetGlyphOfBalanceDrop", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x0043), ApiDomain::Isaac, "EntityPlayer", "GetCollectibleNum", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x0044), ApiDomain::Isaac, "EntityPlayer", "GetTrinketMultiplier", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x0045), ApiDomain::Isaac, "EntityPlayer", "GetPlayerFormCounter", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x0046), ApiDomain::Isaac, "EntityPlayer", "GetSmeltedTrinkets", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x0047), ApiDomain::Isaac, "EntityPlayer", "GetEffects", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x0048), ApiDomain::Isaac, "EntityPlayer", "GetName", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x0049), ApiDomain::Isaac, "EntityPlayer", "HasTrinket", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x004A), ApiDomain::Isaac, "EntityPlayer", "HasGoldenBomb", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x004B), ApiDomain::Isaac, "EntityPlayer", "HasPlayerForm", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x004C), ApiDomain::Isaac, "EntityPlayer", "CanPickRedHearts", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x004D), ApiDomain::Isaac, "EntityPlayer", "IsSubPlayer", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    // 0x004E `EntityPlayer.AddCollectible` —— **真实现**（2026-09-14）：底座是
    // `Entity_Player::AddCollectible`（`0x292A74`，清单里的 `missing_easy`），签名
    // `(type, charge, force, slot, varData)`，返回值取"**实际结果**"（调用后用 `HasCollectible` 复核），
    // 因为引擎那一层的返回类型我们没从反汇编确认过 —— 用效果说话更稳。
    {MakeId(ApiDomain::Isaac, 1, 0x004E), ApiDomain::Isaac, "EntityPlayer", "AddCollectible", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    // 0x0056 `EntityPlayer.AddCoins` —— **真实现**（2026-09-18）：底座是
    // `Entity_Player::AddCoins(int)`（`0x280068`，清单里的 `missing_easy`，符号
    // `_ZN15IsaacRepentance13Entity_Player8AddCoinsEi`）。PC 签名 `AddCoins(int Amount)`、返回 void。
    //
    // 为什么 id 取"域内下一个空号"而不是照抄 PC 的某个编号：**API 的 id 是我们内部的
    // 索引，模组看不到它**（模组是用 `player:AddCoins(n)` 这种名字调的，不像 `ModCallbacks`
    // 那样要传数字）—— 取域内**下一个空号**（0x004E 给 `AddCollectible`、0x004F 给
    // `GetCollectibleCount` 时用的都是这条规则）。⚠️ 别抄我上一版写的 0x004F：那个号已经被
    // `GetCollectibleCount` 占了，`Validate()` 的"id 必须唯一"会直接判红（2026-09-18 就这么红过一次）。
    // 真正影响兼容性的是**方法名与参数表**，那两条与 PC 文档逐字一致。
    {MakeId(ApiDomain::Isaac, 1, 0x0056), ApiDomain::Isaac, "EntityPlayer", "AddCoins", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    // 0x0057~0x005A `EntityPlayer` 的四个引擎方法 —— **真实现**（2026-09-19 批次 050）。
    // 底座与偏移：`SetShootingCooldown` @ `0x2FB994`、`AnimateHappy` @ `0x2F6CA8`、
    // `AnimateSad` @ `0x2F6D2C`、`GetBlackHearts` → 引擎侧符号 `GetNumBlackHearts` @ `0x27FF84`
    // （见 `runtime_constants.hpp` 的批次 050 段，每条带入口指纹）。
    //
    // 为什么这一批是这四个：真机把错误推进到 `scripts/control.lua:38` 的
    // `player:SetShootingCooldown(2)`（"打开地图后按方向键"那条路），而它在
    // `widget.draw_minimap_ui()` **之前** ⇒ 缺它屏幕什么都不画；另外三个是同一条路上
    // 紧随其后的调用点（`AnimateHappy`/`AnimateSad` 在传送成功/失败时各一次，
    // `GetBlackHearts` 在传送前的体力判断里连调两次）。
    // id 仍取域内下一个空号（0x0056 之后连着四个），理由同上。
    {MakeId(ApiDomain::Isaac, 1, 0x0057), ApiDomain::Isaac, "EntityPlayer", "SetShootingCooldown",
     kV1, 0, ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    // 0x0058 / 0x0059 / 0x005A（批次 051）：`AnimateHappy()`、`AnimateSad()`、`GetBlackHearts()`。
    // 三个都走**引擎方法数据行**（`engine_method_api.hpp`）——每个 API 只花 16 字节只读数据、
    // 0 字节代码；这正是"以后加 API 不再撞代码段预算"的落点（050 就是被预算逼着砍掉它们的）。
    // `GetBlackHearts` 的引擎符号叫 `GetNumBlackHearts`（同族 `GetNumCoins` 那种命名）。
    {MakeId(ApiDomain::Isaac, 1, 0x0058), ApiDomain::Isaac, "EntityPlayer", "AnimateHappy", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x0059), ApiDomain::Isaac, "EntityPlayer", "AnimateSad", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x005A), ApiDomain::Isaac, "EntityPlayer", "GetBlackHearts", kV1,
     0, ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    // 0x005B `EntityPlayer.AddNullCostume(int NullId)`（批次 137，2026-09-26）——
    // The Specialist for Good Items 的舞蹈段落要它（给玩家换上一套临时服装）。底座
    // `Entity_Player::AddNullCostume(ItemConfig::eNullItemID)` @ `0x291BBC`（符号 + 入口 4 字节
    // 指纹见 `runtime_constants.hpp`），走**引擎方法数据行**（`Void1`，与 `AddCoins` 同一个 ABI）。
    {MakeId(ApiDomain::Isaac, 1, 0x005B), ApiDomain::Isaac, "EntityPlayer", "AddNullCostume", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    // 0x005C `EntityPlayer.TryRemoveNullCostume(int NullId)`（批次 137）—— 同一模组"跳舞结束/
    // 物品丢掉时摘掉临时服装"的那一半。底座 `Entity_Player::TryRemoveCostume(ItemConfig::eNullItemID)`
    // @ `0x2F2170`（`Entity_Player` 下三条 `TryRemoveCostume` 重载里 `eNullItemID` 那条），
    // 同样走引擎方法数据行（`Void1`）。
    {MakeId(ApiDomain::Isaac, 1, 0x005C), ApiDomain::Isaac, "EntityPlayer", "TryRemoveNullCostume",
     kV1, 0, ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    // 0x0029 `EntityPickup.IsShopItem` —— **真实现**（2026-09-29 批次 201）：判据 = `Price != 0`
    // （引擎 `Entity_Pickup + 0x564`；三条指令级互证 + isaacscript `PickupPrice` 文档写在
    // `isaac_api.cpp` 里 `EntityPickupIsShopItem` 的上方注释）。EID 在卡片/药丸描述路径上
    // **无条件**调用它（`main.lua:1611`/`1636`、`main.lua:926`、`features/eid_bagofcrafting.lua:935`）
    // —— 修好之前恒 false ⇒ 商店里「该隐藏的描述」永远不隐藏。
    // `EntityPickup` 的字段（`Price`/`ShopItemId`/`OptionsPickupIndex`/`ForceBlind`/`Touched`）
    // 走 `__index`，不占 catalog 行。
    {MakeId(ApiDomain::Isaac, 1, 0x0029), ApiDomain::Isaac, "EntityPickup", "IsShopItem", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    // 批次 028：`EntityPickup:CanReroll()`（EID 链式缺口的一半；同名的 `EntityNPC:CanReroll`
    // 要等我们有了 `EntityNPC` 视图才能接 —— 见 `runtime_constants.hpp` 的注释）。
    {MakeId(ApiDomain::Isaac, 1, 0x002B), ApiDomain::Isaac, "EntityPickup", "CanReroll", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    // 批次 041（GoodTrip）：`Isaac.GetRoomEntities()`（id 0x002C）**真实现** —— 语义照 PC 文档
    //（`Isaac.md:382` "all entities in the room"），来源与 `Isaac.FindByType` 同一套三段扫描
    //（活表 + 玩家向量 + 效果表，去重）；缺它 GoodTrip 的 `scripts/trip.lua:38` 直接索引 nil。
    // `Isaac.ExecuteCommand()`（id 0x002D）：批次 041~120 是**平台降级**（当时的结论是"Switch 没有
    // 控制台"）；**批次 121 起是真实现** —— 运行时自己把游戏本体的 `IsaacRepentance::Console`
    // 建起来、把命令喂给它（类与命令实现一直都在镜像里，只是引擎从不实例化它），并**返回控制台
    // 输出的字符串**（PC 契约 `Isaac.md:106` 就是 `string ExecuteCommand(string command)`）。
    // 残留的偏离只有两条：命令长度上限 127 字节、当前没有玩家时拒绝执行（返回空串）——
    // 登记在 `api_deviation.cpp` 的 `0x0E01002D`，判据与取证见 `infrastructure/console/console_bridge.hpp`。
    {MakeId(ApiDomain::Isaac, 1, 0x002C), ApiDomain::Isaac, "Isaac", "GetRoomEntities", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x002D), ApiDomain::Isaac, "Isaac", "ExecuteCommand", kV1, 0,
     ThreadAffinity::MainUpdate, ApiMaturity::Experimental},
    // 批次 139（2026-09-26）：`Isaac.GetCostumeIdByPath(string path)` —— PC 契约
    // `tools/pc_contract_docs/Isaac.md:190`（同页 :192 明写"找不到返回 **-1**"）。
    // The Specialist for Good Items 在**文件作用域**就用它建两张服装表（`main.lua:26/29`）
    // ⇒ 缺它整个模组加载失败。实现：遍历 null 道具向量、比条目 `+0x88` 的 anm2 路径、返回 `+0x04`
    // （偏移的两条互证指令见 `runtime_constants.hpp` 的 `kItemConfigItemNullCostumePathOffset`）。
    {MakeId(ApiDomain::Isaac, 1, 0x005D), ApiDomain::Isaac, "Isaac", "GetCostumeIdByPath", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    // 批次 148（2026-09-26）：`Isaac.GetMusicIdByName(string musicName)` —— 同一个模组
    // "捡到四级物品**放歌**"那半条路（`main.lua:477/478` 拿 `specialist`/`paincialist` 的编号，
    // `:185/186` 拿 `s_<角色>` 那一族的编号）。缺它就是
    // "attempt to call a nil value (field 'GetMusicIdByName')" ⇒ 整条 `MC_POST_UPDATE` 被摘掉。
    // PC 契约 `tools/pc_contract_docs/Isaac.md:290`（`:292` 明写"找不到返回 **-1**"，
    // `:298` 的例子 `"Title Screen"` → 61）⇒ **编号就是曲目表下标**。
    // 实现：遍历 `Music + 0x3D8` 的 `vector<Music::Entry>`（步长 `0x70`）比条目起点的名字串，
    // 命中返回下标（"id 就是下标"由 `Music::Play` 的 `begin + id*0x70` 反汇编佐证）。
    // 域内序号取 0x005E（下一个空号，与 `AddCoins` 取 0x0056 同一条规则）。
    {MakeId(ApiDomain::Isaac, 1, 0x005E), ApiDomain::Isaac, "Isaac", "GetMusicIdByName", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    // 批次 5：`Entity.GetSprite()`（id 0x002A）—— 真实现，**只读**：返回 `Entity + 0x50` 那个
    // 内嵌 `ANM2` 的 `Sprite` 视图（偏移证据见 `runtime_constants.hpp` 的 `kEntitySpriteOffset`）。
    // 句柄带"引擎实体来源"标记（`kSpriteSourceEngineEntity`）：`__gc` 不析构、不释放引擎对象，
    // 每次访问重新校验实体还活着（`lua_object_handles.hpp` 的 `SpriteHandle` 注释）。
    // EID 的 `EID:IsAltChoice()`（`main.lua:216`）在宝藏房里就靠它，缺了它整段描述渲染中断。
    {MakeId(ApiDomain::Isaac, 1, 0x002A), ApiDomain::Isaac, "Entity", "GetSprite", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},

    // `Options` 表：EID 只读 `HUDOffset` 与 `Language` 两个字段，没有它们 EID 一加载就报错。
    // 这两条是**值**而不是方法（绑定表里没有 `lua_CFunction`），值由
    // `interfaces/lua/isaac_api.cpp` 的 `RegisterOptionsTable` 写进表里；PC 版是从引擎选项
    // 结构读的，偏移尚未定位，所以先给与 EID 中文默认配置一致的兼容值。
    // 2026-10-09更正：HUDOffset动态读写Manager+0x36514，见PC/NS字段与setter取证。
    {MakeId(ApiDomain::Global, 2, 0x0001), ApiDomain::Global, "Options", "HUDOffset", kV1, 0,
     ThreadAffinity::Any, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Global, 2, 0x0002), ApiDomain::Global, "Options", "Language", kV1, 0,
     ThreadAffinity::Any, ApiMaturity::Experimental},

    {MakeId(ApiDomain::Global, 2, 0x000B), ApiDomain::Global, "Options", "AnnouncerVoiceMode", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::HostVerified},
    {MakeId(ApiDomain::Global, 2, 0x000C), ApiDomain::Global, "Options", "FoundHUD", kV1, 0,
     ThreadAffinity::Any, ApiMaturity::Experimental},

    // 最小 `debug` 库（批次 3）：只有一个 `debug.getinfo`，因为 EID 的
    // `GetCurrentModPath`（`main.lua:148`）用 `debug.getinfo(fn).source` 直接取真实 mod 路径
    // （`@<mod 根>/main.lua`），比 `require("")` 的错误文本 hack 可靠得多。它同样是**值 +
    // 函数**形态的表：表本身由 `lua_runtime.cpp` 建（`RegisterDebugLibrary`），这里的条目是
    // 表里的成员名（与 `Options` 的两个字段同一种登记方式）。
    {MakeId(ApiDomain::Global, 2, 0x0003), ApiDomain::Global, "debug", "getinfo", kV1, 0,
     ThreadAffinity::Any, ApiMaturity::Experimental},

    // 最小 `os` 库（2026-09-12 批次 3 后补）：EID 的 `features/eid_tmtrainer.lua:200` 用
    // `os.date("%m/%d")` 判愚人节彩蛋，而我们提供 `debug`（真值）却不提供 `os` 时
    // `os.date` 索引 nil 会抛错、整包加载死在那一行。
    //
    // **刻意不提供** `remove`/`rename`/`tmpname`/`exit`（前三个是文件系统写操作，本模块的
    // 写通道尚未打通；`exit` 会直接结束玩家的游戏）—— 因此这里只登记实际存在的 7 个成员，
    // 而不是照抄 PC 的 `os` 库。表本身由 `lua_runtime.cpp` 的 `RegisterOsLibrary` 建。
    {MakeId(ApiDomain::Global, 2, 0x0004), ApiDomain::Global, "os", "clock", kV1, 0,
     ThreadAffinity::Any, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Global, 2, 0x0005), ApiDomain::Global, "os", "date", kV1, 0,
     ThreadAffinity::Any, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Global, 2, 0x0006), ApiDomain::Global, "os", "difftime", kV1, 0,
     ThreadAffinity::Any, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Global, 2, 0x0007), ApiDomain::Global, "os", "getenv", kV1, 0,
     ThreadAffinity::Any, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Global, 2, 0x0008), ApiDomain::Global, "os", "setlocale", kV1, 0,
     ThreadAffinity::Any, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Global, 2, 0x0009), ApiDomain::Global, "os", "time", kV1, 0,
     ThreadAffinity::Any, ApiMaturity::Experimental},

    // Diagnostic-only surface, never part of the Mod-visible API contract.
    {MakeId(ApiDomain::Diagnostic, 1, 0x0001), ApiDomain::Diagnostic, "RuntimeTest",
     "MarkPostUpdate", kV1, 0, ThreadAffinity::MainUpdate, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Diagnostic, 1, 0x0002), ApiDomain::Diagnostic, "RuntimeTest",
     "MarkPostRender", kV1, 0, ThreadAffinity::MainRender, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Diagnostic, 1, 0x0003), ApiDomain::Diagnostic, "RuntimeTest",
     "MarkPostRenderPaused", kV1, 0, ThreadAffinity::MainRender, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Diagnostic, 1, 0x0004), ApiDomain::Diagnostic, "RuntimeTest",
     "MarkMusicDiagnosticCycleCompleted", kV1, 0, ThreadAffinity::MainRender,
     ApiMaturity::Experimental},
    {MakeId(ApiDomain::Diagnostic, 1, 0x0005), ApiDomain::Diagnostic, "RuntimeTest",
     "MarkMusicDiagnosticCurrentId", kV1, 0, ThreadAffinity::MainRender,
     ApiMaturity::Experimental},

    // `RuntimeMods`：运行时自带的模组开关菜单的控制面（2026-09-16，路线 B）。
    // 这四个成员**不是 PC API**（PC 的模组开关在游戏菜单里，Lua 看不到模组清单），
    // 只给运行时自带的那个菜单脚本用：读清单 / 改开关 / 落盘 / 重读。
    {MakeId(ApiDomain::ModMenu, 1, 0x0001), ApiDomain::ModMenu, "RuntimeMods", "List", kV1, 0,
     ThreadAffinity::MainUpdate, ApiMaturity::Experimental},
    {MakeId(ApiDomain::ModMenu, 1, 0x0002), ApiDomain::ModMenu, "RuntimeMods", "SetEnabled", kV1,
     0, ThreadAffinity::MainUpdate, ApiMaturity::Experimental},
    {MakeId(ApiDomain::ModMenu, 1, 0x0003), ApiDomain::ModMenu, "RuntimeMods", "Save", kV1, 0,
     ThreadAffinity::MainUpdate, ApiMaturity::Experimental},
    {MakeId(ApiDomain::ModMenu, 1, 0x0004), ApiDomain::ModMenu, "RuntimeMods", "Reload", kV1, 0,
     ThreadAffinity::MainUpdate, ApiMaturity::Experimental},
    // `Report` 只给菜单脚本上报"走到哪一步"用（真机排障），不参与 PC 覆盖率口径。
    {MakeId(ApiDomain::ModMenu, 1, 0x0005), ApiDomain::ModMenu, "RuntimeMods", "Report", kV1, 0,
     ThreadAffinity::MainUpdate, ApiMaturity::Experimental},

    // ---- 批次 238（2026-09-30）：语料模组适配第一波 28 条（引擎方法数据行，0 字节代码）。
    // 底座 = NRO 动态符号表里的同名成员函数，逐条证据（mangled + 偏移 + 入口指纹）见
    // `runtime_constants.hpp` 的批次 238 段；形状按**符号参数表**取（不是文档的默认参数视角）。
    // 为什么是这 28 条：152 条去重缺口里，形状与接收者都现成的那一批（其余见
    // `tools/mod_corpus_scope.json` 与 `docs/改动日志-20260930.md` 的 238 条）。
    {MakeId(ApiDomain::Isaac, 1, 0x0067), ApiDomain::Isaac, "Entity", "IsBoss", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x0068), ApiDomain::Isaac, "Entity", "IsEnemy", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x0069), ApiDomain::Isaac, "Entity", "Kill", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x006A), ApiDomain::Isaac, "Entity", "Remove", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x006B), ApiDomain::Isaac, "Entity", "Update", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x006C), ApiDomain::Isaac, "EntityPlayer", "AddBrokenHearts", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x006D), ApiDomain::Isaac, "EntityPlayer", "AddCard", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x006E), ApiDomain::Isaac, "EntityPlayer", "AddEternalHearts", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x006F), ApiDomain::Isaac, "EntityPlayer", "AddHearts", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x0070), ApiDomain::Isaac, "EntityPlayer", "AddTrinket", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x0071), ApiDomain::Isaac, "EntityPlayer", "EvaluateItems", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x0072), ApiDomain::Isaac, "EntityPlayer", "GetExtraLives", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x0073), ApiDomain::Isaac, "EntityPlayer", "NeedsCharge", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x0074), ApiDomain::Isaac, "EntityPlayer", "Revive", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x0075), ApiDomain::Isaac, "EntityPlayer", "SetActiveCharge", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x0076), ApiDomain::Isaac, "EntityPlayer", "SetCard", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x0077), ApiDomain::Isaac, "EntityPlayer", "TryRemoveTrinket", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x0078), ApiDomain::Isaac, "EntityPlayer", "UseCard", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    // ---- 批次 252（2026-10-01）：`EntityPlayer:RemoveCollectible`
    // （域内序号取 0x0084 起；Isaac 域此前的最大号是 0x0083 = 批次 242 下转族最后一条）。
    // ★★ 工作清单把它记成 **`ItemPool:RemoveCollectible`**（同名、另一个 owner）——
    //   语料里的接收者是 **EntityPlayer**（`p:RemoveCollectible(id)`）⇒ 按 owner 认才对。
    //   引擎符号 4 格而语料只传 1 个 ⇒ 形状 `VoidIntBoolIntBoolOpt3`（尾部 3 个可省）。
    {MakeId(ApiDomain::Isaac, 1, 0x0084), ApiDomain::Isaac, "EntityPlayer", "RemoveCollectible", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    // ---- 批次 254（2026-10-01）：`EntityPlayer` 三条零成本数据行（域内序号取 0x0085~0x0087）。
    // ★★ 工作清单把它们记成 `needs_new_receiver`（"差接收者视图"）——**那是误判**：清单的桶
    //   来自库存工具的 `thunk_readiness=needs_owner_instance`，而那个字段只认 7 个可达类
    //   （`EntityPlayer` 不在其中）⇒ 凡是 owner 是 `Entity`/`EntityPlayer` 的都落进该桶。
    //   实际接收者（`FieldReceipt::EntityPlayer`）与形状（`Void1`/`Void0`）全都现成 ⇒ 零成本。
    {MakeId(ApiDomain::Isaac, 1, 0x0085), ApiDomain::Isaac, "EntityPlayer", "AddKeys", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x0086), ApiDomain::Isaac, "EntityPlayer", "AddGoldenKey", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x0087), ApiDomain::Isaac, "EntityPlayer", "AddGoldenBomb", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    // ---- 批次 240（2026-09-30）：`Isaac.Get*ByName` 名字表一族（语料适配第二波 C 批）。
    // 表源 `tools/isaac_name_source/*.txt`（追踪在仓库里）→
    // `tools/generate_isaac_name_tables.py` → `runtime/source/program/isaac_name_tables.*`。
    // 为什么不能"遍历引擎的 `ItemConfig` 比名字"、为什么源文件必须进仓库：见生成器文档头。
    // 域内序号取 0x0079 起（Isaac 域此前的最大号是 0x0078）。
    {MakeId(ApiDomain::Isaac, 1, 0x0079), ApiDomain::Isaac, "Isaac", "GetItemIdByName", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x007A), ApiDomain::Isaac, "Isaac", "GetCardIdByName", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x007B), ApiDomain::Isaac, "Isaac", "GetPillEffectByName", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x007C), ApiDomain::Isaac, "Isaac", "GetPlayerTypeByName", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x007D), ApiDomain::Isaac, "Isaac", "GetChallengeIdByName", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    // ---- 批次 242（2026-09-30）：**下转族** 5 条（C 批剩项）。
    // 判据 = `vptr` 精确等于 `base + <类>VtableOffset`；常量由 vtable 符号 + 0x10 得到
    // （4 条已有常量逐条复核过这条关系）。视图用**基类 `Entity` 元表**（与 `ToFamiliar` 同例）。
    // ★ 本批只做"类型闸门"：这些类自己的字段（`TearFlags`/`HitPoints`）与
    //   `EntityLaser:GetEndPoint()` 属**另外的能力**，见存档 README 的"已知欠账"。
    {MakeId(ApiDomain::Isaac, 1, 0x007F), ApiDomain::Isaac, "Entity", "ToNPC", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x0080), ApiDomain::Isaac, "Entity", "ToTear", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x0081), ApiDomain::Isaac, "Entity", "ToLaser", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x0082), ApiDomain::Isaac, "Entity", "ToEffect", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x0083), ApiDomain::Isaac, "Entity", "ToKnife", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    // ---- 批次 261（2026-10-01）：`glue_compose` 桶三条（域内序号取 max+1 = 0x0088..0x008A）。
    // ★ 它们与其余 `Isaac` 成员一样是**全局表上的函数**（模组写 `Isaac.GetChallenge()`，
    //   按 `.` 调）⇒ 栈上**没有 `self`**；真值来源与失败降级见各自的实现处注释。
    {MakeId(ApiDomain::Isaac, 1, 0x0088), ApiDomain::Isaac, "Isaac", "GetChallenge", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x0089), ApiDomain::Isaac, "Isaac", "ConsoleOutput", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x008A), ApiDomain::Isaac, "Isaac", "HasModData", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    // ---- 批次 262（2026-10-01）：`glue_compose` 桶两条（域内序号 0x008B/0x008C）。
    // ★ 两条都是**读 PC 的绑定函数反汇编**定的做法（`tools/pc_exe_binding.py`），
    //   不是照文档猜：`GetFreeNearPosition` 就是 `Room::FindFreePickupSpawnPosition(pos, step, false, false)`；
    //   `GridSpawn` 是"坐标→格下标 → 覆盖判定 → RandomU32() 取种子 → Room::SpawnGridEntity →
    //   返回那一格的 GridEntity"。实现都在 `remaining_api.cpp`。
    {MakeId(ApiDomain::Isaac, 1, 0x008B), ApiDomain::Isaac, "Isaac", "GetFreeNearPosition", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x008C), ApiDomain::Isaac, "Isaac", "GridSpawn", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    // ---- 批次 265（2026-10-02）：`Isaac.GetSoundIdByName`（域内序号 0x008D）。
    // 与 `Isaac:GetMusicIdByName`（0x005E）同一套做法：遍历 `Manager` 里那张 `vector<T>`、
    // 把每条的名字串与入参逐字节比较、命中返回**下标**（"编号 == 下标"的证据见
    // `runtime_constants.hpp` 的批次 265 段 —— 最强的一条是引擎自己的 `SoundEffects::Play` 把 id 当下标用）。
    {MakeId(ApiDomain::Isaac, 1, 0x008D), ApiDomain::Isaac, "Isaac", "GetSoundIdByName", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    // ---- 批次 268（2026-10-02）：`glue_compose` 桶最后两条（域内序号 0x008E/0x008F，取 Isaac 域 max+1）。
    // ★ `CountEntities` 的做法 = **直接转调引擎** `EntityList::CountSpawned` @ `0x7A1CC`
    //   （PC 的绑定函数 VA `0x80D0D0` 读满 4 个实参后就是一次成员调用，逐条证据在
    //   `runtime_constants.hpp` 的批次 268 段）—— 不自己遍历实体表。
    // ★ `RunCallbackWithParam` 是 `Isaac.RunCallback`（0x0005）那一族的"带过滤值"变体：
    //   `param` 是**登记时的过滤值**（不过给回调），完整签名与语义见实现处注释
    //   （契约页那一行只写了 `callbackId`，不完整；完整签名取自同源文档的另一次抓取）。
    {MakeId(ApiDomain::Isaac, 1, 0x008E), ApiDomain::Isaac, "Isaac", "CountEntities", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x008F), ApiDomain::Isaac, "Isaac", "RunCallbackWithParam", kV1,
     0, ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    // ---- 批次 269（2026-10-02）：`blocked_decision` 桶的渲染两条（域内序号 0x0090/0x0091）。
    // ★ 两条与原 `RenderScaledText`（0x0013）**共用同一份运行时默认字体**：`RenderText` 就是
    //   "同一条绘制路径、缩放传 (1,1)"；`GetTextWidth` 契约正文点名"与 RenderText 同一个字体"。
    {MakeId(ApiDomain::Isaac, 1, 0x010E), ApiDomain::Isaac, "Isaac", "GetBuiltInCallbackState", kV1, 0,
     ThreadAffinity::Any, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x010F), ApiDomain::Isaac, "Isaac", "SetBuiltInCallbackState", kV1, 0,
     ThreadAffinity::Any, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x0110), ApiDomain::Isaac, "Isaac", "AddCallback", kV1, 0,
     ThreadAffinity::Any, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x0111), ApiDomain::Isaac, "Isaac", "AddPriorityCallback", kV1, 0,
     ThreadAffinity::Any, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x0112), ApiDomain::Isaac, "Isaac", "RemoveCallback", kV1, 0,
     ThreadAffinity::Any, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x0090), ApiDomain::Isaac, "Isaac", "RenderText", kV1, 0,
     ThreadAffinity::MainRender, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x0091), ApiDomain::Isaac, "Isaac", "GetTextWidth", kV1, 0,
     ThreadAffinity::MainRender, ApiMaturity::Experimental},
    // ---- 批次 271（2026-10-02）：`needs_new_receiver` 桶头部三条（域内序号 0x92/0x93/0x94）。
    // ★ 三条的引擎符号都逐字在 dynsym 里、且**都只有一份实现**（用嵌套名解析器扫过全符号表，
    //   没有子类重写）⇒ 不需要像 `Entity:TakeDamage` 那样在基类/子类之间二选一。
    // ★ `SetColor` 的第一个参数是 `ColorMod const&` —— 与批次 267 的 `Game:SpawnParticles`
    //   **同一个结构**，本批把它抽到 `interfaces/lua/engine_color_mod.hpp`（映射只留一份）。
    {MakeId(ApiDomain::Isaac, 1, 0x0092), ApiDomain::Isaac, "Entity", "SetColor", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x0093), ApiDomain::Isaac, "Entity", "AddCharmed", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x0094), ApiDomain::Isaac, "EntityPlayer", "UseActiveItem", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    // ---- 批次 273（2026-10-02）：`needs_new_receiver` 桶里参数最简单的一批（域内序号 0x96..0x9D）。
    // ★ 选批口径：**同名方法只有一个类有**（用嵌套名解析器扫全符号表）⇒ 没有子类重写，
    //   不需要像 `Entity:TakeDamage` 那样"挑一个"。
    // ★★ **更正（批次 284，2026-10-02）**：这里原来接着写了一句
    //   「`GridEntityDoor:Open/Close` 那种**有重写**的不收」——**那句话是错的**。
    //   批次 284 用"扫全镜像 mangled 名字"（不是"dynsym 里没看见"，也不靠名字眼熟）核实：
    //   `GridEntity_Door::Open()` 与 `GridEntity_Door::Close(bool)` 在整份 `Repentance.nro` 里
    //   **各只有一条** mangled 名字 ⇒ **没有子类重写**。当初大概率是把
    //   `Entity_NPC_HornfelDoor::Open(int)` / `Close()` 看成了重写 —— 那是**另一个类**
    //   （NPC，不是 `GridEntity_Door` 的子类），只是方法名撞了。
    //   ⇒ 这两条已在**批次 284** 收下（连同 `IsTargetRoomArcade`）。
    //   ★ 教训：这条规则要按"扫全镜像"执行；靠印象说"有重写"会把能做的东西一直挡在门外。
    // ★ owner 决定挂哪张处理器表（批次 271 的教训）：`Entity` 两条挂 `kEntityHandlers`、
    //   `EntityPlayer` 六条挂 `kEntityPlayerHandlers`，两处都不能放错。
    {MakeId(ApiDomain::Isaac, 1, 0x0096), ApiDomain::Isaac, "Entity", "AddFreeze", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x0097), ApiDomain::Isaac, "EntityPlayer", "AddBlueSpider", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x0098), ApiDomain::Isaac, "EntityPlayer", "AddGoldenHearts", kV1,
     0, ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x0099), ApiDomain::Isaac, "EntityPlayer", "AddMinisaac", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x009A), ApiDomain::Isaac, "EntityPlayer", "AddPill", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x009B), ApiDomain::Isaac, "EntityPlayer", "AnimateAppear", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x009C), ApiDomain::Isaac, "EntityPlayer", "DropTrinket", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x009E), ApiDomain::Isaac, "Entity", "AddPoison", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    // ---- 批次 274（2026-10-02）：清桶批 11 条（域内序号 0x9D、0x9F、0xA0、0xA1..0xA8）。
    // ★ 选批口径与批次 273 相同（引擎里有同名方法 **且该同名方法只有一个类有**），
    //   只是把参数收到最简：**arity 0..2、参数只有标量 / `Vector` / `EntityRef`**。
    // ★ 与批次 273 一样：**owner 决定挂哪张表**（`Entity` 三条 / `EntityPlayer` 八条）。
    {MakeId(ApiDomain::Isaac, 1, 0x009D), ApiDomain::Isaac, "Entity", "AddFear", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x009F), ApiDomain::Isaac, "Entity", "AddHealth", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x00A0), ApiDomain::Isaac, "Entity", "RemoveStatusEffects", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x00A1), ApiDomain::Isaac, "EntityPlayer", "AddBoneHearts", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x00A2), ApiDomain::Isaac, "EntityPlayer", "AddFriendlyDip", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x00A3), ApiDomain::Isaac, "EntityPlayer", "AddPrettyFly", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x00A4), ApiDomain::Isaac, "EntityPlayer", "AnimateTrapdoor", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x00A5), ApiDomain::Isaac, "EntityPlayer", "CanPickSoulHearts", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x00A6), ApiDomain::Isaac, "EntityPlayer", "DonateLuck", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x00A7), ApiDomain::Isaac, "EntityPlayer", "RemoveGoldenBomb", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x00A8), ApiDomain::Isaac, "EntityPlayer", "RemoveGoldenKey", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    // ---- 批次 275（2026-10-02）：实体标志位加/清（域内序号 0xA9、0xAA）—— `needs_forensics` 桶头部。
    // ★ 这两条**不需要新偏移**：写的就是 `Entity:HasEntityFlags` 已经在用的那个 64 位标志字
    //   （`kEntityFlagsOffset`）；语义来自 `isaac-ng.exe` 两条叶绑定函数的反汇编
    //   （VA 0x4122A0 = `or [ecx+0x160],eax` / `or [ecx+0x164],eax`，VA 0x4122C0 是它的 `not`+`and` 镜像）。
    {MakeId(ApiDomain::Isaac, 1, 0x00A9), ApiDomain::Isaac, "Entity", "AddEntityFlags", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x00AA), ApiDomain::Isaac, "Entity", "ClearEntityFlags", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    // 批次 277（2026-10-02）：`Entity:GetEntityFlags`（域内序号 0xB3）—— 与上面两条**同一格**
    // （`kEntityFlagsOffset`）、同一套证据；PC 绑定 VA 0x4122E0 一次返回两个 dword ⇒ 它是 64 位值。
    {MakeId(ApiDomain::Isaac, 1, 0x00B3), ApiDomain::Isaac, "Entity", "GetEntityFlags", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    // ---- 批次 278（2026-10-02）：`EntityPlayer` 族 5 条（域内序号 0xB4..0xB8）。
    // ★ 选批的硬要求：**引擎符号的参数个数与契约页完全一致** ——
    //   有几条引擎版比 PC 版多一个尾参（`ChangePlayerType(ePlayerType, bool)` 之类），
    //   多出来的那个我们不知道怎么给（0 / false 都是猜）⇒ 那些**不收**。
    {MakeId(ApiDomain::Isaac, 1, 0x00B4), ApiDomain::Isaac, "EntityPlayer", "ThrowHeldEntity", kV1,
     0, ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x00B5), ApiDomain::Isaac, "EntityPlayer", "AddSwarmFlyOrbital",
     kV1, 0, ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x00B6), ApiDomain::Isaac, "EntityPlayer", "AddItemWisp", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x00B7), ApiDomain::Isaac, "EntityPlayer", "UsePill", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x00B8), ApiDomain::Isaac, "EntityPlayer", "AddBlueFlies", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    // ---- 批次 281（2026-10-02）：`EntityTear` **视图**的第一条方法（域内序号 0xB9）。
    // `Entity:ToTear()` 从这一批起压 `EntityTear` 元表（此前压 `Entity` ⇒ 这条方法取不到，
    // 语料 8 处报 "attempt to call a nil value"）。
    {MakeId(ApiDomain::Isaac, 1, 0x00B9), ApiDomain::Isaac, "EntityTear", "ChangeVariant", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    // ---- 批次 282（2026-10-02）：`EntityLaser` **视图**的第一条方法（域内序号 0xBA）。
    // `Entity:ToLaser()` 从这一批起压 `EntityLaser` 元表（此前压 `Entity` ⇒ 这条方法取不到，
    // 语料 6 处报 "attempt to call a nil value"）。
    // ★ 同族的 `ShootAngle` **不收**：引擎符号 7 参 vs 契约 6 参（多一个尾参 bool）
    //   ⇒ 按批次 278 立的「参数个数必须与契约页对齐」规则排除。
    // ---- 批次 325（2026-10-03）：`EntityLaser.ShootAngle(...)`（语料 8 处 / 1 个模组）----
    // PC 契约 `EntityLaser.md:146`（逐字 `static EntityLaser`）。★★ 本批推翻了批 282 的排除理由
    // （"符号 7 参 vs 契约 6 参"）：去读 PC 那条绑定（`0x8C7550`）能看到**它也收 7 个参数**
    // 并原样转发给 `Game::Spawn` ⇒ PC 与 Switch 签名一致，差的第 7 格只是 C++ 缺省值。
    // ★ 静态方法（点号直呼在类名上）⇒ 挂全局 `EntityLaser` 表；返回 `EntityLaser` 句柄。
    {MakeId(ApiDomain::Isaac, 1, 0x00DE), ApiDomain::Isaac, "EntityLaser", "ShootAngle", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x00BA), ApiDomain::Isaac, "EntityLaser", "SetActiveRotation", kV1,
     0, ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    // ---- 批次 284（2026-10-02）：`EntityPlayer` 两条 0 参布尔查询 + `GridEntityDoor` 三条（0xBB..0xBF）。
    // ★ 选批口径 = **"只有一个实现" + "参数个数与契约页相等"**，而"只有一个实现"这次是用
    //   **扫全镜像 mangled 名字**核实的（同一批用它更正了 273 留下的一句错话，见上面 273 段）。
    // ★ `GridEntityDoor` 是**新的 owner** —— 门的方法挂在门元表自己的 `__methods` 上
    //   （`AttachGridEntityDoorMethods`），回落顺序 字段 → 门自己 → `GridEntity` 基类。
    {MakeId(ApiDomain::Isaac, 1, 0x00BB), ApiDomain::Isaac, "EntityPlayer", "IsHoldingItem", kV1,
     0, ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x00BC), ApiDomain::Isaac, "EntityPlayer", "IsExtraAnimationFinished", kV1, 0, ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x00BD), ApiDomain::Isaac, "GridEntityDoor", "Open", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x00BE), ApiDomain::Isaac, "GridEntityDoor", "Close", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x00BF), ApiDomain::Isaac, "GridEntityDoor", "IsTargetRoomArcade", kV1, 0, ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    // 批次 285（2026-10-02）：`EntityNPC` 视图的第一条方法 —— `Entity:ToNPC()` 从本批起压
    // `IsaacRuntime.EntityNPC`（在此之前压基类 `Entity` 元表 ⇒ `EntityNPC` 页上的方法没地方挂）。
    // `Morph(EntityType type, int Variant, int SubType, int ChampionColorIdx)`，返回 boolean
    // （PC 契约 `tools/pc_contract_docs/EntityNPC.md:117`）。引擎符号
    // `_ZN15IsaacRepentance10Entity_NPC5MorphENS_11eEntityTypeEjji`（arity 4 = 契约 4 ✓；
    // 扫全镜像 mangled 名只有 `Entity_NPC::Morph` 与 `Entity_Pickup::Morph` 两条命中 ——
    // 两者是**兄弟类**、不是重写关系）。
    {MakeId(ApiDomain::Isaac, 1, 0x00C0), ApiDomain::Isaac, "EntityNPC", "Morph", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    // 批次 285：`EntityPickup:Morph(...)`（PC 契约 `EntityPickup.md:40`）。★ 契约里后 3 个布尔
    // 带缺省值，语料里 3 参（`ChallengeAPI/.../polaroid_negative.lua:33`）与 6 参
    // （`CyclingItemsAPI/main.lua:392`）两种写法都有 ⇒ 形状声明"尾部 3 个可省"。
    // 引擎符号 `_ZN15IsaacRepentance13Entity_Pickup5MorphENS_11eEntityTypeEjjbbb`（arity 6 = 契约 6 ✓）。
    {MakeId(ApiDomain::Isaac, 1, 0x00C1), ApiDomain::Isaac, "EntityPickup", "Morph", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    // 批次 286（2026-10-02）：`Entity:IsVulnerableEnemy()` —— **单条调用点最多**的未做项
    // （22 处 / Custom-Bossbar、Enhanced-Boss-Bars、IsaacOnTwitchReloaded、RepentancePlus）。
    // PC 契约 `tools/pc_contract_docs/Entity.md:496` 逐字 `boolean IsVulnerableEnemy ( )`。
    // ★ 引擎符号是 `_ZNK15IsaacRepentance6Entity17IsVulnerableEnemyEPS0_`（**多一个 `Entity*`**）——
    //   本批做了 PC 侧取证专项，确认那个形参在当前实现里**只在非空时才被解引用**，
    //   而 PC 的无参重载传的就是**空指针**（`x1 = 0`）⇒ 照 PC 做，形状仍用 `Bool0`。
    //   完整证据链（含 PC 包装 `0x7FAE70` 的反汇编与两版返回值等价证明）见
    //   `runtime_constants.hpp` 的批次 286 段。
    {MakeId(ApiDomain::Isaac, 1, 0x00C2), ApiDomain::Isaac, "Entity", "IsVulnerableEnemy", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    // ---- 批次 293（2026-10-03）：`Entity` 的**三个相邻状态字节**（合 32 处 / 5 个模组）。
    // 三条都**没有**引擎同名访问器（PC 侧那三个绑定本体就是 `mov al,[ecx+0x169/0x16A/0x16B]; ret`）
    // ⇒ 走 `field_row`（数据行在 `isaac_api.cpp` 的 `kFieldApis`，偏移与具名消费者证据在
    // `runtime_constants.hpp` 的批次 293 段）。owner 是 `Entity`，接收者 `FieldReceipt::Entity`
    // —— **都是既有的**，本批零新机制。
    // ★ 三条的语义各有**具名**锚点：`Entity::Render`/`EntityList::RenderShadows`（可见性）、
    //   `EntityList::Update`/`Entity::Remove`（在不在实体表里）、
    //   `Entity::Kill`（置 1，且函数体尾调用 `BloodExplode`，与契约那 sentence 对上）。
    // 契约：`tools/pc_contract_docs/Entity.md` 的 320（`Exists`）/ 466（`IsDead`）/ 491（`IsVisible`）行。
    {MakeId(ApiDomain::Isaac, 1, 0x00C9), ApiDomain::Isaac, "Entity", "IsVisible", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x00CA), ApiDomain::Isaac, "Entity", "Exists", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x00CB), ApiDomain::Isaac, "Entity", "IsDead", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    // ---- 批次 315（2026-10-03）：`Entity:Die()`（**27 处 / 4 个模组**）----
    // 上面那条 `IsDead` 的**写侧**：往同一格 `Entity + 0x1C3` 写常量 **1**
    // （`FieldKind::BoolWriteConst`，与批次 305 的 `Music:Enable/Disable` 同形：不收实参、返回 0 个值）。
    // ★★★ 本批推翻了交接 §4 的"`Entity:Die` 0 实现 ⇒ 别碰"：**"0 实现"只说明 Switch 侧没有同名函数
    //   （内联），字段本身在** —— PC 侧 `Die @ 0x436B60` 与 `IsDead @ 0x412350` **读写同一格**
    //   `+0x16B`（各两条指令，逐字核过）⇒ 这是纯字段写、不需要引擎函数。详见 `isaac_api.cpp`
    //   的数据行注释与 `runtime_constants.hpp` 的批次 293 段。
    {MakeId(ApiDomain::Isaac, 1, 0x00DA), ApiDomain::Isaac, "Entity", "Die", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    // ---- 批次 316（2026-10-03）：`Entity:GetDropRNG()`（3 处 / 2 个模组）----
    // 字段数据行：把 `Entity + 0x3D8` 那份 **16 字节 `RNG`** 读成快照、压 `kRngMetatable` 句柄
    // （本批新开的 `FieldKind::RngSnapshot`）。
    // ★★★ 偏移**不是新取的**：它就是既有的 `Entity.DropSeed` 那一格（`kEntityDropSeedOffset`）——
    //   实体基类只有这一个 RNG 成员，种子就是 RNG 对象头 4 字节 ⇒ 两者同址。
    //   PC 侧两条绑定（`DropSeed @ 0x59FD60` = `mov eax,[ecx+0x334]`、
    //   `GetDropRNG @ 0x412390` = `lea eax,[ecx+0x334]`）**指着同一格**，Switch 侧同理
    //   （构造/出生两处具名函数都拿 `this+0x3d8` 当 `RNG*` 用）。
    // ★ 与 `GridEntity:GetRNG`（`0x0E010054`）及四条 `EntityPlayer:Get*RNG` 同为"快照语义"
    //   （已登记的 `design` 偏离：PC 给的是活引用）。
    // 契约：`tools/pc_contract_docs/Entity.md:377`（`#### RNG GetDropRNG ( )`）。
    {MakeId(ApiDomain::Isaac, 1, 0x00DB), ApiDomain::Isaac, "Entity", "GetDropRNG", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    // ---- 批次 294（2026-10-03）：`GridEntityDoor:IsRoomType(RoomType)`（4 处 / 3 个模组）----
    // ★ 这一条是**手写处理器**（不是数据行）：PC 的绑定本体（`0x5B7550`）只有
    // 「实参 == 门自己的房型 **或** == 门通向的房型」两条比较，而现有字段行 kind 里
    // 没有"拿实参跟两个字段比"的形状（`BoolEquals` 比的是**行里的常量**）。
    // 两个字段我们早就有了具名证据（`GridEntity_Door::InitSubclass @ 0x385F98` 的存值序列 +
    // 写方 `SetRoomTypes(eRoomType, eRoomType) @ 0x385A78`）⇒ **不新增偏移、不调引擎函数**
    // （引擎里没有 `IsRoomType` 这个符号）。实现见 `remaining_api.cpp` 的
    // `GridEntityDoorIsRoomType`（挂在同族的 `GridEntityDoorIndex` 视图上）。
    // 契约：`tools/pc_contract_docs/GridEntityDoor.md` 的 63 行。
    {MakeId(ApiDomain::Isaac, 1, 0x00CC), ApiDomain::Isaac, "GridEntityDoor", "IsRoomType", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    // ---- 批次 296（2026-10-03）：`Entity_NPC` 的两个颜色索引 + `EntityPlayer` 的主动道具充能 ----
    // ★ 前两条是**字段读取型数据行**（`isaac_api.cpp` 的 `kFieldApis`，owner 是 `EntityNPC`，
    //   接收者 `FieldReceipt::Entity`）：PC 侧那两个绑定本体（`0x680DE0` / `0x7A7FD0`）
    //   各自只有一条 `mov eax,[ecx+0xBB4/0xBC8]; ret` ⇒ 引擎里**没有**同名访问器
    //   （`tools/mangled_impl_count.py` 各 0 个实现）⇒ 直读字段才是与 PC 等价的做法。
    //   偏移/具名消费者/语义锚点见 `runtime_constants.hpp` 的批次 296 段与布局表
    //   `tools/layout_tables/entity_npc.json`（本批新建）。降级档 `MinusOne`（PC 的 `Init` 就写 -1）。
    // ★ 第三条是**手写处理器**（`EntityPlayerGetActiveCharge`）：它要按槽位在**同一个数组**里
    //   取第 `slot` 个元素的 `+4` 格（步长 `0x1C`），现有字段行 kind 里没有"带下标"的形状
    //   （`SumU32Array` 是整段求和、`BoolBit` 的 `offset2` 是位号）⇒ 与同族的 `GetActiveItem`
    //   逐字同形地手写。它**复用**两个既有常量（`kEntityPlayerActiveItemChargeOffset` /
    //   `kEntityPlayerActiveItemStride`）⇒ 零新增偏移。
    // 契约：`tools/pc_contract_docs/EntityNPC.md` 的 69 / 77 行、`EntityPlayer.md` 的 757 行。
    {MakeId(ApiDomain::Isaac, 1, 0x00CD), ApiDomain::Isaac, "EntityNPC", "GetChampionColorIdx", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x00CE), ApiDomain::Isaac, "EntityNPC", "GetBossColorIdx", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    // ---- 批次 314（2026-10-03）：`EntityNPC:IsChampion()`（1 处 / 1 个模组）----
    // 只读字段、走 `field_row`（数据行在 `isaac_api.cpp` 的 `kFieldApis`，偏移与证据在
    // `runtime_constants.hpp` 的批次 314 段）。`FieldKind::Bool`（读一个字节、非 0 即真），
    // 接收者 `FieldReceipt::Entity`（与上面两条色号同族；NPC 句柄走的就是实体那一条链）。
    // ★★ 本批**更正了 296 的一条负结果**：PC 的真绑定是 `0x68F580` = `movb 0xbb3(%ecx),%al; ret`
    //   （一条指令，不是"两个条件"）—— `push 0x68F550` 全镜像 0 次引用，那段代码不归它。
    {MakeId(ApiDomain::Isaac, 1, 0x00D9), ApiDomain::Isaac, "EntityNPC", "IsChampion", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x00CF), ApiDomain::Isaac, "EntityPlayer", "GetActiveCharge", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    // ---- 批次 298（2026-10-03）：`GridEntity:GetSprite()`（14 处 / 1 个模组）----
    // PC 的绑定本体（`0x427440`）是 `lea eax,[ecx+0x3C]; ret`（一跳直读成员）⇒ 走**手写处理器**
    // （要交回一个 `Sprite` **句柄**，现有 field kind 都不产出句柄）。
    // ★★ Switch 侧的偏移是 `+0x48`（**与 PC 的 0x3C 不同**）：证据 = 引擎自己把 `this+0x48`
    //   交给 `ANM2::Load/Render/SetFrame`（`GridEntity_Rock` 三处 + 另 10 个子类的 `ANM2::Load`）。
    // ★ `GridEntityRock:GetSprite()`（清单里另记 14 处、**无契约页/无接收者证据**）由**同一段代码**
    //   覆盖：`ToRock()` 压的是基类 `GridEntity` 视图，而 Rock 的内嵌 ANM2 与基类同在 `+0x48`
    //   ⇒ 已登记为伪缺口（`build_api_restore_worklist.py` 的 `CONFIRMED_PSEUDO_GAPS`）。
    // 契约：`tools/pc_contract_docs/GridEntity.md` 的 53 行。
    {MakeId(ApiDomain::Isaac, 1, 0x00D0), ApiDomain::Isaac, "GridEntity", "GetSprite", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    // ---- 批次 299（2026-10-03）：`EntityPlayer:HasFullHearts()`（6 处 / 1 个模组）----
    // PC 的绑定本体（`0x6B1B40`）先用一个**按玩家类型的跳表**（助手 `0x78CDC0`）分类，
    // 再比 `[+0x1294] >= [+0x1290] (+ 2*[+0x1CA8])`。★ 那张跳表的输出集合与既有的
    // `kEntityPlayerBoneHeartlessTypeMask` **逐位相等**（本批从 PC 的 37 字节表独立解出来对照）
    // ⇒ 判据就是「当前红心 ≥ 有效最大红心」，与既有的 `GetEffectiveMaxHearts()` 同一件事
    // ⇒ **手写**处理器，复用同一份 `ReadEffectiveMaxHearts`（判据只有一份）。
    // 契约：`tools/pc_contract_docs/EntityPlayer.md` 的 1357 行。
    // 社区RepentancePlus/CHAPI的原生玩家接口。
    {MakeId(ApiDomain::Isaac, 1, 0x1040), ApiDomain::Isaac, "Entity", "AddBurn", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x1041), ApiDomain::Isaac, "Entity", "AddConfusion", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x1042), ApiDomain::Isaac, "Entity", "AddMidasFreeze", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x1043), ApiDomain::Isaac, "Entity", "AddShrink", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x1044), ApiDomain::Isaac, "Entity", "AddSlowing", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x1045), ApiDomain::Isaac, "Entity", "HasMortalDamage", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x1046), ApiDomain::Isaac, "EntityBomb", "AddTearFlags", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x1047), ApiDomain::Isaac, "EntityKnife", "AddTearFlags", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x1048), ApiDomain::Isaac, "EntityLaser", "AddTearFlags", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x1049), ApiDomain::Isaac, "EntityTear", "AddTearFlags", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x104A), ApiDomain::Isaac, "EntityBomb", "SetExplosionCountdown", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x104B), ApiDomain::Isaac, "EntityPlayer", "AddCostume", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x104C), ApiDomain::Isaac, "EntityPlayer", "AddWisp", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x104D), ApiDomain::Isaac, "EntityPlayer", "AnimateCard", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x104E), ApiDomain::Isaac, "EntityPlayer", "AnimatePickup", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x104F), ApiDomain::Isaac, "EntityPlayer", "CanPickupItem", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x1050), ApiDomain::Isaac, "EntityPlayer", "FireBomb", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x1051), ApiDomain::Isaac, "EntityPlayer", "FlushQueueItem", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x1052), ApiDomain::Isaac, "EntityPlayer", "FullCharge", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x1053), ApiDomain::Isaac, "EntityPlayer", "GetAimDirection", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x1054), ApiDomain::Isaac, "EntityPlayer", "GetMaxTrinkets", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x1055), ApiDomain::Isaac, "EntityPlayer", "GetTearMovementInheritance", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x1056), ApiDomain::Isaac, "EntityPlayer", "RemoveCostume", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x1057), ApiDomain::Isaac, "EntityPlayer", "SetPill", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x1058), ApiDomain::Isaac, "EntityPlayer", "SetPocketActiveItem", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x1059), ApiDomain::Isaac, "EntityPlayer", "ThrowBlueSpider", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x105A), ApiDomain::Isaac, "EntityPlayer", "WillPlayerRevive", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x105B), ApiDomain::Isaac, "EntityProjectile", "HasProjectileFlags", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Game, 1, 0x105C), ApiDomain::Game, "Game", "ClearStagesWithoutHeartsPicked", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Game, 1, 0x105D), ApiDomain::Game, "Game", "Fart", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Game, 1, 0x105E), ApiDomain::Game, "Game", "ShakeScreen", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x105F), ApiDomain::Isaac, "GridEntity", "SetVariant", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x1060), ApiDomain::Isaac, "GridEntityDoor", "Bar", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x1061), ApiDomain::Isaac, "PathFinder", "FindGridPath", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Room, 1, 0x1062), ApiDomain::Room, "Room", "GetAwardSeed", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},

    {MakeId(ApiDomain::Isaac, 1, 0x1020), ApiDomain::Isaac, "Color", "SetColorize", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x1021), ApiDomain::Isaac, "Color", "Lerp", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x1010), ApiDomain::Isaac, "EntityPlayer", "AddBlackHearts", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x1011), ApiDomain::Isaac, "EntityPlayer", "AddMaxHearts", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x1012), ApiDomain::Isaac, "EntityPlayer", "AddRottenHearts", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x1013), ApiDomain::Isaac, "EntityPlayer", "AddSoulHearts", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x1014), ApiDomain::Isaac, "EntityPlayer", "CanPickBlackHearts", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x1015), ApiDomain::Isaac, "EntityPlayer", "CanPickBoneHearts", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x1016), ApiDomain::Isaac, "EntityPlayer", "CanPickGoldenHearts", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x1017), ApiDomain::Isaac, "EntityPlayer", "CanPickRottenHearts", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x1018), ApiDomain::Isaac, "EntityPlayer", "GetGoldenHearts", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x1019), ApiDomain::Isaac, "EntityPlayer", "GetHeartLimit", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x101A), ApiDomain::Isaac, "EntityPlayer", "GetRottenHearts", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x101B), ApiDomain::Isaac, "EntityPlayer", "HasFullHeartsAndSoulHearts", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x101C), ApiDomain::Isaac, "EntityPlayer", "IsBlackHeart", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x101D), ApiDomain::Isaac, "EntityPlayer", "IsBoneHeart", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x101E), ApiDomain::Isaac, "EntityPlayer", "RemoveBlackHeart", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x101F), ApiDomain::Isaac, "EntityPlayer", "SetFullHearts", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},

    {MakeId(ApiDomain::Isaac, 1, 0x1008), ApiDomain::Isaac, "EntityPlayer", "GetMovementInput", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x1000), ApiDomain::Isaac, "EntityPlayer", "GetSubPlayer", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x1001), ApiDomain::Isaac, "EntityPlayer", "GetDamageCooldown", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x1002), ApiDomain::Isaac, "EntityPlayer", "SetMinDamageCooldown", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x1003), ApiDomain::Isaac, "EntityPlayer", "ResetDamageCooldown", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x1004), ApiDomain::Isaac, "EntityPlayer", "AddSoulCharge", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x1005), ApiDomain::Isaac, "EntityPlayer", "AddBloodCharge", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x1006), ApiDomain::Isaac, "EntityPlayer", "AddJarHearts", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x1007), ApiDomain::Isaac, "EntityPlayer", "GetJarHearts", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x00D1), ApiDomain::Isaac, "EntityPlayer", "HasFullHearts", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    // ---- 批次 301（2026-10-03）：`EntityPlayer:AddCacheFlags(CacheFlag)`（34 处 / 4 个模组）----
    // PC 的绑定本体（`0x427800`）只有两句：`mov eax,[ebp+0x8]` + `or dword ptr [ecx+0x14b8], eax`
    // ⇒ 「把参数那段掩码并进玩家的 `_cacheFlags`」。★ 那是一个**有参数、有副作用、不返回值**的
    // 字段写，既有 kind 都覆盖不了（`BoolBitWrite` 只动一位、`BoolBitArrayOfWriteArg` 的实参是
    // 位号而不是掩码）⇒ 本批新增 `FieldKind::U32OrWithArg`（读改写：`字段 |= 实参`，返回 0 个值）。
    // 数据行在 `isaac_api.cpp` 的 `kFieldApis`（`Entity_Player + 0x1958`，**0 字节代码**）；
    // 偏移的两侧对应与取值锚点见 `runtime_constants.hpp` 的批次 301 段。
    // ★ 同一批还发 `CacheFlag` 这张**全局枚举表**（模组写 `CacheFlag.CACHE_DAMAGE`）——
    //   "API + 枚举表常常是同一件事的两半"（批 269/292/297 的先例）：表不发，`CacheFlag.X`
    //   本身就是 nil ⇒ 方法在也照样抛错。
    // 契约：`tools/pc_contract_docs/EntityPlayer.md` 的 108/109 行。
    {MakeId(ApiDomain::Isaac, 1, 0x00D2), ApiDomain::Isaac, "EntityPlayer", "AddCacheFlags", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    // ---- 批次 303（2026-10-03）：**"按 vtable 槽号调用"的第一批** —— `CanShutDoors()` ----
    // `Entity:CanShutDoors()` / `EntityNPC:CanShutDoors()`（各 3 处 = 6 处，都来自 1 个模组）。
    // ★★ 这两条是**虚函数**：PC 的绑定本体是 `mov eax,[ecx]; jmp [eax+0x44]`（PC 镜像里
    //   `0x8604E0` 起是一整张这样的跳板表），调哪一个实现**取决于接收者的动态类型**
    //   ⇒ 既有的"模块基址 + 固定偏移 + 入口指纹"那套**做不了**（直调基类会跳过子类行为）。
    //   ⇒ 本批给引擎方法行加了一条新约定：`offset` 最高位置 1 = "按 vtable 槽号调用"、
    //     低 31 位 = 槽号（见 `engine_method_api.hpp` 的 `kEngineVtableRowFlag`）。
    // ★ 槽号从 **Switch 的 `_ZTV`** 读（`Entity`/`Entity_NPC` 的 `CanShutDoors` 都在槽 **18**），
    //   **不许照抄 PC 的 17** —— 两边差一个析构槽（取证见 `runtime_constants.hpp` 的批次 303 段）。
    // ★ 这种行**没有入口指纹**，护栏换成"vptr 与目标两级指针都要可读且非 0 + 槽号有上界"，
    //   失败记 `EngineRowRejectReason::Vtable`（新增的第 5 类拒绝原因）。
    // 契约：`tools/pc_contract_docs/Entity.md` 的 88 行 / `EntityNPC.md` 的同一语义行。
    {MakeId(ApiDomain::Isaac, 1, 0x00D3), ApiDomain::Isaac, "Entity", "CanShutDoors", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x00D4), ApiDomain::Isaac, "EntityNPC", "CanShutDoors", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    // ---- 批次 324（2026-10-03）：`EntityNPC.ThrowSpider(...)`（语料 3 处 / 2 个模组）----
    // PC 契约 `EntityNPC.md:165`（逐字 `#### static const EntityNPC ThrowSpider ( Vector Position,
    // Entity Spawner, Vector TargetPos, boolean Big, float YOffset )`）。
    // ★★★ 本项目**第一条静态调用**：PC 的写法是 `EntityNPC.ThrowSpider(...)`（点号直呼在**类名**上）
    //   ⇒ 挂在**全局 `EntityNPC` 表**上，不是元表（见 `AttachEntityNPCStatics`）。
    //   ★ 引擎符号 5 参、契约 5 参 **逐字对得上**，没有 `this`；实参映射见 `runtime_constants.hpp`
    //   的批次 324 段（`x0`/`x1`/`x2`/`w3` + `s0`）。
    // ★ 返回 `EntityNPC` 句柄 ⇒ 同批新加的 `EngineReturnKind::EntityNpc`（空指针压 `nil`）。
    {MakeId(ApiDomain::Isaac, 1, 0x00DD), ApiDomain::Isaac, "EntityNPC", "ThrowSpider", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    // ---- 批次 304（2026-10-03）：`GridEntity` 的两条**虚函数**（共 7 处）----
    // `GridEntity:Destroy(boolean Immediate)`（5 处）与 `GridEntity:PostInit()`（2 处）——
    // 与 303 那两条同机制（"按 vtable 槽号调用"），槽号从 **Switch 的 `_ZTVGridEntity`** 读：
    // `Destroy` = **槽 6**、`PostInit` = **槽 2**（`offset` 最高位置 1、低 31 位是槽号）。
    // ★★ 为什么**不能**直调基类：`GridEntity_Door`/`_Rock`/`_Statue`/`_TNT`/`_Web` 都有自己的
    //   `Destroy` —— 直调 `GridEntity::Destroy` 会**跳过子类行为**（石头炸掉不喷掉落物）。
    // ★ 接收者是新开的 `FieldReceipt::GridEntity`（栈上那个句柄，`Room:GetGridEntity(i)` 交回的
    //   就是它）；存活判据与手写路径**同一份**（`IsLiveGridEntityPointer`）。
    // ★ `Destroy` 的实参**可以省略**（语料里 `Destroy()` 与 `Destroy(true)` 都有）⇒ 形状 `BoolOpt1`。
    // 契约：`tools/pc_contract_docs/GridEntity.md` 的 21/23（`Destroy`）与 81/83（`PostInit`）行。
    {MakeId(ApiDomain::Isaac, 1, 0x00D5), ApiDomain::Isaac, "GridEntity", "Destroy", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x00D6), ApiDomain::Isaac, "GridEntity", "PostInit", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    // ---- 批次 321（2026-10-03）：`GridEntity:Update()`（语料 1 处）----
    // PC 契约 `GridEntity.md:152`（`#### void Update ( )`）。走**按 vtable 槽号虚调用**（批 303 立的约定）。
    // ★★★ 槽号 **3**，证据比批 304 那两条还硬：**基类 `_ZTVGridEntity` 的槽 3 就是 `__cxa_pure_virtual`**
    //   （纯虚），而每一个派生类都在槽 3 放自己的 `Update` ⇒ 「基类纯虚 + 派生类逐类覆盖」
    //   正是虚函数的定义，而且**不可能**"落到基类"（基类那份不可调用）。
    // ★ PC 侧同一条规律：跳板表 `0x860507` = `mov eax,[ecx]; jmp [eax+0x8]` ⇒ PC 序号 2 ⇒ Switch 槽 3
    //   （`PC 序号 = Switch 槽号 − 1`；名表里另一条 `Update` 指向 `0x860520` = `Entity::Update` 的槽 4，别混）。
    // ★ 接收者沿用批 304 的 `FieldReceipt::GridEntity`、形状沿用 `Void0` ⇒ **零新机制**。
    {MakeId(ApiDomain::Isaac, 1, 0x00DC), ApiDomain::Isaac, "GridEntity", "Update", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    // ---- 批次 308（2026-10-03）：`GridEntity:SetType(eGridEntityType)`（语料 1 处）----
    // PC 契约 `GridEntity.md:91/93`（`#### void SetType ( [GridEntityType](enums/GridEntityType.md)
    // Type )`）。★ 语料：`BOIStageAPI15/.../roomHandler.lua:1316` 把一块石头改成**金石头** ——
    //   `rockToConvert:SetType(GridEntityType.GRID_ROCK_GOLD)` **紧跟** `:Init(seed)`
    //   （`Init` 我们已有，批次 272）⇒ 金色是 `Init` 重跑子类初始化带来的，两条要一起用。
    // ★ PC 的绑定本体（`0x6DAD50`）只有两条指令、**不调引擎函数** ⇒ 这是一次**字段写**，
    //   走数据行（`FieldKind::U32FromArg`，本批新立）⇒ **0 字节代码**。
    // ★ 写的是 `GridEntity + kGridEntityTypeOffset`（`+0x08`）—— 与 `GridEntity:GetType()`
    //   读的是**同一格** ⇒ "写进去再读回来"是真的往返判据。取证（`Room::CreateGridEntity`
    //   写 `+0x08`、`GridEntity::IsRock` 读 `+0x08`）见 `remaining_api.cpp` 的
    //   `kGridEntityFieldApis` 段注释与 `runtime_constants.hpp` 的 `kGridEntityTypeOffset` 段。
    {MakeId(ApiDomain::Isaac, 1, 0x00D7), ApiDomain::Isaac, "GridEntity", "SetType", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    // ---- 批次 312（2026-10-03）：`EntityPlayer:IsCoopGhost()`（1 处 / 1 个模组）----
    // 只读字段、走 `field_row`（数据行在 `isaac_api.cpp` 的 `kFieldApis`，偏移与四条具名证据在
    // `runtime_constants.hpp` 的批次 312 段）。`FieldKind::Bool`（读一个字节、非 0 即真）
    // 与 PC 绑定 `0x6C4AF0 mov al,[ecx+0x1f88]` 逐字对应；接收者 `FieldReceipt::EntityPlayer`。
    {MakeId(ApiDomain::Isaac, 1, 0x00D8), ApiDomain::Isaac, "EntityPlayer", "IsCoopGhost", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    // 批次 287（2026-10-02）：`EntityPlayer` 的"心数 / 金色钥匙"三条（只读字段，共 13 处 / 3 个模组）。
    // 三条都**没有**引擎同名函数（`tools/mangled_impl_count.py` 各得 0 个实现）⇒ 走 `field_row`
    // （数据行在 `isaac_api.cpp` 的 `kFieldApis`，偏移与三方对应证据在 `runtime_constants.hpp`
    // 的批次 287 段）。owner 是 `EntityPlayer`，接收者 `FieldReceipt::EntityPlayer`。
    {MakeId(ApiDomain::Isaac, 1, 0x00C3), ApiDomain::Isaac, "EntityPlayer", "GetBoneHearts", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x00C4), ApiDomain::Isaac, "EntityPlayer", "GetEternalHearts", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x00C5), ApiDomain::Isaac, "EntityPlayer", "HasGoldenKey", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    // ---- 批次 288（2026-10-02）：`EntityPlayer` 的方向三条 ----
    // 前两条走字段读取型数据行（`Entity_Player+0x19FC` / `+0x1A00`，各 0 字节代码），
    // 第三条走引擎方法数据行（`Entity::get_movement_direction() const` @ `0x5C8AC`，同样 0 字节代码）。
    // 逐条证据在 `runtime_constants.hpp` 的"批次 288"段。
    {MakeId(ApiDomain::Isaac, 1, 0x00C6), ApiDomain::Isaac, "EntityPlayer", "GetHeadDirection", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x00C7), ApiDomain::Isaac, "EntityPlayer", "GetFireDirection", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    // ---- 批次 326（2026-10-03）：`EntityPlayer:FireTechLaser(...)`（语料 1 处）----
    // PC 契约 `EntityPlayer.md:728`。符号 7 参 = 契约 7 参（无"契约少写"问题）；
    // ★ 它是**第一次用到 `EngineArgKind::FloatDefaultOne`** 的 API —— 契约里
    //   `DamageMultiplier 的缺省是 1`（不是 0），那种缺省原来的机制表达不了（只能填 0）。
    {MakeId(ApiDomain::Isaac, 1, 0x00DF), ApiDomain::Isaac, "EntityPlayer", "FireTechLaser", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x00C8), ApiDomain::Isaac, "EntityPlayer", "GetMovementDirection", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    // ---- 批次 328（2026-10-03）：`EntityPlayer:GetShootingInput()` / `GetShootingJoystick()`
    //      （语料合 16 处：14 + 2，是清单里最大的一块）----
    // PC 契约 `EntityPlayer.md:1235`（`#### [Vector] GetShootingInput ( )` —— "Returns a vector
    // that corresponds to the shooting inputs that this player is **pressing**."）与 :1245
    // （`GetShootingJoystick` —— "…**holding**. See the image for the [GetShootingInput] method."）。
    // ★★ **两条在 PC 上共用同一份实现**：两个名字表项指向同一个 VA `0x741B00`
    //   （`tools/pc_exe_binding.py` 各跑一次即可复现）⇒ 我们同样只接**一个**引擎函数。
    // ★ 引擎里**没有** `GetShootingInput` 这个名字（按 Lua 名查是 `no_symbol`），真身是
    //   **snake_case** 的 `_ZN15IsaacRepentance13Entity_Player18get_shooting_inputEv @ 0x2B0FFC`
    //   （入口首 4 字节 `0xD10143FF`）—— 函数体做事见 `runtime_constants.hpp` 的批次 328 段。
    // ★ 返回 `Vector`（两个 `float` 的 HFA，走 `s0`/`s1`）⇒ **通用跳板只回填 `x0`/`d0`、表达不了**
    //   ⇒ 照 `Room:GetCenterPos()` 的先例**手写处理器**（不是数据行）。
    {MakeId(ApiDomain::Isaac, 1, 0x00E0), ApiDomain::Isaac, "EntityPlayer", "GetShootingInput", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x00E1), ApiDomain::Isaac, "EntityPlayer", "GetShootingJoystick", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    // ---- 批次 330（2026-10-03）：`EntityFamiliar:FollowParent()` / `AddToFollowers()`
    //      （语料合 5 处：2 + 3）----
    // PC 契约 `EntityFamiliar.md:65` / `:47`（两条都是 `#### void X ( )` —— 无参、返回 `void`）。
    // ★★ 本批的产出其实是**视图**：`Entity:ToFamiliar()` 此前压的是**基类 `Entity` 元表**
    //   ⇒ `EntityFamiliar` 页上的方法没有地方挂，模组调用报 "attempt to call a nil value"、
    //   整条回调被摘。本批照批次 285 给 `EntityNPC` 立的那套接线建 `kEntityFamiliarMetatable`
    //   （六处：元表 / `EntityView::Familiar` / `EntityViewMetatable` 分支 / `EntityFamiliarIndex` /
    //   `CheckEntityHandle` 认它 / `ToFamiliar()` 改压它），字段仍回落到 `Entity`。
    // ★ 引擎里**没有**这两个驼峰名（按 Lua 名查是 `no_symbol`），真身是 **snake_case** 的
    //   `Entity_Familiar::follow_parent` @ `0xAEC14` 与 `add_to_followers` @ `0xAC958`
    //   （入口首 4 字节 `0xD10243FF` / `0xD10143FF`）；PC 侧两条绑定本体都是**算法** ⇒
    //   判法四档第 ② 档。★ 连"两个名字有没有接反"都逐条对照过函数体（见 `runtime_constants.hpp`）。
    // ★ 接收者 = **本批新开的** `FieldReceipt::EntityFamiliar`（精确 vptr + 类型）——
    //   `follow_parent()` 一进去就解引用 `[this+0xf50]`，拿错类的对象当 `this` 会**野读**。
    {MakeId(ApiDomain::Isaac, 1, 0x00E2), ApiDomain::Isaac, "EntityFamiliar", "FollowParent", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x00E3), ApiDomain::Isaac, "EntityFamiliar", "AddToFollowers", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    // ---- 批次 332（2026-10-03）：`EntityPlayer:GetMovementJoystick()`（语料 4 处）----
    // PC 契约 `EntityPlayer.md:1106`（`#### [Vector](Vector.md) GetMovementJoystick ( )` —— 无参返回 Vector）。
    // ★★ PC 侧 `GetMovementInput`(:1100) 与 `GetMovementJoystick`(:1106) **共用同一个绑定 VA `0x741880`**
    //   ⇒ 两条是同一份实现；本批只接语料用到的那一条。
    // ★★★ 引擎里那个函数叫 **`get_movement_input`**（**`joystick` vs `input`**，名字不同名！）
    //   ⇒ 符号表按 Lua 名查不到、329 的归一化兜底也搜不到 ⇒ **只能靠函数体定案**：
    //   PC 绑定与 Switch `0x2B0D9C` 的七条检查 + 动作号 `0x0b`(11) + 两条分支做法全部一一对应
    //   （对照表在 `runtime_constants.hpp` 的批次 332 段）。
    // ★ 返回 `Vector`（HFA ⇒ `s0`/`s1`）⇒ 与 328 一样走**手写处理器**（复用 `EngineVector2Abi`）。
    {MakeId(ApiDomain::Isaac, 1, 0x00E4), ApiDomain::Isaac, "EntityPlayer", "GetMovementJoystick", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    // ---- 批次 333（2026-10-03）：`Entity:MultiplyFriction(float Value)`（语料 1 处）----
    // PC 契约 `Entity.md:510`（只有签名、没有散文）。PC 绑定本体 `0x5951D0` 是
    // `字段 *= 实参`（读改写一个 float）⇒ **字段数据行**，走**本批新开**的
    // `FieldKind::FloatMultiplyArg`（第一条"浮点读改写"；既有 kind 都是整数/位/字节）。
    // ★ 那一格 = `Entity + 0x340`（**本帧的工作摩擦**）—— 旁边 `+0x33C` 是原值，
    //   定案的四条证据（含"语料每帧调用"这一条）见 `runtime_constants.hpp` 批次 333 段
    //   与布局表 `tools/layout_tables/entity.json` 的 `Friction` 行。
    // ★ 新开一种 `FieldKind` 的代价 ≈ `.text` **+0x40**（316 校准）—— 比手写一条（≈190~490 字节）便宜，
    //   而且"浮点读改写"这类以后还会有（本批只 1 处也划算）。
    {MakeId(ApiDomain::Isaac, 1, 0x00E5), ApiDomain::Isaac, "Entity", "MultiplyFriction", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    // ---- 批次 334（2026-10-03）：`EntityPlayer:CheckFamiliar(...)`（语料 **3 处**）----
    // PC 契约 `tools/pc_contract_docs/EntityPlayer.md:591`：
    // `void CheckFamiliar(FamiliarVariant, int TargetCount, RNG rng, ItemConfigItem = nil, int = -1)`
    // —— 5 个形参、**后两个带非 0 缺省值**。引擎符号（snake_case）逐字存在
    // `Entity_Player::check_familiar(unsigned int, int, RNG&, ItemConfig::Item const*, int)`
    // @ `0x29AD94`（入口首 4 字节 `0xD10243FF`）。
    // ★★★ 走**手写处理器**：数据行那条路要两种**新表达能力**（RNG 引用、缺省 `-1` 的整数），
    //   各 ≈ `+0x480` 字节，而手写 ≈ 300 字节 ⇒ 手写更省（账目与反汇编证据见
    //   `runtime_constants.hpp` 批次 334 段）。★ 形状表**零增长**。
    {MakeId(ApiDomain::Isaac, 1, 0x00E6), ApiDomain::Isaac, "EntityPlayer", "CheckFamiliar", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    // ---- 批次 335（2026-10-03）：交接第八份 §3「批 A」的两条（取号 = Isaac 域接着的两个空号 0x00E7 / 0x00E8）----
    // 两条共用**本批新开的一种形状** `EngineCallShape::VoidIntBoolOpt1`
    // （`void(this, i32, bool)`、尾部 1 个可省 ⇒ **一行 16 字节只读描述符、0 字节代码**）；
    // 契约各写 1 个形参、引擎符号都是 2 格 ⇒ 按符号取（G3 口径），省略那一格保持 0 = PC 缺省。
    // ★ `ChangePlayerType(PlayerType)` —— 契约 `EntityPlayer.md:581`，语料
    //   `RepentancePlus/RepentancePlus/main.lua:1008`（只传 1 个）。那个 `bool` 对语料**惰性**
    //   （分支要求 `PlayerType ∈ {16,17}`，语料传 `PLAYER_EVE`(5)）⇒ 取 0 安全，见批次 335 段。
    {MakeId(ApiDomain::Isaac, 1, 0x00E7), ApiDomain::Isaac, "EntityPlayer", "ChangePlayerType", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    // ★ `DischargeActiveItem(ActiveSlot = SLOT_PRIMARY)` —— 契约 `EntityPlayer.md:642/644`
    //   （「把主动道具充能置 0、但不触发它的效果」），语料
    //   `RepentancePlus/RepentancePlus/main.lua:2249`（只传 1 个）。
    //   ★ 与上一条不同：这条的 `bool` **确实参与分支**（`0x2B9C54` 的 `tbnz w27,#0x0`）
    //   ⇒ 取 0 走的是"契约只暴露 1 个形参 + vanilla 缺省一律是 0"这条口径，
    //   已登记真机项（作业单第九节）——若 PC 那一格不是 0，这一行单独改。
    {MakeId(ApiDomain::Isaac, 1, 0x00E8), ApiDomain::Isaac, "EntityPlayer", "DischargeActiveItem", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    // ---- 批次 336（2026-10-03 深夜）：`Entity:CollidesWithGrid()`（1 处；取号 = Isaac 域下一个空号 0x00E9）----
    // PC 契约 `Entity.md` 的 `CollidesWithGrid` 行：`#### boolean CollidesWithGrid ( )`。
    // PC 绑定本体 `0x641420` = `mov al,[ecx+0x188]; ret`（**纯读一个字节**）
    // ⇒ 只读字段、走 `field_row`（数据行在 `isaac_api.cpp` 的 `kFieldApis`，
    //   偏移 `Entity+0x1EC`，`FieldKind::Bool`，**0 字节代码**）。
    // ★ 定案证据（`Entity::Init` 清零 / `Entity::CollideWithGrid` 与 `PlayerCollideWithGrid`
    //   "整趟前清 0 + 各分支置 1" / 读者是 `Entity::Update` 一族）见 `runtime_constants.hpp`
    //   的批次 336 段；布局表是 `entity.json` 的 `CollidesWithGrid` 行（`confirmed`）。
    {MakeId(ApiDomain::Isaac, 1, 0x00E9), ApiDomain::Isaac, "Entity", "CollidesWithGrid", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    // ---- 批次 337（2026-10-04 凌晨）：`EntityPlayer:FireTear(...)`（**4 处** / 3 个模组；
    //      取号 = Isaac 域下一个空号 0x00EA）----
    // PC 契约 `EntityPlayer.md:720`（7 个形参、后 5 个带缺省；★ 其中**两个缺省是 `true`**）。
    // ★★ 走**手写处理器**：引擎真身 `Entity_Player::FireTear` @ `0x2A991C`（符号逐字存在）
    //   只收 5 格（三个布尔被打包成一个 `u32` 位掩码，`Velocity` 是**按值**的 HFA），
    //   而数据行那条路缺这两种表达能力（每新开一种 ≈ `+0x480`，两种 ≈ `+0x900`；手写 ≈ 300 字节）
    //   ⇒ 手写更省（与 328/332/334 同一笔账）。
    // 语料 4 处全在 `IsaacOnTwitchReloaded/scripts/events.lua`（`:900` / `:938` / `:1168` / `:2377`），
    // 全是 **5 参**写法（`p:FireTear(pos, vel, false, false, false)`）⇒ 后两个走缺省。
    {MakeId(ApiDomain::Isaac, 1, 0x00EA), ApiDomain::Isaac, "EntityPlayer", "FireTear", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    // ---- 批次 339（2026-10-04）：`EntityFamiliar:FireProjectile(Vector Dir)`（1 处；取号 0x00EB）----
    // PC 契约 `EntityFamiliar.md:57/59`：`EntityTear FireProjectile ( Vector Dir )`，散文还写明
    // 「**This function will not play the shoot animation of the familiar.**」。
    // ★★ 走**手写处理器**：引擎真身 `Entity_Familiar::fire_projectiles(Vector2 const&, bool)` @ `0xB06FC`
    //   **逐字存在**（另一个吃 `eDirection` 的重载在 `0xB06B8`，不是契约要的那个）⇒ 转发即可；
    //   契约只 1 个形参、引擎多一个隐藏 `bool` ⇒ 按散文与引擎自身调用点取 `false`（证据见
    //   `runtime_constants.hpp` 批次 339 段）。与 334/337 同一笔账。
    {MakeId(ApiDomain::Isaac, 1, 0x00EB), ApiDomain::Isaac, "EntityFamiliar", "FireProjectile", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    // ---- 批次 340（2026-10-04）：`Game:Spawn(...)`（取号 Game 域 0x0017）----
    // PC 契约 `Game.md:520`：`Entity Spawn ( EntityType Type, int Variant, Vector Position,
    // Vector Velocity, Entity Spawner, int SubType, int Seed )` —— **7 个形参都无缺省**。
    // ★★ 走**手写处理器**（不是数据行）：引擎 `Game::SpawnEx` @ `0x3540D0` 的第 8 个形参
    //   **走栈**（`ldr w8,[x29,#0x60]`），通用跳板填不了栈 ⇒ 手写。前 7 格与契约**逐格同序**。
    // 语料：`BOIStageAPI15/.../taintedkeepercoins.lua:63`、`TBOI_Better-Voiding/.../main.lua:154` 等。
    {MakeId(ApiDomain::Game, 1, 0x0017), ApiDomain::Game, "Game", "Spawn", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    // ---- 批次 340（2026-10-04）：`Isaac.Spawn(...)`（取号 = Isaac 域下一个空号 0x00EC）----
    // PC 契约 `Isaac.md:621`：`Entity Spawn ( EntityType entityType, int entityVariant,
    // int entitySubtype, Vector position, Vector velocity, Entity Spawner )` —— **6 个形参**。
    // ★★ 与 `Game:Spawn` **不是同一份形参序**（`subtype` 在第 3 位、引擎在第 6 位）⇒ 手写转发时
    //    要挪位；且契约明文要求**随机种子**（并警告种子 0 会崩）⇒ 现取 `RandomU32()`、为 0 兜底成 1。
    {MakeId(ApiDomain::Isaac, 1, 0x00EC), ApiDomain::Isaac, "Isaac", "Spawn", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    // ---- 批次 341（2026-10-04）：四条（Isaac 域取号 0x00ED / 0x00EE / 0x00EF / 0x00F0）----
    // 三条是 `field_row` 或 `engine_call` 的数据行，一条是新形状的引擎方法行 —— 全部来自
    // 四份并行取证报告（`docs/取证-C组-三条字段-20261004.md` / `docs/取证-D组-杂项八条-20261004.md`）。
    // `Entity:IsInvincible()`（2 处）：纯读 `Entity + 0x384` 一个字节的**字段行**（`FieldKind::Bool`）。
    {MakeId(ApiDomain::Isaac, 1, 0x00ED), ApiDomain::Isaac, "Entity", "IsInvincible", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    // `EntityLaser:SetMaxDistance(float)`（1 处）：把实参**赋值**给 `Entity_Laser + 0x4F8` 的字段行
    // （新 kind `FloatFromArg`）。
    {MakeId(ApiDomain::Isaac, 1, 0x00EE), ApiDomain::Isaac, "EntityLaser", "SetMaxDistance", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    // `EntityPlayer:TryRemoveTrinketCostume(TrinketType)`（1 处）：转发到同族 `TryRemoveCostume(eTrinketType)`
    // @ `0x2A25B0` 的**引擎方法行**（形状 `Void1`）。
    {MakeId(ApiDomain::Isaac, 1, 0x00EF), ApiDomain::Isaac, "EntityPlayer", "TryRemoveTrinketCostume", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    // `EntityFamiliar:FollowPosition(Vector Pos)`（1 处）：转发到 `follow_position(Vector2 const&)`
    // @ `0xAFCC0` 的**引擎方法行**（新形状 `VoidVector2Ref`）。★★ 本条**推翻批次 331 的负结果**。
    {MakeId(ApiDomain::Isaac, 1, 0x00F0), ApiDomain::Isaac, "EntityFamiliar", "FollowPosition", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    // ---- 批次 342（2026-10-04）：三条（Isaac 域取号 0x00F1 / 0x00F2；Game 域取号 0x0018）----
    // `GridEntity:GetSaveState()`（1 处）：PC 是**指针 getter**（`lea eax,[ecx+0x4]` ⇒ 返回 `&desc`），
    // 契约正文（`GridEntity.md:49`）逐字说明它与属性 `Desc` 返回**同一个对象** ⇒ 与 `GridEntity:Desc`
    // **共用**同一份表构造（`PushGridEntityDescTable`），不调引擎、不引新偏移。
    {MakeId(ApiDomain::Isaac, 1, 0x00F1), ApiDomain::Isaac, "GridEntity", "GetSaveState", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    // `EntityPlayer:StopExtraAnimation()`（1 处）：把 `Entity_Player + 0x1710` / `+0x1712` 两格各清 0
    // 的字段行（新 kind `TwoByteConstZero`）。PC 绑定 `0x57B1D0`；两格相隔 2、中间那格 **不许碰**。
    {MakeId(ApiDomain::Isaac, 1, 0x00F2), ApiDomain::Isaac, "EntityPlayer", "StopExtraAnimation", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    // `Game:Darken(float Darkness, int Timeout)`（1 处）：写 `Game + 0x24F9C0`(float) 与
    // `Game + 0x24F9B8`(int) 的字段行（新 kind `FloatThenIntFromArgs`）。PC 绑定 `0x432F60`。
    {MakeId(ApiDomain::Game, 1, 0x0018), ApiDomain::Game, "Game", "Darken", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    // ---- 批次 343（2026-10-04）：三条（Isaac 域取号 0x00F3 / 0x00F4 / 0x00F5）----
    // `Entity:GetColor()`（**4 处** / 3 个模组）：读 `Entity + 0x138` 起 44 字节 `ColorMod`、
    // 压 Lua `Color` 句柄的字段行（新 kind `ColorModRead`）。PC 绑定 `0x4F3DE0` =
    // `lea eax,[ecx+0xE4]; ret` ⇒ **按值返回**当前/生效色。★★ 极易与 `+0x220`（`Entity.Color`
    // 属性那一格）取错 ⇒ 用例把三格摆成互不相同的值来钉。
    {MakeId(ApiDomain::Isaac, 1, 0x00F3), ApiDomain::Isaac, "Entity", "GetColor", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    // `ItemConfig:GetCollectibles()`（1 处）：压一张 `{Size, Get}` 表（引擎向量
    // `ItemConfig + 0x00 / +0x08`）。★ PC 返回的是 **userdata**（文档自己说 `Get()` 是 bug、
    // 例子只用 `.Size`）⇒ 语料只依赖 `.Size`；这一点与"`#` 不受支持"一起写在台账的边界栏里。
    // 2026-10-09更正：已替换为实时const userdata，支持Size/:Get/#，历史说明保留。
    {MakeId(ApiDomain::Isaac, 1, 0x00F4), ApiDomain::Isaac, "ItemConfig", "GetCollectibles", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    // `ItemConfig:GetTrinkets()`（1 处）：同上，向量在 `ItemConfig + 0x18 / +0x20`。
    {MakeId(ApiDomain::Isaac, 1, 0x00F5), ApiDomain::Isaac, "ItemConfig", "GetTrinkets", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    // ---- 批次 344（2026-10-04）：两条（Isaac 域取号 0x00F6 / 0x00F7）----
    // `EntityPlayer:AnimateCollectible(CollectibleType, AnimName?, SpriteAnimName?)`（**2 处**）：
    // **手写**处理器。引擎真身是**改名**后的
    // `Entity_Player::AnimatePickup(eCollectibleType, char const*, char const*) @ 0x2DD150`
    // （入口字 `0xD10743FF`）—— 同族 5 条重载，只有这一条第 1 格是 `eCollectibleType`。
    // ★★ 缺省的两个字符串**必须传字面串** `"Pickup"` / `"PlayerPickupSparkle"`：引擎把它们喂
    // `ANM2::Play`，那里对名字做 `strcmp`、对 null 无检查 ⇒ 传 nullptr 会当场崩。
    {MakeId(ApiDomain::Isaac, 1, 0x00F6), ApiDomain::Isaac, "EntityPlayer", "AnimateCollectible",
     kV1, 0, ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    // `PathFinder:HasPathToPos(Vector Pos, boolean IgnorePoop)`（1 处）：**引擎方法数据行**，
    // 真身 `NPCAI_Pathfinder::HasPathToPos(Vector2 const&, bool) const @ 0x42F6CC`（入口字
    // `0xA9BA7BFD`）。★ 本批新开：`FieldReceipt::PathFinder`（严格校验句柄类型）+ 形状
    // `BoolVector2RefBool`（纯数据、0 代码）+ `PathFinder` 视图 + `EntityNPC.Pathfinder` 属性入口。
    // 契约页 `PathFinder.md` 本批逐字节 vendor 进 `tools/pc_contract_docs/`。
    {MakeId(ApiDomain::Isaac, 1, 0x00F7), ApiDomain::Isaac, "PathFinder", "HasPathToPos", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    // ---- 批次 388（2026-10-07）：`TemporaryEffects`（`EntityPlayer:GetEffects()` 的返回值）17 条 ----
    // 理由：此前 `GetEffects()` 恒返回空表 ⇒ 模组 `player:GetEffects():HasCollectibleEffect(id)`
    // 等于在空表上取方法 ⇒ 抛 `attempt to call a nil value` ⇒ **整条回调被派发器静默摘掉**
    //（minimapi 的小地图画不出来就是这么来的；EID `features/eid_itemprediction.lua:540` 同写法）。
    // ★ 域仍是 `Isaac`（照 `PathFinder` 的先例：**返回对象不新开域**，只新增 owner 字符串）；
    //   owner = `"TemporaryEffects"`。引擎真身 / 容器偏移 / 证据链见 `runtime_constants.hpp` 的
    //   TemporaryEffects 段；实现见 `isaac_api.cpp`；契约 = `analysis/isaacdocs-snapshot/docs/TemporaryEffects.md`
    //   （本机没有 `tools/pc_contract_docs/TemporaryEffects.md`，完成定义里按"文档里没有"口径交代）。
    // 分工：6 条无可选参数的走**引擎方法数据行**（0x00FA..0x00FF）；6 条 Add*/Remove* **手写**
    //（PC 缺省 true/1）；5 条引擎侧形状未齐的先做**不抛错占位**（0x0100..0x010A，逐条见 `api_deviation.cpp`）。
    {MakeId(ApiDomain::Isaac, 1, 0x00FA), ApiDomain::Isaac, "TemporaryEffects",
     "HasCollectibleEffect", kV1, 0, ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x00FB), ApiDomain::Isaac, "TemporaryEffects", "HasTrinketEffect",
     kV1, 0, ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x00FC), ApiDomain::Isaac, "TemporaryEffects", "HasNullEffect", kV1,
     0, ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x00FD), ApiDomain::Isaac, "TemporaryEffects",
     "GetCollectibleEffectNum", kV1, 0, ThreadAffinity::ManagedCallback,
     ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x00FE), ApiDomain::Isaac, "TemporaryEffects",
     "GetTrinketEffectNum", kV1, 0, ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x00FF), ApiDomain::Isaac, "TemporaryEffects", "GetNullEffectNum",
     kV1, 0, ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x0100), ApiDomain::Isaac, "TemporaryEffects",
     "AddCollectibleEffect", kV1, 0, ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x0101), ApiDomain::Isaac, "TemporaryEffects", "AddTrinketEffect",
     kV1, 0, ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x0102), ApiDomain::Isaac, "TemporaryEffects", "AddNullEffect", kV1,
     0, ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x0103), ApiDomain::Isaac, "TemporaryEffects",
     "RemoveCollectibleEffect", kV1, 0, ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x0104), ApiDomain::Isaac, "TemporaryEffects",
     "RemoveTrinketEffect", kV1, 0, ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x0105), ApiDomain::Isaac, "TemporaryEffects", "RemoveNullEffect",
     kV1, 0, ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x0106), ApiDomain::Isaac, "TemporaryEffects", "ClearEffects", kV1,
     0, ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x0107), ApiDomain::Isaac, "TemporaryEffects",
     "GetCollectibleEffect", kV1, 0, ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x0108), ApiDomain::Isaac, "TemporaryEffects", "GetNullEffect", kV1,
     0, ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x0109), ApiDomain::Isaac, "TemporaryEffects", "GetTrinketEffect",
     kV1, 0, ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x010A), ApiDomain::Isaac, "TemporaryEffects", "GetEffectsList",
     kV1, 0, ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    // 扩展PC模组环境的持久化数据对象：StageAPI查询解锁状态，参数/返回按REPENTOGON绑定。
    {MakeId(ApiDomain::Isaac, 1, 0x010B), ApiDomain::Isaac, "PersistentGameData", "Unlocked", kV1,
     0, ThreadAffinity::Any, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x0113), ApiDomain::Isaac, "PersistentGameData", "GetBestiaryKillCount", kV1,
     0, ThreadAffinity::Any, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x0114), ApiDomain::Isaac, "PersistentGameData", "GetBestiaryDeathCount", kV1,
     0, ThreadAffinity::Any, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x0115), ApiDomain::Isaac, "PersistentGameData", "GetBestiaryEncounterCount", kV1,
     0, ThreadAffinity::Any, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x0116), ApiDomain::Isaac, "PersistentGameData", "AddBestiaryKill", kV1,
     0, ThreadAffinity::Any, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x0117), ApiDomain::Isaac, "PersistentGameData", "AddBossKilled", kV1,
     0, ThreadAffinity::Any, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x0118), ApiDomain::Isaac, "PersistentGameData", "IsBossKilled", kV1,
     0, ThreadAffinity::Any, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x0119), ApiDomain::Isaac, "EntityFamiliar", "GetOrbitPosition", kV1,
     0, ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x011A), ApiDomain::Isaac, "EntityFamiliar", "RecalculateOrbitOffset", kV1,
     0, ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x011B), ApiDomain::Isaac, "EntityFamiliar", "AddToOrbit", kV1,
     0, ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x011C), ApiDomain::Isaac, "EntityFamiliar", "RemoveFromOrbit", kV1,
     0, ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    // ---- 批次 345（2026-10-04）：一条（Isaac 域取号 0x00F8）----
    // `Isaac.Explode(Vector pos, Entity source, float damage)`（**5 处** / 2 个模组）：**手写**。
    // 真身 `Game::BombExplosionEffects @ 0x355C68`（入口字 `0xD10443FF`）—— **9 个形参**
    // ⇒ 第 9 格 `bool` **走栈**（`ldrb w21,[x29,#0x60]`），通用跳板填不了；
    // 第 4 格是 16 字节**按值**的 `bitset128_t`（走 `x2:x3`）。
    // 末尾 4 格是绑定常量 `f=1.0f / b=true / ul=4 / b2=false`；`tearFlags` 传全 0（与 PC 逐字节同）。
    {MakeId(ApiDomain::Isaac, 1, 0x00F8), ApiDomain::Isaac, "Isaac", "Explode", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    // ---- 批次 346（2026-10-04）：一条（Isaac 域取号 0x00F9）----
    // `Entity:AddVelocity(Vector Velocity[, boolean IgnoreTimeScale = false])`（**20 处**）：
    // **手写纯算法**（Switch 侧**没有可调真身**：符号 0 命中 / NRO 原始字节 0 命中）。
    // PC 绑定 `0x422B60` 的算式：`friction = this[+0x2c4]; if (friction == 0.0f) return;
    // k = bool ? 1.0f : this[+0x2f4]; this[+0x2b8] += (k*v.x)/friction; …` —— 无钳制、**无任何 `call`**
    // （**不调** `TimeScaledFriction`，调了反而与 PC 不一致）。Switch 三格：速度 `+0x334/+0x338`、
    // 摩擦 `+0x340`、时间缩放 `+0x370`（本批新增 `kEntityTimeScaleOffset`）。
    // ★★ 本条**推翻旧负结果**「两侧摩擦模型不同 ⇒ 不能做」：实为**同一族**，按 PC 算式复刻即一致。
    {MakeId(ApiDomain::Isaac, 1, 0x00F9), ApiDomain::Isaac, "Entity", "AddVelocity", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Game, 1, 0x000E), ApiDomain::Game, "Game", "AddDevilRoomDeal", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Game, 1, 0x000F), ApiDomain::Game, "Game", "Update", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Level, 1, 0x0012), ApiDomain::Level, "Level", "Update", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Level, 1, 0x0013), ApiDomain::Level, "Level", "UpdateVisibility", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Room, 1, 0x000F), ApiDomain::Room, "Room", "GetRoomConfigStage", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Room, 1, 0x0010), ApiDomain::Room, "Room", "HasCurseMist", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Room, 1, 0x0011), ApiDomain::Room, "Room", "IsAmbushActive", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Room, 1, 0x0012), ApiDomain::Room, "Room", "IsCurrentRoomLastBoss", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Room, 1, 0x0013), ApiDomain::Room, "Room", "RemoveDoor", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Room, 1, 0x0014), ApiDomain::Room, "Room", "Update", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    // ---- 批次 239（2026-09-30）：语料模组适配第二波 A 批（18 条引擎方法数据行）。
    // 域内序号一律取**该域的下一个空号**（G5 闸门：不许猜"上一个 +1"，撞号会让
    // `ApiCatalog::Validate()` 判整张目录无效 ⇒ 所有 API 全不挂）。
    // 逐条的偏移/入口指纹/调用点证据见 `runtime_constants.hpp` 的批次 239 段；
    // 形状选择理由见 `engine_method_api.hpp` 的 `EngineCallShape` 与各数据行的注释。
    {MakeId(ApiDomain::Game, 1, 0x0010), ApiDomain::Game, "Game", "GetGreedBossWaveNum", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    // ---- 批次 252（2026-10-01）：`Game:ShowHallucination`（走 `kGameEngineRows` 数据行）。
    // ★ 契约里 `Backdrop` 的缺省值**不是 0**（`NUM_BACKDROPS` 是枚举末值）⇒ 形状用 `Void2`、
    //   两个参数都必填（"尾部可省"那一格只在缺省值恰好是 0 时才对）。
    {MakeId(ApiDomain::Game, 1, 0x0011), ApiDomain::Game, "Game", "ShowHallucination", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    // ---- 批次 253（2026-10-01）：`Game:CharmFart`（域内序号取 0x0012）。
    {MakeId(ApiDomain::Game, 1, 0x0012), ApiDomain::Game, "Game", "CharmFart", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    // ---- 批次 254（2026-10-01）：`Game:MoveToRandomRoom`（走数据行；域内序号取 0x0013）。
    // 三种参数种类（`Bool`/`Int`/`Handle`）都已在形状表里 ⇒ 这一条是纯数据行。
    {MakeId(ApiDomain::Game, 1, 0x0013), ApiDomain::Game, "Game", "MoveToRandomRoom", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    // ---- 批次 267（2026-10-02）：`Game:SpawnParticles`（域内序号 0x0014，取 Game 域 max+1）。
    // ★ 手写处理器（不是数据行）：第 5 个参数是 `ColorMod const&`，要**先从 Lua 的 `Color`
    //   构造一个 44 字节的引擎对象**，形状机制表达不了那一步。ABI 与取证见实现处注释。
    {MakeId(ApiDomain::Game, 1, 0x0014), ApiDomain::Game, "Game", "SpawnParticles", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Level, 1, 0x0014), ApiDomain::Level, "Level", "SetStage", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Level, 1, 0x0015), ApiDomain::Level, "Level", "SetNextStage", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Level, 1, 0x0016), ApiDomain::Level, "Level", "GetPlanetariumChance", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Level, 1, 0x0017), ApiDomain::Level, "Level", "GetRandomRoomIndex", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    // ---- 批次 270（2026-10-02）：`Level:QueryRoomTypeIndex`（域内序号 0x0018 = Level 域 max+1）
    // —— 作业单 `needs_new_shape` 桶的最后一条。**手写**（第 3 个参数是 `RNG&`），
    // 但**不新增 `EngineCallShape`**：手写处理器本来就什么形状都能写。
    // ★ `RNG` 句柄就是引擎 `RNG` 对象的裸存储（`RngHandle::storage`），把地址交出去即同一件东西。
    {MakeId(ApiDomain::Level, 1, 0x0018), ApiDomain::Level, "Level", "QueryRoomTypeIndex", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    // ---- 批次 294（2026-10-03）：`Level` 的两个**房间列表索引**（合 3 处）----
    // 两条都**没有**引擎同名访问器（PC 侧那两个绑定本体就是 `mov eax,[ecx+0x18198/0x181A4]; ret`）
    // ⇒ 走**字段读取型数据行**（`remaining_api.cpp` 的 `kLevelFieldApis`，`I32` + `FieldReceipt::Level`）。
    // Switch 侧的偏移由具名读者定：`GetPreviousRoomIndex` = `Level+0x2155C`
    // （`Level::GetLastRoomDesc` 把它当 `GetRoomByIdx` 的第一个实参 + 三个 `Room::TrySpawn*Door`）、
    // `GetLastBossRoomListIndex` = `Level+0x21568`（`Room::IsCurrentRoomLastBoss` 把它与当前房间
    // 描述符的 `+0x8` 比较 + 六个具名读者）。
    // 契约：`tools/pc_contract_docs/Level.md` 的 193 / 167 行。
    {MakeId(ApiDomain::Level, 1, 0x0019), ApiDomain::Level, "Level", "GetPreviousRoomIndex", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Level, 1, 0x001A), ApiDomain::Level, "Level", "GetLastBossRoomListIndex", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    // ---- 批次 297（2026-10-03）：`Game`/`Level` 的**状态标志读取**（各 13 处，合 26 处 / 5 个模组）----
    // 两条都**没有**引擎同名访问器（PC 侧那两个绑定本体分别是
    // `test dword [esi + 4*(Flag>>5) + 0x1822C], 1<<(Flag&31)` 与 64 位字那一套）⇒ 走**字段读取型
    // 数据行**，且是**同一条新机制** `FieldKind::BoolBitArrayOfArg`（位号来自 Lua 实参；
    // `offset2` = 元素宽度 —— `Game` 那格是"每字节 8 位"（宽度 1）、`Level` 那格是 `u64`（宽度 8））。
    // ★ Switch 侧两个基址都用"具名函数 + 具名标志号"定死，各有**两处互相独立**的位点位：
    //   `Game + 0x26FA50`（标志 48 在字节 6 位 0、标志 47 在字节 5 位 7）与
    //   `Level + 0x215F0` 的 `u64`（标志 2 = `SetRedHeartDamage` 的 `orr #0x4`、
    //   标志 7 = `ApplyCompassEffect` 的 `orr #0x80`）—— 详见 `runtime_constants.hpp` 的批次 297 段。
    // ★ 这两条同时配了两张枚举表（`GameStateFlag` / `LevelStateFlag`）—— 模组是拿
    //   `GameStateFlag.STATE_BACKWARDS_PATH` 当实参的，表是 nil 时整行抛错、回调被摘。
    // 契约：`tools/pc_contract_docs/Game.md` / `Level.md` 的 `GetStateFlag` 行。
    {MakeId(ApiDomain::Game, 1, 0x0015), ApiDomain::Game, "Game", "GetStateFlag", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Level, 1, 0x001B), ApiDomain::Level, "Level", "GetStateFlag", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    // ---- 批次 300（2026-10-03）：`Game`/`Level` 的**状态标志写入**（各 1 处）----
    // 与 297 那两条读侧是**同一对位数组**（`Game+0x26FA50` 每字节 8 位 / `Level+0x215F0` 的 `u64`）；
    // PC 侧四条绑定（读/写 × Game/Level）也落在同一对格上 ⇒ 走**字段行**、新种类
    // `FieldKind::BoolBitArrayOfWriteArg`（按实参给的标志号读改写那一位，返回 0 个值）。
    // ★ 语料里 `ChallengeAPI` 同时用了读与写（`GetStateFlag(...) or GetStateFlag(...)` 与
    //   `SetStateFlag(STATE_BACKWARDS_PATH_INIT, true)`）⇒ 写侧缺了那条模组照样断。
    {MakeId(ApiDomain::Game, 1, 0x0016), ApiDomain::Game, "Game", "SetStateFlag", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Level, 1, 0x001C), ApiDomain::Level, "Level", "SetStateFlag", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    // ---- 批次 313（2026-10-03）：`Level` 头部两个**布尔标志字节**（合 4 处 / 2 个模组）----
    // 只读字段、走 `field_row`（数据行在 `remaining_api.cpp` 的 `kLevelFieldApis`，偏移与证据在
    // `runtime_constants.hpp` 的批次 313 段）。两条都是"读一个字节、非 0 即真"，接收者
    // `FieldReceipt::Level`（`Game`/`Level` 同一地址）。
    // ★★ 偏移靠"**Switch 的 `Level` 头部与 PC 逐格一致**"钉住：`+0x00`/`+0x04`/`+0x0C` 三条
    //   两平台同值（各有具名函数）⇒ 夹在中间的 `+0x08` 同格；`+0x11` 另有具名消费者
    //   （`Level::try_display_room` 的透视分支）自证语义。
    {MakeId(ApiDomain::Level, 1, 0x001D), ApiDomain::Level, "Level", "HasBossChallenge", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Level, 1, 0x001E), ApiDomain::Level, "Level", "GetCanSeeEverything", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Room, 1, 0x0015), ApiDomain::Room, "Room", "RemoveGridEntity", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Room, 1, 0x0016), ApiDomain::Room, "Room", "GetGridCollision", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Room, 1, 0x0017), ApiDomain::Room, "Room", "SetGridPath", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Room, 1, 0x0018), ApiDomain::Room, "Room", "SpawnClearAward", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Room, 1, 0x0019), ApiDomain::Room, "Room", "DestroyGrid", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Room, 1, 0x001A), ApiDomain::Room, "Room", "TurnGold", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    // ---- 批次 249（2026-10-01）：`Room` 三个**返回 Vector** 的方法（手写，因为跳板只支持标量返回）。
    // ★ 工作清单把它们评为"16 字节值类型、走 x8"—— 那是**错的**：反汇编 `Room::GetGridPosition`
    //   看到的是 `ldp s0, s1, [sp, #0x8]` + `ret` ⇒ `Vector2` 是 8 字节、走 `s0`/`s1`。
    //   取证见 `runtime_constants.hpp` 的 `kRoomGetCenterPosOffset` 段。
    {MakeId(ApiDomain::Room, 1, 0x001B), ApiDomain::Room, "Room", "GetCenterPos", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Room, 1, 0x001C), ApiDomain::Room, "Room", "GetGridPosition", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Room, 1, 0x001D), ApiDomain::Room, "Room", "GetRandomPosition", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    // ---- 批次 252（2026-10-01）：`Room:SpawnGridEntity`（走数据行；域内序号取 0x001E）。
    // 契约写返回 `boolean`，但引擎符号 `…EiNS_15eGridEntityTypeEjji` **没有返回值特征**
    // ⇒ 按**符号**取形状（G3 口径）：`VoidIntIntIntIntInt`。语料那处也不接返回值。
    {MakeId(ApiDomain::Room, 1, 0x001E), ApiDomain::Room, "Room", "SpawnGridEntity", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    // ---- 批次 253（2026-10-01）：`Room:IsPositionInRoom`（域内序号取 0x001F）。
    // ★ 它的第 1 个参数是 `Vector2 const&` ⇒ 走**指针**，不需要扩跳板（见 `Vector2Ref` 那段）。
    {MakeId(ApiDomain::Room, 1, 0x001F), ApiDomain::Room, "Room", "IsPositionInRoom", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    // ---- 批次 259（2026-10-01）：`Room` 四条**位置类**方法（域内序号 0x0020..0x0023）。
    // 都返回 `Vector2` ⇒ 都走**手写处理器**（跳板只支持标量返回，理由与批次 249 的三条相同）。
    // 契约：`tools/pc_contract_docs/Room.md` 的 78 / 152 / 83 / 291 行。
    {MakeId(ApiDomain::Room, 1, 0x0020), ApiDomain::Room, "Room", "FindFreePickupSpawnPosition",
     kV1, 0, ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Room, 1, 0x0021), ApiDomain::Room, "Room", "GetClampedPosition", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Room, 1, 0x0022), ApiDomain::Room, "Room", "FindFreeTilePosition", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Room, 1, 0x0023), ApiDomain::Room, "Room", "GetDoorSlotPosition", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    // ---- 批次 269（2026-10-02）：`blocked_decision` 桶的渲染两条（域内序号 0x24/0x25）。
    // ★★ 两条都是 **`Placeholder`**：PC 侧各是一条 6 字节访问器（`Room+0x12BC` / `Room+0x11FC`），
    //   而 Switch 侧的对应字段**没有取证到**（符号表没有访问器、`RenderStart` 无直接调用点、
    //   PC 与 Switch 的成员布局不同 ⇒ 偏移不能平移）。给保守值而不是编一个像真值的常量 ——
    //   后果（`RENDER_NORMAL` 让水面房间多画一层 / 屏幕尺寸偏小约 8%）逐条写在
    //   `api_deviation.cpp` 的那两条里，也在实现处的注释里。
    {MakeId(ApiDomain::Room, 1, 0x0024), ApiDomain::Room, "Room", "GetRenderMode", kV1, 0,
     ThreadAffinity::MainRender, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Room, 1, 0x0025), ApiDomain::Room, "Room", "GetRenderSurfaceTopLeft", kV1, 0,
     ThreadAffinity::MainRender, ApiMaturity::Experimental},
    // ---- 批次 289（2026-10-02）：`Room` 的两条**边界访问器**（域内序号 0x0026/0x0027）。
    // ★ 两条都返回 `Vector`，而引擎里**都没有同名访问器**（PC 侧那两个方法本体就是原样返回成员，
    //   Switch 侧连符号都没有）⇒ 走**字段读取型数据行**（`FieldKind::Vector2Pair` 压一个真正的
    //   Lua `Vector`，见 `remaining_api.cpp` 的 `kRoomFieldApis`）。
    //   偏移的由来与四条互证见 `runtime_constants.hpp` 的批次 289 段。
    // 契约：`tools/pc_contract_docs/Room.md` 的 566 / 119 行。
    {MakeId(ApiDomain::Room, 1, 0x0026), ApiDomain::Room, "Room", "GetTopLeftPos", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Room, 1, 0x0027), ApiDomain::Room, "Room", "GetBottomRightPos", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    // ---- 批次 290（2026-10-02）：`Room:GetRoomShape()`（域内序号 0x0028）。
    // ★ 引擎里**没有同名访问器**（PC 侧那个方法本体就是走两跳指针链读一个成员，
    //   Switch 侧连符号都没有）⇒ 走**字段读取型数据行**，但接收者是**两跳链的末端**
    //   （`FieldReceipt::RoomConfigData`：当前房间 → 描述符 → 房间配置对象）。
    //   偏移与三条独立读者的证据见 `runtime_constants.hpp` 的 `kRoomConfigShapeOffset`。
    // 契约：`tools/pc_contract_docs/Room.md` 的 530 行。
    {MakeId(ApiDomain::Room, 1, 0x0028), ApiDomain::Room, "Room", "GetRoomShape", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    // ---- 批次 291（2026-10-02）：`Room` 的四个**只读状态量**（域内序号 0x0029..0x002C）。
    // ★ 四条在引擎里都**没有同名访问器**（Switch 构建里连符号都没有）⇒ 全部走
    //   **字段读取型数据行**（`remaining_api.cpp` 的 `kRoomFieldApis`），0 字节代码。
    //   接收者两类：`GetBossID`/`IsFirstVisit` 的字段在 `Room` 自己身上（`FieldReceipt::Room`），
    //   `IsAmbushDone`/`HasWaterPits` 的字段在**房间描述符**的 `Flags` 位掩码上
    //   ⇒ 本批新收的 `FieldReceipt::RoomDescriptor` + 新种类 `FieldKind::BoolBit`。
    //   偏移、PC 绑定函数本体与 Switch 侧具名消费者的证据链见 `runtime_constants.hpp` 的批次 291 段。
    // 契约：`tools/pc_contract_docs/Room.md` 的 109 / 670 / 639 / 622 行。
    {MakeId(ApiDomain::Room, 1, 0x0029), ApiDomain::Room, "Room", "GetBossID", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Room, 1, 0x002A), ApiDomain::Room, "Room", "IsFirstVisit", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Room, 1, 0x002B), ApiDomain::Room, "Room", "IsAmbushDone", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Room, 1, 0x002C), ApiDomain::Room, "Room", "HasWaterPits", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    // ---- 批次 292（2026-10-02）：`Room` 的背景类型 + 清房标志的**写入口**（域内序号 0x002D/0x002E）。
    // ★ `GetBackdropType`：引擎里**没有同名访问器**（PC 侧那个方法本体就是原样返回成员，
    //   Switch 侧连符号都没有）⇒ 走**字段读取型数据行**，读 `Room+0x21B0`
    //   （内嵌 `Backdrop` 子对象的 `eBackdrop`）。
    //   ★ 与本批同时把 `BackdropType` 枚举表生成进运行时 —— 那是**同一件事的两半**
    //     （与批次 269 的 `RenderMode` + `Room:GetRenderMode()` 同形）。
    // ★ `SetClear(boolean)`：PC 侧本体（`0x497800`）就是"读描述符 `Flags` → 按实参置/清 bit0
    //   → 写回"⇒ 本批新收 `FieldKind::BoolBitWrite`（**写一位、不返回值**，是本机制第一条
    //   有副作用的 kind）；**不改走** `Room::TriggerClear(bool)`（副作用远多于 PC 的 `SetClear`）。
    // 契约：`tools/pc_contract_docs/Room.md` 的 103 / 772 行。
    {MakeId(ApiDomain::Room, 1, 0x002D), ApiDomain::Room, "Room", "GetBackdropType", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Room, 1, 0x002E), ApiDomain::Room, "Room", "SetClear", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    // ---- 批次 295（2026-10-03）：房间的**两个种子**（各 8 处 = 16 处）----
    // 两条都**没有**引擎同名访问器（PC 侧那两个绑定本体是 `mov eax,[ecx+4]` → 空则返回 0 →
    // `mov eax,[eax+0x58/0x5C]; ret`）⇒ 走字段行（`kRoomFieldApis`，`I32` + `FieldReceipt::RoomDescriptor`）。
    // Switch 侧的偏移由具名消费者定：`DecorationSeed` = `descriptor+0x64`
    // （★ `Room::LoadBackdropGraphics` 把它喂给 `Backdrop::SetSeed`）、
    // `SpawnSeed` = `descriptor+0x68`（★ `Room::Init` 用它建 RNG 挑房间内随机格子，抽签次数看硬核模式）。
    // 契约：`tools/pc_contract_docs/Room.md` 的 158 / 556 行。
    {MakeId(ApiDomain::Room, 1, 0x002F), ApiDomain::Room, "Room", "GetDecorationSeed", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Room, 1, 0x0030), ApiDomain::Room, "Room", "GetSpawnSeed", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    // ---- 批次 302（2026-10-03）：`Room:SetFloorColor` / `SetWallColor`（各 9 处 = 18 处）----
    // PC 的两条绑定本体各只有 12 条指令、**逐字同形**：`add ecx,0x7188` / `add ecx,0x71b4` 之后
    // 把 44 字节的实参整块拷进去（`ret 0x2c`）⇒ "写一个 `ColorMod` 成员"，**没有别的副作用**。
    // ★ 走**字段数据行**（新种类 `FieldKind::ColorModWrite`：把 `Color` 句柄转成 44 字节
    //   `ColorMod` 整块写进字段、返回 0 个值）—— 本机制里第一条实参是 `Color` 的行。
    //   数据行在 `remaining_api.cpp` 的 `kRoomFieldApis`（`Room+0x7968` / `+0x7994`，**0 字节代码**）。
    // ★ 两格为什么是地板/墙（构造函数用 `ColorMod::Reset` 初始化两格、`Room::Render` 把它们
    //   分别喂给 `Backdrop::RenderFloor` / `RenderWalls`、`Room::TurnGold` 写墙那一格）见
    //   `runtime_constants.hpp` 的批次 302 段；布局表 `room.json` 的 `FloorColorMod` / `WallColorMod`
    //   （`confirmed`，`--verify` 45 条证据全过）。
    // 契约：`tools/pc_contract_docs/Room.md` 的 783 / 834 行。
    {MakeId(ApiDomain::Room, 1, 0x0031), ApiDomain::Room, "Room", "SetFloorColor", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Room, 1, 0x0032), ApiDomain::Room, "Room", "SetWallColor", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Room, 1, 0x0039), ApiDomain::Room, "Room", "GetGridCollisionAtPos", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x011D), ApiDomain::Isaac, "EntityNPC", "GetPlayerTarget", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Sprite, 1, 0x0020), ApiDomain::Sprite, "Sprite", "GetOverlayFrame", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x011E), ApiDomain::Isaac, "Entity", "SetSpriteFrame", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x011F), ApiDomain::Isaac, "Entity", "ToBomb", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x0120), ApiDomain::Isaac, "EntityTear", "ResetSpriteScale", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x0121), ApiDomain::Isaac, "EntityNPC", "PlaySound", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
    {MakeId(ApiDomain::Isaac, 1, 0x0122), ApiDomain::Isaac, "EntityNPC", "AnimWalkFrame", kV1, 0,
     ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},

};

// Constant-initialized: no guard variable and no .init_array dependency.
const ApiCatalog g_defaultCatalog{kDefaultApis, sizeof(kDefaultApis) / sizeof(kDefaultApis[0])};

} // namespace

const ApiCatalog& ApiCatalog::Default() noexcept {
    return g_defaultCatalog;
}

const LuaApiDescriptor* ApiCatalog::At(std::size_t index) const noexcept {
    if (index >= count_) {
        return nullptr;
    }
    return &entries_[index];
}

const LuaApiDescriptor* ApiCatalog::Find(std::uint32_t id) const noexcept {
    for (std::size_t index = 0; index < count_; ++index) {
        if (entries_[index].id == id) {
            return &entries_[index];
        }
    }
    return nullptr;
}

const LuaApiDescriptor* ApiCatalog::Find(const char* owner, const char* name) const noexcept {
    if (EmptyText(owner) || EmptyText(name)) {
        return nullptr;
    }
    for (std::size_t index = 0; index < count_; ++index) {
        if (SameText(entries_[index].owner, owner) && SameText(entries_[index].name, name)) {
            return &entries_[index];
        }
    }
    return nullptr;
}

Status ApiCatalog::Validate() const noexcept {
    if (entries_ == nullptr || count_ == 0) {
        return Status{StatusCode::InvalidArgument};
    }
    if (count_ > kCapacity) {
        return Status{StatusCode::CapacityExceeded};
    }
    for (std::size_t index = 0; index < count_; ++index) {
        const LuaApiDescriptor& entry = entries_[index];
        if (entry.id == 0 || EmptyText(entry.owner) || EmptyText(entry.name)) {
            return Status{StatusCode::InvalidArgument};
        }
        if ((entry.id >> 24) != entry.DomainByte()) {
            return Status{StatusCode::InvalidArgument};
        }
        for (std::size_t other = index + 1; other < count_; ++other) {
            const LuaApiDescriptor& candidate = entries_[other];
            if (candidate.id == entry.id) {
                return Status{StatusCode::Rejected};
            }
            if (SameText(candidate.owner, entry.owner) && SameText(candidate.name, entry.name)) {
                return Status{StatusCode::Rejected};
            }
        }
    }
    return Status::Ok();
}

const char* ToString(ApiDomain domain) noexcept {
    switch (domain) {
        case ApiDomain::Global: return "Global";
        case ApiDomain::Mod: return "Mod";
        case ApiDomain::Game: return "Game";
        case ApiDomain::Level: return "Level";
        case ApiDomain::Room: return "Room";
        case ApiDomain::ItemPool: return "ItemPool";
        case ApiDomain::Music: return "Music";
        case ApiDomain::Rng: return "Rng";
        case ApiDomain::Persistence: return "Persistence";
        case ApiDomain::Input: return "Input";
        case ApiDomain::Diagnostic: return "Diagnostic";
        case ApiDomain::Font: return "Font";
        case ApiDomain::Vector: return "Vector";
        case ApiDomain::Sprite: return "Sprite";
        case ApiDomain::Isaac: return "Isaac";
        case ApiDomain::Seed: return "Seed";
        case ApiDomain::ModMenu: return "ModMenu";
        // 批次 207（2026-09-29）：`HUD`（`Game:GetHUD()` 的返回值）。
        // ★ 这个 `switch` 是 `-Werror -Wswitch` 的：新增域**不在这里加分支就编译不过**
        //   （本次正是这么被拦下的），所以它同时是一张"域清单"。
        case ApiDomain::Hud: return "Hud";
    }
    return "Unknown";
}

const char* ToString(ApiMaturity maturity) noexcept {
    switch (maturity) {
        case ApiMaturity::Experimental: return "Experimental";
        case ApiMaturity::HostVerified: return "HostVerified";
        case ApiMaturity::HardwareVerified: return "HardwareVerified";
        case ApiMaturity::Disabled: return "Disabled";
    }
    return "Unknown";
}

} // namespace isaac::runtime
