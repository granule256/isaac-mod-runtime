#!/usr/bin/env python3
"""读 `api_deviation.cpp` 那张**偏离台账**：谁还在返回兜底/近似值、后果是什么、判据在哪、**性质是哪一类**。

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

## 2026-09-21（批次 017）：按**性质**分组 —— "平台固有"与"我们的欠账"分开

原来的台账只有"偏离长什么样"（`kind`：Partial / Placeholder / NotInEngine），读者分不清一条偏离是
**这台机器上永远消不掉**的，还是**我们还没做到**的。混在一起会出两种错判：把欠账当平台限制
（于是没人去修），或把平台限制当欠账（于是反复去做做不到的事）。

### 口径（与 `api_deviation.cpp` 文件头逐字一致，判定时**不看** `kind`）

* **platform（平台固有）** —— 同时满足：① PC 上确实有对应物（PC 文档里查得到它做什么）；
  ② Switch 平台侧**没有可用底座**，或 PC 的语义**无法映射**过来（PC 依赖的输入源/系统能力在这台
  机器上不存在，例如鼠标这种指向设备、调试控制台）；③ 已经**取证过"没有"**（是"查过、确认没有"，
  不是"我们还没查"）；④ 结论：继续做工作也消不掉，只能永久登记。
  实例：`Input.GetMousePosition`、`Input.IsMouseBtnPressed`（Switch 没有鼠标）、
  `Isaac.ExecuteCommand`（Switch 没有控制台）。
* **debt（我们的欠账）** —— 底座**存在或可定位**（引擎里有对应的字段/函数/数据结构，或台账正文里
  已经写出了可执行的定位办法），只是我们**还没定位 / 还没实现 / 实现得偏保守**。
  结论：**能还**；还清之后应当把这条从台账里删掉。
* **design（主动保留的口径差异）** —— 两侧都做得到，但我们**有意**选了与 PC 不同的口径，而且台账
  正文里明确写了"为什么不照着做"（复刻 PC 等于复刻它的未定义行为；或照着做会把引擎内部指针交给模组）。
  结论：**不打算改**；要动它必须先改设计意图（属于用户裁决，不属于工程欠账）。
  实例：`Room:GetGridPath` 的越界口径、`GridEntity:GetRNG` 返回快照而不是引擎 RNG 的引用。

### 本模块怎么读它（"可判"的含义）

每条正文里必须有一段固定形状的标记：

    性质：<platform|debt|design>（<中文名>）——理由：<一行理由>

* `NATURE_MARKER` 之后的第一段英文单词就是取值 → `DeviationEntry.nature`；
* `——理由：` 之后、`判据：` 之前那一段就是**一行理由** → `DeviationEntry.nature_reason`
  （要求读者"不看别处就明白为什么这么归类"）；
* 取值不在 `NATURES` 里、或整段标记缺失 ⇒ 门禁红（`test_api_deviation.py` 按取值逐个钉条数）。

条目形状（`api_deviation.cpp` 里的表体）：

    {0x04010006,
     ApiDeviationKind::Partial,
     "……偏离后果：……"
     "性质：design（主动保留的口径差异）——理由：……"
     "判据：runtime/tests/test_lua_room_grid.py（钉越界口径）"},

正文可能由多个相邻字符串字面量拼成，解析时按 C++ 的拼接规则连起来。

## 用法

    python3 tools/api_deviation_ledger.py            # 按性质分组的人读输出（带各组条数）
    python3 tools/api_deviation_ledger.py --json     # 机器消费（每条都带 nature / nature_reason）
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEVIATIONS = ROOT / "runtime" / "src" / "interfaces" / "lua" / "api_deviation.cpp"

#: 允许的种类（与 C++ 侧 `ApiDeviationKind` 一致）。
KINDS = ("Partial", "Placeholder", "NotInEngine")

#: 允许的**性质**取值（口径见文件头）。顺序就是人读输出里的分组顺序。
NATURES = ("platform", "debt", "design")

#: 取值 → 中文名（与台账正文里那个括号里写的名字一致）。
NATURE_LABELS = {
    "platform": "平台固有",
    "debt": "我们的欠账",
    "design": "主动保留的口径差异",
}

#: 台账里几个**必填**字段的标记词。门禁按它们判"写了没有"。
CONSEQUENCE_MARKER = "偏离后果："
JUDGEMENT_MARKER = "判据："
NATURE_MARKER = "性质："
NATURE_REASON_MARKER = "——理由："

#: 判据可以写成"暂无（理由…）"—— 那表示"这条偏离目前没有可执行判据"，
#: 属于**欠账**：条数被门禁钉住，只能降不能升。
NO_JUDGEMENT_PREFIX = "暂无"

#: ---- 形状两栏（2026-09-27 批次 161）------------------------------------------
#
# 由来（一次**真机事故**，可复核）：`EntityPlayer:GetMainTwin()` 曾被写成**恒 nil**，而 PC 文档正文
# 明写"其它任何角色 → 该角色自己" ⇒ EID 写 `player:GetMainTwin():GetPlayerType()` 时在 nil 上取方法
# ⇒ 抛 `attempt to index a nil value` ⇒ **派发器把整条 `MC_POST_RENDER` 回调摘掉**（用户看到的是
# "站在长子名分旁边 EID 不显示信息"）。更糟的是批次 128 恰好把这个错误行为用 `value == nil` 钉死了。
#
# ⇒ 纪律（AGENTS.md 同条）：**把"我们返回什么形状"和"PC 返回什么形状"分开写**；形状只要与 PC 不同，
# 就要写明"模组链式调用会不会抛错"，判据要照真实模组那样**链一次**。
#
# 本模块负责这条纪律在**台账侧**的那一半：正文写「恒 nil」的条目必须写清两侧形状；
# `PC 形状` 不是 nil、而我们是 nil 的条目，后果里必须点名 `链式调用会抛错`。
PC_SHAPE_MARKER = "PC 形状："
OUR_SHAPE_MARKER = "我们形状："
#: 允许的形状取值（与 AGENTS.md 里那一行逐字一致）。
SHAPES = ("nil", "对象", "数字", "布尔", "字符串")
#: `PC 形状` 不是 nil、而我们给 nil 时，后果段里必须出现的字样（门禁按它判，不靠关键词顺带命中）。
CHAINING_MARKER = "链式调用会抛错"

# 条目正文只能是C++相邻字符串字面量，字符串里的 }, 不是条目末尾。
ENTRY_PATTERN = re.compile(
    r'\{\s*(0x[0-9A-Fa-f]+)\s*,\s*ApiDeviationKind::(\w+)\s*,\s*'
    r'((?:"(?:[^"\\]|\\.)*"\s*)+)\}\s*,', re.S)
COMMENT_OR_LITERAL = re.compile(
    r'"(?:[^"\\]|\\.)*"|\'(?:[^\'\\]|\\.)*\'|//[^\n]*|/\*.*?\*/', re.S)


def strip_cpp_comments(text: str) -> str:
    """只剥真正注释，保留字符串中的URL/注释符号及换行。"""
    def replace(match: re.Match[str]) -> str:
        token = match.group()
        if token.startswith(("//", "/*")):
            return " " + "\n" * token.count("\n")
        return token
    return COMMENT_OR_LITERAL.sub(replace, text)

STRING_PATTERN = re.compile(r'"((?:[^"\\]|\\.)*)"')
JUDGEMENT_PATH_PATTERN = re.compile(r"(?:runtime/)?tests/[A-Za-z0-9_./-]+\.py")
NATURE_TOKEN_PATTERN = re.compile(r"性质：([^\s（(]+)")


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
        """`偏离后果：` 之后、`性质：`/`判据：` 之前的那段（没写就返回空串 —— 门禁据此判红）。

        ★ 批次 017 起正文里多了一段 `性质：…——理由：…`，它排在 `判据：` 之前，所以这里
        要在**两个**结束标记里取更靠前的那个，否则后果会把性质那段一起吞进来
        （读数工具就打印这个字段）。
        """
        index = self.text.find(CONSEQUENCE_MARKER)
        if index < 0:
            return ""
        tail = self.text[index + len(CONSEQUENCE_MARKER):]
        cuts = [tail.find(marker) for marker in (JUDGEMENT_MARKER, NATURE_MARKER)]
        cuts = [cut for cut in cuts if cut >= 0]
        if cuts:
            tail = tail[:min(cuts)]
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

    # ---- 性质（批次 017）----------------------------------------------------

    @property
    def nature(self) -> str:
        """`性质：` 后面那个取值（`platform`/`debt`/`design`）。

        没写、写错位置、或取值不是上面三个之一时返回原文里那一小段
        （门禁拿它跟 `NATURES` 比；缺标记则返回空串 —— 空串**不是**合法取值）。
        """
        match = NATURE_TOKEN_PATTERN.search(self.text)
        if match is None:
            return ""
        return match.group(1).strip()

    @property
    def nature_label(self) -> str:
        """取值对应的中文名（未知取值返回空串，门禁会红）。"""
        return NATURE_LABELS.get(self.nature, "")

    @property
    def nature_reason(self) -> str:
        """`——理由：` 之后、`判据：` 之前的那**一行**理由（没写就返回空串）。"""
        index = self.text.find(NATURE_REASON_MARKER)
        if index < 0:
            return ""
        tail = self.text[index + len(NATURE_REASON_MARKER):]
        cut = tail.find(JUDGEMENT_MARKER)
        if cut >= 0:
            tail = tail[:cut]
        return tail.strip()

    @property
    def is_classified(self) -> bool:
        """性质取值合法（门禁判"不许有未归类条目"用的就是它）。"""
        return self.nature in NATURES

    # ---- 形状两栏（批次 161）------------------------------------------------

    def _shape(self, marker: str) -> str:
        """取 `marker` 之后那个形状词（没写返回空串；词表校验由门禁做）。"""
        index = self.text.find(marker)
        if index < 0:
            return ""
        tail = self.text[index + len(marker):].lstrip()
        for stop in (" ", "　", "（", "(", "，", ",", "。", "；", ";", "\n", "）", ")"):
            cut = tail.find(stop)
            if cut >= 0:
                tail = tail[:cut]
        return tail.strip("`").strip()

    @property
    def pc_shape(self) -> str:
        """`PC 形状：<nil|对象|数字|布尔|字符串>` 里那个词（没写返回空串）。"""
        return self._shape(PC_SHAPE_MARKER)

    @property
    def our_shape(self) -> str:
        """`我们形状：<…>` 里那个词（没写返回空串）。"""
        return self._shape(OUR_SHAPE_MARKER)

    @property
    def has_pc_shape(self) -> bool:
        return PC_SHAPE_MARKER in self.text

    @property
    def has_our_shape(self) -> bool:
        return OUR_SHAPE_MARKER in self.text

    @property
    def mentions_nil_return(self) -> bool:
        """正文自己说"我们恒 nil"（门禁据此要求写清两侧形状）。"""
        return "恒 nil" in self.text

    @property
    def needs_chaining_warning(self) -> bool:
        """PC 给的不是 nil、而我们给 nil ⇒ 后果里必须交代"链式调用会抛错"。

        ★ 判据用**我们自己写的形状两栏**，不猜正文：`PC 形状` 合法且不是 nil、
        `我们形状` 恰好是 nil —— 这一对就是"模组会链到 nil 上"的机械形态。
        """
        return (
            self.pc_shape in SHAPES
            and self.pc_shape != "nil"
            and self.our_shape == "nil"
        )


def _unescape(literal: str) -> str:
    """C++ 字面量里的转义还原（**只处理我们真会用到的那几个**）。

    不能用 `unicode_escape`：那会把中文按 latin-1 拆坏。台账正文里出现的转义只有
    `\\"`（判据里引用的接口名）与 `\\\\` 两种，逐个替换即可。
    """
    escapes = {'"': '"', "\\": "\\", "n": "\n", "r": "\r", "t": "\t"}
    return re.sub(r'\\([\\"nrt])', lambda match: escapes[match[1]], literal)


def load_entries(path: Path | None = None) -> list[DeviationEntry]:
    """解析整张台账。表体从第一个 `{0x` 开始 —— 之前的注释不属于条目。"""
    text = strip_cpp_comments((path or DEVIATIONS).read_text(encoding="utf-8"))
    body = text
    entries: list[DeviationEntry] = []
    for match in ENTRY_PATTERN.finditer(body):
        identifier, kind, rest = match.groups()
        literal = _unescape("".join(piece for piece in STRING_PATTERN.findall(rest)))
        if not literal:
            continue
        entries.append(DeviationEntry(identifier=int(identifier, 16), kind=kind, text=literal))
    if not entries:
        raise ValueError(f"{path or DEVIATIONS} 里找不到任何有效条目")
    return entries


def by_nature(entries: list[DeviationEntry]) -> dict[str, list[DeviationEntry]]:
    """按性质分组（键含空串与非法取值 —— 未归类的条目不许被悄悄吞掉）。"""
    groups: dict[str, list[DeviationEntry]] = {}
    for entry in entries:
        groups.setdefault(entry.nature, []).append(entry)
    for group in groups.values():
        group.sort(key=lambda item: item.identifier)
    return groups


def group_order(groups: dict[str, list[DeviationEntry]]) -> list[str]:
    """先按口径里的三个取值排，再把未知/缺失的取值排在最后（如实露出来）。"""
    known = [nature for nature in NATURES if nature in groups]
    unknown = sorted(nature for nature in groups if nature not in NATURES)
    return known + unknown


def summarise(entries: list[DeviationEntry]) -> dict:
    """给读数/汇报用的小结（含按性质的条数）。"""
    by_kind: dict[str, int] = {}
    counts_by_nature: dict[str, int] = {}
    for entry in entries:
        by_kind[entry.kind] = by_kind.get(entry.kind, 0) + 1
        counts_by_nature[entry.nature] = counts_by_nature.get(entry.nature, 0) + 1
    return {
        "total": len(entries),
        "by_kind": by_kind,
        "by_nature": counts_by_nature,
        "unclassified": [entry.identifier for entry in entries if not entry.is_classified],
        "missing_reason": [
            entry.identifier for entry in entries if not entry.nature_reason
        ],
        "missing_consequence": [entry.identifier for entry in entries if not entry.has_consequence],
        "missing_judgement": [entry.identifier for entry in entries if entry.judgement_missing],
    }


def dump_json(entries: list[DeviationEntry]) -> str:
    """机器消费用的 JSON：**每条都带 nature 与 nature_reason**。"""
    import json

    stats = summarise(entries)
    return json.dumps(
        {
            "total": stats["total"],
            "by_kind": stats["by_kind"],
            "by_nature": stats["by_nature"],
            "natures": list(NATURES),
            "nature_labels": NATURE_LABELS,
            "unclassified": [f"0x{value:08X}" for value in stats["unclassified"]],
            "entries": [
                {
                    "id": f"0x{entry.identifier:08X}",
                    "kind": entry.kind,
                    "nature": entry.nature,
                    "nature_label": entry.nature_label,
                    "nature_reason": entry.nature_reason,
                    "consequence": entry.consequence,
                    "judgement": entry.judgement,
                    "pc_shape": entry.pc_shape,
                    "our_shape": entry.our_shape,
                    "needs_chaining_warning": entry.needs_chaining_warning,
                }
                for entry in entries
            ],
        },
        ensure_ascii=False,
        indent=2,
    )


def print_grouped(entries: list[DeviationEntry]) -> None:
    """人读输出：**按性质分组**（组内按 id 排序），每组给出条数。"""
    groups = by_nature(entries)
    counts = "、".join(
        f"{nature}（{NATURE_LABELS.get(nature, '未归类')}）{len(groups[nature])} 条"
        for nature in group_order(groups)
    )
    print(f"偏离台账：共 {len(entries)} 条 —— {counts}")
    print("（性质口径见 `runtime/src/interfaces/lua/api_deviation.cpp` 文件头；"
          "取值：platform 平台固有 / debt 我们的欠账 / design 主动保留的口径差异）")
    for nature in group_order(groups):
        label = NATURE_LABELS.get(nature, "未归类（取值非法或缺失 —— 门禁会红）")
        print()
        print(f"=== [{nature or '<未归类>'}] {label}：{len(groups[nature])} 条 ===")
        for entry in groups[nature]:
            print(f"  · 0x{entry.identifier:08X} [{entry.kind}]")
            print(f"      理由：{entry.nature_reason or '**缺理由：……**（门禁会红）'}")
            if entry.has_pc_shape or entry.has_our_shape:
                print(f"      形状：PC = {entry.pc_shape or '**缺**'} / "
                      f"我们 = {entry.our_shape or '**缺**'}"
                      + ("　← ★ 模组链式调用会抛错（后果里必须写明）"
                         if entry.needs_chaining_warning else ""))
            print(f"      后果：{entry.consequence[:120] or '**缺 偏离后果：（门禁会红）**'}")
            print(f"      判据：{entry.judgement[:120] or '**缺判据：……**（门禁会红）'}")
    stats = summarise(entries)
    if stats["unclassified"]:
        print()
        print("⚠ 有未归类（取值非法/缺失）的条目："
              + "、".join(f"0x{value:08X}" for value in stats["unclassified"]))


if __name__ == "__main__":  # 手工看一眼台账现状
    import argparse

    parser = argparse.ArgumentParser(description="打印 API 偏离台账（按性质分组）")
    parser.add_argument("--json", action="store_true",
                        help="输出机器可消费的 JSON（每条带 nature / nature_reason）")
    arguments = parser.parse_args()

    all_entries = load_entries()
    if arguments.json:
        print(dump_json(all_entries))
    else:
        print_grouped(all_entries)
