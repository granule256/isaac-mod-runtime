#!/usr/bin/env python3
"""走 NxConduit 按 fs.stat 的实际文件大小读回并计算 sha256。

用法：python3 tools/nxc_get_sha.py <设备路径> [期望字节数]
"""
import hashlib
import subprocess  # 离线模拟协议时使用相同进程入口。
import sys
from nxc_file_reader import blocks, file_size


def main():
    if len(sys.argv) not in (2, 3):
        print(__doc__)
        return 2
    try:
        remote = sys.argv[1]
        size = file_size(remote)
        if len(sys.argv) == 3 and int(sys.argv[2]) != size:
            raise ValueError(f'大小不符：实际 {size}，期望 {sys.argv[2]}')
        digest = hashlib.sha256()
        total = 0
        for block in blocks(remote, size):
            digest.update(block)
            total += len(block)
        if total != size:
            raise ValueError(f'读回大小不符：{total} / {size}')
        print(f'{remote}\n  {total} 字节  sha256={digest.hexdigest()}')
        return 0
    except (ValueError, OSError) as exc:
        print(f'✗ 读回失败：{exc}')
        return 1


if __name__ == '__main__': sys.exit(main())
