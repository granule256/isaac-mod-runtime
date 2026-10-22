"""游戏控制台那套设施的门禁（批次 121）。

## 为什么要有它

控制台这条路**在宿主上碰不到引擎**，但它里面有几件事**必须离线就能判**，而且判错的后果都不轻：

1. **宽字符转换**：引擎那两个软键盘回调收的是 `wchar_t const*`，而本平台 `wchar_t` 是
   **4 字节**（游戏自己那份实现在 `Menu_Character::VirtualKeyboardUpdate @ 0x4039A4` 里按
   `ldr w0,[x21,x24,lsl #2]` 取元素）。按 16 位读会把每个 ASCII 字符拆成"字符 + NUL"，
   第一个 NUL 就让整串变空 —— 现象是"打了字却什么都没发生"，不报错、不崩，最难查。
2. **跨模块字符串布局**：引擎那份 libc++ 用**经典**布局（短串数据在 `+1`、长度在首字节的高位；
   长串 `+0` 是容量且低 1 位为 1、`+8` 长度、`+0x10` 数据指针），而**宿主/新版 libc++ 不是这一套**
   （实测短串数据在 `+0`）。所以命令串是我们**手工拼的 24 字节**，拼错就是让引擎读一段垃圾。
3. **输出行缓冲**：环形、按 `\n` 切行、单行截断 —— 这些错了在真机上只表现为"屏幕上少一行"。

判据都是**行为**（不是源码文本）。另有一条结构性判据：状态面字段数与读数工具的读取宽度
**必须是同一个数**（18 个 u32 = 9 个字）—— 这类"两处各写一份数字"的地方本项目栽过不止一次。
"""

import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "runtime" / "source"
BRIDGE = ROOT / "runtime" / "src" / "infrastructure" / "console" / "console_bridge.hpp"
READER = ROOT / "tools" / "read_device_state_via_gdb.py"


def host_compilers() -> tuple[str, str] | None:
    """(C 编译器, C++ 编译器)；缺任何一个就整体 skip，不伪装成通过。"""
    cc = shutil.which("cc")
    if cc is None:
        return None
    for candidate in ("c++", "clang++", "g++"):
        found = shutil.which(candidate)
        if found is not None:
            return cc, found
    return None


