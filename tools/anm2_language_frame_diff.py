#!/usr/bin/env python3
"""模组页那行提示的**排版**是从哪来的 —— 逐帧对比各语言的 `modsmenu.anm2`，并把"文字图 + 按键图标"
按指定坐标合成出来看（2026-09-23 批次 078 的现场取证工具）。

## 为什么需要它（2026-09-23 真机现象）

用户报："中文的 TAP 位置偏了、和「键」字重合，英文正常"。查下来那一行**不是运行时画的字**：

* 文字「按 键」/「启用模组」（英文 `PRESS … TO ENABLE MODS`）是**烤在贴图里**的
  （`<语言>/gfx/ui/main menu/seedwidget.pcx`，4 平面 8bpp PCX，PIL 打不开 ⇒ 本工具自带解码器）；
* 中间那个按键图标（贴图里画的 **TAB**）也在这张图上，但**放在哪儿**由页面动画
  `modsmenu.anm2` 里 `Main` 动画的 **layer 13（`WidgetTab`）那一帧**决定；
* 而中英两份 `modsmenu.anm2` **只差这一帧**：中文 `XPosition=125, YPosition=-46`（正好落在
  「按」和「键」中间的缺口里）、英文 `XPosition=148, YPosition=-41`（往右 23 格 ⇒ 压在「键」上）。

⇒ 真机上看到"重合"就等价于："**页面现在用的排版是英文那份，而贴图是中文那份**"。
这个工具的 `--diff` 用来回答"两份动画差在哪一帧"，`--compose` 用来把两种排版各合成一张图
（能一眼看出哪种是对的）。

## 用法

    # 1) 各语言 modsmenu.anm2 与基准（resources/）逐帧比：只列不同的帧
    python3 tools/anm2_language_frame_diff.py --diff

    # 2) 把某个语言的「文字图 + 按键图标」按"用哪套坐标"合成出来（存 PNG）
    python3 tools/anm2_language_frame_diff.py --compose --language zh --layout zh
    python3 tools/anm2_language_frame_diff.py --compose --language zh --layout base

★ 游戏素材路径默认取本仓库里那份拆包目录，`--game-root` 可换。
"""

from __future__ import annotations

import argparse
import os
import re
import struct
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DEFAULT_GAME_ROOT = os.path.join(
    REPO_ROOT,
    "The Binding of Isaac_ Afterbirth+ 1.7.9b [010021C000B6A800][v524288][UPD]",
)
#: `rp_patch/` 下每个语言一层（`resources` = 基准层，其余是语言覆盖层）。
RP_PATCH_RELATIVE = os.path.join("Program #0", "1", "rp_patch")
#: 需要比的层。顺序即输出顺序：第一项当基准。
LAYERS = ("resources", "resources.zh", "resources.de", "resources.es",
          "resources.fr", "resources.jp", "resources.kr", "resources.ru")
#: 页面动画（相对语言根）。
MODSMENU_RELATIVE = os.path.join("gfx", "ui", "main menu", "modsmenu.anm2")
#: 那张贴图（相对语言根）。注意动画里写的是 `SeedWidget.png`，磁盘上是小写 `.pcx`。
SEEDWIDGET_RELATIVE = os.path.join("gfx", "ui", "main menu", "seedwidget.pcx")


