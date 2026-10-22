#include "interfaces/lua/api100_bindings.hpp"
#include "interfaces/lua/music_api.hpp"

#include "infrastructure/call/engine_call_access.hpp"  // 引擎调用层（批次 110：调引擎只在这里转换签名）
#include "interfaces/lua/api_call_stats.hpp"           // 批次 154：编号保险的计数
#include "interfaces/lua/engine_method_api.hpp"        // 批次 154：`CheckMusicId`
#include "interfaces/lua/engine_method_lookup.hpp"     // 批次 185：`EngineOffsetAddress<IsReadable>`
#include "interfaces/lua/owner_binding.hpp"
#include "interfaces/lua/lua_integer_argument.hpp"

#include "lua_object_handles.hpp"
#include "lua_runtime_state.hpp"
#include "runtime_constants.hpp"  // 批次 185/408：`kSoundEffectsIsPlayingOffset` / `kSoundEffectsPlayOffset`
#if defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 48
#include "hook_manager.hpp"
#endif

#include <atomic>
#include <bit>
#include <cstdint>

extern "C" {
#include <lauxlib.h>
}

//: 引擎调用层的短别名（批次 110）：本文件里"把已核对过的地址变成可调用签名"只走它。
namespace engine_call = isaac::runtime::engine_call;

// ============================================================================
// 批次 408（2026-10-08）：`SFXManager:Play` 的**真机探针**（无条件计数，读数工具按符号直读）
// ============================================================================
//
// 目的：把"模组到底调没调 Play / 我们有没有把调用递进引擎 / 递进去时参数是什么 / 没递进去时
// 卡在哪一步"这几件事在真机上一眼分开。形状照同族 `g_Music*`（`g_MusicResolveFailure`、
// `g_MusicGetCurrentMusicId`…）—— 都是**无条件写**的普通全局量，不是探针包专属
// （`probe_gate.hpp` 那套只关"会做事"的采集；这里每次调用只多几次原子写，代价在噪声级，
//  而关掉它们会让这条 API 永远"哑着且看不见"，正是本批要修的病灶）。
//
//   `g_SfxPlayCalls`     —— 进了处理器且参数形状合法几次（"模组调了没"）
//   `g_SfxPlayDelivered` —— 真的把调用递进引擎几次（"我们递进去了没"；`Calls - Delivered` 就是被守卫挡下的）
//   `g_SfxPlayLast*`     —— 最近一次**递进去**的实参（id/volume/frameDelay/loop/pitch/pan）
//   `g_SfxPlayLastFailure` —— 最近一次**没递进去**的失败码（0 = 没失败过；1/2/3/4 同 `g_MusicResolveFailure`）
//
// ★ 浮点参数按**位模式**存 `u32`（`std::bit_cast`），读数端按 `float` 解 —— 与 `g_Isaac*` 一族
//   存 `int32` 位模式的做法同形（u32 全局必须掩码，见 `tools/read_device_state_via_gdb.py` 的
//   `U32ReadMaskingTests`）。
extern "C" {
std::atomic<std::uint32_t> g_SfxPlayCalls{0};
std::atomic<std::uint32_t> g_SfxPlayDelivered{0};
std::atomic<std::uint32_t> g_SfxPlayLastId{0};          // int32 位模式
std::atomic<std::uint32_t> g_SfxPlayLastVolume{0};      // float 位模式
std::atomic<std::uint32_t> g_SfxPlayLastFrameDelay{0};  // int32 位模式
std::atomic<std::uint32_t> g_SfxPlayLastLoop{0};        // 0 / 1
std::atomic<std::uint32_t> g_SfxPlayLastPitch{0};       // float 位模式
std::atomic<std::uint32_t> g_SfxPlayLastPan{0};         // float 位模式
std::atomic<std::uint32_t> g_SfxPlayLastFailure{0};     // 1/2/3/4，0 = 没失败过
}

