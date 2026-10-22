"""门禁：`Room` 三个**返回 `Vector`** 的方法（批次 247，2026-10-01）。

## 为什么它们与别的 API 不同

`Room:GetCenterPos()` / `GetGridPosition(int)` / `GetRandomPosition(float)` 在待办清单里是
`needs_struct_return` 一类。既有的"引擎方法数据行"机制（16 字节/行、0 代码）**走不通**，
因为它的跳板只支持标量返回，而这三条返回 `Vector2`。

⇒ 它们是**手写处理器**（`remaining_api.cpp`），与 `RoomGetDoorSlotPosition` 同一条路。

★★ 顺带纠正清单里的一条**错判**：清单说这三条返回"16 字节值类型、走 x8 间接结果寄存器"。
反汇编 `Room::GetGridPosition(int) @ 0x454D38` 看到的却是

```
add  x0, sp, #0x8          ; 栈上构造 Vector2
bl   KAGE::Math::Vector2::Vector2(float, float)
ldp  s0, s1, [sp, #0x8]    ; 读进 s0 / s1
ret                        ; ⇒ 8 字节、走两个 SIMD 寄存器
```

⇒ `Vector2` 是 **8 字节**（两个 float），于是"声明一个两个 float 的结构体按值返回"就够了，
**不必扩跳板**。本文件把这条证据钉住，免得以后有人按清单的错判去改。

## 本文件钉什么、不钉什么

钉**接线**：目录行、绑定行、常量、手写处理器、失败降级口径。
★ **不钉值**：宿主 harness 的引擎调用跳板**把返回值一律清零**
（`engine_call_trampoline_host_stub.cpp`）⇒ 任何宿主测试都**证明不了** `GetCenterPos()`
真的返回了房间中心。那条只能真机验（成熟度因此仍是 `Experimental`）。
"""

import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
CATALOG = ROOT / "runtime" / "src" / "interfaces" / "lua" / "api_catalog.cpp"
ROOM_API = ROOT / "runtime" / "src" / "interfaces" / "lua" / "remaining_api.cpp"
CONSTANTS = ROOT / "runtime" / "source" / "runtime_constants.hpp"

#: `(名字, 域内序号, 引擎偏移, 入口首字)`
METHODS = (
    ("GetCenterPos", 0x001B, 0x456250, 0xD100C3FF),
    ("GetGridPosition", 0x001C, 0x454D38, 0xD10083FF),
    ("GetRandomPosition", 0x001D, 0x456110, 0xD10183FF),
)


class RoomVectorMethodTests(unittest.TestCase):
    def test_catalog_rows_exist(self):
        source = CATALOG.read_text(encoding="utf-8")
        for name, index, _offset, _word in METHODS:
            with self.subTest(name):
                self.assertIn(
                    f'MakeId(ApiDomain::Room, 1, 0x{index:04X}), ApiDomain::Room, "Room", "{name}"',
                    source, f"catalog 里没有 Room:{name}（域内序号 0x{index:04x}）")

    def test_binding_rows_exist(self):
        source = ROOM_API.read_text(encoding="utf-8")
        for name, index, _offset, _word in METHODS:
            with self.subTest(name):
                self.assertRegex(
                    source, rf"\{{\s*(?i:0x{0x04010000 + index:08x}),\s*&Room{name}\s*\}}",
                    f"绑定表里没有 0x{0x04010000 + index:08X} → Room{name}")

    def test_engine_constants_carry_offset_and_entry_word(self):
        source = CONSTANTS.read_text(encoding="utf-8")
        for name, _index, offset, word in METHODS:
            with self.subTest(name):
                self.assertIn(f"kRoom{name}Offset = 0x{offset:X}", source,
                              f"缺 kRoom{name}Offset = {offset:#x}")
                self.assertIn(f"kRoom{name}EntryWord = 0x{word:08X}U", source,
                              f"缺 kRoom{name}EntryWord = {word:#010x}")

    def test_handlers_are_hand_written_not_data_rows(self):
        """三条必须**没有**出现在任何 `EngineMethodRow` 数组里（它们是手写的）。"""
        source = ROOM_API.read_text(encoding="utf-8")
        # 定义体存在（形如 `int RoomGetCenterPos(lua_State* state) {`）
        for name, _index, _offset, _word in METHODS:
            with self.subTest(name):
                self.assertRegex(source, rf"\nint Room{name}\(lua_State\* state\) \{{",
                                 f"没有 Room{name} 的处理器定义体")
        # 数据行数组里不许出现它们的常量（否则会被跳板当成标量返回处理）
        rows = source[source.index("constexpr EngineMethodRow kRoomEngineRows[]"):
                      source.index("constexpr EngineMethodRow kRoomEngineRows[]") + 6000]
        for name, _index, _offset, _word in METHODS:
            with self.subTest(name):
                self.assertNotIn(f"kRoom{name}Offset", rows,
                                 f"{name} 出现在数据行数组里 —— 它必须走手写路径（返回 Vector）")

    def test_failure_degrades_to_zero_vector_not_nil(self):
        """拿不到房间/入口不匹配时压 `Vector(0,0)`、**不报错**。

        理由是 `EngineMethodHandler` 的头注口径（返回标量就压 0）；压 `nil` 会让模组立刻
        `pos.X` ⇒ "attempt to index a nil value" ⇒ 整条回调被摘掉，比"坐标是 0"严重得多。
        """
        source = ROOM_API.read_text(encoding="utf-8")
        self.assertIn("PushZeroRoomVector", source, "缺失败降级助手")
        self.assertRegex(source, r"PushLuaVector\(state, 0\.0F, 0\.0F\)",
                         "降级必须压 Vector(0,0)")
        for name, _index, _offset, _word in METHODS:
            handler = re.search(rf"\nint Room{name}\(lua_State\* state\) \{{(.*?)\n\}}",
                                source, re.S)
            self.assertIsNotNone(handler, f"找不到 Room{name} 的处理器体")
            body = handler.group(1)
            self.assertIn("PushZeroRoomVector(state)", body,
                          f"{name} 的失败路径必须调 PushZeroRoomVector")
            self.assertNotIn("lua_pushnil", body,
                             f"{name} 的失败路径**不许**压 nil（见本文件文档头）")

    def test_sources_admit_that_values_are_not_host_verified(self):
        """实现处必须写明"值只能真机验"，免得有人把宿主绿灯当成"值对"。"""
        combined = ROOM_API.read_text(encoding="utf-8") + CONSTANTS.read_text(encoding="utf-8")
        self.assertIn("s0", combined, "取证里必须留下 s0/s1 返回约定这条")
        self.assertIn("ldp s0, s1", combined,
                      "取证里必须留下 `ldp s0, s1, [sp, #0x8]` 这条指令证据")


if __name__ == "__main__":
    unittest.main()
