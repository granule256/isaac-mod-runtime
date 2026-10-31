#!/usr/bin/env python3
"""Build the title notice PCX/ANM2 and a small native constants header.

Only the Python standard library and repository PCX helpers are used. Font and
game assets stay in the local dump; generated files belong to the supplied tree.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import hashlib
from pathlib import Path
import struct
import sys
import xml.etree.ElementTree as ET

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
from tools.gamemenu_mod_row import Image, decode_pcx, encode_pcx, discover_dump_root
from tools.title_notice_paper import PaperArt, load_paper_art
from tools.notice_integrity_manifest import MANIFEST_PATH, write_manifest, install_cached_assets
from tools.png_to_pcx import _decode as decode_png

PAPER_WIDTH, PAPER_HEIGHT = 336, 216
MAX_PAGES = 32
ASSET_PATH = "gfx/ui/main menu/isaac-switch/nnotice.anm2"
LANGUAGES = ("en", "de", "es", "fr", "jp", "kr", "ru", "zh")
DEFAULT_UI = {"entry": "兼容层说明", "footer_locked": "请先读完 | L/R 翻页",
              "footer_auto": "长按 B 关闭 | L/R 翻页", "footer_manual": "B 关闭 | L/R 翻页"}
RESOURCE_ROOT = Path("atmosphere/contents/010021C000B6A000/romfs/rp_patch")
INK = (49, 36, 32, 255)
RED = (132, 28, 25, 255)
MUTED = (103, 83, 76, 255)
SUPPORT_CODES = ("wechat", "alipay", "kofi")
SUPPORT_X = (25, 123, 221)


@dataclass(frozen=True)
class Glyph:
    x: int
    y: int
    width: int
    height: int
    xoffset: int
    yoffset: int
    advance: int


@dataclass
class Font:
    line_height: int
    glyphs: dict[int, Glyph]
    image: Image

    def glyph(self, char: str) -> Glyph:
        try:
            return self.glyphs[ord(char)]
        except KeyError:
            raise ValueError(f"missing glyph U+{ord(char):04X} ({char!r})") from None

    def width(self, text: str) -> int:
        return sum(self.glyph(c).advance for c in text if c != "\n")


@dataclass(frozen=True)
class TextLine:
    text: str
    x: int
    y: int
    section: int
    paragraph: int
    kind: str


def load_font(path: Path, *, bitmap: bool = True) -> Font:
    """Read binary BMFont v3, with one case-insensitively located PCX page."""
    data = path.read_bytes()
    if data[:4] != b"BMF\x03":
        raise ValueError(f"{path}: expected binary BMFont v3")
    blocks = {}
    cursor = 4
    while cursor < len(data):
        if cursor + 5 > len(data):
            raise ValueError("truncated BMFont block header")
        kind, size = struct.unpack_from("<BI", data, cursor)
        cursor += 5
        if cursor + size > len(data):
            raise ValueError("truncated BMFont block")
        blocks[kind] = data[cursor:cursor + size]
        cursor += size
    if not all(i in blocks for i in (2, 3, 4)) or len(blocks[2]) < 15:
        raise ValueError("BMFont missing common, pages or chars block")
    line_height, _, width, height, pages = struct.unpack_from("<HHHHH", blocks[2])
    if pages != 1 or line_height <= 0:
        raise ValueError("title notice requires a positive-height single-page font")
    page_name = blocks[3].split(b"\0")[0].decode("utf-8")
    page = next((p for p in path.parent.iterdir() if p.name.casefold() == page_name.casefold()), None)
    if page is None:
        raise ValueError(f"BMFont bitmap not found: {page_name}")
    image = decode_pcx(str(page)) if bitmap else Image(0, 0, bytearray())
    if bitmap and (width, height) != (image.width, image.height):
        raise ValueError("BMFont bitmap dimensions do not match common block")
    if len(blocks[4]) % 20:
        raise ValueError("BMFont chars block is not a multiple of 20 bytes")
    glyphs = {}
    for offset in range(0, len(blocks[4]), 20):
        code, x, y, w, h, xo, yo, advance, page_id, _ = struct.unpack_from("<IHHHHhhhBB", blocks[4], offset)
        if page_id != 0 or x + w > width or y + h > height or advance < 0:
            raise ValueError(f"invalid BMFont glyph U+{code:04X}")
        glyphs[code] = Glyph(x, y, w, h, xo, yo, advance)
    return Font(line_height, glyphs, image)


def wrap_text(text: str, font: Font, max_width: int, *, prefer_words: bool = True) -> list[str]:
    """Prefer whitespace breaks; fall back to glyphs without losing characters."""
    lines, current, width = [], "", 0
    for char in text:
        if char == "\n":
            lines.append(current + char)
            current, width = "", 0
            continue
        glyph = font.glyph(char)
        if glyph.advance > max_width or glyph.width > max_width:
            raise ValueError(f"glyph U+{ord(char):04X} is wider than the {max_width}px text area")
        while current and width + glyph.advance > max_width:
            # Retain the separating whitespace on the preceding line. CJK and
            # words longer than a line still split at a glyph boundary.
            split = max((i + 1 for i, c in enumerate(current) if c.isspace()), default=0) if prefer_words else 0
            if split and current[:split].strip():
                lines.append(current[:split])
                current = current[split:]
                width = font.width(current)
            else:
                lines.append(current)
                current, width = "", 0
        current += char
        width += glyph.advance
    if current or not lines:
        lines.append(current)
    return lines


def paginate(content: dict, font: Font) -> list[list[TextLine]]:
    """Lay out sections at a fixed font size; retain source paragraph identity."""
    pages: list[list[TextLine]] = [[]]
    y = 49
    step = font.line_height + 2
    for si, section in enumerate(content["sections"]):
        if section.get("page_break_before") and pages[-1]:
            if len(pages) >= MAX_PAGES:
                raise ValueError("title notice exceeds 32 pages; split or shorten the content")
            pages.append([])
            y = 49
        elif si:
            y += 4
        kind = section.get("kind", "body")
        for pi, paragraph in enumerate(section["paragraphs"]):
            for text in wrap_text(paragraph, font, 280, prefer_words=content.get("language") not in ("jp", "zh")):
                if y + font.line_height > 185:
                    if len(pages) >= MAX_PAGES:
                        raise ValueError("title notice exceeds 32 pages; split or shorten the content")
                    pages.append([])
                    y = 49
                x = (PAPER_WIDTH - font.width(text)) // 2 if kind == "free" else 28
                pages[-1].append(TextLine(text, x, y, si, pi, kind))
                y += step
    # Append after ALL body pagination, so later sections cannot displace it.
    if support := content.get("support"):
        if len(pages) >= MAX_PAGES:
            raise ValueError("title notice exceeds 32 pages; split or shorten the content")
        if len(support["labels"]) != len(SUPPORT_CODES):
            raise ValueError("notice support requires WeChat, Alipay and Ko-fi labels")
        tail = []
        for x, label in zip(SUPPORT_X, support["labels"]):
            if not label or font.width(label) > 90:
                raise ValueError("notice support label is empty or wider than 90px")
            tail.append(TextLine(label, x + (90 - font.width(label)) // 2, 141,
                                 len(content["sections"]), -1, "support"))
        url = support["github"]
        if not url.startswith("https://github.com/") or url.count("/") != 4:
            raise ValueError("notice support requires a GitHub repository URL")
        owner, repo = url.removeprefix("https://").rsplit("/", 1)
        for text, top in [("GitHub: " + owner + "/", 157), (repo, 172)]:
            if font.width(text) > 280 or font.line_height > 13:
                raise ValueError("notice support link does not fit the final page")
            tail.append(TextLine(text, (336 - font.width(text)) // 2, top,
                                 len(content["sections"]), -1, "support"))
        pages.append(tail)
    return pages


def rectangle(image: Image, x: int, y: int, width: int, height: int, color: tuple) -> None:
    for py in range(max(y, 0), min(y + height, image.height)):
        for px in range(max(x, 0), min(x + width, image.width)):
            image.set_pixel(px, py, color)


def draw_text(image: Image, font: Font, text: str, x: int, y: int, color: tuple = INK) -> None:
    for char in text:
        if char == "\n":
            continue
        glyph = font.glyph(char)
        for gy in range(glyph.height):
            for gx in range(glyph.width):
                px, py = x + glyph.xoffset + gx, y + glyph.yoffset + gy
                if not (0 <= px < image.width and 0 <= py < image.height):
                    raise ValueError(f"text glyph {char!r} extends outside generated atlas")
                # Lanapixel contains white faces, opaque black outlines and
                # black drop shadows. White RGB is the face coverage; alpha
                # alone would merge adjacent 13px outlines at 10px advance.
                # RGB is already premultiplied, so do not multiply alpha twice.
                a = max(font.image.pixel(glyph.x + gx, glyph.y + gy)[:3])
                if a:
                    dst = image.pixel(px, py)
                    # Both bitmap and destination use premultiplied RGBA.
                    alpha = a * color[3] // 255
                    rgb = [(color[c] * alpha + dst[c] * (255 - alpha) + 127) // 255 for c in range(3)]
                    image.set_pixel(px, py, (*rgb, alpha + dst[3] * (255 - alpha) // 255))
        x += glyph.advance


def paper(image: Image, x: int, y: int, width: int, height: int) -> None:
    """Legacy fixture/preview fill; production localized builds require PaperArt."""
    for py in range(height):
        for px in range(width):
            inset = 2 + ((py // 11) % 3)
            top = 2 + ((px // 13) % 3)
            if inset <= px < width - inset and top <= py < height - top:
                edge = px in (inset, width - inset - 1) or py in (top, height - top - 1)
                grain = -3 if (px * 17 + py * 29) % 97 == 0 else 0
                color = (104, 81, 68, 255) if edge else (228 + grain, 213 + grain, 202 + grain, 255)
                image.set_pixel(x + px, y + py, color)


def _frame(parent, *, delay=1, x=0, y=0, xs=100, ys=100, rotation=0, interpolate=False, alpha=255, crop=None):
    attributes = {"XPosition": x, "YPosition": y, "XScale": xs, "YScale": ys,
                  "Delay": delay, "Visible": "true", "RedTint": 255, "GreenTint": 255,
                  "BlueTint": 255, "AlphaTint": alpha, "RedOffset": 0, "GreenOffset": 0,
                  "BlueOffset": 0, "Rotation": rotation, "Interpolated": str(interpolate).lower()}
    if crop:
        cx, cy, w, h, pivot_x, pivot_y = crop
        attributes.update(XCrop=cx, YCrop=cy, Width=w, Height=h, XPivot=pivot_x, YPivot=pivot_y)
    return ET.SubElement(parent, "Frame", {key: str(value) for key, value in attributes.items()})


def make_anm2(page_count: int, support_y: int, basename: str = "nnotice") -> bytes:
    actor = ET.Element("AnimatedActor")
    ET.SubElement(actor, "Info", CreatedBy="Isaac Switch Runtime", Version="18", Fps="30")
    content = ET.SubElement(actor, "Content")
    ET.SubElement(ET.SubElement(content, "Spritesheets"), "Spritesheet", Path=f"{basename}.pcx", Id="0")
    ET.SubElement(ET.SubElement(content, "Layers"), "Layer", Name="Paper", Id="0", SpritesheetId="0")
    ET.SubElement(content, "Nulls")
    ET.SubElement(content, "Events")
    animations = ET.SubElement(actor, "Animations", DefaultAnimation="Idle_0")

    def animation(name, crop, keys, *, y=0, alpha=255):
        total = sum(k[3] for k in keys)
        anim = ET.SubElement(animations, "Animation", Name=name, FrameNum=str(total), Loop="false")
        roots = ET.SubElement(anim, "RootAnimation")
        for x, xs, ys, delay, rotation in keys:
            _frame(roots, x=x, xs=xs, ys=ys, delay=delay, rotation=rotation, interpolate=len(keys) > 1)
        layer = ET.SubElement(ET.SubElement(anim, "LayerAnimations"), "LayerAnimation", LayerId="0", Visible="true")
        _frame(layer, crop=crop, delay=total, y=y, alpha=alpha)
        ET.SubElement(anim, "NullAnimations")
        ET.SubElement(anim, "Triggers")

    idle = [(0, 100, 100, 1, 0)]
    motion = {
        "Open": [(-700, 160, 40, 5, 0), (-176, 120, 80, 2, 0), (0, 80, 120, 2, 0), (0, 100, 100, 1, 0)],
        "Idle": idle,
        "Close": [(0, 100, 100, 2, 0), (0, 80, 120, 1, 0), (176, 120, 80, 6, 0), (700, 160, 40, 1, 0)],
        "FlipOut": [(0, 100, 100, 1, 0), (0, 65, 103, 1, 1), (0, 12, 106, 1, 2)],
        "FlipIn": [(0, 12, 106, 1, -2), (0, 65, 103, 1, -1), (0, 100, 100, 1, 0)],
    }
    for index in range(page_count):
        crop = ((index % 2) * PAPER_WIDTH, (index // 2) * PAPER_HEIGHT, PAPER_WIDTH, PAPER_HEIGHT, 168, 108)
        for name, keys in motion.items():
            animation(f"{name}_{index}", crop, keys)
    animation("Entry", (0, support_y, 120, 26, 60, 13), idle)
    animation("EntrySelected", (120, support_y, 120, 26, 60, 13), idle)
    animation("FooterAuto", (0, support_y + 26, 336, 18, 168, 0), idle, y=82)
    animation("FooterManual", (336, support_y + 26, 336, 18, 168, 0), idle, y=82)
    animation("FooterLocked", (0, support_y + 44, 336, 18, 168, 0), idle, y=82)
    animation("Progress", (0, support_y + 62, 60, 3, 0, 0), idle)
    animation("Dim", (60, support_y + 62, 1, 1, 0, 0), idle, alpha=140)
    ET.indent(actor, space="  ")
    return ET.tostring(actor, encoding="utf-8", xml_declaration=True) + b"\n"


def validate_labels(content: dict, font: Font) -> None:
    """Apply the same required-label checks to header-only and rendered builds."""
    labels = [(content["title"], 300, "title"),
              (content.get("subtitle", "{version}").replace("{version}", content["version"]), 300, "subtitle")]
    if support := content.get("support"):
        labels.extend([(support["title"], 300, "support title"),
                       (support["message"], 300, "support message")])
    ui = content.get("ui", DEFAULT_UI)
    labels.append((ui["entry"], 75, "entry"))
    labels.extend((ui[key], 260, key) for key in ("footer_locked", "footer_auto", "footer_manual"))
    for text, limit, name in labels:
        width = font.width(text)
        if not text or "\n" in text or width > limit:
            raise ValueError(f"notice {name} is empty, multiline or wider than {limit}px ({width}px)")
    # These invariant symbols are also painted into the atlas.
    font.width("0123456789/A?")


def render_asset(content: dict, font: Font, basename: str = "nnotice",
                 paper_art: PaperArt | None = None) -> tuple[dict, bytes, bytes]:
    validate_labels(content, font)
    pages = paginate(content, font)
    support_y = ((len(pages) + 1) // 2) * PAPER_HEIGHT
    atlas = Image(672, support_y + 65, bytearray(672 * (support_y + 65) * 4))
    for index, lines in enumerate(pages):
        x, y = (index % 2) * PAPER_WIDTH, (index // 2) * PAPER_HEIGHT
        (paper_art.paint if paper_art else paper)(atlas, x, y, PAPER_WIDTH, PAPER_HEIGHT)
        title = content["title"]
        subtitle = content.get("subtitle", "{version}").replace("{version}", content["version"])
        support = content.get("support") if lines and lines[0].kind == "support" else None
        if support:
            title, subtitle = support["title"], support["message"]
        for text, top, color in [(title, 14, INK), (subtitle, 29, MUTED)]:
            if font.width(text) > 300:
                raise ValueError("notice title/subtitle is wider than 300px")
            draw_text(atlas, font, text, x + (336 - font.width(text)) // 2, y + top, color)
        rectangle(atlas, x + 27, y + 44, 281, 1, MUTED)
        if support:
            for name, left in zip(SUPPORT_CODES, SUPPORT_X):
                path = Path(__file__).with_name("title_notice_support") / f"{name}.png"
                width, height, rgba = decode_png(path.read_bytes())
                if (width, height) != (90, 90):
                    raise ValueError(f"notice support {name} must be 90x90px")
                for row in range(height):
                    start = ((y + 49 + row) * atlas.width + x + left) * 4
                    atlas.rgba[start:start + width * 4] = rgba[row * width * 4:(row + 1) * width * 4]
        for line in lines:
            if line.kind == "warning":
                rectangle(atlas, x + 22, y + line.y - 1, 292, font.line_height + 2, (215, 193, 178, 255))
                rectangle(atlas, x + 22, y + line.y - 1, 2, font.line_height + 2, RED)
            draw_text(atlas, font, line.text, x + line.x, y + line.y, RED if line.kind in ("warning", "free") else INK)
        count = f"{index + 1}/{len(pages)}"
        draw_text(atlas, font, count, x + 313 - font.width(count), y + 190, MUTED)
        rectangle(atlas, x + 27, y + 186, 281, 1, MUTED)
    for selected, ex in [(False, 0), (True, 120)]:
        (paper_art.paint if paper_art else paper)(atlas, ex, support_y, 120, 26)
        draw_text(atlas, font, content.get("ui", DEFAULT_UI)["entry"], ex + 20, support_y + 6, INK)
        draw_text(atlas, font, "A" if selected else "?", ex + 103, support_y + 6, RED if selected else INK)
        if selected:
            rectangle(atlas, ex + 19, support_y + 20, 72, 1, RED)
            for i in range(5):
                rectangle(atlas, ex + 9, support_y + 8 + i, i + 1, 1, INK)
                rectangle(atlas, ex + 9, support_y + 13 + i, 5 - i, 1, INK)
    ui = content.get("ui", DEFAULT_UI)
    footers = [(0, support_y + 26, ui["footer_auto"]),
               (336, support_y + 26, ui["footer_manual"]),
               (0, support_y + 44, ui["footer_locked"])]
    for footer_x, footer_y, text in footers:
        if font.width(text) > 260:
            raise ValueError("footer text is wider than 260px")
        draw_text(atlas, font, text, footer_x + 19, footer_y, INK)
    rectangle(atlas, 0, support_y + 62, 60, 3, INK)
    rectangle(atlas, 60, support_y + 62, 1, 1, (0, 0, 0, 255))
    if max(atlas.width, atlas.height) > 4096:
        raise ValueError("title notice atlas exceeds 4096px")
    pcx, anm2 = encode_pcx(atlas), make_anm2(len(pages), support_y, basename)
    return ({"page_count": len(pages), "atlas_width": atlas.width, "atlas_height": atlas.height,
             "rgba_bytes": len(atlas.rgba), "pcx_bytes": len(pcx)}, pcx, anm2)


def write_pair(tree: Path, roots: list[str], basename: str, pcx: bytes, anm2: bytes) -> list[str]:
    files = []
    for root in roots:
        out = tree / RESOURCE_ROOT / root / "gfx/ui/main menu/isaac-switch"
        out.mkdir(parents=True, exist_ok=True)
        for name, data in [(f"{basename}.pcx", pcx), (f"{basename}.anm2", anm2)]:
            dest = out / name
            dest.write_bytes(data)
            files.append(str(dest))
    return files


def build_assets(tree: Path, header: Path, content: dict, font: Font) -> dict:
    """Legacy single-catalog builder, retained for fixtures and preview scripts."""
    result, pcx, anm2 = render_asset(content, font)
    result["files"] = write_pair(tree, ["resources", "resources.zh"], "nnotice", pcx, anm2)
    write_header(header, content, result["page_count"])
    return {**result, "header": str(header)}


def load_catalogs(content_path: Path, locales_path: Path | None = None) -> dict[str, dict]:
    chinese = json.loads(content_path.read_text(encoding="utf-8"))
    translations = json.loads((locales_path or Path(__file__).with_name("title_notice_locales.json")).read_text(encoding="utf-8"))
    if set(translations) != set(LANGUAGES) - {"zh"}:
        raise ValueError("notice catalogs must contain exactly en/de/es/fr/jp/kr/ru plus Chinese source")
    structure = [(s.get("kind", "body"), s.get("page_break_before", False), len(s["paragraphs"]))
                 for s in chinese["sections"]]
    catalogs = {}
    for language in LANGUAGES:
        content = dict(chinese if language == "zh" else translations[language])
        content["version"] = chinese["version"]
        content["language"] = language
        if [(s.get("kind", "body"), s.get("page_break_before", False), len(s["paragraphs"]))
                for s in content["sections"]] != structure:
            raise ValueError(f"notice {language} semantic sections differ from Chinese source")
        if set(content.get("ui", {})) != set(DEFAULT_UI):
            raise ValueError(f"notice {language} must translate every UI label")
        if bool(content.get("support")) != bool(chinese.get("support")):
            raise ValueError(f"notice {language} must translate the support page")
        if content.get("support") and content["support"]["github"] != chinese["support"]["github"]:
            raise ValueError(f"notice {language} must use the same GitHub repository")
        catalogs[language] = content
    return catalogs


def write_localized_header(header: Path, catalogs: dict, results: dict, manifest: bytes | None = None) -> None:
    rows = "".join(f'    {{"{code}", {results[code]["page_count"]}, "gfx/ui/main menu/isaac-switch/nnotice_{code}.anm2"}},\n'
                   for code in LANGUAGES)
    views = "".join(f'    {{kLocaleAssetsStorage[{i}].language, kLocaleAssetsStorage[{i}].pageCount, '
                    f'kLocaleAssetsStorage[{i}].assetPath}},\n' for i in range(len(LANGUAGES)))
    integrity = "// Metadata only: no integrity root; unsuitable for production compilation.\n"
    if manifest is not None:
        digest = ", ".join(f"0x{v:02x}" for v in hashlib.sha256(manifest).digest())
        integrity = (f'inline constexpr char kIntegrityManifestPath[] = "{MANIFEST_PATH}";\n'
                     f'inline constexpr std::array<std::uint8_t, 32> kIntegrityManifestDigest = {{{digest}}};\n'
                     'inline constexpr unsigned kIntegrityEntryCount = 30;\n')
    header.parent.mkdir(parents=True, exist_ok=True)
    header.write_text("// Generated by tools/build_title_notice.py; do not edit.\n#pragma once\n"
                      "#include <array>\n#include <cstdint>\n"
                      "namespace isaac::runtime::notice {\n" + integrity +
                      "struct LocaleAssets { const char* language; unsigned pageCount; const char* assetPath; };\n"
                      "// Pointer-free production policy; remains in the protected read-only range.\n"
                      "struct StoredLocaleAssets { char language[3]; unsigned pageCount; char assetPath[64]; };\n"
                      f"inline constexpr char kVersion[] = {json.dumps(catalogs['zh']['version'])};\n"
                      f"inline constexpr StoredLocaleAssets kLocaleAssetsStorage[8] = {{\n{rows}}};\n"
                      "// Preserve the metadata view for existing generated-header consumers.\n"
                      f"inline constexpr LocaleAssets kLocaleAssets[8] = {{\n{views}}};\n"
                      "inline constexpr unsigned kLocaleCount = 8;\n"
                      f"inline constexpr unsigned kPageCount = {results['zh']['page_count']};\n"
                      'inline constexpr char kAssetPath[] = "gfx/ui/main menu/isaac-switch/nnotice_zh.anm2";\n'
                      "inline constexpr float kPaperWidth = 336.F;\n"
                      "inline constexpr float kPaperHeight = 216.F;\n}\n", encoding="utf-8")


def build_localized_assets(tree: Path, header: Path, catalogs: dict, font: Font, *,
                           header_only: bool = False, paper_art: PaperArt | None = None) -> dict:
    """Build each locale once, sharing the decoded original font bitmap."""
    if tuple(catalogs) != LANGUAGES:
        raise ValueError("notice catalog order must be en/de/es/fr/jp/kr/ru/zh")
    if not header_only and paper_art is None:
        raise ValueError("localized notice builds require the original game paper art")
    results = {}
    for code, content in catalogs.items():
        if header_only:
            validate_labels(content, font)
            results[code] = {"page_count": len(paginate(content, font))}
        else:
            result, pcx, anm2 = render_asset(content, font, f"nnotice_{code}", paper_art)
            roots = ["resources"] + ([f"resources.{code}"] if code != "en" else [])
            result["files"] = write_pair(tree, roots, f"nnotice_{code}", pcx, anm2)
            results[code] = result
    manifest, manifest_path = (None, None)
    if not header_only:
        manifest, manifest_path = write_manifest(tree, [p for r in results.values() for p in r["files"]], catalogs["zh"]["version"])
    write_localized_header(header, catalogs, results, manifest)
    return {"version": catalogs["zh"]["version"], "locales": results, "header": str(header), "header_only": header_only,
            "manifest": manifest_path, "manifest_sha256": hashlib.sha256(manifest).hexdigest() if manifest else None}


def write_header(header: Path, content: dict, page_count: int) -> None:
    header.parent.mkdir(parents=True, exist_ok=True)
    header.write_text("// Generated by tools/build_title_notice.py; do not edit.\n#pragma once\n"
                      "namespace isaac::runtime::notice {\n"
                      f"inline constexpr char kVersion[] = {json.dumps(content['version'])};\n"
                      f"inline constexpr unsigned kPageCount = {page_count};\n"
                      f"inline constexpr char kAssetPath[] = {json.dumps(ASSET_PATH)};\n"
                      "inline constexpr float kPaperWidth = 336.F;\n"
                      "inline constexpr float kPaperHeight = 216.F;\n}\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tree", required=True, type=Path)
    parser.add_argument("--header", required=True, type=Path)
    parser.add_argument("--dump-root", default="auto")
    parser.add_argument("--content", type=Path, default=Path(__file__).with_name("title_notice_content.json"))
    parser.add_argument("--locales", type=Path, default=Path(__file__).with_name("title_notice_locales.json"))
    parser.add_argument("--header-only", action="store_true", help="write metadata-only constants without an integrity root (not suitable for production)")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--prepare-cache", type=Path, help="render once to cache and pin its manifest in the precompile header")
    mode.add_argument("--install-cache", type=Path, help="verify cache against the precompile header, then install exact bytes")
    args = parser.parse_args()
    if args.header_only and (args.prepare_cache or args.install_cache):
        parser.error("metadata-only headers cannot prepare/install an integrity cache")
    if args.install_cache:
        try:
            result = install_cached_assets(args.install_cache, args.tree, args.header)
        except (ValueError, OSError) as exc:
            parser.exit(1, f"title notice cache install failed: {exc}\n")
        print(json.dumps(result, indent=2))
        return
    dump = discover_dump_root() if args.dump_root == "auto" else args.dump_root
    if not dump:
        parser.error("game dump not found; provide --dump-root")
    try:
        catalogs = load_catalogs(args.content, args.locales)
        font = load_font(Path(dump) / "rp_patch/resources/font/cjk/lanapixel.fnt", bitmap=not args.header_only)
        paper_art = None if args.header_only else load_paper_art(Path(dump))
        result = build_localized_assets(args.prepare_cache or args.tree, args.header, catalogs, font,
                                        header_only=args.header_only, paper_art=paper_art)
    except (ValueError, OSError, KeyError) as exc:
        parser.exit(1, f"title notice build failed: {exc}\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
