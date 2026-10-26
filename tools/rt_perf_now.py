#!/usr/bin/env python3
"""按属主点名回调税（mem.* 链，不冻结游戏）。

★ 读数前先 `clk.list` 自证超频（2397/1229/2400）——超频掉了读数会整体飘 ×2，本会话踩过
  "整轮读数在超频掉了的状态下采完才发现"（2026-10-11）。

原 /tmp/rt_perf_now.py（431 会话）被系统清空过；本文件 = 2026-10-11 重建版 + 431 探针容错，
2026-10-11 夜入库 tools/。

原 /tmp/rt_perf_now.py 被系统清空（交接文档第 5 节的坑），本文件按同样口径重建，
并加了 431 的 `g_EntityMethodMemoHits` / `g_EntityMethodMemo` 读数。

用法：
    python3 /tmp/rt_perf_now.py --elf runtime/.b431-artifacts/runtime.elf --seconds 40
"""
import argparse
import struct
import sys
import time

sys.path.insert(0, '/Users/kelinls/code/github/isaac mod/tools')
from mem_sample_state import Device  # noqa: E402

TICKS_PER_US = 19.2

EVENT_NAMES = {
    1: 'POST_UPDATE', 2: 'POST_RENDER', 4: 'POST_PEFFECT_UPDATE',
    9: 'POST_PLAYER_INIT', 13: 'INPUT_ACTION', 15: 'POST_GAME_STARTED',
    31: 'POST_PLAYER_UPDATE',
}

#: 431 两个探针是匿名命名空间的内部符号 —— 直接用全名，不走子串兜底
#: （`g_EntityMethodMemo` 是 `g_EntityMethodMemoHits` 的子串，子串会命中两个候选）。
MEMO_HITS_SYM = '_ZN5isaac7runtime12_GLOBAL__N_1L22g_EntityMethodMemoHitsE'
MEMO_TABLE_SYM = '_ZN5isaac7runtime12_GLOBAL__N_1L18g_EntityMethodMemoE'
MEMO_SLOTS = 64
MEMO_SLOT_BYTES = 42  # char name[40]; u8 view; u8 used;


def read_owner_names(dev) -> bytes:
    """只读配对ELF实际存在的表；缺符号或布局不明时不猜地址。"""
    symbol = dev.syms.get('g_ModOwnerNames')
    if not symbol or not symbol[1] or symbol[1] % 64:
        return b''
    raw = dev.read(dev.base + symbol[0], symbol[1])
    return raw if len(raw) == symbol[1] else b''


def owner_name(names: bytes, idx: int) -> str:
    if names is None or idx * 64 + 64 > len(names):
        return f'#{idx}'
    chunk = names[idx * 64: idx * 64 + 64]
    return chunk.split(b'\0')[0].decode('utf-8', 'replace')


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--elf', required=True)
    ap.add_argument('--seconds', type=float, default=40.0)
    args = ap.parse_args()

    dev = Device(args.elf)
    print(f'运行时基址 = {dev.base:#x}'
          f'（exl_main 自证{"通过" if dev.base_confirmed else "**失败**"}）')
    if not dev.base_confirmed:
        print('★ 基址自证失败 ⇒ 读数不可信，停。', file=sys.stderr)
        return 3

    addr_buckets = dev.base + dev.sym('g_RuntimePerfCallbackBuckets')
    addr_state = dev.base + dev.sym('g_ModMenuState')
    # 431 的探针只在 431+ 的 elf 里有 —— 老版本（428 等）就跳过，不报错。
    addr_memo_hits = (dev.base + dev.syms[MEMO_HITS_SYM][0]) if MEMO_HITS_SYM in dev.syms else None
    addr_memo_table = (dev.base + dev.syms[MEMO_TABLE_SYM][0]) if MEMO_TABLE_SYM in dev.syms else None

    def snap():
        raw = dev.read(addr_buckets, 64 * 48)
        if len(raw) != 64 * 48:
            raise RuntimeError(f'桶读取不完整：{len(raw)} B')
        rows = {}
        for o in range(0, 64 * 48, 48):
            k, c, t, m = struct.unpack_from('<QQQQ', raw, o)
            if c:
                rows[k] = [c, t, m]
        names = read_owner_names(dev)
        state = dev.read(addr_state, 4 * 200)
        driven = struct.unpack_from('<I', state, 34 * 4)[0] if len(state) >= 35 * 4 else None
        memo_hits = dev.u64(addr_memo_hits) if addr_memo_hits is not None else None
        memo = dev.read(addr_memo_table, MEMO_SLOTS * MEMO_SLOT_BYTES) if addr_memo_table is not None else b''
        memo_used = None
        if len(memo) == MEMO_SLOTS * MEMO_SLOT_BYTES:
            memo_used = sum(1 for i in range(MEMO_SLOTS) if memo[i * MEMO_SLOT_BYTES + 41])
        return rows, names, driven, memo_hits, memo_used

    a_rows, _names, d0, h0, u0 = snap()
    t0 = time.time()
    print(f'第一次采样：drivenFrames={d0}  memoHits={h0}  memoUsed={u0}'
          f'  → 等 {args.seconds:.0f} 秒…')
    time.sleep(args.seconds)
    b_rows, names, d1, h1, u1 = snap()
    t1 = time.time()

    dt = t1 - t0
    frames = (d1 - d0) if (d0 is not None and d1 is not None) else None
    print(f'窗口 = {dt:.1f} s，drivenFrames {d0} → {d1}'
          + (f'（Δ={frames}，{frames / dt:.1f} f/s）' if frames is not None else '（Δ读不到）'))
    if h0 is not None and h1 is not None:
        print(f'g_EntityMethodMemoHits {h0} → {h1}（Δ={h1 - h0}，{(h1 - h0) / dt:.1f}/s）'
              f'；记忆表已用槽 {u0} → {u1} / {MEMO_SLOTS}')

    keys = set(a_rows) | set(b_rows)
    lines = []
    total_dticks = 0
    for k in keys:
        ca, ta, ma = a_rows.get(k, [0, 0, 0])
        cb, tb, mb = b_rows.get(k, [0, 0, 0])
        dc, dti = cb - ca, tb - ta
        if dc <= 0:
            continue
        owner = (k >> 32) & 0xFFFF
        event = k & 0xFFFFFFFF
        upc = dti / TICKS_PER_US / dc
        rate = dc / dt
        upf = (dti / TICKS_PER_US / frames) if frames else None
        total_dticks += dti
        lines.append((dti, owner, event, dc, upc, rate, upf, mb, ma))

    lines.sort(reverse=True)
    print()
    print(f'{"属主":26s} {"事件":20s} {"Δ次":>7s} {"次/秒":>8s} {"µs/次":>8s} {"µs/帧":>8s} {"histMax":>9s}')
    print('-' * 92)
    for dti, owner, event, dc, upc, rate, upf, mb, ma in lines:
        upf_s = f'{upf:8.2f}' if upf is not None else '     N/A'
        print(f'{owner_name(names, owner):26s} {EVENT_NAMES.get(event, "#" + str(event)):20s}'
              f' {dc:7d} {rate:8.1f} {upc:8.3f} {upf_s} {mb / TICKS_PER_US:8.0f}µs')
    total_us = total_dticks / TICKS_PER_US
    tail = f'—— 合计：{total_us / dt:.0f} µs/s'
    if frames:
        per_frame = total_us / frames
        tail += f'，{per_frame:.0f} µs/帧（帧预算 16667 µs 的 {per_frame / 16667 * 100:.1f}%）'
    print(tail)
    return 0


if __name__ == '__main__':
    sys.exit(main())
