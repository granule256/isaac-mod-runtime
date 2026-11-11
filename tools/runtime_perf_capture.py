#!/usr/bin/env python3
"""Capture coherent runtime counters through an existing NXC host session."""
import argparse
import base64
import json
from pathlib import Path
import re
import struct
import sys
import time

try:
    from .elf_syms import load_symbols, read_vaddr
except ImportError:
    from elf_syms import load_symbols, read_vaddr

MAGIC = 0x3150414e53504652
HEADER_FIELDS = (
    'magic version headerBytes bucketBytes callbackCapacity apiCapacity sequence tick '
    'tickFrequency generation nativeCycles logicCycles callbackCalls callbackTicks '
    'callbackOverflow apiCalls apiTicks apiOverflow syscalls syscallTicks gcTicks '
    'gcSteps gcCycles gcMaxFrame gcHeap gcDebt flags errors').split()
HEADER = struct.Struct('<28Q')
BUCKET = struct.Struct('<4Q4I')
LAYOUT_MAGIC = 0x3154594c465052
LAYOUT = struct.Struct('<16Q')
LAYOUT_FIELDS = ('magic version descriptorBytes snapshotBytes headerBytes bucketBytes '
                 'callbackCapacity apiCapacity ownerCount ownerStride self request done '
                 'attributionUntil snapshot owners').split()


def validate_layout(raw, sdk, symbols):
    if len(raw) != LAYOUT.size:
        raise RuntimeError('unsupported performance layout descriptor size')
    layout = dict(zip(LAYOUT_FIELDS, LAYOUT.unpack(raw)))
    if (layout['magic'], layout['version'], layout['descriptorBytes'],
            layout['headerBytes'], layout['bucketBytes']) != (LAYOUT_MAGIC, 1, 128, HEADER.size, BUCKET.size):
        raise RuntimeError('unsupported live performance layout')
    capacities = layout['callbackCapacity'], layout['apiCapacity']
    if any(not 0 < n <= 4096 for n in capacities):
        raise RuntimeError('invalid live performance table capacities')
    if (layout['snapshotBytes'] != HEADER.size + sum(capacities) * BUCKET.size or
            not 0 < layout['ownerCount'] <= 4096 or not 0 < layout['ownerStride'] <= 256):
        raise RuntimeError('invalid live performance layout extents')
    extents = {
        'self': ('g_RuntimePerfLayout', LAYOUT.size),
        'request': ('g_RuntimePerfCaptureRequest', 8),
        'done': ('g_RuntimePerfCaptureDone', 8),
        'attributionUntil': ('g_RuntimePerfAttributionUntil', 8),
        'snapshot': ('g_RuntimePerfSnapshot', layout['snapshotBytes']),
        'owners': ('g_ModOwnerNames', layout['ownerCount'] * layout['ownerStride']),
    }
    for field, (name, size) in extents.items():
        if name not in symbols or symbols[name] != (layout[field] - sdk, size):
            raise RuntimeError('ELF/live layout mismatch: ' + name)
        if not 0 < layout[field] <= (1 << 64) - size:
            raise RuntimeError('invalid live layout pointer: ' + name)
        if field != 'owners' and layout[field] & 7:
            raise RuntimeError('unaligned live layout pointer: ' + name)
    return layout


def decode_snapshot(raw):
    if len(raw) < HEADER.size:
        raise ValueError('truncated snapshot header')
    header = dict(zip(HEADER_FIELDS, HEADER.unpack_from(raw)))
    if (header['magic'], header['version'], header['headerBytes'], header['bucketBytes']) != (
            MAGIC, 1, HEADER.size, BUCKET.size):
        raise ValueError('unsupported performance snapshot schema')
    capacities = header['callbackCapacity'], header['apiCapacity']
    if any(not 0 < n <= 4096 for n in capacities):
        raise ValueError('invalid snapshot capacity')
    if len(raw) != HEADER.size + sum(capacities) * BUCKET.size:
        raise ValueError('truncated or oversized snapshot')
    result = {'header': header}
    offset = HEADER.size
    for name, capacity in zip(('callbacks', 'apis'), capacities):
        rows = {}
        for _ in range(capacity):
            key, count, ticks, maximum, *bins = BUCKET.unpack_from(raw, offset)
            offset += BUCKET.size
            if count:
                if key in rows:
                    raise ValueError('duplicate performance bucket key')
                rows[key] = dict(key=key, count=count, ticks=ticks, maximum=maximum, bins=bins)
        result[name] = rows
    return result


