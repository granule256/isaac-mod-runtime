#!/usr/bin/env python3
"""生成游戏对象名称到编号的 C++ 查找表。

覆盖收藏品、饰品、卡牌、药丸、角色和挑战。导入游戏 XML 与 stringtable.sta
后生成文本源，再由文本源生成可编译的数据表；游戏原件不随源码分发。
运行时新增的模组名称由独立追加表处理，静态表仅覆盖本体数据。
"""

from __future__ import annotations

import argparse
import pathlib
import re
import sys
import xml.etree.ElementTree as ET

ROOT = pathlib.Path(__file__).resolve().parent.parent
SOURCE_DIR = ROOT / "tools" / "isaac_name_source"
HEADER = ROOT / "runtime" / "source" / "program" / "isaac_name_tables.hpp"
IMPL = ROOT / "runtime" / "source" / "program" / "isaac_name_tables.cpp"

#: 每张表的定义：`kind` → （源文件名, 放它的 XML 元素集合, PC 契约页:行号, 找不到时的返回）
#: 「找不到返回什么」必须按契约写：`GetItemIdByName` 是 `-1`、`GetCardIdByName` 是 `-1`。
TABLES: dict[str, dict] = {
    "collectible": {
        "file": "collectibles.txt",
        "elements": ("passive", "active", "familiar"),
        "doc": "tools/pc_contract_docs/Isaac.md:274",
        "api": "Isaac.GetItemIdByName",
    },
    "card": {
        "file": "cards.txt",
        "elements": ("card",),
        "doc": "tools/pc_contract_docs/Isaac.md:148",
        "api": "Isaac.GetCardIdByName",
    },
    "pill_effect": {
        "file": "pill_effects.txt",
        "elements": ("pilleffect",),
        "doc": "tools/pc_contract_docs/Isaac.md",
        "api": "Isaac.GetPillEffectByName",
    },
    "player_type": {
        "file": "player_types.txt",
        "elements": ("player",),
        "doc": "tools/pc_contract_docs/Isaac.md",
        "api": "Isaac.GetPlayerTypeByName",
    },
    "challenge": {
        "file": "challenges.txt",
        "elements": ("challenge",),
        "doc": "tools/pc_contract_docs/Isaac.md:176",
        "api": "Isaac.GetChallengeIdByName",
    },
    # `Isaac.GetTrinketIdByName` —— 只能加在末尾
    #   （`IsaacNameKind` 的值就是 `kIsaacNameTables` 的下标，加在中间会整体错位）。
    #   契约 `tools/pc_contract_docs/Isaac.md:457`：「Returns the TrinketType of a trinket based on
    #   its name. (File: **items.xml**) Returns `-1` if no trinket with that name could be found」
    #   —— 饰品和收藏品同在一个 `content/items.xml`（`<trinket>` 标签），
    #   本游戏没有 `trinkets.xml`（已核实：全仓找不到该文件；引擎的 `ItemConfig::Load`
    #   同时解析 `<passive>/<active>/<familiar>` 与 `<trinket>`，见存档的反汇编）。
    "trinket": {
        "file": "trinkets.txt",
        "elements": ("trinket",),
        "doc": "tools/pc_contract_docs/Isaac.md:457",
        "api": "Isaac.GetTrinketIdByName",
    },
}

#: 每张表读哪份 XML（`(相对 resources 的路径, 元素名)` 由 `elements` 给出）。
XML_FILES = {
    "collectible": "items.xml",
    "card": "pocketitems.xml",
    "pill_effect": "pocketitems.xml",
    "player_type": "players.xml",
    "challenge": "challenges.xml",
    # 饰品没有独立的 `trinkets.xml` —— 与收藏品同在 `items.xml`（`<trinket>`）。
    "trinket": "items.xml",
}

C_ESCAPES = (("\\", "\\\\"), ("\t", "\\t"), ("\n", "\\n"), ("\r", "\\r"), ("?", "\\?"))

#: `escape_name` 的逆（只认本生成器写出的那几种转义）。
UNESCAPES = {"\\": "\\", "?": "?", "t": "\t", "n": "\n", "r": "\r"}


def escape_name(name: str) -> str:
    for raw, escaped in C_ESCAPES:
        name = name.replace(raw, escaped)
    return name


