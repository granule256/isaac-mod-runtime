"""门禁：`PngToPcx` 转码器（宿主版）与参考实现 `tools/png_to_pcx.py` 逐字节一致。

## 为什么要有它（2026-09-21，贴图桥）

`ImagePcxLoad` 入口中继回调要在内存里把「只带 `.png`」的 Mod 资源转成引擎认识的 PCX 字节。
转码器是手写的（不引第三方库、不 vendoring stb_image），唯一机器核对手段就是这份对照：
**对每一张样本 PNG，C++ 桥产出的 PCX 必须和 Python 参考实现逐字节相同**；形态不支持的 PNG
（调色板 / 隔行 / 16bit）必须**拒绝且不崩**（与参考实现抛 `PngFormatError` 同义）。

样本由本测试自己构造（不依赖 PIL）：手写 IHDR + 过滤后的 IDAT + IEND，覆盖 5 种滤波、
4 种颜色类型、多种尺寸；参考实现走 `tools.png_to_pcx.png_to_pcx`。
"""

import subprocess
import sys
import tempfile
import unittest
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BRIDGE_CPP = ROOT / "runtime" / "src" / "infrastructure" / "content" / "png_to_pcx_bridge.cpp"
HARNESS_CPP = ROOT / "runtime" / "tests" / "png_to_pcx_bridge_harness.cpp"
REFERENCE = ROOT / "tools" / "png_to_pcx.py"

sys.path.insert(0, str(ROOT / "tools"))
from png_to_pcx import png_to_pcx, PngFormatError  # noqa: E402


def build_harness() -> Path:
    exe = Path(tempfile.gettempdir()) / "png_to_pcx_bridge_harness"
    result = subprocess.run(
        ["c++", "-std=c++23", "-Wall", "-Wextra", "-Werror",
         "-I", str(ROOT / "runtime" / "src"),
         str(HARNESS_CPP), str(BRIDGE_CPP), "-lz", "-o", str(exe)],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError("编译转码器夹具失败：\n" + result.stdout + result.stderr)
    return exe


def run_harness(exe: Path, png_path: Path, pcx_path: Path) -> tuple[int, str]:
    result = subprocess.run([str(exe), str(png_path), str(pcx_path)],
                            capture_output=True, text=True)
    return result.returncode, result.stdout.strip()


def make_png(width: int, height: int, color_type: int, pixels, filters) -> bytes:
    """构造一张合法 PNG。`pixels` 是 (height, width, 4) 的 RGBA 数组（0..255）。
    `filters` 是长度为 height 的列表，指定每一行用的滤波器（0..4）。"""
    channels = {0: 1, 2: 3, 4: 2, 6: 4}[color_type]

    def pack_row(rgba_row):
        out = bytearray()
        for px in rgba_row:
            if color_type == 0:
                out.append(px[0])
            elif color_type == 2:
                out.append(px[0]); out.append(px[1]); out.append(px[2])
            elif color_type == 4:
                out.append(px[0]); out.append(px[3])
            else:
                out += bytes(px)
        return out

    raw = bytearray()
    prev = bytearray(width * channels)
    for y in range(height):
        row = pack_row(pixels[y])
        f = filters[y]
        filtered = bytearray(width * channels)
        for i in range(width * channels):
            left = row[i - channels] if i >= channels else 0
            up = prev[i]
            up_left = prev[i - channels] if i >= channels else 0
            if f == 0:
                v = row[i]
            elif f == 1:
                v = row[i] - left
            elif f == 2:
                v = row[i] - up
            elif f == 3:
                v = row[i] - ((left + up) >> 1)
            else:  # 4 Paeth
                p = left + up - up_left
                pa = abs(p - left); pb = abs(p - up); pc = abs(p - up_left)
                pred = left if (pa <= pb and pa <= pc) else (up if pb <= pc else up_left)
                v = row[i] - pred
            filtered[i] = v & 0xFF
        raw.append(f)
        raw += filtered
        prev = row

    def chunk(c_type: bytes, data: bytes) -> bytes:
        return (len(data).to_bytes(4, "big") + c_type + data +
                zlib.crc32(c_type + data).to_bytes(4, "big"))

    ihdr = (width.to_bytes(4, "big") + height.to_bytes(4, "big") +
            bytes([8, color_type, 0, 0, 0]))
    idat = zlib.compress(bytes(raw), 9)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) +
            chunk(b"IDAT", idat) + chunk(b"IEND", b""))


