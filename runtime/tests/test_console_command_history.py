"""Up/Down recalls native command history, not the console output log."""
import subprocess
import tempfile
import unittest
from pathlib import Path

from . import test_console_long_commands as fixture
from . import test_console_panel as panel_fixture


DRIVER = r'''
#include <array>
#include <map>
static std::map<void*,std::string> strings;
static void* StableAssign(void* object,const char* text) {
 auto& owned=strings[object];owned=text;
 assert(console::BuildBorrowedCommandString(owned.c_str(),owned.size(),static_cast<unsigned char*>(object)));
 return object;
}
static void NativeHints(void* object) {
 const char* rows[]={"giveitem  goto  gridspawn","c1 Sad Onion  c2 Inner Eye","stage 1  stage 2","","native hint four","native hint five"};
 for(unsigned i=0;i<6;++i)StableAssign(static_cast<unsigned char*>(object)+0xc0+i*0x18,rows[i]);
}
static std::uint64_t submittedOffset{};
static void NativeHistory(void* object,const void* text) {
 auto* p=static_cast<unsigned char*>(object);std::uintptr_t map{},cursorMap{},cursor{},block{};std::uint64_t start{};
 std::memcpy(&map,p+0x88,8);std::memcpy(&cursorMap,p+0xb0,8);std::memcpy(&cursor,p+0xb8,8);std::memcpy(&start,p+0xa0,8);
 std::memcpy(&block,reinterpret_cast<void*>(cursorMap),8);
 submittedOffset=(cursorMap-map)/8*170+(cursor-block)/24-start;
 History(object,text);
 // Native AddHistoryEntry resets its iterator after insertion.
 cursorMap=map+(start/170)*8;std::memcpy(&block,reinterpret_cast<void*>(cursorMap),8);cursor=block+(start%170)*24;
 std::memcpy(p+0xb0,&cursorMap,8);std::memcpy(p+0xb8,&cursor,8);
}
int main() {
 std::vector<unsigned char> module(kGameOwnerGlobalSlotOffset+16),game(kGamePlayerArrayEndOffset+16);
 alignas(8) std::uintptr_t player=0x1000,gamePointer=memory::AddressOf(game.data());
 writePointer(module,kGameOwnerGlobalSlotOffset,memory::AddressOf(&gamePointer));writePointer(game,kGamePlayerArrayBeginOffset,memory::AddressOf(&player));writePointer(game,kGamePlayerArrayEndOffset,memory::AddressOf(&player)+8);
 moduleBase=memory::AddressOf(module.data());entries.consoleCtor=MockCtor;entries.consoleInit=MockInit;entries.runCommand=MockConsoleRunCommand;entries.paramsCtor=Params;entries.openKeyboard=Keyboard;
 console::PanelNativeEntries ui{Show,Hide,Update,Render,Lines,StableAssign,Print,NativeHistory,NativeHints};
 console::Panel().hooksReady=true;
 const unsigned a=1u<<14,b=1u<<15,up=1u<<19,down=1u<<20,enter=1u<<12;
 auto frame=[&](unsigned mask=0){console::PanelFrame(entries,ui,moduleBase,1,mask,{},0,0,(mask&(a|b))==(a|b));};
 auto press=[&](unsigned mask){frame();frame(mask);};
 auto input=[&](){const auto* h=console::Storage().consoleObject+0x20;return std::string(console::EngineStringData(h),console::EngineStringSize(h));};
 auto draft=[&](const char* text){console::ResetPanelHistoryNavigation();console::CopyCompletionText(console::Panel().draftUtf8,console::kPanelUtf8Capacity,text,std::strlen(text));assert(console::StorePanelDraftUtf8(text));console::SetPanelInput(ui,text);static_cast<void>(console::RefreshPanelCompletions(ui,text));};
 auto open=[&](){frame();for(int i=0;i<48;++i)frame(a|b);frame();assert(console::ConsolePaused());};
 open();
 static_cast<void>(console::RegisterConsoleCommand("nativeprobe","extension","extension",false,18));
 auto* object=console::Storage().consoleObject;
 std::vector<unsigned char> block1(170*0x18),block2(170*0x18),outputBlock(85*0x30);
 std::array<std::uintptr_t,2> map{memory::AddressOf(block1.data()),memory::AddressOf(block2.data())};
 auto put=[&](std::size_t offset,auto value){std::memcpy(object+offset,&value,sizeof(value));};
 put(0x88,memory::AddressOf(map.data()));put(0x90,memory::AddressOf(map.data())+sizeof(map));put(0xa0,std::uint64_t{169});put(0xa8,std::uint64_t{3});
 put(0xb0,memory::AddressOf(map.data()));put(0xb8,memory::AddressOf(block1.data())+169*24);
 std::array<std::string,3> commands{"cmd-a","cmd-b","cmd-c"};
 unsigned char* rows[]={block1.data()+169*0x18,block2.data(),block2.data()+0x18};
 auto setRow=[&](unsigned index){assert(console::BuildBorrowedCommandString(commands[index].c_str(),commands[index].size(),rows[index]));};
 for(unsigned i=0;i<3;++i)setRow(i);
 std::uintptr_t outputMap=memory::AddressOf(outputBlock.data());put(0x58,memory::AddressOf(&outputMap));put(0x60,memory::AddressOf(&outputMap)+8);put(0x70,std::uint64_t{0});put(0x78,std::uint64_t{1});assert(console::BuildBorrowedCommandString("printed output",14,outputBlock.data()));
 auto hints=[&](){for(unsigned i=0;i<6;++i){const auto* h=object+0xc0+i*24;const char* expected[]={"giveitem  goto  gridspawn","c1 Sad Onion  c2 Inner Eye","stage 1  stage 2","","native hint four","native hint five"};assert(std::string(console::EngineStringData(h),console::EngineStringSize(h))==expected[i]);}assert(console::CompletionCount()==0);};
 // Expected transitions were replayed from PC 1.7.9b.J835 ProcessInput @ 0x663550.
 draft("draft");press(down);assert(input().empty());
 draft("draft");press(up);assert(input()=="cmd-a");hints();
 for(int i=0;i<25;++i)frame(up);assert(input()=="cmd-a"); // PC uses triggered edges, not repeat
 press(up);assert(input()=="cmd-b");press(up);assert(input()=="cmd-c");press(up);assert(input()=="cmd-c");
 press(down);assert(input()=="cmd-b");press(down);assert(input()=="cmd-a");press(down);assert(input().empty());press(down);assert(input().empty());
 draft("draft");press(up);assert(input()=="cmd-a");
 press(a);const std::uint32_t edited[]={'e','d','i','t','e','d',0};console::PanelKeyboardChanged(edited,nullptr);console::KeyboardFinishedCallback(nullptr,nullptr);frame();
 assert(input()=="edited");press(up);assert(input()=="cmd-b");press(down);assert(input()=="cmd-a");press(down);assert(input().empty());
 press(up);press(up);assert(input()=="cmd-b");press(b);frame();open();press(up);assert(input()=="cmd-c");
 // Packed native hint rows are not selectable commands. L/R cannot turn them into input.
 press(1u<<21);press(1u<<22);assert(input()=="cmd-c");hints();assert(calls==0);
 press(down);press(down);press(down);assert(input().empty());
 // A recalled command can exceed the system keyboard's limit without being truncated.
 commands[0]=std::string(2100,'x');setRow(0);press(up);assert(input()==commands[0]);
 auto beforeKeyboards=keyboards;press(a);assert(keyboards==beforeKeyboards && input()==commands[0]);
 press(b);frame();open();assert(input()==commands[0]);press(down);assert(input().empty());
 commands[0].clear();for(int i=0;i<500;++i)commands[0]+="\xf0\x9f\x8c\xb1";setRow(0);press(up);
 assert(input()==commands[0] && console::Panel().draft[499]==0x1f331 && console::Panel().draft[500]==0);press(down);
 // Plus submits full long history directly, without a system-keyboard truncation.
 commands[0]=std::string(2100,'z');setRow(0);press(up);
 expected=console::PanelInputText();expectedLength=2100;
 press(enter);assert(calls==1 && histories==1 && input().empty());
 // Plus maps to native Enter. Whitespace-only input is not submitted or cleared.
 draft("   ");press(enter);assert(calls==1 && histories==1 && input()=="   ");
 commands[0]="cmd-a";setRow(0);draft("");press(up);press(up);assert(input()=="cmd-b");
 expected="cmd-b";expectedLength=5;press(enter);assert(calls==2 && histories==2 && submittedOffset==2 && input().empty());hints();
 commands[0]="cmd-b";setRow(0);press(up);assert(input()=="cmd-b");press(down);assert(input().empty());
 press(enter);frame();assert(!console::ConsolePaused()); // native Enter on empty input closes
 // Only the enabled extension consumes registered candidates and maps X to PC Tab.
 ui.extensionEnabled=[](){return true;};
 console::SetConsoleCompletionCatalogProvider(nullptr,[]() noexcept {return true;});
 ui.fillOmnicomplete=[](void* p){for(unsigned i=0;i<6;++i)StableAssign(static_cast<unsigned char*>(p)+0xc0+i*24,"");};
 static_cast<void>(console::RegisterConsoleCommand("alpha","first","first",false,0));
 static_cast<void>(console::RegisterConsoleCommand("alphabet","second","second",false,0));
 open();draft("al");assert(console::CompletionCount()==2);
 press(1u<<21);press(1u<<22);assert(input()=="al");
 press(1u<<23);assert(input()=="alpha" && calls==2);
 press(1u<<23);assert(input()=="alphabet" && calls==2);
 press(1u<<23);assert(input()=="alpha" && console::CompletionCount()==2);
 press(b);frame();open();
 assert(input()=="alpha" && console::Completions().selected==0);
 press(1u<<23);assert(input()=="alphabet" && calls==2);
 auto keyboardsBefore=keyboards;press(a);assert(keyboards==keyboardsBefore+1);
 console::KeyboardFinishedCallback(nullptr,nullptr);frame();assert(calls==2);
 assert(console::ObjectFenceIntact(console::Storage()) && failures==0);
}
'''


class ConsoleCommandHistoryTests(unittest.TestCase):
    def test_actual_panel_native_pc_contract(self):
        with tempfile.TemporaryDirectory(prefix='console-history-') as folder:
            path = Path(folder)
            (path / 'stdfloat').write_text('#pragma once\nnamespace std{using float16_t=float;using float128_t=long double;}\n')
            prefix = fixture.HARNESS[:fixture.HARNESS.index('int main(')]
            prefix += panel_fixture.DRIVER[:panel_fixture.DRIVER.index('int main(')]
            (path / 'test.cpp').write_text(prefix + DRIVER)
            build = subprocess.run([
                fixture.host_compilers()[1], '-std=c++23', '-Wall', '-Wextra', '-Werror',
                '-I'+str(path), '-I'+str(fixture.SOURCE), '-I'+str(fixture.SOURCE.parent/'src'),
                str(path/'test.cpp'), '-o', str(path/'test')], capture_output=True, text=True)
            self.assertEqual(build.returncode, 0, build.stdout + build.stderr)
            run = subprocess.run([str(path/'test')], capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)


if __name__ == '__main__':
    unittest.main()
