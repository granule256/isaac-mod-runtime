#pragma once
#include "infrastructure/console/console_panel_guards.hpp"
#include "infrastructure/call/engine_call_access.hpp"
#include "infrastructure/memory/engine_field_access.hpp"
#include "runtime_constants.hpp"
#include <cstring>

namespace isaac::runtime::console {
using ClearHistoryFunction=void(*)(void*);
inline bool ClearVisibleConsole(void* object,ClearHistoryFunction clear) noexcept {
    if (!object || !clear) return false;
    // Clear会重新Print欢迎语；必须进可见历史，不能被RunCommand的返回串重定向吞掉。
    auto* bytes=static_cast<unsigned char*>(object);
    std::uintptr_t output{};
    std::memcpy(&output,bytes+0x150,sizeof(output));
    std::memset(bytes+0x150,0,sizeof(output));
    clear(object);
    std::memcpy(bytes+0x150,&output,sizeof(output));
    return true;
}
inline ClearHistoryFunction ResolveClearHistory(std::uintptr_t base) noexcept {
    return engine_call::ResolveFunction<ClearHistoryFunction>(base,kGameModuleRangeCheckSize,
        native_panel::kClearOffset,native_panel::kClearBytes,&engine_memory::EngineMemoryReadable);
}
}
