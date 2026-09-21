// 探针：能不能把游戏自己那套模组菜单叫出来。设计与用法见同名 .hpp。
//
// 本 TU 只在 `PROBE_BREAK=1` 且 `PROBE_BREAK_NATIVE_MODS_MENU=1` 时编译（生产包不含它）。

#include "native_mods_menu_probe.hpp"

#if defined(EXL_PROBE_BREAK) && EXL_PROBE_BREAK_NATIVE_MODS_MENU

#include "lua_runtime_state.hpp"  // `InputIsActionPressedThunk()`
#include "mod_page_entries.hpp"
#include "module_finder.hpp"

#include <array>
#include <cstdint>
#include <cstring>
#include <optional>

namespace isaac::runtime::probe {

//: 诊断面（**非匿名命名空间**：读数工具按 mangled 名直接读它，与 `ImagePcxDiagnostics` 同一做法）。
//: 布局固定，字段顺序**不要改**（要加就往后加），读数工具按偏移解析。
struct NativeModsMenuProbeState {
    std::uint32_t armed;
    std::uint32_t presses;
    std::uint32_t backPresses;
    std::uint32_t state;
    std::uint32_t manualMode;
    std::uint32_t initResult;
    std::uint32_t renderCalls;
    std::uint32_t lastFailure;
    std::uint32_t managerOk;
    std::uint32_t menuManagerOk;
    std::uint32_t modListBytes;
    std::uint32_t menuState;
    std::uint32_t heldActionMask;
    std::uint32_t heldControllerMask;
    std::uint32_t scanRounds;
    std::uint32_t modListPointersOk;
    std::uint32_t manualModsPtrOk;
};
NativeModsMenuProbeState g_NativeModsMenuProbeState{
    1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0};

namespace {

// ─────────────────────────────────────────────────────────────────────────────
// 偏移与入口指纹（2026-09-21 从 `Repentance.nro` 逐字节取出，`tools/nro_disasm.py` 可复核）
// ─────────────────────────────────────────────────────────────────────────────
//
// 单例都是**经 GOT 槽的两级取值**，`Menu_Mods::Init` 的原话可作模板：
//
//     00410164  adrp x8, 0xaad000
//     00410168  ldr  x8, [x8, #0x1b0]   ; 槽 → &g_MenuManager（模块内 bss 0xABCD48）
//     0041016c  ldr  x0, [x8]           ; 再取一次才是 MenuManager*
//
// 槽号 0xAAD1B0 / 0xAAC648 都在重定位表里登记过（分别对应 `g_MenuManager` / `g_Manager`），
// 是加载器写进去的，所以这两条读法是"加载器保证"的，不是我们猜的。
constexpr std::uintptr_t kMenuManagerSlotOffset = 0xAAD1B0;
constexpr std::uintptr_t kManagerSlotOffset = 0xAAC648;
// `g_Manager` 里"引擎自己那份模组表"的偏移（与运行时的 `kManagerToModManagerOffset` 同一个数）。
constexpr std::uintptr_t kManagerModsOffset = 0x36800;
// `MenuManager::eState` 就在 `MenuManager+0x38`：`Update` 里是 `ldr w8,[x19,#0x38]`，
// `SetState` 结尾是 `str w19,[x20,#0x38]`。读数里顺手记一格，用来在真机上核对状态机的位置。
constexpr std::uintptr_t kMenuManagerStateOffset = 0x38;

// ── 第三版（2026-09-22）：**自己造条目喂给原生页** ──────────────────────────────
//
// `Menu_Mods::Render` 要的数据结构（静态已确认，见 `.hpp`）：
//   * `g_Manager + 0x36800` 起三个字 = `std::vector<条目指针>` 的 begin / end / cap；
//   * 每个条目 `+0x18` 是 libc++ `std::string`（**长串形态**：字节 0 的 bit0 = 1、
//     `+0x28` 处放 `char*`）、`+0x138` 启用位、`+0x13a` "旧版"位。
// 本版先用**固定测试名**验"能不能列出来、位置对不对"，不接清单（下一步再接 metadata.xml 的 `<name>`）。
constexpr std::uintptr_t kManagerModsVectorOffset = 0x36800;
// `Menu_Title` 是 `MenuManager` 的**内嵌成员**（`Update` 里是 `add x0, x19, #0x670`），
// 它的位置（Vector2，两个 float）就在成员开头 ⇒ 拿它当原生页的位置参数（第三版修"位置偏上"）。
constexpr std::uintptr_t kMenuTitleOffset = 0x670;
// 条目：0x140 字节足够（用到的最高偏移是 0x13a），16 字节对齐。
constexpr std::uintptr_t kEntrySize = 0x140;
constexpr std::uintptr_t kEntryStringOffset = 0x18;  // libc++ std::string 起始
constexpr std::uintptr_t kEntryEnabledOffset = 0x138;
constexpr std::uintptr_t kEntryOldOffset = 0x13a;
constexpr std::uint32_t kProbeEntryCount = 3;

// 输入扫描范围（第二版）：`ButtonAction` 的号都小于 28；手柄号实测出现过 33，所以扫到 63。
constexpr std::uint32_t kScanActions = 28;
constexpr std::uint32_t kScanControllers = 64;
// 每 8 帧扫一轮（一轮 28×64 = 1792 次查询，摊到 8 帧上可以忽略）。按键是**按住**语义，
// 持续几十帧，所以 7.5 Hz 的采样不会漏。
constexpr std::uint32_t kScanEveryNthUpdate = 8;

// `void MenuManager::SetState(eState)`。
constexpr std::uintptr_t kSetStateOffset = 0x3FE4DC;
constexpr std::array<std::uint8_t, 16> kSetStateExpected = {
    0xFD, 0x7B, 0xBD, 0xA9, 0xF5, 0x0B, 0x00, 0xF9,
    0xFD, 0x03, 0x00, 0x91, 0xF4, 0x4F, 0x02, 0xA9,
};

// `Menu_Mods::Menu_Mods()` / `Init(const KAGE::Math::Vector2&)` / `Render()`。
constexpr std::uintptr_t kMenuModsCtorOffset = 0x41008C;
constexpr std::array<std::uint8_t, 16> kMenuModsCtorExpected = {
    0xFD, 0x7B, 0xBE, 0xA9, 0xF3, 0x0B, 0x00, 0xF9,
    0xFD, 0x03, 0x00, 0x91, 0xF3, 0x03, 0x00, 0xAA,
};
constexpr std::uintptr_t kMenuModsInitOffset = 0x4100C4;
constexpr std::array<std::uint8_t, 16> kMenuModsInitExpected = {
    0xFF, 0x43, 0x01, 0xD1, 0xFD, 0x7B, 0x02, 0xA9,
    0xFD, 0x83, 0x00, 0x91, 0xF5, 0x1B, 0x00, 0xF9,
};
constexpr std::uintptr_t kMenuModsRenderOffset = 0x4107C4;
constexpr std::array<std::uint8_t, 16> kMenuModsRenderExpected = {
    0xFF, 0x03, 0x06, 0xD1, 0xEC, 0x7B, 0x00, 0xFD,
    0xEB, 0x2B, 0x10, 0x6D, 0xE9, 0x23, 0x11, 0x6D,
};

// `ButtonAction`：这两个键主菜单自己不用（它只认上下左右/A/B/START 之类），不会被抢走。
constexpr std::uint32_t kActionItem = 9;       // Switch 上的 ZR
constexpr std::uint32_t kActionPillCard = 10;  // Switch 上的 ZL

//: `MenuManager::eState` 的上界。静态表（`Update` 的分发表，`cmp w8,#0xf` + 字节跳表）是
//: 0..15，逐格都对得上具体页面：
//:   1 Menu_Title(+0x670)   2 Menu_Save(+0x7d8)      3 Menu_Game(+0x813A0)
//:   4 DailyChallenge(+0x817F0)  5 Character(+0x1A2658)  6 SpecialSeed(+0x1A3A70)
//:   7 Challenge(+0x1A3C28) 8 Collection(+0x1A3DA8)  9 Stats(+0x1A40B0)
//:  10 Options(+0x1AF1E8)  11 ControllerSelect(+0x1AF4E8) 12 KeyConfig(+0x1AF668)
//:  13 Cutscenes(+0x1AF7D8) 14 Bestiary(+0x1AF940)  15 Custom_Challenge(+0x1AFDA0)
//: 状态 0 走默认分支（什么都不做），**没有模组页那一格**。
constexpr std::uint32_t kLastState = 15;

// 失败码（写进诊断字 [7]，读数里一眼看出卡在哪一步）。
enum : std::uint32_t {
    kFailureNone = 0,
    kFailureInputUnavailable = 1,
    kFailureModuleNotFound = 2,
    kFailureSetStateGuard = 3,
    kFailureMenuManagerNull = 4,
    kFailureMenuModsGuard = 5,
    kFailureRenderGuard = 6,
    kFailureEntryBuild = 7,   // 条目没造出来（名字区/参数不合法）⇒ 整体放弃，不让页面看到半截结构
};

// `initResult` 的取值（诊断字 [5]）。
enum : std::uint32_t {
    kInitNotTried = 0,
    kInitOk = 1,
    kInitGuardMismatch = 2,
    kInitMenuManagerNull = 3,
    kInitModuleNotFound = 4,
};

// 手动模式的临时对象：`Menu_Mods` 是 `MenuManager` 的内嵌成员（大小未知），所以这里给一块
// 足够宽、**静态零初始化**的内存当壳。只在探针里这么干：生产路径永远用引擎自己那块对象。
// 静态已确认的布局：`+0x08` Vector2、`+0x10` ANM2、`+0x168` 字节、`+0x170` u64
// ⇒ 0x800 足够，且四者都落在零初始化内存里（与 `ctor` 的初始化效果一致）。
alignas(16) std::uint8_t g_ManualObject[0x800]{};
float g_ManualPosition[2] = {0.0F, 0.0F};  // `KAGE::Math::Vector2` = 两个 float

//: 三个自造条目（名字固定）、它们的指针数组、以及名字缓冲。**静态零初始化**，不写堆。
//: 条目数组与"名字"分开放：名字必须 NUL 结尾的 C 串（`Render` 只当 C 串用）。
alignas(16) std::uint8_t g_ProbeEntries[kProbeEntryCount][kEntrySize]{};
std::uintptr_t g_ProbeEntryPointers[kProbeEntryCount]{};
//: `begin/end/cap` 三个字（8 字节对齐，`memcpy` 进引擎结构）。
alignas(8) std::uintptr_t g_ProbeVector[3]{};
//: 名字副本（必须是我们自己拥有的稳定内存 —— 不能指向字面量）。
char g_ProbeNameArena[128]{};
std::uint32_t g_VectorWritten = 0;

//: 造好条目、写好指针数组，并把 `begin/end/cap` 三个字写进 `g_Manager + 0x36800`。
//: **必须在 `Init` 之前做**：`Init` 会把 begin 抄进 `对象+0x170`（`Update` 用它翻转启用位）。
//: 布局本身由 `mod_page_entries.hpp` 负责（那里逐字节被宿主门禁钉住）—— 本函数只负责"接线"。
void WriteProbeModsVector(const TargetModule& module, std::uintptr_t manager) {
    if (g_VectorWritten != 0) {
        return;
    }
    // 三个测试条目**故意覆盖三条显示分支**：正常 / 停用（另一种颜色）/ 启用+"旧版"（名字后拼 `[Old]`）。
    const isaac::runtime::ModPageEntrySource sources[kProbeEntryCount] = {
        {"PROBE-MOD-A", true, false},
        {"PROBE-MOD-B", false, false},
        {"PROBE-MOD-C", true, true},
    };
    std::size_t nameBytes = 0;
    if (isaac::runtime::BuildModPageEntries(
            &g_ProbeEntries[0][0], &g_ProbeEntryPointers[0], g_ProbeVector,
            kProbeEntryCount, sources, g_ProbeNameArena, sizeof(g_ProbeNameArena),
            &nameBytes) != kProbeEntryCount) {
        g_NativeModsMenuProbeState.lastFailure = kFailureEntryBuild;
        return;  // 制造失败就整体放弃：绝不让页面读到半截结构
    }
    std::memcpy(reinterpret_cast<void*>(manager + kManagerModsVectorOffset), g_ProbeVector,
                sizeof(g_ProbeVector));
    g_VectorWritten = 1;
}

//: 原生页的位置参数：拿 `Menu_Title` 内嵌成员开头那两个 float（第三版修"位置偏上"）。
void ReadTitleMenuPosition(const TargetModule& module, std::uintptr_t manager, float* out) {
    if (out == nullptr) {
        return;
    }
    const std::uintptr_t title = manager + kMenuTitleOffset;
    float x = 0.0F;
    float y = 0.0F;
    std::memcpy(&x, reinterpret_cast<const void*>(title), sizeof(x));
    std::memcpy(&y, reinterpret_cast<const void*>(title + sizeof(x)), sizeof(y));
    // 位置读出来明显不合理（NaN/极大）时退回 (0,0)：宁可位置偏，也不要让引擎拿垃圾值去画。
    if (!(x > -100000.0F && x < 100000.0F) || !(y > -100000.0F && y < 100000.0F)) {
        out[0] = 0.0F;
        out[1] = 0.0F;
        return;
    }
    out[0] = x;
    out[1] = y;
    (void)module;
}

// 上一帧的两个键：**自己算边沿**。引擎那份"刚按下"状态在我们跑到它的时候是空的
// （这条结论写在 `input_api.cpp` 里），所以沿用"按住"位图 + 自记状态。
std::uint32_t g_LastItem = 0;
std::uint32_t g_LastPillCard = 0;
std::uint32_t g_ComboLatched = 0;
// 自己的帧计数（只用来决定"该不该扫一轮输入"，与引擎帧计数无关）。
std::uint32_t g_UpdateCount = 0;
//: 自动驱动只做一次（第二版）：理由见 `.hpp` 的"第二版"一节。
std::uint32_t g_AutoStarted = 0;

//: 与 `input_api.cpp` 同一个调用形状（那处是权威）：第一个参数被跳板覆盖，动作号进 x1、
//: 手柄号进 x2、第三个引擎参数（PC 的可选 `entity`）一律给空指针。
using ActionQueryFn = bool (*)(void*, std::uint32_t, std::uint32_t, void*);

//: "任一控制器答'是'" —— 第二版的关键修正：**不再假设手柄号是 0**。
//: 项目历史结论（2026-09-16 的 021）是"引擎只认玩家自己的 controller 值（实测出现过 33）"，
//: 第一版就栽在这上面（真机读数里按键计数全 0，而更新中继确实在跑）。
//:
//: ★ 第三版修正（2026-09-22，本轮静态查证）：**游戏自己的菜单代码用的是 `0xFFFFFFFF`**
//: ——`Menu_Title::Update @0x41A4F0` 里是 `mov w2, #-1`（controller）+ `mov w1, #0xe`（动作
//: MENUCONFIRM）再调 `IsActionPressed/IsButtonTriggered`。"任意手柄"这个值我们以前没用过，
//: 而第二版的扫描范围只到 63 ⇒ **下一轮真机还会漏**。现在把它单独问一次（并且只问一次，
//: 因为它的语义是"任意"，不需要按手柄号循环）。
constexpr std::uint32_t kAnyController = 0xFFFFFFFFu;

bool HeldByAnyone(const ActionQueryFn query, std::uint32_t action) {
    if (query(nullptr, action, kAnyController, nullptr)) {
        return true;
    }
    for (std::uint32_t controller = 0; controller < kScanControllers; ++controller) {
        if (query(nullptr, action, controller, nullptr)) {
            return true;
        }
    }
    return false;
}

//: 每 `kScanEveryNthUpdate` 帧扫一轮"动作号 × 手柄号"，把结果记成两张掩码。
//: 这不是为了"让某个键生效"，而是为了**下一次不必再猜**：掩码直接告诉我们
//: 哪些动作号会被按住、哪些手柄号会答"是"。
void ScanInput(const ActionQueryFn query) {
    std::uint32_t actions = 0;
    std::uint32_t controllers = 0;
    for (std::uint32_t action = 0; action < kScanActions; ++action) {
        // `0xFFFFFFFF`（任意手柄）单独问一次；答"是"就把它记在第 31 位，读数里一眼看得出来
        // （0..30 位留给真实手柄号）。
        if (query(nullptr, action, kAnyController, nullptr)) {
            actions |= 1u << action;
            controllers |= 1u << 31;
        }
        for (std::uint32_t controller = 0; controller < kScanControllers; ++controller) {
            if (!query(nullptr, action, controller, nullptr)) {
                continue;
            }
            actions |= 1u << action;
            if (controller < 32) {
                controllers |= 1u << controller;
            }
        }
    }
    g_NativeModsMenuProbeState.heldActionMask = actions;
    g_NativeModsMenuProbeState.heldControllerMask = controllers;
    ++g_NativeModsMenuProbeState.scanRounds;
}

bool Guarded(const TargetModule& module, std::uintptr_t offset,
             const std::array<std::uint8_t, 16>& expected, std::uintptr_t* address) {
    if (module.size < expected.size() || offset > module.size - expected.size()) {
        return false;
    }
    const std::uintptr_t candidate = module.base + offset;
    if (candidate < module.base || candidate + expected.size() > module.base + module.size) {
        return false;
    }
    if (std::memcmp(reinterpret_cast<const void*>(candidate), expected.data(),
                    expected.size()) != 0) {
        return false;
    }
    *address = candidate;
    return true;
}

//: 读一个 GOT 槽里存的东西（= 加载器解析出来的地址）。槽本身必须落在模块映像内。
bool ReadSlot(const TargetModule& module, std::uintptr_t slotOffset, std::uintptr_t* value) {
    if (module.size < sizeof(std::uintptr_t) ||
        slotOffset > module.size - sizeof(std::uintptr_t)) {
        return false;
    }
    const std::uintptr_t slot = module.base + slotOffset;
    if (slot < module.base || slot + sizeof(std::uintptr_t) > module.base + module.size) {
        return false;
    }
    std::memcpy(value, reinterpret_cast<const void*>(slot), sizeof(*value));
    return true;
}

//: 单例的两级取值（槽 → 全局变量地址 → 值）。返回 false = 这条链不成立，**不许再往下用**。
bool ReadSingleton(const TargetModule& module, std::uintptr_t slotOffset, std::uintptr_t* out) {
    std::uintptr_t global = 0;
    if (!ReadSlot(module, slotOffset, &global) || global == 0) {
        return false;
    }
    // 全局变量本身在模块的 bss 里（例如 `g_MenuManager` 在 0xABCD48），所以这里只做
    // 非空与对齐检查，不要求它落在映像内：超出映像尾部的那段正是 bss。
    if ((global & (sizeof(std::uintptr_t) - 1)) != 0) {
        return false;
    }
    std::uintptr_t value = 0;
    std::memcpy(&value, reinterpret_cast<const void*>(global), sizeof(value));
    if (value == 0) {
        return false;
    }
    *out = value;
    return true;
}

bool Edge(std::uint32_t* last, bool now) {
    const bool pressed = now && *last == 0;
    *last = now ? 1U : 0U;
    return pressed;
}

//: 引擎自己那份模组表：`g_Manager + 0x36800` 的 begin/end 指针对（`Render` 用它算行数）。
//: **只读这对指针**，不碰任何一项（`ListMods()` 那种遍历在真机会中断）。
void RefreshEngineModList(const TargetModule& module) {
    std::uintptr_t manager = 0;
    if (!ReadSingleton(module, kManagerSlotOffset, &manager)) {
        g_NativeModsMenuProbeState.managerOk = 0;
        g_NativeModsMenuProbeState.modListBytes = 0;
        return;
    }
    g_NativeModsMenuProbeState.managerOk = 1;
    const std::uintptr_t beginAddress = manager + kManagerModsOffset;
    std::uintptr_t begin = 0;
    std::uintptr_t end = 0;
    std::memcpy(&begin, reinterpret_cast<const void*>(beginAddress), sizeof(begin));
    std::memcpy(&end, reinterpret_cast<const void*>(beginAddress + sizeof(begin)), sizeof(end));
    // `begin`/`end` 该是一对合法指针（模块映像之外的那部分就是引擎自己堆上的模组表）。
    // ★ 为什么要单独记这一格：如果两个值根本不像指针，那 [10] 的 0 **不能**读成"空表" ——
    // 那只说明我们对 `Manager+0x36800` 这个结构的解释不对，得回去重新看静态证据。
    const bool pointerLike = begin >= 0x1000 && end >= 0x1000 &&
                            (begin & 7u) == 0 && (end & 7u) == 0 && end >= begin;
    g_NativeModsMenuProbeState.modListPointersOk = pointerLike ? 1U : 0U;
    if (!pointerLike) {
        g_NativeModsMenuProbeState.modListBytes = 0;
        return;
    }
    const std::uintptr_t bytes = end - begin;
    g_NativeModsMenuProbeState.modListBytes =
        bytes > 0xFFFFFFFFULL ? 0xFFFFFFFFU : static_cast<std::uint32_t>(bytes);
}

void ApplyState(const TargetModule& module, std::uint32_t state) {
    std::uintptr_t manager = 0;
    if (!ReadSingleton(module, kMenuManagerSlotOffset, &manager)) {
        g_NativeModsMenuProbeState.lastFailure = kFailureMenuManagerNull;
        return;
    }
    std::uintptr_t setState = 0;
    if (!Guarded(module, kSetStateOffset, kSetStateExpected, &setState)) {
        g_NativeModsMenuProbeState.lastFailure = kFailureSetStateGuard;
        return;
    }
    using SetStateFn = void (*)(void*, std::int32_t);
    reinterpret_cast<SetStateFn>(setState)(reinterpret_cast<void*>(manager),
                                           static_cast<std::int32_t>(state));
    g_NativeModsMenuProbeState.lastFailure = kFailureNone;
}

//: 手动模式开起来时的**一次性** `ctor` + `Init`。放在 update 中继里做，不放 Present 前中继：
//: `Init` 会加载 ANM2、还会调一次 `MenuManager::SetChallengeOffset`，不该插在渲染中途。
void TryInitManualPage(const TargetModule& module) {
    std::uintptr_t manager = 0;
    if (!ReadSingleton(module, kMenuManagerSlotOffset, &manager)) {
        g_NativeModsMenuProbeState.menuManagerOk = 0;
        g_NativeModsMenuProbeState.lastFailure = kFailureMenuManagerNull;
        g_NativeModsMenuProbeState.initResult = kInitMenuManagerNull;
        return;
    }
    g_NativeModsMenuProbeState.menuManagerOk = 1;
    std::uintptr_t ctor = 0;
    std::uintptr_t init = 0;
    if (!Guarded(module, kMenuModsCtorOffset, kMenuModsCtorExpected, &ctor) ||
        !Guarded(module, kMenuModsInitOffset, kMenuModsInitExpected, &init)) {
        g_NativeModsMenuProbeState.lastFailure = kFailureMenuModsGuard;
        g_NativeModsMenuProbeState.initResult = kInitGuardMismatch;
        return;
    }
    using CtorFn = void (*)(void*);
    using InitFn = void (*)(void*, const float*);
    // 先把自造条目挂进 `g_Manager + 0x36800`（必须在 Init 之前），再按标题菜单的位置初始化。
    WriteProbeModsVector(module, manager);
    ReadTitleMenuPosition(module, manager, g_ManualPosition);
    reinterpret_cast<CtorFn>(ctor)(g_ManualObject);
    reinterpret_cast<InitFn>(init)(g_ManualObject, g_ManualPosition);
    // `Init` 的最后一步就是把 `*(g_Manager+0x36800)` 存进 `对象+0x170`（静态已确认）。
    // 读回来非空 ⇒ **我们这次调用真的进了函数体并跑到底**，而不是"跳进去什么都没发生"。
    std::uintptr_t mods = 0;
    std::memcpy(&mods, g_ManualObject + 0x170, sizeof(mods));
    g_NativeModsMenuProbeState.manualModsPtrOk = mods != 0 ? 1U : 0U;
    g_NativeModsMenuProbeState.initResult = kInitOk;
    g_NativeModsMenuProbeState.lastFailure = kFailureNone;
}

}  // namespace

void NativeModsMenuProbeUpdate() noexcept {
    const std::optional<TargetModule> module = FindTargetModule();
    if (!module.has_value()) {
        g_NativeModsMenuProbeState.lastFailure = kFailureModuleNotFound;
        return;
    }
    ++g_UpdateCount;
    RefreshEngineModList(*module);

    // `g_MenuManager` 是手动 Init 的前置条件，每帧顺手记一格（它随菜单生命周期出现/消失），
    // 顺便把状态机当前状态（`MenuManager+0x38`）也记下来核对静态表。
    std::uintptr_t manager = 0;
    const bool menuManagerOk = ReadSingleton(*module, kMenuManagerSlotOffset, &manager);
    g_NativeModsMenuProbeState.menuManagerOk = menuManagerOk ? 1U : 0U;
    if (menuManagerOk && manager != 0) {
        std::uint32_t state = 0;
        std::memcpy(&state, reinterpret_cast<const void*>(manager + kMenuManagerStateOffset),
                    sizeof(state));
        g_NativeModsMenuProbeState.menuState = state & 0xFFFFU;
    }

    // ★ 第二版：**自动驱动**。只要已经在菜单里（`g_MenuManager` 非空），就自己把原生页
    // 开起来 —— 第一版挂在组合键上，而"猜对按键"这件事本身就是风险（真机已证实会猜错）。
    if (menuManagerOk && g_AutoStarted == 0) {
        g_AutoStarted = 1;
        g_NativeModsMenuProbeState.manualMode = 1;
        g_NativeModsMenuProbeState.initResult = kInitNotTried;
        g_NativeModsMenuProbeState.renderCalls = 0;
    }
    if (g_NativeModsMenuProbeState.manualMode == 1 &&
        g_NativeModsMenuProbeState.initResult == kInitNotTried) {
        TryInitManualPage(*module);
    }

    const std::uintptr_t thunk = LuaRuntime::InputIsActionPressedThunk();
    if (thunk == 0) {
        g_NativeModsMenuProbeState.lastFailure = kFailureInputUnavailable;
        return;
    }
    const auto query = reinterpret_cast<ActionQueryFn>(thunk);
    if (g_UpdateCount % kScanEveryNthUpdate == 0) {
        ScanInput(query);
    }

    // 组合键（ZR+ZL 同时按住，**任一手柄号**答是即算按下）⇒ 开关"手动画原生页"。
    // 自动驱动已经把它打开了，所以这里的作用是"能关掉 / 再打开"。
    const bool item = HeldByAnyone(query, kActionItem);
    const bool pill = HeldByAnyone(query, kActionPillCard);
    const bool itemEdge = Edge(&g_LastItem, item);
    const bool pillEdge = Edge(&g_LastPillCard, pill);

    if (item && pill) {
        if (g_ComboLatched == 0) {
            g_ComboLatched = 1;
            const std::uint32_t next = g_NativeModsMenuProbeState.manualMode == 0 ? 1U : 0U;
            g_NativeModsMenuProbeState.manualMode = next;
            g_NativeModsMenuProbeState.initResult = kInitNotTried;
            g_NativeModsMenuProbeState.renderCalls = 0;
        }
        return;
    }
    g_ComboLatched = 0;

    if (itemEdge) {
        const std::uint32_t next =
            (g_NativeModsMenuProbeState.state + 1U) % (kLastState + 1U);
        g_NativeModsMenuProbeState.state = next;
        ++g_NativeModsMenuProbeState.presses;
        ApplyState(*module, next);
        return;
    }
    if (pillEdge) {
        const std::uint32_t current = g_NativeModsMenuProbeState.state;
        const std::uint32_t next = current == 0 ? kLastState : current - 1U;
        g_NativeModsMenuProbeState.state = next;
        ++g_NativeModsMenuProbeState.backPresses;
        ApplyState(*module, next);
    }
}

void NativeModsMenuProbeBeforePresent() noexcept {
    if (g_NativeModsMenuProbeState.manualMode == 0 ||
        g_NativeModsMenuProbeState.initResult != kInitOk) {
        return;
    }
    const std::optional<TargetModule> module = FindTargetModule();
    if (!module.has_value()) {
        g_NativeModsMenuProbeState.lastFailure = kFailureModuleNotFound;
        return;
    }
    std::uintptr_t render = 0;
    if (!Guarded(*module, kMenuModsRenderOffset, kMenuModsRenderExpected, &render)) {
        g_NativeModsMenuProbeState.lastFailure = kFailureRenderGuard;
        return;
    }
    using RenderFn = void (*)(void*);
    reinterpret_cast<RenderFn>(render)(g_ManualObject);
    ++g_NativeModsMenuProbeState.renderCalls;
    g_NativeModsMenuProbeState.lastFailure = kFailureNone;
}

}  // namespace isaac::runtime::probe

#endif  // EXL_PROBE_BREAK && EXL_PROBE_BREAK_NATIVE_MODS_MENU
