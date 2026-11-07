#!/usr/bin/env python3
"""将模组使用的游戏 API 与运行时实现、字段和契约台账交叉核对。

通过 --mod 指定模组目录，--label 指定报告名称。方法存在、字段可访问及
接收者类型分别检查；同名方法无法确定 owner 时保留候选，不猜测具体类型。
"""

from __future__ import annotations

import argparse
import collections
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
DEFAULT_MOD = ('dist/isaac-eid-release-20260915/atmosphere/contents/010021C000B6A000/'
               'romfs/isaac_mods/mods/external item descriptions_836319872')
INVENTORY = 'docs/PC-Lua-API-对照清单.md'
#: 机器生成的 PC Lua API 清单（`tools/build_lua_api_inventory.py` 跑出来的）。
#: 与上面那份**人维护**的对照清单互为补充：清单可能漏，inventory 覆盖全（见链式那一段的判据 ②）。
API_INVENTORY = 'analysis/lua-api-inventory/inventory.json'
API_DIRS = ('runtime/src/interfaces/lua', 'runtime/source')

# PC 对照清单里的"状态"列取值（宽松匹配，清单里有多张表、列数不一）
READY_TOKENS = ('ready', 'hostverified', 'exact_class')
WEAK_TOKENS = ('experimental', 'partial', 'stub')


def load_inventory() -> dict[str, str]:
    """从 PC 对照清单里取 {Owner:Name: 状态}。清单有多张表，按行宽松解析。"""
    text = (ROOT / INVENTORY).read_text(encoding='utf-8', errors='replace')
    status: dict[str, str] = {}
    for line in text.splitlines():
        if not line.startswith('|'):
            continue
        names = re.findall(r'`([A-Za-z_][A-Za-z0-9_]*)[:.]([A-Za-z_][A-Za-z0-9_]*)`', line)
        if not names:
            continue
        low = line.lower()
        if any(t in low for t in READY_TOKENS):
            state = 'ready'
        elif any(t in low for t in WEAK_TOKENS):
            state = 'weak'
        elif '| — |' in line or '|—|' in line:
            state = 'missing'
        else:
            state = 'unknown'
        for owner, name in names:
            key = f'{owner}:{name}'
            # 同一条目可能出现在多张表里，取"最弱"的那个状态（保守）
            order = {'ready': 0, 'unknown': 1, 'weak': 2, 'missing': 3}
            if key not in status or order[state] > order[status[key]]:
                status[key] = state
    return status


def canonical_owner(owner: str) -> str:
    """owner 标签的归一口径：去下划线 + 小写。

    为什么需要（2026-09-16 实测）：PC 清单里这个族叫 `ItemConfigItem`，而我们的目录用
    `ItemConfig_Item` —— 两边逐字比对就会把**已经实现**的 `IsTrinket` 判成"缺失"，
    于是账本看起来"还缺 9 条"（其实只缺 4 条）。账本可信是这套验收的地基，所以按归一后比对。
    """
    return owner.replace("_", "").lower()


def load_catalog_entries() -> dict[str, dict[str, str]]:
    """Catalog 里 `Owner:Name` → `{id, maturity}`（`kDefaultApis[]` 之内）。

    需要 `id` 才能与"语义偏离表"（`api_deviation.cpp` 按 id 登记）对上。
    """
    text = (ROOT / 'runtime/src/interfaces/lua/api_catalog.cpp').read_text(encoding='utf-8', errors='replace')
    start = text.find('kDefaultApis[]')
    end = text.find('const ApiCatalog g_defaultCatalog', start)
    body = text[start:end if end > start else len(text)]
    domain_values = {
        'Global': 0, 'Mod': 1, 'Game': 2, 'Level': 3, 'Room': 4, 'ItemPool': 5,
        'Music': 6, 'Rng': 7, 'Persistence': 8, 'Input': 9, 'Diagnostic': 10,
        'Font': 11, 'Vector': 12, 'Sprite': 13, 'Isaac': 14, 'Seed': 15,
        # `Hud`（域 17，`Game:GetHUD()` 的返回值）、`ModMenu`（16）。
        # 真值源见 `runtime/src/interfaces/lua/api_descriptor.hpp` 的 `ApiDomain`。
        'ModMenu': 16, 'Hud': 17,
    }
    entries: dict[str, dict[str, str]] = {}
    pattern = re.compile(
        r'MakeId\(ApiDomain::(\w+),\s*(\d+),\s*(0x[0-9A-Fa-f]+)\).*?'
        r'"([A-Za-z_][A-Za-z0-9_]*)",\s*"([A-Za-z_][A-Za-z0-9_]*)"',
        re.DOTALL,
    )
    for match in pattern.finditer(body):
        domain, group, sequence, owner, name = match.groups()
        if domain not in domain_values:
            continue
        identifier = (domain_values[domain] << 24) | (int(group) << 16) | int(sequence, 16)
        entries[f'{canonical_owner(owner)}:{name}'] = {'id': f'0x{identifier:08X}'}
    return entries


def load_deviations() -> dict[str, dict[str, str]]:
    """`api_deviation.cpp` 的 id → `{kind, text}`。

    这是"② 语义不满足"的**标记来源**：有了它，报告才能区分"实现正确"与
    "实现但有已知偏离"，而不是靠人去读实现处的注释。
    """
    path = ROOT / 'runtime/src/interfaces/lua/api_deviation.cpp'
    if not path.is_file():
        return {}
    text = path.read_text(encoding='utf-8', errors='replace')
    deviations: dict[str, dict[str, str]] = {}
    # 2026-09-28 修：原来那条是 `((?:\s*"…"\s*)+)` —— 两端的 `\s*` 归谁都可以，
    # 于是一串拼接字符串之间的每个空白段都有两种归属 ⇒ 失败回溯时组合数**指数爆炸**。
    # 台账条目在变长（几十行拼接）之后越过了阈值 ⇒ `test_mod_api_gap_report`
    # 单模块跑了 25 分钟不出结果（实测栈在 `sre_ucs2_match`），**把所有门禁都挂住了**。
    # 修法：把分隔空白**只写一次**（`"…"(?:\s*"…")*`），归属唯一 ⇒ 回溯不爆炸。
    pattern = re.compile(
        r'\{\s*(0x[0-9A-Fa-f]{8})\s*,\s*ApiDeviationKind::(\w+)\s*,\s*'
        r'("(?:[^"\\]|\\.)*"(?:\s*"(?:[^"\\]|\\.)*")*)\s*\}'
    )
    for match in pattern.finditer(text):
        identifier, kind, raw = match.groups()
        pieces = re.findall(r'"((?:[^"\\]|\\.)*)"', raw)
        deviations[f'0x{int(identifier, 16):08X}'] = {'kind': kind, 'text': ''.join(pieces)}
    return deviations