HARNESS = r'''
#include "domain/console/console_text.hpp"
#include "infrastructure/console/console_bridge.hpp"
// 会话头（每帧点 + 自绘）也拉进来：它只有真机编译才会暴露语法/类型错误，
// 而这次改动（批次 123 的覆盖层参数与右对齐）全在它里面 ⇒ 宿主编译一遍是最便宜的保险。
#include "infrastructure/console/console_session.hpp"

#include <cstdint>
#include <cstdio>
#include <cstring>
#include <string_view>

namespace console = isaac::runtime::console;

namespace {

int g_Failures = 0;

void check(bool condition, const char* name) {
    if (!condition) {
        ++g_Failures;
        std::printf("CONSOLE_FAIL %s\n", name);
    }
}

std::size_t Utf8(const std::uint32_t* text, char* out, std::size_t capacity) {
    return console::Utf32ToUtf8(text, kVirtualKeyboardTextCapacity, out, capacity);
}

} // namespace

int main() {
    // ---- 0) 覆盖层参数：用户要求的"看到就行"（批次 123）----
    // 这三条是**用户口径**，不是技术推导出来的：3 秒（180 帧 @60fps）、字要小、位置在顶部。
    {
        check(console::kOverlayHoldFrames == 180, "overlay-hold-is-3-seconds");
        check(console::kOverlayScale <= 1.0F, "overlay-scale-shrunk");
        check(console::kOverlayTopMargin < 100.0F, "overlay-sits-at-the-top");
        check(console::kOverlayFallbackScreenWidth > 100.0F, "overlay-fallback-width-sane");
    }
    // ---- 0b) 总开关的状态文件（批次 124）----
    // ★ 最要紧的一条是这个开关的 **fail-open 方向**：读不懂 / 文件不在 / 读失败 ⇒ 一律当**开**。
    //   为什么（与污染标记那条方向相反）：不能因为读一个状态文件失败，就把用户唯一的调试入口
    //   静默关掉 —— 那会变成"控制台忽然没了、还不报错"。
    {
        char buffer[isaac::runtime::kConsoleSwitchMaximumBytes]{};
        const std::size_t off =
            isaac::runtime::SerializeConsoleSwitch(false, buffer, sizeof(buffer));
        check(off > 0 && !isaac::runtime::ParseConsoleSwitch(std::string_view(buffer, off)),
              "switch-roundtrip-off");
        const std::size_t on =
            isaac::runtime::SerializeConsoleSwitch(true, buffer, sizeof(buffer));
        check(on > 0 && isaac::runtime::ParseConsoleSwitch(std::string_view(buffer, on)),
              "switch-roundtrip-on");
        check(isaac::runtime::ParseConsoleSwitch("") == isaac::runtime::kConsoleSwitchDefaultEnabled,
              "switch-empty-defaults");
        check(isaac::runtime::ParseConsoleSwitch("enabled=2\n") == true, "switch-unknown-value-is-on");
        check(isaac::runtime::ParseConsoleSwitch("enabled=yes\n") == true,
              "switch-nonnumeric-value-is-on");
        check(isaac::runtime::ParseConsoleSwitch("isaac-switch-console-state 1\n") == true,
              "switch-header-only-is-on");
        check(!isaac::runtime::ParseConsoleSwitch("junk\nenabled=0\n"),
              "switch-finds-the-key-line");
        check(isaac::runtime::SerializeConsoleSwitch(true, nullptr, 0) == 0,
              "switch-serialize-null");
        char tiny[4]{};
        check(isaac::runtime::SerializeConsoleSwitch(true, tiny, sizeof(tiny)) == 0,
              "switch-serialize-no-room");
        // 文件名必须是**相对名**（存档分区），不许是卡上的绝对路径 ——
        // 与模组开关状态文件同一条纪律（那边由 `test_mod_toggle_storage_safety.py` 钉住）。
        check(isaac::runtime::kConsoleSwitchFileName[0] != '/', "switch-file-name-is-relative");
        check(std::strstr(isaac::runtime::kConsoleSwitchFileName, "romfs") == nullptr,
              "switch-file-name-is-not-in-the-overlay");
    }
    // ---- 1) 宽字符 → UTF-8（4 字节码元，UTF-32）----
    {
        const std::uint32_t ascii[] = {'o', 'k', 0};
        char out[16]{};
        check(Utf8(ascii, out, sizeof(out)) == 2, "utf32-ascii-length");
        check(std::strcmp(out, "ok") == 0, "utf32-ascii-text");
    }
    {
        const std::uint32_t bmp[] = {0x4E2D, 0};  // 中
        char out[16]{};
        check(Utf8(bmp, out, sizeof(out)) == 3, "utf32-bmp-length");
        check(static_cast<unsigned char>(out[0]) == 0xE4 && static_cast<unsigned char>(out[2]) == 0xAD,
              "utf32-bmp-bytes");
    }
    {
        const std::uint32_t two[] = {0xE9, 0};  // é
        char out[16]{};
        check(Utf8(two, out, sizeof(out)) == 2, "utf32-latin1-length");
    }
    {
        const std::uint32_t four[] = {0x1F600, 0};  // emoji
        char out[16]{};
        check(Utf8(four, out, sizeof(out)) == 4, "utf32-astral-length");
        check(static_cast<unsigned char>(out[0]) == 0xF0, "utf32-astral-lead-byte");
    }
    {
        const std::uint32_t surrogate[] = {0xD800, 0};  // 代理区：不合法 ⇒ 替换字符 U+FFFD
        char out[16]{};
        check(Utf8(surrogate, out, sizeof(out)) == 3, "utf32-surrogate-becomes-replacement");
        check(static_cast<unsigned char>(out[0]) == 0xEF, "utf32-replacement-bytes");
    }
    {
        const std::uint32_t text[] = {'a', 'b', 'c', 'd', 0};
        char out[4]{};
        check(Utf8(text, out, sizeof(out)) == 3, "utf32-truncates-to-capacity");
        check(std::strcmp(out, "abc") == 0, "utf32-truncation-keeps-terminator");
    }
    {
        char out[4]{};
        check(console::Utf32ToUtf8(nullptr, 4, out, sizeof(out)) == 0, "utf32-null-source");
        check(console::Utf32ToUtf8(reinterpret_cast<const std::uint32_t*>("x"), 1, nullptr, 4) == 0,
              "utf32-null-destination");
        check(Utf8(reinterpret_cast<const std::uint32_t*>("x"), out, 0) == 0, "utf32-zero-capacity");
    }

    // ---- 2) 输出行缓冲：按 `\n` 切、`\r` 丢掉、环形挤掉最旧、单行截断 ----
    {
        console::ConsoleLog log{};
        log.Append("one\ntwo\r\n", 9);
        check(log.LineCount() == 2, "log-splits-on-newline");
        check(std::strcmp(log.Line(0), "one") == 0, "log-first-line");
        check(std::strcmp(log.Line(1), "two") == 0, "log-second-line-drops-cr");
        // 续写：上一段以 `\n` 收尾 ⇒ 新的一段起新行。
        log.Append("three", 5);
        check(log.LineCount() == 3, "log-continuation-starts-a-new-line");
        check(std::strcmp(log.Line(2), "three") == 0, "log-last-line");
        // 越界取行返回空串（不返回 nullptr）。
        check(std::strcmp(log.Line(9), "") == 0, "log-out-of-range-is-empty");
    }
    {
        console::ConsoleLog log{};
        for (int index = 0; index < 20; ++index) {
            char buffer[16]{};
            std::snprintf(buffer, sizeof(buffer), "line%d\n", index);
            log.Append(buffer, std::strlen(buffer));
        }
        check(log.LineCount() == console::kConsoleLogLineCount, "log-ring-count-is-capped");
        check(std::strcmp(log.Line(0), "line8") == 0, "log-ring-drops-oldest");
        check(std::strcmp(log.Line(console::kConsoleLogLineCount - 1), "line19") == 0,
              "log-ring-newest-is-last");
    }
    {
        console::ConsoleLog log{};
        char long_line[300]{};
        std::memset(long_line, 'x', sizeof(long_line) - 2);
        long_line[sizeof(long_line) - 2] = '\n';
        log.Append(long_line, sizeof(long_line) - 1);
        check(log.LineCount() == 1, "log-long-line-is-one-line");
        check(std::strlen(log.Line(0)) == console::kConsoleLogLineCapacity - 1,
              "log-long-line-is-truncated");
    }
    {
        console::ConsoleLog log{};
        log.Append("a\n", 2);
        log.Clear();
        check(log.LineCount() == 0 && std::strcmp(log.Line(0), "") == 0, "log-clear");
    }

    // ---- 3) 跨模块字符串：手工拼的经典布局（短串 / 长串）----
    check(console::EngineStringSize(nullptr) == 0, "engine-string-null-size");
    check(console::StringLayoutSelfCheck(), "string-layout-self-check");
    {
        unsigned char header[console::kEngineStringBytes]{};
        char buffer[console::kCommandBufferCapacity]{};
        const char* command = "giveitem c1";  // 11 字节 ⇒ 短串
        check(console::BuildCommandString(command, std::strlen(command), header, buffer,
                                          sizeof(buffer)), "build-short-ok");
        check(!console::EngineStringIsLong(header), "build-short-is-not-long");
        check(console::EngineStringSize(header) == 11, "build-short-size");
        check(header[0] == 22, "build-short-size-shifted-into-first-byte");
        check(std::strcmp(reinterpret_cast<const char*>(header) + 1, command) == 0,
              "build-short-data-starts-at-plus-one");
        check(console::EngineStringData(header) == reinterpret_cast<const char*>(header) + 1,
              "build-short-data-pointer");
    }
    {
        // 22 = 内联上限（不换堆）；23 = 超出 ⇒ 必须换成长布局。
        unsigned char header[console::kEngineStringBytes]{};
        char buffer[console::kCommandBufferCapacity]{};
        char inline_command[32]{};
        std::memset(inline_command, 'a', 22);
        check(console::BuildCommandString(inline_command, 22, header, buffer, sizeof(buffer)),
              "build-inline-limit-ok");
        check(!console::EngineStringIsLong(header), "build-22-stays-inline");
        char long_command[32]{};
        std::memset(long_command, 'b', 23);
        check(console::BuildCommandString(long_command, 23, header, buffer, sizeof(buffer)),
              "build-23-ok");
        check(console::EngineStringIsLong(header), "build-23-goes-long");
        check(console::EngineStringSize(header) == 23, "build-23-size");
        check(console::EngineStringData(header) == static_cast<const char*>(buffer),
              "build-23-data-is-our-buffer");
        // 容量字段的最低有效位必须是 1（这就是"长串"的标志位）。
        check((header[0] & 0x01U) == 1U, "build-long-capacity-low-bit-is-flag");
    }
    {
        unsigned char header[console::kEngineStringBytes]{};
        char buffer[console::kCommandBufferCapacity]{};
        char big[console::kCommandBufferCapacity + 8]{};
        std::memset(big, 'c', sizeof(big));
        check(console::BuildCommandString(big, console::kCommandLengthLimit, header, buffer,
                                          sizeof(buffer)), "build-at-length-limit-ok");
        check(!console::BuildCommandString(big, console::kCommandLengthLimit + 1, header, buffer,
                                           sizeof(buffer)), "build-over-length-limit-rejected");
        check(!console::BuildCommandString(nullptr, 3, header, buffer, sizeof(buffer)),
              "build-null-command-rejected");
        check(!console::BuildCommandString(big, 3, nullptr, buffer, sizeof(buffer)),
              "build-null-header-rejected");
        check(!console::BuildCommandString(big, 30, header, nullptr, sizeof(buffer)),
              "build-null-buffer-rejected");
    }

    if (g_Failures == 0) {
        std::printf("CONSOLE_BRIDGE_OK\n");
    }
    return g_Failures == 0 ? 0 : 1;
}
'''


