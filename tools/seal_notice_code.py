#!/usr/bin/env python3
"""Seal final immutable notice code before ELF-to-NSO conversion (offline only)."""
import argparse
import hashlib
from pathlib import Path
import struct

MAGIC = b'ISNGC002'
SEAL_SIZE = 96


def layout(data):
    def unpack(fmt, offset):
        size = struct.calcsize(fmt)
        if offset < 0 or offset > len(data) - size:
            raise ValueError('truncated ELF structure')
        return struct.unpack_from(fmt, data, offset)

    if len(data) < 64 or data[:7] != b'\x7fELF\x02\x01\x01':
        raise ValueError('expected little-endian ELF64')
    if unpack('<H', 18)[0] != 183:
        raise ValueError('expected AArch64 ELF')
    shoff, = unpack('<Q', 40)
    stride, count, names_index = unpack('<HHH', 58)
    if stride != 64 or not count or names_index >= count:
        raise ValueError('invalid ELF section table')
    sections = [unpack('<IIQQQQIIQQ', shoff + i * stride) for i in range(count)]

    def payload(section):
        offset, size = section[4:6]
        if offset > len(data) or size > len(data) - offset:
            raise ValueError('section outside file')
        return data[offset:offset + size]

    def string(table, offset):
        end = table.find(b'\0', offset)
        if offset >= len(table) or end < 0:
            raise ValueError('unterminated ELF name')
        return table[offset:end].decode('ascii')

    names = payload(sections[names_index])
    bounds = {}
    abi_present = False
    slots = []
    for section in sections:
        if string(names, section[0]) == '.notice_seal':
            slots.append(section)
        if section[1] == 2:  # SHT_SYMTAB, including local hidden linker symbols
            if section[9] != 24 or section[5] % 24 or section[6] >= count:
                raise ValueError('invalid symbol table')
            strings = payload(sections[section[6]])
            symbols = payload(section)
            for offset in range(0, len(symbols), 24):
                name, _, _, index, value, _ = struct.unpack_from('<IBBHQQ', symbols, offset)
                name = string(strings, name)
                if name == 'g_NoticeCodeState' and index:
                    abi_present = True
                if name in ('__notice_code_start__', '__notice_code_end__',
                            '__notice_ro_start__', '__notice_ro_end__') and index:
                    if name in bounds:
                        raise ValueError('duplicate protected boundary')
                    bounds[name] = value
    if len(slots) != 1 or len(bounds) != 4 or not abi_present:
        raise ValueError('notice code boundaries, compatible guard or unique seal missing')
    slot = slots[0]
    if slot[1] != 1 or slot[2] != 2 or slot[5] != SEAL_SIZE:
        raise ValueError('notice seal must be a fixed allocated read-only section')
    payload(slot)
    start, end = (bounds['__notice_code_start__'], bounds['__notice_code_end__'])
    if not 0 < end - start <= 0x400000 or start % 4 or end % 4:
        raise ValueError('invalid protected code extent')
    owners = [s for s in sections if s[1] == 1 and s[2] == 6 and
              s[3] <= start < end <= s[3] + s[5]]
    if len(owners) != 1:
        raise ValueError('protected code must have a unique immutable executable owner')
    code = owners[0]
    payload(code)
    code_offset = code[4] + start - code[3]
    if code_offset < slot[4] + SEAL_SIZE and slot[4] < code_offset + end - start:
        raise ValueError('seal overlaps protected code')
    ro_start, ro_end = bounds['__notice_ro_start__'], bounds['__notice_ro_end__']
    if not end <= ro_start < ro_end <= 0x600000:
        raise ValueError('invalid protected read-only extent')
    owners = [s for s in sections if s[1] == 1 and s[2] == 2 and
              s[3] <= ro_start < ro_end <= s[3] + s[5]]
    if len(owners) != 1:
        raise ValueError('protected data must have a unique read-only owner')
    if (slot[3] < end and start < slot[3] + SEAL_SIZE) or (
            slot[3] < ro_end and ro_start < slot[3] + SEAL_SIZE):
        raise ValueError('seal overlaps protected virtual extents')
    rodata = owners[0]
    payload(rodata)
    ro_offset = rodata[4] + ro_start - rodata[3]
    if (ro_offset < slot[4] + SEAL_SIZE and slot[4] < ro_offset + ro_end - ro_start) or (
            ro_offset < code_offset + end - start and code_offset < ro_offset + ro_end - ro_start):
        raise ValueError('protected file extents overlap')
    for section in sections:
        if section[1] not in (4, 9):  # RELA/REL: runtime fixups must not change protected bytes
            continue
        width = 24 if section[1] == 4 else 16
        if section[9] != width or section[5] % width:
            raise ValueError('invalid relocation section')
        raw = payload(section)
        for offset in range(0, len(raw), width):
            target, = struct.unpack_from('<Q', raw, offset)
            # All supported dynamic AArch64 fixups write at most eight bytes.
            if (target < end and start < target + 8) or (
                    target < slot[3] + SEAL_SIZE and slot[3] < target + 8) or (
                    target < ro_end and ro_start < target + 8):
                raise ValueError('relocation overlaps immutable notice code or seal')
    return code_offset, start, end, slot[4], ro_offset, ro_start, ro_end


def expected_seal(data, info):
    offset, start, end, _, ro_offset, ro_start, ro_end = info
    header = MAGIC + struct.pack('<QQQQ', start, end, ro_start, ro_end)
    digest = hashlib.sha256(header + data[offset:offset + end - start] +
                            data[ro_offset:ro_offset + ro_end - ro_start]).digest()
    return header + digest + bytes(24)


def verify_elf(data):
    info = layout(data)
    offset = info[3]
    expected = expected_seal(data, info)
    if data[offset:offset + SEAL_SIZE] != expected:
        raise ValueError('notice code seal is absent or differs from final code')
    return {'code_start': info[1], 'code_end': info[2],
            'code_bytes': info[2] - info[1], 'rodata_bytes': info[6] - info[5],
            'sha256': expected[40:72].hex()}


def seal_elf(data):
    info = layout(data)
    offset = info[3]
    sealed = data[:offset] + expected_seal(data, info) + data[offset + SEAL_SIZE:]
    verify_elf(sealed)
    return sealed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--elf', type=Path, required=True)
    parser.add_argument('--verify', action='store_true')
    args = parser.parse_args()
    raw = args.elf.read_bytes()
    if not args.verify:
        raw = seal_elf(raw)
        # Only replace after complete validation, preserving the original on any error.
        temporary = args.elf.with_name(args.elf.name + '.notice-sealed')
        temporary.write_bytes(raw)
        temporary.replace(args.elf)
    print(verify_elf(raw))


if __name__ == '__main__':
    main()