def unescape_name(text: str) -> str:
    """把源数据里那段转义文本解回**原始名字**。

    ★★ 为什么要它（批次 240 真踩了）：源数据里存的是**已转义**的文本，
    而生成 C++ 字面量时**不能**再转一次 —— 转两次会让表里的名字变成
    `\\?\\?\\?'s Only Friend`（带**字面反斜杠**），运行时拿 `???'s Only Friend` 去比
    **永远不中、而且不报错**；同时下标也会错（如果用转义后的长度算，就比真实字节数多）。
    ⇒ 分工写死：**长度一律用解码后的名字**，字面量用源文本（它已经是转义形态）。
    """
    out: list[str] = []
    index = 0
    while index < len(text):
        char = text[index]
        if char == "\\" and index + 1 < len(text):
            out.append(UNESCAPES.get(text[index + 1], text[index + 1]))
            index += 2
        else:
            out.append(char)
            index += 1
    return "".join(out)


# --------------------------------------------------------------------------- #
# 提取
# --------------------------------------------------------------------------- #

def parse_stringtable(path: pathlib.Path) -> dict[str, str]:
    """`stringtable.sta`（其实是 XML）→ `{键: 英文}`。

    ★★ **位置不是 `<languages>` 的 `index`** —— 这里踩过一次、而且会**静默出错**：
    `<languages>` 里 `index=0` 是那个叫 `Key` 的伪语言（放本地化键本身），
    而每个 `<key>` 下的 `<string>` 列表**并不给它留一格** ⇒ 真实位置 = 在
    「按 index 排序、剔除 `Key`」之后的序号。按 `index` 直接取会拿到**日文名**
    （实测：`#ABYSS_NAME` 取到 `アビス` 而不是 `Abyss`，而表照样生成、照样能查，
    只是查出来的名字永远不匹配模组传的英文名 —— 那种错最难发现）。
    """
    root = ET.parse(path).getroot()
    ordered = sorted(
        ((int(language.get("index")), language.get("name"))
         for language in root.find("languages").findall("language")))
    emitted = [name for _, name in ordered if name != "Key"]
    if "English" not in emitted:
        raise SystemExit(f"{path} 的 <languages> 里没有 English")
    english_position = emitted.index("English")

    out: dict[str, str] = {}

    def walk(node: ET.Element) -> None:
        for category in node.findall("category"):
            for key in category.findall("key"):
                strings = [s.text or "" for s in key.findall("string")]
                if english_position < len(strings):
                    out[key.get("name")] = strings[english_position]
            walk(category)

    walk(root)

    # 防呆：拿两个**已知**的键核对取到的确实是英文（不是日文/韩文）。
    # 不核对的话，"位置算错"与"算对"在生成物上长得一模一样。
    for probe_key, expected in (("THE_SAD_ONION_NAME", "The Sad Onion"),
                                ("ISAAC_NAME", "Isaac")):
        got = out.get(probe_key)
        if got != expected:
            raise SystemExit(
                f"{path} 的语言位置算错了：{probe_key} 取到 {got!r}、应是 {expected!r}"
                f"（emitted 语言顺序 = {emitted}）")
    return out


def collect_entries(resources: pathlib.Path, kind: str,
                    stringtable: dict[str, str]) -> dict[int, str]:
    """从一份 `resources/` 里取出 `{编号: 名字}`（`#键` 就地解析成英文）。"""
    path = resources / XML_FILES[kind]
    if not path.is_file():
        return {}
    elements = TABLES[kind]["elements"]
    out: dict[int, str] = {}
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError as error:
        print(f"  ! {path} 解析失败：{error}", file=sys.stderr)
        return {}
    for element in root.iter():
        tag = element.tag.split("}")[-1]
        if tag not in elements:
            continue
        raw = element.get("name")
        identifier = element.get("id")
        if raw is None or identifier is None:
            continue
        try:
            value = int(identifier)
        except ValueError:
            continue
        name = raw
        if name.startswith("#"):
            name = stringtable.get(name[1:], "")
        if name:
            out[value] = name
    return out


