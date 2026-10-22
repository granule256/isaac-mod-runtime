"""输入边沿语义：`Input.IsActionTriggered` / `Input.IsButtonTriggered` 的**帧上事件**判定。

## 当前口径（批次 381，2026-10-06）

边沿 = **引擎帧上采样出来的一次事件，只在它发生的那一帧有效**。

* 每帧在**帧号自增之后、派发回调之前**（`ManagedFrameClock` 的帧边界钩子）由
  `SampleInputFrame()` 主动采一次，把这一帧的边沿按 (码, 设备) 写进
  `LuaRuntime::InputFrameEdges`（`runtime/source/input_edge.hpp`，本文件的权威接口）；
* 查询侧退化成**纯读**：`Triggered(code, controller, frame)` = "这一格记录的边沿帧号
  == 你给的帧号吗"，`Pressed(...)` = "这一格记录的按住帧号 == 你给的帧号吗"；
* ⇒ 模组"什么时候问、问几个、跳过哪一个"**不再改变语义**：同一帧内问多少次一样，
  **下一帧一律 false**。

这一改治的是两张用户可见的脸（旧口径下同时存在，机制见 `input_edge.hpp` 第五节与
`docs/会话交接-20261006-一-输入边沿机制与批次380回归.md` §4.3）：

* **"一次推动走两格"** —— 中文版 MCM 的 `actionsDown/Up/Left/Right` 同时含移动动作与
  菜单动作，而 `inputhelper.lua` 的 `MultipleActionTriggered` 碰到第一个为真就 `return`
  ⇒ 排在后面的动作号当帧不被问 ⇒ 旧判定下一帧把它认成"新按下"⇒ 光标再走一格；
* **"十字键又驱动了菜单"** —— `modconfig.lua:2259` 的
  `MultipleButtonTriggered(ignoreActionButtons)` 闸门把动作导航整块跳过 ⇒ 同理。

## 本文件的两半断言

1. **行为（宿主真跑）**：`InputFrameEdges` 是纯逻辑 ⇒ 内嵌 C++ harness 直接跑它的每条
   分支。第 10 条是**反向自证**：另写一个"旧规则"（批次 380 的
   `bool observe(code, controller, pressed, frame)`，"自这个调用方上一次问过以来"从没按住
   变成按住、且不看 frame）小 struct，用同样的输入序列跑，断言"**旧规则给 true 的那几格，
   新规则必须给 false**"——这一条保证新用例真的钉住了新旧差别，不是自说自话。
2. **接线可见性（文本）**：保证"那条路还在"（纯读判定、帧边界钩子、采样探针、A2 的按住同源）
   ＋"旧的会随调用方节奏变的形状没有回来"。**这一半不验行为。**

## ★ 更正：历史口径（保留，别删）

* **批次 107（2026-09-20）建立**：引擎里那两条"刚按下"都不能用（`ManagerBase::IsActionTriggered`
  只遍历绑定的按钮、不看模拟量 ⇒ 摇杆方向永远假；设备 `IsButtonTriggered` 测的是 `+0x38`，
  而 `Poll` 每帧把 `+0x30` 拷进 `+0x38` ⇒ 语义是"上一帧也按着"）。⇒ 在引擎权威的**按住**
  状态上自己求差分。
* **★ 更正：批次 221（2026-09-30）曾删掉"松手去抖窗口"**（批次 110 加、220 从 6 调到 20）。
  当时判定 = **严格相邻帧差分**（`frame == 上一次采样 + 1`）。理由（不删）：窗口是"猜一个
  时长"、两侧都会咬人，用户当时两侧症状同时出现。**但"严格相邻帧"这个形状本身也已被推翻**
  —— 见下一条。
* **★ 更正：批次 380（2026-10-06）曾把判定改成 `pressed && !entry.held`**（"自这个调用方
  上一次问过以来从没按住 → 按住"），想修"渲染回调比更新回调稀约 5.4% ⇒ 隔帧把整次按下吞掉"。
  **该改法已作废**：它的输入仍是"调用方什么时候来问"⇒ 边沿定义跟着询问节奏走，于是旧病复发
  （一张旋钮两个相反的脸）。批次 381 把它彻底换成"帧上采样 + 纯读"。

⇒ 旧测试文件里的口径（"自上次询问以来"、`ActionEdgeTracker::Observe`）**全部作废**，本文件重写。
"""

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "runtime" / "source"
LUA_DIR = ROOT / "runtime" / "src" / "interfaces" / "lua"

