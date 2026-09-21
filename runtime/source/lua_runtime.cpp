#include "lua_runtime.hpp"
// 批次 106：`Level:GetStartingRoomIndex()` 的派生记账（纯逻辑，见该头文件顶部的取证说明）。
#include "frame_event_decision.hpp"
#include "level_start_room.hpp"
// `GameFileReader::Bindings` 出现在公开入口的签名里（`InitializeManifestMod` / `InitializeEmbeddedMenuMod`）：
// 之前它靠别的头间接带进来，宿主 harness 的包含路径不同就会"未声明"，所以显式包含。
#include "game_file_reader.hpp"

#include "game_observer.hpp"
#include "lua_object_handles.hpp"
#include "lua_runtime_state.hpp"
#include "hook_manager.hpp"
#include "mod_persistence.hpp"
#include "persistence_event_journal.hpp"
#include "program/setting.hpp"

#include <cstdarg>
#include <cstdlib>
#include <ctime>

// 堆用量读数只在真机（devkitA64/newlib）上有意义：宿主 harness 用 clang 编译本文件，
// macOS 的 `sbrk` 被标成 deprecated 且 harness 带 `-Werror`（曾因此让 13 个宿主用例编不过）。
// `__SWITCH__` 是 devkitA64 预定义的。
#if defined(__SWITCH__) && defined(EXL_USE_FAKEHEAP)
#include <unistd.h>
extern "C" char __fake_heap[];
#endif
#include "program/pc_lua_enum_data.hpp"
#include "program/pc_lua_enum_data.cpp"
// 批次 048：`pc_lua_enum_data` 那 20 张之外的 PC 全局枚举表，由仓库自带的 PC 文档快照生成
// （`tools/generate_doc_enum_tables.py`）。真机上 `RoomShape` 缺失 ⇒ GoodTrip 的
// `widget.lua:185` 报 `attempt to index a nil value (global 'RoomShape')`、小地图画不出来。
#include "program/doc_lua_enum_data.hpp"
#include "program/doc_lua_enum_data.cpp"
#include "program/embedded_lua_test_script.hpp"
#include "program/embedded_mod_menu_script.hpp"
#include "runtime_constants.hpp"

// Every build entry point (production module, diagnostics and the startup
// probes) defines `EXL_LAYERED_RUNTIME`, so the layered headers are required
// unconditionally: the non-layered duplicate implementations no longer exist.
#include "interfaces/lua/engine_frame_probe.hpp"
#include "interfaces/lua/engine_memory_guard.hpp"
#include "application/callback/callback_dispatcher.hpp"
#include "application/callback/callback_registry.hpp"
#include "domain/callback/callback_descriptor.hpp"
#include "interfaces/lua/api_catalog.hpp"
#include "interfaces/lua/json_api.hpp"
#include "interfaces/lua/color_api.hpp"
#include "interfaces/lua/entity_ref_api.hpp"
#include "interfaces/lua/font_api.hpp"
#include "interfaces/lua/game_api.hpp"
#include "interfaces/lua/input_api.hpp"
#include "interfaces/lua/mod_menu_api.hpp"
#include "interfaces/lua/isaac_api.hpp"
#include "interfaces/lua/mod_api.hpp"
#include "interfaces/lua/music_api.hpp"
#include "interfaces/lua/remaining_api.hpp"
#include "interfaces/lua/rng_api.hpp"
#include "interfaces/lua/vector_api.hpp"
#include "interfaces/lua/sprite_api.hpp"

#if defined(__SWITCH__)
#include "lib/nx/nx.h"
#endif

extern "C" {
#include <lauxlib.h>
#include <lualib.h>
}

#include <atomic>
#include <array>
#include <cstring>
#include <limits>


#include "interfaces/lua/runtime_perf.hpp"
#include "interfaces/lua/runtime_profiler.hpp"
#include "interfaces/lua/owner_binding.hpp"

// ============================================================================
// 常驻性能面（批次 084：**只用同 TU 的 file-local 计数 + 导出函数**）
// ============================================================================
//
// 为什么是 file-local `static`：批次 081 把它们做成"跨 TU 的全局"，编译器于是**通过数据 GOT 槽**
// 取地址，而那个槽在运行时是 0 ⇒ 启动就对 0 做原子加、`Data Abort`（见 `runtime_perf.hpp` 的说明）。
// file-local `static` 在 `nm` 里仍是**裸名**（读数工具照旧按名字读），但访问走 `adrp/add`，不碰 GOT。
//
// 需要从别的编译单元记账时，**调函数**（PLT），不要引用变量 —— 见 `runtime_perf.hpp` 的约定。
// `extern "C"` + **hidden 可见性** 是**两个都要**：
//   * `hidden` ⇒ 符号不参与跨模块抢占 ⇒ 编译器直接 `adrp/add`，**不经过数据 GOT**
//     （批次 081 的启动崩溃就是走了 GOT 槽：槽里是 0，于是对 0 做原子加）；
//   * `extern "C"` ⇒ 名字不进名称改编（`nm` 里就是裸名 `g_RuntimePerf…`），读数工具按名字直读。
//   只用内部链接（`static`）名字会变成 `_ZL26g_RuntimePerfCallbackCalls`，工具就查不到了。
extern "C" {
__attribute__((visibility("hidden"))) std::atomic<std::uint64_t> g_RuntimePerfCallbackCalls{0};
__attribute__((visibility("hidden"))) std::atomic<std::uint64_t> g_RuntimePerfCallbackTicks{0};
__attribute__((visibility("hidden"))) std::atomic<std::uint64_t> g_RuntimePerfCallbackMaxTicks{0};
__attribute__((visibility("hidden"))) std::atomic<std::uint64_t> g_RuntimePerfSyscalls{0};
__attribute__((visibility("hidden"))) std::atomic<std::uint64_t> g_RuntimePerfSyscallTicks{0};
// 批次 086：按 (事件 id, 属主模组) 分开的回调耗时桶（"贵的是哪一个回调"）。
// 同一个 TU + 直接寻址 ⇒ 不碰数据 GOT；普通数组（不是原子）是因为**只有游戏线程走派发**，
// 与 `g_ErrorContextOwner` / `g_PostUpdateDispatchCount` 同一约定。
__attribute__((visibility("hidden"))) isaac::runtime::RuntimePerfCallbackBucket
    g_RuntimePerfCallbackBuckets[isaac::runtime::kRuntimePerfBucketCount]{};
__attribute__((visibility("hidden"))) std::uint64_t g_RuntimePerfBucketOverflow{0};
// 批次 087：按 **API 接口** 分开的耗时桶（与上面回调桶是两张独立的表）。
__attribute__((visibility("hidden"))) isaac::runtime::RuntimePerfCallbackBucket
    g_RuntimePerfApiBuckets[isaac::runtime::kRuntimePerfApiBucketCount]{};
__attribute__((visibility("hidden"))) std::uint64_t g_RuntimePerfApiBucketOverflow{0};
// 批次 094：**全局合计**——不管有没有进桶都要算，这样"所有接口一共花了多少"永远答得出来
// （093 之后真机溢出 267 万次，只看桶表会把大头漏掉）。
__attribute__((visibility("hidden"))) std::uint64_t g_RuntimePerfApiTotalCalls{0};
__attribute__((visibility("hidden"))) std::uint64_t g_RuntimePerfApiTotalTicks{0};
// 批次 089：Lua 采样剖析器的桶（按 `(source, name)` 归并）。名字同样是裸名，读数工具按名直读。
__attribute__((visibility("hidden"))) isaac::runtime::RuntimePerfProfileBucket
    g_RuntimePerfProfileBuckets[isaac::runtime::kRuntimePerfProfileBucketCount]{};
__attribute__((visibility("hidden"))) std::uint64_t g_RuntimePerfProfileSamples{0};
__attribute__((visibility("hidden"))) std::uint64_t g_RuntimePerfProfileOverflow{0};
// 批次 092：量具自校准（读一次 `cntpct_el0` 要多少 tick）。
__attribute__((visibility("hidden"))) std::uint64_t g_RuntimePerfTickCostTicks{0};
// 批次 095：**地板基准** —— "一次纯 Lua→C 调用"本身要多少 tick（不含任何处理器工作）。
// 有了它才能回答"我们还能把 1.40 µs 压到多低"：压到地板以下是不可能的。
__attribute__((visibility("hidden"))) std::uint64_t g_RuntimePerfEmptyCallTicks{0};
__attribute__((visibility("hidden"))) std::uint64_t g_RuntimePerfEmptyCallCount{0};
// 批次 091：**分配账**。087/088 的尺子量到的是"回调里的时间"与"接口自己的时间"，
// 而 089 的采样器又证明"Lua 指令执行"只占约 10 µs/帧 —— 那剩下的 2 毫秒去哪儿了？
// 唯一的共同嫌疑是**分配本身**（Lua 在每次分配里同步做增量 GC，这段 C 侧时间既不执行
// Lua 指令、也不在我们任何 handler 里，所以两把尺子都量不到它）。
// 给状态换一个"会计数"的分配器，就能直接把"每帧分配多少次、多少字节"量出来。
__attribute__((visibility("hidden"))) std::uint64_t g_RuntimePerfAllocCalls{0};
__attribute__((visibility("hidden"))) std::uint64_t g_RuntimePerfAllocBytes{0};
__attribute__((visibility("hidden"))) std::uint64_t g_RuntimePerfAllocNewCalls{0};
__attribute__((visibility("hidden"))) std::uint64_t g_RuntimePerfFreeCalls{0};
}
// tick 频率**不读寄存器**（`cntfrq_el0` 在 EL0 会陷入，见 `runtime_perf.hpp`）：
// Tegra X1 恒 19.2 MHz，因此这里连变量都不留 —— 读数工具按常量换算。

extern "C" void IsaacRuntime_PerfNoteSyscall(std::uint64_t ticks) {
    g_RuntimePerfSyscalls.fetch_add(1, std::memory_order_relaxed);
    g_RuntimePerfSyscallTicks.fetch_add(ticks, std::memory_order_relaxed);
}

// 批次 087：API 处理器（住在别的编译单元）用这个函数记账 —— **跨 TU 只走函数调用**（PLT），
// 不引用变量 ⇒ 不碰数据 GOT。收尾那次 tick 读数放在这里，调用点只负责"取一次 + 报一次"。
// 批次 092：量具自校准的读口（读数工具也可以直接读那个全局；这个函数给宿主/自检用）。
extern "C" std::uint64_t IsaacRuntime_PerfTickCostTicks() {
    return g_RuntimePerfTickCostTicks;
}

extern "C" void IsaacRuntime_PerfNoteApiCall(std::uint64_t key, std::uint64_t startTick) {
#if defined(ISAAC_RUNTIME_PERF_TIMING)
    const std::uint64_t endTick = isaac::runtime::RuntimePerfTick();
    if (endTick > startTick) {
        g_RuntimePerfApiTotalCalls += 1;
        g_RuntimePerfApiTotalTicks += (endTick - startTick);
        static_cast<void>(isaac::runtime::RecordRuntimePerfCallbackSample(
            g_RuntimePerfApiBuckets, isaac::runtime::kRuntimePerfApiBucketCount, key,
            endTick - startTick, &g_RuntimePerfApiBucketOverflow));
    }
#else
    // 宿主：`RuntimePerfTick()` 恒 0 ⇒ 一个桶都不会建，宿主行为完全不变。
    static_cast<void>(key);
    static_cast<void>(startTick);
#endif
}

// ============================================================================
// Lua 采样剖析器（批次 089）
// ============================================================================
//
// 见 `runtime_profiler.hpp` 的说明。这里只放三件事：**钩子本体**、**挂钩子**、**清桶**。
//
// 钩子纪律（写在这里提醒后来人）：
//   * 钩子里**不许分配内存**、不许调可能分配或抛错的 Lua API —— 它每 N 条指令就跑一次，
//     一旦出错或被分配拖慢，整个模组的每一帧都跟着慢；
//   * `lua_getinfo(state, "nSl", ar)` 只往调用方传进来的那个 `lua_Debug` 里拷，
//     不分配、不碰栈 —— 这是唯一允许的调用；
//   * 桶满只加溢出计数，**不覆盖已有样本**（覆盖会让"最热的那个函数"被后来者顶掉）。
namespace {

struct ProfileHookText {
    char name[32];
    char source[64];
};

//: 从钩子给的那一帧里取"函数名 + 短文件名"；无名函数合成一个 `<匿名 @行>` 名字。
void ReadProfileFrameText(lua_State* state, lua_Debug* debug, ProfileHookText* out) noexcept {
    out->name[0] = '\0';
    out->source[0] = '\0';
    if (debug == nullptr) {
        return;
    }
    lua_getinfo(state, "nSl", debug);
    // `short_src` 是定长数组（不是指针）⇒ 直接拷，不要写 `!= nullptr` 的判空（`-Werror=address`）。
    // 用"保留结尾"的拷贝：路径开头都是 `rom:/isaac_mods/mods/`，从开头截会让不同文件撞名
    // （第一次真机就撞了：两个不同文件的桶显示成同一串）。
    isaac::runtime::ProfileCopyTextTail(out->source, sizeof(out->source), debug->short_src);
    if (debug->name != nullptr && debug->name[0] != '\0') {
        isaac::runtime::ProfileCopyText(out->name, sizeof(out->name), debug->name);
        return;
    }
    // 无名函数（匿名闭包 / 主体代码 / 尾调用）：**只按"种类"合成一个名字**。
    //
    // ★ 2026-09-20 第一次真机撞的坑：这里原本按 `种类#行号` 合成（`main#105`、`main#304`…），
    // 结果**一个文件的主体代码每行就吃一个桶** —— 128 个桶瞬间被"只命中一次"的条目占满，
    // 真正热的函数全部溢出（实测 128/128 占满、5,136 次溢出）。按种类合并之后，
    // 一个 Lua 函数/主体只占一个桶。
    const char* what = debug->what != nullptr ? debug->what : "?";
    std::size_t length = 0;
    while (what[length] != '\0' && length + 3 < sizeof(out->name)) {
        out->name[length] = what[length];
        ++length;
    }
    if (length + 2 < sizeof(out->name)) {
        out->name[length++] = '#';
        out->name[length++] = '<';
        out->name[length++] = '>';
    }
    out->name[length] = '\0';
}

} // namespace

//: 采样桶是否已经"进入游戏后清过一次"（见 `Invoke` 里的说明）。
bool g_ProfileSessionStarted = false;

extern "C" void IsaacRuntime_ProfileHook(lua_State* state, lua_Debug* debug) {
    ProfileHookText text{};
    ReadProfileFrameText(state, debug, &text);
    g_RuntimePerfProfileSamples += 1;
    static_cast<void>(isaac::runtime::RecordRuntimePerfProfileSample(
        g_RuntimePerfProfileBuckets, isaac::runtime::kRuntimePerfProfileBucketCount,
        text.source, text.name, debug != nullptr ? debug->currentline : 0,
        &g_RuntimePerfProfileOverflow));
}

void ResetRuntimePerfProfile() noexcept {
    for (auto& bucket : g_RuntimePerfProfileBuckets) {
        bucket = isaac::runtime::RuntimePerfProfileBucket{};
    }
    g_RuntimePerfProfileSamples = 0;
    g_RuntimePerfProfileOverflow = 0;
}


// ============================================================================
// 会计数的 Lua 分配器（批次 091）
// ============================================================================
//
// Lua 的默认分配器就是 `l_alloc`：`nsize == 0 ? free : realloc`。这里只多记四个计数
// （调用次数 / 请求字节 / 新建次数 / 释放次数），**行为与默认分配器逐字相同**。
//
// 为什么不用"停掉 GC 做 A/B"来判断：停 GC 会让堆无限长（我们模块的假堆只有 32 MiB，
// 而 EID 每帧都在造对象）⇒ 有把游戏撑爆的风险。**计数是零风险的**：它不改任何行为。
extern "C" void* IsaacRuntime_CountingAlloc(void* userData, void* block, std::size_t oldSize,
                                           std::size_t newSize) {
    static_cast<void>(userData);
    static_cast<void>(oldSize);   // 与默认分配器一致：不依赖旧长度
    if (newSize == 0) {
        g_RuntimePerfFreeCalls += 1;
        std::free(block);
        return nullptr;
    }
    g_RuntimePerfAllocCalls += 1;
    g_RuntimePerfAllocBytes += newSize;
    if (block == nullptr) {
        g_RuntimePerfAllocNewCalls += 1;
    }
    return std::realloc(block, newSize);
}


// ============================================================================
// 地板基准（批次 095）：量"一次纯 Lua→C 调用"本身要多少时间
// ============================================================================
//
// **为什么需要**：真机实测每次接口调用平均 1.40 µs（每帧 646 次）。要回答
// "还能压到多低"，必须先知道**地板**：Lua 调用一个 C 函数（建帧 + 返回）本身要多久 ——
// 处理器里什么都不做也躲不掉的那部分。做法：注册一个立刻返回的空函数，
// 在同一个 Lua 状态里连调 N 次并计时，把结果记进两个全局（读数工具会打印）。
//
// 只在设备构建里跑（宿主上 `RuntimePerfTick()` 恒 0），且只在状态创建时跑一次。
#if defined(ISAAC_RUNTIME_PERF_TIMING)
namespace {
int EmptyProbeHandler(lua_State* state) {
    static_cast<void>(state);
    return 0;
}
} // namespace
#endif

void MeasureEmptyCallCost(lua_State* state) noexcept {
#if defined(ISAAC_RUNTIME_PERF_TIMING)
    constexpr std::uint32_t kIterations = 20000;
    lua_pushcfunction(state, &EmptyProbeHandler);
    const int base = lua_gettop(state);
    const std::uint64_t startedAt = isaac::runtime::RuntimePerfTick();
    for (std::uint32_t index = 0; index < kIterations; ++index) {
        lua_pushvalue(state, base);
        lua_call(state, 0, 0);
    }
    const std::uint64_t endedAt = isaac::runtime::RuntimePerfTick();
    lua_pop(state, 1);
    g_RuntimePerfEmptyCallCount = kIterations;
    // ★ 存**总 tick**，由读数端去算"单次多少"：单次不足 1 tick（52 ns）时整除会直接变成 0
    //   （第一版就是这么把结果吃成 0 的 —— 20,000 次空调用总共才几万个 tick）。
    g_RuntimePerfEmptyCallTicks = endedAt > startedAt ? (endedAt - startedAt) : 0;
#else
    static_cast<void>(state);
#endif
}

