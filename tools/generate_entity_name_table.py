#!/usr/bin/env python3
"""生成"实体名 → (Type, Variant)"查表（`runtime/source/program/entity_name_table.*`）。

## 为什么需要它（2026-09-29 批次 207）

MCM（Mod Config Menu）在 `PostGameStarted` 里就调
`Isaac.GetEntityTypeByName("Potato Dummy")` / `Isaac.GetEntityVariantByName("Potato Dummy")`
（`analysis/mod-corpus/isaac-mod-config-menu/scripts/modconfig.lua:260/261`）。
这两条 API 在我们这边**根本不存在** ⇒ "attempt to call a nil value" ⇒ 那一段直接抛错。
PC 契约：`tools/pc_contract_docs/Isaac.md:218`（`GetEntityTypeByName` 找不到返回 `0`）、
`:235`（`GetEntityVariantByName` 找不到返回 `-1`）。

## 数据从哪来 / 为什么源文件在仓库里

本体的 `entities2.xml` **不在仓库里**（`The Binding of Isaac_ Afterbirth+ …` 整个目录被
`.gitignore` 挡掉，是用户的游戏 dump）。这与 `pc_lua_enum_data`（输入是用户 PC 本体的
`enums.lua`）当年遇到的困境一模一样：**输入不在仓库 ⇒ 这一类工作对任何其他人都不可做**。

所以本批按 `tools/pc_enum_docs/` 的先例办：把**提取出来的名字表**作为
`tools/entity_name_source.txt` 进仓库（逐行 `名字<TAB>Type<TAB>Variant`、按名字排序），
生成器只做"文本 → C++"，于是：

* 生成物**在任何干净检出里都可复核**（门禁 `test_entity_name_table.py` 跑 `--check`）；
* 重新提取（`--import-xml`）只在有游戏 dump 的机器上做，属于维护动作，不进门禁。

## 两份 XML 的关系（2026-09-29 实测，决定了这个表怎么拼）

Switch romfs 里有两份：`Program #0/1/resources/entities2.xml`（763 条，**AB+ 英文名**）与
`Program #0/1/rp_patch/resources/entities2.xml`（1337 条，**Repentance 名，很多是本地化键**
形如 `#BOIL`）。实测两者的 `(id, variant)` 键集合是**包含关系**（base 的 701 个键 rp 全有，
rp 多出 436 个），而**同键另有 331 条名字不同**（`Lokii` → `#LOKII`）。

⇒ 拼法：**base 的英文名全部保留**（那是模组真正会去查的名字，例如 `Lokii`），
**再加 rp 里 base 没有的键**（Repentance 新增实体，只有 `#KEY` 形式的名字）。
名字唯一化：同名取第一次出现（base 优先）。

## 已知偏离（写在明处）

* **只看得到本体 XML 里的名字**。PC 上模组可以在 `content/entities2.xml` 里加实体，
  那时 PC 的 `GetEntityTypeByName("模组实体名")` 能查到、我们查不到（返回 `0`/`-1`）。
  ⇒ 这正是 MCM 那个 `"Potato Dummy"` 的情形：那名字**只在 MCM 自己的代码里出现**
  （全仓库扫描过），是它留给"某个装了土豆假人的模组"的兼容分支 ⇒ 我们与本体 PC 一样返回
  `0` / `-1`，MCM 的 `if potatoType and potatoVariant > 0` 自然走"没有"那一支。
* 因此这张表**不是**"引擎的实体配置"，而是"本体 XML 的静态快照"。名字表随 DLC/补丁变化时
  要重新 `--import-xml`。

## 名字里的怪字符（三个坑，都在生成器里堵住了）

1. **制表符**：`name="Telekinesis<TAB>Halo"` —— 不转义的话，`entity_name_source.txt`
   的分隔符就废了（一行解析出四个字段）。
2. **字面量尺寸**：`"Player\0"` 在数组里占 **7** 字节（6 字符 + 显式 `\0`），
   下标按 `len(名字 UTF-8 字节) + 1` 累加。
   ★ **不是 `+2`**：相邻的字符串字面量在 C++ 里先拼接，隐式结尾 `\0` 只有整串末尾一个。
   这里算错过一次（把 `+2` 当公式），后果见 `render_implementation()` 的修正说明。
   ★ 另：**数组声明的大小 = 内容字节数 + 1** —— C++ 不允许 `char[N]` 把字面量的隐式结尾 `\0`
   丢掉（C 允许），尾后要多留一格。这一条同样是编译打回来才补上的。
3. **`?`**：`???'s Only Friend` 里的 `???` 是 C++ 的历史三字符组（trigraph），
   C++17 才删掉、编译器仍报 `-Wtrigraphs`，本项目全量 `-Werror` ⇒ 必须写成 `\\?`
   （标准里的简单转义序列，语义与 `?` 相同）。
4. **XML 实体引用**：`name="Mom&apos;s Chest"` —— XML 解析器会还原成 `Mom's Chest`。
   我们的属性正则**不会**，所以 `parse_xml()` 必须自己走一遍 `unescape_xml()`；
   漏了它，这一类名字（rp_patch 里 33 个）在我们这边就查不到。

## 用法

    python3 tools/generate_entity_name_table.py --write
    python3 tools/generate_entity_name_table.py --check
    python3 tools/generate_entity_name_table.py --import-xml "<romfs 的 Program #0/1 目录>"
"""

