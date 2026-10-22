"""批次 371：「让模组那一层早于引擎第一次读共享路径」的形状契约。

## 这一批要成立的四件事

1. **时机**：早期那一段（`RunEarlyModMountPrelude`）仍出现在 `ModuleWorker` 里
   `svcSleepThread(kWorkerStartupDelayNanoseconds)` 的**之前**，而入口 `exl_main` 里
   **不许有任何等待**（入口被游戏同步等待 ⇒ 在入口等 = 直接给开机加秒数，记录续十六 §二）。
2. **早期那一段只做纯内存的事**：核 `Game::Init` 入口守卫 + `IsMappedRxModuleCodeWindow` +
   `TryInstallEntryRelay`；**不读文件、不调任何引擎函数、不挂挂载点**。这条是批次 370 用真机
   三次启动三次崩溃换来的（崩因：在模块重定位窗口里调引擎文件 API，`dist/crash-20261005-1355/`）。
3. **回调里才挂**（游戏线程、`Game::Init` 原函数之前）：复用批次 370 写好的
   `MountModsBeforeHeavyWork` 实体，跑完原函数要靠回退入口。回调里**不许装钩子**。
4. **5 秒延迟的语义一个字节都没改**：开关名 `WORKER_STARTUP_DELAY_SECONDS`、默认值 `0`、
   `svcSleepThread(kWorkerStartupDelayNanoseconds)` 那一段、以及"等待在 `ModuleWorker` 开头"
   这条形状都还在。

另外钉住仪器化：状态面 `g_EarlyMountState` 的字段名/顺序/类型、它的**外部链接**
（定义必须在匿名命名空间之外 —— 否则读数工具按符号名取不到），以及读数工具的读长与解码口径。

## 这个门禁**不**判什么（诚实说明）

它**测不了**真机行为（中继装没装上、回调有没有被引擎调到、挂载点有没有比引擎第一次读更早）
—— 那是上卡 + 读数的事（判据见 `runtime/source/early_mod_mount_state.hpp` 与存档 README）。
它挡的是"看起来接上了、其实位置/形状/口径不对"的那类错。
"""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "runtime" / "source"
ENTRY = SOURCE / "runtime_entry.cpp"
HOOKS = SOURCE / "hook_manager.cpp"
HOOK_HEADER = SOURCE / "hook_manager.hpp"
STATE_HEADER = SOURCE / "early_mod_mount_state.hpp"
CONSTANTS = SOURCE / "runtime_constants.hpp"
ANM2_IMPL = SOURCE / "anm2_load_override_hook.cpp"
MAKEFILE = ROOT / "runtime" / "Makefile"
READER = ROOT / "tools" / "read_device_state_via_gdb.py"


def strip_line_comments(text: str) -> str:
    """去掉 `//` 行注释（本仓纪律：判据只看**代码**；注释里逐字写着这些名字的例子太多）。"""
    return re.sub(r"//[^\n]*", "", text)


def worker_body(entry: str) -> str:
    """`ModuleWorker` 的**函数体**（按花括号配对取，从真正的定义那一行起算）。

    为什么不用 `index("void ModuleWorker") : index('extern "C" void exl_main')` 那种松切法：
    那会把函数**之后**的东西（本批新增的前置函数定义、状态面定义）也算进来 ——
    于是"提前装中继在 sleep 之前"这条判据会被**函数之外**的同名文本满足，门禁看起来在查、
    其实什么都没查（2026-10-05 做红检时当场抓到的）。
    """
    return function_body(entry, "#if !defined(EXL_STARTUP_PROBE_STAGE) || EXL_STARTUP_PROBE_STAGE != 6\n"
                                "void ModuleWorker(void*) {")


def exl_main_body(entry: str) -> str:
    start = entry.index('extern "C" void exl_main')
    return entry[start:entry.index('extern "C" NORETURN', start)]


