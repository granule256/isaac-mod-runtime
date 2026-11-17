"""Pinned ConsoleMega autocomplete contracts, using the real panel on the host."""

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from .test_console_long_commands import HARNESS, SOURCE, host_compilers


PREAMBLE = HARNESS[:HARNESS.index("int main(")] + r'''
#include "infrastructure/console/console_panel.hpp"
#include <cassert>
#include <map>
using namespace isaac::runtime::console;
static std::map<void*,std::string> assigned;
static unsigned nativeFills{},callsToProvider{};
static bool inGame=true;
static bool registerDuringCallback;
static std::string callbackArguments;
static std::vector<std::pair<std::string,std::string>> rawEntries;
static void Show(void*) {}
static void Hide(void*) {}
static bool Update(void*) { return true; }
static void Render(void*) {}
static void Lines(void*) {}
static void* Assign(void* header,const char* text) {
    auto& copy=assigned[header];copy=text;
    assert(BuildBorrowedCommandString(copy.data(),copy.size(),
                                      static_cast<unsigned char*>(header)));
    return header;
}
static void Print(void*,const void*,std::uint32_t,std::uint32_t) {}
static void History(void*,const void*) {}
static void NativeFill(void*) { ++nativeFills; }
static bool Generate(const char*,std::size_t,const char* args,std::size_t length,
                     AutocompleteVisitor visitor,void* user) {
    ++callsToProvider;callbackArguments.assign(args,length);
    if (registerDuringCallback) {
        for (unsigned i=0;i<100;++i)
            RegisterConsoleCommand("extra"+std::to_string(i),"","",true,0);
    }
    for(const auto& [text,description]:rawEntries)
        if(!visitor(user,text.data(),text.size(),description.data(),description.size()))
            return false;
    return true;
}
static bool Catalog(ConsoleAutocompleteType,AutocompleteVisitor visitor,void* user) noexcept {
    return Generate(nullptr,0,"",0,visitor,user);
}
static PanelNativeEntries UI() {
    return {Show,Hide,Update,Render,Lines,Assign,Print,History,NativeFill,
            [](){return true;}};
}
static std::vector<std::string> Texts() {
    std::vector<std::string> result;
    if(Completions().entries)
        for(const auto& e:*Completions().entries)result.push_back(e.text);
    return result;
}
static void Setup() {
    ResetConsoleCommands();
    ReleasePanelCompletions();
    ResetPanelHistoryNavigation();
    SetConsoleAutofillLimit(10);
    ConsolePanelHostBindings bindings{};bindings.dispatchAutocomplete=Generate;
    SetConsolePanelHostBindings(bindings);
}
'''


