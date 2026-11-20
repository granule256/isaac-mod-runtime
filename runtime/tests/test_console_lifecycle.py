"""Control the native console lifecycle and verify font routing and GOT identities."""
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
  key='_ZNK4KAGE8Graphics4Font10DrawStringEPKcffNS0_5ColorEjb'
  self.assertEqual([(x.offset,x.relocation_type)for x in rows[key]],[(0xa9ec40,1026)])
  for pc in (0x4bdcc,0x4bef0,0x4bf64,0x4c1fc,0x4c348,0x4c5e8):
   self.assertEqual(int.from_bytes(d[pc:pc+4],'little'),0x94000000|((0x6719b0-pc)//4))
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
#include "infrastructure/gotslot/console_lifecycle_hook.cpp"
using namespace isaac::runtime;
namespace n=console::native_panel;
extern "C" void IsaacModRuntime_ConsoleGameInterpolate(void*);
constexpr std::uintptr_t interpolationOffset=0x353ab0,interpolationPlt=0x67ca10,interpolationGot=0xaa4470;
constexpr std::array<std::uint8_t,16> interpolationBytes={0xfd,0x7b,0xbd,0xa9,0xf6,0x57,0x01,0xa9,0xfd,0x03,0x00,0x91,0xf4,0x4f,0x02,0xa9};
constexpr std::array<std::uint8_t,16> interpolationPltBytes={0x50,0x21,0x00,0x90,0x11,0x3a,0x42,0xf9,0x10,0xc2,0x11,0x91,0x20,0x02,0x1f,0xd6};
unsigned input{},updates{},renders{},panel{};
void Input(void*){++input;}void Update(void*){++updates;}void Render(void*){assert(renders==panel);++renders;}
namespace isaac::runtime::console {void RenderConsoleAfterGame()noexcept{assert(renders==panel+1);++panel;}}
unsigned fontLoads{},unicodeDraws{};
const float color[4]={1,1,1,1};
const char* candidate="help (\xe5\xb8\xae\xe5\x8a\xa9)";
namespace LuaRuntime {
FontCtorFn FontCtorThunk() noexcept {return +[](void* font){assert(font);};}
FontDestructorFn FontDestructorThunk() noexcept {return +[](void*){assert(false);};}
FontLoadFn FontLoadThunk() noexcept {return +[](void*,const char* path,const char*){
 ++fontLoads;assert(std::strcmp(path,"font/cjk/lanapixel.fnt")==0);return true;
};}
FontDrawStringUTF8Fn FontDrawStringUTF8Thunk() noexcept {
 return +[](void* font,const char* text,float x,float y,const void* rgba,int width,bool center){
  assert(font&&text==candidate&&x==10&&y==15&&rgba==color&&width==123&&center);
  ++unicodeDraws;
 };
}
FontDrawStringFn FontDrawStringThunk() noexcept {
 return +[](void*,const char*,float,float,const void*,int,bool){};
}
}
int main(){
 auto draw=[](std::uintptr_t address,const char* text) {
  return TryDrawConsoleUtf8(address,text,10,15,color,123,true);
 };
 assert(!draw(0x100, candidate));
 assert(!draw(0x4c200,"help"));
 assert(!draw(0x4c200,"\xe5\xb8"));
 assert(fontLoads==0&&unicodeDraws==0);
 assert(draw(0x4c200,candidate));
 assert(draw(0x4bdd0,candidate));
 assert(fontLoads==1&&unicodeDraws==2);
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
 copy(n::kFontDrawPltOffset,n::kFontDrawPltBytes);
 for(auto pc:n::kConsoleFontDrawSites){
  const std::uint32_t bl=0x94000000|((n::kFontDrawPltOffset-pc)/4);
  memcpy(image.data()+pc,&bl,4);
 }
 const unsigned slots[]={n::kGameInputGot,n::kGameUpdateGot,n::kGameRenderGot,interpolationGot};
 auto reset=[&](){for(auto s:slots){auto pointer=base+kPltResolverOffset;memcpy(image.data()+s,&pointer,8);}};
 auto pristine=[&](){for(auto s:slots){std::uintptr_t p{};memcpy(&p,image.data()+s,8);assert(p==base+kPltResolverOffset);}assert(!console::Panel().hooksReady);};
 HookTarget t{};t.base=base;t.codeSize=0x68d000;t.imageSize=image.size();t.buildId=kTargetBuildId;reset();
 for(auto off:{n::kGameInputOffset,n::kGameUpdateOffset,n::kGameRenderOffset,n::kGameInputPltOffset,n::kGameUpdatePltOffset,n::kGameRenderPltOffset,interpolationOffset,interpolationPlt})for(unsigned i=0;i<16;++i){image[off+i]^=1;assert(!InstallConsoleLifecycleHook(t).ok());image[off+i]^=1;pristine();}
 for(auto s:slots){std::uintptr_t bad=123;memcpy(image.data()+s,&bad,8);assert(!InstallConsoleLifecycleHook(t).ok());reset();pristine();}
 assert(InstallConsoleLifecycleHook(t).ok()&&console::Panel().hooksReady);assert(!InstallConsoleLifecycleHook(t).ok());
 const auto resolver=base+kPltResolverOffset;
 auto fontSlot=[&](){std::uintptr_t p{};memcpy(&p,image.data()+n::kFontDrawGot,8);return p;};
 memcpy(image.data()+n::kFontDrawGot,&resolver,8);
 const auto original=LuaRuntime::FontDrawStringThunk();
 for(auto pc:n::kConsoleFontDrawSites){
  image[pc]^=1;assert(!InstallConsoleFontDraw(t,original));image[pc]^=1;assert(fontSlot()==resolver);
 }
 assert(InstallConsoleFontDraw(t,original));
 assert(fontSlot()==reinterpret_cast<std::uintptr_t>(&IsaacModRuntime_ConsoleFontDraw));
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
   r=subprocess.run(['clang++','-std=c++23','-Wall','-Wextra','-Werror','-I',tmp,'-I',str(ROOT/'runtime/source'),'-I',str(ROOT/'runtime/src'),'-I',str(ROOT/'runtime/source/third_party/lua-5.3.3/src'),str(p/'test.cpp'),'-o',str(p/'test')],capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
   r=subprocess.run([str(p/'test')],capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
