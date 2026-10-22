"""`HasDispatchSite` 的名单必须与代码里真实的派发调用逐项一致。

## 为什么要有这条门禁

设备侧那份"常驻状态面"会报两个数：**有派发点的登记数**、**无派发点的登记数**
（`IsaacModRuntime_GetHookDiagnostics` 的输出槽，宿主通道同源）。这两个数是判断
"某个回调为什么没反应"的第一手依据 —— 但它的可信度完全取决于
`HasDispatchSite()` 那张名单是否与代码一致。

2026-09-15 实测发现它**不一致**：名单里写了 `kCallbackInputAction`（13，
`MC_INPUT_ACTION`），而全仓没有任何地方派发它（`CallbackDispatcher` 的三处调用是
PostGameStarted / PostUpdate / PostRender，加上手工那条 PreGetCollectible）。
后果不是崩溃，而是**读数骗人**：操作者会以为"这种回调有派发点"，于是去别处找原因，
而它一次都不会跑。EID 恰好就注册了 `MC_INPUT_ACTION`。

## 这条门禁怎么判

从**源码文本**里两侧各提取一份集合再比相等：

* 名单侧：`HasDispatchSite()` 函数体里的 `id == kCallback<名字>`；
* 真实派发侧：`lua_runtime.cpp` 里
  * `Dispatch(isaac::runtime::kCallback<名字>,` —— 交给派发器的那几条；
  * `g_CallbackRegistry.At(isaac::runtime::kCallback<名字>, 0)` —— 手工取登记那条。

两侧集合相等才通过。这样"名单多写一项"和"代码新增派发却忘了记名单"都会立刻红，
而不是等下一次真机读数把人带到错误方向。

（与项目其它源码门禁同一形态：不做 C++ 解析，只做受控的文本提取。代价是写法被限制
在有限几种，好处是宿主上零依赖、跑得极快，且不义不容辞地维护一个 C++ 前端。）
"""

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "runtime" / "source"
MOD_API = ROOT / "runtime" / "src" / "interfaces" / "lua" / "mod_api.cpp"
LUA_RUNTIME = SOURCE / "lua_runtime.cpp"

#: `kCallback` 后面的标识符（`kCallbackPostUpdate` → `PostUpdate`）。
_CALLBACK_NAME = r"kCallback([A-Za-z0-9_]+)"


def declared_dispatch_sites(text: str) -> set[str]:
    """从 `HasDispatchSite()` 函数体里取出名单。"""
    start = text.index("bool HasDispatchSite(")
    body = text[start:text.index("}", start)]
    return set(re.findall(r"id\s*==\s*" + _CALLBACK_NAME, body))


def actual_dispatch_sites(text: str) -> set[str]:
    """从运行时源码里取出**真的**会被派发的回调种类。

    三种形态都要认：交给 `CallbackDispatcher` 的通知派发、读回返回值的那条、以及手工从注册表
    取登记的那条。只认这几种写法是刻意的 —— 引入第四种派发方式时这条门禁会红，提醒把它补进来
    （宁可红一次，也不让名单悄悄失真）。

    （2026-09-20 批次 101 从两种涨到三种：`DispatchFiltered` 与 `DispatchModifying` 是新增的
    两个入口，前者按过滤器筛、后者读回返回值。它们**不是新形态**，只是同一个派发器的另外两个
    入口 —— 补进来之后这条门禁的覆盖面与从前一致。）
    """
    dispatched = set(re.findall(r"Dispatch\(isaac::runtime::" + _CALLBACK_NAME, text))
    dispatched |= set(re.findall(r"DispatchFiltered\(isaac::runtime::" + _CALLBACK_NAME, text))
    dispatched |= set(re.findall(r"DispatchModifying\(isaac::runtime::" + _CALLBACK_NAME, text))
    dispatched |= set(re.findall(r"g_CallbackRegistry\.At\(isaac::runtime::" + _CALLBACK_NAME, text))
    # 通用碰撞派发函数按调用方传入的id派发；核对其真实入口中继调用点。
    if re.search(r"DispatchModifying\(callbackId,", text):
        relay = (SOURCE / "hook_manager.cpp").read_text(encoding="utf-8")
        dispatched |= set(re.findall(r"DispatchPreEntityCollision\(isaac::runtime::" + _CALLBACK_NAME, relay))
    # 2026-10-13：21/22经PC _RunCallback，73经PC _UnloadMod；核对真实入口调用链。
    for callback,function,caller in (
        ("GetShaderParams","ShaderValuesProtected","FinishShaderFrame"),
        ("ExecuteCmd","ExecuteCommandCallbackProtected","DispatchExecuteCommand"),
    ):
        if function in text and re.search(r"lua_pushinteger\(state,isaac::runtime::kCallback"+callback+r"\)",text):
            if caller=="FinishShaderFrame":
                pipeline=(SOURCE.parent/"src/application/shader/shader_pipeline.cpp").read_text()
                relay=(SOURCE/"hook_manager.cpp").read_text()
                if "g_State.values(p->view,p->vertices,manager)" in pipeline and "FinishShaderFrame(manager)" in relay:
                    dispatched.add(callback)
            elif "LuaRuntime::DispatchExecuteCommand(view)" in (SOURCE/"console_callback_hook.cpp").read_text():
                dispatched.add(callback)
    if "isaac::runtime::UnloadTrackedMods" in text and "PushModUnloader(state)" in (SOURCE.parent/"src/interfaces/lua/mod_lifecycle_api.cpp").read_text():
        unload=(SOURCE.parent/"src/infrastructure/gotslot/mod_unload_pointer_hook.cpp").read_text()
        if "LuaRuntime::UnloadManifestMods()" in unload:dispatched.add("PreModUnload")
    return dispatched


