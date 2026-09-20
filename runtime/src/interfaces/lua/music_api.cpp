#include "interfaces/lua/music_api.hpp"

#include "interfaces/lua/owner_binding.hpp"
#include "interfaces/lua/lua_integer_argument.hpp"

#include "lua_object_handles.hpp"
#include "lua_runtime_state.hpp"
#if defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 48
#include "hook_manager.hpp"
#endif

#include <cstdint>

extern "C" {
#include <lauxlib.h>
}

namespace isaac::runtime {
namespace {

using LuaRuntime::kMusicMetatable;
using LuaRuntime::MusicGetCurrentMusicIdThunk;
using LuaRuntime::MusicPauseThunk;
using LuaRuntime::MusicResumeThunk;
using LuaRuntime::ResolveMusicGetCurrentMusicId;
using LuaRuntime::ResolveMusicPause;
using LuaRuntime::ResolveMusicResume;

int MusicGetCurrentMusicId(lua_State* state);
int MusicPause(lua_State* state);
int MusicResume(lua_State* state);

constexpr LuaHandlerBinding kMusicHandlers[] = {
    {0x06010001, &MusicGetCurrentMusicId},
    {0x06010002, &MusicPause},
    {0x06010003, &MusicResume},
};

constexpr char kMusicOwner[] = "MusicManager";

// ---- `SFXManager()`（批次 045，为 GoodTrip 补）------------------------------------------
//
// PC 里 `SFXManager()` 是**全局函数**，返回引擎音效管理器单例；模组用
// `SFXManager():Play(SoundEffect, Volume, Pitch, Loop, Pan)` 放音（GoodTrip `scripts/trip.lua:8/74`）。
// 缺它时是 "attempt to call a nil value (global 'SFXManager')" ⇒ **模组整个加载失败**（真机实测）。
//
// **本批只补"对象与方法都在、调用不报错"**：引擎音效单例与 `Play` 的地址尚未取证 ⇒
// `Play` 是**明确的空实现**（不假装成功、也不报错），`IsPlaying` 恒 false；形状与 PC 一致。
// 音效与音乐同属"声音"⇒ 复用域 `0x06`、取域内空号 0x0004/0x0005（文件与 owner 的对应关系
// 由契约测试那张"文件 → 允许的 owner 集合"表登记）。
struct SfxManagerHandle {
    int reserved{0};
};

// `SFXManager:Play(int SoundEffect, float Volume, float Pitch, boolean Loop, float Pan)`。
// 参数校验**只钉"至少一个整数"**：不钉范围、不钉个数 —— 比 PC 严害过我们很多次。
int SfxManagerPlay(lua_State* state) {
    if (lua_gettop(state) < 2 || !isaac::runtime::IsIntegerArgument(state, 2)) {
        return luaL_error(state, "SFXManager:Play accepts a sound effect id");
    }
    return 0;  // 明确空实现：引擎音效通道未取证，不假装成功
}

int SfxManagerIsPlaying(lua_State* state) {
    if (lua_gettop(state) != 2 || !isaac::runtime::IsIntegerArgument(state, 2)) {
        return luaL_error(state, "SFXManager:IsPlaying accepts a sound effect id");
    }
    lua_pushboolean(state, 0);
    return 1;
}


constexpr LuaHandlerBinding kSfxManagerHandlers[] = {
    {0x06010004, &SfxManagerPlay},
    {0x06010005, &SfxManagerIsPlaying},
};

constexpr char kSfxManagerOwner[] = "SFXManager";

// Resolving a Music call is two steps that must not be reordered: the method
// guard verdict first (the bound address must still hold the expected
// instructions), then the callback's Manager-derived Music object. Both steps
// live in the legacy translation unit; the handler only sees the verdict.
int MusicGetCurrentMusicId(lua_State* state) {
    luaL_checkudata(state, 1, kMusicMetatable);
    if (lua_gettop(state) != 1) {
        return luaL_error(state, "Music:GetCurrentMusicID accepts no arguments");
    }
    const std::uintptr_t method = MusicGetCurrentMusicIdThunk();
    std::uintptr_t music = 0;
    if (!ResolveMusicGetCurrentMusicId(method, &music)) {
        return luaL_error(state, "Music:GetCurrentMusicID native bindings are unavailable");
    }
    using GetCurrentMusicIdFn = int (*)(const void*);
    lua_pushinteger(state, reinterpret_cast<GetCurrentMusicIdFn>(method)(reinterpret_cast<const void*>(music)));
    return 1;
}

int MusicPause(lua_State* state) {
    luaL_checkudata(state, 1, kMusicMetatable);
    if (lua_gettop(state) != 1) {
        return luaL_error(state, "Music:Pause accepts no arguments");
    }
    const std::uintptr_t method = MusicPauseThunk();
    std::uintptr_t music = 0;
    if (!ResolveMusicPause(method, &music)) {
        return luaL_error(state, "Music:Pause native bindings are unavailable");
    }
#if defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 48
    Stage48ArmMusicReplayProbe();
#endif
    using PauseFn = void (*)(void*);
    reinterpret_cast<PauseFn>(method)(reinterpret_cast<void*>(music));
    return 0;
}

int MusicResume(lua_State* state) {
    luaL_checkudata(state, 1, kMusicMetatable);
    if (lua_gettop(state) != 1) {
        return luaL_error(state, "Music:Resume accepts no arguments");
    }
    const std::uintptr_t method = MusicResumeThunk();
    std::uintptr_t music = 0;
    if (!ResolveMusicResume(method, &music)) {
        return luaL_error(state, "Music:Resume native bindings are unavailable");
    }
    using ResumeFn = void (*)(void*);
    reinterpret_cast<ResumeFn>(method)(reinterpret_cast<void*>(music));
    return 0;
}

} // namespace

std::size_t AttachMusicMethods(lua_State* state) noexcept {
    return AttachOwnerMethods(state, kMusicOwner, kMusicHandlers,
                              sizeof(kMusicHandlers) / sizeof(kMusicHandlers[0]));
}

//: `SFXManager()` 返回对象的构造器（**元表与全局由中枢 `lua_runtime.cpp` 建** —— 家族 TU
//: 不许自己写注册/建表循环，这是契约门禁的明文要求）。
int SfxManagerCtor(lua_State* state) {
    if (lua_gettop(state) != 0) {
        return luaL_error(state, "SFXManager accepts no arguments");
    }
    auto* handle = static_cast<SfxManagerHandle*>(lua_newuserdata(state, sizeof(SfxManagerHandle)));
    handle->reserved = 0;
    luaL_getmetatable(state, "IsaacRuntime.SFXManager");
    lua_setmetatable(state, -2);
    return 1;
}

//: `SFXManager` 的**方法表**（由中枢建元表时调用；本文件不建元表、也不注册全局）。
std::size_t AttachSfxManagerMethods(lua_State* state) noexcept {
    return AttachOwnerMethods(state, kSfxManagerOwner, kSfxManagerHandlers,
                              sizeof(kSfxManagerHandlers) / sizeof(kSfxManagerHandlers[0]));
}

} // namespace isaac::runtime
