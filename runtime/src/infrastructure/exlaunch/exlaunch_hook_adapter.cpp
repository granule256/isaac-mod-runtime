#include "infrastructure/exlaunch/exlaunch_hook_adapter.hpp"

#include "hook_manager.hpp"
// 只为了让"重建挂载点中继装上没有"留成可读的一格（见下面 `HookId::RebuildMountPoints`）。
#include "image_pcx_bridge_hook.hpp"

#include <algorithm>
#include <cstring>

namespace isaac::runtime {
namespace {

TargetModule ModuleOf(const HookTarget& target) noexcept {
    TargetModule module{};
    module.base = target.base;
    module.textSize = target.codeSize;
    module.size = target.imageSize != 0 ? target.imageSize : target.codeSize;
    const std::size_t buildIdBytes = std::min(module.buildId.size(), target.buildId.size());
    std::memcpy(module.buildId.data(), target.buildId.data(), buildIdBytes);
    return module;
}

} // namespace

Status ExlaunchHookAdapter::Install(HookId id, const HookTarget& target) noexcept {
    const std::size_t index = static_cast<std::size_t>(id);
    if (index >= kHookCount || target.base == 0 || target.codeSize == 0) {
        return Status{StatusCode::InvalidArgument};
    }
    if (installed_[index]) {
        return Status{StatusCode::InvalidState};
    }

    const TargetModule module = ModuleOf(target);
    bool ok = false;
    switch (id) {
        case HookId::ManagerUpdate:
            ok = TryInstallManagerUpdateHook(module) == HookInstallResult::Success;
            break;
        case HookId::ManagerRender:
            ok = TryInstallManagerRenderHook(module) == RenderHookInstallResult::Success;
            break;
        case HookId::PreGetCollectible:
            ok = TryInstallPreGetCollectibleRelay(module) ==
                 PreGetCollectibleRelayInstallResult::Success;
            break;
        case HookId::ManagerPresent:
            ok = TryInstallManagerPresentRelay(module) == RenderPresentRelayInstallResult::Success;
            break;
        case HookId::RebuildMountPoints:
            // 这个安装器直接返回布尔值（真=已验证并发布）。
            ok = TryInstallRebuildMountPointsRelay(module);
            // 把结果留成可读的一格。起因：346 起读数里只有"重建中继跑过 0 次"，
            //   而"**没跑**"与"**没装上**"是两件事 —— 后者意味着引擎一旦重建挂载点表，
            //   模组挂载点就再也不会被恢复（356 的检查点证明挂载点确实在中途消失了）。
            isaac::runtime::bridge::NoteRebuildMountPointsRelayInstalled(ok);
            break;
        case HookId::GameStart:
            // 开局走"代码洞中继 + 回调槽"（`RelaySlot` 后端），旧 IPS 蹦床这边不接。
            return Status{StatusCode::InvalidArgument};
        // 的四个事件靶点只走零占洞入口中继（`kHookCatalog` 里的后端就是 `EntryRelay`）
        // ⇒ 路由不会把它们送到这个旧后端。这里显式给出同样的答复，而不是让 `-Wswitch` 判错：
        // "这个后端不支持这个挂点"是要写出来的事实，不是编译噪音。
        case HookId::UseActiveItem:
        case HookId::UseCard:
        case HookId::UsePill:
        case HookId::GameExit:
        case HookId::PickupCollision:
        case HookId::RoomEntitySpawn:
        // 贴图桥只走零占洞入口中继（`EntryRelay`）⇒ 旧 IPS 后端不支持，与上面同口径。
        case HookId::ImagePcxLoad:
        case HookId::ImageManagerLoadFile:
        case HookId::ContentGetMountedFilePath:
        // `MC_INPUT_ACTION` 的三条查询中继同理 —— 只走零占洞入口中继
        // （`kHookCatalog` 里的后端是 `EntryRelay`），旧 IPS 蹦床这边不接。
        case HookId::ManagerIsActionPressed:
        case HookId::ManagerIsActionTriggered:
        case HookId::ManagerGetActionValue:
        // （模组页搬生产）的三个入口中继同理：只走 `EntryRelay`。
        case HookId::MenuGameRender:
        case HookId::MenuTitleRender:
        case HookId::MenuManagerSetState:
        // （禁成就）：闸门挂在 `SetReadOnly` 上，同样只走零占洞入口中继（`EntryRelay`）。
        case HookId::PersistentGameDataSetReadOnly:
        // （模组 content 加载闸门）：`ModManager::LoadConfigs` 也只走 `EntryRelay`。
        case HookId::ModManagerLoadConfigs:
        // （`ANM2::Load` 入口中继）：同样只走零占洞入口中继。
        case HookId::Anm2Load:
        // `MC_ENTITY_TAKE_DMG` 的四条 + `MC_EVALUATE_CACHE` 同理 ——
        // 只走零占洞入口中继，旧 IPS 蹦床这边不接。
        case HookId::EntityTakeDamage:
        case HookId::EntityPlayerTakeDamage:
        case HookId::EntityPickupTakeDamage:
        case HookId::EntitySlotTakeDamage:
        case HookId::EvaluateItems:
        // 补全回调（第 2 批）的三条同理 —— 只走零占洞入口中继。
        case HookId::EntityKill:
        case HookId::NpcDeathRemove:
        case HookId::GameEnd:
        case HookId::FireTear:
        case HookId::FamiliarCollision:
        case HookId::NpcCollision:
        case HookId::PlayerCollision:
        case HookId::TearCollision:
        case HookId::ProjectileCollision:
        case HookId::KnifeCollision:
        case HookId::BombCollision:
        case HookId::ItemPoolGetPill:
        case HookId::ItemPoolGetPillEffect:
        case HookId::GameDevolveEnemy:
        case HookId::NpcRender:
            return Status{StatusCode::InvalidArgument};
        case HookId::GameSpawnEx:
        case HookId::NpcUpdateAi:
        case HookId::HudRender:
        case HookId::RoomConfigLoadStageBinary:
        case HookId::ItemPoolLoadPools:
        case HookId::ConsoleLifecycle:
        case HookId::NativeInputPoll:
        case HookId::NativeRestartInput:
        case HookId::LevelLoadRoom:
        case HookId::LevelInit:
        case HookId::GameRerollLevelPickups:
        case HookId::GameRerollLevelCollectibles:
        case HookId::EntityTearInit:
        case HookId::EntityEffectInit:
        case HookId::EntityPickupInit:
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
        case HookId::PressurePlateAnimationWriter:
        case HookId::PressurePlateDestructor:
        case HookId::PressurePlateDeletingDestructor:
        case HookId::ProjectileInit:
        case HookId::EntityPlayerInit:
        case HookId::RoomConstructor:
        case HookId::EntityInit:
        case HookId::GameStartStageTransition:
        case HookId::ProjectileUpdate:
        case HookId::Count:
            return Status{StatusCode::InvalidArgument};
    }
    if (!ok) {
        return Status{StatusCode::Rejected};
    }
    installed_[index] = true;
    return Status::Ok();
}

bool ExlaunchHookAdapter::IsInstalled(HookId id) const noexcept {
    const std::size_t index = static_cast<std::size_t>(id);
    if (index >= kHookCount) {
        return false;
    }
    return installed_[index];
}

} // namespace isaac::runtime
