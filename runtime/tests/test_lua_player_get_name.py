"""角色名字必须来自引擎 Player 配置表，包含 SSO、长串与坏范围。"""
import subprocess
import tempfile
import unittest
from pathlib import Path
from .test_support import build_lua_harness
from .test_lua_batch312_coop_ghost import HARNESS, SOURCE

SETUP = r'''
    std::vector<unsigned char> manager(kManagerEntityConfigOffset + 0x30, 0);
    std::vector<unsigned char> entries(44 * kEntityConfigPlayerStride, 0);
    std::uintptr_t managerPointer = AddressOf(manager);
    WriteAt<std::uintptr_t>(g_ModuleBytes, kGameManagerGlobalSlotOffset,
                            reinterpret_cast<std::uintptr_t>(&managerPointer));
    const auto config = kManagerEntityConfigOffset;
    WriteAt<std::uintptr_t>(manager, config + kEntityConfigPlayerArrayBeginOffset, AddressOf(entries));
    WriteAt<std::uintptr_t>(manager, config + kEntityConfigPlayerArrayEndOffset, AddressOf(entries) + entries.size());
    const std::string longName = "A custom character with a long original name";
    int id = 0;
    const char* expected = "Isaac";
    if (std::strcmp(scenario, "long") == 0) { id = 43; expected = longName.c_str(); }
    if (std::strcmp(scenario, "empty") == 0) { id = 41; expected = ""; }
    const auto name = static_cast<std::size_t>(id) * kEntityConfigPlayerStride + kEntityConfigPlayerNameOffset;
    if (id == 43) {
        WriteAt<std::uint64_t>(entries, name, 1);
        WriteAt<std::uint64_t>(entries, name + 8, longName.size());
        WriteAt<std::uintptr_t>(entries, name + 16, reinterpret_cast<std::uintptr_t>(longName.c_str()));
    } else {
        entries[name] = std::strlen(expected) * 2;
        std::memcpy(entries.data() + name + 1, expected, std::strlen(expected));
    }
    WriteAt<std::int32_t>(g_PlayerBytes, kEntityPlayerTypeOffset, id);
    if (std::strcmp(scenario, "negative") == 0) WriteAt<std::int32_t>(g_PlayerBytes, kEntityPlayerTypeOffset, -1);
    if (std::strcmp(scenario, "pastend") == 0) WriteAt<std::int32_t>(g_PlayerBytes, kEntityPlayerTypeOffset, 44);
    if (std::strcmp(scenario, "reversed") == 0)
        WriteAt<std::uintptr_t>(manager, config + kEntityConfigPlayerArrayEndOffset, AddressOf(entries) - 1);
    if (std::strcmp(scenario, "partial") == 0)
        WriteAt<std::uintptr_t>(manager, config + kEntityConfigPlayerArrayEndOffset, AddressOf(entries) + entries.size() - 1);
    if (std::strcmp(scenario, "missing") == 0) managerPointer = 0;
'''

class PlayerGetNameTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="isaac-player-name-")
        text = HARNESS.replace("#include <vector>", "#include <vector>\n#include <string>")
        a = text.index("    // 四个场景：")
        b = text.index("    LuaRuntime::SetGameBindings", a)
        text = text[:a] + "    PublishFakeGame(0, 0);\n" + SETUP + text[b:]
        a = text.index("    const char* script =")
        b = text.index("LuaRuntime::InitializeFromBuffer", a)
        # 保留初始化以下原夹具收尾，仅替换 Lua 脚本。
        end = text.rfind("    ", a, b)
        text = text[:a] + "    const char* script = R\"lua(print('NAME=[' .. tostring(Isaac.GetPlayer(0):GetName()) .. ']'))lua\";\n" + text[end:]
        cls.binary = build_lua_harness(source_root=SOURCE, workdir=Path(cls.temp.name), harness_source=text)
    @classmethod
    def tearDownClass(cls): cls.temp.cleanup()
    def test_engine_names_and_invalid_vectors(self):
        for scenario, expected in [("short", "Isaac"), ("long", "A custom character with a long original name"),
                                   ("empty", ""), ("negative", "nil"), ("pastend", "nil"),
                                   ("reversed", "nil"), ("partial", "nil"), ("missing", "nil")]:
            with self.subTest(scenario=scenario):
                result = subprocess.run([str(self.binary), scenario], text=True, capture_output=True)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn("NAME=[" + expected + "]", result.stdout)

if __name__ == "__main__": unittest.main()
