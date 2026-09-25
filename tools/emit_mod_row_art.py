#!/usr/bin/env python3
"""把『模组』那一行的图**落成真实文件**（`.anm2` + 同名 `.pcx`）——构建/部署期用。

## 这个工具做什么

从 `runtime/source/mod_row_generated.hpp`（由 `tools/gamemenu_mod_row.py` 生成、有门禁钉住）
里读出**每个语言**那一行的 PCX 字节，逐字节落成两个文件：

    mod_row_<语言>.pcx    —— 与头文件里的字节**逐字节相同**（不重编码、不缩放）
    mod_row_<语言>.anm2   —— 照抄引擎自己的 `gamemenu.anm2` 形状（Version="18" Fps="30"），
                             精灵表写 `mod_row_<语言>.png`，动画只有一帧 `Idle`

## 为什么必须落成文件（这才是本工具存在的理由）

2026-09-23 的真机现象：主菜单里我们插的那一行「模组」**跑过若干次对局/关卡加载之后变透明** ——
绘制每帧照调、位置也对、对象指针非空，就是画不出来；用同一条**内存**路线重新加载，
拿回来的仍然是一张画不出来的图，重启游戏才好。

根因：那一行原本是把 PCX 字节交给引擎的**内存版**贴图载入器
（`ImageManager::LoadImage` 的内存重载）并登记在**我们自己编的缓存键**下
（`modrowg0.pcx` 这种名字）。我们是全工程唯一这么做的地方；引擎自己的行、以及所有模组
（EID 等）都是**按磁盘路径**加载（`ANM2::Load`），它们从不消失。关卡加载会把
"没有磁盘文件背书的贴图"从图片缓存里清掉 —— 我们那张就是被清掉的那一类。

⇒ 修法：**构建期把图落成文件**（本工具），运行期改成引擎自己的**按路径加载**
（`ANM2::Load(path, true)`，正是 `Sprite:Load` 与所有模组走的那条路）+ `ANM2::Render`。

## ★ 纪律：运行期**绝不**写 romfs 覆盖层

本工具只在**构建/部署期**往部署包里写文件（`--tree`）。**绝不允许**在游戏运行期往
`/atmosphere/contents/010021C000B6A000/romfs/` 写任何东西 —— 那份覆盖层由 `fs.mitm` 在
游戏启动时解析，历史上改动它 ⇒ 下一次启动在**装载阶段崩**（见 `AGENTS.md`「设备取证纪律」）。
"缺文件就运行期补"这种想法在这里是禁止的：缺文件应当在构建/部署时被门禁与
`tools/verify_device_install.py` 抓住。

## 关键约定：`.png` 与 `.pcx`

引擎解析精灵表路径时会把 `.png` **改写成 `.pcx`**（所以每个模组都得在旁边放同名的 `.pcx`，
见 `tools/device_mod_assets.py`）。⇒ `.anm2` 里写 `mod_row_<语言>.png`，
磁盘上放的是 `mod_row_<语言>.pcx`。这是**故意**的，不是笔误。

## 尺寸从哪来（不许抄头文件里的数字）

宽度/高度**从 PCX 头自己算**（PCX 头是小端 16 位：`bytes 4..5` = XMin、`6..7` = YMin、
`8..9` = XMax、`10..11` = YMax；`width = XMax-XMin+1`、`height = YMax-YMin+1`），
再用它**独立校验**头文件里那份 `width/height` —— 两者不一致就直接报错退出
（头文件被手改、或生成器量错，都会在这里当场爆掉，而不是留到真机上变成"图偏了一块"）。

⚠️ 注意字节位置：网上有些说法把 XMin/YMin 记成 `bytes 8..11`，那是**错的** ——
`4..11` 才是那四个 16 位字段（`12..15` 是分辨率）。本工具按**真实 PCX 格式**读，
并顺手核对 `manufacturer = 0x0A`。仓库里 `tools/gamemenu_mod_row.py` 的 `decode_pcx`
读的是 `bytes 8..11` 两个字段（XMax/YMax）再 +1，那是因为我们自己的这些图 XMin=YMin=0；
本工具不依赖这个前提。

## 用法

    # ① 只生成本地文件（门禁与离线检查用；默认行为）
    python3 tools/emit_mod_row_art.py --out /tmp/mod-row-art
    python3 tools/emit_mod_row_art.py --out /tmp/mod-row-art --languages zh

    # ② 直接落进部署包（★ 构建收尾那一步）
    python3 tools/emit_mod_row_art.py --tree runtime/.gdbsym-artifacts/deploy \
        --languages zh --also-english-root

    # ③ 八个语言全生成（正式包用；`--also-english-root` 让英文根下也各有一份）
    python3 tools/emit_mod_row_art.py --tree runtime/.gdbsym-artifacts/deploy --also-english-root

落点（`--tree`）：

    <tree>/atmosphere/contents/010021C000B6A000/romfs/rp_patch/resources.<语言>/gfx/ui/main menu/isaac-switch/mod_row_<语言>.{anm2,pcx}

英文用 `resources`（不是 `resources.en`）。`--also-english-root` 会把**同一批文件**
再往 `resources/`（英文根）也复制一份。

### `--also-english-root` 为什么需要

引擎挂载根到底是"当前语言目录"（`resources.<语言>/`）还是英文 `resources/` 目录，
**目前没有定论** —— 真机探针会一次试多条候选逻辑路径（见
`runtime/source/probe/native_mods_menu_probe.cpp` 里那张候选表）。要让"英文根"那条假设
也能被验到，英文目录下就必须有同样的文件。
"""

