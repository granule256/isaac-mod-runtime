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
#include <cstring>
#include "probe_gate.hpp"

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
//: 第 4 类降级（批次 141，2026-09-26）：**参数校验**把调用挡下 —— 形状声明了"这个整数参数
//: 必须是一个有效的 null 服装编号"，而模组传进来的编号无效（`GetCostumeIdByPath` 查不到时给的
//: `-1`、越界、或指向空槽）。挡下的理由是硬的：引擎那条路会 `AddCostume(nullptr)` 解引用空指针
//: （真机 `Data Abort`，`Address = 0`）。**这不是"修复"，是保险** —— 挡下过几次在这里看得见，
//: 不会让症状无声消失（见 `g_IsaacNullCostumeLastRequestedId`）。
extern std::atomic<std::uint32_t> g_IsaacEngineRowRejectGuard;

// ---- 服装查表 / 加摘服装的现场（批次 141，2026-09-26）------------------------------
//
// 由来：The Specialist for Good Items 在**文件作用域**用
// `Isaac.GetCostumeIdByPath("the/<…>.anm2")` 建两张服装表（`main.lua:26/29`，共 23 条路径），
// 跳舞时把结果直接喂给 `player:AddNullCostume(id)`（`main.lua:461/465`）。真机上崩在
// `Entity_Player::AddCostume + 0x3c`（空指针）—— 但**为什么**查不到，隔着一层猜不出来：
// 可能是"模组那 23 条根本不在引擎的 null 服装容器里"（资源加载时机），也可能是"命中了但编号
// 口径不对"。下面这几格就是分开这两种情况的尺子（读数工具按裸名直读）。
//
// 全部住 `bss`，加多少格都不花代码段。
extern std::atomic<std::uint32_t> g_IsaacCostumePathCalls;    //: `GetCostumeIdByPath` 被调几次
extern std::atomic<std::uint32_t> g_IsaacCostumePathHits;     //: 其中命中几次
extern std::atomic<std::uint32_t> g_IsaacCostumePathMisses;   //: 其中没命中几次（返回了 `-1`）
//: 最后一次**命中**的编号；`0xFFFFFFFF` = 一次都没命中过（与"命中了编号 0"区分开）。
extern std::atomic<std::uint32_t> g_IsaacCostumePathLastId;
//: 最后一次查表时 null 服装容器里有几个条目；`0xFFFFFFFF` = 那条链当时读不到（不是"容器空"）。
//: ★ 这一格回答的是"模组那 23 条到底在不在容器里"。
extern std::atomic<std::uint32_t> g_IsaacCostumePathNullCount;
//: "加/摘临时服装"最后一次收到的编号（按位模式存 `int32`，`-1` 读出来就是 `0xFFFFFFFF`）。
extern std::atomic<std::uint32_t> g_IsaacNullCostumeLastRequestedId;
//: 编号有效性**判定不了**（解析 `ItemConfig` 的那条链当时读不到）而照原样放行的次数。
//: 这一格必须保持 0：非 0 说明我们自己的链有问题，而那次我们没有挡 —— 不要把放行读成"编号有效"。
extern std::atomic<std::uint32_t> g_IsaacNullCostumeGuardUnknown;
//: ★★ 批次 154（2026-09-27）：`Music:Play` / `MusicManager:Play` 收到的编号**确认无效**
//: （负数或越界）而被我们**静默挡下**的次数 —— 这一格是"这次没放歌"与"我们挡了"的唯一区分点。
//:
//: 为什么要有它（真机事故，`dist/crash-153-20260927-1121.log`）：模组在回调里
//: `local specialist = Isaac.GetMusicIdByName("specialist")`，拿不到就是 `-1`，紧接着
//: `MusicManager():Play(specialist, 1)`（`main.lua:477/489`）。引擎 `Music::Play` 对越界/负数
//: 编号是按 `*(Music+0x3D8) + id*0x70` 算条目地址的（`umaddl`）⇒ 解引用到垃圾 ⇒ **Data Abort、
//: 崩在 `Music::Play + 0x68`**，整个游戏进程没了。
extern std::atomic<std::uint32_t> g_MusicPlayGuardBlocked;

