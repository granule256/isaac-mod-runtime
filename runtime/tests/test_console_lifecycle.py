"""控制台暂停/绘制包装真实行为与原件GOT三槽身份；现扩展覆盖第四个位置插值槽。"""
import subprocess,tempfile,unittest,sys,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
class ConsoleLifecycleTests(unittest.TestCase):
 def test_native_guards_and_symbol_slots(self):
  sys.path.insert(0,str(ROOT/'tools'));from gen_engine_symbol_signatures import NRO
  from nro_symbols import parse_dynamic_relocations
  d=NRO.read_bytes();_,rows=parse_dynamic_relocations(d)
  for name,slot in [('ProcessInput',0xaa4448),('Update',0xaa4458),('Render',0xaa4508),('InterpolatePositions',0xaa4470)]:
   key='_ZN15IsaacRepentance4Game'+str(len(name))+name+'Ev'
   self.assertEqual([(x.offset,x.relocation_type)for x in rows[key]],[(slot,1026)])
  text=(ROOT/'runtime/src/infrastructure/console/console_panel_guards.hpp').read_text()
  for name,off in re.findall(r'k(\w+)Offset=0x([0-9A-F]+)',text):
   raw=re.search('k'+name+r'Bytes=\{(.*?)\}',text).group(1)
   self.assertEqual(bytes(int(x,16)for x in re.findall(r'0x([0-9A-F]{2})',raw)),d[int(off,16):int(off,16)+16],name)
 def test_grouped_slot_installer_and_pause_wrappers(self):
  driver=r'''
#include "console_lifecycle_hook.hpp"
#include "infrastructure/console/console_panel_guards.hpp"
#include "infrastructure/console/console_panel_storage.hpp"
#include "runtime_constants.hpp"
#include <cassert>
#include <cstring>
#include <vector>
using namespace isaac::runtime;
namespace n=console::native_panel;
extern "C" void IsaacModRuntime_ConsoleGameInterpolate(void*);
constexpr std::uintptr_t interpolationOffset=0x353ab0,interpolationPlt=0x67ca10,interpolationGot=0xaa4470;
constexpr std::array<std::uint8_t,16> interpolationBytes={0xfd,0x7b,0xbd,0xa9,0xf6,0x57,0x01,0xa9,0xfd,0x03,0x00,0x91,0xf4,0x4f,0x02,0xa9};
constexpr std::array<std::uint8_t,16> interpolationPltBytes={0x50,0x21,0x00,0x90,0x11,0x3a,0x42,0xf9,0x10,0xc2,0x11,0x91,0x20,0x02,0x1f,0xd6};
unsigned input{},updates{},renders{},panel{};
void Input(void*){++input;}void Update(void*){++updates;}void Render(void*){assert(renders==panel);++renders;}
namespace isaac::runtime::console {void RenderConsoleAfterGame()noexcept{assert(renders==panel+1);++panel;}}
int main(){
 console::RunConsoleGameInput(nullptr,Input);console::RunConsoleGameUpdate(nullptr,Update);
 console::g_ConsoleInputCaptured.store(1);console::g_ConsolePaused.store(1);
 console::RunConsoleGameInput(nullptr,Input);console::RunConsoleGameUpdate(nullptr,Update);
 console::RunConsoleGameRender(nullptr,Render);assert(input==1&&updates==1&&renders==1&&panel==1);
 console::g_ConsolePaused.store(0);console::RunConsoleGameUpdate(nullptr,Update);assert(updates==2);
 std::vector<unsigned char> image(0xab0000);auto base=reinterpret_cast<std::uintptr_t>(image.data());
 auto copy=[&](auto off,const auto& bytes){memcpy(image.data()+off,bytes.data(),bytes.size());};
 copy(n::kGameInputOffset,n::kGameInputBytes);copy(n::kGameUpdateOffset,n::kGameUpdateBytes);copy(n::kGameRenderOffset,n::kGameRenderBytes);
 copy(n::kGameInputPltOffset,n::kGameInputPltBytes);copy(n::kGameUpdatePltOffset,n::kGameUpdatePltBytes);copy(n::kGameRenderPltOffset,n::kGameRenderPltBytes);
 copy(interpolationOffset,interpolationBytes);copy(interpolationPlt,interpolationPltBytes);
 const unsigned slots[]={n::kGameInputGot,n::kGameUpdateGot,n::kGameRenderGot,interpolationGot};
 auto reset=[&](){for(auto s:slots){auto pointer=base+kPltResolverOffset;memcpy(image.data()+s,&pointer,8);}};
 auto pristine=[&](){for(auto s:slots){std::uintptr_t p{};memcpy(&p,image.data()+s,8);assert(p==base+kPltResolverOffset);}assert(!console::Panel().hooksReady);};
 HookTarget t{};t.base=base;t.codeSize=0x68d000;t.imageSize=image.size();t.buildId=kTargetBuildId;reset();
 for(auto off:{n::kGameInputOffset,n::kGameUpdateOffset,n::kGameRenderOffset,n::kGameInputPltOffset,n::kGameUpdatePltOffset,n::kGameRenderPltOffset,interpolationOffset,interpolationPlt})for(unsigned i=0;i<16;++i){image[off+i]^=1;assert(!InstallConsoleLifecycleHook(t).ok());image[off+i]^=1;pristine();}
 for(auto s:slots){std::uintptr_t bad=123;memcpy(image.data()+s,&bad,8);assert(!InstallConsoleLifecycleHook(t).ok());reset();pristine();}
 assert(InstallConsoleLifecycleHook(t).ok()&&console::Panel().hooksReady);assert(!InstallConsoleLifecycleHook(t).ok());
 std::uintptr_t interpolationTarget{};memcpy(&interpolationTarget,image.data()+interpolationGot,8);
 assert(interpolationTarget!=base+kPltResolverOffset&&interpolationTarget!=base+interpolationOffset);
 assert(interpolationTarget==reinterpret_cast<std::uintptr_t>(&IsaacModRuntime_ConsoleGameInterpolate));
 console::g_ConsolePaused.store(1);
 reinterpret_cast<console::GameFrameFunction>(interpolationTarget)(nullptr);
 console::g_ConsolePaused.store(0);
}
'''
  shim='#pragma once\n#include <cstdint>\n#include <cstddef>\nnamespace exl::util{struct RwPages{std::uintptr_t p;RwPages(std::uintptr_t a,std::size_t):p(a){}std::uintptr_t GetRw()const{return p;}void Flush(){}};}\n'
  with tempfile.TemporaryDirectory()as tmp:
   p=Path(tmp);(p/'lib/util/sys').mkdir(parents=True);(p/'lib/util/sys/rw_pages.hpp').write_text(shim);(p/'test.cpp').write_text(driver)
   r=subprocess.run(['clang++','-std=c++23','-Wall','-Wextra','-Werror','-I',tmp,'-I',str(ROOT/'runtime/source'),'-I',str(ROOT/'runtime/src'),str(p/'test.cpp'),str(ROOT/'runtime/src/infrastructure/gotslot/console_lifecycle_hook.cpp'),'-o',str(p/'test')],capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
   r=subprocess.run([str(p/'test')],capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
