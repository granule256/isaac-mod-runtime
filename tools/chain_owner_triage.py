#!/usr/bin/env python3
"""推断 Lua 链式调用和变量接收者的 API 所属类型。

结合 PC 契约中的返回类型、局部变量赋值、类型标注及模组函数返回值，
细化 mod_api_gap_report 的同名方法候选。不确定的接收者保留为未解析，
避免将推断结果当成已验证的兼容性结论。
"""

from __future__ import annotations

import argparse
import collections
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import mod_api_gap_report as gap  # noqa: E402  （候选 owner 与"运行时实现了什么"的口径只有一份）

CONTRACT_DIR = ROOT / "tools" / "pc_contract_docs"

#: 契约页里的签名行：`#### [ReturnType](X.md) Name ( args )` / `#### ReturnType Name ( args )`。
#: 这里要的是类型名，签名行就是权威（AGENTS.md 那条"形状要读正文"讲的是取值形状，两者不冲突）。
SIGNATURE_RE = re.compile(
    r"^####\s+(?:\[([^\]]+)\]\([^)]*\)|([A-Za-z_]\w*))\s+([A-Za-z_]\w*)\s*\(")

#: 根是**构造式全局函数**：返回值类型就是函数名本身。
#: `RegisterMod` 是同一形状（PC 契约：`RegisterMod ( string Name, int APIversion )` → `Mod`）——
#: 模组开头那句 `EID = RegisterMod("…", 1)` 就把 `EID` 定成了 `Mod`，于是 `EID:AddCallback`
#: 就是 `Mod:AddCallback`（补；不补的话它会被当成"同名多 owner"的假缺口挂在那）。
GLOBAL_CALL_TYPES = {
    "Game": "Game", "Level": "Level", "Room": "Room", "Vector": "Vector", "Color": "Color",
    "RNG": "RNG", "ItemPool": "ItemPool", "Font": "Font", "Sprite": "Sprite",
    "RegisterMod": "Mod",
}
#: 根是**全局表**（不是调用）。
GLOBAL_VALUE_TYPES = {"Isaac": "Isaac"}

MEMBER_RE = re.compile(r"\s*([A-Za-z_][A-Za-z0-9_]*)")
IDENT_CALL_RE = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*([:.])\s*([A-Za-z_][A-Za-z0-9_]*)")

#: 赋值行的两种形状（2026-09-28 补齐）。
#:
#: 表达式的窗口必须止于本行（`[^\n]`）。原来写的是 `.{0,300}` + `re.S`，那是贪婪跨行的：
#: 同一条 `local` 会把后面一大段（含紧跟着的好几条 `local`）一并吞掉，而 `finditer` 是从**吞掉之后**
#: 的位置继续扫的 ⇒ **后面那几条定义被静默漏掉**。实测：`local hudBBSprite = Sprite()` 正好夹在
#: `local ArrowSprite = Sprite()` 的 300 字窗口里，一直没被定型。
LOCAL_RE = re.compile(r"\blocal\s+([A-Za-z_][A-Za-z0-9_]*)\s*=(?!=)\s*([^\n]{0,300})")

#: `表.字段 = <表达式>` —— **第三条来源**：模组常把引擎对象挂在字段上（`EID.CursorSprite = Sprite()`、
#: `EID.itemConfig = Isaac.GetItemConfig()`），之后用**裸字段名**调用（`CursorSprite:Render()`）。
#: 绑定口径 = 取**最后一个字段名**，与本模块"按名字绑定"的既有口径一致（本模块不做作用域分析）；
#: 绑错的会在 `triage()` 那一步被"定出的类型必须在该行的候选 owner 里"筛掉。
#:
#: 分隔符一律用 `[ \t]`（不是 `\s`）：`\s` 含换行，会把"上一行句末的 `.` + 下一行的 `X =`"
#:   拼成一次假的字段赋值。2026-09-28 实测踩到过 —— `main.lua` 第 1 行以 `one.` 收尾、第 2 行是
#:   `EID = RegisterMod(…)`，于是绑出了 `EID → Mod`（结论碰巧是对的，但那条匹配是错的，早晚咬人）。
FIELD_RE = re.compile(
    r"([A-Za-z_][A-Za-z0-9_]*)[ \t]*\.[ \t]*([A-Za-z_][A-Za-z0-9_]*)[ \t]*=(?!=)[ \t]*([^\n]{0,300})")

#: `X = <表达式>` —— **裸全局赋值**（既没有 `local`、也没有 `表.` 前缀）。
#: 模组开头那句 `EID = RegisterMod("…", 1)` 就是它：`EID` 从此是个 `Mod`。
#: 必须锚在行首（`re.M`）：不然 `EID.CursorSprite = Sprite()` 里的 `CursorSprite = Sprite()`
#:   也会被这一条抓走 —— 虽然结论一样，但那说明两条正则在互相抢，早晚出错。
GLOBAL_ASSIGN_RE = re.compile(
    r"^[ \t]*([A-Za-z_][A-Za-z0-9_]*)[ \t]*=(?!=)[ \t]*([^\n]{0,300})", re.M)


