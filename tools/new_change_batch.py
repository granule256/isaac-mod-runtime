#!/usr/bin/env python3
"""开一批改动时，把"留痕骨架"一次建好（日志条目 + 存档子目录 + 必需文件）。

## 为什么要有它

本项目有一条**由门禁强制**的留痕规范（`docs/改动日志-YYYYMMDD.md` + `dist/change-archive-YYYYMMDD/NNN-主题/`），
而它有三个"纯靠记性"的坑，全都真的红过：

1. 当天日志里引用的存档子目录**必须存在**，磁盘上的子目录也**必须被日志引用**（双向）；
2. 每个子目录必须有 `README.md`，以及 `change.patch`（或在 README 里写明"无代码改动"）；
3. 含逐字节产物的目录根必须有 `.gitattributes` 写 `* -text`（否则 git 做行尾规范化、备份不再逐字节相同）。

而且 —— **`change.patch` 必须在 `git add` 之前生成**：嵌套套件按 `git ls-files` 复制工作区，
未跟踪的新文件不会被复制，晚生成就会让那条放大器用例一起红（踩过两次）。

这个脚本把骨架一次铺好，并在最后把这几条**再说一遍**。

## 用法

    python3 tools/new_change_batch.py 027-tooling --title "工具化：取证配方 + 批次预检 + 脚手架"
    python3 tools/new_change_batch.py 028-some-fix --dry-run

不带 `NNN-` 前缀时会自动取当天存档目录里的下一个序号。
"""

from __future__ import annotations

import argparse
import datetime
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]

BUILD_COMMAND = '''docker run --rm -v "$PWD":/work -w /work devkitpro/devkita64:latest bash -lc \\
  '. /opt/devkitpro/devkita64.sh && make -C runtime -j8 LAYERED_RUNTIME=1 PROBE_BREAK=0 \\
   SKIP_DEFAULT_PC_MODS=1 WORKER_STARTUP_DELAY_SECONDS=5 \\
   OUT=.gdbsym-artifacts/deploy BUILD=.gdbsym-build EXL_ARTIFACT_DIR=.gdbsym-artifacts runtime_module'
'''


def next_number(archive: pathlib.Path) -> str:
    numbers = []
    if archive.is_dir():
        for entry in archive.iterdir():
            match = re.match(r"^(\d{3})-", entry.name)
            if match:
                numbers.append(int(match.group(1)))
    return f"{(max(numbers) + 1) if numbers else 1:03d}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="建当天日志条目 + 存档子目录骨架")
    parser.add_argument("slug", help="目录名，例如 027-tooling（省略序号则自动取下一个）")
    parser.add_argument("--title", default=None, help="日志条目的标题（默认用 slug）")
    parser.add_argument("--date", default=None, help="日期 YYYYMMDD（默认今天）")
    parser.add_argument("--dry-run", action="store_true", help="只打印将要建什么")
    args = parser.parse_args(argv)

    date = args.date or datetime.date.today().strftime("%Y%m%d")
    archive_root = ROOT / "dist" / f"change-archive-{date}"
    slug = args.slug
    if not re.match(r"^\d{3}-", slug):
        slug = f"{next_number(archive_root)}-{slug}"
    number = slug[:3]
    title = args.title or slug[4:].replace("-", " ")

    batch = archive_root / slug
    log = ROOT / "docs" / f"改动日志-{date}.md"

    readme = f"""# {number} {title}

## 改了什么

| 文件 | 改动 |
| --- | --- |
| （待填） | （待填） |

## 为什么改

（待填：当前存在的具体问题或痛点。）

## 怎么验证

```bash
python3 tools/preflight_batch.py      # 快档预检（约 0.5 秒）
python3 tools/run_tests.py            # 全量门禁
```

## 怎么回退

```bash
git revert <本批提交>
# 或：git apply -R dist/change-archive-{date}/{slug}/change.patch
```

## 产物身份

| 项 | 值 |
| --- | --- |
| 改动前（= 本目录 `*.before`） | （待填：字节数 / sha256） |
| 改动后（= 本目录 `*.after`） | （待填：字节数 / sha256） |
| 构建命令 | `build-command.txt` |

## 结果与结论

（待填：门禁数字、真机结果，**包括"错了/被推翻"的部分**。）
"""

    log_entry = f"""
---

## {number} {title}

**改了什么**：（待填）
**为什么**：（待填）
**产物身份**：（待填）
**怎么回退**：`git revert` 本批提交，或 `git apply -R` 本目录的 `change.patch`。
**结果与结论**：（待填）
"""

    if args.dry_run:
        print(f"（dry-run）会建目录：{batch.relative_to(ROOT)}")
        print(f"（dry-run）会写文件：README.md / .gitattributes / build-command.txt")
        print(f"（dry-run）会追加日志条目到：{log.relative_to(ROOT)}")
        return 0

    batch.mkdir(parents=True, exist_ok=True)
    (batch / "README.md").write_text(readme, encoding="utf-8")
    (batch / ".gitattributes").write_text("* -text\n", encoding="utf-8")
    (batch / "build-command.txt").write_text(BUILD_COMMAND, encoding="utf-8")
    if not log.exists():
        log.write_text(f"# 改动日志 {date}\n\n> 逐条追加。每条至少写：改了什么、为什么改、改了哪些文件、\n"
                       "> 产物身份（字节数 + sha256）、怎么回退、结果与结论（包括\"错了/被推翻\"）。\n"
                       "> 对应存档目录：`dist/change-archive-%s/NNN-主题/`。\n" % date,
                       encoding="utf-8")
    with log.open("a", encoding="utf-8") as handle:
        handle.write(log_entry)

    print(f"已建：{batch.relative_to(ROOT)}（README.md / .gitattributes / build-command.txt）")
    print(f"已追加日志条目：{log.relative_to(ROOT)} 的 ## {number}")
    print()
    print("接下来（顺序别换）：")
    print("  1. 先做改动；改完把改动前后产物放进这个目录（逐字节，文件名 *.before / *.after）；")
    print("  2. **`git add` 之前**生成精确 diff：")
    print("     git diff <显式路径…> > dist/change-archive-%s/%s/change.patch" % (date, slug))
    print("     ⚠️ 范围要显式列出：这个仓库里有些构建产物在工作区里天然是脏的（`.wdelay5-build` 之类），")
    print("        按目录一把抓会把它们卷进 patch。")
    print("  3. 跑预检 `python3 tools/preflight_batch.py`，再跑全量门禁；")
    print("  4. 填日志与 README 的\"结果与结论\"，然后提交（`docs/` 与 `dist/` 一起进本地提交）。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