def load_runtime_apis() -> set[str]:
    """**权威口径**：API Catalog 的 `kDefaultApis[]` 里登记过的 `Owner:Name`。

    为什么只认这张表：它是"本运行时暴露哪些 Lua API"的唯一来源（契约测试也在管它）。
    早先版本是"扫源码里所有 `X:Y` 字样"，结果**连注释里提到过的名字**都被当成已实现
    ——`Level:IsAltStage` 就这么被漏报过（清单里明明写着"未实现"）。
    """
    text = (ROOT / 'runtime/src/interfaces/lua/api_catalog.cpp').read_text(encoding='utf-8', errors='replace')
    start = text.find('kDefaultApis[]')
    end = text.find('const ApiCatalog g_defaultCatalog', start)
    body = text[start:end if end > start else len(text)]
    # owner 归一（见 `canonical_owner` 的说明）：PC 清单与我们目录对这个族的拼法不同。
    result = {f'{canonical_owner(owner)}:{name}'
              for owner, name in re.findall(r'"([A-Za-z_][A-Za-z0-9_]*)",\s*"([A-Za-z_][A-Za-z0-9_]*)"', body)}
    # VectorIndex明确回落元表，显式v:__sub也能访问；它们没有独立catalog ID。
    # 只读取真实注册代码，禁止将注释/任意源码提及当已实现；不影响其它owner。
    source = (ROOT / 'runtime/source/lua_runtime.cpp').read_text(encoding='utf-8')
    block = source.split('void RegisterVectorApi(lua_State* state) {', 1)[1].split('\n}', 1)[0].split('    lua_pop(state, 1);', 1)[0]
    block = re.sub(r'/\*[\s\S]*?\*/|//[^\n]*', '', block)
    registered = re.findall(r'PushHandler\([^;]+;\s*lua_setfield\(state, -2, "(__[a-z]+)"\);', block)
    result.update(f'vector:{name}' for name in registered if name not in ('__index', '__newindex'))
    return result


# --------------------------------------------------------------------------------------------
# Lua 注释剥离（2026-09-29 ）
#
# **为什么要它**：本文件历来"不做词法剥离"，于是**注释里的名字**会被当成真实调用。实测到的那条：
# `features/eid_api.lua:1004` 是一句文档注释
# `---This is for modded characters, whose name is best found by doing EntityPlayer:GetName()`
# —— 分诊器把它读成"模组在 `EntityPlayer` 这个接收者上调了 `GetName`"。那条**只有注释这一次**
# 调用，于是挂在"待人工"里、卡点写着"调用点在注释里"。危险的不是"多报一条"，是**证据指错地方**：
# 顺着证据的行号读回去，读到的是一句话，不是代码（谁复核都会被带偏）。
#
# **口径（三条，别自己改）**：
#   1. 只把**注释里的字符换成空格**，**逐字保持长度与换行**。行号、偏移、`文件:行号` 证据
#      因此全都不变 —— `chain_owner_triage._line_of()` 是靠偏移算行号的，长度一动就全线串位。
#   2. 只剥注释，不剥字符串。字符串里确实也可能有假调用（`print("a:GetName()")`），
#      但**字段面那一路是刻意依赖字符串字面量的**：`load_mod_field_usage()` 认
#      `obj["Field"]` 这个形态，必须读到 `"Field"` 本身。剥字符串会让整条字段路静默失效
#      ⇒ 代价远大于收益。**这一条别再"顺手优化"掉。**
#   3. 长注释 `--[[ … ]]` / `--[==[ … ]==]` 与行注释 `-- …` 都剥；**未闭合的长注释吃到文件尾**
#      （宁可多剥一整段，也不要留半截内容被后面的正则当成代码）。
#   4. 按用途分，不是"一律剥"：读代码（调用点 / 定义 / 赋值 / 循环）用 `lua_source()`；
#      读**注解**（`---@param` / `---@return` —— 它们本身就是注释）用 `lua_source_raw()`。
#      混用的前提是两者行号与偏移完全对齐（剥注释是等长替换）。**理由见 `lua_source_raw()`。**
#
# **怎么判"剥得对不对"**：把改动前后两侧的 `used` / `defined` / `chained` 各跑一遍做差集 ——
#   **只许少掉"落在注释里的那些"**，少掉别的一律按回归处理。实测差集见
#   `dist/change-archive-20260929/202-lua-comment-strip/README.md`。
# --------------------------------------------------------------------------------------------

#: 长括号的开头 `[[` / `[=[` / `[==[` …（捕获组是中间那串等号，闭合形式由它拼出来）。
_LONG_BRACKET_RE = re.compile(r'\[(=*)\[')

#: 读过的文件缓存 —— 一份模组会被 5 个 loader 各扫一遍，而剥注释是纯 Python 逐字符循环。
#: 键里带 `mtime_ns` 与 `size`：测试会把内容换掉再重跑，只按路径缓存会读到上一次的旧内容。
_LUA_SOURCE_CACHE: dict[tuple[str, int, int], str] = {}
_LUA_RAW_CACHE: dict[tuple[str, int, int], str] = {}


def _skip_long_bracket(text: str, start: int) -> int:
    """`start` 指向长括号里第一个 `[`；返回闭合之后的下一位（未闭合就停在文件尾）。

    长**注释** `--[[ … ]]` 与长**字符串** `[[ … ]]` / `[==[ … ]==]` 共用这一个跳过器。
    """
    match = _LONG_BRACKET_RE.match(text, start)
    if match is None:
        return start + 1
    close = ']' + match.group(1) + ']'
    found = text.find(close, match.end())
    return len(text) if found < 0 else found + len(close)


def _skip_short_string(text: str, start: int) -> int:
    """`start` 指向引号；返回这个短串之后的下一位（未闭合就停在行尾 / 文件尾）。

    ★ 它只用来**跳过**字符串，**不剥**它（口径第 2 条）。但"跳过"本身是必须的 ——
    不做这一步的话，`print("a--b")` 里的那个 `--` 会被当成本行的注释开头，
    把这一行剩下的代码全吃掉（**静默漏报**，正是本文件最怕的失败方式）。
    """
    quote = text[start]
    index = start + 1
    while index < len(text):
        char = text[index]
        if char == '\\':
            index += 2                      # 转义：不管下一个是什么，都不结束这个串
            continue
        if char == quote:
            return index + 1
        if char in '\r\n':
            return index                    # Lua 短串不许跨行：未闭合就停，别把整份文件吃掉
        index += 1
    return len(text)


def strip_lua_comments(text: str) -> str:
    """把 Lua 源码里**落在注释里的字符换成空格**；长度、换行、其余字符逐字不变。

    ★ 返回值与入参**等长**（不是"把注释删掉"）—— 这是 `文件:行号` 证据仍然有效的前提。
    ★ 字符串是"认出来并跳过"，不是"剥掉"：剥了会把字段面的 `obj["Field"]` 一并毁掉。
    """
    characters = list(text)
    index = 0
    length = len(text)
    while index < length:
        if text.startswith('--', index):
            # `--[[` / `--[==[` 是长注释；其余 `--…` 是行注释（到行尾，**不含**那个换行）。
            if _LONG_BRACKET_RE.match(text, index + 2):
                end = _skip_long_bracket(text, index + 2)
            else:
                newline = text.find('\n', index)
                end = length if newline < 0 else newline
            for position in range(index, end):
                if characters[position] not in '\r\n':
                    characters[position] = ' '
            index = end
        elif text[index] in '"\'':
            index = _skip_short_string(text, index)
        elif text[index] == '[' and _LONG_BRACKET_RE.match(text, index):
            index = _skip_long_bracket(text, index)
        else:
            index += 1
    return ''.join(characters)


def lua_source(path: pathlib.Path) -> str:
    """读一份模组 `.lua` 并剥掉注释 —— **扫"调用点 / 定义 / 用法"的都必须走它**。

    统一成一个入口的理由：口径只有一份；将来若真要加"剥字符串"的开关，也只在这里加。
    """
    stat = path.stat()
    key = (str(path), stat.st_mtime_ns, stat.st_size)
    cached = _LUA_SOURCE_CACHE.get(key)
    if cached is None:
        cached = strip_lua_comments(path.read_text(encoding='utf-8', errors='replace'))
        _LUA_SOURCE_CACHE[key] = cached
    return cached