# ── PCX（4 平面 × 8bpp，RLE）─────────────────────────────────────────────────
#
# 这份 PCX 是 32 位（四平面各 8 位 = R/G/B/A），PIL 的 PCX 插件不认这种组合
# （`OSError: unknown PCX mode`）⇒ 自己解。格式：128 字节头 + 每扫描线按平面顺序 RLE。
def decode_pcx_32bit(path: str) -> tuple[int, int, bytes]:
    data = open(path, "rb").read()
    if data[0] != 0x0A:
        raise ValueError(f"{path}: 不是 PCX（制造商字节 0x{data[0]:02X}）")
    if data[2] != 1 or data[3] != 8:
        raise ValueError(f"{path}: 只支持 8bpp + RLE（enc={data[2]} bpp={data[3]}）")
    x_min, y_min, x_max, y_max = struct.unpack_from("<4H", data, 4)
    width, height = x_max - x_min + 1, y_max - y_min + 1
    planes = data[65]
    bytes_per_line = struct.unpack_from("<H", data, 66)[0]
    position = 128
    raw = bytearray(width * height * 4)
    for y in range(height):
        rows = []
        for _ in range(planes):
            row = bytearray(bytes_per_line)
            index = 0
            while index < bytes_per_line:
                byte = data[position]
                position += 1
                if byte >= 0xC0:                     # RLE：高两位 11 ⇒ 重复计数
                    count = byte & 0x3F
                    value = data[position]
                    position += 1
                    for _ in range(count):
                        if index < bytes_per_line:
                            row[index] = value
                        index += 1
                else:
                    row[index] = byte
                    index += 1
            rows.append(row)
        for plane, row in enumerate(rows):
            for x in range(width):
                raw[((y * width) + x) * 4 + plane] = row[x]
    return width, height, bytes(raw)


# ── ANM2（Isaac 的动画 XML）─────────────────────────────────────────────────
def read_animation_frames(path: str) -> dict[tuple[str, str, int], dict[str, str]]:
    """把 `<动画名, 图层号, 第几帧> -> 那一帧的属性字典` 摊平，便于逐帧比对/取坐标。

    ★ 比的是**属性值**而不是原始文本：语言层之间会有纯排版的差别（换行、属性顺序、
    末尾斜杠），照原始串比会报出一堆假"不同"（2026-09-23 实测：韩文层 20 帧全被误报）。
    """
    text = open(path, encoding="utf-8", errors="replace").read()
    frames: dict[tuple[str, str, int], dict[str, str]] = {}
    for animation in re.finditer(r"<Animation\b([^>]*)>(.*?)</Animation>", text, re.S):
        name = re.search(r'Name="([^"]*)"', animation.group(1)).group(1)
        for layer in re.finditer(r"<LayerAnimation\b([^>]*)>(.*?)</LayerAnimation>",
                                 animation.group(2), re.S):
            layer_id = re.search(r'LayerId="(\d+)"', layer.group(1))
            if layer_id is None:
                continue
            for index, frame in enumerate(re.findall(r"<Frame\b[^>]*/>", layer.group(2))):
                attributes = dict(re.findall(r'(\w+)="([^"]*)"', frame))
                frames[(name, layer_id.group(1), index)] = attributes
    return frames


def frame_number(frame: dict[str, str] | None, key: str) -> int | None:
    if not frame or key not in frame:
        return None
    return int(frame[key])


def frame_summary(frame: dict[str, str] | None) -> str:
    if frame is None:
        return "（这一层/这一帧在对方那里不存在）"
    x, y = frame_number(frame, "XPosition"), frame_number(frame, "YPosition")
    cx, cy = frame_number(frame, "XCrop"), frame_number(frame, "YCrop")
    w, h = frame_number(frame, "Width"), frame_number(frame, "Height")
    return f"(X,Y)=({x},{y})　裁切区=({cx},{cy},{w},{h})"


def language_root(game_root: str, language: str) -> str:
    return os.path.join(game_root, RP_PATCH_RELATIVE, language)


def cmd_diff(game_root: str, base_language: str) -> int:
    base_path = os.path.join(language_root(game_root, base_language), MODSMENU_RELATIVE)
    if not os.path.isfile(base_path):
        print(f"找不到基准动画 {base_path}")
        return 2
    base = read_animation_frames(base_path)
    print(f"基准 = {base_language}（{len(base)} 帧）")
    for language in LAYERS:
        if language == base_language:
            continue
        path = os.path.join(language_root(game_root, language), MODSMENU_RELATIVE)
        if not os.path.isfile(path):
            print(f"\n== {language}：这一层没有 modsmenu.anm2（引擎会**沿用基准层那份排版**，"
                  f"只换它自己的贴图）")
            continue
        frames = read_animation_frames(path)
        keys = sorted(set(base) | set(frames))
        different = [k for k in keys if base.get(k) != frames.get(k)]
        print(f"\n== {language}：{len(frames)} 帧，与基准不同 {len(different)} 帧")
        for key in different:
            print(f"   anim={key[0]} layer={key[1]} 第{key[2]}帧")
            print(f"      基准：{frame_summary(base.get(key))}")
            print(f"      本语言：{frame_summary(frames.get(key))}")
    return 0


