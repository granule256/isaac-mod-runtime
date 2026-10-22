#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从 Switch 镜像的 `_ZTV<类>` 反查**虚函数槽号**（批次 318 固化，2026-10-03）。

## 为什么需要它

`EngineCallShape` 那套"引擎方法行"要求"同名方法只有一个类实现"；而 `HUD:Update`（95 个实现）、
`GridEntity:Update`（同）、`EntityPlayer:GetShootingInput` 这类**名字完全没用** ——
唯一出路是走 **vtable 槽号**（本仓库的约定：`offset` 最高位置 1 = 按槽号虚调用、低 31 位 = 槽号；
`target = [对象首字 + 槽号*8]`，批 303 立、批 304 修正）。

槽号**看不出来、只能读出来**：

* vtable 在**文件里全是 0**，靠加载时的重定位填；
* 槽位用的是 **`R_AARCH64_ABS64`(257) + 符号索引** —— ★ **不是** `R_AARCH64_RELATIVE`
  （后者是"没有符号、只有 addend"那一类；`nro_symbols.parse_dynamic_relocations()` 会把
  `sym == 0` 的记录**跳过** ⇒ 用 RELATIVE 的做法在这里拿不到东西）；
* Itanium 布局：`[offset-to-top][typeinfo]` 之后 **`+0x10` 起是槽 0**。

## ★★★ 不许照抄 PC 的槽号

Itanium（Switch）在 vtable 开头放**两个**析构变体（`D2`/`D0`），MSVC（PC）只放一个
`scalar deleting destructor` ⇒ **PC 的槽号比 Switch 小 1**（批 303 实测：`CanShutDoors`
PC 第 17、Switch 第 18）。**槽号只能从这张表里读。**

Usage::

    python3 tools/nro_vtable_slot.py Entity                 # 列 _ZTVEntity 的槽表
    python3 tools/nro_vtable_slot.py Entity --slot 18        # 只看第 18 槽
    python3 tools/nro_vtable_slot.py Entity --find CanShutDoors   # 找某个函数的槽号
    python3 tools/nro_vtable_slot.py --find-all Update        # ★ 一次扫**所有** vtable 找这个名字
    python3 tools/nro_vtable_slot.py --list                   # 只看有哪些 _ZTV<类>
