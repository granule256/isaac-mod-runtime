# isaac-mod-runtime

[简体中文](#中文) | [English](#english)

<a id="中文"></a>

面向《以撒的结合：忏悔》PC Lua 模组的社区兼容运行时，适配游戏 API、回调和资源加载，目标是尽可能保持原模组的调用方式与行为。

兼容层统一包含运行时、配套资源以及自身全部修复、性能和时序补丁，统一版本、构建、验证、打包和安装。

> 当前正式版为 v1.0.0。加载成功或零报错不代表模组完整兼容；安装前请备份存档，并核对目标游戏构建。

## 当前进展

当前正式版为 `v1.0.0`，由 `v1.0.0-rc.4` 转正，包含说明界面、完整性检查及已纳入的兼容层补丁。《忏悔》模组运行能力已基本补齐，后续重点是发现和修复可能存在的行为、回调时机及组合兼容问题。可下载版本以仓库的 Releases 页面为准，源码进展不等于所有安装包已经更新。

| 方向 | 当前能力与边界 |
| --- | --- |
| 模组运行 | 提供 Lua API、回调派发、资源加载和配置持久化；不同模组的覆盖范围分别验证 |
| 界面与资源 | 支持精灵、字体、图层及自定义着色器适配，包含多语言标题说明和资源完整性检查 |
| 近期修复 | 修正商店敌人计数导致的说明误隐藏，补充手动实体更新后的回调，支持更大的入口脚本，并修复生成道具贴图的像素读取 |
| 兼容层时序修复 | 修正卡顿后时间累计丢失导致的持续逻辑超速；随完整兼容层统一安装 |
| 性能状态 | 部分负载仍有长帧；内存分配、回收与渲染同步继续调查，不承诺所有场景稳定满帧 |

修复按接口和场景验收。自定义角色、密集特效、复杂地图及多模组组合仍需更多验证。

## 下载与安装

当前正式版：[v1.0.0](https://github.com/granule256/isaac-mod-runtime/releases/tag/v1.0.0)。安装包随该 Release 发布，源码提交不代表安装包已经更新。

| 安装包 | 安装说明语言 |
| --- | --- |
| `isaac-runtime-v1.0.0-zh-CN.zip` | 简体中文 |
| `isaac-runtime-v1.0.0-en.zip` | English |

两包的完整兼容层及全部自身补丁一致，只在根目录 `INSTALL.txt` 的语言上有区别，不附带游戏、Atmosphère 或第三方模组。

1. 准备已配置 Atmosphère 的 Switch 和受支持的《忏悔》`1.7.9b`，备份存档并完全关闭游戏。
2. 解压所选 ZIP，将整个 `atmosphere/` 文件夹复制到 SD 卡根目录，合并目录并覆盖同名文件。核心、资源和补丁必须一起安装，避免混用版本。
3. 启动游戏，确认兼容层说明显示 `v1.0.0`。具体操作见包内 `INSTALL.txt`。
4. 将每个模组的完整文件夹单独放入 `SD:/atmosphere/contents/010021C000B6A000/romfs/isaac_mods/mods/`，避免多套一层文件夹；完全关闭并重启游戏后，在模组菜单管理开关。

`atmosphere/contents/010021C000B6A000/exefs/isaac_runtime_sha256.md` 是正式交付的一部分，记录当前 `subsdk9` 的版本、构建号、大小和 SHA-256。后续发布包沿用当前 v1.0.0 的目录及文档格式，并同步实际运行文件指纹，不能删除该文件或沿用旧指纹。

## 已包含的兼容层补丁

所有下列组件均在完整发行包中，统一版本、安装和验证，无需另行选择或下载补丁：

| 包内目录（`atmosphere/nro_patches/` 下） | 用途 |
| --- | --- |
| `isaac-repentance-lifecycle-relay/` | 运行时所需的生命周期转接 |
| `isaac-repentance-static-callbacks/` | 原生回调挂接 |
| `isaac-repentance-native-heap-budget/` | 与当前核心配套的内存预算 |
| `isaac-repentance-loop-time-carry/` | 保留卡顿补偿后已推进的时间，修复持续逻辑超速 |

开源部分的补丁生成和校验代码见 [`runtime/game_patches/`](runtime/game_patches/) 与 [`tools/`](tools/)。目录划分和内部生成步骤不改变补丁归属；作者模组的覆盖补丁仍归对应模组。时序修复不代表所有场景的绘制帧率已经改善。

版本更新记录见 [Releases](https://github.com/granule256/isaac-mod-runtime/releases)。

已知问题：物品原地变形后，旧小地图图标可能未及时刷新；部分 API 行为、回调时机及多模组组合仍待验证，重负载场景可能出现长帧。

下载亦可通过 ToMod 的以撒页面及 GBAtemp 发布帖；QQ群：**1124953430**，[Discord](https://discord.gg/JMQc2jMsve)。

## 项目组成

- **兼容运行时**：适配 `Isaac`、`Game`、`Level`、`Room`、实体、道具配置、精灵、字体、输入、音频等接口，并提供可枚举的 API Catalog。
- **兼容层补丁实现**：位于 [`runtime/game_patches/`](runtime/game_patches/) 等目录，属于完整兼容层，随兼容层统一版本和交付；保留各项实现的原件指纹与行为校验。
- **打包与诊断工具**：生成安装目录、验证补丁来源及文件指纹，辅助区分逻辑速度、绘制频率和长帧。

仓库不提供游戏原件、密钥、设备凭据或完整第三方模组安装包。部分源码和测试夹具引用第三方项目，相关版权归原作者。

## 已有验证覆盖

以下项目已有部分功能验证记录，不代表全部内容、版本和组合均通过：

- 界面及基础框架：EID、Mod Config Menu、MinimapAPI、StageAPI。
- 功能模组：GoodTrip、Planetarium Chance、MusicModCallback、TimeMachine、Watch out, laser!。
- 其它适配：部分血量、首领血条、大型内容及自定义角色相关接口。

兼容性以接口的存在、返回语义和回调时机共同判断。未测试范围不能按“已恢复”计算。

## 构建兼容运行时

此仓库只发布开源部分。完整构建还需要与当前源码及公告资源匹配的 `NOTICE_GUARD_ARCHIVE`，相关内部实现不在本仓库；缺少匹配库时不能仅凭本仓库构建完整运行时。

需要 Python、Docker、相应 C++ 交叉工具链，以及自行准备的未修改游戏模块输入。当前目标为游戏 `1.7.9b` 的指定构建；具体指纹由构建工具和源码守卫核对，版本不匹配时停止处理。

在仓库根目录执行：

```sh
docker run --rm -v "$PWD":/work -v /path/to/inputs:/inputs -w /work \
  devkitpro/devkita64:latest bash -lc \
  '. /opt/devkitpro/devkita64.sh && make -C runtime runtime_module -j4 \
   SKIP_DEFAULT_PC_MODS=1 OUT=deploy \
   ORIGINAL_NRO=/inputs/Repentance.nro ORIGINAL_NPDM=/inputs/main.npdm \
   NOTICE_GUARD_ARCHIVE=/inputs/libnotice_guard.a MOD_ROW_DUMP_ROOT=/inputs/game-dump'
```

参数与入口说明见 [`runtime/Makefile`](runtime/Makefile)。原始游戏模块仅作为本地构建输入，不随源码分发。

## 构建完整兼容层

完整兼容层必须同时生成核心、配套资源与全部已纳入发布的兼容层补丁，包括 `loop-time-carry` 时序修复。内部组件可以分别编译或生成，发布前须核对清单并合并为同一安装树；缺少任何必需组件的产物不能标作完整兼容层。当前时序修复纠正游戏速度，不代表绘图开销或整体帧率已经改善。

## 打包与安装

基础打包默认保留原模组文件：

```sh
python3 tools/build_deploy_package.py \
  --runtime runtime/deploy \
  --mod /path/to/original-mod \
  --output releases/local/package
```

兼容层自身的全部补丁必须默认进入完整发行包，不能作为用户需要另选或另装的独立产品。上述工具的内部输入参数不决定发布归属；打包前后须核对完整清单，防止遗漏。作者模组的覆盖补丁仍归对应模组，只有明确传入 `--apply-mod-patches` 才会合入；请核对来源版本和指纹。

发行包分中文和英文两版，每包附一份 `INSTALL.txt` 介绍项目和安装方法，并保留 `exefs/isaac_runtime_sha256.md` 记录当前核心指纹；完整兼容层内容一致，运行文件中包含自身全部补丁。安装按包内 TXT 操作。不要混用不同构建的核心、内存预算及说明资源。发布压缩包通过 Release 资产分发，不提交到源码仓库。

## 性能与诊断

当前主要调查重负载下的长帧及限制出帧的路径。回调次数不等于屏幕呈现次数，GPU等待时间也不等于能够直接省掉的时间；性能结论需说明版本、场景、测量窗口及限制。

独立速度诊断载荷保留在本地资料中，不随公共源码分发，可用于区分持续超速与绘制卡顿。当前尚无覆盖全部模组与场景的整体性能结论。

## 源码导航

| 路径 | 内容 |
| --- | --- |
| [`runtime/`](runtime/) | 生产运行时、分层实现与定向测试 |
| [`runtime/game_patches/`](runtime/game_patches/) | 兼容层修复实现与构建清单，随完整兼容层交付 |
| 本地可选输入 | 历史覆盖补丁单独保留，不随公共源码分发 |
| [`tools/`](tools/) | 构建、装配、核对与诊断脚本 |
| `tests/` | 跨模块契约和工具测试 |
| [贡献与协作](#贡献与协作) | 贡献规范、验证及人工发布流程 |

## 许可与致谢

整体按 [GPL-2.0](LICENSE) 发布。原创部分版权署名为 **Copyright (C) 2026 granule256**；第三方文件保留原始版权和许可证。

本项目使用或参考了 [Atmosphère](https://github.com/Atmosphere-NX/Atmosphere)、libnx（ISC）、[exlaunch](https://github.com/shadowninja108/exlaunch) 和 [Lua 5.3.3](https://www.lua.org/)。各组件的许可范围以其源码声明为准。

本项目为非官方社区项目，与游戏开发商、发行商及模组作者无隶属关系。

## 远端精简源码规范（2026-10-30 更新）

远端项目说明集中在根 `README.md`。只提交生产兼容层、现用第三方依赖及许可、构建工具、核心测试和必要文本输入；不能将 `runtime/`、`tools/`、`tests/` 整目录无条件同步。独立 `runtime/diagnostic/`、旧 `runtime/exlaunch/` 工程副本、子目录 README、模组原件/覆盖脚本、游戏素材、媒体工程、日志证据、构建与发布产物和本机规范留在本地。现用 exlaunch 是 `runtime/source/lib/`；枚举生成与契约测试实际使用的指定文档页保留原字节。

在精简发布工作区暂存后运行 `python3 tools/check_remote_source.py`；主开发工作区直接审待发布版本时运行 `python3 tools/check_remote_source.py --ref main`。检查所有未推送提交，避免中间提交夹带被最终树移除的本地内容。`tools/publish_progress.sh` 已改为只读检查，不再自动同步或推送。

发布 `main` 承接 `origin/main`，不直接推开发 `master`、不强推、不使用旧 `public` 远端；AI 只整理和本地提交，所有最终推送（含标签）均由用户审查后亲自点击。`tools/pre_push_source_check.sh` 为本地推送前检查，新检出须安装/整合到 Git `pre-push`，不得绕过。清理只移出发布索引，本地原件与历史文档完整保留。

公告生成工具会在正文分页后固定追加赞赏尾页，包含微信、支付宝、Ko-fi 和项目 GitHub 地址；八种语言共用收款码并分别提供本地化文案。`tools/title_notice_support/` 中仅有三张 90×90 的必要公告输入图片，已逐文件纳入源码检查许可；原始收款截图和生成的公告图集不提交。

### 公告防护模块的本地拆分实验

公告控制、完整性处理、五个基础 Lua 类型的注册及 Font/Sprite 原生入口绑定集中在同一编译模块。公开接口位于 `runtime/source/notice_runtime_bindings.hpp`，其余 API 家族保持原有实现。启动入口表中的部分地址和机器码校验值保存在本地内部输入中；发布检查同时拒绝内部文件和这些地址在公开注释、元数据中的副本。静态库不提交源码仓库。

本地持有完整实现时可运行 `make -C runtime notice-guard-archive`，产物目录沿用 `EXL_ARTIFACT_DIR`；正式构建应显式指定独立的构建及产物目录。仅持有预编译依赖时，给兼容运行时构建命令增加 `NOTICE_GUARD_ARCHIVE=/absolute/path/libnotice_guard.a`；源码与库均缺失时明确停止构建。Lua 集成测试在缺少内部实现的检出中需要匹配宿主平台的 `NOTICE_GUARD_HOST_ARCHIVE`。库与公告资源必须配套，不能混用不同构建。

这是本地边界拆分和防修改实验，尚未作为闭源发行包发布，现有 GPL 许可未改变；正式闭源分发须先解决相关授权。现有私有远端历史含原实现，公开前必须逐提交审查并隔离这些历史，不能仅清理最新目录。隐藏部分地址只增加重建和分析成本，不保证无法通过旧源码或二进制恢复。

该实验的私有输入还包括原生挂钩和模组菜单的实现，公开项目保留它们的接口。发布构建应先生成防护归档，再通过 `NOTICE_GUARD_ARCHIVE` 链接；归档内固定实际校验及其 SHA-256、内存操作实现，避免通过替换公开校验函数授权。调试信息移除时保留异常展开数据。

公告相关的动画加载与资源覆盖控制也在该模块内；库中只保留必要的公告域对外接口，路径、状态与校验基准不作为可替换符号导出。私有构建将清单摘要转换储存，以减少直接查找替换的捷径；这属于增加修改成本，不是客户端秘密无法提取的保证。

2026-10-31 的本地实验进一步保护最终链接的公告代码、必要调用点和只读常量。生产构建在 ELF 转 NSO 前执行 `tools/seal_notice_code.py`，拒绝保护范围内的动态重定位和不兼容的旧防护库；语言资源路径与页数使用不含指针的只读记录。标题转换独立检查本次菜单的更新、绘制和实际绘制挂钩，公告加载失败保持拦截，并与文件不匹配分别显示原因。检查位于启动和标题边界，局内不逐帧散列代码。构建工具及其最小 ELF 测试属于必要源码，不上传生成的库、摘要记录、负例载荷或测试证据。客户端内的摘要可以被成套重算，这些措施不提供不可绕过的信任根；已读版本文件仍只用于保存用户体验状态。


## 贡献与协作

以可复核的行为证据改进兼容性，保持原模组的调用方式和功能。修改前先定位差异，在兼容层内部选择合适的实现位置；自身补丁统一属于兼容层。

## 兼容性判据

接口验证覆盖四项：

1. **接口面**：方法、字段、全局量和枚举均有明确来源。
2. **存在性**：目标接口能够被模组正常调用。
3. **语义**：参数、返回值、错误和对象生命周期符合参考行为。
4. **时机**：回调次数、顺序及执行阶段符合约定。

加载成功、单个接口通过或零错误不代表整个模组通过验收。区分未测试、存在问题、有限测试未发现问题，并注明场景和边界。

API 定义见 `runtime/src/interfaces/lua/api_catalog.cpp`，接口范围工具见 `tools/mod_api_gap_report.py`，契约参考见 `tools/pc_contract_docs/`。

## 修改边界

- 兼容运行时位于 `runtime/source/` 和 `runtime/src/`。
- `runtime/game_patches/` 中的修复属于兼容层，随兼容层统一版本、构建和发布；逐项登记原件指纹、改动范围和行为验证。
- 运行时内存预算、时序修复及其他自身补丁均属于完整兼容层，统一安装。
- 日常修复优先处理兼容实现，保持作者模组原件；历史覆盖补丁须显式选择并核对来源版本。
- 性能优化不能以停用功能、降低逻辑频率或提高设备时钟替代。

## 验证与性能

按改动范围选择定向检查，例如：

```sh
python3 tools/run_tests.py --only loop_time_carry
python3 -m unittest runtime.tests.test_game_patch_bundle
```

本项目不以全量门禁作为日常提交步骤，不运行无筛选的 `tools/run_tests.py`。简单文案修改检查格式、链接和准确性即可；复杂行为修改增加必要的宿主检查和设备验证。

修改前评估每帧CPU、分配与回收、内存峰值及I/O成本。性能对比应保持版本、负载、位置和时钟一致，记录长帧与测量开销；嵌套回调不能重复相加，历史最大值不能冒充本窗口最大值。未取得设备结果时如实说明。

不要为了使结果通过而掩盖失败；测试与实现冲突时先核对契约，明确记录必要的测试更新理由。

## 源码与隐私

可同步范围为 `runtime/`、`tools/`、`tests/`、`README.md`、`LICENSE` 和 `.gitignore`。

本机协作配置、研究记录、设备备份、日志、游戏原件、构建目录、运行时二进制和发布压缩包不进入远端源码。安装包使用 Release 资产分发。

工具通过参数、环境变量或忽略的本机配置读取设备信息。提交不得包含个人目录、设备地址、账号、访问令牌或口令。对外介绍采用中性技术表述，保留第三方许可证和原始版权声明。

## 提交与发布

说明具体问题、改后行为、验证结果和未覆盖范围。建议使用 `fix:`、`feat:`、`docs:`、`tools:` 或 `chore:` 前缀。

开发历史与远端精简历史分别保留。同步以远端 `main` 为父提交，导入经过核对的源码白名单并生成增量提交，不强推开发线，也不重写远端历史。

维护者可以整理和提交待发布内容，**最终推送由人工审查后执行**。不要使用自动推送脚本代替人工确认，也不要将推送到其它旧远端作为替代。

## 问题反馈

请提供核心或发行版本、模组来源版本、触发步骤、预期行为、实际行为及可公开的日志。提交前清除设备地址、账号和私人路径；不要上传存档、游戏数据或凭据来代替复现说明。


## 本地源码拆分与构建

本地仅source与data两层入口：source/public为本工作区、只含可审查发布的源码；source/private保存既定私有实现和相关测试；文档、证据、原件、构建及发布包存放data。公共与私有实现共同构建时，通过private中的tools/workspace.py在data/build/workspace装配，正式源文件不混放。公共检出单独构建仍须提供匹配的NOTICE_GUARD_ARCHIVE。Lua宿主集成测试须提供匹配的NOTICE_GUARD_HOST_ARCHIVE；本机游戏/作者模组依赖的历史集成测试保留在data，不能将其结果当作公共树的独立验收。

设备地址与凭据通过显式参数、环境变量或ISAAC_DEVICE_CONFIG指定，不内置本机地址。所有最终推送仍由用户人工审查后执行，目录整理不代表已有远端历史已清理。


---

<a id="english"></a>

# isaac-mod-runtime — English

[简体中文](#中文) | [English](#english)

A community compatibility layer for running PC Lua mods in **The Binding of Isaac: Repentance on Nintendo Switch**. It provides mod APIs, callbacks, resource loading, configuration persistence and an in-game mod menu while aiming to preserve the original mods' calls and behavior.

The current stable version is **v1.0.0**, based on v1.0.0-rc.4. The compatibility layer includes its runtime, supporting resources and all of its own fixes, performance changes and timing patches as one versioned installation. It is free; donations are optional and do not affect access.

## Download and install

Download the packages from the [v1.0.0 release](https://github.com/granule256/isaac-mod-runtime/releases/tag/v1.0.0). Source updates do not automatically update release assets.

| Package | Installation guide |
| --- | --- |
| `isaac-runtime-v1.0.0-zh-CN.zip` | Simplified Chinese |
| `isaac-runtime-v1.0.0-en.zip` | English |

Both packages contain identical compatibility-layer files and patches; only the root `INSTALL.txt` language differs. The game, Atmosphère and third-party mods are not included.

1. Use a Switch configured for Atmosphère and the supported Repentance **1.7.9b** build. Back up your saves and fully close the game.
2. Extract a package and copy its entire `atmosphere/` folder to the SD card root. Merge folders and overwrite matching files. Keep the core, resources and patches together and avoid mixing versions.
3. Launch the game and check that the compatibility-layer notice displays `v1.0.0`. Follow `INSTALL.txt` for details.
4. Place each complete mod folder in `SD:/atmosphere/contents/010021C000B6A000/romfs/isaac_mods/mods/`, without an extra nested folder. Fully close and restart the game after changing mods, then manage them from the in-game mod menu.

The release includes `atmosphere/contents/010021C000B6A000/exefs/isaac_runtime_sha256.md`. It records the version, build, size and SHA-256 of the actual packaged `subsdk9`. Future packages follow the current v1.0.0 layout and document format, retain this file and update its values for each build.

Use left/right, the stick or L/R to turn notice pages. On first launch or after an update, read every page and hold B to close it. On later launches of the same version it stays closed by default. Select the notice entry at the bottom right of the title screen and press A to reopen it; when opened manually, press B on any page to close it.

## Included patches

All of these components ship and install with the complete compatibility layer:

| Directory under `atmosphere/nro_patches/` | Purpose |
| --- | --- |
| `isaac-repentance-lifecycle-relay/` | Lifecycle relay required by the runtime |
| `isaac-repentance-static-callbacks/` | Native callback hooks |
| `isaac-repentance-native-heap-budget/` | Memory budget paired with the current core |
| `isaac-repentance-loop-time-carry/` | Preserve time already advanced during catch-up updates to fix sustained simulation speedup |

Patch generators and verification code in the open-source portion are in [`runtime/game_patches/`](runtime/game_patches/) and [`tools/`](tools/). Internal generation steps do not make these components separate products. Patches to third-party mods belong to those mods. The timing fix does not imply a general rendering frame-rate improvement.

## Compatibility and known issues

The runtime covers `Isaac`, `Game`, `Level`, `Room`, entities, item configuration, sprites, fonts, input and audio, with an enumerable API Catalog. It supports multilingual title notices, resource integrity checks and adaptations for custom shaders.

Partial validation records exist for EID, Mod Config Menu, MinimapAPI, StageAPI, GoodTrip, Planetarium Chance, MusicModCallback, TimeMachine and Watch out, laser!, along with some health bars, boss bars, larger content mods and custom-character interfaces. These records do not certify every feature, version or combination. Successful loading or zero logged errors does not prove full compatibility.

Known issues include a stale minimap icon after an item transforms in place. Some API semantics, callback timing and mod combinations need further testing. Heavy workloads can still produce long frames; stable full frame rate is not guaranteed. Custom characters, dense effects and complex maps need more coverage.

For version history, see [Releases](https://github.com/granule256/isaac-mod-runtime/releases).

## Source and building

| Path | Contents |
| --- | --- |
| [`runtime/`](runtime/) | Production runtime, layered implementation and targeted tests |
| [`runtime/game_patches/`](runtime/game_patches/) | Compatibility-layer patch implementation and inventory |
| [`tools/`](tools/) | Build, assembly and verification tools |
| [`tests/`](tests/) | Tool and cross-module contract tests |

This repository publishes the open-source portion. A complete runtime build also requires a matching `NOTICE_GUARD_ARCHIVE`; its internal implementation is not included here. Source and library versions must match the notice resources. Host Lua integration tests likewise require a matching `NOTICE_GUARD_HOST_ARCHIVE`.

Building requires Python, Docker, the C++ cross toolchain and your own unmodified supported game inputs. The build tools check the target build and reject mismatches. See [`runtime/Makefile`](runtime/Makefile) for arguments and targets. The following illustrates the runtime component build; replace the input paths with your own files:

```sh
docker run --rm -v "$PWD":/work -v /path/to/inputs:/inputs -w /work \
  devkitpro/devkita64:latest bash -lc \
  '. /opt/devkitpro/devkita64.sh && make -C runtime runtime_module -j4 \
   SKIP_DEFAULT_PC_MODS=1 OUT=deploy \
   ORIGINAL_NRO=/inputs/Repentance.nro ORIGINAL_NPDM=/inputs/main.npdm \
   NOTICE_GUARD_ARCHIVE=/inputs/libnotice_guard.a MOD_ROW_DUMP_ROOT=/inputs/game-dump'
```

A complete release must also assemble and verify all supporting resources and patches, including `loop-time-carry`. Internal component outputs alone must not be labeled a complete compatibility layer. Release ZIPs are distributed as Release assets, separate from the source repository.

## Contributing and verification

Preserve original mod behavior and implement fixes within the compatibility layer. Verify interface provenance, availability, parameter and return semantics, object lifetime and callback timing. Report untested coverage explicitly. Do not replace functionality, reduce logic frequency or raise device clocks to claim an optimization.

Use targeted checks appropriate to the change, for example:

```sh
python3 tools/run_tests.py --only loop_time_carry
python3 -m unittest runtime.tests.test_game_patch_bundle
```

Documentation edits need direct content and link checks. More complex behavioral changes need relevant host checks and device validation. Do not run an unfiltered full test suite by default. Compare performance using the same version, workload, location and clocks, and state measurement limits.

Keep only reviewed production code, active dependencies and licenses, build tools, core tests and required inputs in the remote source tree. Do not upload private implementations, local instructions, credentials, game inputs, mod originals, media projects, logs, evidence, binaries or release archives. Preserve third-party notices. Run `python3 tools/check_remote_source.py` on staged content and audit every unpublished commit before pushing. `tools/publish_progress.sh` is read-only. The pre-push source hook must remain enabled.

Prepare releases on the minimal `main` history based on `origin/main`, without force-pushing development history or using the old `public` remote. All final source/tag pushes and internet publication are performed by the maintainer after review.

## License, credits and contact

The project is licensed under [GPL-2.0](LICENSE). Original code is **Copyright (C) 2026 granule256**. Third-party files retain their own copyrights and licenses. The project uses or references [Atmosphère](https://github.com/Atmosphere-NX/Atmosphere), libnx (ISC), [exlaunch](https://github.com/shadowninja108/exlaunch) and [Lua 5.3.3](https://www.lua.org/). Each component's source notices define its license scope. This is an unofficial community project, unaffiliated with the game developers, publishers or mod authors.

Downloads are also available through the Isaac page on ToMod and the GBAtemp release thread. QQ group: **1124953430**. [Discord](https://discord.gg/JMQc2jMsve).

For bug reports, include the release/core version, mod version, reproduction steps, expected and actual behavior and sanitized logs. Remove private paths, device addresses, accounts and credentials before sharing.
