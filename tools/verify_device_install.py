#!/usr/bin/env python3
"""核对卡上的安装状态与本地部署包是否一致（部署清单）。

## 为什么需要它（2026-09-17 血的教训）

EID 的套装进度恒 `(0/3)`，我们查了很多轮**代码**（运行时的 `GetCollectibleNum`、EID 的
`evaluateTransformationProgress`…），真凶却是**卡上一个被改名的文件**：
`atmosphere/nro_patches/isaac-repentance-lifecycle-relay/…ips` 被改名成 **`.ips.disabled`**
—— Atmosphere 只认 `.ips`，加了后缀就**静默跳过** ⇒ 游戏开局事件的中继永远不套用 ⇒
运行时的开局挂点收不到事件 ⇒ EID 那张套装查找表永远建不起来 ⇒ 进度恒 0。

而文档只记了"改名 `.ips.disabled`"，**没写"这等于关掉开局事件"**，所以没人把它和症状联系起来。
⇒ 把"卡上应有的东西"变成一份**可自动核对的清单**：存在性、哈希、以及**有没有被改名成 `.disabled`**。

## 它查什么

1. **exefs**：`subsdk9` / `main.npdm` 的哈希必须与本地部署包一致（版本漂移 / 没同步）；
2. **nro_patches**（★ 这次的漏洞就在这儿）：本地部署包里每个补丁，卡上必须**同名存在、哈希一致**，
   而且**不允许**出现 `<同名>.disabled`（那是"被静默禁用"的形态）；
3. **多出来的东西**：卡上任何 `*.disabled`（文件或目录）都列出来 —— 它们是**被人为关掉的功能**；
4. **romfs 模组目录**：卡上的模组目录清单（上限 4 个，超了会整批拒绝加载）。

## 用法

    python3 tools/verify_device_install.py                     # 用 tools/device.local.json 里的设备
    python3 tools/verify_device_install.py --deploy runtime/.gdbsym-artifacts/deploy

FTP 纪律照旧：**每读一项新建一次连接、动作之间间隔 1.5 秒**（这台设备的 FTP 对连续连接敏感）。
"""

from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
FTP_TOOL = ROOT / "tools" / "device_ftp.py"
DEFAULT_DEPLOY = ROOT / "runtime" / ".gdbsym-artifacts" / "deploy"
TITLE_DIR = "/atmosphere/contents/010021C000B6A000"
GAP_SECONDS = 1.5

#: ★ 挂点至今**仍走 IPS 那条路**的补丁：卡上缺了 ⇒ 对应功能静默失效。
#: `lifecycle-relay` 就是 2026-09-17 那次的真凶（缺了它 ⇒ 游戏开局事件永远不来 ⇒
#: EID 的套装查找表建不起来 ⇒ 套装进度恒 `(0/3)`）。
REQUIRED_PATCHES = {
    "isaac-repentance-lifecycle-relay",
}

#: **旧 IPS 后端**的遗留：挂点已迁到"运行时自己改内存"那条路，卡上**不该有**这些补丁。
#: 依据（`runtime/source/hook_manager.cpp`）：
#:   * `:2200` 「旧 IPS 后端：游戏映像里必须有那段中继…… 若这时仍按旧前提验，删掉那份 IPS
#:     之后这里会直接判失败」；
#:   * `:4279` 守卫原文「调用点必须已回到**原样**（**即那份 IPS 已删**）」——
#:     也就是说**删掉它们才是新形态的期望状态**。
#: 本地构建仍在产出这些文件（旧后端代码还留着，可回退），所以"卡上缺"是正常的；
#: 反过来，**卡上如果还有它们**，说明卡停留在旧形态 ⇒ 值得提示。
LEGACY_PATCHES = {
    "isaac-repentance-manager-render-relay",
    "isaac-repentance-manager-update-relay",
    "isaac-repentance-pre-get-collectible-relay",
    "isaac-repentance-rebuild-mount-points-relay",
    "isaac-repentance-render-present-relay",
}

#: 卡上这些 `.disabled` 是**故意**的（退役/备份），不算问题。
KNOWN_DISABLED_OK = {
    "/atmosphere/contents/0000000000534C56.disabled",  # SaltyNX sysmodule，2026-09-14 用户裁定退役
    "exefs/subsdk9.disabled",                          # 旧 subsdk9 备份
}


def ftp(*arguments: str) -> tuple[int, str]:
    """调一次 `device_ftp.py`（每次调用都是**新连接**，符合项目纪律）。"""
    result = subprocess.run([sys.executable, str(FTP_TOOL), *arguments],
                            capture_output=True, text=True, cwd=ROOT)
    time.sleep(GAP_SECONDS)
    return result.returncode, (result.stdout + result.stderr).strip()


def ls(remote: str) -> list[str]:
    code, output = ftp("ls", remote)
    if code != 0:
        return []
    names: list[str] = []
    for line in output.splitlines():
        parts = line.split(maxsplit=8)
        if len(parts) == 9:
            names.append(parts[8])
    return names


def sha(remote: str) -> str | None:
    code, output = ftp("sha", remote)
    if code != 0:
        return None
    parts = output.split()
    return parts[1] if len(parts) >= 2 else None


