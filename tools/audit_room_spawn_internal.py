#!/usr/bin/env python3
"""固定AB+ NRO的71窗口入边、首个call前x16活性与跳表审计；只读离线文件。"""
import argparse
import hashlib
import json
import pathlib
import re
import struct

def direct_target(off, word):
    if word & 0x7C000000 == 0x14000000:
        value, bits = word & 0x3FFFFFF, 26
    elif word & 0xFF000010 == 0x54000000 or word & 0x7E000000 == 0x34000000:
        value, bits = (word >> 5) & 0x7FFFF, 19
    elif word & 0x7E000000 == 0x36000000:
        value, bits = (word >> 5) & 0x3FFF, 14
    else:
        return None
    if value & (1 << (bits - 1)): value -= 1 << bits
    return off + value * 4

def audit(nro, disassembly):
    image = nro.read_bytes()
    instructions = {}
    for line in disassembly.read_text().splitlines():
        match = re.match(r"^([0-9a-fA-F]+)\s+([0-9a-fA-F]{8})\s+(\S+)\s*(.*?)\s*(?://|;|$)", line)
        if match:
            off, word, mnemonic, operands = match.groups()
            off = int(off, 16)
            if 0x452948 <= off < 0x453874:
                assert image[off:off+4] == bytes.fromhex(word)[::-1], f"反汇编身份不符{off:x}"
                instructions[off] = (int(word, 16), mnemonic, operands)
    assert len(instructions) == (0x453874 - 0x452948)//4, "必须覆盖完整FixSpawnEntry（含早ret后代码）"
    ranges = [(0x452984, 0x452988)]
    inbound = []
    for off in range(0, 0x68D000, 4):
        word = struct.unpack_from('<I', image, off)[0]
        target = direct_target(off, word)
        if target is not None and any(start <= target < end for start, end in ranges):
            inbound.append([off, target])
    assert inbound == [], inbound
    assert struct.unpack_from('<I',image,0x452984)[0] == 0x94087527
    # Type6的5项跳表是唯一“首call前”间接跳转；由真实bounds cmp + unsigned B.HI限定。
    switch = [0x452BFC + 4*struct.unpack_from('<H', image, 0x8C069C+2*i)[0] for i in range(5)]
    assert switch == [0x452BFC, 0x453110, 0x453124, 0x453134, 0x453150]
    paths = {}
    for start in [0x452A1C, 0x453798]:
        seen, work, terminals = set(), [start], []
        while work:
            off = work.pop()
            if off in seen: continue
            seen.add(off)
            word, mnemonic, operands = instructions[off]
            # 不把call前IP0当作参数；真实PLT随后ADRP x16明确重定义。
            if mnemonic == 'bl':
                destination = direct_target(off, word)
                plt = struct.unpack_from('<I', image, destination)[0]
                assert plt & 0x9F00001F == 0x90000010, f"PLT没有先ADRP x16: {destination:x}"
                terminals.append([off, destination]); continue
            assert not re.search(r'\b[wx](?:16|30)\b', operands), f"首call前读取/使用x16或原LR: {off:x} {operands}"
            if mnemonic == 'br':
                assert off == 0x452BF8 and operands == 'x10'
                work.extend(switch); continue
            assert mnemonic != 'ret', f"未经定义x16就返回: {off:x}"
            target = direct_target(off, word)
            if mnemonic == 'b': work.append(target)
            elif target is not None:
                work.extend([target, off+4])
            else: work.append(off+4)
        paths[f'{start:08x}'] = {'visited': sorted(seen), 'first_calls_redefine_x16_in_plt': sorted(terminals)}
    return {'nro_sha256': hashlib.sha256(image).hexdigest(), 'fix_range': [0x452948,0x453874],
            'patch_ranges': ranges, 'all_text_direct_inbound': inbound, 'type6_table': switch,
            'x16_liveness': paths,
            'lr_difference_dead_before_first_native_call': True,
            'source_bl': 0x94087527, 'veneer_range': [0x68CFD0,0x68CFE0],
            'preserved_middle_entries': [[0x4530B4,0x452AB4],[0x4530CC,0x452AB4],
                [0x453120,0x452AB4],[0x45312C,0x452AB0],[0x453160,0x452AB4]]}

if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--nro',type=pathlib.Path,required=True)
    parser.add_argument('--disassembly',type=pathlib.Path,required=True)
    parser.add_argument('--output',type=pathlib.Path,required=True)
    args=parser.parse_args()
    result=audit(args.nro,args.disassembly)
    args.output.write_text(json.dumps(result,indent=2)+'\n')
    print('完整FixSpawnEntry、全text直接入边、Type6真实跳表及续接x16首定义核验通过')
