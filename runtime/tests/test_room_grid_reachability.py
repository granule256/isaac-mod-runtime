"""端到端判据：**把这类网格喂给 EID 自己的寻路器**，它必须判出"有路/没路"。

## 为什么这条测试存在（而不是只测内存读得对不对）

批次 098 修的是"运行时 `Room:GetGridPath` 恒返 1000"这个占位实现，而**为什么它是缺陷**只能由
消费者（EID）的行为说明：EID 用 `collision <= 900` 判"这一格能不能走"，恒 1000 就恒"不能走"，
于是地上每一颗药丸、每一张卡片都被判"够不到"、只画问号（用户 2026-09-20 报的现象）。

`runtime/tests/test_lua_room_grid.py` 钉的是"我们读的内存对不对"；本测试钉的是
"**换成这个读法之后，EID 的判据会得出什么**" —— 用的是**上游原文的两个函数**
（`features/eid_api.lua` 的 `EID:EvaluateLocation`/`EID:HasPathToPosition`，运行时抽取、
不抄写）与**上游的寻路器**（`features/pathfinder/luafinding.lua`），跑在合成的 13×7 网格上。

判据（`tools/room_grid_reachability_probe.py` 的四个场景）：

| 场景 | 引擎数组口径（新） | 恒 1000（旧） |
| --- | --- | --- |
| 全可走 | **有路** | 没路 ← 旧实现下用户看到的就是这个 |
| 目标被围死 | 没路 | 没路 |
| 竖墙隔开 | 没路 | 没路 |
| 高代价但仍可走（900） | **有路** | 没路 |

⇒ 旧口径**四个场景全判没路**：这条断言就是"症状在宿主上可复现"的存档，也是"新口径真的
改变了 EID 的结论"的证据（只测内存值的话，把它改回常量也能过一部分断言）。

没有宿主 C 编译器时**明确 skip**（不伪装成通过）—— 需要它来编仓库自带的 vendored Lua 5.3.3。
"""

import unittest
from pathlib import Path

try:
    from tools.room_grid_reachability_probe import (
        _scenarios,
        ensure_lua,
        run,
    )
except ImportError:  # 直接以 `python3 runtime/tests/...` 运行时把仓库根加进来
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from tools.room_grid_reachability_probe import (  # type: ignore[no-redef]
        _scenarios,
        ensure_lua,
        run,
    )


class RoomGridReachabilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            ensure_lua()
        except RuntimeError as error:  # 没有 cc：明确 skip，不伪装成通过
            raise unittest.SkipTest(f"没有宿主 C 编译器，跳过端到端寻路判据：{error}") from error
        cls.scenarios = _scenarios()

    def test_engine_array_convention_matches_eids_expectation(self):
        """引擎数组口径下，四个场景的"有路/没路"必须与 PC 判据一致。"""
        rows = run("engine-array", self.scenarios)
        self.assertEqual(len(rows), len(self.scenarios))
        for scenario, row in zip(self.scenarios, rows):
            with self.subTest(scenario=scenario["name"]):
                self.assertEqual(row["has_path"], scenario["expect_path"],
                                 f"{scenario['name']}：EID 的判断与 PC 判据不一致")

    def test_constant_placeholder_makes_every_resource_unreachable(self):
        """★ 存下"旧实现导致的现象"：恒 1000 口径下**四个场景全判没路**。

        这条不是"测旧代码"，而是把根因钉成可执行的：任何时候有人把 `GetGridPath` 改回常量
        （或让它在正常房间里也返回 > 900 的值），用户看到的就会重新变成"药丸/卡片只有问号"。
        """
        rows = run("placeholder-const", self.scenarios)
        self.assertTrue(all(not row["has_path"] for row in rows),
                        "恒 1000 的口径本应让每个场景都判'够不到'（= 用户看到的问号）")

    def test_probe_reports_the_grid_index_it_asked_about(self):
        """顺带钉住下标口径：玩家格 (2,3) ⇒ `W*3+2 = 41`，目标格 (10,3) ⇒ `W*3+10 = 49`。

        下标口径是本批次最容易写错的地方（引擎是 `W*gy + gx`，而 EID 的
        `EvaluateLocation` 写的是 `gx*W + gy` —— 两者靠 `luafinding` 自己的 X/Y 互换才一致）。
        """
        rows = run("engine-array", self.scenarios)
        for row in rows:
            with self.subTest(scenario=row["name"]):
                self.assertEqual(row["start_index"], 13 * 3 + 2)
                self.assertEqual(row["end_index"], 13 * 3 + 10)


if __name__ == "__main__":
    unittest.main()
