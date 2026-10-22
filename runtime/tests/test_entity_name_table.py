"""门禁：`Isaac.GetEntityTypeByName` / `GetEntityVariantByName` 用的静态名字表。

## 为什么有这条门禁（2026-09-29 批次 207）

MCM（Mod Config Menu）在 `PostGameStarted` 里就调
`Isaac.GetEntityTypeByName("Potato Dummy")`（`scripts/modconfig.lua:260/261`）。
这两条 API 原本**不存在** ⇒ "attempt to call a nil value" ⇒ 那一段直接抛错。
实现要查一张"实体名 → (Type, Variant)"的表，数据来源是**本体 `entities2.xml`**
（不在仓库里，是用户的游戏 dump）⇒ 按 `tools/pc_enum_docs/` 的先例，
把**提取好的**名字表 `tools/entity_name_source.txt` 进仓库，
生成器只做"文本 → C++"，生成物在任何干净检出里都能复核。

这条门禁钉五件事：

1. **生成物与源表一致**（跑一次 `--check`）—— 改了源表忘生成，真机就是旧名字；
2. **名字块下标与条目表严格自洽** —— 下标错一位，二分查到的是**别人的** Type/Variant，
   而且**不报错**（这正是最危险的失败方式：错误的名字返回一个看起来合理的实体号）；
   ★ 公式是 `len(名字) + 1`（相邻字面量先拼接，隐式 `\0` 只有整串末尾一个）——
   这条一开始写成了 `+ 2`，等于把生成器的错误模型抄了一遍，所以**它当时是绿的**，
   真缺陷是靠宿主行为测试（`test_lua_api_gap_mcm.py`）抓到的；
3. **表按名字升序** —— 实现在名字块上做二分（`strcmp`），乱序 ⇒ 静默查不到；
4. **几个具体条目钉死**（`Player` / `Monstro` / `Lokii` / `???` 家族）——
   源表被重新提取过时必须有人来解释差在哪；
5. **源码里不许出现 C++ 的历史三字符组**（`??'` 等）—— 见下。

## ★ 三字符组这条为什么值得单列

本体里真有条实体名叫 `???'s Only Friend`（933 号变体的昵称）。第一版生成器只转义了
反斜杠/引号/制表符/换行/回车，于是写出的源码是 `"???'s Only Friend\0"`，
`???` 里后两个 `?` 加 `'` 构成历史三字符组 ⇒ 本项目全量 `-Werror` ⇒
`error: trigraph ignored [-Werror,-Wtrigraphs]`，宿主编译直接失败。
现在生成器统一走 `escape_cpp_literal()`（`?` → `\\?`）。这条门禁**独立复扫一遍源码文本**，
就是防止将来有人"手工修一下生成物"或另写一条转义链把这个坑带回来。
"""

import importlib.util
import re
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "runtime" / "source"
TOOL = ROOT / "tools" / "generate_entity_name_table.py"
TABLE_SOURCE = ROOT / "tools" / "entity_name_source.txt"
GENERATED_HEADER = SOURCE / "program" / "entity_name_table.hpp"
GENERATED_IMPLEMENTATION = SOURCE / "program" / "entity_name_table.cpp"

#: 条目数与名字块字节数（源表被重新提取时这里会红 —— 那时要人工确认改了什么）。
EXPECTED_ENTRY_COUNT = 1028

#: 钉死的条目：`名字 → (Type, Variant, nameOffset)`。
#:
#: * `Player` —— 玩家实体，模组里出现频率最高的一条；
#: * `Monstro` / `Lokii` —— 普通敌人与变体（`Lokii` 的 Variant 是 1，
#:   正好验证"同 Type 不同 Variant"这一维真的进了表）；
#: * `1UP` / `???` / `???'s Only Friend` —— 名字块最前面那几条，
#:   同时是三字符组那个坑的现场（`???` 家族全在这里）；
#: * `Mom's Chest` —— **XML 实体引用**那个坑的现场：原始 XML 写的是
#:   `name="Mom&apos;s Chest"`，属性正则会原样带出 4 个字节的 `&apos;`，
#:   而 XML 解析器会还原成真撇号 ⇒ 名字不对就查不到（详见生成器文档头的第 4 个坑）。
EXPECTED_ENTRIES = {
    "1UP": (3, 41, 0),
    "???": (102, 1, 4),
    "??? (Alt)": (102, 2, 8),
    "???'s Only Friend": (3, 77, 18),
    "Lokii": (69, 1, 7076),
    "Monstro": (20, 0, 7795),
    "Mom's Chest": (5, 390, 7605),
    "Player": (1, 0, 8899),
}