namespace LuaRuntime {

namespace {

constexpr char kModMethodsField[] = "__methods";
// PC 契约里 `MC_POST_UPDATE` 是 1（0 是 `MC_NPC_UPDATE`）。2026-09-12 起 Lua 侧的
// `ModCallbacks` 表由 `pc_lua_enum_data.cpp` 生成（非 stage13 构建直接用生成表），
// 所以这里的常量只在 stage13 诊断路径与派发查询里还有引用；`[[maybe_unused]]`
// 是为了不在 `-Werror` 下因某个构建配置未引用而失败。
[[maybe_unused]] constexpr int kPostUpdateCallback = 1;
// The Stage13 diagnostic build exposes only MC_POST_UPDATE, so these two are
// deliberately unused there; the attribute keeps the shared table complete
// without weakening the -Werror build.
[[maybe_unused]] constexpr int kPostRenderCallback = 2;
[[maybe_unused]] constexpr int kInputActionCallback = 13;
[[maybe_unused]] constexpr int kPreGetCollectibleCallback = 62;
#if !defined(EXL_DIAGNOSTIC_STAGE) || EXL_DIAGNOSTIC_STAGE == 13
#if defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 13
constexpr int kStage13PostUpdateCallback = kStage13CallbackValue;
#endif
constexpr std::size_t kStage13RequireMaximumDepth = 8;
constexpr std::size_t kStage13ModRootCapacity = 1024;
constexpr std::size_t kStage13RequirePathCapacity = 1536;
constexpr char kStage13ModRootPrefix[] = "rom:/isaac_mods/mods/";
#endif

struct LuaIntegerConstant {
    const char* name;
    lua_Integer value;
};

constexpr std::array<LuaIntegerConstant, 28> kButtonActionConstants{{
    {"ACTION_LEFT", 0}, {"ACTION_RIGHT", 1}, {"ACTION_UP", 2}, {"ACTION_DOWN", 3},
    {"ACTION_SHOOTLEFT", 4}, {"ACTION_SHOOTRIGHT", 5}, {"ACTION_SHOOTUP", 6},
    {"ACTION_SHOOTDOWN", 7}, {"ACTION_BOMB", 8}, {"ACTION_ITEM", 9},
    {"ACTION_PILLCARD", 10}, {"ACTION_DROP", 11}, {"ACTION_PAUSE", 12},
    {"ACTION_MAP", 13}, {"ACTION_MENUCONFIRM", 14}, {"ACTION_MENUBACK", 15},
    {"ACTION_RESTART", 16}, {"ACTION_FULLSCREEN", 17}, {"ACTION_MUTE", 18},
    {"ACTION_JOINMULTIPLAYER", 19}, {"ACTION_MENULEFT", 20}, {"ACTION_MENURIGHT", 21},
    {"ACTION_MENUUP", 22}, {"ACTION_MENUDOWN", 23}, {"ACTION_MENULT", 24},
    {"ACTION_MENURT", 25}, {"ACTION_MENUTAB", 26}, {"ACTION_CONSOLE", 28},
}};

constexpr std::array<LuaIntegerConstant, 120> kKeyboardConstants{{
    {"KEY_SPACE", 32}, {"KEY_APOSTROPHE", 39}, {"KEY_COMMA", 44}, {"KEY_MINUS", 45},
    {"KEY_PERIOD", 46}, {"KEY_SLASH", 47}, {"KEY_0", 48}, {"KEY_1", 49}, {"KEY_2", 50},
    {"KEY_3", 51}, {"KEY_4", 52}, {"KEY_5", 53}, {"KEY_6", 54}, {"KEY_7", 55},
    {"KEY_8", 56}, {"KEY_9", 57}, {"KEY_SEMICOLON", 59}, {"KEY_EQUAL", 61},
    {"KEY_A", 65}, {"KEY_B", 66}, {"KEY_C", 67}, {"KEY_D", 68}, {"KEY_E", 69},
    {"KEY_F", 70}, {"KEY_G", 71}, {"KEY_H", 72}, {"KEY_I", 73}, {"KEY_J", 74},
    {"KEY_K", 75}, {"KEY_L", 76}, {"KEY_M", 77}, {"KEY_N", 78}, {"KEY_O", 79},
    {"KEY_P", 80}, {"KEY_Q", 81}, {"KEY_R", 82}, {"KEY_S", 83}, {"KEY_T", 84},
    {"KEY_U", 85}, {"KEY_V", 86}, {"KEY_W", 87}, {"KEY_X", 88}, {"KEY_Y", 89},
    {"KEY_Z", 90}, {"KEY_LEFT_BRACKET", 91}, {"KEY_BACKSLASH", 92},
    {"KEY_RIGHT_BRACKET", 93}, {"KEY_GRAVE_ACCENT", 96}, {"KEY_WORLD_1", 161},
    {"KEY_WORLD_2", 162}, {"KEY_ESCAPE", 256}, {"KEY_ENTER", 257}, {"KEY_TAB", 258},
    {"KEY_BACKSPACE", 259}, {"KEY_INSERT", 260}, {"KEY_DELETE", 261}, {"KEY_RIGHT", 262},
    {"KEY_LEFT", 263}, {"KEY_DOWN", 264}, {"KEY_UP", 265}, {"KEY_PAGE_UP", 266},
    {"KEY_PAGE_DOWN", 267}, {"KEY_HOME", 268}, {"KEY_END", 269}, {"KEY_CAPS_LOCK", 280},
    {"KEY_SCROLL_LOCK", 281}, {"KEY_NUM_LOCK", 282}, {"KEY_PRINT_SCREEN", 283},
    {"KEY_PAUSE", 284}, {"KEY_F1", 290}, {"KEY_F2", 291}, {"KEY_F3", 292},
    {"KEY_F4", 293}, {"KEY_F5", 294}, {"KEY_F6", 295}, {"KEY_F7", 296},
    {"KEY_F8", 297}, {"KEY_F9", 298}, {"KEY_F10", 299}, {"KEY_F11", 300},
    {"KEY_F12", 301}, {"KEY_F13", 302}, {"KEY_F14", 303}, {"KEY_F15", 304},
    {"KEY_F16", 305}, {"KEY_F17", 306}, {"KEY_F18", 307}, {"KEY_F19", 308},
    {"KEY_F20", 309}, {"KEY_F21", 310}, {"KEY_F22", 311}, {"KEY_F23", 312},
    {"KEY_F24", 313}, {"KEY_F25", 314}, {"KEY_KP_0", 320}, {"KEY_KP_1", 321},
    {"KEY_KP_2", 322}, {"KEY_KP_3", 323}, {"KEY_KP_4", 324}, {"KEY_KP_5", 325},
    {"KEY_KP_6", 326}, {"KEY_KP_7", 327}, {"KEY_KP_8", 328}, {"KEY_KP_9", 329},
    {"KEY_KP_DECIMAL", 330}, {"KEY_KP_DIVIDE", 331}, {"KEY_KP_MULTIPLY", 332},
    {"KEY_KP_SUBTRACT", 333}, {"KEY_KP_ADD", 334}, {"KEY_KP_ENTER", 335},
    {"KEY_KP_EQUAL", 336}, {"KEY_LEFT_SHIFT", 340}, {"KEY_LEFT_CONTROL", 341},
    {"KEY_LEFT_ALT", 342}, {"KEY_LEFT_SUPER", 343}, {"KEY_RIGHT_SHIFT", 344},
    {"KEY_RIGHT_CONTROL", 345}, {"KEY_RIGHT_ALT", 346}, {"KEY_RIGHT_SUPER", 347},
    {"KEY_MENU", 348},
}};

lua_State* g_LuaState = nullptr;
// One registry owns every registered callback, so several Mods can register the
// same phase and dispatch order is deterministic. Probe and production builds
// share it; the legacy per-phase single slots were deleted with the migration.
isaac::runtime::CallbackRegistry g_CallbackRegistry;
// 既有的兼容常量：**没有**自己的 Mod 对象的调用方（内嵌测试脚本、诊断阶段 13）用它当 owner。
// 多模组加载（2026-09-16）之后，真正的 Mod 各自拿一个独立句柄，见 `NextModOwner()`。
constexpr isaac::runtime::ModHandle kRuntimeOwner{1, 1};
// `g_ModRegistered`：至少登记过一个 Mod 的 1 字节量。
//
// 多模组加载（2026-09-16）之后它**只被写、模块内部没人读** —— 读者在模块外面：
// 设备侧的读数工具（`tools/read_device_state_via_gdb.py` 的符号表）与错误通道探针直接按
// 这个名字读 bss 里的那个字节，用来判断"Lua 到底有没有跑到 `RegisterMod`"。
//
// ★ `[[gnu::used]]` 是**必须的**：写而不读的静态全局会被优化掉，符号一没，真机读数就永远
// 显示"模组没登记"，而游戏其实一切正常（这是最坏的一类误判：把人引去查完全不存在的问题）。
// 本项目已有同样用法（`saltynx_symbol_resolver.cpp` 的 `g_find_symbol`）。
[[gnu::used]] bool g_ModRegistered = false;
// 已经登记了几个 Mod（多模组加载的验收量：真机上"清单里 2 个 Mod，登记数也必须是 2"）。
std::atomic<u32> g_ModRegisteredCount{0};

// owner 句柄的分配器：index 从 2 起（1 留给 `kRuntimeOwner`），generation 恒 1
// （本运行时不做"槽位复用"，一个 Mod 一辈子一个句柄）。
std::atomic<u32> g_NextModOwnerIndex{2};

isaac::runtime::ModHandle NextModOwner() noexcept {
    const u32 index = g_NextModOwnerIndex.fetch_add(1, std::memory_order_relaxed);
    return isaac::runtime::ModHandle{static_cast<std::uint16_t>(index), 1};
}

// `ModHandle::ownerPacked` 的打包/解包（低 16 位 index、高 16 位 generation）。
// 打包只为了不让 `lua_runtime_state.hpp` 依赖 domain 头（见那个字段的注释）。
u32 PackModOwner(isaac::runtime::ModHandle handle) noexcept {
    return static_cast<u32>(handle.index) | (static_cast<u32>(handle.generation) << 16);
}
std::atomic<u32> g_Ready{false};
std::atomic<u32> g_CallbackError{false};
std::atomic<u32> g_InManagedCallbackDispatch{false};

// --- 最近一次 Lua 错误信息 ------------------------------------------------
//
// 真机上文件写入通道多轮无产物，错误信息只能走“装进诊断字、随探针报错进崩溃报告”
// 这条路。这里保留最近一次失败信息的前 256 字节，诊断出口只吐前 8 字节 + 长度。
std::array<char, 256> g_LastLuaErrorText{};
std::atomic<std::uint32_t> g_LastLuaErrorLength{0};

// --- 最近若干条 Lua 错误（环形历史，2026-09-19 批次 052 新增） ----------------------
//
// ★ 为什么加：只有一个槽的时候，**A 模组的错会盖掉 B 模组的错**。2026-09-19 实测代价 ——
// GoodTrip 的错先被 EID 的错盖住，读数里只剩 EID 那条，于是我在"到底是哪个模组坏了"上
// 兜了三轮；而且每次都要"干净重启 + 不碰某个键"才抢得到那个槽。
// 这不是 PC 语义（PC 没有这个设施），是我们**自己的观测层**在制造耦合。
//
// 语义：`g_LastLuaErrorText` 仍是"**最后一条**"（读数工具与既有门禁的口径**不变**）；
// 这里额外保留最近 `kLuaErrorHistorySlots` 条，每条 NUL 结尾、供调试桩按符号整块读回。
constexpr std::size_t kLuaErrorHistorySlots = 8;
constexpr std::size_t kLuaErrorHistoryEntryBytes = 128;
//: 每条 = `text[120]` + `owner` + `callbackId`（末尾 8 字节放归属，**文本仍在开头** ——
//: 这样既有的"按 128 字节切片、取到第一个 NUL 为止"的读取方式继续成立）。
constexpr std::size_t kLuaErrorHistoryTextBytes = kLuaErrorHistoryEntryBytes - 8;

struct LuaErrorHistoryEntry {
    char text[kLuaErrorHistoryTextBytes];
    std::uint32_t owner;       //: 哪个模组（`ModHandle`）；0 = 不知道
    std::uint32_t callbackId;  //: 哪条回调；`kNoCallbackDispatched` = 不是回调路径（加载期等）
};

static_assert(sizeof(LuaErrorHistoryEntry) == kLuaErrorHistoryEntryBytes,
              "环形历史每条必须正好 128 字节（读数工具按这个步长解码）");

std::array<LuaErrorHistoryEntry, kLuaErrorHistorySlots> g_LuaErrorHistory{};
std::atomic<std::uint32_t> g_LuaErrorHistoryCount{0};

//: 当前正在执行的回调的归属（派发器在调用每个回调前后设置/复原）。
//: 有了它，"是谁报的错"不再需要靠猜或靠探针 —— 直接盖在错误记录上。
std::uint32_t g_ErrorContextOwner = 0;
std::uint32_t g_ErrorContextCallbackId = isaac::runtime::kNoCallbackDispatched;

void RecordLuaErrorHistory(const char* text, std::size_t length) noexcept {
    if (text == nullptr || length == 0) {
        return;
    }
    const std::size_t copyLength =
        length < kLuaErrorHistoryTextBytes - 1 ? length : kLuaErrorHistoryTextBytes - 1;
    // ★ 去重（2026-09-19 批次 068）：**同一个模组的同一条错误只占一格**。
    // 为什么必须去重：真机上遇到过 EID 一条"每帧都报"的错把 8 格全部刷满，
    // 于是 GoodTrip 的错**一条都进不来**，"到底是谁坏了"又得靠探针。
    const std::uint32_t owner = g_ErrorContextOwner;
    const std::uint32_t callbackId = g_ErrorContextCallbackId;
    for (std::size_t slot = 0; slot < kLuaErrorHistorySlots; ++slot) {
        const LuaErrorHistoryEntry& existing = g_LuaErrorHistory[slot];
        if (existing.owner != owner || existing.text[0] == '\0') {
            continue;
        }
        if (std::strncmp(existing.text, text, copyLength) == 0 &&
            existing.text[copyLength] == '\0') {
            // 已经在历史里：**不推进写游标**，也不覆盖别人的格子。
            return;
        }
    }
    const std::uint32_t count = g_LuaErrorHistoryCount.load(std::memory_order_acquire);
    const std::size_t slot = count % kLuaErrorHistorySlots;
    LuaErrorHistoryEntry& entry = g_LuaErrorHistory[slot];
    std::memcpy(entry.text, text, copyLength);
    entry.text[copyLength] = '\0';
    entry.owner = owner;
    entry.callbackId = callbackId;
    g_LuaErrorHistoryCount.store(count + 1, std::memory_order_release);
}

// 记录栈顶的错误值。**对非字符串错误值也能记录**（2026-09-12 第七轮）。
//
// 旧实现只认 `lua_tolstring` 成功的情形：Lua 允许 `error(任意值)`，一旦错误值不是字符串
// （表/函数/userdata/自定义对象——引擎自己的绑定层就这么抛），它**什么都不记**，
// 于是 `errorLength` 与内容长期不一致，报告里读到的是上一条消息的残渣。
// 真机连续性证据：`errorLength = 1`，而负载里读出 `"AKP2"`（上一次探针负载的残片）。
//
// 现在：非字符串时用 `luaL_tolstring`（接受任意值、保证产出字符串、自己压栈），
// 记完把栈复原 —— 调用方原本就打算 `lua_pop(state, 1)` 弹掉错误值，所以这里必须弹干净。
void CaptureLuaErrorTop(lua_State* state) {
    if (state == nullptr || lua_gettop(state) == 0) {
        return;
    }
    std::size_t length = 0;
    if (const char* message = lua_tolstring(state, -1, &length); message != nullptr) {
        if (length == 0) {
            return;
        }
        if (length > g_LastLuaErrorText.size()) {
            length = g_LastLuaErrorText.size();
        }
        std::memcpy(g_LastLuaErrorText.data(), message, length);
        g_LastLuaErrorLength.store(static_cast<std::uint32_t>(length),
                                  std::memory_order_release);
        RecordLuaErrorHistory(message, length);
        return;
    }
    // 非字符串：转成可读文本（表会走 `__tostring` 或类型名）。
    const int topBefore = lua_gettop(state);
    const char* text = luaL_tolstring(state, -1, nullptr);
    if (text != nullptr) {
        const std::size_t textLength = std::strlen(text);
        if (textLength != 0) {
            const std::size_t copyLength = textLength < g_LastLuaErrorText.size()
                                               ? textLength
                                               : g_LastLuaErrorText.size();
            std::memcpy(g_LastLuaErrorText.data(), text, copyLength);
            g_LastLuaErrorLength.store(static_cast<std::uint32_t>(copyLength),
                                       std::memory_order_release);
            RecordLuaErrorHistory(text, copyLength);
        }
    }
    lua_settop(state, topBefore);  // 弹掉 `luaL_tolstring` 压入的字符串
}
#if defined(EXL_PERSISTENCE_TRACE) || defined(EXL_PERSISTENCE_EVENT_DIAGNOSTIC)
std::atomic<u8> g_CallbackOperation{static_cast<u8>(CallbackOperation::None)};
std::atomic<u64> g_CallbackFailureDetail{0};

u64 CallbackErrorTail(lua_State* state) {
    if (state == nullptr || lua_type(state, -1) != LUA_TSTRING) {
        return 0;
    }
    std::size_t length = 0;
    const char* error = lua_tolstring(state, -1, &length);
    constexpr std::size_t kMaximumTailLength = 6;
    const std::size_t tailLength = length > kMaximumTailLength ? kMaximumTailLength : length;
    u64 tail = 0;
    if (error != nullptr) {
        for (std::size_t index = length - tailLength; index < length; ++index) {
            tail = (tail << 8) | static_cast<unsigned char>(error[index]);
        }
    }
    return tail;
}
#endif
// Re-entrancy guard for the PreGetCollectible relay dispatch.
//
// NOT `thread_local`. This is an injected module, and a `thread_local` here cost a
// hardware crash: reading it on the game's MainThread calls `__aarch64_read_tp()`,
// which is `mrs x0, tpidrro_el0 ; ldr x0, [x0, #504]` -- 0 for this module -- and the
// very next instruction dereferences that null (`ldrb w0, [x0, x0]`). Crash report
// `01789099948`: Result 0x4A8 (Data Abort), fault address 0x0, PC = runtime+0x440c,
// reached from `Entity_Pickup::Init` through the PreGetCollectible relay, i.e. as soon
// as a room spawns a pickup. It was the only TLS access in the whole module.
//
// The dispatch only ever happens on the game thread, and its sibling
// `g_InManagedCallbackDispatch` below is an ordinary global, so a plain global is both
// equivalent here and consistent with the rest of the file.
bool g_InPreGetCollectibleDispatch = false;
std::atomic<uintptr_t> g_CurrentCallbackManager{0};
std::atomic<u32> g_PostUpdateCount{0};
#if defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 15
std::atomic<u32> g_PostRenderCount{0};
std::atomic<u32> g_PostRenderPausedCount{0};
#endif
#if defined(EXL_DIAGNOSTIC_STAGE) && (EXL_DIAGNOSTIC_STAGE == 16 || EXL_DIAGNOSTIC_STAGE == 17)
std::atomic<u32> g_MusicDiagnosticCycleCompleted{false};
#endif
#if defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 45
std::atomic<u32> g_MusicDiagnosticCurrentIdReady{false};
std::atomic<u32> g_MusicDiagnosticCurrentId{0};
#endif
std::atomic<u32> g_PreparationStep{0};
std::atomic<u32> g_PreparationStatus{0};
// 游戏本体 NRO 的加载基址（批次 2）：`Isaac.GetPlayer` 的指针链与 `Entity_Player` 的 vptr
// 判据都要用它，所以由 Hook 安装阶段在已拿到 `TargetModule::base` 的地方发布。
std::atomic<uintptr_t> g_EngineModuleBase{0};
std::atomic<uintptr_t> g_GameOwnerSlot{0};
std::atomic<uintptr_t> g_GameIsPausedThunk{0};
std::atomic<uintptr_t> g_GameIsGreedMode{0};
std::atomic<uintptr_t> g_LevelIsAscent{0};
// 批次 8（2026-09-15）：`Level:GetAbsoluteStage()` / `Level:IsNextStageAvailable()` 的入口地址。
std::atomic<uintptr_t> g_LevelGetAbsoluteStage{0};
std::atomic<uintptr_t> g_LevelIsNextStageAvailable{0};
// 2026-09-16：`Room:GetFrameCount()`（`Room::GetFrameCount @ 0x470B0C`）的入口地址。
std::atomic<uintptr_t> g_RoomGetFrameCount{0};
// 2026-09-21：`GridEntity::GetPosition() const @ 0x37E498`（PC 的 `GridEntity.Position`）。
// "可选能力"：为 0 时 handler 报"绑定不可用"并让那次读取失败，**绝不编造坐标**
// （编了会让 EID 挑到错误的网格实体 —— 而 EID 正是靠它算"离玩家最近的刺"）。
std::atomic<uintptr_t> g_GridEntityGetPosition{0};
std::atomic<uintptr_t> g_ItemPoolGetCollectible{0};
// 批次 10（2026-09-15）：`Room:WorldToScreenPosition()` 要调的引擎函数（PLT 桩地址）。
std::atomic<uintptr_t> g_GetRenderPosition{0};
// 宿主注入：设备侧走"校验 16 字节入口 + 调用"那条路，宿主上没有引擎映像，用注入的实现替代。
// 与 `HasCollectible` 的宿主钩子同一形态（`#if !defined(__SWITCH__)` 才存在）。
#if !defined(__SWITCH__)
RenderPositionHostFunction g_GetRenderPositionHost{nullptr};
// 2026-09-16：`Room:GetFrameCount()` 的宿主替身（设备构建里这段被 `#if` 排除）。
RoomFrameCountHostFunction g_RoomGetFrameCountHost{nullptr};
// 2026-09-21：`GridEntity.Position` 的宿主替身（同上，设备构建里走"校验入口 + 调引擎"）。
GridEntityPositionHostFunction g_GridEntityGetPositionHost{nullptr};
#endif
std::atomic<uintptr_t> g_MusicGetCurrentMusicId{0};
std::atomic<uintptr_t> g_MusicPause{0};
std::atomic<uintptr_t> g_MusicResume{0};
std::atomic<uintptr_t> g_RngSetSeed{0};
std::atomic<uintptr_t> g_RngNext{0};
std::atomic<uintptr_t> g_InputIsActionPressed{0};
std::atomic<uintptr_t> g_InputIsActionTriggered{0};
std::atomic<uintptr_t> g_InputGetActionValue{0};
// Font entry points (`KAGE::Graphics::Font`). The Font object these are called on is allocated
// and released by the `Font` family unit, not by the game.
std::atomic<uintptr_t> g_FontCtor{0};
std::atomic<uintptr_t> g_FontDestructor{0};
std::atomic<uintptr_t> g_FontLoad{0};
std::atomic<uintptr_t> g_FontUnload{0};
std::atomic<uintptr_t> g_FontIsLoaded{0};
std::atomic<uintptr_t> g_FontGetStringWidth{0};
std::atomic<uintptr_t> g_FontGetStringWidthUTF8{0};
std::atomic<uintptr_t> g_FontGetLineHeight{0};
std::atomic<uintptr_t> g_FontGetBaselineHeight{0};
std::atomic<uintptr_t> g_FontGetCharacterWidth{0};
std::atomic<uintptr_t> g_FontSetMissingCharacter{0};
std::atomic<uintptr_t> g_FontDrawString{0};
std::atomic<uintptr_t> g_FontDrawStringScaled{0};
std::atomic<uintptr_t> g_FontDrawStringUTF8{0};
std::atomic<uintptr_t> g_FontDrawStringScaledUTF8{0};
std::atomic<uintptr_t> g_SpriteCtor{0};
std::atomic<uintptr_t> g_SpriteDestructor{0};
std::atomic<uintptr_t> g_SpritePlay{0};
std::atomic<uintptr_t> g_SpriteSetAnimation{0};
std::atomic<uintptr_t> g_SpriteSetFrameNamed{0};
std::atomic<uintptr_t> g_SpriteSetFrame{0};
std::atomic<uintptr_t> g_SpriteGetFrame{0};
std::atomic<uintptr_t> g_SpriteSetLayerFrame{0};
std::atomic<uintptr_t> g_SpriteGetLayerFrame{0};
std::atomic<uintptr_t> g_SpriteGetTexel{0};
std::atomic<uintptr_t> g_SpriteUpdate{0};
std::atomic<uintptr_t> g_SpriteIsPlaying{0};
std::atomic<uintptr_t> g_SpriteIsFinished{0};
std::atomic<uintptr_t> g_SpriteRender{0};
std::atomic<uintptr_t> g_SpriteRenderLayer{0};
std::atomic<uintptr_t> g_SpritePlayRandom{0};
std::atomic<uintptr_t> g_SpriteLoad{0};
std::atomic<uintptr_t> g_SpriteLoadGraphics{0};
std::atomic<uintptr_t> g_SpriteReplaceSpritesheet{0};
std::atomic<uintptr_t> g_LibcxxStringAssign{0};
std::atomic<uintptr_t> g_GameOperatorDelete{0};
#if !defined(EXL_DIAGNOSTIC_STAGE) || EXL_DIAGNOSTIC_STAGE == 13
GameFileReader::Bindings g_Stage13Bindings{};
std::array<char, kStage13ModRootCapacity> g_Stage13ModRoot{};
std::array<char, kRomfsModScriptMaximumLength> g_Stage13RequireSource{};
std::size_t g_Stage13ModRootLength = 0;
std::size_t g_Stage13RequireDepth = 0;
int g_RequireCacheRef = LUA_NOREF;
int g_ModObjectRef = LUA_NOREF;
bool g_Stage13Mode = false;
// `require` 是否可用：由 `SetStage13Context` 置位（生产与 stage13 都经过它）。
bool g_RequireAvailable = false;
std::atomic<u32> g_RequireFailureDetail{0};
std::atomic<u64> g_RequireErrorTail{0};
#endif

// `require` 失败的快照量（第一次/最后一次的代码与模块名、总次数）。
//
// **刻意放在上面那个守卫之外**：`RequireFailureSnapshot()` 定义在通用区（探针在所有构建里都调它），
// 而这些量原先写在 `#if !defined(EXL_DIAGNOSTIC_STAGE) || EXL_DIAGNOSTIC_STAGE == 13` 里，
// 于是 stage7/12 这类诊断构建编译 `RequireFailureSnapshot` 时它们"未声明"（宿主 harness 直接编不过）。
std::atomic<u32> g_RequireFirstFailureCode{0};
std::atomic<u64> g_RequireFirstFailureName{0};
std::atomic<u32> g_RequireLastFailureCode{0};
std::atomic<u64> g_RequireLastFailureName{0};
std::atomic<u32> g_RequireFailureTotal{0};

#if !defined(EXL_DIAGNOSTIC_STAGE) || EXL_DIAGNOSTIC_STAGE == 13
// 当前正在处理的模块名（`Require` 一拿到名字就填），供失败记录打包成 8 字节进诊断。
// 为什么需要"名字"：真机报告 `01789202186` 只告诉我们 `eid_mcm.lua:81` 的
// `EID.descriptions[lang]` 是 nil，而**哪一个** `require` 失败、失败在哪一类
// （名字被拒 19 / 打不开 20 / 读失败 21 / 编译失败 22）完全看不到 —— 而这些失败被 EID 的
// `pcall` 静默吞掉（它只在自己认为"文件不存在"时放过，其余只写一条看不见的日志）。
std::array<char, 64> g_RequireCurrentModule{};
std::size_t g_RequireCurrentModuleLength = 0;
u64 PackModuleNameHead() {
    u64 head = 0;
    const std::size_t length =
        g_RequireCurrentModuleLength < sizeof(head) ? g_RequireCurrentModuleLength : sizeof(head);
    std::memcpy(&head, g_RequireCurrentModule.data(), length);
    return head;
}

void SetRequireCurrentModule(const char* name, std::size_t length) {
    g_RequireCurrentModule.fill('\0');
    if (name == nullptr) {
        g_RequireCurrentModuleLength = 0;
        return;
    }
    const std::size_t limit = g_RequireCurrentModule.size() - 1;
    const std::size_t copy = length < limit ? length : limit;
    std::memcpy(g_RequireCurrentModule.data(), name, copy);
    g_RequireCurrentModuleLength = copy;
}

void RecordRequireFailure(u32 detail) {
    const u64 nameHead = PackModuleNameHead();
    u32 expected = 0;
    if (g_RequireFailureDetail.compare_exchange_strong(expected, detail, std::memory_order_release,
                                                       std::memory_order_relaxed)) {
        // 第一次失败：把名字与代码一起留下（第一次失败才是"最先挡住 Mod 的那一个"）。
        g_RequireFirstFailureName.store(nameHead, std::memory_order_release);
        g_RequireFirstFailureCode.store(detail, std::memory_order_release);
    }
    g_RequireLastFailureName.store(nameHead, std::memory_order_release);
    g_RequireLastFailureCode.store(detail, std::memory_order_release);
    g_RequireFailureTotal.fetch_add(1, std::memory_order_acq_rel);
}

int RaiseRequireFailure(lua_State* state, u32 detail, const char* message) {
    RecordRequireFailure(detail);
    // `"%s"` 而不是直接当格式串：批次 3 起这条消息里会**拼进 Mod 自己给的模块名**
    // （PC 形状的 "no file '<路径>.lua'"），名字里出现 `%` 时直接当格式串是未定义行为。
    return luaL_error(state, "%s", message);
}

// PC 形状的 `require` 失败文本（批次 3）。
//
// 为什么必须长成这样：EID 的 `EID:GetCurrentModPath()`（`main.lua:147`）在**没有 debug 库**时
// 用 `require("")` 的失败文本反推自己的 mod 路径：
//
//   local _, err = pcall(require, "")
//   local _, basePathStart = string.find(err, "no file '", 1)     -- 第一条的结尾
//   local _, modPathStart  = string.find(err, "no file '", basePathStart)  -- 第二条的结尾
//   local modPathEnd = string.find(err, ".lua'", modPathStart)
//   modPath = string.sub(err, modPathStart+1, modPathEnd-1)
//
// 也就是"从**第二条** `no file '` 的单引号之后，取到下一个 `.lua'` 之前"。所以：
//   * 至少要有**两条** `no file '…lua'`（只有一条时第二次 `string.find` 返回 nil，
//     `string.sub` 直接报 "bad argument #3 to 'find' (number expected, got nil)"，
//     EID 的 `main.lua` 就断在那里 —— 这正是本批次要修的加载期硬阻断之一）；
//   * **本 Runtime 真正尝试的那条路径必须在第二条**，否则 EID 取到的是别的字符串。
//
// 因此文本固定为（`<rel>` = 模块名里的 `.` 换成 `/`）：
//
//   module '<名>' not found:
//   \tno file '<mod 根>/<rel>/init.lua'
//   \tno file '<mod 根>/<rel>.lua'
//
// `require("")` 时 `<rel>` 为空，第二条是 `<mod 根>/.lua`，EID 于是取到 `<mod 根>/`
// ——正是它要的"mod 目录 + 结尾斜杠"（它随后自己拼 `resources/font/...`）。
// 注意 EID 还会对结果做 `gsub(":/", ":\\")`，所以它最终拿到的是 `rom:\isaac_mods/...`；
// 这是 EID 自己为 Windows 写的转换，我们不改（真机能否被文件层接受见批次报告）。
//
// 名字里的 `'`、控制字符与 `%` 会破坏上面那个形状（也影响后面 `luaL_error` 的处理），
// 所以先做一遍替换。
std::size_t AppendRequireText(char* buffer, std::size_t capacity, std::size_t length,
                              const char* text, std::size_t textLength) {
    if (buffer == nullptr || capacity == 0 || text == nullptr) {
        return length;
    }
    for (std::size_t index = 0; index < textLength && length + 1 < capacity; ++index) {
        buffer[length++] = text[index];
    }
    buffer[length] = '\0';
    return length;
}

// 字面量的重载：长度由数组大小推出，避免手写长度时数错一个字节（读越界）。
template <std::size_t Size>
std::size_t AppendRequireText(char* buffer, std::size_t capacity, std::size_t length,
                              const char (&text)[Size]) {
    return AppendRequireText(buffer, capacity, length, text, Size - 1);
}

const char* BuildRequireNotFoundMessage(std::array<char, kStage13RequirePathCapacity * 2>* buffer,
                                        const char* modRoot, std::size_t modRootLength,
                                        const char* moduleName, std::size_t moduleLength) {
    if (buffer == nullptr) {
        return "module not found";
    }
    char* text = buffer->data();
    const std::size_t capacity = buffer->size();
    text[0] = '\0';
    std::size_t length = 0;
    length = AppendRequireText(text, capacity, length, "module '");
    for (std::size_t index = 0; index < moduleLength; ++index) {
        const unsigned char value = static_cast<unsigned char>(moduleName[index]);
        const char safe = (value >= 0x20 && value < 0x7F && value != '\'' && value != '%')
                              ? static_cast<char>(value)
                              : '?';
        length = AppendRequireText(text, capacity, length, &safe, 1);
    }
    length = AppendRequireText(text, capacity, length, "' not found:");
    for (int entry = 0; entry < 2; ++entry) {
        const bool directoryForm = entry == 0;
        std::size_t lineLength = AppendRequireText(text, capacity, length, "\n\tno file '");
        lineLength = AppendRequireText(text, capacity, lineLength, modRoot, modRootLength);
        // 根与模块名之间的分隔符：与 `Require` 真正拼路径时一样（`root + "/" + rel + ".lua"`）。
        // 少了它，空名（`require("")`）会拼成 `<根>.lua`，EID 提取出来的 mod 路径就没有结尾
        // 的斜杠，它随后拼 `resources/font/...` 会连成一个不存在的路径。
        lineLength = AppendRequireText(text, capacity, lineLength, "/");
        // 模块名逐字符翻译：`.` → `/`（与 `Require` 的成功路径同一条规则）。
        for (std::size_t index = 0; index < moduleLength; ++index) {
            const char translated = moduleName[index] == '.' ? '/' : moduleName[index];
            lineLength = AppendRequireText(text, capacity, lineLength, &translated, 1);
        }
        if (directoryForm) {
            lineLength = AppendRequireText(text, capacity, lineLength, "/init.lua'");
        } else {
            lineLength = AppendRequireText(text, capacity, lineLength, ".lua'");
        }
        length = lineLength;
    }
    return text;
}

u32 ClassifyRequireExecutionFailure(lua_State* state) {
    // 这里曾经把 "RegisterMod accepts exactly one Mod" 单独分类成失败码 26。
    // **2026-09-16（多模组加载）之后这一条不再存在**：每个 Mod 各自调用一次 `RegisterMod`
    // 是常态，`require` 出来的模块里再登记一个 Mod 也合法 —— 所以所有执行期失败一律记 27
    // （"其它执行失败"），并把内层错误文本原样抛出去（调用方的 `errorTail` 仍然拿得到尾部）。
    // 设备侧的解码表 `tools/decode_isaacerr_payload.py` 同步把 26 标成"已退役"。
    static_cast<void>(state);
    return 27;
}

void RecordRequireErrorTail(lua_State* state) {
    std::size_t errorLength = 0;
    const char* error = lua_tolstring(state, -1, &errorLength);
    u64 tail = 0;
    const std::size_t tailLength = errorLength > sizeof(tail) ? sizeof(tail) : errorLength;
    if (error != nullptr) {
        for (std::size_t index = errorLength - tailLength; index < errorLength; ++index) {
            tail = (tail << 8) | static_cast<unsigned char>(error[index]);
        }
    }
    g_RequireErrorTail.store(tail, std::memory_order_release);
}

// 模块名里允许哪些字符。
//
// 这里曾经是一张"字母数字 + `_` + `-` + `.`"的白名单，2026-09-12 真机报告 `01789201969`
// 证明那张白名单少了一个 `+`：
//   `EID:LoadLanguagePacks("ab+")` 会 `require("descriptions.ab+.en_us")`，
//   白名单把它判成"不安全的模块名" → 抛 PC 形状的 not-found → EID 的 `pcall` 把它
//   当"文件不存在"轻轻放过（只是不写警告）→ **ab+ 的 4 个语言包（`pt`/`bul`/`nl_nl`/`el_gr`）
//   永远没被加载**（它们只存在于 `descriptions/ab+/`，`rep/` 里没有）→
//   `EID.descriptions[lang]` 为 nil → `features/eid_mcm.lua:81` 直接崩：
//   "attempt to index a nil value (field '?')"。
//   EID 还用 `features.eid_xmldata_rep+`、`descriptions.rep+.*` 这些同样带 `+` 的名字。
//
// PC 的 `require` 只把 `.` 当层级分隔（换成 `/`），名字里其余字符一律按文件名原样使用。
// 所以这里改成"只挡路径分隔符与不可打印字符"：`..`（路径穿越）由调用点单独挡。
bool IsAsciiModuleCharacter(char value) {
    return value >= 0x20 && value < 0x7F && value != '/' && value != '\\';
}

bool SetStage13Context(const char* modRoot, const GameFileReader::Bindings& bindings) {
    if (modRoot == nullptr) {
        return false;
    }

    std::size_t length = 0;
    while (length < g_Stage13ModRoot.size() && modRoot[length] != '\0') {
        ++length;
    }
    constexpr std::size_t prefixLength = sizeof(kStage13ModRootPrefix) - 1;
    if (length == g_Stage13ModRoot.size() || length <= prefixLength ||
        std::memcmp(modRoot, kStage13ModRootPrefix, prefixLength) != 0) {
        return false;
    }
    const char* directory = modRoot + prefixLength;
    if ((length - prefixLength == 1 && directory[0] == '.') ||
        (length - prefixLength == 2 && directory[0] == '.' && directory[1] == '.')) {
        return false;
    }
    for (std::size_t index = prefixLength; index < length; ++index) {
        if (modRoot[index] == '/' || modRoot[index] == '\\') {
            return false;
        }
    }

    std::memcpy(g_Stage13ModRoot.data(), modRoot, length + 1);
    g_Stage13ModRootLength = length;
    g_Stage13Bindings = bindings;
    g_Stage13Mode = true;
    // 生产路径（清单 Mod 加载）也走这个函数设置 Mod 根目录与文件绑定，所以
    // `require` 从这里开始可用；stage13 只是同一套机制的另一个调用方。
    g_RequireAvailable = true;
    return true;
}

void ResetStage13Context() {
    g_Stage13Bindings = {};
    g_Stage13ModRoot.fill('\0');
    g_Stage13RequireSource.fill('\0');
    g_Stage13ModRootLength = 0;
    g_Stage13RequireDepth = 0;
    g_RequireCacheRef = LUA_NOREF;
    g_ModObjectRef = LUA_NOREF;
    g_Stage13Mode = false;
    g_RequireAvailable = false;
}

int Require(lua_State* state) {
    if (!g_RequireAvailable || lua_gettop(state) != 1 || lua_type(state, 1) != LUA_TSTRING) {
        return RaiseRequireFailure(state, 19, "invalid require module name");
    }

    std::size_t moduleLength = 0;
    const char* moduleName = lua_tolstring(state, 1, &moduleLength);
    // 先登记模块名：下面每一条失败路径（名字被拒 / 打不开 / 读失败 / 编译失败 / 执行失败）
    // 都要把"是谁"记进诊断，否则真机上只能看到"某个 require 挂了"。
    SetRequireCurrentModule(moduleName, moduleName != nullptr ? moduleLength : 0);
    // 失败文本要按 PC 的形状给出"尝试过的路径"（见 `BuildRequireNotFoundMessage`），
    // 所以先把这块缓冲准备好：模块名不安全/太长时同样要能拼出文本。
    std::array<char, kStage13RequirePathCapacity * 2> notFoundText{};
    const char* const notFound = BuildRequireNotFoundMessage(
        &notFoundText, g_Stage13ModRoot.data(), g_Stage13ModRootLength,
        moduleName != nullptr ? moduleName : "", moduleName != nullptr ? moduleLength : 0);
    if (moduleName == nullptr || moduleLength == 0 || moduleName[0] == '.' ||
        moduleName[moduleLength - 1] == '.' ||
        g_Stage13ModRootLength + moduleLength + 6 > kStage13RequirePathCapacity) {
        // `require("")` 就落在这里（EID 的 `EID:GetCurrentModPath()` 用的正是空名），
        // 所以这一条必须带 PC 形状的 "no file '…lua'" 文本。
        return RaiseRequireFailure(state, 19, notFound);
    }

    std::array<char, kStage13RequirePathCapacity> path{};
    std::memcpy(path.data(), g_Stage13ModRoot.data(), g_Stage13ModRootLength);
    std::size_t pathLength = g_Stage13ModRootLength;
    path[pathLength++] = '/';
    for (std::size_t index = 0; index < moduleLength; ++index) {
        if (!IsAsciiModuleCharacter(moduleName[index]) ||
            moduleName[index] == '/' || moduleName[index] == '\\' ||
            (moduleName[index] == '.' && index + 1 < moduleLength && moduleName[index + 1] == '.')) {
            return RaiseRequireFailure(state, 19, notFound);
        }
        path[pathLength++] = moduleName[index] == '.' ? '/' : moduleName[index];
    }
    std::memcpy(path.data() + pathLength, ".lua", 5);
    pathLength += 4;

    lua_rawgeti(state, LUA_REGISTRYINDEX, g_RequireCacheRef);
    const int cacheIndex = lua_gettop(state);
    lua_pushlstring(state, moduleName, moduleLength);
    lua_rawget(state, cacheIndex);
    if (!lua_isnil(state, -1)) {
        return 1;
    }
    lua_pop(state, 1);

    // 内建模块优先于磁盘查找：`json` 是运行时提供的（PC 引擎自带，Mod 无条件 require 它）。
    if (moduleLength == 4 && std::memcmp(moduleName, "json", 4) == 0) {
        lua_getglobal(state, "json");
        if (lua_istable(state, -1)) {
            lua_pushlstring(state, moduleName, moduleLength);
            lua_pushvalue(state, -2);
            lua_rawset(state, cacheIndex);
            return 1;
        }
        lua_pop(state, 1);
    }

    if (g_Stage13RequireDepth >= kStage13RequireMaximumDepth) {
        return RaiseRequireFailure(state, 19, "require nesting exceeds maximum depth");
    }
    ++g_Stage13RequireDepth;

    std::size_t length = 0;
    const auto readResult = GameFileReader::ReadTextFile(
        g_Stage13Bindings, path.data(), reinterpret_cast<u8*>(g_Stage13RequireSource.data()),
        g_Stage13RequireSource.size(), &length);
    if (readResult != GameFileReader::TextReadResult::Success) {
        --g_Stage13RequireDepth;
        if (readResult == GameFileReader::TextReadResult::OpenFailed) {
            // "文件不存在"同样是 PC 形状的 "no file '…lua'"（模块名已拼进文本里）。
            return RaiseRequireFailure(state, 20, notFound);
        }
        if (readResult == GameFileReader::TextReadResult::LengthOutOfRange) {
            // 与"读不出来"分开报：这是**缓冲区装不下**，PC 上不存在这种失败，所以文本必须能一眼
            // 认出来（错误信息会进崩溃报告的诊断字 [13..15]）。2026-09-12 的 EID 轮次里，
            // 16 KiB 的 `kRomfsModScriptMaximumLength` 就是这样吞掉了 EID 的 `require`。
            return RaiseRequireFailure(state, 23, "required module is larger than the script buffer");
        }
        return RaiseRequireFailure(state, 21, "required module could not be read");
    }

    std::array<char, kStage13RequirePathCapacity + 1> chunkNameStorage{};
    chunkNameStorage[0] = '@';
    std::memcpy(chunkNameStorage.data() + 1, path.data(), pathLength + 1);
    const char* chunkName = chunkNameStorage.data();
    auto& source = g_Stage13RequireSource;
    if (luaL_loadbufferx(state, source.data(), length, chunkName, "t") != LUA_OK) {
        --g_Stage13RequireDepth;
        return RaiseRequireFailure(state, 22, "required module could not be compiled");
    }
    if (lua_pcallk(state, 0, 1, 0, 0, nullptr) != LUA_OK) {
        --g_Stage13RequireDepth;
        const u32 detail = ClassifyRequireExecutionFailure(state);
        if (detail == 27 && g_RequireFailureDetail.load(std::memory_order_acquire) == 0) {
            RecordRequireErrorTail(state);
        }
        // 结构化失败码照记（26 = `RegisterMod` 被调用两次、27 = 其它执行失败），但**消息不再替换**：
        // 把内层错误**原样抛出去**，与 PC 的 `require` 一致。
        //
        // 为什么必须改（2026-09-12 第四轮真机）：EID 的 `main.lua:120` 是
        // `require("features.eid_mcm")`，我们原来把内层消息换成自己的
        // "required module could not be executed"，于是真机报告里**完全看不出**
        // `eid_mcm.lua` 到底哪一行、为什么失败 —— 而真机一轮只能问一个问题。
        // PC 的 require 传播原始错误（带出错的 chunk 名与行号），我们也照做。
        RecordRequireFailure(detail);
        if (lua_type(state, -1) == LUA_TSTRING) {
            return lua_error(state);
        }
        lua_pop(state, 1);
        return RaiseRequireFailure(state, detail, "required module could not be executed");
    }
    --g_Stage13RequireDepth;

    if (lua_isnil(state, -1)) {
        lua_pop(state, 1);
        lua_pushboolean(state, 1);
    }
    lua_pushlstring(state, moduleName, moduleLength);
    lua_pushvalue(state, -2);
    lua_rawset(state, cacheIndex);
    return 1;
}

// ---- `load` / `loadstring`（批次 034：按 PC 口径补上，见 `docs/问题与解决记录.md` 续五十九）----
//
// 背景：这两个全局以前**刻意置空**（沙箱决定），而 PC 是 LuaJIT 5.1 —— `load`、`loadstring`、
// `loadfile`、`dofile` 四样都有。真机代价：卡上的可调用性探针 v2 用
// `load('return ' .. 表达式)()` 求值 ⇒ 20 个 owner 全部 skipped、报告里 `miss=0` 是空结论，
// 一轮设备验证白跑（同一天记录在案）。模组本来就执行任意代码，"能编译一段字符串"不构成新的
// 风险面；**比 PC 严**才是本项目反复吃亏的那一类错。
//
// 口径：`loadstring(chunk[, chunkname])` 是 5.1 的字符串版；`load(chunk[, chunkname[, mode[, env]]])`
// **字符串与读取函数两种都收**（5.1 的 `load` 只收函数）。失败形状与 PC 一致：`nil, 错误消息`。
// `loadfile`/`dofile` **仍为 nil**：它们要"从哪个挂载点读文件"的路径口径，属于文件能力那一层，
// 本批不做（写在文档里，不静默留坑）。

//: `load` 的保留槽（照搬 Lua 5.3 `lbaselib.c` 的 `RESERVEDSLOT`）：读取函数返回的那块内存
//: 必须在本轮读取期间一直活着，所以把字符串移到这个固定槽位再交给 `lua_load`。
constexpr int kLoadReservedSlot = 4;

const char* LuaChunkReader(lua_State* state, void* data, size_t* size) {
    static_cast<void>(data);
    if (lua_checkstack(state, 2) == 0) {
        *size = 0;
        return nullptr;
    }
    lua_pushvalue(state, 1);  // 读取函数是 `load` 的第 1 个实参
    lua_call(state, 0, 1);
    if (lua_isnil(state, -1)) {
        lua_pop(state, 1);
        *size = 0;
        return nullptr;  // 读到 nil = 这块完了
    }
    const char* piece = lua_tolstring(state, -1, size);
    if (piece == nullptr) {
        lua_pop(state, 1);
        luaL_error(state, "load reader must return a string");
        *size = 0;
        return nullptr;
    }
    lua_replace(state, kLoadReservedSlot);  // 存进保留槽：本次读取期间它不会被回收
    return piece;
}

//: 统一收尾：编译失败 ⇒ `nil, 消息`（**不抛错**，与 PC 一致）；成功 ⇒ 函数（可选装 `_ENV`）。
int FinishLoad(lua_State* state, int status, bool hasEnvironment) {
    if (status != LUA_OK) {
        lua_pushnil(state);
        lua_insert(state, -2);
        return 2;
    }
    if (hasEnvironment) {
        lua_pushvalue(state, kLoadReservedSlot);
        static_cast<void>(lua_setupvalue(state, -2, 1));  // 第 1 个 upvalue 就是 `_ENV`
    }
    return 1;
}

int ModLoad(lua_State* state) {
    const int argumentCount = lua_gettop(state);
    if (argumentCount < 1 || argumentCount > 4) {
        return luaL_error(state,
                          "load expects a chunk plus optional chunkname, mode and environment");
    }
    const bool hasEnvironment = argumentCount >= 4 && !lua_isnil(state, 4);
    const char* mode = luaL_optstring(state, 3, "bt");
    std::size_t length = 0;
    const char* text = lua_tolstring(state, 1, &length);
    int status = LUA_OK;
    if (text != nullptr) {
        const char* chunkName = luaL_optstring(state, 2, text);
        status = luaL_loadbufferx(state, text, length, chunkName, mode);
    } else if (lua_isfunction(state, 1)) {
        const char* chunkName = luaL_optstring(state, 2, "=(load)");
        lua_settop(state, kLoadReservedSlot);  // 造出保留槽；第 1 位的读取函数留着
        status = lua_load(state, LuaChunkReader, nullptr, chunkName, mode);
    } else {
        return luaL_error(state, "load expects a string or a function");
    }
    return FinishLoad(state, status, hasEnvironment);
}

int ModLoadString(lua_State* state) {
    const int argumentCount = lua_gettop(state);
    if (argumentCount != 1 && argumentCount != 2) {
        return luaL_error(state, "loadstring expects a string plus an optional chunkname");
    }
    std::size_t length = 0;
    const char* text = lua_tolstring(state, 1, &length);
    if (text == nullptr) {
        return luaL_error(state, "loadstring expects a string chunk");
    }
    const char* chunkName = luaL_optstring(state, 2, text);
    return FinishLoad(state, luaL_loadbufferx(state, text, length, chunkName, "bt"), false);
}

// ---- `include(path)`（批次 042：PC 提供的全局，GoodTrip 一加载就要它）--------------------
//
// PC 把 `include` 作为模组环境的一部分提供给 Lua（`analysis/isaacdocs-snapshot/docs/Globals.md:189`
// 的全局清单里有它）。它与 `require` 的差别，模组作者在 GoodTrip 的 `main.lua:30-33` 里写得很准
//（也是 PC 的实际行为）：
//
//   > modules. Only main.lua includes, each file exactly once, here at load: include
//   > **re-reads the file on every luamod** (require would cache it) and **never resolves into
//   > another mod's folder**, so a luamod always runs the code on disk with fresh module state.
//
// 即：**不缓存**（每次都重新读盘执行）、**只在当前模组自己的目录里解析**、**返回 chunk 的返回值**
//（GoodTrip 的用法就是 `include("scripts.config")({...})` —— 返回的是一个工厂函数）。
//
// 我们缺它的代价（2026-09-19 实测）：GoodTrip 的 `main.lua:36` 第一句是
// `pcall(include, "gtconfig")`、随后 `include("scripts.config")` —— `include` 为 nil 时
// **模组整个加载失败**（"attempt to call a nil value (global 'include')"）。
//
// ⚠️ 这条缺口此前**扫不到**：缺口工具认的是 `Owner:Name(` / `Owner.Name(` / 链式三种形态，
// 而 `include(...)` 是**裸全局调用**。已登记为工具的待补形态（见 `docs/问题与解决记录.md` 续六十三）。
//
// 失败口径：与 PC 一致地**抛 Lua 错误**（GoodTrip 用 `pcall` 包着第一次调用，正是为了容忍
// `gtconfig.lua` 不存在/写坏）。
int Include(lua_State* state) {
    if (!g_RequireAvailable || lua_gettop(state) != 1 || lua_type(state, 1) != LUA_TSTRING) {
        return luaL_error(state, "include expects one module path");
    }
    std::size_t moduleLength = 0;
    const char* moduleName = lua_tolstring(state, 1, &moduleLength);
    if (moduleName == nullptr || moduleLength == 0 ||
        g_Stage13ModRootLength + moduleLength + 6 > kStage13RequirePathCapacity) {
        return luaL_error(state, "include expects one usable module path");
    }

    std::array<char, kStage13RequirePathCapacity> path{};
    std::memcpy(path.data(), g_Stage13ModRoot.data(), g_Stage13ModRootLength);
    std::size_t pathLength = g_Stage13ModRootLength;
    path[pathLength++] = '/';
    for (std::size_t index = 0; index < moduleLength; ++index) {
        if (!IsAsciiModuleCharacter(moduleName[index]) || moduleName[index] == '/' ||
            moduleName[index] == '\\' ||
            (moduleName[index] == '.' && index + 1 < moduleLength && moduleName[index + 1] == '.')) {
            return luaL_error(state, "include rejects this module path");
        }
        path[pathLength++] = moduleName[index] == '.' ? '/' : moduleName[index];
    }
    std::memcpy(path.data() + pathLength, ".lua", 5);
    pathLength += 4;

    // 与 `require` 共用同一块源码缓冲与深度计数：两者都在加载期递归执行文件，
    // 各用一份缓冲只会让 `.bss` 白吃一倍（这块是 1 MiB）。
    if (g_Stage13RequireDepth >= kStage13RequireMaximumDepth) {
        return luaL_error(state, "include nesting exceeds maximum depth");
    }
    ++g_Stage13RequireDepth;

    std::size_t length = 0;
    const auto readResult = GameFileReader::ReadTextFile(
        g_Stage13Bindings, path.data(), reinterpret_cast<u8*>(g_Stage13RequireSource.data()),
        g_Stage13RequireSource.size(), &length);
    if (readResult != GameFileReader::TextReadResult::Success) {
        --g_Stage13RequireDepth;
        std::array<char, kStage13RequirePathCapacity * 2> notFoundText{};
        return luaL_error(state, "%s", BuildRequireNotFoundMessage(
                                            &notFoundText, g_Stage13ModRoot.data(),
                                            g_Stage13ModRootLength, moduleName, moduleLength));
    }

    std::array<char, kStage13RequirePathCapacity + 1> chunkNameStorage{};
    chunkNameStorage[0] = '@';
    std::memcpy(chunkNameStorage.data() + 1, path.data(), pathLength + 1);
    if (luaL_loadbufferx(state, g_Stage13RequireSource.data(), length, chunkNameStorage.data(),
                         "t") != LUA_OK) {
        --g_Stage13RequireDepth;
        return lua_error(state);  // 编译错误的原文（带 chunk 名与行号）直接抛出，与 PC 一致
    }
    // 返回**被包含文件 chunk 的返回值**（PC 的 `include` 就是这个形状）；执行中的错误原样抛出。
    if (lua_pcallk(state, 0, LUA_MULTRET, 0, 0, nullptr) != LUA_OK) {
        --g_Stage13RequireDepth;
        return lua_error(state);
    }
    --g_Stage13RequireDepth;
    // 栈上是 `[模块名实参, chunk 的返回值...]`：**第 1 位那个实参不能算进返回值**
    //（返回 `lua_gettop()` 会把模块名当第一个返回值返回 —— 第一版就是这么写的，
    //  结果 `include("x")` 的调用方会多拿到一个字符串）。
    return lua_gettop(state) - 1;
}

void RegisterStage13Require(lua_State* state) {
    // `load`/`loadstring` 按 PC 口径提供（PC 是 LuaJIT 5.1，两个都有；理由见上一条注释）。
    // `include(path)`：PC 提供给模组的全局（`Globals.md:189`），**不缓存、只在当前模组目录里解析**。
    // 缺它时 GoodTrip 的 main.lua 第一句就 "call a nil value" ⇒ 整个模组加载失败（2026-09-19 实测）。
    // `CallbackPriority`（PC 全局枚举表，Repentance+；值取自 enums/CallbackPriority.md）。
    // GoodTrip 的 `main.lua:84` 起就要 `CallbackPriority.EARLY` —— 缺它是"索引 nil"，模组加载失败。
    lua_newtable(state);
    lua_pushinteger(state, -200); lua_setfield(state, -2, "IMPORTANT");
    lua_pushinteger(state, -100); lua_setfield(state, -2, "EARLY");
    lua_pushinteger(state, 0);    lua_setfield(state, -2, "DEFAULT");
    lua_pushinteger(state, 100);  lua_setfield(state, -2, "LATE");
    lua_setglobal(state, "CallbackPriority");
    lua_pushcfunction(state, Include);
    lua_setglobal(state, "include");
    lua_pushcfunction(state, ModLoad);
    lua_setglobal(state, "load");
    lua_pushcfunction(state, ModLoadString);
    lua_setglobal(state, "loadstring");
    lua_pushnil(state);
    lua_setglobal(state, "loadfile");
    lua_pushnil(state);
    lua_setglobal(state, "dofile");

    lua_newtable(state);
    g_RequireCacheRef = luaL_ref(state, LUA_REGISTRYINDEX);
    lua_pushcfunction(state, Require);
    lua_setglobal(state, "require");
}
#endif

void OpenLibrary(lua_State* state, u32 step, const char* name, lua_CFunction open) {
    g_PreparationStep.store(step, std::memory_order_relaxed);
    luaL_requiref(state, name, open, 1);
    lua_pop(state, 1);
}

int ModIndex(lua_State* state) {
    luaL_checkudata(state, 1, kModMetatable);
    if (lua_gettop(state) != 2) {
        return luaL_error(state, "Mod field lookup expects one key");
    }
    lua_getmetatable(state, 1);
    lua_getfield(state, -1, kModMethodsField);
    lua_pushvalue(state, 2);
    lua_rawget(state, -2);
    if (!lua_isnil(state, -1)) return 1;
    lua_pop(state, 3);
    lua_getuservalue(state, 1);
    lua_pushvalue(state, 2);
    lua_rawget(state, -2);
    return 1;
}

int ModNewIndex(lua_State* state) {
    luaL_checkudata(state, 1, kModMetatable);
    if (lua_gettop(state) != 3) {
        return luaL_error(state, "Mod field assignment expects one key and value");
    }
    lua_getuservalue(state, 1);
    lua_pushvalue(state, 2);
    lua_pushvalue(state, 3);
    lua_rawset(state, -3);
    return 0;
}

int RegisterMod(lua_State* state) {
    if (lua_gettop(state) != 2) {
        return luaL_error(state, "RegisterMod expects a name and a version");
    }
    const char* name = luaL_checkstring(state, 1);
    luaL_checkinteger(state, 2);
    // 多模组（2026-09-16）：**不再限制一个 Mod**。
    //
    // 之前这里 `g_ModRegistered` 一次性拦住第二次调用、并报 "RegisterMod accepts exactly one
    // Mod" —— 那是"一次只加载一个模组"时代的产物。多模组加载下每个 Mod 都会调用它一次，
    // 而且 PC 上 `RegisterMod` 本来就可以调用多次（每次返回一个新的 Mod 对象）。
    //
    // 每个 Mod 拿一个**独立的 owner 句柄**：回调登记用它做归属（`CallbackRegistry` 的
    // Find/Remove/RemoveOwner 都按 owner 区分），否则多个 Mod 的回调会混成一家。
    g_ModRegistered = true;
    g_ModRegisteredCount.fetch_add(1, std::memory_order_release);

    auto* mod = static_cast<ModHandle*>(lua_newuserdata(state, sizeof(ModHandle)));
    mod->persistenceNamespace = ModPersistence::HashModNamespace(name, std::strlen(name));
    mod->ownerPacked = PackModOwner(NextModOwner());
    lua_newtable(state);
    lua_setuservalue(state, -2);
    luaL_getmetatable(state, kModMetatable);
    lua_setmetatable(state, -2);
#if !defined(EXL_DIAGNOSTIC_STAGE) || EXL_DIAGNOSTIC_STAGE == 13
    if (g_Stage13Mode) {
        g_ModObjectRef = lua_gettop(state);
        lua_pushvalue(state, g_ModObjectRef);
        g_ModObjectRef = luaL_ref(state, LUA_REGISTRYINDEX);
    }
#endif
    return 1;
}


void SetIntegerConstants(lua_State* state, const LuaIntegerConstant* constants, std::size_t count) {
    lua_newtable(state);
    for (std::size_t index = 0; index < count; ++index) {
        lua_pushinteger(state, constants[index].value);
        lua_setfield(state, -2, constants[index].name);
    }
}

void RegisterPcLuaEnumTables(lua_State* state) {
    std::size_t tableCount = 0;
    const PcLuaEnumData::Table* tables = PcLuaEnumData::Tables(&tableCount);
    if (tables != nullptr) {
        for (std::size_t tableIndex = 0; tableIndex < tableCount; ++tableIndex) {
            lua_newtable(state);
            for (std::size_t valueIndex = 0; valueIndex < tables[tableIndex].count; ++valueIndex) {
                lua_pushinteger(state, tables[tableIndex].values[valueIndex].value);
                lua_setfield(state, -2, tables[tableIndex].values[valueIndex].key);
            }
            lua_setglobal(state, tables[tableIndex].name);
        }
    }
    // 批次 048：PC 文档快照里那几张（`pc_lua_enum_data` 之外的补充）。**两边表名不相交**
    // （生成器 `tools/generate_doc_enum_tables.py` 会断言这一点），所以这里不会互相覆盖。
    // 值走 `std::int64_t`：`DamageFlag.DAMAGE_SPAWN_RUNE` 是 `1 << 32`，32 位会静默回绕成 0。
    std::size_t docCount = 0;
    const DocLuaEnumData::Table* docTables = DocLuaEnumData::Tables(&docCount);
    if (docTables != nullptr) {
        for (std::size_t tableIndex = 0; tableIndex < docCount; ++tableIndex) {
            lua_newtable(state);
            for (std::size_t valueIndex = 0; valueIndex < docTables[tableIndex].count;
                 ++valueIndex) {
                lua_pushinteger(
                    state,
                    static_cast<lua_Integer>(docTables[tableIndex].values[valueIndex].value));
                lua_setfield(state, -2, docTables[tableIndex].values[valueIndex].key);
            }
            lua_setglobal(state, docTables[tableIndex].name);
        }
    }
}


void RegisterNeutralInputApi(lua_State* state) {
    lua_newtable(state);
    static_cast<void>(isaac::runtime::AttachInputMethods(state));
    lua_setglobal(state, "Input");

    SetIntegerConstants(state, kKeyboardConstants.data(), kKeyboardConstants.size());
    lua_setglobal(state, "Keyboard");
    SetIntegerConstants(state, kButtonActionConstants.data(), kButtonActionConstants.size());
    lua_setglobal(state, "ButtonAction");
    constexpr std::array<LuaIntegerConstant, 3> inputHooks{{
        {"IS_ACTION_PRESSED", 0}, {"IS_ACTION_TRIGGERED", 1}, {"GET_ACTION_VALUE", 2},
    }};
    SetIntegerConstants(state, inputHooks.data(), inputHooks.size());
    lua_setglobal(state, "InputHook");
}


int MarkPostUpdate(lua_State* state) {
    if (lua_gettop(state) != 0) {
        return luaL_error(state, "MarkPostUpdate accepts no arguments");
    }
    g_PostUpdateCount.fetch_add(1, std::memory_order_relaxed);
    return 0;
}

#if defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 15
int MarkPostRender(lua_State* state) {
    if (lua_gettop(state) != 0) {
        return luaL_error(state, "MarkPostRender accepts no arguments");
    }
    g_PostRenderCount.fetch_add(1, std::memory_order_relaxed);
    return 0;
}

int MarkPostRenderPaused(lua_State* state) {
    if (lua_gettop(state) != 0) {
        return luaL_error(state, "MarkPostRenderPaused accepts no arguments");
    }
    g_PostRenderPausedCount.fetch_add(1, std::memory_order_relaxed);
    return 0;
}
#endif

#if defined(EXL_DIAGNOSTIC_STAGE) && (EXL_DIAGNOSTIC_STAGE == 16 || EXL_DIAGNOSTIC_STAGE == 17)
int MarkMusicDiagnosticCycleCompleted(lua_State* state) {
    if (lua_gettop(state) != 0) {
        return luaL_error(state, "MarkMusicDiagnosticCycleCompleted accepts no arguments");
    }
    g_MusicDiagnosticCycleCompleted.store(true, std::memory_order_release);
    return 0;
}
#endif

#if defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 45
int MarkMusicDiagnosticCurrentId(lua_State* state) {
    if (lua_gettop(state) != 1 || !lua_isinteger(state, 1)) {
        return luaL_error(state, "MarkMusicDiagnosticCurrentId accepts one integer");
    }
    const lua_Integer value = lua_tointegerx(state, 1, nullptr);
    if (value < INT32_MIN || value > INT32_MAX) {
        return luaL_error(state, "Music ID is outside int32 range");
    }
    g_MusicDiagnosticCurrentId.store(static_cast<u32>(static_cast<s32>(value)),
                                     std::memory_order_release);
    g_MusicDiagnosticCurrentIdReady.store(true, std::memory_order_release);
    return 0;
}
#endif

int CreateGameHandle(lua_State* state) {
    if (lua_gettop(state) != 0) {
        return luaL_error(state, "Game accepts no arguments");
    }
    auto* game = static_cast<GameHandle*>(lua_newuserdata(state, sizeof(GameHandle)));
    game->reserved = 0;
    luaL_getmetatable(state, kGameMetatable);
    lua_setmetatable(state, -2);
    return 1;
}


bool ValidateMusicMethod(uintptr_t address, const u8* expected, std::size_t expectedLength);

bool ValidateItemPoolGetCollectibleMethod(uintptr_t address) {
    if (address == 0 || (address & 3) != 0) return false;
#if defined(__SWITCH__)
    constexpr std::size_t entrySize = kPreGetCollectibleRelayExpectedEntry.size();
    constexpr std::size_t totalSize = kPreGetCollectibleRelayExpectedOriginal.size();
    MemoryInfo info{};
    u32 pageInfo = 0;
    if (address > UINTPTR_MAX - totalSize ||
        R_FAILED(svcQueryMemory(&info, &pageInfo, address)) || info.size == 0 ||
        info.addr > UINTPTR_MAX - info.size) {
        return false;
    }
    const uintptr_t end = address + totalSize;
    if (!(address >= info.addr && end <= info.addr + info.size &&
          (info.type & MemState_Type) == MemType_ModuleCodeStatic && info.perm == Perm_Rx)) {
        return false;
    }
    // 形态一（旧 IPS 中继）：入口前 4 字节是补丁写入的分支，其余仍是被调用函数的原序言。
    if (std::memcmp(reinterpret_cast<const void*>(address), kPreGetCollectibleRelayExpectedEntry.data(),
                    entrySize) == 0 &&
        std::memcmp(reinterpret_cast<const void*>(address + entrySize),
                    kPreGetCollectibleRelayExpectedOriginal.data() + entrySize,
                    totalSize - entrySize) == 0) {
        return true;
    }
    // 形态二（零占洞入口中继）：入口 16 字节整体被改写成 `ldr x16, #8; br x16; .quad 槽地址`。
    // 两个目标都是小端，整字比较与逐字节比较等价；槽地址只做"非零且 8 字节对齐"的轻量核对
    // （它落在我们自己的模块里，这个函数看不到那边的边界）。
    if (std::memcmp(reinterpret_cast<const void*>(address), &kEntryRelayEntryStubWord0,
                    sizeof(kEntryRelayEntryStubWord0)) != 0 ||
        std::memcmp(reinterpret_cast<const void*>(address + sizeof(kEntryRelayEntryStubWord0)),
                    &kEntryRelayEntryStubWord1, sizeof(kEntryRelayEntryStubWord1)) != 0) {
        return false;
    }
    std::uintptr_t slot = 0;
    std::memcpy(&slot, reinterpret_cast<const void*>(address + 8), sizeof(slot));
    return slot != 0 && (slot & (alignof(std::uintptr_t) - 1)) == 0;
#else
    return true;
#endif
}



bool IsReadableMusicObject(uintptr_t address) {
#if defined(__SWITCH__)
    MemoryInfo info{};
    u32 pageInfo = 0;
    if (R_FAILED(svcQueryMemory(&info, &pageInfo, address)) || info.size == 0 ||
        info.addr > UINTPTR_MAX - info.size || address > UINTPTR_MAX - sizeof(uintptr_t)) {
        return false;
    }
    const uintptr_t end = address + sizeof(uintptr_t);
    return address >= info.addr && end <= info.addr + info.size &&
           (info.perm & Perm_R) != 0 && (info.perm & Perm_X) == 0;
#else
    return address != 0 && (address & (alignof(uintptr_t) - 1)) == 0;
#endif
}

bool ValidateMusicMethod(uintptr_t address, const u8* expected, std::size_t expectedLength) {
    if (address == 0 || expected == nullptr || expectedLength == 0 || (address & 3) != 0) {
        return false;
    }
#if defined(__SWITCH__)
    MemoryInfo info{};
    u32 pageInfo = 0;
    if (address > UINTPTR_MAX - expectedLength ||
        R_FAILED(svcQueryMemory(&info, &pageInfo, address)) || info.size == 0 ||
        info.addr > UINTPTR_MAX - info.size) {
        return false;
    }
    const uintptr_t end = address + expectedLength;
    return address >= info.addr && end <= info.addr + info.size &&
           (info.type & MemState_Type) == MemType_ModuleCodeStatic && info.perm == Perm_Rx &&
           std::memcmp(reinterpret_cast<const void*>(address), expected, expectedLength) == 0;
#else
    return true;
#endif
}

bool ResolveMusicForManager(uintptr_t manager, uintptr_t method, const u8* expected,
                            std::size_t expectedLength, uintptr_t* music) {
    if (manager == 0 || manager > UINTPTR_MAX - kManagerMusicOffset) {
        return false;
    }
    const uintptr_t candidate = manager + kManagerMusicOffset;
    if (!IsReadableMusicObject(candidate) || !ValidateMusicMethod(method, expected, expectedLength)) {
        return false;
    }
    *music = candidate;
    return true;
}

bool ResolveMusicForCall(uintptr_t method, const u8* expected, std::size_t expectedLength,
                         uintptr_t* music) {
    if (!g_InManagedCallbackDispatch.load(std::memory_order_acquire)) {
        return false;
    }
    return ResolveMusicForManager(g_CurrentCallbackManager.load(std::memory_order_acquire), method,
                                  expected, expectedLength, music);
}

int CreateMusicHandle(lua_State* state) {
    if (lua_gettop(state) != 0) {
        return luaL_error(state, "MusicManager accepts no arguments");
    }
    auto* music = static_cast<MusicHandle*>(lua_newuserdata(state, sizeof(MusicHandle)));
    music->reserved = 0;
    luaL_getmetatable(state, kMusicMetatable);
    lua_setmetatable(state, -2);
    return 1;
}


#if defined(__GNUC__) && !defined(__clang__)
#pragma GCC push_options
#pragma GCC optimize ("Os")
#endif

int CreateRngHandle(lua_State* state) {
    if (lua_gettop(state) != 0) {
        return luaL_error(state, "RNG accepts no arguments");
    }
    auto* rng = static_cast<RngHandle*>(lua_newuserdata(state, sizeof(RngHandle)));
    *rng = {};
    luaL_getmetatable(state, kRngMetatable);
    lua_setmetatable(state, -2);
    return 1;
}


#if defined(__GNUC__) && !defined(__clang__)
#pragma GCC pop_options
#endif

void RegisterGameApi(lua_State* state) {
    luaL_newmetatable(state, kGameMetatable);
    lua_newtable(state);
    // The `Game` family owns its binding table in
    // `interfaces/lua/game_api.cpp`; every owner registers from its own family
    // unit in layered builds.
    static_cast<void>(isaac::runtime::AttachGameMethods(state));
    // 2026-09-16：`__index` 从"方法表"改成"**先认字段、再落方法表**"的 C 闭包 —— PC 的
    // `game.Challenge` / `game.Difficulty` / `game.TimeCounter` / `game.ScreenShakeOffset`
    // 是**字段**（点访问），挂在表上会被当成方法（返回函数而不是值）。
    // 方法表作为闭包的上值 1 带进去，认不出的键原样落回它。
    lua_pushcclosure(state, isaac::runtime::GameIndex, 1);
    lua_setfield(state, -2, "__index");
    // 批次 061：与 `Level` 同理（同一个实现）—— PC 的 `Game` 字段可写，
    // 例如 GoodTrip 的 `Game().TimeCounter = Game().TimeCounter + addTime`。
    lua_pushcfunction(state, isaac::runtime::IgnoredObjectFieldWrite);
    lua_setfield(state, -2, "__newindex");
    lua_pop(state, 1);

    luaL_newmetatable(state, kRoomMetatable);
    lua_newtable(state);
    static_cast<void>(isaac::runtime::AttachRoomMethods(state));
    lua_setfield(state, -2, "__index");
    lua_pop(state, 1);

    // 地基二期：`RoomDescriptor` 与它的列表。两者的 `__index` 都是**函数**（同时服务字段与方法），
    // 方法表挂在元表的 `__methods` 上（与 `Sprite`/`Vector` 同一形态）。
    // 批次 12：`GridEntity` 族（`Room:GetGridEntity()` 的返回值）。它的方法都住在 `Room`
    // 所在的那个家族 TU 里（`AttachGridEntityMethods`），与"行表住在自己 TU 里"的规矩一致。
    // ★ 2026-09-21：`__index` 由**表**改成**函数**（与 `RoomDescriptor` 同一形态）——
    // PC 的 `GridEntity` 还有 `Position`/`VarData`/`Desc` 这些**字段**（IsaacDocs `GridEntity.md`），
    // 只挂方法表时模组读它们会拿到 `nil`（EID 献祭房就是栽在 `gridEntity.Position` 上）。
    // 方法表因此挪到 `__methods`（`GridEntityIndex` 在答完字段后从那里取）。
    luaL_newmetatable(state, kGridEntityMetatable);
    lua_pushcfunction(state, isaac::runtime::GridEntityIndex);
    lua_setfield(state, -2, "__index");
    lua_newtable(state);
    static_cast<void>(isaac::runtime::AttachGridEntityMethods(state));
    lua_setfield(state, -2, "__methods");
    lua_pop(state, 1);

    // 批次 078：`Room:GetDoor(slot)` 的返回值（`GridEntity_Door`）。PC 里门**同时是** `GridEntity`，
    // 所以它的 `__index` 是**函数**：先答门的字段，答不上再落到上面那张 `GridEntity` 方法表。
    luaL_newmetatable(state, kGridEntityDoorMetatable);
    lua_pushcfunction(state, isaac::runtime::GridEntityDoorIndex);
    lua_setfield(state, -2, "__index");
    lua_pop(state, 1);

    luaL_newmetatable(state, kRoomDescriptorMetatable);
    lua_pushcfunction(state, isaac::runtime::RoomDescriptorIndex);
    lua_setfield(state, -2, "__index");
    lua_pop(state, 1);

    luaL_newmetatable(state, kRoomDescriptorListMetatable);
    lua_pushcfunction(state, isaac::runtime::RoomDescriptorListIndex);
    lua_setfield(state, -2, "__index");
    lua_newtable(state);
    static_cast<void>(isaac::runtime::AttachRoomDescriptorListMethods(state));
    lua_setfield(state, -2, "__methods");
    lua_pop(state, 1);

    luaL_newmetatable(state, kItemPoolMetatable);
    lua_newtable(state);
    static_cast<void>(isaac::runtime::AttachItemPoolMethods(state));
    lua_setfield(state, -2, "__index");
    lua_pop(state, 1);

    luaL_newmetatable(state, kLevelMetatable);
    lua_newtable(state);
    static_cast<void>(isaac::runtime::AttachLevelMethods(state));
    lua_setfield(state, -2, "__index");
    // 批次 061：`Level` 的字段**可写**（PC 的 `Level` 就是引擎对象，模组直接赋值）。
    // 没有这一行时 `floor.level.EnterDoor = -1` 直接抛
    // "attempt to index a IsaacRuntime.Level value" ⇒ GoodTrip 的传送在第一句就断掉。
    lua_pushcfunction(state, isaac::runtime::IgnoredObjectFieldWrite);
    lua_setfield(state, -2, "__newindex");
    lua_pop(state, 1);

    luaL_newmetatable(state, kSeedsMetatable);
    lua_newtable(state);
    static_cast<void>(isaac::runtime::AttachSeedsMethods(state));
    lua_setfield(state, -2, "__index");
    lua_pop(state, 1);

    lua_pushcfunction(state, CreateGameHandle);
    lua_setglobal(state, "Game");
}

void RegisterMusicApi(lua_State* state) {
    luaL_newmetatable(state, kMusicMetatable);
    lua_newtable(state);
    static_cast<void>(isaac::runtime::AttachMusicMethods(state));
    // 批次 045：`SFXManager()`（为 GoodTrip 补）。**元表与全局在中枢建** —— 家族 TU 不许自己写
    // 注册/建表循环（契约门禁明文，`Game` 家族当年同理）。句柄无字段 ⇒ `__index` 就是方法表。
    luaL_newmetatable(state, "IsaacRuntime.SFXManager");
    lua_newtable(state);
    static_cast<void>(isaac::runtime::AttachSfxManagerMethods(state));
    lua_pushvalue(state, -1);
    lua_setfield(state, -3, "__index");
    lua_setfield(state, -2, "__methods");
    lua_pop(state, 1);
    lua_pushcfunction(state, isaac::runtime::SfxManagerCtor);
    lua_setglobal(state, "SFXManager");
    lua_setfield(state, -2, "__index");
    lua_pop(state, 1);

    lua_pushcfunction(state, CreateMusicHandle);
    lua_setglobal(state, "MusicManager");
    lua_newtable(state);
    lua_pushinteger(state, 0);
    lua_setfield(state, -2, "MUSIC_NULL");
    lua_setglobal(state, "Music");
}

#if defined(__GNUC__) && !defined(__clang__)
#pragma GCC push_options
#pragma GCC optimize ("Os")
#endif

void RegisterRngApi(lua_State* state) {
    luaL_newmetatable(state, kRngMetatable);
    lua_newtable(state);
    static_cast<void>(isaac::runtime::AttachRngMethods(state));
    lua_setfield(state, -2, "__index");
    lua_pop(state, 1);

    lua_pushcfunction(state, CreateRngHandle);
    lua_setglobal(state, "RNG");
}

// `KColor` is the colour value type the render-facing APIs take. Its metatable needs an
// `__index` function rather than a method table, because PC Mods read the components
// (`c.R`, `c.G`, ...) instead of calling accessors.
void RegisterColorApi(lua_State* state) {
    luaL_newmetatable(state, LuaRuntime::kColorMetatable);
    lua_pushcfunction(state, isaac::runtime::ColorIndex);
    lua_setfield(state, -2, "__index");
    // 真实 Mod 会写颜色字段：EID 的彩虹/闪烁/淡出效果就是 `color.Alpha = ...` 与
    // `color = func(color)`，所以 KColor 必须可写，否则那些效果会在赋值处报错。
    lua_pushcfunction(state, isaac::runtime::ColorNewIndex);
    lua_setfield(state, -2, "__newindex");
    lua_pop(state, 1);

    // 全局 `KColor` 是可调用的**类表**：`__call` 是构造器，`__index` 提供文档化的常量
    // （`KColor.White` 等）。与 `Vector` 同一形态，理由相同：常量必须挂在类上。
    lua_newtable(state);
    lua_newtable(state);
    isaac::runtime::PushHandler(state, isaac::runtime::CreateColorHandle, 0,
                                     isaac::runtime::kPerfInternalIdColorIndex);
    lua_setfield(state, -2, "__call");
    lua_pushcfunction(state, isaac::runtime::KColorClassIndex);
    lua_setfield(state, -2, "__index");
    lua_setmetatable(state, -2);
    lua_setglobal(state, "KColor");

    // 全局 `Color`（批次 3）：PC 的 `Color` 与 `KColor` 是**同一个类**（`KColor` 是别名之一），
    // 所以这里把上面那张类表**原样**再挂一个全局名 —— 两者恒等（`Color == KColor`），
    // 构造器（含七参 `Color(r,g,b,a,ro,go,bo)` 重载）与常量完全共用，不需要第二份实现。
    // EID 的 `EID:renderIcon`（`features/eid_api.lua:1369`）与 `EID:renderIndicator`
    // （`main.lua:960`）用的就是 `Color(...)`，而 `EID:getTextColor()` 那一路用的是 `KColor(...)`。
    lua_getglobal(state, "KColor");
    lua_setglobal(state, "Color");
}

// `Vector` = `KAGE::Math::Vector2`（8 字节 `{float X, float Y}` 值类型，无虚表）。比 `KColor`
// 多一层：它既要 userdata 元表（字段 + 方法 + 运算符），又要一个**可调用的类表**来承载
// `Vector.Zero`/`Vector.One`/`Vector.FromAngle`。方法表仍来自家族 TU 的 `AttachVectorMethods`。
// `Sprite` = `IsaacRepentance::ANM2`。与 `Font` 同一形态：元表带 `__gc`（我们分配的对象必须
// 由我们释放），方法表来自家族 TU。第一步只注册不收 `std::string` 的那一半。
//
// 批次 3 起 `__index` 是**函数**（`SpriteIndex`）：`Sprite` 多了三个可写属性
// （`Scale`/`Color`/`FlipX`，EID 在绘制路径上直接赋值），而 `__index` 必须是函数才能同时
// 服务字段与方法。方法表因此挪到元表的 `__methods` 上（与 `Vector` 同一形态）；
// `__newindex` 只处理那三个字段，其它字段名报错。
void RegisterSpriteApi(lua_State* state) {
    luaL_newmetatable(state, LuaRuntime::kSpriteMetatable);
    lua_pushcfunction(state, isaac::runtime::DestroySpriteHandle);
    lua_setfield(state, -2, "__gc");
    lua_pushcfunction(state, isaac::runtime::SpriteIndex);
    lua_setfield(state, -2, "__index");
    lua_pushcfunction(state, isaac::runtime::SpriteNewIndex);
    lua_setfield(state, -2, "__newindex");
    lua_newtable(state);
    static_cast<void>(isaac::runtime::AttachSpriteMethods(state));
    lua_setfield(state, -2, "__methods");
    lua_pop(state, 1);

    lua_pushcfunction(state, isaac::runtime::CreateSpriteHandle);
    lua_setglobal(state, "Sprite");
}

// 批次 065：`EntityRef` —— PC 的值类型，GoodTrip 的诅咒房过路费要它
// （`player:TakeDamage(n, flags, EntityRef(player), 0)`）。它底下是**引擎自己的
// `Entity::EntityRef` 结构体**（引擎按引用读），所以句柄就是一块缓冲区，布局证据见
// `interfaces/lua/entity_ref_api.hpp`。`__index` 暴露 `Type`/`Variant`/`Entity` 三个字段。
void RegisterEntityRefApi(lua_State* state) {
    luaL_newmetatable(state, LuaRuntime::kEntityRefMetatable);
    lua_pushcfunction(state, isaac::runtime::EntityRefIndex);
    lua_setfield(state, -2, "__index");
    lua_pop(state, 1);

    isaac::runtime::PushHandler(state, isaac::runtime::CreateEntityRefHandle, 0,
                                     isaac::runtime::kPerfInternalIdEntityRefCall);
    lua_setglobal(state, "EntityRef");
}

void RegisterVectorApi(lua_State* state) {
    luaL_newmetatable(state, LuaRuntime::kVectorMetatable);
    // `__index` 必须是函数：它同时服务 `v.X`/`v.Y` 字段与方法查找（方法表挂在元表的
    // `__methods` 上，见 `interfaces/lua/vector_api.cpp`）。
    isaac::runtime::PushHandler(state, isaac::runtime::VectorIndex, 0,
                                     isaac::runtime::kPerfInternalIdVectorIndex);
    lua_setfield(state, -2, "__index");
    // `X`/`Y` 在 PC 里是可写变量，Mod 会直接赋值。
    isaac::runtime::PushHandler(state, isaac::runtime::VectorNewIndex, 0,
                                     isaac::runtime::kPerfInternalIdVectorNewIndex);
    lua_setfield(state, -2, "__newindex");
    isaac::runtime::PushHandler(state, isaac::runtime::VectorAdd, 0,
                                     isaac::runtime::kPerfInternalIdVectorAdd);
    lua_setfield(state, -2, "__add");
    isaac::runtime::PushHandler(state, isaac::runtime::VectorSub, 0,
                                     isaac::runtime::kPerfInternalIdVectorSub);
    lua_setfield(state, -2, "__sub");
    isaac::runtime::PushHandler(state, isaac::runtime::VectorMul, 0,
                                     isaac::runtime::kPerfInternalIdVectorMul);
    lua_setfield(state, -2, "__mul");
    isaac::runtime::PushHandler(state, isaac::runtime::VectorDiv, 0,
                                     isaac::runtime::kPerfInternalIdVectorDiv);
    lua_setfield(state, -2, "__div");
    isaac::runtime::PushHandler(state, isaac::runtime::VectorUnaryMinus, 0,
                                     isaac::runtime::kPerfInternalIdVectorUnaryMinus);
    lua_setfield(state, -2, "__unm");
    isaac::runtime::PushHandler(state, isaac::runtime::VectorEqual, 0,
                                     isaac::runtime::kPerfInternalIdVectorEqual);
    lua_setfield(state, -2, "__eq");
    isaac::runtime::PushHandler(state, isaac::runtime::VectorToString, 0,
                                     isaac::runtime::kPerfInternalIdVectorToString);
    lua_setfield(state, -2, "__tostring");
    lua_newtable(state);
    static_cast<void>(isaac::runtime::AttachVectorMethods(state));
    lua_setfield(state, -2, "__methods");
    lua_pop(state, 1);

    lua_newtable(state);
    lua_newtable(state);
    isaac::runtime::PushHandler(state, isaac::runtime::CreateVectorHandle, 0,
                                     isaac::runtime::kPerfInternalIdVectorCall);
    lua_setfield(state, -2, "__call");
    lua_pushcfunction(state, isaac::runtime::VectorClassIndex);
    lua_setfield(state, -2, "__index");
    lua_setmetatable(state, -2);
    lua_setglobal(state, "Vector");
}

void RegisterFontApi(lua_State* state) {
    luaL_newmetatable(state, kFontMetatable);
    // Font is the first family that owns its native object, so its metatable needs a `__gc`:
    // it pairs `~Font()` (which only releases the Font's internal buffers) with the release of
    // the block this module allocated for it. The family unit owns both halves.
    lua_pushcfunction(state, isaac::runtime::DestroyFontHandle);
    lua_setfield(state, -2, "__gc");
    lua_newtable(state);
    static_cast<void>(isaac::runtime::AttachFontMethods(state));
    lua_setfield(state, -2, "__index");
    lua_pop(state, 1);

    lua_pushcfunction(state, isaac::runtime::CreateFontHandle);
    lua_setglobal(state, "Font");
}

#if defined(__GNUC__) && !defined(__clang__)
#pragma GCC pop_options
#endif

// --- 最小 `debug` 库（批次 3）--------------------------------------------------
//
// 只有 `debug.getinfo`，因为它是 EID 用来**直接拿到自己真实 mod 路径**的那一条：
//
//   EID:GetCurrentModPath()（main.lua:147）
//     if debug then return string.sub(debug.getinfo(EID.GetCurrentModPath).source,2) .. "/../" end
//     -- 否则退回 require("") 的 "no file '...'" 错误文本 hack
//
// `source` 就是 Lua 自己的 chunk 名：模块脚本由 `Require` 用 `"@" + 路径` 作为 chunk 名加载
// （见 `Require` 里的 `chunkNameStorage`），所以 `source` 是 `@rom:/isaac_mods/mods/<mod>/main.lua`，
// 与 PC 上"文件 chunk"的形状完全一致（PC 也是 `@路径`）。`sub(source, 2)` 去掉那个 `@`。
//
// **为什么不直接开标准 `debug`**：标准库的 `debug.sethook`/`debug.setlocal`/`debug.upvaluejoin`
// 之类能任意改写运行时状态，而 Mod 是在游戏进程里跑的；本 Runtime 一直只开
// base/coroutine/table/string/math/utf8（见 `OpenSafeLibraries`），所以这里只提供读取函数位置
// 所需的那一个入口（`getinfo` 本身是只读的）。
//
// 兼容性提醒：**存在 `debug` 这个全局会让 EID 走上面那条分支**（它只判 `if debug then`），
// 于是 `EID.modPath` 变成 `<mod 根>/main.lua/../`（而不是 require hack 算出来的
// `<mod 根>/`）。两条路径都交给引擎的文件层去解析，最终哪一条能被引擎接受要等真机验证。
int DebugGetInfo(lua_State* state) {
    const int argumentCount = lua_gettop(state);
    if (argumentCount < 1 || argumentCount > 2) {
        return luaL_error(state, "debug.getinfo accepts a function or a stack level");
    }
    lua_Debug information{};
    const bool byFunction = lua_isfunction(state, 1);
    if (byFunction) {
        // `>` 前缀让 `lua_getinfo` 从栈顶取函数（并且弹出它）。
        lua_pushvalue(state, 1);
        if (lua_getinfo(state, ">Su", &information) == 0) {
            lua_pushnil(state);
            return 1;
        }
    } else {
        if (!lua_isinteger(state, 1)) {
            // PC/Lua 的默认形态是 `debug.getinfo(level)`；缺失或 nil 视作第 1 层（调用者）。
            if (!lua_isnoneornil(state, 1)) {
                return luaL_error(state, "debug.getinfo expects a function or a stack level");
            }
        }
        const lua_Integer level =
            lua_isinteger(state, 1) ? lua_tointegerx(state, 1, nullptr) : 1;
        if (level < 0 || !lua_getstack(state, static_cast<int>(level), &information)) {
            lua_pushnil(state);  // 层级越界：Lua 的 `getinfo` 同样返回 nil
            return 1;
        }
        if (lua_getinfo(state, "Slu", &information) == 0) {
            lua_pushnil(state);
            return 1;
        }
    }
    lua_newtable(state);
    lua_pushstring(state, information.source != nullptr ? information.source : "=?");
    lua_setfield(state, -2, "source");
    lua_pushstring(state, information.short_src);
    lua_setfield(state, -2, "short_src");
    lua_pushstring(state, information.what);
    lua_setfield(state, -2, "what");
    lua_pushinteger(state, information.linedefined);
    lua_setfield(state, -2, "linedefined");
    lua_pushinteger(state, information.lastlinedefined);
    lua_setfield(state, -2, "lastlinedefined");
    lua_pushinteger(state, information.currentline);
    lua_setfield(state, -2, "currentline");
    lua_pushinteger(state, information.nups);
    lua_setfield(state, -2, "nups");
    if (!byFunction) {
        lua_pushstring(state, information.name != nullptr ? information.name : "");
        lua_setfield(state, -2, "name");
        lua_pushstring(state, information.namewhat);
        lua_setfield(state, -2, "namewhat");
    }
    return 1;
}

// 把最小 `debug` 表挂成全局。由 `PrepareRuntime` 在 Mod 脚本运行前调用一次。
void RegisterDebugLibrary(lua_State* state) {
    lua_newtable(state);
    lua_pushcfunction(state, DebugGetInfo);
    lua_setfield(state, -2, "getinfo");
    lua_setglobal(state, "debug");
}

// `os` 与 `debug` 一起注册：PC 的 Lua 环境两样都有，Mod 会无条件用（见 `RegisterOsLibrary`）。

// --- 最小 `os` 库（PC Mod 会用 `os.date` / `os.time` / `os.clock`）------------------
//
// 为什么必须补（真机报告 `01789203211`）：EID 的 `features/eid_tmtrainer.lua:199` 有一个
// 愚人节彩蛋 `if (debug and os.date("%m/%d") == "04/01") then … end`。我们提供了 `debug`
// （真值），却没有 `os`，于是 `os.date` 在索引 nil 时直接抛错 —— 整包加载死在 200 行，
// 而 EID 已经登记过回调（诊断字的种类掩码非零）、堆也用掉了 18 MiB，说明它离加载成功只差这一点。
// PC 上 `os` 与 `debug` 都在，所以这段代码在 PC 上从不出错：这是"我们的库比 PC 少"的缺口。
//
// 只实现有据可依、且无害的子集：`clock`/`date`/`difftime`/`getenv`/`setlocale`/`time`。
// **刻意不提供** `remove`/`rename`/`tmpname`/`exit`：前三个是文件系统写操作（本项目的写通道
// 尚未打通，给了只会骗调用方），`exit` 会直接把玩家的游戏结束掉。
int OsClock(lua_State* state) {
    lua_pushnumber(state, static_cast<lua_Number>(std::clock()) / CLOCKS_PER_SEC);
    return 1;
}

// `*t` 形态（`os.date("*t")`）要返回字段表；字段名与顺序照 Lua 5.3 的手册。
int PushDateTable(lua_State* state, const std::tm& value) {
    lua_createtable(state, 0, 9);
    lua_pushinteger(state, value.tm_year + 1900);
    lua_setfield(state, -2, "year");
    lua_pushinteger(state, value.tm_mon + 1);
    lua_setfield(state, -2, "month");
    lua_pushinteger(state, value.tm_mday);
    lua_setfield(state, -2, "day");
    lua_pushinteger(state, value.tm_hour);
    lua_setfield(state, -2, "hour");
    lua_pushinteger(state, value.tm_min);
    lua_setfield(state, -2, "min");
    lua_pushinteger(state, value.tm_sec);
    lua_setfield(state, -2, "sec");
    lua_pushinteger(state, value.tm_wday + 1);
    lua_setfield(state, -2, "wday");
    lua_pushinteger(state, value.tm_yday + 1);
    lua_setfield(state, -2, "yday");
    lua_pushboolean(state, value.tm_isdst > 0);
    lua_setfield(state, -2, "isdst");
    return 1;
}

int OsDate(lua_State* state) {
    const char* format = luaL_optstring(state, 1, "%c");
    const std::time_t when = static_cast<std::time_t>(
        luaL_optinteger(state, 2, static_cast<lua_Integer>(std::time(nullptr))));
    bool utc = false;
    if (format[0] == '!') {
        utc = true;
        ++format;
    }
    std::tm broken{};
    const bool ok = utc ? gmtime_r(&when, &broken) != nullptr : localtime_r(&when, &broken) != nullptr;
    if (!ok) {
        // 设备时钟读不出来时也不能报错：Mod 只是拿不到日期，不该因此整包加载失败。
        lua_pushliteral(state, "");
        return 1;
    }
    if (std::strcmp(format, "*t") == 0) {
        return PushDateTable(state, broken);
    }
    std::array<char, 256> buffer{};
    const std::size_t written = std::strftime(buffer.data(), buffer.size(), format, &broken);
    lua_pushlstring(state, buffer.data(), written);
    return 1;
}

int OsTime(lua_State* state) {
    if (lua_istable(state, 1)) {
        std::tm broken{};
        broken.tm_year = static_cast<int>(luaL_checkinteger(state, 1)) - 1900;
        const char* names[6] = {"month", "day", "hour", "min", "sec", nullptr};
        int* fields[6] = {&broken.tm_mon, &broken.tm_mday, &broken.tm_hour, &broken.tm_min,
                          &broken.tm_sec, nullptr};
        // 表里只给 year 也要能算（Lua 5.3 手册允许省略字段，缺的按 1 月 0 时 0 分 0 秒算）。
        lua_getfield(state, 1, "year");
        if (!lua_isnumber(state, -1)) {
            lua_pop(state, 1);
            return luaL_error(state, "field 'year' missing in date table");
        }
        broken.tm_year = static_cast<int>(lua_tointeger(state, -1)) - 1900;
        lua_pop(state, 1);
        for (std::size_t index = 0; names[index] != nullptr; ++index) {
            lua_getfield(state, 1, names[index]);
            *fields[index] = lua_isnumber(state, -1) ? static_cast<int>(lua_tointeger(state, -1)) : 0;
            lua_pop(state, 1);
        }
        broken.tm_mon -= 1;  // Lua 的月份从 1 开始，`std::tm` 从 0
        lua_pushinteger(state, static_cast<lua_Integer>(std::mktime(&broken)));
        return 1;
    }
    lua_pushinteger(state, static_cast<lua_Integer>(std::time(nullptr)));
    return 1;
}

int OsDifftime(lua_State* state) {
    const std::time_t later = static_cast<std::time_t>(luaL_checkinteger(state, 1));
    const std::time_t earlier = static_cast<std::time_t>(luaL_checkinteger(state, 2));
    lua_pushnumber(state, static_cast<lua_Number>(std::difftime(later, earlier)));
    return 1;
}

int OsGetenv(lua_State* state) {
    // Switch 上没有进程环境变量。返回 nil 是安全降级（Mod 拿到 nil 会走自己的默认分支）。
    luaL_checkstring(state, 1);
    lua_pushnil(state);
    return 1;
}

int OsSetlocale(lua_State* state) {
    // 引擎不做 locale 切换：只认 "C"，并把当前值报回去（与 PC 的调用形状一致）。
    luaL_optstring(state, 1, "C");
    lua_pushliteral(state, "C");
    return 1;
}

// 把最小 `os` 表挂成全局。由 `PrepareRuntime` 在 Mod 脚本运行前调用一次。
void RegisterOsLibrary(lua_State* state) {
    lua_newtable(state);
    lua_pushcfunction(state, OsClock);
    lua_setfield(state, -2, "clock");
    lua_pushcfunction(state, OsDate);
    lua_setfield(state, -2, "date");
    lua_pushcfunction(state, OsDifftime);
    lua_setfield(state, -2, "difftime");
    lua_pushcfunction(state, OsGetenv);
    lua_setfield(state, -2, "getenv");
    lua_pushcfunction(state, OsSetlocale);
    lua_setfield(state, -2, "setlocale");
    lua_pushcfunction(state, OsTime);
    lua_setfield(state, -2, "time");
    lua_setglobal(state, "os");
}

void RegisterModApi(lua_State* state) {
    g_PreparationStep.store(8, std::memory_order_relaxed);
    luaL_newmetatable(state, kModMetatable);
    lua_newtable(state);
    // Catalog-driven registration: adding an API means adding a descriptor and
    // one binding row, not another push/setfield pair. The `Mod` owner now
    // registers from its own translation unit (`interfaces/lua/mod_api.cpp`).
    // Reachability of cross-TU registration is covered by the symbol gate; see
    // the problem log for the two experiments that cleared the old suspicion.
    static_cast<void>(isaac::runtime::AttachModMethods(state));
    lua_setfield(state, -2, kModMethodsField);
    lua_pushcfunction(state, ModIndex);
    lua_setfield(state, -2, "__index");
    lua_pushcfunction(state, ModNewIndex);
    lua_setfield(state, -2, "__newindex");
    lua_pop(state, 1);

    lua_pushcfunction(state, RegisterMod);
    lua_setglobal(state, "RegisterMod");

    RegisterGameApi(state);
    RegisterMusicApi(state);
    RegisterRngApi(state);
    RegisterFontApi(state);
    // 模组开关菜单的控制面（`RuntimeMods`，运行时自己的接口，不是 PC API）：
    // 菜单脚本要用它读清单、改开关、落盘。见 `interfaces/lua/mod_menu_api.hpp`。
    static_cast<void>(isaac::runtime::RegisterModMenuApi(state));
    RegisterColorApi(state);
    RegisterVectorApi(state);
    RegisterSpriteApi(state);
    RegisterEntityRefApi(state);
    RegisterNeutralInputApi(state);
    RegisterPcLuaEnumTables(state);
    // `Isaac` 门面与 `Options` 表必须早于 Mod 脚本存在：EID 加载的第一句就是
    // `Isaac.GetItemConfig()`，随后立刻读 `Options.HUDOffset`/`Options.Language`。
    // 两族都由 `interfaces/lua/isaac_api.cpp` 自己建立表并挂成全局（见该文件的注释：
    // 这一轮只保证"存在且被调用不报错"，引擎数据要等偏移定位后再接）。
    static_cast<void>(isaac::runtime::RegisterIsaacApi(state));
    static_cast<void>(isaac::runtime::RegisterOptionsTable(state));

    // `ModCallbacks` 表：生产构建直接用生成的 PC 表（`RegisterPcLuaEnumTables` 已把它
    // 注册成全局），因为 PC Mod 会在加载阶段注册十几种回调，缺一个名字就整包失败。
    // stage13 诊断要的是"只有 POST_UPDATE"的最小表，所以那条路径覆盖回去。
    // `g_Stage13Mode` 本身只在“非诊断构建或 stage13 构建”里声明（见文件上方它自己的
    // 守卫），所以这里必须用同一个条件包起来，否则 stage14+ 的宿主 harness 编译不过。
#if !defined(EXL_DIAGNOSTIC_STAGE) || EXL_DIAGNOSTIC_STAGE == 13
    if (g_Stage13Mode) {
#if defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 13
        lua_newtable(state);
        lua_pushinteger(state, kStage13PostUpdateCallback);
        lua_setfield(state, -2, "MC_POST_UPDATE");
        lua_setglobal(state, "ModCallbacks");
#endif
    }
#endif

    // 版本判定全局：PC 引擎在忏悔版里定义 `REPENTANCE`，Mod 用它选代码分支
    // （EID 就是靠它决定走 Repentance 还是 AB+ 路径）。Switch 1.7.9b 就是忏悔版。
    // `REPENTANCE_PLUS` 刻意不定义：本体是 PC 专属更新，Mod 会按"非 Plus"处理。
    lua_pushboolean(state, 1);
    lua_setglobal(state, "REPENTANCE");

    // `json` 模块：EID 在加载阶段无条件 `require("json")`（PC 引擎自带这个模块）。
    isaac::runtime::RegisterJsonModule(state);

    // 最小 `debug` 库：EID 的 `EID:GetCurrentModPath()` 用 `debug.getinfo(fn).source` 直接
    // 取真实 mod 路径（见 `DebugGetInfo` 的注释）。必须在 Mod 脚本运行前挂好 —— EID 在
    // `main.lua:148` 的加载期就会读它。
    RegisterDebugLibrary(state);
    RegisterOsLibrary(state);

    lua_newtable(state);
    lua_pushcfunction(state, MarkPostUpdate);
    lua_setfield(state, -2, "MarkPostUpdate");
#if defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 15
    lua_pushcfunction(state, MarkPostRender);
    lua_setfield(state, -2, "MarkPostRender");
    lua_pushcfunction(state, MarkPostRenderPaused);
    lua_setfield(state, -2, "MarkPostRenderPaused");
#endif
#if defined(EXL_DIAGNOSTIC_STAGE) && (EXL_DIAGNOSTIC_STAGE == 16 || EXL_DIAGNOSTIC_STAGE == 17)
    lua_pushcfunction(state, MarkMusicDiagnosticCycleCompleted);
    lua_setfield(state, -2, "MarkMusicDiagnosticCycleCompleted");
#endif
#if defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 45
    lua_pushcfunction(state, MarkMusicDiagnosticCurrentId);
    lua_setfield(state, -2, "MarkMusicDiagnosticCurrentId");
#endif
    lua_setglobal(state, "RuntimeTest");
}

void OpenSafeLibraries(lua_State* state) {
    OpenLibrary(state, 1, "_G", luaopen_base);
    OpenLibrary(state, 2, LUA_COLIBNAME, luaopen_coroutine);
    OpenLibrary(state, 3, LUA_TABLIBNAME, luaopen_table);
    OpenLibrary(state, 4, LUA_STRLIBNAME, luaopen_string);
    OpenLibrary(state, 5, LUA_MATHLIBNAME, luaopen_math);
    OpenLibrary(state, 6, LUA_UTF8LIBNAME, luaopen_utf8);
}

int PrepareRuntime(lua_State* state) {
    OpenSafeLibraries(state);
#if !defined(EXL_DIAGNOSTIC_STAGE) || EXL_DIAGNOSTIC_STAGE == 13
    if (g_Stage13Mode) {
        g_PreparationStep.store(7, std::memory_order_relaxed);
        RegisterStage13Require(state);
    }
#endif
    RegisterModApi(state);
    return 0;
}

LuaInitResult ResetAfterFailure(lua_State* state, LuaInitResult result) {
    lua_close(state);
    g_LuaState = nullptr;
    g_CallbackRegistry.Reset();
    g_ModRegistered = false;
    g_InManagedCallbackDispatch.store(false, std::memory_order_release);
#if !defined(EXL_DIAGNOSTIC_STAGE) || EXL_DIAGNOSTIC_STAGE == 13
    ResetStage13Context();
#endif
    return result;
}

// 建立流程的**唯一实现**：建 Lua 状态 → 跑 `PrepareRuntime` → 跑自带菜单脚本。
// 成功时把 `g_LuaState`/`g_Ready` 设好（模组随后往同一个状态里追加）。
LuaInitResult EnsureRuntimeWithMenuInternal() {
    if (g_LuaState != nullptr && g_Ready.load(std::memory_order_acquire)) {
        return LuaInitResult::Success;      // 幂等
    }
    lua_State* state = luaL_newstate();
    if (state == nullptr) {
        return LuaInitResult::StateCreateFailed;
    }
    // 批次 091：**换掉分配器**换成会计数的那个（行为与 Lua 默认的 `l_alloc` 逐字相同，
    // 只是把"分配了多少次、多少字节"记下来）。用 `lua_setallocf` 而不是自己 `lua_newstate`：
    // `luaL_newstate` 还会装 panic 处理器，自己建会把那部分丢掉（语义要一字不差地保留）。
    lua_setallocf(state, IsaacRuntime_CountingAlloc, nullptr);
    // 批次 089：挂上采样剖析器（计数钩子，每 `kRuntimePerfProfileInstructionStep` 条指令一次）。
    // **只在实际设备构建里挂**：宿主门禁跑上千次 Lua 脚本，挂上去只会让套件变慢；
    // 剖析器自己的门禁会**显式**调用 `IsaacRuntime_ProfileHook` 来验行为。
#if defined(ISAAC_RUNTIME_PERF_TIMING)
    ResetRuntimePerfProfile();
    lua_sethook(state, IsaacRuntime_ProfileHook, LUA_MASKCOUNT,
                isaac::runtime::kRuntimePerfProfileInstructionStep);
    // 批次 095：顺手量一次"地板"（一次纯 Lua→C 调用要多少 tick）。
    MeasureEmptyCallCost(state);
#endif
    lua_pushcfunction(state, PrepareRuntime);
    const int preparationStatus = lua_pcallk(state, 0, 0, 0, 0, nullptr);
    if (preparationStatus != LUA_OK) {
        g_PreparationStatus.store(static_cast<u32>(preparationStatus), std::memory_order_release);
        CaptureLuaErrorTop(state);
        lua_pop(state, 1);
        return ResetAfterFailure(state, preparationStatus == LUA_ERRMEM
            ? LuaInitResult::RuntimePreparationMemoryFailed
            : LuaInitResult::RuntimePreparationFailed);
    }
    // ------------------------------------------------------------------------
    // 模组开关菜单（2026-09-16，路线 B）：在**第一个模组的入口脚本之前**跑一遍。
    // ------------------------------------------------------------------------
    //
    // 放这里的原因：菜单要用 `RegisterMod` 登记自己的回调（于是它和普通模组走同一条派发路径），
    // 而第一个模组跑完之后再登记就会排在它后面 —— 菜单的开关键要最先看到，晚了会被模组抢走。
    // 失败**不影响模组加载**：菜单出错时只把它自己关掉（脚本内部用 pcall 兜住），
    // 这里连失败都只记账、不改变返回结果。
    // 菜单**不再**在这里加载：它现在作为一个模组走标准路径（InitializeEmbeddedMenuMod），
    // 于是与真实模组共用同一套上下文/文件绑定/owner 编号（见头文件里的真机结论）。
    // 宿主 harness 里也不会再因为它多出两条回调。
    g_LuaState = state;
    g_Ready.store(true, std::memory_order_release);
    return LuaInitResult::Success;
}

LuaInitResult InitializeScript(const char* script, std::size_t length, const char* chunkName) {
    if (script == nullptr || length == 0 || chunkName == nullptr) {
        return LuaInitResult::ScriptLoadFailed;
    }
    g_PreparationStep.store(0, std::memory_order_relaxed);
    g_PreparationStatus.store(0, std::memory_order_relaxed);
    g_PostUpdateCount.store(0, std::memory_order_release);
    g_CallbackError.store(false, std::memory_order_release);
#if defined(EXL_PERSISTENCE_TRACE) || defined(EXL_PERSISTENCE_EVENT_DIAGNOSTIC)
        g_CallbackOperation.store(static_cast<u8>(CallbackOperation::None), std::memory_order_release);
    g_CallbackFailureDetail.store(0, std::memory_order_release);
#endif
#if defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 15
    g_PostRenderCount.store(0, std::memory_order_release);
    g_PostRenderPausedCount.store(0, std::memory_order_release);
#endif
#if defined(EXL_DIAGNOSTIC_STAGE) && (EXL_DIAGNOSTIC_STAGE == 16 || EXL_DIAGNOSTIC_STAGE == 17)
    g_MusicDiagnosticCycleCompleted.store(false, std::memory_order_release);
#endif
#if defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 45
    g_MusicDiagnosticCurrentIdReady.store(false, std::memory_order_release);
    g_MusicDiagnosticCurrentId.store(0, std::memory_order_release);
#endif
    const LuaInitResult ready = EnsureRuntimeWithMenuInternal();
    if (ready != LuaInitResult::Success) {
        return ready;
    }
    lua_State* state = g_LuaState;
    if (luaL_loadbufferx(state, script, length, chunkName, "t") != LUA_OK) {
        CaptureLuaErrorTop(state);
        lua_pop(state, 1);
        return ResetAfterFailure(state, LuaInitResult::ScriptLoadFailed);
    }
    if (lua_pcallk(state, 0, 0, 0, 0, nullptr) != LUA_OK) {
        CaptureLuaErrorTop(state);
        lua_pop(state, 1);
        return ResetAfterFailure(state, LuaInitResult::ScriptRunFailed);
    }
    if (g_CallbackRegistry.Count() == 0) {
        return ResetAfterFailure(state, LuaInitResult::MissingPostUpdateCallback);
    }
    // `g_LuaState`/`g_Ready` 由 `EnsureRuntimeWithMenuInternal()` 设好（模组只是往同一个状态里追加）。
    return LuaInitResult::Success;
}

} // namespace


// 对外入口（`lua_runtime.hpp` 声明的那一个）：匿名命名空间里的实现不导出符号，所以这层是必须的。
// 幂等：已经有状态就直接成功。
LuaInitResult EnsureRuntimeWithMenu() noexcept {
    if (g_LuaState != nullptr && g_Ready.load(std::memory_order_acquire)) {
        return LuaInitResult::Success;
    }
    return EnsureRuntimeWithMenuInternal();
}
// 把**任意** Lua 值记成可读文本（2026-09-12，见头文件里的长注释）。
//
// 与下面 `CaptureLuaErrorTop` 的区别：那个只在"栈顶是字符串"时成功，而这个**保证**产出文本
// ——`luaL_tolstring` 接受任意类型（表/函数/userdata 会走 `__tostring` 或类型名），并且它
// 自己把结果压栈、由我们弹掉。为什么需要它：真机的 `errorLength` 与内容长期不一致
// （`= 1` 却读出上一条消息的残渣），根因就是错误值不是字符串时旧通道直接放弃记录。
void RecordLuaErrorValue(lua_State* state) noexcept {
    if (state == nullptr || lua_gettop(state) == 0) {
        return;
    }
    if (lua_type(state, -1) == LUA_TSTRING) {
        CaptureLuaErrorTop(state);
        return;
    }
    // `luaL_tolstring` 把任意值转成字符串并压栈；失败（内存不足等）时返回 nullptr。
    const char* text = luaL_tolstring(state, -1, nullptr);
    if (text != nullptr) {
        const std::size_t length = std::strlen(text);
        if (length != 0) {
            RecordLuaErrorText(text, length);
        }
    }
    lua_pop(state, 1);  // 弹掉 `luaL_tolstring` 压入的字符串
}

// `luaL_error` 的替代实现：**先记录整段消息，再真正抛错**。
//
// 为什么要经过它：`luaL_error` 生成的消息就是最终文本（`luaL_where` 的 `file:line:` 前缀
// + 格式化后的消息），在抛错**之前**把它记下来，报告侧读到的就是消息本体；而旧通道依赖
// 事后从栈上 `lua_tostring`，对非字符串错误值会静默失败。
int ReportAndRecordLuaError(lua_State* state, const char* format, ...) {
    char message[256] = {};
    va_list args;
    va_start(args, format);
    const int written = std::vsnprintf(message, sizeof(message), format, args);
    va_end(args);
    const std::size_t messageLength =
        written > 0 ? (static_cast<std::size_t>(written) < sizeof(message)
                           ? static_cast<std::size_t>(written)
                           : sizeof(message) - 1)
                    : 0;
    // ★★ **必须把 `luaL_where` 的位置前缀也记上**（2026-09-12 第九稿，这是"以前能拿到完整
    // 报错、现在拿不到"的真正原因）。
    //
    // 最早那几轮报告里，错误文本是 `eid_api.lua:2606: attempt to call a nil value (method
    // 'GetPill')` —— **带 `file:line:` 前缀**。那是因为那时的捕获发生在 `luaL_error`
    // **已经构造好完整文本之后**（从栈上取）。而本函数改成"抛错前记录"时，只记了
    // `message`（也就是格式化后的消息本体），**前缀被漏掉了**；遇到本项目的调用点
    // （消息都很简短）时，记下来的就只剩几个字节。
    //
    // `luaL_error` 内部就是这么拼的：`luaL_where(L, 1)` + 消息。这里照抄同样的形状，
    // 记录的内容才与引擎真正抛出的文本一致。
    char full[320] = {};
    luaL_where(state, 1);
    const char* where = lua_tostring(state, -1);
    const std::size_t whereLength = where != nullptr ? std::strlen(where) : 0;
    const std::size_t copyWhere = whereLength < sizeof(full) ? whereLength : sizeof(full) - 1;
    if (copyWhere != 0) {
        std::memcpy(full, where, copyWhere);
    }
    lua_pop(state, 1);  // 弹掉 `luaL_where` 压入的字符串
    const std::size_t remaining = sizeof(full) - 1 - copyWhere;
    const std::size_t copyMessage = messageLength < remaining ? messageLength : remaining;
    if (copyMessage != 0) {
        std::memcpy(full + copyWhere, message, copyMessage);
    }
    if (copyWhere + copyMessage != 0) {
        RecordLuaErrorText(full, copyWhere + copyMessage);
    }
    // 再交给真正的 `luaL_error`（它会自己再加一次位置前缀并 `lua_error` 长跳）。
    // 这里**不能**用宏（否则递归），所以要 `#undef` 后再调。
#pragma push_macro("luaL_error")
#undef luaL_error
    return luaL_error(state, "%s", message);
#pragma pop_macro("luaL_error")
}


void RecordCallbackOperation(CallbackOperation operation) noexcept {
#if defined(EXL_PERSISTENCE_TRACE) || defined(EXL_PERSISTENCE_EVENT_DIAGNOSTIC)
    if (g_InManagedCallbackDispatch.load(std::memory_order_acquire)) {
        g_CallbackOperation.store(static_cast<u8>(operation), std::memory_order_release);
    }
#else
    static_cast<void>(operation);
#endif
}

bool CallbackErrorPending() noexcept {
    return g_CallbackError.load(std::memory_order_acquire);
}

std::uint64_t LastLuaErrorHead(std::uint32_t* length) noexcept {
    const std::uint32_t stored = g_LastLuaErrorLength.load(std::memory_order_acquire);
    if (length != nullptr) {
        *length = stored;
    }
    std::uint64_t head = 0;
    const std::size_t copyLength = stored < 8 ? stored : 8;
    std::memcpy(&head, g_LastLuaErrorText.data(), copyLength);
    return head;
}

// 把最近一次捕获的 Lua 错误文本**整段**拷给调用方（诊断用，探针要的就是它）。
//
// 为什么需要它：真机报告 `01789201566` 只说"main.lua 运行期出错"（诊断字 `[11] = 0x515`
// = `LuaInit` + detail 5 = `ScriptRunFailed`）并给出了错误信息的**前 8 字节**
// （`"..._mods"`——Lua 5.3.3 的 `luaO_chunkid` 把 66 字符的入口路径截成 "...+末 57 字符"，
// 于是信息头正好落在这个位置），但真正要的是**行号 + 消息**，那在后面的 94 个字节里。
// 只带 8 字节等于又白跑一轮，所以补上整段文本的读取口。
// 模块的假堆已经用了多少字节（诊断用）。
//
// `EXL_USE_FAKEHEAP` 让 newlib 的 `fake_heap_start/end` 指向 `init.cpp` 里那块 .bss 数组
// （大小 = `exl::setting::HeapSize`）—— **整个模块的 malloc 只有这一个来源**，Lua 状态也在里面。
// `sbrk(0)` 给出当前堆顶，减掉数组起点就是"已经向堆要过多少"（堆只增不减，所以它同时是峰值）。
//
// 为什么要读它：真机报告 `01789202408` 里 Lua 抛 `LUA_ERRMEM`（"not enough memory"），
// 而当时堆只有 2 MiB。把用量报出来，才能判断"32 MiB 够不够"，而不是靠猜。
std::size_t HeapUsedBytes() noexcept {
#if defined(__SWITCH__) && defined(EXL_USE_FAKEHEAP)
    const auto top = reinterpret_cast<std::uintptr_t>(sbrk(0));
    const auto base = reinterpret_cast<std::uintptr_t>(__fake_heap);
    return top > base ? static_cast<std::size_t>(top - base) : 0;
#else
    return 0;
#endif
}

void RequireFailureSnapshot(RequireFailureView* view) noexcept {
    if (view == nullptr) {
        return;
    }
    view->firstCode = g_RequireFirstFailureCode.load(std::memory_order_acquire);
    view->firstNameHead = g_RequireFirstFailureName.load(std::memory_order_acquire);
    view->lastCode = g_RequireLastFailureCode.load(std::memory_order_acquire);
    view->lastNameHead = g_RequireLastFailureName.load(std::memory_order_acquire);
    view->total = g_RequireFailureTotal.load(std::memory_order_acquire);
}

//: 批次 068：环形历史的只读访问器（口径见 `lua_runtime.hpp`）。**必须与 `g_LuaErrorHistory`
//: 的布局保持一致** —— 调试桩是按符号直读那块内存的，两边不一致就会出现"工具读到的与
//: 测试断言的不同"这种最难查的偏差（`static_assert` 已经钉住 128 字节/条）。
std::size_t CopyLuaErrorHistory(LuaErrorHistoryEntryView* output,
                                std::size_t capacity) noexcept {
    if (output == nullptr || capacity == 0) {
        return 0;
    }
    std::size_t written = 0;
    for (std::size_t slot = 0; slot < kLuaErrorHistorySlots && written < capacity; ++slot) {
        const LuaErrorHistoryEntry& entry = g_LuaErrorHistory[slot];
        if (entry.text[0] == '\0') {
            continue;
        }
        LuaErrorHistoryEntryView& view = output[written];
        view.owner = entry.owner;
        view.callbackId = entry.callbackId;
        std::memcpy(view.text, entry.text, sizeof(view.text));
        view.text[sizeof(view.text) - 1] = '\0';
        ++written;
    }
    return written;
}

std::size_t CopyLastLuaErrorText(char* output, std::size_t capacity) noexcept {
    if (output == nullptr || capacity == 0) {
        return 0;
    }
    const std::uint32_t stored = g_LastLuaErrorLength.load(std::memory_order_acquire);
    std::size_t copyLength = stored;
    if (copyLength > g_LastLuaErrorText.size()) {
        copyLength = g_LastLuaErrorText.size();
    }
    if (copyLength > capacity) {
        copyLength = capacity;
    }
    // ★ **先把缓冲区清零再拷**（2026-09-12，真机报告 `01789225234`：`errorLength = 1`，
    // 但报告里读到的 16 字节却是**上一次**残留的 `file name string` —— 因为调用方只拷
    // `copyLength` 字节，剩下的位置留着旧消息，而报告侧的"错误文本尾部"会把它们当成消息）。
    // 清零之后，凡是超出 `errorLength` 的位置都是 0，报告侧一眼就能看出"这段没有内容"。
    std::memset(output, 0, capacity);
    if (copyLength != 0) {
        std::memcpy(output, g_LastLuaErrorText.data(), copyLength);
    }
    return copyLength;
}

void RecordLuaErrorText(const char* text, std::size_t length) noexcept {
    if (text == nullptr || length == 0) {
        return;
    }
    if (length > g_LastLuaErrorText.size()) {
        length = g_LastLuaErrorText.size();
    }
    std::memcpy(g_LastLuaErrorText.data(), text, length);
    g_LastLuaErrorLength.store(static_cast<std::uint32_t>(length), std::memory_order_release);
}

bool InManagedCallbackScope() noexcept {
    return g_InManagedCallbackDispatch.load(std::memory_order_acquire);
}

std::uintptr_t GameOwnerSlot() noexcept {
    return g_GameOwnerSlot.load(std::memory_order_acquire);
}

std::uintptr_t EngineModuleBase() noexcept {
    return g_EngineModuleBase.load(std::memory_order_acquire);
}

std::uintptr_t GameIsPausedThunk() noexcept {
    return g_GameIsPausedThunk.load(std::memory_order_acquire);
}

std::uintptr_t GameIsGreedModeThunk() noexcept {
    return g_GameIsGreedMode.load(std::memory_order_acquire);
}

std::uintptr_t LevelIsAscentThunk() noexcept {
    return g_LevelIsAscent.load(std::memory_order_acquire);
}

std::uintptr_t LevelGetAbsoluteStageThunk() noexcept {
    return g_LevelGetAbsoluteStage.load(std::memory_order_acquire);
}

// 2026-09-16：`Room:GetFrameCount()` 的入口（安装期校验 16 字节后发布；0 = 不可用）。
std::uintptr_t RoomGetFrameCountThunk() noexcept {
    return g_RoomGetFrameCount.load(std::memory_order_acquire);
}

// 2026-09-21：PC 的 `GridEntity.Position` 要调的引擎函数入口（0 = 守卫没过/不可用）。
std::uintptr_t GridEntityGetPositionThunk() noexcept {
    return g_GridEntityGetPosition.load(std::memory_order_acquire);
}

std::uintptr_t LevelIsNextStageAvailableThunk() noexcept {
    return g_LevelIsNextStageAvailable.load(std::memory_order_acquire);
}

std::uintptr_t GetRenderPositionThunk() noexcept {
    return g_GetRenderPosition.load(std::memory_order_acquire);
}

#if !defined(__SWITCH__)
void SetGetRenderPositionHostFunction(RenderPositionHostFunction function) noexcept {
    g_GetRenderPositionHost = function;
}

RenderPositionHostFunction GetRenderPositionHostFunction() noexcept {
    return g_GetRenderPositionHost;
}

void SetRoomGetFrameCountHostFunction(RoomFrameCountHostFunction function) noexcept {
    g_RoomGetFrameCountHost = function;
}

RoomFrameCountHostFunction GetRoomGetFrameCountHostFunction() noexcept {
    return g_RoomGetFrameCountHost;
}

// 2026-09-21：`GridEntity.Position` 的宿主注入（宿主没有引擎映像；与上面两条同一形态）。
void SetGridEntityGetPositionHostFunction(GridEntityPositionHostFunction function) noexcept {
    g_GridEntityGetPositionHost = function;
}

GridEntityPositionHostFunction GetGridEntityGetPositionHostFunction() noexcept {
    return g_GridEntityGetPositionHost;
}
#endif

std::uintptr_t ItemPoolGetCollectibleThunk() noexcept {
    return g_ItemPoolGetCollectible.load(std::memory_order_acquire);
}

std::uintptr_t MusicGetCurrentMusicIdThunk() noexcept {
    return g_MusicGetCurrentMusicId.load(std::memory_order_acquire);
}

std::uintptr_t MusicPauseThunk() noexcept {
    return g_MusicPause.load(std::memory_order_acquire);
}

std::uintptr_t MusicResumeThunk() noexcept {
    return g_MusicResume.load(std::memory_order_acquire);
}

std::uintptr_t RngSetSeedThunk() noexcept {
    return g_RngSetSeed.load(std::memory_order_acquire);
}

std::uintptr_t InputIsActionPressedThunk() noexcept {
    return g_InputIsActionPressed.load(std::memory_order_acquire);
}

std::uintptr_t InputIsActionTriggeredThunk() noexcept {
    return g_InputIsActionTriggered.load(std::memory_order_acquire);
}

std::uintptr_t InputGetActionValueThunk() noexcept {
    return g_InputGetActionValue.load(std::memory_order_acquire);
}

std::uintptr_t RngNextThunk() noexcept {
    return g_RngNext.load(std::memory_order_acquire);
}

FontCtorFn FontCtorThunk() noexcept {
    return reinterpret_cast<FontCtorFn>(g_FontCtor.load(std::memory_order_acquire));
}

FontDestructorFn FontDestructorThunk() noexcept {
    return reinterpret_cast<FontDestructorFn>(g_FontDestructor.load(std::memory_order_acquire));
}

FontLoadFn FontLoadThunk() noexcept {
    return reinterpret_cast<FontLoadFn>(g_FontLoad.load(std::memory_order_acquire));
}

FontUnloadFn FontUnloadThunk() noexcept {
    return reinterpret_cast<FontUnloadFn>(g_FontUnload.load(std::memory_order_acquire));
}

FontIsLoadedFn FontIsLoadedThunk() noexcept {
    return reinterpret_cast<FontIsLoadedFn>(g_FontIsLoaded.load(std::memory_order_acquire));
}

FontGetStringWidthFn FontGetStringWidthThunk() noexcept {
    return reinterpret_cast<FontGetStringWidthFn>(
        g_FontGetStringWidth.load(std::memory_order_acquire));
}

FontGetStringWidthUTF8Fn FontGetStringWidthUTF8Thunk() noexcept {
    return reinterpret_cast<FontGetStringWidthUTF8Fn>(
        g_FontGetStringWidthUTF8.load(std::memory_order_acquire));
}

FontGetLineHeightFn FontGetLineHeightThunk() noexcept {
    return reinterpret_cast<FontGetLineHeightFn>(
        g_FontGetLineHeight.load(std::memory_order_acquire));
}

FontGetBaselineHeightFn FontGetBaselineHeightThunk() noexcept {
    return reinterpret_cast<FontGetBaselineHeightFn>(
        g_FontGetBaselineHeight.load(std::memory_order_acquire));
}

FontGetCharacterWidthFn FontGetCharacterWidthThunk() noexcept {
    return reinterpret_cast<FontGetCharacterWidthFn>(
        g_FontGetCharacterWidth.load(std::memory_order_acquire));
}

FontSetMissingCharacterFn FontSetMissingCharacterThunk() noexcept {
    return reinterpret_cast<FontSetMissingCharacterFn>(
        g_FontSetMissingCharacter.load(std::memory_order_acquire));
}

FontDrawStringScaledFn FontDrawStringScaledThunk() noexcept {
    return reinterpret_cast<FontDrawStringScaledFn>(
        g_FontDrawStringScaled.load(std::memory_order_acquire));
}

FontDrawStringUTF8Fn FontDrawStringUTF8Thunk() noexcept {
    return reinterpret_cast<FontDrawStringUTF8Fn>(
        g_FontDrawStringUTF8.load(std::memory_order_acquire));
}

FontDrawStringScaledUTF8Fn FontDrawStringScaledUTF8Thunk() noexcept {
    return reinterpret_cast<FontDrawStringScaledUTF8Fn>(
        g_FontDrawStringScaledUTF8.load(std::memory_order_acquire));
}

FontDrawStringFn FontDrawStringThunk() noexcept {
    return reinterpret_cast<FontDrawStringFn>(g_FontDrawString.load(std::memory_order_acquire));
}

SpriteCtorFn SpriteCtorThunk() noexcept {
    return reinterpret_cast<SpriteCtorFn>(g_SpriteCtor.load(std::memory_order_acquire));
}
SpriteDestructorFn SpriteDestructorThunk() noexcept {
    return reinterpret_cast<SpriteDestructorFn>(g_SpriteDestructor.load(std::memory_order_acquire));
}
SpritePlayFn SpritePlayThunk() noexcept {
    return reinterpret_cast<SpritePlayFn>(g_SpritePlay.load(std::memory_order_acquire));
}
SpriteSetAnimationFn SpriteSetAnimationThunk() noexcept {
    return reinterpret_cast<SpriteSetAnimationFn>(
        g_SpriteSetAnimation.load(std::memory_order_acquire));
}
SpriteSetFrameNamedFn SpriteSetFrameNamedThunk() noexcept {
    return reinterpret_cast<SpriteSetFrameNamedFn>(
        g_SpriteSetFrameNamed.load(std::memory_order_acquire));
}
SpriteSetFrameFn SpriteSetFrameThunk() noexcept {
    return reinterpret_cast<SpriteSetFrameFn>(g_SpriteSetFrame.load(std::memory_order_acquire));
}
SpriteGetFrameFn SpriteGetFrameThunk() noexcept {
    return reinterpret_cast<SpriteGetFrameFn>(g_SpriteGetFrame.load(std::memory_order_acquire));
}
SpriteSetLayerFrameFn SpriteSetLayerFrameThunk() noexcept {
    return reinterpret_cast<SpriteSetLayerFrameFn>(
        g_SpriteSetLayerFrame.load(std::memory_order_acquire));
}
SpriteGetLayerFrameFn SpriteGetLayerFrameThunk() noexcept {
    return reinterpret_cast<SpriteGetLayerFrameFn>(
        g_SpriteGetLayerFrame.load(std::memory_order_acquire));
}
SpriteGetTexelFn SpriteGetTexelThunk() noexcept {
    return reinterpret_cast<SpriteGetTexelFn>(g_SpriteGetTexel.load(std::memory_order_acquire));
}
SpriteUpdateFn SpriteUpdateThunk() noexcept {
    return reinterpret_cast<SpriteUpdateFn>(g_SpriteUpdate.load(std::memory_order_acquire));
}
SpriteIsPlayingFn SpriteIsPlayingThunk() noexcept {
    return reinterpret_cast<SpriteIsPlayingFn>(g_SpriteIsPlaying.load(std::memory_order_acquire));
}
SpriteIsFinishedFn SpriteIsFinishedThunk() noexcept {
    return reinterpret_cast<SpriteIsFinishedFn>(g_SpriteIsFinished.load(std::memory_order_acquire));
}
SpriteRenderFn SpriteRenderThunk() noexcept {
    return reinterpret_cast<SpriteRenderFn>(g_SpriteRender.load(std::memory_order_acquire));
}
SpriteRenderLayerFn SpriteRenderLayerThunk() noexcept {
    return reinterpret_cast<SpriteRenderLayerFn>(
        g_SpriteRenderLayer.load(std::memory_order_acquire));
}
SpritePlayRandomFn SpritePlayRandomThunk() noexcept {
    return reinterpret_cast<SpritePlayRandomFn>(g_SpritePlayRandom.load(std::memory_order_acquire));
}

SpriteLoadFn SpriteLoadThunk() noexcept {
    return reinterpret_cast<SpriteLoadFn>(g_SpriteLoad.load(std::memory_order_acquire));
}

SpriteLoadGraphicsFn SpriteLoadGraphicsThunk() noexcept {
    return reinterpret_cast<SpriteLoadGraphicsFn>(
        g_SpriteLoadGraphics.load(std::memory_order_acquire));
}

SpriteReplaceSpritesheetFn SpriteReplaceSpritesheetThunk() noexcept {
    return reinterpret_cast<SpriteReplaceSpritesheetFn>(
        g_SpriteReplaceSpritesheet.load(std::memory_order_acquire));
}

LibcxxStringAssignFn LibcxxStringAssignThunk() noexcept {
    return reinterpret_cast<LibcxxStringAssignFn>(
        g_LibcxxStringAssign.load(std::memory_order_acquire));
}

GameOperatorDeleteFn GameOperatorDeleteThunk() noexcept {
    return reinterpret_cast<GameOperatorDeleteFn>(
        g_GameOperatorDelete.load(std::memory_order_acquire));
}

bool ValidateItemPoolGetCollectibleBinding(std::uintptr_t address) noexcept {
    return ValidateItemPoolGetCollectibleMethod(address);
}

bool ResolveMusicGetCurrentMusicId(std::uintptr_t method, std::uintptr_t* music) noexcept {
    return ResolveMusicForCall(method, kMusicGetCurrentMusicIdExpectedBytes.data(),
                               kMusicGetCurrentMusicIdExpectedBytes.size(), music);
}

bool ResolveMusicPause(std::uintptr_t method, std::uintptr_t* music) noexcept {
    return ResolveMusicForCall(method, kMusicPauseExpectedBytes.data(),
                               kMusicPauseExpectedBytes.size(), music);
}

bool ResolveMusicResume(std::uintptr_t method, std::uintptr_t* music) noexcept {
    return ResolveMusicForCall(method, kMusicResumeExpectedBytes.data(),
                               kMusicResumeExpectedBytes.size(), music);
}

bool ValidateRngSetSeedBinding(std::uintptr_t address) noexcept {
    return ValidateMusicMethod(address, kRngSetSeedExpectedBytes.data(),
                               kRngSetSeedExpectedBytes.size());
}

bool ValidateRngNextBinding(std::uintptr_t address) noexcept {
    return ValidateMusicMethod(address, kRngNextExpectedBytes.data(),
                               kRngNextExpectedBytes.size());
}

isaac::runtime::CallbackRegistry& ManagedCallbackRegistry() noexcept {
    return g_CallbackRegistry;
}

isaac::runtime::ModHandle RuntimeOwnerHandle() noexcept {
    return kRuntimeOwner;
}

isaac::runtime::ModHandle UnpackModOwner(std::uint32_t packed) noexcept {
    return isaac::runtime::ModHandle{static_cast<std::uint16_t>(packed & 0xFFFFU),
                                     static_cast<std::uint16_t>(packed >> 16)};
}

// Read by `interfaces/lua/mod_api.cpp` when it maps a Lua `ModCallbacks` value
// onto a catalog callback id: the Stage13 diagnostic only allows its own
// POST_UPDATE phase.
bool IsStage13CallbackMode() noexcept {
#if defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 13
    return g_Stage13Mode;
#else
    return false;
#endif
}

LuaInitResult InitializeFromBuffer(const char* script, std::size_t length, const char* chunkName) {
    return InitializeScript(script, length, chunkName);
}

#if !defined(EXL_DIAGNOSTIC_STAGE) || EXL_DIAGNOSTIC_STAGE == 13
// 把内嵌菜单当成"第一个模组"加载（见头文件说明）。它内部就是标准的模组初始化路径，
// 所以菜单与真实模组在上下文、文件绑定、owner 编号、回调派发上是同一套东西。
LuaInitResult InitializeEmbeddedMenuMod(const char* modRoot,
                                        const GameFileReader::Bindings& bindings) noexcept {
    return InitializeManifestMod(isaac::runtime::kEmbeddedModMenuScript.data(),
                                 isaac::runtime::kEmbeddedModMenuScript.size(),
                                 isaac::runtime::kModMenuChunkName, modRoot, bindings);
}

LuaInitResult InitializeManifestMod(const char* entry, std::size_t entryLength,
                                    const char* chunkName, const char* modRoot,
                                    const GameFileReader::Bindings& bindings) {
    g_RequireFailureDetail.store(0, std::memory_order_release);
    g_RequireErrorTail.store(0, std::memory_order_release);
    g_RequireFirstFailureCode.store(0, std::memory_order_release);
    g_RequireFirstFailureName.store(0, std::memory_order_release);
    g_RequireLastFailureCode.store(0, std::memory_order_release);
    g_RequireLastFailureName.store(0, std::memory_order_release);
    g_RequireFailureTotal.store(0, std::memory_order_release);
    if (entry == nullptr || entryLength == 0 || chunkName == nullptr ||
        !SetStage13Context(modRoot, bindings)) {
        RecordRequireFailure(19);
        ResetStage13Context();
        return LuaInitResult::ScriptLoadFailed;
    }

    // ------------------------------------------------------------------------
    // 多模组（2026-09-16）：已经有 Lua 状态时，这一份脚本**追加**进同一个状态执行。
    // ------------------------------------------------------------------------
    //
    // PC 的语义就是这样：多个 Mod 共享**一个** Lua 状态（同一个 `Isaac`、同一张全局表、
    // 同一份回调登记表），各 Mod 的入口脚本按清单里的顺序依次执行。此前这里无条件
    // `luaL_newstate()`，于是第二个 Mod 会把第一个 Mod 的状态整个丢掉 —— 症状不是"只加载一个"，
    // 而是"只剩最后一个"。
    //
    // 追加路径与首建路径的区别只有三点，其余一律相同：
    //   * 不重建状态、不重跑 `PrepareRuntime`（那些全局已经在，重跑只会重复注册）；
    //   * 不要求"必须登记了回调"—— 只声明命名回调、或者干脆什么都不登记的 Mod 是合法的；
    //   * 失败时**不关掉**状态：已经跑起来的 Mod 不该因为后来者出错而一起消失
    //     （PC 上一个 Mod 的加载错误也不会把别的 Mod 卸载掉）。
    //
    // `require` 的根逐 Mod 重设（上面那句 `SetStage13Context` 已经做过），所以入口脚本里的
    // `require` 按各自的 Mod 目录解析。⚠️ 已知局限：**运行期**（回调里）的 `require` 用的是
    // 最后一次设置的根；多模组下这意味着后加载的 Mod 的目录。记录见
    // `docs/问题与解决记录.md`，后续要做"按调用者所在 chunk 解析"才能彻底对齐 PC。
    if (g_LuaState != nullptr && g_Ready.load(std::memory_order_acquire)) {
        lua_State* state = g_LuaState;
        if (luaL_loadbufferx(state, entry, entryLength, chunkName, "t") != LUA_OK) {
            CaptureLuaErrorTop(state);
            lua_pop(state, 1);
            RecordRequireFailure(22);
            return LuaInitResult::ScriptLoadFailed;
        }
        if (lua_pcallk(state, 0, 0, 0, 0, nullptr) != LUA_OK) {
            CaptureLuaErrorTop(state);
            lua_pop(state, 1);
            return LuaInitResult::ScriptRunFailed;
        }
        return LuaInitResult::Success;
    }

    g_Ready.store(false, std::memory_order_release);
    g_CallbackError.store(false, std::memory_order_release);
    g_PostUpdateCount.store(0, std::memory_order_release);
    const LuaInitResult result = InitializeScript(entry, entryLength, chunkName);
    if (result != LuaInitResult::Success) {
        ResetStage13Context();
    }
    return result;
}

#if defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 13
LuaInitResult InitializeStage13Mod(const char* entry, std::size_t entryLength,
                                   const char* chunkName, const char* modRoot,
                                   const GameFileReader::Bindings& bindings) {
    return InitializeManifestMod(entry, entryLength, chunkName, modRoot, bindings);
}

u32 RequireFailureDetail() {
    return g_RequireFailureDetail.load(std::memory_order_acquire);
}

u64 RequireErrorTail() {
    return g_RequireErrorTail.load(std::memory_order_acquire);
}
#endif
#endif

LuaInitResult Initialize() {
    return InitializeScript(kEmbeddedLuaTestScript, std::strlen(kEmbeddedLuaTestScript), "@runtime_test.lua");
}

u32 PreparationFailureDetail() {
    const u32 step = g_PreparationStep.load(std::memory_order_acquire);
    const u32 status = g_PreparationStatus.load(std::memory_order_acquire);
    return (step << 8) | (status & 0xFF);
}

void SetGameBindings(uintptr_t ownerSlot, uintptr_t isPausedThunk) {
    g_GameOwnerSlot.store(ownerSlot, std::memory_order_release);
    g_GameIsPausedThunk.store(isPausedThunk, std::memory_order_release);
}

// 游戏本体模块基址：与 `SetGameBindings` 同一种发布方式（Hook 安装阶段调用一次）。
void SetEngineModuleBase(uintptr_t base) noexcept {
    g_EngineModuleBase.store(base, std::memory_order_release);
}

void SetInputBindings(uintptr_t isActionPressed, uintptr_t isActionTriggered,
                      uintptr_t getActionValue) {
    g_InputIsActionPressed.store(isActionPressed, std::memory_order_release);
    g_InputIsActionTriggered.store(isActionTriggered, std::memory_order_release);
    g_InputGetActionValue.store(getActionValue, std::memory_order_release);
}

void SetGameIsGreedModeBinding(uintptr_t method) {
    g_GameIsGreedMode.store(method, std::memory_order_release);
}

void SetLevelIsAscentBinding(uintptr_t method) {
    g_LevelIsAscent.store(method, std::memory_order_release);
}

// 批次 8（2026-09-15）：两个新绑定的发布点。与 `SetLevelIsAscentBinding` 同一种形态：
// 各自一条 release 存储，handler 各自一条 acquire 读 —— 不会出现"半个已校验记录"。
void SetGetRenderPositionBinding(uintptr_t method) {
    g_GetRenderPosition.store(method, std::memory_order_release);
}

void SetLevelGetAbsoluteStageBinding(uintptr_t method) {
    g_LevelGetAbsoluteStage.store(method, std::memory_order_release);
}

void SetLevelIsNextStageAvailableBinding(uintptr_t method) {
    g_LevelIsNextStageAvailable.store(method, std::memory_order_release);
}

// 2026-09-16：`Room:GetFrameCount()` 的发布点，与上面两条同形（一次 release 存储，
// handler 一次 acquire 读，不会看到"半个已校验记录"）。
void SetRoomGetFrameCountBinding(uintptr_t method) {
    g_RoomGetFrameCount.store(method, std::memory_order_release);
}

// 2026-09-21：`GridEntity::GetPosition()` 的发布点，与上面几条同形（一次 release 存储、
// handler 一次 acquire 读 ⇒ 不会看到"半个已校验记录"）。
void SetGridEntityGetPositionBinding(uintptr_t method) {
    g_GridEntityGetPosition.store(method, std::memory_order_release);
}

void SetItemPoolGetCollectibleBinding(uintptr_t method) {
    g_ItemPoolGetCollectible.store(method, std::memory_order_release);
}

void SetMusicBindings(uintptr_t getCurrentMusicId, uintptr_t pause, uintptr_t resume) {
    g_MusicGetCurrentMusicId.store(getCurrentMusicId, std::memory_order_release);
    g_MusicPause.store(pause, std::memory_order_release);
    g_MusicResume.store(resume, std::memory_order_release);
}

#if defined(__GNUC__) && !defined(__clang__)
#pragma GCC push_options
#pragma GCC optimize ("Os")
#endif

void SetRngBindings(uintptr_t setSeed, uintptr_t next) {
    g_RngSetSeed.store(setSeed, std::memory_order_release);
    g_RngNext.store(next, std::memory_order_release);
}

// Published as one record and stored field by field: the handlers read each entry point with its
// own acquire load, so a partially verified record never mixes a verified and an unverified
// address inside a single call.
void SetFontBindings(const LuaFontBindings& bindings) {
    g_FontCtor.store(reinterpret_cast<std::uintptr_t>(bindings.ctor),
                     std::memory_order_release);
    g_FontDestructor.store(reinterpret_cast<std::uintptr_t>(bindings.destructor_),
                           std::memory_order_release);
    g_FontLoad.store(reinterpret_cast<std::uintptr_t>(bindings.load),
                     std::memory_order_release);
    g_FontUnload.store(reinterpret_cast<std::uintptr_t>(bindings.unload),
                       std::memory_order_release);
    g_FontIsLoaded.store(reinterpret_cast<std::uintptr_t>(bindings.isLoaded),
                         std::memory_order_release);
    g_FontGetStringWidth.store(reinterpret_cast<std::uintptr_t>(bindings.getStringWidth),
                               std::memory_order_release);
    g_FontGetStringWidthUTF8.store(reinterpret_cast<std::uintptr_t>(bindings.getStringWidthUTF8),
                                   std::memory_order_release);
    g_FontGetLineHeight.store(reinterpret_cast<std::uintptr_t>(bindings.getLineHeight),
                              std::memory_order_release);
    g_FontGetBaselineHeight.store(reinterpret_cast<std::uintptr_t>(bindings.getBaselineHeight),
                                  std::memory_order_release);
    g_FontGetCharacterWidth.store(reinterpret_cast<std::uintptr_t>(bindings.getCharacterWidth),
                                  std::memory_order_release);
    g_FontSetMissingCharacter.store(reinterpret_cast<std::uintptr_t>(bindings.setMissingCharacter),
                                    std::memory_order_release);
    g_FontDrawString.store(reinterpret_cast<std::uintptr_t>(bindings.drawString),
                           std::memory_order_release);
    g_FontDrawStringScaled.store(reinterpret_cast<std::uintptr_t>(bindings.drawStringScaled),
                                 std::memory_order_release);
    g_FontDrawStringUTF8.store(reinterpret_cast<std::uintptr_t>(bindings.drawStringUTF8),
                               std::memory_order_release);
    g_FontDrawStringScaledUTF8.store(reinterpret_cast<std::uintptr_t>(bindings.drawStringScaledUTF8),
                                     std::memory_order_release);
}

void SetSpriteBindings(const LuaSpriteBindings& bindings) {
    g_SpriteCtor.store(reinterpret_cast<std::uintptr_t>(bindings.ctor),
                       std::memory_order_release);
    g_SpriteDestructor.store(reinterpret_cast<std::uintptr_t>(bindings.destructor_),
                             std::memory_order_release);
    g_SpritePlay.store(reinterpret_cast<std::uintptr_t>(bindings.play),
                       std::memory_order_release);
    g_SpriteSetAnimation.store(reinterpret_cast<std::uintptr_t>(bindings.setAnimation),
                               std::memory_order_release);
    g_SpriteSetFrameNamed.store(reinterpret_cast<std::uintptr_t>(bindings.setFrameNamed),
                                std::memory_order_release);
    g_SpriteSetFrame.store(reinterpret_cast<std::uintptr_t>(bindings.setFrame),
                           std::memory_order_release);
    g_SpriteGetFrame.store(reinterpret_cast<std::uintptr_t>(bindings.getFrame),
                           std::memory_order_release);
    g_SpriteSetLayerFrame.store(reinterpret_cast<std::uintptr_t>(bindings.setLayerFrame),
                                std::memory_order_release);
    g_SpriteGetLayerFrame.store(reinterpret_cast<std::uintptr_t>(bindings.getLayerFrame),
                                std::memory_order_release);
    g_SpriteGetTexel.store(reinterpret_cast<std::uintptr_t>(bindings.getTexel),
                           std::memory_order_release);
    g_SpriteUpdate.store(reinterpret_cast<std::uintptr_t>(bindings.update),
                         std::memory_order_release);
    g_SpriteIsPlaying.store(reinterpret_cast<std::uintptr_t>(bindings.isPlaying),
                            std::memory_order_release);
    g_SpriteIsFinished.store(reinterpret_cast<std::uintptr_t>(bindings.isFinished),
                             std::memory_order_release);
    g_SpriteRender.store(reinterpret_cast<std::uintptr_t>(bindings.render),
                         std::memory_order_release);
    g_SpriteRenderLayer.store(reinterpret_cast<std::uintptr_t>(bindings.renderLayer),
                              std::memory_order_release);
    g_SpritePlayRandom.store(reinterpret_cast<std::uintptr_t>(bindings.playRandom),
                             std::memory_order_release);
    g_SpriteLoad.store(reinterpret_cast<std::uintptr_t>(bindings.load),
                       std::memory_order_release);
    g_SpriteLoadGraphics.store(reinterpret_cast<std::uintptr_t>(bindings.loadGraphics),
                               std::memory_order_release);
    g_SpriteReplaceSpritesheet.store(reinterpret_cast<std::uintptr_t>(bindings.replaceSpritesheet),
                                     std::memory_order_release);
    g_LibcxxStringAssign.store(reinterpret_cast<std::uintptr_t>(bindings.libcxxStringAssign),
                               std::memory_order_release);
    g_GameOperatorDelete.store(reinterpret_cast<std::uintptr_t>(bindings.gameOperatorDelete),
                               std::memory_order_release);
}

#if defined(__GNUC__) && !defined(__clang__)
#pragma GCC pop_options
#endif

#if !defined(EXL_DIAGNOSTIC_STAGE)
bool IsMusicReadyForDefaultCallback(uintptr_t manager) {
    const uintptr_t method = g_MusicGetCurrentMusicId.load(std::memory_order_acquire);
    uintptr_t music = 0;
    if (!ResolveMusicForManager(manager, method, kMusicGetCurrentMusicIdExpectedBytes.data(),
                                kMusicGetCurrentMusicIdExpectedBytes.size(), &music)) {
        return false;
    }
    using GetCurrentMusicIdFn = int (*)(const void*);
    return reinterpret_cast<GetCurrentMusicIdFn>(method)(reinterpret_cast<const void*>(music)) != 0;
}
#endif

//: 一条回调实参（`mod` 之外的那些）。
//:
//: 为什么做成一张小表、而不是像从前那样一串 `bool` 开关字段：本轮要接的回调形状从 3 种涨到
//: 8 种（`(bool)`、`(int, 玩家, int)`、`(int, 玩家, int, int, int)`、`(int, int, bool, int)`…），
//: 每加一种就加两个字段会很快失控，而且"到底压几个实参"会散落到构造点去。表里只描述数据，
//: 压栈、计数、过滤器三件事各在一处做。
struct CallbackArgument {
    enum class Kind : std::uint8_t {
        None = 0,  //: 哨兵（表尾，不压栈）
        Integer,   //: 整数
        Boolean,   //: 布尔（`lua_pushboolean`，不是整数 0/1）
        Entity,    //: 实体句柄（视图与 `Isaac.GetRoomEntities()` 给的一致）
        Nil,       //: 明确压 `nil`
        Vector,    //: 渲染回调的 `RenderOffset`（`Vector` userdata）
    };
    Kind kind{Kind::None};
    std::int64_t number{0};
    std::uintptr_t entity{0};
    float x{0.0F};
    float y{0.0F};
};

struct CallbackArguments {
    static constexpr std::size_t kMaximum = 6;
    CallbackArgument items[kMaximum]{};
    std::size_t count{0};

