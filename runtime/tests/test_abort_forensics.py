"""批次 099（2026-09-24）：「死前留证」兜底的门禁。

## 这条门禁在防什么

`docs/问题记录-画面卡死-20260924.md` 的现场是：游戏**画面卡死、音乐还在、没有崩溃报告**。
离线分析（该文档 §10）把 `runtime.elf` 里所有能到 `abort` 的路列出来，结论是三类嫌疑
分不开 —— 因为**它们一个都不留痕迹**（`abort → newlib _exit` 原地自旋）。

所以这一批只做一件事：在那两条路真的死掉之前先 `svcBreak`，把寄存器交给崩溃报告。
本条门禁钉住**五件事**，缺一条这个能力就是假的：

1. `fatal_forensics.hpp` 里的 `Break` 必须用**真机验证过的那种写法**：
   `x0 = 2`（`BreakReason_User`）+ `svc 0x26` + `__builtin_unreachable()`；
   ★ 2026-09-26（批次 135）改过一次：原来是 `svc 0x7f`，真机报告
   `01790359235_010021c000b6a000.log` 给出的类型是 `Undefined System Call`（`Svc Id: 0x7f`）——
   因为 `0x7f` 在本仓库 svc 表里是 `svcCallSecureMonitor`、userland 下不合法；
   `svcBreak` 的真号是 **`0x26`**（`runtime/config.json`）。**别改回 0x7f**。
2. 魔数必须是 `0x3142414341415349`（ASCII `ISAACAB1`）—— 报告里认它才知道是我装的兜底；
3. **两个注册点都必须在**：`exl_main` 里装 `std::set_terminate`、
   `luaL_newstate` 之后装 `lua_atpanic`（后者正是"Lua 无保护抛错"那条路的唯一兜底）；
4. ★★ **`svc` 必须有 `__aarch64__` 守卫** —— 宿主机（x86_64）门禁夹具会编译这一份，
   没有守卫就会"不是合法指令"编译失败（2026-09-24 实测踩过）；而 `svc` 那条路是**不返回**的，
   所以整个设施必须是**头文件里的 inline**（做成独立 `.cpp` 会让编译 `lua_runtime.cpp` 的夹具
   在链接期报未定义符号 —— 同一天踩到的第二个坑）；
5. **不许顺手改游戏逻辑**：这个设施里不许出现"调引擎 / 包 Lua 调用 / 写引擎内存"的东西 ——
   它只能留证，不能改行为（改行为属于"按报告定位根因"那一步，另开批次）。
6. ★ 2026-09-29（批次 197）新增：**全仓不许再出现 `svc 0x7f`**。批次 135 只改了
   `fatal_forensics.hpp` 一处，其余探针点（`runtime/source/probe/*`、
   `saltynx_runtime_bridge.cpp`、`saltynx_probe_break.hpp`）当时**留作欠账**；本批已全部
   统一成 `0x26`（9 处），并由本条门禁钉住 —— 否则"改了一处就以为全仓一致"会再次发生。

★ 这一条门禁**不检查真机时刻**（那要靠崩溃报告），只钉"能力装上了没有、有没有夹带私货"。
"""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HPP = ROOT / "runtime" / "source" / "fatal_forensics.hpp"
CPP = ROOT / "runtime" / "source" / "fatal_forensics.cpp"
ENTRY = ROOT / "runtime" / "source" / "runtime_entry.cpp"
LUA = ROOT / "runtime" / "source" / "lua_runtime.cpp"
SOURCE = ROOT / "runtime" / "source"


def code_only(text: str) -> str:
    """去掉行注释 —— 判据只看代码，注释里必须能写出这些名字来解释原因。"""
    return re.sub(r"//[^\n]*", "", text)


