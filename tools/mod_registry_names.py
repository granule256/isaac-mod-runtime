#!/usr/bin/env python3
"""列出这台 Switch 上**我们运行时自己发现到的模组**（名字 + 顺序 + 是否活动）。**只读。**

为什么需要它
------------
2026-10-08 查掉帧时，回调耗时桶打出来的是 `[#17 代1]` 这种**属主编号**，光看编号点不了名
（"哪一家在每帧烧 1.6 ms"是整件事的关键）。这份清单就是"编号 ↔ 名字"的那半张表。

数据来源（**不是**自己扫目录，是读运行时内存里那份**发现结果**）
--------------------------------------------------------------
`mod_menu_api.cpp` 里的静态数组：`std::array<MenuEntry, 32> g_entries`、
`MenuEntry { std::array<char,256> directory; bool active; }`
⇒ **步长 257**（`kModDirectoryCapacity = 256` + 1 字节 bool），
自带自检：符号大小 = 32 × 257 = **8224** ✓（`nm` 一看就知道布局对不对）。
条目数在 `g_entryCount`（u64）。

★ 口径提醒：这是**运行时发现顺序**（字母序），**不一定**等于回调桶里那个属主编号的顺序
（2026-10-08 实测：桶里 `#19` 的文件名是 `p1probe/main.lua`、`#21` 是 `whatsmydps/main.lua`，
而本清单里 p1probe = [13]、whatsmydps = [17] ⇒ **两套编号不是一回事**）。⇒ 用它的办法是：
先拿"某个属主编号确凿地属于谁"（例如 Lua 错误历史里带 owner 的那条）去反推偏移量。

用法
----
    export NXC_DEVICE_IP=192.168.124.11
    python3 tools/mod_registry_names.py --elf dist/change-archive-<日>/<批>-*/runtime.elf
"""
from __future__ import annotations

import argparse
import os
import struct
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / 'tools'))
sys.path.insert(0, '/tmp')          # /tmp/nxc_mem.py

ENTRY_STRIDE = 257        # std::array<char,256> + bool，对齐 1 ⇒ 257
ENTRY_COUNT = 32          # kModManifestCapacity


def main() -> int:
    ap = argparse.ArgumentParser(description='列出运行时发现到的模组（只读）')
    ap.add_argument('--elf', default=None)
    ap.add_argument('--ip', default=os.environ.get('NXC_DEVICE_IP', '192.168.124.11'))
    args = ap.parse_args()

    os.environ['NXC_DEVICE_IP'] = args.ip
    import nxc_mem

    elf = args.elf
    if elf is None:
        cands = sorted(REPO.glob('dist/change-archive-*/[0-9]*-*/runtime.elf'))
        if not cands:
            print('找不到 runtime.elf，请用 --elf 指定', file=sys.stderr)
            return 2
        elf = str(cands[-1])
    dev = nxc_mem.Device(elf)
    if not dev.base_confirmed:
        print('★ 运行时基址自证失败 ⇒ 读数不可信，停。', file=sys.stderr)
        return 3

    def u64(a: int) -> int:
        b = dev.read(a, 8)
        return struct.unpack('<Q', b)[0] if len(b) >= 8 else 0

    base = dev.base + dev.sym('g_entries')
    count = u64(dev.base + dev.sym('g_entryCount'))
    print(f'runtime.elf = {elf}')
    print(f'g_entries @ {base:#x}（步长 {ENTRY_STRIDE}，容量 {ENTRY_COUNT}）｜g_entryCount = {count}')
    for index in range(min(int(count), ENTRY_COUNT)):
        blob = dev.read(base + index * ENTRY_STRIDE, ENTRY_STRIDE)
        if len(blob) < ENTRY_STRIDE:
            print(f'  [{index + 1:2d}] （读不到）')
            continue
        name = blob[:256].split(b'\0')[0].decode('utf-8', 'replace')
        print(f'  [{index + 1:2d}] active={blob[256]} {name}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
