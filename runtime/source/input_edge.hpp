#pragma once

#include <cstddef>
#include <cstdint>

namespace LuaRuntime {

// `Input.IsActionTriggered(动作, 控制器)` 的**上升沿判定**（批次 107）。
//
// ## 为什么要自己算（2026-09-20 真机 + 反汇编证据）
//
// PC 的 `IsActionTriggered` 是"**刚按下**"，而引擎里也真有这条：
// `KAGE::Input::ManagerBase::IsActionPressed @ 0x4F9920` 与 `IsActionTriggered @ 0x4F9A64`
// 两个函数**结构完全相同**（都是"按控制器号在列表里找那一条 → 调它的虚函数 → 取返回值"），
// 唯一的实质差别是**调的虚函数槽不同**：`Pressed` 走 `vtable+0x48`、`Triggered` 走 `vtable+0x50`。
//
// 真机读数的形状是：
//   * "按住"位图：动作 **4, 5, 6, 7, 13**（= `ACTION_SHOOT*` 四个方向 + 一个）**有**，
//     controller 号 = 33（正是玩家自己 `EntityPlayer.ControllerIndex` 的值，09-16 已钉过）；
//   * "刚按下"位图：**一次都没为真**（问过 0..27 全部动作）。
//
// 也就是说：**同一条控制器、同一个动作，`IsActionPressed` 是通的，`IsActionTriggered` 永远是假**。
// 原因只能是引擎那份"上升沿状态"在我们跑到它的时机里是空的 —— 而模组（EID）是在
// `MC_POST_UPDATE` / `MC_POST_RENDER` 里问的，那时这一帧的输入处理早已走完。
//
// ## 所以：用"按住"自己算边沿
//
// 拿**已验证可用**的 `IsActionPressed` 当唯一原语，自己记上一次看到的状态：
// 这一次"按住"、上一次"没按住" ⇒ 就是一次上升沿。首次观察（还没有"上一次"）**不算**边沿
// （否则模组第一次问到时若键正被按着，会凭空多一次"刚按下"）。
//
// ## PC 的语义（文档原文，钉死判据）
//
// `analysis/isaacdocs-snapshot/docs/Input.md:73`：
//   `IsActionTriggered` —— "This function will only return true, if the button was pressed down.
//   **It will no longer return true, after you called this function and try to call it in the next
//   update cycle**" ⇒ **一次按键只答一次**（答过之后到下一次按下为止都是 false），
//   而**同一帧内**问多少次都答 true。⇒ **长按在 PC 上也只翻一格**（不会连续触发）。
//
// ## 与 PC 的差别（写进 `api_deviation.cpp`）
//
// ★ 2026-09-20（批次 109）：**改成按帧判**，于是"同一帧内问多少次都答 true"这一条与 PC 一致了
// （见 `Observe` 的语义）。改这里的起因：用户实测"**有时候按一次跳两个物品**"——
// 玩家按一次、EID 却翻了两次，而 EID 的防抖是 50 ms ⇒ 两次触发相隔 ≥50 ms ⇒
// 只能是我们在**一次按住里报了两次边沿**。107 那版"按调用判"会被同一帧内的两次询问骗到
// （中间那一次读到"没按住"就重置了状态）。
// 剩余差别：PC 的边沿来自引擎自己的输入事件状态；我们是从"按住"查询**每帧采样一次**推出来的
// ⇒ 一次按键恰好在一帧的采样点之间完成（按下又抬起都在两帧之间）会漏掉。
//
// 本类是**纯逻辑**（只吃"这一次按住没按住"）⇒ 宿主可以直接测它的每一条分支。
class ActionEdgeTracker {
public:
    //: `ButtonAction` 与控制器号都只取低 5 位（真机上控制器号是 33，低 5 位 = 1）。
    static constexpr std::uint32_t kIndexMask = 31u;
    //: 帧号初值（"还没看过任何一帧"）。
    static constexpr std::uint32_t kNoFrame = 0xFFFFFFFFu;
    //: **松手去抖窗口**：上一次读到"按住"之后，隔这么多帧还没再读到，才算真松手。
    //: 6 帧 ≈ 100 毫秒（60 fps）。取舍：太短挡不住引擎的闪断（就又"长按不停翻页"）；
    //: 太长会把"松手后立刻再按"并成一次（人手指做不到 100 毫秒内完成松开+按下）。
    //: 真机读数里 `"按住"最长闪断` 那一行就是用来判这个值够不够的。
    static constexpr std::uint32_t kReleaseFrames = 6;

