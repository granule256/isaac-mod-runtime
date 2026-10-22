"""真实房间索引/描述符读取的有符号合同：特殊房间必须返回负数。"""
import subprocess
import tempfile
import unittest
from pathlib import Path
from .test_support import build_lua_harness
from .test_lua_room_descriptor import HARNESS, SOURCE


class SignedRoomIndexTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='isaac-signed-room-')
        setup = '''
    if (std::strncmp(scenario, "special:", 8) == 0) {
        const auto index = static_cast<std::int32_t>(std::strtol(scenario + 8, nullptr, 10));
        WriteAt<std::int32_t>(g_LevelBytes, kLevelCurrentRoomIndexOffset, index);
        WriteAt<std::int32_t>(g_LevelBytes, kArrayBase, index);
        WriteAt<std::int32_t>(g_LevelBytes, kArrayBase + 4, index);
    }
'''
        branch = '''
    if (std::strncmp(scenario, "special:", 8) == 0) {
        script = "local l=Game():GetLevel(); local d=l:GetRooms():Get(0);"
                 "print('SIGNED='..l:GetCurrentRoomIndex()..','..d.GridIndex..','..d.SafeGridIndex)";
    } else '''
        harness = '#include <cstdlib>\n' + HARNESS
        harness = harness.replace('    PublishFakeEngine();', '    PublishFakeEngine();\n' + setup, 1)
        anchor = '    if (std::strcmp(scenario, "top_level") == 0) {'
        assert harness.count(anchor) == 2
        harness = harness.replace(anchor, branch + anchor.lstrip(), 1)
        cls.binary = build_lua_harness(source_root=SOURCE, workdir=Path(cls.temp.name)/'harness', harness_source=harness)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_special_and_normal_indices_keep_their_sign(self):
        for index in [-1, -2, -3, -13, -18, 84]:
            with self.subTest(index=index):
                r = subprocess.run([str(self.binary), f'special:{index}'], capture_output=True, text=True)
                self.assertEqual(r.returncode, 0, r.stdout+r.stderr)
                self.assertIn(f'SIGNED={index},{index},{index}', r.stdout)
