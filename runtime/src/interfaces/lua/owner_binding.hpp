#pragma once

#include "interfaces/lua/api_catalog.hpp"
#include "interfaces/lua/engine_method_api.hpp"
#include "interfaces/lua/field_api.hpp"

#include <cstddef>
#include <cstdint>

extern "C" {
#include <lua.h>
}

namespace isaac::runtime {

// One row of a family's `descriptor id -> handler` table. Families own their
// table next to the handlers they expose, so adding a method to a family means
// adding one catalog descriptor and one row here.
struct LuaHandlerBinding {
    std::uint32_t id;
    lua_CFunction handler;
};

// Attaches every catalog descriptor whose owner matches `owner` and whose id has
// a binding. Ids without a binding are skipped, so a catalog entry can never
// publish a null function, and the loop itself lives in one place instead of
// being copied into every family translation unit.
//
// `fieldRows`/`rowCount` 可以省略；给了就把整张**字段读取型 API 数据行**表一并挂上：
// 每个 API 用共享处理器 `FieldApiHandler` + 该行作为闭包上值注册。
// 为什么直接吃 `FieldApiRow`（而不是再造一张 `id → (handler, row)` 表）：id 已经在行里，
// 再抄一份等于每个 API 多花 8–16 字节只读数据 —— 而这套机制存在的意义就是把每个 API 压到
// 一行数据。行表与手写绑定表 `id` 重复时**以手写为准**（便于逐条迁移）。
//
// Returns the number of attached methods.
//: `engineRows`/`engineRowCount`（2026-09-19 批次 051）：**引擎方法类** API 的数据行
//: （`engine_method_api.hpp`）。与字段行同一套机制：共享处理器 `EngineMethodHandler` +
//: 该行作为闭包上值。绑定顺序 = 手写绑定表 → 字段行 → 引擎方法行，
//: 同 id 重复时**以靠前的为准**（便于逐条迁移：先把行加上，再把老处理器删掉）。
//: 把 `handler`（可能带 `upvalueCount` 个上值）包成**中央计时版**并压栈（批次 093）。
//:
//: **为什么要有它**：087/088 只给"看得见的那几个"处理器插了桩，于是 092 的读数里
//: EID 那条渲染回调仍有约 1.3 ms 无从归属。逐个处理器插桩要改两百处、还必然漏；
//: 在**挂载点**统一包一层，就把全部接口（以及以后新加的）一次性覆盖。
//:
//: 包装的 upvalue：`1` = 被包的函数值（可以是带自己上值的闭包），`2` = 它的接口 id。
//: 语义：`luaL_error` 照常向上传播（这一层不捕获、不清理）；错误消息的位置前缀不变
//: （`luaL_where` 对 C 函数返回空串）。
void PushTimedHandler(lua_State* state, lua_CFunction handler, std::size_t upvalueCount,
                      std::uint32_t identifier) noexcept;

//: 挂载处理器时用哪个（批次 095）。**生产构建默认不包** —— 包装每次调用要多一次 `lua_call`，
//: 而真机实测每帧有 646 次接口调用 ⇒ 那层包装本身就是 0.1~0.2 µs × 646 ≈ 65~130 µs/帧。
//: 需要"按接口分开的耗时"时，用 `PERF_API_WRAPPER=1` 构建一份诊断包。
//: 门禁 `test_perf_callback_buckets.py` 钉住"默认必须是 0"。
#ifndef PERF_API_WRAPPER
#define PERF_API_WRAPPER 0
#endif

void PushHandler(lua_State* state, lua_CFunction handler, std::size_t upvalueCount,
                 std::uint32_t identifier) noexcept;

[[nodiscard]] std::size_t AttachOwnerMethods(lua_State* state, const char* owner,
                                             const LuaHandlerBinding* bindings,
                                             std::size_t count,
                                             const FieldApiRow* fieldRows = nullptr,
                                             std::size_t rowCount = 0,
                                             const EngineMethodRow* engineRows = nullptr,
                                             std::size_t engineRowCount = 0) noexcept;

} // namespace isaac::runtime