    void AddInteger(std::int64_t value) noexcept { Push(CallbackArgument::Kind::Integer, value); }
    void AddBoolean(bool value) noexcept {
        Push(CallbackArgument::Kind::Boolean, value ? 1 : 0);
    }
    void AddNil() noexcept { Push(CallbackArgument::Kind::Nil, 0); }
    void AddEntity(std::uintptr_t value) noexcept {
        if (count >= kMaximum) {
            return;
        }
        items[count].kind = CallbackArgument::Kind::Entity;
        items[count].entity = value;
        ++count;
    }
    void AddVector(float x, float y) noexcept {
        if (count >= kMaximum) {
            return;
        }
        items[count].kind = CallbackArgument::Kind::Vector;
        items[count].x = x;
        items[count].y = y;
        ++count;
    }

private:
    void Push(CallbackArgument::Kind kind, std::int64_t value) noexcept {
        if (count >= kMaximum) {
            // 超容量是**调用点的编程错误**（不是模组能造成的）：`kMaximum` 取 6 是照 PC 回调
            // 实参最多的那条（`MC_PRE_USE_ITEM` 的 6 个）定的。这里静默丢弃而不是截断式压栈：
            // 少压一个实参 ⇒ 模组拿到 `nil`，比"多压一个把后面的挤掉"更容易发现。
            return;
        }
        items[count].kind = kind;
        items[count].number = value;
        ++count;
    }
};

// Invokes one registered callback with the same context the legacy single-slot
// path used: the Mod userdata is the only argument. A Lua error is recorded and
// isolated, but the callback remains registered so one missing API cannot
// disable an entire Mod for the rest of the session.
struct LuaCallbackInvoker final : isaac::runtime::ICallbackInvoker {
    std::uintptr_t manager{0};
    bool hasManager{false};
    bool postUpdate{false};
    // 除 `mod` 之外的实参（见 `CallbackArguments`）。
    CallbackArguments arguments{};