def write_png(path: str, width: int, height: int, rgba: bytes) -> None:
    """把 RGBA 字节写成 PNG。**自己写**（zlib 是标准库）—— 免掉 Pillow 依赖，
    这样任何一台机器上的 `python3` 都能跑（PIL 的 PCX 插件本来也解不了这种 PCX）。"""
    import zlib  # noqa: PLC0415

    def chunk(tag: bytes, payload: bytes) -> bytes:
        return (struct.pack(">I", len(payload)) + tag + payload
                + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF))

    raw = bytearray()
    for y in range(height):
        raw.append(0)  # 每行的滤波器 = 0（不过滤）
        raw += rgba[y * width * 4:(y + 1) * width * 4]
    body = (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
            + chunk(b"IEND", b""))
    open(path, "wb").write(body)


def blend_onto(canvas: bytearray, canvas_width: int, canvas_height: int,
               sprite: bytes, sprite_width: int, sprite_height: int,
               at_x: int, at_y: int) -> None:
    """把一张 RGBA 精灵**按 alpha 混**到画布上（越界部分丢掉）。"""
    for y in range(sprite_height):
        target_y = at_y + y
        if target_y < 0 or target_y >= canvas_height:
            continue
        for x in range(sprite_width):
            target_x = at_x + x
            if target_x < 0 or target_x >= canvas_width:
                continue
            source = (y * sprite_width + x) * 4
            alpha = sprite[source + 3]
            if alpha == 0:
                continue
            target = (target_y * canvas_width + target_x) * 4
            if alpha == 255:
                canvas[target:target + 4] = sprite[source:source + 4]
                continue
            for channel in range(3):
                canvas[target + channel] = (
                    (sprite[source + channel] * alpha
                     + canvas[target + channel] * (255 - alpha)) // 255)
            canvas[target + 3] = 255


def crop_rgba(rgba: bytes, width: int, x: int, y: int, w: int, h: int) -> bytes:
    out = bytearray(w * h * 4)
    for row in range(h):
        source = ((y + row) * width + x) * 4
        out[row * w * 4:(row + 1) * w * 4] = rgba[source:source + w * 4]
    return bytes(out)


def cmd_compose(game_root: str, language: str, layout: str, text_animation: str,
                text_layer: str, text_frame: int, glyph_layer: str, glyph_frame: int,
                out_dir: str) -> int:
    """把「文字图（整块裁下来）」与「按键图标」按某个排版帧的坐标贴到一起 —— 一眼看出对不对。"""
    language_path = os.path.join(language_root(game_root, language), MODSMENU_RELATIVE)
    layout_path = os.path.join(language_root(game_root, layout), MODSMENU_RELATIVE)
    for path in (language_path, layout_path):
        if not os.path.isfile(path):
            print(f"找不到动画 {path}")
            return 2

    spritesheet = os.path.join(language_root(game_root, language), SEEDWIDGET_RELATIVE)
    sheet_width, sheet_height, sheet = decode_pcx_32bit(spritesheet)

    text_frames = read_animation_frames(language_path)
    layout_frames = read_animation_frames(layout_path)
    text_key = (text_animation, text_layer, text_frame)
    glyph_key = (text_animation, glyph_layer, glyph_frame)
    text_spec = text_frames.get(text_key)
    glyph_spec = layout_frames.get(glyph_key)
    if text_spec is None or glyph_spec is None:
        print(f"取不到帧：{text_key} / {glyph_key}")
        return 2

    text_crop = (frame_number(text_spec, "XCrop"), frame_number(text_spec, "YCrop"),
                 frame_number(text_spec, "Width"), frame_number(text_spec, "Height"))
    glyph_crop = (frame_number(glyph_spec, "XCrop"), frame_number(glyph_spec, "YCrop"),
                  frame_number(glyph_spec, "Width"), frame_number(glyph_spec, "Height"))
    text_image = crop_rgba(sheet, sheet_width, *text_crop)
    glyph_image = crop_rgba(sheet, sheet_width, *glyph_crop)

    # ANM2 的约定：帧的 XPivot/YPivot 是"贴到哪一个像素上"的锚点 —— 把裁切块按
    # (位置 − 该图自己的 pivot) 贴出去（缩放 100 = 1.0）。缩放不是 100 的情况这里不处理
    # （本页这两层都是 100）。
    offset_x, offset_y = 20, 80  # 画布偏移：把负坐标挪进可视区
    canvas_width, canvas_height = 320, 160
    canvas = bytearray(bytes((255, 255, 255, 255)) * (canvas_width * canvas_height))

    def place(spec: dict[str, str], image: bytes, crop: tuple[int, int, int, int],
              position: tuple[int, int]) -> None:
        pivot_x, pivot_y = frame_number(spec, "XPivot"), frame_number(spec, "YPivot")
        blend_onto(canvas, canvas_width, canvas_height, image, crop[2], crop[3],
                   position[0] - pivot_x + offset_x, position[1] - pivot_y + offset_y)

    text_position = (frame_number(text_spec, "XPosition"), frame_number(text_spec, "YPosition"))
    place(text_spec, text_image, text_crop, text_position)
    # 图标位置用的是 `layout` 那一层的坐标 —— 这正是要看的那件事。
    glyph_position = (frame_number(glyph_spec, "XPosition"), frame_number(glyph_spec, "YPosition"))
    place(glyph_spec, glyph_image, glyph_crop, glyph_position)

    os.makedirs(out_dir, exist_ok=True)
    name = f"compose-{language.replace('.', '-')}-art-with-{layout.replace('.', '-')}-layout.png"
    target = os.path.join(out_dir, name)
    write_png(target, canvas_width, canvas_height, bytes(canvas))
    print(f"贴图 = {language}　排版 = {layout}")
    print(f"  文字块位置 = {text_position}　图标位置 = {glyph_position}")
    print(f"  -> {target}")
    # 原尺寸只有 320×160、字很小，另存一张放大 4 倍的（最近邻，不模糊）方便肉眼看
    scale = 4
    big = bytearray()
    for y in range(canvas_height):
        row = bytearray()
        for x in range(canvas_width):
            row += canvas[(y * canvas_width + x) * 4:(y * canvas_width + x + 1) * 4] * scale
        big += row * scale
    zoom = target.replace(".png", "-x4.png")
    write_png(zoom, canvas_width * scale, canvas_height * scale, bytes(big))
    print(f"  -> {zoom}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--game-root", default=DEFAULT_GAME_ROOT, help="拆包目录")
    parser.add_argument("--diff", action="store_true", help="逐帧比各语言与基准的 modsmenu.anm2")
    parser.add_argument("--base-language", default="resources", help="基准语言层（默认 resources）")
    parser.add_argument("--compose", action="store_true", help="把文字图与按键图标合成出来看")
    parser.add_argument("--language", default="resources.zh", help="合成时用哪一层的**贴图**")
    parser.add_argument("--layout", default="resources.zh",
                        help="合成时用哪一层的**排版坐标**")
    parser.add_argument("--animation", default="Main")
    parser.add_argument("--text-layer", default="12", help="文字图那一层（modsmenu 里是 12）")
    parser.add_argument("--text-frame", type=int, default=0)
    parser.add_argument("--glyph-layer", default="13", help="按键图标那一层（modsmenu 里是 13）")
    parser.add_argument("--glyph-frame", type=int, default=0)
    parser.add_argument("--out-dir", default=os.path.join(REPO_ROOT, "dist", "modpage-hint-art"))
    args = parser.parse_args()

    if args.diff:
        return cmd_diff(args.game_root, args.base_language)
    if args.compose:
        return cmd_compose(args.game_root, args.language, args.layout, args.animation,
                           args.text_layer, args.text_frame, args.glyph_layer,
                           args.glyph_frame, args.out_dir)
    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
