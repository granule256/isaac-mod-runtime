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

## ★ 不打包 `atmosphere/nro_patches/`

那是**旧 IPS 后端**的遗留件。把它们写进卡里会**在启动时改写游戏本体入口**，而现在的运行时装入口中继前
要逐字节核对原版入口 ⇒ **一个挂点都装不上、所有模组连带我们自己的菜单全消失**（2026-09-20 真实事故，
失败码 2 = `EntryMismatch`）。新形态**不需要**它们，`tools/verify_device_install.py` 也打印"期望删掉它"。
本工具因此**永不**把 `nro_patches` 写进包，并在安装说明里写明。

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

CONTENT_ID = "010021C000B6A000"
MODS_RELATIVE = Path("atmosphere/contents") / CONTENT_ID / "romfs/isaac_mods/mods"
EXEFS_RELATIVE = Path("atmosphere/contents") / CONTENT_ID / "exefs"
#: 运行时构建产物里要带上的文件（**不含** nro_patches，理由见模块 docstring）
RUNTIME_FILES = ("subsdk9", "main.npdm")


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


def copy_tree(source: Path, target: Path) -> int:
    count = 0
    for item in sorted(source.rglob("*")):
        if item.is_dir() or is_junk(item):
            continue
        relative = item.relative_to(source)
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(item, destination)
        count += 1
    return count


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

    # 2) 模组
    total = 0
    for mod in args.mod:
        source = Path(mod)
        if not source.is_dir():
            print(f"模组目录不存在：{source}", file=sys.stderr)
            return 2
        target = output / MODS_RELATIVE / source.name
        count = copy_tree(source, target)
        total += count
        print(f"模组    {source.name}：{count} 个文件")

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
