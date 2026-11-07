#pragma once

// 触摸屏 → 指针（建，修）。
//
// ## 背景
//
// PC 的 `Input.GetMousePosition` / `Input.IsMouseBtnPressed` 在 Switch 上没有对应输入源，
// 一直是恒 `(0,0)` / 恒 `false`（登记为"平台固有、永远消不掉"）。后果是第三方模组里
// 所有"鼠标悬停才显示"的交互在真机上是死的** —— EID 的 `EID:handleHoverHUD()`
//（`main.lua:1050`，鼠标悬停热区）与 `EID:renderHUDLocationIndicators()`（`main.lua:1024`）
// 永远触发不了。2026-09-28 用户实测"屏幕上什么都没看到"，查证后确认就是这条路
//（当天日志 §190：我先前把 `EID.HUDElements` 误当成"口袋物品栏"）。
//
// 用户指令：**把 PC 上的鼠标操作映射成 NS 上的触屏操作**（交接文档 §4.7）。
//
// ## 做法：直接读游戏**已经映射好的** hid 共享内存
//
// 关键观察：**我们的模块跑在游戏进程里**（读数里"运行时模块基址/游戏模块基址"同属一个进程）
// ⇒ 游戏为了读手柄而建立的 **`hid` 共享内存本来就在我们的地址空间里**，触摸屏数据就在那块内存里。
// 于是**不需要**创建第二个 `hid` 会话、**不需要**任何 IPC —— 只做**纯内存读**：
// 找到那块映射，按布局读出最新的触摸点。
//
// 这样做的理由（三条都是硬的）：
//   1. **不打扰游戏**：不 `smGetService`、不 `EnableTouchScreen`、不改任何配置 ⇒ 与"只读"的
//      风险约束一致（游戏自己的输入路径一个字节都不动）；
//   2. **不引 libnx**：见下面"为什么不能 include"那段 —— 引 libnx 的 `hid.o` 会连
//      `applet.o → env.o → switch_crt0.o` 一起拉进来，而我们是个模块、链不了 CRT0；
//   3. 失败模式良性：找不到就退回"没按下"，绝不崩。
//
// ## 为什么**不能** include libnx 的 `<switch/services/hid.h>`（2026-09-28 实测两个坑）
//
//   1. 它会拉进 libnx 的 `result.h`，与 exlaunch 自带的同名宏/枚举**逐个冲突**
//      （`-Werror` 下 300 余条：`'R_SUCCEEDED' redefined`、`'MAKERESULT' redefined`、
//       `'Module_Libnx' conflicts with a previous declaration` …）；
//   2. 就算绕开第 1 条，`hidGetTouchScreenStates` 会把 libnx 的 `hid.o` 链进来 ⇒
//      `hid.o` 要 `appletGetAppletResourceUserId` ⇒ 拉 `applet.o` ⇒ 要 `envSetExitFuncPtr`
//      ⇒ 拉 `env.o` ⇒ 要 `__nx_exit` ⇒ 拉 **`switch_crt0.o`** ⇒
//      `relocation R_AARCH64_PREL32 ... can not be used when making a shared object`（链接失败）。
//      （我们是被注入的模块，用的是 exlaunch 自己的 CRT，不是 libnx 的启动代码。）
//   3. 守卫必须用 `__SWITCH__` 而**不是** `__aarch64__`：`__aarch64__` 在 **Apple Silicon 的
//      macOS 上也定义**（本机就是）⇒ 宿主门禁编译会去拉 libnx 头而失败
//      （`fatal error: 'switch/services/hid.h' file not found`，第一版就是这么错的）。
//
// ## 的更正：怎么认出"这块映射就是触摸屏"（在这里错了一次）
//
// 的判据是"17 个条目的点数都在 0..16"，然后 2026-09-28 真机读数就报
// `共享内存 = 找到共享内存`、基址 `0x4cc64f000`。**那是误报**：`--read` 把原始字节读回来看，
// 从 `+0x000` 到 `+0x500` **整段全 0** —— 那只是游戏进程里另一块同样大小的零页，
// 而**任何零页都满足旧判据**（全 0 当然都在 0..16 之间）。
// 后果：读数里那句 `手指在屏幕上的有 0 帧` 什么也证明不了（读的根本不是触摸屏）。
//
// 现在的判据加上了 **lifo 表头**（`HidCommonLifoHeader` = `unused / buffer_count / tail / count`，
// 各 `u64`）：`buffer_count` **恒等于 17**（建表时写死、与有没有触摸无关），`tail < 17`、
// `count <= 17`。零页在第一条就出局（`buffer_count = 0 != 17`）。
//
// ## 布局的口径来源（不是推测）
//
//   * 触摸屏 lifo 在共享内存 **+0x400**（`HidSharedMemory` 里 `debug_pad` 在前）、
//     表头 **0x20 字节**（4 个 `u64`）、条目存储从 **+0x420** 起、**17 条**、每条 **0x298**：
//     `libnx.a` 的 `hidGetTouchScreenStates` 反汇编（`add x0, x0, #0x400` / `#0x420` / `#0x290`），
//     与 `sizeof(HidCommonLifoHeader)=0x20`、`sizeof(HidTouchScreenStateAtomicStorage)=0x298`、
//     `sizeof(HidTouchScreenState)=0x290` 互证（2026-09-28 又用 devkitPro 里 libnx 头逐行核了一遍）；
//   * 条目 = `u64 sampling_number + HidTouchScreenState{ u64 sampling_number; s32 count;
//     u32 reserved; HidTouchState touches[16] }`；
//   * `HidTouchState` 的字段顺序（就是这里错的）：
//     `u64 delta_time; u32 attributes; u32 finger_id; u32 x; u32 y; u32 diameter_x;
//      u32 diameter_y; u32 rotation_angle; u32 reserved;`
//     ⇒ `x` 在 **touch+16**、`y` 在 **touch+20**（相对条目就是 **+40 / +44**）。
//     把 x 算成了 `touch+12`（那是 `finger_id`）⇒ 读到的是错位一个字段的值。
//   * `sizeof(HidSharedMemory) = 0x40000`（编译期实取）。
//
// ## 这一层验不了什么
//
// 触摸坐标的**换算口径**（PC 的 `gameCoords` 真/假各对应什么）**只能真机量**；
// 引擎（KAGE）自己还有一整套触摸层（`KAGE::Input::DeviceTouchscreen::PollForInput @ 0x4fcd7c`、
// `ManagerBase::GetTouches @ 0x4fa568`、`GetTouchPanelSize @ 0x4fa78c`），
// 能调引擎就调引擎是下一步的方向（的第二步）。
// 宿主门禁能验的是"接线、判据、找不到时的良性降级"。