def lua_source_raw(path: pathlib.Path) -> str:
    """读一份模组 `.lua` 的**原文（含注释）**。

    ★★ 为什么需要一个"不剥"的入口：**作者写的类型注解本身就是注释** ——
    `---@param entityPlayer EntityPlayer`、`---@return EntityPlayer?` 都是 `---` 开头。
    分诊器有两条类型来源（第五种 `@param`、第六种 `@return`）**必须读原文**，剥了它们就全废。
    2026-09-29（批次 202）实测踩到过：把这两处一起剥掉之后，
    `entityPlayer:GetName` / `sprite:Render` / `spriteObj:Render` **三条从"不是缺口"退回"待人工"**
    （`not_a_gap` 18 → 15、`manual` 7 → 9）—— 就是"结论变坏"，当场回退。

    所以口径是**按用途分**，不是"一律剥"：
      * **代码内容**（调用点、函数定义、赋值表达式、循环）⇒ `lua_source()`（剥注释）；
      * **注解内容**（`@param` / `@return`）⇒ 本函数（读原文）。
    两者的行号与偏移**完全对齐**（剥注释是等长替换），所以可以放心混用。
    """
    stat = path.stat()
    key = (str(path), stat.st_mtime_ns, stat.st_size)
    cached = _LUA_RAW_CACHE.get(key)
    if cached is None:
        cached = path.read_text(encoding='utf-8', errors='replace')
        _LUA_RAW_CACHE[key] = cached
    return cached


def load_mod_definitions(mod: pathlib.Path) -> set[str]:
    """模组**自己定义**的方法（要排除掉，否则会把模组内部函数当成游戏 API）。"""
    defined: set[str] = set()
    for path in mod.rglob('*.lua'):
        text = lua_source(path)
        for m in re.finditer(r'function\s+([A-Za-z_][A-Za-z0-9_]*)\s*[:.]\s*([A-Za-z_][A-Za-z0-9_]*)\s*\(', text):
            defined.add(f'{m.group(1)}:{m.group(2)}')
        for m in re.finditer(r'([A-Za-z_][A-Za-z0-9_]*)\s*[:.]\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*function', text):
            defined.add(f'{m.group(1)}:{m.group(2)}')
    return defined


def load_mod_usage(mod: pathlib.Path) -> collections.Counter:
    """模组里 `Owner:Name(` 形式的调用（只保留"看起来像游戏对象"的 owner）。

    注意这一路**只认"owner 是一个标识符"**的写法。`game:GetRoom():GetFrameCount()` 这种
    "在另一个调用的结果上再调方法"的链式写法由下面 `load_mod_chained_usage()` /
    `iter_chained_calls()` 那一套负责，两边合起来才是完整的方法面。
    """
    usage: collections.Counter = collections.Counter()
    for path in mod.rglob('*.lua'):
        text = lua_source(path)
        for m in re.finditer(r'([A-Za-z_][A-Za-z0-9_]*)\s*:\s*([A-Za-z_][A-Za-z0-9_]*)\s*\(', text):
            usage[f'{m.group(1)}:{m.group(2)}'] += 1
    return usage


def load_mod_dot_usage(mod: pathlib.Path, pc_catalog: dict[str, list[str]]
                       ) -> collections.Counter:
    """模组里 `Owner.Name(` 形式的**点号调用**（2026-09-19 补）。

    为什么单开一路：`load_mod_usage()` 只认 `Owner:Name(`（**冒号**）。而 PC 侧有一批 API 是
    **表上的函数**，模组按点号调用 —— `Isaac.GetPlayer(0)`、`Input.IsActionPressed(...)`、
    `Options.HUDOffset`、`ItemConfig.TAG_*` 都是这一类。原来整个形态扫不到：
    本工具的第一版在夹具里就漏掉了 `Isaac.GetScreenWidth()`（真机上它正是 GoodTrip 会用到的东西）。

    **判据**：`X.Name` 里的 `X` 必须**正是** PC 目录里这个方法的 owner 之一
    （`load_pc_method_catalog()` 给的候选里含 `X`）。这一条把 `EID.foo()`、`mymod.bar()`
    这类**模组自己的表调用**滤掉，同时不误伤 `Isaac.*`。

    与链式那一路的区别：这里 owner 是**确定的**（就是 `X` 本身）⇒ 进 `used` 并参与
    ① 缺口判定；链式那一路 owner 未知，只能报"方法名 + 候选"。
    """
    usage: collections.Counter = collections.Counter()
    for path in mod.rglob('*.lua'):
        text = lua_source(path)
        for m in re.finditer(r'([A-Za-z_][A-Za-z0-9_]*)\s*\.\s*([A-Za-z_][A-Za-z0-9_]*)\s*\(', text):
            owner, name = m.group(1), m.group(2)
            if owner not in (pc_catalog.get(name) or []):
                continue
            usage[f'{owner}:{name}'] += 1
    return usage


# --------------------------------------------------------------------------------------------
# 链式调用枚举（方法面的一部分，2026-09-16 补）
#
# 为什么单开一路：`load_mod_usage()` 认的是 `Owner:Name(` —— **要求 `:` 左边是一个标识符**。
# 模组里 `game:GetRoom():GetFrameCount()` 这种"**在另一个调用的结果上再调方法**"的写法，
# `:` 左边是 `)` 而不是标识符 ⇒ 正则扫不到 ⇒ `Room:GetFrameCount` 这条真实缺口
# **从来没进过任何清单**，直到 2026-09-16 真机上它每帧抛错才被发现
# （EID `features/eid_bagofcrafting.lua:967`，玩家一持有背包合成，EID 的渲染回调就每帧异常、
# 整段道具描述被打断；诊断见 `docs/问题与解决记录.md` 2026-09-16 续十八/续十九）。
#
# **判据（四道，缺一不可）：**
#
#   ① **形态**：`:` / `.` 这个访问器的**接收者以"表达式收尾字符"结束** —— 即 `)`、`]`、`}`。
#      也就是"在上一个表达式（多半是上一次调用）的结果上再取成员"。
#      接收者是标识符的（`player:HasCollectible(...)`）**不在这里**，它们本来就被上面那一路覆盖
#      ⇒ 这一路不是为了"多收一点"，而是为了覆盖一个**原来完全没覆盖的形态**。
#      没有把 `"`、`'` 算进收尾字符：Lua 里 `"x":upper()` 是**语法错误**（字符串是 `exp` 不是
#      `prefixexp`），收进来只会得到"字符串字面量后面恰好跟了个冒号"的噪音。
#   ② **真的被调用**：名字后面（跳过空白）必须紧跟 `(`。`a:b():c.d(...)` 里的 `c` 只是取成员、
#      `d` 才带参数列表 ⇒ 只记 `d`（链里"取成员"那一段不是调用，收了就是噪音）。
#   ③ **名字必须在 PC 侧存在**：见 `load_pc_method_catalog()`（人维护的对照清单 ∪ 机器生成的
#      inventory）。这条把 `t:gsub()`、`s:find()`、`x:modifierFunction()` 这类**模组自己的方法**
#      滤掉 —— 实测 EID 上原始命中 126 处 / 45 个名字，过滤后 94 处 / 35 个名字，
#      被滤掉的正是这些非游戏方法名。
#   ④ **模组自己定义过的方法名排除**（`load_mod_definitions()`）——与上面那一路同一口径。
#
# **口径：owner 未知。** 链式写法里接收者是"上一次调用的返回值"，静态**认不出类型**
# （`game:GetRoom()` 返回什么只有运行时知道）⇒ 这一路**只报方法名 + 候选 owner**，
# 绝不写死成 `Room:GetFrameCount`。报告里的"候选 owner"= PC 侧所有同名方法的 owner，
# 由人分诊（`GetFrameCount` 的候选是 Game/Isaac/Room，其中 Room 那条正是真机上炸掉的）。
#
# **已知假阳性来源（分诊时先想这几条，免得下一轮重新分诊一遍）：**
#   * `arr[i]:Method()` —— 接收者是**模组自己的表**（实测 EID 的 `EID.coopAllPlayers[i]:GetPlayerType()`、
#     `icon[1]:Play(...)`）。`]` 收尾同样落进这一路，名字恰好与游戏 API 同名时会被收进来。
#     判据是"数组里装的是什么"：装的是游戏对象就是真调用，装的是模组自制对象就是假阳性。
#   * **字符串里的同名字样仍然会被收进来**（`print("a:GetName()")` 这种）。**这是刻意保留的**：
#     注释已在起由 `lua_source()` 剥掉，但字符串不能剥 —— 字段面
#     `load_mod_field_usage()` 的 `obj["Field"]` 形态就靠字符串字面量（理由见上面 `lua_source`
#     那段口径的第 2 条）。实测 EID 上这一路**没有**字符串命中（剥注释前后都是 94 处），
#     但**换一个模组要先看这一条**（字段面那个 `.V1.9.7.7` 版本号假阳性同源）。
#   * `..` 连接符与 `::` 标签：`f(a)..b` 里的 `..` 会被当成"成员访问"，已用 `(?![:.])` 前瞻排除；
#     排除后没有名字可读 ⇒ 直接中止，不会产生条目（用例里有这条负对照）。
# --------------------------------------------------------------------------------------------