    LuaCallbackInvoker(std::uintptr_t managerValue, bool withManager, bool updatePhase,
                       std::int64_t extra = 0, bool withExtra = false) noexcept
        : manager(managerValue), hasManager(withManager), postUpdate(updatePhase) {
        // 老式构造：`extra/withExtra` 就是"一个整数实参"。保留它是因为调用点遍布三十来处
        // （`DispatchFrameEvents` 那一族的 `LuaCallbackInvoker{0, false, false}` 最典型），
        // 而门禁 `test_embedded_lua_runtime.py` 也钉着那个字面写法。
        if (withExtra) {
            arguments.AddInteger(extra);
        }
    }

    // 带**实体实参**的那种（见 `AddEntity`）。做成工厂函数是为了调用点只写一行，
    // 而"派发点"的写法被门禁 `test_lua_callback_dispatch_sites.py` 盯着，越短越不容易写歪。
    [[nodiscard]] static LuaCallbackInvoker ForEntity(std::uintptr_t entity) noexcept {
        LuaCallbackInvoker invoker{0, false, false};
        invoker.arguments.AddEntity(entity);
        return invoker;
    }

    // 带**实体实参 + 渲染偏移**的那种（`MC_POST_*_RENDER` 这一族）。
    [[nodiscard]] static LuaCallbackInvoker ForEntityWithVector(std::uintptr_t entity, float x,
                                                                float y) noexcept {
        LuaCallbackInvoker invoker = ForEntity(entity);
        invoker.arguments.AddVector(x, y);
        return invoker;
    }

