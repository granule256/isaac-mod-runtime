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
    'g_DefaultManifestState': 0x2345a0,          # 0 未武装 1 已武装 2 安装中 3 就绪 4 失败
    'g_HookInstallFailureCode': 0x234614,        # 入口中继后端转发的失败码（0 = 无失败）
    'g_HookInstallFailureSlot': 0x234618,        # 第一个失败挂点 index+1（0 = 没有装失败的）
    'g_HookInstallInstalledCount': 0x23461c,     # 装好的挂点数（函数内静态，见 SYM_ELF_NAMES）
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
    'g_CallbackRegistry': 0xa0578,     # 回调登记表：每项 20 字节，count_ 在 +0x1400
    # ---- 运行时读进来的文件内容（诊断"模组为什么算纯资源型"的关键）----
    'g_DefaultManifest': 0x1b4560,     # 上次读进来的 `manifest.json` 原文（512 KiB 缓冲）
    'g_DefaultEntry': 0xb4560,         # 上次读进来的入口脚本原文（1 MiB 缓冲）
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
              'ManagerPresent', 'RebuildMountPoints', 'GameStart']
# 只用来做比对、本身不是"要读的内存变量"的符号（读数请求要跳过它们）。
SYM_ONLY = ('identity', 'manifest_install',
            'entry_relay_update', 'entry_relay_render',
            'entry_relay_collectible', 'entry_relay_rebuild',
            'present_got_slot', 'present_target', 'present_callsite_offset')
# 已经切到零占洞入口中继的挂点 → 它的回调应当等于"模块基址 + 下面这个符号的偏移"。
RELAY_BY_HOOK = {'ManagerUpdate': 'entry_relay_update',
                 'ManagerRender': 'entry_relay_render',
                 'PreGetCollectible': 'entry_relay_collectible',
                 'RebuildMountPoints': 'entry_relay_rebuild'}
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
    for key, name in SYM_ELF_NAMES.items():
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
        ('mod_data_head', base + SYMS['g_ModDataCache'], 512),
        # API 调用序列（`ApiSequenceState` 的声明顺序：u64 mainMask、u64 secondaryMask、
        # u32 drawCalls、u32 drawBytes、u32 itemConfigFound、u32 itemConfigMissing、
        # u64 filterMask、u32 lastPrimary、u32 lastPrimaryCalls）—— 读前 5 个字（40 字节）够用。
        ('api_sequence', base + SYMS['g_ApiSequence'], 5),
        ('manifest_head', base + SYMS['g_DefaultManifest'], 24),   # 清单原文前 192 字节
        ('entry_head', base + SYMS['g_DefaultEntry'], 8),          # 入口脚本前 64 字节
        # 回调登记表：**按字节**解（每项 20 字节，见 `decode_callback_entries`）。
        # 请求 90 个 8 字节字 = 720 字节 ⇒ 够看满 36 条登记（容量 256 条，EID 一家约 34 条）。
        ('callback_registry', base + SYMS['g_CallbackRegistry'], 90),
        ('callback_count', base + SYMS['g_CallbackRegistry'] + 0x1400, 1),
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
        ('hook_callbacks', base + SYMS['g_hookCallbacks'], 6),
        ('update_entry', game_base + SYMS['manager_update_entry'], 2),
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
}

#: 我们**故意还没接线**、但读数里要标出名字的 id（标名字是为了"这个数字是哪一种"一眼可读）。
#: 与 `CALLBACK_NAMES` 分开是有意的：门禁要求这里每一个 id 在 `callback_descriptor.hpp` 里
#: **没有**对应常量 —— 有常量就说明它已经接线了，该挪到上面那张表去。
CALLBACK_NOT_WIRED = {
    13: 'MC_INPUT_ACTION  ← 已登记但无派发点（见 `HasDispatchSite` 的注释）',
    17: 'MC_PRE_GAME_EXIT  ← 判据未定，2026-09-18 明确不做（见 `callback_surface.json`）',
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
    for offset in range(0, min(len(raw), count * PERF_BUCKET_BYTES), PERF_BUCKET_BYTES):
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
            return int.from_bytes(words_to_bytes(values[key]), 'little')
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
    print(f'  g_PostUpdateCount = {first(values, "g_PostUpdateCount") & 0xFFFFFFFF}')
    count = first(values, 'callback_count')
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
    print('=== 五个挂点：各自的回调指针（g_hookCallbacks）===')
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
