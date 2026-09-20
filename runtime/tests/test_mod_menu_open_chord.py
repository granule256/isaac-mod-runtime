"""门禁：模组开关菜单的**呼出键必须是组合键**（批次 080，2026-09-19）。

## 为什么有这条门禁

用户实测反馈："按 `-` 时 GoodTrip 的地图和模组开关**都会**出现"——
`-`（`ACTION_MAP`）是**游戏自己的地图键**，GoodTrip 的地图叠加也挂在它上面，
我们的菜单早期用单键呼出，等于和它抢同一个键。而 `+`（`ACTION_PAUSE`）是暂停键，
单独占用同样会抢。所以呼出改成**组合键**：单独 `-` = 地图、单独 `+` = 暂停、
**两个一起** = 我们的菜单。

## 这条门禁钉什么

菜单脚本是**内嵌 Lua**（`runtime/source/program/embedded_mod_menu_script.hpp`），
它的按键路径在宿主上跑不起来（`Input.IsActionPressed` 的原生入口在设备上），所以这里钉的是
**脚本的形状**，而且钉得很窄：只钉"呼出分支同时看了两个键"这一件事。

判据（改宽改窄都会红）：
1. `KEY` 表里必须有组合键的第二个键，且它是 `ACTION_PAUSE`（不是别的动作号）；
2. 呼出分支必须**同时**出现"按住 `open_modifier`"与"过沿 `open`"两个条件（两个方向都认）；
3. 脚本里**不许**再出现"只按一个键就呼出"的老形状（`AnyPressedOnce({ KEY.open, KEY.tab })`）。
"""

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "runtime" / "source" / "program" / "embedded_mod_menu_script.hpp"


class ModMenuOpenChordTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = SCRIPT.read_text(encoding="utf-8")

    def test_modifier_key_is_the_pause_action(self):
        """组合键的第二个键必须是 `ACTION_PAUSE`（Switch 上的 `+`），不能是别的动作号。"""
        self.assertIn('open_modifier = ActionCode("ACTION_PAUSE", 12)', self.text)

    def test_open_requires_both_keys(self):
        """呼出分支要同时看"另一个键按住"和"这一键过沿"，且两个方向都认。"""
        self.assertIn("Held(KEY.open_modifier) and PressedOnce(KEY.open)", self.text)
        self.assertIn("Held(KEY.open) and PressedOnce(KEY.open_modifier)", self.text)

    def test_single_key_open_shape_is_gone(self):
        """老形状（单键呼出）不许回退 —— 回退就等于又把地图键抢回来。

        只钉这一条具体的表达式，不做泛化文本匹配（泛化匹配会随无关改动误报）。
        """
        self.assertNotIn("AnyPressedOnce({ KEY.open, KEY.tab })", self.text)
        self.assertNotIn("AnyPressedOnce({ KEY.open })", self.text)


if __name__ == "__main__":
    unittest.main()
