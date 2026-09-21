"""门禁：**下载来的模组体检工具**（`tools/screen_resource_mod.py`）的判据本身。

## 为什么有这条门禁（2026-09-21）

用户要自己下载第三方模组丢进 `mods/` 试用，而"下载来的东西"有三种形状、两条会**静默失败**的路：

1. **形状**：创意工坊风格（根目录有 `resources/`）/ Switch LayeredFS 覆盖包（`atmosphere/contents/<title>/romfs/`）/
   GitHub 多套一层。我们只认第一种，其余必须先剥壳 —— 剥错就会"拷进去了但什么都没变"。
2. **贴图格式**：贴图桥只支持 8 位非隔行的色彩类型 0/2/4/6；**调色板 PNG（类型 3）转不了**，
   真机上就是"这张图不显示、也不报错"。
3. **路径**：模组里的相对路径在本体资源里没有同名文件 ⇒ 引擎永远不会读它，等于白装。

三条都必须**在拷上卡之前**说清楚。这条门禁用 `--game-resources` 指向一个自造的本体资源树，
所以不依赖仓库里那份带空格和 `#` 的真实资源包（跑得快、也不受它是否存在影响）。
"""

import struct
import subprocess
import sys
import tempfile
import unittest
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools" / "screen_resource_mod.py"


def make_png(width: int, height: int, color_type: int, *, bit_depth: int = 8, interlace: int = 0) -> bytes:
    """造一张最小 PNG（只求文件头与 IHDR 合法，内容全 0）。"""
    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[color_type]
    raw = b"".join(b"\x00" + bytes(width * channels) for _ in range(height))

    def chunk(kind: bytes, payload: bytes) -> bytes:
        return (
            struct.pack(">I", len(payload))
            + kind
            + payload
            + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)
        )

    ihdr = struct.pack(">IIBBBBB", width, height, bit_depth, color_type, 0, 0, interlace)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )


class ScreenResourceModTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.root = Path(self._temp.name)
        # 自造的"本体资源"：只要一个物品图，用来验"路径对不对得上"。
        vanilla = self.root / "vanilla" / "resources" / "gfx" / "items" / "collectibles"
        vanilla.mkdir(parents=True)
        (vanilla / "collectibles_001_thesadonion.pcx").write_bytes(b"pcx-ish")

    def tearDown(self) -> None:
        self._temp.cleanup()

    def run_tool(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(TOOL), *args, "--game-resources", str(self.root / "vanilla" / "resources")],
            capture_output=True,
            text=True,
            cwd=ROOT,
        )

    def make_workshop_mod(self, name: str = "MyResprite") -> Path:
        mod = self.root / name
        collectibles = mod / "resources" / "gfx" / "items" / "collectibles"
        collectibles.mkdir(parents=True)
        (collectibles / "collectibles_001_thesadonion.png").write_bytes(make_png(32, 32, 6))
        (mod / "metadata.xml").write_text("<metadata/>", encoding="utf-8")
        return mod

    # ---- 形状 ----

    def test_dlc3_layer_only_mod_is_recognised_and_keeps_its_layer(self):
        """★ 只带 `resources-dlc3/` 的模组（PC 忏悔层）必须是"认得的形状"，且**层名留在原地**。

        实例就是 `visible tinted rocks`：整包 23 张 `gfx/grid/rocks_*.png` 都在 `resources-dlc3/` 下。
        改前这个工具把它判成"缺 resources/ 外壳"、铺盘时整层塞进 `resources/`（层放错）；
        运行时代码侧同时也**从来没挂过那一层**（补 `kLeaves` 见
        `runtime/tests/integration/test_content_mount_service.py`）。
        """
        mod = self.root / "TintedRocks"
        grid = mod / "resources-dlc3" / "gfx" / "grid"
        grid.mkdir(parents=True)
        (grid / "rocks_basement.png").write_bytes(make_png(32, 32, 6))
        (mod / "metadata.xml").write_text("<metadata/>", encoding="utf-8")
        mods = self.root / "card-mods"

        result = self.run_tool(str(mod), "--install-to", str(mods), "--name", "TintedRocks")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("resources-dlc3", result.stdout)
        self.assertNotIn("缺 resources/ 外壳", result.stdout)
        self.assertTrue((mods / "TintedRocks" / "resources-dlc3" / "gfx" / "grid"
                         / "rocks_basement.png").is_file())
        # 不许把它套进 resources/ 里（那是一条永远读不到的路径）。
        self.assertFalse((mods / "TintedRocks" / "resources" / "resources-dlc3").exists())

    def test_install_preserves_every_layer_including_content(self):
        """带 `resources/` + `resources-dlc3/` + `content/` 的模组：三层都要原样落盘。

        `content/`（模组 XML 层）以前会被**静默丢掉**（铺盘只拷 `resources/` 与根文件），
        而运行时是挂 `content` 的 ⇒ 那类模组的 XML 改动会"装了但没生效"。
        """
        mod = self.make_workshop_mod("Layered")
        dlc3 = mod / "resources-dlc3" / "gfx" / "items" / "collectibles"
        dlc3.mkdir(parents=True)
        (dlc3 / "collectibles_001_thesadonion.png").write_bytes(make_png(32, 32, 6))
        content = mod / "content"
        content.mkdir()
        (content / "entities2.xml").write_text("<entities/>", encoding="utf-8")
        mods = self.root / "card-mods"

        result = self.run_tool(str(mod), "--install-to", str(mods), "--name", "Layered")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        installed = mods / "Layered"
        self.assertTrue((installed / "resources" / "gfx" / "items" / "collectibles"
                         / "collectibles_001_thesadonion.png").is_file())
        self.assertTrue((installed / "resources-dlc3" / "gfx" / "items" / "collectibles"
                         / "collectibles_001_thesadonion.png").is_file())
        self.assertTrue((installed / "content" / "entities2.xml").is_file())

    def test_workshop_shape_passes(self):
        mod = self.make_workshop_mod()
        result = self.run_tool(str(mod))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("创意工坊风格", result.stdout)
        self.assertIn("纯资源 ✓", result.stdout)
        self.assertIn("可以直接放进 mods/", result.stdout)
        # 本体里真有这张图的同名 .pcx ⇒ 不该报"路径对不上"。
        self.assertNotIn("路径对不上", result.stdout)

    def test_layeredfs_shape_is_unwrapped_to_base_title(self):
        for title in ("010021C000B6A000", "010021C000B6B001"):
            directory = (
                self.root / "pack" / "atmosphere" / "contents" / title / "romfs"
                / "resources" / "gfx" / "items" / "collectibles"
            )
            directory.mkdir(parents=True)
            (directory / "collectibles_001_thesadonion.png").write_bytes(make_png(8, 8, 6))
        result = self.run_tool(str(self.root / "pack"))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("LayeredFS", result.stdout)
        self.assertIn("010021C000B6A000", result.stdout)
        # 另一份 romfs 里的内容不能被静默丢掉 —— 必须在报告里点名。
        self.assertIn("010021C000B6B001", result.stdout)

    def test_github_extra_directory_is_descended(self):
        mod = self.make_workshop_mod("repo-main")
        nested = self.root / "archive" / "repo-main"
        nested.parent.mkdir(parents=True, exist_ok=True)
        mod.rename(nested)
        result = self.run_tool(str(self.root / "archive"))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("创意工坊风格", result.stdout)

    def test_unknown_shape_is_rejected(self):
        stray = self.root / "stray"
        stray.mkdir()
        (stray / "readme.txt").write_text("nothing here", encoding="utf-8")
        result = self.run_tool(str(stray))
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("认不出这是什么形状", result.stderr + result.stdout)

    # ---- 贴图格式 ----

    def test_palette_png_blocks(self):
        mod = self.root / "palette"
        directory = mod / "resources" / "gfx" / "ui"
        directory.mkdir(parents=True)
        (directory / "hud.png").write_bytes(make_png(16, 16, 3))
        result = self.run_tool(str(mod))
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("调色板(P) —— 不支持", result.stdout)
        self.assertIn("有会静默失败的东西", result.stdout)

    def test_interlaced_and_16bit_png_block(self):
        mod = self.root / "weird"
        directory = mod / "resources" / "gfx" / "ui"
        directory.mkdir(parents=True)
        (directory / "a.png").write_bytes(make_png(8, 8, 2, bit_depth=16))
        (directory / "b.png").write_bytes(make_png(8, 8, 2, interlace=1))
        result = self.run_tool(str(mod))
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("只支持 8 位非隔行", result.stdout)
        # 两张都该被点名（不能只说第一张）。
        self.assertIn("a.png", result.stdout)
        self.assertIn("b.png", result.stdout)

    def test_supported_color_types_pass(self):
        mod = self.root / "oktypes"
        directory = mod / "resources" / "gfx" / "ui"
        directory.mkdir(parents=True)
        for index, color_type in enumerate((0, 2, 4, 6)):
            (directory / f"t{index}.png").write_bytes(make_png(4, 4, color_type))
        result = self.run_tool(str(mod))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("能转 4 张，转不了 0 张", result.stdout)

    # ---- Lua ----

    def test_main_lua_is_reported_as_not_pure_resource(self):
        mod = self.make_workshop_mod()
        (mod / "main.lua").write_text("-- whatever\n", encoding="utf-8")
        result = self.run_tool(str(mod))
        self.assertIn("不是纯资源", result.stdout)

    # ---- 路径对不上 ----

    def test_unknown_target_file_is_reported(self):
        mod = self.make_workshop_mod()
        (mod / "resources" / "gfx" / "items" / "collectibles" / "collectibles_999_ghost.png").write_bytes(
            make_png(4, 4, 6)
        )
        result = self.run_tool(str(mod))
        self.assertIn("collectibles_999_ghost.png", result.stdout)
        self.assertNotIn("collectibles_001_thesadonion.png —— 本体资源里没有", result.stdout)

    def test_multiple_game_resource_roots_are_merged(self):
        """★ 本体 + 忏悔补丁是**两份**资源（补丁在 `rp_patch/resources/`）。

        只比对本体那份，会把所有"忏悔才有"的文件误报成"路径对不上"
        （本体道具编号只到 552，补丁里有到 716 的）—— 这里钉住"合并比对"。
        """
        patch = self.root / "vanilla" / "rp_patch" / "resources" / "gfx" / "items" / "collectibles"
        patch.mkdir(parents=True)
        (patch / "collectibles_716_keeperssack.pcx").write_bytes(b"pcx-ish")

        mod = self.root / "patchonly"
        directory = mod / "resources" / "gfx" / "items" / "collectibles"
        directory.mkdir(parents=True)
        (directory / "collectibles_716_keeperssack.png").write_bytes(make_png(4, 4, 6))

        result = subprocess.run(
            [
                sys.executable,
                str(TOOL),
                str(mod),
                "--game-resources",
                str(self.root / "vanilla" / "resources"),
                "--game-resources",
                str(self.root / "vanilla" / "rp_patch" / "resources"),
            ],
            capture_output=True,
            text=True,
            cwd=ROOT,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn("路径对不上", result.stdout)

        # 只给本体那份时，它就该被点名（证明这条检查真的在比东西，而不是永远不报）。
        only_base = self.run_tool(str(mod))
        self.assertIn("collectibles_716_keeperssack.png", only_base.stdout)

    # ---- 铺盘 ----

    def test_install_unwraps_layeredfs_into_resources(self):
        source = self.root / "pack2"
        directory = (
            source / "atmosphere" / "contents" / "010021C000B6A000" / "romfs"
            / "resources" / "gfx" / "items" / "collectibles"
        )
        directory.mkdir(parents=True)
        (directory / "collectibles_001_thesadonion.png").write_bytes(make_png(8, 8, 6))
        mods = self.root / "card-mods"
        result = self.run_tool(str(source), "--install-to", str(mods), "--name", "pack2")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        installed = mods / "pack2" / "resources" / "gfx" / "items" / "collectibles"
        self.assertTrue((installed / "collectibles_001_thesadonion.png").is_file())

    def test_install_keeps_root_files_and_refuses_to_overwrite(self):
        mod = self.make_workshop_mod()
        mods = self.root / "card-mods"
        first = self.run_tool(str(mod), "--install-to", str(mods), "--name", "MyResprite")
        self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
        self.assertTrue((mods / "MyResprite" / "metadata.xml").is_file())
        self.assertTrue((mods / "MyResprite" / "resources" / "gfx" / "items" / "collectibles").is_dir())

        again = self.run_tool(str(mod), "--install-to", str(mods), "--name", "MyResprite")
        self.assertEqual(again.returncode, 2, again.stdout + again.stderr)
        self.assertIn("已存在", again.stdout + again.stderr)

    def test_zip_source_uses_archive_name_for_default_directory(self):
        mod = self.make_workshop_mod("Zipped")
        archive = self.root / "Zipped.zip"
        with __import__("zipfile").ZipFile(archive, "w") as bundle:
            bundle.write(mod / "metadata.xml", "Zipped/metadata.xml")
            bundle.write(
                mod / "resources" / "gfx" / "items" / "collectibles" / "collectibles_001_thesadonion.png",
                "Zipped/resources/gfx/items/collectibles/collectibles_001_thesadonion.png",
            )
        mods = self.root / "card-mods"
        result = self.run_tool(str(archive), "--install-to", str(mods))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("模组      Zipped.zip", result.stdout)
        self.assertTrue((mods / "Zipped" / "resources" / "gfx" / "items" / "collectibles").is_dir())


if __name__ == "__main__":
    unittest.main()
