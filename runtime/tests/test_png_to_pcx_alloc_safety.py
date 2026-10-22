"""门禁：转码路径的**分配安全**（批次 402 —— 修"选模组角色进局 ⇒ 停在加载画面退回 HOME"）。

## 为什么要有它

真机崩溃报告 `01791381539`（2026-10-07）的符号化栈落在
`PngToPcx → operator new → __cxa_throw → __unexpected → __terminate ⇒ User Break`：
`PngToPcx` 声明成 `noexcept`，但内部用 `std::vector` / `operator new`；分配失败抛
`std::bad_alloc`、穿过 `noexcept` 边界 ⇒ `std::terminate` ⇒ **整个游戏 abort**。
另有旧口径的第二个洞：`kMaxDecodedBytes = 256 MiB` **大于整个假堆（128 MiB）**，等于没设限。

本门禁钉三件事（**先红后绿**）：

1. **任何分配失败 ⇒ `PngToPcx` 返回 `false`、进程不崩**：
   夹具用全局 `operator new` 注入失败（`--fail-alloc-after K`），判据 = 正常退出、打印 `REJECT`、
   退出码 1（**不是**被信号/abort 带走）。这就是把真机那条栈变成**可测**的一刀。
2. **峰值超预算 ⇒ 拒绝**（不是崩、不是崩一半）：构造一张**旧口径会放行、新口径必须拒**的图
   （2500×2500 RGBA：旧"解码后 ≤24 MiB"判据算 23.84 MiB ⇒ 放行；新峰值公式 ≈75 MiB > 64 MiB ⇒ 拒）。
3. **正常 PNG 仍逐字节相同**（拿现成的 `tools/png_to_pcx.py` 对照，不放宽）。

★ 另附静态接线：预算/公式只此一份（`.hpp`），设备侧转码与调用方预检**共用**，口径不许漂移。
"""

import subprocess
import sys
import tempfile
import unittest
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BRIDGE_CPP = ROOT / "runtime" / "src" / "infrastructure" / "content" / "png_to_pcx_bridge.cpp"
BRIDGE_HPP = ROOT / "runtime" / "src" / "infrastructure" / "content" / "png_to_pcx_bridge.hpp"
HOOK_CPP = ROOT / "runtime" / "source" / "image_pcx_bridge_hook.cpp"
HARNESS_CPP = ROOT / "runtime" / "tests" / "png_to_pcx_bridge_harness.cpp"

sys.path.insert(0, str(ROOT / "tools"))
from png_to_pcx import png_to_pcx  # noqa: E402


def build_harness() -> Path:
    exe = Path(tempfile.gettempdir()) / "png_to_pcx_bridge_harness_alloc"
    result = subprocess.run(
        ["c++", "-std=c++23", "-Wall", "-Wextra", "-Werror",
         "-I", str(ROOT / "runtime" / "src"),
         str(HARNESS_CPP), str(BRIDGE_CPP), "-lz", "-o", str(exe)],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError("编译转码器夹具失败：\n" + result.stdout + result.stderr)
    return exe


def run_harness(exe: Path, png_path: Path, pcx_path: Path, extra=None):
    cmd = [str(exe), str(png_path), str(pcx_path)]
    if extra:
        cmd += extra
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode, result.stdout.strip()


def chunk(c_type: bytes, data: bytes) -> bytes:
    return (len(data).to_bytes(4, "big") + c_type + data +
            zlib.crc32(c_type + data).to_bytes(4, "big"))


def png_with_ihdr(width: int, height: int, color_type: int, idat: bytes) -> bytes:
    """只造"签名 + IHDR + 一个 IDAT + IEND"，IDAT 内容无关（峰值闸门在解压之前）。"""
    ihdr = (width.to_bytes(4, "big") + height.to_bytes(4, "big") +
            bytes([8, color_type, 0, 0, 0]))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) +
            chunk(b"IDAT", idat) + chunk(b"IEND", b""))


def solid_rgba_png(width: int, height: int) -> bytes:
    """一张真正合法的 RGBA PNG（每行滤波 0），用于"正常图仍逐字节相同"那条。"""
    raw = bytearray()
    row = bytes([7, 200, 30, 255]) * width
    for _ in range(height):
        raw.append(0)
        raw += row
    ihdr = (width.to_bytes(4, "big") + height.to_bytes(4, "big") +
            bytes([8, 6, 0, 0, 0]))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) +
            chunk(b"IDAT", zlib.compress(bytes(raw), 9)) + chunk(b"IEND", b""))


class PngToPcxAllocSafetyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.exe = build_harness()

    def test_normal_png_still_byte_identical(self):
        """正常 PNG 照旧转得出与参考实现**逐字节相同**的 PCX（没放宽）。"""
        png = solid_rgba_png(64, 64)
        with tempfile.TemporaryDirectory() as d:
            png_path = Path(d) / "in.png"
            pcx_path = Path(d) / "out.pcx"
            png_path.write_bytes(png)
            for extra in (None, ["--fail-alloc-after", "1000000"]):  # 不注入 / 注入但远没触发
                if pcx_path.exists():
                    pcx_path.unlink()
                code, out = run_harness(self.exe, png_path, pcx_path, extra)
                self.assertEqual(code, 0, f"正常 PNG 应转成功，实得 code={code} out={out}")
                self.assertEqual(pcx_path.read_bytes(), png_to_pcx(png),
                                 "转码产出与参考实现不一致")

    def test_injected_alloc_failure_returns_false_and_does_not_abort(self):
        """★ 核心：把"分配失败"注入进去 —— 必须 `REJECT` + 正常退出，**绝不** abort/信号。

        这就是真机那条栈的宿主复现：旧行为下 `bad_alloc` 穿出 `noexcept` ⇒ `SIGABRT`；
        新行为下被 `try/catch(...)` 收口成 `return false` ⇒ 退出码 1。
        """
        png = solid_rgba_png(64, 64)
        with tempfile.TemporaryDirectory() as d:
            png_path = Path(d) / "in.png"
            pcx_path = Path(d) / "out.pcx"
            png_path.write_bytes(png)
            for k in (0, 1, 2, 3, 4, 5):
                if pcx_path.exists():
                    pcx_path.unlink()
                code, out = run_harness(self.exe, png_path, pcx_path,
                                        ["--fail-alloc-after", str(k)])
                self.assertEqual(code, 1,
                                 f"注入第 {k} 次分配后应『拒绝』而非崩（code={code}，负值 = 信号）")
                self.assertIn("REJECT", out)
                self.assertFalse(pcx_path.exists(), "拒绝时不该留下输出文件")

    def test_peak_over_budget_is_rejected(self):
        """★ 新口径：**峰值**超预算就拒 —— 一张旧口径（解码后 24 MiB）会放行的图。

        2500×2500 RGBA：旧判据 `(2500×4+1)×2500 = 25,002,500 B = 23.84 MiB ≤ 24 MiB` ⇒ 放行；
        新峰值上界 ≈ `25.0M + 8×6.25M = 75 MB > 64 MiB` ⇒ 拒。**不崩、不崩一半**。
        """
        png = png_with_ihdr(2500, 2500, 6, b"\x00")
        with tempfile.TemporaryDirectory() as d:
            png_path = Path(d) / "in.png"
            pcx_path = Path(d) / "out.pcx"
            png_path.write_bytes(png)
            code, out = run_harness(self.exe, png_path, pcx_path)
            self.assertEqual(code, 1, f"超预算图应被拒（code={code} out={out}）")
            self.assertIn("REJECT", out)
            self.assertFalse(pcx_path.exists())

    def test_oversize_side_is_rejected_without_crash(self):
        """单边 > 4096 也照旧拒（旧判据保留），且同样是"正常退出"而不是崩。"""
        png = png_with_ihdr(5000, 8, 6, b"\x00")
        with tempfile.TemporaryDirectory() as d:
            png_path = Path(d) / "in.png"
            pcx_path = Path(d) / "out.pcx"
            png_path.write_bytes(png)
            code, _ = run_harness(self.exe, png_path, pcx_path)
            self.assertEqual(code, 1)

    def test_budget_formula_shared_and_no_escape_shape(self):
        """静态接线：预算/公式只此一份、两边共用；桥里 `noexcept` + **全程 nothrow** 形状在。

        ★ 为什么是 nothrow 而不是 `try/catch`：本模块的构建**关掉了 C++ 异常**
        （`-fno-exceptions`，故 `try {} catch (...)` 编译不过），`std::vector` 分配失败会走
        `__throw_bad_alloc` ⇒ 直接 abort。所以桥里**不许有 `std::vector`**，全部走
        `new (std::nothrow)` + 判空。
        """
        hpp = BRIDGE_HPP.read_text(encoding="utf-8")
        self.assertIn("kPngToPcxPeakBudgetBytes", hpp)
        self.assertIn("PngToPcxPeakUpperBound", hpp)

        cpp = BRIDGE_CPP.read_text(encoding="utf-8")
        self.assertIn("PngToPcxPeakUpperBound", cpp)
        self.assertIn("kPngToPcxPeakBudgetBytes", cpp)
        # 旧的 256 MiB 上限**常量定义**不许再回来（注释里提到它的来历是允许的）。
        self.assertNotIn("constexpr std::uint64_t kMaxDecodedBytes", cpp,
                         "旧的 256 MiB 上限是个洞，不许再回来")
        # 会抛的容器一律不许出现在转码路径上（`-fno-exceptions` 下它们就是 abort）。
        # （注释里提到 `std::vector` 的来历是允许的，所以只卡"真的用了"的形状。）
        self.assertNotIn("std::vector<", cpp, "转码路径不许用会抛的 std::vector")
        self.assertNotIn("#include <vector>", cpp)
        self.assertIn("new (std::nothrow)", cpp, "分配一律走 nothrow")
        # `PngToPcx` 仍是 `noexcept`。
        self.assertIn("size_t* out_size) noexcept {", cpp)

        hook = HOOK_CPP.read_text(encoding="utf-8")
        self.assertIn("PngToPcxPeakUpperBound", hook, "调用方预检必须与转码用同一份峰值公式")
        self.assertIn("kPngToPcxPeakBudgetBytes", hook)
        self.assertNotIn("kImagePcxPngDecodedCapBytes", hook,
                         "旧的『只看解码后 24 MiB』口径必须已被峰值口径替换")


if __name__ == "__main__":
    unittest.main()
