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
    assert(console::BuildBorrowedCommandString(owned.c_str(),owned.size(),
        static_cast<unsigned char*>(object)));
    return object;
}
int main() {
    std::vector<unsigned char> module(kGameOwnerGlobalSlotOffset+16),game(kGamePlayerArrayEndOffset+16);
    alignas(8) std::uintptr_t player=0x1000,gamePointer=memory::AddressOf(game.data());
    writePointer(module,kGameOwnerGlobalSlotOffset,memory::AddressOf(&gamePointer));
    writePointer(game,kGamePlayerArrayBeginOffset,memory::AddressOf(&player));
    writePointer(game,kGamePlayerArrayEndOffset,memory::AddressOf(&player)+8);
    moduleBase=memory::AddressOf(module.data());entries.consoleCtor=MockCtor;entries.consoleInit=MockInit;
    entries.runCommand=MockConsoleRunCommand;entries.paramsCtor=Params;entries.openKeyboard=Keyboard;
    console::PanelNativeEntries ui{Show,Hide,Update,Render,Lines,StableAssign,Print,History};
    console::Panel().hooksReady=true;
    const unsigned a=1u<<14,b=1u<<15,up=1u<<19,down=1u<<20,leftShoulder=1u<<21,rightShoulder=1u<<22;
    auto frame=[&](unsigned mask=0){console::PanelFrame(entries,ui,moduleBase,1,mask,{},0,0,(mask&(a|b))==(a|b));};
    auto press=[&](unsigned mask){frame();frame(mask);};
    auto input=[&](){const auto* h=console::Storage().consoleObject+0x20;return std::string(console::EngineStringData(h),console::EngineStringSize(h));};
    auto draft=[&](const char* text){console::CopyCompletionText(console::Panel().draftUtf8,console::kPanelUtf8Capacity,text,std::strlen(text));assert(console::StorePanelDraftUtf8(text));console::SetPanelInput(ui,text);};
    for(int i=0;i<48;++i)frame(a|b);frame();assert(shown==1);
    std::vector<unsigned char> block1(170*0x18),block2(170*0x18),outputBlock(85*0x30);
    std::array<std::uintptr_t,2> map{memory::AddressOf(block1.data()),memory::AddressOf(block2.data())};
    auto* object=console::Storage().consoleObject;
    auto put=[&](std::size_t offset,auto value){std::memcpy(object+offset,&value,sizeof(value));};
    put(0x88,memory::AddressOf(map.data()));put(0x90,memory::AddressOf(map.data())+sizeof(map));
    put(0xa0,std::uint64_t{169});put(0xa8,std::uint64_t{3});
    std::array<std::string,3> commands{"repeat 2","giveitem c1","stage 2"};
    unsigned char* rows[]={block1.data()+169*0x18,block2.data(),block2.data()+0x18};
    auto setRow=[&](unsigned index){assert(console::BuildBorrowedCommandString(commands[index].c_str(),commands[index].size(),rows[index]));};
    for(unsigned i=0;i<commands.size();++i)setRow(i);
    // Printed output lives in a different 0x30-byte-entry deque and must never be recalled.
    std::uintptr_t outputMap=memory::AddressOf(outputBlock.data());
    put(0x58,memory::AddressOf(&outputMap));put(0x60,memory::AddressOf(&outputMap)+8);
    put(0x70,std::uint64_t{0});put(0x78,std::uint64_t{1});
    assert(console::BuildBorrowedCommandString("printed output",14,outputBlock.data()));
    static_cast<void>(console::RegisterConsoleCommand("debug","debug","debug",false,0));
    static_cast<void>(console::RegisterConsoleCommand("giveitem","give","give",false,0));
    static_cast<void>(console::RegisterConsoleCommand("goto","goto","goto",false,0));
    static_cast<void>(console::RegisterConsoleCommand("grid","grid","grid",false,0));
    draft("debug");assert(console::RefreshPanelCompletions(ui,"debug"));
    press(up);assert(input()=="repeat 2" && std::string(console::Panel().draftUtf8)=="repeat 2");
    assert(console::CompletionCount()==0 && console::Completions().selected==-1);
    for(int i=0;i<25;++i)frame(up);assert(input()=="repeat 2"); // one press, one entry
    press(up);assert(input()=="giveitem c1");press(up);assert(input()=="stage 2");
    press(up);assert(input()=="stage 2"); // stop at oldest; no wrap
    press(down);assert(input()=="giveitem c1");press(down);assert(input()=="repeat 2");
    press(down);assert(input()=="debug");press(down);assert(input()=="debug");
    assert(calls==0 && histories==0 && keyboards==0);
    // Completion cycling remains available independently of command recall.
    draft("g");assert(console::RefreshPanelCompletions(ui,"g"));
    assert(console::CompletionCount()==3);
    press(rightShoulder);assert(console::Completions().selected==0);
    press(leftShoulder);assert(console::Completions().selected==2);
    press(up);assert(input()=="repeat 2");
    // Editing a recalled entry starts a new draft, never modifying saved history.
    press(a);assert(console::Panel().keyboardOpen && console::Panel().draft[0]=='r');
    const std::uint32_t edited[]={'e','d','i','t',0};console::PanelKeyboardChanged(edited,nullptr);
    console::KeyboardFinishedCallback(nullptr,nullptr);frame();
    assert(input()=="edit");press(up);assert(input()=="repeat 2");press(down);assert(input()=="edit");
    assert(commands[0]=="repeat 2" && calls==0);
    // Both byte and UTF-32 drafts retain a full 500-codepoint historical command.
    commands[0].clear();for(int i=0;i<500;++i)commands[0]+="\xf0\x9f\x8c\xb1";setRow(0);
    press(up);assert(input()==commands[0] && console::Panel().draft[499]==0x1f331 && console::Panel().draft[500]==0);
    press(down);assert(input()=="edit");
    commands[0]=std::string(2100,'x');setRow(0);press(up);assert(input()=="edit"); // no truncation
    commands[0]=std::string(501,'x');setRow(0);press(up);assert(input()=="edit"); // keyboard limit too
    commands[0]="repeat 2";setRow(0);
    // Empty or invalid native deques do not clobber the current input.
    put(0xa8,std::uint64_t{0});press(up);press(down);assert(input()=="edit");
    put(0xa8,std::uint64_t{3});put(0xa0,UINT64_MAX);press(up);assert(input()=="edit");
    put(0xa0,std::uint64_t{169});
    // Closing/reopening cannot resurrect a stale saved draft/navigation position.
    press(up);assert(input()=="repeat 2");press(b);frame();assert(!console::ConsolePaused());
    for(int i=0;i<48;++i)frame(a|b);frame();assert(console::ConsolePaused());
    press(down);assert(input()=="repeat 2");press(up);assert(input()=="repeat 2");
    press(up);assert(input()=="giveitem c1");
    assert(calls==0);
    // Submitting a recalled/edited command resets navigation to the new history head.
    press(a);const std::uint32_t submitted[]={'d','e','b','u','g',' ','3',0};
    expected="debug 3";expectedLength=7;
    console::KeyboardFinishedCallback(submitted,nullptr);frame();
    assert(calls==1 && histories==1 && input().empty());
    commands[0]="debug 3";setRow(0); // models native AddHistoryEntry inserting at the front
    press(up);assert(input()=="debug 3");press(down);assert(input().empty());
    assert(console::ObjectFenceIntact(console::Storage()) && calls==1);
}
'''


class ConsoleCommandHistoryTests(unittest.TestCase):
    def test_actual_panel_command_recall_and_draft_restore(self):
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