class CallbackDispatchSiteAgreementTests(unittest.TestCase):
    def setUp(self):
        self.mod_api = MOD_API.read_text(encoding="utf-8")
        self.runtime = LUA_RUNTIME.read_text(encoding="utf-8")

    def test_the_ledger_matches_the_real_dispatch_calls(self):
        declared = declared_dispatch_sites(self.mod_api)
        actual = actual_dispatch_sites(self.runtime)
        self.assertTrue(declared, "`HasDispatchSite` 里一个回调种类都没解析到 —— 门禁失去意义")
        self.assertTrue(actual, "运行时源码里一个派发调用都没解析到 —— 门禁失去意义")
        self.assertEqual(
            declared,
            actual,
            "`HasDispatchSite` 的名单与真实派发调用不一致：\n"
            f"  名单多出（报了但不会触发）：{sorted(declared - actual)}\n"
            f"  代码多出（会触发但没报）：{sorted(actual - declared)}",
        )

    def test_the_formerly_never_dispatched_kind_is_now_claimed(self):
        """★ 2026-10-07（批次 390）：`MC_INPUT_ACTION` 从"**永远不派发**"变成**真派发** —— 断言翻向。

        这条原来叫 `test_the_known_never_dispatched_kind_is_not_claimed`，钉的是"它必须留在名单之外"。
        留那条的理由是：当年那次误报是靠**真机读数对不上**才发现的，而上面那条集合相等断言
        在"名单和代码一起写错"时**不会红**。

        现在派发点**真的实现了**（三条 `KAGE::Input::ManagerBase::*` 查询入口中继 +
        `LuaRuntime::DispatchInputAction`，见 `hook_catalog.hpp` 的 `ManagerIsAction*` 段），
        所以把它**翻成正向断言**：
          * 名单里必须能解析到 `InputAction`；
          * 运行时代码里必须真有那处 `DispatchModifying(isaac::runtime::kCallbackInputAction …)`。
        ⇒ "以后有人把派发点删掉、名单忘了删"仍然会红（保住原来那条回归的价值）。
        """
        declared = declared_dispatch_sites(self.mod_api)
        self.assertIn(
            "InputAction",
            declared,
            "`MC_INPUT_ACTION` 的派发点（批次 390）不在名单里 —— 要么回退时漏了，要么有人删了派发调用。",
        )
        self.assertIn(
            "DispatchModifying(isaac::runtime::kCallbackInputAction",
            self.runtime,
            "`MC_INPUT_ACTION` 的派发调用（批次 390）在 `lua_runtime.cpp` 里找不到。",
        )
        # ★★★ 2026-10-07（真机实证后的修复）：这条派发的**过滤器实参必须是 `inputHook`**。
        # 背景：`MC_INPUT_ACTION` 的 Optional Args 就是 `InputHook`（= `AddCallback` 的第 3 个实参 = 过滤器）。
        # 而 `CollectCallOrder` 的判据是"登记声明了过滤器 且 本次传 kNoCallbackFilter ⇒ 跳过"
        # ⇒ 传 `kNoCallbackFilter` 会把**所有声明了过滤器**的登记整类跳过（minimapi 就是这么登记的，
        # 真机表现为它的处理器一次都不跑、小地图永不放大）。
        # 这条断言就是钉"以后别把它改回 kNoCallbackFilter"。
        self.assertIn(
            "static_cast<std::int64_t>(inputHook)",
            self.runtime,
            "`MC_INPUT_ACTION` 的派发又没把 `inputHook` 当过滤器传了（批次 390 的真机 bug 会复发）。",
        )
