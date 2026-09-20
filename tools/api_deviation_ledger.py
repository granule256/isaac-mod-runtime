#!/usr/bin/env python3
"""读 `api_deviation.cpp` 那张**偏离台账**：谁还在返回兜底/近似值、后果是什么、判据在哪。

## 为什么需要它（2026-09-20 批次 099，由 098 那次事故推动）

098 的教训：我们的 `Room:GetGridPath` 是个**恒返回常量**的占位，而 EID 拿它当"这块能不能走"的
真值 ⇒ 地上每一颗药丸、每一张卡片都被判"够不到"、只画问号（用户可见）。台账里**其实登记过**这条，
但"偏离后果"那一栏写的是"不画路径提示"——**写错了**，而且没有任何东西逼着人把它写对、
也没有任何东西让它在日常读数里露面。

⇒ 所以这份台账要变成三件事的共同来源：

* **门禁**（`runtime/tests/contract/test_api_deviation.py`）：每条必须写"偏离后果"，
  并且必须给出"判据：<仓库里的测试文件>"（缺失的条数被钉住、只能降不能升）；
* **读数**（`tools/read_device_state_via_gdb.py`）：每次真机读数都把"还在返回兜底值的接口"
  连同后果打印出来 —— 风险面摊开在眼前，而不是等人踩上去；
* **本模块**：上面两处共用同一个解析口径（不许各写一套正则）。

条目形状（`api_deviation.cpp` 里的表体）：

    {0x04010006,
     ApiDeviationKind::Partial,
     "……偏离后果：……"
     "判据：runtime/tests/test_lua_room_grid.py（钉越界口径）"},

正文可能由多个相邻字符串字面量拼成，解析时按 C++ 的拼接规则连起来。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEVIATIONS = ROOT / "runtime" / "src" / "interfaces" / "lua" / "api_deviation.cpp"

#: 允许的种类（与 C++ 侧 `ApiDeviationKind` 一致）。
KINDS = ("Partial", "Placeholder", "NotInEngine")

#: 台账里两个**必填**字段的标记词。门禁按它们判"写了没有"。
CONSEQUENCE_MARKER = "偏离后果："
JUDGEMENT_MARKER = "判据："

#: 判据可以写成"暂无（理由…）"—— 那表示"这条偏离目前没有可执行判据"，
#: 属于**欠账**：条数被门禁钉住，只能降不能升。
NO_JUDGEMENT_PREFIX = "暂无"

ENTRY_PATTERN = re.compile(
    r"\{\s*(0x[0-9A-Fa-f]+)\s*,\s*ApiDeviationKind::(\w+)\s*,(.*?)\}\s*,", re.S)
STRING_PATTERN = re.compile(r'"((?:[^"\\]|\\.)*)"')
JUDGEMENT_PATH_PATTERN = re.compile(r"(?:runtime/)?tests/[A-Za-z0-9_./-]+\.py")


@dataclass(frozen=True)
class DeviationEntry:
    """台账里的一条：id（十六进制整数）、种类、正文。"""

    identifier: int
    kind: str
    text: str

    @property
    def has_consequence(self) -> bool:
        return CONSEQUENCE_MARKER in self.text

    @property
    def consequence(self) -> str:
        """`偏离后果：` 之后、`判据：` 之前的那段（没写就返回空串 —— 门禁据此判红）。"""
        index = self.text.find(CONSEQUENCE_MARKER)
        if index < 0:
            return ""
        tail = self.text[index + len(CONSEQUENCE_MARKER):]
        cut = tail.find(JUDGEMENT_MARKER)
        if cut >= 0:
            tail = tail[:cut]
        return tail.strip()

    @property
    def judgement(self) -> str:
        """`判据：` 之后的那段（没写就返回空串）。"""
        index = self.text.find(JUDGEMENT_MARKER)
        if index < 0:
            return ""
        return self.text[index + len(JUDGEMENT_MARKER):].strip()

    @property
    def is_placeholder_kind(self) -> bool:
        return self.kind == "Placeholder"

    @property
    def judgement_paths(self) -> list[str]:
        """判据里引用的仓库内测试文件（相对仓库根）。"""
        return sorted(set(JUDGEMENT_PATH_PATTERN.findall(self.judgement)))

    @property
    def judgement_missing(self) -> bool:
        """判据是"暂无…"（欠账）或干脆没写。"""
        judgement = self.judgement
        return not judgement or judgement.startswith(NO_JUDGEMENT_PREFIX)


def _unescape(literal: str) -> str:
    """C++ 字面量里的转义还原（**只处理我们真会用到的那几个**）。

    不能用 `unicode_escape`：那会把中文按 latin-1 拆坏。台账正文里出现的转义只有
    `\\"`（判据里引用的接口名）与 `\\\\` 两种，逐个替换即可。
    """
    return literal.replace('\\"', '"').replace("\\n", "\n").replace("\\\\", "\\")


def load_entries(path: Path | None = None) -> list[DeviationEntry]:
    """解析整张台账。表体从第一个 `{0x` 开始 —— 之前的注释不属于条目。"""
    text = (path or DEVIATIONS).read_text(encoding="utf-8")
    start = text.find("{0x")
    if start < 0:
        raise ValueError(f"{path or DEVIATIONS} 里找不到任何条目（表体应当以 `{{0x` 开始）")
    body = text[start:]
    entries: list[DeviationEntry] = []
    for match in ENTRY_PATTERN.finditer(body):
        identifier, kind, rest = match.groups()
        literal = _unescape("".join(piece for piece in STRING_PATTERN.findall(rest)))
        if not literal:
            continue
        entries.append(DeviationEntry(identifier=int(identifier, 16), kind=kind, text=literal))
    return entries


def summarise(entries: list[DeviationEntry]) -> dict:
    """给读数/汇报用的小结。"""
    by_kind: dict[str, int] = {}
    for entry in entries:
        by_kind[entry.kind] = by_kind.get(entry.kind, 0) + 1
    return {
        "total": len(entries),
        "by_kind": by_kind,
        "missing_consequence": [entry.identifier for entry in entries if not entry.has_consequence],
        "missing_judgement": [entry.identifier for entry in entries if entry.judgement_missing],
    }


if __name__ == "__main__":  # 手工看一眼台账现状
    import json

    all_entries = load_entries()
    print(json.dumps(summarise(all_entries), ensure_ascii=False, indent=2))
    for item in all_entries:
        print(f"\n0x{item.identifier:08X} [{item.kind}]")
        print(f"  后果：{item.consequence[:120]}")
        print(f"  判据：{item.judgement[:120]}")
