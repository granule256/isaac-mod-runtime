#!/usr/bin/env python3
"""通过大气层的调试桩，读设备上「正在运行的以撒」里我们自己的状态（只读）。

为什么需要它：设备侧原有的通道都有硬限制——写文件那条受 SaltyNX 会话生命周期约束
（注入流程结束即失效），崩溃报告一次会话只能取一次。调试桩（大气层自带）可以在游戏
运行时**直接读内存**，一次拿到全部读数：启动状态机走到第几步、清单安装为什么失败、
挂点各自装成什么样、运行时的文件表是否已植入、Lua 侧有没有登记成功。

★ 2026-09-17 更正（用户实测，原记录作废）：**不存在"attach 次数配额"** ——
此前写的"每次开机只可靠支撑很少几次 attach、用光要重启主机"是**错的**（用户原话：
"那个调试桩预算的，没有预算这回事"）。**可以放心多次 attach。**

仍然成立的是**稳定性**问题（这次实测也遇到了）：`monitor get info` 有时**不返回模块表**，
工具会退化成 mappings 扫描；扫描认不出可执行段时，可以用 `--base/--game-base` 手动指定，
或重启设备后第一次连接（那一次通常最完整）。**这跟"配额"是两件事，别再混为一谈。**

★ 2026-09-14 夜间改版：**默认走"一次挂载读完所有地址"**（这个行为保留）——
理由现在只是"**一次连完更快**"，不再是"省配额"。
旧版一次读数要 attach 四次（找进程 → 取基址 → 读身份 → 读变量），常常读到一半就没预算了。
新版把四件事合并进**同一个 gdb 会话、只 attach 一次**：会话是交互式的（gdb 从管道读命令），
先用 `monitor get info` 拿到基址，再用算出来的地址继续发读命令，最后 `detach`。

用法：
    python3 tools/read_device_state_via_gdb.py                      # 一次挂载读完（推荐）
    python3 tools/read_device_state_via_gdb.py --ip 192.168.124.11
    python3 tools/read_device_state_via_gdb.py --pid 141 --base 0x4e8a181000 --game-base 0x...
    python3 tools/read_device_state_via_gdb.py --dry-run            # 只测管道，不连设备

前置条件见 docs/问题与解决记录.md 的「用调试桩直接读设备状态」一节。
"""

from __future__ import annotations

import argparse
import collections
import os
import re
import select
import struct
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from runtime_layout_budget import DEFAULT_CODE_LIMIT

GDB_IMAGE = 'devkitpro/devkita64:latest'
# 2026-10-10静态生产候选：默认符号和51hook必须来自同一冻结包。
# 2026-10-14：100API候选采用本批最终ELF；设备仍需核实际SDK身份，未部署。
# 2026-10-14：用户指定4MiB代码预算的同源新构建；旧API300包仍在原目录保留。
# 2026-10-14：bug/API统一候选；尚未部署，设备读数仍需三锚点核对。
# 2026-10-15：shader挂载读取静态修复；离线未部署，设备须核对应SDK身份。
# 2026-10-15：补齐Random真实引擎源，278符号/8固定偏移同步；运行身份须核锚点。
# 2026-10-16：第五批100项静态包，278符号同步；未部署，不能当作当前卡版。
DEFAULT_ELF = 'dist/api-color-multiply-20261021/runtime-api-repairs.elf'

# 运行时的符号偏移。**必须与设备上那份模块同版本**。
# 同步时间：2026-09-14 23:09 构建（也就是设备上那份诊断版 `subsdk9`，410722 字节 /
# sha256 前 16 位 `633cdbedd743bc90`）。脚本会用三个**代码锚点**（身份函数、`exl_main`、
# `TryInstallDefaultManifestMod` 的函数头）与本地 ELF 逐字节比对——三个都对上，说明
# "设备上跑的这份"与"本表对应的那份"是同一个映像，读数才有意义。
#
# ⚠️ 教训（写在代码里免得再犯）：`identity` 那 16 字节的自校验只能证明"是同一版族"，
# **分不出相邻两次构建**；改过任何编译单元都可能让 `bss`/`data` 整体挪位。
# 所以任何一次重建之后，都必须用 `tools/elf_syms.py` 重新核对下面整张表。
class _SymbolTable(dict):
    """缺键时返回 0 并记账，而不是抛 `KeyError`。

    2026-09-16 的教训：漏一个符号名（`g_selfJournalTotalRecords`）让整次读数在**准备阶段**
    就崩了 —— 调试桩一个启动周期只能 attach 几次，一次 attach 就这么白白烧掉。
    现在缺的键进 `missing`，调用方跳过它们、照读其余的量。
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.missing: list = []

    def __missing__(self, key):
        self.missing.append(key)
        return 0


SYMS = _SymbolTable({
    # 2026-10-14统一候选：实际ELF的模组拥有者名称表。
    'g_ModOwnerNames': 0x5612a0,
    'shader_screen_intercept': 0x55740,
    # ---- 代码锚点（只用于核对版本，不作为"变量"读）----
    'identity': 0xfbb88,              # IsaacModRuntime_GetRuntimeIdentity
    'exl_main': 0x342e0,               # 模块入口（旧表写 0x8840，那是 20:00 那次的构建）
    'manifest_install': 0x9e38,       # TryInstallDefaultManifestMod（本次诊断改的就是它）
    'entry_relay_update': 0x7c0c,     # EntryRelayManagerUpdateCallback（更新挂点入口中继）
    'entry_relay_render': 0x4080,     # EntryRelayManagerRenderCallback（渲染挂点）
    'entry_relay_collectible': 0x474c,  # EntryRelayPreGetCollectibleCallback
    'entry_relay_rebuild': 0x4e7c,    # EntryRelayRebuildMountPointsCallback
    'present_got_intercept': 0x2100,  # IsaacModRuntime_PresentGotSlotIntercept
    # ---- 运行状态（相对我们的运行时模块）----
    'g_runtimeSelfAddress': 0x9de01a8,
    'g_sequence': 0x9de0410,          # TestRunObserver 状态机：走过的步数
    'g_stateDetail': 0x9de0418,       # 低 32 位 = 状态号，高 32 位 = 该步的 detail
    'g_diagnosticFileApi': 0x9de03e8,
    'g_hookCallbacks': 0x9dc1370,
    'g_HookInstallResults': 0x3f64e4,   # 16 字诊断数组（线格式，见 IsaacModRuntime_GetHookDiagnostics）
    'g_HookEnabled': 0x3f6540,
    'g_RenderPresentRelayState': 0x3f64d8,
    # 2026-09-16 卡上开关（一份包测多种配置，见 hook_manager.cpp 的那一节）：
    #   [0] 掩码：bit i = 第 i 个名字的 `<名字>.on` 在卡上（位序见 CARD_SWITCH_NAMES）
    #   [1] 通道：bit0 = 至少一次查询成功；bit1 = 至少一次查询失败（通道不可用）
    # 没这两个量就分不清"开关没读到"与"开关生效了但没用"——那会把整个二分带偏。
    'g_CardSwitchMask': 0x3f64d0,
    'g_CardSwitchChannel': 0x3f64cc,
    'g_PresentGotSlotTarget': 0x2721c0,
    # ---- 2026-09-14 夜间加：清单/挂点失败原因（这次读数的主角）----
    'g_DefaultManifestFailureWord': 0x3f64a8,   # 诊断字 [11]，打包格式见 mod_load_step.hpp
    'g_DefaultManifestFailureDetail': 0x3f64ac,  # 步骤字（1..4 失败、5 纯资源、6 自动发现）
    'g_DefaultManifestState': 0x3f64b0,
    # 清单 + 扫目录的合并结果（2026-09-21：「拷进 mods/ 就能用」）：
    #   [0] = 除清单之外多追加了几个目录；[1] = 合并状态码（0 = 成功）
    'g_AutoAppendedMods': 0x3f64a4,
    'g_AutoAppendStatus': 0x3f64a0,          # 0 未武装 1 已武装 2 安装中 3 就绪 4 失败
    'g_HookInstallFailureCode': 0x3f65ac,        # 入口中继后端转发的失败码（0 = 无失败）
    'g_HookInstallFailureSlot': 0x3f65b0,        # 第一个失败挂点 index+1（0 = 没有装失败的）
    'g_HookInstallInstalledCount': 0x3f65b4,     # 装好的挂点数（函数内静态，见 SYM_ELF_NAMES）
    # 贴图桥（2026-09-21）：转码失败计数（u32）与最近一次请求的路径（128 字节 C 串，
    # 零散读词后按 ASCII 解码——用来在真机上确认引擎传进回调的路径形状）。
    'image_pcx_bindings': 0x3f6420,
    # 模组数据容器（`ModPersistence::detail::g_cache`）的**尾部字段**：payload 是 16 KiB，
    # 尾部依次是 payloadLength(u64)/generation(u64)/loaded(u8)/exists(u8)。
    # 取值时用 `SYMS['g_ModDataCache'] + 0x4000`（见 build_requests 的 `mod_data_tail`）。
    'g_ModDataCache': 0x9ddbce8,
    'g_PendingGameStarted': 0x455d78,            # 待派发的"游戏开局"事件
    # ---- Lua 侧 ----
    'g_ModRegistered': 0x556a2c,       # 模组是否登记成功（1 字节；= Lua 真的跑起来了）
    # 回调派发次数（无 ELF 时的兜底偏移；有 ELF 时由 `sync_syms_from_elf()` 刷新）
    'g_UpdateCallbackEntries': 0x3f64e0,
    'g_RenderCallbackEntries': 0x3f64dc,
    # 自 journal（模块**自己**用 libnx fs 写 SD 的那条路）：会话状态与最后一条记录。
    # 这些量没有兜底偏移 —— 没有 ELF 就如实报"读不到"，绝不用别的地址凑。
    # 2026-09-16 多模组加载：登记成功的 Mod **个数**（清单里有几个 enabled，就该是几）。
    # 偏移由 `sync_syms_from_elf()` 按符号名自动同步，这里只是无 ELF 时的兜底值。
    'g_ModRegisteredCount': 0x556a28,
    'g_LastLuaErrorLength': 0x556900,
    'g_LastLuaErrorText': 0x556910,    # 256 字节文本
    'g_PostUpdateCount': 0x5564d0,
    # 回调派发计数（2026-09-18 新增，见 `callback_dispatcher.hpp`）：74 个 u32，下标就是 PC
    # `ModCallbacks` 的数值；相邻两个标量**分散**排布（链接器重排过），所以各读各的地址。
    # 无 ELF 时下面这三个兜底值不可信 —— 一律靠 `sync_syms_from_elf()` 按符号名同步。
    'g_CallbackDispatchCounts': 0x9dbcb78,
    'g_LastDispatchedCallbackId': 0x24f800,
    'g_CallbackDispatchGeneration': 0x9dbcb70,
    'g_CallbackRegistry': 0x238b50,     # 回调登记表：布局见下面的 `CALLBACK_REGISTRY_*` 常量
    # ---- 运行时读进来的文件内容（诊断"模组为什么算纯资源型"的关键）----
    'g_DefaultManifest': 0x376420,     # 上次读进来的 `manifest.json` 原文（512 KiB 缓冲）
    'g_DefaultEntry': 0x276420,         # 上次读进来的入口脚本原文（1 MiB 缓冲）
    # ---- 游戏开局中继的三格（相对**游戏模块**；来源 `runtime_constants.hpp` 的
    #      `kGameStart*` 常量。`--elf` 同步不会碰它们，因为它们是游戏模块的偏移、不是我们的符号）----
    'gamestart_saved_callsite': 0x3f92a4,
    'gamestart_new_callsite': 0x3f93f8,
    'gamestart_relay_slot': 0x68ccc0,
    # ---- 下面三条都相对**游戏模块**----
    'manager_update_entry': 0x3f8db8,  # `Manager::Update` 入口（该是原样 `ff4301d1...`）
    'manager_render_entry': 0x3f9684,  # `Manager::Render` 入口（该是原样 `ffc302d1...`）
    'present_callsite_offset': 0x3f9b40,  # `Manager::Render` 体内那次 `bl Present`
    'present_got_slot': 0xa9e488,      # Present 的 GOT 槽（应等于 运行时基址 + present_got_intercept）
    'present_target': 0x4f3014,        # `Present` 本体（期望值比对用）
    # ---- 游戏控制台（批次 121）----
    # 控制台**自报一份**状态面（`runtime/src/infrastructure/console/console_bridge.hpp` 的
    # `BridgeState`，18 个 u32）。没有兜底偏移：**只能靠 `--elf` 按符号名同步**，
    # 同步不到就如实报"读不到"，绝不用别的地址凑。
    'g_ConsoleState': 0x3f66c8,
    # ---- 批次 363（2026-10-04）：`ANM2::Load` 入口中继的状态面 ----
    # 这 8 个 u32 是"模组覆盖本体资源"这条链的常驻判据（用户 2026-10-04 明确要求补一条）：
    #   [0] relayState    0 未试 / 1 已装 / 2 未装
    #   [1] relayFailure  安装失败码（0 = 无）
    #   [2] callbackCount 中继被调次数（分母：0 = 这条路压根没走到）
    #   [3] resolverAsked 问解析器次数
    #   [4] staleFound    找到"本体旧条目"的次数
    #   [5] evicted       真正作废并回收的次数
    #   [6] lastPathHash  最近一条"答模组层"的路径哈希
    #   [7] mountListFlags ★ 2026-10-05（批次 368）从"对齐保留"改成有含义：bit0 = 引擎挂载点表里
    #                     没见过模组前缀；bit1 = 出现过"同一路径本会话已作废过 ⇒ 跳过"。
    #                     （★ 更正：下面原文写的 "[7] reserved 对齐保留（恒 0）" 已过时，原文保留在下面。）
    #   [7] reserved      对齐保留（恒 0）
    #   [8] callbackFirstTicks ★★★ 2026-10-06（批次 384）：**本条中继"第一次被调用"的时刻**
    #                     （`RuntimePerfTick()` 的低 32 位；0 = 一次都没被调过）。与 `g_EarlyMountState`
    #                     里 `Game::Init` 那个时刻**同源同单位** ⇒ 比大小就能判"引擎最初那次读
    #                     有没有走我们的中继"（晚于它 ⇒ 没走到 ⇒ 缓存被本体钉死）。
    #   [9] reservedAlign 对齐保留（恒 0）
    # 判读：`evicted > 0` 且 `staleFound > 0` ⇒ 这条链真的在修"旧缓存压住模组"。
    # 没有兜底偏移：**只能靠 `--elf` 按符号名同步**，同步不到就如实报"读不到"。
    'g_Anm2LoadOverrideState': 0x9de0570,
    # ---- 批次 378（2026-10-05）：**PC 的资源层重定向**（`mod_resource_redirect.*`）----
    # 这是"模组资源到底有没有被引擎看见"这一批的**直接证据面**（旧机制那几格挂载计数已结构性为 0）。
    # 结构体 = 10 个相邻 `uint32`（40 字节）+ 两条定长字符数组（查询 192B / 回答 224B）⇒ 456 字节。
    #   [0] published        名单发布过没有（1 = 已发布）
    #   [1] modCount         发布那一刻清单里的模组数
    #   [2] calls            ★ 这个缝一共被问过几次（**含**被跳过的那些；扣掉 [7] 才是真正探测的次数）
    #   [3] hits             ★ 其中**答了模组层路径**的次数（> 0 ⇒ 模组资源真的经这里进了引擎）
    #   [4] dlc3Hits         命中 `<模组>/resources-dlc3/` 的次数（PC 的第一优先）
    #   [5] plainHits        命中 `<模组>/resources/` 的次数（PC 的第二优先）
    #   [6] lastHitMod       最近一次命中的模组下标（`0xFFFFFFFF` = 一次都没命中）
    #   [7] skippedResolved  跳过"引擎自己已经解析成模组路径"的次数（请求带 `rom:/isaac_mods/`）
    #   [8] skippedTooLong   候选路径装不下的次数（正常情况下恒 0）
    #   [9] publishCount     清单被发布过几次
    # 判读：`hits > 0` ⇒ 这条重定向**真的在工作**（配合 `lastQuery`/`lastAnswer` 看具体那一条）；
    #       `calls > 0 且 hits == 0` ⇒ 在问、一条都没命中（先看那两条字符串与 `skippedTooLong`）。
    # 没有兜底偏移：**只能靠 `--elf` 按符号名同步**，同步不到就如实报"读不到"。
    'g_ModResourceRedirectState': 0x5b7c48,
    # ---- 批次 370（2026-10-05）：**提前注册模组挂载点**那一段的时间轴与计数 ----
    # 这 8 格（5 个 u64 tick + 3 个 u32）回答"我们比引擎第一次读共享路径早了没有"：
    #   [0]  workerEnteredTicks       worker 线程进入 `ModuleWorker` 的那一刻
    #   [1]  delayStartTicks          那 5 秒等待**开始**的那一刻（= 前置步骤结束）
    #   [2]  gameModuleFoundTicks     `ScanTargetModule()` 第一次认出游戏模块
    #   [3]  contentManagerFoundTicks `[游戏模块 + 0xAAC748]` 首次非 0
    #   [4]  earlyMountsDoneTicks     提前挂载跑完（含失败）的那一刻
    #   [5]  mountsAttempted          `RegisterMod` 调了几次
    #   [6]  mountsFailed             其中失败几次
    #   [7]  mountListHadModPrefix    挂完之后读引擎那张表：有 `isaac_mods` 前缀 = 1
    # tick 口径 = `cntpct_el0`（19.2 MHz）；**0 = 那一步没走到**（不是"发生在 tick 0"）。
    # 结构体是 **5 个相邻 u64 + 6 个 u32**（40 + 24 = 64 字节）⇒ 读 8 个 8 字节字：
    # 时间戳按字取（`first`），计数按**真正的 u32 下标**取（`u32_at`，见它的注释）。
    # 契约写在 `runtime/source/early_mod_mount_state.hpp`（字段顺序即内存顺序，两边同步改）。
    # 没有兜底偏移：**只能靠 `--elf` 按符号名同步**，同步不到就如实报"读不到"。
    'g_EarlyMountState': 0x5b7e10,
    # ---- 2026-10-05 排查（批次 371 上卡后："MC_POST_RENDER 本会话一次都没派发"）----
    # 这条链是**两条互斥的路**：Present 前中继（`state = Success` 时唯一的路）+ `Manager::Render`
    # 入口中继的**回退**（只有 `state != Success` 才走）。`state = Success` ⇒ 回退被抑制
    # ⇒ 只剩"Present 桩"这一条命脉，它一断就**静默归零、不崩不报错**。
    # 下面这几格就是把这根命脉逐环量出来（都是**只读**取一个 8 字节字）：
    #   g_RenderPresentRelayEntries —— `Present` 前那个派发函数**真的被进了几次**
    #                                  （0 = 桩那条路没跑到；>0 = 跑到了、问题在闸门或下游）
    #   g_DefaultCallbackGate       —— 渲染族独有的那道"默认回调闸门"（锁存：开过就一直开）
    #   g_LuaGameOwnerSlot / g_LuaGameIsPausedThunk / g_MusicGetCurrentMusicId
    #                               —— 闸门的三个输入（任一为 0 ⇒ 闸门恒闭，且**不报错**）
    #   g_RenderFrameManager        —— 本帧交给闸门的 `Manager*`（错的话音乐就绪判定恒假）
    # 契约写在 `runtime/source/hook_manager.cpp`（这些是文件作用域/匿名命名空间的量）。
    # 没有兜底偏移：**只能靠 `--elf` 按符号名同步**，同步不到就如实报"读不到"。
    'g_RenderPresentRelayEntries': 0x3f64d4,
    'g_DefaultCallbackGate': 0x3f649c,
    'g_LuaGameOwnerSlot': 0x3f64c0,
    'g_LuaGameIsPausedThunk': 0x3f64b8,
    'g_MusicGetCurrentMusicId': 0x556460,
    'g_RenderFrameManager': 0x3f6538,
    # 闸门"为什么不开"的最后两格（都是只读一个 8 字节字）：
    #   g_MusicResolveFailure        音乐对象/方法解析失败的理由码（2 = `manager+0x36068` 不可读、
    #                                3 = 方法绑定为 0、4 = 16 字节指纹不符；0 = 解析成功）
    #   g_DeepestGameOwnerObservation `ObserveGameIsPaused` 那条 owner 链**走到最深**的观察值
    #                                （成功 = 链读通；否则是"哪一跳断的"）
    'g_MusicResolveFailure': 0x5564d8,
    'g_DeepestGameOwnerObservation': 0x2721a8,
    # ---- 批次 408（2026-10-08）：`SFXManager:Play` 的真机探针（无条件计数；`extern "C"` 裸名）----
    # 回答"模组调了没 / 我们递进去了没 / 递进去的参数对不对 / 没递进去卡在哪一步"：
    #   g_SfxPlayCalls        —— 进了处理器且参数形状合法几次
    #   g_SfxPlayDelivered    —— 真的把调用递进引擎几次（Calls − Delivered = 被守卫挡下的）
    #   g_SfxPlayLast*        —— 最近一次递进去的实参（id/volume/frameDelay/loop/pitch/pan；
    #                            volume/pitch/pan 是 **float 位模式**，读数端按 float 解）
    #   g_SfxPlayLastFailure  —— 最近一次没递进去的失败码（0=没失败；1/2/3/4 同 g_MusicResolveFailure）
    # 契约写着"`Play` 是空实现、恒不生效"的旧说明在本批作废；这些格就是"从空实现变真调"的尺子。
    'g_SfxPlayCalls': 0x9dddd88,
    'g_SfxPlayDelivered': 0x9dddd80,
    'g_SfxPlayLastId': 0x9dddd78,
    'g_SfxPlayLastVolume': 0x9dddd70,
    'g_SfxPlayLastFrameDelay': 0x9dddd68,
    'g_SfxPlayLastLoop': 0x9dddd60,
    'g_SfxPlayLastPitch': 0x9dddd58,
    'g_SfxPlayLastPan': 0x9dddd50,
    'g_SfxPlayLastFailure': 0x9dddd48,
    # 2026-10-09生产ELF全表同步；游戏相对偏移保持原值。
    'entry_relay_use_active_item': 0x4994,
    'entry_relay_use_card': 0x4a58,
    'entry_relay_use_pill': 0x4aac,
    'entry_relay_game_exit': 0x4b08,
    'entry_relay_pickup_collision': 0x4ba0,
    'entry_relay_image_pcx_load': 0xb2d0,
    'entry_relay_image_mgr_load': 0xbf60,
    'entry_relay_get_mounted_path': 0xca10,
    'entry_relay_mod_loadconfigs': 0x7168,
    'entry_relay_anm2_load': 0xfea30,
    'entry_relay_entity_take_damage': 0x4c34,
    'entry_relay_entity_player_take_damage': 0x4c4c,
    'entry_relay_entity_pickup_take_damage': 0x4c64,
    'entry_relay_entity_slot_take_damage': 0x4c7c,
    'entry_relay_evaluate_items': 0x4c94,
    'entry_relay_entity_kill': 0x4d10,
    'entry_relay_npc_death_remove': 0x4d64,
    'entry_relay_game_end': 0x4dc0,
    'entry_relay_fire_tear': 0x4e00,
    'g_LastIsPaused': 0x9dc2f20,
    'g_ModLoadConfigsCalls': 0x3f65a8,
    'g_ModLoadConfigsEntriesSeen': 0x3f65a4,
    'g_ModLoadConfigsEnabledByUs': 0x3f65a0,
    'g_ModLoadConfigsDisabledByUs': 0x3f659c,
    'g_ModLoadConfigsDisabledKnown': 0x3f6598,
    'g_ModLoadConfigsStateLoaded': 0x3f6594,
    'g_ModLoadConfigsMatchedDisabled': 0x3f6590,
    'g_ModLoadConfigsEngineOff': 0x3f658c,
    'g_ModLoadConfigsWriteFailures': 0x3f6588,
    'g_ModLoadConfigsFirstPath': 0x3f6548,
    'g_ModToggleStateLoaded': 0x3f6544,
    'g_ModEngineScanAttempts': 0x5b0f8c,
    'g_ModEngineScanStage': 0x5b0f88,
    'g_ModEngineModEntries': 0x5b0f84,
    'g_ModEngineResolveFailures': 0x5b0f74,
    'g_ModEngineCostumeLoads': 0x5b0f80,
    'g_ModEngineMusicLoads': 0x5b0f7c,
    'g_ModEngineModDefaultsAnm2Loads': 0x5b0f78,
    'g_ModEnginePathResolveMisses': 0x5b0f70,
    'g_MusicEntryCountBefore': 0x5b0f6c,
    'g_MusicEntryCountAfter': 0x5b0f68,
    'g_CostumeCountBefore': 0x5b0f64,
    'g_CostumeCountAfter': 0x5b0f60,
    'g_ModEngineCostumeForm': 0x5b0f5c,
    'g_ModEngineMusicForm': 0x5b0f58,
    'g_ModEngineCostumeCalls': 0x5b0f54,
    'g_ModEngineMusicCalls': 0x5b0f50,
    'g_ModEngineResolvedCostumes': 0x5b0e50,
    'g_ModEngineResolvedMusic': 0x5b0d50,
    'g_ModEngineMusicLastEntryId': 0x5b0d40,
    'g_ModEngineMusicLastEntryRaw': 0x5b0d20,
    'image_pcx_diag': 0x4504c0,
    'g_throw_forensics': 0x9de04d0,
    'g_throw_wrapper': 0xfc6f0,
    'g_selfJournalServiceState': 0x9de017c,
    'g_selfJournalTotalRecords': 0x9de0184,
    'g_selfJournalLastMarker': 0x9de0180,
    'g_selfJournalLastResults': 0x9de0160,
    'g_LuaErrorHistory': 0x556500,
    'g_LuaErrorHistoryCount': 0x5564f8,
    'g_CallbackError': 0x556a18,
    'g_RequireFailureTotal': 0x455e10,
    'g_RequireLastFailureName': 0x455e18,
    'g_RequireLastFailureCode': 0x455e20,
    'g_RequireFirstFailureName': 0x455e28,
    'g_RequireFirstFailureCode': 0x455e30,
    'g_RequireErrorTail': 0x455e38,
    'g_RequireFailureDetail': 0x455e40,
    'g_Dispatchable': 0x9ddba98,
    'g_Unhooked': 0x9ddba90,
    'g_InputIsActionTriggeredThunk': 0x556400,
    'g_InputActionQueriedMask': 0x9dc3798,
    'g_TouchPointerInitState': 0x3f668c,
    'g_TouchPointerScanAttempts': 0x3f6688,
    'g_TouchPointerShmemLow': 0x3f6684,
    'g_TouchPointerShmemHigh': 0x3f6680,
    'g_TouchPointerSegmentsScanned': 0x3f667c,
    'g_TouchPointerPollFrames': 0x3f6668,
    'g_TouchPointerTouchFrames': 0x3f6664,
    'g_TouchPointerLastRawX': 0x3f6660,
    'g_TouchPointerLastRawY': 0x3f665c,
    'g_TouchPointerLastCount': 0x3f6658,
    'g_TouchPointerLifoBufferCount': 0x3f6678,
    'g_TouchPointerLifoTail': 0x3f6674,
    'g_TouchPointerLifoCount': 0x3f6670,
    'g_TouchPointerRejectedMappings': 0x3f666c,
    'g_TouchPointerLastSampling': 0x3f6654,
    'g_TouchPointerLastEntryIndex': 0x3f6650,
    'g_MinimapTouchGateState': 0x272198,
    'g_MinimapTouchGateApplied': 0x272190,
    'g_MinimapTouchGateGuardMismatch': 0x272188,
    'g_MinimapTouchGateFailureCode': 0x272180,
    'g_InputActionTriggeredMask': 0x9dc37b8,
    'g_InputEdgeCounts': 0x9dc3658,
    'g_InputReleaseRunPeak': 0x9dc35d8,
    'g_InputEdgeGapMin': 0x9dc3558,
    'g_InputEdgeGapLast': 0x9dc34d8,
    'g_InputSampleFrame': 0x265f68,
    'g_InputSampleCalls': 0x9dc2f50,
    'g_InputSampleCodes': 0x9dc2f48,
    'g_InputSampleDevices': 0x9dc2f40,
    'g_InputSampleFailures': 0x9dc2f38,
    'g_InputActionTriggeredMaskOther': 0x9dc37b0,
    'g_InputActionPressedMask': 0x9dc37a8,
    'g_InputActionPressedMaskOther': 0x9dc37a0,
    'g_InputLastController': 0x26af98,
    'g_InputPressedControllerMask': 0x9dc3780,
    'g_InputTriggeredControllerMask': 0x9dc3788,
    'g_InputLastActionCode': 0x26afa0,
    'g_InputLastActionResult': 0x9dc3790,
    'g_InputButtonPressedMask': 0x9dc3778,
    'g_InputButtonQueriedMask': 0x9dc3770,
    'g_InputIsButtonPressed': 0x556418,
    'g_InputGetButtonValue': 0x556410,
    'g_InputControllerMapPcId': 0x265f90,
    'g_InputControllerMapNsId': 0x265f88,
    'g_InputControllerMapOutcome': 0x265f80,
    'g_InputControllerMapFallbacks': 0x9dc3768,
    'g_InputActionMapLuaCode': 0x265f78,
    'g_InputActionMapEngineCode': 0x265f70,
    'g_InputActionMapAbsent': 0x9dc3760,
    'g_EntityFieldWrites': 0x9ddb970,
    'g_EntityFieldWriteRejected': 0x9ddb968,
    'g_LastEntityFieldWriteName': 0x9ddb960,
    'g_SeedsEffectWriteAttempts': 0x9dc2f10,
    'g_InputActionAskedFrame': 0x9dc3458,
    'g_InputActionAskedKind': 0x9dc33d8,
    'g_InputActionAskedController': 0x9dc3358,
    'g_InputActionAskedAnswer': 0x9dc32d8,
    'g_InputButtonEdgeCounts': 0x9dc3258,
    'g_InputButtonAskedFrame': 0x9dc31d8,
    'g_InputButtonAskedKind': 0x9dc3158,
    'g_InputButtonAskedController': 0x9dc30d8,
    'g_InputButtonAskedAnswer': 0x9dc3058,
    'g_InputActionHeldFrame': 0x9dc2fd8,
    'g_InputButtonTriggeredFrame': 0x9dc2f58,
    'g_ButtonEdge': 0x260ee8,
    'g_ModMenuLastCode': 0x9dddd30,
    'g_ModMenuMilestones': 0x9dddd40,
    'g_ModMenuReportCount': 0x9dddd38,
    'g_FontDrawCalls': 0x9dc2f08,
    'g_FontDrawBytes': 0x9dc2f00,
    'g_FontStorageAllocations': 0x9dc2ec8,
    'g_FontStorageLive': 0x9dc2ec0,
    'g_FontStorageLivePeak': 0x9dc2eb8,
    'g_FontLoadCalls': 0x9dc2ef8,
    'g_FontLoadResult': 0x9dc2ef0,
    'g_OptionsProbeExists': 0x5b0fac,
    'g_OptionsProbeStatus': 0x5b0fa8,
    'g_OptionsProbeReadStatus': 0x5b0fa4,
    'g_OptionsProbeSize': 0x5b0fa0,
    'g_OptionsProbeEnableMods': 0x5b0f9c,
    'g_OptionsProbeHeadLow': 0x5b0f98,
    'g_OptionsProbeHeadHigh': 0x5b0f94,
    'g_ModsGateRestores': 0x5b0f90,
    'g_IsaacRoomIdxCalls': 0x9ddde10,
    'g_IsaacRoomIdxEmpty': 0x9ddde08,
    'g_IsaacRoomIdxRejectedFootprint': 0x9ddde00,
    'g_IsaacRoomIdxEngineMapUsed': 0x9ddddf8,
    'g_IsaacRoomIdxLastRequest': 0x26c8b8,
    'g_IsaacRoomIdxLastResolvedGrid': 0x26c8b0,
    'g_IsaacRoomIdxLastResolvedSafe': 0x26c8a8,
    'g_IsaacRoomIdxLastResolvedList': 0x26c8a0,
    'g_IsaacRoomIdxLastRejectRequest': 0x26c898,
    'g_IsaacRoomIdxLastRejectAnchor': 0x26c890,
    'g_IsaacRoomIdxLastRejectDeltaBias': 0x26c888,
    'g_IsaacRoomIdxMapSlotRejected': 0x9ddddf0,
    'g_IsaacRoomIdxAccepted': 0x9dddde8,
    'g_IsaacRoomIdxSlotNegative': 0x9dddde0,
    'g_IsaacRoomIdxUnallocatedAnchor': 0x9ddddd8,
    'g_IsaacRoomIdxSlotBeyondCount': 0x9ddddd0,
    'g_IsaacRoomIdxLastAcceptedRequest': 0x26c880,
    'g_IsaacRoomIdxLastAcceptedSlot': 0x26c878,
    'g_IsaacRoomIdxLastAcceptedAnchor': 0x26c870,
    'g_IsaacRoomIdxLastAcceptedSafe': 0x26c868,
    'g_IsaacRoomIdxNativeCalls': 0x9ddddc8,
    'g_IsaacRoomIdxNativeFallbacks': 0x9ddddc0,
    'g_IsaacRoomIdxNativeLastIndex': 0x26c860,
    'g_IsaacRoomIdxNativeLastDimension': 0x26c858,
    'g_RuntimePerfCallbackCalls': 0x561298,
    'g_RuntimePerfCallbackTicks': 0x561290,
    'g_RuntimePerfCallbackMaxTicks': 0x561288,
    'g_RuntimePerfSyscalls': 0x561280,
    'g_RuntimePerfSyscallTicks': 0x561278,
    'g_RuntimePerfCallbackBuckets': 0x560678,
    'g_RuntimePerfBucketOverflow': 0x560670,
    'g_RuntimePerfApiBuckets': 0x55a670,
    'g_RuntimePerfApiBucketOverflow': 0x55a668,
    'g_RuntimePerfApiTotalCalls': 0x55a660,
    'g_RuntimePerfApiTotalTicks': 0x55a658,
    'g_RuntimePerfProfileBuckets': 0x556a58,
    'g_RuntimePerfProfileSamples': 0x556a50,
    'g_RuntimePerfProfileOverflow': 0x556a48,
    'g_RuntimePerfTickCostTicks': 0x556a40,
    'mod_menu_state': 0x24dfc0,
    'entry_relay_familiarcollision': 0x4ed8,
    'entry_relay_npccollision': 0x4f6c,
    'entry_relay_playercollision': 0x5000,
    'entry_relay_tearcollision': 0x5094,
    'entry_relay_projectilecollision': 0x5128,
    'entry_relay_knifecollision': 0x51bc,
    'entry_relay_bombcollision': 0x5260,
    'entry_relay_npcrender': 0x52f4,
    'entry_relay_itempoolgetpill': 0x5334,
    'entry_relay_itempoolgetpilleffect': 0x5374,
    'entry_relay_gamedevolveenemy': 0x53bc,
    'npc_ai_gotslot_intercept': 0x251c,
    'npc_ai_gotslot_target': 0x2721b8,
    'entry_relay_gamespawnex': 0x540c,
    # 2026-10-10 EID颜色修复包：冻结ELF完整同步，补全此前由运行时动态解析的入口。
    'entity_remove_pointer_callback': 0x60e40,
    'g_CallbackDiagnosticViewIncomplete': 0x9dc2e90,
    'g_CallbackDiagnosticViewOverflow': 0x9dc2e8c,

})
#: 上表里"属于**我们运行时模块**"的那些键 → 它们在本地 ELF 里的**精确符号名**。
#: 有这张表，偏移就不必再靠人手抄：`sync_syms_from_elf()` 每次读数前直接问 ELF。
#: 不在表里的键（`manager_update_entry` 那几条）是**游戏模块**的常量，与我们的重建无关，保持原值。

SYM_ELF_NAMES = {
    'shader_screen_intercept': 'IsaacModRuntime_ShaderScreenIntercept',
    'entity_remove_pointer_callback': 'IsaacModRuntime_EntityRemovePointerIntercept',
    'identity': 'IsaacModRuntime_GetRuntimeIdentity',
    'exl_main': 'exl_main',
    'manifest_install': '_Z28TryInstallDefaultManifestModRK12TargetModule',
    'entry_relay_update': 'EntryRelayManagerUpdateCallback',
    'entry_relay_render': 'EntryRelayManagerRenderCallback',
    'entry_relay_collectible': 'EntryRelayPreGetCollectibleCallback',
    'entry_relay_rebuild': 'EntryRelayRebuildMountPointsCallback',
    # 批次 102 的四个事件中继回调（`g_hookCallbacks` 里应当出现的四个新指针）。
    'entry_relay_use_active_item': 'EntryRelayUseActiveItemCallback',
    'entry_relay_use_card': 'EntryRelayUseCardCallback',
    'entry_relay_use_pill': 'EntryRelayUsePillCallback',
    'entry_relay_game_exit': 'EntryRelayGameExitCallback',
    'entry_relay_pickup_collision': 'EntryRelayPickupCollisionCallback',
    'entry_relay_image_pcx_load': 'EntryRelayImagePcxLoadCallback',
    'entry_relay_image_mgr_load': 'EntryRelayImageManagerLoadFileCallback',
    'entry_relay_get_mounted_path': 'EntryRelayContentGetMountedFilePathCallback',
    # 批次 147（2026-09-26）：引擎那条"模组 content 加载"路的闸门
    # （`ModManager::LoadConfigs` 入口中继）—— 回调 + 九个埋点。
    # 埋点契约写在 `hook_manager.cpp` 那段 `g_ModLoadConfigs*` 的注释里，两边必须同步改。
    'entry_relay_mod_loadconfigs': 'EntryRelayModManagerLoadConfigsCallback',
    # 批次 363（2026-10-04）：`ANM2::Load` 入口中继 —— 回调 + 状态面。
    # 状态面契约写在 `runtime/source/anm2_load_override_hook.hpp` 的 `Anm2LoadOverrideState`，
    # 两边必须同步改（字段顺序即内存顺序）。
    'entry_relay_anm2_load': 'EntryRelayAnm2LoadCallback',
    # 批次 396（2026-10-07）：`MC_ENTITY_TAKE_DMG` 的四条入口中继 + `MC_EVALUATE_CACHE`。
    # 四条受伤共用一个派发函数，但**各有各的回调符号**（`BindingOf` 里按 HookId 取），
    # 所以这里要逐条登记（与 `RegisterEntryRelayCallbacks()` 的名字逐字一致）。
    'entry_relay_entity_take_damage': 'EntryRelayEntityTakeDamageCallback',
    'entry_relay_entity_player_take_damage': 'EntryRelayEntityPlayerTakeDamageCallback',
    'entry_relay_entity_pickup_take_damage': 'EntryRelayEntityPickupTakeDamageCallback',
    'entry_relay_entity_slot_take_damage': 'EntryRelayEntitySlotTakeDamageCallback',
    'entry_relay_evaluate_items': 'EntryRelayEvaluateItemsCallback',
    # 批次 397（2026-10-07）：补全回调（第 2 批）的三条（`MC_POST_ENTITY_KILL` /
    # `MC_POST_NPC_DEATH` / `MC_POST_GAME_END`）。与 `RegisterEntryRelayCallbacks()` 逐字一致。
    'entry_relay_entity_kill': 'EntryRelayEntityKillCallback',
    'entry_relay_npc_death_remove': 'EntryRelayNpcDeathRemoveCallback',
    'entry_relay_game_end': 'EntryRelayGameEndCallback',
    'entry_relay_fire_tear': 'EntryRelayFireTearCallback',
    'entry_relay_familiarcollision': 'EntryRelayFamiliarCollisionCallback',
    'entry_relay_npccollision': 'EntryRelayNpcCollisionCallback',
    'entry_relay_playercollision': 'EntryRelayPlayerCollisionCallback',
    'entry_relay_tearcollision': 'EntryRelayTearCollisionCallback',
    'entry_relay_projectilecollision': 'EntryRelayProjectileCollisionCallback',
    'entry_relay_knifecollision': 'EntryRelayKnifeCollisionCallback',
    'entry_relay_bombcollision': 'EntryRelayBombCollisionCallback',
    'entry_relay_gamespawnex': 'EntryRelayGameSpawnExCallback',
    'entry_relay_npcrender': 'EntryRelayNpcRenderCallback',
    'entry_relay_itempoolgetpill': 'EntryRelayItemPoolGetPillCallback',
    'entry_relay_itempoolgetpilleffect': 'EntryRelayItemPoolGetPillEffectCallback',
    'entry_relay_gamedevolveenemy': 'EntryRelayGameDevolveEnemyCallback',
    'npc_ai_gotslot_intercept': 'IsaacModRuntime_NpcUpdateAiGotSlotIntercept',
    'npc_ai_gotslot_target': 'g_NpcUpdateAiGotSlotTarget',
    # ★ 它是 C++ 命名空间里的变量 ⇒ ELF 里是 mangled 名（`nm` 可核对：32 字节 = 8 个 u32）。
    'g_Anm2LoadOverrideState': '_ZN5isaac7runtime6bridge23g_Anm2LoadOverrideStateE',
    # 批次 378（2026-10-05）：PC 的资源层重定向的状态面（10 个 u32 + 两条定长串）。
    # 同样是 C++ 命名空间里的变量 ⇒ ELF 里是 mangled 名（`nm` 可核对：456 字节）。
    'g_ModResourceRedirectState': '_ZN5isaac7runtime6bridge26g_ModResourceRedirectStateE',
    # 批次 370 起、批次 371 改语义（2026-10-05）：让模组那一层早于引擎第一次读的那一段的状态面。
    # ★ 同样是 C++ 命名空间里的变量 ⇒ ELF 里是 mangled 名（`nm` 可核对：64 字节 = 5 个 u64 + 6 个 u32）。
    'g_EarlyMountState': '_ZN5isaac7runtime10earlymount17g_EarlyMountStateE',
    # 2026-10-05 排查：渲染回调那条命脉的逐环判据（都在 `hook_manager.cpp` 的匿名命名空间里
    # ⇒ ELF 里是 `_ZN12_GLOBAL__N_1L<len><name>E` 这一族）。
    'g_RenderPresentRelayEntries': '_ZN12_GLOBAL__N_1L27g_RenderPresentRelayEntriesE',
    'g_DefaultCallbackGate': '_ZN12_GLOBAL__N_1L21g_DefaultCallbackGateE',
    'g_LuaGameOwnerSlot': '_ZN12_GLOBAL__N_1L18g_LuaGameOwnerSlotE',
    'g_LuaGameIsPausedThunk': '_ZN12_GLOBAL__N_1L22g_LuaGameIsPausedThunkE',
    # ★ 2026-10-08（排查 MCM 打不开）：`Game:IsPaused()` **最后一次返回了什么**。
    #   MCM 的开菜单判定是 `if ControlsEnabled and not isPaused then …`，
    #   而它只在**闸内**才问 `IsButtonTriggered(13, i)` ⇒ 如果我们这一格返回 true，
    #   MCM 会**整段不跑**（不出菜单、也不响），且我们看不到任何 13 号的询问 —— 与现场完全一致。
    #   所以这一格是"闸门"的直接读数：0 = 最后一次返回 false，1 = true。
    #   （写入点：`game_api.cpp` 的 `GameIsPaused()` ⇒ `g_LastIsPaused.store(...)`。）
    'g_LastIsPaused': '_ZN5isaac7runtime14g_LastIsPausedE',
    # `g_MusicGetCurrentMusicId` 在 `LuaRuntime` 的匿名命名空间里 ⇒ 多一层命名空间前缀。
    'g_MusicGetCurrentMusicId': '_ZN10LuaRuntime12_GLOBAL__N_1L24g_MusicGetCurrentMusicIdE',
    'g_RenderFrameManager': '_ZN12_GLOBAL__N_1L20g_RenderFrameManagerE',
    # 闸门最后两格（同在 `LuaRuntime` / `game_observer.cpp` 的匿名命名空间里）。
    'g_MusicResolveFailure': '_ZN10LuaRuntime12_GLOBAL__N_1L21g_MusicResolveFailureE',
    # ---- 批次 408（2026-10-08）：`SFXManager:Play` 探针（`extern "C"` ⇒ ELF 里就是裸名）----
    # ★ 放**主表**而不是探针包专属那张：它们是**无条件写**的（同 `g_MusicResolveFailure`），
    #   生产 ELF 里也解析得到 ⇒ 属于"主表每一项都要能解析"的守门范围。
    'g_SfxPlayCalls': 'g_SfxPlayCalls',
    'g_SfxPlayDelivered': 'g_SfxPlayDelivered',
    'g_SfxPlayLastId': 'g_SfxPlayLastId',
    'g_SfxPlayLastVolume': 'g_SfxPlayLastVolume',
    'g_SfxPlayLastFrameDelay': 'g_SfxPlayLastFrameDelay',
    'g_SfxPlayLastLoop': 'g_SfxPlayLastLoop',
    'g_SfxPlayLastPitch': 'g_SfxPlayLastPitch',
    'g_SfxPlayLastPan': 'g_SfxPlayLastPan',
    'g_SfxPlayLastFailure': 'g_SfxPlayLastFailure',
    'g_DeepestGameOwnerObservation': '_ZN12_GLOBAL__N_1L29g_DeepestGameOwnerObservationE',
    'g_ModLoadConfigsCalls': 'g_ModLoadConfigsCalls',
    'g_ModLoadConfigsEntriesSeen': 'g_ModLoadConfigsEntriesSeen',
    'g_ModLoadConfigsEnabledByUs': 'g_ModLoadConfigsEnabledByUs',
    'g_ModLoadConfigsDisabledByUs': 'g_ModLoadConfigsDisabledByUs',
    'g_ModLoadConfigsDisabledKnown': 'g_ModLoadConfigsDisabledKnown',
    'g_ModLoadConfigsStateLoaded': 'g_ModLoadConfigsStateLoaded',
    'g_ModLoadConfigsMatchedDisabled': 'g_ModLoadConfigsMatchedDisabled',
    'g_ModLoadConfigsEngineOff': 'g_ModLoadConfigsEngineOff',
    'g_ModLoadConfigsWriteFailures': 'g_ModLoadConfigsWriteFailures',
    'g_ModLoadConfigsFirstPath': 'g_ModLoadConfigsFirstPath',
    'g_ModToggleStateLoaded': 'g_ModToggleStateLoaded',
    # ---- 批次 148（2026-09-26）：**我们自己喊一次**引擎那条"扫模组目录 + 加载 content"的路 ----
    # 契约写在 `mod_menu_native.cpp` 文件顶层那段 `g_ModEngine*` 的注释里，两边必须同步改。
    # 触发点是"用户打开模组页"那一刻（批次 143/144 放在"每帧第一帧"各崩一次，见改动日志 §030/§032）。
    'g_ModEngineScanAttempts': 'g_ModEngineScanAttempts',
    'g_ModEngineScanStage': 'g_ModEngineScanStage',
    'g_ModEngineModEntries': 'g_ModEngineModEntries',
    'g_ModEngineResolveFailures': 'g_ModEngineResolveFailures',
    'g_ModEngineCostumeLoads': 'g_ModEngineCostumeLoads',
    'g_ModEngineMusicLoads': 'g_ModEngineMusicLoads',
    # ★ 批次 409（2026-10-08）：引擎 `ModManager::LoadConfigs` 尾部那一步
    # （`ANM2::Load("gfx/ui/mod_defaults.anm2", true)` 到 `ModManager+0x368`）被我们调了几次。
    # **正常 = 1**；0 = 那一步没做 ⇒ 暂停屏画模组道具（id ≥ 733）时会写 `0x80` 崩。
    'g_ModEngineModDefaultsAnm2Loads': 'g_ModEngineModDefaultsAnm2Loads',
    'g_ModEnginePathResolveMisses': 'g_ModEnginePathResolveMisses',
    'g_MusicEntryCountBefore': 'g_MusicEntryCountBefore',
    'g_MusicEntryCountAfter': 'g_MusicEntryCountAfter',
    'g_CostumeCountBefore': 'g_CostumeCountBefore',
    'g_CostumeCountAfter': 'g_CostumeCountAfter',
    # ---- 批次 149b（2026-09-26 深夜）：路径口径留证 ----------------------------------------
    # 148d 真机读数：两个加载器**各被调 1 次**、两个容器**一条没涨** ⇒ 只可能是"喂进去的路径
    # 形态引擎的文件层不认"。反汇编引擎自己的 `ModManager::LoadConfigs` 得到它的写法是
    # `裸文件名 → ModEntry::GetContentPath(名) → FileManager::Exists(路径) → 加载器(路径, ModEntry*)`
    # ⇒ 路径是**应用根相对**的；而 `GetMountedFilePath` 返回带 `rom:/` 的完整路径。
    # 下面四格回答"哪种口径能用"与"解析回来的到底是不是模组自己的那个文件"。
    'g_ModEngineCostumeForm': 'g_ModEngineCostumeForm',
    'g_ModEngineMusicForm': 'g_ModEngineMusicForm',
    'g_ModEngineCostumeCalls': 'g_ModEngineCostumeCalls',
    'g_ModEngineMusicCalls': 'g_ModEngineMusicCalls',
    'g_ModEngineResolvedCostumes': 'g_ModEngineResolvedCostumes',
    'g_ModEngineResolvedMusic': 'g_ModEngineResolvedMusic',
    # ★ 自证条目布局：最后一条的编号（`+0x00`）与名字那 32 字节原始串（`+0x08` 起）。
    #   解码（libc++ 短/长串）放在读数侧做，运行时只搬字节。
    'g_ModEngineMusicLastEntryId': 'g_ModEngineMusicLastEntryId',
    'g_ModEngineMusicLastEntryRaw': 'g_ModEngineMusicLastEntryRaw',
    # 批次 148：曲目名反查（`Isaac.GetMusicIdByName`）的现场。
    # ★ `g_IsaacMusicIdTableCount` 就是"模组的 `content/music.xml` 进引擎了没有"的直接读数
    #   （真机基线 119；模组的 music.xml 再加 2 条 ⇒ 121）；`0xFFFFFFFF` = 链读不到。
    # 贴图桥：**唯一**诊断入口（固定布局结构体，见 hook_manager.cpp 的 ImagePcxDiagnostics）。
    'image_pcx_diag': '_ZN12_GLOBAL__N_1L14g_imagePcxDiagE',
    'image_pcx_bindings': '_ZN12_GLOBAL__N_1L18g_ImagePcxBindingsE',
    # L4 钩子隔离·甲案（2026-09-29 批次 196）：C++ 异常的**抛出位置**记录。
    # 固定布局结构体 `ThrowForensics`（throwCount / reserved0 / lastThrowFrom / lastThrowType /
    # firstThrowFrom），字段只许往后加。`throwCount > 0` = 这一局抛过 C++ 异常。
    'g_throw_forensics': '_ZN5isaac7runtime9forensics16g_ThrowForensicsE',
    'g_throw_wrapper': '__wrap___cxa_throw',
    'present_got_intercept': 'IsaacModRuntime_PresentGotSlotIntercept',
    'g_runtimeSelfAddress': 'g_runtimeSelfAddress',
    'g_sequence': '_ZN12_GLOBAL__N_1L10g_sequenceE',
    'g_stateDetail': '_ZN12_GLOBAL__N_1L13g_stateDetailE',
    'g_diagnosticFileApi': '_ZN12_GLOBAL__N_1L19g_diagnosticFileApiE',
    'g_hookCallbacks': '_ZN5isaac7runtime12_GLOBAL__N_1L15g_hookCallbacksE',
    'g_HookInstallResults': '_ZN12_GLOBAL__N_1L20g_HookInstallResultsE',
    'g_HookEnabled': '_ZN12_GLOBAL__N_1L13g_HookEnabledE',
    'g_RenderPresentRelayState': '_ZN12_GLOBAL__N_1L25g_RenderPresentRelayStateE',
    'g_CardSwitchMask': '_ZN12_GLOBAL__N_1L16g_CardSwitchMaskE',
    'g_CardSwitchChannel': '_ZN12_GLOBAL__N_1L19g_CardSwitchChannelE',
    'g_PresentGotSlotTarget': 'g_PresentGotSlotTarget',
    'g_DefaultManifestFailureWord': '_ZN12_GLOBAL__N_1L28g_DefaultManifestFailureWordE',
    'g_DefaultManifestFailureDetail': '_ZN12_GLOBAL__N_1L30g_DefaultManifestFailureDetailE',
    'g_DefaultManifestState': '_ZN12_GLOBAL__N_1L22g_DefaultManifestStateE',
    'g_AutoAppendedMods': '_ZN12_GLOBAL__N_1L18g_AutoAppendedModsE',
    'g_AutoAppendStatus': '_ZN12_GLOBAL__N_1L18g_AutoAppendStatusE',
    'g_HookInstallFailureCode': '_ZZN5isaac7runtime22HookInstallFailureCodeEvE5value',
    'g_HookInstallFailureSlot': '_ZZN5isaac7runtime22HookInstallFailureSlotEvE5value',
    'g_HookInstallInstalledCount': '_ZZN5isaac7runtime25HookInstallInstalledCountEvE5value',
    'g_ModDataCache': '_ZN14ModPersistence6detail7g_cacheE',
    # API 调用序列掩码（`api_sequence_probe.hpp` 的 `detail::ApiSequence()` 里的函数内静态）：
    # "哪些 API 真被调用过"的直接证据 —— 比"某个功能看起来没生效"这种间接判断硬得多。
    # 2026-09-19 加：GoodTrip 装上后界面不出现，需要先回答"它到底有没有走到 `Sprite:Render`"。
    'g_PendingGameStarted': '_ZN10LuaRuntime12_GLOBAL__N_1L20g_PendingGameStartedE',
    'g_ModRegistered': '_ZN10LuaRuntime12_GLOBAL__N_1L15g_ModRegisteredE',
    # 2026-09-16：回调派发次数的**真身**（数组里那两个槽是错的，见 `legacy` 的注释）。
    'g_UpdateCallbackEntries': '_ZN12_GLOBAL__N_1L23g_UpdateCallbackEntriesE',
    'g_RenderCallbackEntries': '_ZN12_GLOBAL__N_1L23g_RenderCallbackEntriesE',
    # 自 journal：0=没试过、1=sm+fs 会话起来了、2=服务初始化失败。
    'g_selfJournalServiceState': '_ZN12self_journal14g_serviceStateE',
    'g_selfJournalTotalRecords': '_ZN12self_journal14g_totalRecordsE',
    'g_selfJournalLastMarker': '_ZN12self_journal12g_lastMarkerE',
    'g_selfJournalLastResults': '_ZN12self_journal13g_lastResultsE',
    'g_ModRegisteredCount': '_ZN10LuaRuntime12_GLOBAL__N_1L20g_ModRegisteredCountE',
    'g_LastLuaErrorLength': '_ZN10LuaRuntime12_GLOBAL__N_1L20g_LastLuaErrorLengthE',
    'g_LastLuaErrorText': '_ZN10LuaRuntime12_GLOBAL__N_1L18g_LastLuaErrorTextE',
    # 批次 052（2026-09-19）：最近若干条 Lua 错误的**环形历史**。只有一格时
    # A 模组的错会盖掉 B 模组的错（今天就因此兜了三轮），所以额外读这一块。
    'g_LuaErrorHistory': '_ZN10LuaRuntime12_GLOBAL__N_1L17g_LuaErrorHistoryE',
    'g_LuaErrorHistoryCount': '_ZN10LuaRuntime12_GLOBAL__N_1L22g_LuaErrorHistoryCountE',
    'g_PostUpdateCount': '_ZN10LuaRuntime12_GLOBAL__N_1L17g_PostUpdateCountE',
    # 回调派发计数（2026-09-18）。这三个符号**故意**不在匿名命名空间里（见
    # `callback_dispatcher.hpp` 的说明）：名字短、不随编译器版本变。
    'g_CallbackDispatchCounts': '_ZN5isaac7runtime24g_CallbackDispatchCountsE',
    'g_LastDispatchedCallbackId': '_ZN5isaac7runtime26g_LastDispatchedCallbackIdE',
    'g_CallbackDispatchGeneration': '_ZN5isaac7runtime28g_CallbackDispatchGenerationE',
    'g_CallbackRegistry': '_ZN10LuaRuntime12_GLOBAL__N_1L18g_CallbackRegistryE',
    'g_DefaultManifest': '_ZN12_GLOBAL__N_1L17g_DefaultManifestE',
    'g_DefaultEntry': '_ZN12_GLOBAL__N_1L14g_DefaultEntryE',
    # ---- 错误通道探针（`tools/probe_lua_error_channel.py`）也用这张表 ----
    'g_CallbackError': '_ZN10LuaRuntime12_GLOBAL__N_1L15g_CallbackErrorE',
    'g_RequireFailureTotal': '_ZN10LuaRuntime12_GLOBAL__N_1L21g_RequireFailureTotalE',
    'g_RequireLastFailureName': '_ZN10LuaRuntime12_GLOBAL__N_1L24g_RequireLastFailureNameE',
    'g_RequireLastFailureCode': '_ZN10LuaRuntime12_GLOBAL__N_1L24g_RequireLastFailureCodeE',
    'g_RequireFirstFailureName': '_ZN10LuaRuntime12_GLOBAL__N_1L25g_RequireFirstFailureNameE',
    'g_RequireFirstFailureCode': '_ZN10LuaRuntime12_GLOBAL__N_1L25g_RequireFirstFailureCodeE',
    'g_RequireErrorTail': '_ZN10LuaRuntime12_GLOBAL__N_1L18g_RequireErrorTailE',
    'g_RequireFailureDetail': '_ZN10LuaRuntime12_GLOBAL__N_1L22g_RequireFailureDetailE',
    'g_Dispatchable': '_ZN10LuaRuntime12_GLOBAL__N_1L14g_DispatchableE',
    'g_Unhooked': '_ZN10LuaRuntime12_GLOBAL__N_1L10g_UnhookedE',
    # ---- B1 写通道探针（`runtime/source/probe/engine_file_write.cpp`，2026-09-16 第三轮）----
    # 为什么要有这一步：偏移表是手抄的，而**改任何一个编译单元都会让 bss 整体挪位**；
    # 探针从构建里删掉之后，`sync_syms_from_elf` 会自动把这些名字从表里剔掉并打印提示。
    # ---- 模组开关菜单的诊断面（2026-09-16）----
    # 菜单脚本要读键（`Input.*`）与画字（`Font.*`）：这两个绑定在真机上此前**从没被验过**，
    # 所以"按了没反应"的第一件事就是看这几个量。
    'g_InputIsActionTriggeredThunk': '_ZN10LuaRuntime12_GLOBAL__N_1L24g_InputIsActionTriggeredE',
    # 菜单/输入诊断量（名字按 `nm` 直出，长度前缀由脚本核对）
    'g_InputActionQueriedMask': '_ZN5isaac7runtime24g_InputActionQueriedMaskE',
    # 批次 192：触摸屏 → 指针。这一组是"触摸到底通没通"的唯一现场证据
    #（★ 本批**故意不做坐标换算**：PC 的 `gameCoords` 两种口径只能真机量，
    #  先原样交出原始坐标 —— `g_TouchPointerLastRawX/Y`）。
    'g_TouchPointerInitState': '_ZN5isaac7runtime23g_TouchPointerInitStateE',
    'g_TouchPointerScanAttempts': '_ZN5isaac7runtime26g_TouchPointerScanAttemptsE',
    'g_TouchPointerShmemLow': '_ZN5isaac7runtime22g_TouchPointerShmemLowE',
    'g_TouchPointerShmemHigh': '_ZN5isaac7runtime23g_TouchPointerShmemHighE',
    'g_TouchPointerSegmentsScanned': '_ZN5isaac7runtime29g_TouchPointerSegmentsScannedE',
    'g_TouchPointerPollFrames': '_ZN5isaac7runtime24g_TouchPointerPollFramesE',
    'g_TouchPointerTouchFrames': '_ZN5isaac7runtime25g_TouchPointerTouchFramesE',
    'g_TouchPointerLastRawX': '_ZN5isaac7runtime22g_TouchPointerLastRawXE',
    'g_TouchPointerLastRawY': '_ZN5isaac7runtime22g_TouchPointerLastRawYE',
    'g_TouchPointerLastCount': '_ZN5isaac7runtime23g_TouchPointerLastCountE',
    # 批次 193：★ "这次真的认出 lifo 了吗"的证据。批次 192 只有上面那一组，于是**一块零页**
    # 被认成触摸屏共享内存（读数报"找到共享内存"、基址 0x4cc64f000，`--read` 一看整段全 0）。
    # `buffer_count` **必须是 17**（建表时写死、与有没有触摸无关）—— 零页在这里必然露馅。
    'g_TouchPointerLifoBufferCount': '_ZN5isaac7runtime29g_TouchPointerLifoBufferCountE',
    'g_TouchPointerLifoTail': '_ZN5isaac7runtime22g_TouchPointerLifoTailE',
    'g_TouchPointerLifoCount': '_ZN5isaac7runtime23g_TouchPointerLifoCountE',
    'g_TouchPointerRejectedMappings': '_ZN5isaac7runtime30g_TouchPointerRejectedMappingsE',
    # ★ 最新条目的采样号低 32 位与 lifo 槽位号：判"这块内存是活的吗"。
    # 真的 lifo 每采样一次这个号就加一（**与有没有手指无关**）⇒ 两次读数之间它应当变化；
    # 恒 0 = 一条带采样号的条目都没有 = 这块内存没在被写（**不是**"没人在按"）。
    'g_TouchPointerLastSampling': '_ZN5isaac7runtime26g_TouchPointerLastSamplingE',
    'g_TouchPointerLastEntryIndex': '_ZN5isaac7runtime28g_TouchPointerLastEntryIndexE',
    # 批次 194：原生右上角小地图的**触摸门控补丁**装没装上（改的是游戏代码里 3 条指令）。
    # 0 = 还没试、1 = 三处都装上、2 = 有守卫不符/写失败；后三个是明细。
    'g_MinimapTouchGateState': '_ZN5isaac7runtime23g_MinimapTouchGateStateE',
    'g_MinimapTouchGateApplied': '_ZN5isaac7runtime25g_MinimapTouchGateAppliedE',
    'g_MinimapTouchGateGuardMismatch': '_ZN5isaac7runtime31g_MinimapTouchGateGuardMismatchE',
    'g_MinimapTouchGateFailureCode': '_ZN5isaac7runtime29g_MinimapTouchGateFailureCodeE',
    'g_InputActionTriggeredMask': '_ZN5isaac7runtime26g_InputActionTriggeredMaskE',
    # 批次 109：每个动作报过几次"刚按下"（32 个 u32，下标 = 动作号 & 31）。
    'g_InputEdgeCounts': '_ZN5isaac7runtime17g_InputEdgeCountsE',
    # 批次 110：每个动作观察到的最长"闪断"帧数（按住期间连续多少帧读到"没按住"）。
    'g_InputReleaseRunPeak': '_ZN5isaac7runtime21g_InputReleaseRunPeakE',
    # 批次 213 建、批次 221 改口径：**报边沿时"距上一次读到按住"的间隔**（最小 / 最近）——
    # 只有 1~3 帧 ⇒ **闪断**（引擎的「按住」在按着的时候断过帧，会直接多报边沿）；
    # 几百帧 ⇒ 用户真松手再按。★ 批次 221 起**没有"去抖窗口"这个常量**了（已删除：
    # 猜一个时长两侧都会咬人，用户两侧症状同时出现过）。
    # ★ 符号名照 `nm` 抄（`_ZN5isaac7runtime17_/18_…`），别手数长度。
    # ★ 更正（批次 381，2026-10-06）：上面这段的**旧语义作废**（原文保留，只作历史）。
    #   新语义：边沿不再由"调用方询问节奏"决定，改成**每帧在引擎帧边界上采样一次、判定纯读**
    #   ⇒ 这个量现在是「**相邻两次边沿之间隔了几帧**」。用途 = 判"两次独立按下之间隔了多久"
    #   （"真松手再按"仍是几百帧）。★ 它**不再用来判"闪断"**：边沿不依赖调用方节奏之后，
    #   "闪断"这个概念在本机制下不适用（旧文里"1~3 帧 ⇒ 闪断"的判据连同理由一起作废）。
    'g_InputEdgeGapMin': '_ZN5isaac7runtime17g_InputEdgeGapMinE',
    'g_InputEdgeGapLast': '_ZN5isaac7runtime18g_InputEdgeGapLastE',
    # 批次 381（2026-10-06）：**"帧上采样"机制本身的现场**（5 个标量，每个 1 个 u32）。
    # 机制：`Input.IsButtonTriggered`/`IsActionTriggered` 的边沿不再由"调用方询问节奏"决定，
    # 改成**每帧在引擎帧边界上采样一次、判定纯读**。这 5 个量回答"这一帧到底采没采、
    # 采了多少、有没有失败" —— 边沿链路出问题时先用它们把"没采样"与"判定不成立"分开。
    #   * `g_InputSampleFrame`：最后一次"帧上采样"的帧号（应贴着当前帧）。
    #   * `g_InputSampleCalls`：那一帧的引擎调用次数（真机 1 台手柄时约 32；预算有界）。
    #   * `g_InputSampleCodes`：那一帧采了几个码（按键 18 + 动作 32）。
    #   * `g_InputSampleDevices`：那一帧采了几台设备（+1 是"任意设备"聚合槽）。
    #   * `g_InputSampleFailures`：采样失败累计次数（设备表读不到等 ⇒ 该帧全答 false）。
    # ★ 这些符号**在正式包里也编**（定义在 `input_api.cpp` 匿名命名空间之外）⇒ **不要**
    #   放进 `SYM_ELF_NAMES_PROBE_BUILD_ONLY`。
    # ★ 符号名须在构建后用 `nm runtime/.gdbsym-artifacts/runtime.elf | grep g_InputSample` 核对
    #   （下面的长度前缀是按 `isaac::runtime` 命名空间 + 名字长度手算的，别盲信）。
    'g_InputSampleFrame': '_ZN5isaac7runtime18g_InputSampleFrameE',
    'g_InputSampleCalls': '_ZN5isaac7runtime18g_InputSampleCallsE',
    'g_InputSampleCodes': '_ZN5isaac7runtime18g_InputSampleCodesE',
    'g_InputSampleDevices': '_ZN5isaac7runtime20g_InputSampleDevicesE',
    'g_InputSampleFailures': '_ZN5isaac7runtime21g_InputSampleFailuresE',
    # 批次 222：每帧"全动作快照"（我们自己普查的那四组；符号名照 `llvm-nm` 抄）。
    # 批次 223："动作 → 绑定的按钮码"表的 dump（符号名照 `llvm-nm` 抄）。
    # 批次 224：设备内部输入状态（符号名照 `llvm-nm` 抄，不手数长度）。
    # 批次 225：设备对象整块原始内存（符号名照 `llvm-nm` 抄）。
    # 批次 226：表项指针高 32 位 + 当次选中的设备号（修"截断"与"缓存旧指针"两个 bug）。
    # 批次 227：一致性验证（连读两遍 + 来源核对 + 选中项下标；符号名照 `llvm-nm` 抄）。
    # 批次 229：读表失败计数（符号名照 `llvm-nm` 抄）。
    'g_InputActionTriggeredMaskOther': '_ZN5isaac7runtime31g_InputActionTriggeredMaskOtherE',
    'g_InputActionPressedMask': '_ZN5isaac7runtime24g_InputActionPressedMaskE',
    'g_InputActionPressedMaskOther': '_ZN5isaac7runtime29g_InputActionPressedMaskOtherE',
    'g_InputLastController': '_ZN5isaac7runtime21g_InputLastControllerE',
    'g_InputPressedControllerMask': '_ZN5isaac7runtime28g_InputPressedControllerMaskE',
    'g_InputTriggeredControllerMask': '_ZN5isaac7runtime30g_InputTriggeredControllerMaskE',
    'g_InputLastActionCode': '_ZN5isaac7runtime21g_InputLastActionCodeE',
    'g_InputLastActionResult': '_ZN5isaac7runtime23g_InputLastActionResultE',
    # 批次 195（2026-09-29）加的**按键号**那三条查询的现场；批次 209 才接进读数。
    # ★ 那两个变量在源码里的注释写着"真机上唯一能判'到底读到了没有'的就是这两个计数"，
    #   却一直没人读它 ⇒ 典型的"设施做了、判据没接上"（本项目反复犯）。补上。
    'g_InputButtonPressedMask': '_ZN5isaac7runtime24g_InputButtonPressedMaskE',
    'g_InputButtonQueriedMask': '_ZN5isaac7runtime24g_InputButtonQueriedMaskE',
    # ★★★ 批次 210（2026-09-29 深夜）：**按键号那条链"发布没发布"** —— 这一对把 209 那条
    #   错结论钉死的地方说清楚了。两个槽是 `TryInstallInputButtonBindings` 写进去的引擎入口地址：
    #   守卫（序言 16 字节 + `entry+0xE0` 的 4 字节判别式）任一条不符 ⇒ **槽保持 0** ⇒
    #   `Input.IsButtonPressed` / `IsButtonTriggered` 立刻返回 false（**不报错、也不置任何探针位**）。
    #   ⇒ 只看那两个掩码会把"守卫没过"误读成"模组没问"。判据就是这两个槽是不是 0。
    'g_InputIsButtonPressed': '_ZN10LuaRuntime12_GLOBAL__N_1L22g_InputIsButtonPressedE',
    'g_InputGetButtonValue': '_ZN10LuaRuntime12_GLOBAL__N_1L21g_InputGetButtonValueE',
    # ★★★ 批次 211（2026-09-30）：**PC→NS 手柄号映射**的现场。为什么必须有它：模组问的"手柄号"
    #   是 PC 的编号（0=键盘、1..4=第几台手柄），引擎要的是 Switch 的设备号（0=触摸屏、33=手柄）。
    #   翻错了就是**恒答 false、什么线索都没有**（MCM 那一轮就是这么卡住的）。
    # ★ 符号名里的长度是**实测**的（`nm` 核过：24/24/27/29）—— 第一次凭手数写成了 25/25/28/30，
    #   读数会静默把它当成"未解析到"。改这类条目**必须** `nm <elf> | grep <名字>` 复核。
    'g_InputControllerMapPcId': '_ZN5isaac7runtime24g_InputControllerMapPcIdE',
    'g_InputControllerMapNsId': '_ZN5isaac7runtime24g_InputControllerMapNsIdE',
    'g_InputControllerMapOutcome': '_ZN5isaac7runtime27g_InputControllerMapOutcomeE',
    'g_InputControllerMapFallbacks': '_ZN5isaac7runtime29g_InputControllerMapFallbacksE',
    # ★ 批次 230（2026-09-30）：**模组动作号 → 引擎内部动作号**翻译的现场。
    #   为什么必须有它：PC 的 `ButtonAction` 与 Switch 引擎的内部表不是同一张（PC 的
    #   `ACTION_MENULEFT = 20`，引擎的 20 = "菜单下"）⇒ 翻译错了就是"推摇杆下被读成按左"，
    #   而且**不报错、不崩**；翻没翻、翻成几号、有多少次因为"Switch 上没有"直接回答，都要能看见。
    #   口径与逐行证据 = `runtime/src/interfaces/lua/input_action_map.hpp`。
    #   ★ 符号名照 `nm runtime/.gdbsym-artifacts/runtime.elf | grep InputActionMap` 抄（别手数长度）。
    'g_InputActionMapLuaCode': '_ZN5isaac7runtime23g_InputActionMapLuaCodeE',
    'g_InputActionMapEngineCode': '_ZN5isaac7runtime26g_InputActionMapEngineCodeE',
    'g_InputActionMapAbsent': '_ZN5isaac7runtime22g_InputActionMapAbsentE',
    # ★★★ 批次 212（2026-09-30）：**玩家字段写**的现场。为什么必须有它：字段写守卫是"**报错**"不是
    #   "静默忽略" ⇒ 模组写了我们没实现的字段就**整条回调当场中断**（MCM 的菜单就是这么画不出来的：
    #   它在渲染回调里 `player.Velocity = vecZero`）。"它写了什么、有没有被拒"必须不靠眼睛就能读到。
    #   ★ 符号名照 `nm runtime/.gdbsym-artifacts/runtime.elf | grep EntityFieldWrite` 抄下来
    #     （2026-09-30 教训：手数长度编码会静默读不到）。
    'g_EntityFieldWrites': '_ZN5isaac7runtime19g_EntityFieldWritesE',
    'g_EntityFieldWriteRejected': '_ZN5isaac7runtime26g_EntityFieldWriteRejectedE',
    'g_LastEntityFieldWriteName': '_ZN5isaac7runtime26g_LastEntityFieldWriteNameE',
    # 批次 214（2026-09-30）：`Seeds:AddSeedEffect`/`RemoveSeedEffect`（**按设计不生效**的空实现）
    #   被调用了几次。为什么必须有它：那两条的整条理由就是"宁可不生效也不抛错"，
    #   真机上唯一能证明"模组真的调了、我们真的接住了、而且没抛错"的就是这个数。
    'g_SeedsEffectWriteAttempts': '_ZN5isaac7runtime26g_SeedsEffectWriteAttemptsE',
    # 批次 217（2026-09-30）：**每个动作"最后一次被问到时"的现场**（帧号 / 哪条 API / controller / 答案）。
    #   为什么要有它：原来的 `g_InputActionQueriedMask` 那几张是**粘性**的（一旦置位永不清），
    #   真机上早饱和成 `0x0fffffff` ⇒ 分不出"用户按下的那一刻，菜单问没问、我们答了什么"。
    #   ★ 符号名照 `nm runtime/.gdbsym-artifacts/runtime.elf | grep InputActionAsked` 抄（别手数长度）。
    'g_InputActionAskedFrame': '_ZN5isaac7runtime23g_InputActionAskedFrameE',
    'g_InputActionAskedKind': '_ZN5isaac7runtime22g_InputActionAskedKindE',
    'g_InputActionAskedController': '_ZN5isaac7runtime28g_InputActionAskedControllerE',
    'g_InputActionAskedAnswer': '_ZN5isaac7runtime24g_InputActionAskedAnswerE',
    # 批次 218（2026-09-30）：**按键侧**的独立计数与"最后一次被问"的现场。
    #   为什么：原来按键号与动作号共用 `g_InputEdgeCounts` ⇒ 分不出"菜单走了按键分支还是动作分支"。
    #   ★ 符号名照 `nm runtime/.gdbsym-artifacts/runtime.elf | grep InputButton` 抄。
    'g_InputButtonEdgeCounts': '_ZN5isaac7runtime23g_InputButtonEdgeCountsE',
    'g_InputButtonAskedFrame': '_ZN5isaac7runtime23g_InputButtonAskedFrameE',
    'g_InputButtonAskedKind': '_ZN5isaac7runtime22g_InputButtonAskedKindE',
    'g_InputButtonAskedController': '_ZN5isaac7runtime28g_InputButtonAskedControllerE',
    'g_InputButtonAskedAnswer': '_ZN5isaac7runtime24g_InputButtonAskedAnswerE',
    # 批次 219：**"最后一次真的被激活"的帧号**（动作侧 / 按键侧各一张）。
    'g_InputActionHeldFrame': '_ZN5isaac7runtime22g_InputActionHeldFrameE',
    'g_InputButtonTriggeredFrame': '_ZN5isaac7runtime27g_InputButtonTriggeredFrameE',
    # 批次 379（2026-10-06）：按键侧**上升沿表本体**（`LuaRuntime::g_ButtonEdge`，定义在
    # `input_api.cpp` 的匿名命名空间里 ⇒ 符号名带 `12_GLOBAL__N_1L`，照
    # `nm runtime/.gdbsym-artifacts/runtime.elf | grep g_ButtonEdge` 抄）。
    #   为什么非要有它：`IsButtonTriggered` 的答案 = **引擎的"按住"** + **我们自己求的边沿**，
    #   而批次 218 那组探针只能告诉你"模组问过、我们答 false" —— **分不出**是引擎没答"按住"，
    #   还是我们的边沿判定没成立（两条路的修法完全不同）。这张表里的 `held`（这一格上一次
    #   采样时引擎答的"按住"）与 `lastEdgeFrame`（**粘性**：引擎只要答过一次"按住"就留下
    #   帧号）正好把这两件事分开 ⇒ 真机上"按键按下去毫无反应"的唯一判据。
    # ★ 更正（批次 381，2026-10-06）：字段名由 `lastPressedFrame` 改名为 `lastEdgeFrame`，
    #   语义也变了 —— 它现在记的是**边沿发生的那一帧**（不再是"上一次读到按住"的帧号）。
    #   这张表的**读法没变**：行 1 = 设备 33（第 1 台手柄）、行 31 = 任意设备（0xFFFFFFFF）。
    'g_ButtonEdge': '_ZN5isaac7runtime12_GLOBAL__N_1L12g_ButtonEdgeE',
    'g_ModMenuLastCode': '_ZN5isaac7runtime17g_ModMenuLastCodeE',
    'g_ModMenuMilestones': '_ZN5isaac7runtime19g_ModMenuMilestonesE',
    'g_ModMenuReportCount': '_ZN5isaac7runtime20g_ModMenuReportCountE',
    'g_FontDrawCalls': '_ZN5isaac7runtime15g_FontDrawCallsE',
    'g_FontDrawBytes': '_ZN5isaac7runtime15g_FontDrawBytesE',
    # 批次 415：Font 存储改走 **Lua 分配器**（`lua_getallocf`），四格读数替换 414 的池五格。
    # ★ 判据：`g_FontStorageLive`（当前活着没归还的 Font 数）**应当停在个位数** ——
    #   模组 `whatsmydps` 每帧建一个、随即该被 GC 回收；414 那版真机实测是 **288**（= 不回收）。
    #   `g_FontStorageFailures` **应当恒 0**（>0 = 拿不到分配器或分配返回空）。
    'g_FontStorageAllocations': '_ZN5isaac7runtime24g_FontStorageAllocationsE',
    # ★ 2026-10-09 更正：417 ELF 中标识符长度是 17 / 21，旧 18 / 22 根本解析不到。
    'g_FontStorageLive': '_ZN5isaac7runtime17g_FontStorageLiveE',
    'g_FontStorageLivePeak': '_ZN5isaac7runtime21g_FontStorageLivePeakE',
    'g_FontLoadCalls': '_ZN5isaac7runtime15g_FontLoadCallsE',
    'g_FontLoadResult': '_ZN5isaac7runtime16g_FontLoadResultE',
    # ---- 数据行 API 的"调用 / 静默降级"计数器（批次 069，2026-09-19）----
    # 存在的唯一目的：**不再靠探针回答"这条 API 到底有没有被调到"**。
    # 数据行处理器（字段行 `FieldApiHandler` / 引擎方法行 `EngineMethodHandler`）拿不到接收者、
    # 偏移或入口指纹时**静默降级**（不报错），于是"没生效"与"没被调用"在设备上分不开 ——
    # 下面这九个量就是分开它们的那把尺子。名字是 `extern "C"` 的，不进名称改编。
    # ---- 第 4 类降级 + 服装查表现场（批次 141，2026-09-26）----
    # 由来：The Specialist for Good Items 在**文件作用域**用 `Isaac.GetCostumeIdByPath` 建服装表
    # （23 条），跳舞时把结果直接喂给 `player:AddNullCostume(id)`；真机崩在
    # `Entity_Player::AddCostume + 0x3c`（空指针）。这几格分开两件事：
    #   ① `GetCostumeIdByPath` 到底查到没有（查了几次 / 中几次 / 最后一次中的是几 / 容器里有几条）；
    #   ② 模组实际喂进"加/摘临时服装"的编号是几，以及我们**主动挡下**过几次
    #      （`g_IsaacEngineRowRejectGuard`；挡下 = 编号无效时不再往引擎里调，见 `isaac_api.cpp`）。
    # `g_IsaacCostumePathNullCount` 里的 `0xFFFFFFFF` = 那条链当时读不到（**不是**"容器空"）；
    # `g_IsaacCostumePathLastId` 同理 = 一次都没命中过。
    # 批次 154（2026-09-27）：`Music:Play` 的**编号保险**挡下几次 —— 真机事故
    # `dist/crash-153-20260927-1121.log`（模组拿 `-1` 去 `Music::Play`，`Data Abort` 崩在 +0x68）
    # 之后加的。这一格是"这次没放歌"与"我们挡了"的唯一区分点。
    # ---- 批次 144（2026-09-26）：只读看一眼引擎存档分区里的 `options.ini`（EnableMods）----
    'g_OptionsProbeExists': 'g_OptionsProbeExists',
    'g_OptionsProbeStatus': 'g_OptionsProbeStatus',
    'g_OptionsProbeReadStatus': 'g_OptionsProbeReadStatus',
    'g_OptionsProbeSize': 'g_OptionsProbeSize',
    'g_OptionsProbeEnableMods': 'g_OptionsProbeEnableMods',
    'g_OptionsProbeHeadLow': 'g_OptionsProbeHeadLow',
    'g_OptionsProbeHeadHigh': 'g_OptionsProbeHeadHigh',
    # 批次 145：我们每帧把"启用模组"总闸置回 1 的次数（引擎自带的模组页会按键翻转它）。
    'g_ModsGateRestores': 'g_ModsGateRestores',
    #: 补加载那一半（引擎已经加载过时，我们替它再调一次 `Manager::LoadConfigs()`）。
    #: 引擎那个"启用模组"总开关（`Manager + 0x36519`）的原值/现值/我们补写次数，
    #: 以及"引擎自己没置位、由我们补写"的条数（`Fallback > 0` = 我们没赶上 ListMods）。
    # ---- 批次 143（2026-09-26）：按 PC 逻辑"喊引擎自己重扫一遍模组目录"的现场 ----
    # 走的是引擎自己的 `ModManager::Reset()`（扫 `mods/` → 看 `disable.it` + EnableMods 总闸
    # → 写每条模组的启用位 → `ModManager::LoadConfigs()` 读 `costumes2.xml`/`music.xml`）。
    # 判读：`State=1` 且 `MusicAfter > MusicBefore`（或 `NullAfter > NullBefore`）就是**成了**。
    # ---- `RoomDescriptor.Data` 读不出来时的现场（批次 071）----
    # 真机上 `crd.Data` 返回 nil 让 GoodTrip 的 `MC_POST_NEW_ROOM` 回调每次崩
    # （`control.lua:339`）。这几个量回答"是哪种房间、描述符对不对"：
    # GridIndex = 0xFFFFFFFF 表示那个槽位**没填**（我们拿到的是引擎的空描述符）；
    # GridIndex 正常而 Data 仍读不到 ⇒ 那个房间确实没有配置对象（贪婪模式一类）。
    # ---- 房间描述符**解析现场**（批次 074）----
    # 用户报"从部分房间回到两格房时小地图不出现"：GoodTrip 的地图绘制依赖
    # `grid_room[crd.SafeGridIndex] ~= nil`（条件为假 ⇒ 不画、也**不报错**）。
    # 多格房间里 SafeGridIndex 与 GridIndex 锚在不同格子 ⇒ 这几格用来分清
    # "扫描没命中"、"被足迹校验挡掉"（校验太严）、还是"引擎映射表给的槽位无效"。
    'g_IsaacRoomIdxCalls': 'g_IsaacRoomIdxCalls',
    'g_IsaacRoomIdxEmpty': 'g_IsaacRoomIdxEmpty',
    'g_IsaacRoomIdxRejectedFootprint': 'g_IsaacRoomIdxRejectedFootprint',
    'g_IsaacRoomIdxEngineMapUsed': 'g_IsaacRoomIdxEngineMapUsed',
    'g_IsaacRoomIdxLastRequest': 'g_IsaacRoomIdxLastRequest',
    'g_IsaacRoomIdxLastResolvedGrid': 'g_IsaacRoomIdxLastResolvedGrid',
    'g_IsaacRoomIdxLastResolvedSafe': 'g_IsaacRoomIdxLastResolvedSafe',
    'g_IsaacRoomIdxLastResolvedList': 'g_IsaacRoomIdxLastResolvedList',
    'g_IsaacRoomIdxLastRejectRequest': 'g_IsaacRoomIdxLastRejectRequest',
    'g_IsaacRoomIdxLastRejectAnchor': 'g_IsaacRoomIdxLastRejectAnchor',
    'g_IsaacRoomIdxLastRejectDeltaBias': 'g_IsaacRoomIdxLastRejectDeltaBias',
    'g_IsaacRoomIdxMapSlotRejected': 'g_IsaacRoomIdxMapSlotRejected',
    # 批次 076：把"映射表给的槽位"拆成四类（接受 / 槽号为负 / 锚点未分配 / 槽位超过元素个数）
    'g_IsaacRoomIdxAccepted': 'g_IsaacRoomIdxAccepted',
    'g_IsaacRoomIdxSlotNegative': 'g_IsaacRoomIdxSlotNegative',
    'g_IsaacRoomIdxUnallocatedAnchor': 'g_IsaacRoomIdxUnallocatedAnchor',
    'g_IsaacRoomIdxSlotBeyondCount': 'g_IsaacRoomIdxSlotBeyondCount',
    'g_IsaacRoomIdxLastAcceptedRequest': 'g_IsaacRoomIdxLastAcceptedRequest',
    'g_IsaacRoomIdxLastAcceptedSlot': 'g_IsaacRoomIdxLastAcceptedSlot',
    'g_IsaacRoomIdxLastAcceptedAnchor': 'g_IsaacRoomIdxLastAcceptedAnchor',
    'g_IsaacRoomIdxLastAcceptedSafe': 'g_IsaacRoomIdxLastAcceptedSafe',
    # 批次 077：直接调引擎 `Level::GetRoomByIdx` 的次数/回落次数/最后一次入参
    'g_IsaacRoomIdxNativeCalls': 'g_IsaacRoomIdxNativeCalls',
    'g_IsaacRoomIdxNativeFallbacks': 'g_IsaacRoomIdxNativeFallbacks',
    'g_IsaacRoomIdxNativeLastIndex': 'g_IsaacRoomIdxNativeLastIndex',
    'g_IsaacRoomIdxNativeLastDimension': 'g_IsaacRoomIdxNativeLastDimension',
    # ---- 常驻性能面（批次 084；file-local static，名字仍是裸名）----
    'g_RuntimePerfCallbackCalls': 'g_RuntimePerfCallbackCalls',
    'g_RuntimePerfCallbackTicks': 'g_RuntimePerfCallbackTicks',
    'g_RuntimePerfCallbackMaxTicks': 'g_RuntimePerfCallbackMaxTicks',
    'g_RuntimePerfSyscalls': 'g_RuntimePerfSyscalls',
    'g_RuntimePerfSyscallTicks': 'g_RuntimePerfSyscallTicks',
    # ---- 按 (事件 id, 属主模组) 分开的回调耗时桶（批次 086）----
    'g_RuntimePerfCallbackBuckets': 'g_RuntimePerfCallbackBuckets',
    'g_RuntimePerfBucketOverflow': 'g_RuntimePerfBucketOverflow',
    # ---- 按 **API 接口** 分开的耗时桶（批次 087）----
    'g_RuntimePerfApiBuckets': 'g_RuntimePerfApiBuckets',
    'g_RuntimePerfApiBucketOverflow': 'g_RuntimePerfApiBucketOverflow',
    'g_RuntimePerfApiTotalCalls': 'g_RuntimePerfApiTotalCalls',
    'g_RuntimePerfApiTotalTicks': 'g_RuntimePerfApiTotalTicks',
    # ---- Lua 采样剖析器（批次 089）----
    'g_RuntimePerfProfileBuckets': 'g_RuntimePerfProfileBuckets',
    'g_RuntimePerfProfileSamples': 'g_RuntimePerfProfileSamples',
    'g_RuntimePerfProfileOverflow': 'g_RuntimePerfProfileOverflow',
    # ---- 分配账（批次 091）----
    'g_RuntimePerfTickCostTicks': 'g_RuntimePerfTickCostTicks',
    # ★ 2026-10-04（批次 363）：这六条**不在这里** —— 它们在本构建的 ELF 里不存在
    # （只写不读 ⇒ `--gc-sections` 回收；批次 361 那版同样没有）。原因与处置见
    # 下面 `SYM_UNRESOLVABLE` 的注释。放回这里会让 `test_elf_syms` 判红，
    # 而"红"是对的：符号表不该声称一个有读口的量具存在。
    # ---- 模组那一行 + 模组页（**生产版**，批次 077）--------------------------------
    # 状态面结构体在 `runtime/source/mod_menu_native.hpp`（20 个 u32），定义在 `.cpp` 里。
    # ★★ 符号名是**裸名**，不是改编名：它声明成 `extern "C"`（C 语言链接 ⇒ 不加命名空间前缀、
    #    不做名称改编）。**别照抄探针那一行** —— 探针那份是普通 C++ 全局，
    #    符号是 `_ZN5isaac7runtime5probe26g_NativeModsMenuProbeStateE`。
    #    核对办法：`nm -C runtime/.gdbsym-artifacts/runtime.elf | grep g_ModMenuState`。
    'mod_menu_state': 'g_ModMenuState',
    # ---- 批次 418（2026-10-09）：**owner 编号 → 模组名** 的那张表 ------------------
    # 掉了帧要"点名"就得有它：回调耗时桶只给属主编号（`[#17]`），而"模组清单"是引擎给的目录列表、
    # **包含被禁用的模组** ⇒ 两套编号之间**没有固定偏移**（实测两对锚点是 +6 与 +4）。
    # 只有"分配 owner 号的那一刻"知道这个编号是谁 ⇒ 表在 `lua_runtime.cpp` 的 `RegisterMod` 里写。
    # 32 行 × 64 字节 = 2048 字节 = **256 个字**（读取宽度见 `build_requests()`）。
    # 符号是**裸名**（`extern "C"` + `[[gnu::used]]`，定义在全局作用域 —— 不这么做的话
    # `section GC` 会把它整个丢掉、或者符号名带 `_GLOBAL__N_1` 让这里对不上）。
    # 核对办法：`nm runtime/.gdbsym-artifacts/runtime.elf | grep g_ModOwnerNames`。
    'g_ModOwnerNames': 'g_ModOwnerNames',
    # ---- 游戏控制台（批次 121）----
    # ★ 这一份是**改编名**（不是裸名）：它声明成命名空间内的普通 `inline` 变量
    #   （`isaac::runtime::console::g_ConsoleState`），因为 `extern "C"` + 初始化列表会让
    #   gcc 在 `-Werror` 下判红。**别照抄上面那两行的裸名写法**。
    # 核对办法：`nm runtime/.gdbsym-artifacts/runtime.elf | grep -i consolestate`。
    'g_ConsoleState': '_ZN5isaac7runtime7console14g_ConsoleStateE',
}
#: **只在探针构建里存在**的符号（批次 019 起）。为什么要跟主表分开：
#: `runtime/tests/test_elf_syms.py` 钉住的是"主表里每一项都必须能在**当前生产 ELF** 里解析到"
#: —— 那是"偏移表不许过期"的守门人，不该为探针放宽。探针符号按定义在生产 ELF 里**不存在**
#: （`PROBE_BREAK=0` 时整个 TU 被编译掉），所以它们单独一张表：解析到就用，解析不到就删键
#: 并如实记账，主表那两条断言的语义一个字都不动。
#: 名字前缀是探针自己的命名空间 `isaac::runtime::probe`，同一条门禁里另有断言钉住这一点。
# 2026-10-10：RoomEntitySpawn旧入口在内部71桥版本中不再被引用；
# Font分配使用Lua longjmp，旧失败计数没有消费者，可被链接GC移除。
# 保留旧包解析能力，但缺席必须明确未读，不能算0或当成必备符号。
SYM_ELF_NAMES_OPTIONAL = {
    'g_CallbackDiagnosticViewIncomplete': '_ZN5isaac7runtime34g_CallbackDiagnosticViewIncompleteE',
    'g_CallbackDiagnosticViewOverflow': '_ZN5isaac7runtime32g_CallbackDiagnosticViewOverflowE',
    'entry_relay_room_entity_spawn': 'EntryRelayRoomEntitySpawnCallback',
    'g_FontStorageFailures': '_ZN5isaac7runtime21g_FontStorageFailuresE',
}

SYM_ELF_NAMES_PROBE_ONLY = {
    # 原生模组页探针的诊断字（**109 个 u32**，布局见 `native_mods_menu_probe.hpp` ——
    # 单元数由 `runtime/tests/test_probe_state_layout.py` 在 .cpp/.hpp/本工具三处一起钉住；
    # 这个注释以前写着"42 个 u32"（批次 019 时的数字），已经过期过很久）。
    'native_mods_probe': '_ZN5isaac7runtime5probe26g_NativeModsMenuProbeStateE',
}
#: **批次 232（2026-09-30）：只有探针包（`DIAGNOSTIC_PROBES=1`）里才存在**的采集量。
#:
#: 为什么单开一张表：这批把正式包里的探针采集动作整个编译掉了（见 `runtime/source/probe_gate.hpp`），
#: 而正式包是全量 section GC 链接的 ⇒ **没人写的全局量会被链接器整个丢掉**
#: ⇒ 下面这些符号在正式 ELF 里**根本不存在**（实测 77 个）。
#:
#: 主表那两条断言要求「每一项都能在当前**生产** ELF 里解析到」（= 偏移表不许过期的守门人），
#: 不该为探针放宽 —— 与 `SYM_ELF_NAMES_PROBE_ONLY` 同一个理由，所以再分一张：
#:   * 探针包：解析得到 ⇒ 照常进 `SYMS`，读数一切照旧；
#:   * 正式包：解析不到 ⇒ **如实记账**进 `SYM_MISSING`，读数报「本构建没有这项探针」，
#:     绝不用过期偏移去猜一个位置（那是「看起来有值、其实是别人的变量」）。
#:
#: 门禁 `test_elf_syms.py::test_probe_build_only_hints_are_accounted_for` 钉住三件事：
#: ① 名单里每一项要么进 `SYMS`、要么进 `SYM_MISSING`，**不许静默消失**；
#: ② 三张符号表互不重叠；③ 反向自证 —— 能解析到的符号不许混进这张表。
SYM_ELF_NAMES_PROBE_BUILD_ONLY = {
    # ---- 批次 235（2026-09-30）：启动期"读模组"分段计时（`load_phase_probe.hpp`）---------
    # 为什么在生产 ELF 里找不到：整段包在 `#if EXL_DIAGNOSTIC_PROBES` 里，
    # 正式包（默认 0）连符号都不编进去。要看这几个数必须出 `DIAGNOSTIC_PROBES=1` 的包。
    # ★ 名字口径不统一，别照抄：前两个在 `isaac::runtime::loadprobe` 里（**改编名**），
    #   后三个写在 `hook_manager.cpp` 的**文件作用域**（**裸名**）。核对办法：
    #   `nm runtime/.sdmc-test-artifacts/runtime.elf | grep -E "LoadPhaseMicros|ModLoadMicros"`。
    'g_LoadPhaseMicros': '_ZN5isaac7runtime9loadprobe17g_LoadPhaseMicrosE',  # u32[8]
    'g_LoadTotalMicros': '_ZN5isaac7runtime9loadprobe17g_LoadTotalMicrosE',  # u32
    'g_ModLoadMicros': 'g_ModLoadMicros',   # u32[16]，每个模组的加载耗时（微秒）
    'g_ModLoadCount': 'g_ModLoadCount',     # u32，上面写了几个
    'g_ModLoadTotal': 'g_ModLoadTotal',     # u32，本次一共几个模组
    # 批次 236 补：这条加载**跨了几帧**。≈15~20 = 拆帧生效（卡顿来自"每帧仍很重"）；
    # == 1 = 拆帧没生效（整条路还是在一帧里跑完，那是我这侧的 bug）。
    'g_LoadFramesUsed': 'g_LoadFramesUsed',  # u32
    'g_LoadStartFrame': 'g_LoadStartFrame',  # u32，起步那一帧的 Update 进入次数
    'g_ApiSequence': '_ZZN5isaac7runtime6detail11ApiSequenceEvE5state',
    # 批次 250：**原生状态回退**计数（`native_state_fallback.hpp` 的 `detail::NativeFallback()`）。
    # 读法：`count == 0` ⇒ 我们的地址链没问题；`count > 0` ⇒ 看 `lastApi` 是哪一个接口
    # （编号表 = 那个头文件里的 `NativeFallbackApi`），再去回查那一条链。
    # 为什么必须有它：把"读不到就抛错"改成"给回退值"之后，回退会让"地址链错了"**看起来正常**
    # ⇒ 没有这个计数就没有任何东西能把真问题顶出来（这是那次改动唯一的风险控制）。
    'g_NativeFallback': '_ZZN5isaac7runtime6detail14NativeFallbackEvE5state',
    'g_InputActionSnapshotPressed': '_ZN5isaac7runtime28g_InputActionSnapshotPressedE',
    'g_InputActionSnapshotValue': '_ZN5isaac7runtime26g_InputActionSnapshotValueE',
    'g_InputBindingActionCount': '_ZN5isaac7runtime25g_InputBindingActionCountE',
    'g_InputBindingArrayPtr': '_ZN5isaac7runtime22g_InputBindingArrayPtrE',
    'g_InputBindingCodes': '_ZN5isaac7runtime19g_InputBindingCodesE',
    'g_InputBindingDumpDone': '_ZN5isaac7runtime22g_InputBindingDumpDoneE',
    'g_InputButtonSnapshotPressed': '_ZN5isaac7runtime28g_InputButtonSnapshotPressedE',
    'g_InputDeviceRawBeginHigh': '_ZN5isaac7runtime25g_InputDeviceRawBeginHighE',
    'g_InputDeviceRawBeginLow': '_ZN5isaac7runtime24g_InputDeviceRawBeginLowE',
    'g_InputDeviceRawBeginPass2High': '_ZN5isaac7runtime30g_InputDeviceRawBeginPass2HighE',
    'g_InputDeviceRawBeginPass2Low': '_ZN5isaac7runtime29g_InputDeviceRawBeginPass2LowE',
    'g_InputDeviceRawDumpCount': '_ZN5isaac7runtime25g_InputDeviceRawDumpCountE',
    'g_InputDeviceRawEndHigh': '_ZN5isaac7runtime23g_InputDeviceRawEndHighE',
    'g_InputDeviceRawEndLow': '_ZN5isaac7runtime22g_InputDeviceRawEndLowE',
    'g_InputDeviceRawEndPass2High': '_ZN5isaac7runtime28g_InputDeviceRawEndPass2HighE',
    'g_InputDeviceRawEndPass2Low': '_ZN5isaac7runtime27g_InputDeviceRawEndPass2LowE',
    'g_InputDeviceRawHead': '_ZN5isaac7runtime20g_InputDeviceRawHeadE',
    'g_InputDeviceRawId': '_ZN5isaac7runtime18g_InputDeviceRawIdE',
    'g_InputDeviceRawManagerHigh': '_ZN5isaac7runtime27g_InputDeviceRawManagerHighE',
    'g_InputDeviceRawManagerLow': '_ZN5isaac7runtime26g_InputDeviceRawManagerLowE',
    'g_InputDeviceRawPointerHigh': '_ZN5isaac7runtime27g_InputDeviceRawPointerHighE',
    'g_InputDeviceRawPointerLow': '_ZN5isaac7runtime26g_InputDeviceRawPointerLowE',
    'g_InputDeviceRawTail': '_ZN5isaac7runtime20g_InputDeviceRawTailE',
    'g_InputDeviceRawValues': '_ZN5isaac7runtime22g_InputDeviceRawValuesE',
    'g_InputDeviceRawValuesPrevious': '_ZN5isaac7runtime30g_InputDeviceRawValuesPreviousE',
    'g_InputDeviceSelectedId': '_ZN5isaac7runtime23g_InputDeviceSelectedIdE',
    'g_InputDeviceSelectedIndex': '_ZN5isaac7runtime26g_InputDeviceSelectedIndexE',
    'g_InputDeviceStateActionCount': '_ZN5isaac7runtime29g_InputDeviceStateActionCountE',
    'g_InputDeviceStateActionValue': '_ZN5isaac7runtime29g_InputDeviceStateActionValueE',
    'g_InputDeviceStateAxes': '_ZN5isaac7runtime22g_InputDeviceStateAxesE',
    'g_InputDeviceStateDeadzone': '_ZN5isaac7runtime26g_InputDeviceStateDeadzoneE',
    'g_InputDeviceStateDeadzoneAlt': '_ZN5isaac7runtime29g_InputDeviceStateDeadzoneAltE',
    'g_InputDeviceStateDumpCount': '_ZN5isaac7runtime27g_InputDeviceStateDumpCountE',
    'g_InputDeviceStateEnabled': '_ZN5isaac7runtime25g_InputDeviceStateEnabledE',
    'g_InputDeviceStateKeysCurrent': '_ZN5isaac7runtime29g_InputDeviceStateKeysCurrentE',
    'g_InputDeviceStateKeysPrevious': '_ZN5isaac7runtime30g_InputDeviceStateKeysPreviousE',
    'g_InputDeviceStateStickCurrent': '_ZN5isaac7runtime30g_InputDeviceStateStickCurrentE',
    'g_InputDeviceStateStickPrevious': '_ZN5isaac7runtime31g_InputDeviceStateStickPreviousE',
    'g_InputDeviceTableCount': '_ZN5isaac7runtime23g_InputDeviceTableCountE',
    'g_InputDeviceTableId': '_ZN5isaac7runtime20g_InputDeviceTableIdE',
    'g_InputDeviceTablePass2Count': '_ZN5isaac7runtime28g_InputDeviceTablePass2CountE',
    'g_InputDeviceTablePass2Id': '_ZN5isaac7runtime25g_InputDeviceTablePass2IdE',
    'g_InputDeviceTablePass2Pointer': '_ZN5isaac7runtime30g_InputDeviceTablePass2PointerE',
    'g_InputDeviceTablePass2PointerHigh': '_ZN5isaac7runtime34g_InputDeviceTablePass2PointerHighE',
    'g_InputDeviceTablePointer': '_ZN5isaac7runtime25g_InputDeviceTablePointerE',
    'g_InputDeviceTablePointerHigh': '_ZN5isaac7runtime29g_InputDeviceTablePointerHighE',
    'g_InputDeviceTableReadFailures': '_ZN5isaac7runtime30g_InputDeviceTableReadFailuresE',
    'g_InputSnapshotFrame': '_ZN5isaac7runtime20g_InputSnapshotFrameE',
    'g_IsaacApiRowCalls': 'g_IsaacApiRowCalls',
    'g_IsaacApiRowLastCallId': 'g_IsaacApiRowLastCallId',
    'g_IsaacApiRowLastCallKind': 'g_IsaacApiRowLastCallKind',
    'g_IsaacCostumePathCalls': 'g_IsaacCostumePathCalls',
    'g_IsaacCostumePathHits': 'g_IsaacCostumePathHits',
    'g_IsaacCostumePathLastId': 'g_IsaacCostumePathLastId',
    'g_IsaacCostumePathMisses': 'g_IsaacCostumePathMisses',
    'g_IsaacCostumePathNullCount': 'g_IsaacCostumePathNullCount',
    'g_IsaacEngineRowCalls': 'g_IsaacEngineRowCalls',
    'g_IsaacEngineRowLastRejectId': 'g_IsaacEngineRowLastRejectId',
    'g_IsaacEngineRowLastRejectReason': 'g_IsaacEngineRowLastRejectReason',
    'g_IsaacEngineRowRejectEntry': 'g_IsaacEngineRowRejectEntry',
    'g_IsaacEngineRowRejectGuard': 'g_IsaacEngineRowRejectGuard',
    'g_IsaacEngineRowRejectOffset': 'g_IsaacEngineRowRejectOffset',
    'g_IsaacEngineRowRejectReceiver': 'g_IsaacEngineRowRejectReceiver',
    'g_IsaacMusicIdCalls': 'g_IsaacMusicIdCalls',
    'g_IsaacMusicIdHits': 'g_IsaacMusicIdHits',
    'g_IsaacMusicIdLastName': 'g_IsaacMusicIdLastName',
    'g_IsaacMusicIdLastResult': 'g_IsaacMusicIdLastResult',
    'g_IsaacMusicIdTableCount': 'g_IsaacMusicIdTableCount',
    'g_IsaacNullCostumeGuardUnknown': 'g_IsaacNullCostumeGuardUnknown',
    'g_IsaacNullCostumeLastRequestedId': 'g_IsaacNullCostumeLastRequestedId',
    'g_IsaacRoomDescDataDescriptorLow': 'g_IsaacRoomDescDataDescriptorLow',
    'g_IsaacRoomDescDataGridIndex': 'g_IsaacRoomDescDataGridIndex',
    'g_IsaacRoomDescDataListIndex': 'g_IsaacRoomDescDataListIndex',
    'g_IsaacRoomDescDataMisses': 'g_IsaacRoomDescDataMisses',
    'g_IsaacRoomDescDataSafeGridIndex': 'g_IsaacRoomDescDataSafeGridIndex',
    'g_MusicPlayGuardBlocked': 'g_MusicPlayGuardBlocked',
}
#: 表里有、但**这次构建的 ELF 里已经找不到**的符号：不能沿用过期的偏移（那是"看起来有值、
#: 其实是别人的变量"），只能在读数时报"读不到"。这里只记账，方便汇报时说明缺了什么。
SYM_MISSING: dict[str, str] = {}
#: ★ 批次 232：**本构建没有探针包**而缺席的键（`SYM_ELF_NAMES_PROBE_BUILD_ONLY` 的子集）。
#: 与 `SYM_MISSING` 分开记：前者是"设计如此"，后者是"该有却没有"（符号改名/过期）。
SYM_PROBE_BUILD_ABSENT: list[str] = []
#: 已经不再存在的全局量（2026-09-15：装好的挂点数改为从 `g_HookInstallResults` 现算，没有独立变量）。
#: 曾经"这次构建里不存在"的全局量。2026-09-17 复查：`g_HookInstallInstalledCount` 其实是
#: `HookInstallInstalledCount()` 里的**函数内静态**（`_ZZN…HookInstallInstalledCountEvE5value`），
#: 现在在 SYM_ELF_NAMES 里指向了那个符号，所以从这个名单里拿掉。
#: ★ 2026-10-04（批次 363 实施中查出）：**六个性能计数器在本构建的 ELF 里根本不存在** ——
#: `g_RuntimePerfEmptyCallTicks` / `g_RuntimePerfEmptyCallCount` / `g_RuntimePerfAllocCalls` /
#: `g_RuntimePerfAllocBytes` / `g_RuntimePerfAllocNewCalls` / `g_RuntimePerfFreeCalls`。
#:
#: **为什么**：它们定义在 `runtime/source/lua_runtime.cpp` 的匿名命名空间里、带
#: `visibility("hidden")`，**只被写、没有任何地方读** ⇒ 链接期的 `--gc-sections` 直接把它们回收。
#: 对照实验（2026-10-04）：批次 361 那一版的 `runtime.elf` 里同样一个都找不到（不是本批引入的）。
#:
#: **为什么放进这个名单而不是删掉**：删掉会让读数工具"静默少读几行"，而那几行是性能线
#: （`perf-line`）在用的量具 —— 它们的**代码还在**（`MeasureEmptyCallCost` 照样在写），
#: 只是产物里没有符号。放进这个名单 = 读数里明确打印"本构建已无此全局量"，
#: 谁要恢复这几行，就得先让它们**被真的读到**（例如加一个 `extern "C"` 读口），
#: 而不是把符号表改回"看起来有"。
SYM_UNRESOLVABLE = ('g_RuntimePerfEmptyCallTicks', 'g_RuntimePerfEmptyCallCount',
                    'g_RuntimePerfAllocCalls', 'g_RuntimePerfAllocBytes',
                    'g_RuntimePerfAllocNewCalls', 'g_RuntimePerfFreeCalls')
_syms_synced = False
#: `g_imagePcxDiag` 在**本构建**里的字节数（由 `sync_syms_from_elf` 从 ELF 的符号大小填）。
#: 用途：诊断结构体是"表尾追加"演进的（270 起 736 字节、271 起 800、272 起 824…），
#: 旧构建上按固定偏移硬读会打印**垃圾值**（2026-10-02 在 `270-prod` 上就发生过一次，
#: 读数里出现了"Font:Load 窗口 2577779712 次"这种明显不成立的行）。
#: ⇒ 判据必须是"**构建里真的有多少字节**"，不是"我们读回了多少字节"。
IMAGE_PCX_DIAG_BYTES = 0
# 418: Cache从内嵌数组变为动态指针；由ELF大小辨别历史与当前布局。
MOD_DATA_CACHE_BYTES = 0

HOOK_NAMES = ['ManagerUpdate', 'ManagerRender', 'PreGetCollectible',
              'ManagerPresent', 'RebuildMountPoints', 'GameStart',
              # 2026-09-20 批次 102：顺次追加（`HookId` 的顺序就是这张表的顺序，
              # 读数里的 `[i]` 与 `HookInstallReport` 的槽位一一对应）。
              'UseActiveItem', 'UseCard', 'UsePill', 'GameExit',
              # 批次 103/104：掉落物碰撞、房间生成实体。
              'PickupCollision', 'RoomEntitySpawn',
              # 贴图桥（2026-09-21）：`.pcx` 入口中继（v1 诊断层 + v2 真拦截点）。
              'ImagePcxLoad', 'ImageManagerLoadFile', 'ContentGetMountedFilePath',
              # 模组那一行 + 模组页（批次 077）：三个入口中继（生产版接线）。
              'MenuGameRender', 'MenuTitleRender', 'MenuManagerSetState',
    'PersistentGameDataSetReadOnly',
    # 批次 147（2026-09-26）：引擎那条"模组 content 加载"路的闸门（入口中���）。
    'ModManagerLoadConfigs',
    # 批次 363（2026-10-04）：`ANM2::Load` 入口中继 —— 让"模组覆盖本体资源"真正生效。
    'Anm2Load',
    # 批次 390（2026-10-07）：`MC_INPUT_ACTION` 的三条查询中继（`KAGE::Input::ManagerBase::*`）。
    'ManagerIsActionPressed',
    'ManagerIsActionTriggered',
    'ManagerGetActionValue',
    # 批次 396（2026-10-07）：`MC_ENTITY_TAKE_DMG` 的四条（基类 + 玩家/掉落物/槽位）
    # 与 `MC_EVALUATE_CACHE`。顺序必须与 `HookId` 一致。
    'EntityTakeDamage',
    'EntityPlayerTakeDamage',
    'EntityPickupTakeDamage',
    'EntitySlotTakeDamage',
    'EvaluateItems',
    # 批次 397（2026-10-07）：补全回调（第 2 批）的三条。顺序必须与 `HookId` 一致。
    'EntityKill',
    'NpcDeathRemove',
    'GameEnd',
    'FireTear',
    'FamiliarCollision', 'NpcCollision', 'PlayerCollision', 'TearCollision',
    'ProjectileCollision', 'KnifeCollision', 'BombCollision', 'NpcRender', 'ItemPoolGetPill', 'ItemPoolGetPillEffect', 'GameDevolveEnemy', 'NpcUpdateAi', 'GameSpawnEx',
    'ItemPoolTrinketFirstRandom', 'ItemPoolTrinketSelected', 'RoomClearAward',
    'EntityRemovePointers', 'EntityDestructorRemove', 'LevelCurseFirstRandom', 'LevelCurseEvaluation', 'PickupSelection', 'PickupSelectionSpecial', 'ItemPoolGetCard', 'ModManagerUnload', 'ConsoleUnknownLength', 'ConsoleUnknownCompare', 'HudRender', 'RoomConfigLoadStageBinary', 'LevelLoadRoom', 'ConsoleLifecycle', 'PressurePlateAnimationWriter', 'PressurePlateDestructor', 'PressurePlateDeletingDestructor',]
# 这些地址相对固定游戏NRO；内部挂点不使用g_hookCallbacks的旧入口槽。
INTERNAL_HOOK_SITES = {
    'RoomEntitySpawn': (0x452984, 0x68CFD0, 16),
    'ItemPoolTrinketFirstRandom': (0x3C7668, 0x68CFE0, 16),
    'ItemPoolTrinketSelected': (0x3C784C, 0x68CFF0, 16),
    'RoomClearAward': (0x456988, 0x68CDB8, 8),
    'EntityDestructorRemove': (0x58A00, 0x68CDA8, 8),
    'LevelCurseFirstRandom': (0x3E0B34, 0x68CF98, 8),
    'PressurePlateDestructor': (0x38F294, 0x68CD20, 16),
    'PressurePlateDeletingDestructor': (0x38F2D4, 0x68CD30, 16),
}

INTERNAL_LITERAL_SLOTS = {'RoomClearAward':0x68CD68, 'LevelCurseFirstRandom':0x68CD70,
                          'EntityDestructorRemove':0x68CD78}

COLD_HOOK_SITES = {'LevelCurseEvaluation':(0x3E0C88,0x68CDC0,0xF9400309),
                   'PickupSelection':(0x269D50,0x68CDE0,0x7100A29F),
                   'PickupSelectionSpecial':(0x269D08,0x68CD00,0xB85FC3B4)}

ENTITY_REMOVE_POINTER_SITES = (0xA34FB0,0xA350A0,0xA35198,0xA35290,0xA35BA0,0xA37168,
                               0xA37468,0xA37560,0xA37690,0xA37788,0xA9F910)

def decode_internal_branch(word: int, address: int) -> int | None:
    if (word & 0xFC000000) != 0x14000000:
        return None
    imm = word & 0x03FFFFFF
    if imm & 0x02000000:
        imm -= 0x04000000
    return address + imm * 4

def decode_internal_veneer(words, address: int, size: int, literal_slot=None, literal_target=None) -> int | None:
    if not words:
        return None
    low, high = words[0] & 0xFFFFFFFF, words[0] >> 32
    if high != 0xD61F0200:
        return None
    if size == 16:
        return words[1] if len(words) >= 2 and low == 0x58000050 else None
    if size == 8 and (low & 0xFF00001F) == 0x58000010:
        imm = (low >> 5) & 0x7FFFF
        if imm & 0x40000:
            imm -= 0x80000
        return literal_target if address + imm * 4 == literal_slot and literal_target else None
    if size != 8 or (low & 0x9F00001F) != 0x90000010:
        return None
    imm = ((low >> 5) & 0x7FFFF) * 4 + ((low >> 29) & 3)
    if imm & 0x100000:
        imm -= 0x200000
    return (address & ~0xFFF) + imm * 0x1000
# 只用来做比对、本身不是"要读的内存变量"的符号（读数请求要跳过它们）。
SYM_ONLY = ('shader_screen_intercept', 'identity', 'manifest_install', 'entity_remove_pointer_callback',
            'entry_relay_update', 'entry_relay_render',
            'entry_relay_collectible', 'entry_relay_rebuild',
            'entry_relay_use_active_item', 'entry_relay_use_card',
            'entry_relay_use_pill', 'entry_relay_game_exit',
            'entry_relay_pickup_collision', 'entry_relay_room_entity_spawn',
            'entry_relay_image_pcx_load', 'entry_relay_image_mgr_load',
            'entry_relay_get_mounted_path',
            # 批次 147：模组 content 加载闸门的回调（`g_hookCallbacks` 里比对用）。
            'entry_relay_mod_loadconfigs',
            # 批次 363：`ANM2::Load` 入口中继的回调（同上）。
            'entry_relay_anm2_load',
            # 批次 396：`MC_ENTITY_TAKE_DMG` 四条 + `MC_EVALUATE_CACHE` 的回调（同上）。
            'entry_relay_entity_take_damage', 'entry_relay_entity_player_take_damage',
            'entry_relay_entity_pickup_take_damage', 'entry_relay_entity_slot_take_damage',
            'entry_relay_evaluate_items',
            # 批次 397：补全回调（第 2 批）的三条回调（同上）。
            'entry_relay_entity_kill', 'entry_relay_npc_death_remove', 'entry_relay_game_end',
            'entry_relay_fire_tear',
            'present_got_slot', 'present_target', 'present_callsite_offset')
# 中继地址只用于身份比对；所有新增中继自动排除普通u32读数。
SYM_ONLY += tuple(key for key in SYM_ELF_NAMES if key.startswith('entry_relay_') and key not in SYM_ONLY)
# 已经切到零占洞入口中继的挂点 → 它的回调应当等于"模块基址 + 下面这个符号的偏移"。
RELAY_BY_HOOK = {'ManagerUpdate': 'entry_relay_update',
                 'ManagerRender': 'entry_relay_render',
                 'PreGetCollectible': 'entry_relay_collectible',
                 'RebuildMountPoints': 'entry_relay_rebuild',
                 # 批次 102 的四路事件中继。
                 'UseActiveItem': 'entry_relay_use_active_item',
                 'UseCard': 'entry_relay_use_card',
                 'UsePill': 'entry_relay_use_pill',
                 'GameExit': 'entry_relay_game_exit',
                 'PickupCollision': 'entry_relay_pickup_collision',
                 'RoomEntitySpawn': 'entry_relay_room_entity_spawn',
                 'ImagePcxLoad': 'entry_relay_image_pcx_load',
                 'ImageManagerLoadFile': 'entry_relay_image_mgr_load',
                 'ContentGetMountedFilePath': 'entry_relay_get_mounted_path',
                 # 批次 147（模组 content 加载闸门）。
                 'ModManagerLoadConfigs': 'entry_relay_mod_loadconfigs',
                 # 批次 363（`ANM2::Load` 入口中继）。
                 'Anm2Load': 'entry_relay_anm2_load',
                 # 批次 396（`MC_ENTITY_TAKE_DMG` 四条 + `MC_EVALUATE_CACHE`）。
                 'EntityTakeDamage': 'entry_relay_entity_take_damage',
                 'EntityPlayerTakeDamage': 'entry_relay_entity_player_take_damage',
                 'EntityPickupTakeDamage': 'entry_relay_entity_pickup_take_damage',
                 'EntitySlotTakeDamage': 'entry_relay_entity_slot_take_damage',
                 'EvaluateItems': 'entry_relay_evaluate_items',
                 # 批次 397（补全回调第 2 批）。
                 'EntityKill': 'entry_relay_entity_kill',
                 'NpcDeathRemove': 'entry_relay_npc_death_remove',
                 'GameEnd': 'entry_relay_game_end',
                 'FireTear': 'entry_relay_fire_tear',
                 'FamiliarCollision': 'entry_relay_familiarcollision',
                 'NpcCollision': 'entry_relay_npccollision',
                 'PlayerCollision': 'entry_relay_playercollision',
                 'TearCollision': 'entry_relay_tearcollision',
                 'ProjectileCollision': 'entry_relay_projectilecollision',
                 'KnifeCollision': 'entry_relay_knifecollision',
                 'BombCollision': 'entry_relay_bombcollision',
                 'GameSpawnEx': 'entry_relay_gamespawnex', 'NpcRender': 'entry_relay_npcrender','ItemPoolGetPill': 'entry_relay_itempoolgetpill','ItemPoolGetPillEffect': 'entry_relay_itempoolgetpilleffect','GameDevolveEnemy': 'entry_relay_gamedevolveenemy'}
# 插件里 g_helper 的位置：0xd220 就是它在插件 ELF 里的虚拟地址——插件的段是连续的，
# 所以**物理地址 = 插件代码段基址 + 虚拟地址**（实测：0x090ec1e000 + 0xd220 = 0x090ec2b220）。
PLUGIN_HELPER = 0xd220
HANDOVER_FIELDS = ['api[0] open', 'api[1] read', 'api[2] write', 'api[3] close',
                   'identity', 'diagnosticsState', 'selfJournalState',
                   'setPluginNote', 'setSymbolLookup', 'snapshot',
                   'lookupAddress', 'ownIdentity', 'ownBase', 'fileApiSlot']

# 版本核对用的锚点：本地 ELF 里从该偏移起 16 字节，设备上必须逐字节相同。
ANCHOR_NAMES = ('identity', 'exl_main', 'manifest_install')

TEST_RUN_STATES = ['Unseen', 'ExlMainEntered', 'ModuleWorkerEntered', 'TitleStateRead',
                   'ModuleScanEntered', 'ModuleScanReturned', 'ManifestInstallEntered',
                   'ManifestInstallReturned', 'LuaInitializeEntered', 'LuaInitializeReturned',
                   'FinalReportEntered']
MANIFEST_STATES = ['Unarmed(未武装)', 'Armed(已武装)', 'Running(安装中)', 'Ready(就绪)', 'Failed(失败)']
MANIFEST_STEPS = {0: '成功/无失败', 1: '读清单失败', 2: '解析清单失败', 3: '拼路径失败',
                  4: '读入口脚本失败', 5: '纯资源型（无脚本，不是失败）',
                  # 6（方案 A，2026-09-16）：**没有可用清单**，运行时自己列 `isaac_mods/mods`
                  # 发现的模组。不是失败 —— 与 0 一样是加载成功，只是"这批模组不是清单点名的"。
                  6: '自动发现（无清单，扫描 isaac_mods/mods）'}
# `LuaRuntime::LuaInitResult`（`0x10 + 这个值` 就是报告里看到的 detail）。
LUA_INIT_RESULTS = {0: '成功', 1: 'StateCreateFailed（建 lua_State 失败）',
                    2: 'RuntimePreparationMemoryFailed（准备运行时内存失败）',
                    3: 'RuntimePreparationFailed（准备运行时失败）',
                    4: 'ScriptLoadFailed（脚本装载失败）',
                    5: 'ScriptRunFailed（脚本**执行中报错**，具体错误见下面的 Lua 错误文本）',
                    6: 'MissingPostUpdateCallback（没登记 MC_POST_UPDATE）'}


def decode_failure_detail(value: int) -> str:
    """把 `g_DefaultManifestFailureDetail` / 状态机 detail 这个字翻成人话。

    它不是单一枚举：低段是"清单加载步骤"（1..4 失败、5 纯资源型），
    `0x10 + n` 是 Lua 初始化失败，`0x20 + n` 是请求本身不可用（见 `mod_load_step.hpp`）。
    """
    if value == 0:
        return MANIFEST_STEPS[0]
    if value in (5, 6):
        return MANIFEST_STEPS[value]
    if 1 <= value <= 4:
        return MANIFEST_STEPS[value]
    if 0x10 <= value < 0x20:
        n = value - 0x10
        return f'Lua 初始化失败：{LUA_INIT_RESULTS.get(n, f"未知({n})")}'
    if 0x20 <= value < 0x30:
        return f'请求本身不可用（StatusCode {value - 0x20}）'
    return f'未知({value})'
# `HookInstallResult` 家族（旧安装器路径）的失败码：0 = 成功，其余见 hook_manager.hpp。
LEGACY_HOOK_CODES = {0: 'Success', 1: 'InstructionMismatch(指令不符)', 2: 'RelayPatchMismatch(中继补丁不符)',
                     3: 'RelaySlotNotEmpty(中继槽非空)', 4: 'RelayPublishFailed(中继发布失败)',
                     5: 'GameBindingsMismatch', 6: 'GameBindingsPublishFailed', 7: 'MusicBindingsMismatch'}
PRESENT_RELAY_CODES = {0: 'Success', 1: 'RelayPatchMismatch', 2: 'RelaySlotNotEmpty',
                       3: 'RelayPublishFailed', 4: 'GotSlotTargetMismatch(桩/本体/调用点守卫不符)',
                       5: 'GotSlotUnavailable(槽没映射或值为 0)', 6: 'GotSlotWriteFailed(写完读回不一致)'}
HOOK_OUTCOMES = ['Pending(没试过)', 'Installed(装好)', 'Skipped(跳过)', 'Failed(装失败)']


# ---------------------------------------------------------------------------
# 一次挂载读完：交互式 gdb 会话
# ---------------------------------------------------------------------------

class GdbSession:
    """一个长活的 gdb 进程：命令一行一条地喂进去，靠哨兵串确认一条命令的输出已经收完。

    为什么不用 `-batch -x 脚本`：那种方式**一次会话只能发固定的一串命令**，而我们要先用
    `monitor get info` 的输出算出基址、再据此拼出读命令 —— 这要求"能来回对话"。
    又因为 gdb 这份构建**没有 Python 支持**（`Python scripting is not supported`），
    解析只能在宿主这边做，所以用了管道 + 哨兵。
    """

    def __init__(self, timeout: float = 120.0) -> None:
        self.timeout = timeout
        self._counter = 0
        cmd = ['docker', 'run', '--rm', '-i', GDB_IMAGE, 'bash', '-lc',
               '. /opt/devkitpro/devkita64.sh && exec aarch64-none-elf-gdb -q -nx']
        self.proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=subprocess.STDOUT)
        self.log: list[str] = []
        self.command('set pagination off')
        self.command('set confirm off')

    def _drain(self, token: bytes) -> str:
        buf = b''
        deadline = time.time() + self.timeout
        while token not in buf:
            remaining = deadline - time.time()
            if remaining <= 0:
                raise TimeoutError(f'等不到哨兵 {token!r}；已收到：\n{buf.decode(errors="replace")}')
            ready, _, _ = select.select([self.proc.stdout], [], [], remaining)
            if not ready:
                continue
            chunk = os.read(self.proc.stdout.fileno(), 4096)
            if not chunk:
                raise EOFError(f'gdb 提前退出；已收到：\n{buf.decode(errors="replace")}')
            buf += chunk
        # 把提示符之类的残余读干净（非阻塞）。
        while select.select([self.proc.stdout], [], [], 0.15)[0]:
            extra = os.read(self.proc.stdout.fileno(), 4096)
            if not extra:
                break
            buf += extra
        text = buf.decode(errors='replace')
        text = text.split(token.decode(), 1)[0]
        text = text.replace('(gdb) ', '')  # gdb 的提示符混在输出里，去掉免得干扰解析
        self.log.append(text)
        return text

    def command(self, text: str) -> str:
        self._counter += 1
        token = f'@@DSH_DONE_{self._counter}@@'.encode()
        payload = text.rstrip('\n') + '\n' + f'echo {token.decode()}\\n\n'
        assert self.proc.stdin is not None
        self.proc.stdin.write(payload.encode())
        self.proc.stdin.flush()
        return self._drain(token)

    def close(self) -> None:
        try:
            self.command('quit')
        except Exception:
            pass
        try:
            self.proc.wait(timeout=10)
        except Exception:
            self.proc.kill()


def parse_processes(text: str) -> int | None:
    for line in text.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0].isdigit() and parts[1].startswith('Applicat'):
            return int(parts[0])
    return None


#: 游戏本体模块名里的识别串（`Repentance.nrs.elf`）。
GAME_MODULE_MARKER = 'Repentance'


def parse_module_names(info_text: str) -> list[str]:
    """从 `monitor get info` 输出里取 `Modules:` 段的模块名。

    为什么需要它：**"进程表里有 Application"不等于"游戏在跑"** ——
    FTP 自己（`hbl.elf` + `ftpd.elf`）也是一个 Application 进程。
    2026-09-15 实测：用户已经彻底关掉游戏、只开着 FTP，而只看 `parse_processes` 的检查
    会一直报"游戏还在跑"，既挡住本来安全的写卡、又会让人怀疑用户没关游戏。
    真正要看的是模块清单里有没有 `Repentance.nrs.elf`。
    """
    names: list[str] = []
    in_modules = False
    for line in info_text.splitlines():
        stripped = line.strip()
        if stripped.startswith('Modules:'):
            in_modules = True
            continue
        if not in_modules:
            continue
        if not stripped:                     # 空行 = 段落结束
            break
        match = re.match(r'\s*0x[0-9a-f]+\s*-\s*0x[0-9a-f]+\s+(\S+)', line)
        if match:
            names.append(match.group(1))
        elif names:
            break
    return names


def game_is_running(ip: str) -> tuple[bool | None, str]:
    """设备上的以撒在不在跑。返回 `(是否在跑 | None=判断不了, 说明)`。

    写卡（FTP）之前必须问这一句：游戏运行时写卡会与 `fs.mitm` 抢 SD 卡，
    轻则下一次启动崩在装载界面（见 `AGENTS.md` 的"设备取证纪律"）。
    """
    session = GdbSession(timeout=90)
    try:
        session.command(f'target extended-remote {ip}:22225')
        pid = parse_processes(session.command('info os processes'))
        if not pid:
            return False, '进程表里没有 Application ⇒ 游戏没在跑'
        session.command(f'attach {pid}')
        names = parse_module_names(session.command('monitor get info'))
        session.command('detach')
    except Exception as error:               # 桩连不上/预算用光：老实说"判断不了"
        return None, f'调试桩用不了（{type(error).__name__}: {error}）⇒ 判断不了'
    finally:
        session.close()
    if not names:
        return None, '拿不到这个 Application 的模块清单 ⇒ 判断不了'
    if any(GAME_MODULE_MARKER in name for name in names):
        return True, f'模块清单里有 {GAME_MODULE_MARKER} ⇒ 游戏正在运行'
    return False, f'这个 Application 是 {" + ".join(names)}（不是以撒）⇒ 游戏没在跑'


def parse_bases(text: str) -> tuple[int | None, int | None, int | None]:
    """返回（运行时模块基址, 插件基址, 游戏模块基址）。

    游戏模块那一项是 `Repentance.nrs.elf`：**GOT 槽与 `Present` 偏移都相对它**，
    不是相对我们的运行时模块 —— 两者混用会读出一堆看似"不符"的垃圾值（踩过）。
    """
    module = plugin = game = None
    for line in text.splitlines():
        m = re.match(r'\s*0x([0-9a-f]+) - 0x([0-9a-f]+)\s+(\S+)', line)
        if not m:
            continue
        lo, hi, name = int(m.group(1), 16), int(m.group(2), 16), m.group(3)
        if name == 'runtime.elf':
            if hi - lo > 0x20000:
                module = lo
            else:
                plugin = lo
        elif name.startswith('Repentance.'):
            game = lo
    return module, plugin, game


def parse_words(text: str) -> dict[str, list[int]]:
    """从 `TAG xxx` + `x/Ngx` 的输出里取值（按标签分组）。"""
    values: dict[str, list[int]] = {}
    current = None
    for line in text.splitlines():
        if line.startswith('TAG '):
            current = line[4:].strip()
            values[current] = []
        elif current and re.match(r'^0x[0-9a-f]+\s*(<[^>]*>)?:', line):
            _, rest = line.split(':', 1)
            for tok in rest.split():
                try:
                    values[current].append(int(tok, 16))
                except ValueError:
                    pass
    if 'mod_data_head_bytes' in values:
        raw = bytes(values.pop('mod_data_head_bytes'))
        values['mod_data_head'] = [int.from_bytes(raw[i:i+8], 'little')
                                   for i in range(0, len(raw), 8)]
    return values


def recover_font_storage_from_raw(text: str, base: int,
                                  values: dict[str, list[int]]) -> dict[str, str]:
    """只恢复同一 raw 已读到且地址与 ELF 匹配的 Font u32，不用邻居关系猜值。"""
    fields = ('g_FontStorageAllocations', 'g_FontStorageLive',
              'g_FontStorageLivePeak', 'g_FontStorageFailures')
    recovered: dict[str, str] = {}
    source = None
    for line in text.splitlines():
        if line.startswith('TAG '):
            source = line[4:].strip()
            continue
        if source not in fields or source not in SYMS or not base:
            continue
        match = re.match(r'^0x([0-9a-f]+)\s*(?:<[^>]*>)?:\s*(.*)', line)
        if not match:
            continue
        address = int(match.group(1), 16)
        if address != base + SYMS[source]:
            continue  # 指定的 ELF 与原始取数地址不一致，禁止恢复。
        words = [int(tok, 16) for tok in match.group(2).split()
                 if re.fullmatch(r'0x[0-9a-f]+', tok)]
        raw = words_to_bytes(words)
        for key in fields:
            if values.get(key) or key not in SYMS:
                continue
            offset = base + SYMS[key] - address
            if 0 <= offset <= len(raw) - 4:
                values[key] = [int.from_bytes(raw[offset:offset + 4], 'little')]
                recovered[key] = f'{source} 原始字节 @0x{address + offset:x}（ELF 地址一致）'
    return recovered


def parse_mappings(text: str) -> list[tuple[int, int, str, str]]:
    """解析 `monitor get mappings`：返回 [(起, 止, 权限, 种类)]。

    格式（实测）：
      `0x2f80800000 - 0x2f80fcefff rw- Normal           ---- [0, 0]`
      `0x18d2c0e000 - 0x18d2c0efff rw- SharedCode       ---- [0, 0]`
    只有带权限字母（不是 `---`）的段才是真的映射过的。
    """
    out: list[tuple[int, int, str, str]] = []
    for line in text.splitlines():
        m = re.match(r'\s*0x([0-9a-f]+)\s*-\s*0x([0-9a-f]+)\s+([rwx-]{3})\s+(\S+)', line)
        if not m:
            continue
        perms = m.group(3)
        if perms == '---':
            continue
        out.append((int(m.group(1), 16), int(m.group(2), 16), perms, m.group(4)))
    return out


def scan_candidates(maps: list[tuple[int, int, str, str]], minimum_size: int) -> list[int]:
    """从映射表里挑出"可能装着那个模块"的段起点（`locate_by_scan` 的候选筛选）。

    **必须按权限筛**：要认的指纹是**代码**（身份函数头 16 字节、入口函数序言），只有可执行段
    才可能命中。2026-09-16 实测：不筛权限时一次要读 115 个段，输出被堆/共享内存挤满，
    真正的候选反而被截断 —— 那是"看起来在读、其实白读一次 attach"的典型（attach 预算很贵）。

    纯函数，门禁测试直接钉（在设备上试错的代价是挂载预算）。
    """
    return [start for start, end, perm, kind in maps
            if 'x' in perm and end - start > minimum_size
            and kind not in ('Stack', 'SharedCode')]


def locate_by_scan(session: 'GdbSession', elf: Path, *, max_candidates: int = 48
                   ) -> tuple[int | None, int | None]:
    """`monitor get info` 不给模块清单时的兜底：扫内存映射，按**内容指纹**认出两个模块。

    为什么能这么认：身份函数那 16 字节是**我们自己的代码**，只有我们的运行时模块里才有；
    而 `Manager::Update` 入口那 8 字节要么是原版序言、要么是我们自己的入口中继桩，二者都认识。
    两处都只用"模块起始 + 已知偏移"，不依赖调试桩的模块表。
    """
    # ★★ 2026-09-27 改：**最多读三次段表**，每次都把"这次新出现的候选"试一遍。
    #
    # 为什么不是"读一次、失败再补读一次"：`monitor get mappings` 在 `attach` 刚返回时给的表
    # **可以一次比一次完整**（同一次挂载里慢慢补齐）。实测两种坏形态：
    #   * 2026-09-27 上午：**119 段、可执行候选只剩 1 个**（那一个是游戏模块的 `AliasCode`），
    #     而同一次会话末尾再问就给出了含我们代码段的完整列表（7 个可执行段）；
    #   * 2026-09-27 中午：**126 段、候选又只剩 1 个**，我补的那次重读**也没拿到新候选** ⇒
    #     还是认不出来、还是被读成"游戏没在运行"（而游戏明明在跑，用户报的就是局内）。
    # ⇒ 判据是"**还没认出模块**"（不是"段数少"），动作是**再读一次并把新候选也试掉**，最多三轮。
    identity_expect = local_bytes(elf, SYMS['identity'], 16)
    module = game = None
    tried: set = set()
    candidates: list = []
    values: dict = {}
    for attempt in range(3):
        maps = parse_mappings(session.command('monitor get mappings'))
        if not maps:
            continue
        candidates = scan_candidates(maps, SYMS['identity'] + 0x100)[:max_candidates]
        if attempt == 0:
            print(f'  （monitor get info 没给模块表，改用 mappings 扫描：{len(maps)} 段里 '
                  f'{len(candidates)} 个可执行候选）')
        fresh = [start for start in candidates if start not in tried]
        if not fresh:
            print(f'  （第 {attempt + 1} 次读段表：{len(maps)} 段 / {len(candidates)} 个候选，'
                  '没有新东西 ⇒ 再读一次）')
            continue
        tried.update(fresh)
        cmds = []
        for i, start in enumerate(fresh):
            cmds.append(f'echo TAG cand_{i}\\n')
            cmds.append(f'x/2gx 0x{start + SYMS["identity"]:x}')
            cmds.append(f'echo TAG game_{i}\\n')
            cmds.append(f'x/2gx 0x{start + SYMS["manager_update_entry"]:x}')
        values = parse_words(session.command('\n'.join(cmds)))
        for i, start in enumerate(fresh):
            got = b''.join(v.to_bytes(8, 'little')
                           for v in (values.get(f'cand_{i}') or [])[:2])
            if got and got == identity_expect and module is None:
                module = start
            entry = values.get(f'game_{i}') or []
            if entry and game is None:
                word = entry[0] & 0xFFFFFFFF
                # 我们的入口中继桩（`ldr x16,#8; br x16`）或原版 `Manager::Update` 序言。
                if word in (0x58000050, 0xFF4301D1):
                    game = start
        if module is not None and game is not None:
            if attempt > 0:
                print(f'  ★ 第 {attempt + 1} 次读段表才认出来（前几次的段表不完整）：'
                      f'运行时模块基址 = 0x{module:x}、游戏模块基址 = 0x{game:x}')
            break
        if attempt < 2:
            print(f'  （第 {attempt + 1} 次读段表：{len(maps)} 段 / {len(candidates)} 个候选、'
                  f'新增 {len(fresh)} 个 —— 还没对上，再读一次）')
    # 候选被拒时**把"读到什么 / 期望什么"打出来**（2026-09-18 加）。
    #
    # 为什么值得打：此前这条路的失败信息只有一句"基址没取全"，看不出是"段起点不是模块基址"
    # 还是"这段根本不是我们的模块"，于是每次都要再烧一次 attach 去猜。而 attach 在同一个
    # 启动周期里是**会退化**的（第二次常常连映射表都读不到）⇒ 第一跳拿不到线索就等于这轮报废。
    # 这里多打的两行不增加任何一次内存读取（值已经在 `values` 里）。
    if module is None:
        for i, start in enumerate(candidates):
            got_words = (values.get(f'cand_{i}') or [])[:2]
            if not got_words:
                print(f'  · 候选 {i} {start:#x}：读不到（该地址不可读）')
                continue
            got_first = got_words[0] & 0xFFFFFFFF
            want_first = int.from_bytes(identity_expect[:4], 'little')
            print(f'  · 候选 {i} {start:#x}：identity 处读到 {got_first:#010x}，'
                  f'期望 {want_first:#010x}'
                  + ('  ← 相同（说明只是缺少后续字节）' if got_first == want_first else
                     '  ← 不同 ⇒ 这个段的起点不是我们的模块基址'))
    if game is None and candidates:
        entry_words = (values.get('game_0') or [])[:1]
        if entry_words:
            print(f'  · 候选 0 的 Manager::Update 处读到 {(entry_words[0] & 0xFFFFFFFF):#010x}'
                  f'（期望 0x58000050 中继桩 / 0xff4301d1 原版序言）')
    if module is None:
        # 认不出来时把可执行段**列出来**：本次就是靠这个列表手工认出 `0x60f5381000`
        # （我们模块的代码段 499711 字节 ≈ code_end 0x790c0），然后用 `--base` 直接读，
        # 不必再挂一次设备。
        print('  ⚠ 没能按指纹认出模块。可执行段（可据此用 --base 手工指定）：')
        for start, end, perm, kind in parse_mappings(session.command('monitor get mappings')):
            if 'x' in perm:
                print(f'      0x{start:x}-0x{end:x} {kind} 大小={end - start}')
    return module, game


ENTITY_FIELD_WRITES_BYTES = 21 * 4  # 旧包无ELF时的已知边界；新包按真实符号size刷新


def sync_syms_from_elf(elf: Path, *, verbose: bool = False) -> dict[str, str]:
    """用**本地这份 ELF**的符号表刷新"模块内偏移"，返回没解析到的符号。

    为什么要有这一步：偏移表是手抄的，而**改任何一个编译单元都会让 bss/data 整体挪位**
    （项目已经因此误读过两次）。手抄表一定会过期，唯一不会过期的来源就是 ELF 自己。
    解析不到的符号**直接从表里删掉**——沿用过期的偏移比读不到更糟：它会把别人的变量
    当成我们要的那个，读数"看起来有值"却是错的。
    """
    global _syms_synced, IMAGE_PCX_DIAG_BYTES, MOD_DATA_CACHE_BYTES, CALLBACK_REGISTRY_COUNT_OFFSET, CALLBACK_REGISTRY_LAYOUT_KNOWN, ENTITY_FIELD_WRITES_BYTES
    tools_dir = str(Path(__file__).resolve().parent)
    if tools_dir not in sys.path:
        sys.path.insert(0, tools_dir)
    import elf_syms  # 同目录的极简 ELF 解析器（只依赖标准库）

    CALLBACK_REGISTRY_LAYOUT_KNOWN = False
    if not elf.exists():
        _syms_synced = False
        print(f'  ⚠ 找不到本地 ELF（{elf}），沿用表内偏移 —— 读数可能与当前构建不符')
        return {'(整个 ELF)': '文件不存在'}
    symbols = elf_syms.load_symbols(elf.read_bytes())
    if not symbols:
        _syms_synced = False
        print(f'  ⚠ {elf} 里没有 .symtab（被 strip 过？），沿用表内偏移')
        return {'(整个 ELF)': '没有符号表'}

    missing: dict[str, str] = {}
    probe_build_only_absent: list[str] = []
    for key, name in {**SYM_ELF_NAMES, **SYM_ELF_NAMES_OPTIONAL, **SYM_ELF_NAMES_PROBE_ONLY,
                    **SYM_ELF_NAMES_PROBE_BUILD_ONLY}.items():
        hit = symbols.get(name)
        if hit is None:
            missing[key] = name
            SYMS.pop(key, None)
            if key in SYM_ELF_NAMES_PROBE_BUILD_ONLY:
                # ★ 批次 232：这一档的缺席是**设计如此**（正式包不编进探针采集 ⇒ 符号被 GC 掉），
                #   与"符号改名/过期"不是一回事 ⇒ 分开记账、分开报，别让 77 条噪声淹没真问题。
                probe_build_only_absent.append(key)
        else:
            SYMS[key] = hit[0]
    for key in SYM_UNRESOLVABLE:            # 这次构建里已经不存在的全局量
        SYMS.pop(key, None)
        missing[key] = '（本构建已无此全局量）'
    SYM_MISSING.clear()
    SYM_MISSING.update(missing)
    SYM_PROBE_BUILD_ABSENT.clear()
    SYM_PROBE_BUILD_ABSENT.extend(sorted(probe_build_only_absent))
    # 贴图桥诊断结构体在本构建里到底多大 —— 后面按它决定"哪几段字段真的存在"。
    # ★ 注意：`SYMS[key]` 在**上面那个循环之后**已经变成**地址**（`hit[0]`），不再是符号名
    #   ⇒ 必须回头查这张名字表拿 mangled 名（第一版就是在这里取错、读成 0 字节的）。
    diag_name = {**SYM_ELF_NAMES, **SYM_ELF_NAMES_PROBE_ONLY,
                 **SYM_ELF_NAMES_PROBE_BUILD_ONLY}.get('image_pcx_diag')
    diag_symbol = symbols.get(diag_name) if diag_name else None
    IMAGE_PCX_DIAG_BYTES = int(diag_symbol[1]) if diag_symbol else 0
    cache_symbol = symbols.get(SYM_ELF_NAMES['g_ModDataCache'])
    MOD_DATA_CACHE_BYTES = int(cache_symbol[1]) if cache_symbol else 0
    write_symbol = symbols.get(SYM_ELF_NAMES['g_EntityFieldWrites'])
    ENTITY_FIELD_WRITES_BYTES = int(write_symbol[1]) if write_symbol else 0
    registry_symbol = symbols.get(SYM_ELF_NAMES.get('g_CallbackRegistry', ''))
    registry_size = registry_symbol[1] if registry_symbol else 0
    registry_count_offset = {0x2008: 0x2000, 0x2508: 0x2500, 0x2d08: 0x2d00}.get(registry_size)
    if registry_count_offset is not None:
        CALLBACK_REGISTRY_COUNT_OFFSET = registry_count_offset
        CALLBACK_REGISTRY_LAYOUT_KNOWN = True
    _syms_synced = True
    if verbose:
        print(f'  偏移已按 {elf.name} 的符号表刷新（主表 {len(SYM_ELF_NAMES)} 项）')
        stale = sorted(k for k in missing if k not in SYM_ELF_NAMES_PROBE_BUILD_ONLY)
        if stale:
            print(f'  ⚠ 未解析到（读数会显示"读不到"）：{", ".join(stale)}')
        if probe_build_only_absent:
            print(f'  · 本构建没有探针包（DIAGNOSTIC_PROBES=0）⇒ 这 {len(probe_build_only_absent)} 项'
                  f'不采集、符号也不在 ELF 里（正常，不是过期）。要读数请出 `DIAGNOSTIC_PROBES=1` 的包。')
    return missing


def locator_session():
    """读数前的公共准备：刷新偏移表。所有对外入口都该走它，避免漏刷新。"""
    sync_syms_from_elf(ROOT / DEFAULT_ELF)


def local_bytes(elf: Path, vaddr: int, count: int) -> bytes | None:
    data = elf.read_bytes()
    e_phoff, = struct.unpack_from('<Q', data, 0x20)
    e_phentsize, e_phnum = struct.unpack_from('<HH', data, 0x36)
    for i in range(e_phnum):
        o = e_phoff + i * e_phentsize
        p_type, = struct.unpack_from('<I', data, o)
        if p_type != 1:
            continue
        p_offset, p_vaddr, _p, p_filesz = struct.unpack_from('<QQQQ', data, o + 8)
        if p_vaddr <= vaddr < p_vaddr + p_filesz:
            start = p_offset + (vaddr - p_vaddr)
            return data[start:start + count]
    return None


def build_requests(base: int, game_base: int, plugin_base: int):
    """一次挂载里要读完的全部地址（挑最少的字节数换最有用的信息）。

    返回 `(要读的清单, 被跳过的键)`。**缺偏移的量只跳过、不抛异常**：调试桩一个启动周期
    只能 attach 几次，缺一个符号名就让整次 attach 白烧（2026-09-16 真发生过）。
    """
    skipped: list = []
    req = [(name, base + offset, 1) for name, offset in SYMS.items() if name not in SYM_ONLY]
    req += [
        ('anchors', base + SYMS['identity'], 2),          # 版本核对：身份函数头 16 字节
        ('anchor_exl_main', base + SYMS['exl_main'], 2),  # 版本核对：入口函数头
        ('anchor_manifest', base + SYMS['manifest_install'], 2),  # 版本核对：诊断改动的那个函数
        ('manifest_state', base + SYMS['g_DefaultManifestState'], 1),
        ('auto_appended_mods', base + SYMS['g_AutoAppendedMods'], 1),
        ('auto_append_status', base + SYMS['g_AutoAppendStatus'], 1),
        ('hook_results', base + SYMS['g_HookInstallResults'], 5),
        ('update_entries', base + SYMS['g_UpdateCallbackEntries'], 1),
        ('render_entries', base + SYMS['g_RenderCallbackEntries'], 1),
        # 2026-10-05 排查：渲染回调那条命脉的逐环判据（各自独立全局 ⇒ 一个一个读）。
        ('render_present_relay_entries', base + SYMS['g_RenderPresentRelayEntries'], 1),
        ('default_callback_gate', base + SYMS['g_DefaultCallbackGate'], 1),
        ('lua_game_owner_slot', base + SYMS['g_LuaGameOwnerSlot'], 1),
        ('lua_game_ispaused_thunk', base + SYMS['g_LuaGameIsPausedThunk'], 1),
        ('last_is_paused', base + SYMS['g_LastIsPaused'], 1),
        ('music_get_current_id', base + SYMS['g_MusicGetCurrentMusicId'], 1),
        ('render_frame_manager', base + SYMS['g_RenderFrameManager'], 1),
        ('music_resolve_failure', base + SYMS['g_MusicResolveFailure'], 1),
        # 批次 408：`SFXManager:Play` 探针（9 个 u32，各自独立地址 ⇒ 逐个读 1 个字）。
        ('sfx_play_calls', base + SYMS['g_SfxPlayCalls'], 1),
        ('sfx_play_delivered', base + SYMS['g_SfxPlayDelivered'], 1),
        ('sfx_play_last_id', base + SYMS['g_SfxPlayLastId'], 1),
        ('sfx_play_last_volume', base + SYMS['g_SfxPlayLastVolume'], 1),
        ('sfx_play_last_frame_delay', base + SYMS['g_SfxPlayLastFrameDelay'], 1),
        ('sfx_play_last_loop', base + SYMS['g_SfxPlayLastLoop'], 1),
        ('sfx_play_last_pitch', base + SYMS['g_SfxPlayLastPitch'], 1),
        ('sfx_play_last_pan', base + SYMS['g_SfxPlayLastPan'], 1),
        ('sfx_play_last_failure', base + SYMS['g_SfxPlayLastFailure'], 1),
        ('deepest_owner_observation', base + SYMS['g_DeepestGameOwnerObservation'], 1),
        ('callback_error', base + SYMS['g_CallbackError'], 1),
        ('self_journal', base + SYMS['g_selfJournalServiceState'], 1),
        # ★ 这几个量是**分散**排布的（链接器按大小/对齐重排过），所以逐个地址各读各的，
        #   绝不能当成一个连续数组一次读出来 —— 2026-09-16 第一版就是这么写错的。
        ('self_journal_records', base + SYMS['g_selfJournalTotalRecords'], 1),
        ('self_journal_marker', base + SYMS['g_selfJournalLastMarker'], 1),
        ('lua_error_text', base + SYMS['g_LastLuaErrorText'], 32),
        # 8 条 × 128 字节 = 1024 字节（按 8 字节字读 ⇒ 128 个字）；计数单独一个全局。
        ('lua_error_history', base + SYMS['g_LuaErrorHistory'], 128),
        ('lua_error_history_count', base + SYMS['g_LuaErrorHistoryCount'], 1),
        # 历史内嵌布局仅用于旧ELF；当前动态Cache在下方按符号大小另建请求。
        ('mod_data_tail', base + SYMS['g_ModDataCache'] + 0x4000, 3),  # 模组数据容器尾部（见 SYMS 注释）
        # 模组数据容器的**开头 1 KiB**：记录表（每条 24 字节头 + 值，见
        # `ModPersistence::detail::RecordAt`）。读它就能把探针写进 `Mod:SaveData` 的文本
        # 从内存里取回来 —— **不依赖屏幕、不依赖 Lua 错误槽**（2026-09-18：探索针的屏幕读数
        # 只画了一帧就没了，正是靠这条通道才把结论拿到手）。
        # ⚠️ 窗口必须**盖住整个 payload**，否则记录表会在中间"走不通就停"，
        # 而现象是"某条模组的记录不见了"（2026-09-20 实测：EID 的配置记录比 GoodTrip 的大，
        # 4096 字节的窗口正好把它切掉 ⇒ 读数里只有别的模组）。
        # 容器容量是 0x4000（16 KiB）、当前用量在 `mod_data_tail` 里报；这里给 8192 字节。
        # 447起不再从指针变量后盲读8192B；动态记录需按当前Cache布局解引用。
        # API 调用序列（`ApiSequenceState` 的声明顺序：u64 mainMask、u64 secondaryMask、
        # u32 drawCalls、u32 drawBytes、u32 itemConfigFound、u32 itemConfigMissing、
        # u64 filterMask、u32 lastPrimary、u32 lastPrimaryCalls）—— 读前 5 个字（40 字节）够用。
        ('api_sequence', base + SYMS['g_ApiSequence'], 5),
        # 批次 250：原生状态回退（`NativeFallbackState` = u32 count + u32 lastApi ⇒ 1 个字）。
        ('native_fallback', base + SYMS['g_NativeFallback'], 1),
        ('manifest_head', base + SYMS['g_DefaultManifest'], 24),   # 清单原文前 192 字节
        ('entry_head', base + SYMS['g_DefaultEntry'], 8),          # 入口脚本前 64 字节
        # 回调登记表：**按字节**解（每项 20 字节，见 `decode_callback_entries`）。
        # 请求 90 个 8 字节字 = 720 字节 ⇒ 够看满 36 条登记（容量 256 条，EID 一家约 34 条）。
        # ★ 2026-10-08（排查 MCM 打不开）：**整张表读满**（原来只读 90 字 = 36 条，
        #   而容量 256 条 ⇒ 关键的那几条（例如某个 owner 的 `MC_POST_RENDER`）
        #   经常落在"前 3 后 3"之外，看不到就无从判"它到底注册上没有"。
        #   360 字 = 144 条 ≥ 常见条数；不够也不影响（下面的解码只取 count 条）。
        ('callback_registry', base + SYMS['g_CallbackRegistry'], 360),
        ('callback_count', base + SYMS['g_CallbackRegistry'] + CALLBACK_REGISTRY_COUNT_OFFSET, 1),
        # 批次 109：`Input.IsActionTriggered` **每个动作报过几次**（32 个 u32 = 16 个字）。
        # 用途：按**一次**键之后读这里 —— 某个动作 +2 就是"一次按键报了两次边沿"
        # （用户实测的"按一次跳两格"就是这么来的）；+1 才是正常。
        ('input_edge_counts', base + SYMS['g_InputEdgeCounts'], 16),
        # 批次 110 建、批次 221 改口径：最长"闪断"帧数（32 个 u32 = 16 个字）。
        # 批次 221 起边沿是**严格相邻帧差分** ⇒ 闪断会**直接多报边沿**（没有窗口挡它了）。
        ('input_release_peak', base + SYMS['g_InputReleaseRunPeak'], 16),
        # 批次 209：按键号那三条查询的两个掩码（各 1 个 u32，走 `first_u32`）。
        ('input_button_pressed', base + SYMS['g_InputButtonPressedMask'], 1),
        ('input_button_queried', base + SYMS['g_InputButtonQueriedMask'], 1),
        # 批次 213：边沿间隔（32 个 u32 = 128 字节 = 16 个字）。
        ('input_edge_gap_min', base + SYMS['g_InputEdgeGapMin'], 16),
        ('input_edge_gap_last', base + SYMS['g_InputEdgeGapLast'], 16),
        # 批次 381（2026-10-06）：**"帧上采样"机制本身的现场**（5 个 `std::atomic<uint32_t>`
        # 标量，各 1 个 u32）。用途见 `SYM_ELF_NAMES` 里那 5 个键的注释。
        ('input_sample_frame', base + SYMS['g_InputSampleFrame'], 1),
        ('input_sample_calls', base + SYMS['g_InputSampleCalls'], 1),
        ('input_sample_codes', base + SYMS['g_InputSampleCodes'], 1),
        ('input_sample_devices', base + SYMS['g_InputSampleDevices'], 1),
        ('input_sample_failures', base + SYMS['g_InputSampleFailures'], 1),
        # 批次 222：每帧"全动作快照" —— 我们**自己**把全部动作号/按键号各问一遍
        # （口径与三条纪律见 `input_api.cpp` 里 `g_InputSnapshotFrame` 的声明处）。
        # 用途：真机上"推摇杆下"时 MCM 问的那 10 个号里只有 `ACTION_PILLCARD(10)` 为真，
        # 另外 18 个号是黑的 ⇒ 这段把它们全暴露出来。
        ('input_snapshot_frame', base + SYMS['g_InputSnapshotFrame'], 1),
        ('input_action_snapshot_pressed', base + SYMS['g_InputActionSnapshotPressed'], 1),
        ('input_button_snapshot_pressed', base + SYMS['g_InputButtonSnapshotPressed'], 1),
        ('input_action_snapshot_value', base + SYMS['g_InputActionSnapshotValue'], 16),
        # 批次 223："动作 → 绑定的按钮码"表的现场（查"+17 错位"的根因；表只采一次）。
        ('input_binding_dump_done', base + SYMS['g_InputBindingDumpDone'], 1),
        ('input_binding_action_count', base + SYMS['g_InputBindingActionCount'], 1),
        ('input_binding_ptr', base + SYMS['g_InputBindingArrayPtr'], 16),
        ('input_binding_codes', base + SYMS['g_InputBindingCodes'], 64),
        # 批次 224：设备内部输入状态（模拟量 / 位图 / 死区；每帧采）。
        ('input_device_state_dump_count', base + SYMS['g_InputDeviceStateDumpCount'], 1),
        ('input_device_state_enabled', base + SYMS['g_InputDeviceStateEnabled'], 1),
        ('input_device_state_action_count', base + SYMS['g_InputDeviceStateActionCount'], 1),
        ('input_device_state_keys_current', base + SYMS['g_InputDeviceStateKeysCurrent'], 1),
        ('input_device_state_keys_previous', base + SYMS['g_InputDeviceStateKeysPrevious'], 1),
        ('input_device_state_stick_current', base + SYMS['g_InputDeviceStateStickCurrent'], 1),
        ('input_device_state_stick_previous', base + SYMS['g_InputDeviceStateStickPrevious'], 1),
        ('input_device_state_deadzone', base + SYMS['g_InputDeviceStateDeadzone'], 1),
        ('input_device_state_deadzone_alt', base + SYMS['g_InputDeviceStateDeadzoneAlt'], 1),
        ('input_device_state_action_value', base + SYMS['g_InputDeviceStateActionValue'], 32),
        ('input_device_state_axes', base + SYMS['g_InputDeviceStateAxes'], 4),
        # 批次 225：设备对象**整块原始内存**（用户要求"读全"，不再逐字段猜）。
        ('input_device_raw_dump_count', base + SYMS['g_InputDeviceRawDumpCount'], 1),
        ('input_device_raw_pointer_low', base + SYMS['g_InputDeviceRawPointerLow'], 1),
        ('input_device_raw_pointer_high', base + SYMS['g_InputDeviceRawPointerHigh'], 1),
        ('input_device_raw_id', base + SYMS['g_InputDeviceRawId'], 1),
        ('input_device_raw_head', base + SYMS['g_InputDeviceRawHead'], 64),      # 128 u32
        ('input_device_raw_tail', base + SYMS['g_InputDeviceRawTail'], 20),      # 40 u32
        ('input_device_raw_values', base + SYMS['g_InputDeviceRawValues'], 16),
        ('input_device_raw_values_previous', base + SYMS['g_InputDeviceRawValuesPrevious'], 16),
        ('input_device_table_count', base + SYMS['g_InputDeviceTableCount'], 1),
        ('input_device_table_pointer', base + SYMS['g_InputDeviceTablePointer'], 4),
        # 批次 226：表项指针的**高 32 位** + "当次选中的设备号"（修"只存低 32 位被截断"与
        # "缓存旧设备指针导致同帧两份数据不一致"这两个 bug）。
        ('input_device_table_pointer_high', base + SYMS['g_InputDeviceTablePointerHigh'], 4),
        ('input_device_selected_id', base + SYMS['g_InputDeviceSelectedId'], 1),
        # 批次 227：表/来源的一致性验证（连读两遍 + 来源核对 + 选中项下标）。
        ('input_device_raw_manager_low', base + SYMS['g_InputDeviceRawManagerLow'], 1),
        ('input_device_raw_manager_high', base + SYMS['g_InputDeviceRawManagerHigh'], 1),
        ('input_device_raw_begin_low', base + SYMS['g_InputDeviceRawBeginLow'], 1),
        ('input_device_raw_begin_high', base + SYMS['g_InputDeviceRawBeginHigh'], 1),
        ('input_device_raw_end_low', base + SYMS['g_InputDeviceRawEndLow'], 1),
        ('input_device_raw_end_high', base + SYMS['g_InputDeviceRawEndHigh'], 1),
        ('input_device_raw_begin_pass2_low', base + SYMS['g_InputDeviceRawBeginPass2Low'], 1),
        ('input_device_raw_begin_pass2_high', base + SYMS['g_InputDeviceRawBeginPass2High'], 1),
        ('input_device_raw_end_pass2_low', base + SYMS['g_InputDeviceRawEndPass2Low'], 1),
        ('input_device_raw_end_pass2_high', base + SYMS['g_InputDeviceRawEndPass2High'], 1),
        ('input_device_table_pass2_count', base + SYMS['g_InputDeviceTablePass2Count'], 1),
        ('input_device_table_pass2_pointer', base + SYMS['g_InputDeviceTablePass2Pointer'], 4),
        ('input_device_table_pass2_pointer_high',
         base + SYMS['g_InputDeviceTablePass2PointerHigh'], 4),
        ('input_device_table_pass2_id', base + SYMS['g_InputDeviceTablePass2Id'], 4),
        ('input_device_selected_index', base + SYMS['g_InputDeviceSelectedIndex'], 1),
        # 批次 229：读表失败的次数（>0 ⇒ 表里有格子读不到，别把哨兵 0xFFFFFFFF 当真值）。
        ('input_device_table_read_failures', base + SYMS['g_InputDeviceTableReadFailures'], 1),
        ('input_device_table_id', base + SYMS['g_InputDeviceTableId'], 4),
        # 批次 235：启动期"读模组"分段计时。数组按 **u32** 读（`first_u32` 是按 8 字节字取的，
        # 数组要用下面 `_u32_at` 那一套解码 —— 这是 232 查出来的老坑）。
        ('load_phase_micros', base + SYMS['g_LoadPhaseMicros'], 4),        # 8 个 u32 = 4 个字
        ('load_total_micros', base + SYMS['g_LoadTotalMicros'], 1),
        ('mod_load_micros', base + SYMS['g_ModLoadMicros'], 8),            # 16 个 u32 = 8 个字
        ('mod_load_count', base + SYMS['g_ModLoadCount'], 1),
        ('mod_load_total', base + SYMS['g_ModLoadTotal'], 1),
        ('load_frames_used', base + SYMS['g_LoadFramesUsed'], 1),
        # 批次 210：发布槽（0 = 守卫没过 ⇒ 那两条 API 恒答假值）。
        ('input_button_thunk', base + SYMS['g_InputIsButtonPressed'], 1),
        ('input_get_button_value_thunk', base + SYMS['g_InputGetButtonValue'], 1),
        # 批次 211：PC→NS 手柄号映射的现场（最近一次翻译 + 兜底次数）。
        ('input_controller_map_pc_id', base + SYMS['g_InputControllerMapPcId'], 1),
        ('input_controller_map_ns_id', base + SYMS['g_InputControllerMapNsId'], 1),
        ('input_controller_map_outcome', base + SYMS['g_InputControllerMapOutcome'], 1),
        ('input_controller_map_fallbacks', base + SYMS['g_InputControllerMapFallbacks'], 1),
        # 批次 230：动作号翻译的现场（最近一次"模组号 → 引擎内部号" + 因平台上没有而直接回答的次数）。
        ('input_action_map_lua_code', base + SYMS['g_InputActionMapLuaCode'], 1),
        ('input_action_map_engine_code', base + SYMS['g_InputActionMapEngineCode'], 1),
        ('input_action_map_absent', base + SYMS['g_InputActionMapAbsent'], 1),
        # 批次 212：玩家字段写（4 个计数 + 被拒 + 最近写的字段名哈希）。
        ('entity_field_writes', base + SYMS['g_EntityFieldWrites'],
         (ENTITY_FIELD_WRITES_BYTES + 7) // 8),
        ('entity_field_write_rejected', base + SYMS['g_EntityFieldWriteRejected'], 1),
        ('last_entity_field_write_name', base + SYMS['g_LastEntityFieldWriteName'], 1),
        # 批次 214：`Seeds:AddSeedEffect`/`RemoveSeedEffect` 被调用的次数（>0 = 模组真的走了那两条路）。
        ('seeds_effect_write_attempts', base + SYMS['g_SeedsEffectWriteAttempts'], 1),
        # 批次 217：每个动作"最后一次被问"的四项现场（各 32 个 u32）。
        ('input_action_asked_frame', base + SYMS['g_InputActionAskedFrame'], 32),
        ('input_action_asked_kind', base + SYMS['g_InputActionAskedKind'], 32),
        ('input_action_asked_controller', base + SYMS['g_InputActionAskedController'], 32),
        ('input_action_asked_answer', base + SYMS['g_InputActionAskedAnswer'], 32),
        # 批次 218：按键侧的边沿计数（与动作侧**分开**）与"最后一次被问"的四项现场。
        ('input_button_edge_counts', base + SYMS['g_InputButtonEdgeCounts'], 16),
        ('input_button_asked_frame', base + SYMS['g_InputButtonAskedFrame'], 32),
        ('input_button_asked_kind', base + SYMS['g_InputButtonAskedKind'], 32),
        ('input_button_asked_controller', base + SYMS['g_InputButtonAskedController'], 32),
        ('input_button_asked_answer', base + SYMS['g_InputButtonAskedAnswer'], 32),
        # 批次 219：两侧"最后一次真的被激活"的帧号（各 32 个 u32）。
        ('input_action_held_frame', base + SYMS['g_InputActionHeldFrame'], 32),
        ('input_button_triggered_frame', base + SYMS['g_InputButtonTriggeredFrame'], 32),
    ]
    # 批次 379（2026-10-06）：按键侧上升沿表的两行本体（布局见 `BUTTON_EDGE_*` 常量）。
    #   * 行 1  = `controller & 31 == 1` ⇒ 真机那台手柄（设备 33）—— MCM 的
    #     `Input.IsButtonTriggered(13, 1)`（PC 的"第 1 台手柄"）经翻译后正落在这里；
    #   * 行 31 = `0xFFFFFFFF`（引擎的"任意设备"）—— 模组直接传 33 之外的 NS 原生态时落这里。
    # 只在符号解析到时才加这两条：`SYMS` 缺键会退化成 `base + 0`，而这里的地址是
    # `base + 偏移`（不等于 base）⇒ 上面那条"缺偏移就丢掉"的守卫**抓不到**它。
    if SYMS.get('g_ButtonEdge'):
        req.append(('input_button_edge_row_gamepad',
                    base + SYMS['g_ButtonEdge'] + BUTTON_EDGE_ROW_BYTES, 80))
        req.append(('input_button_edge_row_any',
                    base + SYMS['g_ButtonEdge'] + 31 * BUTTON_EDGE_ROW_BYTES, 80))
    req += [
        # 批次 192：触摸屏 → 指针（8 个 u32，逐项分明，不用整块解）。
        # 这一组回答三件事：初始化成没成、到底读没读、**手指的原始坐标是多少**
        #（最后一项是本批的核心产出 —— 坐标换算要靠它，不靠猜）。
        ('touch_init_state', base + SYMS['g_TouchPointerInitState'], 1),
        ('touch_scan_attempts', base + SYMS['g_TouchPointerScanAttempts'], 1),
        ('touch_shmem_low', base + SYMS['g_TouchPointerShmemLow'], 1),
        ('touch_shmem_high', base + SYMS['g_TouchPointerShmemHigh'], 1),
        ('touch_segments', base + SYMS['g_TouchPointerSegmentsScanned'], 1),
        ('touch_poll_frames', base + SYMS['g_TouchPointerPollFrames'], 1),
        ('touch_frames', base + SYMS['g_TouchPointerTouchFrames'], 1),
        ('touch_last_raw_x', base + SYMS['g_TouchPointerLastRawX'], 1),
        ('touch_last_raw_y', base + SYMS['g_TouchPointerLastRawY'], 1),
        ('touch_last_count', base + SYMS['g_TouchPointerLastCount'], 1),
        # 批次 193：★ "这次真的认出 lifo 了吗"的三条证据（认出那块内存时读的 lifo 表头）
        # + 两个"这块内存是活的吗"的量。批次 192 只有上面那一组，结果**一块零页**被认成了触摸屏。
        ('touch_lifo_buffer_count', base + SYMS['g_TouchPointerLifoBufferCount'], 1),
        ('touch_lifo_tail', base + SYMS['g_TouchPointerLifoTail'], 1),
        ('touch_lifo_count', base + SYMS['g_TouchPointerLifoCount'], 1),
        ('touch_rejected_mappings', base + SYMS['g_TouchPointerRejectedMappings'], 1),
        ('touch_last_sampling', base + SYMS['g_TouchPointerLastSampling'], 1),
        ('touch_last_entry_index', base + SYMS['g_TouchPointerLastEntryIndex'], 1),
        # 批次 194：小地图触摸门控补丁的三处引擎改写结果（游戏模块代码，不属我们模块）。
        ('minimap_gate_state', base + SYMS['g_MinimapTouchGateState'], 1),
        ('minimap_gate_applied', base + SYMS['g_MinimapTouchGateApplied'], 1),
        ('minimap_gate_guard_mismatch', base + SYMS['g_MinimapTouchGateGuardMismatch'], 1),
        ('minimap_gate_failure_code', base + SYMS['g_MinimapTouchGateFailureCode'], 1),
        # 回调耗时桶（批次 086）：按 `PERF_BUCKET_COUNT × PERF_BUCKET_BYTES` 整块读，
        # 旁边那个溢出计数是独立全局 ⇒ 各读各的。
        ('perf_buckets',
         base + SYMS['g_RuntimePerfCallbackBuckets'],
         (PERF_BUCKET_COUNT * PERF_BUCKET_BYTES + 7) // 8),
        ('perf_bucket_overflow', base + SYMS['g_RuntimePerfBucketOverflow'], 1),
        # 按 API 接口分开的耗时桶（批次 087）：同一套 32 字节记录，个数不同。
        ('perf_api_buckets',
         base + SYMS['g_RuntimePerfApiBuckets'],
         (PERF_API_BUCKET_COUNT * PERF_BUCKET_BYTES + 7) // 8),
        ('perf_api_bucket_overflow', base + SYMS['g_RuntimePerfApiBucketOverflow'], 1),
        ('perf_api_total_calls', base + SYMS['g_RuntimePerfApiTotalCalls'], 1),
        ('perf_api_total_ticks', base + SYMS['g_RuntimePerfApiTotalTicks'], 1),
        # Lua 采样剖析器（批次 089）：桶数组整块读，旁边两个标量各读各的。
        ('perf_profile_buckets',
         base + SYMS['g_RuntimePerfProfileBuckets'],
         (PROFILE_BUCKET_COUNT * PROFILE_BUCKET_BYTES + 7) // 8),
        ('perf_profile_samples', base + SYMS['g_RuntimePerfProfileSamples'], 1),
        ('perf_profile_overflow', base + SYMS['g_RuntimePerfProfileOverflow'], 1),
        # 分配账（批次 091）：四个独立标量各读各的。
        # ★ 2026-10-04（批次 363）：这六条在**本构建里没有符号**（见 `SYM_UNRESOLVABLE` 的注释）
        #   ⇒ 用 `perf_optional` 收集，符号不在就**不发这条请求**（而不是 KeyError 崩掉读数）。
        *[(key, base + SYMS[name], 1)
          for key, name in (('perf_alloc_calls', 'g_RuntimePerfAllocCalls'),
                            ('perf_empty_call_ticks', 'g_RuntimePerfEmptyCallTicks'),
                            ('perf_empty_call_count', 'g_RuntimePerfEmptyCallCount'),
                            ('perf_alloc_bytes', 'g_RuntimePerfAllocBytes'),
                            ('perf_alloc_new_calls', 'g_RuntimePerfAllocNewCalls'),
                            ('perf_free_calls', 'g_RuntimePerfFreeCalls'))
          if name in SYMS],
        ('perf_tick_cost', base + SYMS['g_RuntimePerfTickCostTicks'], 1),
        # 回调派发计数（2026-09-18）：74 个 u32 是**一个数组**（连续），所以一次读完；
        # 旁边那两个标量是**独立全局**（链接器可能重排）⇒ 各读各的，绝不连读。
        ('callback_dispatch_counts',
         base + SYMS['g_CallbackDispatchCounts'],
         (CALLBACK_DISPATCH_COUNTER_COUNT * 4 + 7) // 8),
        ('callback_dispatch_last', base + SYMS['g_LastDispatchedCallbackId'], 1),
        ('callback_dispatch_generation', base + SYMS['g_CallbackDispatchGeneration'], 1),
        ('filetable', base + SYMS['g_diagnosticFileApi'], 4),
        ('hook_callbacks', base + SYMS['g_hookCallbacks'], len(HOOK_NAMES)),
        *[(f'cold_{name}_source',game_base+site,1) for name,(site,gate,original) in COLD_HOOK_SITES.items()],
        *[(f'cold_{name}_gate',game_base+gate,4) for name,(site,gate,original) in COLD_HOOK_SITES.items()],
        *[(f'entity_remove_pointer_{i}',game_base+site,1)
          for i,site in enumerate(ENTITY_REMOVE_POINTER_SITES)],
        *[(f'internal_{name}_source',game_base+site,1)
          for name,(site,veneer,size) in INTERNAL_HOOK_SITES.items()],
        *[(f'internal_{name}_veneer',game_base+veneer,size//8)
          for name,(site,veneer,size) in INTERNAL_HOOK_SITES.items()],
        *[(f'internal_{name}_literal',game_base+slot,1)
          for name,slot in INTERNAL_LITERAL_SLOTS.items()],
        ('update_entry', game_base + SYMS['manager_update_entry'], 2),
        # 贴图桥 v2/v3 的挂点入口（0x4d1fe4，相对**游戏模块**）：期望是我们写进去的
        # 入口补丁（`ldr x16,#8; br x16; .quad 槽` ⇒ 首四字 `5000005800021fd6`）。
        ('imagemanager_entry', game_base + 0x4D1FE4, 2),
        # v4 新挂点的入口（相对游戏模块）：期望也是入口补丁。
        ('getmounted_entry', game_base + 0x4C2340, 2),
        # 批次 147（2026-09-26）：引擎那条"模组 content 加载"路的闸门。
        # `ModManager::LoadConfigs` 的**入口**（相对游戏模块 0x41E388）：期望是入口中继
        # 写进去的 `ldr x16,#8; br x16; .quad 槽`（首四字 = 5000005800021fd6）。
        ('modmanager_loadconfigs_entry', game_base + 0x41E388, 2),
        # ---- 批次 363（2026-10-04）：`ANM2::Load` 入口中继 ----
        # 入口（相对游戏模块 0xC970）：期望是入口中继写进去的
        # `ldr x16,#8; br x16; .quad 槽`（首四字 = 5000005800021fd6）。
        ('anm2load_entry', game_base + 0xC970, 2),
        # 状态面（8 个 u32 连续 ⇒ 一次读 4 个字 = 32 字节，正好是那个结构体）。
        # ★ 批次 384：元素数 4 → **5**（结构体从 8 个 u32 加到 10 个 u32 = 40 字节；每个元素 8 字节）。
        ('anm2load_state', base + SYMS['g_Anm2LoadOverrideState'], 5),
        # ---- 批次 378（2026-10-05）：PC 的资源层重定向（10 u32 + 192B 查询 + 224B 回答 = 456B）----
        ('mod_redirect_state', base + SYMS['g_ModResourceRedirectState'], 57),
        # ---- 批次 370 起、批次 371 改语义（2026-10-05）：早于引擎第一次读的那一段 ----
        # 结构体 = 5 个相邻 u64 + **8** 个 u32（40 + 32 = **72 字节**）⇒ 一次读 **9** 个字。
        # ★ 批次 385（2026-10-06）在末尾追加了 `[11] earlyResourceRelaysAttempted` /
        #   `[12] earlyResourceRelaysInstalled`（原来 5 个 u64 + 6 个 u32 = 64 字节 / 8 个字）。
        ('early_mount_state', base + SYMS['g_EarlyMountState'], 9),
        # 闸门的九个标量埋点：**各自独立全局** ⇒ 一个一个读，绝不连读（链接器会重排）。
        ('mod_loadcfg_calls', base + SYMS['g_ModLoadConfigsCalls'], 1),
        ('mod_loadcfg_entries', base + SYMS['g_ModLoadConfigsEntriesSeen'], 1),
        ('mod_loadcfg_enabled', base + SYMS['g_ModLoadConfigsEnabledByUs'], 1),
        ('mod_loadcfg_disabled', base + SYMS['g_ModLoadConfigsDisabledByUs'], 1),
        ('mod_loadcfg_disabled_known', base + SYMS['g_ModLoadConfigsDisabledKnown'], 1),
        ('mod_loadcfg_state_loaded', base + SYMS['g_ModLoadConfigsStateLoaded'], 1),
        ('mod_loadcfg_matched', base + SYMS['g_ModLoadConfigsMatchedDisabled'], 1),
        ('mod_loadcfg_engine_off', base + SYMS['g_ModLoadConfigsEngineOff'], 1),
        ('mod_loadcfg_write_failures', base + SYMS['g_ModLoadConfigsWriteFailures'], 1),
        ('mod_loadcfg_first_path', base + SYMS['g_ModLoadConfigsFirstPath'], 8),
        ('mod_toggle_state_loaded', base + SYMS['g_ModToggleStateLoaded'], 1),
        # ---- 批次 148（2026-09-26）：我们自己喊一次引擎那条路（触发点 = 进模组页）----
        # 同样**一个一个读**（链接器会重排）；字符串缓冲各读 8 个字 = 64 字节。
        ('mod_engine_attempts', base + SYMS['g_ModEngineScanAttempts'], 1),
        ('mod_engine_stage', base + SYMS['g_ModEngineScanStage'], 1),
        ('mod_engine_entries', base + SYMS['g_ModEngineModEntries'], 1),
        ('mod_engine_resolve_failures', base + SYMS['g_ModEngineResolveFailures'], 1),
        ('mod_engine_costume_loads', base + SYMS['g_ModEngineCostumeLoads'], 1),
        ('mod_engine_music_loads', base + SYMS['g_ModEngineMusicLoads'], 1),
        # 批次 409：`gfx/ui/mod_defaults.anm2` → `ModManager+0x368` 那一步的调用次数（正常 = 1）。
        ('mod_engine_mod_defaults_anm2_loads',
         base + SYMS['g_ModEngineModDefaultsAnm2Loads'], 1),
        ('mod_engine_path_misses', base + SYMS['g_ModEnginePathResolveMisses'], 1),
        ('music_entries_before', base + SYMS['g_MusicEntryCountBefore'], 1),
        ('music_entries_after', base + SYMS['g_MusicEntryCountAfter'], 1),
        ('costume_entries_before', base + SYMS['g_CostumeCountBefore'], 1),
        ('costume_entries_after', base + SYMS['g_CostumeCountAfter'], 1),
        # 批次 149b：路径口径（哪种让容器涨了）+ 解析回来的原始串（两个 256 字节缓冲 = 32 个字）。
        ('mod_engine_costume_form', base + SYMS['g_ModEngineCostumeForm'], 1),
        ('mod_engine_music_form', base + SYMS['g_ModEngineMusicForm'], 1),
        ('mod_engine_costume_calls', base + SYMS['g_ModEngineCostumeCalls'], 1),
        ('mod_engine_music_calls', base + SYMS['g_ModEngineMusicCalls'], 1),
        ('mod_engine_resolved_costumes', base + SYMS['g_ModEngineResolvedCostumes'], 32),
        ('mod_engine_resolved_music', base + SYMS['g_ModEngineResolvedMusic'], 32),
        # 曲目表最后一条：编号（+0x00）+ 名字 32 字节原始串（+0x08 起）。
        ('mod_engine_music_last_entry_id', base + SYMS['g_ModEngineMusicLastEntryId'], 1),
        ('mod_engine_music_last_entry_raw', base + SYMS['g_ModEngineMusicLastEntryRaw'], 4),
        # 批次 148：曲目名反查（`Isaac.GetMusicIdByName`）。
        ('music_id_calls', base + SYMS['g_IsaacMusicIdCalls'], 1),
        ('music_id_hits', base + SYMS['g_IsaacMusicIdHits'], 1),
        ('music_id_last_result', base + SYMS['g_IsaacMusicIdLastResult'], 1),
        ('music_id_table_count', base + SYMS['g_IsaacMusicIdTableCount'], 1),
        ('music_id_last_name', base + SYMS['g_IsaacMusicIdLastName'], 8),
        # 贴图桥用到的 8 个引擎绑定指针（全 0 = 守卫没过、整套绑定没发布）。
        ('image_pcx_bindings', base + SYMS['image_pcx_bindings'], 8),
        # 贴图桥诊断结构体（ImagePcxDiagnostics）：一次性读全。
        # ★ 276-perf：结构体加长到 856 字节；277 到 888；★ 279 到 896 ⇒ 这里 104 → 107 → 111 → 112 个字
        #   ★ 批次 351（2026-10-04）到 1196 字节 ⇒ 150 个字（多出来的是"非 `.pcx` 挂载查询"那几条）。
        #   ★ 批次 352（2026-10-04）到 2100 字节 ⇒ 263 个字（多出来的是"按路径记"与"主动探测"那几格）。
        #   ★ 批次 353（2026-10-04）到 4896 字节 ⇒ 612 个字（模组名单 + 四条探测路径 + 最近 6 条查询）。
        #   ★ 批次 354（2026-10-04）到 5000 字节 ⇒ 625 个字（模组**挂载成败**两张表）。
        #   ★ 批次 356（2026-10-04）到 5176 字节 ⇒ 647 个字（排除回声的计数 + 刚挂完的检查点）。
        #   ★ 批次 357（2026-10-04）到 5368 字节 ⇒ 671 个字（时间轴位图 + 重挂试验）。
        #   ★ 批次 358（2026-10-04）到 5408 字节 ⇒ 676 个字（重建中继的失败码 + 现场字节）。
        #   ★ 批次 359（2026-10-04）到 5424 字节 ⇒ 678 个字（**活路径**上的入口中继结果 + 包装调用数）。
        #   ★ 批次 360（2026-10-04）到 5440 字节 ⇒ 681 个字（自愈看门狗：检查次数 / 补挂次数）。
        #   ★ 批次 361（2026-10-04）到 5816 字节 ⇒ 727 个字（探测上下文 + 挂载后的一对测量）。
        #   （**读取长度是"够不够读新的尾字段"，而"这个字段在本构建里存不存在"必须看符号大小**，
        #    见 `IMAGE_PCX_DIAG_BYTES` 那条纪律）。
        ('image_pcx_diag', base + SYMS['image_pcx_diag'], 727),
        # L4 钩子隔离·甲案（2026-09-29 批次 196）：C++ 异常的抛出位置记录
        # （`ThrowForensics` 5 个字段 = 4 个 8 字节字：count/reserved 一个、lastFrom、
        # lastType、firstFrom）。
        ('throw_forensics', base + SYMS['g_throw_forensics'], 4),
        # 批次 019/040/041/042/043/046：原生模组页探针的诊断字（58 个 u32 = 232 字节，所以读 29 个字）。
        # 040 新增 4 格：`Menu_Title::Render` 入口中继的安装结果 + 原始失败码，以及
        # 页面空间→屏幕的偏移（`MenuManager+0x3c`）那两组 float。
        # 041 新增 2 格：可见屏幕有多大（`IsaacRepentance::WIDTH` / `HEIGHT`）——
        # 有了它才能算出"页面空间 480×270 被居中裁掉多少"。
        # 042 新增 2 格：本页**实际**被画在哪个页面坐标（目标 (240,72)）。
        # 043 新增 10 格（[32]..[41]）：条目改成**真实模组**之后的全部判据 ——
        # 数据源走没走通、发现到几个目录/几个开着、`metadata.xml` 读到几次、
        # 读文件那组绑定与 `File::Exists` 入口过没过、路径要用哪种形式。
        # 055 新增 7 格（[60]..[66]）：语言码 / 语言取到没 / 贴图那条链通到哪一步 /
        # 贴图画了几帧 / 贴图那次的页面原点拿到没 / 四种路径形态的结果与用了哪一种
        # 058 新增 15 格（[67]..[81]）：把「模组」那一格的确认键接上之后 ——
        # 进没进状态 16、驱动了几帧、页面里的选中项/按住计时/"改过没有"、
        # 我们接的确认与返回各几次、模组总开关、状态 16 的滚动目标、进入时的视图偏移。
        # 059 新增 2 格（[82]..[83]）：进模组页时把引擎的"模组总开关"置上（它原本是 0，
        # 而为 0 时页面只用一个颜色画所有行 ⇒ 切换开关在屏幕上看不出来）。
        # 060 新增 4 格（[84]..[87]）：那一格确认"接管退在哪" + `SetState` 中继装没装、挡了几次。
        # 061 新增 2 格（[88]..[89]）：`ApplyState` 真调出去的次数 / 因入口守卫不过而没调的次数
        # 062 新增 1 格（[90]）；063 新增 3 格（[91]..[93]）
        # 067 新增 3 格（[94]..[96]）；068 新增 2 格（[97]..[98]）；069 新增 1 格（[99]）
        # 071 新增、072 改语义的 9 格（[100]..[108]）：那一行改用**引擎按文件名加载贴图**
        # （`ImageManager::LoadImage(char const* path, ...)`；071 试过的 `ANM2::Load` + `ANM2::Render`
        # 真机崩了，见 `dist/crash-reports-20260923/`）之后的全部判据：
        # 路线状态 / 四条候选路径 × flag 两种取值哪条命中 / 命中掩码 /
        # Load 调用次数 / 磁盘那张图画了几帧 / 关卡切换后**从磁盘重读**几次 /
        # 命中那条路径的长度 / 命中时的 flag 取值 / 入口守卫结果。
        # ⇒ 109 个 u32 = 436 字节，读 55 个字 = 440 字节（多出的 4 字节是整字对齐，
        #   门禁 `test_probe_state_layout` 允许不足一个整字）。
        # 生产构建没有这个符号 ⇒ `SYMS[...]` 返回 0，读到的会是模块基址附近的东西；
        # 所以打印那一段会先用 `nar` 判据（[0] 必须是 1）决定要不要显示。
        ('native_mods_probe', base + SYMS['native_mods_probe'], 55),
        # 批次 078：**生产版**的「模组那一行 + 模组页」状态面（22 个 u32 = 88 字节 ⇒ 11 个字）。
        # 与上面那段探针状态面**不是同一份东西**：探针只在 `PROBE_BREAK_NATIVE_MODS_MENU` 构建里
        # 存在，这一份在生产构建里恒在。两段都会打印，哪一段有数据就看哪一段。
        # ★ 2026-09-23 起是 **26 个 u32**（[22]..[25] 是定位"换语言后 EID 坏掉"加的四格：
        #   挂载点重建中继跑过几次 / 其中失败几次 / 会话挂载服务发布了没 / 最后一次 Font:Load 的结果）。
        # ★ 2026-09-24（批次 097）起是 **40 个 u32**（[35]..[39] 是"成就闸门到底有没有被走到"
        #   的五格分段计数）⇒ 160 字节 = **20 个字**。加字段只能往后加，所以这里跟着改。
        # ★ 2026-09-24（批次 107）起是 **41 个 u32**（[40] = 处于**启用状态**的真实模组个数 ——
        #   判据从"实际加载"改成 PC 口径的"启用状态"之后，这两格必须分开记，见 `.hpp`）⇒ 164 字节 = **21 个字**。
        #   加字段只能往后加，所以这里跟着改。
        # ★ 2026-09-24（批次 116）起是 **45 个 u32**（[41]..[44] = 发现清单自证四格：
        #   清单条数 / 启用位图 / 本局加载位图 / 发现跑过没）⇒ 180 字节 = **23 个字**。
        # ★ 2026-09-25（批次 117）起是 **51 个 u32**（[45]..[50] = 局内单向闩锁六格：
        #   闩锁值 / 置位次数 / 清零次数 / 上次清零来源 / `GameExit` 被调到几次 / 闩锁可用否）
        #   ⇒ 204 字节 = **26 个字**。加字段只能往后加，所以这里跟着改。
        # ★ 2026-09-25（批次 118）起是 **54 个 u32**（[51]..[53] = "在一局里吗" +
        #   边沿写位的调用次数与结果 —— 117 的第一次真机读数暴露"闩锁在菜单上就置位"、
        #   且没有格子能分清"没写进去/写了被清掉"）⇒ 216 字节 = **27 个字**。
        # ★ 2026-09-25（批次 119）起是 **56 个 u32**（[54]..[55] = 出局时留存的污染 /
        #   把留存接回来过几次 —— 用户裁定"继续同一份存档算同一局"）⇒ 224 字节 = **28 个字**。
        # ★ 2026-09-25（批次 120）起是 **58 个 u32**（[56]..[57] = 存档分区里那个"污染过"标记
        #   我们认为它是几 / 读写失败几次 —— 用户裁定"比 PC 严"：跨重启也要保持）⇒ 232 字节 = **29 个字**。
        # ★ 2026-09-26（批次 135）起是 **60 个 u32**（[58]..[59] = 本模块堆的**空闲**/*已用*字节数，
        #   口径 newlib `mallinfo()` —— 转码峰值撞满堆那次就是靠它以后现场可见）⇒ 240 字节 = **30 个字**。
        # ★ 2026-09-27（批次 153）起是 **61 个 u32**（[60] = 「喂模组 content 给引擎」的**触发时机**：
        #   1 = 模组脚本之前 / 2 = 进模组页 —— 真机已证明"喂成功了但喂晚了"与"压根没喂"读数一模一样，
        #   必须能分开）⇒ 244 字节 = **31 个字**。
        # ★ 2026-09-27（批次 159）起是 **64 个 u32**（[62]/[63] = 引擎说「继续游戏」可不可选 /
        #   因为它不可选而跳过它的次数 —— "没有可继续的局时它不该能选中"那条 bug 就靠这两格自证）
        #   ⇒ 256 字节 = **32 个字**。
        # ★ 2026-09-28（批次 180）起是 **68 个 u32**（[64]~[67] = 进程内存总量 / 已用、
        #   系统资源池总量 / 已用）⇒ 272 字节 = **34 个字**。
        # ★ 2026-10-05（批次 378）起是 **74 个 u32**（[68]~[73] = 把"逐模组喂 content"从 2 项
        #   补到引擎那 16 项之后的六格：入口解析成功位图 / 失败位图（含 bit16 = `ModEntry::ctor`、
        #   bit17 = `std::string::assign` 桩）/ 14 项加载器调用次数 / `PostLoadMods` 次数 /
        #   `LoadCustomResources` 次数 / 真 `ModEntry` 构造次数）⇒ 296 字节 = **37 个字**。
        # ★ 2026-10-08（批次 409）起是 **75 个 u32**（[74] = 引擎 `ModManager::LoadConfigs` 尾部
        #   那一步 —— `gfx/ui/mod_defaults.anm2` 载进 `ModManager+0x368` 那个默认模组道具 ANM2
        #   的次数，正常 = 1；0 = 那一步没做 ⇒ 暂停屏画模组道具（id ≥ 733）会写 `0x80` 崩）；
        # ★ **批次 417（2026-10-08）起是 76 个**（[75] = **Lua 状态自己占多少字节**，
        #   用来把"已用 122.8 MB"拆成 Lua 侧与其它：其它 = [59] − [75]）。
        #   ⇒ **304 字节 = 38 个字**（读宽不用改：75 个时按 300 字节向上取整也读 38 个字）。
        #   加字段只能往后加 ⇒ 这里跟着改（与 `test_mod_menu_native_production.py` 的
        #   `STATE_FIELDS` 一起钉住）。
        ('mod_menu_state', base + SYMS['mod_menu_state'], 45),
        # 批次 121：游戏控制台自己的状态面（18 个 u32 = 72 字节 = **9 个字**）。
        # ★ 2026-09-25（批次 122）起是 **19 个 u32**（[18] = "被按住过的动作号"累计位图 ——
        #   [10] 只留最后一个，连打时会被顶掉，一次读数拿不到整张映射）⇒ 76 字节 = **10 个字**。
        # ★ 2026-09-25（批次 124）起是 **22 个 u32**（[19]..[21] = 总开关三格：
        #   开关值 / 被开关拒绝的命令次数 / 开关状态文件读写失败次数 —— 对应 PC 的
        #   `EnableDebugConsole`，开关本体在模组页那一行）⇒ 88 字节 = **11 个字**。
        # 加字段只能往后加 ⇒ 这里跟着改（与 `test_console_bridge.py` 一起钉住）。
        ('console_state', base + SYMS['g_ConsoleState'], 11),
        # 2026-09-21：游戏开局中继的**两处调用点**与它的回调槽。
        # 为什么要固定读它们：`GameStart` 走 `RelaySlot` 后端，**必须**由
        # `atmosphere/nro_patches/isaac-repentance-lifecycle-relay` 的 IPS 把调用点改成
        # `b <代码洞>` 才装得上；装不上时它按 `required=false` 只记 **Skipped**（不算失败），
        # 所以"挂点全装好、零失败"这句话**不能**证明这一路是好的（2026-09-17 的套装进度事故
        # 就是这个形态）。这三格把"补丁在不在"变成一条可以直接看见的读数。
        ('gamestart_saved_callsite', game_base + SYMS['gamestart_saved_callsite'], 1),
        ('gamestart_new_callsite', game_base + SYMS['gamestart_new_callsite'], 1),
        ('gamestart_relay_slot', game_base + SYMS['gamestart_relay_slot'], 1),
        ('render_entry', game_base + SYMS['manager_render_entry'], 2),
        ('present_slot', game_base + SYMS['present_got_slot'], 1),
        ('present_callsite', game_base + SYMS['present_callsite_offset'], 1),
        ('present_body', game_base + SYMS['present_target'], 1),
    ]
    req = [r for r in req if r[0] not in ('mod_data_head', 'mod_data_tail')]
    cache_offset = SYMS.get('g_ModDataCache')
    if cache_offset and MOD_DATA_CACHE_BYTES == 40:
        req.append(('mod_data_descriptor', base + cache_offset, 5))
    elif cache_offset and MOD_DATA_CACHE_BYTES == 16408:
        req.extend([('mod_data_tail', base + cache_offset + 0x4000, 3),
                    ('mod_data_head', base + cache_offset, 1024)])
    else:
        skipped.append('mod_data_cache_layout')
    if plugin_base:
        req.append(('helper', plugin_base + PLUGIN_HELPER, 14))
    # 上面每条都用 `SYMS[...]` 直接取；这里做一遍守卫，缺的进 `skipped` 而不是让整个函数崩掉。
    skipped.extend(SYMS.missing)
    del SYMS.missing[:]
    # 缺偏移的量地址会退化成 `base + 0`（模块基址），必须剔掉 —— 否则会拿一段无关内存当读数。
    for key in ('g_CallbackDiagnosticViewIncomplete', 'g_CallbackDiagnosticViewOverflow'):
        if key in SYMS:
            req.append((key, base + SYMS[key], 1))
    if not CALLBACK_REGISTRY_LAYOUT_KNOWN:
        req = [row for row in req if row[0] != 'callback_count']
        skipped.append('callback_count_layout')
    present = [(key, address, count) for key, address, count in req
               if not (key in skipped and address == base)]
    return present, skipped



def mod_data_payload_commands(base: int) -> list[str]:
    """当前Cache的指针与长度在同一次attach里解引用；窗口上限8192，绝不读取越界尾字。"""
    offset = SYMS.get('g_ModDataCache')
    if not offset or MOD_DATA_CACHE_BYTES != 40:
        return []
    address = base + offset
    return [f'set $isaac_data_ptr = *(unsigned long long*)0x{address:x}',
            f'set $isaac_data_capacity = *(unsigned long long*)0x{address + 8:x}',
            f'set $isaac_data_length = *(unsigned long long*)0x{address + 16:x}',
            'if $isaac_data_ptr != 0 && $isaac_data_length > 0 && $isaac_data_length <= $isaac_data_capacity && $isaac_data_length <= 0xffffffff',
            'set $isaac_data_window = $isaac_data_length > 8192 ? 8192 : $isaac_data_length',
            'echo TAG mod_data_head_bytes\\n',
            'eval "x/%lubx 0x%lx", $isaac_data_window, $isaac_data_ptr',
            'end']


#: 回调登记表（`CallbackRegistry`）在模块内的**布局** —— 三张平行数组 + 一个计数，全是手算的：
#:
#:   | 成员 | 元素大小 | 总计 |
#:   | --- | --- | --- |
#:   | `entries_`（`CallbackDescriptor`） | 20 B | 256 × 20 = **0x1400** |
#:   | `filters_`（过滤器，批次 101 加） | 8 B | 256 ×  8 = **0x0800** |
#:   | `priorities_`（优先级，批次 105 加） | 4 B | 256 ×  4 = **0x0400** |
#:   | `count_`（`size_t`） | — | 落在 **0x2000** |
#:
#: ★★ 这是读数工具里**最容易过期的一处**：任何一次往 `CallbackRegistry` 里加数组都会让 `count_`
#: 整体后移，而后果不是报错、是"**读出一个像模像样的垃圾数**"——
#: 2026-09-20 实测：`+0x1400` 读到了 `filters_[0]` 的哨兵 `kNoCallbackFilter`（= `0x8000000000000000`
#: = 打印出来的 9223372036854775808）。所以下面读回来会**先做合理性判断**
#: （超过容量就响亮报"布局可能变过、来核对这里"），而不是把它当真的登记数念出来。
CALLBACK_REGISTRY_COUNT_OFFSET = 0x2D00
# 2026-10-10：float优先级及持久order数组版本为size=0x2508/count@0x2500；
# integer/float精确保留版本为size=0x2d08/count@0x2d00。
# 历史size=0x2008仍用旧偏移。由当批ELF识别，未知布局不读取count。
CALLBACK_REGISTRY_LAYOUT_KNOWN = False
#: 与 `CallbackRegistry::kCapacity` 一致（门禁 `test_callback_dispatch_counters` 会核对表长那一条，
#: 这一条靠这里的一致性判断兜住）。
CALLBACK_REGISTRY_CAPACITY = 256

#: 回调登记表的一项 = 20 字节（`CallbackDescriptor`）：
#:   +0 `id`(u32)、+4 `owner.index`(u16)、+6 `owner.generation`(u16)、
#:   +8 `affinity`(u8，`ThreadAffinity` 的底层类型就是 `uint8_t`)+3 填充、
#:   +12 `luaReference`(int32)、+16 `modReference`(int32)。
#:
#: **2026-09-16 修正**：这里以前按"每项 40 字节、字段各 8 字节"解 —— 那是错的口径，
#: 读出来的东西（`id = 281483566645271`）谁也认不出来。表项大小与字段宽度都以
#: `runtime/src/domain/callback/callback_descriptor.hpp` 为准。
CALLBACK_ENTRY_BYTES = 20

#: 按键侧上升沿表（`LuaRuntime::InputFrameEdges g_ButtonEdge`）在模块内的**布局**
#: ★ 更正（批次 381，2026-10-06）：类型由 `ActionEdgeTracker` 改名为 `InputFrameEdges`；
#:   `Entry` 的字段顺序与大小**未变**（20 字节），所以下面的 layout 与行字节数继续有效。
#: —— 与上面那张回调表同一类"手算的偏移"，任何一次改 `input_edge.hpp` 的 `Entry` 都会让
#: 这里的解码整体错位（**症状不是报错、是读出一个像模像样的垃圾**）：
#:
#:   | 成员 | 元素大小 | 总计 |
#:   | --- | --- | --- |
#:   | `entries_[controller & 31][code & 31]`（`Entry`） | 20 B | 32 × 32 × 20 = **0x5000** |
#:
#: `Entry` 的字段（`runtime/source/input_edge.hpp`）：
#:   +0 `frame`(u32，`0xFFFFFFFF` = 还没采过)、+4 `edge`(u8，本帧是否边沿)、
#:   +5 `held`(u8，本帧是否按住 —— "最后一次采样时本帧按住状态"，供"按住与边沿同源"用)、
#:   +8 `lastEdgeFrame`(u32；★ 更正（批次 381）：由 `lastPressedFrame` 改名，语义从"上一次
#:      **读到按住**的帧号"变为"**上一次边沿**的帧号")、
#:   +12 `releaseRun`(u8)、+13 `peakReleaseRun`(u8)、
#:   +14 `minEdgeGap`(u16)、+16 `lastEdgeGap`(u16)。
#: ★ 更正（批次 381，2026-10-06）：上面 +12/+13/+14/+16 的语义随"帧上采样 + 纯读"更新 ——
#:   `releaseRun` = 连续多少次采样读到"未按住"、`peakReleaseRun` = 其峰值（旧文里的"闪断"
#:   在本机制下不适用）；`minEdgeGap`/`lastEdgeGap` = **相邻两次边沿之间的帧数间隔**
#:   （用途 = 判"两次独立按下之间隔了多久"，不再是"距上一次读到按住"）。
#: 两处自证：`nm -S runtime/.gdbsym-artifacts/runtime.elf | grep g_ButtonEdge` = **0x5000 字节**；
#: 行号 = `controller & 31` ⇒ 真机那台手柄（设备 33）落在**行 1**、引擎的"任意设备"
#: （`0xFFFFFFFF`）落在**行 31**。★ 布局数值（每行 640 字节 / 整表 0x5000 字节 /
#: 行 1 = 设备 33 / 行 31 = 任意设备）批次 381 **全部不变**。
BUTTON_EDGE_ENTRY_BYTES = 20
BUTTON_EDGE_ROW_BYTES = 32 * BUTTON_EDGE_ENTRY_BYTES
BUTTON_EDGE_NO_FRAME = 0xFFFFFFFF

#: `ModCallbacks` 里我们**已经接线**（代码里真有派发点）的 id → 名字。
#: 名字必须与 `callback_descriptor.hpp` 里的常量逐字对应（去前缀后）；
#: `runtime/tests/test_callback_dispatch_counters.py` 会核对这件事，抄错 id 会让读数把
#: 名字标在别的种类上，把现场判断带偏（2026-09-15 的 `MC_INPUT_ACTION` 误报就是这一类）。
CALLBACK_NAMES = {
    0: 'MC_NPC_UPDATE',
    1: 'MC_POST_UPDATE',
    2: 'MC_POST_RENDER',
    4: 'MC_POST_PEFFECT_UPDATE',
    6: 'MC_FAMILIAR_UPDATE',
    7: 'MC_FAMILIAR_INIT',
    9: 'MC_POST_PLAYER_INIT',
    15: 'MC_POST_GAME_STARTED',
    18: 'MC_POST_NEW_LEVEL',
    19: 'MC_POST_NEW_ROOM',
    25: 'MC_POST_FAMILIAR_RENDER',
    27: 'MC_POST_NPC_INIT',
    31: 'MC_POST_PLAYER_UPDATE',
    32: 'MC_POST_PLAYER_RENDER',
    34: 'MC_POST_PICKUP_INIT',
    35: 'MC_POST_PICKUP_UPDATE',
    36: 'MC_POST_PICKUP_RENDER',
    39: 'MC_POST_TEAR_INIT',
    40: 'MC_POST_TEAR_UPDATE',
    41: 'MC_POST_TEAR_RENDER',
    43: 'MC_POST_PROJECTILE_INIT',
    44: 'MC_POST_PROJECTILE_UPDATE',
    45: 'MC_POST_PROJECTILE_RENDER',
    47: 'MC_POST_LASER_INIT',
    48: 'MC_POST_LASER_UPDATE',
    49: 'MC_POST_LASER_RENDER',
    50: 'MC_POST_KNIFE_INIT',
    51: 'MC_POST_KNIFE_UPDATE',
    52: 'MC_POST_KNIFE_RENDER',
    54: 'MC_POST_EFFECT_INIT',
    55: 'MC_POST_EFFECT_UPDATE',
    56: 'MC_POST_EFFECT_RENDER',
    57: 'MC_POST_BOMB_INIT',
    58: 'MC_POST_BOMB_UPDATE',
    59: 'MC_POST_BOMB_RENDER',
    62: 'MC_PRE_GET_COLLECTIBLE',
    # --- 2026-09-20 批次 102（EID / GoodTrip 在等的那几个事件，走入口中继）---------
    3: 'MC_USE_ITEM',
    5: 'MC_USE_CARD',
    10: 'MC_USE_PILL',
    17: 'MC_PRE_GAME_EXIT',
    23: 'MC_PRE_USE_ITEM',
    38: 'MC_PRE_PICKUP_COLLISION',
    63: 'MC_POST_GET_COLLECTIBLE',
    71: 'MC_PRE_ROOM_ENTITY_SPAWN',
    # 批次 390（2026-10-07）：`MC_INPUT_ACTION` 接线后从 `CALLBACK_NOT_WIRED` 挪过来。
    13: 'MC_INPUT_ACTION',
    # --- 2026-10-07 批次 396（补全回调第 1 批）----------------------------------------
    # 补登是为了读数里能认出这几条 —— 不补的话它们的派发次数会被归到"其它种类"，
    # 而"某条新回调到底派发了几次"正是这几批**唯一能拿到的机器判据**。
    8: 'MC_EVALUATE_CACHE',
    11: 'MC_ENTITY_TAKE_DMG',
    # --- 2026-10-07 批次 397（补全回调第 2 批）----------------------------------------
    16: 'MC_POST_GAME_END',
    29: 'MC_POST_NPC_DEATH',
    61: 'MC_POST_FIRE_TEAR',
    68: 'MC_POST_ENTITY_KILL',
}

#: 我们**故意还没接线**、但读数里要标出名字的 id（标名字是为了"这个数字是哪一种"一眼可读）。
#: 与 `CALLBACK_NAMES` 分开是有意的，门禁（`test_callback_dispatch_counters.py` 的
#: `test_reader_callback_names_have_a_matching_constant`）要求这里每一个 id **不许**出现在
#: `HasDispatchSite` 名单里。两种形态都合法：**有常量但没派发点**（`MC_INPUT_ACTION` 13）
#: 或**连常量都还没有**；一旦它的常量进了 `HasDispatchSite`，就该挪到上面那张表去。
#: （2026-09-20 修正注释：原文说"门禁要求这里没有对应常量"，而门禁实际只判"不在派发点名单里"。）
CALLBACK_NOT_WIRED = {
    # ★ 2026-10-07（批次 390）：`MC_INPUT_ACTION`(13) **已接线**（三条 `KAGE::Input::ManagerBase::*`
    #   查询中继 + `LuaRuntime::DispatchInputAction`）⇒ 按本表的口径挪到上面的 `CALLBACK_NAMES`。
    #   现在这张表**是空的**（EID 在意的 9 种已全部接线），留着它是为了下一个"故意不接"的条目。
}

#: 派发计数表的长度（= PC `ModCallbacks` 的最大值 73 + 1）。与 `callback_dispatcher.hpp` 的
#: `kCallbackDispatchCounterCount` 必须一致；`runtime/tests/test_callback_surface.py` 那一族
#: 门禁盯着台账，这里的数字只用于"读多少个字"。
CALLBACK_DISPATCH_COUNTER_COUNT = 74

#: 回调耗时桶（批次 086）：每项 32 字节 —— `key`(u64)、`count`(u64)、`ticks`(u64)、`maxTicks`(u64)。
#: 与 `runtime/src/interfaces/lua/runtime_perf.hpp` 的 `RuntimePerfCallbackBucket` 逐字段对应，
#: 个数也必须一致（门禁 `runtime/tests/test_perf_callback_buckets.py` 核对两边）。
#: `key` 的打包口径：低 32 位 = 事件 id；bit32..47 = `owner.index`；bit48..63 = `owner.generation`。
PERF_BUCKET_COUNT = 64
#: 每项：`key`(u64)、`count`(u64)、`ticks`(u64)、`maxTicks`(u64)、`bins[4]`(u32×4) = 48 字节
#: （批次 092 给直方图加了 16 字节；与头文件的 `RuntimePerfCallbackBucket` 一致，门禁核对）。
PERF_BUCKET_BYTES = 48

#: 按 **API 接口** 分开的耗时桶（批次 087）：记录格式与上面的回调桶**逐字段相同**，
#: 只是个数不同（`kRuntimePerfApiBucketCount`）。键的高位 `PERF_API_ENGINE_TAG` 置上表示
#: "这一笔只算**引擎调用那一段**"，用来把"我们 handler 的开销 = 总 − 引擎调用"算出来。
PERF_API_BUCKET_COUNT = 512

#: **内部运算 / 元表处理器**的保留 id（批次 093）。它们不是 catalog 里的接口，
#: 但是热路径（实体每次字段读/方法查找都过 `Entity.__index`）。id 段与
#: `runtime_perf.hpp` 的 `kPerfInternalId*` 一一对应，门禁核对两边的**名字与序号**。
INTERNAL_API_NAMES = {
    0xFF000001: 'Entity.__index（字段读 / 方法查找）',
    0xFF000002: 'EntityPlayer.__index',
    0xFF000003: 'EntityPickup.__index',
    0xFF000004: 'Vector.__index',
    0xFF000005: 'Vector.__newindex',
    0xFF000006: 'Vector.__add',
    0xFF000007: 'Vector.__sub',
    0xFF000008: 'Vector.__mul',
    0xFF000009: 'Vector.__div',
    0xFF00000A: 'Vector.__unm',
    0xFF00000B: 'Vector.__eq',
    0xFF00000C: 'Vector.__tostring',
    0xFF00000D: 'Vector()（构造）',
    0xFF00000E: 'Color.__index',
    0xFF000011: 'EntityRef()（构造）',
}
PERF_API_ENGINE_TAG = 1 << 32

#: Lua 采样剖析器（批次 089）：每项 80 字节 —— `hits`(u32)、`line`(i32)、`name`(char[24])、
#: `source`(char[48])。与 `runtime/src/interfaces/lua/runtime_profiler.hpp` 的
#: `RuntimePerfProfileBucket` 逐字段对应，个数也要一致（门禁核对）。
PROFILE_BUCKET_COUNT = 192
PROFILE_BUCKET_BYTES = 80

#: 采样步长（每多少条 Lua 指令一次）。与 runtime_profiler.hpp 的
#: kRuntimePerfProfileInstructionStep 一致 —— 打印里用它说明这个数字是什么意思。
PERF_PROFILE_INSTRUCTION_STEP = 4000


def profile_records(values: dict[str, list[int]]) -> list[tuple[int, int, str, str]]:
    """把采样桶解成 `(hits, line, name, source)` 并按 hits **降序**（最热的在前）。

    `hits == 0` 是空桶，跳过。
    """
    import struct

    raw = words_to_bytes(values.get('perf_profile_buckets') or [])
    records = []
    available = min(len(raw), PROFILE_BUCKET_COUNT * PROFILE_BUCKET_BYTES)
    if available % PROFILE_BUCKET_BYTES:
        print('  ⚠ Lua 采样桶末条不完整 ⇒ 只解释完整记录')
    for offset in range(0, available - PROFILE_BUCKET_BYTES + 1, PROFILE_BUCKET_BYTES):
        hits, line = struct.unpack_from('<Ii', raw, offset)
        if not hits:
            continue
        name = raw[offset + 8:offset + 32].split(b'\0', 1)[0].decode('utf-8', 'replace')
        source = raw[offset + 32:offset + 80].split(b'\0', 1)[0].decode('utf-8', 'replace')
        records.append((hits, line, name, source))
    records.sort(key=lambda record: -record[0])
    return records


def short_source(source: str) -> str:
    """源文件名只做**显示**上的收尾：运行时侧已经按"保留结尾"存了 48 字节，
    这里不再重切路径（重切会让两行看起来一样、实际不同 —— 第一次真机就撞过这个坑）。"""
    return source[1:] if source.startswith('@') else source


def bucket_records(values: dict[str, list[int]], key_name: str,
                   count: int) -> list[tuple[int, int, int, int, tuple[int, ...]]]:
    """把桶数组解成 `(key, count, ticks, maxTicks, bins)`，跳过空槽（`count == 0`）。

    `bins` 是耗时分布四档：`< 250 µs / < 1 ms / < 5 ms / >= 5 ms`（批次 092）——
    平均值会被少数极慢样本带偏，必须能看出"每帧都慢"还是"少数几帧特别慢"。
    """
    import struct

    raw = words_to_bytes(values.get(key_name) or [])
    records = []
    # ★ 2026-09-22 修：**设备有时只回一部分**（真机实测：请求 24576 字节、只回 13520 ——
    # 于是最后一个 offset 处只剩 32 字节，`unpack_from` 直接抛 `struct.error`，
    # **整份读数在打印探针那一段之前就断了**）。所以这里只遍历"能装下完整一条记录"的范围，
    # 并把"少读了多少"如实打出来 —— 读数工具宁可少报，也不能因为一段短读就把整份报告吞掉。
    want_bytes = count * PERF_BUCKET_BYTES
    available = min(len(raw), want_bytes)
    if available < want_bytes:
        print(f'  ⚠ {key_name}：只读到 {available} / {want_bytes} 字节'
              f'（设备这次回得比请求的短）⇒ 只解到能装下的那几条记录')
    for offset in range(0, available - PERF_BUCKET_BYTES + 1, PERF_BUCKET_BYTES):
        key, samples, ticks, max_ticks, *bins = struct.unpack_from('<QQQQIIII', raw, offset)
        if samples:
            records.append((key, samples, ticks, max_ticks, tuple(bins)))
    return records


def perf_bucket_records(values: dict[str, list[int]]) -> list[tuple[int, int, int, int]]:
    return bucket_records(values, 'perf_buckets', PERF_BUCKET_COUNT)


def perf_api_records(values: dict[str, list[int]]) -> list[tuple[int, int, int, int]]:
    return bucket_records(values, 'perf_api_buckets', PERF_API_BUCKET_COUNT)


def rank_perf_api_buckets(
        records: list[tuple[int, int, int, int]]) -> list[tuple[int, int, int, int]]:
    """API 桶 → 按**合计耗时降序**的 `(ticks, count, id, 引擎调用 ticks)`。

    ★ 这里曾经写错成升序取前 10 —— 也就是把"**最便宜**的 10 个接口"当成"最贵的"打出来。
    读数看着很正常（名字、次数、平均都对），只是**结论完全反了**：真凶 `Font:DrawStringScaledUTF8`
    被挤到第 8 名、而最贵的那几个根本没出现。**排序方向这种东西必须由门禁钉住，不能靠眼睛**。
    """
    totals: dict[int, list[int]] = {}
    engine_part: dict[int, int] = {}
    for key, count, ticks, _max_ticks, _bins in records:
        identifier = key & 0xFFFFFFFF
        if key & PERF_API_ENGINE_TAG:
            engine_part[identifier] = ticks
        else:
            totals[identifier] = [count, ticks]
    ranked = [(value[1], value[0], identifier, engine_part.get(identifier, 0))
              for identifier, value in totals.items() if value[0]]
    ranked.sort(key=lambda row: (-row[0], row[2]))
    return ranked


def perf_bucket_owner(key: int) -> str:
    """`key` → 读数的归属写法（与回调登记表同一种 `#N 代M`）。"""
    return f"#{key >> 32 & 0xFFFF} 代{key >> 48}"


def owner_name_table(values: dict[str, list[int]]) -> list[tuple[int, str]]:
    """批次 418：把 `g_ModOwnerNames` 那张表解成 `[(owner 编号, 模组名), …]`（只列非空的）。

    读不到（老读数件 / 老构建）⇒ 返回**空表**，调用方什么都不印 —— **缺就说缺**。
    """
    raw = words_to_bytes(values.get('mod_owner_names') or [])
    if len(raw) < 32 * 64:
        return []
    rows: list[tuple[int, str]] = []
    for index in range(32):
        slot = index * 64
        name = raw[slot:slot + 64].split(b'\0')[0].decode('utf-8', 'replace')
        if name:
            rows.append((index, name))
    return rows


def owner_display_name(values: dict[str, list[int]], owner_index: int) -> str:
    """批次 418：`[#N]` 里的 N → **模组名**（读 `g_ModOwnerNames` 那张表）。

    为什么要有它：掉帧归因一直卡在"桶只给属主编号、点不出名"上（2026-10-08 那次就是这样
    停在"最贵的那两个桶是 #17 / #14"）。这张表在 `RegisterMod` **分配 owner 号的那一刻**写下来
    —— 只有那一刻知道这个编号是谁。**不能用"模组清单的下标"去凑**：那份清单是引擎给的目录
    列表、**包含被禁用的模组**，而 owner 号只给真的调了 `RegisterMod` 的模组，两套编号之间
    没有固定偏移（实测两对锚点是 +6 与 +4，不是同一个数）。

    ★ 读不到就返回**空串**（老读数件、或没编进这一格的构建）⇒ 调用方什么都不加。
      **缺就说缺**，绝不用清单下标凑一个名字出来（那正是这套东西要根治的错）。
    """
    if owner_index < 0 or owner_index >= 32:
        return ''
    for index, name in owner_name_table(values):
        if index == owner_index:
            return name
    return ''


def callback_name(identifier: int) -> str:
    return CALLBACK_NAMES.get(identifier, '其它种类')


#: `ApiDomain` 的取值（`runtime/src/interfaces/lua/api_descriptor.hpp` 的枚举顺序就是编码）。
#: 与那张表**必须**逐项一致：id 是 `(域 << 24) | (ownerGroup << 16) | 序号`。
CATALOG_DOMAINS = {
    'Global': 0, 'Mod': 1, 'Game': 2, 'Level': 3, 'Room': 4, 'ItemPool': 5, 'Music': 6,
    'Rng': 7, 'Persistence': 8, 'Input': 9, 'Diagnostic': 10, 'Font': 11, 'Vector': 12,
    'Sprite': 13, 'Isaac': 14, 'Seed': 15, 'ModMenu': 16,
    # 批次 207（2026-09-29）：`Hud`（域 17，`Game:GetHUD()` 的返回值）—— 读数工具要能
    # 认出 `0x11…` 的 id，否则 HUD 那两条在"风险面"里会被静默丢掉。
    'Hud': 17,
}
CATALOG_ENTRY = re.compile(
    r"\{MakeId\(ApiDomain::(?P<domain>\w+),\s*(?P<group>\d+),\s*(?P<seq>0x[0-9A-Fa-f]+)\),"
    r"[^}]*?\"(?P<owner>[^\"]*)\",\s*\"(?P<name>[^\"]*)\"", re.S)
_CATALOG_NAMES: dict[int, str] | None = None


def api_catalog_names() -> dict[int, str]:
    """catalog id → `owner:name`（读数里只拿到数字 id，报文里得是人能认的名字）。

    数据行的"最后一次被调用 / 最后一次被降级"记的都是 catalog id（`api_call_stats.hpp`），
    而 id 的编码口径写在 `api_catalog.cpp` 的 `MakeId` 上。**在本地解析源码**而不是再抄一张表：
    抄第二份迟早与源码不一致，而这份解析错了会当场表现在读数里（id 对不上就会显示成"未知"）。
    """
    global _CATALOG_NAMES
    if _CATALOG_NAMES is not None:
        return _CATALOG_NAMES
    names: dict[int, str] = {}
    path = ROOT / 'runtime/src/interfaces/lua/api_catalog.cpp'
    if path.exists():
        text = path.read_text(encoding='utf-8')
        for match in CATALOG_ENTRY.finditer(text):
            domain = CATALOG_DOMAINS.get(match.group('domain'))
            if domain is None:
                continue
            identifier = (domain << 24) | (int(match.group('group')) << 16) \
                | int(match.group('seq'), 16)
            names[identifier] = f"{match.group('owner')}:{match.group('name')}"
    _CATALOG_NAMES = names
    return names


def api_name(identifier: int) -> str:
    """id → `owner:name`；查不到就**如实说查不到**（不要编一个像样的名字出来）。"""
    if identifier == 0:
        return '（空）'
    return api_catalog_names().get(identifier, f'未知 id 0x{identifier:08X}')


#: 卡上开关的**名字与位序**，必须与 `runtime/source/hook_manager.cpp` 的 `kCardSwitchNames`
#: 逐字一致（顺序就是 `g_CardSwitchMask` 的位序）。`runtime/tests/test_card_switches.py` 钉住这一点。
#:
#: 只剩"由**游戏主线程**上的代码读取"的两个开关。挂点跳过类开关已经删掉：读它们那一步跑在
#: worker 线程上，会在 nnSdk 里空指针崩溃（2026-09-16，442190 每次开机必崩）——
#: 挂点层面的二分改用编译开关 `ONLY_REQUIRED_HOOK=1`。
CARD_SWITCH_NAMES = (
    'no-menu',
    'no-lua',
)


def decode_callback_entries(raw: bytes) -> list[dict]:
    """把回调登记表的原始字节切成一条条登记（不足一条的尾巴丢掉）。"""
    entries = []
    for offset in range(0, len(raw) - CALLBACK_ENTRY_BYTES + 1, CALLBACK_ENTRY_BYTES):
        chunk = raw[offset:offset + CALLBACK_ENTRY_BYTES]
        entries.append({
            'id': int.from_bytes(chunk[0:4], 'little'),
            'owner_index': int.from_bytes(chunk[4:6], 'little'),
            'owner_generation': int.from_bytes(chunk[6:8], 'little'),
            'affinity': chunk[8],
            'lua_reference': int.from_bytes(chunk[12:16], 'little', signed=True),
            'mod_reference': int.from_bytes(chunk[16:20], 'little', signed=True),
        })
    return entries


def save_raw(text: str, base: int, game_base: int, plugin_base: int) -> Path:
    """原始读数先落盘（含基址）：解析代码再出 bug 也不至于白烧一次调试桩挂载，
    而且可以**离线重放**（`--from-raw`）——换解释、改解码都不用再连设备。"""
    raw_path = ROOT / 'dist' / f'gdb-read-{time.strftime("%Y%m%d-%H%M%S")}.txt'
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    header = f'# base=0x{base:x} game_base=0x{game_base:x} plugin_base=0x{plugin_base:x}\n'
    raw_path.write_text(header + text, encoding='utf-8')
    print(f'原始读数已存：{raw_path.relative_to(ROOT)}（可用 --from-raw 离线重放）')
    return raw_path


def load_raw(path: Path) -> tuple[str, int, int, int]:
    text = path.read_text(encoding='utf-8')
    first_line, _, rest = text.partition('\n')
    m = re.match(r'# base=0x([0-9a-f]+) game_base=0x([0-9a-f]+) plugin_base=0x([0-9a-f]+)', first_line)
    if not m:
        return text, 0, 0, 0
    return rest, int(m.group(1), 16), int(m.group(2), 16), int(m.group(3), 16)


def parse_extra_reads(text: str):
    """`--read 0x1234:32,0x5678:16` → [(地址, 字节数)]。

    用途：探针把"像指针"的值记下来之后，**直接把这些地址的内容读回来** ——
    不必为了多知道几个字节就再烧一次 attach（调试桩一个启动周期只能挂几次）。
    """
    items = []
    for chunk in (text or '').split(','):
        chunk = chunk.strip()
        if not chunk:
            continue
        address_text, _, size_text = chunk.partition(':')
        items.append((int(address_text, 0), int(size_text or '16', 0)))
    return items


#: 玩家链路的两个**游戏侧**偏移（来自 `runtime_constants.hpp`，游戏版本不变就稳定）。
#: ★★ 形状（2026-09-28 更正）：`Game*` 要**解两次** ——
#:     `slot  = *(game_base + 0xAAC698)`   ；槽里放的是 `g_Game` **指针变量的地址**
#:     `Game* = *slot`
#: 这个形状有**两条独立证据**：① 引擎自己的指令（`TriggerPreVictoryLap @0x2FC54C`、
#: `HUD::Render @0x3AD734` 都是 `ldr x,[x,#0x698]` 之后再 `ldr x,[x]`）；
#: ② 我们运行时的 `ResolveGameAddress()`（`isaac_api.cpp:989-1000`）也是两次读。
#: 本工具原来**只解一次**（注释还写着"只解一次"）⇒ 拿到的是"指针变量的地址"而不是对象，
#: 于是"玩家实体地址"在最近几次会话里**一直读不到**（而同一次会话 update/render 在派发、
#: 局内闩锁已置位）。现在改成"两级优先、一级兜底"，并把**走的是哪条**报出来 ——
#: 让下一次真机读数**自己证明**哪一种对（不再靠推断）。
PLAYER_CHAIN_GAME_SLOT = 0xAAC698     # game_base + 它 ⇒ 存 `g_Game` 指针变量地址的那个槽
PLAYER_CHAIN_PLAYERS_BEGIN = 0x25C50  # Game + 它 ⇒ `vector<Entity_Player*>` 的 begin
#: `KAGE::Input::ManagerBase::IsButtonPressed` 的模块内偏移（`kKageIsButtonPressedOffset`，
#: 批次 210 用它当"发布槽对不对"的期望值）。
KAGE_IS_BUTTON_PRESSED_OFFSET = 0x4F9504


def resolve_player_entity_address(session, game_base: int) -> tuple[int, str]:
    """把 `players[0]`（玩家实体）的地址读出来 —— **只读**，任何一步失败就算了。

    为什么加它（2026-09-25 记下的缺环）：做 `player.QueuedItem` / 扫玩家对象找字段偏移时，
    要先拿到**玩家实体地址**，而读数里原来不打印它，只能靠外部猜。

    链：`game_base + 0xAAC698` → `Game*` → `Game + 0x25C50`（`players` 的 begin）
        → 那个 `Entity_Player*`。
    返回 `(地址, 失败原因)`；失败时地址为 0。
    """
    if not game_base:
        return 0, '（没有游戏模块基址，跳过）'

    def read_u64(address: int, tag: str) -> int:
        got = parse_words(session.command(f'echo TAG {tag}\\n\nx/1gx 0x{address:x}')).get(tag, [])
        return got[0] if got else 0

    slot = read_u64(game_base + PLAYER_CHAIN_GAME_SLOT, 'pl_game')
    if not slot:
        # ★★★ 2026-10-04 用户纠正："我从来都是在局内的……你对调试桩的使用容易出问题，非常多次都误以为
        #     调试桩不可用，读错数据，误以为我在局外非局内。" ⇒ **这一格读不到 ≠ 人没进局**。
        #     以前这里写"多半还没进局"，我照着它反推，连着几轮把"人明明在局内"当成"在菜单"。
        #     现在只报事实，并明确禁止从它反推局内/局外。
        return 0, ('（`g_Game` 槽这一格没读出来。★ 这**不代表"人没进局"** —— 2026-10-04 用户明确纠正过：'
                   '他一直在局内、工具却反复报"多半还没进局"。判局内状态请用别的判据'
                   '（update/render 回调计数，或直接问用户），**不要**用这一格反推）')

    # 两级优先（引擎与运行时都是这个形状）；一级兜底并**报告走了哪条**，让真机读数自证。
    for levels, game_ptr in ((2, read_u64(slot, 'pl_game2')), (1, slot)):
        if not game_ptr:
            continue
        players_begin = read_u64(game_ptr + PLAYER_CHAIN_PLAYERS_BEGIN, 'pl_begin')
        if not players_begin:
            continue
        player0 = read_u64(players_begin, 'pl_p0')
        if player0:
            route = '两级（= 引擎与运行时同一形状）' if levels == 2 else '**一级**（兜底；若读数里是这条，说明我改错了，请报告）'
            return player0, route
    return 0, ('（`players[0]` 读不到：两级与一级兜底都没读出非空的 begin/元素。'
               '★ 这**不代表"人没进局"**（同上的纠正）—— 只说明这条链的某一格没读出来：'
               '要么链形状变了，要么这一次 attach 没读上）')


def run_one_shot(ip: str, elf: Path, pid: int = 0, base: int = 0, game_base: int = 0,
                 plugin_base: int = 0, extra_reads=()) -> int:
    session = GdbSession()
    try:
        session.command(f'target extended-remote {ip}:22225')
        if not pid:
            pid = parse_processes(session.command('info os processes')) or 0
        if not pid:
            print('没找到正在运行的 Application，请先启动游戏。')
            return 3
        print(f'进程 = {pid}（本会话只 attach 这一次）')
        attach_out = session.command(f'attach {pid}')
        if not base or not game_base:
            found_module, found_plugin, found_game = parse_bases(session.command('monitor get info'))
            base = base or (found_module or 0)
            plugin_base = plugin_base or (found_plugin or 0)
            game_base = game_base or (found_game or 0)
        if not base or not game_base:
            # 这次实测过：`monitor get info` 在"刚开机第一次挂载"也可能返回空。
            # 兜底：用内存映射 + 内容指纹自己找（只多读几十个 16 字节，仍然是同一次挂载）。
            scanned_module, scanned_game = locate_by_scan(session, elf)
            base = base or (scanned_module or 0)
            game_base = game_base or (scanned_game or 0)
        print(f'运行时模块基址 = 0x{base:x}'
              + (f'；插件基址 = 0x{plugin_base:x}' if plugin_base else '')
              + (f'；游戏模块基址 = 0x{game_base:x}' if game_base else '；游戏模块基址（缺）'))
        if not base or not game_base:
            print('基址没取全（`monitor get info` 与 mappings 扫描都没认出来）。')
            # ★ 2026-09-18 加的判据：**先确认"游戏到底在不在跑"**，别一上来就怀疑调试桩。
            # 实测（同一天）：游戏没开时，调试桩附着到的是 hbl/ftpd 那个 Application，
            # 它的进程里当然没有我们的模块 ⇒ 候选段在 identity 处读到的是一条 `ret`
            # （`0xd65f03c0`）。那种情况下的正确处置是**把游戏开起来再读**，而不是重启设备。
            print('最常见的原因（先排除这个）：**游戏没在运行** —— 调试桩附着到的是 hbl/ftpd 那个'
                  ' Application，它的地址空间里没有我们的模块。')
            print('  判据：上面"候选 N"那几行若显示"identity 处读到 0xd65f03c0（ret）"，'
                  '基本就是这个原因。')
            print('  处置：把游戏开到标题画面（或读盘进局）再重跑本工具。')
            print('次常见：调试桩在同一个启动周期里退化（第二次 attach 常连映射表都读不到）'
                  '⇒ 那就**重启设备**，第一次连接最完整。')
            print('也可以直接用 --base/--game-base 指定（知道基址时）。')
            return 3

        requests, skipped = build_requests(base, game_base, plugin_base)
        for index, item in enumerate(extra_reads):
            address, size = item
            requests.append((f'extra_{index}_0x{address:x}', address, size))
        if skipped:
            print('  ⚠ 这些量没有偏移（本次不读，不影响其它读数）：' + '、'.join(skipped))
        lines = []
        for label, addr, count in requests:
            lines.append(f'echo TAG {label}\\n')
            lines.append(f'x/{count}gx 0x{addr:x}')
        lines.extend(mod_data_payload_commands(base))
        out = session.command('\n'.join(lines))
        # ★ 玩家实体地址（三级链，见 `resolve_player_entity_address`）—— 在**同一个会话**里补读，
        #   因为它的中间地址依赖上一步的结果（不能塞进上面那批一次性请求里）。
        player0, player_why = resolve_player_entity_address(session, game_base)
        session.command('detach')
    finally:
        session.close()

    save_raw(out, base, game_base, plugin_base)
    values = parse_words(out)
    if player0:
        print(f'  ★ 玩家实体地址 = 0x{player0:x}（链走的是 {player_why}）'
              f'　← 扫玩家对象用 `--read 0x{player0 + 0x1800:x}:0x400` 这种口径（0x1800 起是道具/饰品区）')
    else:
        print(f'  玩家实体地址：读不到 {player_why}')

    # ---- 版本核对：三个代码锚点必须与本地 ELF 逐字节相同 ----
    checks = {'identity': 'anchors', 'exl_main': 'anchor_exl_main', 'manifest_install': 'anchor_manifest'}
    mismatched = []
    for name in ANCHOR_NAMES:
        offset = SYMS[name]
        expect = local_bytes(elf, offset, 16)
        got = b''.join(v.to_bytes(8, 'little') for v in values.get(checks[name], [])[:2])
        same = expect is not None and got == expect
        if not same:
            mismatched.append(name)
        extra = ''
        if name == 'exl_main' and not same:
            # 入口偏移会随构建变；把设备上真实的偏移反推出来（`g_runtimeSelfAddress` 存的就是它）。
            self_addr = first(values, 'g_runtimeSelfAddress')
            if self_addr and base and 0 < self_addr - base < DEFAULT_CODE_LIMIT:
                extra = f'（设备上入口在 +0x{self_addr - base:x}）'
        print(f'  锚点 {name:18} @+0x{offset:<7x} '
              + ('✓ 与本地构建逐字节相同' if same else
                 f'✗ 不同：设备 {got.hex()} / 本地 {expect.hex() if expect else "(读不到)"}{extra}'))

    if mismatched:
        print()
        print(f'⚠️ 有锚点与本地那份构建不同：{", ".join(mismatched)} ⇒ 设备上跑的是**另一份构建**'
              '（很可能是发布包里那份正常版）。')
        # 换构建通常只动 `.text` 的排布；只要全局变量的**布局**没变，下面这些读数照样能用。
        # 用三个"必须落在合理范围"的量来判布局是否一致：
        seq = first(values, 'g_sequence') & 0xFFFFFFFF
        state = first(values, 'g_stateDetail') & 0xFFFFFFFF
        mstate = first(values, 'g_DefaultManifestState') & 0xFFFFFFFF
        appended = first(values, 'auto_appended_mods') & 0xFFFFFFFF
        append_status = first(values, 'auto_append_status') & 0xFFFFFFFF
        print(f'  清单 + 扫目录合并：多追加 {appended} 个目录（状态码 {append_status}，0 = 成功）'
              '  ← 「把模组文件夹拷进 mods/ 就能用」')
        self_addr = first(values, 'g_runtimeSelfAddress')
        sane = (seq < 10000 and state < 16 and mstate < 8
                and (self_addr == 0 or (base and 0 < self_addr - base < DEFAULT_CODE_LIMIT)))
        print(f'  布局自检：sequence={seq}、状态机={state}、清单状态={mstate}、'
              f'入口自地址差={hex(self_addr - base) if self_addr and base else "n/a"} ⇒ '
              + ('看着自洽，继续读数（偏移表可用）' if sane else '不自洽 ⇒ 偏移表不可用，停止解释'))
        if not sane:
            print('（要读这份构建，必须重建一份同源的 ELF 并同步整张偏移表。）')
            return 4
        print('  注意：下面的解释按当前偏移表给出；如与设备行为矛盾，先怀疑构建不同。')
    else:
        print('偏移自校验通过（三个代码锚点逐字节一致）')

    report(values, base, game_base, plugin_base)
    return 0


# ---------------------------------------------------------------------------
# 读数解释
# ---------------------------------------------------------------------------

def first(values: dict[str, list[int]], key: str, index: int = 0, default: int = 0) -> int:
    seq = values.get(key) or []
    return seq[index] if index < len(seq) else default


def optional_counter(values: dict[str, list[int]], key: str, *, bits: int = 64) -> int | None:
    """标量只取首字；缺失与实测零分开，避免把相邻字拼成更大的计数。"""
    words = values.get(key) or []
    return (words[0] & ((1 << bits) - 1)) if words else None


def print_callback_diagnostic_view(values: dict[str, list[int]]) -> bool:
    incomplete = optional_counter(values, 'g_CallbackDiagnosticViewIncomplete', bits=32)
    if incomplete is None:
        return False
    overflow = optional_counter(values, 'g_CallbackDiagnosticViewOverflow', bits=32)
    overflow_text = '未读' if overflow is None else str(overflow)
    print('  回调登记表 = 诊断快照；Lua共享表决定实际执行，快照可能过期或截断')
    print(f'    快照不完整标记 = {incomplete}；超出诊断容量的条目 = {overflow_text}（缺读数不按0解释）')
    return True


def print_font_storage(values: dict[str, list[int]]) -> None:
    def count(key):
        value = optional_counter(values, key, bits=32)
        return '缺失（本次没有有效读数）' if value is None else str(value)
    print('  === Font 存储（实际计数；仅凭分配器路径不能证明 GC 记账）===')
    print(f'    累计分配 = {count("g_FontStorageAllocations")}｜★ 当前活着 = {count("g_FontStorageLive")}'
          f'｜峰值 = {count("g_FontStorageLivePeak")}｜★ 失败 = {count("g_FontStorageFailures")}')


def first_u32(values: dict[str, list[int]], key: str, index: int = 0, default: int = 0) -> int:
    """读一个**我们自己的 `uint32` 全局**（取低 32 位）。

    读数工具是按 8 字节取字的，而我们的埋点大多是相邻的 `uint32` —— 一个 8 字节字里装着
    **两个**全局。直接拿整字会把隔壁的值一起算进来。2026-09-26 实测：`mod_engine_stage`
    （真值 2）被印成 `4294967298`（= 2 | 1<<32，高 32 位是隔壁 `mod_engine_attempts` 的 1），
    而同一段里 `LoadCostumes` 的调用次数也被印成 `17179869184` ⇒ 差点据此读错
    （"调了 4 次"与"一次都没调"是完全相反的结论）。凡是我们自己的 `uint32` 全局一律走这里。
    """
    return first(values, key, index, default) & 0xFFFFFFFF


def u32_at(values: dict[str, list[int]], key: str, index: int, default: int = 0) -> int:
    """按**真正的 `uint32` 下标**取一个我们自己埋的 `uint32` **数组**里的元素。

    ★ 为什么不能直接用 `first_u32`（批次 232 定案）：读数工具是**按 8 字节取字**的，
    `first_u32(values, key, i)` 的语义是"第 i 个 8 字节字的低 32 位" ⇒ 对 `u32` **数组**，
    下标 `i` 实际取到的是 **u32 下标 `2i`**，而且 `i` 超过字数一半之后恒返回 0。
    用它读数组会得出"偏移只有真值一半、后半段全是 0"的假结论（批次 225 那次
    "设备号在 `+0x4`"的自相矛盾就是这么来的 —— 其实一直在 `+0x8`）。
    **标量没问题；数组一律走这里。**
    """
    words = values.get(key) or []
    word = words[index // 2] if (index // 2) < len(words) else None
    if word is None:
        return default
    return (word >> (32 * (index % 2))) & 0xFFFFFFFF


def words_to_bytes(words: list[int]) -> bytes:
    return b''.join(v.to_bytes(8, 'little') for v in words)


#: 原生模组页探针的失败码（探针里的 `kFailure*` 常量，**只在探针构建**里有意义）。
NATIVE_MODS_FAILURES = {
    0: '没有失败',
    1: '输入跳板拿不到',
    2: '游戏模块没找到',
    3: '`SetState` 入口守卫不符',
    4: '`g_MenuManager` 为空',
    5: '`Menu_Mods` 入口守卫不符',
    6: '`Menu_Mods::Render` 入口守卫不符',
}
#: 手动 `Init` 的结果（探针里的 `kInit*` 常量）。
NATIVE_MODS_INIT_RESULTS = {
    0: '还没试',
    1: '成功',
    2: '入口守卫不符',
    3: '`g_MenuManager` 为空',
    4: '游戏模块没找到',
}
#: `ButtonAction` 的号 → 名字（与 `runtime/source/lua_runtime.cpp` 的 `kButtonActionConstants`
#: 同一口径；扫描覆盖 0..27，`ACTION_CONSOLE(28)` 不在扫描范围里）。
NATIVE_MODS_ACTIONS = {
    0: 'ACTION_LEFT', 1: 'ACTION_RIGHT', 2: 'ACTION_UP', 3: 'ACTION_DOWN',
    4: 'ACTION_SHOOTLEFT', 5: 'ACTION_SHOOTRIGHT', 6: 'ACTION_SHOOTUP', 7: 'ACTION_SHOOTDOWN',
    8: 'ACTION_BOMB', 9: 'ACTION_ITEM', 10: 'ACTION_PILLCARD', 11: 'ACTION_DROP',
    12: 'ACTION_PAUSE', 13: 'ACTION_MAP', 14: 'ACTION_MENUCONFIRM', 15: 'ACTION_MENUBACK',
    16: 'ACTION_FULLSCREEN', 17: 'ACTION_MUTE', 18: 'ACTION_RESTART', 19: 'ACTION_JOINMULTIPLAYER',
    # ★ 2026-09-30 批次 222 更正：16/17/18 在 **Rep+** 里换了名字（运行时表 `kButtonActionConstants`
    #   早已改对，这张显示用的表却还留着 AB/AB+ 那一套 ⇒ 读数里会把动作名印错、误导判读）。
    20: 'ACTION_MENULEFT', 21: 'ACTION_MENURIGHT', 22: 'ACTION_MENUUP', 23: 'ACTION_MENUDOWN',
    24: 'ACTION_MENULT', 25: 'ACTION_MENURT', 26: 'ACTION_MENUTAB', 27: '(27 未定义)',
}
#: `MenuManager::eState`（静态表：`Update` 的分发表 0..15，逐格对得上具体页面）。
NATIVE_MODS_STATES = {
    0: '（空，走默认分支）', 1: 'Menu_Title', 2: 'Menu_Save', 3: 'Menu_Game',
    4: 'Menu_DailyChallenge', 5: 'Menu_Character', 6: 'Menu_SpecialSeed',
    7: 'Menu_Challenge', 8: 'Menu_Collection', 9: 'Menu_Stats', 10: 'Menu_Options',
    11: 'Menu_ControllerSelect', 12: 'Menu_KeyConfig', 13: 'Menu_Cutscenes',
    14: 'Menu_Bestiary', 15: 'Menu_Custom_Challenge',
}


def print_probe_native_mods_menu(values: dict[str, list[int]]) -> None:
    """打印"原生模组页探针"那一段（批次 019，`PROBE_BREAK_NATIVE_MODS_MENU`）。

    判据：诊断字 [0] 必须是 1。生产构建里这个符号不存在（读的是模块头），[0] 不会是 1，
    所以这一段会显示"本构建不含探针"而不是给出一堆看着像数据的垃圾。

    第二版（2026-09-21 深夜）：新增三格 —— 状态机当前状态、被按住的**动作号位图**、
    答过"是"的**手柄号位图**。第一版就是栽在"猜手柄号"上（真机读数里按键计数全 0）。

    第四~六版（2026-09-22）：渲染上下文（[24]/[25]）、页面空间被裁掉多少（[26]..[29]）、
    本页实际画在哪（[30]/[31]）、以及**条目换成真实模组**之后的十格（[32]..[41]）。
    那十格里最要紧的一条：纸上出现 `PROBE-MOD-A` 就是"真实数据没取到"（[32] = 2），
    与"纸上什么都没有"（渲染/位置那一层）不是同一类现象。
    """
    import struct as _struct
    raw = words_to_bytes(values.get('native_mods_probe') or [])
    print('=== 原生模组页探针（批次 019，只在 `PROBE_BREAK_NATIVE_MODS_MENU` 构建里）===')
    # 够 16 格（64 字节）就能给出全部结论，最后 1 格（`Init` 有没有留下 ModManager）
    # 是后加的：老读数只读了 8 个字，那时它是缺的 —— **缺哪一格就说哪一格缺**，
    # 不要因为少 4 个字节就把整段判成"读不到"（那会白烧一次 attach，项目里有过这种教训）。
    if len(raw) < 64:
        print('  （读不到：本构建不含探针，或调试桩这次没 attach 上）')
        return
    f = _struct.unpack_from('<17I', raw, 0) if len(raw) >= 68 else _struct.unpack_from('<16I', raw, 0)
    has_manual_mods_ptr = len(raw) >= 68
    if f[0] != 1:
        print('  （本构建不含探针 —— 诊断字第 0 格不是 1）')
        return
    print(f'  ZR 换状态 {f[1]} 次｜ZL 换状态 {f[2]} 次｜探针自己换到状态 {f[3]} = '
          f'{NATIVE_MODS_STATES.get(f[3], "（超出静态表范围）")}')
    print(f'  手动画原生页：{"开" if f[4] else "关"}｜Init {NATIVE_MODS_INIT_RESULTS.get(f[5], f[5])}｜'
          f'已经画了 {f[6]} 帧｜最近失败：{NATIVE_MODS_FAILURES.get(f[7], f[7])}')
    print(f'  单例：`g_Manager` {"读到" if f[8] else "没读到"}｜'
          f'`g_MenuManager` {"非空" if f[9] else "空（自动驱动的前置条件不成立）"}｜'
          f'状态机当前状态（`MenuManager+0x38`）= {f[11]} = '
          f'{NATIVE_MODS_STATES.get(f[11], "（超出静态表范围）")}')
    if f[15]:
        print(f'  引擎自己的模组表：begin/end 相差 {f[10]} 字节'
              + ('（0 = 空表 ⇒ 原生页即使画出来也没有条目）' if f[10] == 0 else ''))
    else:
        print('  引擎自己的模组表：那对 begin/end **不像合法指针** ⇒ 上面那个 0 **不能**读成"空表"，'
              '\n    ⇒ 说明我们对 `Manager+0x36800` 这个结构的解释不对，要回去重看静态证据')
    if len(raw) >= 96:
        import struct as _s3
        f24 = _s3.unpack_from('<24I', raw, 0)
        # 039 批次的"六档 Y 标定"用的那一格（[23]）。标定失败了、那条路已被 040 取代，
        # 所以只在它非零时才说一句（老读数件里它是有值的）。
        if f24[23]:
            print(f'  （039 批次的六档位置标定残留：第 {f24[23]} 档 —— 该做法已废弃，'
                  '见改动日志 037/040 节）')
    # 040 批次：入口中继装没装上 + 页面共享的画布原点。**这一节是"页面画在哪"的关键证据**：
    # 位置 = `MenuManager+0x3c`（共享原点）+ 页面自己的偏移（`Menu_Mods` 还会再加 (200,0)）。
    if len(raw) >= 112:
        import struct as _s4
        f28 = _s4.unpack_from('<28I', raw, 0)

        def _fl4(v):
            return _s4.unpack('<f', _s4.pack('<I', v))[0]

        relay_state = {0: '没试（安装函数没跑到）', 1: '★ 装成功（页面现在画在引擎的渲染上下文里）',
                       2: '装失败'}
        relay_failure = {
            0: '', 1: '（地址非法）',
            2: '（入口 16 字节与期望不符 ⇒ 版本不对，一个字节都没写）',
            3: '（竞技场 64 槽用满）', 4: '（写回校验失败 ⇒ 入口可能已被改写）',
            5: '（入口含 PC 相对指令）',
        }
        line = f'  `Menu_Title::Render` 入口中继：{relay_state.get(f28[24], f28[24])}'
        if f28[24] != 1:
            line += f'（原始失败码 {f28[25]}）{relay_failure.get(f28[25], "")}'
        print(line)
        print('  页面空间→屏幕的偏移 `MenuManager+0x3c` = ({:.1f}, {:.1f})'.format(
            _fl4(f28[26]), _fl4(f28[27])) +
              '　←　引擎每个页面 `Render` 都"这个偏移 + 页面自己的位置"')
    # 041 批次：可见屏幕有多大 —— 页面坐标空间是 480×270、屏幕比它小、**居中裁切**。
    # 这一段直接给出"页面空间的哪一块在屏幕外"，这是"纸偏上"那类现象的判据。
    if len(raw) >= 120:
        import struct as _s5
        f30 = _s5.unpack_from('<30I', raw, 0)

        def _fl5(v):
            return _s5.unpack('<f', _s5.pack('<I', v))[0]

        width, height = _fl5(f30[28]), _fl5(f30[29])
        off_x, off_y = _fl5(f30[26]), _fl5(f30[27])
        if width > 0.0 and height > 0.0:
            print('  可见屏幕 {:.0f}×{:.0f}｜页面坐标空间 480×270'.format(width, height) +
                  '　⇒　可见区在页面坐标里 = x∈[{:.0f},{:.0f}]、y∈[{:.0f},{:.0f}]'.format(
                      -off_x, -off_x + width, -off_y, -off_y + height) +
                  '，即上边 {:.0f} 格、左右各 {:.0f} 格在屏幕外'.format(off_y + 270.0 - height, off_x + 480.0 - width))
        else:
            print('  可见屏幕：（这一格是 041 新加的，本次读数里是 0 ⇒ 没读到 WIDTH/HEIGHT）')
    if len(raw) >= 128:
        import struct as _s6
        f32 = _s6.unpack_from('<32I', raw, 0)

        def _fl6(v):
            return _s6.unpack('<f', _s6.pack('<I', v))[0]

        print('  本页实际画在页面坐标 ({:.1f}, {:.1f})'.format(_fl6(f32[30]), _fl6(f32[31])) +
              '　←　目标 (240, 72)：纸铺满页面框 [0,480]、上沿压在页面顶端')
    # 批次 043：条目改成**真实模组**之后，那十格就是"换成功了没有"的全部判据。
    # 关键的一条：**纸上看到 `PROBE-MOD-A` 就是"真实数据没取到"**（[32] = 2），
    # 它与"纸上什么都没有"（渲染/位置那一层）是两件事，别混着看。
    if len(raw) >= 168:
        import struct as _s7
        f42 = _s7.unpack_from('<42I', raw, 0)
        source_state = {0: '还没试', 1: '★ 用的是真实模组（发现结果 + `metadata.xml` 的 <name>）',
                        2: '真实数据没取到 ⇒ 退回那三个固定测试名（纸上会出现 `PROBE-MOD-A`）'}
        print('  条目数据源：' + source_state.get(f42[32], str(f42[32])))
        print('  发现到 {} 个模组目录｜其中 {} 个"开着"｜真实条目造出 {} 条'.format(
            f42[33], f42[34], f42[35]))
        print('  `metadata.xml`：读到 <name> {} 次｜没有这个文件 {} 次（正常，退目录名）｜'
              '解析到了但读失败 {} 次'.format(f42[36], f42[38], f42[37]))
        bindings = {0: '没读过', 1: '★ 校验通过', 2: '校验没过（⇒ 全部退目录名）'}
        resolve_fn = {0: '没试', 1: '★ 用中继记下的原函数入口',
                      2: '用守卫过的引擎入口（中继没装时才走这条）',
                      3: '两条都没拿到（⇒ 全部退目录名）'}
        print('  `ReadTextFile` 那组绑定：' + bindings.get(f42[39], str(f42[39])) +
              '｜挂载解析入口 `GetMountedFilePath`：' + resolve_fn.get(f42[40], str(f42[40])))
        forms = []
        if f42[41] & 1:
            forms.append('原样形式（带 `rom:/`）就解析出来了')
        if f42[41] & 2:
            forms.append('去掉前缀才解析出来')
        print('  解析用的输入形式：' + ('、'.join(forms) if forms else
                              '一次都没解析出来（⇒ 挂载里找不到这些路径，全退目录名）'))
        print('    ↑ 位 1 置位**不代表有问题**：读的是解析出来的绝对路径，不是这条输入'
              '（2026-09-22 的事故就是把输入当成了要读的路径）')
    # 批次 046：在选择界面那一列里插入"模组"那一行。看四件事：
    # 中继装没装、导航有没有动、光标有没有走到我们那一格、那一格画在哪。
    if len(raw) >= 232:
        import struct as _s8
        f58 = _s8.unpack_from('<67I', raw, 0) if len(raw) >= 67 * 4 else _s8.unpack_from('<58I', raw, 0)

        def _fl8(v):
            return _s8.unpack('<f', _s8.pack('<I', v))[0]

        relay = {0: '没试（安装函数没跑到）', 1: '★ 装成功（那一列现在由我们接管排版）', 2: '装失败'}
        print('  「模组」那一行：入口中继 ' + relay.get(f58[42], str(f58[42])))
        if f58[42] != 1:
            print(f'    原始失败码 {f58[43]}｜GetLayer 跳板 {f58[53]}（1 = 拿到）'
                  f'｜画字入口 {f58[54]}（1 = 拿到）｜g_Manager {f58[55]}（1 = 拿到）')
        print(f'  当前第 {f58[44]} 格（**3 = 我们那一格**）｜写回引擎的索引 {f58[45]}（夹在 0..4）'
              f'｜光标帧 {f58[46]}' + ('　★ 正停在我们那一格上' if f58[52] else ''))
        print(f'  我们自己的导航：上 {f58[47]} 次、下 {f58[48]} 次、确认 {f58[49]} 次'
              f'（其中落在我们那一格上 {f58[50]} 次）')
        print(f'  那一屏上我们画了 {f58[51]} 帧｜光标当前那一格的上沿 y = {_fl8(f58[57]):.1f}'
              f'｜那行字（ASCII）画在 y = {_fl8(f58[56]):.1f}')
        if len(raw) >= 240:
            # 048 新增两格：那一行画了几次 / 对照那一次（红色中文）画了几次。
            # 两个都 > 0 而屏幕上看不见 ⇒ 是"字体没有那个字形"，不是调用没发生。
            cjk_state = {0: '没试', 1: '★ 装上了（这一行是中文）', 2: '入口守卫不过（版本不对）',
                         3: '引擎拒绝/没装上（路径或资源不对）'}
            flags = f58[59]
            print(f'  画字调用次数：{f58[58]} 次｜页面原点：'
                  + ('★ 拿到' if flags & 1 else '**没拿到** ⇒ 字会画到屏幕角上')
                  + '｜中文字体：' + cjk_state.get((flags >> 2) & 0x7, '?'))
        if len(raw) >= 67 * 4:
            # 批次 055：那一行改成**贴图**之后，"到底画的是贴图还是退回画字"看这一段。
            # 贴图那条链断在哪一步，直接由 `[62]` 说；`[63]` = 0 而 `[58]` > 0 ⇒ 画的是字。
            code = f58[60]
            chars = ''.join(chr((code >> (8 * shift)) & 0xFF) for shift in (0, 1))
            language = {0: '没试', 1: '★ 拿到', 2: '入口守卫不过（版本不对）',
                        3: '单例空', 4: '挑到的是 en 兜底（不是这个语言的美术）'}
            image = {0: '没试', 1: '★ 贴图好了', 2: '入口守卫不过（版本不对）',
                     3: '单例或描述符空', 4: '引擎返回了空指针', 5: '语言还没定'}
            print(f'  语言码 = {chars!r}（{language.get(f58[61], "?")}）'
                  f'｜贴图 = {image.get(f58[62], "?")}'
                  f'｜贴图画了 {f58[63]} 帧｜页面原点（贴图那次）= '
                  + ('★ 拿到' if f58[64] else '**没拿到**'))
            forms = ''.join('★' if f58[65] & (1 << bit) else '·' for bit in range(4))
            print(f'  四种路径形态（按反汇编结论 / 第一版 / 扩展名+文件名 / 内容路径）：{forms}'
                  f'　实际用了第 {f58[66]} 种（0 = 都没成）')
        if len(raw) >= 100 * 4:
            # 批次 058：「模组」那一格的确认键接上之后（照 PC 走引擎的**状态 16**）。
            # 三段判据：进得去（[69]/[70]/[68]）、页面活着（[71]..[74]）、出得来（[76]）。
            import struct as _s9
            f82 = _s9.unpack_from('<100I', raw, 0)

            def _fl9(v):
                return _s9.unpack('<f', _s9.pack('<I', v))[0]

            print(f'  「模组」那一格的确认 → 模组页（引擎状态 {f82[67]}）：'
                  f'进过 {f82[69]} 次｜Reset 那一下 ' + {0: '没试', 1: '★ 调到', 2: '入口守卫不符'}
                  .get(f82[70], '?')
                  + f'｜当前' + ('★ 就在模组页里' if f82[68] else '不在模组页'))
            print(f'    模组页：驱动 {f82[71]} 帧、画 {f82[77]} 帧｜页面看到 {f82[78]} 条'
                  f'（模组总开关 [79] = {f82[79]}）')
            print(f'    页面里的状态：选中第 {f82[72]} 条｜按住计时 {f82[73]}'
                  f'｜这次改过开关没有 = ' + ('**改过**（退出时该写清单）' if f82[74] else '没改'))
            print(f'    我们接的键：确认（切换开关）{f82[75]} 次、返回 {f82[76]} 次'
                  + ('　← 返回走引擎自己的 `SetState(3)`' if f82[76] else ''))
            if len(raw) >= 100 * 4:
                gate_state = ('★ 已置上（0 会让页面只用一个颜色画所有行 ⇒ 切换开关看不出来）'
                              if f82[79] else '**还是 0** ⇒ 页面会把所有行画成同一种颜色')
                print(f'    模组总开关 [79] = {f82[79]}（{gate_state}）'
                      f'｜我们置过没有 [82] = {f82[82]}（置之前它是 {f82[83]}）')
            outcome = {0: '没被调用（那次确认不在我们那一格）',
                       1: '页面没准备好（`Init` 不是 ok，当场补做也没成）',
                       2: '当时不在选择界面', 3: '★ 进了状态 16', 4: '**没进去**（`[7]` 是失败码）'}
            print(f'    那一格确认的接管：最后一次确认时我们在第 {f82[84]} 格'
                  f'｜结果 [85] = {f82[85]}（{outcome.get(f82[85], "?")}）')
            print(f'    `ApplyState`：真把 `SetState` 调出去 {f82[88]} 次'
                  f'｜因入口守卫不过而**没调** {f82[89]} 次'
                  + ('　← **非 0 就说明"我们的状态切换根本没发生"**（批次 060 就是这么栽的）'
                     if f82[89] else ''))
            print(f'    `SetState` 中继：{f82[87]}（1 = ★ 装上了）'
                  f'｜替我们那一格挡掉了 {f82[86]} 次'
                  + ('　← **不为 0 就说明"引擎本来要跳错页"**，那正是用户看到跳到统计页的原因'
                     if f82[86] else ''))
            print(f'    那一行的贴图：因关卡/房间事件重载过 {f82[97]} 次'
                  f'｜`MC_POST_NEW_LEVEL` 计数 = {f82[99]}'
                  f'｜当前 `Game*`（1 = 在局内）= {f82[98]}')
            print(f'    开关写回：页内改开关 {f82[94]} 次（失败 {f82[95]}）'
                  f'｜退出页面时落盘 = ' + {0: '没试', 1: '★ 成功', 2: '失败'}.get(f82[96], '?')
                  + '（写的是**游戏存档分区**，不是卡上覆盖层）')
            print(f'    纸的位置：定下来的 Y = {_fl9(f82[90]):.1f}'
                  f'｜现场实际画在 ({_fl9(f58[30]):.1f}, {_fl9(f58[31]):.1f})'
                  '　← 过渡期间这一对会动（纸跟着画布滑），停稳后应当是 (240, 72)')
            print(f'    目标偏移 X：我们算的 {_fl9(f82[91]):.1f}｜停稳后现场是 {_fl9(f82[92]):.1f}'
                  f'｜停稳后的位置修正量 {_fl9(f82[93]):.2f}（0 = 公式一次都没错）')
            print(f'    引擎给状态 16 的滚动目标 y = {_fl9(f82[80]):.1f}'
                  f'｜进入那一刻的视图偏移 y = {_fl9(f82[81]):.1f}'
                  f'（现场 `[27]` 现在是 {_fl9(f58[27]):.1f} —— 两个数不一样就说明**引擎在滑**）')
        if len(raw) >= 109 * 4:
            # 批次 072：那一行改用引擎的**按文件名加载贴图**（`ImageManager::LoadImage(路径,...)`）。
            #
            # 为什么（两条，都有真机证据）：
            #   ① 从内存加载的贴图**没有磁盘文件背书**，引擎在关卡资源加载时会把它从图片缓存里
            #      卸掉（真机症状：跑过几次对局之后那一行变透明 —— 绘制每帧照调、位置也对、
            #      对象非空，就是画不出来；重启才好）。引擎自己的行与所有模组都是**从磁盘文件**
            #      加载的，从不消失。
            #   ② 上一批（071）试的 `ANM2::Load` + `ANM2::Render` **真机崩了**
            #      （`Data Abort @ 0x0`，栈为 `ANM2::Render → AnimationLayer::RenderFrame
            #      → GetSourceQuad`）：`.anm2` 找到了，但精灵表没载进来（引擎找的是 `.png`，
            #      我们只放了 `.pcx`）。⇒ 现在的路线"**拿到非空的贴图指针才画**"，结构上不会再崩。
            #
            # 判据：**先看 [100]**。
            #   * 1（★ 装好）⇒ 看 [104] 应当随帧数涨；[105] 会在进过一局之后开始涨；
            #   * 4（候选全返回空）⇒ 引擎没找到文件，看 [101]/[102]（全不命中 = 路径不对）；
            #   * 3（管理器/描述符还没取到）⇒ 内存那条路先失败过，看 [62]；
            #   * 2（入口守卫不过）⇒ 中继没有原函数且原版入口不符；检查挂点安装与模块版本。
            #   * 5 / 0 ⇒ 还没走到（多半是不在"选择界面"那一屏）。
            # 老读数（100 格）里这一段不存在 ⇒ 按长度判，缺了就少打一段，不当成错误。
            import struct as _s10
            f109 = _s10.unpack_from('<109I', raw, 0)
            file_route = {
                0: '还没试', 1: '★ 装好（按文件加载在用）',
                2: '**入口守卫不过**（中继没提供原函数且原版入口不符；检查挂点与模块版本）',
                3: '管理器/顶点描述符还没取到（内存那条路先失败过，看 [62]）',
                4: '**所有候选都返回空**（引擎没找到那个 `.pcx`）',
                5: '语言还没定（等下一帧，不是失败）',
            }
            print('  那一行（新路线：引擎**按文件名加载贴图**）：'
                  f'{file_route.get(f109[100], f109[100])}')
            print(f'    原函数入口/入口守卫 = ' + {0: '没试', 1: '★ 可用', 2: '不可用'}.get(f109[108], '?')
                  + f'｜文件版 `LoadImage` 调了 {f109[103]} 次'
                  f'｜磁盘那张图画了 {f109[104]} 帧'
                  f'｜关卡切换后**从磁盘重读** {f109[105]} 次')
            cand = ''.join('★' if f109[102] & (1 << bit) else '·' for bit in range(8))
            print(f'    候选（路径 1..4 × flag，位序 = 路径序号×2+flag）：{cand}'
                  f'　命中第 {f109[101]} 条（0 = 都没成）')
            if f109[101]:
                print(f'    命中那条路径长 {f109[106]} 字符、`flag` = {f109[107]}'
                      '（★ 这两格回答"哪种写法引擎认"与"那个 bool 是什么语义"）')
            if f109[100] == 1 and f109[104] == 0:
                print('    ⚠ 路线装好了却一帧都没画 ⇒ 看 [64]（页面原点）与 `modRowRenderCalls`')
            if f109[100] == 1 and f109[105] == 0:
                print('    （还没经过关卡/房间事件 ⇒ 首次重读要等进过一局；'
                      '这一格正是"重读判据有没有生效"的留证）')
        if len(raw) >= 110 * 4:
            # 批次 075（2026-09-23）：那一行**改由引擎自己画**（用户定案 A 路线）。
            #
            # 做法：PC 版每个语言的菜单动画本来就有第六层 `Item6`（Switch 版删掉了、只有法语留着），
            # 我们把它按 PC 的数值补回 `gamemenu.anm2`（`tools/gamemenu_mod_row.py --emit-menu-anm2`），
            # 于是那一行由引擎自己的整页渲染画出来，生命周期与其余五行同源。
            #
            # 判据：**[109] = 1 ⇒ 引擎在画，我们那几条兜底绘制不再执行**（[104]/[63]/[58] 应当不再涨，
            # 这是"没有画两遍"的留证）；**[109] = 2 ⇒ 覆盖层里那份菜单动画没装**（或没生效），
            # 行为与上一批一字不变（兜底绘制接管）。这一格就是 `modRowNativeLayer`。
            import struct as _s11
            f110 = _s11.unpack_from('<110I', raw, 0)
            native = {
                0: '还没看（不在选择界面那一屏 / 中继没装）',
                1: '★ 有：那一行由**引擎自己**画（我们不再画）',
                2: '没有：覆盖层里那份菜单动画没生效 ⇒ 退回我们自己的兜底绘制',
            }
            print(f'  那一行的归属（[109]）：{native.get(f110[109], f110[109])}')
            if f110[109] == 1:
                print(f'    （引擎在画 ⇒ 兜底那几条应当停住：磁盘图画了 {f110[104]} 帧、'
                      f'内存图画了 {f110[63]} 帧、画字 {f110[58]} 次）')
            elif f110[109] == 2:
                print('    ⚠ 覆盖层里没有那一层 ⇒ 用 `tools/emit_mod_row_art.py --tree ... '
                      '--menu-row-layer --dump-root <dump>` 重新打包部署')
    if len(raw) >= 92:
        import struct as _s2
        f23 = _s2.unpack_from('<23I', raw, 0)
        def _fl(v):
            return _s2.unpack('<f', _s2.pack('<I', v))[0]
        print('  坐标候选（原始 float）：Menu_Title = ({:.1f}, {:.1f})｜Menu_Options = ({:.1f}, {:.1f})｜'
              'Menu_KeyConfig = ({:.1f}, {:.1f})'.format(
                  _fl(f23[17]), _fl(f23[18]), _fl(f23[19]), _fl(f23[20]), _fl(f23[21]), _fl(f23[22])))
    if has_manual_mods_ptr:
        print('  我们那次 Init：' + ('确实进了函数体（`对象+0x170` 拿到了 ModManager）★'
                                    if f[16] else '没留下痕迹（`对象+0x170` 是空的 ⇒ 这次调用没真正执行完）'))
    else:
        print('  我们那次 Init：（这一格是后加的，本次读数只读了 8 个字 ⇒ 缺）')
    held = [NATIVE_MODS_ACTIONS[i] for i in range(28) if f[12] & (1 << i)]
    if f[14] == 0:
        print('  输入扫描：一轮都没跑（更新中继可能没到过；诊断字第 [14] 格 = 0）')
    else:
        print(f'  输入扫描：跑了 {f[14]} 轮｜被按住过的动作号 = '
              + ('、'.join(held) if held else '（一个都没有——按键期间读数才会非空）'))
        controllers = [str(i) for i in range(32) if f[13] & (1 << i)]
        print('  答过"是"的手柄号 = ' + ('、'.join(controllers) if controllers else '（一个都没有）')
              + '　← 这一行就是"该用哪个手柄号去问输入"的答案')


def print_console_state(values: dict[str, list[int]]) -> None:
    """打印**游戏控制台**那一段（批次 121）。

    这不是"某个模组"的功能，而是**运行时自己**把游戏本体的 `IsaacRepentance::Console` 建起来、
    把命令喂进去（Switch 版把这个类"拆线"了：类与全部命令实现都在镜像里，但引擎从不实例化它）。

    读的时候按这个次序看：
      * `[0]` 必须 = 1（功能编进来了）；
      * `[11]` 帧数（`frames`）必须一直涨 —— 恒 0 = 每帧点根本没跑到，别的格都别信；
      * `[1]` 入口位图应当 = 31（0b11111 = 构造/Init/RunCommand/参数块/开键盘 全解析到）；
      * `[4]` 最近结论码（0 成功 / 1 空命令 / 2 入口缺 / 3 没有玩家 / 4 命令太长 /
        5 抓到越界写 / 6 输出缓冲满）；
      * `[13]` 越界写**必须恒 0**；
      * `[10]` 最近按下的动作号（0xFFFFFFFF = 还没学到）—— 组合键就是靠它定下来的；
      * `[18]` **累计位图**（批次 122）：本会话里被按住过的**每一个**动作号 —— 连打时 `[10]`
        会被顶掉，这一格不会。按几个键再读一次，整张"按键 ↔ 动作号"映射就齐了。
    """
    import struct as _struct
    raw = words_to_bytes(values.get('console_state') or [])
    print('=== 游戏控制台（批次 121：自己建 Console 实例 + `Isaac.ExecuteCommand` 真实现）===')
    if len(raw) < 22 * 4:
        print('  （读不到：这一版运行时不含它，或调试桩这次没 attach 上）')
        return
    f = _struct.unpack_from('<22I', raw, 0)
    if f[0] != 1:
        print(f'  （第 [0] 格 = {f[0]}，不是 1 ⇒ 这一版运行时没编进这套功能）')
        return
    bits = ''.join('★' if f[1] & (1 << bit) else '·' for bit in range(5))
    status = {0: '成功', 1: '空命令', 2: '入口缺', 3: '没有玩家（没调引擎）', 4: '命令太长',
              5: '抓到越界写 ⇒ 已停用', 6: '输出缓冲已满',
              7: '★ 控制台已关（被总开关拒绝，没调引擎）'}
    print(f'  入口解析 = {bits}（位图 {f[1]}；31 = 构造/Init/RunCommand/参数块/开键盘 全齐）'
          f'｜实例已建 = {"是" if f[2] else "否"}')
    print(f'  引擎真的被调 {f[3]} 次｜最近结论 = {status.get(f[4], f[4])}（{f[4]}）'
          f'｜最近命令 {f[5]} 字节｜输出累计 {f[6]} 字节（最近新增 {f[7]}）')
    print(f'  输出串已换引擎堆缓冲 = {"是" if f[12] else "否"}'
          f'｜软键盘：请求 {f[8]} 次 / 交回 {f[9]} 次'
          f'｜组合键按住 = {"是" if f[17] else "否"}｜输出还要显示 {f[16]} 帧')
    print(f'  每帧点跑过 {f[11]} 帧（恒 0 = 打不到这个点）'
          f'｜布局自检 {f[14]} 次 / 通过 = {"是" if f[15] else "否"}'
          f'｜对象越界写 = {f[13]} 次（**必须恒 0**）')
    print('  最近按下的动作号 = '
          + ('（还没学到：这一版没被按过任何键）' if f[10] == 0xFFFFFFFF else f'{f[10]}'))
    # [18] 累计位图（批次 122）：一次读数拿到整张"按键 ↔ 动作号"映射。
    seen = [str(index) for index in range(32) if f[18] & (1 << index)]
    print(f'  按过的动作号（累计位图 0x{f[18]:08x}）= '
          + ('、'.join(seen) if seen else '（一个都没有 —— 按几个键再读一次就有了）'))
    print(f'  呼出组合键 = 动作 {14}/{15} 需连续按住约 0.8 秒'
          f'（现在按住 = {"是" if f[17] else "否"}）')
    # [19]..[21] 总开关（批次 124）：对应 PC 的 `EnableDebugConsole`，开关本体在模组页那一行。
    print(f'  ★ 总开关 [19] = ' + ('★ 1 ⇒ 控制台可用（默认）' if f[19]
                                else '0 ⇒ **控制台已关**：不扫按键、不弹键盘、连 '
                                     '`Isaac.ExecuteCommand` 也一律拒'))
    print(f'  被开关拒绝的命令 [20] = {f[20]} 次'
          f'｜开关状态文件读写失败 [21] = {f[21]} 次'
          + ('　← 读失败**不改开关值**（回默认"开"），只计数' if f[21] else ''))


def print_mod_menu_native(values: dict[str, list[int]]) -> None:
    """打印**生产版**的「模组那一行 + 模组页」那一段（批次 077）。

    与上面那段探针状态面**不是同一份东西**：
      * 探针（`print_probe_native_mods_menu`）只在 `PROBE_BREAK_NATIVE_MODS_MENU` 构建里存在，
        里面还有一大堆"路线探索"用的格子；
      * 这一段是**生产构建里恒在**的那 26 格（`runtime/source/mod_menu_native.hpp` 的 `State`），
        它只回答"这一套功能现在是什么状态"。

    判据：第 [0] 格必须是 1。生产构建里符号一定存在；读到 0 只可能是调试桩这次没 attach 上。
    字段顺序 = 结构体字段顺序，**加字段只能往后加**（插/删会让老读数整段错位）。
    """
    import struct as _struct
    raw = words_to_bytes(values.get('mod_menu_state') or [])
    print('=== 「模组」那一行 + 模组页（生产版，批次 078）===')
    if len(raw) < 40 * 4:
        print('  （读不到：这一版运行时不含它，或调试桩这次没 attach 上）')
        return
    # 批次 116 起状态面是 45 个 u32（[41]..[44] = 发现清单自证四格）；
    # 批次 117 起是 51 个（[45]..[50] = 局内单向闩锁六格）；
    # 批次 118 起是 **54 个**（[51]..[53] = 在一局里吗 / 边沿写位调用几次 / 边沿写位的结果）；
    # 批次 119 起是 **56 个**（[54]..[55] = 出局时留存的污染 / 把留存接回来过几次）；
    # 批次 120 起是 **58 个**（[56]..[57] = 存档分区里那个标记我们认为它是几 / 读写失败几次）。
    # 批次 135 起是 **60 个**（[58]..[59] = 本模块堆的**空闲**/*已用*字节数，口径 newlib `mallinfo()`）。
    # 批次 153 起是 **61 个**（[60] = 喂模组 content 的触发时机）。
    # 批次 154 起是 **62 个**（[61] = "模组脚本之前"那一次走到了哪一步 0..3）。
    # 批次 159 起是 **64 个**（[62]/[63] = 引擎说「继续游戏」可不可选 / 因为它不可选而跳过它的次数）。
    # 批次 180 起是 **68 个**（[64]~[67] = 进程内存总量 / 已用、系统资源池总量 / 已用；
    # `svcGetInfo` 的 6/7/16/17，失败 = 0xFFFFFFFF）。
    # 批次 378 起是 **74 个**（[68]~[73] = 16 项入口解析成功/失败位图 + 四格调用计数；
    # 见下面 `if len(f) >= 74` 那一段的判读表）。
    # 批次 409 起是 **75 个**（[74] = `ModManager+0x368` 那个默认模组道具 ANM2 的载入次数，正常 = 1）。
    # 更老的读数文件里只有 68 / 64 / 62 / 61 / 60 / 58 / 56 / 54 / 51 / 45 / 41 / 40 个
    # ⇒ 逐级回退，下面凡是用到新格的地方都由 `len(f) >= N` 守住（离线重放老文件不会炸）。
    # 当前生产State为90格；保留旧raw快照的76格及以下解码。
    f = (_struct.unpack_from('<90I', raw, 0) if len(raw) >= 90 * 4
         else _struct.unpack_from('<76I', raw, 0) if len(raw) >= 76 * 4
         else _struct.unpack_from('<75I', raw, 0) if len(raw) >= 75 * 4
         else _struct.unpack_from('<74I', raw, 0) if len(raw) >= 74 * 4
         else _struct.unpack_from('<68I', raw, 0) if len(raw) >= 68 * 4
         else _struct.unpack_from('<64I', raw, 0) if len(raw) >= 64 * 4
         else _struct.unpack_from('<62I', raw, 0) if len(raw) >= 62 * 4
         else _struct.unpack_from('<61I', raw, 0) if len(raw) >= 61 * 4
         else _struct.unpack_from('<60I', raw, 0) if len(raw) >= 60 * 4
         else _struct.unpack_from('<58I', raw, 0) if len(raw) >= 58 * 4
         else _struct.unpack_from('<56I', raw, 0) if len(raw) >= 56 * 4
         else _struct.unpack_from('<54I', raw, 0) if len(raw) >= 54 * 4
         else _struct.unpack_from('<51I', raw, 0) if len(raw) >= 51 * 4
         else _struct.unpack_from('<45I', raw, 0) if len(raw) >= 45 * 4
         else _struct.unpack_from('<41I', raw, 0) if len(raw) >= 41 * 4
         else _struct.unpack_from('<40I', raw, 0))
    if f[0] != 1:
        print(f'  （第 [0] 格 = {f[0]}，不是 1 ⇒ 这一版运行时没编进这套功能）')
        return
    relay = f[1]
    print('  三个入口中继 = ' + ''.join('★' if relay & (1 << bit) else '·' for bit in range(3))
          + f'（位图 {relay}）　← 依次 `Menu_Game::Render` / `Menu_Title::Render` / `SetState`')
    owner = {1: '★ 引擎在画（覆盖层生效）', 2: '我们在兜底画（引擎那份动画里没有那一层）'}
    print(f'  那一行的归属 = {owner.get(f[3], f[3])}'
          f'｜我们**真的画出东西** {f[4]} 帧（引擎在画时必须是 0）'
          f'｜兜底这条路走过 {f[5]} 帧')
    lang = bytes(f[6].to_bytes(4, 'little')).split(b'\0')[0].decode('ascii', 'replace')
    print(f'  语言码 = {lang!r}｜当前第 {f[7]} 格（3 = 我们那一格）'
          f'｜写回引擎的**行号** = {f[8]}（必须恒在 0..4）')
    print(f'  确认落在我们那一格 {f[9]} 次'
          f'｜模组页：进 {f[10]} 次 / 返回 {f[11]} 次 / 我们驱动了 {f[12]} 帧')
    # 批次 126：表里**第 1 行（下标 0）是控制台总开关**（`Console: ON/OFF`），模组从第 2 行起
    # ⇒ 条目数比模组数多 1；选中项 0 = 控制台开关那一行（批次 124 那种"选中项 = 模组条数"不再出现）。
    console_hint = '（= 控制台开关那一行）' if (f[13] and f[14] == 0) else ''
    print(f'  条目 {f[13]} 条（含第 1 行的控制台开关，模组从第 2 行起）'
          f'｜选中第 {f[14]} 条{console_hint}'
          f'｜开关写回 = ' + {0: '没写过', 1: '★ 成功', 2: '失败'}.get(f[15], str(f[15])))
    print('  引擎字体对象 = ' + ('未改动（本批已撤掉换字体，恒 0）' if f[16] == 0 else
                                f'⚠ 被我们改写 {f[16]} 次（本批不该发生）')
          + '　← 那一页按字节画字，换字体救不了中文（真机结论）'
          f'｜`SetState` 中继挡下 {f[17]} 次')
    print(f'  语言换过 {f[20]} 次｜因换语言重载过模组页 {f[21]} 次'
          '　← 贴图会跟着换；**排版（那个键盘图标的位置）**要重启游戏才会换'
          '（引擎动画缓存按路径哈希认，而我们**不能**调它的全局回收：会把 EID 搞坏）')
    if f[2] != 0:
        print(f'  ⚠ 最近失败码 = {f[2]}（枚举与探针同一套语义；0 = 没有失败）')
    x = _struct.unpack('<f', _struct.pack('<I', f[18]))[0]
    y = _struct.unpack('<f', _struct.pack('<I', f[19]))[0]
    print(f'  模组页实际画在页面坐标 ({x:.1f}, {y:.1f})　← 已验收的静止位置是 (173, 72)')

    # ---- [22]..[25]：2026-09-23 定位"换语言后 EID 坏掉"加的四格 ----
    #
    # 判据（那条 bug 的根因是"引擎重建挂载点表后我们没把 Mod 挂载点挂回去"）：
    #   * `[24]` 必须是 **1**：会话挂载服务发布了，中继才拿得到实例。
    #     它曾经恒为 0（`SetSessionContentMountService` 从没被调用）⇒ 中继每次都空转。
    #   * `[22]` 应当**大于 0**（引擎每次重建挂载点表都会调到中继；换语言一定会重建）。
    #   * `[23]` 必须**恒 0**（`RemountAll()` 报错次数）。
    #   * `[25]`：bit0 = 最后一次 `Font:Load` 被引擎接受。**0 = 那次字体没装上**
    #     （`Font::Load` 开头先 `Unload()` ⇒ 失败会让字体永久停在"未加载"，
    #      真机现象就是"EID 的信息大部分不显示、只剩一个很浅的图标在闪"）。
    if len(f) >= 35:
        print(f'  ★ 每帧计数器 = {f[34]}　← **隔几秒读两次，这一格必须在涨**；不涨 = 我们的每帧更新没在跑')
    if len(f) >= 40:
        # ---- [35]..[39]：成就闸门（批次 098 起挂在 `PersistentGameData::SetReadOnly` 上）----
        #
        # 为什么挂在那里：它是全镜像**唯一**写"只读位"（`PGD+0x1`）的地方，24 个调用点全在开局路径上。
        # 我们的做法 = 把它的参数改成「引擎原参数 OR 按 PC 规则该禁」，禁与不禁都交回引擎。
        # 判据：
        #   * `[35]` 恒 0 ⇒ 引擎开局根本没调 `SetReadOnly`（闸门位置不对；正常一局至少 1 次）；
        #   * `[36]` 涨 = 引擎自己本来就要锁（特殊种子 / 挑战局）；
        #   * `[37]` 涨 = 我们按 PC 规则抬成锁（**开模组 且 妈腿成就未解锁**）；
        #   * `[38]` = 最后一次真正写下去的值（1 = 本局不给成就）；
        #   * `[39]` = 1 ⇒ 拿不到回退入口（此时我们**什么都不写**，退回 Switch 原生行为 —— 宁可不禁也不误禁）。
        print(f'  ★ 成就闸门（`SetReadOnly`）：被调到 {f[35]} 次｜引擎本来就要锁 {f[36]} 次｜'
              f'我们按 PC 抬成锁 {f[37]} 次｜最后写下的值 = {f[38]}')
        if f[35] == 0:
            print('     ⇒ ⚠ **一次都没被调到**：`SetReadOnly` 没被走到 ⇒ 闸门位置不对'
                  '（正常一局开局必然调它）')
        if f[39]:
            print('     ⇒ ⚠⚠ 出现过"拿不到回退入口"：我们**什么都没写**'
                  '（退回 Switch 原生行为，宁可不禁也不误禁）')
    if len(f) >= 34:
        print('  只读位（`PersistentGameData+0x1`，**真正挡成就的那一位**）= '
              + ('★ 已置位 ⇒ `TryUnlock` 会拒绝解锁 —— 由引擎按本局判据设的；'
                 '我们只在"开模组 且 妈腿成就未解锁"时把它抬成 1' if f[33]
                 else '⚠ 0 ⇒ 成就照样能解锁（此时若开着模组，看 [37] 有没有涨）'))
    if len(f) >= 33:
        sample = [f[32] & 0xFF, (f[32] >> 8) & 0xFF, (f[32] >> 16) & 0xFF, (f[32] >> 24) & 0xFF]
        print(f'  成就位数组抽样（id 0..3）= {sample}'
              + ('　← 只含 0/1 ⇒ 位置读对了 ✓' if all(v in (0, 1) for v in sample)
                 else '　⚠ 出现非 0/1 ⇒ **偏移不对**，别信 [31]'))
    if len(f) >= 32:
        print('  成就 #4（打过妈妈）已解锁 = '
              + ('★ 是 ⇒ 按 PC 规则**不锁**成就（模组随便用）' if f[31]
                 else '否 ⇒ 有模组开着时**锁**成就（PC 规则）'))
    if len(f) >= 31:
        print(f'  `metadata.xml` 的解析口径：应用根相对名成功 {f[27]} 次'
              f'｜只有带 `rom:/` 前缀才成 {f[28]} 次'
              + ('　⚠ 说明新口径不对，要调' if f[28] else '')
              + f'｜两种都没成 {f[29]} 次（那几行退成**目录名**）')
    if len(f) >= 41:
        # ★★ 批次 107 起：这两格**必须分开看**（它们回答不同的问题）——
        #    [40] = **处于启用状态**的个数（**判据就是它**，PC 口径）；[30] = 本局**实际加载**的个数。
        print(f'  处于**启用状态**的真实模组 = {f[40]} 个　← ★ 判据看的是这一格（PC 口径：'
              "列表里每一项的启用位，开关一开就变、不需要重启）")
        print(f'  本局**实际加载**的真实模组 = {f[30]} 个　← 诊断用（开机那一刻按存档开关过滤后加载的）'
              + ('　⚠ 与上一行不同 ⇒ 就是"开了开关但还没重启"那种情形' if f[30] != f[40] else ''))
    elif len(f) >= 31:
        print(f'  运行层**实际加载**的真实模组 = {f[30]} 个'
              '　（这一格是 107 之前的判据；卡上那份是旧构建 ⇒ 新构建还多一格 [40]）')
    if len(f) >= 45:
        # ★★ 批次 116：**发现清单自证四格** —— 专门用来解开"只看汇总数分不出是哪一种"的僵局。
        #    判读表（与状态面 `.hpp` 的 [41]..[44] 那段是同一份口径）：
        #      [41]==0 且 [44]==1 ⇒ **发现了但一条都没有**（判据永远看不到模组）
        #      [41]==0 且 [44]==0 ⇒ **发现这一步根本没跑到**（`ModMenuPublishDiscovered` 没被调）
        #      [41]>0  且 [42]==0 ⇒ 每一条都被开关服务判成"关闭"（状态文件写着全禁用）
        #      [43] 必须与"模组确实在跑"对得上（非 0），否则"清单里有名字"这一条是假的
        shown = min(f[41], 32)

        def _bit_string(mask):
            return ''.join('1' if (mask >> index) & 1 else '0' for index in range(shown)) or '（空）'

        print(f'  发现清单条数 [41] = {f[41]}｜发现跑过没 [44] = {f[44]}'
              + ('　⚠ 0 ⇒ 模组发现这一步根本没跑到（不是"没有模组"）' if f[44] == 0 else ''))
        print(f'  清单里「现在开着」的 [42] = 0x{f[42]:08X}　（第 0 条在最低位）{_bit_string(f[42])}')
        print(f'  清单里「本局真的加载了」的 [43] = 0x{f[43]:08X}　{_bit_string(f[43])}')
    if len(f) >= 51:
        # ★★ 批次 117：**局内单向闩锁**六格（设计与判据见 `mod_menu_native.hpp` 的 [45]..[50]）。
        #    判读表：
        #      [45]==1 ⇒ **这一局锁着成就**（出现过"开着模组 且 妈腿未解锁"，且之后关模组也不解除）；
        #      [46] 涨 = 出现过 0→1（那一下我们会**主动**写一次只读位 = "中途开启模组"生效的机制）；
        #      [47]/[48] = 我们看到过几次"局边界"、上一次是哪一路清的 —— 这两个是**清零点有没有跑到**
        #        的直接证据（[48] 3 = 离开一局 / 1 = 新开一局 / 2 = 读档）；
        #      [49] = `GameExit` 中继被调到几次（恒 0 ⇒ 那一路没装上或没被走到）；
        #      [50] = 1 才说明闩锁在生效；**0 = 因 `GameExit` 缺席而停用**（那时行为退回批次 107
        #        的实时判据：比 PC 松，但不会误锁）。
        reset_sources = {0: '还没遇到过局边界', 1: '开新局（真清零）',
                         2: '继续同一份存档（把留存接回来）', 3: '出局（把闩锁留成留存）'}
        print('  ★ 局内单向闩锁 [45] = ' + ('★ 1 ⇒ **这一局锁着成就**' if f[45]
                                          else '0 ⇒ 这一局没被锁（还没出现过"开着模组 且 妈腿未解锁"）')
              + f'｜置位过 {f[46]} 次｜清零过 {f[47]} 次（上次来源 = '
              + reset_sources.get(f[48], str(f[48])) + '）')
        print(f'  `GameExit` 中继被调到 [49] = {f[49]} 次'
              + ('　⚠ 恒 0 ⇒ 这条清零点没被走到（而闩锁要靠它把上一局的状态挡住）' if f[49] == 0 else '')
              + f'｜闩锁可用 [50] = ' + ('★ 1（在生效）' if f[50] else
                                        '⚠ **0 ⇒ 因 `GameExit` 挂点缺席而停用**（退回实时判据：'
                                        '比 PC 松，但不会误锁）'))
    if len(f) >= 54:
        # ★★ 批次 118 加的三格 —— 它们回答"闩锁为什么没置位""边沿写位到底生效了没有"。
        #    [51] 是判"要不要观察"的那道闸门（117 没有它，于是菜单上就置了位）；
        #    [52]/[53] 把"边沿写位"从"只能推断"变成"当场读回的事实"。
        print('  现在**在一局里**吗 [51] = '
              + ('★ 1 ⇒ 在一局里（闩锁会被观察）' if f[51]
                 else '0 ⇒ 不在局里（菜单上「开着模组」什么都不代表 ⇒ 闩锁**不观察**，这是故意的）'))
        edge_results = {0: '还没试过', 1: '★ 写了、读回确认是 1',
                        2: '拿不到回退入口 ⇒ 什么都没写（降级，不会误禁）',
                        3: '⚠ 写了但读回不是 1 ⇒ 那个地址不对，或写下去被立刻清了'}
        print(f'  边沿写位 [52] 试过 {f[52]} 次｜结果 [53] = '
              + edge_results.get(f[53], str(f[53])))
        # ★★ 批次 119：留存与"接回来"两格 —— 它们回答"继续同一份存档算不算同一局"。
        #    判读：退出后 [54] 应当变成 1（闩锁转成留存）；再"继续"时 [55] 涨 1、
        #    [45] 回到 1（接回来并补写了一次锁）。
        if len(f) >= 56:
            print('  出局时留存的污染 [54] = '
                  + ('★ 1 ⇒ 这一份存档在本局里被污染过（下一次"继续"会把它接回来）' if f[54]
                     else '0 ⇒ 没有留存（这一局没出现过"开着模组 且 妈腿未解锁"）')
                  + f'｜把留存接回来过 [55] = {f[55]} 次'
                  + ('　← 涨了说明"继续同一份存档"被当成同一局（用户 2026-09-25 的裁定）'
                     if f[55] else ''))
            if len(f) >= 58:
                # ★★ 批次 120：存档分区里那个标记（跨重启就靠它）。
                # 判读：[56] = 1 说明"这份存档用过模组"被记住在**文件**里；
                #       开新局会把它写回 0；[57] 必须恒 0（非 0 ⇒ 存档分区读写出了问题）。
                print('  存档分区里的"污染过"标记 [56] = '
                      + {0: '还不知道（这个会话里还没读过它）', 1: '★ 污染过（跨重启仍然禁成就）',
                         2: '干净（没污染 / 开新局已把它清掉）'}.get(f[56], str(f[56]))
                      + f'｜读写失败 [57] = {f[57]} 次'
                      + ('　⚠ 非 0 ⇒ 存档分区那条路有问题（读失败按"干净"处理，不会误禁）'
                         if f[57] else '　← 恒 0 才算"这条路是好的"'))
    if len(f) >= 60:
        # [58]/[59]：本模块自己的堆。撞满历史上的表现 = 转码时 `std::bad_alloc`
        # （09-25 无声卡死 / 09-26 崩溃报告），所以这一行是那类问题的现场判据。
        # 注意：每 60 帧才采一次 ⇒ 刚进游戏时可能是 0（还没采到）。
        print(f'  ★ 本模块堆：空闲 [58] = {f[58] / 1048576:.1f} MB｜已用 [59] = {f[59] / 1048576:.1f} MB'
              + ('　← 两格都是 0：还没采到（每 60 帧采一次）' if f[58] == 0 and f[59] == 0 else
                 ('　⚠ 空闲不足 4 MB ⇒ 大贴图转码有撞满风险' if 0 < f[58] < 4 * 1048576 else '')))
        # 批次 417：把"已用"拆成 **Lua 侧** 与 **其它**（这一格就是为此加的）。
        lua_bytes = (f[75] & 0xFFFFFFFF) if len(f) > 75 else 0
        if f[59] != 0 or lua_bytes != 0:
            others = (f[59] - lua_bytes) if f[59] >= lua_bytes else 0
            print(f'    └ Lua 状态 [75] = {lua_bytes / 1048576:.1f} MB｜'
                  f'其它（我们自己 malloc 的：Font/转码缓冲/挂载表/名字层…）≈ {others / 1048576:.1f} MB'
                  + ('　← [75] 还是 0：没采到（每 60 帧采一次）' if lua_bytes == 0 else ''))
    if len(f) >= 68:
        # [64]~[67]：批次 180（2026-09-28）加的**进程内存四格**。
        # 本批把 `HeapSize` 32 → 128 MiB（治"D6 跳舞模组卡死 / 人物模型消失"：转码单笔要
        # 4.62 MB 连续空间，而 09-27 的读数显示 32 MB 那块堆已经顶满、空闲只剩 2.2 MB ——
        # 见 `dist/specialist-heap-exhaustion-20260928.md`）。
        # ★ `0xFFFFFFFF` 是哨兵 = `svcGetInfo` 调用失败，**不是** 0 字节（两者必须分开）；
        #   四格全 0 = 还没采到（每 60 帧一次）或宿主构建。
        #
        # ★★ 2026-09-28 18:00 首次真机读数之后的**口径更正**（**别再按"余量很小 = 快爆了"去读**）：
        #   第一批真机数字 = `[64] = 3189.0 MB` / `[65] = 3188.0 MB`（该口径下"余量 1.0 MB"），
        #   而**同一刻游戏完全正常**（贴图桥 `实际转码 13 / 失败 0`，模块堆 arena 47.4 MB）——
        #   见 `dist/gdb-read-20260928-133745.txt` 与 `docs/改动日志-20260928.md` §180。
        #   ⇒ 这说明 `UsedMemorySize` 不是"进程实际写了多少"，而更接近"整个应用内存池已被提交"的量
        #     （Switch 应用内存池约 3.1 GB，与这里的 3189 MB 吻合）。**两边几乎相等是常态。**
        #   ⇒ **所以这两个数答不了"堆还能不能再抬"**（我当初写这个字段时的期望没兑现）。
        #     要判断"能不能往上抬"只有一个办法：**抬了之后能不能开机**（128 MiB 就是这么验的）。
        #   ⇒ `[66]`/`[67]` 恒 0 也不是错误：那是"系统资源池"，普通 Application 不使用它。
        _pm = (f[64], f[65], f[66], f[67])

        def _mem_mb(value):
            return '调用失败(0xFFFFFFFF)' if value == 0xFFFFFFFF else f'{value / 1048576:.1f} MB'

        if _pm == (0, 0, 0, 0):
            print('  ★ 进程内存：四格都是 0 ⇒ 还没采到（每 60 帧采一次）或宿主构建')
        else:
            print(f'  ★ 进程内存：可用总量 [64] = {_mem_mb(f[64])}｜已用 [65] = {_mem_mb(f[65])}'
                  f'｜系统资源池总量 [66] = {_mem_mb(f[66])}｜其中已用 [67] = {_mem_mb(f[67])}')
            if 0 < f[64] < 0xFFFFFFFF and f[64] >= f[65]:
                print(f'     ⇒ 该口径下余量 = {(f[64] - f[65]) / 1048576:.1f} MB'
                      '　★ 两边几乎相等是**常态** ⇒ 不能据此说"内存快满了"，也答不了"堆还能不能抬"')
            if 0 < f[66] < 0xFFFFFFFF and f[66] >= f[67]:
                left = f[66] - f[67]
                print(f'     ⇒ 系统资源池余量 = {left / 1048576:.1f} MB'
                      + ('　⚠ 余量不足 16 MB ⇒ 模块体积/挂载再涨就要顶到墙了'
                         if left < 16 * 1048576 else ''))
    if len(f) >= 74:
        # ★★ 批次 378（2026-10-05）：**把"逐模组喂 content"从 2 项补到引擎那 16 项**之后的六格。
        #
        # 为什么要有它们：本批之前只喂 `costumes2.xml` / `music.xml`，其余 12 个文件的内容在
        # Switch 上**从来就没进过引擎**（引擎自己那条 `ModManager::LoadConfigs @ 0x41E388`
        # 在本版镜像里从不执行）。而"某个加载器入口没解析到"和"喂进去了但没生效"在旧读数里
        # **长得一模一样** ⇒ 没有这六格，下一轮只能再猜一遍。
        #
        # 判读表：
        #   * [68] 应当**恒为 0xFFFF**（16 项入口全部解析到）。少哪一位就查下表那个名字 ——
        #     解析失败**不报错、不崩**，只表现为"那个文件的内容不进引擎"；
        #   * [69] = [68] 的补码（bit0..15）+ bit16/bit17/bit18 三个"额外入口"：
        #     bit16 = `ModEntry::ctor`（去掉 ⇒ 8 个要 `ModEntry*` 的项全跳过）、
        #     bit17 = `std::string::assign` 那条 PLT 桩（去掉 ⇒ 真条目的 `+0x48`/`+0x60`
        #     填不上 ⇒ `LoadCustomResources` 一个资源都找不到）、
        #     ★ bit18（批次 409）= `ANM2::Load` 入口（去掉 ⇒ 收尾那一步不调 ⇒
        #     `ModManager+0x368` 的默认模组道具 ANM2 是空的 ⇒ 暂停屏画模组道具时会崩）；
        #   * [70] = 14 项加载器被调了几次（累加）。**正常 ≥ 启用模组数 × 14**；
        #     远大于它 = 重试那几轮把同一条内容喂了多遍（引擎只喂一遍）；
        #   * [71] = `EntityConfig::PostLoadMods()` 调了几次 —— **正常 = 1**（引擎在循环外调一次；
        #     本批用一次性闩锁保证），>1 说明闩锁没生效；
        #   * [72] = `ModEntry::LoadCustomResources()` 调了几次 —— 正常 = 启用模组数；
        #   * [73] = 真 `ModEntry` 构造了几个 —— 正常 = 启用模组数（按下标惰性、只造一次）。
        feed_rows = ('entities2.xml', 'items.xml', 'pocketitems.xml', 'costumes2.xml',
                     'items_metadata.xml', 'wisps.xml', 'locusts.xml', 'recipes.xml',
                     'bombcostumes.xml', 'challenges.xml', 'players.xml', 'sounds.xml',
                     'music.xml', 'nightmares.xml', 'LoadCustomResources', 'PostLoadMods')
        resolved = f[68]
        missing = [feed_rows[i] for i in range(len(feed_rows)) if not (resolved >> i) & 1]
        print(f'  ★ 引擎 16 项入口解析 [68] = 0x{resolved:04X}'
              + ('　← ★ 全 16 项都在（应当如此）' if resolved == 0xFFFF else
                 '　⚠ 缺：' + '、'.join(missing) + '　⇒ 那几项的内容不进引擎（不报错）'))
        extra = []
        if f[69] & (1 << 16):
            extra.append('`ModEntry::ctor`（带 `ModEntry*` 的 8 项全跳过）')
        if f[69] & (1 << 17):
            extra.append('`std::string::assign` 桩（`+0x48`/`+0x60` 填不上 ⇒ 模组资源找不到）')
        if f[69] & (1 << 18):
            extra.append('`ANM2::Load`（收尾那一步不调 ⇒ 默认模组道具 ANM2 空 ⇒ 暂停屏画模组道具会崩）')
        print(f'  解析失败位图 [69] = 0x{f[69]:05X}'
              + ('　← ★ 一条都不缺' if f[69] == 0 else '　⚠ ' + '；'.join(extra) if extra
                 else '　⚠ 见表内位号'))
        print(f'  14 项加载器调用 [70] = {f[70]} 次｜`LoadCustomResources` [72] = {f[72]} 次'
              f'｜真 `ModEntry` 构造 [73] = {f[73]} 个')
        print('  `EntityConfig::PostLoadMods`（所有模组喂完之后收尾）[71] = ' + str(f[71])
              + ('　← ★ 正常（只调一次）' if f[71] == 1 else
                 ('　⚠ 0 ⇒ 还没轮到最后一次尝试，或那一项没解析到' if f[71] == 0 else
                  '　⚠ >1 ⇒ 一次性闩锁没生效（收尾跑了多遍）')))
        # ★ 批次 409：引擎 `ModManager::LoadConfigs` 尾部那一步（默认模组道具 ANM2）。
        if len(f) >= 75:
            print('  ★ 默认模组道具 ANM2（`gfx/ui/mod_defaults.anm2` → `ModManager+0x368`）载入 [74] = '
                  + str(f[74])
                  + ('　← ★ 正常（这一步做了；暂停屏画模组道具不会再崩）' if f[74] == 1 else
                     ('　⚠ 0 ⇒ **这一步没做**：暂停屏上出现模组道具（id ≥ 733）时会写 `0x80` 崩'
                      if f[74] == 0 else '　⚠ >1 ⇒ 一次性闩锁没生效（重复载入）')))
    if len(f) >= 27:
        print('  按 PC 规则**本局该禁**成就（查询结果）= '
              + ('★ 是 —— 判据 = 有真实模组处于**启用状态** **且** 妈腿成就未解锁' if f[26]
                 else '否 ⇒ 不锁，成就照常可拿')
              + ('　（★ 本局还挂着闩锁 [45]）' if len(f) >= 46 and f[45] else ''))
    if len(f) >= 26:
        print(f'  挂载点重建中继：跑过 {f[22]} 次｜其中失败 {f[23]} 次'
              + ('（**必须恒 0**）' if f[23] == 0 else '　⚠ 非 0 ⇒ 重建后没能把 Mod 挂载点挂回去'))
        print('  会话挂载服务已发布 = ' + ('★ 是' if f[24] else '⚠ **否** ⇒ 重建之后一个 Mod 挂载点都不会恢复'))
        w = f[25]
        head = bytes((w >> (16 + 8 * i)) & 0xFF for i in range(4))
        print(f'  最后一次 `Font:Load`：引擎接受 = {"★ 是" if w & 1 else "⚠ **否**"}'
              f'｜干净挂载相对名 = {"是" if (w >> 1) & 1 else "否"}'
              f'｜路径长 {(w >> 8) & 0xFF}｜前 4 字节 {head!r}'
              + ('　← 0 就是"字体没装上"，接着 EID 每次画字都会报错' if not (w & 1) else ''))
    else:
        print('  （[22]..[25] 这四格是 2026-09-23 后加的，本次读数没读到 ⇒ 说明卡上那份还是旧构建）')


def words_to_bytes(words: list[int]) -> bytes:
    return b''.join(v.to_bytes(8, 'little') for v in words)


#: 原生模组页探针的失败码（探针里的 `kFailure*` 常量，**只在探针构建**里有意义）。
NATIVE_MODS_FAILURES = {
    0: '没有失败',
    1: '输入跳板拿不到',
    2: '游戏模块没找到',
    3: '`SetState` 入口守卫不符',
    4: '`g_MenuManager` 为空',
    5: '`Menu_Mods` 入口守卫不符',
    6: '`Menu_Mods::Render` 入口守卫不符',
}
#: 手动 `Init` 的结果（探针里的 `kInit*` 常量）。
NATIVE_MODS_INIT_RESULTS = {
    0: '还没试',
    1: '成功',
    2: '入口守卫不符',
    3: '`g_MenuManager` 为空',
    4: '游戏模块没找到',
}
#: `MenuManager::eState`（静态表：`Update` 的分发表 0..15，逐格对得上具体页面）。
NATIVE_MODS_STATES = {
    0: '（空，走默认分支）', 1: 'Menu_Title', 2: 'Menu_Save', 3: 'Menu_Game',
    4: 'Menu_DailyChallenge', 5: 'Menu_Character', 6: 'Menu_SpecialSeed',
    7: 'Menu_Challenge', 8: 'Menu_Collection', 9: 'Menu_Stats', 10: 'Menu_Options',
    11: 'Menu_ControllerSelect', 12: 'Menu_KeyConfig', 13: 'Menu_Cutscenes',
    14: 'Menu_Bestiary', 15: 'Menu_Custom_Challenge',
}


#: 模组数据容器的记录格式（`ModPersistence::detail::RecordAt`）：24 字节头
#: 命名空间(u64) + 键(u64) + 类型(u8@16) + 值长度(u32@20)，随后是值本身。
MOD_DATA_RECORD_HEADER = 24


def decode_mod_data_records(raw: bytes) -> list[dict]:
    """把模组数据容器的 payload 切成一条条记录（走不通就停，绝不猜）。"""
    records = []
    offset = 0
    while offset + MOD_DATA_RECORD_HEADER <= len(raw):
        header = raw[offset:offset + MOD_DATA_RECORD_HEADER]
        length = int.from_bytes(header[20:24], 'little')
        if length == 0 or offset + MOD_DATA_RECORD_HEADER + length > len(raw):
            break
        value = raw[offset + MOD_DATA_RECORD_HEADER:offset + MOD_DATA_RECORD_HEADER + length]
        records.append({
            'namespace': int.from_bytes(header[0:8], 'little'),
            'key': int.from_bytes(header[8:16], 'little'),
            'type': header[16],
            'value': value,
        })
        offset += MOD_DATA_RECORD_HEADER + length
    return records


def printable_text(value: bytes) -> str | None:
    """值是可打印文本才返回，否则 None（二进制不硬解码）。

    **2026-09-18 修**：原版只认纯 ASCII，于是探针报告里只要出现一个中文字符（我们自己的
    跳过原因就是中文），整条就被判成"二进制"、什么都不打 —— 真机上那次就白读了一趟。
    现在按 UTF-8 解，解不出来或含控制字符才算二进制。
    """
    if not value:
        return None
    try:
        text = value.decode('utf-8')
    except UnicodeDecodeError:
        return None
    if text.isprintable() or all(ch in '\n\r\t' or ch.isprintable() for ch in text):
        return text
    return None


def hook_name(slot: int) -> str:
    """`FirstFailureSlot` 是"序号+1"；越界就说明这个读数本身不可信，不要拿它去索引数组。"""
    return HOOK_NAMES[slot - 1] if 1 <= slot <= len(HOOK_NAMES) else f'越界({slot})'


def describe_runtime_address(address: int, base: int) -> str:
    """把一个**运行时绝对地址**讲成 `（模块内偏移 0x…，落在 <符号>+0x…）`。

    为什么需要它：异常抛出位置（`ThrowForensics.lastThrowFrom`）里存的是运行时绝对地址，
    它每次启动都随 ASLR 变（拿两次读数的地址直接比毫无意义）；减去**运行时模块基址**才得到
    稳定的"模块内偏移"，再拿 `runtime.elf` 的符号表反查，就能当场说出"是哪个函数抛的" ——
    比丢给用户一串十六进制、让他自己去查友好得多。ELF 不在（或被 strip）时**只给偏移、不猜**。
    """
    offset = address - base
    text = f'（模块内偏移 0x{offset:x}'
    try:
        import elf_syms  # 同目录的极简 ELF 解析器（只依赖标准库）
        elf = ROOT / DEFAULT_ELF
        if elf.exists():
            symbols = elf_syms.load_symbols(elf.read_bytes())
            hit = None
            for name, (value, size) in symbols.items():
                if size and value <= offset < value + size:   # 取"最内层"（起始地址最大的那个）
                    if hit is None or value > hit[1]:
                        hit = (name, value)
            if hit is not None:
                text += f'，落在 {hit[0]}+0x{offset - hit[1]:x}'
    except Exception:  # 反查只是锦上添花，失败不该让整份读数崩掉（读数本身还有别的用）
        pass
    return text + '）'


def report(values: dict[str, list[int]], base: int, game_base: int, plugin_base: int) -> None:
    print()
    print('=== 启动状态机（TestRunObserver：游戏主循环那条线程每次启动只走一遍）===')
    #: ★ `first_u32`：`g_sequence` 是 4 字节的 `uint32`（`nm` 实测 size=4），直接 `first(...)`
    #: 会把**隔壁那个全局**取进高 32 位 —— 与 `first_u32` 文档里 `mod_engine_stage`
    #: "真值 2 被印成 4294967298"是同一形状。2026-09-28 批次 192 新加的门禁
    #: （`test_elf_syms.py::U32ReadMaskingTests`）把这一处扫了出来 —— 它此前一直没被发现。
    seq = first_u32(values, 'g_sequence')
    detail_word = first(values, 'g_stateDetail')
    state = detail_word & 0xFFFFFFFF
    detail = detail_word >> 32
    state_name = TEST_RUN_STATES[state] if state < len(TEST_RUN_STATES) else f'未知({state})'
    print(f'  sequence = {seq}（走过 {seq} 步）')
    print(f'  最后一步 = {state} = {state_name}，detail = {detail}')
    if state_name == 'ManifestInstallReturned':
        print(f'    ⇒ 清单安装这一步**走过了**，detail = {detail} = {decode_failure_detail(detail)}')
        if detail == 1:
            print('       （1 = FileBindingMismatch：挂点/文件校验没过 ⇒ 看下面的挂点报告）')
    elif state_name in ('ManifestInstallEntered', 'LuaInitializeEntered'):
        print('    ⇒ 卡在这一步**没返回** ⇒ 不是"校验失败"，是这一步本身没走完。')
    elif state == 5:
        print('    ⇒ 只走到"模块扫描返回"，**清单安装那一步根本没进入**。')

    print()
    print('=== 清单安装为什么失败（2026-09-14 夜间新增的诊断）===')
    mstate = first(values, 'g_DefaultManifestState') & 0xFFFFFFFF
    print(f'  g_DefaultManifestState = {mstate} = '
          + (MANIFEST_STATES[mstate] if mstate < len(MANIFEST_STATES) else '未知'))
    step = first(values, 'g_DefaultManifestFailureDetail') & 0xFFFFFFFF
    print(f'  清单/加载结果字 = {step} = {decode_failure_detail(step)}')
    word = first(values, 'g_DefaultManifestFailureWord') & 0xFFFFFFFF
    if word:
        print(f'  诊断字 [11] = 0x{word:08x}：步骤 {word & 0xFF}、原因 {(word >> 8) & 0xFF}、'
              f'读到的文件大小 {(word >> 16) & 0xFFFFFFFF} 字节')
    else:
        print('  诊断字 [11] = 0（没走过加载）')
    # 32 位变量的高 32 位是**相邻的另一个变量**（gdb 一次读 8 字节），必须屏蔽掉再判读。
    results = values.get('hook_results') or []
    results = [v & 0xFFFFFFFF for v in results]
    if step == 5 or word & 0xFF == 5:
        print('    ⇒ 步骤 5 = "纯资源型"：清单挂载成功，但**没有脚本被执行**。两种可能：')
        print('       ① 清单里这个模组**没有 `entry`**；② 清单写了 `entry`，但那个文件在包里**不存在**。')
        print('       下面"清单原文 / 入口脚本"两段就是用来区分这两条的。')

    # 三个"发布口径"的字：装失败也会被发布（`PublishHookInstallReport` 在判失败之前执行），
    # 所以它们能告诉我们"是哪个挂点、什么原因"，即使模组最终没装上。
    installed = first(values, 'g_HookInstallInstalledCount') & 0xFFFFFFFF
    slot = first(values, 'g_HookInstallFailureSlot') & 0xFFFFFFFF
    code = first(values, 'g_HookInstallFailureCode') & 0xFFFFFFFF
    print()
    print('=== 挂点安装报告（PublishHookInstallReport 发布，装失败也会留下）===')
    print(f'  装好的挂点数 = {installed}')
    print(f'  第一个失败挂点 = {slot}（0 = 没有装失败的；否则是挂点序号+1）'
          + (f' ⇒ {hook_name(slot)}' if slot else ''))
    print(f'  入口中继失败码 = {code}（0 = 无失败）')
    if installed == 0 and slot == 0 and code == 0:
        print('    ⇒ 三项全 0 有两种含义：**安装根本没被走到**，或者报告从未被填充'
              '（`InstallProductionHooks` 在模块无效时会清零报告）。'
              '要区分请看上面的启动状态机走到第几步。')
    elif slot:
        print(f'    ⇒ 挂点 `{hook_name(slot)}` 没装上 ⇒ 这就是模组装不上的直接原因。')

    # ★ 2026-09-16 更正：`g_HookInstallResults` 只写了 [0]/[1]/[2]（三个挂点的安装结果），
    # [3]/[4] 是**另一个东西**：`IsaacModRuntime_FillHookJournalWords` 把
    # `g_UpdateCallbackEntries` / `g_RenderCallbackEntries` 填在输出数组的这两个位置。
    # 以前这里把两套东西混着标（读数组却说"回调进入次数"），于是读数永远是 0 —— 而游戏一切正常。
    # 现在回调进入次数**直接读那两个变量**（见下面的 `callback_entries`）。
    legacy = ['ManagerUpdate 入口中继', 'ManagerRender 入口中继', 'PreGetCollectible 中继',
              '（该数组不用）', '（该数组不用）']
    print()
    print('=== 旧安装器诊断数组 g_HookInstallResults[0..4]（线格式，供交叉核对）===')
    for i, name in enumerate(legacy):
        v = results[i] if i < len(results) else None
        if v is None:
            print(f'  [{i}] {name:22} 读不到')
        elif i < 3:
            print(f'  [{i}] {name:22} = {v} = {LEGACY_HOOK_CODES.get(v, "未知")}')
        else:
            print(f'  [{i}] {name:22} = {v}')
    # 读不到就明说"读不到"，**不许**把"没读到"显示成 0 —— 两者含义完全相反，
    # 而这一类混淆在本项目已经造成过误判（2026-09-16：数组里的 [3]/[4] 被当成计数器，永远是 0）。
    for key, label, zero_hint in (
            ('update_entries', 'update 回调进入次数', '  ⇒ 一次都没进：回调没跑起来（或还没到派发条件）'),
            ('render_entries', 'render 回调进入次数', '  ⇒ 一次都没进'),
            ('callback_error', '回调里出过 Lua 错误', '  ⇒ 无')):
        if key in values:
            count = first(values, key) & 0xFFFFFFFF
            print(f'  {label} = {count}'
                  + ('  ⇒ 确实在派发 ✓' if count else zero_hint))
        else:
            print(f'  {label} = （读不到：本次读数没有取这个地址）')
    if 'self_journal' in values:
        service_state = first(values, 'self_journal') & 0xFFFFFFFF
        records = first(values, 'self_journal_records') & 0xFFFFFFFF
        marker = first(values, 'self_journal_marker') & 0xFFFFFFFF
        state_text = {0: '没试过', 1: 'sm+fs 会话已就绪', 2: '服务初始化失败'}.get(
            service_state, f'未知({service_state})')
        print(f'  模块自己的 SD 写入通道（自 journal）：会话状态 = {state_text}、'
              f'记录数 = {records}、最后标记 = {marker}')
        print('    ⇒ 会话已就绪即说明"我们模块自己起得来 sm/fs、能碰 SD 卡"'
              '（记录数 > 0 则还证明**真的写进去过**）')
    present_state = first(values, 'g_RenderPresentRelayState') & 0xFFFFFFFF
    print(f'  Present 前派发点（GOT 槽方案）状态 = {present_state} = '
          f'{PRESENT_RELAY_CODES.get(present_state, "未知")}')

    # ★ 2026-10-05 新增：`MC_POST_RENDER` 这条命脉**逐环**量出来（"本会话一次都没派发"时看这里）。
    #   为什么必须分层：`present_state == Success` 会把 `Manager::Render` 入口中继那边的**回退**
    #   关掉（`hook_manager.cpp` 的 `if (!IsRenderPresentRelayInstalled())`）⇒ 只剩这一条路，
    #   它任何一环断了都是**静默归零**。三档结论互斥、一眼可判：
    #     entries == 0            ⇒ 桩那条路压根没跑到（GOT 槽/调用方过滤/桩那一层）
    #     entries > 0 且 闸门开   ⇒ 前两环都好、问题在下游（会话/登记）
    #     entries > 0 且 闸门关   ⇒ 渲染族独有的那道闸门从没开（更新族走另一套门，所以它正常）
    if 'render_present_relay_entries' in values:
        relay_entries = first(values, 'render_present_relay_entries') & 0xFFFFFFFF
        gate = first(values, 'default_callback_gate') & 0xFFFFFFFF
        owner_slot = first(values, 'lua_game_owner_slot')
        paused_thunk = first(values, 'lua_game_ispaused_thunk')
        music_fn = first(values, 'music_get_current_id')
        frame_manager = first(values, 'render_frame_manager')
        print('  ── 每帧渲染回调（`MC_POST_RENDER`）逐环判据'
              '（`present_state = Success` 时这条路是**唯一**的）──')
        print(f'    ① `Present` 前那个派发函数**被进了几次**   = {relay_entries}'
              '（0 = 这条路没跑到；>0 = 跑到了、看下一环）')
        print(f'    ② 默认回调闸门 g_DefaultCallbackGate      = 0x{gate:08x}'
              f'（最低位 = {gate & 1}；**锁存**：开过就一直开）')
        print(f'    ③ 闸门三个输入：Game owner 槽 = 0x{owner_slot:012x}'
              f'｜IsPaused thunk = 0x{paused_thunk:012x}｜GetCurrentMusicID = 0x{music_fn:012x}')
        if 'last_is_paused' in values:
            last_paused = first(values, 'last_is_paused') & 0xFFFFFFFF
            print(f'    ③b ★ `Game:IsPaused()` **最后一次返回** = {last_paused}'
                  f'（0 = false、1 = true；★ MCM 的开菜单闸门是 `if ControlsEnabled and not isPaused` '
                  f'⇒ 这一格是 1 的话，MCM 会**整段不跑**：不出菜单、也不响、'
                  f'并且**不会去问** `IsButtonTriggered(13,…)`）')
        print(f'    ④ 本帧 Manager*（g_RenderFrameManager）    = 0x{frame_manager:012x}')
        if 'music_resolve_failure' in values:
            resolve_fail = first(values, 'music_resolve_failure') & 0xFFFFFFFF
            deepest = first(values, 'deepest_owner_observation') & 0xFFFFFFFF
            print(f'    ⑤ 音乐解析失败码 = {resolve_fail}'
                  '（0 = 解析成功；2 = `manager+0x36068` 不可读；3 = 方法绑定为 0；4 = 16 字节指纹不符）'
                  f'｜owner 链最深观察 = {deepest}')
        if relay_entries == 0:
            print('    ⇒ ① 为 0 ⇒ 问题在"**GOT 槽 → 桩 → 调用方过滤**"那一层'
                  '（槽值/过滤值对不上，或那处调用没经过槽）')
        elif gate & 1:
            print('    ⇒ ① > 0 且闸门已开 ⇒ 前两环都好，问题在更下游（会话/登记）')
        else:
            print('    ★ ① > 0、但**闸门从没打开** ⇒ 渲染族（`*_RENDER` / `MC_POST_RENDER`）'
                  '的回调全都不派发；更新族走的是**另一套门**，所以 `MC_POST_UPDATE` 正常 '
                  '—— 与"只卡渲染族、不崩不报错"完全吻合')
            if owner_slot == 0 or paused_thunk == 0 or music_fn == 0:
                print('      ⚠ ③ 里有**为 0** 的输入 ⇒ 那是"守卫不符 ⇒ 字段被留 0"'
                      '（那一族是可选项，失败不报错、不记为挂点失败）')

    # 卡上开关：**先读它再解释任何"开关好像没生效"** —— 掩码为 0 且通道正常时，
    # 说明卡上确实没有开关文件（配置就是"什么都没跳过"），而不是"开关机制坏了"。
    if 'g_CardSwitchMask' in values:
        mask = first(values, 'g_CardSwitchMask') & 0xFFFFFFFF
        channel = first(values, 'g_CardSwitchChannel') & 0xFFFFFFFF
        found = [name for index, name in enumerate(CARD_SWITCH_NAMES) if mask & (1 << index)]
        channel_text = ('查询正常' if channel & 1 else '一次都没查成功')
        if channel & 2:
            channel_text += '；有查询失败（通道部分不可用）'
        if channel & 4:
            channel_text += '；★ 曾在**非游戏线程**上被要求探测 ⇒ 已拒绝执行（这条路径会崩游戏，见实现注释）'
        print(f'  卡上开关：掩码 = 0x{mask:x}、通道 = {channel_text}')
        print(f'    卡上确实存在的开关 = {found if found else "（一个都没有）"}')
        print('    （掩码为 0 且通道正常 ⇒ 就是"什么都没跳过"的正常配置；'
              '通道报失败 ⇒ 读卡这条路有问题，开关读数的结论一律不成立）')

    print()
    print('=== Lua 侧：模组到底跑到哪一步 ===')
    registered = first(values, 'g_ModRegistered') & 0xFF
    print(f'  g_ModRegistered = {registered}'
          + ('  ⇒ 模组登记成功，Lua 真的跑起来了 ✓' if registered else
             '  ⇒ 模组没登记（Lua 从未跑到登记那一步）'))
    if 'g_ModRegisteredCount' in values:
        # 多模组加载（2026-09-16）：个数应当等于清单里 `enabled: true` 的条数。
        # 只有 1 而清单里明明有 2 ⇒ 第二个 Mod 的脚本没跑到 `RegisterMod`（去看它的错误文本）。
        print(f'  g_ModRegisteredCount = {first(values, "g_ModRegisteredCount") & 0xFFFFFFFF}'
              '  ⇒ 登记成功的 Mod 个数（清单里几个 enabled 就该是几）')
    if 'mod_data_descriptor' in values and len(values['mod_data_descriptor']) >= 5:
        values['mod_data_tail'] = values['mod_data_descriptor'][2:5]
    if 'mod_data_tail' in values and len(values['mod_data_tail']) >= 3:
        # 模组数据容器（存档分区）：这三条一起看 —— 存在与否、第几代、多大。
        tail = values['mod_data_tail']
        length = tail[0] & 0xFFFFFFFFFFFFFFFF
        generation = tail[1] & 0xFFFFFFFFFFFFFFFF
        flags = tail[2] & 0xFFFFFFFF
        loaded = flags & 0xFF
        exists = (flags >> 8) & 0xFF
        print(f'  模组数据容器（存档分区 isaac-mod-data.bin）：'
              f'{"已加载" if loaded else "未加载"}、'
              f'{"存档里有" if exists else "存档里没有"}、'
              f'generation={generation}、payload={length} 字节')
        print('    ⇒ generation只在内容变化时递增；重启后不变不能证明未落盘。')
        if length > 8192:
            print('    记录读取窗口为8192字节，超出部分缺失，不能据此判断记录不存在。')
    # ⚠️ `payload_sources` 原来只在"读到了 API 序列那一段"时才被赋值，而**一次读数里只要有一个
    # 地址读不到（例如 `--read` 指到未映射区），gdb 那批输出就会缺后面几段** ⇒ 后面用到它时
    # `UnboundLocalError`，**整份报告崩掉**（2026-09-20 实测）。所以在这里先置空表：
    # "读不到"应当表现为"少一段"，不是"整份报告看不到"。
    payload_sources: list[str] = [key for key in values if key == 'mod_data_head' or key.startswith('extra_')]
    # 模组数据的**记录表**（探针把报告写在 `Mod:SaveData` 里就从这儿读回来）。
    # 除了固定读的那一段，`--read` 指定的区域里也一起找 —— 报告超过固定窗口时（2026-09-18
    # 真机就发生了：payload 长到 1060 字节、探针那条记录被挤出 1 KiB 窗口），
    # 手工多读一段就能把它捞回来，不必改代码重挂。
    if 'api_sequence' in values:
        raw = words_to_bytes(values['api_sequence'])
        main_mask = int.from_bytes(raw[0:8], 'little')
        secondary_mask = int.from_bytes(raw[8:16], 'little')
        draw_calls = int.from_bytes(raw[16:20], 'little')
        item_found = int.from_bytes(raw[24:28], 'little')
        last_primary = int.from_bytes(raw[36:40], 'little')
        known = {16: 'Isaac.GetPlayer', 17: 'Isaac.GetItemConfig', 18: 'Isaac.FindInRadius',
                 19: 'Isaac.FindByType', 20: 'Isaac.CountEnemies', 21: 'Isaac.CountBosses',
                 22: 'Isaac.CountEntities', 23: 'Isaac.RunCallbackWithParam',
                 32: 'Font:DrawString', 33: 'Font:DrawStringScaled', 34: 'Font:DrawStringUTF8',
                 35: 'Font:DrawStringScaledUTF8', 48: 'Sprite:Render', 49: 'Sprite:RenderLayer',
                 50: 'Sprite:GetTexel'}
        print('  === API 调用序列（"哪些 API 真被调用过"的直接证据）===')
        fired = [f'bit{bit}={known.get(bit, "（见位表）")}' for bit in range(64)
                 if main_mask & (1 << bit)]
        print(f'    主掩码 = 0x{main_mask:016x}'
              + (f'  ⇒ {"; ".join(fired)}' if fired else '  ⇒ 一个都没被调用过'))
        print(f'    次掩码 = 0x{secondary_mask:016x}；画字调用 = {draw_calls} 次；'
              f'ItemConfig 命中 = {item_found} 次；最后一次主掩码位 = '
              + ('（还没调用过）' if last_primary == 0xFFFFFFFF else str(last_primary)))
        for bit in (48, 49, 50):
            hit = bool(main_mask & (1 << bit))
            print(f'    Sprite bit{bit}（{known[bit]}）：'
                  + ('**被调用过** ✓' if hit else '从未被调用'))
        payload_sources = [key for key in values if key == 'mod_data_head' or key.startswith('extra_')]
    if 'native_fallback' in values:
        raw = words_to_bytes(values['native_fallback'])
        fallback_count = int.from_bytes(raw[0:4], 'little')
        fallback_last = int.from_bytes(raw[4:8], 'little')
        print('  === 原生状态回退（批次 250：读不到引擎状态时给"该类型下的默认值"而不是抛错）===')
        print(f'    回退次数 = {fallback_count}；最后一次 = 接口 #{fallback_last}')
        print('    口径：0 次 ⇒ 地址链正常（这些接口在本次会话里都读到了真值）；'
              '>0 ⇒ 编号见 runtime/src/interfaces/lua/native_state_fallback.hpp 的 NativeFallbackApi')
    if 'g_IsaacApiRowCalls' in values:
        row_calls = first(values, 'g_IsaacApiRowCalls') & 0xFFFFFFFF
        engine_calls = first(values, 'g_IsaacEngineRowCalls') & 0xFFFFFFFF
        last_id = first(values, 'g_IsaacApiRowLastCallId') & 0xFFFFFFFF
        last_kind = first(values, 'g_IsaacApiRowLastCallKind') & 0xFFFFFFFF
        rej_receiver = first(values, 'g_IsaacEngineRowRejectReceiver') & 0xFFFFFFFF
        rej_offset = first(values, 'g_IsaacEngineRowRejectOffset') & 0xFFFFFFFF
        rej_entry = first(values, 'g_IsaacEngineRowRejectEntry') & 0xFFFFFFFF
        rej_guard = first(values, 'g_IsaacEngineRowRejectGuard') & 0xFFFFFFFF
        rej_id = first(values, 'g_IsaacEngineRowLastRejectId') & 0xFFFFFFFF
        rej_reason = first(values, 'g_IsaacEngineRowLastRejectReason') & 0xFFFFFFFF
        kind_name = {1: '字段行', 2: '引擎方法行'}.get(last_kind, '（还没调用过）')
        reason_name = {0: '（没发生过）', 1: '接收者解析失败', 2: '偏移拿不到',
                       3: '入口 4 字节指纹不匹配',
                       4: '参数校验挡下（无效的 null 服装编号）'}.get(rej_reason,
                                                                    f'未知({rej_reason})')
        print('  === 数据行 API 的调用 / 静默降级（批次 069：不用探针也能回答"调到了没"）===')
        print(f'    数据行被调用 = {row_calls} 次（其中引擎方法行 {engine_calls} 次）')
        print(f'    最后一次调用 = {api_name(last_id)}（{kind_name}）')
        print(f'    引擎方法行被降级 = {rej_receiver + rej_offset + rej_entry + rej_guard} 次'
              f'（接收者 {rej_receiver} / 偏移 {rej_offset} / 入口指纹 {rej_entry} /'
              f' 参数校验挡下 {rej_guard}）')
        print(f'    最后一次降级 = {api_name(rej_id)}：{reason_name}')
        if row_calls == 0:
            print('    ⇒ ★ 一条数据行 API 都没被调用过 ⇒ 问题在"模组没走到那里"，'
                  '不是"我们没实现好"。')
        elif engine_calls and rej_receiver == engine_calls:
            print('    ⇒ ★ 引擎方法行**每一次**都栽在"接收者拿不到"：我们这套 API 在真机上'
                  '等于没生效（先查句柄与回调上下文，不要怀疑偏移表）。')
        elif rej_entry:
            print('    ⇒ ★ 有"入口指纹不匹配" ⇒ 至少有一条引擎方法的偏移/指纹是错的，'
                  '按上面最后一条降级的名字去核对。')
        # ---- 批次 141：服装查表 / 加摘服装的现场 ----
        if 'g_IsaacCostumePathCalls' in values:
            cp_calls = first(values, 'g_IsaacCostumePathCalls') & 0xFFFFFFFF
            cp_hits = first(values, 'g_IsaacCostumePathHits') & 0xFFFFFFFF
            cp_misses = first(values, 'g_IsaacCostumePathMisses') & 0xFFFFFFFF
            cp_last = first(values, 'g_IsaacCostumePathLastId') & 0xFFFFFFFF
            cp_null = first(values, 'g_IsaacCostumePathNullCount') & 0xFFFFFFFF
            nc_last = first(values, 'g_IsaacNullCostumeLastRequestedId') & 0xFFFFFFFF
            nc_unknown = first(values, 'g_IsaacNullCostumeGuardUnknown') & 0xFFFFFFFF
            cp_last_text = '（一次都没命中过）' if cp_last == 0xFFFFFFFF else str(cp_last)
            cp_null_text = '读不到（不是"容器空"）' if cp_null == 0xFFFFFFFF else str(cp_null)
            # 按 int32 解：`-1` 就是 `0xFFFFFFFF`，与"一次都没收到过"同一个位模式 ⇒
            # 靠"加/摘服装那一行被调用过没有"（`g_IsaacEngineRowCalls` 与挡下次数）区分，
            # 不要只看这一格。
            nc_text = str(nc_last - 0x100000000 if nc_last >= 0x80000000 else nc_last)
            print('  === 服装查表 / 加摘临时服装（批次 141：跳舞模组"崩在空指针"的两半）===')
            print(f'    `Isaac.GetCostumeIdByPath` 被调 {cp_calls} 次：'
                  f'命中 {cp_hits} 次、没命中 {cp_misses} 次')
            print(f'    最后一次命中的编号 = {cp_last_text}')
            print(f'    最后一次查表时 null 服装容器条目数 = {cp_null_text}')
            print(f'    "加/摘临时服装"最后一次收到的编号 = {nc_text}'
                  f'（0x{nc_last:08X}）；编号判定不了而放行 {nc_unknown} 次')
            if cp_calls and cp_hits == 0:
                print('    ⇒ ★ `GetCostumeIdByPath` **一次都没命中**：先看上面那行"容器条目数" ——'
                      '若条目数正常，说明容器里**没有模组那 23 条路径**（资源/加载时机问题，'
                      '不是比对口径问题）；若不正常，说明那条链当时读不到。')
            elif cp_hits:
                print('    ⇒ 命中过：核对"最后命中的编号"与"加/摘服装收到的编号"是否同一个 —— '
                      '相同却仍有无效编号进来，说明是**别的调用点**给的。')
            if rej_guard:
                print(f'    ⇒ ★ 兜底挡下 {rej_guard} 次（编号无效，没往引擎里调）—— '
                      '这是**保险生效**，不是功能生效：跳舞服装仍然没有穿上。')
            if nc_unknown:
                print(f'    ⇒ ★ 有 {nc_unknown} 次"编号有效性判定不了"（我们的 `ItemConfig` 链'
                      '当时读不到）⇒ 那些次是**照原样调进去的**，先查我们自己的链。')
        # ---- 批次 154：`Music:Play` 的编号保险（真机崩在 `Music::Play + 0x68` 之后加的）----
        if 'g_MusicPlayGuardBlocked' in values:
            mp_blocked = first(values, 'g_MusicPlayGuardBlocked') & 0xFFFFFFFF
            print('  === 放歌的编号保险（批次 154：`Music:Play` 收到确认无效的编号就静默挡下）===')
            print(f'    挡下次数 = {mp_blocked}'
                  + ('　← 0 说明没有模组拿越界/负数编号来播（正常）' if mp_blocked == 0 else
                     '　★ 非 0 ⇒ 有模组拿着**无效编号**来放歌，我们挡下了（不挡就是'
                     '`Music::Play + 0x68` 的 Data Abort）；'
                     '先查它为什么会拿到无效编号（多半是 `content/music.xml` 没进引擎）'))
        # ---- 批次 408（2026-10-08）：`SFXManager:Play`（**真调引擎**的尺子）----
        # 在此之前 `Play` 是**空实现**（批次 045 的占位）⇒ 真机上所有模组的音效都是哑的
        # （中文版 MCM"房间不安全"该响 `SOUND_BOSS2INTRO_ERRORBUZZ`，实测一点声音都没有）。
        # 这三问分开回答：模组调了没（calls）/ 我们递进去了没（delivered）/ 参数对不对（last*）/
        # 没递进去卡在哪一步（last_failure）。
        if 'sfx_play_calls' in values:
            def _sfx_f32(key: str) -> float:
                return struct.unpack('<f', struct.pack('<I', first_u32(values, key)))[0]

            sfx_calls = first_u32(values, 'sfx_play_calls')
            sfx_delivered = first_u32(values, 'sfx_play_delivered')
            sfx_fail = first_u32(values, 'sfx_play_last_failure')
            print('  === 音效 `SFXManager:Play`（批次 408：从空实现改成 **真调引擎**）===')
            print(f'    模组调用（形状合法）= {sfx_calls}；其中**真的递进引擎** = {sfx_delivered}')
            if sfx_delivered:
                print('    最近一次递进去的实参：'
                      f'id = {first_u32(values, "sfx_play_last_id")}、'
                      f'volume = {_sfx_f32("sfx_play_last_volume"):.4g}、'
                      f'frameDelay = {first_u32(values, "sfx_play_last_frame_delay")}、'
                      f'loop = {first_u32(values, "sfx_play_last_loop")}、'
                      f'pitch = {_sfx_f32("sfx_play_last_pitch"):.4g}、'
                      f'pan = {_sfx_f32("sfx_play_last_pan"):.4g}')
            _sfx_fail_names = {0: '没失败过', 1: '不在托管回调派发里', 2: 'Manager 或音效子对象读不到',
                               3: '方法地址缺失（`EngineOffsetAddress` 返回 0）', 4: '入口 16 字节指纹不符'}
            print(f'    最近一次**没递进去**的失败码 = {sfx_fail}'
                  f'（{_sfx_fail_names.get(sfx_fail, "未知")}）')
            if sfx_calls == 0 and sfx_delivered == 0:
                print('      ⇒ 两格都是 0：要么没有模组调 `SFXManager:Play`，要么这份构建没带探针')
            elif sfx_delivered == 0:
                print('      ★ 调了却一次都没递进去 ⇒ 按上面的失败码定位'
                      '（1/2 是环境、3 是基址、4 是指纹）')
        # ---- 批次 144：引擎配置文件的真相（只读 options.ini 的 EnableMods）----
        if 'g_OptionsProbeExists' in values:
            op_exists = first(values, 'g_OptionsProbeExists') & 0xFFFFFFFF
            op_status = first(values, 'g_OptionsProbeStatus') & 0xFFFFFFFF
            op_read = first(values, 'g_OptionsProbeReadStatus') & 0xFFFFFFFF
            op_size = first(values, 'g_OptionsProbeSize') & 0xFFFFFFFF
            op_enable = first(values, 'g_OptionsProbeEnableMods') & 0xFFFFFFFF
            op_low = first(values, 'g_OptionsProbeHeadLow') & 0xFFFFFFFF
            op_high = first(values, 'g_OptionsProbeHeadHigh') & 0xFFFFFFFF
            head = (op_high << 32) | op_low
            head_text = head.to_bytes(8, 'little').decode('ascii', 'replace') if head else '（空）'
            enable_text = '文件里没有这一行' if op_enable == 0xFFFFFFFF else str(op_enable)
            print('  === 引擎配置文件的真相（批次 144：只读 options.ini 的 EnableMods）===')
            print(f'    `save:/options.ini` 存在 = {op_exists}（Exists 码 {op_status}）；'
                  f'读取码 {op_read}、读回 {op_size} 字节；头 8 字节 = {head_text!r}')
            print(f'    ★ EnableMods = {enable_text}')
            gate_restores = first(values, 'g_ModsGateRestores') & 0xFFFFFFFF
            print(f'    引擎那个总闸被我们纠正回来的次数 = {gate_restores}'
                  '（>0 ⇒ 引擎自带的模组页确实翻转了它，批次 145 的修法在生效）')
            if op_exists and op_status == 0 and op_read == 0:
                if op_enable == 0:
                    print('    ⇒ ★★ **根因坐实**：文件里 EnableMods=0 ⇒ 引擎启动时总闸就是 0 ⇒ 它扫目录时'
                          '把每条模组都标成未启用 ⇒ content 不加载。**按 PC 逻辑的修法就是把这一行改成 1**。')
                elif op_enable == 1:
                    print('    ⇒ 文件里就是 1 ⇒ "总闸是 0"的推断要换来源（查是谁在运行时把它写回 0）。')
                else:
                    print('    ⇒ 文件里没有 EnableMods 这一行（引擎默认 1）⇒ 还要查是谁在运行时写成 0。')
            elif op_read != 0:
                print(f'    ⇒ 读失败（码 {op_read}）⇒ 路径/时机不对（存档挂载点或文件名）。')
    if 'g_IsaacRoomIdxCalls' in values:
        idx_calls = first(values, 'g_IsaacRoomIdxCalls') & 0xFFFFFFFF
        if idx_calls:
            idx_empty = first(values, 'g_IsaacRoomIdxEmpty') & 0xFFFFFFFF
            rejected = first(values, 'g_IsaacRoomIdxRejectedFootprint') & 0xFFFFFFFF
            via_map = first(values, 'g_IsaacRoomIdxEngineMapUsed') & 0xFFFFFFFF
            requested = first(values, 'g_IsaacRoomIdxLastRequest') & 0xFFFFFFFF
            grid = first(values, 'g_IsaacRoomIdxLastResolvedGrid') & 0xFFFFFFFF
            safe = first(values, 'g_IsaacRoomIdxLastResolvedSafe') & 0xFFFFFFFF
            listed = first(values, 'g_IsaacRoomIdxLastResolvedList') & 0xFFFFFFFF
            print('  === 房间描述符解析现场（批次 074：小地图要靠它）===')
            print(f'    解析 {idx_calls} 次：空句柄 {idx_empty} 次、'
                  f'被足迹校验挡掉 {rejected} 次、靠引擎映射表命中 {via_map} 次')
            print(f'    最后一次请求格子 = {requested}，解析结果 GridIndex={grid}、'
                  f'SafeGridIndex={safe}、ListIndex={listed}')
            slot_rejected = first(values, 'g_IsaacRoomIdxMapSlotRejected') & 0xFFFFFFFF
            reject_request = first(values, 'g_IsaacRoomIdxLastRejectRequest') & 0xFFFFFFFF
            reject_anchor = first(values, 'g_IsaacRoomIdxLastRejectAnchor') & 0xFFFFFFFF
            delta_bias = first(values, 'g_IsaacRoomIdxLastRejectDeltaBias') & 0xFFFFFFFF
            delta = (delta_bias - 64) if delta_bias != 0xFFFFFFFF else None
            accepted = first(values, 'g_IsaacRoomIdxAccepted') & 0xFFFFFFFF
            negative = first(values, 'g_IsaacRoomIdxSlotNegative') & 0xFFFFFFFF
            unallocated = first(values, 'g_IsaacRoomIdxUnallocatedAnchor') & 0xFFFFFFFF
            beyond = first(values, 'g_IsaacRoomIdxSlotBeyondCount') & 0xFFFFFFFF
            acc_req = first(values, 'g_IsaacRoomIdxLastAcceptedRequest') & 0xFFFFFFFF
            acc_slot = first(values, 'g_IsaacRoomIdxLastAcceptedSlot') & 0xFFFFFFFF
            acc_anchor = first(values, 'g_IsaacRoomIdxLastAcceptedAnchor') & 0xFFFFFFFF
            acc_safe = first(values, 'g_IsaacRoomIdxLastAcceptedSafe') & 0xFFFFFFFF
            print(f'    映射表命中分类（批次 076）：接受 {accepted}、槽号为负 {negative}、'
                  f'锚点未分配 {unallocated}、槽位>元素个数 {beyond}（**只记账、不再否决**）')
            print(f'    最后一次接受：请求格子 {acc_req}、槽号 {acc_slot}、锚点 {acc_anchor}、'
                  f'该房间 SafeGridIndex {acc_safe}')
            print(f'    （旧口径）给了有效槽位但被前两道校验挡掉 = {slot_rejected} 次')
            native_calls = first(values, 'g_IsaacRoomIdxNativeCalls') & 0xFFFFFFFF
            native_fb = first(values, 'g_IsaacRoomIdxNativeFallbacks') & 0xFFFFFFFF
            native_idx = first(values, 'g_IsaacRoomIdxNativeLastIndex') & 0xFFFFFFFF
            native_dim = first(values, 'g_IsaacRoomIdxNativeLastDimension') & 0xFFFFFFFF
            print(f'    （批次 077）直接问引擎 {native_calls} 次、回落 {native_fb} 次；'
                  f'最后一次入参 index={native_idx}、dimension={native_dim}')
            if native_calls == 0 and native_fb:
                print('    ⇒ ★ 一次都没问成引擎 ⇒ 入口指纹不匹配或模块基址未发布，'
                      '解析仍走手写那条链（要查偏移/指纹）。')
            if rejected:
                print(f'    最后一次被足迹校验挡掉：请求格子 {reject_request}、'
                      f'那个房间的 +0x00 = {reject_anchor}、差值 = {delta}')
                print('    ⇒ ★ 差值落在白名单（0/±1/±13/±14）之外 ⇒ 要么"多格房间的锚点不在这个'
                      '集合里"，要么**映射表给的是另一个房间**（后者更危险，不能直接放宽）。')
            if idx_empty and not rejected and not via_map:
                print('    ⇒ ★ 空句柄全部来自"扫描没命中"且映射表也没给 ⇒ 引擎映射表那一格'
                      '本身是无效的（过渡期/未分配）。')
    if 'g_IsaacRoomDescDataMisses' in values:
        misses = first(values, 'g_IsaacRoomDescDataMisses') & 0xFFFFFFFF
        if misses:
            grid = first(values, 'g_IsaacRoomDescDataGridIndex') & 0xFFFFFFFF
            safe = first(values, 'g_IsaacRoomDescDataSafeGridIndex') & 0xFFFFFFFF
            listed = first(values, 'g_IsaacRoomDescDataListIndex') & 0xFFFFFFFF
            descriptor = first(values, 'g_IsaacRoomDescDataDescriptorLow') & 0xFFFFFFFF
            print('  === RoomDescriptor.Data 读不到的现场（批次 071）===')
            print(f'    发生了 {misses} 次；最后一次：GridIndex={grid}、SafeGridIndex={safe}、'
                  f'ListIndex={listed}、描述符地址低位=0x{descriptor:08x}')
            if grid == 0xFFFFFFFF:
                print('    ⇒ ★ 这是**未分配槽位**（引擎自己的空描述符）⇒ 问题在"当前房间描述符'
                      '没解析到"，不是"房间没有配置对象"。')
            else:
                print('    ⇒ 槽位是有效的、但 `+0x10` 读出 0 ⇒ 这类房间（贪婪模式一类）'
                      '没有 RoomConfig 对象；我们已按字段全 0 返回（不再给 nil）。')
    # ★ `--read` 读回来的原始字节要**原样**看得见（2026-09-28 批次 193 加的）。
    # 原来这些段只喂给"模组数据记录"解码器：解不出记录就等于**什么都没打印** ——
    # 而调查 hid 共享内存这类"看原始位模式"的场合，要的就是那几个字。
    extra_keys = [key for key in values if key.startswith('extra_')]
    if extra_keys:
        print()
        print('=== 额外读回来的原始字节（`--read`；每行一个 8 字节字，小端）===')
        for key in sorted(extra_keys):
            raw = words_to_bytes(values[key])
            print(f'  {key}（{len(raw)} 字节）')
            for offset in range(0, len(raw), 16):
                chunk = raw[offset:offset + 16]
                hex_pairs = ' '.join(f'{int.from_bytes(chunk[i:i+8], "little"):016x}'
                                     for i in range(0, len(chunk), 8))
                print(f'    +0x{offset:03x}: {hex_pairs}')
    payload_records = {}
    for key in payload_sources:
        for record in decode_mod_data_records(words_to_bytes(values[key])):
            payload_records[(record['namespace'], record['key'])] = record
    if payload_records:
        records = [payload_records[k] for k in sorted(payload_records)]
        print(f'  模组数据记录 {len(records)} 条'
              + (f'（来自 {len(payload_sources)} 段读数：'
                 f'{"、".join(sorted(payload_sources))}）' if records else
                 '（容器里没有记录，或首个记录头不完整）'))
        for record in records:
            text = printable_text(record['value'])
            if text is None:
                print(f'    命名空间 0x{record["namespace"]:016x}、键 0x{record["key"]:016x}、'
                      f'类型 {record["type"]}、{len(record["value"])} 字节（二进制）')
                continue
            first_line = text.splitlines()[0] if text.splitlines() else ''
            print(f'    命名空间 0x{record["namespace"]:016x}、键 0x{record["key"]:016x}、'
                  f'类型 {record["type"]}、{len(record["value"])} 字节文本')
            for line in text.splitlines()[:40]:
                print(f'      | {line}')
            if first_line.startswith('CALLPROBE') or 'CALLPROBE' in text:
                print('      ⇒ ★ 这是**可调用性探针**的报告（见 `dist/callability-probe-*/main.lua`）')
            if first_line.startswith('DIAGSAMPLE') or 'DIAGSAMPLE' in text:
                # 批次 070：运行时自带的菜单模组定期把"第三方模组挂出来的全局"浅表扫一遍，
                # 写进它自己的模组数据。看到这一段就说明**不用再往那个模组里装探针**了。
                print('      ⇒ ★ 这是**诊断伴生采样**（批次 070，运行时自带、不占模组位）：'
                      '上面几行是模组内部状态，`<missing>`/`<error>` 表示那条读不到而不是采样失败。')
    if 'g_RuntimePerfCallbackCalls' in values:
        def u64(key: str) -> int | None:
            # ★ 2026-09-21：这里**必须容忍缺键**。同一段报告也要能读"不是生产包"的那份 ELF
            # （例如探针构建），而 `--gc-sections` 会把"本构建里没人读"的计数器整个丢掉
            # （实测：探针包里没有 `g_RuntimePerfSyscalls`，生产包里有）。
            # 历史口径是缺键报 0；★ 2026-10-09 更正：缺键返回 None，不伪造实测零。
            # **不许抛 KeyError** —— 那会让整次 attach 白烧，
            # 而这台机器一个启动周期只允许几次 attach（`build_requests` 的 docstring 同一条纪律）。
            words = values.get(key)
            if not words:
                print(f'  （{key} 缺失：本次没有有效读数）')
                return None
            return optional_counter(values, key)
        cb_calls, cb_ticks, cb_max = (u64('g_RuntimePerfCallbackCalls'),
                                      u64('g_RuntimePerfCallbackTicks'),
                                      u64('g_RuntimePerfCallbackMaxTicks'))
        syscalls, syscall_ticks = u64('g_RuntimePerfSyscalls'), u64('g_RuntimePerfSyscallTicks')
        tick_cost = first(values, 'g_RuntimePerfTickCostTicks')
        to_us = lambda ticks: ticks / 19.2  # 19.2 tick = 1 µs（Tegra X1 恒 19.2 MHz，代码里用常量、不读频率寄存器）
        print('  === 常驻性能面（批次 084：这一帧到底花在哪）===')
        empty_call = first(values, 'g_RuntimePerfEmptyCallTicks')
        empty_count = first(values, 'g_RuntimePerfEmptyCallCount')
        if empty_call and empty_count:
            per_call = to_us(empty_call) / empty_count
            print(f'    地板基准：一次纯 Lua→C 调用（处理器什么都不做）≈ {per_call:.3f} µs'
                  f'（{empty_count} 次共 {to_us(empty_call) / 1000.0:.1f} ms）'
                  f' —— 接口再优化也不可能低于这条线；它也等于"关掉测量包装能省下的每次开销"')
        if tick_cost:
            print(f'    量具自校准：读一次 cntpct_el0 ≈ {tick_cost} tick = {tick_cost / 19.2:.3f} µs'
                  f'{"" if tick_cost < 100 else "  ⇒ ★ 读数本身不便宜，所有耗时都被它抬高，结论要打折"}')
        if None in (cb_calls, cb_ticks, cb_max):
            print('    托管回调：缺失（次数/累计耗时/最大耗时未取全）')
        elif cb_calls:
            print(f'    托管回调 {cb_calls} 次：合计 {to_us(cb_ticks) / 1000.0:.1f} ms、'
                  f'平均 {to_us(cb_ticks) / cb_calls:.1f} µs、最慢一次 {to_us(cb_max):.0f} µs')
        if syscalls is None or syscall_ticks is None:
            print('    引擎内存查询（svcQueryMemory）：缺失（次数/累计耗时未取全）')
        else:
            print(f'    引擎内存查询（svcQueryMemory）{syscalls} 次：合计 {to_us(syscall_ticks) / 1000.0:.1f} ms'
                  + (f'、平均 {to_us(syscall_ticks) / syscalls:.3f} µs' if syscalls else ''))
        # Syscall 在加载和回调路径都会记账；回调总耗时又已包含回调内的 Syscall。
        print('    内存查询含加载等回调外路径；回调内的查询已包含在回调耗时，不能与回调耗时相加。')
        # 批次 086：按 (事件 id, 属主模组) 分开，回答"贵的是哪一个回调"。
        buckets = perf_bucket_records(values)
        if buckets:
            buckets.sort(key=lambda record: record[2], reverse=True)
            print('    最贵的回调（按 (事件 id, 属主模组) 分开；批次 086）——')
            for rank, (key, count, ticks, max_ticks, bins) in enumerate(buckets[:10], start=1):
                owner_named = owner_display_name(values, (key >> 32) & 0xFFFF)
                print(f'      {rank:>2}. {callback_name(key & 0xFFFFFFFF)}'
                      f' [{perf_bucket_owner(key)}{" = " + owner_named if owner_named else ""}]'
                      f'  {count} 次 / 合计 {to_us(ticks) / 1000.0:.1f} ms'
                      f' / 平均 {to_us(ticks) / count:.1f} µs / 最慢 {to_us(max_ticks):.0f} µs')
            # ★ 2026-10-08（排查"某一家模组的回调到底跑没跑"）：**全槽列出**（不只前 10 名）。
            #   为什么非要有：上面那张表只印前 10 名 ⇒ "某个 (事件, 属主) 不在表里" **不能**推出
            #   "它没被派发"（可能只是排在第 11 名以后）。判"这一家跑没跑"必须看全槽：
            #   只要它的 count > 0 就是跑过；count == 0 或键不存在才是真没跑。
            print(f'    ★ 全部 {len(buckets)} 个非空 (事件, 属主) 桶（`grep` 用，例如 `grep "#7 代1"`；'
                  f'缺席不能证明未派发：还须核对短读、溢出及计时是否启用）：')
            for rank, (key, count, ticks, max_ticks, bins) in enumerate(
                    sorted(buckets, key=lambda record: (-record[2], record[0])), start=1):
                print(f'      · {callback_name(key & 0xFFFFFFFF):26s} [{perf_bucket_owner(key)}]'
                      f'  {count} 次 / 合计 {to_us(ticks) / 1000.0:.1f} ms')
                if rank <= 3 and sum(bins):
                    share = [100.0 * value / sum(bins) for value in bins]
                    print(f'          分布：<250µs {share[0]:.0f}% / <1ms {share[1]:.0f}%'
                          f' / <5ms {share[2]:.0f}% / >=5ms {share[3]:.0f}%')
            unused = PERF_BUCKET_COUNT - len(buckets)
            print(f'      （用了 {len(buckets)}/{PERF_BUCKET_COUNT} 个槽，空槽 {unused} 个）')
            overflow = first(values, 'g_RuntimePerfBucketOverflow')
            if overflow:
                print(f'      ⚠ 表满溢出 {overflow} 次 ⇒ 有组合没被单独统计（把 '
                      f'`kRuntimePerfBucketCount` 调大）')
        # 批次 087：按 API 接口分开，回答"那 1.6 ms 花在哪个接口上"。
        api_buckets = perf_api_records(values)
        if api_buckets:
            catalog_names = api_catalog_names()
            print('    最贵的 API（按接口分开；批次 087）——')
            for rank, (ticks, count, identifier, inside) in enumerate(
                    rank_perf_api_buckets(api_buckets)[:10], start=1):
                name = catalog_names.get(identifier) or INTERNAL_API_NAMES.get(
                    identifier, f'未知 id 0x{identifier:08X}')
                line = (f'      {rank:>2}. {name}  {count} 次 / 合计 {to_us(ticks) / 1000.0:.1f} ms'
                        f' / 平均 {to_us(ticks) / count:.1f} µs')
                if inside:
                    share = 100.0 * inside / ticks if ticks else 0.0
                    line += (f'（其中引擎调用 {to_us(inside) / 1000.0:.1f} ms = {share:.0f}%，'
                             f'我们自己的开销 {to_us(ticks - inside) / 1000.0:.1f} ms）')
                print(line)
            print('      （"其中引擎调用"只有画字那条路径单独量过；其余接口的合计含引擎调用）')
            total_calls = optional_counter(values, 'g_RuntimePerfApiTotalCalls')
            total_ticks = optional_counter(values, 'g_RuntimePerfApiTotalTicks')
            if total_calls is None or total_ticks is None:
                print('    ★ API 计时合计：缺失（次数/累计耗时未取全）')
            elif total_calls:
                print(f'    ★ API 计时合计（含没进表的、含引擎段及嵌套计时）：{total_calls} 次 / '
                      f'{to_us(total_ticks) / 1000.0:.1f} ms / 平均 {to_us(total_ticks) / total_calls:.2f} µs'
                      f' —— 各层可能重复覆盖同一时间，不能当作互斥开销或唯一接口调用次数')
            api_overflow = first(values, 'g_RuntimePerfApiBucketOverflow')
            if api_overflow:
                print(f'      ⚠ API 桶表满溢出 {api_overflow} 次 ⇒ 有接口没被单独统计（把 '
                      f'`kRuntimePerfApiBucketCount` 调大）')
        # 批次 089：Lua 采样剖析 —— 回答"模组自己那部分时间花在它哪个函数上"。
        profile = profile_records(values)
        if profile:
            samples = first(values, 'g_RuntimePerfProfileSamples')
            print(f'    Lua 采样剖析（批次 089；共 {samples} 次采样，每 '
                  f'{PERF_PROFILE_INSTRUCTION_STEP} 条指令一次）——')
            for rank, (hits, line, name, source) in enumerate(profile[:12], start=1):
                share = 100.0 * hits / samples if samples else 0.0
                print(f'      {rank:>2}. {share:5.1f}%  {name}  {short_source(source)}:{line}'
                      f'   （{hits} 次）')
            print(f'      （用了 {len(profile)}/{PROFILE_BUCKET_COUNT} 个桶；采样只落在 **Lua 函数**上，'
                  f'C 侧接口的耗时会被算到调用它的那个 Lua 函数头上）')
            alloc_calls = first(values, 'g_RuntimePerfAllocCalls')
            if alloc_calls:
                alloc_bytes = first(values, 'g_RuntimePerfAllocBytes')
                new_calls = first(values, 'g_RuntimePerfAllocNewCalls')
                free_calls = first(values, 'g_RuntimePerfFreeCalls')
                print(f'    Lua 分配账（批次 091）：分配 {alloc_calls} 次 / {alloc_bytes / 1048576.0:.1f} MiB、'
                      f'其中新建 {new_calls} 次、释放 {free_calls} 次'
                      f'（平均每次 {alloc_bytes / alloc_calls:.0f} 字节）')
                print('      （读两次做差就能得到"每帧分配多少次/多少字节"；Lua 在每次分配里同步做增量 GC，'
                      '这段 C 侧时间采样器与接口计时都看不见）')
            profile_overflow = first(values, 'g_RuntimePerfProfileOverflow')
            if profile_overflow:
                print(f'      ⚠ 采样桶表满溢出 {profile_overflow} 次 ⇒ 有条目没被单独统计（把 '
                      f'`kRuntimePerfProfileBucketCount` 调大）')
    err_len = first(values, 'g_LastLuaErrorLength') & 0xFFFFFFFF
    if err_len:
        raw = b''.join(v.to_bytes(8, 'little') for v in (values.get('lua_error_text') or []))
        text = raw[:min(err_len, len(raw))].split(b'\0', 1)[0].decode('utf-8', 'replace')
        print(f'  最后的 Lua 错误（{err_len} 字节）：{text}')

    # 批次 052：把"最近几条 Lua 错误"也打出来 —— 只有一个槽时多个模组的错会互相遮蔽。
    history = values.get('lua_error_history') or []
    if history:
        blob = b''.join(v.to_bytes(8, 'little') for v in history)
        total = len(blob) // 128
        entries = []
        for slot in range(total):
            raw = blob[slot * 128:(slot + 1) * 128]
            if not raw:
                continue
            # 批次 068 起的每条 = `text[120]` + `owner`(u32) + `callbackId`(u32)。
            # 文本仍在开头、仍是 NUL 结尾 ⇒ 老读法（取到第一个 NUL 为止）继续成立。
            text = raw.split(b'\0', 1)[0].decode('utf-8', errors='replace').strip()
            if not text:
                continue
            owner = int.from_bytes(raw[120:124], 'little') if len(raw) >= 124 else 0
            callback = int.from_bytes(raw[124:128], 'little') if len(raw) >= 128 else 0
            entries.append((owner, callback, text))
        count = first(values, 'lua_error_history_count')
        if entries:
            print(f'  最近 {len(entries)} 条 Lua 错误（环形历史，写入计数 = {count}，'
                  f'**按"模组 + 文本"去重**）：')
            for owner, callback, entry in entries:
                # owner 打包：低 16 位 = `ModHandle.index`、高 16 位 = generation
                # （与回调登记表的 `#N 代M` 同一解包方式）。
                index = owner & 0xFFFF
                generation = (owner >> 16) & 0xFFFF
                who = f'#{index} 代{generation}' if owner else '（未知/加载期）'
                which = ('（不是回调路径）' if callback == 0xFFFFFFFF
                         else f'{callback} {callback_name(callback)}')
                print(f'    · [{who} / {which}] {entry[:140]}')
        else:
            print('  环形历史里还没有记录。')
    else:
        print('  最后的 Lua 错误：无（长度 0）')
    # ⚠️ 这个量在生产构建里**恒为 0**：它只由宿主测试脚本用的那个 Lua 全局
    # `RuntimeTest.MarkPostUpdate()` 累加（`lua_runtime.cpp` 的 `MarkPostUpdate`），
    # 真实派发走的是 `g_CallbackDispatchCounts[MC_POST_UPDATE]`（上面那段）。别把它当故障。
    print(f'  g_PostUpdateCount = {first(values, "g_PostUpdateCount") & 0xFFFFFFFF}')
    diagnostic_view = print_callback_diagnostic_view(values)
    count_label = '诊断快照登记数' if diagnostic_view else '回调登记数'
    count = first(values, 'callback_count')
    if not values.get('callback_count'):
        print(f'  {count_label} = 未读（缺读数或ELF布局未知，不按0解释）')
    elif count > CALLBACK_REGISTRY_CAPACITY:
        # 响亮地报"这个数不可信"，而不是把它当真的念出来 —— 布局一变这里就会漂
        # （2026-09-20 就是这么读到 `kNoCallbackFilter` 的哨兵值的）。
        print(f'  {count_label} = {count} ⚠ **不合理**（容量只有 {CALLBACK_REGISTRY_CAPACITY}）'
              f' ⇒ `CallbackRegistry` 的布局可能变过了：'
              f'去核对 `callback_registry.hpp` 的平行数组与 `CALLBACK_REGISTRY_COUNT_OFFSET`'
              f'（= 0x{CALLBACK_REGISTRY_COUNT_OFFSET:X}）')
    else:
        print(f'  {count_label} = {count}')
    reg = values.get('callback_registry') or []
    entries = decode_callback_entries(words_to_bytes(reg))[:count]
    if entries:
        print(f'    （下面按 20 字节/项解码；前 3 条与后 3 条，共读到 {len(entries)} 条）')
        for i in ([0, 1, 2] if len(entries) > 6 else range(len(entries))):
            if i >= len(entries):
                continue
            entry = entries[i]
            print(f'    第 {i} 条：id = {entry["id"]}（{callback_name(entry["id"])}）、'
                  f'owner = #{entry["owner_index"]} 代{entry["owner_generation"]}、'
                  f'affinity = {entry["affinity"]}、luaReference = {entry["lua_reference"]}、'
                  f'modReference = {entry["mod_reference"]}')
        if len(entries) > 6:
            print('    …')
            for i in range(len(entries) - 3, len(entries)):
                entry = entries[i]
                print(f'    第 {i} 条：id = {entry["id"]}（{callback_name(entry["id"])}）、'
                      f'owner = #{entry["owner_index"]} 代{entry["owner_generation"]}、'
                      f'affinity = {entry["affinity"]}、luaReference = {entry["lua_reference"]}、'
                      f'modReference = {entry["mod_reference"]}')
        owners = collections.Counter(
            (e['owner_index'], e['owner_generation']) for e in entries)
        summary = '、'.join(f'#{index}代{gen}：{times} 条' for (index, gen), times in
                            sorted(owners.items()))
        print(f'    ⇒ {len(entries)} 条登记的 owner 分布：{summary}'
              + ('  ← 多个 owner = 多个模组的回调确实并存' if len(owners) > 1 else
                 '  ← 只有一个 owner：多模组下说明只登记上了一家'))
        # ★ 2026-10-08（排查 MCM 打不开）：**带过滤器的登记**与**某个回调的全部登记**。
        #   为什么要这两张：MCM 的识别特征是它注册了
        #   `MC_PRE_NPC_UPDATE + affinity = EntityType.ENTITY_DARK_ESAU`（全表里极少见），
        #   而它的开菜单回调是 `MC_POST_RENDER` ⇒ 只要看到"同一个 owner
        #   **既有那条带过滤器的登记、又有 `MC_POST_RENDER`**"，就能断定
        #   **MCM 的 PostRender 确实注册上了**；反之则说明它的脚本没跑到那一行。
        filtered = [e for e in entries if e['affinity']]
        if filtered:
            print(f'    ⇒ **带过滤器的登记** {len(filtered)} 条（MCM 那条 `MC_PRE_NPC_UPDATE` '
                  f'+ `ENTITY_DARK_ESAU` 就在这里）：')
            for entry in filtered[:12]:
                print(f'        id = {entry["id"]}（{callback_name(entry["id"])}）、'
                      f'owner = #{entry["owner_index"]} 代{entry["owner_generation"]}、'
                      f'affinity = {entry["affinity"]}')
        for target_id, target_name in ((2, 'MC_POST_RENDER'),):
            same = [e for e in entries if e['id'] == target_id]
            print(f'    ⇒ `{target_name}`(id={target_id}) 的**全部登记** {len(same)} 条'
                  f'（属主分布＝谁在每帧渲染回来）：')
            for entry in same:
                print(f'        owner = #{entry["owner_index"]} 代{entry["owner_generation"]}、'
                      f'luaReference = {entry["lua_reference"]}')
        # ★ 2026-10-08：**逐条全表**（排查"某个模组的某条登记到底在不在"）。
        #   142 行很长，但它是判"某个回调注册上了没有"的唯一直接证据；
        #   找的时候 `grep` 就行（例如 `grep 'MC_EXECUTE_CMD'`）。
        print(f'    ⇒ **全表逐条**（{len(entries)} 条；按 `id（名字）｜属主` 排列，'
              f'用来判"某模组的某条登记在不在"）：')
        for index, entry in enumerate(entries):
            print(f'        [{index:3d}] id={entry["id"]:3d} {callback_name(entry["id"]):28s}'
                  f' owner=#{entry["owner_index"]} 代{entry["owner_generation"]}')
    # 回调派发计数（2026-09-18）：这张表回答"某种回调**到底被派发过几次**"。
    # 与上面那张登记表合起来才分得清三种情况：① 根本没登记；② 登记了但一次没触发
    # （= 事件没送到）；③ 触发了很多次但模组自己没干活。以前只能看出 ① 和 ② 的前半截。
    generation = first(values, 'callback_dispatch_generation') & 0xFFFFFFFF
    last_id = first(values, 'callback_dispatch_last') & 0xFFFFFFFF
    dispatch_raw = words_to_bytes(values.get('callback_dispatch_counts') or [])
    counts = [int.from_bytes(dispatch_raw[index * 4:index * 4 + 4], 'little')
              for index in range(CALLBACK_DISPATCH_COUNTER_COUNT)]
    print()
    print(f'  === 回调派发次数（会话代数 {generation}：这张表每次新建 Lua 会话时归零）===')
    if last_id == 0xFFFFFFFF:
        print('    最后一次派发的回调 = 还没有派发过任何回调')
    else:
        print(f'    最后一次派发的回调 = {last_id}（{callback_name(last_id)}）')
    fired = [(index, count) for index, count in enumerate(counts) if count]
    if not fired:
        print('    ⚠️ 74 种回调的计数**全是 0** ⇒ 引擎一次派发都没走到：'
              '不是"模组没干活"，是事件根本没送到。')
    else:
        for index, count in fired:
            print(f'    {index:3d} {callback_name(index):24s} {count}')
        silent = [f'{index} {CALLBACK_NAMES[index]}'
                  for index in sorted(CALLBACK_NAMES)
                  if counts[index] == 0]
        if silent:
            print(f'    （**已接线**但这次一次都没触发：{"、".join(silent)}）')
    self_addr = first(values, 'g_runtimeSelfAddress')
    mark = '（= exl_main，入口跑过 ✓）' if self_addr == base + SYMS['exl_main'] else ''
    print(f'  g_runtimeSelfAddress = 0x{self_addr:012x} {mark}')
    table = values.get('filetable') or []
    if table:
        print(f'  运行时文件表：已植入 {sum(1 for v in table if v)}/4 项'
              f'（{", ".join(hex(v) for v in table)}）')

    print()
    print('=== 运行时**读进来的**清单原文与入口脚本（判"纯资源型"到底属于哪一种）===')
    manifest_raw = words_to_bytes(values.get('manifest_head') or [])
    if manifest_raw.strip(b'\0'):
        text = manifest_raw.split(b'\0', 1)[0].decode('utf-8', 'replace')
        print(f'  清单原文（前 {len(text)} 字节）：')
        for line in text.splitlines()[:12]:
            print(f'    | {line}')
        print('    ⇒ 看 `mods[]` 里的 `directory` / `entry`：')
        print('       · 没有 `entry` 字段 ⇒ 运行时按"纯资源型模组"处理（不会跑 Lua）')
        print('       · 有 `entry` 但那个文件不在包里 ⇒ 同上（且不报错）')
        enabled = re.search(r'"enabled"\s*:\s*(true|false)', text)
        if enabled:
            if enabled.group(1) == 'false':
                print('    ★ 注意：这份清单里模组被标成 **"enabled": false** ⇒'
                      ' 运行时按"没有启用的模组"处理（解析阶段就失败）⇒ **模组不加载、也不报错**。')
            else:
                print('    清单里模组是 "enabled": true ⇒ 不是"被禁用"这一条。')
    else:
        print('  清单缓冲区是空的 ⇒ 这次启动没读进清单（那"纯资源型"就不该出现，需复查）')
    entry_raw = words_to_bytes(values.get('entry_head') or [])
    head = entry_raw.split(b'\0', 1)[0]
    print(f'  入口脚本缓冲区前 {len(head)} 字节：'
          + (f'{head[:80].decode("utf-8", "replace")!r}' if head else '（空 ⇒ 没有脚本被读进来）'))

    print()
    print(f'=== {len(HOOK_NAMES)} 个挂点：各自的回调指针（g_hookCallbacks）===')
    callbacks = values.get('hook_callbacks') or []
    for i, name in enumerate(HOOK_NAMES):
        ptr = callbacks[i] if i < len(callbacks) else None
        relay_key = RELAY_BY_HOOK.get(name)
        if name in COLD_HOOK_SITES:
            site,gate,original=COLD_HOOK_SITES[name]
            source=(values.get(f'cold_{name}_source') or [None])[0]
            words=values.get(f'cold_{name}_gate') or []
            target=decode_internal_branch(source&0xFFFFFFFF,game_base+site) if source is not None else None
            raw=words_to_bytes(words)
            installed=target==game_base+gate and len(raw)>=32 and raw[:16]==bytes.fromhex('d000001010fedfc8500000b400021fd6') and int.from_bytes(raw[16:20],'little')==original and decode_internal_branch(int.from_bytes(raw[20:24],'little'),game_base+gate+20)==game_base+site+4
            pointer=int.from_bytes(raw[24:32],'little') if installed else 0
            if installed:print(f'  [{i}] {name:20} 加载前中继完整，发布gateway '+(f'0x{pointer:x}' if pointer else '尚未发布'))
            else:print(f'  [{i}] {name:20} 原源B/中继缺失或不匹配，不判成已安装')
        elif name == 'EntityRemovePointers':
            wanted = base + SYMS['entity_remove_pointer_callback'] if 'entity_remove_pointer_callback' in SYMS else None
            pointers = [(values.get(f'entity_remove_pointer_{j}') or [None])[0]
                        for j in range(len(ENTITY_REMOVE_POINTER_SITES))]
            matched = sum(p == wanted for p in pointers) if wanted is not None else 0
            print(f'  [{i}] {name:20} GOT/虚表 {matched}/{len(pointers)} 个指针与本包拦截器一致；缺读数不算已装')
        elif name in INTERNAL_HOOK_SITES:
            site,veneer,size = INTERNAL_HOOK_SITES[name]
            raw = values.get(f'internal_{name}_source') or []
            landed = decode_internal_branch(raw[0]&0xFFFFFFFF,game_base+site) if raw else None
            slot = INTERNAL_LITERAL_SLOTS.get(name)
            pointer = (values.get(f'internal_{name}_literal') or [None])[0]
            gateway = decode_internal_veneer(values.get(f'internal_{name}_veneer'),game_base+veneer,size,
                                             game_base+slot if slot is not None else None,pointer)
            if landed == game_base+veneer and gateway is not None:
                print(f'  [{i}] {name:20} 内部单B → 游戏+0x{veneer:x} → gateway 0x{gateway:x}')
            else:
                print(f'  [{i}] {name:20} 内部挂点读不到或指令不匹配；不以旧入口槽判安装成功')
        elif ptr is None:
            print(f'  [{i}] {name:20} 读不到')
        elif relay_key and relay_key in SYMS and ptr == base + SYMS[relay_key]:
            print(f'  [{i}] {name:20} 0x{ptr:012x} ← 零占洞入口中继（模块+0x{SYMS[relay_key]:x}）★')
        elif ptr == 0:
            note = '（该路走 GOT 槽，判据见下）' if name == 'ManagerPresent' else '（该路未走入口中继）'
            print(f'  [{i}] {name:20} 0x{ptr:012x} ← {note}')
        else:
            print(f'  [{i}] {name:20} 0x{ptr:012x}')

    print()
    print('=== 让模组那一层早于引擎第一次读：`Game::Init` 入口中继（批次 371；1 ms = 19200 tick）===')
    early = values.get('early_mount_state') or []
    if len(early) < 8:
        print('  状态面 = 读不到（本构建里没有 `g_EarlyMountState`，或符号没同步上）')
    else:
        # ★ 结构体是 **5 个相邻 u64 + 6 个 u32**（见 `early_mod_mount_state.hpp`）：
        #   时间戳是 u64 ⇒ 按 8 字节字取（`first`）；计数是 u32 ⇒ 必须按**真正的 u32
        #   下标**取（`u32_at`）—— 一个 8 字节字里装着两个 u32，用 `first` 读会把隔壁的值
        #   算进来（这正是 `u32_at` 注释里那个 2026-09-26 的坑）。
        em_worker = first(values, 'early_mount_state', 0)
        em_delay = first(values, 'early_mount_state', 1)
        em_module = first(values, 'early_mount_state', 2)
        em_installed = first(values, 'early_mount_state', 3)
        em_callback = first(values, 'early_mount_state', 4)
        em_install_attempted = u32_at(values, 'early_mount_state', 10)
        em_install_failure = u32_at(values, 'early_mount_state', 11)
        em_callback_fired = u32_at(values, 'early_mount_state', 12)
        em_mounts_attempted = u32_at(values, 'early_mount_state', 13)
        em_mounts_failed = u32_at(values, 'early_mount_state', 14)
        em_prefix = u32_at(values, 'early_mount_state', 15)
        # ★★★ 批次 387（2026-10-07 00:0x）：**u32 下标 16/17** —— `[11]/[12]`（前置步骤里"早装资源类中继"的结果）。
        #   ★ 这里第一版写成 18/19 **是错的**（我按"字段序号"数，忘了前面 5 个是 **u64**、各占 2 个 u32 位）：
        #     正确换算 = 5×2 + (字段序号-5) ⇒ `[11]`→16、`[12]`→17。写错的下标读到越界垃圾（恒 0），
        #     表现为"早装没走到"——差点把一个**已经生效**的改动判成没生效。
        #   ⇒ 教训：**改了结构体就要把下标重算一遍**（"前 5 个是 u64"就是这条的坑）。
        # 原文保留（下面是这两格当初加进来时的说明）：
        #   ★★★ 批次 385（2026-10-06）：u32 下标 18/19 = `[11]/[12]` —— 前置步骤里"早装资源类中继"的结果。
        #   第一次早装**静默失败**了（少了 `RegisterEntryRelayCallbacks()` ⇒ 判定拒绝），
        #   而读数上只表现为"`ANM2` 中继首次被调仍然很晚" ⇒ 白改一轮才发现。
        #   ⇒ 这两格就是为"**不再静默**"加的：`installed < attempted` 就是早装失败。
        em_early_attempted = u32_at(values, 'early_mount_state', 16)
        em_early_installed = u32_at(values, 'early_mount_state', 17)

        def em_rel(tick: int) -> str:
            """相对"worker 进入"的毫秒数；tick 0 = **那一步没走到**（不是"发生在 tick 0"）。"""
            if tick == 0:
                return '没走到'
            if em_worker == 0:
                return f'{tick / 19200.0:.1f} ms（无基准，按绝对 tick 换算）'
            return f'{(tick - em_worker) / 19200.0:+.1f} ms'

        prelude_ms = None
        if em_worker and em_delay and em_delay >= em_worker:
            prelude_ms = (em_delay - em_worker) / 19200.0
        print(f'  worker 进入            = {em_rel(em_worker)}')
        # ★★ 批次 384（2026-10-06）：把"worker 进入"的**原始 tick**也打出来 —— 新增的那格
        #   （`anm2load_state[8]` = `ANM2` 中继"首次被调"的时刻）是**绝对 tick 的低 32 位**，
        #   而上面这些行都只打了相对值 ⇒ **不给绝对基准就没法跟它比大小**。这一行就是那个基准。
        #   ★ 两边都取低 32 位：19.2 MHz 的计数器开机约 223 秒回绕一次，本判据只看开机后头几百秒
        #     ⇒ 够用；比较时若算出"负数"，加 2**32 再比（那是回绕，不是"发生在过去"）。
        if em_worker:
            print(f'  ★ worker 进入的绝对 tick = {em_worker}（低 32 位 = {em_worker & 0xFFFFFFFF}）'
                  f'  ← 与 `ANM2` 中继「首次被调」那格**同源同单位**，可直接比大小')
        print('  5 秒等待开始（= 前置步骤结束）= ' + em_rel(em_delay)
              + (f'（前置步骤花了 {prelude_ms:.1f} ms）' if prelude_ms is not None else ''))
        print(f'  认出游戏模块           = {em_rel(em_module)}')
        print(f'  `Game::Init` 中继装成  = {em_rel(em_installed)}'
              + f'（试装 {em_install_attempted}、失败码 {em_install_failure}）')
        print(f'  中继回调第一次被调     = {em_rel(em_callback)}（共被调 {em_callback_fired} 次）')
        print(f'  回调里调 RegisterMod   = {em_mounts_attempted} 次、失败 {em_mounts_failed} 次')
        # ★★★ 批次 385：前置步骤里"早装资源类中继"的结果（两条 = `GetMountedFilePath` + `Anm2Load`）。
        #   `installed < attempted` ⇒ **早装失败**（第一版就是 0/2：少了 `RegisterEntryRelayCallbacks()`）。
        if em_early_attempted or em_early_installed:
            print(f'  ★ 早装资源类中继       = 试 {em_early_attempted} 条、成 {em_early_installed} 条'
                  + ('  ⇒ **有失败**：绑定表没先注册是最常见的原因'
                     if em_early_installed < em_early_attempted else '  ⇒ 两条都装上了'))
        else:
            print('  ★ 早装资源类中继       = **没走到**（0 条尝试）')
        # 判读按"我们走到了哪一步"分档（tick 0 = 没走到）—— 每档只说那一档能得出的结论：
        # "中继没装上"与"装上了但引擎从没调它"是两件完全不同的事，不许混成一句话。
        if em_worker == 0:
            print('  ⇒ 状态面还是空的：worker 还没走到那一步（或本构建是诊断构建，'
                  '那一段按 `EXL_DIAGNOSTIC_STAGE` 不编译）')
        elif em_module == 0:
            print('  ⇒ 2 秒内没认出游戏模块 ⇒ 前置步骤在第一步就收工（后面那条既有扫描照旧等满 30 秒）')
        elif em_installed == 0:
            if em_install_failure == 0xFFFFFFFE:
                print('  ⚠ 走到了装中继那一步，但**靶点不可挂**（对齐/不在 `.text`/那一页现在不可执行）'
                      '⇒ 看 `Game::Init` 入口那 16 字节与 `kGameInitEntryExpectedBytes` 是否还一致')
            elif em_install_failure == 0:
                print('  ⇒ 还没装（不是失败）—— 走到第三步之前就收工了？看上面的时间轴')
            else:
                print(f'  ⚠ 装中继**失败**（`TryInstallEntryRelay` 失败码 {em_install_failure}；'
                      '码表见 `runtime/source/relay/entry_relay.hpp`）')
        elif em_callback_fired == 0:
            print('  ★ 中继**装上了**、但引擎**从没调过它** ⇒ `Game::Init` 的第一次调用早于我们装钩子 '
                  '⇒ 下一步必须往**更早的入口**走（例如引擎重建内容挂载点表那一次调用）')
        else:
            print(f'  ★ 中继装上了、且被引擎调了 {em_callback_fired} 次 ⇒ 回调确实排在 `Minimap::Init` 之前')
            if em_mounts_attempted == 0:
                print('  ⚠ 但回调里**一次都没挂**（文件绑定不齐，或清单与自动发现都读不出来）')
            elif em_prefix:
                print('  ★★ 挂完之后引擎那张表里**有** `isaac_mods` 前缀 ⇒ 模组层在引擎第一次读之前就存在了')
            else:
                print(f'  ⚠ 挂了 {em_mounts_attempted} 次（失败 {em_mounts_failed} 次）、但读表时**没有** '
                      '`isaac_mods` 前缀 ⇒ 与 `image_pcx_diag` 的挂载后探测/时序位图对照')

    print()
    print('=== 模组覆盖本体资源：`ANM2::Load` 入口中继（批次 363）===')
    anm2_entry = values.get('anm2load_entry') or []
    anm2_hex = b''.join(w.to_bytes(8, 'little') for w in anm2_entry[:2]).hex()
    if not anm2_entry:
        print('  目标入口（游戏模块 0xc970）= 读不到')
    elif anm2_hex.startswith('5000005800021fd6'):
        print(f'  目标入口（游戏模块 0xc970）= {anm2_hex[:32]}… ← 已是入口补丁')
    else:
        print(f'  目标入口（游戏模块 0xc970）= {anm2_hex[:32]}… ← **仍是原版序言**（中继没装上）')
    print('  --- PC 的资源层重定向（批次 378）---')
    redirect_published = u32_at(values, 'mod_redirect_state', 0)
    redirect_mods = u32_at(values, 'mod_redirect_state', 1)
    redirect_calls = u32_at(values, 'mod_redirect_state', 2)
    redirect_hits = u32_at(values, 'mod_redirect_state', 3)
    redirect_dlc3 = u32_at(values, 'mod_redirect_state', 4)
    redirect_plain = u32_at(values, 'mod_redirect_state', 5)
    redirect_last_mod = u32_at(values, 'mod_redirect_state', 6)
    redirect_skipped = u32_at(values, 'mod_redirect_state', 7)
    redirect_toolong = u32_at(values, 'mod_redirect_state', 8)
    redirect_publishes = u32_at(values, 'mod_redirect_state', 9)
    if not (values.get('mod_redirect_state') or []):
        print('  状态面 = 读不到（`--elf` 同步一下符号；或这一版还没有这段代码）')
    else:
        last_mod_text = ('没命中过' if redirect_last_mod == 0xFFFFFFFF
                         else f'模组 #{redirect_last_mod}')
        print(f'  名单发布 = {"已发布" if redirect_published else "还没发布"}'
              f'（发布过 {redirect_publishes} 次 / 那一刻清单里 {redirect_mods} 个模组）')
        print(f'  被问 {redirect_calls} 次｜★ 答了模组层 {redirect_hits} 次'
              f'（`resources-dlc3/` {redirect_dlc3} / `resources/` {redirect_plain}）｜'
              f'最近命中 = {last_mod_text}')
        print(f'  跳过"引擎已解析" {redirect_skipped} 次｜装不下 {redirect_toolong} 次')
        raw = words_to_bytes(values.get('mod_redirect_state') or [])
        query = raw[40:40 + 192].split(b'\x00', 1)[0].decode('utf-8', errors='replace')
        answer = raw[232:232 + 224].split(b'\x00', 1)[0].decode('utf-8', errors='replace')
        print(f'  最近一次问的路径 = {query!r}')
        print(f'  最近一次答的路径 = {answer!r}')
        print('  判读：')
        if redirect_publishes == 0:
            print('    ★ 清单**一次都没发布** ⇒ 这条重定向不可能生效（先查"重活之前"那一步有没有跑到）。')
        elif redirect_calls == 0:
            print('    ★ 发表了但**一次都没被问到** ⇒ 这一局没有任何资源请求走到那个缝上'
                  '（或挂点没装上 —— 看入口那两行的字节）。')
        elif redirect_hits == 0:
            print('    ★ 问到了、但**一次都没命中模组** ⇒ 模组资源这一局没被引擎看见：'
                  '先看上面两条路径是不是这一条、再看清单里的模组目录对不对。')
        else:
            print(f'    ⇒ 这条重定向**真的在工作**：{redirect_hits} 次把请求指到了模组目录。')

    anm2_state = values.get('anm2load_state') or []
    if len(anm2_state) < 5:
        print('  状态面 = 读不到')
    else:
        # ★★ 2026-10-05 修（批次 364 的读数当场抓到的工具缺陷）：`Anm2LoadOverrideState` 是
        #    **10 个相邻 `uint32`**（40 字节 = 读数工具取的 **5** 个 8 字节字；★ 批次 384（2026-10-06）
        #    又在末尾追加了 `[8] callbackFirstTicks` / `[9] reservedAlign`，原来只有 8 个）⇒ 必须按**真正的
        #    u32 下标**解码（`u32_at`），一个 8 字节字里装着**两个**字段。
        #    原来的 `[w & 0xffffffff for w in anm2_state]` 把每个字当成一个字段 ⇒
        #    ① 印出来的"失败码/被调次数"是隔壁字段的值（2026-10-05 01:24 实测把
        #    `callbackCount = 161` 印成"失败码 161"、"被调次数 0"）；
        #    ② 取 `u[4]` 时直接 `IndexError`，**把整份读数打断在最后一段**。
        #    标量走 `first_u32`、数组一律走 `u32_at` —— 这是仓库里已有的口径（见 `u32_at` 注释）。
        relay_state = u32_at(values, 'anm2load_state', 0)
        relay_failure = u32_at(values, 'anm2load_state', 1)
        callback_count = u32_at(values, 'anm2load_state', 2)
        resolver_asked = u32_at(values, 'anm2load_state', 3)
        stale_found = u32_at(values, 'anm2load_state', 4)
        evicted = u32_at(values, 'anm2load_state', 5)
        last_path_hash = u32_at(values, 'anm2load_state', 6)
        # ★ 2026-10-05（批次 368）：第 8 格从"对齐保留"改成有含义的 `mountListFlags`。
        mount_flags = u32_at(values, 'anm2load_state', 7)
        # ★★ 批次 384（2026-10-06）：第 9 格 = **本条中继"第一次被调用"的时刻**（低 32 位 tick）。
        #    用它回答"引擎第一次读共享资源时、我们的中继装了没有"：与上面那段「`Game::Init` 中继
        #    回调第一次被调」（`g_EarlyMountState` 里的一个 u64 时间戳，同源同单位 19.2 MHz）
        #    **比大小**即可。只取低 32 位 —— 19.2 MHz 的计数器在开机约 223 秒内不回绕，够本判据用。
        callback_first_ticks = u32_at(values, 'anm2load_state', 8)
        relay = {0: '未试', 1: '已装', 2: '未装'}.get(relay_state, f'未知({relay_state})')
        print(f'  中继装上没有 = {relay}｜失败码 {relay_failure}')
        print(f'  中继被调次数 = {callback_count}｜问解析器 = {resolver_asked}')
        if callback_first_ticks:
            print(f'  ★★ 中继**首次被调** = tick {callback_first_ticks}'
                  f'（≈ {callback_first_ticks / 19200.0:.1f} ms）')
            # ★★★ 批次 384：**自动与 `Game::Init` 的时刻比大小** —— 这一格的全部意义就在这里。
            #   两个数都是"绝对 tick 的低 32 位"、同源同单位（19.2 MHz；见上面那行新增的基准）。
            #   ★ 回绕：19.2 MHz 的计数器开机约 223 秒后低位绕回来 ⇒ 差值为负时加 2**32 再判。
            em_worker_here = first(values, 'early_mount_state', 0)
            em_callback_here = first(values, 'early_mount_state', 4)
            if em_worker_here and em_callback_here:
                game_init_ticks = em_callback_here & 0xFFFFFFFF
                delta = callback_first_ticks - game_init_ticks
                if delta < 0:
                    delta += 1 << 32
                if delta < 0x40000000:      # 55.8 秒以内算"晚于"；超过它基本是回绕（= 早于）
                    print(f'  ★★★ 与 `Game::Init`（tick {game_init_ticks}）比：**晚于**它'
                          f' {delta / 19200.0 / 1000.0:.1f} 秒 ⇒ **引擎最初那次读没走我们的中继**'
                          f' ⇒ 治法是"把资源类中继提前到 worker 的前置步骤"（见'
                          f' `docs/分析-红字根因-模组覆盖是事后修正而PC是启动期前置-20261006.md` §8.4）')
                else:
                    print(f'  ★★★ 与 `Game::Init`（tick {game_init_ticks}）比：**早于**它'
                          f' ⇒ 最初那次读**走了**我们的中继（那就别再往"提前装中继"改）')
            else:
                print('  （`g_EarlyMountState` 那段没读到 ⇒ 这次没法自动比，请手工比两个 tick）')
        else:
            print('  ★★ 中继**首次被调** = 0（一次都没被调过 ⇒ 先查它装上没有）')
        print(f'  ★ 找到本体旧条目 = {stale_found}｜真正作废并回收 = {evicted}｜'
              f'最近一条模组层路径哈希 = 0x{last_path_hash:08x}')
        # ★ 把"这一格会不会撒谎"当场判出来，别让后来者再被它误导一次：
        #   入口已经是补丁、这一格却还写着"未试" ⇒ 安装结果根本没人记账
        #   （`NoteAnm2LoadRelayInstalled` 直到批次 363 为止**一个调用点都没有**）。
        if mount_flags & 0x1:
            print('  ⚠ 引擎那张挂载点表里**没有模组前缀**（开机快照）⇒ 反推 owner 前缀不成立，'
                  '已按"每个键都算压着模组"处理')
        if mount_flags & 0x2:
            print('  · 出现过"同一路径本会话已作废过 ⇒ 跳过"（防空转）')
        if relay_state == 0 and anm2_entry and anm2_hex.startswith('5000005800021fd6'):
            print('  ⚠ 入口已是补丁、这一格却仍是"未试" ⇒ **安装结果没被记账**'
                  '（`NoteAnm2LoadRelayInstalled` 没有调用点）—— 以入口那一行为准。')
        if callback_count == 0:
            print('  ⇒ 中继一次都没被调到：`ANM2::Load` 这条路本次启动没走过（或中继没装上）')
        elif evicted > 0:
            print('  ⇒ 这条链**真的在修**"旧缓存压住模组"：有共享路径被作废过。')
        elif stale_found > 0:
            print('  ⇒ 找到过旧条目但没作废（计数为 0 或绑定不齐）—— 看失败码那一格。')
        elif resolver_asked == 0:
            print('  ⇒ 中继被调到过，但**一次都没走到"问解析器"那一步**（缓存里没有'
                  '"压着模组"的旧条目）⇒ 这条链本次**没有被真正考到**，别据此判"修好了"。')
        else:
            print('  ⇒ 走过这条路，但没有"解析器答模组层"的路径 ⇒ 本次没有共享资源被模组覆盖。')

    print()
    print('=== 引擎那条"模组 content 加载"路的闸门（批次 147：挂 `ModManager::LoadConfigs` 入口）===')
    ml_entry = values.get('modmanager_loadconfigs_entry') or []
    ml_hex = b''.join(w.to_bytes(8, 'little') for w in ml_entry[:2]).hex()
    if not ml_entry:
        print('  目标入口（游戏模块 0x41e388）= 读不到')
    elif ml_hex.startswith('5000005800021fd6'):
        print(f'  目标入口（游戏模块 0x41e388）= {ml_hex} ← 已是我们的入口中继 ★')
    else:
        print(f'  目标入口（游戏模块 0x41e388）= {ml_hex}'
              '  ← **不是**入口补丁 ⇒ 挂点没装上（本段其余数字都会是 0）')
    ml_calls = first(values, 'mod_loadcfg_calls') or 0
    ml_entries = first(values, 'mod_loadcfg_entries') or 0
    ml_enabled = first(values, 'mod_loadcfg_enabled') or 0
    ml_disabled = first(values, 'mod_loadcfg_disabled') or 0
    ml_known = first(values, 'mod_loadcfg_disabled_known') or 0
    ml_stateloaded = first(values, 'mod_loadcfg_state_loaded') or 0
    ml_matched = first(values, 'mod_loadcfg_matched') or 0
    ml_engineoff = first(values, 'mod_loadcfg_engine_off') or 0
    print(f'  闸门被引擎调到 {ml_calls} 次｜那一次看到模组 {ml_entries} 条：'
          f'我们置"要加载" {ml_enabled} 条、置"不加载" {ml_disabled} 条')
    print(f'  那一刻：存档侧记着关掉 {ml_known} 个模组、状态读过存档没有 = {ml_stateloaded}；'
          f'命中"我们关掉的目录名" {ml_matched} 条')
    print(f'  引擎自己说"这条关着"（`ModEntry + 0x138` 为 0）的有 {ml_engineoff} 条'
          '（那些我们不动 —— 与 Lua 侧认 `disable.it` 的口径一致）')
    ml_writefail = first(values, 'mod_loadcfg_write_failures') or 0
    print(f'  写 `+0x139` 被内存判定挡下 {ml_writefail} 次'
          + ('（非 0 ⇒ 引擎会按它自己那份值走，本闸门没生效）' if ml_writefail else ' ⇒ 全部写下去了'))
    path_raw = words_to_bytes(values.get('mod_loadcfg_first_path') or [])
    path_text = path_raw.split(b'\x00', 1)[0].decode('utf-8', errors='replace')
    print(f'  第一条 `ModEntry+0x48` 的字符串 = {path_text!r}'
          '（期望形如 "<模组目录>/content/"；空 = 偏移或取串口径不对）')
    toggle_loaded = first(values, 'mod_toggle_state_loaded') or 0
    print(f'  存档侧模组开关"读过一次"标志 = {toggle_loaded}')
    print('  判读：')
    if ml_calls == 0:
        print('    ★ 引擎**一次都没调** `ModManager::LoadConfigs` ⇒ 这个挂点（或这个时机）不成立，'
              '再谈内容加载没有意义 —— 下一步要改用别的靶点（例如它上游的 `Reset`）。')
    elif ml_entries == 0:
        print('    ★ 调到了，但那一刻模组列表是空的 ⇒ 我们比 `ListMods` 更早，标志没地方施加。')
    elif ml_stateloaded == 0:
        print('    ★ 列表有了，但**我们的开关状态还没读** ⇒ 这一次是按"全都不拦"放行的：'
              '模组内容会进来，被关掉的那些也会。需要把状态读取挪到引擎扫目录之前。')
        print(f'        置位：要加载 {ml_enabled}、不加载 {ml_disabled}（其中引擎自己关着 {ml_engineoff}）')
    else:
        print(f'    ✓ 时机与状态都对上了：置"要加载" {ml_enabled} 条、'
              f'置"不加载" {ml_disabled} 条（其中引擎自己关着 {ml_engineoff}、'
              f'命中我们存档侧开关 {ml_matched} 条）。')
        print('      下一步看上面"服装查表/null 服装容器"与 Music 表条数有没有从 132 / 119 涨上去。')

    print()
    print('=== 把模组的 content 喂给引擎（批次 152/153：直接调两个加载器 + 时机必须早于模组脚本）===')
    me_attempts = first_u32(values, 'mod_engine_attempts')
    me_stage = first_u32(values, 'mod_engine_stage')
    me_entries = first_u32(values, 'mod_engine_entries')
    me_costume = first_u32(values, 'mod_engine_costume_loads')
    me_music = first_u32(values, 'mod_engine_music_loads')
    me_fail = first_u32(values, 'mod_engine_resolve_failures')
    me_miss = first_u32(values, 'mod_engine_path_misses')
    me_before = first_u32(values, 'music_entries_before')
    me_after = first_u32(values, 'music_entries_after')
    cc_before = first_u32(values, 'costume_entries_before')
    cc_after = first_u32(values, 'costume_entries_after')
    stage_text = {0: '没做（没进过模组页？）', 1: '两个入口已解析（还没加载）',
                  2: '★ 全部走完**且容器涨了**（真喂进去了）', 3: '失败',
                  4: '跑完了但**两个容器一条没涨**（文件没打开 / 路径不对 / 挂载没就绪）'
                  }.get(me_stage, f'未知({me_stage})')
    # ★ 批次 153：**触发时机**（`g_ModMenuState` 的第 [60] 格）。
    # 真机已证明"喂成功了但喂晚了"与"压根没喂"在其他读数上长得一模一样 —— 这一格是唯一能分开的。
    _state_raw = words_to_bytes(values.get('mod_menu_state') or [])
    me_trigger = (int.from_bytes(_state_raw[60 * 4:61 * 4], 'little')
                  if len(_state_raw) >= 61 * 4 else 0)
    trigger_text = {
        0: '没跑过（或这一版运行时还没有这一格）',
        1: '★ 模组脚本**执行之前**（正确时机）',
        2: '模组页那一刻（兜底：早期那次没喂成）',
        3: '每帧重试（早期那次没喂成，靠后来的重试补上）',
    }.get(me_trigger, f'未知({me_trigger})')
    # 批次 154：「模组脚本之前」**那一次**走到了哪一步（会被后来的重试覆盖，所以单独留了一格）。
    me_early = (int.from_bytes(_state_raw[61 * 4:62 * 4], 'little')
                if len(_state_raw) >= 62 * 4 else 0)
    early_text = {0: '没跑过', 1: '两个入口已解析（还没加载）',
                  2: '★ 跑完且容器涨了（**真喂进去了**）', 3: '失败（那一轮没喂成）',
                  4: '跑完了但**一条都没加载**（挂载解析那时还没就绪）'
                  }.get(me_early, f'未知({me_early})')
    # ★ 批次 159：「继续游戏」现在可不可选（`g_ModMenuState` 的第 [62] 格）+ 我们跳过它几次 [63]。
    # 判据：没有可继续的局时引擎把那一项画成灰帧并跳过它，我们那一列的导航必须照抄这条规则；
    # [62] 是"引擎到底怎么说的"（2 = 我们读不到），[63] 是"这条规则真的生效过几次"。
    me_continue = (int.from_bytes(_state_raw[62 * 4:63 * 4], 'little')
                   if len(_state_raw) >= 63 * 4 else None)
    me_continue_skips = (int.from_bytes(_state_raw[63 * 4:64 * 4], 'little')
                         if len(_state_raw) >= 64 * 4 else 0)
    if me_continue is not None:
        continue_text = {0: '不可选（引擎把它画成灰帧）', 1: '可选',
                         2: '⚠ 读不到（按"可选"处理，旧行为）'}.get(
                             me_continue, f'未知({me_continue})')
        print(f'  引擎说「继续游戏」[62] = {me_continue} = {continue_text}'
              f'｜我们因为它不可选而跳过 [63] = {me_continue_skips} 次'
              + ('　← ★ 这条规则生效过（光标不会停在灰项上）' if me_continue_skips else ''))
    print(f'  本函数被走过 {me_attempts} 次｜阶段 = {stage_text}')
    print(f'  触发时机 [60] = {me_trigger} = {trigger_text}')
    print(f'  早期那次（模组脚本之前）走到 [61] = {me_early} = {early_text}'
          + ('' if me_early == 2 else
             '　← ★ 不是"真喂进去了"：那次没成（或还没轮到它）。'
             '**这一格才是"舞能不能出来"的判据** —— 服装编号是模组在它自己 Lua 文件的'
             '文件作用域查死并固定的，那之后我们再把服装喂进引擎也没用。'))
    print(f'  处理了 {me_entries} 个启用着的模组｜`LoadCostumes` 调 {me_costume} 次、'
          f'`Music::LoadConfig` 调 {me_music} 次；挂载解析不到 {me_miss} 条（那些跳过了）')
    if me_fail:
        print(f'  ★ 入口核对失败位图 = {me_fail}（bit0 LoadCostumes / bit1 Music::LoadConfig）'
              ' ⇒ 对不上就一次都不调')
    print(f'  ★★ 验收判据：曲目表 {me_before} → {me_after}（模组 music.xml 2 条 ⇒ 121）；'
          f'null 服装容器 {cc_before} → {cc_after}（模组 costumes2.xml 23 条 ⇒ 155）')
    if me_stage == 2 and me_after == me_before and cc_after == cc_before:
        print('     ⚠ 走完了但两个容器都没涨 ⇒ 文件没被引擎读到：查路径写法'
              '（`isaac_mods/mods/<目录>/content/<文件名>`）与目录名是否与发现结果一致。')
    if me_stage == 2 and (me_after > me_before or cc_after > cc_before):
        print('     ✓ 模组 content 真的进了引擎 —— 这就是"跳舞模组能生效"的前提。')

    # ---- 批次 149b：路径口径（哪个让容器涨了）+ 解析回来的原始串 ----------------------------
    #
    # 148d 那轮是"两个加载器各被调 1 次、容器一条没涨"，只能怀疑路径形态；这一段的判读表：
    #   * form == 1 ⇒ 引擎的文件层要的是**相对应用根**（去 `rom:/`）—— 与 085 的口径一致；
    #   * form == 2 ⇒ 引擎的文件层要的**带 `rom:/`**（那我们原来那条路其实是对的，得另找原因）；
    #   * form == 0 ⇒ 两种口径都不行 ⇒ **不是路径口径的问题**，下一个怀疑对象是
    #     `ItemConfig::LoadCostumes` 的第二个参数（引擎自己传的是真 `ModEntry*`，我们传 `nullptr`）。
    me_cform = first_u32(values, 'mod_engine_costume_form')
    me_mform = first_u32(values, 'mod_engine_music_form')
    me_ccalls = first_u32(values, 'mod_engine_costume_calls')
    me_mcalls = first_u32(values, 'mod_engine_music_calls')
    form_text = {0: '两种口径都没让容器涨', 1: '★ 去掉 `rom:/` 后涨了（= 引擎认相对应用根）',
                 2: '★ 带 `rom:/` 才涨（= 原来那条路其实对）'}
    if me_ccalls or me_mcalls or me_cform or me_mform:
        print(f'  路径口径：服装 {form_text.get(me_cform, me_cform)}'
              f'｜音乐 {form_text.get(me_mform, me_mform)}')
        print(f'  加载器实际调用次数：`LoadCostumes` {me_ccalls} 次、`Music::LoadConfig` {me_mcalls} 次'
              '　（两种口径各算一次；命中一种就停）')
        for label, key in (('服装', 'mod_engine_resolved_costumes'), ('音乐', 'mod_engine_resolved_music')):
            raw = words_to_bytes(values.get(key) or []).split(b'\x00', 1)[0]
            text = raw.decode('utf-8', errors='replace')
            print(f'  `GetMountedFilePath` 为{label}返回的串 = {text!r}')
        # ★ 自证条目布局：曲目表最后一条的编号（`+0x00`）与名字串（`+0x08` 起 32 字节）。
        #   解码口径 = **libc++ `std::string` 的真实布局**（与运行时 `ResolveLibcxxString` 同一套；
        #   2026-09-27 我在这里**写错过一次**：以为短串标志在首字节最高位，实际在**最低位**）：
        #     * 首字节 bit0 == 1 ⇒ **长串**：`+0x00` 是指针、`+0x08` 是长度、`+0x10` 是容量；
        #     * 首字节 bit0 == 0 ⇒ **短串**：长度 = 首字节 >> 1（**存的是 size*2**）、字符从 `+0x01` 起。
        #   真机实证：模组那条 `paincialist` 的首字节是 `0x16` = (11<<1)|0 ⇒ 长度 11、短串 ✓。
        #   这段自证的意义：`Isaac:GetMusicIdByName` 靠"名字在条目 `+0x08`"命中；
        #   它不命中 ⇒ 模组拿 `-1` 去 `MusicManager():Play` ⇒ 引擎按 `-1*0x70` 越界索引而**崩**。
        last_id = first_u32(values, 'mod_engine_music_last_entry_id')
        last_raw = words_to_bytes(values.get('mod_engine_music_last_entry_raw') or [])
        if last_raw:
            head = last_raw[0]
            if head & 1:
                decoded = None
                shape = '长串（本读数不解引用它的指针）'
            else:
                short_len = head >> 1
                decoded = last_raw[1:1 + short_len].decode('utf-8', errors='replace')
                shape = f'短串（长度 {short_len}）'
            print(f'  曲目表最后一条：编号 = {last_id}｜名字串 = {decoded!r}（{shape}）')
            if me_after and me_after != 0xFFFFFFFF:
                if decoded == 'paincialist':
                    print('     ✓ 名字读对了（= 模组 music.xml 的第二条）⇒ 「名字在条目 +0x08」成立'
                          '⇒ `GetMusicIdByName` 会命中 ⇒ 模组不会拿 `-1` 去 `Play`（那条会崩）。')
                elif decoded is None:
                    print('     · 长串：本条不是 `paincialist` 那种短名 —— 需要按指针再读一次'
                          '（多半是本体那条很长的曲目名）。')
                else:
                    print(f'     ⚠ 名字不是 `paincialist`（读到 {decoded!r}）⇒ 偏移可能又错了，'
                          '先别进局。')
        if me_cform == 0 or me_mform == 0:
            print('     ⚠ 有一侧两种口径都没涨 ⇒ 先看上面那两个串"指到哪里"：'
                  '若指到**模组自己的目录**，那问题不在路径口径，而在加载器的第二个参数'
                  '（引擎自己传的是真 `ModEntry*`，我们传 `nullptr`）。')

    print('=== 曲目名反查（批次 148：`Isaac.GetMusicIdByName`）===')
    mi_calls = first_u32(values, 'music_id_calls')
    mi_hits = first_u32(values, 'music_id_hits')
    mi_last = first_u32(values, 'music_id_last_result')
    mi_table = first_u32(values, 'music_id_table_count')
    mi_last_i = mi_last if mi_last < 0x80000000 else mi_last - 0x100000000
    mi_last_text = '（-1，没找到）' if mi_last_i < 0 else str(mi_last_i)
    mi_table_text = '读不到（不是"表空"）' if mi_table == 0xFFFFFFFF else str(mi_table)
    name_raw = words_to_bytes(values.get('music_id_last_name') or [])
    name_text = name_raw.split(b'\x00', 1)[0].decode('utf-8', errors='replace')
    print(f'  被调 {mi_calls} 次、命中 {mi_hits} 次；最后一次结果 = {mi_last_text}、'
          f'查询名 = {name_text!r}')
    print(f'  ★ 查表那一刻曲目表里有 {mi_table_text} 条'
          '（119 = 模组的 music.xml **没进引擎**；>119 = 进了 ⇒ 反查才有意义）')
    if mi_calls and mi_hits == 0 and mi_table == 0xFFFFFFFF:
        print('     ⇒ 曲目表整条链读不到 ⇒ 先看上面批次 148 那一段（`Manager+0x36068`）。')
    elif mi_calls and mi_hits == 0:
        print('     ⇒ 表读得到、名字却都没命中 ⇒ 要么模组的 track 名不在表里，'
              '要么 `kMusicEntryNameStringOffset` 这个偏移不对（看上面那段的条数有没有涨）。')

    print()
    print('=== 贴图桥（.pcx 缺失时内存转码）===')
    diag_words = values.get('image_pcx_diag') or []
    diag_raw = b''.join(w.to_bytes(8, 'little') for w in diag_words)
    if len(diag_raw) < 304:
        print('  （诊断结构体读不到或长度不足 ⇒ 运行时可能是旧构建）')
    else:
        import struct as _struct
        f = _struct.unpack_from('<12I', diag_raw, 0)
        last_req = diag_raw[48:176].split(b'\x00', 1)[0].decode('utf-8', errors='replace')
        last_fb = diag_raw[176:304].split(b'\x00', 1)[0].decode('utf-8', errors='replace')
        names = {0: 'inMemoryLoad', 1: 'inflateInit2', 2: 'inflate', 3: 'inflateEnd',
                 4: 'imageManagerLoadMemory', 5: '(不再校验:钩子目标)', 6: 'operatorDeleteArray',
                 7: 'operatorNewArray'}
        bad = [names[i] for i in range(8) if f[10] & (1 << i)] + \
              (['contentManager(GOT)'] if f[10] & (1 << 8) else [])
        print(f'  入口挂点被调用 {f[0]} 次（原函数成功 {f[1]}）｜合成 .pcx 路径 {f[2]} 条｜'
              f'进入兜底判定 {f[3]} 次')
        print(f'  兜底：记录未命中放弃 {f[4]}｜读到 .png {f[5]}｜缓存命中 {f[6]}｜'
              f'实际转码 {f[7]}（失败 {f[8]}）｜喂入成功 {f[9]}')
        # 2026-09-21：`pngOverrideWins`（老的 `reserved` 槽）=「模组的 PNG 顶掉了**本体已有**的
        # `.pcx`」次数 —— 用来在真机上确认"只带 PNG 的覆盖型模组"真的走了新路。
        print(f'  模组 PNG 顶掉本体 .pcx：{f[11]} 次')
        print(f'  依赖绑定掩码 = 0x{f[10]:x}' + (f' ⇒ 没过的是：{bad}' if bad else ' ⇒ 全部通过 ✓'))
        print(f'  最近请求路径 = {last_req!r}｜最近兜底路径 = {last_fb!r}')
        # ★★★ 270-perf（2026-10-02）：取证字段（**只往后加**，偏移见
        # `runtime/source/image_pcx_bridge_hook.cpp` 的 `ImagePcxDiagnostics`）。
        #   ① 268（在 `ImageManager::LoadImage` 中继里换参数）到底有没有执行；
        #   ② 兜底那 ~1 秒/张花在"读 `.png` / 转码 / 喂引擎"的哪一步。
        if IMAGE_PCX_DIAG_BYTES >= 736:
            g = _struct.unpack_from('<12I', diag_raw, 304)
            last_load = diag_raw[352:480].split(b'\x00', 1)[0].decode('utf-8', errors='replace')
            swap_from = diag_raw[480:608].split(b'\x00', 1)[0].decode('utf-8', errors='replace')
            swap_to = diag_raw[608:736].split(b'\x00', 1)[0].decode('utf-8', errors='replace')
            print(f'  `ImagePcx::Load` 中继被调用 {g[0]} 次；'
                  f'`ImageManager::LoadImage` 中继收到的 `.pcx` 实参 {g[1]} 次｜'
                  f'★ 真换参数 {g[2]} 次（★ 280 起**应恒 0**：268 的换参数已撤）')
            print(f'  最近 LoadImage 实参 = {last_load!r}')
            print(f'  最近换参数 = {swap_from!r} → {swap_to!r}')
            if g[3] > 0:
                print(f'  兜底分段计时（{g[3]} 次转码，单位 ms；累计 / 单次最大）：'
                      f'读 {g[4] / 1000:.1f}/{g[5] / 1000:.1f}｜'
                      f'转码 {g[6] / 1000:.1f}/{g[7] / 1000:.1f}｜'
                      f'喂引擎 {g[8] / 1000:.1f}/{g[9] / 1000:.1f}｜'
                      f'★ 整条兜底 {g[10] / 1000:.1f}/{g[11] / 1000:.1f}')
                print(f'    ⇒ 单次最大那条里：读 {g[5] / 1000:.1f} + 转 {g[7] / 1000:.1f} + '
                      f'喂 {g[9] / 1000:.1f} = {(g[5] + g[7] + g[9]) / 1000:.1f} ms，'
                      f'兜底自身 {(g[11] - g[5] - g[7] - g[9]) / 1000:.1f} ms')
            else:
                print('  兜底分段计时：本会话一次转码都没发生')
        else:
            print(f'  （本构建没有 270-perf 的取证字段：本构建结构体共 {IMAGE_PCX_DIAG_BYTES} 字节，需要 736）')
        # ★★★ 271-perf（2026-10-02）：`Font::Load` 窗口归属 + 文件调用标定。
        # 回答"`Font::Load` 那 ~1 秒花在谁的代码里"：窗口内我们自己的图像层占多少、
        # 以及"一次文件调用值多少微秒"（同一文件上"整块读 vs 10 字节小读"的 A/B）。
        if IMAGE_PCX_DIAG_BYTES >= 800:
            h = _struct.unpack_from('<16I', diag_raw, 736)
            print('  ── 271：Font::Load 窗口归属 + 文件调用标定 ──')
            if h[0] > 0:
                print(f'    Font:Load 窗口 {h[0]} 次｜累计 {h[1] / 1000:.1f} ms｜单次最长 {h[2] / 1000:.1f} ms'
                      f'（平均 {h[1] / max(h[0], 1) / 1000:.1f} ms）')
                print(f'    窗口内：ImageManager::LoadImage 中继 {h[3]} 次 / 引擎里花 {h[4] / 1000:.1f} ms｜'
                      f'ImagePcx::Load 中继 {h[5]} 次 / 引擎里花 {h[6] / 1000:.1f} ms')
                print(f'    ⇒ 其中花在**引擎自己的代码**（`original(...)`）里的是 {((h[4] + h[6]) / 1000):.1f} ms，'
                      f'窗口内其余（我们这侧的胶水 + 引擎的解析/建对象/缓存）{((h[1] - h[4] - h[6]) / 1000):.1f} ms')
                print(f'    最近一次字体：字形数 = {h[7]}｜字形块大小/10 = {h[8]}'
                      f'（20 字节/字形 ⇒ 约 {h[8] * 10} 字节的字形数据）')
            else:
                print('    Font:Load 窗口：一次都没开过（本会话还没调过 Font:Load）')
            if h[9] == 1:
                per_open = h[11] / max(h[10], 1)
                per_read = h[13] / max(h[12], 1)
                print(f'    文件调用标定（文件 {h[14]} 字节）：'
                      f'开+关 {h[10]} 次 = {h[11] / 1000:.1f} ms（每次 {per_open:.1f} µs）｜'
                      f'10 字节读 {h[12]} 次 = {h[13] / 1000:.1f} ms（每次 {per_read:.1f} µs）')
                print(f'    ★ 判读：若"每次小读"是几十微秒量级，那么"上万次小读"就足以吃掉 1 秒；'
                      f'若是亚微秒，则文件调用不是那 1 秒的来源。')
            elif h[9] == 2:
                print('    文件调用标定：**跑失败**（绑定不全或打不开文件）')
            else:
                print('    文件调用标定：还没跑（本会话还没走到过贴图兜底）')
        elif IMAGE_PCX_DIAG_BYTES >= 736:
            print(f'  （本构建没有 271 的窗口字段：本构建结构体共 {IMAGE_PCX_DIAG_BYTES} 字节，需要 800）')
        # ★★★ 272-perf（2026-10-02）：修法计数 —— 模组自带的 `.png` 有多少次被改道去走我们的转码路。
        if IMAGE_PCX_DIAG_BYTES >= 824:
            j = _struct.unpack_from('<6I', diag_raw, 800)
            print('  ── 272：模组 `.png` 改道（修法）──')
            print(f'    `ImageManager::LoadImage` 收到 `.png` 实参 {j[0]} 次｜'
                  f'★ 改道成功 {j[1]} 次｜不是模组文件 {j[2]}｜格式不支持原样放行 {j[3]}｜'
                  f'改道自身开销（276 起含"真转一遍"）{j[4] / 1000:.1f} ms｜绑定不全没跑起来 {j[5]}')
            if j[5] > 0:
                print(f'    ⚠ 有 {j[5]} 次因为"绑定不全"直接放行了 —— 这一条有值就说明改道根本没生效'
                      f'（272 就是栽在这上面：getMountedFilePath 那个字段从来没被填过，要用 Original<> 跳板）。')
            if j[0] > 0:
                print(f'    ⇒ 效果对照：若改道生效，上面那段"窗口内 ImageManager::LoadImage 花在引擎里的时间"'
                      f'应从 ~18000 ms 掉到接近 0（改道后走的是我们那条 3~7 ms 的路）。')
        elif IMAGE_PCX_DIAG_BYTES >= 800:
            print(f'  （本构建没有 272 的改道字段：本构建结构体共 {IMAGE_PCX_DIAG_BYTES} 字节，需要 824）')
        # ★★★ 276-perf（2026-10-02）：把改道做成"**绝不留下空页图**"（273 真机崩溃之后重做）。
        #   本批的硬判据就两条：`feedFailures`（喂引擎被拒）与 `pngNativeRetry`（改道后没拿到图）
        #   **必须都是 0**；`pngRouted` 应 ≈ 40。
        if IMAGE_PCX_DIAG_BYTES >= 856:
            k = _struct.unpack_from('<8I', diag_raw, 824)
            print('  ── 276：改道前的"真转一遍" + 交付保底（重做版）──')
            print(f'    拒绝改道：解码尺寸超上限 {k[0]}｜真转一遍失败 {k[1]}｜格式接不了 {j[3]}｜'
                  f'不是模组文件 {j[2]}｜绑定不全 {j[5]}')
            if k[6] + k[7] > 0:
                print(f'    改道前的真转码耗时：累计 {k[5] / 1000:.1f} ms / 单次最大 {k[6] / 1000:.1f} ms'
                      f'（这两笔就是我们替引擎省下来的钱 —— 引擎自己解 PNG 平均 456 ms/次）')
            else:
                print('    改道前的真转码：一次都没发生（说明一次都没走到"可以改道"那一步）')
            print(f'    ★ 交付：喂引擎被拒 {k[2]} 次｜改道后没拿到图退回原生 PNG {k[3]} 次'
                  f'（其中救回 {k[4]} 次）')
            if k[2] == 0 and k[3] == 0:
                print('    ⇒ 两条都是 0：改道**每一张都交付成功**，没有留下空页图'
                      '（这是本批的硬判据）。')
            else:
                print('    ⚠ 有交付失败 —— "喂引擎被拒"有值说明引擎不收这块 PCX 字节'
                      '（273 的崩因最可能就是这条）；"退回原生 PNG"有值说明改道这一步本身有问题。'
                      '这两条一有值就必须先查清再谈提速。')
        elif IMAGE_PCX_DIAG_BYTES >= 824:
            print(f'  （本构建没有 276 的字段：本构建结构体共 {IMAGE_PCX_DIAG_BYTES} 字节，需要 856）')
        # ★★★ 277-perf（2026-10-02）：276 上卡读数换来的两条修正 ——
        #   ① 合成路径改用**虚拟路径**（引擎的挂载解析只认相对路径，喂它 `rom:/…` 会直接失败）；
        #   ② 把挂载解析中继里那几个**静默返回空**的分支做成计数（276 就是栽在 `mountPngMiss` 上）。
        if IMAGE_PCX_DIAG_BYTES >= 888:
            m = _struct.unpack_from('<8I', diag_raw, 856)
            print('  ── 277：合成路径改用"虚拟路径" + 中继静默分支的计数 ──')
            print(f'    收到本来就是绝对路径的 `.png` 实参（不改道）{m[0]} 次｜'
                  f'真转失败细分：读不到 {m[1]} / 转码失败 {m[2]}')
            print(f'    挂载解析中继：收到 `.pcx` 请求 {m[3]} 次｜其中补位成功 {m[4]}｜'
                  f'问 `.png` 也没问到 {m[5]}｜模组自带 `.pcx` 原样交回 {m[6]}')
            # ★ 277 上卡读数（2026-10-02 16:10）后的口径更正：`mountPngMiss` 是一个**大漏斗**——
            #   引擎会对大量**根本不存在的 `.pcx`**（各种贴图探测）问路，那些既没有 `.pcx` 也没有同名 `.png`
            #   ⇒ 全部计在这里（实测一局 1873 次，而改道 60 张**全部**补位成功、`pngNativeRetry` = 0）。
            #   ⇒ **它不适合当"我们这侧有没有出错"的判据**；判据仍然是 `pngNativeRetry`（= 0 就说明每张都送到了）。
            print('    ★ 口径：`问 .png 也没问到` 是**常规未命中**（引擎会探很多不存在的 `.pcx`），'
                  '不是故障信号；')
            print('      我们这侧"每张都送到"的判据看上面 276 段的 `pngNativeRetry`（必须为 0），'
                  '这里的补位成功数应当 **明显大于 30**（原有模组贴图那条路就是 30）。')
            if m[4] <= 30 and m[3] > 30:
                print('    ⚠ 补位成功没有涨过 30 —— 说明"改道交给引擎的路径"一条都没被解析到。')
        elif IMAGE_PCX_DIAG_BYTES >= 856:
            print(f'  （本构建没有 277 的字段：本构建结构体共 {IMAGE_PCX_DIAG_BYTES} 字节，需要 888）')
        # ★★★ 279-perf（2026-10-02）：**只改道大图** —— 修"开着 visible tinted rocks 时所有石头隐形"。
        #   原因：引擎里所有 `.anm2` 的精灵表都写成 `.png`（石头表 / EID 的图标表 / GoodTrip 的精灵表…），
        #   276 的"模组 `.png` 全改道"会把这些小精灵表也变成 `ImagePcx`，而 anm2 那条取表的路认不下 ⇒ 表变空。
        #   收益本来全在大图（2048×2048 的字体页图），小表改道几乎零收益 ⇒ 加像素数下限。
        if IMAGE_PCX_DIAG_BYTES >= 896:
            o = _struct.unpack_from('<2I', diag_raw, 888)
            print('  ── 279：只改道大图（小精灵表原样放行给引擎）──')
            print(f'    因"太小"被放行的次数 {o[0]}｜最近一张被放行的像素数 = {o[1]}'
                  f'（阈值 {1 << 20}；字体页图 2048×2048 = 4194304）')
            if o[0] > 0:
                print('    ⇒ 有值说明**小精灵表确实被放行给引擎自己解**了（这正是本批要的：anm2 的表回到 ImagePng）。')
        elif IMAGE_PCX_DIAG_BYTES >= 888:
            print(f'  （本构建没有 279 的字段：本构建结构体共 {IMAGE_PCX_DIAG_BYTES} 字节，需要 896）')
        # ★★★ 批次 351（2026-10-04）：**非 `.pcx` 的挂载查询** —— `.anm2` 这类"文件本身"走的就是这条路。
        #   取证目标：minimapi 的 `IsBadLoad()` 为什么判坏（它拿 `Sprite:Load("gfx/ui/minimap1.anm2")`
        #   数帧，期望读到它自己那份 1 帧的，真机却拿到 13 帧的本体那份 ⇒ 打两行红字、不画地图）。
        #   三个量分别回答：① 非 `.pcx` 查询有没有发生；② `.anm2` 几次；③ 引擎答的是不是模组目录。
        if IMAGE_PCX_DIAG_BYTES >= 1196 and len(diag_raw) >= 1196:
            p = _struct.unpack_from('<3I', diag_raw, 896)
            last_anm2_path = diag_raw[908:1036].split(b'\x00', 1)[0].decode('utf-8', errors='replace')
            last_anm2_answer = diag_raw[1036:1196].split(b'\x00', 1)[0].decode('utf-8', errors='replace')
            print('  ── 351：非 `.pcx` 的挂载查询（`.anm2` 到底"谁覆盖谁"，看这一段）──')
            print(f'    非 `.pcx` 查询 {p[0]} 次｜其中 `.anm2` {p[1]} 次｜'
                  f'★ 引擎答出**模组目录**下路径 {p[2]} 次（= 覆盖生效）')
            print(f'    最近一条 `.anm2` 查询 = {last_anm2_path!r}')
            print(f'    引擎对它的回答     = {last_anm2_answer!r}')
            if p[1] == 0:
                print('    ⇒ `.anm2` 一次都没走这条中继 ⇒ **这条不是它的解析路**（靶子错了，别在优先级上耗）。')
            else:
                print(f'    ⚠ **本诊断的自动判读到此为止**：全局计数只能说"这条路能答出模组目录"'
                      f'（{p[2]}/{p[1]}），**它判不了"某一条具体路径归谁"** —— '
                      f'模组独有的路径必然答模组、本体独有的路径必然答本体，这两种都计在里面。')
                print('    ⇒ 要判"共享路径"（两边都有的）归谁，得看上面那两行"最近一条"；'
                      '并且**要拿那条路径去卡上核对"模组是不是也带了这个文件"**。')
                print('    ⚠ 教训（2026-10-04 本批实测）：判据只用全局计数会**下错结论** —— '
                      '本批第一版就是这么写的，读数里"最近一条"恰好是**本体独有**的文件（模组没带），'
                      '于是"答 rp_patch"完全正常、什么都证明不了。')
        elif IMAGE_PCX_DIAG_BYTES >= 896 and len(diag_raw) < 1196:
            if IMAGE_PCX_DIAG_BYTES >= 1196:
                print(f'  （这份读数里没有 351 的字段：原始读数只有 {len(diag_raw)} 字节、需要 1196'
                      f' —— 多半是拿旧读数件在新构建上回放）')
            else:
                print(f'  （本构建没有 351 的"非 .pcx 查询"字段：本构建结构体共 {IMAGE_PCX_DIAG_BYTES} 字节，'
                      f'需要 1196）')
        # ★★★ 批次 352（2026-10-04）：**按路径**回答"这条共享路径归谁"（351 的全局计数答不出来）。
        #   判读顺序（这张表就是结论表，照着念即可）：
        #     ① `主动探测` 那一行的"引擎解析到哪" —— 它由**我们**问，所以最可信：
        #        答模组目录 ⇒ 解析层没问题 ⇒ 问题在"缓存/时序"（minimapi 拿到的是早先缓存的那份）；
        #        答本体     ⇒ 解析层就答错了 ⇒ 修路径解析的优先级。
        #     ② `minimapi 自己来问` 那一行 —— 次数 0 表示它**压根不走这条中继**（同理，去查缓存）。
        if IMAGE_PCX_DIAG_BYTES < 2100:
            print(f'  （本构建没有 352 的"按路径/主动探测"字段：本构建结构体共 {IMAGE_PCX_DIAG_BYTES} 字节，'
                  f'需要 2100）')
        elif len(diag_raw) < 2100:
            print(f'  （这份读数里没有 352 的字段：原始读数只有 {len(diag_raw)} 字节、需要 2100'
                  f' —— 多半是拿旧读数件在新构建上回放）')
        else:
            def _diag_str(start, length):
                return diag_raw[start:start + length].split(b'\x00', 1)[0].decode('utf-8',
                                                                                 errors='replace')

            o352 = _struct.unpack_from('<6I', diag_raw, 1196)
            mm1_query = _diag_str(1220, 128)
            mm1_answer = _diag_str(1348, 160)
            mm2_query = _diag_str(1508, 128)
            mm2_answer = _diag_str(1636, 160)
            probe = _struct.unpack_from('<3I', diag_raw, 1796)
            probe_query = _diag_str(1808, 128)
            probe_answer = _diag_str(1936, 160)
            print('  ── 352：按路径取证 —— "这条共享路径归谁"，看这一段（不是全局计数）──')
            print(f'    非 `.pcx` 总账：答模组目录 {o352[0]} 次｜答非模组（本体或空）{o352[1]} 次')
            print(f'    ★ 主动探测（我们自己问 {probe_query!r}）：跑过 {probe[0]} 次｜'
                  f'最近一次答模组目录 = {"是" if probe[1] else "否"}'
                  f'｜第一次 = {"是" if probe[2] else "否"}')
            print(f'      探测得到的回答 = {probe_answer!r}')
            print(f'    minimapi 自己来问 `minimap1.anm2`：{o352[2]} 次（答模组目录 {o352[3]} 次）')
            if o352[2] > 0:
                print(f'      最近一条查询 = {mm1_query!r}')
                print(f'      引擎的回答   = {mm1_answer!r}')
            print(f'    minimapi 自己来问 `minimap2.anm2`：{o352[4]} 次（答模组目录 {o352[5]} 次）')
            if o352[4] > 0:
                print(f'      最近一条查询 = {mm2_query!r}')
                print(f'      引擎的回答   = {mm2_answer!r}')
            if probe[0] == 0:
                print('    ⇒ 主动探测一次都没跑（本会话非 `.pcx` 查询没过 1 次？）—— 这份读数说明不了归属。')
            elif probe[2] != probe[1]:
                print('    ⚠ 第一次与最近一次的探测结论**不一致** ⇒ 引擎对这条路径的解析结果**会变**'
                      '（缓存 / 挂载时序在起作用），下面按"最近一次"判。')
            if probe[1]:
                print('    ⇒ **解析层是好的**（引擎此刻把这条共享路径解析到了模组目录）'
                      '⇒ minimapi 仍拿到本体那份的话，问题在**缓存/时序**那一侧。')
            else:
                print('    ⇒ **解析层答的是本体那份**（模组自带的那份没赢）⇒ 这是"覆盖没生效"的直接证据，'
                      '修法应落在**路径解析的优先级**上。')
            if o352[2] == 0:
                print('    ⇒ minimapi **一次都没来问过** `minimap1.anm2` ⇒ 它的加载根本不走这条中继'
                      '（先去看别处：缓存 / 它自己的加载路），不要再在这条中继上加力气。')
        # ★★★ 批次 353（2026-10-04）：**回答"甲' 还是 乙'"** —— 352 只说明"没赢"，说明不了为什么。
        #   两种成因的修法完全不同：甲' = 解析顺序/优先级；乙' = 解析结果被**记住**了
        #   （那条路径在模组挂载之前就被本体用过）。分开它们的办法 = 问**一组性质不同的路径**。
        if IMAGE_PCX_DIAG_BYTES < 4896:
            print(f'  （本构建没有 353 的"模组名单/探测组/环形历史"字段：本构建结构体共 '
                  f'{IMAGE_PCX_DIAG_BYTES} 字节，需要 4896）')
        elif len(diag_raw) < 4896:
            print(f'  （这份读数里没有 353 的字段：原始读数只有 {len(diag_raw)} 字节、需要 4896'
                  f' —— 多半是拿旧读数件在新构建上回放）')
        else:
            def _diag_str353(start, length):
                return diag_raw[start:start + length].split(b'\x00', 1)[0].decode('utf-8',
                                                                                  errors='replace')

            print('  ── 353：探测一组路径 + 模组名单 + 最近 6 条查询（分"甲\'/乙\'"用这一段）──')
            mount_count = _struct.unpack_from('<I', diag_raw, 2100)[0]
            names = [_diag_str353(2104 + 48 * i, 48) for i in range(12)]
            shown = [n for n in names if n]
            print(f'    我们登记过的模组目录：{mount_count} 个'
                  f'{"（名单只留前 12 个）" if mount_count > 12 else ""}')
            for i, name in enumerate(shown):
                print(f'      [{i}] {name}')
            if mount_count == 0:
                print('    ⚠ **一个都没登记** ⇒ 模组内容挂载根本没走到这一步，先查那条路（别谈优先级）。'
                      '另外：本行也可能因为"读取时还没走到挂载那一步"而为零，看计数即可。')
            if mount_count > 12:
                print(f'    ⚠ 登记数 {mount_count} > 名单容量 12 ⇒ 名单被截断（只留了前 12 个）。')

            ring_count = _struct.unpack_from('<I', diag_raw, 2680)[0]
            print(f'    最近 6 条非 `.pcx` 查询（累计 {ring_count} 次，环形；按写入顺序印）：')
            slots = min(6, ring_count)
            base_slot = ring_count - slots
            for i in range(slots):
                slot = (base_slot + i) % 6
                rp = _diag_str353(2684 + 88 * slot, 88)
                ra = _diag_str353(3212 + 120 * slot, 120)
                print(f'      {rp!r} ⇒ {ra!r}')

            print('    ★ 四条探测路径（每条各自留痕；【正对照】= 模组独有，【分层】= 共享但本体在哪一层）：')
            probes = []
            for i in range(4):
                off = 3932 + 240 * i
                runs, mod_wins, last_win, first_win = _struct.unpack_from('<4I', diag_raw, off)
                query = _diag_str353(off + 16, 64)
                answer = _diag_str353(off + 80, 160)
                probes.append((query, runs, mod_wins, last_win, first_win, answer))
                print(f'      [{i}] {query!r}：跑过 {runs} 次｜答模组 {mod_wins} 次'
                      f'｜最近一次答模组={"是" if last_win else "否"}'
                      f'｜第一次={"是" if first_win else "否"}'
                      f'{"（★ 两次不一致 ⇒ 结果会变）" if runs > 1 and first_win != last_win else ""}')
                print(f'          回答 = {answer!r}')
            # ★ 判读表**随探测路径表一起变** —— 具体判读在下面 354 那一段里做（那里知道当前表是什么）。
            print('    （这几条的判读见下面"354"那一段；探测路径表每次换，别在这里硬编码结论。）')
        # ★★★ 批次 354（2026-10-04）：**挂载成败 + 换键形状的探测**。
        #   353 的读数把范围缩到"模组独有的路径在 `GetMountedFilePath` 上直接答空"，
        #   于是要分清两件事：① 挂载本身失败？ ② 挂载成功但解析器看不到（键形状/层级不对）？
        _STATUS_CODES = {0: 'Ok', 1: 'InvalidArgument', 2: 'InvalidState', 3: 'Unsupported',
                         4: 'NotFound', 5: 'CapacityExceeded', 6: 'IoFailure', 7: 'Corrupted',
                         8: 'Rejected'}
        _LEAF_NAMES = ['resources', 'resources/gfx', 'content', 'content/gfx',
                       'resources-dlc3', 'resources-dlc3/gfx']
        if IMAGE_PCX_DIAG_BYTES < 5000:
            print(f'  （本构建没有 354 的"挂载成败"字段：本构建结构体共 {IMAGE_PCX_DIAG_BYTES} 字节，'
                  f'需要 5000）')
        elif len(diag_raw) < 5000:
            print(f'  （这份读数里没有 354 的字段：原始读数只有 {len(diag_raw)} 字节、需要 5000'
                  f' —— 多半是拿旧读数件在新构建上回放）')
        else:
            def _diag_str354(start, length):
                return diag_raw[start:start + length].split(b'\x00', 1)[0].decode('utf-8',
                                                                                  errors='replace')

            mount_count = _struct.unpack_from('<I', diag_raw, 2100)[0]
            print('  ── 354：挂载成败（`RegisterMod` 的返回值 + 失败在哪个叶子）＋ 换键形状的探测 ──')
            print(f'    登记尝试 {mount_count} 次（★ 这是"试过几次"，不是"成功几个"）：')
            for i in range(min(12, mount_count)):
                name = _diag_str354(2104 + 48 * i, 48)
                code = _struct.unpack_from('<I', diag_raw, 4896 + 4 * i)[0]
                leaf = _struct.unpack_from('<I', diag_raw, 4944 + 4 * i)[0]
                verdict = '成功' if code == 0 else f'**失败（{_STATUS_CODES.get(code, code)}）**'
                if code == 0:
                    leaf_text = '—'
                elif leaf < len(_LEAF_NAMES):
                    leaf_text = f'第 {leaf} 个叶子 = `{_LEAF_NAMES[leaf]}`'
                else:
                    leaf_text = f'{leaf}（不在叶子表里）'
                print(f'      [{i}] {name} ⇒ {verdict}｜失败叶子 = {leaf_text}')
            ok_count = sum(1 for i in range(min(12, mount_count))
                           if _struct.unpack_from('<I', diag_raw, 4896 + 4 * i)[0] == 0)
            print(f'    ⇒ 成功 {ok_count} 个 / 尝试 {mount_count} 个')
            print('    探测（★ 换过键形状：叶子相对 vs 应用根相对）：')
            probes354 = []
            for i in range(4):
                off = 3932 + 240 * i
                runs, mod_wins, last_win, first_win = _struct.unpack_from('<4I', diag_raw, off)
                query = _diag_str354(off + 16, 64)
                answer = _diag_str354(off + 80, 160)
                probes354.append((query, runs, mod_wins, last_win, first_win, answer))
                print(f'      [{i}] {query!r}')
                print(f'          跑过 {runs} 次｜答模组 {mod_wins} 次｜回答 = {answer!r}')
            app_root_hits = [p for p in probes354[2:] if p[2] > 0]
            leaf_only_hits = [p for p in probes354[:2] if p[2] > 0]
            print('    判读：')
            if app_root_hits:
                print('      ⇒ **模组文件能被这个解析器找到**（应用根相对形式答出了模组目录）'
                      '⇒ 问题在"**叶子相对**这种键形状 / 我们的挂载层级"，不是"模组树不可见"。'
                      '下一刀：让叶子相对查询也能落到模组那一层。')
            elif leaf_only_hits:
                print('      ⇒ 叶子相对能命中、应用根相对反而不能 ⇒ 键形状的口径与我们设想相反，'
                      '按实际命中的那种形式设计修法。')
            else:
                print('      ⇒ **三条模组路径全空** ⇒ 这个解析器**看不到模组树**。'
                      '先看上面的"挂载成败"：若全成功 ⇒ 是挂载之后被清掉/或该 API 不收模组挂载点；'
                      '若有失败 ⇒ 从失败的那个叶子查起。')
        # ★★★ 批次 356（2026-10-04）：**"回声"与"真覆盖"分开** + **刚挂完的检查点**（时间轴切一刀）。
        if IMAGE_PCX_DIAG_BYTES < 5176:
            print(f'  （本构建没有 356 的"排除回声/刚挂完检查点"字段：本构建结构体共 '
                  f'{IMAGE_PCX_DIAG_BYTES} 字节，需要 5176）')
        elif len(diag_raw) < 5176:
            print(f'  （这份读数里没有 356 的字段：原始读数只有 {len(diag_raw)} 字节、需要 5176'
                  f' —— 多半是拿旧读数件在新构建上回放）')
        else:
            def _diag_str356(start, length):
                return diag_raw[start:start + length].split(b'\x00', 1)[0].decode('utf-8',
                                                                                  errors='replace')

            real_wins, probe_runs, probe_win = _struct.unpack_from('<3I', diag_raw, 5000)
            probe_answer = _diag_str356(5012, 160)
            total_wins = _struct.unpack_from('<I', diag_raw, 1196)[0]
            print('  ── 356：回声 vs 真覆盖 ＋ 刚挂完的检查点（把时间轴切一刀）──')
            print(f'    答出模组目录 共 {total_wins} 次｜其中"**查询本身带 `rom:/isaac_mods/` 前缀**"以外的 = {real_wins} 次')
            # ★ 2026-10-04 实测更正（我自己的谓词写错了，必须写在读数旁边，免得后人照着它下结论）：
            #   实际查询用的是**应用根相对**形式（`isaac_mods/…`，**不带** `rom:/`）⇒ 全都被算成
            #   "不是模组路径"⇒ 这个数字到现在还是**分不开"回声"与"真覆盖"**，**不要拿它下结论**。
            print('      ⚠ **这一格目前没有判别力（谓词写错了）**：实际查询用的是"应用根相对"形式'
                  '（`isaac_mods/…`，不带 `rom:/`）⇒ 全被算成"非模组路径"。要区分"回声"与"真覆盖"，'
                  '谓词应改成"**回答是否恰好等于把查询串加上 `rom:/`**"。**别用这一格下结论。**')
            print(f'    ★ 刚挂完那一刻的检查点（问 `sprite/gt/gt_ui.anm2`，叶子相对）：跑过 {probe_runs} 次'
                  f'｜答模组目录 = {"是" if probe_win else "否"}')
            print(f'      回答 = {probe_answer!r}')
            if probe_runs == 0:
                print('      ⇒ 检查点没跑（入口中继那时还没装上？）⇒ 这一格说明不了时间轴，如实记 0。')
            elif probe_win:
                print('      ⇒ **挂载当时叶子相对就能命中** ⇒ 后来问不到 ⇒ **中途被清掉/被换掉**了'
                      '（去找那个清理点，别再改键形状）。')
            else:
                print('      ⇒ **挂载当时叶子相对就命中不了** ⇒ 不是"后来被清掉"，而是**这种键形状'
                      '从来就不在表里** ⇒ 修法落在"让模组挂载点的键能被叶子相对地问到"。')
        # ★★★ 批次 357（2026-10-04）：**挂载点什么时候没的（时间轴）+ 重挂试过没有**。
        if IMAGE_PCX_DIAG_BYTES < 5368:
            print(f'  （本构建没有 357 的"时间轴位图/重挂试验"字段：本构建结构体共 '
                  f'{IMAGE_PCX_DIAG_BYTES} 字节，需要 5368）')
        elif len(diag_raw) < 5368:
            print(f'  （这份读数里没有 357 的字段：原始读数只有 {len(diag_raw)} 字节、需要 5368'
                  f' —— 多半是拿旧读数件在新构建上回放）')
        else:
            def _diag_str357(start, length):
                return diag_raw[start:start + length].split(b'\x00', 1)[0].decode('utf-8',
                                                                                  errors='replace')

            o357 = _struct.unpack_from('<6I', diag_raw, 5176)
            bitmap, runs, relay_ok, remount_tried, remount_code, remount_win = o357
            remount_answer = _diag_str357(5200, 160)
            names = ['挂载收尾', '内容步收尾', '第一个 update 回调', '第一次非 .pcx 查询']
            print('  ── 357：挂载点什么时候没的（时间轴）＋ 重挂试过没有 ──')
            print(f'    检查点跑了 {runs} 次｜位图 = 0b{bitmap:04b}（同一个查询：'
                  f'`sprite/gt/gt_ui.anm2`，叶子相对）')
            for i, name in enumerate(names):
                print(f'      bit{i} {name:<18s} = {"★ 命中模组" if (bitmap >> i) & 1 else "答空"}')
            if runs == 0:
                print('    ⚠ 检查点一次都没跑 ⇒ 时间轴这几格说明不了任何事（先查为什么没跑）。')
            else:
                lost = next((i for i in range(len(names)) if not (bitmap >> i) & 1), None)
                if lost is None:
                    print('    ⇒ 四个点**全都命中** ⇒ 到"第一次非 .pcx 查询"为止挂载点都还在；'
                          '那 354/356 里"游戏里问不到"就发生在更晚的点（或与查询形式有关）。')
                elif lost == 0:
                    print('    ⇒ **连挂载收尾那一刻就没命中** ⇒ 与 356 的读数矛盾（356 说命中了）'
                          '⇒ 先怀疑这次挂载没成功或读的是另一版构建。')
                else:
                    print(f'    ⇒ **消失点在 "{names[lost-1]}" 与 "{names[lost]}" 之间** '
                          f'⇒ 找那一段里谁清的表（`RebuildContentMountPoints()` 开头就是 '
                          f'`ClearMountPoints(false)`）。')
            print(f'    重建挂载点中继：**装上没有 = {"是" if relay_ok else "否"}**'
                  f'（"跑过 0 次"与"没装上"是两件事）')
            if not relay_ok:
                print('      ⇒ **没装上** ⇒ 引擎一旦重建挂载点表，模组挂载点就再也不会被恢复 —— '
                      '这与"挂载点中途消失"完全吻合，是**首要嫌疑**。')
            print(f'    重挂试验：{"试过" if remount_tried else "**没试过**"}'
                  f'｜`RemountAll` 返回 = {remount_code}（0 = Ok）'
                  f'｜重挂后再问同一句 = {"★ 命中模组" if remount_win else "仍然答空"}')
            print(f'      重挂后的回答 = {remount_answer!r}')
            if not remount_tried:
                print('      ⇒ 还没到那一帧（第 300 个 update 回调），或者游戏没跑到那么久。')
            elif remount_win:
                print('      ⇒ ★★ **重挂能救回来** ⇒ 修法方向确定：**在引擎自己初始化内容表之后把模组'
                      '挂载点补回去**（而不是改键形状、也不是改路径解析）。')
            else:
                print('      ⇒ 重挂没救回来 ⇒ 要么 `RemountAll` 没真的把表补上（看返回码/挂载成败），'
                      '要么之后又被清了一次 ⇒ 用上面的时间轴定位。')
        # ★★★ 批次 358（2026-10-04）：重建挂载点中继**卡在哪一条**（357 已证它没装上）。
        _RELAY_FAILURES = {
            0: '没有失败（装上且发布了）',
            1: '前置守卫：空指针 / base 为 0 / buildId 不符 / 长度越界',
            2: '范围与对齐：不在模块内、不在可执行窗口、未对齐',
            3: '★ **目标处字节对不上**（入口那条分支 或 其后 12 字节）',
            4: '★ **代码洞桩字节对不上**',
            5: '桩长度超出本地缓冲',
            6: '发布失败：槽 / 回调非法（0 或未对齐）',
            7: '发布失败：**槽非空**（已经有人占着）',
            8: '发布失败：写进去读回来不一致',
        }
        if IMAGE_PCX_DIAG_BYTES < 5408:
            print(f'  （本构建没有 358 的"重建中继失败码/现场字节"字段：本构建结构体共 '
                  f'{IMAGE_PCX_DIAG_BYTES} 字节，需要 5408）')
        elif len(diag_raw) < 5408:
            print(f'  （这份读数里没有 358 的字段：原始读数只有 {len(diag_raw)} 字节、需要 5408'
                  f' —— 多半是拿旧读数件在新构建上回放）')
        else:
            code = _struct.unpack_from('<I', diag_raw, 5368)[0]
            target_hex = diag_raw[5372:5388].hex()
            stub_hex = diag_raw[5388:5404].hex()
            print('  ── 358：重建挂载点中继"卡在哪一条"（★ 如实说：这一整段测的是**死代码**）──')
            print(f'    失败码 = {code}：{_RELAY_FAILURES.get(code, "未知")}')
            print(f'    目标处（游戏模块 0x3B36F4）实际 16 字节 = {target_hex}')
            print(f'    代码洞桩（0x68CFA0）实际 16 字节        = {stub_hex}')
            print(f'    期望：目标处前 4 字节 = `2b660b14`（一条 `b`，目标 0x68CFA0）'
                  f'｜此时实际前 4 字节 = {target_hex[:8]}')
            if code == 3 and target_hex[:8] != '2b660b14':
                print('    ⇒ **入口那条分支没打上** ⇒ 这套中继是"入口分支 + 零页桩"，分支不在就等于整套没装。'
                      '下一步：查那个 `nro_patches/…-rebuild-mount-points-relay.ips` 到底有没有上卡、'
                      '或者改用**已经证明可用的入口中继机制**去包这个函数（语义相同：先跑原函数、再重挂）。')
            elif code == 4:
                print('    ⇒ 分支在、但**桩字节不对** ⇒ 代码洞被别的东西占了或版本不匹配。')
            elif code == 2:
                print('    ⇒ 地址/映射这一步就过不去 ⇒ 多半是**目标偏移随版本变了**，要对着本机镜像重算。')
            elif code in (6, 7, 8):
                print('    ⇒ 校验全过、**只有发布那一步失败** ⇒ 槽的问题（被占/写不进），不是字节的问题。')
            elif code == 0:
                print('    ⇒ 装了 ⇒ 与 357 的"没装上"矛盾 ⇒ 先看这一版是不是把补丁也一起刷上卡了。')
            print('    ⚠ **这一整段的解释力有限**：挂点目录把 `RebuildMountPoints` 的后端定成 `EntryRelay`，'
                  '所以 `exlaunch_hook_adapter.cpp` 里那一支**永远不会被派到** ⇒ 这几格恒为 0/空。'
                  '要动它，请看下面 **359** 那一段（活的那条路）。')
        # ★★★ 批次 359（2026-10-04）：**活的那条路** —— 入口中继 + 我们那层包装的调用数。
        if IMAGE_PCX_DIAG_BYTES < 5424:
            print(f'  （本构建没有 359 的"入口中继结果/包装调用数"字段：本构建结构体共 '
                  f'{IMAGE_PCX_DIAG_BYTES} 字节，需要 5424）')
        elif len(diag_raw) < 5424:
            print(f'  （这份读数里没有 359 的字段：原始读数只有 {len(diag_raw)} 字节、需要 5424'
                  f' —— 多半是拿旧读数件在新构建上回放）')
        else:
            inst, fail, calls = _struct.unpack_from('<3I', diag_raw, 5408)
            print('  ── 359：重建挂载点中继 —— **活的那条路**（入口中继 + 包装调用数）──')
            print(f'    入口中继（`HookId::RebuildMountPoints`）装上没有 = {"是" if inst else "否"}'
                  f'｜失败码 = {fail}（0 = 成功）')
            print(f'    ★ 我们那层包装（先跑原函数、再重挂）被调用 = **{calls}** 次')
            if not inst:
                print('      ⇒ **入口中继没装上** ⇒ 引擎一旦重建挂载点表就没人补 ⇒ 与现象吻合。'
                      '下一步看失败码（`entry_relay` 的码表：1 地址/边界 2 入口字节不符 3 洞用尽 4 写完读回不一致 5 相对指令）。')
            elif calls == 0:
                print('      ⇒ 装了、但**一次都没被调到** ⇒ **引擎清空挂载点表根本不经过这个函数**')
                print('         ⇒ 在 `RebuildContentMountPoints` 身上挂钩子**永远救不了它**，'
                      '修法要换成"在清表之后、由一个我们控制的时机把模组挂载点补回去"。')
            else:
                print(f'      ⇒ 包装跑过 {calls} 次 ⇒ 引擎确实走这个函数清表；再看上面的'
                      f'「重建挂载点中继：跑过 N 次」是否为 0 —— 那说明"包装跑了但重挂动作没跑"。')
        # ★★★ 批次 360（2026-10-04）：**修法**（自愈补挂）的留痕 —— 这段正常时应该长什么样，写在下面。
        if IMAGE_PCX_DIAG_BYTES < 5440:
            print(f'  （本构建没有 360 的"自愈看门狗"字段：本构建结构体共 {IMAGE_PCX_DIAG_BYTES} 字节，'
                  f'需要 5440）')
        elif len(diag_raw) < 5440:
            print(f'  （这份读数里没有 360 的字段：原始读数只有 {len(diag_raw)} 字节、需要 5440'
                  f' —— 多半是拿旧读数件在新构建上回放）')
        else:
            checks, heals = _struct.unpack_from('<2I', diag_raw, 5424)
            print('  ── 360：**修法**（自愈补挂）—— 模组挂载点是否被维持住 ──')
            print(f'    看门狗检查 = **{checks}** 次｜发现"不在"并补挂 = **{heals}** 次')
            if checks == 0:
                print('      ⚠ 一次都没检查 ⇒ 主循环的 update 回调没跑到，或没走到挂载那一步（`mod_count` 为 0）。')
            elif heals == 0:
                print('      ⇒ 全程都没发现"不在" ⇒ 挂载点**一直有效**（若这与"354 段探测答本体/空"同时出现，'
                      '说明判据本身有问题，先查那一段）。')
            else:
                print(f'      ⇒ 补挂过 {heals} 次（配合上面的「重挂试验」那几格看补挂后是否命中）'
                      f'⇒ ★ 这就是本条链的修法生效现场。')
            print('    ★ 期望的正常形态：**检查 > 0 次 且 补挂 ≥ 1 次**，且 357 那一段的'
                  '「重挂后再问同一句」= **命中模组**。')
        # ★★★ 批次 361（2026-10-04）：**按时间量** —— 每格带"当时的模组数"，另加挂载后的那一对测量。
        if IMAGE_PCX_DIAG_BYTES < 5816:
            print(f'  （本构建没有 361 的"探测上下文/晚点试验"字段：本构建结构体共 '
                  f'{IMAGE_PCX_DIAG_BYTES} 字节，需要 5816）')
        elif len(diag_raw) < 5816:
            print(f'  （这份读数里没有 361 的字段：原始读数只有 {len(diag_raw)} 字节、需要 5816'
                  f' —— 多半是拿旧读数件在新构建上回放）')
        else:
            def _diag_str361(start, length):
                return diag_raw[start:start + length].split(b'\x00', 1)[0].decode('utf-8',
                                                                                  errors='replace')

            seq = _struct.unpack_from('<4I', diag_raw, 5440)
            modcount = _struct.unpack_from('<4I', diag_raw, 5456)
            trial_tick, before_win, after_win, modonly_win = _struct.unpack_from('<4I',
                                                                                 diag_raw, 5472)
            before_answer = _diag_str361(5488, 160)
            after_answer = _diag_str361(5648, 160)
            print('  ── 361：**按时间**看探测（每格带"当时的模组数"）＋ 挂载后的那一对测量 ──')
            print('    四条探测的上下文（`模组数 = 0` ⇒ **这次探测跑在挂载之前，不算数**）：')
            for i in range(4):
                off = 3932 + 240 * i
                query = diag_raw[off + 16:off + 80].split(b'\x00', 1)[0].decode('utf-8',
                                                                               errors='replace')
                verdict = '（模组数 0 ⇒ 忽略）' if modcount[i] == 0 else ''
                print(f'      [{i}] {query!r}：序号 {seq[i]}｜当时模组数 {modcount[i]} {verdict}')
            print('    ★ 挂载之后的晚点试验：')
            if trial_tick == 0:
                print('      ⇒ **没跑**（模组挂上之前就结束了？或 update 回调没走到 30 帧）。')
            else:
                print(f'      跑过｜重挂**前**共享路径答模组 = {"是" if before_win else "否"}'
                      f'｜重挂**后** = {"是" if after_win else "否"}'
                      f'｜模组独有路径（对照）= {"是" if modonly_win else "否"}')
                print(f'      重挂前回答 = {before_answer!r}')
                print(f'      重挂后回答 = {after_answer!r}')
                if not before_win and after_win:
                    print('      ⇒ ★★★ **病根 = 注册顺序**：模组挂载点被本体层（后注册的）压过；'
                          '**重挂一次就翻过来了** ⇒ 修法 = 在引擎初始化之后把模组挂载点补到最后。')
                elif before_win and after_win:
                    print('      ⇒ 共享路径本来就归模组 ⇒ **minimapi 的两行红字另有原因**'
                          '（它读的是别的东西/别的时机），别再查挂载了。')
                elif not before_win and not after_win:
                    print('      ⇒ 重挂也翻不过来 ⇒ 不是"注册顺序"能解释的 ⇒ 要去看解析本身'
                          '（例如 `rp_patch` 层根本不参与同名比较）。')
                else:
                    print('      ⇒ 重挂后**反而**不命中 ⇒ 重挂把某些东西弄乱了，先回退这一条。')
        # ★★★ 批次 411（2026-10-08）：PC 路径分隔符归一化次数（消费了 361 的一个占位槽，
        #   偏移 5808；**总大小仍是 5816、旧偏移一格没动**）。
        #   判据：选带 `\` 写路径的模组角色（如 Trinity 的 Peter）进局，这一格应 > 0；
        #   而且**卡上模组文件保持原样** —— 两者同时成立才说明修的是平台层，不是改模组。
        if len(diag_raw) >= 5812:
            sep_norm = _struct.unpack_from('<I', diag_raw, 5808)[0]
            print(f'  ── 411：PC 路径分隔符归一化（`\\` → `/`）{sep_norm} 次'
                  + ('（> 0 ⇒ 真的有一条模组路径是靠这一层才解析到的）' if sep_norm else
                     '（0 ⇒ 本会话没有带 `\\` 的路径进来过）')
                  + ' ──')
    binds = values.get('image_pcx_bindings') or []
    zero = sum(1 for v in binds if v == 0)
    print(f'  绑定指针：8 个里 {zero} 个为空')
    gm_entry = values.get('getmounted_entry') or []
    gm_hex = b''.join(w.to_bytes(8, 'little') for w in gm_entry[:2]).hex()
    print(f'  路径解析入口（游戏模块 0x4c2340）= {gm_hex}' +
          ('  ← 已是入口补丁 ★' if gm_hex.startswith('5000005800021fd6') else '  ← **不是**入口补丁'))
    entry = values.get('imagemanager_entry') or []
    got = b''.join(w.to_bytes(8, 'little') for w in entry[:2]).hex()
    if not entry:
        print('  游戏模块 LoadImage 入口 = 读不到')
    elif got.startswith('5000005800021fd6'):
        print(f'  游戏模块 LoadImage 入口 = {got} ← 已是我们的入口补丁 ★')
    else:
        print(f'  游戏模块 LoadImage 入口 = {got} ← **不是**入口补丁（应为 5000005800021fd6…）')

    print()
    print('=== C++ 异常抛出位置（L4 钩子隔离·甲案，批次 196）===')
    # 固定布局 `ThrowForensics`（`runtime/source/throw_forensics.cpp`）：throwCount(u32) +
    # reserved(u32) + lastThrowFrom(u64) + lastThrowType(u64) + firstThrowFrom(u64) = 4 个 8 字节字。
    # ★ 批次日 196 只把符号接进了读取列表、**漏了这一段打印** ⇒ 真机验收时"读得到却看不见"。
    tf_words = values.get('throw_forensics') or []
    tf_raw = b''.join(w.to_bytes(8, 'little') for w in tf_words)
    if len(tf_raw) < 32:
        print('  （读不到或长度不足 ⇒ 运行时可能是旧构建）')
    else:
        import struct as _struct
        tf_count = _struct.unpack_from('<I', tf_raw, 0)[0]
        tf_last = _struct.unpack_from('<Q', tf_raw, 8)[0]
        tf_first = _struct.unpack_from('<Q', tf_raw, 24)[0]
        print(f'  本会话抛出的 C++ 异常 = {tf_count} 次')
        if tf_count:
            print(f'  最近一次抛出点 = {describe_runtime_address(tf_last, base)}')
            print(f'  第一次抛出点   = {describe_runtime_address(tf_first, base)}')
            print('  ⇒ 上面反查出的函数就是"谁抛的"；这段设施只记录、不改行为，'
                  '有值本身不代表出问题。')
        else:
            print('  ⇒ 0 次：这一局没抛过 C++ 异常（这段设施只记录，不改变行为）。')

    print()
    print_probe_native_mods_menu(values)
    print()
    print_mod_menu_native(values)
    print()
    print_console_state(values)

    print()
    print('=== 游戏模块的两个入口字节（旧式 IPS 有没有改写它们）===')
    for key, name, expect in (('update_entry', 'Manager::Update', 'ff4301d1fd7b01a9'),
                              ('render_entry', 'Manager::Render', 'ffc302d1e83b00fd')):
        vals = values.get(key) or []
        got = b''.join(v.to_bytes(8, 'little') for v in vals[:2]).hex()
        if not vals:
            print(f'  {name:16} 读不到')
        elif got.startswith(expect):
            print(f'  {name:16} = {got} ← 原样（旧式 IPS 没生效）★')
        else:
            word = vals[0] & 0xFFFFFFFF
            note = '  ← 是 `bl`/`b`（被改写成跳转了）' if (word >> 26) in (0x25, 0x05) else ''
            print(f'  {name:16} = {got} ← 与原版不同{note}')

    print()
    print('=== 游戏开局中继：那份**必需**补丁在不在（2026-09-17 套装进度事故的形态）===')
    # 判据用的是**编码出来的分支指令**，不是猜测：`b <代码洞>` 是打完补丁的样子，
    # `bl <原函数>` 是原版的样子（原版的四个字节在本地 NRO 里可查）。
    for key, name, patched, original in (
            ('gamestart_saved_callsite', '读档调用点', '5f4e0a14', 'f30d0a94'),
            ('gamestart_new_callsite', '新局调用点', '1e4e0a14', 'ae0d0a94')):
        words = values.get(key) or []
        if not words:
            print(f'  {name} 读不到')
            continue
        got = (words[0] & 0xFFFFFFFF).to_bytes(4, 'little').hex()
        if got == patched:
            print(f'  {name} = {got} ← 已是 `b <中继代码洞>` ⇒ **补丁在位** ★')
        elif got == original:
            print(f'  {name} = {got} ← 还是原版 `bl <原函数>` ⇒ **补丁不在位**：'
                  '这一路挂点会被跳过（`required=false` ⇒ 只记 Skipped，不算失败）')
        else:
            print(f'  {name} = {got} ← 既不是补丁形态、也不是原版形态（第三种情况，要查）')
    slot = values.get('gamestart_relay_slot') or []
    if slot:
        if slot[0] == 0:
            print('  回调槽 = 0 ⇒ 我们的 `ObserveGameStart` 没发布进去（与"补丁不在位"一致）')
        else:
            print(f'  回调槽 = 0x{slot[0]:012x} ⇒ 我们的开局回调**已发布** ★')
    else:
        print('  回调槽 读不到')

    print()
    print('=== Present 的 GOT 槽（下面几条的偏移都相对**游戏模块**）===')
    expect_intercept = base + SYMS['present_got_intercept']
    got_slot = values.get('present_slot') or []
    if got_slot:
        mark = '★（= 我们的拦截函数）' if got_slot[0] == expect_intercept else '✗ 与拦截函数不符'
        print(f'  GOT 槽内值     = 0x{got_slot[0]:012x} {mark}')
    print(f'  拦截函数应为   = 0x{expect_intercept:012x}（运行时模块+0x{SYMS["present_got_intercept"]:x}）')
    target = first(values, 'g_PresentGotSlotTarget')
    if target:
        mark = '★（= Present 本体）' if target == game_base + SYMS['present_target'] else '✗ 与 Present 本体不符'
        print(f'  转发目标       = 0x{target:012x} {mark}')
    body = values.get('present_body') or []
    if body:
        word = body[0] & 0xFFFFFFFF
        mark = '★（序言未被改动）' if word == 0xA9BE7BFD else '✗ 序言不符'
        print(f'  Present 序言   = 0x{word:08x} {mark}')
    callsite = values.get('present_callsite') or []
    if callsite:
        word = callsite[0] & 0xFFFFFFFF
        if (word >> 26) == 0x25:
            imm = word & 0x03FFFFFF
            if imm & (1 << 25):
                imm -= 1 << 26
            dest = SYMS['present_callsite_offset'] + (imm << 2)
            mark = '★（目标正是 Present 桩）' if dest == 0x670A40 else f'✗ 目标 0x{dest:x}'
            print(f'  调用点首字     = 0x{word:08x}（bl）{mark}')
        else:
            print(f'  调用点首字     = 0x{word:08x} ✗ 不是 bl（那份 IPS 可能还在）')

    helper = values.get('helper')
    if helper:
        print()
        print('=== 插件自己解析到的地址（与上面交叉核对）===')
        for i, name in enumerate(HANDOVER_FIELDS):
            v = helper[i]
            note = ''
            if name == 'ownBase' and v == base:
                note = '← 与调试桩看到的模块基址一致 ✓'
            elif name == 'ownIdentity' and v == base + SYMS['identity']:
                note = '← 与真实身份函数地址一致 ✓'
            print(f'  {name:20} 0x{v:012x} {note}')

    if 'g_ModMenuMilestones' in values:
        print()
        print('=== 模组开关菜单的诊断（按了没反应时看这里）===')
        thunk = first(values, 'g_InputIsActionTriggeredThunk')
        print(f'  `Input.IsActionTriggered` 的原生入口 = 0x{thunk:012x}'
              + ('  ⇒ **没有绑定**（脚本调用会立刻抛错）' if thunk == 0
                 else '  ⇒ 已绑定 ✓（那"没反应"就不是绑定问题）'))
        milestones = first(values, 'g_ModMenuMilestones') & 0xFFFFFFFF
        names = {1: '脚本已加载并登记', 2: '字体装上', 3: '字体失败', 4: '菜单打开过',
                 5: 'update 回调跑过', 6: '切换过', 7: '落盘成功',
                 8: '至少一个动作号完成过沿判定', 9: '呼出键过沿成立（下一步就该打开）',
                 11: '枚举表缺失（用了数字兜底）', 12: 'Input.IsActionPressed 不可用'}
        # 位 10..25：`Held(动作号)` 曾经返回 true 的那些动作号（code % 16）
        held_codes = sorted({bit - 10 for bit in range(10, 26) if milestones & (1 << bit)})
        hit = [f'{bit}={text}' for bit, text in sorted(names.items()) if milestones & (1 << bit)]
        if held_codes:
            print(f'  菜单自己看到"按住"的动作号（code % 16）= '
                  f'{", ".join(str(c) for c in held_codes)}')
        print(f'  菜单里程碑 = 0x{milestones:08x}'
              + (f' ⇒ {"; ".join(hit)}' if hit else '  ⇒ **一个都没报：菜单脚本根本没跑起来**')
              + f'（上报 {first(values, "g_ModMenuReportCount") & 0xFFFFFFFF} 次，最后一次 = '
              + f'{first(values, "g_ModMenuLastCode") & 0xFFFFFFFF}）')
        load_calls = first(values, 'g_FontLoadCalls') & 0xFFFFFFFF
        load_result = first(values, 'g_FontLoadResult') & 0xFFFFFFFF
        draws = first(values, 'g_FontDrawCalls') & 0xFFFFFFFF
        drawn_bytes = first(values, 'g_FontDrawBytes') & 0xFFFFFFFF
        # 批次 415：Font 存储（走 Lua 分配器 ⇒ 计入 GC 账）。
        # 判据：`Live` 应当停在个位数（模组每帧建一个、随即被 GC 收掉；414 那版实测 288 = 没收）；
        #       `Failures` **必须 0**。
        # ★ 2026-10-09 更正：415 直接调 lua_Alloc 不代表 GC 记账；旧判据仅作历史保留。
        print_font_storage(values)
        print(f'  字体：Load 被调用 {load_calls} 次、最后一次结果 = '
              + {0: '失败', 1: '成功'}.get(load_result, '未知'))
        print(f'  画字：四条变体（含缩放）合计调用 {draws} 次、共 {drawn_bytes} 字节')
        # ★ 历史（2026-09-18 当天）：这两个计数**曾经只记未缩放的两个变体**（计数点写在
        # `else` 分支里），而 EID / q4-items / 菜单 / 我们的 `RenderScaledText` 全走缩放变体
        # ⇒ 读数恒为 0，还被当成过"屏幕上一个字都没画"的证据。批次 037 已把计数点移到
        # 四条变体共用的路径上（门禁 `test_font_draw_instrumentation.py` 钉住这一点）。
        # 所以现在这条 0 是**有信息量**的：真的没人走到绘制。
        if draws == 0:
            print('    ⇒ 四条变体都没被调用过（真的没走到绘制）。'
                  '若屏幕上明显有字，就要怀疑这份读数对应的进程/会话不对。')
        queried = first(values, 'g_InputActionQueriedMask') & 0xFFFFFFFF
        triggered = first(values, 'g_InputActionTriggeredMask') & 0xFFFFFFFF
        triggered_other = first(values, 'g_InputActionTriggeredMaskOther') & 0xFFFFFFFF
        pressed_mask = first(values, 'g_InputActionPressedMask') & 0xFFFFFFFF
        pressed_other = first(values, 'g_InputActionPressedMaskOther') & 0xFFFFFFFF
        pressed_ctrl = first(values, 'g_InputPressedControllerMask') & 0xFFFFFFFF
        # ⚠️ 批次 107 起这两张位图的**含义**变了：`Input.IsActionTriggered` 不再问引擎那条"刚按下"
        # （真机上它永远答假 ⇒ EID 的库存概况导航没反应），改成"问引擎的按住 + Runtime 自己算上升沿"。
        # 所以这里的 `triggered` 记的是**我们判定的上升沿**（不再是引擎的答案），
        # 而 `pressed` 那两张位图仍然来自引擎 —— 两者对照着看就能二分：
        # "按住有、上升沿没有" = 我们的边沿判定没生效；"按住也没有" = 引擎那条查询/控制器号有问题。
        print(f'  输入：问过的动作号 = 0x{queried:08x}、回答"是"的 = 0x{triggered:08x}'
              + f'（最后一次问 {first(values, "g_InputLastActionCode") & 0xFFFFFFFF}，'
              + f'结果 {first(values, "g_InputLastActionResult") & 0xFFFFFFFF}）')
        asked = [str(code) for code in range(32) if queried & (1 << code)]
        fired = [str(code) for code in range(32) if triggered & (1 << code)]
        ctrl_list = [str(v) for v in range(32) if pressed_ctrl & (1 << v)]
        print(f'  能让 IsActionPressed 返回 true 的 controller 值（&31）：'
              f'{", ".join(ctrl_list) if ctrl_list else "（一个都没有）"}')
        print(f'    ⇒ 问过：{", ".join(asked) if asked else "（无）"}；'
              f'按到过：{", ".join(fired) if fired else "**一个都没有**"}')
        fired_other = [str(code) for code in range(32) if triggered_other & (1 << code)]
        pressed = [str(code) for code in range(32) if pressed_mask & (1 << code)]
        if 'input_edge_counts' in values:
            counts = []
            for word in values['input_edge_counts']:
                counts.append(word & 0xFFFFFFFF)
                counts.append((word >> 32) & 0xFFFFFFFF)
            fired_counts = [f'{code}={counts[code]}' for code in range(32) if counts[code]]
            print(f'  "刚按下"累计报过几次（按动作号）：'
                  + (', '.join(fired_counts) if fired_counts else '（一次都没报过）'))
            print('    （★ 批次 218 起**这条只统计动作侧**：按键号那条改进了自己的 '
                  '`g_InputButtonEdgeCounts` —— 以前两者共用同一格 ⇒ 按下标根本分不清是哪一个。）')
            if fired_counts:
                print('    ⇒ 按**一次**键之后看这里：某个动作 +2 = "一次按键报了两次边沿"'
                      '（那就是"按一次跳两格"的成因）；+1 = 正常。')
        if 'input_release_peak' in values:
            peaks = []
            for word in values['input_release_peak']:
                peaks.append(word & 0xFFFFFFFF)
                peaks.append((word >> 32) & 0xFFFFFFFF)
            fired_peaks = [f'{code}={peaks[code]}帧' for code in range(32) if peaks[code]]
            print(f'  "按住"最长闪断（按动作号）：'
                  + (', '.join(fired_peaks) if fired_peaks else '（没断过）'))
        if 'touch_poll_frames' in values:
            # ★ 全部走 `first_u32`：这 10 个都是我们自己的 `uint32` 全局，而读数工具按 8 字节取字
            #   ⇒ 直接 `first(...)` 会把**隔壁那个全局**一起取进高 32 位（本批差点这么错：
            #   实测这 10 个的地址是 4 字节一格的 `0x83c0818…0x83c083c`，正好一个字里装两个）。
            init_state = first_u32(values, 'touch_init_state')
            scan_attempts = first_u32(values, 'touch_scan_attempts')
            shmem = (first_u32(values, 'touch_shmem_high') << 32) | first_u32(values, 'touch_shmem_low')
            segments = first_u32(values, 'touch_segments')
            rejected = first_u32(values, 'touch_rejected_mappings')
            buffer_count = first_u32(values, 'touch_lifo_buffer_count')
            tail = first_u32(values, 'touch_lifo_tail')
            lifo_count = first_u32(values, 'touch_lifo_count')
            poll_frames = first_u32(values, 'touch_poll_frames')
            touch_frames = first_u32(values, 'touch_frames')
            raw_x = first_u32(values, 'touch_last_raw_x')
            raw_y = first_u32(values, 'touch_last_raw_y')
            last_count = first_u32(values, 'touch_last_count')
            last_sampling = first_u32(values, 'touch_last_sampling')
            last_entry = first_u32(values, 'touch_last_entry_index')
            state_name = {0: '还没找过', 1: '找到共享内存', 2: '找过、没找到'}.get(
                init_state, f'未知({init_state})')
            #: 引擎口径：面板 1280×720 → 逻辑屏幕 480×270（系数 0.375，证据见 `touch_pointer.hpp`）。
            #: 这里只是**把模组会拿到的数**顺手印出来，方便与手指位置对照。
            render_x = raw_x * 0.375
            render_y = raw_y * 0.375
            # 批次 213：**边沿间隔**（判"一次按住被拆成几次边沿"到底是不是我们的锅）。
            if 'input_edge_gap_min' in values:
                gap_min = {code: first_u32(values, 'input_edge_gap_min', code) for code in range(32)}
                gap_last = {code: first_u32(values, 'input_edge_gap_last', code) for code in range(32)}
                sampled = [code for code in range(32) if gap_min[code] or gap_last[code]]
                print()
                print('=== 边沿间隔（`IsActionTriggered` 报边沿时距上一次"按住"隔了几帧）===')
                # ★ 更正（批次 381，2026-10-06）：上一行的**标题文字是旧语义**（原文保留只作历史）。
                #   新机制下这个量 = **相邻两次边沿之间隔了几帧**，用途 = 判"两次独立按下之间
                #   隔了多久"；边沿不再依赖调用方节奏 ⇒ "闪断"在本机制下不适用。下面那句提示
                #   把它印在旧标题之后，免得按旧判据读。
                print('  ★ 更正（批次 381，2026-10-06）：本量现在 = 相邻两次边沿间隔帧数'
                      '（判"两次独立按下之间隔了多久"）；"闪断"在本机制下不适用，'
                      '下面"只有 1~3 帧 ⇒ 闪断"的判据文字只作历史。')
                if not sampled:
                    print('  （还没有样本：这次读数之前没有任何动作报过边沿）')
                for code in sampled:
                    # ★ 批次 221（2026-09-30）：**去抖窗口已经删掉**（原先是猜一个时长，批次 110 取 6、
                    #   220 取 20；两侧症状会互相顶掉）。现在判据不再依赖任何常量：
                    #   间隔只有 2~3 帧 ⇒ 引擎的"按住"在按着的时候断了帧（闪断）；
                    #   几百帧 ⇒ 用户真松手再按。闪断要**去源头修**，不是把窗口调大。
                    verdict = ('★ 只有 1~3 帧 ⇒ 是**闪断**（引擎的「按住」在按着的时候断过帧）'
                               '—— 批次 221 起不再用窗口掩盖它：去查源头（同一帧里重复读设备表 / '
                               '帧号来源不唯一），别再来调窗口'
                               if gap_min[code] and gap_min[code] <= 3
                               else '离得很远 ⇒ 是**真松手再按**（正常，不需要任何窗口）')
                    print(f'  动作 {code:>2}：最小间隔 = {gap_min[code]:>5} 帧、'
                          f'最近 = {gap_last[code]:>5} 帧　⇒ {verdict}')
            # 批次 381（2026-10-06）：**"帧上采样"现场**（5 个标量；用途见 `SYM_ELF_NAMES`）。
            # 判据：`frame` 贴着当前帧 = 采样在跑；`failures` 在涨 = 设备表读不到 ⇒ 该帧全答 false。
            if 'input_sample_frame' in values:
                print()
                print('=== "帧上采样"现场（批次 381：每帧在引擎帧边界采样一次、判定纯读）===')
                print(f'  最后采样帧 = {first_u32(values, "input_sample_frame")}（应贴着当前帧）；'
                      f'那一帧引擎调用 = {first_u32(values, "input_sample_calls")} 次'
                      f'（真机 1 台手柄时约 32，预算有界）')
                print(f'  那一帧采了 {first_u32(values, "input_sample_codes")} 个码'
                      f'（按键 18 + 动作 32）、{first_u32(values, "input_sample_devices")} 台设备'
                      f'（+1 是"任意设备"聚合槽）')
                print(f'  采样失败累计 = {first_u32(values, "input_sample_failures")} 次'
                      f'（设备表读不到等 ⇒ 该帧全答 false）')
            print('  === 触摸屏 → 指针（批次 192 建、批次 193 修）===')
            print(f'    共享内存 = {state_name}（值 {init_state}）、扫过映射表 {scan_attempts} 次'
                  f'、走过 {segments} 段、判据不符而跳过 {rejected} 段')
            if shmem:
                print(f'    hid 共享内存基址 = 0x{shmem:x}'
                      f'（lifo 表头：buffer_count = {buffer_count} ← **必须是 17**、'
                      f'tail = {tail}、count = {lifo_count}）')
                if buffer_count != 17:
                    print('    ⚠ buffer_count 不是 17 ⇒ 认出的**不是**触摸屏 lifo'
                          '（批次 192 就是这里太宽，把一块零页认成了它）—— 请把这一行报回来。')
            print(f'    读过触摸屏 {poll_frames} 帧，其中**手指在屏幕上**的有 {touch_frames} 帧')
            print(f'    最新条目：槽位 {last_entry}、采样号低 32 位 = {last_sampling}'
                  '（真的 lifo 每采样一次就加一，**与有没有手指无关**）')
            print(f'    最后一次：点数 = {last_count}、原始触摸坐标 = ({raw_x}, {raw_y})'
                  f' ⇒ 模组拿到的是渲染坐标 ({render_x:.1f}, {render_y:.1f})〔原始值 × 0.375〕')
            if init_state == 2:
                print('    ⇒ 没找到触摸屏 lifo（判据要求在 17 个条目的点数之外，'
                      '还必须有 buffer_count == 17 的表头）⇒ 说明**游戏没把那块内存映射在我们进程里**。'
                      '此时两条 API 退回恒值：功能不回归，但触摸不生效 —— '
                      '下一步改走"调引擎"（`KAGE::Input::g_Manager` @ 模块内 0xb06f60，'
                      '`ManagerBase::GetTouches` @ 0x4fa568），见改动手记 §193。')
            elif buffer_count != 17:
                print('    ⇒ ★ 认到了错的内存 ⇒ 这是**我的 bug**，把上面那行「lifo 表头」贴回来。')
            elif poll_frames == 0:
                print('    ⇒ 一帧都没读过：说明模组**根本没调用** `Input.GetMousePosition`／'
                      '`IsMouseBtnPressed`（那两条才是入口）。不是触摸坏了。')
            elif last_sampling == 0:
                print('    ⇒ 表头对了、但**一条带采样号的条目都没有** ⇒ 这块 lifo 没在被写'
                      '（比"没人在按"更严重：值得把这块内存的原始字节 dump 回来看）。')
            elif touch_frames == 0:
                print('    ⇒ 表头对、采样号在动、**但一次都没检测到手指**。'
                      '最可能是：① 机器在**接电视/底座**状态（掌机模式才有触摸屏）；'
                      '② 读数时手已经离开屏幕（本计数器是**会话累计**，按过就该 > 0）。')
            else:
                print(f'    ⇒ ★ 触摸**真的读到了**：原始 ({raw_x}, {raw_y})'
                      f' ⇒ 模组拿到 ({render_x:.1f}, {render_y:.1f})。'
                      '模组里的 `Isaac.WorldToScreen(Input.GetMousePosition(true))` 组合现在是对的'
                      '（`WorldToScreen` 还是恒等变换，两者套起来正好是渲染坐标）。')
            if fired_peaks:
                print('    ⇒ 闪断帧数 > 1 说明**引擎的「按住」在按着的时候断过帧**，而批次 221 起'
                      '边沿是严格相邻帧差分 ⇒ 会**直接多报边沿**（不再用去抖窗口掩盖）。'
                      '要修的是源头：同一帧里重复读设备表、或帧号来源不唯一。')
        if 'minimap_gate_state' in values:
            gate_state = first_u32(values, 'minimap_gate_state')
            gate_applied = first_u32(values, 'minimap_gate_applied')
            gate_mismatch = first_u32(values, 'minimap_gate_guard_mismatch')
            gate_failure = first_u32(values, 'minimap_gate_failure_code')
            gate_name = {0: '还没试', 1: '三处都装上', 2: '没装上'}.get(
                gate_state, f'未知({gate_state})')
            print('  === 原生小地图的触摸门控（批次 194：只改游戏代码 3 条指令）===')
            print(f'    状态 = {gate_name}（值 {gate_state}）、改写成功 {gate_applied}/3 处、'
                  f'守卫不符 {gate_mismatch} 处、失败码 {gate_failure}')
            if gate_state == 1:
                print('    ⇒ ★ 已装上：原生右上角小地图**只会在手指停在那块矩形内**时被拖动，'
                      '别处触摸不再影响它。')
            elif gate_state == 0:
                print('    ⇒ 这个构建从没尝试装过（不该出现：安装点在模块初始化里）。')
            elif gate_mismatch:
                kind = gate_failure & 0xFF
                ordinal = gate_failure >> 8
                print(f'    ⇒ 现场指令与预期不符（第 {ordinal} 处，种类 {kind}）⇒ **一处都没写**、'
                      '游戏保持原样。多半是游戏版本不同 ⇒ 需要重新核对那三条指令。')
            else:
                kind = gate_failure & 0xFF
                ordinal = gate_failure >> 8
                print(f'    ⇒ 没装上（第 {ordinal} 处，种类 {kind}：1=地址/映射非法、3=写完读回不一致）'
                      ' ⇒ 原生小地图照旧响应任意触摸。')
        print(f'  非 0 号 controller 上按到过的动作号：'
              f'{", ".join(fired_other) if fired_other else "（无）"}'
              f'（最后一次问的 controller = '
              f'{first(values, "g_InputLastController") & 0xFFFFFFFF}）')
        pressed_other_codes = [str(code) for code in range(32) if pressed_other & (1 << code)]
        print(f'  "按住"位图（IsActionPressed）：controller 0 = '
              f'{", ".join(pressed) if pressed else "（无）"}；非 0 = '
              f'{", ".join(pressed_other_codes) if pressed_other_codes else "（无）"}')
        if not fired and not fired_other:
            print('    ⇒ 两个 controller 序号都没有任何动作被判定为按下：说明**查询本身**没通'
                  '（不是键位对不上）—— 下一步要换机制，而不是继续猜动作号。')

    # 批次 209：**按键号**那三条查询（`IsButtonPressed` / `IsButtonTriggered` / `GetButtonValue`）
    # 的现场。为什么单独一段：批次 195 把这三条从"恒 false 的桩"改成真实现时就加了这两个掩码，
    # 源码注释原话是"真机上唯一能判'到底读到了没有'的就是这两个计数"——**却从没接进读数**
    # （典型的"设施做了、判据没接上"）。
    #
    # ★★★ 批次 210 更正（2026-09-29 深夜，这是本段第一版给错的结论）：
    #   209 那段写的是"一位都没问过 ⇒ 模组根本没走到那一步，别再往输入上查"。**错**。
    #   那两个掩码的置位点（`input_api.cpp`）在 handler 的**最后**，前面还有两道**静默返回**的闸：
    #   ① 按键号不是 0..17（键盘码一律答 false，不置位）；
    #   ② **发布槽是 0**（= 引擎入口的逐字节守卫没过）⇒ 立刻 `return false`，**同样不置位**。
    #   ⇒ "掩码全 0"有两种解释，**必须先看发布槽**：
    #     槽非 0 ⇒ 真的是"没问过"（模组那一侧的事）；槽 = 0 ⇒ **是我们这条链哑了**。
    #   真事故：判别式常量写成了字节序反的 `F9 40 19 08`（真值 `08 19 40 F9`）⇒ 槽 = 0 ⇒
    #   MCM 的"按右摇杆开菜单"永远没反应（批次 210 修；见该批存档 README）。
    if 'input_button_queried' in values:
        queried_buttons = first_u32(values, 'input_button_queried')
        pressed_buttons = first_u32(values, 'input_button_pressed')
        # ★ 发布槽是**本批新加的格子** ⇒ 回放老 raw 文件时根本不在 `values` 里。
        #   缺了要**说缺**，不能读成 0 —— 读成 0 会被下面判成"没发布（守卫没过）"，
        #   那是一条**假的硬结论**（本项目栽过同一类：把"没读到"当成"是 0"）。
        has_thunk = 'input_button_thunk' in values
        thunk = (first(values, 'input_button_thunk') & 0xFFFFFFFFFFFFFFFF) if has_thunk else None
        get_value_thunk = (first(values, 'input_get_button_value_thunk') & 0xFFFFFFFFFFFFFFFF
                           if 'input_get_button_value_thunk' in values else None)
        expected_thunk = game_base + KAGE_IS_BUTTON_PRESSED_OFFSET if game_base else 0
        asked_buttons = [code for code in range(32) if queried_buttons & (1 << code)]
        held_buttons = [code for code in range(32) if pressed_buttons & (1 << code)]
        button_names = {0: '十字左', 1: '十字右', 2: '十字上', 3: '十字下', 4: 'A', 5: 'B',
                        6: 'X', 7: 'Y', 8: 'L', 9: 'ZL', 10: '左摇杆按下', 11: 'R',
                        12: 'ZR', 13: '右摇杆按下', 14: '减号', 15: '加号'}
        print()
        print('=== 按按键号查询的现场（`Input.IsButtonPressed` / `IsButtonTriggered`）===')
        if thunk is None:
            print('  发布槽 = **本次读数没读这一格**（多半是在回放批次 210 之前存的 raw 文件）'
                  ' ⇒ 下面"问没问过"这句**这轮判不了**，先跑一次现场读数。')
        else:
            print(f'  发布槽 `IsButtonPressed` = 0x{thunk:x}'
                  + (' ⇒ **没发布**（守卫没过 ⇒ 那两条 API 恒答 false、且这两位永远不置位）'
                     if thunk == 0 else
                     f' ⇒ 已发布（应当 = 游戏基址 + 0x{KAGE_IS_BUTTON_PRESSED_OFFSET:X}'
                     f' = 0x{expected_thunk:x}）'))
            print(f'  发布槽 `GetButtonValue` = 0x{get_value_thunk:x}'
                  + (' ⇒ 没发布' if get_value_thunk == 0 else ' ⇒ 已发布'))
        print(f'  问过的按键号 = 0x{queried_buttons:08x} ⇒ '
              + (', '.join(f'{c}({button_names.get(c, "?")})' for c in asked_buttons)
                 if asked_buttons else '**一个都没问过**'))
        print(f'  `IsButtonPressed` 曾答过"按住"的按键号 = 0x{pressed_buttons:08x} ⇒ '
              + (', '.join(f'{c}({button_names.get(c, "?")})' for c in held_buttons)
                 if held_buttons else '（一个都没有）'))
        print('    （注意这一位的置位条件：`input_api.cpp:298` —— **只有 `Input.IsButtonPressed` '
              '的调用方**会置它，而且只在那一帧真的按住时才置。MCM 走的是 `IsButtonTriggered`，'
              '它**不置**这一位 ⇒ 别拿"这一位没置"当作"引擎没答"。）')
        if 'input_controller_map_outcome' in values:
            # 批次 211：手柄号翻译的现场（口径 = runtime/source/pc_ns_input_device_map.hpp）。
            map_pc = first_u32(values, 'input_controller_map_pc_id')
            map_ns = first_u32(values, 'input_controller_map_ns_id')
            map_outcome = first_u32(values, 'input_controller_map_outcome')
            fallbacks = first_u32(values, 'input_controller_map_fallbacks')
            outcome_text = {0: '原样透传（NS 原生用法）',
                            1: '翻到设备表里那台手柄 ⇒ 拿去问引擎',
                            2: 'PC 上没有这台（键盘档 / 第 k 台手柄不存在）⇒ 直接答 false'}.get(
                                map_outcome, f'未知({map_outcome})')
            print(f'  最近一次手柄号翻译：模组给 {map_pc} ⇒ 引擎设备号 {map_ns}（{outcome_text}）'
                  f'｜因设备表读不到而没能翻译 = {fallbacks} 次')
            if fallbacks:
                print('    ⇒ ★ 有兜底：设备表没读到 ⇒ 1..4 被原样透传（与修之前同形）'
                      ' —— 先查 `ReadNsInputDeviceTable` 链上的偏移/权限。')
        if 'input_action_map_lua_code' in values:
            # 批次 230：动作号翻译的现场（口径 = runtime/src/interfaces/lua/input_action_map.hpp）。
            # ★ Switch 引擎的内部表把 17..20 当"菜单左/右/上/下"（PC 的 `ACTION_MENULEFT` 在引擎里是 17）
            #   ⇒ 这一段是"推方向被读成别的方向"那类缺陷唯一的现场证据。
            map_lua = first_u32(values, 'input_action_map_lua_code')
            map_engine = first_u32(values, 'input_action_map_engine_code')
            map_absent = first_u32(values, 'input_action_map_absent')
            if map_lua == 0xFFFFFFFF:
                print('  最近一次动作号翻译：（本次会话还没有模组问过动作）')
            else:
                engine_text = ('**Switch 上没有这个动作** ⇒ 我们直接答 false / 0（不问引擎）'
                               if map_engine == 0xFFFFFFFF else f'引擎内部动作号 {map_engine}')
                print(f'  最近一次动作号翻译：模组给 {map_lua}（PC 口径）⇒ {engine_text}'
                      f'｜因"Switch 上没有"而直接回答 = {map_absent} 次')
                print('    （对照：PC 的 20/21/22/23 = 菜单左/右/上/下，而 Switch 引擎的内部号是 '
                      '17/18/19/20；逐行证据见 `input_action_map.hpp`。）')
        if thunk is None:
            pass
        elif thunk == 0:
            print('  ⇒ **先修发布槽**：槽是 0 = 引擎入口的守卫没过（序言 16 字节或 `entry+0xE0` 的'
                  '判别式）⇒ 上面那两个掩码**必然全 0**，此时"模组问没问过"这句话判不出来。'
                  '查法：`python3 tools/verify_runtime_constants_against_nro.py` 会拿本地镜像'
                  '逐字节比一遍那些常量。')
        elif 13 in asked_buttons:
            print('  ⇒ **模组问过右摇杆（13 号）** ⇒ 它的渲染回调确实跑到了开菜单判定那一步，'
                  '所以"回调没派发"这一类原因可以排除。')
            print('     那么"按下去毫无反应"只剩两种：① 模组收到这次按下之后**抛了错**'
                  '（菜单开不出来、屏幕上一个字都不会有）；② 收到了、也往下走了，但被'
                  '`RoomIsSafe()` 挡在门外（那样会**响一声错误音效**）。'
                  '判据是上面的 `lua_error_history` 与 `g_ModRegisteredCount`。')
        else:
            print('  ⇒ **模组根本没问过右摇杆**（发布槽非 0，所以这条结论这次站得住）：先查它有没有'
                  '真的登记成功、它的渲染/更新回调有没有在跑（看 `g_ModRegistered` /'
                  ' `g_ModRegisteredCount` / `lua_error_history`）。')

    # 批次 212：**玩家字段写**的现场（口径 = `isaac_api.cpp` 的 `EntityNewIndex`）。
    # 为什么必须打印：字段写守卫是"报错"不是"静默忽略" ⇒ 模组写了个我们没实现的字段，
    # **整条回调当场中断**（MCM 的菜单画不出来就是这么来的）。这里的计数是"不靠眼睛"的那半边判据。
    if 'entity_field_writes' in values:
        write_names = {0: 'Velocity', 1: 'Position', 2: 'ControlsEnabled', 3: 'ControlsCooldown',
                       4: 'HitPoints', 5: 'MaxHitPoints', 6: 'Scale',
                       7: 'MaxFireDelay', 8: 'ShotSpeed', 9: 'Damage', 10: 'MoveSpeed',
                       11: 'Luck', 12: 'TearRange', 13: 'Size', 14: 'Friction', 15: 'Visible',
                       16: 'Variant', 17: 'SubType', 18: 'SpawnerType', 19: 'SpawnerVariant', 20: 'CanFly', 21: 'TearHeight',
                       22: 'TearFallingSpeed', 23: 'TearFallingAcceleration', 24: 'TearColor'}
        counts = {}
        for index, name in write_names.items():
            raw_bytes = words_to_bytes(values['entity_field_writes'])
            available = min(len(raw_bytes), ENTITY_FIELD_WRITES_BYTES)
            counts[name] = first_u32(values, 'entity_field_writes', index) if index * 4 + 4 <= available else None
        rejected = first_u32(values, 'entity_field_write_rejected')
        last_hash = first_u32(values, 'last_entity_field_write_name')
        known_hashes = {0xBA408252: 'Velocity', 0xE27F342A: 'Position',
                        0xD8182F6C: 'ControlsEnabled', 0xB5D0FA92: 'ControlsCooldown',
                        0xEEA83A5D: 'HitPoints', 0xFDDF1A19: 'MaxHitPoints',
                        0x28528E11: 'Scale',
                        0x0C9F5AF0: 'MaxFireDelay', 0x6B489710: 'ShotSpeed',
                        0x2DF7D460: 'Damage', 0xD572779F: 'MoveSpeed',
                        0x773C3F90: 'Luck', 0xC0505A8E: 'TearRange'}
        for name in write_names.values():
            hash_value = 2166136261
            for byte in name.encode('utf-8'):
                hash_value = ((hash_value ^ byte) * 16777619) & 0xffffffff
            known_hashes[hash_value] = name
        last_name = known_hashes.get(last_hash, f'未知字段名（哈希 0x{last_hash:08x}）')
        summary = '、'.join(f'{name}={count}' for name, count in counts.items() if count)
        print()
        print('=== 实体字段写的现场（`Entity.<字段> = …`）===')
        print(f'  被写过的字段：{summary if summary else "（一个都没写过）"}'
              f'｜最近一次写的字段名 = {last_name}')
        unavailable = [name for name, count in counts.items() if count is None]
        if unavailable:
            print('  尚未取得字段写计数：' + '、'.join(unavailable))
        print(f'  被我们拒绝的写 = {rejected} 次'
              + ('　⇒ ★ 模组写了我们没实现的字段 ⇒ **它的回调会在那一行当场中断**'
                 '（症状：那一段功能整块消失、不报错到屏幕上）。'
                 '要放开就得先取证该字段的偏移，别直接放行。' if rejected else '（正常）'))

    # 批次 217：**每个动作"最后一次被问到时"的现场** —— 判"用户按下的那一刻，菜单问没问、我们答了什么"。
    # 为什么需要这一段：原来那几张掩码是**粘性**的（一旦置位永不清），真机上早饱和成 0x0fffffff
    # ⇒ 看"问过的动作号"已经什么都得不出来。这一段带**帧号**，所以能只说"刚才那几帧"。
    if 'input_action_asked_frame' in values:
        action_names = {0: 'LEFT', 1: 'RIGHT', 2: 'UP', 3: 'DOWN', 4: 'SHOOTLEFT', 5: 'SHOOTRIGHT',
                        6: 'SHOOTUP', 7: 'SHOOTDOWN', 8: 'BOMB', 9: 'ITEM', 10: 'PILLCARD',
                        11: 'MAP', 12: 'MENUUP?', 13: 'PAUSE', 22: 'MENUUP', 23: 'MENUDOWN',
                        24: 'MENULEFT', 25: 'MENURIGHT', 26: 'MENUCONFIRM', 27: 'MENUBACK'}
        kind_names = {0: 'IsActionTriggered', 1: 'IsActionPressed', 2: 'GetActionValue'}
        frames = [first_u32(values, 'input_action_asked_frame', index) for index in range(32)]
        newest = max(frames)
        print()
        print('=== 每个动作"最后一次被问"的现场（批次 217：判"按下那一刻菜单问没问、我们答了什么"）===')
        if newest == 0:
            print('  一次都还没问过任何动作（帧号全 0）')
        else:
            recent = 0
            for index in range(32):
                asked = frames[index]
                if asked == 0 or newest - asked > 180:
                    continue
                recent += 1
                kind = first_u32(values, 'input_action_asked_kind', index)
                controller = first_u32(values, 'input_action_asked_controller', index)
                raw = first_u32(values, 'input_action_asked_answer', index)
                if kind == 2:
                    import struct as _struct
                    answer = f'值 {_struct.unpack("<f", _struct.pack("<I", raw))[0]:.4f}'
                else:
                    answer = 'true' if raw else 'false'
                label = action_names.get(index, '?')
                print(f'  动作 {index:2d}（{label}）: {kind_names.get(kind, kind):18s}'
                      f' controller={controller}  答 {answer}'
                      f'  （第 {asked} 帧，比最新一次早 {newest - asked} 帧）')
            if recent == 0:
                print(f'  最近 180 帧内一次都没问过（最新一次提问在第 {newest} 帧）')
        print('  ⇒ 判据：**用户按下的那一刻** ① 问了且我们答 true ⇒ 问题在模组自己的导航逻辑（不是我们）；'
              '② 问了但我们答 false ⇒ 查我们的查询链（手柄号/设备/引擎判定）；③ 压根没被问 ⇒ 模组没走到那一步。')

        # 批次 218：**按键侧**的同一套现场 + "菜单走了哪个分支"的判据。
        # 中文版 MCM 每帧先问 `MultipleButtonTriggered({DPAD_LEFT..DPAD_DOWN, BUTTON_A..Y})`，
        # **任一为真就整块跳过动作导航** ⇒ 那一问的答案决定菜单走哪个分支。
        if 'input_button_asked_frame' in values:
            button_names = {0: 'DPAD_LEFT', 1: 'DPAD_RIGHT', 2: 'DPAD_UP', 3: 'DPAD_DOWN',
                            4: 'BUTTON_A', 5: 'BUTTON_B', 6: 'BUTTON_X', 7: 'BUTTON_Y',
                            8: 'BUMPER_LEFT', 9: 'TRIGGER_LEFT', 10: 'STICK_LEFT',
                            11: 'BUMPER_RIGHT', 12: 'TRIGGER_RIGHT', 13: 'STICK_RIGHT',
                            14: 'BUTTON_BACK', 15: 'BUTTON_START'}
            kind_names_b = {0: 'IsButtonTriggered', 1: 'IsButtonPressed', 2: 'GetButtonValue'}
            frames_b = [first_u32(values, 'input_button_asked_frame', index) for index in range(32)]
            newest_b = max(frames_b)
            # ★ 2026-10-08（排查 MCM 打不开）：**按键 13 / 10 的专项**（不过滤 180 帧）。
            #   为什么非要有：下面那张表会把"180 帧内没问过"的行整行丢掉 ⇒ 看不出
            #   "到底一次都没问过 / 问过但很早"。而 MCM 的开菜单判定是
            #   `if ControlsEnabled and not isPaused then … for i=0,4 do IsButtonTriggered(13,i) …`
            #   ⇒ **它只要在跑，就会每帧问 13** ⇒ 这一格的"最后被问帧号"是不是贴着当前帧，
            #   是判"它跑到那一句没有"的唯一直接证据。
            for target in (13, 10):
                tf = frames_b[target] if target < len(frames_b) else 0
                tk = first_u32(values, 'input_button_asked_kind', target) if \
                    'input_button_asked_kind' in values else 0
                tc = first_u32(values, 'input_button_asked_controller', target) if \
                    'input_button_asked_controller' in values else 0
                ta = first_u32(values, 'input_button_asked_answer', target) if \
                    'input_button_asked_answer' in values else 0
                triggered_f = first_u32(values, 'input_button_triggered_frame', target) if \
                    'input_button_triggered_frame' in values else 0
                cnt = first_u32(values, 'input_button_edge_counts', target) if \
                    'input_button_edge_counts' in values else 0
                age = (newest_b - tf) if tf else -1
                print(f'  ★ 按键 {target}（{button_names.get(target, "?")}）专项：'
                      f'最后被问 = 第 {tf} 帧（最新一次提问在第 {newest_b} 帧 ⇒ 差 {age} 帧）'
                      f'｜问的是 {kind_names_b.get(tk, tk)}｜controller = {tc}'
                      f'（4294967295 = 任意设备）｜那次答 {"true" if ta else "false"}')
                print(f'        ⇒ 累计报过边沿 {cnt} 次｜**最后一次真的报 true 的帧号 = {triggered_f}**'
                      f'（0 = 从未）；★ 若"最后被问"贴着当前帧而"报 true"的帧号是最近按下的那一下，'
                      f'说明边沿确实送到了；若"最后被问"是个很旧的帧号 ⇒ 模组根本没问到这一句')
            print()
            print('=== 每个按键"最后一次被问"的现场（批次 218：判"菜单走按键分支还是动作分支"）===')
            if newest_b == 0:
                print('  一次都还没问过任何按键号（帧号全 0）')
            else:
                recent_b = 0
                for index in range(32):
                    asked = frames_b[index]
                    if asked == 0 or newest_b - asked > 180:
                        continue
                    recent_b += 1
                    kind = first_u32(values, 'input_button_asked_kind', index)
                    controller = first_u32(values, 'input_button_asked_controller', index)
                    raw = first_u32(values, 'input_button_asked_answer', index)
                    if kind == 2:
                        import struct as _struct
                        answer = f'值 {_struct.unpack("<f", _struct.pack("<I", raw))[0]:.4f}'
                    else:
                        answer = 'true' if raw else 'false'
                    print(f'  按键 {index:2d}（{button_names.get(index, "?"):12s}）: '
                          f'{kind_names_b.get(kind, kind):18s} controller={controller}  答 {answer}'
                          f'  （第 {asked} 帧，比最新一次早 {newest_b - asked} 帧）')
                if recent_b == 0:
                    print(f'  最近 180 帧内一次都没问过（最新一次提问在第 {newest_b} 帧）')
            if 'input_button_edge_counts' in values:
                counts_b = []
                for word in values['input_button_edge_counts']:
                    counts_b.append(word & 0xFFFFFFFF)
                    counts_b.append((word >> 32) & 0xFFFFFFFF)
                fired_b = [f'{button_names.get(code, code)}={counts_b[code]}'
                           for code in range(32) if counts_b[code]]
                print(f'  按键侧"刚按下"累计报过几次：'
                      + (', '.join(fired_b) if fired_b else '（一次都没报过）'))
            print('  ⇒ 判据：⑧ D-pad/A/B/X/Y（按键号 0..7）里**只要有一个答 true**，中文版 MCM 就会'
                  '**整块跳过动作导航**走按键分支（它的源码是 `MultipleButtonTriggered(ignoreActionButtons)`）'
                  '⇒ 此时"方向上/下能选"与动作侧无关，要查的是按钮那一问。')

        # 批次 379：**上升沿表本体** —— 把"引擎没答按住"与"我们的边沿没成立"分开。
        # 前面那组只能告诉你"模组问过、我们答 false"；两种病因的修法完全不同：
        #   * `lastPressedFrame` 有值（引擎答过一次"按住"）而边沿没报 ⇒ **我们的边沿判定**要修
        #     （相邻帧、帧号来源、同一格被别的设备号串用……）；
        #   * `lastPressedFrame` 一直是 `0xFFFFFFFF` ⇒ **引擎从来没对这台设备答过这个键的按住**
        #     ⇒ 查设备号翻译 / 按键号（PC 的号在 Switch 上是不是同一个）。
        # ★ 更正（批次 381，2026-10-06）：上面两条判据文字是按**旧语义**写的（原文保留只作历史）：
        #   +8 那个字段已由 `lastPressedFrame` 改名为 `lastEdgeFrame`，且语义从"上一次**读到按住**
        #   的帧号"变成"**上一次边沿**的帧号"。⇒ 旧判据里的"有值而边沿没报"在新机制下不再成立
        #   （有边沿才会留下帧号）。新机制下要判"我们的判定没成立"应改看 `input_sample_*` 那 5 个量
        #   （采样在不在跑、采了几个、有没有失败）。
        for row_key, row_label in (('input_button_edge_row_gamepad', '设备 33（第 1 台手柄）'),
                                   ('input_button_edge_row_any', '0xFFFFFFFF（任意设备）')):
            if row_key not in values:
                continue
            raw = words_to_bytes(values[row_key])
            if len(raw) < BUTTON_EDGE_ROW_BYTES:
                continue
            # 名字表与上面那组**分开**抄一份：上面那份定义在它自己的 `if` 里，这里不能借。
            edge_button_names = {0: 'DPAD_LEFT', 1: 'DPAD_RIGHT', 2: 'DPAD_UP', 3: 'DPAD_DOWN',
                                 4: 'BUTTON_A', 5: 'BUTTON_B', 6: 'BUTTON_X', 7: 'BUTTON_Y',
                                 8: 'BUMPER_LEFT', 9: 'TRIGGER_LEFT', 10: 'STICK_LEFT',
                                 11: 'BUMPER_RIGHT', 12: 'TRIGGER_RIGHT', 13: 'STICK_RIGHT',
                                 14: 'BUTTON_BACK', 15: 'BUTTON_START'}
            print()
            print(f'=== 按键侧上升沿表（批次 379）：行 {1 if "gamepad" in row_key else 31} = {row_label} ===')
            touched = 0
            for code in range(32):
                offset = code * BUTTON_EDGE_ENTRY_BYTES
                frame = int.from_bytes(raw[offset:offset + 4], 'little')
                edge = raw[offset + 4]
                held = raw[offset + 5]
                last_pressed = int.from_bytes(raw[offset + 8:offset + 12], 'little')
                release_run = raw[offset + 12]
                peak_release = raw[offset + 13]
                if (frame == BUTTON_EDGE_NO_FRAME and not edge and not held
                        and last_pressed == BUTTON_EDGE_NO_FRAME):
                    continue
                touched += 1
                last_text = ('从未答过"按住"' if last_pressed == BUTTON_EDGE_NO_FRAME
                             else f'第 {last_pressed} 帧')
                print(f'  按键 {code:2d}（{edge_button_names.get(code, "?"):12s}）: '
                      f'最后采样 = 第 {frame} 帧｜按住 = {"是" if held else "否"}｜'
                      f'本帧报边沿 = {"是" if edge else "否"}｜上次读到按住 = {last_text}｜'
                      f'连续松开 {release_run} 帧（峰值 {peak_release}）')
            if touched == 0:
                print('  这一行一个键都没被问过（没有任何 `IsButtonTriggered` 调用方用这个设备号）')
            else:
                print('  ⇒ 判据：某个键 `上次读到按住` 有帧号、而"按键侧刚按下累计报过几次"里是 0'
                      ' ⇒ 是我们的边沿判定没成立（查相邻帧/帧号来源），**不是**引擎没答；'
                      '一直是"从未答过" ⇒ 引擎对这个（设备号，按键号）压根没答过"按住"'
                      '（查设备号翻译与按键号本身）。')
                # ★ 更正（批次 381，2026-10-06）：上面一行里的字段现在叫 `lastEdgeFrame`，
                #   语义 = "**上一次边沿**的帧号"（不再是"上次读到按住"）⇒ 印出的那一列应按
                #   "上次边沿帧"读；旧判据"有边沿帧而计数为 0 ⇒ 我们的判定没成立"仍可用，但
                #   判"没采样"要看上面那 5 个 `input_sample_*`。
                print('  ★ 更正（批次 381，2026-10-06）：本列字段已改名 `lastEdgeFrame`，'
                      '现在记**上一次边沿**的帧号（不再是"上次读到按住"）。')

        # 批次 219：**"最后一次真的被激活"的帧号** —— 这是回答"推下的时候到底激活了哪个动作号"的唯一手段
        # （217/218 那两族记的是"最后一次被问时答什么"，而 MCM 每帧都问 ⇒ 永远读到"此刻的输入状态"）。
        if 'input_action_held_frame' in values:
            held_names = {0: 'LEFT', 1: 'RIGHT', 2: 'UP', 3: 'DOWN', 4: 'SHOOTLEFT', 5: 'SHOOTRIGHT',
                          6: 'SHOOTUP', 7: 'SHOOTDOWN', 9: 'ITEM', 10: 'PILLCARD', 11: 'MAP',
                          12: 'PAUSE', 13: 'MAP', 14: 'MENUCONFIRM', 15: 'MENUBACK',
                          16: 'FULLSCREEN', 17: 'MUTE', 18: 'RESTART', 19: 'JOINMULTIPLAYER',
                          20: 'MENULEFT', 21: 'MENURIGHT', 22: 'MENUUP', 23: 'MENUDOWN',
                          24: 'MENULT', 25: 'MENURT', 26: 'MENUTAB', 28: 'CONSOLE'}
            held_action = [first_u32(values, 'input_action_held_frame', i) for i in range(32)]
            trig_button = [first_u32(values, 'input_button_triggered_frame', i) for i in range(32)]
            newest_h = max(max(held_action), max(trig_button))
            print()
            print('=== 每个动作/按键"最后一次真的被激活"的帧号（批次 219）===')
            if newest_h == 0:
                print('  一次都还没激活过（帧号全 0）')
            else:
                for index in range(32):
                    if held_action[index]:
                        print(f'  动作 {index:2d}（{held_names.get(index, "?"):14s}）: '
                              f'第 {held_action[index]} 帧（比最新早 {newest_h - held_action[index]} 帧）')
                for index in range(32):
                    if trig_button[index]:
                        print(f'  按键 {index:2d}（{button_names.get(index, "?"):12s}）: '
                              f'第 {trig_button[index]} 帧（比最新早 {newest_h - trig_button[index]} 帧）')
            print('  ⇒ 判据（按**一次**方向之后读它）：那几个帧号就是"这一次按下的动作号 / 按键号"。')
            print('     ★ 推"下"却只有动作 2（UP）的帧号在动 ⇒ 引擎把下映射成了上（查查询链/绑定）；')
            print('     ★ 同一帧里**按键与动作都动** ⇒ 菜单当帧会切到按键分支（方向导航整块不生效，模组自己的设计）。')

    # 批次 222：每帧"全动作快照" —— 我们**自己**把全部动作号 / 按键号各问一遍。
    # 为什么需要它：批次 217/218 的探针**只记"模组问过的"**（MCM 只问 10 个号），
    # 而真机现象是"推摇杆下时只有 `ACTION_PILLCARD(10)` 为真、`ACTION_DOWN(3)` 恒假"
    # ⇒ 另外 18 个号必须看得见，才能判"引擎把'下'接到了哪一项"。
    if 'input_action_snapshot_pressed' in values:
        import struct as _struct
        snapshot_frame = first_u32(values, 'input_snapshot_frame')
        action_mask = first_u32(values, 'input_action_snapshot_pressed')
        button_mask = first_u32(values, 'input_button_snapshot_pressed')
        snapshot_button_names = {
            0: 'DPAD_LEFT', 1: 'DPAD_RIGHT', 2: 'DPAD_UP', 3: 'DPAD_DOWN',
            4: 'BUTTON_A', 5: 'BUTTON_B', 6: 'BUTTON_X', 7: 'BUTTON_Y',
            8: 'BUMPER_LEFT', 9: 'TRIGGER_LEFT', 10: 'STICK_LEFT',
            11: 'BUMPER_RIGHT', 12: 'TRIGGER_RIGHT', 13: 'STICK_RIGHT',
            14: 'BUTTON_BACK', 15: 'BUTTON_START',
        }
        print()
        print('=== 每帧"全动作快照"（批次 222：**我们自己**把全部动作号 / 按键号各问一遍）===')
        print(f'  快照帧号 = {snapshot_frame}'
              '（与上面"最后一次被问"的帧号对照，即可知这份快照是不是这一刻的）')
        if action_mask == 0 and button_mask == 0:
            print('  （两个位图都是 0 ⇒ 读数这一刻没有任何动作 / 按键被按住）')
        if action_mask:
            got = [f'{a}:{NATIVE_MODS_ACTIONS.get(a, "?")}'
                   for a in range(32) if (action_mask >> a) & 1]
            print(f'  答"按住"的动作号 = 0x{action_mask:08x} ⇒ ' + ', '.join(got))
        if button_mask:
            got = [f'{b}:{snapshot_button_names.get(b, "?")}'
                   for b in range(32) if (button_mask >> b) & 1]
            print(f'  答"按住"的按键号 = 0x{button_mask:08x} ⇒ ' + ', '.join(got))
        nonzero = []
        for action in range(32):
            bits = first_u32(values, 'input_action_snapshot_value', action)
            value = _struct.unpack('<f', _struct.pack('<I', bits))[0]
            if value != 0.0 and value == value:      # 排除 NaN
                nonzero.append((action, value))
        print('  `GetActionValue` 非 0 的动作号（判"模拟量数组填到了哪一格"）：'
              + ('（全 0 ⇒ 说明"按住"全部来自按钮绑定，没有模拟量参与）' if not nonzero else ''))
        for action, value in nonzero:
            print(f'    动作 {action:2d}（{NATIVE_MODS_ACTIONS.get(action, "?")}）: {value:+.4f}')
        print('  ⇒ 判据：**推"下"却在某一行看到不相干的动作号 ⇒ 引擎的"动作 ↔ 输入"绑定把它接到那儿了**；')
        print('     若 `GetActionValue` 里"有值的那一格"也不是 3 ⇒ 那是**索引错位**（两者要的修法不同）。')

    # 批次 223："动作 → 绑定的按钮码"表的现场 —— 查"+17 错位"的**根因**。
    # 真机上"推左/右/下"时引擎**同时**答 `action` 与 `action+17` 为真（左⇒0&17、右⇒1&18、下⇒3&20）
    # ⇒ 要看的是"第 i 项与第 i+17 项绑的是不是同一个输入"。
    if 'input_binding_dump_done' in values:
        dump_done = first_u32(values, 'input_binding_dump_done')
        binding_count = first_u32(values, 'input_binding_action_count')
        print()
        print('=== "动作 → 绑定的按钮码"表（批次 223：查"+17 错位"的根因；表只采一次）===')
        if not dump_done:
            print('  （还没采到：设备表/表指针读不到，或这次会话没走到输入查询 —— 推一下方向再读一次）')
        else:
            rows = {}
            for action in range(32):
                ptr = first_u32(values, 'input_binding_ptr', action)
                codes = tuple(first_u32(values, 'input_binding_codes', action * 4 + slot)
                              for slot in range(4))
                rows[action] = (ptr, codes)
            limit = min(binding_count, 32)
            print(f'  设备里的动作数 = {binding_count}')
            for action in range(limit):
                ptr, codes = rows[action]
                name = NATIVE_MODS_ACTIONS.get(action, '?')
                shown = ', '.join(f'{code:#x}' for code in codes)
                print(f'  动作 {action:2d}（{name:22s}）数组指针 = {ptr:#010x}、按钮码 = [{shown}]')
            print('  ⇒ 判据：**第 i 项与第 i+17 项的按钮码完全相同** ⇒ 坐实"同一个输入被绑到了两个动作"，'
                  '根源修法就是**改那张表**（清掉多余的一份），不必在外面拦。')
            for action in range(limit):
                other = action + 17
                if other >= limit:
                    break
                same_codes = rows[action][1] == rows[other][1]
                same_ptr = rows[action][0] == rows[other][0]
                if same_codes and any(rows[action][1]):
                    print(f'     ★ 动作 {action} 与动作 {other} 的按钮码相同'
                          f'（{"同一个数组" if same_ptr else "两份独立但内容相同的数组"}）：'
                          f'{rows[action][1]}')

    # 批次 224：设备**内部**输入状态的原始值（模拟量 / 位图 / 死区）—— **不经过任何 API**。
    # 为什么要这么"原始"：批次 222/223 已经踩过一次"API 说的和引擎内部读的对不上"，
    # 而 `IsActionPressed` 的判定是「绑定的按钮按下 **或** `analog[action] > 死区`」
    # ⇒ 只有把 `+0xd0` 那 24 格看原样，才能回答"多报出来的那个动作号是哪一格有值"。
    if 'input_device_state_dump_count' in values:
        import struct as _struct3
        dumps = first_u32(values, 'input_device_state_dump_count')
        enabled = first_u32(values, 'input_device_state_enabled')
        device_action_count = first_u32(values, 'input_device_state_action_count')
        keys_cur = first_u32(values, 'input_device_state_keys_current')
        keys_prev = first_u32(values, 'input_device_state_keys_previous')
        stick_cur = first_u32(values, 'input_device_state_stick_current')
        stick_prev = first_u32(values, 'input_device_state_stick_previous')
        deadzone = _struct3.unpack(
            '<f', _struct3.pack('<I', first_u32(values, 'input_device_state_deadzone')))[0]
        deadzone_alt = _struct3.unpack(
            '<f', _struct3.pack('<I', first_u32(values, 'input_device_state_deadzone_alt')))[0]
        print()
        print('=== 设备内部输入状态（批次 224：原始格子，**不经过任何 API**）===')
        if dumps == 0:
            print('  （还没采到：设备对象没找到或还没建好 —— 推一下方向再读一次）')
        else:
            print(f'  设备启用 = {enabled}、动作数 = {device_action_count}、本会话采样 {dumps} 次')
            print(f'  死区 = {deadzone:.4f}（`+0xe4`，动作判定用）、另一个 = {deadzone_alt:.4f}（`+0xe0`）')
            print(f'  按键位图：本帧 = {keys_cur:#010x}、上帧 = {keys_prev:#010x}')
            print(f'  摇杆方向位图：本帧 = {stick_cur:#010x}、上帧 = {stick_prev:#010x}')
            axes = [_struct3.unpack(
                '<f', _struct3.pack('<I', first_u32(values, 'input_device_state_axes', i)))[0]
                for i in range(8)]
            print('  8 个轴幅值（`+0x50`..`+0x6c`）= ' + ', '.join(f'{v:+.3f}' for v in axes))
            print('  ★ 每动作模拟量（`+0xd0[action]`）—— **这才是 `IsActionPressed` 真正读的那一份**：')
            any_value = False
            for action in range(32):
                raw = first_u32(values, 'input_device_state_action_value', action)
                value = _struct3.unpack('<f', _struct3.pack('<I', raw))[0]
                if value != 0.0 and value == value:
                    any_value = True
                    verdict = '　← ★ 超过死区 ⇒ 引擎会把这个动作答成"按住"' if value > deadzone else ''
                    print(f'    动作 {action:2d}（{NATIVE_MODS_ACTIONS.get(action, "?")}）:'
                          f' {value:+.4f}{verdict}')
            if not any_value:
                print('    （全 0 ⇒ 没有任何"模拟量"参与，"按住"全部来自按钮绑定）')
            print('  ⇒ 判据：**标了 ★ 的那几行就是引擎认为"被按住"的动作** ——'
                  ' 多报出来的号若出现在这里，修法就是把这格的值归零/纠正；')
            print('     若它不在这里（值没超死区却仍被答成按住）⇒ 那是"按钮绑定"那条路，回头查表。')

    # 批次 225：设备对象**整块原始内存**（用户要求"读全"—— 不再逐字段猜，字段解释留给读数之后）。
    if 'input_device_raw_dump_count' in values:
        import struct as _struct4
        raw_count = first_u32(values, 'input_device_raw_dump_count')
        device_pointer = (first_u32(values, 'input_device_raw_pointer_high') << 32) | \
            first_u32(values, 'input_device_raw_pointer_low')
        device_id = first_u32(values, 'input_device_raw_id')
        print()
        print('=== 设备对象原始内存（批次 225「读全」版：原始字节端上来，解释放在后面）===')
        if raw_count == 0:
            print('  （还没采到：设备对象没找到或还没建好 —— 推着方向再读一次）')
        else:
            print(f'  设备对象指针 = {device_pointer:#018x}、设备号 = {device_id}、采样 {raw_count} 次')
            table_count = first_u32(values, 'input_device_table_count')
            selected_id = first_u32(values, 'input_device_selected_id')
            print(f'  设备表里共 {table_count} 台；**当次选中**的设备号 = {selected_id}'
                  + ('（0 = 一台都没选中）' if selected_id == 0 else ''))
            print('  （★ 批次 226：这几行与下面的原始内存是**同一帧、同一次解析**采的 ——'
                  ' 上一版把设备指针缓存了，会出现"表里没有手柄、却还拿旧指针读内容"的自相矛盾）')
            for index in range(min(table_count, 8)):
                low = first_u32(values, 'input_device_table_pointer', index)
                high = first_u32(values, 'input_device_table_pointer_high', index)
                did = first_u32(values, 'input_device_table_id', index)
                if low == 0xFFFFFFFF and high == 0xFFFFFFFF:
                    print(f'    第 {index} 台：**读失败**（哨兵 ⇒ 不是"值真的是 0"）')
                else:
                    print(f'    第 {index} 台：指针 = {(high << 32) | low:#018x}、设备号 = {did}')
            head = [first_u32(values, 'input_device_raw_head', i) for i in range(128)]
            known_fields = {
                0x00: 'vtable（低 32 位）', 0x08: '设备号 GetId', 0x0C: '标志字节（有 setter）',
                0x0D: '设备启用字节', 0x1C: '动作数', 0x20: '动作→按钮数组的指针表',
                0x30: '本帧按键位图', 0x38: '上帧按键位图',
                0x40: '本帧摇杆方向位图', 0x48: '上帧摇杆方向位图',
                0x50: '（Poll 摇杆段起点）', 0xD0: '每动作模拟量 指针（本帧）',
                0xD8: '每动作模拟量 指针（上帧）', 0xE0: '死区 A', 0xE4: '死区 B（动作判定用）',
            }
            print('  ★ 原始 128 个 u32（`+0x00`..`+0x1FF`），每行 4 个：')
            for row in range(0, 128, 4):
                cells = '  '.join(f'{head[row + col]:#010x}' for col in range(4))
                note = ''
                for known_offset, text in known_fields.items():
                    if known_offset // 4 == row:
                        note = f'   ← {text}'
                        break
                print(f'    +0x{row * 4:03x}: {cells}{note}')
            print('  ★ 这一段里**非 0 且不是已知字段**的格子（先看这些）：')
            for index, word in enumerate(head):
                offset = index * 4
                if word != 0 and offset not in known_fields:
                    as_float = _struct4.unpack('<f', _struct4.pack('<I', word))[0]
                    print(f'    +0x{offset:03x}: {word:#010x}（当 float 看 ≈ {as_float:+.4f}）')
            tail = [first_u32(values, 'input_device_raw_tail', i) for i in range(40)]
            print('  ★ 原始 40 个 u32（`+0x400`..`+0x49F`，`Poll` 的摇杆段里出现过 `+0x478`）：')
            for row in range(0, 40, 4):
                cells = '  '.join(f'{tail[row + col]:#010x}' for col in range(4))
                print(f'    +0x{0x400 + row * 4:03x}: {cells}')
            for label, key, offset in (('本帧', 'input_device_raw_values', 0xD0),
                                       ('上帧', 'input_device_raw_values_previous', 0xD8)):
                floats = [_struct4.unpack(
                    '<f', _struct4.pack('<I', first_u32(values, key, i)))[0] for i in range(32)]
                nonzero = [(i, v) for i, v in enumerate(floats) if v != 0.0 and v == v]
                print(f'  ★ `*(设备+{offset:#x})` 指向的那 32 格（{label}）：'
                      + ('（全 0）' if not nonzero else ''))
                for index, value in nonzero:
                    print(f'    [{index:2d}] = {value:+.4f}'
                          + ('   ← 超过 0.5 死区 ⇒ 会被答成"按住"' if abs(value) > 0.5 else ''))
        print('  ⇒ 说明：上面是**原始字节**。把"引擎自己对每个动作的答案"（上一节）与这里的格子对齐，')
        print('     就能看出"哪个动作号是被哪一格/哪一位撑起来的"—— 这一步在读数之后做，不在设备上做。')

    # 批次 235：启动期"读模组"分段计时（只在 `DIAGNOSTIC_PROBES=1` 的包里存在）。
    # ★ 判据用**符号在不在**（`SYMS` 是 defaultdict，缺的键取出来是 0 ⇒ 只按"值是不是 0"
    #   判断会把"正式包"和"这次没走到这条路"混起来）。正式包没有这个符号 ⇒ 整段不打印。
    if SYMS.get('g_LoadTotalMicros'):
        print()
        print('=== 启动期「读模组」分段计时（批次 235；只在 DIAGNOSTIC_PROBES=1 的包里存在）===')
        total = first_u32(values, 'load_total_micros')
        if total == 0:
            print('  总耗时 = 0 ⇒ 这段没跑到（或本次是"跳过读模组"那条路：卡上有 `no-lua.on`）')
            print('  （也可能这份 ELF 是在宿主上跑的：宿主侧 `cntpct_el0` 读数恒 0 ⇒ 全是 0）')
        else:
            phase_names = {
                0: '整个加载函数',
                1: '读清单 + 列目录 + 读存档里的模组开关',
                2: '给每个模组注册内容挂载点',
                3: '把模组的 content 喂给引擎（LoadCostumes / Music::LoadConfig）',
                4: '我们自带菜单那个模组',
                5: '跑所有模组脚本（逐个读 SD 上的入口脚本并执行）',
            }
            print(f'  ★ 整个加载函数总耗时 = {total} µs（约 {total / 1000.0:.1f} ms）')
            used = first_u32(values, 'load_frames_used')
            if used == 1:
                print('  ★★ 这条加载**只跨了 1 帧** ⇒ 拆帧**没生效**（整条路还是在一帧里跑完）'
                      '—— 那是拆帧实现的问题，不是模组的问题')
            elif used:
                print(f'  ★ 这条加载跨了 {used} 帧（≈{used / 60.0:.2f} 秒 @60fps）'
                      f'⇒ 拆帧生效了；若画面仍看起来"卡住"，说明**每一帧仍然很重**')
            else:
                print('  （跨帧数 = 0 ⇒ 走的可能是"跳过读模组"那条路）')
            for index in range(6):
                micros = u32_at(values, 'load_phase_micros', index)
                name = phase_names.get(index, f'（下标 {index}）')
                share = (micros * 100.0 / total) if total else 0.0
                print(f'    [{index}] {name:<52} {micros:>9} µs  （{share:5.1f}%）')
            count = first_u32(values, 'mod_load_count')
            total_mods = first_u32(values, 'mod_load_total')
            print(f'  逐模组耗时（本次共 {total_mods} 个模组，记下了 {count} 个）：')
            if count == 0:
                print('    （一个都没记下 ⇒ `LoadAll` 没进循环，或没走到那个计时点）')
            for index in range(min(count, 16)):
                print(f'    #{index}: {u32_at(values, "mod_load_micros", index):>9} µs')
            print('  ⇒ 判读：哪一段占大头，修法就落在哪 —— 见 `runtime/source/load_phase_probe.hpp` 顶部的分支说明。')

    # 批次 227：一致性验证 —— "我读的表"在变吗？"我选的项"在表里吗？
    if 'input_device_raw_manager_low' in values:
        manager_ptr = (first_u32(values, 'input_device_raw_manager_high') << 32) | \
            first_u32(values, 'input_device_raw_manager_low')
        begin1 = (first_u32(values, 'input_device_raw_begin_high') << 32) | \
            first_u32(values, 'input_device_raw_begin_low')
        end1 = (first_u32(values, 'input_device_raw_end_high') << 32) | \
            first_u32(values, 'input_device_raw_end_low')
        begin2 = (first_u32(values, 'input_device_raw_begin_pass2_high') << 32) | \
            first_u32(values, 'input_device_raw_begin_pass2_low')
        end2 = (first_u32(values, 'input_device_raw_end_pass2_high') << 32) | \
            first_u32(values, 'input_device_raw_end_pass2_low')
        selected_index = first_u32(values, 'input_device_selected_index')
        print()
        print('=== 一致性验证（批次 227）：我读的表在变吗？我选的项在表里吗？===')
        print(f'  `manager` 指针 = {manager_ptr:#018x}')
        print(f'  第 1 遍：向量 begin = {begin1:#018x}、end = {end1:#018x}'
              f'（{max(end1 - begin1, 0) // 8} 项）')
        print(f'  第 2 遍：向量 begin = {begin2:#018x}、end = {end2:#018x}'
              f'（{max(end2 - begin2, 0) // 8} 项）')
        if begin1 == begin2 and end1 == end2:
            print('  ⇒ 两遍的向量范围**相同** ⇒ **表没有变**：'
                  '那"选中 33 却表里没有 33"就只能是"选"与"打印"用的不是同一处')
        else:
            print('  ⇒ ★ 两遍的向量范围**不同** ⇒ **表在两次读之间变了/被重建**'
                  '（那就把采样固定在进局稳定之后的时刻，别在切换瞬间采）')
        failures = first_u32(values, 'input_device_table_read_failures')
        print(f'  读表失败次数（累计）= {failures}'
              + ('　⇒ 有格子读不到，"读失败"那种行是正常的，**别当成"值是 0"**'
                 if failures else '（0 = 每次都读到了）'))
        count2 = first_u32(values, 'input_device_table_pass2_count')
        print(f'  第 2 遍的表内容（共 {count2} 项）：')
        for index in range(min(count2, 8)):
            low = first_u32(values, 'input_device_table_pass2_pointer', index)
            high = first_u32(values, 'input_device_table_pass2_pointer_high', index)
            did = first_u32(values, 'input_device_table_pass2_id', index)
            if low == 0xFFFFFFFF and high == 0xFFFFFFFF:
                print(f'    第 {index} 台：**读失败**（哨兵 ⇒ 不是"值真的是 0"）')
            else:
                print(f'    第 {index} 台：指针 = {(high << 32) | low:#018x}、设备号 = {did}')
        print('  选中的那台在**第 1 遍**表里的下标 = '
              + ('**不在表里**（0xFFFFFFFF）⇒ 「选」与「打印」用的**不是同一处**'
                 if selected_index == 0xFFFFFFFF else str(selected_index)))

    # 批次 214：`Seeds:AddSeedEffect` / `RemoveSeedEffect` 被调用的次数。
    # 这两条**按设计不生效**（引擎唯一入口吃"名字字符串"，我们拿不到"枚举 → 名字"那条路）
    # ⇒ 计数 >0 是"模组真的走了那两条、而我们没抛错打断它"的唯一证据；
    # 计数 =0 且 MCM 明明开过菜单 ⇒ 说明它走的不是这两条（或压根没到那一步），别去查偏移。
    if 'seeds_effect_write_attempts' in values:
        attempts = first_u32(values, 'seeds_effect_write_attempts')
        print()
        print('=== 种子效果写（`Seeds:AddSeedEffect` / `RemoveSeedEffect`）===')
        print(f'  被调用 = {attempts} 次'
              + ('　⇒ 模组真的走了这两条；它们**按设计不生效**（空实现，理由见台账），'
                 '但**没有抛错**（抛错会打断调用方整条回调）。' if attempts
                 else '（一次都没被调过）'))
    # 注意：这里**不**用上面那段里的 `catalog_names` —— 它只在"有 API 桶"时才会被赋值
    # （生产构建下桶是空的），照抄会直接 NameError。接口名现算。
    print_degradation_surface()


# ---------------------------------------------------------------------------
# 风险面：还在返回兜底值的接口（数据来自仓库里的偏离台账，不是设备读数）
# ---------------------------------------------------------------------------
#
# 为什么要放在**每一次读数**里（2026-09-20 批次 099，由 098 事故推动）：
# `Room:GetGridPath` 恒返回 1000 那条偏离**登记过**，但"后果"写的是"不画路径提示"，
# 真相是"地上每一颗药丸/卡片只显示问号"—— 登记了却没人看、后果还写错了。
# ⇒ 把"还有哪些接口不是真值"摊在每次读数旁边：风险面在眼前，而不是等人踩上去。
#
# ★ 2026-09-21（批次 017）：这一段**按性质分组**打印（platform 平台固有 / debt 我们的欠账 /
#   design 主动保留的口径差异），因为"这条差异还能不能还"决定了下一步该做什么 ——
#   平台固有的登记完就别再投入，欠账要排期还。**只改了打印**：本工具的偏移表（`SYMS`）与
#   一切读设备内存的逻辑都没有动（那个工具很敏感，偏移错了会误读现场）。
def print_degradation_surface() -> None:
    """打印偏离台账的现状（**按性质分组** + 接口名 + 后果 + 判据），缺账本时如实说明而不是静默跳过。"""
    try:
        sys.path.insert(0, str(ROOT / 'tools'))
        from api_deviation_ledger import (
            CONSEQUENCE_MARKER, NATURE_LABELS, by_nature, group_order, load_entries, summarise)
    except ImportError as error:  # 换台机器只拷了工具、没拷台账（或是旧版账本模块）
        print()
        print(f'=== 还在返回兜底值的接口（风险面）===')
        print(f'  ⚠ 读不到偏离台账（{error}）⇒ 这一段跳过；'
              f'别把"没打印"当成"没有偏离"')
        return
    try:
        entries = load_entries()
    except (OSError, ValueError) as error:
        print()
        print('=== 还在返回兜底值的接口（风险面）===')
        print(f'  ⚠ 台账解析失败（{error}）⇒ 这一段跳过')
        return

    try:
        catalog_names = api_catalog_names()
    except Exception:  # 目录读不到不该让整份读数崩掉，最多是名字显示成 id
        catalog_names = {}
    stats = summarise(entries)
    by_kind = '、'.join(f'{kind} {count}' for kind, count in sorted(stats['by_kind'].items()))
    groups = by_nature(entries)
    by_nature_text = '、'.join(
        f'{nature or "<未归类>"}（{NATURE_LABELS.get(nature, "未归类")}）{len(groups[nature])}'
        for nature in group_order(groups))
    gaps = stats['missing_judgement']
    suffix = f'（{gaps}）' if gaps else ''
    print()
    print('=== 还在返回兜底值/近似值的接口（风险面；数据来自 api_deviation.cpp）===')
    print(f'  共 {stats["total"]} 条偏离：{by_nature_text}；其中"暂无判据" {len(gaps)} 条{suffix}')
    print(f'  （偏离种类分布：{by_kind}）')
    print('  ★ 性质口径决定"这条差异还能不能还"：platform = 平台固有（Switch 上没有底座/语义无法映射，'
          '永远消不掉，登记完就别再投入）；')
    print('    debt = 我们的欠账（底座存在或可定位，能还，还清后应当把条目删掉）；'
          'design = 主动保留的口径差异（有意与 PC 不同，不打算改）。')
    print('  ★ 这些接口交回的不是引擎真值。模组拿它们当判据时会出现"看着正常、其实答错"的行为')
    print('     （098 的实例：`Room:GetGridPath` 恒返 1000 ⇒ EID 认为地上药丸/卡片都够不到、只画问号）。')
    for nature in group_order(groups):
        label = NATURE_LABELS.get(nature, '未归类（取值非法或缺失 —— 门禁会红）')
        print(f'  ── [{nature or "<未归类>"}] {label}：{len(groups[nature])} 条 ──')
        for entry in groups[nature]:
            name = catalog_names.get(entry.identifier) or f'未知 id 0x{entry.identifier:08X}'
            reason = entry.nature_reason.replace('\n', ' ')
            consequence = entry.consequence.replace('\n', ' ')
            judgement = entry.judgement.replace('\n', ' ')
            if len(reason) > 110:
                reason = reason[:110] + '…'
            if len(consequence) > 110:
                consequence = consequence[:110] + '…'
            if len(judgement) > 110:
                judgement = judgement[:110] + '…'
            print(f'  · 0x{entry.identifier:08X} {name}'
                  f'（kind={entry.kind} / nature={nature or "未归类"}）')
            # ★ 批次 161：形状两栏（有就打印）。`PC 形状` 不是 nil、我们是 nil 的那些，
            #   模组照 PC 的用法往下链就会**抛错并把整条回调摘掉**（`GetMainTwin` 那次的事故）
            #   ⇒ 读数里必须一眼看得见，不能只在台账正文里。
            if entry.has_pc_shape or entry.has_our_shape:
                print(f'      形状：PC = {entry.pc_shape or "**缺**"} / '
                      f'我们 = {entry.our_shape or "**缺**"}'
                      + ('　← ★ 链式调用会抛错（后果里已写明）'
                         if entry.needs_chaining_warning else ''))
            print(f'      理由：{reason or "**缺 性质：…——理由：…**（门禁会红）"}')
            print(f'      后果：{consequence or f"**缺 {CONSEQUENCE_MARKER}**（门禁会红）"}')
            print('      ' + (f'判据：{judgement}' if judgement else '**缺判据：……**（门禁会红）'))
    print('  （完整正文与判据：`python3 tools/api_deviation_ledger.py`（已按性质分组）；'
          'JSON：`python3 tools/api_deviation_ledger.py --json`；'
          '条数与每类条数由 `runtime/tests/contract/test_api_deviation.py` 钉住）')


# ---------------------------------------------------------------------------
# 备用：两段式（各一次 attach），老流程，留作对照
# ---------------------------------------------------------------------------

def run_gdb_batch(commands: list[str], timeout: int = 120) -> str:
    with tempfile.NamedTemporaryFile('w', suffix='.cmd', delete=False) as fh:
        fh.write('set pagination off\nset confirm off\n')
        fh.write('\n'.join(commands) + '\nquit\n')
        path = fh.name
    cmd = ['docker', 'run', '--rm', '-v', f'{path}:/gdb.cmd:ro', GDB_IMAGE, 'bash', '-lc',
           f'. /opt/devkitpro/devkita64.sh && timeout {timeout} aarch64-none-elf-gdb -batch -x /gdb.cmd']
    try:
        return subprocess.run(cmd, capture_output=True, text=True).stdout
    finally:
        Path(path).unlink(missing_ok=True)


def header(ip: str) -> list[str]:
    return [f'target extended-remote {ip}:22225']


def run_two_phase(ip: str, elf: Path, pid: int = 0, base: int = 0, game_base: int = 0,
                  plugin_base: int = 0) -> int:
    """老流程：找进程一次、取基址一次、读身份一次、读变量一次 = 四次 attach。费预算，慎用。"""
    if not pid:
        out = run_gdb_batch(header(ip) + ['info os processes'], timeout=60)
        pid = parse_processes(out) or 0
    if not pid:
        print('没找到正在运行的 Application，请先启动游戏。')
        return 3
    if not base or not game_base:
        out = run_gdb_batch(header(ip) + [f'attach {pid}', 'monitor get info', 'detach'])
        module, plugin, game = parse_bases(out)
        base = base or (module or 0)
        plugin_base = plugin_base or (plugin or 0)
        game_base = game_base or (game or 0)
    if not base or not game_base:
        print('定位不到模块基址（调试桩的 monitor 输出缺失）。可加 --base/--game-base 指定。')
        return 3
    print(f'进程 = {pid}；运行时模块基址 = 0x{base:x}；游戏模块基址 = 0x{game_base:x}')

    requests, skipped = build_requests(base, game_base, plugin_base)
    if skipped:
        print('  ⚠ 这些量没有偏移（本次不读，不影响其它读数）：' + '、'.join(skipped))
    cmds = header(ip) + [f'attach {pid}']
    for label, addr, count in requests:
        cmds.append(f'printf "TAG {label}\\n"')
        cmds.append(f'x/{count}gx 0x{addr:x}')
    cmds.extend(mod_data_payload_commands(base))
    cmds.append('detach')
    out = run_gdb_batch(cmds)
    values = parse_words(out)

    for name in ANCHOR_NAMES:
        expect = local_bytes(elf, SYMS[name], 16)
        got = b''.join(v.to_bytes(8, 'little') for v in values.get(
            {'identity': 'anchors', 'exl_main': 'anchor_exl_main',
             'manifest_install': 'anchor_manifest'}[name], [])[:2])
        if expect is None or got != expect:
            print(f'偏移自校验失败（锚点 {name}）：设备 {got.hex()} / 本地 '
                  f'{expect.hex() if expect else "(读不到)"}')
            return 4
    print('偏移自校验通过（三个代码锚点逐字节一致）')
    report(values, base, game_base, plugin_base)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--ip', default='192.168.124.11')
    ap.add_argument('--pid', type=int, default=0)
    ap.add_argument('--base', type=lambda s: int(s, 0), default=0, help='运行时模块基址（十六进制）')
    ap.add_argument('--game-base', type=lambda s: int(s, 0), default=0,
                    help='游戏模块（Repentance.nrs.elf）基址；GOT 槽与 Present 偏移相对它')
    ap.add_argument('--plugin-base', type=lambda s: int(s, 0), default=0)
    ap.add_argument('--elf', default=DEFAULT_ELF)
    ap.add_argument('--two-phase', action='store_true',
                    help='走老流程（四次 attach，费调试桩预算），只在一次挂载失败时用')
    ap.add_argument('--dry-run', action='store_true', help='只测 gdb 管道，不连设备')
    ap.add_argument('--read', default='',
                    help='额外读任意地址：ADDR:WORDS[,ADDR:WORDS...]（地址十六进制/十进制都行；'
                         '⚠️ **WORDS 是 8 字节字的个数，不是字节数** —— 32 表示 256 字节）。'
                         '读回来的原始字节会打印成十六进制。'
                         '用途：探针把"像指针"的值记下来之后，直接把那些地址的内容读回来 —— '
                         '不必为了多知道几个字节就再烧一次 attach。')
    ap.add_argument('--from-raw', default='',
                    help='离线重放某次读数（不连设备）：换解码/改解释时用，别再烧调试桩预算')
    args = ap.parse_args()

    elf = ROOT / args.elf
    if not elf.exists():
        print(f'找不到本地重建的模块 ELF：{args.elf}')
        print('偏移自校验需要它。先在本地用同一套旗标重建：')
        print('  docker run --rm -v "$PWD":/work -w /work devkitpro/devkita64:latest bash -lc \\')
        print('    ". /opt/devkitpro/devkita64.sh && make -C runtime -j6 LAYERED_RUNTIME=1 \\')
        print('     PROBE_BREAK=0 OUT=.gdbsym-artifacts/deploy BUILD=.gdbsym-build \\')
        print('     EXL_ARTIFACT_DIR=.gdbsym-artifacts all"')
        return 2

    # 偏移表以**本地这份构建**为准：手抄表会随任何一次重建过期（项目已因此误读过两次）。
    sync_syms_from_elf(elf, verbose=True)

    if args.dry_run:
        session = GdbSession(timeout=60)
        try:
            print(session.command('echo @@管道_ok@@').strip())
            print(session.command('show version').splitlines()[0])
        finally:
            session.close()
        return 0

    if args.from_raw:
        text, raw_base, raw_game, raw_plugin = load_raw(ROOT / args.from_raw)
        values = parse_words(text)
        base = args.base or raw_base
        game_base = args.game_base or raw_game
        plugin_base = args.plugin_base or raw_plugin
        print(f'离线重放 {args.from_raw}：运行时基址 = 0x{base:x}；游戏模块基址 = 0x{game_base:x}')
        for key, source in recover_font_storage_from_raw(text, base, values).items():
            print(f'  恢复 {key} = {values[key][0]}：{source}')
        report(values, base, game_base, plugin_base)
        return 0

    if args.two_phase:
        return run_two_phase(args.ip, elf, args.pid, args.base, args.game_base, args.plugin_base)
    return run_one_shot(args.ip, elf, args.pid, args.base, args.game_base, args.plugin_base,
                        parse_extra_reads(args.read))


if __name__ == '__main__':
    sys.exit(main())
