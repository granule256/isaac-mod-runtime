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
    // 批次 104（第 2 期）：房间生成实体（`MC_PRE_ROOM_ENTITY_SPAWN`）。
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
    Count,
};

inline constexpr std::size_t kHookIdCount = static_cast<std::size_t>(HookId::Count);

// 侵入方式（策略标签）。具体怎么做由基础设施里的适配器实现：
//   LegacyIps  —— Atmosphere 静态中继 IPS + exlaunch 蹦床（历史路径）
//   EntryRelay —— 改写目标函数入口的 16 字节，跳到我们模块里的中继（零占洞）
//   GotSlot    —— 只改写该函数所用 PLT 桩读的那条 GOT 槽（零代码字节）
//   RelaySlot  —— 引擎侧的中继代码（由 IPS 放进游戏模块的代码洞）在"原调用返回之后"
//                 从一个**回调槽**里取出函数指针来调用；本后端只负责把我们的回调指针
//                 写进那个槽（同样零代码字节）。目前只有 `GameStart` 走这条路。
enum class HookBackend : std::uint8_t { LegacyIps, EntryRelay, GotSlot, RelaySlot };

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
    {HookId::RoomEntitySpawn, "RoomEntitySpawn", HookBackend::EntryRelay, false},
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
