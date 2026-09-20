"""门禁：自带模组菜单的**字体候选**必须与"哪些字体真的含中文"一致。

## 为什么要有它

2026-09-17 的事故：菜单（和 q4-items）都拿 `font/droid.fnt` 当"含中文字体"（代码里写着
`cjk = true`），而实测它是**纯 Latin-1**（`tools/fnt_glyph_report.py`：191 字形、码位上限 0xFF、
中日韩 **0** 个）⇒ 中文文案**静默空白**，菜单看上去"什么都没有"。同一条候选表里还有一个
大小写错误（`TeamMeatFont12.fnt`，磁盘上是 `teammeatfont12.fnt`），在大小写敏感的 romfs 上找不到。

这条门禁把三件事钉住：
1. **不许**把游戏自带字体标成含中文（真值取自 `tools/fnt_glyph_report.py`，不是凭印象）；
2. 游戏字体候选的路径必须能在仓库里的游戏资源目录中**按原样大小写**找到；
3. 含中文的候选必须排在纯 ASCII 候选**前面**（否则永远轮不到它们）。
"""

import importlib.util
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MENU_SCRIPT = ROOT / "runtime" / "source" / "program" / "embedded_mod_menu_script.hpp"
Q4_SCRIPT = ROOT / "dist" / "change-archive-20260917" / "003-q4-console-ui" / "main.lua.after"
GAME_FONT_DIR = (
    ROOT
    / "The Binding of Isaac_ Afterbirth+ 1.7.9b [010021C000B6A800][v524288][UPD]"
    / "Program #0/1/resources/font"
)

CANDIDATE_PATTERN = re.compile(r'\{\s*path\s*=\s*"([^"]+)"\s*,\s*cjk\s*=\s*(true|false)')


def load_font_tool():
    spec = importlib.util.spec_from_file_location(
        "fnt_glyph_report", ROOT / "tools" / "fnt_glyph_report.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def candidates(text: str) -> list[tuple[str, bool]]:
    return [(path, flag == "true") for path, flag in CANDIDATE_PATTERN.findall(text)]


class ModMenuFontCandidateTests(unittest.TestCase):
    def test_menu_candidates_are_honest(self):
        found = candidates(MENU_SCRIPT.read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(found), 3, "没解析到菜单的字体候选（脚本格式变了？）")

        # ① 游戏自带字体不许标成含中文
        for path, cjk in found:
            if path.startswith("font/") or path.startswith("resources/font/"):
                self.assertFalse(
                    cjk,
                    f"游戏自带字体 {path} 被标成 cjk = true —— 实测它们没有中文字形"
                    "（否则中文文案会静默空白）",
                )

        # ③ 含中文的候选必须排在纯 ASCII 之前
        flags = [cjk for _, cjk in found]
        self.assertIn(True, flags, "候选里应当至少有一个含中文的字体（否则中文文案永远画不出来）")
        first_ascii = flags.index(False)
        self.assertTrue(
            all(flags[index] for index in range(first_ascii)),
            "含中文的候选必须排在纯 ASCII 候选之前",
        )

        # ② 路径大小写必须与磁盘一致（只核对仓库里真有游戏资源的情况）
        if not GAME_FONT_DIR.exists():
            self.skipTest("仓库里没有游戏字体（公开仓库不带游戏资源）")
        for path, _ in found:
            if not path.startswith("font/"):
                continue
            relative = path[len("font/") :]
            self.assertTrue(
                (GAME_FONT_DIR / relative).exists(),
                f"菜单里的字体路径 {path} 在游戏资源目录里找不到（大小写也要一致）",
            )

    def test_q4_items_candidates_are_honest(self):
        if not Q4_SCRIPT.exists():
            self.skipTest("仓库里没有 q4-items 的最新脚本副本")
        found = candidates(Q4_SCRIPT.read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(found), 3, "没解析到 q4-items 的字体候选")
        for path, cjk in found:
            if path.startswith("font/"):
                self.assertFalse(cjk, f"q4-items 把游戏字体 {path} 标成含中文了")
        self.assertTrue(any(cjk for _, cjk in found), "q4-items 应当先试含中文的字体")

    def test_cjk_candidates_are_really_cjk(self):
        """候选里标了 `cjk = true` 的**仓库内文件**，实测必须真的含中日韩码位。"""
        tool = load_font_tool()
        checked = 0
        for source in (MENU_SCRIPT.read_text(encoding="utf-8"),):
            for path, cjk in candidates(source):
                if not cjk:
                    continue
                # 只核对能映射到仓库文件的那些（卡上路径 / 游戏路径在这里跳过）
                marker = "external item descriptions_836319872/resources/font/"
                if marker in path and not path.startswith("rom:/"):
                    local = ROOT / path
                    if local.exists():
                        entry = tool.report(local)
                        self.assertTrue(entry["can_draw_chinese"], f"{path} 标了含中文但实测不含")
                        checked += 1
        if checked == 0:
            self.skipTest("没有可核对的仓库内中文字体（跳过，不算失败）")


if __name__ == "__main__":
    unittest.main()
