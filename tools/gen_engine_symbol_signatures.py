#!/usr/bin/env python3
"""生成"引擎符号签名表"：把**我们引用的偏移常量**与游戏镜像里的真实符号、参数表对上。

## 为什么要这张表

2026-09-17 的教训：我们按自己的假设解释引擎的 ABI（`HasCollectible` 少了一个 `bool` 参数、释放指针时
假设它是分配起点），两处都是**静态可查**的。查清的依据在游戏镜像里：每个函数的 mangled name
**带着完整参数表**。

而"解析 mangled name"这件事**不该自己写**：第一版手写解析器把 `ItemConfig` 里的 `I` 当成模板起始、
把类名当参数，产生了 3 个假阳性 / 2 个漏报。所以改成：**用 `c++filt` 生成一次，把结果落成表**，
工具与门禁都查这张表（离线可用、可比对、可复查）。

## 用法（表过期时重新生成）

    python3 tools/gen_engine_symbol_signatures.py            # 直接写 tools/engine_symbol_signatures.json
    python3 tools/gen_engine_symbol_signatures.py --check    # 只报告差异，不写文件

`c++filt` 用 devkitPro 容器里的那份（宿主自带的那个在本项目实测不解 Itanium 名字）。

## 名字匹配的**假阳性过滤器**（2026-09-17 补）

按偏移去动态符号表里取名字，会取到**跟我们毫无关系**的符号：动态表的 `st_value` 对不少条目是 0
或很小的值，于是字段偏移（例如 `kEntityPlayerDamageOffset = 0x1844`）会撞上别的东西。
实测 95 条匹配里有 **4 条**是这种货色：`rapidxml::…parse_cdata`、`nndetailRoGetRoDataStart`、
`nndetailRoGetRoDataEnd`、`_fini`。它们会把"ABI 体检"带偏（拿一个无关函数的参数表去比我们的实参）。

所以只接受**引擎自己的命名空间**：`IsaacRepentance::` / `KAGE::` / `nn::`；其余一律当作"这个偏移
没有可用符号"（于是它落到 `field` 类，不会进函数体检）。
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from nro_symbols import parse_dynamic_symbols  # noqa: E402

NRO = (
    ROOT
    / "The Binding of Isaac_ Afterbirth+ 1.7.9b [010021C000B6A800][v524288][UPD]"
    / "Program #0/1/.nro/Repentance.nro"
)
CONSTANTS = ROOT / "runtime" / "source" / "runtime_constants.hpp"
TABLE = ROOT / "tools" / "engine_symbol_signatures.json"
#: ★ 2026-09-19 修：原来只认 `uintptr_t`，而 `runtime_constants.hpp` 里两种写法**都有**
#: （批次 050 起新加的常量写成 `std::uintptr_t`）⇒ 那些常量被**静默漏掉**：它们不进签名表，
#: 于是 ABI 体检看不见它们、覆盖率数字虚高。两种写法都要认。
CONST_RE = re.compile(
    r"^inline constexpr (?:std::)?uintptr_t (k[A-Za-z0-9]+Offset) = (0x[0-9A-Fa-f]+);", re.M)


def our_offsets() -> list[tuple[str, int]]:
    """返回 [(常量名, 偏移)]。

    ⚠️ **必须按常量名建表，不能按偏移建索引**：项目里存在"两个名字指同一个偏移"的写法
    （`kFilesysFileCloseOffset` 与 `kGameFileCloseFileOffset` 都是 `0x4CD00C`），
    按偏移建索引会**静默丢掉一个名字**（第一版就丢了 `File::Close` 那条）。
    """
    text = CONSTANTS.read_text(encoding="utf-8")
    return [(name, int(value, 16)) for name, value in CONST_RE.findall(text)]


def symbols_at_offsets(offsets: set[int]) -> dict[int, str]:
    """只取"我们引用的那些偏移"上的符号（表要小到能进仓库）。"""
    if not NRO.exists():
        raise SystemExit("找不到游戏镜像（公开仓库不带游戏资源）⇒ 无法生成签名表")
    _soname, symbols = parse_dynamic_symbols(NRO.read_bytes())
    found: dict[int, str] = {}
    for name, symbol in symbols.items():
        if symbol.file_offset in offsets:
            found.setdefault(symbol.file_offset, name)
    return found


def demangle(names: list[str]) -> list[str]:
    """用 devkitPro 容器里的 c++filt demangle。

    ⚠️ **必须是"带哨兵的输出"**（`<mangled>\t<demangled>`），不能只按行对齐：
    第一版按行 zip，结果有**一条符号静默丢失**（`File::Close`），因为 c++filt 的输出行数与输入
    不完全一致 ⇒ 从某一行起整体错位。带哨兵就没有这个问题，且能检出"某条没被 demangle"。
    """
    payload = "\n".join(names) + "\n"
    script = 'while IFS= read -r n; do printf "%s\t" "$n"; c++filt "$n"; done'
    result = subprocess.run(
        ["docker", "run", "--rm", "-i", "devkitpro/devkita64:latest", "bash", "-lc", script],
        input=payload, capture_output=True, text=True, check=True,
    )
    out: list[str] = []
    for line in result.stdout.splitlines():
        if "\t" not in line:
            raise SystemExit(f"c++filt 输出格式意外：{line!r}")
        mangled, pretty = line.split("\t", 1)
        out.append(pretty)
    if len(out) != len(names):
        raise SystemExit(f"demangle 条数不符：输入 {len(names)}，输出 {len(out)}")
    return out


def parameter_list(demangled: str) -> list[str] | None:
    """从 demangle 后的签名里取参数表；不是函数（没有括号）时返回 None。"""
    if "(" not in demangled or not demangled.endswith((")", "const", "volatile")):
        return None
    # 找**最后一个**匹配的括号组（`operator()` 之类的前面还有括号）
    depth = 0
    close = None
    for index in range(len(demangled) - 1, -1, -1):
        char = demangled[index]
        if char == ")":
            depth += 1
            close = close if close is not None else index
        elif char == "(":
            depth -= 1
            if depth == 0:
                start = index
                break
    else:
        return None
    if close is None or close <= start + 1:
        return []
    body = demangled[start + 1 : close]
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


#: 只有这些命名空间里的符号才算"引擎自己的"（其余是动态表偏移撞车带来的假阳性）。
ENGINE_NAMESPACES = ("IsaacRepentance::", "KAGE::", "nn::")


def is_engine_symbol(demangled: str) -> bool:
    """判断一个 demangle 后的符号名是否属于引擎自己的命名空间。"""
    return any(namespace in demangled for namespace in ENGINE_NAMESPACES)


def build() -> list[dict]:
    constants = our_offsets()
    symbols = symbols_at_offsets({offset for _, offset in constants})
    names = [symbols[offset] for offset, _ in sorted(symbols.items())]
    demangled = demangle(names) if names else []
    pretty_by_symbol = dict(zip(names, demangled))
    entries: list[dict] = []
    for constant, offset in sorted(constants, key=lambda item: (item[1], item[0])):
        mangled = symbols.get(offset)
        pretty = pretty_by_symbol.get(mangled) if mangled else None
        if pretty is not None and not is_engine_symbol(pretty):
            # 见文件头「假阳性过滤器」：不是引擎自己的命名空间 ⇒ 这个偏移没有可用符号。
            mangled = None
            pretty = None
        params = parameter_list(pretty) if pretty else None
        entries.append(
            {
                "constant": constant,
                "offset": hex(offset),
                "mangled": mangled,
                "demangled": pretty,
                "parameters": params,
                "parameter_count": None if params is None else len(params),
                "kind": "function" if params is not None else ("data" if mangled else "field"),
            }
        )
    return entries


def main() -> int:
    parser = argparse.ArgumentParser(description="生成/校验引擎符号签名表")
    parser.add_argument("--check", action="store_true", help="只报告差异，不写文件")
    args = parser.parse_args()

    entries = build()
    functions = [entry for entry in entries if entry["kind"] == "function"]
    print(f"表内条目 {len(entries)} 个（其中函数 {len(functions)} 个）")
    if args.check:
        if not TABLE.exists():
            print("表不存在")
            return 1
        old = json.loads(TABLE.read_text(encoding="utf-8"))
        if old == entries:
            print("与现有表一致 ✓")
            return 0
        print("与现有表**不一致**（镜像或常量表变过？）")
        return 1
    TABLE.write_text(json.dumps(entries, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"已写入 {TABLE.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
