"""Cold gates for the custom-cache coin, bomb, and key limits."""

from __future__ import annotations

from dataclasses import dataclass
import struct
import sys

try:
    from . import build_patches
    from . import custom_item_pool_cold
    from . import extra_source_cold
    from .nro_ips import encode_ips
except ImportError:
    import build_patches
    import custom_item_pool_cold
    import extra_source_cold
    from nro_ips import encode_ips


BUILD_ID = bytes.fromhex("91C73FDD575061318D68886316AFEAC72388B2AB") + bytes(12)
TEXT_END = 0x68D000


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
        name="AddCoins maxcoins cap csel",
        source=0x2800FC,
        original=0x1A880128,
        gate=0x201F14,
        fallback=0x1CF228,
        slot=0x203278,
    ),
    ColdSite(
        name="AddBombs maxbombs cap csel",
        source=0x2803FC,
        original=0x1A89B108,
        gate=0x1BDEB4,
        fallback=0x1ACF34,
        slot=0x1BDFD8,
    ),
    ColdSite(
        name="AddKeys maxkeys cap csel",
        source=0x2804F8,
        original=0x1A89B108,
        gate=0x3B2DC4,
        fallback=0x3B2E14,
        slot=0x3B2F18,
    ),
)

def _intervals(sites: tuple[ColdSite, ...]):
    for site in sites:
        for offset, size, label in (
            (site.gate, 12, "gate"),
            (site.fallback, 8, "fallback"),
            (site.slot, 8, "slot"),
        ):
            yield offset, offset + size, f"{site.name} {label}"


CAVES: tuple[tuple[int, int], ...] = tuple(
    (begin, end - begin) for begin, end, _ in _intervals(SITES)
)

SLOTS: tuple[tuple[int, int], ...] = tuple((site.slot, 8) for site in SITES)

FUNCTION_GUARDS = (
    (
        0x280068,
        bytes.fromhex("fd7bbda9f50b00f9fd030091f44f02a9"),
        "AddCoins entry",
    ),
    (
        0x280148,
        bytes.fromhex("fd7bbfa9fd03009168410090084d43f9"),
        "GetMaxCoins entry",
    ),
    (
        0x2802E8,
        bytes.fromhex("ff8301d1fd7b01a9fd430091f91300f9"),
        "AddBombs entry",
    ),
    (
        0x2804E8,
        bytes.fromhex("08d456b90801010b1f8d0171690c8052"),
        "AddKeys entry",
    ),
)


def _enc_ldr_literal(rt: int, delta: int) -> int:
    if delta % 4 or not -(1 << 20) <= delta < (1 << 20):
        raise ValueError("pointer slot is outside LDR literal range")
    return 0x58000000 | (((delta >> 2) & 0x7FFFF) << 5) | (rt & 0x1F)


def _enc_cbz(rt: int, delta: int) -> int:
    if delta % 4 or not -(1 << 20) <= delta < (1 << 20):
        raise ValueError("fallback is outside CBZ range")
    return 0xB4000000 | (((delta >> 2) & 0x7FFFF) << 5) | (rt & 0x1F)


def _predecessor_kind(nro: bytes, offset: int) -> str:
    if offset < 4:
        return "none"
    word = struct.unpack_from("<I", nro, offset - 4)[0]
    if word == 0xD65F03C0:
        return "ret"
    if word & 0xFC000000 == 0x14000000:
        return "b"
    return "other"


