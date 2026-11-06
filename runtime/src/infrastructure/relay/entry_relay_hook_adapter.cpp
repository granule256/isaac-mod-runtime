#include "infrastructure/internal/use_item_hook_installer.hpp"
#include "infrastructure/internal/player_damage_hook_installer.hpp"
#include "infrastructure/relay/entry_relay_hook_adapter.hpp"
#include "room_spawn_internal_hook.hpp"
#include "infrastructure/call/engine_call_access.hpp"

#include "anm2_load_override_hook.hpp"  // 批次 365：Anm2Load 的安装结果留痕
#include "image_pcx_bridge_hook.hpp"   // 批次 359：只为了让 RebuildMountPoints 的安装结果留痕
#include "relay/entry_relay.hpp"       // 侵入核心（source/relay/entry_relay.hpp）
#include "runtime_constants.hpp"       // M0 台账
#include "relay/smart_pointer_shim.hpp"  // v2：sret 返回值垫片（source/relay）
#include <atomic>

namespace isaac::runtime {
bool PublishManagerUpdateEntryRelayOriginal(std::uintptr_t original) noexcept;
namespace {

// 台账里的"入口已被入口中继改写"形态常量，必须与编码器逐字一致
// （别的子系统用它来识别入口形态，例如 `ValidateItemPoolGetCollectibleMethod`）。
static_assert(kEntryRelayEntryStubWord0 == relay::kEntryLdrX16Word,
              "kEntryRelayEntryStubWord0 必须等于编码器的 `ldr x16, #8`");
static_assert(kEntryRelayEntryStubWord1 == relay::kEntryBrX16Word,
              "kEntryRelayEntryStubWord1 必须等于编码器的 `br x16`");

// 回调指针表：由 `RegisterEntryRelayCallbacks()` 接上真实回调。初值全为 nullptr 是刻意的 ——
// 空回调会被判定拒绝（见下），否则会装上一个"跳进空地址"的中继。
void* g_hookCallbacks[kHookIdCount] = {};
std::atomic<std::uint32_t> g_installedEntries[kHookIdCount]{};

// 每个挂点一份回退入口存储（安装后写入，回调靠它跑原函数）。
std::uintptr_t g_fallbackEntries[kHookIdCount] = {};

// 真实回调在 hook_manager.cpp 里定义（与各自的钩子体同 TU），这里只持声明。
// 各路的形状不同，见 `RegisterEntryRelayCallbacks` 的注释。
extern "C" void EntryRelayManagerRenderCallback(void* self);
extern "C" void EntryRelayManagerUpdateCallback(void* self);
// 取道具前挂点：目标 ABI 是 `this + poolType + seed + noDecrease + defaultItem`（五个都要透传，
// 旧 IPS 中继桩同样收 x0..x4）。
extern "C" std::uint32_t EntryRelayPreGetCollectibleCallback(void* itemPool, std::uint32_t itemPoolType,
                                                             std::uint32_t seed,
                                                             std::uint32_t noDecrease,
                                                             std::uint32_t defaultItem);
// 挂载点重建：目标函数无参数（`_ZN...RebuildContentMountPointsEv`）。
extern "C" void EntryRelayRebuildMountPointsCallback();
// 成就闸门：`PersistentGameData::SetReadOnly(bool)`（`0x439460`）—— 唯一写"只读位"的地方。
// 形状 = 目标函数的 ABI（`(this /*x0*/, bool /*w1*/)`，返回 void）；我们在回调里把 w1
// 改成「引擎原参数 OR 该禁」再调回退入口（依据见 `runtime_constants.hpp` 那一段取证）。
extern "C" void EntryRelayPersistentGameDataSetReadOnlyCallback(void* self,
                                                               std::uint32_t readOnly);

// --- 回调面补齐（批次 102）：四个事件靶点 ---------------------------------------
//
// 形状各自不同，按目标函数的 ABI 逐字写（依据见 `runtime_constants.hpp` 那一段注释）：
//   * `UseActiveItem`：`(this /*x0*/, 道具 /*w1*/, UseFlags /*w2*/, ActiveSlot /*w3*/,
//     CustomVarData /*w4*/)`；入口派发 `MC_PRE_USE_ITEM`，五处原生消费前边界派 `MC_USE_ITEM`。
//   * `UseCard`：`(this, 卡 /*w1*/, UseFlags /*w2*/)`。
//   * `UsePill`：`(this, 药丸效果 /*w1*/, 药丸颜色 /*w2*/, UseFlags /*w3*/)`。
//   * `Game::Exit`：`(this /*x0*/, 要不要存档 /*w1*/)`。
extern "C" std::uint64_t EntryRelayUseActiveItemCallback(void* player, std::uint32_t item,
                                                std::uint32_t useFlags, std::int32_t activeSlot,
                                                std::int32_t customVarData);
extern "C" void EntryRelayUseCardCallback(void* player, std::uint32_t card,
                                          std::uint32_t useFlags);
extern "C" void EntryRelayUsePillCallback(void* player, std::uint32_t pillEffect,
                                          std::uint32_t pillColor, std::uint32_t useFlags);
extern "C" void EntryRelayGameExitCallback(void* game, std::uint32_t shouldSave);
// MC_INPUT_ACTION的Manager高层查询；第四实参是请求输入的Entity*，可为nullptr。
// 前两条返回bool，第三条float；底层ManagerBase的unsigned*不是本ABI。
extern "C" bool EntryRelayManagerIsActionPressedCallback(void* manager, std::uint32_t action,
                                                         std::uint32_t controller,
                                                         void* entity);
extern "C" bool EntryRelayManagerIsActionTriggeredCallback(void* manager, std::uint32_t action,
                                                           std::uint32_t controller,
                                                           void* entity);
extern "C" float EntryRelayManagerGetActionValueCallback(void* manager, std::uint32_t action,
                                                         std::uint32_t controller,
                                                         void* entity);

// 批次 103：`(掉落物 /*x0*/, 碰它的实体 /*x1*/, low /*w2*/)`。返回值决定要不要跑原函数
// （PC 三态，见 `runtime_constants.hpp` 里那个靶点的注释）。
extern "C" std::uint64_t EntryRelayPickupCollisionCallback(void* pickup, void* collider,
                                                  std::uint32_t low);

// 批次 396（2026-10-07）：`MC_ENTITY_TAKE_DMG` 的四条入口中继。四条形状完全相同
// （目标 ABI 逐字对）：`(实体 /*x0*/, Amount /*s0*/, DamageFlags /*x1*/,
// Source /*x2 = &EntityRef*/, CountdownFrames /*w3*/)`。
// ★ 返回值**必须原样搬运**：本体在 w0 里返回"这次伤害有没有落实"，`Entity_NPC::TakeDamage`
//   拿到它继续用（`0x122260 mov w20,w0`）⇒ 声明成 void 会把引擎的后续判断弄坏。
//   "模组返回 false"时不跑原函数、返回 0（= 这次伤害没落实）。
extern "C" std::uint64_t EntryRelayEntityTakeDamageCallback(void* entity, float amount,
                                                            std::uint64_t damageFlags,
                                                            const void* sourceRef,
                                                            std::int32_t countdownFrames);
extern "C" std::uint64_t EntryRelayEntityPlayerTakeDamageCallback(void* entity, float amount,
                                                                  std::uint64_t damageFlags,
                                                                  const void* sourceRef,
                                                                  std::int32_t countdownFrames);
extern "C" std::uint64_t EntryRelayEntityPickupTakeDamageCallback(void* entity, float amount,
                                                                  std::uint64_t damageFlags,
                                                                  const void* sourceRef,
                                                                  std::int32_t countdownFrames);
extern "C" std::uint64_t EntryRelayEntitySlotTakeDamageCallback(void* entity, float amount,
                                                                std::uint64_t damageFlags,
                                                                const void* sourceRef,
                                                                std::int32_t countdownFrames);

// 批次 396（2026-10-07）：`MC_EVALUATE_CACHE` —— `Entity_Player::EvaluateItems()`，
// 形状 = 无参成员函数（x0 = this = 玩家指针），返回 void。CacheFlag 掩码由回调自己读。
extern "C" void EntryRelayEvaluateItemsCallback(void* player);
extern "C" std::uint64_t EntryRelayFamiliarCollisionCallback(void* entity, void* collider, std::uint32_t low);
extern "C" std::uint64_t EntryRelayNpcCollisionCallback(void* entity, void* collider, std::uint32_t low);
extern "C" std::uint64_t EntryRelayPlayerCollisionCallback(void* entity, void* collider, std::uint32_t low);
extern "C" std::uint64_t EntryRelayTearCollisionCallback(void* entity, void* collider, std::uint32_t low);
extern "C" std::uint64_t EntryRelayProjectileCollisionCallback(void* entity, void* collider, std::uint32_t low);
extern "C" std::uint64_t EntryRelayKnifeCollisionCallback(void* entity, void* collider, std::uint32_t low);
extern "C" std::uint64_t EntryRelayBombCollisionCallback(void* entity, void* collider, std::uint32_t low);
extern "C" void* EntryRelayGameSpawnExCallback(void* game, std::int32_t type, std::uint32_t variant, const void* position, const void* velocity, void* spawner, std::uint32_t subType, std::uint32_t seed, std::uint32_t forceSpawn);
extern "C" void EntryRelayNpcRenderCallback(void* npc, const void* offset);
extern "C" std::int32_t EntryRelayItemPoolGetPillCallback(void* pool, std::uint32_t seed);
extern "C" std::int32_t EntryRelayItemPoolGetPillEffectCallback(void* pool, std::uint32_t color, void* player);
extern "C" std::uint64_t EntryRelayGameDevolveEnemyCallback(void* game, void* entity);

// 批次 397（2026-10-07）：补全回调（第 2 批）的三条入口中继。三条都返回 void。
//   * `Entity::Kill()` —— 无参成员（x0 = this = 实体）。
//   * `Entity_NPC::trigger_death_remove()` —— ★ 符号名是 `…20trigger_death_removeEv`（无参），
//     但函数体开头就读 `x1`（`0x11A3FC str x1,[sp,#0x18]` / `0x11A400 cbnz x1`）⇒ 我们按
//     **两个实参**声明，把它**原样转发**给原函数（我们从不解释它 ⇒ 转发即透明，无论它是什么）。
//   * `Game::End(eEnding)` —— x0 = this（Game*）、w1 = eEnding。
extern "C" void EntryRelayEntityKillCallback(void* entity);
extern "C" void EntryRelayEntityPlayerInitCallback(void*, std::uint32_t, std::uint32_t,
                                                   std::uint32_t, std::uint32_t);
extern "C" void EntryRelayRoomConstructorCallback(void*);
extern "C" void EntryRelayNpcDeathRemoveCallback(void* npc, void* forwarded);
extern "C" void EntryRelayGameEndCallback(void* game, std::int32_t ending);
extern "C" void EntryRelayGameStartStageTransitionCallback(void*, bool, int, void*);
//   * `Entity_Player::FireTear(...)` —— 形状**逐字照批次 337 已经定死的 ABI**
//     （`runtime_constants.hpp` 的「批次 337」段，那边是给 Lua API 手写转发用的同一套取证）：
//     `(this, Vector2 const& /*x1*/, Vector2 /*按值 HFA s0:s1*/, u32 flags /*w2*/,
//       Entity* Source /*x3*/, float DamageMultiplier /*s2*/)`，返回 `Entity_Tear*`（x0）。
extern "C" void* EntryRelayFireTearCallback(void* player, const void* position,
                                            RelayVector2Hfa velocity, std::uint32_t flags,
                                            void* source, float damageMultiplier);

// 批次 104：`Room::spawn_entity(unsigned GridIndex, RoomConfig::Entry const&, unsigned Seed,
// Entity**, bool)`。前三个实参都要转发给 `MC_PRE_ROOM_ENTITY_SPAWN`（Type/Variant/SubType 从
// 第二个实参的**前 12 字节**读，见 `runtime_constants.hpp` 里那段证据）。
extern "C" std::uint64_t EntryRelayRoomEntitySpawnCallback(void* room, std::uint32_t gridIndex,
                                                  const void* entry, std::uint32_t seed,
                                                  void** outEntity, std::uint32_t flags);

// 贴图桥（2026-09-21）：`KAGE::Graphics::ImagePcx::Load(char const*)`。ABI：x0 = this，
// x1 = 路径（`const char*`），返回 w0 = bool。回调自己决定是否跑原函数（入口中继契约），
// 并把返回值原样搬回游戏调用方（否则引擎读不到 `Load` 的成功/失败）。
extern "C" bool EntryRelayImagePcxLoadCallback(void* self, const char* path);

// 贴图桥 v2（2026-09-21 下午）：`KAGE::Graphics::ImageManager::LoadImage(char const*,
// VertexAttributeDescriptor*, bool)` @0x4d1fe4 —— 真正的拦截点（见 hook_catalog 的注释）。
// ABI：x0 = this，x1 = 路径，x2 = 顶点描述符，x3 = bool 标志；返回值是 16 字节
// `SmartPointer<ImageBase>`，按 Itanium ABI 走 **x8（sret）** —— 回调必须用同形状的
// `SmartPointerShim` 声明（非平凡复制 ⇒ 编译器自动按 sret 处理），否则返回值错位。
// clang 会为「extern "C" 返回 C++ 类类型」发 `-Wreturn-type-c-linkage` —— 这里**就是**
// 要按 C++ 对象语义走 sret，压掉该告警（gcc 没有这条告警，不受影响）。
#if defined(__clang__)
#pragma clang diagnostic push
#pragma clang diagnostic ignored "-Wreturn-type-c-linkage"
#endif
extern "C" isaac::runtime::relay::SmartPointerShim EntryRelayImageManagerLoadFileCallback(
    void* self, const char* path, void* descriptor, int flag);
#if defined(__clang__)
#pragma clang diagnostic pop
#endif

// 贴图桥 v4：`IContentManager::GetMountedFilePath(char const*)` —— 成员（x0=内容管理器，
// x1=路径），返回**堆上的挂载路径**（调用方用游戏自己的 delete[] 释放）或空。我们在"`.pcx` 不在任何
// 挂载点、但同名 `.png` 在"时返回一条合成的 `.pcx` 路径，让引擎自己那条链继续走。
extern "C" char* EntryRelayContentGetMountedFilePathCallback(void* self, const char* path);

// 模组页搬生产（2026-09-23，批次 076）：三个入口中继。定义在 `source/mod_menu_native.cpp`
// （与那一套状态机同处，便于对照注释）。形状按目标函数的 ABI 逐字写：
//   * `Menu_Game::Render()`   —— 无参成员（x0 = this）；
//   * `Menu_Title::Render()`  —— 同上；
//   * `MenuManager::SetState(eState)` —— x0 = this，w1 = 状态号（`int`）。
extern "C" void EntryRelayMenuGameRenderCallback(void* self);
extern "C" void EntryRelayMenuTitleRenderCallback(void* self);
extern "C" void EntryRelayMenuManagerSetStateCallback(void* self, std::int32_t state);

// 批次 147（2026-09-26）：`ModManager::LoadConfigs()` —— 无参成员（x0 = this = `ModManager*`），
// 返回 void。钩子体在 `source/hook_manager.cpp`：入口处按我们的模组开关改一遍
// 每条 `ModEntry + 0x139`（纯内存写），再调回退入口跑原函数。形状就是目标函数的 ABI。
extern "C" void EntryRelayModManagerLoadConfigsCallback(void* self);

// 批次 363（2026-10-04）：`ANM2::Load(std::string const&, bool)` —— 形状按目标函数 ABI 逐字写
// （x0 = ANM2*、x1 = libc++ 的 24 字节串对象、w2 = loadGraphics）。钩子体在
// `source/anm2_load_override_hook.cpp`：先问解析器这条路径归谁，答模组层且缓存里还有本体旧条目时
// 用引擎自己的原语作废它，再调回退入口跑原函数。
extern "C" void EntryRelayAnm2LoadCallback(void* anm2, const void* name,
                                           std::uint32_t loadGraphics);

// `RegisterEntryRelayCallbacks` 定义在匿名命名空间之外（外部链接）：调用点在
// hook_manager.cpp，而 g_hookCallbacks 在本 TU 的匿名命名空间里。

extern "C" void EntryRelayPressurePlateAnimationCallback(void*,bool);

EntryRelayBinding BindingOf(HookId id) noexcept {
    const auto index = static_cast<std::size_t>(id);
    void* callback = index < kHookIdCount ? g_hookCallbacks[index] : nullptr;
    switch (id) {
        case HookId::ManagerUpdate:
            return {"Manager::Update", kManagerUpdateFileOffset,
                    kManagerUpdateExpectedBytes.data(), callback, &g_fallbackEntries[index]};
        case HookId::ManagerRender:
            return {"Manager::Render", kManagerRenderFileOffset,
                    kManagerRenderExpectedBytes.data(), callback, &g_fallbackEntries[index]};
        case HookId::PreGetCollectible:
            return {"ItemPool::GetCollectible", kPreGetCollectibleRelayOffset,
                    kPreGetCollectibleRelayExpectedOriginal.data(), callback,
                    &g_fallbackEntries[index]};
        case HookId::RebuildMountPoints:
            return {"RebuildContentMountPoints", kRebuildContentMountPointsOffset,
                    kRebuildContentMountPointsExpectedBytes.data(), callback,
                    &g_fallbackEntries[index]};
        case HookId::PersistentGameDataSetReadOnly:
            return {"PersistentGameData::SetReadOnly", kPersistentGameDataSetReadOnlyOffset,
                    kPersistentGameDataSetReadOnlyExpectedBytes.data(), callback,
                    &g_fallbackEntries[index]};
        case HookId::PressurePlateAnimationWriter:
            return {"PressurePlate::play_greed_animation",kPressurePlateAnimationWriterOffset,
                kPressurePlateAnimationWriterExpectedBytes.data(),callback,&g_fallbackEntries[index]};
        case HookId::UseActiveItem:
            return {"Entity_Player::UseActiveItem", kEntityPlayerUseActiveItemOffset,
                    kEntityPlayerUseActiveItemExpectedBytes.data(), callback,
                    &g_fallbackEntries[index]};
        case HookId::UseCard:
            return {"Entity_Player::UseCard", kEntityPlayerUseCardOffset,
                    kEntityPlayerUseCardExpectedBytes.data(), callback, &g_fallbackEntries[index]};
        // 批次 390（2026-10-07）：`MC_INPUT_ACTION` 的三处**引擎查询入口**。
        // 高层保留Entity*；精确重定位其16字节完整短函数，不能拦底层unsigned*出口。
        case HookId::ManagerIsActionPressed:
            return {"IsaacRepentance::Manager::IsActionPressed", kManagerIsActionPressedOffset,
                    kManagerIsActionPressedExpectedBytes.data(), callback,
                    &g_fallbackEntries[index]};
        case HookId::ManagerIsActionTriggered:
            return {"IsaacRepentance::Manager::IsActionTriggered",
                    kManagerIsActionTriggeredOffset,
                    kManagerIsActionTriggeredExpectedBytes.data(), callback,
                    &g_fallbackEntries[index]};
        case HookId::ManagerGetActionValue:
            return {"IsaacRepentance::Manager::GetActionValue", kManagerGetActionValueOffset,
                    kManagerGetActionValueExpectedBytes.data(), callback,
                    &g_fallbackEntries[index]};
        // 批次 396（2026-10-07）：`MC_ENTITY_TAKE_DMG` 的四条（靶点与守卫见 runtime_constants.hpp
        // 那一大段取证）——基类吃通用实体，三个不回跳基类的子类各挂一条。
        case HookId::EntityTakeDamage:
            return {"Entity::TakeDamage", kEntityTakeDamageOffset,
                    kEntityTakeDamageExpectedBytes.data(), callback, &g_fallbackEntries[index]};
        case HookId::EntityPlayerTakeDamage:
            return {"Entity_Player::TakeDamage", kEntityPlayerTakeDamageOffset,
                    kEntityPlayerTakeDamageExpectedBytes.data(), callback,
                    &g_fallbackEntries[index]};
        case HookId::EntityPickupTakeDamage:
            return {"Entity_Pickup::TakeDamage", kEntityPickupTakeDamageOffset,
                    kEntityPickupTakeDamageExpectedBytes.data(), callback,
                    &g_fallbackEntries[index]};
        case HookId::EntitySlotTakeDamage:
            return {"Entity_Slot::TakeDamage", kEntitySlotTakeDamageOffset,
                    kEntitySlotTakeDamageExpectedBytes.data(), callback,
                    &g_fallbackEntries[index]};
        // 批次 396（2026-10-07）：`MC_EVALUATE_CACHE` 的唯一总闸。
        case HookId::EvaluateItems:
            return {"Entity_Player::EvaluateItems", kEntityPlayerEvaluateItemsOffset,
                    kEntityPlayerEvaluateItemsExpectedBytes.data(), callback,
                    &g_fallbackEntries[index]};
        // 批次 397（2026-10-07）：补全回调（第 2 批）的三条（靶点与语义依据见 runtime_constants.hpp）。
        case HookId::EntityKill:
            return {"Entity::Kill", kEntityKillOffset, kEntityKillExpectedBytes.data(), callback,
                    &g_fallbackEntries[index]};
        case HookId::GameStartStageTransition:
            return {"Game::StartStageTransition", kApi200GameStartStageTransitionOffset,
                    kApi200GameStartStageTransitionExpectedBytes.data(), callback, &g_fallbackEntries[index]};
        case HookId::EntityPlayerInit:
            return {"Entity_Player::Init", kNativePlayerInitOffset,
                    kNativePlayerInitExpectedBytes.data(), callback, &g_fallbackEntries[index]};
        case HookId::RoomConstructor:
            return {"Room::Room", kNativeRoomConstructorOffset,
                    kNativeRoomConstructorExpectedBytes.data(), callback, &g_fallbackEntries[index]};
        case HookId::NpcDeathRemove:
            return {"Entity_NPC::trigger_death_remove", kEntityNpcTriggerDeathRemoveOffset,
                    kEntityNpcTriggerDeathRemoveExpectedBytes.data(), callback,
                    &g_fallbackEntries[index]};
        case HookId::GameEnd:
            return {"Game::End", kGameEndOffset, kGameEndExpectedBytes.data(), callback,
                    &g_fallbackEntries[index]};
        case HookId::FireTear:
            return {"Entity_Player::FireTear", kEntityPlayerFireTearOffset,
                    kEntityPlayerFireTearExpectedBytes.data(), callback,
                    &g_fallbackEntries[index]};
        case HookId::FamiliarCollision:
            return {"FamiliarCollision", kEntityFamiliarHandleCollisionOffset, kEntityFamiliarHandleCollisionExpectedBytes.data(), callback, &g_fallbackEntries[index]};
        case HookId::NpcCollision:
            return {"NpcCollision", kEntityNpcHandleCollisionOffset, kEntityNpcHandleCollisionExpectedBytes.data(), callback, &g_fallbackEntries[index]};
        case HookId::PlayerCollision:
            return {"PlayerCollision", kEntityPlayerHandleCollisionOffset, kEntityPlayerHandleCollisionExpectedBytes.data(), callback, &g_fallbackEntries[index]};
        case HookId::TearCollision:
            return {"TearCollision", kEntityTearHandleCollisionOffset, kEntityTearHandleCollisionExpectedBytes.data(), callback, &g_fallbackEntries[index]};
        case HookId::ProjectileCollision:
            return {"ProjectileCollision", kEntityProjectileHandleCollisionOffset, kEntityProjectileHandleCollisionExpectedBytes.data(), callback, &g_fallbackEntries[index]};
        case HookId::KnifeCollision:
            return {"KnifeCollision", kEntityKnifeHandleCollisionOffset, kEntityKnifeHandleCollisionExpectedBytes.data(), callback, &g_fallbackEntries[index]};
        case HookId::BombCollision:
            return {"BombCollision", kEntityBombHandleCollisionOffset, kEntityBombHandleCollisionExpectedBytes.data(), callback, &g_fallbackEntries[index]};
        case HookId::ItemPoolGetPill:
            return {"ItemPoolGetPill", kItemPoolGetPillOffset, kItemPoolGetPillExpectedBytes.data(), callback, &g_fallbackEntries[index]};
        case HookId::ItemPoolGetPillEffect:
            return {"ItemPoolGetPillEffect", kItemPoolGetPillEffectOffset, kItemPoolGetPillEffectExpectedBytes.data(), callback, &g_fallbackEntries[index]};
        case HookId::GameDevolveEnemy:
            return {"GameDevolveEnemy", kGameDevolveEnemyOffset, kGameDevolveEnemyExpectedBytes.data(), callback, &g_fallbackEntries[index]};
        case HookId::GameSpawnEx:
            return {"GameSpawnEx", kGameSpawnExOffset, kGameSpawnExExpectedBytes.data(), callback, &g_fallbackEntries[index]};
        case HookId::NpcRender:
            return {"NpcRender", kEntityNpcRenderOffset, kEntityNpcRenderExpectedBytes.data(), callback, &g_fallbackEntries[index]};
        case HookId::UsePill:
            return {"Entity_Player::UsePill", kEntityPlayerUsePillOffset,
                    kEntityPlayerUsePillExpectedBytes.data(), callback, &g_fallbackEntries[index]};
        case HookId::GameExit:
            return {"Game::Exit", kGameExitOffset, kGameExitExpectedBytes.data(), callback,
                    &g_fallbackEntries[index]};
        case HookId::PickupCollision:
            return {"Entity_Pickup::handle_collision", kEntityPickupHandleCollisionOffset,
                    kEntityPickupHandleCollisionExpectedBytes.data(), callback,
                    &g_fallbackEntries[index]};
        case HookId::RoomEntitySpawn:
            return {"Room::spawn_entity", kRoomSpawnEntityOffset,
                    kRoomSpawnEntityExpectedBytes.data(), callback, &g_fallbackEntries[index]};
        case HookId::ImagePcxLoad:
            return {"KAGE::Graphics::ImagePcx::Load", kImagePcxLoadFileOffset,
                    kImagePcxLoadExpectedBytes.data(), callback, &g_fallbackEntries[index]};
        case HookId::ImageManagerLoadFile:
            return {"KAGE::Graphics::ImageManager::LoadImage", kImageManagerLoadFileOffset,
                    kImageManagerLoadFileExpectedBytes.data(), callback, &g_fallbackEntries[index]};
        case HookId::ContentGetMountedFilePath:
            return {"KAGE::Filesys::IContentManager::GetMountedFilePath",
                    kContentManagerGetMountedFilePathOffset,
                    kContentManagerGetMountedFilePathExpectedBytes.data(), callback,
                    &g_fallbackEntries[index]};
        // 模组页搬生产（2026-09-23）：三个入口中继的靶点与 16 字节守卫在 `runtime_constants.hpp`
        // （那段注释写了三条各自为什么要挂、以及探针构建里必须跳过它们）。
        case HookId::MenuGameRender:
            return {"Menu_Game::Render", kMenuGameRenderOffset,
                    kMenuGameRenderExpectedBytes.data(), callback, &g_fallbackEntries[index]};
        case HookId::MenuTitleRender:
            return {"Menu_Title::Render", kMenuTitleRenderOffset,
                    kMenuTitleRenderExpectedBytes.data(), callback, &g_fallbackEntries[index]};
        case HookId::MenuManagerSetState:
            return {"MenuManager::SetState", kMenuManagerSetStateOffset,
                    kMenuManagerSetStateExpectedBytes.data(), callback, &g_fallbackEntries[index]};
        // 批次 147（2026-09-26）：模组 content 加载闸门。靶点是 `ModManager::LoadConfigs` 的
        // **入口**（16 字节守卫见 `runtime_constants.hpp` 那一段取证）；挂在入口是为了
        // "列表已建好、还没读任何一条 +0x139"这个窗口。
        case HookId::ModManagerLoadConfigs:
            return {"ModManager::LoadConfigs", kModManagerLoadConfigsFileOffset,
                    kModManagerLoadConfigsExpectedBytes.data(), callback,
                    &g_fallbackEntries[index]};
        case HookId::Anm2Load:
            // ★ 靶点是 `kSpriteLoadOffset`（`0xC970`）—— 那个函数的 mangled 名就是
            // `ANM2::Load`，与 Lua 侧的 `Sprite:Load` 同一个地址（本批不另立常量）。
            return {"ANM2::Load", kSpriteLoadOffset, kSpriteLoadExpectedBytes.data(), callback,
                    &g_fallbackEntries[index]};
        case HookId::ManagerPresent:
        case HookId::GameStart:
        case HookId::NpcUpdateAi:
        case HookId::HudRender:
        case HookId::RoomConfigLoadStageBinary:
        case HookId::ItemPoolLoadPools:
        case HookId::ConsoleLifecycle:
        case HookId::NativeInputPoll:
        case HookId::NativeRestartInput:
        case HookId::LevelLoadRoom:
        case HookId::LevelInit:
        case HookId::EntityInit:
        case HookId::EntityTearInit:
        case HookId::EntityEffectInit:
        case HookId::GameRerollLevelPickups:
        case HookId::GameRerollLevelCollectibles:
        case HookId::ItemPoolTrinketFirstRandom:
        case HookId::ItemPoolTrinketSelected:
        case HookId::RoomClearAward:
        case HookId::ConsoleUnknownLength:
        case HookId::ConsoleUnknownCompare:
        case HookId::ModManagerUnload:
        case HookId::ItemPoolGetCard:
        case HookId::EntityRemovePointers:
        case HookId::EntityDestructorRemove:
        case HookId::LevelCurseFirstRandom:
        case HookId::LevelCurseEvaluation:
        case HookId::PickupSelection:
        case HookId::PickupSelectionSpecial:
        case HookId::PressurePlateDestructor:
        case HookId::PressurePlateDeletingDestructor:
        case HookId::ProjectileInit:
        case HookId::ProjectileUpdate:
        case HookId::Count:
            // ManagerPresent 的靶点是 PLT 调用点（16 字节含 bl），入口中继无法回放：
            // 它走 GOT 槽改写（spec §4.5），在 M2b 单独实现。
            // GameStart 的靶点是"代码洞里已经放好的中继 + 一个回调槽"，也不走入口中继，
            // 而是 `RelaySlot` 后端（见 `infrastructure/relayslot/`）。
            return {};
    }
    return {};
}

}  // namespace

// 把已实现的回调接进绑定表。必须在安装前调用一次。
// 外部链接：调用点在 hook_manager.cpp，而 g_hookCallbacks 在上面的匿名命名空间里。
//
// 四路回调的形状不同，且都是刻意的：
//   * `ManagerRender`：钩子体已抽成两条后端共用的自由函数，中继回调自己读回退入口；
//   * `ManagerUpdate`：钩子体仍是蹦床里的那个 `Callback`（约 300 行、诊断构建下还有十几处
//     按源码切片断言它的测试），所以中继回调复用同一个 `Callback`，由钩子管理器把回退入口
//     发布进蹦床的 `Orig`（见 hook_manager.cpp 的 `PublishEntryRelayOriginals`）。
//     两条后端跑的是同一个函数，行为一致由构造保证，且不必改写那批守护测试。
//   * `PreGetCollectible` / `RebuildMountPoints`：回调体与旧后端共用同一个派发函数，
//     差别只在"没有覆盖时谁来跑原函数"（旧后端的 IPS 桩自己判断，中继桩不做判断，
//     所以回调自己判 / 自己调回退入口）。
void RegisterEntryRelayCallbacks() noexcept {
    g_hookCallbacks[static_cast<std::size_t>(HookId::PressurePlateAnimationWriter)] =
        engine_memory::AsObject(engine_call::AddressOfFunction(&EntryRelayPressurePlateAnimationCallback));
    g_hookCallbacks[static_cast<std::size_t>(HookId::ManagerUpdate)] =
        engine_memory::AsObject(engine_call::AddressOfFunction(&EntryRelayManagerUpdateCallback));
    g_hookCallbacks[static_cast<std::size_t>(HookId::ManagerRender)] =
        engine_memory::AsObject(engine_call::AddressOfFunction(&EntryRelayManagerRenderCallback));
    g_hookCallbacks[static_cast<std::size_t>(HookId::PreGetCollectible)] =
        engine_memory::AsObject(engine_call::AddressOfFunction(&EntryRelayPreGetCollectibleCallback));
    g_hookCallbacks[static_cast<std::size_t>(HookId::RebuildMountPoints)] =
        engine_memory::AsObject(engine_call::AddressOfFunction(&EntryRelayRebuildMountPointsCallback));
    g_hookCallbacks[static_cast<std::size_t>(HookId::PersistentGameDataSetReadOnly)] =
        engine_memory::AsObject(engine_call::AddressOfFunction(&EntryRelayPersistentGameDataSetReadOnlyCallback));
    // 批次 102 的四个：回调体都在 hook_manager.cpp（与各自的派发函数同处，便于对照注释）。
    g_hookCallbacks[static_cast<std::size_t>(HookId::UseActiveItem)] =
        engine_memory::AsObject(engine_call::AddressOfFunction(&EntryRelayUseActiveItemCallback));
    g_hookCallbacks[static_cast<std::size_t>(HookId::UseCard)] =
        engine_memory::AsObject(engine_call::AddressOfFunction(&EntryRelayUseCardCallback));
    // 批次 390（2026-10-07）：`MC_INPUT_ACTION` 的三处查询入口（回调体在 `hook_manager.cpp`）。
    g_hookCallbacks[static_cast<std::size_t>(HookId::ManagerIsActionPressed)] =
        engine_memory::AsObject(engine_call::AddressOfFunction(&EntryRelayManagerIsActionPressedCallback));
    g_hookCallbacks[static_cast<std::size_t>(HookId::ManagerIsActionTriggered)] =
        engine_memory::AsObject(engine_call::AddressOfFunction(&EntryRelayManagerIsActionTriggeredCallback));
    g_hookCallbacks[static_cast<std::size_t>(HookId::ManagerGetActionValue)] =
        engine_memory::AsObject(engine_call::AddressOfFunction(&EntryRelayManagerGetActionValueCallback));
    g_hookCallbacks[static_cast<std::size_t>(HookId::UsePill)] =
        engine_memory::AsObject(engine_call::AddressOfFunction(&EntryRelayUsePillCallback));
    g_hookCallbacks[static_cast<std::size_t>(HookId::GameExit)] =
        engine_memory::AsObject(engine_call::AddressOfFunction(&EntryRelayGameExitCallback));
    g_hookCallbacks[static_cast<std::size_t>(HookId::PickupCollision)] =
        engine_memory::AsObject(engine_call::AddressOfFunction(&EntryRelayPickupCollisionCallback));
    g_hookCallbacks[static_cast<std::size_t>(HookId::RoomEntitySpawn)] =
        engine_memory::AsObject(engine_call::AddressOfFunction(&RoomFixSpawnCtorInternalCallback));
    // 贴图桥：`.pcx` 不存在而同名 `.png` 存在时，在内存里转码兜底（回调体在 hook_manager.cpp）。
    g_hookCallbacks[static_cast<std::size_t>(HookId::ImagePcxLoad)] =
        engine_memory::AsObject(engine_call::AddressOfFunction(&EntryRelayImagePcxLoadCallback));
    // 贴图桥 v2：真正的拦截点（文件版 LoadImage；兜底在原函数失败时接管）。
    g_hookCallbacks[static_cast<std::size_t>(HookId::ImageManagerLoadFile)] =
        engine_memory::AsObject(engine_call::AddressOfFunction(&EntryRelayImageManagerLoadFileCallback));
    // v4：路径解析层（合成 `.pcx` 路径 ⇒ 引擎自己那条链能走通）。
    g_hookCallbacks[static_cast<std::size_t>(HookId::ContentGetMountedFilePath)] =
        engine_memory::AsObject(engine_call::AddressOfFunction(&EntryRelayContentGetMountedFilePathCallback));
    // 模组页搬生产（2026-09-23）：三个入口中继（回调体在 `source/mod_menu_native.cpp`）。
    g_hookCallbacks[static_cast<std::size_t>(HookId::MenuGameRender)] =
        engine_memory::AsObject(engine_call::AddressOfFunction(&EntryRelayMenuGameRenderCallback));
    g_hookCallbacks[static_cast<std::size_t>(HookId::MenuTitleRender)] =
        engine_memory::AsObject(engine_call::AddressOfFunction(&EntryRelayMenuTitleRenderCallback));
    g_hookCallbacks[static_cast<std::size_t>(HookId::MenuManagerSetState)] =
        engine_memory::AsObject(engine_call::AddressOfFunction(&EntryRelayMenuManagerSetStateCallback));
    // 批次 147（2026-09-26）：模组 content 加载闸门（回调体在 hook_manager.cpp）。
    g_hookCallbacks[static_cast<std::size_t>(HookId::ModManagerLoadConfigs)] =
        engine_memory::AsObject(engine_call::AddressOfFunction(&EntryRelayModManagerLoadConfigsCallback));
    // 批次 363（2026-10-04）：`ANM2::Load` 入口中继（回调体在 `source/anm2_load_override_hook.cpp`）。
    g_hookCallbacks[static_cast<std::size_t>(HookId::Anm2Load)] =
        engine_memory::AsObject(engine_call::AddressOfFunction(&EntryRelayAnm2LoadCallback));
    // 批次 396（2026-10-07）：`MC_ENTITY_TAKE_DMG` 的四条 + `MC_EVALUATE_CACHE`（回调体都在
    // `source/hook_manager.cpp`，四条受伤共用同一个派发函数 `DispatchEntityTakeDamage`）。
    g_hookCallbacks[static_cast<std::size_t>(HookId::EntityTakeDamage)] =
        engine_memory::AsObject(engine_call::AddressOfFunction(&EntryRelayEntityTakeDamageCallback));
    g_hookCallbacks[static_cast<std::size_t>(HookId::EntityPlayerTakeDamage)] =
        engine_memory::AsObject(engine_call::AddressOfFunction(&EntryRelayEntityPlayerTakeDamageCallback));
    g_hookCallbacks[static_cast<std::size_t>(HookId::EntityPickupTakeDamage)] =
        engine_memory::AsObject(engine_call::AddressOfFunction(&EntryRelayEntityPickupTakeDamageCallback));
    g_hookCallbacks[static_cast<std::size_t>(HookId::EntitySlotTakeDamage)] =
        engine_memory::AsObject(engine_call::AddressOfFunction(&EntryRelayEntitySlotTakeDamageCallback));
    g_hookCallbacks[static_cast<std::size_t>(HookId::EvaluateItems)] =
        engine_memory::AsObject(engine_call::AddressOfFunction(&EntryRelayEvaluateItemsCallback));
    // 批次 397（2026-10-07）：补全回调（第 2 批）的三条（回调体都在 `source/hook_manager.cpp`）。
    g_hookCallbacks[static_cast<std::size_t>(HookId::EntityKill)] =
        engine_memory::AsObject(engine_call::AddressOfFunction(&EntryRelayEntityKillCallback));
    g_hookCallbacks[static_cast<std::size_t>(HookId::GameStartStageTransition)] =
        engine_memory::AsObject(engine_call::AddressOfFunction(&EntryRelayGameStartStageTransitionCallback));
    g_hookCallbacks[static_cast<std::size_t>(HookId::EntityPlayerInit)] =
        engine_memory::AsObject(engine_call::AddressOfFunction(&EntryRelayEntityPlayerInitCallback));
    g_hookCallbacks[static_cast<std::size_t>(HookId::RoomConstructor)] =
        engine_memory::AsObject(engine_call::AddressOfFunction(&EntryRelayRoomConstructorCallback));
    g_hookCallbacks[static_cast<std::size_t>(HookId::NpcDeathRemove)] =
        engine_memory::AsObject(engine_call::AddressOfFunction(&EntryRelayNpcDeathRemoveCallback));
    g_hookCallbacks[static_cast<std::size_t>(HookId::GameEnd)] =
        engine_memory::AsObject(engine_call::AddressOfFunction(&EntryRelayGameEndCallback));
    g_hookCallbacks[static_cast<std::size_t>(HookId::FireTear)] =
        engine_memory::AsObject(engine_call::AddressOfFunction(&EntryRelayFireTearCallback));
    g_hookCallbacks[static_cast<std::size_t>(HookId::FamiliarCollision)] = engine_memory::AsObject(engine_call::AddressOfFunction(&EntryRelayFamiliarCollisionCallback));
    g_hookCallbacks[static_cast<std::size_t>(HookId::NpcCollision)] = engine_memory::AsObject(engine_call::AddressOfFunction(&EntryRelayNpcCollisionCallback));
    g_hookCallbacks[static_cast<std::size_t>(HookId::PlayerCollision)] = engine_memory::AsObject(engine_call::AddressOfFunction(&EntryRelayPlayerCollisionCallback));
    g_hookCallbacks[static_cast<std::size_t>(HookId::TearCollision)] = engine_memory::AsObject(engine_call::AddressOfFunction(&EntryRelayTearCollisionCallback));
    g_hookCallbacks[static_cast<std::size_t>(HookId::ProjectileCollision)] = engine_memory::AsObject(engine_call::AddressOfFunction(&EntryRelayProjectileCollisionCallback));
    g_hookCallbacks[static_cast<std::size_t>(HookId::KnifeCollision)] = engine_memory::AsObject(engine_call::AddressOfFunction(&EntryRelayKnifeCollisionCallback));
    g_hookCallbacks[static_cast<std::size_t>(HookId::BombCollision)] = engine_memory::AsObject(engine_call::AddressOfFunction(&EntryRelayBombCollisionCallback));
    g_hookCallbacks[static_cast<std::size_t>(HookId::GameSpawnEx)] = engine_memory::AsObject(engine_call::AddressOfFunction(&EntryRelayGameSpawnExCallback));
    g_hookCallbacks[static_cast<std::size_t>(HookId::NpcRender)] = engine_memory::AsObject(engine_call::AddressOfFunction(&EntryRelayNpcRenderCallback));
    g_hookCallbacks[static_cast<std::size_t>(HookId::ItemPoolGetPill)] = engine_memory::AsObject(engine_call::AddressOfFunction(&EntryRelayItemPoolGetPillCallback));
    g_hookCallbacks[static_cast<std::size_t>(HookId::ItemPoolGetPillEffect)] = engine_memory::AsObject(engine_call::AddressOfFunction(&EntryRelayItemPoolGetPillEffectCallback));
    g_hookCallbacks[static_cast<std::size_t>(HookId::GameDevolveEnemy)] = engine_memory::AsObject(engine_call::AddressOfFunction(&EntryRelayGameDevolveEnemyCallback));
}

BindingVerdict EvaluateEntryRelayBinding(const EntryRelayBinding& binding,
                                         const HookTarget& target,
                                         std::uintptr_t* outTarget) noexcept {
    if (outTarget == nullptr || binding.offset == 0 || binding.expectedEntry16 == nullptr ||
        binding.callback == nullptr || binding.fallbackEntry == nullptr) {
        return BindingVerdict::Rejected;                  // 含"回调未接线"，必须响亮失败
    }
    // 地址判定复用头文件里的 constexpr 版（同一份恒等逻辑，编译期已自证）。
    if (!IsHookableEntryAddress(target.base, target.codeSize, binding.offset, outTarget)) {
        return BindingVerdict::Rejected;                  // 空/回绕/越界/对齐/跨页
    }
    return BindingVerdict::Ok;
}

std::uintptr_t EntryRelayFallbackEntry(HookId id) noexcept {
    const auto index = static_cast<std::size_t>(id);
    return index < kHookIdCount ? __atomic_load_n(&g_fallbackEntries[index],__ATOMIC_ACQUIRE) : 0;
}

namespace {
struct EntryPublicationContext { HookId id; std::uintptr_t* slot; };
bool PublishEntryOriginal(std::uintptr_t original,void* opaque) noexcept {
    const auto& context = *static_cast<const EntryPublicationContext*>(opaque);
    if (context.id == HookId::ManagerUpdate && !PublishManagerUpdateEntryRelayOriginal(original))
        return false;
    __atomic_store_n(context.slot,original,__ATOMIC_RELEASE);
    return true;
}
}

Status EntryRelayHookAdapter::Install(HookId id, const HookTarget& target) noexcept {
    // 顶部清零：下面两条早退（InvalidArgument / InvalidState）不是 entry_relay 失败，
    // 不清零会返回上一次成功安装留下的陈旧失败码；Task 4 的路由要转发它、Task 5 要读它。
    lastFailure_ = 0;
    // ★★ 批次 359：`RebuildMountPoints` 需要额外留痕 —— 它是"引擎重建挂载点表之后
    //   把模组挂载点补回来"的唯一一环，而 357/358 记的是**另一条死代码路径**上的结果。
    // ★★ 批次 365（2026-10-05）：`Anm2Load` 同样必须留痕。批次 363 只**定义并声明**了
    //   `NoteAnm2LoadRelayInstalled`、却**一个调用点都没有** ⇒ 读数里"中继装上没有"那一格
    //   恒写"未试"，**即使入口早已是补丁**（2026-10-05 01:24 的真机读数当场对出来的自相矛盾）。
    //   一个会撒谎的判据比没有判据更坏：它会把"装上了"读成"没装"。
    const auto noteIfTracked = [id](bool installed, unsigned failure) {
        if (id == isaac::runtime::HookId::RebuildMountPoints) {
            isaac::runtime::bridge::NoteRebuildMountPointsEntryRelay(installed, failure);
        } else if (id == isaac::runtime::HookId::Anm2Load) {
            isaac::runtime::bridge::NoteAnm2LoadRelayInstalled(installed, failure);
        }
    };
    const auto index = static_cast<std::size_t>(id);
    if (index >= kHookIdCount) {
        noteIfTracked(false, 1U);
        return Status{StatusCode::InvalidArgument};
    }
    if (g_installedEntries[index].load(std::memory_order_acquire) == 4) {
        lastFailure_ = 4;  // 写入校验失败不可恢复，另一安装路径同样不得重试。
        noteIfTracked(false, 4);
        return Status{StatusCode::Rejected};
    }
    if (installed_[index]) {
        noteIfTracked(true, 0U);  // 之前就装上了
        return Status{StatusCode::InvalidState};
    }
    if (id == HookId::RoomEntitySpawn) {
        // BindingOf旧Roomspawn台账留作历史；新callback是内部上下文ABI，不能接到旧入口。
        lastFailure_ = 1U;
        return Status{StatusCode::Rejected};
    }
    const EntryRelayBinding binding = BindingOf(id);
    std::uintptr_t address = 0;
    if (EvaluateEntryRelayBinding(binding, target, &address) != BindingVerdict::Ok) {
        lastFailure_ = 1U;  // 纯判定拒绝（地址/边界/对齐/回调未接线）
        noteIfTracked(false, 1U);
        return Status{StatusCode::Rejected};
    }
    if(id==HookId::UseActiveItem&&!TryInstallUseItemNativeBoundaries(target)){
        lastFailure_=1U;noteIfTracked(false,1U);return Status{StatusCode::Rejected};
    }
    if(id==HookId::EntityPlayerTakeDamage&&!TryInstallPlayerDamageBoundary(target)){
        lastFailure_=1U;noteIfTracked(false,1U);return Status{StatusCode::Rejected};
    }
    std::uintptr_t originalEntry = 0;
    EntryPublicationContext publication{id,binding.fallbackEntry};
    if (!isaac::runtime::relay::TryInstallEntryRelayWithPublisher(
            address, binding.expectedEntry16,
            engine_memory::AddressOf(binding.callback), PublishEntryOriginal, &publication, &originalEntry)) {
        const std::uint32_t failure = isaac::runtime::relay::LastFailure();
        lastFailure_ = failure;
        if (failure == 4) {
            g_installedEntries[index].store(4, std::memory_order_release);
        }
        noteIfTracked(false, failure);
        // 失败分两类，处置口径不同（`entry_relay` 的契约）：
        //   * `EntryRelayFailure` 的 1/2/3/5（InvalidAddress/EntryMismatch/ArenaExhausted/
        //     PcRelativeInstruction）都在**任何写入之前**返回，目标字节保持原样；
        //   * `EntryRelayFailure::WriteVerifyFailed`(4) 表示**已经写过**但用只读别名读回不一致：
        //     不可恢复，绝不允许重试（重试等于把一个可能已被改写的入口再写一次）。
        // 两者都报 Rejected，由调用方（Task 4 的路由）决定是否停机。
        return Status{StatusCode::Rejected};
    }
    // 回退已在目标入口可达前发布；这里仅登记安装结果。
    installed_[index] = true;
    g_installedEntries[index].store(1, std::memory_order_release);
    lastFailure_ = 0;
    noteIfTracked(true, 0U);
    return Status::Ok();
}

bool EntryRelayHookAdapter::IsInstalled(HookId id) const noexcept {
    const auto index = static_cast<std::size_t>(id);
    return index < kHookIdCount && installed_[index];
}

std::uint32_t EntryRelayHookAdapter::LastFailureCode() const noexcept { return lastFailure_; }

// ============================================================================
// 批次 385（2026-10-06）：**早装**个别入口中继 —— 设计与理由见头文件那段注释
// ============================================================================
//
// 与 `EntryRelayHookAdapter::Install` 的关系：**故意的两条平行路径**，靠
// `EntryRelayInstalledEarly()` 让生产安装流程"跳过已早装的那几条"来避免重复安装。
// 不共用一个实例的原因写在头文件里（实例状态不共享 ⇒ 会再装一次 ⇒ `EntryMismatch`）。
namespace {

//: "已经被**早装**过"的挂点位图。只有本 TU 写；`hook_manager.cpp` 通过外部链接的
//: `EntryRelayInstalledEarly()` 查。
bool g_earlyInstalledEntries[kHookIdCount]{};

}  // namespace

bool TryInstallEntryRelayEarly(HookId id, const HookTarget& target,
                               std::uintptr_t* outEntry) noexcept {
    const auto index = static_cast<std::size_t>(id);
    if (index >= kHookIdCount || id == HookId::RoomEntitySpawn ||
        outEntry == nullptr || g_earlyInstalledEntries[index]) {
        return false;
    }
    const EntryRelayBinding binding = BindingOf(id);
    std::uintptr_t address = 0;
    if (EvaluateEntryRelayBinding(binding, target, &address) != BindingVerdict::Ok) {
        return false;   // 纯判定拒绝（地址/边界/对齐/回调未接线）—— 不写任何字节
    }
    if(id==HookId::UseActiveItem&&!TryInstallUseItemNativeBoundaries(target))return false;
    if(id==HookId::EntityPlayerTakeDamage&&!TryInstallPlayerDamageBoundary(target))return false;
    std::uintptr_t originalEntry = 0;
    EntryPublicationContext publication{id,binding.fallbackEntry};
    if (!isaac::runtime::relay::TryInstallEntryRelayWithPublisher(
            address, binding.expectedEntry16,
            engine_memory::AddressOf(binding.callback), PublishEntryOriginal, &publication, &originalEntry)) {
        return false;   // 与 `Install` 同一口径：失败原样返回，由调用方决定怎么办
    }
    // ★ 顺序与 `TryInstallEntryRelay` 的内部纪律一致：**先把回退入口公布出去，再置"已装"**
    //   （口径 = "回调可达 ⇒ 原函数入口一定有效"）。
    *outEntry = originalEntry;
    g_earlyInstalledEntries[index] = true;
    // ★ 记账**照旧走原来那套**（`EntryRelayHookAdapter::Install` 里也是这么记的）——
    //   否则读数里 `g_Anm2LoadOverrideState.relayState` 会显示"未试"，
    //   而入口其实早就被补丁了：**一个会撒谎的判据比没有判据更坏**（批次 365 的教训）。
    if (id == HookId::Anm2Load) {
        isaac::runtime::bridge::NoteAnm2LoadRelayInstalled(true, 0U);
    }
    return true;
}

bool EntryRelayInstalledEarly(HookId id) noexcept {
    const auto index = static_cast<std::size_t>(id);
    return index < kHookIdCount && g_earlyInstalledEntries[index];
}

bool EntryRelayInstalled(HookId id) noexcept {
    const auto index = static_cast<std::size_t>(id);
    return index < kHookIdCount &&
           g_installedEntries[index].load(std::memory_order_acquire) == 1;
}

}  // namespace isaac::runtime
