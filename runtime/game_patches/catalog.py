"""The single inventory of independent original-game patches and their outputs."""
from dataclasses import dataclass
from typing import Callable, Iterable

from . import loop_time_carry


@dataclass(frozen=True)
class GamePatch:
    id: str
    directory: str
    module_id: bytes
    build_patch: Callable[[bytes], bytes]
    records: tuple[tuple[int, bytes], ...]


PATCHES = (
    GamePatch('loop-time-carry', 'isaac-repentance-loop-time-carry',
              loop_time_carry.MODULE_ID, loop_time_carry.build_loop_time_carry_patch,
              (loop_time_carry.RECORD,)),
)


def selected_patches(ids: Iterable[str] | None = None) -> tuple[GamePatch, ...]:
    if ids is None:
        return PATCHES
    requested = tuple(ids)
    known = {patch.id: patch for patch in PATCHES}
    if not requested or any(not isinstance(key, str) or key not in known for key in requested):
        raise ValueError('unknown or empty original-game patch selection')
    if len(set(requested)) != len(requested):
        raise ValueError('duplicate original-game patch selection')
    return tuple(known[key] for key in requested)
