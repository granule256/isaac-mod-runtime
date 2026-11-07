#pragma once

#include <array>
#include <atomic>
#include <cstddef>
#include <cstdint>

// ============================================================================
// 原生右上角小地图的触摸门控
// ============================================================================
//
// 用户诉求（原话）：「原本的 ns 自己的右上角小地图是**全局触摸**都会影响到这个小地图，
// 能不能改成**局部触摸**的」。
//
// 现象与根因（已由父线程用 Ghidra 反汇编确认，本处只复述结论）：Switch 版游戏自己有一整套
// 触摸处理，手指在屏幕上拖动会平移/缩放右上角的**原生小地图**；而 `Minimap::Update` 的门控
// **只看"手指 ID 与上一帧相同"，不看手指在哪** ⇒ 任意位置的拖动都会动它 ——
// 玩 GoodTrip 的地图时会被它干扰（双击/拖动地图时原生小地图跟着乱跑）。
//
// 本补丁只改 `Minimap::Update`（模块内偏移 0x41cb44 起）里的**三条指令**，一个字节都不多写。
//
// ---------------------------------------------------------------------------
// 三处（偏移都是**模块内偏移**，相对 `game_base`；机器码已用 devkitA64 真汇编器核对）
// ---------------------------------------------------------------------------
//
//   #1 0x41ccc4  mov w20, #0x1            → nop
//        去掉"中间游戏区（四周各留 70px）"对 `w20` 的置位 ⇒ `w20` 只剩"手指在右上角
//        小地图矩形内"这一个来源（那一处是 0x41cc78 的 `orr w20, w20, w8`，不动）。
//
//   #2 0x41cccc  cbz w8, 0x41cdec         → tbz w20, #0, 0x41cdec
//        拖拽门控改成必须 `w20 != 0`，即"手指当前在小地图矩形内"。
//        语义变化（有意的）：原来是"本帧触摸点数为 0 就跳过"（`w8` 此刻 = 点数）。
//          点数为 0 时上面那个循环根本没跑、`w20` 必然为 0 ⇒ 新指令同样跳过（语义等价），
//          顺带加上了矩形门控。落点一个字都没动（仍是 0x41cdec）。
//
//   #3 0x41ce68  tbz w20, #0, 0x41ce8c   → cbz w8, 0x41ce8c
//        这一处不能删（写清楚是为了防止后人以为它多余而删掉）：
//        `w20` 原本有两个来源 —— 右上角小地图矩形（0x41cc78）与中间游戏区（0x41ccc4）。
//        0x41ce68 那句 `tbz w20, #0` 属于**另一个功能**：「玩家摸屏幕累计 10 次就自动收起
//        道具说明文字」（0x41ce6c 起：计数 +1，到 10 就调 0x67a610）。#1 之后 `w20` 只反映
//        "手指是否在小地图矩形内" ⇒ 若不改 #3，那个功能会变成"**只有摸小地图才收文字**"，
//        等于把用户没要求改的行为改坏。
//        #3 把判据换成**本帧触摸点数**：`w8` 在那一点正好是 0x41ce60 从 `[sp, #960]` 读出的
//        触摸点数（0x41ce64 刚把它存进 `Minimap + 0xb20`）⇒ 功能原样保住。
//
// 2026-10-14 更正：上述 #3 的“独立触摸十次隐藏道具说明”解释错误，保留原文作历史记录。
// 0x41ce88 实际调用 Level::ShowName(true)；Minimap+8 同时是后续长按判定的计数。
// w20 包含 ACTION_MAP 按住或局部小地图触摸，改为只看触摸数使无触摸减号长按计数恒0，
// 松开被当成短按，固定到大图。#3 新值恢复原版 tbz w20，保留三处守卫/诊断布局。
// 前两处局部拖拽补丁仍保留；外部触摸不置w20，其计数在原状态机同帧清零。
//
// 命中区为什么是"固定矩形"：小地图本身不移动（触摸只平移/缩放它的**内容**），所以引擎按
// 屏幕右上角算出来的那个矩形就是它的命中区 —— 宽高由全局 `WIDTH`/`HEIGHT`（两个 GOT 槽
// 0xaac650/0xaac658，值 480.0f/270.0f）算出，约 x∈[400,453]、y∈[16,63]。
//
// 本批刻意不用 `TouchEvent+0x08`（起点）那条路：该字段的语义没有钉死（只看到"新触摸"
//   分支写它）⇒ 不赌。所以口径是"**手指当前在小地图矩形内**时才拖" —— 这已经解决用户的
//   问题（别处触摸不再动它）。
//
// ---------------------------------------------------------------------------
// 写入方式：复用既有机制，不发明第二套
// ---------------------------------------------------------------------------
//
// 每个字的改写都走 `isaac::runtime::relay::TryRewriteCodeWord`
// （`runtime/source/relay/entry_relay.cpp`）：`exl::util::RwPages` 拿可写别名 → 写 →
// `Flush()`（DCache 清 + ICache 失效）→ 用**只读**地址读回校验，与入口中继那条路逐条同形。
//
// ============================================================================

