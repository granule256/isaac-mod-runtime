"""门禁：回调环境面台账（`tools/callback_surface.json`）。

## 为什么要有它

「模组太多没法一个个测」的正解是**测环境**。回调是模组接收一切事件的唯一通道：
我们**没派发**的回调 ⇒ 注册它的模组**静默不工作**（不报错、不崩）。2026-09-17 的套装 `(0/3)`
就属于「事件没送到」这一类。

所以这份台账要满足三件事：

1. **条数不许丢**：必须与 PC 文档快照（`ModCallbacks.md`）解析出的条数一致 —— 少了说明
   解析坏了、或有人删了行；
2. **口径合法**：每条 `status` 必须是登记过的取值，且必须有 `note`（"为什么归到这一类"）；
3. **★ `unknown` 不许涨**：这是「还没查」的欠账，只能降不能升。允许降（分类推进），
   不允许悄悄涨（新增条目没分类）。要涨必须在提交信息里说明理由，并同时改这个上限。

它不判"派发得够不够多"（那是进度，不是错误）—— 只判"账有没有做假/腐烂"。
"""

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SURFACE = ROOT / "tools" / "callback_surface.json"
DESCRIPTOR = ROOT / "runtime" / "src" / "domain" / "callback" / "callback_descriptor.hpp"
MOD_API = ROOT / "runtime" / "src" / "interfaces" / "lua" / "mod_api.cpp"

STATUSES = {"dispatched", "hookable", "needs_hook", "platform", "unknown"}
#: 「还没查」的条数上限：**只能降不能升**（2026-09-17 首次登记 = 42）。
UNKNOWN_BUDGET = 42


def pc_entries() -> list[str]:
    """PC 侧回调名单 —— 读**台账里的快照**，不读真值源文档。

    真值源（`analysis/isaacdocs-snapshot/…/ModCallbacks.md`）在 `.gitignore` 的 `analysis/` 下、
    **不进 git** ⇒ 而本套件会被 `test_game_file_reader_stage10` 用 `git ls-files` 复制到临时目录里跑，
    那时真值源不存在。所以门禁只认快照（由 `tools/callback_surface.py` 生成时写入）。
    """
    surface = json.loads(SURFACE.read_text(encoding="utf-8"))
    return [entry["name"] for entry in surface.get("pc_entries_snapshot", [])]


class CallbackSurfaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.surface = json.loads(SURFACE.read_text(encoding="utf-8"))
        cls.rows = cls.surface["rows"]

    def test_every_pc_callback_is_in_the_ledger(self):
        """PC 表里的每条回调都必须出现在台账里（不许丢条）。"""
        snapshot = pc_entries()
        self.assertEqual(len(snapshot), 74, f"名单快照条数不对：{len(snapshot)}（应为 74）")
        missing = sorted(set(snapshot) - set(self.rows))
        self.assertEqual(missing, [], f"这些 PC 回调没进台账：{missing[:8]}")

    def test_statuses_are_known_and_justified(self):
        for name, row in self.rows.items():
            with self.subTest(callback=name):
                self.assertIn(row["status"], STATUSES)
                # `unknown` 的"理由"就是"还没查"，不强制写；其余分类必须写清依据。
                self.assertTrue(
                    row.get("note") or row["status"] in ("dispatched", "unknown"),
                    f"{name} 归到 {row['status']} 却没写理由")

    def test_dispatched_rows_exist_in_the_code(self):
        """标 `dispatched` 的必须在 `callback_descriptor.hpp` 里真有对应常量。"""
        text = DESCRIPTOR.read_text(encoding="utf-8")
        for name, row in self.rows.items():
            if row["status"] != "dispatched":
                continue
            with self.subTest(callback=name):
                self.assertRegex(text, r"kCallback\w+ = " + str(row["id"]) + r";",
                                 f"{name}（id={row['id']}）标了 dispatched，代码里却没有这个值")

    def test_dispatched_rows_have_a_dispatch_site(self):
        """★ 标 `dispatched` 的必须在 `HasDispatchSite()` 名单里 —— 与设备侧同一真值源。

        为什么加这一条（2026-09-18）：`tools/callback_surface.py` 原来把"有常量"当成"已派发"，
        于是 `MC_INPUT_ACTION`(13) 被算成已派发，而它**没有派发点**（名单里刻意不含它）。
        后果不是崩溃，是**进度口径比真机事实多一条**，而这份台账正是回调面覆盖率的唯一来源。
        工具已改成按名单算；这条门禁把它钉住，免得下次换个人写又漂回去。
        """
        text = MOD_API.read_text(encoding="utf-8")
        start = text.index("bool HasDispatchSite(")
        body = text[start:text.index("}", start)]
        wired = set(re.findall(r"id\s*==\s*kCallback([A-Za-z0-9_]+)", body))
        self.assertTrue(wired, "`HasDispatchSite` 名单没解析到 —— 门禁失去意义")
        for name, row in self.rows.items():
            if row["status"] != "dispatched":
                continue
            with self.subTest(callback=name):
                expected = name.removeprefix("MC_").title().replace("_", "")
                self.assertIn(
                    expected, wired,
                    f"{name} 标着 dispatched，但 `HasDispatchSite` 名单里没有 kCallback{expected}"
                    f" —— 台账的覆盖率会比真机事实多一条")

    def test_unknown_budget_does_not_grow(self):
        """★ `unknown` 是欠账：只能降不能升。"""
        unknown = sum(1 for row in self.rows.values() if row["status"] == "unknown")
        self.assertLessEqual(
            unknown, UNKNOWN_BUDGET,
            f"未分类（unknown）从 {UNKNOWN_BUDGET} 涨到了 {unknown} —— "
            f"新增条目必须同时给出分类，不能悄悄堆成欠账",
        )

    def test_progress_is_reported(self):
        """只报进度、不判红：回调面的覆盖率一眼可见。"""
        from collections import Counter
        counts = Counter(row["status"] for row in self.rows.values())
        total = len(self.rows)
        print(f"[进度] 回调环境面 {total} 条："
              + "、".join(f"{k} {v}" for k, v in sorted(counts.items(), key=lambda i: -i[1]))
              + f"（已派发覆盖率 {100 * counts.get('dispatched', 0) // max(1, total)}%）")
