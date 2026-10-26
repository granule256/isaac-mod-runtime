"""控制台每帧点在输入入口已挂钩及绑定稍晚发布时仍消费命令。"""
import subprocess,tempfile,unittest
from pathlib import Path
try:
    from .test_input_entity_context import function
except ImportError:
    from test_input_entity_context import function
ROOT=Path(__file__).resolve().parents[2]

class ConsoleInputBindingTests(unittest.TestCase):
    def test_session_uses_published_raw_binding_and_recovers_after_publication(self):
        body=function((ROOT/'runtime/src/infrastructure/console/console_session.hpp').read_text(),'inline void SessionFrameUpdate() noexcept')
        driver=r'''
#include <cassert>
#include <cstdint>
#include <cstddef>
#include "runtime_constants.hpp"
static bool published=false;static unsigned polls{},panelFrames{},depth{};
bool InputQuery(void*,unsigned action,unsigned controller,void* entity){assert(controller==0xffffffffu&&entity==nullptr&&depth>0);++polls;return action==2;}
namespace LuaRuntime {
std::uintptr_t EngineModuleBase(){return 0x1800000000ULL;}
std::uintptr_t InputIsActionPressedBinding(){return published?reinterpret_cast<std::uintptr_t>(&InputQuery):0;}
bool ConsoleConfigMenuVisible(){return false;}
struct RawEngineInputQueryScope{RawEngineInputQueryScope(){++depth;}~RawEngineInputQueryScope(){--depth;}};
}
namespace isaac::runtime {
constexpr unsigned kConsoleNoSecondButton=0xffffffffu;
bool ValidConsoleControls(int){return true;}
namespace engine_call {
template<class F>F AsFunction(std::uintptr_t a){return reinterpret_cast<F>(a);}
// 原生入口已由本运行时挂钩，逐字核旧序言的旧解析器会拒绝。
template<class F,class B,class Check>F ResolveFunction(std::uintptr_t,std::size_t,std::uintptr_t,const B&,Check){return nullptr;}
bool VerifyEntryBytes(std::uintptr_t,const void*,std::size_t,bool(*)(std::uintptr_t,std::size_t)){return true;}
}
namespace engine_memory {
bool EngineMemoryReadable(std::uintptr_t,std::size_t){return true;}
template<class...A>bool ReadAt(A...){return false;}
void*AsObject(std::uintptr_t n){return reinterpret_cast<void*>(n);}
}
namespace console {
using ActionQueryFn=bool(*)(void*,std::uint32_t,std::uint32_t,void*);
struct EngineEntries{};struct Entries{};Entries&SessionPanelEntries(){static Entries e;return e;}
struct S{unsigned armed{},frames{},actionsSeen{},lastAction{};};S&State(){static S s;return s;}
struct C{struct Controls{unsigned first{},second{};operator int()const{return 0;}}controls;};C&Storage(){static C c;return c;}
struct P{unsigned previousMask{};bool touchHeld{};};P&Panel(){static P p;return p;}
struct PanelTouch{bool pressed{};unsigned rawX{},rawY{};};PanelTouch ReadTouchPointer(){return {};}
constexpr unsigned kAnyController=0xffffffffu,kActionScanLimit=32;
void ConsoleSwitchTick(){}bool ConsoleSwitchEnabled(){return true;}bool ConsoleCapturesInput(){return false;}
std::uintptr_t KageSystemManager(std::uintptr_t){return 1;}
bool ResolveConsoleEntries(std::uintptr_t,std::size_t,EngineEntries*){return true;}
bool ResolvePanelEntries(std::uintptr_t,std::size_t,Entries*){return true;}
unsigned NativePanelState(){return 0;}
std::uintptr_t LoadPointerField(std::uintptr_t,std::uintptr_t){return 0;}
float ScreenWidth(std::uintptr_t){return 1280;}
void PanelFrame(const EngineEntries&,const Entries&,std::uintptr_t,std::uintptr_t,unsigned mask,PanelTouch,float,float,bool,bool=false){assert(mask==4&&depth==0);++panelFrames;}
BODY
}}
int main(){
 isaac::runtime::console::SessionFrameUpdate();assert(panelFrames==0&&polls==0);
 published=true;isaac::runtime::console::SessionFrameUpdate();assert(panelFrames==1&&polls==32);
 isaac::runtime::console::SessionFrameUpdate();assert(panelFrames==2&&polls==64&&depth==0);
}
'''.replace('BODY',body)
        with tempfile.TemporaryDirectory(prefix='console-input-binding-') as tmp:
            p=Path(tmp);(p/'main.cpp').write_text(driver)
            r=subprocess.run(['c++','-std=c++23','-Wall','-Wextra','-Werror','-I'+str(ROOT/'runtime/source'),str(p/'main.cpp'),'-o',str(p/'probe')],capture_output=True,text=True)
            self.assertEqual(r.returncode,0,r.stdout+r.stderr)
            r=subprocess.run([str(p/'probe')],capture_output=True,text=True)
            self.assertEqual(r.returncode,0,r.stdout+r.stderr)

if __name__=='__main__':unittest.main()