def summarize(before, after, owners, api_names=None, callback_names=None):
    a, b = before['header'], after['header']
    if a['generation'] != b['generation'] or a['tickFrequency'] != b['tickFrequency']:
        raise ValueError('runtime generation or timer frequency changed')
    if b['tick'] <= a['tick'] or not a['tickFrequency'] or (a['flags'] & b['flags'] & 3) != 3:
        raise ValueError('runtime timing/VM is unavailable or clock did not advance')
    seconds = (b['tick'] - a['tick']) / a['tickFrequency']

    def delta(name):
        value = b[name] - a[name]
        if value < 0:
            raise ValueError('counter reset during capture: ' + name)
        return value

    rows = {}
    for kind in ('callbacks', 'apis'):
        rows[kind] = []
        for key, row in after[kind].items():
            first = before[kind].get(key, dict(count=0, ticks=0))
            calls, ticks = row['count'] - first['count'], row['ticks'] - first['ticks']
            if calls < 0 or ticks < 0:
                raise ValueError('bucket reset during capture')
            if not calls:
                continue
            entry = dict(key=key, calls=calls, calls_per_second=calls / seconds,
                         inclusive_ms_per_second=ticks * 1000 / a['tickFrequency'] / seconds,
                         mean_us=ticks * 1e6 / a['tickFrequency'] / calls)
            if kind == 'callbacks':
                owner = (key >> 32) & 65535
                event = key & 0xffffffff
                event_name = (callback_names or {}).get(event, 'custom/string' if event == 0xffffffff else str(event))
                entry.update(event=event, event_name=event_name, owner=owner, generation=key >> 48,
                             owner_name=owners.get(owner, 'unknown owner ' + str(owner)))
            else:
                identifier = key & 0xffffffff
                entry.update(api=identifier, engine_only=bool(key & (1 << 32)),
                             name=(api_names or {}).get(identifier, f'0x{identifier:08x}'))
            rows[kind].append(entry)
        rows[kind].sort(key=lambda x: x['inclusive_ms_per_second'], reverse=True)
    calls = delta('callbackCalls')
    represented = sum(row['calls'] for row in rows['callbacks'])
    details = (a['flags'] & b['flags'] & 8) == 8
    return dict(seconds=seconds, generation=b['generation'],
                timing_semantics='inclusive: nested callbacks/APIs/GC may overlap; do not sum as CPU time',
                api_timing_scope=('handler wrappers enabled' if b['flags'] & 4 else
                                  'instrumented subpaths only; full handler wrappers disabled'),
                callback_calls_per_second=calls / seconds,
                callback_attribution_enabled=details,
                callback_coverage=(represented / calls if calls else 1) if details else None,
                callback_overflow=delta('callbackOverflow'),
                api_overflow=delta('apiOverflow'),
                callback_inclusive_ms_per_second=delta('callbackTicks') * 1000 / a['tickFrequency'] / seconds,
                gc_ms_per_second=delta('gcTicks') * 1000 / a['tickFrequency'] / seconds,
                gc_steps_per_second=delta('gcSteps') / seconds,
                gc_cycles=delta('gcCycles'), gc_heap_before=a['gcHeap'], gc_heap_after=b['gcHeap'],
                native_cycles_per_second=delta('nativeCycles') / seconds,
                logic_cycles_per_second=delta('logicCycles') / seconds,
                errors_before=a['errors'], errors_after=b['errors'], **rows)


def load_api_names(root):
    folder = root / 'runtime/src/interfaces/lua'
    domains = {name: int(value) for name, value in re.findall(
        r'^\s*(\w+)\s*=\s*(\d+)\s*,', (folder / 'api_descriptor.hpp').read_text(), re.M)}
    pattern = (r'MakeId\(ApiDomain::(\w+),\s*(\d+),\s*(0x[0-9a-fA-F]+|\d+)\),'
               r'\s*ApiDomain::\w+,\s*"([^"]+)",\s*"([^"]+)"')
    names = {}
    for domain, group, sequence, owner, name in re.findall(pattern, (folder / 'api_catalog.cpp').read_text()):
        names[(domains[domain] << 24) | (int(group) << 16) | int(sequence, 0)] = owner + '.' + name
    text = (folder / 'runtime_perf.hpp').read_text()
    for name, offset in re.findall(r'kPerfInternalId(\w+)\s*=\s*kPerfInternalIdBase\s*\+\s*(\d+)U', text):
        names[0xff000000 + int(offset)] = name
    return names


