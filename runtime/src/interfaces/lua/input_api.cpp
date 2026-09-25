#include "interfaces/lua/input_api.hpp"

// 批次 107：`IsActionTriggered` 的上升沿判定（纯逻辑，见该头文件顶部的证据与差别说明）。
#include "input_edge.hpp"

#include <atomic>

#include "interfaces/lua/api_sequence_probe.hpp"
// 批次 110：`Input.IsActionPressed`/`GetActionValue` 的 thunk 在这里变成可调用签名
// （**前提**：thunk 非 0 已在上游判过 —— 那两条 API 各自有一道非零检查）。
#include "infrastructure/call/engine_call_access.hpp"
// 批次 109：`Input.IsActionTriggered` 的"按帧判边沿"要用引擎自己的帧计数
// （`EngineFrameCountNow`）与毫秒时钟（`EngineMillisecondsNow`）。
#include "infrastructure/memory/engine_memory_guard.hpp"
#include "interfaces/lua/isaac_api.hpp"
#include "interfaces/lua/lua_integer_argument.hpp"
#include "interfaces/lua/owner_binding.hpp"
#include "interfaces/lua/vector_api.hpp"

#include "lua_runtime_state.hpp"

extern "C" {
#include <lauxlib.h>
}

//: 引擎调用层的短别名（批次 110）：本文件里"把已核对过的 thunk 变成可调用签名"只走它。
namespace engine_call = isaac::runtime::engine_call;

