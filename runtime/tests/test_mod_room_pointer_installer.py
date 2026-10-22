"""STB原生加载槽：固定NRO重定位、逐字节守卫、只改一条指针。"""
import subprocess,tempfile,unittest,sys,struct,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
class ModRoomInstallerTests(unittest.TestCase):
 def test_pinned_load_got_and_exact_native_guards(self):
  sys.path.insert(0,str(ROOT/'tools'));from gen_engine_symbol_signatures import NRO
  from nro_symbols import parse_dynamic_relocations
  data=NRO.read_bytes();_,rows=parse_dynamic_relocations(data)
  key='_ZN15IsaacRepentance10RoomConfig15LoadStageBinaryENS0_6eStageENS0_5eModeE'
  self.assertEqual([(r.offset,r.relocation_type)for r in rows[key]],[(0xaa57a0,1026)])
  text=(ROOT/'runtime/source/mod_room_guards.hpp').read_text()
  for name,off in [('Load',0x4906a8),('Update',0x4218e4),('Plt',0x67f070)]:
   raw=re.search('k'+name+r'Bytes\{(.*?)\}',text).group(1)
   self.assertEqual(bytes(int(x,16)for x in re.findall(r'0x([a-f0-9]{2})',raw)),data[off:off+16])
  # Switch未接入UpdateRooms，不能误认成已有原生收尾再重复合并。
  direct=[]
  for i,(word,)in enumerate(struct.iter_unpack('<I',data[:0x68d000])):
   if word&0xfc000000!=0x94000000:continue
   value=word&0x3ffffff
   if value&0x2000000:value-=0x4000000
   if i*4+value*4==0x4218e4:direct.append(i*4)
  self.assertEqual(direct,[])
 def test_corrupt_guards_or_foreign_slot_never_install(self):
  shim='#pragma once\n#include <cstdint>\n#include <cstddef>\nnamespace exl::util{struct RwPages{std::uintptr_t p;RwPages(std::uintptr_t a,std::size_t):p(a){}std::uintptr_t GetRw()const{return p;}void Flush(){}};}\n'
  driver=r'''
#include "mod_room_hook.hpp"
#include "mod_room_guards.hpp"
#include "runtime_constants.hpp"
#include <cassert>
#include <cstring>
#include <vector>
namespace isaac::runtime::modmenu{void LoadEngineModRoomsAfterStage(void*,int,int)noexcept{}}
using namespace isaac::runtime;
int main(){std::vector<unsigned char>image(0xab0000);auto base=reinterpret_cast<std::uintptr_t>(image.data());
 auto copy=[&](auto offset,const auto&bytes){memcpy(image.data()+offset,bytes.data(),bytes.size());};
 copy(mod_rooms::kLoadOffset,mod_rooms::kLoadBytes);copy(mod_rooms::kUpdateOffset,mod_rooms::kUpdateBytes);copy(mod_rooms::kPltOffset,mod_rooms::kPltBytes);
 auto write=[&](auto pointer){memcpy(image.data()+mod_rooms::kGotOffset,&pointer,8);};
 HookTarget t{};t.base=base;t.codeSize=0x68d000;t.imageSize=image.size();t.buildId=kTargetBuildId;
 write(base+mod_rooms::kLoadOffset);
 auto reject=[&](auto offset,const auto&bytes){for(unsigned i=0;i<bytes.size();++i){image[offset+i]^=1;assert(!InstallModRoomPointerHook(t).ok());image[offset+i]^=1;}};
 reject(mod_rooms::kLoadOffset,mod_rooms::kLoadBytes);reject(mod_rooms::kUpdateOffset,mod_rooms::kUpdateBytes);reject(mod_rooms::kPltOffset,mod_rooms::kPltBytes);
 write(std::uintptr_t{123});assert(!InstallModRoomPointerHook(t).ok());write(base+kPltResolverOffset);
 auto wrong=t;wrong.buildId[0]^=1;assert(!InstallModRoomPointerHook(wrong).ok());
 assert(InstallModRoomPointerHook(t).ok());assert(!InstallModRoomPointerHook(t).ok());}
'''
  with tempfile.TemporaryDirectory(prefix='isaac-mod-room-install-')as tmp:
   p=Path(tmp);(p/'lib/util/sys').mkdir(parents=True);(p/'lib/util/sys/rw_pages.hpp').write_text(shim)
   (p/'mod_menu_native.hpp').write_text('#pragma once\nnamespace isaac::runtime::modmenu{void LoadEngineModRoomsAfterStage(void*,int,int)noexcept;}\n')
   (p/'test.cpp').write_text(driver)
   r=subprocess.run(['clang++','-std=c++23','-Wall','-Wextra','-Werror','-I',str(p),'-I',str(ROOT/'runtime/source'),'-I',str(ROOT/'runtime/src'),str(p/'test.cpp'),str(ROOT/'runtime/src/infrastructure/gotslot/mod_room_pointer_hook.cpp'),'-o',str(p/'test')],capture_output=True,text=True)
   self.assertEqual(r.returncode,0,r.stdout+r.stderr)
   r=subprocess.run([str(p/'test')],capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
