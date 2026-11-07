#pragma once

// 控制台适配器：长按A+B打开原生面板，A/触屏打开系统输入法。
// SessionFrameUpdate由Manager::Update前调用；SessionRenderOverlay保留旧函数名，
// 现在从Game::Render返回后调用，保持原生画布并覆盖模组与暂停纸。
// 键盘回调只搬数据，命令与原生UI更新一律留在游戏线程。

#include "domain/console/console_text.hpp"
#include "infrastructure/call/engine_call_access.hpp"
#include "infrastructure/console/console_bridge.hpp"
#include "infrastructure/console/console_panel.hpp"
#include "interfaces/lua/touch_pointer.hpp"
#include "infrastructure/memory/engine_field_access.hpp"
#include "lua_runtime_state.hpp"
#include "raw_engine_input.hpp"
#include "runtime_constants.hpp"

#include <cstdint>

namespace isaac::runtime::console {

// 引擎的动作查询跳板（`Manager::IsActionPressed` 那一族的跳板会自己装 Manager 单例，
// 所以第一个参数与最后一个 `Entity*` 都传 `nullptr`）。与模组菜单同一个调用形状。
using ActionQueryFn = bool (*)(void*, std::uint32_t, std::uint32_t, void*);
// `Font::DrawStringScaledUTF8(Font*, text, x, y, xScale, yScale, Color const*, boxWidth, center)`。
using DrawTextFn = void (*)(void*, const char*, float, float, float, float, const void*, int, bool);
using FontLineHeightFn = std::uint16_t (*)(const void*);
// `Font::GetStringWidthUTF8(Font*, text)` —— 量一行 ASCII 的宽度（未缩放像素）。
// 与 `lua_runtime_state.hpp` 里那个 Lua 侧同名的 typedef 是同一个函数、同一套签名。
using StringWidthFn = int (*)(const void*, const char*);

// 引擎自己的菜单代码就是这么问按键的（"任意手柄"，见 `mod_menu_native.cpp` 里那三条依据）。
inline constexpr std::uint32_t kAnyController = 0xFFFFFFFFU;
// 按键诊断扫描的动作号范围（`ButtonAction` 的号都小于 28）。
inline constexpr std::uint32_t kActionScanLimit = 32;
// 呼出需要连续按住多少帧（约 0.8 秒 @60fps）。
// 为什么不是"按住的上升沿"：A/B 在局内是射击面键，连打时两键会在同一帧内同时按下
// （真机实测会误触弹出软键盘）；"持续按住 0.8 秒"是更强的事件，连打时凑不出来。
inline constexpr std::uint32_t kConsoleTriggerHoldFrames = 48;
// 输出在屏幕上保留多少帧（约 3 秒 @60fps）。
// （用户要求）：原来是 8 秒，太长 ⇒ 改成 3 秒。
inline constexpr std::uint32_t kOverlayHoldFrames = 60U * 3U;
// 覆盖层的画法（纯 ASCII 字体，所以只画英文；中文要用模组那套带字形核对的字体层）。
// （用户要求）：字体调小（1.35 → 0.75，够看清就行）、整块贴右上角。
// 右对齐怎么算：用引擎自己的 `Font::GetStringWidthUTF8` 量出每行宽度（未缩放的像素），
// 取最宽的一行算统一的左端 x = 屏幕宽 − 右边距 − 最宽行 × 缩放。不猜字符宽度。
inline constexpr float kOverlayScale = 0.75F;
// 距屏幕上边的留白（第一行标题的顶端）与距屏幕右边的留白。
inline constexpr float kOverlayTopMargin = 12.0F;
inline constexpr float kOverlayRightMargin = 14.0F;
// 量不出宽度时的退化位置（退回左上角）与屏幕宽读不到时的兜底宽度 ——
// 这两种情况都很少见，但宁可位置不理想，也不能把字挤到屏幕外（右对齐算错就会那样）。
inline constexpr float kOverlayFallbackLeftX = 12.0F;
inline constexpr float kOverlayFallbackScreenWidth = 1280.0F;
inline constexpr float kOverlayStepFallback = 12.0F;  // 行距兜底（取不到 lineHeight 时用）
inline constexpr float kOverlayColor[4] = {0.93F, 0.97F, 0.87F, 1.0F};
inline constexpr char kOverlayTitle[] = "CONSOLE  (hold A+B)";

// `IsaacRepentance::WIDTH`（屏幕宽，float）。槽里放的是指向 float 的指针 ⇒ 槽 → 指针 → float。
// 读不到或数值不合理（≤1 / >8192 ⇒ 溢出成垃圾）就回兜底宽度：右对齐只用它算 x，不值得因此不画。
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

// 原生界面的入口缓存：关闭时没有解析、触屏或绘制工作。
inline PanelNativeEntries& SessionPanelEntries() noexcept { static PanelNativeEntries entries{}; return entries; }
inline void SessionFrameUpdate() noexcept {
    State().armed=1;++State().frames;
    ConsoleSwitchTick();
    const auto base=LuaRuntime::EngineModuleBase();
    if (!base) return;
    static EngineEntries entries{};
    static ActionQueryFn query{};
    static ActionQueryFn buttonQuery{};
    static std::uintptr_t kage{};
    static std::uintptr_t resolvedBase{};
    static bool resolved{};
    if (resolvedBase!=base) {
        resolvedBase=base;
        kage=KageSystemManager(base);
        resolved=ResolveConsoleEntries(base,kGameModuleRangeCheckSize,&entries) &&
                 ResolvePanelEntries(base,kGameModuleRangeCheckSize,&SessionPanelEntries());
        // 复用已验证发布的绑定：Manager入口已由我们挂钩，旧原字节守卫会误拒绝。
        // 后面的批量扫描已有RawEngineInputQueryScope，不再为每个动作叠加一层壳。
        query=engine_call::AsFunction<ActionQueryFn>(LuaRuntime::InputIsActionPressedBinding());
        buttonQuery=engine_call::ResolveFunction<ActionQueryFn>(base,kGameModuleRangeCheckSize,
            kKageIsButtonPressedOffset,kKageIsButtonPressedExpectedBytes,&engine_memory::EngineMemoryReadable);
        if (!engine_call::VerifyEntryBytes(base+kKageIsButtonPressedOffset+kKageInputButtonDiscriminatorOffset,
            kKageIsButtonPressedDiscriminator.data(),kKageIsButtonPressedDiscriminator.size(),
            &engine_memory::EngineMemoryReadable)) buttonQuery=nullptr;
    }
    if (!resolved) return;
    // 首次帧点早于绑定发布时允许恢复，不能永久缓存nullptr。
    if (!query) query=engine_call::AsFunction<ActionQueryFn>(LuaRuntime::InputIsActionPressedBinding());
    if (!query) return;
    if (!ConsoleSwitchEnabled()) {
        PanelFrame(entries,SessionPanelEntries(),base,0,0,{},0,0,false);
        return;
    }
    std::uint32_t mask{};
    {
        const LuaRuntime::RawEngineInputQueryScope rawInput;
        for (std::uint32_t action=0;action < kActionScanLimit;++action)
            if (query(nullptr,action,kAnyController,nullptr)) mask|=1U<<action;
    }
    State().actionsSeen|=mask;
    bool combo=false;
    if (buttonQuery) {
        const auto manager=LoadPointerField(base,kKageInputManagerSlotOffset);
        const auto controls=Storage().controls;
        if (manager && isaac::runtime::ValidConsoleControls(controls)) {
            combo=buttonQuery(engine_memory::AsObject(manager),controls.first,kAnyController,nullptr);
            if (combo && controls.second!=isaac::runtime::kConsoleNoSecondButton && controls.second!=controls.first)
                combo=buttonQuery(engine_memory::AsObject(manager),controls.second,kAnyController,nullptr);
        }
    }
    const bool blocked=combo && LuaRuntime::ConsoleConfigMenuVisible();
    const auto risen=mask&~Panel().previousMask;
    if (risen) for (std::uint32_t action=kActionScanLimit;action-- >0;)
        if (risen&(1U<<action)) {State().lastAction=action;break;}
    PanelTouch touch{};
    if (NativePanelState()!=0 || ConsoleCapturesInput()) {
        const auto raw=ReadTouchPointer();touch={raw.pressed,raw.rawX,raw.rawY};
    }
    float width{},height{};
    // 尺寸只为新触点的命中检测读取；关闭态/手柄操作不新增每帧内存查询。
    if (touch.pressed && !Panel().touchHeld) {
        width=ScreenWidth(base);
        const auto heightSlot=LoadPointerField(base,0xAAC658);
        if (heightSlot) static_cast<void>(engine_memory::ReadAt(heightSlot,&height,&engine_memory::EngineMemoryReadable));
    }
    if (!kage && NativePanelState()!=0) kage=KageSystemManager(base);
    PanelFrame(entries,SessionPanelEntries(),base,kage,mask,touch,width,height,combo,blocked);
}

// 只从Game::Render返回处调用，保持游戏逻辑画布与上下文；不在最终Present外侧画。
inline void SessionRenderOverlay() noexcept { RenderPanel(SessionPanelEntries()); }

} // namespace isaac::runtime::console
