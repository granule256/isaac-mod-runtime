"""门禁：**PC 的路径分隔符语义**必须落在平台层，而且**落在"真正消费路径"的那一层**
（批次 411 起，批次 412 定案位置，2026-10-08）。

## 这一批修的是什么

Windows 的文件 API 把 `\\` 与 `/` 当**同一个**分隔符；POSIX 只认 `/`，`\\` 在 POSIX 里是
**普通字符**。PC 上的模组按 Windows 语义写路径，于是同一份模组在 PC 能跑、在 Switch 上解析不到。

真机实证（2026-10-08，Trinity）：
* 模组的 anm2 一律写 `Spritesheet Path="costumes_peter\\character_009b_lazarus2hair.png"`；
* **同目录里本体**的 anm2 一律写 `/`（`costumes/character_009b_lazarus2hair.png`）；
* 带 `\\` 的串在 `IContentManager::GetMountedFilePath` 上查不到 ⇒ 精灵表解析不到
  ⇒ 该层画不出来（真机现象：选 Trinity 的 Peter 进局，角色只剩一对眼睛）。

## 为什么门禁钉的是"平台层"而不是"模组能跑"

★★ 用户 2026-10-08 明确要求：**"需要的不是能跑起来，而是从根本上恢复 PC 的环境；
哪里错了就直接打补丁是不行的"**。所以本批**不许改模组文件**（PC 上那份 mod 本来就不用改），
修法只能落在平台层：在路径解析的入口把 `\\` 归一化成 `/`。

本模块钉两件事：
1. **行为**（宿主编译并执行真实头文件）：归一化真的把 `\\` 换成 `/`、装不下时**不写半条路径**；
2. **接线**：那个中继确实用了它，而且**在把路径交出去之前**（重定向 / 原函数之前）就已经归一化；
   并且**没有**把这件事做在 `ImageManager::LoadImage` 那条中继上（那里引擎可能存路径 ⇒ 栈缓冲会野）。
"""

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "runtime" / "src"
SOURCE = ROOT / "runtime" / "source"
HEADER = SRC / "infrastructure" / "paths" / "pc_path_semantics.hpp"
BRIDGE = SOURCE / "image_pcx_bridge_hook.cpp"
LOAD_FILE_RELAY_NAME = (
    'extern "C" isaac::runtime::relay::SmartPointerShim '
    'EntryRelayImageManagerLoadFileCallback('
)
MOUNT_QUERY_RELAY_NAME = 'extern "C" char* EntryRelayContentGetMountedFilePathCallback('

DRIVER = r"""
#include "infrastructure/paths/pc_path_semantics.hpp"

#include <cstdio>
#include <cstring>

int main() {
    namespace paths = isaac::runtime::paths;
    // ① 判别：只有反斜杠才算 Windows 分隔符。
    std::printf("has_posix=%d\n", paths::HasWindowsSeparator("costumes_peter/x.png") ? 1 : 0);
    std::printf("has_windows=%d\n", paths::HasWindowsSeparator("costumes_peter\\x.png") ? 1 : 0);
    std::printf("has_null=%d\n", paths::HasWindowsSeparator(nullptr) ? 1 : 0);

    // ② 归一化：把 `\` 换成 `/`，其余一字不动（含大小写、多级目录、文件名里的空格）。
    char buffer[128];
    const char* sample =
        "gfx/characters\\costumes_peter\\character_009b_lazarus2hair.png";
    const std::size_t written = paths::NormalizeSeparatorsInto(buffer, sizeof(buffer), sample);
    std::printf("normalized=%s\n", buffer);
    std::printf("normalized_len=%zu\n", written);
    std::printf("normalized_has_backslash=%d\n", std::strchr(buffer, '\\') != nullptr ? 1 : 0);

    // ③ 容量不够 ⇒ 返回 0（**不给出半条路径**），且一个字节都不写。
    char small[8];
    std::memset(small, 'Z', sizeof(small));
    const std::size_t refused =
        paths::NormalizeSeparatorsInto(small, sizeof(small), "abcdefghijklmnop");
    std::printf("refused_len=%zu\n", refused);
    std::printf("refused_untouched=%d\n", small[0] == 'Z' ? 1 : 0);

    // ④ 恰好装得下（含结尾 0）时必须成功 —— 边界值。
    char exact[6];
    const std::size_t exact_written =
        paths::NormalizeSeparatorsInto(exact, sizeof(exact), "a\\b/c");
    std::printf("exact_len=%zu\n", exact_written);
    std::printf("exact_value=%s\n", exact);
    return 0;
}
"""


