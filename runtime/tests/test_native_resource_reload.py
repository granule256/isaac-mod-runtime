"""共享动画必须先放开真实所有者，再零引用回收，再按新资源根重建。"""
from pathlib import Path
import subprocess,tempfile,unittest,re,sys,importlib.util

ROOT=Path(__file__).resolve().parents[2]
HARNESS=r'''
#include "native_resource_reload.hpp"
#include <cassert>
#include <string>
using namespace isaac::runtime;
struct Resources {
 unsigned references=1; bool cached=true,old=true,live=true;std::string trace;
 void Destroy(std::uintptr_t address){assert(address==0x1000&&live);--references;live=false;trace+='D';}
 void Construct(std::uintptr_t address){assert(address==0x1000&&!live);trace+='C';}
 void Reclaim(){if(references==0)cached=false;trace+='F';}
 bool Load(std::uintptr_t address){assert(address==0x1000&&!live);if(!cached){cached=true;old=false;}++references;live=true;trace+='L';return true;}
};
int main(){
 // 旧流程只回收，原生对象仍持有缓存：新路径名单并不能替换已缓存内容。
 Resources old;old.Reclaim();assert(old.cached&&old.old&&old.live);
 NativeResourceReloadState state{};Resources resources;
 assert(PrepareNativeResourceOwner(state,0x1000));
 assert(ReleaseNativeResourceOwner(state,resources));
 assert(resources.references==0&&!resources.live);
 // 重载失败后的重试不能二次析构，也不能丢弃待恢复所有者。
 assert(PrepareNativeResourceOwner(state,0x1000));
 assert(ReleaseNativeResourceOwner(state,resources));assert(resources.trace=="DC");
 assert(!PrepareNativeResourceOwner(state,0x2000));
 resources.Reclaim();
 assert(!RestoreNativeResourceOwner(state,0x2000,resources));assert(resources.trace=="DCF");
 assert(RestoreNativeResourceOwner(state,0x1000,resources));
 assert(!resources.old&&resources.references==1&&resources.live&&resources.trace=="DCFL");
 assert(RestoreNativeResourceOwner(state,0x1000,resources));assert(resources.trace=="DCFL");
 // 仍有其它活引用时，回收不得删除缓存，协调器不偷减外部引用。
 NativeResourceReloadState sharedState{};Resources shared;shared.references=2;
 assert(PrepareNativeResourceOwner(sharedState,0x1000));assert(ReleaseNativeResourceOwner(sharedState,shared));
 shared.Reclaim();assert(shared.references==1&&shared.cached);
 // 正常整轮重复操作不累积引用或重复释放。
 for(unsigned i=0;i<20;++i){
  assert(PrepareNativeResourceOwner(state,0x1000));assert(ReleaseNativeResourceOwner(state,resources));
  resources.Reclaim();assert(RestoreNativeResourceOwner(state,0x1000,resources));assert(resources.references==1);
 }
 NativeResourceReloadState none{};Resources unused;
 assert(PrepareNativeResourceOwner(none,0));assert(ReleaseNativeResourceOwner(none,unused));
 assert(RestoreNativeResourceOwner(none,0,unused));assert(unused.trace.empty());
 NativeResourceReloadState invalid{};assert(!ReleaseNativeResourceOwner(invalid,unused));
 assert(!RestoreNativeResourceOwner(invalid,0x1000,unused));assert(unused.trace.empty());
}
'''
class NativeResourceReloadTests(unittest.TestCase):
 def test_shared_cache_owner_lifetime_and_failure_retry(self):
  with tempfile.TemporaryDirectory(prefix='isaac-native-resource-')as tmp:
   p=Path(tmp);(p/'main.cpp').write_text(HARNESS)
   r=subprocess.run(['c++','-std=c++17','-Wall','-Wextra','-Werror','-I',str(ROOT/'runtime/source'),str(p/'main.cpp'),'-o',str(p/'check')],capture_output=True,text=True)
   self.assertEqual(r.returncode,0,r.stdout+r.stderr)
   r=subprocess.run([str(p/'check')],capture_output=True,text=True)
   self.assertEqual(r.returncode,0,r.stdout+r.stderr)

 def test_native_minimap_bindings_and_game_member_boundaries(self):
  source=(ROOT/'runtime/source/native_game_resource_reload.cpp').read_text()
  sys.path.insert(0,str(ROOT/'tools'))
  import nro_symbols,nro_disasm
  nro=Path(nro_disasm.DEFAULT_NRO).read_bytes();_,symbols=nro_symbols.parse_dynamic_symbols(nro)
  rows=re.findall(r'\{\s*(0x[0-9a-f]+),\s*\{([^}]+)\}\}',source)
  self.assertEqual(len(rows),5,'三个生命周期入口和两处Game成员位置必须核对')
  offsets=[]
  for offset,guard in rows:
   begin=int(offset,16);expected=bytes(int(x.strip(),16)for x in guard.split(',')if x.strip())
   self.assertEqual(expected,nro[begin:begin+len(expected)]);offsets.append(begin)
  for name in ['_ZN15IsaacRepentance7MinimapC1Ev','_ZN15IsaacRepentance7MinimapD1Ev','_ZN15IsaacRepentance7Minimap4InitEv']:
   self.assertIn(symbols[name].file_offset,offsets)
  self.assertIn('kGameMinimapOffset=0x24ee70',source)
  self.assertIn('kGameMinimapSize=0xb40',source)
  # 构造及初始化两条实际调用的this都取同一Game成员；下一成员边界为+24f9b0。
  import struct
  def immediate(at):return (struct.unpack_from('<I',nro,at)[0]>>5)&0xffff
  self.assertEqual(immediate(0x34b418)|(immediate(0x34b41c)<<16),0x24ee70)
  self.assertEqual(immediate(0x34e084)|(immediate(0x34e088)<<16),0x24ee70)
  self.assertEqual((immediate(0x34b428)|(immediate(0x34b42c)<<16))-0x24ee70,0xb40)

 def test_production_releases_and_reclaims_before_new_mod_load(self):
  src=(ROOT/'runtime/source/mod_menu_native.cpp').read_text()
  release=src[src.index('bool ReleaseModReloadNative()'):src.index('bool LoadCycleShaders(')]
  self.assertLess(release.index('ReleaseNativeGameResources()'),release.index('freeUnreferencedEntries('))
  self.assertLess(release.index('freeUnreferencedEntries('),release.index('ReclaimModReloadGraphics(graphics)'))
  finish=src[src.index('bool FinishModReloadNative()'):src.index('bool FinishModReloadNative()')+2400]
  self.assertIn('RestoreNativeGameResources()',finish)
  self.assertIn('CPPFILES += native_game_resource_reload.cpp',(ROOT/'runtime/misc/mk/common.mk').read_text())
