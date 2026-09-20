#pragma once

// ============================================================================
// "这条 API 到底有没有被调到、调了却静默降级了吗"（批次 069，2026-09-19）
// ============================================================================
//
// **为什么要有它**：这个问题在今天之前只能靠**写探针**（改卡上第三方模组的脚本）回答，
// 而探针要用户"退游戏 → 开 FTP → 装 → 关 FTP → 开游戏"，一次十几分钟。
//
// 数据行处理器（`FieldApiHandler` / `EngineMethodHandler`）的设计是**静默降级**：
// 接收者解析不到、偏移拿不到、入口指纹不匹配，都只是"这一次没生效"，**不报错**
// （报错会把整条模组回调摘掉，比"没生效"严重）。代价是"没生效"与"压根没被调用"
// 在设备上长得一模一样 —— 只能靠探针区分。
//
// 所以这里记：
//   * `g_IsaacApiRowCalls` + 最后一次的 id/种类 —— "这个 API 被调过吗"（字段行与引擎方法行都算）；
//   * 引擎方法行三类被拒次数 + 最后一次被拒的 id 与原因 —— "调了但没生效，是哪一类原因"。
//
// 全部是**计数**：加一条 API 不花代码段（这几格是固定的 bss），读数工具按符号直读
// （`extern "C"` 名字不进名称改编）。
//
// 读法：`python3 tools/read_device_state_via_gdb.py --api-stats`
// （id 经 `tools/api_surface_ledger.json` / `api_catalog.cpp` 反查成 `owner:name`）。

#include <atomic>
#include <cstdint>

extern "C" {
//: 数据行（字段行 + 引擎方法行）被调用的总次数；最后一次被调用的行 id 与种类（1=字段 2=引擎方法）。
extern std::atomic<std::uint32_t> g_IsaacApiRowCalls;
extern std::atomic<std::uint32_t> g_IsaacApiRowLastCallId;
extern std::atomic<std::uint32_t> g_IsaacApiRowLastCallKind;

//: 引擎方法行被调用了几次（`g_IsaacApiRowCalls` 的子集，单独留着便于直接对账）。
extern std::atomic<std::uint32_t> g_IsaacEngineRowCalls;
//: 三类静默降级的次数：接收者解析失败 / 偏移拿不到 / 入口 4 字节指纹不匹配。
extern std::atomic<std::uint32_t> g_IsaacEngineRowRejectReceiver;
extern std::atomic<std::uint32_t> g_IsaacEngineRowRejectOffset;
extern std::atomic<std::uint32_t> g_IsaacEngineRowRejectEntry;
//: 最后一次被拒的行 id 与原因（见 `EngineRowRejectReason`）。
extern std::atomic<std::uint32_t> g_IsaacEngineRowLastRejectId;
extern std::atomic<std::uint32_t> g_IsaacEngineRowLastRejectReason;
}

namespace isaac::runtime {

//: 被拒原因码（读数里按这些数字解释，不要改既有取值）。
enum class EngineRowRejectReason : std::uint32_t {
    None = 0,
    Receiver = 1,
    Offset = 2,
    EntryWord = 3,
};

//: 数据行种类（`g_IsaacApiRowLastCallKind` 的取值）。
enum class ApiRowKind : std::uint32_t {
    Field = 1,
    EngineMethod = 2,
};

inline void RecordFieldRowCall(std::uint32_t id) noexcept {
    g_IsaacApiRowCalls.fetch_add(1, std::memory_order_relaxed);
    g_IsaacApiRowLastCallId.store(id, std::memory_order_relaxed);
    g_IsaacApiRowLastCallKind.store(static_cast<std::uint32_t>(ApiRowKind::Field),
                                    std::memory_order_relaxed);
}

inline void RecordEngineRowCall(std::uint32_t id) noexcept {
    g_IsaacApiRowCalls.fetch_add(1, std::memory_order_relaxed);
    g_IsaacApiRowLastCallId.store(id, std::memory_order_relaxed);
    g_IsaacApiRowLastCallKind.store(static_cast<std::uint32_t>(ApiRowKind::EngineMethod),
                                    std::memory_order_relaxed);
    g_IsaacEngineRowCalls.fetch_add(1, std::memory_order_relaxed);
}

inline void RecordEngineRowReject(std::uint32_t id, EngineRowRejectReason reason) noexcept {
    switch (reason) {
        case EngineRowRejectReason::Receiver:
            g_IsaacEngineRowRejectReceiver.fetch_add(1, std::memory_order_relaxed);
            break;
        case EngineRowRejectReason::Offset:
            g_IsaacEngineRowRejectOffset.fetch_add(1, std::memory_order_relaxed);
            break;
        case EngineRowRejectReason::EntryWord:
            g_IsaacEngineRowRejectEntry.fetch_add(1, std::memory_order_relaxed);
            break;
        case EngineRowRejectReason::None:
        default:
            break;
    }
    g_IsaacEngineRowLastRejectId.store(id, std::memory_order_relaxed);
    g_IsaacEngineRowLastRejectReason.store(static_cast<std::uint32_t>(reason),
                                           std::memory_order_relaxed);
}

//: 宿主测试用的快照（调试桩不经它 —— 工具按符号直读上面那几格）。
struct ApiRowStats {
    std::uint32_t calls;
    std::uint32_t lastCallId;
    std::uint32_t lastCallKind;
    std::uint32_t engineCalls;
    std::uint32_t rejectReceiver;
    std::uint32_t rejectOffset;
    std::uint32_t rejectEntry;
    std::uint32_t lastRejectId;
    std::uint32_t lastRejectReason;
};

[[nodiscard]] inline ApiRowStats ApiRowStatsSnapshot() noexcept {
    return ApiRowStats{
        g_IsaacApiRowCalls.load(std::memory_order_relaxed),
        g_IsaacApiRowLastCallId.load(std::memory_order_relaxed),
        g_IsaacApiRowLastCallKind.load(std::memory_order_relaxed),
        g_IsaacEngineRowCalls.load(std::memory_order_relaxed),
        g_IsaacEngineRowRejectReceiver.load(std::memory_order_relaxed),
        g_IsaacEngineRowRejectOffset.load(std::memory_order_relaxed),
        g_IsaacEngineRowRejectEntry.load(std::memory_order_relaxed),
        g_IsaacEngineRowLastRejectId.load(std::memory_order_relaxed),
        g_IsaacEngineRowLastRejectReason.load(std::memory_order_relaxed),
    };
}

} // namespace isaac::runtime
