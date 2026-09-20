"""门禁：跳进游戏模块的那些入口，**声明的签名只能有一份**，而且调用点用的就是那一份。

## 为什么要有它（2026-09-17）

这些入口是"我们手写签名、直接跳进游戏模块"的地方 —— 签名写错就是崩游戏。改动之前，
同一份签名在仓库里有**两份互不相干的副本**：

1. 绑定记录（`LuaFontBindings` / `LuaSpriteBindings`）的字段，类型写成 `uintptr_t`
   —— 谁都看不出它期望什么参数；
2. 每个调用点自己写一份 `using PlayFn = void (*)(void*, const char*, bool);`，
   再用 `reinterpret_cast<PlayFn>(地址)(…)` 调。

两份一旦漂移，没有任何东西会发现；而"ABI 体检"（`tools/engine_offset_abi_report.py`）
也因此读不到这 36 条中的绝大多数 —— 覆盖率长期停在 16/91，那句"参数个数不符 0"
对它们其实是"没比过"。

现在只有一份：`runtime/source/lua_runtime_state.hpp` 里的 `using XxxFn = …`；
绑定记录字段用它、取址助手（`XxxThunk`）返回它、调用点直接调用它（`reinterpret_cast` 消失，
参数由编译器核对）。本门禁钉住这四件事：

* **记录字段必须是那个类型名**（不许退回 `uintptr_t`）；
* **绑定表的每一行都能被体检工具读出类型**（字段名把偏移常量与类型连起来）；
* **被记录声明的那些入口，体检工具必须真的比过**（覆盖率不许悄悄掉回去）；
* **调用点不许再自己抄一份**（不许出现"函数指针类型的本地 `using`"或
  `reinterpret_cast<…Fn>`），并且"哪个 TU 调了这个入口，那个 TU 就必须提到这个类型名"
  —— 这条是"声明的就是调用的"的直接判据。
"""

import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STATE_HPP = ROOT / "runtime" / "source" / "lua_runtime_state.hpp"
RUNTIME_HPP = ROOT / "runtime" / "source" / "lua_runtime.hpp"
RUNTIME_CPP = ROOT / "runtime" / "source" / "lua_runtime.cpp"
HOOK_MANAGER = ROOT / "runtime" / "source" / "hook_manager.cpp"
TABLE = ROOT / "tools" / "engine_symbol_signatures.json"
TOOL = ROOT / "tools" / "engine_offset_abi_report.py"
#: 调用这些入口的翻译单元（目前是 Font 与 Sprite 两族）。
CONSUMERS = [
    ROOT / "runtime" / "src" / "interfaces" / "lua" / "font_api.cpp",
    ROOT / "runtime" / "src" / "interfaces" / "lua" / "sprite_api.cpp",
]
RECORDS = ["LuaFontBindings", "LuaSpriteBindings"]
BINDING_ROW_RE = re.compile(
    r"\{\s*(k[A-Za-z0-9]+Offset)\s*,\s*offsetof\(\s*LuaRuntime::(\w+)\s*,\s*(\w+)\s*\)")


