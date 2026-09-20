#!/usr/bin/env python3
"""引擎调用 ABI 体检：把 `runtime_constants.hpp` 的偏移常量与游戏镜像里的真实符号对上。

## 为什么需要它

2026-09-17 的两处真 bug 是同一类：**我们按自己的假设去解释引擎的 ABI**。

* `EntityPlayer:HasCollectible` —— PC 与原生符号都是 `(eCollectibleType, bool)`，我们只接受一个参数，
  EID 传第二个参数时**每次都报错**；
* 引擎返回的块"是不是分配起点" —— 我们假设是，直接 `delete[]`，踩坏游戏堆（见续三十七）。

这类问题**完全可以静态查清**：游戏镜像 `Repentance.nro` 的动态符号表里，每个函数都带着
**完整的参数表**（Itanium ABI 的 mangled name 里就写着）。把"偏移常量 → 真实符号 → 参数个数/类型"
列出来，再和我们调用点的实参个数比一比，就能在真机之前发现这类错。

## 2026-09-17 升级：从"数实参"改成"比我们声明的函数指针类型"

第一版只会认 `reinterpret_cast<Fn>(base + kXOffset)(a, b)` 这一种形态，实际只找到 **3/92** 个调用点 ——
也就是说那句"参数个数不符 0"**是"没比过"，不是"都没问题"**。

现在改成比**声明**：本项目调用引擎只有两种写法，两种都能静态读出"我们以为它长什么样"：

* `reinterpret_cast<XxxFn>(method)(…)` + `using XxxFn = 返回类型 (*)(参数…)`（`isaac_api.cpp` 一族）；
* `Guarded<decltype(calls.field)>(…)` + `返回类型 (*field)(参数…)`（存档文件适配器一族）。

拿这份"我们的声明"与镜像里的真实签名逐条比，判三类：

| 判据 | 含义 | 处置 |
| --- | --- | --- |
| `our < engine`（少给参数） | 引擎要读的参数我们没准备 ⇒ 那些寄存器是**调用方的残留值** | 必须逐条人工分诊，写进 `tools/engine_abi_triage.json`（写明为什么安全） |
| 浮点/整数不匹配 | 引擎要 `float`/`double`（走 v 寄存器）而我们声明的是整数（走 x 寄存器）⇒ 实参根本传不到 | **一律判红**（2026-09-17 的 `Present` 转发桩就是这个形状） |
| `our > engine + 1` | 我们多给参数（多出来的引擎不读） | 无害，只提示 |

`HasCollectible` 那类错的形状正是"少给一个 `bool`" ⇒ 会被第一类抓住。

### 当前覆盖率与**已知读不出来的形态**（2026-09-17 实测，诚实记账）

91 个函数类偏移里，这份工具现在能读出"我们声明的参数表"的有 **71 个（78%）**，
其余 26 个读不出来（`--json` 里 `verdict=unknown` 的就是它们）。走到今天这条路经：

| 批次 | 做法 | 覆盖率 |
| --- | --- | ---: |
| 第一版 | 只认 `reinterpret_cast<Fn>(base + kXOffset)(…)` | 3/92 |
| 批次 1 | 改成比"我们声明的函数指针类型"（形态 A/B） | 16/91 |
| 同批 | Font/Sprite 两族的绑定记录字段改成声明类型（形态 C） | 41/91 |
| 023 | 单方法绑定那条链（形态 D：常量 → 校验助手 → 局部变量 → 发布函数 → 全局槽 → 取址助手） | 49/91 |
| 024 | "地址交给另一个函数"那一跳（`declared_type_via_callee`） | 51/91 |
| 025 | `GameFileReader` 一族的记录字段改成声明类型（形态 C′） | 59/91 |
| 027 | 形态 E（取址助手的结果经调用点交给"按签名调"的那一层）+ 源码侧拆开 `ItemConfig` 的 `kind` 分派 | **71/91** |
| 026 | **修掉形态 A 里"转型操作数切片少了闭括号"的 bug**（"局部变量"那条支路此前从未生效）、 局部变量的初始化表达式允许是"含常量的算式"、新增**形态 F**（常量当实参交给助手） | **65/91** |

⚠️ **2026-09-17 的更正**：交接文档 026 当时把"4 条读不出来"记成
"转型那一步不是 `reinterpret_cast<XFn>(method)`"，那是**归因错了** ——
真正的原因是切片少了一个闭括号，写法一直是对的。教训：**工具读不出来时，
先怀疑工具自己的正则，再怀疑源码的写法。**

剩下 20 条按"我们到底会不会真的跳进去调"分两类，**逐条**记在 `tools/engine_abi_backlog.json`
（门禁 `test_unknown_entries_are_triaged_in_backlog` 会核对"未覆盖的每一条都在台账里、且台账里没有
已经覆盖的条目"——覆盖率一提而台账没更新就判红）：

| 类别 | 条数 | 含义 | 处置 |
| --- | ---: | --- | --- |
| **A 类** | 0 | 真有消费者、应当能核对的欠账 —— **2026-09-17 第二批已清零**：最后三条（`ItemConfig::Item/Card/PillEffect::IsAvailable`）原本按**运行时 `kind`** 在两条签名间选，已改成"每个常量只对应一个签名"（源码侧拆开，见 `isaac_api.cpp` 的 `CallItemIsAvailable` 上方注释） | — |
| **B 类** | 9 | 只当**挂点/中继目标**（我们替换它的入口或发布自己的中继桩，不为它声明调用签名） | 没有"调用签名"可错，**不必补** |
| **C 类** | 11 | 全仓库没有消费者（`kFilesysFile*` 一族＝退役的"插件持久化"旧线遗留） | 同上，**不必补** |

⇒ **"参数个数不符 0" 必须连覆盖率一起读**：只有 `ok / under / float-mismatch` 那部分是真比过的。
报告把这三个数打出来，就是为了防止把"没比过"读成"都没问题"。

## 用法

    python3 tools/engine_offset_abi_report.py                 # 全量报告（人读）
    python3 tools/engine_offset_abi_report.py --json out.json # 落盘给门禁/台账用
    python3 tools/engine_offset_abi_report.py --mismatch-only # 只看"我们传的参数个数和引擎不符"的

退出码：0 = 没有发现参数个数不符；1 = 发现了（可当门禁用）。
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
CONSTANTS = ROOT / "runtime" / "source" / "runtime_constants.hpp"
SRC_DIRS = [ROOT / "runtime" / "src", ROOT / "runtime" / "source"]
#: 引擎符号签名表：由 `tools/gen_engine_symbol_signatures.py` 生成（用 c++filt），
#: 这里**只查表**，不再自己解析 mangled name —— 手写解析器踩过坑（`ItemConfig` 里的 `I` 被当成模板起始）。
TABLE = ROOT / "tools" / "engine_symbol_signatures.json"

CONST_RE = re.compile(r"^inline constexpr uintptr_t (k[A-Za-z0-9]+Offset) = (0x[0-9A-Fa-f]+);", re.M)

#: 只用于描述类型的人话名（够用就好，不追求完整 demangle）。
SIMPLE_TYPES = {
    "v": "void", "b": "bool", "c": "char", "a": "signed char", "h": "unsigned char",
    "s": "short", "t": "unsigned short", "i": "int", "j": "unsigned int",
    "l": "long", "m": "unsigned long", "x": "long long", "y": "unsigned long long",
    "f": "float", "d": "double", "w": "wchar_t", "e": "long double",
}
PREFIX = {"P": "指针", "R": "引用", "O": "右值引用", "K": "const"}


def load_offsets() -> dict[str, int]:
    text = CONSTANTS.read_text(encoding="utf-8")
    return {name: int(value, 16) for name, value in CONST_RE.findall(text)}


def load_symbols() -> dict[int, str]:
    if not NRO.exists():
        return {}
    _soname, symbols = parse_dynamic_symbols(NRO.read_bytes())
    out: dict[int, str] = {}
    for name, symbol in symbols.items():
        if symbol.file_offset is not None:
            out.setdefault(symbol.file_offset, name)
    return out


CAST_RE = re.compile(r"reinterpret_cast<\s*([^<>]*(?:<[^<>]*>[^<>]*)*)\s*>")
#: **形态 D（2026-09-19 批次 051）**：引擎方法类的"数据行"。
#: 一条 API 长这样（见 `interfaces/lua/engine_method_api.hpp`）：
#:     {0x0E010057, kEntityPlayerSetShootingCooldownOffset, kEntityPlayerSetShootingCooldownEntryWord,
#:      FieldReceipt::EntityPlayer, EngineCallShape::Void1, 1, 0xFF},
#: 这种写法**没有 `reinterpret_cast`**，所以前三种形态都看不见它 —— 而它恰恰是
#: "以后加 API 不再占代码段"的落点。这里按 `shape` 还原出参数表，让覆盖率数字继续诚实。
ENGINE_METHOD_ROW_RE = re.compile(
    r"\{\s*0x[0-9A-Fa-f]+\s*,\s*(k\w+Offset)\s*,\s*k\w+EntryWord\s*,"
    r"\s*FieldReceipt::\w+\s*,\s*EngineCallShape::(\w+)\s*,\s*(\d+)\s*,")
#: 形状 → 参数表（**含 `this`**，与其它形态的口径一致：允许 n 或 n+1）。
ENGINE_CALL_SHAPE_PARAMS = {
    "Void0": [],
    "Void1": ["std::int32_t"],
    "Void2": ["std::int32_t", "std::int32_t"],
    "Int0": [],
    # 批次 055：签名描述符表里的形状名就是 key，参数表按描述符里的 `EngineArgKind` 写。
    # 忘了登记不会让构建失败，但**ABI 体检会看不见这条**（覆盖率虚高）—— 所以加形状时一起登记。
    "VoidFloat1": ["double"],
    "VoidIntIntIntHandleInt": ["std::int32_t", "std::int32_t", "std::int32_t", "std::uintptr_t",
                               "std::int32_t"],
    # 批次 063：`bool(this)`（无参、返回布尔）——`Entity:IsFlying()`。
    "Bool0": [],
}
GUARDED_DECLTYPE_RE = re.compile(r"Guarded<\s*decltype\(\s*([A-Za-z_]\w*)\.([A-Za-z_]\w*)\s*\)\s*>")
#: 绑定表行：`{kSpritePlayOffset, offsetof(LuaRuntime::LuaSpriteBindings, play), &kSpritePlayExpectedBytes},`
BINDING_ROW_RE = re.compile(
    r"\{\s*(k[A-Za-z0-9]+Offset)\s*,\s*offsetof\(\s*LuaRuntime::(\w+)\s*,\s*(\w+)\s*\)")


def balanced(text: str, start: int, open_char: str = "(", close_char: str = ")") -> int:
    """返回从 `start` 处的开括号起、与之匹配的闭括号位置；找不到返回 -1。"""
    depth = 0
    for index in range(start, len(text)):
        if text[index] == open_char:
            depth += 1
        elif text[index] == close_char:
            depth -= 1
            if depth == 0:
                return index
    return -1


def split_parameters(body: str) -> list[str]:
    """按顶层逗号切参数表（忽略模板实参、括号、数组里的逗号）。"""
    params: list[str] = []
    depth = 0
    current = ""
    for char in body:
        if char in "(<[{":
            depth += 1
        elif char in ")>]}":
            depth -= 1
        if char == "," and depth == 0:
            params.append(current.strip())
            current = ""
        else:
            current += char
    if current.strip():
        params.append(current.strip())
    return params


def parameters_of_function_pointer(type_text: str, field: str | None = None) -> list[str] | None:
    """从一份"函数指针类型"文本里取参数表。

    两种形态都认：
      * 类型别名/内联类型：`返回 (*)(参数…)`
      * 结构体成员声明：`返回 (*字段名)(参数…)`（`field` 给出字段名时按名字找）
    """
    pattern = (
        re.compile(r"\(\s*\*\s*" + re.escape(field) + r"\s*\)\s*\(([^;]*?)\)")
        if field
        else re.compile(r"\(\s*\*\s*\)\s*\(([^)]*)\)")
    )
    match = pattern.search(type_text)
    if match is None:
        return None
    return split_parameters(match.group(1))


def resolve_alias(name: str, text: str) -> str | None:
    match = re.search(r"using\s+" + re.escape(name) + r"\s*=\s*([^;]+);", text, re.S)
    return match.group(1).strip() if match else None


def brace_spans(text: str) -> list[tuple[int, int]]:
    """所有"看起来像函数体"的大括号区间（左闭右开）。

    用途：同名局部变量在不同函数里指不同常量（`isaac_api.cpp` 里多个函数都有 `method`），
    平铺地建"变量 → 常量"表会串味，必须**按所在函数体**看。
    """
    spans: list[tuple[int, int]] = []
    for match in re.finditer(r"\{", text):
        head_start = max(0, match.start() - 2000)
        head = text[head_start : match.start()]
        if not re.search(r"\)\s*(?:noexcept\s*)?(?:const\s*)?$", head):
            continue
        # 排除 `if (…) {` / `for (…) {` 这些**控制流**花括号：它们也满足上面的形状，
        # 但把它们当"函数体"会让"按所在函数找局部变量绑定"这一步落空（实测踩过）。
        close_paren = head.rfind(")")
        open_paren = close_paren
        depth = 0
        while open_paren >= 0:
            char = head[open_paren]
            if char == ")":
                depth += 1
            elif char == "(":
                depth -= 1
                if depth == 0:
                    break
            open_paren -= 1
        if open_paren < 0:
            continue
        token = re.search(r"([A-Za-z_]\w*)\s*$", head[:open_paren])
        if token is None or token.group(1) in ("if", "for", "while", "switch", "catch", "else"):
            continue
        end = balanced(text, match.start(), "{", "}")
        if end != -1:
            spans.append((match.start(), end))
    return spans


def enclosing_span(spans: list[tuple[int, int]], position: int) -> tuple[int, int] | None:
    """包含 `position` 的**最小**函数体区间。"""
    containing = [span for span in spans if span[0] <= position <= span[1]]
    return min(containing, key=lambda span: span[1] - span[0]) if containing else None


#: `isaac_api.cpp` 一族用"取址助手 + 局部变量 + 转型调用"三跳来调引擎方法：
#:   `const std::uintptr_t method = base + kXxxOffset;`（在 `XxxMethod()` 里）
#:   → `const std::uintptr_t method = XxxMethod();`（在调用它的函数里）
#:   → `reinterpret_cast<XxxFn>(method)(…)`
#: 下面前两条正则就是用来把这三跳串起来的（第一版只认"常量直接出现在转型操作数里"，只覆盖 3/91）。
#: 取址 helper 的类型集合（`std::uintptr_t` / `uintptr_t` / `u64`）；改这里要连带改 `LOCAL_ALIAS_RE`。
ADDRESS_TYPE = r"(?:const\s+)?(?:std::uintptr_t|uintptr_t|u64)"
HELPER_RE = re.compile(
    r"(?:std::uintptr_t|uintptr_t|u64|void\s*\*)\s+(\w+)\s*\([^;{]*\)\s*(?:noexcept\s*)?\{")
#: 局部变量 → 初始化表达式（**整段**，不限定右边是"助手调用"）。
#:
#: 为什么要把整段留下来（2026-09-17 第二批）：`isaac_api.cpp` 一族有三种写法，右边分别长成
#:   `HasCollectibleMethod()`、`base + kEntityPlayerHasCollectibleOffset`、
#:   `kind == 1 ? CardIsAvailableMethod() : (kind == 2 ? … : ItemIsAvailableMethod())`。
#: 只认第一种时，后两种一律读不出来；而最后一种**本来就不该读出唯一答案**（三个候选），
#: 所以这里把"候选常量集合"整个交出去，由 `resolve_expression_constants` 判定"唯一/不唯一"。
LOCAL_ALIAS_RE = re.compile(
    ADDRESS_TYPE + r"\s+(\w+)\s*=\s*([^;]*);")


def resolve_expression_constants(expression: str, helpers: dict[str, str]) -> set[str]:
    """一段初始化表达式 → 它**可能**取到的偏移常量集合。

    两条来源：表达式里直接写的 `k…Offset`，以及表达式里调用的取址助手（用 `helpers` 翻译）。
    返回多个元素就代表"工具无法唯一确定" —— 调用方必须放弃判决，绝不挑一个用。
    """
    found = set(re.findall(r"\b(k[A-Za-z0-9]+Offset)\b", expression))
    for name in re.findall(r"\b(\w+)\s*\(\s*\)", expression):
        if name in helpers:
            found.add(helpers[name])
    return found


def address_helpers(text: str) -> dict[str, str]:
    """`XxxMethod()` 一族：函数名 → 它**唯一**引用的那个偏移常量。"""
    helpers: dict[str, str] = {}
    for match in HELPER_RE.finditer(text):
        brace = text.find("{", match.end() - 1)
        if brace == -1:
            continue
        end = balanced(text, brace, "{", "}")
        if end == -1:
            continue
        found = set(re.findall(r"\b(k[A-Za-z0-9]+Offset)\b", text[brace : end + 1]))
        if len(found) == 1:
            helpers[match.group(1)] = found.pop()
    return helpers


def local_aliases(text: str, helpers: dict[str, str]) -> dict[str, str | None]:
    """局部变量 → 常量：`const std::uintptr_t method = …;` 这一跳。

    值 `None` 表示"初始化表达式里有多个候选常量"（例如 `kind == 1 ? A() : B()`），
    即**工具读不出唯一答案**。调用方必须把 `None` 当成"不匹配"，不能退化成"随便挑一个"。
    """
    out: dict[str, str | None] = {}
    for name, expression in LOCAL_ALIAS_RE.findall(text):
        candidates = resolve_expression_constants(expression, helpers)
        out[name] = candidates.pop() if len(candidates) == 1 else None
    return out


_FILE_CACHE: dict[pathlib.Path, tuple[str, list[tuple[int, int]], dict[str, str]]] = {}
_DEFINITION_CACHE: dict[pathlib.Path, dict[str, tuple[list[str], str]]] = {}
_SOURCE_LIST: list[pathlib.Path] | None = None


def file_facts(path: pathlib.Path) -> tuple[str, list[tuple[int, int]], dict[str, str]]:
    """读一次文件并缓存：文本、函数体区间、取址助手表。

    为什么要缓存：每个常量都要扫全部生产源码，而 `brace_spans` 是 O(文件大小) ——
    91 个常量不缓存要跑一分半（实测），缓存后几秒。
    """
    cached = _FILE_CACHE.get(path)
    if cached is None:
        text = path.read_text(encoding="utf-8", errors="replace")
        cached = (text, brace_spans(text), address_helpers(text))
        _FILE_CACHE[path] = cached
    return cached


def all_sources() -> list[pathlib.Path]:
    """生产源码全集（`.cpp` + `.hpp`），排序后缓存 —— 跨文件找类型别名要用。"""
    global _SOURCE_LIST
    if _SOURCE_LIST is None:
        paths: list[pathlib.Path] = []
        for directory in SRC_DIRS:
            paths += list(directory.rglob("*.cpp")) + list(directory.rglob("*.hpp"))
        _SOURCE_LIST = sorted(paths)
    return _SOURCE_LIST


def resolve_alias_anywhere(name: str) -> str | None:
    """在整个源码树里找 `using <name> = …;`。

    为什么不是只在本文件里找（2026-09-17）：绑定记录的字段类型声明在
    `lua_runtime_state.hpp`，而记录本身在 `lua_runtime.hpp`、绑定表在 `hook_manager.cpp`
    —— 一份类型横跨三个文件是正常的 C++ 写法，工具必须跟得上。
    """
    for path in all_sources():
        found = resolve_alias(name, file_facts(path)[0])
        if found:
            return found
    return None


def member_declared_type(record: str, field: str) -> str | None:
    """在 `struct <record> { … }` 里找 `<类型> <field>{…};`，返回**解析过别名**的类型文本。"""
    for path in all_sources():
        text = file_facts(path)[0]
        body_match = re.search(r"struct\s+" + re.escape(record) + r"\s*\{(.*?)\n\};", text, re.S)
        if body_match is None:
            continue
        body = re.sub(r"//[^\n]*", "", body_match.group(1))
        declared = re.search(r"([A-Za-z_][\w:<>,\s\*&]*?)\s+" + re.escape(field) + r"\s*\{", body)
        if declared is None:
            continue
        type_name = declared.group(1).strip()
        return resolve_alias_anywhere(type_name) or type_name
    return None


# --- 单方法绑定那条链（形态 D，2026-09-17 第二批）------------------------------------
#
# 与 Font/Sprite 那两族不同，这些入口**没有绑定记录**：安装期由各自的 `VerifyXxx` 助手校验
# （函数体里恰好引用一个 `k…Offset`），把结果写进一个 `uintptr_t` 局部变量，再交给
# `Set…Binding(局部变量)`。所以"偏移常量 → 我们声明的类型"要顺着这条链走：
#
#   kXxxOffset（在 `VerifyXxx` 里，唯一）
#     → `VerifyXxx(module, &local)`            （拿到局部变量名）
#     → `SetYyy(local, …)`                     （拿到实参位置 i）
#     → `SetYyy` 定义体里第 i 个形参存进 `g_Zzz`
#     → `ZzzThunk()` 返回 `g_Zzz`              （在 `lua_runtime.cpp`）
#     → `ZzzThunk()` 调用点声明的类型           （我们实际怎么调它）
#
# 任何一跳对不上就返回 None（算"没比过"）——绝不猜：宁可不比，也不给一个可能是错的判决。
THUNK_DEF_RE = re.compile(r"(\w+)\s+(\w+)Thunk\(\)\s*noexcept\s*\{\s*return\s+[^;]*?(g_\w+)\.load")
SETTER_DEF_RE = re.compile(r"void\s+(Set\w+)\s*\(([^)]*)\)\s*(?:noexcept\s*)?\{")
STORE_PARAM_RE = re.compile(r"(g_\w+)\.store\(\s*(?:reinterpret_cast<[^>]*>\(\s*)?(\w+)")
VERIFY_LOCAL_RE = re.compile(r"(\w+)\s*\(\s*module\s*,\s*&(\w+)\s*\)")
#: 助手体内**同一次调用**里既给出常量又给出出参的那种写法（Music/RNG 这两个族是这么写的）：
#:   `verify(kMusicPauseOffset, …, pause)` —— 常量与出参在同一个实参表里，顺序无关，直接配对。
PAIRED_OUTPUT_RE = re.compile(r"\b(?:verify|Guarded\w*)\s*\(\s*(k\w+Offset)\b[^;]*?,\s*(\w+)\s*\)")
#: 校验助手的定义头：`bool VerifyMusicBindings(const TargetModule& module, uintptr_t* a, uintptr_t* b)`
VERIFY_HELPER_DEF_RE = re.compile(r"(?:bool|void)\s+(Verify\w+)\s*\(([^)]*)\)\s*(?:noexcept\s*)?\{")
SETTER_CALL_RE = re.compile(r"(?:LuaRuntime::)?(Set\w+)\s*\(([^;]*)\)\s*;")


#: `Verify…(module, kXxxOffset, …, &record.field)`：常量与记录字段在同一次调用里。
VERIFY_FIELD_RE = re.compile(
    r"\([^;()]*?(k\w+Offset)\s*,[^;]*?&\s*\w+\s*\.\s*(\w+)\s*\)")


def declared_type_of_field(field: str) -> str | None:
    """在**任意**结构体里找这个字段的声明类型（解析过别名）。

    为什么要"任意结构体"：`GameFileReader::Bindings` 这类记录不是 `LuaRuntime` 名下的，
    字段名（`construct`/`read`/…）也短，所以按"哪个结构体里有这个字段"来找，而不是按记录名。
    解析不出函数指针类型就返回 None（算"没比过"）。
    """
    for path in all_sources():
        # 先把 `{nullptr}` 这类**成员初始化器**抹掉：`struct … {[^}]*}` 这种朴素取体会在第一个 `}`
        # 处截断，于是只有第一个字段能被看到（实测就只认出了 1/8 条）。
        text = file_facts(path)[0].replace("{nullptr}", " ")
        for body_match in re.finditer(r"struct\s+(\w+)\s*\{([^}]*)\}", text):
            body = re.sub(r"//[^\n]*", "", body_match.group(2))
            declared = re.search(r"([A-Za-z_][\w:<>,\s\*&]*?)\s+"
                                 + re.escape(field) + r"\s*[;{=]", body)
            if declared is None:
                continue
            type_text = resolve_alias_anywhere(declared.group(1).strip()) or declared.group(1).strip()
            if parameters_of_function_pointer(type_text) is not None:
                return type_text
    return None


def _enclosing_function_name(text: str, spans: list[tuple[int, int]], position: int) -> str | None:
    """包含 `position` 的最小函数体的**函数名**（判据与 `enclosing_span` 同一套）。"""
    span = enclosing_span(spans, position)
    if span is None:
        return None
    head = text[max(0, span[0] - 400) : span[0]]
    match = re.search(r"(\w+)\s*\([^;{)]*\)\s*(?:noexcept\s*)?$", head)
    return match.group(1) if match else None


def function_definitions(path: pathlib.Path) -> dict[str, tuple[list[str], str]]:
    """文件里的函数定义：函数名 → （形参表, 函数体）。"""
    cached = _DEFINITION_CACHE.get(path)
    if cached is not None:
        return cached
    text, spans, _helpers = file_facts(path)
    definitions: dict[str, tuple[list[str], str]] = {}
    for span in spans:
        name = _enclosing_function_name(text, spans, span[0])
        if name is None:
            continue
        head = text[max(0, span[0] - 400) : span[0]]
        match = re.search(r"\b" + re.escape(name) + r"\s*\(([^;{)]*)\)\s*(?:noexcept\s*)?$", head)
        if match is None:
            continue
        definitions.setdefault(name, (split_parameters(match.group(1)), text[span[0] : span[1]]))
    _DEFINITION_CACHE[path] = definitions
    return definitions


#: 扫描调用点时**不算调用**的关键字（控制流、转型、`sizeof` 之类）。
#: 不排掉它们的话 `if (` 也会被当成一次调用，而它的"实参表"会贪婪吞掉后面整段 ——
#: 实测后果：`if (!CallLevelIntMethod(LuaRuntime::XThunk(), …)) {` 里那次真调用**扫不到**，
#: `Level:GetAbsoluteStage` / `Room:GetFrameCount` 三条的链就断在这里（2026-09-17 第二批查清）。
CALL_EXCLUDED = frozenset({
    "if", "for", "while", "switch", "catch", "return", "sizeof", "decltype", "alignof",
    "static_cast", "reinterpret_cast", "const_cast", "dynamic_cast", "noexcept", "assert",
})


def call_sites(text: str):
    """逐个产出源码里的**函数调用**：`(函数名, 顶层实参表, 位置)`。

    实参表用括号配对取（不是 `[^;]*`）—— 后者遇到嵌套括号会错位，而且匹配区间会**吞掉**
    紧跟在控制流关键字后面的那次调用。这个扫描器是"形态 D 最后一跳"与"形态 F"共用的地基。
    """
    for match in re.finditer(r"\b([A-Za-z_]\w*)\s*\(", text):
        name = match.group(1)
        if name in CALL_EXCLUDED:
            continue
        open_paren = match.end() - 1
        close_paren = balanced(text, open_paren)
        if close_paren == -1:
            continue
        yield name, split_parameters(text[open_paren + 1 : close_paren]), match.start()


def argument_mentions(argument: str, name: str) -> bool:
    """实参里是否用到这个名字。

    纯标识符（局部变量名，例如 `method`）用**整词**匹配：子串匹配会把
    `methodName`、`Method` 之类一起算进来 —— 局部变量名撞车时那就是错判决。
    带括号的（`XxxThunk()`）才用子串匹配，那是独一无二的串。
    """
    if re.fullmatch(r"[A-Za-z_]\w*", name):
        return re.search(r"\b" + re.escape(name) + r"\b", argument) is not None
    return name in argument


def declared_type_via_callee(local_name: str,
                             scope: tuple[pathlib.Path, int, int] | None = None
                             ) -> tuple[str, list[str], str] | None:
    """形态 D 的最后一跳：地址被**交给另一个函数**时，类型写在那边的形参/转型里。

    两种写法都认：
      * 直接给出去：`CallLevelIntMethod(LuaRuntime::XThunk(), …)`（实参就是取址助手调用）；
      * 先收进局部变量再给出去：`const uintptr_t method = XThunk(); … CallRoomIntMethod(room, method, …)`。
    进到被调函数的定义体后，找 `reinterpret_cast<Y>(<那个形参>)` 这一次转型，`Y` 就是声明的类型。

    `scope` = `(文件, 函数体起点, 终点)`：**局部变量那一支必须给**。
    `method` 这类名字在 `isaac_api.cpp` 里到处都是，不加作用域限制就会跑到别的函数里去拿类型
    （那是错判决，比"没比过"更糟）。给了 scope 就只在该文件的该函数体内找使用点。

    候选**不唯一**（同一个地址被交给两个签名不同的函数）时返回 None：不猜。
    """
    candidates: set[tuple[str, list[str], str]] = set()
    for path in all_sources():
        if path.suffix != ".cpp":
            continue
        if scope is not None and path != scope[0]:
            continue
        text = file_facts(path)[0]
        for callee, arguments, position in call_sites(text):
            if scope is not None and not (scope[1] <= position <= scope[2]):
                continue
            # 实参两种写法都算命中：直接把取址助手调用当实参（`…(LuaRuntime::XThunk(), …)`），
            # 或者传的是从它取出来的那个局部变量（`…(room, method, …)`）。
            hits = [index for index, argument in enumerate(arguments)
                    if argument_mentions(argument, local_name)]
            if not hits:
                continue
            for other in all_sources():
                if other.suffix != ".cpp":
                    continue
                definitions = function_definitions(other)
                if callee not in definitions:
                    continue
                parameters, body = definitions[callee]
                for index in hits:
                    if index >= len(parameters):
                        continue
                    parameter_name = parameters[index].split()[-1].strip("*& ")
                    # 形参本身转型，或"形参派生出的地址变量"再转型（形态 F 那一跳同源）。
                    for variable in sorted(derived_address_locals(body, parameter_name)):
                        for cast in re.finditer(r"reinterpret_cast<\s*(\w+)\s*>\s*\(\s*"
                                                + re.escape(variable) + r"\b", body):
                            type_name = cast.group(1)
                            type_text = (resolve_alias(type_name, file_facts(other)[0])
                                         or resolve_alias_anywhere(type_name) or type_name)
                            params = parameters_of_function_pointer(type_text)
                            if params is not None:
                                candidates.add((str(path.relative_to(ROOT)), tuple(params),
                                                f"{callee}() 的形参 {parameter_name} → {type_text}"))
    if len(candidates) != 1:
        return None
    file, params, type_text = candidates.pop()
    return file, list(params), type_text


def declared_type_of_thunk(thunk: str) -> tuple[str, list[str], str] | None:
    """某个取址助手（`<thunk>Thunk()`）的调用点**声明了什么类型**。

    判据与形态 A 同源（"调用点附近有一次到函数指针类型的转型，类型名在本文件里能解析"），
    只是入口从"偏移常量"换成"助手名"；调用点自己不转型、而是把地址交给别人时，再走一跳
    `declared_type_via_callee`。找不到就返回 None。
    """
    return declared_type_of_helper_call(thunk + "Thunk")


def declared_type_via_address_helper(constant: str) -> tuple[str, list[str], str] | None:
    """形态 E：常量在**某个取址助手**体内（`const uintptr_t method = base + kXxxOffset;`），
    助手返回的地址再被调用点交给"按签名调"的那一层。

    与形态 D 的区别：形态 D 的助手在 `hook_manager.cpp`、地址要经"发布函数 → 全局槽 → Thunk"
    绕一大圈；这里助手**离调用点很近**（常常同一个文件），链条只有
    "常量 → 助手 → 调用点 → （转型 | 交给另一个函数）"。

    例（2026-09-17 拆开 `ItemConfig` 那三条之后）：
        `const uintptr_t method = CardIsAvailableMethod();`
        `… CallCardIsAvailable(method, entry)` → 那边的 `reinterpret_cast<NoArgFn>(method)`
    助手名**撞车**（不止一个助手引用同一个常量）时返回 None：不猜。
    """
    helpers: dict[str, str] = {}
    for path in all_sources():
        for name, target in file_facts(path)[2].items():
            if target == constant:
                helpers.setdefault(name, str(path.relative_to(ROOT)))
    if len(helpers) != 1:
        return None
    helper = next(iter(helpers))
    return declared_type_of_helper_call(helper)


def declared_type_of_helper_call(helper: str) -> tuple[str, list[str], str] | None:
    """`<helper>()` 的调用点声明了什么类型（转型直接写在那儿，或它把地址交给了别人）。"""
    needle = helper + "()"
    for path in all_sources():
        if path.suffix != ".cpp":
            continue
        text, spans, _helpers = file_facts(path)
        if needle not in text:
            continue
        for match in re.finditer(re.escape(needle), text):
            # 转型必须在**同一个函数体**里找：`window` 原来是"往后 1200 字符"，
            # 那会看到下一个函数体里的转型（错判决）。现在取"同函数体"与"1200 字符"中更近的那个。
            span = enclosing_span(spans, match.start())
            window_end = min(match.end() + 1200, span[1] if span else len(text))
            window = text[match.end() : window_end]
            for cast in CAST_RE.finditer(window):
                name = cast.group(1).strip()
                type_text = resolve_alias(name, text) or name
                params = parameters_of_function_pointer(type_text)
                if params is not None:
                    return str(path.relative_to(ROOT)), params, f"{helper}() → {type_text}"
            # 调用点自己不转型 ⇒ 看它把地址交给了谁（可能先收进一个局部变量）。
            # ⚠️ `statement` 要**含结尾分号**：原来切到 `match.end()` 为止，而 needle 后面还有 `;`，
            #    于是 `local` 那条正则永远不成立、局部变量名取不出来 —— `Room:GetFrameCount`
            #    （`const uintptr_t method = …Thunk();` 再传给 `CallRoomIntMethod`）就断在这一跳。
            start = max(text.rfind(";", 0, match.start()), text.rfind("{", 0, match.start())) + 1
            statement_end = text.find(";", match.end())
            statement = text[start : statement_end + 1 if statement_end != -1 else match.end()]
            local = re.search(r"(\w+)\s*=\s*(?:LuaRuntime::)?" + re.escape(needle) + r"\s*;", statement)
            if local is not None and span is not None:
                # 局部变量名（`method`）太常见 ⇒ 只在该函数体里找它的去向；
                # 而且还要按"**这个名字的下一次声明**"切出作用域：
                # `ItemConfigItemIsAvailable` 里三条分支各有一个 `const uintptr_t method = …`
                # （不同作用域、不同对象），不切开就会同时看到"交给 Card/PillEffect/Item 三种签名"
                # ⇒ 候选不唯一 ⇒ 只能报"没比过"。切开口之后每条都唯一。
                # 起点取 `match.end()`（该变量必须先初始化后使用）——这同时排除了前面分支里的同名变量。
                boundary = span[1]
                later = re.search(
                    ADDRESS_TYPE + r"\s+" + re.escape(local.group(1)) + r"\s*=",
                    text[match.end() : span[1]])
                if later is not None:
                    boundary = match.end() + later.start()
                via_callee = declared_type_via_callee(local.group(1), (path, match.end(), boundary))
            else:
                via_callee = declared_type_via_callee(local.group(1) if local else needle)
            if via_callee is not None:
                return via_callee
    return None


#: 局部地址变量声明：`const std::uintptr_t target = base + offset;`（形态 F 用）。
DERIVED_LOCAL_RE = re.compile(ADDRESS_TYPE + r"\s+(\w+)\s*=\s*([^;]*);")


def derived_address_locals(body: str, parameter_name: str) -> set[str]:
    """函数体里"由某个形参算出来"的地址变量名集合（`base + offset` → `target`，含形参本身）。"""
    names = {parameter_name}
    for name, expression in DERIVED_LOCAL_RE.findall(body):
        if re.search(r"\b" + re.escape(parameter_name) + r"\b", expression):
            names.add(name)
    return names


def declared_type_via_argument_helper(constant: str) -> tuple[str, list[str], str] | None:
    """形态 F：常量**直接当实参**交给某个助手，类型写在那边的形参链上。

    例（`remaining_api.cpp` 的诅咒访问器）：

        `CallGameCurseAccessor(kGameSpecialSeedPermanentCursesOffset, …, &called)`

    这个常量既不在任何 `reinterpret_cast` 的操作数里、也不在任何取址助手里 ——
    它作为实参进了被调函数的形参 `offset`，在那边派生成 `const std::uintptr_t target = base + offset;`，
    最后由 `reinterpret_cast<AccessorFn>(target)(…)` 转型。所以要跟着走
    "实参 → 形参 → 派生出的地址变量 → 转型类型"。

    候选**不唯一就不给判决**（例如同一个常量在两处以不同签名使用）：宁可不比，也不猜。
    """
    candidates: set[tuple[str, list[str], str]] = set()
    for path in all_sources():
        if path.suffix != ".cpp":
            continue
        text = file_facts(path)[0]
        if constant not in text:
            continue
        for callee, arguments, _position in call_sites(text):
            for index, argument in enumerate(arguments):
                if argument.strip() != constant:
                    continue
                for other in all_sources():
                    if other.suffix != ".cpp":
                        continue
                    definitions = function_definitions(other)
                    if callee not in definitions:
                        continue
                    parameters, body = definitions[callee]
                    if index >= len(parameters):
                        continue
                    parameter_name = parameters[index].split()[-1].strip("*& ")
                    for name in sorted(derived_address_locals(body, parameter_name)):
                        cast = re.search(r"reinterpret_cast<\s*(\w+)\s*>\s*\(\s*"
                                         + re.escape(name) + r"\b", body)
                        if cast is None:
                            continue
                        type_name = cast.group(1)
                        type_text = (resolve_alias(type_name, file_facts(other)[0])
                                     or resolve_alias_anywhere(type_name) or type_name)
                        params = parameters_of_function_pointer(type_text)
                        if params is not None:
                            candidates.add((
                                str(path.relative_to(ROOT)), tuple(params),
                                f"{callee}({constant}, …) → 形参 {parameter_name} → {type_text}",
                            ))
    if len(candidates) != 1:
        return None
    file, params, type_text = candidates.pop()
    return file, list(params), type_text


def single_binding_signature(constant: str) -> tuple[str, list[str], str] | None:
    """形态 D：走完"常量 → 校验助手 → 局部变量 → 发布函数 → 全局槽 → 取址助手 → 调用点"这条链。"""
    hook_path = ROOT / "runtime" / "source" / "hook_manager.cpp"
    text, spans, _helpers = file_facts(hook_path)
    if constant not in text:
        return None
    # 1) 常量落在哪个校验助手的函数体里？两种写法都认：
    #    ① 助手体里**只有这一个**常量 ⇒ 出参就是这个常量（单方法绑定）；
    #    ② 助手体里有多个常量，但每个常量在**同一次 `verify(...)` 调用**里与某个出参成对出现
    #       （Music/RNG 两个族就是这么写的）⇒ 直接按配对接上，不靠顺序猜。
    helper_names: set[str] = set()
    paired_output: str | None = None
    for hit in re.finditer(r"\b" + re.escape(constant) + r"\b", text):
        span = enclosing_span(spans, hit.start())
        if span is None:
            return None
        body = text[span[0] : span[1]]
        name = _enclosing_function_name(text, spans, hit.start())
        if name is None:
            return None
        if len(set(re.findall(r"\bk[A-Za-z0-9]+Offset\b", body))) == 1:
            helper_names.add(name)
            continue
        for paired_constant, output in PAIRED_OUTPUT_RE.findall(body):
            if paired_constant == constant:
                helper_names.add(name)
                paired_output = output
    if len(helper_names) != 1:
        return None
    helper = helper_names.pop()
    # 2) 谁调用这个助手、把结果写进哪个局部变量？
    locals_used: set[str] = set()
    # 调用点的实参表用括号配对取，不要求"以 `;` 结尾" —— 有的调用点在 `if (!Verify…(…)) {` 里
    # （RNG 那一族就是），要求分号会整条链断掉。
    for call in re.finditer(r"\b" + re.escape(helper) + r"\s*\(", text):
        open_paren = text.index("(", call.end() - 1)
        close_paren = balanced(text, open_paren)
        if close_paren == -1:
            continue
        arguments = text[open_paren + 1 : close_paren]
        if paired_output is None:
            locals_used.update(local for _called, local in VERIFY_LOCAL_RE.findall(f"{helper}({arguments})"))
            continue
        # 成对写法：常量对应助手的第 i 个出参 ⇒ 取调用点第 i+1 个实参（第一个是 `module`）。
        definition = VERIFY_HELPER_DEF_RE.search(text)
        for definition in VERIFY_HELPER_DEF_RE.finditer(text):
            if definition.group(1) != helper:
                continue
            parameters = [p.split()[-1].strip("*& ") for p in split_parameters(definition.group(2))]
            if paired_output not in parameters:
                break
            index = parameters.index(paired_output)
            actual = split_parameters(arguments)
            if index < len(actual):
                locals_used.add(actual[index].strip().lstrip("&"))
            break
    if not locals_used:
        return None
    # 3) 哪个发布函数把这个局部变量当第 i 个实参？
    for call in SETTER_CALL_RE.finditer(text):
        setter, arguments = call.group(1), split_parameters(call.group(2))
        for index, argument in enumerate(arguments):
            if argument.strip() not in locals_used:
                continue
            # 4) 发布函数定义体里，第 i 个形参存进哪个全局槽？
            #    注意：发布函数的**定义**在 `lua_runtime.cpp`，调用点才在 `hook_manager.cpp`。
            runtime_text = file_facts(ROOT / "runtime" / "source" / "lua_runtime.cpp")[0]
            for definition in SETTER_DEF_RE.finditer(runtime_text):
                if definition.group(1) != setter:
                    continue
                parameters = split_parameters(definition.group(2))
                if index >= len(parameters):
                    continue
                parameter_name = parameters[index].split()[-1].strip("*& ")
                body_end = balanced(runtime_text, definition.end() - 1, "{", "}")
                if body_end == -1:
                    continue
                body = runtime_text[definition.end() : body_end]
                stored = [global_name for global_name, source in STORE_PARAM_RE.findall(body)
                          if source == parameter_name]
                if len(stored) != 1:
                    continue
                # 5) 哪个取址助手返回这个全局槽？它的调用点声明了什么类型？
                for thunk_match in THUNK_DEF_RE.finditer(runtime_text):
                    if thunk_match.group(3) != stored[0]:
                        continue
                    signature = declared_type_of_thunk(thunk_match.group(2))
                    if signature is not None:
                        file, params, type_text = signature
                        return file, params, f"{constant} → {helper} → {setter} → {stored[0]} → {type_text}"
    return None


def find_member_declaration(text: str, field: str) -> str | None:
    """找成员声明（`返回类型 (*field)(参数…)`）—— 只认得"字段本身就是函数指针类型"的写法。"""
    pattern = r"[^;{}]*\(\s*\*\s*" + re.escape(field) + r"\s*\)[^;{}]*"
    fn_ptr = re.search(pattern, text)
    return fn_ptr.group(0) if fn_ptr is not None else None


def declared_signature(constant: str) -> tuple[str, list[str], str] | None:
    """找 `k…Offset` 的调用点，并读出**我们声明的函数指针参数表**。

    返回 `(文件, 参数表, 类型文本)`；找不到返回 None（属于"没比过"，会被计入覆盖率缺口）。
    """
    for directory in SRC_DIRS:
        for path in sorted(list(directory.rglob("*.cpp")) + list(directory.rglob("*.hpp"))):
            text, spans, helpers = file_facts(path)
            if constant not in text:
                continue
            relative = str(path.relative_to(ROOT))
            # 形态 A：`reinterpret_cast<XxxFn>(…)`，XxxFn 可能是别名或内联的函数指针类型。
            for match in CAST_RE.finditer(text):
                operand_start = text.find("(", match.end())
                if operand_start == -1:
                    continue
                operand_end = balanced(text, operand_start)
                if operand_end == -1:
                    continue
                operand = text[operand_start : operand_end + 1]
                # 两种来源：常量直接出现在操作数里，或操作数是"某个局部变量"。
                #
                # ⚠️ 2026-09-17 更正（本轮实测）：原来 `operand` 取的是 `[start:end]`，**少了闭括号**，
                #    于是下面那句 `re.fullmatch(r"\(\s*\w+\s*\)", operand)` 永远不成立 ——
                #    "局部变量"这条支路其实**从来没生效过**。交接文档 026 当时把它记成
                #    "转型那一步不是 `reinterpret_cast<XFn>(method)`"，是**归因错了**（写法一直是对的）。
                #    修成 `[start:end+1]` 之后这股路才真的开始工作。
                # 操作数里的常量不唯一（`cond ? kAOffset : kBOffset` 这种）一律不匹配：不猜。
                matched = resolve_expression_constants(operand, helpers) == {constant}
                if not matched and re.fullmatch(r"\(\s*\w+\s*\)", operand):
                    name_in_operand = operand.strip()[1:-1].strip()
                    # 从**最内层作用域往外找**绑定：函数里常有 `#if`/`{}` 嵌套块，
                    # 而直接用整份文件又会因同名局部变量（多个函数都有 `method`）而串味。
                    # `scope_locals` 的值可能是 `None`（初始化表达式里多个候选）—— 那时不予匹配。
                    for scope in sorted((sp for sp in spans
                                         if sp[0] <= match.start() <= sp[1]),
                                        key=lambda sp: sp[1] - sp[0]):
                        scope_locals = local_aliases(text[scope[0] : scope[1]], helpers)
                        if scope_locals.get(name_in_operand) == constant:
                            matched = True
                            break
                if not matched:
                    continue
                declared = match.group(1).strip()
                type_text = resolve_alias(declared, text) or declared
                params = parameters_of_function_pointer(type_text)
                if params is not None:
                    return relative, params, type_text
            # 形态 D：引擎方法的数据行（见 `ENGINE_METHOD_ROW_RE` 的说明）。
            for match in ENGINE_METHOD_ROW_RE.finditer(text):
                if match.group(1) != constant:
                    continue
                shape = match.group(2)
                params = ENGINE_CALL_SHAPE_PARAMS.get(shape)
                if params is None:
                    continue
                declared_arity = int(match.group(3))
                if declared_arity != len(params):
                    continue
                return relative, ["std::uintptr_t"] + list(params), f"EngineMethodRow/{shape}"

            # 形态 B：`Guarded<decltype(calls.field)>(…)`，字段的声明在同一个文件的结构体里。
            for match in GUARDED_DECLTYPE_RE.finditer(text):
                operand_start = text.find("(", match.end())
                if operand_start == -1:
                    continue
                operand_end = balanced(text, operand_start)
                if operand_end == -1 or constant not in text[operand_start:operand_end]:
                    continue
                field = match.group(2)
                params = parameters_of_function_pointer(text, field)
                if params is not None:
                    return relative, params, f"decltype({match.group(1)}.{field})"
            # 形态 C：绑定表行 `{kXxxOffset, offsetof(LuaRuntime::LuaXxxBindings, field), …}`
            # —— 字段的**声明类型**就是我们手写的签名（2026-09-17 起字段类型不再是 `uintptr_t`）。
            # 这条路覆盖的是"取址 → 发布到原子槽 → 调用点各自转型"那一族：字段名把
            # 偏移常量（本文件）与声明类型（可能在另一个头文件）连起来，不必再依赖调用点的写法。
            for match in BINDING_ROW_RE.finditer(text):
                if match.group(1) != constant:
                    continue
                record, field = match.group(2), match.group(3)
                type_text = member_declared_type(record, field)
                if type_text is None:
                    continue
                params = parameters_of_function_pointer(type_text)
                if params is not None:
                    return relative, params, f"{record}::{field} → {type_text}"
            # 形态 C′：`VerifyGameEntry(module, kXxxOffset, …, &verified.<字段>)` —— 常量与**记录字段**
            # 在同一次调用里见面（`game_file_reader` 那一族就是这么写的）。字段的声明类型即
            # 我们手写的签名，与形态 C 同源，只是这里没有 `offsetof` 而是取字段地址。
            for match in VERIFY_FIELD_RE.finditer(text):
                if match.group(1) != constant:
                    continue
                field = match.group(2)
                type_text = declared_type_of_field(field)
                if type_text is None:
                    continue
                params = parameters_of_function_pointer(type_text)
                if params is not None:
                    return relative, params, f"{constant} → &…::{field} → {type_text}"
            # 形态 D：单方法绑定（没有绑定记录）——走"校验助手 → 局部变量 → 发布函数 → 全局槽 →
            # 取址助手 → 调用点"这条链，见 `single_binding_signature` 的注释。
            signature = single_binding_signature(constant)
            if signature is not None:
                return signature
            # 形态 F：常量**直接当实参**交给某个助手（诅咒访问器那一族），
            # 类型写在被调函数的"形参 → 派生地址变量 → 转型"上。
            signature = declared_type_via_argument_helper(constant)
            if signature is not None:
                return signature
            # 形态 E：常量在某个取址助手体内，助手的结果被调用点交给"按签名调"的那一层。
            signature = declared_type_via_address_helper(constant)
            if signature is not None:
                return signature
    return None


LAYOUT_DIR = ROOT / "tools" / "layout_tables"


def layout_covered() -> set[str]:
    covered: set[str] = set()
    if LAYOUT_DIR.exists():
        for path in LAYOUT_DIR.glob("*.json"):
            covered.update(re.findall(r"k[A-Za-z0-9]+Offset", path.read_text(encoding="utf-8")))
    return covered


def inline_notes() -> dict[str, str]:
    """取常量声明行尾的注释 —— 那是目前字段偏移唯一携带的证据（批次号 / 真机读数）。"""
    notes: dict[str, str] = {}
    for line in CONSTANTS.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^inline constexpr uintptr_t (k[A-Za-z0-9]+Offset) = 0x[0-9A-Fa-f]+;\s*(//.*)?$", line)
        if match:
            notes[match.group(1)] = (match.group(2) or "").lstrip("/ ").strip()
    return notes


def print_layout_backlog(entries: list[dict]) -> None:
    covered = layout_covered()
    notes = inline_notes()
    fields = [e for e in entries if e["kind"] == "field" and e["constant"] not in covered]
    print(f"\n【布局表欠账】字段偏移 {sum(1 for e in entries if e['kind'] == 'field')} 个，"
          f"已有布局表证据 {sum(1 for e in entries if e['kind'] == 'field' and e['constant'] in covered)} 个，"
          f"**待取证 {len(fields)} 个**：")
    for entry in sorted(fields, key=lambda item: int(item["offset"], 16)):
        note = notes.get(entry["constant"], "")
        print(f"  {entry['constant']:42s} {entry['offset']:>8s}   {note[:96]}")


def load_table() -> list[dict]:
    if not TABLE.exists():
        raise SystemExit(f"缺少签名表 {TABLE.relative_to(ROOT)}：先跑 tools/gen_engine_symbol_signatures.py")
    return json.loads(TABLE.read_text(encoding="utf-8"))


#: 人工分诊台账：少数"我们故意少给参数"的调用点必须在这里写明理由与依据。
TRIAGE = ROOT / "tools" / "engine_abi_triage.json"
#: 欠账台账：工具**读不出声明**的每一条为什么读不出来、要不要补（门禁双向核对）。
BACKLOG = ROOT / "tools" / "engine_abi_backlog.json"


def load_backlog() -> dict[str, dict]:
    if not BACKLOG.exists():
        return {}
    return json.loads(BACKLOG.read_text(encoding="utf-8")).get("rows", {})


def print_abi_backlog(rows: list[dict]) -> None:
    """按类别列出"工具读不出声明"的那些条目（哪条欠账、哪条不必补，一眼看清）。"""
    backlog = load_backlog()
    unknown = [row for row in rows if row["verdict"] == "unknown"]
    print(f"\n【ABI 体检欠账】读不出声明的 {len(unknown)} 条，按台账分类：")
    for group in ("A", "B", "C"):
        members = [row for row in unknown if backlog.get(row["constant"], {}).get("class") == group]
        if not members:
            continue
        titles = {"A": "真有消费者、应当能核对（欠账）",
                  "B": "只当挂点/中继目标（不必补）",
                  "C": "全仓库没有消费者（不必补）"}
        print(f"  [{group}] {titles[group]}：{len(members)} 条")
        for row in sorted(members, key=lambda item: item["constant"]):
            print(f"      {row['constant']:42s} {backlog[row['constant']]['why'][:88]}")
    untracked = [row["constant"] for row in unknown if row["constant"] not in backlog]
    if untracked:
        print(f"  ⚠️ 未分诊（读不出又没写理由，门禁会判红）：{untracked}")


def load_triage() -> dict[str, dict]:
    if not TRIAGE.exists():
        return {}
    return json.loads(TRIAGE.read_text(encoding="utf-8")).get("rows", {})


def has_float(text: str) -> bool:
    return bool(re.search(r"\b(float|double)\b", text))


def classify(entry: dict, our_params: list[str] | None) -> dict:
    """把我们声明的参数表与引擎签名比一比。"""
    engine_params: list[str] = entry.get("parameters") or []
    row = {
        **entry,
        "declared_file": "",
        "declared_parameters": our_params,
        "declared_type": "",
        "verdict": "unknown",
        "detail": "没找到调用点（本轮没比过）",
    }
    if our_params is None:
        return row
    signature = declared_signature(entry["constant"])
    if signature is None:
        return row
    file, params, type_text = signature
    row["declared_file"] = file
    row["declared_parameters"] = params
    row["declared_type"] = type_text
    our_count = len(params)
    engine_count = len(engine_params)
    float_mismatch = has_float(" ".join(engine_params)) != has_float(" ".join(params))
    if float_mismatch:
        row["verdict"] = "float-mismatch"
        row["detail"] = ("引擎参数里有浮点而我们声明的是整数（实参传不到，v 寄存器没准备）"
                         if has_float(" ".join(engine_params))
                         else "引擎参数里没有浮点而我们声明了浮点")
    elif our_count < engine_count + 1:
        # ★ 2026-09-19 修正：**我们的声明里带着隐式的 `this`，引擎签名（从 mangled name 解出来的）
        # 不带**。所以正确的判据是 `our == engine + 1`；旧写法允许 `our == engine` 也算"一致"
        # ⇒ 正好把"**少给一个参数**"这一整类错放过去了 —— 而 `Entity:TakeDamage` 就是这一类，
        # 真机上它直接**把游戏打崩**（`Data Abort`，引擎把我们当成标志位的那个 0 当引用指针解，
        # 见 `docs/问题与解决记录.md` 续六十四）。
        row["verdict"] = "under"
        row["detail"] = (f"我们少给参数：声明 {our_count} 个（含 this）< 引擎 {engine_count} + 1 "
                         f"⇒ 引擎要读的那个参数是**调用方的残留值**")
    elif our_count > engine_count + 1:
        row["verdict"] = "over"
        row["detail"] = f"我们多给参数：声明 {our_count} 个 > 引擎 {engine_count} + 1（多出来的引擎不读）"
    else:
        row["verdict"] = "ok"
        row["detail"] = "一致（我们声明含 this，引擎签名不含 ⇒ 恰好 +1）"
    return row


def main() -> int:
    parser = argparse.ArgumentParser(description="引擎调用 ABI 体检（查签名表 ↔ 我们声明的参数表）")
    parser.add_argument("--json", type=pathlib.Path, help="把结果写成 JSON")
    parser.add_argument("--mismatch-only", action="store_true", help="只打印判红的条目")
    parser.add_argument("--layout-backlog", action="store_true",
                        help="列出还没有布局表证据的字段偏移（二期欠账清单）")
    parser.add_argument("--backlog", action="store_true",
                        help="按 A/B/C 类别列出工具读不出声明的条目（哪条欠账、哪条不必补）")
    args = parser.parse_args()

    entries = load_table()
    if args.layout_backlog:
        print_layout_backlog(entries)
        return 0

    functions = [e for e in entries if e["kind"] == "function"]
    rows = []
    for entry in functions:
        signature = declared_signature(entry["constant"])
        params = signature[1] if signature else None
        rows.append(classify(entry, params))

    triage = load_triage()
    unresolved = [r for r in rows if r["verdict"] == "unknown"]
    float_bad = [r for r in rows if r["verdict"] == "float-mismatch"]
    under = [r for r in rows if r["verdict"] == "under"]
    triaged = [r for r in under if r["constant"] in triage]
    untriaged = [r for r in under if r["constant"] not in triage]
    over = [r for r in rows if r["verdict"] == "over"]
    ok = [r for r in rows if r["verdict"] == "ok"]
    mismatches = float_bad + untriaged

    if args.backlog:
        print(f"函数类偏移 {len(functions)} 个：声明可读 **{len(functions) - len(unresolved)}** 个、"
              f"读不出 {len(unresolved)} 个")
        print_abi_backlog(rows)
        return 0

    print(f"函数类偏移 {len(functions)} 个：声明可读 **{len(functions) - len(unresolved)}** 个"
          f"（覆盖 {100 * (len(functions) - len(unresolved)) // max(1, len(functions))}%）、"
          f"读不到 {len(unresolved)} 个")
    print(f"  ✓ 一致 {len(ok)}；~ 少给参数 {len(under)}（其中已分诊 {len(triaged)}）；"
          f"+ 多给参数 {len(over)}；✗ 浮点不匹配 {len(float_bad)}")
    print(f"参数个数不符 **{len(mismatches)}** 个"
          + (f"（另有 {len(triaged)} 个『少给参数』已在 {TRIAGE.name} 里写明理由）" if triaged else ""))

    if float_bad:
        print("\n✗ 浮点/整数不匹配（实参传不到引擎）：")
        for row in float_bad:
            print(f"  {row['constant']} @ {row['offset']} → {row['demangled']}")
            print(f"    引擎参数：{row['parameters']}；我们声明：{row['declared_parameters']}"
                  f"（{row['declared_file']}）")
    if untriaged:
        print("\n✗ 少给参数且没有分诊记录（要么补参数、要么在台账里写明为什么安全）：")
        for row in untriaged:
            print(f"  {row['constant']} @ {row['offset']} → {row['demangled']}")
            print(f"    引擎参数：{row['parameters']}；我们声明：{row['declared_parameters']}"
                  f"（{row['declared_file']}）")
    if not args.mismatch_only:
        print("\n函数类条目逐条：")
        marks = {"ok": "✓", "under": "~", "over": "+", "float-mismatch": "✗", "unknown": "?"}
        for row in sorted(rows, key=lambda item: item["constant"]):
            ours = "—" if row["declared_parameters"] is None else len(row["declared_parameters"])
            print(f"  {marks[row['verdict']]} {row['constant']:40s} 引擎 {len(row['parameters'] or [])} 参数"
                  f" / 我们 {ours}  {row['detail']}")
    if args.json is not None:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"（JSON 已写入 {args.json}）")
    return 1 if mismatches else 0


if __name__ == "__main__":
    sys.exit(main())
