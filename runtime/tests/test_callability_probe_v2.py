"""门禁：可调用性探针必须**每条结论都不依赖屏幕**（v2 的四条通道不许退化）。

## 为什么要有它

2026-09-18 第一版探针（v1）在真机上"什么都没看到"，一轮设备验证就白跑了。原因是我们自己写错：

* v1 把 `reported = true` 放在绘制**之前**，函数开头又是 `if reported ... then return end`
  ⇒ 那行字**只在测量那一帧画了一次**（约 16 毫秒），屏幕上几乎不可能看到；
* 同一轮里，读数工具那句"画字 0 次 ⇒ **一个字都没画过**"又误导了判断 —— 那个计数只在
  `Font:DrawString*` 的**未缩放**分支里加，而 EID / q4-items / 探针用的都是缩放变体。

所以这条门禁钉住三件事：

1. 探针**每帧重画**（绘制调用必须在"一次性"判断之外）；
2. 探针有**不依赖屏幕**的回报通道：脚本一加载就往自己的模组存档写 `LOADED` 标记，
   测完写完整清单（`Mod:SaveData`，设备侧可从内存读回）；
3. 读数工具里"画字"那段不许再出现"一个字都没画过"这类**超出计数口径**的结论。

（与项目其它源码门禁同一形态：不做 Lua 解析，只做受控的文本提取。）
"""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GENERATOR = ROOT / "tools" / "gen_callability_probe.py"
READER = ROOT / "tools" / "read_device_state_via_gdb.py"


def newest_probe() -> Path:
    candidates = sorted((ROOT / "dist").glob("callability-probe-*/main.lua"))
    if not candidates:
        raise AssertionError("找不到生成出来的可调用性探针（dist/callability-probe-*/main.lua）")
    return candidates[-1]


