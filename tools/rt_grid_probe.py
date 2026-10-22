#!/usr/bin/env python3
"""读 `Room:GetGridEntity` 的**子阶段探针**（批次 435；只在 `PERF_API_WRAPPER=1` 的诊断包里存在）。

口径（`remaining_api.cpp` 的 `g_GridEntityProbe*`，`extern "C"` 无修饰名）：
  * `ChainTicks` = `ResolveCurrentLevel` + `ReadCurrentGameRoom`（"解析链"）；
  * `RestTicks`  = 其余（读表项 + `PushGridEntityAtSlot` 里的 `lua_newuserdata` + 元表）。
19.2 tick = 1 µs。`mem.*` 链、不冻结游戏。★ 读数前先 `clk.list` 自证超频。

用法：
    python3 tools/rt_grid_probe.py --elf runtime/.diag3-probe-artifacts/runtime.elf --seconds 30
"""
import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from mem_sample_state import Device  # noqa: E402

TICKS_PER_US = 19.2
SYM_CALLS = 'g_GridEntityProbeCalls'
SYM_CHAIN = 'g_GridEntityProbeChainTicks'
SYM_REST = 'g_GridEntityProbeRestTicks'


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--elf', required=True, help='卡上那一版对应的 runtime.elf（435 探针包）')
    ap.add_argument('--seconds', type=float, default=30.0)
    args = ap.parse_args()

    dev = Device(args.elf)
    print(f'运行时基址 = {dev.base:#x}'
          f'（exl_main 自证{"通过" if dev.base_confirmed else "**失败**"}）')
    if not dev.base_confirmed:
        return 3

    addresses = {}
    for name in (SYM_CALLS, SYM_CHAIN, SYM_REST):
        try:
            addresses[name] = dev.base + dev.sym(name)
        except KeyError:
            print(f'缺符号 {name} —— 这个包不是 435 探针包（或 PERF_API_WRAPPER 没开）？停。',
                  file=sys.stderr)
            return 3

    def snap():
        return {name: dev.u64(addr) for name, addr in addresses.items()}

    a = snap()
    t0 = time.time()
    print(f'第一次采样：{a}  → 等 {args.seconds:.0f} 秒…')
    time.sleep(args.seconds)
    b = snap()
    dt = time.time() - t0

    calls = b[SYM_CALLS] - a[SYM_CALLS]
    chain = b[SYM_CHAIN] - a[SYM_CHAIN]
    rest = b[SYM_REST] - a[SYM_REST]
    total = chain + rest
    print(f'窗口 = {dt:.1f} s；调用 {calls}（{calls / dt:.0f}/s）')
    if calls <= 0:
        print('★ 窗口里一次调用都没记到 —— 游戏在跑吗？在局内吗？')
        return 2
    print(f'解析链（ResolveCurrentLevel + ReadCurrentGameRoom）：'
          f'{chain / TICKS_PER_US / calls:.3f} µs/次'
          f'（占 {chain / total * 100:.0f}%；摊 {chain / TICKS_PER_US / dt:.0f} µs/s）')
    print(f'读表+push（lua_newuserdata 等）：'
          f'{rest / TICKS_PER_US / calls:.3f} µs/次'
          f'（占 {rest / total * 100:.0f}%；摊 {rest / TICKS_PER_US / dt:.0f} µs/s）')
    print(f'合计 {total / TICKS_PER_US / calls:.3f} µs/次'
          f'；折每帧 {total / TICKS_PER_US / dt / 60.2:.1f} µs/帧（@60.2fps）')
    return 0


if __name__ == '__main__':
    sys.exit(main())