// 设备侧要用 `svcQueryMemory` 遍历映射表。用仓库里 vendored 的那份 libnx
// （`runtime/source/lib/nx/nx.h`，与 `infrastructure/memory/engine_field_access.hpp:55` 同一条路）——
// 它已经定义了 `MemoryInfo` / `Result` / `Perm_R`。
// 为什么不自己声明：第一版就是自己声明的，结果与 vendored 的那份签名冲突
// （`conflicting declaration of C function 'svcQueryMemory(TouchPointerMemoryInfo*, ...)'`）——
// 同一个编译单元里本来就引过 vendored 头（经由 `engine_call_access.hpp`），再声明一份是多余且错的。
// 为什么不用 devkitpro 的 `<switch.h>`：见文件头"为什么不能 include libnx"。
#if defined(__SWITCH__)
#include "lib/nx/nx.h"
// 取值走框架的受保护读原语（`engine_memory::ReadAt` + `EngineMemoryReadable`），
// 不自己解引用。理由两条：
// ① 这是本项目对"碰引擎内存"的唯一既定通道：先判可读、再取值，判定结果按整段映射缓存
// （`infrastructure/memory/engine_field_access.hpp`）；自己 `*reinterpret_cast<T*>` 等于
// 绕开它 —— 门禁 `test_no_new_raw_engine_access` 正是拦这个（第一版被它拦下）。
// ② 那两处"裸碰"会被记成新增存量（683 → 685），而存量只许减不许增。
#include "infrastructure/memory/engine_field_access.hpp"
#endif

#include <atomic>
#include <cstdint>

