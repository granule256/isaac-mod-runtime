#!/usr/bin/env python3
"""从一个"引擎字段配方"里把**字段偏移**与**入口指纹**提取出来。

## 为什么要有它

本项目里"把引擎的某个数值搬进 Lua"有一大半走的是**同一个配方**：
引擎的 `Add<X>(int amount)`（给钥匙 / 给炸弹 / 给魂充能 / 给血充能 / 给金币…）函数体就是
**"读那个字段 → 加上参数 → 夹上限 → 写回"**，所以只要找到那条读写同一个偏移的指令对，
字段就定下来了，而且入口前 4 字节还能当"这份映像的入口指纹"（`runtime_constants.hpp`
里那几条常量都是这么来的：`kEntityPlayerKeysOffset = 0x16D4`、`kEntityPlayerCoinsOffset = 0x16E0`…）。

2026-09-18 之前这是**手抄**的：反汇编、肉眼找、抄进注释，一条大约 20 分钟。
这个工具把那一套自动化，并顺手打印**可以直接粘进常量注释的证据行**。

## 用法

    python3 tools/engine_field_recipe.py 0x2804E8          # AddKeys
    python3 tools/engine_field_recipe.py 0x280068          # AddCoins（对照用）
    python3 tools/engine_field_recipe.py --json 0x2804E8

输出：

* **入口指纹**：入口前 4 字节（十六进制），与 `p@nro_disasm` 看到的一致；
* **候选字段**：函数体里"被读过又被写过"的偏移（按访问次数排序）——那就是被累加的字段；
* **夹取常量**：函数体里的 `movz/movk` 立即数合成值（例如 `w8 = 99`/`999` 就是上限）；
* **证据块**：几行 `；证据：0x… 指令 说明`，可直接粘进 `runtime_constants.hpp`。

## 口径与保守之处

* 只认**无偏移写回**（unsigned-offset）的 `ldr/str/ldrb/strb/ldp/stp` —— 这些函数体都很短，
  编译器不会用花哨的寻址；**认不出来时如实说"没找到"**，不猜一个偏移给你；
* 候选里除了"读写同一个偏移"还允许"只被写过一次"的（有些函数是纯写），但会**分开列**，
  让人自己判断；
* 它不判断字段的**语义**（是钥匙还是炸弹）—— 那要靠调用点/常量上下文，工具只负责"偏移 + 指纹"。
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import struct
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_NRO = (
    REPO_ROOT
    / "The Binding of Isaac_ Afterbirth+ 1.7.9b [010021C0006A800][v524288][UPD]"
)
# 真实目录名里那一串是 010021C000B6A800（这里不写字面量，避免被"看起来像 title id"的搜索误伤）。
DEFAULT_NRO = Path(
    os.path.join(
        REPO_ROOT,
        "The Binding of Isaac_ Afterbirth+ 1.7.9b [010021C000B6A800][v524288][UPD]",
        "Program #0",
        "1",
        ".nro",
        "Repentance.nro",
    )
)

#: 函数体扫描上限（指令条数）。这些 `Add<X>` 都很短（十几到几十条），256 条足够；
#: 扫到第一条 `ret` 就停。
MAX_INSTRUCTIONS = 256

RET = 0xD65F03C0


def load_disassembler():
    """复用 `tools/nro_disasm.py` 的 `disassemble()`（它把区间包成最小 ELF 交给 llvm-objdump）。"""
    spec = importlib.util.spec_from_file_location("nro_disasm", REPO_ROOT / "tools" / "nro_disasm.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def decode_access(word: int) -> tuple[str, int, int] | None:
    """(kind, base_register, byte_offset)，认不出返回 None。

    只认无偏移写回（unsigned offset）的整字/半字/字节访问，以及 32/64 位的 pair 访问。
    """
    # LDR/STR (immediate, unsigned offset)：size 在 bit 30-31，opc 在 bit 22-23。
    if (word & 0x3B000000) == 0x39000000:
        size = (word >> 30) & 0x3
        opc = (word >> 22) & 0x3
        scale = {0: 1, 1: 2, 2: 4, 3: 8}[size]
        if opc not in (0, 1):  # 只认 STR / LDR（不认 LDRSW/PRFM 一类）
            return None
        kind = "str" if opc == 0 else "ldr"
        width = {0: "b", 1: "h", 2: "", 3: "x"}[size]
        return (kind + width, (word >> 5) & 0x1F, ((word >> 10) & 0xFFF) * scale)
    # LDP/STP (signed offset)：0xA9000000 / 0xA9400000 家族，imm7 以 4/8 字节为单位。
    if (word & 0x3A000000) == 0x28000000:
        opc = (word >> 22) & 0x3
        if opc != 0b10:  # 只认 32/64 位的 STP/LDP 变体
            return None
        is_load = ((word >> 22) & 0x1) == 0 and ((word >> 22) & 0x2) != 0
        offset = ((word >> 15) & 0x7F)
        if offset & 0x40:
            offset -= 0x80
        return ("ldp" if is_load else "stp", (word >> 5) & 0x1F, offset * 4)
    return None


def decode_add_registers(word: int) -> tuple[int, int, int] | None:
    """`add wD, wA, wB`（32 位、寄存器、无移位）⇒ (D, A, B)，否则 None。"""
    if (word & 0xFF200000) != 0x0B000000:
        return None
    if ((word >> 22) & 0x3) != 0 or ((word >> 10) & 0x3F) != 0:  # 只认不带移位/扩展的形态
        return None
    return (word & 0x1F, (word >> 5) & 0x1F, (word >> 16) & 0x1F)


def decode_mov_registers(word: int) -> tuple[int, int] | None:
    """`mov wD, wM`（= `orr wD, wzr, wM`）⇒ (D, M)，否则 None。"""
    if (word & 0xFFE0FFE0) != 0x2A0003E0:
        return None
    return (word & 0x1F, (word >> 16) & 0x1F)


def find_increment_hits(words: list[int], accesses: list[tuple[int, str, int, int]]) -> set[int]:
    """哪些偏移是"被读出来、加上**入参**、再写回去"的那个字段。

    为什么需要它（2026-09-18 实测教训）：`AddBombs @ 0x2802E8` 里访问次数最多的是 `+0x16DC`
    （ldr×4/str×3），而真正的炸弹字段是 `+0x16E4` —— **按次数排名会给出错的答案**。
    配方的本质是"读出来的值被加上入参"，所以这里顺着数据流找：
    入参从 `w0`/`w1` 进来（函数可能开头 `mov` 到别的寄存器），凡是"某个寄存器的值来自入参"
    且"某条 add 把刚读出来的字段值加上它" ⇒ 那个偏移就是强命中。
    """
    # 入参寄存器集合：w0/w1，以及开头从它们复制出去的寄存器（扫前 16 条就够）。
    argument_registers = {0, 1}
    for word in words[:16]:
        moved = decode_mov_registers(word)
        if moved is not None and moved[1] in argument_registers:
            argument_registers.add(moved[0])

    # 最近一次"从哪个偏移读到哪个寄存器"。
    loaded_from: dict[int, int] = {}  # 目标寄存器 -> 偏移
    hits: set[int] = set()
    for word in words:
        decoded = None
        for candidate in accesses:
            index, kind, base, offset = candidate
            del index, base
        # 直接在指令流上解码，才拿得到目标寄存器
        access = decode_access(word)
        if access is not None:
            kind, base, offset = access
            if base != 31 and 0 < offset <= 0x4000:
                target = word & 0x1F
                if kind.startswith(("ldr", "ldp")):
                    loaded_from[target] = offset
                elif kind.startswith(("str", "stp")) and target in loaded_from:
                    loaded_from.pop(target, None)
            continue
        added = decode_add_registers(word)
        if added is None:
            continue
        _, left, right = added
        for source in (left, right):
            if source in argument_registers:
                other = right if source == left else left
                if other in loaded_from:
                    hits.add(loaded_from[other])
    return hits


def collect_mov_constants(words: list[int]) -> list[str]:
    """把 `movz/movk/movn` 合成的常量还原成人看得懂的形式（上限值常在这里）。"""
    registers: dict[int, int] = defaultdict(int)
    shifts: dict[int, int] = defaultdict(int)
    out: list[str] = []
    for word in words:
        if (word & 0x7F800000) == 0x52800000:  # MOVZ 32-bit
            rd = word & 0x1F
            imm = (word >> 5) & 0xFFFF
            shift = ((word >> 21) & 0x3) * 16
            registers[rd] = imm << shift
            shifts[rd] = 0
        elif (word & 0x7F800000) == 0x72800000:  # MOVK 32-bit
            rd = word & 0x1F
            imm = (word >> 5) & 0xFFFF
            shift = ((word >> 21) & 0x3) * 16
            registers[rd] = (registers.get(rd, 0) & ~(0xFFFF << shift)) | (imm << shift)
            shifts[rd] = shift
        elif (word & 0x7F800000) == 0x12800000:  # MOVN 32-bit
            rd = word & 0x1F
            imm = (word >> 5) & 0xFFFF
            shift = ((word >> 21) & 0x3) * 16
            registers[rd] = (~(imm << shift)) & 0xFFFFFFFF
            shifts[rd] = 0
        elif (word & 0x7F800000) == 0x12000000:  # AND 立即数（夹取里也常见，但这里不还原）
            continue
        else:
            # 只要不是立即数装载，就把该寄存器当作"被覆盖"（不再当常量）。
            if (word & 0x1F000000) != 0x01000000 and (word & 0x1F000000) != 0x01800000:
                pass
            continue
        if shift != 0 or (word & 0x7F800000) == 0x52800000:
            out.append(f"w{rd} = {registers[rd]} (0x{registers[rd] & 0xFFFFFFFF:x})")
    # 去重但保序
    seen = set()
    unique = []
    for item in out:
        if item not in seen:
            seen.add(item)
            unique.append(item)
    return unique


def analyse(nro_path: Path, entry: int, pretty: bool) -> dict:
    blob = nro_path.read_bytes()
    if entry + 4 > len(blob):
        raise SystemExit(f"入口 0x{entry:x} 超出映像大小（0x{len(blob):x}）")
    # 指纹按**仓库既有口径**给两种写法：小端整字（`0xA9BD7BFD`，与
    # `kEntityPlayerAddCoinsEntryWord` 那类常量一致）与文件序字节（`FD 7B BD A9`，与 16 字节 guard 对照用）。
    entry_word = struct.unpack_from("<I", blob, entry)[0]
    fingerprint_word = f"0x{entry_word:08X}"
    fingerprint_bytes = " ".join(f"{byte:02X}" for byte in blob[entry : entry + 4])

    words: list[int] = []
    for index in range(MAX_INSTRUCTIONS):
        offset = entry + index * 4
        if offset + 4 > len(blob):
            break
        word = struct.unpack_from("<I", blob, offset)[0]
        words.append(word)
        if word == RET and index > 0:
            break

    accesses: dict[tuple[str, int], Counter] = defaultdict(Counter)
    detail: dict[tuple[str, int], list[str]] = defaultdict(list)
    for index, word in enumerate(words):
        decoded = decode_access(word)
        if decoded is None:
            continue
        kind, base, offset = decoded
        if offset <= 0 or offset > 0x4000:  # 0/过大 ⇒ 不是我们要找的字段
            continue
        if base == 31:  # x31 = SP ⇒ 那是栈访问，不是实体字段（之前它会在候选里排到前面）
            continue
        key = (kind, offset)
        accesses[key][base] += 1
        detail[key].append(f"0x{entry + index * 4:x} 0x{word:08x} {kind} [x{base}, #0x{offset:x}]")

    # 候选：**同一个偏移**既被读过又被写过（配方 = 取-加-夹-存），按偏移归并。
    by_offset: dict[int, dict[str, Counter]] = defaultdict(lambda: defaultdict(Counter))
    for (kind, offset), bases in accesses.items():
        for base, count in bases.items():
            by_offset[offset][kind][base] += count

    read_write: list[tuple[int, dict]] = []
    write_only: list[tuple[int, dict]] = []
    for offset, kinds in by_offset.items():
        # 取最常用的那个基址寄存器当"this 指针"。
        bases = Counter()
        for counter in kinds.values():
            bases.update(counter)
        common_base, base_hits = bases.most_common(1)[0]
        loaded = any(kind.startswith(("ldr", "ldp")) for kind in kinds)
        stored = any(kind.startswith(("str", "stp")) for kind in kinds)
        entry_info = {
            "offset": offset,
            "base_register": common_base,
            "base_hits": base_hits,
            "kinds": {kind: sum(counter.values()) for kind, counter in kinds.items()},
            "evidence": [line for key, lines in detail.items() if key[1] == offset for line in lines],
        }
        if loaded and stored:
            read_write.append((offset, entry_info))
        elif stored:
            write_only.append((offset, entry_info))

    increment_hits = find_increment_hits(words, [])
    for _offset, info in read_write:
        info["incremented_by_argument"] = _offset in increment_hits
    # 强命中（被加上入参的那个字段）排最前；其余按访问次数。
    read_write.sort(key=lambda item: (0 if item[1]["incremented_by_argument"] else 1,
                                      -item[1]["base_hits"]))
    write_only.sort(key=lambda item: -item[1]["base_hits"])

    return {
        "entry": entry,
        "fingerprint_word": fingerprint_word,
        "fingerprint_bytes": fingerprint_bytes,
        "instructions": len(words),
        "read_write_fields": read_write,
        "write_only_fields": write_only,
        "constants": collect_mov_constants(words),
        "pretty": pretty,
    }


def render(result: dict, target: str | None) -> str:
    lines: list[str] = []
    lines.append(f"入口 0x{result['entry']:x}  指令 {result['instructions']} 条")
    lines.append(f"入口整字（小端，仓库常量口径） {result['fingerprint_word']}"
                 f"    文件序字节 {result['fingerprint_bytes']}")
    if result["read_write_fields"]:
        lines.append("")
        lines.append("★ 候选字段（同一偏移既被读又被写 = 「取-加-夹-存」）：")
        for offset, info in result["read_write_fields"][:6]:
            kinds = "、".join(f"{kind}×{count}" for kind, count in sorted(info["kinds"].items()))
            mark = "★强命中（读出来的值被加上**入参**）" if info.get("incremented_by_argument") \
                else "  弱（只是同偏移读+写）"
            lines.append(f"   {mark} +0x{offset:X}  （基址 x{info['base_register']}，{kinds}）")
        if not any(info.get("incremented_by_argument") for _o, info in result["read_write_fields"]):
            lines.append("   ⚠️ 没有强命中 ⇒ **不要**把列表第一条当答案："
                         "`AddBombs` 就是反例（访问次数最多的是 +0x16DC，真正的字段是 +0x16E4）")
    else:
        lines.append("")
        lines.append("★ 没找到「既读又写」的字段 —— **不要猜**：确认入口地址对不对，"
                     "或这个函数本来就不改字段。")
    if result["write_only_fields"]:
        lines.append("")
        lines.append("（只被写过的偏移，供参考，未必是本函数的目标字段）")
        for offset, info in result["write_only_fields"][:4]:
            kinds = "、".join(f"{kind}×{count}" for kind, count in sorted(info["kinds"].items()))
            lines.append(f"   +0x{offset:X}  （基址 x{info['base_register']}，{kinds}）")
    if result["constants"]:
        lines.append("")
        lines.append("函数体里的立即数常量（上限/掩码常在这里）：")
        for item in result["constants"][:8]:
            lines.append(f"   {item}")

    strongest = next(((o, i) for o, i in result["read_write_fields"]
                     if i.get("incremented_by_argument")), None)
    if strongest is not None:
        offset, info = strongest
        name = target or "kEntityPlayer<X>Offset"
        lines.append("")
        lines.append("可直接粘进常量注释的证据块：")
        lines.append(f"//   {name} = 0x{offset:X}")
        for line in info["evidence"][:6]:
            lines.append(f"//   证据：{line}")
        lines.append("//   入口 4 字节（小端整字）："
                     f"{result['fingerprint_word']}（文件序 {result['fingerprint_bytes']}）")
        lines.append(f"inline constexpr std::uint32_t {name.replace('Offset', 'EntryWord')} = "
                     f"{result['fingerprint_word']}U;")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="提取引擎 Add<X> 一类函数的字段偏移与入口指纹")
    parser.add_argument("entry", help="函数入口偏移，例如 0x2804E8")
    parser.add_argument("--nro", default=str(DEFAULT_NRO), help="NRO 路径（默认是仓库里那份）")
    parser.add_argument("--name", default=None, help="建议的常量名（打印证据块时用）")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    parser.add_argument("--pretty", action="store_true", help="额外打印反汇编（走 nro_disasm + llvm-objdump）")
    args = parser.parse_args(argv)

    entry = int(args.entry, 0)
    nro_path = Path(args.nro)
    if not nro_path.is_file():
        print(f"找不到 NRO：{nro_path}", file=sys.stderr)
        return 2
    result = analyse(nro_path, entry, args.pretty)

    if args.json:
        payload = {
            "entry": result["entry"],
            "fingerprint_word": result["fingerprint_word"],
            "fingerprint_bytes": result["fingerprint_bytes"],
            "instructions": result["instructions"],
            "read_write_fields": [
                {"offset": offset, **{k: v for k, v in info.items() if k != "evidence"},
                 "evidence": info["evidence"]}
                for offset, info in result["read_write_fields"]
            ],
            "increment_hits": sorted(
                offset for offset, info in result["read_write_fields"]
                if info.get("incremented_by_argument")
            ),
            "write_only_fields": [
                {"offset": offset, "kinds": info["kinds"]} for offset, info in result["write_only_fields"]
            ],
            "constants": result["constants"],
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(render(result, args.name))

    if args.pretty:
        disassembler = load_disassembler()
        print()
        print("\n".join(disassembler.disassemble(str(nro_path), entry, result["instructions"] * 4)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
