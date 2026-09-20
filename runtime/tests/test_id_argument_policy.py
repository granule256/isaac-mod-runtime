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

#: 参数是**枚举 id** 的七个成员：必须用 `EntityPlayerProbeIdArgument` 校验。
ID_ARGUMENT_MEMBERS = (
    "EntityPlayer:GetCollectibleRNG",
    "EntityPlayer:GetTrinketRNG",
    "EntityPlayer:GetCardRNG",
    "EntityPlayer:GetPillRNG",
    "EntityPlayer:HasTrinket",
    "EntityPlayer:HasPlayerForm",
    "EntityPlayer:GetPlayerFormCounter",
)

#: 参数在 PC 上确实是槽位、但"越界不是错误"的两个成员：只钉整数，越界走"没有"。
POCKET_SLOT_MEMBERS = (
    "EntityPlayer:GetCard",
    "EntityPlayer:GetPill",
)


class IdArgumentPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = ISAAC_API.read_text(encoding="utf-8")

    def test_every_id_member_uses_the_integer_only_helper(self) -> None:
        for member in ID_ARGUMENT_MEMBERS:
            with self.subTest(member=member):
                self.assertIn(f'EntityPlayerProbeIdArgument(state, "{member}")', self.text)

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

    def test_pocket_slot_members_keep_the_no_range_rule(self) -> None:
        """`GetCard`/`GetPill` 的槽位口径不许退化成"越界即错"（它们各自有真机证据链）。"""
        for member in POCKET_SLOT_MEMBERS:
            with self.subTest(member=member):
                self.assertIn(f'EntityPlayerProbePocketSlot(state, "{member}"', self.text)
        pocket = self.text[self.text.index("bool EntityPlayerProbePocketSlot"):]
        pocket = pocket[:pocket.index("\n}")]
        self.assertNotIn("slot >", pocket)
        self.assertNotIn("slot <", pocket)

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
