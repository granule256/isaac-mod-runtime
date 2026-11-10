#pragma once

#include "domain/runtime/status.hpp"

#include <cstddef>
#include <string_view>

namespace isaac::runtime {

// Small compatibility-layer files, named relative to the active profile root.
// Production uses an SD backend; the original save adapter remains available
// for one-time reads of older configuration. Native game saves stay in their
// own save filesystem. The historical interface name is retained for callers.
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

    // 覆盖写整个文件：文件不存在就创建、存在就截到新长度，写完持久化到对应后端。
    // 超过实现上限 ⇒ `CapacityExceeded`（宁可报错也不写半截 —— 半截状态比没有状态更难查）。
    [[nodiscard]] virtual Status Write(std::string_view name, std::string_view data) noexcept = 0;

    // 删掉文件并持久化删除状态；文件本来就不存在 ⇒ 仍返回 `Ok`（"删干净了"这件事已经成立）。
    [[nodiscard]] virtual Status Remove(std::string_view name) noexcept = 0;

    // 存在性检查，路径是**完整的**（例如 `rom:/isaac_mods/mods/<dir>/disable.it`）。
    // 用途：读用户在 SD 卡上**手工**放下的标记文件 —— 只读，不经过存档分区。
    [[nodiscard]] virtual Status Exists(const char* absolutePath, bool* exists) noexcept = 0;
};

// Consumers share one session port. Its provider owns profile isolation,
// legacy migration and the game-thread gate; absence must be reported as an
// unavailable capability rather than a successful no-op.
inline ISaveFilePort* g_sessionSaveFilePort = nullptr;

[[nodiscard]] inline ISaveFilePort* SessionSaveFilePort() noexcept {
    return g_sessionSaveFilePort;
}

// Publish only on the game thread before loading Mods and their settings.
inline void SetSessionSaveFilePort(ISaveFilePort* port) noexcept {
    g_sessionSaveFilePort = port;
}

} // namespace isaac::runtime
