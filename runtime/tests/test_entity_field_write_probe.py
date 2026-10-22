"""写探针必须在读数里看得见（批次 212 玩家字段写 / 批次 214 种子效果写）。

为什么单开一条门禁：字段写守卫是"**报错**"，不是"静默忽略" —— 模组写了我们没实现的字段，
**整条回调当场中断**（MCM 的菜单就是这么画不出来的：它在渲染回调里 `player.Velocity = vecZero`）。
所以"模组到底写了哪些字段、有没有被拒绝"必须**不需要看屏幕**就能读到；
而"设施做了、判据没接上"是本项目最容易犯的错（批次 196/203/209/211 各犯过一次）。

批次 214 同理补了第二个探针：`Seeds:AddSeedEffect`/`RemoveSeedEffect` 是**按设计不生效的空实现**
（理由见 `api_deviation.cpp` 的 `0x0F010005`/`0x0F010006`）⇒ "模组真的调了它们、而我们没抛错打断"
这件事**只能**靠一个可读的计数来证明。那两条还额外踩过同一个坑：探针一开始写在
`game_api.cpp` 的**匿名命名空间里** ⇒ 内部链接 ⇒ ELF 符号表里查不到 ⇒ 读数工具永远读不到它。

这条门禁钉四件事：
1. 探针符号在读数工具的 `SYM_ELF_NAMES` 里（不然真机读不到）；
2. 读数工具**真的把它们打印出来**（只进读取列表、漏了打印 = 等于没测）；
3. 被拒字段的计数也在打印里（"模组写了什么我们没实现"要一眼可见）；
4. ★ 探针的定义**必须在匿名命名空间之外**（内部链接会让符号从 ELF 里消失，读数工具静默读不到）。
"""

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
READER = ROOT / "tools" / "read_device_state_via_gdb.py"
IMPLEMENTATION = ROOT / "runtime" / "src" / "interfaces" / "lua" / "isaac_api.cpp"
GAME_IMPLEMENTATION = ROOT / "runtime" / "src" / "interfaces" / "lua" / "game_api.cpp"

#: 探针键名（读数工具里的读取键）。
PROBE_KEYS = (
    "entity_field_writes",
    "entity_field_write_rejected",
    "last_entity_field_write_name",
)

#: 批次 214：种子效果写探针（符号名 → 读数键）。
SEEDS_PROBE_SYMBOL = "g_SeedsEffectWriteAttempts"
SEEDS_PROBE_KEY = "seeds_effect_write_attempts"


class EntityFieldWriteProbeTests(unittest.TestCase):
    def test_implementation_exposes_the_probes(self):
        source = IMPLEMENTATION.read_text(encoding="utf-8")
        for symbol in ("g_EntityFieldWrites", "g_EntityFieldWriteRejected",
                       "g_LastEntityFieldWriteName"):
            self.assertIn(symbol, source, f"实现里必须有 {symbol} 这个探针")

    def test_reader_knows_the_symbols(self):
        reader = READER.read_text(encoding="utf-8")
        for symbol in ("g_EntityFieldWrites", "g_EntityFieldWriteRejected",
                       "g_LastEntityFieldWriteName"):
            self.assertIn(symbol, reader, f"读数工具必须认得 {symbol}，否则真机上读不到")

    def test_reader_actually_prints_the_reading(self):
        reader = READER.read_text(encoding="utf-8")
        for key in PROBE_KEYS:
            # "打印出来了"的三种合法写法：`'key' in values`（整段判在不在）、
            # `first_u32(values, 'key')` / `first(values, 'key')`（取值）。**只要读了就算**，
            # 关键是别"接进读取列表却没进打印那一段"。
            printed = any(marker in reader for marker in (
                f"'{key}' in values", f"first_u32(values, '{key}')", f"first(values, '{key}')"))
            self.assertTrue(printed, f"读数工具必须打印 {key}（缺了就是「读得到却看不见」）")
        self.assertIn("被我们拒绝的写", reader,
                      "被拒字段的计数也要打印出来（模组写了我们没实现的字段时能一眼看见）")

    def test_writable_field_names_are_the_documented_set(self):
        """可写字段名只能是我们**取证过**的那些 —— 加字段必须同时改这里（防静默扩权）。"""
        source = IMPLEMENTATION.read_text(encoding="utf-8")
        # 四个手写字段仍然是逐字段 `std::strcmp(field, "X")` 分支（不进表）。
        for field in ("ControlsCooldown", "ControlsEnabled", "Velocity", "Position"):
            self.assertIn(f'std::strcmp(field, "{field}")', source,
                          f"{field} 必须在 EntityNewIndex 里有显式分支")
        # 批次 405：六个战斗属性走表驱动（`{"Field", kEntityPlayer…Offset, bucket}`）。
        for field in ("Damage", "MoveSpeed", "MaxFireDelay", "ShotSpeed", "Luck", "TearRange"):
            self.assertIn(f'"{field}",', source,
                          f"{field} 必须登记进 EntityNewIndex 的字段表")
        self.assertIn("read-only except", source,
                      "陌生字段名仍然要报错（故意保留：防拼错被静默吞掉）")
        # 拒写文案必须把新放行的字段名都列出来（否则读者会以为它们不可写）。
        for field in ("Damage", "MoveSpeed", "MaxFireDelay", "ShotSpeed", "Luck", "TearRange"):
            self.assertIn(field, source, f"拒写文案里要列出 {field}")


