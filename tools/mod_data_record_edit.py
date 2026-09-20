#!/usr/bin/env python3
"""改**模组数据容器**里某条记录的值（等长替换 + 重算校验和），并保证可验证、可回退。

## 为什么需要它

EID 的设置存在游戏存档分区的 `isaac-mod-data.bin`（`ISMODST2` 容器）里，而**卡上没有装
ModConfigMenu**（每局读数里都有 `module 'scripts.modconfig' not found`）⇒ 游戏里**没有菜单**可以改设置，
只能改这个文件。用户的诉求是"EID 恢复原版，但扫描频率再往下降" ⇒ 代码必须逐字节还原成原版，
唯一能动的地方就是这里的那一个数字。

## 容器格式（来自 `runtime/source/mod_persistence.hpp`，逐字段对齐）

```
头 32 字节： magic "ISMODST2" @0 (8) | version u16 @8 | headerSize u16 @10 |
             generation u64 @12 | recordCount u32 @20 | payloadLength u32 @24 |
             checksum u32 @28（FNV-1a-32 over payload）
每条记录：   namespace u64 @0 | key u64 @8 | type u8 @16 | （@17..@19 保留）| length u32 @20 |
             值 @24，共 length 字节；记录总长 = 24 + length
```

`checksum` 是 FNV-1a 32 位（offset basis 2166136261 / prime 16777619），**只覆盖 payload**。

## 纪律（照 `AGENTS.md`）

* **只做等长替换**：改完 `length` 与记录边界都不变，风险最小；长度不一致直接拒绝。
* 改完**必须**在本地重新解析一遍（`--verify`）并把结果打出来；写卡用 `tools/device_ftp.py`（它会先判"游戏在不在跑"）。
* 写之前先把原文件备份下来（逐字节），回退就是把备份写回去。

## 用法

    # 0) 自测（不需要设备）：造一个合成容器 → 改一条 → 校验 → 解析
    python3 tools/mod_data_record_edit.py --selftest

    # 1) 看容器里有什么
    python3 tools/mod_data_record_edit.py list <本地文件>

    # 2) 等长替换某个命名空间里的一个子串（会重算校验和，就地写回）
    python3 tools/mod_data_record_edit.py edit <本地文件> \
        --namespace 0x3ba7a40c243dcc08 --replace '"RefreshRate":30' '"RefreshRate":10'

    # 3) 只校验（解析 + 校验和 + 每条记录的长度自洽）
    python3 tools/mod_data_record_edit.py verify <本地文件>
"""

from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path

MAGIC = b"ISMODST2"
VERSION = 2
HEADER_SIZE = 32
RECORD_HEADER_SIZE = 24
FNV_OFFSET = 2166136261
FNV_PRIME = 16777619
MOD_DATA_KEY = 0x6D6F642D64617461


def checksum(payload: bytes) -> int:
    value = FNV_OFFSET
    for byte in payload:
        value ^= byte
        value = (value * FNV_PRIME) & 0xFFFFFFFF
    return value


def parse(data: bytes) -> tuple[dict, list[dict]]:
    """返回 (头部字典, 记录列表)；任何自洽性检查不过就抛 ValueError。"""
    if len(data) < HEADER_SIZE:
        raise ValueError(f"文件太短：{len(data)} 字节")
    if data[:8] != MAGIC:
        raise ValueError(f"magic 不对：{data[:8]!r}")
    version, header_size = struct.unpack_from("<HH", data, 8)
    if version != VERSION or header_size != HEADER_SIZE:
        raise ValueError(f"版本/头长不对：version={version} headerSize={header_size}")
    generation = struct.unpack_from("<Q", data, 12)[0]
    record_count, payload_length, stored_checksum = struct.unpack_from("<III", data, 20)
    if payload_length != len(data) - HEADER_SIZE:
        raise ValueError(f"payloadLength={payload_length} 与文件长度不符（{len(data) - HEADER_SIZE}）")
    payload = data[HEADER_SIZE:]
    actual = checksum(payload)
    if actual != stored_checksum:
        raise ValueError(f"校验和不符：文件里 {stored_checksum:#010x}，算出来 {actual:#010x}")

    records = []
    offset = 0
    while offset < payload_length:
        if payload_length - offset < RECORD_HEADER_SIZE:
            raise ValueError(f"记录头被截断 @{offset}")
        namespace, key = struct.unpack_from("<QQ", payload, offset)
        type_byte = payload[offset + 16]
        length = struct.unpack_from("<I", payload, offset + 20)[0]
        if length > payload_length - offset - RECORD_HEADER_SIZE:
            raise ValueError(f"记录值被截断 @{offset}")
        value = payload[offset + RECORD_HEADER_SIZE: offset + RECORD_HEADER_SIZE + length]
        records.append({
            "offset": offset,
            "namespace": namespace,
            "key": key,
            "type": type_byte,
            "length": length,
            "value": value,
        })
        offset += RECORD_HEADER_SIZE + length
    if len(records) != record_count:
        raise ValueError(f"recordCount={record_count} 与实际解出 {len(records)} 条不符")
    return ({"generation": generation, "record_count": record_count,
             "payload_length": payload_length, "checksum": stored_checksum}, records)


