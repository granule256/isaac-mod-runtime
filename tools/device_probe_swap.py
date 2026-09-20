#!/usr/bin/env python3
"""一条命令完成"真机验收探针的装卸"：撤一个模组 → 装探针 → 读回核对 → 事后恢复原状。

## 为什么要有它

真机验收探针（`dist/*-probe-*/main.lua`）现在已经是本项目的标准做法，但**装卸过程有 7 个手工步骤**
（查游戏在不在跑、把被替换的模组改名移出发现根、建目录、上传、读回哈希、跑部署核对、
用完再逐个反向操作），而且每一步都踩过坑：

* 卡上模组上限 **4**，超限时发现流程返回 `CapacityExceeded` 且**不截断** ⇒ 加第 5 个会让**整批不加载**
  ⇒ **只能替换，不能新增**（2026-09-18 两次都靠这条纪律）；
* 被替换的模组必须移出**发现根**（`isaac_mods/mods`）之外才不会被扫到，所以移到
  `isaac_mods/<name>.disabled`；
* 写卡前要确认游戏没在跑（`device_ftp.py` 会自动查，并在查不出来时明确警告）。

这个脚本把那一串固化成两个子命令，并**总是读回核对 + 跑部署清单核对**。

## 用法

    # 装：撤掉 multimod-probe，装上验收探针
    python3 tools/device_probe_swap.py install \
        --probe dist/low-cost-stub-probe-20260918/main.lua \
        --name low-cost-stub-probe

    # 用完：删掉探针、把被替换的模组移回
    python3 tools/device_probe_swap.py restore \
        --name low-cost-stub-probe --victim multimod-probe

    # 看一眼卡上现在有哪几个模组（含哈希）
    python3 tools/device_probe_swap.py status

FTP 纪律照旧：**一个连接只做一件事、动作之间留 1.5 秒**（这台设备的 FTP 对连续连接敏感）。
"""

from __future__ import annotations

import argparse
import hashlib
import pathlib
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
FTP_TOOL = ROOT / "tools" / "device_ftp.py"
VERIFY_TOOL = ROOT / "tools" / "verify_device_install.py"
TITLE_DIR = "/atmosphere/contents/010021C000B6A000"
MODS_DIR = f"{TITLE_DIR}/romfs/isaac_mods/mods"
DISABLED_DIR = f"{TITLE_DIR}/romfs/isaac_mods"
GAP_SECONDS = 1.5


def ftp(*args: str, check: bool = True) -> str:
    time.sleep(GAP_SECONDS)
    result = subprocess.run([sys.executable, str(FTP_TOOL), *args],
                            cwd=ROOT, text=True, capture_output=True)
    output = (result.stdout + result.stderr).strip()
    if check and result.returncode != 0:
        raise SystemExit(f"FTP 动作失败（{' '.join(args)}）：\n{output}")
    return output


def sha256_of(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_install() -> None:
    print()
    print("== 部署清单核对 ==")
    result = subprocess.run([sys.executable, str(VERIFY_TOOL)], cwd=ROOT, text=True,
                            capture_output=True)
    print((result.stdout + result.stderr).strip())
    if result.returncode != 0:
        raise SystemExit("部署清单核对没过 —— 先处理上面的问题。")


def list_mods() -> None:
    print(ftp("ls", f"{MODS_DIR}/"))


def command_install(args: argparse.Namespace) -> int:
    probe = pathlib.Path(args.probe)
    if not probe.is_file():
        raise SystemExit(f"找不到探针脚本：{probe}")
    digest = sha256_of(probe)

    print("== 1/4 把被替换的模组移出发现根 ==")
    victim = args.victim
    if victim:
        print(ftp("mv", f"{MODS_DIR}/{victim}", f"{DISABLED_DIR}/{victim}.disabled"))
    else:
        print("（--victim 为空：不撤任何模组 —— 前提是卡上模组数 < 4）")

    print("== 2/4 建目录并上传探针 ==")
    ftp("mkdir", f"{MODS_DIR}/{args.name}", check=False)
    print(ftp("put", str(probe), f"{MODS_DIR}/{args.name}/main.lua"))

    print("== 3/4 读回核对 ==")
    reported = ftp("sha", f"{MODS_DIR}/{args.name}/main.lua")
    print(reported)
    if digest[:16] not in reported:
        raise SystemExit(f"读回的哈希与本地不一致！本地 {digest}")

    print("== 4/4 卡上模组一览 ==")
    list_mods()
    verify_install()
    print()
    print("装好了。跑完验收之后用这条恢复：")
    print(f"  python3 tools/device_probe_swap.py restore --name {args.name}"
          + (f" --victim {victim}" if victim else ""))
    return 0


def command_restore(args: argparse.Namespace) -> int:
    print("== 1/4 删掉探针 ==")
    ftp("rm", f"{MODS_DIR}/{args.name}/main.lua", check=False)
    print(ftp("rmdir", f"{MODS_DIR}/{args.name}", check=False))

    print("== 2/4 把被替换的模组移回 ==")
    if args.victim:
        print(ftp("mv", f"{DISABLED_DIR}/{args.victim}.disabled", f"{MODS_DIR}/{args.victim}"))
        reported = ftp("sha", f"{MODS_DIR}/{args.victim}/main.lua")
        print(reported)
        if args.expect_victim_sha and args.expect_victim_sha[:16] not in reported:
            raise SystemExit("被替换的模组读回哈希与预期不一致 —— 别继续，先查。")
    else:
        print("（--victim 为空：没有要移回的模组）")

    print("== 3/4 卡上模组一览 ==")
    list_mods()
    print("== 4/4 ==")
    verify_install()
    print()
    print("卡上已恢复原状。")
    return 0


def command_status(_args: argparse.Namespace) -> int:
    list_mods()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="真机验收探针的装卸（一条命令、带核对）")
    sub = parser.add_subparsers(dest="command", required=True)

    install = sub.add_parser("install", help="撤掉一个模组并装上探针")
    install.add_argument("--probe", required=True, help="工作区里的探针 main.lua 路径")
    install.add_argument("--name", required=True, help="卡上的探针目录名（ASCII）")
    install.add_argument("--victim", default="multimod-probe",
                         help="被替换掉的模组目录名（默认 multimod-probe；传空字符串表示不撤）")
    install.set_defaults(func=command_install)

    restore = sub.add_parser("restore", help="删掉探针并把被替换的模组移回")
    restore.add_argument("--name", required=True, help="卡上的探针目录名")
    restore.add_argument("--victim", default="multimod-probe", help="要移回的模组目录名")
    restore.add_argument("--expect-victim-sha", default=None,
                         help="移回后读回哈希必须包含这个前缀（例如 988309330026acde）")
    restore.set_defaults(func=command_restore)

    status = sub.add_parser("status", help="列卡上模组")
    status.set_defaults(func=command_status)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
