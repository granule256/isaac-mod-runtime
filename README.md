# isaac-mod-runtime

让 **PC 版《以撒的结合：忏悔》的 Lua 模组**（例如 EID「External Item Descriptions」物品描述）
能在**另一套主机平台**上运行。做法是在游戏进程里注入一个运行时模块，装上派发挂点、
实现一套 Lua API，再按清单把模组加载起来。

> ⚠️ **开发测试版（work-in-progress / experimental），不保证可用。**
> 只在少数场景验证过；可能启动失败、运行中崩溃、功能静默失效，也可能影响存档与设备。
> 请只在你自己的、已备份、可承受风险的机器上使用，后果自负。
>
> 本仓库**不包含任何模组本体**（例如 EID 是第三方作品，请自行获取并遵守其许可），
> 也不包含游戏数据、密钥或设备凭据。

## 项目结构

核心源码在 `runtime/`（`runtime/source` 与 `runtime/src` 是两个源码根）；顶层 `tools/`、`tests/`
是开发用的辅助脚本，不参与编译。

## 适用环境

| 项目 | 要求 |
| --- | --- |
| 主机 | 能够加载自制运行环境的机型 |
| 游戏 | **The Binding of Isaac: Repentance** 1.7.9b |
| 其他 | 运行时**会核对游戏构建号**，版本不符不会加载 |

## 它做什么 / 不做什么

**做**：
- 在游戏进程里装上派发挂点（每帧更新、渲染、取道具前、资源挂载点重建），并自己派发"游戏开局"事件；
- 实现 PC 版 Lua API 的一个**子集**（`Isaac` / `Game` / `Level` / `Entity` / `EntityPlayer` /
  `ItemConfig` / `Sprite` / `Font` / `RNG` / `Vector` / `Color` 等），并带一张**可枚举的 API Catalog**；
- 按 `manifest.json` 加载一个模组：读清单 → 读入口脚本 → 建 Lua 状态 → 注册回调 → 挂载模组资源。

**不保证**：
- **语义与 PC 完全一致**。按三个维度验收，任何一维不满足都会被标记，但"未标记"不等于"一定正确"
  （基准见 `CONTRIBUTING.md`）：① **存在**（PC 有的接口我们有没有）② **语义**（返回值是否与 PC 一致）
  ③ **时机**（回调/事件的派发时机是否与 PC 一致）。
- 兼容所有模组：目前只在少数模组上做过较多验证，且仍有已知缺口。

## 已知问题（节选）

1. **启动期概率崩溃**：当"运行时的启动期工作"与"游戏装载自身模块"重叠时可能中止。
   当前规避办法是把启动期工作推迟若干秒（见 `runtime/source/runtime_entry.cpp` 的模块 worker）。
2. **部分 Lua 接口缺失或语义未核对**：缺失接口在模组里表现为"调用 nil"；若发生在没有 `pcall`
   保护的条件回调里，会让整条物品描述消失。仓库内附静态核对工具：`tools/eid_api_gap_report.py`。

## 构建

需要 Docker 与 `devkitpro/devkita64` 镜像：

```bash
docker run --rm -v "$PWD":/work -w /work devkitpro/devkita64:latest bash -lc \
  '. /opt/devkitpro/devkita64.sh && make -C runtime -j6 LAYERED_RUNTIME=1 PROBE_BREAK=0 \
   OUT=deploy BUILD=build runtime_module'
```

产物在 `deploy/` 下。

## 安装

发布包自带 `README.md`，按里面的步骤覆盖到存储卡即可。**覆盖前请先备份你自己的文件。**

## 目录结构

```
runtime/
  source/            运行时本体（入口、挂点管理、Lua 运行时、引擎绑定）
  src/               分层架构：domain / application / infrastructure / interfaces
  exelaunch/         兼容层（第三方派生，见文件头许可）
  source/third_party/lua-5.3.3   Lua 5.3.3 源码（MIT）
  tests/             单元 / 集成 / 契约测试
tools/               离线与设备侧工具：读数、发布包部署、API 缺口核对
tests/               跨模块集成与契约测试
```

设备访问凭据不写在仓库里：所有工具从命令行参数、环境变量（`ISAAC_DEVICE_*`），
或本机私有文件（已 gitignore）读取。

## 免责声明

- 本项目与游戏开发商、发行商及任何模组作者无关联；
- 不提供任何游戏本体、密钥或模组内容；
- 修改主机系统与游戏进程存在风险（也可能违反主机使用条款），请自行判断并自担后果。

## 致谢与许可

项目派生/参考了若干开源项目，**整体以 GPL-2.0 发布**（见 `LICENSE`）。
各第三方组件的版权与许可声明保留在对应源文件头部。

第三方模组（例如 EID，作者 wofsauge）**不在本仓库内**，版权归原作者。