#: C++ 的历史三字符组（C++17 起被删除，但编译器仍会为旧写法报警）。
TRIGRAPHS = ("??=", "??/", "??'", "??(", "??)", "??!", "??<", "??>", "??-")


def load_tool():
    spec = importlib.util.spec_from_file_location("generate_entity_name_table", TOOL)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def unescape_cpp(text: str) -> str:
    """把生成物里那个 `"..."` 片段还原成真实字符。

    只认生成器会写出的那几种转义；出现别的就抛错 —— 那说明转义链被改过，
    而"改了转义链但门禁照旧绿"正是这类生成物最坏的退化方式。
    """
    out: list[str] = []
    index = 0
    while index < len(text):
        character = text[index]
        if character != "\\":
            out.append(character)
            index += 1
            continue
        if index + 1 >= len(text):
            raise AssertionError(f"字面量以孤立的反斜杠结尾：…{text[-8:]!r}")
        following = text[index + 1]
        simple = {"\\": "\\", '"': '"', "t": "\t", "n": "\n", "r": "\r", "?": "?",
                  "0": "\0", "'": "'", "a": "\a", "b": "\b", "f": "\f", "v": "\v"}
        if following not in simple:
            raise AssertionError(
                f"生成物里出现了生成器不该写出的转义 `\\{following}` ——"
                " 转义链被改过了，先把这条门禁的期望值对齐再说")
        out.append(simple[following])
        index += 2
    return "".join(out)


class EntityNameTableGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = GENERATED_IMPLEMENTATION.read_text(encoding="utf-8")

        match = re.search(r"constexpr char kEntityNameBlob\[(\d+)\] = \{(.*?)\n\};",
                          cls.text, re.S)
        assert match is not None, "解析 kEntityNameBlob 失败（生成物格式变了？）"
        cls.blob_declared_size = int(match.group(1))
        cls.blob_pieces = [unescape_cpp(chunk) for chunk in
                           re.findall(r'"((?:[^"\\]|\\.)*)"', match.group(2))]

        cls.entries = [(int(offset), int(type_number), int(variant), unescape_cpp(name))
                       for offset, type_number, variant, name in
                       re.findall(r"\{(\d+), (\d+), (-?\d+)\},\s*//\s*(.*)",
                                  cls.text)]

    def test_generated_files_match_the_source_table(self):
        """生成物必须与 `tools/entity_name_source.txt` 逐字节一致。"""
        result = subprocess.run([sys.executable, str(TOOL), "--check"],
                                capture_output=True, text=True, cwd=ROOT)
        self.assertEqual(result.returncode, 0,
                         "生成物与 tools/entity_name_source.txt 不一致：\n"
                         + result.stdout + result.stderr)
        self.assertIn("生成物与源一致", result.stdout)

    def test_entry_count_is_pinned(self):
        self.assertEqual(len(self.entries), EXPECTED_ENTRY_COUNT,
                         "条目数变了：源表被重新提取过，先确认增删了哪些名字，再改这里")

    def test_offsets_are_the_running_sum_of_the_names(self):
        """条目下标 = 前面所有名字块长度的累加（`len(名字 UTF-8 字节) + 1`）。

        错一位 ⇒ 二分命中别人的 Type/Variant，而且**不报错**。

        ★ **公式是 `+1`，不是 `+2`**（2026-09-29 修正）。生成物写成一串**相邻的字符串
        字面量**（`"1UP\\0" "???\\0" …`），而 C++ 里相邻字面量在**翻译阶段先拼接成一整条**，
        隐式结尾 `\\0` 只有**整串末尾一个**、**不是每片一个** ⇒ 每条名字在数组里就是
        `名字字节 + 自己的显式 \\0`。
        第一版把 `+2` 当公式 ⇒ 第一条之外全部偏大（第 i 条偏 i 字节）⇒
        真机上 `Isaac.GetEntityTypeByName("Monstro")` **恒返回 0**。
        ★ 这条门禁当时**没抓住**它 —— 因为下面这段累加把同一个错误模型抄了一遍
        （`+2`），等于自己证明自己。抓到它的是
        `runtime/tests/test_lua_api_gap_mcm.py`（真 Lua 状态机 + 伪造内存）。
        改这一行之前，先想清楚"隐式 `\\0` 到底有几个"。
        """
        running = 0
        for index, (offset, _, _, name) in enumerate(self.entries):
            self.assertEqual(offset, running,
                             f"第 {index} 条 `{name}` 的下标是 {offset}，按公式应为 {running}")
            running += len(name.encode("utf-8")) + 1
        # ★ 声明的大小 = 内容 + 1：C++ 不允许 `char[N] = "字面量"` 丢掉字面量自带的隐式
        #   结尾 `\0`（C 允许、C++ 是硬错误），所以尾后必须多留一格。
        self.assertEqual(self.blob_declared_size, running + 1,
                         "名字块声明的大小与 `len + 1` 的累加对不上"
                         "（应当是内容字节数再加上尾后那格隐式结尾）")

    def test_blob_pieces_line_up_with_the_entries(self):
        """名字块的**每一片**都要与条目表一一对应，且块内该下标处真的是那条名字。

        ★ 这条是"下标自洽"的独立验证 —— 上一条只算加法，这条真的去块里取字节。
        名字片按 `"名字\\0"` 写 ⇒ 还原出来每片是 `名字 + "\\0"`；相邻字面量**先拼接**
        ⇒ 整块就是这些片**直接首尾相接**（片与片之间**不再**多一个 `\\0`）。
        数组声明的大小 = 拼接结果长度 **+ 1**（那一格是字面量自带的隐式结尾 `\\0`，
        C++ 不许把它丢掉 ⇒ 尾后多留一格；它在最后一条名字的显式 `\\0` 之后，永远读不到）。
        """
        self.assertEqual(len(self.blob_pieces), len(self.entries),
                         "名字块的片数与条目数不一致")
        blob = "".join(self.blob_pieces)
        for index, (offset, _, _, name) in enumerate(self.entries):
            self.assertEqual(self.blob_pieces[index], name + "\0",
                             f"第 {index} 片与条目表的名字不一致")
            sliced = blob[offset:]
            self.assertTrue(sliced.startswith(name + "\0"),
                            f"名字 `{name}` 在块内下标 {offset} 处对不上：读到 {sliced[:24]!r}")
        self.assertEqual(self.blob_declared_size, len(blob) + 1)

    def test_names_are_sorted_so_the_binary_search_works(self):
        """表按名字**字节序升序** —— 实现的二分建立在这一点上，乱序就是静默查不到。"""
        names = [name for _, _, _, name in self.entries]
        encoded = [name.encode("utf-8") for name in names]
        self.assertEqual(encoded, sorted(encoded),
                         "名字不是升序：二分查找会静默漏掉一些名字")

    def test_pinned_entries(self):
        found = {name: (type_number, variant, offset)
                 for offset, type_number, variant, name in self.entries}
        for name, expected in EXPECTED_ENTRIES.items():
            with self.subTest(name=name):
                self.assertIn(name, found, f"名字 `{name}` 从表里消失了")
                self.assertEqual(found[name], expected,
                                 f"`{name}` 的 (Type, Variant, 下标) 变了 —— 先确认源表改了什么")

    def test_no_xml_entity_survives_into_the_table(self):
        """★ 源表里不许留下 XML 实体引用（`&apos;` 这类）—— 那是**没有反转义**的痕迹。

        `rp_patch/resources/entities2.xml` 里 33 处 `&apos;` 全在 `name` 属性上，
        其中 7 个（其余 26 个在 base 里已有裸撇号版本、被 base 优先覆盖）会真的进表。
        XML 解析器会把它们还原成 `'`，我们只做属性正则 ⇒ 必须自己走一遍反转义。
        留一个 `&amp;`/`&apos;` 在表里就等于那条名字**永远查不到**。
        """
        for _, _, _, name in self.entries:
            with self.subTest(name=name):
                self.assertNotRegex(name, r"&(#x?[0-9A-Fa-f]+|amp|lt|gt|quot|apos);",
                                    "名字里还有 XML 实体引用：表是从 XML 提取的，"
                                    "`parse_xml()` 必须走 `unescape_xml()`")

    def test_mod_only_names_are_absent(self):
        """`Potato Dummy` 这类**只在模组代码里出现**的名字必须查不到。

        这正是文档头写明的偏离：PC 上模组可以在 `content/entities2.xml` 里加实体，
        我们只看得到本体 XML ⇒ 与本体 PC 一样返回 `0` / `-1`，
        MCM 的 `if potatoType and potatoVariant > 0` 自然走"没有"那一支。
        """
        names = {name for _, _, _, name in self.entries}
        self.assertNotIn("Potato Dummy", names)

    def test_no_cpp_trigraph_in_the_generated_source(self):
        """★ 生成物里不许出现三字符组（本体真有条名字叫 `???'s Only Friend`）。

        替换发生在词法分析之前，注释也在射程内 ⇒ 整份文件一起扫。
        """
        for trigraph in TRIGRAPHS:
            self.assertNotIn(trigraph, self.text,
                             f"生成物里出现了 C++ 三字符组 `{trigraph}`："
                             " 生成器的 `escape_cpp_literal()` 没把它转义成 `\\?`"
                             f"（本项目 -Werror，这会直接编译失败）")
        self.assertIn(r"\?\?\?'s Only Friend", self.text,
                      "`???'s Only Friend` 这条名字不见了 —— 它是三字符组那个坑的现场，别删")

    def test_header_declares_the_lookup_contract(self):
        """头文件要明确 `variant` 是有符号（查不到返回 `-1`）与名字块的存在。

        实现里 `variant` 用无符号就得额外走一条特例分支；这条把设计意图钉住。
        """
        header = GENERATED_HEADER.read_text(encoding="utf-8")
        self.assertIn("std::int16_t variant;", header)
        self.assertIn("EntityNameBlob", header)
        self.assertIn("EntityNameEntries", header)

    def test_the_repository_source_table_round_trips(self):
        """`tools/entity_name_source.txt` 的读回必须与生成器解析出的一致。

        这条防的是"源文件被手工编辑过、转义没遵守规则"——生成物照样能重算出来，
        但源文件本身已经不可信了。
        """
        tool = load_tool()
        rows = tool.read_source()
        self.assertEqual(len(rows), EXPECTED_ENTRY_COUNT)
        for name, type_number, variant in rows:
            # 写出去再读回来必须一模一样（`escape_name()` / `unescape_name()` 互逆）。
            self.assertEqual(tool.unescape_name(tool.escape_name(name)), name)
            # ★ 名字里**本来就可能有制表符**（`Telekinesis<TAB>Halo`）——
            #   这正是转义存在的理由，所以这里只能要求"转义后没有裸制表符"。
            self.assertNotIn("\t", tool.escape_name(name))
            self.assertNotIn("\n", tool.escape_name(name))
            self.assertLess(type_number, 1 << 16)
            self.assertGreaterEqual(variant, -(1 << 15))
        self.assertEqual([row[0] for row in rows], sorted(row[0] for row in rows))
        # 源文件里也应已经转义了问号（与生成物同一套规则）。
        raw = TABLE_SOURCE.read_text(encoding="utf-8")
        for trigraph in TRIGRAPHS:
            self.assertNotIn(trigraph, raw,
                             f"源表里出现了未转义的 `{trigraph}`")


if __name__ == "__main__":
    unittest.main()
