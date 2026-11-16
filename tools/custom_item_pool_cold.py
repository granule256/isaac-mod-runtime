"""Cold gates for the two native ItemPool pool-address calculations."""

from __future__ import annotations

from dataclasses import dataclass
import struct

try:
    from . import build_patches
except ImportError:
    import build_patches


BUILD_ID = bytes.fromhex("91C73FDD575061318D68886316AFEAC72388B2AB") + bytes(12)


@dataclass(frozen=True)
class ColdSite:
    name: str
    source: int
    original: int
    gate: int
    fallback: int
    slot: int


SITES = (
    ColdSite(
        name="ItemPool::GetCollectible initial pool lookup",
        source=0x3C6698,
        original=0x9B285AF7,
        gate=0xA96F4,
        fallback=0x6C44,
        slot=0x6CC8,
    ),
    ColdSite(
        name="ItemPool::GetCollectible Chaos repick lookup",
        source=0x3C66EC,
        original=0x9B285817,
        gate=0x12E4,
        fallback=0x357A4,
        slot=0x18A18,
    ),
)


def _enc_ldr_literal(rt: int, delta: int) -> int:
    if delta % 4 or not -(1 << 20) <= delta < (1 << 20):
        raise ValueError("literal load outside range")
    return 0x58000000 | (((delta >> 2) & 0x7FFFF) << 5) | rt


def _enc_cbz(rt: int, delta: int) -> int:
    if delta % 4 or not -(1 << 20) <= delta < (1 << 20):
        raise ValueError("CBZ outside range")
    return 0xB4000000 | (((delta >> 2) & 0x7FFFF) << 5) | rt


def gate_image(site: ColdSite) -> bytes:
    if site.slot % 8:
        raise ValueError("pointer slot must be 8-byte aligned for atomic publication")
    return struct.pack(
        "<III",
        _enc_ldr_literal(16, site.slot - site.gate),
        _enc_cbz(16, site.fallback - (site.gate + 4)),
        0xD61F0200,  # br x16
    )


def fallback_image(site: ColdSite) -> bytes:
    return struct.pack("<I", site.original) + build_patches.encode_branch(
        site.fallback + 4, site.source + 4
    )


def cold_records(nro: bytes) -> list[tuple[int, bytes]]:
    if len(nro) < 0x68D000 or nro[0x40:0x60] != BUILD_ID:
        raise ValueError("fixed Repentance NRO identity mismatch")
    records: list[tuple[int, bytes]] = []
    ranges: list[tuple[int, int, str]] = []
    for site in SITES:
        if struct.unpack_from("<I", nro, site.source)[0] != site.original:
            raise ValueError(f"{site.name}: source instruction mismatch")
        if nro[site.gate:site.gate + 12] != bytes(12):
            raise ValueError(f"{site.name}: gate hole is not empty")
        if nro[site.fallback:site.fallback + 8] != bytes(8):
            raise ValueError(f"{site.name}: fallback hole is not empty")
        if nro[site.slot:site.slot + 8] != bytes(8):
            raise ValueError(f"{site.name}: pointer slot is not empty")
        for address in (site.gate, site.fallback, site.slot):
            # An aligned 8-byte slot may use the last eight bytes of a
            # 12-byte padding run. Validate the start of that same zero run.
            start = address
            while start >= 4 and nro[start - 4:start] == bytes(4):
                start -= 4
            predecessor = struct.unpack_from("<I", nro, start - 4)[0]
            if predecessor != 0xD65F03C0 and predecessor & 0xFC000000 != 0x14000000:
                raise ValueError(f"{site.name}: cave must follow RET/B")
        source = build_patches.encode_branch(site.source, site.gate)
        records.extend(
            (
                (site.source, source),
                (site.gate, gate_image(site)),
                (site.fallback, fallback_image(site)),
                (site.slot, bytes(8)),
            )
        )
        ranges.extend(
            (
                (site.source, site.source + 4, site.name + " source"),
                (site.gate, site.gate + 12, site.name + " gate"),
                (site.fallback, site.fallback + 8, site.name + " fallback"),
                (site.slot, site.slot + 8, site.name + " slot"),
            )
        )
    ranges.sort()
    for left, right in zip(ranges, ranges[1:]):
        if left[1] > right[0]:
            raise ValueError(f"overlapping cold ranges: {left[2]} and {right[2]}")
    return records