from __future__ import annotations

import argparse
import re
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GENERATED = ROOT / "runtime" / "source" / "mod_row_generated.hpp"

sys.path.insert(0, str(ROOT))
#: 菜单动画补层那一套（`--menu-row-layer`）：工具函数复用同一份实现，绝不另抄一套。
from tools.gamemenu_mod_row import (ArtError, DUMP_DIRECTORY_GLOB, discover_dump_root,  # noqa: E402
                                    emit_menu_anm2,
                                    language_directory as row_language_directory)

#: romfs 覆盖层根（部署包里的相对路径）。
ROMFS_RELATIVE = Path("atmosphere/contents/010021C000B6A000/romfs")
#: 游戏 romfs 里 `rp_patch` 之下放语言资源目录（其余语言是 `resources.<码>`）。
RP_PATCH = "rp_patch"
#: 我们这一行美术在页面资源里的落点（与探针里的候选逻辑路径一一对应）。
ASSET_SUBDIR = Path("gfx/ui/main menu/isaac-switch")

#: ★ 2026-09-23（批次 072）：**不再生成 `.anm2`**。
#:
#: 071 生成过 `mod_row_<语言>.anm2`（照抄引擎自己那份 `gamemenu.anm2` 的形状），运行期用
#: `ANM2::Load` + `ANM2::Render` 画 —— **真机上崩了**：`Data Abort @ 0x0`，栈为
#: `ANM2::Render → AnimationLayer::RenderFrame → GetSourceQuad`。原因是引擎按 `.anm2` 里
#: `<Spritesheet Path="mod_row_zh.png">` 去找的是 **`.png`**（模组都是 `.png` 与同名 `.pcx`
#: 都放），我们只放了 `.pcx` ⇒ 精灵表空 ⇒ 图层取图踩空。
#:
#: 现在运行期改用引擎的**按文件名版**贴图加载 `ImageManager::LoadImage(char const* path, ...)`
#: （和我们一直在用的内存版同一个管理器、同一个返回值形状），它要的就是这张 `.pcx` 本身
#: ⇒ 本工具只落 `.pcx`。**空的东西绝不拿去画**这条纪律也钉在探针那边（拿到空指针就不画）。


class EmitError(RuntimeError):
    """解析/校验失败 —— 一律当场报错退出，绝不"猜一个尺寸继续"。"""


def language_directory(language: str) -> str:
    """语言码 → 游戏 romfs 里的语言资源目录名（英文是裸 `resources`）。

    真值源在 `tools/gamemenu_mod_row.py`（补层那一步也用它算落点）；这里转一手，
    免得两处各写一份、改了一处就静默错位。
    """
    return row_language_directory(language)


# ---------------------------------------------------------------------------
# 解析 `mod_row_generated.hpp`
# ---------------------------------------------------------------------------

ARRAY_RE = re.compile(
    r"inline constexpr std::uint8_t kModRowPcx_(\w+)\[\]\s*=\s*\{(.*?)\};", re.S)
#: 布局项那一行：`{kModRowPcx_zh, sizeof(kModRowPcx_zh), 80, 39, 4.0F, 10.0F, 37.0F},`
#: 后三个是字在贴图内的包围盒（本工具不用，但一并要求存在 —— 少了说明头文件形状变了）。
SPRITE_RE = re.compile(
    r"\{kModRowPcx_(\w+),\s*sizeof\(kModRowPcx_\1\),\s*(\d+),\s*(\d+),"
    r"\s*[-0-9.]+F,\s*[-0-9.]+F,\s*[-0-9.]+F\}")


