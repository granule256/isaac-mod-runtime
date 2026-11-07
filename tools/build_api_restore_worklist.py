#!/usr/bin/env python3
"""生成 Lua API 恢复工作清单及汇总报告。

合并模组缺口、接口目录、PC 契约和运行时接收者信息，区分可复用的数据驱动
绑定、需要原生调用的接口及证据不足的条目。检查模式用于核对清单完整性。
"""

from __future__ import annotations

import argparse
import collections
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
RUNTIME_LUA = ROOT / "runtime" / "src" / "interfaces" / "lua"
CONTRACT_DOCS = ROOT / "tools" / "pc_contract_docs"
INVENTORY = ROOT / "analysis" / "lua-api-inventory" / "inventory.json"

#: 走 `x8` 间接结果寄存器的 16 字节值类型 —— 引擎调用跳板**不支持**这类返回
#: （`docs/加一个Lua-API-的做法.md` 第 3 节的「能力边界」）。
STRUCT_RETURN_TYPES = {"Vector", "KColor"}

#: PC 契约里返回值是容器/对象（要做表或句柄），单独一档。
TABLE_RETURN_TYPES = {
    "EntityList", "table", "RNG", "Sprite", "Entity", "GridEntity", "RoomDescriptor",
    "EntityPlayer", "ItemConfig_Item", "HUD", "Seeds", "MusicManager",
}

#: 契约页里这些"返回类型"其实就是标量，只是文档写成了类名/枚举名。
SCALAR_ALIASES = {
    "int", "float", "boolean", "bool", "string", "void",
    "CollectibleType", "Card", "TrinketType", "PillEffect", "EntityType", "EntityVariant",
    "RoomType", "RoomShape", "RenderMode", "BackdropType", "GridCollisionClass",
    "DoorSlot", "Direction", "SoundEffect", "Music", "SeedEffect", "LevelStage",
    "StageType", "Difficulty", "PlayerType", "Challenge", "ItemPoolType", "PickupVariant",
    "CacheFlag", "EntityFlag", "DamageFlag", "ButtonAction", "GridRooms", "Dim",
    "ControllerIndex", "PlayerForm", "ActiveSlot", "WeaponType", "EffectVariant",
}

HUMAN_ORDER = [
    "engine_row",            # 数据行：接收者+形状都现成
    "field_row",             # 数据行：读接收者的固定偏移
    "glue_compose",          # 用现成原语自己拼（名字表 / 下转 / 回调表）
    "needs_new_shape",       # 差一种新签名的"形状能力"
    "needs_struct_return",   # 差"16 字节结构体返回"能力（跳板不支持）
    "needs_new_receiver",    # 差接收者视图
    "needs_forensics",       # 无引擎入口，要先反汇编定性（内联 / 字段 / 真没有）
    "blocked_decision",      # 语义要人为裁定（渲染、控制台输出）
]

