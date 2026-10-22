#!/usr/bin/env python3
"""只读核对怀表的道具配置、原生文件索引、图片缓存和地面图层。

NXC只使用title.current、mem.info和mem.read；不挂起进程、不注入代码或改图。
--elf为卡上运行时的对应ELF，供动态模块表缺少Repentance时定位引擎；
也可显式--engine-base，随后仍核对原件的三处代码字节。
结果是非原子现场快照，记录前后PID/帧数和索引向量变化，不把读失败当不存在。
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import socket
import struct
import sys
from pathlib import Path

PRIMARY = Path('/Users/kelinls/code/github/isaac mod')
DEFAULT_NRO = PRIMARY / 'The Binding of Isaac_ Afterbirth+ 1.7.9b [010021C000B6A800][v524288][UPD]/Program #0/1/.nro/Repentance.nro'
TARGETS = (
    'gfx/items/collectibles/collectibles_232_stopwatch.pcx',
    'gfx/items/trinkets/trinket_061_thelefthand.pcx',
)


class ProbeError(RuntimeError):
    pass


def canonical(path: str) -> str:
    # 原版只折叠ASCII大小写，不改UTF-8文件名的其它字节。
    return ''.join(chr(ord(c) + 32) if 'A' <= c <= 'Z' else c for c in path.replace('\\', '/'))


def djb2(path: str, insensitive: bool = True) -> int:
    # FileManager::HashDJB2(4c2a14)忽略大小写；Graphics版(523650)由bool控制。
    value = 5381
    text = canonical(path) if insensitive else path.replace('\\', '/')
    for byte in text.encode('utf-8'):
        value = (value * 33 + byte) & 0xffffffff
    return value


class ReadOnlyNxc:
    def __init__(self, ip: str, port: int, timeout: float, nxc):
        self.nxc = nxc
        self.socket = socket.create_connection((ip, port), timeout)
        self.socket.settimeout(timeout)
        self.stream = self.socket.makefile('rb')
        self.calls = 0

    def close(self):
        self.stream.close()
        self.socket.close()

    def command(self, command: str):
        if command.split()[0] not in {'title.current', 'mem.info', 'mem.read'}:
            raise ProbeError('此工具仅提供三个只读命令')
        self.socket.sendall((command + '\n').encode())
        header = self.stream.readline().decode().strip()
        if not header.startswith('OK '):
            raise ProbeError(f'{command}: {header or "连接中断"}')
        lines = []
        for _ in range(int(header.split()[1])):
            line = self.stream.readline()
            if not line:
                raise ProbeError('响应正文中断')
            lines.append(line.decode().rstrip('\r\n'))
        self.calls += 1
        return lines

    def structured(self, command: str):
        return self.nxc.to_structured(self.command(command))

    def read(self, address: int, size: int) -> bytes:
        if address <= 0 or size < 0 or size > 1024 * 1024:
            raise ProbeError(f'非法读取范围：{address:#x}/{size}')
        out = bytearray()
        for offset in range(0, size, 2000):
            count = min(2000, size - offset)
            lines = self.command(f'mem.read addr={address + offset:#x} size={count}')
            payload = [line[1:] for line in lines if line.startswith('#')]
            if len(payload) != 1:
                raise ProbeError('内存响应没有唯一的数据行')
            block = base64.b64decode(payload[0], validate=True)
            if len(block) != count:
                raise ProbeError('内存响应长度不符')
            out.extend(block)
        return bytes(out)

    def q(self, address: int) -> int:
        return struct.unpack('<Q', self.read(address, 8))[0]

    def u(self, address: int) -> int:
        return struct.unpack('<I', self.read(address, 4))[0]

    def string(self, address: int) -> str | None:
        if not address:
            return None
        value = bytearray()
        for offset in range(0, 512, 32):
            block = self.read(address + offset, 32)
            if b'\0' in block:
                value.extend(block.split(b'\0', 1)[0])
                return value.decode('utf-8', 'strict')
            value.extend(block)
        raise ProbeError('路径超过512字节或不是有效的零结尾字符串')

    def native_string(self, address: int) -> str:
        value = self.read(address, 24)
        if value[0] & 1:
            size, data = struct.unpack_from('<QQ', value, 8)
            if size > 511 or not data:
                raise ProbeError('libc++长字符串长度/指针不符')
            return self.read(data, size).decode('utf-8', 'strict')
        size = value[0] >> 1
        if size > 22:
            raise ProbeError('libc++短字符串长度不符')
        return value[1:1 + size].decode('utf-8', 'strict')


def vector(client, address: int, stride: int, limit: int):
    begin, end = struct.unpack('<QQ', client.read(address, 16))
    if not begin and not end:
        return begin, end, 0
    if not begin or end < begin or (end - begin) % stride or (end - begin) // stride > limit:
        raise ProbeError(f'向量范围不符：{address:#x}, {begin:#x}..{end:#x}')
    return begin, end, (end - begin) // stride


def file_map_entry(client, file_map: int, query: str, nodes: dict):
    # FileMap::Get(4cafd8)：map根在this+0x10；节点key+0x20/value+0x28。
    node = client.q(file_map + 0x10)
    wanted = djb2(query)
    visited = set()
    for _ in range(64):
        if not node or node == file_map + 0x10:
            return None
        if node in visited:
            raise ProbeError('文件索引树存在环')
        visited.add(node)
        if node not in nodes:
            nodes[node] = client.read(node, 48)
        data = nodes[node]
        left, right = struct.unpack_from('<QQ', data)
        key = struct.unpack_from('<I', data, 0x20)[0]
        if key == wanted:
            pointer = struct.unpack_from('<Q', data, 0x28)[0]
            name = client.string(pointer)
            return {'node': hex(node), 'key': hex(key), 'value_pointer': hex(pointer),
                    'value': name, 'value_matches_query': name is not None and canonical(name) == canonical(query),
                    'value_hash': hex(djb2(name)) if name else None,
                    'value_key_consistent': djb2(name) == key if name else None}
        node = left if wanted < key else right
    raise ProbeError('文件索引树超过64层')


def resolve_engine(client, modules, elf: Path | None, explicit: int | None):
    if explicit:
        return explicit, {'method': 'explicit'}
    matches = [m for m in modules if isinstance(m, dict) and 'base' in m
               and 'repentance' in json.dumps(m).lower()]
    if len(matches) == 1:
        return int(str(matches[0]['base']), 0), {'method': 'mem.info', 'module': matches[0]}
    if elf is None:
        raise ProbeError('mem.info没有唯一游戏模块；需要卡上对应ELF或已验证的--engine-base')
    import elf_syms
    blob = elf.read_bytes()
    symbols = elf_syms.load_symbols(blob)
    anchors = ['exl_main', 'IsaacModRuntime_GetRuntimeIdentity', '_Z28TryInstallDefaultManifestModRK12TargetModule']
    offsets = [(symbols[name][0], elf_syms.read_vaddr(blob, symbols[name][0], 16)) for name in anchors]
    candidates = sorted({int(str(m['base']), 0) + int(str(m['size']), 0)
                         for m in modules if isinstance(m, dict) and 'module' in m and 'base' in m and 'size' in m})
    for base in candidates:
        try:
            if not all(client.read(base + offset, 16) == expected for offset, expected in offsets):
                continue
        except ProbeError:
            continue
        names = [n for n in symbols if n.endswith('g_EngineModuleBaseE')]
        if len(names) != 1:
            raise ProbeError('ELF中引擎基址变量不唯一')
        return client.q(base + symbols[names[0]][0]), {'method': 'runtime-elf-three-anchors',
                    'runtime_base': hex(base), 'elf_sha256': hashlib.sha256(blob).hexdigest()}
    raise ProbeError('没有运行时通过指定ELF的三个代码锚点')


def inspect(client, engine: int, nro: bytes):
    # 这三条均不在当前生产挂点清单中，故比原字节；避免误把自身入口中继判为版本错误。
    guards = {0x4d0d70: 8, 0x4cafd8: 16, 0x4d1ddc: 16}
    for offset, size in guards.items():
        if client.read(engine + offset, size) != nro[offset:offset + size]:
            raise ProbeError(f'原生图片/文件查询入口不符：{offset:#x}')
    report = {'engine': hex(engine), 'native_guards_verified': True,
              'nro_sha256': hashlib.sha256(nro).hexdigest(), 'snapshot_non_atomic': True}
    game = client.q(client.q(engine + 0xaac698))
    report['game'] = hex(game)
    report['frame_before'] = client.u(game + 0x24f99c) if game else None
    manager = client.q(client.q(engine + 0xaac648))
    if manager:
        config = manager + 0x36538
        begin, _, count = vector(client, config, 8, 65536)
        if count <= 232:
            raise ProbeError('当前道具配置没有232号条目')
        item = client.q(begin + 232 * 8)
        report['item232'] = {'address': hex(item), 'id': client.u(item + 4),
                             'name': client.native_string(item + 8), 'gfx': client.native_string(item + 0x38)}
    content = client.q(engine + 0xaac748)
    begin, end, count = vector(client, content + 0x10, 8, 64)
    mounts = struct.unpack(f'<{count}Q', client.read(begin, count * 8)) if count else ()
    nodes, candidates = {}, {'rom:/resources/' + query for query in TARGETS}
    report['file_maps'] = []
    for file_map in reversed(mounts):
        prefix = client.string(client.q(file_map + 0x20))
        entries = {query: file_map_entry(client, file_map, query, nodes) for query in TARGETS}
        report['file_maps'].append({'address': hex(file_map), 'prefix': prefix, 'entries': entries})
        if prefix:
            for entry in entries.values():
                if entry and entry['value']:
                    candidates.add(prefix.rstrip('/') + '/' + entry['value'].lstrip('/'))
    report['mount_vector_changed'] = vector(client, content + 0x10, 8, 64)[:2] != (begin, end)
    images = client.q(engine + 0xaac758)
    buckets = client.q(images)
    bucket_count = client.u(client.q(engine + 0xaad518))
    if not buckets or not 1 <= bucket_count <= 65536:
        raise ProbeError('原生图片缓存桶数量/指针不符')
    report['image_manager'] = {'address': hex(images), 'bucket_count': bucket_count, 'buckets': []}
    # GetImage使用Graphics.HashDJB2(caseInsensitive=false)，实际路径可能已规范化大小写。
    indexes = {djb2(path, False) % bucket_count for path in candidates}
    indexes |= {djb2(path.upper(), False) % bucket_count for path in candidates}
    for index in sorted(indexes):
        address = buckets + index * 24
        begin, end, count = vector(client, address, 16, 4096)
        refs = client.read(begin, count * 16) if count else b''
        entries = []
        for offset in range(0, len(refs), 16):
            image, control = struct.unpack_from('<QQ', refs, offset)
            path = client.string(client.q(image + 0x50)) if image else None
            path_bucket = djb2(path, False) % bucket_count if path else None
            entries.append({'image': hex(image), 'control': hex(control), 'path': path,
                            'path_bucket': path_bucket, 'path_matches_bucket': path_bucket == index if path else None,
                            'loaded_flags': client.u(image + 0x10) if image else None,
                            'control_counts_word': client.u(control + 8) if control else None,
                            'control_owned_image': hex(client.q(control + 0x40)) if control else None})
        report['image_manager']['buckets'].append({'index': index, 'entries': entries,
                         'vector_changed': vector(client, address, 16, 4096)[:2] != (begin, end)})
    report['watch_pickups'] = []
    if game:
        room = client.q(game + 0x21550)
        if room:
            # EntityList::EntityArray起点+0x78，元素数+0x84；是数组，不是vector.end。
            array = client.q(room + 0x19c8)
            count = client.u(room + 0x19d4)
            if count > 4096 or (count and not array):
                raise ProbeError('房间实体数组范围不符')
            addresses = struct.unpack(f'<{count}Q', client.read(array, count * 8)) if count else ()
            for entity in addresses:
                if not entity:
                    continue
                kind, variant, subtype = struct.unpack('<3I', client.read(entity + 0x38, 12))
                if (kind, variant, subtype) != (5, 100, 232):
                    continue
                sprite = entity + 0x50
                layers = client.q(sprite + 0xa8)
                layer_count = client.u(sprite + 0xb0)
                if not layers or not 1 < layer_count < 128:
                    raise ProbeError('怀表底座图层范围不符')
                layer = layers + 0xb0
                image = client.q(layer + 0xa0)
                report['watch_pickups'].append({'entity': hex(entity), 'replacement': client.native_string(layer + 0x10),
                    'image': hex(image), 'control': hex(client.q(layer + 0xa8)),
                    'path': client.string(client.q(image + 0x50)) if image else None})
        report['frame_after'] = client.u(game + 0x24f99c)
    report['read_commands'] = client.calls
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ip', default='10.178.165.202')
    parser.add_argument('--port', type=int, default=47800)
    parser.add_argument('--timeout', type=float, default=5)
    parser.add_argument('--elf', type=Path)
    parser.add_argument('--engine-base', type=lambda s: int(s, 0))
    parser.add_argument('--nro', type=Path, default=DEFAULT_NRO)
    parser.add_argument('--nxc-client', type=Path, default=Path('/Users/kelinls/code/github/KELI-NX/pc'))
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(args.nxc_client))
    import nxc
    client = None
    report = {'ip': args.ip, 'port': args.port, 'complete': False}
    try:
        nro = args.nro.read_bytes()
        client = ReadOnlyNxc(args.ip, args.port, args.timeout, nxc)
        title = client.structured('title.current')
        if not title or not isinstance(title[0], dict) or int(title[0].get('program_id', '0'), 0) != 0x010021c000b6a000:
            raise ProbeError('当前运行的不是目标游戏')
        report['title_before'] = title
        engine, identity = resolve_engine(client, client.structured('mem.info'), args.elf, args.engine_base)
        report['identity'] = identity
        report.update(inspect(client, engine, nro))
        report['title_after'] = client.structured('title.current')
        if report['title_after'] != title:
            raise ProbeError('读取期间进程身份变化，不能作为同一现场')
        report['complete'] = True
    except (OSError, ProbeError, ValueError, KeyError, struct.error) as error:
        report['error'] = f'{type(error).__name__}: {error}'
    finally:
        if client:
            client.close()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report['complete'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