// ---- 曲目反查的现场（批次 148，2026-09-26）-----------------------------------------
//
// 由来：The Specialist for Good Items 的"捡到四级物品放歌"在 `main.lua:477/478/185` 用
// `Isaac.GetMusicIdByName("specialist")` 拿**引擎的曲目编号**，再把编号喂给
// `MusicManager():Play(id, 1)`。PC 契约（`tools/pc_contract_docs/Isaac.md:290`）：
// "Returns the MusicID of a music track. (File: music.xml) Returns `-1` if no music with that
// name could be found."，例子里 `GetMusicIdByName("Title Screen")` 返回 61 ⇒ **编号就是曲目表下标**。
//
// 这几格是"这条反查到底有没有用"的尺子：调用次数 / 命中次数 / 最后一次的查询名与结果。
extern std::atomic<std::uint32_t> g_IsaacMusicIdCalls;
extern std::atomic<std::uint32_t> g_IsaacMusicIdHits;
//: 最后一次反查的结果（按位模式存 `int32`；`0xFFFFFFFF` = `-1`，与"编号 0"区分开）。
extern std::atomic<std::uint32_t> g_IsaacMusicIdLastResult;
//: 最后一次反查时曲目表里有多少条；`0xFFFFFFFF` = 那条链当时读不到（不是"表是空的"）。
//: ★ 这一格回答"模组的 `content/music.xml` 到底进引擎了没有"（真机基线：119 条）。
extern std::atomic<std::uint32_t> g_IsaacMusicIdTableCount;
//: 最后一次查询用的名字（NUL 结尾，按裸名符号直读）。`GetMusicIdByName` 的入参就是它。
extern char g_IsaacMusicIdLastName[64];
}

namespace isaac::runtime {

//: 被拒原因码（读数里按这些数字解释，不要改既有取值）。
enum class EngineRowRejectReason : std::uint32_t {
    None = 0,
    Receiver = 1,
    Offset = 2,
    EntryWord = 3,
    //: 批次 141（2026-09-26）：参数校验挡下（当前只有一种：无效的 null 服装编号）。
    //: 与前三类的区别：前三类是"我们没本事调进去"，这一类是"我们**主动不调**"（调了会崩）。
    ArgumentGuard = 4,
    //: 批次 303（2026-10-03）：**按 vtable 槽号调用的行**在解析目标时失败 ——
    //: 要么接收者首字（vptr）读不出来 / 为 0，要么 `[vptr + 0x10 + 槽号*8]` 读不出来 / 为 0，
    //: 要么槽号超过上界（行写错了）。这一类**没有**入口指纹可核（目标运行期才知道），
    //: 所以它与 `Offset` / `EntryWord` 分开记 —— 现场判读时能一眼区分"行写错了"与"vptr 不对"。
    Vtable = 5,
};

//: 数据行种类（`g_IsaacApiRowLastCallKind` 的取值）。
enum class ApiRowKind : std::uint32_t {
    Field = 1,
    EngineMethod = 2,
};

inline void RecordFieldRowCall(std::uint32_t id) noexcept {
    (void)id;  // 批次 232：生产构建里这段被编译掉 ⇒ 参数必然用不上
#if EXL_DIAGNOSTIC_PROBES  // 批次 232 探针总开关（口径见 probe_gate.hpp）
    g_IsaacApiRowCalls.fetch_add(1, std::memory_order_relaxed);
    g_IsaacApiRowLastCallId.store(id, std::memory_order_relaxed);
    g_IsaacApiRowLastCallKind.store(static_cast<std::uint32_t>(ApiRowKind::Field),
                                    std::memory_order_relaxed);
#endif  // EXL_DIAGNOSTIC_PROBES
}

inline void RecordEngineRowCall(std::uint32_t id) noexcept {
    (void)id;  // 批次 232：生产构建里这段被编译掉 ⇒ 参数必然用不上
#if EXL_DIAGNOSTIC_PROBES  // 批次 232 探针总开关（口径见 probe_gate.hpp）
    g_IsaacApiRowCalls.fetch_add(1, std::memory_order_relaxed);
    g_IsaacApiRowLastCallId.store(id, std::memory_order_relaxed);
    g_IsaacApiRowLastCallKind.store(static_cast<std::uint32_t>(ApiRowKind::EngineMethod),
                                    std::memory_order_relaxed);
    g_IsaacEngineRowCalls.fetch_add(1, std::memory_order_relaxed);
#endif  // EXL_DIAGNOSTIC_PROBES
}

inline void RecordEngineRowReject(std::uint32_t id, EngineRowRejectReason reason) noexcept {
    (void)id;  // 批次 232：生产构建里这段被编译掉 ⇒ 参数必然用不上
    (void)reason;  // 批次 232：生产构建里这段被编译掉 ⇒ 参数必然用不上
#if EXL_DIAGNOSTIC_PROBES  // 批次 232 探针总开关（口径见 probe_gate.hpp）
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
        case EngineRowRejectReason::ArgumentGuard:
            g_IsaacEngineRowRejectGuard.fetch_add(1, std::memory_order_relaxed);
            break;
        case EngineRowRejectReason::None:
        default:
            break;
    }
    g_IsaacEngineRowLastRejectId.store(id, std::memory_order_relaxed);
    g_IsaacEngineRowLastRejectReason.store(static_cast<std::uint32_t>(reason),
                                           std::memory_order_relaxed);
#endif  // EXL_DIAGNOSTIC_PROBES
}

