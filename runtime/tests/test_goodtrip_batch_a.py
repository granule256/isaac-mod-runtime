"""门禁：批次 041（为 GoodTrip 补的四条）不许悄悄退化。

## 为什么要有它

GoodTrip（[Fixed] 2.2.56）真机一跑就会调用这四条；它们的**失败形态各不相同**，而每一种都很隐蔽：

* `Isaac.GetRoomEntities()` —— **真实现**（PC 侧这一条本身就是 Lua glue）。缺它时
  `scripts/trip.lua:38` 直接索引 nil ⇒ **传送功能整块不工作**（连"把跟班一起带走"都做不到）；
* `Input.GetMousePosition(boolean)` —— **平台降级**（Switch 没有鼠标指针）：必须
  **恒返回一个 Vector 且绝不抛错**。GoodTrip 在 `scripts/control.lua:190` **每帧**调它，
  一旦抛错，派发器会把整条回调静默摘掉（现象是"模组像没装"）；
* `Input.IsMouseBtnPressed(Mouse)` —— **平台降级**：恒 false（= "鼠标没点"）；
* `Isaac.ExecuteCommand(string)` —— **平台降级**：Switch 没有控制台 ⇒ 什么都不做，
  但**形状要与 PC 一致**（PC 返回 void）。后果是 GoodTrip 的 `TAB + R` 快速重开不生效 ——
  这一条必须写在实现注释里，否则下一轮会有人把它当成"模组 bug"。

所以这里钉四件事：**目录行在**、**绑定在**、**降级/改写的处理器必须写明"性质"与后果**
（平台降级写「平台限制」，已改写成触摸屏的写「触摸屏」）、
以及 `GetRoomEntities` **必须是真实现**（不许变成 `PushZero` 那种假读数）。
"""

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LUA_API = ROOT / "runtime" / "src" / "interfaces" / "lua"
CATALOG = LUA_API / "api_catalog.cpp"
ISAAC_API = LUA_API / "isaac_api.cpp"
INPUT_API = LUA_API / "input_api.cpp"

#: (源文件, 处理器名, 绑定 id, 目录里的 MakeId 片段, 是否平台降级)
#: 绑定 id 是 `域号<<24 | 1<<16 | 序号`，而目录行写的是 `MakeId(ApiDomain::X, 1, 0x序号)`
#: —— 两种写法都要核（绑定对不上目录会让门禁在别处以"幽灵条目"的形式报出来）。
EXPECTED = (
    (ISAAC_API, "IsaacGetRoomEntities", "0x0E01002C", "ApiDomain::Isaac, 1, 0x002C", False),
    (ISAAC_API, "IsaacExecuteCommand", "0x0E01002D", "ApiDomain::Isaac, 1, 0x002D", True),
    (INPUT_API, "InputGetMousePosition", "0x09010007", "ApiDomain::Input, 1, 0x0007", True),
    (INPUT_API, "InputIsMouseBtnPressed", "0x09010008", "ApiDomain::Input, 1, 0x0008", True),
)


def definition_of(text: str, name: str) -> int:
    """返回处理器**定义**的起点。

    必须带 ` {` 去找：同名的**前置声明**（`int X(lua_State* state);`）就写在同一文件靠前的位置，
    只按名字找会命中声明 ⇒ 后续断言全落在那几行声明上（本次第一版就是这么错的）。
    """
    return text.index("int " + name + "(lua_State* state) {")


def body_of(text: str, name: str) -> str:
    """取一个处理器的函数体（到下一个顶层 `}` 行为止）。"""
    start = definition_of(text, name)
    end = text.index("\n}\n", start)
    return text[start:end]


def block_with_leading_comment(text: str, name: str) -> str:
    """函数体 + 它**正上方那一段注释**（平台限制的判据写在注释里）。"""
    definition = definition_of(text, name)
    head = text.rindex("\n\n", 0, definition)
    return text[head:definition] + body_of(text, name)