class ConsoleBridgeHarnessTests(unittest.TestCase):
    """在宿主上编译这套设施并跑行为用例（不需要 docker、不碰引擎）。"""

    @classmethod
    def setUpClass(cls):
        compilers = host_compilers()
        if compilers is None:
            raise unittest.SkipTest("需要宿主 C/C++ 编译器（本用例不需要 docker）")
        _, cxx = compilers
        cls.temporary = tempfile.TemporaryDirectory(prefix="isaac-console-")
        temporary = Path(cls.temporary.name)
        compatibility = temporary / "compatibility"
        compatibility.mkdir()
        (compatibility / "stdfloat").write_text(
            "#pragma once\nnamespace std { using float16_t = float; using float128_t = long double; }\n"
        )
        harness = temporary / "console_harness.cpp"
        harness.write_text(HARNESS.lstrip())
        cls.binary = temporary / "console_harness"
        cls.compile = subprocess.run(
            [
                cxx, "-std=c++23", "-Wall", "-Wextra", "-Werror",
                "-DEXL_LAYERED_RUNTIME=1",
                "-I", str(compatibility), "-I", str(SOURCE), "-I", str(SOURCE.parent / "src"),
                # 会话头会拉起 `lua_runtime_state.hpp` ⇒ 需要 vendored Lua 的头
                # （与 `test_lua_font_resources.py` 那一批宿主夹具同一份来源）。
                "-I", str(SOURCE / "third_party" / "lua-5.3.3" / "src"),
                str(harness), "-o", str(cls.binary),
            ],
            capture_output=True,
            text=True,
        )

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def test_harness_compiles(self):
        self.assertEqual(self.compile.returncode, 0,
                         f"宿主编译失败：\n{self.compile.stdout}\n{self.compile.stderr}")

    def test_behaviour_cases_pass(self):
        if self.compile.returncode != 0:
            self.skipTest("编译没通过，行为用例无从谈起（见上一条）")
        result = subprocess.run([str(self.binary)], capture_output=True, text=True)
        self.assertIn("CONSOLE_BRIDGE_OK", result.stdout,
                      f"夹具报出的失败项：\n{result.stdout}\n{result.stderr}")
        self.assertEqual(result.returncode, 0)