def _known_ranges() -> list[tuple[int, int, str]]:
    ranges = [
        (0x3631C4, 0x3631D0, "mgo-misc tear gate"),
        (0x38E8A8, 0x38E8B0, "mgo-misc tear slot"),
        (0x37FC48, 0x37FC50, "mgo-misc tear fallback"),
        (0x259874, 0x259880, "mgo-death gate"),
        (0x24DDA4, 0x24DDB0, "mgo-death callback gate"),
        (0x249548, 0x249550, "mgo-death slot"),
        (0x303FD4, 0x303FE0, "activeMin1073 veneer 0"),
        (0x3289E8, 0x3289F0, "activeMin1073 slot 0"),
        (0x31D954, 0x31D960, "activeMin1073 veneer 1"),
        (0x342B98, 0x342BA0, "activeMin1073 slot 1"),
        (0x32F114, 0x32F120, "activeMin1073 veneer 2"),
        (0x342EB8, 0x342EC0, "activeMin1073 slot 2"),
        (0x342D24, 0x342D30, "activeMin1073 veneer 3"),
        (0x342EE8, 0x342EF0, "activeMin1073 slot 3"),
        (0x2FE458, 0x2FE460, "activeMin1073 veneer 4"),
        (0x3017A8, 0x3017B0, "activeMin1073 slot 4"),
        (0x68CF60, 0x68CF90, "StatHUD cold gates"),
        (0x60C704, 0x60C730, "StatHUD fallbacks"),
        (0x429AD8, 0x429ADC, "nightmare source"),
        (0x427A24, 0x427A2C, "nightmare veneer"),
        (0x423A98, 0x423AA0, "nightmare slot"),
        (0x3FE9D4, 0x3FE9D8, "main-menu source"),
        (0x4237C8, 0x4237D0, "main-menu veneer"),
        (0x3E3778, 0x3E3780, "main-menu slot"),
        (0x68CBE0, 0x68D000, "ordinary source-cold relay cave"),
        (0x277744, 0x277750, "legacy custom-cache gate"),
        (0x259988, 0x259990, "legacy custom-cache slot"),
        (0x23F7D4, 0x23F7E0, "legacy custom-cache fallback"),
    ]
    ranges.extend(
        (begin, end, "mgo-chance")
        for begin, end in (
            (0x44C5D4, 0x44C5E0), (0x44AFC8, 0x44AFD0),
            (0x443CB8, 0x443CC0), (0x443894, 0x4438A0),
            (0x443874, 0x443880), (0x4437B8, 0x4437C0),
            (0x3C24C4, 0x3C24D0), (0x3C2228, 0x3C2230),
            (0x3CBCF8, 0x3CBD00), (0x3DEFC4, 0x3DEFD0),
            (0x3EB654, 0x3EB660), (0x3D5488, 0x3D5490),
            (0x3B3854, 0x3B3860), (0x3B3814, 0x3B3820),
            (0x3B2F78, 0x3B2F80),
        )
    )
    for source, veneer, slot in (
        (0x4666E0, 0x500478, 0x500518),
        (0x457B90, 0x503138, 0x503158),
        (0x299F48, 0x503998, 0x5039C8),
        (0x300A94, 0x5042B8, 0x5054F8),
        (0x5DF2C, 0x50AD08, 0x50B7A8),
    ):
        ranges.extend(
            (
                (source, source + 4, "phase source"),
                (veneer, veneer + 8, "phase veneer"),
                (slot, slot + 8, "phase slot"),
            )
        )
    for site in extra_source_cold.SITES:
        ranges.extend(
            (
                (site.source, site.source + 4, site.name + " source"),
                (site.gate, site.gate + 12, site.name + " gate"),
                (site.slot, site.slot + 8, site.name + " slot"),
                (site.fallback, site.fallback + 8, site.name + " fallback"),
            )
        )
    for site in custom_item_pool_cold.SITES:
        ranges.extend(
            (
                (site.source, site.source + 4, site.name + " source"),
                (site.gate, site.gate + 12, site.name + " gate"),
                (site.slot, site.slot + 8, site.name + " slot"),
                (site.fallback, site.fallback + 8, site.name + " fallback"),
            )
        )
    return ranges


def cave_intervals() -> tuple[tuple[int, int, str], ...]:
    return tuple(_intervals(SITES))


def gate_image(site: ColdSite) -> bytes:
    return struct.pack(
        "<III",
        _enc_ldr_literal(16, site.slot - site.gate),
        _enc_cbz(16, site.fallback - (site.gate + 4)),
        0xD61F0200,
    )


def fallback_image(site: ColdSite) -> bytes:
    return struct.pack("<I", site.original) + build_patches.encode_branch(
        site.fallback + 4, site.source + 4
    )


def _signed(value: int, bits: int) -> int:
    sign = 1 << (bits - 1)
    return (value ^ sign) - sign


