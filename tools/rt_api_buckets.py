#!/usr/bin/env python3
"""按**接口**点名 API 耗时（诊断包专用；`mem.*` 链，不冻结游戏）。

## 前置

* 卡上必须是**诊断包**（`PERF_API_WRAPPER=1 DIAGNOSTIC_PROBES=0` 构建）——
  生产包的 `g_RuntimePerfApiBuckets` 恒空（包装默认关，见 `owner_binding.hpp`）。
* ★ 读数前先 `clk.list` 自证超频（2397/1229/2400）——超频掉了读数会整体飘 ×2，
  本会话踩过"整轮读数在超频掉了的状态下采完才发现"（2026-10-11）。

## 用法

    python3 tools/rt_api_buckets.py --elf runtime/.diag2-api-artifacts/runtime.elf --seconds 60

产出 = 按"窗口内合计 tick"降序的接口表：`µs/次`、`次/秒`、`µs/帧`（+ 引擎调用段那一段）。
与 `docs/分析-API层归因-三家模组调了哪些接口-20261011.md` 的全表**同一口径**
（DIG1 的读法脚本被系统清空过，本文件 = 2026-10-11 重建版）。
"""
import argparse
import struct
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from mem_sample_state import Device  # noqa: E402
from read_device_state_via_gdb import (  # noqa: E402
    INTERNAL_API_NAMES,
    PERF_API_BUCKET_COUNT,
    PERF_API_ENGINE_TAG,
    api_name,
)

TICKS_PER_US = 19.2
BUCKET_BYTES = 48  # key/count/ticks/maxTicks + bins[4]，与 RuntimePerfCallbackBucket 同构

#: ★ mem.read 单次读取上限 = **3072 字节**（2026-10-11 实测：3072 完整、3200/3584/4096/24576 只回
#: 256 字节的"头"——**不报错**，静默截断）。24576 = 8 × 3072，正好整段。
MEM_READ_CHUNK = 3072


def read_big(dev, address: int, total: int) -> bytes:
    """分段读（每段 ≤ 3072）——超大单次读会被设备**静默截断到 256 字节**。"""
    buffer = bytearray()
    while len(buffer) < total:
        piece = dev.read(address + len(buffer), min(MEM_READ_CHUNK, total - len(buffer)))
        if not piece:
            break
        buffer.extend(piece)
    return bytes(buffer)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--elf', required=True, help='卡上那一版对应的 runtime.elf')
    ap.add_argument('--seconds', type=float, default=40.0)
    args = ap.parse_args()

    dev = Device(args.elf)
    print(f'运行时基址 = {dev.base:#x}'
          f'（exl_main 自证{"通过" if dev.base_confirmed else "**失败**"}）')
    if not dev.base_confirmed:
        print('★ 基址自证失败 ⇒ 读数不可信，停。', file=sys.stderr)
        return 3

    addr_api = dev.base + dev.sym('g_RuntimePerfApiBuckets')
    addr_state = dev.base + dev.sym('g_ModMenuState')
    try:
        addr_overflow = dev.base + dev.sym('g_RuntimePerfApiBucketOverflow')
    except KeyError:
        addr_overflow = None

    want = PERF_API_BUCKET_COUNT * BUCKET_BYTES

    def snap():
        raw = read_big(dev, addr_api, want)
        rows = {}
        available = min(len(raw), want)
        if available < want:
            print(f'  ⚠ API 桶只读到 {available} / {want} 字节（设备回得比请求短）')
        for o in range(0, available - BUCKET_BYTES + 1, BUCKET_BYTES):
            k, c, t, m = struct.unpack_from('<QQQQ', raw, o)
            if c:
                rows[k] = [c, t, m]
        state = dev.read(addr_state, 4 * 200)
        driven = struct.unpack_from('<I', state, 34 * 4)[0] if len(state) >= 35 * 4 else None
        overflow = dev.u64(addr_overflow) if addr_overflow is not None else None
        return rows, driven, overflow

    a, d0, ov0 = snap()
    t0 = time.time()
    print(f'第一次采样：drivenFrames={d0}  overflow={ov0}  → 等 {args.seconds:.0f} 秒…')
    time.sleep(args.seconds)
    b, d1, ov1 = snap()
    t1 = time.time()

    dt = t1 - t0
    frames = (d1 - d0) if (d0 is not None and d1 is not None) else None
    print(f'窗口 = {dt:.1f} s，drivenFrames {d0} → {d1}'
          + (f'（Δ={frames}，{frames / dt:.1f} f/s）' if frames is not None else '（Δ读不到）'))
    if ov0 is not None and ov1 is not None:
        print(f'g_RuntimePerfApiBucketOverflow {ov0} → {ov1}（Δ={ov1 - ov0}；非 0 = 桶溢出，读数不全）')

    # 合并两个相：非引擎段 = "整个处理器"，引擎段（bit32）= "其中引擎调用那一段"。
    totals: dict[int, list[int]] = {}
    engine: dict[int, int] = {}
    for k in set(a) | set(b):
        ca, ta, _ = a.get(k, [0, 0, 0])
        cb, tb, _ = b.get(k, [0, 0, 0])
        dc, dticks = cb - ca, tb - ta
        if dc <= 0:
            continue
        ident = k & 0xFFFFFFFF
        if k & PERF_API_ENGINE_TAG:
            engine[ident] = engine.get(ident, 0) + dticks
        else:
            totals[ident] = [dc, dticks]

    rows = sorted(((v[1], v[0], ident) for ident, v in totals.items()), reverse=True)
    print()
    print(f'{"接口":44s} {"Δ次":>8s} {"次/秒":>8s} {"µs/次":>9s} {"µs/帧":>8s} {"引擎段µs/帧":>11s}')
    print('-' * 96)
    for dticks, count, ident in rows:
        name = INTERNAL_API_NAMES.get(ident) or api_name(ident)
        upc = dticks / TICKS_PER_US / count
        rate = count / dt
        upf = (dticks / TICKS_PER_US / frames) if frames else None
        eng = engine.get(ident, 0)
        engf = f'{eng / TICKS_PER_US / frames:11.2f}' if (frames and eng) else '          -'
        print(f'{name:44s} {count:8d} {rate:8.1f} {upc:9.3f}'
              f' {(f"{upf:8.2f}" if upf is not None else "     N/A")} {engf}')
    total_us = sum(r[0] for r in rows) / TICKS_PER_US
    tail = f'—— 合计：{total_us / dt:.0f} µs/s'
    if frames:
        tail += f'，{total_us / frames:.0f} µs/帧（帧预算 16667 µs 的 {total_us / frames / 16667 * 100:.1f}%）'
    print(tail)
    return 0


if __name__ == '__main__':
    sys.exit(main())