def import_xml(game_dir: pathlib.Path) -> None:
    rp = game_dir / "rp_patch" / "resources"
    base = game_dir / "resources"
    if not rp.is_dir():
        raise SystemExit(f"找不到 {rp}（--import-xml 要给到 `Program #0/1` 这一层）")
    stringtable = parse_stringtable(rp / "stringtable.sta")
    print(f"stringtable 键数 = {len(stringtable)}")

    SOURCE_DIR.mkdir(parents=True, exist_ok=True)
    for kind, meta in TABLES.items():
        merged: dict[int, str] = {}
        rp_entries = collect_entries(rp, kind, stringtable)
        merged.update(rp_entries)
        base_entries = collect_entries(base, kind, {})
        # base 的英文名优先（同一 id）：它是原文，不是本地化键解析出来的。
        for identifier, name in base_entries.items():
            if not name.startswith("#"):
                merged[identifier] = name
        # 名字唯一化。角色表例外：`players.xml` 里 id 21..40 是堕落角色、
        # 名字与本体（0..20）**逐字重复** ⇒ 那 21 条同时保留「本体编号」与「堕落编号」两列
        # （`Isaac.GetPlayerTypeByName(name, Tainted)` 的第二个参数就靠它）。
        # 其余表同名只取第一次出现（按 id 升序），与实体名表同一口径。
        by_name: dict[str, list[int]] = {}
        for identifier in sorted(merged):
            by_name.setdefault(merged[identifier], []).append(identifier)
        rows: list[tuple[str, int, int]] = []
        for name, identifiers in by_name.items():
            if kind == "player_type" and len(identifiers) >= 2:
                rows.append((name, identifiers[0], identifiers[1]))
            else:
                rows.append((name, identifiers[0], -1))
        rows.sort(key=lambda item: item[0])
        target = SOURCE_DIR / meta["file"]
        escaped = escape_name
        body = [
            f"# 由 tools/generate_isaac_name_tables.py --import-xml 从游戏 dump 提取。",
            f"# 来源：rp_patch/resources/{XML_FILES[kind]}（编号+键，权威）"
            f" + resources/{XML_FILES[kind]}（补英文原文）",
            f"#       + rp_patch/resources/stringtable.sta（键 → 英文；"
            f"★ 语言位置要剔除 `Key` 伪语言那一档，见 `parse_stringtable` 的注释）。",
            f"# 格式：名字<TAB>编号[<TAB>堕落编号]，按名字升序。用途：{meta['api']}"
            f"（PC 契约 {meta['doc']}）。",
            f"# 第三列只有角色表有（`players.xml` 的 id 21..40 是堕落角色、名字与本体重复）。",
            f"# 名字里的反斜杠/制表符/换行/回车/问号已转义（`\\\\` / `\\t` / `\\n` / `\\r` / `\\?`）。",
        ]
        for name, identifier, alternate in rows:
            fields = [escaped(name), str(identifier)]
            if alternate >= 0:
                fields.append(str(alternate))
            body.append("\t".join(fields))
        target.write_text("\n".join(body) + "\n", encoding="utf-8")
        print(f"  已写 {target.relative_to(ROOT)}：{len(rows)} 条"
              f"（rp {len(rp_entries)} + base 补 {len(rows) - len(rp_entries)}）")


# --------------------------------------------------------------------------- #
# 生成
# --------------------------------------------------------------------------- #

