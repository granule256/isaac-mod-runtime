"""Split repositories must retain private-address checks and explicit device inputs."""
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


class SplitSourceInputTests(unittest.TestCase):
    def test_sibling_private_source_is_checked_after_git_store_moves(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'source/public'
            private = root.parent / 'private/runtime/source/notice_guard/private_engine_addresses.hpp'
            root.mkdir(parents=True)
            private.parent.mkdir(parents=True)
            private.write_text('constexpr uintptr_t kPrivate = 0x789abcd;\n')
            subprocess.run(['git', 'init', '-q', str(root)], check=True)
            for name in ('README.md', 'LICENSE', '.gitignore'):
                (root / name).write_text('test\n' if name != '.gitignore' else '')
            (root / 'tools').mkdir()
            (root / 'tools/ledger.json').write_text('{"address": "0x789abcd"}\n')
            subprocess.run(['git', '-C', str(root), 'add', '.'], check=True)
            result = subprocess.run([sys.executable, str(ROOT / 'tools/check_remote_source.py'),
                                     '--root', str(root)], text=True, capture_output=True)
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn('private engine address literal exposed', result.stdout)

    def test_missing_device_host_fails_instead_of_using_a_personal_address(self):
        from tools import device_access
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {}, clear=True), \
                patch.object(device_access, 'LOCAL_FILE', Path(tmp) / 'absent.json'):
            with self.assertRaises(SystemExit):
                device_access.resolve_device(user='example', password='example')

    def test_explicit_device_host_remains_supported(self):
        from tools import device_access
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {}, clear=True), \
                patch.object(device_access, 'LOCAL_FILE', Path(tmp) / 'absent.json'):
            self.assertEqual(device_access.resolve_device('192.0.2.10', user='u', password='p'),
                             ('192.0.2.10', 5000, 'u', 'p'))
