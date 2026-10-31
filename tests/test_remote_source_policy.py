"""Exercise the publication checker against real temporary Git indexes."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

CHECKER = Path(__file__).resolve().parents[1] / 'tools/check_remote_source.py'


class SourceRepositoryFixture:
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.git('init', '-q')
        self.add('README.md', '# Example\n')
        self.add('LICENSE', 'Example license\n')
        self.add('.gitignore', 'dist/\n')

    def git(self, *args):
        return subprocess.check_output(['git', *args], cwd=self.root)

    def add(self, path, content='test\n'):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
        self.git('add', '-f', '--', path)

    def check(self, *args):
        self.assertTrue(CHECKER.is_file(), 'remote source checker is not implemented')
        return subprocess.run([sys.executable, str(CHECKER), '--root', str(self.root), *args],
                              text=True, capture_output=True)


class RemoteSourcePolicyTests(SourceRepositoryFixture, unittest.TestCase):
    def test_accepts_core_dependencies_and_contract_inputs(self):
        for path in ('runtime/source/lib/hook.cpp', 'runtime/src/runtime.hpp',
                     'runtime/source/rtld/LICENSE.txt',
                     'runtime/source/third_party/lua-5.3.3/SOURCE.md',
                     'tools/pc_enum_docs/RoomShape.md', 'tools/pc_contract_docs/Room.md',
                     'tools/build.py', 'tests/test_build.py',
                     'tools/title_notice_support/wechat.png', 'tools/title_notice_support/alipay.png',
                     'tools/title_notice_support/kofi.png'):
            self.add(path)
        self.assertEqual(self.check().returncode, 0)

    def test_rejects_payloads_redundant_docs_artifacts_and_unknown_paths(self):
        for path in ('runtime/diagnostic/stage10/main.lua', 'runtime/exlaunch/source/lib.hpp',
                     'runtime/README.md', 'tools/pc_enum_docs/readme.MD',
                     'runtime/tests/evidence/result.log', 'runtime/tests/.temp-build/main.cpp',
                     'runtime/build/main.cpp', 'tools/video_intro_20300101/build.py',
                     'runtime/source/notes.md', 'runtime/unreviewed/new.cpp',
                     'runtime/source/notice_guard/notice_guard_core.cpp',
                     'runtime/source/notice_integrity_native.cpp',
                     'runtime/source/title_notice_native.cpp',
                     'runtime/source/hook_manager.cpp',
                     'runtime/source/mod_menu_native.cpp',
                     'runtime/source/image_pcx_bridge_hook.cpp',
                     'runtime/source/mod_resource_redirect.cpp',
                     'runtime/source/mod_image_resources.cpp',
                     'runtime/source/anm2_load_override_hook.cpp',
                     'runtime/tests/test_notice_guard_module.py',
                     'tools/payload.zip', 'tools/dump.bin', 'AGENTS.md',
                     'tools/title_notice_support/unreviewed.png',
                     'outputs/report.csv', 'dist/result.json'):
            with self.subTest(path=path):
                self.add(path)
                result = self.check()
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertIn(path, result.stdout)
                self.git('rm', '--cached', '--', path)

    def test_force_added_ignored_files_are_rejected(self):
        self.add('.gitignore', 'tools/local.py\n')
        self.add('tools/local.py')
        result = self.check()
        self.assertEqual(result.returncode, 1)
        self.assertIn('tools/local.py', result.stdout)

    def test_rejects_private_address_copies_in_staged_comments_and_metadata(self):
        private = self.root / 'runtime/source/notice_guard/private_engine_addresses.hpp'
        private.parent.mkdir(parents=True)
        private.write_text('inline constexpr uintptr_t kHiddenEntryOffset = 0x789abcd;\n')
        self.add('tools/ledger.json', '{"evidence": "entry at 0x0789ABCD"}\n')
        result = self.check()
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn('tools/ledger.json', result.stdout)
        # The audit must use index bytes, even if the working copy was cleaned.
        (self.root / 'tools/ledger.json').write_text('{}\n')
        self.assertEqual(self.check().returncode, 1)
        self.add('tools/ledger.json', '{}\n')
        self.assertEqual(self.check().returncode, 0)
        self.add('tools/ledger.json', '{"entry": ' + str(0x789abcd) + '}\n')
        self.assertEqual(self.check().returncode, 1)

    def test_ref_checks_committed_tree_instead_of_current_index(self):
        self.git('-c', 'user.name=Test', '-c', 'user.email=test@example.invalid',
                 'commit', '-qm', 'clean source')
        self.add('runtime/README.md')
        self.assertEqual(self.check('--ref', 'HEAD').returncode, 0)
        self.assertEqual(self.check().returncode, 1)
        self.git('-c', 'user.name=Test', '-c', 'user.email=test@example.invalid',
                 'commit', '-qm', 'bad source')
        self.assertEqual(self.check('--ref', 'HEAD').returncode, 1)

    def test_missing_required_files_and_invalid_ref_fail_closed(self):
        self.git('rm', '--cached', '--', 'LICENSE')
        self.assertEqual(self.check().returncode, 1)
        self.assertNotEqual(self.check('--ref', 'does-not-exist').returncode, 0)


class PrePushSourcePolicyTests(SourceRepositoryFixture, unittest.TestCase):
    def hook(self, local_oid, remote='origin'):
        script = CHECKER.with_name('pre_push_source_check.sh')
        self.assertTrue(script.is_file(), 'pre-push source check is not implemented')
        self.add('tools/check_remote_source.py', CHECKER.read_text())
        return subprocess.run(['bash', str(script), remote], cwd=self.root,
                              input=f'refs/heads/main {local_oid} refs/heads/main {"0" * 40}\n',
                              text=True, capture_output=True)

    def commit(self, message):
        self.git('-c', 'user.name=Test', '-c', 'user.email=test@example.invalid',
                 'commit', '-qm', message)
        return self.git('rev-parse', 'HEAD').decode().strip()

    def test_hook_accepts_clean_commit_even_with_unrelated_staged_work(self):
        clean = self.commit('clean publication')
        self.add('AGENTS.md')
        self.assertEqual(self.hook(clean).returncode, 0)

    def test_hook_rejects_disallowed_files_in_intermediate_commit(self):
        self.commit('clean base')
        self.add('runtime/diagnostic/main.lua')
        self.commit('accidentally added probe')
        self.git('rm', '--cached', '--', 'runtime/diagnostic/main.lua')
        tip = self.commit('remove probe from tip')
        result = self.hook(tip)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn('runtime/diagnostic/main.lua', result.stdout)

    def test_hook_rejects_old_public_remote(self):
        tip = self.commit('clean publication')
        self.assertEqual(self.hook(tip, 'public').returncode, 1)
