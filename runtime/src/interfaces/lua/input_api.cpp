#include "domain/console/console_panel_state.hpp"
#include "interfaces/lua/input_api.hpp"

// `IsActionTriggered` 的上升沿判定（纯逻辑，见该头文件顶部的证据与差别说明）。
#include "input_edge.hpp"

#include <atomic>
#include <cstring>

#include "interfaces/lua/api_sequence_probe.hpp"
// `Input.IsActionPressed`/`GetActionValue` 的 thunk 在这里变成可调用签名
// （**前提**：thunk 非 0 已在上游判过 —— 那两条 API 各自有一道非零检查）。
#include "infrastructure/call/engine_call_access.hpp"
// `Input.*Triggered` 的"按帧判边沿"要用唯一来源的帧号 —— 就是本 Runtime
// 自己的 `ManagedFrameClock`（= `Isaac.GetFrameCount()` 的真源，每派发一次 `MC_POST_UPDATE` 加一）。
// 起取消"引擎帧计数 + 毫秒兜底"那种双来源：两个刻度混用会让帧号往回跳，
// 而无符号减法 `frame - last` 一溢出就变成"早就松手了" ⇒ 误报边沿。
#include "application/callback/callback_dispatcher.hpp"
#include "infrastructure/memory/engine_memory_guard.hpp"
#include "interfaces/lua/isaac_api.hpp"
#include "interfaces/lua/lua_integer_argument.hpp"
#include "interfaces/lua/owner_binding.hpp"
// 鼠标两条 API 的指针源改成触摸屏（`hid` 服务，只读）。头文件里 `inline` 实现，
// 这样宿主门禁夹具（各自单独列源文件、不含本目录新 .cpp）也能链接过。
#include "interfaces/lua/touch_pointer.hpp"
// 按按键号查询的引擎入口来自 `KAGE::Input::ManagerBase`，判据常量与
// 单例槽在 `runtime_constants.hpp`；读取走框架的受保护读原语。
#include "infrastructure/memory/engine_field_access.hpp"
#include "runtime_constants.hpp"
#include "probe_gate.hpp"     // 探针总开关（正式包默认关）
// PC 的 `controllerId` → Switch 设备号 的映射表（纯换算，口径见那个头文件）。
#include "pc_ns_input_device_map.hpp"
// 模组（PC）的动作号 → Switch 引擎内部动作号 的映射表（纯换算，逐行证据在那个头文件）。
// 没有它就会出现"推摇杆下 = 按左"：PC 的 `ACTION_MENULEFT(20)` 在 Switch 引擎里是"菜单下"。
#include "interfaces/lua/input_action_map.hpp"
#include "interfaces/lua/restart_input_chord.hpp"
#include "interfaces/lua/remaining_api.hpp"
#include "interfaces/lua/vector_api.hpp"

#include "lua_runtime_state.hpp"

extern "C" {
#include <lauxlib.h>
}

// 引擎调用层的短别名：本文件里"把已核对过的 thunk 变成可调用签名"只走它。
namespace engine_call = isaac::runtime::engine_call;

