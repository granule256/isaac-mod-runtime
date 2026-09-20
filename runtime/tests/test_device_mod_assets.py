"""门禁：**卡上模组资源体检**（`tools/device_mod_assets.py`）的判据本身。

## 为什么有这条门禁（2026-09-19 的一次真实事故）

真机上"绘制代码明明在跑、却一个像素都不显示"，排查**四轮**才定位到：手工拷进卡的第三方模组
（GoodTrip）的 `resources/sprite/gt/*.png` 旁边**没有同名 `.pcx`**，而 Switch 版引擎
（`Manager::LoadImage`）会把 `.png` 改写成 `.pcx`、解码器又按扩展名挑 ⇒ 贴图**静默加载失败**。
这条知识**本来就在仓库里**（`tools/png_to_pcx.py` 的头部注释），但它只是注释 ⇒ 又踩了一次。

于是把它做成命令（`tools/device_mod_assets.py`），并**用这条门禁钉住它的判据**，
免得下次有人把判据改宽/改窄（两种错都真发生过）：

1. **`.anm2` 引用的贴图必须有同名 `.pcx`** —— 漏报 ⇒ 又会出现"看不见的精灵"（事故本身）；
2. **没被任何 `.anm2` 引用的 PNG 不判** —— 误报 ⇒ 字体贴图会被当成缺项（本工具第一版里
   EID 一下就刷出 **39 条假阳性**，而 EID 的中文字体在真机上一直是好的）；
3. **`.png` 与 `.pcx` 都不在** ⇒ 报 `missing_spritesheet`（引用完全落地不了，是模组自己的资源问题）。
"""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools" / "device_mod_assets.py"

#: 一个最小 `.anm2`：只需要 `Path="…"` 这一条（解析器只认它）。
ANM2 = """<?xml version="1.0"?>
<AnimatedSprite>
  <Content>
    <Spritesheets>
      <Spritesheet Path="{name}" Id="0" />
    </Spritesheets>
  </Content>
</AnimatedSprite>
"""


def build_mod(root: Path, *, pcx: bool, unreferenced_png: bool, missing_reference: bool) -> Path:
    """搭一份合成模组：`resources/sprite/gt/` 下放一份被引用的贴图（可选带 `.pcx`）。"""
    mod = root / "fixture-mod"
    sprite = mod / "resources" / "sprite" / "gt"
    sprite.mkdir(parents=True)
    (sprite / "sheet.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    if pcx:
        (sprite / "sheet.pcx").write_bytes(b"\x0a\x05\x01\x08")
    (sprite / "sheet.anm2").write_text(ANM2.format(name="sheet.png"), encoding="utf-8")
    if missing_reference:
        (sprite / "ghost.anm2").write_text(ANM2.format(name="ghost.png"), encoding="utf-8")
    if unreferenced_png:
        font = mod / "resources" / "font"
        font.mkdir(parents=True)
        (font / "family.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    return mod


class DeviceModAssetsGateTests(unittest.TestCase):
    def run_tool(self, mod: Path) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(TOOL), "--local", str(mod), "--json"],
            text=True, capture_output=True)

    def findings(self, result: subprocess.CompletedProcess) -> list[dict]:
        payload = json.loads(result.stdout)
        return [finding for report in payload["reports"] for finding in report["findings"]]

    def test_missing_pcx_is_reported(self):
        """判据 1：`.anm2` 引用的贴图没有同名 `.pcx` ⇒ 必须报（这就是那次事故）。"""
        with tempfile.TemporaryDirectory() as temporary:
            mod = build_mod(Path(temporary), pcx=False, unreferenced_png=False,
                            missing_reference=False)
            result = self.run_tool(mod)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        findings = self.findings(result)
        self.assertEqual([f["kind"] for f in findings], ["missing_pcx"], findings)
        self.assertTrue(findings[0]["path"].endswith("resources/sprite/gt/sheet.pcx"),
                        findings[0])

    def test_complete_mod_passes(self):
        with tempfile.TemporaryDirectory() as temporary:
            mod = build_mod(Path(temporary), pcx=True, unreferenced_png=True,
                            missing_reference=False)
            result = self.run_tool(mod)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.findings(result), [])

    def test_unreferenced_png_is_not_a_finding(self):
        """判据 2：字体那一类（没有被 `.anm2` 引用的 PNG）不许报 —— 第一版在这里误报了 39 条。"""
        with tempfile.TemporaryDirectory() as temporary:
            mod = build_mod(Path(temporary), pcx=True, unreferenced_png=True,
                            missing_reference=False)
            result = self.run_tool(mod)
        self.assertEqual(self.findings(result), [], result.stdout)

    def test_reference_with_no_file_at_all_is_its_own_kind(self):
        """判据 3：`.png`/`.pcx` 都不在 ⇒ `missing_spritesheet`（与"缺 .pcx"分开，处置不同）。"""
        with tempfile.TemporaryDirectory() as temporary:
            mod = build_mod(Path(temporary), pcx=True, unreferenced_png=False,
                            missing_reference=True)
            result = self.run_tool(mod)
        kinds = sorted(finding["kind"] for finding in self.findings(result))
        self.assertEqual(kinds, ["missing_spritesheet"], result.stdout)


if __name__ == "__main__":
    unittest.main()
