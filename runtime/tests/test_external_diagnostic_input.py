"""External probe payloads must work without a bundled diagnostic directory."""
from pathlib import Path
import os
import subprocess
import tempfile
import unittest

RUNTIME = Path(__file__).resolve().parents[1]


class ExternalDiagnosticInputTests(unittest.TestCase):
    def test_make_copies_explicit_external_payload_from_path_with_spaces(self):
        with tempfile.TemporaryDirectory(prefix='remote-probe-input-') as temporary:
            root = Path(temporary)
            diagnostic = root / 'local inputs'
            payload = diagnostic / 'stage10/isaac_mod_probe.lua'
            payload.parent.mkdir(parents=True)
            payload.write_text('return "synthetic fixture"\n')
            devkit = root / 'devkit'
            rules = devkit / 'libnx/switch_rules'
            rules.parent.mkdir(parents=True)
            rules.write_text('%.npdm:\n\t@:\n%.nso:\n\t@:\n%.elf:\n\t@:\n')
            output = root / 'output'
            target = output / 'atmosphere/contents/010021C000B6A000/romfs/isaac_mod_probe.lua'
            result = subprocess.run(
                ['make', '--no-print-directory', str(target), 'DIAGNOSTIC_STAGE=10',
                 f'DIAGNOSTIC_ROOT={diagnostic}', f'OUT={output}'],
                cwd=RUNTIME, env=os.environ | {'DEVKITPRO': str(devkit)},
                text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(target.read_bytes(), payload.read_bytes())
