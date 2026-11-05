#pragma once

#include <array>
#include <cstddef>
#include <cstdint>
#include <string_view>

namespace isaac::runtime {

// Runtime 认识的全部"侵入点"（挂点）。这张表是**唯一真值源**：ID、显示名、用哪种侵入方式、
// 以及"它是不是加载 Mod 的前置条件"都写在一处，于是
//   * 应用层（`HookInstallService`）按它决定安装顺序与必需/可选策略；
//   * 基础设施（路由适配器）按它选后端；
//   * 读数/日志按它取名字。
//
// **加一个挂点 = 这里加一行**，外加该挂点自己的目标常量（`runtime_constants.hpp`）与回调体。
// 表放在 domain：它只描述事实，不依赖端口、也不依赖基础设施，谁都可以引用它。
enum class HookId : std::uint8_t {
    ManagerUpdate = 0,
    ManagerRender,
    PreGetCollectible,
    ManagerPresent,
    RebuildMountPoints,
    // 游戏开局：引擎在 `Game::Start` / `Game::StartFromSavedState` **返回之后**通知我们。
    // 模组的 `MC_POST_GAME_STARTED` 依赖它（没有它，EID 的开局初始化永远不执行）。
    GameStart,
    // --- 回调面补齐（2026-09-20 批次 102）：EID / GoodTrip 在等的四个事件 -----------
    //
    // 四条都走 `EntryRelay`（零占洞：改目标函数入口 16 字节），四个靶点的偏移与 16 字节守卫
    // 在 `runtime_constants.hpp`（那里的注释写了实参映射的依据）。
    // 全部标 `required = false`：装不上只让对应的回调静默不派发（与改造前一样），
    // 不该因此让整个 Mod 加载失败。
    UseActiveItem,
    UseCard,
    UsePill,
    GameExit,
    // 批次 103（第 2 期）：掉落物碰撞（`MC_PRE_PICKUP_COLLISION`）。
    PickupCollision,
    // 71精确挂在FixSpawnEntry内部预转换之后；用Internal，不再在Roomspawn入口通知。
    RoomEntitySpawn,
    // 贴图桥（2026-09-21）：`.pcx` 加载最后一站。走 `EntryRelay`（零占洞改入口 16 字节）。
    // 偏移与 16 字节守卫在 `runtime_constants.hpp`。标 `required = false`：装不上只让
    // `.png`→`.pcx` 兜底静默失效（退化为原生仅 `.pcx`），不该令整个 Mod 加载失败。
    ImagePcxLoad,
    // 贴图桥 v2（2026-09-21 下午）：真正的拦截点。`ImageManager::LoadImage` 文件版在
    // 创建贴图对象**之前**就用 `GetMountedFilePath` 查"文件在不在任何挂载点"，不在直接
    // 返回空 ⇒ v1 那层（`ImagePcx::Load`）对"文件不存在"永远等不到调用（真机 14:10 验证）。
    // 本层兜底：原函数失败 → 读同名 `.png` 转 PCX 字节 → 调五参内存版 → 原样交出返回值。
    ImageManagerLoadFile,
    // 贴图桥 v4：`IContentManager::GetMountedFilePath` —— 让"文件不在任何挂载点"的 `.pcx`
    // 也能被引擎自己那条加载链走通（返回合成的 `.pcx` 路径）。见 runtime_constants 的 v4 段。
    ContentGetMountedFilePath,
    // --- 模组页搬生产（2026-09-23，批次 076）：三个入口中继 -------------------------
    //
    // 由来：`docs/设计-模组页搬生产-20260923.md`。行为真值源是探针
    // `runtime/source/probe/native_mods_menu_probe.cpp`（那三个入口在探针里已逐字节核过、
    // 真机跑过）。偏移与 16 字节守卫在 `runtime_constants.hpp`。
    //
    // 三条都标 `required = false`：装不上只让"那一列多一格「模组」/ 模组页"静默失效
    // （回到改造前：菜单里没有模组那一项），不该因此让整个 Mod 加载失败。
    //
    // ⚠️ 这三个靶点与探针**是同一批入口**：入口中继靠"改写入口 16 字节"工作，同一入口
    // 装第二次必然 `EntryMismatch` ⇒ 探针构建里由 `SkipOptionalHooksPredicate` 跳过这三条
    // （编译期常量判据），探针自己那套安装照旧生效。
    MenuGameRender,
    MenuTitleRender,
    MenuManagerSetState,
    // 成就闸门（2026-09-24 批次 098 从 `TryUnlock` 挪到这里）：`SetReadOnly` 是**唯一**写
    // "只读位"（`PGD+0x1`）的地方，也是每局开局设一次"本局给不给成就"的关卡。
    // 我们在它入口上按 PC 的规则把参数改成「引擎原参数 OR 该禁」⇒ 禁与不禁都交回引擎。
    // `required = false`：装不上只是"开模组时不再禁成就"（退回 Switch 原生行为），不影响游戏。
    PersistentGameDataSetReadOnly,
    // 引擎那条"模组 content 加载"路的闸门（2026-09-26 批次 147）：`ModManager::LoadConfigs`
    // 逐条读 `ModEntry + 0x139` 决定读不读这个模组的 `content/*.xml`（皮肤 `costumes2.xml`、
    // 曲子 `music.xml`…）。我们在它入口按**存在存档分区里的**模组开关把这一字节改成该启用/该禁用，
    // 再放行原函数 ⇒ 引擎用它自己的解析器把模组内容加载进来。
    //
    // 为什么必须由我们补这一步：引擎判"这个模组关掉了没"只看卡上覆盖层里的 `<目录>/disable.it`，
    // 而我们的模组目录在 romfs 覆盖层里**不能写**（写它会触发"下次启动崩"，AGENTS 有整段记录）
    // ⇒ 我们的开关只能存在存档分区，引擎看不见。挂在这里 = 时机用引擎的、状态用我们的。
    //
    // `required = false`：装不上只是"模组的皮肤/音乐又回到进不来"（即今天之前的行为），
    // 不该因此让整个 Mod 加载失败。
    ModManagerLoadConfigs,
    // 批次 363（2026-10-04）：`ANM2::Load` 入口中继（见 `kHookCatalog` 里那一行的注释）。
    Anm2Load,
    // --- 批次 390（2026-10-07）：`MC_INPUT_ACTION` 的三处**引擎查询入口** -------------------
    //
    // 契约（`analysis/isaacdocs-snapshot/docs/enums/ModCallbacks.md:347-367`）：**引擎每次轮询某个
    // `ButtonAction` 时**触发一次（官方"执行信息"栏写 **每秒约 1470 次**），且**返回值可以覆盖**
    // 这次查询的结果（`nil` = 不覆盖）。语料 3 个消费者里**有 2 个靠这个覆盖**
    // （MCM 开菜单时屏蔽玩家输入、InputHelper 强制某键按下）⇒ 只"观察"不"覆盖"做不完整。
    // 2026-10-25：挂Manager高层三入口，原生Entity*尚未被清掉；其调用者含玩家、
    // HUD、受控跟班等。底层ManagerBase不再接此PC事件，原始Input查询仍有独立旁路。
    // 三条required=false，精确守卫及短函数重定位均通过才安装。
    ManagerIsActionPressed,
    ManagerIsActionTriggered,
    ManagerGetActionValue,
    // --- 批次 396（2026-10-07）：`MC_ENTITY_TAKE_DMG`(11) 的四条 + `MC_EVALUATE_CACHE`(8) ---
    //
    // 受伤为什么要四条：引擎里只有基类 `Entity::TakeDamage` 一份通用实现，而
    // `Entity_Player` / `Entity_Pickup` / `Entity_Slot` 三个子类**不回跳基类**
    // （全长反汇编核对，见 `runtime_constants.hpp` 那一段取证）⇒ 只挂基类会漏玩家受伤。
    // 覆盖口径 = 基类（吃 NPC/跟班/其余实体）+ 这三个子类，**不重复**。
    // 五条都 `required = false`：装不上只让对应回调静默不派发（与改造前一样）。
    // ⚠️ 名字必须与读数工具 `read_device_state_via_gdb.py` 的 `HOOK_NAMES` 逐字一致。
    EntityTakeDamage,
    EntityPlayerTakeDamage,
    EntityPickupTakeDamage,
    EntitySlotTakeDamage,
    // `Entity_Player::EvaluateItems()` —— 玩家属性重算的唯一总闸（入口不带 CacheFlag 实参，
    // 由中继从 `+0x1958` 掩码解位，见 `runtime_constants.hpp`）。
    EvaluateItems,
    // --- 批次 397（2026-10-07）：补全回调（第 2 批）—— 三条 hookable 的新入口中继 ---
    //
    // 三条的靶点与语义依据见 `runtime_constants.hpp` 的「批次 397」那段：
    //   * `Entity::Kill`：`MC_POST_ENTITY_KILL`（"death animation 被触发之前"）——
    //     ★ 只挂基类一条即全覆盖（NPC/跟班两个覆写都回跳基类，逐条反汇编核对过）；
    //   * `Entity_NPC::trigger_death_remove`：`MC_POST_NPC_DEATH`（"死亡动画播完之后"）；
    //   * `Game::End`：`MC_POST_GAME_END`（`IsGameOver` 由 `eEnding` 推，见那边的两项证据）。
    // 三条都 `required = false`：装不上只让对应回调静默不派发（与改造前一样）。
    // ⚠️ 名字必须与读数工具 `read_device_state_via_gdb.py` 的 `HOOK_NAMES` 逐字一致。
    EntityKill,
    NpcDeathRemove,
    GameEnd,
    // `Entity_Player::FireTear(...)`：`MC_POST_FIRE_TEAR`（"玩家开火"，Incubus 那条路也汇入这里）。
    // 靶点与整套 ABI 取证见 `runtime_constants.hpp` 的「批次 337」+「批次 397」两段。
    FireTear,
    FamiliarCollision,
    NpcCollision,
    PlayerCollision,
    TearCollision,
    ProjectileCollision,
    KnifeCollision,
    BombCollision,
    NpcRender,
    ItemPoolGetPill,
    ItemPoolGetPillEffect,
    GameDevolveEnemy,
    NpcUpdateAi,
    GameSpawnEx,
    ItemPoolTrinketFirstRandom,
    ItemPoolTrinketSelected,
    RoomClearAward,
    EntityRemovePointers,
    EntityDestructorRemove,
    LevelCurseFirstRandom,
    LevelCurseEvaluation,
    PickupSelection,
    PickupSelectionSpecial,
    ItemPoolGetCard,
    ModManagerUnload,
    ConsoleUnknownLength,
    ConsoleUnknownCompare,
    HudRender,
    RoomConfigLoadStageBinary,
    LevelLoadRoom,
    LevelInit,
    ConsoleLifecycle,
    PressurePlateAnimationWriter,
    PressurePlateDestructor,
    PressurePlateDeletingDestructor,
    ProjectileUpdate,
    ProjectileInit,
    EntityPlayerInit,
    GameStartStageTransition,
    EntityInit,
    NativeInputPoll,
    RoomConstructor,
    GameRerollLevelPickups,
    GameRerollLevelCollectibles,
    EntityTearInit,
    EntityEffectInit,
    NativeRestartInput,
    Count,
};

inline constexpr std::size_t kHookIdCount = static_cast<std::size_t>(HookId::Count);

// 侵入方式（策略标签）。具体怎么做由基础设施里的适配器实现：
//   LegacyIps  —— Atmosphere 静态中继 IPS + exlaunch 蹦床（历史路径）
//   EntryRelay —— 改写目标函数入口的 16 字节，跳到我们模块里的中继（零占洞）
//   GotSlot    —— 只改写该函数所用 PLT 桩读的那条 GOT 槽（零代码字节）
//   RelaySlot  —— 引擎侧的中继代码（由 IPS 放进游戏模块的代码洞）在"原调用返回之后"
//                 从一个**回调槽**里取出函数指针来调用；本后端只负责把我们的回调指针
//                 写进那个槽（同样零代码字节）；包括GameStart与弹幕Init/Update完成边界。
enum class HookBackend : std::uint8_t { LegacyIps, EntryRelay, GotSlot, RelaySlot, Internal };

struct HookDescriptor {
    HookId id;
    std::string_view name;   // 读数与日志用；不参与行为判定
    HookBackend backend;
    bool required;           // true = 装不上就不能加载 Mod；其余点失败只记 Skipped
};

// 顺序必须与 `HookId` 一致（测试会钉住这一点）。
inline constexpr std::array<HookDescriptor, kHookIdCount> kHookCatalog = {{
    {HookId::ManagerUpdate, "ManagerUpdate", HookBackend::EntryRelay, true},
    {HookId::ManagerRender, "ManagerRender", HookBackend::EntryRelay, false},
    {HookId::PreGetCollectible, "PreGetCollectible", HookBackend::EntryRelay, false},
    {HookId::ManagerPresent, "ManagerPresent", HookBackend::GotSlot, false},
    {HookId::RebuildMountPoints, "RebuildMountPoints", HookBackend::EntryRelay, false},
    {HookId::GameStart, "GameStart", HookBackend::RelaySlot, false},
    {HookId::UseActiveItem, "UseActiveItem", HookBackend::EntryRelay, false},
    {HookId::UseCard, "UseCard", HookBackend::EntryRelay, false},
    {HookId::UsePill, "UsePill", HookBackend::EntryRelay, false},
    {HookId::GameExit, "GameExit", HookBackend::EntryRelay, false},
    {HookId::PickupCollision, "PickupCollision", HookBackend::EntryRelay, false},
    {HookId::RoomEntitySpawn, "RoomEntitySpawn", HookBackend::Internal, false},
    {HookId::ImagePcxLoad, "ImagePcxLoad", HookBackend::EntryRelay, false},
    {HookId::ImageManagerLoadFile, "ImageManagerLoadFile", HookBackend::EntryRelay, false},
    {HookId::ContentGetMountedFilePath, "ContentGetMountedFilePath", HookBackend::EntryRelay, false},
    // 模组页搬生产（2026-09-23）：三个入口中继。名字与 `tools/read_device_state_via_gdb.py`
    // 的 `HOOK_NAMES` 必须逐字一致（那张表按 HookId 顺序读 `g_hookCallbacks`）。
    {HookId::MenuGameRender, "MenuGameRender", HookBackend::EntryRelay, false},
    {HookId::MenuTitleRender, "MenuTitleRender", HookBackend::EntryRelay, false},
    {HookId::MenuManagerSetState, "MenuManagerSetState", HookBackend::EntryRelay, false},
    {HookId::PersistentGameDataSetReadOnly, "PersistentGameDataSetReadOnly", HookBackend::EntryRelay,
     false},
    // 批次 147（2026-09-26）：模组 content 加载闸门。名字与读数工具 `read_device_state_via_gdb.py`
    // 的 `HOOK_NAMES` 必须逐字一致（那张表按 HookId 顺序读 `g_hookCallbacks`）。
    {HookId::ModManagerLoadConfigs, "ModManagerLoadConfigs", HookBackend::EntryRelay, false},
    // 批次 363（2026-10-04）：模组覆盖本体资源的最后一环。靶点是 `ANM2::Load` 的入口
    // （`0xC970`，16 字节守卫见 `runtime_constants.hpp` 那一段取证）。挂在这里是因为
    // 引擎开机时自己就把 `gfx/ui/minimap1.anm2` 这类共享路径按"本体层"读进了动画缓存，
    // 而缓存查找是"挂载点前缀 + 路径哈希、先命中先生效"⇒ 模组那份永远轮不到。
    // 回调先问解析器这条路径现在归谁，答模组层且缓存里还有旧条目时用引擎自己的原语作废它。
    // `required = false`：装不上只是"共享路径仍旧吃本体那份"（即今天之前的行为），
    // 不该因此让整个 Mod 加载失败。
    {HookId::Anm2Load, "Anm2Load", HookBackend::EntryRelay, false},
    // 批次 390（2026-10-07）：`MC_INPUT_ACTION` 的三处查询入口。名字与读数工具
    // `read_device_state_via_gdb.py` 的 `HOOK_NAMES` 必须逐字一致（它按 HookId 顺序读 `g_hookCallbacks`）。
    // ⚠️ `IsActionPressed` 与 `IsActionTriggered` 的 16 字节守卫**逐字节相同** ⇒ 守卫挡不住"两者互换"。
    {HookId::ManagerIsActionPressed, "ManagerIsActionPressed", HookBackend::EntryRelay, false},
    {HookId::ManagerIsActionTriggered, "ManagerIsActionTriggered", HookBackend::EntryRelay, false},
    {HookId::ManagerGetActionValue, "ManagerGetActionValue", HookBackend::EntryRelay, false},
    // 批次 396（2026-10-07）：`MC_ENTITY_TAKE_DMG` 的四条入口中继 + `MC_EVALUATE_CACHE`。
    // 名字与读数工具 `read_device_state_via_gdb.py` 的 `HOOK_NAMES` 必须逐字一致。
    {HookId::EntityTakeDamage, "EntityTakeDamage", HookBackend::EntryRelay, false},
    {HookId::EntityPlayerTakeDamage, "EntityPlayerTakeDamage", HookBackend::EntryRelay, false},
    {HookId::EntityPickupTakeDamage, "EntityPickupTakeDamage", HookBackend::EntryRelay, false},
    {HookId::EntitySlotTakeDamage, "EntitySlotTakeDamage", HookBackend::EntryRelay, false},
    {HookId::EvaluateItems, "EvaluateItems", HookBackend::EntryRelay, false},
    // 批次 397（2026-10-07）：补全回调（第 2 批）的三条。名字与读数工具的 `HOOK_NAMES` 逐字一致。
    {HookId::EntityKill, "EntityKill", HookBackend::EntryRelay, false},
    {HookId::NpcDeathRemove, "NpcDeathRemove", HookBackend::EntryRelay, false},
    {HookId::GameEnd, "GameEnd", HookBackend::EntryRelay, false},
    {HookId::FireTear, "FireTear", HookBackend::EntryRelay, false},
    {HookId::FamiliarCollision, "FamiliarCollision", HookBackend::EntryRelay, false},
    {HookId::NpcCollision, "NpcCollision", HookBackend::EntryRelay, false},
    {HookId::PlayerCollision, "PlayerCollision", HookBackend::EntryRelay, false},
    {HookId::TearCollision, "TearCollision", HookBackend::EntryRelay, false},
    {HookId::ProjectileCollision, "ProjectileCollision", HookBackend::EntryRelay, false},
    {HookId::KnifeCollision, "KnifeCollision", HookBackend::EntryRelay, false},
    {HookId::BombCollision, "BombCollision", HookBackend::EntryRelay, false},
    {HookId::NpcRender, "NpcRender", HookBackend::EntryRelay, false},
    {HookId::ItemPoolGetPill, "ItemPoolGetPill", HookBackend::EntryRelay, false},
    {HookId::ItemPoolGetPillEffect, "ItemPoolGetPillEffect", HookBackend::EntryRelay, false},
    {HookId::GameDevolveEnemy, "GameDevolveEnemy", HookBackend::EntryRelay, false},
    {HookId::NpcUpdateAi, "NpcUpdateAi", HookBackend::GotSlot, false},
    {HookId::GameSpawnEx, "GameSpawnEx", HookBackend::EntryRelay, false},
    {HookId::ItemPoolTrinketFirstRandom, "ItemPoolTrinketFirstRandom", HookBackend::Internal, false},
    {HookId::ItemPoolTrinketSelected, "ItemPoolTrinketSelected", HookBackend::Internal, false},
    {HookId::RoomClearAward, "RoomClearAward", HookBackend::Internal, false},
    {HookId::EntityRemovePointers, "EntityRemovePointers", HookBackend::GotSlot, false},
    {HookId::EntityDestructorRemove, "EntityDestructorRemove", HookBackend::Internal, false},
    {HookId::LevelCurseFirstRandom, "LevelCurseFirstRandom", HookBackend::Internal, false},
    {HookId::LevelCurseEvaluation, "LevelCurseEvaluation", HookBackend::Internal, false},
    {HookId::PickupSelection, "PickupSelection", HookBackend::Internal, false},
    {HookId::PickupSelectionSpecial, "PickupSelectionSpecial", HookBackend::Internal, false},
    {HookId::ItemPoolGetCard, "ItemPoolGetCard", HookBackend::GotSlot, false},
    {HookId::ModManagerUnload, "ModManagerUnload", HookBackend::GotSlot, false},
    {HookId::ConsoleUnknownLength, "ConsoleUnknownLength", HookBackend::Internal, false},
    {HookId::ConsoleUnknownCompare, "ConsoleUnknownCompare", HookBackend::Internal, false},
    {HookId::HudRender, "HudRender", HookBackend::GotSlot, false},
    {HookId::RoomConfigLoadStageBinary, "RoomConfigLoadStageBinary", HookBackend::GotSlot, false},
    {HookId::LevelLoadRoom, "LevelLoadRoom", HookBackend::GotSlot, false},
    {HookId::LevelInit, "LevelInit", HookBackend::GotSlot, false},
    {HookId::ConsoleLifecycle, "ConsoleLifecycle", HookBackend::GotSlot, false},
    {HookId::PressurePlateAnimationWriter, "PressurePlateAnimationWriter", HookBackend::EntryRelay, false},
    {HookId::PressurePlateDestructor, "PressurePlateDestructor", HookBackend::Internal, false},
    {HookId::PressurePlateDeletingDestructor, "PressurePlateDeletingDestructor", HookBackend::Internal, false},
    {HookId::ProjectileUpdate, "ProjectileUpdate", HookBackend::RelaySlot, false},
    {HookId::ProjectileInit, "ProjectileInit", HookBackend::RelaySlot, false},
    {HookId::EntityPlayerInit, "EntityPlayerInit", HookBackend::EntryRelay, false},
    {HookId::GameStartStageTransition, "GameStartStageTransition", HookBackend::EntryRelay, false},
    {HookId::EntityInit, "EntityInit", HookBackend::GotSlot, true},
    {HookId::NativeInputPoll, "NativeInputPoll", HookBackend::GotSlot, true},
    {HookId::RoomConstructor, "RoomConstructor", HookBackend::EntryRelay, true},
    {HookId::GameRerollLevelPickups, "GameRerollLevelPickups", HookBackend::GotSlot, false},
    {HookId::GameRerollLevelCollectibles, "GameRerollLevelCollectibles", HookBackend::GotSlot, false},
    {HookId::EntityTearInit, "EntityTearInit", HookBackend::GotSlot, true},
    {HookId::EntityEffectInit, "EntityEffectInit", HookBackend::GotSlot, true},
    {HookId::NativeRestartInput, "NativeRestartInput", HookBackend::GotSlot, false},
}};

// 取登记项。传入 `HookId::Count` 或越界值属于调用方错误，这里退化成第一个登记项
// （不抛异常 —— 这条路在游戏进程里跑，宁可返回保守值也不引入新的失败模式）。
[[nodiscard]] constexpr const HookDescriptor& DescriptorOf(HookId id) noexcept {
    const std::size_t index = static_cast<std::size_t>(id);
    return kHookCatalog[index < kHookIdCount ? index : 0];
}

[[nodiscard]] constexpr HookBackend BackendOf(HookId id) noexcept {
    return DescriptorOf(id).backend;
}

[[nodiscard]] constexpr bool IsRequired(HookId id) noexcept {
    return DescriptorOf(id).required;
}

[[nodiscard]] constexpr std::string_view NameOf(HookId id) noexcept {
    return DescriptorOf(id).name;
}

// 从表派生的后端数组（顺序 = HookId 顺序）。路由适配器用它，避免第二处定义。
[[nodiscard]] constexpr std::array<HookBackend, kHookIdCount> CatalogBackends() noexcept {
    std::array<HookBackend, kHookIdCount> backends{};
    for (std::size_t index = 0; index < kHookIdCount; ++index) {
        backends[index] = kHookCatalog[index].backend;
    }
    return backends;
}

} // namespace isaac::runtime