namespace isaac::runtime {

// 输入探针（2026-09-16，模组菜单那一轮）：菜单"按了没反应"时必须能分辨三种原因 ——
// 绑定根本没装上、动作号和手柄按键对不上、或者回调根本没跑。这三个量回答前两种：
//   * `g_InputActionTriggeredMask`：`IsActionTriggered` 回答过 `true` 的动作号（按位）；
//   * `g_InputActionQueriedMask`：被问过的动作号（按位）—— 用来确认"菜单确实在问"；
//   * `g_InputLastActionCode` / `g_InputLastActionResult`：最后一次问的号与结果。
// 它们是**我们自己的入口**的计数，与 `g_FontLoadCalls` 同一性质（真机可读、无副作用）。
std::atomic<std::uint32_t> g_InputActionTriggeredMask{0};
//: 非 0 号 controller（手柄）上"回答过是"的动作号。真机上"键位对不上"最常见的原因就是
//: controller 序号：PC 的 `Input.IsActionTriggered(动作, 0)` 里 0 通常指键盘，手柄是 1~4。
std::atomic<std::uint32_t> g_InputActionTriggeredMaskOther{0};
//: `IsActionPressed` 的同一张位图（按住而不是"刚按下"）——两条查询互为对照。
std::atomic<std::uint32_t> g_InputActionPressedMask{0};
//: 非 0 号 controller 上"按住"的动作号（与上面同一张位图的补充，用来确定手柄序号）。
std::atomic<std::uint32_t> g_InputActionPressedMaskOther{0};
std::atomic<std::uint32_t> g_InputActionQueriedMask{0};
std::atomic<std::uint32_t> g_InputLastActionCode{0xFFFFFFFFu};
std::atomic<std::uint32_t> g_InputLastActionResult{0};
std::atomic<std::uint32_t> g_InputLastController{0xFFFFFFFFu};
//: 让"按住/刚按下"返回 true 的那些 **controller 值**（按 `controller & 31` 记位）。
//: 真机结论（2026-09-16）：玩家自己的 `EntityPlayer.ControllerIndex`（那次是 33）才是引擎认的值，
//: 猜 0/1 永远拿不到"按下"。这两张掩码就是用来一次读数钉死"到底该传什么"。
std::atomic<std::uint32_t> g_InputTriggeredControllerMask{0};
std::atomic<std::uint32_t> g_InputPressedControllerMask{0};

//: 批次 107：`IsActionTriggered` 的上升沿表（只有游戏线程的派发路径读写它 ⇒ 普通对象、不是原子）。
LuaRuntime::ActionEdgeTracker g_ActionEdge{};

//: 批次 109：**每个动作报过几次"刚按下"**（下标 = `动作 & 31`）。
//: 为什么要有它：用户实测"有时候按一次跳两个物品" —— 有了这个计数，按**一次**键之后读一次数
//: 就能直接判定"是我们报了两次边沿"还是"别的地方翻了两格"（`g_InputActionTriggeredMaskOther`
//: 只知道"报过"，不知道"报了几次"）。读数工具会把非零项打出来。
std::atomic<std::uint32_t> g_InputEdgeCounts[32];

//: 批次 110：每个动作观察到的**最长"闪断"帧数**（按住期间连续多少帧读到"没按住"）。
//: 用途：`ActionEdgeTracker::kReleaseFrames`（松手去抖窗口）够不够，就看这一行 ——
//: 真机上引擎的"按住"查询会闪断（109 的读数：动作 7 在按住期间被报了 **170** 次边沿）。
//: 若某个动作的闪断帧数 ≥ 去抖窗口，那"长按不停翻页"就还会犯，需要把窗口调大。
std::atomic<std::uint32_t> g_InputReleaseRunPeak[32];

namespace {

int InputIsButtonTriggered(lua_State* state);
int InputIsButtonPressed(lua_State* state);
int InputGetButtonValue(lua_State* state);
int InputIsActionTriggered(lua_State* state);
int InputIsActionPressed(lua_State* state);
int InputGetActionValue(lua_State* state);
// 鼠标两条（批次 041，为 GoodTrip 补）：Switch 上**明确降级**，见实现处注释。
int InputGetMousePosition(lua_State* state);
int InputIsMouseBtnPressed(lua_State* state);

constexpr LuaHandlerBinding kInputHandlers[] = {
    {0x09010001, &InputIsButtonTriggered},
    {0x09010002, &InputIsButtonPressed},
    {0x09010003, &InputGetButtonValue},
    {0x09010004, &InputIsActionTriggered},
    {0x09010005, &InputIsActionPressed},
    {0x09010006, &InputGetActionValue},
    // 批次 041（GoodTrip）：鼠标两条。PC 的签名里**只有鼠标按钮号**，没有 controller 参数。
    {0x09010007, &InputGetMousePosition},
    {0x09010008, &InputIsMouseBtnPressed},
};

constexpr char kInputOwner[] = "Input";

// ★ 调用约定（2026-09-16 修正，这是"按键查询永远答没按下"的真因）：
//
// 绑定的那三个地址**不是**函数本体，而是游戏自己的**入口跳板**，逐字节读出来是：
//
//     adrp x0, <g_Manager> ; ldr x0, [x0, #0x768]   → x0 = Manager 单例
//     mov  x3, xzr                                  → x3 = 0（尾随的实体参数清零）
//     b    <真函数>                                 → 尾调用真函数
//
// 所以真函数的签名是 `(Manager*, u32 action, u32 controller, void* entity)`，
// 跳板只负责补 x0 与 x3，**动作号在 x1、手柄序号在 x2**。
//
// 照 PC 的形态直接 `query(action, controller)` 会把动作号塞进 x0（被跳板覆盖）、手柄序号塞进 x1
// （被当成动作号）、x2 留成垃圾 ⇒ 引擎每次都答"没按下"。
// 真机实测（`docs/问题与解决日志.md` 续三十六）：0~27 号动作 × controller 0/1 全问一遍、
// 玩家按遍所有键，回答"是"的一个都没有 —— 就是这条错的调用约定。
//
// 因此调用时必须给一个**占位的第一个参数**（跳板会覆盖它），把动作号与手柄序号放进 x1/x2。
// ★ 2026-09-19 修正（ABI 体检的"少给参数"判据修正后当场查出来）：
// 引擎签名是 `Manager::IsActionPressed(unsigned int, unsigned int, Entity*)`（`tools/engine_symbol_signatures.json`），
// 我们原先只声明了 3 个形参（被跳板覆盖的 Manager* + 动作号 + controller）⇒ **第 4 个寄存器是调用方的残留值**。
// 第 3 个引擎参数是 PC `Input.IsActionPressed(action, controller, entity)` 的那个可选 `entity`
// （PC 的 Lua 侧允许省略 ⇒ 传空指针），所以这里按 `nullptr` 显式给出去，不留残留值。
using ActionQueryFn = bool (*)(void* /* 被跳板覆盖的 Manager* */, std::uint32_t, std::uint32_t,
                               void* /* Entity*：PC 的可选第三参，我们一律给空指针 */);
using ActionValueFn = float (*)(void*, std::uint32_t, std::uint32_t, void*);

// Every Input method takes `(input code, controllerId)`.
void CheckInputQueryArguments(lua_State* state, const char* apiName) {
    if (lua_gettop(state) != 2 || !isaac::runtime::IsIntegerArgument(state, 1) || !isaac::runtime::IsIntegerArgument(state, 2)) {
        luaL_error(state, "%s accepts input code and controllerId integers", apiName);
    }
}

// The button query functions have no entry point the Runtime can call yet: the game has no
// `Manager::IsButton*` trampoline, and the `KAGE::Input::ManagerBase::IsButton*` variants need
// the KAGE input manager instance, which the Runtime has not located. Those handlers keep
// validating their arguments and answer "not pressed" so a Mod using them runs instead of
// erroring. The three action queries below are bound to the game's own `Manager::` trampolines,
// which load the Manager singleton themselves and zero the trailing `Entity*` argument, so
// they take exactly the two arguments the PC API takes.

int InputIsButtonTriggered(lua_State* state) {
    CheckInputQueryArguments(state, "Input.IsButtonTriggered");
    lua_pushboolean(state, 0);
    return 1;
}

int InputIsButtonPressed(lua_State* state) {
    CheckInputQueryArguments(state, "Input.IsButtonPressed");
    lua_pushboolean(state, 0);
    return 1;
}

int InputGetButtonValue(lua_State* state) {
    CheckInputQueryArguments(state, "Input.GetButtonValue");
    lua_pushnumber(state, 0.0);
    return 1;
}

// ★ 2026-09-20（批次 107）：**不再用引擎那条"刚按下"查询**，改用我们自己算的上升沿。
//
// 证据（真机读数 + 反汇编）：`KAGE::Input::ManagerBase::IsActionPressed @ 0x4F9920` 与
// `IsActionTriggered @ 0x4F9A64` 结构完全相同（找控制器条目 → 调它的虚函数 → 取返回值），
// 只有虚函数槽不同（`vtable+0x48` vs `+0x50`）。而真机上："按住"位图对
// 动作 4/5/6/7/13、controller = 33（玩家自己的 `EntityPlayer.ControllerIndex`，09-16 已钉）**为真**，
// "刚按下"位图**一次都没为真** ⇒ **同一条控制器、同一个动作，Pressed 通、Triggered 永远假**
// —— 引擎那份上升沿状态在我们跑到它的时候（`MC_POST_UPDATE`/`MC_POST_RENDER` 里）是空的。
//
// 于是：拿**已验证可用**的 `IsActionPressed` 当唯一原语，自己记上一次的状态算上升沿
// （`LuaRuntime::ActionEdgeTracker`）。与 PC 的差别（一次边沿只答一次 true）写在 `api_deviation.cpp`。
int InputIsActionTriggered(lua_State* state) {
    CheckInputQueryArguments(state, "Input.IsActionTriggered");
    const std::uintptr_t thunk = LuaRuntime::InputIsActionPressedThunk();
    if (thunk == 0) {
        return luaL_error(state, "Input.IsActionTriggered native binding is unavailable");
    }
    const auto query = engine_call::AsFunction<ActionQueryFn>(thunk);
    const auto code = static_cast<std::uint32_t>(lua_tointeger(state, 1));
    const auto controller = static_cast<std::uint32_t>(lua_tointeger(state, 2));
    const bool pressed = query(nullptr, code, controller, nullptr);
    // 帧号：优先用**引擎自己的帧计数**（`Game::Update` 每帧 +1）；读不到就退化成用毫秒时钟
    // 当序号（粒度比一帧细，同一帧内基本不会变）—— 关键是**读失败不能让边沿永远不刷新**。
    std::uint32_t frame = isaac::runtime::EngineFrameCountNow();
    if (frame == 0) {
        frame = static_cast<std::uint32_t>(isaac::runtime::EngineMillisecondsNow() / 4);
    }
    const bool triggered = g_ActionEdge.Observe(code, controller, pressed, frame);
    g_InputReleaseRunPeak[code & 31u].store(g_ActionEdge.PeakReleaseRun(code, controller),
                                            std::memory_order_relaxed);
    // 探针：位图按 32 位取模（`ButtonAction` 的号都小于 32），越界不影响判定。
    const std::uint32_t bit = 1u << (code & 31u);
    g_InputActionQueriedMask.fetch_or(bit, std::memory_order_relaxed);
    if (triggered) {
        g_InputEdgeCounts[code & 31u].fetch_add(1, std::memory_order_relaxed);
        if (controller == 0) {
            g_InputActionTriggeredMask.fetch_or(bit, std::memory_order_relaxed);
        } else {
            g_InputActionTriggeredMaskOther.fetch_or(bit, std::memory_order_relaxed);
        }
        g_InputTriggeredControllerMask.fetch_or(1u << (controller & 31u),
                                                std::memory_order_relaxed);
    }
    g_InputLastActionCode.store(code, std::memory_order_relaxed);
    // 记的是**这一问的回答**（是不是刚按下）；"按住"那一路有自己的位图（下面那条查询）。
    g_InputLastActionResult.store(triggered ? 1u : 0u, std::memory_order_relaxed);
    g_InputLastController.store(controller, std::memory_order_relaxed);
    lua_pushboolean(state, triggered ? 1 : 0);
    return 1;
}

int InputIsActionPressed(lua_State* state) {
    RecordApiSequenceSecondary(32U);
    CheckInputQueryArguments(state, "Input.IsActionPressed");
    const std::uintptr_t thunk = LuaRuntime::InputIsActionPressedThunk();
    if (thunk == 0) {
        return luaL_error(state, "Input.IsActionPressed native binding is unavailable");
    }
    const auto query = engine_call::AsFunction<ActionQueryFn>(thunk);
    const auto code = static_cast<std::uint32_t>(lua_tointeger(state, 1));
    const bool held = query(nullptr, code,
                            static_cast<std::uint32_t>(lua_tointeger(state, 2)), nullptr);
    if (held) {
        const auto controller = static_cast<std::uint32_t>(lua_tointeger(state, 2));
        if (controller == 0) {
            g_InputActionPressedMask.fetch_or(1u << (code & 31u), std::memory_order_relaxed);
        } else {
            g_InputActionPressedMaskOther.fetch_or(1u << (code & 31u),
                                                   std::memory_order_relaxed);
        }
        g_InputPressedControllerMask.fetch_or(1u << (controller & 31u),
                                              std::memory_order_relaxed);
        g_InputLastController.store(controller, std::memory_order_relaxed);
    }
    lua_pushboolean(state, held ? 1 : 0);
    return 1;
}

// 鼠标查询的参数校验：PC 的签名是 `Input.IsMouseBtnPressed(Mouse button)`（`Input.md:121`）
// 与 `Input.GetMousePosition(boolean gameCoords)`（`Input.md:40`）—— **都没有 controller 参数**。
// 只钉"必须是一个整数"（`Mouse` 枚举），取值范围不钉：越界在 PC 上只是"没按下"，
// 而不是错误（"比 PC 严"害过我们好几次，2026-09-18 的两条缺陷就是这一类）。
void CheckMouseButtonArguments(lua_State* state, const char* apiName) {
    if (lua_gettop(state) != 1 || !isaac::runtime::IsIntegerArgument(state, 1)) {
        luaL_error(state, "%s accepts one mouse button index", apiName);
    }
}

// ★ 平台限制（2026-09-19 批次 041，为 GoodTrip 补）：**Switch 没有鼠标指针**。
//
// 判据与后果（写清楚，免得下一个人当成"功能没做"）：
//   * GoodTrip 的 `scripts/control.lua:190` **每帧**调 `Input.GetMousePosition(true)`，
//     只用它的结果算"鼠标这一帧动了没有"（与上一帧的距离平方 > 4）⇒ 返回**固定 (0,0)**
//     就是"鼠标永远没动过"，拖拽/图钉那些鼠标交互不会触发 —— 这与"只做手柄路径"的
//     既定决定一致（辅助小地图用 `MapButton + 方向键` 操作，那条路不需要鼠标）；
//   * **绝不能抛错**：每帧调用点一旦报错，整条回调会被派发器静默摘掉。
//
// 为什么不做成"真实现"：本机没有鼠标输入源，要等价替代得先做**触摸屏**或**摇杆光标**的
// 输入层取证（那是新任务）。届时把这里换成真值即可，接口形状不用变。
int InputGetMousePosition(lua_State* state) {
    if (lua_gettop(state) != 0 && lua_gettop(state) != 1) {
        return luaL_error(state, "Input.GetMousePosition takes an optional boolean");
    }
    PushLuaVector(state, 0.0F, 0.0F);
    return 1;
}

// ★ 平台限制（同上一条：Switch 没有鼠标）：`Input.IsMouseBtnPressed(Mouse button)` 恒返回
// **false** —— 对 GoodTrip 就是"鼠标没点"，于是它那套鼠标拖拽 / 点地图传送的分支都不会触发
//（与"只做手柄路径"的既定决定一致）。同样**不抛错**：它被每帧的鼠标状态跟踪调用。
int InputIsMouseBtnPressed(lua_State* state) {
    CheckMouseButtonArguments(state, "Input.IsMouseBtnPressed");
    lua_pushboolean(state, 0);
    return 1;
}

int InputGetActionValue(lua_State* state) {
    CheckInputQueryArguments(state, "Input.GetActionValue");
    const std::uintptr_t thunk = LuaRuntime::InputGetActionValueThunk();
    if (thunk == 0) {
        return luaL_error(state, "Input.GetActionValue native binding is unavailable");
    }
    // The PC API returns a float; the game's own function is the authority on the scale.
    const auto query = engine_call::AsFunction<ActionValueFn>(thunk);
    lua_pushnumber(state, static_cast<lua_Number>(
                              query(nullptr, static_cast<std::uint32_t>(lua_tointeger(state, 1)),
                                    static_cast<std::uint32_t>(lua_tointeger(state, 2)), nullptr)));
    return 1;
}

} // namespace

// 批次 107：会话级重置（`ResetSessionState()` 调用）。
//
// ⚠️ 必须定义在**匿名命名空间之外**：它要给 `isaac_api.cpp`（另一个 TU）链接。
// 本批第一版把它放进了匿名命名空间（内部链接）⇒ 只编译 API 层子集的宿主 harness 集体链接失败，
// 而只编译 `input_api.cpp` 的那些 harness 报 `-Werror=unused-function`（那正是"内部链接、没人用"
// 的信号）。**106 批也踩过同一个坑**（见 `lua_runtime.cpp` 里那段注释）。
void ResetInputEdgeState() noexcept {
    g_ActionEdge.Reset();
}

std::size_t AttachInputMethods(lua_State* state) noexcept {
    return AttachOwnerMethods(state, kInputOwner, kInputHandlers,
                              sizeof(kInputHandlers) / sizeof(kInputHandlers[0]));
}

} // namespace isaac::runtime
