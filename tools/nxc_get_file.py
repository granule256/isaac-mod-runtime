#!/usr/bin/env python3
"""走 NxConduit 下载文件，先 fs.stat 再按大小分块，不需要 FTP。

用法：python3 tools/nxc_get_file.py <设备路径> <本地路径>
"""
import os
import subprocess  # 保留工具进程入口，便于离线模拟协议。
import sys
import tempfile
from pathlib import Path
from nxc_file_reader import blocks, file_size


def main():
    if len(sys.argv) != 3:
        print(__doc__)
        return 2
    remote, local = sys.argv[1], Path(sys.argv[2])
    temporary = None
    try:
        size = file_size(remote)
        local.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=local.parent, delete=False) as handle:
            temporary = Path(handle.name)
            written = 0
            for block in blocks(remote, size):
                handle.write(block)
                written += len(block)
        if written != size:
            raise ValueError(f'大小不符：{written} / {size}')
        os.replace(temporary, local)
        temporary = None
        print(f'{remote} -> {local}：{written} 字节')
        return 0
    except (ValueError, OSError) as exc:
        print(f'✗ 下载失败：{exc}')
        return 1
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


if __name__ == '__main__': sys.exit(main())
