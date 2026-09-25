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
GDB_IMAGE = 'devkitpro/devkita64:latest'
DEFAULT_ELF = 'runtime/.gdbsym-artifacts/runtime.elf'

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
    # ---- 代码锚点（只用于核对版本，不作为"变量"读）----
    'identity': 0x27e48,              # IsaacModRuntime_GetRuntimeIdentity
    'exl_main': 0x8890,               # 模块入口（旧表写 0x8840，那是 20:00 那次的构建）
    'manifest_install': 0x361c,       # TryInstallDefaultManifestMod（本次诊断改的就是它）
    'entry_relay_update': 0x1910,     # EntryRelayManagerUpdateCallback（更新挂点入口中继）
    'entry_relay_render': 0x1904,     # EntryRelayManagerRenderCallback（渲染挂点）
    'entry_relay_collectible': 0x1f7c,  # EntryRelayPreGetCollectibleCallback
    'entry_relay_rebuild': 0x1ff8,    # EntryRelayRebuildMountPointsCallback
    'present_got_intercept': 0x16e4,  # IsaacModRuntime_PresentGotSlotIntercept
    # ---- 运行状态（相对我们的运行时模块）----
    'g_runtimeSelfAddress': 0x23476b8,
    'g_sequence': 0x2347940,          # TestRunObserver 状态机：走过的步数
    'g_stateDetail': 0x2347948,       # 低 32 位 = 状态号，高 32 位 = 该步的 detail
    'g_diagnosticFileApi': 0x23478f8,
    'g_hookCallbacks': 0x2339620,
    'g_HookInstallResults': 0x2345c8,   # 16 字诊断数组（线格式，见 IsaacModRuntime_GetHookDiagnostics）
    'g_HookEnabled': 0x234610,
    'g_RenderPresentRelayState': 0x2345bc,
    # 2026-09-16 卡上开关（一份包测多种配置，见 hook_manager.cpp 的那一节）：
    #   [0] 掩码：bit i = 第 i 个名字的 `<名字>.on` 在卡上（位序见 CARD_SWITCH_NAMES）
    #   [1] 通道：bit0 = 至少一次查询成功；bit1 = 至少一次查询失败（通道不可用）
    # 没这两个量就分不清"开关没读到"与"开关生效了但没用"——那会把整个二分带偏。
    'g_CardSwitchMask': 0x0,
    'g_CardSwitchChannel': 0x0,
    'g_PresentGotSlotTarget': 0xb40f0,
    # ---- 2026-09-14 夜间加：清单/挂点失败原因（这次读数的主角）----
    'g_DefaultManifestFailureWord': 0x234598,   # 诊断字 [11]，打包格式见 mod_load_step.hpp
    'g_DefaultManifestFailureDetail': 0x23459c,  # 步骤字（1..4 失败、5 纯资源、6 自动发现）
    'g_DefaultManifestState': 0x2345a0,
    # 清单 + 扫目录的合并结果（2026-09-21：「拷进 mods/ 就能用」）：
    #   [0] = 除清单之外多追加了几个目录；[1] = 合并状态码（0 = 成功）
    'g_AutoAppendedMods': 0x0,
    'g_AutoAppendStatus': 0x0,          # 0 未武装 1 已武装 2 安装中 3 就绪 4 失败
    'g_HookInstallFailureCode': 0x234614,        # 入口中继后端转发的失败码（0 = 无失败）
    'g_HookInstallFailureSlot': 0x234618,        # 第一个失败挂点 index+1（0 = 没有装失败的）
    'g_HookInstallInstalledCount': 0x23461c,     # 装好的挂点数（函数内静态，见 SYM_ELF_NAMES）
    # 贴图桥（2026-09-21）：转码失败计数（u32）与最近一次请求的路径（128 字节 C 串，
    # 零散读词后按 ASCII 解码——用来在真机上确认引擎传进回调的路径形状）。
    'image_pcx_bindings': 0x0,
    # 模组数据容器（`ModPersistence::detail::g_cache`）的**尾部字段**：payload 是 16 KiB，
    # 尾部依次是 payloadLength(u64)/generation(u64)/loaded(u8)/exists(u8)。
    # 取值时用 `SYMS['g_ModDataCache'] + 0x4000`（见 build_requests 的 `mod_data_tail`）。
    'g_ModDataCache': 0x2353208,
    'g_PendingGameStarted': 0x234624,            # 待派发的"游戏开局"事件
    # ---- Lua 侧 ----
    'g_ModRegistered': 0x334da4,       # 模组是否登记成功（1 字节；= Lua 真的跑起来了）
    # 回调派发次数（无 ELF 时的兜底偏移；有 ELF 时由 `sync_syms_from_elf()` 刷新）
    'g_UpdateCallbackEntries': 0x2345b0,
    'g_RenderCallbackEntries': 0x2345b4,
    # 自 journal（模块**自己**用 libnx fs 写 SD 的那条路）：会话状态与最后一条记录。
    # 这些量没有兜底偏移 —— 没有 ELF 就如实报"读不到"，绝不用别的地址凑。
    # 2026-09-16 多模组加载：登记成功的 Mod **个数**（清单里有几个 enabled，就该是几）。
    # 偏移由 `sync_syms_from_elf()` 按符号名自动同步，这里只是无 ELF 时的兜底值。
    'g_ModRegisteredCount': 0x334da8,
    'g_LastLuaErrorLength': 0x334c94,
    'g_LastLuaErrorText': 0x334c98,    # 256 字节文本
    'g_PostUpdateCount': 0x334c80,
    # 回调派发计数（2026-09-18 新增，见 `callback_dispatcher.hpp`）：74 个 u32，下标就是 PC
    # `ModCallbacks` 的数值；相邻两个标量**分散**排布（链接器重排过），所以各读各的地址。
    # 无 ELF 时下面这三个兜底值不可信 —— 一律靠 `sync_syms_from_elf()` 按符号名同步。
    'g_CallbackDispatchCounts': 0x0,
    'g_LastDispatchedCallbackId': 0x0,
    'g_CallbackDispatchGeneration': 0x0,
    'g_CallbackRegistry': 0xa0578,     # 回调登记表：布局见下面的 `CALLBACK_REGISTRY_*` 常量
    # ---- 运行时读进来的文件内容（诊断"模组为什么算纯资源型"的关键）----
    'g_DefaultManifest': 0x1b4560,     # 上次读进来的 `manifest.json` 原文（512 KiB 缓冲）
    'g_DefaultEntry': 0xb4560,         # 上次读进来的入口脚本原文（1 MiB 缓冲）
    # ---- 游戏开局中继的三格（相对**游戏模块**；来源 `runtime_constants.hpp` 的
    #      `kGameStart*` 常量。`--elf` 同步不会碰它们，因为它们是游戏模块的偏移、不是我们的符号）----
    'gamestart_saved_callsite': 0x3F92A4,
    'gamestart_new_callsite': 0x3F93F8,
    'gamestart_relay_slot': 0x68CCC0,
    # ---- 下面三条都相对**游戏模块**----
    'manager_update_entry': 0x3F8DB8,  # `Manager::Update` 入口（该是原样 `ff4301d1...`）
    'manager_render_entry': 0x3F9684,  # `Manager::Render` 入口（该是原样 `ffc302d1...`）
    'present_callsite_offset': 0x3F9B40,  # `Manager::Render` 体内那次 `bl Present`
    'present_got_slot': 0xA9E488,      # Present 的 GOT 槽（应等于 运行时基址 + present_got_intercept）
    'present_target': 0x4F3014,        # `Present` 本体（期望值比对用）
})
#: 上表里"属于**我们运行时模块**"的那些键 → 它们在本地 ELF 里的**精确符号名**。
#: 有这张表，偏移就不必再靠人手抄：`sync_syms_from_elf()` 每次读数前直接问 ELF。
#: 不在表里的键（`manager_update_entry` 那几条）是**游戏模块**的常量，与我们的重建无关，保持原值。

