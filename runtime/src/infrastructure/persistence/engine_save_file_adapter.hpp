#pragma once

#include "ports/save_file_port.hpp"

#include <array>
#include <cstddef>
#include <cstdint>
#include <string_view>

namespace isaac::runtime {

// 走游戏自己 fs 会话的存档文件适配器（2026-09-16，B1 真机验收之后）。
//
// 为什么是**直连 `nn::fs`**（而不是引擎的 `KAGE::Filesys::File` 类）：
//   * 真机对照过两条路（`docs/问题与解决记录.md` 续三十四）：两条都能写，但引擎那条的
//     `read_stream_data` 稳定读回 0 字节、`File::Close()` 的返回类型还是 `void`；
//   * 直连的每一步都返回 `Result` 码（0 = 成功），没有缓冲层与流模式语义要照顾；
//   * 全部入口都是游戏模块自己的**导入跳板**，地址来自它的 `.got`，每个跳板都有 16 字节守卫。
//
// 具体入口与偏移写在 `runtime_constants.hpp`（含逐条证据）；这里只负责编排与把
// `Result` 翻成项目的 `Status`。
class EngineSaveFileAdapter final : public ISaveFilePort {
public:
    EngineSaveFileAdapter() noexcept = default;

    [[nodiscard]] Status Read(std::string_view name, char* out, std::size_t capacity,
                              std::size_t* size) noexcept override;
    [[nodiscard]] Status Write(std::string_view name, std::string_view data) noexcept override;
    [[nodiscard]] Status Remove(std::string_view name) noexcept override;
    [[nodiscard]] Status Exists(const char* absolutePath, bool* exists) noexcept override;

    // ★ 线程硬闸（2026-09-17，用户指令"所有持久化统一走存档分区"的配套纪律）。
    //
    // 为什么必须闸：游戏这套 nnSdk 的文件 API **只允许在游戏自己的线程上调用** ——
    // 2026-09-16 的 442190 就是"在我们的 worker 线程上调 `nn::fs::OpenFile`"导致
    // **每次开机必崩**（崩在 SDK 的线程本地堆里，两份崩溃报告在案）。
    // 所以这个适配器**默认拒绝一切操作**（返回 `Unsupported`，即"能力不可用"，不是失败），
    // 只有游戏线程上的代码显式打开它之后才工作。任何新的持久化消费者只要走这个端口，
    // 就自动继承这道保护，不需要各自再记一遍"我是不是在游戏线程上"。
    void AllowFromGameThread() noexcept { allowed_ = true; }
    [[nodiscard]] bool Allowed() const noexcept { return allowed_; }

    // 单次读写的上限：缓冲区是**一个页对齐的静态缓冲**，因为 `nn::fs::ReadFile` 对
    // 缓冲区对齐有要求（真机第三轮探针就是靠这一点把"读回 0 字节"排除掉的）。
    //
    // 2026-09-17：0x1000 → **0x4000**。理由：模组数据容器（`ModPersistence`）的单文件上限是
    // 16 KiB，而它现在改走这个适配器 ⇒ 缓冲必须能装下整个容器，否则每次都会 `CapacityExceeded`。
    // 门禁 `test_save_file_channel` 钉住"缓冲 ≥ 容器上限"这条关系。
    static constexpr std::size_t kMaximumFileBytes = 0x4000;

private:
    struct Calls;

    [[nodiscard]] const Calls* Resolve() noexcept;
    [[nodiscard]] static bool ResolveMount(const Calls& calls, std::array<char, 32>& mountPoint,
                                          std::array<char, 32>& mountName) noexcept;
    [[nodiscard]] bool BuildRelativePath(std::string_view name, char* out,
                                         std::size_t capacity) const noexcept;

    std::array<char, 32> mountPoint_{};
    std::array<char, 32> mountName_{};
    bool mountResolved_{false};
    bool mountValid_{false};
    // 见 `AllowFromGameThread()`：默认 closed，只有游戏线程上的代码能打开。
    bool allowed_{false};
    // 页对齐：`nn::fs::ReadFile` 对缓冲区对齐有要求；放在静态存储里（不进游戏线程栈）。
    alignas(0x1000) static char buffer_[kMaximumFileBytes];
};

} // namespace isaac::runtime
