#!/usr/bin/env python3
"""接口台账的"安全桩"检查器：**哪些 API 有目录行，但语义是假的**。

## 为什么要有它（2026-09-18）

`analysis/lua-api-inventory` 把 API 分类成 `implemented` 的口径是**只判"命中
`api_catalog.cpp`"**（见 `tools/build_lua_api_inventory.py` 的 `classify()`）——
也就是说，**"有目录行"被当成了"已实现"**。

后果已经真实发生过一次：`EntityPlayer:GetNumKeys` / `GetNumBombs` / `GetSoulCharge` /
`GetBloodCharge` 四个都是 `PushZero` 的**恒返回 0 假桩**，却都被记成 `implemented`
⇒ 谁读那份台账都会以为"钥匙/炸弹已经做完了"。而假读数**不报错、不崩**，模组拿它们做算术
会得到错误结论（与"套装恒 `0/3`"同一类静默失效）。

这与 2026-09-18 下午修掉的"回调覆盖率多算一条"是**同一族问题**：**用间接特征代替真值源**。
回调那一面后来把真值源钉成了 `HasDispatchSite()`；接口这一面就由本工具提供。

## 判据（刻意保守：只把"有把握"的判成桩）

对每个在绑定表里出现的处理器，**剥掉注释**后看函数体：

* 含 `PushZero(` 或 `WarnStubOnce(`（"我什么都不读、直接编一个值"的两个标记）
  **且不含**任何"真的碰了引擎/游戏状态"的标记时 ⇒ 判 `stub`；
* 其余一律判 `real`（含"读不到才降级"的写法 —— 那是对的，不是桩）；
* 找不到函数体（例如走 `field_api.hpp` 数据行、或处理器定义在别处）⇒ 判 `unknown`，
  **不猜**。`unknown` 是欠账，门禁盯着它只许降不许升。

## 用法

    python3 tools/lua_api_stub_report.py            # 报告
    python3 tools/lua_api_stub_report.py --write    # 重新生成 tools/lua_api_stub_ledger.json
    python3 tools/lua_api_stub_report.py --strict   # 有任何漂移/无理由的条目就非零退出（门禁用）
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
LUA_DIR = ROOT / "runtime" / "src" / "interfaces" / "lua"
CATALOG = LUA_DIR / "api_catalog.cpp"
LEDGER = ROOT / "tools" / "lua_api_stub_ledger.json"

#: "我什么都不读、直接编一个值"的标记。
STUB_MARKERS = ("PushZero(", "WarnStubOnce(")
#: "真的碰了引擎/游戏状态"的标记。出现任何一个就不再算桩 —— 哪怕它同时有降级分支
#: （"读不到才降级"是**正确**写法，不能和"恒返回 0"混为一谈；2026-09-18 我自己就混过一次）。
REAL_MARKERS = (
    "ReadEngine(",
    "ReadEngineUnchecked(",
    "ReadCurrent",
    "ReadGame",
    "ObserveGame",
    "ObserveLevel",
    "Thunk(",
    "Method()",
    "ValidatedEntity",
    "ValidatedEntityPlayer",
    "CallRoomIntMethod",
    "ResolveEngine",
    "ResolveMusic",
    "IsEngineMemoryReadable(",
    "lua_pcallk(",          # 回调转发类处理器（真的在跑东西）
    "luaL_ref(",            # 登记类（真的在记东西）
    # **共享的"读一个字段并压栈"助手**：项目里这类成员自己不写读偏移，而是把偏移交给一个
    # 共享助手（`PushPlayerUintOrZero(state, handle, offset)` 之类）。第一版漏了这几个，
    # 于是 `EntityPlayer:GetTrinket` 被误报成桩 —— 它是真实现（`PushPlayerUintOrZero(...)`）。
    "PushPlayerUintOrZero(",
    "PushEntityPlayerCounter(",
    "PushEntityField(",
    "PushEntityPickupField(",
    "PushItemField(",
    "PushRoomDescriptor(",
)

_CATALOG_ROW = re.compile(
    r"\{MakeId\(ApiDomain::(\w+), (\d+), (0x[0-9A-Fa-f]+)\),\s*ApiDomain::\w+,\s*"
    r"\"([^\"]+)\",\s*\"([^\"]+)\"")
_BINDING_ROW = re.compile(r"\{(0x[0-9A-Fa-f]{8}),\s*&(\w+)\}")


def strip_comments(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return re.sub(r"//[^\n]*", "", text)


def catalog_entries() -> dict[int, tuple[str, str]]:
    """绑定键（`0x0E010039` 这种 8 位十六进制）→ `(owner, name)`。"""
    text = strip_comments(CATALOG.read_text(encoding="utf-8"))
    domain_bytes = {"Isaac": 0x0E, "Global": 0x00, "Game": 0x02, "Level": 0x03, "Room": 0x04,
                    "ItemPool": 0x05, "MusicManager": 0x06, "RNG": 0x07, "Persistence": 0x08,
                    "Input": 0x09, "Font": 0x0A, "Sprite": 0x0B, "Mod": 0x01, "ModMenu": 0x0C,
                    "Vector": 0x0D, "Color": 0x0F, "GridEntity": 0x10, "PlayerManager": 0x11,
                    "Entity": 0x12, "EntityPlayer": 0x13, "EntityPickup": 0x14,
                    "EntityFamiliar": 0x15, "ItemConfig": 0x16, "ItemConfig_Item": 0x17}
    entries: dict[int, tuple[str, str]] = {}
    for domain, version, ordinal, owner, name in _CATALOG_ROW.findall(text):
        key = (domain_bytes.get(domain, 0x00) << 24) | (int(version) << 16) | int(ordinal, 16)
        entries[key] = (owner, name)
    return entries


def bindings() -> dict[int, str]:
    """绑定键 → 处理器函数名（扫全部家族 TU）。"""
    out: dict[int, str] = {}
    for source in sorted(LUA_DIR.glob("*.cpp")):
        text = strip_comments(source.read_text(encoding="utf-8"))
        for key, handler in _BINDING_ROW.findall(text):
            out.setdefault(int(key, 16), handler)
    return out


def handler_bodies() -> dict[str, str]:
    """处理器名 → 函数体（剥掉注释）。用"行首 `}`"当结束标记 —— 与本仓库其它文本门禁同一形态。"""
    out: dict[str, str] = {}
    for source in sorted(LUA_DIR.glob("*.cpp")):
        text = strip_comments(source.read_text(encoding="utf-8"))
        for match in re.finditer(r"^int (\w+)\(lua_State\* state\) \{", text, re.M):
            name = match.group(1)
            end = text.find("\n}", match.end())
            out[name] = text[match.end():end if end != -1 else len(text)]
    return out


def classify_bodies() -> dict[str, str]:
    """处理器名 → `stub` / `real` / `unknown`。"""
    verdicts: dict[str, str] = {}
    for name, body in handler_bodies().items():
        if not any(marker in body for marker in STUB_MARKERS):
            verdicts[name] = "real"
            continue
        verdicts[name] = "stub" if not any(m in body for m in REAL_MARKERS) else "real"
    return verdicts


def survey() -> dict[str, dict]:
    """当前源码里"有绑定行 + 判成桩"的全部条目。"""
    entries = catalog_entries()
    bound = bindings()
    verdicts = classify_bodies()
    rows: dict[str, dict] = {}
    for key, handler in bound.items():
        entry = entries.get(key)
        if entry is None:
            continue
        owner, name = entry
        verdict = verdicts.get(handler, "unknown")
        if verdict != "stub":
            continue
        rows[f"{owner}:{name}"] = {
            "owner": owner,
            "name": name,
            "handler": handler,
            "binding_key": f"0x{key:08X}",
        }
    return rows


def load_ledger() -> dict:
    if LEDGER.is_file():
        return json.loads(LEDGER.read_text(encoding="utf-8"))
    return {"schema": "isaac-lua-api-stub-ledger/1", "rows": {}}


def main() -> int:
    parser = argparse.ArgumentParser(description="接口台账的安全桩检查器")
    parser.add_argument("--write", action="store_true", help="重新生成 tools/lua_api_stub_ledger.json")
    parser.add_argument("--strict", action="store_true", help="有任何漂移或无理由的条目就非零退出")
    args = parser.parse_args()

    found = survey()
    ledger = load_ledger()
    known: dict[str, dict] = ledger.get("rows", {})

    new = sorted(set(found) - set(known))
    gone = sorted(set(known) - set(found))
    # 台账里每条都必须带 `note`（"为什么它是桩、要修它得先取证什么"）——
    # 与回调面那份台账同一口径：分类必须写清依据，不能只留一个名字。
    unsubstantiated = sorted(k for k, row in known.items() if not row.get("note"))

    if args.write:
        for key, row in found.items():
            merged = dict(known.get(key, {}))
            merged.update(row)
            merged.setdefault("note", "")
            known[key] = merged
        for key in gone:
            known.pop(key, None)
        ledger["rows"] = known
        ledger["source"] = "runtime/src/interfaces/lua/*.cpp（绑定行 + 处理器函数体）"
        ledger["criteria"] = (
            "处理器体（剥掉注释）含 PushZero/WarnStubOnce、且不含任何引擎读取标记 ⇒ 判桩；"
            "其余判真实现；找不到函数体判 unknown（不猜）"
        )
        LEDGER.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"已写入 {LEDGER.relative_to(ROOT)}（{len(known)} 条）")

    print(f"\n接口台账里的安全桩：**{len(known)}** 条"
          f"（本轮源码里认出 {len(found)} 条）")
    for key in sorted(known):
        row = known[key]
        print(f"  {key:38s} {row.get('handler', ''):38s} {row.get('note', '（缺理由）')[:40]}")
    if new:
        print(f"\n★ 新增（源码里是桩、台账里没有）：{new}")
    if gone:
        print(f"\n★ 已消失（台账里有、源码里已不是桩）：{gone}")
    if unsubstantiated:
        print(f"\n★ 缺理由的条目：{unsubstantiated}")

    if args.strict:
        problems = []
        if new:
            problems.append(f"台账没跟上源码（新增 {new}）")
        if gone:
            problems.append(f"台账落后于源码（已修好但没销账 {gone}）")
        if unsubstantiated:
            problems.append(f"这些条目没写理由：{unsubstantiated}")
        if problems:
            print("\n".join(problems))
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
