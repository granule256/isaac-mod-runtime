#!/usr/bin/env python3
"""把本地一棵目录写到设备上 —— 走 NxConduit 的 `fs.write`，**不需要 FTP**。

为什么写它（2026-10-06 夜）：设备上的 FTP 只在相册进程里、一进游戏就没了，
而 NxConduit（端口 47800）是常驻的。它的 `fs.copy` 只收**文件**（目录会回 `ERR 404 cannot-open-src`），
所以整棵目录要自己逐文件写：`fs.mkdir` 逐级建目录 + `fs.write`（base64）分块写。

用法：python3 /tmp/nxc_put_tree.py <本地目录> <设备上的目标目录>
"""
import base64
import subprocess
import sys
from pathlib import Path

NXC_DIR = Path('/Users/kelinls/code/github/KELI-NX')
#: 每块的原始字节数。
#: ★ 2026-10-06 实测：协议**一条命令行装不下长载荷** —— 12000 字节（base64 约 16 KB）会被拒
#:   （`fs.write` 报 `[…]` 截断的错误）。降到 **2000 字节**（base64 约 2.7 KB/行）后稳定。
CHUNK_BYTES = 2000


def call(*commands: str) -> tuple[int, str]:
    """跑一次 PC 侧客户端（`--json` 便于解析），返回 (返回码, 输出)。

    ★★ 2026-10-06 的坑（花了一轮才发现）：**不能用 `'ERR' in 输出` 判失败** ——
    `--json` 的输出里**会回显整条命令**（`>>> fs.write ... data=<base64>`），
    而 base64 正文**碰巧可能含 "ERR"** ⇒ 被误判成失败（当时表现为"某个大文件突然传不动"）。
    ⇒ 正确做法：先**剔掉以 `>>>` 开头的回显行**，再判 `ERR`；并以**返回码**为准。
    """
    result = subprocess.run([sys.executable, 'pc/nxc.py', '--json', *commands],
                            capture_output=True, text=True, cwd=NXC_DIR)
    output = (result.stdout + result.stderr).strip()
    body = '\n'.join(line for line in output.splitlines() if not line.startswith('>>>'))
    return result.returncode, body


def ensure_dir(remote_dir: str) -> None:
    """逐级建目录（平台的 `fs.mkdir` 只建一级，已存在算成功）。"""
    parts = [piece for piece in remote_dir.split('/') if piece]
    current = ''
    for piece in parts:
        current += '/' + piece
        call(f'fs.mkdir path={current}')


def put_file(local: Path, remote: str) -> int:
    data = local.read_bytes()
    ensure_dir(remote.rsplit('/', 1)[0])
    if not data:
        code, out = call(f'fs.write path={remote} data= append=0')
        return 0 if code == 0 else -1
    for offset in range(0, len(data), CHUNK_BYTES):
        block = data[offset:offset + CHUNK_BYTES]
        payload = base64.b64encode(block).decode('ascii')
        append = 1 if offset else 0
        code, out = call(f'fs.write path={remote} data={payload} append={append}')
        # ★★ **只按返回码判成败**（2026-10-06 第二课）：`--json` 的输出里含 base64 正文，
        #   而 base64 **可能碰巧含 "ERR"** ⇒ 任何"在输出里找 ERR"的判据都会误报。
        #   这一课是用"suddenly 传不动了、把卡上的 subsdk9 写了一半"换来的。
        if code != 0:
            print(f'  ✗ {remote} @{offset}: rc={code} {out[:300]}')
            return -1
    return len(data)


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__)
        return 2
    local_root = Path(sys.argv[1])
    remote_root = sys.argv[2].rstrip('/')
    files = sorted(path for path in local_root.rglob('*') if path.is_file())
    total_bytes = sum(path.stat().st_size for path in files)
    print(f'本地 {local_root}\n远端 {remote_root}\n{len(files)} 个文件 / {total_bytes} 字节')
    done = 0
    for index, path in enumerate(files, start=1):
        relative = path.relative_to(local_root).as_posix()
        written = put_file(path, f'{remote_root}/{relative}')
        if written < 0:
            print(f'✗ 中止（已完成 {done} 个）')
            return 1
        done += 1
        if index % 10 == 0 or index == len(files):
            print(f'  [{index}/{len(files)}] {relative} ({written} B)')
    print(f'✓ 完成 {done}/{len(files)} 个文件')
    return 0


if __name__ == '__main__':
    sys.exit(main())
