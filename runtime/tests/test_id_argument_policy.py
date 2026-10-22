"""门禁：`EntityPlayer` 那一族"参数是枚举 id"的成员**不许再钉取值范围**。

## 为什么要有它

2026-09-18 真机，可调用性探针（批次 033）第一次上机就撞出一条真缺陷：

```
RNG(call-error: EntityPlayer:GetCollectibleRNG accepts one slot in [0, 0])
```

探针按 PC 文档传的是**收藏品 id**（1 = 洋葱），而我们把这个参数当**槽位**卡在 `[0, 0]`。
PC 文档快照里这一族的签名都是**枚举 id**（`analysis/isaacdocs-snapshot/docs/EntityPlayer.md`）：

* `RNG GetCollectibleRNG(CollectibleType ID)`（:903）
* `RNG GetTrinketRNG(TrinketType TrinketID)`（:1331）
* `RNG GetCardRNG(Card ID)`（:888）
* `RNG GetPillRNG(PillEffect ID)`（:1191）
* `bool HasTrinket(TrinketType TrinketID)`、`bool HasPlayerForm(PlayerForm)`、
  `int GetPlayerFormCounter(PlayerForm)`

**为什么这条错特别值钱**：id 空间里有上千个值（饰品、形态），模组传合法 id 就会抛 Lua 错误，
而回调里抛错会被派发器**静默摘掉整条回调** —— 现象是"那个模组的某块功能整个不工作、
屏幕上什么都没有、游戏也不崩"。这与 2026-09-18 那条药丸（`Sprite:SetFrame` 只收整数子类型
⇒ EID 的描述整条不显示）是同一类：**我们比 PC 严**。

**规则**：参数是 id（或 PC 上确实是槽位但不"越界即错"）时，只钉"必须是一个整数"
（那才是 Mod 作者的笔误），**不钉取值范围**；越界在 PC 上是"没有"（nil / 0 / false）。

（与项目其它源码门禁同一形态：不做 C++ 解析，只做受控的文本提取。）
"""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ISAAC_API = ROOT / "runtime" / "src" / "interfaces" / "lua" / "isaac_api.cpp"


def code_only(text: str) -> str:
    """去掉注释行：注释里会**引用历史错误文本**（"accepts one slot in [0, 1]" 就是证据链的一部分），
    统计"代码里还有没有范围校验"时不能把它算进去。"""
    return "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("//"))

#: 参数是**枚举 id** 的六个成员：必须用 `EntityPlayerProbeIdArgument` 校验。
#: ★ 批次 177（2026-09-28）：`EntityPlayer:HasPlayerForm` 从这份名单里**移出** —— 它不再是
#: 手写处理器，改走引擎方法数据行（`kEntityPlayerEngineRows` 的 `0x0E01004B`，
#: `EngineCallShape::Bool1`）。"只收一个整数、不做范围校验"这条口径由那一行数据表达。
ID_ARGUMENT_MEMBERS = (
    "EntityPlayer:GetCollectibleRNG",
    "EntityPlayer:GetTrinketRNG",
    "EntityPlayer:GetCardRNG",
    "EntityPlayer:GetPillRNG",
    "EntityPlayer:HasTrinket",
    "EntityPlayer:GetPlayerFormCounter",
)

#: 参数在 PC 上确实是槽位、但"越界不是错误"的两个成员。
#: ★ 批次 177（2026-09-28）：这两条**已经不是手写处理器**了 —— 改走引擎方法数据行
#: （`0x0E010030`/`0x0E010031`，`EngineCallShape::Int1`）。"只钉整数、不钉范围"由
#: `IntArgumentGuard::None` + `argumentCount = 1` 表达；下面那条测试因此改成查**数据行**，
#: 而不是查处理器正文里的助手调用。
POCKET_SLOT_MEMBERS = (
    "EntityPlayer:GetCard",
    "EntityPlayer:GetPill",
)