class ConsoleStateSurfaceTests(unittest.TestCase):
    """状态面字段数 ↔ 读数工具读取宽度：两处必须是同一个数。"""

    def test_field_count_matches_reader_width(self):
        text = BRIDGE.read_text(encoding="utf-8")
        markers = re.findall(r"//\s*\[(\d+)\]", text)
        self.assertTrue(markers, "没在状态面里解析到 `// [N]` 标记（格式变了？）")
        count = len(markers)
        self.assertEqual(markers, [str(index) for index in range(count)],
                         "状态面字段编号必须从 0 连续到 N-1（加字段只能往后追加）")

        reader = READER.read_text(encoding="utf-8")
        request = re.search(r"\('console_state',[^)]*?,\s*(\d+)\)", reader)
        self.assertIsNotNone(request, "读数工具里没有 `console_state` 这一条请求")
        words = int(request.group(1))
        expected_words = (count * 4 + 7) // 8
        self.assertEqual(words, expected_words,
                         f"读数工具要读 {words} 个字，而状态面是 {count} 个 u32 "
                         f"（{expected_words} 个字）—— 两处必须一起改")

    def test_state_symbol_shape_matches_reader(self):
        """状态面的符号名必须两处一致（这一份是**改编名**，不是裸名 —— 见桥那头两条踩坑记录）。"""
        bridge = BRIDGE.read_text(encoding="utf-8")
        self.assertIn("inline BridgeState g_ConsoleState{};", bridge)
        # `extern "C"` + 初始化列表会让 gcc 在 `-Werror` 下判红；把它写成**声明行**就该被拦下
        # （注释里提到这串是允许的 —— 那正是踩坑记录）。
        declarations = [line.strip() for line in bridge.splitlines() if not line.strip().startswith("//")]
        self.assertFalse([line for line in declarations if line.startswith('extern "C" inline BridgeState')],
                         "状态面不能写成 `extern \"C\" inline ... = {}`（gcc -Werror 会判红）")
        reader = READER.read_text(encoding="utf-8")
        self.assertIn("'g_ConsoleState': '_ZN5isaac7runtime7console14g_ConsoleStateE'", reader)
        # ELF同步后的真实偏移和待同步占位值都可登记；零不是状态面契约。
        self.assertRegex(reader, r"'g_ConsoleState':\s*0x[0-9a-fA-F]+")
        self.assertIn("sync_syms_from_elf", reader)


