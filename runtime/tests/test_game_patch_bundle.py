"""Original-game optimizations build independently and are verified before composition."""
import ast
import hashlib
import importlib
import json
import os
from pathlib import Path
import tempfile
import unittest

from tools.nro_ips import encode_ips

ROOT = Path(__file__).resolve().parents[2]
SOURCE_ROOT = Path(os.environ.get('ISAAC_SOURCE_ROOT', ROOT))


class GamePatchBundleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.nro = next(SOURCE_ROOT.glob('The Binding*Afterbirth*/*/1/.nro/Repentance.nro')).read_bytes()

    def module(self):
        self.assertIsNotNone(importlib.util.find_spec('runtime.game_patches'),
                             'independent original-game patch package is missing')
        return importlib.import_module('runtime.game_patches.build')

    def test_standalone_bundle_contains_the_already_verified_bytes_without_sdk(self):
        build = self.module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = build.build_bundle(self.nro, root)
            self.assertEqual([p['id'] for p in manifest['patches']], ['loop-time-carry'])
            blobs = build.verified_bundle_files(root)
            ips = [raw for path, raw in blobs.items() if path.suffix == '.ips']
            self.assertEqual(len(ips), 1)
            self.assertEqual(len(ips[0]), 17)
            self.assertEqual(hashlib.sha256(ips[0]).hexdigest(),
                             '5a9ea6865f08af590ef35a0e1a75dc867c00665aa2d8e4d081fdc84ff25ad79a')
            self.assertFalse((root / 'atmosphere/contents').exists(), 'SDK dependencies leaked in')
            self.assertTrue(all(path.suffix in ('.ips', '.json') for path in blobs))

    def test_wrong_bytes_are_rejected_even_with_a_recomputed_manifest_digest(self):
        build = self.module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            document = build.build_bundle(self.nro, root)
            path = next(root.rglob('*.ips'))
            wrong = encode_ips([(0x4C08F4, bytes(4))])
            path.write_bytes(wrong)
            document['patches'][0]['sha256'] = hashlib.sha256(wrong).hexdigest()
            document['patches'][0]['bytes'] = len(wrong)
            (root / 'game-patches.json').write_text(json.dumps(document))
            with self.assertRaises(ValueError):
                build.verified_bundle_files(root)

    def test_missing_patch_unregistered_id_and_manifest_paths_are_rejected(self):
        build = self.module()
        for field, value in [('id', 'unknown'), ('directory', '../outside'), ('module_id', 'bad')]:
            with self.subTest(field=field), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                document = build.build_bundle(self.nro, root)
                document['patches'][0][field] = value
                (root / 'game-patches.json').write_text(json.dumps(document))
                with self.assertRaises(ValueError):
                    build.verified_bundle_files(root)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            build.build_bundle(self.nro, root)
            next(root.rglob('*.ips')).unlink()
            with self.assertRaises(ValueError):
                build.verified_bundle_files(root)

    def test_selection_and_bad_source_fail_before_writing_output(self):
        build = self.module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'output'
            with self.assertRaises(ValueError):
                build.build_bundle(self.nro, root, ['unknown'])
            self.assertFalse(root.exists())
            wrong = bytearray(self.nro)
            wrong[0x4C08F4] ^= 1
            with self.assertRaises(ValueError):
                build.build_bundle(bytes(wrong), root)
            self.assertFalse(root.exists())

    def test_game_patches_and_compatibility_have_no_implementation_imports_between_them(self):
        self.module()
        forbidden = {'tools.build_patches', 'tools.cold_static_callbacks',
                     'tools.native_heap_budget_patch', 'tools.build_deploy_package'}
        for path in (ROOT / 'runtime/game_patches').glob('*.py'):
            for node in ast.walk(ast.parse(path.read_text())):
                if isinstance(node, ast.ImportFrom):
                    self.assertNotIn(node.module, forbidden, str(path))
                elif isinstance(node, ast.Import):
                    self.assertFalse({name.name for name in node.names} & forbidden, str(path))
        for node in ast.walk(ast.parse((ROOT / 'tools/build_patches.py').read_text())):
            if isinstance(node, ast.ImportFrom):
                self.assertFalse((node.module or '').startswith('runtime.game_patches'))
        self.assertFalse((ROOT / 'tools/game_loop_timing_patch.py').exists(),
                         'old implementation entry still owns the original-game patch')
