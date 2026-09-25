#!/usr/bin/env python3
"""把"模组"那一行做成**贴图**（而不是用字体画），并生成可覆盖本体的两份美术文件。

## 为什么走贴图（2026-09-22 用户定案，原话）

> 「你不能看看其他的行代码是这么写的，按它们的来写吗？为什么要自己一个个调？」

答案：**那五行根本不是"代码画的"，是 `gamemenu.anm2` 的五张手绘贴图**（`Item1`~`Item5`），
引擎只是渲染 ANM2。所以我们这一行也应该是**一层贴图** —— 位置/大小/倾角/跟着纸滑全部自动一致，
运行时的那些手调（挪行、画字、字号）全部可以删掉。

## 那"模组"这两个字从哪来

**从游戏自己的美术里剪**：每个语言包的**模组页**（`modsmenu.pcx`）标题条上，
就画着那个语言的"模组/MODS"手绘字（实测：`zh` = 「模组」、`kr` = 韩文、`de`/`fr`/`ru`/`es` = 拉丁字母那套），
和选择界面那五行是**同一套笔**。⇒ 不需要自己画，也不需要 PC 版资源（本机 PC 目录里没有美术）。

## 生成什么

**贴图就是游戏自己画的那一行 —— 不剪、不缩放、不旋转。**

整份游戏资源里**只有法语**把这一行登记进了 ANM2（`<Layer Name="Item6" Id="12" .../>`，
帧 `XCrop=195 YCrop=475 80×39`、pivot `(16,16)`，画的就是那个语言的「模组/MODS」）；
**其它语言的 ANM2 里没有这一层，但图集里那一块美术照样在**（只有法语引用它）
⇒ 拿法语那一帧的 crop 当模板，去**每个语言自己的图集**里取同一块。

> 这一条是用户点出来的（"你确定你找对了……正确的图片资源吗"）。之前我找错了：
> 用的是**模组页标题纸带**上的字（另一张版面、更大、更斜），再缩放 + 旋转去凑周围几行，
> 凑出来就是"像截图贴在纸上"。现在用的是游戏自己写在纸上的那两个字，1:1 取用。

然后排位置：**六个格子的页内位置一个字都不算** —— 直接照搬 PC 版**同一语言**那份
`gamemenu.anm2` 里写死的坐标（见下一节）。本语言自己的 `gamemenu.anm2` 只用来回答
"引擎那五行原本在哪、光标有几帧"（行要挪多少 = PC 的位置 − 本语言的原始位置）。

产物：`--emit-layouts <path>` 生成运行时头文件 `runtime/source/mod_row_generated.hpp`
（八个语言各一套：那一块贴图的 PCX 字节 + 布局常量）。运行时按游戏的语言码挑一套，
**不依赖任何可被关闭的模组、也不在卡上放文件**。

## 排版的"真值源"：**PC 版同一语言**的那份 `gamemenu.anm2`（`reference-pc/lang/<语言>/`）

用户的要求（2026-09-22 晚）："你不要改了，先查清楚 pc 到底是如何处理的"。

查清楚的结果是：**PC 不做任何"算间距"这件事** —— 它在 `gamemenu.anm2` 里把六行写死成绝对坐标：

| 行 | 图层 | 位置 (X,Y) | 轴心 | 画在页面的哪一块 |
| --- | --- | --- | --- | --- |
| 新游戏 | Item1 | 177,34 | 0,0 | 34 起 |
| 继续游戏 | Item2 | 177,59 | 0,0 | 59 起 |
| 挑战 | Item3 | 180,87 | 0,0 | 87 起 |
| **模组** | **Item6** | 201,139 | **16,16** | **123..162** |
| 统计数据 | Item4 | 187,150 | 0,0 | 150 起 |
| 选项 | Item5 | 192,177 | 0,0 | 177 起 |

也就是说：**"模组"在 PC 里不是插进去的，它本来就占着一格**；挑战(87) 与统计数据(150) 之间
那 63 格的空档就是留给它的。Switch 版**删掉了 `Item6` 这一层**，并把剩下五行重新压成
39/68/103/138/172（法语那份 Switch 资源是 PC 的原件，没被改过 ⇒ 它是"开关被删之前"的样子）。

所以本工具的做法是：**八个语言各自读 PC 版同一语言的 `gamemenu.anm2`，把六个页内 y 照搬下来**
（`pc_language_layout()`），一个字都不自己算。各语言的 X 也照搬 PC 的框（`Item6` 的
`201−16 = 185`）。

用法（`reference-pc/lang/` 缺了就会直接报错并说明去哪取，见 `docs/PC-主菜单参考资源.md`）：
    python3 tools/gamemenu_mod_row.py --dump-root "<游戏 dump>/Program #0/1" \
        --emit-layouts runtime/source/mod_row_generated.hpp     # 八个语言一次生成
    python3 tools/gamemenu_mod_row.py --dump-root "<游戏 dump>/Program #0/1" \
        --language zh --mockup /tmp/menu-zh.png                 # 离线看"这一列长什么样"
"""

from __future__ import annotations

import argparse
import os
import re
import struct
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from tools.png_to_pcx import _encode_pcx  # noqa: E402  （仓库自带的 PCX 编码器）

#: 每种语言"带语言后缀"的美术根（相对游戏 dump 根；`Program #0/1/` 之下）。
#: 这只是**语言包那一层**；实际找文件要按 `mount_root_order()` 的顺序穿过好几层。
LANGUAGE_ROOTS = {
    "en": "rp_patch/resources",
    "de": "rp_patch/resources.de",
    "es": "rp_patch/resources.es",
    "fr": "rp_patch/resources.fr",
    "jp": "rp_patch/resources.jp",
    "kr": "rp_patch/resources.kr",
    "ru": "rp_patch/resources.ru",
    "zh": "rp_patch/resources.zh",
}

MODS_PAGE = "gfx/ui/main menu/modsmenu.pcx"
GAMEMENU_PCX = "gfx/ui/main menu/gamemenu.pcx"
GAMEMENU_ANM2 = "gfx/ui/main menu/gamemenu.anm2"

#: 光标层的 layer id（`Cursor`）。它有几帧**逐语言不同**（中文 5 帧、英文 6 帧），必须读。
CURSOR_LAYER_ID = 6
#: 五行在 ANM2 里的图层名（按这一列的顺序）。
ROW_LAYER_NAMES = ("Item1", "Item2", "Item3", "Item4", "Item5")
#: 图层名 → id 用不上（各语言 id 都是 1..5），但保留这条顺序表，避免散在各处。
#: 行图在 ANM2 里是 128×48；"第 6 行"那一块实测 80×39（模板从法语的 ANM2 里读，不写死）。
#: 量"纸的可用带"时看的列范围（= 行图所在的列，`Item1..Item5` 的 crop 都在 179..313 里）。
PAPER_MEASURE_X = (185, 313)
#: "还是纸色"的亮度下限（用来把纸下面的**阴影**从纸里分出去，见 `paper_band`）。
PAPER_LUMINANCE = 190.0
#: 量出来的带子"不像纸"的两个判据（英文那套的底是不透明背景 ⇒ 两个都超），见 `measure_paper_bands`：
#: ① 带子高过图集的这个比例；② 带子中间那一行"不透明像素"占宽的比例。
PAPER_BAND_SANITY = 0.6
PAPER_WIDTH_SANITY = 0.9

#: 我们那一行落在第几格（0 起）—— 3 = 挑战与统计数据之间。
MOD_ENTRY_SLOT = 3
#: "原版自己那一行"的判据（见 `vanilla_mods_row`）：图层 id ≥ 12、宽 ≥ 48、高 24..64。
EXTRA_ROW_LAYER_MIN = 12
ROW_WIDTH_MIN = 48
ROW_HEIGHT_MIN = 24
ROW_HEIGHT_MAX = 64
#: 六格（含我们那一格）与五行（引擎自己那几行）的个数 —— 生成的表里按这两个数定长。
SLOT_COUNT = 6
ENGINE_ROW_COUNT = 5

#: 找"标题纸带里的那几个字"时用的判据（见 `extract_word`）：
#: 纸带外框的填充率实测约 6%，字是 55%~67% ⇒ 这一条能把"外框"和"笔画"分开。
PANEL_MARGIN = 6
GLYPH_MIN_HEIGHT = 10
GLYPH_MIN_FILL = 0.2


class ArtError(RuntimeError):
    pass


# ---------------------------------------------------------------------------
# PCX 读写（四平面 RGBA；编码复用仓库自带的 `_encode_pcx`）
# ---------------------------------------------------------------------------


@dataclass
class Image:
    width: int
    height: int
    rgba: bytearray  # 行优先，每像素 4 字节

    def pixel(self, x: int, y: int) -> tuple[int, int, int, int]:
        base = (y * self.width + x) * 4
        return (self.rgba[base], self.rgba[base + 1], self.rgba[base + 2],
                self.rgba[base + 3])

    def set_pixel(self, x: int, y: int, value: tuple[int, int, int, int]) -> None:
        base = (y * self.width + x) * 4
        self.rgba[base:base + 4] = bytes(value)

    def blank(self, width: int, height: int) -> "Image":
        return Image(width, height, bytearray(width * height * 4))


def decode_pcx(path: str) -> Image:
    data = open(path, "rb").read()
    if not data or data[0] != 0x0A:
        raise ArtError(f"{path} 不是 PCX")
    planes = data[65]
    bpr = struct.unpack_from("<H", data, 66)[0]
    width, height = struct.unpack_from("<HH", data, 8)
    width += 1
    height += 1
    if planes != 4 or data[3] != 8:
        raise ArtError(f"{path} 不是四平面 8 位 PCX（planes={planes} bpp={data[3]}）")
    total = planes * bpr
    cursor = 128
    rgba = bytearray(width * height * 4)
    for y in range(height):
        line = bytearray()
        while len(line) < total:
            value = data[cursor]
            cursor += 1
            if value >= 0xC0:
                run = value & 0x3F
                line += bytes([data[cursor]]) * run
                cursor += 1
            else:
                line.append(value)
        for x in range(width):
            base = (y * width + x) * 4
            rgba[base] = line[x]
            rgba[base + 1] = line[bpr + x]
            rgba[base + 2] = line[2 * bpr + x]
            rgba[base + 3] = line[3 * bpr + x]
    return Image(width, height, rgba)


def encode_pcx(image: Image) -> bytes:
    return _encode_pcx(image.width, image.height, bytes(image.rgba))


# ---------------------------------------------------------------------------
# 纯函数（宿主门禁直接测这些）
# ---------------------------------------------------------------------------


def ink_bbox(image: Image, box: tuple[int, int, int, int]) -> tuple[int, int, int, int] | None:
    """在 `box = (x0, y0, x1, y1)` 里找"深色不透明笔画"的包围盒（闭区间返回）。"""
    x0, y0, x1, y1 = box
    left = top = 1 << 30
    right = bottom = -1
    for y in range(max(0, y0), min(image.height, y1 + 1)):
        for x in range(max(0, x0), min(image.width, x1 + 1)):
            r, g, b, a = image.pixel(x, y)
            if a > 120 and (0.299 * r + 0.587 * g + 0.114 * b) < 150:
                left = min(left, x)
                right = max(right, x)
                top = min(top, y)
                bottom = max(bottom, y)
    if right < 0:
        return None
    return (left, top, right, bottom)