# =====================================================================================
# 第五种来源（2026-09-28 ）：模组自己写的 LuaLS 类型注解
# =====================================================================================
#
# 为什么加：前四种来源（全局表 / 构造式全局调用 / 已知根 + 方法链 / 赋值形状）都推不出
# **函数形参**的类型 —— 而 13 条"待人工"里**函数参数那 3 条**正是这一档。
# 模组作者自己写了注解（`---@param entity Entity`），那不是"猜"：它点名到文件:行号、
# 是作者对契约的声明，与前面几种来源一样可复核。
#
# 口径（与前面几种刻意不同的一点，是这一批最重要的一条）：
#   注解是**函数作用域**的，必须**按"调用点落在哪个函数体内"**取，
#   **不许**像前几种来源那样"按变量名全文件汇总"。
#   实测（EID）：`entityPlayer` 这个名字在两个不同函数里出现 ——
#   一处是 `EID:findPlayerName(id)` 里的**局部变量**（`local _, entityPlayer = EID:PlayersHaveCharacter(…)`），
#   另一处才是 `EID:getPlayerID(entityPlayer, lazarusAdjust)` 的**形参**（那里才有 `@param entityPlayer EntityPlayer`）。
#   按变量名汇总会把前者误绑到后者的注解上 ⇒ 得出一条"看着有证据、其实张冠李戴"的结论。
#   ⇒ 严口径下这一档只定案 **3 条**（松散口径会多 2 条假的），**这 2 条的差就是两次实测的差**。

#: 函数定义行：`function A.b(...)` / `function A:b(...)` / `local function f(...)`。
LUA_FUNCTION_RE = re.compile(
    r"^[ \t]*(?:local[ \t]+)?function[ \t]+[A-Za-z_][A-Za-z0-9_]*[.:]"
    r"([A-Za-z_][A-Za-z0-9_]*)[ \t]*\(([^)]*)\)", re.M)

#: `---@param 名字 类型 …`（`?` = 可选参数）。**类型保留原文**（不在这里退化取词），
#: 退化取词交给 `_annotation_single_type()` —— 因为它要能看见 `|`（联合类型一律不采用，
#: 见那里的说明）；在这里就把 `|` 丢掉的话，"取第一个词"与"弃用联合"两种口径就没法区分了。
LUA_PARAM_ANNOTATION_RE = re.compile(
    r"^[ \t]*---[ \t]*@param[ \t]+([A-Za-z_][A-Za-z0-9_]*)(\?)?[ \t]+([^\n]+)$")

#: `---@return 类型1, 类型2, …`（2026-09-29 新增，第六种来源：模组自己函数的返回值）。
#: 与 `@param` 一样保留**整行原文**，切分与退化交给 `_return_types_of()`。
LUA_RETURN_ANNOTATION_RE = re.compile(r"^[ \t]*---[ \t]*@return[ \t]+([^\n]+)$")

#: 多变量局部赋值：`local a, b = <表达式>`（**至少两个变量名**；单变量的那条仍走 `LOCAL_RE`）。
#: 加它的理由：模组常写 `local hasBag, bagPlayer = EID:PlayersHaveCollectible(710)` ——
#: 右边的类型在第 2 个返回值上，单变量正则根本抓不到第二个名字。
LOCAL_MULTI_RE = re.compile(
    r"\blocal\s+([A-Za-z_][A-Za-z0-9_]*(?:[ \t]*,[ \t]*[A-Za-z_][A-Za-z0-9_]*)+)"
    r"\s*=(?!=)\s*([^\n]{0,300})")

#: 右边是"一次普通调用"：`<根>[:.]<方法>(`。用来把 `local a, b = EID:Foo(…)` 认成"模组自己的函数调用"。
PLAIN_CALL_RE = re.compile(r"^[ \t]*([A-Za-z_][A-Za-z0-9_]*)\s*[:.]\s*([A-Za-z_][A-Za-z0-9_]*)\s*\(")

#: 循环变量（2026-09-29 ）：`for <k>, <v> in ipairs(<表达式>) do`。
#: 表达式那段用**括号配对**取（不用正则里的 `.*?` —— 表达式里还有一层 `FindByType(…)` 的括号）。
#: 口径：`ipairs/pairs` 遍历的是数组 ⇒ **元素类型 = 那个表达式在契约页上的返回类型**
#: （契约把数组写成 `X[]`，而签名正则取到的就是 `X`，正好是元素类型）。
#: 取不到 / 取到的不是候选 owner ⇒ 照旧留在待人工（守恒）。
LUA_FOR_IN_RE = re.compile(
    r"\bfor\s+([A-Za-z_][A-Za-z0-9_]*)\s*,\s*([A-Za-z_][A-Za-z0-9_]*)\s+in\s+"
    r"(?:ipairs|pairs)\s*\(")

#: Lua 关键字 / 结构词（块扫描用）。
_LUA_WORD_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
#: 会开一个块的词。`for` / `while` 不在这里 —— 它们的块由后面那个 `do` 开
#: （`for i = 1, n do … end` 里 `end` 与 `do` 配对，不是与 `for`）；
#: 所以 `do` 必须**无条件**入栈，`for` / `while` 只是它的前导。
_LUA_BLOCK_OPENERS = ("do", "if", "function", "repeat")
#: 会闭一个块的词（`until` 配 `repeat`，其余配上面这四个里的各自那一个）。
_LUA_BLOCK_CLOSERS = ("end", "until")