class RepentogonCompletionTests(unittest.TestCase):
    def run_contract(self, body):
        with tempfile.TemporaryDirectory(prefix="console-repentogon-") as folder:
            work = Path(folder)
            (work / "stdfloat").write_text(
                "#pragma once\nnamespace std{using float16_t=float;using float128_t=long double;}\n"
            )
            (work / "test.cpp").write_text(PREAMBLE + body)
            result = subprocess.run(
                [host_compilers()[1], "-std=c++23", "-Wall", "-Wextra", "-Werror",
                 "-Wno-unused-variable", "-Wno-unused-function",
                 *(["-fsanitize=address,undefined", "-fno-omit-frame-pointer"]
                   if os.environ.get("CONSOLE_COMPLETION_SANITIZE") else []),
                 "-I", str(work), "-I", str(SOURCE),
                 "-I", str(SOURCE.parent / "src"), str(work / "test.cpp"),
                 "-o", str(work / "test")], capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            result = subprocess.run([str(work / "test")], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_sort_and_equivalence_precede_filter_and_limit(self):
        self.run_contract(r'''
int main() {
    Setup();RegisterConsoleCommand("probe","","",true,18);auto ui=UI();
    rawEntries={{"10","ten"},{"02","first two"},{"2","ignored duplicate"},
                {"1.10","ten sub"},{"1.2","two sub"},{"3","third"},{"1","one"},
                {"A","first letter"},{"a","ignored case duplicate"}};
    assert(RefreshPanelCompletions(ui,"probe "));
    assert((Texts()==std::vector<std::string>{
        "probe 1","probe 1.2","probe 1.10","probe 02","probe 3","probe 10","probe A"}));
    assert((*Completions().entries)[3].description=="first two");
    SetConsoleAutofillLimit(1);
    assert(RefreshPanelCompletions(ui,"probe "));
    assert((Texts()==std::vector<std::string>{"probe 1","probe 1.2"}));
    assert(RefreshPanelCompletions(ui,"probe ten"));
    assert((Texts()==std::vector<std::string>{"probe 1.10","probe 10"}));
    assert(nativeFills==0);
}
''')

    def test_parser_retains_literal_space_tokens_and_raw_prefix(self):
        self.run_contract(r'''
int main() {
    Setup();RegisterConsoleCommand("probe","","",true,18);auto ui=UI();
    rawEntries={{"alpha",""},{"beta","a  b"},{"value","a b"}};
    assert(RefreshPanelCompletions(ui,"probe a  b"));
    assert(callbackArguments=="a  b");
    assert((Texts()==std::vector<std::string>{"probe beta"}));
    assert(!RefreshPanelCompletions(ui,"probe a\tb"));
    assert(callbackArguments=="ab");
    assert(!RefreshPanelCompletions(ui,"probe\talpha"));
    assert(!RefreshPanelCompletions(ui," probe alpha"));
    assert(!RefreshPanelCompletions(ui,"PROBE alpha"));
    rawEntries={{"alpha","nothing"},{"beta",""}};
    assert(!RefreshPanelCompletions(ui,"probe  a"));
    assert(callbackArguments==" a");
    assert(Texts().empty()); // no normalized prefix or description match
}
''')

    def test_click_and_tab_keep_buffer_and_selected_row_visible(self):
        self.run_contract(r'''
int main() {
    Setup();RegisterConsoleCommand("probe","","",true,18);auto ui=UI();
    for(int i=1;i<=9;++i)rawEntries.emplace_back(std::to_string(i),"");
    assert(RefreshPanelCompletions(ui,"probe "));
    for(int i=0;i<8;++i)assert(CyclePanelCompletion(ui));
    assert(std::string(PanelInputText())=="probe 8");
    assert(Completions().selected==7 && Completions().windowStart==2);
    assert(assigned[Storage().consoleObject+0xc0].find("probe 8")!=std::string::npos);
    Completions().selected=2;
    assert(ApplySelectedPanelCompletion(ui));
    assert(std::string(PanelInputText())=="probe 3");
    assert(CompletionCount()==9 && Completions().selected==2);
    assert(CyclePanelCompletion(ui));
    assert(std::string(PanelInputText())=="probe 4");
}
''')

    def test_long_candidates_remain_and_tab_uses_pc_utf8_buffer_limit(self):
        self.run_contract(r'''
int main() {
    Setup();RegisterConsoleCommand("probe","","",true,18);auto ui=UI();
    rawEntries={{std::string(3000,'x'),"long"}};
    assert(RefreshPanelCompletions(ui,"probe "));
    assert(CompletionCount()==1 && Texts()[0].size()==3006);
    assert(CyclePanelCompletion(ui));
    assert(std::string(PanelInputText())==std::string("probe ")+std::string(1017,'x'));
    assert(Completions().selected==0 && CompletionCount()==1);
    rawEntries={{std::string(1016,'x')+"\xe4\xb8\xad","utf8"}};
    assert(RefreshPanelCompletions(ui,"probe "));
    assert(CyclePanelCompletion(ui));
    assert(std::string(PanelInputText()).size()==1022);
    rawEntries={{std::string(600,'z'),""}};
    assert(RefreshPanelCompletions(ui,"probe "));
    assert(CyclePanelCompletion(ui));
    assert(std::string(PanelInputText()).size()==606);
}
''')

    def test_enhanced_empty_and_no_match_do_not_use_native_packed_hints(self):
        self.run_contract(r'''
int main() {
    Setup();auto ui=UI();RegisterConsoleCommand("probe","","",true,18);
    assert(!RefreshPanelCompletions(ui,""));
    assert(!RefreshPanelCompletions(ui,"missing"));
    assert(!RefreshPanelCompletions(ui,"probe nope"));
    assert(nativeFills==0);
    ui.extensionEnabled=[](){return false;};
    assert(!RefreshPanelCompletions(ui,"probe "));
    assert(nativeFills==1 && CompletionCount()==0);
}
''')

    def test_commands_use_natural_equivalence_aliases_and_menu_visibility(self):
        self.run_contract(r'''
int main() {
    Setup();auto ui=UI();
    SetConsoleCompletionCatalogProvider(Catalog,[]() noexcept {return inGame;});
    RegisterConsoleCommand("zz10","ten","",true,18);
    RegisterConsoleCommand("zz2","two","",false,18);
    assert(RegisterConsoleCommand("ZZ02","duplicate","",true,18)==ConsoleCommandRegistration::Duplicate);
    SetConsoleAutofillLimit(1);
    inGame=true;
    assert(RefreshPanelCompletions(ui,"zz"));
    assert((Texts()==std::vector<std::string>{"zz2","zz10"}));
    inGame=false;
    assert(RefreshPanelCompletions(ui,"zz"));
    assert((Texts()==std::vector<std::string>{"zz10"}));
    assert(!RefreshPanelCompletions(ui,"ZZ"));
    rawEntries={{"c10","ten"},{"c2","two"}};
    assert(RefreshPanelCompletions(ui,"g "));
    assert((Texts()==std::vector<std::string>{"g c2","g c10"}));
    assert(FindConsoleCommand("g")->name=="giveitem");
    assert(RefreshPanelCompletions(ui,"giveitem "));
    assert(callsToProvider==1); // alias resolves the same cached command
}
''')

    def test_cached_builtin_entries_and_custom_regeneration(self):
        self.run_contract(r'''
int main() {
    Setup();auto ui=UI();
    SetConsoleCompletionCatalogProvider(Catalog,[]() noexcept {return inGame;});
    rawEntries={{"c1","The Sad Onion"},{"c2","The Inner Eye"}};
    assert(RefreshPanelCompletions(ui,"giveitem "));
    assert(callsToProvider==1);
    assert(RefreshPanelCompletions(ui,"giveitem ONION"));
    assert((Texts()==std::vector<std::string>{"giveitem c1"}));
    assert(callsToProvider==1);
    assert(!RefreshPanelCompletions(ui,"giveitem xyz"));
    assert(callsToProvider==1);
    assert(RefreshPanelCompletions(ui,"stage "));
    assert(callsToProvider==2);
    assert(RefreshPanelCompletions(ui,"giveitem "));
    assert(callsToProvider==3);
    RegisterConsoleCommand("probe","","",true,18);
    assert(RefreshPanelCompletions(ui,"probe "));
    assert(RefreshPanelCompletions(ui,"probe "));
    assert(callsToProvider==5);
    ResetConsoleCommands(); // invalidates cached pointers/metadata on VM reload
    assert(RefreshPanelCompletions(ui,"giveitem "));
    assert(callsToProvider==6);
}
''')

    def test_curse_initial_mask_preview_and_upstream_cached_filter_quirk(self):
        self.run_contract(r'''
int main() {
    Setup();auto ui=UI();
    SetConsoleCompletionCatalogProvider(Catalog,[]() noexcept {return inGame;});
    rawEntries={{"1","Darkness"},{"2","Labyrinth"},{"4","Lost"}};
    SetConsoleAutofillLimit(1);
    assert(RefreshPanelCompletions(ui,"curse "));
    assert(CompletionCount()==3); // initial CURSE path has no limit
    assert(RefreshPanelCompletions(ui,"curse "));
    assert(CompletionCount()==2); // same-command edits jump to generic filter
    RegisterConsoleCommand("unrelated","","",true,0);
    assert(RefreshPanelCompletions(ui,"curse "));
    assert(CompletionCount()==2); // std::set insertions keep prev_command valid
    assert(!RefreshPanelCompletions(ui,"curse 3"));
    RefreshPanelCompletions(ui,"stage "); // switch away so CURSE regenerates
    assert(RefreshPanelCompletions(ui,"curse 3junk"));
    assert(Texts()==std::vector<std::string>{"curse 3"});
    assert((*Completions().entries)[0].description=="Darkness + Labyrinth");
    assert(!RefreshPanelCompletions(ui,"curse 3junk"));
    RefreshPanelCompletions(ui,"stage ");
    assert(!RefreshPanelCompletions(ui,"curse 99999999999999999999"));
}
''')

    def test_empty_custom_entries_and_first_equivalent_description_survive(self):
        self.run_contract(r'''
int main() {
    Setup();RegisterConsoleCommand("probe","","",true,18);auto ui=UI();
    rawEntries={{"","empty"},{"A","first"},{"a","later"},{"01","zero"},{"1","one"}};
    assert(RefreshPanelCompletions(ui,"probe "));
    assert((Texts()==std::vector<std::string>{"probe ","probe 01","probe A"}));
    assert((*Completions().entries)[1].description=="zero");
    assert((*Completions().entries)[2].description=="first");
    assert(RefreshPanelCompletions(ui,"probe later")==false);
}
''')

    def test_item_name_submission_uses_first_candidate_like_fix_spawn_command(self):
        self.run_contract(r'''
int main() {
    Setup();auto ui=UI();
    SetConsoleCompletionCatalogProvider(Catalog,[]() noexcept {return inGame;});
    rawEntries={{"c10","Onion ten"},{"c2","Onion two"}};
    assert(RefreshPanelCompletions(ui,"giveitem onion"));
    assert(FixPanelCompletionCommand("giveitem onion  ")=="giveitem c2");
    assert(FixPanelCompletionCommand("giveitem c10  ")=="giveitem c10");
    assert(FixPanelCompletionCommand("giveitem c  ")=="giveitem c");
    assert(CyclePanelCompletion(ui));assert(CyclePanelCompletion(ui));
    assert(FixPanelCompletionCommand(PanelInputText())=="giveitem c10");
    assert(FixPanelCompletionCommand("debug 1  ")=="debug 1");
}
''')

    def test_callback_registration_does_not_invalidate_current_command(self):
        self.run_contract(r'''
int main() {
    Setup();auto ui=UI();
    RegisterConsoleCommand("probe","","",true,18);
    rawEntries={{"1","one"}};registerDuringCallback=true;
    assert(RefreshPanelCompletions(ui,"probe "));
    assert(Texts()==std::vector<std::string>{"probe 1"});
    assert(Completions().cache->command=="probe");
    assert(RefreshPanelCompletions(ui,"probe "));
    assert(callsToProvider==2);
}
''')

    def test_persisted_limit_is_signed_and_only_ui_clamps_it(self):
        self.run_contract(r'''
int main() {
    Setup();auto ui=UI();RegisterConsoleCommand("probe","","",true,18);
    rawEntries={{"1",""},{"2",""},{"3",""}};
    SetConsoleAutofillLimit(0);
    assert(RefreshPanelCompletions(ui,"probe "));
    assert(CompletionCount()==1);
    SetConsoleAutofillLimit(-1);
    assert(!RefreshPanelCompletions(ui,"probe "));
    assert(CompletionCount()==0);
    SetConsoleAutofillLimit(2000);
    assert(ConsoleAutofillLimit()==2000);
    assert(RefreshPanelCompletions(ui,"probe "));
    assert(CompletionCount()==3);
}
''')


if __name__ == "__main__":
    unittest.main()
