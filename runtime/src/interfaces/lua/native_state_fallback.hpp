#pragma once

// 批次 250（2026-10-01）：**原生状态读不到时的回退口径**（统一的出口 + 探针）。
//
// ## 为什么要有这个文件
//
// 本运行时里有一批接口要"顺着全局槽去解析引擎对象"（`Game`/`Level`/`Room`/`ItemPool`/
// `RoomDescriptor`）。**解析失败时原本一律抛 Lua 错误**（`"X could not read the native …"`，
// 共 41 处）。那个口径的理由写在代码里是"报错至少是可见的"——**但那是个错误的权衡**：
//
//   * 一次 Lua 错误 = **整条模组回调被摘掉**。真机现象是"模组像没装"
//     （2026-10-01 的 GoodTrip：`scripts/floor.lua:12` 抛错 ⇒ `main.lua` 从那里中断
//     ⇒ 功能全无 + 设置页也不注册）。**代价是一整个模组**，不是一个值。
//   * **PC 上这些调用根本不失败**：PC 的绑定层拿的是模组手上那个有效对象，直接读字段，
//     没有"解析"这一步；`Game():GetLevel()` 之类在 PC 上永远给对象。
//     ⇒ 用"抛错"表达**我们特有的解析失败**，等于让模组的行为偏离 PC。
//
// **本项目自己的先例已经给出了正解**（`remaining_api.cpp` 的 `PushRoomDescriptor`，批次 043）：
// 「**永远给对象**，哪怕这一刻拿不到地址」「PC 里这些字段都有确定类型 ⇒ 给该类型下的空值，
// 而不是给 nil（`nil > 0`、`nil.Type` 都会把回调打断）」。批次 043 只覆盖了"描述符地址为 0"，
// **没覆盖"连 Level 都解析不到"** —— 加载期走的正是后者，所以那次修复没救到 GoodTrip。
//
// ## 口径（三句话）
//
// 1. **读不到就返回"PC 在该类型下的默认值"**：数值 → 0（`GridIndex` 一族 → -1，与引擎的
//    "没有这个房间"表示法一致）、布尔 → `false`、对象 → **空壳句柄**（不是 nil）。
// 2. **每一处都记一笔探针**（`RecordNativeStateFallback`）—— 这是这个改动**唯一的风险控制**：
//    回退值会让"地址链错了"**看起来正常**，所以真机上必须能回答"退过多少次、退在哪一条"。
//    读数口径：`count == 0` ⇒ 地址链没问题；`count > 0` ⇒ 看 `lastApi` 回查那一条链。
// 3. **参数错误照旧抛错**（模组传错类型/个数）—— PC 在那种情形下也抛，不属于本文件的范围。

#include <atomic>
#include <cstdint>

extern "C" {
#include <lauxlib.h>
#include <lua.h>

#include "probe_gate.hpp"
}

