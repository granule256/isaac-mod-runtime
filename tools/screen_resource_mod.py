"""体检一个刚下载的模组：它能不能直接放进 `mods/` 生效？（2026-09-21）

## 为什么需要它

用户从创意工坊 / 镜像站下载的模组有三种"形状"，**我们这个运行时只认其中一种**：

1. **创意工坊风格**（PC 版最常见的形状）—— 模组根目录下直接有 `resources/`：
   ```
   <模组名>/resources/gfx/items/collectibles/xxx.png
   ```
   这正是 `mods/<名字>/` 需要的形状，抄进去就能用。

2. **Switch LayeredFS 覆盖包**（GameBanana 的 Switch 专区全是这种）—— 按 title 的 romfs 铺开：
   ```
   atmosphere/contents/010021C000B6A000/romfs/resources/gfx/...
   ```
   内容是对的，但**外壳不对**：直接拷进卡里会走 Atmosphere 的文件覆盖层，
   绕开我们自己的模组装载器（也就绕开贴图桥）。要用这个运行时，得把 `romfs/` 里面那层
   剥出来、塞进 `mods/<名字>/`。

3. **GitHub 压缩包**—— 常常多套一层目录（`mod-main/resources/...`），要往下钻一层。

### 资源**层**（`MOD_LAYERS`）

模组的内容可以分几层，运行时逐层注册挂载点（`content_mount_service.hpp` 的 `kLeaves`）：
`resources`（本体层）、`resources-dlc3`（**忏悔层**：同名优先于 `resources`）、
`content`（模组 XML 层）。铺盘时**层名原样保留** —— 把 `resources-dlc3` 塞进 `resources/`
会改变覆盖语义（`resources/resources-dlc3/…` 更是一条永远读不到的路径）。

除了形状，还有两件会**静默失败**的事必须先查出来（真机上不报错、画面就是没变化）：

* **贴图格式**：贴图桥只支持 8 位、非隔行、灰度/RGB/带透明（PNG 色彩类型 0/2/4/6）。
  **调色板 PNG（色彩类型 3）不支持** —— 这类图会照旧不显示。很多老模组正好是调色板的。
* **路径对不上**：模组里的相对路径在本体资源里**没有同目录同名的文件**（多见于给旧版本做的模组、
  或作者打错字）。引擎永远不会去读它，等于没装。

## 怎么用

```bash
# 只体检（不写任何东西）
python3 tools/screen_resource_mod.py ~/Downloads/某某模组.zip

# 体检并直接铺进一个 mods 目录（默认拒绝覆盖已有目录）
python3 tools/screen_resource_mod.py ~/Downloads/某某模组.zip --install-to /tmp/mymods
```

退出码：`0` = 可以直接放；`1` = 有会静默失败的东西（贴图格式）；`2` = 用法或读文件出错。
"""

from __future__ import annotations

import argparse
import shutil
import struct
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

#: 卡上装模组的落点（对外给用户看的那条路径）。
CARD_MODS_DIR = "atmosphere/contents/010021C000B6A000/romfs/isaac_mods/mods"

#: 本体资源在我们仓库里的落点（用于"路径对不上"这项检查）。
#: 目录名带空格与 `#`，所以用 glob 找，不写死。
#:
#: 必须是两份合起来：`resources/` 是本体（只到 552 号道具），
#: `rp_patch/resources/` 是忏悔补丁（9046 个文件，道具到 716 号）。
#: 只比对前者会把**所有忏悔才有**的文件（后期道具、堕化角色、新房间）误报成"路径对不上"。
GAME_RESOURCE_GLOBS = (
    "The Binding of Isaac_ Afterbirth+ */Program #*/*/resources",
    "The Binding of Isaac_ Afterbirth+ */Program #*/*/rp_patch/resources",
    "The Binding of Isaac Afterbirth+ */Program #*/*/resources",
    "The Binding of Isaac Afterbirth+ */Program #*/*/rp_patch/resources",
)

#: 贴图桥支持的 PNG 色彩类型（与 `tools/png_to_pcx.py` 同一口径）。
SUPPORTED_PNG_COLOR_TYPES = {
    0: "灰度",
    2: "RGB",
    4: "灰度+透明",
    6: "RGB+透明",
}

#: LayeredFS 包里优先取哪一份 romfs（基础游戏本体那份）。
BASE_TITLE_HINT = "010021C000B6A000"

