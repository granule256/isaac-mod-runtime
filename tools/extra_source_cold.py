"""Cold indirect BLR gates for TakeDamage ExtraSource sites."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import struct
import sys

try:
    from . import build_patches
    from .nro_ips import encode_ips
except ImportError:
    import build_patches
    from nro_ips import encode_ips


BUILD_ID = bytes.fromhex("91C73FDD575061318D68886316AFEAC72388B2AB") + bytes(12)
TEXT_END = 0x68D000
RESERVED_RELAY_CAVE = (0x68CBE0, 0x68D000)
GATE_BYTES = 12
SLOT_BYTES = 8
FALLBACK_BYTES = 8


@dataclass(frozen=True)
class ColdSite:
    name: str
    source: int
    original: int
    target_register: int
    gate: int
    slot: int
    fallback: int
    function_offset: int = 0
    function_guard: bytes = b""


@dataclass(frozen=True)
class PaddingHole:
    offset: int
    size: int
    predecessor: str


LASER_SITE = ColdSite(
    name="Entity_Laser::do_damage ExtraSource",
    source=0xFF978,
    original=0xD63F0100,
    target_register=8,
    gate=0x0EA894,
    slot=0x13E5D8,
    fallback=0x12F544,
    function_offset=0xFF580,
    function_guard=bytes.fromhex("ff0302d1e923046dfd7b05a9fd430191"),
)

MELEE_PREFIX_GUARD = bytes.fromhex(
    "ef3bb66ded33016deb2b026de923036d"
    "fd7b04a9fd030191fc6f05a9fa6706a9"
    "f85f07a9f65708a9f44f09a9"
)
KNIFE_FUNCTION_GUARD = MELEE_PREFIX_GUARD + bytes.fromhex("ff8306d1")
GELLO_FUNCTION_GUARD = MELEE_PREFIX_GUARD + bytes.fromhex("ffc307d1")
EFFECT_FUNCTION_GUARD = MELEE_PREFIX_GUARD + bytes.fromhex("ffc311d1")
KNIFE_NORMAL_SITE = ColdSite(
    name="KnifeNormal",
    source=0xF0D84,
    original=0xD63F0100,
    target_register=8,
    gate=0x37014,
    slot=0x36F58,
    fallback=0x37054,
    function_offset=0xEF3A8,
    function_guard=KNIFE_FUNCTION_GUARD,
)
KNIFE_FIREPLACE_SITE = ColdSite(
    name="KnifeFireplace",
    source=0xF0FD4,
    original=0xD63F0100,
    target_register=8,
    gate=0x370C4,
    slot=0x373B8,
    fallback=0x371E4,
    function_offset=0xEF3A8,
    function_guard=KNIFE_FUNCTION_GUARD,
)
KNIFE_HIT_LIST_SITE = ColdSite(
    name="KnifeHitList",
    source=0xF10B0,
    original=0xD63F0100,
    target_register=8,
    gate=0x38254,
    slot=0x374D8,
    fallback=0x39814,
    function_offset=0xEF3A8,
    function_guard=KNIFE_FUNCTION_GUARD,
)
GELLO_NORMAL_SITE = ColdSite(
    name="GelloNormal",
    source=0xE1044,
    original=0xD63F0100,
    target_register=8,
    gate=0xD6D4,
    slot=0x39838,
    fallback=0x3AD44,
    function_offset=0xDE398,
    function_guard=GELLO_FUNCTION_GUARD,
)
GELLO_FIREPLACE_SITE = ColdSite(
    name="GelloFireplace",
    source=0xE1224,
    original=0xD63F0100,
    target_register=8,
    gate=0xE694,
    slot=0x35C58,
    fallback=0x35844,
    function_offset=0xDE398,
    function_guard=GELLO_FUNCTION_GUARD,
)
BRIMSTONE_BALL_SITE = ColdSite(
    name="BrimstoneBall",
    source=0x97B0C,
    original=0xD63F0100,
    target_register=8,
    gate=0x731B4,
    slot=0x35E08,
    fallback=0x679A4,
    function_offset=0x859A0,
    function_guard=EFFECT_FUNCTION_GUARD,
)

SITES = (
    LASER_SITE,
    KNIFE_NORMAL_SITE,
    KNIFE_FIREPLACE_SITE,
    KNIFE_HIT_LIST_SITE,
    GELLO_NORMAL_SITE,
    GELLO_FIREPLACE_SITE,
    BRIMSTONE_BALL_SITE,
)


def _bytes_word(word: int) -> bytes:
    return struct.pack("<I", word)


def _signed(value: int, bits: int) -> bool:
    return -(1 << (bits - 1)) <= value < (1 << (bits - 1))


def _aligned(value: int, alignment: int) -> bool:
    return value >= 0 and value % alignment == 0


def _enc_literal_ldr(rt: int, delta: int) -> int:
    return 0x58000000 | ((((delta >> 2) & 0x7FFFF) << 5)) | (rt & 0x1F)


def _enc_cbz(rt: int, delta: int) -> int:
    return 0xB4000000 | ((((delta >> 2) & 0x7FFFF) << 5)) | (rt & 0x1F)


def _enc_adr(rd: int, delta: int) -> int:
    immediate = delta & 0x1FFFFF
    return (
        0x10000000
        | ((immediate & 3) << 29)
        | (((immediate >> 2) & 0x7FFFF) << 5)
        | (rd & 0x1F)
    )


def _enc_br(rn: int) -> int:
    return 0xD61F0000 | ((rn & 0x1F) << 5)


def _ranges(site: ColdSite) -> tuple[tuple[int, int, str], ...]:
    return (
        (site.source, site.source + 4, "source"),
        (site.gate, site.gate + GATE_BYTES, "gate"),
        (site.slot, site.slot + SLOT_BYTES, "slot"),
        (site.fallback, site.fallback + FALLBACK_BYTES, "fallback"),
    )


def _validate_site(site: ColdSite) -> None:
    if not site.name or not _aligned(site.source, 4) or not _aligned(site.gate, 4):
        raise ValueError(f"{site.name}: source/gate alignment is invalid")
    if not _aligned(site.slot, 8) or not _aligned(site.fallback, 4):
        raise ValueError(f"{site.name}: slot/fallback alignment is invalid")
    if site.target_register < 0 or site.target_register > 30:
        raise ValueError(f"{site.name}: target register is invalid")
    if site.target_register in (16, 30):
        raise ValueError(f"{site.name}: gate uses x16 and ADR uses x30")
    expected_blr = 0xD63F0000 | (site.target_register << 5)
    if site.original != expected_blr:
        raise ValueError(f"{site.name}: original word is not blr x{site.target_register}")
    if not _signed(site.slot - site.gate, 21) or (site.slot - site.gate) % 4:
        raise ValueError(f"{site.name}: pointer slot is outside LDR literal range")
    if not _signed(site.fallback - (site.gate + 4), 21):
        raise ValueError(f"{site.name}: fallback is outside CBZ range")
    if not _signed(site.source + 4 - site.fallback, 21):
        raise ValueError(f"{site.name}: source resume is outside ADR range")
    build_patches.encode_branch(site.source, site.gate)
    intervals = sorted(_ranges(site))
    if any(begin < RESERVED_RELAY_CAVE[1] and RESERVED_RELAY_CAVE[0] < end
           for begin, end, _ in intervals):
        raise ValueError(f"{site.name}: overlaps the filled relay cave")
    for left, right in zip(intervals, intervals[1:]):
        if left[1] > right[0]:
            raise ValueError(f"{site.name}: source/hole ranges overlap")


def gate_image(site: ColdSite) -> bytes:
    _validate_site(site)
    return struct.pack(
        "<III",
        _enc_literal_ldr(16, site.slot - site.gate),
        _enc_cbz(16, site.fallback - (site.gate + 4)),
        _enc_br(16),
    )


def fallback_image(site: ColdSite) -> bytes:
    _validate_site(site)
    return struct.pack(
        "<II",
        _enc_adr(30, site.source + 4 - site.fallback),
        _enc_br(site.target_register),
    )


def predecessor_kind(nro: bytes, offset: int) -> str:
    if offset < 4:
        return "none"
    word = struct.unpack_from("<I", nro, offset - 4)[0]
    if word == 0xD65F03C0:
        return "ret"
    if word & 0xFC000000 == 0x14000000:
        return "b"
    return "other"


def scan_padding_holes(nro: bytes) -> list[PaddingHole]:
    if len(nro) < TEXT_END or nro[0x40:0x60] != BUILD_ID:
        raise ValueError("fixed Repentance NRO identity mismatch")
    holes: list[PaddingHole] = []
    offset = 0
    while offset < TEXT_END:
        if nro[offset] != 0:
            offset += 1
            continue
        end = offset
        while end < TEXT_END and nro[end] == 0:
            end += 1
        if end - offset >= 8 and offset % 4 == 0:
            holes.append(PaddingHole(offset, end - offset, predecessor_kind(nro, offset)))
        offset = end
    return holes


def discover_holes(nro: bytes, source: int) -> tuple[int, int, int]:
    holes = [
        hole
        for hole in scan_padding_holes(nro)
        if hole.predecessor in ("ret", "b")
        and not (0x68CBE0 <= hole.offset < 0x68D000)
    ]
    gate = min(
        (hole for hole in holes if hole.size >= GATE_BYTES),
        key=lambda hole: abs(hole.offset - source),
    )
    used = [(gate.offset, gate.offset + GATE_BYTES)]
    slot = min(
        (
            hole
            for hole in holes
            if hole.size >= SLOT_BYTES
            and hole.offset % 8 == 0
            and all(hole.offset >= end or hole.offset + SLOT_BYTES <= begin
                    for begin, end in used)
        ),
        key=lambda hole: abs(hole.offset - source),
    )
    used.append((slot.offset, slot.offset + SLOT_BYTES))
    fallback = min(
        (
            hole
            for hole in holes
            if hole.size >= FALLBACK_BYTES
            and all(hole.offset >= end or hole.offset + FALLBACK_BYTES <= begin
                    for begin, end in used)
        ),
        key=lambda hole: abs(hole.offset - source),
    )
    return gate.offset, slot.offset, fallback.offset


def verify_site(nro: bytes, site: ColdSite) -> None:
    _validate_site(site)
    if len(nro) < TEXT_END or nro[0x40:0x60] != BUILD_ID:
        raise ValueError(f"{site.name}: fixed NRO identity mismatch")
    if site.function_offset and site.function_guard:
        guard = nro[site.function_offset : site.function_offset + len(site.function_guard)]
        if guard != site.function_guard:
            raise ValueError(f"{site.name}: function guard mismatch")
    if struct.unpack_from("<I", nro, site.source)[0] != site.original:
        raise ValueError(f"{site.name}: original BLR mismatch")
    for address, length, label in (
        (site.gate, GATE_BYTES, "gate"),
        (site.slot, SLOT_BYTES, "slot"),
        (site.fallback, FALLBACK_BYTES, "fallback"),
    ):
        if nro[address : address + length] != bytes(length):
            raise ValueError(f"{site.name}: {label} cave is not empty")
        if predecessor_kind(nro, address) not in ("ret", "b"):
            raise ValueError(f"{site.name}: {label} is not RET/B-tail padding")


def scan_hole_xrefs(
    nro: bytes, sites: tuple[ColdSite, ...] = SITES
) -> list[tuple[int, int, int]]:
    """Find literal 32/64-bit references into cold gate/slot/fallback holes."""
    ranges: list[tuple[int, int, str]] = []
    for site in sites:
        ranges.extend(
            (
                (site.gate, site.gate + GATE_BYTES, site.name),
                (site.slot, site.slot + SLOT_BYTES, site.name),
                (site.fallback, site.fallback + FALLBACK_BYTES, site.name),
            )
        )
    wanted = {
        address
        for begin, end, _ in ranges
        for address in range(begin, end)
    }
    hits: list[tuple[int, int, int]] = []
    for offset in range(0, TEXT_END - 3, 4):
        word32 = struct.unpack_from("<I", nro, offset)[0]
        if word32 in wanted:
            hits.append((offset, 4, word32))
        if offset + 8 <= TEXT_END:
            word64 = struct.unpack_from("<Q", nro, offset)[0]
            if word64 in wanted:
                hits.append((offset, 8, word64))
    return hits


def cold_records(
    nro: bytes, sites: tuple[ColdSite, ...] = SITES
) -> list[tuple[int, bytes]]:
    records: list[tuple[int, bytes]] = []
    occupied: list[tuple[int, int]] = []
    for site in sites:
        verify_site(nro, site)
        site_records = (
            (site.source, build_patches.encode_branch(site.source, site.gate)),
            (site.gate, gate_image(site)),
            (site.fallback, fallback_image(site)),
        )
        for offset, payload in site_records:
            interval = (offset, offset + len(payload))
            if any(interval[0] < end and begin < interval[1]
                   for begin, end in occupied):
                raise ValueError(f"{site.name}: generated records overlap")
            occupied.append(interval)
            records.append((offset, payload))
        slot_interval = (site.slot, site.slot + SLOT_BYTES)
        if any(slot_interval[0] < end and begin < slot_interval[1]
               for begin, end in occupied):
            raise ValueError(f"{site.name}: pointer slot overlaps another site")
        occupied.append(slot_interval)
    return records


def build_cold_patch(
    nro: bytes, sites: tuple[ColdSite, ...] = SITES
) -> bytes:
    return encode_ips(cold_records(nro, sites))


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--nro", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    patch = build_cold_patch(args.nro.read_bytes())
    if args.output:
        args.output.write_bytes(patch)
    else:
        sys.stdout.buffer.write(patch)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