def parse_header(text: str) -> dict[str, dict]:
    """→ `{语言: {"pcx": bytes, "declared": (宽, 高)}}`。"""
    pcx_arrays: dict[str, bytes] = {}
    for match in ARRAY_RE.finditer(text):
        language = match.group(1)
        values = [int(token, 16) for token in re.findall(r"0x([0-9A-Fa-f]{2})", match.group(2))]
        if not values:
            raise EmitError(f"kModRowPcx_{language} 里一个字节都没解析到")
        # 逐字节核对：解析出来的个数必须与逗号数一致（漏字节比报错更糟）。
        tokens = [token for token in re.split(r"[,\s]+", match.group(2).strip()) if token]
        if len(tokens) != len(values):
            raise EmitError(
                f"kModRowPcx_{language}：{len(tokens)} 个记号里只认出 {len(values)} 个字节"
                "（格式不是 `0xNN,` 列表？）")
        pcx_arrays[language] = bytes(values)
    if not pcx_arrays:
        raise EmitError("头文件里一个 kModRowPcx_<语言> 数组都没找到")

    declared: dict[str, tuple[int, int]] = {}
    for match in SPRITE_RE.finditer(text):
        declared[match.group(1)] = (int(match.group(2)), int(match.group(3)))

    entries: dict[str, dict] = {}
    for language, data in pcx_arrays.items():
        if language not in declared:
            raise EmitError(
                f"{language}：有 PCX 字节，但布局里没找到 `{{kModRowPcx_{language}, "
                "sizeof(...), 宽, 高, ...}}` 那一项")
        entries[language] = {"pcx": data, "declared": declared[language]}
    for language in declared:
        if language not in pcx_arrays:
            raise EmitError(f"{language}：布局里有，但没有 kModRowPcx_{language} 字节数组")
    return entries


# ---------------------------------------------------------------------------
# PCX 头（尺寸的**独立**真值源）
# ---------------------------------------------------------------------------

def pcx_dimensions(data: bytes) -> tuple[int, int]:
    if len(data) < 128:
        raise EmitError(f"PCX 只有 {len(data)} 字节（连 128 字节的头都不够）")
    if data[0] != 0x0A:
        raise EmitError(f"PCX 制造商字节是 0x{data[0]:02X}，不是 0x0A")
    if data[2] != 1:
        raise EmitError(f"PCX 编码字节是 {data[2]}，不是 1（RLE）")
    if data[3] != 8:
        raise EmitError(f"PCX 每平面位数是 {data[3]}，不是 8")
    x_min, y_min, x_max, y_max = struct.unpack_from("<HHHH", data, 4)
    if x_max < x_min or y_max < y_min:
        raise EmitError(f"PCX 的头不自洽：XMin={x_min} XMax={x_max} YMin={y_min} YMax={y_max}")
    return x_max - x_min + 1, y_max - y_min + 1


def build_entries(header_text: str, languages: list[str]) -> list[dict]:
    parsed = parse_header(header_text)
    missing = [language for language in languages if language not in parsed]
    if missing:
        raise EmitError(f"头文件里没有这些语言的贴图：{missing}（有：{sorted(parsed)}）")
    entries = []
    for language in languages:
        entry = parsed[language]
        width, height = pcx_dimensions(entry["pcx"])
        declared_width, declared_height = entry["declared"]
        if (width, height) != (declared_width, declared_height):
            raise EmitError(
                f"{language}：PCX 头算出来是 {width}×{height}，而 mod_row_generated.hpp 里写的是 "
                f"{declared_width}×{declared_height} —— 头文件与字节不一致（手改了？生成器量错了？）")
        entries.append({
            "language": language,
            "pcx": entry["pcx"],
            "width": width,
            "height": height,
        })
    return entries


# ---------------------------------------------------------------------------
# 落盘
# ---------------------------------------------------------------------------

