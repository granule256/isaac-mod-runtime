"""Build and verify original-game patch bundles without an SDK or compatibility runtime."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Iterable

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from runtime.game_patches.catalog import GamePatch, selected_patches
from tools.nro_ips import encode_ips

MANIFEST = Path('game-patches.json')


def patch_path(patch: GamePatch) -> Path:
    return Path('atmosphere/nro_patches') / patch.directory / (patch.module_id.hex().upper() + '.ips')


def metadata(patch: GamePatch, blob: bytes) -> dict:
    return dict(id=patch.id, directory=patch.directory, module_id=patch.module_id.hex().upper(),
                bytes=len(blob), sha256=hashlib.sha256(blob).hexdigest())


def build_bundle(nro: bytes, output: Path, ids: Iterable[str] | None = None) -> dict:
    patches = selected_patches(ids)
    snapshots = {}
    entries = []
    # Verify every selected input before creating/replacing any output file.
    for patch in patches:
        blob = patch.build_patch(nro)
        if blob != encode_ips(list(patch.records)):
            raise ValueError(f'generator differs from registered records: {patch.id}')
        snapshots[patch_path(patch)] = blob
        entries.append(metadata(patch, blob))
    existing = {p.relative_to(output) for p in output.glob('atmosphere/nro_patches/**/*.ips')}
    if existing - snapshots.keys():
        raise ValueError('output contains other patches; choose a separate output directory')
    document = dict(schema_version=1, patches=entries)
    snapshots[MANIFEST] = (json.dumps(document, indent=2) + '\n').encode()
    for relative, blob in snapshots.items():
        path = output / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(blob)
    return document


def verified_bundle_files(source: Path) -> dict[Path, bytes]:
    """Return verified snapshots for a release composer; no NRO/SDK input is needed.

    Use trusted catalog paths and exact registered IPS records, not paths or
    digests supplied by the manifest. Read each file once so later copying uses
    the same verified bytes rather than reopening a changing input.
    """
    try:
        raw = (source / MANIFEST).read_bytes()
        document = json.loads(raw)
        if (not isinstance(document, dict) or set(document) != {'schema_version', 'patches'}
                or type(document['schema_version']) is not int or document['schema_version'] != 1
                or not isinstance(document['patches'], list)):
            raise ValueError('invalid original-game patch manifest')
        entries = document['patches']
        if any(not isinstance(entry, dict) for entry in entries):
            raise ValueError('invalid original-game patch entry')
        patches = selected_patches(entry.get('id') for entry in entries)
        snapshots = {MANIFEST: raw}
        for patch, entry in zip(patches, entries):
            relative = patch_path(patch)
            blob = (source / relative).read_bytes()
            expected = encode_ips(list(patch.records))
            if blob != expected or entry != metadata(patch, expected):
                raise ValueError(f'original-game patch contents/metadata mismatch: {patch.id}')
            snapshots[relative] = blob
        actual = {p.relative_to(source) for p in source.glob('atmosphere/nro_patches/**/*.ips')}
        if actual != {path for path in snapshots if path.suffix == '.ips'}:
            raise ValueError('bundle contains unregistered or undeclared IPS files')
        return snapshots
    except (OSError, TypeError, KeyError, ValueError) as error:
        raise ValueError(f'cannot verify original-game patch bundle: {error}') from error


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--nro', required=True, type=Path, help='Unmodified supported game NRO')
    parser.add_argument('--output', required=True, type=Path, help='Independent deployment tree')
    parser.add_argument('--patch', action='append', help='Registered patch ID; default: all')
    args = parser.parse_args()
    try:
        document = build_bundle(args.nro.read_bytes(), args.output, args.patch)
    except (OSError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 2
    print(json.dumps(document))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