"""

from __future__ import annotations

import argparse
import bisect
import os
import sys
from dataclasses import dataclass

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "tools"))

import nro_symbols  # noqa: E402  (in-repo helper, stdlib only)

DEFAULT_NRO = os.path.join(
    REPO_ROOT,
    "The Binding of Isaac_ Afterbirth+ 1.7.9b [010021C000B6A800][v524288][UPD]"
    "/Program #0/1/.nro/Repentance.nro",
)

#: 槽 0 相对 vtable 起点的偏移（Itanium：`+0x0` offset-to-top、`+0x8` typeinfo）。
SLOT_ZERO_OFFSET = 0x10
#: 每个槽 8 字节（AArch64）。
SLOT_SIZE = 8
#: `R_AARCH64_ABS64` —— 槽位用的就是这一种（带符号索引）。
RELOCATION_ABS64 = 257
#: 一张 vtable 最多看多少个槽（兜底；正常靠"下一个符号的起点"界定）。
MAXIMUM_SLOTS = 4096


def mangle_vtable_name(class_name: str) -> str:
    """`Entity_NPC` → `_ZTVN15IsaacRepentance10Entity_NPCE`（Itanium 名字修饰）。"""
    return f"_ZTVN15IsaacRepentance{len(class_name)}{class_name}E"


@dataclass(frozen=True)
class Mirror:
    """一次解析、反复查（★ 早先每查一个类都要重解析一遍重定位 ⇒ 全表扫要几分钟）。"""

    symbols: dict
    slot_map: dict
    #: 所有已定义符号的起点（升序）—— 用来给一张 vtable 定长度。
    starts: list

    def upper_bound(self, vtable_offset: int):
        """`vtable_offset + 0x10` 之后**最近的**已定义符号起点。"""
        position = bisect.bisect_right(self.starts, vtable_offset + SLOT_ZERO_OFFSET)
        return self.starts[position] if position < len(self.starts) else None

    def read_slots(self, vtable_offset: int) -> list:
        """返回 `[(槽号, 符号名), …]`。

        ★ 必须有**上界**：`_ZTV` 在 `.data.rel.ro` 里是**紧挨着排**的，只靠"连续两个空槽"停不下来
        （本工具第一版就这么错的：`Entity` 的槽表一路走进了下一张表，于是 `--find` 报出 4 个槽）。
        """
        bound = self.upper_bound(vtable_offset)
        slots: list = []
        for index in range(MAXIMUM_SLOTS):
            address = vtable_offset + SLOT_ZERO_OFFSET + index * SLOT_SIZE
            if bound is not None and address >= bound:
                break
            name = self.slot_map.get(address)
            if name is not None:
                slots.append((index, name))
        return slots

    def vtable_names(self) -> list:
        """`[(符号名, 文件偏移), …]`，按地址升序。"""
        out = [
            (name, symbol.file_offset)
            for name, symbol in self.symbols.items()
            if name.startswith("_ZTV") and symbol.is_defined and symbol.file_offset is not None
        ]
        out.sort(key=lambda item: item[1])
        return out


def load(nro_path: str) -> Mirror:
    data = open(nro_path, "rb").read()
    _build_id, symbols = nro_symbols.parse_dynamic_symbols(data)
    _build_id, relocations = nro_symbols.parse_dynamic_relocations(data)
    slot_map: dict = {}
    for symbol_name, records in relocations.items():
        for record in records:
            if record.relocation_type == RELOCATION_ABS64:
                slot_map[record.offset] = symbol_name
    starts = sorted(
        symbol.file_offset for symbol in symbols.values()
        if symbol.is_defined and symbol.file_offset is not None
    )
    return Mirror(symbols=symbols, slot_map=slot_map, starts=starts)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="从 _ZTV<类> 反查虚函数槽号")
    parser.add_argument("class_name", nargs="?", help="类名（如 Entity_NPC）或完整 _ZTV 符号名")
    parser.add_argument("--nro", default=DEFAULT_NRO)
    parser.add_argument("--slot", type=int, help="只看这一个槽号")
    parser.add_argument("--find", help="按名字子串找槽号")
    parser.add_argument("--find-all", metavar="名字", help="★ 一次扫**所有** vtable 找这个名字")
    parser.add_argument("--list", action="store_true", help="只列出镜像里有哪些 _ZTV<类>")
    arguments = parser.parse_args(argv)

    if not os.path.isfile(arguments.nro):
        print(f"找不到 NRO：{arguments.nro}", file=sys.stderr)
        return 2
    mirror = load(arguments.nro)

    if arguments.find_all is not None:
        hits = 0
        for name, offset in mirror.vtable_names():
            found = [
                (index, slot_name) for index, slot_name in mirror.read_slots(offset)
                if arguments.find_all in slot_name
            ]
            if found:
                hits += len(found)
                print(f"=== {name} @ {offset:#x} ===")
                for index, slot_name in found:
                    print(f"  slot {index:<3} = {slot_name}")
        if hits == 0:
            print(f"全镜像的 vtable 里没有名字含 {arguments.find_all!r} 的槽", file=sys.stderr)
            return 1
        return 0

    if arguments.list or arguments.class_name is None:
        names = mirror.vtable_names()
        print(f"镜像里有 {len(names)} 张 _ZTV：")
        for name, offset in names:
            print(f"  {name}  @ {offset:#x}")
        return 0

    wanted = arguments.class_name
    if not wanted.startswith("_ZTV"):
        wanted = mangle_vtable_name(wanted)
    symbol = mirror.symbols.get(wanted)
    if symbol is None or not symbol.is_defined or symbol.file_offset is None:
        print(f"符号表里没有 {wanted}（用 --list 看有哪些）", file=sys.stderr)
        return 1

    slots = mirror.read_slots(symbol.file_offset)
    if arguments.slot is not None:
        found = [name for index, name in slots if index == arguments.slot]
        if not found:
            print(f"{wanted} 的槽 {arguments.slot} 没有 R_AARCH64_ABS64 记录", file=sys.stderr)
            return 1
        print(f"{wanted} @ {symbol.file_offset:#x}  slot {arguments.slot}  =  {found[0]}")
        return 0

    if arguments.find:
        hits = [(index, name) for index, name in slots if arguments.find in name]
        if not hits:
            print(f"{wanted} 里没有名字含 {arguments.find!r} 的槽", file=sys.stderr)
            return 1
        for index, name in hits:
            print(f"slot {index:<3} = {name}")
        return 0

    print(f"=== {wanted} @ {symbol.file_offset:#x}（{len(slots)} 个槽）===")
    for index, name in slots:
        print(f"  slot {index:<3} = {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
