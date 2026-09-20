"""门禁：`SKIP_HOOK_*` 编译开关必须与"跳过判据"里的分支一一对应。

## 为什么要有它

`SkipOptionalHooksPredicate` 是"一次只摘一个挂点"这种二分实验的唯一入口（用来定位
"模组全关时主屏/退出对局必崩"到底由哪个可选挂点引起）。这类开关最容易出的错是**写了两处、
只改了一处**：Makefile 里加了 `SKIP_HOOK_XXX`，判据里却没写对应分支 —— 于是构建"成功"、
开关"看起来生效"，实际上什么都没摘，**二分实验会给出完全错误的结论**（本项目已经因为
"两处各写一遍"栽过一次，见 `filesys` 路径归一化那条）。

所以这里把两边逐一比对：
* Makefile 里出现的每个 `SKIP_HOOK_<名字>` 都必须在判据里有对应分支；
* 判据里 `EXL_SKIP_HOOK_<名字>` 的每个分支也必须在 Makefile 里有变量；
* `EXL_CFLAGS` 必须把 `EXL_SKIP_HOOK_CFLAGS` 挂进去（否则变量定义了也传不到编译器）。
"""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MAKEFILE = ROOT / "runtime" / "Makefile"
HOOK_MANAGER = ROOT / "runtime" / "source" / "hook_manager.cpp"


class HookSkipSwitchTests(unittest.TestCase):
    def test_makefile_and_predicate_agree(self):
        makefile = MAKEFILE.read_text(encoding="utf-8")
        source = HOOK_MANAGER.read_text(encoding="utf-8")

        # Makefile：`SKIP_HOOK_X ?= 0` 形式声明的变量名
        declared = set(re.findall(r"^(SKIP_HOOK_[A-Z0-9_]+)\s*\?=", makefile, re.MULTILINE))
        self.assertTrue(declared, "Makefile 里没有声明任何 SKIP_HOOK_* 变量")

        # 判据：`EXL_SKIP_HOOK_X == 1` 的分支
        guarded = set(re.findall(r"EXL_(SKIP_HOOK_[A-Z0-9_]+)\s*==\s*1", source))
        self.assertTrue(guarded, "hook_manager.cpp 里没有 EXL_SKIP_HOOK_* 分支")

        self.assertEqual(
            declared,
            guarded,
            f"Makefile 与判据不一致：只在 Makefile={sorted(declared - guarded)}，"
            f"只在判据={sorted(guarded - declared)}",
        )

        # 每个开关都要真的被 -D 出去（否则定义了也传不到编译器）
        for name in sorted(declared):
            self.assertIn(
                f"-DEXL_{name}=$({name})",
                makefile,
                f"{name} 没有出现在 EXL_SKIP_HOOK_CFLAGS 的 -D 列表里",
            )
        self.assertIn(
            "$(EXL_SKIP_HOOK_CFLAGS)",
            makefile,
            "EXL_CFLAGS 没有接入 EXL_SKIP_HOOK_CFLAGS",
        )

    def test_every_optional_hook_has_a_switch(self):
        """表里的每个**可选**挂点都应当有对应的单摘开关（加新挂点时别忘了加开关）。

        开关后缀是**显式映射**、不按驼峰机械拆分：`ManagerRender` 的开关叫 `SKIP_HOOK_RENDER`
        （见 Makefile 里那段注释与 `docs/改动日志-20260917.md` 的构建命令）。
        """
        catalog = (
            ROOT / "runtime" / "src" / "domain" / "runtime" / "hook_catalog.hpp"
        ).read_text(encoding="utf-8")
        body = catalog.split("kHookCatalog = {{", 1)[1].split("}}", 1)[0]
        required = []
        optional = []
        for line in body.splitlines():
            line = line.strip()
            if not line.startswith("{HookId::"):
                continue
            name = line.split("HookId::", 1)[1].split(",", 1)[0]
            (required if "true}" in line.replace(" ", "") else optional).append(name)
        self.assertTrue(optional, "没解析出任何可选挂点（hook_catalog.hpp 的格式变了？）")

        switch_suffix = {
            "ManagerRender": "RENDER",
            "PreGetCollectible": "PREGETCOLLECTIBLE",
            "ManagerPresent": "PRESENT",
            "RebuildMountPoints": "REBUILDMOUNTS",
            "GameStart": "GAMESTART",
            # 批次 102 的四个事件中继（可选点）。
            "UseActiveItem": "USEACTIVEITEM",
            "UseCard": "USECARD",
            "UsePill": "USEPILL",
            "GameExit": "GAMEEXIT",
            # 批次 103 的掉落物碰撞（可选点）。
            "PickupCollision": "PICKUPCOLLISION",
            # 批次 104 的房间生成实体（可选点）。
            "RoomEntitySpawn": "ROOMENTITYSPAWN",
        }
        makefile = MAKEFILE.read_text(encoding="utf-8")
        source = HOOK_MANAGER.read_text(encoding="utf-8")
        for name in optional:
            self.assertIn(name, switch_suffix, f"可选挂点 {name} 没有登记开关后缀")
            suffix = switch_suffix[name]
            self.assertIn(f"SKIP_HOOK_{suffix}", makefile, f"{name} 缺 SKIP_HOOK_{suffix}")
            self.assertIn(
                f"HookId::{name}", source, f"判据里没有针对 {name} 的分支"
            )


if __name__ == "__main__":
    unittest.main()
