"""Console command registry, 1120 autocomplete transport, and panel consumption."""

import re
import subprocess
import tempfile
import unittest
from pathlib import Path

from . import test_support
from .test_console_long_commands import HARNESS as PANEL_HARNESS
from .test_console_long_commands import SOURCE as CONSOLE_SOURCE
from .test_console_long_commands import host_compilers
from .test_repentogon_in_game import PREFIX

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "runtime" / "source"


class ConsoleCommandRegistryTests(unittest.TestCase):
    def test_registry_help_and_duplicate_first_wins(self):
        code = r'''
#include "domain/console/console_commands.hpp"
#include <cassert>
#include <string>
using namespace isaac::runtime::console;
int main() {
    ResetConsoleCommands();
    assert(RegisterConsoleCommand("alpha", "first desc", "first help", true,
                                  static_cast<std::uint32_t>(ConsoleAutocompleteType::Custom)) ==
           ConsoleCommandRegistration::Added);
    assert(RegisterConsoleCommand("alpha", "replacement", "replacement", true,
                                  static_cast<std::uint32_t>(ConsoleAutocompleteType::None)) ==
           ConsoleCommandRegistration::Duplicate);
    assert(RegisterConsoleCommand("alphabet", "second desc", "second help", false,
                                  static_cast<std::uint32_t>(ConsoleAutocompleteType::None)) ==
           ConsoleCommandRegistration::Added);
    assert(ConsoleCommandCount() == 2);
    const auto* alpha = FindConsoleCommand("alpha");
    assert(alpha && alpha->description == "first desc" && alpha->helpText == "first help");
    assert(alpha->autocompleteType == ConsoleAutocompleteType::Custom);
    const auto all = BuildConsoleHelp("help", true);
    assert(all.find("  - alpha - first desc\n") != std::string::npos);
    assert(all.find("  - alphabet - second desc\n") != std::string::npos);
    assert(BuildConsoleHelp("help", false).find("alphabet") == std::string::npos);
    assert(BuildConsoleHelp("help alpha", true) == "alpha - first help\n");
    ResetConsoleCommands();
}
'''
        with tempfile.TemporaryDirectory(prefix="console-command-registry-") as folder:
            work = Path(folder)
            (work / "stdfloat").write_text(
                "#pragma once\nnamespace std{using float16_t=float;using float128_t=long double;}\n",
                encoding="utf-8",
            )
            (work / "test.cpp").write_text(code, encoding="utf-8")
            result = subprocess.run(
                [host_compilers()[1], "-std=c++23", "-Wall", "-Wextra", "-Werror",
                 "-I", str(work), "-I", str(SOURCE), "-I", str(ROOT / "runtime" / "src"),
                 str(work / "test.cpp"), "-o", str(work / "test")],
                capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            result = subprocess.run([str(work / "test")], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_lua_register_command_matches_upstream_argument_coercion(self):
        driver = PREFIX + r'''
#include "domain/console/console_commands.hpp"
#include "infrastructure/console/console_completion_catalog.hpp"
#include "interfaces/lua/repentogon_console_api.hpp"
#include <array>
#include <cstring>

static lua_State* consoleState;
static void Extensions(lua_State* state) noexcept {
    consoleState=state;
    RegisterRepentogonConsoleApi(state);
    lua_getglobal(state, "Console");
    lua_getfield(state, -1, "RegisterCommand");
    lua_setglobal(state, "_register");
    lua_getfield(state, -1, "RegisterMacro");
    lua_setglobal(state, "_macro");
    lua_pop(state, 1);
}

int main() {
    Files files(true);
    SetSessionSaveFilePort(&files);
    LuaRuntime::ObserveGameThread();
    const isaac::runtime::repentogon::NativePort port{Ready, Ready};
    isaac::runtime::repentogon::SetNativePort(&port);
    LuaRuntime::SetRuntimeExtensionInstaller(Extensions);
    const char* script = R"lua(
assert(AutocompleteType.CUSTOM == 18 and AutocompleteType.EFFECT == 19)
_register("alpha", "desc", "help", 1, AutocompleteType.CUSTOM)
_register("alpha", "ignored", "ignored", true, 0)
_register("alphabet", "second", "second help", nil, "0")
_macro("testmacro", {"g c1", 123})
_macro("testmacro", {"g c2"})
assert(not pcall(_macro, "bad", false))
)lua";
    assert(LuaRuntime::InitializeFromBuffer(script, std::strlen(script),
                                             "@console-register.lua") ==
           LuaRuntime::LuaInitResult::Success);
    using namespace isaac::runtime::console;
    assert(ConsoleCommandCount() ==
           std::size(kConsoleBuiltinCommandMetadata) + 2);
    const auto* alpha = FindConsoleCommand("alpha");
    assert(alpha && alpha->description == "desc" && alpha->showOnMenu &&
           alpha->autocompleteType == ConsoleAutocompleteType::Custom);
    const auto* alphabet = FindConsoleCommand("alphabet");
    assert(alphabet && !alphabet->showOnMenu &&
           alphabet->autocompleteType == ConsoleAutocompleteType::None);
    const auto& macros = ConsoleRegisteredMacros();
    assert(macros.size() == 2 && macros[0].name == "testmacro");
    assert(macros[0].commands[1] == "123");
    assert(macros[1].commands[0] == "g c2");
    RegisterRepentogonConsoleApi(consoleState);
    assert(FindConsoleCommand("alpha") &&
           ConsoleRegisteredMacros().size() == 2);
    assert(LuaRuntime::ShutdownForModReload());
    ResetConsoleCommands();
    LuaRuntime::SetRuntimeExtensionInstaller(nullptr);
    isaac::runtime::repentogon::SetNativePort(nullptr);
    SetSessionSaveFilePort(nullptr);
}
'''
        with tempfile.TemporaryDirectory(prefix="console-register-") as folder:
            binary = test_support.build_lua_harness(
                source_root=SOURCE, workdir=Path(folder), harness_source=driver)
            result = subprocess.run([str(binary)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


class ConsoleAutocompleteDispatchTests(unittest.TestCase):
    def test_1120_uses_string_filter_and_consumes_table_entries(self):
        driver = PREFIX + r'''
#include "interfaces/lua/console_autocomplete.hpp"
#include <cstring>
#include <string>
#include <vector>

struct Entry { std::string text, description; };
static std::vector<Entry> entries;

static bool Collect(void*, const char* text, std::size_t textLength,
                    const char* description, std::size_t descriptionLength) {
    entries.push_back({std::string(text, textLength),
                       std::string(description, descriptionLength)});
    return true;
}

int main() {
    Files files(true);
    SetSessionSaveFilePort(&files);
    LuaRuntime::ObserveGameThread();
    const isaac::runtime::repentogon::NativePort port{Ready, Ready};
    isaac::runtime::repentogon::SetNativePort(&port);
    const char* script = R"lua(
local m = RegisterMod("console-autocomplete", 1)
m:AddCallback(1120, function(_, command, params)
    assert(command == "custom")
    assert(params == "a b")
        local generated = {false, 987654321}
        generated[1] = nil
        setmetatable(generated, {
            __index = function(_, key)
                if key == 1 then
                    local value = string.rep("q", 4096)
                    collectgarbage("collect")
                    return value
                end
            end
        })
        return {"one", {"two", "second"}, generated, 123, "", true,
                "nul\0tail", {"desc", "de\0tail"}}
end, "custom")
m:AddCallback(1120, function()
    error("string filter did not skip this callback")
end, "other")
)lua";
    assert(LuaRuntime::InitializeFromBuffer(script, std::strlen(script),
                                             "@console-autocomplete.lua") ==
           LuaRuntime::LuaInitResult::Success);
    assert(LuaRuntime::DispatchConsoleAutocomplete("custom", 6, "a b", 3, &Collect, nullptr));
    assert(entries.size() == 8);
    assert(entries[0].text == "one" && entries[0].description.empty());
    assert(entries[1].text == "two" && entries[1].description == "second");
    assert(entries[2].text == std::string(4096, 'q'));
    assert(entries[2].description == "987654321");
    assert(entries[3].text == "123" && entries[3].description.empty());
    assert(entries[4].text.empty() && entries[5].text.empty());
    assert(entries[6].text == "nul");
    assert(entries[7].text == "desc" && entries[7].description == "de");
    entries.clear();
    assert(!LuaRuntime::DispatchConsoleAutocomplete("missing", 7, "", 0, &Collect, nullptr));
    assert(entries.empty());
    assert(LuaRuntime::ShutdownForModReload());
    LuaRuntime::SetRuntimeExtensionInstaller(nullptr);
    isaac::runtime::repentogon::SetNativePort(nullptr);
    SetSessionSaveFilePort(nullptr);
}
'''
        with tempfile.TemporaryDirectory(prefix="console-autocomplete-") as folder:
            binary = test_support.build_lua_harness(
                source_root=SOURCE, workdir=Path(folder), harness_source=driver)
            result = subprocess.run([str(binary)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


class ConsolePanelCommandIntegrationTests(unittest.TestCase):
    def test_custom_candidates_are_written_to_native_slots_and_selectable(self):
        code = r'''
#include "domain/console/console_commands.hpp"
#include "infrastructure/console/console_panel.hpp"
#include <cassert>
#include <cstring>
#include <memory>
#include <string>
using namespace isaac::runtime;
static std::string printed;
static std::string longCommand(80, 'c');
static void Show(void*) {}
static void Hide(void*) {}
static bool Update(void*) { return true; }
static void Render(void*) {}
static void Lines(void*) {}
static void* Assign(void* header, const char* text) {
    static std::vector<std::unique_ptr<std::string>> assigned;
    assigned.push_back(std::make_unique<std::string>(text));
    assert(console::BuildBorrowedCommandString(assigned.back()->c_str(),
        assigned.back()->size(),
        static_cast<unsigned char*>(header)));
    return header;
}
static void Print(void*, const void* header, std::uint32_t, std::uint32_t) {
    const auto* text=static_cast<const unsigned char*>(header);
    printed.append(console::EngineStringData(text),console::EngineStringSize(text));
}
static void History(void*, const void*) {}
static void Fill(void*) {
    for (std::uintptr_t offset : {0xc0U,0xd8U,0xf0U,0x108U,0x120U,0x138U})
        Assign(console::Storage().consoleObject + offset, "");
}
static bool Autocomplete(const char* command, std::size_t commandLength,
                         const char*, std::size_t,
                         console::AutocompleteVisitor visitor, void* user) {
    const std::string name(command,commandLength);
    if(name=="weaken") {
        for(int index=1;index<=8;++index) {
            const auto text="stage"+std::to_string(index);
            if(!visitor(user,text.data(),text.size(),"desc",4))return false;
        }
        return true;
    }
    if(name==longCommand) {
        const std::string text(240,'x');
        return visitor(user,text.data(),text.size(),nullptr,0);
    }
    return false;
}
int main() {
    using namespace console;
    auto* object=Storage().consoleObject;
    ResetConsoleCommands();
    assert(RegisterConsoleCommand("alpha", "first", "first help", true, 18) ==
           ConsoleCommandRegistration::Added);
    assert(RegisterConsoleCommand("alphabet", "second", "second help", true, 0) ==
           ConsoleCommandRegistration::Added);
    assert(RegisterConsoleCommand("weaken", "custom", "custom help", true, 18) ==
           ConsoleCommandRegistration::Added);
    assert(RegisterConsoleCommand(longCommand, "long", "long help", true, 18) ==
           ConsoleCommandRegistration::Added);
    PanelNativeEntries ui{Show,Hide,Update,Render,Lines,Assign,Print,History,Fill,
        [](){return true;}};
    ConsolePanelHostBindings bindings{};
    bindings.dispatchAutocomplete=&Autocomplete;
    SetConsolePanelHostBindings(bindings);
    assert(RefreshPanelCompletions(ui, "al"));
    assert(CompletionCount() == 2);
    assert((*Completions().entries)[0].text == "alpha");
    assert((*Completions().entries)[1].text == "alphabet");
    assert(CyclePanelCompletion(ui));
    assert(std::string(Panel().draftUtf8) == "alpha");
    assert(CyclePanelCompletion(ui));
    assert(std::string(Panel().draftUtf8) == "alphabet");
    assert(CyclePanelCompletion(ui));
    assert(std::string(Panel().draftUtf8) == "alpha");
    assert(CompletionCount() == 2);
    assert(RefreshPanelCompletions(ui, "al"));
    assert(MovePanelCompletionSelection(1));
    assert(Completions().selected == 0);
    assert(MovePanelCompletionSelection(1));
    assert(Completions().selected == 1);
    assert(ApplySelectedPanelCompletion(ui));
    assert(std::string(Panel().draftUtf8) == "alphabet");
    assert(EngineStringSize(object + 0x20) == 8);
    assert(std::string(EngineStringData(object + 0x20),
                       EngineStringSize(object + 0x20)) == "alphabet");
    assert(RefreshPanelCompletions(ui, "weaken "));
    assert(CompletionCount() == 8);
    for(int index=0;index<8;++index)
        assert((*Completions().entries)[index].text ==
               "weaken stage"+std::to_string(index+1));
    for(int index=0;index<8;++index) assert(MovePanelCompletionSelection(1));
    assert(Completions().selected == 7 && Completions().windowStart == 2);
    WritePanelCompletionSlots(ui);
    assert(std::string(EngineStringData(object+0x138),
                       EngineStringSize(object+0x138)) == "weaken stage3 (desc)");
    assert(std::string(EngineStringData(object+0xc0),
                       EngineStringSize(object+0xc0)) == "> weaken stage8 (desc)");
    assert(ApplySelectedPanelCompletion(ui));
    assert(std::string(Panel().draftUtf8) == "weaken stage8");
    assert(RefreshPanelCompletions(ui, (longCommand + " ").c_str()));
    assert(CompletionCount() == 1);
    assert((*Completions().entries)[0].text ==
           longCommand + " " + std::string(240,'x'));
    assert(AddPanelCompletion(
        std::string(kPanelCompletionTextCapacity,'y'),std::string_view{}));
    assert(Completions().rejected == 0 && CompletionCount() == 2);
    assert(ConsoleAutofillLimit() == 10);
    SetConsoleAutofillLimit(1);
    assert(RefreshPanelCompletions(ui, "al"));
    assert(CompletionCount() == 2);
    SetConsoleAutofillLimit(3);
    assert(ConsoleAutofillLimit() == 3);
    assert(RefreshPanelCompletions(ui, "weaken "));
    assert(CompletionCount() == 4);
    SetConsoleAutofillLimit(0);
    assert(ConsoleAutofillLimit() == 0);
    SetConsoleAutofillLimit(2000);
    assert(ConsoleAutofillLimit() == 2000);
    SetConsoleAutofillLimit(kConsoleAutofillLimitDefault);
    const std::string oversizeInput(kPanelUtf8Capacity,'i');
    assert(!RefreshPanelCompletions(ui, oversizeInput.c_str()));
    assert(CompletionCount() == 0);
    assert(!RefreshPanelCompletions(ui, "weaken z"));
    assert(CompletionCount() == 0);
    assert(RefreshPanelCompletions(ui, "weaken de"));
    assert(CompletionCount() == 8);
    assert(BuildConsoleHelp("help alpha", true) == "alpha - first help\n");
    printed.clear();
    assert(PrintCustomConsoleHelp(ui,"help alpha",10,true));
    assert(printed=="alpha - first help\n");
    SetConsolePanelHostBindings({});
    ResetConsoleCommands();
}
'''
        with tempfile.TemporaryDirectory(prefix="console-panel-commands-") as folder:
            work = Path(folder)
            (work / "stdfloat").write_text(
                "#pragma once\nnamespace std{using float16_t=float;using float128_t=long double;}\n",
                encoding="utf-8",
            )
            source = PANEL_HARNESS[:PANEL_HARNESS.index("int main(")] + code
            (work / "test.cpp").write_text(source, encoding="utf-8")
            result = subprocess.run(
                [host_compilers()[1], "-std=c++23", "-Wall", "-Wextra", "-Werror",
                 "-I", str(work), "-I", str(CONSOLE_SOURCE),
                 "-I", str(CONSOLE_SOURCE.parent / "src"), str(work / "test.cpp"),
                 "-o", str(work / "test")],
                capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            result = subprocess.run([str(work / "test")], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


class ConsolePanelFenceTests(unittest.TestCase):
    def test_broken_fence_never_calls_native_completion_assign(self):
        code = r'''
#include "infrastructure/console/console_panel.hpp"
#include <cassert>
#include <cstring>

static unsigned assignments;
static void Show(void*) {}
static void Hide(void*) {}
static bool Update(void*) { return true; }
static void Render(void*) {}
static void Lines(void*) {}
static void* Assign(void* header, const char*) {
    ++assignments;
    return header;
}
static void Print(void*, const void*, std::uint32_t, std::uint32_t) {}
static void History(void*, const void*) {}

int main() {
    using namespace isaac::runtime;
    using namespace isaac::runtime::console;
    PanelNativeEntries ui{Show,Hide,Update,Render,Lines,Assign,Print,History,nullptr};
    std::memset(Storage().consoleObject,0,sizeof(Storage().consoleObject));
    Storage().objectReady=true;
    State().fenceBroken=1;
    assignments=0;
    ClosePanelImmediately(ui);
    assert(assignments==0);
    assert(Completions().entries==nullptr);

    for(std::size_t i=kConsoleObjectSize-kObjectFenceBytes;
        i<kConsoleObjectSize;++i)
        Storage().consoleObject[i]=kObjectFenceValue;
    std::uint32_t panelState=2;
    std::memcpy(Storage().consoleObject,&panelState,sizeof(panelState));
    State().fenceBroken=0;
    assignments=0;
    ClosePanelImmediately(ui);
    assert(assignments==kPanelCompletionCount);
}
'''
        with tempfile.TemporaryDirectory(prefix="console-panel-fence-") as folder:
            work = Path(folder)
            (work / "stdfloat").write_text(
                "#pragma once\nnamespace std{using float16_t=float;using float128_t=long double;}\n",
                encoding="utf-8",
            )
            source = PANEL_HARNESS[:PANEL_HARNESS.index("int main(")] + code
            (work / "test.cpp").write_text(source, encoding="utf-8")
            result = subprocess.run(
                [host_compilers()[1], "-std=c++23", "-Wall", "-Wextra", "-Werror",
                 "-I", str(work), "-I", str(CONSOLE_SOURCE),
                 "-I", str(CONSOLE_SOURCE.parent / "src"), str(work / "test.cpp"),
                 "-o", str(work / "test")],
                capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            result = subprocess.run([str(work / "test")], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
