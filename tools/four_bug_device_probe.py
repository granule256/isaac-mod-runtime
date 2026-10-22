#!/usr/bin/env python3
"""四项bug现场读数，先核当前ELF代码身份；控制台命令在游戏线程执行。"""
import argparse,base64,json,struct,sys,hashlib,time
from pathlib import Path
import elf_syms,read_device_state_via_gdb as reader
sys.path.insert(0,"/Users/kelinls/code/github/KELI-NX/pc")
import nxc
p=argparse.ArgumentParser();p.add_argument("--elf",type=Path,required=True);p.add_argument("--out",type=Path,required=True);p.add_argument("--ip",default="192.168.124.11");p.add_argument("--command");a=p.parse_args()
b=a.elf.read_bytes();syms=elf_syms.load_symbols(b);reader.sync_syms_from_elf(a.elf)
def call(cmd):
 r=nxc.run(a.ip,47800,[cmd],15)[0]
 if not r["header"].startswith("OK "):raise RuntimeError(r)
 return r
def read(addr,size):
 raw=bytearray()
 for off in range(0,size,2000):
  r=call(f"mem.read addr={addr+off:#x} size={min(2000,size-off)}")
  raw.extend(base64.b64decode(next(l[1:] for l in r["lines"] if l.startswith("#"))))
 if len(raw)!=size:raise RuntimeError("内存长度不符")
 return bytes(raw)
def q(addr):return struct.unpack("<Q",read(addr,8))[0]
def u(addr):return struct.unpack("<I",read(addr,4))[0]
title=nxc.to_structured(call("title.current")["lines"])[0]
info=nxc.to_structured(call("mem.info")["lines"]);ends=sorted({int(m["base"],16)+int(m["size"],16) for m in info if isinstance(m,dict) and "module" in m},reverse=True)
base=None
for candidate in ends:
 try:
  if all(read(candidate+reader.SYMS[k],16)==elf_syms.read_vaddr(b,reader.SYMS[k],16) for k in ["exl_main","identity","manifest_install"]):base=candidate;break
 except RuntimeError:pass
if base is None:raise RuntimeError("当前运行时与指定ELF代码身份不符")
def own(name):
 key=reader.SYM_ELF_NAMES.get(name,name)
 if key in syms:return base+syms[key][0]
 matches=[v[0] for k,v in syms.items() if name+"E" in k]
 if len(matches)!=1:raise RuntimeError((name,matches))
 return base+matches[0]
def string(addr):
 d=read(addr,24)
 if d[0]&1:
  n=struct.unpack_from("<Q",d,8)[0];ptr=struct.unpack_from("<Q",d,16)[0]
  if n>512:return "<长度非法>"
  return read(ptr,n).decode(errors="replace")
 return d[1:1+(d[0]>>1)].decode(errors="replace")
core=own("_ZZN5isaac7runtime7console7StorageEvE4core")
if a.command:
 c=a.command.encode();assert 0<len(c)<128
 if read(core+2740,1)!=b"\0":raise RuntimeError("仍有待执行命令")
 for address,value in [(core+2544,c+b"\0"),(core+2736,struct.pack("<I",len(c))),(core+2740,b"\1")]:
  call(f"mem.write addr={address:#x} data={base64.b64encode(value).decode()} confirm=I-KNOW-THIS-WRITES-MEMORY")
result={"time":time.time(),"title":title,"runtime":base,"elf_sha256":hashlib.sha256(b).hexdigest(),"anchors_verified":True}
result["console"]=list(struct.unpack("<22I",read(own("g_ConsoleState"),88)))
result["console_output"]=read(core+2028,512).split(b"\0")[0].decode(errors="replace")
result["menu_frames"]=u(own("mod_menu_state")+34*4)
engine=q(own("g_EngineModuleBase"));result["engine"]=engine
if engine:
 game=q(q(engine+0xaac698));result["game_address"]=game
 if game:
  result["stage"]=u(game);result["stage_type"]=u(game+4);result["room_index"]=u(game+0x21558);result["dimension"]=u(game+0x21560)
  beg=q(game+0x25c50);end=q(game+0x25c58);result["players"]=[]
  for i in range(min((end-beg)//8,4)) if beg and end>=beg else []:
   player=q(beg+i*8)
   result["players"].append({"address":player,"type":u(player+0x1738),"hearts":u(player+0x16bc),"soul":u(player+0x16c4),"bone":u(player+0x2450),"coins":u(player+0x16e0),"position":struct.unpack("<2f",read(player+0x310,8))})
  room=q(game+0x21550);result["room_address"]=room
  if room:
   beg=q(room+0x1950+0x78);cnt=u(room+0x1950+0x84);result["pickups"]=[]
   for i in range(min(cnt,2048)) if beg else []:
    e=q(beg+i*8);typ,var,sub=struct.unpack("<3I",read(e+0x38,12))
    if typ!=5:continue
    row={"address":e,"variant":var,"subtype":sub,"position":struct.unpack("<2f",read(e+0x310,8))}
    if var==100 and sub==232:
     sprite=e+0x50;layers=q(sprite+0xa8);count=u(sprite+0xb0);row["sprite_file"]=string(sprite)
     if layers and count>1:
      layer=layers+176;row["replacement"]=string(layer+0x10);image=q(layer+0xa0);row["image"]=image;row["control"]=q(layer+0xa8)
      if image:
       path=q(image+0x50);row["actual_image_path"]=read(path,192).split(b"\0")[0].decode(errors="replace")
    result["pickups"].append(row)
errors=read(own("g_LuaErrorHistory"),1024);result["error_count"]=u(own("g_LuaErrorHistoryCount"));result["errors"]=[errors[i:i+120].split(b"\0")[0].decode(errors="replace") for i in range(0,1024,128)]
a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(result,ensure_ascii=False,indent=2));print(json.dumps(result,ensure_ascii=False),flush=True)
