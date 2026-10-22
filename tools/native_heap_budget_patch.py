#!/usr/bin/env python3
"""按注入NSO实际占用恢复原版CPU堆余量；生成仅修改KAGE启动预算的IPS。"""
import argparse,hashlib,json,struct
from pathlib import Path
from nro_ips import encode_ips,read_module_id
MODULE_ID='91C73FDD575061318D68886316AFEAC72388B2AB000000000000000000000000'
MAIN_HEAP_OFFSET=0x8BF884
INIT_OFFSET=0x4FEDC8
INIT_GUARD=bytes.fromhex('fd7bbea9f30b00f9fd030091682d00f0')
GRAPHICS_INIT_OFFSET=0x4ff1f0
GRAPHICS_INIT_GUARD=bytes.fromhex('080140b90900b852280108cbf30300aa004002914100805202fd41d3')
BASE_CPU_RESERVE=240*1024*1024
NATIVE_TOTAL_RESERVE=3*1024*1024*1024
# initialize_graphics_heaps将(3GiB-CPU预留)除以二。图形池必须按4KiB页对齐，
# 因此CPU预留需按8KiB上取整，不能只按NSO的4KiB占用原样相加。
GRAPHICS_POOL_ALIGNMENT=4096
CPU_RESERVE_ALIGNMENT=2*GRAPHICS_POOL_ALIGNMENT

def runtime_footprint(nso:bytes)->int:
 if len(nso)<256 or nso[:4]!=b'NSO0':raise ValueError('缺少完整NSO0头')
 # 三段的内存偏移包含段间对齐；BSS是装载后实际占用，不是压缩文件字节数。
 ends=[]
 for i in range(3):
  _,memory,size=struct.unpack_from('<III',nso,0x10+i*16)
  ends.append(memory+size)
 bss=struct.unpack_from('<I',nso,0x3c)[0]
 total=(max(ends[0],ends[1],ends[2]+bss)+4095)&~4095
 if total<=0 or total>=NATIVE_TOTAL_RESERVE-BASE_CPU_RESERVE:raise ValueError('模块占用超出可用进程预算')
 return total

def generate(nro:bytes,nso:bytes):
 if read_module_id(nro).hex().upper()!=MODULE_ID:raise ValueError('不匹配当前游戏NRO版本')
 if nro[INIT_OFFSET:INIT_OFFSET+len(INIT_GUARD)]!=INIT_GUARD:raise ValueError('原生内存初始化指纹不匹配')
 if nro[GRAPHICS_INIT_OFFSET:GRAPHICS_INIT_OFFSET+len(GRAPHICS_INIT_GUARD)]!=GRAPHICS_INIT_GUARD:raise ValueError('原生图形堆减预留后除二的指纹不匹配')
 if len(nro)<MAIN_HEAP_OFFSET+4 or struct.unpack_from('<I',nro,MAIN_HEAP_OFFSET)[0]!=BASE_CPU_RESERVE:raise ValueError('原始CPU预留不是240MiB')
 footprint=runtime_footprint(nso);minimum=BASE_CPU_RESERVE+footprint
 reserve=(minimum+CPU_RESERVE_ALIGNMENT-1)&~(CPU_RESERVE_ALIGNMENT-1)
 if reserve>=NATIVE_TOTAL_RESERVE:raise ValueError('对齐后的CPU预留超出可用进程预算')
 patch=encode_ips([(MAIN_HEAP_OFFSET,struct.pack('<I',reserve))])
 info={'runtime_sha256':hashlib.sha256(nso).hexdigest(),'runtime_footprint':footprint,
       'original_cpu_reserve':BASE_CPU_RESERVE,'cpu_reserve':reserve,
       'original_device_heap':NATIVE_TOTAL_RESERVE-BASE_CPU_RESERVE,
       'device_heap':NATIVE_TOTAL_RESERVE-reserve,'module_id':MODULE_ID,'offset':MAIN_HEAP_OFFSET,
       'cpu_reserve_alignment':CPU_RESERVE_ALIGNMENT,'cpu_padding':reserve-minimum,
       'graphics_heap':(NATIVE_TOTAL_RESERVE-reserve)//2,'graphics_pool_alignment':GRAPHICS_POOL_ALIGNMENT}
 return patch,info

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--nro',type=Path,required=True);p.add_argument('--runtime',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--report',type=Path)
 a=p.parse_args();patch,info=generate(a.nro.read_bytes(),a.runtime.read_bytes())
 a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_bytes(patch)
 if a.report:a.report.parent.mkdir(parents=True,exist_ok=True);a.report.write_text(json.dumps(info,indent=2))
 print(json.dumps(info,ensure_ascii=False))
if __name__=='__main__':main()
