#include "domain/console/console_panel_state.hpp"
#include "infrastructure/console/console_bridge.hpp"
#include "interfaces/lua/console_controls_menu.hpp"
#include "interfaces/lua/api700_containers.hpp"
#include "interfaces/lua/api700_player.hpp"
#include "interfaces/lua/api700_bindings.hpp"
#include "interfaces/lua/api500_world.hpp"
#include "interfaces/lua/api200_bindings.hpp"
#include "application/shader/shader_pipeline.hpp"
#include "interfaces/lua/class_metadata.hpp"
#include "card_rng_scope.hpp"
#include "interfaces/lua/entity_lifetime.hpp"
#include "lua_runtime.hpp"
#include "notice_integrity_native.hpp"
#include "notice_runtime_bindings.hpp"
#include "native_player_init.hpp"
#include "interfaces/lua/os_api.hpp"
#include "infrastructure/memory/engine_field_access.hpp"
// 批次 106：`Level:GetStartingRoomIndex()` 的派生记账（纯逻辑，见该头文件顶部的取证说明）。
#include "frame_event_decision.hpp"
#include "native_room_events.hpp"
#include "level_start_room.hpp"
// `GameFileReader::Bindings` 出现在公开入口的签名里（`InitializeManifestMod`）：
// 之前它靠别的头间接带进来，宿主 harness 的包含路径不同就会"未声明"，所以显式包含。
#include "game_file_reader.hpp"

#include "game_observer.hpp"
#include "lua_object_handles.hpp"
#include "lua_runtime_state.hpp"
extern "C" {
#include "lgcbudget.h"
}
#include "hook_manager.hpp"
#include "mod_persistence.hpp"
#include "fatal_forensics.hpp"
#include "persistence_event_journal.hpp"
#include "probe_gate.hpp"  // 批次 262：诊断探针总开关（剖析钩子/分配账只在诊断包里装）
#include "program/setting.hpp"

#include <cstdarg>
#include <cstdio>
#include <cstdlib>
#include <ctime>
#include <type_traits>

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
#include "runtime_constants.hpp"

// Every build entry point (production module, diagnostics and the startup
// probes) defines `EXL_LAYERED_RUNTIME`, so the layered headers are required
// unconditionally: the non-layered duplicate implementations no longer exist.
#include "interfaces/lua/engine_frame_probe.hpp"
// 批次 390（2026-10-07）：`MC_INPUT_ACTION` 要给 `entity` 实参，用 `ResolveEnginePlayerAt(0)`
// （与 `Isaac.GetPlayer(0)` **同一条**解析链，见 `isaac_api.hpp` 的声明处）。
#include "interfaces/lua/isaac_api.hpp"
#include "infrastructure/call/engine_call_access.hpp"
#include "infrastructure/memory/engine_memory_guard.hpp"
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
// 批次 393（2026-10-07）：`MC_INPUT_ACTION` 的 `buttonAction` 实参要给**模组（PC）口径**的号
// （引擎内部号与 PC 号不是同一张表，16..23 那一段错开 3）⇒ 用同一条真值源的反表。
#include "interfaces/lua/input_action_map.hpp"
#include "interfaces/lua/mod_menu_api.hpp"
#include "interfaces/lua/isaac_api.hpp"
#include "interfaces/lua/mod_api.hpp"
#include "interfaces/lua/callback_table_api.hpp"
#include "interfaces/lua/mod_lifecycle_api.hpp"
#include "interfaces/lua/api700_grid.hpp"
#include "interfaces/lua/music_api.hpp"
#include "interfaces/lua/remaining_api.hpp"
#include "interfaces/lua/rng_api.hpp"
#include "interfaces/lua/bitset128_api.hpp"
#include "interfaces/lua/vector_api.hpp"
#include "interfaces/lua/sprite_api.hpp"

#if defined(__SWITCH__)
#include "lib/nx/nx.h"
#endif

extern "C" {
#include <lauxlib.h>
#include <lualib.h>
}

