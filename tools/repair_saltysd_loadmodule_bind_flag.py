#!/usr/bin/env python3
"""保留卡上SaltySD装载代理的调用者参数；仅处理已冻结校验的原件。"""
import argparse
import hashlib
import json
import struct
from pathlib import Path

ORIGINAL_SHA256 = 'aae6dfa9351e6f3af5a7086820ea07bed8690127fd8786220cca3f19931c753c'
CHANGES = {0x8e64: (0xf0000104, 0xf0000105),
           0x8e6c: (0xf940ac85, 0xf940aca5),
           0x8e70: (0x52800004, 0xd503201f)}

def file_offset(blob, address):
    phoff = struct.unpack_from('<Q', blob, 0x20)[0]
    stride, count = struct.unpack_from('<HH', blob, 0x36)
    for i in range(count):
        start = phoff+i*stride
        kind = struct.unpack_from('<I', blob, start)[0]
        offset, va, _, size = struct.unpack_from('<4Q', blob, start+8)
        if kind == 1 and va <= address and address+4 <= va+size:
            return offset+address-va
    raise ValueError('目标指令不在ELF文件映射中')

def repair(blob):
    if hashlib.sha256(blob).hexdigest() != ORIGINAL_SHA256:
        raise ValueError('SaltySD原件SHA256不符，拒绝修改')
    result = bytearray(blob)
    for address, (old, new) in CHANGES.items():
        offset = file_offset(blob, address)
        if struct.unpack_from('<I', blob, offset)[0] != old:
            raise ValueError(f'入口守卫不符：{address:#x}')
        struct.pack_into('<I', result, offset, new)
    # x5只作函数指针临时寄存器；w4保持游戏调用者给定值。
    return bytes(result)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    if args.source.resolve() == args.output.resolve():
        parser.error('原件与输出不能是同一文件')
    blob = args.source.read_bytes()
    result = repair(blob)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(result)
    print(json.dumps({'bytes':len(result),'sha256':hashlib.sha256(result).hexdigest(),
                      'instructions':[hex(a) for a in CHANGES]}, ensure_ascii=False))

if __name__ == '__main__':
    main()
