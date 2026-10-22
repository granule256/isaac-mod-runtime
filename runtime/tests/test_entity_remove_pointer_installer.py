"""实际指针安装器：28B原码、11重定位目标、先发布原函数及真实拦截调用。"""
import re,struct,sys,subprocess,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
class PointerInstallerTests(unittest.TestCase):
 def test_actual_relocations_and_all_base_remove_callers(self):
  sys.path.insert(0,str(ROOT/'tools'))
  from nro_symbols import parse_dynamic_relocations
  nro=next(Path('/Users/kelinls/code/github/isaac mod').glob('The Binding of Isaac_ Afterbirth+*/Program #0/1/.nro/Repentance.nro')).read_bytes()
  _,rows=parse_dynamic_relocations(nro)
  relocs=rows['_ZN15IsaacRepentance6Entity6RemoveEv']
  header=(ROOT/'runtime/source/entity_remove_slots.hpp').read_text().split('kEntityRemovePointerOffsets={',1)[1].split('};',1)[0]
  expected=[int(x,16) for x in re.findall(r'0x[0-9A-Fa-f]+',header)]
  self.assertEqual([r.offset for r in relocs],expected)
  self.assertEqual([r.relocation_type for r in relocs],[257]*10+[1026])
  self.assertTrue(all(r.addend==0 for r in relocs))
  direct=[];plt=[]
  for offset,(word,) in enumerate(struct.iter_unpack('<I',nro[0:0x68d000])):
   if word&0x7c000000!=0x14000000:continue
   imm=word&0x3ffffff
   if imm&0x2000000:imm-=0x4000000
   pc=offset*4;target=pc+imm*4
   if target==0x5d3e0:direct.append(pc)
   if target==0x673350:plt.append(pc)
  self.assertEqual(direct,[],'Root Remove无搬入口之外的直接跳入者')
  self.assertEqual(plt,[0xad568,0x104b64,0x1063f0,0x106414,0x276990])

 def test_guarded_real_installer_and_original_publication(self):
  nro=next(Path('/Users/kelinls/code/github/isaac mod').glob('The Binding of Isaac_ Afterbirth+*/Program #0/1/.nro/Repentance.nro')).read_bytes()
  raw=nro[0x5d3e0:0x5d3fc]
  shim='''#pragma once
#include <cstdint>
#include <cstddef>
namespace exl::util {struct RwPages {
 std::uintptr_t p;RwPages(std::uintptr_t a,std::size_t):p(a){}
 std::uintptr_t GetRw()const{return p;}void Flush(){}
};}
'''
  driver=r'''
#include "entity_remove_hook.hpp"
#include "entity_remove_slots.hpp"
#include "runtime_constants.hpp"
#include <cassert>
#include <cstring>
#include <vector>
using namespace isaac::runtime;
std::uintptr_t wantOriginal{};unsigned calls{};
namespace isaac::runtime {
void RunEntityRemoveIntercept(const EntityRemoveNativeBindings*n,void* e)noexcept {
 assert(reinterpret_cast<std::uintptr_t>(n->remove)==wantOriginal&&e==reinterpret_cast<void*>(0x1000));++calls;
}}
extern "C" void IsaacModRuntime_EntityRemovePointerIntercept(void*);
int main(){
 std::vector<unsigned char> image(0xaac000);auto base=reinterpret_cast<std::uintptr_t>(image.data());
 wantOriginal=base+kEntityRemoveOffset;unsigned char raw[]={ORIGINAL};
 std::memcpy(image.data()+kEntityRemoveOffset,raw,sizeof(raw));
 auto write=[&](std::uintptr_t o,std::uintptr_t v){std::memcpy(image.data()+o,&v,8);};
 auto reset=[&](){for(auto o:kEntityRemovePointerOffsets)write(o,wantOriginal);};reset();
 HookTarget t{};t.base=base;t.codeSize=0x68d000;t.imageSize=image.size();t.buildId=kTargetBuildId;
 for(unsigned i=0;i<sizeof(raw);++i){
  image[kEntityRemoveOffset+i]^=1;assert(!InstallEntityRemovePointerHooks(t).ok());image[kEntityRemoveOffset+i]^=1;
 }
 for(auto off:kEntityRemovePointerOffsets){write(off,0x12345678);assert(!InstallEntityRemovePointerHooks(t).ok());reset();}
 write(kEntityRemovePointerOffsets.back(),base+kPltResolverOffset);
 assert(InstallEntityRemovePointerHooks(t).ok());
 for(auto o:kEntityRemovePointerOffsets){std::uintptr_t v{};std::memcpy(&v,image.data()+o,8);assert(v==reinterpret_cast<std::uintptr_t>(&IsaacModRuntime_EntityRemovePointerIntercept));}
 IsaacModRuntime_EntityRemovePointerIntercept(reinterpret_cast<void*>(0x1000));assert(calls==1);
 assert(!InstallEntityRemovePointerHooks(t).ok());
}
'''.replace('ORIGINAL',','.join(str(v) for v in raw))
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp);(p/'lib/util/sys').mkdir(parents=True);(p/'lib/util/sys/rw_pages.hpp').write_text(shim);(p/'test.cpp').write_text(driver)
   r=subprocess.run(['clang++','-std=c++23','-Wall','-Wextra','-Werror','-I',str(p),'-I',str(ROOT/'runtime/source'),'-I',str(ROOT/'runtime/src'),str(p/'test.cpp'),str(ROOT/'runtime/src/infrastructure/gotslot/entity_remove_pointer_hooks.cpp'),'-o',str(p/'test')],capture_output=True,text=True)
   self.assertEqual(r.returncode,0,r.stdout+r.stderr)
   r=subprocess.run([str(p/'test')],capture_output=True,text=True)
   self.assertEqual(r.returncode,0,r.stdout+r.stderr)
