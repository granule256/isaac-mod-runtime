#!/usr/bin/env python3
"""把一份 EID 个人设置**写进模组自己的配置文件** `eid_config.lua`（而不是靠存档/一次性补丁）。

## 为什么可以这么做（判据在 EID 源码里，不是猜的）

`main.lua:13` 是 `EID.Config = EID.UserConfig`，而 `EID.UserConfig` / `EID.DefaultConfig` 都定义在
`eid_config.lua` 里。`OnGameStart`（`main.lua:1948-1963`）的判据是：

```lua
if savedEIDConfig.Version == EID.Config.Version then
    local isDefaultConfig = true
    for key, value in pairs(EID.Config) do
        if EID.DefaultConfig[key] ~= value then isDefaultConfig = false end
    end
    if isDefaultConfig or EID.MCMLoaded then  -- ← 只有"文件还是默认"或"装了 MCM"才用存档
        ... 用存档里的值覆盖 ...
```

⇒ **只要 `EID.UserConfig` 与 `EID.DefaultConfig` 不同**（我们改过它），EID 就"**以文件为准**"，
不再拿存档里的旧值覆盖。于是：**把设置直接写进 `eid_config.lua` 就能生效**，
`main.lua` 保持逐字节原版，也不需要"一次性补丁 + 退出保存"那套。

## 做法

只改**与文件现有值不同**的那些标量项（数字/字符串/布尔）——不碰表值项（那些是运行期状态：
`CollectedItems` / `UsedPillColors` / `PlayerItemInteractions` … 它们由存档单独读写）。
写法是**在文件末尾追加**一段"逐项赋值"，不重排、不重写原表 ⇒ diff 最小、人可复核。

## 用法

    python3 tools/apply_eid_config_to_mod.py <eid_config.lua> <settings.json> [--dry-run] [--set K=V ...]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

#: `["Key"] = 值,` —— eid_config.lua 的 UserConfig 表就是这个格式（可能有行内注释）
SCALAR_LINE = re.compile(r'^\s*\["([^"]+)"\]\s*=\s*(.+?),?\s*(?:--.*)?$')


def parse_user_config(path: Path) -> dict[str, object]:
    """从 `EID.UserConfig = { … }` 里抽出标量项（数字/字符串/布尔）。"""
    text = path.read_text(encoding="utf-8")
    start = text.index("EID.UserConfig = {")
    depth = 0
    end = None
    for index in range(text.index("{", start), len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                end = index
                break
    if end is None:
        raise ValueError("找不到 EID.UserConfig 表的结尾")
    values: dict[str, object] = {}
    for line in text[start:end].splitlines():
        match = SCALAR_LINE.match(line)
        if not match:
            continue
        key, raw = match.group(1), match.group(2).strip()
        if raw in ("true", "false"):
            values[key] = raw == "true"
        elif raw.startswith('"') and raw.endswith('"'):
            values[key] = raw[1:-1]
        else:
            try:
                values[key] = int(raw)
            except ValueError:
                try:
                    values[key] = float(raw)
                except ValueError:
                    continue
    return values


def lua_literal(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    return repr(value)


def main() -> int:
    parser = argparse.ArgumentParser(description="把 EID 设置写进 eid_config.lua（追加逐项赋值，不重写原表）")
    parser.add_argument("config_lua", type=Path)
    parser.add_argument("settings_json", type=Path)
    parser.add_argument("--dry-run", action="store_true", help="只打印会写什么，不改文件")
    parser.add_argument("--set", action="append", default=[], metavar="KEY=VALUE",
                        help="额外强制覆盖（例如 RefreshRate=6），可多次")
    args = parser.parse_args()

    file_values = parse_user_config(args.config_lua)
    settings = json.loads(args.settings_json.read_text(encoding="utf-8"))
    #: 不写进配置文件的键：`_` 开头的是内部/诊断残留（例如我们测性能时留下的 `_PerfReport`），
    #: `Version` 由 EID 自己管理（写死会让它以后升级时判定"版本不符"）。
    skip = {"Version"} | {key for key in settings if key.startswith("_")}
    overrides: dict[str, object] = {}
    for key, value in settings.items():
        if key in skip:
            continue
        if isinstance(value, (dict, list)):
            continue                      # 表值项是运行期状态，交给存档
        if key in file_values and file_values[key] == value:
            continue                      # 与文件现有值相同 ⇒ 不用写
        overrides[key] = value
    for pair in args.set:
        key, _, raw = pair.partition("=")
        if raw in ("true", "false"):
            overrides[key] = raw == "true"
        else:
            overrides[key] = int(raw) if raw.lstrip("-").isdigit() else raw

    print(f"eid_config.lua 现有标量项 {len(file_values)} 个；要写入 {len(overrides)} 项：")
    for key in sorted(overrides):
        print(f"  {key}: {file_values.get(key, '<文件里没有>')!r} -> {overrides[key]!r}")
    if args.dry_run:
        return 0

    block = ["", "",
             "-- ===========================================================================",
             "-- 本机设置（随发布包提供，2026-09-20 起）",
             "-- 这些赋值写在文件末尾：只覆盖列出的项，原表一个字不动。",
             "-- 这里写了值 ⇒ EID.UserConfig 与 EID.DefaultConfig 不同 ⇒ EID 判定“配置文件被改过”，",
             "-- 于是以本文件为准、不再用存档里的旧值覆盖（判据见 main.lua:1948-1963）。",
             "-- 想改哪一项，直接改下面的值；想恢复“以存档为准”，把这一段删掉即可。",
             "-- ==========================================================================="]
    for key in sorted(overrides):
        block.append(f'EID.UserConfig["{key}"] = {lua_literal(overrides[key])}')
    raw = args.config_lua.read_bytes()
    if "本机设置（随发布包提供".encode() in raw:
        print("文件里已经有这一段了；先删掉再跑（避免重复）", file=sys.stderr)
        return 2
    # ★ 逐字节保住原来的行尾：EID 的 `.lua` 是 CRLF，用文本模式读写会把**整个文件**变成 LF
    #   （2026-09-20 实测：这样一改 diff 从 13 行膨胀到 1381 行，"最小改动"就没了）。
    newline = b"\r\n" if raw.count(b"\r\n") > raw.count(b"\n") - raw.count(b"\r\n") else b"\n"
    block_bytes = newline.join(line.encode("utf-8") for line in block) + newline
    args.config_lua.write_bytes(raw.rstrip(b"\r\n") + newline + block_bytes)
    print(f"已写入 {args.config_lua}（行尾保持 {'CRLF' if newline == b'\r\n' else 'LF'}）")
    print(f"已写入 {args.config_lua}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
