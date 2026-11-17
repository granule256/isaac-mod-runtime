#pragma once

#include "domain/console/console_commands.hpp"
#include "infrastructure/console/console_bridge.hpp"
#include "infrastructure/console/console_command_history.hpp"
#include "infrastructure/console/console_panel_guards.hpp"
#include "ports/console_autocomplete_port.hpp"
#include "application/repentogon/repentogon_settings.hpp"

#include <algorithm>
#include <array>
#include <cstddef>
#include <cctype>
#include <cstdio>
#include <cstring>
#include <new>
#include <string>
#include <string_view>
#include <vector>

namespace isaac::runtime::console {
using ConsoleHistoryVisitor=void(*)(void*,const char*,std::size_t);
#if !defined(__SWITCH__)
struct ConsolePanelHostBindings {
    bool (*printWarning)(const char*,std::size_t){};
    bool (*printError)(const char*,std::size_t){};
    bool (*visitHistory)(ConsoleHistoryVisitor,void*){};
    bool (*dispatchAutocomplete)(const char*,std::size_t,const char*,std::size_t,
                                 AutocompleteVisitor,void*){};
};
inline ConsolePanelHostBindings& ConsolePanelTestBindings() noexcept {
    static ConsolePanelHostBindings bindings{};
    return bindings;
}
inline void SetConsolePanelHostBindings(ConsolePanelHostBindings bindings) noexcept {
    ConsolePanelTestBindings()=bindings;
}
#endif
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
    void (*fillOmnicomplete)(void*){};
    bool (*extensionEnabled)(){};
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
    out->fillOmnicomplete=engine_call::ResolveFunction<decltype(out->fillOmnicomplete)>(
        base,size,native_panel::kFillOmnicompleteOffset,
        native_panel::kFillOmnicompleteBytes,&engine_memory::EngineMemoryReadable);
    out->extensionEnabled=[](){return g_RepentogonSettings.StartupEnabled();};
#undef CONSOLE_PANEL_ENTRY
    return out->Ready();
}
inline std::uint32_t NativePanelState() noexcept {
    std::uint32_t value{};
    if (Storage().objectReady) std::memcpy(&value,Storage().consoleObject,sizeof(value));
    return value;
}
inline void SetPanelInput(const PanelNativeEntries& ui,const char* text) noexcept;
inline constexpr std::size_t kPanelCompletionCount=6;
inline constexpr std::size_t kPanelCompletionTextCapacity=kPanelUtf8Capacity;
inline constexpr std::array<std::uintptr_t,kPanelCompletionCount> kPanelCompletionOffsets={
    0x138,0x120,0x108,0xf0,0xd8,0xc0};
