"""Minimal independently built ELF inputs, never game or release machine code."""
import importlib.util
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def elf_fixture(relocation=None):
    names = b'\0.text\0.notice_seal\0.symtab\0.strtab\0.shstrtab\0.rela.dyn\0.rodata\0'
    entries = [('__notice_code_start__', 0), ('__notice_code_end__', 16),
               ('__notice_ro_start__', 0x2000), ('__notice_ro_end__', 0x2010),
               ('g_NoticeCodeState', 0x3000)]
    strings = b'\0' + b''.join(name.encode() + b'\0' for name, _ in entries)
    symbols = bytes(24) + b''.join(struct.pack('<IBBHQQ', strings.index(name.encode()),
        0x10, 0, 1, value, 0) for name, value in entries)
    # Records: name, type, flags, address, contents, link, entry size.
    sections = [('', 0, 0, 0, b'', 0, 0),
                ('.text', 1, 6, 0, bytes(range(16)), 0, 0),
                ('.notice_seal', 1, 2, 0x1000, bytes(96), 0, 0),
                ('.symtab', 2, 0, 0, symbols, 4, 24),
                ('.strtab', 3, 0, 0, strings, 0, 0),
                ('.shstrtab', 3, 0, 0, names, 0, 0),
                ('.rodata', 1, 2, 0x2000, bytes(range(16, 32)), 0, 0)]
    if relocation is not None:
        sections.append(('.rela.dyn', 4, 2, 0x2000,
                         struct.pack('<QQq', relocation, 1027, 0), 0, 24))
    data = bytearray(64)
    headers = []
    for name, kind, flags, address, payload, link, entsize in sections:
        headers.append(struct.pack('<IIQQQQIIQQ', names.index(name.encode()+b'\0') if name else 0,
                                   kind, flags, address, len(data), len(payload), link, 0, 1, entsize))
        data.extend(payload)
    shoff = len(data)
    data.extend(b''.join(headers))
    struct.pack_into('<16sHHIQQQIHHHHHH', data, 0, b'\x7fELF\x02\x01\x01'+bytes(9),
                     3, 183, 1, 0, 0, shoff, 0, 64, 0, 0, 64, len(sections), 5)
    return bytes(data)


class NoticeCodeSealTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = ROOT / 'tools/seal_notice_code.py'
        spec = importlib.util.spec_from_file_location('seal_notice_code', path)
        cls.tool = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.tool)

    def test_seals_final_code_and_detects_mutation(self):
        raw = elf_fixture()
        sealed = self.tool.seal_elf(raw)
        self.assertEqual(self.tool.verify_elf(sealed)['code_bytes'], 16)
        self.assertEqual(sealed, self.tool.seal_elf(sealed))
        # Includes literal drawing constants as well as instructions and seal.
        shoff = struct.unpack_from('<Q', sealed, 40)[0]
        ro_offset = struct.unpack_from('<Q', sealed, shoff + 6 * 64 + 24)[0]
        for offset in list(range(64, 176)) + list(range(ro_offset, ro_offset + 16)):
            bad = bytearray(sealed)
            bad[offset] ^= 1
            with self.subTest(offset=offset), self.assertRaises(ValueError):
                self.tool.verify_elf(bytes(bad))

    def test_unsealed_and_invalid_inputs_fail_closed(self):
        for raw in (b'', b'\x7fELF', elf_fixture()):
            with self.subTest(size=len(raw)), self.assertRaises(ValueError):
                self.tool.verify_elf(raw)
        bad = bytearray(elf_fixture())
        bad[4] = 1
        with self.assertRaises(ValueError):
            self.tool.seal_elf(bytes(bad))

    def test_relocation_in_code_or_seal_is_rejected(self):
        for address in (0, 8, 15, 0x1000, 0x105f, 0x2000, 0x200f):
            with self.subTest(address=address), self.assertRaises(ValueError):
                self.tool.seal_elf(elf_fixture(address))
        self.tool.verify_elf(self.tool.seal_elf(elf_fixture(0x3000)))

    def test_missing_compatible_guard_and_writable_or_overlapping_seal_rejected(self):
        raw = elf_fixture()
        bad = raw.replace(b'g_NoticeCodeState', b'g_UnsupportedAbiX')
        with self.assertRaises(ValueError):
            self.tool.seal_elf(bad)
        shoff = struct.unpack_from('<Q', raw, 40)[0]
        for field, value in ((8, 3), (16, 0), (24, 64), (32, 0)):
            bad = bytearray(raw)
            struct.pack_into('<Q', bad, shoff + 2 * 64 + field, value)
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.tool.seal_elf(bytes(bad))

    def test_locale_policy_uses_pointer_free_read_only_records(self):
        from tools import build_title_notice as notice
        catalogs = {code: {'version': 'test'} for code in notice.LANGUAGES}
        results = {code: {'page_count': 4} for code in notice.LANGUAGES}
        with tempfile.TemporaryDirectory(prefix='notice-policy-records-') as tmp:
            root = Path(tmp)
            notice.write_localized_header(root / 'generated.hpp', catalogs, results)
            (root / 'test.cpp').write_text(r'''
#include "generated.hpp"
#include <type_traits>
#include <cstring>
#include <cassert>
using namespace isaac::runtime::notice;
static_assert(std::is_array_v<decltype(kLocaleAssetsStorage[0].assetPath)>);
static_assert(std::is_array_v<decltype(kLocaleAssetsStorage[0].language)>);
static_assert(sizeof(kLocaleAssetsStorage[0]) == 72);
int main() {
 for (unsigned i=0;i<8;++i) {
  assert(kLocaleAssetsStorage[i].pageCount==4);
  assert(std::strcmp(kLocaleAssetsStorage[i].assetPath,kLocaleAssets[i].assetPath)==0);
 }
}
''')
            built = subprocess.run(['c++', '-std=c++17', str(root / 'test.cpp'), '-o', str(root / 'test')],
                                   capture_output=True, text=True)
            self.assertEqual(built.returncode, 0, built.stderr)
            ran = subprocess.run([str(root / 'test')], capture_output=True, text=True)
            self.assertEqual(ran.returncode, 0, ran.stderr)
