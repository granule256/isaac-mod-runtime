"""补丁只覆盖登记文件，完整原模组作为独立且不可变的安装底包。"""

import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile


TOOL = Path(__file__).resolve().parents[2] / "tools/build_mod_patch_packages.py"
PREFIX = "contents/010021C000B6A000/romfs/isaac_mods/mods/Test Mod/"


def digest(data):
    return hashlib.sha256(data).hexdigest()


class ModPatchPackagesTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(TOOL.is_file(), "standalone mod patch packager is missing")
        spec = importlib.util.spec_from_file_location("build_mod_patch_packages", TOOL)
        self.tool = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.tool)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "registry"
        (self.source / "sources").mkdir(parents=True)
        self.patched = b"return 'optimized'\n"
        (self.source / "sources/main.lua").write_bytes(self.patched)
        self.registry = {
            "schema": 1,
            "version": "v1.0-test",
            "packages": [{
                "id": "test_mod", "title": "测试模组", "directory": "Test Mod",
                "files": [{"path": "main.lua", "source": "sources/main.lua",
                           "original_sha256": digest(b"return 'original'\n"),
                           "patched_sha256": digest(self.patched)}],
            }],
        }
        self.registry_path = self.source / "patches.json"
        self.output = self.root / "output"

    def build(self, registry=None, **kwargs):
        self.registry_path.write_text(json.dumps(registry or self.registry), encoding="utf-8")
        return self.tool.build_packages(self.registry_path, self.output, **kwargs)

    def make_base(self):
        self.base = self.root / "base"
        mod = self.base / "Test Mod"
        (mod / "resources").mkdir(parents=True)
        (mod / "main.lua").write_bytes(b"return 'original'\n")
        (mod / "resources/image.bin").write_bytes(b"original resource\x00")
        (mod / ".DS_Store").write_bytes(b"metadata")
        (mod / "._image").write_bytes(b"metadata")
        for folder in (".git", "__pycache__"):
            (mod / folder).mkdir()
            (mod / folder / "junk").write_bytes(b"metadata")
        return mod

    def test_patch_archive_contains_only_registered_overlay_and_records_hashes(self):
        result = self.build()
        archive = self.output / "test_mod/test_mod-patch-v1.0-test.zip"
        with zipfile.ZipFile(archive) as zipped:
            self.assertEqual(zipped.namelist(), [PREFIX + "main.lua"])
            self.assertEqual(zipped.read(PREFIX + "main.lua"), self.patched)
            self.assertIsNone(zipped.testzip())
        self.assertEqual((self.output / "test_mod/extracted" / PREFIX / "main.lua").read_bytes(), self.patched)
        manifest = json.loads((self.output / "manifest.json").read_text())
        self.assertEqual(result, manifest)
        self.assertEqual(manifest["packages"][0]["files"][0]["patched_sha256"], digest(self.patched))
        sums = (self.output / "SHA256SUMS").read_text()
        self.assertIn(digest(archive.read_bytes()), sums)
        readme = (self.output / "test_mod/README.md").read_text()
        self.assertIn("先安装原模组", readme)
        self.assertIn("atmosphere", readme)
        self.assertIn(self.registry["packages"][0]["files"][0]["original_sha256"], readme)
        self.assertFalse((self.output / "original-mods").exists())

    def test_original_then_overlay_preserves_resources_and_all_sources(self):
        mod = self.make_base()
        before = {p.relative_to(self.root).as_posix(): p.read_bytes()
                  for p in self.root.rglob("*") if p.is_file()}
        self.build(base_root=self.base)
        destination = self.root / "installed"
        base_zip = self.output / "original-mods/test_mod-original.zip"
        with zipfile.ZipFile(base_zip) as zipped:
            self.assertEqual(set(zipped.namelist()), {PREFIX + "main.lua", PREFIX + "resources/image.bin"})
            self.assertIsNone(zipped.testzip())
            zipped.extractall(destination)
        with zipfile.ZipFile(self.output / "test_mod/test_mod-patch-v1.0-test.zip") as zipped:
            zipped.extractall(destination)
        self.assertEqual((destination / PREFIX / "main.lua").read_bytes(), self.patched)
        self.assertEqual((destination / PREFIX / "resources/image.bin").read_bytes(), b"original resource\x00")
        for name, payload in before.items():
            self.assertEqual((self.root / name).read_bytes(), payload)
        base_manifest = json.loads((self.output / "original-mods/test_mod-original-manifest.json").read_text())
        self.assertEqual(len(base_manifest["files"]), 2)
        self.assertIn(digest(base_zip.read_bytes()), (self.output / "SHA256SUMS").read_text())

    def test_invalid_original_refuses_before_output_creation(self):
        mod = self.make_base()
        (mod / "main.lua").write_bytes(b"unknown original")
        with self.assertRaises(ValueError):
            self.build(base_root=self.base)
        self.assertFalse(self.output.exists())

    def test_invalid_registry_refuses_before_output_creation(self):
        mutations = [
            ("version", "../v1"), ("version", "版本1"),
            ("id", "../mod"), ("directory", "../mod"),
            ("directory", "模组"), ("path", "../main.lua"),
            ("path", "/tmp/main.lua"), ("path", "a\\main.lua"),
            ("path", "中文.lua"), ("source", "../escape.lua"),
            ("source", "/tmp/main.lua"), ("source", "a/../sources/main.lua"),
            ("original_sha256", "bad"), ("patched_sha256", "0" * 64),
        ]
        for field, value in mutations:
            with self.subTest(field=field, value=value):
                registry = copy.deepcopy(self.registry)
                if field == "version":
                    registry[field] = value
                elif field in ("id", "directory"):
                    registry["packages"][0][field] = value
                else:
                    registry["packages"][0]["files"][0][field] = value
                with self.assertRaises(ValueError):
                    self.build(registry)
                self.assertFalse(self.output.exists())

    def test_duplicate_paths_or_package_directories_refused(self):
        registry = copy.deepcopy(self.registry)
        registry["packages"][0]["files"] *= 2
        with self.assertRaises(ValueError):
            self.build(registry)
        registry = copy.deepcopy(self.registry)
        duplicate = copy.deepcopy(registry["packages"][0])
        duplicate["id"] = "other_mod"
        registry["packages"].append(duplicate)
        with self.assertRaises(ValueError):
            self.build(registry)
        self.assertFalse(self.output.exists())

    def test_source_symlink_cannot_escape_registry(self):
        outside = self.root / "outside.lua"
        outside.write_bytes(self.patched)
        (self.source / "sources/main.lua").unlink()
        (self.source / "sources/main.lua").symlink_to(outside)
        with self.assertRaises(ValueError):
            self.build()
        self.assertFalse(self.output.exists())

    def test_original_symlink_and_non_ascii_filename_refused(self):
        mod = self.make_base()
        (mod / "resources/link").symlink_to(mod / "main.lua")
        with self.assertRaises(ValueError):
            self.build(base_root=self.base)
        (mod / "resources/link").unlink()
        (mod / "resources/中文.txt").write_bytes(b"data")
        with self.assertRaises(ValueError):
            self.build(base_root=self.base)
        self.assertFalse(self.output.exists())

    def test_existing_output_preserved(self):
        self.output.mkdir()
        sentinel = self.output / "sentinel"
        sentinel.write_text("preserve")
        with self.assertRaises(FileExistsError):
            self.build()
        self.assertEqual(sentinel.read_text(), "preserve")

    def test_output_cannot_be_created_inside_original_mod(self):
        mod = self.make_base()
        self.output = mod / "new-package"
        with self.assertRaises(ValueError):
            self.build(base_root=self.base)
        self.assertFalse(self.output.exists())

    def test_cli_builds_patch_packages(self):
        self.registry_path.write_text(json.dumps(self.registry), encoding="utf-8")
        completed = subprocess.run([sys.executable, str(TOOL), "--registry", str(self.registry_path),
                                    "--output", str(self.output)], capture_output=True, text=True)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertTrue((self.output / "manifest.json").is_file())


if __name__ == "__main__":
    unittest.main()