class SeedsEffectWriteProbeTests(unittest.TestCase):
    """批次 214：`Seeds:AddSeedEffect`/`RemoveSeedEffect` 的"被调用了几次"探针。

    这两条按设计**不生效**，唯一能证明"模组真的走了、而没被我们抛错打断"的就是这个计数
    ⇒ 它必须**可读、且真的被打印**（与上面那组同一套口径）。
    """

    def test_implementation_exposes_the_probe_outside_the_anonymous_namespace(self):
        source = GAME_IMPLEMENTATION.read_text(encoding="utf-8")
        self.assertIn(SEEDS_PROBE_SYMBOL, source, f"实现里必须有 {SEEDS_PROBE_SYMBOL} 这个探针")
        # ★ 定义必须在**匿名命名空间之外**：放进去就变成内部链接，ELF 里查不到（本批真实踩过）。
        #   判据 = 定义出现在第一个 `namespace {` 之前。
        definition = f"std::atomic<std::uint32_t> {SEEDS_PROBE_SYMBOL}{{0}};"
        self.assertIn(definition, source, "探针要有唯一的一处定义（带初值）")
        self.assertLess(
            source.index(definition), source.index("\nnamespace {\n"),
            f"{SEEDS_PROBE_SYMBOL} 必须定义在匿名命名空间**之外** —— 放进去就是内部链接，"
            "读数工具（用 mangled 名查 ELF）永远读不到它。")

    def test_reader_knows_and_prints_the_symbol(self):
        reader = READER.read_text(encoding="utf-8")
        self.assertIn(SEEDS_PROBE_SYMBOL, reader, f"读数工具必须认得 {SEEDS_PROBE_SYMBOL}")
        printed = any(marker in reader for marker in (
            f"'{SEEDS_PROBE_KEY}' in values", f"first_u32(values, '{SEEDS_PROBE_KEY}')",
            f"first(values, '{SEEDS_PROBE_KEY}')"))
        self.assertTrue(printed, f"读数工具必须打印 {SEEDS_PROBE_KEY}（缺了就是「读得到却看不见」）")

    def test_the_two_apis_share_one_counter_and_never_raise(self):
        source = GAME_IMPLEMENTATION.read_text(encoding="utf-8")
        # 两条处理器各记一次数（共用一个计数器）。
        self.assertEqual(source.count(f"{SEEDS_PROBE_SYMBOL}.fetch_add(1"), 2,
                         "Add/Remove 各记一次数")
        for handler in ("SeedsAddSeedEffect", "SeedsRemoveSeedEffect"):
            start = source.index(f"int {handler}(lua_State* state) {{")
            body = source[start:source.index("\n}\n", start) + 3]
            counted = body.index(f"{SEEDS_PROBE_SYMBOL}.fetch_add(1")
            tail = body[counted:]
            # ★ 记数之后**只许** `return 0;` —— 参数不对时的 `luaL_error` 允许（在记数之前），
            #   但"正常调用路径"绝不许抛错（抛错会打断调用方整条回调，正是这两条存在的理由）。
            self.assertIn("return 0;", tail, f"{handler} 记数之后必须原样返回")
            self.assertNotIn("luaL_error", tail, f"{handler} 的正常路径绝不许抛错")


if __name__ == "__main__":
    unittest.main()