def function_body(text: str, signature: str) -> str:
    """按花括号配对取一个函数的**定义体**（从签名到配对的 `}`）。

    为什么不用 `index(签名) : index("下一个函数")` 那种切法：本批的
    `RunEarlyModMountPrelude` 定义排在 `ModuleWorker` **之后**（那样才能让
    `#if ... != 6` 与 `void ModuleWorker(void*)` 保持相邻，见 `runtime_entry.cpp` 里的说明），
    用"下一个函数"切会切出空串 ⇒ 门禁看起来在查、其实什么都没查。
    """
    start = text.index(signature)
    opening = text.index("{", start)
    depth = 0
    for index in range(opening, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                return text[start:index + 1]
    raise AssertionError(f"unterminated function: {signature}")


class EarlyModMountTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.entry = ENTRY.read_text(encoding="utf-8")
        cls.hooks = HOOKS.read_text(encoding="utf-8")
        cls.hook_header = HOOK_HEADER.read_text(encoding="utf-8")
        cls.state_header = STATE_HEADER.read_text(encoding="utf-8")
        cls.constants = CONSTANTS.read_text(encoding="utf-8")
        cls.anm2_impl = ANM2_IMPL.read_text(encoding="utf-8")
        cls.makefile = MAKEFILE.read_text(encoding="utf-8")
        cls.reader = READER.read_text(encoding="utf-8")

    # ---- ① 时间形状：前置段在 5 秒等待之前；入口里没有等待 ---------------------
    def test_early_mount_is_not_a_worker_timeout_race(self):
        worker = worker_body(self.entry)
        self.assertNotIn("RunEarlyModMountPrelude();", worker)
        self.assertIn("MainModuleLoadPreparationReady()", worker)
        entry = exl_main_body(self.entry)
        self.assertLess(entry.index("InstallMainModuleLoadObserver"), entry.index("svcCreateThread"))
        self.assertIn("g_EarlyMountState.delayStartTicks =", worker)

    def test_the_entry_point_never_waits(self):
        entry = strip_line_comments(exl_main_body(self.entry))
        self.assertNotIn("svcSleepThread", entry,
                         "★ 入口里不许等待 —— 入口被游戏同步等待，在入口等 = 给开机加秒数")
        self.assertNotIn("RunEarlyModMountPrelude", entry,
                         "★ 前置步骤只能挂在 worker 线程上（`ModuleWorker`），不许搬进入口")

    def test_the_worker_delay_switch_is_unchanged(self):
        worker = worker_body(self.entry)
        # 默认值仍是 0（生产形状：worker 建好就开始干活）。
        self.assertIn("#if !defined(EXL_WORKER_STARTUP_DELAY_SECONDS)\n"
                      "#define EXL_WORKER_STARTUP_DELAY_SECONDS 0\n"
                      "#endif", self.constants,
                      "`WORKER_STARTUP_DELAY_SECONDS` 的默认值被改了（生产形状必须仍是 0）")
        self.assertIn("inline constexpr std::int64_t kWorkerStartupDelayNanoseconds =\n"
                      "    static_cast<std::int64_t>(EXL_WORKER_STARTUP_DELAY_SECONDS) * "
                      "1'000'000'000LL;", self.constants)
        # 等待本身仍在（放在 worker 开头、在重活之前，且在"标题检查"之前）。
        self.assertIn("if (kWorkerStartupDelayNanoseconds > 0) {", worker)
        self.assertIn("svcSleepThread(kWorkerStartupDelayNanoseconds);", worker)
        self.assertLess(worker.index("svcSleepThread(kWorkerStartupDelayNanoseconds)"),
                        worker.index("TestRunObserver::Mark(TestRunObserver::State::ModuleWorkerEntered)"),
                        "等待必须仍在重活之前（它在 worker 的最前面）")
        # 开关名不许改名：Makefile 是它唯一的来源，构建命令里写的就是这个名字。
        self.assertIn("WORKER_STARTUP_DELAY_SECONDS ?= 0", self.makefile)
        self.assertIn("-DEXL_WORKER_STARTUP_DELAY_SECONDS=$(WORKER_STARTUP_DELAY_SECONDS)",
                      self.makefile)
        # 顺手挡住"用新的固定延迟替换掉这个开关"的倒退形状。
        self.assertNotIn("svcSleepThread(5'000'000'000)", worker)

    # ---- ② 早期那一段：只做纯内存的事（核靶点 + 装中继）-----------------------
    def test_the_prelude_only_installs_the_entry_relay(self):
        prelude = function_body(self.entry, "bool PrepareEarlyResourcesAfterLoad() noexcept {")
        # ① 有界等待游戏模块：复用既有的 `ScanTargetModule`（不另写扫描），上限 2 秒。
        self.assertIn("ScanTargetModule()", prelude)
        self.assertNotIn("svcSleepThread", strip_line_comments(prelude))
        self.assertNotIn("kEarlyMountModuleScanAttemptLimit", strip_line_comments(prelude))
        self.assertIn("TargetModuleScanStatus::Found", prelude)
        self.assertIn("return false;", prelude)
        # ② 纯内存核靶点：必须先过"这一页现在可执行"那道门才敢读入口 16 字节。
        self.assertIn("kGameInitEntryFileOffset", prelude)
        self.assertIn("IsMappedRxModuleCodeWindow(", prelude,
                      "读目标入口那 16 字节之前必须先确认它可执行（否则读它本身就是崩溃）")
        # ③ 装入口中继（只改游戏模块 `.text` 的 16 字节）。
        self.assertIn("isaac::runtime::relay::TryInstallEntryRelayWithPublisher(", prelude)
        self.assertIn("kGameInitEntryExpectedBytes", prelude)
        self.assertIn("static_cast<std::atomic<std::uintptr_t>*>(opaque)->store(original,std::memory_order_release)", prelude,
                      "真正的回退原子槽必须由publisher提前写入")
        self.assertIn("}, &g_GameInitFallbackEntry, &fallbackEntry)", prelude,
                      "publisher必须收到回调实际读取的g_GameInitFallbackEntry，不能只公布到局部out")
        # 上限常量本身：2 秒 = 400 × 5 ms（写死在这里，改了必须有人解释）。
        self.assertIn("kEarlyMountModuleScanAttemptLimit = 400;", self.constants)
        self.assertIn("kEarlyMountPollNanoseconds = 5'000'000;", self.constants)

    def test_the_prelude_touches_no_files_and_no_engine(self):
        """★ 批次 370 的真机崩溃就是在这里：早期窗口里**不许**读文件/调引擎/挂挂载点。"""
        code = strip_line_comments(function_body(self.entry, "bool PrepareEarlyResourcesAfterLoad() noexcept {"))
        for forbidden in ("MountModsBeforeHeavyWork", "engine_memory::ReadAt",
                          "EngineMountPointListHasModPrefix", "ResolveAll", "RegisterMod",
                          "svcSleepThread(kEarlyMountContentManagerAttemptLimit)"):
            self.assertNotIn(forbidden, code,
                             f"早期那一段里不许出现 `{forbidden}` —— 它只能做纯内存的事"
                             "（370 就是死在'在那个窗口里调引擎'上）")

    def test_the_target_is_the_game_init_entry(self):
        # 靶点 = `Game::Init` 的入口（0x34DD50），16 字节守卫逐字节钉死。
        self.assertIn("inline constexpr uintptr_t kGameInitEntryFileOffset = 0x34DD50;",
                      self.constants)
        guard = re.search(r"kGameInitEntryExpectedBytes = \{(.*?)\};", self.constants, re.S)
        self.assertIsNotNone(guard, "靶点的 16 字节守卫没有登记")
        bytes_in_order = re.findall(r"0x([0-9A-Fa-f]{2})", guard.group(1))
        self.assertEqual(
            [b.upper() for b in bytes_in_order],
            ["FF", "C3", "01", "D1", "FD", "7B", "03", "A9",
             "FD", "C3", "00", "91", "F8", "5F", "04", "A9"],
            "`Game::Init` 入口的 16 字节守卫被改了（可能是版本换了，或者抄错了）",
        )

    def test_timestamps_use_the_physical_counter(self):
        prelude = function_body(self.entry, "bool PrepareEarlyResourcesAfterLoad() noexcept {")
        self.assertIn("RuntimePerfTick()", prelude,
                      "时间戳必须走 `RuntimePerfTick()`（`cntpct_el0`）")
        # 两个 EL0 读不到的寄存器一个都不许出现在**这一段代码**里（批次 085 的真机崩溃）。
        # 只看代码、不把注释算进来（注释里解释"为什么不用它们"是好事，本仓纪律：判据只看代码）；
        # 全文件的同类判据由既有门禁 `test_no_el0_privileged_register_reads` 按白名单钉住。
        code = strip_line_comments(prelude)
        for forbidden in ("cntvct_el0", "cntfrq_el0"):
            self.assertNotIn(forbidden, code)

    # ---- ③ 回调：**实验 B** —— 只读清单、一个字节都不碰引擎 -------------------
    def test_the_callback_reads_the_manifest_but_never_touches_the_engine(self):
        """★ 实验 B（2026-10-05）：把 371 的差异再拆一半 —— 回调里**只读清单**。

        实验 A（只装中继、回调里什么都不做）真机**干净** ⇒ 元凶在"回调里做的那件事"，
        而那件事分两半：**读文件** 与 **调引擎（`AddMountPoint`）**。本卡只做前半段。
        判据：引擎有没有音乐（= 渲染族闸门开不开 ⇒ 屏幕上的探针文字画不画）。
        """
        callback = function_body(
            self.entry, 'extern "C" void EntryRelayGameInitCallback(void* self) {')
        code = strip_line_comments(callback)
        # 形状 = 目标函数 ABI（`void Game::Init()` ⇒ x0 = this）。
        self.assertIn("++g_EarlyMountState.relayCallbackFired;", code,
                      "回调被调次数没记账 ⇒ '引擎调到了没有'这第一判据就没了")
        # 跑原函数：靠回退入口，用引擎调用层转换签名；没有回退入口就什么都不做。
        self.assertIn("engine_call::AsFunction<void (*)(void*)>(", code)
        self.assertIn("original(self);", code)
        self.assertIn("if (original != nullptr)", code)
        self.assertIn("if (original != nullptr)", code)
        # ★★ **批次 383（2026-10-06）更新这一条**：回调从"只读清单"改成"**读清单 + 发布重定向名单**"。
        #
        # 由来（真机读数定案）：`Game::Init` 里有 8 处资源读取，其中 `Game::Init+0x340` 的
        # `Minimap::Init` 会第一次读 `gfx/ui/minimap1.anm2`；而引擎的动画缓存**按键存条目**
        # ⇒ "谁先读到哪一份，那份就被钉住"。只读清单会让名单**晚于**那次读才发布 ⇒ 缓存里被
        # 本体那份钉死 ⇒ `Sprite:Load` 命中缓存、连路径都不问（`ANM2::Load` 中继 757 次里只有
        # 134 次问到解析器）；而唯一的事后手段（作废缓存条目）在批次 368 崩过、369 起被禁用。
        # 逐条证据：`docs/分析-红字根因-模组覆盖是事后修正而PC是启动期前置-20261006.md`。
        #
        # ⇒ 现在**允许** `MountModsBeforeHeavyWork`（它只读文件 + 写我们自己的内存，
        #   发布那一步是纯内存数组 + 屏障，一个引擎接口都不调）；
        #   **仍然禁止**"调引擎的挂载接口 / 读引擎挂载点表 / 装钩子"这一族（那正是 371 坏掉的那一半）。
        self.assertIn("MountModsBeforeHeavyWork(", code,
                      "回调必须在这一刻把'可重定向的模组根'发布出去 —— 否则引擎先把本体那份缓存住，"
                      "之后就再也改不回来了")
        for forbidden in ("EngineMountPointListHasModPrefix", "RegisterMod", "TryInstall",
                          "SetSessionContentMountService", "AddMountPoint"):
            self.assertNotIn(forbidden, code,
                             f"回调里不许出现 `{forbidden}` —— 这一刀只许**读文件 + 写我们自己的内存**")
        # 前向声明要在（早期那一段要取它的地址）。
        self.assertIn("extern \"C\" void EntryRelayGameInitCallback(void* self);", self.entry)

    def test_the_manifest_read_helper_never_mounts(self):
        """实验 B 用的那个入口必须**一个字节都不碰引擎**（不 `RegisterMod`、不写 session）。"""
        body = function_body(
            self.hooks,
            "bool ReadManifestOnlyForExperimentImpl(const TargetModule& module) noexcept {")
        code = strip_line_comments(body)
        for forbidden in ("RegisterMod", "SetSessionContentMountService", "AddMountPoint",
                          "TryInstall"):
            self.assertNotIn(forbidden, code,
                             f"`ReadManifestOnlyForExperiment` 里不许出现 `{forbidden}`")
        # 但它必须复用与正式路径**同一套**读法（否则测的不是同一件事）。
        self.assertIn("GameFileReader::VerifyBindings(module, &bindings)", code)
        self.assertIn("manifestService.ResolveAll(", code)
        self.assertIn("g_ModDiscoveryService.Discover(&batch)", code)

    def test_callback_is_declared_with_external_linkage(self):
        # `extern "C"` = 外部链接 ⇒ 早期那一段取地址合法，且不会因诊断构建不引用而报 unused。
        self.assertIn('extern "C" void EntryRelayGameInitCallback(void* self) {', self.entry)

    # ---- ④ 挂载实体：只挂挂载点、复用既有服务（370 定的，371 继续用）-----------
    def test_mounts_only_and_reuses_the_existing_services(self):
        # ★ 真正的实现叫 `...Impl`，住在 `hook_manager.cpp` 的**匿名命名空间**里（它要用那几个
        #   文件作用域的服务）；对外只有一层转发壳（有外部链接，`runtime_entry.cpp` 调的是它）。
        impl_signature = "EarlyModMountOutcome MountModsBeforeHeavyWorkImpl(const TargetModule& module) noexcept {"
        body = function_body(self.hooks, impl_signature)
        wrapper = function_body(
            self.hooks,
            "EarlyModMountOutcome MountModsBeforeHeavyWork(const TargetModule& module) noexcept {")
        self.assertIn("return MountModsBeforeHeavyWorkImpl(module);", wrapper,
                      "对外那层壳必须转发到实现（否则回调里调的是一个没定义的符号）")
        code = strip_line_comments(body)
        # 复用既有服务，而不是自己另写一套扫描/引擎调用。
        self.assertIn("manifestService.ResolveAll(", code)
        self.assertIn("g_ModDiscoveryService.Discover(&batch)", code)
        self.assertIn("g_ModDiscoveryService.AppendUnlisted(&batch)", code)
        self.assertIn("GameFileReader::VerifyBindings(module, &bindings)", code)
        # ★★★ 批次 378（2026-10-05）：这一步从"早挂六个内容叶子"改成"早发布**重定向清单**"
        #   （PC 的机制：`ModManager::GetModResourcePath @0x870460` 按清单顺序问"哪个模组有
        #   这个文件"）。判定意图不变 —— 提前那一段仍然**只**做"让模组资源能被引擎看见"
        #   这一件事，而且现在连一次引擎调用都没有。取证见
        #   `docs/分析-模组挂载机制与371没音乐定案-20261005.md`。
        self.assertIn("isaac::runtime::bridge::PublishModResourceRedirectList(roots, rootCount)",
                      code)
        # 只发布清单：不许装钩子、不许建 Lua 状态、不许跑模组脚本、不许读存档侧开关，
        # 也**不许**再碰引擎的内容挂载点（挂载机制已撤除）。
        for forbidden in ("TryInstall", "HookInstallService", "LuaRuntime::", "service.LoadAll(",
                          "LoadEmbeddedMenuMod(", "CardSwitchOn(",
                          "g_ContentMountService", "SetSessionContentMountService",
                          "AddMountPoint", "MountModDirectory"):
            self.assertNotIn(forbidden, code,
                             f"提前那一段里不许出现 `{forbidden}`（它只能发布重定向清单）")
        # 现有开关读取已在游戏线程授权；发布前必须排除用户禁用的模组。
        self.assertIn("g_SaveFileAdapter.AllowFromGameThread()", code)
        self.assertIn("g_ModToggleService.ApplyToBatch(&batch)", code)
        # 声明也要在头文件的非诊断分支里（诊断构建没有那套服务）。
        self.assertIn("EarlyModMountOutcome MountModsBeforeHeavyWork(const TargetModule& module) "
                      "noexcept;", self.hook_header)

    def test_mount_list_is_read_as_eight_byte_char_pointers(self):
        # 读引擎那张挂载点表：复用 ANM2 那一路定案的读法（8 字节 `const char*`），
        # 不在别处再抄一份（抄错就是 2026-10-05 那次"静默失效"的根因）。
        # ★ 实验 A（批次 372）：回调里**不再读表**（挂载被摘掉了）⇒ 这里只钉住"读法本身在 ANM2
        #   那条链上有一份、且只有一个写法"；等实验 A 的读数说话之后，实验 B / 正式版要用它时
        #   从 `anm2_load_override_hook.hpp` 取（不许在 `runtime_entry.cpp` 另抄一份）。
        self.assertIn("bool EngineMountPointListHasModPrefix(const TargetModule& module) noexcept",
                      self.anm2_impl)
        self.assertIn("item += kMountPointEntrySize", self.anm2_impl)
        self.assertIn("ReadMountPointAt(item", self.anm2_impl)
        self.assertIn("ReadMountPointsAt(vector, &list)", self.anm2_impl)
        self.assertNotIn("kNativeStringSize", self.anm2_impl)
        callback = strip_line_comments(function_body(
            self.entry, 'extern "C" void EntryRelayGameInitCallback(void* self) {'))
        self.assertNotIn("EngineMountPointListHasModPrefix", callback,
                         "实验 A 的回调里不该读挂载点表（挂载那一段已经摘掉）")

    def test_isolated_guard_helper_is_shared_not_copied(self):
        # `IsMappedRxModuleCodeWindow` 只在 `hook_manager.cpp` 定义一次；`runtime_entry.cpp`
        # 用的是头文件里的那一声声明（不许各写一份判定）。
        self.assertIn("bool IsMappedRxModuleCodeWindow(uintptr_t address, size_t length);",
                      self.hook_header)
        self.assertIn("bool IsMappedRxModuleCodeWindow(uintptr_t address, size_t length) {",
                      self.hooks)

    # ---- ⑤ 状态面：字段名/顺序/类型 + 外部链接（定义在匿名命名空间之外）--------
    def test_state_plane_field_order_is_the_memory_order(self):
        fields = re.search(r"struct EarlyModMountState \{(.*?)\n\};", self.state_header, re.S)
        self.assertIsNotNone(fields, "头文件里没有 EarlyModMountState")
        names = re.findall(r"std::uint(?:32|64)_t (\w+);", fields.group(1))
        self.assertEqual(
            names,
            [
                "workerEnteredTicks",
                "delayStartTicks",
                "gameModuleFoundTicks",
                "relayInstalledTicks",
                "callbackFirstFiredTicks",
                "relayInstallAttempted",
                "relayInstallFailure",
                "relayCallbackFired",
                "mountsAttempted",
                "mountsFailed",
                "mountListHadModPrefix",
                # ★ 批次 385（2026-10-06）：前置步骤里"早装资源类中继"的结果（试几条 / 成几条）。
                #   **只许往后加**（字段顺序即内存顺序，读数工具按下标解码）。
                "earlyResourceRelaysAttempted",
                "earlyResourceRelaysInstalled",
            ],
            "状态面字段名/顺序变了 —— 读数工具的判读表必须同步改（字段顺序即内存顺序）",
        )
        # 五个时间戳必须是 u64（读数按 8 字节字取）、**八个**计数是 u32（读数按 u32 下标取）。
        kinds = re.findall(r"std::uint(32|64)_t \w+;", fields.group(1))
        self.assertEqual(kinds, ["64", "64", "64", "64", "64",
                                 "32", "32", "32", "32", "32", "32", "32", "32"],
                         "时间戳必须 u64、计数必须 u32（读数侧按这个划分解码口径）")
        # 契约本身要写明"改动必须同步读数工具"。
        self.assertIn("tools/read_device_state_via_gdb.py", self.state_header,
                      "状态面契约必须写明：改动要同步读数工具")
        self.assertIn("extern EarlyModMountState g_EarlyMountState;", self.state_header,
                      "状态面必须是**外部链接**（读数工具按符号名读）")

    def test_state_plane_is_defined_outside_the_anonymous_namespace(self):
        # ★ 与 `Anm2LoadOverrideState` 同一条纪律：放进匿名命名空间 ⇒ 读数工具读不到，
        #   而且是静默读不到（`SYMS` 里那格恒 0，看起来像"这一步没走到"）。
        self.assertRegex(
            self.entry,
            r"namespace isaac::runtime::earlymount \{\s*\n(?:\s*//[^\n]*\n)*"
            r"EarlyModMountState g_EarlyMountState\{\};",
            "状态面定义必须在匿名命名空间之外（要有外部链接的符号名）",
        )
        # 反过来：定义**不许**出现在任何 `namespace {` 的括号范围里。
        # 判法 = 去掉注释后做一次花括号配对（够用：本文件里没有把 `{`/`}` 放进字符串字面量的地方）。
        bare = re.sub(r"/\*.*?\*/", "", strip_line_comments(self.entry), flags=re.S)
        definition = bare.index("EarlyModMountState g_EarlyMountState{};")
        for match in re.finditer(r"namespace \{", bare):
            depth = 0
            cursor = bare.index("{", match.start())
            while cursor < len(bare):
                if bare[cursor] == "{":
                    depth += 1
                elif bare[cursor] == "}":
                    depth -= 1
                    if depth == 0:
                        break
                cursor += 1
            self.assertFalse(
                match.start() < definition < cursor,
                "状态面定义被塞进了匿名命名空间 ⇒ 没有外部符号，读数工具取不到那个符号",
            )

    # ---- ⑥ 读数面：符号、读长、解码口径 -------------------------------------
    def test_reader_prints_the_new_state_plane(self):
        self.assertIn(
            "'g_EarlyMountState': '_ZN5isaac7runtime10earlymount17g_EarlyMountStateE'",
            self.reader,
            "读数工具必须按 mangled 名登记这个符号（C++ 命名空间里的变量在 ELF 里就是 mangled 名）",
        )
        self.assertIn("('early_mount_state', base + SYMS['g_EarlyMountState'], 9)", self.reader,
                      "读数工具没按 **9** 个 8 字节字读它（5 个 u64 + 8 个 u32 = **72 字节**；"
                      "★ 批次 385 追加了 [11]/[12] 两格，原来 6 个 u32 / 64 字节 / 8 个字）")
        self.assertIn("`Game::Init` 入口中继", self.reader, "读数里没有这一段报告")
        # ★ 八个 u32 计数**必须**按真正的 u32 下标取（`u32_at`）—— 用 `first` 会把隔壁字段算进来。
        for index, name in ((10, "relayInstallAttempted"), (11, "relayInstallFailure"),
                            (12, "relayCallbackFired"), (13, "mountsAttempted"),
                            (14, "mountsFailed"), (15, "mountListHadModPrefix"),
                            # ★ 批次 387（2026-10-07）：u32 下标 **16/17** = `[11]/[12]`
                            #   （前置步骤里"早装资源类中继"的结果 —— 试几条 / 成几条）。
                            #   ★ 第一版写 18/19 是错的：前面 5 个是 **u64**（各占 2 个 u32 位）
                            #     ⇒ 正确换算 = 5×2 + (字段序号-5)。
                            (16, "earlyResourceRelaysAttempted"),
                            (17, "earlyResourceRelaysInstalled")):
            self.assertIn(f"u32_at(values, 'early_mount_state', {index})", self.reader,
                          f"读数工具没有按 u32 下标取第 {index} 格（{name}）")
        self.assertNotIn("first_u32(values, 'early_mount_state'", self.reader,
                         "u32 数组口径不许用 first_u32（批次 232 定案）")


if __name__ == "__main__":
    unittest.main()
