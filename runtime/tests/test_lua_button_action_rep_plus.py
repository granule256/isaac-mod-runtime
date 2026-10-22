"""`ButtonAction` 的 16/17/18 必须按 **Rep+** 的名字 —— 批次 218（2026-09-30）。

## 为什么单开一条门禁

`ButtonAction` 是**手写**表（`runtime/source/lua_runtime.cpp` 的 `kButtonActionConstants`），
不由生成器产出，所以**以前没有任何东西拿文档对过它**。而 PC 文档
（`tools/pc_enum_docs/ButtonAction.md`，仓库内的逐字节副本）明写这三个值**在 Rep+ 改了名字**：

```
|[.abrep]  |16 |ACTION_RESTART     | Restart run |
|[.repplus]|16 |ACTION_FULLSCREEN  | Toggle fullscreen **(Value changed with Rep+)** |
|[.abrep]  |17 |ACTION_FULLSCREEN  | Toggle fullscreen |
|[.repplus]|17 |ACTION_MUTE        | Mute gameplay **(Value changed with Rep+)** |
|[.abrep]  |18 |ACTION_MUTE        | Mute gameplay |
|[.repplus]|18 |ACTION_RESTART     | Restart run **(Value changed with Rep+)** |
```

我们跑的是 Rep+（1.7.9b）⇒ **16 = ACTION_FULLSCREEN、17 = ACTION_MUTE、18 = ACTION_RESTART**。
改之前我们写的是 AB/AB+ 那一套（16=RESTART / 17=FULLSCREEN / 18=MUTE）⇒ **错位**：
模组写 `ButtonAction.ACTION_RESTART` 想按"重开"，实际会问到全屏切换那个动作。

★ 这是"**值对了、名字错了**"这一类缺陷：不报错、不崩，只是**问错了动作**
（真机上表现为"按这个键触发了别的功能"）。所以必须用文档逐行钉住。

## 这条门禁钉什么

1. 仓库内的契约页里那三对行确实存在（`abrep` 与 `repplus` 各一行、且 `repplus` 那行带
   "Value changed with Rep+" 的注明）—— 也就是说"该按 Rep+ 读"这件事本身有出处；
2. 我们表里的三个名字分别是 **FULLSCREEN / MUTE / RESTART**；
3. 值不变（16 / 17 / 18），且表里**只有一个** `ACTION_FULLSCREEN` / `ACTION_MUTE` / `ACTION_RESTART`
   （防"改一半、两个都留着"）。
"""

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CONTRACT = ROOT / "tools" / "pc_enum_docs" / "ButtonAction.md"
RUNTIME = ROOT / "runtime" / "source" / "lua_runtime.cpp"

#: Rep+ 下的三个名字（值 → 名字）。
REP_PLUS_NAMES = {16: "ACTION_FULLSCREEN", 17: "ACTION_MUTE", 18: "ACTION_RESTART"}


def rep_plus_rows() -> dict[int, str]:
    """从契约页里取 `.repplus` 那几行的「值 → 枚举名」。"""
    rows: dict[int, str] = {}
    for line in CONTRACT.read_text(encoding="utf-8").splitlines():
        if ".repplus" not in line:
            continue
        match = re.match(r"\|\[\s*\]\(#\)\{:\s*\.repplus[^}]*\}\|(\d+)\s*\|\s*([A-Za-z_][A-Za-z0-9_]*)", line)
        if match:
            rows[int(match.group(1))] = match.group(2)
    return rows


class ButtonActionRepPlusTests(unittest.TestCase):
    def test_the_contract_page_says_the_names_changed_with_rep_plus(self):
        rows = rep_plus_rows()
        for value, name in REP_PLUS_NAMES.items():
            with self.subTest(value=value):
                self.assertEqual(rows.get(value), name,
                                 f"契约页里 Rep+ 的 {value} 应当是 {name}")
        text = CONTRACT.read_text(encoding="utf-8")
        self.assertIn("Value changed with Rep+", text,
                      "契约页必须自己写着'这些名字随 Rep+ 变过' —— 不然'按 Rep+ 读'就没有出处")

    def test_our_table_uses_the_rep_plus_names(self):
        source = RUNTIME.read_text(encoding="utf-8")
        for value, name in REP_PLUS_NAMES.items():
            with self.subTest(value=value):
                self.assertIn(f'{{"{name}", {value}}}', source,
                              f"我们的 ButtonAction 表里 {value} 必须是 {name}")

    def test_the_old_ab_plus_names_are_gone(self):
        """AB/AB+ 的那套名字不许留（留一半就是"两个都认"，等于没修）。"""
        source = RUNTIME.read_text(encoding="utf-8")
        table = source[source.index("kButtonActionConstants{{"):]
        table = table[:table.index("}};")]
        for name in ("ACTION_FULLSCREEN", "ACTION_MUTE", "ACTION_RESTART"):
            with self.subTest(name=name):
                self.assertEqual(table.count(f'"{name}"'), 1,
                                 f"{name} 在表里必须恰好出现一次")


if __name__ == "__main__":
    unittest.main()