namespace isaac::runtime {
namespace {

using LuaRuntime::kMusicMetatable;
using LuaRuntime::MusicGetCurrentMusicIdThunk;
using LuaRuntime::MusicPauseThunk;
using LuaRuntime::MusicPlayThunk;
using LuaRuntime::MusicResumeThunk;
using LuaRuntime::MusicUpdateVolumeThunk;
using LuaRuntime::ResolveMusicGetCurrentMusicId;
using LuaRuntime::ResolveMusicPause;
using LuaRuntime::ResolveMusicPlay;
using LuaRuntime::ResolveMusicResume;
using LuaRuntime::ResolveMusicUpdateVolume;
using LuaRuntime::ResolveSoundEffectsForCall;  // 批次 185：`SFXManager:IsPlaying` 的接收者解析
using LuaRuntime::ResolveSoundEffectsPlayForCall;  // 批次 408：`SFXManager:Play` 的接收者解析

int MusicGetCurrentMusicId(lua_State* state);
int MusicPause(lua_State* state);
int MusicResume(lua_State* state);
int MusicUpdateVolume(lua_State* state);
int MusicPlay(lua_State* state);

constexpr LuaHandlerBinding kMusicHandlers[] = {
    {0x06010001, &MusicGetCurrentMusicId},
    {0x06010002, &MusicPause},
    {0x06010003, &MusicResume},
    // 批次 137（2026-09-26）：`MusicManager:UpdateVolume()` —— The Specialist for Good Items
    // 的"捡到四级物品放歌"要用它（把音乐音量重新同步到选项菜单的设置）。底座
    // `Music::UpdateVolume()` @ `0x427908`（见 `runtime_constants.hpp` 的同名常量）。
    {0x06010006, &MusicUpdateVolume},
    // 批次 138（2026-09-26）：`MusicManager:Play(ID, Volume = 1)` —— 同一模组**放歌的主路径**
    // （`main.lua:483/489/494` 的 `MusicManager():Play(id, 1)`）。底座
    // `Music::Play(eMusic, float)` @ `0x427238`。
    {0x06010007, &MusicPlay},
};

constexpr char kMusicOwner[] = "MusicManager";

//: 引擎**函数地址**的可读判据（`EngineOffsetAddress<IsReadable>` 要的模板参数形态）。
//: 与 `game_api.cpp` / `sprite_api.cpp` / `remaining_api.cpp` 各自那一份**逐字同源** ——
//: 四族历史上各有一份拷贝、判决条件一条没改（只把实现收进 L1 的
//: `engine_memory::EngineMemoryReadable`）。批次 185 给 music 族补上这一份；
//: 本文件里它服务 `SFXManager:IsPlaying` 与 `SFXManager:Play` 两条（批次 408 起 Play 也要走守卫）。
bool IsEngineMemoryReadable(std::uintptr_t address, std::size_t length) noexcept {
    return isaac::runtime::engine_memory::EngineMemoryReadable(address, length);
}

// ---- `SFXManager()`（批次 045，为 GoodTrip 补）------------------------------------------
//
// PC 里 `SFXManager()` 是**全局函数**，返回引擎音效管理器单例；模组用
// `SFXManager():Play(SoundEffect, Volume, Pitch, Loop, Pan)` 放音（GoodTrip `scripts/trip.lua:8/74`）。
// 缺它时是 "attempt to call a nil value (global 'SFXManager')" ⇒ **模组整个加载失败**（真机实测）。
//
// **批次 045 只补了"对象与方法都在、调用不报错"**：当时引擎音效单例与 `Play` 的地址尚未取证 ⇒
// `Play` 曾是**明确的空实现**（不假装成功、也不报错），`IsPlaying` 恒 false；形状与 PC 一致。
// ★ 批次 185（2026-09-28）把 `IsPlaying` 补成真调引擎；**批次 408（2026-10-08）把 `Play` 也补上**
//   （引擎入口 `SoundEffects::Play` @ `0x4A2FD0`，取证见 `runtime_constants.hpp` 的批次 408 段）
//   —— 上面那句"`Play` 是空实现"到此为止已**过时**，留着是为了记住它曾经的样子。
// 音效与音乐同属"声音"⇒ 复用域 `0x06`、取域内空号 0x0004/0x0005（文件与 owner 的对应关系
// 由契约测试那张"文件 → 允许的 owner 集合"表登记）。
struct SfxManagerHandle {
    int reserved{0};
};

// ---- 批次 408：Play 探针的写入助手（无条件；见文件顶部那张表）----------------------------
//
// 浮点按位模式存（读数端按 `float` 解）；`loop` 存 0/1。三个助手都只在 `SfxManagerPlay` 里调。
std::uint32_t FloatBits(float value) noexcept {
    return std::bit_cast<std::uint32_t>(value);
}
void RecordSfxPlayArguments(std::int32_t id, float volume, std::int32_t frameDelay,
                            std::uint32_t loop, float pitch, float pan) noexcept {
    g_SfxPlayCalls.fetch_add(1, std::memory_order_relaxed);
    g_SfxPlayLastId.store(static_cast<std::uint32_t>(id), std::memory_order_relaxed);
    g_SfxPlayLastVolume.store(FloatBits(volume), std::memory_order_relaxed);
    g_SfxPlayLastFrameDelay.store(static_cast<std::uint32_t>(frameDelay),
                                  std::memory_order_relaxed);
    g_SfxPlayLastLoop.store(loop, std::memory_order_relaxed);
    g_SfxPlayLastPitch.store(FloatBits(pitch), std::memory_order_relaxed);
    g_SfxPlayLastPan.store(FloatBits(pan), std::memory_order_relaxed);
}
void RecordSfxPlayDelivered() noexcept {
    g_SfxPlayDelivered.fetch_add(1, std::memory_order_relaxed);
}
void RecordSfxPlayFailure(std::uint32_t code) noexcept {
    g_SfxPlayLastFailure.store(code, std::memory_order_relaxed);
}

// `SFXManager:Play(SoundEffect ID, float Volume, int FrameDelay, boolean Loop, float Pitch, float Pan)`
// —— **批次 408（2026-10-08）从"空实现"改成真调引擎**（引擎入口 `SoundEffects::Play` @ `0x4A2FD0`；
// 三条独立证据 + 16 字节指纹见 `runtime_constants.hpp` 的批次 408 段；PC 契约
// `tools/pc_contract_docs/SFXManager.md:53`）。
//
// ★ 参数形状（**完整照 PC 契约，不自己发明**）：`ID, Volume=1, FrameDelay=2, Loop=false, Pitch=1, Pan=0`。
//   校验口径**沿用批次 045 的现状、一个字不加严**：只钉"第 2 个参数是整数"，不钉范围、不钉个数
//   （比 PC 严害过我们很多次）。第 3~7 个参数缺省时补 PC 的缺省值，给了就用给的 ——
//   `lua_isnumber` / `lua_toboolean` 都**不会抛错**（不是数字/布尔就落到缺省，与 PC 的容忍一致）。
//   ⚠️ 契约里 `FrameDelay` 是 **`int`（缺省 `2`）**，不是浮点、不是 `0`；引擎符号
//      `…Efibff` 也把它标成 `i`（见常量注释）。
//
// ★ 参数**按 ABI 顺序**递：`x0 = 音效子对象`、`w1 = ID`、`s0 = Volume`、`w2 = FrameDelay`、
//   `w3 = Loop`、`s1 = Pitch`、`s2 = Pan`（`AsFunction` 的**带签名**函数指针在编译期完成编组，
//   所以这里直接按 `(void*, int32, float, int32, int, float, float)` 调）。
//   `Loop` 形参写成 `int`（递 0/1）：设备侧 `bool` 与 `int` 都落在同一个 `w3`，宿主夹具也按 `int` 接。
//
// ★ 三道守卫（**调用之前**，与同文件 `SfxManagerIsPlaying` 逐条同形）：
//   ① `EngineOffsetAddress<IsEngineMemoryReadable>(kSoundEffectsPlayOffset)` —— 模块基址 + 偏移 + 可读；
//   ② `ResolveSoundEffectsPlayForCall` 内部的"当前回调的 Manager → `Manager + 0x364A8` 音效子对象"；
//   ③ 同一个函数里的 16 字节入口指纹。
//   任一不过 ⇒ **什么都不做、返回 0**（PC 的返回类型就是 `void`；报错会把整条模组回调摘掉，
//   比"这次没响"严重得多）。**不假装成功**：只有真的把调用递进引擎才 `RecordSfxPlayDelivered()`。
int SfxManagerPlay(lua_State* state) {
    if (lua_gettop(state) < 2 || !isaac::runtime::IsIntegerArgument(state, 2)) {
        return luaL_error(state, "SFXManager:Play accepts a sound effect id");
    }
    const auto soundEffect = static_cast<std::int32_t>(lua_tointegerx(state, 2, nullptr));
    const float volume =
        lua_isnumber(state, 3) != 0 ? static_cast<float>(lua_tonumber(state, 3)) : 1.0f;
    const auto frameDelay = static_cast<std::int32_t>(
        lua_isnumber(state, 4) != 0 ? lua_tointeger(state, 4) : 2);
    const std::uint32_t loop = lua_toboolean(state, 5) != 0 ? 1u : 0u;
    const float pitch =
        lua_isnumber(state, 6) != 0 ? static_cast<float>(lua_tonumber(state, 6)) : 1.0f;
    const float pan =
        lua_isnumber(state, 7) != 0 ? static_cast<float>(lua_tonumber(state, 7)) : 0.0f;
    RecordSfxPlayArguments(soundEffect, volume, frameDelay, loop, pitch, pan);
    const std::uintptr_t method =
        isaac::runtime::EngineOffsetAddress<IsEngineMemoryReadable>(kSoundEffectsPlayOffset);
    std::uintptr_t soundEffects = 0;
    std::uint32_t failureCode = 0;
    if (method != 0 && ResolveSoundEffectsPlayForCall(method, &soundEffects, &failureCode)) {
        using PlayFn = void (*)(void*, std::int32_t, float, std::int32_t, int, float, float);
        engine_call::AsFunction<PlayFn>(method)(engine_memory::AsObject(soundEffects), soundEffect,
                                                volume, frameDelay, static_cast<int>(loop), pitch,
                                                pan);
        RecordSfxPlayDelivered();
    } else {
        // `method == 0` ⇒ 守卫①就没过（模块基址没发布 / 偏移不可读）⇒ 记 3（"方法地址缺失"）。
        RecordSfxPlayFailure(method == 0 ? 3u : failureCode);
    }
    return 0;
}

// `SFXManager:IsPlaying(SoundEffect ID)` —— 批次 185（2026-09-28）从"**恒 false**"改成**真调引擎**。
//
// PC 契约 `tools/pc_contract_docs/SFXManager.md:48`：「boolean IsPlaying ( SoundEffect ID )」。
//
// ★ 接收者**不在 Lua 栈上**：PC 里 `SFXManager()` 是个**全局函数**、返回引擎的音效单例，
//   而我们这个 handle 是**空结构** ⇒ 接收者只能从"当前回调的 Manager"解析
//   （`Manager + kManagerSoundEffectsOffset`，偏移的反汇编取证见 `runtime_constants.hpp`）。
//   这与 `MusicManager:` 一族同形 ⇒ 复用同一套两跳取 Manager 的 `ResolveSoundEffectsForCall`。
//   ★ 这也是它**不能**走"数据行"（`engine_method_api.hpp` 那张 16 字节表）的原因：
//     数据行的接收者只能来自 `FieldReceipt` —— 也就是**从 Lua 栈上那个 self 句柄**解出来的。
//
// ★ 三道守卫都在调用**之前**：`EngineOffsetAddress` 管"模块基址 + 偏移 + 该地址可读"，
//   `ResolveSoundEffectsForCall` 内部的 `ValidateMusicMethod` 管"入口 16 字节指纹"。
//   三道任一不过就**什么都不做**（压 false）—— 偏移写错会调到别的函数上去改引擎状态，
//   **没有**"反正调一下试试"这种选项。
//
// ★ 失败与"引擎说没在播"在 Lua 侧**分不开**（都只能压 `false`）：PC 的返回类型就是 boolean，
//   压 nil 会让模组 `if x then` 判错、甚至把整条回调摘掉。**不报错**也是同族口径
//   （拿不到实例时按 PC 的返回类型降级）。要区分就去看 `ResolveSoundEffectsForCall`
//   记下的失败码（1 = 不在托管回调里 / 2 = Manager 或子对象读不到 / 3 = 方法地址缺失 /
//    4 = 入口指纹不符）。
int SfxManagerIsPlaying(lua_State* state) {
    if (lua_gettop(state) != 2 || !isaac::runtime::IsIntegerArgument(state, 2)) {
        return luaL_error(state, "SFXManager:IsPlaying accepts a sound effect id");
    }
    const auto soundEffect = static_cast<std::int32_t>(lua_tointegerx(state, 2, nullptr));
    bool playing = false;
    const std::uintptr_t method =
        isaac::runtime::EngineOffsetAddress<IsEngineMemoryReadable>(kSoundEffectsIsPlayingOffset);
    std::uintptr_t soundEffects = 0;
    if (method != 0 && ResolveSoundEffectsForCall(method, &soundEffects)) {
        using IsPlayingFn = bool (*)(const void*, std::int32_t);
        playing = engine_call::AsFunction<IsPlayingFn>(method)(
            engine_memory::AsObject(soundEffects), soundEffect);
    }
    lua_pushboolean(state, playing ? 1 : 0);
    return 1;
}


// 2026-10-09：七个方法调用同名原生成员；缺入口不返回伪造成功/音量。
void RequireSfxReceiver(lua_State* state, std::uintptr_t method, const u8* expected,
                         std::size_t size, std::uintptr_t* receiver) {
    luaL_checkudata(state, 1, "IsaacRuntime.SFXManager");
    if (!LuaRuntime::ResolveSoundEffectsMethodForCall(method, expected, size, receiver)) {
        luaL_error(state, "SFXManager native method is unavailable");
    }
}

int SfxManagerAdjustPitch(lua_State* state) {
    if (lua_gettop(state) != 3) return luaL_error(state, "SFXManager:AdjustPitch expects 2 argument(s)");
    const auto id = static_cast<std::int32_t>(luaL_checkinteger(state, 2));
    const auto value = static_cast<float>(luaL_checknumber(state, 3));
    std::uintptr_t receiver = 0;
    const std::uintptr_t method = isaac::runtime::EngineOffsetAddress<IsEngineMemoryReadable>(kSoundEffectsAdjustPitchOffset);
    RequireSfxReceiver(state, method,
        kSoundEffectsAdjustPitchExpectedBytes.data(), kSoundEffectsAdjustPitchExpectedBytes.size(), &receiver);
    using SfxAdjustPitchFn = void (*)(void*, std::int32_t, float);
    engine_call::AsFunction<SfxAdjustPitchFn>(method)(engine_memory::AsObject(receiver), id, value);
    return 0;
}

int SfxManagerAdjustVolume(lua_State* state) {
    if (lua_gettop(state) != 3) return luaL_error(state, "SFXManager:AdjustVolume expects 2 argument(s)");
    const auto id = static_cast<std::int32_t>(luaL_checkinteger(state, 2));
    const auto value = static_cast<float>(luaL_checknumber(state, 3));
    std::uintptr_t receiver = 0;
    const std::uintptr_t method = isaac::runtime::EngineOffsetAddress<IsEngineMemoryReadable>(kSoundEffectsAdjustVolumeOffset);
    RequireSfxReceiver(state, method,
        kSoundEffectsAdjustVolumeExpectedBytes.data(), kSoundEffectsAdjustVolumeExpectedBytes.size(), &receiver);
    using SfxAdjustVolumeFn = void (*)(void*, std::int32_t, float);
    engine_call::AsFunction<SfxAdjustVolumeFn>(method)(engine_memory::AsObject(receiver), id, value);
    return 0;
}

int SfxManagerGetAmbientSoundVolume(lua_State* state) {
    if (lua_gettop(state) != 2) return luaL_error(state, "SFXManager:GetAmbientSoundVolume expects 1 argument(s)");
    const auto id = static_cast<std::int32_t>(luaL_checkinteger(state, 2));
    std::uintptr_t receiver = 0;
    const std::uintptr_t method = isaac::runtime::EngineOffsetAddress<IsEngineMemoryReadable>(kSoundEffectsGetAmbientSoundVolumeOffset);
    RequireSfxReceiver(state, method,
        kSoundEffectsGetAmbientSoundVolumeExpectedBytes.data(), kSoundEffectsGetAmbientSoundVolumeExpectedBytes.size(), &receiver);
    using SfxGetAmbientSoundVolumeFn = float (*)(void*, std::int32_t);
    lua_pushnumber(state, engine_call::AsFunction<SfxGetAmbientSoundVolumeFn>(method)(engine_memory::AsObject(receiver), id));
    return 1;
}

int SfxManagerPreload(lua_State* state) {
    if (lua_gettop(state) != 2) return luaL_error(state, "SFXManager:Preload expects 1 argument(s)");
    const auto id = static_cast<std::int32_t>(luaL_checkinteger(state, 2));
    std::uintptr_t receiver = 0;
    const std::uintptr_t method = isaac::runtime::EngineOffsetAddress<IsEngineMemoryReadable>(kSoundEffectsPreloadOffset);
    RequireSfxReceiver(state, method,
        kSoundEffectsPreloadExpectedBytes.data(), kSoundEffectsPreloadExpectedBytes.size(), &receiver);
    using SfxPreloadFn = void (*)(void*, std::int32_t);
    engine_call::AsFunction<SfxPreloadFn>(method)(engine_memory::AsObject(receiver), id);
    return 0;
}

int SfxManagerSetAmbientSound(lua_State* state) {
    if (lua_gettop(state) != 4) return luaL_error(state, "SFXManager:SetAmbientSound expects 3 argument(s)");
    const auto id = static_cast<std::int32_t>(luaL_checkinteger(state, 2));
    const auto value = static_cast<float>(luaL_checknumber(state, 3));
    const auto pitch = static_cast<float>(luaL_checknumber(state, 4));
    std::uintptr_t receiver = 0;
    const std::uintptr_t method = isaac::runtime::EngineOffsetAddress<IsEngineMemoryReadable>(kSoundEffectsSetAmbientSoundOffset);
    RequireSfxReceiver(state, method,
        kSoundEffectsSetAmbientSoundExpectedBytes.data(), kSoundEffectsSetAmbientSoundExpectedBytes.size(), &receiver);
    using SfxSetAmbientSoundFn = void (*)(void*, std::int32_t, float, float);
    engine_call::AsFunction<SfxSetAmbientSoundFn>(method)(engine_memory::AsObject(receiver), id, value, pitch);
    return 0;
}

int SfxManagerStop(lua_State* state) {
    if (lua_gettop(state) != 2) return luaL_error(state, "SFXManager:Stop expects 1 argument(s)");
    const auto id = static_cast<std::int32_t>(luaL_checkinteger(state, 2));
    std::uintptr_t receiver = 0;
    const std::uintptr_t method = isaac::runtime::EngineOffsetAddress<IsEngineMemoryReadable>(kSoundEffectsStopOffset);
    RequireSfxReceiver(state, method,
        kSoundEffectsStopExpectedBytes.data(), kSoundEffectsStopExpectedBytes.size(), &receiver);
    using SfxStopFn = void (*)(void*, std::int32_t);
    engine_call::AsFunction<SfxStopFn>(method)(engine_memory::AsObject(receiver), id);
    return 0;
}

int SfxManagerStopLoopingSounds(lua_State* state) {
    if (lua_gettop(state) != 1) return luaL_error(state, "SFXManager:StopLoopingSounds expects 0 argument(s)");
    std::uintptr_t receiver = 0;
    const std::uintptr_t method = isaac::runtime::EngineOffsetAddress<IsEngineMemoryReadable>(kSoundEffectsStopLoopingSoundsOffset);
    RequireSfxReceiver(state, method,
        kSoundEffectsStopLoopingSoundsExpectedBytes.data(), kSoundEffectsStopLoopingSoundsExpectedBytes.size(), &receiver);
    using SfxStopLoopingSoundsFn = void (*)(void*);
    engine_call::AsFunction<SfxStopLoopingSoundsFn>(method)(engine_memory::AsObject(receiver));
    return 0;
}

constexpr LuaHandlerBinding kSfxManagerHandlers[] = {
    {0x06010004, &SfxManagerPlay},
    {0x06010005, &SfxManagerIsPlaying},
    {0x06010020, &SfxManagerAdjustPitch},
    {0x06010021, &SfxManagerAdjustVolume},
    {0x06010022, &SfxManagerGetAmbientSoundVolume},
    {0x06010023, &SfxManagerPreload},
    {0x06010024, &SfxManagerSetAmbientSound},
    {0x06010025, &SfxManagerStop},
    {0x06010026, &SfxManagerStopLoopingSounds},
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
        return luaL_error(state, "Music:GetCurrentMusicID native bindings are unavailable (%s)",
                          LuaRuntime::MusicResolveFailureReason());
    }
    using GetCurrentMusicIdFn = int (*)(const void*);
    lua_pushinteger(state,
                    engine_call::AsFunction<GetCurrentMusicIdFn>(method)(
                        engine_memory::AsObject(music)));
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
        return luaL_error(state, "Music:Pause native bindings are unavailable (%s)",
                          LuaRuntime::MusicResolveFailureReason());
    }
#if defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 48
    Stage48ArmMusicReplayProbe();
#endif
    using PauseFn = void (*)(void*);
    engine_call::AsFunction<PauseFn>(method)(engine_memory::AsObject(music));
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
        return luaL_error(state, "Music:Resume native bindings are unavailable (%s)",
                          LuaRuntime::MusicResolveFailureReason());
    }
    using ResumeFn = void (*)(void*);
    engine_call::AsFunction<ResumeFn>(method)(engine_memory::AsObject(music));
    return 0;
}

