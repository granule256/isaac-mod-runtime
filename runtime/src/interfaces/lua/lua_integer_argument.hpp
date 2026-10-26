#pragma once

// "这个实参是不是整数"的**唯一**判据：Lua 的整数子类型，或**取整后完全相等的浮点**。
//
// ## 为什么必须统一（2026-09-18 真机证据）
//
// PC 的 Lua 绑定用 `luaL_checkinteger`，而 Lua 5.3 的 `lua_tointegerx` **会把整值浮点转成整数**
// （`3.0` ⇒ `3`，只有带小数部分才报错）。我们不少处理器却写成"只认整数子类型"的那个判据（`lua.h` 里那一族名字以 `lua_is` 开头的整数判定）
// —— 那**只认整数子类型**，于是比 PC 更严：模组只要把值经过一次除法（Lua 的 `/` **永远**产生
// 浮点）、或经过 `math.abs`/`math.min` 之类返回浮点的路径，就会在我们这里**报错**，
// 而在 PC 上正常工作。
//
// 真机实例：EID 渲染**药丸描述**时调 `spriteObj:SetFrame(anim, frameNum)`
// （`features/eid_api.lua:1349`），我们直接抛
// `Sprite:SetFrame accepts a frame number or an animation name and a frame number`
// ⇒ 整条描述画不出来（用户看到的现象是"站在药丸旁边什么信息都没有，连吃过的药丸也不显示"）。
//
// ## 用法
//
// ```cpp
// lua_Integer frame = 0;
// if (IntegerArgumentAt(state, 3, &frame)) { ...用 frame... }
// ```
//
// 返回 false 只表示"不是整值数"（含 nil、字符串、表、带小数部分的浮点），由调用方决定怎么报错。
// 报错信息里**要带上实际拿到的类型**（`luaL_typename(state, index)`）—— 这一条是给下一次
// 真机读数用的：错误文本里带着类型，就不必再猜一次。

#include <cstdint>

extern "C" {
#include <lua.h>
}

namespace isaac::runtime {

// 只判"像不像整数"、不取值的版本：给那种"一整串 `&&` 条件里顺带检查一下"的写法用。
//
// 为什么单开一个：仓库里有 33 处参数校验写成"只认整数子类型"的那个判据（取反后接在 `&&` 里），散在各种 `&&` 里
// （2026-09-18 统计）。要逐处把它们改成"先取局部变量再判"会把那些表达式改得很难读，
// 而实际上只需要换一个判据 —— 用这个函数做**纯文本替换**即可，语义与 `IntegerArgumentAt` 一致。
[[nodiscard]] inline bool IsIntegerArgument(lua_State* state, int index) noexcept {
    if (state == nullptr) return false;
    int converted = 0;
    lua_tointegerx(state, index, &converted);
    return converted != 0;
}

[[nodiscard]] inline bool IntegerArgumentAt(lua_State* state, int index,
                                            lua_Integer* out) noexcept {
    if (state == nullptr || out == nullptr) {
        return false;
    }
    int converted = 0;
    const lua_Integer value = lua_tointegerx(state, index, &converted);
    if (converted == 0) return false;
    *out = value;
    return true;
}

} // namespace isaac::runtime
