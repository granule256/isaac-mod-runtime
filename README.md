# isaac-mod-runtime

面向《以撒的结合：忏悔》PC Lua 模组的社区兼容运行时，适配游戏 API、回调、资源加载和配置持久化，目标是恢复 PC 模组行为，保持作者模组原件。

当前处于预发布阶段。开发线包含 `v1.0.0-beta.4` 的说明界面、完整性检查和后续兼容修复；可下载版本以 Releases 为准。加载成功、零报错和完整功能验收是不同结论。

## 源码结构

| 路径 | 用途 |
| --- | --- |
| `runtime/source/` | 启动、原生游戏绑定、现用 exlaunch 底层及 Lua 源码 |
| `runtime/src/` | 模组加载、API、回调、资源、平台接口与实现 |
| `runtime/game_patches/` | 单独构建的游戏修复，包含版本和原件指纹守卫 |
| `runtime/misc/`、`runtime/tools/` | 编译、链接及部署树生成规则 |
| `tools/` | 构建、装配、接口核对和开发工具 |
| `runtime/tests/`、`tests/` | 核心实现的定向测试 |

生产构建使用 `runtime/source/lib/` 中的 exlaunch 代码；它负责将 C++ 代码接入游戏进程并挂接游戏函数。旧的 `runtime/exlaunch/` 完整工程副本不属于构建输入，不随源码发布。

## 构建

需要 Python、Docker、C++ 交叉工具链和自行准备的未修改游戏模块。当前目标为游戏 `1.7.9b` 的指定构建；版本、结构或指纹不匹配时停止处理。仓库不提供游戏原件、密钥、设备配置或第三方模组安装包。

在仓库根目录执行，将示例输入路径改为容器内实际路径：

```sh
docker run --rm -v "$PWD":/work -w /work devkitpro/devkita64:latest bash -lc \
  '. /opt/devkitpro/devkita64.sh && make -C runtime runtime_module -j4 \
   SKIP_DEFAULT_PC_MODS=1 OUT=deploy \
   "ORIGINAL_NRO=/path/to/original/Repentance.nro" \
   "ORIGINAL_NPDM=/path/to/original/main.npdm"'
```

`runtime_module` 是生产入口，默认不附带示例模组。构建变量见 `runtime/Makefile` 和 `runtime/config.mk`；原始模块仅作为本地输入。

独立游戏修复不依赖兼容运行时或设备连接：

```sh
python3 -m runtime.game_patches.build \
  --nro /path/to/original/Repentance.nro \
  --output dist/game-patches
```

当前登记的 `loop-time-carry` 修正卡顿后时间累计丢失导致的持续逻辑超速；它不代表绘图开销或整体帧率改善。原件、记录或输出目录不满足要求时拒绝生成。

## 打包与验证

基础打包保留原模组文件；组合独立修复时显式增加 `--game-patches dist/game-patches`：

```sh
python3 tools/build_deploy_package.py \
  --runtime runtime/deploy \
  --mod /path/to/original-mod \
  --output releases/local/package
```

历史覆盖补丁不随源码提供；旧工具需要这些数据时，通过 `ISAAC_MOD_PATCH_ROOT` 指定本地外部输入。兼容修复应改运行时实现，不改写作者模组。安装遵循发行包内说明，不混用不同构建的核心、内存预算和说明资源；发布压缩包作为 Release 资产分发。

按修改范围选择定向测试，例如：

```sh
python3 -m unittest runtime.tests.test_source_package_purity tests.test_remote_source_policy
python3 -m unittest runtime.tests.test_game_patch_bundle
python3 tools/run_tests.py --only loop_time_carry
```

禁止运行无筛选的 `tools/run_tests.py` 全量门禁。简单文字和仓库整理做格式、引用与范围检查；行为变化增加相关宿主或设备验证。修改前评估 CPU、分配和回收、内存峰值与 I/O，不以停用模组、删减功能或提高时钟掩盖性能问题。

EID、Mod Config Menu、MinimapAPI、StageAPI、GoodTrip 等已有部分验证记录；自定义角色、密集特效和多模组组合仍需按版本、功能和场景验收，不据此宣称全部兼容或稳定满帧。

## 远端源码提交规范

1. **按用途逐项选文件。** 只收生产实现、实际使用的依赖、构建配置与工具、核心测试和必要文本输入。`runtime/`、`tools/`、`tests/` 是范围上限，不是整目录无条件白名单。
2. **项目说明只有根目录这一份 README。** 子目录不放 README，贡献与发布规则集中于此。保留第三方许可证、版权与来源声明；`tools/pc_enum_docs/` 和 `tools/pc_contract_docs/` 中实际用于生成或契约测试的文本是必要输入，保持来源和字节可核对，不扩成资料仓库。
3. **不上传本地材料。** 禁止独立 `runtime/diagnostic/`、旧 `runtime/exlaunch/`、模组原件和覆盖脚本、研究与交接文档、测试运行日志、设备读数、反汇编证据、游戏素材、媒体工程、本机规范和凭据。必要测试使用小型自建或临时生成的样本，不能借测试夹具夹带游戏原件。
4. **不上传产物和重复副本。** 构建目录、二进制、图片、录屏、压缩包、备份不进源码树；发布包放 Releases。本地移出索引时保留原件，历史文档完整归档。
5. **提交前检查索引，推送前检查实际提交。** 每次核对新增文件、完整待推送树和提交范围；提交说明写清问题、改后行为、验证及未覆盖范围。新增源码目录或文件类型须先明确用途并更新检查规则，不能放宽规则来通过检查。
6. **由人执行最终推送。** 开发历史与远端精简历史分开；发布增量承接 `origin/main`，不把本地开发线直接推上去、不强推或重写远端历史，不使用旧 `public` 远端。AI 可以整理和本地提交，最终由维护者审查后点击推送；标签同样适用。

```sh
# 审核已暂存的完整源码树；检查忽略规则也取自索引。
python3 tools/check_remote_source.py
# 审核将推送的实际版本，不受其它未提交工作影响。
python3 tools/check_remote_source.py --ref main
```

`tools/publish_progress.sh` 仅调用上述检查，不再切换分支、自动提交、推送或运行全量测试。

可将 `tools/pre_push_source_check.sh` 安装为本地 Git `pre-push` 钩子（已有钩子时先保留并整合）。它检查提交树及尚未进入远端的每个提交，拒绝夹带非源码内容，并只允许 `origin/main` 和发布标签；它本身不发起推送。

独立诊断脚本保留在本地。历史诊断构建需要额外载荷时，显式传入 `DIAGNOSTIC_ROOT=/absolute/path/to/local/diagnostic`；不从远端源码补带这些文件。

## 许可与来源

整体按 [GPL-2.0](LICENSE) 发布。原创部分版权署名为 **Copyright (C) 2026 granule256**；第三方文件保留原始版权和许可证。

使用或参考 [Atmosphère](https://github.com/Atmosphere-NX/Atmosphere)、[libnx](https://github.com/switchbrew/libnx)、[exlaunch](https://github.com/shadowninja108/exlaunch) 和 [Lua 5.3.3](https://www.lua.org/)。exlaunch 来源版本记录在 `runtime/config.mk`；Lua 归档来源和指纹保留在 `runtime/source/third_party/lua-5.3.3/SOURCE.md`，许可保留在其 `COPYRIGHT`；rtld 许可见 `runtime/source/rtld/LICENSE.txt`。

本项目为非官方社区项目，与游戏开发商、发行商及模组作者无隶属关系。反馈请提供版本、触发步骤、预期及实际行为，并清除设备地址、账号和私人路径。