def _dark_components(image: Image, box: tuple[int, int, int, int],
                     threshold: float = 150.0) -> list[tuple[int, int, int, int, int]]:
    """在 `box` 里找深色像素的 4 邻接连通块，返回 `(x0, y0, x1, y1, 像素数)`（按像素数降序）。"""
    x0, y0, x1, y1 = box
    mask: set[tuple[int, int]] = set()
    for y in range(max(0, y0), min(image.height, y1 + 1)):
        for x in range(max(0, x0), min(image.width, x1 + 1)):
            r, g, b, a = image.pixel(x, y)
            if a > 120 and (0.299 * r + 0.587 * g + 0.114 * b) < threshold:
                mask.add((x, y))
    seen: set[tuple[int, int]] = set()
    found: list[tuple[int, int, int, int, int]] = []
    for start in mask:
        if start in seen:
            continue
        seen.add(start)
        stack = [start]
        pixels: list[tuple[int, int]] = []
        while stack:
            cx, cy = stack.pop()
            pixels.append((cx, cy))
            for neighbour in ((cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)):
                if neighbour in mask and neighbour not in seen:
                    seen.add(neighbour)
                    stack.append(neighbour)
        xs = [p[0] for p in pixels]
        ys = [p[1] for p in pixels]
        found.append((min(xs), min(ys), max(xs), max(ys), len(pixels)))
    return sorted(found, key=lambda entry: -entry[4])


def _ink_points(sheet: Image, crop: tuple[int, int, int, int]) -> list[tuple[int, int]]:
    """`crop`（x0,y0,x1,y1）里"深色不透明"的像素点（框内坐标）。"""
    x0, y0, x1, y1 = crop
    points = []
    for y in range(max(0, y0), min(sheet.height, y1 + 1)):
        for x in range(max(0, x0), min(sheet.width, x1 + 1)):
            r, g, b, a = sheet.pixel(x, y)
            if a > 120 and (0.299 * r + 0.587 * g + 0.114 * b) < 150:
                points.append((x - x0, y - y0))
    return points


def fit_slant(points: list[tuple[int, int]]) -> float:
    """线性拟合"逐列墨迹重心"的斜率（**负 = 往右上升**）。样本不够返回 0。"""
    columns: dict[int, list[int]] = {}
    for x, y in points:
        columns.setdefault(x, []).append(y)
    samples = [(x, sum(ys) / len(ys)) for x, ys in sorted(columns.items()) if len(ys) >= 2]
    if len(samples) < 8:
        return 0.0
    count = len(samples)
    mean_x = sum(sample[0] for sample in samples) / count
    mean_y = sum(sample[1] for sample in samples) / count
    numerator = sum((x - mean_x) * (y - mean_y) for x, y in samples)
    denominator = sum((x - mean_x) ** 2 for x, _ in samples)
    return numerator / denominator if denominator else 0.0


def unrotate(points: list[tuple[float, float]], slope: float) -> list[tuple[float, float]]:
    """把"沿着斜率 slope 往右上升"的字**转正**（返回转正后的点）。"""
    import math
    angle = math.atan(slope)
    cosine, sine = math.cos(angle), math.sin(angle)
    return [(x * cosine + y * sine, -x * sine + y * cosine) for x, y in points]