namespace isaac::runtime {

// 接口编号（探针的 `lastApi`）。★ **只增不改**：改了会让历史读数对不上。
enum NativeFallbackApi : std::uint32_t {
    kFbNone = 0,
    // —— Level ——
    kFbLevelGetStage = 1,
    kFbLevelIsAscent = 2,
    kFbLevelGetCurses = 3,
    kFbLevelGetCurrentRoomIndex = 4,
    kFbLevelGetCurrentRoom = 5,
    kFbLevelGetCurrentRoomDesc = 6,
    kFbLevelGetRoomByIdx = 7,
    kFbLevelGetRooms = 8,
    kFbLevelGetLastRoomDesc = 9,
    // —— Room ——
    kFbRoomGetType = 10,
    kFbRoomIsMirrorWorld = 11,
    kFbRoomGetFrameCount = 12,
    kFbRoomIsClear = 13,
    kFbRoomGetGridWidth = 14,
    kFbRoomGetGridHeight = 15,
    kFbRoomGetGridSize = 16,
    kFbRoomGetGridIndex = 17,
    kFbRoomGetGridPath = 18,
    kFbRoomGetDoor = 19,
    kFbRoomGetGridEntity = 20,
    kFbRoomGetRenderScrollOffset = 21,
    // —— ItemPool ——
    kFbItemPoolGetLastPool = 22,
    kFbItemPoolGetCollectible = 23,
    kFbItemPoolIsPillIdentified = 24,
    kFbItemPoolGetPillEffect = 25,
    kFbItemPoolGetPoolForRoom = 26,
    // —— 句柄字段 ——
    kFbGridEntityVarData = 27,
    kFbRoomDescriptorGridIndex = 28,
    kFbRoomDescriptorSafeGridIndex = 29,
    kFbRoomDescriptorListIndex = 30,
    kFbRoomDescriptorVisitedCount = 31,
    kFbRoomDescriptorDisplayFlags = 32,
    kFbRoomDescriptorFlags = 33,
    kFbRoomDescriptorClear = 34,
    // —— Game ——
    kFbGameIsPaused = 35,
    kFbGameIsGreedMode = 36,
    kFbGameGetItemPool = 37,
    kFbGameGetRoom = 38,
    // —— Room（批次 269 追加）——
    //: `Room:GetRenderSurfaceTopLeft()`：**与其他回退不同**，这一条不是"这一次读不到"，
    //: 而是"偏移本身还没取证"（`Placeholder` 偏离，见 `api_deviation.cpp` 的 `0x04010025`）
    //: ⇒ 每一次调用都会记一笔。真机上这个计数**恒 > 0 是预期行为**，不是地址链坏了。
    kFbRoomGetRenderSurfaceTopLeft = 39,
    //: 批次 274：`EntityPlayer:CanPickSoulHearts()` 是**返回布尔**的那一条 —— 拿不到实体/入口时
    //: 给 `false`（「不能捡」是保守的那一边），并按纪律记一笔探针。
    kFbEntityPlayerCanPickSoulHearts = 45,
    //: 批次 277：`Entity:GetEntityFlags()` 读不到那一格时给 `0`（= 没有任何标志位）。
    kFbEntityGetEntityFlags = 46,
    // —— `Isaac` 的渲染两条（批次 269 追加）——
    //: 没有可用屏幕字体时 `Isaac.RenderText` 什么都不画（`void` 的自然降级，**不报错** ——
    //: 报错会摘掉整条渲染回调，而 PC 上这一条根本不会失败）。
    kFbIsaacRenderText = 40,
    //: `Isaac.GetTextWidth` 量不出宽度时给 `-1`。
    kFbIsaacGetTextWidth = 41,
    // —— Level（批次 270 追加）——
    //: `Level:QueryRoomTypeIndex` 读不到 `Level` 或引擎入口时给 **-1**
    //: （= 引擎自己"没有这种房间"的表示法，见 `runtime_constants.hpp` 的批次 270 段）。
    kFbLevelQueryRoomTypeIndex = 42,
    // —— EntityPlayer（批次 284 追加）——
    //: 批次 284：`EntityPlayer:IsHoldingItem()` / `IsExtraAnimationFinished()` —— 两条都是
    //: **返回布尔**的 0 参查询，拿不到实体（句柄失效）或引擎入口对不上时给 `false`
    //: （= "没拿着东西" / "额外动画已结束" 里保守的那一边），并按纪律各记一笔探针。
    kFbEntityPlayerIsHoldingItem = 47,
    kFbEntityPlayerIsExtraAnimationFinished = 48,
};

struct NativeFallbackProbe {
    std::uint32_t count{0};
    std::uint32_t lastApi{0};
};

namespace detail {

struct NativeFallbackState {
    std::atomic<std::uint32_t> count{0};
    std::atomic<std::uint32_t> lastApi{0};
};

// 函数内 `static`：模块只有一个实例（与 `api_sequence_probe.hpp` 同一手法）。
inline NativeFallbackState& NativeFallback() noexcept {
    static NativeFallbackState state;
    return state;
}

} // namespace detail

inline void RecordNativeStateFallback(NativeFallbackApi api) noexcept {
    (void)api;  // 批次 232：生产构建里这段被编译掉 ⇒ 参数必然用不上
#if EXL_DIAGNOSTIC_PROBES
    detail::NativeFallback().count.fetch_add(1, std::memory_order_relaxed);
    detail::NativeFallback().lastApi.store(static_cast<std::uint32_t>(api),
                                           std::memory_order_relaxed);
#endif
}

[[nodiscard]] inline NativeFallbackProbe NativeFallbackProbeSnapshot() noexcept {
    detail::NativeFallbackState& state = detail::NativeFallback();
    NativeFallbackProbe probe{};
    probe.count = state.count.load(std::memory_order_acquire);
    probe.lastApi = state.lastApi.load(std::memory_order_acquire);
    return probe;
}

// —— 三种回退出口（集中在这里，免得 41 处各写各的、口径漂开）——
//
// 为什么是三个函数而不是一个模板：回退值的**类型**不同（整数 / 布尔 / 对象），
// 而"对象"那条必须由各接口自己构造（`Room`/`RoomDescriptor`/`ItemPool` 的句柄各不相同）。

inline int PushNativeFallbackInteger(lua_State* state, NativeFallbackApi api,
                                     lua_Integer value) noexcept {
    RecordNativeStateFallback(api);
    lua_pushinteger(state, value);
    return 1;
}

inline int PushNativeFallbackBoolean(lua_State* state, NativeFallbackApi api,
                                     bool value) noexcept {
    RecordNativeStateFallback(api);
    lua_pushboolean(state, value ? 1 : 0);
    return 1;
}

// 少数几条接口的 PC 语义**本来就是"可能没有"**（`Room:GetDoor` 对没有门的槽位给 nil、
// `Room:GetGridEntity` 对空格子给 nil）⇒ 读不到时与"没有"同口径（nil），
// 而不是硬造一个对象出来 —— "给对象"那条规矩只适用于 PC 保证有对象的地方。
inline int PushNativeFallbackNil(lua_State* state, NativeFallbackApi api) noexcept {
    RecordNativeStateFallback(api);
    lua_pushnil(state);
    return 1;
}

} // namespace isaac::runtime