#: 链式调用的起点：访问器（`:` / `.`）的接收者以"表达式收尾字符"结束。
#: `(?![:.])` 是为了排除 `..` 连接符与 `::`（Lua 5.3 标签）——它们不是成员访问。
CHAIN_ROOT_RE = re.compile(r'([)\]}])\s*([:.])(?![:.])')
#: 链里一个成员的名字（访问器之后）。
CHAIN_MEMBER_RE = re.compile(r'\s*([A-Za-z_][A-Za-z0-9_]*)')


def _skip_balanced(text: str, start: int) -> int:
    """`start` 指向开括号，返回配对闭合括号的后一位；不做词法分析（够用，见上面的假阳性说明）。"""
    pairs = {'(': ')', '[': ']', '{': '}'}
    stack = [pairs[text[start]]]
    index = start + 1
    while index < len(text) and stack:
        char = text[index]
        if char in pairs:
            stack.append(pairs[char])
        elif char == stack[-1]:
            stack.pop()
        index += 1
    return index


def _skip_blank(text: str, start: int) -> int:
    index = start
    while index < len(text) and text[index] in ' \t\r\n':
        index += 1
    return index


def iter_chained_calls(text: str):
    """从 Lua 源码里吐出**链式调用**用到的方法名（接收者不是标识符的那些）。

    走法：找到"收尾字符 + 访问器"这个起点，然后沿链往后逐个成员走 ——
    成员后面跟 `(` 就算一次调用（并跳过参数表），跟 `[` 就跳过下标继续，
    后面还接 `:` / `.` 就继续走下一个成员，否则这条链到头。
    """
    for root in CHAIN_ROOT_RE.finditer(text):
        position = root.end()
        while True:
            member = CHAIN_MEMBER_RE.match(text, position)
            if member is None:
                break
            name = member.group(1)
            cursor = _skip_blank(text, member.end())
            if cursor < len(text) and text[cursor] == '(':
                yield name                      # 判据 ②：带参数列表 ⇒ 真的被调用
                cursor = _skip_balanced(text, cursor)
            elif cursor < len(text) and text[cursor] == '[':
                cursor = _skip_balanced(text, cursor)
            cursor = _skip_blank(text, cursor)
            if cursor < len(text) and text[cursor] in ':.':
                position = cursor + 1           # 链还没完（`a:b():c.d(` 的 `.d` 就是在这一步走到的）
                continue
            break


def load_pc_method_catalog() -> dict[str, list[str]]:
    """PC 侧 `方法名 → 候选 owner 列表` —— 链式那一路的过滤器（判据 ③）与候选来源。

    两个来源取并集，**缺一不可**：
      * `docs/PC-Lua-API-对照清单.md`（人维护的对照表；同一方法名常有多个 owner）；
      * `analysis/lua-api-inventory/inventory.json`（`tools/build_lua_api_inventory.py` 从 PC
        Lua 文档生成；`kinds` 含 `Functions` 的条目）。
    为什么两份都要：清单是人写的、可能漏；inventory 是机器生成的、覆盖全但只有"主 owner"。
    只认其中一份，就会重新制造"某条真实缺口扫不到"的老问题 —— 这正是本次要修的东西。
    """
    catalog: dict[str, list[str]] = collections.defaultdict(list)

    def remember(owner: str, name: str) -> None:
        if owner and name and owner not in catalog[name]:
            catalog[name].append(owner)

    text = (ROOT / INVENTORY).read_text(encoding='utf-8', errors='replace')
    for line in text.splitlines():
        if not line.startswith('|'):
            continue
        # 对照清单第 2 列是种类。`Variables` 行是**字段**，不是方法 —— 链式判据 ③ 收它进来
        # 只会让过滤变松（`obj:Quality()` 根本不是 PC 上的写法），所以这里显式排掉。
        cells = [cell.strip() for cell in line.strip().strip('|').split('|')]
        if len(cells) >= 2 and cells[1] == 'Variables':
            continue
        for owner, name in re.findall(r'`([A-Za-z_][A-Za-z0-9_]*)[:.]([A-Za-z_][A-Za-z0-9_]*)`', line):
            remember(owner, name)

    path = ROOT / API_INVENTORY
    if path.is_file():
        table = json.loads(path.read_text(encoding='utf-8'))
        for entry in table.get('apis', []):
            if 'Functions' in (entry.get('kinds') or []):
                remember(str(entry.get('owner', '')), str(entry.get('name', '')))

    return dict(catalog)


def load_mod_chained_usage(mod: pathlib.Path) -> collections.Counter:
    """模组里**链式调用**用到的方法名（判据 ①②③；owner 未知，见上面那一段）。"""
    known = load_pc_method_catalog()
    usage: collections.Counter = collections.Counter()
    for path in mod.rglob('*.lua'):
        text = lua_source(path)
        for name in iter_chained_calls(text):
            if name in known:
                usage[name] += 1
    return usage


def audit_chained_calls(mod: pathlib.Path, pc_catalog: dict[str, list[str]] | None = None) -> dict:
    """链式调用这一路的结论：认出来的方法名、候选 owner、候选里我们没实现的那些。

    **为什么这一路不进 `--strict`**：`--strict` 现在只对**字段面**（第 ⑤ 段）判"未登记 ⇒ 失败"，
    而字段缺口的处置台账 `tools/api_surface_ledger.json` 是**按字段名**建的（`Variables` 节）。
    链式调用是**方法**，它没有对应的台账行；直接把它接进 `--strict` 会让门禁**长期红着**
    （CONTRIBUTING 明确说"否则门禁会红着，等于没有"）。所以这一轮先把它们**枚举出来、报出来**，
    要不要给方法缺口也建一本台账、怎么与 `ApiCatalog` 对齐，属于口径变更，另行决定。
    """
    usage = load_mod_chained_usage(mod)
    defined_names = {key.split(':', 1)[1] for key in load_mod_definitions(mod)}
    runtime_apis = load_runtime_apis()
    #: 调用方（`main`）已经解析过一遍 PC 目录 ⇒ 传进来复用；单独调用时自己解析。
    catalog = pc_catalog if pc_catalog is not None else load_pc_method_catalog()

    rows = []
    for name, count in sorted(usage.items(), key=lambda item: (-item[1], item[0])):
        if name in defined_names:
            continue                    # 判据 ④：模组自己定义过的方法，不是游戏 API
        candidates = catalog.get(name, [])
        missing = [owner for owner in candidates
                   if f'{canonical_owner(owner)}:{name}' not in runtime_apis]
        rows.append({
            'api': f'?:{name}',         # `?` = owner 未知（刻意不猜，见上面的口径说明）
            'name': name,
            'calls': count,
            'candidate_owners': candidates,
            # 候选 owner 里"我们运行时没有"的 —— 这一路真正的信号：可能是缺口，要人分诊。
            'missing_owners': missing,
            # **高置信判据**：所有候选 owner 都缺 ⇒ 不管接收者是谁都跑不通 ⇒ 几乎可以断定是缺口。
            # 反例（为什么需要这个字段）：`icon[1]:Update(...)` 的接收者是 Sprite，而 `Sprite:Update`
            # 我们实现了 —— 但候选 owner 里有 Room/Game/Level/HUD/GridEntity 都缺，
            # 不分开的话 `Update` 会一直挂在"缺口"里，看的人会以为它没实现。
            'every_candidate_missing': bool(candidates) and len(missing) == len(candidates),
        })

    with_gap = [row for row in rows if row['missing_owners']]
    return {
        'pc_method_names': len(catalog),
        'names': len(rows),
        'with_candidate_gap': with_gap,
        'every_candidate_missing': [row for row in with_gap if row['every_candidate_missing']],
        'rows': rows,
    }


