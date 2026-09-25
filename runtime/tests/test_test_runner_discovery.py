"""门禁运行器（`tools/run_tests.py`）的**发现阶段**判据（批次 109，2026-09-24）。

## 这条门禁在防什么

**一个坏掉的门禁 = 一条永远绿的假证据。**

`unittest` 的发现器对"模块导入失败"是**吞掉**的：一个语法错的 `test_x.py` 不会让 `discover()`
报错，而是被换成一个 `_FailedTest`（归到 `unittest.loader` 名下）⇒ 真正的模块名**从列表里消失**。
于是在 `tools/run_tests.py` 里：

* `--only x`（x 是那个坏模块）⇒ 打印 `Ran 0 tests ...（0 个模块）OK`、**退出码 0**；
* `--fast` / 全量 ⇒ 列表里少一个模块，**照旧全绿**。

2026-09-24 实测（批次 108 收尾时撞到的）：新写的 `test_engine_call_access.py` 里有一行引号写错
⇒ 那条门禁**根本没被跑**，而 `--only engine_call_access` 的输出看着像"跑过了、没问题"。

## 判据

1. 正常情况：好模块被认出来，列表里**不许**出现 `unittest.loader`（它出现就是有模块被吞了）；
2. 放一个语法错的 `test_broken.py` ⇒ `discover_modules()` **必须抛 `DiscoveryError`**，
   且报错里点名那个文件（不是"静默少一个"）；
3. 把坏文件删掉 ⇒ 恢复；
4. 导入期**合法跳过**（`raise unittest.SkipTest`）**不许**被误判成失败 ——
   `unittest` 里"失败"与"跳过"走**不同**的类（`_FailedTest` vs 动态类 `ModuleSkipped`）；
5. **端到端**：真实跑一遍 `tools/run_tests.py`（在临时根目录里放一份副本），
   坏模块在场 ⇒ 退出码 **2**；删掉 ⇒ 退出码 **0**（且那条好模块真的被跑了）。

★ 为什么都在临时目录里造：往 `runtime/tests/` 写临时文件会污染**并发跑着的**其它门禁
（好几条门禁会枚举那个目录），所以判据自带一个隔离的"根目录"（含 `probe/tests/` 与
`tools/run_tests.py` 的副本）。
★ 包名带上 PID：临时目录里的包名若叫 `runtime`，会被**真仓库**那个 `runtime` 命名空间包
遮蔽（`runtime.tests.test_good` 会解析到真仓库的文件）⇒ 判据自己先撞上一个假的
`ModuleNotFoundError`。带上 PID 的名字不会与仓库里任何东西重名。
"""

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tools.run_tests import DiscoveryError, discover_modules


ROOT = Path(__file__).resolve().parents[2]
GOOD_MODULE = """\
import unittest


class GoodTests(unittest.TestCase):
    def test_passes(self):
        self.assertTrue(True)
"""

#: 语法错的模块：这正是 2026-09-24 撞到的形状（`def f(:`）。
BROKEN_MODULE = "def f(:\n    pass\n"

#: 导入期**合法跳过**的模块（`unittest` 用它表示"这个环境跑不了"）。
SKIPPED_MODULE = """\
import unittest

raise unittest.SkipTest("这个门禁在当前环境跑不了（判据：不该被算成导不进来）")
"""


class TestRunnerDiscoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="isaac_runner_probe_")
        # ★ 两套临时目录，**不能合并**：
        #   ① 直接调用 `discover_modules()` 的用例：包名必须唯一（带 PID）——否则会被
        #      **真仓库**的 `runtime` 遮蔽（那个名字已经在 `sys.modules` 里，见文件头说明）；
        #   ② 端到端跑命令行副本的用例：布局必须是 `runtime/tests/`，因为
        #      `run_tests.py` 把 `TESTS_DIR` 硬编码成 `ROOT/runtime/tests`。
        #      子进程的 `sys.path` 里没有真仓库 ⇒ 那个 `runtime` 不会遮蔽。
        cls.root = Path(cls.temporary.name) / "direct"
        cls.package_name = f"isaac_runner_probe_{os.getpid()}"
        cls.tests = cls.root / cls.package_name / "tests"
        cls.tests.mkdir(parents=True)
        (cls.tests / "__init__.py").write_text("")
        (cls.tests / "test_good.py").write_text(GOOD_MODULE)
        cls.broken = cls.tests / "test_broken.py"

        cls.cli_root = Path(cls.temporary.name) / "cli"
        cls.cli_tests = cls.cli_root / "runtime" / "tests"
        cls.cli_tests.mkdir(parents=True)
        (cls.cli_tests / "__init__.py").write_text("")
        (cls.cli_tests / "test_good.py").write_text(GOOD_MODULE)
        (cls.cli_root / "tools").mkdir()
        shutil.copy(ROOT / "tools" / "run_tests.py", cls.cli_root / "tools" / "run_tests.py")
        cls.cli_broken = cls.cli_tests / "test_broken.py"

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def discover(self):
        return discover_modules(self.tests, self.root)

    def run_runner(self) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(self.cli_root / "tools" / "run_tests.py")],
            cwd=str(self.cli_root), text=True, capture_output=True, timeout=120,
        )

    def test_good_module_is_discovered(self):
        parallel, exclusive = self.discover()
        self.assertIn(f"{self.package_name}.tests.test_good", parallel + exclusive)
        self.assertNotIn("unittest.loader", parallel + exclusive,
                         "列表里出现 `unittest.loader` = 有模块导入失败被吞掉了")

    def test_broken_module_fails_loudly(self):
        """★ 主判据：语法错的模块**必须**让发现阶段抛错，而不是静默少跑一个。"""
        self.broken.write_text(BROKEN_MODULE)
        try:
            with self.assertRaises(DiscoveryError) as caught:
                self.discover()
        finally:
            self.broken.unlink()
        message = str(caught.exception)
        self.assertIn("test_broken", message,
                      f"报错必须点名那个导不进来的模块（否则没法修）：{message}")

    def test_removing_the_broken_module_restores_discovery(self):
        """反证：删掉坏文件就恢复 —— 上面那条判据不是「只要目录里有东西就报错」。"""
        parallel, exclusive = self.discover()
        self.assertIn(f"{self.package_name}.tests.test_good", parallel + exclusive)

    def test_import_time_skip_is_not_a_failure(self):
        """导入期合法 `SkipTest` **不算**「导不进来」（它是 `unittest` 的正常机制）。

        为什么必须分开：`_FailedTest` 与"跳过"在发现器里走**不同**的类
        （失败 → `_FailedTest`；跳过 → 动态类 `ModuleSkipped`）。混为一谈会让
        「某个门禁在某个环境里合法跳过」变成「整套门禁跑不起来」。
        """
        skipped = self.tests / "test_skipped_env.py"
        skipped.write_text(SKIPPED_MODULE)
        try:
            parallel, exclusive = self.discover()
        finally:
            skipped.unlink()
        self.assertIn(f"{self.package_name}.tests.test_good", parallel + exclusive)

    def test_runner_reports_exit_code_two_when_a_module_cannot_be_imported(self):
        """端到端：坏模块在场 ⇒ 真跑一遍运行器，退出码必须是 **2**（曾经实测是 0）。"""
        self.cli_broken.write_text(BROKEN_MODULE)
        try:
            result = self.run_runner()
        finally:
            self.cli_broken.unlink()
        self.assertEqual(
            result.returncode, 2,
            "坏门禁在场时运行器没判错（退出码 "
            f"{result.returncode}）—— 那正是「静默少跑一个门禁」：\n"
            + (result.stdout or "") + (result.stderr or ""))

    def test_runner_is_green_and_really_runs_the_module_when_nothing_is_broken(self):
        """反证（同一套端到端）：没有坏模块时退出码 0、且那条好模块确实被跑了。

        判 "确实被跑了" 看输出里的模块名 —— 只看退出码是不够的（"0 个模块"也是 0）。
        """
        result = self.run_runner()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("runtime.tests.test_good", result.stdout,
                      "运行器的输出里应当列出它跑了哪个模块（否则无法区分「跑了」与「一个都没跑」）")


if __name__ == "__main__":
    unittest.main()