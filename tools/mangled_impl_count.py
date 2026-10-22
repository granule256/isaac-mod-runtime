#!/usr/bin/env python3
"""数一个方法在整份 ``Repentance.nro`` 里有**几个实现**（按 mangled 名的长度前缀解析）。

这是"进批三条硬门槛"里的第 ② 条（**同名方法只有一个类有实现**）的判据工具。
它回答的是一个很具体的问题：`IsVulnerableEnemy` 在镜像里到底有几个 `IsaacRepentance::*`
实现？一个 ⇒ 可以直调那个地址；两个以上 ⇒ 得先搞清谁重写了谁，不能盲调。

**为什么不直接用正则扫。** 以前用的是 ``_ZN15IsaacRepentance\\w*<名>E\\w*``，它有
三个会**静默给出相反结论**的坑：

1. **`const` 方法的前缀是 `_ZNK`，不是 `_ZN`**（`_ZNK` 是两个 cv 限定符：`K` = const）。
   只写 `_ZN` 时，const 方法**恒 0 命中** —— 2026-10-02 批次 286 就在
   `Entity::IsVulnerableEnemy`（`_ZNK15IsaacRepentance6Entity17IsVulnerableEnemyEPS0_`）
   上撞到：扫出 0 条，而"0 条"会被读成**"这条根本没有实现"**（与事实相反）。
   同样被漏掉的还有 `Entity::IsActiveEnemy`。
2. **`\\w*<名>` 会子串误命中** —— 扫 `IsFlying` 会命中
   `PlayerManager::AnyPlayerIsFlying`（多一个实现，虚警）。
3. **更不能靠"名字眼熟"** —— 批次 273 把 `Entity_NPC_HornfelDoor::Open/Close`
   （**另一个类**，只是名字撞车）当成了 `GridEntity_Door::Open/Close` 的重写，
   于是那两条被白挡了 11 批。

**正确做法**（本工具的做法）：定位 `_Z<限定符>15IsaacRepentance`，跳过**连续的**限定符，
然后逐段读「十进制长度 + 该长度的名字」；最后一段就是方法名，**逐字比对**（不是子串）。

用法::

    python3 tools/mangled_impl_count.py IsVulnerableEnemy
    python3 tools/mangled_impl_count.py IsFlying Morph CanShutDoors
    python3 tools/mangled_impl_count.py --nro "<other path>" IsHoldingItem

输出每个方法有多少个实现、各自的 owner 链与 mangled 签名。退出码：0 = 每个方法**恰好 1 个**
实现（可以直接进批）；1 = 有方法不是恰好 1 个（要人工判断，别盲调）。

★ 另有一条同源坑（2026-10-02 批次 284 立）：**"守卫长得像 `mov x0, xzr; ret`（两条）
⇒ 那个地址落在导入跳板区，不是函数体"** —— 在 `Entity:CanShutDoors` 上发现过。
那条与"数实现数"是两件事，本工具只管后者。
"""

from __future__ import annotations

import argparse
import os
import re
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DEFAULT_NRO = os.path.join(
    REPO_ROOT,
    "The Binding of Isaac_ Afterbirth+ 1.7.9b [010021C000B6A800][v524288][UPD]",
    "Program #0",
    "1",
    ".nro",
    "Repentance.nro",
)

#: `_Z` + 0~2 个 cv/ref 限定符 + `15IsaacRepentance`。`{0,2}` 是给 `_ZNK`/`_ZNV` 这类留位。
NAMESPACE_PATTERN = re.compile(rb"_Z[A-Za-z]{0,2}15IsaacRepentance")

#: 一条 mangled 名最多看这么多个字节（够长到覆盖 `E` 之前的全部组件）。
SEGMENT_WINDOW = 128

CV_QUALIFIERS = "NKVRO"


def components(mangled: str) -> tuple[list[str], int]:
    """把 `_Z…` 之后的「长度前缀」组件逐个切出来，并给出**解析停下的下标**。

    跳过**连续的** cv/ref 限定符（`_ZNK` = 两个：`N` 与 `K`）。
    只吃「十进制长度 + 该长度的名字」；碰到 `E`/`I` 等终止符时自然停下。
    ★ 返回的下标用来切"签名前缀" —— 千万别拿 `str.split("E")` 切：
    `IsaacRepentance6Entity` 里的 `E` 会让它在半个组件名上断开（本工具第一版就这么错过）。
    """
    index = 2
    while index < len(mangled) and mangled[index] in CV_QUALIFIERS:
        index += 1
    out: list[str] = []
    while index < len(mangled) and mangled[index].isdigit():
        start = index
        while index < len(mangled) and mangled[index].isdigit():
            index += 1
        length = int(mangled[start:index])
        out.append(mangled[index:index + length])
        index += length
    return out, index


def implementations(data: bytes, method: str) -> set[tuple[tuple[str, ...], str]]:
    """返回 `{(owner 组件链, 到解析停下处为止的签名), …}` —— 集合大小就是实现个数。"""
    found: set[tuple[tuple[str, ...], str]] = set()
    for match in NAMESPACE_PATTERN.finditer(data):
        segment = data[match.start():match.start() + SEGMENT_WINDOW].split(b"\0")[0]
        text = segment.decode("latin1", errors="replace")
        parts, stop = components(text)
        if parts and parts[-1] == method:
            found.add((tuple(parts[:-1]), text[:stop]))
    return found


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="数一个方法在 Repentance.nro 里有几个实现（按 mangled 长度前缀解析）。")
    parser.add_argument("methods", nargs="+", help="要数的方法名（可给多个）。")
    parser.add_argument("--nro", default=DEFAULT_NRO, help="NRO 路径（默认取仓库里那份）。")
    args = parser.parse_args(argv)

    with open(args.nro, "rb") as handle:
        data = handle.read()

    exit_code = 0
    for method in args.methods:
        rows = sorted(implementations(data, method))
        print(f"{method:<24} -> {len(rows)} 个实现")
        for owner, signature in rows:
            print(f"      owner = {'/'.join(owner) if owner else '(无命名空间之外的主类链)'}")
            print(f"      {signature}")
        if len(rows) != 1:
            exit_code = 1
    if exit_code != 0:
        print("⇒ 有方法不是「恰好 1 个实现」：进批前必须人工判断（谁重写了谁、能不能直调）。",
              file=sys.stderr)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
