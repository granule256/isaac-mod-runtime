"""门禁：Lua 侧**不许**再用"只认整数子类型"那个判据卡模组传进来的实参。

## 为什么要有它

PC 的 Lua 绑定一律走 `luaL_checkinteger`，而 Lua 5.3 的 `lua_tointegerx` **接受整值浮点**
（`3.0` ⇒ `3`，只有带小数部分才报错）。我们此前有 33 处处理器写成"只认整数子类型"那个判据
（`lua.h` 里的 `lua_isinteger`），于是**比 PC 严**：模组只要把数值算过一次除法
（Lua 的 `/` **永远**产生浮点），就会在我们这里报错、在 PC 上正常工作。

真机后果（2026-09-18）：EID 渲染**药丸描述**时调 `sprite:SetFrame(anim, frameNum)`，
被那条判据拒掉 ⇒ **整条回调中断、描述一个字都不显示**。用户看到的现象是
"站在药丸旁边什么信息都没有，连吃过的药丸也不显示"。

## 它检查什么

`runtime/src/interfaces/lua/` 下的所有源文件（**连注释一起**，纯文本匹配）：
不许出现那个函数名。要判"像不像整数"一律用
`interfaces/lua/lua_integer_argument.hpp` 的 `IsIntegerArgument()` / `IntegerArgumentAt()`
（口径与 PC 一致：整数子类型**或**取整后完全相等的浮点）。

写注释时要说明这件事，就**用文字描述**，别把那个函数名抄进去 —— 这条门禁是纯文本匹配，
抄进注释一样会红（本项目已有同类先例：派发点名（`test_lua_callback_dispatch_sites`）、
带 `.json` 后缀的文件名（`test_lua_json_module`））。
"""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LUA_API_DIR = ROOT / "runtime" / "src" / "interfaces" / "lua"

#: 被禁的标识符（拼出来是为了让本文件自己也不含那串字面量）。
BANNED = "lua_" + "isinteger"

#: **刻意的例外**：`json_api.cpp` 是 JSON 解码器，它的口径是"JSON 的 `1` 落成 Lua 整数、
#: `1.0` 落成 Lua 浮点"（与 Lua 词法一致）—— 那与"模组传进来的实参该有多宽容"是两件事。
#: 它由自己的契约用例钉住（`test_lua_json_module` 的 `integral float keeps its subtype`），
#: 并且它的 TU 自包含白名单也不允许引我们的头文件。
EXEMPT = {"json_api.cpp"}


class IntegerArgumentPolicyTests(unittest.TestCase):
    def test_lua_api_sources_do_not_use_the_strict_integer_predicate(self):
        offenders = []
        for path in sorted(LUA_API_DIR.rglob("*.cpp")) + sorted(LUA_API_DIR.rglob("*.hpp")):
            if path.name in EXEMPT:
                continue
            text = path.read_text(encoding="utf-8")
            for number, line in enumerate(text.splitlines(), start=1):
                if BANNED in line:
                    offenders.append(f"{path.relative_to(ROOT)}:{number}: {line.strip()[:100]}")
        self.assertEqual(
            offenders, [],
            "这些地方还在用'只认整数子类型'的判据（比 PC 严 ⇒ 模组算过的数会被拒）：\n  - "
            + "\n  - ".join(offenders)
            + "\n请改用 `lua_integer_argument.hpp` 的 `IsIntegerArgument` / `IntegerArgumentAt`。",
        )

    def test_the_shared_predicate_keeps_the_pc_semantics(self):
        """共享判据本身的口径：整数子类型 **或** 取整后完全相等的浮点（= `luaL_checkinteger`）。"""
        header = (LUA_API_DIR / "lua_integer_argument.hpp").read_text(encoding="utf-8")
        for token in ("IsIntegerArgument", "IntegerArgumentAt", "truncated", "luaL_checkinteger"):
            with self.subTest(token=token):
                self.assertIn(token, header)

    def test_setframe_uses_the_shared_predicate(self):
        """真机实例（药丸描述）：`Sprite:SetFrame` 两个重载都必须用共享判据。"""
        sprite = (LUA_API_DIR / "sprite_api.cpp").read_text(encoding="utf-8")
        self.assertIn("IsaacIntegerArgument".replace("Isaac", "isaac::runtime::"), sprite)
        self.assertEqual(re.findall(r"IntegerArgumentAt\(state, [23], &frameNumber\)", sprite).__len__(),
                         2, "`Sprite:SetFrame` 的两个重载都要用共享判据")


if __name__ == "__main__":
    unittest.main()
