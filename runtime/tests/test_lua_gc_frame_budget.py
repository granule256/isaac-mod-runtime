"""Fast standalone regressions against the real vendored Lua collector."""
import pathlib
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


class GcFrameBudgetTest(unittest.TestCase):
    def test_real_lua_collector(self):
        lua = ROOT / 'source/third_party/lua-5.3.3/src'
        with tempfile.TemporaryDirectory() as tmp:
            exe = pathlib.Path(tmp) / 'gc-budget'
            sources = sorted(str(p) for p in lua.glob('*.c')
                             if p.name not in {'lua.c', 'luac.c'})
            subprocess.run(['cc', '-std=c99', '-O1', '-g', '-DLUA_C89_NUMBERS',
                            '-I' + str(lua), str(ROOT / 'tests/gc_frame_budget_harness.c'),
                            *sources, '-lm', '-o', str(exe)], check=True,
                           capture_output=True, text=True)
            for case in ['shared', 'continuation', 'explicit', 'stop', 'finalizers',
                         'gcerror', 'nested', 'pressure', 'oom', 'isolation', 'credit',
                         'saturation']:
                with self.subTest(case=case):
                    result = subprocess.run([str(exe), case], capture_output=True, text=True)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
