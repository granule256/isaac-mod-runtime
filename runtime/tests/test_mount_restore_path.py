"""门禁：**"重建挂载点表之后把 Mod 的挂载点挂回去"这条路必须真的是通的**。

## 为什么有这条（2026-09-23 真机定位到的 bug）

用户报："换过语言之后，EID 的信息显示坏掉 —— 大部分信息都没有，只剩一个很浅的图标在闪。
重启游戏就正常，再换语言又坏。"

根因链（每一步都有证据）：

1. 换语言 → 引擎的 `PerformLanguageSwitch` → **`Manager::SetLanguage` 的最后一条指令是
   `b RebuildContentMountPoints`（尾调用）**（反汇编 `0x3F5BA8`，实证）⇒ **换一次语言就重建一次
   内容挂载点表，Mod 的挂载点全被丢掉**。
2. 我们的入口中继（`HookId::RebuildMountPoints`）本来就是干"重建之后重新挂回去"的，
   它通过 `SessionContentMountService()` 拿实例、调 `RemountAll()`。
3. **但 `SetSessionContentMountService(...)` 在整个代码库里从来没有被调用过** ⇒ 那个指针恒为空
   ⇒ 中继每次都在 `service == nullptr` 上直接返回、**一个挂载点都不恢复**。
   （注释里写着"重建中继通过 `SessionContentMountService()` 拿到同一个实例"—— 意图在，发布调用没写。）
4. 后果：换语言后 Mod 的文件不可达。EID 每次开局（`MC_POST_GAME_STARTED`）都会重新
   `Font:Load` 它自己的 `.fnt`；**`Font::Load` 开头先 `Unload()`** ⇒ 文件打不开时
   字体**永久停在"未加载"** ⇒ 之后每次画字都被运行时拒绝（Lua 错误历史里就是
   `Font:DrawStringScaledUTF8 requires a loaded Font`）⇒ 信息全不显示。
   开机时已经载进内存的图标还在，所以看起来是"只剩一个很浅的图标在闪"。
5. **重启就好** —— 开机走的是 `RegisterMod` 那条路（它直接 `MountLeaves`），不经过中继。

## 判据（这一条钉住"路是通的"，不是钉住某一行代码）

1. **发布点必须存在**：`hook_manager.cpp` 里必须调用 `SetSessionContentMountService(&g_ContentMountService)`
   —— 只定义访问器、不发布，就是这次这个 bug 的形态（访问器看起来"有"，实际永远是空）；
2. **发布必须在挂点装好之前**：那一句要出现在 `TryInstallDefaultManifestMod` 的函数体里
   （中继只可能在挂点装好之后被调到 ⇒ 此处发布一定够早）；
3. **注册路径必须还在**：`RegisterMod` 必须被调用（开机时挂载点就是这么来的），
   且 `RemountAll()` 必须遍历已注册的 Mod（`count_`）—— 两条一起才构成"重建后能恢复"；
4. **观测面必须还在**：状态面的 [22]/[23]/[24] 三格（中继跑过几次 / 失败几次 / 服务发布了没）
   必须在 `.hpp`、`.cpp`、读数工具三处一致 —— 下次再出这类问题，读数里一眼能看出来。

## ★★★ 批次 378（2026-10-05）：这条路**整体作废**，判据翻面 —— 记录如下

* **改了机制**：模组资源**不再靠引擎的内容挂载点**。PC 的做法是"每次读资源前按清单顺序问一遍
  哪个模组有这个文件"（`ModManager::GetModResourcePath @0x870460`），我们照它实现成
  `IContentManager::GetMountedFilePath` 那一个缝上的重定向（`mod_resource_redirect.*`）。
  取证与逐条偏移：`docs/分析-模组挂载机制与371没音乐定案-20261005.md`。
* **因此第 1/2/3 条判据翻面**：`SetSessionContentMountService(...)` 与 `RegisterMod(...)`
  **都不许再出现** —— 它们代表的正是被撤除的机制。而上面那个 2026-09-23 的 bug
  （换语言 ⇒ 重建挂载点表 ⇒ 模组文件不可达 ⇒ EID 字体永久坏掉）在**新机制下不可能发生**：
  **没有模组挂载点可以丢**（不是"修好了"，是"那条依赖不存在了"）。
* **★ 但必须重新真机复验**：2026-09-23 那条结论（"换语言后 EID 字体坏"）是在旧机制下判的；
  换机制之后要重新走一遍"换语言 → 开局 → EID 是否还显示"（本批的验收项之一）。
* **中继那段代码保留但结构性空转**：`RebuildContentMountPoints` 中继照旧拿
  `SessionContentMountService()`（恒为空 ⇒ 直接返回）；留着是为了不动历史现场、也便于对照。
* **第 4 条（三格观测面）保留**，但 `[24]`（服务发布了没）**从此恒为 0** ——
  读数里**不许**把它读成"量过了、没问题"；新机制的证据面是 `g_ModResourceRedirectState`
  （读数工具新增那一段）。
"""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HOOK_MANAGER = ROOT / "runtime" / "source" / "hook_manager.cpp"
SERVICE_CPP = ROOT / "runtime" / "src" / "application" / "mod" / "content_mount_service.cpp"
SERVICE_HPP = ROOT / "runtime" / "src" / "application" / "mod" / "content_mount_service.hpp"
RELAY = ROOT / "runtime" / "source" / "content" / "rebuild_content_mount_points_relay.cpp"
STATE_HPP = ROOT / "runtime" / "source" / "mod_menu_native.hpp"
STATE_CPP = ROOT / "runtime" / "source" / "mod_menu_native.cpp"
READER = ROOT / "tools" / "read_device_state_via_gdb.py"


