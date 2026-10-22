#!/usr/bin/env python3
"""为Specialist结束舞蹈的恢复路径接入MMC公开接口；保留原文件行尾。"""
from pathlib import Path
import argparse


def patch(source: bytes) -> bytes:
    old = b'                    Game():GetRoom():PlayMusic();'
    guard = b'if EpicSettings["EnableMusic"] and wasPog then'
    if source.count(old) != 1 or source.count(guard) != 1:
        raise ValueError('作者恢复代码形状不匹配，拒绝修改')
    position = source.index(old)
    if not 0 < position - source.index(guard) < 256:
        raise ValueError('恢复调用不在预期的舞蹈结束分支')
    newline = b'\r\n' if b'\r\n' in source else b'\n'
    replacement = newline.join([
        b'                    -- MMC replaces native room tracks; restore through its public manager.',
        b'                    if MMC and MMC.Initialised then',
        b'                        MMC.Manager():Crossfade(MMC.GetMusicTrack());',
        b'                    else',
        old.replace(b'                    ', b'                        ', 1),
        b'                    end',
    ])
    return source.replace(old, replacement, 1)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    if args.source.resolve() == args.output.resolve():
        parser.error('必须另存候选文件，保留原件')
    args.output.write_bytes(patch(args.source.read_bytes()))
