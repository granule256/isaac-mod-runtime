#!/usr/bin/env python3
"""按固定间隔采样 Isaac 运行时的**模块状态面 + Font 计数**（走 NxConduit `mem.*`，**不冻结游戏**）。

为什么要有它（与 `read_device_state_via_gdb.py` 的分工）
--------------------------------------------------------
`read_device_state_via_gdb.py` 走 **GDB attach**，一次拿全所有字段，但：
* **attach 期间游戏是冻住的** ⇒ 采不到"随时间变化"；
* 调试桩在**同一个开机周期里会退化**（2026-10-10 实测：连着两次 `monitor get info` 与映射扫描
  都认不出模块，`运行时模块基址 = 0x0`，`--two-phase` 同样失败）。

而 `mem.read` **不冻结**、可以随便采多少次 ⇒ 要看"某个计数随时间涨不涨"
（批次 422 的 B 项：Font 块"活着 212 个"是稳定的 GC 水位，还是单调涨的泄漏）就得用这条。
★ 两者**互斥**：`mem.*` 与 PC 侧 GDB 抢同一个调试句柄，不能同时开。

地址怎么来（与 `players_watchdog.py` 同一套，**全程不需要 GDB**）
--------------------------------------------------------------
* 运行时模块基址 = `mem.info` 的模块列表里**最后一个**的 `base + size`，
  再用 `exl_main` 的序言字节（`fd7bbca9fd030091`）自证；
* 其余全是**本模块自己的符号偏移**，从 `runtime.elf` 的符号表读；
* 游戏模块基址也是从我们自己的符号 `g_EngineModuleBase` 里解出来的。

用法
----
    python3 tools/mem_sample_state.py --elf <runtime.elf> --selftest      # 不连设备，先自检
    python3 tools/mem_sample_state.py --elf <runtime.elf> --once          # 采一次
    python3 tools/mem_sample_state.py --elf <runtime.elf> --seconds 600 --interval 10

★ 只读：不写内存、不注入按键。
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import struct
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'tools'))

#: nxc CLI 的位置按顺序探测（可用环境变量 NXC_CLI 覆盖）。
NXC_CLI_CANDIDATES = (
    Path.home() / 'code' / 'github' / 'NXC' / 'pc' / 'nxc.py',
    Path.home() / 'code' / 'github' / 'KELI-NX' / 'pc' / 'nxc.py',
)

#: 游戏模块基址槽（游戏模块基址 + 它 ⇒ 存 `g_Game` 指针的那个槽）。
GAME_SLOT = 0xAAC698
FRAME_COUNT = 0x24F99C

#: ★★ 必须用**确定的全名**取符号，不许靠子串兜底。
#: 例（2026-10-10 自检当场抓到）：`g_FontStorageLive` 有两个子串候选 ——
#: `_ZN5isaac7runtime17g_FontStorageLiveE`（真身）与
#: `_ZN5isaac7runtime21g_FontStorageLivePeakE`（峰值）；子串兜底按字典序挑一个，
#: **可能一直读峰值却显示成"活着"**，而且读数看着完全正常。
#: 这张表与 `read_device_state_via_gdb.py` 里那份**同一口径**。
Mangled = {
    'g_ModMenuState': 'g_ModMenuState',
    'exl_main': 'exl_main',
    'g_LastNumPlayers': '_ZN5isaac7runtime16g_LastNumPlayersE',
    'g_EngineModuleBase': '_ZN10LuaRuntime12_GLOBAL__N_1L18g_EngineModuleBaseE',
    'g_FontStorageAllocations': '_ZN5isaac7runtime24g_FontStorageAllocationsE',
    'g_FontStorageLive': '_ZN5isaac7runtime17g_FontStorageLiveE',
    'g_FontStorageLivePeak': '_ZN5isaac7runtime21g_FontStorageLivePeakE',
    'g_FontStorageFailures': '_ZN5isaac7runtime21g_FontStorageFailuresE',
}

#: 采样本脚本**真正依赖**的那几格：编号 → 期望名字。
#: 只写依赖项，不抄全套 —— hpp 里一旦有人插/挪字段，这里会立刻炸，
#: 而不是安静地读错格（本项目按编号读状态面已经踩过一次）。
EXPECTED_FIELDS = {
    58: 'heapFreeBytes',
    59: 'heapUsedBytes',
    75: 'luaStateBytes',
    76: 'heapAllocatedBytes',
    77: 'heapFreeChunkCount',
    78: 'heapMmappedRegions',
    79: 'heapTopFreeBytes',
    80: 'imagePcxCacheUsedBytes',
    85: 'memNormalKiB',
    86: 'memHeapKiB',
    87: 'memCodeKiB',
    88: 'memMappedKiB',
    89: 'memPrivateKiB',
}

EXL_MAIN_PROLOGUE = bytes.fromhex('fd7bbca9fd030091')


# ---------------------------------------------------------------------------
# 状态面字段顺序：从 `mod_menu_native.hpp` 的 `// [NN]` 注释解析（**唯一真值源**）
# ---------------------------------------------------------------------------
def state_field_order() -> list[str]:
    src = (REPO / 'runtime' / 'source' / 'mod_menu_native.hpp').read_text(encoding='utf-8')
    rows = [(int(i), n) for n, i in
            re.findall(r'^\s*std::uint32_t\s+(\w+);\s*//\s*\[(\d+)\]', src, re.M)]
    rows.sort()
    return [n for _, n in rows]


def resolve_cli() -> Path:
    override = os.environ.get('NXC_CLI')
    if override:
        return Path(override)
    for path in NXC_CLI_CANDIDATES:
        if path.exists():
            return path
    raise SystemExit('找不到 nxc CLI；用 NXC_CLI=<pc/nxc.py> 指定')


def nxc(method: str, **params) -> dict:
    """调一次 nxc 平台方法，返回 JSON 数组的第一项。

    ★★ 判据：**回包必须以 `[` 开头才当 JSON**。原写法 `out.find('[')` 会在
    `连接失败：OSError: [Errno 51] Network is unreachable` 这种错误文本里
    **咬住 `[Errno` 那个 `[`**，于是把一句错误消息当数据解析（2026-10-10 真撞上）。
    ⇒ 现在解析不出来就**把原文端上来**，不猜。
    """
    cli = resolve_cli()
    py = os.environ.get('NXC_PYTHON', sys.executable)
    line = method if not params else method + ' ' + ' '.join(f'{k}={v}' for k, v in params.items())
    proc = subprocess.run([py, cli.name, '--json', line], cwd=str(cli.parent),
                          capture_output=True, text=True, timeout=60, check=False)
    out = (proc.stdout + proc.stderr).strip()
    if not out.startswith('['):
        raise RuntimeError(f'nxc 没返回 JSON（rc={proc.returncode}）；原文：{out[:400]}')
    try:
        parsed = json.loads(out)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f'nxc 回包不是合法 JSON（{exc}）；原文：{out[:400]}') from None
    return parsed[0]


class Device:
    """运行时模块基址自证 + 按符号读内存。"""

    def __init__(self, elf: str):
        sys.path.insert(0, str(REPO / 'tools'))
        import elf_syms
        self.syms = elf_syms.load_symbols(open(elf, 'rb').read())
        info = nxc('mem.info')
        mods = sorted((int(item['base'], 16), int(item['size'], 16))
                      for item in info['payload']
                      if isinstance(item, dict) and 'module' in item)
        if not mods:
            raise SystemExit(f'mem.info 没给出模块表：{info!r}')
        base, size = mods[-1]
        self.base = base + size          # 运行时模块是最后加载的那个 ⇒ 基址 = 最后一个模块的末尾
        probe = self.read(self.base + self.sym('exl_main'), 8)
        self.base_confirmed = probe == EXL_MAIN_PROLOGUE

    def sym(self, name: str) -> int:
        full = Mangled.get(name, name)
        if full in self.syms:
            return self.syms[full][0]
        hits = [k for k in self.syms if name in k]
        if len(hits) == 1:               # 唯一候选才敢用；多于一个**报错，不猜**
            return self.syms[hits[0]][0]
        raise KeyError(f'符号 `{name}` 解析不到或有 {len(hits)} 个候选：{[hex(self.syms[h][0]) + " " + h for h in hits]}')

    def read(self, addr: int, size: int) -> bytes:
        obj = nxc('mem.read', addr=hex(addr), size=size)
        for item in obj.get('payload', []):
            if isinstance(item, dict) and 'data' in item:
                return base64.b64decode(item['data'])
            if isinstance(item, str):
                try:
                    return base64.b64decode(item)
                except Exception:  # noqa: BLE001
                    pass
        return b''

    def u32(self, addr: int):
        blob = self.read(addr, 4)
        return struct.unpack('<I', blob)[0] if len(blob) >= 4 else None

    def u32s(self, addr: int, count: int):
        blob = self.read(addr, count * 4)
        return list(struct.unpack_from(f'<{count}I', blob, 0)) if len(blob) >= count * 4 else None

    def u64(self, addr: int):
        blob = self.read(addr, 8)
        return struct.unpack('<Q', blob)[0] if len(blob) >= 8 else None


def selftest(elf: str) -> int:
    """不连设备：校验字段编号映射 + 符号能否**按全名唯一**解析。"""
    problems: list[str] = []
    order = state_field_order()
    print(f'状态面字段数 = {len(order)}')
    for number, name in sorted(EXPECTED_FIELDS.items()):
        if number >= len(order):
            problems.append(f'[{number}] 越界（只有 {len(order)} 格）')
        elif order[number] != name:
            problems.append(f'[{number}] 期望 {name}，hpp 里是 {order[number]}')
    print('字段编号映射 ' + ('OK（核对了 %d 格）' % len(EXPECTED_FIELDS) if not problems else '**不对**'))

    import elf_syms
    syms = elf_syms.load_symbols(open(elf, 'rb').read())
    keys = list(syms)
    for want, full in Mangled.items():
        exact = [k for k in keys if k == full]
        fuzzy = [k for k in keys if want in k]
        if len(exact) == 1:
            print(f'  {want:28s} → {hex(syms[full][0])}')
        elif len(fuzzy) == 1:
            print(f'  {want:28s} → **全名没写对**（唯一候选 {fuzzy[0]}）')
            problems.append(f'{want} 的全名 `{full}` 解析不到；唯一候选是 {fuzzy[0]}')
        else:
            cand = ', '.join(f'{hex(syms[k][0])} {k}' for k in fuzzy)
            print(f'  {want:28s} → **解析不到**（{len(fuzzy)} 个候选：{cand}）')
            problems.append(f'{want} 有 {len(fuzzy)} 个候选，不许猜')
    if problems:
        print('★ 自检不通过：\n  - ' + '\n  - '.join(problems))
        return 1
    print('自检通过（不连设备）')
    return 0


def mb(value) -> str:
    return f'{value / 1048576:.1f}' if isinstance(value, int) else 'NA'


def main() -> int:
    ap = argparse.ArgumentParser(description='采样运行时状态面 + Font 计数（不冻结游戏）')
    ap.add_argument('--elf', required=True, help='卡上那一版对应的 runtime.elf')
    ap.add_argument('--ip', default=None, help='设备地址（默认取 device_access 的默认主机）')
    ap.add_argument('--interval', type=float, default=10.0)
    ap.add_argument('--seconds', type=float, default=300.0)
    ap.add_argument('--once', action='store_true')
    ap.add_argument('--selftest', action='store_true', help='不连设备：只校验映射与符号')
    args = ap.parse_args()

    if args.selftest:
        return selftest(args.elf)

    if args.ip:
        os.environ['ISAAC_DEVICE_HOST'] = args.ip
    import device_access
    host, _port, _user, _pwd = device_access.resolve_device(required=False)
    # ★ CLI 认的是 NXC_DEVICE_IP（不是 ISAAC_DEVICE_HOST）⇒ 必须显式传下去，
    #   否则它会去连自己的默认地址 192.168.1.50 并回一句"连接失败"。
    os.environ['NXC_DEVICE_IP'] = host
    print(f'设备 = {host}')

    order = state_field_order()
    dev = Device(args.elf)
    print(f'runtime.elf = {args.elf}')
    print(f'运行时基址 = {dev.base:#x}'
          f'（exl_main 自证{"通过" if dev.base_confirmed else "**失败**"}）｜状态面字段数 = {len(order)}')
    if not dev.base_confirmed:
        print('★ 基址自证失败 ⇒ 读数不可信，停。', file=sys.stderr)
        return 3

    idx = {name: i for i, name in enumerate(order)}
    addr_state = dev.base + dev.sym('g_ModMenuState')
    addr_font = {k: dev.base + dev.sym(k) for k in
                 ('g_FontStorageAllocations', 'g_FontStorageLive',
                  'g_FontStorageLivePeak', 'g_FontStorageFailures')}
    addr_lnp = dev.base + dev.sym('g_LastNumPlayers')
    addr_engbase = dev.base + dev.sym('g_EngineModuleBase')

    header = ('时间      帧计数  堆空闲  堆已用   Lua    其它  缓存[80] 分配[76] 空块 '
              '存活Font 峰值 失败 累计分配 玩家')
    print(header)
    print('-' * len(header))

    game_base = dev.u64(addr_engbase) or 0
    deadline = time.time() + args.seconds
    while True:
        f = dev.u32s(addr_state, len(order))
        if f is None:
            print('★ 状态面读不到（游戏没跑？）', file=sys.stderr)
            return 4
        live = dev.u32(addr_font['g_FontStorageLive'])
        peak = dev.u32(addr_font['g_FontStorageLivePeak'])
        fails = dev.u32(addr_font['g_FontStorageFailures'])
        allos = dev.u32(addr_font['g_FontStorageAllocations'])
        lnp = dev.u32(addr_lnp)
        frame = None
        if not game_base:                     # 起步时可能还没发布 ⇒ 每轮补试一次
            game_base = dev.u64(addr_engbase) or 0
        if game_base:
            # ★★ 要**解两次**：`game_base + 0xAAC698` 只是那个**槽**（存 `Game*` 指针变量的地址），
            #   再解一次才是 `Game*`。少解一次会拿到一个没映射的地址 ⇒ `mem.read` 回
            #   `ERR 500 read-failed rc=0x0000D401`（内核 InvalidAddress），
            #   而读数只是安静地显示 `NA`（2026-10-10 真撞上）。
            game = dev.u64(dev.u64(game_base + GAME_SLOT) or 0) or 0
            if game:
                frame = dev.u32(game + FRAME_COUNT)
        used, lua = f[idx['heapUsedBytes']], f[idx['luaStateBytes']]
        row = ' '.join((
            time.strftime('%H:%M:%S'),
            f'{frame if frame is not None else "NA":>8}',
            f'{mb(f[idx["heapFreeBytes"]]):>7}',
            f'{mb(used):>7}',
            f'{mb(lua):>6}',
            f'{mb(max(used - lua, 0)):>6}',
            f'{mb(f[idx["imagePcxCacheUsedBytes"]]):>8}',
            f'{mb(f[idx["heapAllocatedBytes"]]):>8}',
            f'{f[idx["heapFreeChunkCount"]]:>5}',
            f'{live if live is not None else "NA":>8}',
            f'{peak if peak is not None else "NA":>5}',
            f'{fails if fails is not None else "NA":>5}',
            f'{allos if allos is not None else "NA":>8}',
            f'{lnp if lnp is not None else "NA":>4}',
        ))
        print(row, flush=True)
        if args.once or time.time() >= deadline:
            break
        time.sleep(args.interval)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
