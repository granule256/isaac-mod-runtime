"""The remote source tree must exclude local mod payloads and media tooling."""
from pathlib import Path
import argparse
import hashlib
import importlib.util
import os
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
FORBIDDEN = (
    'runtime/mod-patches/', 'runtime/pc-mods/',
    'runtime/diagnostic/', 'runtime/exlaunch/', 'runtime/tests/evidence/',
    'runtime/tests/fixtures/mod_lua_performance/',
    'runtime/tests/fixtures/mod_mcm_logic/',
    'runtime/tests/fixtures/mod_reload_optimizations/',
    'runtime/tests/fixtures/mod_config_restore/',
    'runtime/tests/fixtures/stageapi_shared_init/',
    'runtime/tests/fixtures/minimapapi_frame_events/',
    'tools/video_intro_', 'tools/test_fixtures/eid-highlight/',
    'runtime/tests/fixtures/shared_item_images/',
)

class SourcePackagePurityTests(unittest.TestCase):
    def test_tracked_source_excludes_local_mod_and_media_payloads(self):
        result = subprocess.run(['git', 'ls-files', '-z'], cwd=ROOT, capture_output=True, check=True)
        tracked = [p.decode() for p in result.stdout.split(b'\0') if p]
        self.assertEqual([p for p in tracked if p.startswith(FORBIDDEN)], [])

    def test_default_runtime_build_does_not_bundle_example_mods(self):
        makefile = (ROOT / 'runtime/Makefile').read_text()
        self.assertIn('SKIP_DEFAULT_PC_MODS ?= 1', makefile)

    def test_ignored_local_paths_are_not_tracked(self):
        raw=subprocess.check_output(['git','ls-files','-ci','--exclude-standard'],cwd=ROOT)
        self.assertEqual(raw,b'')

    def test_tracked_source_has_no_packaged_images_or_build_outputs(self):
        raw=subprocess.check_output(['git','ls-files','-z'],cwd=ROOT)
        tracked=[p.decode()for p in raw.split(b'\0')if p]
        suffixes={'.png','.pcx','.fnt','.elf','.nro','.nsp','.zip','.mp4','.mov','.o'}
        self.assertEqual([p for p in tracked if Path(p).suffix.lower()in suffixes],[])

    def test_remote_tree_has_no_standalone_lua_mods(self):
        raw = subprocess.check_output(['git', 'ls-files', '-z', '*.lua'], cwd=ROOT)
        self.assertEqual(raw, b'')

    def test_only_root_readme_is_tracked(self):
        raw = subprocess.check_output(['git', 'ls-files', '-z'], cwd=ROOT)
        readmes = [p.decode() for p in raw.split(b'\0')
                   if p and Path(p.decode()).name.lower().startswith('readme')]
        self.assertEqual(readmes, ['README.md'])

    def test_missing_external_patch_data_does_not_remove_existing_output(self):
        spec = importlib.util.spec_from_file_location('purity_packager', ROOT / 'tools/build_deploy_package.py')
        tool = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(tool)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / 'existing'
            output.mkdir()
            sentinel = output / 'keep.txt'
            sentinel.write_text('keep existing package')
            args = argparse.Namespace(apply_mod_patches=True, game_patches=None,
                                      runtime=str(root/'runtime'), relay_patches=False,
                                      output=str(output), name='test')
            with patch.dict(os.environ, {'ISAAC_MOD_PATCH_ROOT':str(root/'missing')}):
                self.assertEqual(tool.build(args), 2)
            self.assertEqual(sentinel.read_text(), 'keep existing package')

    def test_library_copy_preserves_user_scripts_by_default(self):
        spec = importlib.util.spec_from_file_location('purity_copy', ROOT / 'tools/build_deploy_package.py')
        tool = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(tool)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source=root/'source';source.mkdir()
            content=b'-- user-owned source\r\nreturn true\r\n'
            (source/'main.lua').write_bytes(content)
            with patch.object(tool,'_approved_entry_patch',side_effect=AssertionError('patch path entered')):
                tool.copy_tree(source,root/'output')
            self.assertEqual((root/'output/main.lua').read_bytes(),content)

    def test_explicit_patch_data_can_live_outside_the_source_tree(self):
        from tools import mod_lua_performance_patches as module
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            source=root/'input.lua';source.write_bytes(b'return 1\n')
            external=root/'external';external.mkdir()
            patched=external/'replacement.lua';patched.write_bytes(b'return 2\n')
            spec=('replacement.lua',frozenset({hashlib.sha256(source.read_bytes()).hexdigest()}),
                  hashlib.sha256(patched.read_bytes()).hexdigest())
            with patch.dict(module.PATCHES,{Path('main.lua'):spec}):
                self.assertEqual(module.approved_patch(source,Path('main.lua'),external),patched)
                patched.write_bytes(b'changed')
                with self.assertRaises(ValueError):
                    module.approved_patch(source,Path('main.lua'),external)