class CallabilityProbeV2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.probe_text = newest_probe().read_text(encoding="utf-8")
        cls.generator_text = GENERATOR.read_text(encoding="utf-8")

    def test_probe_draws_on_every_frame_not_once(self) -> None:
        """绘制必须在"一次性"分支**之外**：`error(...)` 后面还要有 draw 调用。"""
        text = self.probe_text
        once = text.index("state.stage == 0 and state.frames >= 30")
        draw_call = text.index("draw('CALLPROBE alive", once)
        self.assertLess(once, draw_call,
                        "画字调用必须在'只测一次'的判断之后（每帧都会走到），否则又变成只画一帧")
        # v1 的形状（`if reported or frames < 30 then return end`）不许回来。
        self.assertNotIn("if reported or frames <", text)

    def test_probe_resolves_objects_without_load(self) -> None:
        """★ v2 的真机翻车点：`load('return ' .. 表达式)()` 编出来的 chunk 取不到全局
        （20 个 owner 全被跳过，连 `mod` 都拿不到）。所以解析必须**直接内联求值**，
        并且报告里要带上 `type(load)`、`type(Isaac)` 这类环境读数，便于一次分辨。"""
        text = self.probe_text
        self.assertIn("local function resolveObjects()", text)
        self.assertIn("return (Isaac.FindByType(20)[1]", text)
        # 除注释外不许出现 load(...) 求值（注释里那句是在记录这次翻车）。
        code = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("--"))
        self.assertNotIn("load('return '", code)
        self.assertIn("load=' .. type(load)", text)
        # 每个 owner 都要有"为什么没拿到"的原因（`nil` 与调用出错要分得开）。
        self.assertIn("call-error: ", text)

    def test_probe_measures_in_three_stages(self) -> None:
        """A（第 30 帧现场）、B（进局后量实体族）、C（房间里真出现拾取物时再量一次）。"""
        text = self.probe_text
        self.assertIn("runStage('A-early')", text)
        self.assertIn("runStage('B-in-game')", text)
        self.assertIn("runStage('C-pickup')", text)
        self.assertIn("CALLPROBE-B TIMEOUT", text)
        # A 阶段的报告必须记下"当时第几帧、在不在局内" —— 这才分得清
        # "标题画面没派发" 与 "画了看不见"。
        self.assertIn("'\\nframes=' .. tostring(state.frames) .. ' inGame='", text)

    def test_render_probe_lines_are_redrawn_every_frame(self) -> None:
        """★ 同一个毛病犯过两次：诊断文字只在"测量那一轮"画一次 ⇒ 屏幕上只闪一帧，
        于是"看不到"被误读成"画不出来"。这两行必须**每帧**重画，且**不受阶段分支影响**。"""
        text = self.probe_text
        # 画的那一份住在独立函数里，由 `check()` 无条件调用。
        self.assertIn("local function drawRenderProbeLines()", text)
        # 调用点必须在 `check()` 尾部（所有阶段分支之后）⇒ 每帧都会走到。
        self.assertGreater(text.rindex("drawRenderProbeLines()"),
                           text.index("state.tried.pickup"),
                           "每帧调用必须放在所有阶段分支之后")

    def test_render_scaled_text_probe_is_ascii_with_a_control_line(self) -> None:
        """★ v3 的坑：拿中文串测 `RenderScaledText`，而游戏自带字体没有中文字形 ⇒
        看不到不能作为反证。现在必须**纯 ASCII** 串，并且有一条"已知能显示"的对照行。"""
        text = self.probe_text
        line = next(l for l in text.splitlines() if l.startswith("local RST_LINE = "))
        self.assertTrue(all(ord(ch) < 128 for ch in line),
                        "RST_LINE 的文本必须是纯 ASCII（游戏自带字体没有中文字形）")
        self.assertIn("(ASCII)", line)
        # 标定行与 RST 标记都要在每帧绘制里被用到。
        block = text[text.index("local function drawRenderProbeLines()"):]
        block = block[:block.index("\nend")]
        self.assertIn("RST_LINE", block)
        self.assertIn("CALIBRATION_Y", block)
        # 标定表必须逐行写上自己的 y（否则"哪一行在哪"记录不下来）。
        self.assertIn("'Y=' .. tostring(y)", block)

    def test_probe_reports_through_mod_data(self) -> None:
        """通道②：模组存档。加载时一笔 `LOADED`，测完一笔完整清单。"""
        text = self.probe_text
        self.assertIn("mod:SaveData(text)", text)
        self.assertIn("'CALLPROBE v2 LOADED", text)
        # 加载标记必须**在**测量函数之外（chunk 顶层就写好），否则"回调没派发"又查不出来。
        load_marker = text.index("'CALLPROBE v2 LOADED")
        self.assertLess(load_marker, text.index("local function measure()"),
                        "加载标记要在测量函数之前写（否则回调没派发时什么都查不到）")

    def test_probe_tests_render_scaled_text_explicitly(self) -> None:
        """通道④：`Isaac.RenderScaledText` 要真的被调一次，并把结果画出来。"""
        text = self.probe_text
        self.assertIn("Isaac.RenderScaledText(RST_LINE, 400, 300,", text)
        self.assertIn("RenderScaledText: ", text)
        # 每个阶段的报告里都要带这一条（它回答"我们新写的默认字体绘制能不能画"）。
        self.assertIn("'\\nRenderScaledText=' .. renderTextResult", text)

    def test_probe_raises_once_per_stage(self) -> None:
        """通道③：每个阶段各抛一次（A/B/C），且不许每帧抛。"""
        self.assertEqual(self.probe_text.count("error(runStage("), 3)

    def test_probe_font_fallback_is_the_proven_path(self) -> None:
        """通道①：自己装字体、走缩放 UTF8 绘制（EID / q4-items 真机验证过的路径）。"""
        text = self.probe_text
        self.assertIn("DrawStringScaledUTF8", text)
        self.assertIn("'font/droid.fnt'", text)

    def test_reader_does_not_claim_more_than_the_counter_knows(self) -> None:
        """读数工具的"画字"结论不许超出计数口径（缩放变体没有计数点）。"""
        text = READER.read_text(encoding="utf-8")
        self.assertNotIn("一个字都没画过", text)
        self.assertIn("未缩放", text)

    def test_generator_and_probe_stay_in_sync(self) -> None:
        """探针是生成的：生成器里必须同样有这四条通道（否则一次重新生成就退化）。"""
        text = self.generator_text
        for needle in ("mod:SaveData(text)", "'CALLPROBE v2 LOADED", "DrawStringScaledUTF8",
                       "error(runStage(", "draw('CALLPROBE alive", "local function resolveObjects()",
                       "runStage('B-in-game')", "runStage('C-pickup')"):
            self.assertIn(needle, text, f"生成器模板里缺 {needle}")


class ModDataRecordDecoderTests(unittest.TestCase):
    """读数工具解模组数据记录的纯函数：格式按 `ModPersistence::detail::RecordAt`。"""

    @classmethod
    def setUpClass(cls) -> None:
        import importlib.util
        spec = importlib.util.spec_from_file_location("read_device_state_via_gdb", READER)
        cls.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.module)

    @staticmethod
    def record(namespace: int, key: int, value: bytes) -> bytes:
        header = (namespace.to_bytes(8, "little") + key.to_bytes(8, "little") + bytes([1, 0, 0, 0])
                  + len(value).to_bytes(4, "little"))
        return header + value

    def test_decodes_two_records_in_order(self) -> None:
        payload = self.record(0x11, 0x6D6F642D64617461, b"CALLPROBE v2 LOADED font=font/droid.fnt") \
            + self.record(0x22, 0x6D6F642D64617461, b"CALLPROBE miss=0 skipped=3")
        records = self.module.decode_mod_data_records(payload)
        self.assertEqual([r["namespace"] for r in records], [0x11, 0x22])
        self.assertEqual(records[1]["value"], b"CALLPROBE miss=0 skipped=3")

    def test_stops_on_truncated_tail(self) -> None:
        payload = self.record(0x11, 0x1, b"OK") + b"\x00" * 8
        self.assertEqual(len(self.module.decode_mod_data_records(payload)), 1)

    def test_binary_value_is_not_forced_into_text(self) -> None:
        self.assertIsNone(self.module.printable_text(b"\x00\x01\x02"))
        self.assertEqual(self.module.printable_text(b"a\nb"), "a\nb")


if __name__ == "__main__":
    unittest.main()
