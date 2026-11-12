"""Console extension methods validate arguments and expose native history."""

import subprocess
import tempfile
import unittest
from pathlib import Path

from . import test_support
from .test_repentogon_in_game import PREFIX

SOURCE = Path(__file__).resolve().parents[1] / "source"
DRIVER = PREFIX + r'''
#include "infrastructure/console/console_panel.hpp"

#include <cassert>
#include <cstdio>
#include <cstring>
#include <string>

static std::string errorText;
static std::string warningText;
static int errorCalls;
static int warningCalls;

static bool Error(const char* text, std::size_t length) {
    ++errorCalls;
    errorText.assign(text, length);
    return true;
}

static bool Warning(const char* text, std::size_t length) {
    ++warningCalls;
    warningText.assign(text, length);
    return true;
}

static bool History(isaac::runtime::console::ConsoleHistoryVisitor visitor,
                    void* user) {
    visitor(user, "first", 5);
    visitor(user, "second", 6);
    return true;
}

int main() {
    Files files(true);
    SetSessionSaveFilePort(&files);
    LuaRuntime::ObserveGameThread();
    const isaac::runtime::repentogon::NativePort port{Ready, Ready};
    isaac::runtime::repentogon::SetNativePort(&port);
    isaac::runtime::console::ConsolePanelHostBindings bindings{};
    bindings.printError = &Error;
    bindings.printWarning = &Warning;
    bindings.visitHistory = &History;
    isaac::runtime::console::SetConsolePanelHostBindings(bindings);

    const char* script = R"lua(
assert(type(Console) == 'table')
Console.PrintError('bad')
Console.PrintWarning('careful')
local history = Console.GetHistory()
assert(#history == 2 and history[1] == 'first' and history[2] == 'second')
assert(not pcall(function() Console.PrintError() end))
assert(not pcall(function() Console.PrintWarning() end))
assert(not pcall(function() Console.PrintError('x', 'y') end))
assert(not pcall(function() Console.GetHistory(1) end))
)lua";
    if (LuaRuntime::InitializeFromBuffer(script, std::strlen(script),
                                         "@console-api.lua") !=
        LuaRuntime::LuaInitResult::Success) {
        char error[2048]{};
        static_cast<void>(LuaRuntime::CopyLastLuaErrorText(error, sizeof(error)));
        std::fprintf(stderr, "%s\n", error);
        return 1;
    }
    assert(errorCalls == 1 && errorText == "bad");
    assert(warningCalls == 1 && warningText == "careful\n");
    assert(LuaRuntime::ShutdownForModReload());
    isaac::runtime::console::SetConsolePanelHostBindings({});
    isaac::runtime::repentogon::SetNativePort(nullptr);
    SetSessionSaveFilePort(nullptr);
}
'''


class RepentogonConsoleApiTests(unittest.TestCase):
    def test_print_and_history(self):
        with tempfile.TemporaryDirectory(prefix="repentogon-console-") as folder:
            binary = test_support.build_lua_harness(
                source_root=SOURCE, workdir=Path(folder), harness_source=DRIVER)
            result = subprocess.run([str(binary)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