#: Lua 保留字（判断"注解的类型词是不是垃圾"时用来挡 `nil` / `function` / `not` 这类）。
#: 只放关键字，不放类型名（`any` / `integer` / `string`）—— 类型名会随 PC 侧演化，
#: 在这里维护一张名单早晚过期；它们由 `triage()` 的"类型必须在候选 owner 里"自然筛掉。
_LUA_RESERVED = frozenset((
    "and", "break", "do", "else", "elseif", "end", "false", "for", "function", "goto",
    "if", "in", "local", "nil", "not", "or", "repeat", "return", "then", "true", "until", "while",
))


def lua_function_spans(text: str) -> tuple[list[tuple[int, int]], int]:
    """扫出每个 `function … end` 的 `(起始行, 结束行)`；返回 `(配对结果, 剩余未配对的结构词数)`。

    ★ 为什么要自己扫：注解是作用域的，而"哪个函数的体覆盖了第 N 行"必须知道块的配对。
    不用正则硬怼（`end` 与 `if/then` 的配对、字符串里的 `end`、长注释/长字符串都会骗人），
    而是**逐字符状态机**：跳过注释、长字符串、普通字符串，再数关键字。

    口径（宁可保守）：
      * 四种开块词（`do` / `if` / `function` / `repeat`）**各自入栈**，`end` / `until` 出栈一个。
        ★ `for` / `while` **不入栈** —— `for i = 1, n do … end` 里 `end` 配的是那个 `do`，
        不是 `for`；把 `for` 也算一个块的话，每个循环都会多出一个只由 `end` 消掉的层，
        后面所有 `function` 的跨度就会**提前一行收尾**。
      * ★ 第二个返回值是**没配平的结构词数** —— 调用方（`lua_function_param_types`）看到它非 0
        就**整份文件不产出结论**：宁可少给一条，也不给一条位置算错的。
    """
    n = len(text)
    index = 0
    line = 1
    stack: list[tuple[str, int]] = []       # [(结构词, 该词所在行)]
    functions: list[tuple[int, int]] = []
    while index < n:
        char = text[index]
        if char == "\n":
            line += 1
            index += 1
            continue
        # 注释（行注释 / 长注释 `--[[ … ]]` / `--[=[ … ]=]`）
        if text.startswith("--", index):
            opener = re.match(r"--\[(=*)\[", text[index:])
            if opener is not None:
                closer = "]" + opener.group(1) + "]"
                end = text.find(closer, index + opener.end())
                segment = text[index:(end + len(closer)) if end >= 0 else n]
                line += segment.count("\n")
                index += len(segment)
                continue
            end = text.find("\n", index)
            index = n if end < 0 else end
            continue
        # 长字符串 `[[ … ]]`
        if char == "[":
            opener = re.match(r"\[(=*)\[", text[index:])
            if opener is not None:
                closer = "]" + opener.group(1) + "]"
                end = text.find(closer, index + opener.end())
                segment = text[index:(end + len(closer)) if end >= 0 else n]
                line += segment.count("\n")
                index += len(segment)
                continue
        # 普通字符串
        if char in "\"'":
            cursor = index + 1
            while cursor < n and text[cursor] != char:
                if text[cursor] == "\\":
                    cursor += 1
                if text[cursor] == "\n":
                    line += 1
                cursor += 1
            index = cursor + 1
            continue
        word = _LUA_WORD_RE.match(text, index)
        if word is not None:
            token = word.group(0)
            if token in _LUA_BLOCK_OPENERS:
                stack.append((token, line))
            elif token in _LUA_BLOCK_CLOSERS:
                if stack:
                    opener, opener_line = stack.pop()
                    if opener == "function":
                        functions.append((opener_line, line))
            index = word.end()
            continue
        index += 1
    return functions, len(stack)


def lua_function_param_types(path: pathlib.Path) -> list[tuple[int, int, dict[str, str]]]:
    """`[(起始行, 结束行, {形参名: 注解原文})]`，**按跨度从小到大**排（取"最内层"就用第一个命中）。

    ★ 位置（函数头行号）与块配对（结束行）都由**同一份** `lua_function_spans` 给，
    避免"注解按行号取、函数体按字符位取"两边口径不一致（那会让证据行指向别的函数）。

    ★ 存的是**注解原文**（如 `Entity | GridEntity`、`fun(spriteObj: Sprite) | nil`），
    不是退化后的词 —— 退化与"联合类型一律不采用"两条口径都在 `annotation_single_type()`
    里，那边要看得见 `|` 才能判。

    ★★ 配不平（`lua_function_spans` 的第二个返回值非 0）⇒ **返回空表**：这份文件一条注解都不用。
    """
    # 读原文，不剥注释：本函数要的是 `---@param` 注解，而注解本身就是注释
    #   （理由与实测回归见 `gap.lua_source_raw()` 的 docstring）。
    text = gap.lua_source_raw(path)
    lines = text.splitlines()
    funcs, unbalanced = lua_function_spans(text)
    if unbalanced:
        return []
    if not funcs:
        return []
    end_by_start = dict(funcs)
    out: list[tuple[int, int, dict[str, str]]] = []
    for match in LUA_FUNCTION_RE.finditer(text):
        start = text.count("\n", 0, match.start()) + 1
        if start not in end_by_start:
            continue        # 没配对上的函数头 ⇒ 不用它的注解（位置不可信）
        parameters = [item.strip() for item in match.group(2).split(",") if item.strip()]
        # 往上收集连续的 `---` 注解块
        annotations: list[str] = []
        cursor = start - 2
        while cursor >= 0 and lines[cursor].strip().startswith("---"):
            annotations.append(lines[cursor])
            cursor -= 1
        declared: dict[str, str] = {}
        for annotation in reversed(annotations):
            found = LUA_PARAM_ANNOTATION_RE.match(annotation)
            if found is not None:
                declared[found.group(1)] = found.group(3).strip()
        if not declared:
            continue
        out.append((start, end_by_start[start], {p: declared[p] for p in parameters if p in declared}))
    out.sort(key=lambda item: item[1] - item[0])
    return out


