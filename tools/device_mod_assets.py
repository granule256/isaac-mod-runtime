#!/usr/bin/env python3
"""卡上模组资源体检：**PNG 有没有同名 `.pcx`**（Switch 版引擎只按 `.pcx` 找贴图）。

## 为什么要有这个工具（2026-09-19，一次真实事故）

GoodTrip 在真机上"绘制代码明明在跑、却一个像素都不显示"，排查了**四轮**才定位到：
它是**手工拷进卡**的第三方模组，`resources/sprite/gt/*.png` 旁边**一个 `.pcx` 都没有** ——
而 `IsaacRepentance::Manager::LoadImage` 会把请求里的 `.png` **改写成 `.pcx`**、
`KAGE::Graphics::ImageManager::LoadImage` 又**按扩展名挑解码器** ⇒ 磁盘上没有真实 `.pcx` 时
贴图**静默加载失败**（`Load` 照样返回成功、画面空白、不报错）。

**这条知识本来就在仓库里**（`tools/png_to_pcx.py` 的头部注释写得很清楚，打包工具
`tools/pc_mod_manifest.py` 也一直这么做），但它只是一段**注释**：
走打包流程的模组没问题，**手工拷进来的**模组没人检查 ⇒ 于是同一个坑又踩了一次。

**所以把它变成命令**：任何模组上卡之后（或接新模组时）跑一次

    python3 tools/device_mod_assets.py                 # 体检卡上所有模组
    python3 tools/device_mod_assets.py --fix           # 缺什么就转什么并传上去
    python3 tools/device_mod_assets.py --local <目录>  # 只体检本地一份模组（离线，门禁用）

## 判据（**只看 `.anm2` 引用的贴图**，不是"看看有没有 .png"）

1. **`.anm2` 里 `Path="x.png"` 引用的每一张贴图，同目录必须有 `x.pcx`** ——
   因为精灵渲染走的是 `Manager::LoadImage`（会把 `.png` 改写成 `.pcx`）那条路。
2. **引用完全落地不了**（`.png` 与 `.pcx` 都不在）单独报 `missing_spritesheet`。
3. `resources/` 下**没有被任何 `.anm2` 引用**的 PNG **不判**：字体贴图就是这一类
   （`.fnt` 里按 `.png` 名字直接引用，引擎那条改写不适用）—— EID 的中文字体在真机上一直是好的，
   把它们算成缺项只会刷假警报（本工具第一版就犯过这个错，实测 39 条假阳性之后收窄）。
4. **报告要能被机器读**：`--json` 输出结构化结果，便于门禁与后续工具复用。

## 纪律（沿用 `tools/device_ftp.py`）

* FTP **一个连接只做一件事**、随用随关、动作之间留 1~3 秒；**不常驻**；
* `--fix` 会写卡：写之前先确认**游戏没在跑**（复用 `device_ftp` 的那条检查）。

退出码：0 = 全部通过；1 = 有缺项（或 `--fix` 之后仍有缺项）；2 = 参数/连接错误。
"""

from __future__ import annotations

import argparse
import fnmatch
import io
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.device_ftp import (  # noqa: E402
    DEFAULT_HOST,
    DEFAULT_PASSWORD,
    DEFAULT_PORT,
    DEFAULT_USER,
    RETRY_WAIT_SECONDS,
    SETTLE_SECONDS,
    assert_game_stopped,
    connect,
    with_retry,
)
from tools.png_to_pcx import PngFormatError, png_to_pcx  # noqa: E402

#: 卡上模组所在目录（`rom:/isaac_mods/mods` 对应的 SD 路径）。
CARD_MODS_DIRECTORY = "/atmosphere/contents/010021C000B6A000/romfs/isaac_mods/mods"

#: 只关心这些扩展名：它们是"引擎会按 `.pcx` 去找"的贴图。
TEXTURE_EXTENSIONS = (".png",)

#: `.anm2` 里的贴图引用：`<Spritesheet Path="minimap0.png" .../>`（相对该 `.anm2` 所在目录）。
ANM2_PATH_RE = re.compile(rb'Path="([^"]+)"')