def load_callback_names(root):
    source = root / 'runtime/source/program/pc_lua_enum_data.cpp'
    return {int(value, 0): name for name, value in re.findall(
        r'\{"(MC_[A-Z0-9_]+)",\s*(0x[0-9a-fA-F]+|\d+)\}', source.read_text())}


class NxcTransport:
    def __init__(self, package=None):
        if package:
            sys.path.insert(0, str(Path(package).expanduser().resolve()))
        try:
            from nxc_host.client import HostClient
            from nxc_host.config import load_config
        except ImportError as error:
            raise RuntimeError('install NXC or pass --nxc-package pointing to its zipapp/package directory') from error
        self.client = HostClient(load_config())

    def call(self, method, **params):
        response = self.client.request({'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call',
                                        'params': {'name': 'nxc_call', 'arguments': {
                                            'method': method, 'params': params}}}, autostart=False)
        if 'error' in response:
            raise RuntimeError(response['error'])
        result = response['result']
        if result.get('isError'):
            raise RuntimeError(result)
        payload = json.loads(next(x['text'] for x in result['content'] if x.get('type') == 'text'))
        if 'error' in payload:
            raise RuntimeError(payload['error'])
        return payload['payload']


class PerfReader:
    def __init__(self, transport, elf):
        self.transport = transport
        self.pid = self.current_pid()
        blob = Path(elf).read_bytes()
        self.syms = load_symbols(blob)
        info = self.transport.call('mem.info')
        main = int(next(x['main_base'] for x in info if isinstance(x, dict) and 'main_base' in x), 16)
        veneer = self.read(main + 0x86ff0, 16)
        if veneer[:8] != bytes.fromhex('5000005800021fd6'):
            raise RuntimeError('unsupported runtime bootstrap; no memory writes performed')
        gateway = int.from_bytes(veneer[8:], 'little')
        self.sdk = self.q(gateway + 24) - self.syms['isaac_internal_hook_context'][0]
        for name in ('exl_main', 'IsaacModRuntime_CreateProceduralItemWithCpuPixels'):
            address, size = self.syms[name]
            count = min(64, size)
            if not count or self.read(self.sdk + address, count) != read_vaddr(blob, address, count):
                raise RuntimeError('ELF does not match the running SDK; no memory writes performed')
        descriptor = self.address('g_RuntimePerfLayout')
        if self.syms['g_RuntimePerfLayout'][1] != LAYOUT.size:
            raise RuntimeError('ELF performance descriptor size mismatch; no writes performed')
        self.layout = validate_layout(self.read(descriptor, LAYOUT.size), self.sdk, self.syms)
        self.request, self.done = self.layout['request'], self.layout['done']
        self.attribution_until, self.snapshot = self.layout['attributionUntil'], self.layout['snapshot']

    def current_pid(self):
        rows = self.transport.call('title.current')
        app = next((x for x in rows if isinstance(x, dict) and x.get('running') == 'application'), None)
        if not app or int(app.get('program_id', '0'), 16) != 0x010021C000B6A000:
            raise RuntimeError('supported game is not running')
        return int(app['pid'])

    def address(self, name):
        if name not in self.syms:
            raise RuntimeError('SDK lacks snapshot support: ' + name)
        return self.sdk + self.syms[name][0]

    def read(self, address, size):
        pieces = []
        for offset in range(0, size, 3072):
            count = min(3072, size - offset)
            payload = self.transport.call('mem.read', addr=hex(address + offset), size=count)
            raw = base64.b64decode(next(x for x in payload if isinstance(x, str)), validate=True)
            if len(raw) != count:
                raise RuntimeError('short memory read')
            pieces.append(raw)
        return b''.join(pieces)

    def q(self, address):
        return int.from_bytes(self.read(address, 8), 'little')

    def capture(self):
        if self.current_pid() != self.pid:
            raise RuntimeError('application process changed; capture aborted before memory writes')
        sequence = max(self.q(self.request), self.q(self.done)) + 1
        self.transport.call('mem.write', addr=hex(self.request),
                            data=base64.b64encode(struct.pack('<Q', sequence)).decode(),
                            confirm='I-KNOW-THIS-WRITES-MEMORY')
        deadline = time.monotonic() + 5
        while self.q(self.done) != sequence:
            if time.monotonic() > deadline:
                raise TimeoutError('game thread did not complete performance capture')
            time.sleep(.03)
        raw = self.read(self.snapshot, self.layout['snapshotBytes'])
        if self.q(self.done) != sequence or self.q(self.request) != sequence:
            raise RuntimeError('another profiler requested a capture; snapshot rejected')
        decoded = decode_snapshot(raw)
        if decoded['header']['sequence'] != sequence:
            raise RuntimeError('incomplete performance capture')
        for field in ('callbackCapacity', 'apiCapacity', 'headerBytes', 'bucketBytes'):
            if decoded['header'][field] != self.layout[field]:
                raise RuntimeError('captured header disagrees with live layout')
        return raw, decoded

    def write_attribution_until(self, value):
        if self.current_pid() != self.pid:
            raise RuntimeError('application changed; attribution write aborted')
        self.transport.call('mem.write', addr=hex(self.attribution_until),
                            data=base64.b64encode(struct.pack('<Q', value)).decode(),
                            confirm='I-KNOW-THIS-WRITES-MEMORY')

    def arm_attribution(self, seconds):
        _, snapshot = self.capture()
        header = snapshot['header']
        if not header['tick'] or not header['tickFrequency'] or (header['flags'] & 3) != 3:
            raise RuntimeError('runtime timer/VM is not ready for attribution')
        if self.q(self.attribution_until) > header['tick']:
            raise RuntimeError('another callback profiler is already active')
        # Absolute target-clock deadline also stops attribution if this process dies.
        self.attribution_deadline = header['tick'] + int((seconds + 15) * header['tickFrequency'])
        self.write_attribution_until(self.attribution_deadline)

    def stop_attribution(self):
        if self.current_pid() == self.pid and self.q(self.attribution_until) == self.attribution_deadline:
            self.write_attribution_until(0)

    def owners(self):
        stride, count = self.layout['ownerStride'], self.layout['ownerCount']
        raw = self.read(self.layout['owners'], count * stride)
        return {i: raw[i * stride:(i + 1) * stride].split(b'\0')[0].decode(errors='replace')
                for i in range(count)}

    def presentation(self):
        raw = self.read(0x8000004, 174)
        if raw[:4] != b'SPF\0':
            raise RuntimeError('SaltyNX presentation counter unavailable')
        return dict(time=time.monotonic(), presents=struct.unpack_from('<Q', raw, 165)[0])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--elf', type=Path, required=True)
    parser.add_argument('--nxc-package', help='NXC zipapp or Python package root; uses the existing host session')
    parser.add_argument('--seconds', type=float, default=8)
    parser.add_argument('--callback-details', action='store_true',
                        help='sample per-(owner,event) callback costs during the requested windows')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if not 0 < args.seconds <= 3600:
        parser.error('--seconds must be in (0, 3600]')
    if args.callback_details and args.seconds > 30:
        parser.error('detailed callback windows must not exceed 30 seconds')
    reader = PerfReader(NxcTransport(args.nxc_package), args.elf)
    owners = reader.owners()
    clocks = reader.transport.call('clk.list')
    if args.callback_details:
        reader.arm_attribution(args.seconds)
    try:
        raw_a, a = reader.capture()
        try:
            present_a = reader.presentation()
        except RuntimeError:
            present_a = None
        time.sleep(args.seconds)
        raw_b, b = reader.capture()
        present_b = reader.presentation() if present_a else None
    finally:
        if args.callback_details:
            reader.stop_attribution()
    if reader.transport.call('clk.list') != clocks:
        raise RuntimeError('device clocks changed during capture')
    root = Path(__file__).resolve().parents[1]
    report = summarize(a, b, owners, load_api_names(root), load_callback_names(root))
    if args.callback_details:
        if not report['callback_attribution_enabled']:
            raise RuntimeError('callback attribution expired during capture')
        report['callback_detail_scope'] = 'instrumented window; its FPS is not an uninstrumented benchmark'
    report['clocks'] = clocks
    if present_a:
        report['presentation_seconds'] = present_b['time'] - present_a['time']
        report['fps'] = (present_b['presents'] - present_a['presents']) / report['presentation_seconds']
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.with_suffix('.before.bin').write_bytes(raw_a)
    args.output.with_suffix('.after.bin').write_bytes(raw_b)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k: v for k, v in report.items() if k not in ('callbacks', 'apis', 'clocks')}, indent=2))
    for row in report['callbacks'][:12]:
        print(f"{row['owner_name']}: {row['event_name']}: {row['calls_per_second']:.1f}/s "
              f"{row['inclusive_ms_per_second']:.2f} inclusive ms/s")


if __name__ == '__main__':
    main()
