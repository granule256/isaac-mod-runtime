"""门禁：接口"安全桩"台账（`tools/lua_api_stub_ledger.json`）。

## 为什么要有它

`analysis/lua-api-inventory` 把 API 分类成 `implemented` 的口径**只判"命中 `api_catalog.cpp`"**
（见 `tools/build_lua_api_inventory.py` 的 `classify()`）—— **"有目录行"被当成了"已实现"**。
2026-09-18 就因此误判过：`EntityPlayer:GetNumKeys` / `GetNumBombs` / `GetSoulCharge` /
`GetBloodCharge` 四个是 `PushZero` 的**恒返回 0 假桩**，却被记成 `implemented`。
假读数不报错、不崩，模组拿它们做算术会得到错误结论（与"套装恒 `0/3`"同一类）。
**这与 09-18 下午修掉的"回调覆盖率多算一条"是同一族问题：用间接特征代替真值源。**

所以补这一维，并且按本项目既有形状钉住四件事：

1. **台账不许腐烂**：源码里认出的桩集合 == 台账里的集合（**双向**：多了说明没登记，
   少了说明"已经修好但没销账"——销账这一步是刻意的，逼着人把"修好了"这件事写下来）；
2. **条数只能降不能升**：`STUB_BUDGET` 是上限，涨了必须显式改这个数字（"新增的桩"要被看见）；
3. **每条必须写理由**（`note`）：至少说清"为什么它是桩、修它要先取证什么"，
   否则下一轮的人还得重新查一遍；
4. **钉住已经修好的那几条**：`GetNumKeys` / `GetNumBombs` / `GetSoulCharge` / `GetBloodCharge`
   不许再回到桩集合里（回归断言；它们的真实现有反汇编证据与行为测试）。

它**不判**"桩该不该现在修"（那是排期，不是错误）。
"""

import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LEDGER = ROOT / "tools" / "lua_api_stub_ledger.json"
REPORT_TOOL = ROOT / "tools" / "lua_api_stub_report.py"

#: ★ 桩的条数**上限**：只能降不能升（2026-09-18 首次登记 = 15；批次 026 修掉四条 ⇒ 11）。
#: 要涨必须在提交信息里说明为什么新增一个"什么都不读的处理器"，并同时改这个数字。
STUB_BUDGET = 11

#: 已经修好的（2026-09-18，批次 018 及更早）：它们**不许**再出现在桩集合里。
FIXED_AND_MUST_STAY_FIXED = (
    "EntityPlayer:GetNumKeys",
    "EntityPlayer:GetNumBombs",
    "EntityPlayer:GetSoulCharge",
    "EntityPlayer:GetBloodCharge",
    "EntityPlayer:GetNumCoins",
    # 批次 026：四条"低成本安全桩"改成真实现（判据见各自实现处与 `runtime_constants.hpp`）。
    # `CountBosses` 走新取证的 boss 标记字节（`Entity + 0xCC9`）；
    # `LoadModData`/`SaveModData` 转到 `Mod:SaveData`/`LoadData` 那份共用核心；
    # `RenderScaledText` 复用 `Font:DrawString*` 这条绘制路径 + 运行时自己的默认字体。
    "Isaac:CountBosses",
    "Isaac:LoadModData",
    "Isaac:SaveModData",
    "Isaac:RenderScaledText",
)


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class LuaApiStubLedgerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ledger = json.loads(LEDGER.read_text(encoding="utf-8"))
        cls.rows = cls.ledger["rows"]
        cls.tool = load_module("lua_api_stub_report", REPORT_TOOL)
        # 从**源码**重算一遍（不读 `analysis/` 那种不进 git 的东西 —— 见问题记录里的那条原则）。
        cls.found = cls.tool.survey()

    def test_ledger_matches_the_source_both_ways(self):
        """多了 = 没登记；少了 = 修好了但没销账。两种都要红。"""
        on_disk = set(self.rows)
        in_source = set(self.found)
        self.assertEqual(
            in_source - on_disk, set(),
            f"源码里认出这些桩，台账里没有（跑 `python3 tools/lua_api_stub_report.py --write`）："
            f"{sorted(in_source - on_disk)}",
        )
        self.assertEqual(
            on_disk - in_source, set(),
            f"台账里有这些桩，但源码里已经不是了（修好之后要**销账**：重跑 --write）："
            f"{sorted(on_disk - in_source)}",
        )

    def test_every_stub_has_a_reason(self):
        """每条必须写清"为什么是桩、修它要先取证什么"。"""
        missing = sorted(key for key, row in self.rows.items() if not row.get("note"))
        self.assertEqual(missing, [], f"这些桩没写理由：{missing}")

    def test_the_stub_count_only_shrinks(self):
        self.assertLessEqual(
            len(self.rows), STUB_BUDGET,
            f"接口安全桩从 {STUB_BUDGET} 涨到 {len(self.rows)} —— "
            f"新增一个'什么都不读的处理器'要显式改 STUB_BUDGET 并说明理由",
        )

    def test_already_fixed_entries_never_come_back(self):
        """回归：这五条已经有反汇编证据 + 行为测试，不许退化成桩。"""
        for key in FIXED_AND_MUST_STAY_FIXED:
            with self.subTest(api=key):
                self.assertNotIn(
                    key, self.found,
                    f"{key} 是**真实现**（有取证与行为测试）；它现在又被判成桩了 —— "
                    f"要么实现退化了，要么判据（`tools/lua_api_stub_report.py` 的 REAL_MARKERS）"
                    f"漏了它用的那种读法",
                )

    def test_progress_is_reported(self):
        """只报进度、不判红：桩还剩多少、其中哪些标了"低成本可修"。"""
        cheap = sorted(key for key, row in self.rows.items()
                       if "低成本可修" in (row.get("note") or ""))
        print(f"[进度] 接口安全桩（有目录行但处理器什么都不读）：{len(self.rows)} 条"
              f"（上限 {STUB_BUDGET}）；其中标了『低成本可修』的 {len(cheap)} 条：{cheap}")


if __name__ == "__main__":
    unittest.main()