// 批次 137：`MusicManager:UpdateVolume()`（无参、void）。形状与 `Pause`/`Resume` 逐字相同 ——
// 接收者仍是由回调的 Manager 派生的 Music 对象（`ResolveMusicUpdateVolume` 内两跳：先判
// "在托管回调里"，再按 `manager + kManagerMusicOffset` 解析 + 16 字节入口守卫），
// 所以"不在回调里 / 绑定不可用"时报错而不是静默假装成功。
int MusicUpdateVolume(lua_State* state) {
    luaL_checkudata(state, 1, kMusicMetatable);
    if (lua_gettop(state) != 1) {
        return luaL_error(state, "Music:UpdateVolume accepts no arguments");
    }
    const std::uintptr_t method = MusicUpdateVolumeThunk();
    std::uintptr_t music = 0;
    if (!ResolveMusicUpdateVolume(method, &music)) {
        return luaL_error(state, "Music:UpdateVolume native bindings are unavailable (%s)",
                          LuaRuntime::MusicResolveFailureReason());
    }
    using UpdateVolumeFn = void (*)(void*);
    engine_call::AsFunction<UpdateVolumeFn>(method)(engine_memory::AsObject(music));
    return 0;
}

// 批次 138：`MusicManager:Play(eMusic ID, float Volume = 1)` —— The Specialist for Good Items
// "放歌"的**主路径**。PC 契约 `tools/pc_contract_docs/MusicManager.md:102` 逐字：
//   `#### void Play ( [Music](enums/Music.md) ID, float Volume = 1 ) {: .copyable aria-label='Functions' }`
// **同一个契约页第 103~104 行**还明写"ID 为负或超出范围时 PC 会**崩游戏**"（`???+ bug "Bug"`）——
// 我们**不**替模组挡这个：与 PC 一致（挡了就是"我们比 PC 严"，会把本该发生的调用变成 Lua 报错，
// 反而摘掉整条回调）。
// 形状口径：冒号调用时栈上 = [self, ID] 或 [self, ID, Volume]；第 2 个参数省缺时按 PC 默认值
// 传 `1.0f`（引擎侧就是同一个重载 `Music::Play(eMusic, float)`，见 `runtime_constants.hpp` 的
// `kMusicPlayOffset` 注释）。参数**类型**错（ID 不是整数 / Volume 不是数字）才报错。
int MusicPlay(lua_State* state) {
    luaL_checkudata(state, 1, kMusicMetatable);
    const int argumentCount = lua_gettop(state);
    const bool volumeGiven = argumentCount == 3;
    if (argumentCount < 2 || argumentCount > 3 || !isaac::runtime::IsIntegerArgument(state, 2) ||
        (volumeGiven && lua_isnumber(state, 3) == 0)) {
        return luaL_error(state, "Music:Play accepts (music[, volume])");
    }
    const lua_Number volume = volumeGiven ? lua_tonumber(state, 3) : 1.0;
    // ★★ 批次 154（2026-09-27）：**编号保险**（见 `engine_method_api.hpp` 的 `CheckMusicId`）。
    //
    // 与下面那段"照 PC 语义不挡"的说明**不矛盾**，是对它的收窄：PC 上模组拿到的编号不会是 `-1`，
    // 因为 PC 在模组脚本看到它之前就把模组的 `content/music.xml` 加载好了；我们这边会因为
    // **自己的加载时机**而出现那个窗口 ⇒ 真机就崩在 `Music::Play + 0x68`（`Data Abort`，
    // `dist/crash-153-20260927-1121.log`）。**那是我们的缺口，不该让玩家承担一次崩溃。**
    //
    // 挡法是**静默跳过**（**不报 Lua 错** —— 报错会把整条模组回调摘掉，比"这次没放歌"严重得多），
    // 与 `AddNullCostume` 的保险同一套形状；挡下就记 `g_MusicPlayGuardBlocked`，
    // 读数里"这次没放歌"与"我们挡了"因此分得开。
    // 判定不了（曲目表那条链当时读不到）时**照原样放进去**：宁可放行，也不吞掉合法调用；
    // 那种情况不另开计数格 —— 它会同时反映在 `g_IsaacMusicIdTableCount = 0xFFFFFFFF` 上。
    const auto musicIdVerdict =
        isaac::runtime::CheckMusicId(static_cast<std::int64_t>(lua_tointeger(state, 2)));
    if (musicIdVerdict == isaac::runtime::MusicIdVerdict::Invalid) {
        isaac::runtime::RecordMusicPlayGuardBlocked();
        return 0;
    }
    const std::uintptr_t method = MusicPlayThunk();
    std::uintptr_t music = 0;
    if (!ResolveMusicPlay(method, &music)) {
        return luaL_error(state, "Music:Play native bindings are unavailable (%s)",
                          LuaRuntime::MusicResolveFailureReason());
    }
    using PlayFn = void (*)(void*, std::int32_t, float);
    engine_call::AsFunction<PlayFn>(method)(
        engine_memory::AsObject(music), static_cast<std::int32_t>(lua_tointeger(state, 2)),
        static_cast<float>(volume));
    return 0;
}

} // namespace

