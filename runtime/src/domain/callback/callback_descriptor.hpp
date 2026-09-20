#pragma once

#include "domain/mod/mod_handle.hpp"
#include "domain/runtime/thread_affinity.hpp"

#include <cstdint>

namespace isaac::runtime {

// ModCallbacks identifier (MC_POST_UPDATE, MC_POST_RENDER, ...). Kept as a
// plain integer so the domain layer does not depend on the Lua API catalogue.
using CallbackId = std::uint32_t;

// Values match the PC ModCallbacks table the Runtime exposes to Lua, so a Mod
// that stores or compares the number behaves like it does on PC. The table
// itself comes from `pc_lua_enum_data.cpp` (generated from the PC `enums.lua`).
//
// `MC_POST_UPDATE` used to be 0 here, which is the PC value of `MC_NPC_UPDATE`;
// 2026-09-12 修正为 1（同时把 Lua 侧的表改成生成表）。
inline constexpr CallbackId kCallbackPostUpdate = 1;
inline constexpr CallbackId kCallbackPostRender = 2;
inline constexpr CallbackId kCallbackInputAction = 13;
// 游戏开局：值必须等于 PC `ModCallbacks` 表里的 `MC_POST_GAME_STARTED`（15）。
inline constexpr CallbackId kCallbackPostGameStarted = 15;
inline constexpr CallbackId kCallbackPreGetCollectible = 62;
// --- 每帧事件（回调面地基，2026-09-18）----------------------------------------
//
// 这五种在 PC 上由引擎在事件发生的**那一刻**触发，而我们没有对应挂点；它们用"每帧时机 +
// 状态差分"实现（见 `lua_runtime.cpp` 的 `DispatchFrameEvents`）。取值同样必须等于 PC 表：
// 模组会把 `ModCallbacks.MC_POST_NEW_ROOM` 这个数字原样传给 `Mod:AddCallback`，
// 而我们把它直接当内部 id 用（见 `ResolveCallbackId`）。
inline constexpr CallbackId kCallbackPostPlayerInit = 9;
inline constexpr CallbackId kCallbackPostNewLevel = 18;
inline constexpr CallbackId kCallbackPostNewRoom = 19;
inline constexpr CallbackId kCallbackPostPickupInit = 34;
inline constexpr CallbackId kCallbackPostPickupUpdate = 35;
// --- 实体族回调（2026-09-18 批次 010）------------------------------------------
//
// PC 在"某个实体更新/渲染/刚出现"的那一刻逐实体触发这一族回调。我们没有那么多挂点，
// 同样用"每帧时机 + 类型分派"实现（见 `lua_runtime.cpp` 的实体族派发）。取值必须等于 PC
// `ModCallbacks` 表里的值 —— 模组把 `ModCallbacks.MC_POST_TEAR_UPDATE` 这个数字原样传给
// `Mod:AddCallback`，我们直接当内部 id 用。
//
// 命名规则（被读数工具的门禁钉住）：`MC_XXX_YYY` ↔ `kCallbackXxxYyy`。
inline constexpr CallbackId kCallbackNpcUpdate = 0;
inline constexpr CallbackId kCallbackPostPeffectUpdate = 4;
inline constexpr CallbackId kCallbackFamiliarUpdate = 6;
inline constexpr CallbackId kCallbackFamiliarInit = 7;
inline constexpr CallbackId kCallbackPostFamiliarRender = 25;
inline constexpr CallbackId kCallbackPostNpcInit = 27;
inline constexpr CallbackId kCallbackPostPlayerUpdate = 31;
inline constexpr CallbackId kCallbackPostPlayerRender = 32;
inline constexpr CallbackId kCallbackPostPickupRender = 36;
inline constexpr CallbackId kCallbackPostTearInit = 39;
inline constexpr CallbackId kCallbackPostTearUpdate = 40;
inline constexpr CallbackId kCallbackPostTearRender = 41;
inline constexpr CallbackId kCallbackPostProjectileInit = 43;
inline constexpr CallbackId kCallbackPostProjectileUpdate = 44;
inline constexpr CallbackId kCallbackPostProjectileRender = 45;
inline constexpr CallbackId kCallbackPostLaserInit = 47;
inline constexpr CallbackId kCallbackPostLaserUpdate = 48;
inline constexpr CallbackId kCallbackPostLaserRender = 49;
inline constexpr CallbackId kCallbackPostKnifeInit = 50;
inline constexpr CallbackId kCallbackPostKnifeUpdate = 51;
inline constexpr CallbackId kCallbackPostKnifeRender = 52;
inline constexpr CallbackId kCallbackPostEffectInit = 54;
inline constexpr CallbackId kCallbackPostEffectUpdate = 55;
inline constexpr CallbackId kCallbackPostEffectRender = 56;
inline constexpr CallbackId kCallbackPostBombInit = 57;
inline constexpr CallbackId kCallbackPostBombUpdate = 58;
inline constexpr CallbackId kCallbackPostBombRender = 59;
// 目前已挂钩派发点的回调种类上限（含未挂钩但允许登记的）：PC 表到 73。
inline constexpr CallbackId kCallbackMaximumId = 73;

// One registered callback. The Lua function is referenced by registry index,
// never by a raw lua_State pointer or C++ function pointer.
struct CallbackDescriptor {
    CallbackId id{0};
    ModHandle owner{};
    ThreadAffinity affinity{ThreadAffinity::ManagedCallback};
    // Lua registry reference of the callback function.
    int luaReference{0};
    // Lua registry reference of the Mod userdata passed as the first argument.
    int modReference{0};

    // MC_POST_UPDATE is 0, so the callback id itself is always a valid value;
    // validity is about having an owner and a Lua registry reference.
    [[nodiscard]] constexpr bool valid() const noexcept {
        return owner.valid() && luaReference != 0;
    }
};

} // namespace isaac::runtime
