#!/usr/bin/env python3
"""报告 `.fnt` 字体的**字形覆盖**（能不能画中文），支持 Isaac/BMFont 两种块序。

## 为什么需要它

2026-09-17 的真实事故：模组用 `font/droid.fnt` 画中文，屏幕上**什么都不显示**——
因为游戏自带字体只有 ASCII 字形（`droid.fnt` 整个索引 3896 字节），
而"缺字形"是**静默**的：不报错、不警告，只是空白。当时为了确认这件事，是临时手写解析脚本查的；
这个工具把那次的一次性脚本固化下来，**以后画文字前先跑一遍**。

## 格式要点（Isaac 的 `.fnt` 与 BMFont 官方字段号**不同**，踩过）

* 文件头 `BMF` + 版本字节；
* 块 = `类型(1 字节)` + `长度(4 字节, 小端)` + 内容；
* 本项目的镜像里：**类型 3 = 图集文件名（可多个，NUL 分隔）**、**类型 4 = 字符表**
  （`[count(4)] + count × 20 字节`，每条以 `uint32 码位` 开头）；
* 若文件是 BMFont **文本**格式（`char id=<数字>` 行），也一并支持。

用法：
    python3 tools/fnt_glyph_report.py <字体.fnt> [更多.fnt ...]
    python3 tools/fnt_glyph_report.py --json out.json <字体.fnt> ...
    python3 tools/fnt_glyph_report.py --dir "<游戏资源目录>/resources/font"

退出码：0 = 全部可解析；1 = 有文件解析失败（当门禁用时能直接判红）。
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import struct
import sys

#: 中文（含常用字）的抽样：用于给出"能不能画中文"这一句人话结论。
CJK_SAMPLE = "神性体圣饼铲子碎片恶魔天使圣杯钥匙炸弹硬币中文测试"


def parse_binary_fnt(raw: bytes) -> tuple[list[int], list[str]] | None:
    """返回 (码位列表, 图集文件名列表)；不是二进制 BMF 时返回 None。"""
    if raw[:3] != b"BMF":
        return None
    codepoints: list[int] = []
    pages: list[str] = []
    offset = 4
    while offset < len(raw):
        block_type = raw[offset]
        offset += 1
        if offset + 4 > len(raw):
            break
        size = struct.unpack_from("<I", raw, offset)[0]
        offset += 4
        content = raw[offset : offset + size]
        offset += size
        if block_type == 4:
            # ⚠️ Isaac 的字符块**没有"数量"前缀**：内容就是 `size / 20` 条 20 字节的记录，
            # 每条前 4 字节是码位。把第一条记录的前 4 字节当"数量"读会得到 0x20 = 32（空格），
            # 于是整个字体看起来"只有 32 个字形" —— 这个坑 2026-09-17 踩过一次，别再犯。
            count = size // 20
            for index in range(count):
                begin = index * 20
                if begin + 4 > len(content):
                    break
                codepoints.append(struct.unpack_from("<I", content, begin)[0])
        elif block_type == 3:
            pages.extend(part.decode("latin-1") for part in content.split(b"\0") if part)
    return codepoints, pages


def parse_text_fnt(raw: bytes) -> tuple[list[int], list[str]] | None:
    if b"char id=" not in raw:
        return None
    codepoints = [int(value) for value in re.findall(rb"char id=(\d+)", raw)]
    pages = [part.decode("latin-1") for part in re.findall(rb"page file=\"([^\"]+)\"", raw)]
    return codepoints, pages


def report(path: pathlib.Path) -> dict:
    raw = path.read_bytes()
    parsed = parse_binary_fnt(raw) or parse_text_fnt(raw)
    if parsed is None:
        return {"path": str(path), "ok": False, "reason": "既不是二进制 BMF 也不是文本 BMFont"}
    codepoints, pages = parsed
    if not codepoints:
        return {"path": str(path), "ok": False, "reason": "解析出来的字符表是空的"}
    cjk = [c for c in codepoints if c > 0x2E80]
    missing = [ch for ch in CJK_SAMPLE if ord(ch) not in codepoints]
    return {
        "path": str(path),
        "ok": True,
        "index_bytes": len(raw),
        "glyphs": len(codepoints),
        "max_codepoint": max(codepoints),
        "cjk_glyphs": len(cjk),
        "pages": pages,
        "can_draw_chinese": not missing,
        "missing_from_sample": missing,
    }


def human(entry: dict) -> str:
    if not entry["ok"]:
        return f"{entry['path']}: 解析失败 —— {entry['reason']}"
    verdict = "含中文" if entry["can_draw_chinese"] else "**不含中文（画中文只会空白）**"
    return (
        f"{entry['path']}: 索引 {entry['index_bytes']} 字节、字形 {entry['glyphs']} 个、"
        f"码位上限 {entry['max_codepoint']:#x}、中日韩码位 {entry['cjk_glyphs']} 个 ⇒ {verdict}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="报告 .fnt 的字形覆盖（能不能画中文）")
    parser.add_argument("fonts", nargs="*", type=pathlib.Path, help="一个或多个 .fnt")
    parser.add_argument("--dir", type=pathlib.Path, action="append", default=[],
                        help="目录（递归找 *.fnt），可多次给")
    parser.add_argument("--json", type=pathlib.Path, help="把结果写成 JSON")
    args = parser.parse_args()

    targets: list[pathlib.Path] = list(args.fonts)
    for directory in args.dir:
        targets.extend(sorted(directory.rglob("*.fnt")))
    if not targets:
        parser.error("至少要给一个 .fnt 或 --dir")

    results = [report(path) for path in targets]
    for entry in results:
        print(human(entry))
    if args.json is not None:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"（JSON 已写入 {args.json}）")
    return 0 if all(entry["ok"] for entry in results) else 1


if __name__ == "__main__":
    sys.exit(main())