    isaac::runtime::Status Invoke(
        const isaac::runtime::CallbackDescriptor& descriptor) noexcept override {
        return InvokeCore(descriptor, false, nullptr);
    }

    isaac::runtime::Status InvokeCollecting(const isaac::runtime::CallbackDescriptor& descriptor,
                                           isaac::runtime::CallbackReturn* result) noexcept override {
        if (result != nullptr) {
            *result = isaac::runtime::CallbackReturn{};
        }
        return InvokeCore(descriptor, true, result);
    }

private:
    //: `Invoke` 与 `InvokeCollecting` 的唯一实现（"要几个返回值、要不要读栈顶"由
    //: `collecting` 决定，其余一字不差）。分成两个公开入口是因为调用点要能一眼看出
    //: "这一条读了返回值"。
    //:
    //: ⚠️ 本注释里**故意不写那次 Lua 调用的函数名**：`test_manager_render_hook.py` 与
    //: `test_lua_game_ispaused_stage37.py` 都是纯文本门禁，它们按"第一个出现的位置"判断
    //: "回调作用域标记必须在那次调用之前"——注释里出现一次就会把判据指到注释上（本批第一版
    //: 就是这么红的）。与 `test_lua_callback_dispatch_sites.py` 同一条约定。
    isaac::runtime::Status InvokeCore(const isaac::runtime::CallbackDescriptor& descriptor,
                                      bool collecting,
                                      isaac::runtime::CallbackReturn* result) noexcept {
        if (g_LuaState == nullptr) {
            return isaac::runtime::Status{isaac::runtime::StatusCode::InvalidState};
        }
        lua_rawgeti(g_LuaState, LUA_REGISTRYINDEX, descriptor.luaReference);
        lua_rawgeti(g_LuaState, LUA_REGISTRYINDEX, descriptor.modReference);
#if defined(EXL_PERSISTENCE_TRACE) || defined(EXL_PERSISTENCE_EVENT_DIAGNOSTIC)
        if (postUpdate) {
            g_CallbackOperation.store(static_cast<u8>(CallbackOperation::None),
                                      std::memory_order_release);
        }
#endif
        if (hasManager) {
            g_CurrentCallbackManager.store(manager, std::memory_order_release);
        }
        g_InManagedCallbackDispatch.store(true, std::memory_order_release);
        // 批次 090：**第一个托管回调**时清一次采样桶 —— 模组加载阶段的脚本（入口脚本、
        // 各 `require`）会把桶塞满跟"每帧代价"无关的东西（第一次真机就是这么被占满的）。
        // 清一次之后，桶里剩下的才是"进了游戏之后真正在跑的东西"。
        if (!g_ProfileSessionStarted) {
            g_ProfileSessionStarted = true;
            ResetRuntimePerfProfile();
        }
        // 批次 068：把"正在执行哪条回调、属于哪个模组"记下来，供错误记录盖归属。
        // 用普通全局而不是原子：只有游戏线程走派发（与 `g_PostUpdateDispatchCount` 同一约定）。
        const std::uint32_t previousOwner = g_ErrorContextOwner;
        const std::uint32_t previousCallbackId = g_ErrorContextCallbackId;
        // 归属打包成 u32：低 16 位 = `ModHandle::index`、高 16 位 = `generation`
        // （与回调登记表在读数里的 `#N 代M` 同一种解包方式，工具照同一套打印）。
        g_ErrorContextOwner = static_cast<std::uint32_t>(descriptor.owner.index) |
                              (static_cast<std::uint32_t>(descriptor.owner.generation) << 16);
        g_ErrorContextCallbackId = descriptor.id;
        // 实参按编组表顺序压栈（`mod` 已经在栈上，是第 1 个）。
        for (std::size_t index = 0; index < arguments.count; ++index) {
            const CallbackArgument& argument = arguments.items[index];
            switch (argument.kind) {
                case CallbackArgument::Kind::Integer:
                    lua_pushinteger(g_LuaState, static_cast<lua_Integer>(argument.number));
                    break;
                case CallbackArgument::Kind::Boolean:
                    lua_pushboolean(g_LuaState, argument.number != 0 ? 1 : 0);
                    break;
                case CallbackArgument::Kind::Nil:
                    lua_pushnil(g_LuaState);
                    break;
                case CallbackArgument::Kind::Entity:
                    // 视图与 `Isaac.GetRoomEntities()` 给出的一致（玩家给 `EntityPlayer`），
                    // 否则模组在回调里对参数调 `player:HasCollectible()` 会失败。
                    isaac::runtime::PushEntityCallbackArgument(g_LuaState, argument.entity);
                    break;
                case CallbackArgument::Kind::Vector:
                    // 渲染偏移（`Vector` userdata，与 `Room:GetRenderScrollOffset()` 给出的是同一种值类型）。
                    isaac::runtime::PushLuaVector(g_LuaState, argument.x, argument.y);
                    break;
                case CallbackArgument::Kind::None:
                    break;
            }
        }
        // 批次 084：同 TU 的 file-local 计数（不碰数据 GOT），只读一次 `cntpct_el0`
        // （**物理**计数器；`cntvct_el0` 在 EL0 会被禁止读，批次 085 的真机崩溃就是它）。
        const std::uint64_t perfStart = isaac::runtime::RuntimePerfTick();
        // 实参个数 = 1（`mod`）+ 编组表的条数；返回值个数 = 要不要读（`collecting`）。
        // 写成这个表达式而不是 `1 + arguments.count` 直接内联，是为了让"实参个数由编组表决定"
        // 这条不变量在源码里是一个可被门禁钉住的字面量（`test_embedded_lua_runtime.py`）。
        const int argumentCount = 1 + static_cast<int>(arguments.count);
        const int callbackStatus = lua_pcallk(g_LuaState, argumentCount, collecting ? 1 : 0, 0, 0,
                                             nullptr);
        {
            const std::uint64_t perfEnd = isaac::runtime::RuntimePerfTick();
            g_RuntimePerfCallbackCalls.fetch_add(1, std::memory_order_relaxed);
            if (perfEnd > perfStart) {
                const std::uint64_t spent = perfEnd - perfStart;
                g_RuntimePerfCallbackTicks.fetch_add(spent, std::memory_order_relaxed);
                if (spent > g_RuntimePerfCallbackMaxTicks.load(std::memory_order_relaxed)) {
                    g_RuntimePerfCallbackMaxTicks.store(spent, std::memory_order_relaxed);
                }
                // 批次 092：每隔 256 次回调做一次**量具自校准**（读一次 tick 要多少 tick）。
                // 直方图在 `RecordRuntimePerfCallbackSample` 里随桶一起记。
                if ((g_RuntimePerfCallbackCalls.load(std::memory_order_relaxed) & 0xFFU) == 0U) {
                    const std::uint64_t calibration0 = isaac::runtime::RuntimePerfTick();
                    static_cast<void>(isaac::runtime::RuntimePerfTick());  // 中间那次只为把流水线拉开
                    const std::uint64_t calibration2 = isaac::runtime::RuntimePerfTick();
                    if (calibration2 > calibration0) {
                        g_RuntimePerfTickCostTicks = (calibration2 - calibration0) / 2U;
                    }
                }
                // 批次 086：再按 (事件 id, 属主模组) 分一次 —— 回答"贵的是哪一个回调"。
                // 传的是本 TU 自己的数组（直接寻址、不碰数据 GOT）；记账逻辑在头文件里，宿主有测试。
                // 返回值在这里**故意不用**（表满时由 `g_RuntimePerfBucketOverflow` 记账、读数里会报），
                // 显式丢弃是为了过 `-Werror=unused-result`（`nodiscard` 是给宿主门禁看的）。
                static_cast<void>(isaac::runtime::RecordRuntimePerfCallbackSample(
                    g_RuntimePerfCallbackBuckets, isaac::runtime::kRuntimePerfBucketCount,
                    isaac::runtime::RuntimePerfCallbackKey(
                        descriptor.id, descriptor.owner.index, descriptor.owner.generation),
                    spent, &g_RuntimePerfBucketOverflow));
            }
        }
        // ★ 复原必须放在**错误捕获之后**：`CaptureLuaErrorTop` 要读这两个值来盖归属，
        // 放在 pcall 之后立刻复原的话，记录到的永远是默认值（宿主测试第一次就是这么红的）。
        g_InManagedCallbackDispatch.store(false, std::memory_order_release);
        if (hasManager) {
            g_CurrentCallbackManager.store(0, std::memory_order_release);
        }
        if (callbackStatus != LUA_OK) {
#if defined(EXL_PERSISTENCE_TRACE) || defined(EXL_PERSISTENCE_EVENT_DIAGNOSTIC)
            const u64 detail =
                (CallbackErrorTail(g_LuaState) << 16) |
                (static_cast<u64>(g_CallbackOperation.load(std::memory_order_acquire)) << 8) |
                static_cast<u8>(callbackStatus);
            g_CallbackFailureDetail.store(detail, std::memory_order_release);
#endif
            CaptureLuaErrorTop(g_LuaState);
            lua_pop(g_LuaState, 1);
            g_ErrorContextOwner = previousOwner;
            g_ErrorContextCallbackId = previousCallbackId;
            g_CallbackError.store(true, std::memory_order_release);
            return isaac::runtime::Status{isaac::runtime::StatusCode::Rejected};
        }
        // 读回返回值。受保护调用在 `collecting` 时**保证**栈上恰好有 1 个结果
        // （函数没 `return` 时 Lua 补 `nil`），所以这里不需要"检查栈高"。
        // ⚠️ 这里同样**不写那次调用的函数名**（理由见 `InvokeCore` 上方的注释）。
        if (result != nullptr) {
            result->called = true;
            if (lua_isnil(g_LuaState, -1) == 0) {
                result->nonNil = true;
                // "真值"用 `lua_toboolean`（Lua 的真值语义：`1`、字符串等非假值都算）。
                // 依据是 PC 文档对 `MC_PRE_USE_ITEM` 的那句 ——"返回除 nil 以外的任何值都会阻止
                // 后续回调"—— 说明引擎读的不是"严格等于 boolean true"。
                result->truthy = lua_toboolean(g_LuaState, -1) != 0;
                if (lua_isinteger(g_LuaState, -1) != 0) {
                    result->hasInteger = true;
                    result->integer =
                        static_cast<std::int64_t>(lua_tointegerx(g_LuaState, -1, nullptr));
                }
            }
            lua_pop(g_LuaState, 1);
        }
        return isaac::runtime::Status::Ok();
    }
};

namespace {
// 引擎侧的开局中继记下的"刚开了一局"。用原子变量跨线程/跨帧传递，见 `NoteGameStarted`。
// 取值：0 = 没有待派发的开局事件；1 = 待派发，且是**读档**进游戏；2 = 待派发，且是**新开一局**。
// 刻意用整型而不是 bool 类型的原子变量：本项目有一条门禁，运行时代码里不允许出现 bool 原子
// （`runtime/tests/test_manager_update_hook_audit.py::test_runtime_source_contains_no_bool_atomics`
// 做的是纯字符串匹配，所以这里连写法都不能照抄）。
std::atomic<std::uint32_t> g_PendingGameStarted{0};
constexpr std::uint32_t kGameStartedFromSave = 1;
constexpr std::uint32_t kGameStartedFresh = 2;
}  // namespace

void NoteGameStarted(bool isSave) noexcept {
    g_PendingGameStarted.store(isSave ? kGameStartedFromSave : kGameStartedFresh,
                               std::memory_order_release);
}

// 返回"是否真的派发出去了"。**调用方必须据此决定能否清掉待派发标志** ——
// 早先的写法无条件清标志，于是在"当前不允许派发"（例如刚开局那几帧）时把开局事件永久吞掉：
// 真机症状就是套装计数一直 (0/3)。这是 2026-09-14 定位到的真 bug。
bool DispatchPostGameStarted(bool isSave) {
    if (!IsReady() || g_LuaState == nullptr ||
        !isaac::runtime::ShouldDispatchManagedCallbacks()) {
        return false;
    }
    isaac::runtime::EngineGuardEnterDispatch();
    LuaCallbackInvoker invoker{0, false, false, isSave ? 1 : 0, true};
    isaac::runtime::CallbackDispatcher dispatcher{g_CallbackRegistry, invoker};
    static_cast<void>(dispatcher.Dispatch(isaac::runtime::kCallbackPostGameStarted,
                                          isaac::runtime::ThreadAffinity::Any));
    isaac::runtime::EngineGuardLeaveDispatch();
    return true;
}

// --- 每帧事件与实体族回调（回调面地基，2026-09-18）-------------------------------
//
// 这些回调在 PC 上由引擎在事件发生**的那一刻**触发，而我们没有对应挂点（挂点要逐条逆向定位，
// 属于 `tools/callback_surface.json` 里的 `needs_hook`）。所以用"每帧时机 + 状态差分/类型分派"
// 实现：Manager 每帧的那次 update 派发里读一次"在哪个房间、哪一层、房间里有谁"（换房/换层），
// 以及"房间里每个实体是什么类"（实体族：更新/渲染/刚出现三种时机）。
//
// **代价与已知差异**（写在这里，免得以后把它们当成 bug 查）：
//   * 时机被推迟到本帧的派发点，最多比 PC 晚一帧；
//   * `MC_*_INIT`（含 `MC_POST_PICKUP_INIT`）的判据是"这一帧没见过这个指针 ⇒ 算新出现"。
//     因此**每次进新房间**，房间里原本就摆着的实体（掉落物、跟班、敌人…）会各收到一次 INIT。
//     PC 上它们在房间生成时就被初始化，而模组此时通常已经加载完毕 ⇒"补发"比"漏发"更接近
//     PC 的观感；
//   * "见过"的表以**房间**为生命周期（换房清空；玩家那张例外，玩家跨房间存活）。
//     房间内被拿走、又在同一房间重新生成的同一个指针不会被重复触发（指针复用）；
//     这是拿"能立刻做出来"换来的已知缺口；
//   * 实体族按 `EntityType` 分派，判据见 `ClassifyCallbackEntity`；**没有各自 vtable 常量**的
//     那几类（眼泪/弹射物/激光/刀/炸弹/效果）只比 `Type`；
//   * 渲染族的第二个实参（`RenderOffset`）是"房间滚动偏移 + 游戏屏幕调整量"两项之和，
//     **尚未逐字核对** PC 是否就是这么算的（见 `game_observer.hpp` 的 `GameRenderOffset`）；
//   * 这一族**只在有人登记时才派发** ⇒ 设备读数里它们的计数代表"有人听的时候"（换房/换层
//     那两条是例外，它们不受登记影响）。
//
// 为什么状态是普通全局而不是原子/`thread_local`：与 `g_PendingGameStarted` 同一条约定 ——
// 读写只发生在游戏线程的这条派发路径上；而本项目在真机上被 `thread_local` 坑过（见本文件
// 上面的注释），所以一律不用。

namespace {

//: "见过"的实体指针表容量，按类各一张。容量照"一个房间里可能同时存在多少"给：眼泪与效果
//: 最多（弹幕与爆炸可以上百），跟班/刀/炸弹少。**满了就不再记录、也不再报"新"**（见
//: `NoteNewEntity` 的注释）。
constexpr std::uint32_t kSeenPickupCapacity = 256;
constexpr std::uint32_t kSeenPlayerCapacity = 8;
constexpr std::uint32_t kSeenNpcCapacity = 256;
constexpr std::uint32_t kSeenFamiliarCapacity = 64;
constexpr std::uint32_t kSeenTearCapacity = 512;
constexpr std::uint32_t kSeenProjectileCapacity = 256;
constexpr std::uint32_t kSeenLaserCapacity = 128;
constexpr std::uint32_t kSeenKnifeCapacity = 32;
constexpr std::uint32_t kSeenEffectCapacity = 512;
constexpr std::uint32_t kSeenBombCapacity = 64;

struct FrameEventState {
    // 上一次看到的房间/层身份。`known == 0` 表示"暂时还不知道"（读数失败过、或还没进局）。
    // 不知道时**不判变化** —— 拿读数失败留下的残值当身份，会把回调派发成"每帧一次"。
    std::uint32_t roomKnown{0};
    std::uint32_t levelKnown{0};
    //: 2026-09-22：本局"开局那间房"还没补派过 `NEW_LEVEL`/`NEW_ROOM`。
    //: 为什么需要它：旧代码"第一次读到身份时不判变化"，于是开局房间**永远**收不到这两条事件
    //: （真机读数：开局那一局 `19 MC_POST_NEW_ROOM = 0`），而 PC 是照发的 ——
    //: EID 的房间信息恰好就在 `NEW_ROOM` 里算，所以"重启后第一次进局正好在献祭房 ⇒ 不显示"。
    //: 由开局派发成功那一刻置 1，由 `DispatchFrameEvents()` 在补派成功后清 0。
    std::uint32_t initialRoomPending{0};
    GameLocationKey location{};
    // 下面这些表**只用来比较、绝不解引用**：里面的地址可能已经被释放，但比较两个整数
    // 地址不碰内存。（本项目的纪律是"过期的原生指针不许解引用"，这里遵守。）
    //
    // 为什么按类各一张而不是共用一张：共用的那张会被**数量最多的那一类**（效果/眼泪）填满，
    // 于是同一房间里后来出现的敌人、掉落物再也收不到 INIT —— 一类把另一类饿死。
    std::uintptr_t seenPickups[kSeenPickupCapacity]{};
    std::uint32_t seenPickupCount{0};
    std::uintptr_t seenPlayers[kSeenPlayerCapacity]{};
    std::uint32_t seenPlayerCount{0};
    std::uintptr_t seenNpcs[kSeenNpcCapacity]{};
    std::uint32_t seenNpcCount{0};
    std::uintptr_t seenFamiliars[kSeenFamiliarCapacity]{};
    std::uint32_t seenFamiliarCount{0};
    std::uintptr_t seenTears[kSeenTearCapacity]{};
    std::uint32_t seenTearCount{0};
    std::uintptr_t seenProjectiles[kSeenProjectileCapacity]{};
    std::uint32_t seenProjectileCount{0};
    std::uintptr_t seenLasers[kSeenLaserCapacity]{};
    std::uint32_t seenLaserCount{0};
    std::uintptr_t seenKnives[kSeenKnifeCapacity]{};
    std::uint32_t seenKnifeCount{0};
    std::uintptr_t seenEffects[kSeenEffectCapacity]{};
    std::uint32_t seenEffectCount{0};
    std::uintptr_t seenBombs[kSeenBombCapacity]{};
    std::uint32_t seenBombCount{0};
};

FrameEventState g_FrameEventState{};

//: 本层"起始房间"的记账（批次 106）。与 `g_FrameEventState` 同一条约定：只有游戏线程的派发路径
//: 读写它，所以是普通全局、不是原子。读数工具不读它（它只有 API 层按需取值）。
LuaRuntime::LevelStartRoomTracker g_LevelStartRoom{};

// 新建 Lua 会话时清空（只在本 TU 调用：会话重置那一处）⇒ 定义在调用点之前即可。
void ResetLevelStartRoomTracker() noexcept {
    g_LevelStartRoom.Reset();
}



//: 记一个"这次见过的"实体；返回 true 表示它是**新出现的**（调用方据此派发 INIT）。
//:
//: ★ 表满时返回 false：既不记录、也不说"新"。早先的实现在表满时仍然返回 true 且不记录，
//: 于是**每一个没被记下的实体会每帧收到一次 INIT**（满房间的掉落物就会这样）。
//: 宁可漏发一次，也不重复发 —— 重复发的事件会让模组每秒做 60 次同样的注册。
bool NoteNewEntity(std::uintptr_t* entries, std::uint32_t capacity, std::uint32_t* count,
                   std::uintptr_t entity) noexcept {
    if (entries == nullptr || count == nullptr || capacity == 0 || entity == 0) {
        return false;
    }
    for (std::uint32_t index = 0; index < *count; ++index) {
        if (entries[index] == entity) {
            return false;
        }
    }
    if (*count >= capacity) {
        return false;
    }
    entries[(*count)++] = entity;
    return true;
}

void ClearSeenEntities(std::uint32_t* count) noexcept {
    if (count != nullptr) {
        *count = 0;
    }
}

// 这一帧"哪些回调有人登记"的位图（下标 = 回调 id，0..127）。
//
// 为什么要有它：实体族的派发点有三十来处，每处都问一次 `CountOf` 就是每帧把登记表线性扫
// 三十来遍（登记表四十多项）。这里扫**一遍**拿到全部答案。（`CountOf` 的线性扫描在
// 项目里是有先例的写法，只是不适合"每帧 × 三十种"这个量级。）
struct RegisteredCallbackMask {
    std::uint64_t low{0};   // id 0..63
    std::uint64_t high{0};  // id 64..127

