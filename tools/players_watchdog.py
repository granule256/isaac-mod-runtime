#!/usr/bin/env python3
"""盯"引擎里到底有几个玩家"的看门狗（NxConduit `mem.*`，**只读**）。

为什么要有它
------------
2026-10-08：用户报"选人界面上那个模组角色进局后，右上角多出一排人脸 + 红加号"，
并确认**没有第二个玩家**。那排东西是**引擎自己画的合作模式槽位条**（图集出处 = `gfx/ui/coop menu.png`），
它出现 ⇒ 那一刻引擎的玩家数组里**不止一个人**。可是同一角色今天新开一局实测是 **1 个**（见
`docs/诊断-模组角色Template的口袋道具与GetName欠账-20261008.md` §九）⇒ 说明它是**偶发/瞬时**的，
必须"当它发生时正好在读"。

它读什么
--------
* `g_LastNumPlayers`（我们运行时里 `Game:GetNumPlayers()` 最后一次的返回值 —— 模组看到的就是它）；
* 引擎的 `vector<Entity_Player*>`：`Game*` ← `*(*(g_EngineModuleBase + 0xAAC698))`，
  元素在 `Game + 0x25C50`（begin）/ `+0x25C58`（end）；
* 每个玩家的 **玩家类型**（`kEntityPlayerTypeOffset` 那条，若读得到）与**手柄号**（`+0x19EC`）。

用法
----
    # 一直盯，玩家数不是 1 就喊（并抓一张图到 /config/nxc/watch.jpg）
    python3 tools/players_watchdog.py --elf dist/change-archive-<日>/<批>-*/runtime.elf --elf-path
    # 只盯 N 秒
    python3 tools/players_watchdog.py --elf <path> --seconds 600

★ 只读：不写内存、不注入按键；`mem.*` 与 PC 侧 GDB **互斥**（别同时开调试桩）。
★ 需要设备地址：`export NXC_DEVICE_IP=192.168.124.11`（或用 `--ip`）。
"""
from __future__ import annotations

import argparse
import os
import struct
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / 'tools'))
sys.path.insert(0, '/tmp')          # /tmp/nxc_mem.py（本会话写的设备侧内存小工具）

GAME_SLOT = 0xAAC698          # 游戏模块基址 + 它 ⇒ 存 `g_Game` 指针变量地址的那个槽
PLAYERS_BEGIN = 0x25C50       # Game + 它 ⇒ vector<Entity_Player*> 的 begin
PLAYERS_END = 0x25C58
FRAME_COUNT = 0x24F99C        # Game + 它 ⇒ 帧计数（u32，**冻住 = 暂停**）
CONTROLLER_INDEX = 0x19EC     # Entity_Player + 它 ⇒ 手柄号（kEntityPlayerControllerIndexOffset）
PLAYER_TYPE = 0x1738          # Entity_Player + 它 ⇒ 玩家类型（kEntityPlayerTypeOffset，没有 GetPlayerType 方法）


def main() -> int:
    ap = argparse.ArgumentParser(description='盯引擎玩家数（只读）')
    ap.add_argument('--elf', default=None, help='本机 runtime.elf（取符号偏移用）')
    ap.add_argument('--ip', default=os.environ.get('NXC_DEVICE_IP', '192.168.124.11'))
    ap.add_argument('--seconds', type=float, default=0, help='盯多久（0 = 一直盯）')
    ap.add_argument('--interval', type=float, default=0.5)
    ap.add_argument('--expect', type=int, default=1, help='期望的玩家数；不是这个值就喊')
    ap.add_argument('--shot', default='/config/nxc/watch.jpg', help='喊的时候抓图存到卡上这个路径')
    args = ap.parse_args()

    os.environ['NXC_DEVICE_IP'] = args.ip
    import nxc_mem  # noqa: E402  （/tmp/nxc_mem.py）

    elf = args.elf
    if elf is None:
        cands = sorted(REPO.glob('dist/change-archive-*/[0-9]*-*/runtime.elf'))
        if not cands:
            print('找不到 runtime.elf，请用 --elf 指定', file=sys.stderr)
            return 2
        elf = str(cands[-1])
    dev = nxc_mem.Device(elf)
    if not dev.base_confirmed:
        print('★ 运行时基址自证失败（exl_main 序言不符）⇒ 读数不可信，停。', file=sys.stderr)
        return 3

    def u64(addr: int) -> int:
        b = dev.read(addr, 8)
        return struct.unpack('<Q', b)[0] if len(b) >= 8 else 0

    def u32(addr: int) -> int | None:
        b = dev.read(addr, 4)
        return struct.unpack('<I', b)[0] if len(b) >= 4 else None

    game_base = u64(dev.base + dev.sym('g_EngineModuleBase'))
    print(f'runtime.elf = {elf}')
    print(f'运行时基址 = {dev.base:#x}（自证通过）｜游戏模块基址 = {game_base:#x}')
    if game_base == 0:
        print('★ 游戏模块基址还没发布（游戏没跑 / 还没进局）⇒ 等它。', file=sys.stderr)

    last = None
    deadline = time.time() + args.seconds if args.seconds else None
    while deadline is None or time.time() < deadline:
        lnp = u32(dev.base + dev.sym('g_LastNumPlayers'))
        slot = u64(game_base + GAME_SLOT) if game_base else 0
        game = u64(slot) if slot else 0
        count, players = None, []
        if game:
            begin, end = u64(game + PLAYERS_BEGIN), u64(game + PLAYERS_END)
            if begin and end and end >= begin:
                count = (end - begin) // 8
                if 0 <= count <= 8:
                    players = [u64(begin + i * 8) for i in range(count)]
        stamp = time.strftime('%H:%M:%S')
        row = f'[{stamp}] GetNumPlayers={lnp} 引擎玩家数={count}'
        if count is not None and count != args.expect:
            details = []
            for i, p in enumerate(players):
                details.append(f'p{i}={p:#x} type={u32(p + PLAYER_TYPE)} ctrl={u32(p + CONTROLLER_INDEX)}')
            print(f'{row}  ★★ 不是 {args.expect}！' + ('  ' + ' | '.join(details) if details else ''), flush=True)
            if args.shot:
                os.system(f"cd /Users/kelinls/code/github/NXC/pc && NXC_DEVICE_IP={args.ip} "
                          f"python3 nxc.py 'screen.capture path={args.shot}' >/dev/null 2>&1")
                print(f'    已抓图到卡上 {args.shot}', flush=True)
        elif row != last:
            print(row, flush=True)
        last = row
        time.sleep(args.interval)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
