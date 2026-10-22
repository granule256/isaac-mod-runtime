"""原生房间完成槽：固定NRO守卫，原调用结束前不得发布完成。"""
import subprocess,tempfile,unittest,sys,struct,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
class NativeRoomInstallerTests(unittest.TestCase):
 def test_pinned_native_completion_slot_and_guards(self):
  sys.path.insert(0,str(ROOT/'tools'));from gen_engine_symbol_signatures import NRO
  from nro_symbols import parse_dynamic_relocations
  data=NRO.read_bytes();_,rows=parse_dynamic_relocations(data)
  key='_ZN15IsaacRepentance5Level9load_roomEv'
  self.assertEqual([(r.offset,r.relocation_type)for r in rows[key]],[(0xaa3f18,1026)])
  text=(ROOT/'runtime/source/mod_room_guards.hpp').read_text().split('namespace isaac::runtime::native_room {',1)[1]
  for name,off in [('Load',0x3d6cb0),('Tail',0x3d79e0),('Plt',0x67bf60)]:
   raw=re.search('k'+name+r'Bytes\{(.*?)\}',text).group(1)
   self.assertEqual(bytes(int(x,16)for x in re.findall(r'0x([a-f0-9]{2})',raw)),data[off:off+16])
 def test_corrupt_guards_or_foreign_slot_never_install(self):
  shim='#pragma once\n#include <cstdint>\n#include <cstddef>\nnamespace exl::util{struct RwPages{std::uintptr_t p;RwPages(std::uintptr_t a,std::size_t):p(a){}std::uintptr_t GetRw()const{return p;}void Flush(){}};}\n'
  driver=r'''
#include "mod_room_hook.hpp"
#include "native_room_events.hpp"
#include "mod_room_guards.hpp"
#include "runtime_constants.hpp"
#include <cassert>
#include <cstring>
#include <vector>
namespace isaac::runtime::modmenu{void LoadEngineModRoomsAfterStage(void*,int,int)noexcept{}}
using namespace isaac::runtime;
struct FakeLevel{std::uint32_t stage=1,type=0;int finished=0;};
void FakeLoad(void* p){assert(NativeRoomLoadGeneration()==0&&!NativeLoadedLevelMatches(2,0));auto*level=static_cast<FakeLevel*>(p);level->stage=2;level->finished=1;}
int main(){FakeLevel level;CompleteNativeRoomLoad(FakeLoad,&level);assert(level.finished==1&&NativeRoomLoadGeneration()==1&&NativeLoadedLevelMatches(2,0)&&!NativeLoadedLevelMatches(2,1));
std::vector<unsigned char>image(0xab0000);auto base=reinterpret_cast<std::uintptr_t>(image.data());
 auto copy=[&](auto offset,const auto&bytes){memcpy(image.data()+offset,bytes.data(),bytes.size());};
 copy(native_room::kLoadOffset,native_room::kLoadBytes);copy(native_room::kTailOffset,native_room::kTailBytes);copy(native_room::kPltOffset,native_room::kPltBytes);
 auto write=[&](auto pointer){memcpy(image.data()+native_room::kGotOffset,&pointer,8);};
 HookTarget t{};t.base=base;t.codeSize=0x68d000;t.imageSize=image.size();t.buildId=kTargetBuildId;
 write(base+native_room::kLoadOffset);
 auto reject=[&](auto offset,const auto&bytes){for(unsigned i=0;i<bytes.size();++i){image[offset+i]^=1;assert(!InstallLevelRoomPointerHook(t).ok());image[offset+i]^=1;}};
 reject(native_room::kLoadOffset,native_room::kLoadBytes);reject(native_room::kTailOffset,native_room::kTailBytes);reject(native_room::kPltOffset,native_room::kPltBytes);
 write(std::uintptr_t{123});assert(!InstallLevelRoomPointerHook(t).ok());write(base+kPltResolverOffset);
 auto wrong=t;wrong.buildId[0]^=1;assert(!InstallLevelRoomPointerHook(wrong).ok());
 assert(InstallLevelRoomPointerHook(t).ok());assert(!InstallLevelRoomPointerHook(t).ok());}
'''
  with tempfile.TemporaryDirectory(prefix='isaac-mod-room-install-')as tmp:
   p=Path(tmp);(p/'lib/util/sys').mkdir(parents=True);(p/'lib/util/sys/rw_pages.hpp').write_text(shim)
   (p/'mod_menu_native.hpp').write_text('#pragma once\nnamespace isaac::runtime::modmenu{void LoadEngineModRoomsAfterStage(void*,int,int)noexcept;}\n')
   (p/'test.cpp').write_text(driver)
   r=subprocess.run(['clang++','-std=c++23','-Wall','-Wextra','-Werror','-I',str(p),'-I',str(ROOT/'runtime/source'),'-I',str(ROOT/'runtime/src'),str(p/'test.cpp'),str(ROOT/'runtime/src/infrastructure/gotslot/mod_room_pointer_hook.cpp'),'-o',str(p/'test')],capture_output=True,text=True)
   self.assertEqual(r.returncode,0,r.stdout+r.stderr)
   r=subprocess.run([str(p/'test')],capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
