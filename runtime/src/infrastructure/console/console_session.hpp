#pragma once

// 控制台的**每帧点**：按键 → 弹系统软键盘 → 执行命令 → 自己画输出。
//
// ★ 为什么放在 `infrastructure/` 而不是 `application/`：它**直接调引擎入口**（动作查询、字体绘制）
//   并依赖 `lua_runtime_state.hpp`，而门禁 `test_hook_callback_pipeline` 钉死"应用/领域/端口层
//   不得依赖平台或实现头文件"。它在这一层的身份是**适配器**（把"每帧点"接到引擎上）；
//   纯逻辑（文本转换、行缓冲）在 `domain/console/`，那一层不碰任何引擎头。
//
// 两个入口分别由**中枢里那一行**调用（不是把业务塞进中枢，见 `docs/加一个功能模块的做法.md`）：
//   * `SessionFrameUpdate()`  ← `hook_manager.cpp` 的 `ManagerUpdateHook::Callback`（游戏主线程、
//     跑 `Manager::Update` 之前）—— 与模组菜单那个"每帧点"同一个位置口径；
//   * `SessionRenderOverlay()` ← `hook_manager.cpp` 的 `DispatchModPostRender()`（模组的
//     `MC_POST_RENDER` 绘制点，真机已知可用；EID 就在这一档里画字）。
//
// ## 为什么命令不在软键盘回调里执行
//
// 引擎是在它自己的 applet 处理里回调我们（`KeyboardFinishedCallback`）。那个位置上跑一条
// 完整命令（可能生成实体、切关卡）**没有依据**；所以回调只搬数据，命令由**下一帧**这个
// 每帧点执行 —— 与项目纪律"要动手就在游戏线程的每帧点做"一致。

#include "domain/console/console_text.hpp"
#include "infrastructure/call/engine_call_access.hpp"
#include "infrastructure/console/console_bridge.hpp"
#include "infrastructure/memory/engine_field_access.hpp"
#include "lua_runtime_state.hpp"
#include "runtime_constants.hpp"

#include <cstdint>