class GoodTripBatchATests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = CATALOG.read_text(encoding="utf-8")
        cls.sources = {path: path.read_text(encoding="utf-8") for path in (ISAAC_API, INPUT_API)}

    def test_catalog_has_every_entry(self) -> None:
        for _, _, _, fragment, _ in EXPECTED:
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, self.catalog)

    def test_every_handler_is_bound(self) -> None:
        for path, name, identifier, _, _ in EXPECTED:
            with self.subTest(handler=name):
                self.assertIn("{" + identifier + ", &" + name + "}", self.sources[path],
                              name + " 没有登记进绑定表（登记了才会出现在对象上）")

    def test_platform_limits_say_so(self) -> None:
        """降级/改写的处理器必须写明**性质**与后果（否则下一个人会当成功能 bug）。

        ★ 2026-09-28 批次 192：`Input` 那两条已**不是**平台降级（指针源改成触摸屏），
        所以它们不再要求出现「平台限制」——改成要求写明「触摸屏」。
        本条的用意（"注释必须交代性质，别让人误判成 bug"）**没有放宽**：两条路径各自都要留话。
        """
        for path, name, _, _, degraded in EXPECTED:
            if not degraded:
                continue
            with self.subTest(handler=name):
                block = block_with_leading_comment(self.sources[path], name)
                if name.startswith("Input"):
                    # 批次 192：已改写成触摸屏 ⇒ 必须写明这件事（含"为什么改了"）。
                    self.assertIn("触摸屏", block)
                else:
                    self.assertIn("平台限制", block)

    def test_execute_command_documents_the_fast_restart_consequence(self) -> None:
        block = block_with_leading_comment(self.sources[ISAAC_API], "IsaacExecuteCommand")
        self.assertIn("restart", block.lower())
        self.assertIn("不会重开", block)

    def test_get_room_entities_is_a_real_implementation(self) -> None:
        """它必须真的遍历房间（用到三段来源），**不是** `PushZero` 那种假读数。"""
        body = body_of(self.sources[ISAAC_API], "IsaacGetRoomEntities")
        self.assertIn("ResolveRoom()", body)
        self.assertIn("ForEachEntityInTable", body)
        self.assertIn("PushQueryResult", body)
        self.assertNotIn("PushZero", body)
        # 声明为无参数：PC 的签名就是 `GetRoomEntities()`。
        self.assertIn("accepts no arguments", body)

    def test_mouse_handlers_never_raise_on_the_hot_path(self) -> None:
        """`Input.GetMousePosition` 每帧都被调用 ⇒ 只允许「参数个数不对」这一条抛错路径。

        ★ 2026-09-28 批次 192 改判据（**行为按用户指令变了，不是"改测试让它过"**）：
        本条原先钉的是 `PushLuaVector(state, 0.0F, 0.0F)` —— 即"恒 (0,0) 的平台降级"。
        用户 2026-09-28 指定「把 PC 的鼠标操作映射成 NS 的触屏操作」并选定"先接线不做换算"
        ⇒ 指针源改成触摸屏，**恒值那一半的断言必须撤掉**（留着它就是把修好的行为再钉死一次，
        批次 128 在 `GetMainTwin` 上正是这么栽的）。**不抛错那一半照旧钉着**，它才是本条的用意。
        """
        body = body_of(self.sources[INPUT_API], "InputGetMousePosition")
        self.assertIn("ReadTouchPointer()", body)
        self.assertNotIn("0.0F, 0.0F", body)
        self.assertEqual(body.count("luaL_error"), 1)

    def test_is_mouse_btn_pressed_reads_the_touch_screen_and_checks_arguments(self) -> None:
        """★ 2026-09-28 批次 192 改判据（同上：行为按用户指令变了）。

        语义由用户定为「手指在屏幕上 = 左键按下」⇒ 不能再钉"恒 false"；
        参数形状校验与"不抛错"照旧 —— 它被每帧的鼠标状态跟踪调用。
        """
        body = body_of(self.sources[INPUT_API], "InputIsMouseBtnPressed")
        self.assertIn("CheckMouseButtonArguments", body)
        self.assertIn("ReadTouchPointer()", body)
        self.assertIn("touch.pressed", body)
        # 不许再有"恒假"那种写死的返回值。
        self.assertNotIn("lua_pushboolean(state, 0)", body)


if __name__ == "__main__":
    unittest.main()
