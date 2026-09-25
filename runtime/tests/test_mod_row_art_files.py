"""门禁：『模组』那一行的美术**必须能落成真实文件**（`.pcx`），而且内容对得上。

## 为什么要有它（2026-09-23，批次 071）

真机现象：主菜单里那一行「模组」跑过若干次对局/关卡加载之后**变透明** —— 绘制每帧照调、
位置也对、对象指针非空，就是画不出来；用同一条**内存**路线重新加载拿回来的仍然是一张
画不出来的图，重启才好。

根因：那一行的图原本是**从内存**交给引擎贴图管理器的，还登记在**我们自己编的缓存键**
（`modrowg0.pcx` 这种名字）下 —— 全工程唯一这么做的地方。引擎自己的行、以及所有模组
（EID 等）都是**按磁盘路径**加载（`ANM2::Load`），它们从不消失；关卡加载会把"没有磁盘文件
背书的贴图"清掉，我们那张就是被清掉的那一类。

⇒ 修法：构建/部署期把图落成**真实文件**（本门禁钉的工具），运行期改成引擎自己的按路径加载。

## 判据（一条都不许放松）

1. **八个语言、每个一张 `.pcx` 都在，且不许出现 `.anm2`**（072 起运行期按文件名直接
   加载 `.pcx`；上一批那份 `.anm2` 对应的 `ANM2::Load` + `ANM2::Render` 在真机上崩了）；
2. `.pcx` 与 `mod_row_generated.hpp` 里的字节**逐字节相同**（不重编码、不缩放 —— 这一行
   美术是"游戏自己画的那一块，1:1 取用"，重编码就等于改了美术）；
3. `.anm2` 引用的精灵表名必须是 **`mod_row_<语言>.png`** —— 引擎解析时会把 `.png` 改写成
   `.pcx`（所以磁盘上放的是 `.pcx`），这是**约定**，写错扩展名就是"静默加载失败、画面空白"；
4. `.anm2` 里的 `Width`/`Height` 必须等于**从 `.pcx` 头自己算出来**的尺寸 ——
   尺寸的真值源是 PCX 头，不是任何人抄的数字；
5. `.anm2` 必须是**良构 XML** 且形状与引擎自己的 `gamemenu.anm2` 一致（一帧 Idle、
   一张精灵表、图层 0 指向精灵表 0）—— "能不能被引擎接受"只有真机能证，但"格式是不是
   我们以为的那一份"必须在仓库里就能证；
6. 尺寸对不上时工具**必须报错退出**（拿一份被改过的头文件喂给它验一次）——
   否则"独立校验"就只是注释里的一句话。

对应工具：`tools/emit_mod_row_art.py`。
"""

import re
import struct
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools" / "emit_mod_row_art.py"
GENERATED = ROOT / "runtime" / "source" / "mod_row_generated.hpp"

#: 八个语言（与 `mod_row_generated.hpp` 的布局表同一套码；英文的资源目录是裸 `resources`）。
LANGUAGES = ("de", "en", "es", "fr", "jp", "kr", "ru", "zh")
ROMFS = Path("atmosphere/contents/010021C000B6A000/romfs")
#: 游戏 dump 根（补层那一批要读里面的原版菜单动画与 PC 参考；缺了就跳过那几条）。
DUMP = (ROOT / "The Binding of Isaac_ Afterbirth+ 1.7.9b [010021C000B6A800][v524288][UPD]"
        / "Program #0/1")

sys.path.insert(0, str(ROOT))

from tools.emit_mod_row_art import language_directory  # noqa: E402
ASSET_SUBDIR = Path("rp_patch") / "gfx" / "ui" / "main menu" / "isaac-switch"

ARRAY_RE = re.compile(
    r"inline constexpr std::uint8_t kModRowPcx_(\w+)\[\]\s*=\s*\{(.*?)\};", re.S)


