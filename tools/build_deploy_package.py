#!/usr/bin/env python3
"""把"当前这一版"打成可直接拷进 SD 卡的发布包（目录树 + SHA256SUMS + zip）。

## 为什么要有它

之前的发布包是手工拼的（`dist/isaac-eid-release-20260917/` 那种：`atmosphere/` 树 + `SHA256SUMS.txt` +
`安装说明.md`），每次都得重新"找来源、拷文件、算哈希"，容易漏。这里把流程固定成一条命令。

## 它做什么

1. 按参数把 **运行时**（`subsdk9` + `main.npdm` + **romfs 覆盖层**）与若干 **模组目录** 拷进 `<输出>/atmosphere/...`；
2. 可选：把一个 **EID 配置 JSON** 放进 `<输出>/EID配置/eid-config.json`（附应用方法见安装说明）；
3. 生成 `SHA256SUMS.txt`（`hash  相对路径`，与上一版发布包同格式）；
4. 打成 `<输出>.zip`（zip 里以输出目录名为根，便于直接解压到 SD 卡根）。

命令行默认原样保留模组脚本与配置：先安装完整原模组，再单独覆盖补丁包。
仅显式传 `--apply-mod-patches` 才在整包中合入已核对的历史替换文件。

## ★ 运行时那份 **romfs 覆盖层** 也必须进包（2026-09-23 修正）

构建会往部署树里写 `atmosphere/contents/<id>/romfs/rp_patch/…`（`runtime/Makefile` 的
`mod-row-art` 步骤，22 个文件）。它是**主菜单那一列里「模组」那一行**的来源：
引擎那份菜单动画原本只有 12 层（Switch 版把 PC 本来就有的第 13 层 `Item6` 删了），
把第 13 层补回去之后**引擎才会把那一行画出来**（批次 075 的真机验收形态）。

**缺了它的后果是静默的**：引擎只有 12 层 ⇒ 那一行退回"我们自己画字" ⇒
屏幕上有那一行、但**不是验收过的那张原图**。所以本工具把它当**硬要求**
（缺了直接拒绝打包，而不是打个警告继续）。

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
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from mod_lua_performance_patches import approved_patch as approved_lua_performance_patch

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
#: ★ 2026-09-23（批次 077）：运行时构建产物里还有一份 **romfs 覆盖层**必须进包
#: （`<runtime>/atmosphere/contents/<id>/romfs/`，构建的 `mod-row-art` 步骤写进去的
#: `rp_patch/…`；理由与后果见模块 docstring 那一节）。
#:
#: 它是"合并"语义：模组目录落在同一个 `romfs/` 下的 `isaac_mods/`，两边互不相干，
#: 而且这一步跑在模组那一步**之前**。
RUNTIME_OVERLAY_RELATIVE = Path("atmosphere/contents") / CONTENT_ID / "romfs"
#: **必须**进包的 IPS 补丁（理由见模块 docstring）。名字 = 构建产物
#: `atmosphere/nro_patches/<名字>/` 这个目录名；目录里的 `.ips` 文件名带游戏 build id，原样拷。
# 2026-10-13追加：449预算与本包NSO必须成对；只打运行时而漏预算会复发stage12内存失败。
REQUIRED_RELAY_PATCHES = ("isaac-repentance-lifecycle-relay", "isaac-repentance-static-callbacks", "isaac-repentance-native-heap-budget")
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
    """**不再生成 `isaac_mods/manifest.json`**（2026-10-01 用户指令）。

    ## 为什么可以不要它

    这份清单曾经是运行时**唯一**的加载依据（第一条必须是模组配置菜单，加载顺序写死在里面）。
    后来两步把它降级成了可选项：

    * 2026-09-16：运行时支持"自己扫 `isaac_mods/mods` 下的子目录"（`ModDiscoveryService::Discover`）；
    * 2026-09-21：清单存在时也会把"清单里没列出的目录"追加进来（`AppendUnlisted`）。

    ## 用户裁定（2026-10-01）

    「manifest.json 给删了，**以后也不准再出现**；所有的模组都必须走扫描文件夹查询加载。」

    ⇒ 本函数只打印一行说明，不再写文件。加载顺序改由运行时的扫描排序决定 ——
    ★ 那里已经保证"**模组配置菜单排最前**"（`mod_discovery_service.cpp` 的 `ModPriorityRank`），
    因为 GoodTrip / TheSpecialist 是在加载那一刻靠全局 `ModConfigMenu` 决定要不要注册设置页的。
    """
    print(f"模组目录  {len(sources)} 个（★ 不再生成 manifest.json：按 2026-10-01 指令，"
          f"加载一律走扫描 `isaac_mods/mods` 下的子目录）")
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


def _mod_patch_root() -> Path:
    """Optional, explicitly supplied local data; never part of core source."""
    return Path(os.environ.get("ISAAC_MOD_PATCH_ROOT", ROOT / "runtime/mod-patches"))


def _approved_entry_patch(source: Path) -> Path:
    """只替换逐字核过的DPS旧入口；新作者版本保持原样，不改源目录。"""
    if source.stat().st_size != 6514:
        return source
    if hashlib.sha256(source.read_bytes()).hexdigest() != (
        "01bf6f70012f1c3ec25303a2eb058aae130a4614259cdea33b22c7cad445c3ec"
    ):
        return source
    patch = _mod_patch_root() / "whatsmydps/main.lua"
    if hashlib.sha256(patch.read_bytes()).hexdigest() != (
        "8a2bbc484b89de6b5923b000fa54d9ca381a599d1b33d504da3b8a3af1a5f158"
    ):
        raise ValueError("DPS字体补丁已变化，需要重新审查并更新打包身份")
    return patch


def _approved_rplus_entry_patch(source: Path) -> Path:
    """只为核过的忏悔加入口补齐阅读页手柄确认，不改未知作者版本。"""
    if source.stat().st_size != 369225 or hashlib.sha256(source.read_bytes()).hexdigest() != (
        "c9553b4c90b6292eb65aa53bb0f5136d21934d376df2172a65d2c18ad6128591"
    ):
        return source
    patch = _mod_patch_root() / "repentanceplus/main.lua"
    if hashlib.sha256(patch.read_bytes()).hexdigest() != (
        "ac6e41fd54f9689ab710a72fdb8185e9b31da510758ab4ca99df88e11a7ca98d"
    ):
        raise ValueError("忏悔加阅读页补丁已变化，需要重新审查并更新打包身份")
    return patch


def _approved_dss_patch(source: Path) -> Path:
    """只替换已核作者版本的DSS资源，其它版本保持原样。"""
    if source.stat().st_size != 116028 or hashlib.sha256(source.read_bytes()).hexdigest() != (
        "69d7a3a59a33c1e40f8dbc68e5cf83cec83bd1a8a5035f8cb23de7bf5e8f69d2"
    ):
        return source
    patch = _mod_patch_root() / "repentanceplus/scripts/dssmenucore.lua"
    if hashlib.sha256(patch.read_bytes()).hexdigest() != (
        "47be21f322dd1e63053cf7e58f20cf39e5c7c9389ff212c52f014c315086613b"
    ):
        raise ValueError("DSS裁剪补丁已变化，需要重新审查并更新打包身份")
    return patch


def _approved_stageapi_grid_patch(source: Path) -> Path:
    """保留类型读取修正，并减少私有坑/门列表的临时分配。"""
    if hashlib.sha256(source.read_bytes()).hexdigest() not in {
        "b4d5bf2d661e917bb689e2444d61e2cde64bf754050d91d89707e18efe0ab4c6",
        "6afdd9711dcb00dc6107d49a65fd425e956bf55f789addc9fd30f1dc459c4f97",
    }:
        return source
    patch = _mod_patch_root() / "StageAPI/scripts/stageapi/core/callbacks.lua"
    if hashlib.sha256(patch.read_bytes()).hexdigest() != (
        "a14999454fabe556815cb6012bd5d20ba247d978a1dc178b322baf0980e83fd0"
    ):
        raise ValueError("StageAPI网格补丁已变化，需要重新审查并更新打包身份")
    return patch


def _approved_stageapi_shared_patch(source: Path) -> Path:
    """重新打包时保留已部署的StageAPI首次对象初始化修正。"""
    if source.stat().st_size != 983 or hashlib.sha256(source.read_bytes()).hexdigest() != (
        "df39061cf095dd860dcc15864f87d8fa27343b899d8e227f4e1809c77b148ffb"
    ):
        return source
    patch = _mod_patch_root() / "StageAPI/scripts/stageapi/shared.lua"
    if hashlib.sha256(patch.read_bytes()).hexdigest() != (
        "9b64b5c30980dd6b53c2858483e0bea5bbe9fdcd868b9b016f023e6f1348aba5"
    ):
        raise ValueError("StageAPI初始化补丁已变化，需要重新审查并更新打包身份")
    return patch


def _approved_challenge_goal_patch(source: Path) -> Path:
    """仅修已核ChallengeAPI目标图标定位；未审作者版本不替换。"""
    if source.stat().st_size != 2682 or hashlib.sha256(source.read_bytes()).hexdigest() != (
        "620e1c909b91e6347684cfeb4245ff3edeac4130b44f59fec7f978f3826fee5e"
    ):
        return source
    patch = _mod_patch_root() / "ChallengeAPI/scripts/challengeapi/hud/challenge_goal.lua"
    if hashlib.sha256(patch.read_bytes()).hexdigest() != (
        "8a7357580a27b1a7b58b0256120eb81d75e79afd48fec88cf4eed9fef405c787"
    ):
        raise ValueError("ChallengeAPI目标图标补丁已变化，需要重新审查并更新打包身份")
    return patch


def _approved_eid_config_original(source: Path) -> Path:
    """恢复已知历史手工配置，避免重打旧来源时再次带入27项覆盖。"""
    if hashlib.sha256(source.read_bytes()).hexdigest() != (
        "c13c8b228fc135db024f2e20661f2ed721aa1d933b39fcfa2f9501b17ea66685"
    ):
        return source
    original = _mod_patch_root() / "EID/eid_config.lua"
    if hashlib.sha256(original.read_bytes()).hexdigest() != (
        "14cd00a145ac026f981096e072c845a48c8d35575a30ab4518af10b1d8f749db"
    ):
        raise ValueError("EID作者原版配置已变化，需要重新核对原件")
    return original


def copy_tree(source: Path, target: Path, *, drop_pcx: bool = False,
              apply_patches: bool = False) -> int:
    """拷贝模组树。`drop_pcx=True` 时**跳过** `.pcx`（2026-09-21 起可选）。

    默认原样复制输入脚本和配置；历史补丁只能明确选择并提供本地输入。

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
        copied_source = item
        if apply_patches:
            copied_source = _approved_rplus_entry_patch(_approved_entry_patch(item)) if relative == Path("main.lua") else item
            if relative == Path("scripts/dssmenucore.lua"):
                copied_source = _approved_dss_patch(item)
            elif relative == Path("scripts/stageapi/core/callbacks.lua"):
                copied_source = _approved_stageapi_grid_patch(item)
            elif relative == Path("scripts/stageapi/shared.lua"):
                copied_source = _approved_stageapi_shared_patch(item)
            elif relative == Path("scripts/challengeapi/hud/challenge_goal.lua"):
                copied_source = _approved_challenge_goal_patch(item)
            elif relative == Path("eid_config.lua"):
                copied_source = _approved_eid_config_original(item)
            copied_source = approved_lua_performance_patch(copied_source, relative, _mod_patch_root())
        shutil.copy2(copied_source, destination)
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


