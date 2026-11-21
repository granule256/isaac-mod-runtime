"""加载前安装诅咒/拾取选择中继；运行中仅发布64bit slot，不热改LDR/CMP。"""
from __future__ import annotations
import hashlib
import struct
try:
    from . import build_patches
    from . import extra_source_cold
    from . import custom_item_pool_cold
    from . import mgo_death_cold
except ImportError:
    import build_patches
    import extra_source_cold
    import custom_item_pool_cold
    import mgo_death_cold

BUILD_ID=bytes.fromhex('91C73FDD575061318D68886316AFEAC72388B2AB')+bytes(12)
SITES=((0x2857A8,0x68CF40,0x394002A8),(0x3E0C88,0x68CDC0,0xF9400309),(0x269D50,0x68CDE0,0x7100A29F),(0x269D08,0x68CD00,0xB85FC3B4))
PROJECTILE_TAIL_SITE=(0x32744C,0x68CCD0,0x910603FF)
PROJECTILE_INIT_TAIL_SITE=(0x31F2D8,0x68CE20,0xA9424FF4)
# 生产版主动道具五条消费路径；CE60..CF00与历史诊断102/104/109/110/112/127/128互斥。
USE_ITEM_BOUNDARY_SITES=((0x30A19C,0x68CE60,0xB9595B69),(0x30C728,0x68CE80,0xB9595B69),
 (0x317318,0x68CEA0,0xB9595B69),(0x31A80C,0x68CEC0,0xB94056E8),(0x31A92C,0x68CEE0,0xB94056E8))
CONSOLE_BRANCH_SITES=((0x41878,0x68CD40,0x54002761),(0x41898,0x68CD80,0x35002660))
STAT_HUD_BRANCH_SITES=((0x3AF298,0x68CF60,0x60C704,0x54FFFF40),
                      (0x3AF558,0x68CF78,0x60C724,0x54FFFF43))

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

def projectile_tail_gate(source:int,gate:int,original:int)->bytes:
    if (source,gate,original) not in (PROJECTILE_TAIL_SITE,PROJECTILE_INIT_TAIL_SITE):raise ValueError('弹幕正常完成边界身份不符')
    # void退出边界：x28仍为this，原x30在帧上；C++调用无需全寄存器快照。
    # null槽直达ADD SP；有槽按AAPCS64调用，再重放同一ADD SP/原epilogue。
    return struct.pack('<8IQ',0x10000110,0xC8DFFE10,0xB4000070,(0xAA1303E0 if (source,gate,original)==PROJECTILE_INIT_TAIL_SITE else 0xAA1C03E0),
                       0xD63F0200,original,branch(gate+24,source+4),0xD503201F,0)

def player_candle_return_records(nro:bytes)->list[tuple[int,bytes]]:
    source,island,original=0x2F215C,0x68CFA0,0xA94C4FF4
    if len(nro)<island+12 or nro[0x40:0x60]!=BUILD_ID:
        raise ValueError('Player candle NRO identity mismatch')
    if nro[source:source+4]!=struct.pack('<I',original):
        raise ValueError('Player candle epilogue mismatch')
    if nro[island:island+12]!=bytes(12):
        raise ValueError('Player candle return island is not empty')
    # shoot_blue_candle ends with Effect::Update (void). Save the created
    # effect as the result before the original epilogue restores x20/x19.
    return [(source,struct.pack('<I',branch(source,island))),
            (island,struct.pack('<3I',0xAA1403E0,original,branch(island+8,source+4)))]

