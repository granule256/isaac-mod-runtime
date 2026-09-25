"""门禁：那一行**由引擎自己画**时，我们不许再画一遍；而且判据必须是"引擎怎么看层数"。

## 这一批（2026-09-23，批次 075，用户定案 A 路线）

现象：主菜单里那一行「模组」跑过一局之后变空白，引擎自己那五行从不消失。

机制：引擎自己的图层用 `ANM2::LayerState::SetSpriteSheet(SmartPointer<ImageBase>)` 持有
**真正的引用计数**；我们那份是 16 字节裸拷贝（`SmartPointerShim`：不加引用、也不释放）
⇒ 管理器一放手，对象就被回收（显存缓冲清零、对象内存还看着正常）—— 与现场读数逐条吻合。

做法：PC 版每个语言的菜单动画**本来就有**第六层 `Item6`（Switch 版删掉了，只有法语留着），
把它按 PC 的数值补回 `gamemenu.anm2`（`tools/gamemenu_mod_row.py --emit-menu-anm2`）
⇒ 那一行由引擎自己的整页渲染画出来，生命周期与其余五行同源。

## 判据（一条都不许放松）

1. **判"有没有那一层"只能读图层数**（`ANM2+0xB0`）：`ANM2::GetLayer(int)` 越界时**不返回空指针**
   （它打一条日志后照样算出界地址）⇒ 用"`GetLayer(12)` 是不是空"来判就是读越界内存。
   这条判据既钉代码、也钉注释里那句警告（不然下一个人还会这么写）；
2. **有那一层时绝不再画**：回调里必须先判、再 `return`，`ModRowDrawSprite` 只能出现在它之后；
3. 兜底那条路**必须原样保留**（没有那一层时行为与上一批一字不变）—— 覆盖层没装/被回退时，
   那一行不能又变回"整行消失"；
4. 探针里那个层数常量必须等于**补层工具真做出来的文件**的层数（两处各写一个数字 = 迟早错位）；
5. 这条判据必须在读数里看得见：`.cpp` / `.hpp` / 读数工具三处都有 [109] 的解释。
"""

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROBE = ROOT / "runtime" / "source" / "probe" / "native_mods_menu_probe.cpp"
HPP = ROOT / "runtime" / "source" / "probe" / "native_mods_menu_probe.hpp"
READER = ROOT / "tools" / "read_device_state_via_gdb.py"
DUMP = (ROOT / "The Binding of Isaac_ Afterbirth+ 1.7.9b [010021C000B6A800][v524288][UPD]"
        / "Program #0/1")

sys.path.insert(0, str(ROOT))


def function_body(text: str, signature: str) -> str:
    """取一个函数的函数体（从签名起、到下一个顶格的 `}` 为止）。"""
    assert signature in text, f"没找到 {signature}"
    return text.split(signature, 1)[1].split("\n}\n", 1)[0]


