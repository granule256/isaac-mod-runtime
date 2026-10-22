"""设备越界读会返回垃圾，下载与哈希必须按 stat 的大小收口。"""
import base64
import hashlib
import importlib.util
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))

class NxcFileBoundsTests(unittest.TestCase):
    def check_tool(self, name, data, expected=None, corrupt=False, stat_error=False, remote='/file'):
        spec = importlib.util.spec_from_file_location(name, ROOT / 'tools' / (name + '.py'))
        mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
        calls = []
        def run(args, **kwargs):
            cmd = args[-1]; calls.append(cmd)
            from urllib.parse import unquote
            field = next(token[5:] for token in cmd.split() if token.startswith('path='))
            self.assertEqual(unquote(field), remote, '设备不识别引号，路径须按协议转义')
            self.assertEqual(kwargs['env']['NXC_DEVICE_IP'], '192.168.124.11')
            if cmd.startswith('fs.stat'):
                return SimpleNamespace(returncode=1 if stat_error else 0,
                    stdout=json.dumps([{'header': 'OK 1', 'payload': [{'size': str(len(data))}]}]), stderr='')
            offset = int(cmd.split('offset=')[1].split()[0])
            size = int(cmd.split('len=')[1].split()[0])
            self.assertLess(offset, len(data), '禁止发起 EOF 以外的读取')
            self.assertLessEqual(offset + size, len(data), '请求长度必须按文件剩余大小收口')
            block = data[offset:offset+size] + (b'garbage' if corrupt else b'')
            return SimpleNamespace(returncode=0, stdout=json.dumps([{'header': 'OK 2', 'payload':
                [{'bytes': str(len(block))}, base64.b64encode(block).decode()]}]), stderr='')
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / 'result'
            target.write_bytes(b'old-result')
            args = ['tool', remote, str(target)] if name == 'nxc_get_file' else ['tool', remote]
            if name == 'nxc_get_sha' and expected is not None: args.append(str(expected))
            with patch.object(sys, 'argv', args), patch.object(mod.subprocess, 'run', run), patch('sys.stdout', new_callable=io.StringIO) as out:
                status = mod.main(); output = out.getvalue()
            if corrupt or stat_error or (expected is not None and expected != len(data)):
                self.assertNotEqual(status, 0)
                if name == 'nxc_get_file': self.assertEqual(target.read_bytes(), b'old-result')
            else:
                self.assertEqual(status, 0, output)
                self.assertTrue(calls[0].startswith('fs.stat'))
                if name == 'nxc_get_file': self.assertEqual(target.read_bytes(), data)
                else: self.assertIn(hashlib.sha256(data).hexdigest(), output)
    def test_exact_chunks_empty_and_tail(self):
        for name in ('nxc_get_file', 'nxc_get_sha'):
            for size in (0, 2000, 4000, 4017):
                with self.subTest(tool=name, size=size): self.check_tool(name, b'a' * size)
    def test_oversized_payload_is_rejected(self):
        for name in ('nxc_get_file', 'nxc_get_sha'): self.check_tool(name, b'a', corrupt=True)
    def test_stat_failure_preserves_existing_result(self):
        for name in ('nxc_get_file', 'nxc_get_sha'): self.check_tool(name, b'a', stat_error=True)
    def test_expected_size_mismatch_is_rejected(self): self.check_tool('nxc_get_sha', b'a', expected=2)
    def test_paths_preserve_spaces_unicode_quotes_and_literal_percent(self):
        for name in ('nxc_get_file', 'nxc_get_sha'):
            for remote in ('/file', '/目录/visible tinted rocks/file', '/literal%20/name".lua'):
                with self.subTest(tool=name, remote=remote): self.check_tool(name, b'abc', remote=remote)

    def test_protocol_error_is_rejected_even_when_cli_exits_zero(self):
        import nxc_file_reader as reader
        for response in ({'header': 'ERR 404 missing', 'error': {'code': 404}},
                         {'header': 'OK 0', 'error': {'code': 404}},
                         {'header': 'unrecognized', 'payload': []}):
            with self.subTest(response=response):
                result = SimpleNamespace(returncode=0, stdout=json.dumps([response]), stderr='')
                with patch.object(reader.subprocess, 'run', return_value=result):
                    with self.assertRaises(ValueError): reader.call('fs.stat path=/missing')

if __name__ == '__main__': unittest.main()
