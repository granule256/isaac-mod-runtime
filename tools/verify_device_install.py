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
4. **romfs 模组目录**：卡上的模组目录清单（上限从运行时源码的常量读，**不写死**——
   它变过三次：4 → 16 → 32；写死 4 时卡上 6 个目录会被误报成"整批拒绝加载"）；
5. **romfs 资源覆盖层**（★ 2026-09-23 批次 071 新增）：本地部署包里只要存在
   `atmosphere/contents/010021C000B6A000/romfs/`，就把那棵子树下的**每个文件**在卡上按同路径
   读回、比对**字节数与 sha256**，缺失或不一致一律报错并列出。

   为什么必须补这一条（一句话）：主菜单那一行的「模组」美术**改成了引擎按磁盘路径加载**
   （`ANM2::Load`，见 `tools/emit_mod_row_art.py`）—— 资源文件没传上去的症状是
   "**不报错、那一行就是不见了**"，而 `ls` 看不出这种静默缺失。这条就是那类事故的拦截器
   （与"补丁被改名成 `.disabled` 静默跳过"是同一类：部署核对必须**逐字节**，不能靠肉眼看目录）。

## 用法

    python3 tools/verify_device_install.py                     # 用 tools/device.local.json 里的设备
    python3 tools/verify_device_install.py --deploy runtime/.gdbsym-artifacts/deploy

FTP 纪律照旧：**每读一项新建一次连接、动作之间间隔 1.5 秒**（这台设备的 FTP 对连续连接敏感）。
romfs 那一节是**逐个文件**读回核对的，所以文件多时会慢（每个文件一个连接 + 1.5 秒间隔）。
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

#: 模组数量上限的**唯一真值源**：运行时源码里的常量（`static_assert` 把它和多选表钉一致）。
#: 这个数字变过三次（4 → 16 → 32），所以任何写死它的地方都会变成"过期判据"。
CAPACITY_SOURCES = (
    ROOT / "runtime" / "src" / "domain" / "mod" / "mod_manifest.hpp",
    ROOT / "runtime" / "source" / "mod_manifest.hpp",
)


def _mod_capacity_from_source() -> int | None:
    """从源码里读 `kModManifestCapacity`/`kMaximumSelectedMods`（读不到返回 None ⇒ 不下结论）。"""
    import re

    pattern = re.compile(r"k(?:ModManifestCapacity|MaximumSelectedMods)\s*=\s*(\d+)")
    for path in CAPACITY_SOURCES:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        match = pattern.search(text)
        if match:
            return int(match.group(1))
    return None

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
    """调一次 `device_ftp.py`。

    ★★ **更正（2026-10-06）**：这里原来写着"每次调用都是**新连接**，符合项目纪律"，
    并在每次调用后 `time.sleep(GAP_SECONDS)` 睡 1.5 秒。那条"纪律"（"动作之间留 1~3 秒"）
    当天被用户当场纠正、并被实测推翻：**设备侧没有这个限制，慢的只是"我们反复新建连接 + 睡"**
    —— `put-tree` 改成"一条连接连续传"之后，42 个文件从 **3 分 26 秒**降到 **3.2 秒**。
    ⇒ 这个 1.5 秒的间隔**去掉了**（本脚本核 22 个文件时，那 33 秒全是纯等待）。
    ★ 但"**不要并发**"这条仍然要守（并发确实会让服务端 reset）—— 本脚本本来就是串行的。
    """
    result = subprocess.run([sys.executable, str(FTP_TOOL), *arguments],
                            capture_output=True, text=True, cwd=ROOT)
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


def sha_and_size(remote: str) -> tuple[int | None, str | None]:
    """一次连接同时拿到"卡上那个文件的字节数与 sha256"（`sha` 子命令的打印格式就是三列）。

    为什么要字节数：**只比哈希会漏掉"本地是空文件"** 这类情况，而"字节数对不上"
    在报告里比一串十六进制好读得多（本项目要求报错要能一眼看出差在哪）。
    """
    code, output = ftp("sha", remote)
    if code != 0:
        return None, None
    parts = output.split()
    if len(parts) < 3:
        return None, None
    try:
        size = int(parts[0])
    except ValueError:
        return None, None
    return size, parts[1]


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
    # ★ 2026-09-21：上限**不能再写死**。它由运行时源码里的常量决定，且跟着批次变过三次
    # （4 → 16 → 32）；写死 4 时，卡上 6 个目录会被误报成"整批拒绝加载"（当时真就被这条唬了一下）。
    # 判据改成"从源码读常量"：读不到就**不报**，而不是拿一个可能过期的数字下结论。
    capacity = _mod_capacity_from_source()
    if capacity is not None and len(mods) > capacity:
        problems.append(f"模组目录 {len(mods)} 个 > 上限 {capacity}（`kModManifestCapacity`）⇒ 运行时会整批拒绝加载")
    elif capacity is None:
        print("  （上限判不了：源码里的 `kModManifestCapacity` 没读到 ⇒ 不拿旧数字下结论）")

    # ---- ⑤ romfs 资源覆盖层：逐文件读回核对（★ 批次 071 新增）----
    #
    # 为什么逐文件：这一棵子树里放的是**运行期真的会被引擎按路径打开**的资源
    # （例如『模组』那一行的 `mod_row_<语言>.anm2` + 同名 `.pcx`）。少一个或内容不同，
    # 症状是"不报错、画面上少一块"—— 肉眼翻目录看不出这种静默缺失，只有逐字节核对能拦住。
    romfs_local = deploy / "atmosphere" / "contents" / "010021C000B6A000" / "romfs"
    if romfs_local.is_dir():
        files = local_files(romfs_local)
        print(f"\n== romfs 资源覆盖层（本地 {len(files)} 个文件，逐个读回核对）==")
        missing = 0
        mismatched = 0
        for relative, expected in sorted(files.items()):
            local_path = romfs_local / relative
            remote = f"{TITLE_DIR}/romfs/{relative}"
            expected_size = local_path.stat().st_size
            actual_size, actual = sha_and_size(remote)
            if actual is None:
                missing += 1
                problems.append(f"romfs/{relative}：卡上读不到（缺失？资源没传上去？）")
                print(f"  ✗ romfs/{relative}：卡上读不到")
            elif actual != expected or actual_size != expected_size:
                mismatched += 1
                problems.append(
                    f"romfs/{relative}：内容不一致"
                    f"（卡上 {actual_size} 字节 / {actual[:16]}…，"
                    f"本地 {expected_size} 字节 / {expected[:16]}…）")
                print(f"  ✗ romfs/{relative}：内容不一致（卡上 {actual_size} 字节、"
                      f"本地 {expected_size} 字节）")
            else:
                print(f"  ✓ romfs/{relative}（{expected_size} 字节）")
        if not files:
            print("  （本地这棵子树是空的 ⇒ 没什么可核对）")
        elif not missing and not mismatched:
            print(f"  ⇒ {len(files)} 个文件全部逐字节一致")

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