SYM_ELF_NAMES = {
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
    'entry_relay_room_entity_spawn': 'EntryRelayRoomEntitySpawnCallback',
    'entry_relay_image_pcx_load': 'EntryRelayImagePcxLoadCallback',
    'entry_relay_image_mgr_load': 'EntryRelayImageManagerLoadFileCallback',
    'entry_relay_get_mounted_path': 'EntryRelayContentGetMountedFilePathCallback',
    # 贴图桥：**唯一**诊断入口（固定布局结构体，见 hook_manager.cpp 的 ImagePcxDiagnostics）。
    'image_pcx_diag': '_ZN12_GLOBAL__N_1L14g_imagePcxDiagE',
    'image_pcx_bindings': '_ZN12_GLOBAL__N_1L18g_ImagePcxBindingsE',
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
    'g_ApiSequence': '_ZZN5isaac7runtime6detail11ApiSequenceEvE5state',
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
    'g_InputActionTriggeredMask': '_ZN5isaac7runtime26g_InputActionTriggeredMaskE',
    # 批次 109：每个动作报过几次"刚按下"（32 个 u32，下标 = 动作号 & 31）。
    'g_InputEdgeCounts': '_ZN5isaac7runtime17g_InputEdgeCountsE',
    # 批次 110：每个动作观察到的最长"闪断"帧数（按住期间连续多少帧读到"没按住"）。
    'g_InputReleaseRunPeak': '_ZN5isaac7runtime21g_InputReleaseRunPeakE',
    'g_InputActionTriggeredMaskOther': '_ZN5isaac7runtime31g_InputActionTriggeredMaskOtherE',
    'g_InputActionPressedMask': '_ZN5isaac7runtime24g_InputActionPressedMaskE',
    'g_InputActionPressedMaskOther': '_ZN5isaac7runtime29g_InputActionPressedMaskOtherE',
    'g_InputLastController': '_ZN5isaac7runtime21g_InputLastControllerE',
    'g_InputPressedControllerMask': '_ZN5isaac7runtime28g_InputPressedControllerMaskE',
    'g_InputTriggeredControllerMask': '_ZN5isaac7runtime30g_InputTriggeredControllerMaskE',
    'g_InputLastActionCode': '_ZN5isaac7runtime21g_InputLastActionCodeE',
    'g_InputLastActionResult': '_ZN5isaac7runtime23g_InputLastActionResultE',
    'g_ModMenuLastCode': '_ZN5isaac7runtime17g_ModMenuLastCodeE',
    'g_ModMenuMilestones': '_ZN5isaac7runtime19g_ModMenuMilestonesE',
    'g_ModMenuReportCount': '_ZN5isaac7runtime20g_ModMenuReportCountE',
    'g_FontDrawCalls': '_ZN5isaac7runtime15g_FontDrawCallsE',
    'g_FontDrawBytes': '_ZN5isaac7runtime15g_FontDrawBytesE',
    'g_FontLoadCalls': '_ZN5isaac7runtime15g_FontLoadCallsE',
    'g_FontLoadResult': '_ZN5isaac7runtime16g_FontLoadResultE',
    # ---- 数据行 API 的"调用 / 静默降级"计数器（批次 069，2026-09-19）----
    # 存在的唯一目的：**不再靠探针回答"这条 API 到底有没有被调到"**。
    # 数据行处理器（字段行 `FieldApiHandler` / 引擎方法行 `EngineMethodHandler`）拿不到接收者、
    # 偏移或入口指纹时**静默降级**（不报错），于是"没生效"与"没被调用"在设备上分不开 ——
    # 下面这九个量就是分开它们的那把尺子。名字是 `extern "C"` 的，不进名称改编。
    'g_IsaacApiRowCalls': 'g_IsaacApiRowCalls',
    'g_IsaacApiRowLastCallId': 'g_IsaacApiRowLastCallId',
    'g_IsaacApiRowLastCallKind': 'g_IsaacApiRowLastCallKind',
    'g_IsaacEngineRowCalls': 'g_IsaacEngineRowCalls',
    'g_IsaacEngineRowRejectReceiver': 'g_IsaacEngineRowRejectReceiver',
    'g_IsaacEngineRowRejectOffset': 'g_IsaacEngineRowRejectOffset',
    'g_IsaacEngineRowRejectEntry': 'g_IsaacEngineRowRejectEntry',
    'g_IsaacEngineRowLastRejectId': 'g_IsaacEngineRowLastRejectId',
    'g_IsaacEngineRowLastRejectReason': 'g_IsaacEngineRowLastRejectReason',
    # ---- `RoomDescriptor.Data` 读不出来时的现场（批次 071）----
    # 真机上 `crd.Data` 返回 nil 让 GoodTrip 的 `MC_POST_NEW_ROOM` 回调每次崩
    # （`control.lua:339`）。这几个量回答"是哪种房间、描述符对不对"：
    # GridIndex = 0xFFFFFFFF 表示那个槽位**没填**（我们拿到的是引擎的空描述符）；
    # GridIndex 正常而 Data 仍读不到 ⇒ 那个房间确实没有配置对象（贪婪模式一类）。
    'g_IsaacRoomDescDataMisses': 'g_IsaacRoomDescDataMisses',
    'g_IsaacRoomDescDataGridIndex': 'g_IsaacRoomDescDataGridIndex',
    'g_IsaacRoomDescDataSafeGridIndex': 'g_IsaacRoomDescDataSafeGridIndex',
    'g_IsaacRoomDescDataListIndex': 'g_IsaacRoomDescDataListIndex',
    'g_IsaacRoomDescDataDescriptorLow': 'g_IsaacRoomDescDataDescriptorLow',
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
    'g_RuntimePerfEmptyCallTicks': 'g_RuntimePerfEmptyCallTicks',
    'g_RuntimePerfEmptyCallCount': 'g_RuntimePerfEmptyCallCount',
    'g_RuntimePerfAllocCalls': 'g_RuntimePerfAllocCalls',
    'g_RuntimePerfAllocBytes': 'g_RuntimePerfAllocBytes',
    'g_RuntimePerfAllocNewCalls': 'g_RuntimePerfAllocNewCalls',
    'g_RuntimePerfFreeCalls': 'g_RuntimePerfFreeCalls',
    # ---- 模组那一行 + 模组页（**生产版**，批次 077）--------------------------------
    # 状态面结构体在 `runtime/source/mod_menu_native.hpp`（20 个 u32），定义在 `.cpp` 里。
    # ★★ 符号名是**裸名**，不是改编名：它声明成 `extern "C"`（C 语言链接 ⇒ 不加命名空间前缀、
    #    不做名称改编）。**别照抄探针那一行** —— 探针那份是普通 C++ 全局，
    #    符号是 `_ZN5isaac7runtime5probe26g_NativeModsMenuProbeStateE`。
    #    核对办法：`nm -C runtime/.gdbsym-artifacts/runtime.elf | grep g_ModMenuState`。
    'mod_menu_state': 'g_ModMenuState',
}
#: **只在探针构建里存在**的符号（批次 019 起）。为什么要跟主表分开：
#: `runtime/tests/test_elf_syms.py` 钉住的是"主表里每一项都必须能在**当前生产 ELF** 里解析到"
#: —— 那是"偏移表不许过期"的守门人，不该为探针放宽。探针符号按定义在生产 ELF 里**不存在**
#: （`PROBE_BREAK=0` 时整个 TU 被编译掉），所以它们单独一张表：解析到就用，解析不到就删键
#: 并如实记账，主表那两条断言的语义一个字都不动。
#: 名字前缀是探针自己的命名空间 `isaac::runtime::probe`，同一条门禁里另有断言钉住这一点。
SYM_ELF_NAMES_PROBE_ONLY = {
    # 原生模组页探针的诊断字（**109 个 u32**，布局见 `native_mods_menu_probe.hpp` ——
    # 单元数由 `runtime/tests/test_probe_state_layout.py` 在 .cpp/.hpp/本工具三处一起钉住；
    # 这个注释以前写着"42 个 u32"（批次 019 时的数字），已经过期过很久）。
    'native_mods_probe': '_ZN5isaac7runtime5probe26g_NativeModsMenuProbeStateE',
}
#: 表里有、但**这次构建的 ELF 里已经找不到**的符号：不能沿用过期的偏移（那是"看起来有值、
#: 其实是别人的变量"），只能在读数时报"读不到"。这里只记账，方便汇报时说明缺了什么。
SYM_MISSING: dict[str, str] = {}
#: 已经不再存在的全局量（2026-09-15：装好的挂点数改为从 `g_HookInstallResults` 现算，没有独立变量）。
#: 曾经"这次构建里不存在"的全局量。2026-09-17 复查：`g_HookInstallInstalledCount` 其实是
#: `HookInstallInstalledCount()` 里的**函数内静态**（`_ZZN…HookInstallInstalledCountEvE5value`），
#: 现在在 SYM_ELF_NAMES 里指向了那个符号，所以从这个名单里拿掉。
SYM_UNRESOLVABLE = ()
_syms_synced = False

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
    'PersistentGameDataSetReadOnly',]