def read_source(kind: str) -> list[tuple[str, int, int]]:
    """读源数据 → `[(名字, 编号, 堕落编号)]`（没有第三列时堕落编号是 `-1`）。"""
    path = SOURCE_DIR / TABLES[kind]["file"]
    if not path.is_file():
        raise SystemExit(f"缺 {path.relative_to(ROOT)}：先在有游戏 dump 的机器上跑 --import-xml")
    rows: list[tuple[str, int, int]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        fields = line.split("\t")
        if len(fields) < 2:
            continue
        name = fields[0]
        rows.append((name, int(fields[1]), int(fields[2]) if len(fields) > 2 else -1))
    return rows


def render_header() -> str:
    kinds = list(TABLES)
    lines = [
        "#pragma once",
        "",
        "// 由 `tools/generate_isaac_name_tables.py` 从 `tools/isaac_name_source/*.txt` 生成 —— **不要手改**。",
        "// 表是「本体 XML + stringtable 的静态快照」，来源、拼法与已知偏离见生成器的文档头。",
        "//",
        "// 用途（PC 契约逐条见 `tools/pc_contract_docs/Isaac.md`）：",
    ]
    for kind in kinds:
        meta = TABLES[kind]
        lines.append(f"//   * `{meta['api']}`（{meta['doc']}）")
    lines += [
        "//",
        "// ★ 为什么不用「遍历引擎的 ItemConfig 比名字」：Switch 叠加层里 `rp_patch/resources/items.xml`",
        "//   的 960 条名字里 911 条是本地化键（`#THE_SAD_ONION_NAME`）⇒ 运行时 `ItemConfig_Item.Name`",
        "//   读到的是**键**，拿 `Brimstone` 这种原文去比永远不中。",
        "",
        "#include <cstddef>",
        "#include <cstdint>",
        "",
        "namespace isaac::runtime {",
        "",
        "//: 名字表的选择器（下标就是 `kIsaacNameTables` 的位置，**只能在末尾追加**）。",
        "enum class IsaacNameKind : std::uint8_t {",
    ]
    for index, kind in enumerate(kinds):
        lines.append(f"    {''.join(part.capitalize() for part in kind.split('_'))} = {index},")
    lines += [
        "};",
        "",
        "//: 一行 = 一个名字。`nameOffset` 是它在名字块（`'\\0'` 分隔）里的字节下标。",
        "//: `id` 用**有符号** —— 查不到时要返回 `-1`（PC 契约明文）。",
        "//: `alternateId` 目前只服务 `Isaac.GetPlayerTypeByName(name, Tainted)`：",
        "//: `players.xml` 里 id 21..40 是**堕落角色**、名字与本体（0..20）逐字重复 ⇒",
        "//: 同一个名字存两格（本体 / 堕落）；其余表恒为 `-1`。",
        "struct IsaacNameEntry {",
        "    std::uint32_t nameOffset;",
        "    std::int32_t id;",
        "    std::int32_t alternateId;",
        "};",
        "",
        "//: 一张表 = 名字块 + 条目表 + 条数。",
        "struct IsaacNameTable {",
        "    const char* blob;",
        "    const IsaacNameEntry* entries;",
        "    std::size_t count;",
        "};",
        "",
        "//: 全部名字表（下标 = `IsaacNameKind` 的值）。`count` 通过出参给出。",
        "[[nodiscard]] const IsaacNameTable* IsaacNameTables(std::size_t* count) noexcept;",
        "",
        "//: 在 `kind` 那张表里按名字查编号（**逐字节比较**，与引擎/契约同一口径）。",
        "//: `alternate` = true 时取 `alternateId`（目前只有角色表的堕落角色会用到）。",
        "//: 命中返回编号，**未命中返回 `-1`**（PC 契约：这几条 API 找不到都是 `-1`，不是 `nil`）。",
        "[[nodiscard]] std::int32_t LookupIsaacName(IsaacNameKind kind, const char* name,",
        "                                           std::size_t length,",
        "                                           bool alternate = false) noexcept;",
        "",
        "} // namespace isaac::runtime",
    ]
    return "\n".join(lines) + "\n"


def render_impl() -> str:
    kinds = list(TABLES)
    blobs: list[str] = []
    entries: list[str] = []
    table_rows: list[str] = []
    for kind in kinds:
        rows = read_source(kind)          # 名字是**已转义**的源文本
        camel = "".join(part.capitalize() for part in kind.split("_"))
        # 字面量直接用源文本（已转义）；长度必须用解码后的名字（见 `unescape_name` 的注释）。
        pieces = [name + "\\0" for name, _, _ in rows]
        content_bytes = sum(len(unescape_name(name).encode("utf-8")) + 1 for name, _, _ in rows)
        blobs.append(f"//: `{TABLES[kind]['api']}` 的名字块（{len(rows)} 条，按名字升序）。")
        blobs.append(f"constexpr char k{camel}NameBlob[{content_bytes + 1}] = {{")
        for piece in pieces:
            blobs.append(f'    "{piece}"')
        blobs.append("};")
        blobs.append("")
        entries.append(f"//: `{TABLES[kind]['api']}` 的条目表（与上面名字块一一对应）。")
        entries.append(f"constexpr IsaacNameEntry k{camel}NameEntries[] = {{")
        offset = 0
        for name, identifier, alternate in rows:
            entries.append(f"    {{{offset}, {identifier}, {alternate}}},")
            offset += len(unescape_name(name).encode("utf-8")) + 1
        entries.append("};")
        entries.append("")
        table_rows.append(f"    {{k{camel}NameBlob, k{camel}NameEntries, "
                          f"sizeof(k{camel}NameEntries) / sizeof(k{camel}NameEntries[0])}},")

    lines = [
        "// 由 `tools/generate_isaac_name_tables.py` 从 `tools/isaac_name_source/*.txt` 生成 —— **不要手改**。",
        "",
        '#include "program/isaac_name_tables.hpp"',
        "",
        "#include <cstring>",
        "",
        "namespace isaac::runtime {",
        "namespace {",
        "",
    ]
    lines += blobs
    lines += entries
    lines += [
        "//: 名字块按名字升序 ⇒ 下面的查找走**二分**（表最大 960 条，无脑线性扫也能过，",
        "//: 但二分让「每帧查几次」的模组不吃亏；前提是同一份升序，见生成器的排序）。",
        "constexpr IsaacNameTable kIsaacNameTables[] = {",
    ]
    lines += table_rows
    lines += [
        "};",
        "",
        "std::int32_t LookupInTable(const IsaacNameTable& table, const char* name,",
        "                           std::size_t length, bool alternate) noexcept {",
        "    std::size_t low = 0;",
        "    std::size_t high = table.count;",
        "    while (low < high) {",
        "        const std::size_t middle = low + (high - low) / 2;",
        "        const char* candidate = table.blob + table.entries[middle].nameOffset;",
        "        const std::size_t candidate_length = std::strlen(candidate);",
        "        const std::size_t shorter = length < candidate_length ? length : candidate_length;",
        "        const int order = std::memcmp(name, candidate, shorter);",
        "        // 前缀相同时短的那个排在前面（与生成器的字典序一致）。",
        "        const int verdict = order != 0 ? order",
        "                                       : (length < candidate_length ? -1",
        "                                          : (length > candidate_length ? 1 : 0));",
        "        if (verdict == 0) {",
        "            return alternate ? table.entries[middle].alternateId",
        "                             : table.entries[middle].id;",
        "        }",
        "        if (verdict < 0) {",
        "            high = middle;",
        "        } else {",
        "            low = middle + 1;",
        "        }",
        "    }",
        "    return -1;",
        "}",
        "",
        "} // namespace",
        "",
        "const IsaacNameTable* IsaacNameTables(std::size_t* count) noexcept {",
        "    if (count != nullptr) {",
        "        *count = sizeof(kIsaacNameTables) / sizeof(kIsaacNameTables[0]);",
        "    }",
        "    return kIsaacNameTables;",
        "}",
        "",
        "std::int32_t LookupIsaacName(IsaacNameKind kind, const char* name,",
        "                             std::size_t length, bool alternate) noexcept {",
        "    std::size_t count = 0;",
        "    const IsaacNameTable* tables = IsaacNameTables(&count);",
        "    const auto index = static_cast<std::size_t>(kind);",
        "    if (tables == nullptr || name == nullptr || length == 0 || index >= count) {",
        "        return -1;",
        "    }",
        "    return LookupInTable(tables[index], name, length, alternate);",
        "}",
        "",
        "} // namespace isaac::runtime",
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--import-xml", metavar="DIR",
                    help="从游戏 dump 的 `Program #0/1` 目录提取名字表（维护动作）")
    ap.add_argument("--write", action="store_true", help="由源数据生成 C++（默认动作）")
    ap.add_argument("--check", action="store_true", help="只核对生成物是否与源数据一致")
    args = ap.parse_args()

    if args.import_xml:
        import_xml(pathlib.Path(args.import_xml))
        if not args.write:
            return 0

    header = render_header()
    impl = render_impl()
    if args.check:
        problems = []
        for path, expected in ((HEADER, header), (IMPL, impl)):
            if not path.is_file():
                problems.append(f"{path.relative_to(ROOT)} 不存在")
            elif path.read_text(encoding="utf-8") != expected:
                problems.append(f"{path.relative_to(ROOT)} 与源数据不一致（重跑 --write）")
        for problem in problems:
            print(f"  ✗ {problem}", file=sys.stderr)
        return 1 if problems else 0

    HEADER.parent.mkdir(parents=True, exist_ok=True)
    HEADER.write_text(header, encoding="utf-8")
    IMPL.write_text(impl, encoding="utf-8")
    total = sum(len(read_source(kind)) for kind in TABLES)
    print(f"已写 {HEADER.relative_to(ROOT)} / {IMPL.relative_to(ROOT)}：共 {total} 条")
    for kind in TABLES:
        print(f"    {TABLES[kind]['file']:22s} {len(read_source(kind)):5d} 条  →  {TABLES[kind]['api']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