def annotation_types_of(raw: str) -> tuple[str, list[str]]:
    """把一条 `---@param` 的类型原文拆成 `(单类型, 联合成员表)`；两者都可以是空的。

    ★★ 为什么把联合类型**单列**、不当成单类型用（本批定的一条口径，2026-09-28 批次 186）：

    `---@param entity Entity | GridEntity` 同时点了两个 owner，而我们的 `GridEntity:GetSprite`
    **没实现**。若"取第一个词"（`Entity`）就当结论，这条会被判成"不是缺口" ——
    可那是在**替模组选**它说的两个类型里的一个，而这个选择**决定了结论**。
    反过来，若把联合取并集直接判缺口，又会**凭空报出一个缺口** —— 因为模组自己都说这个变量的
    实际类型是两者之一，我们并不知道这一次是哪个。

    ⇒ 联合成员**只用于"降级"**：`not_a_gap` 要成立，联合里**每个成员都必须在候选里、且我们都实现了**；
    只要有一个联合成员是我们没实现的，这条就退回**待人工**（不给 `gap` 也不给 `not_a_gap`）。
    这样既不替模组选类型，也不会把"可能"说成"就是"。

    形状处理：
      * `Sprite` ⇒ `("Sprite", [])`；
      * `Entity | GridEntity` ⇒ `("", ["Entity", "GridEntity"])`；
      * `fun(spriteObj: Sprite) | nil` ⇒ `("", ["fun"])` —— 取词只能取到 `fun`，
        这是个垃圾值，靠 `triage()` 那一步"类型必须在候选 owner 里"自然筛掉；
      * `GridEntity: The grid entity to check for a description.` ⇒ `("GridEntity", [])`
        —— 类型后面跟说明文字是**收得成的**（只有首个词是类型）；
      * `nil` / `function` / 空 ⇒ `("", [])`（Lua 关键字不成类型）。
    """
    text = raw.strip()
    if not text:
        return "", []
    if "|" in text:
        members: list[str] = []
        for piece in text.split("|"):
            head = re.match(r"[A-Za-z_][A-Za-z0-9_]*", piece.strip())
            if head is not None and head.group(0) not in _LUA_RESERVED:
                members.append(head.group(0))
        return "", members
    head = re.match(r"[A-Za-z_][A-Za-z0-9_]*", text)
    if head is None:
        return "", []
    word = head.group(0)
    # 首词必须是标识符且不是 Lua 关键字 —— 把 `nil` / `function` / `not` 这类挡住。
    #   形状不对的词（`any`、`integer`、`string`、`number`）不在关键字表里，由 `triage()`
    #   那一步"类型必须在候选 owner 里"自然筛掉，不在这里维护一张会过期的名单。
    if word in _LUA_RESERVED:
        return "", []
    return word, []


