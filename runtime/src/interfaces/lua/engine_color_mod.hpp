#pragma once

#include <cstddef>

#include "lua_object_handles.hpp"
#include "interfaces/lua/color_api.hpp"
#include "runtime_constants.hpp"

extern "C" {
#include <lauxlib.h>
#include <lua.h>
}

namespace isaac::runtime {

//: 引擎侧的 `ColorMod`（44 字节）。
//:
//: ★ 布局与尺寸的取证在 `runtime_constants.hpp` 的 `kColorModSize` 段（`tint` 在 `+0x00`、
//: 2026-10-10 更正：colorize 在 +0x10，shift 在 +0x20；Reset 清零不足以定语义。
//: `static_assert` 把字段数钉在**编译期** —— 改错字段数当场编译红，不会等到真机上颜色不对。
//:
//: ★ 为什么单独成一个头（批次 271）：这段结构原来只在 `game_api.cpp` 的 `GameSpawnParticles`
//: **函数内**（批次 267，理由见那处的长注释），而本批 `Entity:SetColor` 的第一个参数**也是**
//: `ColorMod const&` ⇒ 再抄一份就是**第三份**拷贝（`sprite_api.cpp` 写 `Sprite.Color` 时还有
//: 一份"同源映射"）。**"颜色 → `ColorMod`"的映射从此只有这一份**。
struct EngineColorMod {
    float tint[4];      // +0x00：R/G/B/A（乘）
    float colorize[4];  // +0x10：染色 RGB 与染色强度（SetColorize）
    float shift[3];     // +0x20：RO/GO/BO，加在纹理颜色上（SetOffset）
};
static_assert(sizeof(EngineColorMod) == kColorModSize,
              "ColorMod 的字段数变了（见 kColorModSize 的取证）");

static_assert(offsetof(EngineColorMod, tint) == kColorModTintOffset);
static_assert(offsetof(EngineColorMod, colorize) == kColorModColorizeOffset);
static_assert(offsetof(EngineColorMod, shift) == kColorModShiftOffset);

// Lua 七参 Color 未设置染色；完整值赋予引擎时四个染色分量应为 0。
[[nodiscard]] inline EngineColorMod EngineColorModFromHandle(
        const LuaRuntime::ColorHandle& handle) noexcept {
    EngineColorMod out{};
    out.tint[0] = handle.red;
    out.tint[1] = handle.green;
    out.tint[2] = handle.blue;
    out.tint[3] = handle.alpha;
    out.colorize[0] = handle.colorizeRed;
    out.colorize[1] = handle.colorizeGreen;
    out.colorize[2] = handle.colorizeBlue;
    out.colorize[3] = handle.colorizeAmount;
    out.shift[0] = handle.offsetRed;
    out.shift[1] = handle.offsetGreen;
    out.shift[2] = handle.offsetBlue;
    return out;
}

//: 契约缺省：PC 的 `Color.Default` 就是**白色不透明** ⇒ tint 全 1、其余保持 0。
[[nodiscard]] inline EngineColorMod DefaultEngineColorMod() noexcept {
    EngineColorMod color{};
    color.tint[0] = 1.0F;
    color.tint[1] = 1.0F;
    color.tint[2] = 1.0F;
    color.tint[3] = 1.0F;
    return color;
}

//: 从栈上第 `index` 格的 Lua `Color` 句柄填一份 `ColorMod`：
//: `tint` = R/G/B/A、`shift` = 三个颜色偏移分量（colorize 留 0），
//: 与 `sprite_api.cpp` 写 `Sprite.Color` 时的映射**同源**。
//:
//: 返回 `false` 表示那一格不是 `Color` 句柄（**不抛错**）—— 由调用方决定是报错
//: （参数类型写错了，PC 也会报）还是按缺省值处理（可选参数缺席）。
[[nodiscard]] inline bool FillEngineColorMod(lua_State* state, int index,
                                             EngineColorMod* out) noexcept {
    if (state == nullptr || out == nullptr) {
        return false;
    }
    auto* handle = TryColorArgument(state, index);
    if (handle == nullptr) {
        return false;
    }
    *out = EngineColorModFromHandle(*handle);
    return true;
}

//: 批次 343（2026-10-04）：`FillEngineColorMod` 的**反方向** —— 把一份引擎 `ColorMod`
//: （44 字节，tint 起点 +0x00、offset 起点 +0x20）压成一个 Lua `Color` 句柄（`kColorMetatable`）。
//:
//: 为什么需要它：`Entity:GetColor()`（PC 绑定 `0x4F3DE0` = `lea eax,[ecx+0xE4]; ret`）在 PC 上
//: **按值**返回一个 `Color`；Switch 侧那一格是 `Entity + 0x138` 的 44 字节 `ColorMod`
//: （取证见 `runtime_constants.hpp` 的 `kEntityGetColorOffset` 段）⇒ 我们要把它读出来、
//: 按 `tint → R/G/B/A`、`shift → RO/GO/BO` 的对应关系压回一个真正的 Lua `Color` 句柄
//: （模组要能读 `.R/.G/.B/.A`、要能直接喂回 `SetColor`）。
//:
//: ★★ **与 `FillEngineColorMod` 是同一份映射的两个方向** ⇒ 必须同住这一个头文件
//:   （批次 271 立的"颜色映射只有一份"纪律；两处各写一份迟早只改一边）。
//: ★ **逐格直拷、不乘 255**：`ColorMod::Reset` 把 tint 写成 `0x3F800000`（`1.0f`）、
//:   `ColorMod::SetTint` 直接把 float 寄存器 `str` 进去 ⇒ 引擎侧就是 0..1 的 float，
//:   而我们的 `ColorHandle` 也是 0..1 的 float（与 PC 一致）。
//: ★ +0x1C 是染色强度，不是第四个 offset；offset 只有 +0x20/+0x24/+0x28。
//: ★ **值拷贝**：压进去的是调用瞬间那 7 个 float 的副本，不是引擎内存的活引用 ——
//:   与 PC 的"按值返回"逐值一致，**不是偏离**（对照 `RngSnapshot` 那条登记的偏离）。
// 2026-10-14：在既有值句柄上回填，setter无需分配另一个userdata；11分量映射只有一份。
inline void FillLuaColorHandleFromEngineColorMod(LuaRuntime::ColorHandle& handle,
                                                const EngineColorMod& value) noexcept {
    handle.colorizeRed = value.colorize[0];
    handle.colorizeGreen = value.colorize[1];
    handle.colorizeBlue = value.colorize[2];
    handle.colorizeAmount = value.colorize[3];
    handle.red = value.tint[0];
    handle.green = value.tint[1];
    handle.blue = value.tint[2];
    handle.alpha = value.tint[3];
    handle.offsetRed = value.shift[0];
    handle.offsetGreen = value.shift[1];
    handle.offsetBlue = value.shift[2];
}

inline void PushLuaColorFromEngineColorMod(lua_State* state,
                                           const EngineColorMod& value) noexcept {
    auto* handle = static_cast<LuaRuntime::ColorHandle*>(
        lua_newuserdata(state, sizeof(LuaRuntime::ColorHandle)));
    FillLuaColorHandleFromEngineColorMod(*handle,value);
    luaL_getmetatable(state, LuaRuntime::kColorMetatable);
    lua_setmetatable(state, -2);
}

} // namespace isaac::runtime
