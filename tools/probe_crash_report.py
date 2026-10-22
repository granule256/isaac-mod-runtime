#!/usr/bin/env python3
"""在给定的 epoch 秒区间里，逐秒探测卡上有没有那一份以撒崩溃报告。

为什么要它：`fs.ls /atmosphere/crash_reports` 有硬上限 200 条且**顺序任意**，
目录里几百条 ⇒ **最新那份通常不在你看到的那 200 条里**，而崩溃报告文件名 = 精确到秒的时间戳，
没法用通配符。既然我们已经知道"崩在几点到几点之间"，就逐秒 `fs.stat` 扫一遍。

用法：python3 /tmp/probe_crash.py <起始epoch> <结束epoch> [program_id]
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

NXC_DIR = Path('/Users/kelinls/code/github/KELI-NX')


def stat(remote: str) -> bool:
    result = subprocess.run(
        [sys.executable, 'pc/nxc.py', '--json', f'fs.stat path={remote}'],
        capture_output=True, text=True, cwd=NXC_DIR,
        env=dict(os.environ, NXC_DEVICE_IP='192.168.124.11'))
    # ★ 判据是回包的 header：`OK 1` = 文件在、`ERR 404 not-found` = 不在。
    #   客户端自己的 returncode 一直是 0（连上了就算成功），不能拿它当判据。
    return '"header": "OK' in result.stdout


def main(argv: list[str]) -> int:
    start = int(argv[1])
    end = int(argv[2])
    program = argv[3] if len(argv) > 3 else '010021c000b6a000'
    hits: list[int] = []
    for ts in range(start, end + 1):
        remote = f'/atmosphere/crash_reports/{ts:011d}_{program}.log'
        if stat(remote):
            print(f'HIT {remote}', flush=True)
            hits.append(ts)
        if ts % 60 == 0:
            print(f'...扫到 {ts}（{ts - start}/{end - start}）', flush=True)
    print(f'命中 {len(hits)} 份：{hits}', flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv))
