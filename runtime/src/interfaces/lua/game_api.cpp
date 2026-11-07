#include "domain/console/console_panel_state.hpp"
#include "interfaces/lua/api700_bindings.hpp"
#include "interfaces/lua/api600_bindings.hpp"
#include "interfaces/lua/api600_world.hpp"
#include "interfaces/lua/api300_bindings.hpp"
#include "interfaces/lua/api200_bindings.hpp"
#include "interfaces/lua/rplus_method_bindings.hpp"
#include "interfaces/lua/game_api.hpp"
#include "interfaces/lua/seed_effects_api.hpp"

#include "interfaces/lua/lua_integer_argument.hpp"
#include "interfaces/lua/field_api.hpp"   // `kGameFieldApis`（字段读取型数据行）
#include "interfaces/lua/engine_method_lookup.hpp"

#include "interfaces/lua/api_sequence_probe.hpp"
#include "interfaces/lua/native_state_fallback.hpp"
#include "infrastructure/call/engine_call_access.hpp"
#include "infrastructure/memory/engine_field_access.hpp"
#include "infrastructure/memory/engine_memory_guard.hpp"
#include "interfaces/lua/isaac_api.hpp"
#include "interfaces/lua/owner_binding.hpp"
#include "interfaces/lua/vector_api.hpp"

#include "application/callback/callback_dispatcher.hpp"
#include "game_observer.hpp"
#include "engine_color_mod.hpp"
#include "lua_object_handles.hpp"
#include "lua_runtime_state.hpp"
#include "runtime_constants.hpp"
// `kGameFieldApis` 里 `Game:Darken` 那两格要做编译期对账
// （`runtime_constants.hpp` 的常量 vs 布局表生成物），所以这个 TU 要拿到生成的布局头。
#include "game_layout.hpp"

#include <cstddef>
#include <cstdint>
#include <atomic>
#include <cstring>

#if defined(__SWITCH__)
#include "lib/nx/nx.h"
#endif

extern "C" {
#include <lauxlib.h>
}

