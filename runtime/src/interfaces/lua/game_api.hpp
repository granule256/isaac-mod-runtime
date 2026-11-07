#pragma once

#include <cstddef>
#include <cstdint>

extern "C" {
#include <lua.h>
}

namespace isaac::runtime {

// Registers the `Game` owner methods (IsPaused / IsGreedMode / GetLevel /
// GetItemPool / GetRoom) from the API catalog.
//
// The owner's binding table, its handler bodies and the shared attach loop all
// live in the layered tree: this file and `owner_binding.cpp`.
//
// Returns how many methods were attached.
[[nodiscard]] std::size_t AttachGameMethods(lua_State* state) noexcept;

// `Game` 的 `__index`：**先认字段**（`Challenge`/`Difficulty`/`TimeCounter`/`ScreenShakeOffset`），
// 认不出就落到方法表（方法表必须作为**上值 1** 传进来）。装配点在 `lua_runtime.cpp` 的
// `RegisterGameApi`。加它的理由与偏移证据见 `game_api.cpp` 里 `GameIndex` 的注释。
int GameIndex(lua_State* state);

// `Seeds` 家族的方法表（`Game:GetSeeds()` 的返回值：`IsCustomRun` / `GetStartSeed`）。
[[nodiscard]] std::size_t AttachSeedsMethods(lua_State* state) noexcept;

// `HUD` 家族的方法表（`Game:GetHUD()` 的返回值：`IsVisible` / `SetVisible(bool)`，）。
// 与 `AttachSeedsMethods` 同形：句柄不持地址，元表在 `lua_runtime.cpp` 的 `RegisterGameApi` 建。
[[nodiscard]] std::size_t AttachHudMethods(lua_State* state) noexcept;

// `Game:IsPaused()` 最后一次是否返回 true（探针读：EID 用它决定是否隐藏描述）。
[[nodiscard]] std::uint32_t LastIsPausedForProbe() noexcept;

// `Game:GetNumPlayers()` 最后一次返回值（探针：EID 的 `EID.player` 依赖它）。
[[nodiscard]] std::uint32_t LastNumPlayersForProbe() noexcept;

} // namespace isaac::runtime

#if !defined(__SWITCH__)
namespace isaac::runtime {
struct HudNativeTestBindings {
 void (*render)(void*){};
 void (*text)(void*,const char*,const char*,bool,bool){};
 void (*fortune)(void*,const void*){};
 void (*item)(void*,void*,const void*){};
};
void SetHudNativeTestBindings(HudNativeTestBindings) noexcept;
}
#endif
