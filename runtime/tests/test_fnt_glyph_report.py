"""门禁：`tools/fnt_glyph_report.py` 的解析必须与 Isaac 的 `.fnt` 真实布局一致。

## 为什么要有它

2026-09-17 的教训：`.fnt` 字符块**没有"数量"前缀**（内容直接是 `size / 20` 条 20 字节记录），
把第一条记录的码位（空格 = `0x20` = 32）当"数量"读，会让**每个**字体都被报告成"32 个字形"，
而"缺字形"这种故障是**静默**的（画中文只会空白，不报错）—— 用错的解析结果去下结论，
就会得出"这个字体只有 32 个字形"这类**假结论**。

所以这里用**合成字体**把关：
* 造一个只有 3 个字形（含一个中文码位）的假 `.fnt`，断言解析出 3 个字形 —— 记录布局一改就判红；
* 仓库里若有真实字体（游戏资源目录 / EID 字体），顺便核对已知数字（droid 无中日韩码位、
  EID 中文字体含大量中日韩码位）；文件不在时跳过，不阻塞别的门禁。
"""

import struct
import unittest
from pathlib import Path

import importlib.util

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools" / "fnt_glyph_report.py"

GAME_FONT_DIR = (
    ROOT
    / "The Binding of Isaac_ Afterbirth+ 1.7.9b [010021C000B6A800][v524288][UPD]"
    / "Program #0/1/resources/font"
)
EID_CN_FONT = (
    ROOT
    / "analysis/pc-mod-contract/romfs-preview/atmosphere/contents/010021C000B6A000"
    / "romfs/isaac_mods/mods/external item descriptions_836319872/resources/font/eid_cn_default.fnt"
)


def load_tool():
    spec = importlib.util.spec_from_file_location("fnt_glyph_report", TOOL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def synthetic_fnt(codepoints):
    """按真实布局造一个最小 `.fnt`：类型 3 = 图集名、类型 4 = 字符表（无数量前缀）。"""
    pages = b"fake_0.png\0"
    chars = b"".join(struct.pack("<I", code) + bytes(16) for code in codepoints)
    out = bytearray(b"BMF\x03")
    out.append(1)
    out += struct.pack("<I", 4) + b"info"
    out.append(3)
    out += struct.pack("<I", len(pages)) + pages
    out.append(4)
    out += struct.pack("<I", len(chars)) + chars
    return bytes(out)


class FntGlyphReportTests(unittest.TestCase):
    def test_record_layout_has_no_count_prefix(self):
        tool = load_tool()
        raw = synthetic_fnt([0x20, 0x41, 0x795E])   # 空格、'A'、神
        codepoints, pages = tool.parse_binary_fnt(raw)
        self.assertEqual(codepoints, [0x20, 0x41, 0x795E],
                         "字符块被当成有'数量'前缀了（那会把 0x20 读成 32 个字形）")
        self.assertEqual(pages, ["fake_0.png"])

        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "synthetic.fnt"
            path.write_bytes(raw)
            entry = tool.report(path)
        self.assertTrue(entry["ok"])
        self.assertEqual(entry["glyphs"], 3)
        self.assertFalse(entry["can_draw_chinese"], "抽样里的中文不在字体里时不该判成'含中文'")

    def test_real_fonts_if_present(self):
        tool = load_tool()
        droid = GAME_FONT_DIR / "droid.fnt"
        if not droid.exists():
            self.skipTest("仓库里没有游戏字体（公开仓库不带游戏资源）")
        entry = tool.report(droid)
        self.assertTrue(entry["ok"])
        self.assertEqual(entry["cjk_glyphs"], 0, "游戏自带 droid.fnt 不含中日韩字形")
        self.assertFalse(entry["can_draw_chinese"])

        if not EID_CN_FONT.exists():
            self.skipTest("仓库里没有 EID 的中文字体")
        cn = tool.report(EID_CN_FONT)
        self.assertTrue(cn["ok"])
        self.assertGreater(cn["cjk_glyphs"], 10000, "EID 中文字体应当含大量中日韩字形")
        self.assertTrue(cn["can_draw_chinese"])


if __name__ == "__main__":
    unittest.main()
