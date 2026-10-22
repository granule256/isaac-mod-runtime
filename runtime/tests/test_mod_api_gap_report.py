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

★ 2026-09-29（批次 202）补上第三条轴：**注释不算代码**。原先工具"不做词法剥离"，于是注释里的
名字会被当成真调用 —— 实测到的那条是 EID `features/eid_api.lua:1004` 的一句文档注释
`---This is for modded characters, whose name is best found by doing EntityPlayer:GetName()`，
它被读成了"模组在 `EntityPlayer` 上调 `GetName`"。**危险的不是多报一条，是证据指错行**
（顺着证据行号读回去是一句话，不是代码）。所以下面加了两个负对照：
`COMMENT_ONLY_FIXTURE`（整份是注释 ⇒ 一条用法都不许有）与 `STRING_DASH_FIXTURE`
（字符串里的 `--` 不许被当成注释开头 —— 否则同一行后面的真调用会被**静默吃掉**）。

（分析用的 `analysis/lua-api-inventory/inventory.json` 是**生成物、不入 git**，
在 `git ls-files` 复制出来的工作区里不存在 ⇒ 那种环境下跳过本门禁，并说明原因。）
"""

import importlib.util
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
  Game():GetRoom():EmitBloodFromWalls(1, 1)  -- 链式 + 运行时没有这个方法
  -- ★ 这一行换过**四次**，每次都是因为"夹具里那个方法被实现掉了"：
  --   ① 原来是 `Game():ChangeRoom(1, 1)`，批次 050 实现 `Game:ChangeRoom` ⇒ 不再算缺口；
  --   ② 换成 `Game():StartRoomTransition(1, 1)`，批次 055 又把它实现掉了（GoodTrip 传送要用）；
  --   ③ 换成 `Game():GetLevel():GetStartingRoomIndex()`，**批次 106** 把它实现掉了
  --      （EID 的 `eid_holdmapdesc.lua:35` 每条回调都在调 ⇒ 不能一直缺着）
  --      ⇒ 换成仍然缺的 `Room:GetDecorationSeed`（属批次 028 记下的"6 条无引擎符号成员"之一）；
  --   ④ **批次 295（2026-10-03）把 `Room:GetDecorationSeed` 也实现掉了**（EID 的库存概况要用它），
  --      ⇒ 换成 `Entity:AddVelocity`（15 处）—— 它当时在"不要再接"清单里（真算法 + 多一个
  --      bool + 无符号），**以为不会被实现**；
  --   ⑤ **批次 346（2026-10-04）把 `Entity:AddVelocity` 也实现掉了**（推翻旧负结果后按 PC 算式
  --      复刻的纯算法处理器）⇒ 换成 `Room:EmitBloodFromWalls` —— 它是清单里**唯一有"做不到"
  --      定案**的一条（B 组：全镜像 `0x7108/0x710c` 零命中、两条独立证据都拿不到）⇒
  --      **没有可落地的实现路径**，这条判据因此能长期稳住。真要接它时按同一套办法再换一条。
  local w = Isaac.GetScreenPointScale()      -- 点号调用 + 运行时没有这个方法
  return t, w
end)
"""

#: 夹具里那个"点号调用 + 运行时没有"的例子**换过一次**（与上面链式那行同一类原因）：
#:   原来是 `Isaac.GetScreenWidth()`，**批次 207（2026-09-29）把它实现掉了**
#:   （MCM 的 `screenhelper.lua:55` 要用它摆界面）⇒ 不再算缺口。
#:   现在换成 `Isaac.GetScreenPointScale()` —— 同族（都是屏幕尺寸），仍然缺。
#:   ★ 换掉它时要连 `STRING_DASH_FIXTURE` 与两条断言一起换，否则那两条会静默变成空转。
_MISSING_DOT_CALL = "Isaac:GetScreenPointScale"

#: **负对照一：整份文件都是注释 ⇒ 报告里一条用法都不许有。**
#: 里面的名字都是真的 PC 方法（`GetPlayer` / `GetPlayerType` / `GetName` / `GetScreenWidth`），
#: 所以"没扫到"只可能来自"注释被剥掉了"，不可能来自"名字不认识"。
COMMENT_ONLY_FIXTURE = """-- 整份文件都是注释（批次 202 的负对照），下面每一条都不算调用：
-- local player = Isaac.GetPlayer(0)
-- player:GetPlayerType()
-- Game():GetRoom():AddVelocity(Vector(1, 0))
--[[
  EntityPlayer:GetName()
  Isaac.GetScreenWidth()
  item:IsAvailable()
]]
---@param player EntityPlayer
-- 上面那行是有意放的注解：注解本身也是注释，但它**不许**被当成"这个文件定义了 player"。
"""