HARNESS = r'''
#include "input_edge.hpp"

#include <cstdint>
#include <cstdio>

using LuaRuntime::InputFrameEdges;

namespace {

int failures = 0;

void Check(bool condition, const char* label) {
    if (!condition) {
        std::printf("FAIL %s\n", label);
        ++failures;
    }
}

// 真机上的那两个值：动作 4，控制器 33（玩家自己的 `ControllerIndex` ⇒ 槽 1）。
constexpr std::uint32_t kAction = 4;
constexpr std::uint32_t kController = 33;
// 第 3 条："一次推动走两格"——同时被点亮的两个动作号（移动号 + 菜单号）。
constexpr std::uint32_t kMoveDown = 2;
constexpr std::uint32_t kMenuDown = 23;
// 第 4 条：十字键的按键号（`g_ButtonEdge` 的语义走这一格）。
constexpr std::uint32_t kButton = 6;
// 第 7 条："任意设备"聚合槽（低 5 位 = 31）。
constexpr std::uint32_t kAnyDevice = 0xFFFFFFFFu;

// ★★ 第 10 条反向自证用：**旧规则**（批次 380 的形状）。
//
// 判定 = "**自这个调用方上一次问过以来**从没按住、这一次按住"（`pressed && has && !held`），
// 且**完全不看 frame 是不是当前帧** ⇒ 迟到的查询照样能拿到 true。这里只做对照，别拿去用。
struct OldRule {
    struct Cell {
        bool held = false;
        bool has = false;
    };
    Cell cells[InputFrameEdges::kSlots][InputFrameEdges::kSlots];

    bool Observe(std::uint32_t code, std::uint32_t controller, bool pressed,
                 std::uint32_t frame) {
        static_cast<void>(frame);   // 旧规则不看帧号 —— 这正是被推翻的那一点。
        Cell& entry = cells[controller & InputFrameEdges::kIndexMask][code & InputFrameEdges::kIndexMask];
        const bool edge = pressed && entry.has && !entry.held;
        entry.held = pressed;
        entry.has = true;
        return edge;
    }
};

}  // namespace

int main() {
    // ① 同一帧内问两次 ⇒ 同答案。
    {
        InputFrameEdges edges{};
        bool released[InputFrameEdges::kSlots] = {};
        edges.SampleRow(kController, 100, released, nullptr);
        bool pressed[InputFrameEdges::kSlots] = {};
        pressed[kAction] = true;
        edges.SampleRow(kController, 101, pressed, nullptr);
        const bool first = edges.Triggered(kAction, kController, 101);
        const bool second = edges.Triggered(kAction, kController, 101);
        Check(first, "第1条：边沿帧上有边沿");
        Check(first == second, "第1条：同一帧内问两次答案相同");
        Check(edges.Triggered(kAction, kController, 101), "第1条：第三次问仍相同");
    }

    // ② **边沿的下一帧再问 ⇒ false**（整批的要害）。哪怕那一帧模组没问 / 没采过，也必须 false。
    {
        InputFrameEdges edges{};
        bool released[InputFrameEdges::kSlots] = {};
        edges.SampleRow(kController, 200, released, nullptr);
        bool pressed[InputFrameEdges::kSlots] = {};
        pressed[kAction] = true;
        edges.SampleRow(kController, 201, pressed, nullptr);
        Check(edges.Triggered(kAction, kController, 201), "第2条：201 那帧有边沿");
        // 201 那一帧模组没问；202 才第一次问（202 没被采过）。
        Check(!edges.Triggered(kAction, kController, 202), "第2条：下一帧再问必须 false（该帧没采过）");
        // 就算 202 被采过（仍按住），也还是 false。
        edges.SampleRow(kController, 202, pressed, nullptr);
        Check(!edges.Triggered(kAction, kController, 202), "第2条：下一帧采过也 false");
        Check(!edges.Triggered(kAction, kController, 203), "第2条：再往后一律 false");
    }

    // ③ "走两格"回归：一次推动同时点亮两个动作号 ⇒ 两个号都在**同一帧**报边沿；
    //    下一帧**都必须 false**（旧规则会说 menuDown 还是 true ⇒ 光标再走一格）。
    {
        InputFrameEdges edges{};
        bool released[InputFrameEdges::kSlots] = {};
        edges.SampleRow(kController, 300, released, nullptr);
        bool pressed[InputFrameEdges::kSlots] = {};
        pressed[kMoveDown] = true;
        pressed[kMenuDown] = true;
        edges.SampleRow(kController, 301, pressed, nullptr);
        Check(edges.Triggered(kMoveDown, kController, 301), "第3条：移动号本帧报边沿");
        Check(edges.Triggered(kMenuDown, kController, 301), "第3条：菜单号同一帧也报边沿");
        edges.SampleRow(kController, 302, pressed, nullptr);
        Check(!edges.Triggered(kMenuDown, kController, 302), "第3条：下一帧菜单号必须 false（否则走两格）");
        Check(!edges.Triggered(kMoveDown, kController, 302), "第3条：下一帧移动号也 false");
    }

    // ④ 十字键闸门回归：用两个 InputFrameEdges 实例分别当"按键表"与"动作表"。
    //    帧 f 两表都有边沿，但模组那一帧被闸门整块跳过（没问动作），到 f+1 才第一次问 ⇒ 必须 false。
    {
        InputFrameEdges buttonTable{};
        InputFrameEdges actionTable{};
        bool released[InputFrameEdges::kSlots] = {};
        buttonTable.SampleRow(kController, 400, released, nullptr);
        actionTable.SampleRow(kController, 400, released, nullptr);
        bool button[InputFrameEdges::kSlots] = {};
        button[kButton] = true;
        bool action[InputFrameEdges::kSlots] = {};
        action[kAction] = true;
        buttonTable.SampleRow(kController, 401, button, nullptr);
        actionTable.SampleRow(kController, 401, action, nullptr);
        Check(buttonTable.Triggered(kButton, kController, 401), "第4条：按键表本帧有边沿");
        Check(actionTable.Triggered(kAction, kController, 401), "第4条：动作表本帧也有边沿");
        // 模组 401 被 `MultipleButtonTriggered(ignoreActionButtons)` 闸门跳过 ⇒ 402 才第一次问动作。
        buttonTable.SampleRow(kController, 402, button, nullptr);
        actionTable.SampleRow(kController, 402, action, nullptr);
        Check(!actionTable.Triggered(kAction, kController, 402), "第4条：402 第一次问动作必须 false");
    }

    // ⑤ 按住跨帧不再报；松开一帧后再按 ⇒ 报一次。
    {
        InputFrameEdges edges{};
        bool released[InputFrameEdges::kSlots] = {};
        edges.SampleRow(kController, 500, released, nullptr);
        bool pressed[InputFrameEdges::kSlots] = {};
        pressed[kAction] = true;
        edges.SampleRow(kController, 501, pressed, nullptr);
        Check(edges.Triggered(kAction, kController, 501), "第5条：有历史后第一次按下报一次");
        edges.SampleRow(kController, 502, pressed, nullptr);
        edges.SampleRow(kController, 503, pressed, nullptr);
        Check(!edges.Triggered(kAction, kController, 502), "第5条：连续按住 502 不再报");
        Check(!edges.Triggered(kAction, kController, 503), "第5条：连续按住 503 不再报");
        edges.SampleRow(kController, 504, released, nullptr);
        Check(!edges.Triggered(kAction, kController, 504), "第5条：松开那一帧不报");
        edges.SampleRow(kController, 505, pressed, nullptr);
        Check(edges.Triggered(kAction, kController, 505), "第5条：松开一帧后再按报一次");
    }

    // ⑥ 运行时第一帧不算边沿（自己差分那条路）；直接喂 edge_or_null 那条路第一帧就信任调用方。
    {
        InputFrameEdges edges{};
        bool pressed[InputFrameEdges::kSlots] = {};
        pressed[kAction] = true;
        edges.SampleRow(kController, 600, pressed, nullptr);
        Check(!edges.Triggered(kAction, kController, 600),
              "第6条：全新实例第一帧按住（自己差分）不算边沿");
        Check(edges.Pressed(kAction, kController, 600), "第6条：第一帧的按住仍可读");
    }
    {
        InputFrameEdges edges{};
        bool pressed[InputFrameEdges::kSlots] = {};
        pressed[kButton] = true;
        bool edge[InputFrameEdges::kSlots] = {};
        edge[kButton] = true;
        edges.SampleRow(kController, 601, pressed, edge);
        Check(edges.Triggered(kButton, kController, 601),
              "第6条：直接喂 edge_or_null ⇒ 第一帧就信任调用方（引擎自带上一帧位图）");
    }

    // ⑦ "任意设备"聚合：两个 controller 槽分别按下 ⇒ 聚合槽（0xFFFFFFFF）边沿只在那一帧为真。
    {
        InputFrameEdges edges{};
        bool released[InputFrameEdges::kSlots] = {};
        edges.SampleRow(33, 700, released, nullptr);              // 槽 1
        edges.SampleRow(0, 700, released, nullptr);               // 槽 0
        edges.SampleRow(kAnyDevice, 700, released, nullptr);      // 槽 31（聚合）
        bool pressed[InputFrameEdges::kSlots] = {};
        pressed[kAction] = true;
        edges.SampleRow(33, 701, pressed, nullptr);
        edges.SampleRow(0, 701, pressed, nullptr);
        edges.SampleRow(kAnyDevice, 701, pressed, nullptr);
        Check(edges.Triggered(kAction, 33, 701), "第7条：设备槽 1 本帧有边沿");
        Check(edges.Triggered(kAction, 0, 701), "第7条：设备槽 0 本帧有边沿");
        Check(edges.Triggered(kAction, kAnyDevice, 701), "第7条：聚合槽本帧有边沿");
        Check(!edges.Triggered(kAction, kAnyDevice, 700), "第7条：聚合槽上一帧 false");
        edges.SampleRow(kAnyDevice, 702, pressed, nullptr);
        Check(!edges.Triggered(kAction, kAnyDevice, 702), "第7条：聚合槽下一帧 false（只在那一帧）");
    }

    // ⑧ 帧号回退 / 跳变不误报。
    {
        InputFrameEdges edges{};
        bool released[InputFrameEdges::kSlots] = {};
        edges.SampleRow(kController, 800, released, nullptr);
        bool pressed[InputFrameEdges::kSlots] = {};
        pressed[kAction] = true;
        edges.SampleRow(kController, 801, pressed, nullptr);
        Check(edges.Triggered(kAction, kController, 801), "第8条：801 有边沿");
        Check(!edges.Triggered(kAction, kController, 999), "第8条：用错的 frame 查 ⇒ false");
        Check(!edges.Triggered(kAction, kController, 800), "第8条：差一帧查 ⇒ false");
        // 帧号往回跳（801 -> 790）：不产生边沿（判定纯读、不做帧号算术）。
        edges.SampleRow(kController, 790, pressed, nullptr);
        Check(!edges.Triggered(kAction, kController, 790), "第8条：帧号回退不产生边沿");
        // 跨帧（790 -> 802）仍按住：不报。
        edges.SampleRow(kController, 802, pressed, nullptr);
        Check(!edges.Triggered(kAction, kController, 802), "第8条：跨帧仍按住不报");
    }

    // ⑨ 没采样 / 采样失败 ⇒ 答 false；`pressed=nullptr` 不崩且不改变已有记录。
    {
        InputFrameEdges edges{};
        Check(!edges.Triggered(kAction, kController, 1), "第9条：全新实例没采过 ⇒ Triggered false");
        Check(!edges.Pressed(kAction, kController, 1), "第9条：全新实例没采过 ⇒ Pressed false");
        Check(!edges.HasFrame(kAction, kController, 1), "第9条：全新实例没采过 ⇒ HasFrame false");
    }
    {
        InputFrameEdges edges{};
        bool released[InputFrameEdges::kSlots] = {};
        edges.SampleRow(kController, 900, released, nullptr);
        bool pressed[InputFrameEdges::kSlots] = {};
        pressed[kAction] = true;
        edges.SampleRow(kController, 901, pressed, nullptr);
        Check(edges.Triggered(kAction, kController, 901), "第9条(防御)：采样后有边沿");
        edges.SampleRow(kController, 902, nullptr, nullptr);   // pressed=nullptr
        Check(edges.Triggered(kAction, kController, 901),
              "第9条(防御)：pressed=nullptr 不改变已有记录（901 仍答边沿）");
    }

    // ⑩ ★★ 反向自证：旧规则（批次 380 形状）在**同样的输入序列**上会给出 true，
    //     而新规则必须给 false。逐格断言"两者结论不同"。
    {
        // ---- 对第 2 条 ----
        InputFrameEdges edges{};
        OldRule oldRule{};
        bool released[InputFrameEdges::kSlots] = {};
        edges.SampleRow(kController, 1000, released, nullptr);
        Check(!oldRule.Observe(kAction, kController, false, 1000),
              "反证2：旧规则首问（没按住）不算边沿");
        bool pressed[InputFrameEdges::kSlots] = {};
        pressed[kAction] = true;
        edges.SampleRow(kController, 1001, pressed, nullptr);
        Check(edges.Triggered(kAction, kController, 1001), "反证2：新规则 1001 有边沿");
        // 模组 1001 那帧没问（被闸门跳过）；1002 才第一次问。
        edges.SampleRow(kController, 1002, pressed, nullptr);
        const bool newAns2 = edges.Triggered(kAction, kController, 1002);
        const bool oldAns2 = oldRule.Observe(kAction, kController, true, 1002);
        Check(!newAns2, "反证2：新规则 1002 问 = false（边沿只在 1001 那帧有效）");
        Check(oldAns2, "反证2：旧规则 1002 问 = true（自上次询问以来发生按下）");
        Check(newAns2 != oldAns2, "反证2：第2条这一格『旧 true / 新 false』结论不同");
    }
    {
        // ---- 对第 3 条（"一次推动走两格"）----
        InputFrameEdges edges{};
        OldRule oldRule{};
        bool released[InputFrameEdges::kSlots] = {};
        edges.SampleRow(kController, 1100, released, nullptr);
        static_cast<void>(oldRule.Observe(kMoveDown, kController, false, 1100));
        static_cast<void>(oldRule.Observe(kMenuDown, kController, false, 1100));
        bool pressed[InputFrameEdges::kSlots] = {};
        pressed[kMoveDown] = true;
        pressed[kMenuDown] = true;
        edges.SampleRow(kController, 1101, pressed, nullptr);
        Check(edges.Triggered(kMoveDown, kController, 1101), "反证3：新 1101 kMoveDown 边沿");
        Check(edges.Triggered(kMenuDown, kController, 1101), "反证3：新 1101 kMenuDown 边沿");
        Check(oldRule.Observe(kMoveDown, kController, true, 1101), "反证3：旧 1101 kMoveDown 边沿");
        // ★ 模拟 `MultipleActionTriggered` 碰到第一个为真就 return ⇒ 1101 **不问** kMenuDown。
        edges.SampleRow(kController, 1102, pressed, nullptr);
        const bool newMove = edges.Triggered(kMoveDown, kController, 1102);
        const bool newMenu = edges.Triggered(kMenuDown, kController, 1102);
        const bool oldMove = oldRule.Observe(kMoveDown, kController, true, 1102);
        const bool oldMenu = oldRule.Observe(kMenuDown, kController, true, 1102);
        Check(!newMove && !oldMove, "反证3：kMoveDown 这一格新旧一致（都 false）");
        Check(!newMenu, "反证3：新规则 1102 kMenuDown = false（光标不走第二格）");
        Check(oldMenu, "反证3：旧规则 1102 kMenuDown = true（光标再走一格）");
        Check(newMenu != oldMenu, "反证3：第3条这一格『旧 true / 新 false』结论不同");
    }
    {
        // ---- 对第 4 条（十字键闸门）----
        InputFrameEdges buttonTable{};
        InputFrameEdges actionTable{};
        OldRule oldRule{};
        bool released[InputFrameEdges::kSlots] = {};
        buttonTable.SampleRow(kController, 1200, released, nullptr);
        actionTable.SampleRow(kController, 1200, released, nullptr);
        static_cast<void>(oldRule.Observe(kAction, kController, false, 1200));
        bool button[InputFrameEdges::kSlots] = {};
        button[kButton] = true;
        bool action[InputFrameEdges::kSlots] = {};
        action[kAction] = true;
        buttonTable.SampleRow(kController, 1201, button, nullptr);
        actionTable.SampleRow(kController, 1201, action, nullptr);
        Check(buttonTable.Triggered(kButton, kController, 1201), "反证4：新 1201 按键边沿");
        Check(actionTable.Triggered(kAction, kController, 1201), "反证4：新 1201 动作边沿");
        // 模组 1201 被 `MultipleButtonTriggered(ignoreActionButtons)` 整块跳过 ⇒ 1202 才第一次问动作。
        buttonTable.SampleRow(kController, 1202, button, nullptr);
        actionTable.SampleRow(kController, 1202, action, nullptr);
        const bool newAns4 = actionTable.Triggered(kAction, kController, 1202);
        const bool oldAns4 = oldRule.Observe(kAction, kController, true, 1202);
        Check(!newAns4, "反证4：新规则 1202 第一次问动作 = false（十字键不驱动菜单）");
        Check(oldAns4, "反证4：旧规则 1202 第一次问动作 = true（十字键又驱动菜单）");
        Check(newAns4 != oldAns4, "反证4：第4条这一格『旧 true / 新 false』结论不同");
    }

    // ⑪ ★★★ 批次 400 的回归钉：**局内那对位图恒等**这一场景。
    //    批次 381 起，采样器把 `本帧 & ~上帧` 当 `edge_or_null` 喂进来；真机读数证明
    //    设备对象 `+0x30`/`+0x38` 在**局内**的采样点恒等 ⇒ 这份边沿**恒 false** ⇒
    //    `IsButtonTriggered` 在里面永远 false ⇒ MCM 永远开不出来。下面把两侧都钉住。
    {
        InputFrameEdges broken{};
        bool released[InputFrameEdges::kSlots] = {};
        bool pressed[InputFrameEdges::kSlots] = {};
        pressed[kButton] = true;
        bool flatEdge[InputFrameEdges::kSlots] = {};   // = 引擎的 `本帧 & ~上帧`（局内恒 0）
        broken.SampleRow(kController, 1300, released, flatEdge);
        broken.SampleRow(kController, 1301, pressed, flatEdge);
        Check(!broken.Triggered(kButton, kController, 1301),
              "第11条：信那对恒等的位图 ⇒ 按下了也报不出边沿（批次 381~399 的真机症状）");
        broken.SampleRow(kController, 1302, pressed, flatEdge);
        Check(!broken.Triggered(kButton, kController, 1302),
              "第11条：而且下一帧照样报不出（不是'迟到'，是永远没有）");

        InputFrameEdges fixed{};
        fixed.SampleRow(kController, 1300, released, nullptr);
        fixed.SampleRow(kController, 1301, pressed, nullptr);
        Check(fixed.Triggered(kButton, kController, 1301),
              "第11条：同一串输入走自己差分（nullptr）就报得出边沿（批次 400 的修法）");
        fixed.SampleRow(kController, 1302, pressed, nullptr);
        Check(!fixed.Triggered(kButton, kController, 1302),
              "第11条：边沿仍然只在那一帧有效（381 的口径没被改回去）");
    }

    if (failures != 0) {
        std::printf("INPUT_ACTION_EDGE_CHECKS_FAILED %d\n", failures);
        return 1;
    }
    std::printf("INPUT_ACTION_EDGE_CHECKS_PASSED\n");
    return 0;
}
'''


