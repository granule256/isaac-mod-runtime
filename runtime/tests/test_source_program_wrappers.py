"""门禁：顶层 `runtime/source/*.cpp` **必须真的进了模块构建**，不许"加了文件、其实没编进去"。

## 为什么有这条（2026-09-23 批次 077 的一次真实构建失败）

构建的源文件收集在 `runtime/misc/mk/common.mk`：

```
MODULES := $(shell find $(ROOT_SOURCE) -mindepth 1 -maxdepth 1 -type d) $(EXTRA_MODULES)
SOURCES := $(foreach module,$(MODULES),$(shell find $(module) -type d))
CPPFILES := $(foreach dir,$(SOURCES),$(notdir $(wildcard $(dir)/*.cpp)))
```

`MODULES` **只收 `source/` 的下一级子目录**（`source/program/`、`source/probe/`、`source/relay/`…），
**`source/` 自己不在里面** ⇒ 顶层 `source/*.cpp` 不会进 `CPPFILES`。
它们能被编进去，全靠 `source/program/<同名>.cpp` 这个**一行包装**（`#include "../<同名>.cpp"`）。

**漏了包装会怎样**：不编译、不报错、不警告 —— 一路走到链接才以"未定义符号"的形式炸出来
（这一次是 `未定义符号门禁失败：… EntryRelayMenuGameRenderCallback … ModMenuNativeInstall`），
排查成本是"读构建日志、dump `make -p`、找 CPPFILES 为什么不含它"。
而这条纪律**项目里早就写过**（`docs/交接文档-20260921-夜-…` 第四节第 5 条
"新源文件要补 `source/program/` 包装"）—— 但**当时只是文档里的一句话**，
所以又踩了一次。⇒ 按项目的元纪律："凡是已经知道、但只在某处注释里的坑，
都要变成一条命令 + 一条门禁"。

## 判据

1. **包装指对了**：每个 `source/program/X.cpp`，只要顶层有 `source/X.cpp`，
   它的内容就必须是 `#include "../X.cpp"`（不许指到别处、不许空壳）；
2. **没有静默漏网**：顶层每个 `source/*.cpp` 都必须满足三者之一 ——
   * 有 `source/program/<同名>` 包装；**或**
   * 在 `common.mk` 里被**显式** `CPPFILES +=` 收进去；**或**
   * 在下面的"不参与模块构建"名单里，**并写明理由**。
3. **名单不许腐烂**：名单里每一项都必须真的还存在（文件删了就要从名单里去掉）。
"""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "runtime" / "source"
PROGRAM = SOURCE / "program"
COMMON_MK = ROOT / "runtime" / "misc" / "mk" / "common.mk"

#: 顶层有、但**不进**模块构建的源文件（各有各的理由，不许"因为没写包装"而留在这里）。
NOT_IN_MODULE_BUILD = {
    "diagnostic_entry.cpp":
        "诊断阶段自己的入口（`EXL_DIAGNOSTIC_STAGE` 那些构建才用），不进生产模块",
    "saltynx_external_plugin_entry.cpp":
        "SaltyNX 宿主插件那条线的入口（`SALTYNX_PLUGIN=1`），不进生产模块",
}


class SourceProgramWrapperTests(unittest.TestCase):
    def top_level(self) -> list[str]:
        return sorted(p.name for p in SOURCE.glob("*.cpp") if p.is_file())

    def test_every_top_level_source_is_actually_built(self):
        """顶层每个 `source/*.cpp` 都要有办法进构建 —— 否则它**永远不会被编译**。"""
        common = COMMON_MK.read_text(encoding="utf-8")
        # One Make assignment may register several source files on the same line.
        assignments = re.findall(r"^CPPFILES\s*\+=\s*([^\n#]+)", common, re.MULTILINE)
        explicit = {word for row in assignments for word in row.split() if word.endswith('.cpp')}
        missing = []
        for name in self.top_level():
            if (PROGRAM / name).is_file():
                continue
            if name in explicit:
                continue
            if name in NOT_IN_MODULE_BUILD:
                continue
            missing.append(name)
        self.assertEqual(
            missing, [],
            f"这些顶层源文件既没有 `source/program/` 包装、也没在 common.mk 里显式收进 CPPFILES、"
            f"也不在「不参与模块构建」名单里 ⇒ **它们永远不会被编译**（要到链接才以未定义符号报出来）："
            f"{missing}\n"
            f"修法：`runtime/source/program/<同名>.cpp` 里写一行 `#include \"../<同名>.cpp\"`。")

    def test_wrapper_points_at_the_matching_top_level_file(self):
        """包装必须**指向同名那个顶层文件**（空壳/指错 = 编了个不相干的东西）。"""
        checked = 0
        for wrapper in sorted(PROGRAM.glob("*.cpp")):
            top = SOURCE / wrapper.name
            if not top.is_file():
                continue  # `program/` 下也有自己独有的文件（例如 saltynx 那几个探针）
            body = wrapper.read_text(encoding="utf-8")
            includes = re.findall(r'^\s*#\s*include\s+"([^"]+)"', body, re.MULTILINE)
            self.assertIn(
                f"../{wrapper.name}", includes,
                f"{wrapper.relative_to(ROOT)} 必须 `#include \"../{wrapper.name}\"`"
                f"（现在是 {includes}）—— 指错就等于编了个不相干的东西")
            checked += 1
        self.assertGreater(checked, 5, "一个包装都没检查到，这条门禁多半失效了")

    def test_not_built_list_does_not_rot(self):
        """名单里每一项都必须真的还存在（文件没了就要从名单里去掉）。"""
        stale = [name for name in NOT_IN_MODULE_BUILD if not (SOURCE / name).is_file()]
        self.assertEqual(stale, [], f"这些文件已经不存在了，请从 NOT_IN_MODULE_BUILD 里删掉：{stale}")
        # 名单里也不许出现"其实有包装"的项（那说明有人补了包装却没更新名单）
        redundant = [name for name in NOT_IN_MODULE_BUILD if (PROGRAM / name).is_file()]
        self.assertEqual(redundant, [], f"这些已经有包装了，不该再留在名单里：{redundant}")


if __name__ == "__main__":
    unittest.main()
