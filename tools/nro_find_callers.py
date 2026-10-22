#!/usr/bin/env python3
"""只读取证：扫 `Repentance.nro` 的 `.text`，找出**所有 `bl` 到某个（或某几个）函数的调用点**，
并按"最近的已定义符号"归属调用者。

为什么需要它：这一批要判的字段（BossID / 先访 / 伏击完成 / 两个种子）在 Switch 上**没有同名访问器**，
只能靠"谁消费了这个值"来找偏移。而消费点往往是"把 Room 的某个成员喂给某个具名引擎函数"，
所以先定位那个具名函数的**全部调用点**，再逐个看它的实参是怎么算出来的。

局限（不许把"没扫到"当成"不存在"）：
  * 只认 `bl`（`0x94...`）与 `b`（`0x14...`）；**不认** `blr`/函数指针表/PLT 之外的间接调用；
  * 调用者归属是"不晚于该地址的最近一个已定义符号"，长函数里的命中可能挂在前一个符号上
    ⇒ 每条命中都要再交给 `tools/nro_disasm.py` 复核。

用法：
    python3 tools/nro_find_callers.py StartBossIntro
    python3 tools/nro_find_callers.py GetBoss  BossPool
"""
from __future__ import annotations

import struct
import sys
from bisect import bisect_right
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tools"))
import nro_symbols as ns  # noqa: E402
import nro_disasm as nd  # noqa: E402  (复用它的 PLT 桩解析)

NRO = (REPO / "The Binding of Isaac_ Afterbirth+ 1.7.9b [010021C000B6A800][v524288][UPD]"
       / "Program #0" / "1" / ".nro" / "Repentance.nro")


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    data = NRO.read_bytes()
    _soname, symbols = ns.parse_dynamic_symbols(data)
    defined = [(s.file_offset, s.name) for s in symbols.values()
               if s.is_defined and s.file_offset is not None]
    defined.sort()
    keys = [off for off, _ in defined]

    def owner_of(off: int) -> str:
        i = bisect_right(keys, off) - 1
        return defined[i][1] if i >= 0 else "<无符号>"

    # 目标既可能是"真函数"，也可能是**导入桩**（跨模块调用都走 PLT 桩）⇒ 两边都收。
    targets = {}
    for s in symbols.values():
        if s.is_defined and s.file_offset is not None:
            for kw in argv:
                if kw.lower() in s.name.lower():
                    targets.setdefault(s.name, s.file_offset)

    plt_slots, _data_slots = nd._relocation_maps(str(NRO))
    stub_names: dict[int, str] = {}
    for off in range(0, len(data) - 16, 4):
        name = nd._plt_import(data, off, plt_slots)
        if name is None:
            continue
        for kw in argv:
            if kw.lower() in name.lower():
                stub_names.setdefault(off, name)
                targets.setdefault(f"[stub] {name}", off)

    print(f"目标符号 {len(targets)} 个")
    for name, off in sorted(targets.items(), key=lambda kv: kv[1]):
        print(f"  {off:#08x}  {name}")
    if not targets:
        return 1

    by_off = {off: name for name, off in targets.items()}
    hits: dict[int, list[tuple[int, str]]] = {off: [] for off in by_off}
    for off in range(0, len(data) - 4, 4):
        word = struct.unpack_from("<I", data, off)[0]
        if (word & 0xFC000000) != 0x94000000:   # bl
            continue
        imm = word & 0x03FFFFFF
        if imm & 0x02000000:
            imm -= 0x04000000
        target = off + imm * 4
        if target in hits:
            hits[target].append((off, owner_of(off)))

    for off, name in sorted(by_off.items(), key=lambda kv: kv[1]):
        site = hits[off]
        print(f"\n===== {name} @ {off:#x} —— {len(site)} 个调用点 =====")
        for addr, owner in sorted(site):
            print(f"  0x{addr:06X}  ← {owner}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