#: 拷贝时一律忽略的垃圾（版本控制、打包残留、系统隐藏文件）。
JUNK_NAMES = frozenset({".git", ".github", ".vscode", ".idea", "__MACOSX", "__pycache__"})
JUNK_SUFFIXES = frozenset({".ds_store", ".pyc", ".db"})


@dataclass
class Finding:
    """一条体检结论。`kind` 用于分组，`level` 决定它是否阻断（阻断 = 真机会静默没效果）。"""

    kind: str
    level: str  # "block"：会静默失败；"note"：只是提醒
    path: str
    detail: str


@dataclass
class PngStats:
    ok: int = 0
    unsupported: list[tuple[str, str]] = field(default_factory=list)


@dataclass
class Screening:
    """一个模组的完整体检结果。"""

    source: Path
    payload: Path
    layout: str
    entries: set[str] = field(default_factory=set)
    findings: list[Finding] = field(default_factory=list)
    png: PngStats = field(default_factory=PngStats)
    counts: dict[str, int] = field(default_factory=dict)

    @property
    def blocked(self) -> bool:
        return any(finding.level == "block" for finding in self.findings)

    @property
    def pure_resource(self) -> bool:
        """纯资源 = 没有 `main.lua`（有的话我们会尝试跑它，结局取决于它调了哪些 API）。"""
        return "main.lua" not in self.entries

    def of_kind(self, kind: str) -> list[Finding]:
        return [finding for finding in self.findings if finding.kind == kind]


def _is_junk(path: Path) -> bool:
    return path.name in JUNK_NAMES or path.suffix.lower() in JUNK_SUFFIXES


#: 模组可以带的**层目录**（PC 契约；运行时按这些名字注册挂载点，见
#: `runtime/src/application/mod/content_mount_service.hpp` 的 `kLeaves`）：
#:   * `resources`      —— 本体层（同名覆盖本体 `resources/`）；
#:   * `resources-dlc3` —— **忏悔层**：同名文件**优先于** `resources`（IsaacDocs
#:     `tutorials/directories-and-save-files.md:53`），覆盖忏悔资源的模组整包放这一层
#:     （2026-09-21 实例：`visible tinted rocks` 的 23 张 `gfx/grid/rocks_*.png`）；
#:   * `content`        —— 模组的 XML 层（`content/entities2.xml` 等）。
#: 这套层名以前只活在别处的注释里 ⇒ 本工具把 `resources-dlc3` 当成"缺外壳"、铺盘时还会把它
#: **套进** `resources/` 里（层就错了）。现在认形状/铺盘/数文件三处都按这张表走。
MOD_LAYERS = ("resources", "resources-dlc3", "content")


def _layer_dirs(payload: Path) -> list[tuple[str, Path]]:
    """模组里真实存在的层目录（一个都没有时返回空表 ⇒ 调用方按"缺外壳"处理）。"""
    return [(name, payload / name) for name in MOD_LAYERS if (payload / name).is_dir()]


def _has_resources(directory: Path) -> bool:
    """有没有**任何一层**资源目录（不再只看 `resources/`）。"""
    return any((directory / name).is_dir() for name in MOD_LAYERS)


def _romfs_dirs(root: Path) -> list[Path]:
    """找出 LayeredFS 包里所有 `contents/<title>/romfs/`。"""
    for base in (root, root / "atmosphere", root / "atmosphere" / "contents", root / "contents"):
        contents = base if base.name == "contents" else base / "contents"
        if not contents.is_dir():
            continue
        found = [title / "romfs" for title in sorted(contents.iterdir()) if (title / "romfs").is_dir()]
        if found:
            return found
        # 直接给的是 `contents/<title>/romfs` 那一层
        if (base / "romfs").is_dir() and base.parent.name == "contents":
            return [base / "romfs"]
    return []


