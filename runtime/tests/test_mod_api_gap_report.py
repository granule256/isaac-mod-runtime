"""门禁：模组缺口扫描这条流水线本身要能自测（`tools/mod_api_gap_report.py`）。

## 为什么要有它

接新模组（GoodTrip 等）时，第一步永远是"把这个模组用到的 API 与我们运行时的状态交叉核对"。
如果**工具本身**漏掉某个调用形态，缺口表就是**假绿**（"没有缺口"其实是"没扫到"），
而后果要等真机上模组功能静默消失才发现 —— 这正是 `Room:GetFrameCount` 与
`Isaac.GetScreenWidth` 两次踩过的坑（前者是链式调用没扫、后者是点号调用没扫）。

所以这里用**一个合成夹具模组**把三条路都钉住：

* `Owner:Name(`（冒号，owner 确定）；
* `Owner.Name(`（点号，owner 确定；2026-09-19 补）；
* `a:b():c(`（链式，owner 未知，只报方法名 + 候选）。

另外钉住两件事：**模组自己定义的方法不能进缺口表**（否则每个模组都会刷出一堆假缺口），
以及报告里要带 `label`（工具已泛化为"任意模组"，不再写死 EID）。

（分析用的 `analysis/lua-api-inventory/inventory.json` 是**生成物、不入 git**，
在 `git ls-files` 复制出来的工作区里不存在 ⇒ 那种环境下跳过本门禁，并说明原因。）
"""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools" / "mod_api_gap_report.py"
API_INVENTORY = ROOT / "analysis" / "lua-api-inventory" / "inventory.json"
CONTRACT_LIST = ROOT / "docs" / "PC-Lua-API-对照清单.md"

FIXTURE = """-- 合成夹具模组：只用来验证缺口扫描这条流水线本身（不是真模组）
local mod = RegisterMod("FixtureMod", 1)
local function MyOwnHelper(a) return a end   -- 模组自建方法：不该被当成游戏 API

mod:AddCallback(ModCallbacks.MC_POST_RENDER, function()
  local player = Isaac.GetPlayer(0)          -- 点号调用（owner 确定）
  local room = Game():GetRoom()              -- 链式调用（owner 未知）
  local gridIndex = room:GetGridIndex(player.Position)   -- 冒号调用（owner 确定）
  MyOwnHelper(gridIndex)
  local t = player:GetPlayerType()           -- 冒号调用（owner 确定）
  Game():GetRoom():GetDecorationSeed()       -- 链式 + 运行时没有这个方法
  -- ★ 这一行换过**三次**，每次都是因为"夹具里那个方法被实现掉了"：
  --   ① 原来是 `Game():ChangeRoom(1, 1)`，批次 050 实现 `Game:ChangeRoom` ⇒ 不再算缺口；
  --   ② 换成 `Game():StartRoomTransition(1, 1)`，批次 055 又把它实现掉了（GoodTrip 传送要用）；
  --   ③ 换成 `Game():GetLevel():GetStartingRoomIndex()`，**批次 106** 把它实现掉了
  --      （EID 的 `eid_holdmapdesc.lua:35` 每条回调都在调 ⇒ 不能一直缺着）
  --      ⇒ 现在换成仍然缺的 `Room:GetDecorationSeed`（属批次 028 记下的"6 条无引擎符号成员"之一）。
  --      真机就报过它；它在引擎里没有访问器符号，要还原 `Level` 布局才能做，属真欠账）。
  local w = Isaac.GetScreenWidth()           -- 点号调用 + 运行时没有这个方法
  return t, w
end)
"""


class ModApiGapReportTests(unittest.TestCase):
    def setUp(self) -> None:
        if not API_INVENTORY.is_file():
            self.skipTest("analysis/lua-api-inventory/inventory.json 不存在"
                          "（生成物、不入 git ⇒ 在复制出来的工作区里跳过）")
        if not CONTRACT_LIST.is_file():
            self.skipTest(f"{CONTRACT_LIST.relative_to(ROOT)} 不存在")
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.mod = Path(self.tmp.name) / "fixture-mod"
        self.mod.mkdir()
        (self.mod / "main.lua").write_text(FIXTURE, encoding="utf-8")
        self.report_path = Path(self.tmp.name) / "fixture-report.json"

    def run_tool(self) -> dict:
        result = subprocess.run(
            [sys.executable, str(TOOL), "--mod", str(self.mod), "--label", "fixture",
             "--json", str(self.report_path)],
            cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(self.report_path.is_file(), "工具没有写出报告")
        return json.loads(self.report_path.read_text(encoding="utf-8"))

    def test_the_report_carries_the_label_of_the_scanned_mod(self) -> None:
        report = self.run_tool()
        self.assertEqual(report["label"], "fixture")
        self.assertIn("fixture-mod", report["mod"])

    def test_colon_calls_are_matched_with_a_known_owner(self) -> None:
        report = self.run_tool()
        used = {row["api"]: row for row in report["used"]}
        self.assertIn("Room:GetGridIndex", used)
        self.assertIn("EntityPlayer:GetPlayerType", used)
        self.assertTrue(used["EntityPlayer:GetPlayerType"]["in_runtime"])

    def test_dot_calls_are_matched_too(self) -> None:
        """点号调用（表上的函数）必须进清单 —— 否则 `Isaac.GetScreenWidth()` 这类缺口永远扫不到。"""
        report = self.run_tool()
        used = {row["api"]: row for row in report["used"]}
        self.assertIn("Isaac:GetPlayer", used, "点号调用没有进 used")
        self.assertTrue(used["Isaac:GetPlayer"]["in_runtime"])
        missing = {row["api"] for row in report["missing_in_runtime"]}
        self.assertIn("Isaac:GetScreenWidth", missing,
                      "点号形式的缺口没有被判成高置信缺失")

    def test_chained_calls_are_reported_without_guessing_the_owner(self) -> None:
        """链式调用要报出**候选 owner**（不猜是哪一家），而且已经实现的不能再算缺口。

        ★ 设计变更记**三次**（每次都是"夹具里那个方法被实现掉了"）：批次 050 把 `Game:ChangeRoom`
        实现掉 ⇒ 夹具换成 `StartRoomTransition`；批次 055 又把它实现掉（GoodTrip 传送要用）
        ⇒ 换成 `Level:GetStartingRoomIndex`；**批次 106** 又把它实现掉（EID 每条回调都在调）
        ⇒ 现在换成仍然缺的 `Room:GetDecorationSeed`。这条门禁要验的东西一次都没变：
        **接收者类型未知时列出全部候选 owner，不猜**。
        """
        report = self.run_tool()
        chained = report["chained_calls"]
        names = {row["name"] for row in chained["every_candidate_missing"]}
        self.assertIn("GetDecorationSeed", names)
        row = next(r for r in chained["every_candidate_missing"]
                   if r["name"] == "GetDecorationSeed")
        self.assertIn("Room", row["candidate_owners"])

    def test_the_mods_own_methods_never_show_up_as_gaps(self) -> None:
        report = self.run_tool()
        blob = json.dumps(report, ensure_ascii=False)
        self.assertNotIn("MyOwnHelper", blob,
                         "模组自建方法被当成游戏 API 了（会让每个模组都刷出一堆假缺口）")


if __name__ == "__main__":
    unittest.main()
