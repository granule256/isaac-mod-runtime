"""经公共执行入口验证命令原文、调用期生命周期与既有拒绝条件。"""

import subprocess
import tempfile
import unittest
from pathlib import Path

try:
    from .test_console_bridge import ROOT, SOURCE, host_compilers
except ImportError:
    from test_console_bridge import ROOT, SOURCE, host_compilers


HARNESS = r'''
#include "infrastructure/console/console_bridge.hpp"
#include <cstdio>
#include <cstring>
#include <limits>
#include <string>
#include <vector>

namespace console = isaac::runtime::console;
namespace memory = isaac::runtime::engine_memory;
int failures = 0;
unsigned calls = 0;
const char* expected = nullptr;
std::size_t expectedLength = 0;
std::uintptr_t moduleBase = 0;
console::EngineEntries entries{};
bool recurse = false;
bool breakFence = false;

void check(bool condition, const char* name) {
    if (!condition) { ++failures; std::printf("CONSOLE_FAIL %s\n", name); }
}
void MockCtor(void*) {}
void MockInit(void*) {}
void MockConsoleRunCommand(void* object, const void* command, void* output, void* player) {
    ++calls;
    // 原生RunCommand会设置重定向，并在返回前清零；Lua命令内再调ExecuteCommand亦如此。
    std::uintptr_t redirect=memory::AddressOf(output);
    std::memcpy(static_cast<unsigned char*>(object)+0x150,&redirect,sizeof(redirect));
    const auto* header = static_cast<const unsigned char*>(command);
    const char* data = console::EngineStringData(header);
    check(console::EngineStringSize(header) == expectedLength, "engine-receives-full-size");
    check(std::memcmp(data, expected, expectedLength) == 0, "engine-receives-original-bytes");
    check(data[expectedLength] == '\0', "input-terminator-is-accessible");
    check(player == nullptr, "existing-player-argument-preserved");
    if (expectedLength > console::kCommandInlineCapacity) {
        check(console::EngineStringIsLong(header), "long-layout");
        check(data == expected, "long-input-is-borrowed");
    } else {
        check(!console::EngineStringIsLong(header), "short-layout");
        check(data == static_cast<const char*>(command) + 1, "short-input-is-inline");
    }
    // 同步递归时外层串头与数据必须仍然有效，不能被共享缓冲覆盖。
    if (recurse) {
        recurse = false;
        const char* outer = expected;
        const std::size_t outerLength = expectedLength;
        unsigned char saved[console::kEngineStringBytes];
        std::memcpy(saved, header, sizeof(saved));
        std::string nested(1024, 'n');
        expected = nested.c_str(); expectedLength = nested.size();
        const auto result = console::ExecuteCommand(entries, moduleBase, expected, expectedLength);
        check(result.status == console::ExecStatus::kOk, "recursive-command-runs");
        check(std::memcmp(saved, header, sizeof(saved)) == 0, "outer-header-survives-recursion");
        check(std::memcmp(console::EngineStringData(header), outer, outerLength) == 0,
              "outer-text-survives-recursion");
        std::uintptr_t restored{};
        std::memcpy(&restored,static_cast<unsigned char*>(object)+0x150,sizeof(restored));
        check(restored==redirect,"nested-command-restores-output-redirection");
        expected = outer; expectedLength = outerLength;
    }
    std::memset(static_cast<unsigned char*>(object)+0x150,0,sizeof(redirect));
    auto* result = static_cast<unsigned char*>(output);
    std::memset(result, 0, console::kEngineStringBytes);
    result[0] = 4; result[1] = 'o'; result[2] = 'k';
    if (breakFence) {
        auto* bytes = static_cast<unsigned char*>(object);
        bytes[kConsoleObjectSize - 1] = 0;
    }
}

void writePointer(std::vector<unsigned char>& bytes, std::size_t offset, std::uintptr_t value) {
    std::memcpy(bytes.data() + offset, &value, sizeof(value));
}

int main(int argc, char** argv) {
    if (argc != 2) return 2;
    std::vector<unsigned char> module(kGameOwnerGlobalSlotOffset + 16);
    std::vector<unsigned char> game(kGamePlayerArrayEndOffset + 16);
    alignas(8) std::uintptr_t player = 0x1000;
    alignas(8) std::uintptr_t gamePointer = memory::AddressOf(game.data());
    writePointer(module, kGameOwnerGlobalSlotOffset, memory::AddressOf(&gamePointer));
    writePointer(game, kGamePlayerArrayBeginOffset, memory::AddressOf(&player));
    writePointer(game, kGamePlayerArrayEndOffset, memory::AddressOf(&player) + sizeof(player));
    moduleBase = memory::AddressOf(module.data());
    entries.consoleCtor = MockCtor; entries.consoleInit = MockInit;
    entries.runCommand = MockConsoleRunCommand;
    std::string scenario(argv[1]);
    if (scenario == "guards") {
        std::string input(65536, 'g');
        expected = input.c_str(); expectedLength = input.size();
        auto execute = [&]() { return console::ExecuteCommand(entries, moduleBase, expected, expectedLength); };
        check(console::ExecuteCommand(entries, moduleBase, nullptr, 10).status == console::ExecStatus::kEmptyCommand,
              "null-input-rejected");
        check(console::ExecuteCommand(entries, moduleBase, "", 0).status == console::ExecStatus::kEmptyCommand,
              "empty-input-rejected");
        console::Storage().switchEnabled = false;
        check(execute().status == console::ExecStatus::kDisabledBySwitch, "disabled-long-command-rejected");
        check(calls == 0 && console::State().switchRefusals == 1, "disabled-does-not-call-engine");
        console::Storage().switchEnabled = true;
        entries.runCommand = nullptr;
        check(execute().status == console::ExecStatus::kEntriesMissing, "missing-run-entry-rejected");
        entries.runCommand = MockConsoleRunCommand;
        player = 0;
        check(execute().status == console::ExecStatus::kNoPlayer, "null-player-rejected");
        player = 0x1000;
        writePointer(game, kGamePlayerArrayEndOffset, memory::AddressOf(&player));
        check(execute().status == console::ExecStatus::kNoPlayer, "empty-player-list-rejected");
        writePointer(game, kGamePlayerArrayEndOffset, memory::AddressOf(&player) + sizeof(player));
        console::State().outputBytes = console::kOutputByteLimit;
        check(execute().status == console::ExecStatus::kOutputFenced, "full-output-rejected");
        console::State().outputBytes = 0;
        console::State().fenceBroken = 1;
        check(execute().status == console::ExecStatus::kFenceBroken, "broken-object-rejected");
        console::State().fenceBroken = 0;
        check(calls == 0, "guards-never-call-engine");
        expectedLength = std::numeric_limits<std::size_t>::max();
        check(execute().status == console::ExecStatus::kTooLong, "length-plus-nul-overflow-rejected");
        check(calls == 0, "overflow-does-not-read-input");
        expectedLength = input.size(); breakFence = true;
        const auto result = execute();
        check(result.status == console::ExecStatus::kOk && calls == 1, "healthy-long-command-executes");
        check(console::State().fenceBroken == 1, "post-call-fence-damage-recorded");
        check(execute().status == console::ExecStatus::kFenceBroken && calls == 1,
              "post-call-fence-damage-blocks-next-call");
    } else {
        const std::size_t length = scenario == "recursive" ? 22 : std::stoull(scenario);
        std::string input(length, 'a');
        for (std::size_t i = 0; i < length; ++i) input[i] = static_cast<char>('a' + i % 23);
        // 原文中的 NUL 必须随显式长度穿过入口，不能由 strlen 截断。
        if (length > 10) input[7] = '\0';
        const std::string original = input;
        expected = input.c_str(); expectedLength = input.size(); recurse = scenario == "recursive";
        const auto result = console::ExecuteCommand(entries, moduleBase, expected, expectedLength);
        check(result.status == console::ExecStatus::kOk, "command-executes");
        check(calls == (scenario == "recursive" ? 2U : 1U), "engine-called-exactly-once-per-command");
        check(input == original, "caller-text-unchanged");
        check(console::State().lastCommandLength == length, "full-length-published");
        check(console::State().commandsRun == calls, "successful-calls-published");
        const char* output = nullptr; std::uint32_t outputLength = 0;
        check(console::TakeLastOutput(&output, &outputLength) && outputLength == 2 &&
              std::memcmp(output, "ok", 2) == 0, "output-still-returned");
    }
    if (!failures) std::puts("CONSOLE_LONG_COMMAND_OK");
    return failures ? 1 : 0;
}
'''


class ConsoleLongCommandTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compilers = host_compilers()
        if compilers is None:
            raise RuntimeError("需要已有宿主 C/C++ 编译器")
        cls.temporary = tempfile.TemporaryDirectory(prefix="isaac-console-long-")
        temporary = Path(cls.temporary.name)
        compatibility = temporary / "compatibility"
        compatibility.mkdir()
        (compatibility / "stdfloat").write_text(
            "#pragma once\nnamespace std { using float16_t = float; using float128_t = long double; }\n"
        )
        harness = temporary / "console_long.cpp"
        harness.write_text(HARNESS)
        cls.binary = temporary / "console_long"
        result = subprocess.run([
            compilers[1], "-std=c++23", "-Wall", "-Wextra", "-Werror",
            "-I", str(compatibility), "-I", str(SOURCE), "-I", str(SOURCE.parent / "src"),
            str(harness), "-o", str(cls.binary),
        ], capture_output=True, text=True)
        if result.returncode:
            raise RuntimeError(f"宿主夹具编译失败：\n{result.stdout}\n{result.stderr}")

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def run_case(self, scenario):
        result = subprocess.run([str(self.binary), str(scenario)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("CONSOLE_LONG_COMMAND_OK", result.stdout)

    def test_short_and_long_boundaries(self):
        for length in (1, 21, 22, 23, 24, 126, 127):
            with self.subTest(length=length):
                self.run_case(length)

    def test_128_bytes_reach_engine(self):
        self.run_case(128)

    def test_1kib_reaches_engine(self):
        self.run_case(1024)

    def test_64kib_reaches_engine(self):
        self.run_case(65536)

    def test_recursive_execution_keeps_outer_command_alive(self):
        self.run_case("recursive")

    def test_guards_and_size_overflow_remain_enforced(self):
        self.run_case("guards")


if __name__ == "__main__":
    unittest.main()