def host_compiler() -> str | None:
    for candidate in ("c++", "clang++", "g++"):
        found = shutil.which(candidate)
        if found is not None:
            return found
    return None


class ActionEdgeBehaviourTests(unittest.TestCase):
    """行为（宿主真跑）：`InputFrameEdges` 是纯逻辑 ⇒ 直接跑它的每条分支。"""

    def test_edge_semantics_on_host(self):
        compiler = host_compiler()
        if compiler is None:
            self.skipTest("宿主机没有 C++ 编译器")
        with tempfile.TemporaryDirectory(prefix="isaac-input-edge-") as directory:
            workdir = Path(directory)
            source = workdir / "harness.cpp"
            source.write_text(HARNESS.lstrip(), encoding="utf-8")
            binary = workdir / "harness"
            build = subprocess.run(
                [compiler, "-std=c++23", "-Wall", "-Wextra", "-Werror", "-I", str(SOURCE),
                 str(source), "-o", str(binary)],
                text=True, capture_output=True,
            )
            self.assertEqual(build.returncode, 0, build.stdout + build.stderr)
            run = subprocess.run([str(binary)], text=True, capture_output=True)
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
            self.assertIn("INPUT_ACTION_EDGE_CHECKS_PASSED", run.stdout)


class ActionEdgeWiringTests(unittest.TestCase):
    """接线可见性（文本）。**不验行为** —— 这一半只保证"那条路还在"，见文件头的口径说明。"""

    @classmethod
    def setUpClass(cls):
        cls.input_api = (LUA_DIR / "input_api.cpp").read_text(encoding="utf-8")
        cls.input_header = (LUA_DIR / "input_api.hpp").read_text(encoding="utf-8")
        cls.edge_header = (SOURCE / "input_edge.hpp").read_text(encoding="utf-8")
        cls.isaac_api = (LUA_DIR / "isaac_api.cpp").read_text(encoding="utf-8")
        cls.deviation = (LUA_DIR / "api_deviation.cpp").read_text(encoding="utf-8")

    def test_edge_table_shape_is_pure_read(self):
        """★ 批次 381：边沿表退化成**纯读** —— 判定只看"这一格在本帧是不是边沿"。

        钉住 `InputFrameEdges` 的接口形状（采样入口 + 三个纯读入口）与判定本体
        `entry.frame == frame && entry.edge`（纯比较、不做任何帧号算术）。
        """
        self.assertIn("void SampleRow(", self.edge_header)
        self.assertIn("bool Triggered(", self.edge_header)
        self.assertIn("bool Pressed(", self.edge_header)
        self.assertIn("bool HasFrame(", self.edge_header)
        self.assertIn("entry.frame == frame && entry.edge", self.edge_header)

    def test_old_caller_paced_shapes_do_not_come_back(self):
        """★ 不许把"由调用方询问节奏决定"的旧形状加回来（批次 221 的窗口 + 批次 380 的 Observe）。

        * `kReleaseFrames` = 批次 110/220 的"松手去抖窗口"，批次 221 已删；
        * `frame == entry.frame + 1u` = 批次 221 的"必须严格相邻帧"，批次 380 已删；
        * `Observe(` = 批次 380 的"自这个调用方上一次问过以来"接口，批次 381 已删。
        """
        self.assertNotIn("kReleaseFrames", self.edge_header)
        self.assertNotIn("frame == entry.frame + 1u", self.edge_header)
        self.assertNotIn("Observe(", self.edge_header)

    def test_queries_are_pure_reads_of_the_edge_table(self):
        """查询侧必须走**纯读**：`IsActionTriggered` 读 `g_ActionEdge.Triggered(`、
        `IsButtonTriggered` 读 `g_ButtonEdge.Triggered(`；不许再出现调用方驱动的 `Observe`。
        """
        self.assertIn("g_ActionEdge.Triggered(", self.input_api)
        self.assertIn("g_ButtonEdge.Triggered(", self.input_api)
        self.assertNotIn(".Observe(", self.input_api)

    def test_frame_boundary_sampling_is_wired(self):
        """★ 批次 381：每帧固定时刻采一次 —— `SampleInputFrame()` + 帧边界钩子。

        帧号唯一来源那条老纪律还在：输入路径上不许再出现毫秒时钟（批次 220 前误报的根因之一）。
        """
        self.assertIn("void SampleInputFrame(", self.input_api)
        self.assertIn("SetFrameBoundaryHook(&FrameBoundaryHookEntry)", self.input_api)
        self.assertNotIn("EngineMillisecondsNow", self.input_api)

    def test_device_table_is_read_once_per_frame(self):
        """★ 批次 221：设备表**每帧只读一次**（每帧多次查询都去读表 ⇒ 失败会伪装成"闪断"）。

        采样器复用同一份"每帧只读一次"的缓存（`g_InputDeviceTableFrame` + `ReadNsInputDeviceTable`）。
        """
        self.assertIn("g_InputDeviceTableFrame != frame", self.input_api)
        self.assertIn("ReadNsInputDeviceTable", self.input_api)

    def test_pressed_reads_the_same_sample(self):
        """★ 批次 381 的 A2：`IsButtonPressed` 对采样集合内的格子读**同一次采样**的按住值。"""
        self.assertIn("g_ButtonEdge.Pressed(", self.input_api)

    def test_edge_state_is_session_scoped(self):
        """上升沿表是会话级状态：新会话必须清空（否则上一次会话"按住过"的记录会凭空报一次边沿）。"""
        self.assertIn("void ResetInputEdgeState() noexcept;", self.input_header)
        self.assertIn("ResetInputEdgeState();", self.isaac_api)

    def test_new_probes_exist_outside_the_anonymous_namespace(self):
        """★ 批次 381：新增的采样探针定义必须在第一个匿名命名空间**之前**（外部链接）。

        否则读数工具按符号查不到（本项目同类事故第 5 次，见批次 214）。探针：
        `g_InputSampleFrame` / `g_InputSampleCalls` / `g_InputSampleCodes` /
        `g_InputSampleDevices` / `g_InputSampleFailures`。
        """
        anonymous_namespace = self.input_api.index("namespace {")
        for probe in ("g_InputSampleFrame", "g_InputSampleCalls", "g_InputSampleCodes",
                      "g_InputSampleDevices", "g_InputSampleFailures"):
            self.assertLess(self.input_api.index(f"std::atomic<std::uint32_t> {probe}"),
                            anonymous_namespace,
                            f"{probe} 必须定义在匿名命名空间之外，否则读数工具读不到它")

    def test_the_deviation_is_registered(self):
        """换成我们自己的语义必须进偏离台账（本项目对"交回的不是引擎值"的硬要求）。"""
        self.assertIn("{0x09010004,", self.deviation)
        entry = self.deviation[self.deviation.index("{0x09010004,"):]
        entry = entry[:entry.index("},")]
        self.assertIn("判据：", entry)
        self.assertIn("偏离后果：", entry)

    def test_button_side_no_longer_trusts_the_engines_frame_pair(self):
        """★★★ 批次 400：按键侧的边沿**不许再读引擎那对"本帧位图 / 上帧位图"**。

        为什么：真机读数证明那两格（设备对象 `+0x30` / `+0x38`）在**局内**的采样点**恒等**
        ⇒ `本帧 & ~上帧` 恒为 0 ⇒ 局内一次边沿都报不出来（菜单里却正常）⇒
        `Input.IsButtonTriggered` 在里面永远 false ⇒ **MCM 永远开不出来**。
        定案对比（`g_InputButtonEdgeCounts`，只有真答了 `true` 才加一）：
        批次 380 局内报过"右摇杆按下 3 次"（那版用户实测 MCM 能开）；
        批次 398 局内 8042 帧**全 0**。见 `input_edge.hpp` 第七节。

        ⇒ 现在按键侧第三个实参一律 `nullptr` —— 边沿由 `InputFrameEdges` 按**它自己上一帧的
        `held`** 差分（一帧一份、与调用方询问节奏无关）。
        """
        sampler = self._sample_input_frame_source()
        # ① 按键侧必须走"自己差分"那条路（第三个实参 = nullptr）。
        self.assertIn("g_ButtonEdge.SampleRow(", sampler)
        self.assertIn("buttonPressed, nullptr)", sampler)
        self.assertIn("aggButtonPressed, nullptr)", sampler)
        # ② 采样器里不许再碰"上帧位图"与手算的那份边沿数组。
        #   ⚠️ 只钉**代码形状**（声明 / 读取 / 实参名），不钉注释里的文字 ——
        #   本批的注释里就要写出"原先传的是哪个表达式"，把注释也算进去会自己把自己判红。
        self.assertNotIn("kKageInputDeviceKeysPreviousOffset", sampler)
        self.assertNotIn("std::uint32_t keysPrevious", sampler)
        self.assertNotIn("bool buttonEdge", sampler)
        self.assertNotIn("aggButtonEdge", sampler)

    def _sample_input_frame_source(self):
        """把 `SampleInputFrame` 的函数体切出来（后面那些函数不参与本条判定）。"""
        start = self.input_api.index("void SampleInputFrame(")
        end = self.input_api.index("void FrameBoundaryHookEntry(", start)
        return self.input_api[start:end]


if __name__ == "__main__":
    unittest.main()