def verify_native_heap_budget(runtime: Path) -> None:
    from native_heap_budget_patch import (
        runtime_footprint, BASE_CPU_RESERVE, MAIN_HEAP_OFFSET, MODULE_ID,
        CPU_RESERVE_ALIGNMENT,
    )
    from nro_ips import encode_ips
    try:
        footprint = runtime_footprint((runtime / EXEFS_RELATIVE / "subsdk9").read_bytes())
        patch = (runtime / "atmosphere/nro_patches/isaac-repentance-native-heap-budget" / (MODULE_ID + ".ips")).read_bytes()
    except (OSError, ValueError) as error:
        raise ValueError(f"本包NSO或原生预算不可验证：{error}") from error
    minimum = BASE_CPU_RESERVE + footprint
    reserve = (minimum + CPU_RESERVE_ALIGNMENT - 1) & ~(CPU_RESERVE_ALIGNMENT - 1)
    expected = encode_ips([(MAIN_HEAP_OFFSET, reserve.to_bytes(4, "little"))])
    if patch != expected:
        raise ValueError("原生预算IPS不对应本包NSO的实际映射占用，必须重新构建配套预算")


def verified_compatibility_patch_files(runtime: Path) -> dict[Path, bytes]:
    """Validate compatibility artifacts and keep the exact bytes for copying."""
    from tools.build_patches import EXPECTED_MODULE_ID, GAME_START_LIFECYCLE_RELAY_RECORDS
    from tools.nro_ips import decode_ips
    snapshots = {}
    for name in REQUIRED_RELAY_PATCHES:
        relative = Path('atmosphere/nro_patches') / name
        directory = runtime / relative
        if not directory.is_dir():
            raise ValueError(f'缺少必需的中继补丁目录：{directory}，请重新构建兼容层')
        files = {item.name: item.read_bytes() for item in sorted(directory.iterdir()) if item.is_file()}
        if name == 'isaac-repentance-lifecycle-relay':
            filename = EXPECTED_MODULE_ID.hex().upper() + '.ips'
            try:
                ips = [key for key in files if key.endswith('.ips')]
                if ips != [filename] or decode_ips(files[filename]) != GAME_START_LIFECYCLE_RELAY_RECORDS:
                    raise ValueError('unexpected lifecycle IPS records or module ID')
            except (KeyError, ValueError) as error:
                raise ValueError('生命周期兼容补丁包含旧混合或未知记录，请重新构建兼容层；'
                                 '原游戏优化须通过 --game-patches 单独选择') from error
        snapshots.update({relative / filename: blob for filename, blob in files.items()})
    return snapshots


