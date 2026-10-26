"""容量扩展不能把数百KiB临时清单推到游戏线程栈上。"""
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class ModCapacityStackTests(unittest.TestCase):
    def test_loading_functions_keep_bounded_stack_frames(self):
        sources = [
            'runtime/source/mod_manifest.cpp',
            'runtime/src/infrastructure/mod/manifest_selector_adapter.cpp',
            'runtime/src/application/mod/manifest_parser.cpp',
            'runtime/src/application/mod/manifest_service.cpp',
            'runtime/src/application/mod/mod_discovery_service.cpp',
            'runtime/src/application/mod/mod_toggle_service.cpp',
            'runtime/src/domain/mod/mod_toggle_state.cpp',
        ]
        checked = 0
        with tempfile.TemporaryDirectory() as tmp:
            for index, source in enumerate(sources):
                output = Path(tmp) / f'source{index}.o'
                built = subprocess.run([
                    'c++', '-std=c++17', '-O2', '-fstack-usage',
                    '-Iruntime/src', '-Iruntime/source', '-c', source,
                    '-o', str(output),
                ], cwd=ROOT, text=True, capture_output=True)
                self.assertEqual(built.returncode, 0, built.stdout + built.stderr)
                usage = output.with_suffix('.su').read_text()
                for line in usage.splitlines():
                    fields = line.split('\t')
                    if len(fields) >= 3 and fields[-2].isdigit():
                        checked += 1
                        with self.subTest(source=source, function=fields[0]):
                            self.assertLessEqual(int(fields[-2]), 16384, line)
        self.assertGreater(checked, 25)


if __name__ == '__main__':
    unittest.main()