    //: 问一次。`pressed` 是调用方刚查到的"按住"状态，`frame` 是**当前帧号**
    //: （调用方优先用引擎自己的帧计数）。
    //:
    //: 语义（与 PC 的 `IsActionTriggered` 对齐，文档 `Input.md:73`）：
    //:   * **同一帧内**问多少次都是同一个答案（PC 的"这一帧刚按下"）；
    //:   * 一次按键**只报一次** true（答过之后到下一次按下为止都是 false）——
    //:     所以**长按在 PC 上也只翻一格**，不会连续触发；
    //:   * **"按住"要连续 `kReleaseFrames` 帧没读到才算松手**（去抖）。真机上引擎的
    //:     "按住"查询会**闪断**（109 的读数：动作 7 在按住期间被报了 **170** 次边沿），
    //:     不挡它就会变成"长按不停翻页、速度还忽快忽慢"；
    //:   * **第一次观察**某个动作不算边沿（那时还不知道上一帧是什么状态）。
    [[nodiscard]] bool Observe(std::uint32_t code, std::uint32_t controller, bool pressed,
                               std::uint32_t frame) noexcept {
        const std::size_t slot = controller & kIndexMask;
        const std::uint8_t index = static_cast<std::uint8_t>(code & kIndexMask);
        const std::uint32_t bit = 1u << index;
        if (frame_[slot] != frame) {
            frame_[slot] = frame;
            edge_[slot] = 0;                 // 新的一帧：本帧的边沿重新开始攒
        }
        const bool seen = (observed_[slot] & bit) != 0;
        const std::uint32_t last = lastPressedFrame_[slot][index];
        // 距上一次读到"按住"过了多少帧（<= 窗口 ⇒ 还认为按着，闪断不算松手）。
        const std::uint32_t gap = frame - last;
        const bool wasHeld = seen && gap <= kReleaseFrames;
        if (pressed) {
            if (seen && !wasHeld) {
                edge_[slot] |= bit;          // 上一次按住已经断了 ⇒ 这是一次新的按下
            }
            if (seen && gap > 1 && gap - 1 > peakReleaseRun_[slot][index]) {
                // 诊断：这一次"闪断"持续了几帧（用来判去抖窗口够不够）。
                const std::uint32_t drop = gap - 1;
                peakReleaseRun_[slot][index] =
                    static_cast<std::uint8_t>(drop > 255 ? 255 : drop);
            }
            lastPressedFrame_[slot][index] = frame;
        }
        observed_[slot] |= bit;
        return (edge_[slot] & bit) != 0;
    }

    //: 诊断：某个动作观察到的**最长闪断帧数**（0 = 没断过）。
    [[nodiscard]] std::uint8_t PeakReleaseRun(std::uint32_t code,
                                              std::uint32_t controller) const noexcept {
        return peakReleaseRun_[controller & kIndexMask][code & kIndexMask];
    }

    //: 新建 Lua 会话时清空（与其它会话级状态同一个口径）。
    void Reset() noexcept {
        for (std::size_t slot = 0; slot < kSlots; ++slot) {
            edge_[slot] = 0;
            observed_[slot] = 0;
            frame_[slot] = kNoFrame;
            for (std::size_t index = 0; index < kSlots; ++index) {
                lastPressedFrame_[slot][index] = kNoFrame;
                peakReleaseRun_[slot][index] = 0;
            }
        }
    }

private:
    static constexpr std::size_t kSlots = kIndexMask + 1;
    //: **这一帧**已经报出去的边沿（帧内不撤销 ⇒ 同帧问多少次都同一个答案）。
    std::uint32_t edge_[kSlots]{};
    //: 至少被观察过一次的动作（区分"没按"与"还没看过"）。
    std::uint32_t observed_[kSlots]{};
    //: 上一次更新时的帧号（用来判定"新的一帧"）。
    std::uint32_t frame_[kSlots]{};
    //: 每个动作**上一次读到"按住"的帧号**（去抖判据的核心；`kNoFrame` = 还没读过）。
    std::uint32_t lastPressedFrame_[kSlots][kSlots]{};
    //: 诊断：观察过的最长闪断帧数。
    std::uint8_t peakReleaseRun_[kSlots][kSlots]{};
};

} // namespace LuaRuntime
