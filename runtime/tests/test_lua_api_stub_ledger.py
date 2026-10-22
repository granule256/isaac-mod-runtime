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
#:
#: ★ 2026-09-25（批次 127）**11 → 13**：`Isaac:WorldToScreen` / `WorldToRenderPosition` 进表。
#: 它们**不是新增的桩**，而是**一直就是桩、只是没被认出来** —— `isaac_api.cpp` 的 `enum class Stub`
#: 里明明有这两条、注释还写着"与台账双向一致"，但它们把桩逻辑共享在具名助手 `WorldToIdentity` 里，
#: 旧判据只看处理器自己的正文 ⇒ 判成真实现。判据补了"一层委托"与 `Stub::` 标记（见
#: `tools/lua_api_stub_report.py` 文件头）之后，台账与源码才真的对上了。
#: ⇒ 这个数字涨的原因是"**看见了两条原本看不见的**"，不是"新写了假实现"。
#:
#: ★★ 2026-09-28（审查第 3 遍，批次 174）**13 → 24**：`tools/lua_api_stub_report.py` 的
#: `STUB_MARKERS` 补了 `lua_pushboolean(state, 0/1)` 与 `lua_pushinteger(state, 0)` 两类
#: **直接压常量**的写法。起因是审查 Lua 接口面时把"我们实现的接口"与引擎符号表对账，
#: 发现 7 条"引擎里**有同名成员函数**、我们却恒返回假值"的桩 —— 其中 3 条
#: （`EntityPlayer:HasPlayerForm` / `CanPickRedHearts` / `SFXManager:IsPlaying`）
#: **根本没进台账**，因为它们是恒假布尔而不是 `PushZero(`。
#: 新增的 11 条**全是"一直就是桩、只是没被认出来"**（逐条已核实，见各条 `note`），
#: 不是新写的假实现 —— 与 2026-09-25 那次 11 → 13 同一性质。
#: 为什么**不收** `lua_pushnil(state)`："返回 nil" 常常是正确的语义（单人局的 `GetOtherTwin`），
#: 收进来会把真实现判成桩（实测多认 6 条）⇒ 宁可漏、不可误。
#:
#: ★★ 2026-09-28（批次 177）**24 → 19 —— 第一次往下降**：批次 174 查出的 5 条
#: "引擎里有同名成员函数、我们却恒返回假值"的桩**已经还清**（从手写假桩改成引擎方法数据行）：
#: `EntityPlayer:GetPill` / `GetCard` / `GetZodiacEffect` / `HasPlayerForm` / `CanPickRedHearts`。
#: 这 5 条**已从台账删除**（不是"留着但标已修"—— 本门禁的设计就是"修好了必须销账"，
#: `test_ledger_matches_the_source_both_ways` 的双向判据会红）。
#: ★ 同一批里 `EntityPlayer:GetGlyphOfBalanceDrop`（`0x0E010042`）与 `SFXManager:IsPlaying`
#:   **当时都留在台账里**（理由逐条写在各自的 `note`）：前者引擎那个函数是
#:   `void(this, uint&, uint&)`（**两个引用出参**）、而唯一的已知调用方 EID 要的是**表**
#:   （`eid_repentogon.lua:265` 的 `dropIDTable[1]`），Lua 侧形状没有 PC 文档可对齐；
#:   后者缺"引擎音效单例怎么拿"（`SoundEffects` 没有全局符号，得从 `Manager` 里翻）⇒
#:   两条都要先把前置取证做掉，不能凭猜实现。
#:
#: **19 → 18（2026-09-28，批次 184）**：上面两条里的**前者做掉了** ——
#: `EntityPlayer:GetGlyphOfBalanceDrop` 新增了形状 `EngineCallShape::Ref2U32Pair`
#: （两个"入出参" + 返回一张两元表），手写"恒 0"桩删除 ⇒ 销账。
#: `SFXManager:IsPlaying` **仍留在台账里**（仍然缺"音效单例怎么拿"这一条前置取证），
#: 它的 `note` 里写着缺什么 —— 按本门禁的设计，**做不了就留着并写清缺什么，不许悄悄销账**。
#:
#: **18 → 17（2026-09-28，批次 185）**：上面那两条里的**后者也做掉了** ——
#: `SFXManager:IsPlaying` 改成真调引擎（`SoundEffects::IsPlaying` @ `0x4A38AC`）。
#: 补上了「音效单例怎么拿」：`Manager + 0x364A8`（反汇编取证：`Manager::PlaySound` 里
#: `add x0, this, #0x364a8` 之后尾调用 import 桩 `SoundEffects::Play`）⇒ 销账。
#: ⇒ 至此批次 177 留下的 **2 条靶子全部还清**（另一条 `GetGlyphOfBalanceDrop` 在批次 184）。
#:
#: （台账在本批之前已经是 **16 条** —— 那一步的来历见当时的改动日志；本批只负责下面这次下降。）
#:
#: ★★ **16 → 14（2026-09-29，批次 195）**：两条**恒值桩**改成真读数 ⇒ 销账 ——
#:   * `EntityPlayer:HasGoldenBomb`：改成**字段数据行**（读 `Entity_Player + 0x16D9` 一个字节；
#:     取值锚点 = 引擎自己的一对同名函数 `AddGoldenBomb @ 0x2FC3F0` / `RemoveGoldenBomb @ 0x2FC490`）；
#:   * `Game:GetVictoryLap`：改成字段直读（`Game + 0x26FD50`；写它的就是 `Game::NextVictoryLap`，
#:     另有五个独立读者）。
#:   两条的偏移与逐条指令证据抄在 `runtime_constants.hpp`，消费者视角判据在
#:   `runtime/tests/test_lua_entity_rng_and_fields.py`；它们同时被加进下面的
#:   `FIXED_AND_MUST_STAY_FIXED`（修好了就不许回退成桩）。
#:   ⚠️ 与批次 177 同一句口径：**还没上真机验收** ⇒ 只是"不再是假值"，不是"值已验真"。
#: ★ 2026-09-29（批次 195）**14 → 3**：九条"什么都不读、直接编一个值"的处理器改成**真读数**
#: （全部是这一批新取证的偏移/入口），它们**不再是什么都不读的桩** ⇒ 必须销账：
#:   * `Isaac:WorldToScreen` / `WorldToRenderPosition`：真调引擎 `GetRenderPosition(pos, true)`
#:     （两条只差"要不要再加 `Room[0x1938] + Game[0x24F9B0]`"）；同一批还新增了 `Isaac.ScreenToWorld`；
#:   * `Input:IsButtonPressed` / `IsButtonTriggered`：真调 `KAGE::Input::ManagerBase` 的
#:     `0x4F9504`（键盘码仍一律 false —— 平台固有，登记在偏离台账）；
#:   * `ItemConfig:HasTags` / `ItemConfig_Item:HasTags`：tags 位掩码确证在 `Item + 0xC0`（u64/33 位），
#:     口径 = 引擎自己三处同形的"任一命中"；
#:   * `EntityPlayer:GetHearts` / `GetPoopMana` / `GetPoopSpell` / `GetModelingClayEffect` /
#:     `GetPlayerFormCounter`：五个字段直读（`+0x16BC` / `+0x269C` / `+0x26A0` / `+0x2730` / `+0x1C54`）。
#: ⚠️ 与批次 177 同一句口径：**这些新实现还没上真机验收** —— 只是"不再是假值"，不是"值已验真"。
# ★ 2026-10-06（批次 381）：`Input:IsButtonTriggered` 不再被误判成桩 ——
#   边沿改成"帧上采样 + 纯读"之后，处理器正文里不再直接碰引擎，而 `REAL_MARKERS` 当时
#   只认"碰引擎 / 碰持久化层 / 碰编译进去的静态表 / 走通用跳板"这几种来源 ⇒ 漏了
#   "**读输入边沿表**"这一种（那张表每帧由采样器读引擎设备对象填出来，见 `input_edge.hpp`）。
#   补进 `REAL_MARKERS` 后它判回 `real`。**条数不变（仍是 3）** —— 它本来就**不在**台账里
#   （台账里那 3 条是另外三条真桩），`--write` 也照旧写 3 条；这次是**判据补全**，
#   不是新增或删除了桩（与批次 174 / 207 / 311 同一性质）。
STUB_BUDGET = 3

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
    # 批次 192（2026-09-28）：`Input:IsMouseBtnPressed` 从"恒返回 false 的安全桩"改成**真实现**
    # —— 指针源接上了触摸屏（`runtime/src/interfaces/lua/touch_pointer.hpp`），
    # 语义由用户定为"手指在屏幕上 = 左键按下"。它**不再什么都不读**，所以必须销账。
    # ⚠️ 它与 `Input:GetMousePosition` 一起把两条偏离从 `platform` 改档成 `debt`
    #（见 `api_deviation.cpp` 的两条 `0x09010007`/`0x09010008`）。
    "Input:IsMouseBtnPressed",
    # 批次 195（2026-09-29）：两条"什么都不读、直接编一个值"的处理器改成**真读数** ——
    #   * `EntityPlayer:HasGoldenBomb`：字段数据行，读 `Entity_Player + 0x16D9`（取值锚点 =
    #     引擎自己的一对同名函数 `AddGoldenBomb` / `RemoveGoldenBomb`）；
    #   * `Game:GetVictoryLap`：字段直读 `Game + 0x26FD50`（写它的就是 `Game::NextVictoryLap`）。
    # 判据：`runtime/tests/test_lua_entity_rng_and_fields.py`（消费者视角：两个场景各读一次、
    # 逐值可核；`HasGoldenBomb` 还在 `runtime/tests/test_lua_entity_player.py` 的夹具里钉住）。
    "EntityPlayer:HasGoldenBomb",
    "Game:GetVictoryLap",
    # 批次 195（2026-09-29）：九条同上（逐条理由见 `STUB_BUDGET` 上面那段注释）。
    # ★ 对 `Input` 那两条特别记一笔：它们进过表的理由是"引擎里没有按按键号查询的入口"，
    #   **那条前提已被推翻**（入口在 `KAGE::Input::ManagerBase`，游戏自己就在用）——
    #   所以这次不是"把桩换个写法"，是把整条路接上了引擎。
    "Isaac:WorldToScreen",
    "Isaac:WorldToRenderPosition",
    "Input:IsButtonPressed",
    "Input:IsButtonTriggered",
    "ItemConfig:HasTags",
    "ItemConfig_Item:HasTags",
    "EntityPlayer:GetHearts",
    "EntityPlayer:GetPoopMana",
    "EntityPlayer:GetPoopSpell",
    "EntityPlayer:GetModelingClayEffect",
    "EntityPlayer:GetPlayerFormCounter",
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
