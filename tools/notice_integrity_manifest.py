"""Canonical notice manifest and pinned-cache validation (no rendering)."""
from __future__ import annotations
import hashlib
from pathlib import Path
import re

MANIFEST_PATH = 'rom:/rp_patch/resources/gfx/ui/main menu/isaac-switch/nnotice.manifest'
RESOURCE_ROOT = Path('atmosphere/contents/010021C000B6A000/romfs/rp_patch')
LANGUAGES = ('en', 'de', 'es', 'fr', 'jp', 'kr', 'ru', 'zh')


def expected_paths() -> list[str]:
    return sorted(f'rom:/rp_patch/{root}/gfx/ui/main menu/isaac-switch/nnotice_{code}.{ext}'
                  for code in LANGUAGES
                  for root in (['resources'] + ([f'resources.{code}'] if code != 'en' else []))
                  for ext in ('pcx', 'anm2'))


def local_path(tree: Path, physical: str) -> Path:
    return tree / RESOURCE_ROOT / physical.removeprefix('rom:/rp_patch/')


def write_manifest(tree: Path, files: list[str], version: str) -> tuple[bytes, str]:
    paths = sorted('rom:/rp_patch/' + Path(p).relative_to(tree / RESOURCE_ROOT).as_posix() for p in files)
    if paths != expected_paths():
        raise ValueError('notice manifest must cover exactly the 30 localized resources')
    if not re.fullmatch(r'[!-~]+', version):
        raise ValueError('notice version must be printable ASCII without whitespace')
    rows = ['ISAAC-NOTICE/1', version]
    for physical in paths:
        data = local_path(tree, physical).read_bytes()
        rows.append(f'{len(data)}\t{hashlib.sha256(data).hexdigest()}\t{physical}')
    raw = ('\n'.join(rows) + '\n').encode('ascii')
    path = local_path(tree, MANIFEST_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return raw, str(path)


def install_cached_assets(cache: Path, tree: Path, header: Path) -> dict:
    """Use the precompile header as authority; never bless a recomputed cache root.

    Validate every byte before creating the output. Copy verified byte snapshots,
    so a subsequent source change cannot turn a valid check into a different copy.
    """
    text = header.read_text(encoding='utf-8')
    match = re.search(r'kIntegrityManifestDigest\s*=\s*\{([^}]+)\}', text)
    count = re.search(r'kIntegrityEntryCount\s*=\s*(\d+)', text)
    version = re.search(r'kVersion\[\]\s*=\s*"([^"\n]+)"', text)
    if not match or not count or not version:
        raise ValueError('precompile header has no pinned integrity root')
    values = re.findall(r'0x([0-9a-f]{2})', match[1])
    if len(values) != 32 or int(count[1]) != 30:
        raise ValueError('invalid pinned integrity root/count')
    raw = local_path(cache, MANIFEST_PATH).read_bytes()
    if len(raw) > 16384 or hashlib.sha256(raw).digest() != bytes.fromhex(''.join(values)):
        raise ValueError('cached manifest differs from pinned precompile root')
    try:
        lines = raw.decode('ascii').split('\n')
        if lines[:2] != ['ISAAC-NOTICE/1', version[1]] or lines[-1] != '':
            raise ValueError('cached manifest format/version')
        entries = []
        for line in lines[2:-1]:
            size, digest, path = line.split('\t')
            if not re.fullmatch(r'0|[1-9][0-9]*', size) or not re.fullmatch('[0-9a-f]{64}', digest):
                raise ValueError('cached manifest entry format')
            entries.append((int(size), digest, path))
        if [p for _, _, p in entries] != expected_paths():
            raise ValueError('cached manifest path set')
    except (UnicodeError, ValueError) as exc:
        raise ValueError(f'invalid cached manifest: {exc}') from exc
    snapshots = []
    for size, digest, physical in entries:
        data = local_path(cache, physical).read_bytes()
        if len(data) != size or hashlib.sha256(data).hexdigest() != digest:
            raise ValueError(f'cached resource changed: {physical}')
        snapshots.append((physical, data))
    snapshots.append((MANIFEST_PATH, raw))
    for physical, data in snapshots:
        dest = local_path(tree, physical)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
    return {'installed_files': len(snapshots), 'manifest_sha256': hashlib.sha256(raw).hexdigest()}
