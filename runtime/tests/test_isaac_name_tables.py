"""门禁：`Isaac.Get*ByName` 名字表一族用的静态表（批次 240，2026-09-30）。

## 为什么有这条门禁

这 5 条 API（`GetItemIdByName` / `GetCardIdByName` / `GetPillEffectByName` /
`GetPlayerTypeByName` / `GetChallengeIdByName`）在 Switch 上没有引擎函数可调，
表是我们**自己生成**的（`tools/isaac_name_source/*.txt` →
`tools/generate_isaac_name_tables.py` → `runtime/source/program/isaac_name_tables.*`）。
自己生成的表有两个"静默出错"的口子，本文件各钉一条：

1. **名字块下标与条目表不自洽** —— 下标错一位，二分查到的是**别人的**编号，
   而且**不报错**（最危险的失败方式：返回一个看起来合理的编号，模组拿它去 `AddCollectible`）。
   ★ 所以本文件**不调用生成器**来核对下标，而是**自己按源表重算一遍**再逐字节比
   （`test_entity_name_table.py` 的教训：把生成器那套公式抄进门禁，等于把它的错误模型也抄进来，
   于是生成器错、门禁也绿）。
2. **表没按名字升序** —— 实现是二分查找，乱序 ⇒ 静默查不到（返回 `-1`，
   模组以为"这个道具不存在"）。

另外钉住三件事：生成物与源表一致（跑 `--check`）、**条目名不许出现未转义的特殊字符**
（反斜杠/制表符/问号三字符组 —— 本项目全量 `-Werror`，`???` 会直接编译失败）、
以及几个**具体条目**（源表被重新提取时必须有人解释差在哪）。

## 为什么源数据必须进仓库

游戏 dump 不在仓库里（`.gitignore` 挡掉）⇒ 若源文件也放 dump 里，这类工作
**对任何其他人都不可做**。与 `entity_name_source.txt` / `pc_enum_docs/` 同一条规矩。
"""

import importlib.util
import pathlib
import re
import subprocess
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
GENERATOR = ROOT / "tools" / "generate_isaac_name_tables.py"
SOURCE_DIR = ROOT / "tools" / "isaac_name_source"
HEADER = ROOT / "runtime" / "source" / "program" / "isaac_name_tables.hpp"
IMPL = ROOT / "runtime" / "source" / "program" / "isaac_name_tables.cpp"

#: 契约里逐个给过的例子（`tools/pc_contract_docs/Isaac.md`）—— 必须逐条对上。
#: `("表 kind", 名字, 期望编号, 期望堕落编号[或 None])`
PINNED = (
    ("collectible", "The Sad Onion", 1, None),
    ("collectible", "Brimstone", 118, None),   # `Isaac.md:282` 的例子：注释里逐字写着 118
    ("collectible", "Void", 477, None),        # 语料 TBOI_Better-Voiding 实际传的名字
    ("collectible", "Abyss", 706, None),
    ("collectible", "Flip", 711, None),
    ("player_type", "Isaac", 0, 21),           # 堕落版（`GetPlayerTypeByName(name, true)`）
    ("player_type", "Magdalene", 1, 22),
    ("challenge", "Aprils fool", 32, None),    # `Isaac.md:183` 的例子（注意小写 f）
    ("challenge", "Pitch Black", 1, None),     # challenges.xml 的第一条
)


def load_generator():
    spec = importlib.util.spec_from_file_location("generate_isaac_name_tables", GENERATOR)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def read_sources() -> dict[str, list[tuple[str, int, int]]]:
    """源表 → `{表名: [(名字, 编号, 堕落编号)]}`（**独立于生成器**地读）。

    ★ 名字要**解回转义**再交出去：源文件里存的是转义文本（`\\?\\?\\?`），
    而运行时比的是**原始字节**（`???`）。两者在字典序上不同（`\\` 是 0x5C、`?` 是 0x3F）
    ⇒ 不解码的话"升序"与"字节长度"两条判据都会拿错口径（本门禁第一版就这么错过一次）。
    """
    out: dict[str, list[tuple[str, int, int]]] = {}
    for kind, meta in load_generator().TABLES.items():
        rows: list[tuple[str, int, int]] = []
        for line in (SOURCE_DIR / meta["file"]).read_text(encoding="utf-8").splitlines():
            if not line or line.startswith("#"):
                continue
            fields = line.split("\t")
            rows.append((decode_literal(fields[0]), int(fields[1]),
                         int(fields[2]) if len(fields) > 2 else -1))
        out[kind] = rows
    return out


