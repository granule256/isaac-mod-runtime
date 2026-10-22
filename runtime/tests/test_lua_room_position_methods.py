"""门禁：`Room` 四条**位置类**方法（批次 259，2026-10-01）。

## 这四条为什么要手写

`Room:FindFreePickupSpawnPosition(Vector,…)` / `Room:GetClampedPosition(Vector,float)` /
`Room:FindFreeTilePosition(Vector,float)` / `Room:GetDoorSlotPosition(DoorSlot)` 在待办清单里
归在 `needs_new_shape`（"参数里有向量/枚举 ⇒ 要先扩一种形状能力"）。

逐条核对 **mangled 签名**之后结论与批次 253 相同：**不需要扩任何能力** —— 它们的 `Vector`
参数是 **`Vector2 const&`（引用 ⇒ ABI 上就是一个指针参数）**：

```
_ZNK15IsaacRepentance4Room27FindFreePickupSpawnPositionERKN4KAGE4Math7Vector2Efbb
                                                        ^^^^ const 引用
_ZNK15IsaacRepentance4Room18GetClampedPositionERKN4KAGE4Math7Vector2Effff
_ZNK15IsaacRepentance4Room20FindFreeTilePositionERKN4KAGE4Math7Vector2Ef
_ZNK15IsaacRepentance4Room19GetDoorSlotPositionENS_9eDoorSlotE      (只有枚举参数)
```

仍然走**手写处理器**的唯一原因是**返回 `Vector2`**：通用跳板只支持标量返回
（`engine_call_trampoline.hpp` 写明的能力边界），而 `Vector2` 在 AAPCS64 上走 `s0`/`s1` ——
声明"两个 float 的结构体按值返回"就对得上（与批次 249 的三条、与 `CallRoomDoorSlotPosition`
同一条路）。本文件把那几条反汇编证据钉住，免得以后有人按清单的错判去改跳板。

## 本文件钉什么、不钉什么

钉**接线**：目录行、绑定行、常量（偏移 + 入口首字）、手写处理器的存在与"不在数据行数组里"、
失败降级口径（压 `Vector(0,0)`、**不压 nil**）、以及契约原文里的**缺省值**（它们决定了
`FindFreePickupSpawnPosition` 的 1 个参数为什么必须能过）。

★ **不钉值**：宿主上没有引擎（跳板桩把返回值一律清零、手写路径根本不会跳到引擎）
⇒ 任何宿主测试都**证明不了** `FindFreePickupSpawnPosition` 真的返回了合法落点。
那条只能真机验（成熟度因此是 `Experimental`）。
"""

import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
CATALOG = ROOT / "runtime" / "src" / "interfaces" / "lua" / "api_catalog.cpp"
ROOM_API = ROOT / "runtime" / "src" / "interfaces" / "lua" / "remaining_api.cpp"
CONSTANTS = ROOT / "runtime" / "source" / "runtime_constants.hpp"

#: `(名字, 域内序号, 引擎偏移, 入口首字, 契约页:行)`
METHODS = (
    ("FindFreePickupSpawnPosition", 0x0020, 0x455BFC, 0xD10303FF, "Room.md:78"),
    ("GetClampedPosition", 0x0021, 0x4842A0, 0xD10243FF, "Room.md:152"),
    ("FindFreeTilePosition", 0x0022, 0x488050, 0xD10203FF, "Room.md:83"),
    ("GetDoorSlotPosition", 0x0023, 0x464B8C, 0xD10083FF, "Room.md:291"),
)