class MountRestorePathTests(unittest.TestCase):
    def test_the_session_mount_service_is_actually_published(self):
        """★★★ 批次 378 翻面：这个"发布点必须有"的判据，现在变成"**不许有**"。

        原来它钉的是"访问器有、发布点没有 ⇒ 中继永远空转"那个 bug。机制换成 PC 的资源层
        重定向之后，**发布点有才是错的**（那意味着旧机制又回来了）。
        """
        text = HOOK_MANAGER.read_text(encoding="utf-8")
        # ★ 判据只看**代码**：撤除说明（以及 2026-09-23 那段历史注释）里逐字写着这个名字，
        #   不剥注释会先命中注释。
        code = re.sub(r"//[^\n]*", "", text)
        self.assertNotIn(
            "SetSessionContentMountService(",
            code,
            "模组挂载机制已撤除（376）：不许再发布会话内容挂载服务 —— "
            "新机制是 `mod_resource_redirect.*`（PC 的规则：按清单顺序问哪个模组有这个文件）")

    def test_the_resource_redirect_list_is_published_before_the_scripts_run(self):
        """★ 376 的正向判据：替代上面那条 —— 模组清单必须在**跑模组脚本之前**发布出去。"""
        text = HOOK_MANAGER.read_text(encoding="utf-8")
        publish = text.index("PublishModResourceRedirectList(")
        script_step = text.index("ManifestLoadStep::Scripts")
        self.assertLess(publish, script_step,
                        "重定向清单必须在 `ManifestLoadStep::Scripts` 之前发布 —— "
                        "模组脚本在文件作用域就查死服装编号、回调里现查音乐编号，晚一步就补不回来")
        # 重建挂载点表那条中继**不许**碰它：新机制下重建与模组资源无关（这正是"不可能再丢"的理由）。
        relay = RELAY.read_text(encoding="utf-8")
        self.assertNotIn("PublishModResourceRedirectList", relay,
                         "重建挂载点表的中继不许重新发布重定向清单 —— "
                         "清了重建也不影响（清单不依赖引擎的挂载点表）")

    def test_registration_still_mounts_and_remount_walks_the_registered_mods(self):
        """★ 376 翻面：`RegisterMod`（开机那条路）**不许再有**；`RemountAll` 的遍历逻辑保留。"""
        hooks = HOOK_MANAGER.read_text(encoding="utf-8")
        self.assertNotIn("g_ContentMountService.RegisterMod(", hooks,
                         "模组挂载机制已撤除（376）：不许再登记模组内容挂载点")
        service = SERVICE_CPP.read_text(encoding="utf-8")
        remount = service[service.index("Status ContentMountService::RemountAll()"):
                          service.index("void ContentMountService::Clear()")]
        self.assertIn("count_", remount,
                      "`RemountAll()` 必须遍历**已注册**的 Mod —— 注册表空着它就只能空转")

    def test_the_relay_reports_through_the_session_service(self):
        """中继必须真的去拿那个实例（而不是绕开它）。"""
        relay = RELAY.read_text(encoding="utf-8")
        self.assertIn("SessionContentMountService()", relay)
        self.assertIn("RemountAll()", relay)

    def test_the_three_observability_cells_exist_in_all_three_places(self):
        """[22]/[23]/[24] 三格必须在 .hpp / .cpp / 读数工具三处一致（口径不许漂）。"""
        hpp = STATE_HPP.read_text(encoding="utf-8")
        cpp = STATE_CPP.read_text(encoding="utf-8")
        reader = READER.read_text(encoding="utf-8")
        for field in ("mountRelayFired", "mountRelayFailures", "mountServicePublished"):
            self.assertIn(field, hpp, f"状态面 .hpp 缺字段 {field}")
            self.assertIn(field, cpp, f"状态面 .cpp 没有填 {field}")
        self.assertIn("f[22]", reader, "读数工具没有打印 [22]（中继跑过几次）")
        self.assertIn("f[23]", reader, "读数工具没有打印 [23]（失败几次）")
        self.assertIn("f[24]", reader, "读数工具没有打印 [24]（服务发布了没）")
        # 读数请求的宽度要跟上字段数 —— ★ 从 `.hpp` 的字段个数**算出来**，不写死
        #   （写死的话每加一格都要改这里，而漏改的表现是「读数少读一段」，很隐蔽）。
        #   1 个字 = 8 字节；每个字段 4 字节。
        fields = len(re.findall(r"std::uint32_t\s+\w+;", hpp))
        words = (fields * 4 + 7) // 8
        self.assertIn(f"('mod_menu_state', base + SYMS['mod_menu_state'], {words})", reader,
                      f"状态面读数的宽度必须跟着字段数走（{fields} 个 u32 = {words} 个字）")


if __name__ == "__main__":
    unittest.main()