// ── 批次 418（2026-10-09）：**owner 编号 → 模组名** 的那张表（掉帧归因的"落名读数"） ──────
//
// 要解决的问题：性能读数里的回调耗时桶只给**属主编号**（`[#17]` 这种），而点数不出名 ——
// 2026-10-08 就是因为这个卡住的："哪一家在每帧烧 1.6 ms" 回答不了。
//
// 为什么不能用现成的"模组清单"去套：那份清单（`mod_menu_api.cpp` 的 `g_entries`）是**引擎给的
// 目录列表**，它在**开关过滤之前**就发布了（`hook_manager.cpp` 先 `ModMenuPublishDiscovered`
// 再 `ApplyToBatch` 把被禁用的剔除）⇒ **被禁用的模组占清单格子、却不消耗 owner 号**；
// 而 owner 号只在模组脚本**真的调用 `RegisterMod`** 时才 +1（同一个模组还能调多次）。
// ⇒ 两套编号之间**没有固定偏移**（实测两对锚点是 +6 与 +4，不是同一个数）。
// 唯一的正解就是**在分配 owner 号的那一刻把名字记下来**。
//
// ★ 口径：`index` = `ModHandle::index`（从 2 起，1 留给 `kRuntimeOwner`），与
//   `runtime_perf.hpp` 的 `RuntimePerfCallbackKey(id, ownerIndex, generation)` 里那个
//   `ownerIndex` **是同一个数** ⇒ 读数可以直接拿 `[#N]` 去查这张表。
// ★ 为什么是 `extern "C"` 的裸符号：读数工具按符号名读它（`tools/read_device_state_via_gdb.py`）；
//   一进匿名命名空间就变成内部链接、符号名带 `_GLOBAL__N_1`，工具那边要跟着改（见技能 §11）。
// ★ `[[gnu::used]]`：这张表**只写、模块内部没人读**（读者在模块外面）⇒ 不加会被优化掉，
//   符号一没，真机读数就永远是"查不到名字"（`g_ModRegistered` 踩过同一个坑）。
// ★ 代价：静态 `.bss` 32 × 64 = 2048 字节，**不进假堆、不在每帧热路径上**
//   （只在模组加载期写一次）。
// ★ 用内建 `unsigned` 而不是 `std::size_t`：这一段**故意放在标准头之前**
//   （`<cstddef>` 还没进来），而且它就是数组维度、不需要 `std::size_t` 那个类型。
static constexpr unsigned kModOwnerNameSlots = 258;
static constexpr unsigned kModOwnerNameCapacity = 64;
// ★★ 必须用**块形式** `extern "C" { … }`：写成 `[[gnu::used]] extern "C" char x[…] = {};`
//    会被 gcc 判成语法错（`expected unqualified-id before string constant`）——
//    属性不能放在 linkage-specification 前面。本构建是 `-Werror` ⇒ 直接编译失败
//    （2026-10-09 本批实撞，与 `mod_menu_native.cpp` 里 `g_ModMenuState` 那条同一个道理）。
extern "C" {
[[gnu::used]] char g_ModOwnerNames[kModOwnerNameSlots][kModOwnerNameCapacity] = {};
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
// Written only by this TU at native frame boundaries; external tools read the
// completed frame and cumulative scheduler counters without a hot data GOT.
__attribute__((visibility("hidden"))) lua_GCBudgetInfo g_RuntimeGcBudgetSnapshot{};
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
int InvokeObservedCallback(lua_State* state);
int InvokeObservedNativeCallback(lua_State* state);

namespace {

// luaL_loadfilex skips a complete leading UTF-8 BOM; luaL_loadbufferx does not.
// File callers borrow the same bytes without copying or changing line numbers.
int LoadFileChunk(lua_State* state, const char* source, std::size_t length,
                  const char* chunkName) {
    if (length >= 3 && static_cast<unsigned char>(source[0]) == 0xef &&
        static_cast<unsigned char>(source[1]) == 0xbb &&
        static_cast<unsigned char>(source[2]) == 0xbf) {
        source += 3;
        length -= 3;
    }
    return luaL_loadbufferx(state, source, length, chunkName, "t");
}

const char* g_LoadingModRoot="";
constexpr char kModMethodsField[] = "__methods";
//: 批次 216（2026-09-30）：**Mod 方法的共享原型表**在 registry 里的键。
//: 为什么需要它：PC 的 `RegisterMod` 返回的是 **table**（`GlobalFunctions.md:101`
//: 「Returns a table which acts the Mod Reference」），我们的 Mod 对象从 2026-09-30 起也是 table
//: ⇒ 每个 Mod 对象要一个**自己的**元表（里面放它自己的句柄），而方法从这张共享原型里找
//: （`__index = 原型`）。原型只是 `kModMetatable.__methods` 那一张表的**同一个引用**。
constexpr char kModPrototypeField[] = "__isaac_mod_methods_prototype";
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
// Legitimate dependency graphs (for example Stats+) exceed eight nested modules.
// Keep a finite bound for recursive require/include without rejecting those graphs.
constexpr std::size_t kStage13RequireMaximumDepth = 32;
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
    // ★★ 2026-09-30 批次 218 更正：**16/17/18 三个名字在 Rep+ 变了**，原来写的是 AB/AB+ 那一套。
    // PC 契约（`analysis/isaacdocs-snapshot/docs/enums/ButtonAction.md:24-29`，逐行原文）：
    //   `|[.abrep]|16 |ACTION_RESTART| Restart run |`
    //   `|[.repplus]|16 |ACTION_FULLSCREEN| Toggle fullscreen **(Value changed with Rep+)** |`
    //   `|[.abrep]|17 |ACTION_FULLSCREEN| … |` / `|[.repplus]|17 |ACTION_MUTE| … **(Value changed with Rep+)** |`
    //   `|[.abrep]|18 |ACTION_MUTE| … |`        / `|[.repplus]|18 |ACTION_RESTART| … **(Value changed with Rep+)** |`
    // 我们跑的是 Rep+（1.7.9b）⇒ 16=FULLSCREEN / 17=MUTE / 18=RESTART。
    // 后果举例：模组写 `ButtonAction.ACTION_RESTART` 想按"重开"键，旧表给它 **16**（Rep+ 里那是全屏）
    // ⇒ 按下去触发的是全屏切换；`ACTION_MUTE` 同理错位。
    // 判据：`runtime/tests/test_lua_button_action_rep_plus.py`。
    {"ACTION_FULLSCREEN", 16}, {"ACTION_MUTE", 17}, {"ACTION_RESTART", 18},
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
// 只在游戏线程的显式整批重载期间置位；终结器和73回调不能递归关闭或新建VM。
bool g_ShuttingDownForModReload = false;
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
    u32 index = g_NextModOwnerIndex.load(std::memory_order_relaxed);
    do {
        if (index > UINT16_MAX) return {}; // 饱和失败，不允许截断后复用其它模组owner。
    } while (!g_NextModOwnerIndex.compare_exchange_weak(index, index + 1,
                                                       std::memory_order_relaxed));
    return isaac::runtime::ModHandle{static_cast<std::uint16_t>(index), 1};
}

// 批次 418（2026-10-09）：把"这个 owner 编号属于哪个模组"记下来（掉帧归因的落名读数）。
//
// 调用点 = `RegisterMod` 分配 owner 号的那一刻 —— **只有这一刻**才知道这个编号是谁。
// 为什么要在这里记、而不是事后拿清单去对：见文件顶部那张表上面那段（清单包含被禁用的模组、
// 属主号不包含 ⇒ 两套编号之间没有固定偏移）。
//
// ★ 只写、不改任何行为；越界一律丢弃（`owner.index` 理论上不会到 32，但**不许**越界写 ——
//   那是本项目的头号事故形态）。
void RecordModOwnerName(std::uint16_t index, const char* name) noexcept {
    if (name == nullptr || index >= kModOwnerNameSlots) {
        return;
    }
    std::strncpy(g_ModOwnerNames[index], name, kModOwnerNameCapacity - 1);
    g_ModOwnerNames[index][kModOwnerNameCapacity - 1] = '\0';
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
// 批次 397（2026-10-07）：`MC_POST_ENTITY_KILL` 的重入守卫。
// 为什么这条**必须**有：`Entity:Kill()` 的 Lua API 走的是**虚槽**（批次 319），而基类槽
// 就是 `Entity::Kill` —— 也就是我们这条入口中继。模组的处理器里只要再调一次
// `entity:Kill()`（很常见：先判再杀），中继又会跑一次 → 又派发一次 → **无限递归**。
// 守卫在派发层（不是回调层）：重入时**跳过派发**，但仍然照常跑原函数。
bool g_InPostEntityKillDispatch = false;
std::atomic<uintptr_t> g_CurrentCallbackManager{0};
// 批次 149："本帧的 Manager"兜底来源（`SetFrameManagerProvider` 发布；宿主夹具不发 ⇒ 空）。
std::atomic<uintptr_t (*)()> g_FrameManagerProvider{nullptr};
// 批次 149：上一次 `Music` 方法解析失败的原因码 —— 只用来把报错写清楚，不参与判据。
//   0 = 没失败过；1 = 不在托管回调派发里；2 = 拿不到 Manager（回调里没有、本帧也没有）；
//   3 = 方法地址没发布（那份绑定缺失）；4 = 入口 16 字节指纹不符（偏移写错）。
std::atomic<u32> g_MusicResolveFailure{0};

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
// 批次 137：`MusicManager:UpdateVolume()` 的单方法槽（与 `MusicResume` 同一个发布/读取形态）。
std::atomic<uintptr_t> g_MusicUpdateVolume{0};
// 批次 138：`MusicManager:Play(ID, Volume)` 的单方法槽（同上）。
std::atomic<uintptr_t> g_MusicPlay{0};
std::atomic<uintptr_t> g_RngSetSeed{0};
std::atomic<uintptr_t> g_RngNext{0};
// 批次 195：`RNG:RandomInt(Max)` / `RNG:RandomFloat()`（发布见 `SetRngRandomBindings`）。
std::atomic<uintptr_t> g_RngRandomUint{0};
std::atomic<uintptr_t> g_RngRandom{0};
// 批次 195：按键号那两条查询（`KAGE::Input::ManagerBase`，发布见 `SetInputButtonBindings`）。
std::atomic<uintptr_t> g_InputIsButtonPressed{0};
std::atomic<uintptr_t> g_InputGetButtonValue{0};
std::atomic<uintptr_t> g_InputIsActionPressed{0};
std::atomic<uintptr_t> g_InputIsActionTriggered{0};
std::atomic<uintptr_t> g_InputGetActionValue{0};
// Font entry points (`KAGE::Graphics::Font`). The Font object these are called on is allocated
// and released by the `Font` family unit, not by the game.
std::atomic<uintptr_t> g_FontCtor{0};
std::atomic<std::uint64_t> g_FontBindingGeneration{0};
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
//: 批次 214：`ANM2::Reset()`。
std::atomic<uintptr_t> g_SpriteReset{0};
std::atomic<uintptr_t> g_SpriteRender{0};
std::atomic<uintptr_t> g_SpriteRenderLayer{0};
std::atomic<uintptr_t> g_SpritePlayRandom{0};
//: 批次 279：overlay 三条（`ANM2::PlayOverlay(char const*, bool)` /
//: `SetLastFrame()` / `SetOverlayFrame(char const*, int)`）。
std::atomic<uintptr_t> g_SpritePlayOverlay{0};
std::atomic<uintptr_t> g_SpriteSetLastFrame{0};
std::atomic<uintptr_t> g_SpriteSetOverlayFrame{0};
//: 批次 280：`ANM2::Stop()`。
std::atomic<uintptr_t> g_SpriteStop{0};
//: 批次 283：四条「按名字查询」（引擎侧 `bool ANM2::Xxx(std::string const&) const`）。
std::atomic<uintptr_t> g_SpriteIsOverlayPlaying{0};
std::atomic<uintptr_t> g_SpriteIsOverlayFinished{0};
std::atomic<uintptr_t> g_SpriteIsEventTriggered{0};
std::atomic<uintptr_t> g_SpriteWasEventTriggered{0};
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
    g_LoadingModRoot=g_Stage13ModRoot.data();
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
    std::array<char,kStage13ModRootCapacity> callerRoot{};
    std::size_t modRootLength=g_Stage13ModRootLength;
    const char* modRoot=g_Stage13ModRoot.data();
    if(isaac::runtime::CopyCallingModRoot(state,callerRoot.data(),callerRoot.size(),&modRootLength,"require"))
        modRoot=callerRoot.data();

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
        &notFoundText, modRoot, modRootLength,
        moduleName != nullptr ? moduleName : "", moduleName != nullptr ? moduleLength : 0);
    if (moduleName == nullptr || moduleLength == 0 || moduleName[0] == '.' ||
        moduleName[moduleLength - 1] == '.' ||
        modRootLength + moduleLength + 6 > kStage13RequirePathCapacity) {
        // `require("")` 就落在这里（EID 的 `EID:GetCurrentModPath()` 用的正是空名），
        // 所以这一条必须带 PC 形状的 "no file '…lua'" 文本。
        return RaiseRequireFailure(state, 19, notFound);
    }

    std::array<char, kStage13RequirePathCapacity> path{};
    std::memcpy(path.data(), modRoot, modRootLength);
    std::size_t pathLength = modRootLength;
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
    if (lua_toboolean(state, -1)) {
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
    if (LoadFileChunk(state, source.data(), length, chunkName) != LUA_OK) {
        --g_Stage13RequireDepth;
        RecordRequireErrorTail(state);
        RecordRequireFailure(22);
        return lua_error(state);  // 保留具体模块、行号及语法/OOM原因。
    }
    lua_pushlstring(state, moduleName, moduleLength);  // PC require 给加载器传模块名。
    if (lua_pcallk(state, 1, 1, 0, 0, nullptr) != LUA_OK) {
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
        // Lua加载器可以只写package.loaded而不return；保留它登记的表或false。
        lua_pushlstring(state, moduleName, moduleLength);
        lua_rawget(state, cacheIndex);
        if (lua_isnil(state, -1)) {
            lua_pop(state, 1);
            lua_pushboolean(state, 1);
        }
    }
    lua_pushlstring(state, moduleName, moduleLength);
    lua_pushvalue(state, -2);
    lua_rawset(state, cacheIndex);
    isaac::runtime::TrackRequiredModule(state,modRoot,moduleName,-1);
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
    std::array<char,kStage13ModRootCapacity> callerRoot{};
    std::size_t modRootLength=g_Stage13ModRootLength;
    const char* modRoot=g_Stage13ModRoot.data();
    if(isaac::runtime::CopyCallingModRoot(state,callerRoot.data(),callerRoot.size(),&modRootLength,"include"))
        modRoot=callerRoot.data();

    if (!g_RequireAvailable || lua_gettop(state) != 1 || lua_type(state, 1) != LUA_TSTRING) {
        return luaL_error(state, "include expects one module path");
    }
    std::size_t moduleLength = 0;
    const char* moduleName = lua_tolstring(state, 1, &moduleLength);
    if (moduleName == nullptr || moduleLength == 0 ||
        modRootLength + moduleLength + 6 > kStage13RequirePathCapacity) {
        return luaL_error(state, "include expects one usable module path");
    }

    std::array<char, kStage13RequirePathCapacity> path{};
    std::memcpy(path.data(), modRoot, modRootLength);
    std::size_t pathLength = modRootLength;
    path[pathLength++] = '/';
    // PC模组同时使用点分模块名与斜杠文件名，显式.lua不能被转成目录或再追加一次。
    const bool extension=moduleLength>=4&&std::memcmp(moduleName+moduleLength-4,".lua",4)==0;
    const std::size_t stemLength=extension?moduleLength-4:moduleLength;
    if(!stemLength){return luaL_error(state,"include rejects this module path");}
    for (std::size_t index = 0; index < stemLength; ++index) {
        const char c=moduleName[index];
        if(c<0x20||c>=0x7f||c==':'||
           ((c=='/'||c=='\\')&&(index==0||index+1==stemLength))||
           (c=='.'&&index+1<stemLength&&moduleName[index+1]=='.')) {
            return luaL_error(state, "include rejects this module path");
        }
        path[pathLength++] = c=='.'||c=='\\' ? '/' : c;
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
                                            &notFoundText, modRoot,
                                            modRootLength, moduleName, moduleLength));
    }

    std::array<char, kStage13RequirePathCapacity + 1> chunkNameStorage{};
    chunkNameStorage[0] = '@';
    std::memcpy(chunkNameStorage.data() + 1, path.data(), pathLength + 1);
    if (LoadFileChunk(state, g_Stage13RequireSource.data(), length, chunkNameStorage.data()) != LUA_OK) {
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

    // 标准库由luaL_requiref登记在registry._LOADED；公开同一张表，不能另建影子缓存。
    // StageAPI的package.loaded[name]=false必须使下一次require真正重读模块。
    luaL_getsubtable(state, LUA_REGISTRYINDEX, "_LOADED");
    const int loadedIndex = lua_gettop(state);
    lua_pushvalue(state, loadedIndex);
    g_RequireCacheRef = luaL_ref(state, LUA_REGISTRYINDEX);
    lua_newtable(state);
    lua_pushvalue(state, loadedIndex);
    lua_setfield(state, -2, "loaded");
    lua_pushvalue(state, -1);
    lua_setfield(state, loadedIndex, LUA_LOADLIBNAME);
    lua_setglobal(state, LUA_LOADLIBNAME);
    lua_pop(state, 1);
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

    // ★★ 批次 216（2026-09-30）：**返回 table，不再返回 userdata** —— 这是 PC 的形态，
    // 我们原来是错的（偏差的代价：中文版 MCM 开菜单那条路直接断，见下）。
    //
    // 证据（三条互相独立）：
    //   ① PC 文档 `tools/pc_contract_docs/GlobalFunctions.md:101`：
    //      「Returns a table which acts as the [Mod Reference](ModReference.md).」；
    //   ② 同一份文档 `ModReference.md:102`：Mod Reference 有一个**变量** `string Name`；
    //   ③ 两个互不相干的模组作者都按"table"写：
    //      · 中文版 MCM `scripts/customcallbacks.lua:161`：`if type(mod) ~= "table" then
    //        error("CustomCallbackHelper.AddCallback Error: No valid mod reference provided")`；
    //      · MinimapAPI `scripts/minimapapi/main.lua:1315`：
    //        `if type(modtable) == "table" and modtable.Name and modtable.AddCallback then`。
    //
    // 我们的代价（真机读数 2026-09-30 傍晚）：中文版 MCM 的 `savehelper.lua:696` 走
    // `SaveHelper.Mod:AddCustomCallback(...)`，而 `SaveHelper.Mod = RegisterMod("Save Helper", 1)`
    // ⇒ `type(mod) == "userdata"` ⇒ 那句 `error(...)` ⇒ **加载期脚本失败**
    // （清单安装结果字 = 21 = ScriptRunFailed）⇒ MCM 的回调一条都没登记 ⇒ **菜单打不开**。
    //
    // 实现：内部句柄仍是那个 `ModHandle` userdata（归属、存档命名空间都在里面，一处不改），
    // 但**它只藏在元表里**（`__handle`），对外给出去的是 table：
    //   * `T.Name` = 模组名（PC 的 `Name` 变量）；
    //   * 方法从**共享原型**经 `__index` 找（`T.AddCallback` 非 nil，`T:AddCallback(...)` 照常）；
    //   * 模组往自己身上写字段（`mod.foo = 1`）现在天然可行 —— 这正是 PC 用 table 的理由。
    auto* mod = static_cast<ModHandle*>(lua_newuserdata(state, sizeof(ModHandle)));  // [U]
    mod->persistenceNamespace = ModPersistence::HashModNamespace(name, std::strlen(name));
    const isaac::runtime::ModHandle ownerHandle = NextModOwner();
    if (ownerHandle.index == 0) return luaL_error(state, "mod owner capacity exceeded");
    mod->ownerPacked = PackModOwner(ownerHandle);
    // 批次 418：把 `owner.index` 与模组名的对应关系留下来（读数用；掉帧归因的"落名"）。
    // 只有这一处知道"这个编号是谁" —— 事后再拿清单去对是错的（清单含被禁用的模组）。
    RecordModOwnerName(ownerHandle.index, name);
    lua_newtable(state);
    lua_setuservalue(state, -2);
    luaL_getmetatable(state, kModMetatable);
    lua_setmetatable(state, -2);      // 句柄自己仍挂旧元表（ModIndex/ModNewIndex 那条路不变）

    lua_newtable(state);                                              // [U T]
    lua_pushstring(state, name);
    lua_setfield(state, -2, "Name");                                  // T.Name = 模组名
    lua_newtable(state);                                              // [U T Mi]
    lua_pushvalue(state, -3);
    lua_setfield(state, -2, "__handle");                              // Mi.__handle = U
    lua_getfield(state, LUA_REGISTRYINDEX, kModPrototypeField);       // [U T Mi 原型]
    lua_setfield(state, -2, "__index");                               // Mi.__index = 原型
    lua_setmetatable(state, -2);                                      // setmetatable(T, Mi) → [U T]
    lua_remove(state, -2);                                            // [T]
    isaac::runtime::TrackLoadedMod(state,-1,g_LoadingModRoot,false);
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
    isaac::runtime::RegisterBitSet128Api(state);
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

// 引擎调用层 / 内存访问层的接口。本文件在**全局** `LuaRuntime` 命名空间里（见
// `lua_runtime_state.hpp` 顶部那条说明），`engine_call::` / `engine_memory::` 这类名字不能直接
// 解析 —— 用一个短名字别名，免得每条判据写的都是完整路径。
using isaac::runtime::engine_call::AsFunction;
using isaac::runtime::engine_call::BytesMatchAt;
using isaac::runtime::engine_call::ValueMatchesAt;
using isaac::runtime::engine_call::VerifyEntryBytes;
using isaac::runtime::engine_memory::AsObject;
using isaac::runtime::engine_memory::FieldAddress;
using isaac::runtime::engine_memory::LoadVerifiedAt;

//: 「这段地址是不是引擎模块的**代码段**」—— 形状与 L1/L2 的 `ReadableCheck` 一致，供引擎调用层注入。
//:
//: 判据**逐条照搬**本文件原有那两处内联查询（`ValidateItemPoolGetCollectibleMethod` 与
//: `ValidateMusicMethod` 各一份，去掉注释后逐字相同）：整段落在**同一段映射**内、
//: `(type & MemState_Type) == MemType_ModuleCodeStatic`、`perm == Perm_Rx`。
//: ★ 这比层里那份通用可读判定（`EngineMemoryReadable`，只要求带 `Perm_R`）**严得多** ——
//:   放宽成"能读就行"就等于允许拿一个数据地址当函数入口去调，所以这条判定按原样保留。
//: 本函数**只判"模块代码段"这一件事**，不比较字节（比较在层的 `VerifyEntryBytes` 里）。
//: 只在设备上定义：它的两个消费者都在 `#if defined(__SWITCH__)` 里（宿主没有 `svcQueryMemory`）。
#if defined(__SWITCH__)
bool IsEngineModuleCodeReadable(uintptr_t address, std::size_t length) {
    if (length == 0 || address > UINTPTR_MAX - length) {
        return false;
    }
    MemoryInfo info{};
    u32 pageInfo = 0;
    if (R_FAILED(svcQueryMemory(&info, &pageInfo, address)) || info.size == 0 ||
        info.addr > UINTPTR_MAX - info.size) {
        return false;
    }
    const uintptr_t end = address + length;
    return address >= info.addr && end <= info.addr + info.size &&
           (info.type & MemState_Type) == MemType_ModuleCodeStatic && info.perm == Perm_Rx;
}
#endif

bool ValidateItemPoolGetCollectibleMethod(uintptr_t address) {
    if (address == 0 || (address & 3) != 0) return false;
#if defined(__SWITCH__)
    constexpr std::size_t entrySize = kPreGetCollectibleRelayExpectedEntry.size();
    constexpr std::size_t totalSize = kPreGetCollectibleRelayExpectedOriginal.size();
    // 先**一次**核对包住整个 16 字节窗口（判据见 `IsEngineModuleCodeReadable`），之后每一次比较都
    // 只在这段已核对过的窗口里做 —— 问内核的次数与原来一样是**一次**（不是每比一段问一次）。
    if (!IsEngineModuleCodeReadable(address, totalSize)) {
        return false;
    }
    // 形态一（旧 IPS 中继）：入口前 4 字节是补丁写入的分支，其余仍是被调用函数的原序言。
    if (BytesMatchAt(address, kPreGetCollectibleRelayExpectedEntry.data(), entrySize) &&
        BytesMatchAt(address + entrySize,
                     kPreGetCollectibleRelayExpectedOriginal.data() + entrySize,
                     totalSize - entrySize)) {
        return true;
    }
    // 形态二（零占洞入口中继）：入口 16 字节整体被改写成 `ldr x16, #8; br x16; .quad 槽地址`。
    // 两个目标都是小端，整字比较与逐字节比较等价；槽地址只做"非零且 8 字节对齐"的轻量核对
    // （它落在我们自己的模块里，这个函数看不到那边的边界）。
    if (!ValueMatchesAt(address, kEntryRelayEntryStubWord0) ||
        !ValueMatchesAt(address + sizeof(kEntryRelayEntryStubWord0), kEntryRelayEntryStubWord1)) {
        return false;
    }
    std::uintptr_t slot = 0;
    if (!LoadVerifiedAt(address + 8, 0, &slot)) {
        return false;
    }
    return slot != 0 && (slot & (alignof(std::uintptr_t) - 1)) == 0;
#else
    return true;
#endif
}



//: 「这 `length` 个字节可读、且**不可执行**吗」—— 形状与 L1/L2 的 `ReadableCheck` 一致，
//: 供引擎调用层（`FieldAddress`）注入。判据**逐条照搬**本文件原来那份（同一个策略在
//: `game_observer.cpp` 里叫 `IsReadableNonExecutableMapping`，那是那个 TU 的内部实现，
//: 这里按原样保留一份，不做跨 TU 合并）。
//: ★ 与 `IsEngineModuleCodeReadable` 是**两种不同的判定**，不许互相替换：这份允许数据段
//:   （只要带 `Perm_R`），但要求**不带** `Perm_X`；那份只认模块映像的代码段。
bool IsReadableMusicObject(uintptr_t address, std::size_t length) {
#if defined(__SWITCH__)
    MemoryInfo info{};
    u32 pageInfo = 0;
    if (R_FAILED(svcQueryMemory(&info, &pageInfo, address)) || info.size == 0 ||
        info.addr > UINTPTR_MAX - info.size || address > UINTPTR_MAX - length) {
        return false;
    }
    const uintptr_t end = address + length;
    return address >= info.addr && end <= info.addr + info.size &&
           (info.perm & Perm_R) != 0 && (info.perm & Perm_X) == 0;
#else
    static_cast<void>(length);
    return address != 0 && (address & (alignof(uintptr_t) - 1)) == 0;
#endif
}

bool ValidateMusicMethod(uintptr_t address, const u8* expected, std::size_t expectedLength) {
    if (address == 0 || expected == nullptr || expectedLength == 0 || (address & 3) != 0) {
        return false;
    }
#if defined(__SWITCH__)
    // 地址是**别处算好的**（Lua 侧传进来的方法地址 / 调用点传来的入口）⇒ 形状是
    // `VerifyEntryBytes`（核对已算好的地址），而不是 `ResolveEntryAddress`（基址 + 偏移）。
    // 注入的判定比层里那份通用可读**更严**：只认模块映像的代码段（见 `IsEngineModuleCodeReadable`）。
    return VerifyEntryBytes(address, expected, expectedLength, &IsEngineModuleCodeReadable);
#else
    // 宿主构建没有 `svcQueryMemory`：宿主门禁会把**进程内的真函数**（例如 `&SetSeed`）当引擎方法
    // 传进来，其机器码与设备端常量必然不同 ⇒ 原实现把"问内核 + 逐字节比对"整段包在 `__SWITCH__`
    // 里、宿主一律放行。这里**逐条保持** —— 这不是"放宽判据"，是"设备判据在宿主上无法执行"；
    // 上面那三条参数/对齐判据在宿主上照旧生效（原来也是如此）。
    return true;
#endif
}

bool ResolveMusicForManager(uintptr_t manager, uintptr_t method, const u8* expected,
                            std::size_t expectedLength, uintptr_t* music) {
    if (manager == 0) {
        g_MusicResolveFailure.store(2, std::memory_order_release);
        return false;
    }
    if (method == 0 || expected == nullptr || expectedLength == 0) {
        // 方法地址/期望字节缺失 = "那一份绑定根本没发布"（与"偏移写错"分开报）。
        g_MusicResolveFailure.store(3, std::memory_order_release);
        return false;
    }
    // `manager + kManagerMusicOffset` 的"偏移算术 + 回绕 + 可读"三件事收进 L1 的 `FieldAddress`
    // （原来是自己加偏移、再调 `IsReadableMusicObject`）；注入的判定就是本文件那份"可读且不可执行"，
    // 宽度仍是 8 字节 —— 判据逐条未改。
    const uintptr_t candidate = FieldAddress(manager, kManagerMusicOffset,
                                             sizeof(uintptr_t), 0, &IsReadableMusicObject);
    if (candidate == 0 || !ValidateMusicMethod(method, expected, expectedLength)) {
        // 两者分开报：`candidate == 0` 是"Manager 给了但 Music 子对象读不到"（仍是环境问题），
        // 指纹不符才是"我们的偏移/期望字节不对"（最值得怀疑的那一类）。
        g_MusicResolveFailure.store(candidate == 0 ? 2 : 4, std::memory_order_release);
        return false;
    }
    g_MusicResolveFailure.store(0, std::memory_order_release);
    *music = candidate;
    return true;
}

//: `MusicManager:` 一族取 Manager 的**唯一**入口（批次 149 起两跳）。
//:
//: 第一跳：当前正在派发的那条回调带的 Manager（`hasManager == true` 的派发才写得进它）。
//: 第二跳（批次 149 新增）：本帧的 Manager —— `MC_POST_UPDATE` 的派发**不带** Manager，
//: 而模组正是在那条回调里调音乐（The Specialist for Good Items 的 `main.lua:482/488/493/500`，
//: 由 `OnGameUpdate → OnPogMoment → DoCostume` 走到）。PC 的绑定层读的是引擎自己的全局
//: Manager，所以这里也退到"本帧 `Manager::Update` 收到的 self" —— 两者是同一个单例。
//: 两跳都拿不到才算"没有 Manager"（原因码 2），报错时能一眼看出是环境还是偏移。
bool ResolveMusicForCall(uintptr_t method, const u8* expected, std::size_t expectedLength,
                         uintptr_t* music) {
    if (!g_InManagedCallbackDispatch.load(std::memory_order_acquire)) {
        g_MusicResolveFailure.store(1, std::memory_order_release);
        return false;
    }
    uintptr_t manager = g_CurrentCallbackManager.load(std::memory_order_acquire);
    if (manager == 0) {
        if (auto provider = g_FrameManagerProvider.load(std::memory_order_acquire)) {
            manager = provider();
        }
    }
    return ResolveMusicForManager(manager, method, expected, expectedLength, music);
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
    // 批次 061：与 `Level` 同理（同一个实现）。★ 2026-10-26（BUG-014）更正：此前这里只是
    // "**接受并忽略**"，注释举的例子（`Game().TimeCounter = Game().TimeCounter + addTime`）
    // 其实一直没生效 —— 真机 TimeMachine 的计时补偿就是这么丢的。现在 `TimeCounter` 已是
    // **真写**（`IgnoredObjectFieldWrite` 里的 `TryWriteGameTimeCounter`），其余没有偏移证据的
    // 字段仍只记忽略计数（`g_IsaacIgnoredFieldWriteCount` / `g_IsaacLastIgnoredFieldName`）。
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
    lua_pushcfunction(state,isaac::runtime::Api500GridNewIndex);lua_setfield(state,-2,"__newindex");
    lua_newtable(state);
    static_cast<void>(isaac::runtime::AttachGridEntityMethods(state));
    lua_setfield(state, -2, "__methods");
    lua_pop(state, 1);

    // 批次 078：`Room:GetDoor(slot)` 的返回值（`GridEntity_Door`）。PC 里门**同时是** `GridEntity`，
    // 所以它的 `__index` 是**函数**：先答门的字段，答不上再落到上面那张 `GridEntity` 方法表。
    // ★ 批次 284：门从这一批起**有了自己的 `__methods`**（`Open`/`Close`/`IsTargetRoomArcade`），
    //   回落顺序变成 **字段 → 门自己 → `GridEntity` 基类**（`GridEntityDoorIndex` 里那两段）。
    //   ★ 为什么也挪到 `__methods` 而不是继续在 `__index` 里 `if (strcmp(key, …))` 硬编码：
    //     那正是 `IsOpen` 现在的写法，而它的代价是"实现在、目录里没有" —— 完成定义台账与
    //     绑定行统计都覆盖不到它（项 079 的老账）。新方法一律走目录 + 处理器表。
    luaL_newmetatable(state, kGridEntityDoorMetatable);
    lua_pushcfunction(state, isaac::runtime::GridEntityDoorIndex);
    lua_setfield(state, -2, "__index");
    lua_pushcfunction(state,isaac::runtime::Api500GridNewIndex);lua_setfield(state,-2,"__newindex");
    lua_newtable(state);
    static_cast<void>(isaac::runtime::AttachGridEntityDoorMethods(state));
    lua_setfield(state, -2, "__methods");
    lua_pop(state, 1);

    luaL_newmetatable(state, kRoomDescriptorMetatable);
    lua_pushcfunction(state, isaac::runtime::RoomDescriptorIndex);
    lua_setfield(state, -2, "__index");
    lua_pushcfunction(state,isaac::runtime::RoomDescriptorNewIndex);lua_setfield(state,-2,"__newindex");
    lua_pop(state, 1);

    luaL_newmetatable(state, kRoomDescriptorListMetatable);
    lua_pushcfunction(state, isaac::runtime::RoomDescriptorListIndex);
    lua_setfield(state, -2, "__index");
    lua_newtable(state);
    static_cast<void>(isaac::runtime::AttachRoomDescriptorListMethods(state));
    lua_setfield(state, -2, "__methods");
    // ★★ 批次 349（2026-10-04）：`__len` —— 让 `#rooms` 成立。
    //   真机读数（`dist/gdb-report-20261004-183801.txt`）里 minimapi 报
    //   `minimapapi/main.lua:840: attempt to get length of a IsaacRuntime.RoomDescriptorList value`；
    //   那几行是 `for i = 0, #rooms - 1 do` / `CheckedRoomCount = #rooms`。
    //   PC 的 `RoomDescriptorList` 是列表 ⇒ 支持 `#` 才是"与 PC 一致"。
    lua_pushcfunction(state, isaac::runtime::RoomDescriptorListLen);
    lua_setfield(state, -2, "__len");
    lua_pop(state, 1);

    //: 批次 347（2026-10-04）：`RoomDescriptor.Data.Spawns` 的两个视图 ——
    //: `RoomConfigSpawn`（`Data.Spawns:Get(i)` 的返回值，有 `SumWeights`/`EntryCount` 两个属性
    //: 与 `PickEntry` 一个方法）与 `RoomConfigEntry`（`spawn:PickEntry(r)` 的返回值，只有四个属性）。
    //: ★ 两个 `__index` 都是函数（先答属性、再查 `__methods`）—— 与 `GridEntityDoor` 同一形态。
    luaL_newmetatable(state, kRoomConfigSpawnMetatable);
    lua_pushcfunction(state, isaac::runtime::RoomConfigSpawnIndex);
    lua_setfield(state, -2, "__index");
    lua_newtable(state);
    static_cast<void>(isaac::runtime::AttachRoomConfigSpawnMethods(state));
    lua_setfield(state, -2, "__methods");
    lua_pop(state, 1);

    luaL_newmetatable(state, kRoomConfigEntryMetatable);
    lua_pushcfunction(state, isaac::runtime::RoomConfigEntryIndex);
    lua_setfield(state, -2, "__index");
    lua_pop(state, 1);

    luaL_newmetatable(state, kItemPoolMetatable);
    lua_newtable(state);
    static_cast<void>(isaac::runtime::AttachItemPoolMethods(state));
    lua_setfield(state, -2, "__index");
    lua_pop(state, 1);

    // ★★ 批次 284（2026-10-04）：`Level` 的元表要补成 **PC 的形状** —— 三处消费者都要它：
    //   * `MinimapAPI/main.lua:230`：`getmetatable(Level).__class.MakeRedRoomDoor`
    //     ⇒ **`Level` 这个类全局必须存在**，且它的元表要有 `__class`；
    //   * `MinimapAPI/main.lua:626-637` 的 `InstanceOf(obj, class)`：
    //     `getmetatable(class).__class == getmetatable(obj)` ⇒ **`__class` 必须就是"实例用的那个元表"**；
    //   * `MinimapAPI/apioverride.lua:15-32`：拿 `__class` 当类元表，读 `__type` 当去重键、
    //     读 `__index` 当旧查找，然后 `rawset(__index, 包装)`。
    // ⇒ 做法：**方法直接落在元表自己身上**（不再放"__index 子表"），再把 `__class` 指回元表自己、补上 `__type`。
    // ★ 我们**之前根本没建 `Level` 这个全局** ⇒ 模组取到的是 `nil` ⇒ `getmetatable(nil)` 返回 nil
    //   ⇒ 再索引 `.__class` 就是真机那条 "attempt to index a nil value"。
    // ★★ **更正（批次 348，2026-10-04）**：上面 284 原文写着"`__index` 得在元表上、**且是个表**"
    //   —— 后半句是**读错了**。`apioverride` 第 25 行是 `return classDat.New[k] or oldIndex(self, k)`，
    //   它把 `__index` 取出来当**函数调用**。284 把 `__index` 设成"元表自己"那张表 ⇒ 真机报
    //   `apioverride.lua:25: attempt to call a table value (upvalue 'oldIndex')`
    //   （读数原文 = `dist/gdb-report-20261004-181018.txt`，Lua 错误环形历史 4 条全是它）；
    //   而且 minimapi 那一下 `rawset` 一装上，**Level 实例的每一次属性查找**都走那条会报错的包装
    //   ⇒ 同一条派发链上后面的模组跟着断（GoodTrip 的画地图在内）。
    //   ⇒ 348 起 `__index` 是**函数**（`LevelIndex`，上值 1 = 类元表）。语义与表 `__index` 完全等价
    //     （Lua 对表 `__index` 做的就是 `rawget`），只是变成**可调用** —— 与 `Game`/`RoomDescriptor`/
    //     `GridEntity` 族同一形态（它们本来就是函数，`Level` 是唯一一处写成表的）。
    luaL_newmetatable(state, kLevelMetatable);
    static_cast<void>(isaac::runtime::AttachLevelMethods(state));
    lua_pushvalue(state, -1);                                 // 上值 1 = 类元表自己
    lua_pushcclosure(state, isaac::runtime::LevelIndex, 1);
    lua_setfield(state, -2, "__index");   // ★ 348：函数（284 是"元表自己"那张表 ⇒ minimapi 一调就炸）
    lua_pushvalue(state, -1);
    lua_setfield(state, -2, "__class");   // = 自己（PC：`getmetatable(类).__class` 就是它）
    lua_pushliteral(state, "Level");
    lua_setfield(state, -2, "__type");    // 类名（`apioverride` 拿它当"这个类被改过没有"的键）
    // 批次 061：`Level` 的字段**可写**（PC 的 `Level` 就是引擎对象，模组直接赋值）。
    // 没有这一行时 `floor.level.EnterDoor = -1` 直接抛
    // "attempt to index a IsaacRuntime.Level value" ⇒ GoodTrip 的传送在第一句就断掉。
    lua_pushcfunction(state, isaac::runtime::IgnoredObjectFieldWrite);
    lua_setfield(state, -2, "__newindex");
    lua_pop(state, 1);

    luaL_newmetatable(state, kSeedsMetatable);
    lua_newtable(state);
    static_cast<void>(isaac::runtime::AttachSeedsMethods(state));
    lua_setfield(state, -2, "__methods");
    lua_pushcfunction(state,isaac::runtime::NativeClassMethodIndex);lua_setfield(state,-2,"__index");
    lua_pop(state, 1);
    isaac::runtime::PublishNativeClass(state,"Seeds",kSeedsMetatable);
    isaac::runtime::PublishApi200Statics(state,"Seeds");
    isaac::runtime::PublishApi700Statics(state,"Seeds");

    // 批次 207（2026-09-29）：`HUD`（`Game:GetHUD()` 的返回值：`IsVisible()` / `SetVisible(bool)`）。
    // 与 `Seeds` 同形 —— 句柄无字段、方法都是真方法（没有字段要挂 `__index` 闭包），
    // 所以 `__index` 直接就是方法表。方法体与绑定表在 `interfaces/lua/game_api.cpp`。
    luaL_newmetatable(state, kHudMetatable);
    lua_newtable(state);
    static_cast<void>(isaac::runtime::AttachHudMethods(state));
    lua_setfield(state, -2, "__methods");
    lua_pushcfunction(state,isaac::runtime::NativeClassMethodIndex);
    lua_setfield(state,-2,"__index");
    lua_pop(state, 1);
    isaac::runtime::PublishNativeClass(state,"HUD",kHudMetatable);

    lua_pushcfunction(state, CreateGameHandle);
    lua_setglobal(state, "Game");

    // ★★ 批次 284（2026-10-04）：**`Level` 这个"类全局"** —— PC 上它是模组拿"类的元表"的标准入口。
    // 形状（三处消费者都要，逐条见 `kLevelMetatable` 那段注释）：
    //     Level            ← 全局：一张**表**（不是函数；模组只用它来取元表）
    //     getmetatable(Level).__class   ← 就是**实例用的那个元表**（`IsaacRuntime.Level`）
    //     __class.__type / .__class.__index / .__class.<方法>   ← 全在元表上（见上）
    // ★ 为什么必须现在补：真机读数（2026-10-04 15:33）里 minimapi 的 Lua 错误原文就是
    //   `scripts/minimapapi/main.lua:230: attempt to index a nil value`，而那一行是
    //   `getmetatable(Level).__class.MakeRedRoomDoor` —— `Level` 是 nil、`getmetatable(nil)` 也是 nil。
    lua_newtable(state);                                   // 全局 `Level`（一张表）
    lua_newtable(state);                                   // 它自己的元表（"外层"）
    luaL_getmetatable(state, kLevelMetatable);             // 压入类元表（实例用的那个）
    lua_setfield(state, -2, "__class");                    // 外层.__class = 类元表
    lua_setmetatable(state, -2);                           // 把外层挂给 `Level`
    lua_setglobal(state, "Level");
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

#if defined(__GNUC__) && !defined(__clang__)
#pragma GCC pop_options
#endif

// --- 最小 `debug` 库（批次 3）--------------------------------------------------
//
// `debug.getinfo` 供 EID 定位脚本，`debug.traceback` 供模组构造错误堆栈。
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
// base/coroutine/table/string/math/utf8（见 `OpenSafeLibraries`），这里只提供只读查询。
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

// Match Lua 5.3's traceback arguments without opening the mutable debug library.
int DebugTraceback(lua_State* state) {
    lua_State* thread = lua_tothread(state,1);
    const int argument = thread != nullptr ? 1 : 0;
    if (thread == nullptr) thread = state;
    const char* message = lua_tostring(state,argument+1);
    if (message == nullptr && !lua_isnoneornil(state,argument+1)) {
        lua_pushvalue(state,argument+1);
    } else {
        const int level = static_cast<int>(luaL_optinteger(state,argument+2,
                                                          state == thread ? 1 : 0));
        luaL_traceback(state,thread,message,level);
    }
    return 1;
}

// 把最小 `debug` 表挂成全局。由 `PrepareRuntime` 在 Mod 脚本运行前调用一次。
void RegisterDebugLibrary(lua_State* state) {
    lua_newtable(state);
    lua_pushcfunction(state, DebugGetInfo);
    lua_setfield(state, -2, "getinfo");
    lua_pushcfunction(state, DebugTraceback);
    lua_setfield(state, -2, "traceback");
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
// os语义直接复用固定Lua5.3.3；原近似实现全文保留在本轮证据归档。
void RegisterOsLibrary(lua_State* state) {
    isaac::runtime::RegisterOsLibrary(state);
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
    // 批次 216：同一张方法表**再存一份到 registry**，给"每个 Mod 对象自己的元表"当 `__index`
    // （`RegisterMod` 用它建表）。存的是同一个引用 ⇒ 方法与旧路径完全一致，不存在两份定义。
    lua_pushvalue(state, -1);
    lua_setfield(state, LUA_REGISTRYINDEX, kModPrototypeField);
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
    isaac::runtime::notice::InstallRuntimeTypes(state);
    // 模组开关菜单的控制面（`RuntimeMods`，运行时自己的接口，不是 PC API）：
    // 菜单脚本要用它读清单、改开关、落盘。见 `interfaces/lua/mod_menu_api.hpp`。
    static_cast<void>(isaac::runtime::RegisterModMenuApi(state));
    RegisterNeutralInputApi(state);
    RegisterPcLuaEnumTables(state);
    // `Isaac` 门面与 `Options` 表必须早于 Mod 脚本存在：EID 加载的第一句就是
    // `Isaac.GetItemConfig()`，随后立刻读 `Options.HUDOffset`/`Options.Language`。
    // 两族都由 `interfaces/lua/isaac_api.cpp` 自己建立表并挂成全局（见该文件的注释：
    // 这一轮只保证"存在且被调用不报错"，引擎数据要等偏移定位后再接）。
    static_cast<void>(isaac::runtime::RegisterIsaacApi(state));
    isaac::runtime::RegisterApi700PlayerTypes(state);
    isaac::runtime::RegisterApi700Containers(state);
    isaac::runtime::PublishApi700Statics(state,"EntityLaser");
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
    isaac::runtime::RegisterCallbackBootstrap(state, InvokeObservedCallback, InvokeObservedNativeCallback);
    isaac::runtime::SetShaderValueProvider(FillShaderParameters);

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

int ConsolePrint(lua_State* state) {
    const int count=lua_gettop(state);
    if (!ConsoleCommandOutputActive()) {
        lua_pushvalue(state,lua_upvalueindex(1));
        lua_insert(state,1);
        lua_call(state,count,0);
        return 0;
    }
    // 沿用Lua5.3 base print的tostring/制表符/换行规则，不另分配整行缓冲。
    lua_getglobal(state,"tostring");
    for (int i=1;i<=count;++i) {
        lua_pushvalue(state,-1);lua_pushvalue(state,i);lua_call(state,1,1);
        std::size_t length{};const auto* text=lua_tolstring(state,-1,&length);
        if (!text) return luaL_error(state,"'tostring' must return a string to 'print'");
        if (i>1) {static_cast<void>(WriteActiveConsoleOutput("\t",1));std::fwrite("\t",1,1,stdout);}
        static_cast<void>(WriteActiveConsoleOutput(text,length));std::fwrite(text,1,length,stdout);
        lua_pop(state,1);
    }
    static_cast<void>(WriteActiveConsoleOutput("\n",1));std::fwrite("\n",1,1,stdout);
    return 0;
}
void OpenSafeLibraries(lua_State* state) {
    OpenLibrary(state, 1, "_G", luaopen_base);
    lua_getglobal(state,"print");lua_pushcclosure(state,ConsolePrint,1);lua_setglobal(state,"print");
    OpenLibrary(state, 2, LUA_COLIBNAME, luaopen_coroutine);
    OpenLibrary(state, 3, LUA_TABLIBNAME, luaopen_table);
    OpenLibrary(state, 4, LUA_STRLIBNAME, luaopen_string);
    OpenLibrary(state, 5, LUA_MATHLIBNAME, luaopen_math);
    OpenLibrary(state, 6, LUA_UTF8LIBNAME, luaopen_utf8);
}

int GetConsoleControls(lua_State* state) {
    const auto value=isaac::runtime::console::Storage().controls;
    lua_pushinteger(state,value.first);lua_pushinteger(state,value.second);lua_pushinteger(state,value.holdTenths);
    return 3;
}
int SetConsoleControls(lua_State* state) {
    if (lua_gettop(state)!=3 || !lua_isinteger(state,1) || !lua_isinteger(state,2) || !lua_isinteger(state,3))
        return luaL_error(state,"SetControls expects two button codes and hold tenths");
    const auto a=lua_tointeger(state,1),b=lua_tointeger(state,2),t=lua_tointeger(state,3);
    if (a<0 || a>=14 || b<0 || (b>=14 && b!=255) || t<2 || t>50)
        return luaL_error(state,"Invalid console controls (buttons 0..13 / second 255; hold 2..50)");
    lua_pushboolean(state,isaac::runtime::console::RequestConsoleControlsWrite({
        static_cast<std::uint32_t>(a),static_cast<std::uint32_t>(b),static_cast<std::uint32_t>(t)}));
    return 1;
}
#if !defined(EXL_DIAGNOSTIC_STAGE) || EXL_DIAGNOSTIC_STAGE == 13
bool InstallConsoleControlsMenu(lua_State* state) {
    lua_getglobal(state,"ModConfigMenu");
    if (!lua_istable(state,-1)) {lua_pop(state,1);return true;}
    lua_getfield(state,-1,"SwitchConsoleSettingsInstalled");
    const bool installed=lua_toboolean(state,-1);lua_pop(state,2);
    if (installed) return true;
    int status=luaL_loadbufferx(state,kConsoleControlsMenuScript,sizeof(kConsoleControlsMenuScript)-1,
                               "@runtime/console_controls_menu.lua","t");
    if (status==LUA_OK) status=lua_pcallk(state,0,0,0,0,nullptr);
    if (status==LUA_OK) return true;
    CaptureLuaErrorTop(state);lua_pop(state,1);return false;
}
#endif

int PrepareRuntime(lua_State* state) {
    OpenSafeLibraries(state);
#if !defined(EXL_DIAGNOSTIC_STAGE) || EXL_DIAGNOSTIC_STAGE == 13
    // 菜单先建空VM、随后逐模组装载时也需要require/include；实际读文件仍由
    // SetStage13Context发布根和绑定，不能把安装这些全局依赖于首建时已存在模组。
    g_PreparationStep.store(7, std::memory_order_relaxed);
    RegisterStage13Require(state);
#endif
    RegisterModApi(state);
    lua_newtable(state);
    lua_pushcfunction(state,GetConsoleControls);lua_setfield(state,-2,"GetControls");
    lua_pushcfunction(state,SetConsoleControls);lua_setfield(state,-2,"SetControls");
    lua_setglobal(state,"SwitchConsole");
    return 0;
}

int RestoreAllPressurePinsProtected(lua_State* state){
    isaac::runtime::RestorePressurePlateAnimationPins(state,nullptr);return 0;
}
LuaInitResult ResetAfterFailure(lua_State* state, LuaInitResult result) {
    if(isaac::runtime::HasPressurePlateAnimationPins()){
        // 原错误已先留证；关闭前的清理不能让native字段悬挂到已释放的Lua串。
        lua_settop(state,0);
        lua_pushcfunction(state,RestoreAllPressurePinsProtected);
        if(lua_pcall(state,0,0,0)!=LUA_OK){
            CaptureLuaErrorTop(state);g_LuaState=state;
            g_Ready.store(false,std::memory_order_release);return result;
        }
    }
    isaac::runtime::ResetEntityLifetimeState();
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

// 批次 099（2026-09-24）：Lua「无保护抛错」的留证兜底（见 `fatal_forensics.hpp` 的文件头）。
//
// 为什么需要它：Lua 的错误在整条链上找不到 `errorJmp` 时，`luaD_throw` 会走到末尾的 `abort()`
// （离线反汇编见 `docs/问题记录-画面卡死-20260924.md` §10），而我们**从没注册过 `lua_atpanic`**
// ⇒ 那条路一个字节的痕迹都不留（表现就是画面停、音乐继续、没有崩溃报告）。
// 这里注册的处理器**不返回**：先 `svcBreak` 把寄存器交给崩溃报告（`x2 = 2` = Lua 这条路）。
//
// 为什么在这个文件里定义、而不是放进那个头：它需要 `lua_State` 类型；放头里会把 lua 头
// 引入每一个包含它的单元（`runtime_entry.cpp` 等），没必要。
int LuaPanicForensics(lua_State* state) {
    isaac::runtime::forensics::Break(
        isaac::runtime::forensics::kKindLuaPanic,
        static_cast<std::uint64_t>(isaac::runtime::engine_memory::AddressOf(state)));
    return 0;  // 不可达：上面的 Break 是 [[noreturn]]
}

// 建立流程的唯一实现：建 Lua 状态并运行 PrepareRuntime；不装额外菜单模组。
// 成功时把 `g_LuaState`/`g_Ready` 设好（模组随后往同一个状态里追加）。
LuaInitResult EnsureRuntimeWithMenuInternal() {
    if (!isaac::runtime::notice::integrity::RuntimeAllowed()) return LuaInitResult::RuntimePreparationFailed;
    if (g_ShuttingDownForModReload) return LuaInitResult::ScriptRunFailed;
    if(g_LuaState && !g_Ready.load(std::memory_order_acquire) && isaac::runtime::HasPressurePlateAnimationPins())
        return LuaInitResult::ScriptRunFailed; // 上次关闭清理失败，保留强持状态，不覆盖丢失它。
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
    //
    // ★★★ 批次 262（A2 性能）：**只在诊断包里换**。理由：EID 每帧分配约 1.4 MB（每次约 93 字节）
    // ⇒ 每帧约 1.5 万次分配 × 2（分配+释放），每次都要多走一遍计数分支；正式包用 Lua 自带的
    // 默认分配器（零记账）。★ 分配器本体与四个计数器**都还留着** ⇒ 出 `DIAGNOSTIC_PROBES=1`
    // 的诊断包时照旧能读"Lua 分配账"（读数工具按符号读，值在诊断包里照常增长）。
#if defined(ISAAC_RUNTIME_PERF_TIMING) && EXL_DIAGNOSTIC_PROBES
    lua_setallocf(state, IsaacRuntime_CountingAlloc, nullptr);
#endif
    // 批次 099（2026-09-24）：把「Lua 在**没有 pcall 保护**的上下文里抛错」从**静默卡死**
    // 变成**可读的崩溃报告**（处理器本体见上面的 `LuaPanicForensics`）。这一句只装兜底，
    // **不改任何 Lua 语义**；必须建好状态之后才能注册（在那之前没有 `lua_State`）。
    lua_atpanic(state, &LuaPanicForensics);
    // 批次 089：挂上采样剖析器（计数钩子，每 `kRuntimePerfProfileInstructionStep` 条指令一次）。
    // **只在实际设备构建里挂**：宿主门禁跑上千次 Lua 脚本，挂上去只会让套件变慢；
    // 剖析器自己的门禁会**显式**调用 `IsaacRuntime_ProfileHook` 来验行为。
    //
    // ★★★ 批次 262（A1 性能）：**再加一道"只在诊断包"的门**（`EXL_DIAGNOSTIC_PROBES`）。
    // 这一条是本次性能修复里最值钱的：装了计数钩子之后，Lua 5.3 的 VM 在
    // **每条指令**上都要走一次 `vmfetch` 里那句 `if (L->hookmask & (行钩子 | 计数钩子))
    // Protect(luaG_traceexec(L));`（`third_party/lua-5.3.3/src/lvm.c`）——那是一句
    // **跨 TU 的真实函数调用**。
    // ★ 注意：这里**故意不写那两个掩码宏的名字** —— `runtime/tests/test_lua_profiler.py`
    //   是按**整文件子串**判定的（`assertNotIn`），把宏名写进注释也会让它变红。
    // 本机实测（同一份负载、同一版本 Lua 5.3.3、钩子步长同为 4000）：
    //   重分配型负载（`string.format`/`string.find`/表读写，仿 EID 每帧的活） **+13%**
    //   紧凑数值循环                                                    **+58%**
    // ⇒ 正式包不该为"采样剖析"常年付这笔税。钩子、采样桶、读数工具**全部保留**，
    //   出 `DIAGNOSTIC_PROBES=1` 的诊断包时照旧可用。
    // ★ 顺带：这一条也是"以后要换 LuaJIT"的前置条件 —— LuaJIT 在有调试钩子生效期间会停用 JIT。
#if defined(ISAAC_RUNTIME_PERF_TIMING) && EXL_DIAGNOSTIC_PROBES
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
    g_LuaState = state;
    g_Ready.store(true, std::memory_order_release);
    return LuaInitResult::Success;
}

LuaInitResult InitializeScript(const char* script, std::size_t length, const char* chunkName,
                               bool fileSource = false) {
    if (g_ShuttingDownForModReload) return LuaInitResult::ScriptRunFailed;
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
    if ((fileSource ? LoadFileChunk(state, script, length, chunkName)
                    : luaL_loadbufferx(state, script, length, chunkName, "t")) != LUA_OK) {
        CaptureLuaErrorTop(state);
        lua_pop(state, 1);
        return ResetAfterFailure(state, LuaInitResult::ScriptLoadFailed);
    }
    if (lua_pcallk(state, 0, 0, 0, 0, nullptr) != LUA_OK) {
        CaptureLuaErrorTop(state);
        lua_pop(state, 1);
        return ResetAfterFailure(state, LuaInitResult::ScriptRunFailed);
    }
    if (IsStage13CallbackMode() && isaac::runtime::CountLuaCallbacks(state,1) == 0) {
        return ResetAfterFailure(state, LuaInitResult::MissingPostUpdateCallback);
    }
    // `g_LuaState`/`g_Ready` 由 `EnsureRuntimeWithMenuInternal()` 设好（模组只是往同一个状态里追加）。
    return LuaInitResult::Success;
}

} // namespace


// 对外入口（`lua_runtime.hpp` 声明的那一个）：匿名命名空间里的实现不导出符号，所以这层是必须的。
// 幂等：已经有状态就直接成功。
LuaInitResult EnsureRuntimeWithMenu() noexcept {
    if (!isaac::runtime::notice::integrity::RuntimeAllowed()) return LuaInitResult::RuntimePreparationFailed;
    if (g_LuaState != nullptr && g_Ready.load(std::memory_order_acquire)) {
        return LuaInitResult::Success;
    }
    return EnsureRuntimeWithMenuInternal();
}
bool ConsoleConfigMenuVisible() noexcept {
    if (!isaac::runtime::notice::integrity::RuntimeAllowed()) return false;
    if (!g_LuaState || !g_Ready.load(std::memory_order_acquire)) return false;
    lua_getglobal(g_LuaState,"ModConfigMenu");
    if (!lua_istable(g_LuaState,-1)) {lua_pop(g_LuaState,1);return false;}
    lua_getfield(g_LuaState,-1,"IsVisible");
    const bool visible=lua_toboolean(g_LuaState,-1);lua_pop(g_LuaState,2);
    return visible;
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
    // ★ 这两处**刻意不迁**到引擎内存访问层：`sbrk`/`__fake_heap` 是我们**自己的假堆**，
    // 不是引擎内存 —— 用 `engine_memory::AddressOf` 去转会把那个名字的含义搞混
    // （那个命名空间治的是"引擎内存"，见 `engine_field_access.hpp` 头部）。
    // 台账 `tools/raw_engine_access_baseline.json` 的口径本来就是**代理指标**，
    // 它明说了"同一个数字里混着两类完全不同的东西"，这一处属于"不是引擎访问"那一类。
    const auto top = isaac::runtime::engine_memory::AddressOf(sbrk(0));
    const auto base = isaac::runtime::engine_memory::AddressOf(__fake_heap);
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

std::uintptr_t MusicUpdateVolumeThunk() noexcept {
    return g_MusicUpdateVolume.load(std::memory_order_acquire);
}

std::uintptr_t MusicPlayThunk() noexcept {
    return g_MusicPlay.load(std::memory_order_acquire);
}

std::uintptr_t RngSetSeedThunk() noexcept {
    return g_RngSetSeed.load(std::memory_order_acquire);
}

// ============================================================================
// 批次 392（2026-10-07）：我们这侧的输入读取 —— 直读壳（绕开 `MC_INPUT_ACTION` 的覆盖）
// ============================================================================
//
// 为什么（真机回归 + 反汇编定案，完整证据链见 `lua_runtime.hpp` 的声明处）：
//   * Lua 的 `Input.IsActionPressed` 绑的 `0x3F9B6C`（符号 = `IsaacRepentance::Manager::IsActionPressed`）
//     **尾跳**进 `KAGE::Input::ManagerBase::IsActionPressed`（`0x4F9920`）—— 正是批次 390 给
//     `MC_INPUT_ACTION` 挂中继的地方；而**引擎本体**（`Entity_Player::get_movement_input` /
//     `control_shooting` / 各菜单类自己的输入处理）也走同一个符号 ⇒ **两种读取在入口上同形**。
//   * PC 契约（`ModCallbacks.md:355`）明写覆盖**不影响** `Input` 类的读取 ⇒ 不绕的后果：
//     MCM 菜单可见时对一切动作 `return false`（本意是冻住角色），把它**自己的**光标读输入也
//     答成 false ⇒ 摇杆推不动光标。
//
// 形状：下面两个壳转发到**引擎胶水**（`g_InputIsAction*` 里那一份 —— 照旧由 `SetInputBindings`
// 发布、照旧被 ABI 工具追踪），只在中间套一次 `RawEngineInputQueryScope`；中继见标记就
// 跳过派发、直接调原函数。
//   ★ 壳里用胶水而**不是** `Original<>`：诊断档把中继 `SKIP_HOOK_INPUTACTION*` 跳掉时，胶水本来就
//     没被挂钩、照样答真值；用 `Original<>` 会在那些档里拿到空指针、把所有输入答成 false，
//     把**原生模组页的导航**一起弄死（那是我们自己的 UI）。
//   ★ 只给 `IsActionPressed` 与 `GetActionValue` 两条做壳：`IsActionTriggered` 那条**没有任何
//     消费者**（批次 107 起 `Input.IsActionTriggered` = 问"按住" + 我们自己按帧算边沿），
//     它的取值助手照旧原样返回胶水地址。
namespace {
//: 嵌套计数（> 0 = 正在直读）。游戏线程单线程访问；用原子只是与相邻状态同形。
std::atomic<std::uint32_t> g_RawEngineInputQueryDepth{0};

bool RawInputActionPressedShell(void* manager, std::uint32_t action, std::uint32_t controller,
                                void* out) {
    using QueryFn = bool (*)(void*, std::uint32_t, std::uint32_t, void*);
    const auto query =
        isaac::runtime::engine_call::AsFunction<QueryFn>(g_InputIsActionPressed.load(std::memory_order_acquire));
    if (query == nullptr) {
        return false;  // 与"绑定不可用"同口径：绝不编造一个"没按下"
    }
    const RawEngineInputQueryScope scope;
    return query(manager, action, controller, out);
}

float RawInputGetActionValueShell(void* manager, std::uint32_t action, std::uint32_t controller,
                                  void* out) {
    using QueryFn = float (*)(void*, std::uint32_t, std::uint32_t, void*);
    const auto query =
        isaac::runtime::engine_call::AsFunction<QueryFn>(g_InputGetActionValue.load(std::memory_order_acquire));
    if (query == nullptr) {
        return 0.0F;
    }
    const RawEngineInputQueryScope scope;
    return query(manager, action, controller, out);
}
}  // namespace

bool IsRawEngineInputQuery() noexcept {
    return g_RawEngineInputQueryDepth.load(std::memory_order_relaxed) != 0;
}

RawEngineInputQueryScope::RawEngineInputQueryScope() noexcept {
    g_RawEngineInputQueryDepth.fetch_add(1, std::memory_order_relaxed);
}

RawEngineInputQueryScope::~RawEngineInputQueryScope() noexcept {
    g_RawEngineInputQueryDepth.fetch_sub(1, std::memory_order_relaxed);
}

// ★ 批次 392：返回**直读壳**（不是引擎胶水地址）—— 所有消费者（Lua 的 `Input.*`、每帧全动作
//   采样器、原生模组页与探针）因此自动走直读。绑定没发布（守卫不符）时仍然给 0，
//   保持"handler 报绑定不可用"的原语义，**不**编一个 false 出来。
// ⚠ 写法约束：**必须写成一条 `return` 的三元表达式**，不能拆成 `if (...) { return 0; } …`。
//   `tools/engine_offset_abi_report.py` 的 `THUNK_DEF_RE` 按字面要求
//   "`Thunk() noexcept { return … g_<槽>.load`" 这个形状来认"全局槽 → 取值助手"那一跳；
//   写成 `if` 会让三条 `kManager*Offset` 的声明判决掉回「没比过」
//   （门禁 `test_engine_offset_signatures` 当场红 —— 2026-10-07 本批就踩了一次）。
std::uintptr_t InputIsActionPressedThunk() noexcept {
    return g_InputIsActionPressed.load(std::memory_order_acquire) == 0
               ? 0
               : isaac::runtime::engine_call::AddressOfFunction(&RawInputActionPressedShell);
}

std::uintptr_t InputIsActionPressedBinding() noexcept {
    return g_InputIsActionPressed.load(std::memory_order_acquire);
}

// 批次 417（2026-10-08）：Lua 状态自己的内存占用（字节）。
// 为什么要它：415 的真机读数说模块堆"已用 122.8 MB / 空闲 5.2 MB"，而"这 122 MB 是谁吃的"
// 当时只能猜。这一格把 **Lua 侧**（模组的表与字符串 —— EID 的语言包光源码就有 8 MB）与
// **其它**（`malloc` 出来的：Font 块、贴图转码缓冲、挂载表、名字层…）分开：
//     其它 = `heapUsedBytes`（状态面 [59]）− 本函数返回值。
// 口径：`LUA_GCCOUNT` 给 KB、`LUA_GCCOUNTB` 给余数字节；状态没建/已关时返回 0。
// ★ 只读：不触发 GC、不改任何状态（这两个 `what` 纯粹是查询）。
// ★★ 位置必须**在这个文件里第一个 `namespace {` 之前**（本文件的匿名命名空间是
//    `LuaRuntime::{anon}`，定义落在里面就变成**内部链接** ⇒ 与头里那份外部链接声明对不上
//    ⇒ 调用点报 "no matching function"（2026-10-08 本批实撞）。放在
//    `InputIsActionPressedThunk()`（同文件里**已被跨 TU 调用**过的外部函数）旁边最稳。
// ★ Lua 5.3 的 `lua_gc` 是**三个参数**（`(L, what, data)`）—— 第三格对这两条查询无用，传 0。
std::uint32_t LuaStateMemoryBytes() noexcept {
    lua_State* state = g_LuaState;
    if (state == nullptr) {
        return 0;
    }
    const int kilobytes = lua_gc(state, LUA_GCCOUNT, 0);
    const int remainder = lua_gc(state, LUA_GCCOUNTB, 0);
    if (kilobytes < 0 || remainder < 0) {
        return 0;
    }
    const std::uint64_t bytes = static_cast<std::uint64_t>(kilobytes) * 1024ULL +
                                static_cast<std::uint64_t>(remainder);
    return bytes > 0xFFFFFFFFULL ? 0xFFFFFFFFU : static_cast<std::uint32_t>(bytes);
}

// ─────────────────────────────────────────────────────────────────────────────
// ★★★ 批次 425（2026-10-10）：**把"Lua 的 GC 看不见的那笔内存"补给 GC 看**。
//
// 起因（真机实测，全部有读数）：`whatsmydps` 在 `MC_POST_RENDER` 里每帧
//   `local font = Font()` + `font:Load(...)`，用完即弃 ⇒
//   **`MC_POST_RENDER` 派发次数 : Font 分配次数 = 1 : 1**，
//   Font 存活块数一路锯到 **507 块**（× 128 KiB = **63 MB**），**每约 250 帧**才被收一次。
//
// ★★ 为什么 GC 会放着 63 MB 垃圾不collect —— **415 批那句前提是错的**：
//   那 128 KiB 的块走的是 `lua_getallocf` 拿到的**裸 `frealloc`**
//   （`lapi.c:1169` 就是 `return G(L)->frealloc;`），
//   而 Lua **只在 `luaM_realloc_` 里更新 `g->GCdebt`**（`lmem.c:97`）。
//   ⇒ 直接调 `frealloc` **绕过了这笔账** ⇒ 这块内存不进 Lua 的用量统计
//   ⇒ GC 的触发判断（`GCdebt` 对 `GCthreshold`）**永远看不到它**。
//   415 的原话"它计入 Lua 的 GC 账 ⇒ GC 按需回收" **实测不成立** ⇒ 本批订正。
//
// 修法：这笔内存**我们自己看得见**（`g_FontStorageLive`）⇒ 由我们把它**补报**给 GC。
//   * 软上限 **64 块**（= 8 MiB）：超过就催；
//   * **最小间隔 30 帧**：给全量 GC 的触发率设上界（避免"分配越快、GC 越勤"的正反馈）；
//   * 用 **`LUA_GCCOLLECT`（= 2，全量）**而不是 `LUA_GCSTEP` ——
//     这批垃圾是 **userdata 的终结器**（我们把块交给 `__gc` 归还），
//     而 `LUA_GCSTEP` 的"工作单位"很小、可能要很多拍才走完一轮；全量一次就干净。
//     ★ 常量名与取值从 vendored `lua.h:302-309` 核过（**两个 C 的 `GCCOLLECT`**）——
//       写错一个字母就是一个**静默的错操作**（本项目在"手抄名字"上栽过）。
//
// ★ 调用点在 `mod_menu_native.cpp` 的 `ModMenuNativeUpdate()`（每帧路径，
//   **不在 Lua 执行中**）：GC 会跑终结器，在 Lua 里乱插一脚是不安全的。
// ★★ 块数由**调用方传进来**（`FontStorageLiveBlocks()`）：**不要**在本文件里写
//   `namespace isaac::runtime { extern … }` —— 本文件在 `namespace LuaRuntime` 里，
//   那样会**造出 `LuaRuntime::isaac::runtime`** 并**抢走本 TU 后面所有 `isaac::runtime::X`
//   的查找**（2026-10-10 实撞：一次性 15 个 `does not name a type`）。
//
// ─────────────────────────────────────────────────────────────────────────────
// ★★★ 2026-10-10 当晚（批次 426）：**从"全量 GC"改成"按时间预算切片的增量步进"**。
//
// **为什么改**：425 用的是 `lua_gc(L, LUA_GCCOLLECT, 0)`（**全量**），一秒左右跑一次。
// 用户当晚就报「帧率十分不稳定，**掉一下回 60，然后再掉一下回 60**，一直这样」——
// **全量 GC 是 stop-the-world**，一次停顿就是一两帧。**这是我上一批造的**。
// ★ 教训：425 的注释里我写"`LUA_GCSTEP` 的工作单位很小、可能要很多拍才走完一轮；
//   全量一次就干净" —— **只权衡了"干净"，没权衡"停顿"**。改性能相关的选择，
//   **必须把"单次最长耗时"当成一等判据**，不能只看"做完了没有"。
//
// **读源码之后才看清的 `LUA_GCSTEP` 语义**（`lapi.c:1066-1078`）：
//   * `data == 0` ⇒ `luaE_setdebt(g, -GCSTEPSIZE); luaC_step(L);` ⇒ **只做一个"单步"，有界**；
//   * `data != 0` ⇒ `debt = data*1024 + g->GCdebt; luaC_setdebt(...); luaC_checkGC(L);`
//     ⇒ 而 `luaC_step` 是 `do { work = singlestep(); debt -= work; } while (debt > -GCSTEPSIZE)`
//     ⇒ **按"债"一路还完 ≈ 全量** ⇒ **`data != 0` 一样会停顿时长不可控**。
//   ⇒ **能安全切片的是 `LUA_GCSTEP, 0`（单步）**。
//
// **现在的做法**：一拍之内**反复走单步**，直到 **① 一轮走完（返回 1）**，
//   或 **② 花掉的时间预算（1 ms）**，或 ③ 撞到步数硬上限。
//   ⇒ 单次停顿**有界（~1 ms，肉眼不可见）**，而同样的总工作量摊到许多拍上。
//   * `kFontGcMinFrameGap = 2` ⇒ 最多 ~30 拍/秒 × 1 ms ≈ **3% CPU**（与 425 的总量同量级，
//     只是不再"一秒攒成一次大停顿"）；
//   * ★ **自停仍在**，但判据改到**"一轮结束时"**评（增量 GC 不可能一拍就收掉东西）：
//     记下轮开始时的存活数，轮结束时若**没降**（<16 块）⇒ 判"这些块是**真活着**的" ⇒ 停手。
namespace {
constexpr std::uint32_t kFontBlockSoftLimit = 48;     // 48 × 128 KiB = 6 MiB
constexpr std::uint32_t kFontGcMinFrameGap = 2;       // 至多每 2 帧起一拍
constexpr std::uint64_t kFontGcBudgetTicks = 19200;   // 1 ms（19.2 tick / µs）
constexpr std::uint32_t kFontGcMaxSteps = 4096;       // 硬上限
constexpr std::uint32_t kFontGcMinDrop = 16;          // 一轮至少要收掉这么多块才算"有效"
std::uint32_t g_fontLastGcFrame = 0;                  // 只被每帧路径写（单线程）
bool g_fontGcProductive = true;                       // 上一轮是否真的收掉了垃圾
std::uint32_t g_fontLastUnproductiveAllocation = 0;
std::uint32_t g_fontDestructionsAtCycleStart = 0;
}  // namespace

//: ★ 外部链接（**写在 `namespace {` 之外**）：读数工具按符号名读
//: （技能 `isaac-switch-probe-batch` §11 —— 本项目已因此栽过 5 次）。
std::atomic<std::uint32_t> g_FontGcNudges{0};      // 起了多少"拍"（有实际步进的）
std::atomic<std::uint32_t> g_FontGcSteps{0};       // 累计走了多少个单步
std::atomic<std::uint32_t> g_FontGcMicros{0};      // 累计耗时（µs）
std::atomic<std::uint32_t> g_FontGcMicrosMax{0};   // ★ **单拍最长**（µs）—— 停顿的量具

std::uint32_t NudgeLuaGcIfFontBlocksHigh(std::uint32_t frames,
                                         std::uint32_t liveFontBlocks) noexcept {
    lua_State* state = g_LuaState;
    if (state == nullptr) {
        return 0;
    }
    if (liveFontBlocks <= kFontBlockSoftLimit) {
        // 回到阈值以下 ⇒ 重新允许催收（上一轮的"自停"解除）。
        g_fontGcProductive = true;
        return 0;
    }
    // ★★ "自停"判据：上一**轮**收了**没收到东西** ⇒ 这些块是**真活着**的（不是垃圾）
    //   ⇒ **别再白催**。没有这一条，一个"合法持有 100 个 Font"的模组会让我们永远在做 GC。
    if (!g_fontGcProductive) {
        if (isaac::runtime::FontStorageAllocationCount() == g_fontLastUnproductiveAllocation) return 0;
        g_fontGcProductive = true;
    }
    if (frames - g_fontLastGcFrame < kFontGcMinFrameGap) {
        return 0;
    }
    g_fontLastGcFrame = frames;

    const std::uint64_t start = isaac::runtime::RuntimePerfTick();
    std::uint32_t steps = 0;
    bool cycleDone = false;
    for (std::uint32_t i = 0; i < kFontGcMaxSteps; ++i) {
        ++steps;
        if (lua_gc(state, LUA_GCSTEP, 0) != 0) {   // 返回 1 = 这一轮 GC 走完了
            cycleDone = true;
            break;
        }
        // ★★ 批次 427：**每步都查预算**（原来是每 16 步查一次）。
        //   426 真机实测：单拍最长 **2258 µs** —— 那正是"16 × 141 µs"，
        //   即**超预算的部分全是那个检查粒度造成的**。
        //   读 `cntpct_el0` 只有纳秒级开销，压在每一步上完全付得起；
        //   换来的是**单拍最长 ≈ 一个单步**（≈141 µs）⇒ 停顿彻底落到肉眼之下。
        if (isaac::runtime::RuntimePerfTick() - start >= kFontGcBudgetTicks) {
            break;
        }
    }
    const std::uint64_t ticks = isaac::runtime::RuntimePerfTick() - start;
    // 19.2 tick / µs ⇒ µs = ticks × 10 / 192。
    const std::uint32_t micros = static_cast<std::uint32_t>(ticks * 10ULL / 192ULL);
    g_FontGcMicros.fetch_add(micros, std::memory_order_relaxed);
    std::uint32_t prevMax = g_FontGcMicrosMax.load(std::memory_order_relaxed);
    while (micros > prevMax &&
           !g_FontGcMicrosMax.compare_exchange_weak(prevMax, micros,
                                                    std::memory_order_relaxed)) {
    }
    g_FontGcSteps.fetch_add(steps, std::memory_order_relaxed);

    g_FontGcNudges.fetch_add(1, std::memory_order_relaxed);
    if (cycleDone) {
        const auto destroyed = isaac::runtime::FontStorageDestructionCount();
        if (destroyed - g_fontDestructionsAtCycleStart < kFontGcMinDrop) {
            g_fontGcProductive = false;
            g_fontLastUnproductiveAllocation = isaac::runtime::FontStorageAllocationCount();
        }
        g_fontDestructionsAtCycleStart = destroyed;
    }
    return 1;
}

// ★ 批次 392：这一条**没有消费者**（见上面那段的原因），所以不给它套壳 —— 保持原样。
std::uintptr_t InputIsActionTriggeredThunk() noexcept {
    return g_InputIsActionTriggered.load(std::memory_order_acquire);
}

// ★ 批次 392：同 `InputIsActionPressedThunk`（返回直读壳；写法约束同上）。
std::uintptr_t InputGetActionValueThunk() noexcept {
    return g_InputGetActionValue.load(std::memory_order_acquire) == 0
               ? 0
               : isaac::runtime::engine_call::AddressOfFunction(&RawInputGetActionValueShell);
}

// 批次 195：按键号那两条查询的取址助手（0 = 没发布 ⇒ handler 报"绑定不可用"）。
std::uintptr_t InputIsButtonPressedThunk() noexcept {
    return g_InputIsButtonPressed.load(std::memory_order_acquire);
}

std::uintptr_t InputGetButtonValueThunk() noexcept {
    return g_InputGetButtonValue.load(std::memory_order_acquire);
}

std::uintptr_t RngNextThunk() noexcept {
    return g_RngNext.load(std::memory_order_acquire);
}

// 批次 195：`RNG:RandomInt(Max)` / `RNG:RandomFloat()` 的取址助手。
std::uintptr_t RngRandomUintThunk() noexcept {
    return g_RngRandomUint.load(std::memory_order_acquire);
}

std::uintptr_t RngRandomThunk() noexcept {
    return g_RngRandom.load(std::memory_order_acquire);
}

// 取址助手：把原子槽里存的地址交回**带签名的函数指针**。
//
// 2026-09-24（批次 114）：转换从 `reinterpret_cast<XxxFn>(…)` 改成引擎调用层的
// `AsFunction<XxxFn>(…)` —— 全仓"整数地址 → 函数指针"只允许在层里那一处出现（可检索、可审计），
// 这也正是 `docs/架构诊断-框架为什么失效-20260924.md` 里"裸碰引擎"要治的那一类。
// 这些地址是**钩子中继在安装时核对过**的（`ResolveEntryAddress` 那条路），所以只做转换、不再核对
// （层的注释写明：`AsFunction` 不做可读/映像归属核对，交进来的必须是已经核对过的地址）。
FontCtorFn FontCtorThunk() noexcept {
    return AsFunction<FontCtorFn>(g_FontCtor.load(std::memory_order_acquire));
}

FontDestructorFn FontDestructorThunk() noexcept {
    return AsFunction<FontDestructorFn>(g_FontDestructor.load(std::memory_order_acquire));
}

FontLoadFn FontLoadThunk() noexcept {
    return AsFunction<FontLoadFn>(g_FontLoad.load(std::memory_order_acquire));
}

FontUnloadFn FontUnloadThunk() noexcept {
    return AsFunction<FontUnloadFn>(g_FontUnload.load(std::memory_order_acquire));
}

FontIsLoadedFn FontIsLoadedThunk() noexcept {
    return AsFunction<FontIsLoadedFn>(g_FontIsLoaded.load(std::memory_order_acquire));
}

FontGetStringWidthFn FontGetStringWidthThunk() noexcept {
    return AsFunction<FontGetStringWidthFn>(
        g_FontGetStringWidth.load(std::memory_order_acquire));
}

FontGetStringWidthUTF8Fn FontGetStringWidthUTF8Thunk() noexcept {
    return AsFunction<FontGetStringWidthUTF8Fn>(
        g_FontGetStringWidthUTF8.load(std::memory_order_acquire));
}

FontGetLineHeightFn FontGetLineHeightThunk() noexcept {
    return AsFunction<FontGetLineHeightFn>(
        g_FontGetLineHeight.load(std::memory_order_acquire));
}

FontGetBaselineHeightFn FontGetBaselineHeightThunk() noexcept {
    return AsFunction<FontGetBaselineHeightFn>(
        g_FontGetBaselineHeight.load(std::memory_order_acquire));
}

FontGetCharacterWidthFn FontGetCharacterWidthThunk() noexcept {
    return AsFunction<FontGetCharacterWidthFn>(
        g_FontGetCharacterWidth.load(std::memory_order_acquire));
}

FontSetMissingCharacterFn FontSetMissingCharacterThunk() noexcept {
    return AsFunction<FontSetMissingCharacterFn>(
        g_FontSetMissingCharacter.load(std::memory_order_acquire));
}

FontDrawStringScaledFn FontDrawStringScaledThunk() noexcept {
    return AsFunction<FontDrawStringScaledFn>(
        g_FontDrawStringScaled.load(std::memory_order_acquire));
}

FontDrawStringUTF8Fn FontDrawStringUTF8Thunk() noexcept {
    return AsFunction<FontDrawStringUTF8Fn>(
        g_FontDrawStringUTF8.load(std::memory_order_acquire));
}

FontDrawStringScaledUTF8Fn FontDrawStringScaledUTF8Thunk() noexcept {
    return AsFunction<FontDrawStringScaledUTF8Fn>(
        g_FontDrawStringScaledUTF8.load(std::memory_order_acquire));
}

FontDrawStringFn FontDrawStringThunk() noexcept {
    return AsFunction<FontDrawStringFn>(g_FontDrawString.load(std::memory_order_acquire));
}

SpriteCtorFn SpriteCtorThunk() noexcept {
    return AsFunction<SpriteCtorFn>(g_SpriteCtor.load(std::memory_order_acquire));
}
SpriteDestructorFn SpriteDestructorThunk() noexcept {
    return AsFunction<SpriteDestructorFn>(g_SpriteDestructor.load(std::memory_order_acquire));
}
SpritePlayFn SpritePlayThunk() noexcept {
    return AsFunction<SpritePlayFn>(g_SpritePlay.load(std::memory_order_acquire));
}
SpriteSetAnimationFn SpriteSetAnimationThunk() noexcept {
    return AsFunction<SpriteSetAnimationFn>(
        g_SpriteSetAnimation.load(std::memory_order_acquire));
}
SpriteSetFrameNamedFn SpriteSetFrameNamedThunk() noexcept {
    return AsFunction<SpriteSetFrameNamedFn>(
        g_SpriteSetFrameNamed.load(std::memory_order_acquire));
}
SpriteSetFrameFn SpriteSetFrameThunk() noexcept {
    return AsFunction<SpriteSetFrameFn>(g_SpriteSetFrame.load(std::memory_order_acquire));
}
SpriteGetFrameFn SpriteGetFrameThunk() noexcept {
    return AsFunction<SpriteGetFrameFn>(g_SpriteGetFrame.load(std::memory_order_acquire));
}
SpriteSetLayerFrameFn SpriteSetLayerFrameThunk() noexcept {
    return AsFunction<SpriteSetLayerFrameFn>(
        g_SpriteSetLayerFrame.load(std::memory_order_acquire));
}
SpriteGetLayerFrameFn SpriteGetLayerFrameThunk() noexcept {
    return AsFunction<SpriteGetLayerFrameFn>(
        g_SpriteGetLayerFrame.load(std::memory_order_acquire));
}
SpriteGetTexelFn SpriteGetTexelThunk() noexcept {
    return AsFunction<SpriteGetTexelFn>(g_SpriteGetTexel.load(std::memory_order_acquire));
}
SpriteUpdateFn SpriteUpdateThunk() noexcept {
    return AsFunction<SpriteUpdateFn>(g_SpriteUpdate.load(std::memory_order_acquire));
}
SpriteIsPlayingFn SpriteIsPlayingThunk() noexcept {
    return AsFunction<SpriteIsPlayingFn>(g_SpriteIsPlaying.load(std::memory_order_acquire));
}
SpriteIsFinishedFn SpriteIsFinishedThunk() noexcept {
    return AsFunction<SpriteIsFinishedFn>(g_SpriteIsFinished.load(std::memory_order_acquire));
}
SpriteResetFn SpriteResetThunk() noexcept {
    return AsFunction<SpriteResetFn>(g_SpriteReset.load(std::memory_order_acquire));
}
SpriteRenderFn SpriteRenderThunk() noexcept {
    return AsFunction<SpriteRenderFn>(g_SpriteRender.load(std::memory_order_acquire));
}
SpriteRenderLayerFn SpriteRenderLayerThunk() noexcept {
    return AsFunction<SpriteRenderLayerFn>(
        g_SpriteRenderLayer.load(std::memory_order_acquire));
}
SpritePlayRandomFn SpritePlayRandomThunk() noexcept {
    return AsFunction<SpritePlayRandomFn>(g_SpritePlayRandom.load(std::memory_order_acquire));
}

SpritePlayOverlayFn SpritePlayOverlayThunk() noexcept {
    return AsFunction<SpritePlayOverlayFn>(g_SpritePlayOverlay.load(std::memory_order_acquire));
}
SpriteSetLastFrameFn SpriteSetLastFrameThunk() noexcept {
    return AsFunction<SpriteSetLastFrameFn>(g_SpriteSetLastFrame.load(std::memory_order_acquire));
}
SpriteSetOverlayFrameFn SpriteSetOverlayFrameThunk() noexcept {
    return AsFunction<SpriteSetOverlayFrameFn>(
        g_SpriteSetOverlayFrame.load(std::memory_order_acquire));
}

SpriteStopFn SpriteStopThunk() noexcept {
    return AsFunction<SpriteStopFn>(g_SpriteStop.load(std::memory_order_acquire));
}

SpriteIsOverlayPlayingFn SpriteIsOverlayPlayingThunk() noexcept {
    return AsFunction<SpriteIsOverlayPlayingFn>(
        g_SpriteIsOverlayPlaying.load(std::memory_order_acquire));
}

SpriteIsOverlayFinishedFn SpriteIsOverlayFinishedThunk() noexcept {
    return AsFunction<SpriteIsOverlayFinishedFn>(
        g_SpriteIsOverlayFinished.load(std::memory_order_acquire));
}

SpriteIsEventTriggeredFn SpriteIsEventTriggeredThunk() noexcept {
    return AsFunction<SpriteIsEventTriggeredFn>(
        g_SpriteIsEventTriggered.load(std::memory_order_acquire));
}

SpriteWasEventTriggeredFn SpriteWasEventTriggeredThunk() noexcept {
    return AsFunction<SpriteWasEventTriggeredFn>(
        g_SpriteWasEventTriggered.load(std::memory_order_acquire));
}

SpriteLoadFn SpriteLoadThunk() noexcept {
    return AsFunction<SpriteLoadFn>(g_SpriteLoad.load(std::memory_order_acquire));
}

SpriteLoadGraphicsFn SpriteLoadGraphicsThunk() noexcept {
    return AsFunction<SpriteLoadGraphicsFn>(
        g_SpriteLoadGraphics.load(std::memory_order_acquire));
}

SpriteReplaceSpritesheetFn SpriteReplaceSpritesheetThunk() noexcept {
    return AsFunction<SpriteReplaceSpritesheetFn>(
        g_SpriteReplaceSpritesheet.load(std::memory_order_acquire));
}

LibcxxStringAssignFn LibcxxStringAssignThunk() noexcept {
    return AsFunction<LibcxxStringAssignFn>(
        g_LibcxxStringAssign.load(std::memory_order_acquire));
}

GameOperatorDeleteFn GameOperatorDeleteThunk() noexcept {
    return AsFunction<GameOperatorDeleteFn>(
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

bool ResolveMusicUpdateVolume(std::uintptr_t method, std::uintptr_t* music) noexcept {
    return ResolveMusicForCall(method, kMusicUpdateVolumeExpectedBytes.data(),
                               kMusicUpdateVolumeExpectedBytes.size(), music);
}

bool ResolveMusicPlay(std::uintptr_t method, std::uintptr_t* music) noexcept {
    return ResolveMusicForCall(method, kMusicPlayExpectedBytes.data(),
                               kMusicPlayExpectedBytes.size(), music);
}

// 批次 185（2026-09-28）：`SFXManager:IsPlaying(ID)` 的接收者解析。
//
// 与 `ResolveMusicForCall` **同一套"取 Manager"的两跳**（当前回调的 Manager → 本帧 `Manager::Update`
// 收到的 self，两者是同一个单例），差别只有**子对象的偏移**：
// `Manager + kManagerSoundEffectsOffset`（`0x364A8`，反汇编证据在 `runtime_constants.hpp`）。
//
// ★ 为什么不能走"数据行"（`engine_method_api.hpp` 那套）：数据行的接收者来自
//   `FieldReceipt`（`Entity`/`EntityPlayer`/`Level`/`Room` 等 —— 都是**从 Lua 栈上那个 self 句柄**解）。
//   而 `SFXManager()` 在 PC 里是**全局函数**、返回的是引擎单例，我们的 handle 里**什么都没有**
//   （`SfxManagerHandle` 是空结构）⇒ 接收者只能从这里解析。这与 `MusicManager:` 一族同形。
//
// ★ `g_MusicResolveFailure` 这个失败码**由 Music 与 SFX 共用**（语义一致：
//   1 = 不在托管回调里 / 2 = Manager 或子对象读不到 / 3 = 方法地址或期望字节缺失 / 4 = 入口指纹不符）。
//   不另开一格是为了不动诊断面；两者同时出错时读数上区分不出"是哪一个"，这一点如实记在这里。
//
// ★★ 批次 408（2026-10-08）：`SFXManager:Play` **复用同一套接收者解析**，只是入口指纹不同
//   （`SoundEffects::Play` 的 16 字节 vs `IsPlaying` 的）⇒ 把判据抽成本函数
//   `ResolveSoundEffectsCore`（**判据一个字节没改**，只把"失败码写到哪一格"变成出参）。
//   为什么失败码不能共用同一格：`IsPlaying` 与 `Play` 可能在同一帧里都被调，共用一格会让
//   "最近一次失败"分不清是谁的 —— 与本批次新增的 Play 探针（`g_SfxPlayLastFailure`）冲突。
//   `ResolveSoundEffectsForCall` 因此**保持旧签名、旧行为**（继续写 `g_MusicResolveFailure`），
//   `Play` 走新入口把码写进它自己的探针格。
namespace {
bool ResolveSoundEffectsCore(std::uintptr_t method, const u8* expected, std::size_t expectedLength,
                             std::uintptr_t* soundEffects, std::uint32_t* failureCode) noexcept {
    const auto fail = [failureCode](std::uint32_t code) {
        if (failureCode != nullptr) {
            *failureCode = code;
        }
        return false;
    };
    if (!g_InManagedCallbackDispatch.load(std::memory_order_acquire)) {
        return fail(1);
    }
    uintptr_t manager = g_CurrentCallbackManager.load(std::memory_order_acquire);
    if (manager == 0) {
        if (auto provider = g_FrameManagerProvider.load(std::memory_order_acquire)) {
            manager = provider();
        }
    }
    if (manager == 0) {
        return fail(2);
    }
    if (method == 0 || expected == nullptr || expectedLength == 0) {
        return fail(3);
    }
    // 第 4 个参数 `0` = "不解引用"：`SoundEffects` 是 `Manager` 里**内嵌**的子对象，
    // `manager + 偏移` 本身就是对象地址（`Manager::PlaySound` 的 `add x0, x21, #0x364a8` 同一口径）。
    const uintptr_t candidate = FieldAddress(manager, kManagerSoundEffectsOffset,
                                             sizeof(uintptr_t), 0, &IsReadableMusicObject);
    if (candidate == 0 || !ValidateMusicMethod(method, expected, expectedLength)) {
        // 两者分开报：`candidate == 0` 是"Manager 给了但子对象读不到"（环境问题），
        // 指纹不符才是"我们的偏移/期望字节不对"（最值得怀疑的一类）。
        return fail(candidate == 0 ? 2 : 4);
    }
    if (failureCode != nullptr) {
        *failureCode = 0;
    }
    *soundEffects = candidate;
    return true;
}
}  // namespace

bool ResolveSoundEffectsMethodForCall(std::uintptr_t method, const unsigned char* expected,
                                      std::size_t expectedLength, std::uintptr_t* soundEffects) noexcept {
    std::uint32_t failureCode = 0;
    const bool ok = ResolveSoundEffectsCore(method, expected, expectedLength, soundEffects, &failureCode);
    g_MusicResolveFailure.store(failureCode, std::memory_order_release);
    return ok;
}

bool ResolveSoundEffectsForCall(std::uintptr_t method, std::uintptr_t* soundEffects) noexcept {
    std::uint32_t failureCode = 0;
    const bool ok = ResolveSoundEffectsCore(method, kSoundEffectsIsPlayingExpectedBytes.data(),
                                            kSoundEffectsIsPlayingExpectedBytes.size(), soundEffects,
                                            &failureCode);
    g_MusicResolveFailure.store(failureCode, std::memory_order_release);
    return ok;
}

// 批次 408：`SFXManager:Play` 的接收者解析（同上一套的**同一个**核心，只换指纹）。
// `failureCode` 出参：0 = 成功；1/2/3/4 同 `g_MusicResolveFailure` 的码（见上）。
bool ResolveSoundEffectsPlayForCall(std::uintptr_t method, std::uintptr_t* soundEffects,
                                    std::uint32_t* failureCode) noexcept {
    return ResolveSoundEffectsCore(method, kSoundEffectsPlayExpectedBytes.data(),
                                   kSoundEffectsPlayExpectedBytes.size(), soundEffects, failureCode);
}

bool ValidateRngSetSeedBinding(std::uintptr_t address) noexcept {
    return ValidateMusicMethod(address, kRngSetSeedExpectedBytes.data(),
                               kRngSetSeedExpectedBytes.size());
}

bool ValidateRngNextBinding(std::uintptr_t address) noexcept {
    return ValidateMusicMethod(address, kRngNextExpectedBytes.data(),
                               kRngNextExpectedBytes.size());
}

// 批次 195：`RNG::Random(uint)` / `RNG::Random()`。两次核对都用同一份 16 字节指纹判据
// （`ValidateMusicMethod`）—— 与 `SetSeed`/`Next` 逐字同形，没有第二套口径。
bool ValidateRngRandomUintBinding(std::uintptr_t address) noexcept {
    return ValidateMusicMethod(address, kRngRandomUintExpectedBytes.data(),
                               kRngRandomUintExpectedBytes.size());
}

bool ValidateRngRandomBinding(std::uintptr_t address) noexcept {
    return ValidateMusicMethod(address, kRngRandomExpectedBytes.data(),
                               kRngRandomExpectedBytes.size());
}

// 批次 195（2026-09-29）：`KAGE::Input::ManagerBase` 上按**按键号**查询的入口。
//
// ★ 这些入口**不能只比序言**：`IsButtonPressed` / `IsButtonTriggered` / `IsActionPressed` /
//   `IsActionTriggered` 四条入口的**头 32 字节完全相同** ⇒ 16 字节（甚至 32 字节）指纹认不出
//   谁是谁，偏移写串会被静默放过（换到另一条按钮查询 = 给出错语义，属最难查的一类）。
//   区分点是**各自动用的虚表槽**那条指令：`entry+0xE0` 的 4 字节 —— `IsButtonPressed` 是
//   `ldr x8,[x8,#0x30]`（指令字 `0xF9401908`，**内存字节 `08 19 40 F9`**）、
//   `IsButtonTriggered` 是 `[#0x38]`（字 `0xF9401D08`，内存 `08 1D 40 F9`）。
//   ⇒ 判据 = **16 字节序言 且 entry+0xE0 的 4 字节**。
//   ★★★ 这里原来是按"指令字的十六进制字面顺序"写的（`F9 40 19 08`）⇒ 守卫在真机上**永远不比中**、
//   而 `IsButtonPressed`/`IsButtonTriggered` 于是**恒答 false**（批次 195 留的雷，批次 210 拆掉）。
//   写这四个字节一律**按内存字节序**（与 `kKageIsButtonPressedExpectedBytes` 同一种写法）。
//   与「Card/PillEffect 序言同构、靠句柄 beginOffset 区分」是同一类坑，处置也同一套。
bool ValidateInputButtonEntry(std::uintptr_t address, const u8* expected,
                              const u8* discriminator) noexcept {
    if (address == 0 || expected == nullptr || discriminator == nullptr || (address & 3) != 0) {
        return false;
    }
#if defined(__SWITCH__)
    if (!VerifyEntryBytes(address, expected, 16, &IsEngineModuleCodeReadable)) {
        return false;
    }
    return VerifyEntryBytes(address + kKageInputButtonDiscriminatorOffset, discriminator, 4,
                            &IsEngineModuleCodeReadable);
#else
    // 宿主：同 `ValidateMusicMethod` —— 设备判据（问内核 + 逐字节比对）在宿主上无法执行，
    // 参数/对齐判据照旧生效。宿主门禁验的是"这条链有没有接上"，不是真机机器码。
    return true;
#endif
}

bool ValidateInputIsButtonPressedBinding(std::uintptr_t address) noexcept {
    return ValidateInputButtonEntry(address, kKageIsButtonPressedExpectedBytes.data(),
                                    kKageIsButtonPressedDiscriminator.data());
}

bool ValidateInputGetButtonValueBinding(std::uintptr_t address) noexcept {
    // `GetButtonValue` 的序言本来就与那三条不同（浮点返回 ⇒ `str d8,[sp,#-0x50]!` 打头）
    // ⇒ 16 字节指纹已经分得开，不需要第二个判据。
    return ValidateMusicMethod(address, kKageGetButtonValueExpectedBytes.data(),
                               kKageGetButtonValueExpectedBytes.size());
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
LuaInitResult InitializeManifestMod(const char* entry, std::size_t entryLength,
                                    const char* chunkName, const char* modRoot,
                                    const GameFileReader::Bindings& bindings) {
    if (!isaac::runtime::notice::integrity::RuntimeAllowed()) return LuaInitResult::RuntimePreparationFailed;
    if (g_ShuttingDownForModReload) return LuaInitResult::ScriptRunFailed;
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
        if (LoadFileChunk(state, entry, entryLength, chunkName) != LUA_OK) {
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
        return InstallConsoleControlsMenu(state)?LuaInitResult::Success:LuaInitResult::ScriptRunFailed;
    }

    g_Ready.store(false, std::memory_order_release);
    g_CallbackError.store(false, std::memory_order_release);
    g_PostUpdateCount.store(0, std::memory_order_release);
    const LuaInitResult result = InitializeScript(entry, entryLength, chunkName, true);
    if (result != LuaInitResult::Success) {
        ResetStage13Context();
    } else if (!InstallConsoleControlsMenu(g_LuaState)) {
        return LuaInitResult::ScriptRunFailed;
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

bool DebugConsoleEnabled() noexcept {
    return isaac::runtime::console::ConsoleSwitchEnabled();
}

void SetDebugConsoleEnabled(bool enabled) noexcept {
    if (isaac::runtime::console::ConsoleSwitchEnabled() != enabled)
        isaac::runtime::console::RequestConsoleSwitchWrite(enabled);
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

// 批次 195：按键号那两条查询的发布点（与 `SetRngRandomBindings` 同形、各自独立 acquire/release）。
void SetInputButtonBindings(uintptr_t isButtonPressed, uintptr_t getButtonValue) {
    g_InputIsButtonPressed.store(isButtonPressed, std::memory_order_release);
    g_InputGetButtonValue.store(getButtonValue, std::memory_order_release);
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

// 批次 137：`MusicManager:UpdateVolume()` 的发布点。与 `SetLevelIsAscentBinding` 同形
// （一次 release 存储、handler 一次 acquire 读 ⇒ 不会看到"半个已校验记录"）。
void SetMusicUpdateVolumeBinding(uintptr_t method) {
    g_MusicUpdateVolume.store(method, std::memory_order_release);
}

// ---- 批次 149（2026-09-26）：`MusicManager:` 一族"回调里拿不到 Manager"的兜底 ------------
//
// ★ 这两个定义**必须留在 `namespace LuaRuntime` 的正式作用域**（不能放进本文件里那些匿名
// 命名空间）：它们分别被 `hook_manager.cpp` 与 `src/interfaces/lua/` 调用，是模块对外的接口。
// 第一版就写进了匿名命名空间 ⇒ 构建在 `-Werror=unused-function` 上判红（`lua_runtime.cpp`
// 会被多个 TU 各自 include，谁不用谁就报"定义未使用"）。
void SetFrameManagerProvider(uintptr_t (*provider)()) noexcept {
    g_FrameManagerProvider.store(provider, std::memory_order_release);
}

namespace {
std::uint64_t GcBudgetClock(void*) {
    return isaac::runtime::RuntimePerfTick();
}
}

void BeginGcFrame(std::uint64_t serial) noexcept {
    if (!IsReady() || !g_LuaState || !g_ProfileSessionStarted ||
        isaac::runtime::RuntimePerfTick() == 0) return;
    // Start earlier than Lua's default 2x live-set threshold. Share 2 ms across
    // all callbacks/coroutines; pressure above 112 MiB gets a bounded 8 ms.
    // Leave explicit mod changes to the pause setting intact after setup.
    lua_gc_budgetinfo(g_LuaState, &g_RuntimeGcBudgetSnapshot);
    if (!g_RuntimeGcBudgetSnapshot.budget) lua_gc(g_LuaState, LUA_GCSETPAUSE, 110);
    lua_gc_setframebudget(g_LuaState, GcBudgetClock, nullptr, 38400, 112U * 1024U * 1024U);
    lua_gc_beginframe(g_LuaState, serial);
}

const char* MusicResolveFailureReason() noexcept {
    switch (g_MusicResolveFailure.load(std::memory_order_acquire)) {
        case 1:
            return "not inside a managed callback dispatch";
        case 2:
            return "no Manager available (neither from the callback nor for this frame)";
        case 3:
            return "the engine method was not published by the binding install";
        case 4:
            return "the engine method entry fingerprint does not match this build";
        default:
            return "no recorded reason";
    }
}

// 批次 138：`MusicManager:Play(ID, Volume)` 的发布点（与上一条同形）。
void SetMusicPlayBinding(uintptr_t method) {
    g_MusicPlay.store(method, std::memory_order_release);
}

#if defined(__GNUC__) && !defined(__clang__)
#pragma GCC push_options
#pragma GCC optimize ("Os")
#endif

void SetRngBindings(uintptr_t setSeed, uintptr_t next) {
    g_RngSetSeed.store(setSeed, std::memory_order_release);
    g_RngNext.store(next, std::memory_order_release);
}

// 批次 195：两条新 RNG 入口的发布点（与 `SetRngBindings` 同形、各自独立 acquire/release）。
void SetRngRandomBindings(uintptr_t randomUint, uintptr_t randomFloat) {
    g_RngRandomUint.store(randomUint, std::memory_order_release);
    g_RngRandom.store(randomFloat, std::memory_order_release);
}

// Published as one record and stored field by field: the handlers read each entry point with its
// own acquire load, so a partially verified record never mixes a verified and an unverified
// address inside a single call.
void SetFontBindings(const LuaFontBindings& bindings) {
    g_FontCtor.store(isaac::runtime::engine_call::AddressOfFunction(bindings.ctor),
                     std::memory_order_release);
    g_FontDestructor.store(isaac::runtime::engine_call::AddressOfFunction(bindings.destructor_),
                           std::memory_order_release);
    g_FontLoad.store(isaac::runtime::engine_call::AddressOfFunction(bindings.load),
                     std::memory_order_release);
    g_FontUnload.store(isaac::runtime::engine_call::AddressOfFunction(bindings.unload),
                       std::memory_order_release);
    g_FontIsLoaded.store(isaac::runtime::engine_call::AddressOfFunction(bindings.isLoaded),
                         std::memory_order_release);
    g_FontGetStringWidth.store(isaac::runtime::engine_call::AddressOfFunction(bindings.getStringWidth),
                               std::memory_order_release);
    g_FontGetStringWidthUTF8.store(isaac::runtime::engine_call::AddressOfFunction(bindings.getStringWidthUTF8),
                                   std::memory_order_release);
    g_FontGetLineHeight.store(isaac::runtime::engine_call::AddressOfFunction(bindings.getLineHeight),
                              std::memory_order_release);
    g_FontGetBaselineHeight.store(isaac::runtime::engine_call::AddressOfFunction(bindings.getBaselineHeight),
                                  std::memory_order_release);
    g_FontGetCharacterWidth.store(isaac::runtime::engine_call::AddressOfFunction(bindings.getCharacterWidth),
                                  std::memory_order_release);
    g_FontSetMissingCharacter.store(isaac::runtime::engine_call::AddressOfFunction(bindings.setMissingCharacter),
                                    std::memory_order_release);
    g_FontDrawString.store(isaac::runtime::engine_call::AddressOfFunction(bindings.drawString),
                           std::memory_order_release);
    g_FontDrawStringScaled.store(isaac::runtime::engine_call::AddressOfFunction(bindings.drawStringScaled),
                                 std::memory_order_release);
    g_FontDrawStringUTF8.store(isaac::runtime::engine_call::AddressOfFunction(bindings.drawStringUTF8),
                               std::memory_order_release);
    g_FontDrawStringScaledUTF8.store(isaac::runtime::engine_call::AddressOfFunction(bindings.drawStringScaledUTF8),
                                     std::memory_order_release);
    g_FontBindingGeneration.fetch_add(1, std::memory_order_release);
}

std::uint64_t FontBindingGeneration() noexcept {
    return g_FontBindingGeneration.load(std::memory_order_acquire);
}

void SetSpriteBindings(const LuaSpriteBindings& bindings) {
    g_SpriteCtor.store(isaac::runtime::engine_call::AddressOfFunction(bindings.ctor),
                       std::memory_order_release);
    g_SpriteDestructor.store(isaac::runtime::engine_call::AddressOfFunction(bindings.destructor_),
                             std::memory_order_release);
    g_SpritePlay.store(isaac::runtime::engine_call::AddressOfFunction(bindings.play),
                       std::memory_order_release);
    g_SpriteSetAnimation.store(isaac::runtime::engine_call::AddressOfFunction(bindings.setAnimation),
                               std::memory_order_release);
    g_SpriteSetFrameNamed.store(isaac::runtime::engine_call::AddressOfFunction(bindings.setFrameNamed),
                                std::memory_order_release);
    g_SpriteSetFrame.store(isaac::runtime::engine_call::AddressOfFunction(bindings.setFrame),
                           std::memory_order_release);
    g_SpriteGetFrame.store(isaac::runtime::engine_call::AddressOfFunction(bindings.getFrame),
                           std::memory_order_release);
    g_SpriteSetLayerFrame.store(isaac::runtime::engine_call::AddressOfFunction(bindings.setLayerFrame),
                                std::memory_order_release);
    g_SpriteGetLayerFrame.store(isaac::runtime::engine_call::AddressOfFunction(bindings.getLayerFrame),
                                std::memory_order_release);
    g_SpriteGetTexel.store(isaac::runtime::engine_call::AddressOfFunction(bindings.getTexel),
                           std::memory_order_release);
    g_SpriteUpdate.store(isaac::runtime::engine_call::AddressOfFunction(bindings.update),
                         std::memory_order_release);
    g_SpriteIsPlaying.store(isaac::runtime::engine_call::AddressOfFunction(bindings.isPlaying),
                            std::memory_order_release);
    g_SpriteReset.store(isaac::runtime::engine_call::AddressOfFunction(bindings.reset), std::memory_order_release);
    g_SpriteIsFinished.store(isaac::runtime::engine_call::AddressOfFunction(bindings.isFinished),
                             std::memory_order_release);
    g_SpriteRender.store(isaac::runtime::engine_call::AddressOfFunction(bindings.render),
                         std::memory_order_release);
    g_SpriteRenderLayer.store(isaac::runtime::engine_call::AddressOfFunction(bindings.renderLayer),
                              std::memory_order_release);
    g_SpritePlayRandom.store(isaac::runtime::engine_call::AddressOfFunction(bindings.playRandom),
                             std::memory_order_release);
    //: 批次 279：overlay 三条。
    g_SpritePlayOverlay.store(isaac::runtime::engine_call::AddressOfFunction(bindings.playOverlay),
                              std::memory_order_release);
    g_SpriteSetLastFrame.store(isaac::runtime::engine_call::AddressOfFunction(bindings.setLastFrame),
                               std::memory_order_release);
    g_SpriteSetOverlayFrame.store(isaac::runtime::engine_call::AddressOfFunction(bindings.setOverlayFrame),
                                  std::memory_order_release);
    //: 批次 280：`Stop`。
    g_SpriteStop.store(isaac::runtime::engine_call::AddressOfFunction(bindings.stop),
                       std::memory_order_release);
    //: 批次 283：四条「按名字查询」。
    g_SpriteIsOverlayPlaying.store(
        isaac::runtime::engine_call::AddressOfFunction(bindings.isOverlayPlaying), std::memory_order_release);
    g_SpriteIsOverlayFinished.store(
        isaac::runtime::engine_call::AddressOfFunction(bindings.isOverlayFinished), std::memory_order_release);
    g_SpriteIsEventTriggered.store(
        isaac::runtime::engine_call::AddressOfFunction(bindings.isEventTriggered), std::memory_order_release);
    g_SpriteWasEventTriggered.store(
        isaac::runtime::engine_call::AddressOfFunction(bindings.wasEventTriggered), std::memory_order_release);
    g_SpriteLoad.store(isaac::runtime::engine_call::AddressOfFunction(bindings.load),
                       std::memory_order_release);
    g_SpriteLoadGraphics.store(isaac::runtime::engine_call::AddressOfFunction(bindings.loadGraphics),
                               std::memory_order_release);
    g_SpriteReplaceSpritesheet.store(isaac::runtime::engine_call::AddressOfFunction(bindings.replaceSpritesheet),
                                     std::memory_order_release);
    g_LibcxxStringAssign.store(isaac::runtime::engine_call::AddressOfFunction(bindings.libcxxStringAssign),
                               std::memory_order_release);
    g_GameOperatorDelete.store(isaac::runtime::engine_call::AddressOfFunction(bindings.gameOperatorDelete),
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
    // `method` 刚被 `ResolveMusicForManager` 核对过 ⇒ 这里只做"地址 → 带签名的函数指针"这一步
    // （全仓唯一那处转换在层的 `AsFunction` 里）；`music` 是对象地址，走层的 `AsObject`。
    return AsFunction<GetCurrentMusicIdFn>(method)(AsObject(music)) != 0;
}
#endif

//: 一条回调实参（`mod` 之外的那些）。
//:
//: 为什么做成一张小表、而不是像从前那样一串 `bool` 开关字段：本轮要接的回调形状从 3 种涨到
//: 8 种（`(bool)`、`(int, 玩家, int)`、`(int, 玩家, int, int, int)`、`(int, int, bool, int)`…），
//: 每加一种就加两个字段会很快失控，而且"到底压几个实参"会散落到构造点去。表里只描述数据，
//: 压栈、计数、过滤器三件事各在一处做。
isaac::runtime::CardRngScopes g_CardRngScopes{};
std::uintptr_t ResolveCardRngReference(const RngHandle* handle) noexcept {
    if(!LuaRuntime::IsOnGameThread())return 0;
    return g_CardRngScopes.Resolve(handle->owner,handle->index);
}

struct CallbackArgument {
    enum class Kind : std::uint8_t {
        None = 0,  //: 哨兵（表尾，不压栈）
        Integer,   //: 整数
        Boolean,   //: 布尔（`lua_pushboolean`，不是整数 0/1）
        Entity,    //: 实体句柄（视图与 `Isaac.GetRoomEntities()` 给的一致）
        Nil,       //: 明确压 `nil`
        Vector,    //: 渲染回调的 `RenderOffset`（`Vector` userdata）
        //: 批次 396（2026-10-07）：`MC_ENTITY_TAKE_DMG` 的 `Amount`。PC 是 **float** ⇒
        //: 必须 `lua_pushnumber`（压整数会让模组 `amount > 1.5` 这类比较失真）。
        //: 值借用 `x` 那一格（与 `Vector` 共用，不另开字段）。
        Float,
        //: 批次 396：`MC_ENTITY_TAKE_DMG` 的 `Source`（`EntityRef` 句柄，缓冲区装的是**这一次**
        //: 调用的那个引用）。值借用 `entity` 那一格存"引擎实体引用的指针"。
        Reference,
        // 66：PC 包装复制整个16B RNG；不是池引用，整批回调共享同一个userdata。
        RngSnapshot,
        RngBorrowed,
        CollectibleRng,
    };
    Kind kind{Kind::None};
    std::int64_t number{0};
    std::uintptr_t entity{0};
    float x{0.0F};
    float y{0.0F};
    std::array<std::uint8_t,16> rngSnapshot{};
    std::uint64_t rngToken{};
};

struct CallbackArguments {
    static constexpr std::size_t kMaximum = 7;
    CallbackArgument items[kMaximum]{};
    std::size_t count{0};

    void AddInteger(std::int64_t value) noexcept { Push(CallbackArgument::Kind::Integer, value); }
    void AddBoolean(bool value) noexcept {
        Push(CallbackArgument::Kind::Boolean, value ? 1 : 0);
    }
    void AddNil() noexcept { Push(CallbackArgument::Kind::Nil, 0); }
    void AddCollectibleRng(std::uintptr_t player,std::int32_t item) noexcept {
        if(count>=kMaximum)return;
        auto& argument=items[count++];argument.kind=CallbackArgument::Kind::CollectibleRng;
        argument.entity=player;argument.number=item;
    }
    void AddRngSnapshot(const std::array<std::uint8_t,16>& snapshot) noexcept {
        if (count >= kMaximum) return;
        items[count].kind = CallbackArgument::Kind::RngSnapshot;
        items[count].rngSnapshot = snapshot;
        ++count;
    }
    void AddBorrowedRng(std::uintptr_t pointer,std::uint64_t token) noexcept {
        if(count>=kMaximum)return;
        auto& item=items[count++];item.kind=CallbackArgument::Kind::RngBorrowed;
        item.entity=pointer;item.rngToken=token;
    }
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
    //: 批次 396：PC 是 float 的实参（`MC_ENTITY_TAKE_DMG` 的 `Amount`）。
    void AddFloat(float value) noexcept {
        if (count >= kMaximum) {
            return;
        }
        items[count].kind = CallbackArgument::Kind::Float;
        items[count].x = value;
        ++count;
    }
    //: 批次 396：`EntityRef` 实参（值 = 引擎那个引用的地址；0 表示空引用）。
    void AddReference(std::uintptr_t engineRef) noexcept {
        if (count >= kMaximum) {
            return;
        }
        items[count].kind = CallbackArgument::Kind::Reference;
        items[count].entity = engineRef;
        ++count;
    }

private:
    void Push(CallbackArgument::Kind kind, std::int64_t value) noexcept {
        if (count >= kMaximum) {
            // 超容量是调用点的编程错误；七格覆盖MC_PRE_ENTITY_SPAWN的全部实参。
            // 这里保留原有防越界行为：
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

struct BatchObservation {
    isaac::runtime::CallbackBatchResult* result;
    std::uint32_t lastOwner{0};
    std::uint32_t depth{0};
    std::uint32_t failureOwner{0};
    std::uint32_t failureId{0};
    bool hasFailureContext{false};
    bool nativePending{false};
    std::uint64_t nativeStartedAt{0};
};
BatchObservation* g_ActiveCallbackBatch = nullptr;

void RecordObservedCallbackPerf(std::uint32_t owner, std::uint32_t callbackId,
                                std::uint64_t perfStart) {
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
                        callbackId, static_cast<std::uint16_t>(owner), static_cast<std::uint16_t>(owner >> 16)),
                    spent, &g_RuntimePerfBucketOverflow));
            }
        }
}

int InvokeObservedProtected(lua_State* state) {
    const int count=lua_gettop(state);
    if(!lua_checkstack(state,count+4))return luaL_error(state,"not enough memory preparing callback arguments");
    lua_getfield(state,2,"Function");
    lua_getfield(state,2,"Mod");
    if(lua_istable(state,-1)&&lua_getmetatable(state,-1)) {
        lua_pushliteral(state,"__handle");lua_rawget(state,-2);
        const auto* handle=static_cast<ModHandle*>(luaL_testudata(state,-1,kModMetatable));
        g_ErrorContextOwner=handle?handle->ownerPacked:0;lua_pop(state,2);
    } else g_ErrorContextOwner=0;
    for(int index=3;index<=count;++index)lua_pushvalue(state,index);
    lua_call(state,count-1,1);return 1;
}
int InvokeObservedCallback(lua_State* state) {
    if (!isaac::runtime::notice::integrity::RuntimeAllowed())
        return luaL_error(state, "compatibility layer disabled: notice resources do not match this build");
    const auto previousOwner=g_ErrorContextOwner,previousId=g_ErrorContextCallbackId;
    g_ErrorContextOwner=0;
    int integral = 0;
    const auto callbackId = lua_type(state, 1) == LUA_TNUMBER
        ? lua_tointegerx(state, 1, &integral) : 0;
    g_ErrorContextCallbackId = integral && callbackId >= 0 &&
        static_cast<std::uint64_t>(callbackId) <= UINT32_MAX
        ? static_cast<std::uint32_t>(callbackId) : UINT32_MAX;
    const int count=lua_gettop(state);
    lua_pushcfunction(state,InvokeObservedProtected);lua_insert(state,1);
    auto* observation=g_ActiveCallbackBatch;
    const bool nativeEntry=observation&&observation->depth++==0;
    const auto perfStart=isaac::runtime::RuntimePerfTick();
    const int status=lua_pcall(state,count,1,0);
    RecordObservedCallbackPerf(g_ErrorContextOwner,g_ErrorContextCallbackId,perfStart);
    if(observation) {
        --observation->depth;
        if(nativeEntry) {
            if(status==LUA_OK) {
                ++observation->result->invoked;
                if(!lua_isnil(state,-1))observation->lastOwner=g_ErrorContextOwner;
            } else {
                observation->failureOwner=g_ErrorContextOwner;
                observation->failureId=g_ErrorContextCallbackId;
                observation->hasFailureContext=true;
            }
        }
    }
    g_ErrorContextOwner=previousOwner;g_ErrorContextCallbackId=previousId;
    return status==LUA_OK?1:lua_error(state);
}

// 原生 runner 的未完成调用由外层保护收尾；手动/嵌套 Lua 派发保留独立保护。
void FinishObservedNativeCallback(lua_State* state, BatchObservation& observation, bool failed) {
    RecordObservedCallbackPerf(g_ErrorContextOwner, g_ErrorContextCallbackId, observation.nativeStartedAt);
    observation.nativePending = false;
    observation.depth = 0;
    if (failed) {
        observation.failureOwner = g_ErrorContextOwner;
        observation.failureId = g_ErrorContextCallbackId;
        observation.hasFailureContext = true;
    } else {
        ++observation.result->invoked;
        if (!lua_isnil(state, -1)) observation.lastOwner = g_ErrorContextOwner;
    }
}

int InvokeObservedNativeCallback(lua_State* state) {
    auto* observation = g_ActiveCallbackBatch;
    if (!observation || observation->depth != 0) return InvokeObservedCallback(state);
    if (!isaac::runtime::notice::integrity::RuntimeAllowed())
        return luaL_error(state, "compatibility layer disabled: notice resources do not match this build");
    const auto previousOwner = g_ErrorContextOwner, previousId = g_ErrorContextCallbackId;
    g_ErrorContextOwner = 0;
    int integral = 0;
    const auto id = lua_type(state, 1) == LUA_TNUMBER ? lua_tointegerx(state, 1, &integral) : 0;
    g_ErrorContextCallbackId = integral && id >= 0 && static_cast<std::uint64_t>(id) <= UINT32_MAX
        ? static_cast<std::uint32_t>(id) : UINT32_MAX;
    observation->nativePending = true;
    observation->depth = 1;
    observation->nativeStartedAt = isaac::runtime::RuntimePerfTick();
    const int result = InvokeObservedProtected(state);
    FinishObservedNativeCallback(state, *observation, false);
    g_ErrorContextOwner = previousOwner;
    g_ErrorContextCallbackId = previousId;
    return result;
}

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

    // 带**一个布尔实参**的那种（★ 2026-10-07 批次 388-fix）。
    //
    // 为什么必须有它：老式构造的 `extra/withExtra` 走 `AddInteger` ⇒ 压的是**整数**。
    // 而 PC 契约里 `MC_POST_GAME_STARTED` 的 `IsContinued` 是 **`bool`**
    // （`analysis/isaacdocs-snapshot/docs/enums/ModCallbacks.md:396`）。
    // 压整数不是"类型不严格"而是**真错**：Lua 里 **`0` 是 truthy** ⇒ 新开局时模组写
    // `if isContinued then` 会**照样进 `then` 分支**（PC 上是 `false` ⇒ 不进）
    // ⇒ 新开局的逻辑被当成"继续存档"执行。
    [[nodiscard]] static LuaCallbackInvoker ForBoolean(bool value) noexcept {
        LuaCallbackInvoker invoker{0, false, false};
        invoker.arguments.AddBoolean(value);
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

    // 外层生成保护桥保留一格Lua栈；每次成功的表只替换引用，最终才读字段。
    int tableStackIndex{0};
    std::uint32_t tableOwner{0};
    bool batchMode{false};
    std::int64_t batchFilter{isaac::runtime::CallbackRegistry::kNoCallbackFilter};
    bool ownerBatch{false};
    std::uint32_t batchOwner{0};
    bool InvokeBatch(isaac::runtime::CallbackId id, std::int64_t filter,
                     isaac::runtime::CallbackBatchResult* result,
                     const isaac::runtime::ModHandle* owner = nullptr) noexcept override {
        *result={};
        if(!isaac::runtime::BuiltinCallbackEnabled(id))return true;
        BatchObservation observation{result};
        const auto previous=g_ActiveCallbackBatch;g_ActiveCallbackBatch=&observation;
        batchMode=true;batchFilter=filter;ownerBatch=owner!=nullptr;
        batchOwner=owner?static_cast<std::uint32_t>(owner->index)|(static_cast<std::uint32_t>(owner->generation)<<16):0;
        isaac::runtime::CallbackDescriptor descriptor{};descriptor.id=id;
        const auto status=InvokeCore(descriptor,true,&result->returned);
        if(!status.ok())result->failed=1;
        tableOwner=observation.lastOwner;
        batchMode=false;g_ActiveCallbackBatch=previous;
        return true;
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
    // 零upvalue的C函数不分配闭包；userdata与实际Lua调用都在外层保护之内。
    static int InvokeProtected(lua_State* state) {
        auto* self = static_cast<LuaCallbackInvoker*>(lua_touserdata(state, 1));
        const auto* descriptor = static_cast<const isaac::runtime::CallbackDescriptor*>(lua_touserdata(state, 2));
        const bool collecting = lua_toboolean(state, 3) != 0;
        if(self->batchMode) {
            isaac::runtime::PushCallbackRunner(state,self->ownerBatch);
            lua_pushinteger(state,descriptor->id);
            if(self->batchFilter==isaac::runtime::CallbackRegistry::kNoCallbackFilter)lua_pushnil(state);
            else lua_pushinteger(state,self->batchFilter);
            if(self->ownerBatch)lua_pushinteger(state,self->batchOwner);
        } else {
            lua_rawgeti(state, LUA_REGISTRYINDEX, descriptor->luaReference);
            lua_rawgeti(state, LUA_REGISTRYINDEX, descriptor->modReference);
        }
        // 实参按编组表顺序压栈（`mod` 已经在栈上，是第 1 个）。
        for (std::size_t index = 0; index < self->arguments.count; ++index) {
            const CallbackArgument& argument = self->arguments.items[index];
            switch (argument.kind) {
                case CallbackArgument::Kind::Integer:
                    lua_pushinteger(state, static_cast<lua_Integer>(argument.number));
                    break;
                case CallbackArgument::Kind::Boolean:
                    lua_pushboolean(state, argument.number != 0 ? 1 : 0);
                    break;
                case CallbackArgument::Kind::Nil:
                    lua_pushnil(state);
                    break;
                case CallbackArgument::Kind::CollectibleRng:
                    isaac::runtime::PushCollectibleRngCallbackArgument(state,argument.entity,
                        static_cast<std::int32_t>(argument.number));
                    break;
                case CallbackArgument::Kind::Entity:
                    // 视图与 `Isaac.GetRoomEntities()` 给出的一致（玩家给 `EntityPlayer`），
                    // 否则模组在回调里对参数调 `player:HasCollectible()` 会失败。
                    isaac::runtime::PushEntityCallbackArgument(state, argument.entity);
                    break;
                case CallbackArgument::Kind::Vector:
                    // 渲染偏移（`Vector` userdata，与 `Room:GetRenderScrollOffset()` 给出的是同一种值类型）。
                    isaac::runtime::PushLuaVector(state, argument.x, argument.y);
                    break;
                case CallbackArgument::Kind::Float:
                    // 批次 396：PC 契约写的是 float（`Amount`）⇒ 压 number，不是 integer。
                    lua_pushnumber(state, static_cast<lua_Number>(argument.x));
                    break;
                case CallbackArgument::Kind::Reference:
                    // 批次 396：`EntityRef` 句柄（缓冲区从引擎那个引用搬，见 entity_ref_api.cpp）。
                    isaac::runtime::PushEntityRefArgument(state, argument.entity);
                    break;
                case CallbackArgument::Kind::None:
                    break;
                case CallbackArgument::Kind::RngBorrowed: {
                    auto* rng=static_cast<RngHandle*>(lua_newuserdata(state,sizeof(RngHandle)));
                    *rng={};rng->resolver=ResolveCardRngReference;
                    rng->owner=argument.entity;rng->index=argument.rngToken;
                    luaL_getmetatable(state,kRngMetatable);lua_setmetatable(state,-2);
                    break;
                }
                case CallbackArgument::Kind::RngSnapshot: {
                    // 分配/设元表必须在此保护内；Lua 批处理 runner 收到同一份值对象。
                    auto* rng = static_cast<RngHandle*>(lua_newuserdata(state,sizeof(RngHandle)));
                    *rng = {};
                    rng->storage = argument.rngSnapshot;
                    luaL_getmetatable(state,kRngMetatable);
                    lua_setmetatable(state,-2);
                    break;
                }
            }
        }
        const int argumentCount = (self->batchMode ? (self->ownerBatch ? 3 : 2) : 1) + static_cast<int>(self->arguments.count);
        lua_callk(state, argumentCount, collecting ? 1 : 0, 0, nullptr);
        const auto id = descriptor->id;
        const bool integerReturn = id == isaac::runtime::kCallbackPreGetCollectible ||
            id == isaac::runtime::kCallbackPostGetCollectible || id == isaac::runtime::kCallbackGetCard ||
            id == isaac::runtime::kCallbackGetPillColor || id == isaac::runtime::kCallbackGetPillEffect ||
            id == isaac::runtime::kCallbackGetTrinket || id == isaac::runtime::kCallbackPostCurseEval;
        if (collecting && integerReturn && !lua_isnil(state, -1)) {
            // native外包装使用luaL_checkinteger：数字字符串/整数浮点也接受；
            // 非整数/false等错误必须仍位于本C桥的外层保护内，不穿过C++派发栈。
            const auto integer = luaL_checkinteger(state, -1);
            lua_pop(state, 1);
            lua_pushinteger(state, integer);
        }
        // The returned value remains rooted. Finalizer errors stay inside the
        // caller's existing lua_pcall; the native frame hook never executes GC.
        lua_gc_advance(state);
        return collecting ? 1 : 0;
    }

    isaac::runtime::Status InvokeCore(const isaac::runtime::CallbackDescriptor& descriptor,
                                      bool collecting,
                                      isaac::runtime::CallbackReturn* result) noexcept {
        if (!isaac::runtime::notice::integrity::RuntimeAllowed())
            return isaac::runtime::Status{isaac::runtime::StatusCode::InvalidState};
        if (g_LuaState == nullptr) {
            return isaac::runtime::Status{isaac::runtime::StatusCode::InvalidState};
        }
        // lua_checkstack自己使用受保护的扩栈；失败不进入作用域也不改变调用方栈。
        if (!lua_checkstack(g_LuaState, 8)) {
            g_CallbackError.store(true, std::memory_order_release);
            return isaac::runtime::Status{isaac::runtime::StatusCode::Rejected};
        }
        lua_pushcfunction(g_LuaState, InvokeProtected);
        lua_pushlightuserdata(g_LuaState, this);
        lua_pushlightuserdata(g_LuaState, const_cast<isaac::runtime::CallbackDescriptor*>(&descriptor));
        lua_pushboolean(g_LuaState, collecting);
#if defined(EXL_PERSISTENCE_TRACE) || defined(EXL_PERSISTENCE_EVENT_DIAGNOSTIC)
        if (postUpdate) {
            g_CallbackOperation.store(static_cast<u8>(CallbackOperation::None),
                                      std::memory_order_release);
        }
#endif
        // 嵌套入口回调必须恢复外层作用域，不能把仍在运行的外层当成已经退出。
        const auto previousManagedScope = g_InManagedCallbackDispatch.load(std::memory_order_acquire);
        const auto previousManager = g_CurrentCallbackManager.load(std::memory_order_acquire);
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
        // 批次 084：同 TU 的 file-local 计数（不碰数据 GOT），只读一次 `cntpct_el0`
        // （**物理**计数器；`cntvct_el0` 在 EL0 会被禁止读，批次 085 的真机崩溃就是它）。
        // 三个桥接实参：invoker、登记项、是否收集结果；真正实参在保护内准备。
        const int callbackStatus = lua_pcallk(g_LuaState, 3, collecting ? 1 : 0, 0, 0,
                                             nullptr);
        // ★ 复原必须放在**错误捕获之后**：`CaptureLuaErrorTop` 要读这两个值来盖归属，
        // 放在 pcall 之后立刻复原的话，记录到的永远是默认值（宿主测试第一次就是这么红的）。
        g_InManagedCallbackDispatch.store(previousManagedScope, std::memory_order_release);
        g_CurrentCallbackManager.store(previousManager, std::memory_order_release);
        if (callbackStatus != LUA_OK) {
            if (batchMode && g_ActiveCallbackBatch && g_ActiveCallbackBatch->nativePending) {
                FinishObservedNativeCallback(g_LuaState, *g_ActiveCallbackBatch, true);
            }
#if defined(EXL_PERSISTENCE_TRACE) || defined(EXL_PERSISTENCE_EVENT_DIAGNOSTIC)
            const u64 detail =
                (CallbackErrorTail(g_LuaState) << 16) |
                (static_cast<u64>(g_CallbackOperation.load(std::memory_order_acquire)) << 8) |
                static_cast<u8>(callbackStatus);
            g_CallbackFailureDetail.store(detail, std::memory_order_release);
#endif
            if(batchMode&&g_ActiveCallbackBatch&&g_ActiveCallbackBatch->hasFailureContext) {
                g_ErrorContextOwner=g_ActiveCallbackBatch->failureOwner;
                g_ErrorContextCallbackId=g_ActiveCallbackBatch->failureId;
            }
            CaptureLuaErrorTop(g_LuaState);
            lua_pop(g_LuaState, 1);
            g_ErrorContextOwner = previousOwner;
            g_ErrorContextCallbackId = previousCallbackId;
            g_CallbackError.store(true, std::memory_order_release);
            return isaac::runtime::Status{isaac::runtime::StatusCode::Rejected};
        }
        g_ErrorContextOwner = previousOwner;
        g_ErrorContextCallbackId = previousCallbackId;
        // 读回返回值。受保护调用在 `collecting` 时**保证**栈上恰好有 1 个结果
        // （函数没 `return` 时 Lua 补 `nil`），所以这里不需要"检查栈高"。
        // ⚠️ 这里同样**不写那次调用的函数名**（理由见 `InvokeCore` 上方的注释）。
        if (result != nullptr) {
            if ((descriptor.id == isaac::runtime::kCallbackPreEntitySpawn ||
                 descriptor.id == isaac::runtime::kCallbackPreRoomEntitySpawn ||
                 descriptor.id == isaac::runtime::kCallbackUseItem ||
                 descriptor.id == isaac::runtime::kCallbackPostPickupSelection) && lua_istable(g_LuaState, -1)) {
                result->hasTable = true;
                if (tableStackIndex != 0) {
                    lua_copy(g_LuaState, -1, tableStackIndex);
                    tableOwner = static_cast<std::uint32_t>(descriptor.owner.index) |
                        (static_cast<std::uint32_t>(descriptor.owner.generation) << 16);
                }
            }
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
                // ★ 2026-10-07（批次 390）：数字通道（整数与浮点都算）。
                //   `MC_INPUT_ACTION` 的 `GET_ACTION_VALUE` 覆盖值是 float（0.0~1.0），
                //   而模组通常写 `return 0`（Lua 的整数）⇒ 只看 `lua_isinteger` 会漏掉一半写法。
                if (lua_type(g_LuaState, -1) == LUA_TNUMBER) {
                    result->hasNumber = true;
                    result->number = static_cast<double>(lua_tonumberx(g_LuaState, -1, nullptr));
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
// 模组重载会在主菜单新建 VM；进局前作者尚未从存档恢复配置。
bool g_GameStartedInCurrentVm{};
isaac::runtime::ManagedUpdateSnapshot g_LastManagedUpdate{};
bool g_HasManagedUpdate{};

// 两个明确相关的派发入口复用同一窗口，嵌套GAME_STARTED不清空外层缓存。
class ManagedEngineDispatchScope final {
public:
    ManagedEngineDispatchScope() noexcept
        : owns_(isaac::runtime::EngineGuardDispatchActive().load(std::memory_order_acquire) == 0) {
        if (owns_) isaac::runtime::EngineGuardEnterDispatch();
    }
    ~ManagedEngineDispatchScope() noexcept {
        if (owns_) isaac::runtime::EngineGuardLeaveDispatch();
    }
    ManagedEngineDispatchScope(const ManagedEngineDispatchScope&) = delete;
    ManagedEngineDispatchScope& operator=(const ManagedEngineDispatchScope&) = delete;
private:
    bool owns_;
};

constexpr std::uint32_t kGameStartedFromSave = 1;
constexpr std::uint32_t kGameStartedFresh = 2;
}  // namespace

void NoteGameStarted(bool isSave) noexcept {
    g_HasManagedUpdate = false;
    g_LastManagedUpdate = {};
    isaac::runtime::console::InvalidateConsoleSession();
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
    const ManagedEngineDispatchScope dispatchScope;
    // ★ 2026-10-07（批次 388-fix）：`IsContinued` 必须压 **布尔** —— 老式写法
    //   `LuaCallbackInvoker{0,false,false, isSave?1:0, true}` 走 `AddInteger`，
    //   而 Lua 里 `0` 是 truthy ⇒ 新开局时模组判 `if isContinued then` 会走成"继续存档"。
    //   PC 契约：`analysis/isaacdocs-snapshot/docs/enums/ModCallbacks.md:396`（`boolean IsContinued`）。
    LuaCallbackInvoker invoker = LuaCallbackInvoker::ForBoolean(isSave);
    isaac::runtime::CallbackDispatcher dispatcher{g_CallbackRegistry, invoker};
    static_cast<void>(dispatcher.Dispatch(isaac::runtime::kCallbackPostGameStarted,
                                          isaac::runtime::ThreadAffinity::Any));
    g_GameStartedInCurrentVm = true;
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
    // 2026-10-16：开局分阶段准备；身份暂不可读时保留已派发的玩家INIT，避免重发。
    std::uint32_t preparedGameStartKind{0};
    GameLocationKey location{};
    std::uint64_t roomLoadGeneration{0};
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
// 原生Init已经接管时，扫描只建立开局/玩家账本，不重复补发初始化。
bool g_NativePlayerInitObserved{};

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
    for(std::uint32_t id=0;id<=isaac::runtime::kCallbackMaximumId;++id) {
        if(!isaac::runtime::BuiltinCallbackEnabled(id))continue;
        if(id<64)mask.low|=1ULL<<id;else mask.high|=1ULL<<(id-64);
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
           mask.Has(isaac::runtime::kCallbackPostProjectileInit) ||
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
void DispatchNpcEntityEvents(EntityEventScan* scan, std::uintptr_t entity,
                             std::int64_t filter) noexcept {
    if (scan->renderPhase) {
        return;  // `MC_POST_NPC_RENDER` 不在本批（台账里是 needs_hook），见批次 010 的记录。
    }
    if (scan->registered.Has(isaac::runtime::kCallbackPostNpcInit) &&
        NoteNewEntity(g_FrameEventState.seenNpcs, kSeenNpcCapacity, &g_FrameEventState.seenNpcCount,
                      entity)) {
        LuaCallbackInvoker invoker = LuaCallbackInvoker::ForEntity(entity);
        isaac::runtime::CallbackDispatcher dispatcher{g_CallbackRegistry, invoker};
        static_cast<void>(dispatcher.DispatchFiltered(isaac::runtime::kCallbackPostNpcInit,
                                              isaac::runtime::ThreadAffinity::Any, filter));
    }
    if (scan->registered.Has(isaac::runtime::kCallbackNpcUpdate)) {
        LuaCallbackInvoker invoker = LuaCallbackInvoker::ForEntity(entity);
        isaac::runtime::CallbackDispatcher dispatcher{g_CallbackRegistry, invoker};
        static_cast<void>(dispatcher.DispatchFiltered(isaac::runtime::kCallbackNpcUpdate,
                                              isaac::runtime::ThreadAffinity::Any, filter));
    }

}

void DispatchFamiliarEntityEvents(EntityEventScan* scan, std::uintptr_t entity,
                             std::int64_t filter) noexcept {
    if (!scan->renderPhase && scan->registered.Has(isaac::runtime::kCallbackFamiliarInit) &&
        NoteNewEntity(g_FrameEventState.seenFamiliars, kSeenFamiliarCapacity,
                      &g_FrameEventState.seenFamiliarCount, entity)) {
        LuaCallbackInvoker invoker = LuaCallbackInvoker::ForEntity(entity);
        isaac::runtime::CallbackDispatcher dispatcher{g_CallbackRegistry, invoker};
        static_cast<void>(dispatcher.DispatchFiltered(isaac::runtime::kCallbackFamiliarInit,
                                              isaac::runtime::ThreadAffinity::Any, filter));
    }
    if (!scan->renderPhase && scan->registered.Has(isaac::runtime::kCallbackFamiliarUpdate)) {
        LuaCallbackInvoker invoker = LuaCallbackInvoker::ForEntity(entity);
        isaac::runtime::CallbackDispatcher dispatcher{g_CallbackRegistry, invoker};
        static_cast<void>(dispatcher.DispatchFiltered(isaac::runtime::kCallbackFamiliarUpdate,
                                              isaac::runtime::ThreadAffinity::Any, filter));
    }
    if (scan->renderPhase && scan->registered.Has(isaac::runtime::kCallbackPostFamiliarRender)) {
        LuaCallbackInvoker invoker = LuaCallbackInvoker::ForEntityWithVector(
            entity, scan->renderOffsetX, scan->renderOffsetY);
        isaac::runtime::CallbackDispatcher dispatcher{g_CallbackRegistry, invoker};
        static_cast<void>(dispatcher.DispatchFiltered(isaac::runtime::kCallbackPostFamiliarRender,
                                              isaac::runtime::ThreadAffinity::Any, filter));
    }
}

void DispatchTearEntityEvents(EntityEventScan* scan, std::uintptr_t entity,
                             std::int64_t filter) noexcept {
    if (!scan->renderPhase && scan->registered.Has(isaac::runtime::kCallbackPostTearInit) &&
        NoteNewEntity(g_FrameEventState.seenTears, kSeenTearCapacity, &g_FrameEventState.seenTearCount,
                      entity)) {
        LuaCallbackInvoker invoker = LuaCallbackInvoker::ForEntity(entity);
        isaac::runtime::CallbackDispatcher dispatcher{g_CallbackRegistry, invoker};
        static_cast<void>(dispatcher.DispatchFiltered(isaac::runtime::kCallbackPostTearInit,
                                              isaac::runtime::ThreadAffinity::Any, filter));
    }
    if (!scan->renderPhase && scan->registered.Has(isaac::runtime::kCallbackPostTearUpdate)) {
        LuaCallbackInvoker invoker = LuaCallbackInvoker::ForEntity(entity);
        isaac::runtime::CallbackDispatcher dispatcher{g_CallbackRegistry, invoker};
        static_cast<void>(dispatcher.DispatchFiltered(isaac::runtime::kCallbackPostTearUpdate,
                                              isaac::runtime::ThreadAffinity::Any, filter));
    }
    if (scan->renderPhase && scan->registered.Has(isaac::runtime::kCallbackPostTearRender)) {
        LuaCallbackInvoker invoker = LuaCallbackInvoker::ForEntityWithVector(
            entity, scan->renderOffsetX, scan->renderOffsetY);
        isaac::runtime::CallbackDispatcher dispatcher{g_CallbackRegistry, invoker};
        static_cast<void>(dispatcher.DispatchFiltered(isaac::runtime::kCallbackPostTearRender,
                                              isaac::runtime::ThreadAffinity::Any, filter));
    }
}

void DispatchProjectileEntityEvents(EntityEventScan* scan, std::uintptr_t entity,
                             std::int64_t filter) noexcept {
    // 44号由真实Projectile.Update正常完成尾部派发，不能随Manager/渲染循环扫描。
    if (scan->renderPhase && scan->registered.Has(isaac::runtime::kCallbackPostProjectileRender)) {
        LuaCallbackInvoker invoker = LuaCallbackInvoker::ForEntityWithVector(
            entity, scan->renderOffsetX, scan->renderOffsetY);
        isaac::runtime::CallbackDispatcher dispatcher{g_CallbackRegistry, invoker};
        static_cast<void>(dispatcher.DispatchFiltered(isaac::runtime::kCallbackPostProjectileRender,
                                              isaac::runtime::ThreadAffinity::Any, filter));
    }
}

void DispatchLaserEntityEvents(EntityEventScan* scan, std::uintptr_t entity,
                             std::int64_t filter) noexcept {
    if (!scan->renderPhase && scan->registered.Has(isaac::runtime::kCallbackPostLaserInit) &&
        NoteNewEntity(g_FrameEventState.seenLasers, kSeenLaserCapacity,
                      &g_FrameEventState.seenLaserCount, entity)) {
        LuaCallbackInvoker invoker = LuaCallbackInvoker::ForEntity(entity);
        isaac::runtime::CallbackDispatcher dispatcher{g_CallbackRegistry, invoker};
        static_cast<void>(dispatcher.DispatchFiltered(isaac::runtime::kCallbackPostLaserInit,
                                              isaac::runtime::ThreadAffinity::Any, filter));
    }
    if (!scan->renderPhase && scan->registered.Has(isaac::runtime::kCallbackPostLaserUpdate)) {
        LuaCallbackInvoker invoker = LuaCallbackInvoker::ForEntity(entity);
        isaac::runtime::CallbackDispatcher dispatcher{g_CallbackRegistry, invoker};
        static_cast<void>(dispatcher.DispatchFiltered(isaac::runtime::kCallbackPostLaserUpdate,
                                              isaac::runtime::ThreadAffinity::Any, filter));
    }
    if (scan->renderPhase && scan->registered.Has(isaac::runtime::kCallbackPostLaserRender)) {
        LuaCallbackInvoker invoker = LuaCallbackInvoker::ForEntityWithVector(
            entity, scan->renderOffsetX, scan->renderOffsetY);
        isaac::runtime::CallbackDispatcher dispatcher{g_CallbackRegistry, invoker};
        static_cast<void>(dispatcher.DispatchFiltered(isaac::runtime::kCallbackPostLaserRender,
                                              isaac::runtime::ThreadAffinity::Any, filter));
    }
}

void DispatchKnifeEntityEvents(EntityEventScan* scan, std::uintptr_t entity,
                             std::int64_t filter) noexcept {
    if (!scan->renderPhase && scan->registered.Has(isaac::runtime::kCallbackPostKnifeInit) &&
        NoteNewEntity(g_FrameEventState.seenKnives, kSeenKnifeCapacity,
                      &g_FrameEventState.seenKnifeCount, entity)) {
        LuaCallbackInvoker invoker = LuaCallbackInvoker::ForEntity(entity);
        isaac::runtime::CallbackDispatcher dispatcher{g_CallbackRegistry, invoker};
        static_cast<void>(dispatcher.DispatchFiltered(isaac::runtime::kCallbackPostKnifeInit,
                                              isaac::runtime::ThreadAffinity::Any, filter));
    }
    if (!scan->renderPhase && scan->registered.Has(isaac::runtime::kCallbackPostKnifeUpdate)) {
        LuaCallbackInvoker invoker = LuaCallbackInvoker::ForEntity(entity);
        isaac::runtime::CallbackDispatcher dispatcher{g_CallbackRegistry, invoker};
        static_cast<void>(dispatcher.DispatchFiltered(isaac::runtime::kCallbackPostKnifeUpdate,
                                              isaac::runtime::ThreadAffinity::Any, filter));
    }
    if (scan->renderPhase && scan->registered.Has(isaac::runtime::kCallbackPostKnifeRender)) {
        LuaCallbackInvoker invoker = LuaCallbackInvoker::ForEntityWithVector(
            entity, scan->renderOffsetX, scan->renderOffsetY);
        isaac::runtime::CallbackDispatcher dispatcher{g_CallbackRegistry, invoker};
        static_cast<void>(dispatcher.DispatchFiltered(isaac::runtime::kCallbackPostKnifeRender,
                                              isaac::runtime::ThreadAffinity::Any, filter));
    }
}

void DispatchEffectEntityEvents(EntityEventScan* scan, std::uintptr_t entity,
                             std::int64_t filter) noexcept {
    if (!scan->renderPhase && scan->registered.Has(isaac::runtime::kCallbackPostEffectInit) &&
        NoteNewEntity(g_FrameEventState.seenEffects, kSeenEffectCapacity,
                      &g_FrameEventState.seenEffectCount, entity)) {
        LuaCallbackInvoker invoker = LuaCallbackInvoker::ForEntity(entity);
        isaac::runtime::CallbackDispatcher dispatcher{g_CallbackRegistry, invoker};
        static_cast<void>(dispatcher.DispatchFiltered(isaac::runtime::kCallbackPostEffectInit,
                                              isaac::runtime::ThreadAffinity::Any, filter));
    }
    if (!scan->renderPhase && scan->registered.Has(isaac::runtime::kCallbackPostEffectUpdate)) {
        LuaCallbackInvoker invoker = LuaCallbackInvoker::ForEntity(entity);
        isaac::runtime::CallbackDispatcher dispatcher{g_CallbackRegistry, invoker};
        static_cast<void>(dispatcher.DispatchFiltered(isaac::runtime::kCallbackPostEffectUpdate,
                                              isaac::runtime::ThreadAffinity::Any, filter));
    }
    if (scan->renderPhase && scan->registered.Has(isaac::runtime::kCallbackPostEffectRender)) {
        LuaCallbackInvoker invoker = LuaCallbackInvoker::ForEntityWithVector(
            entity, scan->renderOffsetX, scan->renderOffsetY);
        isaac::runtime::CallbackDispatcher dispatcher{g_CallbackRegistry, invoker};
        static_cast<void>(dispatcher.DispatchFiltered(isaac::runtime::kCallbackPostEffectRender,
                                              isaac::runtime::ThreadAffinity::Any, filter));
    }
}

void DispatchBombEntityEvents(EntityEventScan* scan, std::uintptr_t entity,
                             std::int64_t filter) noexcept {
    if (!scan->renderPhase && scan->registered.Has(isaac::runtime::kCallbackPostBombInit) &&
        NoteNewEntity(g_FrameEventState.seenBombs, kSeenBombCapacity, &g_FrameEventState.seenBombCount,
                      entity)) {
        LuaCallbackInvoker invoker = LuaCallbackInvoker::ForEntity(entity);
        isaac::runtime::CallbackDispatcher dispatcher{g_CallbackRegistry, invoker};
        static_cast<void>(dispatcher.DispatchFiltered(isaac::runtime::kCallbackPostBombInit,
                                              isaac::runtime::ThreadAffinity::Any, filter));
    }
    if (!scan->renderPhase && scan->registered.Has(isaac::runtime::kCallbackPostBombUpdate)) {
        LuaCallbackInvoker invoker = LuaCallbackInvoker::ForEntity(entity);
        isaac::runtime::CallbackDispatcher dispatcher{g_CallbackRegistry, invoker};
        static_cast<void>(dispatcher.DispatchFiltered(isaac::runtime::kCallbackPostBombUpdate,
                                              isaac::runtime::ThreadAffinity::Any, filter));
    }
    if (scan->renderPhase && scan->registered.Has(isaac::runtime::kCallbackPostBombRender)) {
        LuaCallbackInvoker invoker = LuaCallbackInvoker::ForEntityWithVector(
            entity, scan->renderOffsetX, scan->renderOffsetY);
        isaac::runtime::CallbackDispatcher dispatcher{g_CallbackRegistry, invoker};
        static_cast<void>(dispatcher.DispatchFiltered(isaac::runtime::kCallbackPostBombRender,
                                              isaac::runtime::ThreadAffinity::Any, filter));
    }
}

void DispatchPickupEntityEvents(EntityEventScan* scan, std::uintptr_t entity,
                             std::int64_t filter) noexcept {
    if (!scan->renderPhase && scan->registered.Has(isaac::runtime::kCallbackPostPickupInit) &&
        NoteNewEntity(g_FrameEventState.seenPickups, kSeenPickupCapacity,
                      &g_FrameEventState.seenPickupCount, entity)) {
        LuaCallbackInvoker invoker = LuaCallbackInvoker::ForEntity(entity);
        isaac::runtime::CallbackDispatcher dispatcher{g_CallbackRegistry, invoker};
        static_cast<void>(dispatcher.DispatchFiltered(isaac::runtime::kCallbackPostPickupInit,
                                              isaac::runtime::ThreadAffinity::Any, filter));
    }
    if (!scan->renderPhase && scan->registered.Has(isaac::runtime::kCallbackPostPickupUpdate)) {
        LuaCallbackInvoker invoker = LuaCallbackInvoker::ForEntity(entity);
        isaac::runtime::CallbackDispatcher dispatcher{g_CallbackRegistry, invoker};
        static_cast<void>(dispatcher.DispatchFiltered(isaac::runtime::kCallbackPostPickupUpdate,
                                              isaac::runtime::ThreadAffinity::Any, filter));
    }
    if (scan->renderPhase && scan->registered.Has(isaac::runtime::kCallbackPostPickupRender)) {
        LuaCallbackInvoker invoker = LuaCallbackInvoker::ForEntityWithVector(
            entity, scan->renderOffsetX, scan->renderOffsetY);
        isaac::runtime::CallbackDispatcher dispatcher{g_CallbackRegistry, invoker};
        static_cast<void>(dispatcher.DispatchFiltered(isaac::runtime::kCallbackPostPickupRender,
                                              isaac::runtime::ThreadAffinity::Any, filter));
    }
}

void DispatchPlayerInitialization(EntityEventScan* scan, std::uintptr_t entity,
                             std::int64_t filter) noexcept {
    if (!scan->renderPhase && scan->registered.Has(isaac::runtime::kCallbackPostPlayerInit) &&
        NoteNewEntity(g_FrameEventState.seenPlayers, kSeenPlayerCapacity,
                      &g_FrameEventState.seenPlayerCount, entity)) {
        if (g_NativePlayerInitObserved) return;
        LuaCallbackInvoker invoker = LuaCallbackInvoker::ForEntity(entity);
        isaac::runtime::CallbackDispatcher dispatcher{g_CallbackRegistry, invoker};
        static_cast<void>(dispatcher.DispatchFiltered(isaac::runtime::kCallbackPostPlayerInit,
                                              isaac::runtime::ThreadAffinity::Any, filter));
    }
}

void DispatchPlayerEntityEvents(EntityEventScan* scan, std::uintptr_t entity,
                             std::int64_t filter) noexcept {
    DispatchPlayerInitialization(scan, entity, filter);
    // `MC_POST_PEFFECT_UPDATE` 在 PC 上是"玩家身上的效果每帧更新"，实参就是那个玩家。
    if (!scan->renderPhase && scan->registered.Has(isaac::runtime::kCallbackPostPeffectUpdate)) {
        LuaCallbackInvoker invoker = LuaCallbackInvoker::ForEntity(entity);
        isaac::runtime::CallbackDispatcher dispatcher{g_CallbackRegistry, invoker};
        static_cast<void>(dispatcher.DispatchFiltered(isaac::runtime::kCallbackPostPeffectUpdate,
                                              isaac::runtime::ThreadAffinity::Any, filter));
    }
    if (!scan->renderPhase && scan->registered.Has(isaac::runtime::kCallbackPostPlayerUpdate)) {
        LuaCallbackInvoker invoker = LuaCallbackInvoker::ForEntity(entity);
        isaac::runtime::CallbackDispatcher dispatcher{g_CallbackRegistry, invoker};
        static_cast<void>(dispatcher.DispatchFiltered(isaac::runtime::kCallbackPostPlayerUpdate,
                                              isaac::runtime::ThreadAffinity::Any, filter));
    }
    // 玩家那张"见过"表**跨房间不清**（玩家跨房间存活，见 `FrameEventState` 的说明）。
    if (scan->renderPhase && scan->registered.Has(isaac::runtime::kCallbackPostPlayerRender)) {
        LuaCallbackInvoker invoker = LuaCallbackInvoker::ForEntityWithVector(
            entity, scan->renderOffsetX, scan->renderOffsetY);
        isaac::runtime::CallbackDispatcher dispatcher{g_CallbackRegistry, invoker};
        static_cast<void>(dispatcher.DispatchFiltered(isaac::runtime::kCallbackPostPlayerRender,
                                              isaac::runtime::ThreadAffinity::Any, filter));
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
    std::int64_t filter = 0;
    switch (isaac::runtime::ClassifyCallbackEntity(entity, &filter)) {
        case isaac::runtime::CallbackEntityClass::Npc:
            DispatchNpcEntityEvents(scan, entity, filter);
            break;
        case isaac::runtime::CallbackEntityClass::Familiar:
            DispatchFamiliarEntityEvents(scan, entity, filter);
            break;
        case isaac::runtime::CallbackEntityClass::Tear:
            DispatchTearEntityEvents(scan, entity, filter);
            break;
        case isaac::runtime::CallbackEntityClass::Projectile:
            DispatchProjectileEntityEvents(scan, entity, filter);
            break;
        case isaac::runtime::CallbackEntityClass::Laser:
            DispatchLaserEntityEvents(scan, entity, filter);
            break;
        case isaac::runtime::CallbackEntityClass::Knife:
            DispatchKnifeEntityEvents(scan, entity, filter);
            break;
        case isaac::runtime::CallbackEntityClass::Effect:
            DispatchEffectEntityEvents(scan, entity, filter);
            break;
        case isaac::runtime::CallbackEntityClass::Bomb:
            DispatchBombEntityEvents(scan, entity, filter);
            break;
        case isaac::runtime::CallbackEntityClass::Pickup:
            DispatchPickupEntityEvents(scan, entity, filter);
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
    std::int64_t filter = 0;
    if (isaac::runtime::ClassifyCallbackEntity(entity, &filter) !=
        isaac::runtime::CallbackEntityClass::Player) {
        return;
    }
    DispatchPlayerEntityEvents(scan, entity, filter);
}

void OnInitialPlayerEvent(void* context, std::uintptr_t entity) noexcept {
    auto* scan = static_cast<EntityEventScan*>(context);
    if (scan != nullptr && entity != 0) {
        std::int64_t filter = 0;
        if (isaac::runtime::ClassifyCallbackEntity(entity, &filter) ==
            isaac::runtime::CallbackEntityClass::Player) {
            DispatchPlayerInitialization(scan, entity, filter);
        }
    }
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

void DispatchFrameEvents(bool initialOnly = false) {
    const RegisteredCallbackMask registered = BuildRegisteredCallbackMask();
    const bool wantsEntityScan = AnyEntityFamilyRegistered(registered);
    const bool wantsRoom = registered.Has(isaac::runtime::kCallbackPostNewRoom);
    const bool wantsLevel = registered.Has(isaac::runtime::kCallbackPostNewLevel);
    // 一种都没登记就整段跳过：这条路径每帧都要读房间身份，有实体时还要扫实体表，
    // "没人听"的时候一律不做（不白花每帧的引擎读取与 `svcQueryMemory`）。
    if (!initialOnly && !wantsEntityScan && !wantsRoom && !wantsLevel) {
        return;
    }

    GameLocationKey location{};
    const bool haveLocation =
        ReadGameLocationKey(GameOwnerSlot(), &location) == GameRoomObservation::Success;
    if (!haveLocation) {
        // 瞬时读失败只跳过本帧，不遗忘最后一次成功身份；否则换层期间一次失败
        // 会让新层被当作中途加载，吞掉NEW_LEVEL/NEW_ROOM。新局已有显式复位。
    }

    bool enteredNewRoom = false;
    bool enteredNewLevel = false;
    // 真实下层时stage先变，房间数组仍属于旧层；不消费这段过渡身份。
    // 初始开局由Game::Start返回后的现有流程处理；普通同层路径不读取完成标记。
    if (haveLocation &&
        (g_FrameEventState.levelKnown == 0 || location.SameLevel(g_FrameEventState.location) ||
         isaac::runtime::NativeLoadedLevelMatches(location.stage, location.stageType))) {
        const auto roomLoadGeneration = isaac::runtime::NativeRoomLoadGeneration();
        // 判定抽到 `frame_event_decision.hpp`（纯函数、宿主上逐条验）：三条口径 ——
        // 开局起始房间补一次、读不到身份时不判也不消费、中途加载时不拿残值当身份。
        const isaac::runtime::FrameRoomDecision decision =
            isaac::runtime::DecideFrameRoomEvents(
            true, g_FrameEventState.roomKnown != 0, g_FrameEventState.levelKnown != 0,
            location.stage == g_FrameEventState.location.stage &&
                location.stageType == g_FrameEventState.location.stageType,
            location.SameRoom(g_FrameEventState.location) &&
                roomLoadGeneration == g_FrameEventState.roomLoadGeneration,
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
        // ★ 2026-10-14 更正：上述 NEW_LEVEL/NEW_ROOM 顺序是历史误记，实际应先 NEW_ROOM 再 NEW_LEVEL。
        // 现在的口径：**开局那一间房补派一次**（由 `initialRoomPending` 驱动，见上面派发处）；
        // 只有"运行时在该层中途才加载"（没有 `initialRoomPending`）时才不判变化。
        g_FrameEventState.location = location;
        // Consume before callbacks, so a load triggered by a callback remains pending.
        g_FrameEventState.roomLoadGeneration = roomLoadGeneration;
        g_FrameEventState.roomKnown = 1;
        g_FrameEventState.levelKnown = 1;
    }

    // 先扫实体与玩家，再派发"换房/换层"。顺序是照 PC 的观感定的：换层时模组先收到
    // `POST_NEW_LEVEL`、再收到 `POST_NEW_ROOM`，而实体的 INIT/UPDATE 属于"新房间已经在了"
    // 之后的事 —— 放在前面会让模组在一个它还不认识的房间里收到实体事件。
    if (wantsEntityScan && !initialOnly) {
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
    // ★ 2026-10-14 更正：上面的历史顺序注释写反了；PC 官方明确 NEW_LEVEL 总在 NEW_ROOM 之后。
    // MinimapAPI 在 NEW_ROOM 刷新 cache.RoomDescriptor/Stage，NEW_LEVEL 重建地图并读取这些缓存；
    // 因此必须先换房再换层，避免换层地图仍读到上一层。实体扫描与 GAME_STARTED 顺序不改。
    if (enteredNewRoom) {
        LuaCallbackInvoker invoker{0, false, false};
        isaac::runtime::CallbackDispatcher dispatcher{g_CallbackRegistry, invoker};
        static_cast<void>(dispatcher.Dispatch(isaac::runtime::kCallbackPostNewRoom,
                                              isaac::runtime::ThreadAffinity::Any));
    }
    if (enteredNewLevel) {
        LuaCallbackInvoker invoker{0, false, false};
        isaac::runtime::CallbackDispatcher dispatcher{g_CallbackRegistry, invoker};
        static_cast<void>(dispatcher.Dispatch(isaac::runtime::kCallbackPostNewLevel,
                                              isaac::runtime::ThreadAffinity::Any));
    }
}

void DispatchPostUpdate() {
    if (!IsReady() || g_LuaState == nullptr) return;
    const ManagedEngineDispatchScope dispatchScope;
    if (isaac::runtime::console::ConsolePaused() ||
        !isaac::runtime::ShouldDispatchManagedCallbacks()) return;
    // 2026-10-16更正：PC在PLAYER_INIT、NEW_ROOM、NEW_LEVEL之后才发GAME_STARTED。
    // 旧顺序原文保存在callback-order-fix/lua_runtime.cpp.before，不能再让作者自行补初始化。
    if (const std::uint32_t pending = g_PendingGameStarted.load(std::memory_order_acquire);
        pending != 0) {
        if (g_FrameEventState.preparedGameStartKind != pending) {
            ResetLevelStartRoomTracker();
            g_FrameEventState.roomKnown = 0;
            g_FrameEventState.levelKnown = 0;
            g_FrameEventState.initialRoomPending = 1;
            g_FrameEventState.seenPlayerCount = 0;
            g_FrameEventState.preparedGameStartKind = pending;
        }
        EntityEventScan initialPlayers{};
        initialPlayers.registered = BuildRegisteredCallbackMask();
        if (initialPlayers.registered.Has(isaac::runtime::kCallbackPostPlayerInit)) {
            isaac::runtime::VisitPlayerEntities(&OnInitialPlayerEvent, &initialPlayers);
            if (g_FrameEventState.seenPlayerCount == 0) {
                return;
            }
        }
        DispatchFrameEvents(true);
        const bool initialRoomReady = g_FrameEventState.initialRoomPending == 0;
        if (!initialRoomReady || !DispatchPostGameStarted(pending == kGameStartedFromSave)) {
            return;
        }
        g_PendingGameStarted.store(0, std::memory_order_release);
        g_FrameEventState.preparedGameStartKind = 0;
    }
    // 一次性初始化保持原次序；普通更新只认领当前Game的一个原生simulation帧。
    isaac::runtime::ManagedUpdateSnapshot snapshot{};
    if (!isaac::runtime::ShouldDispatchManagedUpdates(&snapshot)) return;
    if (snapshot.game != 0) {
        if (g_HasManagedUpdate && snapshot.game == g_LastManagedUpdate.game &&
            snapshot.frame == g_LastManagedUpdate.frame) return;
        // 进入任何Lua前认领；同步重入不能再次派发同一帧。
        g_LastManagedUpdate = snapshot;
        g_HasManagedUpdate = true;
    }
    // 新房间的初始化必须先于它的第一次POST_UPDATE；否则模组仍拿上一房间的
    // 追踪状态处理新房间。复用本帧已有扫描，且在认领simulation帧后才允许Lua重入。
    DispatchFrameEvents();
    if (isaac::runtime::BuiltinCallbackEnabled(isaac::runtime::kCallbackPostUpdate)) {
        LuaCallbackInvoker invoker{0, false, true};
        isaac::runtime::CallbackDispatcher dispatcher{g_CallbackRegistry, invoker};
        static_cast<void>(dispatcher.Dispatch(isaac::runtime::kCallbackPostUpdate,
                                              isaac::runtime::ThreadAffinity::Any));
    }
}

void DispatchNativePlayerInit(std::uintptr_t player) noexcept {
    if (!IsReady() || g_LuaState == nullptr || player == 0) return;
    const ManagedEngineDispatchScope dispatchScope;
    std::int64_t variant{};
    if (isaac::runtime::ClassifyCallbackEntity(player, &variant) !=
        isaac::runtime::CallbackEntityClass::Player) return;
    g_NativePlayerInitObserved = true;
    if (!isaac::runtime::BuiltinCallbackEnabled(isaac::runtime::kCallbackPostPlayerInit)) return;
    // 每次真正Init都是新生命周期；同地址重建不能靠旧指针集合去重。
    LuaCallbackInvoker invoker = LuaCallbackInvoker::ForEntity(player);
    isaac::runtime::CallbackDispatcher dispatcher{g_CallbackRegistry, invoker};
    static_cast<void>(dispatcher.DispatchFiltered(isaac::runtime::kCallbackPostPlayerInit,
                                                   isaac::runtime::ThreadAffinity::Any, variant));
}

// load_room can finish on a transition frame that renders before the next
// simulation update. Publish its room/level events before either HUD consumer,
// or mods write the destination's pickups into their cached previous room.
bool PrepareRoomEventsForRender() {
    if (g_PendingGameStarted.load(std::memory_order_acquire) != 0 ||
        g_FrameEventState.roomKnown == 0 ||
        isaac::runtime::NativeRoomLoadGeneration() == g_FrameEventState.roomLoadGeneration) {
        return true;
    }
    const ManagedEngineDispatchScope dispatchScope;
    DispatchFrameEvents(true); // Room lifecycle only; never synthesize entity updates in render.
    // A failed read, incomplete new level, or another load inside a callback
    // must retry before any renderer consumes the still-stale room cache.
    return isaac::runtime::NativeRoomLoadGeneration() == g_FrameEventState.roomLoadGeneration;
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
        isaac::runtime::BuiltinCallbackEnabled(isaac::runtime::kCallbackPostRender);
    const RegisteredCallbackMask registered = BuildRegisteredCallbackMask();
    if (!wantsPostRender && !AnyEntityRenderFamilyRegistered(registered)) {
        return;
    }
    if (!PrepareRoomEventsForRender()) return;
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
    // 主菜单关闭游戏也会走系统退出入口。重载后未进局的 VM 只有默认配置，
    // 此时派发会让 EID 等模组把默认值覆盖到原有存档。
    if (!IsReady() || g_LuaState == nullptr || !g_GameStartedInCurrentVm) {
        return;
    }
    if (!isaac::runtime::BuiltinCallbackEnabled(isaac::runtime::kCallbackPreGameExit)) {
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
    if (!isaac::runtime::BuiltinCallbackEnabled(isaac::runtime::kCallbackPreUseItem)) {
        return false;
    }
    isaac::runtime::EngineGuardEnterDispatch();
    LuaCallbackInvoker invoker{0, false, false};
    // PC 签名：`(CollectibleType, RNG, EntityPlayer, UseFlags, ActiveSlot, CustomVarData)`。
    // RNG与GetCollectibleRNG共享原生状态，保留玩家/容器失效检查。
    invoker.arguments.AddInteger(collectibleType);
    invoker.arguments.AddCollectibleRng(player,collectibleType);
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

namespace {
struct UseItemResultContext {
    LuaCallbackInvoker* invoker;
    isaac::runtime::UseItemCallbackResult result{};
    std::uintptr_t player{};std::int32_t item{},flags{};
    bool nativeBoundary{},animationAllowed{true};std::uint64_t nativeResult{};
};
int CollectUseItemResult(lua_State* state){
    auto* context=static_cast<UseItemResultContext*>(lua_touserdata(state,1));
    lua_pushnil(state);context->invoker->tableStackIndex=2;
    isaac::runtime::CallbackDispatcher dispatcher{g_CallbackRegistry,*context->invoker};
    const auto outcome=dispatcher.DispatchModifying(isaac::runtime::kCallbackUseItem,
        isaac::runtime::ThreadAffinity::Any,context->item);
    context->invoker->tableStackIndex=0;
    if(outcome.hasTable){
        g_ErrorContextOwner=context->invoker->tableOwner;
        lua_getfield(state,2,"Discharge");
        if(!lua_isnil(state,-1)){context->result.hasDischarge=true;context->result.discharge=lua_toboolean(state,-1)!=0;}
        lua_pop(state,1);
        lua_getfield(state,2,"Remove");
        if(!lua_isnil(state,-1)){context->result.hasRemove=true;context->result.remove=lua_toboolean(state,-1)!=0;}
        lua_pop(state,1);
        lua_getfield(state,2,"ShowAnim");context->result.showAnimation=lua_toboolean(state,-1)!=0;lua_pop(state,1);
    }else context->result.showAnimation=outcome.anyTruthy;
    if(context->result.showAnimation&&!(context->flags&1)&&context->animationAllowed)
        isaac::runtime::ApplyUseItemCallbackAnimation(state,context->player,context->item);
    if(context->nativeBoundary&&(context->flags&64)&&(context->result.Apply(context->nativeResult)&0x100U)){
        isaac::runtime::ApplyUseItemNativeRemoval(state,context->player,context->item);
        context->result.hasRemove=true;context->result.remove=false;
    }
    return 0;
}
}
static isaac::runtime::UseItemCallbackResult DispatchUseItemImpl(std::uintptr_t player, std::int32_t collectibleType,
    std::int32_t useFlags,std::int32_t activeSlot,std::int32_t customVarData,
    bool nativeBoundary,std::uint64_t nativeResult,bool animationAllowed){
    if(!IsReady()||!g_LuaState||!isaac::runtime::ShouldDispatchManagedCallbacks()||
       (!isaac::runtime::BuiltinCallbackEnabled(isaac::runtime::kCallbackUseItem)&&
        !(nativeBoundary&&(useFlags&64)&&(nativeResult&0x100U))))return {};
    if(!lua_checkstack(g_LuaState,4)){g_CallbackError.store(true,std::memory_order_release);return {};}
    isaac::runtime::EngineGuardEnterDispatch();
    LuaCallbackInvoker invoker{0,false,false};
    invoker.arguments.AddInteger(collectibleType);invoker.arguments.AddCollectibleRng(player,collectibleType);
    AddPlayerArgument(&invoker.arguments,player);invoker.arguments.AddInteger(useFlags);
    invoker.arguments.AddInteger(activeSlot);invoker.arguments.AddInteger(customVarData);
    UseItemResultContext context{&invoker,{},player,collectibleType,useFlags,nativeBoundary,animationAllowed,nativeResult};
    const int top=lua_gettop(g_LuaState);const auto owner=g_ErrorContextOwner;
    lua_pushcfunction(g_LuaState,CollectUseItemResult);lua_pushlightuserdata(g_LuaState,&context);
    if(lua_pcall(g_LuaState,1,0,0)!=LUA_OK){CaptureLuaErrorTop(g_LuaState);g_CallbackError.store(true,std::memory_order_release);}
    lua_settop(g_LuaState,top);g_ErrorContextOwner=owner;
    isaac::runtime::EngineGuardLeaveDispatch();return context.result;
}

isaac::runtime::UseItemCallbackResult DispatchUseItem(std::uintptr_t player,std::int32_t item,
    std::int32_t flags,std::int32_t slot,std::int32_t custom){
    return DispatchUseItemImpl(player,item,flags,slot,custom,false,0,true);
}
isaac::runtime::UseItemCallbackResult DispatchUseItemAtNativeBoundary(std::uintptr_t player,std::int32_t item,
    std::int32_t flags,std::int32_t slot,std::int32_t custom,std::uint64_t nativeResult,bool animationAllowed){
    return DispatchUseItemImpl(player,item,flags,slot,custom,true,nativeResult,animationAllowed);
}

void DispatchUseCard(std::uintptr_t player, std::int32_t card, std::int32_t useFlags) {
    if (!IsReady() || g_LuaState == nullptr ||
        !isaac::runtime::ShouldDispatchManagedCallbacks()) {
        return;
    }
    if (!isaac::runtime::BuiltinCallbackEnabled(isaac::runtime::kCallbackUseCard)) {
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
    if (!isaac::runtime::BuiltinCallbackEnabled(isaac::runtime::kCallbackUsePill)) {
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

CollisionOverride DispatchPreEntityCollision(std::uint32_t callbackId, std::uintptr_t pickup,
    std::uintptr_t collider, bool low, std::int32_t pickupVariant) {
    if (!IsReady() || g_LuaState == nullptr ||
        !isaac::runtime::ShouldDispatchManagedCallbacks()) {
        return CollisionOverride::Continue;
    }
    if (!isaac::runtime::BuiltinCallbackEnabled(callbackId)) {
        return CollisionOverride::Continue;
    }
    isaac::runtime::EngineGuardEnterDispatch();
    LuaCallbackInvoker invoker{0, false, false};
    // PC 签名：`(EntityPickup, Collider [Entity], Low [bool])`。
    // 两个实参都是实体视图（EID 的处理器读 `collider.Type` 判"是玩家/跟班还是别的"）。
    invoker.arguments.AddEntity(pickup);
    invoker.arguments.AddEntity(collider);
    invoker.arguments.AddBoolean(low);
    isaac::runtime::CallbackDispatcher dispatcher{g_CallbackRegistry, invoker};
    // 过滤值 = **掉落物的变体**：PC 给这条回调的可选实参类型是 `PickupVariant`（而第一个实参是
    // 实体、不是数字，所以过滤值必须由调用点从实体上读出来并单独传进来 —— 见
    // `CallbackDispatchOutcome` 的说明）。反汇编也印证了这个字段：
    // `handle_collision` 开头就是 `ldr w8, [x0, #0x3C]; cmp w8, #0x64`（变体 100 = 可拾取物）。
    const isaac::runtime::CallbackDispatchOutcome outcome =
        dispatcher.DispatchModifying(callbackId,
                                     isaac::runtime::ThreadAffinity::Any,
                                     static_cast<std::int64_t>(pickupVariant));
    isaac::runtime::EngineGuardLeaveDispatch();
    // PC 的三态里 `true`（忽略碰撞）与 `false`（算碰撞但不执行内部代码）**都不执行**内部代码，
    // 只有 `nil` 才照常执行 ⇒ 判据是"**非 nil**"而不是"真值"。
    return !outcome.anyNonNil ? CollisionOverride::Continue :
           outcome.anyTruthy ? CollisionOverride::Ignore : CollisionOverride::Collide;
}

// 历史布尔接口仅表示是否跳过原生内部代码；实际入口中继必须使用上面的三态。
bool DispatchPrePickupCollision(std::uintptr_t pickup, std::uintptr_t collider, bool low,
                                std::int32_t pickupVariant) {
    return DispatchPreEntityCollision(isaac::runtime::kCallbackPrePickupCollision, pickup,
        collider, low, pickupVariant) != CollisionOverride::Continue;
}

static void DispatchProjectileNativeEvent(std::uint32_t id,std::uintptr_t projectile) {
    if (!IsReady() || g_LuaState == nullptr || !isaac::runtime::BuiltinCallbackEnabled(id) ||
        !isaac::runtime::ShouldDispatchManagedCallbacks()) return;
    std::uint32_t type{},variant{};
    if (!isaac::runtime::ReadEntityIdentity(projectile,&type,&variant) || type!=9) return;
    isaac::runtime::EngineGuardEnterDispatch();
    auto invoker=LuaCallbackInvoker::ForEntity(projectile);
    isaac::runtime::CallbackDispatcher dispatcher{g_CallbackRegistry,invoker};
    static_cast<void>(dispatcher.DispatchFiltered(id,
        isaac::runtime::ThreadAffinity::Any,variant));
    isaac::runtime::EngineGuardLeaveDispatch();
}

void DispatchPostProjectileInit(std::uintptr_t projectile) {
    DispatchProjectileNativeEvent(isaac::runtime::kCallbackPostProjectileInit,projectile);
}
void DispatchPostProjectileUpdate(std::uintptr_t projectile) {
    DispatchProjectileNativeEvent(isaac::runtime::kCallbackPostProjectileUpdate,projectile);
}

void DispatchPostManualEntityUpdate(std::uintptr_t entity) {
    if (!IsReady() || g_LuaState == nullptr ||
        !isaac::runtime::ShouldDispatchManagedCallbacks()) return;
    std::int64_t filter{};
    isaac::runtime::CallbackId id{};
    switch (isaac::runtime::ClassifyCallbackEntity(entity, &filter)) {
        case isaac::runtime::CallbackEntityClass::Player:
            id = isaac::runtime::kCallbackPostPlayerUpdate; break;
        case isaac::runtime::CallbackEntityClass::Npc:
            id = isaac::runtime::kCallbackNpcUpdate; break;
        case isaac::runtime::CallbackEntityClass::Familiar:
            id = isaac::runtime::kCallbackFamiliarUpdate; break;
        case isaac::runtime::CallbackEntityClass::Pickup:
            id = isaac::runtime::kCallbackPostPickupUpdate; break;
        case isaac::runtime::CallbackEntityClass::Tear:
            id = isaac::runtime::kCallbackPostTearUpdate; break;
        case isaac::runtime::CallbackEntityClass::Laser:
            id = isaac::runtime::kCallbackPostLaserUpdate; break;
        case isaac::runtime::CallbackEntityClass::Knife:
            id = isaac::runtime::kCallbackPostKnifeUpdate; break;
        case isaac::runtime::CallbackEntityClass::Effect:
            id = isaac::runtime::kCallbackPostEffectUpdate; break;
        case isaac::runtime::CallbackEntityClass::Bomb:
            id = isaac::runtime::kCallbackPostBombUpdate; break;
        // Projectile.Update has a native completion relay. Slot6 has no standard
        // post-update callback. Neither may be fed into another entity family.
        case isaac::runtime::CallbackEntityClass::Projectile:
        case isaac::runtime::CallbackEntityClass::None:
            return;
    }
    if (!isaac::runtime::BuiltinCallbackEnabled(id)) return;
    // Per explicit call, independent of simulation-frame dedup. Bounded recursive
    // updates in an author's callback are real updates too; do not suppress them.
    const ManagedEngineDispatchScope dispatchScope;
    auto invoker = LuaCallbackInvoker::ForEntity(entity);
    isaac::runtime::CallbackDispatcher dispatcher{g_CallbackRegistry, invoker};
    static_cast<void>(dispatcher.DispatchFiltered(id, isaac::runtime::ThreadAffinity::Any, filter));
}

void DispatchPostNpcRender(std::uintptr_t npc, const void* renderOffset) {
    if (!IsReady() || g_LuaState == nullptr || !isaac::runtime::ShouldDispatchManagedCallbacks() ||
        !isaac::runtime::BuiltinCallbackEnabled(isaac::runtime::kCallbackPostNpcRender)) return;
    std::uint32_t type = 0, variant = 0;
    if (!isaac::runtime::ReadEntityIdentity(npc, &type, &variant) || renderOffset == nullptr ||
        !isaac::runtime::engine_memory::EngineMemoryReadable(isaac::runtime::engine_memory::AddressOf(renderOffset), 2 * sizeof(float))) return;
    float offset[2];
    std::memcpy(offset, renderOffset, sizeof(offset));
    isaac::runtime::EngineGuardEnterDispatch();
    auto invoker = LuaCallbackInvoker::ForEntityWithVector(npc, offset[0], offset[1]);
    isaac::runtime::CallbackDispatcher dispatcher{g_CallbackRegistry, invoker};
    static_cast<void>(dispatcher.DispatchFiltered(isaac::runtime::kCallbackPostNpcRender,
        isaac::runtime::ThreadAffinity::Any, type));
    isaac::runtime::EngineGuardLeaveDispatch();
}

void DispatchPreRoomEntitySpawn(std::int32_t entityType, std::int32_t variant,
                                std::int32_t subType, std::int32_t gridIndex,
                                std::int32_t seed) {
    // 保留旧宿主/诊断调用入口；生产内部挂点使用有返回值的接口。
    static_cast<void>(DispatchPreRoomEntitySpawnModifying(entityType,
        static_cast<std::uint16_t>(variant), static_cast<std::uint16_t>(subType),
        static_cast<std::uint32_t>(gridIndex), static_cast<std::uint32_t>(seed)));
}

// 批次 396（2026-10-07）：`MC_ENTITY_TAKE_DMG`(11)。
// 四条入口中继（基类 + 玩家/掉落物/槽位）共用这一个派发函数。
//
// 返回值：**true = 不要跑原函数**（模组要求取消这次伤害）。PC 契约原文
// （`ModCallbacks.md:318`）：「Return true or nil if the entity or player should sustain the
// damage, otherwise false to ignore it.」⇒ 只有**返回 `false`** 才取消。
// ★ Lua 里 **`0` 是 truthy** ⇒ "有人返回过非 nil（`anyNonNil`）且没有真值（`!anyTruthy`）"
//   恰好等价于"有人返回了 `false`"，不必单独开一个字段。
// 已知偏离：我们的派发器**不短路**（PC 会停在第一个非 nil），所以"一个返回 true、另一个返回
// false"时我们按"照常受伤"处理；这与项目里 `MC_INPUT_ACTION` 那处已知偏离同源。
// 2026-10-09更正上方历史偏离：受伤现在首个非nil短路；Input PC文档明确继续执行，不能类比。
bool DispatchEntityTakeDamage(std::uintptr_t entity, float amount, std::int32_t damageFlags,
                              std::uintptr_t sourceRef, std::int32_t countdownFrames,
                              std::int32_t entityType) {
    if (!IsReady() || g_LuaState == nullptr ||
        !isaac::runtime::ShouldDispatchManagedCallbacks()) {
        return false;
    }
    if (!isaac::runtime::BuiltinCallbackEnabled(isaac::runtime::kCallbackEntityTakeDmg)) {
        return false;
    }
    isaac::runtime::EngineGuardEnterDispatch();
    LuaCallbackInvoker invoker{0, false, false};
    // PC 签名：`(Entity, Amount [float], DamageFlags [int], Source [EntityRef], CountdownFrames [int])`。
    invoker.arguments.AddEntity(entity);
    invoker.arguments.AddFloat(amount);
    invoker.arguments.AddInteger(static_cast<std::int64_t>(damageFlags));
    invoker.arguments.AddReference(sourceRef);
    invoker.arguments.AddInteger(static_cast<std::int64_t>(countdownFrames));
    isaac::runtime::CallbackDispatcher dispatcher{g_CallbackRegistry, invoker};
    // 过滤值 = 实体的 `EntityType`（PC 给这条回调的可选实参类型就是 `EntityType`；
    // 语料里 Trinity 的五个处理器全带 `EntityType.ENTITY_PLAYER` ⇒ 过滤必须真给）。
    const isaac::runtime::CallbackDispatchOutcome outcome =
        dispatcher.DispatchModifying(isaac::runtime::kCallbackEntityTakeDmg,
                                     isaac::runtime::ThreadAffinity::Any,
                                     static_cast<std::int64_t>(entityType));
    isaac::runtime::EngineGuardLeaveDispatch();
    return outcome.anyNonNil && !outcome.anyTruthy;
}

// 批次 396（2026-10-07）：`MC_EVALUATE_CACHE`(8)。过滤器 = 本次要重算的那个 CacheFlag 位。
// 调用点（`EntryRelayEvaluateItemsCallback`）负责把入口快照的掩码逐位拆开、一位调一次。
void DispatchEvaluateCache(std::uintptr_t player, std::int32_t cacheFlag) {
    if (!IsReady() || g_LuaState == nullptr ||
        !isaac::runtime::ShouldDispatchManagedCallbacks()) {
        return;
    }
    if (!isaac::runtime::BuiltinCallbackEnabled(isaac::runtime::kCallbackEvaluateCache)) {
        return;
    }
    isaac::runtime::EngineGuardEnterDispatch();
    LuaCallbackInvoker invoker{0, false, false};
    AddPlayerArgument(&invoker.arguments, player);
    invoker.arguments.AddInteger(static_cast<std::int64_t>(cacheFlag));
    isaac::runtime::CallbackDispatcher dispatcher{g_CallbackRegistry, invoker};
    static_cast<void>(dispatcher.DispatchFiltered(isaac::runtime::kCallbackEvaluateCache,
                                                  isaac::runtime::ThreadAffinity::Any,
                                                  static_cast<std::int64_t>(cacheFlag)));
    isaac::runtime::EngineGuardLeaveDispatch();
}

// 批次 397（2026-10-07）：`MC_POST_ENTITY_KILL`(68)。
// 契约原文（`ModCallbacks.md`）：「Called right before a death animation is triggered for an
// Entity.」实参 `(Entity)`，可选实参（过滤器）= `EntityType`，返回 void（返回值无效果）。
// 调用点（`EntryRelayEntityKillCallback`）在**入口**派发 —— 那正好是"死亡动画被触发之前"。
void DispatchPostEntityKill(std::uintptr_t entity, std::int32_t entityType) {
    // ★ 重入守卫（`g_InPostEntityKillDispatch` 的说明在上面的声明处）：模组在自己这条回调里
    //   又调 `entity:Kill()` 时**跳过派发**（不跳过原函数 —— 那由调用点照常做）。
    if (!IsReady() || g_InPostEntityKillDispatch || g_LuaState == nullptr ||
        !isaac::runtime::ShouldDispatchManagedCallbacks()) {
        return;
    }
    if (!isaac::runtime::BuiltinCallbackEnabled(isaac::runtime::kCallbackPostEntityKill)) {
        return;
    }
    isaac::runtime::EngineGuardEnterDispatch();
    g_InPostEntityKillDispatch = true;
    LuaCallbackInvoker invoker = LuaCallbackInvoker::ForEntity(entity);
    isaac::runtime::CallbackDispatcher dispatcher{g_CallbackRegistry, invoker};
    static_cast<void>(dispatcher.DispatchFiltered(isaac::runtime::kCallbackPostEntityKill,
                                                  isaac::runtime::ThreadAffinity::Any,
                                                  static_cast<std::int64_t>(entityType)));
    g_InPostEntityKillDispatch = false;
    isaac::runtime::EngineGuardLeaveDispatch();
}

// 批次 397（2026-10-07）：`MC_POST_NPC_DEATH`(29)。
// 契约原文：「Gets called **after the Death animation is played**.」实参 `(EntityNPC)`，
// 过滤器 = `EntityType`，返回 void。调用点 = `Entity_NPC::trigger_death_remove()` 的入口
// （就是"动画播完之后"那个汇合点；在入口派发是为了**赶在它把 NPC 掉落/移除之前**拿到指针）。
void DispatchPostNpcDeath(std::uintptr_t npc, std::int32_t entityType) {
    if (!IsReady() || g_LuaState == nullptr ||
        !isaac::runtime::ShouldDispatchManagedCallbacks()) {
        return;
    }
    if (!isaac::runtime::BuiltinCallbackEnabled(isaac::runtime::kCallbackPostNpcDeath)) {
        return;
    }
    isaac::runtime::EngineGuardEnterDispatch();
    LuaCallbackInvoker invoker = LuaCallbackInvoker::ForEntity(npc);
    isaac::runtime::CallbackDispatcher dispatcher{g_CallbackRegistry, invoker};
    static_cast<void>(dispatcher.DispatchFiltered(isaac::runtime::kCallbackPostNpcDeath,
                                                  isaac::runtime::ThreadAffinity::Any,
                                                  static_cast<std::int64_t>(entityType)));
    isaac::runtime::EngineGuardLeaveDispatch();
}

// 批次 397（2026-10-07）：`MC_POST_GAME_END`(16)。
// 契约原文：「called when the game over screen appears, or when an ending starts playing.
// The boolean value is **true when you died and got a game over**, false when you won and got
// an ending.」实参 `(bool IsGameOver)`，可选实参 `-`（无过滤），返回 void。
// ★ 必须压 **布尔**（`ForBoolean`）而不是整数：Lua 里 **`0` 是 truthy** ⇒ 压整数会让
//   "打赢了"（false）被模组当成"死了"（批次 388-fix 在同一类问题上栽过一次）。
void DispatchPostGameEnd(bool isGameOver) {
    if (!IsReady() || g_LuaState == nullptr ||
        !isaac::runtime::ShouldDispatchManagedCallbacks()) {
        return;
    }
    if (!isaac::runtime::BuiltinCallbackEnabled(isaac::runtime::kCallbackPostGameEnd)) {
        return;
    }
    isaac::runtime::EngineGuardEnterDispatch();
    LuaCallbackInvoker invoker = LuaCallbackInvoker::ForBoolean(isGameOver);
    isaac::runtime::CallbackDispatcher dispatcher{g_CallbackRegistry, invoker};
    static_cast<void>(dispatcher.Dispatch(isaac::runtime::kCallbackPostGameEnd,
                                          isaac::runtime::ThreadAffinity::Any));
    isaac::runtime::EngineGuardLeaveDispatch();
}

// 批次 397（2026-10-07）：`MC_POST_FIRE_TEAR`(61)。
// 契约原文：「Called when the player fires a tear. … In Repentance, it works for tears fired
// with Incubus.」实参 `(EntityTear)`，可选实参 `-`（无过滤），返回 void。
// 调用点（`EntryRelayFireTearCallback`）在**原函数返回之后**派发 —— 泪弹是它的返回值。
void DispatchPostFireTear(std::uintptr_t tear) {
    if (!IsReady() || g_LuaState == nullptr ||
        !isaac::runtime::ShouldDispatchManagedCallbacks()) {
        return;
    }
    if (!isaac::runtime::BuiltinCallbackEnabled(isaac::runtime::kCallbackPostFireTear)) {
        return;
    }
    isaac::runtime::EngineGuardEnterDispatch();
    LuaCallbackInvoker invoker = LuaCallbackInvoker::ForEntity(tear);
    isaac::runtime::CallbackDispatcher dispatcher{g_CallbackRegistry, invoker};
    static_cast<void>(dispatcher.Dispatch(isaac::runtime::kCallbackPostFireTear,
                                          isaac::runtime::ThreadAffinity::Any));
    isaac::runtime::EngineGuardLeaveDispatch();
}

// 批次 396（2026-10-07）：`MC_ENTITY_TAKE_DMG`(11)。
// 四条入口中继（基类 + 玩家/掉落物/槽位）共用这一个派发函数。
//
// 返回值：**true = 不要跑原函数**（模组要求取消这次伤害）。PC 契约原文
// （`ModCallbacks.md:318`）：「Return true or nil if the entity or player should sustain the
// damage, otherwise false to ignore it.」⇒ 只有**返回 `false`** 才取消。
// ★ Lua 里 **`0` 是 truthy** ⇒ "有人返回过非 nil（`anyNonNil`）且没有真值（`!anyTruthy`）"
//   恰好等价于"有人返回了 `false`"，不必单独开一个字段。
// 已知偏离：我们的派发器**不短路**（PC 会停在第一个非 nil），所以"一个返回 true、另一个返回
// false"时我们按"照常受伤"处理；这与项目里 `MC_INPUT_ACTION` 那处已知偏离同源。


// 批次 396（2026-10-07）：`MC_EVALUATE_CACHE`(8)。过滤器 = 本次要重算的那个 CacheFlag 位。
// 调用点（`EntryRelayEvaluateItemsCallback`）负责把入口快照的掩码逐位拆开、一位调一次。


// 批次 397（2026-10-07）：`MC_POST_ENTITY_KILL`(68)。
// 契约原文（`ModCallbacks.md`）：「Called right before a death animation is triggered for an
// Entity.」实参 `(Entity)`，可选实参（过滤器）= `EntityType`，返回 void（返回值无效果）。
// 调用点（`EntryRelayEntityKillCallback`）在**入口**派发 —— 那正好是"死亡动画被触发之前"。


// 批次 397（2026-10-07）：`MC_POST_NPC_DEATH`(29)。
// 契约原文：「Gets called **after the Death animation is played**.」实参 `(EntityNPC)`，
// 过滤器 = `EntityType`，返回 void。调用点 = `Entity_NPC::trigger_death_remove()` 的入口
// （就是"动画播完之后"那个汇合点；在入口派发是为了**赶在它把 NPC 掉落/移除之前**拿到指针）。


// 批次 397（2026-10-07）：`MC_POST_GAME_END`(16)。
// 契约原文：「called when the game over screen appears, or when an ending starts playing.
// The boolean value is **true when you died and got a game over**, false when you won and got
// an ending.」实参 `(bool IsGameOver)`，可选实参 `-`（无过滤），返回 void。
// ★ 必须压 **布尔**（`ForBoolean`）而不是整数：Lua 里 **`0` 是 truthy** ⇒ 压整数会让
//   "打赢了"（false）被模组当成"死了"（批次 388-fix 在同一类问题上栽过一次）。


// 批次 397（2026-10-07）：`MC_POST_FIRE_TEAR`(61)。
// 契约原文：「Called when the player fires a tear. … In Repentance, it works for tears fired
// with Incubus.」实参 `(EntityTear)`，可选实参 `-`（无过滤），返回 void。
// 调用点（`EntryRelayFireTearCallback`）在**原函数返回之后**派发 —— 泪弹是它的返回值。


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
    if (!isaac::runtime::BuiltinCallbackEnabled(isaac::runtime::kCallbackPostGetCollectible)) {
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
    // PC POST直接取luaL_checkinteger的低32位，包含零；没有额外人为域夹限。
    if (!outcome.hasInteger) return 0;
    return (std::uint64_t{1} << 32) | static_cast<std::uint32_t>(outcome.integer);
}

// 批次 392（2026-10-07）：直读标记与"直读壳"都定义在本文件上部（挨着三条取值助手），
// 见那里的说明 —— 这条派发函数只是它的消费者之一：中继看到标记就**跳过这里**、直接调原函数。
// 批次 390（2026-10-07）：`MC_INPUT_ACTION`。契约见 `lua_runtime.hpp` 的 `InputActionOutcome`。
//
// ★★ 性能是这条的主要约束：`IsActionPressed` 每秒被引擎问约 1470 次（官方"执行信息栏"），
//   所以**没有模组登记时必须一个 Lua 调用都不做** —— 那一步（`CountOf == 0`）就在最前面。
// ★ 重入：模组在回调里再问输入（minimapi 就调 `Input.IsActionPressed`）时，内层不再派发。
//   ★★ 批次 392 更正（2026-10-07）：这句原来写的是"我们的 `Input.*` **不走**引擎这条查询
//   （契约也要求覆盖不影响 Lua 读取）"——**那是错的**，反汇编已证伪：Lua 的 `Input.*` 绑的
//   `0x3F9B6C` 正是尾跳进本中继的靶点（`ManagerBase::IsAction*`）⇒ 当时我们的读取**确实**会被
//   覆盖（MCM 光标被冻住就是这么来的）。现在这两道防线是：① 我们这侧一律套
//   `RawEngineInputQueryScope`（中继见标记直接走原函数，见 `hook_manager.cpp` 那三个壳）；
//   ② 下面这道重入守卫只管"派发正在进行中"这一种情形（例如模组的处理器里再问输入）。
InputActionOutcome DispatchInputAction(std::uint32_t action, std::uint32_t controllerIndex,
                                       std::int32_t inputHook, std::uintptr_t entity) {
    InputActionOutcome outcome{};
    static_cast<void>(controllerIndex);  // PC回调不暴露此参数，真实Entity由原生独立提供。
    if (!IsReady() || g_LuaState == nullptr ||
        !isaac::runtime::ShouldDispatchManagedCallbacks()) {
        return outcome;
    }
    if (!isaac::runtime::BuiltinCallbackEnabled(isaac::runtime::kCallbackInputAction)) {
        return outcome;  // ★ 快路径（绝大多数帧走这里）
    }
    static bool inInputActionDispatch = false;
    if (inInputActionDispatch) {
        return outcome;
    }
    isaac::runtime::EngineGuardEnterDispatch();
    LuaCallbackInvoker invoker{0, false, false};
    // PC 签名：`(Entity, InputHook, ButtonAction)`。
    // 真实nil/玩家/受控实体，保留原调用者上下文，不把界面输入伪装成玩家0。
    if (entity != 0) {
        invoker.arguments.AddEntity(entity);
    } else {
        invoker.arguments.AddNil();
    }
    invoker.arguments.AddInteger(static_cast<std::int64_t>(inputHook));
    // ★★ 批次 393（2026-10-07）：`buttonAction` 必须给**模组（PC）口径**的号，不是引擎内部号。
    //
    // PC 契约里这个实参就是 `ButtonAction` 的值；而引擎轮询时给我们的 `action` 是**内部号**，
    // 两张表只在 0..15 同号：`ACTION_MAP(13)` 恰好同号（所以 minimapi 从来不受影响，这也是
    // 这个错一直没被咬到的原因），但 `16..23` 那一段整体错开 3（PC 的
    // `MENULEFT..MENUDOWN = 20..23` ↔ 引擎内部 `17..20`）⇒ 任何**比较动作号**的模组都会判错。
    // 已知的真消费者形状：`InputHelper.HandleForceActionPressed`（`inputhelper.lua:257-295`）
    // 用 `forcingActionPressed[controlleIndex][buttonAction]` 存"要强制的动作"——存的是 PC 号。
    // 逐行映射、来源与两处口径说明见 `interfaces/lua/input_action_map.hpp` 的反表。
    // 越界号（引擎不会给；见那张表的注释）**原样透传**，不编造一个 PC 号。
    invoker.arguments.AddInteger(static_cast<std::int64_t>(
        isaac::runtime::TranslateEngineActionToLuaAction(action)));
    isaac::runtime::CallbackDispatcher dispatcher{g_CallbackRegistry, invoker};
    inInputActionDispatch = true;
    // ★★★ 2026-10-07（批次 390 修复）：下面这一条的**过滤器实参必须是 `inputHook`**，
    // **不能**是 `kNoCallbackFilter`。
    //
    // 为什么（真机实证 + 代码）：`MC_INPUT_ACTION` 契约里的 **Optional Args 就是 `InputHook`** ——
    // 也就是 `Mod:AddCallback(id, fn, InputHook)` 的**第 3 个实参 = 过滤器**。
    // 而 `CollectCallOrder` 的判据（`callback_dispatcher.hpp:191-200`）是：
    //   登记声明了过滤器 且 （本次传的是 `kNoCallbackFilter` 或 两者不等） ⇒ **跳过这条登记**
    // ⇒ 传 `kNoCallbackFilter` 会把**所有声明了过滤器**的登记整类跳过。
    // minimapi 正是这么登记的（源码 `main.lua:1773` 的 `end, InputHook.IS_ACTION_PRESSED)`）⇒
    // 它的处理器**一次都不会跑** ⇒ `mapheldframes` 恒 0 ⇒ `IsLarge()` 恒假 ⇒ 小地图永不放大。
    // 探针实测（修复前的读数）：屏幕上 `all=0`（同形登记的回调一次都没收到）。
    //
    // 传 `inputHook`（0/1/2）之后的匹配：
    //   * 声明了 `filter == inputHook` 的登记 ⇒ 匹配（minimapi 声明 PRESSED，PRESSED 那次就能跑）；
    //   * 没声明过滤器的登记（`kNoCallbackFilter`）⇒ 第一个条件为假 ⇒ 照常匹配（MCM 就是这种）；
    //   * 声明了**别的** hook 的登记 ⇒ 跳过 —— 与它自己的声明、也与 PC 语义一致。
    // ★ 回归断言钉在 `runtime/tests/test_lua_callback_dispatch_sites.py`（那条门禁还会核对
    //   "派发点名单 ↔ 源码里的派发调用"，所以这三行的**写法**也别乱改）。
    const isaac::runtime::CallbackDispatchOutcome result =
        dispatcher.DispatchModifying(isaac::runtime::kCallbackInputAction,
                                     isaac::runtime::ThreadAffinity::Any,
                                     static_cast<std::int64_t>(inputHook));
    inInputActionDispatch = false;
    isaac::runtime::EngineGuardLeaveDispatch();
    if (!result.anyNonNil) {
        return outcome;  // 没有模组想覆盖这次查询
    }
    // ★ 覆盖口径：官方教程原文 "`Isaac.RunCallback` will stop at the first callback that returns a
    //   value and return it." ⇒ 取**第一条**返回非 nil 的登记（`DispatchModifying` 的汇总就是这个口径）。
    //   ⚠️ 已知差别：我们**仍然会把后面的登记也叫一遍**（派发器不做短路），PC 会停。
    outcome.overridden = true;
    if (inputHook == kInputHookGetActionValue) {
        // PC 契约：`GET_ACTION_VALUE` 的覆盖值是 **0.0~1.0 的 float**。模组常写 `return 0`（整数）
        // ⇒ 两条通道都认，再按契约夹紧（越界不是模组的锅，夹住比把垃圾值递给引擎安全）。
        double value = result.hasNumber ? result.number
                                        : (result.hasInteger
                                               ? static_cast<double>(result.integer)
                                               : 0.0);
        if (value < 0.0) {
            value = 0.0;
        }
        if (value > 1.0) {
            value = 1.0;
        }
        outcome.value = static_cast<float>(value);
    } else {
        // `IS_ACTION_PRESSED` / `IS_ACTION_TRIGGERED`：覆盖值是布尔（PC 用"除 nil 外的任何值"判真）。
        outcome.boolean = result.anyTruthy;
    }
    return outcome;
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
    if (!isaac::runtime::BuiltinCallbackEnabled(isaac::runtime::kCallbackPreGetCollectible)) {
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
    // 固定PC PRE wrapper只返回低32位；最终eax=0是“继续原生成/POST”哨兵。
    // 转换错误由InvokeProtected捕获，没有结果，也走原生成。不能按raw非nil跳POST。
    if (!outcome.hasInteger) return 0;
    const auto value = static_cast<std::uint32_t>(outcome.integer);
    if (value == 0) return 0;
    return (std::uint64_t{1} << 33) | (std::uint64_t{1} << 32) | value;
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
    return isaac::runtime::notice::integrity::RuntimeAllowed() && g_Ready.load(std::memory_order_acquire);
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
    return isaac::runtime::CountLuaCallbacks(g_LuaState,callbackId);
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

namespace LuaRuntime {
std::uint32_t DispatchGetTrinket(std::int32_t selected,
    const std::array<std::uint8_t,16>& snapshot) {
    // 原生池事件不要求房间/玩家存在（PC wrapper只有内建启用位和Lua状态）。
    if (!IsReady() || g_LuaState == nullptr ||
        !isaac::runtime::BuiltinCallbackEnabled(isaac::runtime::kCallbackGetTrinket)) return 0;
    isaac::runtime::EngineGuardEnterDispatch();
    LuaCallbackInvoker invoker{0,false,false};
    invoker.arguments.AddInteger(selected);
    invoker.arguments.AddRngSnapshot(snapshot);
    isaac::runtime::CallbackDispatcher dispatcher{g_CallbackRegistry,invoker};
    const auto result = dispatcher.DispatchModifying(isaac::runtime::kCallbackGetTrinket,
        isaac::runtime::ThreadAffinity::Any,isaac::runtime::CallbackRegistry::kNoCallbackFilter);
    isaac::runtime::EngineGuardLeaveDispatch();
    // luaL_checkinteger 已在 InvokeProtected 中完成；原包装只读低32位，0表示不覆盖。
    return result.hasInteger ? static_cast<std::uint32_t>(result.integer) : 0U;
}
std::int32_t DispatchGetPillColor(std::uint32_t seed, std::int32_t selected) {
    if (!IsReady() || g_LuaState == nullptr || !isaac::runtime::ShouldDispatchManagedCallbacks() ||
        !isaac::runtime::BuiltinCallbackEnabled(isaac::runtime::kCallbackGetPillColor)) return selected;
    isaac::runtime::EngineGuardEnterDispatch();
    LuaCallbackInvoker invoker{0, false, false};
    invoker.arguments.AddInteger(seed);
    isaac::runtime::CallbackDispatcher dispatcher{g_CallbackRegistry, invoker};
    const auto result = dispatcher.DispatchModifying(isaac::runtime::kCallbackGetPillColor,
        isaac::runtime::ThreadAffinity::Any, isaac::runtime::CallbackRegistry::kNoCallbackFilter);
    isaac::runtime::EngineGuardLeaveDispatch();
    return result.hasInteger && result.integer >= INT32_MIN && result.integer <= INT32_MAX
        ? static_cast<std::int32_t>(result.integer) : selected;
}
std::int32_t DispatchGetPillEffect(std::uint32_t color, std::int32_t selected) {
    if (!IsReady() || g_LuaState == nullptr || !isaac::runtime::ShouldDispatchManagedCallbacks() ||
        !isaac::runtime::BuiltinCallbackEnabled(isaac::runtime::kCallbackGetPillEffect)) return selected;
    isaac::runtime::EngineGuardEnterDispatch();
    LuaCallbackInvoker invoker{0, false, false};
    invoker.arguments.AddInteger(selected);
    invoker.arguments.AddInteger(color);
    isaac::runtime::CallbackDispatcher dispatcher{g_CallbackRegistry, invoker};
    const auto result = dispatcher.DispatchModifying(isaac::runtime::kCallbackGetPillEffect,
        isaac::runtime::ThreadAffinity::Any, isaac::runtime::CallbackRegistry::kNoCallbackFilter);
    isaac::runtime::EngineGuardLeaveDispatch();
    return result.hasInteger && result.integer >= INT32_MIN && result.integer <= INT32_MAX
        ? static_cast<std::int32_t>(result.integer) : selected;
}
bool DispatchPreEntityDevolve(std::uintptr_t entity) {
    if (!IsReady() || g_LuaState == nullptr || !isaac::runtime::ShouldDispatchManagedCallbacks() ||
        !isaac::runtime::BuiltinCallbackEnabled(isaac::runtime::kCallbackPreEntityDevolve)) return false;
    isaac::runtime::EngineGuardEnterDispatch();
    auto invoker = LuaCallbackInvoker::ForEntity(entity);
    isaac::runtime::CallbackDispatcher dispatcher{g_CallbackRegistry, invoker};
    const auto result = dispatcher.DispatchModifying(isaac::runtime::kCallbackPreEntityDevolve,
        isaac::runtime::ThreadAffinity::Any, isaac::runtime::CallbackRegistry::kNoCallbackFilter);
    isaac::runtime::EngineGuardLeaveDispatch();
    return result.anyTruthy;
}
} // namespace LuaRuntime

namespace LuaRuntime {
bool DispatchPreNpcUpdate(std::uintptr_t npc, std::int32_t entityType) {
    if (!IsReady() || g_LuaState == nullptr || !isaac::runtime::ShouldDispatchManagedCallbacks() ||
        !isaac::runtime::BuiltinCallbackEnabled(isaac::runtime::kCallbackPreNpcUpdate)) return false;
    isaac::runtime::EngineGuardEnterDispatch();
    auto invoker = LuaCallbackInvoker::ForEntity(npc);
    isaac::runtime::CallbackDispatcher dispatcher{g_CallbackRegistry, invoker};
    const auto result = dispatcher.DispatchModifying(isaac::runtime::kCallbackPreNpcUpdate,
        isaac::runtime::ThreadAffinity::Any, entityType);
    isaac::runtime::EngineGuardLeaveDispatch();
    return result.anyTruthy;
}
} // namespace LuaRuntime

namespace LuaRuntime {
namespace {
struct SpawnDispatchContext {
    LuaCallbackInvoker* invoker;
    EntitySpawnOverride result;
};
int CollectPreEntitySpawn(lua_State* state) {
    auto* context = static_cast<SpawnDispatchContext*>(lua_touserdata(state, 1));
    lua_pushnil(state); // 栈2保留最后有效表，嵌套的保护调用不会改变这个槽位。
    context->invoker->tableStackIndex = 2;
    isaac::runtime::CallbackDispatcher dispatcher{g_CallbackRegistry, *context->invoker};
    const auto outcome = dispatcher.DispatchModifying(isaac::runtime::kCallbackPreEntitySpawn,
        isaac::runtime::ThreadAffinity::Any, isaac::runtime::CallbackRegistry::kNoCallbackFilter);
    context->invoker->tableStackIndex = 0;
    if (!outcome.hasTable) return 0;
    g_ErrorContextOwner = context->invoker->tableOwner;
    context->result.present = true;
    for (int index = 1; index <= 4; ++index) {
        // PC LuaRef用lua_gettable，所有登记结束后才读最后一张表；元方法亦在外层保护内。
        lua_geti(state, 2, index);
        if (!lua_isnil(state, -1)) {
            // PC整数转换为luaL_checkinteger，32位原生参数取低32位。
            const lua_Integer value = luaL_checkinteger(state, -1);
            switch (index) {
                case 1: context->result.type = static_cast<std::int32_t>(value); break;
                case 2: context->result.variant = static_cast<std::uint32_t>(value); break;
                case 3: context->result.subType = static_cast<std::uint32_t>(value); break;
                case 4: context->result.seed = static_cast<std::uint32_t>(value); break;
            }
        }
        lua_pop(state, 1);
    }
    return 0;
}
} // namespace
EntitySpawnOverride DispatchPreEntitySpawn(std::int32_t type, std::uint32_t variant,
    std::uint32_t subType, const void* position, const void* velocity,
    std::uintptr_t spawner, std::uint32_t seed) {
    const EntitySpawnOverride original{false, type, variant, subType, seed};
    if (!IsReady() || g_LuaState == nullptr || !isaac::runtime::ShouldDispatchManagedCallbacks() ||
        !isaac::runtime::BuiltinCallbackEnabled(isaac::runtime::kCallbackPreEntitySpawn) ||
        position == nullptr || velocity == nullptr ||
        !isaac::runtime::engine_memory::EngineMemoryReadable(isaac::runtime::engine_memory::AddressOf(position), 2 * sizeof(float)) ||
        !isaac::runtime::engine_memory::EngineMemoryReadable(isaac::runtime::engine_memory::AddressOf(velocity), 2 * sizeof(float))) return original;
    float pos[2], vel[2];
    std::memcpy(pos, position, sizeof(pos));
    std::memcpy(vel, velocity, sizeof(vel));
    // 非平凡C++对象留在外层，Lua longjmp不会跳过其析构；保护桥里只有引用和POD。
    LuaCallbackInvoker invoker{0, false, false};
    invoker.arguments.AddInteger(type);
    invoker.arguments.AddInteger(variant);
    invoker.arguments.AddInteger(subType);
    invoker.arguments.AddVector(pos[0], pos[1]);
    invoker.arguments.AddVector(vel[0], vel[1]);
    if (spawner != 0) invoker.arguments.AddEntity(spawner); else invoker.arguments.AddNil();
    invoker.arguments.AddInteger(seed);
    if (!lua_checkstack(g_LuaState, 4)) { g_CallbackError.store(true, std::memory_order_release); return original; }
    SpawnDispatchContext context{&invoker, original};
    const auto previousOwner = g_ErrorContextOwner, previousId = g_ErrorContextCallbackId;
    const auto previousScope = g_InManagedCallbackDispatch.load(std::memory_order_acquire);
    g_ErrorContextCallbackId = isaac::runtime::kCallbackPreEntitySpawn;
    g_InManagedCallbackDispatch.store(true, std::memory_order_release);
    isaac::runtime::EngineGuardEnterDispatch();
    lua_pushcfunction(g_LuaState, CollectPreEntitySpawn);
    lua_pushlightuserdata(g_LuaState, &context);
    const int status = lua_pcallk(g_LuaState, 1, 0, 0, 0, nullptr);
    if (status != LUA_OK) {
        CaptureLuaErrorTop(g_LuaState);
        lua_pop(g_LuaState, 1);
        g_CallbackError.store(true, std::memory_order_release);
        context.result = original; // 非法最终表明确报错，不发布半张表的修改。
    }
    isaac::runtime::EngineGuardLeaveDispatch();
    g_ErrorContextOwner = previousOwner;
    g_ErrorContextCallbackId = previousId;
    g_InManagedCallbackDispatch.store(previousScope, std::memory_order_release);
    return context.result;
}

namespace {
struct RoomSpawnDispatchContext {
    LuaCallbackInvoker* invoker;
    RoomEntitySpawnOverride result;
};
int CollectPreRoomEntitySpawn(lua_State* state) {
    static_assert(std::is_trivially_destructible_v<RoomSpawnDispatchContext>);
    static_assert(std::is_trivially_destructible_v<isaac::runtime::CallbackDispatcher>);
    static_assert(std::is_trivially_destructible_v<isaac::runtime::CallbackDispatchOutcome>);
    auto* context = static_cast<RoomSpawnDispatchContext*>(lua_touserdata(state, 1));
    lua_pushnil(state);
    context->invoker->tableStackIndex = 2;
    isaac::runtime::CallbackDispatcher dispatcher{g_CallbackRegistry, *context->invoker};
    const auto outcome = dispatcher.DispatchModifying(isaac::runtime::kCallbackPreRoomEntitySpawn,
        isaac::runtime::ThreadAffinity::Any, isaac::runtime::CallbackRegistry::kNoCallbackFilter);
    context->invoker->tableStackIndex = 0;
    if (!outcome.hasTable) return 0;
    g_ErrorContextOwner = context->invoker->tableOwner;
    // PC71只在全部登记结束后读取最终表；空表/仅索引4不跳常规修正。
    for (int index = 1; index <= 3; ++index) {
        lua_geti(state, 2, index);
        if (!lua_isnil(state, -1)) {
            const lua_Integer value = luaL_checkinteger(state, -1);
            context->result.present = true;
            if (index == 1) context->result.type = static_cast<std::int32_t>(value);
            else if (index == 2) context->result.variant = static_cast<std::uint16_t>(value);
            else context->result.subType = static_cast<std::uint16_t>(value);
        }
        lua_pop(state, 1);
    }
    return 0;
}
} // namespace

RoomEntitySpawnOverride DispatchPreRoomEntitySpawnModifying(std::int32_t type,
    std::uint16_t variant, std::uint16_t subType, std::uint32_t gridIndex, std::uint32_t seed) {
    const RoomEntitySpawnOverride original{false, type, variant, subType};
    if (!IsReady() || g_LuaState == nullptr || !isaac::runtime::ShouldDispatchManagedCallbacks() ||
        !isaac::runtime::BuiltinCallbackEnabled(isaac::runtime::kCallbackPreRoomEntitySpawn)) return original;
    // 非平凡invoker在外层；保护C桥里的所有局部对象均可平凡析构。
    LuaCallbackInvoker invoker{0, false, false};
    invoker.arguments.AddInteger(type);
    invoker.arguments.AddInteger(variant);
    invoker.arguments.AddInteger(subType);
    invoker.arguments.AddInteger(gridIndex);
    invoker.arguments.AddInteger(seed);
    if (!lua_checkstack(g_LuaState, 4)) { g_CallbackError.store(true, std::memory_order_release); return original; }
    RoomSpawnDispatchContext context{&invoker, original};
    const auto previousOwner = g_ErrorContextOwner, previousId = g_ErrorContextCallbackId;
    const auto previousScope = g_InManagedCallbackDispatch.load(std::memory_order_acquire);
    g_ErrorContextCallbackId = isaac::runtime::kCallbackPreRoomEntitySpawn;
    g_InManagedCallbackDispatch.store(true, std::memory_order_release);
    isaac::runtime::EngineGuardEnterDispatch();
    lua_pushcfunction(g_LuaState, CollectPreRoomEntitySpawn);
    lua_pushlightuserdata(g_LuaState, &context);
    const int status = lua_pcallk(g_LuaState, 1, 0, 0, 0, nullptr);
    if (status != LUA_OK) {
        CaptureLuaErrorTop(g_LuaState);
        lua_pop(g_LuaState, 1);
        g_CallbackError.store(true, std::memory_order_release);
        context.result = original;
    }
    isaac::runtime::EngineGuardLeaveDispatch();
    g_ErrorContextOwner = previousOwner;
    g_ErrorContextCallbackId = previousId;
    g_InManagedCallbackDispatch.store(previousScope, std::memory_order_release);
    return context.result;
}
} // namespace LuaRuntime

namespace LuaRuntime {
bool DispatchPreSpawnCleanAward(const std::array<std::uint8_t,16>& snapshot, float x, float y) {
    if (!IsReady() || g_LuaState == nullptr ||
        !isaac::runtime::BuiltinCallbackEnabled(isaac::runtime::kCallbackPreSpawnCleanAward)) return false;
    isaac::runtime::EngineGuardEnterDispatch();
    LuaCallbackInvoker invoker{0,false,false};
    invoker.arguments.AddRngSnapshot(snapshot);
    invoker.arguments.AddVector(x,y);
    isaac::runtime::CallbackDispatcher dispatcher{g_CallbackRegistry,invoker};
    const auto result = dispatcher.DispatchModifying(isaac::runtime::kCallbackPreSpawnCleanAward,
        isaac::runtime::ThreadAffinity::Any,isaac::runtime::CallbackRegistry::kNoCallbackFilter);
    isaac::runtime::EngineGuardLeaveDispatch();
    return result.anyTruthy;
}
}

namespace LuaRuntime {
void DispatchPostEntityRemove(std::uintptr_t entity, std::int32_t entityType) {
    if (!IsReady() || g_LuaState == nullptr ||
        !isaac::runtime::BuiltinCallbackEnabled(isaac::runtime::kCallbackPostEntityRemove)) return;
    isaac::runtime::EngineGuardEnterDispatch();
    LuaCallbackInvoker invoker = LuaCallbackInvoker::ForEntity(entity);
    isaac::runtime::CallbackDispatcher dispatcher{g_CallbackRegistry, invoker};
    static_cast<void>(dispatcher.DispatchFiltered(isaac::runtime::kCallbackPostEntityRemove,
        isaac::runtime::ThreadAffinity::Any,static_cast<std::int64_t>(entityType)));
    isaac::runtime::EngineGuardLeaveDispatch();
}
}

namespace LuaRuntime {
std::uint32_t DispatchPostCurseEval(std::uint32_t curses) {
    if (!IsReady() || g_LuaState==nullptr || !isaac::runtime::BuiltinCallbackEnabled(isaac::runtime::kCallbackPostCurseEval)) return curses;
    LuaCallbackInvoker invoker{0,false,false};invoker.arguments.AddInteger(curses);
    isaac::runtime::EngineGuardEnterDispatch();
    isaac::runtime::CallbackDispatcher dispatcher{g_CallbackRegistry,invoker};
    const auto out=dispatcher.DispatchModifying(isaac::runtime::kCallbackPostCurseEval,isaac::runtime::ThreadAffinity::Any,-1);
    isaac::runtime::EngineGuardLeaveDispatch();
    return out.hasInteger?static_cast<std::uint32_t>(out.integer):curses;
}
namespace {
struct PickupSelectionContext {LuaCallbackInvoker* invoker;std::uint32_t* variant;std::uint32_t* subtype;};
int CollectPickupSelection(lua_State* state) {
    auto* c=static_cast<PickupSelectionContext*>(lua_touserdata(state,1));
    lua_pushnil(state);c->invoker->tableStackIndex=2;
    isaac::runtime::CallbackDispatcher dispatcher{g_CallbackRegistry,*c->invoker};
    const auto out=dispatcher.DispatchModifying(isaac::runtime::kCallbackPostPickupSelection,isaac::runtime::ThreadAffinity::Any,-1);
    c->invoker->tableStackIndex=0;
    if (!out.hasTable) return 0;
    g_ErrorContextOwner=c->invoker->tableOwner;
    for(int index=1;index<=2;++index) {
        lua_geti(state,2,index);
        if (!lua_isnil(state,-1)) {
            const auto value=static_cast<std::uint32_t>(luaL_checkinteger(state,-1));
            // PC7FFC0C先写variant；第二项失败不能撤销第一项。
            *(index==1?c->variant:c->subtype)=value;
        }
        lua_pop(state,1);
    }
    return 0;
}
}
void DispatchPostPickupSelection(std::uintptr_t pickup,std::uint32_t* variant,std::uint32_t* subType) {
    if (!IsReady() || g_LuaState==nullptr || variant==nullptr || subType==nullptr ||
        !isaac::runtime::BuiltinCallbackEnabled(isaac::runtime::kCallbackPostPickupSelection)) return;
    auto invoker=LuaCallbackInvoker::ForEntity(pickup);
    invoker.arguments.AddInteger(*variant);invoker.arguments.AddInteger(*subType);
    if (!lua_checkstack(g_LuaState,4)) {g_CallbackError.store(true,std::memory_order_release);return;}
    PickupSelectionContext context{&invoker,variant,subType};
    const auto previousOwner=g_ErrorContextOwner,previousId=g_ErrorContextCallbackId;
    const auto previousScope=g_InManagedCallbackDispatch.load(std::memory_order_acquire);
    g_ErrorContextCallbackId=isaac::runtime::kCallbackPostPickupSelection;
    g_InManagedCallbackDispatch.store(true,std::memory_order_release);
    isaac::runtime::EngineGuardEnterDispatch();
    lua_pushcfunction(g_LuaState,CollectPickupSelection);lua_pushlightuserdata(g_LuaState,&context);
    if (lua_pcallk(g_LuaState,1,0,0,0,nullptr)!=LUA_OK) {
        CaptureLuaErrorTop(g_LuaState);lua_pop(g_LuaState,1);g_CallbackError.store(true,std::memory_order_release);
    }
    isaac::runtime::EngineGuardLeaveDispatch();g_ErrorContextOwner=previousOwner;g_ErrorContextCallbackId=previousId;
    g_InManagedCallbackDispatch.store(previousScope,std::memory_order_release);
}
}

namespace LuaRuntime {
bool CanDispatchGetCard() noexcept {
    return IsOnGameThread() && IsReady() && g_LuaState!=nullptr &&
        isaac::runtime::BuiltinCallbackEnabled(isaac::runtime::kCallbackGetCard);
}
std::uint32_t DispatchGetCard(void* rng,std::uint32_t selected,bool playing,bool runes,bool onlyRunes) {
    if(!CanDispatchGetCard())return selected;
    isaac::runtime::CardRngScope scope{};
    if(!g_CardRngScopes.Enter(scope,reinterpret_cast<std::uintptr_t>(rng)))return selected;
    const bool previousGuard=isaac::runtime::EngineGuardDispatchActive().load(std::memory_order_acquire)!=0;
    isaac::runtime::EngineGuardEnterDispatch();
    LuaCallbackInvoker invoker{0,false,false};
    invoker.arguments.AddBorrowedRng(scope.pointer,scope.token);
    invoker.arguments.AddInteger(selected);
    invoker.arguments.AddBoolean(playing);invoker.arguments.AddBoolean(runes);invoker.arguments.AddBoolean(onlyRunes);
    isaac::runtime::CallbackDispatcher dispatcher{g_CallbackRegistry,invoker};
    const auto result=dispatcher.DispatchModifying(isaac::runtime::kCallbackGetCard,
        isaac::runtime::ThreadAffinity::Any,-1);
    g_CardRngScopes.Leave(scope);
    if(!previousGuard)isaac::runtime::EngineGuardLeaveDispatch();
    return result.hasInteger?static_cast<std::uint32_t>(result.integer):selected;
}
}

namespace LuaRuntime {
namespace {
std::atomic<std::uintptr_t> s_GameThreadToken{};
std::uintptr_t CurrentGameThreadToken() noexcept {
#if defined(__aarch64__)
    std::uintptr_t token{};
    asm volatile("mrs %0, tpidrro_el0" : "=r"(token));
    return token;
#else
    static thread_local unsigned char token;
    return reinterpret_cast<std::uintptr_t>(&token);
#endif
}
bool s_UnloadingManifestMods{};
}
void ObserveGameThread() noexcept {
    if(s_GameThreadToken.load(std::memory_order_relaxed)!=0)return;
    std::uintptr_t empty{};
    s_GameThreadToken.compare_exchange_strong(empty,CurrentGameThreadToken(),std::memory_order_release);
}
bool IsOnGameThread() noexcept {
    const auto token=s_GameThreadToken.load(std::memory_order_acquire);
    return token!=0 && token==CurrentGameThreadToken();
}
bool UnloadManifestMods() noexcept {
    if (!IsOnGameThread() || !IsReady() || !g_LuaState) return false;
    if (s_UnloadingManifestMods) return true;
    if (!lua_checkstack(g_LuaState,4)) return false;
    const int top=lua_gettop(g_LuaState);s_UnloadingManifestMods=true;
    lua_pushcfunction(g_LuaState,isaac::runtime::UnloadTrackedMods);
    const int status=lua_pcall(g_LuaState,0,2,0);
    const bool success=status==LUA_OK && lua_toboolean(g_LuaState,-2)!=0;
    if(!success){CaptureLuaErrorTop(g_LuaState);g_CallbackError.store(true,std::memory_order_release);}
    lua_settop(g_LuaState,top);s_UnloadingManifestMods=false;
    return success;
}

bool ShutdownForModReload() noexcept {
    // 先确认线程，再读Lua栈；没有VM时重复调用不需要触碰任何Lua对象。
    if (!g_LuaState && !g_ShuttingDownForModReload) return true;
    if (!IsOnGameThread()) {
        constexpr char error[] = "mod reload shutdown requires the observed game thread";
        RecordLuaErrorText(error,sizeof(error)-1);return false;
    }
    lua_Debug frame{};
    if (g_ShuttingDownForModReload || s_UnloadingManifestMods ||
        InManagedCallbackScope() || g_ActiveCallbackBatch || g_CardRngScopes.top ||
        lua_getstack(g_LuaState,0,&frame)) {
        constexpr char error[] = "mod reload shutdown rejected while Lua is executing";
        RecordLuaErrorText(error,sizeof(error)-1);return false;
    }
    g_ShuttingDownForModReload = true;
    if (!UnloadManifestMods()) {
        g_ShuttingDownForModReload = false;
        return false; // 正常卸载的错误与可重试对象仍由原VM持有，不进入失败清理。
    }
    lua_State* state = g_LuaState;
    if (isaac::runtime::HasPressurePlateAnimationPins()) {
        const int top = lua_gettop(state);
        if (!lua_checkstack(state,1)) {
            constexpr char error[] = "mod reload shutdown cannot reserve cleanup stack";
            RecordLuaErrorText(error,sizeof(error)-1);
            g_ShuttingDownForModReload = false;return false;
        }
        lua_pushcfunction(state,RestoreAllPressurePinsProtected);
        const int result = lua_pcall(state,0,0,0);
        if (result != LUA_OK) {
            CaptureLuaErrorTop(state);lua_settop(state,top);
            g_CallbackError.store(true,std::memory_order_release);
            g_ShuttingDownForModReload = false;return false;
        }
        lua_settop(state,top);
    }
    g_Ready.store(false,std::memory_order_release);
    // lua_close负责完整运行Font/Sprite和其它userdata终结器；绑定仍须有效。
    isaac::runtime::ResetEntityLifetimeState();
    lua_close(state);
    g_LuaState = nullptr;
    // 用户终结器可能再次访问过GetData，关闭之后再解除一次外部缓存。
    isaac::runtime::ResetEntityLifetimeState();
    g_CallbackRegistry.Reset();
    isaac::runtime::ResetCallbackRuntimeState();
    ResetCallbackRegistrationCensus();
    g_ModRegistered = false;
    g_ModRegisteredCount.store(0,std::memory_order_relaxed);
    g_NextModOwnerIndex.store(2,std::memory_order_relaxed);
    std::memset(g_ModOwnerNames,0,sizeof(g_ModOwnerNames));
    g_LoadingModRoot = "";
#if !defined(EXL_DIAGNOSTIC_STAGE) || EXL_DIAGNOSTIC_STAGE == 13
    ResetStage13Context();
    SetRequireCurrentModule(nullptr,0);
    g_RequireFailureDetail.store(0,std::memory_order_relaxed);
    g_RequireErrorTail.store(0,std::memory_order_relaxed);
#endif
    g_RequireFirstFailureCode.store(0,std::memory_order_relaxed);
    g_RequireFirstFailureName.store(0,std::memory_order_relaxed);
    g_RequireLastFailureCode.store(0,std::memory_order_relaxed);
    g_RequireLastFailureName.store(0,std::memory_order_relaxed);
    g_RequireFailureTotal.store(0,std::memory_order_relaxed);
    g_PendingGameStarted.store(0,std::memory_order_release);
    g_GameStartedInCurrentVm = false;
    g_FrameEventState = {};
    g_NativePlayerInitObserved = false;
    ResetLevelStartRoomTracker();
    g_CurrentCallbackManager.store(0,std::memory_order_release);
    g_InManagedCallbackDispatch.store(false,std::memory_order_release);
    g_InPreGetCollectibleDispatch = false;
    g_InPostEntityKillDispatch = false;
    g_CardRngScopes = {};
    g_ErrorContextOwner = 0;
    g_ErrorContextCallbackId = isaac::runtime::kNoCallbackDispatched;
    g_PreparationStep.store(0,std::memory_order_relaxed);
    g_PreparationStatus.store(0,std::memory_order_relaxed);
    g_PostUpdateCount.store(0,std::memory_order_relaxed);
    g_CallbackError.store(false,std::memory_order_release);
#if defined(EXL_PERSISTENCE_TRACE) || defined(EXL_PERSISTENCE_EVENT_DIAGNOSTIC)
    g_CallbackOperation.store(static_cast<u8>(CallbackOperation::None),std::memory_order_relaxed);
    g_CallbackFailureDetail.store(0,std::memory_order_relaxed);
#endif
#if defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 15
    g_PostRenderCount.store(0,std::memory_order_relaxed);
    g_PostRenderPausedCount.store(0,std::memory_order_relaxed);
#endif
#if defined(EXL_DIAGNOSTIC_STAGE) && (EXL_DIAGNOSTIC_STAGE == 16 || EXL_DIAGNOSTIC_STAGE == 17)
    g_MusicDiagnosticCycleCompleted.store(false,std::memory_order_relaxed);
#endif
#if defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 45
    g_MusicDiagnosticCurrentIdReady.store(false,std::memory_order_relaxed);
    g_MusicDiagnosticCurrentId.store(0,std::memory_order_relaxed);
#endif
    g_MusicResolveFailure.store(0,std::memory_order_relaxed);
    g_fontLastGcFrame = 0;
    g_fontGcProductive = true;
    g_fontLastUnproductiveAllocation = 0;
    g_fontDestructionsAtCycleStart = 0;
    // Owner编号会重用，旧代的按owner计时桶不能落到新模组名上。
    for (auto& bucket : g_RuntimePerfCallbackBuckets) bucket = {};
    g_RuntimePerfBucketOverflow = 0;
    g_ProfileSessionStarted = false;
    ResetRuntimePerfProfile();
    g_ShuttingDownForModReload = false;
    return true;
}
bool ClosingForModReload() noexcept {
    return g_ShuttingDownForModReload && !g_Ready.load(std::memory_order_acquire);
}
}

#include "console_callback_hook.hpp"
#include "infrastructure/console/console_bridge.hpp"
#include "infrastructure/console/console_clear.hpp"
namespace LuaRuntime {
namespace {
const isaac::runtime::ConsoleCommandView* s_ActiveConsoleCommand{};
bool ConsoleTokenEquals(const char* text,std::size_t length,const char* wanted) noexcept {
    return length==std::strlen(wanted) && std::memcmp(text,wanted,length)==0;
}
#if !defined(EXL_DIAGNOSTIC_STAGE) || EXL_DIAGNOSTIC_STAGE == 13
int ReloadModBody(lua_State* state){
    const auto* root=luaL_checkstring(state,1);
    lua_pushcfunction(state,isaac::runtime::UnloadTrackedModRoot);lua_pushvalue(state,1);
    lua_call(state,1,2);
    if(!lua_toboolean(state,-2)){lua_remove(state,-2);return lua_error(state);}
    lua_pop(state,2);
    isaac::runtime::ClearTrackedRequireModules(state,root);
    lua_pushvalue(state,2);lua_call(state,0,0);return 0;
}
int ReloadConsoleMod(lua_State* state){
    luaL_checkstring(state,1);
    lua_pushcfunction(state,isaac::runtime::FindTrackedModRoot);lua_pushvalue(state,1);lua_call(state,1,1);
    const int rootIndex=lua_gettop(state);const auto* root=lua_tostring(state,rootIndex);
    std::array<char,kStage13RequirePathCapacity> path{};
    const int n=std::snprintf(path.data(),path.size(),"%s/main.lua",root);
    if(n<0||static_cast<std::size_t>(n)>=path.size())return luaL_error(state,"luamod path is too long");
    std::size_t length{};
    if(GameFileReader::ReadTextFile(g_Stage13Bindings,path.data(),
       reinterpret_cast<u8*>(g_Stage13RequireSource.data()),g_Stage13RequireSource.size(),&length)!=GameFileReader::TextReadResult::Success)
        return luaL_error(state,"luamod cannot read %s",path.data());
    std::array<char,kStage13RequirePathCapacity+1> chunk{};chunk[0]='@';std::memcpy(chunk.data()+1,path.data(),static_cast<std::size_t>(n)+1);
    if(LoadFileChunk(state,g_Stage13RequireSource.data(),length,chunk.data())!=LUA_OK)return lua_error(state);
    const int function=lua_gettop(state);
    // 所有可抛Lua错误的卸载/缓存/入口执行放在内层保护内，之后始终恢复原装载上下文。
    const auto previousRoot=g_Stage13ModRoot;const auto previousBindings=g_Stage13Bindings;
    if(!SetStage13Context(root,previousBindings))return luaL_error(state,"luamod root is unavailable");
    lua_pushcfunction(state,ReloadModBody);lua_pushvalue(state,rootIndex);lua_pushvalue(state,function);
    const int result=lua_pcall(state,2,0,0);
    static_cast<void>(SetStage13Context(previousRoot.data(),previousBindings));
    if(result!=LUA_OK)return lua_error(state);
    return 0;
}
#endif
int ExecuteCommandCallbackProtected(lua_State* state) {
    const auto* view=static_cast<const isaac::runtime::ConsoleCommandView*>(lua_touserdata(state,1));
    const char* token{};std::size_t length{};
    if(!isaac::runtime::ReadConsoleToken(*view,0,&token,&length))return luaL_error(state,"invalid native console token");
    const bool luaCommand=ConsoleTokenEquals(token,length,"lua") || ConsoleTokenEquals(token,length,"l");
    if (ConsoleTokenEquals(token,length,"clear")) {
        if (!isaac::runtime::console::ClearVisibleConsole(view->console,
            isaac::runtime::console::ResolveClearHistory(EngineModuleBase())))
            return luaL_error(state,"console clear entry unavailable");
        return 0;
    }
    if (ConsoleTokenEquals(token,length,"luamem")) {
        char message[96];const int written=std::snprintf(message,sizeof(message),
            "Lua mem usage: %d KB and %d bytes\n",lua_gc(state,LUA_GCCOUNT,0),lua_gc(state,LUA_GCCOUNTB,0));
        if (written>0 && static_cast<std::size_t>(written)<sizeof(message))
            static_cast<void>(WriteActiveConsoleOutput(message,static_cast<std::size_t>(written)));
        return 0;
    }
    if(ConsoleTokenEquals(token,length,"luamod")){
#if !defined(EXL_DIAGNOSTIC_STAGE) || EXL_DIAGNOSTIC_STAGE == 13
        if(view->count<2)return luaL_error(state,"luamod expects a mod directory or loaded name");
        lua_pushcfunction(state,ReloadConsoleMod);
        luaL_Buffer name;luaL_buffinit(state,&name);
        for(std::size_t i=1;i<view->count;++i){
            if(!isaac::runtime::ReadConsoleToken(*view,i,&token,&length))return luaL_error(state,"invalid luamod parameter");
            if(i!=1)luaL_addchar(&name,' ');
            luaL_addlstring(&name,token,length);
        }
        luaL_pushresult(&name);lua_call(state,1,0);return 0;
#else
        return luaL_error(state,"luamod file loading is unavailable in this diagnostic build");
#endif
    }
    if (!luaCommand && !isaac::runtime::BuiltinCallbackEnabled(isaac::runtime::kCallbackExecuteCmd)) return 0;
    isaac::runtime::PushCallbackRunner(state);lua_pushinteger(state,isaac::runtime::kCallbackExecuteCmd);lua_pushinteger(state,-1);
    lua_pushlstring(state,token,length);
    luaL_Buffer parameters;luaL_buffinit(state,&parameters);
    for(std::size_t i=1;i<view->count;++i) {
        if(!isaac::runtime::ReadConsoleToken(*view,i,&token,&length))return luaL_error(state,"invalid native console parameter");
        if(i!=1)luaL_addchar(&parameters,' ');
        luaL_addlstring(&parameters,token,length);
    }
    luaL_pushresult(&parameters);
    if (luaCommand && view->count>=2) {
        // PC669E18..669EEE同样逐token用空格重组，不另开Lua状态。
        const auto* source=lua_tolstring(state,-1,&length);
        int status=luaL_loadbufferx(state,source,length,"=(console)","t");
        if (status==LUA_OK) status=lua_pcall(state,0,0,0);
        if (status!=LUA_OK) {
            const auto* error=lua_tolstring(state,-1,&length);
            if (error) static_cast<void>(WriteActiveConsoleOutput(error,length));
            static_cast<void>(WriteActiveConsoleOutput("\n",1));
        }
        return 0;
    }
    if (luaCommand) return 0;
    lua_call(state,4,1);
    // PC801F30只消费LUA_TSTRING；不强制转换number/false，也不继续其它回调。
    if(lua_type(state,-1)==LUA_TSTRING) {
        const auto* result=lua_tolstring(state,-1,&length);
        if(length && view->print) {
            unsigned char borrowed[24];
            if(isaac::runtime::console::BuildBorrowedCommandString(result,length,borrowed))view->print(view->console,borrowed,0xffd3d3d3U,150);
        }
    }
    return 0;
}
}
bool ConsoleCommandOutputActive() noexcept {return s_ActiveConsoleCommand && s_ActiveConsoleCommand->print;}
bool WriteActiveConsoleOutput(const char* text,std::size_t length) noexcept {
    if (!ConsoleCommandOutputActive()) return false;
    alignas(8) unsigned char borrowed[24]{};
    if (text && length && isaac::runtime::console::BuildBorrowedCommandString(text,length,borrowed))
        s_ActiveConsoleCommand->print(s_ActiveConsoleCommand->console,borrowed,0xffd3d3d3U,150);
    return true;
}
void DispatchExecuteCommand(const isaac::runtime::ConsoleCommandView& view) noexcept {
    if(!IsOnGameThread() || !IsReady() || !g_LuaState || !view.count)return;
    if(!lua_checkstack(g_LuaState,4)){g_CallbackError.store(true,std::memory_order_release);return;}
    const int top=lua_gettop(g_LuaState);
    const auto* previousCommand=s_ActiveConsoleCommand;s_ActiveConsoleCommand=&view;
    const auto previousOwner=g_ErrorContextOwner,previousId=g_ErrorContextCallbackId;
    g_ErrorContextCallbackId=isaac::runtime::kCallbackExecuteCmd;
    const bool previousGuard=isaac::runtime::EngineGuardDispatchActive().load(std::memory_order_acquire)!=0;
    isaac::runtime::EngineGuardEnterDispatch();
    const auto previousScope=g_InManagedCallbackDispatch.load(std::memory_order_acquire);
    g_InManagedCallbackDispatch.store(true,std::memory_order_release);
    lua_pushcfunction(g_LuaState,ExecuteCommandCallbackProtected);
    lua_pushlightuserdata(g_LuaState,const_cast<isaac::runtime::ConsoleCommandView*>(&view));
    if(lua_pcall(g_LuaState,1,0,0)!=LUA_OK){
        std::size_t length{};const auto* error=lua_tolstring(g_LuaState,-1,&length);
        if (error) static_cast<void>(WriteActiveConsoleOutput(error,length));
        CaptureLuaErrorTop(g_LuaState);g_CallbackError.store(true,std::memory_order_release);
    }
    lua_settop(g_LuaState,top);g_InManagedCallbackDispatch.store(previousScope,std::memory_order_release);
    s_ActiveConsoleCommand=previousCommand;
    g_ErrorContextOwner=previousOwner;g_ErrorContextCallbackId=previousId;
    if(!previousGuard)isaac::runtime::EngineGuardLeaveDispatch();
}
}

namespace LuaRuntime {
namespace {
struct ShaderArguments {const isaac::runtime::ShaderProgramView* program;float* vertices;};
int ShaderValuesProtected(lua_State* state) {
    auto* request=static_cast<ShaderArguments*>(lua_touserdata(state,1));
    isaac::runtime::PushCallbackRunner(state);lua_pushinteger(state,isaac::runtime::kCallbackGetShaderParams);lua_pushinteger(state,-1);
    lua_pushstring(state,request->program->name);lua_call(state,3,1);
    if(!lua_istable(state,-1))return 0; // PC非table结果使用零参数，第一非nil仍由原bootstrap短路。
    const int table=lua_gettop(state);
    for(unsigned vertex=0;vertex<4;++vertex) {
        float* values=request->vertices+vertex*request->program->strideFloats;
        for(std::size_t i=0;i<request->program->parameterCount;++i) {
            const auto& param=request->program->parameters[i];lua_getfield(state,table,param.name);
            if(lua_isnil(state,-1)){lua_pop(state,1);continue;}
            if(param.components==1) {
                values[param.offset]=lua_isboolean(state,-1)?static_cast<float>(lua_toboolean(state,-1)):static_cast<float>(luaL_checknumber(state,-1));
            }else {
                if(!lua_istable(state,-1))return luaL_error(state,"shader parameter %s requires %u components",param.name,param.components);
                const int vector=lua_gettop(state);
                for(unsigned component=0;component<param.components;++component){lua_pushinteger(state,component+1);lua_gettable(state,vector);
                    values[param.offset+component]=static_cast<float>(luaL_checknumber(state,-1));lua_pop(state,1);}
            }
            lua_pop(state,1);
        }
    }
    return 0;
}
}
bool FillShaderParameters(const isaac::runtime::ShaderProgramView& program,float* vertices,std::uintptr_t manager) noexcept {
    if(!g_LuaState||!IsReady()||!isaac::runtime::BuiltinCallbackEnabled(21))return true;
    if(!vertices||!lua_checkstack(g_LuaState,12))return false;
    if(!PrepareRoomEventsForRender())return false;
    const int top=lua_gettop(g_LuaState);ShaderArguments arguments{&program,vertices};
    const auto oldScope=g_InManagedCallbackDispatch.load(std::memory_order_acquire);
    const auto oldManager=g_CurrentCallbackManager.load(std::memory_order_acquire);
    const bool oldGuard=isaac::runtime::EngineGuardDispatchActive().load(std::memory_order_acquire)!=0;
    const auto oldId=g_ErrorContextCallbackId;g_ErrorContextCallbackId=21;
    isaac::runtime::EngineGuardEnterDispatch();g_InManagedCallbackDispatch.store(true,std::memory_order_release);g_CurrentCallbackManager.store(manager,std::memory_order_release);
    lua_pushcfunction(g_LuaState,ShaderValuesProtected);lua_pushlightuserdata(g_LuaState,&arguments);
    const int status=lua_pcall(g_LuaState,1,0,0);
    if(status!=LUA_OK){CaptureLuaErrorTop(g_LuaState);g_CallbackError.store(true,std::memory_order_release);}
    lua_settop(g_LuaState,top);g_CurrentCallbackManager.store(oldManager,std::memory_order_release);g_InManagedCallbackDispatch.store(oldScope,std::memory_order_release);
    g_ErrorContextCallbackId=oldId;
    if(!oldGuard)isaac::runtime::EngineGuardLeaveDispatch();
    return status==LUA_OK;
}
}

namespace LuaRuntime {
namespace {
struct PressurePinEvent {std::uintptr_t grid;bool beforeDestroy;};
int PressurePinEventProtected(lua_State* state){
 const auto* event=static_cast<const PressurePinEvent*>(lua_touserdata(state,1));
 if(event->beforeDestroy)isaac::runtime::ForgetPressurePlateAnimationPinBeforeDestroy(state,event->grid);
 else isaac::runtime::RefreshPressurePlateAnimationPinAfterNativeWrite(state,event->grid);
 return 0;
}
}
void DispatchPressurePlateAnimationPinEvent(std::uintptr_t grid,bool beforeDestroy) noexcept {
 if(!isaac::runtime::HasPressurePlateAnimationPins()||!g_LuaState||!IsOnGameThread())return;
 const int top=lua_gettop(g_LuaState);
 if(!lua_checkstack(g_LuaState,4)){g_CallbackError.store(true,std::memory_order_release);return;}
 PressurePinEvent event{grid,beforeDestroy};
 lua_pushcfunction(g_LuaState,PressurePinEventProtected);lua_pushlightuserdata(g_LuaState,&event);
 if(lua_pcall(g_LuaState,1,0,0)!=LUA_OK){CaptureLuaErrorTop(g_LuaState);g_CallbackError.store(true,std::memory_order_release);}
 lua_settop(g_LuaState,top);
}
}