@dataclass
class AssetFinding:
    """一条体检结论。`kind` 用固定词表，便于门禁与统计。"""

    kind: str  #: "missing_pcx" / "missing_spritesheet"
    path: str  #: 出问题的文件（相对模组根或卡上绝对路径）
    detail: str

    def as_dict(self) -> dict:
        return {"kind": self.kind, "path": self.path, "detail": self.detail}


@dataclass
class ModReport:
    mod: str
    textures: int = 0
    findings: list[AssetFinding] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "mod": self.mod,
            "textures": self.textures,
            "findings": [finding.as_dict() for finding in self.findings],
        }

    @property
    def ok(self) -> bool:
        return not self.findings


def anm2_spritesheet_findings(anm2_path: str, payload: bytes,
                              present: set[str]) -> list[AssetFinding]:
    """检查一个 `.anm2` 引用的贴图在 `present`（模组根相对路径集合）里的落地情况。

    两条判据（见本文件头部）：`.pcx` 必须在；两个都没有才报"引用完全落地不了"。
    纯函数：门禁与离线模式共用，不碰设备。
    """
    directory = str(Path(anm2_path).parent)
    findings: list[AssetFinding] = []
    for raw in ANM2_PATH_RE.findall(payload):
        name = raw.decode("utf-8", "replace")
        candidate = str(Path(directory) / name) if directory not in ("", ".") else name
        pcx = str(Path(candidate).with_suffix(".pcx"))
        if candidate not in present and pcx not in present:
            findings.append(
                AssetFinding(
                    kind="missing_spritesheet",
                    path=anm2_path,
                    detail=f"{anm2_path} 引用的贴图 {candidate} 与它的 .pcx 都不在模组里",
                )
            )
            continue
        if pcx not in present:
            findings.append(
                AssetFinding(
                    kind="missing_pcx",
                    path=pcx,
                    detail=f"{anm2_path} 引用 {name}，但同目录没有 {Path(pcx).name}"
                    "（引擎按 .pcx 找贴图 ⇒ 这张图在真机上不会显示）",
                )
            )
    return findings


def check_local_mod(mod_root: Path) -> ModReport:
    """体检本地一份模组目录（离线；门禁与排障都用它）。"""
    report = ModReport(mod=mod_root.name)
    files = [path for path in mod_root.rglob("*") if path.is_file()]
    relative = {str(path.relative_to(mod_root)): path for path in files}
    textures = [name for name in relative if name.lower().endswith(TEXTURE_EXTENSIONS)]
    report.textures = len(textures)

    present = set(relative)
    for name, path in sorted(relative.items()):
        if not name.lower().endswith(".anm2"):
            continue
        report.findings.extend(anm2_spritesheet_findings(name, path.read_bytes(), present))
    return report


def list_remote_tree(args, directory: str) -> list[tuple[str, int]]:
    """递归列卡上一个目录：返回 `[(相对路径, 字节数)]`。

    一次连接只做一件事 ⇒ 这里为**每个目录**开一次连接（慢，但符合纪律；
    一个模组的贴图目录数量是个位数）。
    """
    entries: list[tuple[str, int]] = []

    def walk(current: str, prefix: str) -> None:
        listing = with_retry(args, lambda ftp: _mlsd(ftp, current), f"ls {current}")
        for name, size, is_directory in listing:
            relative = f"{prefix}{name}"
            if is_directory:
                walk(f"{current}/{name}", f"{relative}/")
            else:
                entries.append((relative, size))

    walk(directory, "")
    return entries


def _mlsd(ftp, path: str) -> list[tuple[str, int, bool]]:
    """用 `MLSD` 拿结构化目录项；服务端不支持时退回 `LIST` 解析。"""
    try:
        return [
            (name, int(facts.get("size", "0") or 0), facts.get("type", "") == "dir")
            for name, facts in ftp.mlsd(path)
            if name not in (".", "..")
        ]
    except Exception:
        lines: list[str] = []
        ftp.retrlines(f"LIST {path}", lines.append)
        parsed = []
        for line in lines:
            parts = line.split(maxsplit=8)
            if len(parts) < 9:
                continue
            name = parts[8]
            is_directory = parts[0].startswith("d")
            try:
                size = int(parts[4])
            except ValueError:
                size = 0
            parsed.append((name, size, is_directory))
        return parsed


