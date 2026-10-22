"""发布包需携带已验字体补丁；保留作者输入、其它资源和未审查的新版本。"""
from pathlib import Path
import tempfile
import unittest
from tools.build_deploy_package import copy_tree

ROOT = Path(__file__).resolve().parents[2]


class WmdPackagingTests(unittest.TestCase):
    def test_copy_tree_keeps_font_optimization_without_editing_author_input(self):
        original = (ROOT / "dist/dps-font-cache-20261017/author-main.lua").read_bytes()
        patched = (ROOT / "runtime/mod-patches/whatsmydps/main.lua").read_bytes()
        for content, expected in ((original, patched), (patched, patched),
                                  (original.replace(b'Whats My DPS?', b'Whats My DpS?', 1), original.replace(b'Whats My DPS?', b'Whats My DpS?', 1)),
                                  (original + b"\n-- different author version\n",
                                   original + b"\n-- different author version\n")):
            with tempfile.TemporaryDirectory(prefix="wmd-package-") as tmp:
                source, target = Path(tmp) / "author", Path(tmp) / "package"
                (source / "resources").mkdir(parents=True)
                (source / "main.lua").write_bytes(content)
                (source / "resources/keep.bin").write_bytes(b"original-resource")
                self.assertEqual(copy_tree(source, target), 2)
                self.assertEqual((target / "main.lua").read_bytes(), expected)
                self.assertEqual((source / "main.lua").read_bytes(), content)
                self.assertEqual((target / "resources/keep.bin").read_bytes(),
                                 b"original-resource")


if __name__ == "__main__":
    unittest.main()
