#!/usr/bin/env python3
"""量这台 Switch 上**以撒的真实帧率**（NxConduit `mem.*` 直读引擎帧计数，**只读、不冻结游戏**）。

为什么不用调试桩：`read_device_state_via_gdb.py` 要 attach，**attach 期间游戏是停的**，
而回调计时用的是真时间 ⇒ 一次 attach 会被算进某个回调里（历史"EID 平均 16.4 ms"就是这么被骗的，
见技能 `isaac-switch-perf-analysis` §四）。`mem.*` 读内存**不冻结游戏** ⇒ 可以边跑边量。

读什么
------
`Game*` ← `*(*(g_EngineModuleBase + 0xAAC698))`；帧计数 = `Game + 0x24F99C`（u32）。
★ 帧计数**几秒不动 = 游戏被暂停 / 被系统界面挡住**（2026-10-08 实测踩过：拔虚拟手柄会弹系统的
"手柄顺序"页，游戏就被压在后面，帧计数冻住）。所以这个工具同时是"游戏真的在前台跑吗"的判据。

用法
----
    export NXC_DEVICE_IP=192.168.124.11
    python3 tools/perf_frame_rate.py --elf dist/change-archive-<日>/<批>-*/runtime.elf
    python3 tools/perf_frame_rate.py --seconds 3 --samples 5     # 采样窗口 / 次数
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
sys.path.insert(0, '/tmp')          # /tmp/nxc_mem.py

GAME_SLOT = 0xAAC698
FRAME_COUNT = 0x24F99C


def frame_interval(t0: float, f0: int | None, t1: float,
                   f1: int | None) -> tuple[float, int, float] | None:
    """u32 前向差分兼容回绕；缺失、倒退/重置或无效时间不生成帧率。"""
    if f0 is None or f1 is None or t1 <= t0:
        return None
    frames = (f1 - f0) & 0xFFFFFFFF
    if frames >= 0x80000000:
        return None  # 短采样窗不可能前进半个 u32；通常是重新开局/计数重置。
    dt = t1 - t0
    return dt, frames, frames / dt


def main() -> int:
    ap = argparse.ArgumentParser(description='量真实帧率（只读）')
    ap.add_argument('--elf', default=None)
    ap.add_argument('--ip', default=os.environ.get('NXC_DEVICE_IP', '192.168.124.11'))
    ap.add_argument('--seconds', type=float, default=3.0, help='每个采样窗口的秒数')
    ap.add_argument('--samples', type=int, default=5)
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

    def u64(a: int) -> int | None:
        b = dev.read(a, 8)
        return struct.unpack('<Q', b[:8])[0] if len(b) >= 8 else None

    def u32(a: int) -> int | None:
        b = dev.read(a, 4)
        return struct.unpack('<I', b)[0] if len(b) >= 4 else None

    # ★★ `Game*` 要**解两层**：槽里放的是 `g_Game` **指针变量的地址**，再解一次才是对象。
    # （2026-10-08 第一版只解了一层 ⇒ 帧计数读到垃圾、采样一行都不打印。引擎自己也这么做：
    #  `HUD::Render` 是 `ldr x,[x,#0x698]` 之后再 `ldr x,[x]`。一级只作兜底。）
    # ★ 2026-10-09 更正：二级读取缺失时，槽地址不能当成 Game 对象。
    engine = u64(dev.base + dev.sym('g_EngineModuleBase'))
    slot = u64(engine + GAME_SLOT) if engine else None
    game = u64(slot) if slot else None
    print(f'runtime.elf = {elf}')
    pointer_text = lambda value: '缺失' if value is None else f'{value:#x}'
    print(f'运行时基址 = {dev.base:#x}（自证通过）｜Game 槽 = {pointer_text(slot)}｜Game* = {pointer_text(game)}')
    if not game:
        print('★ Game* 缺失或为空：无法采样，不能据此判断游戏状态。', file=sys.stderr)
        return 4

    samples: list[tuple[float, int | None]] = []
    for index in range(args.samples + 1):
        frame = u32(game + FRAME_COUNT)
        samples.append((time.monotonic(), frame))
        if index < args.samples:
            time.sleep(args.seconds)
    rates: list[float] = []
    total_seconds = total_frames = 0
    for (t0, f0), (t1, f1) in zip(samples, samples[1:]):
        interval = frame_interval(t0, f0, t1, f1)
        if interval is None:
            print('  采样窗口缺失、计数重置或时间无效 ⇒ 不计算帧率')
            continue
        dt, frames, rate = interval
        total_seconds += dt
        total_frames += frames
        rates.append(rate)
        print(f'  {dt:.2f}s 内 {frames} 帧 ⇒ {rate:.1f} fps')
    if rates:
        print(f'⇒ 平均 {total_frames/total_seconds:.1f} fps（最低 {min(rates):.1f} / 最高 {max(rates):.1f}）')
        if max(rates) < 1.0:
            print('★ 帧计数几乎不动 ⇒ 游戏被暂停 / 被系统界面挡住，**这一组数不代表帧率**。')
    else:
        print('★ 没有有效采样窗口，无法计算帧率。', file=sys.stderr)
        return 5
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