def stat_hud_conditional_records(nro:bytes)->list[tuple[int,bytes]]:
    if len(nro)<0x68CF90 or nro[0x40:0x60]!=BUILD_ID:
        raise ValueError('StatHUD NRO identity mismatch')
    records=[]
    for source,gate,fallback,original in STAT_HUD_BRANCH_SITES:
        if nro[source:source+4]!=struct.pack('<I',original):
            raise ValueError('StatHUD original condition mismatch')
        if nro[gate:gate+24]!=bytes(24) or nro[fallback:fallback+12]!=bytes(12):
            raise ValueError('StatHUD cold gate is not empty')
        # LDR/CBZ/BR preserve NZCV. A null pointer replays the original
        # condition in a separate island, including when the extension is off.
        delta=fallback-(gate+4)
        if delta&3 or not -(1<<20)<=delta<(1<<20):
            raise ValueError('StatHUD null continuation outside CBZ range')
        cbz=0xB4000010|(((delta//4)&0x7FFFF)<<5)
        image=struct.pack('<4IQ',0x58000090,cbz,0xD61F0200,0xD503201F,0)
        displacement=(original>>5)&0x7FFFF
        if displacement&(1<<18):displacement-=1<<19
        target=source+displacement*4
        inverse=0x54000040|((original&15)^1)
        replay=struct.pack('<3I',inverse,branch(fallback+4,target),
                           branch(fallback+8,source+4))
        records.extend(((source,struct.pack('<I',branch(source,gate))),
                        (gate,image),(fallback,replay)))
    return records

def challenge_achievement_records(nro: bytes) -> list[tuple[int, bytes]]:
    start, end = 0x439500, 0x439654
    if (nro[0x40:0x60] != BUILD_ID or hashlib.sha256(nro[start:end]).hexdigest() !=
            'a9ce86f22feadfc46476d5b8add60e2680fc23a5ccad81731bf838f716100662'):
        raise ValueError('Unexpected native challenge achievement scan')
    # A prerequisite outside PGD's achievement range is not satisfied. Exit to
    # the next challenge, just as for a locked prerequisite, without indexing PGD.
    # X0 already points to the current ChallengeParam, so reuse its vector end
    # instead of calling the pure GetChallengeParams getter again at 0x4395C0.
    return [(0x439598, bytes.fromhex(
        '092047a9'  # ldp x9, x8, [x0, #112] (prerequisite begin/end)
        '2a7974b8'  # ldr w10, [x9, x20, lsl #2]
        '4a050051'  # sub w10, w10, #1
        '5ff10971'  # cmp w10, #636 (valid achievement IDs are 1..637)
        '28fdff54'  # b.hi 0x43954C
        '6a020a8b'  # add x10, x19, x10
        '4aa54039'  # ldrb w10, [x10, #41] (PGD + id + 40)
        'cafcff34'  # cbz w10, 0x43954C
        'f4031b2a'  # mov w20, w27
        '03000014'  # b 0x4395C8 (original vector count and loop advance)
    ))]

def shader_control_memory_records(nro: bytes) -> list[tuple[int, bytes]]:
    # CommandBuffer::Initialize allocates the storage. Begin registers its
    # capacity with NVN. Keep both sizes equal across every recording.
    sites = ((0x4F4038, 0x52808001, 0x52880001),
             (0x4F4134, 0x52808002, 0x52880002))
    for offset, original, _ in sites:
        if nro[offset:offset+4] != struct.pack('<I', original):
            raise ValueError('Unexpected native command control memory size')
    return [(offset, struct.pack('<I', replacement))
            for offset, _, replacement in sites]


def build_static_callback_patch(nro:bytes)->bytes:
    if len(nro)<0x68CCA0 or nro[0x40:0x60]!=BUILD_ID:raise ValueError('固定NRO身份不符')
    records=[]
    for source,gate,original in (*SITES,*USE_ITEM_BOUNDARY_SITES):
        if nro[source:source+4]!=struct.pack('<I',original):raise ValueError(f'{source:x}原指令不符')
        if nro[gate:gate+32]!=bytes(32):raise ValueError(f'{gate:x}中继不是完整空区')
        records.extend(((source,struct.pack('<I',branch(source,gate))),
                        (gate,gate_image(source,gate,original))))
    for source,gate,original in CONSOLE_BRANCH_SITES:
        if nro[source:source+4]!=struct.pack('<I',original):raise ValueError(f'{source:x}原命令条件不符')
        if nro[gate:gate+40]!=bytes(40):raise ValueError(f'{gate:x}命令中继不是完整空区')
        records.extend(((source,struct.pack('<I',branch(source,gate))),
                        (gate,console_branch_gate(source,gate,original))))
    for source,gate,original in (PROJECTILE_TAIL_SITE,PROJECTILE_INIT_TAIL_SITE):
        if nro[source:source+4]!=struct.pack('<I',original):raise ValueError('弹幕完成边界原指令不符')
        if nro[gate:gate+40]!=bytes(40):raise ValueError('弹幕完成中继不是完整空区')
        records.extend(((source,struct.pack('<I',branch(source,gate))),
                        (gate,projectile_tail_gate(source,gate,original))))
    records.extend(stat_hud_conditional_records(nro))
    records.extend(player_candle_return_records(nro))
    records.extend(extra_source_cold.cold_records(nro))
    records.extend(custom_item_pool_cold.cold_records(nro))
    records.extend(mgo_death_cold.records(nro))
    records.extend(challenge_achievement_records(nro))
    records.extend(shader_control_memory_records(nro))
    return build_patches.encode_ips(records)
