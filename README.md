# isaac-mod-runtime

[![ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/P8P729Q77R)

[简体中文](#中文) | [English](#english)

<a id="中文"></a>

面向 NX 版《以撒的结合：忏悔》的 PC Lua 模组兼容层，提供模组菜单、游戏 API、回调、资源加载与配置持久化，尽可能保留原模组的调用方式和行为。

当前正式版为 **v1.0.0**，目标游戏版本为 **1.7.9b** 的指定构建。兼容层免费，赞赏自愿且不影响使用。为防止倒卖，公告部分的代码未开源。

## 功能

- 适配 `Isaac`、`Game`、`Level`、`Room`、实体、道具配置、输入和音频等接口。
- 支持精灵、字体、图层、自定义着色器适配及多语言标题说明。
- 提供模组自动发现、游戏内开关和配置持久化。
- 完整安装包包含核心、配套资源及兼容层自身全部补丁，无需单独安装补丁。

| 补丁目录（`atmosphere/nro_patches/` 下） | 用途 |
| --- | --- |
| `isaac-repentance-lifecycle-relay/` | 运行时生命周期转接 |
| `isaac-repentance-static-callbacks/` | 原生回调挂接 |
| `isaac-repentance-native-heap-budget/` | 与核心配套的内存预算 |
| `isaac-repentance-loop-time-carry/` | 修复卡顿补偿后的持续逻辑超速 |

时序修复不代表所有场景的绘制帧率提升。作者模组的覆盖补丁归对应模组。

## 下载与安装

下载 [isaac-runtime-v1.0.0.zip](https://github.com/granule256/isaac-mod-runtime/releases/download/v1.0.0/isaac-runtime-v1.0.0.zip)。包内附英文 `INSTALL.txt`，不包含游戏、Atmosphère 或第三方模组。版本更新记录见 [Releases](https://github.com/granule256/isaac-mod-runtime/releases)。

1. 准备已配置大气层的设备和受支持的游戏构建，备份存档并完全关闭游戏。
2. 解压安装包，将整个 `atmosphere/` 文件夹复制到 SD 卡根目录，合并目录并覆盖同名文件。核心、资源和补丁一起安装，避免混用版本。
3. 启动游戏，确认兼容层说明显示 `v1.0.0`。
4. 将每个模组的完整文件夹单独放入以下目录，避免多套一层文件夹：

   ```text
   SD:/atmosphere/contents/010021C000B6A000/romfs/isaac_mods/mods/
   ```

   安装或更换模组前先完全关闭游戏，再重新启动并通过游戏内模组菜单管理开关。

包内 `atmosphere/contents/010021C000B6A000/exefs/isaac_runtime_sha256.md` 记录核心 `subsdk9` 的版本、构建号、大小与 SHA-256，可用于核对安装文件。

## 游戏内说明

左右方向、摇杆或 L/R 翻页。首次启动或版本更新后，读完全部页面，再长按 B 关闭；同版本后续启动默认收起。在标题画面右下角选择“兼容层说明”并按 A 可重新打开，手动打开后可在任意页点按 B 关闭。

## 兼容性与已知问题

已有部分功能验证记录的模组包括 EID、Mod Config Menu、MinimapAPI、StageAPI、GoodTrip、Planetarium Chance、MusicModCallback、TimeMachine 和 Watch out, laser!，不代表其全部功能、版本或组合均已通过。

- 物品原地变形后，小地图图标可能未及时刷新。
- 部分 API 行为、回调时机、自定义角色和多模组组合仍需进一步验证。
- 重负载场景可能出现长帧，不保证所有场景稳定满帧。

加载成功或零报错不代表模组完整兼容。反馈问题时请提供发行版本、模组版本、触发步骤、预期与实际行为，以及清除私人信息后的日志。

## 源码与构建

| 路径 | 内容 |
| --- | --- |
| [`runtime/`](runtime/) | 运行时实现与相关测试 |
| [`runtime/game_patches/`](runtime/game_patches/) | 兼容层补丁生成与校验 |
| [`tools/`](tools/) | 构建、打包和验证工具 |
| [`tests/`](tests/) | 工具及跨模块测试 |

构建需要 Python、Docker、相应 C++ 交叉工具链及自行准备的受支持游戏原件输入。参数与构建目标见 [`runtime/Makefile`](runtime/Makefile)。完整运行时还需要与源码和公告资源匹配的 `NOTICE_GUARD_ARCHIVE`；该模块的内部实现未包含在本仓库中。Lua 宿主集成测试需要匹配宿主平台的 `NOTICE_GUARD_HOST_ARCHIVE`。

## 许可与致谢

本仓库公开源码按 [GPL-2.0](LICENSE) 发布。原创部分版权署名为 **Copyright (C) 2026 granule256**；第三方文件保留原始版权和许可证。

本项目使用或参考了 [Atmosphère](https://github.com/Atmosphere-NX/Atmosphere)、libnx（ISC）、[exlaunch](https://github.com/shadowninja108/exlaunch) 和 [Lua 5.3.3](https://www.lua.org/)。各组件的许可范围以其源码声明为准。

本项目为非官方社区项目，与游戏开发商、发行商及模组作者无隶属关系。

## 联系

QQ群：**1124953430** · [Discord](https://discord.gg/JMQc2jMsve)。也可通过 ToMod 的以撒页面及 GBAtemp 发布帖获取下载信息。

---

<a id="english"></a>

# isaac-mod-runtime — English

[简体中文](#中文) | [English](#english)

A community compatibility layer for running PC Lua mods in **The Binding of Isaac: Repentance on NX**. It provides a mod menu, game APIs, callbacks, resource loading and configuration persistence while aiming to preserve original mod calls and behavior.

The current stable version is **v1.0.0**, targeting the supported **1.7.9b** game build. The layer is free; donations are optional and do not affect access. To prevent resale, the notice-related code is not open source.

## Features

- Adaptations for `Isaac`, `Game`, `Level`, `Room`, entities, item configuration, input and audio.
- Support for sprites, fonts, layers, custom shader adaptations and multilingual title notices.
- Automatic mod discovery, in-game mod toggles and configuration persistence.
- One complete installation containing the core, supporting resources and all compatibility-layer patches.

| Patch directory under `atmosphere/nro_patches/` | Purpose |
| --- | --- |
| `isaac-repentance-lifecycle-relay/` | Runtime lifecycle relay |
| `isaac-repentance-static-callbacks/` | Native callback hooks |
| `isaac-repentance-native-heap-budget/` | Memory budget paired with the core |
| `isaac-repentance-loop-time-carry/` | Fix sustained simulation speedup after catch-up updates |

The timing fix does not imply a general rendering frame-rate improvement. Patches to third-party mods belong to those mods.

## Download and install

Download [isaac-runtime-v1.0.0.zip](https://github.com/granule256/isaac-mod-runtime/releases/download/v1.0.0/isaac-runtime-v1.0.0.zip). It includes an English `INSTALL.txt`; the game, Atmosphère and third-party mods are not bundled. See [Releases](https://github.com/granule256/isaac-mod-runtime/releases) for version changes.

1. Use an NX device configured for Atmosphère and the supported game build. Back up your saves and fully close the game.
2. Extract the package and copy its entire `atmosphere/` folder to the SD card root. Merge folders and overwrite matching files. Install the core, resources and patches together and avoid mixing versions.
3. Launch the game and check that the compatibility-layer notice displays `v1.0.0`.
4. Place each complete mod folder in the following directory without an extra nested folder:

   ```text
   SD:/atmosphere/contents/010021C000B6A000/romfs/isaac_mods/mods/
   ```

   Fully close the game before installing or changing mods, then restart it and manage mod toggles from the in-game menu.

The package includes `atmosphere/contents/010021C000B6A000/exefs/isaac_runtime_sha256.md`, recording the version, build, size and SHA-256 of `subsdk9` for file verification.

## In-game notice

Use left/right, the stick or L/R to turn pages. On first launch or after an update, read every page and hold B to close it. Later launches of the same version leave it closed by default. Select the notice entry at the bottom right of the title screen and press A to reopen it; when opened manually, press B on any page to close it.

## Compatibility and known issues

Partial validation records exist for EID, Mod Config Menu, MinimapAPI, StageAPI, GoodTrip, Planetarium Chance, MusicModCallback, TimeMachine and Watch out, laser! These records do not certify every feature, version or combination.

- An item transforming in place can leave a stale minimap icon.
- Some API behavior, callback timing, custom characters and mod combinations need further testing.
- Heavy workloads may produce long frames; stable full frame rate is not guaranteed in every scene.

Successful loading or zero logged errors does not prove full compatibility. For bug reports, include the release version, mod version, reproduction steps, expected and actual behavior, and logs with private information removed.

## Source and building

| Path | Contents |
| --- | --- |
| [`runtime/`](runtime/) | Runtime implementation and related tests |
| [`runtime/game_patches/`](runtime/game_patches/) | Compatibility-layer patch generation and verification |
| [`tools/`](tools/) | Build, packaging and verification tools |
| [`tests/`](tests/) | Tool and cross-module tests |

Building requires Python, Docker, the C++ cross toolchain and your own supported original game inputs. See [`runtime/Makefile`](runtime/Makefile) for arguments and targets. A complete runtime build also requires a `NOTICE_GUARD_ARCHIVE` matching the source and notice resources; its internal implementation is not included in this repository. Host Lua integration tests require a matching `NOTICE_GUARD_HOST_ARCHIVE` for the host platform.

## License and credits

The source code published in this repository is licensed under [GPL-2.0](LICENSE). Original code is **Copyright (C) 2026 granule256**. Third-party files retain their own copyrights and licenses.

The project uses or references [Atmosphère](https://github.com/Atmosphere-NX/Atmosphere), libnx (ISC), [exlaunch](https://github.com/shadowninja108/exlaunch) and [Lua 5.3.3](https://www.lua.org/). Each component's source notices define its license scope.

This is an unofficial community project, unaffiliated with the game developers, publishers or mod authors.

## Contact

QQ group: **1124953430** · [Discord](https://discord.gg/JMQc2jMsve). Downloads are also available through the Isaac page on ToMod and the GBAtemp release thread.
