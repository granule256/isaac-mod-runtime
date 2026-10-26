#include "interfaces/lua/rng_api.hpp"

#include "infrastructure/call/engine_call_access.hpp"  // 引擎调用层（批次 110：调引擎只在这里转换签名）
#include "interfaces/lua/lua_integer_argument.hpp"
#include "interfaces/lua/owner_binding.hpp"

#include "lua_object_handles.hpp"
#include "infrastructure/memory/engine_field_access.hpp"
#include "infrastructure/memory/engine_memory_guard.hpp"
#include "lua_runtime_state.hpp"
#include "runtime_constants.hpp"

#include <cstddef>
#include <cstdint>
#include <cstring>
#include <limits>

extern "C" {
#include <lauxlib.h>
}

//: 引擎调用层的短别名（批次 110）：本文件里"把已核对过的地址变成可调用签名"只走它。
namespace engine_call = isaac::runtime::engine_call;

namespace isaac::runtime {

void* TryResolveRngObject(LuaRuntime::RngHandle* handle, bool writable) noexcept {
    if (handle == nullptr) return nullptr;
    if (handle->resolver == nullptr) { return handle->storage.data(); }
    const auto address = handle->resolver(handle);
    if (address == 0 || !engine_memory::EngineMemoryReadable(address, kRngObjectSize) ||
        (writable && !engine_memory::EngineMemoryWritable(address, kRngObjectSize))) {
        return nullptr;
    }
    return engine_memory::AsObject(address);
}

void* ResolveRngObject(lua_State* state, LuaRuntime::RngHandle* handle, bool writable) {
    auto* object=TryResolveRngObject(handle,writable);
    if (object == nullptr) luaL_error(state, "RNG reference is no longer available");
    return object;
}

namespace {

// 句柄体就是"一份 RNG 对象快照"（16 字节：种子 + 移位三元组），必须与引擎里 `RNG` 的尺寸
// 一致 —— 否则 `RNG:SetSeed`/`Next` 打到引擎函数上的那块内存会越界（证据见
// `runtime_constants.hpp` 的 `kRngObjectSize` 注释）。
static_assert(sizeof(LuaRuntime::RngHandle::storage) == kRngObjectSize,
              "the RNG handle body must match the engine RNG object size");

using LuaRuntime::kRngMetatable;
using LuaRuntime::RngHandle;
using LuaRuntime::RngNextThunk;
using LuaRuntime::RngRandomThunk;
using LuaRuntime::RngRandomUintThunk;
using LuaRuntime::RngSetSeedThunk;
using LuaRuntime::ValidateRngNextBinding;
using LuaRuntime::ValidateRngRandomBinding;
using LuaRuntime::ValidateRngRandomUintBinding;
using LuaRuntime::ValidateRngSetSeedBinding;

int RngSetSeed(lua_State* state);
int RngNext(lua_State* state);
int RngGetSeed(lua_State* state);
// 批次 195（2026-09-29）：PC 的 `RNG:RandomInt(int Max)` / `RNG:RandomFloat()`。
int RngRandomInt(lua_State* state);
int RngRandomFloat(lua_State* state);

constexpr LuaHandlerBinding kRngHandlers[] = {
    {0x07010001, &RngSetSeed},
    {0x07010002, &RngNext},
    {0x07010003, &RngGetSeed},
    // 批次 195：id 取域内**下一个空号**（`0x0003` 之后连着的两个，见 `api_catalog.cpp`
    // 同两行的注释）—— 与 `Isaac`/`EntityPlayer` 家族取号的规则相同。
    {0x07010004, &RngRandomInt},
    {0x07010005, &RngRandomFloat},
};

constexpr char kRngOwner[] = "RNG";

int RngSetSeed(lua_State* state) {
    auto* rng = static_cast<RngHandle*>(luaL_checkudata(state, 1, kRngMetatable));
    if (lua_gettop(state) != 3 || !isaac::runtime::IsIntegerArgument(state, 2) || !isaac::runtime::IsIntegerArgument(state, 3)) {
        return luaL_error(state, "RNG:SetSeed accepts seed and shift integers");
    }
    const lua_Integer seed = lua_tointegerx(state, 2, nullptr);
    const lua_Integer shift = lua_tointegerx(state, 3, nullptr);
    // PC 0x84582B取lua_Integer后只将eax传入uint32种子，允许和式溢出取低32位。
    if (shift < 0 || static_cast<std::uint64_t>(shift) > std::numeric_limits<std::uint32_t>::max()) {
        return luaL_error(state, "RNG:SetSeed arguments are outside uint32 range");
    }
    const std::uintptr_t method = RngSetSeedThunk();
    if (!ValidateRngSetSeedBinding(method)) {
        return luaL_error(state, "RNG:SetSeed native bindings are unavailable");
    }
    using SetSeedFn = void (*)(void*, std::uint32_t, std::uint32_t);
    engine_call::AsFunction<SetSeedFn>(method)(ResolveRngObject(state, rng, true),
                                               static_cast<std::uint32_t>(seed),
                                               static_cast<std::uint32_t>(shift));
    return 0;
}

int RngNext(lua_State* state) {
    auto* rng = static_cast<RngHandle*>(luaL_checkudata(state, 1, kRngMetatable));
    if (lua_gettop(state) != 1) {
        return luaL_error(state, "RNG:Next accepts no arguments");
    }
    const std::uintptr_t method = RngNextThunk();
    if (!ValidateRngNextBinding(method)) {
        return luaL_error(state, "RNG:Next native bindings are unavailable");
    }
    using NextFn = void (*)(void*);
    void* object = ResolveRngObject(state, rng, true);
    engine_call::AsFunction<NextFn>(method)(object);
    std::uint32_t value = 0;
    std::memcpy(&value, object, sizeof(value));
    lua_pushinteger(state, static_cast<lua_Integer>(value));
    return 1;
}

// `RNG:GetSeed()`（批次 13，2026-09-16）：PC 文档 `analysis/isaacdocs-snapshot/docs/RNG.md:56`
// —— "Returns the current seed of the RNG object"，返回类型 `int`。
//
// 为什么不需要引擎调用：RNG 的种子就是它自己的**头 4 字节**。证据在
// `RNG::SetSeed(uint seed, uint shift) @ 0x44E3C0`：第一条就是 `str w1, [x0]`（w1 即 seed 参数），
// 随后才写 `[x0+0x4..0xB]`（移位三元组）与 `[x0+0xC]`；`RNG::Next() @ 0x44E4E4` 也是原地更新
// `[x19]` 后把新值返回。所以本句柄里那 16 字节的**前半**就是引擎语义上的"当前种子"。
//
// 与 `SetSeed`/`Next` 不同，这条**不查** `InManagedCallbackScope()`：它只读本句柄自己的字节，
// 不碰任何引擎状态（PC 侧 `RNG():GetSeed()` 在脚本顶层同样是合法的）。
int RngGetSeed(lua_State* state) {
    auto* rng = static_cast<RngHandle*>(luaL_checkudata(state, 1, kRngMetatable));
    if (lua_gettop(state) != 1) {
        return luaL_error(state, "RNG:GetSeed accepts no arguments");
    }
    std::uint32_t seed = 0;
    std::memcpy(&seed, ResolveRngObject(state, rng, false), sizeof(seed));
    lua_pushinteger(state, static_cast<lua_Integer>(seed));
    return 1;
}

// 批次 195（2026-09-29）：`RNG:RandomInt(int Max)` / `RNG:RandomFloat()`。
//
// **为什么必须补这两条**（不是"顺手加的"）：语料里的 Trinity 写的是
// `GetCollectibleRNG(CollectibleType.BIRTHRIGHT):RandomFloat()`（`analysis/mod-corpus/Trinity/main.lua:173`）
// —— 本批刚把四条 `Get*RNG` 从恒 nil 改成真返回 RNG 句柄，链上就只剩 `RandomFloat` 这一环是 nil
// ⇒ 那一条仍然抛 `attempt to call a nil value`（回调被派发器整条摘掉）。PC 契约
// （`analysis/isaacdocs-snapshot/docs/RNG.md:101-104` 与 `:124-127`）两条都明写
// "**Since this mutates the RNG object**, you should use this method with care."
// ⇒ 它们**会推进**这颗 RNG，与 `SetSeed`/`Next` 同族。
//
// 引擎底座（地址与入口 16 字节指纹见 `runtime_constants.hpp` 的 `kRngRandomUintOffset` /
// `kRngRandomOffset`；`Hook 安装`时按同一条判据核对后发布）：
//   * `RNG::Random(unsigned Max)` → `uint`（引擎自己在 `UsePill` 里 `.Random(50)`、`UseCard` 里 `.Random(97)`）；
//   * `RNG::Random()` → `float`。
//
// ★ 与另外三条一样，这里操作的是**本句柄自己的 16 字节快照**（PC 改的是实体里那颗 RNG）——
//   这正是 `api_deviation.cpp` 的 `0x0E010054` 与 `0x0E010033`~`0x0E010036` 那几条 `design`
//   登记的口径差异；"同一个句柄上连续 `Next()`/`RandomInt()` 得到的序列与 PC 相同"。
//
// 参数口径：PC 的签名是 `int RandomInt(int Max)`；引擎收的是 `unsigned`。只要求"是一个整数、
// 且能放进 uint32"，**不做别的范围校验**（与 `SetSeed` 同一口径）；绑定没发布时报错而不是
// 编一个随机数（假随机数比报错更难查，而且会导致模组偷偷走进错误分支）。
int RngRandomInt(lua_State* state) {
    auto* rng = static_cast<RngHandle*>(luaL_checkudata(state, 1, kRngMetatable));
    lua_Integer maximum = 0;
    if (lua_gettop(state) != 2 || !isaac::runtime::IsIntegerArgument(state, 2) ||
        (maximum = lua_tointegerx(state, 2, nullptr)) < 0 ||
        static_cast<std::uint64_t>(maximum) > std::numeric_limits<std::uint32_t>::max()) {
        return luaL_error(state, "RNG:RandomInt accepts one integer maximum inside uint32 range");
    }
    const std::uintptr_t method = RngRandomUintThunk();
    if (!ValidateRngRandomUintBinding(method)) {
        return luaL_error(state, "RNG:RandomInt native bindings are unavailable");
    }
    using RandomUintFn = std::uint32_t (*)(void*, std::uint32_t);
    const std::uint32_t value =
        engine_call::AsFunction<RandomUintFn>(method)(ResolveRngObject(state, rng, true),
                                                      static_cast<std::uint32_t>(maximum));
    lua_pushinteger(state, static_cast<lua_Integer>(value));
    return 1;
}

int RngRandomFloat(lua_State* state) {
    auto* rng = static_cast<RngHandle*>(luaL_checkudata(state, 1, kRngMetatable));
    if (lua_gettop(state) != 1) {
        return luaL_error(state, "RNG:RandomFloat accepts no arguments");
    }
    const std::uintptr_t method = RngRandomThunk();
    if (!ValidateRngRandomBinding(method)) {
        return luaL_error(state, "RNG:RandomFloat native bindings are unavailable");
    }
    using RandomFn = float (*)(void*);
    const float value = engine_call::AsFunction<RandomFn>(method)(ResolveRngObject(state, rng, true));
    lua_pushnumber(state, static_cast<lua_Number>(value));
    return 1;
}

} // namespace

std::size_t AttachRngMethods(lua_State* state) noexcept {
    return AttachOwnerMethods(state, kRngOwner, kRngHandlers,
                              sizeof(kRngHandlers) / sizeof(kRngHandlers[0]));
}

} // namespace isaac::runtime