class AbortForensicsTests(unittest.TestCase):
    def setUp(self):
        for path in (HPP, ENTRY, LUA):
            self.assertTrue(path.is_file(), f"缺文件：{path}")

    def test_break_uses_the_hardware_proven_shape(self):
        """`Break` 必须是真机验证过的形状：`x0=2` + `svc 0x26` + `__builtin_unreachable()`。

        为什么是 `0x26`：那是本仓库 svc 表里的 `svcBreak`（`runtime/config.json`）。
        2026-09-26 之前的 `0x7f` 是 `svcCallSecureMonitor`，userland 下被判"未定义系统调用"，
        报告类型会显示成 `Undefined System Call`（真机报告 `01790359235_...log` 为证）。
        """
        text = HPP.read_text(encoding="utf-8")
        self.assertIn('register std::uint64_t x0 __asm__("x0") = 2;', text,
                      "x0 必须是 2 = `BreakReason_User`")
        self.assertIn('__asm__ volatile("svc 0x26"', text,
                      "必须是 `svc 0x26`（= `svcBreak`；`0x7f` 是 `svcCallSecureMonitor`，"
                      "userland 下报告会变成 `Undefined System Call`）")
        self.assertIn("__builtin_unreachable();", text,
                      "`svcBreak` 之后不返回，要显式告诉编译器")
        self.assertIn("[[noreturn]] inline void Break", text,
                      "`Break` 必须是 inline（见文件头：宿主夹具各自编译一部分运行时）且标 `[[noreturn]]`")

    def test_svc_is_guarded_for_the_host_build(self):
        """★★ `svc` 必须只在 AArch64 上编译，宿主退化成 `std::abort()`。

        理由（2026-09-24 实测）：宿主门禁夹具在 x86_64 上编译运行时的一部分，
        `svc` 在那里**不是合法指令** ⇒ 没有守卫就编不过。
        另一条同源的教训：这个设施**不能做成独立 `.cpp`** —— 编译 `lua_runtime.cpp` 的夹具
        源清单里没有它，会在链接期报 `InstallLuaPanicHandler` 未定义。
        """
        text = HPP.read_text(encoding="utf-8")
        self.assertIn("#if defined(__aarch64__)", text,
                      "`svc` 必须有 AArch64 守卫（否则宿主夹具编译失败）")
        self.assertIn("std::abort();", text,
                      "宿主分支要退化成 `std::abort()`（夹具不会触发，只保证编得过）")
        # 那个独立 .cpp 必须已经删掉（它的存在正是"链接期未定义符号"的成因）。
        self.assertFalse(CPP.is_file(),
                         "这个设施必须是头文件里的 inline；不要再拆出 `.cpp`"
                         "（宿主夹具不会编译它 ⇒ 链接期未定义符号）")

    def test_magic_is_the_documented_one(self):
        """魔数是报告里的识别码：`0x3142414341415349` = ASCII `ISAACAB1`。"""
        text = HPP.read_text(encoding="utf-8")
        self.assertIn("0x3142414341415349ULL", text,
                      "魔数变了 ⇒ 读崩溃报告的人按老值找不到它")
        self.assertRegex(text, r"kKindCxxTerminate\s*=\s*1;")
        self.assertRegex(text, r"kKindLuaPanic\s*=\s*2;")

    def test_both_handlers_are_actually_installed(self):
        """两个注册点缺一不可 —— 缺了就等于"这个兜底只装了一半"。"""
        # ① 模块入口：未捕获 C++ 异常那条路
        entry = ENTRY.read_text(encoding="utf-8")
        self.assertIn("forensics::InstallAbortForensics();", entry,
                      "`exl_main` 里必须调 `InstallAbortForensics()`")
        self.assertIn("std::set_terminate(&detail::TerminateForensics);",
                      HPP.read_text(encoding="utf-8"),
                      "`InstallAbortForensics` 必须真装 terminate 处理器")
        # ② Lua 状态创建之后：无保护抛错那条路（**唯一**的兜底时机）
        lua = LUA.read_text(encoding="utf-8")
        self.assertIn("lua_atpanic(state, &LuaPanicForensics);", lua,
                      "`luaL_newstate()` 之后必须注册 panic 处理器")
        self.assertLess(lua.index("luaL_newstate()"),
                        lua.index("lua_atpanic(state, &LuaPanicForensics);"),
                        "注册必须在**建好状态之后**（在那之前没有 `lua_State` 可注册）")
        # panic 处理器必须走我们的 `Break`（分类码 = Lua 那条路），而不是自己 abort。
        panic_body = lua[lua.index("int LuaPanicForensics(lua_State* state)") :]
        panic_body = panic_body[: panic_body.index("\n}")]
        self.assertIn("forensics::Break", panic_body,
                      "panic 处理器必须调 `forensics::Break`（否则留不下证据）")
        self.assertIn("kKindLuaPanic", panic_body,
                      "分类码必须是 `kKindLuaPanic`（报告里靠 x2 区分是哪条路）")

    def test_it_does_not_smuggle_game_logic_changes(self):
        """★ 这一批只许"留证"，不许夹带任何行为改动。

        判据：这个设施的实现里不许出现「包 Lua 调用 / 调引擎 / 写引擎内存」三类东西。
        要做行为改动（例如给读不到就报错的 API 换保守返回值）属于"按报告定位根因"那一步，
        **另开批次**，不许混在这一批里 —— 混进来之后，"卡死变没变"就归因不清了。
        """
        hpp_code = code_only(HPP.read_text(encoding="utf-8"))
        for forbidden, why in (
            ("lua_pcall", "不许在这里包 Lua 调用（那会改语义）"),
            ("lua_call", "不许在这里直接调 Lua"),
            ("Original<", "不许在这里调引擎原函数"),
            ("memcpy", "留证设施不该做数据搬运"),
            ("new ", "不许在这里分配堆内存（可能就在死之前，分配会再炸一次）"),
        ):
            self.assertNotIn(forbidden, hpp_code, why)

    def test_no_probe_uses_svc_0x7f_anywhere(self):
        """★ 全仓禁止 `svc 0x7f`（2026-09-29 批次 197）。

        为什么：`0x7f` 在本仓库 svc 表里是 `svcCallSecureMonitor`，userland 下被判
        "未定义系统调用" ⇒ 报告类型不是 `User Break`、寄存器语义也不对（批次 135 真机报告
        `01790359235_010021c000b6a000.log` 实测）。批次 135 只改了 `fatal_forensics.hpp`，
        其余 9 处**留作欠账**，于是"改了一处就以为全仓一致"。本批统一后加这条门禁。
        判据只看**代码**（注释里会引 `0x7f` 来解释原因，不该被误伤）。
        """
        offenders = []
        for path in sorted(SOURCE.rglob("*")):
            if path.suffix not in (".cpp", ".hpp", ".c", ".h", ".s"):
                continue
            if "third_party" in path.parts:
                continue
            code = code_only(path.read_text(encoding="utf-8", errors="ignore"))
            if "svc 0x7f" in code:
                offenders.append(str(path.relative_to(ROOT)))
        self.assertEqual(offenders, [],
                         f"这些文件里还有 `svc 0x7f`（应为 `svc 0x26`）：{offenders}")


if __name__ == "__main__":
    unittest.main()