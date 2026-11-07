#pragma once

// ============================================================================
// PC 的 `controllerId` → Switch（`KAGE::Input`）的**设备号**：独立的映射表
//
// ============================================================================
//
// ## 为什么需要这张表（同一个坑踩了三次）
//
// PC 模组里"第几个手柄"用的是 **PC 的编号习惯**：`0` = 键盘、`1..4` = 第 1..4 台手柄
// （PC 文档 examples 就是 `ButtonAction.ACTION_LEFT, 1`；`InputHelper.KeyboardTriggered(key, i)`
// 的 `i` 也是 `0..4` 的循环）。而 Switch 引擎（`KAGE::Input`）的**设备号是另一张表**：
//
//   * `0` = **触摸屏**（`Manager::Initialize` 里最先 `AddDevice` 的一台，设备号由生成器给 0）；
//   * `1..8`、`33` = 手柄设备（`Manager::Poll` 拿候选表 `{0..7,32}` 逐个试，**命中的候选 + 1**，
//     见 `analysis/api-restore-input-keys/spec.json` 的 `device_ids`）；
//   * `0xFFFFFFFF` = **任意设备**（引擎自己的习惯：游戏本体的 L+R+双摇杆组合键、以及我们自己的
//     "长按 A+B 呼出软键盘"都这么问）。
//
// ⇒ 模组传 `1` 时，引擎去设备表里找**设备号 1**：真机上那台手柄是 **33** ⇒ 找不到 ⇒ **恒答 false**。
// 三次真事故都出在这里：
//   ① 嵌入式模组菜单（`docs/问题与解决记录.md` 里有"自学习 controller"那一段）；
//   ② 主菜单自绘入口（`action_input_poll.hpp` 的候选表就是为它写的）；
//   ③ MCM 的"按右摇杆开菜单"（2026-09-30：守卫修好之后露出这一层 —— 读数证明模组确实在问 13 号，
//      但引擎设备表里只有 `0` 与 `33`，模组的 `for i = 0, 4` 全落空）。
//
// ## 这张表的口径（**唯一的真值源，别再各处猜**）
//
// | PC 的 `controllerId` | PC 语义 | Switch 上怎么办 |
// | --- | --- | --- |
// | `0` | 键盘 | **没有这台**（Switch 引擎里没有键盘设备，已取证）⇒ 答 `false` / `0.0` |
// | `1` | 第 1 台手柄 | 设备表里**第 1 台"手柄"设备**（跳过触摸屏）的设备号（真机实测 = `33`） |
// | `2..4` | 第 2..4 台手柄 | 设备表里第 2..4 台手柄；**不够就是"没有这台"**（PC 上也是这个结果） |
// | 其它（负、`> 4`、`0xFFFFFFFF`） | 不是 PC 的档 | **原样透传** ⇒ NS 原生用法照旧（`33` / `0xFFFFFFFF`） |
//
// ## 同槽别名去重
//
// 引擎的设备表里可能同一台物理手柄出现两次（真机：设备号 `1` 与 `33`，相差 32 ⇒ `& 31` 同槽）。
// 于是模组 `for i = 0, 4` 会**两次**命中同一台手柄（`i=1` 与 `i=2` 都答 true）—— 中文版 MCM 的
// 开菜单判定就会在同一帧里 `ToggleConfigMenu()` **两次（先开、再立刻关）**，屏幕上什么都没有。
//
// ⇒ 本文件新增一个**按槽去重**的包装函数 `MapPcControllerIdToNsInputDeviceDeduped`（口径同上表，
//   再加一条）：`i` 映射到的设备号若与**更小的某个 `i`** 已经映射到的设备号**落进同一个槽**
//   （`(a & 31) == (b & 31)`），则本 `i` 返回 `NoSuchDevice`（"这一档不存在" ⇒ 调用方得到 `false`，
//   与 PC 上"第 k 台手柄没插"同形）。**查询层（`ResolveInputDevice*`）用这个包装函数**。
//   底层纯函数 `MapPcControllerIdToNsInputDevice` 的口径不变（只做"`i` ⇒ 第 `i` 台手柄"）。
//
// 判据是同槽，不是"同物理"：真的插了两台不同手柄时它们不同槽（如 `1` 与 `2`）⇒
// 仍然各自命中 —— **不会砍掉玩家 2**（PC 语义保留）。**也别**简化成"永远只允许 `i=1`"。
//
// "手柄设备"的判据（两条取或，都写在 `IsNsTouchscreenEntry` 里）：
//   * **表里第 0 项** —— 触摸屏永远是最先 `AddDevice` 的那台；
//   * **设备号 == 0** —— 触摸屏的设备号由生成器给 0（手柄号来自候选 + 1，永远 ≥ 1）。
//
// ## 读不到设备表时怎么办（**写在表里，不藏在调用点**）
//
// 读不到就**无法**把 `1..4` 翻成设备号 ⇒ 按 `NsDeviceTableState::Unknown` 走：
// **原样透传**（也就是与修之前的行为一致：引擎按 `1..4` 找不到设备 ⇒ 答 false）。
//
// 为什么不偷偷换成"任意设备"（`0xFFFFFFFF`）：那会让**本地双人**里"你的按键"变成"谁按都算"，
// 而且这种静默降级正是这次事故的形状（模组拿不到真值却毫无线索）。**表读不到要能被看见**：
// 调用点必须把"因为表读不到而没能翻译"的次数记进探针（`g_InputControllerMapFallbacks`），
// 读数里打印出来。真机上这张表是可读的（`dist/gdb-read-20260930-0030-device-table.txt`）。
//
// ## 分工
//
// 本文件**只做纯换算**（只吃参数、不碰引擎内存、不碰文件）⇒ 宿主门禁能逐条钉住口径；
// 读设备表、写探针、调引擎都留在调用点（`interfaces/lua/input_api.cpp`）。