def locate_payload(root: Path) -> tuple[Path, str, str | None]:
    """找到"真正要拷进去的那一层"，并说清它是哪种形状。

    返回 `(内容层, 形状说明, 警告)`；认不出来就抛 `ValueError`。
    """
    romfs_dirs = _romfs_dirs(root)
    if romfs_dirs:
        chosen = next((item for item in romfs_dirs if BASE_TITLE_HINT in str(item)), romfs_dirs[0])
        warning = None
        if len(romfs_dirs) > 1:
            others = "、".join(str(item.relative_to(root)) for item in romfs_dirs if item != chosen)
            warning = (
                f"这是按 title 铺开的包，里面有多份 romfs（选了含 {BASE_TITLE_HINT} 的那份）；"
                f"其余几份（{others}）里可能还有内容，必要时手工并进来"
            )
        else:
            warning = "外壳是「按 title 铺开的 romfs 覆盖层」，不是 mods/ 要的形状；下面会用剥壳后的内容来铺"
        return chosen, "Switch LayeredFS 覆盖包（GameBanana 那种）", warning

    if _has_resources(root):
        layers = "、".join(name for name, _ in _layer_dirs(root))
        return root, f"创意工坊风格（根目录下直接有资源层：{layers}）", None

    if _has_resources(root / "romfs"):
        return root / "romfs", "romfs 覆盖包（只有 romfs/ 这一层）", None

    # GitHub 压缩包常见多套一层。只往下钻一层，避免误判。
    children = [item for item in sorted(root.iterdir()) if item.is_dir() and not _is_junk(item)]
    if len(children) == 1:
        try:
            return locate_payload(children[0])
        except ValueError:
            pass

    # 兜底：直接就是 gfx/、music/ 这一层（少了 resources/ 外壳，铺的时候补上）。
    if any((root / name).is_dir() for name in ("gfx", "music", "sfx", "rooms")):
        return root, "缺 resources/ 外壳（铺的时候会自动套上）", None

    raise ValueError(
        f"认不出这是什么形状：{root}。既没有资源层目录（{'、'.join(MOD_LAYERS)}），"
        "也没有 atmosphere/contents/*/romfs/。"
    )