//: 服装查表埋点（批次 141）。`hit` = 这次查到了（返回的是真实编号，不是 `-1`）；
//: `id` 只在命中时有意义；`nullItemCount` = 这次查表时容器里的条目数（`0xFFFFFFFF` = 读不到）。
inline void RecordCostumePathLookup(bool hit, std::uint32_t id,
                                    std::uint32_t nullItemCount) noexcept {
    (void)hit;  // 批次 232：生产构建里这段被编译掉 ⇒ 参数必然用不上
    (void)id;  // 批次 232：生产构建里这段被编译掉 ⇒ 参数必然用不上
    (void)nullItemCount;  // 批次 232：生产构建里这段被编译掉 ⇒ 参数必然用不上
#if EXL_DIAGNOSTIC_PROBES  // 批次 232 探针总开关（口径见 probe_gate.hpp）
    g_IsaacCostumePathCalls.fetch_add(1, std::memory_order_relaxed);
    if (hit) {
        g_IsaacCostumePathHits.fetch_add(1, std::memory_order_relaxed);
        g_IsaacCostumePathLastId.store(id, std::memory_order_relaxed);
    } else {
        g_IsaacCostumePathMisses.fetch_add(1, std::memory_order_relaxed);
    }
    g_IsaacCostumePathNullCount.store(nullItemCount, std::memory_order_relaxed);
#endif  // EXL_DIAGNOSTIC_PROBES
}

//: "加/摘临时服装"收到的编号（批次 141）：**无论有效与否都记**，这样"模组到底喂了什么进来"
//: 与"我们挡没挡"能对上。按位模式存，读数端按 `int32` 解。
inline void RecordNullCostumeRequest(std::int32_t id) noexcept {
    (void)id;  // 批次 232：生产构建里这段被编译掉 ⇒ 参数必然用不上
#if EXL_DIAGNOSTIC_PROBES  // 批次 232 探针总开关（口径见 probe_gate.hpp）
    g_IsaacNullCostumeLastRequestedId.store(static_cast<std::uint32_t>(id),
                                           std::memory_order_relaxed);
#endif  // EXL_DIAGNOSTIC_PROBES
}

//: 编号有效性判定不了（那条链读不到）而放行的次数（批次 141）。**应当恒 0**。
inline void RecordNullCostumeGuardUnknown() noexcept {
#if EXL_DIAGNOSTIC_PROBES  // 批次 232 探针总开关（口径见 probe_gate.hpp）
    g_IsaacNullCostumeGuardUnknown.fetch_add(1, std::memory_order_relaxed);
#endif  // EXL_DIAGNOSTIC_PROBES
}