# --------------------------------------------------------------------------------------------
# 接口面枚举（"第 0 维"，2026-09-16 新增）
#
# 为什么单开一段：三维验收（存在 / 语义 / 时机）问的是"**这一条**接口对不对"，它默认
# **接口清单本身是全的**。而原来的清单只覆盖方法（`obj:Method(`）：字段（PC 文档里的
# `Variables`，例如 `ItemConfig_Item.Quality`）在模组源码里的写法是 `obj.Field`，
# 既匹配不上方法提取的那个正则，也不在 `ApiCatalog`（目录只登记方法）⇒ **从来没被问过**。
# 表现：EID 读 `.Quality` 拿到 nil，被 `and desc.Quality` 短路，静默少一块品质图标。
# 过程记录见 `docs/错误复盘.md` 2026-09-16。这一段把"字段面"补成可枚举、可登记、可门禁的路。
# --------------------------------------------------------------------------------------------

LEDGER_PATH = 'tools/api_surface_ledger.json'
LUA_IMPL_DIR = 'runtime/src/interfaces/lua'
LAYOUT_TABLE_DIR = 'tools/layout_tables'
#: 语料模组的**范围声明**（target / deferred）—— 见 `load_scope()` 的说明。
SCOPE_PATH = 'tools/mod_corpus_scope.json'
CORPUS_DIR = 'analysis/mod-corpus'

#: 模组侧的字段读取形态：`obj.Field` 与 `obj["Field"]`。
#: 与 `load_mod_usage()` 同一套思路 —— 不做 owner 解析（模组里的对象多是局部变量），
#: 只按名字收，再由调用方拿"PC 契约里的变量名"过滤。
FIELD_DOT_RE = re.compile(r'\.\s*([A-Za-z_][A-Za-z0-9_]*)')
FIELD_BRACKET_RE = re.compile(r'\[\s*"([A-Za-z_][A-Za-z0-9_]*)"\s*\]')

#: 运行时侧的"确实在对外提供字段"的两种写法（实测穷举出来的，别删其中任一）：
#:   ① `{"Name", offsetof(...)}` —— `kColorFields` / `kEntityFields` / `ItemConfig::Item` 字段表；
#:   ② `strcmp(<表达式>, "Name")` —— `PushItemField` / `RoomDescriptorIndex` / `Vector` 分派。
#: 只认其中一种会误报（第一版只认 ②，于是 `Color.A`、`Vector.X` 这种被当成缺口）。
CARRIER_TABLE_RE = re.compile(r'\{\s*"([A-Za-z_][A-Za-z0-9_]*)"\s*,')
CARRIER_STRCMP_RE = re.compile(r'strcmp\s*\([^,]+,\s*"([A-Za-z_][A-Za-z0-9_]*)"\s*\)')

#: 运行时侧的**第三种**载体写法（2026-09-16 补）：命名常量 + 用它做名字分派。
#:
#:     constexpr char kSpriteColorField[] = "Color";
#:     if (std::strcmp(field, kSpriteColorField) == 0) { ... }
#:
#: **为什么必须认它**：`Sprite.Color` / `Sprite.FlipX` 在 2026-09-16 的"引擎写通道"批次里真的
#: 实现了（`sprite_api.cpp` 的 `SpriteNewIndex` 把这三个字段写进 `ANM2`），但上面两种写法只认
#: **字面量**，于是工具看不见 ⇒ 台账里那两条"已完成"的条目删不掉（一删就变成"未登记缺口"，
#: 门禁反过来变红）。**漏报**是这条路最危险的失败方式（见文件开头），所以补上这一种。
#:
#: 判据紧贴实现、不放松：常量名必须以 `Field` 结尾，值必须是纯标识符字符串
#: （`"Color"` 算，`"some path/with spaces"` 不算），且**必须真的被同文件里的 `strcmp` 用到**
#: —— 只声明不使用的常量不算载体。
CARRIER_NAMED_CONSTANT_RE = re.compile(r'constexpr\s+char\s+(k\w*Field)\s*\[\s*\]\s*=\s*"(\w+)"')
CARRIER_NAMED_CONSTANT_USE_RE = re.compile(r'strcmp\s*\([^,]+,\s*(k\w*Field)\s*\)')


def load_variable_owners() -> dict[str, list[str]]:
    """PC 对照清单里 `Variables` 行的 `字段名 → 可能归属的 owner 列表`。

    与 `load_inventory()`（服务于方法）分开：这一份只收变量/字段，并保留 owner 线索。
    保留 owner 只是**候选提示** —— 工具分不出模组里 `desc.Quality` 的 `desc` 到底是哪一家，
    所以判定按名字做，owner 写进报告供人工分诊。
    """
    text = (ROOT / INVENTORY).read_text(encoding='utf-8', errors='replace')
    owners: dict[str, list[str]] = collections.defaultdict(list)
    for line in text.splitlines():
        if not line.startswith('|'):
            continue
        cells = [cell.strip() for cell in line.strip().strip('|').split('|')]
        if len(cells) < 2 or cells[1] != 'Variables':
            continue
        for owner, name in re.findall(r'`([A-Za-z_]\w*)[:.]([A-Za-z_]\w*)`', cells[0]):
            if owner not in owners[name]:
                owners[name].append(owner)
    return owners


def load_mod_field_usage(mod: pathlib.Path) -> collections.Counter:
    """模组里 `obj.Field` / `obj["Field"]` 形态的字段读取（按名字计数）。"""
    usage: collections.Counter = collections.Counter()
    for path in mod.rglob('*.lua'):
        text = lua_source(path)
        usage.update(FIELD_DOT_RE.findall(text))
        usage.update(FIELD_BRACKET_RE.findall(text))
    return usage


