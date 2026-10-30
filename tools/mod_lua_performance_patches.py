"""Apply reviewed Lua performance patches only to exact author file identities."""
from __future__ import annotations

import hashlib
from pathlib import Path

# relative path -> (patch path, accepted source hashes, reviewed patch hash).
# Line endings belong to the identity: patches are stored as portable LF text.
PATCHES = {
    Path('scripts/inputhelper.lua'): (
        'ModConfigMenu/scripts/inputhelper.lua',
        frozenset({'9ba9c7cdfdaee96d5d75ca3929c7fe88d42b5cb637c9972eb99658669ae52858'}),
        '22a3d7714601103d00ef5caf3afd3174cede5a26c67d699e3ea158407c907a90',
    ),
    Path('scripts/minimapapi/main.lua'): (
        'MinimapAPI/scripts/minimapapi/main.lua',
        frozenset({'edbb6e0e8195598b014ad1510d988785769a161da964dba10f3b9d1b5073da9d'}),
        'b8e93147eb7b275be1ad394e549afe8076bc8c8f0d610d39052bd116153f5c50',
    ),
    Path('features/eid_api.lua'): (
        'EID/features/eid_api.lua',
        frozenset({'93d7adb0738467992d42724df93434aa4531dff5d840dc5ddeea6e334532e346'}),
        '620ff83f69a941f0c436ae36e262f01dd85078cc8e05682b59f319aac10912ae',
    ),
}


def approved_patch(source: Path, relative: Path, patch_root: Path) -> Path:
    """Return a verified replacement; unknown versions and other files pass through."""
    spec = PATCHES.get(relative)
    if spec is None:
        return source
    patch_name, authors, expected = spec
    identity = hashlib.sha256(source.read_bytes()).hexdigest()
    if identity not in authors:
        return source
    patch = patch_root / patch_name
    if hashlib.sha256(patch.read_bytes()).hexdigest() != expected:
        raise ValueError(f'{patch_name} 性能补丁已变化，需要重新审查并更新打包身份')
    return patch
