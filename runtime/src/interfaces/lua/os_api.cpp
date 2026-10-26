#include "third_party/lua-5.3.3/src/lprefix.h"
#include "interfaces/lua/os_api.hpp"
#include "interfaces/lua/process_elapsed_clock.hpp"
#include "interfaces/lua/runtime_perf.hpp"
#if !defined(__SWITCH__)
#include <chrono>
#endif
// 原件不改；只复用其时间/日期/环境/locale消费者，避免另写一份近似Lua规则。
// luaopen_os本体没有注册或调用；未选中的文件/进程函数不进入公开os表。
extern "C" {
#define luaopen_os isaac_unregistered_original_os_library
#include "third_party/lua-5.3.3/src/loslib.c"
#undef luaopen_os
}
namespace isaac::runtime {
namespace {
ProcessElapsedClock g_ProcessClock{};
std::uint64_t ClockTick() noexcept {
#if defined(__SWITCH__)
    return RuntimePerfTick();
#else
    return static_cast<std::uint64_t>(std::chrono::duration_cast<std::chrono::nanoseconds>(
        std::chrono::steady_clock::now().time_since_epoch()).count());
#endif
}
int ProcessClock(lua_State* state) {
#if defined(__SWITCH__)
    constexpr auto frequency = 19200000ULL;
#else
    constexpr auto frequency = 1000000000ULL;
#endif
    lua_pushnumber(state, g_ProcessClock.Seconds(ClockTick(), frequency));
    return 1;
}
}
void InitializeOsClock() noexcept { g_ProcessClock.Start(ClockTick()); }
void RegisterOsLibrary(lua_State* state) {
    InitializeOsClock();
    static const luaL_Reg functions[]{
        {"clock",ProcessClock},{"date",os_date},{"difftime",os_difftime},
        {"getenv",os_getenv},{"setlocale",os_setlocale},{"time",os_time},{nullptr,nullptr},
    };
    luaL_newlib(state,functions);
    lua_setglobal(state,"os");
}
}
