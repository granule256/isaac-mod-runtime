#!/usr/bin/env python3
"""一次性探针：对照"引擎的 `Level+0x2d18` 映射表"与"扫描 GridIndex 相等"两种房间定位法。

背景（2026-09-19）：`Level:GetCurrentRoomDesc()` 给出**空句柄** ⇒ GoodTrip 的
`floor.lua:220` `link[here]` 报 "table index is nil"。

引擎自己的解析法（`Level::GetRoomByIdx` 反汇编，`0x3dc5c8` 起）：
    slot = *(int32*)(Level + 0x2d18 + (dim*169 + gridIndex)*4)
    descriptor = Level + 0x18 + slot*0x100        （slot < 0 ⇒ 引擎返回它自己的空描述符）
我们当前的实现是"扫描 `+0x00 == GridIndex`"。历史记录说探针**否证**过映射表
（`docs/问题与解决记录.md:8457`），但那个结论与本次反汇编冲突 ⇒ 现场读一次定论。

只 attach 一次，用完 detach。
"""

from __future__ import annotations

import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import read_device_state_via_gdb as R  # noqa: E402

GAME_SLOT_OFFSET = 0xAAC698        # kGameOwnerGlobalSlotOffset（相对游戏模块基址）
LEVEL_CURRENT_IDX = 0x21558        # kLevelCurrentRoomIndexOffset
LEVEL_DIMENSION = 0x21560          # kLevelCurrentRoomDimensionOffset
LEVEL_COUNT = 0x21510              # 已分配房间数
MAP_TABLE = 0x2D18                 # 引擎的"网格下标 → 槽位号"表（int32，3×169）
DESC_BASE = 0x18
DESC_STRIDE = 0x100


def read_values(session, address: int, count: int, fmt: str) -> list[int | None]:
    """`x/N<fmt>` → 值列表（读不到的位置给 None，**不中断整轮**）。

    ★ 注意：gdb 每行形如 `0xADDR:\t0xVALUE` —— 第一版用 `findall("0x…")` 取到的是行首的
    **地址**，于是整份读数变成"值 = 我请求的地址"，看起来还特别像指针（差点据此下错结论）。
    """
    out = session.command(f'x/{count}{fmt} 0x{address:x}')
    values: list[int | None] = []
    for line in out.splitlines():
        head, sep, rest = line.partition(':')
        if not sep or not head.strip().startswith('0x'):
            continue
        match = re.search(r'0x([0-9a-fA-F]+)', rest)
        if match:
            values.append(int(match.group(1), 16))
        elif 'Cannot access' in rest or 'out of bounds' in rest:
            values.append(None)
    return values


def read_one(session, address: int, fmt: str = 'g') -> int | None:
    values = read_values(session, address, 1, fmt)
    return values[0] if values else None


def u32(value: int | None) -> int | None:
    return None if value is None else value & 0xFFFFFFFF


def s32(value: int) -> int:
    v = value & 0xFFFFFFFF
    return v - (1 << 32) if v & 0x80000000 else v


def main() -> int:
    session = R.GdbSession()
    try:
        session.command('target extended-remote 192.168.124.11:22225')
        pid = R.parse_processes(session.command('info os processes')) or 0
        if not pid:
            print('没找到正在运行的 Application')
            return 3
        module, plugin, game = R.parse_bases(session.command('monitor get info'))
        session.command(f'attach {pid}')
        elf = R.ROOT / R.DEFAULT_ELF
        if not module or not game:
            scanned_module, scanned_game = R.locate_by_scan(session, elf)
            module = module or scanned_module
            game = game or scanned_game
        print(f'模块基址=0x{module or 0:x}  游戏模块基址=0x{game or 0:x}')
        if not game:
            print('游戏模块基址没取到')
            return 3

        slot = game + GAME_SLOT_OFFSET
        owner = read_one(session, slot)
        level = read_one(session, owner or 0)
        print(f'槽 0x{slot:x} → owner=0x{owner or 0:x} → Level/Game=0x{level or 0:x}')
        if not level:
            print('Level 没取到 ⇒ 游戏可能还没进局')
            return 3

        idx = u32(read_one(session, level + LEVEL_CURRENT_IDX, 'w')) or 0
        dim = u32(read_one(session, level + LEVEL_DIMENSION, 'w')) or 0
        count = u32(read_one(session, level + LEVEL_COUNT, 'w')) or 0
        print(f'当前网格下标 = {idx}；维度 = {dim}；已分配房间数（+0x21510）= {count}')

        # 整表一次读回：3 个维度 × 169 = 507 个 int32（2028 字节）。
        raw_map = read_values(session, level + MAP_TABLE, 507, 'wx')
        if len(raw_map) < 169:
            print(f'⚠ 映射表只读到 {len(raw_map)} 项（预期 507）—— 下面结论要打折')
        dim0 = [s32(v) for v in raw_map[:169] if v is not None]
        print(f'映射表读回 {len(raw_map)} 项')

        print('\n逐槽位（+0x00 GridIndex / +0x04 SafeGridIndex / +0x08 ListIndex）：')
        allocated: list[tuple[int, int]] = []
        for s in range(0, 40):
            base = level + DESC_BASE + s * DESC_STRIDE
            g = u32(read_one(session, base + 0x00, 'w'))
            safe = u32(read_one(session, base + 0x04, 'w'))
            li = u32(read_one(session, base + 0x08, 'w'))
            if g is None:
                print(f'  slot{s:2d}  读不到')
                continue
            if g != 0xFFFFFFFF and g <= 0xFFFF:
                allocated.append((s, g))
            tag = '  ← 扫描命中（GridIndex == 当前下标）' if g == idx else ''
            if tag or s < count + 3:
                print(f'  slot{s:2d}  Grid={g:10d}  Safe={safe}  List={li}{tag}')

        print('\n★ 交叉验证（dim=0）：映射表是否满足 map[槽位的 GridIndex] == 该槽位号？')
        agree, disagree = 0, []
        for s, g in allocated:
            mapped = dim0[g] if g < len(dim0) else None
            if mapped == s:
                agree += 1
            else:
                disagree.append((f'slot{s}', f'grid{g}', f'map={mapped}'))
        print(f'  {len(allocated)} 个已分配槽位：一致 {agree}，不一致 {disagree}')

        print(f'\n★ 映射表[当前网格下标 {idx}] = {dim0[idx] if idx < len(dim0) else "越界"}')
        print('★ 映射表里 >=0 的条目（dim0，前 24 条）：')
        entries = [(i, v) for i, v in enumerate(dim0) if v >= 0]
        print(f'  共 {len(entries)} 条：{entries[:24]}')
        session.command('detach')
    finally:
        session.close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