def solid(w, h, rgba):
    return [[rgba for _ in range(w)] for _ in range(h)]


class PngToPcxBridgeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.exe = build_harness()

    def _compare(self, png_bytes, label):
        with tempfile.TemporaryDirectory() as d:
            png_path = Path(d) / "in.png"
            pcx_path = Path(d) / "out.pcx"
            png_path.write_bytes(png_bytes)
            code, _ = run_harness(self.exe, png_path, pcx_path)
            self.assertEqual(code, 0, f"{label}：转码器拒绝了一张它应当接受的 PNG")
            got = pcx_path.read_bytes()
            expected = png_to_pcx(png_bytes)
            self.assertEqual(got, expected,
                             f"{label}：转码器产出与参考实现不一致（{len(got)} vs {len(expected)} 字节）")

    def test_rgba_various_filters(self):
        # 5 行分别用 5 种滤波器，覆盖 Sub/Up/Average/Paeth 反滤波路径。
        filters = [0, 1, 2, 3, 4]
        px = [[((x * 40 + y * 30) & 0xFF, (x * 17) & 0xFF, (y * 53) & 0xFF,
                (x * 11 + y * 7) & 0xFF) for x in range(8)] for y in range(5)]
        self._compare(make_png(8, 5, 6, px, filters), "rgba-8x5-filters[0..4]")

    def test_rgb_and_gray_and_gray_alpha(self):
        px = solid(4, 4, [10, 20, 30, 255])
        self._compare(make_png(4, 4, 2, px, [0] * 4), "rgb-4x4")
        g = solid(4, 4, [128, 128, 128, 255])
        self._compare(make_png(4, 4, 0, g, [0] * 4), "gray-4x4")
        ga = [[(200, 0, 0, (x * 64) & 0xFF) for x in range(4)] for _ in range(4)]
        self._compare(make_png(4, 4, 4, ga, [2] * 4), "gray-alpha-4x4-up")

    def test_larger_image_exercises_rle(self):
        # 64x64 多色块，触发长 RLE 行程。
        px = [[((x // 8) * 30 & 0xFF, (y // 8) * 30 & 0xFF, (x + y) & 0xFF, 255)
               for x in range(64)] for y in range(64)]
        self._compare(make_png(64, 64, 6, px, [0] * 64), "rgba-64x64-rle")

    def test_1x1_edge(self):
        self._compare(make_png(1, 1, 6, solid(1, 1, [1, 2, 3, 4]), [0]), "rgba-1x1")

    def test_palette_png_is_rejected(self):
        # 调色板色型（color_type=3）：参考实现抛 PngFormatError，转码器须返回 false。
        png = make_png(2, 2, 6, solid(2, 2, [1, 2, 3, 4]), [0, 0])  # 先造一张合法 RGBA
        # 把 IHDR 的 color_type 字节（偏移 25+9）改成 3，变成调色板图（无 PLTE）。
        b = bytearray(png)
        b[25 + 9] = 3  # IHDR: 8(sig)+4(len)+4(type)+4(w)+4(h)+1(bit_depth)+1(color_type)
        with tempfile.TemporaryDirectory() as d:
            png_path = Path(d) / "in.png"
            pcx_path = Path(d) / "out.pcx"
            png_path.write_bytes(bytes(b))
            code, _ = run_harness(self.exe, png_path, pcx_path)
            self.assertNotEqual(code, 0, "调色板 PNG 不该被接受")
            self.assertFalse(pcx_path.exists())

    def test_interlaced_png_is_rejected(self):
        png = bytearray(make_png(4, 4, 6, solid(4, 4, [9, 9, 9, 255]), [0] * 4))
        # IHDR 的 interlace 字节（offset 25+12）改成 1。
        png[25 + 12] = 1
        with tempfile.TemporaryDirectory() as d:
            png_path = Path(d) / "in.png"
            pcx_path = Path(d) / "out.pcx"
            png_path.write_bytes(bytes(png))
            code, _ = run_harness(self.exe, png_path, pcx_path)
            self.assertNotEqual(code, 0, "隔行 PNG 不该被接受")
            self.assertFalse(pcx_path.exists())

    def test_corrupt_png_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            png_path = Path(d) / "in.png"
            pcx_path = Path(d) / "out.pcx"
            png_path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"garbage")
            code, _ = run_harness(self.exe, png_path, pcx_path)
            self.assertNotEqual(code, 0, "损坏的 PNG 不该被接受")


if __name__ == "__main__":
    unittest.main()
