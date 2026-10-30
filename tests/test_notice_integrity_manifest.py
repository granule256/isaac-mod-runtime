"""Small integrity/cache tests; rendering is replaced with fixture bytes."""
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools import build_title_notice as b

class NoticeManifestTests(unittest.TestCase):
    def test_prepared_root_pins_all_thirty_files_and_install_rejects_changes(self):
        catalogs = b.load_catalogs(ROOT / 'tools/title_notice_content.json')
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cache, header, out = root / 'cache', root / 'generated.hpp', root / 'out'
            with patch.object(b, 'render_asset', side_effect=lambda *args: ({'page_count': 3}, b'fixture pcx', b'fixture anm2')):
                result = b.build_localized_assets(cache, header, catalogs, None, paper_art=object())
            manifest = cache / b.RESOURCE_ROOT / 'resources/gfx/ui/main menu/isaac-switch/nnotice.manifest'
            raw = manifest.read_bytes()
            self.assertEqual(len(raw.splitlines()), 32)
            self.assertEqual(raw.splitlines()[:2], [b'ISAAC-NOTICE/1', b'v1.0.0-beta.4'])
            paths = [line.split(b'\t')[2] for line in raw.splitlines()[2:]]
            self.assertEqual(paths, sorted(set(paths)))
            self.assertEqual(len(paths), 30)
            self.assertIn('kIntegrityEntryCount = 30', header.read_text())
            self.assertEqual(result['manifest_sha256'], hashlib.sha256(raw).hexdigest())
            b.install_cached_assets(cache, out, header)
            self.assertEqual((out / manifest.relative_to(cache)).read_bytes(), raw)
            resource = next(cache.rglob('*.pcx'))
            original = resource.read_bytes()
            resource.write_bytes(b'X' + original[1:])
            with self.assertRaisesRegex(ValueError, 'resource'):
                b.install_cached_assets(cache, root / 'bad', header)
            self.assertFalse((root / 'bad').exists())
            resource.write_bytes(original)
            manifest.write_bytes(b'X' + raw[1:])
            with self.assertRaisesRegex(ValueError, 'manifest'):
                b.install_cached_assets(cache, root / 'bad', header)
            manifest.write_bytes(raw)
            resource.unlink()
            with self.assertRaises((ValueError, OSError)):
                b.install_cached_assets(cache, root / 'bad', header)
            metadata = root / 'metadata.hpp'
            metadata.write_text('// metadata only')
            with self.assertRaisesRegex(ValueError, 'root'):
                b.install_cached_assets(cache, out, metadata)

if __name__ == '__main__': unittest.main()