namespace isaac::runtime {

// 触摸读取的三态：还没找到 / 找到了 / 试过但没找到（找不到时一律退回恒值行为）。
enum class TouchPointerInitState : std::uint32_t {
    kNotTried = 0,
    kReady = 1,
    kFailed = 2,
};

// 可读的诊断量（真机读数用；不是 Lua 接口）。它们是"触摸到底通没通"的唯一现场证据。
// 命名与既有输入探针（`g_InputActionTriggeredMask` 等）同风格，读数工具按 `nm` 直出即可找到。
inline std::atomic<std::uint32_t> g_TouchPointerInitState{
    static_cast<std::uint32_t>(TouchPointerInitState::kNotTried)};
// 扫过映射表几次（正常 1 次就够）。
inline std::atomic<std::uint32_t> g_TouchPointerScanAttempts{0};
// 找到的共享内存基址（0 = 没找到）。
inline std::atomic<std::uint32_t> g_TouchPointerShmemLow{0};
inline std::atomic<std::uint32_t> g_TouchPointerShmemHigh{0};
// 扫过的映射段数（诊断用：太小说明遍历提前退出了）。
inline std::atomic<std::uint32_t> g_TouchPointerSegmentsScanned{0};
// 加的"这次真的认出 lifo 了吗"证据（全是发现那块内存时读下来的）：
// lifo 表头里的 `buffer_count`（必须是 17）、`tail`、`count`。零页在这里会露馅（读到 0）。
inline std::atomic<std::uint32_t> g_TouchPointerLifoBufferCount{0};
inline std::atomic<std::uint32_t> g_TouchPointerLifoTail{0};
inline std::atomic<std::uint32_t> g_TouchPointerLifoCount{0};
// 扫描时"可读但判据不符"的映射段数（> 0 说明扫到过别的东西，判据确实在筛）。
inline std::atomic<std::uint32_t> g_TouchPointerRejectedMappings{0};
// 读过触摸屏的总帧数（含"没有触摸"的那些）—— 与下面的计数配合，区分"没点"与"根本没读"。
inline std::atomic<std::uint32_t> g_TouchPointerPollFrames{0};
// 读到"至少一个触摸点"的帧数（> 0 就证明手指位置真的被读到了）。
inline std::atomic<std::uint32_t> g_TouchPointerTouchFrames{0};
// 最后一次的原始触摸坐标与点数（未做任何换算）。
inline std::atomic<std::uint32_t> g_TouchPointerLastRawX{0};
inline std::atomic<std::uint32_t> g_TouchPointerLastRawY{0};
inline std::atomic<std::uint32_t> g_TouchPointerLastCount{0};
// 最新条目的采样号低 32 位与它在 lifo 里的槽位号。用途：判"这块内存是活的吗" ——
// 真的 lifo 每采样一次这个号就加一（与有没有手指无关），所以两次读数之间它应当变化。
// `0` = 一条带采样号的条目都没有（那说明是块死内存，而不是"没人在按"）。
inline std::atomic<std::uint32_t> g_TouchPointerLastSampling{0};
inline std::atomic<std::uint32_t> g_TouchPointerLastEntryIndex{0};

// 一帧的触摸快照（已归一化成"指针"语义）。
struct TouchPointerSnapshot {
    // = 手指在屏幕上（用户 2026-09-28 定的语义：手指在屏幕上 = 左键按下）。
    bool pressed;
    // 原始触摸坐标（未换算）。`pressed == false` 时这两项保留上一次的值 ——
    // 与 PC 的"鼠标不动时位置不变"一致，也正是 GoodTrip「与上一帧的距离平方 > 4」需要的输入。
    std::uint32_t rawX;
    std::uint32_t rawY;
};

// ---------------------------------------------------------------------------
// 布局与判据（**纯逻辑**：不碰引擎内存、不依赖任何 Switch 头 ⇒ 宿主门禁直接可测）。
//
// 放在守卫外面是刻意的：的误报是纯逻辑错（判据太弱），而当时这段逻辑在
// `#if defined(__SWITCH__)` 里面 ⇒ 宿主机根本编不到它、门禁也就抓不住。
// 「让门禁能抓到它」比"少一层条件编译"重要得多。
// ---------------------------------------------------------------------------
namespace touch_pointer_detail {

// 触摸屏 lifo 在共享内存里的位置与大小（口径来源见文件头）。
constexpr std::uintptr_t kTouchScreenLifoOffset = 0x400;
constexpr std::uintptr_t kLifoHeaderBytes = 0x20;
// 条目存储的起点（lifo 头 0x20 字节在 +0x400，条目从 +0x420 起）。
constexpr std::uintptr_t kTouchScreenStorageOffset = kTouchScreenLifoOffset + kLifoHeaderBytes;
constexpr std::uint32_t kLifoEntryCount = 17;
constexpr std::uintptr_t kLifoEntryStride = 0x298;

// `HidCommonLifoHeader { u64 unused; u64 buffer_count; u64 tail; u64 count; }`（相对 lifo 起点）。
constexpr std::uintptr_t kHeaderBufferCountOffset = 8;
constexpr std::uintptr_t kHeaderTailOffset = 16;
constexpr std::uintptr_t kHeaderCountOffset = 24;
// `buffer_count` 恒等于条目数 —— 建表时写死，与有没有触摸无关 ⇒ 认内存的硬判据。
constexpr std::uint64_t kExpectedBufferCount = kLifoEntryCount;

// 一个条目里"采样号 / 点数 / 第 0 个触摸点"的位置（相对条目起点）。
// 条目 = `u64 sampling_number + HidTouchScreenState{ u64 sampling_number; s32 count;
// u32 reserved; HidTouchState touches[16] }`。
constexpr std::uintptr_t kEntrySamplingOffset = 8;
constexpr std::uintptr_t kEntryCountOffset = kEntrySamplingOffset + 8;   // 16
constexpr std::uintptr_t kEntryTouch0Offset = kEntrySamplingOffset + 16; // 24
// `HidTouchState = u64 delta_time; u32 attributes; u32 finger_id; u32 x; u32 y; ...`
// ⇒ x 在 touch+16、y 在 touch+20（写成 +12/+16，读到的是 finger_id 与 x）。
constexpr std::uintptr_t kTouchFieldXOffset = 16;
constexpr std::uintptr_t kTouchFieldYOffset = 20;
constexpr std::uintptr_t kEntryTouch0XOffset = kEntryTouch0Offset + kTouchFieldXOffset; // 40
constexpr std::uintptr_t kEntryTouch0YOffset = kEntryTouch0Offset + kTouchFieldYOffset; // 44

// 认定"这块映射是 hid 共享内存"所需的最小长度（lifo 条目要全部落在映射内，
// 否则会读到映射外 ⇒ 可能 `Data Abort`）。
constexpr std::uint64_t kMinimumSharedMemoryBytes =
    kTouchScreenStorageOffset + kLifoEntryCount * kLifoEntryStride;

// "读不到"的哨兵：必须让每一条判据都判否（不能"读不到 = 通过"）。
constexpr std::uint64_t kUnreadableU64 = 0xFFFFFFFFFFFFFFFFULL;
constexpr std::uint32_t kUnreadableU32 = 0xFFFFFFFFU;

// 触摸面板像素 → 引擎逻辑屏幕（渲染）坐标的换算系数（2026-09-28 独立核实，不是我发明的口径）。
// 口径来源（三条互证）：
// ① `DeviceTouchscreen::GetTouchPanelWidth/Height`（`0x4fcd6c` / `0x4fcd74`）反编译就是
// `return 0x500;` / `return 0x2d0;` = 硬编码 1280 / 720（不来自任何全局）；
// ② 引擎的逻辑屏幕是 480×270：`GraphicsConfigOptions::s_OrthographicProjectionWidth/Height`
// @ `0xa386c0` / `0xa386c4` = `480.0f` / `270.0f`；
// ③ 引擎自己消费触摸时就是这么算的：`Minimap::Update`（`0x41cb84`~`0x41cc0c`）
// `Vector2(480,270) / 面板尺寸`（→ 0.375）再乘触摸坐标。
// ⇒ 480/1280 与 270/720 都是 0.375（同一个标量，下面那个 `static_assert` 钉住这一点）。
// 这也正是 `Isaac.WorldToScreen` 返回的那个尺度（PC 文档：`Isaac.md:655`「一般在 500×300 以内」）。
constexpr float kTouchPanelWidth = 1280.0F;
constexpr float kTouchPanelHeight = 720.0F;
constexpr float kRenderWidth = 480.0F;
constexpr float kRenderHeight = 270.0F;
constexpr float kPanelToRenderScaleX = kRenderWidth / kTouchPanelWidth;
constexpr float kPanelToRenderScaleY = kRenderHeight / kTouchPanelHeight;
static_assert(kPanelToRenderScaleX == kPanelToRenderScaleY,
              "两轴系数必须相同（480/1280 与 270/720）—— 不同就意味着该用两个标量，别再当成一个");

// 这块映射像不像 hid 触摸屏 lifo？三条判据，缺一不可：
// ① 长度够（`kMinimumSharedMemoryBytes`，否则会读到映射外）；
// ② lifo 表头成立：`buffer_count == 17`（这条是补的，零页就死在这里）、
// `tail < 17`、`count <= 17`；
// ③ 17 个条目的"点数"全部落在 0..16。
// `readU64/readU32` 是注入的读原语（设备侧走框架的受保护读，宿主侧由门禁喂合成缓冲）。
template <typename ReadU64Fn, typename ReadU32Fn>
inline bool LooksLikeTouchScreenLifo(ReadU64Fn readU64, ReadU32Fn readU32,
                                     std::uintptr_t base, std::uint64_t size) noexcept {
    if (size < kMinimumSharedMemoryBytes) {
        return false;
    }
    const std::uintptr_t lifo = base + kTouchScreenLifoOffset;
    if (readU64(lifo + kHeaderBufferCountOffset, kUnreadableU64) != kExpectedBufferCount) {
        return false;
    }
    if (readU64(lifo + kHeaderTailOffset, kUnreadableU64) >= kLifoEntryCount) {
        return false;
    }
    if (readU64(lifo + kHeaderCountOffset, kUnreadableU64) > kLifoEntryCount) {
        return false;
    }
    const std::uintptr_t storage = base + kTouchScreenStorageOffset;
    for (std::uint32_t i = 0; i < kLifoEntryCount; ++i) {
        // 读不到 ⇒ 哨兵肯定越界 ⇒ 判"不像"（而不是"像"）。
        const std::int32_t count = static_cast<std::int32_t>(
            readU32(storage + i * kLifoEntryStride + kEntryCountOffset, kUnreadableU32));
        if (count < 0 || count > 16) {
            return false;
        }
    }
    return true;
}

// 从 lifo 里取最新的那个条目：`sampling_number` 最大的那一条。
// 为什么用"最大 sampling_number"而不是 lifo 头里的索引：少依赖一个字段的语义，
// 而 `sampling_number` 是单调递增的采样号（libnx 自己判新旧也用类似办法）。
// 返回 false = 一条带采样号的条目都没有（这块内存没在被写）。
template <typename ReadU64Fn, typename ReadU32Fn>
inline bool ReadNewestTouchFrom(ReadU64Fn readU64, ReadU32Fn readU32, std::uintptr_t base,
                                std::uint32_t* outX, std::uint32_t* outY, std::uint32_t* outCount,
                                std::uint32_t* outEntryIndex, std::uint64_t* outSampling) noexcept {
    const std::uintptr_t storage = base + kTouchScreenStorageOffset;
    std::uint64_t newestSampling = 0;
    bool found = false;
    for (std::uint32_t i = 0; i < kLifoEntryCount; ++i) {
        const std::uintptr_t entry = storage + i * kLifoEntryStride;
        // 采样号读不到 ⇒ 跳过这一条（哨兵 0 同时也是"还没比较过"的初值）。
        const std::uint64_t sampling = readU64(entry + kEntrySamplingOffset, 0);
        if (sampling == 0) {
            continue;
        }
        if (!found || sampling > newestSampling) {
            newestSampling = sampling;
            found = true;
            *outCount = static_cast<std::uint32_t>(
                static_cast<std::int32_t>(readU32(entry + kEntryCountOffset, 0)));
            *outX = readU32(entry + kEntryTouch0XOffset, kUnreadableU32);
            *outY = readU32(entry + kEntryTouch0YOffset, kUnreadableU32);
            *outEntryIndex = i;
            *outSampling = sampling;
        }
    }
    return found;
}

} // namespace touch_pointer_detail

#if defined(__SWITCH__)

namespace touch_pointer_detail {

// 取一个 u32/u64：先判可读、再取值（委托给框架层）。
// 读不到时返回 `fallback`（绝不崩、也不返回"半个值"）。
// ⚠️ 调用方必须传"会让判据判否"的 `fallback`：把读不到当成 0，会让 `count` 假成"没有手指"，
// 看起来与"真的没按"一模一样。
inline std::uint32_t ReadU32(std::uintptr_t address, std::uint32_t fallback) noexcept {
    std::uint32_t value = fallback;
    if (!engine_memory::ReadAt(address, &value, &engine_memory::EngineMemoryReadable)) {
        return fallback;
    }
    return value;
}
inline std::uint64_t ReadU64(std::uintptr_t address, std::uint64_t fallback) noexcept {
    std::uint64_t value = fallback;
    if (!engine_memory::ReadAt(address, &value, &engine_memory::EngineMemoryReadable)) {
        return fallback;
    }
    return value;
}

// 设备侧的判据 = 纯逻辑那段 + 框架读原语。
inline bool LooksLikeHidSharedMemory(std::uintptr_t base, std::uint64_t size) noexcept {
    return LooksLikeTouchScreenLifo(&ReadU64, &ReadU32, base, size);
}

// 找到的共享内存基址（0 = 还没找到）。一次扫描后缓存，不是每帧扫。
inline std::uintptr_t g_shmemBase = 0;
// 扫描失败后，隔多少次读再试一次（游戏可能在我们的模块起来之后才建立 hid 会话）。
constexpr std::uint32_t kRescanIntervalReads = 60;

// 遍历本进程映射表，找出 hid 的共享内存。
// 用 `svcQueryMemory` 成功时给出的"整段映射"直接跳段（不是逐页问）：段数少、开销可忽略
// （既有实测：一次 `svcQueryMemory` 约 0.5 µs）。返回 0 = 没找到。
inline std::uintptr_t FindHidSharedMemory() noexcept {
    std::uint64_t address = 0;
    // Switch 用户态地址空间上限（39 位）。到顶就停，避免回绕成死循环。
    constexpr std::uint64_t kUserSpaceLimit = 0x8000000000ULL;
    constexpr std::uint32_t kSegmentCap = 100000;
    std::uint32_t segments = 0;
    std::uint32_t rejected = 0;
    while (address < kUserSpaceLimit && segments < kSegmentCap) {
        MemoryInfo info{};
        u32 pageInfo = 0;
        if (R_FAILED(svcQueryMemory(&info, &pageInfo, address))) {
            break;
        }
        if (info.size == 0) {
            break;
        }
        ++segments;
        const std::uintptr_t base = static_cast<std::uintptr_t>(info.addr);
        if ((info.perm & Perm_R) != 0) {
            if (LooksLikeHidSharedMemory(base, info.size)) {
                // 把"我们凭什么认出它"记下来 —— 零页在 `buffer_count` 这一条上必然露馅。
                g_TouchPointerLifoBufferCount.store(static_cast<std::uint32_t>(
                    ReadU64(base + kTouchScreenLifoOffset + kHeaderBufferCountOffset, kUnreadableU32)));
                g_TouchPointerLifoTail.store(static_cast<std::uint32_t>(
                    ReadU64(base + kTouchScreenLifoOffset + kHeaderTailOffset, kUnreadableU32)));
                g_TouchPointerLifoCount.store(static_cast<std::uint32_t>(
                    ReadU64(base + kTouchScreenLifoOffset + kHeaderCountOffset, kUnreadableU32)));
                g_TouchPointerRejectedMappings.store(rejected);
                g_TouchPointerSegmentsScanned.store(segments);
                return base;
            }
            ++rejected;
        }
        address = info.addr + info.size;
    }
    g_TouchPointerRejectedMappings.store(rejected);
    g_TouchPointerSegmentsScanned.store(segments);
    return 0;
}

} // namespace touch_pointer_detail

#endif // __SWITCH__

// 读一帧触摸。任何失败都不抛错、不崩，只记诊断量并返回"没按下"。
inline TouchPointerSnapshot ReadTouchPointer() noexcept {
#if defined(__SWITCH__)
    namespace detail = touch_pointer_detail;
    if (detail::g_shmemBase == 0) {
        // 还没找到 ⇒ 隔一段时间重试一次（游戏可能比我们晚建立 hid 会话）。
        const std::uint32_t reads = g_TouchPointerPollFrames.fetch_add(1);
        if (reads % detail::kRescanIntervalReads != 0) {
            return TouchPointerSnapshot{false, g_TouchPointerLastRawX.load(),
                                        g_TouchPointerLastRawY.load()};
        }
        g_TouchPointerScanAttempts.fetch_add(1);
        detail::g_shmemBase = detail::FindHidSharedMemory();
        if (detail::g_shmemBase == 0) {
            g_TouchPointerInitState.store(static_cast<std::uint32_t>(TouchPointerInitState::kFailed));
            return TouchPointerSnapshot{false, g_TouchPointerLastRawX.load(),
                                        g_TouchPointerLastRawY.load()};
        }
        g_TouchPointerInitState.store(static_cast<std::uint32_t>(TouchPointerInitState::kReady));
        const std::uintptr_t found = detail::g_shmemBase;
        g_TouchPointerShmemLow.store(static_cast<std::uint32_t>(found & 0xFFFFFFFFULL));
        g_TouchPointerShmemHigh.store(static_cast<std::uint32_t>(found >> 32));
    } else {
        g_TouchPointerPollFrames.fetch_add(1);
    }
    std::uint32_t x = 0;
    std::uint32_t y = 0;
    std::uint32_t count = 0;
    std::uint32_t entryIndex = 0;
    std::uint64_t sampling = 0;
    if (!detail::ReadNewestTouchFrom(&detail::ReadU64, &detail::ReadU32, detail::g_shmemBase,
                                     &x, &y, &count, &entryIndex, &sampling)) {
        // 一条带采样号的条目都没有 ⇒ 这块内存没在被写（不是"没人在按"）。
        // 把采样号记成 0，读数的判据靠它区分这两种情况。
        g_TouchPointerLastSampling.store(0);
        return TouchPointerSnapshot{false, g_TouchPointerLastRawX.load(),
                                    g_TouchPointerLastRawY.load()};
    }
    // 采样号低 32 位 + 槽位号：判"这块内存是活的"（两次读数之间应当变化）。
    g_TouchPointerLastSampling.store(static_cast<std::uint32_t>(sampling & 0xFFFFFFFFULL));
    g_TouchPointerLastEntryIndex.store(entryIndex);
    if (count == 0) {
        // 没有手指：位置保持上一次的值（与 PC 的"鼠标不动"一致）。
        return TouchPointerSnapshot{false, g_TouchPointerLastRawX.load(),
                                    g_TouchPointerLastRawY.load()};
    }
    g_TouchPointerLastRawX.store(x);
    g_TouchPointerLastRawY.store(y);
    g_TouchPointerLastCount.store(count);
    g_TouchPointerTouchFrames.fetch_add(1);
    return TouchPointerSnapshot{true, x, y};
#else
    // 宿主机（门禁夹具）：没有触摸屏、也没有 `svcQueryMemory`，老实回答"没按下"，**不做任何事**。
    // ⇒ 宿主门禁验的是**判据与布局**（`LooksLikeTouchScreenLifo` / `ReadNewestTouchFrom`，
    //    它们是纯逻辑、直接可测），真值一律真机（与引擎返回值同一性质）。
    return TouchPointerSnapshot{false, 0, 0};
#endif
}

// 会话重置（换局/重载模组时把"上一次位置"清掉，免得新会话第一次读就用旧坐标）。
inline void ResetTouchPointer() noexcept {
    g_TouchPointerPollFrames.store(0);
    g_TouchPointerTouchFrames.store(0);
    g_TouchPointerLastRawX.store(0);
    g_TouchPointerLastRawY.store(0);
    g_TouchPointerLastCount.store(0);
    g_TouchPointerLastSampling.store(0);
    g_TouchPointerLastEntryIndex.store(0);
    // 找到的共享内存基址、扫描结果与 lifo 表头刻意不重置：那块映射是进程级的，
    // 而且重置成"没找到"只会让下一次读白扫一遍映射表（几十万次内核查询）。
}

} // namespace isaac::runtime