def row_slant(rows) -> float:
    """那支笔的**倾斜**：五行各自拟合，取中位数（实测中文 ≈ -0.17，即往右上升约 10°）。

    为什么要量它（用户两次说过"字还是笔直的"）：选择界面那五行**本身就是斜着写的**，
    从模组页标题带上剪下来的字却是**正的** ⇒ 直接摆上去风格就不对。
    """
    slopes = sorted(row["slant"] for row in rows if "slant" in row)
    return slopes[len(slopes) // 2] if slopes else 0.0


def envelope_slant(points: list[tuple[int, int]]) -> float:
    """墨迹**上下包络**的斜率（Theil–Sen：所有点对斜率取中位数 ⇒ 对离群点稳健）。

    为什么不用"逐列重心拟合"（`fit_slant`）：那个估计量对**字的形状**很敏感，
    同一支笔写的两个字读音能差一倍（中文那五行：重心拟合读 -0.17，而包络读 -0.22）。
    包络量的是"这行字整体往哪个方向走"，与眼睛看到的一致 ⇒ 拿它当判据。
    """
    columns: dict[int, list[int]] = {}
    for x, y in points:
        columns.setdefault(x, []).append(y)
    if len(columns) < 8:
        return 0.0
    result = []
    for mode in ("bottom", "top"):
        envelope = [(x, max(ys) if mode == "bottom" else min(ys))
                    for x, ys in sorted(columns.items())]
        slopes = []
        for index in range(len(envelope)):
            for other in range(index + 1, len(envelope)):
                span = envelope[other][0] - envelope[index][0]
                if span >= 6:
                    slopes.append((envelope[other][1] - envelope[index][1]) / span)
        if slopes:
            slopes.sort()
            result.append(slopes[len(slopes) // 2])
    return sum(result) / len(result) if result else 0.0


def image_slant(image: Image) -> float:
    """一张**贴图**里墨迹的斜率（与量游戏美术用的是同一个估计量）。"""
    return envelope_slant(_ink_points(image, (0, 0, image.width - 1, image.height - 1)))


def glyph_height(sheet: Image, rows) -> float:
    """那五行"把字转正以后"有多高（取中位数）。

    为什么不能直接用墨迹包围盒的高度（我第一版就是这么错的）：字是**斜着**写的，
    包围盒高度 = 字高×cos + 字宽×sin ⇒ 中文那五行量出来是 25~34，而**真实的字高只有约 20**
    ⇒ 照包围盒去缩放，我们剪的字会比周围大 40%（用户原话："仍然很大"）。
    """
    heights = []
    for row in rows:
        points = row.get("ink_points")
        if not points:
            continue
        upright = unrotate([(float(x), float(y)) for x, y in points], row.get("slant", 0.0))
        ys = [y for _, y in upright]
        heights.append(max(ys) - min(ys) + 1.0)
    if not heights:
        raise ArtError("量不出字高（那一行没有墨迹）")
    heights.sort()
    return heights[len(heights) // 2]


def read_layers(xml: str, animation: str = "Idle"):
    """从 ANM2 里读出每个图层的 id/名字，以及某个动画里**每一层的第一帧**。

    ★ 属性顺序**逐语言不同**（实测：法语那份写的是 `<Layer Name="Main" Id="0" .../>`，
    其它语言是 `<Layer Id="0" Name="Main" .../>`）⇒ 不能按固定顺序配对，
    这里统一按"属性名 → 值"解析。
    """
    start = xml.find('Name="%s"' % animation)
    body = xml[start:] if start >= 0 else xml
    frames = {}
    for match in re.finditer(r'<LayerAnimation ([^>]*)>\s*<Frame ([^/]*)/>', body, re.S):
        layer_id = int(dict(re.findall(r'(\w+)="([^"]*)"', match.group(1)))["LayerId"])
        frames[layer_id] = dict(re.findall(r'(\w+)="([^"]*)"', match.group(2)))
    names = {}
    for match in re.finditer(r'<Layer ([^>]*?)/?>', xml):
        attrs = dict(re.findall(r'(\w+)="([^"]*)"', match.group(1)))
        if "Id" in attrs and "Name" in attrs:
            names[int(attrs["Id"])] = attrs["Name"]
    return names, frames


def row_geometry(xml: str, sheet: Image):
    """每一行的"框顶 Y"与"字在框内的墨迹范围"（框内坐标，从图集里量）。"""
    names, frames = read_layers(xml)
    rows = []
    for name in ROW_LAYER_NAMES:
        layer_id = next((i for i, n in names.items() if n == name), None)
        if layer_id is None or layer_id not in frames:
            raise ArtError(f"ANM2 里没有 {name} 的那一帧")
        frame = frames[layer_id]
        crop_x = int(float(frame["XCrop"]))
        crop_y = int(float(frame["YCrop"]))
        width = int(float(frame["Width"]))
        height = int(float(frame["Height"]))
        box = (crop_x, crop_y, crop_x + width - 1, crop_y + height - 1)
        bbox = ink_bbox(sheet, box)
        if bbox is None:
            raise ArtError(f"{name} 的贴图里没找到笔画")
        points = _ink_points(sheet, box)
        rows.append({
            "name": name,
            "layer_id": layer_id,
            "y": float(frame["YPosition"]),
            "x": float(frame["XPosition"]),
            "ink_left": bbox[0] - crop_x,
            "ink_top": bbox[1] - crop_y,
            "ink_bottom": bbox[3] - crop_y,
            #: 字**左边缘**与**中心**在页内的横坐标（对齐用：原版是按左边缘对齐的）
            "ink_page_left": float(frame["XPosition"]) + bbox[0] - crop_x,
            "ink_center_x": float(frame["XPosition"]) + (bbox[0] + bbox[2] - 2 * crop_x) / 2.0,
            #: 这一行墨迹的**框内**点与拟合出来的斜率（那支笔写得多斜）—— 见 `fit_slant`
            "ink_points": points,
            "slant": envelope_slant(points),
        })
    return rows


def _extra_row_frame(xml: str) -> dict | None:
    """ANM2 里"多出来的那一行"（图层 `Id ≥ 12`、帧是行状）的那一帧；没有返回 `None`。"""
    _, frames = read_layers(xml)
    for layer_id in sorted(frames):
        if layer_id < EXTRA_ROW_LAYER_MIN:
            continue
        frame = frames[layer_id]
        width, height = int(float(frame["Width"])), int(float(frame["Height"]))
        if width >= ROW_WIDTH_MIN and ROW_HEIGHT_MIN <= height <= ROW_HEIGHT_MAX:
            return frame
    return None


#: ★★ PC 版主菜单的**字位置**与光标六帧 —— 2026-09-22 晚从 PC 文件里读出来的真值
#: （用户要求："你不能做到一次性获取 pc 上如何处理的间距然后复用吗" ⇒ 能）。
#:
#: 来源（可复核）：用游戏自带的官方解包器（`tools/ResourceExtractor/macOS/ResourceExtractor`）
#: 把 PC 的 `resources/packed/repentance.a` 解开，读
#:   `resources-dlc3/gfx/ui/main menu/gamemenu.anm2`（12068 字节 /
#:    sha256 `ea11d9559724c537094f365ca3642edcf4aa9747c29712bc672e31ba8f24f535`）
#: 与同目录的 `gamemenu.png`：
#:
#:   六行的**框顶** = 34 / 59 / 87 / **139（Item6，就是「模组」那一行）** / 150 / 177
#:   六行的**字**（框顶 + 框内字位；Item6 还有 pivot (16,16)）落在页面
#:        43..74 / 69..99 / 94..128 / 126..159 / 161..188 / 186..217
#:        ⇒ **字中心 58.5 / 84 / 111 / 142.5 / 174.5 / 201.5**
#:   光标六帧 = 68 / 94 / 122 / 152 / 181 / 211
#:
#: 用法：**按"字中心"对齐**（不是搬框顶）—— 因为各语言的字在框里位置略有不同
#: （中文 Item4 的字顶在框内 +6、法语是 +11），搬框顶会让某些语言撞在一起；
#: 搬"字中心"才是"看上去和 PC 一样"。
#:
#: 另外：**法语那套 Switch 的 ANM2 与 PC 的这份逐字段相同**（法语没被改过），
#: 其它语言才是"删掉这一行 + 把五行挪过"的版本（39/68/103/140/172）—— 所以"按 PC 的来"
#: 等于把法语那套的**字位置**用到所有语言上。
#: PC（英语）六行**字的上下沿**（页面坐标）—— 留着当**门禁锚点**：这一组数字必须与
#: `reference-pc/lang/en/…/gamemenu.anm2` 现场读出来的一致（PC 换了文件就会被发现）。
#: ⚠️ 历史：我一度用"相邻两行的白边"（74→69 = -5、…）来推各语言的位置，那是**错的方向** ——
#: PC 不推任何东西，六行的位置就是文件里写死的数字（见 `pc_language_layout()`）。
PC_ROW_INK = ((43.0, 74.0), (69.0, 99.0), (94.0, 128.0), (126.0, 159.0),
              (161.0, 188.0), (186.0, 217.0))
#: PC（英语）六行的**框顶**页内 y（就是 `YPosition`，`Item6` 减掉轴心 16）—— 同上，锚点用。
PC_ROW_TOP = (34.0, 59.0, 87.0, 123.0, 150.0, 177.0)
PC_CURSOR_Y = (68.0, 94.0, 122.0, 152.0, 181.0, 211.0)
#: PC 参考文件在仓库里的位置（游戏数据，已 gitignore）。存在时门禁会重新读一遍核对上面的数字。
PC_REFERENCE_DIR = os.path.join(REPO_ROOT, "reference-pc", "gfx", "ui", "main menu")
#: ★ 排版的真值源：**PC 版每个语言**的主菜单资源（`reference-pc/lang/<语言>/gfx/ui/main menu/`）。
#: 取法见 `docs/PC-主菜单参考资源.md`（要先用游戏自带的解包器解 `repentance_<语言>.a`）。
PC_LANGUAGE_ROOT = os.path.join(REPO_ROOT, "reference-pc", "lang")


class _SheetView:
    """把 `png_to_pcx._decode()` 出来的 `(w, h, rgba)` 适配成 `Image` 那套只读接口。"""

    def __init__(self, decoded):
        self.width, self.height, self.rgba = decoded

    def pixel(self, x, y):
        base = (y * self.width + x) * 4
        return (self.rgba[base], self.rgba[base + 1], self.rgba[base + 2],
                self.rgba[base + 3])


def pc_layout(pc_anm2_path: str) -> dict:
    """★ 从**PC 版**的 `gamemenu.anm2` 里读出六行的 Y 与光标的六帧 —— 间距的"真值源"。

    用户的要求（2026-09-22 晚）："你不能做到一次性获取 pc 上如何处理的间距然后复用吗"
    —— 能，而且这才是对的做法：PC 那份文件把这些位置写死了，读一次就能八个语言共用。

    读出什么：
      * `rows`：每个"行状图层"（宽 ≥48、高 24..64）的 `YPosition` 与它的 crop
        —— crop 用来和 Switch 那份**同一张美术**对齐（同一行在两边 crop 相同）；
      * `cursor`：光标层的各帧 `YPosition`（PC 是六行 ⇒ 应当有六帧）。

    用法：`--pc-anm2 <PC 的 gamemenu.anm2>`；不给时按"量出来的等间距"排（本项目原来的做法）。
    """
    xml = open(pc_anm2_path, "rb").read().decode("utf-8", "replace")
    names, frames = read_layers(xml)
    rows = []
    for layer_id in sorted(frames):
        name = names.get(layer_id, "")
        # ★ 只认 `Item*` 命名的图层：`DailyText`（118×64）之类按尺寸也会"像一行"，
        #   按名字认才干净（两边的命名约定一样：Item1..Item5 + 多出来的那一行）。
        if not name.startswith("Item"):
            continue
        frame = frames[layer_id]
        width, height = int(float(frame["Width"])), int(float(frame["Height"]))
        rows.append({
            "layer_id": layer_id,
            "name": name,
            "y": float(frame["YPosition"]),
            "crop": (int(float(frame["XCrop"])), int(float(frame["YCrop"])), width, height),
        })
    if len(rows) < SLOT_COUNT:
        raise ArtError(f"PC 那份 ANM2 里只找到 {len(rows)} 个 `Item*` 行图层"
                       f"（要 {SLOT_COUNT} 个）—— 这份文件是不是主菜单的？")
    rows.sort(key=lambda entry: entry["y"])
    try:
        cursor = cursor_frames(xml)
    except ArtError:
        cursor = []
    # 同目录下的 `gamemenu.png`（PC 的图集）⇒ 把每一行"字"在页面上的位置算出来。
    sheet = None
    png_path = os.path.join(os.path.dirname(pc_anm2_path), "gamemenu.png")
    if os.path.exists(png_path):
        try:
            from tools.png_to_pcx import _decode
            width, height, rgba = _decode(open(png_path, "rb").read())
            sheet = (width, height, rgba)
        except Exception:
            sheet = None
    for entry in rows:
        crop_x, crop_y, width, height = entry["crop"]
        # Item6 那一行有 pivot (16,16)，框顶要减去它才是贴图的左上角
        pivot_y = 16.0 if entry["name"] == "Item6" else 0.0
        page_top = entry["y"] - pivot_y
        entry["page_top"] = page_top
        if sheet is None:
            continue
        image = sheet
        bbox = ink_bbox(_SheetView(image), (crop_x, crop_y, crop_x + width - 1,
                                            crop_y + height - 1))
        if bbox is None:
            continue
        entry["ink_page_top"] = page_top + (bbox[1] - crop_y)
        entry["ink_page_bottom"] = page_top + (bbox[3] - crop_y)
        entry["ink_center"] = (entry["ink_page_top"] + entry["ink_page_bottom"]) / 2.0
    return {"rows": rows, "cursor": cursor, "source": os.path.abspath(pc_anm2_path)}


def pc_language_layout(language: str, pc_root: str | None = None) -> dict:
    """★ 读 **PC 版同一语言**的 `gamemenu.anm2` ⇒ 六个格子的**绝对页内位置**（排版的真值源）。

    为什么按语言分开读（2026-09-22 深夜，用户："pc版的中文是在忏悔dlc中的"）：
    PC 的忏悔 DLC 里八种语言各有一份主菜单资源（`resources-dlc3.<语言>/…`），
    它们**不是同一份文件**——德语的"挑战"那一行是一整条 88 格高的斜横幅、西班牙语的
    第一行在 y=37、其余语言与英语一致。所以"PC 怎么做"要**按语言问 PC 自己**，
    而不是拿英语那份套到八个语言上。

    读出什么（key = 格子号 0..5，与运行时的 `slot` 同一套编号）：
      * `page_top`：这一格**框的左上角**在页内的 y。`Item6`（模组）有轴心 (16,16)，
        所以 `page_top = YPosition − YPivot`（PC 的 139 ⇒ 123）；
      * `page_x`：同上取 x（`Item6` 的 201−16 = 185）；
      * `cursor`：光标层的六帧 y（PC 一行一帧，正好六帧）。
    排序按 y 自然得到 新游戏/继续游戏/挑战/**模组**/统计数据/选项 —— `Item6` 在 139，
    正好落在挑战(87) 与统计数据(150) 之间。
    """
    root = pc_root or PC_LANGUAGE_ROOT
    path = os.path.join(root, language, "gfx", "ui", "main menu", "gamemenu.anm2")
    if not os.path.exists(path):
        raise ArtError(f"找不到 PC 版 {language} 的 gamemenu.anm2（{path}）—— "
                       f"排版真值源就没了；怎么取得见 docs/PC-主菜单参考资源.md")
    layout = pc_layout(path)
    rows = layout["rows"][:SLOT_COUNT]
    if len(rows) < SLOT_COUNT:
        raise ArtError(f"PC 版 {language} 那份只有 {len(rows)} 行（要 {SLOT_COUNT} 行）")
    # 轴心与 x 要另取一次（`pc_layout()` 只留了 y 与 crop）：按图层名建索引，
    # 这样"哪个 Item 是哪一格"不靠编号硬编码（PC 的 Item6 是 Id=12、排在 Item5 后面）。
    raw = open(path, "rb").read().decode("utf-8", "replace")
    names, frames = read_layers(raw)
    first = {names[layer_id]: frame for layer_id, frame in frames.items()
             if layer_id in names}
    slots = []
    for slot, entry in enumerate(rows):
        frame = first.get(entry["name"], {})
        pivot_x = float(frame.get("XPivot", 0.0))
        pivot_y = float(frame.get("YPivot", 0.0))
        crop_x, crop_y, width, height = entry["crop"]
        slots.append({"slot": slot, "name": entry["name"],
                      "page_top": float(entry["y"]) - pivot_y,
                      "page_x": float(frame.get("XPosition", 0.0)) - pivot_x,
                      "crop": (crop_x, crop_y, width, height)})
    cursor = [float(value) for value in layout["cursor"]]
    if len(cursor) < SLOT_COUNT:
        raise ArtError(f"PC 版 {language} 的光标只有 {len(cursor)} 帧（六行要六帧）")
    return {"language": language, "slots": slots, "cursor": cursor,
            "source": layout["source"]}


def pc_language_layouts(pc_root: str | None = None) -> dict[str, dict]:
    """八个语言的 PC 布局（生成时一次读完，逐语言使用）。"""
    return {language: pc_language_layout(language, pc_root)
            for language in sorted(LANGUAGE_ROOTS)}


def sixth_row_region(dump_root: str) -> dict:
    """**模板**：从法语那份 `gamemenu.anm2` 里读出"第 6 行"那一块（crop + pivot）。

    为什么不写死坐标：整份游戏资源里**只有法语**把这一行登记进了 ANM2
    （`<Layer Name="Item6" Id="12" .../>`，帧 `XCrop=195 YCrop=475 80×39`、pivot `(16,16)`），
    而那一行画的正是那个语言的「模组/MODS」。其它语言的 ANM2 里**没有这一层，
    但图集里那一块美术照样在**（只有法语引用了它）⇒ 拿法语那一帧的 crop 当模板，
    去每个语言自己的图集里取同一块 —— 于是拿到的是**游戏自己画的、尺寸/斜度/笔触
    都与其它行一致**的那两个字（不是从别的页面剪下来再缩放旋转的）。

    ★ 这一步是用户点出来的："你确定你找对了……正确的图片资源吗" —— 之前确实找错了：
    我用的是**模组页标题纸带**上的字（另一张版面、更大、更斜），再缩放+旋转去凑，
    凑出来就是"像截图贴在纸上"。
    """
    path = resolve_content_file(dump_root, "fr", GAMEMENU_ANM2)
    xml = open(path, "rb").read().decode("utf-8")
    frame = _extra_row_frame(xml)
    if frame is None:
        raise ArtError("法语那份 ANM2 里找不到第 6 行（`Item6`）—— 模板就没了")
    return {"crop_x": int(float(frame["XCrop"])), "crop_y": int(float(frame["YCrop"])),
            "width": int(float(frame["Width"])), "height": int(float(frame["Height"])),
            "pivot_x": float(frame["XPivot"]), "pivot_y": float(frame["YPivot"])}


def sixth_row_art(sheet: Image, region: dict) -> tuple[Image, tuple[int, int, int, int]] | None:
    """在某个语言的图集里取出模板那一块；那一块是空的返回 `None`。

    返回 `(那一块的图, 框内墨迹包围盒)`。
    """
    cx, cy = region["crop_x"], region["crop_y"]
    width, height = region["width"], region["height"]
    if cx + width > sheet.width or cy + height > sheet.height:
        return None
    bbox = ink_bbox(sheet, (cx, cy, cx + width - 1, cy + height - 1))
    if bbox is None:
        return None
    image = Image(width, height, bytearray(width * height * 4))
    for y in range(height):
        for x in range(width):
            image.set_pixel(x, y, sheet.pixel(cx + x, cy + y))
    return image, (bbox[0] - cx, bbox[1] - cy, bbox[2] - cx, bbox[3] - cy)


def vanilla_mods_row(xml: str, sheet: Image) -> dict | None:
    """该语言的 ANM2 里**已经**有一行"模组"图层时把它读出来（没有返回 `None`）。

    ★★ 2026-09-22 晚的发现（把八个语言的 `gamemenu.anm2` 一起看才发现的）：
    **法语那套本来就多一行** —— `<Layer Name="Item6" Id="12" SpritesheetId="0"/>`，
    帧是 `XPosition=201 YPosition=139 XPivot=16 YPivot=16 XCrop=195,475 80×39`，
    把那块 crop 解出来按字符画看，画的就是 **MODS**（游戏自己那支笔、和另外五行一模一样）；
    而且法语那五行的 Y 也已经为它让好了位（34/59/87/**139**/150/177，光标 6 帧）。

    为什么这一段值得写：这一条**证明了"引擎会把 ANM2 里所有图层都画出来"**
    （`Menu_Game::Render` 里 `ANM2::Render` 只有一处，它画整个动画 ⇒ 法语版真机上本来就
    显示着这一行、只是选不中）。⇒ 对这样的语言，我们**不要**自己排、也**不要**自己画，
    直接用它自己的美术与位置，运行时只补"能选中 + 能进页面"那部分。

    判据：图层 `Id ≥ 12`（0..11 是八个语言都有的那十二层）且帧是"一行"的形状
    （宽 ≥ 48、高 24..64）。
    """
    _, frames = read_layers(xml)
    for layer_id in sorted(frames):
        if layer_id < EXTRA_ROW_LAYER_MIN:
            continue
        frame = frames[layer_id]
        width = int(float(frame["Width"]))
        height = int(float(frame["Height"]))
        if width < ROW_WIDTH_MIN or not (ROW_HEIGHT_MIN <= height <= ROW_HEIGHT_MAX):
            continue
        crop_x, crop_y = int(float(frame["XCrop"])), int(float(frame["YCrop"]))
        bbox = ink_bbox(sheet, (crop_x, crop_y, crop_x + width - 1, crop_y + height - 1))
        if bbox is None:
            continue
        image = Image(width, height, bytearray(width * height * 4))
        for y in range(height):
            for x in range(width):
                image.set_pixel(x, y, sheet.pixel(crop_x + x, crop_y + y))
        pivot_x, pivot_y = float(frame["XPivot"]), float(frame["YPivot"])
        return {
            "layer_id": layer_id,
            "image": image,
            "page_x": float(frame["XPosition"]) - pivot_x,
            "page_y": float(frame["YPosition"]) - pivot_y,
            "ink_top": bbox[1] - crop_y,
            "ink_bottom": bbox[3] - crop_y,
            "ink_center_x": float(frame["XPosition"]) - pivot_x
                             + (bbox[0] + bbox[2] - 2 * crop_x) / 2.0,
        }
    return None


def paper_band(sheet: Image, x_range: tuple[int, int] = PAPER_MEASURE_X) -> tuple[float, float]:
    """纸的**可用带**：行图所在那几列里，"每一列都还是纸"的纵向范围（取交集 ⇒ 保守值）。

    上下沿用的判据**不一样**，各有一条实测理由（中文件的 `gamemenu.pcx` 逐像素看过）：

    * **上沿**：整列都变成不透明（alpha > 120）的那一行 —— 纸的上边是一条从透明渐入的软边，
      取"每一列都已经进来了"最稳（实测 36）；
    * **下沿**：整列都还是**纸色**（亮，亮度 > `PAPER_LUMINANCE`）的最后一行 ——
      纸的下面是**画在背景上的阴影**（实测 x=310 处：纸色到 213、阴影到 218、半透明黑到 222），
      只看"不透明"会把阴影也算成纸（得出 218，比真纸多 5 格）。

    为什么必须取交集：撕边是**斜的**（x=175 处纸到 228、x=310 处只到 213），
    只要有一列在某一行已经不是纸，那一行就不能放东西 —— 046/047 两批把 OPTIONS 挤出纸外，
    正是因为没有"取交集"这一步。
    """
    firsts: list[int] = []
    lasts: list[int] = []
    for x in range(x_range[0], x_range[1] + 1):
        column = [y for y in range(sheet.height) if sheet.pixel(x, y)[3] > 120]
        if not column:
            continue
        firsts.append(min(column))
        paper = [y for y in column
                 if 0.299 * sheet.pixel(x, y)[0] + 0.587 * sheet.pixel(x, y)[1]
                 + 0.114 * sheet.pixel(x, y)[2] > PAPER_LUMINANCE]
        if paper:
            lasts.append(max(paper))
    if not firsts or not lasts:
        raise ArtError("量纸的边界时那一列全透明（美术不对？）")
    return float(max(firsts)), float(min(lasts))


def cursor_frames(xml: str) -> list[float]:
    """`Cursor` 层（`Id=6`）在 `Idle` 里各帧的 `YPosition`（= 光标**中心**的页内 y）。

    ★ 逐语言读的理由：中文版只有 **5 帧**、英文版有 **6 帧**，而且同一个格子的 y 差 1~2 格
    （中文 73/105/140/171/207、英文 72/102/138/169/206）。项目里 049 批的手写表是照英文那套抄的。
    """
    idle = xml[xml.find('Name="Idle"'):]
    match = re.search(r'<LayerAnimation LayerId="' + str(CURSOR_LAYER_ID) + r'"[^>]*>(.*?)</LayerAnimation>',
                      idle, re.S)
    if match is None:
        raise ArtError("ANM2 里没有光标层的那一段")
    ys = [float(m.group(1)) for m in re.finditer(r'YPosition="([-\d.]+)"', match.group(1))]
    if len(ys) < ENGINE_ROW_COUNT:
        raise ArtError(f"光标层只有 {len(ys)} 帧，少于引擎的五格")
    return ys


def mount_root_order(language: str) -> list[str]:
    """该语言下"内容挂载点的查找顺序"（前 = 优先）。

    实测：补丁层（`rp_patch/...`）压着基础层（`resources*`）；带语言后缀的优先于不带后缀的。
    `en` 没有 `rp_patch/resources.en`（英文就是基础那套），所以它只有两层。
    """
    if language == "en":
        return ["rp_patch/resources", "resources"]
    # `LANGUAGE_ROOTS` 里的值已经带 `rp_patch/` 前缀；最后那条是基础层里同名语言目录（日/韩有）。
    return [LANGUAGE_ROOTS[language],
            "rp_patch/resources",
            LANGUAGE_ROOTS[language].replace("rp_patch/", ""),
            "resources"]


def resolve_content_file(dump_root: str, language: str, relative: str) -> str:
    """按"内容挂载点的查找顺序"找文件（同一个文件可能分处不同层）。

    实测（本机 dump）：选择界面那几行的美术就分两层 —— `gamemenu.anm2` 在补丁层
    `rp_patch/resources`，而 `gamemenu.pcx` 与 `modsmenu.pcx` 在基础层 `resources`；
    带语言后缀的（中文/韩文…）又在 `rp_patch/resources.<lang>`。所以不能只认一个根。
    """
    for root in mount_root_order(language):
        path = os.path.join(dump_root, root, relative)
        if os.path.exists(path):
            return path
    raise ArtError(f"{language} 找不到 {relative}"
                   f"（按顺序找过：{', '.join(mount_root_order(language))}）")


def measure_paper_bands(dump_root: str) -> dict[str, tuple[float, float]]:
    """八个语言各自量一遍纸的可用带，**量不出来的那套退回参考带**。

    为什么需要这一步（实测）：中文/德/西/法/日/韩/俄那一套量出来都是 `(36, 213)`（与 048 批
    真机上验过的手写值 35/213 一致），而**英文那套的 `gamemenu.pcx` 是一张不透明底的旧版面**
    （整张 480×540 的底都是不透明的）⇒ 量出来是 `(0, 269)`、等于整张图，显然是"没量到纸"。
    判据写成"带子高过图集 60% 就不算数"，参考带取那些**量得出来的**语言的**交集**
    （交集 = 最保守的那个，八个语言的纸本来就是同一张版面）。
    """
    measured: dict[str, tuple[float, float]] = {}
    for language in LANGUAGE_ROOTS:
        sheet = decode_pcx(resolve_content_file(dump_root, language, GAMEMENU_PCX))
        band = paper_band(sheet)
        if band[1] - band[0] + 1 > PAPER_BAND_SANITY * sheet.height:
            continue
        # 横向的判据：纸在某一行上**不可能铺满整张图集**（实测中文 0.37、英文那套 1.00）。
        middle = int((band[0] + band[1]) / 2)
        opaque = sum(1 for x in range(sheet.width) if sheet.pixel(x, middle)[3] > 120)
        if opaque >= PAPER_WIDTH_SANITY * sheet.width:
            continue
        measured[language] = band
    if not measured:
        raise ArtError("八个语言都量不出纸的可用带（美术版面对不上？）")
    reference = (max(band[0] for band in measured.values()),
                 min(band[1] for band in measured.values()))
    return {language: measured.get(language, reference) for language in LANGUAGE_ROOTS}


def build_language(dump_root: str, language: str, output_root: str | None = None,
                   preview: bool = False, sprite_pcx: str | None = None,
                   band: tuple[float, float] | None = None,
                   region: dict | None = None, pc: dict | None = None) -> dict:
    """算出一个语言的全套布局 + 那一行要画的贴图。

    贴图**就是游戏自己画的那一行**（各语言图集里"第 6 行"那一块，1:1 取用，不缩放不旋转）；
    位置/光标/位移仍然按量出来的规则算。
    """
    sheet_path = resolve_content_file(dump_root, language, GAMEMENU_PCX)
    anm2_path = resolve_content_file(dump_root, language, GAMEMENU_ANM2)

    # 1) 量该语言自己的几何：纸的可用带 / 五行的框顶与墨迹 / 光标的各帧
    sheet = decode_pcx(sheet_path)
    with open(anm2_path, "rb") as handle:
        xml = handle.read().decode("utf-8")
    if band is None:
        band = paper_band(sheet)
    rows = row_geometry(xml, sheet)
    frames = cursor_frames(xml)
    vanilla = vanilla_mods_row(xml, sheet)
    slant = row_slant(rows)          # 那支笔有多斜（生成的头里记着，兜底画字与门禁都用）
    target = glyph_height(sheet, rows)  # 字（转正后）有多高 —— 兜底画字按它算字号

    # 2) 我们那一行的贴图：本语言图集里的"第 6 行"那一块；那块是空的就借同一位画的其他语言。
    #    （实测：只有**英文**那套的图集里没有这一行 —— 它是旧版面；而那个词在英/德/西/法
    #      四套里都是 "MODS"、同一支笔 ⇒ 借过来是等价的。）
    if region is None:
        region = sixth_row_region(dump_root)
    if pc is None:
        # 不给 PC 文件也按 PC 那套常量排（"按 PC 的来"是**默认**行为，不是可选参数）
        pc = {"rows": [], "cursor": ()}
    art = sixth_row_art(sheet, region)
    donor = None
    if art is None:
        for candidate in ("fr", "de", "es"):
            if candidate == language:
                continue
            other = decode_pcx(resolve_content_file(dump_root, candidate, GAMEMENU_PCX))
            art = sixth_row_art(other, region)
            if art is not None:
                donor = candidate
                break
    if art is None:
        raise ArtError(f"{language}：图集里找不到第 6 行那一块，而且没有可借的语言")
    sprite, ink_rel = art
    row = sprite                      # ★ 1:1：贴图就是那一块本身（80×39 那种尺寸）
    ink_left, ink_top = float(ink_rel[0]), float(ink_rel[1])
    ink_bottom = float(ink_rel[3])
    ink_height = ink_bottom - ink_top + 1.0

    # 3) 排版：**照搬 PC 同一语言那份 ANM2 里的六个绝对位置**（用户 2026-09-22 晚定）。
    #    PC 里"模组"本来就占一格（`Item6`，框顶 123），其余五行也各有各的写死位置
    #    （英语/中文/日文/韩文/俄语都是 34/59/87/150/177；德语那条"挑战"是 88 格高的斜横幅、
    #      西班牙语第一行在 37）—— 挑战与统计数据之间那 63 格空档就是留给"模组"的。
    #    ⇒ 我们**一格都不算**：六个页内 y 直接取 PC 那份文件的值，横向也取 PC 的框
    #      （`Item6` 的 201−16 = 185）。
    #    ⚠️ 历史（别回头走）：我先后试过"六格等间距""按 PC 的字中心""逐格链 PC 的白边"——
    #      三条都是在**推导**间距，而 PC 根本没有可推导的规律（它的行框 48 高、相邻只隔 25~35，
    #      本来就互相重叠）；推导还把我自己量字高的误差带进了位置里 ⇒ 真机上就是
    #      "这一列偏上"和"模组上下两行的间距变大"。
    #    法语不再单开分支：它的 Switch 资源就是 PC 的原件，照搬 PC 得到的就是"原地不动"
    #    （`shifts` 全 0、与旧输出逐值相同），`vanillaRow` 仍为 1（引擎自己会画那一行）。
    if pc is None:
        raise ArtError(f"{language}：没有 PC 的排版真值源 —— 六个格子的位置必须是 PC 的文件里"
                       f"写死的那些数（见 docs/PC-主菜单参考资源.md）")
    slots = pc["slots"]
    plan = []
    for index, entry in enumerate(rows):
        slot = index if index < MOD_ENTRY_SLOT else index + 1
        plan.append({"name": entry["name"], "layer_id": entry["layer_id"],
                     "y": slots[slot]["page_top"], "background": False})
    new_layer_y = slots[MOD_ENTRY_SLOT]["page_top"]
    sprite_x = slots[MOD_ENTRY_SLOT]["page_x"]
    centers = []
    for slot in range(SLOT_COUNT):
        if slot == MOD_ENTRY_SLOT:
            centers.append(new_layer_y + (ink_top + ink_bottom) / 2.0)
            continue
        entry = rows[slot if slot < MOD_ENTRY_SLOT else slot - 1]
        centers.append(slots[slot]["page_top"]
                       + (entry["ink_top"] + entry["ink_bottom"]) / 2.0)
    cursor_y = [float(pc["cursor"][slot]) for slot in range(SLOT_COUNT)]
    # 光标的**帧号**仍按本语言自己的帧数夹一下（有的语言只有 5 帧）：同一语言里
    # 六帧用的是同一块裁切、只差位置，而位置由我们设的那个 y 决定 ⇒ 夹帧不影响样子。
    cursor_frame = [min(slot, max(len(frames) - 1, 0)) for slot in range(SLOT_COUNT)]
    shifts = [plan[index]["y"] - rows[index]["y"] for index in range(ENGINE_ROW_COUNT)]
    # ★ 横向也照搬 PC 的框 x（用户 2026-09-22 深夜："模组似乎偏左了一点"）。
    #   只搬 Y 的时候，中文那一列的字左是 185/187/192/**189**/195/199 ——「模组」比它上面
    #   那行挑战(192)还靠左 3 格，所以看着偏左；而 PC 中文自己那一列是
    #   183/184/187/**189**/196/199（模组在挑战右边 2 格）。两边的图集是同一块美术
    #   （每行"框内字左"逐行相等），差别只在 ANM2 里的框 x ⇒ 照搬 x 就对了。
    #   ⚠️ 这里第一个版本写成 `slots[slot if index < … else index + 1]` —— 那个 `slot` 不是本
    #      推导式的变量，而是**上面那个 for 循环留下的 `slot = 5`**（Python 的作用域规则会
    #      悄悄用它）⇒ 前三行的 x 全取成了最后一行的框。门禁那条"框 x 必须等于 PC 的值"就是
    #      为了兜住这类错（生成表本身看不出来）。
    shifts_x = [slots[index if index < MOD_ENTRY_SLOT else index + 1]["page_x"] - rows[index]["x"]
                for index in range(ENGINE_ROW_COUNT)]

    #: 六格的横向锚点（页内 x）：就是 PC 的框 x（横向照搬 PC，不插值、不对齐）
    slot_lefts = [float(slots[slot]["page_x"]) for slot in range(SLOT_COUNT)]

    #: 六格的锚点（页内 y）：引擎行 = 挪完之后的框顶，我们那一格 = 贴图顶
    slot_tops = []
    for slot in range(SLOT_COUNT):
        if slot == MOD_ENTRY_SLOT:
            slot_tops.append(new_layer_y)
        else:
            slot_tops.append(plan[slot if slot < MOD_ENTRY_SLOT else slot - 1]["y"])

    if preview:
        width = int(ink_left + (ink_bottom - ink_top) * 0 + (ink_rel[2] - ink_rel[0]))
        print(f"--- {language}：那一行（{sprite.width}×{sprite.height}，字在框内 "
              f"({ink_left:.0f},{ink_top:.0f})..({ink_rel[2]:.0f},{ink_rel[3]:.0f})）---")
        for y in range(ink_rel[1], ink_rel[3] + 1):
            print('   |' + ''.join('#' if sprite.pixel(x, y)[3] > 120 else '.'
                                   for x in range(ink_rel[0], ink_rel[2] + 1)))
        del width

    result = {
        "language": language,
        "plan": plan,
        "centers": centers,
        "row_image": row,
        "sprite": (sprite.width, sprite.height),
        "ink_left": ink_left,
        "ink_top": ink_top,
        "ink_bottom": ink_bottom,
        "sprite_x": sprite_x,
        "new_layer_y": new_layer_y,
        "slot_tops": slot_tops,
        "slot_lefts": slot_lefts,
        "shifts": shifts,
        "shifts_x": shifts_x,
        "row_original_left": [row["x"] for row in rows],
        "cursor_frames": frames,
        "cursor_frame": cursor_frame,
        "cursor_y": cursor_y,
        "band": band,
        "rows": rows,
        "slant": slant,
        "glyph_height": target,
        #: 我们那张贴图自己的斜率（与五行用的是同一个估计量）—— 门禁拿它比"斜度一致"
        "sprite_slant": envelope_slant(_ink_points(row, (0, 0, row.width - 1, row.height - 1))),
        "vanilla_row": vanilla is not None,
        "donor": donor,
        "sheet": sheet_path,
    }
    if sprite_pcx:
        os.makedirs(os.path.dirname(os.path.abspath(sprite_pcx)), exist_ok=True)
        with open(sprite_pcx, "wb") as handle:
            handle.write(encode_pcx(row))
        result["sprite_pcx"] = sprite_pcx
    return result


def write_png(path: str, image: Image, scale: int = 1) -> None:
    """把一张 `Image` 写成 PNG（只为离线核对——不开新依赖，用 zlib 手写最小 PNG）。"""
    import zlib
    width, height = image.width * scale, image.height * scale
    raw = bytearray()
    for y in range(height):
        raw.append(0)  # filter: none
        for x in range(width):
            r, g, b, a = image.pixel(x // scale, y // scale)
            raw += bytes((r, g, b, a))
    def chunk(tag: bytes, payload: bytes) -> bytes:
        return (len(payload).to_bytes(4, "big") + tag + payload
                + zlib.crc32(tag + payload).to_bytes(4, "big"))
    header = bytes((137, 80, 78, 71, 13, 10, 26, 10))
    body = (chunk(b"IHDR", width.to_bytes(4, "big") + height.to_bytes(4, "big")
                  + bytes((8, 6, 0, 0, 0)))
            + chunk(b"IDAT", zlib.compress(bytes(raw), 9)) + chunk(b"IEND", b""))
    with open(path, "wb") as handle:
        handle.write(header + body)


def mockup(result: dict, sheet: Image, rows, frames) -> Image:
    """把"这一列在游戏里长什么样"画出来（离线看效果用，别上真机猜）。

    画的东西：纸（从该语言的图集里取）＋ 五行按**新位置**贴上去 ＋ 我们那一格。
    坐标就是页内坐标（480×270 那一套），颜色/透明度原样搬。
    """
    canvas = Image(sheet.width, 270, bytearray(sheet.width * 270 * 4))
    # 纸：把图集里 y<270 的那一段原样搬过来（引擎就是这么画的：Main 层的 crop = 整张上半）
    for y in range(min(270, sheet.height)):
        for x in range(sheet.width):
            canvas.set_pixel(x, y, sheet.pixel(x, y))
    for index, entry in enumerate(rows):
        frame = frames[entry["layer_id"]]
        cx, cy, w, h = (int(float(frame[k])) for k in ("XCrop", "YCrop", "Width", "Height"))
        left, top = int(round(entry["x"])), int(round(result["plan"][index]["y"]))
        for y in range(h):
            for x in range(w):
                source = sheet.pixel(cx + x, cy + y)
                if source[3] == 0:
                    continue
                target_x, target_y = left + x, top + y
                if 0 <= target_x < canvas.width and 0 <= target_y < canvas.height:
                    canvas.set_pixel(target_x, target_y, source)
    sprite = result["row_image"]
    left, top = int(round(result["sprite_x"])), int(round(result["new_layer_y"]))
    for y in range(sprite.height):
        for x in range(sprite.width):
            source = sprite.pixel(x, y)
            if source[3] == 0:
                continue
            target_x, target_y = left + x, top + y
            if 0 <= target_x < canvas.width and 0 <= target_y < canvas.height:
                canvas.set_pixel(target_x, target_y, source)
    return canvas


def _f(value) -> str:
    """一个 float 常量的写法：保留一位小数（工具自己的输出与生成的头逐字一致，门禁按字节比）。"""
    return f"{value:.1f}F"


def _array(name: str, values, indent: str = "    ") -> list[str]:
    """一个聚合初始化用的 `{...},`（数组名只写成注释 —— 这里不能写 `name = {...}`）。"""
    return [f"{indent}// {name}",
            f"{indent}{{",
            indent + "    " + ", ".join(_f(v) for v in values) + ",",
            indent + "},"]


def emit_layouts(results: list[dict], header_name: str) -> str:
    """把八个语言的**行贴图 + 布局常量**写成运行时头文件（`runtime/source/mod_row_generated.hpp`）。

    为什么编进模块而不是放文件（2026-09-22 用户定案）：要求"这一行不能被关闭、也不要放在
    romfs 的模组目录里" ⇒ 编进 `subsdk9` 最直接：没有可关闭的东西、不碰模组目录、也不依赖
    挂载优先级。运行时本来就有"把内存里的贴图字节变成贴图对象"这条链
    （贴图桥 v2 用过的五参 `ImageManager::LoadImage`），所以只要把字节交进去。

    贴图字节是 **PCX**（四平面 8 位，仓库自带的编码器），因为引擎按**扩展名**挑解码器
    （`strcmp(ext,"png"/"pcx"/"pic")` 三选一 ⇒ 路径必须以 `.pcx` 结尾）。
    """
    lines: list[str] = []
    lines.append("// 由 `tools/gamemenu_mod_row.py` 生成 —— **不要手改**。")
    lines.append("//")
    lines.append("// 重新生成（八个语言一次）：")
    lines.append("//   python3 tools/gamemenu_mod_row.py --dump-root '<游戏 dump>/Program #0/1'")
    lines.append("//       --emit-layouts runtime/source/mod_row_generated.hpp")
    lines.append("//")
    lines.append("// 内容：")
    lines.append("//   * 每个语言一张『模组/MODS』行贴图（PCX 字节 = **游戏自己画的那一行**，1:1 取用、")
    lines.append("//     不缩放不旋转；来源是各语言图集里『第 6 行』那一块，位置从法语 ANM2 的 `Item6` 读出来）；")
    lines.append("//   * 每个语言的布局：五行的位移、我们那一格的贴图落点、六格的光标 y、纸的上下沿。")
    lines.append("//     全部由该语言自己的 `gamemenu.anm2` / `gamemenu.pcx` 量出来（见工具里的规则）。")
    lines.append("//")
    lines.append("// 门禁：`runtime/tests/test_gamemenu_mod_row.py` 会**重新生成一遍并逐字节比对** ⇒")
    lines.append("// 这个文件过期（或有人手改了）门禁就红。")
    lines.append("#pragma once")
    lines.append("")
    lines.append("#include <cstdint>")
    lines.append("")
    lines.append("namespace isaac::runtime {")
    lines.append("")
    lines.append("//: 六格（含我们插进去的那一格）与引擎自己那五行 —— 与 `mod_menu_entry_row.hpp` 的")
    lines.append("//: `kMenuGameEntryCount` / `kMenuGameEngineEntryCount` 必须一致（那里有 static_assert）。")
    lines.append(f"inline constexpr std::uint32_t kModRowSlotCount = {SLOT_COUNT};")
    lines.append(f"inline constexpr std::uint32_t kModRowEngineRowCount = {ENGINE_ROW_COUNT};")
    lines.append("")
    lines.append("//: 一行贴图（PCX 字节 + 尺寸 + 字在贴图内的落点）。")
    lines.append("struct ModRowSprite {")
    lines.append("    const std::uint8_t* pcx;")
    lines.append("    std::uint32_t pcxBytes;")
    lines.append("    std::uint32_t width;")
    lines.append("    std::uint32_t height;")
    lines.append("    float inkLeft;    // 字在贴图内的包围盒（画布是整张图，字只占其中一块）")
    lines.append("    float inkTop;")
    lines.append("    float inkBottom;")
    lines.append("};")
    lines.append("")
    lines.append("//: 一个语言的全套布局。")
    lines.append("struct ModRowLayout {")
    lines.append("    const char* language;            // 游戏的语言码（`Manager::GetLanguageCode`）")
    lines.append("    ModRowSprite sprite;")
    lines.append("    float spriteX;                   // 我们那一格：贴图左上角的页内坐标")
    lines.append("    float spriteY;")
    lines.append("    float rowShiftY[kModRowEngineRowCount];     // 五行相对**原位置**的位移（负 = 上移）")
    lines.append("    float rowShiftX[kModRowEngineRowCount];     // 五行相对**原位置**的横向位移")
    lines.append("                                                //     （= PC 的框 x − 本语言的框 x）")
    lines.append("    float rowOriginalLeft[kModRowEngineRowCount];  // 本语言 ANM2 里各行的框 x")
    lines.append("    float rowOriginalTop[kModRowEngineRowCount];")
    lines.append("    float rowInkTop[kModRowEngineRowCount];     // 字在行贴图内（框内坐标）")
    lines.append("    float rowInkBottom[kModRowEngineRowCount];")
    # ⚠️ 下面这些字段的**声明顺序必须与写入顺序完全一致**（聚合初始化按顺序吃）——
    #    实测踩过一次：声明 slotTop 在前、写入 slotLeft 在前 ⇒ `slotTop` 读到的是横向的值，
    #    真机上就是"六格全挤到左边"；宿主门禁那条横向判据当场报错（3b1）。
    lines.append("    float slotLeft[kModRowSlotCount];           // 六格的横向锚点（= PC 的框 x，横向也照搬）")
    lines.append("    float slotTop[kModRowSlotCount];            // 六格的锚点（引擎行 = 框顶，我们 = 贴图顶）")
    lines.append("    float cursorFrameY[kModRowSlotCount];       // 光标各帧**原生**的 y（该语言自己的帧数 ≤6）")
    lines.append("    std::uint32_t cursorFrame[kModRowSlotCount];// 每一格该用第几帧（原版六行的语言是 0..5；")
    lines.append("                                                // 我们插一行的语言是 0,1,2,3,3,4 —— 我们那一格借")
    lines.append("                                                // 统计数据的帧，第 5、6 格顺延）")
    lines.append("    float cursorY[kModRowSlotCount];            // 六格光标该落的 y（= 光标中心）")
    lines.append("    std::uint32_t vanillaRow;                   // 1 = 这个语言**原版自己就有**这一行")
    lines.append("                                                //     （实测：法语 `Item6`）⇒ 引擎本来就会画它，")
    lines.append("                                                //     运行时照画只是『补一手』（同位置、看不出来）")
    lines.append("    float glyphHeight;                          // 那支笔写出来的字**转正以后**有多高")
    lines.append("                                                //     （退回用字体画时按它算字号；不是包围盒高）")
    lines.append("    float slant;                                // 那支笔有多斜（逐行拟合斜率的中位数，负 = 往右上升）")
    lines.append("    float paperTop;                             // 纸的可用带（量出来的，门禁用它判出界）")
    lines.append("    float paperBottom;")
    lines.append("};")
    lines.append("")
    for result in results:
        rows = result["rows"]
        pcx = encode_pcx(result["row_image"])
        source = ("原版自己那一行（本语言 ANM2 里的 `Item6`）" if result["vanilla_row"]
                  else "本语言图集里的『第 6 行』那一块")
        if result.get("donor"):
            source += f"，本语言那块是空的 ⇒ 借了 {result['donor']} 的"
        lines.append(f"// ── {result['language']}：{source} → {result['sprite'][0]}×{result['sprite'][1]}"
                     f"，落点 ({result['sprite_x']:.1f}, {result['new_layer_y']:.1f}) ──")
        lines.append(f"inline constexpr std::uint8_t kModRowPcx_{result['language']}[] = {{")
        for offset in range(0, len(pcx), 12):
            chunk = ", ".join(f"0x{value:02X}" for value in pcx[offset:offset + 12])
            lines.append(f"    {chunk},")
        lines.append("};")
        lines.append("")
    lines.append("inline constexpr ModRowLayout kModRowLayouts[] = {")
    for result in results:
        language = result["language"]
        frames = list(result["cursor_frames"])
        while len(frames) < SLOT_COUNT:
            frames.append(0.0)
        lines.append("    {")
        lines.append(f'        "{language}",')
        # ⚠️ 这里必须是**贴图（画布）**的尺寸，不是"字"的尺寸：运行时是把这个尺寸当 quad 用、
        # 引擎按整个图像缩放进去 ⇒ 写成字的尺寸就会把 160×48 的画布压扁到字那么大。
        # （2026-09-22 晚踩过：de 那套写成 72×32，字被压扁且位置错。）
        canvas = result["row_image"]
        lines.append(f"        {{kModRowPcx_{language}, sizeof(kModRowPcx_{language}), "
                     f"{canvas.width}, {canvas.height}, "
                     f"{_f(result['ink_left'])}, {_f(result['ink_top'])}, "
                     f"{_f(result['ink_bottom'])}}},")
        lines.append(f"        {_f(result['sprite_x'])}, {_f(result['new_layer_y'])},")
        for name, values in (("rowShiftY", result["shifts"]),
                             ("rowShiftX", result["shifts_x"]),
                             ("rowOriginalLeft", result["row_original_left"]),
                             ("rowOriginalTop", [row["y"] for row in result["rows"]]),
                             ("rowInkTop", [float(row["ink_top"]) for row in result["rows"]]),
                             ("rowInkBottom", [float(row["ink_bottom"]) for row in result["rows"]]),
                             ("slotLeft", result["slot_lefts"]),
                             ("slotTop", result["slot_tops"]),
                             ("cursorFrameY", frames)):
            lines.extend(_array(name, values, indent="        "))
        # ★ 顺序必须与上面 `ModRowLayout` 的声明一致（聚合初始化按顺序吃）
        lines.append("        // cursorFrame")
        lines.append("        {" + ", ".join(str(v) for v in result["cursor_frame"]) + "},")
        lines.extend(_array("cursorY", result["cursor_y"], indent="        "))
        lines.append(f"        {int(result['vanilla_row'])},  // vanillaRow")
        lines.append(f"        {_f(result['glyph_height'])}, {_f(result['slant'])},"
                 f"  // 字高 / 五行那支笔的倾斜（我们那张贴图自己的斜率 "
                 f"{result['sprite_slant']:+.3f}，它是**游戏自己画的、1:1 取用**）")
        lines.append(f"        {_f(result['band'][0])}, {_f(result['band'][1])},")
        lines.append("    },")
    lines.append("};")
    lines.append(f"inline constexpr std::uint32_t kModRowLayoutCount = "
                 f"{len(results)};  // = sizeof(kModRowLayouts)/sizeof(kModRowLayouts[0])")
    lines.append("")
    lines.append("}  // namespace isaac::runtime")
    lines.append("")
    return "\n".join(lines)


def describe(result: dict) -> None:
    source = ("原版自己那一行（本语言 ANM2 里的 `Item6`）" if result["vanilla_row"]
              else "本语言图集里的『第 6 行』那一块")
    if result.get("donor"):
        source += f"（本语言图集里那块是空的，借了 {result['donor']} 的）"
    print(f"[{result['language']}] 那一行来自 {source} → {result['sprite'][0]}×{result['sprite'][1]}"
          f"，贴图斜率 {result['sprite_slant']:+.3f} vs 五行 {result['slant']:+.3f}"
          f"，落点 ({result['sprite_x']:.1f}, {result['new_layer_y']:.1f})")
    print(f"  纸的可用带 {result['band'][0]:g}..{result['band'][1]:g}")
    print('  六格（引擎行 ← 原框顶 + 位移 = 新框顶）：')
    for index, entry in enumerate(result['plan']):
        slot = index if index < MOD_ENTRY_SLOT else index + 1
        print('    格%d %-9s 原 Y=%-7g 位移 %+6.1f → %-7.1f（字 %g..%g，光标 %g）' % (
            slot, entry['name'], result['rows'][index]['y'], result['shifts'][index],
            entry['y'], result['centers'][slot] - (result['rows'][index]['ink_bottom']
                                                   - result['rows'][index]['ink_top']) / 2.0,
            result['centers'][slot] + (result['rows'][index]['ink_bottom']
                                       - result['rows'][index]['ink_top']) / 2.0,
            result['cursor_y'][slot]))
    print('    格%d %-9s 贴图 Y=%-7.1f（字中心 %g，光标 %g）  ← 我们那一行' % (
        MOD_ENTRY_SLOT, 'Mods', result['new_layer_y'],
        result['centers'][MOD_ENTRY_SLOT], result['cursor_y'][MOD_ENTRY_SLOT]))
    if result.get('sprite_pcx'):
        print(f"  行贴图 PCX → {result['sprite_pcx']}")


# ---------------------------------------------------------------------------
# 把 PC 那一层 `Item6` **补回 Switch 的菜单动画**（2026-09-23，用户定案：走原生那一套）
# ---------------------------------------------------------------------------
#
# ## 为什么（这一批的根因）
#
# 那一行跑过一局之后变空白，而引擎自己那五行从不消失。机制：引擎自己的图层用
# `ANM2::LayerState::SetSpriteSheet(SmartPointer<ImageBase>)` 持有**真正的引用计数**
# （`ImageManager::s_image_reference_freed` 就是管理器对"引用被释放"的反应），而我们那份是
# 16 字节裸拷贝（`SmartPointerShim`：不加引用、也不释放）⇒ 管理器一放手，对象就被回收 ——
# 显存缓冲清零、对象内存还看着正常，与现场读数逐条吻合。
#
# ⇒ 只要那一行**不是我们另外持有的一张图**，这一类故障就不可能出现。
#
# ## 做法：把游戏自己删掉的那一层补回去
#
# PC 版**每个语言**的 `gamemenu.anm2` 都有第 13 层 `Item6`（`SpritesheetId=0`，一帧，
# 位置 `(201,139)`、轴心 `(16,16)`、从图集裁 `(195,475)` 的 `80×39`），八个语言的数值**逐字段相同**；
# Switch 版把这层删了，**只有法语那份还留着**（它就是 PC 的原件）—— 也就是说：
# 我们要补的这套数值，游戏自己就在用。
#
# 补完之后，那一行由引擎自己的整页渲染画出来（`Menu_Game::Render` 里只有**一次**
# `ANM2::Render`，所有图层统一画），生命周期与其余五行**完全同源**。
#
# ## 纪律
#
# * **只插两段**：图层定义行 + 它在 `Idle` 动画里的一帧；其余字节一字不改（有门禁逐字节比）；
# * 样式（缩进、属性顺序、` />` 还是 `/>`）**照原版自己那份文件**，不自己编 —— 各语言文件的
#   排版本来就不一样（法语那份是 PC 风格）；
# * 原版已经有这一层（法语）⇒ **一字不改**，并报出这件事；
# * 缺原版、缺 PC 参考、PC 参考里没有那一层 ⇒ 当场报错，绝不猜一个数值继续。

#: 补回去的那一层（PC 原版的名字与编号）。
RESTORED_LAYER_NAME = "Item6"
RESTORED_LAYER_ID = 12
RESTORED_LAYER_SPRITESHEET_ID = "0"
#: 原版自己就有这一层的语言（Switch 的法语资源是 PC 原件，没被删过）⇒ 不需要我们补。
LANGUAGES_WITH_RESTORED_LAYER = ("fr",)
#: 补这一层时用哪个"行图层"当排版模板（它的样式与属性顺序就是我们要的）。
RESTORED_LAYER_TEMPLATE_LAYER_ID = 5
#: 补这一层时用哪一条动画当模板（同样只为拿样式）。
RESTORED_LAYER_TEMPLATE_ANIMATION_ID = 5


@dataclass(frozen=True)
class RestoredLayer:
    """补完之后的整份文件文本，以及"到底插了什么"的逐字留证。"""

    text: str                      # 补完之后的整份文件
    inserted: tuple[str, ...]      # 插进去的原文（去掉它们应当逐字节还原成原版）
    frame: dict                    # 插进去那一帧的属性（值来自 PC 参考）
    already_present: bool          # 原版本来就有这一层（法语）⇒ 一字未改


def language_directory(language: str) -> str:
    """语言码 → 游戏 romfs 里那个语言资源目录名（英文是裸 `resources`）。

    与 `tools/emit_mod_row_art.py` 的同名函数必须一致（有门禁比对两处）。
    """
    return LANGUAGE_ROOTS[language].split("/", 1)[1]


def switch_menu_anm2_path(dump_root: str, language: str) -> Path:
    """Switch 版该语言的菜单动画（**引擎实际读的那一份**）。

    落点由 `rp_patch/kage_mount_points.dat` 的八个挂载根逐个核过：每个语言根都登记了
    `gfx\\ui\\main menu\\gamemenu.anm2`，物理文件在 `rp_patch/<语言根>/` 下
    （英文的语言根是裸 `resources`）。所以补这一层就是**覆盖这一个文件**。
    """
    return Path(dump_root) / LANGUAGE_ROOTS[language] / GAMEMENU_ANM2


def pc_menu_anm2_path(language: str, pc_root: str | None = None) -> Path:
    """PC 版同语言的菜单动画（**数值真值源**）。"""
    return Path(pc_root or PC_LANGUAGE_ROOT) / language / GAMEMENU_ANM2


#: 找 dump 用的通配（**不要写死完整目录名**）。
#:
#: 2026-09-23 实测：本机那份 dump 的目录名在 Docker Desktop（VirtioFS）里**用字面量打不开**
#: （`ls "The Binding of Isaac_ Afterbirth+ …[UPD]/Program #0/1"` 报 no such file），
#: 而**按 readdir 列出来再拼**（glob）却完全正常。构建跑在 Docker 里 ⇒ 一律走通配发现，
#: 不要写死那个带空格/方括号/`#` 的目录名。
DUMP_DIRECTORY_GLOB = "The Binding of Isaac*UPD]"
#: dump 根的相对尾段（`Program #0/1` 之下才是 `rp_patch/`、`resources/`）。
DUMP_SUBDIRECTORY = os.path.join("Program #0", "1")


def discover_dump_root(repo_root: str | None = None) -> str | None:
    """按通配找游戏 dump 根；找不到返回 None（**不猜**）。"""
    import glob
    pattern = os.path.join(repo_root or REPO_ROOT, DUMP_DIRECTORY_GLOB)
    for candidate in sorted(glob.glob(pattern)):
        root = os.path.join(candidate, DUMP_SUBDIRECTORY)
        if os.path.isdir(root):
            return root
    return None


def _tag_attributes(tag: str) -> dict:
    return dict(re.findall(r'(\w+)="([^"]*)"', tag))


def _layer_tags(xml: str) -> list:
    return re.findall(r"<Layer\b[^>]*>", xml)


def _rewrite_attributes(tag: str, values: dict, *, what: str) -> str:
    """把标签里的若干属性**只改值**（样式/顺序/空白全照原样）。

    键集必须完全一致：模板少一个键或多一个键都当场报错 —— 少一个说明我们对这份文件的形状
    理解错了，多一个说明新值里有模板不认识的东西；两种情况都该停下来，而不是硬写进去。
    """
    present = set(_tag_attributes(tag))
    if present != set(values):
        raise ArtError(f"{what} 的属性集对不上：模板 {sorted(present)}，"
                       f"新值 {sorted(values)}")
    for key, value in values.items():
        tag = re.sub(rf'{key}="[^"]*"', f'{key}="{value}"', tag, count=1)
    return tag


def _layer_animation_block(xml: str, layer_id: int, *, what: str) -> str:
    """取某条 `LayerAnimation` 的**原文**（含首尾标签，不含缩进之外的空白改动）。"""
    match = re.search(r'([ \t]*)<LayerAnimation\b[^>]*LayerId="%d"[^>]*>.*?</LayerAnimation>'
                      % layer_id, xml, re.S)
    if match is None:
        raise ArtError(f"{what}：没有 LayerId={layer_id} 的 LayerAnimation")
    return match.group(0)


def restore_mods_row_layer(vanilla_text: str, pc_text: str, *,
                           language: str) -> RestoredLayer:
    """把 PC 的 `Item6` 层补进 Switch 那份菜单动画；除这两段外逐字节不变。"""
    # 0) 原版已经有这一层（法语）⇒ 一字不改。也不去"顺手统一"它的数值：
    #    那是游戏自己写的，改它等于替游戏改行为，而且没有任何理由。
    existing = [tag for tag in _layer_tags(vanilla_text)
                if _tag_attributes(tag).get("Name") == RESTORED_LAYER_NAME]
    if existing:
        if len(existing) != 1:
            raise ArtError(f"{language}：原版里有 {len(existing)} 个 {RESTORED_LAYER_NAME}")
        attributes = _tag_attributes(existing[0])
        if (attributes.get("Id") != str(RESTORED_LAYER_ID)
                or attributes.get("SpritesheetId") != RESTORED_LAYER_SPRITESHEET_ID):
            raise ArtError(f"{language}：原版那一层是 Id={attributes.get('Id')} "
                           f"SpritesheetId={attributes.get('SpritesheetId')}，与预期不符")
        block = _layer_animation_block(vanilla_text, RESTORED_LAYER_ID, what=language)
        frame = re.search(r"<Frame\b[^>]*>", block)
        return RestoredLayer(vanilla_text, (), _tag_attributes(frame.group(0)) if frame else {},
                             True)

    # 1) 数值真值源：PC 版同语言文件里那一层、那一帧。
    pc_layers = [tag for tag in _layer_tags(pc_text)
                 if _tag_attributes(tag).get("Name") == RESTORED_LAYER_NAME]
    if len(pc_layers) != 1:
        raise ArtError(f"{language}：PC 参考里 {RESTORED_LAYER_NAME} 有 {len(pc_layers)} 个"
                       f"（要恰好一个）")
    pc_attributes = _tag_attributes(pc_layers[0])
    if (pc_attributes.get("Id") != str(RESTORED_LAYER_ID)
            or pc_attributes.get("SpritesheetId") != RESTORED_LAYER_SPRITESHEET_ID):
        raise ArtError(f"{language}：PC 那一层是 Id={pc_attributes.get('Id')} "
                       f"SpritesheetId={pc_attributes.get('SpritesheetId')}，与预期不符")
    pc_block = _layer_animation_block(pc_text, RESTORED_LAYER_ID, what=f"{language} 的 PC 参考")
    pc_frames = re.findall(r"<Frame\b[^>]*>", pc_block)
    if len(pc_frames) != 1:
        raise ArtError(f"{language}：PC 那一层有 {len(pc_frames)} 帧（要恰好一帧）")
    pc_frame = _tag_attributes(pc_frames[0])

    # 2) 样式模板：原版自己的一个行图层 + 它那条动画（缩进/属性顺序/自闭合写法全照它）。
    templates = [tag for tag in _layer_tags(vanilla_text)
                 if _tag_attributes(tag).get("Id") == str(RESTORED_LAYER_TEMPLATE_LAYER_ID)]
    if len(templates) != 1:
        raise ArtError(f"{language}：原版里 Id={RESTORED_LAYER_TEMPLATE_LAYER_ID} 的图层"
                       f"有 {len(templates)} 个（样式模板要唯一）")
    template_block = _layer_animation_block(vanilla_text, RESTORED_LAYER_TEMPLATE_ANIMATION_ID,
                                           what=f"{language} 的样式模板")
    template_frames = re.findall(r"<Frame\b[^>]*>", template_block)
    if len(template_frames) != 1:
        raise ArtError(f"{language}：样式模板那条动画有 {len(template_frames)} 帧（要恰好一帧）")

    # 3) 重写：图层定义只改三个属性值；动画段只改 LayerId 与那一帧的属性值。
    new_layer_tag = _rewrite_attributes(
        templates[0],
        {"Id": str(RESTORED_LAYER_ID), "Name": RESTORED_LAYER_NAME,
         "SpritesheetId": RESTORED_LAYER_SPRITESHEET_ID},
        what=f"{language} 的图层定义")
    new_block = template_block
    opening = re.search(r"<LayerAnimation\b[^>]*>", new_block)
    if opening is None:
        raise ArtError(f"{language}：样式模板里没有 LayerAnimation 开标签")
    template_opening = _tag_attributes(opening.group(0))
    pc_opening = _tag_attributes(re.search(r"<LayerAnimation\b[^>]*>", pc_block).group(0))
    for key, value in pc_opening.items():
        if key != "LayerId" and template_opening.get(key) != value:
            raise ArtError(f"{language}：动画段的 {key} 模板是 {template_opening.get(key)}、"
                           f"PC 是 {value}（样式与真值不一致，停下来问清楚）")
    # 只改开标签里的 LayerId（其余属性照模板，样式不动）。
    new_opening = _rewrite_attributes(opening.group(0),
                                      {**template_opening, "LayerId": str(RESTORED_LAYER_ID)},
                                      what=f"{language} 的动画段开标签")
    new_block = new_block[:opening.start()] + new_opening + new_block[opening.end():]
    # 只改那一帧的属性值（属性集必须与 PC 参考完全一致）。
    frame = re.search(r"<Frame\b[^>]*>", new_block)
    if frame is None:
        raise ArtError(f"{language}：样式模板里没有 Frame")
    new_block = (new_block[:frame.start()]
                 + _rewrite_attributes(frame.group(0), pc_frame, what=f"{language} 的那一帧")
                 + new_block[frame.end():])

    # 4) 插入：图层行插在最后一个图层之后；动画段插在 `</LayerAnimations>` 之前。
    layer_lines = list(re.finditer(r"[ \t]*<Layer\b[^>]*>[ \t]*\n", vanilla_text))
    if not layer_lines:
        raise ArtError(f"{language}：原版里找不到图层行")
    indent = re.match(r"[ \t]*", layer_lines[-1].group(0)).group(0)
    inserted_layer = f"{indent}{new_layer_tag}\n"
    text = vanilla_text[:layer_lines[-1].end()] + inserted_layer + vanilla_text[
        layer_lines[-1].end():]

    closing = list(re.finditer(r"[ \t]*</LayerAnimations>[ \t]*\n", text))
    if len(closing) != 1:
        raise ArtError(f"{language}：`</LayerAnimations>` 出现 {len(closing)} 次（要恰好一次）")
    inserted_block = f"{new_block}\n"
    text = text[:closing[0].start()] + inserted_block + text[closing[0].start():]

    # 5) 自检：去掉插入的两段必须逐字节还原（门禁也会独立再验一次）。
    check = text
    for block in (inserted_layer, inserted_block):
        if check.count(block) != 1:
            raise ArtError(f"{language}：插入段在结果里不是唯一出现")
        check = check.replace(block, "", 1)
    if check != vanilla_text:
        raise ArtError(f"{language}：补完之后去掉插入段 ≠ 原版（说明还动了别的字节）")
    return RestoredLayer(text, (inserted_layer, inserted_block), pc_frame, False)


def build_patched_gamemenu(dump_root: str, language: str,
                           pc_root: str | None = None) -> RestoredLayer:
    """读真实文件（Switch 原版 + PC 参考）算出补完的那一份。"""
    vanilla_path = switch_menu_anm2_path(dump_root, language)
    if not vanilla_path.is_file():
        raise ArtError(f"{language}：找不到 Switch 原版菜单动画 {vanilla_path}")
    pc_path = pc_menu_anm2_path(language, pc_root)
    if not pc_path.is_file():
        raise ArtError(f"{language}：找不到 PC 参考 {pc_path}（取法见 docs/PC-主菜单参考资源.md）")
    return restore_mods_row_layer(vanilla_path.read_text(encoding="utf-8"),
                                  pc_path.read_text(encoding="utf-8"), language=language)


def emit_menu_anm2(directory: str, dump_root: str, languages=None,
                   pc_root: str | None = None) -> list:
    """把补完的菜单动画落到 `directory` 下（`directory` = 部署包里的 `rp_patch/`）。

    只给"原版没有这一层"的语言落文件（法语原版就有 ⇒ 落一份多余的文件等于无谓地覆盖游戏资源）。
    """
    written = []
    for language in sorted(languages or LANGUAGE_ROOTS):
        restored = build_patched_gamemenu(dump_root, language, pc_root)
        if restored.already_present:
            continue
        target = Path(directory) / language_directory(language) / GAMEMENU_ANM2
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "w", encoding="utf-8", newline="") as handle:
            handle.write(restored.text)
        written.append(target)
    return written


def main() -> int:
    parser = argparse.ArgumentParser(
        description="生成『模组』那一行的手绘贴图与布局（运行时头文件 / 备用美术 / 菜单动画补层）")
    parser.add_argument("--dump-root", required=True, help="游戏 dump 根（其下有 rp_patch/、resources/）")
    parser.add_argument("--language", choices=sorted(LANGUAGE_ROOTS),
                        help="只生成一个语言（不给 --emit-layouts 时必填）")
    parser.add_argument("--output", help="备用美术的输出根（一般是 <模组目录>/resources；不给就不生成）")
    parser.add_argument("--sprite-pcx", help="把那一行的贴图单独存成 PCX（离线核对/别的用途）")
    parser.add_argument("--preview", action="store_true", help="打印新行贴图的字符画（离线核对用）")
    parser.add_argument("--mockup", help="把『这一列在游戏里长什么样』画成 PNG（离线核对用）")
    parser.add_argument("--pc-root", default=PC_LANGUAGE_ROOT,
                        help="PC 版每语言主菜单参考的根（其下 <语言>/gfx/ui/main menu/…）；"
                             f"默认 {PC_LANGUAGE_ROOT}")
    parser.add_argument("--emit-layouts", help="生成运行时头文件（八个语言一次；= 提交进仓库的那份）")
    parser.add_argument("--emit-menu-anm2",
                        help="把 PC 那一层 `Item6` 补回菜单动画，落到这个目录下"
                             "（= 部署包里的 rp_patch/；只落「原版没有这一层」的语言）")
    args = parser.parse_args()

    if args.emit_menu_anm2:
        try:
            written = emit_menu_anm2(args.emit_menu_anm2, args.dump_root, pc_root=args.pc_root)
        except ArtError as error:
            print(f"生成失败：{error}")
            return 1
        for path in written:
            print(f"菜单动画（补回 Item6 层）→ {path}"
                  f"（{path.stat().st_size} 字节）")
        print(f"共 {len(written)} 个语言；"
              f"{'、'.join(LANGUAGES_WITH_RESTORED_LAYER)} 原版自带这一层 ⇒ 未改动")
        return 0

    if args.emit_layouts:
        results = []
        try:
            bands = measure_paper_bands(args.dump_root)
            region = sixth_row_region(args.dump_root)
            # ★ 排版真值源：PC 版**同一语言**的 ANM2（八份各读一次，不做任何推导）
            layouts = pc_language_layouts(args.pc_root)
            for language in sorted(LANGUAGE_ROOTS):
                results.append(build_language(args.dump_root, language, None,
                                              band=bands[language], region=region,
                                              pc=layouts[language]))
        except ArtError as error:
            print(f"生成失败：{error}")
            return 1
        header = emit_layouts(results, os.path.basename(args.emit_layouts))
        os.makedirs(os.path.dirname(os.path.abspath(args.emit_layouts)), exist_ok=True)
        with open(args.emit_layouts, "w", encoding="utf-8", newline="") as handle:
            handle.write(header)
        print(f"运行时头文件 → {args.emit_layouts}"
              f"（{len(results)} 个语言，{len(header)} 字节，"
              f"贴图合计 {sum(len(encode_pcx(r['row_image'])) for r in results)} 字节）")
        for result in results:
            print(f"  {result['language']}: 贴图 {result['sprite'][0]}×{result['sprite'][1]}，"
                  f"落点 ({result['sprite_x']:.1f}, {result['new_layer_y']:.1f})，"
                  f"纸 {result['band'][0]:g}..{result['band'][1]:g}，"
                  f"位移 {[round(v, 1) for v in result['shifts']]}")
        return 0

    if not args.language:
        print("生成失败：要么给 --emit-layouts，要么给 --language")
        return 1
    try:
        layout = pc_language_layout(args.language, args.pc_root)
        result = build_language(args.dump_root, args.language, args.output, args.preview,
                               args.sprite_pcx, pc=layout)
    except ArtError as error:
        print(f"生成失败：{error}")
        return 1
    describe(result)
    if args.mockup:
        sheet = decode_pcx(resolve_content_file(args.dump_root, args.language, GAMEMENU_PCX))
        xml = open(resolve_content_file(args.dump_root, args.language, GAMEMENU_ANM2),
                   "rb").read().decode("utf-8")
        rows = row_geometry(xml, sheet)
        _, frames = read_layers(xml)
        write_png(args.mockup, mockup(result, sheet, rows, frames), scale=2)
        print(f"  效果图 → {args.mockup}（页内坐标 480×270，放大 2 倍）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