from __future__ import annotations

import argparse
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
SOURCE = ROOT / "tools" / "entity_name_source.txt"
HEADER = ROOT / "runtime" / "source" / "program" / "entity_name_table.hpp"
IMPLEMENTATION = ROOT / "runtime" / "source" / "program" / "entity_name_table.cpp"

#: `entities2.xml` 里我们真正要的两个属性（`name` 与 `id`），外加 `variant`。
_ATTRIBUTE_RE = re.compile(r'\b(name|id|variant)="([^"]*)"')

#: XML 的**预定义实体引用** + 数字字符引用。XML 规范里只有这五种具名实体，
#: 所以这里**不用** `html.unescape()` —— 那会多认 `&nbsp;`/`&copy;` 之类的 HTML 具名实体，
#: 把 XML 里字面上就该叫 `&copy;` 的名字改掉。
_XML_ENTITY_RE = re.compile(r"&(#x[0-9A-Fa-f]+|#[0-9]+|amp|lt|gt|quot|apos);")
_XML_NAMED_ENTITIES = {"amp": "&", "lt": "<", "gt": ">", "quot": '"', "apos": "'"}


def unescape_xml(text: str) -> str:
    """把 XML 属性值里的实体引用还原成真字符。

    ★ 第四个坑（2026-09-29 修）：`name` 属性里**真的有** `&apos;` ——
      `rp_patch/resources/entities2.xml` 有 33 处、全都落在 `name` 上（base 里 0 处，
      全库扫描确认，见 `tools/entity_name_source.txt` 那一批名字）。
      原始 XML 文本是 `name="Mom&apos;s Chest"`，**XML 解析器会还原成** `Mom's Chest`，
      而本函数上面那个正则式解析器只做属性提取、不做反转义 ⇒ 名字块里存的是
      **4 个字节的 `&apos;` 字面量**。
      后果是这一类名字在我们这边**查不到**（`GetEntityTypeByName("Mom's Chest")` 答 0），
      而 PC 上能查到 —— 与"名字表是本体 XML 的快照"这个前提直接冲突。
    """
    def replace(match: re.Match[str]) -> str:
        body = match.group(1)
        if body[:2] in ("#x", "#X"):
            return chr(int(body[2:], 16))
        if body.startswith("#"):
            return chr(int(body[1:]))
        return _XML_NAMED_ENTITIES[body]

    return _XML_ENTITY_RE.sub(replace, text)


def parse_xml(path: pathlib.Path) -> list[tuple[str, int, int]]:
    """把一份 `entities2.xml` 读成 `[(name, type, variant)]`。"""
    text = path.read_text(encoding="utf-8", errors="replace")
    rows: list[tuple[str, int, int]] = []
    for match in re.finditer(r"<entity\s([^>]*)>", text):
        attributes = dict(_ATTRIBUTE_RE.findall(match.group(1)))
        name = attributes.get("name")
        if not name:
            continue
        # `id`/`variant` 是纯数字、不含实体引用；只有 `name` 要反转义。
        rows.append((unescape_xml(name), int(attributes["id"]),
                     int(attributes.get("variant", "0"))))
    return rows


