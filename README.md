# isaac-mod-runtime

让 **PC 版《以撒的结合：忏悔》的 Lua 模组**（例如 EID「External Item Descriptions」物品描述）
能在**另一套主机平台**上运行。做法是在游戏进程里注入一个运行时模块，装上派发挂点、
实现一套 Lua API，再按清单把模组加载起来。

> ⚠️ **预发布版（beta），不保证可用。**
> 只在少数场景验证过；可能启动失败、运行中崩溃、功能静默失效，也可能影响存档与设备。
> 请只在你自己的、已备份、可承受风险的机器上使用，后果自负。
>
> 本仓库**不包含任何模组本体**（例如 EID 是第三方作品，请自行获取并遵守其许可），
> 也不包含游戏数据、密钥或设备凭据。

## 当前版本

`v1.0.0-beta.1`（内部构建 `20261026341000`）。预发布，尚未正式发布。

## 适用环境

| 项目 | 要求 |
| --- | --- |
| 主机 | 已安装 **Atmosphère** 自制固件 |
| 游戏 | **The Binding of Isaac: Repentance** 1.7.9b（构建号 `91C73FDD575061318D68886316AFEAC72388B2AB`） |
| 其他 | 运行时**会核对游戏构建号**，版本不符不会加载 |

## 它做什么

- 在游戏进程里装上派发挂点（每帧更新、渲染、取道具前、资源挂载点重建、玩家初始化），并自己派发"游戏开局"事件；
- 实现 PC 版 Lua API 的一个**子集**，带一张**可枚举的 API Catalog**（`Isaac` / `Game` / `Level` /
  `Room` / `Entity` 各子类 / `EntityPlayer` / `ItemConfig` / `Sprite` / `Font` / `RNG` / `Vector` /
  `Color` / `Input` / `SFXManager` / `MusicManager` / `PersistentGameData` 等）；
- 按 `manifest.json` 加载一个模组：读清单 → 读入口脚本 → 建 Lua 状态 → 注册回调 → 挂载模组资源；
- 模组资源里的 `.png` 在内存里转成引擎认识的 PCX（含预乘 alpha 处理）。

**不保证**语义与 PC 完全一致。按三个维度验收，任何一维不满足都会被标记，但"未标记"不等于"一定正确"
（基准见 `CONTRIBUTING.md`）：① **存在** ② **语义**（返回值是否与 PC 一致）③ **时机**（回调派发时机是否与 PC 一致）。

## 验证范围

**部分功能验证过**的模组（不代表完整游玩验收）：

- 界面类：**Mod Config Menu 中文版**、**EID**（物品描述）、**MinimapAPI**（小地图）、**StageAPI**
- 玩法类：**GoodTrip**（传送）、**Planetarium Chance**、**What's My DPS**、**No Donation Machine Jam**
- 大型/角色类：**RepentancePlus 社区版**、**Trinity**、**Auri**（自定义角色，含贪婪模式）
- 其它：**Custom-Bossbar** / **Enhanced-Boss-Bars**、**Mini pause menu+**、**TimeMachine**、**MusicModCallback**

其余模组未系统验证。单个 API 通过、加载零报错都不代表整个模组已恢复。

## 已知问题

1. **局内帧率约 30~40（满帧 60）**——当前最影响手感的问题。模组回调每帧约 5.9 ms，加上引擎侧开销
   超过 16.7 ms 的帧预算，引擎只能隔帧跑逻辑。尚未解决。
2. **启动期概率崩溃**：启动期工作与"游戏装载自身模块"重叠时可能中止。当前规避办法是把启动期工作
   推迟若干秒（见 `runtime/source/runtime_entry.cpp` 的模块 worker）。
3. **部分 Lua 接口缺失或语义未核对**：缺失接口在模组里表现为"调用 nil"；若发生在没有 `pcall`
   保护的条件回调里，会让整条物品描述消失。仓库内附静态核对工具：`tools/eid_api_gap_report.py`。

## 构建

需要 Docker、`devkitpro/devkita64` 镜像，以及**自行准备的原版游戏模块文件**（NRO 与 npdm）作为构建输入：

```bash
docker run --rm -v "$PWD":/work -w /work devkitpro/devkita64:latest bash -lc \
  '. /opt/devkitpro/devkita64.sh && make -C runtime -j4 SKIP_DEFAULT_PC_MODS=1 \
   OUT=deploy "ORIGINAL_NRO=<原版 NRO 路径>" "ORIGINAL_NPDM=<原版 npdm 路径>" \
   TEST_BUILD_ID=<构建号>'
```

产物是一棵可直接覆盖到存储卡的目录树，共 28 个文件：`exefs/`（运行时模块 + npdm）、
`romfs/rp_patch/`（菜单行资源）、`nro_patches/`（补丁与内存预算表）。

可选参数（分层构建、产物目录、启动延迟、清单行导出等）见 `runtime/Makefile` 与 `runtime/config.mk`。

## 安装

发布包自带 `README.md`，按里面的步骤覆盖到存储卡即可。**覆盖前请先备份你自己的文件。**

## 目录结构

```
runtime/
  source/          运行时本体（入口、挂点管理、Lua 运行时、引擎绑定、平台兼容层）
  src/             分层架构：domain / application / infrastructure / interfaces
  exelaunch/       兼容层（第三方派生，见文件头许可）
  misc/            构建片段与打包规则
  diagnostic/      诊断探针
  probes/          实验性探针构建
  mod-patches/     模组补丁（不进发布包）
  pc-mods/         PC 版模组副本（开发参考）
  tools/           运行时侧工具
  tests/           单元 / 集成 / 契约测试
  source/third_party/lua-5.3.3   Lua 5.3.3 源码（MIT）
tools/             离线工具：读数、发布包部署、API 缺口核对
tests/             跨模块集成与契约测试
```

设备访问凭据不写在仓库里：所有工具从命令行参数、环境变量（`ISAAC_DEVICE_*`），
或本机私有文件（已 gitignore）读取。

## 免责声明

- 本项目与游戏开发商、发行商及任何模组作者无关联；
- 不提供任何游戏本体、密钥或模组内容；
- 修改主机系统与游戏进程存在风险（也可能违反主机使用条款），请自行判断并自担后果。

## 致谢与许可

项目派生/参考了以下开源项目，**整体以 GPL-2.0 发布**（见 `LICENSE`）：

- [Atmosphère-NX](https://github.com/Atmosphere-NX/Atmosphere)（GPL-2.0）：`runtime/source/nn/os/*` 等；
- libnx（ISC）：`runtime/source/lib/nx/*` 等；
- [exlaunch](https://github.com/shadowninja108/exlaunch)（GPL-2.0）：兼容层与入口约定；
- [Lua 5.3.3](https://www.lua.org/)（MIT）：`runtime/source/third_party/lua-5.3.3`。

各第三方组件的版权与许可声明保留在对应源文件头部。

第三方模组（例如 EID，作者 wofsauge）**不在本仓库内**，版权归原作者。