class ConsoleSwitchSurfaceTests(unittest.TestCase):
    """批次 124 的总开关：**只在一条缝上做 I/O** + 关掉时**真的挡在执行入口前面**。

    这两条都是结构性的（宿主上碰不到文件系统与引擎），所以按仓库既有做法用**文本判据**钉住
    （先例：`test_mod_toggle_storage_safety.py` 对模组开关状态文件就是这么钉的）。
    """

    def test_switch_io_goes_through_the_save_port_only(self):
        bridge = BRIDGE.read_text(encoding="utf-8")
        self.assertIn("SessionSaveFilePort()", bridge,
                      "开关状态必须经存档分区端口读写（`SessionSaveFilePort()`）")
        for forbidden in ("fopen", "std::ofstream", "ifstream", "romfs", "rom:/"):
            self.assertNotIn(forbidden, bridge,
                             f"开关那条路不许出现 {forbidden!r}（不许自己拼卡上的路径）")

    def test_switch_blocks_before_anything_else(self):
        """关掉时必须**在执行入口最前面**就返回，且每帧点里连按键都不扫。"""
        bridge = BRIDGE.read_text(encoding="utf-8")
        self.assertIn("kDisabledBySwitch", bridge)
        # 拒绝判据必须在"长度上限"那条之前（否则关了开关还会去判命令合法性，语义就不叫"没有控制台"）。
        self.assertLess(bridge.index("!core.switchEnabled"), bridge.index("length == SIZE_MAX", bridge.index("!core.switchEnabled")),
                        "开关判据必须排在执行入口的更前面")
        session = (ROOT / "runtime" / "src" / "infrastructure" / "console"
                   / "console_session.hpp").read_text(encoding="utf-8")
        self.assertIn("ConsoleSwitchTick();", session,
                      "每帧点必须做开关的 I/O 待办（开局读一次 / 拨动后写一次）")
        # 关掉 ⇒ 早退，且排在"扫按键"之前（不然关了还每帧问 32 次动作查询）。
        # 用**循环那一行**而不是常量名：常量定义在文件上半部分，比早退更靠前，拿它比就假了。
        self.assertLess(session.index("!ConsoleSwitchEnabled()"),
                        session.index("action < kActionScanLimit"),
                        "开关判据必须在按键扫描之前")


if __name__ == "__main__":
    unittest.main()