#: G1 闸门「确认是伪缺口」的**结案名单**：人工核过 ⇒ **不进待办清单**。
#:
#: 纪律（流水线 G1）：确认是伪缺口的**要划掉并写明理由，不许悄悄销账** —— 所以理由写在这里，
#: 而不是简单地把条目从报告里删掉。判据形态：运行时其实已经能答，只是**实现不走
#: `api_catalog.cpp`**（`tools/mod_api_gap_report.py` 只读 catalog ⇒ 看不见）。
#: 派生 owner 的方法会自动消失，不必登记在这里（实测）：`mod_api_gap_report.py`
#: 解析模组的缺口时会**沿 owner 的继承链**看基类 —— 一旦我们给基类 owner 加了实现
#: （例如 `GridEntity:GetSprite`），清单里那条**派生 owner** 的行（`GridEntityRock:GetSprite`）
#: 就**自己**不见了（两条各记 14 处、同一个模组、同一个接收者写法）。所以那一类"同方法名、
#: 不同 owner"的行**不需要**写进这张表 —— 写了也不会出现在报告里（这张表只对"仍在缺口里、
#: 但人工核过其实能用"的条目生效）。
#: `needs_new_receiver` 那个桶里混着「虚函数」—— 读它的时候要留神（实测）：
#: 桶的标签是「引擎方法行要一个能取到 this 的 receipt」，但至少三条**不是**差接收者，而是
#: **虚函数**（项目纪律：引擎方法行要求「同名方法**只有一个类实现**」）：
#:
#:   * `GridEntity:Destroy(bool)` —— 3 份实现（`GridEntity` / `_Door` / `_Rock`）；
#:   * `GridEntity:PostInit()`    —— 4 份（`GridEntity` / `_Gravity` / `_Pit` / `_Poop`）；
#:   * `Entity:CanShutDoors()` / `EntityNPC:CanShutDoors()` —— 5+ 份，而且PC 的绑定本体
#:     本来就是走 vtable 的（`mov eax,[ecx]` 之后 `call [eax+0x44]` 一类）⇒ 直调基类会
#:     **跳过子类行为**、与 PC 不一致（例如石头 `Destroy` 不喷掉落物）。
#:
#: ⇒ 这几条（合 13 处）的正确出路是给引擎方法行加**「按 vtable 槽号调用」**的支持 ——
#:   槽号能从 vtable 数据直接读出来（在 `_ZTV<类>` 块里找基类实现的地址、算槽下标），
#:   所以那会是一条证据充分的新机制；**不是**补接收者能解决的。
#: 判断办法：`python3 tools/mangled_impl_count.py <方法名>` 看看有几份实现；
#:   ≥2 份就到 PC 侧看那条绑定是不是 `call [eax+偏移]`（虚调）。
CONFIRMED_PSEUDO_GAPS: dict[str, str] = {
    "Vector:__sub": (
        "运行时的 `Vector` 元表**早就挂了 `__sub`**（`runtime/source/lua_runtime.cpp` 的 "
        "`RegisterVectorApi`），且 `VectorIndex`（`runtime/src/interfaces/lua/vector_api.cpp`）"
        "对 `__` 开头的键**直接从元表取同一个函数对象** —— 这是 2026-09-12 为真机报告 "
        "`01789211254` 专门加的（EID 两种写法都用：`pos - other` 与 `pos:__sub(other)`）。"
        "⇒ `Vector:__sub` 现在**就能用**，不需要新增任何东西（批次 261 复核）。"
    ),
    "GridEntityDoor:IsOpen": (
        "批次 079 起就是**真实现**：门的 `__index`（`runtime/src/interfaces/lua/remaining_api.cpp`）"
        "对键 `IsOpen` 直接返回处理器 `GridEntityDoorIsOpen`（同一个位置还有 `Position`/`Desc`/"
        "`VarData` 等字段）。实现在 `api_catalog.cpp` 里**没有目录行**（它不走 catalog、也不走"
        "数据行）⇒ 缺口报告看不见。★ 顺带说明这条为什么必须留在这里："
        "批次 078 曾把它误做成**布尔字段**，模组按方法调用时是 attempt to call a boolean value，"
        "`rules.lua:12` 的 `check_room_open()` 就是这么把整条规则回调打断的（批次 079 已修）。"
    ),
}


# --------------------------------------------------------------------------- #
# 输入
# --------------------------------------------------------------------------- #