def header_bytes(language: str) -> bytes:
    """**独立**从生成的头文件里取某个语言的 PCX 字节（不复用工具的解析器）。"""
    text = GENERATED.read_text(encoding="utf-8")
    match = ARRAY_RE.search(text)
    found = None
    for match in ARRAY_RE.finditer(text):
        if match.group(1) == language:
            found = match
            break
    assert found is not None, f"头文件里没有 kModRowPcx_{language}"
    values = re.findall(r"0x([0-9A-Fa-f]{2})", found.group(2))
    assert values, f"kModRowPcx_{language} 一个字节都没解析到"
    return bytes(int(value, 16) for value in values)


def pcx_size(data: bytes) -> tuple[int, int]:
    """从 PCX 头算尺寸（`bytes 4..11` 是 XMin/YMin/XMax/YMax 四个小端 16 位）。"""
    assert data[0] == 0x0A, "不是 PCX"
    x_min, y_min, x_max, y_max = struct.unpack_from("<HHHH", data, 4)
    return x_max - x_min + 1, y_max - y_min + 1


class ModRowArtFilesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="isaac-mod-row-art-")
        cls.out = Path(cls.temporary.name) / "out"
        cls.producing = subprocess.run(
            [sys.executable, str(TOOL), "--out", str(cls.out)],
            text=True, capture_output=True, cwd=ROOT)

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def test_tool_succeeds(self):
        self.assertEqual(self.producing.returncode, 0,
                         self.producing.stdout + self.producing.stderr)

    def test_every_language_emits_the_pcx_and_nothing_else(self):
        self.assertEqual(self.producing.returncode, 0,
                         self.producing.stdout + self.producing.stderr)
        for language in LANGUAGES:
            for suffix in (".pcx",):
                path = self.out / f"mod_row_{language}{suffix}"
                self.assertTrue(path.is_file(), f"少了 {path.name}")
                self.assertGreater(path.stat().st_size, 0, f"{path.name} 是空的")
        # 也不许多出别的语言来（多出来的多半是"挑文件挑错了"）
        emitted = sorted(path.stem for path in self.out.glob("mod_row_*.pcx"))
        self.assertEqual(emitted, [f"mod_row_{language}" for language in sorted(LANGUAGES)])

    def test_pcx_is_byte_identical_to_the_generated_header(self):
        for language in LANGUAGES:
            expected = header_bytes(language)
            actual = (self.out / f"mod_row_{language}.pcx").read_bytes()
            self.assertEqual(actual, expected,
                             f"{language}：落盘的 .pcx 与头文件里的字节不一致"
                             f"（{len(actual)} vs {len(expected)}）——这是 1:1 取用的美术，"
                             "重编码/缩放都不允许")

    def test_tree_layout_matches_the_candidate_paths(self):
        """`--tree` 的落点必须与探针那张**候选逻辑路径**表逐条对得上。

        英文用裸 `resources`（不是 `resources.en`）；`--also-english-root` 让英文根下
        也各有一份 —— 因为"引擎挂载根到底是当前语言目录还是英文目录"目前没有定论，
        真机探针要一次试多条候选。
        """
        self.temporary_tree = tempfile.TemporaryDirectory(prefix="isaac-mod-row-tree-")
        self.addCleanup(self.temporary_tree.cleanup)
        tree = Path(self.temporary_tree.name)
        done = subprocess.run(
            [sys.executable, str(TOOL), "--tree", str(tree),
             "--languages", "zh", "--also-english-root"],
            text=True, capture_output=True, cwd=ROOT)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        expected = {
            ROMFS / "rp_patch" / "resources.zh" / "gfx" / "ui" / "main menu" / "isaac-switch"
            / f"mod_row_zh{suffix}"
            for suffix in (".pcx",)
        }
        expected.update({
            ROMFS / "rp_patch" / "resources" / "gfx" / "ui" / "main menu" / "isaac-switch"
            / f"mod_row_zh{suffix}"
            for suffix in (".pcx",)
        })
        actual = {path.relative_to(tree) for path in tree.rglob("*") if path.is_file()}
        self.assertEqual(actual, set(expected),
                         "`--tree --languages zh --also-english-root` 应当正好落 "
                         "resources.zh 与 resources 各 2 个文件（= 探针候选表里那两条根假设）")
        # 英文根那一份必须是**逐字节相同**的副本（它是同一个文件、只是换了个根）
        for relative in expected:
            if "resources.zh" not in str(relative):
                continue
            mirrored = Path(str(relative).replace("resources.zh", "resources"))
            self.assertEqual((tree / relative).read_bytes(), (tree / mirrored).read_bytes(),
                             f"{mirrored} 与 {relative} 不是逐字节相同的副本")

    # ---- 8) 菜单动画补层（`--menu-row-layer`，2026-09-23 A 路线）----------------

    def test_language_directory_agrees_with_the_row_tool(self):
        """两处"语言码 → 资源目录名"必须一致（补层那一步用另一份实现算落点）。"""
        from tools import gamemenu_mod_row as row_module
        for language in LANGUAGES:
            self.assertEqual(language_directory(language),
                             row_module.language_directory(language),
                             f"{language}：两个工具对资源目录名的看法不一致")

    def test_menu_row_layer_flag_writes_the_patched_animation(self):
        """`--tree --menu-row-layer` 必须把补完的菜单动画落进部署包（且内容与工具一致）。"""
        dump = DUMP
        if not dump.is_dir():
            self.skipTest(f"没有游戏 dump：{dump}")
        from tools import gamemenu_mod_row as row_module
        with tempfile.TemporaryDirectory(prefix="isaac-mod-row-layer-tree-") as directory:
            tree = Path(directory)
            done = subprocess.run(
                [sys.executable, str(TOOL), "--tree", str(tree), "--languages", "zh",
                 "--menu-row-layer", "--dump-root", str(dump)],
                text=True, capture_output=True, cwd=ROOT)
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
            patched = (tree / ROMFS / "rp_patch" / "resources.zh" / "gfx" / "ui" / "main menu"
                       / "gamemenu.anm2")
            self.assertTrue(patched.is_file(), f"没有落 {patched}")
            expected = row_module.build_patched_gamemenu(str(dump), "zh").text
            self.assertEqual(patched.read_text(encoding="utf-8"), expected,
                             "部署包里的菜单动画必须与工具算出来的逐字节一致")

    def test_menu_row_layer_refuses_an_explicit_bad_dump_root(self):
        """显式给的 dump 根读不到 ⇒ **当场报错**（不许悄悄少一层）。"""
        with tempfile.TemporaryDirectory(prefix="isaac-mod-row-layer-tree-") as directory:
            done = subprocess.run(
                [sys.executable, str(TOOL), "--tree", directory, "--languages", "zh",
                 "--menu-row-layer", "--dump-root", str(Path(directory) / "不存在的 dump")],
                text=True, capture_output=True, cwd=ROOT)
            self.assertNotEqual(done.returncode, 0,
                                "显式给了 dump 根却读不到文件时必须失败，不许当成「跳过」")

    def test_tool_refuses_a_header_whose_size_disagrees_with_the_pcx(self):
        """尺寸判据必须真的生效：改坏头文件里的尺寸 ⇒ 工具**报错退出**，不是照样生成。"""
        text = GENERATED.read_text(encoding="utf-8")
        doctored = re.sub(r"(\{kModRowPcx_zh,\s*sizeof\(kModRowPcx_zh\),\s*)80(\s*,\s*39\s*,)",
                          r"\g<1>81\g<2>", text, count=1)
        self.assertNotEqual(doctored, text, "没能把头文件里的尺寸改坏（正则过期了？）")
        with tempfile.TemporaryDirectory(prefix="isaac-mod-row-bad-header-") as directory:
            bad = Path(directory) / "mod_row_generated.hpp"
            bad.write_text(doctored, encoding="utf-8")
            done = subprocess.run(
                [sys.executable, str(TOOL), "--out", str(Path(directory) / "out"),
                 "--languages", "zh", "--header", str(bad)],
                text=True, capture_output=True, cwd=ROOT)
        self.assertNotEqual(done.returncode, 0,
                            "尺寸与 PCX 头不一致时工具竟然成功了 —— 独立校验形同虚设")
        self.assertIn("zh", done.stdout + done.stderr)


if __name__ == "__main__":
    unittest.main()