class RoomPositionMethodTests(unittest.TestCase):
    def test_catalog_rows_exist(self):
        source = CATALOG.read_text(encoding="utf-8")
        for name, index, _offset, _word, _page in METHODS:
            with self.subTest(name):
                self.assertIn(
                    f'MakeId(ApiDomain::Room, 1, 0x{index:04X}), ApiDomain::Room, "Room", "{name}"',
                    source, f"catalog 里没有 Room:{name}（域内序号 0x{index:04x}）")

    def test_binding_rows_exist(self):
        source = ROOM_API.read_text(encoding="utf-8")
        for name, index, _offset, _word, _page in METHODS:
            with self.subTest(name):
                self.assertRegex(
                    source, rf"\{{\s*(?i:0x{0x04010000 + index:08x}),\s*&Room{name}\s*\}}",
                    f"绑定表里没有 0x{0x04010000 + index:08X} → Room{name}")

    def test_engine_constants_carry_offset_and_entry_word(self):
        source = CONSTANTS.read_text(encoding="utf-8")
        for name, _index, offset, word, _page in METHODS:
            with self.subTest(name):
                self.assertIn(f"kRoom{name}Offset = 0x{offset:X}", source,
                              f"缺 kRoom{name}Offset = {offset:#x}")
                # 后缀大小写不钉（`GetDoorSlotPosition` 那条是批次 249 写的 `…FFu`）。
                self.assertIn(f"kRoom{name}EntryWord = 0x{word:08X}", source,
                              f"缺 kRoom{name}EntryWord = {word:#010x}")

    def test_handlers_are_hand_written_not_data_rows(self):
        """四条必须**没有**出现在 `kRoomEngineRows` 里（它们是手写的）。"""
        source = ROOM_API.read_text(encoding="utf-8")
        for name, _index, _offset, _word, _page in METHODS:
            with self.subTest(name):
                self.assertRegex(source, rf"\nint Room{name}\(lua_State\* state\) \{{",
                                 f"没有 Room{name} 的处理器定义体")
        rows = source[source.index("constexpr EngineMethodRow kRoomEngineRows[]"):
                      source.index("constexpr EngineMethodRow kRoomEngineRows[]") + 6000]
        for name, _index, _offset, _word, _page in METHODS:
            with self.subTest(name):
                self.assertNotIn(f"kRoom{name}Offset", rows,
                                 f"{name} 出现在数据行数组里 —— 它必须走手写路径（返回 Vector）")

    def test_contract_page_and_line_are_quoted_in_the_implementation(self):
        """实现处必须留下 `Room.md:<行>`（G2 闸门：写不出页:行号就先别写代码）。"""
        source = ROOM_API.read_text(encoding="utf-8")
        for name, _index, _offset, _word, page in METHODS:
            with self.subTest(name):
                self.assertIn(page, source, f"{name} 的实现处没有引用契约 {page}")

    def test_optional_tail_arguments_follow_the_contract_defaults(self):
        """`FindFreePickupSpawnPosition` 的 1 个参数必须能过（语料里有 1 个参数的调用）。

        契约（`Room.md:78`）写明了三个尾部缺省值 `InitialStep = 0` / `AvoidActiveEntities = false`
        / `AllowPits = false`，所以省略时必须**按这些值填**，而不是当成"参数不够、报错"。
        """
        source = ROOM_API.read_text(encoding="utf-8")
        self.assertIn("InitialStep = 0", source, "实现处必须留下 InitialStep 的缺省值")
        self.assertIn("AvoidActiveEntities = false", source, "实现处必须留下 AvoidActiveEntities 的缺省值")
        self.assertIn("AllowPits = false", source, "实现处必须留下 AllowPits 的缺省值")
        handler = re.search(r"\nint RoomFindFreePickupSpawnPosition\(lua_State\* state\) \{(.*?)\n\}",
                            source, re.S)
        self.assertIsNotNone(handler, "找不到 RoomFindFreePickupSpawnPosition 的处理器体")
        body = handler.group(1)
        self.assertIn("arguments < 1 || arguments > 4", body,
                      "必须显式接受 1..4 个参数（尾部可省）")

    def test_failure_degrades_to_zero_vector_not_nil(self):
        """拿不到房间/入口不匹配时压 `Vector(0,0)`、**不报错**。

        口径与批次 249 相同（`EngineMethodHandler` 头注）：压 `nil` 会让模组立刻 `pos.X`
        ⇒ "attempt to index a nil value" ⇒ 整条回调被摘掉，比"坐标是 0"严重得多。
        `GetDoorSlotPosition` 的零向量还**正好等于 PC 语义**（槽位越界时引擎返回 `Vector2::Zero`）。
        """
        source = ROOM_API.read_text(encoding="utf-8")
        self.assertRegex(source, r"PushLuaVector\(state, 0\.0F, 0\.0F\)", "降级必须压 Vector(0,0)")
        for name, _index, _offset, _word, _page in METHODS:
            with self.subTest(name):
                handler = re.search(rf"\nint Room{name}\(lua_State\* state\) \{{(.*?)\n\}}",
                                    source, re.S)
                self.assertIsNotNone(handler, f"找不到 Room{name} 的处理器体")
                body = handler.group(1)
                self.assertIn("PushZeroRoomVector(state)", body,
                              f"{name} 的失败路径必须调 PushZeroRoomVector")
                self.assertNotIn("lua_pushnil", body,
                                 f"{name} 的失败路径**不许**压 nil（见本文件文档头）")

    def test_vector_argument_is_read_from_a_vector_handle_only(self):
        """`Pos` 必须只接受 `Vector` 句柄 —— 传别的类型要让这次调用**报错**。

        把一个别的指针当 `Vector2 const&` 交出去，引擎会照读那块内存当坐标，**不报错**
        （静默的错坐标）⇒ 比"这次降级"严重得多，所以在解析阶段就挡掉。
        """
        source = ROOM_API.read_text(encoding="utf-8")
        self.assertIn("ReadRoomVectorArgument", source, "缺 Vector 实参解析助手")
        self.assertIn("LuaRuntime::kVectorMetatable", source, "解析必须走 Vector 的元表判据")

    def test_sources_admit_that_values_are_not_host_verified(self):
        """实现处必须写明"返回约定是 `s0`/`s1`"这条证据，免得有人按 x8 的错判去扩跳板。"""
        combined = ROOM_API.read_text(encoding="utf-8") + CONSTANTS.read_text(encoding="utf-8")
        self.assertIn("ldp s0, s1", combined, "取证里必须留下 `ldp s0, s1` 这条指令证据")
        self.assertIn("mov v0.16b, v8.16b", combined, "取证里必须留下 `mov v0.16b, v8.16b` 这条证据")


if __name__ == "__main__":
    unittest.main()
