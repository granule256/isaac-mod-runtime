#include "infrastructure/gotslot/got_slot_hook_adapter.hpp"

#include "hook_manager.hpp"
#include "entity_remove_hook.hpp"
#include "entity_init_hook.hpp"
#include "mod_unload_hook.hpp"
#include "card_hook.hpp"
#include "mod_room_hook.hpp"
#include "mod_itempool_hook.hpp"
#include "console_lifecycle_hook.hpp"
#include "input_poll_hook.hpp"
#include "infrastructure/gotslot/level_pickup_reroll_hook.hpp"
#include "infrastructure/gotslot/restart_input_hook.hpp"

#include <algorithm>
#include <cstring>

namespace isaac::runtime {
namespace {

// 端口类型 → 安装器要的模块描述。与 `exlaunch_hook_adapter.cpp` 里那份换算是同一套口径
// （`HookTarget` 与 `TargetModule` 字段一一对应），这里为了不动那个已冻结的适配器而各自持一份。
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

Status GotSlotHookAdapter::Install(HookId id, const HookTarget& target) noexcept {
    const std::size_t index = static_cast<std::size_t>(id);
    if (index >= kHookIdCount || target.base == 0 || target.codeSize == 0) {
        return Status{StatusCode::InvalidArgument};
    }
    if (installed_[index]) {
        return Status{StatusCode::InvalidState};
    }
    if (id == HookId::EntityInit || id == HookId::EntityTearInit || id == HookId::EntityEffectInit ||
        id == HookId::EntityPickupInit) {
        const auto result = InstallEntityInitPointerHooks(id, target);
        if (result.ok()) installed_[index] = true;
        return result;
    }
    // Present、原生HUD与NPC内部AI等数据槽；别的挂点由路由表交给各自的适配器。
    // 走到这里的其它 `HookId` 是配置错误，**响亮失败**而不是静默成功。
    if (id == HookId::NativeInputPoll) {
        const auto result = InstallNativeInputPollHook(target);
        if (result.ok()) installed_[index] = true;
        return result;
    }
    if (id == HookId::NativeRestartInput) {
        const auto result = InstallNativeRestartInputHook(target);
        if (result.ok()) installed_[index] = true;
        return result;
    }
    if (id == HookId::ConsoleLifecycle) {
        const auto result=InstallConsoleLifecycleHook(target);
        if(result.ok())installed_[index]=true;
        return result;
    }
    if (id == HookId::LevelLoadRoom) {
        const auto result=InstallLevelRoomPointerHook(target);
        if(result.ok())installed_[index]=true;
        return result;
    }
    if (id == HookId::LevelInit) {
        const auto result=InstallLevelInitPointerHook(target);
        if(result.ok())installed_[index]=true;
        return result;
    }
    if (id == HookId::GameRerollLevelPickups || id == HookId::GameRerollLevelCollectibles) {
        const auto result=InstallLevelPickupRerollPointerHook(id,target);
        if(result.ok())installed_[index]=true;
        return result;
    }
    if (id == HookId::ItemPoolLoadPools) {
        const auto result=InstallModItemPoolPointerHook(target);
        if(result.ok())installed_[index]=true;
        return result;
    }
    if (id == HookId::RoomConfigLoadStageBinary) {
        const auto result=InstallModRoomPointerHook(target);
        if(result.ok())installed_[index]=true;
        return result;
    }
    if (id == HookId::ItemPoolGetCard) {
        const auto result=InstallCardPointerHook(target);
        if(result.ok())installed_[index]=true;
        return result;
    }
    if (id == HookId::ModManagerUnload) {
        const auto result=InstallModUnloadPointerHook(target);
        if(result.ok())installed_[index]=true;
        return result;
    }
    if (id == HookId::EntityRemovePointers) {
        const auto result = InstallEntityRemovePointerHooks(target);
        if (result.ok()) installed_[index] = true;
        return result;
    }
    if (id != HookId::ManagerPresent && id != HookId::NpcUpdateAi && id != HookId::HudRender) {
        return Status{StatusCode::Rejected};
    }
    const auto result = id == HookId::HudRender
        ? TryInstallHudRenderGotSlot(ModuleOf(target))
        : id == HookId::NpcUpdateAi
        ? TryInstallNpcUpdateAiGotSlot(ModuleOf(target))
        : TryInstallManagerPresentGotSlot(ModuleOf(target));
    if (result !=
        RenderPresentRelayInstallResult::Success) {
        return Status{StatusCode::Rejected};
    }
    installed_[index] = true;
    return Status::Ok();
}

bool GotSlotHookAdapter::IsInstalled(HookId id) const noexcept {
    const std::size_t index = static_cast<std::size_t>(id);
    return index < kHookIdCount && installed_[index];
}

} // namespace isaac::runtime
