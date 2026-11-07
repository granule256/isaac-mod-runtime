#!/usr/bin/env python3
"""检查 API 目录行是否绑定到占位、常量兜底或实际处理器。

解析绑定表和处理器函数体，并结合桩台账生成报告。目录登记只说明接口存在，
不能单独证明其语义或回调时序正确；无法静态判断的实现保留为待核查。
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
TOOL_DIR = ROOT / "tools"
LUA_DIR = ROOT / "runtime" / "src" / "interfaces" / "lua"
LEDGER = TOOL_DIR / "lua_api_stub_ledger.json"

#: "我什么都不读、直接编一个值"的标记。
#:
#: 2026-09-25 加了 `"Stub::"`：`isaac_api.cpp` 里有一份显式的桩枚举（`enum class Stub`，注释
#: 自称"这里的枚举就是还在桩里的那些，与台账双向一致"）。**那句话当时是错的** —— 枚举里
#: `WorldToScreen` / `WorldToRenderPosition` 两条走共享助手 `WorldToIdentity`，判据只看处理器
#: 自己的正文，于是这两条被判成 `real`、台账里也没有它们。加这个标记就是把那条注释变成事实。
#:
#: 2026-09-28（审查第 3 遍，）加了两类直接压常量的写法：
#: `lua_pushboolean(state, 0/1)`、`lua_pushinteger(state, 0)`。
#: 起因：审查 Lua 接口面时把"我们实现的东西"与引擎符号表对账，发现 7 条"引擎里**有同名成员函数**、
#: 我们却恒返回假值"的桩 —— 其中 `EntityPlayer:HasPlayerForm` / `CanPickRedHearts` /
#: `SFXManager:IsPlaying` 三条**根本没进台账**，因为它们是 `lua_pushboolean(state, 0)`
#: 而不是 `PushZero(`。补上这个判据后台账 13 → 28 条（**不是新增桩，是看见一直看不见的**，
#: 与 09-25 那次 11 → 13 同一性质）。
#: 为什么之前没人发现：这 13 条老桩恰好都用了 `PushZero(`/`WarnStubOnce(`，于是"恒假布尔"这一整类
#: 在判据里是盲区。判据词表改了 ⇒ `STUB_BUDGET`（门禁）要一起动。
#:
#: 为什么不收 `lua_pushnil(state)`："返回 nil" 常常是正确的语义（例如
#: `EntityPlayer:GetOtherTwin` 在单人局就该给 nil、`GetMainTwin` 同族），收进来会把真实现判成桩
#: （实测会多认 6 条：`GetOtherTwin` / `GetMainTwin` / `GetCardRNG` 一族 / `GetName` / `ItemConfig:Get*`）。
#: 这个取舍是**刻意保守**：宁可漏（留在 `unknown` 里等人看），不可误（把真实现挂上"桩"的名）。
STUB_MARKERS = (
    "PushZero(", "WarnStubOnce(", "Stub::",
    "lua_pushboolean(state, 0)", "lua_pushboolean(state, 1)",
    "lua_pushinteger(state, 0)",
)
#: "真的碰了引擎/游戏状态"的标记。出现任何一个就不再算桩 —— 哪怕它同时有降级分支
#: （"读不到才降级"是**正确**写法，不能和"恒返回 0"混为一谈；2026-09-18 我自己就混过一次）。
#:
#: 2026-09-25 补了 `engine_memory::` / `engine_call::`：L1/L2 两层重构（~114）之后，
#: **引擎访问全部经这两个命名空间**，而词表还停在重构前的写法上。不补的后果是"降级型处理器"
#: （既有 `PushZero` 分支、又经层读引擎）会被判成桩 → 假阳性。实测补之前有 75 条"看起来不碰引擎"
#: 的处理器，其中大半是这种误报（`Isaac:FindInRadius`、`Room:GetGridIndex` 等）。
REAL_MARKERS = (
    "engine_memory::",      # L1：内存访问层（ReadAt / ReadField / AddressOf / AsObject …）
    "engine_call::",        # L2：引擎调用层（ResolveEntryAddress / AsFunction / VerifyEntryBytes …）
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
    # 2026-09-28：碰运行时自己的状态也算"真实现"。
    # 起因：把恒布尔/整数写进 `STUB_MARKERS` 之后，`RuntimeMods:Save` 被判成桩 —— 而它是真实现
    # （`g_toggles->Save()` 存到存档分区，返回值由那个结果决定），只是**开头有一句降级分支**
    # `if (g_toggles == nullptr) { lua_pushboolean(state, 0); return 1; }`。
    # 这正是本表注释反复强调的那条："**读不到才降级**是正确写法，不能和恒返回 0 混为一谈"。
    # `RuntimeMods` 一族碰的是我们自己的持久化层（不是引擎），原来的词表只认"碰引擎"的那些写法。
    "g_toggles",
    "Status::",
    # 2026-09-29：读运行时自己编译进去的静态表也算"真实现"。
    # 起因：`Isaac:GetEntityTypeByName` / `GetEntityVariantByName` 的返回值来自
    # `program/entity_name_table.hpp`（由 `tools/generate_entity_name_table.py` 从
    # `tools/entity_name_source.txt` 生成的本体 `entities2.xml` 名字快照）——
    # 它确实是"查表得到的数据"，不是"什么都不读、直接编一个值"，
    # 但旧词表只认"碰引擎"和"碰我们的持久化层"，于是这两条被判成桩（误报）。
    # 与上一批 `g_toggles` 同一性质（第三类真值来源：编译进去的静态快照），
    #   只是这次的数据源是本模块内的查表，不是引擎内存。
    #   写具名助手而不是表访问函数：这两个处理器自己不碰表，而是调
    #   `FindEntityNameEntry()`（"在生成的名字表里二分"）—— `REAL_MARKERS` 只看处理器自己的正文
    #   （与 `stub_helper_names()` 的"一层委托"方向相反，那边的委托只用在判**桩**上）。
    #   所以这里两个都收：助手名管"现在这么写"，表访问名管"将来有人把它内联进处理器"。
    # 为什么不能靠"改代码形状躲开"：判据要抓的是"返回值有没有来源"，
    #   把 `lua_pushinteger(state, 0)` 换个写法只是让检查瞎掉，来源问题一点没解决。
    "FindEntityNameEntry(",
    "EntityNameEntries(",
    # 2026-10-02：走通用跳板调引擎也是一种"返回值有来源"，旧词表看不见。
    # 起因：`Isaac:CountEntities` 被判成桩 —— 它真读真调（`ResolveRoom()` 解房间 →
    # `EntityListFingerprintMatches()` 校验容器 → 解析 `EntityList::CountSpawned @ 0x7A1CC`
    # 的入口 → `EngineCallTrampoline(...)` 调进去），但两条降级分支写的是
    # `lua_pushinteger(state, 0)`，而正文里**一个旧标记都命中不了**：
    #   * 旧词表有 `IsEngineMemoryReadable(`（**带括号**）—— 而跳板形态是把它当模板实参传进去，
    #     写出来是 `EngineOffsetAddress<IsEngineMemoryReadable>(...)` ⇒ 差一个字符，永远命不中；
    #   * 跳板调用本身（`EngineCallTrampoline(`）也不在词表里。
    # ⇒ 这不是"新增了一类真值来源"，而是**同一个来源多了一种写法**（与 `ReadEngine(` 并列）。
    # 按本文件结尾那条纪律，不许靠"把 `lua_pushinteger(state, 0)` 换个写法"躲开。
    "EngineOffsetAddress<",
    "EngineCallTrampoline(",
    # 2026-10-03：把共享助手名也收进来 —— `Room:GetAliveBossesCount` /
    # `Room:GetAliveEnemiesCount` 两条（PC 上的孪生 API）现在共用 `PushRoomAliveCount(...)`，
    # 于是处理器自己的正文里**一个引擎标记都不剩**，而那个助手因为带降级分支
    # `lua_pushinteger(state, 0)` 会被 `stub_helper_names()` 派生进去 ⇒ 两条真实现被误判成桩。
    # ⇒ 与 `PushEntityField(` / `FindEntityNameEntry(` 同一处理：**助手名进本表**
    #   （助手名管"现在这么写"，偏移常量名管"将来有人把它内联进处理器"）。
    # 为什么不把助手写成不含桩标记的形状：本文件结尾那条纪律说得很清楚 ——
    #   判据要抓的是"返回值有没有来源"，换个写法只是让检查瞎掉，来源问题一点没解决。
    "PushRoomAliveCount(",
    # 2026-10-06：读"输入边沿表"也是一种"返回值有来源"。
    # 起因：`Input.IsButtonTriggered` / `IsActionTriggered` 改成"**每帧帧上采样 + 判定纯读**"
    # 之后（口径见 `runtime/source/input_edge.hpp` 第五节），处理器正文里**不再直接碰引擎**
    # （原来那两句现查引擎的调用没了）⇒ 两条真实现被误判成桩。
    # 但它们读的 `g_ButtonEdge` / `g_ActionEdge` 是**每帧由帧上采样填出来的**（采样器直接读
    # 引擎设备对象的 `+0x30/+0x38` 位图、并对每个动作号调一次引擎 `IsActionPressed`）——
    # 与 `g_toggles` / 编译进去的静态名字表同一性质：**返回值有来源**，不是"什么都不读、直接编一个值"。
    # 两条本来就在 `FIXED_AND_MUST_STAY_FIXED` 里（不许退回成桩），这次是判据补全 ——
    # 只收**读边沿表**这四种写法，不收宽泛的 `Triggered(` / `Pressed(`（那会误伤别的处理器）。
    "g_ButtonEdge.Triggered(", "g_ActionEdge.Triggered(",
    "g_ButtonEdge.Pressed(", "g_ActionEdge.Pressed(",
)

_BINDING_ROW = re.compile(r"\{(0x[0-9A-Fa-f]{8}),\s*&(\w+)\}")


def strip_comments(text: str) -> str:
    """剥掉 `/* */` 与 `//` ��释。

    ★ 2026-10-04（批次 363 实施中查出并修掉）：原实现是
    `re.sub(r"/\\*.*?\\*/", "", text, flags=re.S)` —— **非贪婪配对**，靠"最近的一个 `*/`"收尾。
    只要**散文里出现一个孤立的 `/*`**（例如 `` `tools/isaac_name_source/*.txt` `` 这种路径写法），
    它就会把从那里到**下一个 `*/`** 之间的全部源码当成注释吃掉。

    实测（`runtime/src/interfaces/lua/isaac_api.cpp`，2026-10-04）：
      * 该文件 `/*` 出现 12 次、`*/` 只出现 5 次（其余是散文里的路径写法，不是真注释）；
      * 于是 568468 字节被剥成 81249 字节（**吃掉约 86%**）；
      * 绑定行从 **144 条**掉到 **3 条** ⇒ 台账门禁报"三条桩在源码里已经不是桩了"
        （`EntityPlayer:IsSubPlayer` / `Isaac:GetPersistentGameData` / `Isaac:GetTrinketIdByName`），
        而真相是**这三条一直是桩**、只是检查器瞎了。
      * 把那一处散文的 `/*` 换成等价写法后，绑定行立刻回到 144 条、三条也回到 found 里
        ⇒ 单一原因，已用对照实验钉住。

    修法：**按 C 的规则做状态机**（引号 / 字符字面量里的 `/*` `//` 不算注释，块注释按嵌套深度收尾），
    而不是靠正则配对。这样"散文里的孤立 `/*`"再也不会吃掉后面的代码。
    """
    out: list[str] = []
    i = 0
    n = len(text)
    state = "code"  # code | line | block | str | chr
    while i < n:
        ch = text[i]
        nxt = text[i + 1] if i + 1 < n else ""
        if state == "code":
            if ch == "/" and nxt == "*":
                state = "block"
                i += 2
                continue
            if ch == "/" and nxt == "/":
                state = "line"
                i += 2
                continue
            if ch == '"':
                state = "str"
            elif ch == "'":
                state = "chr"
            out.append(ch)
            i += 1
            continue
        if state == "line":
            if ch == "\n":
                state = "code"
                out.append(ch)
            i += 1
            continue
        if state == "block":
            if ch == "*" and nxt == "/":
                state = "code"
                i += 2
                continue
            # 块注释里保留换行 ⇒ 行号不变（报错信息里的行号仍然可用）。
            if ch == "\n":
                out.append(ch)
            i += 1
            continue
        # str / chr：处理转义，碰到收尾引号回 code。
        if ch == "\\":
            out.append(ch)
            if nxt:
                out.append(nxt)
            i += 2
            continue
        if (state == "str" and ch == '"') or (state == "chr" and ch == "'"):
            state = "code"
        out.append(ch)
        i += 1
    return "".join(out)


def catalog_entries() -> dict[int, tuple[str, str]]:
    """绑定键（`0x0E010039` 这种 8 位十六进制）→ `(owner, name)`。

    ★ 2026-09-25（批次 127）：**改为复用 `tools/api_definition_of_done.py` 的解析器**。
    原先本文件自己带一份正则 + 一张域名表，结果是**两个工具的口径漂移**：
    本文件认出 237 条目录行，而完成定义那边（它的正则与 `api_descriptor.hpp` 有门禁互校）认出 252 条
    ⇒ 有 **28 条绑定行的 id 在本文件里查不到**，而 `survey()` 对查不到的 id 是 `continue` ——
    **那 28 条里的桩对这道闸门完全不可见**（其中就有 `MusicManager:Enable/Disable/IsEnabled`
    这种恒假的处理器）。域名表也旧了（把 `Seed` 当成 `Color`，没有 `ModMenu`）。
    ⇒ 口径只有一份：解析目录行这件事由完成定义工具负责，本文件不再自己抄。
    """
    spec = importlib.util.spec_from_file_location(
        "api_definition_of_done", TOOL_DIR / "api_definition_of_done.py")
    module = importlib.util.module_from_spec(spec)
    # 必须先登记进 `sys.modules` 再 exec：那个模块里有 `@dataclass(frozen=True)`，
    # dataclass 会回头查 `sys.modules[cls.__module__].__dict__`，不登记就 AttributeError。
    sys.modules.setdefault("api_definition_of_done", module)
    spec.loader.exec_module(module)
    return {entry.identifier: (entry.owner, entry.name)
            for entry in module.load_catalog().values()}


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


#: 一个具名函数定义的起始（为了拿"助手"的函数体 —— 处理器之外的那些）。
_FUNCTION_START = re.compile(
    r"^(?:[A-Za-z_][A-Za-z0-9_:<>,\*&\s]*?)\b(\w+)\s*\([^;{]*\)\s*\{", re.M)


def all_function_bodies() -> dict[str, str]:
    """每个具名函数的函数体（含**非处理器**的共享助手）。用"行首 `}`"当结束标记。"""
    out: dict[str, str] = {}
    for source in sorted(LUA_DIR.glob("*.cpp")):
        text = strip_comments(source.read_text(encoding="utf-8"))
        for match in _FUNCTION_START.finditer(text):
            name = match.group(1)
            end = text.find("\n}", match.end())
            out.setdefault(name, text[match.end():end if end != -1 else len(text)])
    return out


def stub_helper_names() -> set[str]:
    """**一层委托**的源头：那些"自己就是桩"的具名助手。

    为什么判据要往下走一层（2026-09-25）：`IsaacWorldToScreen` 的正文只有一句
    `return WorldToIdentity(state, Stub::WorldToScreen, "Isaac.WorldToScreen");` —— 把它**共享**
    给两条 API 的那段桩逻辑在 `WorldToIdentity` 里。只看处理器自己的正文，这两条桩就判不出来。
    ⇒ 所以：处理器调用的具名函数若含 `STUB_MARKERS`，该处理器也算桩（仍然可以被 `REAL_MARKERS` 翻案）。

    **为什么是"自动派生"而不是写死一份白名单**：白名单会在下一次有人抽出新的桩助手时失效
    （这正是本次漏掉这两条的原因）。派生版本的代价是它可能把"含桩标记的合法读写助手"也算进来
    （例如 `PushEntityField`）—— 那由第二段判据兜住：调用方若同时含 `REAL_MARKERS`（那几个助手
    本身就在词表里），照旧判 `real`。
    """
    return {name for name, body in all_function_bodies().items()
            if any(marker in body for marker in STUB_MARKERS)}


def classify_bodies() -> dict[str, str]:
    """处理器名 → `stub` / `real` / `unknown`。

    两段判据（改宽改窄都会改变台账条数，门禁 `test_lua_api_stub_ledger` 钉着）：
      1. **像不像桩**：正文含 `STUB_MARKERS` 之一，**或**调用了一个"自己就是桩"的具名助手（一层委托）；
      2. **能不能翻案**：正文同时含 `REAL_MARKERS` 之一（真的碰了引擎）⇒ 判 `real`
         —— "读不到才降级"是正确写法，不能和"恒返回 0"混为一谈。
    """
    helpers = stub_helper_names()
    verdicts: dict[str, str] = {}
    for name, body in handler_bodies().items():
        looks_like_stub = any(marker in body for marker in STUB_MARKERS) or any(
            f"{helper}(" in body for helper in helpers
        )
        if not looks_like_stub:
            verdicts[name] = "real"
            continue
        verdicts[name] = "real" if any(m in body for m in REAL_MARKERS) else "stub"
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
        # 顶层 `count` 也要跟着改（2026-09-25 发现的疏漏：`--write` 只改了 rows，
        # `count` 一直停在 11 ⇒ 台账自己内部就对不上；核对条数的人会被这个数字骗一次）。
        ledger["count"] = len(known)
        ledger["source"] = "runtime/src/interfaces/lua/*.cpp（绑定行 + 处理器函数体）"
        ledger["criteria"] = (
            "处理器体（剥掉注释）（①）含 PushZero/WarnStubOnce/Stub:: 之一，或调用了"
            "「自己含桩标记」的具名助手（一层委托）（②）且不含任何引擎真值标记"
            "（engine_memory:: / engine_call:: / ReadEngine / Thunk / Observe* …）⇒ 判桩；"
            "其余判真实现；找不到函数体判 unknown（不猜）。"
            "★ 2026-09-25 补 (①)的 Stub:: 与 (②)一层委托、并补全真值词表 —— 判据细节见文件头。"
            "★ 2026-09-29（批次 207）真值词表再补一条：**读运行时自己编译进去的静态快照**"
            "（`FindEntityNameEntry(` / `EntityNameEntries(` ——"
            "`Isaac:GetEntityTypeByName` 一族查的是生成的本体实体名表）也算真实现。"
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