def load_corpus_gap_reports() -> tuple[dict, list[str]]:
    """把 17 个语料模组的 `missing_in_runtime` 去重成 {api: 聚合}。

    ★ 去重键是 `api`（形如 `Entity:ToNPC`）；同一个 API 被不同接收者调用会有多行，
      因此调用点求和、模组数**按模组去重**（早先按行数累加会得出 18 > 17 个模组的荒谬数字）。
    """
    agg: dict[str, dict] = {}
    labels: list[str] = []
    for path in sorted(DIST.glob("*-api-gap-report.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        mod = data.get("mod", "")
        if not mod.startswith("analysis/mod-corpus/"):
            continue
        label = data.get("label") or path.name
        labels.append(label)
        for row in data.get("missing_in_runtime", []):
            api = row.get("api")
            if not api:
                continue
            slot = agg.setdefault(api, {"mods": set(), "calls": 0, "called_as": set()})
            slot["mods"].add(label)
            slot["calls"] += int(row.get("calls") or 0)
            if row.get("called_as"):
                slot["called_as"].add(row["called_as"])
    return agg, sorted(set(labels))


def load_inventory() -> dict[str, dict]:
    if not INVENTORY.exists():
        sys.exit(
            f"缺 {INVENTORY.relative_to(ROOT)}：它是 gitignore 的本机产物，"
            "先跑 `python3 tools/build_lua_api_inventory.py`。"
        )
    data = json.loads(INVENTORY.read_text(encoding="utf-8"))
    return {a["key"]: a for a in data.get("apis", [])}


def contract_pages() -> dict[str, list[str]]:
    return {
        p.stem: p.read_text(encoding="utf-8", errors="replace").splitlines()
        for p in CONTRACT_DOCS.glob("*.md")
    }


DOC_LINE = re.compile(r"^####\s+(?P<ret>.+?)\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*\((?P<args>.*)\)")


def parse_return_type(raw: str) -> str:
    """把契约页那一行的返回类型规范化成裸名字（去掉 Markdown 链接与枚举路径）。"""
    raw = raw.strip()
    m = re.match(r"\[([^\]]+)\]\(([^)]*)\)", raw)
    if m:
        return m.group(1).strip()
    return raw


def lookup_contract(pages: dict[str, list[str]], owner: str, name: str) -> dict:
    """去契约页里找这条 API：返回类型 + 参数表 + `页:行号`。

    找不到就如实报 `found: False`（流水线第 2 道闸门要求先把它补齐）。
    """
    lines = pages.get(owner)
    if lines is None:
        return {"found": False, "reason": f"没有 {owner}.md 契约页"}
    hits: list[dict] = []
    for idx, line in enumerate(lines, start=1):
        m = DOC_LINE.match(line)
        if not m or m.group("name") != name:
            continue
        ret = parse_return_type(m.group("ret"))
        args = [a.strip() for a in m.group("args").split(",") if a.strip()]
        hits.append({"line": idx, "return_type": ret, "args": args, "raw": line.strip()})
    if not hits:
        return {"found": False, "reason": f"{owner}.md 里没有 {name} 的 `####` 签名行"}
    first = hits[0]
    return {
        "found": True,
        "page": f"tools/pc_contract_docs/{owner}.md",
        "line": first["line"],
        "return_type": first["return_type"],
        "doc_arity": len(first["args"]),
        "overloads": len(hits),
        "raw": first["raw"],
    }


# --------------------------------------------------------------------------- #
# 运行时代码里的"接收者到底在不在"（可复核的事实，不用手维护白名单）
# --------------------------------------------------------------------------- #

def runtime_receiver_evidence() -> dict[str, str]:
    """扫运行时代码，得出每个 owner 的接收者状态。

    判据（任一条命中即算有）：
      * `FieldReceipt::<Owner>`       —— 引擎方法数据行可以直接用它取 `this`
      * `k<Owner>Metatable` / `<Owner>Handle` —— 该族的句柄/元表已经存在
    """
    evidence: dict[str, str] = {}
    sources = list(RUNTIME_LUA.glob("*.hpp")) + list(RUNTIME_LUA.glob("*.cpp"))
    blob = "\n".join(p.read_text(encoding="utf-8", errors="replace") for p in sources)

    for owner in sorted(set(re.findall(r"FieldReceipt::([A-Za-z_][A-Za-z0-9_]*)", blob))):
        if owner in ("Entity", "EntityPlayer"):
            evidence[owner] = "FieldReceipt + 句柄视图"
        else:
            evidence[owner] = "FieldReceipt"
    for mt in sorted(set(re.findall(r"k([A-Za-z_][A-Za-z0-9_]*)Metatable", blob))):
        if mt in evidence:
            continue
        evidence[mt] = "元表"
    for handle in sorted(set(re.findall(r"\b([A-Za-z_][A-Za-z0-9_]*)Handle\b", blob))):
        evidence.setdefault(handle, "句柄")
    return evidence


#: `strcmp(<expr>, "名字")` —— 这是 `__index` 里的**名字分派**：它既不在 `api_catalog.cpp`
#: 里、也不是数据行，`tools/mod_api_gap_report.py`（只读 catalog）**完全看不见它**。
#: 教训：→201 的 `EntityPickup:IsShopItem` 与 `GridEntityDoor.IsOpen` 都属这一类，
#: 「工具说缺、其实早就能用」。所以清单的第 1 道闸门必须把它扫出来。
STRCMP_DISPATCH = re.compile(r'strcmp\s*\(\s*[^,]+,\s*"([A-Za-z_][A-Za-z0-9_]*)"\s*\)')

#: `lua_setfield(state, -2, "__sub")` —— **元表上的运算符/协议字段**。
#:
#: 为什么也要扫（补）：`Vector:__sub` 在待办清单里挂了很久，但运行时的 `Vector`
#: **元表上早就挂着 `__sub`**，而且 `VectorIndex` 对 `__` 开头的键**直接从元表取函数对象**
#: （`vector_api.cpp`，2026-09-12 为真机报告 `01789211254` 加的）⇒ `v:__sub(other)` 与
#: `v - other` 语义完全一致、**不需要新增任何东西**。它与 `strcmp` 那一类是同一个毛病
#: （实现不走 catalog ⇒ 缺口报告看不见），只是判据形态不同。
METATABLE_FIELD = re.compile(r'lua_setfield\s*\([^,]+,\s*-2\s*,\s*"(__[A-Za-z]+)"\s*\)')


def runtime_dispatched_names() -> dict[str, list[str]]:
    """收集 `__index` 分派 / 元表字段里出现过的名字 → 证据位置。"""
    found: dict[str, list[str]] = {}
    for path in list(RUNTIME_LUA.glob("*.cpp")) + list(RUNTIME_LUA.glob("*.hpp")):
        text = path.read_text(encoding="utf-8", errors="replace")
        for idx, line in enumerate(text.splitlines(), start=1):
            for pattern in (STRCMP_DISPATCH, METATABLE_FIELD):
                for name in pattern.findall(line):
                    found.setdefault(name, []).append(f"{path.name}:{idx}")
    # 元表字段也可能注册在 `lua_runtime.cpp`（`RegisterVectorApi` 那一族在那里）。
    for path in sorted((ROOT / "runtime" / "source").glob("*.cpp")):
        text = path.read_text(encoding="utf-8", errors="replace")
        for idx, line in enumerate(text.splitlines(), start=1):
            for name in METATABLE_FIELD.findall(line):
                found.setdefault(name, []).append(f"{path.name}:{idx}")
    return found


# --------------------------------------------------------------------------- #
# 判定
# --------------------------------------------------------------------------- #

def classify(entry: dict, inv: dict, contract: dict, receivers: dict) -> dict:
    owner, _, name = entry_key_parts(inv["key"])
    category = inv.get("category") or "unknown"
    reason = inv.get("reason_code") or ""
    readi = inv.get("thunk_readiness") or ""
    switch = inv.get("switch") or {}

    ret = contract.get("return_type") if contract.get("found") else None
    ret_class = "unknown"
    if contract.get("found"):
        if ret in STRUCT_RETURN_TYPES:
            ret_class = "struct16"
        elif ret in SCALAR_ALIASES:
            ret_class = "scalar"
        elif ret in TABLE_RETURN_TYPES:
            ret_class = "table_or_handle"
        else:
            ret_class = "unknown"

    mech = "needs_forensics"
    why = ""

    if category == "missing_easy" and readi == "ready":
        if ret_class == "struct16":
            mech, why = "needs_struct_return", (
                f"返回 {ret}（16 字节值类型，走 x8 间接结果寄存器）"
                "—— 引擎调用跳板只支持标量返回，必须手写或先扩跳板"
            )
        elif ret_class in ("table_or_handle", "unknown"):
            mech, why = "needs_forensics", f"返回类型 {ret or '未知'} 需要先定性（表/句柄/标量）"
        else:
            mech, why = "engine_row", "接收者 + 形状都现成，16 字节数据行、0 代码"
    elif category == "missing_easy" and readi == "needs_arg_marshalling":
        mech, why = "needs_new_shape", "参数里含向量/枚举/字符串等非基本类型，要先扩一种形状能力"
    elif category == "missing_easy":
        mech, why = "needs_new_receiver", "差接收者视图（引擎方法行要一个能取到 this 的 receipt）"
    elif reason in ("struct_field_layout", "accessor_heuristic"):
        mech, why = "field_row", "引擎里没有同名访问器 ⇒ 先取证字段偏移，再走字段数据行"
    elif reason in ("lua_glue_type", "mod_loading_unavailable"):
        mech, why = "glue_compose", "PC 在 Lua 胶水层实现 ⇒ 用现成原语自己拼（名字表/下转/回调表）"
    elif reason == "no_symbol":
        mech, why = "needs_forensics", "符号表里没有 ⇒ 先反汇编定性（内联 / 字段 / 真没有）"
    elif reason == "render_glue":
        mech, why = "blocked_decision", "渲染/字体胶水 ⇒ 要人为裁定做不做、做到什么程度"
    else:
        mech, why = "needs_forensics", f"未分类原因码 {reason!r}"

    if owner in ("Entity", "EntityPlayer", "Room", "Level", "Game", "ItemPool", "MusicManager"):
        recv = receivers.get(owner, "（FieldReceipt 未列出）")
    else:
        recv = receivers.get(owner)

    return {
        "api": inv["key"],
        "owner": owner,
        "name": name,
        "mods": sorted(entry["mods"]),
        "mod_count": len(entry["mods"]),
        "calls": entry["calls"],
        "category": category,
        "reason_code": reason or None,
        "thunk_readiness": readi or None,
        "mechanism": mech,
        "why": why,
        "engine_offset": switch.get("offset"),
        "engine_offset_hex": switch.get("offset_hex"),
        "mangled": switch.get("mangled"),
        "guard16": switch.get("guard16"),
        "symbol_arity": switch.get("arity"),
        "pc_page": contract.get("page"),
        "pc_line": contract.get("line"),
        "pc_return": ret,
        "pc_return_class": ret_class,
        "pc_arity": contract.get("doc_arity"),
        "pc_signature": contract.get("raw") if contract.get("found") else None,
        "contract_found": bool(contract.get("found")),
        "contract_note": contract.get("reason"),
        "receiver_evidence": recv,
    }


def entry_key_parts(key: str) -> tuple[str, str, str]:
    owner, _, name = key.partition(":")
    return owner, ":", name


def gate_check(row: dict) -> list[str]:
    """逐条列出它**还要过哪几道闸门**（给执行的人当 checklist）。"""
    gates: list[str] = []
    if not row["contract_found"]:
        gates.append("G2 契约：先把 PC 契约页补齐并抄原文（写不出 页:行号 就别动代码）")
    if row["pc_arity"] is not None and row["symbol_arity"] is not None:
        if row["pc_arity"] != row["symbol_arity"]:
            gates.append(
                f"G3 形状：文档参数 {row['pc_arity']} 个 vs 符号 {row['symbol_arity']} 个"
                "—— 按符号签名取（默认参数照样占寄存器）"
            )
    # 返回 16 字节值类型是跨桶的闸门：不管它在哪个桶里，都不能走引擎方法数据行。
    if row["pc_return_class"] == "struct16" and row["mechanism"] != "blocked_decision":
        gates.append(
            f"G3 能力：返回 {row['pc_return']}（16 字节、x8 间接结果寄存器）"
            "—— 跳板不支持，必须手写或先扩跳板"
        )
    if row["mechanism"] in ("field_row", "needs_forensics"):
        gates.append("G4 取证：反汇编定位偏移/入口，并写出互证点")
    if row["mechanism"] in ("needs_new_shape", "needs_struct_return", "needs_new_receiver"):
        gates.append("G3 能力：先补「一种能力」（形状 / 返回种类 / 接收者），再挂条目")
    gates.append("G5 记账：目录行 id 取域内下一个空号 + 四处计数/台账同步")
    gates.append("G6 验证：定向 --only + 宿主 ABI；真值只能真机")
    return gates


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--print", dest="print_only", action="store_true", help="只打印汇总，不写文件")
    args = ap.parse_args()

    agg, labels = load_corpus_gap_reports()
    if not agg:
        sys.exit("没有找到语料模组的缺口报告（dist/*-api-gap-report.json 且 mod 以 analysis/mod-corpus/ 开头）")
    inv = load_inventory()
    pages = contract_pages()
    receivers = runtime_receiver_evidence()
    dispatched = runtime_dispatched_names()

    rows: list[dict] = []
    missing_inv: list[str] = []
    confirmed_pseudo: list[str] = []
    for api, entry in agg.items():
        meta = inv.get(api)
        if meta is None:
            missing_inv.append(api)
            continue
        # G1 结案名单：人工核过是伪缺口 ⇒ 从清单里划掉（理由写在 `CONFIRMED_PSEUDO_GAPS`，
        #   不许悄悄销账）。进这里的必须先在名单里写明判据。
        if api in CONFIRMED_PSEUDO_GAPS:
            confirmed_pseudo.append(api)
            continue
        contract = lookup_contract(pages, meta["owner"], meta["name"])
        row = classify(entry, meta, contract, receivers)
        # G1 闸门：这个名字在运行时的 `__index` 分派里出现过吗？
        # 出现 ⇒ 可能**早就能用**（缺口报告只读 catalog，看不见分派）⇒ 必须先人工确认。
        hits = dispatched.get(meta["name"], [])
        if hits:
            row["dispatch_evidence"] = hits[:4]
            row["pseudo_gap_suspect"] = True
        else:
            row["dispatch_evidence"] = []
            row["pseudo_gap_suspect"] = False
        row["gates"] = gate_check(row)
        if row["pseudo_gap_suspect"]:
            row["gates"].insert(
                0,
                "G1 伪缺口：这个名字在 __index 分派里出现过"
                " —— 先确认是不是同一个族（很可能「早就能用」）",
            )
        rows.append(row)

    rows.sort(key=lambda r: (HUMAN_ORDER.index(r["mechanism"])
                             if r["mechanism"] in HUMAN_ORDER else 99,
                             -r["calls"], r["api"]))

    by_mech = collections.Counter(r["mechanism"] for r in rows)
    by_mech_calls = collections.Counter()
    for r in rows:
        by_mech_calls[r["mechanism"]] += r["calls"]

    print(f"语料模组（{len(labels)} 个）：{', '.join(labels)}")
    print(f"去重缺口 API = {len(rows)} 条；调用点合计 = {sum(r['calls'] for r in rows)}")
    if missing_inv:
        print(f"⚠ 不在库存里的 {len(missing_inv)} 条（需人工看）：{missing_inv[:8]}")
    print()
    header = f"{'机制':<22}{'条数':>6}{'调用点':>8}  说明"
    print(header)
    print("-" * len(header))
    for mech in HUMAN_ORDER:
        if mech not in by_mech:
            continue
        sample = next(r["why"] for r in rows if r["mechanism"] == mech)
        print(f"{mech:<22}{by_mech[mech]:>6}{by_mech_calls[mech]:>8}  {sample[:44]}")
    unknown = [m for m in by_mech if m not in HUMAN_ORDER]
    for mech in unknown:
        print(f"{mech:<22}{by_mech[mech]:>6}{by_mech_calls[mech]:>8}")
    print()
    print("契约页缺失（第 2 道闸门要补）=", sum(1 for r in rows if not r["contract_found"]))
    print("返回 16 字节值类型（跳板不支持，必须手写）=",
          sum(1 for r in rows if r["pc_return_class"] == "struct16"))
    print("文档参数个数 ≠ 符号参数个数（G3 会拦）=",
          sum(1 for r in rows if r["pc_arity"] is not None and r["symbol_arity"] is not None
              and r["pc_arity"] != r["symbol_arity"]))
    print(f"G1 已结案伪缺口（人工核过、已划掉）={len(confirmed_pseudo)}"
          + (f"：{', '.join(sorted(confirmed_pseudo))}" if confirmed_pseudo else ""))
    suspect = [r for r in rows if r["pseudo_gap_suspect"]]
    print(f"G1 伪缺口嫌疑（名字出现在 __index 分派 / 元表字段里）={len(suspect)}")
    for r in sorted(suspect, key=lambda x: -x["calls"])[:10]:
        print(f"    {r['api']:42s} {r['calls']:3d} 处   证据 {r['dispatch_evidence'][0]}")

    if args.print_only:
        return 0

    out_json = DIST / "api-restore-worklist.json"
    out_json.write_text(json.dumps({
        "schema": "isaac-api-restore-worklist/1",
        "note": "由 tools/build_api_restore_worklist.py 生成；判据与闸门见 docs/批量恢复API的流水线.md。"
                "★ 只决定往哪个桶里放，不代替任何一步取证。",
        "corpus_mods": labels,
        "api_count": len(rows),
        "call_sites": sum(r["calls"] for r in rows),
        "by_mechanism": dict(by_mech),
        "confirmed_pseudo_gaps": {
            api: CONFIRMED_PSEUDO_GAPS[api] for api in sorted(confirmed_pseudo)
        },
        "rows": rows,
    }, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    lines = [
        "# 批量恢复 API · 待办清单（生成物，勿手改）",
        "",
        f"- 语料模组：{len(labels)} 个",
        f"- 去重缺口 API：**{len(rows)}** 条；调用点合计 **{sum(r['calls'] for r in rows)}**",
        "- 生成器：`tools/build_api_restore_worklist.py`；判据见 `docs/批量恢复API的流水线.md`",
        "",
        "| 机制 | 条数 | 调用点 | 走法 |",
        "| --- | --- | --- | --- |",
    ]
    for mech in HUMAN_ORDER:
        if mech not in by_mech:
            continue
        sample = next(r["why"] for r in rows if r["mechanism"] == mech)
        lines.append(f"| `{mech}` | {by_mech[mech]} | {by_mech_calls[mech]} | {sample} |")
    lines.append("")
    if confirmed_pseudo:
        lines += ["## G1 已结案伪缺口（人工核过 ⇒ **已从清单划掉**）", "",
                  "判据与理由写在生成器的 `CONFIRMED_PSEUDO_GAPS`（**不许悄悄销账**）。", "",
                  "| API | 为什么不需要做 |", "| --- | --- |"]
        for api in sorted(confirmed_pseudo):
            lines.append(f"| `{api}` | {CONFIRMED_PSEUDO_GAPS[api]} |")
        lines.append("")
    suspect = [r for r in rows if r["pseudo_gap_suspect"]]
    if suspect:
        lines += ["## G1 伪缺口嫌疑（先确认再动手，可能「早就能用」）", "",
                  "| API | 调用点 | 名字分派证据 |", "| --- | --- | --- |"]
        for r in sorted(suspect, key=lambda x: -x["calls"]):
            lines.append(f"| `{r['api']}` | {r['calls']} | {', '.join(r['dispatch_evidence'])} |")
        lines.append("")
    for mech in HUMAN_ORDER:
        group = [r for r in rows if r["mechanism"] == mech]
        if not group:
            continue
        lines += [f"## {mech}（{len(group)} 条）", "",
                  "| API | 模组 | 调用点 | 返回 | 引擎偏移 | 接收者 |",
                  "| --- | --- | --- | --- | --- | --- |"]
        for r in group:
            off = r["engine_offset_hex"] or "—"
            recv = r["receiver_evidence"] or "—"
            lines.append(
                f"| `{r['api']}` | {r['mod_count']} | {r['calls']} | {r['pc_return'] or '?'} | {off} | {recv} |"
            )
        lines.append("")
    (DIST / "api-restore-worklist.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print()
    print(f"已写：{out_json.relative_to(ROOT)}")
    print(f"已写：{(DIST / 'api-restore-worklist.md').relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
