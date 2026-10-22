#!/usr/bin/env python3
"""Find the call sites of a module offset (or of a mangled symbol name) in ``Repentance.nro``.

Why this exists
---------------
``tools/nro_disasm.py`` disassembles a single address range — the *forward*
direction. Several investigations need the *reverse* one ("who calls this",
"who reads this field"), and ``tools/ghidra_cached.py`` cannot answer it: the
in-repo Ghidra project is imported with ``-noanalysis``, so it has **no
reference graph at all** (``getReferencesTo`` returns nothing but the dynamic
symbol-table entry).

Two facts make a hand-rolled scan both correct and cheap:

1. NRO file offsets equal runtime module offsets, so a call site is just a
   ``BL``/``B`` instruction whose sign-extended 26-bit immediate lands on the
   requested address.
2. This module is built as a shared object **without** ``-Bsymbolic``, so calls
   to its own global functions go through a PLT stub (16 bytes:
   ``adrp x16``/``ldr x17``/``add x16``/``br x17``) whose GOT slot is described
   by a ``R_AARCH64_JUMP_SLOT`` entry.  That entry's ``r_info`` indexes
   ``.dynsym``, which carries the mangled name *and* the stubbed address — so
   the PLT can be decoded exactly, without guessing.

Hence: "who calls ``HUD::Update``" = "find the GOT slot whose JUMP_SLOT symbol
value is ``0x3aa378`` → find the stub that loads it → list the ``BL`` sites of
that stub → name the enclosing function".

Usage::

    python3 tools/nro_callers.py 0x3aa378
    python3 tools/nro_callers.py --symbol _ZN15IsaacRepentance3HUD6UpdateEv
    python3 tools/nro_callers.py --symbol HUD6Update --substring
    python3 tools/nro_callers.py --list-stubs HUD          # stub addr + name
"""

from __future__ import annotations

import argparse
import os
import struct
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "tools"))

import nro_symbols  # noqa: E402  (in-repo helper, stdlib only)

DEFAULT_NRO = os.path.join(
    REPO_ROOT,
    "The Binding of Isaac_ Afterbirth+ 1.7.9b [010021C000B6A800][v524288][UPD]",
    "Program #0",
    "1",
    ".nro",
    "Repentance.nro",
)

_MASK_OP = 0xFC000000
_OP_BL = 0x94000000
_OP_B = 0x14000000
_MASK_BCOND = 0xFF000010
_OP_BCOND = 0x54000000

#: dynamic tags we rely on.
_DT_STRTAB = 5
_DT_SYMTAB = 6
_DT_JMPREL = 23
_DT_PLTRELSZ = 2


def _sign_extend(value: int, bits: int) -> int:
    if value & (1 << (bits - 1)):
        return value - (1 << bits)
    return value


def bl_target(word: int, address: int, branches: bool) -> int | None:
    op = word & _MASK_OP
    if op == _OP_BL:
        pass
    elif branches and (op == _OP_B or (word & _MASK_BCOND) == _OP_BCOND):
        pass
    else:
        return None
    return address + (_sign_extend(word & 0x03FFFFFF, 26) << 2)


