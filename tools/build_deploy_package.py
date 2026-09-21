#!/usr/bin/env python3
"""把"当前这一版"打成可直接拷进 SD 卡的发布包（目录树 + SHA256SUMS + zip）。

## 为什么要有它

之前的发布包是手工拼的（`dist/isaac-eid-release-20260917/` 那种：`atmosphere/` 树 + `SHA256SUMS.txt` +
`安装说明.md`），每次都得重新"找来源、拷文件、算哈希"，容易漏。这里把流程固定成一条命令。

## 它做什么

1. 按参数把 **运行时**（`subsdk9` + `main.npdm`）与若干 **模组目录** 拷进 `<输出>/atmosphere/...`；
2. 可选：把一个 **EID 配置 JSON** 放进 `<输出>/EID配置/eid-config.json`（附应用方法见安装说明）；
3. 生成 `SHA256SUMS.txt`（`hash  相对路径`，与上一版发布包同格式）；
4. 打成 `<输出>.zip`（zip 里以输出目录名为根，便于直接解压到 SD 卡根）。

## ★ `atmosphere/nro_patches/`：**只带一份，别的一律不带**（2026-09-22 修正）

两类补丁的期望**正好相反**，这里必须分开说：

* **5 份旧 IPS 后端遗留**（`manager-update-relay` / `manager-render-relay` / `pre-get-collectible-relay` /
  `rebuild-mount-points-relay` / `render-present-relay`）：**不许带**。现在的运行时装入口中继前要逐字节
  核对**原版**入口，带上它们会 ⇒ **一个挂点都装不上、所有模组连带我们自己的菜单全消失**
  （2026-09-20 真实事故，失败码 2 = `EntryMismatch`）。
* **`isaac-repentance-lifecycle-relay`：必须带**。它是"游戏开局"挂点唯一的实现方式
  （`HookBackend::RelaySlot`，见 `hook_catalog.hpp`）：补丁把 `Game::Start` /
  `Game::StartFromSavedState` 的调用点改成 `b <代码洞>`，运行时只往代码洞后面的槽里发布回调。
  **卡上缺了它 ⇒ 开局事件永远不来 ⇒ EID 的套装查找表建不起来 ⇒ 套装进度恒 `0/3`**
  （2026-09-17 查了很久的那次；2026-09-22 又在卡上复现，证据：两处调用点仍是原版 `bl`、回调槽 = 0）。
  注意这一路是 `required=false` ⇒ 装不上**只记 Skipped、不计入失败**，
  所以"挂点全装好、零失败"这句话**不能**用来判断它是不是好的。

本工具因此只把 `REQUIRED_RELAY_PATCHES` 里那几份写进包，并在安装说明里写明"这一份不能删"。

## 用法

    python3 tools/build_deploy_package.py --name isaac-switch-release-20260920 \\
        --runtime runtime/.gdbsym-artifacts/deploy \\
        --mod "dist/isaac-eid-release-20260917/atmosphere/contents/010021C000B6A000/romfs/isaac_mods/mods/external item descriptions_836319872" \\
        --mod /tmp/goodtripfixed --mod /tmp/q4-items \\
        --config /tmp/eid-config-from-device.json

    # 只校验（把包里的每个文件与卡上同名文件比大小；再对 --hash-sample 里点名的文件比 sha256）
    python3 tools/build_deploy_package.py --verify-device dist/isaac-switch-release-20260920
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

CONTENT_ID = "010021C000B6A000"
MODS_RELATIVE = Path("atmosphere/contents") / CONTENT_ID / "romfs/isaac_mods/mods"
#: ★ 2026-09-21 新增：模组清单。运行时读的路径是**写死的**
#: （`runtime_constants.hpp`/`manifest_service.hpp` 的 `kRomfsModManifestPath =
#: "rom:/isaac_mods/manifest.json"`，由 `ManifestService` 解析）。
#:
#: ★★ 2026-09-21 晚更正一句**过期结论**（原注释写的是"干净卡上一个模组都不加载"，不准确）：
#: **没有清单并不会让模组全都不加载** —— `ManifestService::ResolveAll` 读不到/解析不了清单时
#: （`failure.step == ManifestRead|ManifestParse`），`hook_manager.cpp` 会转走"方案 A"：
#: `ModDiscoveryService::Discover()` 扫 `isaac_mods/mods/` 的子目录、按名字升序全部当模组
#: （入口固定取 `mods/<名字>/main.lua`，没有它则如实报 `EntryAbsent` 但**保留内容挂载点**）。
#: 2026-09-20 那版之所以漏掉 GoodTrip，是**另一条**机制：卡上当时已有一份旧清单，
#: 而"清单之外的目录也要加载"（`AppendUnlisted` 合并）是 2026-09-21 才做的。
#:
#: 那为什么包里**仍然必须**带清单？因为它能表达**扫目录表达不了的三件事**：
#:   1. **加载顺序** —— 清单里的在前（按书写顺序），未列出的按名字升序追加；只有扫描时顺序=名字序；
#:   2. **入口不是 `main.lua` 的模组** —— 扫描写死 `main.lua`，别的入口只能靠清单写；
#:   3. **`enabled: false`** —— 关掉一个模组但**不删目录**（且合并逻辑不会把它再捡回来）。
#: 另外它是"这个包**打算装哪几个**模组"的显式声明：安装后的初始状态、诊断与读数都对着它看。
MANIFEST_RELATIVE = (Path("atmosphere/contents") / CONTENT_ID
                     / "romfs/isaac_mods/manifest.json")
EXEFS_RELATIVE = Path("atmosphere/contents") / CONTENT_ID / "exefs"
#: 运行时构建产物里要带上的文件（exefs 里那两个；补丁见 `REQUIRED_RELAY_PATCHES`）
RUNTIME_FILES = ("subsdk9", "main.npdm")
#: **必须**进包的 IPS 补丁（理由见模块 docstring）。名字 = 构建产物
#: `atmosphere/nro_patches/<名字>/` 这个目录名；目录里的 `.ips` 文件名带游戏 build id，原样拷。
REQUIRED_RELAY_PATCHES = ("isaac-repentance-lifecycle-relay",)
#: **不许**进包的旧 IPS 后端遗留（带上去会让所有挂点失效，见模块 docstring）。
#: 这里显式列出来是为了让门禁能断言"包里没有它们"，而不是靠"我们没拷"这种沉默保证。
FORBIDDEN_RELAY_PATCHES = (
    "isaac-repentance-manager-update-relay",
    "isaac-repentance-manager-render-relay",
    "isaac-repentance-pre-get-collectible-relay",
    "isaac-repentance-rebuild-mount-points-relay",
    "isaac-repentance-render-present-relay",
)


def mod_entry(directory: str, source: Path) -> str | None:
    """清单里的 `entry`。运行时按 `mods/<directory>/…lua` 校验（`mod_manifest.cpp` 的
    `IsSafeEntry`：前缀必须是 `mods/<目录>/`、后缀必须是 `.lua`）。

    优先 `main.lua`；否则取顶层唯一那个 `.lua`；一个都没有 ⇒ 返回 `None`（纯资源模组，
    清单解析器允许省略 `entry` —— 见 `runtime/source/mod_manifest.hpp` 的注释）。
    """
    if (source / "main.lua").is_file():
        return f"mods/{directory}/main.lua"
    candidates = sorted(path.name for path in source.glob("*.lua"))
    if len(candidates) == 1:
        return f"mods/{directory}/{candidates[0]}"
    return None


def write_manifest(output: Path, sources: list[Path]) -> int:
    """把"包内实际带上的模组"写成 `isaac_mods/manifest.json`（覆盖同名文件）。"""
    mods = []
    for source in sources:
        entry = mod_entry(source.name, source)
        item: dict[str, object] = {"directory": source.name, "enabled": True}
        if entry is not None:
            item["entry"] = entry
        mods.append(item)
        if entry is None:
            print(f"  ⚠ {source.name}：顶层没有 .lua ⇒ 清单里不写 entry（按纯资源模组处理）")
    path = output / MANIFEST_RELATIVE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"schema_version": 1, "mods": mods}, ensure_ascii=False, indent=2)
                    + "\n", encoding="utf-8")
    print(f"模组清单  {len(mods)} 条 → {MANIFEST_RELATIVE.as_posix()}")
    return 0


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


#: macOS 的目录元数据，别进包（2026-09-20：第一版包里混进了 `.DS_Store` 与 `._*`）
JUNK_NAMES = {".DS_Store"}


def is_junk(path: Path) -> bool:
    return path.name in JUNK_NAMES or path.name.startswith("._")


def copy_tree(source: Path, target: Path, *, drop_pcx: bool = False) -> int:
    """拷贝模组树。`drop_pcx=True` 时**跳过** `.pcx`（2026-09-21 起可选）。

    为什么可以丢：运行时的贴图桥会在引擎读 `.pcx` 时按需把同名 `.png` 转成 PCX
    （`KAGE::Graphics::ImagePcx::Load` 兜底 + `GetMountedFilePath` 补位），
    所以"必须自带 `.pcx`"这条约束已经取消 —— 干净安装也能靠桥显示。
    """
    count = 0
    for item in sorted(source.rglob("*")):
        if item.is_dir() or is_junk(item):
            continue
        if drop_pcx and item.suffix.lower() == ".pcx":
            continue
        relative = item.relative_to(source)
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(item, destination)
        count += 1
    return count


def check_mod_assets(source: Path) -> tuple[int, int]:
    """打包前体检模组的贴图。**`missing_pcx` 一律拒绝打包**（返回 `(missing_pcx, other)`）。

    ## 为什么把它接进打包（2026-09-21 真实事故）

    2026-09-20 那版发布包里的 `goodtripfixed` 是**只带 `.png` 的那份源**（卡上那份在 09-19 已经被
    `tools/device_mod_assets.py --fix` 补过 `.pcx`）⇒ 干净安装时**小地图一张图都不显示**
    （`Load` 成功、画面空白、不报错），用户看到的就是"GoodTrip 在列表里、但用不了"。
    这条知识本来只在注释与那条手动命令里 —— 打包工具不知道，于是又踩一次。
    `missing_spritesheet`（`.png`/`.pcx` 都不在）属模组自己的资源问题，只提示不拦。
    """
    import device_mod_assets  # noqa: PLC0415  （同目录的仓库工具，见上面 sys.path）

    report = device_mod_assets.check_local_mod(source)
    missing_pcx = [f for f in report.findings if f.kind == "missing_pcx"]
    other = [f for f in report.findings if f.kind != "missing_pcx"]
    if missing_pcx:
        print(f"✗ {source.name}：{len(missing_pcx)} 张贴图缺同名 `.pcx` ⇒ 真机上**不会显示**：")
        for finding in missing_pcx[:6]:
            print(f"    {finding.path}")
        print("  ⇒ 先跑 `python3 tools/device_mod_assets.py --fix`（或 --local <模组> 看全量），"
              "再打包；确实要带伤发布就加 --allow-asset-problems")
    for finding in other:
        print(f"  ⚠ {source.name}：{finding.kind} —— {finding.path}（模组自身资源问题，不拦）")
    return len(missing_pcx), len(other)


def check_png_convertibility(source: Path) -> int:
    """打包前体检：模组带的 PNG，运行时的贴图桥**能不能转**（返回不合格张数）。

    ## 为什么要有这条（2026-09-21，跟着 `--drop-mod-pcx` 一起加的）

    `--drop-mod-pcx`（发布包的默认做法）之后，模组贴图**全靠运行时把 PNG 转成 PCX**
    （`Manager::LoadImage` 把请求的 `.png` 改写成 `.pcx`，贴图桥按需转码）。
    桥只支持 **8 位、非隔行、色彩类型 0/2/4/6**；调色板 PNG（类型 3）、16 位、隔行**转不了** ——
    真机现象是"`Load` 成功、画面空白、不报错"，也就是用户嘴里的**"这个模组装了没用"**。

    ⇒ 丢了 `.pcx` 就必须补上这条判据：`copy_tree` 只负责搬文件，它不会告诉你哪张图转不了。

    ## 字体 PNG 豁免

    字体贴图是 `.fnt` 按 `.png` **名字直接引用**的（引擎那条 `.png→.pcx` 改写不适用），
    不经过桥、不需要转码。把它们算成不合格只会刷假警报 —— 2026-09-19 实测过：
    那版体检工具把 EID 的 39 张字体图全报成缺项。所以这里跳过路径里含 `font` 目录的 PNG。
    """
    sys.path.insert(0, str(ROOT / "tools"))
    from screen_resource_mod import png_header  # noqa: PLC0415

    unacceptable = 0
    for path in sorted(source.rglob("*.png")):
        if "font" in path.relative_to(source).parts:
            continue
        try:
            _w, _h, depth, color, interlace = png_header(path)
        except Exception as error:  # noqa: BLE001 - 读不了就如实报，不猜
            print(f"  ✗ {source.name}：{path.relative_to(source)} 读不了（{error}）")
            unacceptable += 1
            continue
        if depth != 8 or interlace != 0 or color not in (0, 2, 4, 6):
            print(f"  ✗ {source.name}：{path.relative_to(source)} ⇒ 贴图桥转不了"
                  f"（位深={depth} 色彩类型={color} 隔行={interlace}）⇒ 真机上这张图**空白**")
            unacceptable += 1
    if unacceptable:
        print("  ⇒ 先用美术工具另存成 8 位非隔行 PNG（或让它自带同名 `.pcx`）；"
              "确实要带伤发布就加 --allow-asset-problems")
    return unacceptable


def build(args: argparse.Namespace) -> int:
    output = Path(args.output) if args.output else Path("dist") / args.name
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)

    # 1) 运行时
    runtime = Path(args.runtime)
    exefs = output / EXEFS_RELATIVE
    exefs.mkdir(parents=True, exist_ok=True)
    for name in RUNTIME_FILES:
        source = runtime / EXEFS_RELATIVE / name
        if not source.is_file():
            print(f"缺少运行时文件：{source}", file=sys.stderr)
            return 2
        shutil.copy2(source, exefs / name)
        print(f"运行时  {name:12s} {source.stat().st_size:>9d} 字节  {sha256(source)[:16]}…")

    # 1b) **必需**的中继补丁（默认带；`--no-relay-patches` 只给"故意要一份不含补丁的包"用）
    if args.relay_patches:
        for name in REQUIRED_RELAY_PATCHES:
            patch_dir = runtime / "atmosphere/nro_patches" / name
            if not patch_dir.is_dir():
                print(f"缺少必需的中继补丁目录：{patch_dir}", file=sys.stderr)
                print("  （先构建一次运行时；补丁是构建产物，见 runtime/.gdbsym-artifacts/deploy/…）",
                      file=sys.stderr)
                return 2
            target_dir = output / "atmosphere/nro_patches" / name
            target_dir.mkdir(parents=True, exist_ok=True)
            for item in sorted(patch_dir.iterdir()):
                if item.is_file():
                    shutil.copy2(item, target_dir / item.name)
                    print(f"补丁    {name}/{item.name}  {item.stat().st_size} 字节  "
                          f"{sha256(item)[:16]}…")
    # 2) 模组
    total = 0
    mod_sources: list[Path] = []
    for mod in args.mod:
        source = Path(mod)
        if not source.is_dir():
            print(f"模组目录不存在：{source}", file=sys.stderr)
            return 2
        target = output / MODS_RELATIVE / source.name
        count = copy_tree(source, target, drop_pcx=args.drop_mod_pcx)
        total += count
        mod_sources.append(source)
        # ★ 不管有没有丢 `.pcx`，都要体检"PNG 转不转得了"（2026-09-21）：
        # 丢了 `.pcx` 之后贴图全走运行时转码，"转不了"就等于"这张图空白、还不报错"。
        unconvertible = check_png_convertibility(source)
        if unconvertible and not args.allow_asset_problems:
            print(f"  ⇒ {source.name} 有 {unconvertible} 张转不了的 PNG，已中止打包（返回码 3）",
                  file=sys.stderr)
            return 3
        if args.drop_mod_pcx:
            dropped = sum(1 for f in source.rglob("*.pcx") if f.is_file())
            print(f"模组    {source.name}：{count} 个文件（★ 按 --drop-mod-pcx 丢掉 {dropped} 个 .pcx，"
                  f"贴图走运行时 PNG→PCX 桥）"
                  + (f"（★ {unconvertible} 张转不了，已按 --allow-asset-problems 放行）"
                     if unconvertible else ""))
            continue
        missing_pcx, _other = check_mod_assets(source)
        if missing_pcx and not args.allow_asset_problems:
            return 3
        print(f"模组    {source.name}：{count} 个文件"
              + ("" if not missing_pcx else f"（★ {missing_pcx} 张图缺 .pcx，已按 --allow-asset-problems 放行）"))

    # 2.5) 模组清单（必须有，理由见模块 docstring）
    write_manifest(output, mod_sources)

    # 3) 安装说明（可选；不传就提醒，别让包"悄悄没有说明书"）
    if args.instructions:
        instructions = Path(args.instructions)
        if not instructions.is_file():
            print(f"安装说明不存在：{instructions}", file=sys.stderr)
            return 2
        shutil.copy2(instructions, output / "安装说明.md")
        print(f"安装说明  {instructions.name} → 安装说明.md")
    else:
        print("⚠ 没有传 --instructions：包里不会带安装说明（SD 包建议带上）")

    # 3) EID 配置（可选）
    if args.config:
        config_source = Path(args.config)
        config = json.loads(config_source.read_text(encoding="utf-8"))
        if args.refresh_rate is not None:
            config["RefreshRate"] = args.refresh_rate
        config_dir = output / "EID配置"
        config_dir.mkdir(parents=True, exist_ok=True)
        (config_dir / "eid-config.json").write_text(
            json.dumps(config, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"EID 配置  {len(config)} 个键；RefreshRate={config.get('RefreshRate')} "
              f"（写进 EID配置/eid-config.json）")

    # 4) SHA256SUMS
    lines = []
    for item in sorted(output.rglob("*")):
        if item.is_file() and item.name != "SHA256SUMS.txt" and not is_junk(item):
            lines.append(f"{sha256(item)}  {item.relative_to(output).as_posix()}")
    (output / "SHA256SUMS.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"SHA256SUMS.txt：{len(lines)} 条（不含安装说明与它自己）")

    # 5) zip
    if args.zip:
        archive = output.with_suffix(".zip")
        if archive.exists():
            archive.unlink()
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
            for item in sorted(output.rglob("*")):
                if item.is_file():
                    bundle.write(item, Path(output.name) / item.relative_to(output))
        print(f"zip     {archive}（{archive.stat().st_size} 字节）")
    print(f"\n包体：{output}（模组文件合计 {total} 个 + 运行时 {len(RUNTIME_FILES)} 个）")
    return 0


def _ftp(*arguments: str) -> str:
    """调一次 tools/device_ftp.py（一次连接只做一件事的纪律在那边实现）。"""
    result = subprocess.run([sys.executable, "tools/device_ftp.py", *arguments],
                            capture_output=True, text=True, check=False)
    return (result.stdout or "") + (result.stderr or "")


def verify_device(package: Path, sample: list[str], mod_dirs: list[str]) -> int:
    """抽检：点名的文件逐字节比 sha256；模组目录比**顶层文件名单**（少文件会被看出来）。"""
    problems: list[str] = []
    print("抽样比 sha256（包里 vs 卡上）：")
    for name in sample:
        local = package / name
        if not local.is_file():
            problems.append(f"{name}: 包里没有")
            continue
        output = _ftp("sha", "/" + name)
        # `device_ftp.py sha` 的输出是 `<字节数>\t<sha256>\t<路径>` ⇒ 取第二列
        fields = output.strip().split("\t")
        remote_hash = fields[1].strip() if len(fields) >= 2 else ""
        local_hash = sha256(local)
        mark = "✓" if remote_hash == local_hash else "✗"
        if mark == "✗":
            problems.append(f"{name}: sha256 不一致（卡上 {remote_hash[:16]}… / 包里 {local_hash[:16]}…）")
        print(f"  {mark} {name}\n      卡上 {remote_hash[:24]}…  包里 {local_hash[:24]}…")

    print("模组目录顶层文件名单：")
    for mod in mod_dirs:
        remote_dir = f"/atmosphere/contents/{CONTENT_ID}/romfs/isaac_mods/mods/{mod}"
        listing = _ftp("ls", remote_dir)
        remote_names = set()
        for line in listing.splitlines():
            parts = line.split()
            if len(parts) >= 2 and not line.startswith("["):
                remote_names.add(parts[-1])
        local_dir = package / MODS_RELATIVE / mod
        local_names = {item.name for item in local_dir.iterdir()} if local_dir.is_dir() else set()
        missing = sorted(local_names - remote_names)
        extra = sorted(name for name in remote_names - local_names if not name.startswith("."))
        print(f"  {mod}: 本地 {len(local_names)} 项 / 卡上 {len(remote_names)} 项"
              + (f"；本地有卡上没有：{missing}" if missing else "")
              + (f"；卡上有本地没有：{extra}" if extra else ""))
        if missing or extra:
            problems.append(f"{mod}: 顶层名单不一致")
    print(f"\n抽检问题 {len(problems)} 个")
    return 1 if problems else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="打可部署的 SD 卡发布包（目录树 + SHA256SUMS + zip）")
    parser.add_argument("--name", default="isaac-switch-release")
    parser.add_argument("--output", default=None, help="输出目录（默认 dist/<name>）")
    parser.add_argument("--runtime", default="runtime/.gdbsym-artifacts/deploy",
                        help="运行时构建产物目录（含 atmosphere/contents/<id>/exefs/）")
    parser.add_argument("--mod", action="append", default=[], help="要打包的模组目录（可多次）")
    parser.add_argument("--instructions", default=None, metavar="FILE",
                        help="安装说明（拷进包根当 安装说明.md；不传则包内没有说明书并会提醒）")
    parser.add_argument("--no-relay-patches", dest="relay_patches", action="store_false",
                        help="**不要**带那份必需的中继补丁（默认带）。只在明确要一份不含补丁的包时用；"
                         "带上它才是能用的包（缺了它 EID 套装进度恒 0/3）")
    parser.add_argument("--drop-mod-pcx", action="store_true",
                        help="丢掉模组里的 .pcx，只留 .png（运行时贴图桥会按需转码；"
                             "同时跳过缺 .pcx 的体检）")
    parser.add_argument("--allow-asset-problems", action="store_true",
                        help="贴图缺 `.pcx` 也照打（默认**拒绝打包**：那种包在真机上贴图静默不显示）")
    parser.add_argument("--config", default=None, help="EID 配置 JSON（放进 EID配置/）")
    parser.add_argument("--refresh-rate", type=int, default=None,
                        help="顺便把配置里的 RefreshRate 改成这个值")
    parser.add_argument("--zip", action="store_true", help="顺便打 zip")
    parser.add_argument("--verify-device", default=None, metavar="PACKAGE",
                        help="只校验：把包里的文件与卡上比大小（需要 FTP）")
    parser.add_argument("--hash-sample", action="append", default=[],
                        help="校验时逐字节比 sha256 的相对路径（可多次）")
    parser.add_argument("--verify-mod", action="append", default=[],
                        help="校验时比顶层文件名单的模组目录名（可多次）")
    args = parser.parse_args()

    if args.verify_device:
        return verify_device(Path(args.verify_device), args.hash_sample, args.verify_mod)
    if not args.mod:
        print("至少要有一个 --mod", file=sys.stderr)
        return 2
    return build(args)


if __name__ == "__main__":
    raise SystemExit(main())
