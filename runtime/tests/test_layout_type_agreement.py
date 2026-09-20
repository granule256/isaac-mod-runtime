"""门禁：布局表核对（第一半）—— 草稿声明的宽度/浮点 vs 我们实际的读法。

## 为什么要有它

`tools/layout_tables/drafts/*.json` 有 93 条字段偏移草稿（`confidence=candidate`）。升格成
`confirmed` 需要人工确认**语义**（那是第二半，还没做）；但在那之前有一半是机器能核的：
我们自己的读取代码也带类型（字段表 / `FieldApiRow` / `ReadEngine` 的局部变量声明），
两边对不上就是真 bug 候选（最典型：当成 `u32` 读、实际是 `float` —— 不崩、只是数字莫名其妙）。

这条门禁钉三件事：

1. **核对必须真的在核对**：能比对的条数不许掉（93 条草稿里我们真的会读的有 35 条，
   其余 58 条还没暴露成接口 —— 这个数掉下来说明读取点被删了或正则失效了）；
2. **判红必须有人工结论**：`we-read-wider`（我们读得比镜像里见过的任何访问都宽）一律要在
   `tools/layout_type_agreement.json` 里写明"看过了、结论是什么、依据是什么"；
3. **台账本身要合格**：每条都要有 `verdict` / `why` / `evidence` 三样，引用的常量必须真的在草稿里。

★ 一条经验（已写进工具文档与台账）：**草稿证据是按偏移全局搜的、不看基类型** ——
同一个偏移在别的结构体上被按 1 字节访问，并不说明我们的字段就是 1 字节。
2026-09-17 唯一那条判红就是这么来的（`Level+0x04`），查过 `Level::SetStage` 的
`stp w21, w20, [x19]` 之后确认**我们按 u32 读是对的**。
"""

import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools" / "layout_type_agreement.py"
LEDGER = ROOT / "tools" / "layout_type_agreement.json"
DRAFT_DIR = ROOT / "tools" / "layout_tables" / "drafts"


def run_tool() -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(TOOL)], capture_output=True, text=True, cwd=ROOT)


class LayoutTypeAgreementTests(unittest.TestCase):
    def test_drafts_still_exist(self):
        drafts = sorted(DRAFT_DIR.glob("*.json"))
        self.assertTrue(drafts, "布局表草稿不见了（tools/layout_tables/drafts/）")
        total = 0
        for path in drafts:
            data = json.loads(path.read_text(encoding="utf-8"))
            total += len(data.get("rows") or data.get("fields") or [])
        self.assertGreaterEqual(total, 93, f"草稿条数掉了：{total}")

    def test_no_untriaged_findings(self):
        """判红项必须都有人工结论 —— 这正是"机器能核的那半"的出口。"""
        result = run_tool()
        self.assertEqual(result.returncode, 0,
                         "布局表核对发现了未分诊的问题：\n" + result.stdout + result.stderr)
        self.assertIn("we-read-wider", result.stdout)

    def test_comparison_coverage_does_not_regress(self):
        """能比对的条数不许掉：掉下来说明读取点被删了、或提取正则失效了。"""
        result = run_tool()
        self.assertIn("我们真的会读它的", result.stdout)
        compared = int(result.stdout.split("我们真的会读它的 ")[1].split(" 条")[0])
        self.assertGreaterEqual(compared, 35,
                                f"能比对的条数掉了：{compared}（提取正则或读取点变了？）")

    def test_ledger_rows_are_well_formed(self):
        self.assertTrue(LEDGER.is_file(), "缺少 tools/layout_type_agreement.json（人工分诊台账）")
        data = json.loads(LEDGER.read_text(encoding="utf-8"))
        names = set()
        for path in DRAFT_DIR.glob("*.json"):
            for row in json.loads(path.read_text(encoding="utf-8")).get("rows", []):
                names.add(row["name"])
        for constant, row in data["rows"].items():
            with self.subTest(constant=constant):
                self.assertIn(constant, names, "台账里的常量不在任何草稿里")
                for key in ("verdict", "why", "evidence"):
                    self.assertTrue(row.get(key), f"{constant} 缺少 {key}")
                self.assertTrue(row["evidence"], f"{constant} 必须给出依据")


if __name__ == "__main__":
    unittest.main()
