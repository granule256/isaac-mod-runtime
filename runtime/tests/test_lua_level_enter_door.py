"""换房时MusicModCallback必须能读到引擎的入门槽位，继续执行恢复音乐逻辑。"""
import subprocess
import tempfile
import unittest
from pathlib import Path

try:
    from .test_lua_level_batch8 import HARNESS
    from .test_support import build_lua_harness
except ImportError:
    from test_lua_level_batch8 import HARNESS
    from test_support import build_lua_harness

ROOT = Path(__file__).resolve().parents[2]


class LevelEnterDoorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="level-enter-door-")
        cls.addClassCleanup(cls.tmp.cleanup)
        # 沿用原生Game/Level两级指针夹具；额外覆盖进入门字段所在内存。
        harness = HARNESS
        harness = harness.replace("    const char* script = nullptr;", r'''
    const std::int32_t door = static_cast<std::int32_t>(std::strtol(scenario, nullptr, 10));
    WriteAt<std::int32_t>(g_GameBytes, 0x21570, door);
    const char* script = nullptr;''')
        begin = harness.index('    if (std::strcmp(scenario, "top_level") == 0) {')
        end = harness.index('    LuaRuntime::SetGameBindings(', begin)
        harness = harness[:begin] + r'''
    script = "local mod=RegisterMod('MusicDoorProbe',1);"
        "mod:AddCallback(ModCallbacks.MC_PRE_GET_COLLECTIBLE,function() "
        "local level=Game():GetLevel() "
        "local prevDoorChecked=false "
        "if level.EnterDoor >= 0 then prevDoorChecked=true end "
        "assert(math.type(level.EnterDoor)=='integer', 'EnterDoor must be native integer') "
        "print('RESTORE_MUSIC enter='..level.EnterDoor..' prev='..tostring(prevDoorChecked)) "
        "assert(type(level.GetCurrentRoomIndex)=='function', 'Level methods lost') "
        "end)";
''' + harness[end:]
        harness = harness.replace('#include <cstdint>', '#include <cstdint>\n#include <cstdlib>')
        harness = harness.replace('if (LuaRuntime::TakeCallbackError()) return 4;',
            'char error[256]{}; static_cast<void>(LuaRuntime::CopyLastLuaErrorText(error, sizeof(error))); '
            'std::puts(error); return LuaRuntime::TakeCallbackError() ? 4 : 0;')
        cls.binary = build_lua_harness(source_root=ROOT / "runtime/source",
            workdir=Path(cls.tmp.name), harness_source=harness)

    def test_native_enter_door_allows_music_restore_for_each_door_and_no_door(self):
        for door in range(-1, 8):
            with self.subTest(door=door):
                r = subprocess.run([str(self.binary), str(door)], text=True, capture_output=True)
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
                self.assertIn(f"RESTORE_MUSIC enter={door} prev={'true' if door >= 0 else 'false'}", r.stdout)


if __name__ == "__main__":
    unittest.main()