//: 批次 239（2026-09-30）：`MusicManager` 的**引擎方法数据行**（机制见 `engine_method_api.hpp`）。
//:
//: ★ 为什么这 7 条走数据行、而上面的 `Pause`/`Resume`/`Play`/`UpdateVolume` 是手写处理器：
//: 那 4 条写在数据行机制（批次 051）之前，而且各自带一份"入口 16 字节指纹"的手写核对。
//: 数据行机制把"接收者解析 + 入口 4 字节核对 + 参数编组"收成了一份共享实现，
//: 所以从批次 239 起，`MusicManager` 的新 API 一律走数据行（**16 字节只读、0 字节代码**）。
//:
//: 接收者 = `FieldReceipt::Music`（**不从 Lua 栈上取**，见 `field_api.hpp` 那条的注释）：
//: `MusicManager()` 在 Lua 里是占位句柄，引擎的 `Music` 在 `Manager + kManagerMusicOffset`。
constexpr EngineMethodRow kMusicEngineRows[] = {
    // ---- 批次 239：`MusicManager:DisableLayer`（void DisableLayer ( int LayerId = 0 )）
    // PC 契约 `tools/pc_contract_docs/MusicManager.md:47`。语料**一个参数都不传**
    // （`BOIStageAPI15/.../callbacks.lua` 的 `shared.Music:DisableLayer()`）⇒ 形状 `VoidIntOpt1`
    // 声明尾部 1 个可省（复用 `Void1` 会因为"参数个数严格相等"直接报错、摘掉整条回调）。
    {0x06010008, kMusicDisableLayerOffset, kMusicDisableLayerEntryWord, FieldReceipt::Music,
     EngineCallShape::VoidIntOpt1, 1, 0xFF},
    // ---- 批次 239：`MusicManager:IsLayerEnabled`（boolean IsLayerEnabled ( int LayerId = 0 )）
    // PC 契约 `MusicManager.md:87`。语料同样不传参数 ⇒ `BoolIntOpt1`（尾部 1 个可省）。
    {0x06010009, kMusicIsLayerEnabledOffset, kMusicIsLayerEnabledEntryWord, FieldReceipt::Music,
     EngineCallShape::BoolIntOpt1, 1, 0xFF},
    // ---- 批次 239：`MusicManager:EnableLayer`（void EnableLayer ( int LayerId = 0, boolean Instant = false )）
    // PC 契约 `MusicManager.md:57`。语料不传参数（`shared.Music:EnableLayer()`）⇒ `VoidIntBoolOpt2`
    // 声明尾部 2 个可省（两个缺省值都是 0 ⇒ 省略时寄存器保持 0 恰好就是 PC 缺省）。
    {0x0601000A, kMusicEnableLayerOffset, kMusicEnableLayerEntryWord, FieldReceipt::Music,
     EngineCallShape::VoidIntBoolOpt2, 2, 0xFF},
    // ---- 批次 239：`MusicManager:VolumeSlide`（void VolumeSlide ( float TargetVolume, float FadeRate = 0.08 )）
    // PC 契约 `MusicManager.md:130`。语料传 2 个（`musicmgr:VolumeSlide(0.1, 0.05)`）⇒
    // `VoidFloatFloatOpt1`（尾部 1 个可省，省略时 `d1` 保持 0）。
    {0x0601000B, kMusicVolumeSlideOffset, kMusicVolumeSlideEntryWord, FieldReceipt::Music,
     EngineCallShape::VoidFloatFloatOpt1, 2, 0xFF},
    // ---- 批次 239：`MusicManager:GetQueuedMusicID`（Music GetQueuedMusicID ( )）
    // PC 契约 `MusicManager.md:77`。无参、返回 eMusic（枚举 ⇒ 整数）⇒ `Int0`。
    {0x0601000C, kMusicGetQueuedMusicIdOffset, kMusicGetQueuedMusicIdEntryWord,
     FieldReceipt::Music, EngineCallShape::Int0, 0, 0xFF},
    // ---- 批次 239：`MusicManager:PitchSlide`（void PitchSlide ( float TargetPitch )）
    // PC 契约 `MusicManager.md:97` —— **无缺省值** ⇒ 直接复用既有的 `VoidFloat1`。
    {0x0601000D, kMusicPitchSlideOffset, kMusicPitchSlideEntryWord, FieldReceipt::Music,
     EngineCallShape::VoidFloat1, 1, 0xFF},
    // ---- 批次 239：`MusicManager:ResetPitch`（void ResetPitch ( )）
    // PC 契约 `MusicManager.md:114`。无参、返回 void ⇒ `Void0`。
    {0x0601000E, kMusicResetPitchOffset, kMusicResetPitchEntryWord, FieldReceipt::Music,
     EngineCallShape::Void0, 0, 0xFF},
    // ---- 批次 252（2026-10-01）：`MusicManager:Queue`（void Queue ( Music ID )）
    // PC 契约 `MusicManager.md:109`，**无缺省值**；语料传 1 个
    // （`BOIStageAPI15/.../callbacks.lua:545` 的 `shared.Music:Queue(shouldQueue)`）
    // ⇒ 形状 `Void1`、`argumentCount` = 1。
    {0x0601000F, kMusicQueueOffset, kMusicQueueEntryWord, FieldReceipt::Music,
     EngineCallShape::Void1, 1, 0xFF},
    // ---- 批次 252：`MusicManager:Crossfade`（void Crossfade ( Music ID, float FadeRate = 0.08 )）
    // PC 契约 `MusicManager.md:35`；语料传 2 个（`MusicModCallback/.../repentance.lua:771`）
    // ⇒ `VoidIntFloatOpt1`（本批新增的形状；尾部 1 个可省，省略时 `d1` 保持 0）。
    {0x06010010, kMusicCrossfadeOffset, kMusicCrossfadeEntryWord, FieldReceipt::Music,
     EngineCallShape::VoidIntFloatOpt1, 2, 0xFF},
};