def find_compiler():
    for candidate in (os.environ.get("CXX"), "clang++", "g++"):
        if candidate and shutil.which(candidate):
            return shutil.which(candidate)
    return None


class PcPathSemanticsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.compiler = find_compiler()
        cls.output = {}
        cls.compile_error = None
        if cls.compiler is None:
            return
        cls.tempdir = tempfile.TemporaryDirectory(prefix="pc_path_semantics_")
        source = Path(cls.tempdir.name) / "driver.cpp"
        source.write_text(DRIVER.lstrip(), encoding="utf-8")
        binary = Path(cls.tempdir.name) / "driver"
        build = subprocess.run(
            [cls.compiler, "-std=c++23", "-Wall", "-Wextra", "-Werror",
             "-I", str(SRC), "-o", str(binary), str(source)],
            capture_output=True, text=True,
        )
        if build.returncode != 0:
            cls.compile_error = build.stderr.strip() or build.stdout.strip()
            return
        run = subprocess.run([str(binary)], capture_output=True, text=True)
        if run.returncode != 0:
            cls.compile_error = f"driver 退出码 {run.returncode}: {run.stderr.strip()}"
            return
        for line in run.stdout.splitlines():
            if "=" in line:
                key, value = line.split("=", 1)
                cls.output[key] = value

    @classmethod
    def tearDownClass(cls):
        if getattr(cls, "tempdir", None) is not None:
            cls.tempdir.cleanup()

    def require_driver(self):
        if self.compiler is None:
            self.skipTest("宿主机没有可用的 C++ 编译器（clang++/g++），跳过真实头文件执行测试")
        if self.compile_error:
            self.fail(f"头文件在宿主机编译/执行失败：{self.compile_error}")

    # ------------------------------------------------------------------
    # 行为判据
    # ------------------------------------------------------------------

    def test_detects_windows_separator_only(self):
        """只有 `\\` 才算 Windows 分隔符；`/`、空指针都不算。"""
        self.require_driver()
        self.assertEqual(self.output["has_posix"], "0")
        self.assertEqual(self.output["has_windows"], "1")
        self.assertEqual(self.output["has_null"], "0")

    def test_normalizes_backslash_to_slash(self):
        """归一化：`\\` 全变 `/`，其余（大小写、多级目录、下划线）一字不动。"""
        self.require_driver()
        self.assertEqual(
            self.output["normalized"],
            "gfx/characters/costumes_peter/character_009b_lazarus2hair.png")
        self.assertEqual(int(self.output["normalized_len"]), len(self.output["normalized"]),
                         "返回的长度必须等于写进去的字符数")
        self.assertEqual(self.output["normalized_has_backslash"], "0")

    def test_refuses_when_capacity_is_too_small(self):
        """容量不够 ⇒ 返回 0 且**一个字节都不写**（绝不给半条路径）。"""
        self.require_driver()
        self.assertEqual(self.output["refused_len"], "0")
        self.assertEqual(self.output["refused_untouched"], "1")

    def test_accepts_exact_fit(self):
        """恰好装得下（含结尾 0）必须成功 —— 边界值。"""
        self.require_driver()
        self.assertEqual(self.output["exact_len"], "5")
        self.assertEqual(self.output["exact_value"], "a/b/c")

    # ------------------------------------------------------------------
    # 接线判据（防止"设施做了、中继没用它"；也防止**修在一条走不到的路上**）
    # ------------------------------------------------------------------

    def load_file_relay_body(self):
        text = BRIDGE.read_text(encoding="utf-8")
        start = text.index(LOAD_FILE_RELAY_NAME)
        body = text[start:]
        return body[:body.index("\n}\n") + 3]

    def mount_query_relay_body(self):
        text = BRIDGE.read_text(encoding="utf-8")
        start = text.index(MOUNT_QUERY_RELAY_NAME)
        body = text[start:]
        return body[:body.index("\n}\n") + 3]

    def test_normalization_is_in_the_layer_that_consumes_the_path(self):
        """★★★ 归一化必须在 `ImageManager::LoadImage` 那条中继上 —— **409/411 两次教训换来的位置**。

        事实链：anm2 引 `.png` 的精灵表从这条路进来（`pngArgCalls` 计的就是它），
        而引擎拿**它收到的实参**去 `CreateCleanPath` + `GetExtension` 分派
        （桥里 268 的真机教训 + 反汇编复核）⇒ 只有改这里的实参才管用。
        """
        body = self.load_file_relay_body()
        self.assertIn("NormalizePathSeparatorsForEngine(rawPath)", body,
                      "这条中继必须把入参喂给归一化")
        self.assertIn("const char* path = NormalizePathSeparatorsForEngine(rawPath);", body,
                      "归一化之后必须有一份 `path` 供下面整段使用")
        self.assertIn("const char* rawPath", body, "形参应改名 `rawPath`")
        # 引擎必须拿到**归一化后**的那一份：`original(self, loadPath, …)` 的上游是 `effectivePath`。
        self.assertIn("loadWith(effectivePath)", body)

    def test_normalization_helper_uses_a_long_lived_buffer(self):
        """实参要交给引擎 ⇒ 缓冲必须是**长生命周期**的（栈缓冲出函数即失效）。"""
        text = BRIDGE.read_text(encoding="utf-8")
        body = text[text.index("NormalizePathSeparatorsForEngine(const char* path)"):]
        body = body[:body.index("\n}\n") + 3]
        self.assertIn("g_pathSeparatorRing", body, "必须用文件级的长生命周期环形缓冲")
        self.assertNotIn("char slot[", body, "不许在函数里开栈缓冲（出函数即失效 ⇒ 野指针）")
        self.assertIn("HasWindowsSeparator(path)", body,
                      "没有 `\\` 时应零拷贝原样返回")

    def test_normalization_is_not_in_the_mount_query_relay(self):
        """★★ 归一化**不许**留在 `GetMountedFilePath` 那条中继上 —— 411 就是放这儿，真机读数**恒 0**。

        `.anm2` 文件自己确实经过那个入口，但 **anm2 引用的精灵表路径不经过** ⇒
        放在那里等于给一条走不到的路修栅栏（功能全绿、计数恒 0、真机照旧坏）。
        """
        body = self.mount_query_relay_body()
        self.assertNotIn("NormalizeSeparatorsInto(", body,
                         "411 的教训：这一层看不到精灵表路径，归一化放在这里等于没做")
        self.assertNotIn("NormalizePathSeparatorsForEngine(", body,
                         "同上 —— 归一化只放在真正消费路径的那一层")

    def test_diagnostic_counter_landed_in_a_reserved_slot(self):
        """诊断计数必须落在 361 的占位槽里 —— 不挪任何已发布偏移（结构体大小仍是 5816）。"""
        text = BRIDGE.read_text(encoding="utf-8")
        self.assertIn("pathSeparatorNormalized", text)
        self.assertIn("== 5816", text,
                      "结构体大小必须保持 5816（读数工具按固定偏移解析）")

    def test_diag_copy_stays_out_of_line_and_uses_libc(self):
        """★★★ 诊断字符串搬运：**不内联 + 只走 libc** —— 两条都是真机量出来的（不是保守写法）。

        411 把它从 `strncpy` 改成有界循环、又在调用点引入 4096 字节入参缓冲之后：
        * 没有 `noinline` ⇒ GCC 在 ~10 个调用点全部内联展开：`EntryRelayContentGetMountedFilePathCallback`
          一个函数 **3108 → 21316 字节（+18 KiB）**，模块代码段 `0xa6700 → 0xaa700`；
        * 只有 `noinline`、仍是手写循环 ⇒ GCC 按 `capacity` 做 `constprop` 克隆并向量化展开成
          ~7 份、每份 1.3~1.6 KiB ⇒ 代码段仍比 410 高 8 KiB。
        * 改成 libc（`strlen` + 有界 `memcpy`）之后没有可展开的循环体 ⇒ 这一段回到一份、几十字节。
        """
        text = BRIDGE.read_text(encoding="utf-8")
        self.assertIn("__attribute__((noinline)) void ImagePcxCopyDiagString(", text,
                      "必须带 `noinline`（否则会在 ~10 个调用点各展开一份 ⇒ 单函数涨 18 KiB）")
        body = text[text.index("void ImagePcxCopyDiagString("):]
        body = body[:body.index("\n}\n") + 3]
        self.assertIn("std::memcpy(destination, source, length)", body,
                      "拷贝必须走 libc（手写循环会被按 capacity 克隆 + 向量化展开）")
        self.assertNotIn("for (", body,
                         "这个函数体里不许出现手写循环 —— GCC 会把它们展开成一堆克隆"
                         "（411 实测：7 份、每份 1.3~1.6 KiB）")


if __name__ == "__main__":
    unittest.main()