def caller_map(blob: bytes, targets: set[int], branches: bool) -> dict[int, list[int]]:
    found: dict[int, list[int]] = {target: [] for target in targets}
    for index in range(len(blob) // 4):
        address = index * 4
        word = struct.unpack_from("<I", blob, address)[0]
        landed = bl_target(word, address, branches)
        if landed is not None and landed in found:
            found[landed].append(address)
    return found


def jump_slots(blob: bytes) -> dict[int, tuple[str, int, int]]:
    """``{GOT slot: (mangled name, stub address, size)}`` from ``.rela.plt``."""
    dynamic, _ = nro_symbols._dynamic_table(blob)
    strtab = dynamic[_DT_STRTAB]
    symtab = dynamic[_DT_SYMTAB]
    offset = dynamic[_DT_JMPREL]
    count = dynamic[_DT_PLTRELSZ] // 24
    slots: dict[int, tuple[str, int, int]] = {}
    for index in range(count):
        entry = offset + index * 24
        r_offset, r_info = struct.unpack_from("<QQ", blob, entry)
        symbol = symtab + (r_info >> 32) * 24
        name_offset = struct.unpack_from("<I", blob, symbol)[0]
        name = nro_symbols._cstring(blob, strtab + name_offset) if name_offset else ""
        stub, size = struct.unpack_from("<QQ", blob, symbol + 8)
        slots[r_offset] = (name, stub, size)
    return slots


def _adrp_target(address: int, word: int) -> int:
    immhi = (word >> 5) & 0x7FFFF
    immlo = (word >> 29) & 0x3
    imm = (immhi << 2) | immlo
    if imm & (1 << 20):
        imm -= 1 << 21
    return ((address >> 12) + imm) << 12


def plt_stubs(blob: bytes) -> dict[int, int]:
    """``{GOT slot: first instruction of the PLT stub that loads it}``."""
    stubs: dict[int, int] = {}
    for index in range(len(blob) // 4 - 3):
        address = index * 4
        word = struct.unpack_from("<I", blob, address)[0]
        if (word & 0x9F000000) != 0x90000000:  # adrp
            continue
        destination = word & 0x1F
        second = struct.unpack_from("<I", blob, address + 4)[0]
        if (second & 0xFFC00000) != 0xF9400000:  # ldr xN, [xM, #imm]
            continue
        if ((second >> 5) & 0x1F) != destination:
            continue
        third = struct.unpack_from("<I", blob, address + 8)[0]
        if (third & 0xFFC003FF) != 0x91000210:  # add x16, x16, #imm
            continue
        fourth = struct.unpack_from("<I", blob, address + 12)[0]
        if (fourth & 0xFFFFFC1F) != 0xD61F0000:  # br x17
            continue
        slot = _adrp_target(address, word) + (((second >> 10) & 0xFFF) << 3)
        stubs.setdefault(slot, address)
    return stubs


def symbol_names(blob: bytes) -> list[tuple[int, str]]:
    _build, table = nro_symbols.parse_dynamic_symbols(blob)
    return sorted(
        (symbol.file_offset, name)
        for name, symbol in table.items()
        if symbol.file_offset is not None
    )


def enclosing(address: int, names: list[tuple[int, str]]) -> str:
    best = None
    for offset, name in names:
        if offset <= address:
            best = (offset, name)
        else:
            break
    return "" if best is None else "  %s+%#x" % (best[1], address - best[0])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("targets", nargs="*", help="module offsets, e.g. 0x3aa378")
    parser.add_argument("--nro", default=DEFAULT_NRO)
    parser.add_argument("--symbol", help="mangled (or partial) symbol name to resolve")
    parser.add_argument("--substring", action="store_true", help="substring match for --symbol")
    parser.add_argument("--list-stubs", help="print the PLT stub for every symbol containing this text")
    parser.add_argument("--branches", action="store_true", help="also match B / B.cond")
    parser.add_argument("--no-names", action="store_true", help="skip enclosing-function naming")
    parser.add_argument("--limit", type=int, default=40)
    args = parser.parse_args()

    blob = open(args.nro, "rb").read()

    if args.list_stubs:
        slots = jump_slots(blob)
        stubs = plt_stubs(blob)
        rows = [
            (stubs[slot], slot, name, stub)
            for slot, (name, stub, _size) in slots.items()
            if args.list_stubs in name and slot in stubs
        ]
        for stub_address, slot, name, stub in sorted(rows):
            print("stub=%#x slot=%#x target=%#x  %s" % (stub_address, slot, stub, name))
        print("total %d" % len(rows))
        return 0

    targets: list[tuple[int, str]] = []
    for value in args.targets:
        targets.append((int(value, 0), ""))

    slots = jump_slots(blob)
    stubs = plt_stubs(blob)
    #: 一个"函数地址"在被调用处通常出现为它的 PLT 桩地址，所以裸地址先翻译成桩。
    stub_for_target: dict[int, int] = {}
    for slot, (_name, stub_address, _size) in slots.items():
        if slot in stubs:
            stub_for_target.setdefault(stub_address, stubs[slot])

    def resolve_function(address: int) -> tuple[int, str]:
        """Return the address call sites actually reference, plus a human label."""
        stub = stub_for_target.get(address)
        if stub is None:
            return address, "(direct / no PLT stub)"
        slot = {value: key for key, value in stubs.items()}.get(stub)
        name = slots.get(slot, ("", 0, 0))[0] if slot is not None else ""
        return stub, name

    resolved: list[tuple[int, str]] = [resolve_function(address) for address, _ in targets]

    if args.symbol:
        if args.substring:
            candidates = [
                (stub, name) for _slot, (name, stub, _size) in slots.items()
                if args.symbol in name
            ]
        else:
            candidates = [
                (stub, name) for _slot, (name, stub, _size) in slots.items()
                if name == args.symbol
            ]
        if not candidates:
            print("no PLT stub matches %r (its calls may be direct or it may be unused here)"
                  % args.symbol)
            return 1
        resolved.extend(sorted(candidates))

    if not resolved:
        parser.print_help()
        return 2

    names = [] if args.no_names else symbol_names(blob)
    found = caller_map(blob, {address for address, _ in resolved}, args.branches)
    for address, label in resolved:
        sites = found[address]
        print("== callers of %#x : %d  %s" % (address, len(sites), label))
        for site in sites[: args.limit]:
            print("    %#x%s" % (site, enclosing(site, names)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