# 只用来做比对、本身不是"要读的内存变量"的符号（读数请求要跳过它们）。
SYM_ONLY = ('identity', 'manifest_install',
            'entry_relay_update', 'entry_relay_render',
            'entry_relay_collectible', 'entry_relay_rebuild',
            'entry_relay_use_active_item', 'entry_relay_use_card',
            'entry_relay_use_pill', 'entry_relay_game_exit',
            'entry_relay_pickup_collision', 'entry_relay_room_entity_spawn',
            'entry_relay_image_pcx_load', 'entry_relay_image_mgr_load',
            'entry_relay_get_mounted_path',
            'present_got_slot', 'present_target', 'present_callsite_offset')
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
                 'ContentGetMountedFilePath': 'entry_relay_get_mounted_path'}
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
    return values


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
    maps = parse_mappings(session.command('monitor get mappings'))
    if len(maps) < 3:
        # ★ 2026-09-19 实测：`attach` 刚返回时 `monitor get mappings` 可能只给一小部分段
        # （97 段、且**不含我们的代码段**）⇒ 候选只剩 1 个、基址取不到，白烧一次挂载。
        # 稍后同一次挂载再问一遍就能拿到完整的 148 段，所以这里重试一次。
        maps = parse_mappings(session.command('monitor get mappings')) or maps
    if not maps:
        return None, None
    candidates = scan_candidates(maps, SYMS['identity'] + 0x100)[:max_candidates]
    print(f'  （monitor get info 没给模块表，改用 mappings 扫描：{len(maps)} 段里 '
          f'{len(candidates)} 个可执行候选）')
    identity_expect = local_bytes(elf, SYMS['identity'], 16)
    cmds = []
    for i, start in enumerate(candidates):
        cmds.append(f'echo TAG cand_{i}\\n')
        cmds.append(f'x/2gx 0x{start + SYMS["identity"]:x}')
        cmds.append(f'echo TAG game_{i}\\n')
        cmds.append(f'x/2gx 0x{start + SYMS["manager_update_entry"]:x}')
    values = parse_words(session.command('\n'.join(cmds)))
    module = game = None
    for i, start in enumerate(candidates):
        got = b''.join(v.to_bytes(8, 'little') for v in (values.get(f'cand_{i}') or [])[:2])
        if got and got == identity_expect and module is None:
            module = start
        entry = values.get(f'game_{i}') or []
        if entry and game is None:
            word = entry[0] & 0xFFFFFFFF
            # 我们的入口中继桩（`ldr x16,#8; br x16`）或原版 `Manager::Update` 序言。
            if word in (0x58000050, 0xFF4301D1):
                game = start
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


