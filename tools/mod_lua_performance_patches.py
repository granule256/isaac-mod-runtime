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
        frozenset({'b8e93147eb7b275be1ad394e549afe8076bc8c8f0d610d39052bd116153f5c50', 'edbb6e0e8195598b014ad1510d988785769a161da964dba10f3b9d1b5073da9d'}),
        '545f5838049e579ea2d3b719f9d0daae20bc3cfcb5945932a904c27215c6c261',
    ),
    Path('features/eid_api.lua'): (
        'EID/features/eid_api.lua',
        frozenset({'93d7adb0738467992d42724df93434aa4531dff5d840dc5ddeea6e334532e346'}),
        'aa11c0c1fd5ab7406925d7976b7305a6908ea3921c2b3f3728dbadc59149ccb8',
    ),
    Path('features/eid_modifiers.lua'): (
        'EID/features/eid_modifiers.lua',
        frozenset({'80c50cf506ee2525e0a08a10173509f767627f142a53ace3abb9d3fd5a288881'}),
        'b95f0027472dfcf70468134d9d8bffae490bff9bd00872748cbdbb8939f3536c',
    ),
    Path('scripts/modconfig.lua'): (
        'ModConfigMenu/scripts/modconfig.lua',
        frozenset({'19a0366d7db6faae98a94dd46c5111f5ec4e5d4dc1bc456cb7fd3cacac3ffaf2', 'a561f8b4783bcdbdd8dd04d6d21a63677e668dcb6c2d7c9ffac53f3b10ed699e', 'b69879a456046a1c2ec787d19152f69a3999924b0c106afe77162a7e181fb098'}),
        'fe8752bfff7830a7f3d718e063009c8190725e223f00208468c67ab0242431eb',
    ),
    Path('main.lua'): (
        'EID/main.lua',
        frozenset({'b2e361e581fd1951d54ff7784efd8977c7ce7139df4e55052a77e9549914c383'}),
        '666fbb450898c8fd7b50bde77c8866ce4d78916796b07dcb3f3dce7d3fe23aa7',
    ),
    Path('features/eid_bagofcrafting_search.lua'): (
        'EID/features/eid_bagofcrafting_search.lua',
        frozenset({'4d135223865223e94f14916805023376cbb3bb50758fb5004a75a2685969d136'}),
        '0331ec4f9d47dbdf85b3e8f90d7f5bd24950fe60d8717cc7af903bbc6068a2f9',
    ),
    Path('features/eid_bagofcrafting.lua'): (
        'EID/features/eid_bagofcrafting.lua',
        frozenset({'b9e91099d7fb6cde17277dbf12a2b557b77d7be25fd5e0ea95339bd0aee4361c'}),
        'ac4de428d09a65b392f902be69dfc4507fddf3113ff2fb75f4b5adcb09df5197',
    ),
    Path('features/eid_mcm.lua'): (
        'EID/features/eid_mcm.lua',
        frozenset({'f227eb04ef56d07c7b92c56ecbd0d42c1626101909064d7b9629c9d6383e2832'}),
        '9d3566bb0b5074f8641eef85a96f2045807618d015d2e69aec1571e49bb93551',
    ),
    Path('scripts/stageapi/core/commands.lua'): (
        'StageAPI/scripts/stageapi/core/commands.lua',
        frozenset({'2fbdd617404af3c73c6a97faacd6423357743af3d829e48bd08126ec6b4ee80f'}),
        '77f4862f066328847f0bc077097340e4d3fab72e7c887e862c08bbed1fa888ec',
    ),
    Path('scripts/stageapi/basementRenovator.lua'): (
        'StageAPI/scripts/stageapi/basementRenovator.lua',
        frozenset({'918c889a7f3593fe30870e5461737fde454ac72adf08a6a6bf676031f7bee941'}),
        '4d6a074565e500394250b3a2eafab244617978b7e33064352001b9dcb80aa94a',
    ),
}


def approved_patch(source: Path, relative: Path, root: Path) -> Path:
    """Return a verified replacement; unknown versions and other files pass through."""
    spec = PATCHES.get(relative)
    if spec is None:
        return source
    patch_name, authors, expected = spec
    identity = hashlib.sha256(source.read_bytes()).hexdigest()
    if identity not in authors:
        return source
    patch = root / 'runtime/mod-patches' / patch_name
    if hashlib.sha256(patch.read_bytes()).hexdigest() != expected:
        raise ValueError(f'{patch_name} 性能补丁已变化，需要重新审查并更新打包身份')
    return patch