def _instruction_target(offset: int, word: int) -> int | None:
    if word & 0x7C000000 == 0x14000000:
        return offset + 4 * _signed(word & 0x3FFFFFF, 26)
    if (
        word & 0xFF000010 == 0x54000000
        or word & 0x7E000000 == 0x34000000
        or word & 0x3B000000 == 0x18000000
    ):
        return offset + 4 * _signed((word >> 5) & 0x7FFFF, 19)
    if word & 0x7E000000 == 0x36000000:
        return offset + 4 * _signed((word >> 5) & 0x3FFF, 14)
    if word & 0x9F000000 == 0x10000000:
        immediate = ((word >> 5) & 0x7FFFF) * 4 + ((word >> 29) & 3)
        return offset + _signed(immediate, 21)
    return None


def _xrefs(nro: bytes, intervals: tuple[tuple[int, int, str], ...]) -> list[tuple[int, int]]:
    wanted = {address for begin, end, _ in intervals for address in range(begin, end)}
    hits: list[tuple[int, int]] = []
    for offset in range(0, TEXT_END - 3, 4):
        word32 = struct.unpack_from("<I", nro, offset)[0]
        target = _instruction_target(offset, word32)
        if word32 in wanted:
            hits.append((offset, word32))
        if target is not None and target in wanted:
            hits.append((offset, target))
        if offset + 8 <= TEXT_END:
            word64 = struct.unpack_from("<Q", nro, offset)[0]
            if word64 in wanted:
                hits.append((offset, word64))
    return hits


def verify(nro: bytes, sites: tuple[ColdSite, ...] = SITES) -> None:
    if len(nro) < TEXT_END or nro[0x40:0x60] != BUILD_ID:
        raise ValueError("fixed Repentance NRO identity mismatch")
    intervals = tuple(_intervals(sites))
    ordered = sorted(intervals)
    for left, right in zip(ordered, ordered[1:]):
        if left[1] > right[0]:
            raise ValueError(f"cold intervals overlap: {left[2]} and {right[2]}")
    known = _known_ranges()
    for begin, end, name in intervals:
        for other_begin, other_end, other_name in known:
            if begin < other_end and other_begin < end:
                raise ValueError(f"{name} overlaps {other_name}")
    hits = _xrefs(nro, intervals)
    if hits:
        raise ValueError(f"native references target cold intervals: {hits[:4]}")
    for offset, guard, name in FUNCTION_GUARDS:
        if nro[offset:offset + len(guard)] != guard:
            raise ValueError(f"{name} guard mismatch")
    for site in sites:
        if struct.unpack_from("<I", nro, site.source)[0] != site.original:
            raise ValueError(f"{site.name}: source instruction mismatch")
        build_patches.encode_branch(site.source, site.gate)
        build_patches.encode_branch(site.fallback + 4, site.source + 4)
        for address, length, label in (
            (site.gate, 12, "gate"),
            (site.fallback, 8, "fallback"),
            (site.slot, 8, "slot"),
        ):
            if nro[address:address + length] != bytes(length):
                raise ValueError(f"{site.name}: {label} hole is not empty")
            if _predecessor_kind(nro, address) not in ("ret", "b"):
                raise ValueError(f"{site.name}: {label} is not RET/B-tail padding")


def cold_records(
    nro: bytes, sites: tuple[ColdSite, ...] = SITES
) -> list[tuple[int, bytes]]:
    verify(nro, sites)
    records: list[tuple[int, bytes]] = []
    occupied: list[tuple[int, int]] = []
    for site in sites:
        for offset, payload in (
            (site.source, build_patches.encode_branch(site.source, site.gate)),
            (site.gate, gate_image(site)),
            (site.fallback, fallback_image(site)),
            (site.slot, bytes(8)),
        ):
            interval = (offset, offset + len(payload))
            if any(interval[0] < end and begin < interval[1]
                   for begin, end in occupied):
                raise ValueError(f"{site.name}: generated records overlap")
            occupied.append(interval)
            records.append((offset, payload))
    return records


def build_cold_patch(nro: bytes) -> bytes:
    return encode_ips(cold_records(nro))


def main(argv: list[str] | None = None) -> int:
    import argparse
    from pathlib import Path

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
