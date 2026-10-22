"""q4-items字体候选检查；旧内嵌菜单已移除，原测试逐字归档在本轮dist。"""
import importlib.util
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
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
        if not Q4_SCRIPT.exists():
            self.skipTest("仓库没有q4-items字体脚本")
        for source in (Q4_SCRIPT.read_text(encoding="utf-8"),):
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
