#!/usr/bin/env python3
"""Bind guard policy/data locally while retaining its public integration ABI."""
import argparse
from pathlib import Path
import subprocess

PUBLIC_NOTICE_ABI = {
    '_ZN5isaac7runtime6notice19InstallRuntimeTypesEP9lua_State',
    '_ZN5isaac7runtime6notice9integrity14RuntimeAllowedEv',
    '_ZN5isaac7runtime6notice9integrity7BlockedEv',
}
PRIVATE_PROVIDERS = {
    'sha256CalculateHash', 'sha256ContextCreate', 'sha256ContextUpdate',
    'sha256ContextGetHash', 'memcpy', 'memmove', 'memset', 'memcmp',
    'g_NoticeIntegrityExpectedRoot',
}


def local_symbols(symbols):
    """Include weak/unique inline metadata, not just externally called functions."""
    result = set()
    for line in symbols.splitlines():
        fields = line.split()
        if len(fields) < 3:
            continue
        name = fields[-1]
        if name in PRIVATE_PROVIDERS or (
            '5isaac7runtime6notice' in name and name not in PUBLIC_NOTICE_ABI
        ):
            result.add(name)
    return sorted(result)


def seal(source, output, nm, objcopy):
    symbols = subprocess.check_output([nm, '-g', '--defined-only', str(source)], text=True)
    names = local_symbols(symbols)
    command = [objcopy, '--strip-debug', '--strip-unneeded']
    command += ['--localize-symbol=' + name for name in names]
    subprocess.run([*command, str(source), str(output)], check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--nm', default='aarch64-none-elf-nm')
    parser.add_argument('--objcopy', default='aarch64-none-elf-objcopy')
    args = parser.parse_args()
    seal(args.input, args.output, args.nm, args.objcopy)


if __name__ == '__main__':
    main()
