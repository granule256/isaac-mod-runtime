"""门禁：**改动留痕**必须完整 —— 存档子目录与当天改动日志必须互相对应。

## 为什么要有它

`AGENTS.md` 的「改动留痕规范」（2026-09-16 起，用户要求）写着：**任何改动都要留痕；
没有记录 + 没有备份，就等于这次改动没做过**。而这条规矩此前**只靠自觉** ——
2026-09-17 当天就漏了 4 个存档子目录（004/005/011/012），补的时候还得回头翻提交。
所以把它变成机器判据：

1. 当天日志里引用的每个 `dist/change-archive-<日期>/<NNN-主题>/` **必须真实存在**；
2. 磁盘上每个存档子目录**必须被当天日志引用**（不许有"没人知道为什么在这"的目录）；
3. 每个子目录必须有 `README.md`；
4. 每个子目录必须有 `change.patch`，或者在 README 里写明"**无代码改动**"
   （纯构建/纯设备/纯文档的批次没有 diff 可写，但必须明说，不能靠沉默）；
5. 子目录里若含**二进制产物**（`subsdk9*`、`*.lua`、`*.npdm` 等逐字节备份），
   存档根目录必须有 `.gitattributes` 且含 `* -text`（否则 git 会做行尾规范化、备份不再逐字节相同）。
"""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DIST = ROOT / "dist"

DIR_REFERENCE_RE = re.compile(r"change-archive-(\d{8})/([^/\s`]+)")
BINARY_SUFFIXES = (".lua", ".npdm", ".on")
BINARY_PREFIXES = ("subsdk9", "main.npdm", "no-lua.on")


def _plausible_archive_name(name: str) -> bool:
    """过滤"完整路径"里明显是占位/示例/文件的尾巴（批次 433）。

    放宽完整路径收集（让 `jit-432-card-state`、`DIAG1-api-attribution` 这类**非"NNN-"起的
    合法目录名**也能被收）之后，文本里的"示例"尾巴也会被正则吃到 —— 实测被吃到的有：
    `NNN-主题`（占位）、`014-…` / `185-...`（省略号）、`152~157`（范围）、`<编号>-<主题>`、
    `change-archive-20260930/.gitattributes`（文件）。用"名字字符集"把这些剔掉：
    只接受 `[A-Za-z0-9_-]`、首尾不为 `-` 的非空名（占位里的中文/`…`/`~`/`<`/`.` 自然出局）。
    """
    return bool(name) and name[0] != '-' and name[-1] != '-' and all(
        c.isascii() and (c.isalnum() or c in '_-') for c in name)


def archive_roots() -> list[Path]:
    return sorted(path for path in DIST.glob("change-archive-*") if path.is_dir())


def referenced_dirs(log_text: str, date: str) -> set[str]:
    """当天日志里提到的存档子目录。

    两种引用形态都认（09-16 那天用过"裸名字"写法）：
      * `dist/change-archive-<日期>/<NNN-主题>/`（带完整路径）
      * `<NNN-主题>/`（只写子目录名，例如 "（存档 `025-no-lua-state-isolation/`）"）

    ★ 批次 433（2026-10-11）：裸名字收集**之前**先把"完整路径"形态整体抹掉 ——
      否则 `dist/change-archive-20261008/416-heap-256mib/` 的**尾巴**也会被裸名字正则
      收进"当天引用"，要求它存在于**另一天**的存档目录下（20261010 的日志撞过这个误报）。
      完整路径引用仍由上面的 `DIR_REFERENCE_RE` 按**它自己的日期**登记与校验，
      检查没有被弱化（跨日期引用照旧要指向真实存在的目录）。
    """
    referenced = {name for stamp, name in DIR_REFERENCE_RE.findall(log_text)
                  if stamp == date and _plausible_archive_name(name)}
    stripped = DIR_REFERENCE_RE.sub("", log_text)
    for name in re.findall(r"\b(\d{3}-[A-Za-z0-9_-]+)/", stripped):
        referenced.add(name)
    return referenced


class ChangeArchiveCompletenessTests(unittest.TestCase):
    def test_archives_exist_for_every_referenced_directory(self):
        for root in archive_roots():
            date = root.name[len("change-archive-") :]
            log = ROOT / "docs" / f"改动日志-{date}.md"
            if not log.exists():
                self.fail(f"{root.relative_to(ROOT)} 没有对应的当天日志 {log.name}")
            referenced = referenced_dirs(log.read_text(encoding="utf-8"), date)
            on_disk = {path.name for path in root.iterdir() if path.is_dir()}
            self.assertFalse(
                referenced - on_disk,
                f"{date} 的日志引用了不存在的存档子目录：{sorted(referenced - on_disk)}",
            )
            self.assertFalse(
                on_disk - referenced,
                f"{date} 的存档里有日志没提到的子目录（谁也不知道它为什么在这）："
                f"{sorted(on_disk - referenced)}",
            )

    def test_every_archive_directory_has_readme_and_patch_or_a_stated_reason(self):
        """一次把所有缺项都列出来（不要第一个就抛，否则每次都只看到一个）。"""
        problems: list[str] = []
        for root in archive_roots():
            for path in sorted(item for item in root.iterdir() if item.is_dir()):
                if not (path / "README.md").exists():
                    problems.append(f"{path.relative_to(ROOT)} 缺 README.md")
                    continue
                readme = (path / "README.md").read_text(encoding="utf-8")
                if not (path / "change.patch").exists() and "无代码改动" not in readme:
                    problems.append(
                        f"{path.relative_to(ROOT)} 既没有 change.patch，也没写明「无代码改动」"
                    )
        self.assertFalse(problems, "留痕缺项：\n  - " + "\n  - ".join(problems))

    def test_byte_exact_archives_declare_gitattributes(self):
        for root in archive_roots():
            has_binary = False
            for path in root.rglob("*"):
                if not path.is_file():
                    continue
                if path.name.startswith(BINARY_PREFIXES) or path.suffix in BINARY_SUFFIXES:
                    has_binary = True
                    break
            if not has_binary:
                continue
            attributes = root / ".gitattributes"
            self.assertTrue(attributes.exists(),
                            f"{root.relative_to(ROOT)} 里有逐字节产物，却没有 .gitattributes")
            self.assertIn("* -text", attributes.read_text(encoding="utf-8"),
                          f"{root.relative_to(ROOT)} 的 .gitattributes 必须写 `* -text`")


if __name__ == "__main__":
    unittest.main()
