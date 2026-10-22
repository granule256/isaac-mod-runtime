"""我们这侧的 `Input.*` 查询必须**绕开** `MC_INPUT_ACTION` 的覆盖。

## 这条门禁要防的回归（2026-10-07 真机事故）

Lua 的 `Input.IsActionPressed/IsActionTriggered/GetActionValue` 绑的是 `0x3F9B6C/0x3F9B7C/0x3F9B8C`
（符号 = `IsaacRepentance::Manager::IsAction*`），而这三条**尾跳**进
`KAGE::Input::ManagerBase::IsAction*`（`0x4F9920/0x4F9A64/0x4F9BCC`）—— **正是批次 390 给
`MC_INPUT_ACTION` 挂中继的那三条**。同一个符号另有 35/21/20 个调用点，含
`Entity_Player::get_movement_input` / `control_shooting` / 各 `Menu_*::ProcessInput`
⇒ **Lua 的读取与引擎自己的读取是同一次调用，在函数入口上区分不了**（连实参都同形：
`Entity_Player::Update` 读输入时也是 `mov x3, xzr`）。

于是批次 390/391 上卡后出现真机回归：MCM 菜单可见时对一切动作 `return false`（本意是冻住角色），
结果**它自己的光标读输入**也被答成 false ⇒ 「摇杆推不动光标」。而 PC 契约
（`analysis/isaacdocs-snapshot/docs/enums/ModCallbacks.md:355`）明写：
*"This callback will not affect any custom mod code that is reading user input via the `Input` class."*

批次 392 的修法 = 我们这侧读输入时套 `LuaRuntime::RawEngineInputQueryScope`；三条中继见标记就
**跳过派发、直接调原函数**；取值助手返回的是 `lua_runtime.cpp` 里的**直读壳**（转发到引擎胶水），
于是 `InputIsAction*Thunk()` 的**所有**消费者自动全部走直读。

## 判据（纯源码文本，与项目其它源码门禁同形态）

1. 中继宏里在派发**之前**有 `LuaRuntime::IsRawEngineInputQuery()` 的早退分支；
2. `lua_runtime.cpp` 真的定义了那对 RAII（构造 +1、析构 −1，嵌套安全）；
3. 两条有消费者的取值助手返回**壳**，壳转发到**引擎胶水**（不是 `Original<>` —— 那会让
   `SKIP_HOOK_INPUTACTION*` 的档位把所有输入答成 false）；
4. **发布点保持 `LuaRuntime::SetInputBindings(...)` 不变**：ABI 工具
   （`tools/engine_offset_abi_report.py` 的 `single_binding_signature`）靠"发布函数名以 `Set` 开头"
   这条文本判据追踪三条 `kManager*Offset` 的声明；改成别的名字会让它们的判决掉回"没比过"
   （门禁 `test_engine_offset_signatures` 当场红 —— 这条就是那次踩到的坑钉下来的）。
"""

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "runtime" / "source"
HOOK_MANAGER = SOURCE / "hook_manager.cpp"
LUA_RUNTIME = SOURCE / "lua_runtime.cpp"
LUA_RUNTIME_HPP = SOURCE / "lua_runtime.hpp"


class LuaInputRawQueryBypassTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.hook_manager = HOOK_MANAGER.read_text(encoding="utf-8")
        cls.runtime = LUA_RUNTIME.read_text(encoding="utf-8")
        cls.runtime_hpp = LUA_RUNTIME_HPP.read_text(encoding="utf-8") + (SOURCE / "raw_engine_input.hpp").read_text(encoding="utf-8")

    def test_relay_skips_dispatch_while_we_are_reading(self):
        """中继必须先看"正在直读"标记 —— 否则 `Input.*` 又被自己的覆盖答 false。"""
        start = self.hook_manager.index("#define ISAAC_RUNTIME_INPUT_ACTION_RELAY(")
        body = self.hook_manager[
            start : self.hook_manager.index("\nISAAC_RUNTIME_INPUT_ACTION_RELAY(", start)
        ]
        self.assertIn(
            "LuaRuntime::IsRawEngineInputQuery()",
            body,
            "`ISAAC_RUNTIME_INPUT_ACTION_RELAY` 里找不到直读早退 —— "
            "Lua 的 `Input.*` 会重新被 `MC_INPUT_ACTION` 的覆盖命中（MCM 光标回归会复发）。",
        )
        # 早退必须在**派发之前**：放在后面等于"先覆盖了再绕"，白绕。
        self.assertLess(
            body.index("LuaRuntime::IsRawEngineInputQuery()"),
            body.index("LuaRuntime::DispatchInputAction("),
            "直读早退排在了 `DispatchInputAction` 后面 —— 那时覆盖已经产生，绕不过去了。",
        )

    def test_scope_is_defined_and_counts_nesting(self):
        """RAII 必须是计数式：构造 +1、析构 −1（嵌套：模组在自己的处理器里再问输入）。"""
        for required in (
            "bool IsRawEngineInputQuery() noexcept",
            "RawEngineInputQueryScope::RawEngineInputQueryScope() noexcept",
            "RawEngineInputQueryScope::~RawEngineInputQueryScope() noexcept",
        ):
            self.assertIn(required, self.runtime, f"`lua_runtime.cpp` 里缺定义：{required}")
        self.assertIn("fetch_add(1", self.runtime, "置标记没走计数 —— 嵌套会提前清零。")
        self.assertIn("fetch_sub(1", self.runtime, "清标记没走计数 —— 嵌套会提前清零。")

    def test_thunks_hand_out_our_shells(self):
        """两条有消费者的取值助手必须返回壳；`IsActionTriggered` 那条没有消费者，保持原样。"""
        for shell in ("RawInputActionPressedShell", "RawInputGetActionValueShell"):
            self.assertIn(shell, self.runtime, f"`{shell}` 不见了 —— 直读壳被拆掉了。")
        for hand_out in (
            "isaac::runtime::engine_call::AddressOfFunction(&RawInputActionPressedShell)",
            "isaac::runtime::engine_call::AddressOfFunction(&RawInputGetActionValueShell)",
        ):
            self.assertIn(hand_out, self.runtime, f"取值助手没交出壳：{hand_out}")
        # 绑定没发布时仍然给 0（保住"handler 报绑定不可用"的原语义，不编一个 false）。
        # ⚠ 这一条同时钉住**写法**：必须是 `{ return … g_X.load…` 的形状（不能拆成 `if`）——
        #   `tools/engine_offset_abi_report.py` 的 `THUNK_DEF_RE` 按字面认这一跳，
        #   写成 `if` 会让三条 `kManager*Offset` 的声明判决掉回「没比过」（本批踩过一次）。
        self.assertIn(
            "g_InputIsActionPressed.load(std::memory_order_acquire) == 0",
            self.runtime,
            "`InputIsActionPressedThunk` 不再在绑定缺失时给 0 —— "
            "handler 会把「绑定不可用」误判成「没按下」。",
        )
        self.assertRegex(
            self.runtime,
            r"InputIsActionPressedThunk\(\)\s*noexcept\s*\{\s*return\s+[^;]*?g_InputIsActionPressed\.load",
            "`InputIsActionPressedThunk` 的函数体形状变了（`THUNK_DEF_RE` 认的是 `{ return … g_X.load`）—— "
            "ABI 门禁会判「没比过」。",
        )

    def test_shell_forwards_to_the_engine_glue_so_skip_builds_still_answer(self):
        """壳里转发到**引擎胶水**而不是 `Original<>`：诊断档跳掉中继时照样答真值。"""
        for glue in ("g_InputIsActionPressed", "g_InputGetActionValue"):
            self.assertIn(
                f"isaac::runtime::engine_call::AsFunction<QueryFn>({glue}.load(",
                self.runtime,
                f"壳失去了转发目标 `{glue}` —— 它必须在调用时读那个槽（而不是把地址烧死）。",
            )
        self.assertNotIn(
            "Original<QueryFn>(isaac::runtime::HookId::ManagerIsAction",
            self.runtime,
            "壳改用 `Original<>` 了 —— 中继被 `SKIP_HOOK_INPUTACTION*` 跳掉的档位里它会拿到空指针、"
            "把所有输入答成 false（原生模组页的导航会一起死）。",
        )

    def test_publish_points_keep_their_names_for_the_abi_chain(self):
        """发布点必须保持 `LuaRuntime::SetInputBindings(...)`：ABI 工具按函数名前缀追踪声明。"""
        self.assertEqual(
            self.hook_manager.count(
                "LuaRuntime::SetInputBindings(isActionPressed, isActionTriggered, getActionValue);"
            ),
            2,
            "两个档位（诊断 / 生产）的发布点必须**成对**保持 `SetInputBindings`"
            "（本项目旧教训：漏发一处 ⇒ 某个档位少一样东西；改名 ⇒ ABI 追踪链断、判决掉回「没比过」）。",
        )

    def test_header_documents_the_contract_that_forces_the_bypass(self):
        """头文件必须留着"为什么"（PC 契约原文 + 同一个函数这件事），否则下一个人会再拆掉它。"""
        for required in (
            "IsRawEngineInputQuery() noexcept",
            "RawEngineInputQueryScope",
            "This callback will not affect any custom mod code",
        ):
            self.assertIn(required, self.runtime_hpp, f"`lua_runtime.hpp` 里缺：{required}")


if __name__ == "__main__":
    unittest.main()