struct PanelCompletionEntry {
    std::string text;
    std::string description;
};
struct PanelCompletionState {
    // The state itself stays POD. The candidate vector is created only when
    // an input change actually needs a new completion list.
    std::vector<PanelCompletionEntry>* entries{};
    std::size_t windowStart{};
    int selected{-1};
    std::size_t rejected{};
};
inline PanelCompletionState& Completions() noexcept {
    static PanelCompletionState state{};
    return state;
}
inline std::vector<PanelCompletionEntry>* PanelCompletionEntries() noexcept {
    auto& state=Completions();
    if(!state.entries)
        state.entries=new(std::nothrow) std::vector<PanelCompletionEntry>();
    return state.entries;
}
inline std::size_t CompletionCount() noexcept {
    const auto* entries=Completions().entries;
    return entries?entries->size():0;
}
inline void ResetPanelCompletionState() noexcept {
    auto& completions=Completions();
    if(completions.entries)completions.entries->clear();
    completions.windowStart=0;
    completions.selected=-1;
    completions.rejected=0;
}
inline void CopyCompletionText(char* destination,std::size_t capacity,
                               const char* source,std::size_t length) noexcept {
    if(!destination||!capacity)return;
    const auto copy=source?std::min(length,capacity-1):0;
    if(copy)std::memcpy(destination,source,copy);
    destination[copy]='\0';
}
inline void ClearPanelCompletions(const PanelNativeEntries& ui) noexcept {
    ResetPanelCompletionState();
    if(!ui.assign)return;
    for(const auto offset:kPanelCompletionOffsets)
        ui.assign(Storage().consoleObject+offset,"");
}
inline void ReleasePanelCompletions() noexcept {
    auto& completions=Completions();
    delete completions.entries;
    completions.entries=nullptr;
    completions.windowStart=0;
    completions.selected=-1;
    completions.rejected=0;
}
inline bool ContainsIgnoreCase(std::string_view text,std::string_view wanted) noexcept {
    if(wanted.empty())return true;
    for(std::size_t at=0;at<text.size();++at) {
        std::size_t index=0;
        while(at+index<text.size()&&index<wanted.size()&&
              std::tolower(static_cast<unsigned char>(text[at+index]))==
              std::tolower(static_cast<unsigned char>(wanted[index])))++index;
        if(index==wanted.size())return true;
    }
    return false;
}
inline bool StartsWithIgnoreCase(std::string_view text,std::string_view prefix) noexcept {
    if(prefix.size()>text.size())return false;
    for(std::size_t index=0;index<prefix.size();++index) {
        if(std::tolower(static_cast<unsigned char>(text[index]))!=
           std::tolower(static_cast<unsigned char>(prefix[index])))return false;
    }
    return true;
}
inline bool AddPanelCompletion(std::string_view text,std::string_view description,
                               bool applyLimit=true) noexcept {
    auto& completions=Completions();
    if(text.empty())return true;
    if(text.size()>=kPanelCompletionTextCapacity) {
        ++completions.rejected;
        return true;
    }
    auto* entries=PanelCompletionEntries();
    if(!entries)return false;
    for(const auto& existing:*entries)
        if(existing.text==text)return true;
    // Match ConsoleMega's candidate acceptance point: filtering happens first,
    // then the visible buffer is capped while entries are appended. The pinned
    // upstream condition is `size() > limit`, so the default of 10 admits 11.
    if (applyLimit && CompletionCount() >
        static_cast<std::size_t>(ConsoleAutofillLimit())) return true;
    try {
        entries->push_back(PanelCompletionEntry{
            std::string(text),std::string(description)});
    } catch(...) {
        return false;
    }
    return true;
}
inline void WritePanelCompletionSlots(const PanelNativeEntries& ui) noexcept {
    auto& completions=Completions();
    if(!ui.assign)return;
    const auto* entries=completions.entries;
    const auto count=entries?entries->size():0;
    for(std::size_t index=0;index<kPanelCompletionCount;++index) {
        std::string display;
        const auto entryIndex=completions.windowStart+index;
        if(entryIndex<count) {
            const auto& entry=(*entries)[entryIndex];
            if(static_cast<int>(entryIndex)==completions.selected)
                display="> ";
            display+=entry.text;
        }
        ui.assign(Storage().consoleObject+kPanelCompletionOffsets[index],
                  display.c_str());
    }
}
inline bool SplitPanelAutocomplete(const char* input,char* command,
                                   std::size_t commandCapacity,char* parameters,
                                   std::size_t parameterCapacity,
                                   bool* hasArguments) noexcept {
    if(command&&commandCapacity)command[0]='\0';
    if(parameters&&parameterCapacity)parameters[0]='\0';
    if(hasArguments)*hasArguments=false;
    if(!input||!command||!commandCapacity||!parameters||!parameterCapacity)return false;
    std::size_t inputLength=0;
    while(inputLength<kPanelUtf8Capacity&&input[inputLength])++inputLength;
    if(inputLength==kPanelUtf8Capacity)return false;
    std::size_t at=0;
    while(input[at]&&std::isspace(static_cast<unsigned char>(input[at])))++at;
    std::size_t written=0;
    while(input[at]&&!std::isspace(static_cast<unsigned char>(input[at]))) {
        if(written+1>=commandCapacity)return false;
        command[written++]=input[at++];
    }
    command[written]='\0';
    const bool separated=input[at]!=0;
    while(input[at]&&std::isspace(static_cast<unsigned char>(input[at])))++at;
    written=0;
    bool pendingSpace=false;
    for(;input[at];++at) {
        if(std::isspace(static_cast<unsigned char>(input[at]))) {
            pendingSpace=written!=0;
            continue;
        }
        if(pendingSpace) {
            if(written+1>=parameterCapacity)return false;
            parameters[written++]=' ';
        }
        pendingSpace=false;
        if(written+1>=parameterCapacity)return false;
        parameters[written++]=input[at];
    }
    parameters[written]='\0';
    if(hasArguments)*hasArguments=separated;
    return true;
}
struct PanelAutocompleteCollector {
    std::string_view command;
    std::string_view parameters;
};
inline bool CollectPanelAutocomplete(void* user,const char* text,std::size_t textLength,
                                     const char* description,
                                     std::size_t descriptionLength) noexcept {
    auto* collector=static_cast<PanelAutocompleteCollector*>(user);
    if(!collector||!text||!textLength)return true;
    if(collector->command.size()>=kPanelCompletionTextCapacity-1||
       textLength>=kPanelCompletionTextCapacity-collector->command.size()-1) {
        ++Completions().rejected;
        return true;
    }
    std::string full;
    try {
        full.reserve(collector->command.size()+1+textLength);
        full.append(collector->command);
        full.push_back(' ');
        full.append(text,textLength);
    } catch(...) {
        return false;
    }
    const bool textMatches=StartsWithIgnoreCase(full,collector->command)&&
        full.size()>collector->command.size()&&
        full[collector->command.size()]==' '&&
        StartsWithIgnoreCase(std::string_view(full).substr(
            collector->command.size()+1),collector->parameters);
    const std::string_view descriptionText=
        description?std::string_view(description,descriptionLength):std::string_view{};
    if(textMatches||
       ContainsIgnoreCase(descriptionText,collector->parameters))
        return AddPanelCompletion(full,descriptionText);
    return true;
}
inline bool DispatchPanelAutocomplete(const char* command,std::size_t commandLength,
                                      const char* parameters,
                                      std::size_t parameterLength,
                                      AutocompleteVisitor visitor,
                                      void* user) noexcept {
#if !defined(__SWITCH__)
    if(const auto& bindings=ConsolePanelTestBindings();bindings.dispatchAutocomplete)
        return bindings.dispatchAutocomplete(command,commandLength,parameters,
                                             parameterLength,visitor,user);
#endif
    return DispatchAutocomplete(command,commandLength,parameters,
                                parameterLength,visitor,user);
}
inline bool RefreshPanelCompletions(const PanelNativeEntries& ui,
                                    const char* input) noexcept {
    if (!ui.extensionEnabled || !ui.extensionEnabled()) {
        ResetPanelCompletionState();
        if (ui.fillOmnicomplete) ui.fillOmnicomplete(Storage().consoleObject);
        return false;
    }
    ClearPanelCompletions(ui);
    if(!input||!ui.assign)return false;
    if(!*input) {
        if(ui.fillOmnicomplete)ui.fillOmnicomplete(Storage().consoleObject);
        return false;
    }
    char command[kPanelUtf8Capacity]{};
    char parameters[kPanelUtf8Capacity]{};
    bool hasArguments=false;
    if(!SplitPanelAutocomplete(input,command,sizeof(command),parameters,
                               sizeof(parameters),&hasArguments)) {
        WritePanelCompletionSlots(ui);
        return false;
    }
    if(!command[0]) {
        WritePanelCompletionSlots(ui);
        return CompletionCount()!=0;
    }
    if(!hasArguments) {
        for(std::size_t index=0;index<ConsoleCommandCount();++index) {
            const auto* definition=ConsoleCommandAt(index);
            if(definition&&definition->name.starts_with(command))
                static_cast<void>(AddPanelCompletion(
                    definition->name,definition->description,false));
        }
    } else {
        const auto* definition=FindConsoleCommand(command);
        if(definition&&definition->autocompleteType==
           ConsoleAutocompleteType::Custom) {
            PanelAutocompleteCollector collector{command,parameters};
            static_cast<void>(DispatchPanelAutocomplete(
                command,std::strlen(command),parameters,std::strlen(parameters),
                &CollectPanelAutocomplete,&collector));
        }
    }
    if(!CompletionCount()) {
        // Native slots are packed display rows, never executable extension candidates.
        if(ui.fillOmnicomplete)ui.fillOmnicomplete(Storage().consoleObject);
        return false;
    }
    WritePanelCompletionSlots(ui);
    return CompletionCount()!=0;
}
inline bool MovePanelCompletionSelection(int delta) noexcept {
    auto& completions=Completions();
    const auto count=CompletionCount();
    if(!count||!delta)return false;
    int selected=completions.selected;
    if(selected<0)selected=delta>0?0:static_cast<int>(count)-1;
    else {
        const int boundedCount=static_cast<int>(count);
        selected=(selected+delta)%boundedCount;
        if(selected<0)selected+=boundedCount;
    }
    completions.selected=selected;
    const auto visible=std::min<std::size_t>(kPanelCompletionCount,count);
    if(static_cast<std::size_t>(selected)<completions.windowStart)
        completions.windowStart=static_cast<std::size_t>(selected);
    else if(static_cast<std::size_t>(selected)>=
            completions.windowStart+visible)
        completions.windowStart=static_cast<std::size_t>(selected)-visible+1;
    if(completions.windowStart>count-visible)
        completions.windowStart=count-visible;
    return true;
}
inline bool StorePanelDraftUtf8(const char* text) noexcept {
    auto& panel=Panel();
    std::size_t at=0,written=0;
    while(text&&text[at]&&written+1<kPanelTextCapacity) {
        std::uint32_t codePoint{};
        const auto lead=static_cast<unsigned char>(text[at++]);
        if(lead<0x80U)codePoint=lead;
        else if((lead&0xe0U)==0xc0U&&text[at]) {
            codePoint=static_cast<std::uint32_t>(lead&0x1fU)<<6;
            codePoint|=static_cast<unsigned char>(text[at++])&0x3fU;
        } else if((lead&0xf0U)==0xe0U&&text[at]&&text[at+1]) {
            codePoint=static_cast<std::uint32_t>(lead&0x0fU)<<12;
            codePoint|=static_cast<std::uint32_t>(
                static_cast<unsigned char>(text[at++])&0x3fU)<<6;
            codePoint|=static_cast<unsigned char>(text[at++])&0x3fU;
        } else if((lead&0xf8U)==0xf0U&&text[at]&&text[at+1]&&text[at+2]) {
            codePoint=static_cast<std::uint32_t>(lead&0x07U)<<18;
            codePoint|=static_cast<std::uint32_t>(
                static_cast<unsigned char>(text[at++])&0x3fU)<<12;
            codePoint|=static_cast<std::uint32_t>(
                static_cast<unsigned char>(text[at++])&0x3fU)<<6;
            codePoint|=static_cast<unsigned char>(text[at++])&0x3fU;
        } else codePoint=0xfffdU;
        panel.draft[written++]=codePoint;
    }
    panel.draft[written]=0;
    return true;
}
inline std::string*& PanelRecalledInput() noexcept {
    static std::string* text{};
    return text;
}
inline const char* PanelInputText() noexcept {
    return PanelRecalledInput()?PanelRecalledInput()->c_str():Panel().draftUtf8;
}
inline void ResetPanelHistoryNavigation() noexcept {
    delete PanelRecalledInput();
    PanelRecalledInput()=nullptr;
}
inline bool PanelDraftFitsKeyboard(const char* text) noexcept {
    std::size_t points{};
    for (const auto* ch=text;*ch;++ch)
        if ((static_cast<unsigned char>(*ch)&0xc0U)!=0x80U) ++points;
    return points<kPanelTextCapacity;
}
inline bool MovePanelHistory(const PanelNativeEntries& ui,int delta) noexcept {
    auto& panel=Panel();
    CommandHistoryView history{};
    if (!delta || !ReadCommandHistoryView(Storage().consoleObject,&history)) return false;
    std::uint64_t current{};
    if (!CommandHistoryOffset(history,&current)) return false;
    auto next=current;
    if (delta<0) {
        if (next>=history.count) return false;
        ++next;
    } else {
        if (next) --next;
    }
    std::string selected;
    if (next && !ReadCommandHistoryEntry(history,next-1,&selected)) {
        return false;
    }
    auto* text=new(std::nothrow) std::string();
    if (!text) return false;
    text->swap(selected);
    if (!SetCommandHistoryOffset(history,next)) {delete text;return false;}
    ResetPanelHistoryNavigation();
    PanelRecalledInput()=text;
    if (text->size()<sizeof(panel.draftUtf8) && PanelDraftFitsKeyboard(text->c_str())) {
        CopyCompletionText(panel.draftUtf8,sizeof(panel.draftUtf8),text->data(),text->size());
        static_cast<void>(StorePanelDraftUtf8(text->c_str()));
    }
    SetPanelInput(ui,text->c_str());
    static_cast<void>(RefreshPanelCompletions(ui,text->c_str()));
    return true;
}
inline bool ApplySelectedPanelCompletion(const PanelNativeEntries& ui) noexcept {
    auto& completions=Completions();
    if(completions.selected<0||
       static_cast<std::size_t>(completions.selected)>=CompletionCount()||
       !completions.entries)return false;
    const auto& entry=(*completions.entries)[completions.selected];
    auto& panel=Panel();
    if(entry.text.size()>=sizeof(panel.draftUtf8))return false;
    ResetPanelHistoryNavigation();
    CopyCompletionText(panel.draftUtf8,sizeof(panel.draftUtf8),
                       entry.text.data(),entry.text.size());
    static_cast<void>(StorePanelDraftUtf8(panel.draftUtf8));
    SetPanelInput(ui,panel.draftUtf8);
    ClearPanelCompletions(ui);
    return true;
}
inline bool CyclePanelCompletion(const PanelNativeEntries& ui) noexcept {
    if (!CompletionCount()) return false;
    auto& state=Completions();
    state.selected=(state.selected+1)%static_cast<int>(CompletionCount());
    const auto& entry=(*state.entries)[state.selected];
    if (entry.text.size()>=sizeof(Panel().draftUtf8) ||
        !PanelDraftFitsKeyboard(entry.text.c_str())) return false;
    ResetPanelHistoryNavigation();
    CopyCompletionText(Panel().draftUtf8,sizeof(Panel().draftUtf8),entry.text.data(),entry.text.size());
    static_cast<void>(StorePanelDraftUtf8(entry.text.c_str()));
    SetPanelInput(ui,entry.text.c_str());
    // Like PC's extension Tab callback, keep the original candidate buffer while cycling.
    return true;
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
                       std::uint32_t color=0xFFD3D3D3U,
                       std::uint32_t flags=0) noexcept {
    if (!text || !length) return;
    alignas(8) unsigned char borrowed[kEngineStringBytes]{};
    if (!BuildBorrowedCommandString(text,length,borrowed)) return;
    // RunCommand的输出重定向只属于那次调用；显示历史必须送往原生deque。
    auto& c=Storage();
    std::uintptr_t output{};
    std::memcpy(&output,c.consoleObject+0x150,sizeof(output));
    std::memset(c.consoleObject+0x150,0,sizeof(output));
    ui.print(c.consoleObject,borrowed,color,flags);
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
inline bool PrintConsoleWarning(std::uintptr_t base,const char* text,std::size_t length) noexcept {
#if !defined(__SWITCH__)
    if (const auto& bindings=ConsolePanelTestBindings();bindings.printWarning)
        return bindings.printWarning(text,length);
#endif
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
    PrintPanel(ui,text,length,0xFFFCCA03U,0x96U);
    return ObjectFenceIntact(Storage());
}
inline bool PrintConsoleError(std::uintptr_t base,const char* text,std::size_t length) noexcept {
#if !defined(__SWITCH__)
    if (const auto& bindings=ConsolePanelTestBindings();bindings.printError)
        return bindings.printError(text,length);
#endif
    if (!base || !text || !length) return false;
    static std::uintptr_t cachedBase{};
    static EngineEntries engine{};
    static void (*printError)(void*,const void*){};
    static bool ready{};
    if (cachedBase!=base) {
        cachedBase=base;
        ready=ResolveConsoleEntries(base,kGameModuleRangeCheckSize,&engine);
        printError=ready?engine_call::ResolveFunction<decltype(printError)>(
            base,kGameModuleRangeCheckSize,native_panel::kPrintErrorOffset,
            native_panel::kPrintErrorBytes,&engine_memory::EngineMemoryReadable):nullptr;
        ready=ready&&printError;
    }
    if (!ready || !EnsureConsoleObject(engine)) return false;
    alignas(8) unsigned char borrowed[kEngineStringBytes]{};
    if (!BuildBorrowedCommandString(text,length,borrowed)) return false;
    printError(Storage().consoleObject,borrowed);
    return ObjectFenceIntact(Storage());
}
inline bool VisitConsoleHistoryObject(const void* object,ConsoleHistoryVisitor visitor,void* user) noexcept {
    auto* bytes=static_cast<const unsigned char*>(object);
    if (!object || !visitor) return false;
    std::uintptr_t map{},mapEnd{};
    std::uint64_t begin{},count{};
    std::memcpy(&map,bytes+0x58,sizeof(map));
    std::memcpy(&mapEnd,bytes+0x60,sizeof(mapEnd));
    std::memcpy(&begin,bytes+0x70,sizeof(begin));
    std::memcpy(&count,bytes+0x78,sizeof(count));
    if (!count) return true;
    if (!map || mapEnd<map || (mapEnd-map)%sizeof(std::uintptr_t) ||
        count>0x10000 || begin>UINT64_MAX-count) return false;
    constexpr std::uint64_t kBlockEntries=85;
    constexpr std::uintptr_t kEntryBytes=0x30;
    const auto mapCount=(mapEnd-map)/sizeof(std::uintptr_t);
    if ((begin+count-1)/kBlockEntries>=mapCount) return false;
    for (std::uint64_t index=begin;index<begin+count;++index) {
        const auto blockIndex=index/kBlockEntries;
        const auto entryIndex=index%kBlockEntries;
        std::uintptr_t block{};
        if (!engine_memory::ReadField(map,blockIndex*sizeof(block),&block,
                                      engine_memory::EngineMemoryReadable) ||
            !block) return false;
        if (block>UINTPTR_MAX-entryIndex*kEntryBytes) return false;
        const auto entry=block+entryIndex*kEntryBytes;
        unsigned char header[0x18]{};
        if (!engine_memory::ReadField(entry,0,&header,
                                      engine_memory::EngineMemoryReadable)) return false;
        const bool longString=(header[0]&1U)!=0;
        std::uintptr_t data{};
        std::size_t length{};
        if (longString) {
            std::memcpy(&length,header+0x08,sizeof(length));
            std::memcpy(&data,header+0x10,sizeof(data));
            if (!data || length>1024*1024) return false;
            if (length && !engine_memory::EngineMemoryReadable(data,length)) return false;
            visitor(user,reinterpret_cast<const char*>(data),length);
        } else {
            length=static_cast<std::size_t>(header[0]>>1);
            if (length>sizeof(header)-2) return false;
            visitor(user,reinterpret_cast<const char*>(header+1),length);
        }
    }
    return true;
}
inline bool VisitConsoleHistory(std::uintptr_t base,ConsoleHistoryVisitor visitor,void* user) noexcept {
#if !defined(__SWITCH__)
    if (const auto& bindings=ConsolePanelTestBindings();bindings.visitHistory)
        return bindings.visitHistory(visitor,user);
#endif
    if (!base || !visitor) return false;
    static std::uintptr_t cachedBase{};
    static EngineEntries engine{};
    static bool ready{};
    if (cachedBase!=base) {
        cachedBase=base;
        ready=ResolveConsoleEntries(base,kGameModuleRangeCheckSize,&engine);
    }
    if (!ready || !EnsureConsoleObject(engine) || !ObjectFenceIntact(Storage())) return false;
    return VisitConsoleHistoryObject(Storage().consoleObject,visitor,user);
}

inline void ClosePanelImmediately(const PanelNativeEntries& ui) noexcept {
    auto& p=Panel();
    const bool nativeUsable=NativePanelState()!=0 && ui.Ready() &&
                            ObjectFenceIntact(Storage());
    if(nativeUsable) {
        ClearPanelCompletions(ui);
    } else {
        // A failed fence means the native object bytes are no longer trustworthy.
        // Reset only our POD/vector state; never call native assign here.
        ResetPanelCompletionState();
    }
    ReleasePanelCompletions();
    if (nativeUsable) {
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
inline int PanelCompletionHit(PanelTouch touch,float width,float height) noexcept {
    const auto count=CompletionCount();
    if(!touch.pressed||!count||touch.rawX>=1280||touch.rawY>=720||
       !(width>20&&width<=8192&&height>20&&height<=8192))return -1;
    float bottom=height-1;
    float nativeBottom{};
    std::memcpy(&nativeBottom,Storage().consoleObject+0x10,sizeof(nativeBottom));
    if(nativeBottom>0&&nativeBottom<height)bottom=nativeBottom;
    const float x=static_cast<float>(touch.rawX)*width/1280.0F;
    const float y=static_cast<float>(touch.rawY)*height/720.0F;
    std::uintptr_t begin{},end{};
    std::memcpy(&begin,Storage().consoleObject+0x38,sizeof(begin));
    std::memcpy(&end,Storage().consoleObject+0x40,sizeof(end));
    const auto breaks=end>=begin?(end-begin)/2:0;
    if(breaks>=kPanelTextCapacity)return -1;
    const auto inputRows=breaks>6?breaks:6;
    const auto inputTop=bottom-18-static_cast<float>(inputRows)*15;
    const auto visible=std::min<std::size_t>(count,
        6-static_cast<std::size_t>(std::min<std::uintptr_t>(breaks,6)));
    const auto regionTop=inputTop-static_cast<float>(visible)*15;
    if(x<10||x>width-10||y<regionTop||y>=inputTop)return -1;
    const auto row=static_cast<std::size_t>((y-regionTop)/15);
    const auto index=Completions().windowStart+row;
    return index<count?static_cast<int>(index):-1;
}
inline bool IsHelpInvocation(const char* command,std::size_t length) noexcept {
    char parsed[kPanelUtf8Capacity]{};
    char parameters[kPanelUtf8Capacity]{};
    std::string input(command&&length?std::string_view(command,length):std::string_view{});
    if(!SplitPanelAutocomplete(input.c_str(),parsed,sizeof(parsed),parameters,
                               sizeof(parameters),nullptr))return false;
    return std::strcmp(parsed,"help")==0;
}
inline bool PrintCustomConsoleHelp(const PanelNativeEntries& ui,const char* command,
                                   std::size_t length,bool inGame) noexcept {
    if(!ui.print||!command||!length)return false;
    std::string invocation(command,length);
    auto help=BuildConsoleHelp(invocation,inGame);
    if(help.empty())return false;
    PrintPanel(ui,help.data(),help.size());
    return true;
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
        ResetPanelHistoryNavigation();
        if (NativePanelState()!=0) ClosePanelImmediately(ui);
        else ReleasePanelCompletions();
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
                SetPanelInput(ui,PanelInputText());
                static_cast<void>(RefreshPanelCompletions(ui,PanelInputText()));
                p.game=game;p.sessionEpoch=g_ConsoleSessionEpoch.load(std::memory_order_relaxed);p.waitRelease=true;justOpened=true;++p.opened;
            } else if (NativePanelState()!=0) {
                ui.hide(core.consoleObject);p.waitRelease=true;++p.closed;
                ReleasePanelCompletions();
            }
        }
    } else if (!combo) {core.comboHeldFrames=0;core.comboFired=false;}

    if (p.draftChanged) {
        ResetPanelHistoryNavigation();
        static_cast<void>(Utf32ToUtf8(p.draft,kPanelTextCapacity,p.draftUtf8,sizeof(p.draftUtf8)));
        SetPanelInput(ui,p.draftUtf8);
        static_cast<void>(RefreshPanelCompletions(ui,p.draftUtf8));
        p.draftChanged=false;
    }
    const bool panelEnter=(NativePanelState()==2 || NativePanelState()==3) &&
        !p.keyboardOpen && !p.waitRelease && !combo && (risen&(1U<<12));
    if (panelEnter && !*PanelInputText()) {
        ui.hide(core.consoleObject);p.waitRelease=true;++p.closed;
        ReleasePanelCompletions();
    }
    if (p.keyboardFinished || (core.pendingReady && !p.keyboardOpen) ||
        (panelEnter && *PanelInputText())) {
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
        if (panelEnter) {
            command=PanelInputText();length=static_cast<std::uint32_t>(std::strlen(command));
        }
        bool nonSpace=false;
        for (std::size_t i=0;command && i<length;++i) if(command[i]!=' ') {nonSpace=true;break;}
        if ((fromKeyboard ? length!=0 : pending || panelEnter) && nonSpace && EnsureConsoleObject(entries)) {
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
            }
            if (outcome.status==ExecStatus::kOk && IsHelpInvocation(command,length))
                static_cast<void>(PrintCustomConsoleHelp(ui,command,length,true));
            else if (outcome.status!=ExecStatus::kOk) {
                char note[]="[status 00]\n";
                const auto code=static_cast<unsigned>(outcome.status)%100;
                note[8]=static_cast<char>('0'+code/10);note[9]=static_cast<char>('0'+code%10);
                PrintPanel(ui,note,sizeof(note)-1);
            }
            std::memset(p.draft,0,sizeof(p.draft));p.draftUtf8[0]=0;SetPanelInput(ui,"");
            ResetPanelHistoryNavigation();
            static_cast<void>(RefreshPanelCompletions(ui,""));
        }
    }
    if (p.waitRelease && mask==0 && !touch.pressed && !p.keyboardOpen) p.waitRelease=false;
    if ((NativePanelState()==2 || NativePanelState()==3) && !justOpened && !p.keyboardOpen && !p.waitRelease && !combo) {
        constexpr std::uint32_t historyUp=1U<<19,historyDown=1U<<20;
        constexpr std::uint32_t completionTab=1U<<23; // Switch X maps to extension Tab.
        bool completionHandled=false;
        if ((risen&historyUp)!=0||(risen&historyDown)!=0) {
            static_cast<void>(MovePanelHistory(ui,(risen&historyUp)!=0?-1:1));
            completionHandled=true;
        } else if (ui.extensionEnabled && ui.extensionEnabled() &&
                   (risen&completionTab)!=0) {
            if (!CompletionCount()) static_cast<void>(RefreshPanelCompletions(ui,p.draftUtf8));
            completionHandled=CyclePanelCompletion(ui);
        }
        if (!completionHandled&&touchRise) {
            const auto hit=PanelCompletionHit(touch,width,height);
            if (hit>=0&&static_cast<std::size_t>(hit)<CompletionCount()) {
                Completions().selected=hit;
                completionHandled=ApplySelectedPanelCompletion(ui);
                p.waitRelease=true;
            }
        }
        if (!completionHandled) {
            if ((risen&back)!=0 || shortBack) {
                ClearPanelCompletions(ui);
                ui.hide(core.consoleObject);p.waitRelease=true;++p.closed;
            } else if ((risen&confirm)!=0 || shortConfirm ||
                       (touchRise&&PanelInputHit(touch,width,height))) {
                if (PanelDraftFitsKeyboard(PanelInputText())) {
                    static_cast<void>(StorePanelDraftUtf8(PanelInputText()));
                    p.keyboardFinished=false;p.keyboardOpen=true;
                    if (!RequestKeyboard(entries,kage,&PanelKeyboardChanged,p.draft))
                        p.keyboardOpen=false;
                }
            }
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
