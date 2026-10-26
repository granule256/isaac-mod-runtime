"""BUG-018：`PNG -> PCX` 必须**预乘 alpha**，与本体资源同一口径。

现场：Auri 贪婪开局，头顶光圈 / 右侧方块 / 左上沙漏 HUD 是**实心青块**。
作者 PNG 的半透明像素是 `(0,255,255)` / `(43,230,255)`（非预乘）；本体自己的 PCX 是预乘的
（`resources/gfx/spotlight.pcx` 的 34498 个半透明像素里 `max(R,G,B) > a` 的一个都没有）。
⇒ 桥必须把 straight 转 premultiplied，否则引擎按预乘再加一遍就是青得发亮。

本测试守三条：半透明被预乘、不透明原样、全透明归零；外加一条真实 Auri 贴图的不变式检查。
"""
import unittest
from pathlib import Path

from .test_png_to_pcx_bridge import build_harness, make_png, run_harness
import tempfile

ROOT = Path(__file__).resolve().parents[2]
AURI_CROWN_PNG = (ROOT / "dist" / "character-hair-pause-20261026" / "auri-user-original" /
                  "2283703372" / "resources" / "gfx" / "crownoflight.png")


def decode_pcx(data: bytes):
    """解 8bpp RLE + N planes 的 PCX（只服务本测试）。"""
    planes = data[65]
    width = (data[8] | (data[9] << 8)) - (data[4] | (data[5] << 8)) + 1
    height = (data[10] | (data[11] << 8)) - (data[6] | (data[7] << 8)) + 1
    bytes_per_line = data[66] | (data[67] << 8)
    total = height * planes * bytes_per_line
    raw = bytearray()
    pos = 128
    while len(raw) < total and pos < len(data):
        value = data[pos]
        pos += 1
        if (value & 0xC0) == 0xC0:
            count = value & 0x3F
            raw += bytes((data[pos],)) * count
            pos += 1
        else:
            raw.append(value)
    pixels = []
    for y in range(height):
        base = y * planes * bytes_per_line
        for x in range(width):
            pixels.append(tuple(raw[base + plane * bytes_per_line + x] for plane in range(planes)))
    return width, height, planes, pixels


class PngPremultipliedAlpha(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.exe = build_harness()

    def convert(self, png: bytes):
        with tempfile.TemporaryDirectory(prefix='premul-') as tmp:
            png_path = Path(tmp) / 'in.png'
            pcx_path = Path(tmp) / 'out.pcx'
            png_path.write_bytes(png)
            code, message = run_harness(self.exe, png_path, pcx_path)
            self.assertEqual(code, 0, message)
            return decode_pcx(pcx_path.read_bytes())

    def test_semi_transparent_is_premultiplied(self):
        # 非预乘的纯青 + a=128：预乘后 RGB 必须塌到 128，alpha 保持不变。
        width, height, planes, pixels = self.convert(
            make_png(1, 1, 6, [[(0, 255, 255, 128)]], [0]))
        self.assertEqual((width, height, planes), (1, 1, 4))
        self.assertEqual(pixels[0], (0, 128, 128, 128))

    def test_opaque_pixels_are_untouched(self):
        width, height, planes, pixels = self.convert(
            make_png(2, 1, 6, [[(200, 100, 50, 255), (0, 90, 106, 255)]], [0]))
        self.assertEqual(pixels[0], (200, 100, 50, 255))
        self.assertEqual(pixels[1], (0, 90, 106, 255))

    def test_fully_transparent_goes_to_zero(self):
        # 作者把 alpha=0 的像素写成白的也很常见 —— 预乘后必须变黑，不能留下白点。
        width, height, planes, pixels = self.convert(
            make_png(1, 1, 6, [[(255, 255, 255, 0)]], [0]))
        self.assertEqual(pixels[0], (0, 0, 0, 0))

    def test_white_times_alpha_matches_vanilla(self):
        # 本体的"白 × alpha"是 `RGB == a`；舍入必须是 `(v*a+127)/255` 这一条。
        for alpha in (1, 37, 128, 200, 254):
            width, height, planes, pixels = self.convert(
                make_png(1, 1, 6, [[(255, 255, 255, alpha)]], [0]))
            self.assertEqual(pixels[0], (alpha, alpha, alpha, alpha), f'alpha={alpha}')

    @unittest.skipUnless(AURI_CROWN_PNG.exists(), 'Auri 原包不在本机')
    def test_real_auri_crown_is_never_brighter_than_alpha(self):
        # 现场那张图：735 个半透明像素原本全是 (0,255,255)；预乘后必须满足 `max(RGB) <= a`
        # （这正是本体 spotlight.pcx / crackthesky.pcx 的不变式）。
        result = subprocess_run(self.exe, AURI_CROWN_PNG)
        width, height, planes, pixels = result
        self.assertEqual((width, height, planes), (64, 64, 4))
        offenders = [px for px in pixels if 0 < px[3] < 255 and max(px[0], px[1], px[2]) > px[3]]
        self.assertEqual(offenders, [], f'{len(offenders)} 个半透明像素仍亮于 alpha')


def subprocess_run(exe, png_path):
    with tempfile.TemporaryDirectory(prefix='premul-real-') as tmp:
        pcx_path = Path(tmp) / 'out.pcx'
        code, message = run_harness(exe, png_path, pcx_path)
        if code != 0:
            raise AssertionError(message)
        return decode_pcx(pcx_path.read_bytes())