//: `Music:Play` / `MusicManager:Play` 的编号保险挡下一次（批次 154）。见上面那一格的注释。
inline void RecordMusicPlayGuardBlocked() noexcept {
#if EXL_DIAGNOSTIC_PROBES  // 批次 232 探针总开关（口径见 probe_gate.hpp）
    g_MusicPlayGuardBlocked.fetch_add(1, std::memory_order_relaxed);
#endif  // EXL_DIAGNOSTIC_PROBES
}

//: 曲目名反查埋点（批次 148）。`result` = 反查结果（`-1` = 没找到）；`tableCount` = 查的时候
//: 曲目表里有几条（`0xFFFFFFFF` = 读不到）；`name` 是这次的查询名（可为 null ⇒ 不覆盖上一次）。
inline void RecordMusicIdLookup(std::int32_t result, std::uint32_t tableCount,
                                const char* name) noexcept {
    (void)result;  // 批次 232：生产构建里这段被编译掉 ⇒ 参数必然用不上
    (void)tableCount;  // 批次 232：生产构建里这段被编译掉 ⇒ 参数必然用不上
    (void)name;  // 批次 232：生产构建里这段被编译掉 ⇒ 参数必然用不上
#if EXL_DIAGNOSTIC_PROBES  // 批次 232 探针总开关（口径见 probe_gate.hpp）
    g_IsaacMusicIdCalls.fetch_add(1, std::memory_order_relaxed);
    if (result >= 0) {
        g_IsaacMusicIdHits.fetch_add(1, std::memory_order_relaxed);
    }
    g_IsaacMusicIdLastResult.store(static_cast<std::uint32_t>(result), std::memory_order_relaxed);
    g_IsaacMusicIdTableCount.store(tableCount, std::memory_order_relaxed);
    if (name != nullptr) {
        const std::size_t length = std::strlen(name);
        const std::size_t copy = length < sizeof(g_IsaacMusicIdLastName) - 1
                                     ? length
                                     : sizeof(g_IsaacMusicIdLastName) - 1;
        std::memcpy(g_IsaacMusicIdLastName, name, copy);
        g_IsaacMusicIdLastName[copy] = '\0';
    }
#endif  // EXL_DIAGNOSTIC_PROBES
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
    // ---- 批次 141 加：参数校验挡下 + 服装查表现场（新增字段一律加在**末尾**）----
    std::uint32_t rejectGuard;
    std::uint32_t costumePathCalls;
    std::uint32_t costumePathHits;
    std::uint32_t costumePathMisses;
    std::uint32_t costumePathLastId;
    std::uint32_t costumePathNullCount;
    std::uint32_t nullCostumeLastRequestedId;
    std::uint32_t nullCostumeGuardUnknown;
    // ---- 批次 148 加：曲目名反查（新增字段一律加在**末尾**）----
    std::uint32_t musicIdCalls;
    std::uint32_t musicIdHits;
    std::uint32_t musicIdLastResult;
    std::uint32_t musicIdTableCount;
    // ---- 批次 154 加：`Music:Play` 的编号保险挡下几次（新增字段一律加在**末尾**）----
    std::uint32_t musicPlayGuardBlocked;
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
        g_IsaacEngineRowRejectGuard.load(std::memory_order_relaxed),
        g_IsaacCostumePathCalls.load(std::memory_order_relaxed),
        g_IsaacCostumePathHits.load(std::memory_order_relaxed),
        g_IsaacCostumePathMisses.load(std::memory_order_relaxed),
        g_IsaacCostumePathLastId.load(std::memory_order_relaxed),
        g_IsaacCostumePathNullCount.load(std::memory_order_relaxed),
        g_IsaacNullCostumeLastRequestedId.load(std::memory_order_relaxed),
        g_IsaacNullCostumeGuardUnknown.load(std::memory_order_relaxed),
        g_IsaacMusicIdCalls.load(std::memory_order_relaxed),
        g_IsaacMusicIdHits.load(std::memory_order_relaxed),
        g_IsaacMusicIdLastResult.load(std::memory_order_relaxed),
        g_IsaacMusicIdTableCount.load(std::memory_order_relaxed),
        g_MusicPlayGuardBlocked.load(std::memory_order_relaxed),
    };
}

} // namespace isaac::runtime