def resolve_annotation_types(mod: pathlib.Path
                             ) -> dict[tuple[str, str], tuple[dict[str, list[str]],
                                                             dict[str, list[str]]]]:
    """第五种来源：模组自己写的 `---@param` 注解
    ⇒ `(接收者, 方法名) → (单类型表, 联合成员表)`，两张表都是 `{类型名: [证据]}`。

    ★★ **索引键是 `(接收者, 方法名)`，不是光接收者名** —— 这是与前面四种来源最不一样、
    也最容易做错的一点。两个理由：

    ① **注解是函数作用域**的：同名变量在不同函数里可以是不同的东西。
       实测（EID，2026-09-28）：`entityPlayer` 在 `eid_api.lua:1009` 是 `EID:findPlayerName` 里的
       **局部变量**（`local _, entityPlayer = EID:PlayersHaveCharacter(…)`），
       而 `---@param entityPlayer EntityPlayer` 写在**另一个函数** `EID:getPlayerID` 上 ⇒
       按变量名汇总就会把 1009 行那条调用误绑上去（一条"看着有证据、其实张冠李戴"的结论）。
    ② **同一个名字在不同调用点上是不同的类型**：`entity` 在 `eid_api.lua:2217` 的
       `EID:getEntityData(entity, str)` 上是 `Entity`，在 `eid_grid_descriptions.lua:79` 的另一个
       函数上却是 `GridEntity`。只看变量名的话，`entity:GetSprite` 会把 `GridEntity` 也吃进来
       ⇒ 定出 `Entity/GridEntity` 两个类型 ⇒ 因为 `GridEntity:GetSprite` 我们没实现，
       **凭空报出一条"真缺口"**（批次 186 实测踩到过）。
       按 `(接收者, 方法名)` 索引就不会把别的函数的注解搬过来。

    ⇒ 本函数**只在"这一行的调用恰好落在某个函数体内、且该函数把这个名字声明成形参"时**收。
    单类型与联合成员**分开返回**：能不能据此下结论，由 `triage()` 按候选与实现状态判
    （联合只用于"降级"，见那里的说明）。
    """
    call_re = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*[:.]\s*([A-Za-z_][A-Za-z0-9_]*)\s*\(")
    singles: dict[tuple[str, str], dict[str, list[str]]] = collections.defaultdict(
        lambda: collections.defaultdict(list))
    unions: dict[tuple[str, str], dict[str, list[str]]] = collections.defaultdict(
        lambda: collections.defaultdict(list))
    for path in sorted(mod.rglob("*.lua")):
        spans = lua_function_param_types(path)
        if not spans:
            continue
        text = gap.lua_source(path)
        for match in call_re.finditer(text):
            receiver, method = match.group(1), match.group(2)
            line = _line_of(text, match.start())
            # spans 已按跨度从小到大排 ⇒ 第一个覆盖该行、且形参里有这个名字的，就是"最内层"。
            for start, end, declared in spans:
                if start <= line <= end and receiver in declared:
                    single, members = annotation_types_of(declared[receiver])
                    place = f"{path.name}:{line}（@param 在 {path.name}:{start}）"
                    if single:
                        singles[(receiver, method)][single].append(place)
                    for member in members:
                        unions[(receiver, method)][member].append(place)
                    break
    keys = set(singles) | set(unions)
    return {key: (dict(singles.get(key, {})), dict(unions.get(key, {}))) for key in keys}


def load_contract_array_element_types() -> dict[tuple[str, str], str]:
    """PC 契约页 → `{(owner, 方法名): 元素类型}`，**只收写成 `X[]` 的那些**（批次 197 新增）。

    为什么单开一张表、而不扩 `SIGNATURE_RE`：契约里数组返回类型写成
    `#### [Entity](Entity.md)[] FindByType ( … )` —— 类型与链接之间夹了个 `[]`，
    而 `SIGNATURE_RE` 要求类型后面紧跟空白 ⇒ **所有数组返回类型一直没被解析到**
    （实测：`Isaac.FindByType` 在 `load_contract_return_types()` 里查不到）。
    单开一张表的好处是**不改变既有那 4 种来源的行为**（既有口径一个字节都不动），
    只有"循环变量"这一档去读它。

    ★ 口径：**只认 `X[]` 这种形状**；契约里用容器名写的（`RoomDescriptor List`、
    `EntityList`）**不在这张表里** ⇒ 那类循环变量照旧留在待人工（守恒，不猜）。
    """
    array_re = re.compile(
        r"^####\s+\[([^\]]+)\]\([^)]*\)\s*\[\]\s+([A-Za-z_]\w*)\s*\(")
    table: dict[tuple[str, str], str] = {}
    for page in sorted(CONTRACT_DIR.glob("*.md")):
        for line in page.read_text(encoding="utf-8", errors="replace").splitlines():
            match = array_re.match(line)
            if match is not None:
                table[(page.stem, match.group(2))] = match.group(1).strip()
    return table


def load_contract_return_types() -> dict[tuple[str, str], str]:
    """PC 契约页 → `{(owner, 方法名): 返回类型}`（owner = 页文件名）。"""
    table: dict[tuple[str, str], str] = {}
    for page in sorted(CONTRACT_DIR.glob("*.md")):
        for line in page.read_text(encoding="utf-8", errors="replace").splitlines():
            match = SIGNATURE_RE.match(line)
            if match is not None:
                table[(page.stem, match.group(3))] = (match.group(1) or match.group(2)).strip()
    return table


def _return_types_of(raw: str) -> list[str]:
    """把 `---@return boolean, EntityPlayer?, integer?` 拆成**按位置**的类型表（未知位给 `""`）。

    ★ **必须按位置**：`local hasBag, bagPlayer = EID:PlayersHaveCollectible(710)` 里
    `bagPlayer` 是**第 2 个**返回值 —— 只留"类型集合"而不留位置，就会把 `boolean` 当对象类型去用。
    每个词先去掉可选的 `?`（`EntityPlayer?` = 可能是 nil，类型仍是 `EntityPlayer`），
    再挡掉 Lua 关键字与非标识符（`nil` / `function` / `table`）。**不挡** `integer`/`string`/`boolean`
    这类内建名 —— 它们不是候选 owner，会在 `triage()` 的"类型必须在候选里"那一步自然筛掉
    （与 `annotation_types_of()` 同一口径：**不维护一张会过期的名单**）。
    """
    out: list[str] = []
    for piece in raw.split(","):
        head = re.match(r"[A-Za-z_][A-Za-z0-9_]*", piece.strip())
        word = head.group(0) if head is not None else ""
        out.append("" if word in _LUA_RESERVED else word)
    return out


def mod_function_return_types(path: pathlib.Path) -> dict[str, list[str]]:
    """**第六种来源**（2026-09-29 批次 197）：模组自己函数的**声明返回值**
    ⇒ `{函数名: [按位置的类型]}`。

    为什么需要：`local hasBag, bagPlayer = EID:PlayersHaveCollectible(710)` 这类赋值的右边是
    **模组自己**的函数 —— 不在 PC 契约页、没有返回类型可查，前四种来源全都推不动
    （批次 186 定案的"待人工"里，"模组自己的函数返回值"那 2 条就是它）。
    而作者自己写了 `---@return boolean, EntityPlayer?, integer?` ⇒ 与 `@param` 一样是
    **作者对契约的声明、可复核**，不是我们猜的。

    ★ 口径两条：
      ① **按名字取整份文件的函数定义**（键 = 方法名）。与 `@param` 那条"按函数作用域取"不同：
         `@return` 描述的是**被调用函数本身**，与"在哪一行调用"无关 ⇒ 不需要作用域约束。
      ② 文件块配不平就整份不用（与 `lua_function_param_types()` 同一道闸）。
    """
    # 读原文：要取的是 `---@return`，它写在注释里（同 `lua_function_param_types()`）。
    text = gap.lua_source_raw(path)
    lines = text.splitlines()
    _, unbalanced = lua_function_spans(text)
    if unbalanced:
        return {}
    out: dict[str, list[str]] = {}
    for match in LUA_FUNCTION_RE.finditer(text):
        start = text.count("\n", 0, match.start()) + 1
        annotations: list[str] = []
        cursor = start - 2
        while cursor >= 0 and lines[cursor].strip().startswith("---"):
            annotations.append(lines[cursor])
            cursor -= 1
        for annotation in annotations:
            found = LUA_RETURN_ANNOTATION_RE.match(annotation)
            if found is not None:
                out[match.group(1)] = _return_types_of(found.group(1))
                break
    return out


def _line_of(text: str, position: int) -> int:
    return text.count("\n", 0, position) + 1


def _chain_from(text: str, cursor: int) -> list[tuple[str, bool]]:
    """从 `cursor` 起走完整条链，返回 `[(成员名, 是否被调用)]`（跳过规则与缺口报告同一套）。"""
    steps: list[tuple[str, bool]] = []
    while True:
        cursor = gap._skip_blank(text, cursor)  # noqa: SLF001（同一份走法，别再抄一遍）
        if cursor < len(text) and text[cursor] in ":.":
            cursor += 1
        else:
            break
        member = MEMBER_RE.match(text, cursor)
        if member is None:
            break
        name = member.group(1)
        cursor = gap._skip_blank(text, member.end())
        called = False
        if cursor < len(text) and text[cursor] == "(":
            called = True
            cursor = gap._skip_balanced(text, cursor)
        elif cursor < len(text) and text[cursor] == "[":
            cursor = gap._skip_balanced(text, cursor)
        steps.append((name, called))
    return steps


def resolve_variable_types(mod: pathlib.Path) -> dict[str, dict[str, list[str]]]:
    """`变量名 → {类型: [证据(文件:行)]}` —— 只收"推得出来"的那些。

    三种赋值形状都收：`local x = …`（局部变量）、`表.字段 = …`（取最后一个字段名）、
    `X = …`（裸全局赋值，例如模组开头的 `EID = RegisterMod(…)`）；
    另收链式调用里每一步的接收者类型
    （缺口报告把后者单独列成一段，这里合并起来，因为判"是不是缺口"用的是同一句判据：
    这个接收者类型上有没有这个方法）。
    """
    return_types = load_contract_return_types()
    array_types = load_contract_array_element_types()
    types: dict[str, dict[str, list[str]]] = collections.defaultdict(lambda: collections.defaultdict(list))

    for path in sorted(mod.rglob("*.lua")):
        text = gap.lua_source(path)
        locals_: dict[str, str] = {}
        # 第六种来源：模组自己函数的声明返回值 —— 按函数名建一份小表。
        mod_returns = mod_function_return_types(path)
        # 三种赋值形状要按文件里的先后顺序处理（同一条链上后面的赋值可能用到前面的变量），
        #   所以先收集再排序，而不是一种形状扫完再扫下一种。
        assignments: list[tuple[int, str, str]] = []
        for match in LOCAL_RE.finditer(text):
            assignments.append((match.start(), match.group(1), match.group(2)))
        for match in FIELD_RE.finditer(text):
            assignments.append((match.start(), match.group(2), match.group(3)))
        for match in GLOBAL_ASSIGN_RE.finditer(text):
            assignments.append((match.start(), match.group(1), match.group(2)))
        for position, variable, expression in sorted(assignments):
            resolved = _type_of_expression(expression, locals_, return_types)
            if resolved:
                locals_[variable] = resolved
                types[variable][resolved].append(f"{path.name}:{_line_of(text, position)}")

        # 多返回值：`local a, b = EID:PlayersHaveCollectible(710)`（新增）。
        #   右边是**模组自己**的函数 ⇒ 前四种来源都推不动；作者写了 `---@return` 才定得出来。
        #   按位置取（第 2 个变量拿第 2 个返回类型），类型仍是"必须在候选 owner 里"才被采用。
        for match in LOCAL_MULTI_RE.finditer(text):
            call = PLAIN_CALL_RE.match(match.group(2))
            if call is None:
                continue
            declared = mod_returns.get(call.group(2))
            if not declared:
                continue
            evidence = f"{path.name}:{_line_of(text, match.start())}"
            for index, name in enumerate(v.strip() for v in match.group(1).split(",")):
                if index >= len(declared) or not declared[index]:
                    continue
                locals_[name] = declared[index]
                types[name][declared[index]].append(evidence)

        # 循环变量：`for _, crane in ipairs(Isaac.FindByType(…)) do`（新增）。
        #   元素类型优先查**数组元素类型表**（契约里写成 `X[]` 的那些），查不到再退回普通定型。
        #   契约里写成"容器名"的（`Level:GetRooms()` → `RoomDescriptor List`）两张表都没有它，
        #     会自然留在待人工 —— 与其它来源同一条口径：**推不出就不写**。
        for match in LUA_FOR_IN_RE.finditer(text):
            variable = match.group(2)
            paren = match.end() - 1                    # 指向 `ipairs(` 的那个 `(`
            close = gap._skip_balanced(text, paren)    # noqa: SLF001（与链式那一路同一份走法）
            if close <= paren:
                continue
            expression = text[paren + 1:close - 1]
            element = ""
            call = PLAIN_CALL_RE.match(expression)
            if call is not None:
                root_type = GLOBAL_VALUE_TYPES.get(call.group(1)) or locals_.get(call.group(1))
                if root_type is not None:
                    element = array_types.get((root_type, call.group(2)), "")
            if not element:
                element = _type_of_expression(expression, locals_, return_types)
            if element:
                types[variable][element].append(f"{path.name}:{_line_of(text, match.start())}")

        # 链/冒号调用：从**已知类型的根**开始，逐跳记下接收者类型。
        for match in IDENT_CALL_RE.finditer(text):
            root, _separator, first = match.groups()
            current = GLOBAL_VALUE_TYPES.get(root) or locals_.get(root)
            if current is None:
                continue
            cursor = gap._skip_blank(text, match.end())
            if not (cursor < len(text) and text[cursor] == "("):
                continue        # 不是调用（`Isaac.PlayerType` 这类常量访问）⇒ 不推
            cursor = gap._skip_balanced(text, cursor)
            evidence = f"{path.name}:{_line_of(text, match.start())}"
            types[first][current].append(evidence)
            current = return_types.get((current, first))
            for name, called in _chain_from(text, cursor):
                if not called or current is None:
                    break
                types[name][current].append(evidence)
                current = return_types.get((current, name))

    return {name: dict(owners) for name, owners in types.items()}


def _type_of_expression(expression: str, locals_: dict[str, str],
                        return_types: dict[tuple[str, str], str]) -> str:
    """给一条赋值右边定型 —— 规则①②③的**唯一**入口。

    只认三种根（与模块头部那三条来源一一对应）：
      ① 全局表（`Isaac`）—— 类型就是表名，后面必须跟 `.方法(...)`；
      ② 构造式全局调用（`Sprite()` / `Game()` / `Vector(…)`）—— 类型就是函数名本身；
      ③ 已知变量（`local x = …` 或 `表.字段 = …` 定的）—— 后面必须跟 `:方法(...)`。

    形状对不上就返回 `""`：**不猜**。三种"对不上"都要挡住 —— 根不认识、
    只写了成员名没调用（`Isaac.PlayerType` 这种常量访问）、链中途的方法名不在契约页里。
    """
    stripped = expression.lstrip()
    head = re.match(r"([A-Za-z_][A-Za-z0-9_]*)", stripped)
    if head is None:
        return ""
    root, cursor = head.group(1), head.end()

    if root in GLOBAL_VALUE_TYPES or locals_.get(root) is not None:
        current = GLOBAL_VALUE_TYPES.get(root) or locals_[root]
    elif root in GLOBAL_CALL_TYPES:
        # 规则②：构造式全局调用。它以前只写在文档里（`GLOBAL_CALL_TYPES` 是个从没被读过的
        #   死常量），所以 `local s = Sprite()` 一直定不出类型 —— 补上。
        cursor = gap._skip_blank(stripped, cursor)
        if not (cursor < len(stripped) and stripped[cursor] == "("):
            return ""       # 只写了函数名、没调用 ⇒ 不猜
        cursor = gap._skip_balanced(stripped, cursor)
        return _walk_members(GLOBAL_CALL_TYPES[root], stripped, cursor, return_types,
                             first_must_be_call=False)
    else:
        return ""           # 陌生根（函数参数、模组自己的表…）⇒ 不猜

    return _walk_members(current, stripped, cursor, return_types, first_must_be_call=True)


def _walk_members(current: str, text: str, cursor: int,
                  return_types: dict[tuple[str, str], str], first_must_be_call: bool) -> str:
    """从 `cursor` 起顺着 `:方法()` / `.方法()` 往下推类型（推不动就停在原地）。

    `first_must_be_call=True` 时要求**第一跳必须是调用** —— `local x = Isaac.PlayerType`
    是"取常量"不是"调方法"，那时 `x` 的类型是**未知**，不能把根的类型（`Isaac`）当成它的类型。
    构造式调用那一支不受这条约束（`local s = Sprite()` 后面本来就没有成员）。
    """
    steps = _chain_from(text, cursor)
    if first_must_be_call and (not steps or not steps[0][1]):
        return ""
    for name, called in steps:
        if not called or not current:
            break
        current = return_types.get((current, name), "")
    return current


def triage(mod: pathlib.Path | None = None) -> dict:
    """整份分诊结果（缺口报告与门禁共用同一份）。"""
    mod = mod or (ROOT / gap.DEFAULT_MOD)
    variable_types = resolve_variable_types(mod)
    annotation_types = resolve_annotation_types(mod)
    runtime_apis = gap.load_runtime_apis()

    # ①b 的构成与缺口报告一致：**方法名有多个 PC owner**、且其中有我们没实现的那些。
    pc_catalog = gap.load_pc_method_catalog()
    usage = gap.load_mod_usage(mod)
    usage.update(gap.load_mod_dot_usage(mod, pc_catalog))
    defined = gap.load_mod_definitions(mod)
    defined_names = {key.split(":", 1)[1] for key in defined}

    rows = []
    for key, count in sorted(usage.items()):
        receiver, name = key.split(":", 1)
        if key in defined or name in defined_names:
            continue
        candidates = pc_catalog.get(name) or []
        if len(candidates) < 2:
            continue        # 只有一个 owner ⇒ 归 ① 主清单，不进这一档
        missing = [owner for owner in candidates
                   if f"{gap.canonical_owner(owner)}:{name}" not in runtime_apis]
        if not missing:
            continue        # 候选里没有缺的 ⇒ 本来就不在这档里
        places = variable_types.get(receiver, {})
        evidence: list[str] = []
        decided: dict[str, list[str]] = {}
        for owner, where in sorted(places.items()):
            # 只认"候选 owner 里真有这个类型"的那些 —— 推理结果落在候选之外时说明推错了，
            # 那种情况**不采用**（宁可留在待人工，也不拿一个自相矛盾的结论去关缺口）。
            if owner not in candidates:
                continue
            decided[owner] = where
            evidence.extend(f"{receiver} = {owner} ← {place}" for place in where)
        if not decided:
            # 第五种来源：模组自己写的 `---@param` 注解。
            #   ① 只有前四种来源**一条都没定出来**时才用它 —— 赋值推出来的类型是"这段代码实际
            #      发生了什么"，比作者写的声明更硬；两者冲突时以赋值为准。
            #   ② 采用口径与前面完全一致：**类型必须在该行的候选 owner 里**，否则不采用
            #      （`fun(spriteObj: Sprite) | nil` 拆出来的 `fun` 就落在这里被筛掉）。
            #   ③ **联合类型不采用**（`Entity | GridEntity` ⇒ 一个都不用）。两种"替模组做主"的
            #      写法都要拦：取第一个词会让真实缺口静默消失；取并集会在模组自己都没说死类型时
            #      把"可能"报成"就是"。这条判据的选择直接决定结论 ⇒ 分诊器无权替它选，退回待人工。
            #      实测（EID）：`entity:GetSprite` 若采用联合的 `GridEntity` 成员就会被报成
            #      "真缺口"，可那些调用点其实都在 `EID:IsGridEntity(entity)` 的**排除分支之后** ——
            #      一条假缺口。它另有单类型注解（`main.lua:919` 的 `@param entity Entity`）⇒ 照常定案。
            #      证据里留一行说明"看见过联合、没采用"，免得日后有人以为漏了。
            single_types, union_members = annotation_types.get((receiver, name), ({}, {}))
            for owner, where in sorted(single_types.items()):
                if owner in candidates:
                    decided[owner] = where
                    evidence.extend(f"{receiver} ← @param {owner}：{place}" for place in where)
            if union_members:
                evidence.append("（另有调用点的 @param 是联合类型 "
                                f"{' | '.join(sorted(union_members))}，未采用："
                                f"{union_members[sorted(union_members)[0]][0]}）")
        if not decided:
            verdict = "manual"
        elif any(f"{gap.canonical_owner(owner)}:{name}" not in runtime_apis for owner in decided):
            verdict = "gap"
        else:
            verdict = "not_a_gap"
        rows.append({
            #: 与缺口报告同一口径：`<模组里那个接收者标识符>:<方法名>`（报告里叫 `called_as`）。
            "called_as": key,
            "receiver": receiver,
            "name": name,
            "calls": count,
            "candidate_owners": candidates,
            "resolved_owners": sorted(decided),
            "verdict": verdict,
            "evidence": evidence[:6],
        })

    by_verdict = collections.Counter(row["verdict"] for row in rows)
    return {
        "mod": str(mod.relative_to(ROOT)) if str(mod).startswith(str(ROOT)) else str(mod),
        "pc_signatures": len(load_contract_return_types()),
        "rows": len(rows),
        "by_verdict": dict(by_verdict),
        "triaged": rows,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--mod", default=None, help="模组目录（默认 = 缺口报告的默认模组）")
    parser.add_argument("--json", action="store_true", help="输出机器可消费的 JSON")
    arguments = parser.parse_args(argv)
    result = triage(pathlib.Path(arguments.mod) if arguments.mod else None)
    if arguments.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    print(f"接收者类型分诊：{result['mod']}")
    print(f"  PC 契约签名 {result['pc_signatures']} 条；①b 这一档 {result['rows']} 条 ⇒ {result['by_verdict']}")
    print("  （口径：变量类型只看 全局表 / 构造式全局调用 / `<已知类型的根> + 一串方法调用` 三种来源 ——"
          "赋值形状 `local x = …`、`表.字段 = …`、`X = …` 都收；"
          "另收**模组自己写的 `---@param` 注解**（按调用点所在函数取、按「接收者+方法名」索引，"
          "联合类型不采用）；"
          "推不动就停在「待人工」，**绝不写死 owner**。）")
    for verdict, title in (("gap", "★ 真缺口（定出的接收者上，我们没有这个方法）"),
                           ("not_a_gap", "不是缺口（定出的接收者我们都有这个方法）"),
                           ("manual", "待人工（类型没法定出来）")):
        rows = [row for row in result["triaged"] if row["verdict"] == verdict]
        print(f"\n== {title}：{len(rows)} 条 ==")
        for row in sorted(rows, key=lambda item: (-item["calls"], item["called_as"])):
            owners = "/".join(row["resolved_owners"]) or "—"
            print(f"  {row['called_as']:32} 调用 {row['calls']:3} 次｜定出 {owners}"
                  f"｜候选 {','.join(row['candidate_owners'])}")
            for line in row["evidence"][:2]:
                print(f"        · {line}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