def load_tool_module():
    import importlib.util

    spec = importlib.util.spec_from_file_location("abi_report", TOOL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def declared_aliases() -> dict[str, str]:
    """`lua_runtime_state.hpp` 里声明的引擎入口类型：别名 → 类型文本。"""
    text = STATE_HPP.read_text(encoding="utf-8")
    return dict(re.findall(r"using (\w+Fn) = ([^;]+);", text))


def record_fields() -> list[tuple[str, str, str]]:
    """两个绑定记录的字段：(记录名, 字段名, 声明类型)。"""
    text = RUNTIME_HPP.read_text(encoding="utf-8")
    out: list[tuple[str, str, str]] = []
    for record in RECORDS:
        match = re.search(r"struct\s+" + record + r"\s*\{(.*?)\n\};", text, re.S)
        assert match is not None, f"找不到 {record} 的定义（结构体被改名了？）"
        body = re.sub(r"//[^\n]*", "", match.group(1))
        for declared_type, field in re.findall(r"([A-Za-z_]\w*)\s+(\w+)\{nullptr\}", body):
            out.append((record, field, declared_type))
    return out


def binding_rows() -> list[tuple[str, str, str]]:
    """`hook_manager.cpp` 里"偏移常量 ↔ 记录字段"的行：(常量, 记录名, 字段名)。"""
    text = HOOK_MANAGER.read_text(encoding="utf-8")
    return BINDING_ROW_RE.findall(text)


class BindingDeclaredTypeTests(unittest.TestCase):
    def test_records_use_named_function_pointer_types(self):
        """绑定记录字段的类型必须是**声明过的函数指针别名**，不是 `uintptr_t`。"""
        aliases = declared_aliases()
        self.assertGreaterEqual(len(aliases), 36, "引擎入口类型的声明数掉了（被删了？）")
        fields = record_fields()
        self.assertEqual(len(fields), 36, f"两个绑定记录的字段数变成 {len(fields)} 个（应为 36）")
        for record, field, declared_type in fields:
            with self.subTest(record=record, field=field):
                self.assertIn(
                    declared_type, aliases,
                    f"{record}::{field} 的类型 {declared_type} 不是声明过的引擎入口类型 —— "
                    "退回 `uintptr_t` 就等于把「我们期望什么参数」这件事删掉了",
                )

    def test_binding_rows_expose_a_declared_type(self):
        """绑定表每一行都必须能被读出字段的声明类型（体检工具走的就是这条）。"""
        module = load_tool_module()
        rows = binding_rows()
        self.assertGreaterEqual(len(rows), 36, f"绑定表只剩 {len(rows)} 行（应为 36）")
        for constant, record, field in rows:
            with self.subTest(constant=constant):
                type_text = module.member_declared_type(record, field)
                self.assertIsNotNone(type_text, f"{record}::{field} 读不到声明类型")
                params = module.parameters_of_function_pointer(type_text)
                self.assertIsNotNone(
                    params,
                    f"{record}::{field} 的声明类型 {type_text} 不是函数指针 —— 体检工具比不了参数表",
                )

    def test_every_declared_binding_is_compared_by_the_report(self):
        """被声明的那 36 条里，体检工具**真的比过**的那些不许掉回去。"""
        module = load_tool_module()
        registered = {entry["constant"] for entry in json.loads(TABLE.read_text(encoding="utf-8"))}
        rows = [row for row in binding_rows() if row[0] in registered]
        self.assertGreaterEqual(len(rows), 34, f"能体检的绑定只剩 {len(rows)} 条")
        for constant, _record, _field in rows:
            with self.subTest(constant=constant):
                signature = module.declared_signature(constant)
                self.assertIsNotNone(
                    signature,
                    f"{constant} 读不出我们声明的参数表：绑定记录那条路又断了（覆盖率会悄悄掉）",
                )

    def test_consumers_use_the_declared_type(self):
        """调用点不许再抄一份：不许有函数指针类型的本地 `using`、不许 `reinterpret_cast<…Fn>`。"""
        for path in CONSUMERS:
            text = path.read_text(encoding="utf-8")
            with self.subTest(file=path.name):
                raw_alias = re.findall(r"using (\w+) = [^;]*\(\s*\*\s*\)\s*\([^;]*;", text)
                self.assertEqual(
                    raw_alias, [],
                    f"{path.name} 又出现了自己抄的函数指针别名 {raw_alias} —— "
                    f"应当直接用 `LuaRuntime::XxxFn`（声明只允许有一份）",
                )
                casts = re.findall(r"reinterpret_cast<\s*(\w*Fn)\s*>", text)
                self.assertEqual(
                    casts, [],
                    f"{path.name} 又把带类型的入口转型了一次 {casts} —— 直接调用即可，"
                    f"转型会把编译器的参数核对绕过去",
                )

    def test_each_consumer_uses_the_type_it_calls(self):
        """取址助手（`XxxThunk()`）的结果必须**立刻声明成共享类型**，而不是 `uintptr_t` 再转型。

        判据取"所在的那条语句里必须出现某个 `LuaRuntime::…Fn` 类型名"：直接把结果交给类型化的
        局部变量 ⇒ 语句里有类型名；若退回"先收成 `uintptr_t`、调用时再 `reinterpret_cast`"，
        语句里就只有 `uintptr_t`，本条判红。四个绘制变体是"按分支选一个"的写法，同样满足
        （缩放分支声明成 `FontDrawStringScaledFn`、非缩放分支声明成 `FontDrawStringFn`）。
        """
        thunk_call = re.compile(r"LuaRuntime::(\w+)Thunk\(\)")
        for path in CONSUMERS:
            text = path.read_text(encoding="utf-8")
            for match in thunk_call.finditer(text):
                statement_start = max(text.rfind(";", 0, match.start()),
                                      text.rfind("{", 0, match.start())) + 1
                statement = text[statement_start : match.end()]
                with self.subTest(file=path.name, thunk=match.group(1)):
                    self.assertRegex(
                        statement,
                        r"LuaRuntime::\w+Fn\b",
                        f"{path.name} 里 `{match.group(1)}Thunk()` 的结果没有声明成共享类型：\n"
                        f"    {statement.strip()}",
                    )

    def test_binding_setters_convert_at_the_storage_boundary(self):
        """记录字段进原子槽时必须在**存储边界**显式转换（字段类型不再等于槽的类型）。"""
        text = RUNTIME_CPP.read_text(encoding="utf-8")
        for _record, field, _type in record_fields():
            with self.subTest(field=field):
                self.assertIn(
                    f"reinterpret_cast<std::uintptr_t>(bindings.{field})", text,
                    f"`bindings.{field}` 没有以 `reinterpret_cast<std::uintptr_t>(…)` 的形式发布"
                    f" —— 发布点被改写了（原子槽存的是地址，不是类型）",
                )


if __name__ == "__main__":
    unittest.main()
