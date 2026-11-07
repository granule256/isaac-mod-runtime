#!/usr/bin/env python3
"""PC 侧取证：**按 Lua API 的名字找到 exe 里那条绑定函数**，并（可选）反汇编它。

## 它解决什么问题

"PC 上这条 API 到底怎么做的"是本项目反复要回答的问题（作业单第五节 5.2 给了配方）。
配方本身是四步，但每一步都手工做很烦、而且很容易**算错 VA**：

1. `strings -t x isaac-ng.exe | grep <方法名>` ⇒ 字符串的**文件偏移**；
2. 解析 PE 段表把文件偏移换成 **VA**（ImageBase + 所在段的 RVA 偏移）；
3. 全文件搜 `push imm32`（`0x68` + VA 小端）⇒ 找到**名字表项**（`push <函数>; push <名字>`
   成对出现，所以**名字前面那条 push 的立即数就是绑定函数的 VA**）；
4. `objdump -d --x86-asm-syntax=intel --start-address=<VA-0x30> --stop-address=<VA+0x120>`。

★ 第 3 步的"成对"这条是本项目实测定案的（2026-10-01 批次 259 用它读出了
`Room::GetClampedPosition` 的三个文档没写的缺省值）。**别自己重新推导**，直接用这个工具。

## 用法

    python3 tools/pc_exe_binding.py GetClampedPosition            # 只打印绑定函数 VA
    python3 tools/pc_exe_binding.py GetClampedPosition --disasm   # 再反汇编它（前后各一段）
    python3 tools/pc_exe_binding.py GridSpawn --disasm --before 0x40 --after 0x140
    python3 tools/pc_exe_binding.py --exe "<另一份 exe 路径>" <方法名>

## 已知限制（别被它骗）

* **拼写必须与 exe 里的字符串逐字一致**（例如 `Isaac.GridSpawn` 在名字表里只写 `GridSpawn`；
  找不到时它会列出**最接近的几个名字**，照着挑）。
* 同一个名字可能在 exe 里出现多次（不同 DLC 版本的绑定表）⇒ 工具会**把全部命中都列出来**，
  需要人按反汇编内容判断哪一条是当前版本用的。
* 反汇编窗口是**写死的长度**，不是"这个函数的真实长度"—— 它是 x86、没有符号表可界定边界。
  越过函数末尾的指令**看起来照样像证据**（与批次 244 那条"AArch64 要先界定函数长度"同类），
  所以读的时候要认得出 `ret`/`int3` 填充。
"""

from __future__ import annotations

import argparse
import os
import pathlib
import struct
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
DEFAULT_EXE = ROOT / "The Binding of Isaac Rebirth" / "isaac-ng.exe"
OBJDUMP = "/usr/bin/objdump"


class PeImage:
    """最小 PE32 解析：只做"文件偏移 ↔ VA"与字符串/立即数搜索。"""

    def __init__(self, data: bytes):
        self.data = data
        pe = struct.unpack_from("<I", data, 0x3C)[0]
        if data[pe:pe + 4] != b"PE\0\0":
            raise ValueError("不是 PE 文件")
        self.image_base = struct.unpack_from("<I", data, pe + 24 + 28)[0]
        section_count = struct.unpack_from("<H", data, pe + 6)[0]
        optional_size = struct.unpack_from("<H", data, pe + 20)[0]
        offset = pe + 24 + optional_size
        self.sections: list[tuple[str, int, int, int, int]] = []
        for index in range(section_count):
            base = offset + index * 40
            name = data[base:base + 8].rstrip(b"\0").decode(errors="replace")
            virtual_size, virtual_address, raw_size, raw_offset = struct.unpack_from(
                "<IIII", data, base + 8)
            self.sections.append((name, virtual_address, virtual_size, raw_offset, raw_size))

    def file_offset_to_va(self, offset: int) -> int | None:
        for _name, virtual_address, _vsize, raw_offset, raw_size in self.sections:
            if raw_offset <= offset < raw_offset + raw_size:
                return self.image_base + virtual_address + (offset - raw_offset)
        return None

    def va_to_file_offset(self, va: int) -> int | None:
        rva = va - self.image_base
        for _name, virtual_address, virtual_size, raw_offset, _raw_size in self.sections:
            if virtual_address <= rva < virtual_address + max(virtual_size, 1):
                return raw_offset + (rva - virtual_address)
        return None

    def section_of_va(self, va: int) -> str | None:
        """这个 VA 落在哪个段里（不在任何段里 ⇒ 不是可执行代码地址，多半是读歪了）。

        ★ 批次 320 加：名表错位时读出来的"函数 VA"会是数据区的垃圾（实测 `0xCC48300`），
        这里用"在不在某个段里"把它挡掉 —— 只判段、不判它是不是函数开头（x86 没有符号表，
        判不了"开头"，那是反汇编时要人看的事）。
        """
        rva = va - self.image_base
        for name, virtual_address, virtual_size, _raw_offset, _raw_size in self.sections:
            if virtual_address <= rva < virtual_address + max(virtual_size, 1):
                return name
        return None

    def find_string_offsets(self, needle: str) -> list[int]:
        """按"零结尾的 ASCII 串"找，避免命中别的串的一部分。"""
        pattern = needle.encode() + b"\0"
        found: list[int] = []
        start = 0
        while True:
            hit = self.data.find(pattern, start)
            if hit == -1:
                return found
            # 前一字节必须是不可打印的（否则命中的是更长串的尾巴）。
            if hit == 0 or not (0x20 <= self.data[hit - 1] < 0x7F):
                found.append(hit)
            start = hit + 1

    def find_push_references(self, va: int) -> list[int]:
        """`push imm32`（`0x68` + 小端 VA）出现的位置。"""
        pattern = b"\x68" + struct.pack("<I", va)
        found: list[int] = []
        start = 0
        while True:
            hit = self.data.find(pattern, start)
            if hit == -1:
                return found
            found.append(hit)
            start = hit + 1

    def read_u32(self, file_offset: int) -> int:
        return struct.unpack_from("<I", self.data, file_offset)[0]