def merge(names: list[str]) -> list[tuple[str, int, int]]:
    """按 `--import-xml` 给的顺序拼表：第一个文件的名字优先，后面的只补新键。

    `names` 是 `Program #0/1` 目录下的两份 XML 路径（先 base、后 rp_patch）。
    """
    merged: dict[str, tuple[str, int, int]] = {}
    seen_keys: set[tuple[int, int]] = set()
    for index, relative in enumerate(names):
        for row in parse_xml(pathlib.Path(relative)):
            key = (row[1], row[2])
            if index == 0:
                # base：英文名全部收，且记住这些键已经被"英文名"覆盖过。
                seen_keys.add(key)
                merged.setdefault(row[0], row)
            elif key not in seen_keys:
                # rp_patch：只补 base 里没有的键（Repentance 新增实体）。
                merged.setdefault(row[0], row)
    return sorted(merged.values(), key=lambda row: row[0])


def escape_name(name: str) -> str:
    """把名字写进 `entity_name_source.txt` 时的转义。

    ★ 必须转义制表符：本体 XML 里**真的有带制表符的名字** ——
    `name="Telekinesis<TAB>Halo"`（`rp_patch/resources/entities2.xml:3399`，
    `anm2path="1000.123_Halo (Telekinesis).anm2"`）。直接用 `<TAB>` 当分隔符
    会在那一行解析出四个字段（2026-09-29 第一次生成时就是这么炸的）。

    ★ 也要转义 `?`：见 `render_implementation()` 里那条"三字符组"的说明 ——
    两处必须**用同一套转义规则**（`unescape_name()` 是这里的逆），
    否则 `--import-xml` 写出的源文件与 `--check` 期望的对不上。
    """
    return (name.replace("\\", "\\\\").replace("\t", "\\t")
                .replace("\n", "\\n").replace("\r", "\\r")
                .replace("?", "\\?"))


def unescape_name(text: str) -> str:
    out: list[str] = []
    index = 0
    while index < len(text):
        character = text[index]
        if character == "\\" and index + 1 < len(text):
            following = text[index + 1]
            out.append({"t": "\t", "n": "\n", "r": "\r", "\\": "\\"}.get(following, following))
            index += 2
            continue
        out.append(character)
        index += 1
    return "".join(out)


def read_source() -> list[tuple[str, int, int]]:
    rows: list[tuple[str, int, int]] = []
    for line in SOURCE.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        name, type_text, variant_text = line.split("\t")
        rows.append((unescape_name(name), int(type_text), int(variant_text)))
    return rows


def render_header() -> str:
    return """#pragma once

// 由 `tools/generate_entity_name_table.py` 从 `tools/entity_name_source.txt` 生成 —— **不要手改**。
// 表本身是"本体 `entities2.xml` 的静态快照"，来源与拼法见生成器的文档头。
//
// 用途：`Isaac.GetEntityTypeByName(name)` / `GetEntityVariantByName(name)`
// （PC 契约 `tools/pc_contract_docs/Isaac.md:218/235`；消费方 MCM 的
// `scripts/modconfig.lua:260/261`）。

#include <cstddef>
#include <cstdint>

namespace isaac::runtime {

//: 一行 = 一个实体名。`nameOffset` 是它在名字块（`'\\0'` 分隔）里的字节下标。
//:
//: `type` 用 `std::uint16_t`：本体的实体编号远小于 65535（最大约 `0x3DD`）。
//: `variant` 用 **`std::int16_t`** 而不是无符号 —— `GetEntityVariantByName` 查不到时要返回
//: `-1`（PC 契约 `Isaac.md:235`），用无符号就得额外走一条特例分支。
struct EntityNameEntry {
    std::uint32_t nameOffset;
    std::uint16_t type;
    std::int16_t variant;
};

//: 名字块（`'\\0'` 分隔、按名字升序，与 `EntityNameEntries()` 一一对应）。
[[nodiscard]] const char* EntityNameBlob() noexcept;

//: 名字条目表（**按名字升序**，查找用二分）。`count` 通过出参给出。
[[nodiscard]] const EntityNameEntry* EntityNameEntries(std::size_t* count) noexcept;

} // namespace isaac::runtime
"""