class ProbeModRowNativeLayerTests(unittest.TestCase):
    # ---- 1) 判据必须是图层数，不是 `GetLayer` 的空指针 ------------------------

    def test_layer_presence_is_read_from_the_layer_count(self):
        text = PROBE.read_text(encoding="utf-8")
        self.assertIn("kAnm2LayerCountOffset", text, "必须有一个「图层数在 ANM2 里哪个偏移」的常量")
        body = function_body(text, "bool ModRowHasNativeLayer")
        self.assertIn("kAnm2LayerCountOffset", body, "判定函数必须读图层数")
        self.assertNotIn("getLayer(", body,
                         "不许用 `GetLayer(12)` 判有没有那一层：它越界时返回的是出界地址")
        self.assertIn("kMenuGameLayerCountWithModRow", body, "阈值要有名字、不许写魔数")

    def test_the_getlayer_trap_is_written_down_next_to_the_constant(self):
        """把「`GetLayer` 越界不返回空」这件事写在常量旁边 —— 不然下一个人还会那样写。"""
        text = PROBE.read_text(encoding="utf-8")
        anchor = text.index("kAnm2LayerCountOffset = ")
        window = text[max(0, anchor - 1200):anchor + 400]
        self.assertIn("GetLayer", window, "常量旁边要提到 `GetLayer` 这个坑")
        self.assertIn("空指针", window, "要说清「越界时不返回空指针」这件事")

    # ---- 2) 有那一层时不再自己画 --------------------------------------------

    def test_the_relay_skips_its_own_drawing_when_the_engine_draws_it(self):
        body = function_body(PROBE.read_text(encoding="utf-8"),
                             'extern "C" void ModRowMenuGameRenderRelayCallback')
        self.assertIn("ModRowHasNativeLayer", body, "回调里必须问一次「引擎那份动画有没有这一层」")
        self.assertIn("if (nativeLayer)", body, "有那一层时必须走单独的分支")
        native_branch = body.split("if (nativeLayer)", 1)[1].split("}", 1)[0]
        self.assertIn("return", native_branch, "有那一层时这一帧不再画我们自己的东西")
        self.assertLess(body.index("ModRowHasNativeLayer"), body.index("ModRowDrawSprite"),
                        "必须先判、后画（顺序反了就等于画两遍）")
        self.assertLess(body.index("if (nativeLayer)"), body.index("ModRowDrawSprite"),
                        "我们的绘制必须排在那个分支**之后**")

    def test_the_fallback_drawing_path_is_still_there(self):
        text = PROBE.read_text(encoding="utf-8")
        self.assertIn("bool ModRowDrawSprite", text, "兜底绘制必须原样保留")
        self.assertIn("ModRowDrawLabel", text, "画字那条最后兜底也必须保留")
        body = function_body(text, 'extern "C" void ModRowMenuGameRenderRelayCallback')
        self.assertIn("if (!ModRowDrawSprite(", body,
                      "兜底仍然是「贴图拿不到就画字」这个次序（072 的纪律不变）")

    # ---- 3) 层数常量必须与补层工具真做出来的文件一致 -------------------------

    def test_the_expected_layer_count_matches_the_patched_file(self):
        if not DUMP.is_dir():
            self.skipTest(f"没有游戏 dump：{DUMP}")
        from tools import gamemenu_mod_row as row_module
        if not row_module.pc_menu_anm2_path("zh").is_file():
            self.skipTest(f"没有 PC 参考资源：{row_module.PC_LANGUAGE_ROOT}")
        text = PROBE.read_text(encoding="utf-8")
        constant = re.search(r"kMenuGameLayerCountWithModRow\s*=\s*(\d+)", text)
        self.assertIsNotNone(constant, "探针里没有层数常量")
        expected = int(constant.group(1))
        patched = row_module.build_patched_gamemenu(str(DUMP), "zh").text
        layers = len(re.findall(r"<Layer\b[^>]*>", patched))
        self.assertEqual(layers, expected,
                         f"补层工具做出来的文件有 {layers} 层，而探针按 {expected} 层判"
                         "（两处各写一个数字 = 迟早错位）")
        vanilla = row_module.switch_menu_anm2_path(str(DUMP), "zh").read_text(encoding="utf-8")
        self.assertEqual(len(re.findall(r"<Layer\b[^>]*>", vanilla)) + 1, expected,
                         "补层只加一层（原版层数 + 1 必须等于那个常量）")

    # ---- 4) 判据在读数里看得见 ----------------------------------------------

    def test_the_build_step_ships_the_layer_and_says_so_when_it_cannot(self):
        """构建必须**带上这一层**；dump 找不到时要说清后果，而不是悄悄少一层。"""
        makefile = (ROOT / "runtime" / "Makefile").read_text(encoding="utf-8")
        target = makefile.split("mod-row-art: $(BUILD)", 1)[1].split("\n\n", 1)[0]
        self.assertIn("--menu-row-layer", target, "构建步骤必须把这一层打进部署包")
        self.assertIn("--dump-root", target, "补层要读 dump 里的原版与 PC 参考")
        self.assertIn("MOD_ROW_DUMP_ROOT", target, "dump 根要能覆盖（换机器时路径不同）")
        self.assertRegex(makefile, r"MOD_ROW_DUMP_ROOT\s*\?=\s*auto",
                         "默认必须是通配发现（目录名在 Docker 里打不开，见工具注释）")
        tool = (ROOT / "tools" / "emit_mod_row_art.py").read_text(encoding="utf-8")
        self.assertIn("跳过", tool, "找不到 dump 时工具要明说「跳过」")
        self.assertIn("[109]", tool, "还要说清后果（读数 [109] = 2，那一行退回兜底绘制）")

    def test_dump_discovery_does_not_hardcode_the_directory_name(self):
        """dump 根必须**按通配发现**：那个目录名在 Docker Desktop 里用字面量打不开。"""
        from tools import gamemenu_mod_row as row_module
        self.assertIsNone(row_module.discover_dump_root("/nonexistent-repo-root"),
                          "找不到就要返回 None（不许猜一个路径继续）")
        if not DUMP.is_dir():
            self.skipTest(f"没有游戏 dump：{DUMP}")
        found = row_module.discover_dump_root(str(ROOT))
        self.assertIsNotNone(found, "仓库里明明有 dump，通配却没找到")
        self.assertTrue((Path(found) / "rp_patch").is_dir(),
                        f"通配找到的根不对：{found}（应当是 `Program #0/1` 那一层）")

    def test_the_judgement_is_visible_in_the_diagnostics(self):
        probe = PROBE.read_text(encoding="utf-8")
        hpp = HPP.read_text(encoding="utf-8")
        reader = READER.read_text(encoding="utf-8")
        self.assertIn("modRowNativeLayer", probe, "探针状态里要有这一格")
        self.assertIn("modRowNativeLayer", hpp, ".hpp 的说明里也要有（两处必须一致）")
        self.assertIn("modRowNativeLayer", reader, "读数工具要按名字解释它")
        self.assertIn("[109]", reader, "读数里要打出行号，便于现场核对")


if __name__ == "__main__":
    unittest.main()
