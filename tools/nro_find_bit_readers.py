#!/usr/bin/env python3
"""只读取证：找"读了某个 u32 字段（默认描述符 `+0x50`）之后，**单独测其中某一位**"的位置。

动机：`Room:IsAmbushDone()`（PC = 描述符 Flags 的 bit3）与 `Room:HasWaterPits()`（PC = bit5）
在 Switch 上都没有同名访问器。它们的语义要靠**引擎自己的位测试**来锚定 ——
`tbnz/tbz w?, #N`、`ubfx`、或 `and w?, w?, #(1<<N)` 都是"这一位有独立含义"的直接证据。

局限：只做**指令窗口**匹配（读到该偏移后 12 条指令内出现位测试），
不是数据流分析 ⇒ 每条命中都要再用 `tools/nro_disasm.py` 复核。
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
WINDOW = 12


def main(argv):
    pool = int(argv[0], 0) if argv else 0x50
    load_mnemonics = []
    for mask, expect, name, scale, field in (
        (0xFFC00000, 0x39400000, "ldrb w", 1, "u12"),
        (0xFFC00000, 0xB9400000, "ldr  w", 4, "u12"),
    ):
        load_mnemonics.append((mask, expect, name, scale, field))

    data = NRO.read_bytes()
    _so, symbols = ns.parse_dynamic_symbols(data)
    defined = sorted((s.file_offset, s.name) for s in symbols.values()
                     if s.is_defined and s.file_offset is not None)
    keys = [o for o, _ in defined]

    def owner_of(off):
        i = bisect_right(keys, off) - 1
        return defined[i][1] if i >= 0 else "<无符号>"

    words = struct.unpack_from(f"<{len(data)//4}I", data, 0)
    hits = []
    for i, word in enumerate(words):
        for mask, expect, _name, scale, field in load_mnemonics:
            if word & mask != expect:
                continue
            if ((word >> 10) & 0xFFF) * scale != pool:
                continue
            rt = word & 0x1F
            # 在窗口内找同一寄存器的位测试
            for j in range(i + 1, min(i + 1 + WINDOW, len(words))):
                w = words[j]
                if (w & 0x7E000000) == 0x36000000 and (w & 0x1F) == rt:      # tbz/tbnz w?
                    bit = ((w >> 26) & 0x20) | ((w >> 19) & 0x1F)
                    hits.append((i * 4, owner_of(i * 4), f"tbz/tbnz bit{bit}"))
                elif (w & 0x7F000000) == 0x12000000 and (w & 0x1F) == rt and ((w >> 16) & 0x3F) == 0x33:
                    hits.append((i * 4, owner_of(i * 4), f"and #0x{((w >> 10) & 0x1FFF):x}"))
                elif (w & 0xFF800000) == 0x53000000 and (w & 0x1F) == rt:    # ubfx/ubfm
                    hits.append((i * 4, owner_of(i * 4), f"ubfx w{rt}"))
    seen = set()
    for off, owner, what in sorted(hits):
        key = (off, what)
        if key in seen:
            continue
        seen.add(key)
        print(f"  0x{off:06X}  {what:>16}  ← {owner}")
    print(f"\n共 {len(seen)} 条")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