def parse_generated() -> dict[str, dict]:
    """从生成物里把每张表的名字块与条目表读回来（**不信任生成器的自述**）。"""
    text = IMPL.read_text(encoding="utf-8")

    tables: dict[str, dict] = {}
    for kind in load_generator().TABLES:
        camel = "".join(part.capitalize() for part in kind.split("_"))
        blob = re.search(rf"constexpr char k{camel}NameBlob\[\d+\] = \{{(.*?)\n\}};",
                         text, re.S)
        entries = re.search(rf"constexpr IsaacNameEntry k{camel}NameEntries\[\] = \{{(.*?)\n\}};",
                            text, re.S)
        assert blob is not None, f"生成物里找不到 k{camel}NameBlob"
        assert entries is not None, f"生成物里找不到 k{camel}NameEntries"
        raw = re.findall(r'"((?:[^"\\]|\\.)*)"', blob.group(1))
        parsed = [
            (int(m.group(1)), int(m.group(2)), int(m.group(3)))
            for m in re.finditer(r"\{\s*(\d+),\s*(-?\d+),\s*(-?\d+)\s*\}", entries.group(1))
        ]
        tables[kind] = {"raw": raw, "entries": parsed}
    return tables


def decode_literal(literal: str) -> str:
    """把生成物里那一段 C++ 字符串字面量的内容解回名字（**独立实现**，不借生成器的转义函数）。

    生成物每条是 `"名字\\0"`（尾部那个 `\\0` 是**分隔符**，不是名字的一部分）。
    """
    body = literal
    if body.endswith("\\0"):
        body = body[:-2]
    out: list[str] = []
    index = 0
    while index < len(body):
        char = body[index]
        if char == "\\" and index + 1 < len(body):
            following = body[index + 1]
            out.append({"\\": "\\", "?": "?", "t": "\t", "n": "\n", "r": "\r"}
                       .get(following, following))
            index += 2
        else:
            out.append(char)
            index += 1
    return "".join(out)


class IsaacNameTableGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sources = read_sources()
        cls.generated = parse_generated()

    def test_generated_matches_the_sources(self):
        """跑生成器的 `--check`：生成物必须与源表逐字节一致。"""
        result = subprocess.run([sys.executable, str(GENERATOR), "--check"],
                                cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0,
                         f"生成物与源表不一致（重跑 --write）：\n{result.stdout}{result.stderr}")

    def test_blob_offsets_are_recomputed_independently(self):
        """★ 按源表**自己重算**每个名字的下标与名字块内容，再与生成物逐字节比。

        不调用生成器的函数：抄它的公式等于抄它的错误模型（见文件头第 1 条）。
        """
        for kind, rows in self.sources.items():
            with self.subTest(kind=kind):
                generated = self.generated[kind]
                # ① 名字块：把源表里每个名字解回来逐条比。
                self.assertEqual(len(generated["raw"]), len(rows),
                                 f"{kind}：名字块条数与源表不一致")
                for index, (got, (name, _, _)) in enumerate(zip(generated["raw"], rows)):
                    self.assertEqual(decode_literal(got), name,
                                     f"{kind} 第 {index} 条名字不一致")
                # ② 下标：按 `len(UTF-8 字节) + 1` 累加，与生成物里的 nameOffset 逐条比。
                offset = 0
                for index, (name, identifier, alternate) in enumerate(rows):
                    entry = generated["entries"][index]
                    self.assertEqual(entry[0], offset,
                                     f"{kind} 第 {index} 条（{name}）的 nameOffset 应是 {offset}、"
                                     f"生成物写 {entry[0]}")
                    self.assertEqual(entry[1], identifier, f"{kind}：{name} 的编号不一致")
                    self.assertEqual(entry[2], alternate, f"{kind}：{name} 的堕落编号不一致")
                    offset += len(name.encode("utf-8")) + 1

    def test_names_are_sorted_for_binary_search(self):
        """实现在名字块上做二分 ⇒ 必须按名字升序（UTF-8 字节序，与 `strcmp`/`memcmp` 同口径）。"""
        for kind, rows in self.sources.items():
            with self.subTest(kind=kind):
                names = [name.encode("utf-8") for name, _, _ in rows]
                self.assertEqual(names, sorted(names), f"{kind} 的名字没有按升序排")

    def test_no_unescaped_special_characters_in_generated_source(self):
        """生成物里不许有未转义的 `?`（三字符组）、制表符、裸反斜杠。

        与 `test_entity_name_table.py` 同一条理由：本项目全量 `-Werror`，
        `???'s Only Friend` 那种名字会直接编译失败。这里**独立复扫**生成物文本。
        """
        text = IMPL.read_text(encoding="utf-8")
        blob = re.search(r"kCollectibleNameBlob\[\d+\] = \{(.*?)\n\};", text, re.S)
        self.assertIsNotNone(blob)
        for line in blob.group(1).splitlines():
            literal = line.strip()
            if not literal.startswith('"'):
                continue
            self.assertNotIn("\t", literal, f"名字块里有裸制表符：{literal!r}")
            body = literal[1:literal.rindex('"')]
            # 去掉合法转义序列之后，剩下的 `?` 必须是 `\?`
            stripped = re.sub(r"\\[\\?tnr]", "", body)
            self.assertNotIn("?", stripped, f"名字块里有未转义的 `?`（三字符组）：{literal!r}")

    def test_pinned_entries(self):
        """契约例子与语料实际用到的名字钉死 —— 源表重提取时必须有人解释差在哪。"""
        by_kind = {kind: dict((name, (identifier, alternate))
                              for name, identifier, alternate in rows)
                   for kind, rows in self.sources.items()}
        for kind, name, identifier, alternate in PINNED:
            with self.subTest(f"{kind}:{name}"):
                self.assertIn(name, by_kind[kind], f"{kind} 里没有 {name!r}")
                self.assertEqual(by_kind[kind][name][0], identifier,
                                 f"{kind}:{name} 的编号变了（契约/语料钉的是 {identifier}）")
                if alternate is not None:
                    self.assertEqual(by_kind[kind][name][1], alternate,
                                     f"{kind}:{name} 的堕落编号变了（契约钉的是 {alternate}）")

    def test_lookup_signature_is_wired(self):
        """静态名字查询仍接线；药丸走当前独立的名字服务。"""
        api = (ROOT / "runtime" / "src" / "interfaces" / "lua" / "isaac_api.cpp").read_text(
            encoding="utf-8")
        for kind in ("Collectible", "Card", "PlayerType", "Challenge"):
            with self.subTest(kind):
                self.assertTrue(f"IsaacNameKind::{kind}" in api,
                              f"isaac_api.cpp 里没有用到 IsaacNameKind::{kind}")
        self.assertIn("LookupIsaacName", api)
        self.assertIn("return RuntimeGetPillEffectByName(state);", api)
        service = (ROOT / "runtime/src/interfaces/lua/rplus_content_names.cpp").read_text()
        self.assertIn("int RuntimeGetPillEffectByName(lua_State* state)", service)
        self.assertIn("Lookup(state,Family::Pill)", service)

    def test_header_declares_the_alternate_id(self):
        header = HEADER.read_text(encoding="utf-8")
        self.assertIn("alternateId", header,
                      "名字表结构体里应有 alternateId（角色表的堕落编号要用）")


if __name__ == "__main__":
    unittest.main()
