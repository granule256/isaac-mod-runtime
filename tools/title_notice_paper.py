"""Original game paper art, resized only in its blank middle at build time."""
from dataclasses import dataclass
from pathlib import Path

from tools.gamemenu_mod_row import Image, decode_pcx


def _visible(source: Image) -> Image:
    points = [(i % source.width, i // source.width)
              for i in range(source.width * source.height) if source.rgba[i * 4 + 3]]
    if not points:
        raise ValueError("original notice paper is completely transparent")
    left = min(x for x, _ in points)
    top = min(y for _, y in points)
    right = max(x for x, _ in points) + 1
    bottom = max(y for _, y in points) + 1
    result = Image(right - left, bottom - top, bytearray((right - left) * (bottom - top) * 4))
    for y in range(result.height):
        start = ((top + y) * source.width + left) * 4
        result.rgba[y * result.width * 4:(y + 1) * result.width * 4] = source.rgba[start:start + result.width * 4]
    return result


def _stretch(source: Image, width: int, height: int, borders: tuple) -> Image:
    left, top, right, bottom = borders
    if min(width - left - right, height - top - bottom,
           source.width - left - right, source.height - top - bottom) <= 0:
        raise ValueError("original paper borders leave no stretchable middle")

    def axis(value, target, original, before, after):
        if value < before:
            return value
        if value >= target - after:
            return original - (target - value)
        return before + (value - before) * (original - before - after) // (target - before - after)

    xs = [axis(x, width, source.width, left, right) for x in range(width)]
    ys = [axis(y, height, source.height, top, bottom) for y in range(height)]
    result = Image(width, height, bytearray(width * height * 4))
    for y, sy in enumerate(ys):
        for x, sx in enumerate(xs):
            a = (sy * source.width + sx) * 4
            b = (y * width + x) * 4
            result.rgba[b:b + 4] = source.rgba[a:a + 4]
    return result


@dataclass
class PaperArt:
    sheet: Image
    entry: Image

    def paint(self, target: Image, x: int, y: int, width: int, height: int) -> None:
        tile = self.sheet if (width, height) == (336, 216) else self.entry
        if (tile.width, tile.height) != (width, height):
            raise ValueError("notice paper dimensions do not match the layout")
        for row in range(height):
            start = ((y + row) * target.width + x) * 4
            target.rgba[start:start + width * 4] = tile.rgba[row * width * 4:(row + 1) * width * 4]


def load_paper_art(dump: Path) -> PaperArt:
    def read(relative):
        for root in (dump / "rp_patch/resources", dump / "resources"):
            path = root / relative
            if path.is_file():
                return _visible(decode_pcx(str(path)))
        raise ValueError(f"original game paper missing: {relative}")

    sheet = read("gfx/ui/main menu/seedunlockpaper.pcx")
    entry = read("gfx/ui/seed paper.pcx")
    # Preserve the complete circle doodle and folded corners without stretching
    # them into ovals. Only the unmarked interior grows to the booklet's size.
    return PaperArt(_stretch(sheet, 336, 216, (24, 18, 56, 80)),
                    _stretch(entry, 120, 26, (10, 5, 10, 7)))