def escape_cpp_literal(name: str) -> str:
    """把名字写进 C++ 字符串字面量时的转义。

    ★ 第三个坑（2026-09-29 修）：**`?` 也必须转义成 `\\?`**。
      C++ 里连续两个 `?` 的历史三字符组（trigraph）规则到 C++17 才被删掉，
      编译器仍会为已废弃的写法报 `-Wtrigraphs`；本项目全量 `-Werror`
      ⇒ `entity_name_source.txt` 里那条 `???'s Only Friend`（本体 933 号变体
      "Sister Maggy / ???" 的口径）直接让宿主编译失败：
      `error: trigraph ignored [-Werror,-Wtrigraphs]`。
      `\\?` 是标准里的简单转义序列，与写 `?` 语义完全一致。

    沿用 `escape_name()` 的其余规则（反斜杠、制表符、换行、回车），
    保证"源文件里长什么样"与"源码里长什么样"一一对应。
    """
    return escape_name(name).replace('"', '\\"')


def render_implementation(rows: list[tuple[str, int, int]]) -> str:
    """生成实现文件。

    ★ **每条名字在数组里占 `len(名字 UTF-8 字节) + 1` 个字节**（自己的显式 `\\0`）。
      相邻的字符串字面量在 C++ 里是**先拼接**的 —— 隐式结尾 `\\0` 只有**整串末尾一个**，
      **不是每片一个**。

    ★★ 2026-09-29 修正（宿主行为测试抓到的一个**真功能缺陷**）：第一版按 `len + 2` 累加
      （以为每片各带一个隐式 `\\0`），于是**第一条之外的名字下标全部偏大**（第 i 条偏 i 字节）
      ⇒ 二分查找按错位的下标 `strcmp`，读到的都是别人的名字 ⇒
      `Isaac.GetEntityTypeByName("Monstro")` **恒返回 0**（而且不报错 —— 模组的
      `if t > 0` 判断静默走错分支）。
      抓到它的是 `runtime/tests/test_lua_api_gap_mcm.py`（伪造内存 + 真 Lua 状态机，
      断言 `Monstro → 20`、`Lokii → (69, 1)`）；本文件自己的门禁当时**没抓住**，因为它
      把同一个错误模型抄了一遍（"每片后面补一个 `\\0`"）⇒ 已一并改成按拼接语义算。

    ★ 转义走 `escape_cpp_literal()`：**不要在这里另写一条转义链**，
      `?`（三字符组）与制表符两个坑都是在那里一次说清的。
      注意转义只改"怎么写"、**不改字节数**（`\\?` 在源码里是 2 个字符、在数组里仍是 1 字节）
      ⇒ 下面 `len(name.encode("utf-8")) + 1` 依旧成立。

    ★ **数组声明的大小 = 内容字节数 `+ 1`**（2026-09-29，宿主编译抓到）：内容里已经每条名字
      自带一个显式 `\\0`，但 C++ **不允许** `char[N] = "字面量"` 把字面量自带的隐式结尾 `\\0`
      丢掉（C 允许，C++ 从 C++11 起是硬错误），所以数组必须再多留一格：
      `error: initializer-string for char array is too long, array size is 13348 but
      initializer has size 13349 (including the null terminating character)`。
      多出来的这一格在最后一条名字的 `\\0` 之后，**永远读不到**（`strcmp` 型查找到此为止），
      留着纯粹是让声明合法、并且把"内容 13348"与"声明 13349"两个数都钉在生成物里。
    """
    emitted: list[tuple[str, int]] = []
    for name, _, _ in rows:
        emitted.append((escape_cpp_literal(name), len(name.encode("utf-8")) + 1))

    offsets: list[int] = []
    offset = 0
    for _, length in emitted:
        offsets.append(offset)
        offset += length
    content_bytes = offset
    #: 内容 + 字面量自带的隐式结尾 `\0`（见上面那段说明）。
    declared_bytes = content_bytes + 1

    lines = [
        "// 由 `tools/generate_entity_name_table.py` 从 `tools/entity_name_source.txt` 生成 —— **不要手改**。",
        "",
        '#include "program/entity_name_table.hpp"',
        "",
        "namespace isaac::runtime {",
        "namespace {",
        "",
        "//: 名字块：每条名字后跟 `'\\0'`。写法用**字符串字面量拼接**而不是显式字符表 ——",
        "//: 可读性差一点点，但每条名字在数组里占的字节数有确定公式（`len(名字) + 1`：",
        "//: 只有显式的分隔 `\\0`）。★ 注意相邻的字符串字面量在 C++ 里**先拼接**，",
        "//: 隐式结尾 `\\0` 只有**整串末尾一个**、**不是每片一个** —— 这一点算错过一次，",
        "//: 后果是第一条之外的名字下标全部偏大、`GetEntityTypeByName` 恒返回 0。",
        "//: ★ 声明的大小 = 内容字节数 + 1：C++ 不允许丢掉字面量的隐式结尾 `\\0`，",
        f"//: 所以尾后多一格（内容 {content_bytes}、声明 {declared_bytes}）。",
        f"constexpr char kEntityNameBlob[{declared_bytes}] = {{",
    ]
    for escaped, _ in emitted:
        lines.append(f'    "{escaped}\\0"')
    lines.append("};")
    lines.append("")
    lines.append("//: 与名字块一一对应（`nameOffset` 是块内下标）。**按名字升序** ⇒ 可以二分。")
    lines.append(f"constexpr EntityNameEntry kEntityNameEntries[{len(rows)}] = {{")
    for (name, type_number, variant), name_offset in zip(rows, offsets):
        # 注释里同样转义 `?`：三字符组替换发生在**词法分析之前**，
        # 注释也在其射程内（`??'` 是 `^` 的三字符组）。Apple clang 17 在注释里不报，
        # 但 devkitPro 那个 clang 不保证 ⇒ 不赌，注释与字面量用同一套转义。
        lines.append(f"    {{{name_offset}, {type_number}, {variant}}},  // {escape_cpp_literal(name)}")
    lines.append("};")
    lines.append("")
    lines.append("} // namespace")
    lines.append("")
    lines.append("const char* EntityNameBlob() noexcept { return kEntityNameBlob; }")
    lines.append("")
    lines.append("const EntityNameEntry* EntityNameEntries(std::size_t* count) noexcept {")
    lines.append("    if (count != nullptr) {")
    lines.append("        *count = sizeof(kEntityNameEntries) / sizeof(kEntityNameEntries[0]);")
    lines.append("    }")
    lines.append("    return kEntityNameEntries;")
    lines.append("}")
    lines.append("")
    lines.append("} // namespace isaac::runtime")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="写出生成物")
    parser.add_argument("--check", action="store_true", help="只比对，不一致就退 1")
    parser.add_argument("--import-xml", nargs=2, metavar=("BASE_XML", "RP_PATCH_XML"),
                        help="从游戏 dump 的两份 entities2.xml 重新提取 tools/entity_name_source.txt")
    arguments = parser.parse_args()

    if arguments.import_xml:
        rows = merge(list(arguments.import_xml))
        SOURCE.write_text(
            "# 由 `tools/generate_entity_name_table.py --import-xml` 从游戏 dump 的\n"
            "# `resources/entities2.xml` + `rp_patch/resources/entities2.xml` 提取。\n"
            "# 格式：名字<TAB>Type<TAB>Variant，按名字升序。拼法（base 优先、rp 补新键）见生成器文档头。\n"
            "# 名字里的反斜杠/制表符/换行/回车/问号已转义（`\\\\` / `\\t` / `\\n` / `\\r` / `\\?`；\n"
            "# 问号是躲 C++ 的历史三字符组，见生成器文档头）。\n"
            + "".join(f"{escape_name(name)}\t{type_number}\t{variant}\n"
                      for name, type_number, variant in rows),
            encoding="utf-8")
        print(f"已写 {SOURCE}（{len(rows)} 条）")
        return 0

    rows = read_source()
    expected_header = render_header()
    expected_implementation = render_implementation(rows)

    if arguments.check:
        problems = []
        for path, expected in ((HEADER, expected_header), (IMPLEMENTATION, expected_implementation)):
            actual = path.read_text(encoding="utf-8") if path.exists() else ""
            if actual != expected:
                problems.append(str(path))
        if problems:
            print("生成物与 tools/entity_name_source.txt 不一致：", file=sys.stderr)
            for path in problems:
                print(f"  - {path}", file=sys.stderr)
            print("跑 `python3 tools/generate_entity_name_table.py --write` 重新生成。", file=sys.stderr)
            return 1
        print(f"ok：生成物与源一致（{len(rows)} 条）")
        return 0

    if not arguments.write:
        parser.error("要么 --write、要么 --check、要么 --import-xml")

    HEADER.parent.mkdir(parents=True, exist_ok=True)
    HEADER.write_text(expected_header, encoding="utf-8")
    IMPLEMENTATION.write_text(expected_implementation, encoding="utf-8")
    print(f"已写 {HEADER} 与 {IMPLEMENTATION}（{len(rows)} 条）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
