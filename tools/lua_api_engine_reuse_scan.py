#!/usr/bin/env python3
"""审查第 3~5 遍用的**只读复核器**：把"我们自己写的 Lua 接口"与"引擎符号表里其实有的成员函数"
对到一起，回答用户 2026-09-27 定的那个判据 —— **"引擎里其实有、我们却自己又写了一遍"**。

## 为什么要有它

用户 2026-09-27 的判定：模组加载与模组页面这两个问题，都是**我们自己另写一套去"还原 PC 的样子"**，
而没有直接遵循 PC 的写法、复用 NS 上剩下的代码。审查要逐条回答三句：
① 引擎里现成的入口是哪个（符号 + 地址）？② 为什么不能直接调？③ 能调的话代价是什么？

第 1~2 遍是**人工**在 `docs/审查-自己实现vs复用引擎-20260927.md` 里逐条写。
第 3 遍（Lua 接口面）一上手就发现：**553 条接口不可能靠肉眼看** —— 而引擎符号表
（`Repentance.nro` 的 `.dynsym`，16998 条、其中 IsaacRepentance/KAGE 方法 6508 条）
本身就是**权威真值源**。本工具把"我们实现的接口"与"引擎的同名方法"机械地对起来，
把人力集中在**真正对上的那几十条**上。

## 它做什么（三段，全部只读）

1. **解出"我们实现的接口"**：读 `api_catalog.cpp` 的目录行（`MakeId(域, ownerGroup, 序号)`
   → 8 位 id）与各家族 TU 的绑定表（`{0xNNNNNNNN, &Handler}`），得到 `id -> (owner, name, handler)`。
2. **解出"处理器正文**长什么样**"**：剥掉注释后取每个 `int Handler(lua_State* state) { ... }` 的函数体，
   用与 `tools/lua_api_stub_report.py` **同一套词表**判"它碰不碰引擎"（`REAL_MARKERS`）
   与"它是不是恒值桩"（`STUB_MARKERS` + 恒假布尔/恒零整数/恒 nil）。
   —— 口径**刻意复用**那份工具，不另立一套（098 的教训：两套判据会漂移）。
3. **解出"引擎里有没有同名成员函数"**：读 `Repentance.nro` 的 `.dynsym`，`llvm-cxxfilt -n` 解混淆，
   建 `(类名, 方法名) -> [(偏移, 签名)]`。owner 名按 PC→C++ 的规范化（`EntityPlayer`→`Entity_Player`）
   与 `tools/build_lua_api_inventory.py` 的 `OWNER_ALIASES` 展开成候选类名，逐个试。

## 输出（判据）

| 判定 | 含义 | 该怎么处置 |
| --- | --- | --- |
| `stub+engine` | 我们是**恒值桩**，而引擎里**有同名成员函数** | ★ **最该做的一类**：直接照 `runtime_constants.hpp` 建常量 + 调引擎顶掉桩 |
| `stub-only` | 恒值桩，引擎里没有完全同名的方法 | 需要另找入口（字段偏移 / 近似名 / 引擎没有）⇒ 留在台账，逐条取证 |
| `real` | 已经真的碰引擎 / 不是恒值 | 正常，不用管 |
| `no-binding` | 有目录行但在绑定表里找不到处理器 | 数据行机制（`field_api.hpp` / `engine_method_api.hpp`）或 `unknown` ⇒ 不猜 |

## 用法

    python3 tools/lua_api_engine_reuse_scan.py              # 人读报告（按判定分组）
    python3 tools/lua_api_engine_reuse_scan.py --json       # 机器消费
    python3 tools/lua_api_engine_reuse_scan.py --only stub+engine

★ **只读**：本工具**不改任何文件**、不写台账（台账是 `tools/lua_api_stub_report.py --write` 的职责）。
   它存在的意义是"审查时能一条命令把靶子列出来"，而不是新增一份要维护的台账。
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOL_DIR = ROOT / "tools"
LUA_DIR = ROOT / "runtime" / "src" / "interfaces" / "lua"
CATALOG = LUA_DIR / "api_catalog.cpp"
NRO = (ROOT / "The Binding of Isaac_ Afterbirth+ 1.7.9b [010021C000B6A800][v524288][UPD]"
       / "Program #0" / "1" / ".nro" / "Repentance.nro")

sys.path.insert(0, str(TOOL_DIR))

#: 域字节 → 编号（与 `api_descriptor.hpp` 的 `enum class ApiDomain` 逐条一致）。
DOMAIN_BYTES = {
    "Global": 0, "Mod": 1, "Game": 2, "Level": 3, "Room": 4, "ItemPool": 5, "Music": 6,
    "Rng": 7, "Persistence": 8, "Input": 9, "Diagnostic": 10, "Font": 11, "Vector": 12,
    "Sprite": 13, "Isaac": 14, "Seed": 15, "ModMenu": 16,
    # 批次 207（2026-09-29）：`Hud`（域 17，`Game:GetHUD()` 的返回值）。真值源见
    # `runtime/src/interfaces/lua/api_descriptor.hpp` 的 `ApiDomain`。
    "Hud": 17,
}

#: 与 `tools/lua_api_stub_report.py` **逐字相同**的两份词表（刻意复制：审查口径要与台账口径一致；
#: 那份工具改了词表，这里要跟着改 —— 但**不许**在这里偷偷放宽，否则审查结论与台账会对不上）。
STUB_MARKERS = ("PushZero(", "WarnStubOnce(", "Stub::")
REAL_MARKERS = (
    "engine_memory::", "engine_call::", "ReadEngine(", "ReadEngineUnchecked(", "ReadCurrent",
    "ReadGame", "ObserveGame", "ObserveLevel", "Thunk(", "Method()", "ValidatedEntity",
    "ValidatedEntityPlayer", "CallRoomIntMethod", "ResolveEngine", "ResolveMusic",
    "IsEngineMemoryReadable(", "lua_pcallk(", "luaL_ref(", "PushPlayerUintOrZero(",
    "PushEntityPlayerCounter(", "PushEntityField(", "PushEntityPickupField(", "PushItemField(",
    "PushRoomDescriptor(",
)

#: 恒值标记（比台账多两条**布尔/整数**的恒假——台账的 `STUB_MARKERS` 原本只认
#: `PushZero(`/`Stub::`，于是 `EntityPlayer:HasPlayerForm`（`lua_pushboolean(state, 0)`）这类
#: 逃过了台账；2026-09-28 已把这两类补进台账词表，这里保持同步。
#: ★ 同一天（批次 177）本节列出的 7 条 `stub+engine` 靶子里，**5 条已改成引擎方法数据行**
#: （`EntityPlayer` 的 `GetPill`/`GetCard`/`GetZodiacEffect`/`HasPlayerForm`/`CanPickRedHearts`）
#: ⇒ 本扫描器的 `stub+engine` 一档应当只剩 **2 条**（`EntityPlayer:GetGlyphOfBalanceDrop` 与
#: `SFXManager:IsPlaying`，两条各自缺前置取证、理由见桩台账里的 `note`）。
#: 数字变了说明"又冒出来一条引擎里有、我们却恒返回假值的接口"—— 那正是要再查的信号。
#: **刻意不收 `lua_pushnil(state)`**："返回 nil" 常常是正确的语义（单人局的 `GetOtherTwin`），
#: 收进来会把真实现判成桩 —— 宁可漏、不可误，理由见 `lua_api_stub_report.py` 同处注释）。
CONST_VALUE_MARKERS = (
    "lua_pushboolean(state, 0)", "lua_pushboolean(state, 1)",
    "lua_pushinteger(state, 0)",
)

_CATALOG_ROW = re.compile(
    r'MakeId\(ApiDomain::(\w+),\s*(\d+),\s*(0x[0-9A-Fa-f]+)\),\s*ApiDomain::\w+,\s*'
    r'"([^"]+)"\s*,\s*"([^"]+)"')
_BINDING_ROW = re.compile(r"\{(0x[0-9A-Fa-f]{8}),\s*&(\w+)\}")
_HANDLER_START = re.compile(r"^int (\w+)\(lua_State\* state\) \{", re.M)
_TYPE_METHOD = re.compile(r"^(\w[\w:]*)::(\w+)\(", re.M)


def strip_comments(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return re.sub(r"//[^\n]*", "", text)


def catalog_entries() -> dict[int, tuple[str, str]]:
    """目录行 → `id -> (owner, name)`（`MakeId` 的编码在这里复现一次）。"""
    text = strip_comments(CATALOG.read_text(encoding="utf-8"))
    out: dict[int, tuple[str, str]] = {}
    for domain, group, sequence, owner, name in _CATALOG_ROW.findall(text):
        if domain not in DOMAIN_BYTES:
            continue
        identifier = (DOMAIN_BYTES[domain] << 24) | (int(group) << 16) | int(sequence, 16)
        out[identifier] = (owner, name)
    return out


def bindings() -> dict[int, str]:
    """绑定键 → 处理器名（扫全部家族 TU）。"""
    out: dict[int, str] = {}
    for source in sorted(LUA_DIR.glob("*.cpp")):
        text = strip_comments(source.read_text(encoding="utf-8"))
        for key, handler in _BINDING_ROW.findall(text):
            out.setdefault(int(key, 16), handler)
    return out


def handler_bodies() -> dict[str, str]:
    """处理器名 → 函数体（剥注释；用花括号配对取整段，比"行首 }"更稳）。"""
    out: dict[str, str] = {}
    for source in sorted(LUA_DIR.glob("*.cpp")):
        text = strip_comments(source.read_text(encoding="utf-8"))
        for match in _HANDLER_START.finditer(text):
            start = match.end() - 1
            depth, index = 0, start
            while index < len(text):
                if text[index] == "{":
                    depth += 1
                elif text[index] == "}":
                    depth -= 1
                    if depth == 0:
                        break
                index += 1
            out[match.group(1)] = text[start:index + 1]
    return out


#: 解混淆器候选（与 `tools/build_lua_api_inventory.py` 同一份，顺序一致）——
#: 对齐那份是为了"审查结论"与"PC-Lua-API 对照清单"解出同一批符号名。
_CXXFILT_CANDIDATES = (
    "/Applications/Xcode.app/Contents/Developer/Toolchains/XcodeDefault.xctoolchain/usr/bin/llvm-cxxfilt",
    "/usr/bin/llvm-cxxfilt",
    "/opt/homebrew/opt/llvm/bin/llvm-cxxfilt",
    "llvm-cxxfilt",
    "/usr/bin/c++filt",
)


def _cxxfilt() -> str | None:
    for candidate in _CXXFILT_CANDIDATES:
        found = shutil.which(candidate) if "/" not in candidate else (
            candidate if Path(candidate).is_file() else None)
        if found:
            return found
    return None


def engine_methods() -> dict[tuple[str, str], list[dict]]:
    """引擎 `(类名, 方法名) -> [(偏移, 签名, 是否已定义)]`。

    ★ 类名取**最内层**（`IsaacRepentance::Entity_Player::GetPill` → `Entity_Player`）——
    与审查里"PC owner → C++ 类名"的规范化对得上。
    """
    import nro_symbols  # 仓库内工具，仅 stdlib

    build, symbols = nro_symbols.parse_dynamic_symbols(NRO.read_bytes())
    mangled = [name for name in symbols if name.startswith("_Z")]
    filt = _cxxfilt()
    if filt is None:
        raise SystemExit("找不到 llvm-cxxfilt（Xcode 命令行工具）—— 解混淆需要它")
    demangled = subprocess.run(
        [filt, "-n"], input="\n".join(mangled), capture_output=True, text=True,
        check=True).stdout.splitlines()
    out: dict[tuple[str, str], list[dict]] = {}
    for name, pretty in zip(mangled, demangled):
        match = _TYPE_METHOD.match(pretty)
        if not match:
            continue
        klass = match.group(1).split("::")[-1]
        symbol = symbols[name]
        out.setdefault((klass, match.group(2)), []).append(
            {"offset": symbol.file_offset, "signature": pretty,
             "defined": symbol.is_defined, "build": build})
    return out


def owner_candidates(owner: str, aliases: dict[str, list[str]]) -> set[str]:
    """PC owner → 可能的 C++ 类名（规范化 + 别名表，与 `build_lua_api_inventory.py` 一致）。"""
    out = {owner, owner.replace(" ", "_")}
    out.add(re.sub(r"([a-z])([A-Z])", r"\1_\2", owner))
    for target in aliases.get(owner, []):
        out.add(target.split("::")[-1])
    return out


def load_aliases() -> dict[str, list[str]]:
    spec = importlib.util.spec_from_file_location(
        "build_lua_api_inventory", TOOL_DIR / "build_lua_api_inventory.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("build_lua_api_inventory", module)
    try:
        spec.loader.exec_module(module)
    except SystemExit:
        pass
    return dict(getattr(module, "OWNER_ALIASES", {}))


def survey() -> list[dict]:
    catalog = catalog_entries()
    bound = bindings()
    bodies = handler_bodies()
    engine = engine_methods()
    aliases = load_aliases()
    rows: list[dict] = []
    for identifier, (owner, name) in sorted(catalog.items()):
        handler = bound.get(identifier)
        body = bodies.get(handler) if handler else None
        if body is None:
            verdict = "no-binding"
            engine_hit = None
        else:
            touches_engine = any(marker in body for marker in REAL_MARKERS)
            is_constant = any(marker in body for marker in STUB_MARKERS) or any(
                marker in body for marker in CONST_VALUE_MARKERS)
            if touches_engine:
                verdict = "real"
            elif is_constant:
                verdict = "stub-only"
            else:
                verdict = "unknown"
            engine_hit = None
            for candidate in owner_candidates(owner, aliases):
                if (candidate, name) in engine:
                    first = engine[(candidate, name)][0]
                    engine_hit = {"class": candidate, "offset": first["offset"],
                                  "signature": first["signature"]}
                    break
            if verdict == "stub-only" and engine_hit:
                verdict = "stub+engine"
        rows.append({
            "id": f"0x{identifier:08X}", "owner": owner, "name": name,
            "handler": handler, "verdict": verdict, "engine": engine_hit,
        })
    return rows


VERDICT_HELP = {
    "stub+engine": "★ 我们是恒值桩，引擎里有同名成员函数 ⇒ 建常量 + 调引擎即可顶掉",
    "stub-only": "恒值桩，引擎里没有完全同名的方法 ⇒ 另找入口（字段/近似名）",
    "unknown": "不碰引擎又不是恒值标记 ⇒ 需人工看（可能是数据行/包装）",
    "no-binding": "有目录行但不在绑定表 ⇒ 数据行机制或未接线",
    "real": "已经真的碰引擎（正常）",
}


def print_report(rows: list[dict], only: str | None) -> None:
    from collections import Counter

    counts = Counter(row["verdict"] for row in rows)
    print(f"接口面复核：共 {len(rows)} 条 —— " + "、".join(
        f"{name} {counts[name]}" for name in VERDICT_HELP if counts[name]))
    for verdict in VERDICT_HELP:
        if only and verdict != only:
            continue
        group = [row for row in rows if row["verdict"] == verdict]
        if not group:
            continue
        print(f"\n=== [{verdict}] {VERDICT_HELP[verdict]}：{len(group)} 条 ===")
        for row in group:
            line = f"  {row['owner']}:{row['name']:34s} ({row['handler'] or '-'})"
            print(line)
            if row["engine"]:
                hit = row["engine"]
                print(f"      → 引擎 {hit['signature']}  @0x{hit['offset']:06X}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Lua 接口面：我们手写的 vs 引擎里现成的")
    parser.add_argument("--json", action="store_true", help="机器消费")
    parser.add_argument("--only", choices=list(VERDICT_HELP), help="只看某一类判定")
    arguments = parser.parse_args()
    rows = survey()
    if arguments.json:
        print(json.dumps({"rows": rows, "verdict_help": VERDICT_HELP},
                         ensure_ascii=False, indent=2))
    else:
        print_report(rows, arguments.only)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