def sync_syms_from_elf(elf: Path, *, verbose: bool = False) -> dict[str, str]:
    """用**本地这份 ELF**的符号表刷新"模块内偏移"，返回没解析到的符号。

    为什么要有这一步：偏移表是手抄的，而**改任何一个编译单元都会让 bss/data 整体挪位**
    （项目已经因此误读过两次）。手抄表一定会过期，唯一不会过期的来源就是 ELF 自己。
    解析不到的符号**直接从表里删掉**——沿用过期的偏移比读不到更糟：它会把别人的变量
    当成我们要的那个，读数"看起来有值"却是错的。
    """
    global _syms_synced
    tools_dir = str(Path(__file__).resolve().parent)
    if tools_dir not in sys.path:
        sys.path.insert(0, tools_dir)
    import elf_syms  # 同目录的极简 ELF 解析器（只依赖标准库）

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
    for key, name in {**SYM_ELF_NAMES, **SYM_ELF_NAMES_PROBE_ONLY}.items():
        hit = symbols.get(name)
        if hit is None:
            missing[key] = name
            SYMS.pop(key, None)
        else:
            SYMS[key] = hit[0]
    for key in SYM_UNRESOLVABLE:            # 这次构建里已经不存在的全局量
        SYMS.pop(key, None)
        missing[key] = '（本构建已无此全局量）'
    SYM_MISSING.clear()
    SYM_MISSING.update(missing)
    _syms_synced = True
    if verbose:
        print(f'  偏移已按 {elf.name} 的符号表刷新（{len(SYM_ELF_NAMES)} 项）')
        if missing:
            print(f'  ⚠ 未解析到（读数会显示"读不到"）：{", ".join(sorted(missing))}')
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
        ('mod_data_tail', base + SYMS['g_ModDataCache'] + 0x4000, 3),  # 模组数据容器尾部（见 SYMS 注释）
        # 模组数据容器的**开头 1 KiB**：记录表（每条 24 字节头 + 值，见
        # `ModPersistence::detail::RecordAt`）。读它就能把探针写进 `Mod:SaveData` 的文本
        # 从内存里取回来 —— **不依赖屏幕、不依赖 Lua 错误槽**（2026-09-18：探索针的屏幕读数
        # 只画了一帧就没了，正是靠这条通道才把结论拿到手）。
        # ⚠️ 窗口必须**盖住整个 payload**，否则记录表会在中间"走不通就停"，
        # 而现象是"某条模组的记录不见了"（2026-09-20 实测：EID 的配置记录比 GoodTrip 的大，
        # 4096 字节的窗口正好把它切掉 ⇒ 读数里只有别的模组）。
        # 容器容量是 0x4000（16 KiB）、当前用量在 `mod_data_tail` 里报；这里给 8192 字节。
        ('mod_data_head', base + SYMS['g_ModDataCache'], 1024),
        # API 调用序列（`ApiSequenceState` 的声明顺序：u64 mainMask、u64 secondaryMask、
        # u32 drawCalls、u32 drawBytes、u32 itemConfigFound、u32 itemConfigMissing、
        # u64 filterMask、u32 lastPrimary、u32 lastPrimaryCalls）—— 读前 5 个字（40 字节）够用。
        ('api_sequence', base + SYMS['g_ApiSequence'], 5),
        ('manifest_head', base + SYMS['g_DefaultManifest'], 24),   # 清单原文前 192 字节
        ('entry_head', base + SYMS['g_DefaultEntry'], 8),          # 入口脚本前 64 字节
        # 回调登记表：**按字节**解（每项 20 字节，见 `decode_callback_entries`）。
        # 请求 90 个 8 字节字 = 720 字节 ⇒ 够看满 36 条登记（容量 256 条，EID 一家约 34 条）。
        ('callback_registry', base + SYMS['g_CallbackRegistry'], 90),
        ('callback_count', base + SYMS['g_CallbackRegistry'] + CALLBACK_REGISTRY_COUNT_OFFSET, 1),
        # 批次 109：`Input.IsActionTriggered` **每个动作报过几次**（32 个 u32 = 16 个字）。
        # 用途：按**一次**键之后读这里 —— 某个动作 +2 就是"一次按键报了两次边沿"
        # （用户实测的"按一次跳两格"就是这么来的）；+1 才是正常。
        ('input_edge_counts', base + SYMS['g_InputEdgeCounts'], 16),
        # 批次 110：最长"闪断"帧数（32 个 u32 = 16 个字）。去抖窗口够不够看它。
        ('input_release_peak', base + SYMS['g_InputReleaseRunPeak'], 16),
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
        ('perf_alloc_calls', base + SYMS['g_RuntimePerfAllocCalls'], 1),
        ('perf_tick_cost', base + SYMS['g_RuntimePerfTickCostTicks'], 1),
        ('perf_empty_call_ticks', base + SYMS['g_RuntimePerfEmptyCallTicks'], 1),
        ('perf_empty_call_count', base + SYMS['g_RuntimePerfEmptyCallCount'], 1),
        ('perf_alloc_bytes', base + SYMS['g_RuntimePerfAllocBytes'], 1),
        ('perf_alloc_new_calls', base + SYMS['g_RuntimePerfAllocNewCalls'], 1),
        ('perf_free_calls', base + SYMS['g_RuntimePerfFreeCalls'], 1),
        # 回调派发计数（2026-09-18）：74 个 u32 是**一个数组**（连续），所以一次读完；
        # 旁边那两个标量是**独立全局**（链接器可能重排）⇒ 各读各的，绝不连读。
        ('callback_dispatch_counts',
         base + SYMS['g_CallbackDispatchCounts'],
         (CALLBACK_DISPATCH_COUNTER_COUNT * 4 + 7) // 8),
        ('callback_dispatch_last', base + SYMS['g_LastDispatchedCallbackId'], 1),
        ('callback_dispatch_generation', base + SYMS['g_CallbackDispatchGeneration'], 1),
        ('filetable', base + SYMS['g_diagnosticFileApi'], 4),
        ('hook_callbacks', base + SYMS['g_hookCallbacks'], len(HOOK_NAMES)),
        ('update_entry', game_base + SYMS['manager_update_entry'], 2),
        # 贴图桥 v2/v3 的挂点入口（0x4d1fe4，相对**游戏模块**）：期望是我们写进去的
        # 入口补丁（`ldr x16,#8; br x16; .quad 槽` ⇒ 首四字 `5000005800021fd6`）。
        ('imagemanager_entry', game_base + 0x4D1FE4, 2),
        # v4 新挂点的入口（相对游戏模块）：期望也是入口补丁。
        ('getmounted_entry', game_base + 0x4C2340, 2),
        # 贴图桥用到的 8 个引擎绑定指针（全 0 = 守卫没过、整套绑定没发布）。
        ('image_pcx_bindings', base + SYMS['image_pcx_bindings'], 8),
        # 贴图桥诊断结构体（ImagePcxDiagnostics）：一次性读全。
        ('image_pcx_diag', base + SYMS['image_pcx_diag'], 40),
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
        ('mod_menu_state', base + SYMS['mod_menu_state'], 29),
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
    if plugin_base:
        req.append(('helper', plugin_base + PLUGIN_HELPER, 14))
    # 上面每条都用 `SYMS[...]` 直接取；这里做一遍守卫，缺的进 `skipped` 而不是让整个函数崩掉。
    skipped.extend(SYMS.missing)
    del SYMS.missing[:]
    # 缺偏移的量地址会退化成 `base + 0`（模块基址），必须剔掉 —— 否则会拿一段无关内存当读数。
    present = [(key, address, count) for key, address, count in req
               if not (key in skipped and address == base)]
    return present, skipped


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
CALLBACK_REGISTRY_COUNT_OFFSET = 0x2000
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
}

