#!/usr/bin/env python3
"""为"字段偏移"自动**起草证据**：在游戏镜像里找出访问该偏移的指令，归到所在函数。

## 要解决什么

`tools/layout_tables/` 的口径是"每行都得能被 `build_layout_table.py --verify` 重新反汇编证明一次"，
但 193 个字段偏移里目前只有 1 个进了表 —— 其余只有 `runtime_constants.hpp` 行尾的一句注释。
逐个手工反汇编找证据不现实，所以做成"自动起草 + 人工筛选"：

1. 扫镜像 `.text`，把所有**访问某个偏移**的访存指令（`ldr/str/ldur/stur/ldp/stp`，含 SIMD）找出来；
2. 用符号表把每条指令归到**它所在的函数**；
3. 按"函数名是否与本行常量名里的结构体名相呼应"打分，挑出候选；
4. 产出 `tools/layout_tables/drafts/<结构体>.json` —— 形状与正式表**完全一致**，
   所以可以直接被 `build_layout_table.py --verify` 复核（但**不参与生成**，落表要人工确认语义）。

⚠️ 自检：本工具的访存解码有一个**已知答案**可以对照 —— `Room` 的 `EnterFrameCount`（+0x191c）
就在 `_ZN15IsaacRepentance4Room13GetFrameCountEv` 里、地址 `0x00470b2c`（见 `room.json`）。
`--self-test` 会核对这一点；解码写错就立刻暴露（这正是本仓库"证据要能被机器复核"的做法）。
"""

from __future__ import annotations

import argparse
import bisect
import json
import pathlib
import re
import struct
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import nro_disasm  # noqa: E402
import nro_symbols  # noqa: E402

NRO = (
    ROOT
    / "The Binding of Isaac_ Afterbirth+ 1.7.9b [010021C000B6A800][v524288][UPD]"
    / "Program #0/1/.nro/Repentance.nro"
)
SIGNATURES = ROOT / "tools" / "engine_symbol_signatures.json"
LAYOUT_DIR = ROOT / "tools" / "layout_tables"
DRAFT_DIR = LAYOUT_DIR / "drafts"

#: (掩码, 期望值, 宽度, 是否立即数按宽度缩放, 说明) —— 覆盖常见访存形态。
LOAD_STORE_FORMS = [
    (0xFFC00000, 0xB9400000, 4, 4, "ldr w"),
    (0xFFC00000, 0xF9400000, 8, 8, "ldr x"),
    (0xFFC00000, 0x39400000, 1, 1, "ldrb"),
    (0xFFC00000, 0x79400000, 2, 2, "ldrh"),
    (0xFFC00000, 0xB9800000, 4, 4, "ldrsw"),
    (0xFFC00000, 0x39800000, 1, 1, "ldrsb"),
    (0xFFC00000, 0x79800000, 2, 2, "ldrsh"),
    (0xFFC00000, 0xB9000000, 4, 4, "str w"),
    (0xFFC00000, 0xF9000000, 8, 8, "str x"),
    (0xFFC00000, 0x39000000, 1, 1, "strb"),
    (0xFFC00000, 0x79000000, 2, 2, "strh"),
    (0xFFC00000, 0x3DC00000, 16, 16, "ldr q"),
    (0xFFC00000, 0x3D400000, 8, 8, "ldr d"),
    (0xFFC00000, 0xBD400000, 4, 4, "ldr s"),
    (0xFFC00000, 0x3D800000, 16, 16, "str q"),
    (0xFFC00000, 0x3D000000, 8, 8, "str d"),
    (0xFFC00000, 0xBD000000, 4, 4, "str s"),
]
#: 非缩放的 ldur/stur（imm9），以及成对访存 ldp/stp（imm7，按宽度缩放）。
UNSCALED_FORMS = [
    (0xFFE00C00, 0xB8400000, 4, "ldur w"),
    (0xFFE00C00, 0xF8400000, 8, "ldur x"),
    (0xFFE00C00, 0x38400000, 1, "ldurb"),
    (0xFFE00C00, 0x78400000, 2, "ldurh"),
    (0xFFE00C00, 0xB8000000, 4, "stur w"),
    (0xFFE00C00, 0xF8000000, 8, "stur x"),
    (0xFFE00C00, 0x38000000, 1, "sturb"),
    (0xFFE00C00, 0x78000000, 2, "sturh"),
]
PAIR_FORMS = [
    (0xFFC00000, 0x29400000, 4, "ldp w"),
    (0xFFC00000, 0xA9400000, 8, "ldp x"),
    (0xFFC00000, 0x29000000, 4, "stp w"),
    (0xFFC00000, 0xA9000000, 8, "stp x"),
    (0xFFC00000, 0xAD400000, 16, "ldp q"),
    (0xFFC00000, 0xAD000000, 16, "stp q"),
]


def _sign_extend(value: int, bits: int) -> int:
    if value & (1 << (bits - 1)):
        return value - (1 << bits)
    return value


