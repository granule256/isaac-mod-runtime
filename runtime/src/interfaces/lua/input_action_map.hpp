#pragma once

// ============================================================================
// 模组（PC 口径）的**动作号** → Switch（`KAGE::Input`）引擎的**内部动作号**：
// 独立的翻译表（批次 230，2026-09-30）
// ============================================================================
//
// ## 为什么需要这张表（"推摇杆下 = 按左"的根因）
//
// PC 的 `ButtonAction` 与 Switch 引擎**内部**的动作号**不是同一张表**：
// PC 里 `ACTION_MENULEFT = 20`，而 Switch 引擎里 **20 号是"菜单下"**。我们原来把模组给的
// PC 号**原样**递给引擎 ⇒ `Input.IsActionPressed(ACTION_MENULEFT)` 问的是引擎的"下"
// ⇒ 推"下"时引擎把 `ACTION_MENULEFT(20)` 也答成"按住"。
//
// 真机症状（2026-09-30 用户实测）：中文版 MCM 的导航链是 **下 → 上 → 右 → 左**（后判覆盖前判，
// `modconfig.lua:1651-1663`），而"左"那一组是 `{ACTION_LEFT(0), ACTION_SHOOTLEFT(4), ACTION_MENULEFT(20)}`
// ⇒ 推"下"被那个假真改写成"左" ⇒ **摇杆向下推不能正常向下选择**。左/右多报的 17/18 不在任何
// 方向组里，所以感觉不到（这就是读数里"多报 `action + 17`"的全部来历）。
//
// ## 证据（全部离线复算得，命令都能重跑）
//
// 用 `tools/nro_disasm.py`（`Repentance.nro` 的偏移 = 运行期模块偏移）：
//
// 1. **设备层按号直接取**：`KAGE::Input::InputDeviceBase::IsActionPressed @0x4F76A8`
//      `ldr w8,[x0,#0x1c] ; cmp w8,w1 ; b.ls ⇒ false`（越界即假，真机 `设备+0x1c = 24`）
//      `ldr x8,[x19,#0x20]`（该动作绑定的按钮码数组）→ 逐个调虚槽 `+0x30`
//      `ldr x8,[x19,#0xd0] ; ldr s0,[x8,x20,lsl #2]`、`ldr s1,[x19,#0xe4] ; fcmp ⇒ >0.5`
//    ⇒ 动作号**直接当数组下标**，全程没有翻译。
// 2. **管理器层也不翻译**：`ManagerBase::IsActionPressed @0x4F9920` 只做"按设备号找设备 →
//    调它的虚槽 `+0x48`"，动作号原样传下去（`IsActionTriggered` 同形，只差虚槽）。
// 3. **引擎自己的菜单代码用的是 17/18/19/20**：
//      * `Menu_Game::Update @0x40D770`：`IsActionPressed(0x13=19)` ⇒ 选中行 **-1**（上）；
//        `IsActionPressed(0x14=20)` ⇒ **+1**（下）—— 行为可读，所以"19=上、20=下"是硬结论；
//      * `PauseScreen::ProcessInput` / `Menu_Bestiary::ProcessInput` / `Menu_KeyConfig::Update` /
//        `Menu_Options::Update`：全部用 17/18/19/20，而且**每个方向各有一个"按住计数"**；
//      * 严格模式扫全镜像：`IsActionPressed/Triggered` 的**常量实参**只出现 17..23（101 个调用点）。
// 4. **默认按键表**（`IsaacRepentance::s_ButtonMap @0xa38300`；同一张表 288 字节，
//    3 台设备各一份：`s_ButtonMap` / `s_JoyConLeftButtonMap @0xa38420` / `s_JoyConRightButtonMap @0xa384e0`）
//    是 24 条「内部动作号 → 按钮码」，逐条对上 PC 语义：
//      0..3 ← 十字键四向 + **左**摇杆；4..7 ← 手柄面键 + **右**摇杆；8 ← L、9 ← ZL、10 ← R、11 ← ZR；
//      12 ← `+`、13 ← `-`、14 ← A、15 ← B、16 ← `+`；**17..20 ← 十字键四向 + 左摇杆**；
//      21 ← L、22 ← R、23 ← X。
//      （按钮码 → 名字取自 `DeviceNX::GetButtonName @0x4FC600` 的跳表：0=Left Button、
//       4=A、5=B、6=X、7=Y、8=L、9=ZL、11=R、12=ZR、14=`+`、15=`-`、16=SL、17=SR。）
// 5. **16 号 = `JOINMULTIPLAYER`**：`PlayerManager::ProcessInput @0x43E700` 在
//    「`IsActionTriggered(16)` 且 `IsActionPressed(8)`（炸弹）且 `IsActionPressed(10)`（药丸）」
//    时调 `PlayerManager::SpawnCoPlayer(-1)` + `Entity_Player::SetControllerIndex(device,1)`
//    —— 这正是 PC 上"按住炸弹+卡牌、再按 Start 加一个手柄"的加入机制。
// 6. **真机读数**（批次 222，`dist/gdb-read-20260930-1633*-snapshot.txt`）：推左 ⇒ 引擎把
//    0 与 **17** 答成按住、推右 ⇒ 1 与 **18**、推下 ⇒ 3 与 **20**（四点全对上）。
// 7. 设备动作数 = **24**（真机 `设备+0x1c`），而上面的表正好用满 0..23
//    ⇒ Switch 上**没有** `FULLSCREEN/MUTE/RESTART/MENULT/MENURT/MENUEX/EMOTES/CONSOLE`
//    这些 PC 才有的动作（这也是"多报 +17"看起来像 `action + 17` 的原因：PC 的 17..20
//    正好落在 Switch 的"菜单四向"上）。
//
// ## 这张表的口径（**唯一的真值源，别再各处猜**）
//
// | 模组（PC）动作号 | 名字 | Switch 引擎内部号 |
// | --- | --- | --- |
// | `0..15` | LEFT … MENUBACK | **同号** |
// | `16 / 17 / 18` | FULLSCREEN / MUTE / RESTART | **无**（Switch 上不存在） |
// | `19` | JOINMULTIPLAYER | `16` |
// | `20 / 21 / 22 / 23` | MENULEFT / MENURIGHT / MENUUP / MENUDOWN | `17 / 18 / 19 / 20` |
// | `24 / 25` | MENULB / MENURB | `21 / 22` |
// | `26 / 28 / 29` | MENUTAB（三种写法的候选号，见下） | `23` |
// | `27` | MENURT | **无** |
// | `30 / 31 / 32` | EMOTES / （未定义）/ CONSOLE | **无** |
//
// ### 20..23 这一段是**用户可见缺陷**的所在，也是本表最硬的一段
//
// 20..23 四行有三条独立证据（引擎自己的菜单代码、默认按键表、真机摇杆读数）⇒ 不需要再验。
//
// ### 24..29 这一段契约页自己就矛盾（如实记录，不掩盖）
//
// `tools/pc_enum_docs/ButtonAction.md:35-45`（仓库内逐字节副本）在 Rep+ 名下同时写着：
//
//   * `24 ACTION_MENULB`（L 肩键，**added with Rep+**）与 `24 ACTION_MENULT`（AB+ 那行，左扳机）；
//   * `25 ACTION_MENURB` 与 `25 ACTION_MENURT`；
//   * `26 ACTION_MENULT`（Rep+）与 `26 ACTION_MENUTAB`（AB+）；
//   * `27 ACTION_MENURT`；`28 ACTION_MENUTAB`（带 **Value changed with Rep+**）**和** `28 ACTION_MENUEX`；
//     `29 ACTION_MENUTAB`；`30 ACTION_EMOTES`；`32 ACTION_CONSOLE`。
//
// 而本仓库**自己**暴露的 `ButtonAction` 表（`runtime/source/lua_runtime.cpp` 的
// `kButtonActionConstants`）目前是 `24=MENULT / 25=MENURT / 26=MENUTAB / 28=CONSOLE`
// （= AB+ 那一套；批次 218 只校过 16/17/18，24 之后还没校）。
//
// ⇒ 一个号同时被两种写法指着时，本表的取舍是**"取 Switch 上真的存在的那一个"**：
//   * `24 → 21`、`25 → 22`：`MENULB/MENURB` 在 Switch 上就是 L/R（默认表 21←L、22←R；
//     `Menu_Character::ProcessInput` 也用 21/22 翻页）；而 `MENULT/MENURT` 在 Switch 上**不存在**
//     （ZL/ZR 已经被 `ITEM`/`DROP` 占用，见默认表）⇒ 取前者。
//   * `26 → 23`、`29 → 23`：`MENUTAB` 在 Switch 上就是 X（默认表 23←X；
//     `Menu_Character::ProcessInput` 用 23 做"里角色"切换，PC 文档也写 `MENUTAB` = 手柄 X）；
//     26 还有一种读法是 `MENULT`（Switch 无）⇒ 取 `MENUTAB`。
//   * `28 → 23`：契约页 28 三行互相矛盾（`MENUTAB` / `MENUEX` / AB+ 的 `CONSOLE`），
//     其中只有 `MENUTAB` 在 Switch 上有对应 ⇒ 按它处理。
//   * `27 → 无`：`MENURT` 在 Switch 上没有对应项，**不许**拿别的号顶替。
//
// ⚠️ **已知的两点代价（写在这里，不藏在别处）**：
//   ① 一个模组若把 24/25/28 当作"扳机/`MENUEX`"用（AB+ 口径），会拿到**肩键/X**的答案 ——
//      即可能出现"假真"。之所以接受：Switch 上没有扳机菜单动作，答 false 同样是"答不出来"，
//      而这三行**碰不到方向四向**（引擎 21/22/23 不是方向），不会再引发"MCM 向下变成向左"那一类
//      用户可见缺陷（那一类的号是 17..20，已按硬证据一对一映射）。
//   ② 我们自己的 `ButtonAction` 表在 24..28 上还是 AB+ 的值 ⇒ 用**我们自己那个常量**的模组
//      仍然会拿到 AB+ 的号（本表的取舍正好是"两种写法都给同一个存在项"，所以行为是对的）。
//      把常量表按 Rep+ 校正（`24=MENULB … 29=MENUTAB`、`32=CONSOLE`）**另开一批**做，
//      不在本批顺手改（会动到已暴露给模组的常量值，另有门禁与模组影响面要评估）。
//
// ## 分工
//
// 本文件**只做纯换算**（只吃参数、不碰引擎内存、不碰文件）⇒ 宿主门禁能逐条钉住；
// 调引擎、记探针都留在调用点（`interfaces/lua/input_api.cpp`）。

