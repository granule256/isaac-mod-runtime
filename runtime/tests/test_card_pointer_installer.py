import subprocess,tempfile,unittest,sys,struct
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
NRO=Path('/Users/kelinls/code/github/isaac mod/The Binding of Isaac_ Afterbirth+ 1.7.9b [010021C000B6A800][v524288][UPD]/Program #0/1/.nro/Repentance.nro')
class CardInstallerTests(unittest.TestCase):
 def test_real_single_got_and_basic_callers(self):
  sys.path.insert(0,str(ROOT/'tools'));from nro_symbols import parse_dynamic_relocations
  image=NRO.read_bytes();_,rows=parse_dynamic_relocations(image)
  self.assertEqual([(x.offset,x.relocation_type,x.addend)for x in rows['_ZNK15IsaacRepentance8ItemPool7GetCardEjbbb']],[(0xaa0140,1026,0)])
  direct=[];plt=[]
  for i,(w,)in enumerate(struct.iter_unpack('<I',image[:0x68d000])):
   if w&0x7c000000!=0x14000000:continue
   imm=w&0x3ffffff
   if imm&0x2000000:imm-=0x4000000
   target=i*4+imm*4
   if target==0x3c8488:direct.append(i*4)
   if target==0x6743b0:plt.append(i*4)
  self.assertEqual(direct,[]);self.assertEqual(len(plt),25)
 def test_guarded_cas_original_publication(self):
  shim='''#pragma once
#include <cstdint>
#include <cstddef>
namespace exl::util {struct RwPages {std::uintptr_t p;RwPages(std::uintptr_t a,std::size_t):p(a){} std::uintptr_t GetRw()const{return p;}void Flush(){}};}
'''
  driver=r'''
#include "card_hook.hpp"
#include "card_guards.hpp"
#include "runtime_constants.hpp"
#include <cassert>
#include <cstring>
#include <vector>
using namespace isaac::runtime;
std::uintptr_t want{};unsigned calls{};
namespace isaac::runtime {std::uint32_t RunCardIntercept(const CardNativeBindings*n,const void*,std::uint32_t,bool,bool,bool)noexcept{assert(reinterpret_cast<std::uintptr_t>(n->getCard)==want);++calls;return 9;}}
extern "C" std::uint32_t IsaacModRuntime_CardPointerIntercept(const void*,std::uint32_t,bool,bool,bool);
int main(){std::vector<unsigned char> image(0xab0000);auto base=reinterpret_cast<std::uintptr_t>(image.data());want=base+card::kBasicOffset;
 auto guard=[&](auto off,const auto&bytes){memcpy(image.data()+off,bytes.data(),bytes.size());};
 guard(card::kBasicOffset,card::kBasicBytes);guard(card::kPltOffset,card::kPltBytes);guard(card::kCtorOffset,card::kCtorBytes);guard(card::kDtorOffset,card::kDtorBytes);guard(card::kShiftsOffset,card::kShiftsBytes);
 auto write=[&](auto v){memcpy(image.data()+card::kGotOffset,&v,8);};write(want);
 HookTarget t{};t.base=base;t.codeSize=0x68d000;t.imageSize=image.size();t.buildId=kTargetBuildId;
 auto rejectEachByte=[&](auto off,const auto& bytes){for(unsigned i=0;i<bytes.size();++i){image[off+i]^=1;assert(!InstallCardPointerHook(t).ok());image[off+i]^=1;}};
 rejectEachByte(card::kBasicOffset,card::kBasicBytes);rejectEachByte(card::kPltOffset,card::kPltBytes);rejectEachByte(card::kCtorOffset,card::kCtorBytes);rejectEachByte(card::kDtorOffset,card::kDtorBytes);rejectEachByte(card::kShiftsOffset,card::kShiftsBytes);
 write(std::uintptr_t{123});assert(!InstallCardPointerHook(t).ok());write(base+kPltResolverOffset);
 assert(ResolveCardApiEntry(base)==nullptr);
 assert(InstallCardPointerHook(t).ok());assert(ResolveCardApiEntry(0)==nullptr&&ResolveCardApiEntry(base+1)==nullptr);
 auto api=ResolveCardApiEntry(base);assert(api&&api(nullptr,1,false,false,false)==9&&calls==1);
 write(std::uintptr_t{123});assert(ResolveCardApiEntry(base)==nullptr);
 write(reinterpret_cast<std::uintptr_t>(&IsaacModRuntime_CardPointerIntercept));
 assert(IsaacModRuntime_CardPointerIntercept(nullptr,1,false,false,false)==9&&calls==2);assert(!InstallCardPointerHook(t).ok());}
'''
  with tempfile.TemporaryDirectory()as tmp:
   p=Path(tmp);(p/'lib/util/sys').mkdir(parents=True);(p/'lib/util/sys/rw_pages.hpp').write_text(shim);(p/'test.cpp').write_text(driver)
   r=subprocess.run(['clang++','-std=c++23','-Wall','-Wextra','-Werror','-I',str(p),'-I',str(ROOT/'runtime/source'),'-I',str(ROOT/'runtime/src'),str(p/'test.cpp'),str(ROOT/'runtime/src/infrastructure/gotslot/card_pointer_hook.cpp'),'-o',str(p/'test')],capture_output=True,text=True)
   self.assertEqual(r.returncode,0,r.stdout+r.stderr);r=subprocess.run([str(p/'test')],capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
