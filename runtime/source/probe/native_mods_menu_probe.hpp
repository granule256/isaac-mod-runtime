#pragma once

// 探针：**能不能把游戏自己那套模组菜单叫出来**（2026-09-21 晚，PC 式模组页可行性的第一问）。
//
// ## 为什么要有它（背景）
//
// 用户要"与 PC 一模一样的模组管理页，并且是主界面里新增的一项"。静态取证已经查清（见
// `docs/改动日志-20260921.md` 的 019 小节）：
//   * Switch 版二进制里**有完整的 `Menu_Mods`**（ctor/Init/Update/UpdateKeyPress/Render/
//     Reset 全在，`Init` 会加载 `gfx/ui/main menu/ModsMenu.anm2`），UI 资源在本体里也有
//     （`rp_patch/resources/gfx/ui/main menu/modsmenu.anm2`）；
//   * 但它是**彻底的死代码**：11 个方法既没有调用点、也没有 GOT 槽引用、也没有函数指针表；
//   * 状态机只有 16 个状态（0 空 + 1..15），逐格都对得上具体页面，**没有模组页那一格**。
//
// 所以只剩两个问题必须在真机上回答，本探针就是为它们写的：
//   Q1 状态机那 16 个状态在真机上分别是什么页面（静态表见 `.cpp` 的注释，用来核对）；
//   Q2 绕开状态机、我们自己调 `Menu_Mods::ctor/Init/Render`，页面能不能画出来？
//      （能画 ⇒ 即使没有状态格，也能"借原生页当壳 + 喂我们自己的数据"。）
//
// ## ★ 第二版（2026-09-21 深夜，第一版真机读数之后）
//
// 第一版把"手动画原生页"挂在 **ZR+ZL 组合键**上，真机结果是**一次都没命中**：诊断字里
// `presses/backPresses/manualMode` 全是 0，而 `managerOk=1`（= 更新中继确实在跑）。
// 原因不是探针没跑，而是**手柄序号猜错了** —— 项目自己的历史结论是"引擎只认玩家自己的
// controller 值（真机上出现过 33）"，而主菜单里根本没有玩家，0/1 一律不回应。
//
// ⇒ 第二版改成两条腿，**都不再依赖"猜对按键"**：
//   * **自动驱动**：只要 `g_MenuManager` 非空（= 已经在菜单里），就自动做一次 `ctor`+`Init`，
//     之后每帧 `Render`。⇒ 用户开机停在主菜单就能看到结果，一个键都不用按。
//   * **输入扫描**：每 8 帧扫一遍 `动作号 0..27 × 手柄号 0..63`，把"哪些动作被按住""哪些手柄号
//     答过'是'"记成掩码。⇒ 下次接按键就不必再猜；顺便验证"主菜单里到底哪个 controller 有效"。
//
// 组合键（ZR+ZL）与 ZR/ZL 单键仍然保留：它们走的是"**任一手柄号**答是"的并集判定，
// 所以这次只要那个号在扫描范围里就能生效（但自动驱动已经不依赖它们了）。
//
// ## 数据从哪来（静态已确认）
//
// `Menu_Mods::Init` 会把 `*(g_Manager + 0x36800)`（= 引擎自己的 ModManager 对象）存进
// `this+0x170`；`Update` 就在它上面翻转"启用"字节（`+0x138`），`Render` 从
// `g_Manager+0x36800` 的 begin/end 指针对算行数。⇒ **页面显示的是引擎自己的模组表**，
// 不是我们的清单。它到底有没有内容，是真机问题之一（读数里 `modListBytes` 那一格）。
//
// ## 纪律
//
//   * 每次调引擎前**逐字节核对入口指纹**；不符就只记失败码、**不调用**（绝不盲目跳地址）；
//   * 只读单例、只写我们自己的诊断字；**不写任何文件、不碰 SD**；
//   * **不调 `ModManager::ListMods()`**（它在真机会中断，见 `docs/开发规范.md` 第 26 条）；
//   * 整个 TU 在 `PROBE_BREAK=0` 时被编译掉（生产包不含它）。

#include <cstdint>

namespace isaac::runtime::probe {

//: 诊断字（`IsaacModRuntime_NativeModsMenuProbeDiagnostics` 按固定顺序写出这些 u32）。
//: 读数工具按这些下标解析，**不要改顺序**（要加就往后加）。
struct NativeModsMenuProbeView {
    std::uint32_t armed;         // [0] 1 = 本探针编进来了（否则读数里恒 0）
    std::uint32_t presses;       // [1] ZR 按过几次（状态递增次数）
    std::uint32_t backPresses;   // [2] ZL 按过几次（状态递减次数）
    std::uint32_t state;         // [3] 当前试到的 `MenuManager::eState` 值（0..15）
    std::uint32_t manualMode;    // [4] 1 = 手动画原生页开着（第二版起由"菜单出现"自动打开）
    std::uint32_t initResult;    // [5] 手动 Init 的结果（0 未试 / 1 成功 / 2 入口守卫不符 /
                                 //     3 单例为空 / 4 模块找不到）
    std::uint32_t renderCalls;   // [6] 手动 `Menu_Mods::Render` 调了几次
    std::uint32_t lastFailure;   // [7] 最近一次失败码（0 = 没有；含义见 .cpp 的常量）
    std::uint32_t managerOk;     // [8] 1 = `g_Manager` 那句 GOT 槽读到的指针非空
    std::uint32_t menuManagerOk; // [9] 1 = `g_MenuManager` 非空（手动 Init 的前置条件）
    std::uint32_t modListBytes;  // [10] 引擎模组表 `end - begin` 的原始字节数（0 = 空表）
    std::uint32_t menuState;     // [11] 随手记的 `MenuManager+0x38`（= 状态机当前状态）
    // ---- 第二版新增（输入映射的实测结果，全部是"并集"口径）----
    std::uint32_t heldActionMask;     // [12] 扫描里被按住过的动作号位图（bit0..bit27）
    std::uint32_t heldControllerMask; // [13] 答过"是"的手柄号位图（bit0..bit31）
    std::uint32_t scanRounds;         // [14] 扫描跑了几轮（0 = 扫描没跑起来）
    std::uint32_t modListPointersOk;  // [15] 1 = 上面那对 begin/end 像合法指针（>=0x1000 且 8 对齐）
                                      //      ⇒ 0 而 [10] 也是 0 时，"空表"这个结论**不成立**
                                      //      （更可能是我们对 `Manager+0x36800` 那个结构的解释不对）
    std::uint32_t manualModsPtrOk;    // [16] 1 = `Init` 确实跑进函数体并把 ModManager 记进了
                                      //      `对象+0x170`（这是"我们的 Init 调用真的执行了"的硬证据）
};

//: 更新中继每帧调一次（读输入、动状态；自动模式下在这里做一次 `Init`）。
void NativeModsMenuProbeUpdate() noexcept;
//: Present 前中继每帧调一次（手动模式 + Init 成功时真的画）。
void NativeModsMenuProbeBeforePresent() noexcept;

} // namespace isaac::runtime::probe
