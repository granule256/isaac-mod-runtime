#include "infrastructure/relay/entry_relay_hook_adapter.hpp"

#include "relay/entry_relay.hpp"       // 侵入核心（source/relay/entry_relay.hpp）
#include "runtime_constants.hpp"       // M0 台账
#include "relay/smart_pointer_shim.hpp"  // v2：sret 返回值垫片（source/relay）

namespace isaac::runtime {
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

// --- 回调面补齐（批次 102）：四个事件靶点 ---------------------------------------
//
// 形状各自不同，按目标函数的 ABI 逐字写（依据见 `runtime_constants.hpp` 那一段注释）：
//   * `UseActiveItem`：`(this /*x0*/, 道具 /*w1*/, UseFlags /*w2*/, ActiveSlot /*w3*/,
//     CustomVarData /*w4*/)`；入口派发 `MC_PRE_USE_ITEM`、原函数返回后派发 `MC_USE_ITEM`。
//   * `UseCard`：`(this, 卡 /*w1*/, UseFlags /*w2*/)`。
//   * `UsePill`：`(this, 药丸效果 /*w1*/, 药丸颜色 /*w2*/, UseFlags /*w3*/)`。
//   * `Game::Exit`：`(this /*x0*/, 要不要存档 /*w1*/)`。
extern "C" void EntryRelayUseActiveItemCallback(void* player, std::uint32_t item,
                                                std::uint32_t useFlags, std::int32_t activeSlot,
                                                std::int32_t customVarData);
extern "C" void EntryRelayUseCardCallback(void* player, std::uint32_t card,
                                          std::uint32_t useFlags);
extern "C" void EntryRelayUsePillCallback(void* player, std::uint32_t pillEffect,
                                          std::uint32_t pillColor, std::uint32_t useFlags);
extern "C" void EntryRelayGameExitCallback(void* game, std::uint32_t shouldSave);

// 批次 103：`(掉落物 /*x0*/, 碰它的实体 /*x1*/, low /*w2*/)`。返回值决定要不要跑原函数
// （PC 三态，见 `runtime_constants.hpp` 里那个靶点的注释）。
extern "C" void EntryRelayPickupCollisionCallback(void* pickup, void* collider,
                                                  std::uint32_t low);

// 批次 104：`Room::spawn_entity(unsigned GridIndex, RoomConfig::Entry const&, unsigned Seed,
// Entity**, bool)`。前三个实参都要转发给 `MC_PRE_ROOM_ENTITY_SPAWN`（Type/Variant/SubType 从
// 第二个实参的**前 12 字节**读，见 `runtime_constants.hpp` 里那段证据）。
extern "C" void EntryRelayRoomEntitySpawnCallback(void* room, std::uint32_t gridIndex,
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

// `RegisterEntryRelayCallbacks` 定义在匿名命名空间之外（外部链接）：调用点在
// hook_manager.cpp，而 g_hookCallbacks 在本 TU 的匿名命名空间里。

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
        case HookId::UseActiveItem:
            return {"Entity_Player::UseActiveItem", kEntityPlayerUseActiveItemOffset,
                    kEntityPlayerUseActiveItemExpectedBytes.data(), callback,
                    &g_fallbackEntries[index]};
        case HookId::UseCard:
            return {"Entity_Player::UseCard", kEntityPlayerUseCardOffset,
                    kEntityPlayerUseCardExpectedBytes.data(), callback, &g_fallbackEntries[index]};
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
        case HookId::ManagerPresent:
        case HookId::GameStart:
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
    g_hookCallbacks[static_cast<std::size_t>(HookId::ManagerUpdate)] =
        reinterpret_cast<void*>(&EntryRelayManagerUpdateCallback);
    g_hookCallbacks[static_cast<std::size_t>(HookId::ManagerRender)] =
        reinterpret_cast<void*>(&EntryRelayManagerRenderCallback);
    g_hookCallbacks[static_cast<std::size_t>(HookId::PreGetCollectible)] =
        reinterpret_cast<void*>(&EntryRelayPreGetCollectibleCallback);
    g_hookCallbacks[static_cast<std::size_t>(HookId::RebuildMountPoints)] =
        reinterpret_cast<void*>(&EntryRelayRebuildMountPointsCallback);
    // 批次 102 的四个：回调体都在 hook_manager.cpp（与各自的派发函数同处，便于对照注释）。
    g_hookCallbacks[static_cast<std::size_t>(HookId::UseActiveItem)] =
        reinterpret_cast<void*>(&EntryRelayUseActiveItemCallback);
    g_hookCallbacks[static_cast<std::size_t>(HookId::UseCard)] =
        reinterpret_cast<void*>(&EntryRelayUseCardCallback);
    g_hookCallbacks[static_cast<std::size_t>(HookId::UsePill)] =
        reinterpret_cast<void*>(&EntryRelayUsePillCallback);
    g_hookCallbacks[static_cast<std::size_t>(HookId::GameExit)] =
        reinterpret_cast<void*>(&EntryRelayGameExitCallback);
    g_hookCallbacks[static_cast<std::size_t>(HookId::PickupCollision)] =
        reinterpret_cast<void*>(&EntryRelayPickupCollisionCallback);
    g_hookCallbacks[static_cast<std::size_t>(HookId::RoomEntitySpawn)] =
        reinterpret_cast<void*>(&EntryRelayRoomEntitySpawnCallback);
    // 贴图桥：`.pcx` 不存在而同名 `.png` 存在时，在内存里转码兜底（回调体在 hook_manager.cpp）。
    g_hookCallbacks[static_cast<std::size_t>(HookId::ImagePcxLoad)] =
        reinterpret_cast<void*>(&EntryRelayImagePcxLoadCallback);
    // 贴图桥 v2：真正的拦截点（文件版 LoadImage；兜底在原函数失败时接管）。
    g_hookCallbacks[static_cast<std::size_t>(HookId::ImageManagerLoadFile)] =
        reinterpret_cast<void*>(&EntryRelayImageManagerLoadFileCallback);
    // v4：路径解析层（合成 `.pcx` 路径 ⇒ 引擎自己那条链能走通）。
    g_hookCallbacks[static_cast<std::size_t>(HookId::ContentGetMountedFilePath)] =
        reinterpret_cast<void*>(&EntryRelayContentGetMountedFilePathCallback);
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
    return index < kHookIdCount ? g_fallbackEntries[index] : 0;
}

Status EntryRelayHookAdapter::Install(HookId id, const HookTarget& target) noexcept {
    // 顶部清零：下面两条早退（InvalidArgument / InvalidState）不是 entry_relay 失败，
    // 不清零会返回上一次成功安装留下的陈旧失败码；Task 4 的路由要转发它、Task 5 要读它。
    lastFailure_ = 0;
    const auto index = static_cast<std::size_t>(id);
    if (index >= kHookIdCount) {
        return Status{StatusCode::InvalidArgument};
    }
    if (installed_[index]) {
        return Status{StatusCode::InvalidState};
    }
    const EntryRelayBinding binding = BindingOf(id);
    std::uintptr_t address = 0;
    if (EvaluateEntryRelayBinding(binding, target, &address) != BindingVerdict::Ok) {
        lastFailure_ = 1U;  // 纯判定拒绝（地址/边界/对齐/回调未接线）
        return Status{StatusCode::Rejected};
    }
    std::uintptr_t originalEntry = 0;
    if (!isaac::runtime::relay::TryInstallEntryRelay(
            address, binding.expectedEntry16,
            reinterpret_cast<std::uintptr_t>(binding.callback), &originalEntry)) {
        const std::uint32_t failure = isaac::runtime::relay::LastFailure();
        lastFailure_ = failure;
        // 失败分两类，处置口径不同（`entry_relay` 的契约）：
        //   * `EntryRelayFailure` 的 1/2/3/5（InvalidAddress/EntryMismatch/ArenaExhausted/
        //     PcRelativeInstruction）都在**任何写入之前**返回，目标字节保持原样；
        //   * `EntryRelayFailure::WriteVerifyFailed`(4) 表示**已经写过**但用只读别名读回不一致：
        //     不可恢复，绝不允许重试（重试等于把一个可能已被改写的入口再写一次）。
        // 两者都报 Rejected，由调用方（Task 4 的路由）决定是否停机。
        return Status{StatusCode::Rejected};
    }
    *binding.fallbackEntry = originalEntry;
    installed_[index] = true;
    lastFailure_ = 0;
    return Status::Ok();
}

bool EntryRelayHookAdapter::IsInstalled(HookId id) const noexcept {
    const auto index = static_cast<std::size_t>(id);
    return index < kHookIdCount && installed_[index];
}

std::uint32_t EntryRelayHookAdapter::LastFailureCode() const noexcept { return lastFailure_; }

}  // namespace isaac::runtime