namespace isaac::runtime {
#if !defined(__SWITCH__)
static HudNativeTestBindings g_HudNativeTest{};
void SetHudNativeTestBindings(HudNativeTestBindings bindings) noexcept {g_HudNativeTest=bindings;}
#endif


// 探针：`Game:IsPaused()` 最后一次返回 true。EID 的 `OnRender` 用它配合 `HideInBattle`
// 决定是否隐藏描述，所以"描述没画"必须能看出这个读数。放在匿名命名空间之外，探针出口要用。
std::atomic<std::uint32_t> g_LastIsPaused{0};

// 探针：`Game:GetNumPlayers()` 最后一次返回值（EID 的 `EID.player` 依赖它）。
std::atomic<std::uint32_t> g_LastNumPlayers{0};

// 探针：`Seeds:AddSeedEffect` / `RemoveSeedEffect` 被调用了几次（两条共用一个计数）。
// 为什么要它：这两条按设计**不生效**（引擎唯一入口吃"名字字符串"，我们拿不到"枚举 → 名字"这条路，
// 取证见 `SeedsAddSeedEffect` 上面那段）⇒ 真机上唯一能证明"模组真的调了、我们真的接住了"的就是这个数。
// 必须放在匿名命名空间之外：放进去就变成内部链接、ELF 符号表里查不到，
//    读数工具（`tools/read_device_state_via_gdb.py` 的 `SYMS`）就永远读不到它。
//    本批第一版正是放在里面 —— `runtime/tests/test_entity_field_write_probe.py` 的
//    "探针必须可读" 那组断言把它抓了出来。
std::atomic<std::uint32_t> g_SeedsEffectWriteAttempts{0};

namespace {

using LuaRuntime::EngineModuleBase;
using LuaRuntime::GameHandle;
using LuaRuntime::GameIsGreedModeThunk;
using LuaRuntime::GameIsPausedThunk;
using LuaRuntime::GameOwnerSlot;
using LuaRuntime::InManagedCallbackScope;
using LuaRuntime::ItemPoolHandle;
using LuaRuntime::kGameMetatable;
using LuaRuntime::kItemPoolMetatable;
using LuaRuntime::kLevelMetatable;
using LuaRuntime::kRoomMetatable;
using LuaRuntime::LevelHandle;
using LuaRuntime::RoomHandle;
using LuaRuntime::SeedHandle;
using LuaRuntime::kSeedsMetatable;
// `Seeds:GetNextSeed()` 就是"对 `Seeds + 0x8` 那个内嵌 RNG 调 `RNG::Next()`"
// ⇒ **复用** `RNG:Next` 那一条已经立好的发布点与 16 字节入口指纹（`RngNextThunk` / `ValidateRngNextBinding`）。
// 不自己抄一份 xorshift：PC 是把 `RNG::Next` 内联进绑定本体的（指令级对照写在
//   `runtime_constants.hpp` 的 `kSeedsRngOffset` 段），Switch 侧它是**独立函数** ⇒ 调它才是同一条语义。
using LuaRuntime::RngNextThunk;
using LuaRuntime::ValidateRngNextBinding;
// `Game:GetHUD()` 的返回值与它的两个方法。
using LuaRuntime::HudHandle;
using LuaRuntime::kHudMetatable;
// 玩家数量的**唯一**来源：与 `Isaac.GetPlayer` 共用同一次判定（真机 `01789207110` 的根因）。
using isaac::runtime::EnginePlayerArray;
using isaac::runtime::ResolveEnginePlayerArray;
// `Game:GetPlayer(index)` 用的是"取第 index 个玩家"那一条链（与 `Isaac.GetPlayer` 同源）。
using isaac::runtime::PushEntityCallbackArgument;
using isaac::runtime::ResolveEnginePlayerAt;

int GameIsPaused(lua_State* state);
int GameIsGreedMode(lua_State* state);
int GameGetLevel(lua_State* state);
int GameGetItemPool(lua_State* state);
int GameGetRoom(lua_State* state);
int GameGetNumPlayers(lua_State* state);
int GameGetFrameCount(lua_State* state);
int GameGetSeeds(lua_State* state);
int SeedsIsCustomRun(lua_State* state);
int SeedsGetStartSeed(lua_State* state);
// 中文版 MCM（`!!Mod Config Menu Chinese`，工坊 2494192799）要这三条，
// 英文版（`!! Mod Config Menu Pure`）要其中 `Has`/`Add`/`Remove`；两者都缺、且都在**开菜单**那条路上。
// 语义与依据见实现处注释；`Add`/`Remove` 只有"不抛错的空实现"这一条路（证据见实现处）。
int SeedsHasSeedEffect(lua_State* state);
int SeedsAddSeedEffect(lua_State* state);
// `Seeds:ForgetStageSeed(LevelStage Stage)`（语料 1 处）。
// `this` 不是句柄存的地址，而是 `Game + kGameSeedsObjectOffset` 现算 —— 与 `Seeds:GetStartSeed()`
// 同一条思路（`Seeds` 是 `Game` 里**内嵌**的子对象）。
int SeedsForgetStageSeed(lua_State* state);
// `Seeds:GetStageSeed(LevelStage)` 与 `Seeds:GetNextSeed()`。
// 两条都是**手写**而不是数据行，理由有数可查（写在实现处）：`Seeds` 句柄**不持引擎指针**
// （接收者要 `Game + kGameSeedsObjectOffset` 现算 ⇒ 先要有 `FieldReceipt::Seeds` 这一档），
// 而 `GetNextSeed` 还要**调引擎的 `RNG::Next()`** ⇒ 数据行机制本来也表达不了。
// 这个家族里已有的 5 条（`IsCustomRun`/`GetStartSeed`/`Has|Add|RemoveSeedEffect`/`ForgetStageSeed`）
// 全是手写 —— 新开一档 receipt + 一个新 kind 只服务 3 个调用点，比写两条处理器更贵。
int SeedsGetStageSeed(lua_State* state);
int SeedsGetNextSeed(lua_State* state);
int SeedsRemoveSeedEffect(lua_State* state);
// `Game:GetHUD()` 与它的返回值 `HUD` 的两个方法。
// MCM 的 `RoomIsSafe()` 与 `OpenConfigMenu`/`CloseConfigMenu` 都要用（见 `api_catalog.cpp` 的条目注释）。
int GameGetHUD(lua_State* state);
int HudIsVisible(lua_State* state);
int HudSetVisible(lua_State* state);
int HudRender(lua_State* state);
int HudShowItemText(lua_State* state);
int HudShowFortuneText(lua_State* state);
int GameGetVictoryLap(lua_State* state);
// （2026-10-02，语料 API 恢复的 `needs_new_shape` 桶）：`Game:SpawnParticles(...)`
// —— 必须手写的理由（`ColorMod const&` 要从 Lua 的 `Color` 构造，形状机制表达不了那一步）
// 与 ABI 证据写在实现处注释与 `runtime_constants.hpp` 的 `kGameSpawnParticlesOffset` 段。
int GameSpawnParticles(lua_State* state);
// `Game:GetPlayer(index)` —— The Specialist for Good Items 的
// `main.lua:447` 在 `MC_POST_NEW_ROOM` 里用它取玩家（缺它整条回调被摘，跳舞/放歌都跑不到）。
int GameGetPlayer(lua_State* state);
// `Game:ChangeRoom(int roomIndex, int dimension)` —— 直接调引擎方法。
// GoodTrip 的传送主路径（`scripts/trip.lua` 6 处）就是 `Game():ChangeRoom(目标格, -1)`；
// 第二参 `-1` 在 PC 语义里是"按当前维度"。缺它 = method 不存在 ⇒ 整条回调被打断。

constexpr LuaHandlerBinding kGameHandlers[] = {
    {0x02010001, &GameIsPaused},
    {0x02010002, &GameIsGreedMode},
    {0x02010003, &GameGetLevel},
    {0x02010004, &GameGetItemPool},
    {0x02010005, &GameGetRoom},
    {0x02010006, &GameGetNumPlayers},
    {0x02010007, &GameGetFrameCount},
    {0x02010008, &GameGetSeeds},
    {0x02010009, &GameGetVictoryLap},
    // `Game:GetHUD()` —— MCM 每次开/关菜单都要用它拿 HUD。
    // id 取 Game 域下一个空号 0x000D（目录行与常量见 `api_catalog.cpp` / `runtime_constants.hpp`）。
    {0x0201000D, &GameGetHUD},
    // `Game:SpawnParticles`（域内序号 0x0014，取 Game 域 max+1）。
    {0x02010014, &GameSpawnParticles},
    // `Game:GetPlayer(index)`。真机证据：The Specialist for Good Items 的
    // `main.lua:447` 在 `MC_POST_NEW_ROOM` 里调它，报 `attempt to call a nil value (method 'GetPlayer')`
    // ⇒ 整条回调被派发器摘掉 ⇒ 用户看到"没音乐也不跳舞"。口径见实现处的注释（PC 契约逐字）。
    {0x0201000C, &GameGetPlayer},
    // `Game:Spawn(...)`（手写：引擎 `Game::SpawnEx` 的第 8 个形参
    // **走栈**，通用跳板只填 `x0..x7`/`d0..d7` ⇒ 数据行那条路会把栈上那格留成垃圾；
    // 手写由编译器按编译期签名放栈 ✓）。实现与 `Isaac.Spawn` 共用（都在 `isaac_api.cpp`）。
    {0x02010017, &GameSpawn},
};



// `Seeds` 家族（`Game:GetSeeds()` 的返回值）的方法表。EID 只用这两个；语义与依据见
// `api_catalog.cpp` 里对应条目的注释与 `SeedHandle` 的定义。
constexpr LuaHandlerBinding kSeedsHandlers[] = {
    {0x0F010001, &SeedsIsCustomRun},
    {0x0F010002, &SeedsGetStartSeed},
    // 中文版 MCM 要这三条（缺任一条都会打断它的开菜单回调）。
    {0x0F010004, &SeedsHasSeedEffect},
    {0x0F010005, &SeedsAddSeedEffect},
    {0x0F010006, &SeedsRemoveSeedEffect},
    // `Seeds:ForgetStageSeed(stage)`（取号 = Seeds 域下一个空号 0x0007）。
    {0x0F010007, &SeedsForgetStageSeed},
    // `Seeds:GetStageSeed(stage)` / `Seeds:GetNextSeed()`
    //（取号 = 域内接着的两个空号 0x0008 / 0x0009）。
    {0x0F010008, &SeedsGetStageSeed},
    {0x0F010009, &SeedsGetNextSeed},
};

constexpr char kSeedsOwner[] = "Seeds";

// `HUD` 家族（`Game:GetHUD()` 的返回值）的方法表。id 段见 `api_catalog.cpp` 的 `ApiDomain::Hud` 条目。
constexpr LuaHandlerBinding kHudHandlers[] = {
    {0x11010001, &HudIsVisible},
    {0x11010002, &HudSetVisible},
    {0x11010003, &HudRender},
    {0x11010004, &HudShowItemText},
    {0x11010005, &HudShowFortuneText},
};

constexpr char kHudOwner[] = "HUD";

// `Game` 家族在 Catalog 里的 owner 名（绑定表按它挑条目）。
constexpr char kGameOwner[] = "Game";

// --- `Game` 的两个只读标量 ---------------------------------------------
//
// 这两个方法都要读引擎内存，而 `game_observer` 的观察函数只回答"读到了什么"、不暴露
// `Game*` 本身，所以这里按 `interfaces/lua/isaac_api.cpp` 的同一套写法自带最小读取原语：
// 设备侧先用 `svcQueryMemory` 确认这段内存可读，宿主侧只排除空地址（宿主测试的"引擎内存"
// 是本进程 malloc 出来的伪造块，本来就一定可读）。
//
// **只读**：这两个方法都不写引擎内存。
// 「这段地址可读吗」：唯一实现在引擎内存访问层里（2026-09-24 收敛）。
// 此前四个 API 族各有一份逐字相同的拷贝（去掉注释后各 781 字符）；判决条件一条没改，
// 只是"实现在几处"从 4 变成了 1。**函数名保留** —— `test_lua_missing_members_batch028`
// 按这个名字核对四个手写处理器体里有没有做可读性检查。
bool IsEngineMemoryReadable(std::uintptr_t address, std::size_t length) noexcept {
    return isaac::runtime::engine_memory::EngineMemoryReadable(address, length);
}

template <typename T>
bool ReadEngine(std::uintptr_t address, T* value) noexcept {
    if (value == nullptr || !IsEngineMemoryReadable(address, sizeof(T))) {
        return false;
    }
    std::memcpy(value, reinterpret_cast<const void*>(address), sizeof(T));
    return true;
}

// 「这段地址可写吗」与写入口：与读侧同一套，实现在引擎内存访问层里（**唯一一份**）。
//
// 加写侧：`HUD:SetVisible(bool)` 是 `Game` 家族第一条写引擎内存的 API
//   （此前 `Game` 家族四个读数方法都只读，`game_api.cpp` 顶上的注释还写着"只读"）。
//   写与读的危险等级不同 —— 写错地址是静默破坏别人的内存（随机崩溃/存档损坏且事后无从归因），
//   所以这里照 `isaac_api.cpp` 的同一形态：**先确认可写，再写**，判定不通过就一个字节都不落。
bool IsEngineMemoryWritable(std::uintptr_t address, std::size_t length) noexcept {
    return isaac::runtime::engine_memory::EngineMemoryWritable(address, length);
}

template <typename T>
bool WriteEngine(std::uintptr_t address, const T& value) noexcept {
    return isaac::runtime::engine_memory::WriteAt(address, value, &IsEngineMemoryWritable);
}

// `Game*`：与 `Isaac.GetPlayer` **完全同一条链** —— 模块基址 + `kGameOwnerGlobalSlotOffset`
// 是 `g_Game` 的槽（槽里是**指针变量**，解一次才是 `Game*`，见 `isaac_api.cpp` 的
// `ResolveEntityPlayer`）。返回 0 = 拿不到。
//
// 这里刻意不用 `LuaRuntime::GameOwnerSlot()`（那是 `Game:IsPaused` 那一路的入口）：两个方法都
// 只读引擎内存，走"基址 + 槽偏移"就和 `Isaac.GetPlayer` 依赖同一份已发布状态，
// 少一个"要等 `SetGameBindings` 先跑过"的隐含前提；拿不到时降级行为见各自的注释。
std::uintptr_t ResolveGame() noexcept {
    const std::uintptr_t base = EngineModuleBase();
    if (base == 0 || base > UINTPTR_MAX - kGameOwnerGlobalSlotOffset) {
        return 0;
    }
    std::uintptr_t ownerSlot = 0;
    std::uintptr_t game = 0;
    if (!ReadEngine(base + kGameOwnerGlobalSlotOffset, &ownerSlot) || ownerSlot == 0 ||
        !ReadEngine(ownerSlot, &game) || game == 0) {
        return 0;
    }
    return game;
}

// `Game:GetNumPlayers()`：`players` 是 `Game + 0x25C50/+0x25C58` 处的
// `std::vector<Entity_Player*>`（步长 8），元素个数 = `(end - begin) / 8`。
//
// **口径必须与 `Isaac.GetPlayer` 完全一致（2026-09-12 真机报告 `01789207110` 修正）**：
// 两处都走 `ResolveEnginePlayerArray()`，它同时给出"元素个数"和"这次读成功了吗"。
//   * 读成功（`readable`）：**如实返回元素个数**，包括 0 —— 玩家向量为空就是没有玩家，
//     此时 `Isaac.GetPlayer(0)` 也返回 nil，两者一致；
//   * 读失败（不可读）：返回 **1**（单人降级）。这一档里 `GetPlayer(0)` 同样返回 nil，
//     但 EID 只会走"单人快路径"、不会进入 `for i = 0, n-1` 的循环（`main.lua:1065` 判的就是
//     `numPlayers == 1`），因此不会索引 nil。
//
// 修正前的写法是"任何读不到都答 1"（连**空向量**也答 1），于是 EID 的
// `features/eid_api.lua:2620` 循环体里 `Isaac.GetPlayer(0)` 拿到 nil、
// `player.QueuedItem` 直接抛错、派发器静默摘除该回调 —— 屏幕全空但游戏不崩，
// 属于最难查的一类现象。原注释担心"返回 0 会让 EID 走多人分支"，那个担心对
// **读失败**成立（故保留 1），对**读成功且为空**不成立（EID 的多人分支在 0 个玩家时同样不会执行循环体）。
int GameGetNumPlayers(lua_State* state) {
    RecordApiSequence(5U);
    luaL_checkudata(state, 1, kGameMetatable);
    if (lua_gettop(state) != 1) {
        return luaL_error(state, "Game:GetNumPlayers accepts no arguments");
    }
    const EnginePlayerArray players = ResolveEnginePlayerArray();
    // **拿不到玩家数组就答 0**（2026-09-12 第五轮修正：原来答 1）。
    //
    // 真机证据链（报告 `01789209134` → `01789209282` → `01789209426` → `01789209547`）：
    // 玩家向量在主界面是 `begin == end == 0`（空向量，`Isaac.GetPlayer(0)` 因此是 nil），
    // 而"读失败降级答 1"这一档让 EID 的
    //   `for i = 0, game:GetNumPlayers() - 1 do local player = Isaac.GetPlayer(i) ... player.QueuedItem`
    // （`features/eid_api.lua:2620-2625`）**真的进了循环体**，于是索引 nil、抛错、
    // 那两条回调被派发器静默摘除 —— 屏幕全空、游戏不崩，是最难查的形态。
    //
    // 口径统一后的规则很简单：**`GetNumPlayers()` 的答案必须让 `Isaac.GetPlayer(0)` 有意义**。
    //   * 数得出个数（含 0）→ 如实报；
    //   * 数不出个数         → 报 0（"不知道"按"没有"处理），而不是报 1 然后给 nil。
    // 旧的"答 1"理由（避免 EID 走多人分支）在**数不出个数**时并不成立：多人分支同样需要
    // `Isaac.GetPlayer`，而它那时也只能给 nil。
    if (!players.readable || players.count == 0) {
        g_LastNumPlayers.store(0, std::memory_order_relaxed);
        lua_pushinteger(state, 0);
        return 1;
    }
    g_LastNumPlayers.store(static_cast<std::uint32_t>(players.count), std::memory_order_relaxed);
    lua_pushinteger(state, static_cast<lua_Integer>(players.count));
    return 1;
}

// `Game:GetFrameCount()`：**引擎自己的帧计数** `Game + 0x24F99C`（u32，`Game::Update`
// 每帧 +1；`Entity::GetFrameCount`/`Room::GetFrameCount`/`Game::SaveState` 读的都是它，
// 指令级证据见 `runtime_constants.hpp`）。
//
// 退化路径：拿不到 `Game*` 或字段不可读时返回本 Runtime 自己的 `ManagedFrameClock`
// （`Isaac.GetFrameCount` 用的同一个时钟）。**这是近似值**：它按 Runtime 的 update 派发
// 前进，与引擎的"游戏内帧数"不保证逐值一致；数值单调递增，所以 EID 的
// `frame - lastTouch > 45`、`frame % maxAnimTime` 这类用法仍然成立。
// `Game:GetSeeds()`：返回一个 `Seeds` 句柄（**不持有引擎指针**，见 `SeedHandle` 的注释）。
//
// 为什么先这样做：EID 的 `features/eid_api.lua:2046` 直接 `game:GetSeeds():IsCustomRun()`，
// nil 会让整条 update 回调报错并被派发器摘除（真机报告 `01789210180`）。
// 句柄仍然只是个"身份"，但两个方法的返回值不再是自洽占位 ——
//   `GetStartSeed`/`IsCustomRun` 现在按调用时的 `Game + 0x25D40` 那条链真读引擎
//   （偏移与证据见 `runtime_constants.hpp` 的 `kGameSeedsObjectOffset`）。
int GameGetSeeds(lua_State* state) {
    RecordApiSequence(7U);
    luaL_checkudata(state, 1, kGameMetatable);
    if (lua_gettop(state) != 1) {
        return luaL_error(state, "Game:GetSeeds accepts no arguments");
    }
    auto* seeds = static_cast<SeedHandle*>(lua_newuserdata(state, sizeof(SeedHandle)));
    seeds->reserved = 0;
    luaL_getmetatable(state, kSeedsMetatable);
    lua_setmetatable(state, -2);
    return 1;
}

// `Game:GetVictoryLap()`：胜利圈计数 = `Game + 0x26FD50`（int32）。
//
// 偏移的主锚点是**写它的就是同名函数**：`Game::NextVictoryLap() @ 0x34FE00` 读这一格、`+1`
// 写回（`0x34FE58`/`0x34FE5C` 合成 0x26FD50、`0x34FE60 ldr w9,[x19,x8]`、`0x34FE68 str w10,[x19,x8]`），
// 首次进圈顺带把难度改成 HARD —— 与 PC 的跑圈语义逐条吻合；另有五个独立读者都拿它与
// 小整数（1/2/3）比较（HUD 的跑圈标记 `≥1 才画`、`Level::Init` 的 `==3`…）。逐条见
// `runtime_constants.hpp` 的 `kGameVictoryLapOffset`。
//
// 退化：拿不到 `Game*` / 字段读不到 ⇒ **返回 0**。EID 的用法全是 `> 0` 判断
// （`eid_api.lua:2360/2368`），返回 nil 会让那句直接抛 `attempt to compare nil with number`。
int GameGetVictoryLap(lua_State* state) {
    RecordApiSequence(8U);
    luaL_checkudata(state, 1, kGameMetatable);
    if (lua_gettop(state) != 1) {
        return luaL_error(state, "Game:GetVictoryLap accepts no arguments");
    }
    std::int32_t victoryLap = 0;
    const std::uintptr_t game = ResolveGame();
    if (game != 0 && game <= UINTPTR_MAX - kGameVictoryLapOffset &&
        ReadEngine(game + kGameVictoryLapOffset, &victoryLap)) {
        lua_pushinteger(state, static_cast<lua_Integer>(victoryLap));
        return 1;
    }
    lua_pushinteger(state, 0);
    return 1;
}

// `Game:GetPlayer(index)` —— PC 契约 `tools/pc_contract_docs/Game.md:337` 的签名
// `#### EntityPlayer GetPlayer ( int Index )`（`data-altreturn='nil'`）+ 同页 `:338` 正文逐字：
//   “Returns the EntityPlayer with the given index. This function can return `nil` if the function is
//    called before any player is initialized. **If an index is given, that is not used, it will return
//    the last player in the list.**”
//
// ⇒ 口径**只照这一页的正文**（它的徽章是 `.alldlc` = 全 DLC，含我们跑的忏悔本体）：
//   * 参数不是整数（含缺参数 / 浮点 / 字符串）⇒ **nil**，且**不抛 Lua 错误**
//     （与 `Isaac.GetPlayer` 同口径：被调用时不报错优先于"参数严格"）；
//   * 玩家向量读得到且非空：`0 <= index < count` ⇒ 那一个；**下标"没被用上"（越界或负数）⇒ 最后一个**；
//   * 向量为空 / 读不到 / 元素为空 / vptr 不符 ⇒ **nil**（两页正文都写"在任何玩家初始化之前调用可返回 nil"）。
//
// 为什么越界给"最后一个"而不是 nil（后者看着更"安全"）：The Specialist for Good Items 的
//   `main.lua:446` 写的是 `for playerNum = 1, game:GetNumPlayers() do local player = game:GetPlayer(playerNum)`
//   —— **1 基**循环，单人局第一句就是 `GetPlayer(1)`（越界）；返回 nil 会立刻在 `:450` 的
//   `player:GetPlayerType()` 上抛错、整条 `MC_POST_NEW_ROOM` 回调被摘（这正是本轮在修的现象）。
//   按正文给"最后一个"才是与模组在 PC 上的行为一致的做法。
//
// 为什么不像 `Isaac.GetPlayer` 那样越界给 nil：那一条是既有行为且有门禁钉着
//   （`test_lua_entity_player.py:731/736`、`test_lua_isaac_table.py:480` 断言越界/负数为 nil），
//   本轮不动它；两处口径的差异（以及 `Isaac.md:326` 那条 `.reporplus` 正文写的是
//   "非法 id ⇒ 按 0 处理"、属于 Repentance+ 而非本版本）登记在 `api_deviation.cpp` 的 0x0201000A。
int GameGetPlayer(lua_State* state) {
    luaL_checkudata(state, 1, kGameMetatable);
    if (lua_gettop(state) < 2 || !IsIntegerArgument(state, 2)) {
        lua_pushnil(state);
        return 1;
    }
    const std::int64_t requested = static_cast<std::int64_t>(lua_tointegerx(state, 2, nullptr));
    const EnginePlayerArray players = ResolveEnginePlayerArray();
    if (!players.readable || players.count == 0) {
        // 没有玩家（主界面/过渡期）⇒ nil。**不**降级成"造一个假玩家"：PC 正文允许 nil，
        // 而模组那边 `GetNumPlayers()` 同样报 0 ⇒ 它不会进循环、不会索引 nil。
        lua_pushnil(state);
        return 1;
    }
    // 2026-10-16固定PC 0x412792无符号比较；越界/负数走0x4127A0读取首玩家。
    const std::size_t index = requested >= 0 && static_cast<std::uint64_t>(requested) < players.count
                                  ? static_cast<std::size_t>(requested) : 0;
    const std::uintptr_t player = ResolveEnginePlayerAt(index);
    if (player == 0) {
        lua_pushnil(state);
        return 1;
    }
    // 视图与 `Isaac.GetPlayer` 交给 Lua 的那一个**完全一致**（`PushEntityCallbackArgument` 对
    // 通过 vptr 校验的玩家给 `EntityPlayer` 元表）—— 模组会立刻在它上面调 `:GetPlayerType()`。
    PushEntityCallbackArgument(state, player);
    return 1;
}

// `Seeds:IsCustomRun()`：PC 语义是"挑战局**或**带种子的局"（`tools/pc_contract_docs/Seeds.md:111`
// 签名 + `:112` 正文）。
//
// 真读数 —— `Game + 0x25D40` 那一个字节（`Seeds + 0x0`）非 0
// 即"本局用的是玩家自选种子"。三处写（控制台 `seed <串>` / 角色选择界面输入种子 / `StartDebug`）、
// 三处读（`Seeds::AchievementUnlocksDisallowed` 的 `非 0 ⇒ 本局禁成就`、`Seeds::Restart` 的
// `非 0 ⇒ 沿用同一颗种子`、本函数）互相印证；逐条指令见 `runtime_constants.hpp` 的
// `kSeedsCustomRunFlagOffset`。
//
// ⚠️ **挑战局那一半没有实现**：PC 文档把"挑战局"也算 `IsCustomRun`，而全镜像里写这一字节的
// 只有上面三处（没有挑战选择路径写它）；"挑战局会不会经由 `Seeds::operator=` 把它抄进来"
// 静态上排除不了 ⇒ 规格里 OR 上 `Game+0x26FA88`（eChallenge）的那一半是**推断**，
// 有待真机三点读数（普通局 / 输入种子局 / 挑战局）钉死或推翻（判据见
// `analysis/api-restore-game/README.md` §三.2）。**本轮刻意不猜**。
//
// 退化：`Game*` 或那一字节读不到 ⇒ `false`（与旧占位的取值相同，但现在是"读不到"，不是"恒假"）。
int SeedsIsCustomRun(lua_State* state) {
    static_cast<void>(luaL_checkudata(state, 1, kSeedsMetatable));
    if (lua_gettop(state) != 1) {
        return luaL_error(state, "Seeds:IsCustomRun accepts no arguments");
    }
    std::uint8_t flag = 0;
    const std::uintptr_t game = ResolveGame();
    if (game != 0 && game <= UINTPTR_MAX - kGameSeedsObjectOffset &&
        ReadEngine(game + kGameSeedsObjectOffset + kSeedsCustomRunFlagOffset, &flag)) {
        lua_pushboolean(state, flag != 0 ? 1 : 0);
        return 1;
    }
    lua_pushboolean(state, 0);
    return 1;
}

// ---------------------------------------------------------------------------
// `Seeds:HasSeedEffect` / `AddSeedEffect` / `RemoveSeedEffect`
// ---------------------------------------------------------------------------
//
// 谁在用：MCM 的 `OpenConfigMenu()` 里 `seeds:AddSeedEffect(SeedEffect.SEED_NO_HUD)`（顺手隐藏 HUD）、
// `CloseConfigMenu()` 里 `RemoveSeedEffect(...)`。**那几行不在 `pcall` 里** ⇒ 少一条就把"开菜单"
// 那条路径打断（症状与"菜单画不出来"一模一样）。
//
// 引擎侧取证（2026-09-30 反汇编）：
//   * `Seeds` 对象 = `Game + kGameSeedsObjectOffset`；布局见 `Seeds::Seeds @0x49CBD4`：
//     `+0x00` u8、`+0x04` u32（= 起始种子，`SetStartSeed` 写它）、`+0x08` 一个 RNG、
//     **`+0x58` 起是 `std::set<eSeedEffect>`**（libc++ `__tree`：end 在 `+0x58`、根在 `+0x60`）。
//   * ⇒ **生效中的种子效果存在那棵树里，不是位图** ⇒ `HasSeedEffect` 只能走树查找（下面内联的就是）。
//   * `Add/Remove` 在引擎里**唯一**的增删入口吃的是**名字字符串**
//     （`Seeds::AddSeedEffect(std::string) @0x4A1270` / `RemoveSeedEffect(std::string) @0x4A137C`）；
//     "枚举 → 名字"的唯一函数是 `Menu_SpecialSeed::GetSeedName(eSeedEffect) @0x417ADC` —— 它读
//     `this+0x1a0`，**是非静态成员**（要一个 `Menu_SpecialSeed` 实例，我们拿不到），
//     镜像里也搜不到那批名字串（`SEED_NO_HUD` / `NO HUD` 都没有）。
//   ⇒ **没有可信的实现路径**：所以这两条按"**不抛错的空实现**"处理 —— 这**不是**静默假成功，
//     次数记进探针 `g_SeedsEffectWriteAttempts`、口径写进 `api_deviation.cpp` 的台账。
//     取舍理由：抛错会把模组**整条回调**打断（MCM 的菜单就被这类错打断过一次），
//     而"这个种子效果没加上"只影响它那一个视觉特性（MCM 同时还会调 `HUD:SetVisible(false)`，那条是真的）。
// （探针 `g_SeedsEffectWriteAttempts` 的定义在**匿名命名空间之外**，见文件开头 —— 内部链接会让它读不到。）

// 2026-10-20更正：PC整数绑定直接set插入/删除，现按同一容器语义调用游戏分配器和
// libc++树平衡/删除，不再依赖菜单名字。旧“不可信/空实现”说明保留为历史，当前代码已替换。
// 树深度上限：红黑树高度 = 2*log2(n)，这里的元素最多几十个 ⇒ 64 层远远够；有环也不会死循环。
// 查找循环内联在处理器正文里（不抽公共助手）：桩检测器按"处理器正文里有没有碰引擎的标记"
// 判桩，把读整个藏进助手会让这条真实现被重新判成"安全桩"（`input_api.cpp` 里记过同一个坑）。
constexpr int kSeedsEffectSearchDepth = 64;

int SeedsHasSeedEffect(lua_State* state) {
    static_cast<void>(luaL_checkudata(state, 1, kSeedsMetatable));
    if (lua_gettop(state) != 2) {
        return luaL_error(state, "Seeds:HasSeedEffect accepts one seed effect");
    }
    const std::int32_t effect = static_cast<std::int32_t>(luaL_checkinteger(state, 2));
    const std::uintptr_t game = ResolveGame();
    if (game == 0 || game > UINTPTR_MAX - kGameSeedsObjectOffset) {
        lua_pushboolean(state, 0);
        return 1;
    }
    // 树查找：根 = `*(Seeds + 0x58 + 8)`，结点键在 `+0x1c`、左孩子 `+0x00`、右孩子 `+0x08`
    // （与 `Seeds::SeedEffectBlocksAchievements @0x49ED14` 的查找循环逐条对齐）。
    const std::uintptr_t seeds = game + kGameSeedsObjectOffset;
    std::uintptr_t node = 0;
    bool found = false;
    if (ReadEngine(seeds + kSeedsEffectTreeOffset + sizeof(void*), &node)) {
        for (int depth = 0; depth < kSeedsEffectSearchDepth && node != 0; ++depth) {
            std::int32_t key = 0;
            if (!ReadEngine(node + kLibcxxTreeNodeKeyOffset, &key)) {
                break;
            }
            if (key == effect) {
                found = true;
                break;
            }
            std::uintptr_t next = 0;
            if (!ReadEngine(node + (effect < key ? kLibcxxTreeNodeLeftOffset
                                                 : kLibcxxTreeNodeRightOffset), &next)) {
                break;
            }
            node = next;
        }
    }
    lua_pushboolean(state, found ? 1 : 0);
    return 1;
}

int SeedsAddSeedEffect(lua_State* state) {
    static_cast<void>(luaL_checkudata(state, 1, kSeedsMetatable));
    if (lua_gettop(state) != 2) {
        return luaL_error(state, "Seeds:AddSeedEffect accepts one seed effect");
    }
    const auto effect=static_cast<std::int32_t>(luaL_checkinteger(state, 2));
    g_SeedsEffectWriteAttempts.fetch_add(1, std::memory_order_relaxed);
    return MutateSeedEffect(state,ResolveGame(),effect,true);
}

// `Seeds:ForgetStageSeed(LevelStage Stage)` —— PC 契约 `tools/pc_contract_docs/Seeds.md`，语料 1 处。
//
// 引擎入口 `Seeds::ForgetStageSeed(eLevelStage)` @ `0x4A1228`（arity 1、返回 `void`）。
// `this` 不是句柄里存的地址：`Seeds` 是 `Game` 里内嵌的子对象（`Game + 0x25D40`，
//   证据见 `kGameSeedsObjectOffset` 段），所以每次按当前 `Game` 基址现算 ——
//   与 `Seeds:GetStartSeed()` 逐字同一条思路（换局/重建 `Game` 都不会拿到过期地址）。
// 入口 16 字节守卫写在 `runtime_constants.hpp`；这里用与 `Game:SpawnParticles` 相同的
//   `EngineOffsetAddress + VerifyEntryBytes` 两条关。
//
// 失败降级：拿不到 `Game` / 入口对不上 ⇒ **什么都不做、不报错**（PC 返回 `void`）。
int SeedsForgetStageSeed(lua_State* state) {
    static_cast<void>(luaL_checkudata(state, 1, kSeedsMetatable));
    if (lua_gettop(state) != 2 || !isaac::runtime::IsIntegerArgument(state, 2)) {
        return luaL_error(state, "Seeds:ForgetStageSeed expects a stage; got %d argument(s)",
                          lua_gettop(state) - 1);
    }
    const std::int32_t stage = static_cast<std::int32_t>(lua_tointegerx(state, 2, nullptr));
    const std::uintptr_t game = ResolveGame();
    const std::uintptr_t method =
        isaac::runtime::EngineOffsetAddress<IsEngineMemoryReadable>(kSeedsForgetStageSeedOffset);
    if (game == 0 || method == 0 ||
        !isaac::runtime::engine_call::VerifyEntryBytes(method, kSeedsForgetStageSeedExpectedBytes.data(),
                                                       kSeedsForgetStageSeedExpectedBytes.size(),
                                                       &IsEngineMemoryReadable)) {
        return 0;
    }
    using SeedsForgetStageSeedFn = void (*)(std::uintptr_t, std::int32_t);
    isaac::runtime::engine_call::AsFunction<SeedsForgetStageSeedFn>(method)(
        game + kGameSeedsObjectOffset, stage);
    return 0;
}

int SeedsRemoveSeedEffect(lua_State* state) {
    static_cast<void>(luaL_checkudata(state, 1, kSeedsMetatable));
    if (lua_gettop(state) != 2) {
        return luaL_error(state, "Seeds:RemoveSeedEffect accepts one seed effect");
    }
    const auto effect=static_cast<std::int32_t>(luaL_checkinteger(state, 2));
    g_SeedsEffectWriteAttempts.fetch_add(1, std::memory_order_relaxed);
    return MutateSeedEffect(state,ResolveGame(),effect,false);
}

// `Seeds:GetStageSeed(LevelStage Stage)` —— 契约 `tools/pc_contract_docs/Seeds.md:71/73`
// （`#### int GetStageSeed ( [LevelStage](enums/LevelStage.md) Stage )`）。
//
// 引擎侧 = 读 `Seeds + 0x18 + 4*Stage` 的一个 u32。**两条独立证据**（逐条写在
// `runtime_constants.hpp` 的段）：
//   * Switch 侧：`Seeds::Seeds()` 构造函数把内嵌 `RNG` 放在 `+0x8`（16 字节 ⇒ 到 `+0x18` 为止），
//     而 `Seeds::ForgetStageLevel(eLevelStage) @ 0x4A1228` 直接按下标读写这一格
//     （`add x19,x0,w1,uxtw #2` → `ldr w1,[x19,#0x18]` → … → `str w0,[x19,#0x18]`）；
//   * PC 侧：`GetStageSeed @ 0x705F30` = `mov eax, [esi + 4*eax + 0x18]` —— **基址与步长逐字相同**。
//
// 谁在用：`BOIStageAPI15` 用 `GetStageSeed(stage)` 去 `StageRNG:SetSeed(...)`（3 处）、
//   `MusicModCallback` 用它挑曲目（1 处）。返回 nil 会让 `SetSeed(nil)` 那条整块抛错。
//
// 边界：PC 那条绑定没有边界检查（函数开头只有一句"本局已开始"的断言）⇒ 越界就是读飞。
//   我们按 16 个槽降级（`+0x18` 到 `+0x58` 的 `__tree` 终点之间正好 16 个 u32）：
//   **越界返回 0、不报错** —— 与 `BoolBitArrayOfArg` 的越界降级同一口径的**刻意偏离**
//   （报错会摘掉整条模组回调，比"这个 stage 没种子"严重得多）。
int SeedsGetStageSeed(lua_State* state) {
    static_cast<void>(luaL_checkudata(state, 1, kSeedsMetatable));
    if (lua_gettop(state) != 2 || !isaac::runtime::IsIntegerArgument(state, 2)) {
        return luaL_error(state, "Seeds:GetStageSeed expects a stage");
    }
    const std::int64_t stage = static_cast<std::int64_t>(lua_tointegerx(state, 2, nullptr));
    if (stage < 0 || static_cast<std::uint64_t>(stage) >= kSeedsStageSeedSlotCount) {
        lua_pushinteger(state, 0);  // 越界：PC 会读飞，我们降级（刻意偏离）
        return 1;
    }
    std::uint32_t raw = 0;
    const std::uintptr_t game = ResolveGame();
    const std::uintptr_t within =
        kGameSeedsObjectOffset + kSeedsStageSeedArrayOffset +
        kSeedsStageSeedStride * static_cast<std::uintptr_t>(stage);
    if (game != 0 && within <= UINTPTR_MAX - game && ReadEngine(game + within, &raw)) {
        // PC 的返回类型是 `int` ⇒ 按 int32 呈现（与 `GetStartSeed` 同一口径）。
        lua_pushinteger(state, static_cast<lua_Integer>(static_cast<std::int32_t>(raw)));
        return 1;
    }
    lua_pushinteger(state, 0);  // 拿不到 `Game*` / 读不到 ⇒ 0（不报错）
    return 1;
}

// `Seeds:GetNextSeed()` —— 契约 `tools/pc_contract_docs/Seeds.md:56/58`（`#### int GetNextSeed ( )`）。
//
// 它不是一次字段读：PC 的绑定本体（`0x6C4560`）把 `RNG::Next()` 内联在里面 ——
//   读 `Seeds+0x8/+0xc/+0x10/+0x14` 四个字做 xorshift、**写回 `Seeds+0x8`**、并在 `eax` 里返回。
//   Switch 侧同一个函数（`RNG::Next() @ 0x44E464`）是**独立符号**、指令逐句同形
//   （`ldp w9,w10,[x19,#0x4]` / `ldr w9,[x19,#0xc]` / `str w0,[x19]`）。
//   ⇒ 正确做法 = **调引擎自己的 `RNG::Next()`**、`this` 传 `Seeds + 0x8`，
//     而不是自己抄一份 xorshift（抄了就是第二份真值源，迟早与引擎漂）。
//
// 复用 `RNG:Next` 那条已经立好的发布链路（`RngNextThunk()` + 16 字节入口指纹
//   `ValidateRngNextBinding()`）—— **同一条引擎函数、同一份指纹，不另立一份**。
//
// 谁在用：`TBOI_Better-Voiding` 把它当 `Game:Spawn` 的种子、`IsaacOnTwitchReloaded`
//   把它喂给 `MakeChampion(seed)`（3 处）。**这条会推进引擎的种子 RNG**（与 PC 一致）。
//
// 退化：拿不到 `Game*` / 绑定不可用 ⇒ 压 0（PC 的返回类型是 `int`；压 nil 会让
//   `Spawn(..., nil)` 与 `MakeChampion(nil)` 抛错）。**不报错**。
int SeedsGetNextSeed(lua_State* state) {
    static_cast<void>(luaL_checkudata(state, 1, kSeedsMetatable));
    if (lua_gettop(state) != 1) {
        return luaL_error(state, "Seeds:GetNextSeed accepts no arguments");
    }
    const std::uintptr_t game = ResolveGame();
    const std::uintptr_t method = RngNextThunk();
    const std::uintptr_t within = kGameSeedsObjectOffset + kSeedsRngOffset;
    if (game == 0 || method == 0 || !ValidateRngNextBinding(method) ||
        within > UINTPTR_MAX - game) {
        lua_pushinteger(state, 0);
        return 1;
    }
    // `RNG::Next()` 的返回值就是新种子（`RNG::Next @ 0x44e4ac` 把结果放在 `w0`，
    // `0x44e4b0` 再写回 `[x19]`）—— 与 `RNG:Next` 那个处理器读回内存是同一个值的两种取法。
    using NextFn = std::uint32_t (*)(void*);
    const std::uint32_t next =
        isaac::runtime::engine_call::AsFunction<NextFn>(method)(
            isaac::runtime::engine_memory::AsObject(game + within));
    lua_pushinteger(state, static_cast<lua_Integer>(static_cast<std::int32_t>(next)));
    return 1;
}

// `Seeds:GetStartSeed()`：本局起始种子 = `Game + 0x25D44`（= `Seeds + 0x4`，uint32）。
//
// 唯一写它的是 `Seeds::SetStartSeed(unsigned) @ 0x4A1114`（`str w1,[x0,#0x4]`，0 时取
// `RandomU32() ?: 1` —— 与 PC 文档 `Seeds.md:79` 的"1 与 2^32-1 之间"吻合）；另有两处独立读到它。
//
// 文档值域是 1..2^32-1，Lua integer 可完整保存；不能经 int32 符号扩展。
// EID 直接用它运行 Lua xorshift，负种子会让随机配方错误落到道具 1。
// 退化：`Game*` 或字段读不到 ⇒ 0（主菜单里 PC 本来就返回 0，`Seeds.md:81`）。
int SeedsGetStartSeed(lua_State* state) {
    static_cast<void>(luaL_checkudata(state, 1, kSeedsMetatable));
    if (lua_gettop(state) != 1) {
        return luaL_error(state, "Seeds:GetStartSeed accepts no arguments");
    }
    std::uint32_t raw = 0;
    const std::uintptr_t game = ResolveGame();
    if (game != 0 && game <= UINTPTR_MAX - (kGameSeedsObjectOffset + kSeedsStartSeedOffset) &&
        ReadEngine(game + kGameSeedsObjectOffset + kSeedsStartSeedOffset, &raw)) {
        lua_pushinteger(state, static_cast<lua_Integer>(raw));
        return 1;
    }
    lua_pushinteger(state, 0);
    return 1;
}

// `Game:GetHUD()`：返回一个 `HUD` 句柄（不持有引擎指针，
// 见 `HudHandle` 的注释）。
//
// PC 契约 `tools/pc_contract_docs/Game.md`（`HUD GetHUD ( )`，`.alldlc`）。消费者是 MCM：
// `scripts/modconfig.lua:1199/2939/2961` 拿 HUD 再 `hud:SetVisible(false/true)` 把血条藏起来/
// 恢复（`:1202/1206` 还读 `hud:IsVisible()`）。缺它 = "attempt to call a nil value
// (method 'GetHUD')" ⇒ 整条开/关菜单回调被摘（这正是本轮要补的那条路）。
//
// 句柄只是个"身份"：`HUD` 是 `Game` 里**内嵌**的子对象（`Game* + 0xE8468`，引擎里不存在指向
// 它的指针），所以两个方法每次按当前 `Game` 基址现算 —— 换局/重建 `Game` 都不会拿到过期地址。
// 与 `Game:GetSeeds()` 逐字同一条思路（`SeedHandle` 的注释）。
// `Game:SpawnParticles(...)` —— PC 契约 `tools/pc_contract_docs/Game.md:546`：
//   `#### void SpawnParticles ( Vector Pos, EffectVariant ParticleType, int NumParticles,
//      float Speed, Color Color = Color.Default, float Height = 100000, int SubType = 0 )`
//
// 语料（`IsaacOnTwitchReloaded` 14 处）一律 `Game():SpawnParticles(pos, EffectVariant.X, n, speed,
// Color(...), h)` —— **真实体调用**（`self` 在栈上），颜色**总是显式给**（所以缺省那一支只有
// 契约口径可依，见下）。
//
// ABI（反汇编 `0x3598F8`，逐条见 `runtime_constants.hpp` 的 `kGameSpawnParticlesOffset` 段）：
//   `(this=x0, pos=x1, variant=w2, count=w3, speed=s0, colorMod=x4, height=s1, subtype=w5)`，
//   返回 `void`。两处容易写错的地方都有指令为证：`Height` 走 **`s1`**（不是因为它是第 6 个参数
//   就走 s1 —— 是因为 `speed` 占了 `s0`），而且引擎会拿 `height == 100000.0f` 比一次决定分支
//   ⇒ 缺省值必须按契约原文给 `100000`，不能给 0。
//
// 为什么不写成数据行（项目的第一选择）：`ColorMod const&` 不是"把 Lua 值按标量宽度搬进寄存器"，
//   而是**要先从 Lua 的 `Color` 句柄构造一个 44 字节的引擎对象**（`kColorModSize = 0x2C`、
//   tint@+0x00、shift@+0x10 —— 见 `kSpriteColorOffset` 段）⇒ 形状机制表达不了这一步，只能手写。
//   颜色 → `ColorMod` 的映射与 `sprite_api.cpp` 写 `Sprite.Color` 时那一份逐字同源
//     （tint = R/G/B/A、shift = 三个偏移分量、其余留 0）；两处必须一起改。
//
// 失败降级：拿不到 `Game*` / 入口指纹不符 ⇒ 什么都不做（返回 `void`，与 PC 同）且不报错
//   —— 这是定的口径（读不到原生状态不许抛 Lua 错误）。
int GameSpawnParticles(lua_State* state) {
    luaL_checkudata(state, 1, kGameMetatable);
    const int arguments = lua_gettop(state);  // 含 `self`
    if (arguments < 5 || arguments > 8) {
        return luaL_error(state, "Game:SpawnParticles expects 4 to 7 arguments");
    }
    auto* position =
        TryVectorArgument(state,2);
    if (position == nullptr) {
        return luaL_error(state, "Game:SpawnParticles expects a Vector position");
    }
    if (!isaac::runtime::IsIntegerArgument(state, 3) ||
        !isaac::runtime::IsIntegerArgument(state, 4)) {
        return luaL_error(state, "Game:SpawnParticles expects an effect variant and a count");
    }
    const auto variant = static_cast<std::int32_t>(lua_tointegerx(state, 3, nullptr));
    const auto count = static_cast<std::int32_t>(lua_tointegerx(state, 4, nullptr));
    const float speed = static_cast<float>(luaL_checknumber(state, 5));

    // 引擎侧的 `ColorMod`（44 字节，布局见 `kColorModSize` 段）起住在
    // `engine_color_mod.hpp` —— 本条的 `Color` 参数与 `Entity:SetColor` 的第一个参数
    // 是同一个类型，映射只留一份（原先这里是个函数内局部结构，再抄一份就是第三份）。
    // 下面这行 `static_assert` 保留在原地：门禁 `test_lua_game_spawn_particles.py`
    // 钉住"这个处理器确实在用那个被钉住尺寸的类型"；尺寸本身的断言在头里也有一份。
    static_assert(sizeof(EngineColorMod) == kColorModSize,
                  "ColorMod 的字段数变了（见 kColorModSize 的取证）");
    EngineColorMod color = isaac::runtime::DefaultEngineColorMod();
    if (lua_toboolean(state, 6)) {
        // 缺省（不给第 5 个参数）就是契约的 `Color.Default` —— 白色不透明，
        // 也就是 `DefaultEngineColorMod()` 那份全 1 的 tint。
        if (!isaac::runtime::FillEngineColorMod(state, 6, &color)) {
            return luaL_error(state, "Game:SpawnParticles expects a Color");
        }
    }
    float height = 100000.0F;  // 契约缺省；引擎会拿它比一次，别改成 0
    if (lua_toboolean(state, 7)) {
        height = static_cast<float>(luaL_checknumber(state, 7));
    }
    unsigned int subtype = 0;
    if (lua_toboolean(state, 8)) {
        if (!isaac::runtime::IsIntegerArgument(state, 8)) {
            return luaL_error(state, "Game:SpawnParticles expects an integer subtype");
        }
        subtype = static_cast<unsigned int>(lua_tointegerx(state, 8, nullptr));
    }

    const std::uintptr_t game = ResolveGame();
    const std::uintptr_t method =
        isaac::runtime::EngineOffsetAddress<IsEngineMemoryReadable>(kGameSpawnParticlesOffset);
    if (game == 0 || !isaac::runtime::EngineEntryWordMatches(method, kGameSpawnParticlesEntryWord)) {
        return 0;  // 降级：什么都不做、不报错（PC 的返回类型就是 void）
    }
    // 参数表按 ABI 逐条对齐（`Vector2 const&` 与 `ColorMod const&` 都是指针）。
    using GameSpawnParticlesFn =
        void (*)(void*, const LuaRuntime::VectorHandle*, int, int, float, const EngineColorMod*,
                 float, unsigned int);
    isaac::runtime::engine_call::AsFunction<GameSpawnParticlesFn>(method)(
        isaac::runtime::engine_memory::AsObject(game), position, variant, count, speed, &color,
        height, subtype);
    return 0;
}

int GameGetHUD(lua_State* state) {
    RecordApiSequence(9U);
    luaL_checkudata(state, 1, kGameMetatable);
    if (lua_gettop(state) != 1) {
        return luaL_error(state, "Game:GetHUD accepts no arguments");
    }
    auto* hud = static_cast<HudHandle*>(lua_newuserdata(state, sizeof(HudHandle)));
    hud->reserved = 0;
    luaL_getmetatable(state, kHudMetatable);
    lua_setmetatable(state, -2);
    return 1;
}

// `HUD` 两个方法共用的地址解析：内嵌的 HUD 对象地址 = `Game* + 0xE8468`（加法，不是解引用）。
// 返回 0 = 拿不到（`Game*` 解析失败 / 加法回绕）。
std::uintptr_t ResolveHud() noexcept {
    const std::uintptr_t game = ResolveGame();
    if (game == 0 || game > UINTPTR_MAX - kGameHudObjectOffset) {
        return 0;
    }
    return game + kGameHudObjectOffset;
}

// `HUD:IsVisible()`：PC 契约 `tools/pc_contract_docs/HUD.md:41/43`（`#### boolean IsVisible ( )`）。
//
// 判据是 `HUD::Render()` @ `0x3AC71C` 开头那四条指令读的**同一个字节**（`HUD + 0xC53FA`）：
//     0x3AC74C  mov  w8, #0x53fa
//     0x3AC750  movk w8, #0xc, lsl #16     ; w8 = 0xC53FA
//     0x3AC754  ldrb w8, [x0, x8]
//     0x3AC758  cbz  w8, 0x3AE3B4          ; == 0 ⇒ 跳过整段 HUD 渲染
// 取证逐条见 `runtime_constants.hpp` 的 `kHudVisibleFlagOffset`。它不是猜的：这是**唯一**一处
// 让整块 HUD 不画的条件，也正是 PC 那个访问器的语义。
//
// 退化：`Game*` / 那一字节读不到 ⇒ **压 `false`、不报错**。理由与 `Seeds:IsCustomRun` 同一条：
// 抛 Lua 错误会让整条回调被派发器摘掉；压 `false` 在 `if hud:IsVisible() then`（MCM `:1202`）
// 上等于"没显示"，是安全的一侧。
int HudIsVisible(lua_State* state) {
    RecordApiSequenceSecondary(19U);
    static_cast<void>(luaL_checkudata(state, 1, kHudMetatable));
    if (lua_gettop(state) != 1) {
        return luaL_error(state, "HUD:IsVisible accepts no arguments");
    }
    std::uint8_t visible = 0;
    const std::uintptr_t hud = ResolveHud();
    if (hud != 0 && hud <= UINTPTR_MAX - kHudVisibleFlagOffset &&
        ReadEngine(hud + kHudVisibleFlagOffset, &visible)) {
        lua_pushboolean(state, visible != 0 ? 1 : 0);
        return 1;
    }
    lua_pushboolean(state, 0);
    return 1;
}

// `HUD:SetVisible(bool Visible = false)`：PC 契约 `tools/pc_contract_docs/HUD.md:54/56`。
//
// PC 的缺省值是 `false`（文档签名里就写着），所以 Lua 侧不传参数时按 `false` 写 0
//   —— 与 `Entity:IsActiveEnemy(bool includeDead)` 那种"不传即 false"同一口径。
//   参数非布尔（数字/字符串/nil）时也按 `false` 处理、**不抛错**：`lua_toboolean` 就是 PC 侧
//   Lua→C++ `bool` 的转换口径（0 与空串为真，只有 `false`/`nil` 为假），而 MCM 传的一律是
//   `false`/`true` 字面量。
//
// 本模块第一条"写 UI 状态"的 API：写的就是 `HUD + 0xC53FA` 那一个字节，也就是
//    `HUD::Render()` 用来决定"整块 HUD 画不画"的开关。写坏这一格的代价是 HUD 不见（直到重进
//    游戏），所以：只在 `Game*` 与那一字节都通过可写判定时才落值（`WriteEngine` 内部先判定），
//    写失败**不报错** —— MCM 的 `OpenConfigMenu`/`CloseConfigMenu`（`modconfig.lua:2939/2961`）
//    是**光秃秃的顺序语句**，没有任何容错分支，抛错会连累整条回调。
// 该偏离（"我们会写引擎内存"）登记在 `api_deviation.cpp`。
int HudSetVisible(lua_State* state) {
    RecordApiSequenceSecondary(20U);
    static_cast<void>(luaL_checkudata(state, 1, kHudMetatable));
    const int arguments = lua_gettop(state);
    if (arguments > 2) {
        return luaL_error(state, "HUD:SetVisible accepts at most one argument");
    }
    const bool visible = arguments >= 2 && lua_toboolean(state, 2) != 0;
    const std::uint8_t flag = visible ? 1U : 0U;
    const std::uintptr_t hud = ResolveHud();
    if (hud != 0 && hud <= UINTPTR_MAX - kHudVisibleFlagOffset) {
        static_cast<void>(WriteEngine(hud + kHudVisibleFlagOffset, flag));
    }
    return 0;
}
// 只在Lua显式请求时运行；帧上不建表、不读文件。字符串仍由原生HUD转换并绘制。
template<std::size_t N> std::uintptr_t HudNative(lua_State* state,std::uintptr_t offset,
    const std::array<unsigned char,N>& guard) {
    const auto method=EngineOffsetAddress<IsEngineMemoryReadable>(offset);
    if(!method || !engine_call::VerifyEntryBytes(method,guard.data(),N,&IsEngineMemoryReadable))
        luaL_error(state,"HUD native binding is unavailable");
    return method;
}
void* HudReceiver(lua_State* state) {
    luaL_checkudata(state,1,kHudMetatable);
    const auto hud=ResolveHud();if(!hud)luaL_error(state,"HUD is unavailable");
    return engine_memory::AsObject(hud);
}
int HudRender(lua_State* state) {
    auto* hud=HudReceiver(state);using Fn=void(*)(void*);Fn method=nullptr;
#if !defined(__SWITCH__)
    method=g_HudNativeTest.render;
#endif
    if(!method)method=engine_call::AsFunction<Fn>(HudNative(state,kHudRenderOffset,kHudRenderExpectedBytes));
    method(hud);return 0;
}
int HudShowItemText(lua_State* state) {
    auto* hud=HudReceiver(state);
    if(luaL_testudata(state,2,LuaRuntime::kEntityPlayerMetatable)) {
        const auto player=EntityPointerArgument(state,2);const auto item=ItemConfigPointerArgument(state,3);
        if(!player||!item)return luaL_error(state,"HUD:ShowItemText requires a live player and item");
        using Fn=void(*)(void*,void*,const void*);Fn method=nullptr;
#if !defined(__SWITCH__)
        method=g_HudNativeTest.item;
#endif
        if(!method)method=engine_call::AsFunction<Fn>(HudNative(state,kHudShowItemObjectOffset,kHudShowItemObjectExpectedBytes));
        method(hud,engine_memory::AsObject(player),engine_memory::AsObject(item));return 0;
    }
    const char* main=luaL_optstring(state,2,"");const char* secondary=luaL_optstring(state,3,"");
    const bool curse=lua_toboolean(state,4)!=0;
    using Fn=void(*)(void*,const char*,const char*,bool,bool);Fn method=nullptr;
#if !defined(__SWITCH__)
    method=g_HudNativeTest.text;
#endif
    if(!method)method=engine_call::AsFunction<Fn>(HudNative(state,kHudShowItemTextOffset,kHudShowItemTextExpectedBytes));
    // PC原包装把隐藏的第一个bool固定false，IsCurseDisplay传第二bool；不冒充官方DLC新参数。
    method(hud,main,secondary,false,curse);return 0;
}
int HudShowFortuneText(lua_State* state) {
    auto* hud=HudReceiver(state);
    // 固定PC7FB300最多消费32个字符串，遇nil/缺失结束；NS const list按size和next消费。
    struct Link {Link* prev;Link* next;};
    struct String {std::uintptr_t capacity;std::size_t length;const char* data;};
    struct Node {Link link;String string;};
    struct List {Link head;std::size_t count;};
    static_assert(sizeof(Node)==40 && sizeof(List)==24,"libc++ list<string> ABI");
    Node nodes[32]{};List list{};list.head={&list.head,&list.head};
    for(int i=2;i<=33 && !lua_isnoneornil(state,i);++i) {
        if(lua_type(state,i)!=LUA_TSTRING)return luaL_error(state,"HUD:ShowFortuneText expects strings");
        auto& node=nodes[list.count];node.string.data=lua_tolstring(state,i,&node.string.length);
        node.string.capacity=(node.string.length+1)|1U;
        node.link={list.head.prev,&list.head};list.head.prev->next=&node.link;list.head.prev=&node.link;
        ++list.count;
    }
    using Fn=void(*)(void*,const void*);Fn method=nullptr;
#if !defined(__SWITCH__)
    method=g_HudNativeTest.fortune;
#endif
    if(!method)method=engine_call::AsFunction<Fn>(HudNative(state,kHudShowFortuneTextOffset,kHudShowFortuneTextExpectedBytes));
    method(hud,&list);return 0;
}


int GameGetFrameCount(lua_State* state) {
    RecordApiSequence(6U);
    luaL_checkudata(state, 1, kGameMetatable);
    if (lua_gettop(state) != 1) {
        return luaL_error(state, "Game:GetFrameCount accepts no arguments");
    }
    const std::uintptr_t game = ResolveGame();
    std::uint32_t frames = 0;
    if (game != 0 && game <= UINTPTR_MAX - kGameFrameCountOffset &&
        ReadEngine(game + kGameFrameCountOffset, &frames)) {
        lua_pushinteger(state, static_cast<lua_Integer>(frames));
        return 1;
    }
    lua_pushinteger(state, static_cast<lua_Integer>(ManagedFrameClock::Count()));
    return 1;
}

int GameIsPaused(lua_State* state) {
    RecordApiSequence(0U);
    luaL_checkudata(state, 1, kGameMetatable);
    if (lua_gettop(state) != 1) {
        return luaL_error(state, "Game:IsPaused accepts no arguments");
    }
    // 2026-09-19：这里原本有一道 `InManagedCallbackScope()` 守卫，
    // 不在托管回调里就直接抛错（"… is only available during a Runtime callback"）。
    // **PC 没有这条限制**：模组在**加载期**读引擎状态是常见写法（GoodTrip 的
    // `scripts/floor.lua:11-17` 就在加载期读 `Game():GetLevel()`/`GetRoom()`/`Level:GetStage()`），
    // 而报错会让整个模组的功能**整块消失**（真机现象："模组像没装"）。
    // 所以守卫已删除：允许读，读不到时由各自实现返回**如实回退值**。
    // 证据与理由见 `docs/改动日志-20260919.md`（042·补二 / 043）。

    const std::uintptr_t ownerSlot = GameOwnerSlot();
    const std::uintptr_t isPausedThunk = GameIsPausedThunk();
    if (ownerSlot == 0 || isPausedThunk == 0) {
        return luaL_error(state, "Game:IsPaused native bindings are unavailable");
    }

    if (console::ConsolePaused()) {
        g_LastIsPaused.store(1, std::memory_order_relaxed);
        lua_pushboolean(state, 1);
        return 1;
    }
    const GameIsPausedObservation observation = ObserveGameIsPaused(ownerSlot, isPausedThunk);
    if (observation == GameIsPausedObservation::PausedFalse) {
        g_LastIsPaused.store(0, std::memory_order_relaxed);  // 探针：最后一次返回 false
        lua_pushboolean(state, 0);
        return 1;
    }
    if (observation == GameIsPausedObservation::PausedTrue) {
        g_LastIsPaused.store(1, std::memory_order_relaxed);  // 探针：最后一次返回 true
        lua_pushboolean(state, 1);
        return 1;
    }
    return PushNativeFallbackBoolean(state, kFbGameIsPaused, false);
}

int GameIsGreedMode(lua_State* state) {
    luaL_checkudata(state, 1, kGameMetatable);
    if (lua_gettop(state) != 1) {
        return luaL_error(state, "Game:IsGreedMode accepts no arguments");
    }
    const GameIsGreedModeObservation observation =
        ObserveGameIsGreedMode(GameOwnerSlot(), GameIsGreedModeThunk());
    if (observation == GameIsGreedModeObservation::GreedFalse) {
        lua_pushboolean(state, 0);
        return 1;
    }
    if (observation == GameIsGreedModeObservation::GreedTrue) {
        lua_pushboolean(state, 1);
        return 1;
    }
    return PushNativeFallbackBoolean(state, kFbGameIsGreedMode, false);
}

// `Game:ChangeRoom(int roomIndex, int dimension)`。
// 底座：`IsaacRepentance::Game::ChangeRoom(int, int)` @ `0x353FE0`（符号
// `_ZN15IsaacRepentance4Game10ChangeRoomEii`），模块基址 + 偏移 + 入口 4 字节指纹
// （判据见 `engine_method_lookup.hpp`）。
int GameGetLevel(lua_State* state) {
    RecordApiSequence(2U);
    luaL_checkudata(state, 1, kGameMetatable);
    if (lua_gettop(state) != 1) {
        return luaL_error(state, "Game:GetLevel accepts no arguments");
    }
    auto* level = static_cast<LevelHandle*>(lua_newuserdata(state, sizeof(LevelHandle)));
    level->reserved = 0;
    luaL_getmetatable(state, kLevelMetatable);
    lua_setmetatable(state, -2);
    return 1;
}

int GameGetItemPool(lua_State* state) {
    RecordApiSequence(3U);
    luaL_checkudata(state, 1, kGameMetatable);
    if (lua_gettop(state) != 1) {
        return luaL_error(state, "Game:GetItemPool accepts no arguments");
    }
    void* itemPool = nullptr;
    if (ReadCurrentGameItemPool(GameOwnerSlot(), &itemPool) != GameItemPoolObservation::Success) {
        // 给空壳句柄（既不报错、也不给 nil）。`ItemPool` 句柄本身不持指针
        // （方法每次从全局槽现查），所以空壳没有野指针风险，只是它的方法会各自回退。
        // **PC 在这里返回的是对象** —— 同一个文件上面的 `Game:GetLevel` 一直是"永远给句柄"
        // 的写法（它从不失败），这里与它对齐；口径与理由见 `native_state_fallback.hpp`。
        RecordNativeStateFallback(kFbGameGetItemPool);
        auto* fallbackHandle = static_cast<ItemPoolHandle*>(
            lua_newuserdata(state, sizeof(ItemPoolHandle)));
        fallbackHandle->reserved = 0;
        luaL_getmetatable(state, kItemPoolMetatable);
        lua_setmetatable(state, -2);
        return 1;
    }
    auto* handle = static_cast<ItemPoolHandle*>(lua_newuserdata(state, sizeof(ItemPoolHandle)));
    handle->reserved = 0;
    luaL_getmetatable(state, kItemPoolMetatable);
    lua_setmetatable(state, -2);
    return 1;
}

int GameGetRoom(lua_State* state) {
    RecordApiSequence(4U);
    luaL_checkudata(state, 1, kGameMetatable);
    if (lua_gettop(state) != 1) {
        return luaL_error(state, "Game:GetRoom accepts no arguments");
    }
    void* room = nullptr;
    if (ReadCurrentGameRoom(GameOwnerSlot(), &room) != GameRoomObservation::Success) {
        // 给空壳句柄（既不报错、也不给 nil）。PC 在这里返回的是对象 ——
        // 模组作者就是敢直接写 `Game():GetRoom():GetType()`（GoodTrip 的 `scripts/floor.lua:15`
        // 直接把结果存进 `M.room` 再调它的方法）；给 nil 会让那句 "attempt to index a nil value"
        // 把**整个模组**的加载打断，而给空壳只是让该房间的方法各自回退。
        RecordNativeStateFallback(kFbGameGetRoom);
        auto* fallbackHandle = static_cast<RoomHandle*>(lua_newuserdata(state, sizeof(RoomHandle)));
        fallbackHandle->reserved = 0;
        luaL_getmetatable(state, kRoomMetatable);
        lua_setmetatable(state, -2);
        return 1;
    }
    auto* handle = static_cast<RoomHandle*>(lua_newuserdata(state, sizeof(RoomHandle)));
    handle->reserved = 0;
    luaL_getmetatable(state, kRoomMetatable);
    lua_setmetatable(state, -2);
    return 1;
}

} // namespace

// `Game` 的**字段**访问（2026-09-16，字段缺口台账的 planned 项）。
//
// PC 契约里这几个是字段（`game.Challenge`、`game.Difficulty`、`game.TimeCounter`、
// `game.ScreenShakeOffset`），不是方法 ⇒ 必须挂在 `__index` 上。`__index` 原来直接是**方法表**，
// 所以这里改成一个 C 函数：先认这几个字段，认不出就落到方法表（方法表作为上值 1 带进来）。
// **绝不能**让字段查找吞掉方法名 —— 那会让 `game:GetRoom()` 之类静默失效。
//
// 偏移证据（全部 2026-09-16 静态取证，NRO 文件偏移 = 运行时模块偏移；每条在两处不同函数里复核）：
//   * `Challenge = Game + 0x26FA88`：`Game::Start(ePlayerType,eChallenge,Seeds,eDifficulty) @ 0x34E570`
//     `str w2,[this+0x26FA88]`（w2 = 第 2 个参数）；`Game::GetChallengeParams @ 0x34EA9C` 读它后
//     尾跳 `Manager::GetChallengeParams(eChallenge)`；`Game::SaveState @ 0x350678` 也抄它。
//   * `Difficulty = Game + 0x2F0028`：`Game::Start @ 0x34E56C` `str w4,[this+0x2F0028]`（w4 = 第 4 个参数）；
//     `Game::IsHardMode @ 0x3501EC` 读它并 `and #0xfffffffd; cmp #1`（`IsGreedMode @ 0x350208` 同址
//     `and #0xfffffffe; cmp #2` —— 正是本项目已在打补丁的那条函数，互为印证）。
//   * `TimeCounter = Game + 0x24F9A0`：`Game::Update @ 0x352114-0x352120` 每帧与 `FrameCount(0x24F99C)`
//     一起 `+1`（`ldp w8,w9,[x24,#0x4]` … `stp`，x24 = Game+0x24F998）；控制台 `time` 命令 @0x3EF48
//     用 `ldrsw`（**有符号**）读它再除以 30。
//   * `ScreenShakeOffset = Game + 0x24F9B0`：与既有常量 `kGameToScreenAdjustOffset` **同一个字段**
//     （结构名 vs PC 名），这里只加一个更贴 PC 的别名，不新增第二个偏移。
//     `Game::Update @ 0x3518EC-0x35191C` 在震动帧数 `+0x24F9AC` 归零那一帧把它设成 `Vector2::Zero`；
//     `Camera::update_drag2 @ 0x34164` 写它；`Room::Render @ 0x47FD60` 把它加进渲染坐标。
//
// 读不到时按 PC 的"字段不存在"口径给 nil（而不是编 0/编向量）—— EID 用
// `game.ScreenShakeOffset` 做减法，编一个 0 向量会让画面抖动时描述位置偏掉。
int GameIndex(lua_State* state) {
    if (lua_type(state, 2) != LUA_TSTRING) {
        lua_pushnil(state);
        return 1;
    }
    const char* field = lua_tostring(state, 2);
    const std::uintptr_t game = ResolveGame();
    if (game != 0) {
        if(const int n=TryPushApi600WorldField(state,game,"Game",field))return n;
        if (std::strcmp(field, "Challenge") == 0) {
            std::int32_t value = 0;
            if (game <= UINTPTR_MAX - kGameChallengeOffset &&
                ReadEngine(game + kGameChallengeOffset, &value)) {
                lua_pushinteger(state, static_cast<lua_Integer>(value));
                return 1;
            }
            lua_pushnil(state);
            return 1;
        }
        if (std::strcmp(field, "Difficulty") == 0) {
            std::int32_t value = 0;
            if (game <= UINTPTR_MAX - kGameDifficultyOffset &&
                ReadEngine(game + kGameDifficultyOffset, &value)) {
                lua_pushinteger(state, static_cast<lua_Integer>(value));
                return 1;
            }
            lua_pushnil(state);
            return 1;
        }
        if (std::strcmp(field, "TimeCounter") == 0) {
            // **有符号**读：控制台 `time` 命令用的是 `ldrsw`。
            // 写侧见 `remaining_api.cpp` 的 `TryWriteGameTimeCounter`（BUG-014，2026-10-26 补：
            //   此前这个字段只有 getter，`__newindex` 只记忽略 ⇒ TimeMachine 的计时补偿丢失）。
            std::int32_t value = 0;
            if (game <= UINTPTR_MAX - kGameTimeCounterOffset &&
                ReadEngine(game + kGameTimeCounterOffset, &value)) {
                lua_pushinteger(state, static_cast<lua_Integer>(value));
                return 1;
            }
            lua_pushnil(state);
            return 1;
        }
        if (std::strcmp(field, "ScreenShakeOffset") == 0) {
            float x = 0.0F;
            float y = 0.0F;
            if (game <= UINTPTR_MAX - kGameScreenShakeOffsetOffset &&
                ReadEngine(game + kGameScreenShakeOffsetOffset, &x) &&
                ReadEngine(game + kGameScreenShakeOffsetOffset + sizeof(float), &y)) {
                // 用 `Vector` userdata（不是一张只有 X/Y 的表）：PC 侧这个字段就是 `Vector`，
                // Mod 会继续对它调 `:Length()` 一类的方法。
                // 也顺便避开契约门禁那条"Game 家族不许自己写注册/建表循环"的字符串判据。
                isaac::runtime::PushLuaVector(state, x, y);
                return 1;
            }
            lua_pushnil(state);
            return 1;
        }
    }
    // 不是字段 ⇒ 落到方法表（上值 1）。方法表里没有就是 nil，与原来"`__index` 是表"的行为一致。
    lua_pushvalue(state, lua_upvalueindex(1));
    lua_pushvalue(state, 2);
    lua_rawget(state, -2);
    lua_remove(state, -2);
    return 1;
}

// `Game` 的引擎方法数据行（机制见 `engine_method_api.hpp`）。
constexpr EngineMethodRow kGameEngineRows[] = {
    // 0x000A `Game:ChangeRoom(int, int)`：`x0 = this(Game/Level)`、`w1 = 房间格`、`w2 = 维度`（-1 = 当前）。
    {0x0201000A, kGameChangeRoomOffset, kGameChangeRoomEntryWord, FieldReceipt::Level,
     EngineCallShape::Void2, 2, 0xFF},
    // 0x000B `Game:StartRoomTransition(int, Direction, RoomTransitionAnim, EntityPlayer, int)`
    //   —— GoodTrip 传送的**默认路径**（`scripts/trip.lua:207`）。5 个参数、第 4 个是玩家指针，
    //   所以这一行用的是的"任意签名"形状（描述符见 `isaac_api.cpp` 的 `kEngineCallShapes`）。
    //   PC 文档（`Game.md`）逐字为
    //   `void StartRoomTransition(int RoomIndex, Direction, RoomTransitionAnim Animation = WALK,
    //    EntityPlayer Player = nil, int Dimension = -1)`。
    {0x0201000B, kGameStartRoomTransitionOffset, kGameStartRoomTransitionEntryWord,
     FieldReceipt::Level, EngineCallShape::VoidIntIntIntHandleInt, 5, 0xFF},
    // ---- `Game:AddDevilRoomDeal`（void AddDevilRoomDeal ( )）
    // 符号 `_ZN15IsaacRepentance4Game16AddDevilRoomDealEv`；形状按符号参数表取（见 `runtime_constants.hpp` 的段）。
    {0x0201000E, kGameAddDevilRoomDealOffset, kGameAddDevilRoomDealEntryWord, FieldReceipt::Level,
     EngineCallShape::Void0, 0, 0xFF},
    // ---- `Game:Update`（void Update ( )）
    // 符号 `_ZN15IsaacRepentance4Game6UpdateEv`；形状按符号参数表取（见 `runtime_constants.hpp` 的段）。
    {0x0201000F, kGameUpdateOffset, kGameUpdateEntryWord, FieldReceipt::Level,
     EngineCallShape::Void0, 0, 0xFF},
    // ---- `Game:GetGreedBossWaveNum`（int GetGreedBossWaveNum ( )）
    // 接收者与同族既有的 `Game:ChangeRoom`/`Game:Update` 一致（`FieldReceipt::Level`：
    // 引擎里 `Level` 内嵌在 `Game` 起始处，所以同一条解析链）。
    {0x02010010, kGameGetGreedBossWaveNumOffset, kGameGetGreedBossWaveNumEntryWord,
     FieldReceipt::Level, EngineCallShape::Int0, 0, 0xFF},
    // ---- `Game:ShowHallucination`（void ShowHallucination (
    //   int FrameCount, BackdropType Backdrop = BackdropType.NUM_BACKDROPS )）
    // PC 契约 `Game.md:484`。那个缺省值不是 0（`NUM_BACKDROPS` 是枚举末值）
    // ⇒ 不能用"尾部可省"（省略时寄存器保持 0，而 0 不是那个缺省）⇒ 形状用 `Void2`、两个参数都必填；
    // 语料也传满 2 个（`BOIStageAPI15/.../roomgfx.lua:160` 的 `ShowHallucination(0, backdrop)`）。
    {0x02010011, kGameShowHallucinationOffset, kGameShowHallucinationEntryWord,
     FieldReceipt::Level, EngineCallShape::Void2, 2, 0xFF},
    // ---- `Game:CharmFart`
    //   （void CharmFart ( Vector Position, float Radius, Entity Source )），PC 契约 `Game.md:102`。
    // 第 1 个参数是 `Vector2 const&`（走指针，见 `EngineArgKind::Vector2Ref`）；
    //   第 3 个是**裸实体指针**（`PNS_6EntityE`）⇒ 用 `Handle` 种类。
    {0x02010012, kGameCharmFartOffset, kGameCharmFartEntryWord, FieldReceipt::Level,
     EngineCallShape::VoidVector2RefFloatHandle, 3, 0xFF},
    // ---- `Game:MoveToRandomRoom`
    //   （void MoveToRandomRoom ( boolean IAmErrorRoom, int Seed, EntityPlayer Player )），
    //   PC 契约 `Game.md:424`。接收者与同族一致（`FieldReceipt::Level`）。
    // 引擎符号 `_ZN15IsaacRepentance4Game16MoveToRandomRoomEbjPNS_13Entity_PlayerE`
    //   ⇒ `(bool, i32, Entity_Player*)`；第 3 个是**裸实体指针** ⇒ `Handle` 种类（`nil` = 空指针）。
    //   形状 `VoidBoolIntHandle`（本批新增；三种参数种类都已在表里，只差这一行组合）。
    //   语料传满 3 个（`BOIStageAPI15/.../callbacks.lua:142`）。
    {0x02010013, kGameMoveToRandomRoomOffset, kGameMoveToRandomRoomEntryWord,
     FieldReceipt::Level, EngineCallShape::VoidBoolIntHandle, 3, 0xFF},
};

// `Game` 族的字段读取型数据行（此前 `Game` 一条都没有 ——
// `AttachGameMethods` 的字段表参数一直是 `nullptr, 0`）。
// 家族的行表住在自己的 TU 里（与 `kLevelFieldApis` 在 `remaining_api.cpp`、
// `kFieldApis` 在 `isaac_api.cpp` 同一条规矩）。
// 接收者用 `FieldReceipt::Level` —— 枚举注释里本来就写着"`Game`/`Level`（引擎里 Level
// 内嵌在 Game 起始处，解析链同一条）"⇒ `Game` 与 `Level` 拿到的是同一个地址，
// 不需要新接收者。
constexpr FieldApiRow kGameFieldApis[] = {
    // `Game:GetStateFlag(int Flag)`（13 处 / 3 个模组）：读 `Game + 0x26FA50` 那个
    // **位数组**（每字节 8 个标志 ⇒ `offset2` = 1）的第 `Flag` 位。
    // 基址与位号的取证（两处互相独立的位点位）：`Level::IsBackwardsPath() @ 0x3E1DBC`
    //   读 `0x26FA56` 的 **bit 0**（`48 = STATE_BACKWARDS_PATH`）、
    //   `Level::CanSpawnDevilRoom() @ 0x3E79A0` 读 `0x26FA55` 的 **bit 7**
    //   （`47 = STATE_BACKWARDS_PATH_INIT`）；另有 `Level::Init @ 0x3E0F5C` 把
    //   「基址 `0x26FA50` + 字节 6」直接写出来。详见 `runtime_constants.hpp` 的段。
    // 降级档 `False`；越界标志号也走这一档（PC 那条绑定同样没有边界检查）。
    // 契约：`tools/pc_contract_docs/Game.md` 的 `GetStateFlag` 行。
    {0x02010015, kGameStateFlagsOffset, 1, FieldKind::BoolBitArrayOfArg, FieldMissing::False,
     FieldReceipt::Level, 0xFF},
    // ---- `Game:SetStateFlag(int Flag, boolean Value)`（1 处）----
    // **写侧**：按实参给的标志号去同一个位数组里读改写那一位（`BoolBitArrayOfWriteArg`）。
    // PC 侧对应绑定是 `0x55DC20`（对 `Game+0x1822C` 那个 32 位字数组做读改写）—— 与
    // `GetStateFlag` 的 `0x4E61D0` **同一格**；Switch 侧的基址/位号取证见
    // `runtime_constants.hpp` 的段（本批只加写的那一半）。
    // 契约：`tools/pc_contract_docs/Game.md` 的 `SetStateFlag` 行。
    {0x02010016, kGameStateFlagsOffset, 1, FieldKind::BoolBitArrayOfWriteArg,
     FieldMissing::False, FieldReceipt::Level, 0xFF},
    // ---- `Game:Darken(float Darkness, int Timeout)`（1 处 / 1 个模组）----
    // PC 契约 `tools/pc_contract_docs/Game.md:129`：`#### void Darken ( float Darkness, int Timeout )`。
    // PC 绑定本体（`0x432F60`，`__thiscall`）= 把两个标量形参各存进一个成员 ⇒ **写两格**。
    // 走新开的 `FieldKind::FloatThenIntFromArgs`：数值 → `offset`（float）、
    //   整数 → `offset2`（i32）。既有 kind 每一种都只动一格 ⇒ 覆盖不了「两实参写两格」。
    // Switch 侧那两格 = `Game + 0x24F9C0`（TargetDarkness，float）与 `Game + 0x24F9B8`
    //   （Timeout，int）—— 布局表 `tools/layout_tables/game.json` 的两行都是 `confirmed`。
    //   两格不相邻（中间夹着 `+0x24F9BC` 那个插值量）⇒ 必须两个独立偏移，
    //     绝不能用一条 `u64`/`u32` 掩盖（那会静默写坏中间那一格）。用例里有专门的反回归断言。
    // 证据（默认值成对写入 `Entity_NPC::ai_lamb`、每帧递减 `Game::Update`、渲染读
    //   `Room::GetLightingAlpha`）写在 `runtime_constants.hpp` 的段与布局表那两行的
    //   `evidence` 里（`--verify` 会重新反汇编逐条核对）。
    // 降级档写 `Zero` 只为满足行结构（本 kind 不返回值，`missing` 用不上）。
    {0x02010018, kGameTargetDarknessOffset, static_cast<std::uint32_t>(kGameDarknessTimeoutOffset),
     FieldKind::FloatThenIntFromArgs, FieldMissing::Zero, FieldReceipt::Level, 0xFF},
};

// `Darken` 那两格的偏移在两处各有一个具名常量 —— 本表用的住在
// `runtime_constants.hpp`（字段行的门禁只认那里），布局表生成的 `layout::kGame…Offset`
// 服务别处。同一个值写两遍迟早漂移 ⇒ 编译期钉死（与同一做法）。
static_assert(kGameTargetDarknessOffset == layout::kGameTargetDarknessOffset,
              "TargetDarkness 的偏移在 runtime_constants.hpp 与布局表生成物之间不一致");
static_assert(kGameDarknessTimeoutOffset == layout::kGameDarknessTimeoutOffset,
              "DarknessTimeout 的偏移在 runtime_constants.hpp 与布局表生成物之间不一致");

std::size_t AttachGameMethods(lua_State* state) noexcept {
    return AttachApi700Methods(state,"Game") + AttachApi600Methods(state,"Game") + AttachApi300Methods(state,"Game") + AttachApi200Methods(state,"Game") + AttachRPlusMethods(state,"Game") + AttachOwnerMethods(state, kGameOwner, kGameHandlers,
                              sizeof(kGameHandlers) / sizeof(kGameHandlers[0]),
                              kGameFieldApis, sizeof(kGameFieldApis) / sizeof(kGameFieldApis[0]),
                              kGameEngineRows, sizeof(kGameEngineRows) / sizeof(kGameEngineRows[0]));
}

// `Seeds` 的引擎方法数据行。
//
// 为什么此前 `Seeds` 家族一条引擎方法行都没有：那三条手写方法
// （`GetStageSeed` / `GetNextSeed` / `ForgetStageSeed`）之所以手写，注释里写得很清楚 ——
// 「`Seeds` 句柄不持引擎指针（接收者要 `Game + kGameSeedsObjectOffset` 现算
// ⇒ 先要有 `FieldReceipt::Seeds` 这一档）」。本批把那一档补上了
// （见 `field_api.hpp` 与 `isaac_api.cpp` 的 `ResolveFieldReceipt`），
// 于是 `Seeds:SetStartSeed` 可以落成 16 字节数据行（0 字节代码）。
// 既有的三条手写方法本批不动（改动最小）：它们各有自己的取证与语义
// （`GetNextSeed` 还要推进内嵌 RNG），重写成数据行是另一笔账。
//
// `Seeds:SetStartSeed(int)` —— PC 契约 `tools/pc_contract_docs/Seeds.md:170/172`
// （逐字 `#### void SetStartSeed ( string StartSeed )` + "Empty string means we will pick
// a new random seed."）。语料 `IsaacOnTwitchReloaded/scripts/events.lua:1433` 与 `:1465`
// 传的是 数字（`seeds:GetNextSeed()` 的返回值）⇒ 走引擎的数字重载
// `Seeds::SetStartSeed(unsigned int)` @ `0x4A1114`（字符串版只是"解析 + 尾调"它）。
// 形状复用现成的 `EngineCallShape::Void1`（`void(this, i32)`）—— 本批零新形状。
// 逐条证据（两个重载的 mangled 名、字符串版的尾调关系、数字版的分支）见
// `runtime_constants.hpp` 的段。
constexpr EngineMethodRow kSeedsEngineRows[] = {
    // 0x000A `SetStartSeed(int)`（id 取 Seed 域下一个空号；目录行见 `api_catalog.cpp`）。
    {0x0F01000A, kSeedsSetStartSeedOffset, kSeedsSetStartSeedEntryWord, FieldReceipt::Seeds,
     EngineCallShape::VoidSeed1, 1, 0xFF},
};

std::size_t AttachSeedsMethods(lua_State* state) noexcept {
    // 与 `AttachGameMethods` 同形 —— 手写绑定表与引擎方法数据行并存
    // （`AttachOwnerMethods` 先按手写绑定行匹配、匹配不到再按数据行挂，所以同一 owner
    //  里两者可以共存；`Seeds` 那三条手写方法继续走绑定表）。
    return AttachApi700Methods(state,"Seeds") + AttachApi300Methods(state,"Seeds") + AttachApi200Methods(state,"Seeds") + AttachOwnerMethods(state, kSeedsOwner, kSeedsHandlers,
                              sizeof(kSeedsHandlers) / sizeof(kSeedsHandlers[0]), nullptr, 0,
                              kSeedsEngineRows,
                              sizeof(kSeedsEngineRows) / sizeof(kSeedsEngineRows[0]));
}

// `HUD` 家族（`Game:GetHUD()` 的返回值）的方法表装配。
// 与 `AttachSeedsMethods` 同形：句柄无字段 ⇒ 元表建在 `lua_runtime.cpp` 的 `RegisterGameApi`
// 里，`__index` 直接就是这张表。
std::size_t AttachHudMethods(lua_State* state) noexcept {
    return AttachApi200Methods(state,"HUD") + AttachOwnerMethods(state, kHudOwner, kHudHandlers,
                              sizeof(kHudHandlers) / sizeof(kHudHandlers[0]));
}

std::uint32_t LastNumPlayersForProbe() noexcept {
    return g_LastNumPlayers.load(std::memory_order_relaxed);
}

std::uint32_t LastIsPausedForProbe() noexcept {
    return g_LastIsPaused.load(std::memory_order_relaxed);
}

} // namespace isaac::runtime