#include <cstdint>

namespace isaac::runtime {

//: 模组（PC/`ButtonAction`）动作号的上界：PC Rep+ 最大用到 32（`ACTION_CONSOLE`）。
inline constexpr std::uint32_t kLuaActionCapacity = 33;

//: "这个动作在 Switch 引擎里没有对应项"的哨兵。调用点必须**直接答 `false` / `0.0`**，
//: **不许**把这个值当动作号递给引擎（设备层对越界号会答 false，但那是巧合、不是本表的意思）。
inline constexpr std::uint32_t kNoEngineAction = 0xFFFFFFFFu;

//: Switch 引擎的内部动作总数（真机 `设备+0x1c` 实测 = 24；`IsActionPressed` 的序言拿它做越界判据）。
inline constexpr std::uint32_t kSwitchEngineActionCount = 24;

//: 模组动作号 → 引擎内部动作号（`kNoEngineAction` = Switch 上没有这个动作）。逐行证据见文件头。
inline constexpr std::uint32_t kLuaActionToEngineAction[kLuaActionCapacity] = {
    /*  0 ACTION_LEFT           */ 0u,
    /*  1 ACTION_RIGHT          */ 1u,
    /*  2 ACTION_UP             */ 2u,
    /*  3 ACTION_DOWN           */ 3u,
    /*  4 ACTION_SHOOTLEFT      */ 4u,
    /*  5 ACTION_SHOOTRIGHT     */ 5u,
    /*  6 ACTION_SHOOTUP        */ 6u,
    /*  7 ACTION_SHOOTDOWN      */ 7u,
    /*  8 ACTION_BOMB           */ 8u,
    /*  9 ACTION_ITEM           */ 9u,
    /* 10 ACTION_PILLCARD       */ 10u,
    /* 11 ACTION_DROP           */ 11u,
    /* 12 ACTION_PAUSE          */ 12u,
    /* 13 ACTION_MAP            */ 13u,
    /* 14 ACTION_MENUCONFIRM    */ 14u,
    /* 15 ACTION_MENUBACK       */ 15u,
    /* 16 ACTION_FULLSCREEN     */ kNoEngineAction,
    /* 17 ACTION_MUTE           */ kNoEngineAction,
    /* 18 ACTION_RESTART        */ kNoEngineAction,
    /* 19 ACTION_JOINMULTIPLAYER*/ 16u,
    /* 20 ACTION_MENULEFT       */ 17u,
    /* 21 ACTION_MENURIGHT      */ 18u,
    /* 22 ACTION_MENUUP         */ 19u,
    /* 23 ACTION_MENUDOWN       */ 20u,
    /* 24 MENULB（或 AB+ MENULT）*/ 21u,
    /* 25 MENURB（或 AB+ MENURT）*/ 22u,
    /* 26 MENUTAB（或 Rep+ MENULT）*/ 23u,
    /* 27 MENURT                */ kNoEngineAction,
    /* 28 MENUTAB（或 MENUEX）  */ 23u,
    /* 29 MENUTAB               */ 23u,
    /* 30 ACTION_EMOTES         */ kNoEngineAction,
    /* 31 （未定义）            */ kNoEngineAction,
    /* 32 ACTION_CONSOLE        */ kNoEngineAction,
};

//: 取"这个模组动作号在 Switch 引擎里是几号"；越界与"平台上没有"都返回 `kNoEngineAction`。
[[nodiscard]] constexpr std::uint32_t TranslateLuaActionToEngineAction(
    std::uint32_t lua_action) noexcept {
    return lua_action < kLuaActionCapacity ? kLuaActionToEngineAction[lua_action] : kNoEngineAction;
}

//: 这个模组动作号在 Switch 引擎里有没有对应项（没有 ⇒ 调用点直接答 false / 0）。
[[nodiscard]] constexpr bool LuaActionExistsOnSwitch(std::uint32_t lua_action) noexcept {
    return TranslateLuaActionToEngineAction(lua_action) != kNoEngineAction;
}

// ============================================================================
// 反方向：引擎内部动作号 → 模组（PC）动作号（批次 393，2026-10-07）
// ============================================================================
//
// ## 为什么需要它：`MC_INPUT_ACTION` 的 `buttonAction` 实参
//
// 上面那张表解决的是"模组问引擎"（`Input.IsActionPressed(PC号)`）。回调是**反过来**：
// 引擎在轮询时说"我现在问的是内部 20 号"，而 PC 契约里这个实参是**模组的 `ButtonAction` 值**。
// 我们批次 390/392 一直是把**引擎内部号**原样递过去的 ⇒ 比较动作号的模组会判错。
//
// ★ 为什么以前没被咬到：`ACTION_MAP = 13` 在两张表里**恰好同号**（minimapi 用的就是它），
//   而错开的那一段（16..23）在使用中的模组里没有消费者 —— 但这是运气，不是正确性。
//   已知的真消费者形状：`InputHelper.HandleForceActionPressed` 用
//   `forcingActionPressed[controllerIndex][buttonAction]` 存"要强制的动作"
//   （`analysis/mod-corpus/isaac-mod-config-menu/scripts/inputhelper.lua:257-295`）——
//   存进去的是 PC 号、拿出来比对的是我们给的号 ⇒ 不对上就永远命中不了。
//
// ## 这张反表怎么来的（逐行，不是"照抄正向表"）
//
// 正向表里 `16/17/18` 三行指向 `kNoEngineAction`（PC 的 FULLSCREEN/MUTE/RESTART 在 Switch
// 上没有对应动作）⇒ 从 PC 19 起，**每个号都比引擎号大 3**：
//
//   * 引擎 `16..20` ← PC `19..23`（JOINMULTIPLAYER / MENU 四向）；
//   * 引擎 `21/22/23` ← PC `24/25/26`（Switch 上分别就是 L / R / X）。
//
// 所以整张反表 = **0..15 同号 + 16..23 一律 `+3`**。写成逐行表而不是 `+3` 的算式，是为了
// 与正向表一样"每一行都能被门禁逐条钉住"（一个 `+3` 写错会整段偏，逐行表只会错一行）。
//
// ## 一处必须选一个的地方（如实记录）
//
// 引擎 `23`（X）在正向表里有**三个** PC 写法指向它：`26 / 28 / 29`（都是 `MENUTAB` 的候选号，
// 见文件头 24..29 那段的自相矛盾）。反表**取正写的 `26`**：它与我们的 `ButtonAction` 常量表
// 一致（`kButtonActionConstants` 里 26 = MENUTAB），模组写 `ButtonAction.ACTION_MENUTAB` 就能比中。
//
// ## ⚠ 口径说明（写在这里，不藏在别处）
//
// 给出去的号**是"模组自己那张 `ButtonAction` 表里的号"**，不是"PC Rep+ 的号" —— 两者在
// `24/25/26/28` 上还不一致（我们暂时暴露的是 AB+ 那一套：`24=MENULT`、`25=MENURT`、`26=MENUTAB`）。
// ⇒ **一个只带 `ACTION_MENUTAB` 的模组是安全的**（26 两种口径同值）；把 24/25 当
// "L/R 肩键"用的模组拿到的号在我们表里叫 `MENULT/MENURT`。把常量表按 Rep+ 校正**另开一批**
// （见文件头"已知的两点代价"②），本批不动它。
inline constexpr std::uint32_t kEngineActionToLuaAction[kSwitchEngineActionCount] = {
    /*  0 */ 0u,  /*  1 */ 1u,  /*  2 */ 2u,  /*  3 */ 3u,
    /*  4 */ 4u,  /*  5 */ 5u,  /*  6 */ 6u,  /*  7 */ 7u,
    /*  8 */ 8u,  /*  9 */ 9u,  /* 10 */ 10u, /* 11 */ 11u,
    /* 12 */ 12u, /* 13 */ 13u, /* 14 */ 14u, /* 15 */ 15u,
    /* 16 JOINMULTIPLAYER（"+"）   */ 19u,
    /* 17 MENULEFT（十字键左/左摇杆）*/ 20u,
    /* 18 MENURIGHT               */ 21u,
    /* 19 MENUUP                  */ 22u,
    /* 20 MENUDOWN                */ 23u,
    /* 21 MENULB（Switch = L）    */ 24u,
    /* 22 MENURB（Switch = R）    */ 25u,
    /* 23 MENUTAB（Switch = X）   */ 26u,
};

//: 取"引擎这个内部动作号在模组（PC）口径下是几号"。
//:
//: 越界（≥ `kSwitchEngineActionCount`）**原样返回**、不编造：引擎只会轮询 0..23
//: （设备动作数 24，真机 `设备+0x1c` 实测），出现越界号说明调用方不是引擎 —— 那时把原值透传，
//: 比编一个"看起来合法"的 PC 号安全（消费点 `DispatchInputAction` 的注释里也写了这一条）。
[[nodiscard]] constexpr std::uint32_t TranslateEngineActionToLuaAction(
    std::uint32_t engine_action) noexcept {
    return engine_action < kSwitchEngineActionCount ? kEngineActionToLuaAction[engine_action]
                                                    : engine_action;
}

}  // namespace isaac::runtime
