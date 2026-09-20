"""门禁：**不许把构建产物提交进 git**（批次 096，2026-09-20）。

## 为什么有这条门禁

2026-09-20 审计公开仓库时发现：**8 个实验构建目录 + 1 个产物目录被跟踪进了 git**
（`runtime/.batch15-build/`、`.only-required-build/`、`.legacyfree-build/`、
`.legacyforwarder-build/`、`.skip-present-build/`、`.skip-render-build/`、
`.wdelay0-build/`、`.wdelay5-build/`、`.wdelay0-artifacts/`），共 **1,872 个文件、约 89 MB**，
**占公开仓库体积的 91%**；里面是 `.o`/`.d`/**`.map`**（我们模块的完整符号映射）
以及一个 `subsdk9.head-before` 二进制备份。

它们不是"不小心多推了一次"，而是**一直在 master 里被跟踪** ⇒ 每次发布都会被重新推上公开仓库
（发布脚本按白名单 `git checkout master -- runtime` 同步，跟踪什么就推什么）。

**教训与对策**：光清理不够 —— 清理只是把这一次的垃圾拿走，**下一次构建又会留下新的目录**。
所以把它变成门禁：**已跟踪的文件里出现构建产物 ⇒ 直接判红**，并指向修法
（`git rm -r --cached` + 补 `.gitignore`）。

## 判据（改宽改窄都会红）

1. 已跟踪路径里**不许出现** `runtime/.xxx-build/`、`runtime/.xxx-artifacts/` 这类构建/产物目录；
2. 已跟踪路径里**不许出现**常见构建产物后缀（`.o`/`.d`/`.map`/`.lst`/`.build_flags`/`.elf`/`.nso`/`.nro`…）
   —— 只查 `runtime/` 下，且**排除** vendored 的 `exlaunch`（上游自带少量数据文件）；
3. `.gitignore` 里必须有盖住这些目录的规则（否则新目录又会以"未跟踪"的形态被 `git add -A` 收进去，
   发布脚本的守卫也会因为"白名单路径下有未跟踪文件"而失败）。
"""

import pathlib
import subprocess
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]

#: 构建/产物目录的形态：`runtime/.名字-build/` 或 `runtime/.名字-artifacts/`
BUILD_DIR_PREFIXES = ("runtime/.",)
BUILD_DIR_SUFFIXES = ("-build/", "-artifacts/")

#: 构建产物后缀（只查这些；`exlaunch` 是 vendored 上游，单独排除）
ARTIFACT_SUFFIXES = (".o", ".d", ".map", ".lst", ".elf", ".nso", ".nro", ".nsp", ".npdm")
ARTIFACT_NAMES = (".build_flags",)

#: 排除的路径片段（vendored 上游 / 第三方）
EXCLUDED_PARTS = ("/exlaunch/", "/third_party/")


def tracked_files() -> list[str] | None:
    """本仓库**已跟踪**的文件；`None` 表示这里不是 git 工作区（此时本门禁无从判断）。

    ★ 为什么必须处理这种情况（2026-09-20 实测踩到）：本仓库有一条"嵌套套件"用例
    （`test_game_file_reader_stage10`）会把工作区**按 `git ls-files` 复制到临时目录**再整套跑一遍，
    而副本里**没有 `.git`** —— 第一版门禁在这里直接 `check=True` 抛错，把**整套门禁**弄红了，
    连带让公开仓库的发布脚本在"门禁"那一步就被 `set -e` 提前终止（现象是：门禁输出打完就没了下文、
    公开分支一点没变）。**在非 git 目录里应当 skip，而不是失败。**
    """
    probe = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--is-inside-work-tree"],
                           capture_output=True, text=True)
    if probe.returncode != 0 or probe.stdout.strip() != "true":
        return None
    finished = subprocess.run(["git", "-C", str(ROOT), "ls-files", "-z"],
                              capture_output=True, text=False, check=True)
    return [os_fsdecode(entry) for entry in finished.stdout.split(b"\0") if entry]


def os_fsdecode(raw: bytes) -> str:
    import os

    return os.fsdecode(raw)


class NoTrackedBuildArtifacts(unittest.TestCase):
    def test_no_build_directories_or_artifacts_are_tracked(self):
        files = tracked_files()
        if files is None:
            self.skipTest("这里不是 git 工作区（嵌套套件的副本），无从判断已跟踪文件")
        offenders: list[str] = []
        for path in files:
            if any(part in f"/{path}" for part in EXCLUDED_PARTS):
                continue
            if not path.startswith("runtime/"):
                continue
            name = path.split("/")[-1]
            if (path.startswith(BUILD_DIR_PREFIXES) and any(
                    segment.endswith(BUILD_DIR_SUFFIXES)
                    for segment in path.split("/") if segment.startswith("."))):
                offenders.append(f"{path}（构建/产物目录）")
                continue
            if name.endswith(ARTIFACT_SUFFIXES) or name in ARTIFACT_NAMES:
                offenders.append(f"{path}（构建产物）")
        self.assertEqual(
            offenders, [],
            "这些构建产物被 git 跟踪了 —— 它们会被发布脚本按白名单原样推上公开仓库"
            "（2026-09-20 实测：1872 个文件、约 89 MB、占公开仓库体积 91%）。\n"
            "修法：`git rm -r --cached <目录>` 后再补 `.gitignore` 规则：\n"
            + "\n".join(offenders[:20]))

    def test_gitignore_covers_build_output(self):
        text = (ROOT / ".gitignore").read_text(encoding="utf-8")
        for rule in ("runtime/.*-build/", "runtime/.*-artifacts/"):
            self.assertIn(rule, text,
                          f"`.gitignore` 里必须有 `{rule}`：否则新构建目录会以"
                          f"「未跟踪文件」的形态被发布脚本的守卫拦下或误推上去")


if __name__ == "__main__":
    unittest.main()