def load_implemented_fields() -> set[str]:
    """本运行时会对外提供哪些字段名（载体口径）。

    三类代码形态 + 一张数据表，缺一不可：
      1. `{"Name", offsetof(...)}` 静态字段表；
      2. `strcmp(<表达式>, "Name")` 名字分派；
      3. `constexpr char kXxxField[] = "Name"` + `strcmp(<表达式>, kXxxField)` 命名常量分派
         （见 `CARRIER_NAMED_CONSTANT_RE` 的注释：`Sprite` 那三个可写字段就是这么写的）；
      4. `tools/layout_tables/*.json` 里**已复核为 `confirmed`** 的结构体字段（带偏移证据）。
    口径故意只认这四种 —— 宽松到"扫文件里所有标识符字面量"会把普通字符串也算进来，
    造成"看着实现了其实没有"的假阴性（漏报缺口比误报更危险）。

    ★ **2026-09-19 批次 047 收紧**：第 4 条以前认**任何**一行（不分 confidence），于是
    `candidate` 行也被算成"已实现" —— 而项目的规矩恰恰是"`candidate` 只登记、**不进对外 API**"。
    真被这条咬过一次：`RoomDescriptor.DisplayFlags`（+0x48）当时是 `candidate`，在报告里被记成
    `in_runtime=true`，于是它既不在"未登记缺口"里、也不需要台账行，**门禁永远看不见它**；
    直到 GoodTrip 真机上因为读它拿到 nil 而报 `attempt to compare number with nil` 才暴露。
    改法：只认 `confidence == "confirmed"`（缺 confidence 的旧表按 confirmed 处理，保持兼容）。
    """
    names: set[str] = set()
    for path in sorted((ROOT / LUA_IMPL_DIR).glob('*.cpp')):
        text = path.read_text(encoding='utf-8', errors='replace')
        names.update(CARRIER_TABLE_RE.findall(text))
        names.update(CARRIER_STRCMP_RE.findall(text))
        # 形态 ③：常量先"声明 → 值"，再要求同文件里真的有 `strcmp(…, 常量)` 用它。
        constant_values = dict(CARRIER_NAMED_CONSTANT_RE.findall(text))
        for constant in CARRIER_NAMED_CONSTANT_USE_RE.findall(text):
            value = constant_values.get(constant)
            if value:
                names.add(value)
    for path in sorted((ROOT / LAYOUT_TABLE_DIR).glob('*.json')):
        table = json.loads(path.read_text(encoding='utf-8'))
        for row in table.get('rows', []):
            # 只有 confirmed 的行才允许进对外 API（与 `build_layout_table.py` 的
            # `API_ALLOWED_CONFIDENCE` 同一条口径）。
            if str(row.get('confidence', 'confirmed')) != 'confirmed':
                continue
            name = str(row.get('name', ''))
            if name:
                names.add(name.split('.')[-1])          # `Data.Type` 记成 `Type`
            if row.get('nested_in'):
                names.add(str(row['nested_in']))
    return names


def load_surface_ledger(path: pathlib.Path | None = None) -> dict[str, dict]:
    """人工分诊台账：字段名 → 处置条目（`tools/api_surface_ledger.json`）。

    为什么处置必须落盘成文件、而不是停在报告里：**"补 / 不补"是人的判断，不是工具的结论**。
    工具只能说"模组读了它、我们没实现"；要不要补、什么时候补、为什么不补，得有人负责。
    门禁（`runtime/tests/test_api_surface_ledger.py`）要求两者**一一对应**：
    没有台账条目的缺口 ⇒ 红；台账里已经实现或模组已不再用的条目 ⇒ 也红（过期条目要清掉）。
    """
    path = path if path is not None else (ROOT / LEDGER_PATH)
    if not path.is_file():
        return {}
    table = json.loads(path.read_text(encoding='utf-8'))
    return {str(row['name']): row for row in table.get('rows', [])}


def audit_field_surface(mod: pathlib.Path,
                        ledger: dict[str, dict] | None = None) -> dict:
    """算出字段面的四个集合：已实现 / 已登记 / **未登记缺口** / 过期台账条目。"""
    usage = load_mod_field_usage(mod)
    owners_of = load_variable_owners()
    implemented = load_implemented_fields()
    ledger = load_surface_ledger() if ledger is None else ledger

    used: dict[str, dict] = {}
    for name, count in usage.items():
        if name not in owners_of:
            continue                    # 名字不在 PC 契约的变量节里 ⇒ 不是游戏字段
        used[name] = {
            'name': name,
            'calls': count,
            'owners': owners_of[name],
            'in_runtime': name in implemented,
        }

    implemented_rows = [row for row in used.values() if row['in_runtime']]
    registered, unregistered = [], []
    for row in used.values():
        if row['in_runtime']:
            continue
        entry = ledger.get(row['name'])
        if entry is None:
            unregistered.append(row)
        else:
            registered.append({**row, 'disposition': entry.get('disposition', ''),
                               'why': entry.get('why', '')})

    stale = []
    for name, entry in ledger.items():
        row = used.get(name)
        if row is None:
            stale.append({'name': name, 'why_stale': '模组当前没读到这个字段（或它不在 PC 契约的变量节里）'})
        elif row['in_runtime']:
            stale.append({'name': name, 'why_stale': '运行时已经实现了这个字段，台账条目该删掉'})

    return {
        'variable_names_in_pc_contract': len(owners_of),
        'used': sorted(used.values(), key=lambda item: (-item['calls'], item['name'])),
        'implemented': implemented_rows,
        'registered': registered,
        'unregistered': sorted(unregistered, key=lambda item: (-item['calls'], item['name'])),
        'stale_ledger_rows': stale,
        'ledger_size': len(ledger),
    }


# --------------------------------------------------------------------------------------------
# 2026-09-25：把"字段缺口必须被分诊"从默认模组扩到多模组
#
# 为什么：上一版的门禁只拿默认模组（EID）核对"缺口 ↔ 台账"一一对应 ⇒ 语料模组的字段缺口
# **会被打印、但没有任何闸门逼人分诊**（`EntityPickup.Wait` 就是这么漏过去的，而它还是个
# "写入即抛错"的真缺陷）。实测 16 个语料模组合计 **146** 处未登记缺口 ⇒ "每个模组都必须
# 零缺口"这种门禁当场装不上去。
#
# 所以改成 **"每个模组必须被显式声明"**（`tools/mod_corpus_scope.json`）：
#   * `target`   —— 我们在接/已接它 ⇒ 它的缺口必须逐条进台账（未登记即红）；
#   * `deferred` —— 还没接 ⇒ 只要求点名 + 写理由（沉默消失了，成本也压得住）。
# 同时把"台账条目过期"的判据从"默认模组不再读"改成"**所有**已声明模组都不再读"，
# 因为台账是按**字段名**建的、是全局的，而"模组不再读它"是**单个模组**的性质。
# --------------------------------------------------------------------------------------------


def load_scope() -> dict[str, dict]:
    """读语料模组的范围声明（相对路径 → 那一行）。口径见上面那一段注释。"""
    path = ROOT / SCOPE_PATH
    if not path.is_file():
        return {}
    table = json.loads(path.read_text(encoding='utf-8'))
    return {str(row['path']): row for row in table.get('mods', [])}


def corpus_mod_paths() -> list[str]:
    """语料目录下所有模组的相对路径（排序稳定；含**没有**未登记缺口的那些）。"""
    root = ROOT / CORPUS_DIR
    if not root.is_dir():
        return []
    return sorted(f'{CORPUS_DIR}/{child.name}' for child in root.iterdir() if child.is_dir())


