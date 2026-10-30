"""Offline entry points must not need local device credentials or a running device."""
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]


class DeployReleaseEntryTests(unittest.TestCase):
    def test_help_works_without_resolving_a_device(self):
        result = subprocess.run([sys.executable, 'tools/deploy_release_package.py', '--help'],
                                cwd=ROOT, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('--package', result.stdout)

    def test_module_can_be_imported_without_local_configuration(self):
        result = subprocess.run([sys.executable, '-c',
                                 'import tools.deploy_release_package as d; assert callable(d.main)'],
                                cwd=ROOT, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