def png_header(path: Path) -> tuple[int, int, int, int, int]:
    """从 PNG 的 IHDR 里读出 (宽, 高, 位深, 色彩类型, 隔行方式)。不做完整解码。"""
    with path.open("rb") as handle:
        head = handle.read(33)
    if len(head) < 33 or head[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("不是 PNG（文件头不对）")
    width, height, bit_depth, color_type, _comp, _filter, interlace = struct.unpack_from(">IIBBBBB", head, 16)
    return width, height, bit_depth, color_type, interlace


def screen_pngs(payload: Path) -> PngStats:
    """逐张检查 PNG 是不是贴图桥能转的那几种。

    报的路径用"模组内的资源相对路径"（`gfx/...`），与"路径对不上"那项同一口径，
    方便和本体资源对照。
    """
    stats = PngStats()
    base = payload_base(payload)
    for path in sorted(base.rglob("*")):
        if not path.is_file() or path.suffix.lower() != ".png":
            continue
        relative = path.relative_to(base).as_posix()
        try:
            _width, _height, bit_depth, color_type, interlace = png_header(path)
        except (OSError, ValueError) as error:
            stats.unsupported.append((relative, str(error)))
            continue
        if bit_depth != 8 or interlace != 0:
            stats.unsupported.append((relative, f"{bit_depth} 位 / 隔行方式 {interlace}（只支持 8 位非隔行）"))
            continue
        if color_type not in SUPPORTED_PNG_COLOR_TYPES:
            shown = {3: "调色板(P)"}.get(color_type, f"色彩类型 {color_type}")
            stats.unsupported.append((relative, f"{shown} —— 不支持"))
            continue
        stats.ok += 1
    return stats


def game_resource_stems(resources: Path | list[Path]) -> set[tuple[str, str]]:
    """本体资源的 `(相对目录, 去掉扩展名的文件名)` 集合 —— 用来判"路径对不对得上"。

    只比"目录 + 主名"、不比扩展名：模组带 `.png`、本体是同名 `.pcx` 是**正常情况**
    （贴图桥就是干这个的）。

    可以给多份（本体 + 忏悔补丁），会合并 —— 见 `GAME_RESOURCE_GLOBS` 那段说明。
    """
    roots = [resources] if isinstance(resources, Path) else resources
    stems: set[tuple[str, str]] = set()
    for root in roots:
        for path in root.rglob("*"):
            if path.is_file():
                stems.add((path.parent.relative_to(root).as_posix(), path.stem.lower()))
    return stems


def payload_base(payload: Path) -> Path:
    """模组里"资源的根"：有 `resources/` 就用它，否则内容层自己就是根（仅用于旧的单层判据）。"""
    return payload / "resources" if (payload / "resources").is_dir() else payload


def missing_targets(payload: Path, resources: Path | list[Path]) -> list[str]:
    """模组里的文件，哪些在本体资源里找不到同目录同名的对应物。

    逐**层**比对（`resources` 与 `resources-dlc3` 各比一遍）：本体那份资源树在 Switch 上是
    `resources/` + `rp_patch/resources/` 两份合并（见 `default_game_resources`），
    所以两层的文件都拿同一份"已知集合"来判 —— 判的是"路径对不对"，不判"层放得对不对"
    （后者由运行时按层序处理：dlc3 层优先级最高）。
    """
    known = game_resource_stems(resources)
    misses: list[str] = []
    layers = _layer_dirs(payload) or [("resources", payload)]
    for name, base in layers:
        for path in sorted(base.rglob("*")):
            if not path.is_file() or _is_junk(path):
                continue
            relative = path.relative_to(base)
            key = (relative.parent.as_posix(), path.stem.lower())
            if key not in known:
                misses.append(f"{name}/{relative.as_posix()}")
    return misses


def count_files(payload: Path) -> dict[str, int]:
    """按扩展名数一遍。"""
    counts: dict[str, int] = {}
    for path in payload.rglob("*"):
        if not path.is_file() or _is_junk(path):
            continue
        suffix = path.suffix.lower() or "(无扩展名)"
        counts[suffix] = counts.get(suffix, 0) + 1
    return counts


def screen(source: Path, *, resources: Path | list[Path] | None = None) -> Screening:
    """跑完所有检查。`source` 必须是**已经解压好**的目录。"""
    payload, layout, warning = locate_payload(source)
    result = Screening(source=source, payload=payload, layout=layout)
    result.entries = {item.name for item in payload.iterdir()}
    if warning:
        result.findings.append(Finding("形状", "note", ".", warning))

    if "main.lua" in result.entries:
        result.findings.append(
            Finding(
                "Lua 代码",
                "note",
                "main.lua",
                "带 Lua 的模组不是纯资源：我们会尝试跑它，能不能用取决于它调了哪些 API",
            )
        )

    result.counts = count_files(payload)
    result.png = screen_pngs(payload)
    for path, reason in result.png.unsupported:
        result.findings.append(Finding("贴图格式", "block", path, f"贴图桥转不了（{reason}）⇒ 这张图不会显示"))

    if resources is not None:
        for path in missing_targets(payload, resources):
            result.findings.append(
                Finding("路径对不上", "note", path, "本体资源里没有同目录同名的文件 ⇒ 引擎永远不会读它")
            )
    return result


def screen_zip(archive: Path, *, keep: Path, resources: Path | None = None) -> Screening:
    """解压到 `keep` 再体检（`--install-to` 要用同一个目录，所以解压位置由调用方给）。"""
    keep.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as bundle:
        bundle.extractall(keep)
    result = screen(keep, resources=resources)
    # 报头和默认目录名都用 zip 自己的名字，不要暴露临时解压目录。
    result.source = archive
    return result


def install(result: Screening, mods_root: Path, *, name: str | None, force: bool) -> Path:
    """把剥好壳的内容铺成 `mods/<名字>/{resources/…, resources-dlc3/…, content/…, main.lua, metadata.xml}`。

    ★ **层要原样保留**：`resources-dlc3` 是忏悔层（同名优先于 `resources`），
    把它塞进 `resources/` 会改变覆盖语义（而且 `resources/resources-dlc3/…` 根本不会被读）。
    """
    mod_name = name or result.source.stem or result.payload.name
    destination = mods_root / mod_name
    if destination.exists() and not force:
        raise ValueError(f"{destination} 已存在（要覆盖就加 --force）")
    destination.mkdir(parents=True, exist_ok=True)

    payload = result.payload
    layers = _layer_dirs(payload)
    if layers:
        for layer_name, directory in layers:
            shutil.copytree(directory, destination / layer_name, dirs_exist_ok=True,
                            ignore=_ignore_junk)
        root_files = [item for item in sorted(payload.iterdir()) if item.is_file() and not _is_junk(item)]
    else:
        # 缺任何一层外壳：整层塞进 resources/，根目录不放东西。
        shutil.copytree(payload, destination / "resources", dirs_exist_ok=True, ignore=_ignore_junk)
        root_files = []
    for item in root_files:
        shutil.copy2(item, destination / item.name)
    return destination


def _ignore_junk(_directory: str, names: list[str]) -> list[str]:
    return [name for name in names if name in JUNK_NAMES or Path(name).suffix.lower() in JUNK_SUFFIXES]


def default_game_resources() -> list[Path]:
    """仓库里能找到的本体资源根（本体 + 忏悔补丁）。找不到就是空列表。"""
    roots: list[Path] = []
    for pattern in GAME_RESOURCE_GLOBS:
        for candidate in sorted(REPO_ROOT.glob(pattern)):
            if candidate.is_dir() and candidate not in roots:
                roots.append(candidate)
    return roots


def format_report(result: Screening, *, per_kind_limit: int = 8) -> str:
    lines: list[str] = []
    lines.append(f"模组      {result.source.name}")
    lines.append(f"形状      {result.layout}")
    lines.append(f"内容层    {result.payload}")
    shown = "、".join(f"{key} × {value}" for key, value in sorted(result.counts.items())) or "（空）"
    lines.append(f"文件      {shown}")
    lines.append(
        "性质      纯资源 ✓（没有 main.lua，只替换素材）"
        if result.pure_resource
        else "性质      **不是纯资源**（有 main.lua，我们会尝试跑它）"
    )
    if result.png.ok or result.png.unsupported:
        lines.append(f"贴图      PNG 里能转 {result.png.ok} 张，转不了 {len(result.png.unsupported)} 张")

    for kind in ("形状", "Lua 代码", "贴图格式", "路径对不上"):
        findings = result.of_kind(kind)
        for finding in findings[:per_kind_limit]:
            mark = "✗" if finding.level == "block" else "⚠"
            lines.append(f"  {mark} [{finding.kind}] {finding.path} —— {finding.detail}")
        if len(findings) > per_kind_limit:
            lines.append(f"  ⚠ [{kind}] 还有 {len(findings) - per_kind_limit} 条同类，见 --install-to 之后的自查")

    lines.append("")
    if result.blocked:
        lines.append("结论      **有会静默失败的东西**（上面的 ✗）：装是能装，但那几张图不会显示。")
    elif result.of_kind("路径对不上"):
        lines.append(
            f"结论      **可以放进 mods/**；但有 {len(result.of_kind('路径对不上'))} 个文件在本体里找不到对应物"
            "——纯替换类模组出现这个多半是版本不符（有些会等于白装）。"
        )
    else:
        lines.append("结论      **可以直接放进 mods/**（引擎下次启动就会挂上）。")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="体检一个刚下载的模组，判断它能不能放进 mods/ 生效")
    parser.add_argument("source", type=Path, help="模组目录或 zip")
    parser.add_argument("--install-to", type=Path, help="铺进这个 mods 目录（默认只体检，不写任何东西）")
    parser.add_argument("--name", help="铺进去用的目录名（默认取 zip / 目录名）")
    parser.add_argument("--force", action="store_true", help="目标目录已存在时也覆盖")
    parser.add_argument(
        "--game-resources",
        type=Path,
        action="append",
        help="本体 resources 目录（可给多次；默认自动找仓库里的本体 + 忏悔补丁两份）",
    )
    parser.add_argument("--no-path-check", action="store_true", help="跳过「路径对不上」这项检查")
    args = parser.parse_args(argv)

    if not args.source.exists():
        parser.exit(2, f"找不到：{args.source}\n")

    resources: list[Path] | None = None
    if not args.no_path_check:
        resources = args.game_resources or default_game_resources()
        if not resources:
            print("⚠ 仓库里没找到本体 resources 目录，跳过「路径对不上」检查。")
            resources = None

    extracted: Path | None = None
    try:
        if args.source.is_dir():
            result = screen(args.source, resources=resources)
        else:
            # zip 一律先解到临时目录：体检、铺盘都对着同一份解压结果做，完了删掉。
            extracted = Path(tempfile.mkdtemp(prefix="screen-mod-"))
            result = screen_zip(args.source, keep=extracted, resources=resources)
    except (OSError, ValueError, zipfile.BadZipFile) as error:
        if extracted is not None:
            shutil.rmtree(extracted, ignore_errors=True)
        parser.exit(2, f"读不了 {args.source}：{error}\n")

    print(format_report(result))

    if args.install_to is not None:
        try:
            destination = install(result, args.install_to, name=args.name, force=args.force)
        except (OSError, ValueError) as error:
            parser.exit(2, f"铺不进去：{error}\n")
        print(f"\n已铺到    {destination}")
        print(f"卡上位置  {CARD_MODS_DIR}/{destination.name}")
        print("下一步    把上面这个目录整个拷到卡上同名路径，然后启动游戏（改动素材后要重启游戏才生效）")

    if extracted is not None:
        shutil.rmtree(extracted, ignore_errors=True)
    return 1 if result.blocked else 0


if __name__ == "__main__":
    raise SystemExit(main())
