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
        """★ 这条就是那个 bug 的判据：访问器有、发布点没有 ⇒ 中继永远空转。"""
        text = HOOK_MANAGER.read_text(encoding="utf-8")
        self.assertIn(
            "SetSessionContentMountService(&g_ContentMountService)",
            text,
            "必须把会话内容挂载服务发布出去（`SetSessionContentMountService`）—— "
            "没有这一句，重建中继拿到的实例恒为空，重建之后一个 Mod 挂载点都不会恢复")

    def test_publication_happens_inside_the_install_path(self):
        """发布必须在安装路径里（挂点装好之前），否则中继可能先被调到。"""
        text = HOOK_MANAGER.read_text(encoding="utf-8")
        start = text.index("DefaultManifestInstallResult TryInstallDefaultManifestMod(")
        body = text[start:start + 8000]
        self.assertIn("SetSessionContentMountService(&g_ContentMountService)", body,
                      "发布要写在 `TryInstallDefaultManifestMod` 里（模块初始化线程、主循环之前）")

    def test_registration_still_mounts_and_remount_walks_the_registered_mods(self):
        """`RegisterMod`（开机那条路）与 `RemountAll`（重建那条路）两条都要在。"""
        hooks = HOOK_MANAGER.read_text(encoding="utf-8")
        self.assertIn("g_ContentMountService.RegisterMod(", hooks,
                      "开机时每个 Mod 的资源目录靠 `RegisterMod` 挂上（删了它 Mod 直接失效）")
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
