#!/usr/bin/env python3
"""布局表核对（第一半，机器可核的那半）：**草稿声明的宽度/浮点 vs 我们实际的读法**。

## 背景

`tools/layout_tables/drafts/*.json` 是自动起草的字段偏移证据（93 条，`confidence=candidate`）：
每条 = 一个 `k…Offset` + 镜像里访问它的访存指令（含 `ldr w`/`ldr s`/`ldr x` 这类**宽度与浮点信息**）。
升格成 `confirmed` 需要人确认"语义对不对"（那是第二半，还没做）。但在那之前有一半是**机器能核**的：

> 我们自己的读取代码也带着类型 —— 字段表（`{"Index", kEntityIndexOffset, false}`）、
> 数据行（`FieldApiRow` 的 `FieldKind::U32`）、以及 `ReadEngine(… + kXxxOffset, &localValue)`
> 里那个局部变量的声明类型。**两边对不上就是真 bug 候选**（最典型的：当成 `u32` 读、实际是 `float`，
> 那种错不崩、只是数字莫名其妙）。

## 判据

| verdict | 含义 | 处置 |
| --- | --- | --- |
| `agree` | 宽度一致，且浮点口径不矛盾 | 通过 |
| `wider-only` | 我们读得比草稿记的那条窄，但镜像里本来就有更宽的访问（`ldp`/`str x` 之类） | 记账，不判红 |
| `we-read-wider` | 我们读得比**镜像里见过的任何**访问都宽（例如按 8 字节读、镜像里只见过 4 字节） | **判红**（可能读到字段之外） |
| `floatness-unclear` | 我们按浮点读、但草稿证据里**没有任何** SIMD 访存；或反过来 | 人工看一次（可能是"这个偏移既有整数访问也有浮点访问"，也可能是我们读错了） |
| `no-reader` | 这个常量在我们的代码里根本没被读（还没暴露成 Lua API） | 记账，不判红 |

## 用法

    python3 tools/layout_type_agreement.py            # 人读
    python3 tools/layout_type_agreement.py --json out.json
    python3 tools/layout_type_agreement.py --mismatch-only

退出码：0 = 没有 `we-read-wider`；1 = 有（可当门禁用）。

> 为什么不是"宽度必须逐个相等"：同一个偏移在镜像里常被**多种宽度**的指令碰到
> （`ldp` 一次搬一对、`str x` 覆盖相邻两个字段、拷贝循环按整字搬浮点……），
> 草稿只记录其中一条 ⇒ 拿那一条当"这个字段就是 N 字节"会造出一堆假阳性（实测 10 条里绝大多数是这种）。
> 所以判据是"**与其中任意一条相符**即算一致"，只有"我们读得比所有见过的访问都宽"才判红。
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
DRAFT_DIR = ROOT / "tools" / "layout_tables" / "drafts"
SRC_DIRS = (ROOT / "runtime" / "src", ROOT / "runtime" / "source")

#: 草稿证据里那句 `why` 会写明是哪条访存指令（`ldr w` / `ldr s` / `str x` …）。
MNEMONIC_RE = re.compile(r"\b(ldr|str)(b|h|sb|sh|sw)?\s*([wxsdq])?\b")
#: SIMD 访存（浮点/向量）：`ldr s` / `str s` / `ldr d` / `str d` / `ldr q` / `str q`。
SIMD_MNEMONICS = ("s", "d", "q")

#: 我们侧"读法"的类型 → (宽度, 是否浮点)。`None` 宽度表示"不是按固定宽度读一个值"。
OUR_KINDS = {
    "u32": (4, False), "i32": (4, False), "bool": (1, False), "u8": (1, False),
    "u64": (8, False), "i64": (8, False), "float": (4, True), "double": (8, True),
}

TABLE_PATTERNS = (
    # 整型字段表：`{"Name", kXxxOffset, false}`（第三个字段 = 是否有符号）
    (re.compile(r'\{\s*"([A-Za-z_]\w*)"\s*,\s*(k\w+Offset)\s*,\s*(true|false)\s*\}'),
     lambda signed: ("i32" if signed == "true" else "u32")),
    # 浮点字段表：`{"Name", kXxxOffset}`（没有第三个字段）
    (re.compile(r'\{\s*"([A-Za-z_]\w*)"\s*,\s*(k\w+Offset)\s*\}'), lambda _: "float"),
)
#: 数据行：`{0x…id, kXxxOffset, …, FieldKind::Kind, …}`
FIELD_ROW_RE = re.compile(r"\{\s*0x[0-9A-Fa-f]+,\s*(k\w+Offset)\s*,[^}]*?FieldKind::(\w+)")
FIELD_KIND_WIDTH = {
    "U32": "u32", "I32": "i32", "Bool": "bool", "Sum2U32": "u32", "BoolEquals": "u32",
    "BoolNonZero": "u32", "SumU32Array": "u32", "VectorCount": "u32",
}
#: `ReadEngine(<expr> + kXxxOffset, &local)`：从上下文里找 `local` 的声明类型。
READ_CALL_RE = re.compile(r"ReadEngine\(\s*[^;()]*?(k\w+Offset)\s*,\s*&(\w+)\s*\)")
LOCAL_DECL_PATTERN = (
    r"(std::uint32_t|std::int32_t|std::uint64_t|std::int64_t|std::uint8_t|float|double|bool|"
    r"u32|i32|u64|i64|u8)\s+{name}\s*[=;{{(]"
)


def draft_rows() -> list[dict]:
    rows: list[dict] = []
    for path in sorted(DRAFT_DIR.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        for row in data.get("fields") or data.get("rows") or data:
            row = dict(row)
            row["_file"] = path.name
            rows.append(row)
    return rows


def evidence_widths(row: dict) -> set[int]:
    """草稿证据里**所有**访问的宽度（同一个偏移常被多种宽度的指令碰到：`ldp` 一对、
    `str x` 覆盖两个相邻字段……所以"与其中一条相符"才算一致，不能只比草稿选中的那一条）。"""
    widths = {int(evidence["width"]) for evidence in row.get("evidence", [])
              if isinstance(evidence.get("width"), int)}
    if isinstance(row.get("width"), int):
        widths.add(int(row["width"]))
    return widths


def evidence_mnemonics(row: dict) -> list[str]:
    out: list[str] = []
    for evidence in row.get("evidence", []):
        for match in MNEMONIC_RE.finditer(evidence.get("why", "")):
            out.append("".join(part for part in match.groups() if part))
    return out


def our_readers() -> dict[str, str]:
    """常量 → 我们读它用的类型（`u32` / `i32` / `float` / …）。"""
    readers: dict[str, str] = {}
    for directory in SRC_DIRS:
        for path in sorted(list(directory.rglob("*.cpp")) + list(directory.rglob("*.hpp"))):
            text = path.read_text(encoding="utf-8", errors="replace")
            for pattern, kind_of in TABLE_PATTERNS:
                for match in pattern.finditer(text):
                    readers.setdefault(match.group(2), kind_of(match.group(3) if match.lastindex and match.lastindex >= 3 else ""))
            for constant, kind in FIELD_ROW_RE.findall(text):
                if kind in FIELD_KIND_WIDTH:
                    readers.setdefault(constant, FIELD_KIND_WIDTH[kind])
            for constant, local in READ_CALL_RE.findall(text):
                # 在该调用点**之前**的窗口里找 `local` 的声明类型（取最近的一次声明）。
                pattern = re.compile(LOCAL_DECL_PATTERN.replace("{name}", re.escape(local)))
                for call in re.finditer(re.escape(constant), text):
                    window = text[max(0, call.start() - 1200) : call.start()]
                    declarations = pattern.findall(window)
                    if not declarations:
                        continue
                    readers.setdefault(constant, normalize_type(declarations[-1]))
                    break
    return readers


def normalize_type(declared: str) -> str:
    mapping = {
        "std::uint32_t": "u32", "std::int32_t": "i32", "std::uint64_t": "u64",
        "std::int64_t": "i64", "std::uint8_t": "u8", "float": "float", "double": "double",
        "bool": "bool", "u32": "u32", "i32": "i32", "u64": "u64", "i64": "i64", "u8": "u8",
    }
    return mapping.get(declared.strip(), "unknown")


def classify(row: dict, ours: str | None) -> dict:
    mnemonics = evidence_mnemonics(row)
    simd = [m for m in mnemonics if m[-1:] in SIMD_MNEMONICS]
    widths = evidence_widths(row)
    result = {
        "constant": row["name"],
        "draft_file": row.get("_file", ""),
        "draft_kind": row.get("kind", ""),
        "draft_width": row.get("width"),
        "draft_mnemonics": mnemonics,
        "draft_widths": sorted(widths),
        "draft_simd": simd,
        "our_kind": ours,
        "verdict": "no-reader",
        "detail": "我们没有读这个字段（还没暴露成接口）",
    }
    if ours is None or ours == "unknown":
        return result
    our_width, our_float = OUR_KINDS.get(ours, (None, None))
    draft_width = row.get("width")
    if our_width is not None and widths and our_width not in widths:
        if our_width > max(widths):
            result["verdict"] = "we-read-wider"
            result["detail"] = (f"我们按 {ours}（{our_width} 字节）读，但镜像里只见过 "
                                f"{sorted(widths)} 字节的访问 ⇒ **可能读到字段之外**")
        else:
            result["verdict"] = "wider-only"
            result["detail"] = (f"我们按 {ours}（{our_width} 字节）读，镜像里见过 "
                                f"{sorted(widths)} 字节的访问（更宽的访问可能同时覆盖相邻字段）"
                                "⇒ 记账，不判红")
        return result
    if our_float and not simd:
        result["verdict"] = "floatness-unclear"
        result["detail"] = ("我们按浮点读，但草稿证据里没有 SIMD 访存。**注意这不一定是错**："
                           "整字搬运（`ldr w`/`str w`）也会用来拷贝浮点数据 ⇒ 人工看一眼即可")
        return result
    if (not our_float) and simd and not any("w" in m for m in mnemonics):
        result["verdict"] = "floatness-unclear"
        result["detail"] = "草稿证据只有 SIMD 访存，而我们按整数读（更像是我们读错了）"
        return result
    result["verdict"] = "agree"
    result["detail"] = f"宽度与浮点口径一致（我们 {ours}，镜像里见过 {sorted(widths)} 字节的访问）"
    return result


#: 人工分诊台账：`we-read-wider` 一律要在这里写清"看过了、结论是什么"。
TRIAGE = ROOT / "tools" / "layout_type_agreement.json"


def load_triage() -> dict[str, dict]:
    if not TRIAGE.exists():
        return {}
    return json.loads(TRIAGE.read_text(encoding="utf-8")).get("rows", {})


def main() -> int:
    parser = argparse.ArgumentParser(description="布局表核对：草稿宽度/浮点 vs 我们的读法")
    parser.add_argument("--json", type=pathlib.Path)
    parser.add_argument("--mismatch-only", action="store_true")
    args = parser.parse_args()

    readers = our_readers()
    rows = [classify(row, readers.get(row["name"])) for row in draft_rows()]
    by_verdict: dict[str, list[dict]] = {}
    for row in rows:
        by_verdict.setdefault(row["verdict"], []).append(row)

    compared = len(rows) - len(by_verdict.get("no-reader", []))
    print(f"草稿字段 {len(rows)} 条；我们真的会读它的 {compared} 条（其余 {len(rows) - compared} 条还没暴露）")
    for verdict in ("agree", "wider-only", "floatness-unclear", "we-read-wider", "no-reader"):
        print(f"  {verdict:20} {len(by_verdict.get(verdict, []))}")

    triage = load_triage()
    all_bad = by_verdict.get("we-read-wider", [])
    bad = [row for row in all_bad if row["constant"] not in triage]
    triaged = [row for row in all_bad if row["constant"] in triage]
    if triaged:
        print(f"（其中 {len(triaged)} 条已人工看过并写在 {TRIAGE.name} 里）")
    if bad:
        print("\n✗ 我们读得比镜像里见过的任何访问都宽（可能读到字段之外）：")
        for row in bad:
            print(f"  {row['constant']:38} {row['detail']}（草稿 {row['draft_file']}）")
    unclear = [row for row in by_verdict.get("floatness-unclear", [])
               if row["constant"] not in triage]
    if by_verdict.get("floatness-unclear") and not unclear and not args.mismatch_only:
        print("\n~ 浮点口径需要人工看的那几条：都已在台账里写了结论 ✓")
    if unclear and not args.mismatch_only:
        print("\n~ 浮点口径需要人工看一眼：")
        for row in unclear:
            print(f"  {row['constant']:38} {row['detail']}；草稿里的访存 = {row['draft_mnemonics'][:4]}")
    if not args.mismatch_only:
        print("\n逐条：")
        for row in sorted(rows, key=lambda item: item["constant"]):
            ours = row["our_kind"] or "—"
            triaged_mark = row["constant"] in triage
            mark = {"agree": "✓", "wider-only": "+",
                    "floatness-unclear": "~" if not triaged_mark else "=",
                    "we-read-wider": "✗" if not triaged_mark else "=",
                    "no-reader": "·"}[row["verdict"]]
            print(f"  {mark} {row['constant']:38} 草稿 {row['draft_kind']}/{row['draft_width']} 字节"
                  f" · 我们 {ours}  {row['detail']}")
    if args.json is not None:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"（JSON 已写入 {args.json}）")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
