#!/usr/bin/env python3
"""生成独立模组覆盖补丁；可选将已核对的完整原模组另打底包，输入始终只读。"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import sys
import zipfile


MODS_PREFIX = PurePosixPath("contents/010021C000B6A000/romfs/isaac_mods/mods")
SAFE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*\Z")
SAFE_VERSION = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*\Z")
SHA256 = re.compile(r"[0-9a-fA-F]{64}\Z")
JUNK = {".DS_Store", ".git", "__pycache__"}


def _sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return _stream_sha256(stream)


def _stream_sha256(stream) -> str:
    digest = hashlib.sha256()
    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
        digest.update(chunk)
    return digest.hexdigest()


def _relative(value, label: str, *, ascii_only: bool = True) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        raise ValueError(f"{label}: expected a relative POSIX path")
    if any(part in ("", ".", "..") for part in value.split("/")):
        raise ValueError(f"{label}: absolute paths and traversal are forbidden: {value!r}")
    if any(ord(char) < 32 or char in ':*?"<>|' for char in value):
        raise ValueError(f"{label}: unsafe filename: {value!r}")
    if ascii_only and not value.isascii():
        raise ValueError(f"{label}: ZIP paths must be ASCII: {value!r}")
    if any(part.endswith((" ", ".")) for part in value.split("/")):
        raise ValueError(f"{label}: trailing spaces or dots are unsafe: {value!r}")
    return value


def _contained(root: Path, relative: str) -> Path:
    result = (root / relative).resolve()
    if not result.is_relative_to(root.resolve()):
        raise ValueError(f"source escapes its root: {relative!r}")
    return result


def _junk(name: str) -> bool:
    return name in JUNK or name.startswith("._")


def _original_files(mod: Path) -> list[dict]:
    if mod.is_symlink() or not mod.is_dir():
        raise ValueError(f"original mod must be a real directory: {mod}")
    records = []
    seen = set()
    for directory, folders, files in os.walk(mod, followlinks=False):
        folders[:] = sorted(name for name in folders if not _junk(name))
        for name in folders:
            if (Path(directory) / name).is_symlink():
                raise ValueError(f"original mod contains a symbolic link: {name}")
        for name in sorted(files):
            if _junk(name):
                continue
            path = Path(directory) / name
            relative = _relative(path.relative_to(mod).as_posix(), "original file")
            if path.is_symlink() or not path.is_file():
                raise ValueError(f"original mod contains a non-regular file: {relative}")
            if relative.casefold() in seen:
                raise ValueError(f"duplicate original path: {relative}")
            seen.add(relative.casefold())
            records.append({"path": relative, "sha256": _sha256(path), "size": path.stat().st_size})
    if not records:
        raise ValueError(f"original mod is empty: {mod}")
    return sorted(records, key=lambda record: record["path"])


def _prepare(registry_path: Path, base_root: Path | None) -> tuple[str, list[dict]]:
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    if not isinstance(registry, dict) or registry.get("schema") != 1:
        raise ValueError("unsupported patch registry schema")
    version = registry.get("version")
    if not isinstance(version, str) or not SAFE_VERSION.fullmatch(version):
        raise ValueError("version must be a safe ASCII filename component")
    packages = registry.get("packages")
    if not isinstance(packages, list) or not packages:
        raise ValueError("registry must contain at least one package")
    prepared = []
    ids, directories = set(), set()
    for package in packages:
        if not isinstance(package, dict):
            raise ValueError("package must be an object")
        identifier = package.get("id")
        if not isinstance(identifier, str) or not SAFE_ID.fullmatch(identifier):
            raise ValueError("package id must be a safe ASCII filename component")
        directory = _relative(package.get("directory"), "mod directory")
        if "/" in directory:
            raise ValueError("mod directory must be one folder name")
        if identifier.casefold() in ids or directory.casefold() in directories:
            raise ValueError(f"duplicate package id or directory: {identifier}")
        ids.add(identifier.casefold())
        directories.add(directory.casefold())
        title = package.get("title")
        if not isinstance(title, str) or not title.strip():
            raise ValueError(f"package {identifier} needs a title")
        files = package.get("files")
        if not isinstance(files, list) or not files:
            raise ValueError(f"package {identifier} needs overlay files")
        entries, payloads, seen = [], {}, set()
        for entry in files:
            if not isinstance(entry, dict):
                raise ValueError("file entry must be an object")
            target = _relative(entry.get("path"), "overlay path")
            source = _relative(entry.get("source"), "patch source", ascii_only=False)
            if target.casefold() in seen:
                raise ValueError(f"duplicate overlay path: {target}")
            seen.add(target.casefold())
            hashes = {}
            for key in ("original_sha256", "patched_sha256"):
                value = entry.get(key)
                if not isinstance(value, str) or not SHA256.fullmatch(value):
                    raise ValueError(f"invalid {key}: {target}")
                hashes[key] = value.lower()
            source_path = _contained(registry_path.parent, source)
            if not source_path.is_file():
                raise ValueError(f"patch source is not a file: {source}")
            payload = source_path.read_bytes()
            if hashlib.sha256(payload).hexdigest() != hashes["patched_sha256"]:
                raise ValueError(f"patched SHA256 mismatch: {source}")
            entries.append({"path": target, "source": source, **hashes})
            payloads[target] = payload
        record = {"id": identifier, "title": title, "directory": directory,
                  "files": entries, "payloads": payloads}
        if base_root is not None:
            mod = _contained(base_root, directory)
            if (base_root / directory).is_symlink():
                raise ValueError(f"original mod directory cannot be a symlink: {directory}")
            originals = _original_files(mod)
            original_hashes = {entry["path"]: entry["sha256"] for entry in originals}
            for entry in entries:
                if original_hashes.get(entry["path"]) != entry["original_sha256"]:
                    raise ValueError(f"unsupported original SHA256: {directory}/{entry['path']}")
            record.update(original_root=mod, originals=originals)
        prepared.append(record)
    return version, prepared


def _write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _verify_archive(path: Path, expected: dict[str, str]) -> None:
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if len(names) != len(expected) or set(names) != set(expected):
            raise ValueError(f"ZIP member check failed: {path}")
        for name, digest in expected.items():
            # ZipExtFile 在读至 EOF 时自动核 CRC；同一次读取同时核 SHA256。
            with archive.open(name) as stream:
                if _stream_sha256(stream) != digest:
                    raise ValueError(f"ZIP payload SHA256 mismatch: {path}: {name}")


def _package_readme(package: dict, version: str) -> str:
    lines = [f"# {package['title']}：独立覆盖补丁 {version}", "",
             "1. 先安装原模组：将完整原模组放到 SD 卡的 "
             f"`atmosphere/{MODS_PREFIX}/{package['directory']}/`。",
             "2. 再解压本补丁 ZIP，将其中的 `contents/` 合并复制到 SD 卡的 "
             "`atmosphere/`，同名文件选择覆盖。",
             "3. 补丁直接覆盖原模组的同名目录；不要再新建一层模组文件夹。", "",
             "补丁只包含下列修改文件，不包含原模组的完整脚本和资源。"
             "仅适用于下列原文件 SHA256；其他作者版本请勿覆盖。", ""]
    if "original_zip" in package:
        lines.extend([f"本次附带已核对的完整原模组：`../{package['original_zip']}`。"
                      "先将该 ZIP 的 `contents/` 合并到 SD 卡 `atmosphere/`，再覆盖补丁。", ""])
    for entry in package["files"]:
        lines.extend([f"- 文件：`{entry['path']}`",
                      f"  - 支持的原文件 SHA256：`{entry['original_sha256']}`",
                      f"  - 补丁文件 SHA256：`{entry['patched_sha256']}`"])
    return "\n".join(lines) + "\n"


def build_packages(registry_path: Path, output: Path, *, base_root: Path | None = None) -> dict:
    """先完整校验再输出；返回与输出 manifest.json 相同的包清单。"""
    registry_path, output = Path(registry_path), Path(output)
    if output.exists() or output.is_symlink():
        raise FileExistsError(f"output already exists: {output}")
    base_root = Path(base_root) if base_root is not None else None
    version, prepared = _prepare(registry_path, base_root)
    for item in prepared:
        if "original_root" in item and output.resolve().is_relative_to(item["original_root"]):
            raise ValueError("output cannot be inside an original mod directory")
    manifest = {"schema": 1, "version": version, "packages": []}
    archives = []
    output.mkdir(parents=True)
    try:
        for item in prepared:
            identifier = item["id"]
            package_dir = output / identifier
            extracted = package_dir / "extracted"
            extracted.mkdir(parents=True)
            package = {key: item[key] for key in ("id", "title", "directory", "files")}
            prefix = MODS_PREFIX / item["directory"]
            patch_relative = f"{identifier}/{identifier}-patch-{version}.zip"
            patch_zip = output / patch_relative
            expected = {}
            with zipfile.ZipFile(patch_zip, "w", zipfile.ZIP_DEFLATED) as archive:
                for entry in item["files"]:
                    name = str(prefix / entry["path"])
                    target = extracted / name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(item["payloads"][entry["path"]])
                    archive.write(target, name)
                    expected[name] = entry["patched_sha256"]
            _verify_archive(patch_zip, expected)
            package["patch_zip"] = patch_relative
            archives.append(patch_relative)
            if "originals" in item:
                original_dir = output / "original-mods"
                original_dir.mkdir(exist_ok=True)
                original_relative = f"original-mods/{identifier}-original.zip"
                original_zip = output / original_relative
                expected = {}
                with zipfile.ZipFile(original_zip, "w", zipfile.ZIP_DEFLATED) as archive:
                    for entry in item["originals"]:
                        name = str(prefix / entry["path"])
                        archive.write(item["original_root"] / entry["path"], name)
                        expected[name] = entry["sha256"]
                _verify_archive(original_zip, expected)
                base_manifest_relative = f"original-mods/{identifier}-original-manifest.json"
                _write_json(output / base_manifest_relative,
                            {"schema": 1, "id": identifier, "directory": item["directory"],
                             "files": item["originals"]})
                package.update(original_zip=original_relative, original_manifest=base_manifest_relative)
                archives.append(original_relative)
            _write_json(package_dir / "manifest.json", {"schema": 1, "version": version, **package})
            (package_dir / "README.md").write_text(_package_readme(package, version), encoding="utf-8")
            manifest["packages"].append(package)
        _write_json(output / "manifest.json", manifest)
        (output / "SHA256SUMS").write_text("".join(
            f"{_sha256(output / name)}  {name}\n" for name in sorted(archives)), encoding="ascii")
        lines = [f"# 模组独立覆盖补丁 {version}", "",
                 "先安装原模组，再覆盖对应补丁。每个补丁只带登记的修改文件。",
                 "ZIP 中的 `contents/` 应合并复制到 SD 卡的 `atmosphere/`；"
                 "不要另建一层模组目录。详细步骤和支持的原文件哈希见各包 README.md。", ""]
        lines.extend(f"- {package['title']}：`{package['patch_zip']}`" for package in manifest["packages"])
        if base_root is not None:
            lines.extend(["", "`original-mods/` 内是独立的完整原模组 ZIP 和逐文件 SHA256 清单；"
                          "原文件未改动，已排除系统元数据。原模组 ZIP 安装后仍需覆盖补丁 ZIP。"])
        else:
            lines.extend(["", "本次未附带完整原模组，请自行准备与各包登记哈希一致的原版。"])
        (output / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    except Exception:
        shutil.rmtree(output)
        raise
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--base-root", type=Path, help="完整原模组的父目录；按登记哈希校验")
    args = parser.parse_args()
    try:
        manifest = build_packages(args.registry, args.output, base_root=args.base_root)
    except (OSError, ValueError, zipfile.BadZipFile) as error:
        print(f"打包失败：{error}", file=sys.stderr)
        return 1
    print(f"已生成 {len(manifest['packages'])} 个独立补丁：{args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
