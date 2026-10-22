#pragma once

#include "domain/runtime/status.hpp"

#include <cstddef>
#include <string_view>

namespace isaac::runtime {

// 游戏**存档分区**里的小文件（2026-09-16，B1 探针真机验收之后定的能力缝）。
//
// 为什么是"存档分区"而不是 SD 卡：游戏把它的存档分区挂成了 `sdmc` 这个名字
// （`SaveDataManager::GetMountPoint()` 硬编码返回 `"sdmc:/"`，初始化时截断成 `"sdmc"` 再调
// `nn::fs::MountSaveData("sdmc", uid)`），而它**根本没有导入** `nn::fs::MountSdCard` ——
// 也就是说游戏进程里没有"挂载真 SD 卡"的入口。真机验收（`docs/问题与解决记录.md` 续三十四）：
// 写 27 字节 → 重开读到 27 → **重启主机后仍然读得到**，所以这一层足以承载"模组开关状态"这类
// 需要跨启动保留的小数据。
//
// 名字一律**相对存档根**（例如 `isaac-switch-mods-state.txt`）。端口只描述"要什么"，
// 引擎细节（模块基址、导入跳板、守卫字节、对齐缓冲）全在适配器里。
class ISaveFilePort {
public:
    virtual ~ISaveFilePort() = default;

    // 读整个文件。文件不存在 ⇒ `NotFound`（**不是**错误：调用方要能区分"还没有状态"与
    // "读坏了"）；文件比 `capacity` 大 ⇒ `CapacityExceeded`（不截断，见下面 `Write` 的口径）。
    [[nodiscard]] virtual Status Read(std::string_view name, char* out, std::size_t capacity,
                                      std::size_t* size) noexcept = 0;

    // 可选真实大小能力：旧提供方可不实现；消费者回退到Read，CapacityExceeded时
    // 应把所需完整长度写入size，不能静默截断。
    [[nodiscard]] virtual Status GetSize(std::string_view, std::size_t*) noexcept {
        return Status{StatusCode::Unsupported};
    }

    // 0表示尚未选择槽（或旧提供方不提供槽），1..3对应引擎实际保存槽。
    // 默认值仅兼容已有端口替身；生产提供方必须读取真实引擎字段。
    [[nodiscard]] virtual Status GetSaveSlot(unsigned* slot) noexcept {
        if (slot == nullptr) return Status{StatusCode::InvalidArgument};
        *slot = 0;
        return Status::Ok();
    }

    // 覆盖写整个文件：文件不存在就创建、存在就截到新长度，写完**提交存档**。
    // 超过实现上限 ⇒ `CapacityExceeded`（宁可报错也不写半截 —— 半截状态比没有状态更难查）。
    [[nodiscard]] virtual Status Write(std::string_view name, std::string_view data) noexcept = 0;

    // 删掉文件并提交存档；文件本来就不存在 ⇒ 仍返回 `Ok`（"删干净了"这件事已经成立）。
    [[nodiscard]] virtual Status Remove(std::string_view name) noexcept = 0;

    // 存在性检查，路径是**完整的**（例如 `rom:/isaac_mods/mods/<dir>/disable.it`）。
    // 用途：读用户在 SD 卡上**手工**放下的标记文件 —— 只读，不经过存档分区。
    [[nodiscard]] virtual Status Exists(const char* absolutePath, bool* exists) noexcept = 0;
};

// ---- 会话级默认实现（2026-09-17，用户指令）------------------------------------------
//
// 用户口径原话："将之后所有的持久化都走存档分区，直接将存档分区持久化作为当前持久化的默认实现，
// 做到解耦合，以后统一调用同样的接口。"
//
// 所以持久化只有**一个**接口（就是上面的 `ISaveFilePort`），**默认提供方是存档分区**
// （`EngineSaveFileAdapter`）。消费者（模组数据容器、模组开关状态，以及以后任何持久化）一律通过
// `SessionSaveFilePort()` 取端口，不自己找文件、也不自己判"有没有文件能力"：
//   * 还没接上（或构建里根本没接）⇒ 返回 nullptr ⇒ 调用方按"能力不可用"如实报，**不静默失败**；
//   * 接上之后，**线程纪律由端口实现负责**（存档分区适配器默认拒绝一切操作，只有游戏线程上的代码
//     能打开它），消费者不必各自再记一遍"我是不是在游戏线程上"。
//
// 这是 `inline` 变量（常量初始化，没有动态初始化顺序问题）—— 本模块用 `-nostartfiles` 链接，
// 刻意不用"函数内静态 + 守卫变量"那套。
inline ISaveFilePort* g_sessionSaveFilePort = nullptr;

[[nodiscard]] inline ISaveFilePort* SessionSaveFilePort() noexcept {
    return g_sessionSaveFilePort;
}

// 只允许在**游戏线程**上、且存档分区已经可用之后调用（当前唯一调用点：模组加载路径）。
inline void SetSessionSaveFilePort(ISaveFilePort* port) noexcept {
    g_sessionSaveFilePort = port;
}

} // namespace isaac::runtime
