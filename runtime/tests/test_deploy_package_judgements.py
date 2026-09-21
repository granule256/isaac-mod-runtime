"""打包工具的**判据**门禁：别再打出"装了却用不了"的包。

## 为什么有这条（2026-09-21）

发布包出过两类"用户看得见、我们看不见"的问题：

1. **包里没有清单**（2026-09-20）：运行时的清单路径是写死的 `rom:/isaac_mods/manifest.json`，
   包里缺它 ⇒ 干净卡上**一个模组都不加载**；旧卡上则是"清单里列着、目录换成别的" ⇒
   用户看到的是"**模组在列表里、但用不了**"。工具现在**永远**写清单（`write_manifest`）。
2. **模组贴图只带 PNG 而图转不了**（2026-09-21）：`--drop-mod-pcx` 之后贴图全靠运行时
   PNG→PCX 桥；桥只支持 8 位、非隔行、色彩类型 0/2/4/6 —— **调色板/16 位/隔行转不了**，
   真机现象是"`Load` 成功、画面空白、不报错"，也就是"这个模组装了没用"。
   工具现在会在打包前把这类图挑出来并**中止**（`check_png_convertibility`）。

本门禁钉住这两条，以及**字体 PNG 的豁免**（`.fnt` 按 `.png` 名字直接引用、不经过桥；
2026-09-19 那版体检工具把 EID 的 39 张字体图全报成缺项，就是漏了这条口径）。
"""

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

try:
    from .test_screen_resource_mod import make_png
except ImportError:
    from test_screen_resource_mod import make_png


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools" / "build_deploy_package.py"
CONTENT_ID = "010021C000B6A000"


class DeployPackageJudgementTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.root = Path(self._temp.name)
        # 假运行时：工具只要求这两个文件存在（内容不校验）
        exefs = self.root / "runtime" / "atmosphere" / "contents" / CONTENT_ID / "exefs"
        exefs.mkdir(parents=True)
        (exefs / "subsdk9").write_bytes(b"fake-subsdk9")
        (exefs / "main.npdm").write_bytes(b"fake-npdm")
        # 假运行时也要带"必需的中继补丁目录"：真实构建产物里每次都会生成它，
        # 打包工具现在**要求**它在（缺了就直接拒绝打包 —— 那是"EID 套装进度恒 0/3"的形态）。
        patch = (self.root / "runtime" / "atmosphere" / "nro_patches"
                 / "isaac-repentance-lifecycle-relay")
        patch.mkdir(parents=True)
        (patch / "BUILDID0000000000000000000000000000000000000000000000000000000000.ips").write_bytes(
            b"fake-lifecycle-ips")
        # 旧 IPS 后端遗留也放一份进假运行时：打包工具**不许**把它们带进包，
        # 下面有断言钉住这一点（带上去会让所有挂点失效）。
        for name in ("isaac-repentance-manager-update-relay",
                     "isaac-repentance-model-server-relay-not-a-real-name"):
            legacy = self.root / "runtime" / "atmosphere" / "nro_patches" / name
            legacy.mkdir(parents=True)
            (legacy / "legacy.ips").write_bytes(b"fake-legacy-ips")

    def tearDown(self) -> None:
        self._temp.cleanup()

    def make_mod(self, name: str, png_color_type: int, *, png_relative: str,
                 with_lua: bool = True) -> Path:
        mod = self.root / name
        target = mod / png_relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(make_png(8, 8, png_color_type))
        if with_lua:
            (mod / "main.lua").write_text("-- mod\n", encoding="utf-8")
        return mod

    def run_tool(self, *mods: Path, extra: tuple[str, ...] = ()) -> subprocess.CompletedProcess:
        output = self.root / "package"
        return subprocess.run(
            [sys.executable, str(TOOL), "--name", "test-package", "--output", str(output),
             "--runtime", str(self.root / "runtime"),
             *[arg for mod in mods for arg in ("--mod", str(mod))],
             *extra],
            capture_output=True, text=True, cwd=ROOT,
        )

    def test_good_mod_packages_and_manifest_lists_every_mod(self):
        """正常模组：打包成功，清单**逐条列出**（缺清单就是"模组在列表里但用不了"）。"""
        first = self.make_mod("AlphaMod", 6, png_relative="resources/gfx/a.png")
        second = self.make_mod("BetaMod", 2, png_relative="resources-dlc3/gfx/b.png")
        result = self.run_tool(first, second, extra=("--drop-mod-pcx",))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        manifest_path = (self.root / "package" / "atmosphere" / "contents" / CONTENT_ID
                         / "romfs/isaac_mods/manifest.json")
        self.assertTrue(manifest_path.is_file(), "包里必须有清单")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual([m["directory"] for m in manifest["mods"]], ["AlphaMod", "BetaMod"])
        self.assertEqual(manifest["mods"][0]["entry"], "mods/AlphaMod/main.lua")
        # `resources-dlc3` 层要**原样**带进包（层名不能改，改了覆盖语义就变）
        self.assertTrue((self.root / "package" / "atmosphere" / "contents" / CONTENT_ID
                         / "romfs/isaac_mods/mods/BetaMod/resources-dlc3/gfx/b.png").is_file())

    def test_palette_png_refuses_even_when_dropping_pcx(self):
        """调色板 PNG 转不了 ⇒ **丢掉 `.pcx` 也必须中止**（否则真机上那张图静默空白）。"""
        mod = self.make_mod("PaletteMod", 3, png_relative="resources/gfx/palette.png")
        result = self.run_tool(mod, extra=("--drop-mod-pcx",))
        self.assertEqual(result.returncode, 3, result.stdout + result.stderr)
        self.assertIn("转不了", result.stdout + result.stderr)

    def test_allow_asset_problems_lets_it_through_with_a_warning(self):
        """确实要带伤发布时，`--allow-asset-problems` 放行（但必须打出来）。"""
        mod = self.make_mod("PaletteMod", 3, png_relative="resources/gfx/palette.png")
        result = self.run_tool(mod, extra=("--drop-mod-pcx", "--allow-asset-problems"))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("转不了", result.stdout)

    def test_package_ships_the_required_relay_patch_only(self):
        """包必须带 `lifecycle-relay` 那一份，**不许**带旧 IPS 后端那几份。

        这一条来自 2026-09-22 的真机证据：卡上缺这份补丁 ⇒ 开局事件永远不来 ⇒
        EID 的套装进度恒 `0/3`（`GameStart` 是 `required=false`，装不上只记 Skipped，
        所以"挂点全装好、零失败"看不出问题）。反过来，带上旧那 5 份会让
        **所有**挂点装不上（入口要逐字节核对原版字节）。
        """
        mod = self.make_mod("AlphaMod", 6, png_relative="resources/gfx/a.png")
        result = self.run_tool(mod, extra=("--drop-mod-pcx",))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        patches = self.root / "package" / "atmosphere" / "nro_patches"
        self.assertTrue((patches / "isaac-repentance-lifecycle-relay").is_dir(),
                        "包里必须有 lifecycle-relay（缺了它套装进度恒 0/3）")
        self.assertEqual(sorted(p.name for p in patches.iterdir()),
                         ["isaac-repentance-lifecycle-relay"],
                         "包里只允许有 lifecycle-relay 这一份补丁")
        # 必需补丁的**文件**也要在（目录空着等于没带）
        self.assertTrue(any(p.suffix == ".ips" for p in
                            (patches / "isaac-repentance-lifecycle-relay").iterdir()))

    def test_no_relay_patches_switch_omits_it_deliberately(self):
        """`--no-relay-patches` 是"我就是要一份不含补丁的包"的显式开关（默认带）。"""
        mod = self.make_mod("AlphaMod", 6, png_relative="resources/gfx/a.png")
        result = self.run_tool(mod, extra=("--drop-mod-pcx", "--no-relay-patches"))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse((self.root / "package" / "atmosphere" / "nro_patches").exists())

    def test_font_pngs_are_exempt(self):
        """字体 PNG 豁免：`.fnt` 按 `.png` 名字直接引用、不经过桥 ⇒ 调色板也不算问题。"""
        mod = self.make_mod("FontMod", 3, png_relative="resources/font/palette_font.png")
        result = self.run_tool(mod, extra=("--drop-mod-pcx",))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