//: 批次 305（2026-10-03）：`MusicManager` 的**字段数据行**（第 3 条数据行表形态）。
//:
//: `Disable()` / `Enable()` / `IsEnabled()` 三条在 PC 上都是 `Music` 上的**一个字节**
//: （`+0x328`）：`Disable` = 写 0、`Enable` = 写 1、`IsEnabled` = 读它（三条绑定各一条指令，
//: `tools/pc_exe_binding.py` 给的是 `0x7FAC30` / `0x7AC20` / `0x7FAC40`）。
//: Switch 侧那一格是 `Music + 0x3F0`：构造函数用 `mov w8,#1` + `strb w8,[x19,#0x3f0]` 初始化
//: （默认**启用**，与 PC 一致），`Music::Update` 读它当闸（`ldrb w8,[x0,#0x3f0]` + `cbnz → 更新音乐`）
//: ⇒ 取证与"为什么不许平移 PC 的 `0x328`"见 `runtime_constants.hpp` 的批次 305 段。
//:
//: ★ 前两条走**新种类 `FieldKind::BoolWriteConst`**（往 1 字节字段写**常量**、**不收实参**、
//:   返回 0 个值）；第三条是既有的 `FieldKind::Bool`（读 1 字节压布尔）。
//: ★ 接收者是既有的 `FieldReceipt::Music`（批次 239 立的：`Music` 是 `Manager` 的内嵌子对象，
//:   接收者**算出来**而不是从栈上取）。
constexpr FieldApiRow kMusicFieldApis[] = {
    {0x06010011, kMusicEnabledOffset, 0, FieldKind::BoolWriteConst, FieldMissing::False,
     FieldReceipt::Music, 0xFF},
    {0x06010012, kMusicEnabledOffset, 1, FieldKind::BoolWriteConst, FieldMissing::False,
     FieldReceipt::Music, 0xFF},
    {0x06010013, kMusicEnabledOffset, 0, FieldKind::Bool, FieldMissing::False,
     FieldReceipt::Music, 0xFF},
};
static_assert(sizeof(kMusicFieldApis) / sizeof(kMusicFieldApis[0]) == 3,
              "行数与 id 段（0x0011 / 0x0012 / 0x0013）要一起改");

std::size_t AttachMusicMethods(lua_State* state) noexcept {
    // 批次 239：手写处理器表与引擎方法数据行表一起挂 —— 绑定循环按 id 匹配，不会串族。
    // 批次 305：再加上字段数据行表（`Disable`/`Enable`/`IsEnabled`）。
    return AttachApi100Methods(state,"MusicManager") + AttachOwnerMethods(state, kMusicOwner, kMusicHandlers,
                              sizeof(kMusicHandlers) / sizeof(kMusicHandlers[0]),
                              kMusicFieldApis,
                              sizeof(kMusicFieldApis) / sizeof(kMusicFieldApis[0]),
                              kMusicEngineRows, sizeof(kMusicEngineRows) / sizeof(kMusicEngineRows[0]));
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