def check_card(args) -> list[ModReport]:
    """体检卡上所有模组（每个模组用独立的连接，遵守"一次连接只做一件事"）。"""
    mods = with_retry(args, lambda ftp: [name for name, facts in ftp.mlsd(CARD_MODS_DIRECTORY)
                                         if facts.get("type") == "dir"], "ls mods")
    reports: list[ModReport] = []
    for mod in sorted(mods):
        root = f"{CARD_MODS_DIRECTORY}/{mod}"
        entries = list_remote_tree(args, root)
        names = {name for name, _ in entries}
        report = ModReport(mod=mod)
        report.textures = len([name for name in names
                               if name.lower().endswith(TEXTURE_EXTENSIONS)])
        for name in sorted(names):
            if not name.lower().endswith(".anm2"):
                continue
            payload = with_retry(args, lambda ftp, p=f"{root}/{name}": _read(ftp, p),
                                 f"get {name}")
            for finding in anm2_spritesheet_findings(name, payload, names):
                finding.path = f"{root}/{finding.path}"
                report.findings.append(finding)
        reports.append(report)
    return reports


def _read(ftp, path: str) -> bytes:
    buffer = io.BytesIO()
    ftp.retrbinary(f"RETR {path}", buffer.write)
    return buffer.getvalue()


def fix_card(args, reports: list[ModReport]) -> int:
    """把"缺 `.pcx`"的那些补上：本地转码 → 上传 → 读回核对。

    只处理 `missing_pcx`；`.anm2` 引用缺失（`missing_spritesheet`）是模组自己的资源问题，
    工具不替它编文件。
    """
    if not assert_game_stopped(args):
        print("✗ 游戏正在运行 —— 现在写卡会与 fs.mitm 抢 SD。请先彻底退出游戏。", file=sys.stderr)
        return 2
    uploaded = 0
    for report in reports:
        for finding in report.findings:
            if finding.kind != "missing_pcx":
                continue
            remote_png = f"{finding.path[:-4]}.png"
            try:
                payload = with_retry(args, lambda ftp, p=remote_png: _read(ftp, p),
                                     f"get {remote_png}")
                converted = png_to_pcx(payload)
            except PngFormatError as error:
                print(f"✗ {remote_png}: 形态不受支持，跳过（{error}）", file=sys.stderr)
                continue
            with_retry(args, lambda ftp, p=finding.path, b=converted: _store(ftp, p, b),
                       f"put {finding.path}")
            uploaded += 1
            print(f"✓ 已补 {finding.path}（{len(converted)} 字节）")
    if uploaded:
        print(f"\n补了 {uploaded} 个 `.pcx`；**重新启动游戏**之后生效（贴图在模组加载时读）。")
    return 0


def _store(ftp, path: str, payload: bytes) -> None:
    ftp.storbinary(f"STOR {path}", io.BytesIO(payload))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--user", default=DEFAULT_USER)
    parser.add_argument("--password", default=DEFAULT_PASSWORD)
    parser.add_argument("--local", type=Path, default=None,
                        help="只体检本地一份模组目录（离线；不连设备）")
    parser.add_argument("--fix", action="store_true",
                        help="把缺的 `.pcx` 现场转码并传上卡（需要 FTP，且游戏必须没在跑）")
    parser.add_argument("--json", action="store_true", help="机器可读输出")
    args = parser.parse_args(argv)

    if args.local is not None:
        report = check_local_mod(args.local)
        reports = [report]
    else:
        reports = check_card(args)

    if args.json:
        print(json.dumps({"reports": [report.as_dict() for report in reports]},
                         ensure_ascii=False, indent=2))
    else:
        for report in reports:
            status = "✓" if report.ok else "✗"
            print(f"{status} {report.mod}：贴图 {report.textures} 个，问题 {len(report.findings)} 条")
            for finding in report.findings:
                print(f"    [{finding.kind}] {finding.path}\n        {finding.detail}")

    if args.fix and args.local is None:
        if any(not report.ok for report in reports):
            status = fix_card(args, reports)
            if status != 0:
                return status
            # 补完再体检一次，确认真的没有缺项（不信"我传过了"）。
            reports = check_card(args)
            if args.json:
                print(json.dumps({"reports": [report.as_dict() for report in reports]},
                                 ensure_ascii=False, indent=2))

    return 0 if all(report.ok for report in reports) else 1


if __name__ == "__main__":
    sys.exit(main())