namespace isaac::runtime::console {

//: 引擎的动作查询跳板（`Manager::IsActionPressed` 那一族的跳板会**自己装 Manager 单例**，
//: 所以第一个参数与最后一个 `Entity*` 都传 `nullptr`）。与模组菜单同一个调用形状。
using ActionQueryFn = bool (*)(void*, std::uint32_t, std::uint32_t, void*);
//: `Font::DrawStringScaledUTF8(Font*, text, x, y, xScale, yScale, Color const*, boxWidth, center)`。
using DrawTextFn = void (*)(void*, const char*, float, float, float, float, const void*, int, bool);
using FontLineHeightFn = std::uint16_t (*)(const void*);
//: `Font::GetStringWidthUTF8(Font*, text)` —— 量一行 ASCII 的宽度（**未缩放**像素）。
//: 与 `lua_runtime_state.hpp` 里那个 Lua 侧同名的 typedef 是同一个函数、同一套签名。
using StringWidthFn = int (*)(const void*, const char*);

//: 引擎自己的菜单代码就是这么问按键的（"任意手柄"，见 `mod_menu_native.cpp` 里那三条依据）。
inline constexpr std::uint32_t kAnyController = 0xFFFFFFFFU;
//: 按键诊断扫描的动作号范围（`ButtonAction` 的号都小于 28）。
inline constexpr std::uint32_t kActionScanLimit = 32;
//: 呼出需要**连续按住**多少帧（约 0.8 秒 @60fps）。
//: 为什么不是"按住的上升沿"：A/B 在局内是射击面键，连打时两键会在同一帧内同时按下
//: （真机实测会误触弹出软键盘）；"持续按住 0.8 秒"是更强的事件，连打时凑不出来。
inline constexpr std::uint32_t kConsoleTriggerHoldFrames = 48;
//: 输出在屏幕上保留多少帧（约 3 秒 @60fps）。
//: ★ 批次 123（用户要求）：原来是 8 秒，太长 ⇒ 改成 3 秒。
inline constexpr std::uint32_t kOverlayHoldFrames = 60U * 3U;
//: 覆盖层的画法（**纯 ASCII 字体**，所以只画英文；中文要用模组那套带字形核对的字体层）。
//: ★ 批次 123（用户要求）：字体调小（1.35 → 0.75，够看清就行）、整块**贴右上角**。
//: 右对齐怎么算：用引擎自己的 `Font::GetStringWidthUTF8` 量出每行宽度（**未缩放**的像素），
//: 取最宽的一行算统一的左端 x = 屏幕宽 − 右边距 − 最宽行 × 缩放。**不猜字符宽度**。
inline constexpr float kOverlayScale = 0.75F;
//: 距屏幕上边的留白（第一行标题的顶端）与距屏幕右边的留白。
inline constexpr float kOverlayTopMargin = 12.0F;
inline constexpr float kOverlayRightMargin = 14.0F;
//: 量不出宽度时的**退化位置**（退回左上角）与屏幕宽读不到时的兜底宽度 ——
//: 这两种情况都很少见，但宁可位置不理想，也不能把字挤到屏幕外（右对齐算错就会那样）。
inline constexpr float kOverlayFallbackLeftX = 12.0F;
inline constexpr float kOverlayFallbackScreenWidth = 1280.0F;
inline constexpr float kOverlayStepFallback = 12.0F;  // 行距兜底（取不到 lineHeight 时用）
inline constexpr float kOverlayColor[4] = {0.93F, 0.97F, 0.87F, 1.0F};
inline constexpr char kOverlayTitle[] = "CONSOLE  (hold A+B)";

//: `IsaacRepentance::WIDTH`（屏幕宽，float）。槽里放的是**指向 float 的指针** ⇒ 槽 → 指针 → float。
//: 读不到或数值不合理（≤1 / >8192 ⇒ 溢出成垃圾）就回兜底宽度：右对齐只用它算 x，不值得因此不画。
[[nodiscard]] inline float ScreenWidth(std::uintptr_t base) noexcept {
    const std::uintptr_t slot = LoadPointerField(base, kIsaacScreenWidthSlotOffset);
    float width = 0.0F;
    if (slot == 0 || !engine_memory::ReadAt(slot, &width, &engine_memory::EngineMemoryReadable)) {
        width = 0.0F;
    }
    if (!(width > 1.0F) || width > 8192.0F) {
        return kOverlayFallbackScreenWidth;
    }
    return width;
}

//: 每帧点。**任何前置条件不成立就只是什么都不做**，不报错、不崩。
inline void SessionFrameUpdate() noexcept {
    State().armed = 1;  // 每帧点跑到过 ⇒ 这一套编进来了（读数第 [0] 格的判据）
    State().frames += 1;
    // 总开关的 I/O 待办（开局读一次 / 拨动后写一次）在**每帧点最开头**做掉 ——
    // 不放在拨动那一刻（那一下正在驱动引擎的菜单状态机），与污染标记那条路同一个位置口径。
    ConsoleSwitchTick();
    if (!ConsoleSwitchEnabled()) {
        // 关着 ⇒ 不扫按键、不弹键盘、不执行（PC 的 `EnableDebugConsole=0`：没有控制台）。
        // 顺手复位长按计数与"当前按住"：否则刚打开开关那一帧，之前累积的按住会被当成一次长按。
        State().triggerHeld = 0;
        Core& core = Storage();
        core.comboHeldFrames = 0;
        core.comboFired = false;
        return;
    }
    const std::uintptr_t base = LuaRuntime::EngineModuleBase();
    if (base == 0) {
        return;  // 基址还没发布（安装阶段之后才有），本帧不是异常
    }
    // 入口解析一次并缓存（守卫在 `ResolveConsoleEntries` 里逐条核对过）。
    static EngineEntries entries{};
    static std::uintptr_t resolvedBase = 0;
    static bool resolved = false;
    if (!resolved || resolvedBase != base) {
        resolved = ResolveConsoleEntries(base, kGameModuleRangeCheckSize, &entries);
        resolvedBase = base;
    }
    if (!resolved) {
        return;  // 构造/Init/RunCommand 有缺 ⇒ 不碰键盘、不执行
    }
    static ActionQueryFn query = nullptr;
    static bool queryResolved = false;
    if (!queryResolved) {
        query = engine_call::ResolveFunction<ActionQueryFn>(
            base, kGameModuleRangeCheckSize, kManagerIsActionPressedOffset,
            kManagerIsActionPressedExpectedBytes, &engine_memory::EngineMemoryReadable);
        queryResolved = true;
    }
    if (query == nullptr) {
        return;
    }

    // ---- 按键 ----
    // ① 诊断：把"哪个键 = 哪个动作号"在真机上记下来（只问"任意手柄"这一档，每帧 32 次查询）。
    //    用**上升沿**记"最近按下"，否则按住的键会每帧把上一个值顶掉。
    static std::uint32_t heldMask = 0;
    std::uint32_t mask = 0;
    for (std::uint32_t action = 0; action < kActionScanLimit; ++action) {
        if (query(nullptr, action, kAnyController, nullptr)) {
            mask |= (1U << action);
        }
    }
    const std::uint32_t risen = mask & ~heldMask;
    heldMask = mask;
    State().actionsSeen |= mask;  // 累计位图：读数一次就能拿到整张"按键 ↔ 动作号"映射
    if (risen != 0) {
        for (std::uint32_t action = kActionScanLimit; action-- > 0;) {
            if ((risen & (1U << action)) != 0U) {
                State().lastAction = action;
                break;
            }
        }
    }
    // ② 组合键（同时按住两个动作）⇒ **连续按住约 0.8 秒**才弹一次软键盘（判据见
    //    `kConsoleTriggerHoldFrames`：连打射击时两键会在同一帧里被按下，所以不能只看上升沿）。
    const bool combo = query(nullptr, kConsoleTriggerActionA, kAnyController, nullptr) &&
                       query(nullptr, kConsoleTriggerActionB, kAnyController, nullptr);
    State().triggerHeld = combo ? 1U : 0U;
    Core& core = Storage();
    if (combo) {
        if (core.comboHeldFrames < kConsoleTriggerHoldFrames) {
            core.comboHeldFrames += 1;
        }
        if (!core.comboFired && core.comboHeldFrames >= kConsoleTriggerHoldFrames) {
            core.comboFired = true;  // 一直按着只弹一次；松开才允许下一轮
            if (!core.pendingReady) {
                // 开不成（入口缺 / 拿不到 `KAGE::System::g_Manager`）就什么都不发生 ——
                // 结论已经记在状态面里，这里不额外报错。
                static_cast<void>(RequestKeyboard(entries, KageSystemManager(base)));
            }
        }
    } else {
        core.comboHeldFrames = 0;
        core.comboFired = false;
    }

    // ---- 软键盘交回的命令（本轮执行）----
    const char* command = nullptr;
    std::uint32_t length = 0;
    if (TakePendingCommand(&command, &length)) {
        core.log.Append("> ", 2);
        core.log.Append(command, length);
        core.log.Append("\n", 1);
        const ExecutionOutcome outcome = ExecuteCommand(entries, base, command, length);
        // 被拒（没有玩家 / 命令太长 / …）也把结论写进屏幕，免得用户以为"打了字没反应"。
        // 只写两位数字，不引 `std::string`（那一份分配器与引擎的不是同一套，能不用就不用）。
        if (outcome.status != ExecStatus::kOk) {
            char note[16] = "[status 00]\n";
            const unsigned code = static_cast<unsigned>(outcome.status) % 100U;
            note[8] = static_cast<char>('0' + (code / 10U));
            note[9] = static_cast<char>('0' + (code % 10U));
            core.log.Append(note, sizeof("[status 00]\n") - 1);
        }
        State().overlayFrames = kOverlayHoldFrames;
    }
    if (State().overlayFrames > 0) {
        State().overlayFrames -= 1;
    }
}

//: 画输出。由 `DispatchModPostRender()` 每帧调用一次；**没在显示窗口里就直接返回**
//: （不解析入口、不取字体，避免白花帧预算）。
inline void SessionRenderOverlay() noexcept {
    if (State().overlayFrames == 0) {
        return;
    }
    const std::uintptr_t base = LuaRuntime::EngineModuleBase();
    if (base == 0) {
        return;
    }
    static DrawTextFn draw = nullptr;
    static FontLineHeightFn lineHeight = nullptr;
    static StringWidthFn measure = nullptr;
    static bool renderResolved = false;
    if (!renderResolved) {
        draw = engine_call::ResolveFunction<DrawTextFn>(
            base, kGameModuleRangeCheckSize, kFontDrawStringScaledUTF8Offset,
            kFontDrawStringScaledUTF8ExpectedBytes, &engine_memory::EngineMemoryReadable);
        lineHeight = engine_call::ResolveFunction<FontLineHeightFn>(
            base, kGameModuleRangeCheckSize, kFontGetLineHeightOffset,
            kFontGetLineHeightExpectedBytes, &engine_memory::EngineMemoryReadable);
        measure = engine_call::ResolveFunction<StringWidthFn>(
            base, kGameModuleRangeCheckSize, kFontGetStringWidthUTF8Offset,
            kFontGetStringWidthUTF8ExpectedBytes, &engine_memory::EngineMemoryReadable);
        renderResolved = true;
    }
    if (draw == nullptr) {
        return;
    }
    // 字体对象：`IsaacRepentance::g_Manager` 也是**指针变量**（槽 → 变量 → `Manager*`）。
    const std::uintptr_t managerVariable = LoadPointerField(base, kGameManagerGlobalSlotOffset);
    const std::uintptr_t manager =
        managerVariable != 0 ? LoadPointerField(managerVariable, 0) : 0;
    if (manager == 0) {
        return;
    }
    void* font = engine_memory::AsObject(manager + kIsaacManagerFontObjectOffset);
    float step = kOverlayStepFallback;
    if (lineHeight != nullptr) {
        const float measured = static_cast<float>(lineHeight(font)) * kOverlayScale;
        if (measured > 1.0F && measured < 200.0F) {
            step = measured;
        }
    }
    const Core& core = Storage();
    const std::size_t lines = core.log.LineCount();
    // 右对齐：量出最宽的一行（标题也算在内；**未缩放**宽度 × 缩放 = 实际占宽），
    // 所有行共用同一个左端 x ⇒ 右边缘齐平。
    // ★ 量不出宽度（`measure` 没解析到）就退回左上角：右对齐算错会把整块挤出屏幕右边，
    //   而"位置偏一点"远比"看不见"好。
    float x = kOverlayFallbackLeftX;
    if (measure != nullptr) {
        float widest = static_cast<float>(measure(font, kOverlayTitle)) * kOverlayScale;
        for (std::size_t index = 0; index < lines; ++index) {
            const float width =
                static_cast<float>(measure(font, core.log.Line(index))) * kOverlayScale;
            if (width > widest) {
                widest = width;
            }
        }
        const float right = ScreenWidth(base) - kOverlayRightMargin;
        const float aligned = right - widest;
        x = aligned > kOverlayFallbackLeftX ? aligned : kOverlayFallbackLeftX;
    }
    float y = kOverlayTopMargin;
    draw(font, kOverlayTitle, x, y, kOverlayScale, kOverlayScale, kOverlayColor, 0, false);
    for (std::size_t index = 0; index < lines; ++index) {
        y += step;
        draw(font, core.log.Line(index), x, y, kOverlayScale, kOverlayScale, kOverlayColor, 0,
             false);
    }
}

}  // namespace isaac::runtime::console