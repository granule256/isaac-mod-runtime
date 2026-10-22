#!/usr/bin/env python3
"""447资源修复的NxConduit取证：按当前ELF三锚点自证，读字体、图片、保存缓存及Lua错误。"""
import argparse, base64, hashlib, json, os, struct, sys, time
from pathlib import Path
import elf_syms
import read_device_state_via_gdb as reader
sys.path.insert(0,'/Users/kelinls/code/github/KELI-NX/pc')
import nxc
p=argparse.ArgumentParser()
p.add_argument('--elf',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
p.add_argument('--command');p.add_argument('--ip',default=os.environ.get('NXC_DEVICE_IP','192.168.124.11'))
a=p.parse_args();blob=a.elf.read_bytes();symbols=elf_syms.load_symbols(blob);reader.sync_syms_from_elf(a.elf)
def call(commands):
 result=nxc.run(a.ip,47800,commands,20)
 for item in result:
  if not item['header'].startswith('OK '): raise RuntimeError(item)
 return result
def data(command):
 r=call([command])[0];return base64.b64decode(next(line[1:] for line in r['lines'] if line.startswith('#')))
def read(addr,size):
 result=b''.join(data(f'mem.read addr={addr+offset:#x} size={min(2000,size-offset)}') for offset in range(0,size,2000))
 if len(result)!=size: raise RuntimeError('内存读长度不符')
 return result
def u64(addr):return struct.unpack('<Q',read(addr,8))[0]
def u32(addr):return struct.unpack('<I',read(addr,4))[0]
current=nxc.to_structured(call(['title.current'])[0]['lines'])[0]
info=nxc.to_structured(call(['mem.info'])[0]['lines'])
modules=[item for item in info if isinstance(item,dict) and 'module' in item]
ends=sorted({int(m['base'],16)+int(m['size'],16) for m in modules},reverse=True)
base=None
for candidate in ends:
 try:
  if all(read(candidate+reader.SYMS[key],16)==elf_syms.read_vaddr(blob,reader.SYMS[key],16)
         for key in ('exl_main','identity','manifest_install')):
   base=candidate;break
 except RuntimeError:continue
if base is None:raise RuntimeError('运行时三锚点未匹配，禁止读猜测地址')
def sym(key):
 if key in reader.SYMS:return base+reader.SYMS[key]
 if key in symbols:return base+symbols[key][0]
 candidates=[k for k in symbols if key+'E' in k]
 if len(candidates)!=1:raise RuntimeError((key,candidates))
 return base+symbols[candidates[0]][0]
if a.command:
 core=base+symbols['_ZZN5isaac7runtime7console7StorageEvE4core'][0]
 if read(core+2740,1)!=b'\0':raise RuntimeError('控制台仍有待执行命令')
 command=a.command.encode();assert len(command)<192
 for address,value in ((core+2544,command+b'\0'),(core+2736,struct.pack('<I',len(command))),(core+2740,b'\1')):
  call([f'mem.write addr={address:#x} data={base64.b64encode(value).decode()} confirm=I-KNOW-THIS-WRITES-MEMORY'])
 print('已提交原生控制台命令',a.command)
result={'time':time.time(),'title':current,'runtime_base':base,'anchors_verified':True,'elf_sha256':hashlib.sha256(blob).hexdigest()}
result['fonts']={k:u32(sym(k)) for k in ('g_FontStorageLive','g_FontStorageAllocations','g_FontStorageLivePeak','g_FontStorageDestructions','g_FontGcNudges','g_FontGcSteps','g_FontGcMicros','g_FontGcMicrosMax')}
menu=struct.unpack('<82I',read(sym('mod_menu_state'),328));result['menu']={'frames':menu[34],'in_game':menu[51],'heap_free':menu[58],'heap_used':menu[59],'free_chunks':menu[77],'heap_top_free':menu[79],'pcx_cache_bytes':menu[80]}
diag=read(sym('image_pcx_diag'),reader.IMAGE_PCX_DIAG_BYTES)
a.out.parent.mkdir(parents=True,exist_ok=True);a.out.with_suffix('.image.bin').write_bytes(diag)
# 已发布诊断结构前12个u32，后两条128B路径；完整原件保留。
names=('hookCalls','originalOk','syntheticPaths','fallbackAttempts','ringMiss','readOk','cacheHits','cacheConversions','convertFailures','fedOk','bindingMask','pngOverrideWins')
result['images']=dict(zip(names,struct.unpack_from('<12I',diag)))
fields=json.loads((Path(__file__).resolve().parent/'dance_image_diag_fields.json').read_text())
for key,offset in fields.items():
 if key in ('feedFailures','pngProbeFail','pngNativeRetry','readMicrosMax','convertMicrosMax','fallbackMicrosMax','pngProbeMicrosMax'):
  result['images'][key]=struct.unpack_from('<I',diag,offset)[0]
result['images']['last_path']=diag[176:304].split(b'\0')[0].decode(errors='replace')
result['images']['last_conversion_failure']=u32(sym('g_ImagePcxLastConversionFailure'))
result['images']['last_failed_png_bytes']=u32(sym('g_ImagePcxLastFailedPngBytes'))
errors=read(sym('g_LuaErrorHistory'),1024)
a.out.with_suffix('.errors.bin').write_bytes(errors)
result['error_count']=u32(sym('g_LuaErrorHistoryCount'))
result['errors']=[{'text':errors[i:i+120].split(b'\0')[0].decode(errors='replace'),'owner':struct.unpack_from('<I',errors,i+120)[0],'callback':struct.unpack_from('<I',errors,i+124)[0]} for i in range(0,1024,128)]
result['caches']=[];node=u64(sym('g_ModDataCache'));seen=set()
while node:
 if node in seen or len(seen)>1024:raise RuntimeError('保存缓存链表异常')
 seen.add(node);header=read(node,56)
 next_,ns=struct.unpack_from('<QQ',header);slot=struct.unpack_from('<I',header,16)[0]
 encoded,length,generation=struct.unpack_from('<QQQ',header,24);bank=struct.unpack_from('<i',header,48)[0]
 entry={'namespace':hex(ns),'slot':slot,'length':length,'generation':generation,'bank':bank,'loaded':bool(header[52]),'exists':bool(header[53])}
 if encoded and 48<=length<=1024*1024 and header[53]:
  value=read(encoded+48,length-48)
  entry['sha256']=hashlib.sha256(value).hexdigest()
  filename=a.out.with_name(a.out.stem+f'.mod-{ns:016x}-s{slot}.bin');filename.write_bytes(value)
  try:entry['json_keys']=len(json.loads(value))
  except (ValueError,TypeError):pass
 result['caches'].append(entry);node=next_
manager=u64(sym('g_RenderFrameManager'))
if manager:
 result['manager']=manager;result['slot']=u32(manager+0x10)
 result['music']={'current':u32(manager+0x36068+0x3c8),'enabled':read(manager+0x36068+0x3f0,1)[0]}
 engine=u64(sym('g_EngineModuleBase'));result['engine_base']=engine
 game=u64(u64(engine+0xAAC698)) if engine else 0
 if game:result['game']={'address':game,'room':u32(game+0x21558),'enter_door':struct.unpack('<i',read(game+0x21570,4))[0]}
a.out.write_text(json.dumps(result,ensure_ascii=False,indent=2))
print(json.dumps({k:v for k,v in result.items() if k not in ('caches','errors')},ensure_ascii=False))
print('错误',result['errors'],'保存缓存',result['caches'])