def local_files(directory: pathlib.Path) -> dict[str, str]:
    import hashlib
    out: dict[str, str] = {}
    for path in sorted(directory.rglob("*")):
        if path.is_file():
            out[str(path.relative_to(directory))] = hashlib.sha256(path.read_bytes()).hexdigest()
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="核对卡上安装状态 vs 本地部署包")
    parser.add_argument("--deploy", default=str(DEFAULT_DEPLOY))
    args = parser.parse_args()
    deploy = pathlib.Path(args.deploy)
    if not deploy.is_dir():
        print(f"找不到本地部署包：{deploy}", file=sys.stderr)
        return 2

    problems: list[str] = []
    notes: list[str] = []

    # ---- ① exefs ----
    print("== exefs ==")
    exefs_local = deploy / "atmosphere" / "contents" / "010021C000B6A000" / "exefs"
    for path in sorted(exefs_local.glob("*")):
        remote = f"{TITLE_DIR}/exefs/{path.name}"
        actual = sha(remote)
        import hashlib
        expected = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual is None:
            problems.append(f"exefs/{path.name}：卡上读不到（缺失？）")
            print(f"  ✗ {path.name}：卡上读不到")
        elif actual != expected:
            problems.append(f"exefs/{path.name}：哈希不符（卡上 {actual[:16]}… / 本地 {expected[:16]}…）")
            print(f"  ✗ {path.name}：哈希不符（版本漂移？）")
        else:
            print(f"  ✓ {path.name}")

    # ---- ② nro_patches：本次漏洞的形态 ----
    print("\n== nro_patches（★ 补丁被静默禁用的形态就在这里）==")
    patches_local = deploy / "atmosphere" / "nro_patches"
    for directory in sorted(patches_local.iterdir()):
        if not directory.is_dir():
            continue
        remote_dir = f"/atmosphere/nro_patches/{directory.name}"
        remote_names = ls(remote_dir)
        local_names = sorted(p.name for p in directory.iterdir() if p.is_file())
        if not local_names:
            continue
        legacy = directory.name in LEGACY_PATCHES
        required = directory.name in REQUIRED_PATCHES
        if not required and not legacy:
            print(f"  ？ {directory.name}：既不在必需清单、也不在遗留清单里（新补丁？请核对后登记）")
        for name in local_names:
            if name in remote_names:
                actual = sha(f"{remote_dir}/{name}")
                import hashlib
                expected = hashlib.sha256((directory / name).read_bytes()).hexdigest()
                if actual == expected:
                    print(f"  ✓ {directory.name}/{name}")
                else:
                    problems.append(f"{directory.name}/{name}：哈希不符 ⇒ 补丁与当前构建不匹配")
                    print(f"  ✗ {directory.name}/{name}：哈希不符（补丁与当前构建不匹配）")
            elif f"{name}.disabled" in remote_names:
                problems.append(
                    f"{directory.name}/{name}：**被改名成 .disabled ⇒ Atmosphere 会静默跳过**"
                    f"（这个补丁负责的功能现在全都不工作）")
                print(f"  ✗✗ {directory.name}/{name}：被改名成 `.disabled` ⇒ 该补丁负责的功能全部失效")
            elif legacy:
                print(f"  · {directory.name}/{name}：卡上按新形态**不需要**（旧 IPS 后端遗留）")
            else:
                problems.append(f"{directory.name}/{name}：卡上没有（补丁缺失）")
                print(f"  ✗ {directory.name}/{name}：卡上没有")

        # 旧后端的补丁**不该**留在卡上：留着说明卡停留旧形态。
        for name in remote_names:
            if name in local_names and legacy:
                notes.append(f"{directory.name}/{name}：旧 IPS 后端的补丁仍在卡上（新形态期望删掉它）")
                print(f"  ⚠ {directory.name}/{name}：旧后端的补丁仍在卡上")

    # ---- ③ 卡上被禁用的东西 ----
    print("\n== 卡上被禁用（.disabled）的东西 ==")
    for root in ("/atmosphere/nro_patches", "/atmosphere/contents"):
        for name in ls(root):
            if name.endswith(".disabled"):
                key = f"{root}/{name}"
                if key in KNOWN_DISABLED_OK:
                    print(f"  · {key}（已知故意退役/备份）")
                    continue
                notes.append(f"{key}：**被禁用**（改名 .disabled）—— 需要确认它关掉了什么功能")
                print(f"  ⚠ {key}")
    for name in ls("/atmosphere/contents/010021C000B6A000/exefs"):
        if name.endswith(".disabled"):
            key = f"exefs/{name}"
            if key in KNOWN_DISABLED_OK:
                print(f"  · {key}（已知故意备份）")
                continue
            notes.append(f"{key}：**被禁用**")
            print(f"  ⚠ {key}")
    if not notes:
        print("  （没有）")

    # ---- ④ 模组目录 ----
    print("\n== romfs 模组目录 ==")
    mods = ls(f"{TITLE_DIR}/romfs/isaac_mods/mods")
    print(f"  {len(mods)} 个：{'、'.join(mods) if mods else '（读不到）'}")
    if len(mods) > 4:
        problems.append(f"模组目录 {len(mods)} 个 > 上限 4 ⇒ 运行时会整批拒绝加载")

    # ---- 汇总 ----
    print("\n== 汇总 ==")
    for problem in problems:
        print(f"  ✗ {problem}")
    for note in notes:
        print(f"  ⚠ {note}")
    if not problems:
        print("  ✓ 没有发现缺失/改名/哈希不符")
    print(f"\n（读了 {len(notes)} 处禁用项、{len(problems)} 个问题）")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
