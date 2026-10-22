#!/usr/bin/env python3
"""只读取证：找**用「寄存器合成的大偏移」寻址**的访存点（`movz` + `movk` + `ldr/str [xM, xN]`）。

为什么需要它（2026-10-03 批次 293）：既有的两个扫描器（`Analysis/api-restore-room-289/scan_float_field.py`
与 `Analysis/api-restore-entityplayer-a/scan_field.py`）**只认立即数寻址**（`[x0, #0x21b0]`）。
而 AArch64 的 imm12 按元素大小缩放，**最大只到 0x3FFC**（4 字节元素）—— 也就是说
`Room`/`Game`/`Level` 这些**大结构体**里偏移超过 0x3FFC 的字段（例如 `Game+0x21558` 的当前房间索引、
`Game+0x26FAE0` 的伏击标志、`Room+0x7188` 的地板颜色）编译器**必须**用
  `movz wN, #lo16` + `movk wN, #hi16, lsl #16` + `ldr w?, [xM, xN]`
这种"寄存器合成"形态 ⇒ 用立即数扫描器扫它们会得到 **0 命中**，而那很容易被误读成
"这个偏移没人用/不存在"（批次 293 一开始就差点被它骗过）。

局限（不许把"没扫到"当成"不存在"）：
  * 只匹配合成后**紧邻几条指令内**的 `[xM, xN]` 形态；合成寄存器被复用/转存到别处再寻址的扫不到；
  * 只扫 `.text`；
  * 命中地址按"最近的已定义符号"归属 ⇒ 长函数里的命中可能挂在前一个符号上，
    每条命中都要再交给 `tools/nro_disasm.py` 复核。

用法：
    python3 tools/nro_find_offset_access.py 0x21558
    python3 tools/nro_find_offset_access.py 0x2180-0x2200        # 区间（找数组基址时很有用）
"""
from __future__ import annotations

import struct
import sys
from bisect import bisect_right
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tools"))
import nro_symbols as ns  # noqa: E402

NRO = (REPO / "The Binding of Isaac_ Afterbirth+ 1.7.9b [010021C000B6A800][v524288][UPD]"
       / "Program #0" / "1" / ".nro" / "Repentance.nro")
WINDOW = 5          # 合成之后多少条指令内算"这次合成的用途"

#: 只关心这几种访存（读/写、字/字节、带不带 lsl）
LOADS = (
    (0xFFC00000, 0xB9400000, "ldr  w"), (0xFFC00000, 0xB9000000, "str  w"),
    (0xFFC00000, 0x39400000, "ldrb w"), (0xFFC00000, 0x39000000, "strb w"),
    (0xFFC00000, 0xF9400000, "ldr  x"), (0xFFC00000, 0xF9000000, "str  x"),
    (0xFFC00000, 0xB9800000, "ldrsw"), (0xFFC00000, 0xBD400000, "ldr  s"),
    (0xFFC00000, 0xBD000000, "str  s"), (0xFFC00000, 0x79400000, "ldrh w"),
    (0xFFC00000, 0x79000000, "strh w"), (0xFFC00000, 0x39800000, "ldrsb w"),
)


def decode_access(word: int):
    for mask, expect, name in LOADS:
        if word & mask == expect:
            return name, (word >> 5) & 0x1F, word & 0x1F
    return None


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    spec = argv[0]
    if "-" in spec:
        low, high = (int(x, 0) for x in spec.split("-"))
        wanted = set(range(low, high + 1))
    else:
        wanted = {int(spec, 0)}

    data = NRO.read_bytes()
    _so, symbols = ns.parse_dynamic_symbols(data)
    defined = sorted((s.file_offset, s.name) for s in symbols.values()
                     if s.is_defined and s.file_offset is not None)
    keys = [o for o, _ in defined]

    def owner_of(off: int) -> str:
        i = bisect_right(keys, off) - 1
        return defined[i][1] if i >= 0 else "<无符号>"

    words = struct.unpack_from(f"<{len(data) // 4}I", data, 0)
    hits: list[tuple[int, int, str, str]] = []
    for i, word in enumerate(words):
        # `movz wN, #imm16`
        if word & 0xFF800000 != 0x52800000:
            continue
        reg = word & 0x1F
        value = (word >> 5) & 0xFFFF
        # ★★ 紧随其后的 `movk wN, #hi, lsl #16` —— 有则合成 32 位，**没有也算数**！
        #   偏移 ≤ 0xFFFF 时编译器只发一条 `movz`（例如 `Room+0x7914` 的地板颜色），
        #   第一版只认 movz+movk 的组合 ⇒ 对这种"单条 movz"的偏移**全漏**（又是 0 命中）。
        at = i
        composed = value
        for j in range(i + 1, min(i + 1 + WINDOW, len(words))):
            w = words[j]
            if w & 0xFF800000 == 0x72800000 and (w & 0x1F) == reg \
                    and ((w >> 21) & 0x3) == 1:
                at, composed = j, value | (((w >> 5) & 0xFFFF) << 16)
                break
        if composed not in wanted:
            continue
        for k in range(at + 1, min(at + 1 + WINDOW, len(words))):
            # ★ 数组基址那种"先算地址再索引"的形态：`add xD, xN, xReg[, lsl #k]`
            #   （`Game+0x21558` 这类字段是 `[x8, x9]` 直接寻址，而**位数组基址**是
            #    `add x9, x0, x9` 之后再 `ldr w?, [x9, x10, lsl #2]` ⇒ 不认 add 会全漏。）
            w = words[k]
            if w & 0x7F200000 == 0x0B000000 and ((w >> 16) & 0x1F) == reg:
                base = (w >> 5) & 0x1F
                if base != reg:
                    shift = (w >> 22) & 0x3
                    hits.append((i * 4, composed,
                                 f"add  x{w & 0x1F}, x{base}, x{reg}"
                                 + (f", lsl #{shift}" if shift else ""),
                                 owner_of(i * 4)))
                    break
            access = decode_access(words[k])
            if access is None:
                continue
            name, base, index = access
            if index == reg and base != reg:
                hits.append((i * 4, composed, f"{name} [x{base}, x{reg}]", owner_of(i * 4)))
                break
            if base == reg:
                hits.append((i * 4, composed, f"{name} [x{reg}]", owner_of(i * 4)))
                break

    print(f"合成的偏移 ∈ {[hex(v) for v in sorted(wanted)]} —— {len(hits)} 命中")
    for off, composed, text, owner in sorted(hits):
        print(f"  0x{off:06X}  0x{composed:x}  {text:<18} ← {owner}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