def describe(record: dict) -> str:
    text = ""
    if record["type"] == 1:
        try:
            text = record["value"].decode("utf-8")
        except UnicodeDecodeError:
            text = "<非 UTF-8>"
    preview = text.replace("\n", " ")[:96]
    key = record["key"].to_bytes(8, "little").decode("ascii", "replace")
    return (f"  ns={record['namespace']:#018x} key={record['key']:#018x}({key!r}) "
            f"type={record['type']} len={record['length']}\n      {preview}")


def cmd_list(path: Path) -> int:
    header, records = parse(path.read_bytes())
    print(f"{path}: generation={header['generation']} 记录 {header['record_count']} 条 "
          f"payload={header['payload_length']} 字节 checksum={header['checksum']:#010x} ✓")
    for record in records:
        print(describe(record))
    return 0


def cmd_verify(path: Path) -> int:
    header, records = parse(path.read_bytes())
    print(f"{path}: 解析与校验和都过 ✓（generation={header['generation']}、"
          f"{header['record_count']} 条、payload={header['payload_length']} 字节）")
    return 0


def cmd_edit(path: Path, namespace: int | None, old: str, new: str) -> int:
    if len(old) != len(new):
        print(f"拒绝：等长替换才安全（old={len(old)} 字节，new={len(new)} 字节）", file=sys.stderr)
        return 2
    data = bytearray(path.read_bytes())
    header, records = parse(bytes(data))
    targets = [r for r in records if namespace is None or r["namespace"] == namespace]
    hits = 0
    for record in targets:
        if record["type"] != 1:
            continue
        start = HEADER_SIZE + record["offset"] + RECORD_HEADER_SIZE
        blob = bytes(data[start:start + record["length"]])
        if old.encode() not in blob:
            continue
        if blob.count(old.encode()) != 1:
            print(f"拒绝：命名空间 {record['namespace']:#018x} 里有 {blob.count(old.encode())} 处 '{old}'，"
                  f"说不清该改哪一个", file=sys.stderr)
            return 2
        replaced = blob.replace(old.encode(), new.encode())
        assert len(replaced) == len(blob)
        data[start:start + record["length"]] = replaced
        hits += 1
    if hits != 1:
        print(f"拒绝：命中 {hits} 条记录（需要恰好 1 条）", file=sys.stderr)
        return 2
    payload = bytes(data[HEADER_SIZE:])
    struct.pack_into("<I", data, 28, checksum(payload))
    path.write_bytes(bytes(data))
    # 就地自检：改完必须还能解析
    header_after, _ = parse(path.read_bytes())
    print(f"{path}: 已把 '{old}' 换成 '{new}'（等长），"
          f"checksum 重算为 {header_after['checksum']:#010x}，重新解析 ✓")
    return 0


def cmd_selftest() -> int:
    """造一个合成容器：两条记录、字符串类型；改一条里的等长子串；校验和与解析都必须随之正确。"""
    namespace = 0x3BA7A40C243DCC08
    text = b'{"RefreshRate":30,"FontType":"cn_alt"}'
    other = b'hello'
    payload = b""
    for ns, value in ((namespace, text), (0x1111222233334444, other)):
        payload += struct.pack("<QQ", ns, MOD_DATA_KEY) + bytes([1]) + b"\0\0\0" + \
            struct.pack("<I", len(value)) + value
    header = MAGIC + struct.pack("<HH", VERSION, HEADER_SIZE) + struct.pack("<Q", 7) + \
        struct.pack("<III", 2, len(payload), checksum(payload))
    blob = header + payload

    tmp = Path("/tmp/mod-data-selftest.bin")
    tmp.write_bytes(blob)
    _, records = parse(tmp.read_bytes())
    assert len(records) == 2, records
    assert records[0]["value"] == text
    rc = cmd_edit(tmp, namespace, '"RefreshRate":30', '"RefreshRate":10')
    assert rc == 0, rc
    header_after, records_after = parse(tmp.read_bytes())
    assert header_after["payload_length"] == len(payload)            # 等长 ⇒ 长度不变
    assert records_after[0]["value"] == text.replace(b"30", b"10")
    assert records_after[1]["value"] == other                        # 别的记录没被碰
    assert header_after["checksum"] == checksum(payload.replace(b"30", b"10", 1))
    # 反例：不等长必须被拒
    assert cmd_edit(tmp, namespace, '"RefreshRate":10', '"RefreshRate":100') == 2
    # 反例：校验和错了必须解析失败
    broken = bytearray(tmp.read_bytes())
    struct.pack_into("<I", broken, 28, 0xDEADBEEF)
    try:
        parse(bytes(broken))
    except ValueError:
        pass
    else:
        raise AssertionError("校验和错了却没报错")
    print("selftest ✓（等长替换生效、其他记录不受影响、校验和重算正确、不等长与坏校验和都被拒）")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="改模组数据容器里的一条记录（等长替换 + 重算校验和）")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("selftest")
    for name in ("list", "verify"):
        p = sub.add_parser(name)
        p.add_argument("path", type=Path)
    p_edit = sub.add_parser("edit")
    p_edit.add_argument("path", type=Path)
    p_edit.add_argument("--namespace", type=lambda text: int(text, 0), default=None)
    p_edit.add_argument("--replace", nargs=2, metavar=("OLD", "NEW"), required=True)
    args = parser.parse_args()

    if args.command == "selftest":
        return cmd_selftest()
    if args.command == "list":
        return cmd_list(args.path)
    if args.command == "verify":
        return cmd_verify(args.path)
    return cmd_edit(args.path, args.namespace, args.replace[0], args.replace[1])


if __name__ == "__main__":
    raise SystemExit(main())