    [[nodiscard]] bool Has(isaac::runtime::CallbackId id) const noexcept {
        if (id < 64) {
            return (low & (1ULL << id)) != 0;
        }
        if (id < 128) {
            return (high & (1ULL << (id - 64))) != 0;
        }
        return false;
    }
};

RegisteredCallbackMask BuildRegisteredCallbackMask() noexcept {
    RegisteredCallbackMask mask{};
    const std::size_t total = g_CallbackRegistry.Count();
    for (std::size_t index = 0; index < total; ++index) {
        const isaac::runtime::CallbackDescriptor* descriptor = g_CallbackRegistry.AtIndex(index);
        if (descriptor == nullptr) {
            continue;
        }
        const isaac::runtime::CallbackId id = descriptor->id;
        if (id < 64) {
            mask.low |= 1ULL << id;
        } else if (id < 128) {
            mask.high |= 1ULL << (id - 64);
        }
    }
    return mask;
}

//: 这一帧要不要遍历实体表/玩家向量。写成一条条 `||` 而不是 id 表循环，理由与派发点相同：
//: id 表这种写法离"表驱动派发"只有一步，而派发点必须逐个显式写（门禁靠它把设备侧报出来的
//: 名单与代码里的真实派发对上）。
[[nodiscard]] bool AnyEntityFamilyRegistered(const RegisteredCallbackMask& mask) noexcept {
    return mask.Has(isaac::runtime::kCallbackNpcUpdate) || mask.Has(isaac::runtime::kCallbackPostPeffectUpdate) ||
           mask.Has(isaac::runtime::kCallbackFamiliarUpdate) || mask.Has(isaac::runtime::kCallbackFamiliarInit) ||
           mask.Has(isaac::runtime::kCallbackPostFamiliarRender) || mask.Has(isaac::runtime::kCallbackPostNpcInit) ||
           mask.Has(isaac::runtime::kCallbackPostPlayerUpdate) || mask.Has(isaac::runtime::kCallbackPostPlayerRender) ||
           mask.Has(isaac::runtime::kCallbackPostPickupRender) || mask.Has(isaac::runtime::kCallbackPostTearInit) ||
           mask.Has(isaac::runtime::kCallbackPostTearUpdate) || mask.Has(isaac::runtime::kCallbackPostTearRender) ||
           mask.Has(isaac::runtime::kCallbackPostProjectileInit) || mask.Has(isaac::runtime::kCallbackPostProjectileUpdate) ||
           mask.Has(isaac::runtime::kCallbackPostProjectileRender) || mask.Has(isaac::runtime::kCallbackPostLaserInit) ||
           mask.Has(isaac::runtime::kCallbackPostLaserUpdate) || mask.Has(isaac::runtime::kCallbackPostLaserRender) ||
           mask.Has(isaac::runtime::kCallbackPostKnifeInit) || mask.Has(isaac::runtime::kCallbackPostKnifeUpdate) ||
           mask.Has(isaac::runtime::kCallbackPostKnifeRender) || mask.Has(isaac::runtime::kCallbackPostEffectInit) ||
           mask.Has(isaac::runtime::kCallbackPostEffectUpdate) || mask.Has(isaac::runtime::kCallbackPostEffectRender) ||
           mask.Has(isaac::runtime::kCallbackPostBombInit) || mask.Has(isaac::runtime::kCallbackPostBombUpdate) ||
           mask.Has(isaac::runtime::kCallbackPostBombRender) || mask.Has(isaac::runtime::kCallbackPostPickupInit) ||
           mask.Has(isaac::runtime::kCallbackPostPickupUpdate) || mask.Has(isaac::runtime::kCallbackPostPlayerInit);
}

//: 渲染族里有没有人登记（没有就不必花一次渲染偏移读数 + 一趟实体表遍历）。
[[nodiscard]] bool AnyEntityRenderFamilyRegistered(const RegisteredCallbackMask& mask) noexcept {
    return mask.Has(isaac::runtime::kCallbackPostFamiliarRender) || mask.Has(isaac::runtime::kCallbackPostPlayerRender) ||
           mask.Has(isaac::runtime::kCallbackPostPickupRender) || mask.Has(isaac::runtime::kCallbackPostTearRender) ||
           mask.Has(isaac::runtime::kCallbackPostProjectileRender) || mask.Has(isaac::runtime::kCallbackPostLaserRender) ||
           mask.Has(isaac::runtime::kCallbackPostKnifeRender) || mask.Has(isaac::runtime::kCallbackPostEffectRender) ||
           mask.Has(isaac::runtime::kCallbackPostBombRender);
}

// 一次实体族派发需要的上下文：谁在听、现在是哪个时机、渲染偏移是多少。
struct EntityEventScan {
    RegisteredCallbackMask registered{};
    // false = 更新时机（Manager::Update 那条每帧派发里），true = 渲染时机。
    bool renderPhase{false};
    float renderOffsetX{0.0F};
    float renderOffsetY{0.0F};
};

// 下面这一族小函数是"按实体类派发"的实现主体：**每个函数里都把回调常量直接写进派发调用**
// （不许表驱动 —— 见 `runtime/tests/test_lua_callback_dispatch_sites.py`，也见上面
// `AnyEntityFamilyRegistered` 的注释）。注释里同样不许出现那种调用的字面写法：那条门禁是
// 纯文本匹配、连注释一起扫（2026-09-18 被它抓过一次）。
void DispatchNpcEntityEvents(EntityEventScan* scan, std::uintptr_t entity) noexcept {
    if (scan->renderPhase) {
        return;  // `MC_POST_NPC_RENDER` 不在本批（台账里是 needs_hook），见批次 010 的记录。
    }
    if (scan->registered.Has(isaac::runtime::kCallbackNpcUpdate)) {
        LuaCallbackInvoker invoker = LuaCallbackInvoker::ForEntity(entity);
        isaac::runtime::CallbackDispatcher dispatcher{g_CallbackRegistry, invoker};
        static_cast<void>(dispatcher.Dispatch(isaac::runtime::kCallbackNpcUpdate,
                                              isaac::runtime::ThreadAffinity::Any));
    }
    if (scan->registered.Has(isaac::runtime::kCallbackPostNpcInit) &&
        NoteNewEntity(g_FrameEventState.seenNpcs, kSeenNpcCapacity, &g_FrameEventState.seenNpcCount,
                      entity)) {
        LuaCallbackInvoker invoker = LuaCallbackInvoker::ForEntity(entity);
        isaac::runtime::CallbackDispatcher dispatcher{g_CallbackRegistry, invoker};
        static_cast<void>(dispatcher.Dispatch(isaac::runtime::kCallbackPostNpcInit,
                                              isaac::runtime::ThreadAffinity::Any));
    }
}

void DispatchFamiliarEntityEvents(EntityEventScan* scan, std::uintptr_t entity) noexcept {
    if (!scan->renderPhase && scan->registered.Has(isaac::runtime::kCallbackFamiliarUpdate)) {
        LuaCallbackInvoker invoker = LuaCallbackInvoker::ForEntity(entity);
        isaac::runtime::CallbackDispatcher dispatcher{g_CallbackRegistry, invoker};
        static_cast<void>(dispatcher.Dispatch(isaac::runtime::kCallbackFamiliarUpdate,
                                              isaac::runtime::ThreadAffinity::Any));
    }
    if (!scan->renderPhase && scan->registered.Has(isaac::runtime::kCallbackFamiliarInit) &&
        NoteNewEntity(g_FrameEventState.seenFamiliars, kSeenFamiliarCapacity,
                      &g_FrameEventState.seenFamiliarCount, entity)) {
        LuaCallbackInvoker invoker = LuaCallbackInvoker::ForEntity(entity);
        isaac::runtime::CallbackDispatcher dispatcher{g_CallbackRegistry, invoker};
        static_cast<void>(dispatcher.Dispatch(isaac::runtime::kCallbackFamiliarInit,
                                              isaac::runtime::ThreadAffinity::Any));
    }
    if (scan->renderPhase && scan->registered.Has(isaac::runtime::kCallbackPostFamiliarRender)) {
        LuaCallbackInvoker invoker = LuaCallbackInvoker::ForEntityWithVector(
            entity, scan->renderOffsetX, scan->renderOffsetY);
        isaac::runtime::CallbackDispatcher dispatcher{g_CallbackRegistry, invoker};
        static_cast<void>(dispatcher.Dispatch(isaac::runtime::kCallbackPostFamiliarRender,
                                              isaac::runtime::ThreadAffinity::Any));
    }
}

void DispatchTearEntityEvents(EntityEventScan* scan, std::uintptr_t entity) noexcept {
    if (!scan->renderPhase && scan->registered.Has(isaac::runtime::kCallbackPostTearUpdate)) {
        LuaCallbackInvoker invoker = LuaCallbackInvoker::ForEntity(entity);
        isaac::runtime::CallbackDispatcher dispatcher{g_CallbackRegistry, invoker};
        static_cast<void>(dispatcher.Dispatch(isaac::runtime::kCallbackPostTearUpdate,
                                              isaac::runtime::ThreadAffinity::Any));
    }
    if (!scan->renderPhase && scan->registered.Has(isaac::runtime::kCallbackPostTearInit) &&
        NoteNewEntity(g_FrameEventState.seenTears, kSeenTearCapacity, &g_FrameEventState.seenTearCount,
                      entity)) {
        LuaCallbackInvoker invoker = LuaCallbackInvoker::ForEntity(entity);
        isaac::runtime::CallbackDispatcher dispatcher{g_CallbackRegistry, invoker};
        static_cast<void>(dispatcher.Dispatch(isaac::runtime::kCallbackPostTearInit,
                                              isaac::runtime::ThreadAffinity::Any));
    }
    if (scan->renderPhase && scan->registered.Has(isaac::runtime::kCallbackPostTearRender)) {
        LuaCallbackInvoker invoker = LuaCallbackInvoker::ForEntityWithVector(
            entity, scan->renderOffsetX, scan->renderOffsetY);
        isaac::runtime::CallbackDispatcher dispatcher{g_CallbackRegistry, invoker};
        static_cast<void>(dispatcher.Dispatch(isaac::runtime::kCallbackPostTearRender,
                                              isaac::runtime::ThreadAffinity::Any));
    }
}

void DispatchProjectileEntityEvents(EntityEventScan* scan, std::uintptr_t entity) noexcept {
    if (!scan->renderPhase && scan->registered.Has(isaac::runtime::kCallbackPostProjectileUpdate)) {
        LuaCallbackInvoker invoker = LuaCallbackInvoker::ForEntity(entity);
        isaac::runtime::CallbackDispatcher dispatcher{g_CallbackRegistry, invoker};
        static_cast<void>(dispatcher.Dispatch(isaac::runtime::kCallbackPostProjectileUpdate,
                                              isaac::runtime::ThreadAffinity::Any));
    }
    if (!scan->renderPhase && scan->registered.Has(isaac::runtime::kCallbackPostProjectileInit) &&
        NoteNewEntity(g_FrameEventState.seenProjectiles, kSeenProjectileCapacity,
                      &g_FrameEventState.seenProjectileCount, entity)) {
        LuaCallbackInvoker invoker = LuaCallbackInvoker::ForEntity(entity);
        isaac::runtime::CallbackDispatcher dispatcher{g_CallbackRegistry, invoker};
        static_cast<void>(dispatcher.Dispatch(isaac::runtime::kCallbackPostProjectileInit,
                                              isaac::runtime::ThreadAffinity::Any));
    }
    if (scan->renderPhase && scan->registered.Has(isaac::runtime::kCallbackPostProjectileRender)) {
        LuaCallbackInvoker invoker = LuaCallbackInvoker::ForEntityWithVector(
            entity, scan->renderOffsetX, scan->renderOffsetY);
        isaac::runtime::CallbackDispatcher dispatcher{g_CallbackRegistry, invoker};
        static_cast<void>(dispatcher.Dispatch(isaac::runtime::kCallbackPostProjectileRender,
                                              isaac::runtime::ThreadAffinity::Any));
    }
}

void DispatchLaserEntityEvents(EntityEventScan* scan, std::uintptr_t entity) noexcept {
    if (!scan->renderPhase && scan->registered.Has(isaac::runtime::kCallbackPostLaserUpdate)) {
        LuaCallbackInvoker invoker = LuaCallbackInvoker::ForEntity(entity);
        isaac::runtime::CallbackDispatcher dispatcher{g_CallbackRegistry, invoker};
        static_cast<void>(dispatcher.Dispatch(isaac::runtime::kCallbackPostLaserUpdate,
                                              isaac::runtime::ThreadAffinity::Any));
    }
    if (!scan->renderPhase && scan->registered.Has(isaac::runtime::kCallbackPostLaserInit) &&
        NoteNewEntity(g_FrameEventState.seenLasers, kSeenLaserCapacity,
                      &g_FrameEventState.seenLaserCount, entity)) {
        LuaCallbackInvoker invoker = LuaCallbackInvoker::ForEntity(entity);
        isaac::runtime::CallbackDispatcher dispatcher{g_CallbackRegistry, invoker};
        static_cast<void>(dispatcher.Dispatch(isaac::runtime::kCallbackPostLaserInit,
                                              isaac::runtime::ThreadAffinity::Any));
    }
    if (scan->renderPhase && scan->registered.Has(isaac::runtime::kCallbackPostLaserRender)) {
        LuaCallbackInvoker invoker = LuaCallbackInvoker::ForEntityWithVector(
            entity, scan->renderOffsetX, scan->renderOffsetY);
        isaac::runtime::CallbackDispatcher dispatcher{g_CallbackRegistry, invoker};
        static_cast<void>(dispatcher.Dispatch(isaac::runtime::kCallbackPostLaserRender,
                                              isaac::runtime::ThreadAffinity::Any));
    }
}

void DispatchKnifeEntityEvents(EntityEventScan* scan, std::uintptr_t entity) noexcept {
    if (!scan->renderPhase && scan->registered.Has(isaac::runtime::kCallbackPostKnifeUpdate)) {
        LuaCallbackInvoker invoker = LuaCallbackInvoker::ForEntity(entity);
        isaac::runtime::CallbackDispatcher dispatcher{g_CallbackRegistry, invoker};
        static_cast<void>(dispatcher.Dispatch(isaac::runtime::kCallbackPostKnifeUpdate,
                                              isaac::runtime::ThreadAffinity::Any));
    }
    if (!scan->renderPhase && scan->registered.Has(isaac::runtime::kCallbackPostKnifeInit) &&
        NoteNewEntity(g_FrameEventState.seenKnives, kSeenKnifeCapacity,
                      &g_FrameEventState.seenKnifeCount, entity)) {
        LuaCallbackInvoker invoker = LuaCallbackInvoker::ForEntity(entity);
        isaac::runtime::CallbackDispatcher dispatcher{g_CallbackRegistry, invoker};
        static_cast<void>(dispatcher.Dispatch(isaac::runtime::kCallbackPostKnifeInit,
                                              isaac::runtime::ThreadAffinity::Any));
    }
    if (scan->renderPhase && scan->registered.Has(isaac::runtime::kCallbackPostKnifeRender)) {
        LuaCallbackInvoker invoker = LuaCallbackInvoker::ForEntityWithVector(
            entity, scan->renderOffsetX, scan->renderOffsetY);
        isaac::runtime::CallbackDispatcher dispatcher{g_CallbackRegistry, invoker};
        static_cast<void>(dispatcher.Dispatch(isaac::runtime::kCallbackPostKnifeRender,
                                              isaac::runtime::ThreadAffinity::Any));
    }
}

void DispatchEffectEntityEvents(EntityEventScan* scan, std::uintptr_t entity) noexcept {
    if (!scan->renderPhase && scan->registered.Has(isaac::runtime::kCallbackPostEffectUpdate)) {
        LuaCallbackInvoker invoker = LuaCallbackInvoker::ForEntity(entity);
        isaac::runtime::CallbackDispatcher dispatcher{g_CallbackRegistry, invoker};
        static_cast<void>(dispatcher.Dispatch(isaac::runtime::kCallbackPostEffectUpdate,
                                              isaac::runtime::ThreadAffinity::Any));
    }
    if (!scan->renderPhase && scan->registered.Has(isaac::runtime::kCallbackPostEffectInit) &&
        NoteNewEntity(g_FrameEventState.seenEffects, kSeenEffectCapacity,
                      &g_FrameEventState.seenEffectCount, entity)) {
        LuaCallbackInvoker invoker = LuaCallbackInvoker::ForEntity(entity);
        isaac::runtime::CallbackDispatcher dispatcher{g_CallbackRegistry, invoker};
        static_cast<void>(dispatcher.Dispatch(isaac::runtime::kCallbackPostEffectInit,
                                              isaac::runtime::ThreadAffinity::Any));
    }
    if (scan->renderPhase && scan->registered.Has(isaac::runtime::kCallbackPostEffectRender)) {
        LuaCallbackInvoker invoker = LuaCallbackInvoker::ForEntityWithVector(
            entity, scan->renderOffsetX, scan->renderOffsetY);
        isaac::runtime::CallbackDispatcher dispatcher{g_CallbackRegistry, invoker};
        static_cast<void>(dispatcher.Dispatch(isaac::runtime::kCallbackPostEffectRender,
                                              isaac::runtime::ThreadAffinity::Any));
    }
}

void DispatchBombEntityEvents(EntityEventScan* scan, std::uintptr_t entity) noexcept {
    if (!scan->renderPhase && scan->registered.Has(isaac::runtime::kCallbackPostBombUpdate)) {
        LuaCallbackInvoker invoker = LuaCallbackInvoker::ForEntity(entity);
        isaac::runtime::CallbackDispatcher dispatcher{g_CallbackRegistry, invoker};
        static_cast<void>(dispatcher.Dispatch(isaac::runtime::kCallbackPostBombUpdate,
                                              isaac::runtime::ThreadAffinity::Any));
    }
    if (!scan->renderPhase && scan->registered.Has(isaac::runtime::kCallbackPostBombInit) &&
        NoteNewEntity(g_FrameEventState.seenBombs, kSeenBombCapacity, &g_FrameEventState.seenBombCount,
                      entity)) {
        LuaCallbackInvoker invoker = LuaCallbackInvoker::ForEntity(entity);
        isaac::runtime::CallbackDispatcher dispatcher{g_CallbackRegistry, invoker};
        static_cast<void>(dispatcher.Dispatch(isaac::runtime::kCallbackPostBombInit,
                                              isaac::runtime::ThreadAffinity::Any));
    }
    if (scan->renderPhase && scan->registered.Has(isaac::runtime::kCallbackPostBombRender)) {
        LuaCallbackInvoker invoker = LuaCallbackInvoker::ForEntityWithVector(
            entity, scan->renderOffsetX, scan->renderOffsetY);
        isaac::runtime::CallbackDispatcher dispatcher{g_CallbackRegistry, invoker};
        static_cast<void>(dispatcher.Dispatch(isaac::runtime::kCallbackPostBombRender,
                                              isaac::runtime::ThreadAffinity::Any));
    }
}

void DispatchPickupEntityEvents(EntityEventScan* scan, std::uintptr_t entity) noexcept {
    if (!scan->renderPhase && scan->registered.Has(isaac::runtime::kCallbackPostPickupUpdate)) {
        LuaCallbackInvoker invoker = LuaCallbackInvoker::ForEntity(entity);
        isaac::runtime::CallbackDispatcher dispatcher{g_CallbackRegistry, invoker};
        static_cast<void>(dispatcher.Dispatch(isaac::runtime::kCallbackPostPickupUpdate,
                                              isaac::runtime::ThreadAffinity::Any));
    }
    if (!scan->renderPhase && scan->registered.Has(isaac::runtime::kCallbackPostPickupInit) &&
        NoteNewEntity(g_FrameEventState.seenPickups, kSeenPickupCapacity,
                      &g_FrameEventState.seenPickupCount, entity)) {
        LuaCallbackInvoker invoker = LuaCallbackInvoker::ForEntity(entity);
        isaac::runtime::CallbackDispatcher dispatcher{g_CallbackRegistry, invoker};
        static_cast<void>(dispatcher.Dispatch(isaac::runtime::kCallbackPostPickupInit,
                                              isaac::runtime::ThreadAffinity::Any));
    }
    if (scan->renderPhase && scan->registered.Has(isaac::runtime::kCallbackPostPickupRender)) {
        LuaCallbackInvoker invoker = LuaCallbackInvoker::ForEntityWithVector(
            entity, scan->renderOffsetX, scan->renderOffsetY);
        isaac::runtime::CallbackDispatcher dispatcher{g_CallbackRegistry, invoker};
        static_cast<void>(dispatcher.Dispatch(isaac::runtime::kCallbackPostPickupRender,
                                              isaac::runtime::ThreadAffinity::Any));
    }
}

void DispatchPlayerEntityEvents(EntityEventScan* scan, std::uintptr_t entity) noexcept {
    // `MC_POST_PEFFECT_UPDATE` 在 PC 上是"玩家身上的效果每帧更新"，实参就是那个玩家。
    if (!scan->renderPhase && scan->registered.Has(isaac::runtime::kCallbackPostPeffectUpdate)) {
        LuaCallbackInvoker invoker = LuaCallbackInvoker::ForEntity(entity);
        isaac::runtime::CallbackDispatcher dispatcher{g_CallbackRegistry, invoker};
        static_cast<void>(dispatcher.Dispatch(isaac::runtime::kCallbackPostPeffectUpdate,
                                              isaac::runtime::ThreadAffinity::Any));
    }
    if (!scan->renderPhase && scan->registered.Has(isaac::runtime::kCallbackPostPlayerUpdate)) {
        LuaCallbackInvoker invoker = LuaCallbackInvoker::ForEntity(entity);
        isaac::runtime::CallbackDispatcher dispatcher{g_CallbackRegistry, invoker};
        static_cast<void>(dispatcher.Dispatch(isaac::runtime::kCallbackPostPlayerUpdate,
                                              isaac::runtime::ThreadAffinity::Any));
    }
    // 玩家那张"见过"表**跨房间不清**（玩家跨房间存活，见 `FrameEventState` 的说明）。
    if (!scan->renderPhase && scan->registered.Has(isaac::runtime::kCallbackPostPlayerInit) &&
        NoteNewEntity(g_FrameEventState.seenPlayers, kSeenPlayerCapacity,
                      &g_FrameEventState.seenPlayerCount, entity)) {
        LuaCallbackInvoker invoker = LuaCallbackInvoker::ForEntity(entity);
        isaac::runtime::CallbackDispatcher dispatcher{g_CallbackRegistry, invoker};
        static_cast<void>(dispatcher.Dispatch(isaac::runtime::kCallbackPostPlayerInit,
                                              isaac::runtime::ThreadAffinity::Any));
    }
    if (scan->renderPhase && scan->registered.Has(isaac::runtime::kCallbackPostPlayerRender)) {
        LuaCallbackInvoker invoker = LuaCallbackInvoker::ForEntityWithVector(
            entity, scan->renderOffsetX, scan->renderOffsetY);
        isaac::runtime::CallbackDispatcher dispatcher{g_CallbackRegistry, invoker};
        static_cast<void>(dispatcher.Dispatch(isaac::runtime::kCallbackPostPlayerRender,
                                              isaac::runtime::ThreadAffinity::Any));
    }
}

// 房间实体表里的每一个实体：先分类，再交给对应那一类。
//
// 玩家**不走这里**（玩家不在房间实体表里，而在引擎自己的玩家向量里，见
// `VisitPlayerEntities`）；这里即使遇到玩家类的实体也直接跳过，免得同一次派发里
// 被数成两遍（引擎的碰撞分区里玩家确实会出现）。
void OnEntityEvent(void* context, std::uintptr_t entity) noexcept {
    auto* scan = static_cast<EntityEventScan*>(context);
    if (scan == nullptr) {
        return;
    }
    switch (isaac::runtime::ClassifyCallbackEntity(entity)) {
        case isaac::runtime::CallbackEntityClass::Npc:
            DispatchNpcEntityEvents(scan, entity);
            break;
        case isaac::runtime::CallbackEntityClass::Familiar:
            DispatchFamiliarEntityEvents(scan, entity);
            break;
        case isaac::runtime::CallbackEntityClass::Tear:
            DispatchTearEntityEvents(scan, entity);
            break;
        case isaac::runtime::CallbackEntityClass::Projectile:
            DispatchProjectileEntityEvents(scan, entity);
            break;
        case isaac::runtime::CallbackEntityClass::Laser:
            DispatchLaserEntityEvents(scan, entity);
            break;
        case isaac::runtime::CallbackEntityClass::Knife:
            DispatchKnifeEntityEvents(scan, entity);
            break;
        case isaac::runtime::CallbackEntityClass::Effect:
            DispatchEffectEntityEvents(scan, entity);
            break;
        case isaac::runtime::CallbackEntityClass::Bomb:
            DispatchBombEntityEvents(scan, entity);
            break;
        case isaac::runtime::CallbackEntityClass::Pickup:
            DispatchPickupEntityEvents(scan, entity);
            break;
        case isaac::runtime::CallbackEntityClass::Player:
        case isaac::runtime::CallbackEntityClass::None:
        default:
            break;
    }
}

void OnEntityEventPlayer(void* context, std::uintptr_t entity) noexcept {
    auto* scan = static_cast<EntityEventScan*>(context);
    if (scan == nullptr || entity == 0) {
        return;
    }
    DispatchPlayerEntityEvents(scan, entity);
}

// 渲染时机的实体族派发。**调用方负责开/关派发窗口**（`EngineGuardEnterDispatch` /
// `EngineGuardLeaveDispatch`）：本函数与那条每帧渲染回调共用同一个窗口。
//
// 两条入场条件：
//   * 渲染族里没人登记 ⇒ 直接不做（省一次渲染偏移读数 + 一趟实体表遍历）；
//   * 渲染偏移读不到 ⇒ **整族不派发**。PC 的这个实参是必需的（模组用它定位自己的绘制），
//     给 `nil` 会让模组当场报错或画错位置 —— 那比"这一帧没有事件"难查得多。
//     读数失败是瞬时的（房间/游戏指针还没就绪），下一帧会重试。
void DispatchEntityRenderEvents(const RegisteredCallbackMask& registered) noexcept {
    if (!AnyEntityRenderFamilyRegistered(registered)) {
        return;
    }
    GameRenderOffset offset{};
    if (ReadGameRenderOffset(GameOwnerSlot(), &offset) != GameRoomObservation::Success) {
        return;
    }
    EntityEventScan scan{};
    scan.registered = registered;
    scan.renderPhase = true;
    scan.renderOffsetX = offset.x;
    scan.renderOffsetY = offset.y;
    isaac::runtime::VisitRoomEntities(&OnEntityEvent, &scan);
    isaac::runtime::VisitPlayerEntities(&OnEntityEventPlayer, &scan);
}

}  // namespace

void DispatchFrameEvents() {
    const RegisteredCallbackMask registered = BuildRegisteredCallbackMask();
    const bool wantsEntityScan = AnyEntityFamilyRegistered(registered);
    const bool wantsRoom = registered.Has(isaac::runtime::kCallbackPostNewRoom);
    const bool wantsLevel = registered.Has(isaac::runtime::kCallbackPostNewLevel);
    // 一种都没登记就整段跳过：这条路径每帧都要读房间身份，有实体时还要扫实体表，
    // "没人听"的时候一律不做（不白花每帧的引擎读取与 `svcQueryMemory`）。
    if (!wantsEntityScan && !wantsRoom && !wantsLevel) {
        return;
    }

    GameLocationKey location{};
    const bool haveLocation =
        ReadGameLocationKey(GameOwnerSlot(), &location) == GameRoomObservation::Success;
    if (!haveLocation) {
        // 读数失败 ⇒ 身份作废，等下一次成功读数重新"起底"。**只**作废身份，不清"见过"的表：
        // 一次瞬时读失败不该让模组收到一次凭空的 INIT。
        g_FrameEventState.roomKnown = 0;
        g_FrameEventState.levelKnown = 0;
    // 新会话 ⇒ 起始房间记账也清空（否则上一局的记录会被当成这一局的起始房间）。
    ResetLevelStartRoomTracker();
    }

    bool enteredNewRoom = false;
    bool enteredNewLevel = false;
    if (haveLocation) {
        // 判定抽到 `frame_event_decision.hpp`（纯函数、宿主上逐条验）：三条口径 ——
        // 开局起始房间补一次、读不到身份时不判也不消费、中途加载时不拿残值当身份。
        const isaac::runtime::FrameRoomDecision decision =
            isaac::runtime::DecideFrameRoomEvents(
            true, g_FrameEventState.roomKnown != 0, g_FrameEventState.levelKnown != 0,
            location.stage == g_FrameEventState.location.stage &&
                location.stageType == g_FrameEventState.location.stageType,
            location.SameRoom(g_FrameEventState.location),
            g_FrameEventState.initialRoomPending);
        enteredNewLevel = decision.newLevel;
        if (decision.initialRoomConsumed) {
            g_FrameEventState.initialRoomPending = 0;
        }
        if (decision.newRoom) {
            enteredNewRoom = true;
            // 换房间 = 房间里的实体整批换掉，"见过"的表随之作废，于是新房间里原本摆着的
            // 实体（掉落物、跟班、敌人…）会各自收到一次 INIT（见文件上方"代价与已知差异"）。
            // 玩家那张表**不清**：玩家跨房间存活，清了会让同一个玩家每次换房都收到一次 INIT。
            ClearSeenEntities(&g_FrameEventState.seenPickupCount);
            ClearSeenEntities(&g_FrameEventState.seenNpcCount);
            ClearSeenEntities(&g_FrameEventState.seenFamiliarCount);
            ClearSeenEntities(&g_FrameEventState.seenTearCount);
            ClearSeenEntities(&g_FrameEventState.seenProjectileCount);
            ClearSeenEntities(&g_FrameEventState.seenLaserCount);
            ClearSeenEntities(&g_FrameEventState.seenKnifeCount);
            ClearSeenEntities(&g_FrameEventState.seenEffectCount);
            ClearSeenEntities(&g_FrameEventState.seenBombCount);
        }
        // 开始房间记账（批次 106）：层号变了、或**第一次**读到身份，都把当时的房间索引记下来。
        // 为什么"第一次"也算：那是我们唯一能知道本层起始房间的时机；正常路径（开局/换层后第一次
        // 看到新层）玩家正站在起始房间。已知偏的情形只有"运行时在该层中途才加载"，写在
        // `api_deviation.cpp` 的 0x03010011 那条里。
        if (enteredNewLevel || g_FrameEventState.levelKnown == 0) {
            g_LevelStartRoom.Observe(location.stage, location.stageType, location.roomIndex);
        }
        // ★ 2026-09-22 更正：这句话以前是这么写的 ——"第一次读到身份时**不判变化**：那时这一局
        // 刚开局，`MC_POST_GAME_STARTED` 已经承担了'开局'这件事，再补一次'进入新房间'会让模组
        // 把开局那间房当成第二间房"。**前半段的前提是错的**：PC 在开局时"开局事件"与
        // "进入第一间房"是**两件事**（`POST_GAME_STARTED` → `POST_NEW_LEVEL` → `POST_NEW_ROOM`），
        // 少发后者会让依赖房间事件的模组在开局房间里彻底不工作（EID 献祭房信息就是这样丢的）。
        // 现在的口径：**开局那一间房补派一次**（由 `initialRoomPending` 驱动，见上面派发处）；
        // 只有"运行时在该层中途才加载"（没有 `initialRoomPending`）时才不判变化。
        g_FrameEventState.location = location;
        g_FrameEventState.roomKnown = 1;
        g_FrameEventState.levelKnown = 1;
    }

    // 先扫实体与玩家，再派发"换房/换层"。顺序是照 PC 的观感定的：换层时模组先收到
    // `POST_NEW_LEVEL`、再收到 `POST_NEW_ROOM`，而实体的 INIT/UPDATE 属于"新房间已经在了"
    // 之后的事 —— 放在前面会让模组在一个它还不认识的房间里收到实体事件。
    if (wantsEntityScan) {
        EntityEventScan scan{};
        scan.registered = registered;
        scan.renderPhase = false;
        isaac::runtime::VisitRoomEntities(&OnEntityEvent, &scan);
        isaac::runtime::VisitPlayerEntities(&OnEntityEventPlayer, &scan);
    }

    // ★ 这两条**不受"有没有人登记"影响**：判"换房/换层"要读的那四个字本来就要读，而
    // 派发器会把计数记在最前面 ⇒ 即使一条登记都没有，"引擎确实到了这个时机"仍然留在
    // 派发计数里。那正是设备侧区分"事件没送到"与"送到了没人听"的唯一依据。
    // （按实体派发的那一族要遍历实体表/玩家向量，只在有人登记时才做 ⇒ 它们的计数
    //   只代表"有人听的时候"）。
    if (enteredNewLevel) {
        LuaCallbackInvoker invoker{0, false, false};
        isaac::runtime::CallbackDispatcher dispatcher{g_CallbackRegistry, invoker};
        static_cast<void>(dispatcher.Dispatch(isaac::runtime::kCallbackPostNewLevel,
                                              isaac::runtime::ThreadAffinity::Any));
    }
    if (enteredNewRoom) {
        LuaCallbackInvoker invoker{0, false, false};
        isaac::runtime::CallbackDispatcher dispatcher{g_CallbackRegistry, invoker};
        static_cast<void>(dispatcher.Dispatch(isaac::runtime::kCallbackPostNewRoom,
                                              isaac::runtime::ThreadAffinity::Any));
    }
}

void DispatchPostUpdate() {
    // 开局事件先派发：PC 上它发生在这一局的第一帧之前，放到 POST_UPDATE 之前最接近原语义。
    // 这里才是真正跑模组 Lua 的地方 —— 中继本身只记账（见 `NoteGameStarted` 的注释）。
    if (const std::uint32_t pending = g_PendingGameStarted.load(std::memory_order_acquire);
        pending != 0 && IsReady()) {
        // **只有真的派发出去才清标志**：清早了就把开局事件永久吞掉（真机症状 = 计数一直 0/3）。
        // 没派发成就留到下一帧再试 —— 它只是"晚到"，语义上仍然是"这一局的开局事件"。
        if (DispatchPostGameStarted(pending == kGameStartedFromSave)) {
            g_PendingGameStarted.store(0, std::memory_order_release);
            // ★ 2026-09-22：开局这件事派发成功之后，把**起始房间**也当成"进了一个新层 + 新房间"。
            // 顺序与 PC 一致（`POST_GAME_STARTED` → `POST_NEW_LEVEL` → `POST_NEW_ROOM`），
            // 而且就在**同一帧**的 `DispatchFrameEvents()` 里补：模组（EID）在开局回调里建的表，
            // 到了 `NEW_ROOM` 那一步已经能用了。判定与理由见 `frame_event_decision.hpp`。
            g_FrameEventState.initialRoomPending = 1;
        }
    }
    if (!IsReady() || g_LuaState == nullptr ||
        !isaac::runtime::ShouldDispatchManagedCallbacks()) {
        return;
    }
    // 引擎内存可读性缓存只在派发期间有效（见 `engine_memory_guard.hpp`）：游戏线程正在执行
    // 我们的 Lua，这段时间里没有东西会改页表，所以这一层缓存不可能读到过期结论；
    // 出了派发就关闭，任何非派发路径仍然每次都做真正的 `svcQueryMemory`。
    //
    // 每帧事件与 POST_UPDATE 共用**同一个**窗口（2026-09-18）：两者都发生在本帧这一个派发时机里，
    // 分成两段进入/退出只会让每帧多两次往返。口径没变 —— `Isaac.GetFrameCount()` 唯一的累加点
    // 仍是下面那次 `Dispatch(kCallbackPostUpdate, …)`，没有登记 POST_UPDATE 时它照旧不推进。
    isaac::runtime::EngineGuardEnterDispatch();
    if (g_CallbackRegistry.CountOf(isaac::runtime::kCallbackPostUpdate) != 0) {
        LuaCallbackInvoker invoker{0, false, true};
        isaac::runtime::CallbackDispatcher dispatcher{g_CallbackRegistry, invoker};
        static_cast<void>(dispatcher.Dispatch(isaac::runtime::kCallbackPostUpdate,
                                              isaac::runtime::ThreadAffinity::Any));
    }
    DispatchFrameEvents();
    isaac::runtime::EngineGuardLeaveDispatch();
}

void DispatchPostRender(uintptr_t manager) {
    if (!IsReady() || manager == 0 || g_LuaState == nullptr ||
        !isaac::runtime::ShouldDispatchManagedCallbacks()) {
        return;
    }
    // 入场判据从"有人登记每帧渲染回调"放宽成"每帧渲染回调或实体渲染族里有人登记"（2026-09-18）：
    // 两条路径共用同一个渲染时机、同一个派发窗口，分成两段只会让每帧多两次窗口进出。
    //
    // 这里刻意**保留** `CountOf` 这一句（而不是直接用下面位图里的那一位）：它是"这条每帧渲染
    // 路径有没有人听"的判据，也是 `test_lua_callback_pipeline` 用来证明"核心 TU 用的是**共享**
    // 注册表、没有自己留一份"的证据之一。判据本身没变，只是多了一条并行的入场条件。
    const bool wantsPostRender =
        g_CallbackRegistry.CountOf(isaac::runtime::kCallbackPostRender) != 0;
    const RegisteredCallbackMask registered = BuildRegisteredCallbackMask();
    if (!wantsPostRender && !AnyEntityRenderFamilyRegistered(registered)) {
        return;
    }
    // 帧归因探针的帧边界就定在这里：这条路径已经要求房间与玩家都成立，所以只有"在局内、
    // EID 正在工作"的帧才进样本（生产构建里这几个调用是空操作）。它现在也覆盖实体渲染族
    // 的那些帧 —— 覆盖面变大是这条路径的题意（"本帧走过托管派发"），不是口径变了。
    isaac::runtime::EngineFrameProbeOnManagedDispatch();
    isaac::runtime::EngineGuardEnterDispatch();
    isaac::runtime::EngineFrameProbeOnDispatchBegin();
    if (wantsPostRender) {
        LuaCallbackInvoker invoker{manager, true, false};
        isaac::runtime::CallbackDispatcher dispatcher{g_CallbackRegistry, invoker};
        static_cast<void>(dispatcher.Dispatch(isaac::runtime::kCallbackPostRender,
                                              isaac::runtime::ThreadAffinity::Any));
    }
    DispatchEntityRenderEvents(registered);
    isaac::runtime::EngineFrameProbeOnDispatchEnd();
    isaac::runtime::EngineGuardLeaveDispatch();
}

// --- 回调面补齐（批次 102）：四个事件中继的派发入口 -------------------------------
//
// 这一族与"每帧事件"那一族的共同点：调用点都在**引擎自己的函数里**（入口中继的回调体），
// 不是我们的帧时机。所以每一个都自己做三件事：
//   ① 判"现在能不能派发"（`IsReady` / Lua 状态 / `ShouldDispatchManagedCallbacks`）；
//   ② 判"有没有人登记"（没有人登记就直接返回 —— 不给没有听众的事件付代价）；
//   ③ 进出派发窗口（`EngineGuardEnterDispatch` / `LeaveDispatch`，与其它派发点同一口径）。
//
// 实参一律**照 PC 的签名逐位对齐**（依据写在 `runtime_constants.hpp` 的靶点注释里），
// 拿不到的实参压 `nil` 并在偏离台账里登记 —— 本轮唯一一处是 `MC_PRE_USE_ITEM` / `MC_USE_ITEM`
// 的第二个实参 `RNG`（PC 上由引擎现造，我们没有对应对象）。
namespace {

//: 把"玩家"作为一个实体实参压栈（视图与 `Isaac.GetRoomEntities()` 一致）。
void AddPlayerArgument(CallbackArguments* arguments, std::uintptr_t player) noexcept {
    if (arguments != nullptr) {
        arguments->AddEntity(player);
    }
}

}  // namespace

void DispatchPreGameExit(bool shouldSave) {
    if (!IsReady() || g_LuaState == nullptr) {
        return;
    }
    if (g_CallbackRegistry.CountOf(isaac::runtime::kCallbackPreGameExit) == 0) {
        return;
    }
    // ★ 对"房间/玩家可解析"的要求在这里**必须放宽**：`Game::Exit` 触发时这一局正在结束，
    // `ShouldDispatchManagedCallbacks()`（要求房间非空且至少一个可验证玩家）很可能已经不成立。
    // 用它会让"退出时保存配置"这条**唯一的**保存点再次静默失效 —— 而那正是本批要修的东西。
    // 付出的代价写在明处：如果 Lua 处理器读了已经不存在的引擎对象，它会在自己的那一行报错，
    // 错误进环形历史、回调被隔离（不向上抛）。EID 的 `EID:OnGameExit` 恰好是"先算术、后调
    // `EID.SaveData`、最后才碰渲染"的顺序，所以报错也不会发生在保存之前。
    isaac::runtime::EngineGuardEnterDispatch();
    LuaCallbackInvoker invoker{0, false, false};
    invoker.arguments.AddBoolean(shouldSave);
    isaac::runtime::CallbackDispatcher dispatcher{g_CallbackRegistry, invoker};
    static_cast<void>(dispatcher.Dispatch(isaac::runtime::kCallbackPreGameExit,
                                          isaac::runtime::ThreadAffinity::Any));
    isaac::runtime::EngineGuardLeaveDispatch();
}

bool DispatchPreUseItem(std::uintptr_t player, std::int32_t collectibleType, std::int32_t useFlags,
                        std::int32_t activeSlot, std::int32_t customVarData) {
    if (!IsReady() || g_LuaState == nullptr ||
        !isaac::runtime::ShouldDispatchManagedCallbacks()) {
        return false;
    }
    if (g_CallbackRegistry.CountOf(isaac::runtime::kCallbackPreUseItem) == 0) {
        return false;
    }
    isaac::runtime::EngineGuardEnterDispatch();
    LuaCallbackInvoker invoker{0, false, false};
    // PC 签名：`(CollectibleType, RNG, EntityPlayer, UseFlags, ActiveSlot, CustomVarData)`。
    // RNG 压 `nil`（偏离已登记：EID 的处理器全都忽略它）。
    invoker.arguments.AddInteger(collectibleType);
    invoker.arguments.AddNil();
    AddPlayerArgument(&invoker.arguments, player);
    invoker.arguments.AddInteger(useFlags);
    invoker.arguments.AddInteger(activeSlot);
    invoker.arguments.AddInteger(customVarData);
    isaac::runtime::CallbackDispatcher dispatcher{g_CallbackRegistry, invoker};
    // 过滤值 = 第一个实参（PC 的 `AddCallback(id, fn, entityId)`：`MC_PRE_USE_ITEM` 的可选实参
    // 类型就是 `CollectibleType`）。EID 用它把 6 个处理器分别绑到 Smelter / Void / Flip /
    // D4 / Genesis / Lemegeton 上，不筛的话每一个都会在**任何**主动道具使用时跑。
    const isaac::runtime::CallbackDispatchOutcome outcome =
        dispatcher.DispatchModifying(isaac::runtime::kCallbackPreUseItem,
                                     isaac::runtime::ThreadAffinity::Any,
                                     static_cast<std::int64_t>(collectibleType));
    isaac::runtime::EngineGuardLeaveDispatch();
    // PC 约定：任一条返回 true 即"取消这次使用"。
    return outcome.blocked();
}

void DispatchUseItem(std::uintptr_t player, std::int32_t collectibleType, std::int32_t useFlags,
                     std::int32_t activeSlot, std::int32_t customVarData) {
    if (!IsReady() || g_LuaState == nullptr ||
        !isaac::runtime::ShouldDispatchManagedCallbacks()) {
        return;
    }
    if (g_CallbackRegistry.CountOf(isaac::runtime::kCallbackUseItem) == 0) {
        return;
    }
    isaac::runtime::EngineGuardEnterDispatch();
    LuaCallbackInvoker invoker{0, false, false};
    invoker.arguments.AddInteger(collectibleType);
    invoker.arguments.AddNil();  // RNG（同上）
    AddPlayerArgument(&invoker.arguments, player);
    invoker.arguments.AddInteger(useFlags);
    invoker.arguments.AddInteger(activeSlot);
    invoker.arguments.AddInteger(customVarData);
    isaac::runtime::CallbackDispatcher dispatcher{g_CallbackRegistry, invoker};
    // **不读返回值**：PC 上 `MC_USE_ITEM` 的返回值只表示"要不要播使用动画"（返回 table 还能改
    // 放电/移除），它**不拦**任何事。我们不复刻那部分（见存档 README 的偏离登记），所以用
    // 只通知的那条入口，读它反而会让"读了一个本来用不上的值"变成下一轮的误解。
    static_cast<void>(dispatcher.DispatchFiltered(isaac::runtime::kCallbackUseItem,
                                                 isaac::runtime::ThreadAffinity::Any,
                                                 static_cast<std::int64_t>(collectibleType)));
    isaac::runtime::EngineGuardLeaveDispatch();
}

void DispatchUseCard(std::uintptr_t player, std::int32_t card, std::int32_t useFlags) {
    if (!IsReady() || g_LuaState == nullptr ||
        !isaac::runtime::ShouldDispatchManagedCallbacks()) {
        return;
    }
    if (g_CallbackRegistry.CountOf(isaac::runtime::kCallbackUseCard) == 0) {
        return;
    }
    isaac::runtime::EngineGuardEnterDispatch();
    LuaCallbackInvoker invoker{0, false, false};
    // PC 签名：`(Card, EntityPlayer, UseFlags)`。
    invoker.arguments.AddInteger(card);
    AddPlayerArgument(&invoker.arguments, player);
    invoker.arguments.AddInteger(useFlags);
    isaac::runtime::CallbackDispatcher dispatcher{g_CallbackRegistry, invoker};
    static_cast<void>(dispatcher.DispatchFiltered(isaac::runtime::kCallbackUseCard,
                                                 isaac::runtime::ThreadAffinity::Any,
                                                 static_cast<std::int64_t>(card)));
    isaac::runtime::EngineGuardLeaveDispatch();
}

void DispatchUsePill(std::uintptr_t player, std::int32_t pillEffect, std::int32_t useFlags) {
    if (!IsReady() || g_LuaState == nullptr ||
        !isaac::runtime::ShouldDispatchManagedCallbacks()) {
        return;
    }
    if (g_CallbackRegistry.CountOf(isaac::runtime::kCallbackUsePill) == 0) {
        return;
    }
    isaac::runtime::EngineGuardEnterDispatch();
    LuaCallbackInvoker invoker{0, false, false};
    // PC 签名：`(PillEffect, EntityPlayer, UseFlags)` —— **没有**药丸颜色这个实参
    // （EID 的 `OnUsePill` 自己从玩家口袋读颜色：`EID.PlayerHeldPill[...]`）。
    invoker.arguments.AddInteger(pillEffect);
    AddPlayerArgument(&invoker.arguments, player);
    invoker.arguments.AddInteger(useFlags);
    isaac::runtime::CallbackDispatcher dispatcher{g_CallbackRegistry, invoker};
    static_cast<void>(dispatcher.DispatchFiltered(isaac::runtime::kCallbackUsePill,
                                                 isaac::runtime::ThreadAffinity::Any,
                                                 static_cast<std::int64_t>(pillEffect)));
    isaac::runtime::EngineGuardLeaveDispatch();
}

bool DispatchPrePickupCollision(std::uintptr_t pickup, std::uintptr_t collider, bool low,
                                std::int32_t pickupVariant) {
    if (!IsReady() || g_LuaState == nullptr ||
        !isaac::runtime::ShouldDispatchManagedCallbacks()) {
        return false;
    }
    if (g_CallbackRegistry.CountOf(isaac::runtime::kCallbackPrePickupCollision) == 0) {
        return false;
    }
    isaac::runtime::EngineGuardEnterDispatch();
    LuaCallbackInvoker invoker{0, false, false};
    // PC 签名：`(EntityPickup, Collider [Entity], Low [bool])`。
    // 两个实参都是实体视图（EID 的处理器读 `collider.Type` 判"是玩家/跟班还是别的"）。
    AddPlayerArgument(&invoker.arguments, pickup);
    invoker.arguments.AddEntity(collider);
    invoker.arguments.AddBoolean(low);
    isaac::runtime::CallbackDispatcher dispatcher{g_CallbackRegistry, invoker};
    // 过滤值 = **掉落物的变体**：PC 给这条回调的可选实参类型是 `PickupVariant`（而第一个实参是
    // 实体、不是数字，所以过滤值必须由调用点从实体上读出来并单独传进来 —— 见
    // `CallbackDispatchOutcome` 的说明）。反汇编也印证了这个字段：
    // `handle_collision` 开头就是 `ldr w8, [x0, #0x3C]; cmp w8, #0x64`（变体 100 = 可拾取物）。
    const isaac::runtime::CallbackDispatchOutcome outcome =
        dispatcher.DispatchModifying(isaac::runtime::kCallbackPrePickupCollision,
                                     isaac::runtime::ThreadAffinity::Any,
                                     static_cast<std::int64_t>(pickupVariant));
    isaac::runtime::EngineGuardLeaveDispatch();
    // PC 的三态里 `true`（忽略碰撞）与 `false`（算碰撞但不执行内部代码）**都不执行**内部代码，
    // 只有 `nil` 才照常执行 ⇒ 判据是"**非 nil**"而不是"真值"。
    return outcome.anyNonNil;
}

void DispatchPreRoomEntitySpawn(std::int32_t entityType, std::int32_t variant,
                                std::int32_t subType, std::int32_t gridIndex,
                                std::int32_t seed) {
    if (!IsReady() || g_LuaState == nullptr ||
        !isaac::runtime::ShouldDispatchManagedCallbacks()) {
        return;
    }
    if (g_CallbackRegistry.CountOf(isaac::runtime::kCallbackPreRoomEntitySpawn) == 0) {
        return;
    }
    isaac::runtime::EngineGuardEnterDispatch();
    LuaCallbackInvoker invoker{0, false, false};
    // PC 签名：`(EntityType, Variant, SubType, GridIndex, Seed)` —— 五个整数，**没有实体实参**。
    invoker.arguments.AddInteger(entityType);
    invoker.arguments.AddInteger(variant);
    invoker.arguments.AddInteger(subType);
    invoker.arguments.AddInteger(gridIndex);
    invoker.arguments.AddInteger(seed);
    isaac::runtime::CallbackDispatcher dispatcher{g_CallbackRegistry, invoker};
    // 用"只通知"那条入口：PC 给这条的可选实参是 `-`（没有过滤语义），返回值是一个
    // **可以覆盖 Type/Variant/SubType 的表** —— 我们第一版不支持表覆盖（见存档 README 的偏离登记），
    // 所以**不读**返回值（读了也只有"收到一张表"这一个事实，没有可用的语义）。
    static_cast<void>(dispatcher.Dispatch(isaac::runtime::kCallbackPreRoomEntitySpawn,
                                          isaac::runtime::ThreadAffinity::Any));
    isaac::runtime::EngineGuardLeaveDispatch();
}

std::uint64_t DispatchPostGetCollectible(void* itemPool, std::uint32_t itemPoolType,
                                         std::uint32_t seed, std::uint32_t decrease,
                                         std::uint32_t selectedCollectible) {
    (void)itemPool;
    // 打包口径与 `DispatchPreGetCollectible` 完全相同（高 32 位非零 = "拿到了替换值"），
    // 这样中继回调那侧只有一条判断。
    if (!IsReady() || g_InPreGetCollectibleDispatch || g_LuaState == nullptr) {
        return 0;
    }
    if (!isaac::runtime::ShouldDispatchManagedCallbacks()) {
        return 0;
    }
    if (g_CallbackRegistry.CountOf(isaac::runtime::kCallbackPostGetCollectible) == 0) {
        return 0;
    }
    isaac::runtime::EngineGuardEnterDispatch();
    LuaCallbackInvoker invoker{0, false, false};
    // PC 签名：`(SelectedCollectible, ItemPoolType, Decrease [bool], Seed [int])`。
    // ★ 这一条与 `MC_PRE_GET_COLLECTIBLE` 的差别就在第一个实参：PRE 那侧引擎还没选，所以
    // 只有 `(poolType, decrease, seed)`；POST 这一侧我们**拿得到**刚选出来的道具，必须放在
    // 第一位 —— EID 的 `EID:postGetCollectible(selectedCollectible, itemPoolType)` 就是按
    // 这个顺序读的（`main.lua:259`）。
    invoker.arguments.AddInteger(static_cast<std::int64_t>(selectedCollectible));
    invoker.arguments.AddInteger(static_cast<std::int64_t>(itemPoolType));
    invoker.arguments.AddBoolean(decrease != 0);
    invoker.arguments.AddInteger(static_cast<std::int64_t>(seed));
    isaac::runtime::CallbackDispatcher dispatcher{g_CallbackRegistry, invoker};
    const isaac::runtime::CallbackDispatchOutcome outcome =
        dispatcher.DispatchModifying(isaac::runtime::kCallbackPostGetCollectible,
                                     isaac::runtime::ThreadAffinity::Any,
                                     isaac::runtime::CallbackRegistry::kNoCallbackFilter);
    isaac::runtime::EngineGuardLeaveDispatch();
    if (!outcome.hasInteger || outcome.integer < 0 ||
        static_cast<std::uint64_t>(outcome.integer) >
            std::numeric_limits<std::uint32_t>::max()) {
        return 0;
    }
    return (std::uint64_t{1} << 32) | static_cast<std::uint32_t>(outcome.integer);
}

std::uint64_t DispatchPreGetCollectible(void* itemPool, std::uint32_t itemPoolType,
                                        std::uint32_t seed, std::uint32_t noDecrease,
                                        std::uint32_t lastCollectibleType) {
    (void)itemPool;
    (void)lastCollectibleType;
    if (!IsReady() || g_InPreGetCollectibleDispatch || g_LuaState == nullptr) {
        return 0;
    }
    if (!isaac::runtime::ShouldDispatchManagedCallbacks()) {
        return 0;
    }
    if (g_CallbackRegistry.CountOf(isaac::runtime::kCallbackPreGetCollectible) == 0) {
        return 0;
    }
    // 打包口径（调用方 = 取道具中继的回调体，只有它读这两个位）：
    //   bit 32 = "拿到了替换值"，`value` 里有那 32 位；
    //   bit 33 = "**返回过非 nil**"（可能是 `false`、字符串…，但没有可用整数）。
    // 为什么要第二位：PC 文档写着"若 `MC_PRE_GET_COLLECTIBLE` 返回了非 nil，`MC_POST_GET_COLLECTIBLE`
    // 就跳过" —— 那是"非 nil"、不是"有替换值"。只留 bit 32 的话，某条回调返回 `false` 时我们会
    // 照常派发 POST，而 PC 不会（多派发一次 = 模组多做一遍它以为不该做的事）。
    isaac::runtime::EngineGuardEnterDispatch();
    LuaCallbackInvoker invoker{0, false, false};
    // PC 签名：`(ItemPoolType, Decrease [bool], Seed [int])` —— 这一条**没有**可选实参
    // （`ModCallbacks.md` 的 Optional Args 栏是 `-`），所以过滤值传"没有过滤语义"。
    invoker.arguments.AddInteger(static_cast<std::int64_t>(itemPoolType));
    invoker.arguments.AddBoolean(noDecrease == 0);
    invoker.arguments.AddInteger(static_cast<std::int64_t>(seed));
    isaac::runtime::CallbackDispatcher dispatcher{g_CallbackRegistry, invoker};
    // ★ 2026-09-20 批次 103：这一条原来**手工取第 0 条登记**（`g_CallbackRegistry.At(id, 0)`），
    // 于是同一 id 上第二条及以后的登记永远收不到事件 —— 与 PC 的"同一 id 可登记多条、按登记顺序
    // 全部调用"不符。现在改走通用派发器（`DispatchModifying`），因此同时获得了：
    //   * 多条登记全部被调用；
    //   * 返回值按文档口径取**第一条**整数（"返回的值不会更新后续回调看到的 SelectedCollectible"）；
    //   * `anyNonNil`（bit 33 的来处）。
    // 重入守卫（`g_InPreGetCollectibleDispatch`）仍然保留：Lua 里直接调
    // `ItemPool:GetCollectible` 会再进这条中继，守卫让内层不派发（引擎照原样跑）。
    g_InPreGetCollectibleDispatch = true;
    const isaac::runtime::CallbackDispatchOutcome outcome =
        dispatcher.DispatchModifying(isaac::runtime::kCallbackPreGetCollectible,
                                     isaac::runtime::ThreadAffinity::Any,
                                     isaac::runtime::CallbackRegistry::kNoCallbackFilter);
    g_InPreGetCollectibleDispatch = false;
    isaac::runtime::EngineGuardLeaveDispatch();
    std::uint64_t packed = outcome.anyNonNil ? (std::uint64_t{1} << 33) : 0;
    if (!outcome.hasInteger) {
        if (outcome.anyNonNil) {
            // 返回了"非 nil 但拿不到整数"的东西（`true`、字符串…）：**记一次回调错误**。
            // 这一条是改动前就有的诊断（原来写的是"非整数 ⇒ 报错"），保留它是因为
            // "报错是响的、假值是哑的" —— 模组在这里返回了没法当道具用的值，属于它自己的 bug，
            // 让它进错误环形历史比静默忽略有用得多。同时仍置 bit 33：PC 的"PRE 返回非 nil
            // ⇒ 跳过 POST"是另一回事（它只看是不是 nil）。
            g_CallbackError.store(true, std::memory_order_release);
        }
        return packed;
    }
    if (outcome.integer < 0 ||
        static_cast<std::uint64_t>(outcome.integer) > std::numeric_limits<std::uint32_t>::max()) {
        // 越界整数：与改动前的口径一致 —— 记一次回调错误，且**不给替换值**
        // （`test_lua_pre_get_collectible` 的 `out_of_range` 场景钉着这一条）。
        g_CallbackError.store(true, std::memory_order_release);
        return packed;
    }
    return packed | (std::uint64_t{1} << 32) | static_cast<std::uint32_t>(outcome.integer);
}

// ---- 批次 106：`Level:GetStartingRoomIndex()` 的派生记账（**外部链接**）-----------------
//
// ⚠️ 这两个函数必须定义在**匿名命名空间之外**：它们要给 `remaining_api.cpp`（另一个 TU）链接。
// 本批第一版把它们定义在匿名命名空间里（内部链接）⇒ 只编译 API 层的宿主 harness 集体链接失败，
// 而宿主门禁把 `-Werror=unused-function` 也一起报了出来（那个警告正是"内部链接、没人用"的信号）。
std::uint32_t StartingRoomIndexForCurrentLevel() noexcept {
    return g_LevelStartRoom.Value();
}

void NoteCurrentLocationForStartRoom() noexcept {
    GameLocationKey location{};
    if (ReadGameLocationKey(GameOwnerSlot(), &location) != GameRoomObservation::Success) {
        return;  // 读不到就不动记录：宁可继续答"还不知道"，也不编一个房间号
    }
    g_LevelStartRoom.Observe(location.stage, location.stageType, location.roomIndex);
}

bool IsReady() {
    return g_Ready.load(std::memory_order_acquire);
}

u32 PostUpdateCount() {
    return g_PostUpdateCount.load(std::memory_order_acquire);
}

#if defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 15
u32 PostRenderCount() {
    return g_PostRenderCount.load(std::memory_order_acquire);
}

u32 PostRenderPausedCount() {
    return g_PostRenderPausedCount.load(std::memory_order_acquire);
}
#endif

#if defined(EXL_DIAGNOSTIC_STAGE) && (EXL_DIAGNOSTIC_STAGE == 16 || EXL_DIAGNOSTIC_STAGE == 17)
bool MusicDiagnosticCycleCompleted() {
    return g_MusicDiagnosticCycleCompleted.load(std::memory_order_acquire);
}
#endif

#if defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 45
bool MusicDiagnosticCurrentId(u32* value) {
    if (value == nullptr || !g_MusicDiagnosticCurrentIdReady.load(std::memory_order_acquire)) {
        return false;
    }
    *value = g_MusicDiagnosticCurrentId.load(std::memory_order_acquire);
    return true;
}
#endif

bool ReadLuaGlobalNumber(const char* name, double* value) {
    if (!IsReady() || g_LuaState == nullptr || name == nullptr || value == nullptr) {
        return false;
    }
    lua_getglobal(g_LuaState, name);
    const bool isNumber = lua_isnumber(g_LuaState, -1) != 0;
    if (isNumber) {
        *value = static_cast<double>(lua_tonumber(g_LuaState, -1));
    }
    lua_pop(g_LuaState, 1);
    return isNumber;
}

std::uint32_t ReadLuaTableNumber(const char* globalName, const char* fieldName,
                                 double* value) {
    if (!IsReady() || g_LuaState == nullptr || globalName == nullptr || fieldName == nullptr ||
        value == nullptr) {
        return 1;
    }
    lua_getglobal(g_LuaState, globalName);
    if (lua_istable(g_LuaState, -1) == 0) {
        lua_pop(g_LuaState, 1);
        return 1;  // 全局不是表：`EID` 还没建出来
    }
    lua_getfield(g_LuaState, -1, fieldName);
    if (lua_isnil(g_LuaState, -1) != 0) {
        lua_pop(g_LuaState, 2);
        return 2;  // 表在，字段是 nil
    }
    if (lua_isnumber(g_LuaState, -1) == 0) {
        lua_pop(g_LuaState, 2);
        return 3;  // 字段在但不是 number
    }
    *value = static_cast<double>(lua_tonumber(g_LuaState, -1));
    lua_pop(g_LuaState, 2);
    return 0;
}

bool ReadLuaTableBoolean(const char* globalName, const char* fieldName, bool* value) {
    if (!IsReady() || g_LuaState == nullptr || globalName == nullptr || fieldName == nullptr ||
        value == nullptr) {
        return false;
    }
    lua_getglobal(g_LuaState, globalName);
    if (lua_istable(g_LuaState, -1) == 0) {
        lua_pop(g_LuaState, 1);
        return false;
    }
    lua_getfield(g_LuaState, -1, fieldName);
    const bool isBoolean = lua_type(g_LuaState, -1) == LUA_TBOOLEAN;
    if (isBoolean) {
        *value = lua_toboolean(g_LuaState, -1) != 0;
    }
    lua_pop(g_LuaState, 2);
    return isBoolean;
}

bool LuaTableFieldIsTable(const char* globalName, const char* fieldName) {
    if (!IsReady() || g_LuaState == nullptr || globalName == nullptr || fieldName == nullptr) {
        return false;
    }
    lua_getglobal(g_LuaState, globalName);
    if (lua_istable(g_LuaState, -1) == 0) {
        lua_pop(g_LuaState, 1);
        return false;
    }
    lua_getfield(g_LuaState, -1, fieldName);
    const bool isTable = lua_istable(g_LuaState, -1) != 0;
    lua_pop(g_LuaState, 2);
    return isTable;
}

std::uint32_t ReadLuaNestedNumber(const char* globalName, const char* tableName,
                                  const char* fieldName, double* value) {
    if (!IsReady() || g_LuaState == nullptr || globalName == nullptr || tableName == nullptr ||
        fieldName == nullptr || value == nullptr) {
        return 1;
    }
    lua_getglobal(g_LuaState, globalName);
    if (lua_istable(g_LuaState, -1) == 0) {
        lua_pop(g_LuaState, 1);
        return 1;
    }
    lua_getfield(g_LuaState, -1, tableName);
    if (lua_istable(g_LuaState, -1) == 0) {
        lua_pop(g_LuaState, 2);
        return 1;
    }
    lua_getfield(g_LuaState, -1, fieldName);
    if (lua_isnil(g_LuaState, -1) != 0) {
        lua_pop(g_LuaState, 3);
        return 2;
    }
    if (lua_isnumber(g_LuaState, -1) == 0) {
        lua_pop(g_LuaState, 3);
        return 3;
    }
    *value = static_cast<double>(lua_tonumber(g_LuaState, -1));
    lua_pop(g_LuaState, 3);
    return 0;
}

bool ReadLuaNestedBoolean(const char* globalName, const char* tableName, const char* fieldName,
                          bool* value) {
    if (!IsReady() || g_LuaState == nullptr || globalName == nullptr || tableName == nullptr ||
        fieldName == nullptr || value == nullptr) {
        return false;
    }
    lua_getglobal(g_LuaState, globalName);
    if (lua_istable(g_LuaState, -1) == 0) {
        lua_pop(g_LuaState, 1);
        return false;
    }
    lua_getfield(g_LuaState, -1, tableName);
    if (lua_istable(g_LuaState, -1) == 0) {
        lua_pop(g_LuaState, 2);
        return false;
    }
    lua_getfield(g_LuaState, -1, fieldName);
    const bool isBoolean = lua_type(g_LuaState, -1) == LUA_TBOOLEAN;
    if (isBoolean) {
        *value = lua_toboolean(g_LuaState, -1) != 0;
    }
    lua_pop(g_LuaState, 3);
    return isBoolean;
}

std::uint32_t RegisteredCallbackCount(std::uint32_t callbackId) {
    return static_cast<std::uint32_t>(g_CallbackRegistry.CountOf(callbackId));
}

bool TakeCallbackError() {
    return g_CallbackError.exchange(false, std::memory_order_acq_rel);
}

#if defined(EXL_PERSISTENCE_TRACE) || defined(EXL_PERSISTENCE_EVENT_DIAGNOSTIC)
u64 CallbackFailureDetail() {
    return g_CallbackFailureDetail.load(std::memory_order_acquire);
}
#endif

} // namespace LuaRuntime
