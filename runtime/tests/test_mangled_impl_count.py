"""门禁：`tools/mangled_impl_count.py`（数"同名方法有几个实现"）的判据工具不能自己出错。

## 为什么要有它

批次 286（2026-10-02）暴露的是**"判据工具本身静默给出相反结论"**这一类风险。
那个工具回答的问题很硬：某个方法在整份 `Repentance.nro` 里有几个实现
（进批三条硬门槛的第 ② 条）。以前用的是正则 `_ZN15IsaacRepentance\\w*<名>E\\w*`，
它有**三个会给出错误答案的坑**：

1. **`const` 方法前缀是 `_ZNK` 而不是 `_ZN`** ⇒ 只写 `_ZN` 时 const 方法**恒 0 命中**。
   批次 286 在 `Entity::IsVulnerableEnemy`（`_ZNK15IsaacRepentance6Entity17IsVulnerableEnemyEPS0_`）
   上撞到：扫出 **0 条**，而"0 条"会被读成**"这条根本没有实现"**（与事实相反）。
2. **`\\w*<名>` 会子串误命中** ⇒ 扫 `IsFlying` 会命中 `PlayerManager::AnyPlayerIsFlying`（虚警）。
3. **签名前缀不能用 `split("E")` 切** ⇒ `IsaacRepentance6Entity` 里的 `E` 会让它在半个组件名上断开
   （本工具第一版就是这么错的，第一版输出 `_ZNK15IsaacRepentance6`）。

本门禁把这三条**钉在机器上**：前两条用真实镜像验（仓库里那份 NRO 在就直接验，不在就跳过），
第三条用纯函数验（不需要镜像）。★ 这样"工具哪天又被改回正则"会在门禁里红，而不是等到
某条 API 被误判成"引擎没有"而白挡 11 批。
"""

import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools" / "mangled_impl_count.py"
NRO = (
    ROOT
    / "The Binding of Isaac_ Afterbirth+ 1.7.9b [010021C000B6A800][v524288][UPD]"
    / "Program #0/1/.nro/Repentance.nro"
)


def load_tool():
    """按路径加载 `tools/mangled_impl_count.py`（`tools/` 不是包）。"""
    spec = importlib.util.spec_from_file_location("mangled_impl_count", TOOL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class MangledComponentsTests(unittest.TestCase):
    """纯函数：`components()` 的切段与"停下位置"。"""

    @classmethod
    def setUpClass(cls):
        cls.tool = load_tool()

    def test_const_method_prefix_is_parsed(self):
        """★ 坑 ①：`_ZNK` = 两个 cv 限定符（`N` + `K`），都要跳过。"""
        parts, _ = self.tool.components(
            "_ZNK15IsaacRepentance6Entity17IsVulnerableEnemyEPS0_")
        self.assertEqual(parts, ["IsaacRepentance", "Entity", "IsVulnerableEnemy"])

    def test_non_const_method_prefix_is_parsed(self):
        parts, _ = self.tool.components("_ZN15IsaacRepentance10Entity_NPC5MorphENS_11eEntityTypeEjj i")
        self.assertEqual(parts, ["IsaacRepentance", "Entity_NPC", "Morph"])

    def test_signature_stops_after_the_last_component(self):
        """★★ 坑 ③：签名前缀不能停在 `IsaacRepentance6Entity` 的那个 `E` 上。"""
        text = "_ZNK15IsaacRepentance6Entity17IsVulnerableEnemyEPS0_"
        _, stop = self.tool.components(text)
        self.assertEqual(text[:stop], "_ZNK15IsaacRepentance6Entity17IsVulnerableEnemy")

    def test_exact_name_match_is_not_a_substring_match(self):
        """坑 ②：`AnyPlayerIsFlying` 的组件链**不以** `IsFlying` 结尾 ⇒ 不该算命中。"""
        parts, _ = self.tool.components("_ZNK15IsaacRepentance13PlayerManager17AnyPlayerIsFlyingEv")
        self.assertNotEqual(parts[-1], "IsFlying")
        self.assertEqual(parts[-1], "AnyPlayerIsFlying")


class MangledImplCountAgainstImageTests(unittest.TestCase):
    """真镜像判据（没有镜像就跳过 —— 这是"证据缺失"而不是"通过"）。"""

    @classmethod
    def setUpClass(cls):
        if not NRO.exists():
            raise unittest.SkipTest(f"本机没有游戏镜像：{NRO}")
        cls.tool = load_tool()
        cls.data = NRO.read_bytes()

    def count(self, method):
        return self.tool.implementations(self.data, method)

    def test_const_method_is_found_at_all(self):
        """★★ 坑 ①的真镜像判据：const 方法**必须能数到 1 个**（老正则会给出 0）。"""
        rows = self.count("IsVulnerableEnemy")
        self.assertEqual(len(rows), 1, f"IsVulnerableEnemy 应恰好 1 个实现，实得 {len(rows)}")
        (owners, signature), = rows
        self.assertEqual(owners, ("IsaacRepentance", "Entity"))
        self.assertTrue(signature.startswith("_ZNK"), signature)
        self.assertTrue(signature.endswith("IsVulnerableEnemy"), signature)

    def test_substring_name_is_not_inflated(self):
        """★★ 坑 ②的真镜像判据：`IsFlying` 只有 `Entity` 一个实现（不被 `AnyPlayerIsFlying` 顶成 2）。"""
        owners = {owner for owner, _ in self.count("IsFlying")}
        self.assertEqual(owners, {("IsaacRepentance", "Entity")})

    def test_two_sibling_classes_both_show_up(self):
        """反回归：`Morph` 应当数到**两个不同的类**（批次 285 的进批依据就是这一条）。"""
        owners = {owner for owner, _ in self.count("Morph")}
        self.assertEqual(owners, {("IsaacRepentance", "Entity_NPC"),
                                  ("IsaacRepentance", "Entity_Pickup")})

    def test_multi_implementation_is_reported(self):
        """反回归：多实现的方法要**如实数出多个**（`CanShutDoors` = 4，批次 284 用它做规则性排除）。"""
        owners = {owner for owner, _ in self.count("CanShutDoors")}
        self.assertEqual(owners, {("IsaacRepentance", "Entity"),
                                  ("IsaacRepentance", "Entity_Familiar"),
                                  ("IsaacRepentance", "Entity_NPC"),
                                  ("IsaacRepentance", "Entity_Projectile")})


if __name__ == "__main__":
    unittest.main()
