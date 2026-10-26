#pragma once

#include "application/mod/manifest_service.hpp"
#include "domain/mod/mod_toggle_state.hpp"
#include "domain/runtime/status.hpp"
#include "ports/save_file_port.hpp"

#include <atomic>
#include <cstddef>
#include <string_view>

namespace isaac::runtime {

//: ★★ 批次 427：两个读数（**外部链接**，读数工具按符号名读）。
//:   * `g_ModTogglePrunedEntries` = 开机时清掉的"死条目"累计（模组已删/改名 ⇒ 清掉它占的格）；
//:   * `g_ModToggleCapacityRejections` = ★ **因名单满而被拒的开关次数** ——
//:     用户报的"关不掉"当年就是**静默**的（`SetEnabled` 返回 false、脚本只给一句笼统提示），
//:     这一格让"到底有没有被容量挡下"变成一个可读的数。
extern std::atomic<std::uint32_t> g_ModTogglePrunedEntries;
extern std::atomic<std::uint32_t> g_ModToggleCapacityRejections;

// 模组开关（2026-09-16，路线 B 的第一步）：把"哪些模组被关掉了"存进**游戏存档分区**，
// 并在扫描/加载之前按它过滤。
//
// 语义（照 PC）：新装的模组默认**开着**；这里只记例外 —— 用户关掉的那些目录名。
// 两个生效时机上的事实（真机验过，见 `docs/问题与解决记录.md` 续三十四）：
//   * 模组加载那一刻存档分区**已经挂好** ⇒ 开机就能读到状态，**当次生效**；
//   * 但模组的资源挂载点是在启动时建立的，所以"在菜单里关掉一个模组"要**重启游戏**才真正不加载
//     （PC 版同样要求重启）。
//
// 这个服务只做三件事：读状态、改状态、按状态过滤一批已解析的模组。它不碰 Lua、不碰 UI，
// 因此菜单（画界面）与扫描器（开机过滤）可以各自独立地用它。
class ModToggleService {
public:
    explicit ModToggleService(ISaveFilePort& files) noexcept : files_(files) {}

    // 从存档读状态。文件不存在 ⇒ 清空状态并返回 `Ok`（第一次运行就是这种情况）。
    [[nodiscard]] Status Load() noexcept;

    // 把内存里的状态写回存档（写完由适配器提交）。
    [[nodiscard]] Status Save() noexcept;

    [[nodiscard]] bool IsEnabled(std::string_view directory) const noexcept {
        return !state_.IsDisabled(directory);
    }

    // 内存里改一个模组的开关（**不落盘**，落盘由调用方在合适时机调 `Save()`）。
    [[nodiscard]] Status SetEnabled(std::string_view directory, bool enabled) noexcept {
        const Status status = state_.SetEnabled(directory, enabled);
        if (status.ok()) ++revision_;
        if (!status.ok() && status.code() == StatusCode::CapacityExceeded) {
            // ★ 批次 427：让"被容量挡下"留痕（用户报的"关不掉"就是它）。
            g_ModToggleCapacityRejections.fetch_add(1, std::memory_order_relaxed);
        }
        return status;
    }

    [[nodiscard]] const ModToggleState& state() const noexcept { return state_; }
    [[nodiscard]] std::size_t DisabledCount() const noexcept { return state_.disabledCount; }
    [[nodiscard]] std::uint64_t Revision() const noexcept { return revision_; }

    // 用户在 SD 卡上手工放的标记文件：`<modRoot>/disable.it` 存在 ⇒ 这个模组不加载。
    // 只读，不写卡（卡上的覆盖层是只读的），所以它是一条**给用户保底**的手工路径。
    [[nodiscard]] bool HasUserDisableMarker(const char* modRoot) noexcept;

    // 按状态过滤一批已解析的模组：被关掉的（或带用户标记的）整条移出去，其余**保持原顺序**。
    // 返回值 = 移掉了几个。指针在搬动后会被重新指向新的缓冲（`ResolvedManifestMod` 只有指针，
    // 见 `manifest_service.hpp`）。
    [[nodiscard]] std::size_t ApplyToBatch(ResolvedManifestModBatch* batch) noexcept;

private:
    ISaveFilePort& files_;
    ModToggleState state_{};
    std::uint64_t revision_{0};
};

} // namespace isaac::runtime