#include <cstddef>
#include <cstdint>

namespace isaac::runtime {

// 引擎里"任意设备"的哨兵值（`ManagerBase::IsButtonPressed` 的 `deviceId`）。
inline constexpr std::uint32_t kNsAnyInputDevice = 0xFFFFFFFFu;

// 设备表里第 0 项 = 触摸屏（最先 `AddDevice`）。
inline constexpr std::size_t kNsTouchscreenEntryIndex = 0;
// 触摸屏的设备号（构造时从生成器拿到的就是 0）。
inline constexpr std::uint32_t kNsTouchscreenDeviceId = 0;

// PC 的"键盘"档。
inline constexpr std::int64_t kPcKeyboardControllerId = 0;
// PC 的手柄档（含两端）：`1..4`。
inline constexpr std::int64_t kPcFirstGamepadControllerId = 1;
inline constexpr std::int64_t kPcLastGamepadControllerId = 4;

// 引擎设备表最多几台（候选表 `{0..7,32}` 命中后 +1 ⇒ 上限 9：触摸屏 + 8 台手柄）。
// 超出的一律不读（读数与调用点都按这个上限分配快照）。
inline constexpr std::size_t kNsInputDeviceCapacity = 9;

// 引擎给设备"入槽"用的掩码（`设备号 & 31`）—— 与边沿表 `InputFrameEdges::kIndexMask` 同一口径。
// 手柄号 `1` 与 `33` 相差 32 ⇒ `1 & 31 == 33 & 31 == 1` ⇒ 落进同一个槽。
// 这台文件把它单独拎出来，用于下面的"同槽别名去重"（见 `MapPcControllerIdToNsInputDevice`）。
inline constexpr std::uint32_t kNsInputDeviceSlotMask = 31u;

// 设备表这一帧读到了没有。
enum class NsDeviceTableState {
    Known,     // 读到了设备表（可以把 1..4 翻成设备号）
    Unknown,   // 读不到 ⇒ 按下面那条兜底口径走，并计数
};

// 一次换算的结果。
enum class NsDeviceSelection {
    Passthrough,    // 不是 PC 的 0..4 档 ⇒ 当 NS 原生设备号原样传
    Mapped,         // 翻成了设备表里某台手柄的设备号
    NoSuchDevice,   // PC 上没有这台（键盘档 / 第 k 台手柄不存在）⇒ 答 `false` / `0.0`
};

struct NsDeviceTarget {
    NsDeviceSelection kind;
    std::uint32_t device_id;   // 只有 `Passthrough` / `Mapped` 有意义
};

// 这一项是不是"触摸屏那台"（判据见文件头：表里第 0 项 或 设备号 0）。
[[nodiscard]] inline bool IsNsTouchscreenEntry(std::size_t entry_index,
                                               std::uint32_t device_id) noexcept {
    return entry_index == kNsTouchscreenEntryIndex || device_id == kNsTouchscreenDeviceId;
}

// 把 PC 的 `controllerId` 翻成 Switch 的设备号（口径见文件头那张表）。
//
// `device_ids` / `device_count` 是设备表快照（按表里的先后顺序）；表读不到时传
// `table_state = Unknown`（此时不需要 `device_ids`）。
//
// 这个函数只做纯换算（`i` ⇒ 表里第 `i` 台手柄），不做同槽去重 —— 同槽去重在下面的
// `MapPcControllerIdToNsInputDeviceDeduped`（查询层用的那一个）。
[[nodiscard]] inline NsDeviceTarget MapPcControllerIdToNsInputDevice(
    std::int64_t pc_controller_id, const std::uint32_t* device_ids, std::size_t device_count,
    NsDeviceTableState table_state) noexcept {
    // 负数不是 PC 的档（PC 文档里 controllerId 只有 0..4）；`0xFFFFFFFF` 走 >4 那条透传。
    if (pc_controller_id < 0) {
        return {NsDeviceSelection::NoSuchDevice, 0u};
    }
    if (pc_controller_id == kPcKeyboardControllerId) {
        // PC 的"键盘"档：Switch 引擎里没有键盘设备（已取证）⇒ 没有真值来源。
        return {NsDeviceSelection::NoSuchDevice, 0u};
    }
    if (pc_controller_id > kPcLastGamepadControllerId) {
        // 不是 PC 的档 ⇒ 当 NS 原生设备号（`33` / `0xFFFFFFFF` / `0..3` 扫档里的 32..35 等）。
        return {NsDeviceSelection::Passthrough,
                static_cast<std::uint32_t>(pc_controller_id)};
    }
    if (table_state == NsDeviceTableState::Unknown) {
        // 表读不到 ⇒ 原样透传（= 与修之前一致）；**不许**偷偷换成"任意设备"（双人局会算错人）。
        // 这种"没能翻译"必须被看见 ⇒ 调用点计数（`g_InputControllerMapFallbacks`）。
        return {NsDeviceSelection::Passthrough, static_cast<std::uint32_t>(pc_controller_id)};
    }
    const std::size_t wanted = static_cast<std::size_t>(pc_controller_id);
    std::size_t gamepads = 0;
    for (std::size_t index = 0; index < device_count && index < kNsInputDeviceCapacity; ++index) {
        if (device_ids == nullptr) {
            break;
        }
        const std::uint32_t device_id = device_ids[index];
        if (IsNsTouchscreenEntry(index, device_id)) {
            continue;
        }
        ++gamepads;
        if (gamepads == wanted) {
            return {NsDeviceSelection::Mapped, device_id};
        }
    }
    // 表里没有第 k 台手柄 ⇒ PC 上也是"没有这台"（单手柄时 `2..4` 就该是 false）。
    return {NsDeviceSelection::NoSuchDevice, 0u};
}

// 把 PC 的 `controllerId` 翻成 Switch 设备号，并做同槽别名去重。
//
// 与 `MapPcControllerIdToNsInputDevice` 的唯一差别：若本档映射到的设备号与更小的某个 `i`
// 映射到的设备号落进同一个槽（`设备号 & 31` 相同），返回 `NoSuchDevice`（"这一档不存在"）
// —— 唯一目的：让同一台物理手柄在同一次 `for i = 0, 4` 里只命中一次（中文版 MCM 的
// 开菜单判定在同一帧里只会 `ToggleConfigMenu()` 一次，不再"先开、再立刻关"）。
// 判据是同槽，不是"同物理"：真的插了两台不同手柄（如 `1`、`2`）时它们不同槽 ⇒
// 仍然各自命中（玩家 2 不受影响、PC 语义保留）。
//
// 为什么不直接把这条塞进 `MapPcControllerIdToNsInputDevice`：那个纯函数的口径是"`i` ⇒ 表里第
// `i` 台手柄"，被 `test_pc_ns_input_device_map.py` 逐条钉住（含 `{0,1,33}` ⇒ `i=2` 仍能翻到
// 第 2 台的那条）；"同槽去重"是查询层的一条策略，放在这层、由 `ResolveInputDevice*`
// 使用，语义分层更清楚。动作侧走同一个 `ResolveInputDevice` ⇒ 一并受益（不单开一套）。
[[nodiscard]] inline NsDeviceTarget MapPcControllerIdToNsInputDeviceDeduped(
    std::int64_t pc_controller_id, const std::uint32_t* device_ids, std::size_t device_count,
    NsDeviceTableState table_state) noexcept {
    const NsDeviceTarget target =
        MapPcControllerIdToNsInputDevice(pc_controller_id, device_ids, device_count, table_state);
    if (target.kind != NsDeviceSelection::Mapped) {
        // 只对"翻到某台手柄"的档去重；键盘档 / 没有这台 / 透传 一律原样返回。
        return target;
    }
    const std::uint32_t slot = target.device_id & kNsInputDeviceSlotMask;
    for (std::int64_t smaller = kPcFirstGamepadControllerId; smaller < pc_controller_id; ++smaller) {
        const NsDeviceTarget earlier =
            MapPcControllerIdToNsInputDevice(smaller, device_ids, device_count, table_state);
        if (earlier.kind == NsDeviceSelection::Mapped &&
            (earlier.device_id & kNsInputDeviceSlotMask) == slot) {
            // 与**更小的某个 i**同槽 ⇒ 本档是它的**别名** ⇒ "这一档不存在"（答 false）。
            return {NsDeviceSelection::NoSuchDevice, 0u};
        }
    }
    return target;
}

}  // namespace isaac::runtime