namespace isaac::runtime {

// 输入探针（2026-09-16，模组菜单那一轮）：菜单"按了没反应"时必须能分辨三种原因 ——
// 绑定根本没装上、动作号和手柄按键对不上、或者回调根本没跑。这三个量回答前两种：
//   * `g_InputActionTriggeredMask`：`IsActionTriggered` 回答过 `true` 的动作号（按位）；
//   * `g_InputActionQueriedMask`：被问过的动作号（按位）—— 用来确认"菜单确实在问"；
//   * `g_InputLastActionCode` / `g_InputLastActionResult`：最后一次问的号与结果。
// 它们是**我们自己的入口**的计数，与 `g_FontLoadCalls` 同一性质（真机可读、无副作用）。
std::atomic<std::uint32_t> g_InputActionTriggeredMask{0};
// 非 0 号 controller（手柄）上"回答过是"的动作号。真机上"键位对不上"最常见的原因就是
// controller 序号：PC 的 `Input.IsActionTriggered(动作, 0)` 里 0 通常指键盘，手柄是 1~4。
std::atomic<std::uint32_t> g_InputActionTriggeredMaskOther{0};
// `IsActionPressed` 的同一张位图（按住而不是"刚按下"）——两条查询互为对照。
std::atomic<std::uint32_t> g_InputActionPressedMask{0};
// 非 0 号 controller 上"按住"的动作号（与上面同一张位图的补充，用来确定手柄序号）。
std::atomic<std::uint32_t> g_InputActionPressedMaskOther{0};
std::atomic<std::uint32_t> g_InputActionQueriedMask{0};
std::atomic<std::uint32_t> g_InputLastActionCode{0xFFFFFFFFu};
std::atomic<std::uint32_t> g_InputLastActionResult{0};
std::atomic<std::uint32_t> g_InputLastController{0xFFFFFFFFu};
// 让"按住/刚按下"返回 true 的那些 controller 值（按 `controller & 31` 记位）。
// 真机结论（2026-09-16）：玩家自己的 `EntityPlayer.ControllerIndex`（那次是 33）才是引擎认的值，
// 猜 0/1 永远拿不到"按下"。这两张掩码就是用来一次读数钉死"到底该传什么"。
std::atomic<std::uint32_t> g_InputTriggeredControllerMask{0};
std::atomic<std::uint32_t> g_InputPressedControllerMask{0};

// `IsActionTriggered` 的上升沿表（只有游戏线程的派发路径读写它 ⇒ 普通对象、不是原子）。
// 类型由 `ActionEdgeTracker` 改名为 `InputFrameEdges`，并改成"帧上采样 + 纯读"
// （每帧由 `SampleInputFrame()` 在帧边界采一次；判定只看"本帧是不是边沿"）——
// 口径见 `runtime/source/input_edge.hpp` 第五节。`Entry` 布局未变（读数工具按它解码）。
LuaRuntime::InputFrameEdges g_ActionEdge{};

// 按键号那三条查询的读数（与上面动作那几张位图同族）。
// 为什么要有它：`IsButtonPressed` 从"恒 false"改成真值之后，真机上唯一能判"到底读到了没有"的
// 就是这两个计数 —— 手柄 A（按键号 4）按下时 `g_InputButtonPressedMask` 的第 4 位应当为 1，
// 松手为 0。没有它就只能看画面（而这条 API 不产生任何可见差异）。
std::atomic<std::uint32_t> g_InputButtonPressedMask{0};
std::atomic<std::uint32_t> g_InputButtonQueriedMask{0};

// PC→NS 手柄号映射的现场。
// 为什么要有它：模组问的"手柄号"是 PC 的编号（0=键盘、1..4=第几台手柄），引擎要的是
// Switch 的设备号（0=触摸屏、33=手柄）。翻错了就是恒答 false、且什么线索都不留
// （MCM 的"按右摇杆开菜单"卡了一整轮）。所以最近一次翻译的三个量必须可读：
// * `g_InputControllerMapPcId`：模组给的 controllerId；
// * `g_InputControllerMapNsId`：翻成的设备号（`Passthrough` 时 = 原样透传的值）；
// * `g_InputControllerMapOutcome`：0=透传、1=翻到设备表里某台、2=没有这台（键盘档/不够 k 台）；
// * `g_InputControllerMapFallbacks`：因为设备表没读到而没能翻译的次数（>0 说明兜底在跑）。
std::atomic<std::uint32_t> g_InputControllerMapPcId{0xFFFFFFFFu};
std::atomic<std::uint32_t> g_InputControllerMapNsId{0xFFFFFFFFu};
std::atomic<std::uint32_t> g_InputControllerMapOutcome{0xFFFFFFFFu};
std::atomic<std::uint32_t> g_InputControllerMapFallbacks{0};

// 模组动作号 → 引擎内部动作号翻译的现场。
// 为什么要有它：模组问的是 PC 的 `ButtonAction`（20 = `ACTION_MENULEFT`），而 Switch 引擎的内部表
// 把 20 当"菜单下" ⇒ 不翻译就是"推下被答成按左"（用户实测的那个缺陷），而且不报错、不崩。
// 口径与逐行证据在 `interfaces/lua/input_action_map.hpp`。这三个量让读数能一眼看出翻译在不在：
// * `g_InputActionMapLuaCode`：最后一次被翻译的模组动作号；
// * `g_InputActionMapEngineCode`：翻出来的引擎内部号（`0xFFFFFFFF` = Switch 上没有这个动作）；
// * `g_InputActionMapAbsent`：因为 Switch 上没有这个动作而直接答 false / 0 的次数（>0 = 该行在跑）。
std::atomic<std::uint32_t> g_InputActionMapLuaCode{0xFFFFFFFFu};
std::atomic<std::uint32_t> g_InputActionMapEngineCode{0xFFFFFFFFu};
std::atomic<std::uint32_t> g_InputActionMapAbsent{0};

// 引擎输入设备表的一张快照（起用；起按帧缓存）。
struct NsInputDeviceTableSnapshot {
    std::uint32_t ids[kNsInputDeviceCapacity];
    // 设备对象指针也存一份 —— 帧上采样要直接读设备对象的
    // `+0x30/+0x38`（引擎自己每帧维护的本帧/上帧按键位图），只存设备号不够用。
    std::uintptr_t pointers[kNsInputDeviceCapacity];
    std::size_t count;
};

// "还没有帧号"的哨兵（与上升沿表用同一个值，避免两处哨兵打架）。
constexpr std::uint32_t kNoInputFrame = LuaRuntime::InputFrameEdges::kNoFrame;

// 输入路径上"帧"的唯一定义。
//
// 更正：下面这句"上升沿判定靠 `本帧 == 上一次采样 + 1` 认相邻帧"
// 已不再成立 —— 取消了"必须严格相邻帧"，判定只看"上一次采样到没按住、这一次按住"
// （原因见 `runtime/source/input_edge.hpp` 第四节：真机量到渲染回调比更新回调少约 5.4%，
// 在渲染回调里每帧都问的模组会整次丢按下）。"帧号只有一个来源"这条纪律仍然要守，
// 因为它现在服务于诊断量（"上一次读到按住的帧"、边沿间隔）与"同一帧内答案一致"。
// 原文保留在下面，供后来者看到当时的形状。
//
// 为什么必须只有一个来源：上升沿判定靠 `本帧 == 上一次采样 + 1` 认"相邻帧"。
// 之前这里是"引擎帧计数读不到就退化成 `毫秒 ÷ 4`" —— 两个刻度差 4 倍以上，
// 混用会让帧号往回跳，而 `frame - last` 是无符号减法 ⇒ 溢出成天文数字
// ⇒ 判定成"早就松手了" ⇒ 误报一次边沿（"按一次跳多格"）；
// 反过来也会把真实连按并掉（"按着没反应"）。两种症状同时出现就是这么来的。
//
// 现在的定义 = `ManagedFrameClock`（`Isaac.GetFrameCount()` 的同一个真源：
// 每派发一次 `MC_POST_UPDATE` 加一，见那个类的注释）。选它的三个理由：
// 1. 它恰好等于"模组能跑代码的时机" —— 没有派发就没人问输入，
// 所以"帧号不动"与"没人观测"是同一件事，不会误报；
// 2. 不依赖引擎字段（不再需要 `Game*` 可读），主菜单/过场/宿主夹具一视同仁；
// 3. 它已经有了、已经在被 `Isaac.GetFrameCount()` 使用 ⇒ 不再新造设施。
//
// 引擎输入设备表的每帧缓存（读表本来每次查询都做一遍，MCM 每帧要问
// 28 个动作 × 5 个手柄号 = 140 次 ⇒ 每次都有若干次带校验的内存读；任何一次读失败就
// "原样透传"把设备号翻错 ⇒ 引擎按 `GetId()` 找不到那台手柄 ⇒ 答 false
// ⇒ 在上升沿判定看来就是一次"闪断"）。改成每帧只读一次，失败率随之降一个数量级。
//
// 只在游戏线程访问（Lua 派发路径），与 `g_ActionEdge` 同口径 ⇒ 普通变量、不是原子。
std::uint32_t g_InputDeviceTableFrame{kNoInputFrame};
bool g_InputDeviceTableKnown = false;
NsInputDeviceTableSnapshot g_InputDeviceTableSnapshot{};

// Input edges and cached device rows use the native polling cycle, shared by
// simulation and rendering consumers. Querying never advances this clock.
[[nodiscard]] std::uint32_t CurrentInputFrame() noexcept {
    return static_cast<std::uint32_t>(isaac::runtime::NativeFrameClock::Count());
}

// 每个动作报过几次"刚按下"（下标 = `动作 & 31`）。
// 为什么要有它：用户实测"有时候按一次跳两个物品" —— 有了这个计数，按一次键之后读一次数
// 就能直接判定"是我们报了两次边沿"还是"别的地方翻了两格"（`g_InputActionTriggeredMaskOther`
// 只知道"报过"，不知道"报了几次"）。读数工具会把非零项打出来。
std::atomic<std::uint32_t> g_InputEdgeCounts[32];

// 每个动作观察到的最长"闪断"帧数（按住期间连续多少帧读到"没按住"）。
// 更正：这里原来写"用途：看松手去抖窗口（`kReleaseFrames`）够不够" ——
// 那个窗口就删了，又把"严格相邻帧"也去掉了 ⇒ 现在没有窗口可调。
// 这一项现在的用途只剩一个：判"闪断"这个病灶到底还在不在（闪断会如实多报边沿，
// 因为我们的判定把它看成"松手又按下"）。真机读数里若某个动作的峰值明显 > 1，
// 要查的是源头（帧号来源、设备表读失败、模组自己漏问），不是加窗口。
std::atomic<std::uint32_t> g_InputReleaseRunPeak[32];

// "一次按住报了几次边沿"（= 用户报的"按一次有多次效果"的直接判据）。
// 为什么不能拿 `g_InputEdgeCounts` 判：那个是按调用次数累加的，而我们的语义是"同一帧内问多少次
// 都答 true" ⇒ 它约等于"按住的帧数"，分不出"一次按住报了多次边沿"与"用户按了很久/按了很多次"。
// 这两个数组才分得出：
// * `g_InputEdgeGapMin[动作]`：报边沿时"距上一次读到按住"的最小间隔（0 = 还没样本）——
// 2~3 帧 ⇒ 是闪断（判定如实多报，要去源头修）；
// * `g_InputEdgeGapLast[动作]`：最近一次边沿的间隔（对照用：几百帧就是真松手再按）。
// 更正：原文里"贴着去抖窗口（`kReleaseFrames + 1` 附近）"那句作废 ——
// 窗口与"必须严格相邻帧"都已不存在（见 `input_edge.hpp` 第四节的真机依据）。
std::atomic<std::uint32_t> g_InputEdgeGapMin[32];
std::atomic<std::uint32_t> g_InputEdgeGapLast[32];

// 每个动作最后一次被问到时的那四项现场 ——
// 「第几帧被问、问的是哪条 API、controller、我们答了什么」。
//
// 为什么非要有它（这是"菜单操作问题"最后卡住的地方）：原来那几个掩码是粘性的 ——
// `g_InputActionQueriedMask` 一旦置位永不清，真机上早就饱和成 `0x0fffffff`（问过全部 28 个动作）
// ⇒ 分不出"用户按下的那一刻，菜单到底问没问、我们答的是真还是假"。
// 有了"帧号 + 答案"，一次读数就能判：
// * 某个动作在刚才那几帧被问过、而且我们答了 true ⇒ 那就是模组自己的逻辑没走（不是我们）；
// * 被问过、我们答 false ⇒ 问题在我们的查询链（手柄号/设备/引擎判定）；
// * 压根没被问 ⇒ 模组没走到那一步（它自己的前置条件没满足）。
// 三个 kind：0 = `IsActionTriggered`、1 = `IsActionPressed`、2 = `GetActionValue`
// （kind=2 时 `answer` 存的是浮点数的原始位，读数工具按 float 打印）。
std::atomic<std::uint32_t> g_InputActionAskedFrame[32];
std::atomic<std::uint32_t> g_InputActionAskedKind[32];
std::atomic<std::uint32_t> g_InputActionAskedController[32];
std::atomic<std::uint32_t> g_InputActionAskedAnswer[32];

// 按键侧与动作侧分开计数 —— 原来两条路都往 `g_InputEdgeCounts`
// 累加，而按键号与动作号是两套命名空间（同一个下标是两个之和）⇒ 真机上
// "菜单为什么走了按键分支 / 某个按键到底报没报过边沿"分不出来（工具自己在打印里都写着"不能单独归因"）。
std::atomic<std::uint32_t> g_InputButtonEdgeCounts[32];

// 按键侧"最后一次被问到时"的现场（与动作侧那四个数组一一对应，kind 用同一套编号：
// 0 = `IsButtonTriggered`、1 = `IsButtonPressed`、2 = `GetButtonValue`）。
// 为什么必须有：中文版 MCM 每帧先问一次
// `InputHelper.MultipleButtonTriggered({DPAD_UP..DPAD_DOWN, BUTTON_A..Y})`，任一为真就整块跳过动作导航
// ⇒ 判"菜单走的是按键分支还是动作分支"只能看按键侧答了什么，动作侧的掩码帮不上忙。
std::atomic<std::uint32_t> g_InputButtonAskedFrame[32];
std::atomic<std::uint32_t> g_InputButtonAskedKind[32];
std::atomic<std::uint32_t> g_InputButtonAskedController[32];
std::atomic<std::uint32_t> g_InputButtonAskedAnswer[32];

// 每个动作/按键"最后一次答 true 的帧号"。
//
// 为什么还要再加一组（217/218 那两族不够）：那两族记的是"最后一次被问时答什么"，
// 而 MCM 每帧都在问 ⇒ 读到的永远是"读数那一刻的输入状态"（用户早松手了 ⇒ 全是 false）。
// 要回答"推摇杆下的时候，到底是哪个动作号被激活"（比如"下"会不会错激活成 `ACTION_UP`），
// 必须把"答 true 的时刻"钉在帧号上。
// 于是：用户按一次方向、读数把两组帧号一比 ⇒ 立刻看出"这一次按的是哪个动作号"，
// 以及"顺序上它和哪一次按键重叠"（同一帧里按键与动作同时为真 ⇒ 模组会切到按键分支）。
std::atomic<std::uint32_t> g_InputActionHeldFrame[32];
std::atomic<std::uint32_t> g_InputButtonTriggeredFrame[32];

// 每帧"全动作快照" —— 我们自己把全部动作号与按键号各查一遍。
//
// 为什么非要有它：真机上"推摇杆下"时，MCM 问的那 10 个动作号里只有 `ACTION_PILLCARD(10)` 答 true、
// `ACTION_DOWN(3)` 恒 false（连续两次读数一致，`dist/gdb-read-20260930-1620*-stick-down-held*.txt`），
// 而推"左"时 `ACTION_LEFT(0)` 是正确的。⇒ 要判"引擎把'下'接到哪个动作号上"，
// 必须看到全部 28+ 个动作的答案，而那两组探针只记"模组问过的"
// （MCM 只问 10 个号）⇒ 另外 18 个是黑的。
//
// 本组由我们自己每帧普查：28+ 个动作的 `IsActionPressed`（位图）、同批的 `GetActionValue`（浮点）、
// 18 个手柄按键的 `IsButtonPressed`（位图）。`GetActionValue` 尤其关键 ——
// 它直接暴露"模拟量数组里哪一格有值"，能区分「绑定表错位」与「索引错位」。
//
// 三条纪律（都是本项目踩过的坑）：
// ① 只查无副作用的引擎读 —— 绝不调我们自己的 `IsActionTriggered`（那会推进边沿表状态）；
// ② 只写本组数组，不碰 `g_InputActionAsked*` / `g_InputButtonAsked*` 那两组"谁问的"现场
// （的教训：普查会把现场全覆盖成它自己）；
// ③ 走 `ResolveInputDeviceQuiet()` —— 不写"最近一次手柄号翻译"那三个探针（同理）。
std::atomic<std::uint32_t> g_InputSnapshotFrame{kNoInputFrame};
// 此刻答"按住"的动作号位图（bit = 动作号；我们查 0..31，越界的引擎自己会答 false）。
std::atomic<std::uint32_t> g_InputActionSnapshotPressed{0};
// 此刻答"按住"的手柄按键号位图（bit = 按键号 0..17）。
std::atomic<std::uint32_t> g_InputButtonSnapshotPressed{0};
// 每个动作的 `GetActionValue`（存 float 的原始位；读数工具按浮点打印）。
std::atomic<std::uint32_t> g_InputActionSnapshotValue[32];

// "动作 → 绑定的按钮码"表的现场 dump（查"+17 错位"的根因）。
//
// 为什么要它：真机上"推左 / 右 / 下"时，引擎同时答 `action` 与 `action + 17` 为真
// （左 ⇒ 0 与 17、右 ⇒ 1 与 18、下 ⇒ 3 与 20，四个数据点全部对上）⇒
// 嫌疑是"那张表里第 i 项与第 i+17 项绑到了同一个输入"（输入被重复绑定）。
// 要修就得先看清表，不能再猜。
//
// 采法（表的来源见 `runtime_constants.hpp` 里 `kKageInputDeviceActionTableOffset` 的证据）：
// * `设备+0x1c` = 动作数；`设备+0x20` = "每动作一个指针"的数组，指针指向该动作的按钮码数组；
// * 每个动作采前 4 个按钮码（够看出"第 i 项与第 i+17 项是否同一份内容"）。
// 表在设备初始化时就建好、之后不变 ⇒ 只采一次（`g_InputBindingDumpDone`）；
// 采失败不置位，下一帧会重试（游戏刚起来时设备表可能还没建好）。
std::atomic<std::uint32_t> g_InputBindingDumpDone{0};
std::atomic<std::uint32_t> g_InputBindingActionCount{0};
std::atomic<std::uint32_t> g_InputBindingArrayPtr[32];
std::atomic<std::uint32_t> g_InputBindingCodes[32][4];

// 设备内部输入状态的原始 dump —— 查"推方向时引擎多报 `action+17`"的
// 最后一步（口径与理由见 `runtime_constants.hpp` 里那一组 `kKageInputDevice*` 的注释）。
//
// 有了什么：已证明"动作 12..23 没有任何按钮绑定"（绑定数组指针全 0），
// 而多报的号（17/18/20）全落在这一段 ⇒ 多报只能来自 `IsActionPressed` 的第二条判定
// 「`analog[action] > 死区`」⇒ 必须直接看 `+0xd0` 那 24 格的原始值。
// 这些格子每帧都在变（模拟量、位图）⇒ 与"绑定表（只采一次）"不同，这里是每帧都采。
std::atomic<std::uint32_t> g_InputDeviceStateDumpCount{0};
// 设备启用字节（`+0xd`；0 ⇒ 整个设备答 false）。
std::atomic<std::uint32_t> g_InputDeviceStateEnabled{0};
// 动作数（`+0x1c`；真机实测 = 24 ⇒ Switch 只支持动作 0..23）。
std::atomic<std::uint32_t> g_InputDeviceStateActionCount{0};
// 本帧 / 上一帧的按键位图（`+0x30` / `+0x38`）。
std::atomic<std::uint32_t> g_InputDeviceStateKeysCurrent{0};
std::atomic<std::uint32_t> g_InputDeviceStateKeysPrevious{0};
// 本帧 / 上一帧的摇杆方向位图（`+0x40` / `+0x48`）。
std::atomic<std::uint32_t> g_InputDeviceStateStickCurrent{0};
std::atomic<std::uint32_t> g_InputDeviceStateStickPrevious{0};
// 两个死区（`+0xe4` 是动作判定用的那一个；`+0xe0` 是摇杆长度重映射那一处）。
std::atomic<std::uint32_t> g_InputDeviceStateDeadzone{0};
std::atomic<std::uint32_t> g_InputDeviceStateDeadzoneAlt{0};
// 每动作的模拟量（`+0xd0[action]`，float 原始位）—— 这份才是 `IsActionPressed` 真正读的。
std::atomic<std::uint32_t> g_InputDeviceStateActionValue[32];
// 8 个轴幅值（`+0x50 + 4*i`）。
std::atomic<std::uint32_t> g_InputDeviceStateAxes[8];

// 设备对象整块原始内存的 dump —— 用户要求"读全"，
// 且已排除"选错设备"（用户确认：机器上只有那一台手柄）。
//
// 为什么换成"原始字节"：逐字段读出来的值与引擎自己的判定对不上
// （引擎说"动作 20 被按住"，而按我的字段假设读出的 `+0xd0[20]` 是 0）。
// 逐字段读的前提是"我猜对了字段布局"，而那个前提已经不成立 ⇒ 换成把原样端上来、事后解释。
//
// 采法（每帧一次，与其它快照同帧，保证"引擎的答案"与"原始字节"是同一时刻、同一台设备）：
// `+0x00..+0x1FF`（已知字段全在这段）、`+0x400..+0x49F`（`Poll` 里出现过 `+0x478`）、
// `*(+0xd0)` 与 `*(+0xd8)` 两份数组的前 32 格、以及设备表里每一台设备的指针与 id。
std::atomic<std::uint32_t> g_InputDeviceRawDumpCount{0};
std::atomic<std::uint32_t> g_InputDeviceRawPointerLow{0};
std::atomic<std::uint32_t> g_InputDeviceRawPointerHigh{0};
std::atomic<std::uint32_t> g_InputDeviceRawId{0};
std::atomic<std::uint32_t> g_InputDeviceRawHead[128];
std::atomic<std::uint32_t> g_InputDeviceRawTail[40];
std::atomic<std::uint32_t> g_InputDeviceRawValues[32];
std::atomic<std::uint32_t> g_InputDeviceRawValuesPrevious[32];
std::atomic<std::uint32_t> g_InputDeviceTableCount{0};
std::atomic<std::uint32_t> g_InputDeviceTablePointer[8];
// 表项指针的高 32 位（加：只存低 32 位时，打印出来会被截断成 `0x47a3b000`
// 这种看着像指针、其实不是完整地址的值，读数时会被误读）。
std::atomic<std::uint32_t> g_InputDeviceTablePointerHigh[8];
std::atomic<std::uint32_t> g_InputDeviceTableId[8];
// 当次选中的那台设备的号（0 = 没选中任何一台）—— 与上面的表同一个时刻采的。
std::atomic<std::uint32_t> g_InputDeviceSelectedId{0};

// "我读的表"与"引擎用的表"是不是同一处 —— 一次读数定死。
//
// 起因：226 的读数里"当次选中的设备号 = 33"与"表里只有触摸屏（id 0）"互相矛盾
// （同一函数、同一帧）。两种解释必须靠数据分开：① 表在两次读之间变了；② 我读表的位置与引擎用的不是一处。
//
// 采法（同一次采里）：来源（`manager` 指针、向量的 begin/end）各记一遍，
// 然后紧接着再读一遍表（两遍之间不做别的事）⇒ 两遍不同就是"表在变"；
// 另外记"选中的那台在表里的第几项"（`0xFFFFFFFF` = 不在表里 ⇒ "选"与"打印"用的不是同一处）。
std::atomic<std::uint32_t> g_InputDeviceRawManagerLow{0};
std::atomic<std::uint32_t> g_InputDeviceRawManagerHigh{0};
std::atomic<std::uint32_t> g_InputDeviceRawBeginLow{0};
std::atomic<std::uint32_t> g_InputDeviceRawBeginHigh{0};
std::atomic<std::uint32_t> g_InputDeviceRawEndLow{0};
std::atomic<std::uint32_t> g_InputDeviceRawEndHigh{0};
std::atomic<std::uint32_t> g_InputDeviceRawBeginPass2Low{0};
std::atomic<std::uint32_t> g_InputDeviceRawBeginPass2High{0};
std::atomic<std::uint32_t> g_InputDeviceRawEndPass2Low{0};
std::atomic<std::uint32_t> g_InputDeviceRawEndPass2High{0};
std::atomic<std::uint32_t> g_InputDeviceTablePass2Count{0};
std::atomic<std::uint32_t> g_InputDeviceTablePass2Pointer[8];
std::atomic<std::uint32_t> g_InputDeviceTablePass2PointerHigh[8];
std::atomic<std::uint32_t> g_InputDeviceTablePass2Id[8];
// 选中的那台在表里的下标（`0xFFFFFFFF` = 不在表里）。
std::atomic<std::uint32_t> g_InputDeviceSelectedIndex{0xFFFFFFFFu};
// 读设备表时的失败次数（>0 ⇒ 表里有格子读不到，别把哨兵 `0xFFFFFFFF` 当成真值）。
std::atomic<std::uint32_t> g_InputDeviceTableReadFailures{0};

// 帧上采样的现场。
//
// 为什么要有它：新机制把"边沿"从"由调用方的询问节奏决定"搬到"每帧固定时刻采一次、
// 只在那一帧有效"（口径见 `runtime/source/input_edge.hpp` 第五节）。⇒ 必须能回答
// "采样真的在跑吗、每帧花了多少次引擎调用、采了哪些东西、有没有失败"这几件事。
//
// * `g_InputSampleFrame`：最后一次采样的帧号（真机上应贴着当前帧）；
// * `g_InputSampleCalls`：那一帧的引擎调用次数（真机 1 台手柄时 = 动作侧 32 次；
// 按键侧不调引擎 —— 直接读设备对象的本帧/上帧位图 ⇒ 0 次）；
// * `g_InputSampleCodes`：那一帧采了几个码（按键 0..17 + 动作 0..31 = 50）；
// * `g_InputSampleDevices`：那一帧采了几台设备（+1 = "任意设备" `0xFFFFFFFF` 聚合槽）；
// * `g_InputSampleFailures`：采样失败累计（设备表读不到 / 设备对象读不到 / 绑定没发布）。
//
// 定义在匿名命名空间之外（外部链接）⇒ 读数工具按符号直读；正式包里也编。
std::atomic<std::uint32_t> g_InputSampleFrame{kNoInputFrame};
std::atomic<std::uint32_t> g_InputSampleCalls{0};
std::atomic<std::uint32_t> g_InputSampleCodes{0};
std::atomic<std::uint32_t> g_InputSampleDevices{0};
std::atomic<std::uint32_t> g_InputSampleFailures{0};

namespace {

// "读失败"的哨兵值 —— 探针里必须把"读不到"与"值真的是 0"分开。
// 起因：227 的读数里"选中的那台在第 1 项"与"第 1 项的值 = 0"互相矛盾，根子在我：
// `ReadAt(...)` 失败时不写输出变量，而我把输出变量初始化成 0 ⇒ 读失败被打印成"值是 0"
// ⇒ 整整一轮把"表里没有手柄"当成了事实。本项目的老纪律：读不到就如实说，不许编造。
// （放在匿名命名空间最早处，供下面所有 dump 函数使用。）
[[maybe_unused]] inline constexpr std::uint32_t kProbeReadFailed = 0xFFFFFFFFu;

// 帧上采样集合的上界。
// 按键号 0..17（`kKageControllerButtonMaximum`）、动作号 0..31（低 5 位可用域）。
// 放在匿名命名空间最前面（本项目纪律）：`InputIsActionPressed`（下面）与采样器
// （最后）都要用它 —— 放在使用点之后就编不过（`-Werror` 的 `not declared`）。
inline constexpr std::uint32_t kSampleButtonCodeCount = kKageControllerButtonMaximum + 1u;
inline constexpr std::uint32_t kSampleActionCodeCount = LuaRuntime::InputFrameEdges::kSlots;

int InputIsButtonTriggered(lua_State* state);
int InputIsButtonPressed(lua_State* state);
int InputGetButtonValue(lua_State* state);
int InputIsActionTriggered(lua_State* state);
int InputIsActionPressed(lua_State* state);
int InputGetActionValue(lua_State* state);
// 鼠标两条（，为 GoodTrip 补）：Switch 上明确降级，见实现处注释。
int InputGetMousePosition(lua_State* state);
int InputIsMouseBtnPressed(lua_State* state);
// 每帧"全动作快照"的刷新（定义在下面的处理器之后，口径见探针数组的声明处）。
void RefreshInputSnapshot() noexcept;

constexpr LuaHandlerBinding kInputHandlers[] = {
    {0x09010001, &InputIsButtonTriggered},
    {0x09010002, &InputIsButtonPressed},
    {0x09010003, &InputGetButtonValue},
    {0x09010004, &InputIsActionTriggered},
    {0x09010005, &InputIsActionPressed},
    {0x09010006, &InputGetActionValue},
    // （GoodTrip）：鼠标两条。PC 的签名里只有鼠标按钮号，没有 controller 参数。
    {0x09010007, &InputGetMousePosition},
    {0x09010008, &InputIsMouseBtnPressed},
};

constexpr char kInputOwner[] = "Input";

// 调用约定（2026-09-16 修正，这是"按键查询永远答没按下"的真因）：
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
// 2026-09-19 修正（ABI 体检的"少给参数"判据修正后当场查出来）：
// 引擎签名是 `Manager::IsActionPressed(unsigned int, unsigned int, Entity*)`（`tools/engine_symbol_signatures.json`），
// 我们原先只声明了 3 个形参（被跳板覆盖的 Manager* + 动作号 + controller）⇒ **第 4 个寄存器是调用方的残留值**。
// PC 的 Input 包装只消费动作号和手柄号，并给底层查询传空指针。
// 额外 Lua 参数不映射为原生 Entity*，不能把模组附带的布尔值当指针。
using ActionQueryFn = bool (*)(void* /* 被跳板覆盖的 Manager* */, std::uint32_t, std::uint32_t,
                               void* /* Entity*：原始 Input 查询传 nullptr */);
using ActionValueFn = float (*)(void*, std::uint32_t, std::uint32_t, void*);

// PC bindings consume the two required arguments and ignore trailing Lua values.
void CheckInputQueryArguments(lua_State* state, const char* apiName) {
    if (lua_gettop(state) < 2 || !isaac::runtime::IsIntegerArgument(state, 1) || !isaac::runtime::IsIntegerArgument(state, 2)) {
        luaL_error(state, "%s accepts input code and controllerId integers", apiName);
    }
}

// ============================================================================
// `Input.IsButtonPressed` / `IsButtonTriggered` / `GetButtonValue`
// ============================================================================
//
// 这三条以前是"恒 false / 恒 0"的桩，理由是"引擎里没有按按键号查询的入口"。那条前提已被
// 推翻**（证据规格 `analysis/api-restore-input-keys/spec.json`）：
//   * 入口在 `KAGE::Input::ManagerBase` 上：`IsButtonPressed @ 0x4F9504` /
//     `IsButtonTriggered @ 0x4F9648` / `GetButtonValue @ 0x4F97B0`，单例槽 `0xAAC768`；
//   * **游戏自己就在用**：`Game::ProcessInput` 的 L+R+StickL+StickR 组合键（按键 8/11/10/13）、
//     `Menu_Title::Update`、`Console::check_key_autorepeat` —— 全部传 `deviceId = 0xFFFFFFFF`；
//   * 手柄按键号 `0..15` 与 PC 的 `Controller` 枚举**逐项相同**
//     （`analysis/mod-corpus/isaac-mod-config-menu/scripts/inputhelper.lua:40-55`）。
//
// 调用约定：`x0 = ManagerBase*`（要自己从槽里取，这条不像动作那三条有自带 `g_Manager`
//   的跳板）、`w1 = button`、`w2 = deviceId`（`0xFFFFFFFF` = 任意设备）、`x3 = 可空的 out 指针`；
//   `GetButtonValue` 的返回值走 **s0**。我们一律传 `out = nullptr`（PC 的 Lua 侧不暴露它）。
//
// 键盘码一律答 false / 0.0，绝不透传：引擎按 `button & 31` 取位，`KEY_SPACE(32)` 会撞上
//   "方向左"、`KEY_R(82)` 撞到位 18（没人写）—— 透传等于"按一次空格就误报左方向键按下"
//   （模组自己都知道这个坑：InputHelper 写 `IsButtonTriggered(key) and not
//   IsButtonTriggered(key % 32)`）。Switch 引擎里**确实没有键盘设备**（`KAGE::Input` 的类全列
//   只有手柄/触摸两个设备类，`Manager::Initialize` 只 new 两个），所以键盘码没有真值来源 ⇒
//   答 false 与 PC 上"那个键没被按"同形，是**不误报**的那一侧。这条偏离登记在 `api_deviation.cpp`。
//
// PC 的六个 Input 查询只读取键码/动作号和手柄号；尾随 Lua 参数不参与查询。
// 不能限制总参数个数，也不能校验未消费参数的类型。
//
// 边沿（Triggered）不用引擎那条：引擎的 `+0x38` 语义是"上一帧也按着"
//   （`InputDeviceBase::Poll @ 0x4F70B0` 把 `+0x30` 复制进 `+0x38`），不是 PC 文档说的
//   "问一次就消费掉的上升沿"。与 `IsActionTriggered` 同一处置：拿"按住"当唯一原语，
//   用**我们自己的边沿表**算。
using ButtonBoolFn = bool (*)(void* /* KAGE::Input::ManagerBase* */, std::uint32_t button,
                             std::uint32_t deviceId,
                             void* /* unsigned* outDeviceId，我们一律传 nullptr */);
using ButtonFloatFn = float (*)(void* /* 同上 */, std::uint32_t button, std::uint32_t deviceId,
                               void* /* 同上 */);

// `Input.IsButtonTriggered` 用的边沿表 —— 与动作那条分开：PC 里按键号与动作号是两套
// 命名空间，共用一张表会让 `IsActionTriggered(4, c)` 与 `IsButtonTriggered(4, c)` 互相干扰。
// 类型改名 `InputFrameEdges`，同样改成"帧上采样 + 纯读"（见 `input_edge.hpp` 第五节）。
LuaRuntime::InputFrameEdges g_ButtonEdge{};

// Only the two consumed arguments are validated and converted.
struct InputButtonArguments {
    lua_Integer code{};
    lua_Integer controller{};
};
InputButtonArguments CheckInputButtonArguments(lua_State* state, const char* apiName) {
    InputButtonArguments arguments{};
    const int top = lua_gettop(state);
    if (top < 2 ||
        !isaac::runtime::IntegerArgumentAt(state, 1, &arguments.code) ||
        !isaac::runtime::IntegerArgumentAt(state, 2, &arguments.controller)) {
        luaL_error(state, "%s accepts an input button and a controller id",
                   apiName);
    }
    return arguments;
}

// 这个按键号是不是"手柄按键"？只有 0..17 有真值来源（见 `kKageControllerButtonMaximum`）。
// 键盘码（`Keyboard.KEY_*` 是 GLFW 键码，>= 32）与一切越界值都答"没有"。
bool IsControllerButtonCode(lua_Integer code) noexcept {
    return code >= 0 && static_cast<std::uint64_t>(code) <= kKageControllerButtonMaximum;
}

// 取 `KAGE::Input::g_Manager`（GOT 槽 → 指针）。读不到 ⇒ false。
//
// 宿主门禁夹具没有引擎映像（模块基址 0）⇒ 这里返回 false，调用方给**保守答案**（false / 0.0）
// 且**绝不抛错** —— 与"引擎还没起来时"同形。
bool ReadKageInputManager(std::uintptr_t* out) noexcept {
    if (out == nullptr) {
        return false;
    }
    const std::uintptr_t base = LuaRuntime::EngineModuleBase();
    if (base == 0 || base > UINTPTR_MAX - kKageInputManagerSlotOffset) {
        return false;
    }
    std::uintptr_t manager = 0;
    if (!isaac::runtime::engine_memory::ReadAt(base + kKageInputManagerSlotOffset, &manager,
                                               &isaac::runtime::engine_memory::EngineMemoryReadable) ||
        manager == 0) {
        return false;
    }
    *out = manager;
    return true;
}

// ============================================================================
// PC 的 `controllerId` → Switch 设备号
// ============================================================================
//
// 口径在 `runtime/source/pc_ns_input_device_map.hpp`（那张表 + 三条规则的证据）。这里只做两件事：
// **把引擎的设备表读出来**、**把换算结果接上探针**。六条查询（按键三条 + 动作三条）共用它。
//
// 为什么必须做这一步（同一个坑第三次）：PC 模组传 `controllerId = 1`（PC 上"第 1 台手柄"），
//   而 Switch 引擎的设备号里那台手柄是 `33` ⇒ 引擎按 `GetId()` 找不到 ⇒ 恒答 false。
//   前两次（嵌入式模组菜单、主菜单自绘入口）都是靠"猜候选 + 自学习"绕过去的，这次改成**读设备表**。
// 读表结果按帧缓存（`g_InputDeviceTableFrame` 那三个变量），
//   不再每次查询都读一遍 —— 理由见缓存变量的声明处（重复读表的失败会伪装成"按住闪断"）。
//
// 读引擎的设备表（`ManagerBase + 0x8` = 向量 begin、`+0x10` = end；每个条目 = 设备指针、
// 设备 `+0x8` = 设备号）。任一步读不到 ⇒ false（调用方按"表读不到"的口径原样透传，并计数）。
// 半张表比没有更糟 ⇒ 中途失败就整体判读不到，不返回半份快照。
bool ReadNsInputDeviceTable(NsInputDeviceTableSnapshot* out) noexcept {
    if (out == nullptr) {
        return false;
    }
    out->count = 0;
    std::uintptr_t manager = 0;
    if (!ReadKageInputManager(&manager)) {
        return false;
    }
    std::uintptr_t begin = 0;
    std::uintptr_t end = 0;
    if (!isaac::runtime::engine_memory::ReadAt(manager + kKageInputDeviceVectorBeginOffset, &begin,
                                               &isaac::runtime::engine_memory::EngineMemoryReadable) ||
        !isaac::runtime::engine_memory::ReadAt(manager + kKageInputDeviceVectorEndOffset, &end,
                                               &isaac::runtime::engine_memory::EngineMemoryReadable)) {
        return false;
    }
    if (begin == 0 || end < begin) {
        return false;
    }
    const std::size_t raw = static_cast<std::size_t>(end - begin) / sizeof(std::uintptr_t);
    const std::size_t count = raw < kNsInputDeviceCapacity ? raw : kNsInputDeviceCapacity;
    for (std::size_t index = 0; index < count; ++index) {
        std::uintptr_t device = 0;
        if (!isaac::runtime::engine_memory::ReadAt(begin + index * sizeof(std::uintptr_t), &device,
                                                   &isaac::runtime::engine_memory::EngineMemoryReadable) ||
            device == 0 ||
            !isaac::runtime::engine_memory::ReadAt(device + kKageInputDeviceIdOffset, &out->ids[index],
                                                   &isaac::runtime::engine_memory::EngineMemoryReadable)) {
            out->count = 0;
            return false;
        }
        // 把设备对象指针也留下（帧上采样读 `+0x30/+0x38` 要用）。
        out->pointers[index] = device;
    }
    out->count = count;
    return true;
}

struct ResolvedInputDevice {
    bool query;             // false = 这台设备不存在 ⇒ 直接答 false / 0.0（引擎一次都不问）
    std::uint32_t device_id;
    NsDeviceSelection kind; // 翻译结果的性质（给"最近一次翻译"探针用；加）
};

// 把模组给的 `controllerId` 翻成引擎要的 `deviceId`。纯解析，不记任何探针。
//
// 拆出来是给"每帧全动作快照"（`RefreshInputSnapshot`）用的 —— 那个普查走这条，
// 免得把"最近一次手柄号翻译"的现场覆盖掉（普查不是"模组的一次查询"，不该冒充它）。
ResolvedInputDevice ResolveInputDeviceQuiet(lua_Integer pc_controller_id) noexcept {
    // 设备表每帧只读一次（帧号没变就直接用缓存）。
    //   原来每次查询都读 ⇒ MCM 每帧 140 次查询就是 140 次带校验的内存读，
    //   任何一次失败都会把设备号翻错（透传）⇒ 引擎答 false ⇒ 上升沿判定看成"闪断"。
    const std::uint32_t frame = CurrentInputFrame();
    if (g_InputDeviceTableFrame != frame) {
        g_InputDeviceTableFrame = frame;
        g_InputDeviceTableKnown = ReadNsInputDeviceTable(&g_InputDeviceTableSnapshot);
    }
    const bool known = g_InputDeviceTableKnown;
    // 走去重版（`MapPcControllerIdToNsInputDeviceDeduped`）—— 同一台物理手柄
    //   可能以两个设备号出现（真机 `1` 与 `33` 相差 32 ⇒ 同槽），去重后 `for i = 0, 4` 里
    //   同一台手柄**只命中一次**（否则中文版 MCM 会在同一帧里 toggle 两次：先开、再立刻关）。
    //   动作侧的六条处理器**共用**这一个解析入口 ⇒ 一并受益。
    const NsDeviceTarget target = MapPcControllerIdToNsInputDeviceDeduped(
        static_cast<std::int64_t>(pc_controller_id), g_InputDeviceTableSnapshot.ids,
        known ? g_InputDeviceTableSnapshot.count : 0,
        known ? NsDeviceTableState::Known : NsDeviceTableState::Unknown);
    return ResolvedInputDevice{target.kind != NsDeviceSelection::NoSuchDevice, target.device_id,
                               target.kind};
}

// 模组一次查询走的入口：解析 + 记"最近一次翻译"那三个探针。
ResolvedInputDevice ResolveInputDevice(lua_Integer pc_controller_id) noexcept {
    const ResolvedInputDevice resolved = ResolveInputDeviceQuiet(pc_controller_id);
    if (!g_InputDeviceTableKnown && pc_controller_id >= kPcFirstGamepadControllerId &&
        pc_controller_id <= kPcLastGamepadControllerId) {
        // 设备表没读到 ⇒ 没能翻译（原样透传）。这种降级必须被看见，不许静默。
        g_InputControllerMapFallbacks.fetch_add(1, std::memory_order_relaxed);
    }
    g_InputControllerMapPcId.store(static_cast<std::uint32_t>(pc_controller_id),
                                   std::memory_order_relaxed);
    g_InputControllerMapNsId.store(resolved.device_id, std::memory_order_relaxed);
    g_InputControllerMapOutcome.store(static_cast<std::uint32_t>(resolved.kind),
                                      std::memory_order_relaxed);
    return resolved;
}

// 取"输入管理器 + 已核对过的引擎入口"这一对。任一步不成立（没有引擎映像 / 绑定没发布 /
// 入口指纹不符）⇒ false，调用方给**保守答案**（false / 0.0），**绝不抛错**。
//
// 注意：这条助手只做"取地址与核对"，真正的调用写在各处理器自己的正文里 —— 桩检测器
// （`tools/lua_api_stub_report.py`）按"处理器正文里有没有碰引擎的标记"判桩，把调用整个
// 藏进助手会让这三条被重新判成桩（而它们已经是真实现）。
bool ResolveButtonQuery(std::uintptr_t* manager, std::uintptr_t* method,
                        std::uintptr_t thunk) noexcept {
    if (manager == nullptr || method == nullptr || thunk == 0) {
        return false;
    }
    if (!ReadKageInputManager(manager)) {
        return false;
    }
    *method = thunk;
    return true;
}

int InputIsButtonTriggered(lua_State* state) {
    const auto arguments = CheckInputButtonArguments(state, "Input.IsButtonTriggered");
    if (console::ConsoleCapturesInput()) { lua_pushboolean(state, 0); return 1; }
    const lua_Integer code = arguments.code;
    // 键盘码 / 越界：**没有真值来源**（见上面那段），答 false 且不查引擎。
    if (!IsControllerButtonCode(code)) {
        lua_pushboolean(state, 0);
        return 1;
    }
    // 模组给的是 PC 的手柄号（0 = 键盘、1..4 = 第 1..4 台手柄），引擎要的是
    // **Switch 的设备号**（0 = 触摸屏、33 = 手柄）⇒ 先按 `pc_ns_input_device_map.hpp` 翻译。
    // "没有这台"（键盘档 / 第 k 台手柄不存在）⇒ **引擎一次都不问**，直接答 false（PC 上也是 false）。
    // 无真值来源的键码在上方保留原答案；只有实际输入查询需要快照。
    RefreshInputSnapshot();
    const ResolvedInputDevice target = ResolveInputDevice(arguments.controller);
    if (!target.query) {
        lua_pushboolean(state, 0);
        return 1;
    }
    const std::uint32_t controller = target.device_id;
    // 纯读。
    //
    // 原来这里要"现查引擎的按住状态、再喂给边沿表算差分"，于是边沿的定义落在
    // "**自这个调用方上一次问过以来**"上 —— 中文版 MCM 的 `MultipleButtonTriggered(ignoreActionButtons)`
    // 闸门一旦早退（`modconfig.lua:2259`），被它跳过的那个按键边沿下一帧还会被认成"新按下"
    // ⇒ **十字键又驱动了菜单**（机制与两张脸见 `runtime/source/input_edge.hpp` 第五节）。
    // 现在边沿由**每帧固定时刻的帧上采样**（`SampleInputFrame`）写好，这里只看
    // "**这一格在本帧是不是边沿**" ⇒ 与 PC 的"过了那一次 update 就没了"同形。
    // 不再查引擎：按键侧的边沿在采样时就地由引擎对象的 `本帧 & ~上帧` 位图算好。
    // 更正：上面那句"由引擎对象的 `本帧 & ~上帧` 位图算好"作废 ——
    //   数据源已改成"采样时对 0..17 **逐个问引擎**"（那格 `+0x30` 不是引擎用的按键位图），
    //   但**判定仍是纯读**（边沿由 `InputFrameEdges` 一帧一份地差分，第三个实参仍 `nullptr`）。
    const std::uint32_t frame = CurrentInputFrame();
    // The reserved platform chord is one logical command. Keep physical held
    // state, but do not also deliver its components as standalone button edges.
    const bool reservedChord = NativeRestartChordButton(static_cast<std::uint32_t>(code)) &&
                               g_ActionEdge.Pressed(kLuaRestartAction, kNsAnyInputDevice, frame);
    const bool triggered = !reservedChord &&
                          g_ButtonEdge.Triggered(static_cast<std::uint32_t>(code), controller, frame);
    // 记"这次问的现场"（见那四个数组的声明处）。
    g_InputButtonAskedFrame[static_cast<std::uint32_t>(code) & 31u].store(frame,
                                                                         std::memory_order_relaxed);
    g_InputButtonAskedKind[static_cast<std::uint32_t>(code) & 31u].store(0u, std::memory_order_relaxed);
    g_InputButtonAskedController[static_cast<std::uint32_t>(code) & 31u].store(
        controller, std::memory_order_relaxed);
    g_InputButtonAskedAnswer[static_cast<std::uint32_t>(code) & 31u].store(triggered ? 1u : 0u,
                                                                           std::memory_order_relaxed);
    if (triggered) {
        g_InputButtonTriggeredFrame[static_cast<std::uint32_t>(code) & 31u].store(
            frame, std::memory_order_relaxed);
    }
    g_InputButtonQueriedMask.fetch_or(1u << (static_cast<std::uint32_t>(code) & 31u),
                                      std::memory_order_relaxed);
    if (triggered) {
        // 按键侧记自己的数组（原来与动作侧共用 `g_InputEdgeCounts` ⇒ 两套命名空间混在一起）。
        g_InputButtonEdgeCounts[static_cast<std::uint32_t>(code) & 31u].fetch_add(
            1, std::memory_order_relaxed);
    }
    lua_pushboolean(state, triggered ? 1 : 0);
    return 1;
}

int InputIsButtonPressed(lua_State* state) {
    const auto arguments = CheckInputButtonArguments(state, "Input.IsButtonPressed");
    if (console::ConsoleCapturesInput()) { lua_pushboolean(state, 0); return 1; }
    const lua_Integer code = arguments.code;
    if (!IsControllerButtonCode(code)) {
        lua_pushboolean(state, 0);
        return 1;
    }
    // 手柄号翻译同 `IsButtonTriggered`。
    // 无真值来源的键码在上方保留原答案；只有实际输入查询需要快照。
    RefreshInputSnapshot();
    const ResolvedInputDevice target = ResolveInputDevice(arguments.controller);
    if (!target.query) {
        lua_pushboolean(state, 0);
        return 1;
    }
    // （A2，"按住"与"边沿"同源）：采样集合内的 (按键号, 设备) 答同一次采样的值
    //   —— PC 上"按住"与"边沿"本来就是同一次 Poll 出来的（口径见 `input_edge.hpp` 第五节）。
    //   采样记录里没有这一格的**本帧**记录（采样没跑 / 设备不在表里）时**回退现查**，
    //   不引入新风险（旧路径逐字保留在 else 分支里）。
    const std::uint32_t sampleFrame = CurrentInputFrame();
    bool pressed = false;
    if (g_ButtonEdge.HasFrame(static_cast<std::uint32_t>(code), target.device_id, sampleFrame)) {
        pressed =
            g_ButtonEdge.Pressed(static_cast<std::uint32_t>(code), target.device_id, sampleFrame);
    } else {
        std::uintptr_t manager = 0;
        std::uintptr_t method = 0;
        if (ResolveButtonQuery(&manager, &method, LuaRuntime::InputIsButtonPressedThunk()) &&
            LuaRuntime::ValidateInputIsButtonPressedBinding(method)) {
            pressed = engine_call::AsFunction<ButtonBoolFn>(method)(
                isaac::runtime::engine_memory::AsObject(manager), static_cast<std::uint32_t>(code),
                target.device_id, nullptr);
        }
    }
    // 见 `g_InputButtonAskedFrame` 的声明处。
    {
        const std::uint32_t slot = static_cast<std::uint32_t>(code) & 31u;
        const std::uint32_t now = CurrentInputFrame();
        g_InputButtonAskedFrame[slot].store(now, std::memory_order_relaxed);
        g_InputButtonAskedKind[slot].store(1u, std::memory_order_relaxed);
        g_InputButtonAskedController[slot].store(target.device_id, std::memory_order_relaxed);
        g_InputButtonAskedAnswer[slot].store(pressed ? 1u : 0u, std::memory_order_relaxed);
    }
    if (pressed) {
        g_InputButtonPressedMask.fetch_or(1u << (static_cast<std::uint32_t>(code) & 31u),
                                          std::memory_order_relaxed);
    }
    lua_pushboolean(state, pressed ? 1 : 0);
    return 1;
}

int InputGetButtonValue(lua_State* state) {
    const auto arguments = CheckInputButtonArguments(state, "Input.GetButtonValue");
    if (console::ConsoleCapturesInput()) { lua_pushnumber(state, 0); return 1; }
    const lua_Integer code = arguments.code;
    if (!IsControllerButtonCode(code)) {
        lua_pushnumber(state, 0.0);
        return 1;
    }
    // 手柄号翻译同 `IsButtonTriggered`。
    const ResolvedInputDevice target = ResolveInputDevice(arguments.controller);
    if (!target.query) {
        lua_pushnumber(state, 0.0);
        return 1;
    }
    std::uintptr_t manager = 0;
    const std::uintptr_t method = LuaRuntime::InputGetButtonValueThunk();
    if (!ReadKageInputManager(&manager) || method == 0 ||
        !LuaRuntime::ValidateInputGetButtonValueBinding(method)) {
        lua_pushnumber(state, 0.0);
        return 1;
    }
    const auto query = engine_call::AsFunction<ButtonFloatFn>(method);
    lua_pushnumber(state, static_cast<lua_Number>(
                              query(isaac::runtime::engine_memory::AsObject(manager),
                                    static_cast<std::uint32_t>(code), target.device_id, nullptr)));
    return 1;
}

// 模组的（PC）动作号 → 引擎内部动作号，并把翻译现场记进探针。
//
// 为什么三条入口都必须过这里：PC 的 `ButtonAction` 与 Switch 引擎的内部表不是同一张表
//   （PC 的 `ACTION_MENULEFT = 20`，Switch 引擎的 20 = "菜单下"）⇒ 原样递过去就会
//   "推摇杆下 = 按左"（中文版 MCM 把它读成"左"，用户实测的那个缺陷）。逐行证据见
//   `interfaces/lua/input_action_map.hpp` 的文件头。
// 返回 `kNoEngineAction` ⇒ Switch 引擎里没有这个动作（FULLSCREEN/MUTE/RESTART/…）：
//   调用点**直接答 false / 0**，不许把这个哨兵当动作号递给引擎（设备层对越界号会判假，
//   但那是巧合、不是本表的意思，而且会把"平台上没有"和"现在没按"混成同一件事）。
[[nodiscard]] std::uint32_t TranslateActionForEngine(std::uint32_t lua_action) noexcept {
    const std::uint32_t engine_action = TranslateLuaActionToEngineAction(lua_action);
    g_InputActionMapLuaCode.store(lua_action, std::memory_order_relaxed);
    g_InputActionMapEngineCode.store(engine_action, std::memory_order_relaxed);
    if (engine_action == kNoEngineAction) {
        g_InputActionMapAbsent.fetch_add(1, std::memory_order_relaxed);
    }
    return engine_action;
}

// 2026-09-20：不再用引擎那条"刚按下"查询，改用我们自己算的上升沿。
//
// 证据（真机读数 + 反汇编）：`KAGE::Input::ManagerBase::IsActionPressed @ 0x4F9920` 与
// `IsActionTriggered @ 0x4F9A64` 结构完全相同（找控制器条目 → 调它的虚函数 → 取返回值），
// 只有虚函数槽不同（`vtable+0x48` vs `+0x50`）。而真机上："按住"位图对
// 动作 4/5/6/7/13、controller = 33（玩家自己的 `EntityPlayer.ControllerIndex`，09-16 已钉）**为真**，
// "刚按下"位图**一次都没为真** ⇒ **同一条控制器、同一个动作，Pressed 通、Triggered 永远假**
// —— 引擎那份上升沿状态在我们跑到它的时候（`MC_POST_UPDATE`/`MC_POST_RENDER` 里）是空的。
//
// 于是：拿**已验证可用**的 `IsActionPressed` 当唯一原语，自己按引擎帧算上升沿
// （`LuaRuntime::InputFrameEdges`，更正：原名 `ActionEdgeTracker`，
// 且改成"每帧在引擎帧边界采一次、判定纯读"）。与 PC 的差别写在 `api_deviation.cpp`。
int InputIsActionTriggered(lua_State* state) {
    RefreshInputSnapshot();     //
    CheckInputQueryArguments(state, "Input.IsActionTriggered");
    if (console::ConsoleCapturesInput()) { lua_pushboolean(state, 0); return 1; }
    const std::uintptr_t thunk = LuaRuntime::InputIsActionPressedThunk();
    if (thunk == 0) {
        return luaL_error(state, "Input.IsActionTriggered native binding is unavailable");
    }
    const auto code = static_cast<std::uint32_t>(lua_tointeger(state, 1));
    // 翻译现场照旧记进探针（`g_InputActionMap*`，读数连续性）；本判定不再用它。
    static_cast<void>(TranslateActionForEngine(code));
    // 动作这族同样是模组的 PC 手柄号 → Switch 设备号（MCM 的菜单导航就是
    // `for index = 0, 4 do Input.IsActionPressed(动作, index)`；不翻译 ⇒ 菜单能开也动不了）。
    const ResolvedInputDevice target = ResolveInputDevice(lua_tointeger(state, 2));
    if (!target.query) {
        lua_pushboolean(state, 0);
        return 1;
    }
    const std::uint32_t controller = target.device_id;
    // 纯读。
    //
    // 边沿由**每帧固定时刻的帧上采样**（`SampleInputFrame`）写好，这里只看"**这一格在本帧
    // 是不是边沿**"（口径见 `runtime/source/input_edge.hpp` 第五节）。中文版 MCM 的
    // `actionsDown/Up/Left/Right` 同时含移动动作与菜单动作，而 `inputhelper.lua` 的
    // `MultipleActionTriggered` **碰到第一个为真的动作就 `return`** ⇒ 排在后面的动作号当帧
    // 不被问；旧判定（"自这个调用方上次问过以来"）下一帧把它认成"新按下"⇒ **光标再走一格**
    //（"一次推动走两格"）。改成纯读之后，"晚一帧问"一律答 false ⇒ 与 PC 同形。
    const std::uint32_t frame = CurrentInputFrame();
    const bool triggered = g_ActionEdge.Triggered(code, controller, frame);
    // 把"这次问的现场"记下来（见那四个数组的声明处 —— 粘性掩码分不出"按下的那一刻"）。
    // 记的是引擎 + 边沿表算出来的那一次回答，不是"这一帧有没有报过"（同帧多次问答案相同）。
    g_InputActionAskedFrame[code & 31u].store(frame, std::memory_order_relaxed);
    g_InputActionAskedKind[code & 31u].store(0u, std::memory_order_relaxed);
    g_InputActionAskedController[code & 31u].store(controller, std::memory_order_relaxed);
    g_InputActionAskedAnswer[code & 31u].store(triggered ? 1u : 0u, std::memory_order_relaxed);
    g_InputReleaseRunPeak[code & 31u].store(g_ActionEdge.PeakReleaseRun(code, controller),
                                            std::memory_order_relaxed);
    // 把"边沿间隔的最小值 / 最近值"也报出去（判据见这两个量的声明处）。
    g_InputEdgeGapMin[code & 31u].store(g_ActionEdge.MinEdgeGap(code, controller),
                                        std::memory_order_relaxed);
    g_InputEdgeGapLast[code & 31u].store(g_ActionEdge.LastEdgeGap(code, controller),
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
    RefreshInputSnapshot();     //
    RecordApiSequenceSecondary(32U);
    CheckInputQueryArguments(state, "Input.IsActionPressed");
    if (console::ConsoleCapturesInput()) { lua_pushboolean(state, 0); return 1; }
    const std::uintptr_t thunk = LuaRuntime::InputIsActionPressedThunk();
    if (thunk == 0) {
        return luaL_error(state, "Input.IsActionPressed native binding is unavailable");
    }
    const auto query = engine_call::AsFunction<ActionQueryFn>(thunk);
    const auto code = static_cast<std::uint32_t>(lua_tointeger(state, 1));
    // 先翻译动作号（同 `IsActionTriggered`；口径见 `input_action_map.hpp`）。
    const std::uint32_t engine_action = TranslateActionForEngine(code);
    // 手柄号翻译同 `IsActionTriggered`。
    const ResolvedInputDevice target = ResolveInputDevice(lua_tointeger(state, 2));
    if (!target.query) {
        lua_pushboolean(state, 0);
        return 1;
    }
    // （A2，"按住"与"边沿"同源）：采样集合内的 (动作号, 设备) 答同一次采样的值
    //   —— PC 上"按住"与"边沿"本来就是同一次 Poll 出来的（口径见 `input_edge.hpp` 第五节）。
    //   集合外（动作号 ≥ 采样上界 / 该槽本帧没记录）**回退现查**，不引入新风险。
    const std::uint32_t sampleFrame = CurrentInputFrame();
    bool held = false;
    if (code < kSampleActionCodeCount &&
        g_ActionEdge.HasFrame(code, target.device_id, sampleFrame)) {
        held = g_ActionEdge.Pressed(code, target.device_id, sampleFrame);
    } else {
        held = engine_action != kNoEngineAction &&
               query(nullptr, engine_action, target.device_id, nullptr);
    }
    // 见 `g_InputActionAskedFrame` 的声明处。
    {
        const std::uint32_t slot = code & 31u;
        const std::uint32_t frame = CurrentInputFrame();
        g_InputActionAskedFrame[slot].store(frame, std::memory_order_relaxed);
        g_InputActionAskedKind[slot].store(1u, std::memory_order_relaxed);
        g_InputActionAskedController[slot].store(target.device_id, std::memory_order_relaxed);
        g_InputActionAskedAnswer[slot].store(held ? 1u : 0u, std::memory_order_relaxed);
        if (held) {
            g_InputActionHeldFrame[slot].store(frame, std::memory_order_relaxed);
        }
    }
    if (held) {
        const auto controller = target.device_id;
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

// 指针源 = 触摸屏（2026-09-28 ；此前的"平台固有、永远消不掉"已被用户推翻并还清）。
//
// 保留的历史判据（说明**为什么必须不抛错**）：GoodTrip 的 `scripts/control.lua:190` **每帧**调
// `Input.GetMousePosition(true)`，只用它的结果算"鼠标这一帧动了没有"（与上一帧的距离平方 > 4）；
// 每帧调用点一旦报错，整条回调会被派发器静默摘掉。
//
// 为什么改成触摸屏：PC 模组里"鼠标悬停某处才显示信息"的交互在真机上是**死的**
//（EID 的 `EID:handleHoverHUD()`，`main.lua:1050`），而 `hid` 服务权限本来就在模块清单里
//（`runtime/exlaunch/config.json`）⇒ 缺的不是权限，是没做。
int InputGetMousePosition(lua_State* state) {
    if (lua_gettop(state) != 0 && lua_gettop(state) != 1) {
        return luaL_error(state, "Input.GetMousePosition takes an optional boolean");
    }
    // 2026-09-29：两种 `gameCoords` 都按 PC 语义实现（旧版两种都给"画布坐标"）。
    //
    //   * `false`（PC 叫 "render coordinates"）= **窗口像素**。核算：PC 默认窗口 960×540、
    //     `POINTSCALE=2`，`(false)` 给 0..960；`(true)` 再除 2 得到 0..480 的渲染平面点。
    //     Switch 上触摸面板与 framebuffer 同尺寸 ⇒ **窗口像素就是触摸面板原始读数（0..1280）**。
    //   * `true`（PC："world coordinates"）= 世界坐标 = `Isaac.ScreenToWorld(窗口像素)`
    //     （PC 的 handler 自己内联了同一套算术）。
    //
    // 的 `×0.375` 是错的：0.375 = 480/1280 是"画布"系数，而掌机的渲染平面是
    //   426×240**（系数 426/1280 = 0.3328），而且 `WIDTH`/`HEIGHT`/`POINTSCALE` 都是**运行期全局**
    //   （`ResizeWindow` 会改）⇒ 一律不硬编码，由 `TransformScreenToWorldPosition` 运行期从
    //   引擎全局读（它们读不到时它返回 false，我们原样给出窗口像素）。
    //
    // 这条与 `Isaac.WorldToScreen` 的配对关系随之改变：模组的
    //   `Isaac.WorldToScreen(Input.GetMousePosition(true))` 现在是 `W2S ∘ S2W`，仍是正确组合；
    //   旧版那种"两个恒等凑出来恰好对"的耦合同时消失（门禁 `test_touch_pointer.py` 的
    //   `test_the_world_coord_deviation_is_coupled_to_worldtoscreen` 按说明改写）。
    //
    // 仍然：**绝不抛错**（参数不对那条除外）。GoodTrip 的 `scripts/control.lua:190` 每帧调它，
    // 抛错会让整条回调被派发器摘掉。没有触摸时给**上一次**的位置（"鼠标不动时位置不变"）。
    const bool worldCoordinates = lua_gettop(state) == 1 && lua_isboolean(state, 1) &&
                                  lua_toboolean(state, 1) != 0;
    static TouchPointerSnapshot gameTouch{};
    if (!console::ConsoleCapturesInput()) {
        const TouchPointerSnapshot touch = ReadTouchPointer();
        gameTouch=touch;
    }
    float x = static_cast<float>(gameTouch.rawX);
    float y = static_cast<float>(gameTouch.rawY);
    if (worldCoordinates) {
        float world[2] = {x, y};
        // 引擎还没进局（`g_Game` 为空）或换算常量读不到 ⇒ **原样返回输入**（PC 的空指针保护行为）。
        static_cast<void>(TransformScreenToWorldPosition(&x, world));
        x = world[0];
        y = world[1];
    }
    // `PushLuaVector` 收的是 float（Isaac 的 Vector 分量本来就是 float），显式转，别靠隐式收窄。
    PushLuaVector(state, x, y);
    return 1;
}

// 同 `GetMousePosition`，指针源改成触摸屏 —— 手指在屏幕上 = 左键按下
//（用户 2026-09-28 定的语义：最接近 PC 的"按住鼠标"，且天然适配 EID 的"3 秒内动过"判定：
// 松手 3 秒后悬停信息自动消失）。仍然**绝不抛错**（参数不对那条除外）。
int InputIsMouseBtnPressed(lua_State* state) {
    CheckMouseButtonArguments(state, "Input.IsMouseBtnPressed");
    if (console::ConsoleCapturesInput()) { lua_pushboolean(state, 0); return 1; }
    const TouchPointerSnapshot touch = ReadTouchPointer();
    lua_pushboolean(state, !console::ConsoleCapturesInput() && touch.pressed ? 1 : 0);
    return 1;
}

int InputGetActionValue(lua_State* state) {
    RefreshInputSnapshot();     //
    CheckInputQueryArguments(state, "Input.GetActionValue");
    if (console::ConsoleCapturesInput()) { lua_pushnumber(state, 0); return 1; }
    const std::uintptr_t thunk = LuaRuntime::InputGetActionValueThunk();
    if (thunk == 0) {
        return luaL_error(state, "Input.GetActionValue native binding is unavailable");
    }
    // 手柄号翻译同 `IsActionTriggered`。
    const ResolvedInputDevice target = ResolveInputDevice(lua_tointeger(state, 2));
    if (!target.query) {
        lua_pushnumber(state, 0.0);
        return 1;
    }
    // The PC API returns a float; the game's own function is the authority on the scale.
    const auto query = engine_call::AsFunction<ActionValueFn>(thunk);
    const std::uint32_t code = static_cast<std::uint32_t>(lua_tointeger(state, 1));
    // 先翻译动作号（与 `IsActionPressed/Triggered` 同一个口径）；Switch 上没有的动作 ⇒ 0。
    const std::uint32_t engine_action = TranslateActionForEngine(code);
    const float value = code == kLuaRestartAction
                            ? (g_ActionEdge.Pressed(code, target.device_id, CurrentInputFrame()) ? 1.0f : 0.0f)
                        : engine_action != kNoEngineAction
                            ? query(nullptr, engine_action, target.device_id, nullptr)
                            : 0.0f;
    // 见 `g_InputActionAskedFrame` 的声明处；kind=2 的 answer 存浮点原始位。
    {
        const std::uint32_t slot = code & 31u;
        const std::uint32_t frame = CurrentInputFrame();
        std::uint32_t bits = 0;
        static_assert(sizeof(bits) == sizeof(value), "float must be 4 bytes");
        std::memcpy(&bits, &value, sizeof(bits));
        g_InputActionAskedFrame[slot].store(frame, std::memory_order_relaxed);
        g_InputActionAskedKind[slot].store(2u, std::memory_order_relaxed);
        g_InputActionAskedController[slot].store(target.device_id, std::memory_order_relaxed);
        g_InputActionAskedAnswer[slot].store(bits, std::memory_order_relaxed);
    }
    lua_pushnumber(state, static_cast<lua_Number>(value));
    return 1;
}

// ============================================================================
// 设备对象的定位（建、抽出复用）
// ============================================================================
// 找"第 1 台手柄"（= 真机上的设备 33）的设备对象指针；找不到 ⇒ 0（`outDeviceId` 给选中的设备号）。
// 优先按"翻译后的设备号"匹配（口径见 `pc_ns_input_device_map.hpp`）；翻译不出来就取
// "第一台非 0 号设备"（触摸屏的设备号是 0）。读不到就是读不到，不编造（调用方按 0 处理）。
//
// 不再缓存。原来找到一次就记在 `g_GamepadDevicePointer` 里、之后永远返回它 ——
// 结果是"设备表已经变了（表里没有手柄）而我还拿着旧指针去读" ⇒ 同一帧里采到两份互相矛盾的数据
// （旧对象的内容 + 当次读的表）：225 那次读数就出现了"设备表里没有 id=33、而'设备对象'里死区是 0"
// 这种自相矛盾。每次重新解析，并把"当次选中的设备号"一起报出去，保证"表、设备、答案"同帧同源。
#if EXL_DIAGNOSTIC_PROBES  // 只被上面那几个 dump 用（口径见 probe_gate.hpp）
std::uintptr_t FindGamepadDevice(std::uint32_t* outDeviceId) noexcept {
    if (outDeviceId != nullptr) {
        *outDeviceId = 0;
    }
    std::uintptr_t manager = 0;
    if (!ReadKageInputManager(&manager)) {
        return 0;
    }
    std::uintptr_t begin = 0;
    std::uintptr_t end = 0;
    if (!isaac::runtime::engine_memory::ReadAt(manager + kKageInputDeviceVectorBeginOffset, &begin,
                                               &isaac::runtime::engine_memory::EngineMemoryReadable) ||
        !isaac::runtime::engine_memory::ReadAt(manager + kKageInputDeviceVectorEndOffset, &end,
                                               &isaac::runtime::engine_memory::EngineMemoryReadable) ||
        begin == 0 || end <= begin) {
        return 0;
    }
    const std::size_t raw = static_cast<std::size_t>(end - begin) / sizeof(std::uintptr_t);
    const ResolvedInputDevice target = ResolveInputDeviceQuiet(kPcFirstGamepadControllerId);
    std::uintptr_t fallback = 0;
    std::uint32_t fallbackId = 0;
    for (std::size_t index = 0; index < raw && index < kNsInputDeviceCapacity; ++index) {
        std::uintptr_t candidate = 0;
        std::uint32_t id = 0;
        if (!isaac::runtime::engine_memory::ReadAt(begin + index * sizeof(std::uintptr_t), &candidate,
                                                   &isaac::runtime::engine_memory::EngineMemoryReadable) ||
            candidate == 0 ||
            !isaac::runtime::engine_memory::ReadAt(candidate + kKageInputDeviceIdOffset, &id,
                                                   &isaac::runtime::engine_memory::EngineMemoryReadable)) {
            continue;
        }
        if (target.query && id == target.device_id) {
            if (outDeviceId != nullptr) {
                *outDeviceId = id;
            }
            return candidate;
        }
        if (id != 0 && fallback == 0) {
            fallback = candidate;
            fallbackId = id;
        }
    }
    if (outDeviceId != nullptr) {
        *outDeviceId = fallbackId;
    }
    return fallback;
}
#endif  // EXL_DIAGNOSTIC_PROBES

// ============================================================================
// 把"动作 → 按钮码"表 dump 一次（口径见 `g_InputBindingDumpDone` 的声明处）
// ============================================================================
#if EXL_DIAGNOSTIC_PROBES  // 正式包不编进这一段（口径见 probe_gate.hpp）
void DumpInputBindings() noexcept {
    if (g_InputBindingDumpDone.load(std::memory_order_relaxed) != 0) {
        return;     // 表建好之后不变 ⇒ 一次就够
    }
    const std::uintptr_t device = FindGamepadDevice(nullptr);
    if (device == 0) {
        return;
    }
    std::uint32_t actionCount = 0;
    std::uintptr_t table = 0;
    if (!isaac::runtime::engine_memory::ReadAt(device + kKageInputDeviceActionCountOffset,
                                               &actionCount,
                                               &isaac::runtime::engine_memory::EngineMemoryReadable) ||
        !isaac::runtime::engine_memory::ReadAt(device + kKageInputDeviceActionTableOffset, &table,
                                               &isaac::runtime::engine_memory::EngineMemoryReadable) ||
        table == 0) {
        return;
    }
    g_InputBindingActionCount.store(actionCount, std::memory_order_relaxed);
    const std::uint32_t limit = actionCount < 32u ? actionCount : 32u;
    for (std::uint32_t action = 0; action < limit; ++action) {
        std::uintptr_t codes = 0;
        if (!isaac::runtime::engine_memory::ReadAt(table + action * sizeof(std::uintptr_t), &codes,
                                                   &isaac::runtime::engine_memory::EngineMemoryReadable) ||
            codes == 0) {
            continue;
        }
        g_InputBindingArrayPtr[action].store(static_cast<std::uint32_t>(codes),
                                             std::memory_order_relaxed);
        for (std::uint32_t slot = 0; slot < 4u; ++slot) {
            std::uint32_t code = 0;
            static_cast<void>(isaac::runtime::engine_memory::ReadAt(
                codes + slot * sizeof(std::uint32_t), &code,
                &isaac::runtime::engine_memory::EngineMemoryReadable));
            g_InputBindingCodes[action][slot].store(code, std::memory_order_relaxed);
        }
    }
    g_InputBindingDumpDone.store(1, std::memory_order_relaxed);
}
#endif  // EXL_DIAGNOSTIC_PROBES

// ============================================================================
// 每帧采一次"设备内部输入状态"（口径见 `g_InputDeviceStateDumpCount` 的声明处）
// ============================================================================
#if EXL_DIAGNOSTIC_PROBES  // 正式包不编进这一段（口径见 probe_gate.hpp）
void DumpInputDeviceState() noexcept {
    const std::uintptr_t device = FindGamepadDevice(nullptr);
    if (device == 0) {
        return;
    }
    using isaac::runtime::engine_memory::EngineMemoryReadable;
    using isaac::runtime::engine_memory::ReadAt;

    std::uint8_t enabled = 0;
    if (!ReadAt(device + kKageInputDeviceEnabledOffset, &enabled, &EngineMemoryReadable)) {
        return;                     // 设备对象还没建好 ⇒ 下一帧再试（不置任何"完成"标志）
    }
    g_InputDeviceStateEnabled.store(enabled, std::memory_order_relaxed);

    std::uint32_t actionCount = 0;
    std::uint32_t keysCurrent = 0;
    std::uint32_t keysPrevious = 0;
    std::uint32_t stickCurrent = 0;
    std::uint32_t stickPrevious = 0;
    float deadzone = 0.0f;
    float deadzoneAlt = 0.0f;
    static_cast<void>(ReadAt(device + kKageInputDeviceActionCountOffset, &actionCount,
                             &EngineMemoryReadable));
    static_cast<void>(ReadAt(device + kKageInputDeviceKeysCurrentOffset, &keysCurrent,
                             &EngineMemoryReadable));
    static_cast<void>(ReadAt(device + kKageInputDeviceKeysPreviousOffset, &keysPrevious,
                             &EngineMemoryReadable));
    static_cast<void>(ReadAt(device + kKageInputDeviceStickCurrentOffset, &stickCurrent,
                             &EngineMemoryReadable));
    static_cast<void>(ReadAt(device + kKageInputDeviceStickPreviousOffset, &stickPrevious,
                             &EngineMemoryReadable));
    static_cast<void>(ReadAt(device + kKageInputDeviceDeadzoneOffset, &deadzone,
                             &EngineMemoryReadable));
    static_cast<void>(ReadAt(device + kKageInputDeviceDeadzoneAltOffset, &deadzoneAlt,
                             &EngineMemoryReadable));
    g_InputDeviceStateActionCount.store(actionCount, std::memory_order_relaxed);
    g_InputDeviceStateKeysCurrent.store(keysCurrent, std::memory_order_relaxed);
    g_InputDeviceStateKeysPrevious.store(keysPrevious, std::memory_order_relaxed);
    g_InputDeviceStateStickCurrent.store(stickCurrent, std::memory_order_relaxed);
    g_InputDeviceStateStickPrevious.store(stickPrevious, std::memory_order_relaxed);

    const auto bits = [](float value) {
        std::uint32_t raw = 0;
        std::memcpy(&raw, &value, sizeof(raw));
        return raw;
    };
    g_InputDeviceStateDeadzone.store(bits(deadzone), std::memory_order_relaxed);
    g_InputDeviceStateDeadzoneAlt.store(bits(deadzoneAlt), std::memory_order_relaxed);

    // **每动作的模拟量**（`+0xd0[action]`）—— 这才是 `IsActionPressed` 真正读的那一份。
    std::uintptr_t values = 0;
    if (ReadAt(device + kKageInputDeviceActionValueOffset, &values, &EngineMemoryReadable) &&
        values != 0) {
        for (std::uint32_t action = 0; action < 32u; ++action) {
            float value = 0.0f;
            static_cast<void>(ReadAt(values + action * sizeof(std::uint32_t), &value,
                                     &EngineMemoryReadable));
            g_InputDeviceStateActionValue[action].store(bits(value), std::memory_order_relaxed);
        }
    }
    // 8 个轴幅值（`+0x50 + 4*i`）。
    for (std::uint32_t axis = 0; axis < 8u; ++axis) {
        float value = 0.0f;
        static_cast<void>(ReadAt(device + kKageInputDeviceAxesOffset + axis * sizeof(std::uint32_t),
                                 &value, &EngineMemoryReadable));
        g_InputDeviceStateAxes[axis].store(bits(value), std::memory_order_relaxed);
    }
    static_cast<void>(g_InputDeviceStateDumpCount.fetch_add(1, std::memory_order_relaxed));
}
#endif  // EXL_DIAGNOSTIC_PROBES

// ============================================================================
// 设备对象整块原始内存的 dump（口径见 `g_InputDeviceRawDumpCount` 的声明处）
// ============================================================================
#if EXL_DIAGNOSTIC_PROBES  // 正式包不编进这一段（口径见 probe_gate.hpp）
void DumpInputDeviceRaw() noexcept {
    std::uint32_t selectedId = 0;
    const std::uintptr_t device = FindGamepadDevice(&selectedId);
    g_InputDeviceSelectedId.store(selectedId, std::memory_order_relaxed);
    if (device == 0) {
        return;
    }
    using isaac::runtime::engine_memory::EngineMemoryReadable;
    using isaac::runtime::engine_memory::ReadAt;

    g_InputDeviceRawPointerLow.store(static_cast<std::uint32_t>(device), std::memory_order_relaxed);
    g_InputDeviceRawPointerHigh.store(static_cast<std::uint32_t>(device >> 32u),
                                      std::memory_order_relaxed);
    std::uint32_t id = 0;
    static_cast<void>(ReadAt(device + kKageInputDeviceIdOffset, &id, &EngineMemoryReadable));
    g_InputDeviceRawId.store(id, std::memory_order_relaxed);

    // 头部 0x000..0x1FF（128 个 u32）—— 已知字段全落在这一段里。
    for (std::uint32_t index = 0; index < 128u; ++index) {
        std::uint32_t word = 0;
        static_cast<void>(ReadAt(device + index * sizeof(std::uint32_t), &word,
                                 &EngineMemoryReadable));
        g_InputDeviceRawHead[index].store(word, std::memory_order_relaxed);
    }
    // 尾部 0x400..0x49F（40 个 u32；`Poll` 的摇杆段里出现过 `+0x478`）。
    for (std::uint32_t index = 0; index < 40u; ++index) {
        std::uint32_t word = 0;
        static_cast<void>(ReadAt(device + 0x400u + index * sizeof(std::uint32_t), &word,
                                 &EngineMemoryReadable));
        g_InputDeviceRawTail[index].store(word, std::memory_order_relaxed);
    }
    // 两份"每动作模拟量"数组 —— `+0xd0` 与 `+0xd8` **都是指针**（`Poll` 里 memcpy 的那一对）。
    for (std::uint32_t which = 0; which < 2u; ++which) {
        std::uintptr_t values = 0;
        if (!ReadAt(device + kKageInputDeviceActionValueOffset + which * sizeof(std::uintptr_t),
                    &values, &EngineMemoryReadable) ||
            values == 0) {
            continue;
        }
        for (std::uint32_t index = 0; index < 32u; ++index) {
            std::uint32_t word = 0;
            static_cast<void>(ReadAt(values + index * sizeof(std::uint32_t), &word,
                                     &EngineMemoryReadable));
            if (which == 0) {
                g_InputDeviceRawValues[index].store(word, std::memory_order_relaxed);
            } else {
                g_InputDeviceRawValuesPrevious[index].store(word, std::memory_order_relaxed);
            }
        }
    }
    // 设备表：每一台设备的指针与 id（"只有一台手柄"的正证也在这里）。
    // 顺便记"来源"（manager / 向量 begin、end）与"选中项在表里的下标"，
    //   并**紧接着再读一遍表**（两遍之间不做别的事）⇒ 一次读数就能分清
    //   "表在变" 还是 "我选的项不在我打印的那些项里"。
    std::uintptr_t manager = 0;
    g_InputDeviceSelectedIndex.store(0xFFFFFFFFu, std::memory_order_relaxed);
    if (ReadKageInputManager(&manager)) {
        g_InputDeviceRawManagerLow.store(static_cast<std::uint32_t>(manager),
                                         std::memory_order_relaxed);
        g_InputDeviceRawManagerHigh.store(static_cast<std::uint32_t>(manager >> 32u),
                                          std::memory_order_relaxed);
        std::uintptr_t begin = 0;
        std::uintptr_t end = 0;
        if (ReadAt(manager + kKageInputDeviceVectorBeginOffset, &begin, &EngineMemoryReadable) &&
            ReadAt(manager + kKageInputDeviceVectorEndOffset, &end, &EngineMemoryReadable) &&
            begin != 0 && end > begin) {
            g_InputDeviceRawBeginLow.store(static_cast<std::uint32_t>(begin),
                                           std::memory_order_relaxed);
            g_InputDeviceRawBeginHigh.store(static_cast<std::uint32_t>(begin >> 32u),
                                            std::memory_order_relaxed);
            g_InputDeviceRawEndLow.store(static_cast<std::uint32_t>(end),
                                         std::memory_order_relaxed);
            g_InputDeviceRawEndHigh.store(static_cast<std::uint32_t>(end >> 32u),
                                          std::memory_order_relaxed);
            const std::size_t raw = static_cast<std::size_t>(end - begin) / sizeof(std::uintptr_t);
            const std::uint32_t limit = raw < 8u ? static_cast<std::uint32_t>(raw) : 8u;
            g_InputDeviceTableCount.store(limit, std::memory_order_relaxed);
            for (std::uint32_t index = 0; index < limit; ++index) {
                std::uintptr_t candidate = 0;
                std::uint32_t deviceId = 0;
                // 读失败 ⇒ 记哨兵 + 计数，绝不冒充 0（227 那次就是这么被误导的）。
                if (!ReadAt(begin + index * sizeof(std::uintptr_t), &candidate,
                            &EngineMemoryReadable)) {
                    static_cast<void>(g_InputDeviceTableReadFailures.fetch_add(
                        1, std::memory_order_relaxed));
                    g_InputDeviceTablePointer[index].store(kProbeReadFailed,
                                                           std::memory_order_relaxed);
                    g_InputDeviceTablePointerHigh[index].store(kProbeReadFailed,
                                                               std::memory_order_relaxed);
                    g_InputDeviceTableId[index].store(kProbeReadFailed,
                                                      std::memory_order_relaxed);
                    continue;
                }
                if (candidate != 0 &&
                    !ReadAt(candidate + kKageInputDeviceIdOffset, &deviceId,
                            &EngineMemoryReadable)) {
                    static_cast<void>(g_InputDeviceTableReadFailures.fetch_add(
                        1, std::memory_order_relaxed));
                    deviceId = kProbeReadFailed;
                }
                // 选中的那一台在表里的下标（用于判"选"与"打印"是不是同一处）。
                if (candidate != 0 && candidate == device) {
                    g_InputDeviceSelectedIndex.store(index, std::memory_order_relaxed);
                }
                g_InputDeviceTablePointer[index].store(static_cast<std::uint32_t>(candidate),
                                                       std::memory_order_relaxed);
                g_InputDeviceTablePointerHigh[index].store(
                    static_cast<std::uint32_t>(candidate >> 32u), std::memory_order_relaxed);
                g_InputDeviceTableId[index].store(deviceId, std::memory_order_relaxed);
            }
        }
        // 第二遍：**立刻**重读（中间不做别的）⇒ 两遍若不同，就是"表在变"。
        std::uintptr_t begin2 = 0;
        std::uintptr_t end2 = 0;
        if (ReadAt(manager + kKageInputDeviceVectorBeginOffset, &begin2, &EngineMemoryReadable) &&
            ReadAt(manager + kKageInputDeviceVectorEndOffset, &end2, &EngineMemoryReadable)) {
            g_InputDeviceRawBeginPass2Low.store(static_cast<std::uint32_t>(begin2),
                                                std::memory_order_relaxed);
            g_InputDeviceRawBeginPass2High.store(static_cast<std::uint32_t>(begin2 >> 32u),
                                                 std::memory_order_relaxed);
            g_InputDeviceRawEndPass2Low.store(static_cast<std::uint32_t>(end2),
                                              std::memory_order_relaxed);
            g_InputDeviceRawEndPass2High.store(static_cast<std::uint32_t>(end2 >> 32u),
                                               std::memory_order_relaxed);
            if (begin2 != 0 && end2 > begin2) {
                const std::size_t raw2 = static_cast<std::size_t>(end2 - begin2) /
                                         sizeof(std::uintptr_t);
                const std::uint32_t limit2 = raw2 < 8u ? static_cast<std::uint32_t>(raw2) : 8u;
                g_InputDeviceTablePass2Count.store(limit2, std::memory_order_relaxed);
                for (std::uint32_t index = 0; index < limit2; ++index) {
                    std::uintptr_t candidate = 0;
                    std::uint32_t deviceId = 0;
                    if (!ReadAt(begin2 + index * sizeof(std::uintptr_t), &candidate,
                                &EngineMemoryReadable)) {
                        static_cast<void>(g_InputDeviceTableReadFailures.fetch_add(
                            1, std::memory_order_relaxed));
                        g_InputDeviceTablePass2Pointer[index].store(kProbeReadFailed,
                                                                   std::memory_order_relaxed);
                        g_InputDeviceTablePass2PointerHigh[index].store(kProbeReadFailed,
                                                                       std::memory_order_relaxed);
                        g_InputDeviceTablePass2Id[index].store(kProbeReadFailed,
                                                              std::memory_order_relaxed);
                        continue;
                    }
                    if (candidate != 0 &&
                        !ReadAt(candidate + kKageInputDeviceIdOffset, &deviceId,
                                &EngineMemoryReadable)) {
                        static_cast<void>(g_InputDeviceTableReadFailures.fetch_add(
                            1, std::memory_order_relaxed));
                        deviceId = kProbeReadFailed;
                    }
                    g_InputDeviceTablePass2Pointer[index].store(
                        static_cast<std::uint32_t>(candidate), std::memory_order_relaxed);
                    g_InputDeviceTablePass2PointerHigh[index].store(
                        static_cast<std::uint32_t>(candidate >> 32u), std::memory_order_relaxed);
                    g_InputDeviceTablePass2Id[index].store(deviceId, std::memory_order_relaxed);
                }
            }
        }
    }
    static_cast<void>(g_InputDeviceRawDumpCount.fetch_add(1, std::memory_order_relaxed));
}
#endif  // EXL_DIAGNOSTIC_PROBES

// 诊断探针降频（治"打开配置菜单后游戏画面卡死、只剩音乐"）。
//
// 起因（用户实测）：打开配置菜单后游戏画面卡住不动、只有音乐在放。
// 时间上正好对得上那几组"每帧都采"的重探针 ——
// 配置菜单里模组每帧问输入 ⇒ 我们的刷新就被每帧触发，而一次要读
// 46 次引擎查询 + 几百个内存格子（每次读都带一遍"这段内存可读吗"的检查）⇒ 把主线程拖住。
//
// ⇒ 重探针改成每这么多帧采一次（60 帧 ≈ 1 秒）；读数时等一秒就能采到，判读不受影响。
// 功能路径（边沿判定）完全不依赖这些探针，所以降频不会影响真机手感。
[[maybe_unused]] inline constexpr std::uint32_t kHeavyProbeIntervalFrames = 60;

// ============================================================================
// 每帧"全动作快照"（口径与三条纪律见 `g_InputSnapshotFrame` 的声明处）
// ============================================================================
void RefreshInputSnapshot() noexcept {
#if EXL_DIAGNOSTIC_PROBES
    // 本函数的整段采集动作受探针总开关保护
    //   （口径与"哪些故意不关"的判据见 `runtime/source/probe_gate.hpp`）。
    //
    //   为什么整段关掉：这里每 60 帧要读 ~250 格引擎内存（每格都带一次"这段可读吗"的检查）
    //   + 几十次引擎调用；在加载 / 播片期间它会与主线程撞上。而这些输出**运行时没有任何代码读**
    //   （只有读数工具在宿主侧按符号直读）⇒ 关掉它不改变任何行为。
    //   探针包传 `DIAGNOSTIC_PROBES=1` 原样恢复。
    DumpInputBindings();        // 绑定表只 dump 一次（函数自己判）
    const std::uint32_t frame = CurrentInputFrame();
    if (g_InputSnapshotFrame.load(std::memory_order_relaxed) == frame) {
        return;     // 这一帧已经处理过（每帧最多一次）
    }
    g_InputSnapshotFrame.store(frame, std::memory_order_relaxed);

    // 重探针降频 —— 见 `kHeavyProbeIntervalFrames` 的注释。
    //   下面这几组每帧做的话会把主线程拖住（配置菜单里模组每帧问输入 ⇒ 每帧都触发）。
    if (frame % kHeavyProbeIntervalFrames != 0u) {
        return;
    }
    DumpInputDeviceState();     // 设备内部原始状态
    DumpInputDeviceRaw();       // 设备对象整块原始内存（"读全"版）

    // 只普查"第 1 台手柄"（= 真机上的设备 33）：口径见 `pc_ns_input_device_map.hpp`。
    // 走 Quiet 版 —— 不写"最近一次手柄号翻译"那三个探针。
    const ResolvedInputDevice target = ResolveInputDeviceQuiet(kPcFirstGamepadControllerId);
    if (!target.query) {
        g_InputActionSnapshotPressed.store(0, std::memory_order_relaxed);
        g_InputButtonSnapshotPressed.store(0, std::memory_order_relaxed);
        return;
    }

    // ---- 动作侧：0..31 全部问一遍（越界的引擎自己答 false）-----------------------
    // 这里故意问原始号、不走翻译表 —— 本段回答的是"引擎自己此刻把哪些号答成按住"
    //   （诊断用），与模组口径无关。走的若是翻译表，读数就再也看不出"引擎的 17..20 是菜单四向"
    //   这件事（正是靠它查出"多报 +17"）。模组侧的口径见 `input_action_map.hpp`。
    std::uintptr_t manager = 0;
    std::uintptr_t actionMethod = 0;
    if (ResolveButtonQuery(&manager, &actionMethod, LuaRuntime::InputIsActionPressedThunk()) &&
        actionMethod != 0) {
        const auto actionQuery = engine_call::AsFunction<ActionQueryFn>(actionMethod);
        std::uint32_t pressed = 0;
        for (std::uint32_t action = 0; action < 32u; ++action) {
            if (actionQuery(isaac::runtime::engine_memory::AsObject(manager), action,
                            target.device_id, nullptr)) {
                pressed |= 1u << action;
            }
        }
        g_InputActionSnapshotPressed.store(pressed, std::memory_order_relaxed);

        // 同批把 `GetActionValue` 也采下来 —— 它直接暴露"模拟量数组里哪一格有值"，
        // 用来区分「绑定表错位」与「索引错位」（两者要的修法不同）。
        const std::uintptr_t valueMethod = LuaRuntime::InputGetActionValueThunk();
        if (valueMethod != 0) {
            const auto valueQuery = engine_call::AsFunction<ActionValueFn>(valueMethod);
            for (std::uint32_t action = 0; action < 32u; ++action) {
                const float value = valueQuery(isaac::runtime::engine_memory::AsObject(manager),
                                               action, target.device_id, nullptr);
                std::uint32_t bits = 0;
                std::memcpy(&bits, &value, sizeof(bits));
                g_InputActionSnapshotValue[action].store(bits, std::memory_order_relaxed);
            }
        }
    }

    // ---- 按键侧：0..17（手柄按键号，与 PC 的 `Controller` 枚举逐项相同）---------
    std::uintptr_t buttonMethod = 0;
    if (ResolveButtonQuery(&manager, &buttonMethod, LuaRuntime::InputIsButtonPressedThunk()) &&
        LuaRuntime::ValidateInputIsButtonPressedBinding(buttonMethod)) {
        const auto buttonQuery = engine_call::AsFunction<ButtonBoolFn>(buttonMethod);
        std::uint32_t pressed = 0;
        for (std::uint32_t button = 0; button <= kKageControllerButtonMaximum; ++button) {
            if (buttonQuery(isaac::runtime::engine_memory::AsObject(manager), button,
                            target.device_id, nullptr)) {
                pressed |= 1u << button;
            }
        }
        g_InputButtonSnapshotPressed.store(pressed, std::memory_order_relaxed);
    }
#endif  // EXL_DIAGNOSTIC_PROBES（探针总开关）
}

// ============================================================================
// 帧上采样 —— 边沿改成"引擎帧上的一次事件"
// ============================================================================
//
// 口径与"为什么"见 `runtime/source/input_edge.hpp` 第五节。这里只做机械的采样：
// 每帧由**帧边界钩子**（`ManagedFrameClock` 推进帧号之后、派发回调之前 —— 见
// `callback_dispatcher.hpp` 的 `FrameBoundaryHook`）调一次，把这一帧的边沿按
// (码, 设备) 记进 `g_ButtonEdge` / `g_ActionEdge`；之后 `IsButtonTriggered` /
// `IsActionTriggered` 只是**纯读**（"这一格在本帧是不是边沿"）。
//
// 三条要点：
//   ① **采样集合有界**：按键 0..17 全采、动作 0..31 全采，× 设备表里的手柄 ＋一份"任意设备"
//      聚合 ⇒ 上限 = 32 × 手柄数 次引擎调用/帧（真机 1 台手柄 = **32**）；
//   ② **按键侧一次引擎调用都不用**：设备对象 `+0x30` 就是引擎自己每帧维护的"**本帧按键位图**"
//      （位号 = PC 按键号）⇒ "按住"直接读它；**边沿由本类按帧自己差分**。
//      更正：原先还读 `+0x38`（引擎的"上帧位图"）算 `本帧 & ~上帧`，
//      真机读数证明**局内这两格在采样点恒等**（8042 帧一次边沿都没有；菜单里却正常）
//      ⇒ **局内永远没有边沿 ⇒ MCM 开不出来**。现在第三个实参一律传 `nullptr`
//      （判定见 `SampleInputFrame` 里那段注释与 `input_edge.hpp` 第七节）；
//   ③ **失败绝不抛错**：设备表 / 设备对象 / 引擎绑定任一步读不到 ⇒ 该帧全部答 false，并计数
//      （`g_InputSampleFailures`），读数里看得见。
//
//   再更正上面两条（只加不删）：
//      * ① 的"上限 = 32 × 手柄数"是旧账 —— 现在按键侧也问引擎（`18 × 手柄数`）⇒
//        合计 **50 × 手柄数**（真机 1 台 = 50），由 `g_InputSampleCalls` / `g_InputSampleCodes` 报出；
//      * ② 的"按键侧一次引擎调用都不用"**作废**：真机读数（8523 帧、用户全程在玩）证明设备对象
//        `+0x30` **不是引擎用的按键位图** —— 0..4 与 14 活，5..13 与 15..17（B/X/Y/L/ZL/两摇杆
//        按下/R/ZR/+）**从未答过按住**。⇒ 按键侧改回"对 0..17 逐个问引擎"（与
//        `InputIsButtonPressed` 的回退分支同一枚入口）。**判定语义不变**（第三个实参仍 `nullptr`、
//        `Triggered`/`Pressed` 仍纯读）——见 `input_api.cpp` 采样器里那段与 `input_edge.hpp` 第七节。
//      * `g_InputSampleCalls` 的口径：**动作侧 + 按键侧共用一个 `calls`**，累加的是"这一帧真正
//        递出去的引擎查询次数"（动作侧按映射后非缺件的号、按键侧 18 个号）⇒ 真机单手柄约 42..50，
//        上限 50。`g_InputSampleCodes`（50）是"每台手柄**计划**采多少个号"，两者刻意分开报。
//
//   槽撞车修复（只加不删）：
//      * **病**：边沿表按 `设备号 & 31` 入槽，引擎手柄号 ∈ {1..8, 33} ⇒ **`1` 与 `33` 同槽**；
//        且 `SampleRow` 同帧对同一槽**不幂等**（写边沿后立刻把 `held` 更新 ⇒ 第二次写抹掉边沿）。
//        真机有 2 台手柄⇒ 每帧对槽 1 写两次 ⇒ 边沿全灭 ⇒ MCM 局内开不出来。
//      * **修**：本函数改成**按槽聚合、每槽每帧只写一次** —— 见下面采样器开头那段。
//        ⇒ 上面 ①/②/③ 与 403 的口径**都不变**，`g_InputSampleCalls`/`g_InputSampleCodes` 的口径
//        **也不变**（`calls` 仍按设备累加、`codes` 仍是每台手柄 50）—— 变的只是**写入次数**
//        （由"每设备一次"变成"每槽一次"），而这两个计数本来就不数写入。

// 采样失败时：把"设备表里可能出现的槽"都写成"本帧没有边沿 / 没按住"，让纯读一律答 false。
// （槽号 = 设备号 & 31；真机设备号 0 与 33 ⇒ 槽 0 与 1；聚合 `0xFFFFFFFF` ⇒ 槽 31。）
void MarkSampleRowsEmpty(std::uint32_t frame) noexcept {
    bool zeros[kSampleActionCodeCount] = {};
    for (std::uint32_t slot = 0; slot <= kNsInputDeviceCapacity; ++slot) {
        g_ButtonEdge.SampleRow(slot, frame, zeros, nullptr);
        g_ActionEdge.SampleRow(slot, frame, zeros, nullptr);
    }
    g_ButtonEdge.SampleRow(kNsAnyInputDevice, frame, zeros, nullptr);
    g_ActionEdge.SampleRow(kNsAnyInputDevice, frame, zeros, nullptr);
}

// 每帧一次的帧上采样（帧边界钩子调用，口径见上面那段）。
void SampleInputFrame(std::uint32_t frame) noexcept {
    g_InputSampleFrame.store(frame, std::memory_order_relaxed);
    g_InputSampleCalls.store(0, std::memory_order_relaxed);
    g_InputSampleCodes.store(0, std::memory_order_relaxed);
    g_InputSampleDevices.store(0, std::memory_order_relaxed);

    // 设备表：复用"每帧只读一次"的缓存（本帧第一次读；之后模组的查询走同一份）。
    if (g_InputDeviceTableFrame != frame) {
        g_InputDeviceTableFrame = frame;
        g_InputDeviceTableKnown = ReadNsInputDeviceTable(&g_InputDeviceTableSnapshot);
    }
    if (!g_InputDeviceTableKnown) {
        MarkSampleRowsEmpty(frame);
        g_InputSampleFailures.fetch_add(1, std::memory_order_relaxed);
        return;
    }

    std::uintptr_t manager = 0;
    const bool managerOk = ReadKageInputManager(&manager);
    const std::uintptr_t actionThunk = LuaRuntime::InputIsActionPressedThunk();
    const auto actionQuery = (managerOk && actionThunk != 0)
                                 ? engine_call::AsFunction<ActionQueryFn>(actionThunk)
                                 : nullptr;

    // ---- 按键侧：引擎"按按键号问"的那枚入口（换源）---------------------
    // 取法与 `InputIsButtonPressed` 的回退分支**完全相同**（同一套三件：`…Thunk()` +
    // `ResolveButtonQuery(&manager, &method, …)` + `ValidateInputIsButtonPressedBinding(method)`）。
    // `ResolveButtonQuery` 内部自己读一次 `KAGE::Input::g_Manager`（与上面那条动作侧同源）。
    // 解析不到（没有引擎映像 / 绑定没发布 / 指纹不符）⇒ `buttonQuery == nullptr`，
    // 该帧按键侧全答 false 并计失败（`g_InputSampleFailures`）——**绝不抛错**（本模块 `-fno-exceptions`）。
    std::uintptr_t buttonManager = 0;
    std::uintptr_t buttonMethod = 0;
    const bool buttonOk =
        ResolveButtonQuery(&buttonManager, &buttonMethod, LuaRuntime::InputIsButtonPressedThunk()) &&
        LuaRuntime::ValidateInputIsButtonPressedBinding(buttonMethod);
    const auto buttonQuery =
        buttonOk ? engine_call::AsFunction<ButtonBoolFn>(buttonMethod) : nullptr;

    std::uint32_t calls = 0;
    std::uint32_t devices = 0;
    // 聚合（"任意设备"）的缓冲：各手柄的 OR。
    bool aggButtonPressed[kSampleActionCodeCount] = {};
    bool aggActionPressed[kSampleActionCodeCount] = {};

    // 按槽（`deviceId & 31`）聚合、每槽每帧只写一次。
    //
    // **病灶**：边沿表按 `设备号 & 31` 入槽，而引擎手柄号 ∈ {1..8, 33}（`NpadId + 1`，候选表
    // `{0..7,32}`）⇒ `1` 与 `33` 相差 32、落进同一个槽 1；真机读数证明设备表里
    // **有 2 台真手柄**（`g_InputSampleCalls = 88 = 2 × 44`）。而 `InputFrameEdges::SampleRow`
    // 在**同一帧对同一槽不幂等**：它写下 `edge = cur && !entry.held` 后立刻 `entry.held = cur`
    // ⇒ 同帧第二次写同一槽时 `!entry.held` 已为假 ⇒ **`entry.edge` 被覆盖成 false，
    // 第一次那条边沿就没了**。⇒ 每次边沿都在写入那一刻被抹掉。
    //   * 这解释了为什么（现问引擎、不经这张槽表）是通的，而 code 8（B 键）能到第 5750 帧、
    //     code 13（右摇杆按下）只到第 350 帧 —— 第二台手柄是在那之后才进表的。
    //   * 它同时解释了中文版 MCM 在**局内、不暂停**时按右摇杆完全没反应（`IsButtonTriggered(13, i)`
    //     永远读不到边沿 ⇒ MCM 开不出来）。
    //
    // **修法**：把本帧所有设备的按键/动作结果先按槽 **OR** 聚合进下面这份缓冲，
    // 循环结束后**对每个槽只调一次 `SampleRow`**（见后面那段"每槽只写一次"的循环）。
    //   * 查询**仍按设备**做（每台手柄 18 次按键 + 动作侧若干次）—— 只是**写入**变成每槽一次；
    //   * 第三个实参**仍是 `nullptr`**：边沿继续由 `InputFrameEdges` 用**它自己上一帧的 `held`**
    //     差分（"一帧一次事件"的口径不变，**不**退回"按调用方询问节奏算差分"）。
    bool slotButtonPressed[LuaRuntime::InputFrameEdges::kSlots][kSampleActionCodeCount] = {};
    bool slotActionPressed[LuaRuntime::InputFrameEdges::kSlots][kSampleActionCodeCount] = {};
    // 本帧有没有设备落进这个槽（没落进去的槽不写 —— 与"设备表里有什么就采什么"一致）。
    bool slotPresent[LuaRuntime::InputFrameEdges::kSlots] = {};

    for (std::size_t index = 0; index < g_InputDeviceTableSnapshot.count; ++index) {
        const std::uint32_t deviceId = g_InputDeviceTableSnapshot.ids[index];
        const std::uintptr_t device = g_InputDeviceTableSnapshot.pointers[index];
        // 触摸屏没有按键/动作（判据见 `pc_ns_input_device_map.hpp`）；指针读不到就跳过。
        if (IsNsTouchscreenEntry(index, deviceId) || device == 0) {
            continue;
        }
        // 入槽号（与查询侧 `EntryAt` 的取槽方式一致）—— 撞车的多台设备共用这一个槽。
        const std::uint32_t slot = deviceId & LuaRuntime::InputFrameEdges::kIndexMask;
        slotPresent[slot] = true;

        // ---- 按键侧：对这台设备把按键号 0..17 逐个问引擎（换源）--------
        // 为什么换源：读设备对象 `+0x30`（"本帧位图"）
        //   拆位，真机读数证明**那一格不是引擎用的按键位图** —— 一个 8523 帧、用户全程在玩
        //   （开枪、移动）的会话里，按键 5..13 与 15..17（B/X/Y/L/ZL/两摇杆按下/R/ZR/+ 都在
        //   这一带）**从未答过按住**、`g_InputButtonEdgeCounts` 一次都没加过；而引擎自己对
        //   code 13（右摇杆按下，MCM 的开菜单键）是能答 true 的（= 查询时现问引擎，
        //   真机读到 `g_InputButtonEdgeCounts[13] = 3`、用户实测 MCM 能开）。
        //   ⇒ 改回"**问引擎**"（与 `InputIsButtonPressed` 回退分支同一枚入口）。
        //   判定语义一个字都没改：`SampleRow` 第三个实参仍是 `nullptr` ⇒ 边沿仍由
        //   `InputFrameEdges` 按"它自己上一帧的 `held`"一帧一份地差分（见下面那段注释）。
        bool buttonPressed[kSampleActionCodeCount] = {};
        if (buttonQuery != nullptr) {
            for (std::uint32_t code = 0; code < kSampleButtonCodeCount; ++code) {
                buttonPressed[code] =
                    buttonQuery(isaac::runtime::engine_memory::AsObject(buttonManager), code,
                                deviceId, nullptr);
                ++calls;     // 按键侧从"0 次/帧"变成 `18 × 手柄数`（真机 1 台 = 18）
            }
        } else {
            g_InputSampleFailures.fetch_add(1, std::memory_order_relaxed);
        }
        // 第三个实参传 `nullptr` —— 边沿不再用引擎的 `+0x38`。
        //
        // 原先传 `keysCurrent & ~keysPrevious`（引擎自己那对"本帧/上帧位图"），理由是"一次引擎
        // 调用都不用、天然与 PC 同形"。**真机读数把那条理由推翻了**：局内这两格在采样点**恒等**
        // ⇒ `本帧 & ~上帧` 恒为 0 ⇒ 我们**在局内一次边沿都报不出来**（菜单里却正常）：
        //   * （查询时现问引擎）：局内 `g_InputButtonEdgeCounts` 报过 十字下 3 / B 6 /
        //     左摇杆 7 / **右摇杆 3**，用户实测 **MCM 能开**；
        //   * / pid 166：局内 8042 帧，全数组 0；pid 168：19 次边沿全在进局之前。
        // ⇒ MCM 的开菜单判定**只能在局内跑**（渲染回调被"有房间+有玩家"的闸门挡在局外），
        //   所以它**永远开不出来**（用户原话「我明确告诉你不能打开 mcm，就是存在 bug」）。
        //
        // 传 `nullptr` ⇒ `InputFrameEdges::SampleRow` 走**它自己那条差分**：
        // `edge = pressed && 上一帧采样里的 held` —— `held` 是**我们自己的、一帧一份**的，
        // 与"调用方什么时候来问"无关 ⇒ **"一帧一次事件"的口径不变**（381 治好的
        // "推一下走两格 / 十字键驱动菜单"两张脸不会回来），而数据来源不再依赖那对私有位图。
        //
        // 不在这里写边沿表（同槽的第二台设备会在同帧再写一次、把边沿抹掉，
        // 见本函数开头那段）—— 只把本台设备的结果 OR 进"本槽"缓冲与"任意设备"缓冲，
        // 循环结束后按槽各写一次。
        for (std::uint32_t code = 0; code < kSampleActionCodeCount; ++code) {
            slotButtonPressed[slot][code] = slotButtonPressed[slot][code] || buttonPressed[code];
            aggButtonPressed[code] = aggButtonPressed[code] || buttonPressed[code];
        }

        // ---- 动作侧：每个动作号问一次引擎（`prev` 由 `InputFrameEdges` 自己按帧存）----
        bool actionPressed[kSampleActionCodeCount] = {};
        if (actionQuery != nullptr) {
            for (std::uint32_t code = 0; code < kSampleActionCodeCount; ++code) {
                const std::uint32_t engineAction = TranslateLuaActionToEngineAction(code);
                if (engineAction == kNoEngineAction) {
                    continue;   // Switch 引擎里没有这个动作 ⇒ 恒"没按住"
                }
                actionPressed[code] = actionQuery(isaac::runtime::engine_memory::AsObject(manager),
                                                  engineAction, deviceId, nullptr);
                ++calls;
            }
        } else {
            g_InputSampleFailures.fetch_add(1, std::memory_order_relaxed);
        }
        // Restart has no native action-table row: compose it from the same raw
        // sample as the button queries, before folding physical devices together.
        actionPressed[kLuaRestartAction] = NativeRestartChordHeld(buttonPressed);
        // 动作侧同理 —— 不在这里写边沿表，只 OR 进"本槽"与"任意设备"缓冲。
        for (std::uint32_t code = 0; code < kSampleActionCodeCount; ++code) {
            slotActionPressed[slot][code] = slotActionPressed[slot][code] || actionPressed[code];
            aggActionPressed[code] = aggActionPressed[code] || actionPressed[code];
        }
        ++devices;
    }

    // 每槽只写一次。撞车的多台设备（如引擎手柄号 `1` 与 `33` ⇒ 同槽 1）
    // 已经在上面的循环里 OR 进同一份缓冲；这里对每个"本帧有设备落进"的槽调一次 `SampleRow`。
    // `slotDeviceId` 取**槽号本身**（0..31）—— 因为查询侧 `EntryAt` 也是 `controller & 31` 取槽，
    // `slot & 31 == slot`，用槽号最直白、也避免再引入一个可能与真设备号混淆的值。
    // 第三个实参仍 `nullptr`：边沿继续由 `InputFrameEdges` 按它自己上一帧的 `held` 差分。
    for (std::uint32_t slot = 0; slot < LuaRuntime::InputFrameEdges::kSlots; ++slot) {
        if (!slotPresent[slot]) {
            continue;
        }
        // 引用本槽聚合后的缓冲（撞进同一槽的多台设备已在上面 OR 进来）。
        const bool* buttonPressed = slotButtonPressed[slot];
        const bool* actionPressed = slotActionPressed[slot];
        g_ButtonEdge.SampleRow(slot, frame, buttonPressed, nullptr);
        g_ActionEdge.SampleRow(slot, frame, actionPressed, nullptr);
    }

    // "任意设备"聚合槽（`0xFFFFFFFF & 31 = 31`）：模组问 `0xFFFFFFFF` 时读它。
    // 边沿同样由本类按帧自己差分（第三个实参 `nullptr`，理由见上面按键侧那段）。
    g_ButtonEdge.SampleRow(kNsAnyInputDevice, frame, aggButtonPressed, nullptr);
    // The native restart gate queries each component with "any device", so
    // its global action may span controllers. Per-device actions stay separate.
    aggActionPressed[kLuaRestartAction] = NativeRestartChordHeld(aggButtonPressed);
    g_ActionEdge.SampleRow(kNsAnyInputDevice, frame, aggActionPressed, nullptr);

    g_InputSampleCalls.store(calls, std::memory_order_relaxed);
    g_InputSampleCodes.store(kSampleButtonCodeCount + kSampleActionCodeCount,
                             std::memory_order_relaxed);
    g_InputSampleDevices.store(devices + 1u, std::memory_order_relaxed);
}

// Called once after a native cycle actually polled input, before managed callbacks.
void FrameBoundaryHookEntry(std::uint64_t frame) noexcept {
    SampleInputFrame(static_cast<std::uint32_t>(frame));
}

} // namespace

// 会话级重置（`ResetSessionState()` 调用）。
//
// ⚠️ 必须定义在**匿名命名空间之外**：它要给 `isaac_api.cpp`（另一个 TU）链接。
// 本批第一版把它放进了匿名命名空间（内部链接）⇒ 只编译 API 层子集的宿主 harness 集体链接失败，
// 而只编译 `input_api.cpp` 的那些 harness 报 `-Werror=unused-function`（那正是"内部链接、没人用"
// 的信号）。**106 批也踩过同一个坑**（见 `lua_runtime.cpp` 里那段注释）。
void ResetInputEdgeState() noexcept {
    g_ActionEdge.Reset();
    // 按键号的边沿表也是"每会话"口径（理由同上：不清的话新一次加载会读到上一次的残留）。
    g_ButtonEdge.Reset();
    // 装"帧边界钩子" —— 每帧在"帧号自增之后、派发回调之前"
    //   采一次输入（口径见 `runtime/source/input_edge.hpp` 第五节）。幂等；每次新会话装一次只是保险。
    //   `FrameBoundaryHookEntry` 是上面匿名命名空间里的内部链接函数 —— 同一 TU 内取地址并对接
    //     给 `isaac::runtime` 的函数指针，合法（不给别的 TU 用这个名字）。
    isaac::runtime::SetFrameBoundaryHook(&FrameBoundaryHookEntry);
}

std::size_t AttachInputMethods(lua_State* state) noexcept {
    return AttachOwnerMethods(state, kInputOwner, kInputHandlers,
                              sizeof(kInputHandlers) / sizeof(kInputHandlers[0]));
}

} // namespace isaac::runtime
