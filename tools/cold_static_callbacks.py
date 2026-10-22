"""加载前安装诅咒/拾取选择中继；运行中仅发布64bit slot，不热改LDR/CMP。"""
from __future__ import annotations
import struct
try:
    from . import build_patches
except ImportError:
    import build_patches

BUILD_ID=bytes.fromhex('91C73FDD575061318D68886316AFEAC72388B2AB')+bytes(12)
SITES=((0x3E0C88,0x68CDC0,0xF9400309),(0x269D50,0x68CDE0,0x7100A29F),(0x269D08,0x68CD00,0xB85FC3B4))
CONSOLE_BRANCH_SITES=((0x41878,0x68CD40,0x54002761),(0x41898,0x68CD80,0x35002660))

def branch(source:int,target:int)->int:
    delta=target-source
    if delta&3 or not -(1<<27)<=delta<(1<<27):raise ValueError('源与中继不在B范围')
    return 0x14000000|((delta//4)&0x3ffffff)

def gate_image(source:int,gate:int,original:int)->bytes:
    if gate&7:raise ValueError('64bit slot未对齐')
    # ADR x16,+24；LDAR x16,[x16]；CBZ x16,+8；BR x16；原指令；B续接；slot。
    return struct.pack('<6IQ',0x100000D0,0xC8DFFE10,0xB4000050,0xD61F0200,
                       original,branch(gate+20,source+4),0)

def console_branch_gate(source:int,gate:int,original:int)->bytes:
    if (source,gate,original) not in CONSOLE_BRANCH_SITES or gate&7:raise ValueError('未知命令分支身份不符')
    # null槽重放条件：原B.NE/CBNZ反条件越过taken B；两条B不依赖短条件跳范围。
    inverse=0x54000040 if source==0x41878 else 0x34000040
    return struct.pack('<8IQ',0x10000110,0xC8DFFE10,0xB4000050,0xD61F0200,
                       inverse,branch(gate+20,0x41D64),branch(gate+24,source+4),0xD503201F,0)

def build_static_callback_patch(nro:bytes)->bytes:
    if len(nro)<0x68CCA0 or nro[0x40:0x60]!=BUILD_ID:raise ValueError('固定NRO身份不符')
    records=[]
    for source,gate,original in SITES:
        if nro[source:source+4]!=struct.pack('<I',original):raise ValueError(f'{source:x}原指令不符')
        if nro[gate:gate+32]!=bytes(32):raise ValueError(f'{gate:x}中继不是完整空区')
        records.extend(((source,struct.pack('<I',branch(source,gate))),
                        (gate,gate_image(source,gate,original))))
    for source,gate,original in CONSOLE_BRANCH_SITES:
        if nro[source:source+4]!=struct.pack('<I',original):raise ValueError(f'{source:x}原命令条件不符')
        if nro[gate:gate+40]!=bytes(40):raise ValueError(f'{gate:x}命令中继不是完整空区')
        records.extend(((source,struct.pack('<I',branch(source,gate))),
                        (gate,console_branch_gate(source,gate,original))))
    return build_patches.encode_ips(records)
