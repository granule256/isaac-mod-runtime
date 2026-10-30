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
import os
import struct
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
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
        nso=bytearray(256);nso[:4]=b"NSO0";struct.pack_into('<III',nso,0x30,256,0x400000,0x1000);struct.pack_into('<I',nso,0x3c,152*1024*1024)
        (exefs / "subsdk9").write_bytes(nso)
        budget_dir=self.root/"runtime/atmosphere/nro_patches/isaac-repentance-native-heap-budget";budget_dir.mkdir(parents=True)
        budget=(b"PATCH"+(0x8bf884).to_bytes(3,'big')+b"\0\4"+(240*1024*1024+0x9c02000).to_bytes(4,'little')+b"EOF")
        (budget_dir/"91C73FDD575061318D68886316AFEAC72388B2AB000000000000000000000000.ips").write_bytes(budget)
        (exefs / "main.npdm").write_bytes(b"fake-npdm")
        # 假运行时也要带"必需的中继补丁目录"：真实构建产物里每次都会生成它，
        # 打包工具现在**要求**它在（缺了就直接拒绝打包 —— 那是"EID 套装进度恒 0/3"的形态）。
        patch = (self.root / "runtime" / "atmosphere" / "nro_patches"
                 / "isaac-repentance-lifecycle-relay")
        patch.mkdir(parents=True)
        from tools.build_patches import EXPECTED_MODULE_ID, GAME_START_LIFECYCLE_RELAY_RECORDS
        from tools.nro_ips import encode_ips
        (patch / (EXPECTED_MODULE_ID.hex().upper() + '.ips')).write_bytes(
            encode_ips(GAME_START_LIFECYCLE_RELAY_RECORDS))
        cold = self.root / "runtime" / "atmosphere" / "nro_patches" / "isaac-repentance-static-callbacks"
        cold.mkdir(parents=True)
        (cold / "BUILDID0000000000000000000000000000000000000000000000000000000000.ips").write_bytes(b"fake-cold-ips")
        # 旧 IPS 后端遗留也放一份进假运行时：打包工具**不许**把它们带进包，
        # 下面有断言钉住这一点（带上去会让所有挂点失效）。
        for name in ("isaac-repentance-manager-update-relay",
                     "isaac-repentance-model-server-relay-not-a-real-name"):
            legacy = self.root / "runtime" / "atmosphere" / "nro_patches" / name
            legacy.mkdir(parents=True)
            (legacy / "legacy.ips").write_bytes(b"fake-legacy-ips")
        # ★ 2026-09-23（批次 077）：假运行时也要带 **romfs 覆盖层** —— 真实构建产物里
        # `mod-row-art` 每次都会写它，而打包工具现在把它当**硬要求**（缺了直接拒绝打包）。
        overlay = (self.root / "runtime" / "atmosphere" / "contents" / CONTENT_ID
                   / "romfs" / "rp_patch" / "resources.zh" / "gfx" / "ui" / "main menu")
        overlay.mkdir(parents=True)
        (overlay / "gamemenu.anm2").write_bytes(b"<AnimatedSprite/>")
        (overlay / "isaac-switch").mkdir()
        (overlay / "isaac-switch" / "mod_row_zh.pcx").write_bytes(b"PCX")

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

    def test_good_mod_packages_directory_scan_has_no_manifest(self):
        """按2026-10-01实际用户指令，扫描真实模组目录加载，不能重新生成已禁止的清单。"""
        first = self.make_mod("AlphaMod", 6, png_relative="resources/gfx/a.png")
        second = self.make_mod("BetaMod", 2, png_relative="resources-dlc3/gfx/b.png")
        result = self.run_tool(first, second, extra=("--drop-mod-pcx",))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        manifest_path = (self.root / "package" / "atmosphere" / "contents" / CONTENT_ID
                         / "romfs/isaac_mods/manifest.json")
        self.assertFalse(manifest_path.exists(), "按2026-10-01用户指令，manifest.json不应重新出现")
        mods = manifest_path.parent / "mods"
        self.assertEqual(sorted(p.name for p in mods.iterdir()), ["AlphaMod", "BetaMod"])
        self.assertTrue((mods / "AlphaMod" / "main.lua").is_file())
        self.assertTrue((mods / "BetaMod" / "main.lua").is_file())
        # `resources-dlc3` 层要**原样**带进包（层名不能改，改了覆盖语义就变）
        self.assertTrue((self.root / "package" / "atmosphere" / "contents" / CONTENT_ID
                         / "romfs/isaac_mods/mods/BetaMod/resources-dlc3/gfx/b.png").is_file())

    def test_cli_preserves_original_and_requires_external_patch_inputs(self):
        author = b"-- synthetic user input\r\nreturn true\r\n"
        mod = self.root / "WhatsMyDPS"
        mod.mkdir()
        (mod / "main.lua").write_bytes(author)
        destination = (self.root / "package/atmosphere/contents" / CONTENT_ID
                       / "romfs/isaac_mods/mods/WhatsMyDPS/main.lua")
        result = self.run_tool(mod)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(destination.read_bytes(), author)
        with patch.dict(os.environ, {"ISAAC_MOD_PATCH_ROOT": str(self.root / "missing-patches")}):
            result = self.run_tool(mod, extra=("--apply-mod-patches",))
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("ISAAC_MOD_PATCH_ROOT", result.stderr)
        self.assertEqual(destination.read_bytes(), author)
        self.assertEqual((mod / "main.lua").read_bytes(), author)

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
                         ["isaac-repentance-lifecycle-relay", "isaac-repentance-native-heap-budget", "isaac-repentance-static-callbacks"],
                         "包里必须保留lifecycle及加载前静态回调两份生产补丁，不带冻结诊断IPS")
        # 必需补丁的**文件**也要在（目录空着等于没带）
        self.assertTrue(any(p.suffix == ".ips" for p in
                            (patches / "isaac-repentance-lifecycle-relay").iterdir()))

    # ---- 2026-09-23（批次 077）：运行时那份 romfs 覆盖层必须进包 ------------------

    def test_package_ships_the_runtime_romfs_overlay(self):
        """包必须带**运行时构建树里的 romfs 覆盖层**（主菜单那一行「模组」的来源）。

        那一行是**引擎自己画的**：引擎那份菜单动画原本只有 12 层（Switch 版把 PC 本来就有的
        第 13 层 `Item6` 删了），构建的 `mod-row-art` 步骤把补好的 `gamemenu.anm2` 写进
        `romfs/rp_patch/…`。**包里缺了它 ⇒ 引擎只有 12 层 ⇒ 那一行退回我们自己画字** ——
        屏幕上仍有那一行，但不是真机验收过的原图（静默降级，最难查）。
        """
        mod = self.make_mod("AlphaMod", 6, png_relative="resources/gfx/a.png")
        result = self.run_tool(mod, extra=("--drop-mod-pcx",))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        romfs = self.root / "package" / "atmosphere" / "contents" / CONTENT_ID / "romfs"
        self.assertTrue((romfs / "rp_patch/resources.zh/gfx/ui/main menu/gamemenu.anm2").is_file(),
                        "覆盖层里的 gamemenu.anm2 必须进包（引擎画那一行全靠它）")
        self.assertTrue(
            (romfs / "rp_patch/resources.zh/gfx/ui/main menu/isaac-switch/mod_row_zh.pcx").is_file(),
            "覆盖层里的行贴图也要进包")
        # 合并语义：覆盖层与模组目录在同一个 `romfs/` 下，两边都要在（不许一边盖掉另一边）
        self.assertTrue((romfs / "isaac_mods/mods/AlphaMod/main.lua").is_file(),
                        "模组目录不能被覆盖层那一步冲掉")

    def test_missing_romfs_overlay_refuses_to_package(self):
        """运行时构建树里没有覆盖层 ⇒ **拒绝打包**（不是打个警告继续）。

        为什么要拒绝而不是警告：这一层的降级是静默的（引擎不画 ⇒ 我们自己画字），
        打出一个"看起来正常、其实不是验收形态"的包，比打包失败难查得多。
        """
        overlay_root = (self.root / "runtime" / "atmosphere" / "contents" / CONTENT_ID / "romfs")
        shutil.rmtree(overlay_root)
        mod = self.make_mod("AlphaMod", 6, png_relative="resources/gfx/a.png")
        result = self.run_tool(mod, extra=("--drop-mod-pcx",))
        self.assertNotEqual(result.returncode, 0, "缺覆盖层必须非零退出")
        combined = result.stdout + result.stderr
        self.assertIn("romfs 覆盖层", combined)

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

    def game_patch_bundle(self):
        from runtime.game_patches.build import build_bundle
        import os
        source = Path(os.environ.get('ISAAC_SOURCE_ROOT', ROOT))
        nro = next(source.glob('The Binding*Afterbirth*/*/1/.nro/Repentance.nro')).read_bytes()
        output = self.root / 'game-patches'
        build_bundle(nro, output)
        return output

    def test_explicit_game_patch_input_is_copied_separately_from_relays(self):
        bundle = self.game_patch_bundle()
        mod = self.make_mod('AlphaMod', 6, png_relative='resources/gfx/a.png')
        result = self.run_tool(mod, extra=('--drop-mod-pcx', '--game-patches', str(bundle)))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        patches = self.root / 'package/atmosphere/nro_patches'
        self.assertTrue((patches / 'isaac-repentance-loop-time-carry').is_dir())
        self.assertTrue((patches / 'isaac-repentance-lifecycle-relay').is_dir())
        self.assertTrue((self.root / 'package/game-patches.json').is_file())

    def test_game_patch_selection_is_independent_of_relay_selection(self):
        bundle = self.game_patch_bundle()
        mod = self.make_mod('AlphaMod', 6, png_relative='resources/gfx/a.png')
        result = self.run_tool(mod, extra=('--drop-mod-pcx', '--no-relay-patches',
                                           '--game-patches', str(bundle)))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        patches = self.root / 'package/atmosphere/nro_patches'
        self.assertEqual([p.name for p in patches.iterdir()], ['isaac-repentance-loop-time-carry'])

    def test_bad_game_patch_input_is_rejected_before_replacing_an_output(self):
        bundle = self.game_patch_bundle()
        next(bundle.rglob('*.ips')).write_bytes(b'bad patch')
        output = self.root / 'package'
        output.mkdir()
        marker = output / 'previous.txt'
        marker.write_text('preserve existing output')
        mod = self.make_mod('AlphaMod', 6, png_relative='resources/gfx/a.png')
        result = self.run_tool(mod, extra=('--drop-mod-pcx', '--game-patches', str(bundle)))
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn('cannot verify original-game patch bundle', result.stderr)
        self.assertEqual(marker.read_text(), 'preserve existing output')

    def test_mixed_legacy_runtime_is_rejected_before_replacing_output(self):
        from tools.build_patches import GAME_START_LIFECYCLE_RELAY_RECORDS
        from tools.nro_ips import encode_ips
        bundle = self.game_patch_bundle()
        lifecycle = next((self.root / 'runtime/atmosphere/nro_patches/isaac-repentance-lifecycle-relay').glob('*.ips'))
        lifecycle.write_bytes(encode_ips(GAME_START_LIFECYCLE_RELAY_RECORDS +
                                        [(0x4C08F4, bytes.fromhex('29496a1e'))]))
        mod = self.make_mod('AlphaMod', 6, png_relative='resources/gfx/a.png')
        output = self.root / 'package'
        for select_game_patches in (False, True):
            with self.subTest(game_patches=select_game_patches):
                output.mkdir(exist_ok=True)
                marker = output / 'previous.txt'
                marker.write_text('preserve existing output')
                options = ('--game-patches', str(bundle)) if select_game_patches else ()
                result = self.run_tool(mod, extra=('--drop-mod-pcx', *options))
                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                self.assertIn('重新构建', result.stderr)
                self.assertEqual(marker.read_text(), 'preserve existing output')


if __name__ == "__main__":
    unittest.main()
