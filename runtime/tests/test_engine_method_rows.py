"""门禁：**引擎方法数据行**机制（`runtime/src/interfaces/lua/engine_method_api.hpp`）。

## 为什么有这条门禁（2026-09-19 批次 051）

一条"调引擎方法"的 API 原来要手写 ≈490 字节代码（入口守卫 224 + handler ~200），
而代码段当时只有 512 KiB、保留线 32 KiB ⇒ 2026-09-19 真的撞上了：**一口气补 8 条，构建直接失败**。
（当天晚些时候闸门按"失控增长闸门"的规则抬到 1 MiB / 2 MiB，见 `runtime/misc/link.ld` 的注释；
但"每条 API 花 490 字节代码"这个成本模型本身才是要治的东西。）

改成数据行之后，每个 API 只花 **16 字节只读数据、0 字节代码**（共享处理器一份）。
这条门禁守住这个**不变式** —— 否则不知不觉就会有人"顺手再写个处理器"，机制形同虚设：

1. 行里的 id 必须能在 `api_catalog.cpp` 里找到，**且 owner 对得上**；
2. 行的 `shape` 与 `argumentCount` 必须自洽（`VoidN` 就要 N 个整数参数）；
3. 行的两个常量（偏移 + 入口指纹）必须都在 `runtime_constants.hpp` 里，
   **且都登记进了 `tools/engine_symbol_signatures.json`**（否则 ABI 体检看不见它）；
4. **行里的 id 不许再出现在任何手写绑定表**（`{0x…, &Handler}` 那种）——
   那意味着这个 API 又占上了代码段，机制白做；
5. 行数写死（增删都要有人来解释）；
6. 行必须正好 16 字节（结构体里那条 `static_assert` 是成本前提）。
"""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "runtime" / "source"
LUA_DIR = ROOT / "runtime" / "src" / "interfaces" / "lua"
CATALOG = LUA_DIR / "api_catalog.cpp"
CONSTANTS = SOURCE / "runtime_constants.hpp"
SIGNATURES = ROOT / "tools" / "engine_symbol_signatures.json"
BINDING = LUA_DIR / "owner_binding.cpp"
ROWS_HEADER = LUA_DIR / "engine_method_api.hpp"

#: 承载数据行的家族 TU（加新的就在这张表里登记）。
ROW_FILES = (LUA_DIR / "isaac_api.cpp", LUA_DIR / "game_api.cpp", LUA_DIR / "remaining_api.cpp")

#: 行总数（**增删都要在这里解释**）。2026-09-19 批次 051 首批：5（EntityPlayer）+ 1（Game）
#: + 2（Level）+ 1（Room）= 9；批次 055 加 1 行：`Game:StartRoomTransition`（GoodTrip 传送的
#: 默认路径）⇒ 10；批次 063 再加 1 行：`Entity:IsFlying()`（GoodTrip 的诅咒房判定，
#: 缺它时刺房传送报 "attempt to call a nil value (method 'IsFlying')"）⇒ 11。
EXPECTED_ROW_TOTAL = 11


def shape_arity_table() -> dict[str, int]:
    """`shape` → 该形状要求几个参数。

    **从签名描述符表派生，不再写死**（批次 055 起形状本身是数据）：枚举名与下标的对应关系
    读 `engine_method_api.hpp` 的 `EngineCallShape`，每个形状的参数个数读
    `isaac_api.cpp` 里 `kEngineCallShapes` 的行（每行第一个字段就是参数个数）。
    这样"加一种形状"只要改那两处，门禁自动跟上，不会再出现"门禁与实现说法不一致"。
    """
    header = ROWS_HEADER.read_text(encoding="utf-8")
    enum_block = re.search(
        r"enum class EngineCallShape[^{]*\{(.*?)\n\};", header, re.S)
    if enum_block is None:
        raise AssertionError("engine_method_api.hpp 里找不到 EngineCallShape 枚举")
    names = {}
    for name, index in re.findall(r"(\w+)\s*=\s*(\d+)", enum_block.group(1)):
        names[int(index)] = name

    table = (LUA_DIR / "isaac_api.cpp").read_text(encoding="utf-8")
    table_block = re.search(r"kEngineCallShapes\[\]\s*=\s*\{(.*?)\n\};", table, re.S)
    if table_block is None:
        raise AssertionError("isaac_api.cpp 里找不到 kEngineCallShapes 签名描述符表")
    counts = [int(value) for value in
              re.findall(r"^\s*\{(\d+),\s*\{EngineArgKind::", table_block.group(1), re.M)]

    if len(counts) != len(names):
        raise AssertionError(
            f"签名描述符表有 {len(counts)} 行、枚举有 {len(names)} 个值 —— 两者必须一一对应")
    return {names[index]: counts[index] for index in sorted(names)}

ROW_RE = re.compile(
    r"\{\s*0x([0-9A-Fa-f]{8})\s*,\s*(k\w+Offset)\s*,\s*(k\w+EntryWord)\s*,\s*"
    r"FieldReceipt::(\w+)\s*,\s*EngineCallShape::(\w+)\s*,\s*(\d+)\s*,")


def parse_rows() -> list[dict]:
    rows = []
    for path in ROW_FILES:
        text = path.read_text(encoding="utf-8")
        for match in ROW_RE.finditer(text):
            rows.append({
                "file": path.name,
                "id": "0x" + match.group(1).upper(),
                "offset_constant": match.group(2),
                "entry_constant": match.group(3),
                "receipt": match.group(4),
                "shape": match.group(5),
                "argument_count": int(match.group(6)),
            })
    return rows


class EngineMethodRowGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = parse_rows()
        cls.catalog_text = CATALOG.read_text(encoding="utf-8")
        cls.constants_text = CONSTANTS.read_text(encoding="utf-8")
        cls.signatures_text = SIGNATURES.read_text(encoding="utf-8")

    def test_row_ids_exist_in_the_catalog(self):
        """行里的 id 必须在目录里能找到 —— 否则这一行永远挂不上任何 API（静默失效）。

        目录行的写法：`{MakeId(ApiDomain::Isaac, 1, 0x0056), …}`，所以这里用
        `MakeId(<域>, 1, 0x…id)` 这个形状去核对（域按行所在的家族不同而不同，不在这里判域）。
        """
        for row in self.rows:
            with self.subTest(row["id"]):
                # 目录行里写的是 `MakeId(域, ownerGroup, 序号)` —— **序号只有低 16 位**，
                # 而数据行里的 id 是**拼好的完整 id**（`域<<24 | ownerGroup<<16 | 序号`，
                # 与绑定表 `{0x0E010056, …}` 同一口径）。所以这里拿低 4 位十六进制去核。
                sequence = row["id"][-4:]
                pattern = re.compile(r"MakeId\(ApiDomain::\w+, 1, 0x" + sequence + r"\)")
                self.assertRegex(self.catalog_text, pattern,
                                 f"{row['id']} 不在目录里 —— 行挂不上任何 API")

    def test_shape_and_argument_count_agree(self):
        """行里的 `argumentCount` 必须与签名描述符表说的**一模一样**。

        不一致时共享处理器会直接报错（不硬调），所以这条门禁是"构建前就拦下来"的那半。
        """
        arity = shape_arity_table()
        for row in self.rows:
            with self.subTest(f"{row['id']}/{row['shape']}"):
                self.assertIn(row["shape"], arity,
                              f"未知形状 {row['shape']}：要么在 EngineCallShape 里加一个下标、"
                              f"并在 kEngineCallShapes 里补一行描述符，要么改用已有形状")
                self.assertEqual(row["argument_count"], arity[row["shape"]],
                                 "形状与参数个数不一致（会按错误的 ABI 调进引擎）")

    def test_row_constants_are_declared_and_registered(self):
        """两个常量都必须**定义**；其中 `k…Offset` 还必须**登记进签名表**。

        签名表只收 `k…Offset`（它按偏移把常量对应到 NRO 里的符号），
        入口指纹常量 `k…EntryWord` 是同一份证据的另一半，不进那张表。
        """
        for row in self.rows:
            for constant in (row["offset_constant"], row["entry_constant"]):
                with self.subTest(constant):
                    self.assertIn(f"{constant} = ", self.constants_text,
                                  f"{constant} 没在 runtime_constants.hpp 里定义")
            with self.subTest(row["offset_constant"]):
                self.assertIn(row["offset_constant"], self.signatures_text,
                              f"{row['offset_constant']} 没登记进 engine_symbol_signatures.json"
                              f"（先跑 tools/gen_engine_symbol_signatures.py）")

    def test_row_ids_never_use_a_hand_written_handler(self):
        """★ 机制的核心不变式：数据行的 id **不许**再挂手写处理器（那会重新占代码段）。"""
        binding_rows = re.findall(r"\{(0x[0-9A-Fa-f]{8}),\s*&\w+\}", self.catalog_text)
        for path in ROW_FILES:
            binding_rows.extend(
                re.findall(r"\{(0x[0-9A-Fa-f]{8}),\s*&\w+\}",
                           path.read_text(encoding="utf-8")))
        hand_written = {value.upper() for value in binding_rows}
        offenders = sorted(row["id"] for row in self.rows if row["id"] in hand_written)
        self.assertEqual(offenders, [],
                         f"这些 id 既在数据行里、又有手写处理器：{offenders} —— "
                         f"删掉手写那一份，否则每个 API 还是占 ≈490 字节代码")

    def test_row_total_is_pinned(self):
        self.assertEqual(len(self.rows), EXPECTED_ROW_TOTAL,
                         "数据行增减了 —— 改这里要写明本批加了什么、为什么")

    def test_the_row_struct_is_still_sixteen_bytes(self):
        header = ROWS_HEADER.read_text(encoding="utf-8")
        self.assertIn("static_assert(sizeof(EngineMethodRow) == 16", header,
                      "16 字节是这套机制的成本前提，改动它要重新做成本核算")
        for field in ("id", "offset", "entryWord", "receipt", "shape", "argumentCount",
                      "probeBit"):
            self.assertIn(field, header, f"行结构体里应有 {field}")

    def test_one_shared_handler_serves_every_row(self):
        """共享处理器必须只有**一份实现**，而且绑定循环真的在用它。"""
        implementations = []
        for path in LUA_DIR.glob("*.cpp"):
            text = path.read_text(encoding="utf-8")
            if re.search(r"^int EngineMethodHandler\(lua_State\* state\)", text, re.M):
                implementations.append(path.name)
        self.assertEqual(implementations, ["isaac_api.cpp"],
                         f"共享处理器应当只有一份实现，实际：{implementations}")
        binding = BINDING.read_text(encoding="utf-8")
        self.assertIn("EngineMethodHandler", binding,
                      "绑定循环没有接上共享处理器 ⇒ 数据行根本挂不上去")


if __name__ == "__main__":
    unittest.main()