#: **负对照二：字符串里的 `--` 不许被当成注释开头。**
#: ★ 这一条防的是**静默漏报**：`"a--b"` 里的 `--` 若被当成注释，会把这**一整行剩下的字符**都吃掉
#: —— 包括同一行后面那个真调用。本文件开头说过，漏报比误报危险得多。
STRING_DASH_FIXTURE = """local label = "a--b" local w = Isaac.GetScreenPointScale()
local quoted = "-- local x = 1" local p = Isaac.GetPlayer(0)
local escaped = 'it\\'s -- fine' local q = item["Quality"]
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
        """点号调用（表上的函数）必须进清单 —— 否则 `Isaac.GetScreenPointScale()` 这类缺口永远扫不到。"""
        report = self.run_tool()
        used = {row["api"]: row for row in report["used"]}
        self.assertIn("Isaac:GetPlayer", used, "点号调用没有进 used")
        self.assertTrue(used["Isaac:GetPlayer"]["in_runtime"])
        missing = {row["api"] for row in report["missing_in_runtime"]}
        self.assertIn(_MISSING_DOT_CALL, missing,
                      "点号形式的缺口没有被判成高置信缺失")

    def test_chained_calls_are_reported_without_guessing_the_owner(self) -> None:
        """链式调用要报出**候选 owner**（不猜是哪一家），而且已经实现的不能再算缺口。

        ★ 设计变更记**五次**（每次都是"夹具里那个方法被实现掉了"）：批次 050 把 `Game:ChangeRoom`
        实现掉 ⇒ 夹具换成 `StartRoomTransition`；批次 055 又把它实现掉（GoodTrip 传送要用）
        ⇒ 换成 `Level:GetStartingRoomIndex`；**批次 106** 又把它实现掉（EID 每条回调都在调）
        ⇒ 换成 `Room:GetDecorationSeed`；**批次 295** 又把它实现掉（第四次）⇒ 换成
        `Entity:AddVelocity`；**批次 346（2026-10-04）把 `Entity:AddVelocity` 也实现掉了**
        （推翻旧负结果后按 PC 算式复刻的纯算法）⇒ 换成 `Room:EmitBloodFromWalls`
        （B 组已定案「做不到」⇒ 没有可落地的实现路径，能长期稳住）。
        这条门禁要验的东西一次都没变：**接收者类型未知时列出全部候选 owner，不猜**。
        """
        report = self.run_tool()
        chained = report["chained_calls"]
        names = {row["name"] for row in chained["every_candidate_missing"]}
        self.assertIn("EmitBloodFromWalls", names)
        row = next(r for r in chained["every_candidate_missing"]
                   if r["name"] == "EmitBloodFromWalls")
        self.assertIn("Room", row["candidate_owners"])

    def test_the_mods_own_methods_never_show_up_as_gaps(self) -> None:
        report = self.run_tool()
        blob = json.dumps(report, ensure_ascii=False)
        self.assertNotIn("MyOwnHelper", blob,
                         "模组自建方法被当成游戏 API 了（会让每个模组都刷出一堆假缺口）")

    # ---------------------------------------------------------------- 注释不许算代码（批次 202）

    def run_tool_on_source(self, source: str) -> dict:
        """把一段 Lua 当成一整个模组跑一遍，返回报告（负对照用）。"""
        with tempfile.TemporaryDirectory() as directory:
            mod = Path(directory) / "fixture-mod"
            mod.mkdir()
            (mod / "main.lua").write_text(source, encoding="utf-8")
            report_path = Path(directory) / "report.json"
            result = subprocess.run(
                [sys.executable, str(TOOL), "--mod", str(mod), "--label", "fixture",
                 "--json", str(report_path)],
                cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            return json.loads(report_path.read_text(encoding="utf-8"))

    def test_comment_only_fixture_yields_no_usage_at_all(self) -> None:
        """整份注释的模组 ⇒ 一条用法都不许有。

        这是"注释不算代码"的正面判据。里面的名字全是真 PC 方法，所以"没扫到"只可能来自
        注释被剥掉，不可能来自"名字不认识"。★ 别把这条删掉换成"少几条"的弱断言 ——
        弱断言在"剥注释整个没生效"时**照样绿**。
        """
        report = self.run_tool_on_source(COMMENT_ONLY_FIXTURE)
        self.assertEqual(report["used"], [], "注释里的调用被当成真调用收进 `used` 了")
        self.assertEqual(report["missing_in_runtime"], [], "注释里的缺口被当真缺口报出来了")
        self.assertEqual(report["chained_calls"]["rows"], [], "注释里的链式调用被收进来了")

    def test_a_double_dash_inside_a_string_is_not_a_comment(self) -> None:
        """字符串里的 `--` 不许被当成注释开头 —— 否则同一行后面的**真调用会被静默吃掉**。

        ★ 这条防的是漏报（比误报危险得多）：`"a--b"` 后面的 `Isaac.GetScreenPointScale()` 必须仍在。
        同时钉住"字符串本身**不许**被剥掉"——`item["Quality"]` 那个字段面形态靠它。
        """
        report = self.run_tool_on_source(STRING_DASH_FIXTURE)
        used = {row["api"] for row in report["used"]}
        missing = {row["api"] for row in report["missing_in_runtime"]}
        self.assertIn("Isaac:GetPlayer", used,
                      "字符串里的 `--` 被当成注释了：同一行后面的点号调用被吃掉")
        self.assertIn(_MISSING_DOT_CALL, missing,
                      "字符串里的 `--` 被当成注释了：同一行后面的缺口扫不出来（静默漏报）")
        fields = {row["name"] for row in report["field_surface"]["used"]}
        self.assertIn("Quality", fields,
                      "字符串字面量被剥掉了：字段面 `obj[\"Field\"]` 这条形态随之失效")


class LuaCommentStrippingTests(unittest.TestCase):
    """`strip_lua_comments()` 本身的单元测试 —— 它是上面那些结论的**地基**。

    为什么不只用合成模组做集成测试：等长性、转义、长括号这些性质**只有在字符级才看得见**，
    而它们一旦坏了就是"证据行号整体串位"或"整段代码被吃掉"这种远端症状，很难从报告倒推。
    """

    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("mod_api_gap_report", TOOL)
        cls.tool = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.tool)

    def assert_stripped(self, source: str, kept=(), dropped=()):
        """剥一遍：断言**等长/换行数不变**，且指定片段该留的留、该没的没。"""
        result = self.tool.strip_lua_comments(source)
        self.assertEqual(len(result), len(source), "剥注释改变了长度 ⇒ 行号与证据会整体串位")
        self.assertEqual(result.count("\n"), source.count("\n"), "剥注释改变了换行数")
        for needle in kept:
            self.assertIn(needle, result, f"{needle!r} 不该被剥掉")
        for needle in dropped:
            self.assertNotIn(needle, result, f"{needle!r} 应该被剥掉")

    def test_line_comments_are_stripped_but_code_is_untouched(self):
        self.assert_stripped(
            'local a = 1 -- room:GetFrameCount()\nlocal b = 2\n',
            kept=("local a = 1", "local b = 2"), dropped=("GetFrameCount",))

    def test_long_comments_are_stripped(self):
        self.assert_stripped('--[[\nIsaac.GetScreenWidth()\n]]\nlocal c = 3\n',
                             kept=("local c = 3",), dropped=("GetScreenWidth",))
        self.assert_stripped('--[==[ player:GetPlayerType() ]==]\nlocal d = 4\n',
                             kept=("local d = 4",), dropped=("GetPlayerType",))

    def test_an_unclosed_long_comment_eats_the_rest_of_the_file(self):
        """未闭合的长注释吃到文件尾 —— 宁可多剥，也不要留半截被当成代码。"""
        self.assert_stripped('local e = 5\n--[[ 没收口\nIsaac.GetPlayer(0)\n',
                             kept=("local e = 5",), dropped=("Isaac.GetPlayer",))

    def test_a_double_dash_inside_a_string_does_not_start_a_comment(self):
        """★ 字符串必须被"认出来并跳过"——否则 `--` 会把这一行剩下的代码全吃掉。"""
        self.assert_stripped('print("a--b") local c = Isaac.GetPlayer(0)\n',
                             kept=('print("a--b")', "Isaac.GetPlayer"))
        self.assert_stripped("local s = 'it\\'s --x' local f = Game():GetRoom()\n",
                             kept=("Game():GetRoom",))
        self.assert_stripped('print[[a--b]] local g = Game():GetRoom()\n',
                             kept=("[[a--b]]", "Game():GetRoom"))

    def test_string_literals_survive_because_the_field_surface_needs_them(self):
        """字符串**不许剥**：字段面 `obj["Field"]` 靠它（这是本批刻意保留的口径）。"""
        self.assert_stripped('local v = item["Quality"]\n', kept=('["Quality"]',))
        self.assert_stripped('print("EntityPlayer:GetName()")\n',
                             kept=("EntityPlayer:GetName",))

    def test_an_apostrophe_inside_a_comment_does_not_open_a_string(self):
        """注释里的撇号不许被当成字符串开头 —— 否则会把后面整份文件吃进"字符串里"。"""
        self.assert_stripped("-- don't\nlocal i = Isaac.GetPlayer(0)\n",
                             kept=("Isaac.GetPlayer",))

    def test_a_minus_sign_is_not_a_comment(self):
        self.assert_stripped('local h = a - -b\n', kept=("local h = a - -b",))


if __name__ == "__main__":
    unittest.main()
