#pragma once

#include <cstddef>

extern "C" {
#include <lua.h>
}

namespace isaac::runtime {

// Registers the `Mod` owner methods (AddCallback / SaveData / LoadData /
// HasData / RemoveData) from the API catalog.
//
// Slice 1 of the per-family split: the owner's binding table and registration
// loop live in this translation unit, while the handler bodies still live in
// the legacy `lua_runtime.cpp` and are reached through the bindings declared in
// `mod_handler_bindings.hpp`. Moving the bodies is a later slice.
//
// Returns how many methods were attached; unknown ids are skipped so a catalog
// entry can never attach a null function.
[[nodiscard]] std::size_t AttachModMethods(lua_State* state) noexcept;

// --- 命名回调（PC 的"自定义回调名"）--------------------------------------------
//
// 忏悔版的 `Mod:AddCallback` 除数字 `ModCallbacks` 之外还接受**字符串名**：
// 那是 Mod 自己的回调名（`Isaac.RunCallback("SOME_NAME", ...)` 触发）。EID 就用了它
// （`features/eid_bagofcrafting_search.lua:58` 的
// `EID:AddCallback("EIDCallbacks.SEARCH_NAME_CONVERSION", fn)`，而 `EID` 就是
// `RegisterMod` 返回的 Mod 对象，所以那一句直接走 `Mod:AddCallback`）。
//
// 名字形式的登记**不进** `CallbackRegistry`（那是数字 id 的注册表），而是进 Lua registry
// 里的一张按名字索引的表：`name -> { { Function = fn, Mod = <Mod 对象> }, ... }`，
// 条目形状与 PC 的 `Isaac.GetCallbacks(name)` 返回的"回调表"一致（EID 读
// `callbackData.Function` 与 `callbackData.Mod`）。表按 Lua registry 的字符串键存放，
// 所以每个 Lua 状态各有一份、`lua_close` 时自然消失，不存在跨状态悬垂引用。
//
// `RegisterNamedCallback` 从栈顶取两个值：先 `Function`（回调函数），再 `Mod`（Mod 对象），
// 两者都会被消费（`lua_pop`）。成功返回 true。
[[nodiscard]] bool RegisterNamedCallback(lua_State* state, const char* name);

// 把 `name` 名下的回调表压到栈顶（**永远是表**，没有登记时是空表）——`Isaac.GetCallbacks`。
void PushNamedCallbacks(lua_State* state, const char* name);

// 按登记顺序调用 `name` 名下的每个回调，第一个参数固定为它自己的 `Mod` 对象，
// 之后是栈上从 `firstArgument` 开始的实参（与 PC 的 `Mod:AddCallback` 回调签名一致）。
//
// PC 的 `Isaac.RunCallback` 是"跑到第一个返回值就停，并把那个值返回"（见
// `analysis/isaacdocs-snapshot/docs/Isaac.md:579`），所以这里同样在第一个**非 nil**
// 返回值处停下并把该值留在栈顶（返回 1）；一个回调都没有时返回 0（栈上不留值）。
// 回调里抛出的 Lua 错误原样向外抛（与数字路径一致）。
int RunNamedCallbacks(lua_State* state, const char* name, int firstArgument);

// `Isaac.SaveModData(modRef, data)` / `Isaac.LoadModData(modRef)`：PC 上它们与
// `Mod:SaveData(data)` / `Mod:LoadData()` 是**同一件事**（读写同一份 "saveX.dat"，
// 见 `analysis/isaacdocs-snapshot/docs/Isaac.md:505,590`），栈形状也一样
// （Mod 对象在 1、数据在 2）⇒ `Isaac` 家族那两个处理器**直接转调**下面这两个实现
// （它们住在 `mod_api.cpp` 的匿名命名空间里、只由本头文件导出），不写第二份持久化逻辑。
//
// 为什么要从 `Isaac` 这一层开出口：EID 开局时（`main.lua:1873`）判 `EID:HasData()` 之后会
// `json.decode(Isaac.LoadModData(EID))` —— 旧的桩**一个值都不返回**（nil），而运行时的
// `json.decode` 走的是 `luaL_checklstring`，拿到 nil 会直接抛 Lua 错误 ⇒ EID 的配置加载
// 当场中断（不崩、屏幕上也没提示，只留一行错误）。
//
// ⚠️ 已知小瑕疵（刻意保留）：参数个数写错时，错误信息里的名字是 `Mod:SaveData` /
// `Mod:LoadData`（这两个实现自己的名字），不是调用者写的 `Isaac.SaveModData`。
// 要把它变成"按调用者报名字"就得把函数体搬到共用的核心函数里，而门禁
// `test_lua_mod_persistence` 正是按**函数体**钉住"事件诊断包住持久化调用、且包在校验之后"
// 这条不变量的（搬走要改门禁）。报错名字略有出入，比为此改动门禁与结构更划算。
int ModSaveData(lua_State* state);
int ModLoadData(lua_State* state);

} // namespace isaac::runtime