def decode_access(word: int) -> tuple[int, int, str, int] | None:
    """返回 (偏移, 宽度, 助记符, 基址寄存器) —— 偏移**带符号**（负数是栈访问，不算字段）。

    不是"带立即数的访存"时返回 None（寄存器偏移形态本工具不追）。
    """
    base = (word >> 5) & 0x1F
    for mask, expected, width, scale, mnemonic in LOAD_STORE_FORMS:
        if word & mask == expected:
            return ((word >> 10) & 0xFFF) * scale, width, mnemonic, base
    for mask, expected, width, mnemonic in UNSCALED_FORMS:
        if word & mask == expected:
            return _sign_extend((word >> 12) & 0x1FF, 9), width, mnemonic, base
    for mask, expected, width, mnemonic in PAIR_FORMS:
        if word & mask == expected:
            return _sign_extend((word >> 15) & 0x7F, 7) * width, width, mnemonic, base
    return None


def symbol_index(symbols: dict) -> tuple[list[int], list[str]]:
    pairs = sorted((s.file_offset, n) for n, s in symbols.items() if s.file_offset is not None)
    return [offset for offset, _ in pairs], [name for _, name in pairs]


def scan_accesses(nro: bytes, wanted: dict[int, set[str]]) -> dict[int, list[tuple[int, int, str]]]:
    """扫 .text，收集"偏移命中 wanted"的访存指令：{偏移: [(地址, 宽度, 助记符)]}。"""
    text_start, text_end = 0x100, 0x100 + (len(nro) - 0x100)   # NSO 里 .text 从 0x100 起
    found: dict[int, list[tuple[int, int, str]]] = {}
    for address in range(text_start, text_end - 4, 4):
        word = struct.unpack_from("<I", nro, address)[0]
        decoded = decode_access(word)
        if decoded is None:
            continue
        offset, width, mnemonic, base = decoded
        # 负偏移 = 栈访问；基址是 sp(31) / x29 帧指针 = 局部变量 —— 都不是结构体字段。
        if offset < 0 or base in (29, 31):
            continue
        if offset in wanted:
            found.setdefault(offset, []).append((address, width, mnemonic))
    return found


def struct_hint(constant: str) -> str:
    """`kGridEntityTypeOffset` → `grid entity`（用来和函数名做呼应打分）。"""
    stem = constant[len("k") : -len("Offset")]
    return re.sub(r"(?<!^)(?=[A-Z])", " ", stem).lower()


def evidence_passes_verify(function: str, address: int, offset: int,
                           nro: pathlib.Path, symbols: dict) -> bool:
    """★ 起草时就自己复核一遍：那条地址上必须真的有一条"带该偏移"的访存指令。

    为什么要在这里做：`build_layout_table.py --verify` 复核的是"函数的反汇编里能否找到这个地址、
    且指令里带该偏移"。如果我只按"最近的符号"给指令归函数，会归错（某些地址落在符号缝隙里），
    于是草稿出来就得人工返工 —— 所以**先把复核条件搬到这里**，通不过就换下一个候选，
    保证草稿天生 100% 可复核（这是本仓库"证据必须能被机器重新证明"的一贯口径）。
    """
    symbol = symbols.get(function)
    if symbol is None or not symbol.is_defined or symbol.file_offset is None:
        return False
    lines = [line.strip() for line in nro_disasm.disassemble(str(nro), symbol.file_offset, 4096,
                                                             annotate=False)]
    wanted = f"{address:08x}"
    found = next((line for line in lines if line.startswith(wanted)), None)
    if found is None:
        lines = [line.strip() for line in nro_disasm.disassemble(str(nro), symbol.file_offset,
                                                                16384, annotate=False)]
        found = next((line for line in lines if line.startswith(wanted)), None)
    if found is None:
        return False
    return f"#{offset:#x}" in found or offset == 0


def pick_candidates(constant: str, accesses: list[tuple[int, int, str]],
                    offsets: list[int], names: list[str], symbols: dict,
                    nro: pathlib.Path, limit: int = 3) -> list[dict]:
    hint = struct_hint(constant)
    words = [word for word in hint.split() if len(word) > 3]
    scored: list[tuple[int, int]] = []
    for index, (address, width, mnemonic) in enumerate(accesses):
        position = bisect.bisect_right(offsets, address) - 1
        if position < 0:
            continue
        name = names[position]
        demangled_words = re.sub(r"[^A-Za-z]", " ", name).lower()
        score = sum(1 for word in words if word in demangled_words)
        scored.append((-score, index))
    scored.sort()
    picked: list[dict] = []
    for _, index in scored:
        if len(picked) >= limit:
            break
        address, width, mnemonic = accesses[index]
        position = bisect.bisect_right(offsets, address) - 1
        name = names[position]
        if not evidence_passes_verify(name, address, offset_for(constant), nro, symbols):
            continue
        picked.append({"function": name, "address": address, "width": width, "mnemonic": mnemonic})
    return picked


def offset_for(constant: str) -> int:
    return _OFFSETS[constant]