#: 批次 177：这 5 条从"手写假桩"换成了引擎方法数据行（= 审查第 3 遍点名的
#: "引擎里有同名成员函数、我们却恒返回假值"那一类）。每一条都要**同时**满足：
#:   ① 它的 id 出现在 `kEntityPlayerEngineRows` 里（真的接上引擎了）；
#:   ② 它的名字**不再**出现在手写处理器绑定表 `kEntityPlayerHandlers` 里（旧的假桩真的删了）。
#: 只钉 ① 会漏掉"数据行加了、旧处理器还留着"（那样两条路都在、谁生效取决于查表顺序）。
ENGINE_ROW_MEMBERS = (
    ("EntityPlayer:GetPill", "0x0E010030", "Int1"),
    ("EntityPlayer:GetCard", "0x0E010031", "Int1"),
    ("EntityPlayer:GetZodiacEffect", "0x0E010040", "Int0"),
    ("EntityPlayer:HasPlayerForm", "0x0E01004B", "Bool1"),
    ("EntityPlayer:CanPickRedHearts", "0x0E01004C", "Bool0"),
)


class IdArgumentPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = ISAAC_API.read_text(encoding="utf-8")

    def test_every_id_member_uses_the_integer_only_helper(self) -> None:
        for member in ID_ARGUMENT_MEMBERS:
            with self.subTest(member=member):
                # ★ 批次 130（2026-09-25）：只钉到引号处、**不含闭合括号** —— `HasTrinket` 现在多传
                # 一个 `allowTrailingBoolean`（PC 的 `IgnoreModifiers` 可省），"用哪个助手"这条判据
                # 不该因此变红。谁把某个成员换成别的助手（例如带范围校验的那个），这里仍然会红。
                self.assertIn(f'EntityPlayerProbeIdArgument(state, "{member}"', self.text)

    def test_pc_optional_parameters_are_accepted(self) -> None:
        """★ 批次 130（2026-09-25）：**PC 的可选参数不许被我们判成错误**。

        查 026 那批时发现两处旧实现比 PC 严，后果都不是"答错"而是"抛 Lua 错误 ⇒
        派发器静默摘掉整条回调"（模组某块功能整个不工作、画面正常）：

          * `EntityPlayer:HasTrinket(Type, IgnoreModifiers = false)` —— 第二个参数可省。
            证据（不是推测）：语料里的 `analysis/mod-corpus/TBOI_Better-Voiding/main.lua:508`
            与 `:762` 写的就是 `playerEntity:HasTrinket(TrinketType.TRINKET_YOUR_SOUL, false)`；
          * `EntityPlayer:GetPoopSpell(int Position)` —— PC 的签名带位置参数，旧实现要求无参。

        这里钉**代码形状**（调用点必须显式声明允许那个可选参数）；"真的传两个参数也不报错"
        由 `runtime/tests/test_lua_entity_player.py` 的端到端断言钉住。
        """
        # ★ 批次 133（2026-09-25）：只钉到 `true` 为止（**不含闭合括号**）—— `HasTrinket` 现在
        # 还要把这个 id 取出来比对饰品槽，于是多了一个**出参**。"显式声明允许可选尾参"这条判据
        # 不受影响：谁把 `true` 去掉、或换回别的助手，这里仍然会红。
        self.assertIn('EntityPlayerProbeIdArgument(state, "EntityPlayer:HasTrinket", true', self.text)
        self.assertIn('EntityPlayerProbeOptionalIntegerArgument(state, "EntityPlayer:GetPoopSpell")',
                      self.text)

    def test_the_range_checking_helper_is_gone(self) -> None:
        """`EntityPlayerProbeSlots`（带 `maximum` 的那个）已被删除：留着它就是留一个
        "把 id 当槽位卡上限"的现成写法，下一个人会照着用。"""
        self.assertNotIn("EntityPlayerProbeSlots", code_only(self.text))
        self.assertNotIn("accepts one slot in [0,", code_only(self.text))

    def test_the_helper_only_requires_an_integer(self) -> None:
        body = self.text[self.text.index("bool EntityPlayerProbeIdArgument"):]
        body = body[:body.index("\n}")]
        self.assertIn("ReadIntegerArgument", body)  # 与统一口径一致：整数值的浮点也算
        self.assertNotIn("maximum", body)
        # 只钉"值不许做范围比较"（`static_cast<void>` 那种尖括号不算）。
        for forbidden in ("value <", "value >", "value <=", "value >=", "slot <", "slot >"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, body)

    def test_pocket_slot_members_no_longer_go_through_a_range_checking_helper(self) -> None:
        """`GetCard`/`GetPill` 的槽位口径不许退化成"越界即错"（它们各自有真机证据链）。

        ★ 批次 177（2026-09-28）：这两条现在是**引擎方法数据行**
        （`Entity_Player::GetPill(int)` @ `0x2E8D80` / `GetCard(int)` @ `0x2E8D58`），判据跟着换：
          ① 旧的手写助手 `EntityPlayerProbePocketSlot` **必须已经删掉**（否则就是"引擎里有、
             我们还自己写一遍"，而且那条路恒返回 0 —— 口袋里有东西时 EID 永远缺一条描述）；
          ② `Int1` 这个形状的描述符里 `intGuard` 必须是 `IntArgumentGuard::None`
             —— 只要有人给它挂上校验，`j = 2` 那次合法调用就又会被判错（旧缺陷的形态）。
        ★ 为什么不再逐字查"有没有范围比较"：这两条已经**没有代码**了（数据行只有参数个数与
        参数种类），所以"不许做范围校验"这件事只能由 ② 那条描述符断言表达。
        """
        self.assertNotIn("EntityPlayerProbePocketSlot", code_only(self.text))
        int1 = self.text[self.text.index("// 8 Int1："):]
        int1 = int1[:int1.index("IntArgumentGuard::None")]
        self.assertIn("EngineReturnKind::Int", int1)
        self.assertIn("EngineArgKind::Int", int1)

    def test_the_five_stubs_that_have_an_engine_twin_are_wired_to_it(self) -> None:
        """批次 177：这 5 条既是"引擎里有同名成员"、也是"以前恒返回假值"⇒ 两条判据都要查。

        ① 数据行在（id 出现在 `kEntityPlayerEngineRows` 里）；
        ② 旧处理器绑定**不在**（id 不出现在 `kEntityPlayerHandlers` 里）。
        ★ 只查 ① 会漏掉"数据行加了、旧假桩还留着"那种半截状态。
        """
        handlers = self.text[self.text.index("kEntityPlayerHandlers[]"):]
        handlers = handlers[:handlers.index("\n};")]
        rows = self.text[self.text.index("kEntityPlayerEngineRows[]"):]
        rows = rows[:rows.index("\n};")]
        for member, row_id, shape in ENGINE_ROW_MEMBERS:
            with self.subTest(member=member):
                self.assertIn(f"{{{row_id}, kEntityPlayer", rows,
                              f"{member} 必须走引擎方法数据行（{row_id}）")
                self.assertIn(f"EngineCallShape::{shape}", rows,
                              f"{member} 该用 {shape} 形状（签名见 runtime_constants.hpp 的注释）")
                self.assertNotIn(f"{{{row_id}, ", handlers,
                                 f"{member}（{row_id}）不许再留在手写处理器表里")
                self.assertNotIn(f"&{member.split(':')[1]},", handlers,
                                 f"{member} 的旧手写处理器必须已删除")
        # `GetCard`/`GetPill` 这两条（就是上面那份 `POCKET_SLOT_MEMBERS`）必须是 `Int1`：
        # 它们是"参数在 PC 上是槽位、越界不是错误"的唯一两条，形状错了就等于把范围口径改回去了。
        for member in POCKET_SLOT_MEMBERS:
            with self.subTest(member=member):
                entry = next(item for item in ENGINE_ROW_MEMBERS if item[0] == member)
                self.assertEqual(entry[2], "Int1")

    def test_the_evidence_trail_is_written_down(self) -> None:
        """判据必须能追溯到 PC 文档（改这条规则的人要能看到"凭什么是 id"）。"""
        helper = self.text[self.text.index("// 参数是**枚举 id**"):]
        helper = helper[:helper.index("bool EntityPlayerProbeIdArgument")]
        self.assertIn("isaacdocs-snapshot/docs/EntityPlayer.md", helper)
        for line in (":903", ":888", ":1191", ":1331"):
            with self.subTest(doc_line=line):
                self.assertIn(line, helper)


if __name__ == "__main__":
    unittest.main()
