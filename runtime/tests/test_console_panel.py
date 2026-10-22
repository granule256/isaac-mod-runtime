"""真实面板适配器的打开、键盘往返、暂停与输入隔离；引擎入口用宿主替身。"""
import subprocess,tempfile,unittest
from pathlib import Path
from . import test_console_long_commands as f

DRIVER=r'''
#include "infrastructure/console/console_panel.hpp"
#include <cassert>
#include <string>
using namespace isaac::runtime;
unsigned shown{},hidden{},updates{},renders{},keyboards{},prints{},lineBreaks{};
std::string printed;
unsigned histories{};
void History(void* object,const void* head){++histories;auto* h=static_cast<const unsigned char*>(head);auto* input=static_cast<const unsigned char*>(object)+0x20;assert(console::EngineStringSize(input)==console::EngineStringSize(h));assert(std::string(console::EngineStringData(input),console::EngineStringSize(input))==std::string(console::EngineStringData(h),console::EngineStringSize(h)));printed+=std::string(console::EngineStringData(h),console::EngineStringSize(h));}
void Show(void* p){++shown;*static_cast<unsigned*>(p)=1;}
void Hide(void* p){++hidden;*static_cast<unsigned*>(p)=4;}
bool Update(void* p){++updates;auto& s=*static_cast<unsigned*>(p);s=s==4?0:2;return s!=0;}
void Render(void*){++renders;}
void Lines(void*){++lineBreaks;}
void* Assign(void* p,const char* text){static char buffer[2100];std::strcpy(buffer,text);assert(console::BuildBorrowedCommandString(buffer,strlen(buffer),static_cast<unsigned char*>(p)));return p;}
void Print(void*,const void* text,unsigned,unsigned){++prints;const auto* s=static_cast<const unsigned char*>(text);printed.append(console::EngineStringData(s),console::EngineStringSize(s));}
void Params(void* p){std::memset(p,0,0x38);}
void Keyboard(std::uintptr_t,const void*,unsigned){++keyboards;}
int main(){
 std::vector<unsigned char> module(kGameOwnerGlobalSlotOffset+16),game(kGamePlayerArrayEndOffset+16);
 alignas(8) std::uintptr_t player=0x1000,gamePointer=memory::AddressOf(game.data());
 writePointer(module,kGameOwnerGlobalSlotOffset,memory::AddressOf(&gamePointer));writePointer(game,kGamePlayerArrayBeginOffset,memory::AddressOf(&player));writePointer(game,kGamePlayerArrayEndOffset,memory::AddressOf(&player)+8);
 moduleBase=memory::AddressOf(module.data());entries.consoleCtor=MockCtor;entries.consoleInit=MockInit;entries.runCommand=MockConsoleRunCommand;entries.paramsCtor=Params;entries.openKeyboard=Keyboard;
 console::PanelNativeEntries ui{Show,Hide,Update,Render,Lines,Assign,Print,History};
 console::Panel().hooksReady=true;
 auto frame=[&](unsigned mask=0,bool touch=false,unsigned x=0,unsigned y=0){console::PanelFrame(entries,ui,moduleBase,1,mask,{touch,x,y},426,240,(mask&((1u<<14)|(1u<<15)))==((1u<<14)|(1u<<15)));};
 const unsigned a=1u<<14,b=1u<<15;
 // 长按只打开面板，松开之前不能把A当成编辑。
 for(int i=0;i<48;++i)frame(a|b);
 assert(shown==1&&keyboards==0&&console::ConsolePaused());
 for(int i=0;i<20;++i)frame(a|b);
 assert(shown==1&&keyboards==0);
 frame();console::RenderPanel(ui);assert(renders==1);
 frame(0,true,1280,720);assert(keyboards==0); // 超出原始屏幕的触点拒绝
 frame();frame(0,true,300,680);assert(keyboards==0); // 面板底部是补全区，不是输入行
 frame();frame(0,true,300,410);assert(keyboards==1&&console::Panel().keyboardOpen);
 for(int i=0;i<8;++i)frame(a,true,300,410);assert(keyboards==1);
 const std::uint32_t draft[]={'g',' ','c','1',0};console::PanelKeyboardChanged(draft,nullptr);
 console::KeyboardFinishedCallback(nullptr,nullptr);frame();
 assert(std::string(console::Panel().draftUtf8)=="g c1" && lineBreaks>=2);
 assert(histories==0);
 assert(calls==0&&!console::Panel().keyboardOpen&&console::ConsolePaused());
 console::Storage().log.Append("keep",4);
 frame();frame(a);assert(keyboards==2);
 assert(std::strncmp(console::Storage().log.Line(0),"keep",4)==0); // 手柄确认选中的输入行
 const std::uint32_t command[]={'d','e','b','u','g',' ','3',0};expected="debug 3";expectedLength=7;
 console::KeyboardFinishedCallback(command,nullptr);frame(a);frame(a);assert(calls==1&&console::ConsolePaused()&&histories==1);
 assert(printed.find("debug 3")!=std::string::npos&&printed.find("ok")!=std::string::npos);
 frame();frame(b);assert(hidden==1&&!console::ConsolePaused()&&console::ConsoleCapturesInput());
 frame(b);assert(console::ConsoleCapturesInput());frame();assert(!console::ConsoleCapturesInput());
 // 重开、关闭总开关不遗留暂停，不执行键盘迟到结果。
 for(int i=0;i<48;++i)frame(a|b);frame();frame(a);assert(keyboards==3);
 console::Storage().switchEnabled=false;frame();console::KeyboardFinishedCallback(command,nullptr);frame();assert(!console::ConsolePaused()&&calls==1);
 console::Storage().switchEnabled=true;frame();
 for(int i=0;i<48;++i)frame(a|b);frame();assert(console::ConsolePaused());
 frame(a);assert(console::Panel().keyboardOpen);
 console::InvalidateConsoleSession();frame();assert(!console::ConsolePaused());
 console::KeyboardFinishedCallback(command,nullptr);frame();assert(calls==1&&!console::ConsolePaused());
 frame();for(int i=0;i<48;++i)frame(a|b);frame();assert(console::ConsolePaused());
 gamePointer=0;frame();assert(!console::ConsolePaused());
 console::RenderPanel(ui);assert(renders==1);
 assert(console::ObjectFenceIntact(console::Storage()));
 // 系统键盘实际允许500字符；超过原63字符的提交必须完整执行，不能截短。
 gamePointer=memory::AddressOf(game.data());frame();for(int i=0;i<48;++i)frame(a|b);frame();frame(a);
 std::vector<std::uint32_t> longText(501,'x');longText[500]=0;std::string longCommand(500,'x');
 expected=longCommand.c_str();expectedLength=500;
 console::KeyboardFinishedCallback(longText.data(),nullptr);expected=console::Panel().completedUtf8;frame();assert(calls==2&&console::Panel().completedLength==500&&histories==2);
 const auto previousUpdates=updates,previousHidden=hidden;
 console::Storage().consoleObject[kConsoleObjectSize-1]=0;frame();
 assert(console::State().fenceBroken==1&&updates==previousUpdates&&hidden==previousHidden&&!console::ConsolePaused());
 return failures?1:0;
}
'''
class ConsolePanelTests(unittest.TestCase):
 def test_actual_panel_keyboard_roundtrip(self):
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp);(p/'stdfloat').write_text('#pragma once\nnamespace std{using float16_t=float;using float128_t=long double;}\n')
   (p/'test.cpp').write_text(f.HARNESS[:f.HARNESS.index('int main(')]+DRIVER)
   r=subprocess.run([f.host_compilers()[1],'-std=c++23','-Wall','-Wextra','-Werror','-I',tmp,'-I',str(f.SOURCE),'-I',str(f.SOURCE.parent/'src'),str(p/'test.cpp'),'-o',str(p/'test')],capture_output=True,text=True)
   self.assertEqual(r.returncode,0,r.stdout+r.stderr)
   r=subprocess.run([str(p/'test')],capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