def write_pair(directory: Path, entry: dict) -> list[Path]:
    directory.mkdir(parents=True, exist_ok=True)
    language = entry["language"]
    pcx_path = directory / f"mod_row_{language}.pcx"
    pcx_path.write_bytes(entry["pcx"])
    return [pcx_path]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="把『模组』那一行的图落成真实文件（.pcx，供引擎按文件名加载）",
        formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    parser.add_argument("--out", help="只生成文件到这个目录（默认行为）")
    parser.add_argument("--tree", help="部署包根目录（会写到 <tree>/atmosphere/contents/.../romfs/rp_patch/...）")
    parser.add_argument("--languages", default="all",
                        help="`all`（默认）或逗号分隔的语言码，例如 `zh` / `zh,en`")
    parser.add_argument("--also-english-root", action="store_true",
                        help="额外把同一批文件往 `resources/`（英文根）复制一份")
    parser.add_argument("--menu-row-layer", action="store_true",
                        help="同时把 PC 那一层 `Item6` 补回菜单动画（`rp_patch/<语言根>/gfx/ui/"
                             "main menu/gamemenu.anm2`）—— 这一行由**引擎自己**画")
    parser.add_argument("--dump-root", default="auto",
                        help="游戏 dump 根（`--menu-row-layer` 要读里面的原版菜单动画与 PC 参考）；"
                             "`auto`（默认）= 按通配自己找，找不到就**跳过并大声提示**")
    parser.add_argument("--header", default=str(GENERATED), help=argparse.SUPPRESS)
    args = parser.parse_args()

    if bool(args.out) == bool(args.tree):
        print("必须且只能给一个：`--out <目录>`（只生成文件）或 `--tree <部署包目录>`",
              file=sys.stderr)
        return 2
    if args.also_english_root and not args.tree:
        print("`--also-english-root` 只在 `--tree` 下有意义（`--out` 里没有语言目录结构）",
              file=sys.stderr)
        return 2
    if args.menu_row_layer and not args.tree:
        print("`--menu-row-layer` 只在 `--tree` 下有意义（它要写进部署包的 romfs 覆盖层）",
              file=sys.stderr)
        return 2

    header_path = Path(args.header)
    if not header_path.is_file():
        print(f"找不到 {header_path}", file=sys.stderr)
        return 2
    header_text = header_path.read_text(encoding="utf-8")

    # `all` = 头文件里出现过的语言，**按头文件顺序**（与运行时的布局表同序，便于人眼核对）。
    available = list(parse_header(header_text))
    if args.languages.strip() == "all":
        languages = available
    else:
        languages = [item.strip() for item in args.languages.split(",") if item.strip()]
        if not languages:
            print("`--languages` 给空了", file=sys.stderr)
            return 2

    try:
        entries = build_entries(header_text, languages)
    except EmitError as error:
        print(f"✗ {error}", file=sys.stderr)
        return 1

    written: list[Path] = []
    if args.out:
        base = Path(args.out)
        for entry in entries:
            written += write_pair(base, entry)
    else:
        romfs = Path(args.tree) / ROMFS_RELATIVE
        for entry in entries:
            language = entry["language"]
            directory = romfs / RP_PATCH / language_directory(language) / ASSET_SUBDIR
            written += write_pair(directory, entry)
        if args.also_english_root:
            english = romfs / RP_PATCH / language_directory("en") / ASSET_SUBDIR
            for entry in entries:
                if entry["language"] == "en":
                    continue  # 就是英文根自己，不重复写
                written += write_pair(english, entry)
                # `write_pair` 用语言码命名 ⇒ 英文根下是 `mod_row_<该语言>.{anm2,pcx}`，
                # 这正是"引擎根其实是英文目录"那条候选路径要找的文件名。
        if args.menu_row_layer:
            # ★ 2026-09-23（A 路线）：把 PC 那一层 `Item6` 补回**引擎自己那份菜单动画**，
            #   让那一行由引擎的整页渲染画出来 —— 生命周期与其余五行完全同源。
            #   写的是 `rp_patch/<语言根>/gfx/ui/main menu/gamemenu.anm2`（覆盖游戏原版那份）。
            #
            # `auto`（默认）：按通配找 dump（**不写死目录名**，见 `DUMP_DIRECTORY_GLOB` 的注释）。
            # 找不到 ⇒ **大声提示并跳过**（那一行会退回运行时自己的兜底绘制，读数 [109] = 2，
            # 不会消失）；显式给了路径却读不到 ⇒ 当场报错，绝不悄悄少一层。
            dump_root = args.dump_root
            if dump_root in (None, "", "auto"):
                dump_root = discover_dump_root()
                if dump_root is None:
                    print("⚠ 没找到游戏 dump（按通配 " + DUMP_DIRECTORY_GLOB + " 找过）"
                          "⇒ 跳过「把 PC 的 Item6 层补回菜单动画」这一步；", file=sys.stderr)
                    print("  那一行会退回运行时自己的兜底绘制（读数 [109] = 2）。"
                          "要带上这一层就传 `--dump-root '<dump>/Program #0/1'`。", file=sys.stderr)
            if dump_root:
                try:
                    written += emit_menu_anm2(str(romfs / RP_PATCH), dump_root, languages)
                except row.ArtError as error:
                    print(f"✗ 菜单动画补层失败：{error}", file=sys.stderr)
                    return 1

    for path in written:
        print(f"{path}  {path.stat().st_size} 字节")
    print(f"共 {len(written)} 个文件（{len(entries)} 个语言）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
