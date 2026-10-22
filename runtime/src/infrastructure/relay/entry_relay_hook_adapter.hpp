#pragma once

#include "infrastructure/relay/entry_relay_binding.hpp"
#include "ports/hook_port.hpp"

#include <array>
#include <cstddef>
#include <cstdint>

namespace isaac::runtime {

// 零占洞后端：中继体写进本模块自己的竞技场（`source/relay/entry_relay.*`），
// 只改写目标函数入口 16 字节，**不占用游戏映像的任何字节**，因此不再需要
// Atmosphere 的 IPS 静态中继，也不再与金手指抢地址。
class EntryRelayHookAdapter final : public IHookPort {
public:
    [[nodiscard]] Status Install(HookId id, const HookTarget& target) noexcept override;
    [[nodiscard]] bool IsInstalled(HookId id) const noexcept override;

    // 自有诊断接口（不进端口）：最近一次 entry_relay 失败码，0 表示成功。
    [[nodiscard]] std::uint32_t LastFailureCode() const noexcept;

private:
    std::array<bool, kHookIdCount> installed_{};
    std::uint32_t lastFailure_{0};
};

// 安装前把已实现的回调接进入口中继绑定表（Task 4）。定义在同模块的另一 TU，
// 这里给外部链接声明；调用点在 hook_manager.cpp（安装前调用一次）。
void RegisterEntryRelayCallbacks() noexcept;

// ============================================================================
// ★★★ 批次 385（2026-10-06）：**早装**个别入口中继（目前只用于"资源类"那两条）
// ============================================================================
//
// ## 为什么需要它（真机读数定案，别再靠推断）
//
// `dist/gdb-read-20261006-1537-relay-verdict.txt`：`ANM2::Load` 中继**首次被调用比 `Game::Init`
// 晚 6.5 秒**（tick 4,131,309,069 vs 4,006,329,802），而引擎读 `gfx/ui/minimap1.anm2` 就在
// `Game::Init` 里（`Game::Init+0x340` → `Minimap::Init` → `ANM2::Load`）
// ⇒ **那次读没走我们的中继** ⇒ 引擎按本体解析 ⇒ 本体那份被钉进它自己的动画缓存
// ⇒ 之后我们答得再对也改不掉（模组画红字）。
//
// 治本 = 把这两条的安装**提前到 worker 的前置步骤**（与 `Game::Init` 入口中继同一批，
// 见 `runtime_entry.cpp` 的 `RunEarlyModMountPrelude`）：
//   * `HookId::Anm2Load`                   —— "发现动画缓存里压着本体旧条目"的那一环；
//   * `HookId::ContentGetMountedFilePath`  —— "回答模组那份"的那一环（资源层重定向寄生在它身上）。
//
// ## 为什么不直接复用 `EntryRelayHookAdapter`
//
// 它的 `installed_` 是**实例状态**，而生产那套安装用的是另一个实例 ⇒ 两边不共享
// ⇒ 生产那边会**再装一次**同一个入口 ⇒ 按入口中继的契约必然 `EntryMismatch`
// （见 `hook_manager.cpp` 里"同一入口装第二次必然 EntryMismatch"那段注释）。
// ⇒ 所以这里**直接调 `relay::TryInstallEntryRelay`**，并把"早装过"记进本模块的位图；
// 生产安装流程靠 `EntryRelayInstalledEarly(id)` 在**跳过判据**里让开这两条。
//
// 失败**不抛错、不半装**：任一步不成立就返回 false（调用方原样继续 ⇒ 退回"晚装"的旧行为）。
bool TryInstallEntryRelayEarly(HookId id, const HookTarget& target,
                               std::uintptr_t* outEntry) noexcept;
bool EntryRelayInstalledEarly(HookId id) noexcept;
// 跨安装路径的成功状态；回退地址已公布不等于入口写入验证成功。
bool EntryRelayInstalled(HookId id) noexcept;

} // namespace isaac::runtime