def dump(pe: PeImage, va: int, before: int, after: int) -> str:
    if not os.path.exists(OBJDUMP):
        return f"（找不到 {OBJDUMP}，跳过反汇编）"
    result = subprocess.run(
        [OBJDUMP, "-d", "--x86-asm-syntax=intel",
         f"--start-address=0x{max(va - before, 0):X}", f"--stop-address=0x{va + after:X}",
         str(pe_path_holder["path"])],
        text=True, capture_output=True,
    )
    return result.stdout


pe_path_holder: dict[str, str] = {}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("name", nargs="?", help="exe 名字表里的那个字符串（逐字，不含引号）")
    parser.add_argument("--exe", default=str(DEFAULT_EXE), help="isaac-ng.exe 路径")
    parser.add_argument("--disasm", action="store_true", help="反汇编命中的绑定函数")
    parser.add_argument("--before", type=lambda v: int(v, 0), default=0x30)
    parser.add_argument("--after", type=lambda v: int(v, 0), default=0x120)
    parser.add_argument("--list", action="store_true", help="列出名字表里包含该词的候选名字")
    args = parser.parse_args(argv)

    path = pathlib.Path(args.exe)
    if not path.is_file():
        print(f"找不到 exe：{path}", file=sys.stderr)
        return 2
    pe_path_holder["path"] = str(path)
    pe = PeImage(path.read_bytes())

    if args.list or args.name is None:
        if args.name is None:
            print("要么给名字，要么 --list 配合一个词", file=sys.stderr)
            return 2
        # 名字表是连续的以 \0 分隔的串：把包含该词的候选列出来，便于纠正拼写。
        blob = pe.data
        candidates = set()
        index = blob.find(args.name.encode())
        while index != -1:
            left = blob.rfind(b"\0", max(index - 64, 0), index)
            right = blob.find(b"\0", index)
            text = blob[left + 1:right].decode(errors="replace")
            if 1 <= len(text) <= 48 and all(0x20 <= ord(c) < 0x7F for c in text):
                candidates.add(text)
            index = blob.find(args.name.encode(), index + 1)
        for text in sorted(candidates)[:40]:
            print(text)
        return 0

    offsets = pe.find_string_offsets(args.name)
    if not offsets:
        print(f"name table 里没有逐字等于 {args.name!r} 的字符串 —— 用 --list 看候选拼写",
              file=sys.stderr)
        return 1

    for offset in offsets:
        va = pe.file_offset_to_va(offset)
        push_sites = pe.find_push_references(va) if va is not None else []
        print(f"string @ file 0x{offset:X}  va 0x{va:X}  push 引用 {len(push_sites)} 处")
        for site in push_sites:
            site_va = pe.file_offset_to_va(site)
            # 成对出现：`push <函数VA>; push <名字VA>` ⇒ 名字那条 push **前面**那一条
            # 就是"函数"那条 push。
            #
            # 补的两道校验 —— 在这之前这里无条件读"前 4 字节"，
            #   于是名表里那些**不成对**的区域会产出**移位的假行**（实测：`Remove` 报出
            #   `0xCC48300`、`Explode` 报出 `0x6A0000`，两个都不是真正的绑定函数）。
            #   判据从"读前 4 字节"改成：
            #     ① 前一条**必须真的是 `push imm32`**（`site - 5` 处是 `0x68`）—— 表里 push 是 5 字节；
            #     ② 读出来的那个值**必须真的落在某个段里**（`va_to_file_offset` 不为 None）。
            #   两条都不满足时**显式跳过并说明**，不猜、不静默给一个数。
            previous = site - 5
            if previous < 0 or pe.data[previous] != 0x68:
                print(f"  name-table entry @ file 0x{site:X} (va 0x{site_va:X})"
                      f" ⇒ ★ 前一条不是 push imm32（表里这一处不成对）⇒ 跳过")
                continue
            fn = pe.read_u32(previous + 1)
            section = pe.section_of_va(fn)
            if section is None:
                print(f"  name-table entry @ file 0x{site:X} (va 0x{site_va:X})"
                      f" ⇒ ★ 0x{fn:X} 不在任何段里 ⇒ 不是绑定函数，跳过")
                continue
            print(f"  name-table entry @ file 0x{site:X} (va 0x{site_va:X})"
                  f" ⇒ 绑定函数 VA 0x{fn:X}   [{section}]")
            if args.disasm:
                print(dump(pe, fn, args.before, args.after))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