def audit_multi_mod_field_surface(mods: list[str], ledger: dict[str, dict] | None = None) -> dict:
    """跨模组看字段面：每个模组的未登记缺口 + **对哪个模组都不再成立**的台账条目。"""
    ledger = load_surface_ledger() if ledger is None else ledger
    per_mod: dict[str, dict] = {}
    ever_used: set[str] = set()
    ever_implemented: set[str] = set()
    for mod_path in mods:
        report = audit_field_surface(ROOT / mod_path, ledger)
        per_mod[mod_path] = report
        ever_used.update(row['name'] for row in report['used'])
        ever_implemented.update(row['name'] for row in report['implemented'])
    globally_stale = []
    for name in ledger:
        if name in ever_implemented:
            globally_stale.append(
                {'name': name, 'why_stale': '运行时已经实现了这个字段，台账条目该删掉'})
        elif name not in ever_used:
            globally_stale.append(
                {'name': name,
                 'why_stale': '所有已声明的模组都没读到这个字段（或它不在 PC 契约的变量节里）'})
    return {
        'mods': list(mods),
        'per_mod': per_mod,
        'globally_stale': sorted(globally_stale, key=lambda item: item['name']),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--mod', default=DEFAULT_MOD)
    ap.add_argument('--label', default=None,
                    help='报告里用的模组名（默认取模组目录名）')
    ap.add_argument('--json', default=None,
                    help='报告落点（默认 dist/<label>-api-gap-report.json）')
    ap.add_argument('--top', type=int, default=40)
    ap.add_argument('--ledger', default=LEDGER_PATH, help='接口面台账（人工分诊结论）')
    ap.add_argument('--strict', action='store_true',
                    help='存在"未登记缺口"或过期台账条目时以退出码 1 结束（门禁用法）')
    args = ap.parse_args()

    mod = ROOT / args.mod
    if not mod.is_dir():
        print(f'模组目录不存在：{args.mod}')
        return 2
    #: 报告里用的模组名：默认取目录名（EID 的目录名很长，所以允许 --label 覆盖）。
    label = args.label or mod.name
    if args.json is None:
        args.json = f'dist/{label}-api-gap-report.json'

    inventory = load_inventory()
    runtime_apis = load_runtime_apis()
    catalog_entries = load_catalog_entries()
    deviations = load_deviations()
    defined = load_mod_definitions(mod)
    # 方法面三条路合起来才完整：`Owner:Name(`（冒号，owner 确定）、`Owner.Name(`（点号，owner 确定，
    # 2026-09-19 补）、链式 `a:b():c(`（owner 未知，另段处理）。
    pc_catalog = load_pc_method_catalog()
    usage = load_mod_usage(mod)
    usage.update(load_mod_dot_usage(mod, pc_catalog))

    # 判据：**按方法名**匹配 PC 目录（模组里 `player:GetPlayerType()` 的 owner 是局部变量，
    # 拿 owner 去卡会把绝大多数调用滤掉 —— 第一版就是这么只剩 3 条的）。
    # 模组自己定义过的方法名要排除；同名方法可能属于多个 owner，全部列出来。
    owners_of: dict[str, list[str]] = collections.defaultdict(list)
    for key in inventory:
        owner, name = key.split(':', 1)
        owners_of[name].append(owner)
    defined_names = {k.split(':', 1)[1] for k in defined}

    rows = []
    for key, count in usage.items():
        owner, name = key.split(':', 1)
        if key in defined or name in defined_names:
            continue                    # 模组自己的方法
        if name not in owners_of:
            continue                    # 方法名不在 PC 目录里 ⇒ 不是游戏 API
        for candidate_owner in owners_of[name]:
            api = f'{candidate_owner}:{name}'
            identifier = catalog_entries.get(f'{canonical_owner(candidate_owner)}:{name}', {}).get('id', '')
            deviation = deviations.get(identifier) if identifier else None
            rows.append({
                'api': api,
                'called_as': key,
                'calls': count,
                'pc_status': inventory.get(api, 'unknown'),
                'in_runtime': f'{canonical_owner(candidate_owner)}:{name}' in runtime_apis,
                # ② 语义维的标记：有实现、但**已知与 PC 语义不同**（差在哪见 `text`）。
                'deviation_kind': deviation['kind'] if deviation else '',
                'deviation': deviation['text'] if deviation else '',
                # `Get`/`Set` 这类通用方法名会在目录里属于很多 owner，凭方法名对不上真实类型，
                # 只能算"低置信参考"，不进主清单。
                'confident': len(owners_of[name]) == 1,
            })

    missing = [r for r in rows if not r['in_runtime'] and r['confident']]
    missing_lowconf = [r for r in rows if not r['in_runtime'] and not r['confident']]
    # ①b 这一档按接收者类型分诊（`tools/chain_owner_triage.py`）。
    #   为什么必须分诊：这一档原先只能报"方法名 + 所有同名 owner 的候选"，于是 `Update` / `Render` /
    #   `Get` 这种通用名长期挂着 —— 排期时既不敢做、也不敢划掉。分诊器只从三种来源定类型
    #   （全局表 / 构造式全局调用 / `<已知类型的根> + 一串方法调用`；赋值形状 `local x = …`、
    #   `表.字段 = …`、`X = …` 都收 —— 把后两种补上，并把"构造式全局调用"真的实现），
    #   **推不动就停在"待人工"**，绝不写死 owner。
    #   分诊成"不是缺口"的行从这个清单里移出去，分诊成"真缺口"的并进 ① 主清单。
    triage_result = None
    verdict_by_api: dict[str, str] = {}
    try:
        import chain_owner_triage
        triage_result = chain_owner_triage.triage(mod)
        verdict_by_api = {row['called_as']: row['verdict'] for row in triage_result['triaged']}
    except (ImportError, OSError, ValueError) as error:
        print(f'  ⚠ 接收者分诊没跑起来（{error}）⇒ ①b 这一档只有原始候选，没有结论')
    if verdict_by_api:
        resolved_gaps = [r for r in missing_lowconf if verdict_by_api.get(r['called_as']) == 'gap']
        not_a_gap = [r for r in missing_lowconf if verdict_by_api.get(r['called_as']) == 'not_a_gap']
        missing = missing + resolved_gaps
        moved = {r['called_as'] for r in resolved_gaps} | {r['called_as'] for r in not_a_gap}
        missing_lowconf = [r for r in missing_lowconf if r['called_as'] not in moved]
        lowconf_not_a_gap = len(not_a_gap)
        lowconf_resolved_gap = len(resolved_gaps)
    else:
        lowconf_not_a_gap = 0
        lowconf_resolved_gap = 0
    weak = [r for r in rows if r['in_runtime'] and r['pc_status'] in ('weak', 'missing')]
    unknown = [r for r in rows if r['in_runtime'] and r['pc_status'] == 'unknown']
    # ④：**EID 确实用到、且我们已知语义有偏离**的条目（每条都带"差在哪"）。
    # 与 ② 的区别：② 是"PC 清单里标 weak/unknown"（外部证据弱），
    # ④ 是"我们自己明确知道返回值与 PC 不同"（内部已承认的偏离）——后者才是必须标记的不满足。
    deviating = [r for r in rows if r['deviation'] and r['confident']]

    print(f'{label} 用到的游戏 API：{len(rows)} 条'
          f'（去掉了模组自建方法 {len(defined)} 条、非游戏 owner）')
    print(f'  ① 运行时里找不到（高置信）：{len(missing)} 条  ← 调用会直接报错，落在条件回调里会让整条描述消失')
    print(f'  ①b 同名方法多 owner、无法凭名字定类型（低置信参考）：{len(missing_lowconf)} 条'
          + (f'（原 {len(missing_lowconf) + lowconf_not_a_gap + lowconf_resolved_gap} 条：'
             f'**{lowconf_not_a_gap} 条已分诊为"不是缺口"**（接收者类型推得出来、我们都实现了）、'
             f'{lowconf_resolved_gap} 条分诊成真缺口（已并进 ①））' if triage_result else ''))
    print(f'  ② 有实现但 PC 状态偏弱（Experimental/—）：{len(weak)} 条')
    print(f'  ③ 状态未知（清单里没查到）：{len(unknown)} 条')
    print(f'  ④ 有实现、但**已知与 PC 语义偏离**（② 维的不满足标记）：{len(deviating)} 条')
    print()
    print('== ① 运行时里找不到的（按调用次数）==')
    for r in sorted(missing, key=lambda x: -x['calls'])[:args.top]:
        print(f"   {r['api']:34} 调用 {r['calls']:4} 次   PC 状态={r['pc_status']}")
    if weak:
        print('\n== ② 有实现但没底的 ==')
        for r in sorted(weak, key=lambda x: -x['calls'])[:args.top]:
            print(f"   {r['api']:34} 调用 {r['calls']:4} 次   PC 状态={r['pc_status']}")
    if deviating:
        print('\n== ④ 已知语义偏离（差在哪、后果是什么）==')
        for r in sorted(deviating, key=lambda x: -x['calls'])[:args.top]:
            print(f"   {r['api']:34} 调用 {r['calls']:4} 次  [{r['deviation_kind']}]")
            print(f"      {r['deviation']}")

    surface = audit_field_surface(mod, load_surface_ledger(ROOT / args.ledger))
    print()
    print(f"== ⑤ 接口面（字段 / PC 契约的 Variables 节）==")
    print(f"   PC 契约里的字段名 {surface['variable_names_in_pc_contract']} 个；"
          f"模组读到 {len(surface['used'])} 个；台账登记 {surface['ledger_size']} 条")
    print(f"   ✅ 已实现：{len(surface['implemented'])} 条")
    print(f"   📝 已登记：{len(surface['registered'])} 条（人工处置过，见台账）")
    print(f"   ❌ 未登记缺口：{len(surface['unregistered'])} 条"
          f"    ← 模组读了、我们没实现、也还没人处置的，必须进台账")
    for r in surface['unregistered'][:args.top]:
        print(f"      {r['name']:24} 读 {r['calls']:4} 次   候选归属 {'/'.join(r['owners'])}")
    if surface['stale_ledger_rows']:
        # 起口径修正：台账是按字段名建的全局台账 ⇒ "本模组不再读它"
        # 不是删除条目的理由（别的模组可能还在读 —— `EntityPickup.Wait` 就属于这种）。
        # 这里照旧列出来，是为了让读者看到"本模组没用到这些"；`--strict` 用的是全局判据
        # （所有已声明模组都不再读、或运行时已实现，见本文件"多模组"那一段）。
        print(f"   ℹ️ 台账条目里本模组没用上的：{len(surface['stale_ledger_rows'])} 条"
              f"（**不足以判定该删**；全局过期判据见 --strict）")
        for r in surface['stale_ledger_rows'][:args.top]:
            print(f"      {r['name']:24} {r['why_stale']}")
    # 范围声明：这条模组是被要求"逐条分诊"（target），还是只声明了"还没接"（deferred）。
    # 不说清这一点，上面那句"必须进台账"就只对默认模组成立，读者会以为对谁都成立。
    scope = load_scope()
    try:
        relative_mod = str(mod.resolve().relative_to(ROOT.resolve()))
    except ValueError:
        relative_mod = str(args.mod)
    scope_row = scope.get(relative_mod)
    labels = {'target': '我们在接它 ⇒ 它的缺口必须逐条进台账',
              'deferred': '还没接 ⇒ 只要求声明 + 理由（接它时改成 target）'}
    if scope_row:
        status = str(scope_row.get('status'))
        print(f"   范围声明：status={status}（{labels.get(status, '取值未知 —— 门禁会红')}）")
    elif relative_mod != DEFAULT_MOD:
        print(f"   ⚠️ 这个模组**不在** {SCOPE_PATH} 的声明里 ⇒ 它的 {len(surface['unregistered'])} 处"
              f"缺口没人被要求分诊（门禁会红：每个语料模组都必须被声明）")

    # ⑥：**链式调用**（`a:b():c(` 这类，接收者是上一次调用的返回值）——原来整个形态都扫不到。
    # 只报"方法名 + 候选 owner + 候选里的缺口"，不猜 owner（判据与假阳性来源见上面那一段注释）。
    chained = audit_chained_calls(mod, pc_catalog)
    high = chained['every_candidate_missing']
    partial = [r for r in chained['with_candidate_gap'] if not r['every_candidate_missing']]
    print()
    print('== ⑥ 链式调用（`a:b():c(` / `(expr):c(`，接收者是上次调用的返回值 ⇒ owner 未知）==')
    print(f"   模组里认到 {chained['names']} 个方法名；其中 {len(high)} 个**所有**候选 owner 都没有"
          f"（高置信缺口），另有 {len(partial)} 个只有部分候选缺（多半不是缺口）")
    for r in high[:args.top]:
        owners = '/'.join(r['candidate_owners']) or '（PC 清单里没有 owner 线索）'
        print(f"      {r['name']:30} 链式调用 {r['calls']:3} 次   候选 owner：{owners}")
        print(f"         ✗ 全缺：{'、'.join(o + ':' + r['name'] for o in r['missing_owners'])}")
    if partial:
        print('   以下方法名只有**部分**候选 owner 缺 —— 接收者很可能正好落在已实现的那家，'
              '多半不是缺口（要看链的接收者到底是什么类型才能定）：')
        for r in partial[:args.top]:
            print(f"      {r['name']:30} 链式调用 {r['calls']:3} 次   候选 owner："
                  f"{'/'.join(r['candidate_owners'])}   缺：{'、'.join(r['missing_owners'])}")

    out = ROOT / args.json
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({'mod': args.mod, 'label': label, 'used': rows, 'missing_in_runtime': missing,
                               'missing_low_confidence': missing_lowconf,
                               'chain_owner_triage': ({
                                   'pc_signatures': triage_result['pc_signatures'],
                                   'rows': triage_result['rows'],
                                   'by_verdict': triage_result['by_verdict'],
                               } if triage_result else None),
                               'weak_status': weak, 'unknown_status': unknown,
                               'semantic_deviations': deviating,
                               'field_surface': surface,
                               'chained_calls': chained},
                              ensure_ascii=False, indent=1), encoding='utf-8')
    print(f'\n报告已写：{out}')

    if args.strict:
        # `--strict` 的判据从"只看默认模组"扩到多模组：
        #   * `target` 的模组（含默认模组）⇒ 未登记缺口一律算失败；
        #   * 台账条目 ⇒ 只有"**所有**已声明模组都不再读 / 都已实现"才算过期
        #     （台账是按字段名建的、是全局的；只按某一个模组判会把"别的模组在读"的条目误判成过期）。
        scope = load_scope()
        ledger_rows = load_surface_ledger(ROOT / args.ledger)
        all_mods = corpus_mod_paths() + [DEFAULT_MOD]
        multi = audit_multi_mod_field_surface(all_mods, ledger_rows)
        must_triage = [name for name in all_mods
                       if name == DEFAULT_MOD or scope.get(name, {}).get('status') == 'target']
        offenders = {name: [r['name'] for r in multi['per_mod'][name]['unregistered']]
                     for name in must_triage}
        offenders = {name: names for name, names in offenders.items() if names}
        if offenders or multi['globally_stale']:
            print('\n门禁未通过（接口面 / 第 0 维）：', file=sys.stderr)
            for name, names in offenders.items():
                shown = '、'.join(names[:8]) + (' …' if len(names) > 8 else '')
                print(f'  {name} 有 {len(names)} 处未登记字段缺口 —— 它是'
                      f'{"默认模组" if name == DEFAULT_MOD else "target 模组"}，必须逐条进台账：{shown}',
                      file=sys.stderr)
            for row in multi['globally_stale']:
                print(f'  台账条目过期：{row["name"]} —— {row["why_stale"]}', file=sys.stderr)
            print(f'  （口径见 {SCOPE_PATH} 与 tools/mod_api_gap_report.py 的"多模组"那一段；'
                  f'接某个模组时把它标成 target）', file=sys.stderr)
            return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
