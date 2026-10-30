#!/usr/bin/env python3
"""Preserve time already advanced by native catch-up updates after rendering."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.nro_ips import encode_ips, read_module_id

MODULE_ID = bytes.fromhex('91C73FDD575061318D68886316AFEAC72388B2AB' + '00' * 12)
SOURCE_SHA256 = 'cc363208c220f65547edda6d8268b3b6c0f7373b14c91ae6ffb378018de4b66a'
LOOP_OFFSET = 0x4C08B8
LOOP_SIZE = 0x1B0
LOOP_SHA256 = '9ef801fb17e6e41b36c6d2bf48aa2289d3efcf7b639ea9aabfd5f41271da08f9'
SITE = 0x4C08F4
ORIGINAL = bytes.fromhex('491daa4e')  # FMOV V9.16B, V10.16B: anchor = sample.
REPLACEMENT = bytes.fromhex('29496a1e')  # FMAX D9,D9,D10: anchor = max(deadline,sample).
RECORD = (SITE, REPLACEMENT)


def build_loop_time_carry_patch(nro: bytes) -> bytes:
    """Reject every image except the supported original; emit one four-byte record.

    run_repentance adds 1/60 to D9 before each update and uses D10-D9 to choose
    skipped renders. Resetting D9 to D10 after a render loses an early update's
    lead and permits repeated overcompensation. FMAX retains that lead. When
    behind, it still rebases to the sampled wall time, preserving the original
    bounded recovery after long stalls, loading and suspension.

    Only D9's low double is live here; subsequent loop code reads it as D9.
    No additional branches, calls, allocation, clock sources or state are added.
    """
    if read_module_id(nro) != MODULE_ID:
        raise ValueError('unsupported game module ID')
    if nro[SITE:SITE + 4] != ORIGINAL:
        raise ValueError('native time anchor instruction does not match original')
    if hashlib.sha256(nro[LOOP_OFFSET:LOOP_OFFSET + LOOP_SIZE]).hexdigest() != LOOP_SHA256:
        raise ValueError('native timing loop context does not match original')
    if hashlib.sha256(nro).hexdigest() != SOURCE_SHA256:
        raise ValueError('unsupported original NRO SHA256')
    return encode_ips([RECORD])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--nro', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    blob = build_loop_time_carry_patch(args.nro.read_bytes())
    info = dict(module_id=MODULE_ID.hex().upper(), source_sha256=SOURCE_SHA256,
                offset=SITE, original=ORIGINAL.hex(), replacement=REPLACEMENT.hex(),
                patch_sha256=hashlib.sha256(blob).hexdigest(), bytes=len(blob),
                description='Preserve early simulation time across rendered frames')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(blob)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(info, indent=2) + '\n')
    print(json.dumps(info))


if __name__ == '__main__':
    main()