def build(args: argparse.Namespace) -> int:
    if getattr(args, "apply_mod_patches", False) and not _mod_patch_root().is_dir():
        print("可选模组补丁不属于源码包；请通过 ISAAC_MOD_PATCH_ROOT 提供本地补丁目录。",
              file=sys.stderr)
        return 2
    # Original-game optimizations are independently built inputs. Resolve them
    # only when explicitly selected, before touching an existing output tree.
    game_patch_files = {}
    if getattr(args, "game_patches", None):
        from runtime.game_patches.build import verified_bundle_files
        try:
            game_patch_files = verified_bundle_files(Path(args.game_patches))
        except ValueError as error:
            print(str(error), file=sys.stderr)
            return 2
    runtime = Path(args.runtime)
    compatibility_files = {}
    if args.relay_patches:
        try:
            verify_native_heap_budget(runtime)
            compatibility_files = verified_compatibility_patch_files(runtime)
        except (OSError, ValueError) as error:
            print(str(error), file=sys.stderr)
            return 2
    output = Path(args.output) if args.output else Path("dist") / args.name
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)

    # 1) 运行时
    exefs = output / EXEFS_RELATIVE
    exefs.mkdir(parents=True, exist_ok=True)
    for name in RUNTIME_FILES:
        source = runtime / EXEFS_RELATIVE / name
        if not source.is_file():
            print(f"缺少运行时文件：{source}", file=sys.stderr)
            return 2
        shutil.copy2(source, exefs / name)
        print(f"运行时  {name:12s} {source.stat().st_size:>9d} 字节  {sha256(source)[:16]}…")

    # 1a) 运行时的 **romfs 覆盖层**（主菜单那一行「模组」的来源；理由见模块 docstring）。
    #     缺了它**直接拒绝打包** —— 那一行的降级是静默的（引擎不画 ⇒ 我们自己画字），
    #     打出一个"看起来正常、其实不是验收形态"的包，比打包失败难查得多。
    overlay_source = runtime / RUNTIME_OVERLAY_RELATIVE
    if not overlay_source.is_dir():
        print(f"缺少运行时的 romfs 覆盖层：{overlay_source}", file=sys.stderr)
        print("  （先构建一次运行时；那一层是构建产物，见 runtime/Makefile 的 `mod-row-art` 步骤）",
              file=sys.stderr)
        print("  它是什么：补回 PC 本来就有的第 13 层 `Item6` 的 `gamemenu.anm2` + 各语言的"
              " `mod_row_*.pcx`；缺了它，主菜单那一行会退回我们自己画字（不是验收过的形态）。",
              file=sys.stderr)
        return 2
    overlay_files = copy_tree(overlay_source, output / RUNTIME_OVERLAY_RELATIVE)
    print(f"覆盖层  romfs/rp_patch/  {overlay_files} 个文件（引擎画那一行要用的菜单动画与贴图）")

    # 1b) Copy the same compatibility bytes checked before replacing output.
    for relative, blob in compatibility_files.items():
        target = output / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(blob)
        print(f"兼容补丁  {relative}  {len(blob)} 字节")
    # Original-game patches are not controlled by the compatibility relay flag.
    for relative, blob in game_patch_files.items():
        target = output / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(blob)
        print(f"游戏补丁  {relative}  {len(blob)} 字节")
    # 2) 模组
    total = 0
    mod_sources: list[Path] = []
    for mod in args.mod:
        source = Path(mod)
        if not source.is_dir():
            print(f"模组目录不存在：{source}", file=sys.stderr)
            return 2
        target = output / MODS_RELATIVE / source.name
        count = copy_tree(source, target, drop_pcx=args.drop_mod_pcx,
                          apply_patches=args.apply_mod_patches)
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

    # 2.5) 模组清单：**不再生成**（2026-10-01 用户指令；理由见 `write_manifest` 的 docstring）
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
    parser.add_argument("--apply-mod-patches", action="store_true",
                        help="显式合入已核对的历史模组补丁；默认保留原模组，补丁另行覆盖安装")
    parser.add_argument("--game-patches", default=None, metavar="DIR",
                        help="显式组合独立构建的原游戏优化补丁；不传则只带兼容层补丁")
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
