#pragma once

#include "infrastructure/console/console_bridge.hpp"
#include "infrastructure/console/console_panel_guards.hpp"

namespace isaac::runtime::console {
struct PanelTouch { bool pressed{}; std::uint32_t rawX{}, rawY{}; };
struct PanelNativeEntries {
    void (*show)(void*){};
    void (*hide)(void*){};
    bool (*update)(void*){};
    void (*render)(void*){};
    void (*inputLines)(void*){};
    void* (*assign)(void*,const char*){};
    void (*print)(void*,const void*,std::uint32_t,std::uint32_t){};
    void (*addHistory)(void*,const void*){};
    bool Ready() const noexcept {
        return show && hide && update && render && inputLines && assign && print && addHistory;
    }
};
inline bool ResolvePanelEntries(std::uintptr_t base, std::size_t size, PanelNativeEntries* out) noexcept {
    if (!out) return false;
    using namespace native_panel;
#define CONSOLE_PANEL_ENTRY(field, Name) \
    out->field=engine_call::ResolveFunction<decltype(out->field)>(base,size,k##Name##Offset,k##Name##Bytes,&engine_memory::EngineMemoryReadable)
    CONSOLE_PANEL_ENTRY(show,Show);
    CONSOLE_PANEL_ENTRY(hide,Hide);
    CONSOLE_PANEL_ENTRY(update,Update);
    CONSOLE_PANEL_ENTRY(render,Render);
    CONSOLE_PANEL_ENTRY(inputLines,InputLines);
    CONSOLE_PANEL_ENTRY(assign,Assign);
    CONSOLE_PANEL_ENTRY(print,Print);
    CONSOLE_PANEL_ENTRY(addHistory,AddHistory);
#undef CONSOLE_PANEL_ENTRY
    return out->Ready();
}
inline std::uint32_t NativePanelState() noexcept {
    std::uint32_t value{};
    if (Storage().objectReady) std::memcpy(&value,Storage().consoleObject,sizeof(value));
    return value;
}
inline void PanelKeyboardChanged(const std::uint32_t* text,void*) noexcept {
    if (!Panel().keyboardOpen || text==nullptr) return;
    auto& p=Panel();
    std::size_t i=0;
    for (;i+1<kPanelTextCapacity && text[i]!=0;++i) p.draft[i]=text[i];
    p.draft[i]=0;
    p.draftChanged=true;
}
inline void SetPanelInput(const PanelNativeEntries& ui,const char* text) noexcept {
    auto& c=Storage();
    ui.assign(c.consoleObject+0x20,text);
    const auto* header=c.consoleObject+0x20;
    const char* cursor=EngineStringData(header)+EngineStringSize(header);
    std::memcpy(c.consoleObject+0x158,&cursor,sizeof(cursor));
    ui.inputLines(c.consoleObject);
}
inline void PrintPanel(const PanelNativeEntries& ui,const char* text,std::size_t length,
                       std::uint32_t color=0xFFD3D3D3U) noexcept {
    if (!text || !length) return;
    alignas(8) unsigned char borrowed[kEngineStringBytes]{};
    if (!BuildBorrowedCommandString(text,length,borrowed)) return;
    // RunCommand的输出重定向只属于那次调用；显示历史必须送往原生deque。
    auto& c=Storage();
    std::uintptr_t output{};
    std::memcpy(&output,c.consoleObject+0x150,sizeof(output));
    std::memset(c.consoleObject+0x150,0,sizeof(output));
    ui.print(c.consoleObject,borrowed,color,0);
    std::memcpy(c.consoleObject+0x150,&output,sizeof(output));
}
// ConsoleOutput与界面共用同一份原生历史；加载期没有模块基址时保留调用方原日志通道。
inline bool AppendConsoleHistory(std::uintptr_t base,const char* text,std::size_t length) noexcept {
    if (!base || !text || !length) return false;
    static std::uintptr_t cachedBase{};
    static EngineEntries engine{};
    static PanelNativeEntries ui{};
    static bool ready{};
    if (cachedBase!=base) {
        cachedBase=base;
        ready=ResolveConsoleEntries(base,kGameModuleRangeCheckSize,&engine) &&
              ResolvePanelEntries(base,kGameModuleRangeCheckSize,&ui);
    }
    if (!ready || !EnsureConsoleObject(engine)) return false;
    PrintPanel(ui,text,length);
    return ObjectFenceIntact(Storage());
}
inline void ClosePanelImmediately(const PanelNativeEntries& ui) noexcept {
    auto& p=Panel();
    if (NativePanelState()!=0 && ui.Ready() && ObjectFenceIntact(Storage())) {
        // Hide不接受刚Show的state1；先推进一次，恢复Manager自己的输入标志。
        if (NativePanelState()==1) static_cast<void>(ui.update(Storage().consoleObject));
        ui.hide(Storage().consoleObject);
        std::uint32_t closed=0;
        std::memcpy(Storage().consoleObject,&closed,sizeof(closed));
        ++p.closed;
    }
    std::uint32_t state=0;
    std::memcpy(Storage().consoleObject,&state,sizeof(state));
    p.game=0;
    p.completedLength=0;
    p.waitRelease=true;
    Storage().pendingReady=false;
    g_ConsolePaused.store(false,std::memory_order_relaxed);
    g_ConsoleInputCaptured.store(true,std::memory_order_relaxed);
}
inline bool PanelInputHit(PanelTouch touch,float width,float height) noexcept {
    if (!touch.pressed || touch.rawX>=1280 || touch.rawY>=720 ||
        !(width>20 && width<=8192 && height>20 && height<=8192)) return false;
    float bottom=height-1;
    float nativeBottom{};
    std::memcpy(&nativeBottom,Storage().consoleObject+0x10,sizeof(nativeBottom));
    if (nativeBottom>0 && nativeBottom<height) bottom=nativeBottom;
    const float x=static_cast<float>(touch.rawX)*width/1280.0F;
    const float y=static_cast<float>(touch.rawY)*height/720.0F;
    std::uintptr_t begin{},end{};
    std::memcpy(&begin,Storage().consoleObject+0x38,sizeof(begin));
    std::memcpy(&end,Storage().consoleObject+0x40,sizeof(end));
    const auto breaks=end>=begin?(end-begin)/2:0;
    if (breaks>=kPanelTextCapacity) return false;
    // 原生Render先预留6-breaks条补全行，再逆序画输入的breaks条换行与首行。
    // 热区必须跟随实际输入文字，不能把面板底线当成输入框。
    const auto inputRows=breaks>6?breaks:6;
    const auto completionRows=breaks<6?6-breaks:0;
    const float top=bottom-18-static_cast<float>(inputRows)*15;
    const float last=bottom-18-static_cast<float>(completionRows)*15;
    return x>=10 && x<=width-10 && y>=top && y<=last+15;
}

// 唯一的会话状态机。系统键盘回调只搬数据；全部原生UI/命令调用都在此游戏线程执行。
inline void PanelFrame(const EngineEntries& entries,const PanelNativeEntries& ui,
                       std::uintptr_t base,std::uintptr_t kage,std::uint32_t mask,
                       PanelTouch touch,float width,float height,bool combo,bool triggerBlocked=false) noexcept {
    auto& p=Panel(); auto& core=Storage();
    if (State().fenceBroken!=0 || (core.objectReady && !ObjectFenceIntact(core))) {
        State().fenceBroken=1;
        ClosePanelImmediately(ui);
        return;
    }
    const auto risen=mask&~p.previousMask;
    p.previousMask=mask;
    const bool touchRise=touch.pressed&&!p.touchHeld;
    p.touchHeld=touch.pressed;
    // 没打开且无操作时不读Game/玩家、不做svc查询；保持原有关闭态帧开销。
    if (triggerBlocked) {core.comboHeldFrames=0;core.comboFired=true;}
    if (NativePanelState()==0 && !p.keyboardOpen && !core.pendingReady &&
        (!combo || triggerBlocked)) {
        core.comboHeldFrames=0;core.comboFired=triggerBlocked;State().triggerHeld=0;
        if (!mask && !touch.pressed) p.waitRelease=false;
        g_ConsolePaused.store(0,std::memory_order_relaxed);
        g_ConsoleInputCaptured.store(p.waitRelease,std::memory_order_relaxed);
        return;
    }
    const auto game=ResolveGame(base);
    const bool available=p.hooksReady && ui.Ready() && ConsoleSwitchEnabled() &&
                         HasUsableFirstPlayer(game) && State().fenceBroken==0;
    if (!available || (p.game!=0 && (p.game!=game || p.sessionEpoch!=g_ConsoleSessionEpoch.load(std::memory_order_relaxed)))) {
        if (NativePanelState()!=0) ClosePanelImmediately(ui);
        core.comboHeldFrames=0;core.comboFired=false;core.pendingReady=false;
        if (p.keyboardFinished) {p.keyboardOpen=false;p.keyboardFinished=false;}
        if (mask==0 && !touch.pressed && !p.keyboardOpen) p.waitRelease=false;
        g_ConsoleInputCaptured.store(p.waitRelease||p.keyboardOpen,std::memory_order_relaxed);
        return;
    }
    constexpr std::uint32_t confirm=1U<<14,back=1U<<15;
    const auto holdFrames=core.controls.holdTenths*6U;
    // 单A/B兼任开启键时，短按在松开时交给编辑/返回，长按仍切换控制台。
    const bool singleKey=core.controls.second==isaac::runtime::kConsoleNoSecondButton ||
                         core.controls.first==core.controls.second;
    const bool shortReleased=singleKey && !combo && core.comboHeldFrames!=0 &&
                             core.comboHeldFrames<holdFrames && !core.comboFired;
    const bool shortConfirm=shortReleased && core.controls.first==4;
    const bool shortBack=shortReleased && core.controls.first==5;
    State().triggerHeld=combo?1U:0U;
    bool justOpened=false;
    if (combo && !p.keyboardOpen && !triggerBlocked) {
        if (core.comboHeldFrames<holdFrames) ++core.comboHeldFrames;
        if (!core.comboFired && core.comboHeldFrames>=holdFrames) {
            core.comboFired=true;
            if (NativePanelState()==0 && EnsureConsoleObject(entries)) {
                ui.show(core.consoleObject);
                SetPanelInput(ui,p.draftUtf8);
                p.game=game;p.sessionEpoch=g_ConsoleSessionEpoch.load(std::memory_order_relaxed);p.waitRelease=true;justOpened=true;++p.opened;
            } else if (NativePanelState()!=0) {
                ui.hide(core.consoleObject);p.waitRelease=true;++p.closed;
            }
        }
    } else if (!combo) {core.comboHeldFrames=0;core.comboFired=false;}

    if (p.draftChanged) {
        static_cast<void>(Utf32ToUtf8(p.draft,kPanelTextCapacity,p.draftUtf8,sizeof(p.draftUtf8)));
        SetPanelInput(ui,p.draftUtf8);p.draftChanged=false;
    }
    if (p.keyboardFinished || (core.pendingReady && !p.keyboardOpen)) {
        const bool fromKeyboard=p.keyboardOpen;
        p.keyboardFinished=false;p.keyboardOpen=false;p.waitRelease=true;
        const char* command{};std::uint32_t length{};
        const bool pending=TakePendingCommand(&command,&length);
        if (fromKeyboard) {
            command=p.completedUtf8;
            // 换局/关闭后才交回的旧键盘结果，不得在新会话执行。
            const auto state=NativePanelState();
            length=(state==2 || state==3)?p.completedLength:0;
        }
        if ((fromKeyboard ? length!=0 : pending) && EnsureConsoleObject(entries)) {
            core.log.Append("> ",2);core.log.Append(command,length);core.log.Append("\n",1);
            // 原生AddHistoryEntry按当前输入去重、回显，并在RunCommand前加入命令deque。
            // repeat会跳过deque首项（自身），因此必须在执行之前登记。
            SetPanelInput(ui,command);
            alignas(8) unsigned char history[kEngineStringBytes]{};
            if (BuildBorrowedCommandString(command,length,history)) ui.addHistory(core.consoleObject,history);
            const auto before=EngineStringSize(core.outputString);
            const auto outcome=ExecuteCommand(entries,base,command,length);
            const auto after=EngineStringSize(core.outputString);
            if (outcome.status==ExecStatus::kOk && after>before) {
                const auto* output=EngineStringData(core.outputString);
                if (output && engine_memory::EngineMemoryReadable(engine_memory::AddressOf(output),after))
                    PrintPanel(ui,output+before,after-before);
            } else if (outcome.status!=ExecStatus::kOk) {
                char note[]="[status 00]\n";
                const auto code=static_cast<unsigned>(outcome.status)%100;
                note[8]=static_cast<char>('0'+code/10);note[9]=static_cast<char>('0'+code%10);
                PrintPanel(ui,note,sizeof(note)-1);
            }
            std::memset(p.draft,0,sizeof(p.draft));p.draftUtf8[0]=0;SetPanelInput(ui,"");
        }
    }
    if (p.waitRelease && mask==0 && !touch.pressed && !p.keyboardOpen) p.waitRelease=false;
    if ((NativePanelState()==2 || NativePanelState()==3) && !justOpened && !p.keyboardOpen && !p.waitRelease && !combo) {
        if ((risen&back)!=0 || shortBack) {ui.hide(core.consoleObject);p.waitRelease=true;++p.closed;}
        else if ((risen&confirm)!=0 || shortConfirm || (touchRise&&PanelInputHit(touch,width,height))) {
            p.keyboardFinished=false;p.keyboardOpen=true;
            if (!RequestKeyboard(entries,kage,&PanelKeyboardChanged,p.draft)) p.keyboardOpen=false;
        }
    }
    if (NativePanelState()!=0) static_cast<void>(ui.update(core.consoleObject));
    const bool paused=NativePanelState()!=0 || p.keyboardOpen;
    g_ConsolePaused.store(paused,std::memory_order_relaxed);
    g_ConsoleInputCaptured.store(paused||p.waitRelease,std::memory_order_relaxed);
    if (!paused) p.game=0;
    if (core.objectReady && !ObjectFenceIntact(core)) {
        State().fenceBroken=1;ClosePanelImmediately(ui);
    }
}
inline void RenderPanel(const PanelNativeEntries& ui) noexcept {
    if (!Panel().hooksReady || !ui.Ready() || NativePanelState()==0 || !ObjectFenceIntact(Storage())) return;
    ui.render(Storage().consoleObject);
    ++Panel().rendered;
}
} // namespace isaac::runtime::console