#: 我们**故意还没接线**、但读数里要标出名字的 id（标名字是为了"这个数字是哪一种"一眼可读）。
#: 与 `CALLBACK_NAMES` 分开是有意的，门禁（`test_callback_dispatch_counters.py` 的
#: `test_reader_callback_names_have_a_matching_constant`）要求这里每一个 id **不许**出现在
#: `HasDispatchSite` 名单里。两种形态都合法：**有常量但没派发点**（`MC_INPUT_ACTION` 13）
#: 或**连常量都还没有**；一旦它的常量进了 `HasDispatchSite`，就该挪到上面那张表去。
#: （2026-09-20 修正注释：原文说"门禁要求这里没有对应常量"，而门禁实际只判"不在派发点名单里"。）
CALLBACK_NOT_WIRED = {
    13: 'MC_INPUT_ACTION  ← 已登记但无派发点（见 `HasDispatchSite` 的注释）',
    # 17 `MC_PRE_GAME_EXIT`（批次 102）、38 `MC_PRE_PICKUP_COLLISION`（批次 103）、
    # 71 `MC_PRE_ROOM_ENTITY_SPAWN`（批次 104）都已接线 ⇒ 都挪到上面的 `CALLBACK_NAMES`。
    # 也就是说：EID 在意的 9 种里，现在只剩 `MC_INPUT_ACTION`(13) 故意不接（它要钩热函数）。
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
    for offset in range(0, min(len(raw), PROFILE_BUCKET_COUNT * PROFILE_BUCKET_BYTES),
                        PROFILE_BUCKET_BYTES):
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


def callback_name(identifier: int) -> str:
    return CALLBACK_NAMES.get(identifier, '其它种类')


#: `ApiDomain` 的取值（`runtime/src/interfaces/lua/api_descriptor.hpp` 的枚举顺序就是编码）。
#: 与那张表**必须**逐项一致：id 是 `(域 << 24) | (ownerGroup << 16) | 序号`。
CATALOG_DOMAINS = {
    'Global': 0, 'Mod': 1, 'Game': 2, 'Level': 3, 'Room': 4, 'ItemPool': 5, 'Music': 6,
    'Rng': 7, 'Persistence': 8, 'Input': 9, 'Diagnostic': 10, 'Font': 11, 'Vector': 12,
    'Sprite': 13, 'Isaac': 14, 'Seed': 15, 'ModMenu': 16,
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
        out = session.command('\n'.join(lines))
        session.command('detach')
    finally:
        session.close()

    save_raw(out, base, game_base, plugin_base)
    values = parse_words(out)

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
            if self_addr and base and 0 < self_addr - base < 0x200000:
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
                and (self_addr == 0 or (base and 0 < self_addr - base < 0x200000)))
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
    16: 'ACTION_RESTART', 17: 'ACTION_FULLSCREEN', 18: 'ACTION_MUTE', 19: 'ACTION_JOINMULTIPLAYER',
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
    # 更老的读数文件里只有 56 / 54 / 51 / 45 / 41 / 40 个 ⇒ 逐级回退，下面凡是用到新格的地方
    # 都由 `len(f) >= N` 守住（离线重放老文件不会炸）。
    f = (_struct.unpack_from('<58I', raw, 0) if len(raw) >= 58 * 4
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
    print(f'  条目 {f[13]} 条｜选中第 {f[14]} 条'
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


def report(values: dict[str, list[int]], base: int, game_base: int, plugin_base: int) -> None:
    print()
    print('=== 启动状态机（TestRunObserver：游戏主循环那条线程每次启动只走一遍）===')
    seq = first(values, 'g_sequence')
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
    if 'mod_data_tail' in values:
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
        print('    ⇒ 第一次开机后应当"存档里有 + generation>=1"；'
              '重启后再读一次 generation 应当继续增大（说明真的落盘了）')
    # ⚠️ `payload_sources` 原来只在"读到了 API 序列那一段"时才被赋值，而**一次读数里只要有一个
    # 地址读不到（例如 `--read` 指到未映射区），gdb 那批输出就会缺后面几段** ⇒ 后面用到它时
    # `UnboundLocalError`，**整份报告崩掉**（2026-09-20 实测）。所以在这里先置空表：
    # "读不到"应当表现为"少一段"，不是"整份报告看不到"。
    payload_sources: list[str] = []
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
    if 'g_IsaacApiRowCalls' in values:
        row_calls = first(values, 'g_IsaacApiRowCalls') & 0xFFFFFFFF
        engine_calls = first(values, 'g_IsaacEngineRowCalls') & 0xFFFFFFFF
        last_id = first(values, 'g_IsaacApiRowLastCallId') & 0xFFFFFFFF
        last_kind = first(values, 'g_IsaacApiRowLastCallKind') & 0xFFFFFFFF
        rej_receiver = first(values, 'g_IsaacEngineRowRejectReceiver') & 0xFFFFFFFF
        rej_offset = first(values, 'g_IsaacEngineRowRejectOffset') & 0xFFFFFFFF
        rej_entry = first(values, 'g_IsaacEngineRowRejectEntry') & 0xFFFFFFFF
        rej_id = first(values, 'g_IsaacEngineRowLastRejectId') & 0xFFFFFFFF
        rej_reason = first(values, 'g_IsaacEngineRowLastRejectReason') & 0xFFFFFFFF
        kind_name = {1: '字段行', 2: '引擎方法行'}.get(last_kind, '（还没调用过）')
        reason_name = {0: '（没发生过）', 1: '接收者解析失败', 2: '偏移拿不到',
                       3: '入口 4 字节指纹不匹配'}.get(rej_reason, f'未知({rej_reason})')
        print('  === 数据行 API 的调用 / 静默降级（批次 069：不用探针也能回答"调到了没"）===')
        print(f'    数据行被调用 = {row_calls} 次（其中引擎方法行 {engine_calls} 次）')
        print(f'    最后一次调用 = {api_name(last_id)}（{kind_name}）')
        print(f'    引擎方法行被降级 = {rej_receiver + rej_offset + rej_entry} 次'
              f'（接收者 {rej_receiver} / 偏移 {rej_offset} / 入口指纹 {rej_entry}）')
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
        def u64(key: str) -> int:
            # ★ 2026-09-21：这里**必须容忍缺键**。同一段报告也要能读"不是生产包"的那份 ELF
            # （例如探针构建），而 `--gc-sections` 会把"本构建里没人读"的计数器整个丢掉
            # （实测：探针包里没有 `g_RuntimePerfSyscalls`，生产包里有）。
            # 缺键就报 0 并打印"读不到"，**不许抛 KeyError** —— 那会让整次 attach 白烧，
            # 而这台机器一个启动周期只允许几次 attach（`build_requests` 的 docstring 同一条纪律）。
            words = values.get(key)
            if not words:
                print(f'  （{key} 读不到：本构建里没有这个符号）')
                return 0
            return int.from_bytes(words_to_bytes(words), 'little')
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
        if cb_calls:
            print(f'    托管回调 {cb_calls} 次：合计 {to_us(cb_ticks) / 1000.0:.1f} ms、'
                  f'平均 {to_us(cb_ticks) / cb_calls:.1f} µs、最慢一次 {to_us(cb_max):.0f} µs')
        print(f'    引擎内存查询（svcQueryMemory）{syscalls} 次：合计 {to_us(syscall_ticks) / 1000.0:.1f} ms'
              + (f'、平均 {to_us(syscall_ticks) / syscalls:.1f} µs' if syscalls else ''))
        if cb_calls and cb_ticks:
            share = 100.0 * syscall_ticks / cb_ticks
            print(f'    其中"读引擎内存"占回调总耗时的 {share:.1f}%'
                  + ('  ⇒ ★ 大头在我们自己的内存查询上' if share > 40 else ''))
        # 批次 086：按 (事件 id, 属主模组) 分开，回答"贵的是哪一个回调"。
        buckets = perf_bucket_records(values)
        if buckets:
            buckets.sort(key=lambda record: record[2], reverse=True)
            print('    最贵的回调（按 (事件 id, 属主模组) 分开；批次 086）——')
            for rank, (key, count, ticks, max_ticks, bins) in enumerate(buckets[:10], start=1):
                print(f'      {rank:>2}. {callback_name(key & 0xFFFFFFFF)} [{perf_bucket_owner(key)}]'
                      f'  {count} 次 / 合计 {to_us(ticks) / 1000.0:.1f} ms'
                      f' / 平均 {to_us(ticks) / count:.1f} µs / 最慢 {to_us(max_ticks):.0f} µs')
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
            total_calls = first(values, 'g_RuntimePerfApiTotalCalls')
            total_ticks = first(values, 'g_RuntimePerfApiTotalTicks')
            if total_calls:
                print(f'    ★ 全部接口合计（含没进表的）：{total_calls} 次 / '
                      f'{to_us(total_ticks) / 1000.0:.1f} ms / 平均 {to_us(total_ticks) / total_calls:.2f} µs'
                      f' —— 读两次做差即得"每帧多少次、每帧多少 µs"，与回调耗时直接对账')
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
    count = first(values, 'callback_count')
    if count > CALLBACK_REGISTRY_CAPACITY:
        # 响亮地报"这个数不可信"，而不是把它当真的念出来 —— 布局一变这里就会漂
        # （2026-09-20 就是这么读到 `kNoCallbackFilter` 的哨兵值的）。
        print(f'  回调登记数 = {count} ⚠ **不合理**（容量只有 {CALLBACK_REGISTRY_CAPACITY}）'
              f' ⇒ `CallbackRegistry` 的布局可能变过了：'
              f'去核对 `callback_registry.hpp` 的平行数组与 `CALLBACK_REGISTRY_COUNT_OFFSET`'
              f'（= 0x{CALLBACK_REGISTRY_COUNT_OFFSET:X}）')
    else:
        print(f'  回调登记数 = {count}')
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
        if ptr is None:
            print(f'  [{i}] {name:20} 读不到')
        elif relay_key and ptr == base + SYMS[relay_key]:
            print(f'  [{i}] {name:20} 0x{ptr:012x} ← 零占洞入口中继（模块+0x{SYMS[relay_key]:x}）★')
        elif ptr == 0:
            note = '（该路走 GOT 槽，判据见下）' if name == 'ManagerPresent' else '（该路未走入口中继）'
            print(f'  [{i}] {name:20} 0x{ptr:012x} ← {note}')
        else:
            print(f'  [{i}] {name:20} 0x{ptr:012x}')

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
    print_probe_native_mods_menu(values)
    print()
    print_mod_menu_native(values)

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
            if fired_peaks:
                print('    ⇒ 闪断帧数若 ≥ 松手去抖窗口（6 帧）就还会"长按不停翻页"'
                      '（那时要把窗口调大）。')
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
                    help='额外读任意地址：ADDR:SIZE[,ADDR:SIZE...]（十六进制/十进制都行）。'
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
        report(values, base, game_base, plugin_base)
        return 0

    if args.two_phase:
        return run_two_phase(args.ip, elf, args.pid, args.base, args.game_base, args.plugin_base)
    return run_one_shot(args.ip, elf, args.pid, args.base, args.game_base, args.plugin_base,
                        parse_extra_reads(args.read))


if __name__ == '__main__':
    sys.exit(main())
