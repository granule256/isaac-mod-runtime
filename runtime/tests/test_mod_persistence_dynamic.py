"""真实ModPersistence宿主行为：大数据、独立文件、断写恢复、旧容器迁移及去重。"""
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

class DynamicPersistenceTests(unittest.TestCase):
    def test_behavior(self):
        with tempfile.TemporaryDirectory() as directory:
            binary = Path(directory) / 'persistence'
            built = subprocess.run(['c++', '-std=c++23', '-Wall', '-Wextra', '-Werror',
                '-I', str(ROOT/'runtime/src'), '-I', str(ROOT/'runtime/source'),
                str(ROOT/'runtime/tests/mod_persistence_dynamic_harness.cpp'),
                '-o', str(binary)], text=True, capture_output=True)
            self.assertEqual(built.returncode, 0, built.stdout+built.stderr)
            fixture = ROOT/'runtime/tests/fixtures/specialist-save-25183.json'
            result = subprocess.run([str(binary), str(fixture)], text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
            print(result.stdout.strip())

if __name__ == '__main__': unittest.main()