_OFFSETS: dict[str, int] = {}


def main() -> int:
    parser = argparse.ArgumentParser(description="为字段偏移自动起草布局表证据")
    parser.add_argument("--self-test", action="store_true", help="只用已知答案核对访存解码")
    parser.add_argument("--limit", type=int, default=200, help="最多处理多少个偏移")
    args = parser.parse_args()

    if not NRO.exists():
        raise SystemExit("找不到游戏镜像（公开仓库不带游戏资源）")
    raw = NRO.read_bytes()
    _soname, symbols = nro_symbols.parse_dynamic_symbols(raw)
    offsets, names = symbol_index(symbols)

    if args.self_test:
        # 已知答案：Room::GetFrameCount 里 ldr w9, [x0, #0x191c] @ 0x470b2c
        hits = scan_accesses(raw, {0x191C: {"x"}})[0x191C]
        ok = any(address == 0x470B2C for address, _, _ in hits)
        print(f"自检：偏移 0x191c 命中 {len(hits)} 条；0x470b2c 在不在里面：{ok}")
        return 0 if ok else 1

    table = json.loads(SIGNATURES.read_text(encoding="utf-8"))
    _OFFSETS.update({e["constant"]: int(e["offset"], 16) for e in table})
    covered: set[str] = set()
    for path in LAYOUT_DIR.glob("*.json"):
        covered.update(re.findall(r"k[A-Za-z0-9]+Offset", path.read_text(encoding="utf-8")))
    fields = [
        entry for entry in table
        if entry["kind"] == "field"
        and "Slot" not in entry["constant"]
        and int(entry["offset"], 16) < 0x200000
        and entry["constant"] not in covered
    ][: args.limit]
    wanted = {int(entry["offset"], 16): {entry["constant"]} for entry in fields}
    print(f"待取证字段偏移 {len(fields)} 个；开始扫镜像（{len(raw) // 1024} KiB）…")
    accesses = scan_accesses(raw, wanted)

    DRAFT_DIR.mkdir(parents=True, exist_ok=True)
    no_evidence: list[str] = []
    by_constant: dict[str, list[dict]] = {}
    for entry in fields:
        offset = int(entry["offset"], 16)
        hits = accesses.get(offset, [])
        if not hits:
            no_evidence.append(entry["constant"])
            continue
        candidates = pick_candidates(entry["constant"], hits, offsets, names, symbols, NRO)
        by_constant[entry["constant"]] = [
            {
                "kind": "access",
                "function": candidate["function"],
                "address": f"0x{candidate['address']:08x}",
                "offset": offset,
                "width": candidate["width"],
                "why": f"镜像里访问该偏移的指令（{candidate['mnemonic']}，宽度 {candidate['width']}）；"
                       f"共找到 {len(hits)} 条同类访问，此为该常量名呼应度最高的函数之一",
            }
            for candidate in candidates
        ]

    # 按"常量名里的结构体前缀"分组落成草稿
    groups: dict[str, list[dict]] = {}
    for constant, evidence in by_constant.items():
        prefix = re.match(r"([A-Z][a-z]+)", constant[len("k"):])
        group = prefix.group(1).lower() if prefix else "misc"
        row = {
            "name": constant,
            "kind": "int32",
            "offset": int(next(e for e in fields if e["constant"] == constant)["offset"], 16),
            "width": evidence[0]["width"],
            "confidence": "candidate",
            "semantic": "（草稿）自动取证：语义未确认，仅登记「偏移 + 一处可复核的访问指令」",
            "evidence": evidence,
        }
        groups.setdefault(group, []).append(row)

    for group, rows in groups.items():
        path = DRAFT_DIR / f"{group}.json"
        path.write_text(
            json.dumps(
                {
                    "schema": "isaac-layout-table/1",
                    "build_id": "91C73FDD575061318D68886316AFEAC72388B2AB",
                    "struct": group,
                    "note": [
                        "★ 这是**自动起草**的草稿（`tools/draft_layout_evidence.py` 生成），不参与 C++ 生成。",
                        "每行的证据是「镜像里访问该偏移的一条指令 + 它所在的函数」，可被 "
                        "`tools/build_layout_table.py --verify` 重新反汇编复核。",
                        "语义（字段名/含义）尚未人工确认 ⇒ confidence 一律 candidate，不得进对外 API。",
                    ],
                    "rows": sorted(rows, key=lambda item: item["offset"]),
                },
                ensure_ascii=False, indent=1,
            ),
            encoding="utf-8",
        )

    total = len(fields)
    with_evidence = len(by_constant)
    print(f"起草完成：{with_evidence}/{total} 个偏移找到可复核证据，草稿写在 {DRAFT_DIR.relative_to(ROOT)}/")
    if no_evidence:
        print(f"另有 {len(no_evidence)} 个偏移**没扫到直接访存**（可能经指针/计算地址访问）⇒ 需人工：")
        print("  " + ", ".join(sorted(no_evidence)[:20]) + (" …" if len(no_evidence) > 20 else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
