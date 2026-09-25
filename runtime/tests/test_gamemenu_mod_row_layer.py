"""门禁：『模组』那一行必须**回到引擎自己的菜单动画里**，而不是我们另画一张图。

## 这一批为什么这么做（2026-09-23，用户定案：走原生那一套）

现象：那一行跑过一局之后变空白；引擎自己那五行从不消失。

机制（静态取证）：引擎自己的图层用 `ANM2::LayerState::SetSpriteSheet(SmartPointer<ImageBase>)`
持有**真正的引用计数**（`ImageManager::s_image_reference_freed` 就是管理器对"引用被释放"的反应），
而我们那份是 16 字节裸拷贝（`SmartPointerShim`，不加引用、也不释放）⇒ 管理器一放手，对象就被回收：
显存缓冲清零、而对象内存还看着正常 —— 与现场读数逐条吻合。⇒ 只要那一行**不是我们另外持有的一张图**，
这一类故障就不可能出现。

做法：**PC 版每个语言的菜单动画本来就有第六层 `Item6`**（`SpritesheetId=0`，一帧，
位置 `(201,139)`、轴心 `(16,16)`、从图集裁 `(195,475)` 的 `80×39`）；Switch 版把这层删了，
只有法语那份还留着。所以把这一层按 PC 的数值补回 Switch 的 `gamemenu.anm2`，由引擎自己画。

## 判据（一条都不许放松）

1. 补完的文件必须是"**原版 + 恰好两段**"：把插入的两段各自去掉一次之后，**逐字节**等于原版；
2. 插进去那一帧的数值必须**逐个**等于 PC 版同语言文件里 `Item6` 的那一帧（不许自己算）；
3. 原版已经有这一层时（法语）**不许动它**：不重复插入、也不改写游戏自己写的数值，
   并且要报出"已经有"这个事实（真机上表现为"这一层是游戏自己的"）；
4. 落点必须与挂载表一致：`rp_patch/resources.<语言>/gfx/ui/main menu/gamemenu.anm2`
   （英文是裸 `resources`）；
5. 缺原版、缺 PC 参考、或 PC 参考里没有那一层时**当场报错**，不许猜一个数值继续；
6. 补完的文件必须是**良构 XML**，且图层数比原版**恰好 +1**。
"""

import os
import re
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools" / "gamemenu_mod_row.py"
DUMP = (ROOT / "The Binding of Isaac_ Afterbirth+ 1.7.9b [010021C000B6A800][v524288][UPD]"
        / "Program #0/1")

sys.path.insert(0, str(ROOT))

from tools import gamemenu_mod_row as row  # noqa: E402

#: 补回去的那一层（PC 原版的名字与编号）。
LAYER_NAME = "Item6"
LAYER_ID = 12
#: PC 那一帧的**数值真值源**：位置/轴心/裁剪窗口。八个语言逐字段相同（已核）。
EXPECTED_FRAME = {
    "XPosition": "201", "YPosition": "139", "XPivot": "16", "YPivot": "16",
    "XCrop": "195", "YCrop": "475", "Width": "80", "Height": "39",
}
#: 原版**已经**有这一层的语言（Switch 的法语那份是 PC 的原件，没被删过）。
ALREADY_PRESENT = ("fr",)


def frame_attributes(text: str, layer_id: int) -> dict:
    """取某个图层在 `Idle` 动画里第一帧的属性（独立解析，不复用工具的写法）。"""
    match = re.search(r'<LayerAnimation LayerId="%d"[^>]*>(.*?)</LayerAnimation>' % layer_id,
                      text, re.S)
    assert match is not None, f"没有 LayerId={layer_id} 的 LayerAnimation"
    frame = re.search(r"<Frame\b[^>]*>", match.group(1))
    assert frame is not None, f"LayerId={layer_id} 里没有 Frame"
    return dict(re.findall(r'(\w+)="([^"]*)"', frame.group(0)))


def layer_names(text: str) -> list:
    return [dict(re.findall(r'(\w+)="([^"]*)"', tag)).get("Name")
            for tag in re.findall(r"<Layer\b[^>]*>", text)]


class GamemenuModRowLayerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not DUMP.is_dir():
            raise unittest.SkipTest(f"没有游戏 dump：{DUMP}")
        if not row.pc_menu_anm2_path("zh").is_file():
            raise unittest.SkipTest(f"没有 PC 参考资源：{row.PC_LANGUAGE_ROOT}")
        cls.restored = {language: row.build_patched_gamemenu(str(DUMP), language)
                        for language in row.LANGUAGE_ROOTS}
        cls.vanilla = {language: row.switch_menu_anm2_path(str(DUMP), language).read_text(
            encoding="utf-8") for language in row.LANGUAGE_ROOTS}

    # ---- 1) 补完的文件 = 原版 + 恰好两段 -------------------------------------

    def test_only_the_two_inserted_blocks_differ_from_the_vanilla_file(self):
        for language, restored in self.restored.items():
            if language in ALREADY_PRESENT:
                self.assertEqual(restored.text, self.vanilla[language],
                                 f"{language}：原版已经有这一层，文件必须一字不改")
                self.assertEqual(restored.inserted, (),
                                 f"{language}：没有插入就不该报「插入了什么」")
                continue
            text = restored.text
            self.assertEqual(len(restored.inserted), 2,
                             f"{language}：只允许插入两段（图层定义 + 动画帧）")
            for block in restored.inserted:
                self.assertEqual(text.count(block), 1,
                                 f"{language}：插入段必须在文件里唯一出现一次")
                text = text.replace(block, "", 1)
            self.assertEqual(text, self.vanilla[language],
                             f"{language}：去掉插入的两段之后必须逐字节等于原版")

    # ---- 2) 数值来自 PC 参考，不是我们算的 -----------------------------------

    def test_restored_frame_values_come_from_the_pc_reference(self):
        for language, restored in self.restored.items():
            self.assertEqual({key: restored.frame.get(key) for key in EXPECTED_FRAME},
                             EXPECTED_FRAME,
                             f"{language}：补回去那一帧的数值必须与 PC 的 Item6 一致")
            pc_frame = frame_attributes(row.pc_menu_anm2_path(language).read_text(
                encoding="utf-8"), LAYER_ID)
            self.assertEqual(restored.frame, pc_frame,
                             f"{language}：插进去那一帧必须逐个字段等于 PC 参考（不许自己算）")
            for key, value in EXPECTED_FRAME.items():
                self.assertEqual(pc_frame[key], value,
                                 f"{language}：PC 参考里的 {key} 与仓库里记的不一致")

    # ---- 3) 法语：游戏自己就有这一层，不许动 --------------------------------

    def test_languages_that_already_have_the_layer_are_left_untouched(self):
        for language in ALREADY_PRESENT:
            restored = self.restored[language]
            self.assertTrue(restored.already_present,
                            f"{language}：原版已有该层，必须报出这件事")
            self.assertEqual(restored.text, self.vanilla[language], f"{language}：不许改写")

    # ---- 4) 补完的文件是良构 XML，图层恰好 +1 --------------------------------

    def test_patched_file_is_well_formed_and_gains_exactly_one_layer(self):
        for language, restored in self.restored.items():
            before = layer_names(self.vanilla[language])
            after = layer_names(restored.text)
            self.assertEqual(after, before + ([LAYER_NAME] if language not in ALREADY_PRESENT
                                              else []),
                             f"{language}：图层顺序必须是「原来那些 + 我们这一层」")
            root = ET.fromstring(restored.text)
            layers = root.findall("./Content/Layers/Layer")
            self.assertEqual(len(layers), len(after), f"{language}：XML 里的图层数对不上")
            item6 = [tag for tag in layers if tag.get("Name") == LAYER_NAME]
            self.assertEqual(len(item6), 1, f"{language}：{LAYER_NAME} 必须恰好一层")
            self.assertEqual(item6[0].get("Id"), str(LAYER_ID), f"{language}：图层编号")
            self.assertEqual(item6[0].get("SpritesheetId"), "0",
                             f"{language}：必须用行图那张精灵表（与引擎自己那五行同一张）")

    def test_the_result_is_a_configuration_the_game_itself_ships(self):
        """补完之后那份文件，**标签与属性名**必须与法语原版（游戏自己那份 13 层）一模一样。

        为什么值得单独钉：这一层最终要被**引擎的 XML 解析器**吃下去，而"引擎认不认"在仓库里
        证不了；能证的是"我们造出来的形态，与游戏自己发售的那一份同形" —— 法语那份 Switch 资源
        本来就带 `Item6`（它就是 PC 的原件），是**同一套解析器接受的配置**。
        """
        def attribute_names(text: str) -> dict:
            skeleton: dict = {}
            for name, attributes in re.findall(r"<(\w+)\b([^>]*)>", text):
                names = tuple(sorted(re.findall(r'(\w+)=\s*"', attributes)))
                skeleton.setdefault(name, set()).add(names)
            return skeleton

        reference = attribute_names(self.vanilla["fr"])
        for language, restored in self.restored.items():
            skeleton = attribute_names(restored.text)
            for tag in ("Layer", "LayerAnimation", "Frame", "Spritesheet", "Animation"):
                self.assertEqual(skeleton.get(tag), reference.get(tag),
                                 f"{language}：<{tag}> 的属性名集合与游戏自己那份 13 层文件不一致")

    def test_animation_entry_is_appended_to_the_same_animation(self):
        for language, restored in self.restored.items():
            if language in ALREADY_PRESENT:
                continue
            anims = ET.fromstring(restored.text).findall("./Animations/Animation")
            self.assertEqual(len(anims), 1, f"{language}：这一页只有一个动画（Idle）")
            entries = anims[0].findall("./LayerAnimations/LayerAnimation")
            self.assertEqual(entries[-1].get("LayerId"), str(LAYER_ID),
                             f"{language}：新图层必须是**最后**一条（画在纸和字上面，与 PC 一致）")
            frames = entries[-1].findall("./Frame")
            self.assertEqual(len(frames), 1, f"{language}：补回去的图层只有一帧")

    # ---- 5) 缺东西时当场报错，不许猜 ----------------------------------------

    def test_refuses_when_the_vanilla_file_is_missing(self):
        with self.assertRaises(Exception):
            row.build_patched_gamemenu(str(DUMP / "不存在的目录"), "zh")

    def test_refuses_when_the_pc_reference_has_no_such_layer(self):
        vanilla = self.vanilla["zh"]
        pc_without = vanilla  # 拿一份"没有 Item6 的文件"冒充 PC 参考
        with self.assertRaises(Exception):
            row.restore_mods_row_layer(vanilla, pc_without, language="zh")

    def test_never_inserts_the_layer_twice(self):
        """已经补过的文件再喂进去 ⇒ 必须原样返回，**不许插第二层**（幂等）。

        （原版本来就有这一层的法语也走同一条路：`already_present`。）
        """
        for language in ("zh", "fr"):
            once = self.restored[language]
            again = row.restore_mods_row_layer(once.text, row.pc_menu_anm2_path(language).read_text(
                encoding="utf-8"), language=language)
            self.assertTrue(again.already_present, f"{language}：第二次必须认出「已经有」")
            self.assertEqual(again.inserted, (), f"{language}：第二次不许再插")
            self.assertEqual(again.text, once.text, f"{language}：第二次不许改一个字节")

    def test_refuses_when_the_existing_layer_has_the_wrong_id(self):
        """原版里那一层编号不对 ⇒ 报错（不猜、也不改写游戏自己的数值）。"""
        pc_text = row.pc_menu_anm2_path("zh").read_text(encoding="utf-8")
        broken = pc_text.replace('<Layer Name="Item6" Id="12"', '<Layer Name="Item6" Id="11"')
        self.assertNotEqual(broken, pc_text, "测试自己没改成（PC 参考的写法变了？）")
        with self.assertRaises(Exception):
            row.restore_mods_row_layer(broken, pc_text, language="zh")

    # ---- 6) 落点与挂载表一致 -------------------------------------------------

    def test_paths_follow_the_mount_table(self):
        self.assertEqual(row.switch_menu_anm2_path(str(DUMP), "zh"),
                         DUMP / "rp_patch" / "resources.zh" / "gfx" / "ui" / "main menu"
                         / "gamemenu.anm2")
        self.assertEqual(row.switch_menu_anm2_path(str(DUMP), "en"),
                         DUMP / "rp_patch" / "resources" / "gfx" / "ui" / "main menu"
                         / "gamemenu.anm2",
                         "英文的资源目录是裸 resources（与挂载表一致）")

    # ---- 7) 命令行：一次落七个语言（法语不需要） -----------------------------

    def test_cli_writes_one_file_per_language_that_needs_it(self):
        with tempfile.TemporaryDirectory(prefix="isaac-mod-row-layer-") as directory:
            out = Path(directory) / "rp_patch"
            producing = subprocess.run(
                [sys.executable, str(TOOL), "--dump-root", str(DUMP),
                 "--emit-menu-anm2", str(out)],
                text=True, capture_output=True, cwd=ROOT)
            self.assertEqual(producing.returncode, 0, producing.stdout + producing.stderr)
            written = sorted(p.relative_to(out).as_posix()
                             for p in out.rglob("gamemenu.anm2"))
            expected = sorted(
                f"{row.language_directory(language)}/gfx/ui/main menu/gamemenu.anm2"
                for language in row.LANGUAGE_ROOTS if language not in ALREADY_PRESENT)
            self.assertEqual(written, expected,
                             "只给「原版没有这一层」的语言落文件；法语原版就有，落了就是多余改动")
            for relative in written:
                language = relative.split("/")[0].replace("resources.", "").replace(
                    "resources", "en")
                self.assertEqual((out / relative).read_text(encoding="utf-8"),
                                 self.restored[language].text,
                                 f"{language}：落盘的内容必须与工具算出来的逐字节一致")

    def test_cli_refuses_to_write_when_the_dump_is_missing(self):
        with tempfile.TemporaryDirectory(prefix="isaac-mod-row-layer-") as directory:
            producing = subprocess.run(
                [sys.executable, str(TOOL), "--dump-root", str(Path(directory) / "空"),
                 "--emit-menu-anm2", str(Path(directory) / "out")],
                text=True, capture_output=True, cwd=ROOT)
            self.assertNotEqual(producing.returncode, 0,
                                "没有原版文件时必须报错退出，而不是落一份猜出来的文件")


if __name__ == "__main__":
    unittest.main()