namespace isaac::runtime {

// 一条"单指令"补丁：模块内偏移 + 期望原值 + 新值。
// 三个字段都是口径：改一个字节就会改坏游戏（真机表现为"原生小地图不动/乱动"或
// "摸屏幕不再收道具文字"）。所以它们被 `runtime/tests/test_minimap_touch_gate.py`
// 逐条钉住，并与真汇编器 + 仓库里的游戏镜像交叉核对。
// 2026-10-14 更正：上面的“收道具文字”是历史误解；本计数实际控制长按和ShowName。
struct MinimapTouchGatePatch {
    std::uintptr_t offset;
    std::uint32_t expected;
    std::uint32_t patched;
};

inline constexpr std::size_t kMinimapTouchGatePatchCount = 3;

inline constexpr std::array<MinimapTouchGatePatch, kMinimapTouchGatePatchCount>
    kMinimapTouchGatePatches = {{
        // #1 `mov w20, #0x1`（0x52800034）⇒ `nop`（0xD503201F）
        {0x41CCC4u, 0x52800034u, 0xD503201Fu},
        // #2 `cbz w8, 0x41cdec`（0x34000908）⇒ `tbz w20, #0, 0x41cdec`（0x36000914）
        {0x41CCCCu, 0x34000908u, 0x36000914u},
        // #3 `tbz w20, #0, 0x41ce8c`（0x36000134）⇒ `cbz w8, 0x41ce8c`（0x34000128）
        //    删掉这一处就会弄坏"摸屏幕自动收道具文字"，理由见文件头。
        //    2026-10-14 更正：恢复原版 tbz w20；本处保留校验，不再改动原生长按计数门控。
        {0x41CE68u, 0x36000134u, 0x36000134u},
    }};

// ---------------------------------------------------------------------------
// 诊断量（设备侧读数用；**名字与类型要稳定**）
// ---------------------------------------------------------------------------
//
// 四个数合起来回答"装上没有、为什么没装上"：
//
//   g_MinimapTouchGateState          0 = 还没试；1 = 三处都装上；2 = 有守卫不符 / 写失败
//   g_MinimapTouchGateApplied        成功改写的处数（0..3）
//   g_MinimapTouchGateGuardMismatch  期望原值与现场不符的处数（0..3）
//   g_MinimapTouchGateFailureCode    失败码：0 = 没问题；否则 `(序号 << 8) | 种类`
//                                    种类 1 = 模块/地址非法，2 = 守卫不符，3 = 写入后读回不一致；
//                                    序号 1..3 = 第几处（只有"模块整体非法"这种与具体某一处
//                                    无关的情形序号才是 0）
//
// 命名与类型跟 `g_TouchPointer*`（`runtime/src/interfaces/lua/touch_pointer.hpp`）同一风格：
// 同在本命名空间里、都是 `std::atomic<std::uint32_t>`，读数工具按符号表取地址。
inline std::atomic<std::uint32_t> g_MinimapTouchGateState{0};
inline std::atomic<std::uint32_t> g_MinimapTouchGateApplied{0};
inline std::atomic<std::uint32_t> g_MinimapTouchGateGuardMismatch{0};
inline std::atomic<std::uint32_t> g_MinimapTouchGateFailureCode{0};

enum class MinimapTouchGateState : std::uint32_t {
    kNotTried = 0,
    kInstalled = 1,
    kFailed = 2,
};

enum class MinimapTouchGateFailureKind : std::uint32_t {
    kModuleInvalid = 1,  // 模块基址/代码段装不下这三处（含"那一页不是游戏模块代码段"）
    kGuardMismatch = 2,  // 现场原值与期望原值不符 —— 一处都不写
    kWriteFailed = 3,    // 写入后读回不一致
};

constexpr std::uint32_t MakeMinimapTouchGateFailureCode(MinimapTouchGateFailureKind kind,
                                                       std::uint32_t index = 0) {
    return (index << 8) | static_cast<std::uint32_t>(kind);
}

// 纯函数（真机路径与宿主夹具共用同一份判据）：返回 0 = 三处现场原值全部相符；
// 否则返回 1..3 = **第一处**不符的序号。它只比较，不碰任何内存。
constexpr std::uint32_t FirstMinimapTouchGateGuardMismatch(
    const std::array<std::uint32_t, kMinimapTouchGatePatchCount>& current) {
    for (std::size_t index = 0; index < kMinimapTouchGatePatches.size(); ++index) {
        if (current[index] != kMinimapTouchGatePatches[index].expected) {
            return static_cast<std::uint32_t>(index) + 1u;
        }
    }
    return 0;
}

// 纯函数：不符的**处数**（0..3）。
constexpr std::uint32_t CountMinimapTouchGateGuardMismatches(
    const std::array<std::uint32_t, kMinimapTouchGatePatchCount>& current) {
    std::uint32_t count = 0;
    for (std::size_t index = 0; index < kMinimapTouchGatePatches.size(); ++index) {
        if (current[index] != kMinimapTouchGatePatches[index].expected) {
            ++count;
        }
    }
    return count;
}

// ---------------------------------------------------------------------------
// 安装
// ---------------------------------------------------------------------------

// 在**模块启动时、游戏代码段已映射之后**调用（与既有补丁/挂点同一起点，见
// `hook_manager.cpp::TryInstallDefaultManifestMod` 里那一行）。
//
// 口径是**全有或全无**：三处里只要有一处现场原值与期望不符，就**一处都不写**、游戏保持原样
// （与入口中继"绝不半改"同一口径）。理由不是洁癖：#1 与 #2 必须成对才成立（只装 #2 时
// `w20` 仍会被中间游戏区置位 ⇒ 拖拽照旧是全局的），而 #1 单独装上又会把 #3 那个功能的
// 触发条件收窄成"摸小地图" ⇒ 半套补丁会把行为改得比不改更糟。
//
// 2026-10-14 更正：上述“#3收文字”的半套解释是历史误解；#3现在保留原值，
// 第三处仍参加统一守卫/写回验证，前两处局部拖拽仍须成对安装。
// 无论成败都把结果记进上面四个诊断量。返回是否三处都装上（都装上 ⇒ 用户诉求达成）。
bool InstallMinimapTouchGate(std::uintptr_t moduleBase, std::size_t moduleTextSize);

}  // namespace isaac::runtime
