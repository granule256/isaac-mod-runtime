#include <atomic>
#include "interfaces/lua/mod_api.hpp"
#include "interfaces/lua/callback_table_api.hpp"

#include "interfaces/lua/owner_binding.hpp"
#include "interfaces/lua/lua_integer_argument.hpp"

#include "application/callback/callback_registry.hpp"
#include "domain/callback/callback_descriptor.hpp"

#include "lua_runtime_state.hpp"
#include "mod_persistence.hpp"
#include "persistence_event_journal.hpp"

#include <cstddef>
#include <cstdint>

extern "C" {
#include <lauxlib.h>

// ============================================================================
// 批次 429：`Mod:SaveData` 的**归属探针**（只读；每调用一次记一笔）
// ============================================================================
// 为什么要有它：API 层归因量出 `Mod:SaveData` **每 5.06 秒一次、单次 10.2 ms 平均 / 44.3 ms 最长**
// （12/12 次都 ≥5 ms）⇒ 一个**周期性必发**的顿。而"是谁在存"**不能靠周期猜**：
// 我们自己的 `probe_logger.cpp:65` 就有个 `frame % 300`（5.00 秒）的心跳，差点被当成它
// （而且实测周期是 5.06 ≠ 5.00）。按项目纪律：**归属问题必须按对象记，只记总数是错的。**
//
// 记录什么：`ModHandle` 里本来就同时带着两样 —— `ownerPacked`（低 16 位 = 模组下标 ⇒ **谁**）
// 与 `persistenceNamespace`（那一家自己的命名空间号）。⇒ 直接按**模组下标**做一张表，O(1) 落账。
// ★ 不引入任何新 include、不读时钟：读数脚本采两次求差即可（与现有量具同一口径）。
//
// ★★ 定义在文件作用域、**不在匿名命名空间里**（匿名命名空间 = 内部链接 ⇒ 符号表里查不到 ⇒
//     `mem.*` 读数工具永远看不到它，而代码看着完全正常）。本项目第 5 次重申这条（196/203/209/211/214 → 本批）。
constexpr std::size_t kModSaveProbeOwnerSlots = 32;   // 与 `ownerPacked` 的低 16 位下标空间无关，够用即可

std::uint64_t g_ModSaveProbeCallsByOwner[kModSaveProbeOwnerSlots] = {};
std::uint64_t g_ModSaveProbeNamespaceByOwner[kModSaveProbeOwnerSlots] = {};
std::uint64_t g_ModSaveProbeTotalCalls = 0;
std::uint64_t g_ModSaveProbeLastOwner = 0;
}

namespace isaac::runtime {
namespace {

using LuaRuntime::CallbackOperation;
using LuaRuntime::IsStage13CallbackMode;
using LuaRuntime::kModMetatable;
using LuaRuntime::kStage13CallbackValue;
using LuaRuntime::ModHandle;
using LuaRuntime::RecordCallbackOperation;

int ModAddCallback(lua_State* state);
int ModRemoveCallback(lua_State* state);
int ModAddPriorityCallback(lua_State* state);
int ModHasData(lua_State* state);
int ModRemoveData(lua_State* state);

constexpr LuaHandlerBinding kModHandlers[] = {
    {0x01010001, &ModAddCallback},
    // 0x0002：`Mod:RemoveCallback`（2026-09-18）。Mod 域此前只有 AddCallback 一条，0x0002 空着
    // （取号前扫过整个域，见 `api_catalog.cpp` 那一行的注释）。
    {0x01010002, &ModRemoveCallback},
    // 批次 045：`Mod:AddPriorityCallback`（GoodTrip 用；id 取域内下一个空号 0x0003）。
    {0x01010003, &ModAddPriorityCallback},
    {0x08010001, &ModSaveData},
    {0x08010002, &ModLoadData},
    {0x08010003, &ModHasData},
    {0x08010004, &ModRemoveData},
};

constexpr char kModOwner[] = "Mod";

// ============================================================================
// 批次 216（2026-09-30）：Mod 对象的**两种形态**都要认
// ============================================================================
//
// 背景：我们的 `RegisterMod` 以前返回 **userdata**，而 PC 返回 **table**
// （`GlobalFunctions.md:101`「Returns a table which acts the Mod Reference」）——
// 中文版 MCM 的 `customcallbacks.lua:161` 有一句 `if type(mod) ~= "table" then error(...) end`
// ⇒ 加载期脚本失败 ⇒ 它的回调一条都没登记 ⇒ **菜单打不开**（真机读数 2026-09-30 傍晚）。
//
// 现在对外给出去的是 table（`T.Name` = 模组名、方法从共享原型经 `__index` 找、模组可以往自己身上写
// 字段），内部那个 `ModHandle` userdata **藏在每个 Mod 对象自己的元表的 `__handle` 里**。
//
// 这个解析器**两种形态都认**：table（PC 形态，现在也是我们的形态）与 userdata（旧形态 ——
// 运行时自己那份宿主对象、以及宿主门禁夹具造的老对象还在用）。找不到就返回 `nullptr`，
// 由调用方决定报什么错（**不许**静默当成"某个 Mod"—— 归属错会让回调混成一家）。

LuaRuntime::ModHandle* ModHandleFromObject(lua_State* state, int index) noexcept {
    if (lua_istable(state, index)) {
        if (lua_getmetatable(state, index) == 0) {
            return nullptr;
        }
        lua_getfield(state, -1, "__handle");
        auto* handle = static_cast<LuaRuntime::ModHandle*>(
            luaL_testudata(state, -1, LuaRuntime::kModMetatable));
        lua_pop(state, 2);
        return handle;
    }
    return static_cast<LuaRuntime::ModHandle*>(
        luaL_testudata(state, index, LuaRuntime::kModMetatable));
}

//: 取不到就**报错**（不是返回 nil 继续跑）——`self` 认不出来时，任何"归属"判断都是错的。
LuaRuntime::ModHandle* RequireModObject(lua_State* state, int index, const char* apiName) {
    LuaRuntime::ModHandle* handle = ModHandleFromObject(state, index);
    if (handle == nullptr) {
        luaL_error(state, "%s expects a Mod object (the value returned by RegisterMod)", apiName);
    }
    return handle;
}

ModHandle* CheckModHandle(lua_State* state, int expectedArguments, const char* apiName) {
    if (lua_gettop(state) != expectedArguments) {
        luaL_error(state, "%s received an invalid argument count", apiName);
    }
    return RequireModObject(state, 1, apiName);
}

const char* PersistenceErrorMessage(ModPersistence::Result result) {
    switch (result) {
        case ModPersistence::Result::Unavailable:
            return "Mod persistent storage is unavailable";
        case ModPersistence::Result::Corrupt:
            return "Mod persistent storage is corrupt";
        case ModPersistence::Result::TooLarge:
            return "Mod persistent storage is full";
        case ModPersistence::Result::IoFailure:
            return "Mod persistent storage I/O failed";
        case ModPersistence::Result::Success:
        case ModPersistence::Result::Missing:
            return "Mod persistent storage failed";
    }
    return "Mod persistent storage failed";
}

// Maps a Lua `ModCallbacks` value onto the catalog's stable callback id. The
// Stage13 manifest/require diagnostic only allows its own POST_UPDATE phase.
//
// 非 Stage13 构建里，**PC 表里的每一种回调都允许登记**：我们只有少数几种挂了
// 派发点（见 `HasDispatchSite`），其余的登记下来但永不触发。这样做是刻意的——
// PC Mod 会在加载阶段一次性注册十几种回调，任何一种报错都会让整个 Mod 加载失败
// （EID 就是这种），而“注册成功但收不到事件”只会让功能静默缺失。哪些种类挂了
// 派发点、哪些只是登记，由 `IsaacModRuntime_GetHookDiagnostics` 报出去。
//
// ★ 这张名单**必须与代码里真实的派发调用逐项一致**（2026-09-15 更正）：
//   * 走 `CallbackDispatcher` 的 —— `lua_runtime.cpp` 里的
//     `Dispatch(kCallbackPostGameStarted / kCallbackPostUpdate / kCallbackPostRender, …)`，
//     以及 2026-09-18 接上的每帧事件五条（`kCallbackPostNewRoom` / `kCallbackPostNewLevel` /
//     `kCallbackPostPickupInit` / `kCallbackPostPickupUpdate` / `kCallbackPostPlayerInit`，
//     见 `DispatchFrameEvents`）；
//   * 手工那一条 —— `DispatchPreGetCollectible()` 用
//     `g_CallbackRegistry.At(kCallbackPreGetCollectible, 0)` 取登记。
// 以前这里多写了 `kCallbackInputAction`（13）：全仓**没有任何地方**派发它，
// 于是设备侧那份状态面会告诉操作者"这种回调有派发点"，而它一次都不会跑，
// 每次读数里"有派发点 / 无派发点"这两个数都因此偏一项。
// `runtime/tests/test_lua_callback_dispatch_sites.py` 现在按源码做一致性门禁：
// 名单里多一项或漏一项都会红。
bool HasDispatchSite(CallbackId id) {
    return id == kCallbackGetShaderParams || id == kCallbackGetCard || id == kCallbackInputAction ||  // 批次 390（2026-10-07）：三条 ManagerBase 查询中继
           id == kCallbackPostUpdate || id == kCallbackPostRender ||
           id == kCallbackPreGetCollectible || id == kCallbackPostGameStarted ||
           id == kCallbackPostNewRoom || id == kCallbackPostNewLevel ||
           id == kCallbackPostPickupInit || id == kCallbackPostPickupUpdate ||
           id == kCallbackPostPlayerInit ||
           // --- 实体族（2026-09-18 批次 010）：更新/渲染/刚出现三种时机，按实体类型分派 ---
           id == kCallbackNpcUpdate || id == kCallbackPostPeffectUpdate ||
           id == kCallbackFamiliarUpdate || id == kCallbackFamiliarInit ||
           id == kCallbackPostFamiliarRender || id == kCallbackPostNpcInit ||
           id == kCallbackPostPlayerUpdate || id == kCallbackPostPlayerRender ||
           id == kCallbackPostPickupRender || id == kCallbackPostTearInit ||
           id == kCallbackPostTearUpdate || id == kCallbackPostTearRender ||
           id == kCallbackPostProjectileInit || id == kCallbackPostProjectileUpdate ||
           id == kCallbackPostProjectileRender || id == kCallbackPostLaserInit ||
           id == kCallbackPostLaserUpdate || id == kCallbackPostLaserRender ||
           id == kCallbackPostKnifeInit || id == kCallbackPostKnifeUpdate ||
           id == kCallbackPostKnifeRender || id == kCallbackPostEffectInit ||
           id == kCallbackPostEffectUpdate || id == kCallbackPostEffectRender ||
           id == kCallbackPostBombInit || id == kCallbackPostBombUpdate ||
           id == kCallbackPostBombRender ||
           // --- 2026-09-20 批次 102：EID / GoodTrip 在等的那几个事件（入口中继）---
           // 前四条走中继回调里的 `DispatchFiltered` / `DispatchModifying`，
           // `kCallbackPreGetCollectible` 旁边那条（`kCallbackPostGetCollectible`）走的是
           // **已有的**取道具中继、在原函数返回之后派发。
           id == kCallbackPreGameExit || id == kCallbackUseItem || id == kCallbackUseCard ||
           id == kCallbackUsePill || id == kCallbackPreUseItem ||
           id == kCallbackPostGetCollectible ||
           // 批次 103（第 2 期）：掉落物碰撞（中继回调里 `DispatchModifying`，过滤值是掉落物变体）。
           id == kCallbackPrePickupCollision ||
           // 批次 104（第 2 期）：房间生成实体（中继回调里 `Dispatch`，只通知）。
           id == kCallbackPreRoomEntitySpawn ||
           // 2026-10-07 批次 396：补全回调（第 1 批）——
           //   `MC_ENTITY_TAKE_DMG` 走 `DispatchEntityTakeDamage`（中继里 `DispatchModifying`，
           //   过滤值 = 实体的 `EntityType`，"返回 false ⇒ 取消这次伤害"）；
           //   `MC_EVALUATE_CACHE` 走 `DispatchEvaluateCache`（中继里 `DispatchFiltered`，
           //   过滤值 = 本次要重算的那个 CacheFlag 位）。
           id == kCallbackEntityTakeDmg ||
           id == kCallbackEvaluateCache ||
           // 2026-10-07 批次 397：补全回调（第 2 批）—— 三条 hookable 改走入口中继。
           //   `MC_POST_ENTITY_KILL` / `MC_POST_NPC_DEATH` 走 `DispatchFiltered`（过滤值 = EntityType）；
           //   `MC_POST_GAME_END` 走 `Dispatch`（无过滤），实参是 bool。
           id == kCallbackPostEntityKill ||
           id == kCallbackPostNpcDeath ||
           id == kCallbackPostGameEnd ||
           // `MC_POST_FIRE_TEAR`：派发点在 `Entity_Player::FireTear` **原函数返回之后**
           // （实参 = 返回的泪弹指针），无过滤。
           id == kCallbackPostFireTear || id == kCallbackPostNpcRender ||
           id == kCallbackPreFamiliarCollision ||
           id == kCallbackPreNpcCollision ||
           id == kCallbackPrePlayerCollision ||
           id == kCallbackPreTearCollision ||
           id == kCallbackPreProjectileCollision ||
           id == kCallbackPreKnifeCollision ||
           id == kCallbackPreBombCollision || id == kCallbackGetPillColor ||
           id == kCallbackGetPillEffect || id == kCallbackGetTrinket || id == kCallbackPostEntityRemove || id == kCallbackPostCurseEval || id == kCallbackPostPickupSelection || id == kCallbackPreSpawnCleanAward || id == kCallbackPreEntityDevolve || id == kCallbackPreNpcUpdate || id == kCallbackPreEntitySpawn || id == kCallbackPreModUnload || id == kCallbackExecuteCmd;
}

bool ResolveCallbackId(lua_Integer callback, CallbackId* id) {
    if (IsStage13CallbackMode()) {
        if (callback != kStage13CallbackValue) {
            return false;
        }
        *id = kCallbackPostUpdate;
        return true;
    }
    if (callback < 0 || callback > static_cast<lua_Integer>(kCallbackMaximumId)) {
        return false;
    }
    // PC 表里的值直接作为内部 id：这样 Lua 侧的枚举值与注册表 id 一一对应，
    // 诊断报出来的掩码就是 Mod 注册过的枚举值本身。
    *id = static_cast<CallbackId>(callback);
    return true;
}

//: 登记一条回调的**共用实现**（`Mod:AddCallback` 与 `Mod:AddPriorityCallback` 都走它）。
//:
//: 进入时栈上必须是 `(self, id, fn[, filter])` —— 优先级由 `ModAddPriorityCallback` 先摘掉、
//: 再作为实参传进来。这样拆的好处是**两条登记路径的其余行为一字不差**（校验、命名回调、
//: 过滤参数、追加语义、普查计数都在这一份里），差别只有"优先级"这一处 ——
//: 而"两处各写一遍"正是本项目栽过的坑（`SKIP_HOOK_*` 那次）。
[[maybe_unused]] int RegisterCallbackFromStack(lua_State* state, CallbackPriorityValue priority) {
    // PC 版签名是 `Mod:AddCallback(kind, function[, entityId])`（`ModReference.md:17`：
    // `void AddCallback(ModCallbacks callbackId, function callbackFn, int entityId)`）。
    //
    // 第三个实参是**过滤器**：官方文档里叫 `entityId`，取值类型随回调而异
    // （`CollectibleType` / `Card` / `PillEffect` / `PickupVariant`…），语义是"这条登记只在
    // 过滤值相等时被派发"。EID 重度依赖它 —— 它把 `MC_PRE_USE_ITEM` 登记了 6 条各自带
    // CollectibleType 过滤器的处理函数（Smelter / Void / Flip / D4 / Genesis / Lemegeton）；
    // 不筛的话 `EID.OnUseSmelter` 会在**每一次**主动道具使用时都跑一遍。
    //
    // 2026-09-20（批次 101）之前这里是"接受但忽略"（那时这些种类还没有派发点，忽略的后果
    // 只是"以后接上时要记得补"）。现在过滤值真的存进登记表并与登记项平行（见
    // `CallbackRegistry::kNoCallbackFilter`），派发侧按它筛。
    const int argumentCount = lua_gettop(state);
    if (argumentCount != 3 && argumentCount != 4) {
        return luaL_error(state, "unsupported callback id for this Runtime phase");
    }
    luaL_checktype(state, 3, LUA_TFUNCTION);
    // **字符串回调名**（PC 忏悔版的自定义回调）：只登记进命名回调表，不抛错。
    // EID 在加载阶段就会走这一条（`features/eid_bagofcrafting_search.lua:58`），
    // 报错会让 `require("features.eid_bagofcrafting")` 失败并把整个 `main.lua` 打断。
    // 名字不参与数字派发、也不进回调普查掩码（掩码是 `ModCallbacks` 枚举的位图）。
    if (lua_type(state, 2) == LUA_TSTRING) {
        // 顺序：先压回调函数、再压 Mod 对象 —— `RegisterNamedCallback` 的约定。
        lua_pushvalue(state, 3);
        lua_pushvalue(state, 1);
        // 批次 268：第 4 个实参（PC 的 `entityId`）对字符串回调名就是**过滤值**，
        // 由 `Isaac.RunCallbackWithParam` 在派发时比对。传 0 = 这一条没给过滤值。
        // ★ 这里**不做整数校验**（与下面数字路径不同）：过滤值的类型在 PC 侧不限定
        //   （`__matchParams` 用的是 Lua 的 `==`），而且旧行为是"完全忽略它"——
        //   在这里改成"非整数就报错"会让**已经在跑的模组**（字符串回调名 + 非整数第三参）
        //   从"静默忽略"变成"加载失败"，是比现状更坏的退化。
        const int filterIndex = argumentCount == 4 ? 4 : 0;
        if (!RegisterNamedCallback(state, lua_tostring(state, 2), filterIndex, priority)) {
            return luaL_error(state, "named callback registration failed");
        }
        return 0;
    }
    const lua_Integer callback = luaL_checkinteger(state, 2);
    CallbackId id = 0;
    if (!ResolveCallbackId(callback, &id)) {
        return luaL_error(state, "unsupported callback id for this Runtime phase");
    }
    // 过滤器（可选第三个实参）：`nil` / 缺省 = 不带过滤器。
    //
    // 数值判定用 `IsIntegerArgument`（接受 `5.0` 这类"整数值的浮点"）而不是 `luaL_checkinteger`：
    // 与 09-13 修 `Room:GetGridPath(5.0)` 那次同一个理由 —— 模组把枚举值当浮点传是常态，
    // 在这里严格拒绝会让**整条 `Mod:AddCallback` 报错**，而它通常写在模组入口脚本里
    // ⇒ 一个参数写法把整个模组打成"加载失败"。真给一个非整数（例如 `0.5`）时仍然报错：
    // 那种值不可能是 PC 的 `int entityId`，静默取整会让登记的过滤值不是模组想要的。
    std::int64_t filter = CallbackRegistry::kNoCallbackFilter;
    if (argumentCount == 4 && lua_type(state, 4) != LUA_TNIL) {
        lua_Integer value = 0;
        if (!isaac::runtime::IntegerArgumentAt(state, 4, &value)) {
            return luaL_error(state,
                              "Mod:AddCallback expects an integer filter value as its third argument");
        }
        filter = static_cast<std::int64_t>(value);
    }
    lua_pushvalue(state, 3);
    const int functionRef = luaL_ref(state, LUA_REGISTRYINDEX);
    lua_pushvalue(state, 1);
    const int modRef = luaL_ref(state, LUA_REGISTRYINDEX);
    // **追加**登记，而不是"替换同一 id 的旧登记"。
    //
    // PC 语义是后者做不到的：同一 Mod 对同一 id 可以登记多个回调，派发时**按登记顺序全部调用**。
    // EID 就重度依赖这一点 —— 它一次登记 **5 个 `MC_POST_NEW_ROOM`**（`main.lua:848/865`、
    // `eid_bagofcrafting.lua:467` …）、**10 个 `MC_PRE_USE_ITEM`**（`main.lua:381/403/1768/1782/1795/1804`、
    // `eid_itemprediction.lua:60/69`、`eid_bagofcrafting.lua:504`）。
    // 2026-09-12 真机报告 `01789203482` 里"注册表只有 7 条"正是替换语义造成的：
    // 7 = 种类的个数，而不是登记的个数。
    //
    // 旧实现先 `Remove(id, owner)` 再登记，注释写的是"避免 Lua 引用泄漏" —— 泄漏确实要防，
    // 但正确的做法是**追加**（引用各自归各自的登记），而不是把 Mod 的回调吃掉。
    CallbackRegistry& registry = LuaRuntime::ManagedCallbackRegistry();
    // 归属 = **登记这个回调的那个 Mod**（多模组，2026-09-16）。
    //
    // 此前所有回调都挂同一个常量 owner（`kRuntimeOwner{1,1}`），前提是"只加载一个 Mod"。
    // 多模组之后那样会把两个 Mod 的回调混成一家：`Find`/`Remove`/`RemoveOwner` 全部按 owner
    // 区分，混成一家之后"摘掉某个 Mod 的回调"会连别人的一起摘掉。
    // owner 就存在 Mod userdata 里（`ModHandle::ownerPacked`，见 `lua_runtime.cpp` 的
    // `RegisterMod`），而 `self`（栈下标 1）正是这个 Mod 对象。
    const auto* modHandle = RequireModObject(state, 1, "Mod:AddCallback");
    const isaac::runtime::ModHandle owner = LuaRuntime::UnpackModOwner(modHandle->ownerPacked);
    CallbackDescriptor descriptor{};
    descriptor.id = id;
    descriptor.owner = owner;
    descriptor.affinity = isaac::runtime::ThreadAffinity::Any;
    descriptor.luaReference = functionRef;
    descriptor.modReference = modRef;
    if (!registry.Register(descriptor, filter, priority).ok()) {
        luaL_unref(state, LUA_REGISTRYINDEX, functionRef);
        luaL_unref(state, LUA_REGISTRYINDEX, modRef);
        // 容量耗尽：把可判据的原因说清楚（`CallbackRegistry::kCapacity` 是全 Mod 共享的上限）。
        return luaL_error(state, "callback registry is full (%d entries)",
                          static_cast<int>(CallbackRegistry::kCapacity));
    }
    LuaRuntime::RecordCallbackRegistration(id, HasDispatchSite(id));
    return 0;
}

// PC 的 `Mod:RemoveCallback(callbackId, callbackFn)`（`ModReference.md:58`，返回 void）。
//
// ★ **必须按"函数身份"摘，不能按 id 摘**。同一 Mod 对同一 id 可以登记多个回调
// （见 `ModAddCallback` 的注释：EID 一家就登记 5 个 `MC_POST_NEW_ROOM`、10 个 `MC_PRE_USE_ITEM`），
// 而它注销时用的是 `EID:RemoveCallback(ModCallbacks.MC_POST_NEW_ROOM, EID.BoCOnNewRoom)`
// （`features/eid_repentogon.lua:168`，另有 `MC_POST_RENDER` / `MC_PRE_USE_ITEM` 两处）——
// **只摘那一个函数**，同 id 上其余的必须留着。按 id 摘会把其余几条一起摘掉，
// 症状正是本项目最难查的一类：不报错、不崩，那几块功能静默失效。
//
// 身份用 `lua_rawequal` 比：Lua 里同一个闭包的不同引用相等，而"代码完全相同的另一个闭包"
// 不相等 —— 与 PC 一致（它比的是闭包对象本身）。所以调用方必须传**当初登记的那个函数值**
// （EID 传的是 `EID.OnRender` 这类表里的同一份引用，成立）。
int ModRemoveCallback(lua_State* state) {
    return CallCallbackTableApi(state, "RemoveCallback");
}

// PC：`Mod:AddPriorityCallback(callbackId, CallbackPriority, fn)` —— 与 `AddCallback` 同路，
// 差别只是"同一 id 内的执行顺序"（GoodTrip 的 `main.lua:84` 起就用它）。
//
// ★ 2026-09-20（批次 105）：**优先级已经真的参与排序**了（此前是"只校验、暂不排序"，见
// `docs/改动日志-20260920.md` 的 105 与 `mod_api.cpp` 的历史注释）。做法与过滤器同一套：
// `CallbackRegistry` 里加一张**与登记项平行的优先级数组**（不往 `CallbackDescriptor` 加字段
// —— 那会改"20 字节/项"的布局，读数工具与离线解码都得跟着改），派发时按它**升序稳定排序**：
//   * 升序 = PC 语义（`CallbackPriority.EARLY = -100` 比 `DEFAULT = 0` **先**执行）；
//   * 稳定 = 同优先级之间保持**登记顺序**（PC 也是这个观感，而且是我们此前的行为）。
// 为什么值得做：GoodTrip 的**每一个**回调都用 `AddPriorityCallback(…, EARLY, …)` 登记
// （`main.lua:84-104`），而它的绘制要压在其他 HUD 之前 —— 优先级不生效等于"它以为自己在最前，
// 实际排在最后"。
int ModAddCallback(lua_State* state) {
    return CallCallbackTableApi(state, "AddCallback");
}

int ModAddPriorityCallback(lua_State* state) {
    return CallCallbackTableApi(state, "AddPriorityCallback");
}

int ModHasData(lua_State* state) {
    ModHandle* mod = CheckModHandle(state, 1, "Mod:HasData");
    RecordCallbackOperation(CallbackOperation::HasData);
    PersistenceEventJournal::MarkAndFlush(
        PersistenceEventJournal::Event::OperationEntered,
        PersistenceEventJournal::Operation::HasData);
    bool has = false;
    const ModPersistence::Result result = ModPersistence::HasModData(mod->persistenceNamespace, &has);
    PersistenceEventJournal::MarkAndFlush(
        PersistenceEventJournal::Event::OperationReturned,
        PersistenceEventJournal::Operation::HasData,
        static_cast<std::uint32_t>(result));
    if (result != ModPersistence::Result::Success) {
        return luaL_error(state, "%s", PersistenceErrorMessage(result));
    }
    lua_pushboolean(state, has ? 1 : 0);
    return 1;
}

int ModRemoveData(lua_State* state) {
    ModHandle* mod = CheckModHandle(state, 1, "Mod:RemoveData");
    RecordCallbackOperation(CallbackOperation::RemoveData);
    PersistenceEventJournal::MarkAndFlush(
        PersistenceEventJournal::Event::OperationEntered,
        PersistenceEventJournal::Operation::RemoveData);
    const ModPersistence::Result result = ModPersistence::RemoveModData(mod->persistenceNamespace);
    PersistenceEventJournal::MarkAndFlush(
        PersistenceEventJournal::Event::OperationReturned,
        PersistenceEventJournal::Operation::RemoveData,
        static_cast<std::uint32_t>(result));
    if (result != ModPersistence::Result::Success) {
        return luaL_error(state, "%s", PersistenceErrorMessage(result));
    }
    return 0;
}

} // namespace

// 这两个实现被 `mod_api.hpp` 导出（`Isaac.SaveModData`/`Isaac.LoadModData` 转调它们），
// 所以必须留在**匿名命名空间之外**；名字因此写全限定（`using LuaRuntime::...` 只在
// 上面那个匿名命名空间里生效）。
int ModSaveData(lua_State* state) {
    LuaRuntime::ModHandle* mod = CheckModHandle(state, 2, "Mod:SaveData");
    std::size_t length = 0;
    const char* data = luaL_checklstring(state, 2, &length);
    // 批次 429：按模组下标落一笔（谁在存）—— 见文件顶部那段注释。
    {
        const std::uint32_t probeOwner = static_cast<std::uint32_t>(mod->ownerPacked & 0xFFFFU);
        if (probeOwner < kModSaveProbeOwnerSlots) {
            ++g_ModSaveProbeCallsByOwner[probeOwner];
            g_ModSaveProbeNamespaceByOwner[probeOwner] = mod->persistenceNamespace;
        }
        ++g_ModSaveProbeTotalCalls;
        g_ModSaveProbeLastOwner = probeOwner;
    }
    LuaRuntime::RecordCallbackOperation(LuaRuntime::CallbackOperation::SaveData);
    PersistenceEventJournal::MarkAndFlush(
        PersistenceEventJournal::Event::OperationEntered,
        PersistenceEventJournal::Operation::SaveData);
    const ModPersistence::Result result =
        ModPersistence::SaveModData(mod->persistenceNamespace, data, length);
    PersistenceEventJournal::MarkAndFlush(
        PersistenceEventJournal::Event::OperationReturned,
        PersistenceEventJournal::Operation::SaveData,
        static_cast<std::uint32_t>(result));
    if (result != ModPersistence::Result::Success) {
        return luaL_error(state, "%s", PersistenceErrorMessage(result));
    }
    return 0;
}

int ModLoadData(lua_State* state) {
    LuaRuntime::ModHandle* mod = CheckModHandle(state, 1, "Mod:LoadData");
    LuaRuntime::RecordCallbackOperation(LuaRuntime::CallbackOperation::LoadData);
    PersistenceEventJournal::MarkAndFlush(
        PersistenceEventJournal::Event::OperationEntered,
        PersistenceEventJournal::Operation::LoadData);
    const char* data = nullptr;
    std::size_t length = 0;
    const ModPersistence::Result result =
        ModPersistence::LoadModData(mod->persistenceNamespace, &data, &length);
    PersistenceEventJournal::MarkAndFlush(
        PersistenceEventJournal::Event::OperationReturned,
        PersistenceEventJournal::Operation::LoadData,
        static_cast<std::uint32_t>(result));
    if (result == ModPersistence::Result::Missing) {
        lua_pushliteral(state, "");
        return 1;
    }
    if (result != ModPersistence::Result::Success) {
        return luaL_error(state, "%s", PersistenceErrorMessage(result));
    }
    lua_pushlstring(state, data, length);
    return 1;
}

// `Isaac.HasModData(modRef)`（批次 261）：**直接转调** `Mod:HasData` —— 契约上两者是同一件事
// （都在问这个模组有没有存过 saveX.dat），判定只能有一份（`ModPersistence::HasModData`，
// 作业单第三节第 7 条）。栈形状也一样（Mod 对象在 1）⇒ 不需要任何适配。
int IsaacHasModData(lua_State* state) {
    return ModHasData(state);
}

std::size_t AttachModMethods(lua_State* state) noexcept {
    return AttachOwnerMethods(state, kModOwner, kModHandlers,
                              sizeof(kModHandlers) / sizeof(kModHandlers[0]));
}
void RecordCallbackTableRegistration(std::uint32_t id) noexcept {
    LuaRuntime::RecordCallbackRegistration(id,HasDispatchSite(id));
}

// --- 命名回调（字符串回调名）------------------------------------------------
//
// 实现说明（栈纪律）：所有条目都放在 Lua registry 的一张表里，调用方只需要按
// `[[nodiscard]]`/`void`/`int` 的约定使用，函数自己把栈恢复到调用前的形状。
// 注意：这一段必须留在 `isaac::runtime` 里（不是 `isaac::runtime::LuaRuntime`）——
// `mod_api.hpp` 在 `isaac::runtime` 里声明它们，限定命名空间会让定义落到另一个符号上，
// 链接期表现为未定义符号（本文件末尾的回调普查段有同样的说明）。
namespace {

// Lua registry 里那张"名字 → 回调表"的表的键。用**字符串键**（而不是 `luaL_ref` 的整数引用）
// 是因为每个 Lua 状态各有一份 registry：`lua_close` 之后引用自然失效，
// 不需要（也不可能）跨状态维护一个静态引用。
constexpr char kNamedCallbacksRegistryKey[] = "IsaacRuntime.NamedCallbacks";

// 把命名回调表压到栈顶（不存在时创建并写回 registry）。失败（栈溢出等）返回 false
// 且不留下值——调用方据此报 "named callback registration failed"。
bool PushNamedCallbacksTable(lua_State* state) {
    lua_getfield(state, LUA_REGISTRYINDEX, kNamedCallbacksRegistryKey);
    if (lua_istable(state, -1)) {
        return true;
    }
    lua_pop(state, 1);
    lua_newtable(state);                            // [.. named]
    lua_pushstring(state, kNamedCallbacksRegistryKey);
    lua_pushvalue(state, -2);                       // [.. named key named]
    lua_rawset(state, LUA_REGISTRYINDEX);           // registry[键] = named（弹出键与值）
    return true;
}

} // namespace

bool RegisterNamedCallback(lua_State* state, const char* name, int filterIndex,
                           CallbackPriorityValue priority) {
    if (state == nullptr || name == nullptr || name[0] == '\0') {
        return false;
    }
    // 约定：栈顶是 `Mod`，紧邻它下面的是回调函数（`Mod:AddCallback` 的压栈顺序）。
    const int modIndex = lua_gettop(state);
    const int functionIndex = modIndex - 1;
    if (functionIndex < 1 || !lua_isfunction(state, functionIndex)) {
        return false;
    }

    if (!PushNamedCallbacksTable(state)) {          // [.. named]
        return false;
    }
    const int namedIndex = lua_gettop(state);
    lua_getfield(state, namedIndex, name);          // [.. named list?]
    if (!lua_istable(state, -1)) {
        lua_pop(state, 1);
        lua_newtable(state);                        // [.. named list]
        const int freshListIndex = lua_gettop(state);
        lua_pushstring(state, name);
        lua_pushvalue(state, freshListIndex);
        // 用 `lua_rawset` 而不是"按名字写字段"的封装：家族 TU 里出现按名字写字段的形态
        // 会被契约测试当成"自己再写一遍注册循环"拦下来，而这里写的是我们自己的 registry
        // 表、不是元表注册。`lua_rawset` 的栈约定是"**值在栈顶、键在它下面**"，
        // 所以每一处都是先压键、再压值。
        lua_rawset(state, namedIndex);              // named[name] = list
    }
    const int listIndex = lua_gettop(state);

    // 条目形状与 PC 的 `Isaac.GetCallbacks` 返回的回调表一致：`{ Function = fn, Mod = mod }`。
    //
    // 再一次提醒：`lua_rawset` 取"栈顶 = 值、其下 = 键"，所以要**先压键、再压值**。
    lua_newtable(state);                            // [.. named list entry]
    const int entryIndex = lua_gettop(state);
    lua_pushstring(state, "Function");
    lua_pushvalue(state, functionIndex);
    lua_rawset(state, entryIndex);                  // entry.Function = fn
    lua_pushstring(state, "Mod");
    lua_pushvalue(state, modIndex);
    lua_rawset(state, entryIndex);                  // entry.Mod = mod
    // 批次 268：可选的过滤值（`Mod:AddCallback(名字, fn, entityId)` 的第三个实参）。
    // 字段名用 PC 回调表那一栏的名字；`filterIndex == 0` 或那一格是 `nil` 时写进 `nil`
    // —— 在 Lua 里等价于"没有这一栏"，所以 `Isaac.GetCallbacks` 的返回形状对旧调用方不变。
    if (filterIndex > 0 && !lua_isnoneornil(state, filterIndex)) {
        lua_pushstring(state, "OptionalArg");
        lua_pushvalue(state, filterIndex);
        lua_rawset(state, entryIndex);              // entry.OptionalArg = <值>
    }
    lua_pushstring(state, "Priority");
    if (priority.isInteger) lua_pushinteger(state, static_cast<lua_Integer>(priority.integer));
    else lua_pushnumber(state, priority.number);
    lua_rawset(state, entryIndex);
    // 逐字遵守PC的倒向插入比较；NaN时<=为false，不能改成>。
    lua_Integer position = static_cast<lua_Integer>(lua_rawlen(state, listIndex)) + 1;
    for (lua_Integer index = position - 1; index > 0; --index) {
        lua_rawgeti(state, listIndex, index);
        lua_getfield(state, -1, "Priority");
        if (priority.isInteger) lua_pushinteger(state, static_cast<lua_Integer>(priority.integer));
        else lua_pushnumber(state, priority.number);
        const bool before = lua_compare(state, -2, -1, LUA_OPLE) != 0;
        lua_pop(state, 2);
        if (before) {
            lua_pop(state, 1);
            break;
        }
        lua_rawseti(state, listIndex, index + 1);
        --position;
    }
    lua_rawseti(state, listIndex, position);
    // 把调用方压进来的两个值（fn、mod）也消费掉，恢复调用前的栈。
    lua_settop(state, functionIndex - 1);
    return true;
}

void PushNamedCallbacks(lua_State* state, const char* name) {
    if (state == nullptr || name == nullptr) {
        lua_newtable(state);
        return;
    }
    if (!PushNamedCallbacksTable(state)) {          // [.. named]
        lua_newtable(state);
        return;
    }
    lua_getfield(state, -1, name);                  // [.. named list?]
    lua_remove(state, -2);
    if (!lua_istable(state, -1)) {                  // "没有登记"与"名字下有 0 个回调"同形：空表
        lua_pop(state, 1);
        lua_newtable(state);
    }
}

namespace {

// 批次 268：`Isaac.RunCallbackWithParam(callbackId, param, ...)` 的过滤判据。
//
// `registeredIndex` / `requestedIndex` 是**同一次调用期间**栈上两个值的下标（0 = 那一侧没有值）。
// 规则逐字来自 PC 的 Lua 胶水（REPENTOGON issue #336 引用了那一段）：
//   `__matchParams = function(a, b) return not a or not b or a == -1 or b == -1 or a == b end`
// ⇒ ① 任一侧缺席（`nil` / 没给）⇒ 匹配；② 任一侧是 `-1` ⇒ 匹配；③ 其余按 Lua 的 `==` 比。
//
// 为什么用 `lua_compare(LUA_OPEQ)` 而不是 `lua_rawequal`：PC 那段用的就是 Lua 的 `==`
// （会走 `__eq`），而这里要比的类型可能是引擎句柄（userdata）—— 两边保持一致比"更严格"重要。
bool CallbackParamMatches(lua_State* state, int registeredIndex, int requestedIndex) {
    if (registeredIndex == 0 || requestedIndex == 0) {
        return true;
    }
    if (lua_isnoneornil(state, registeredIndex) || lua_isnoneornil(state, requestedIndex)) {
        return true;
    }
    if (lua_isnumber(state, registeredIndex) && lua_isnumber(state, requestedIndex)) {
        const lua_Integer registered = lua_tointegerx(state, registeredIndex, nullptr);
        const lua_Integer requested = lua_tointegerx(state, requestedIndex, nullptr);
        if (registered == -1 || requested == -1) {
            return true;
        }
    }
    return lua_compare(state, registeredIndex, requestedIndex, LUA_OPEQ) != 0;
}

} // namespace

int RunNamedCallbacksWithFilter(lua_State* state, const char* name, int filterIndex,
                                int firstArgument) {
    if (state == nullptr || name == nullptr) {
        return 0;
    }
    const int lastArgument = lua_gettop(state);
    if (!PushNamedCallbacksTable(state)) {          // [args.. named]
        return 0;
    }
    lua_getfield(state, -1, name);                  // [args.. named list?]
    lua_remove(state, -2);
    if (!lua_istable(state, -1)) {                  // 没有这个名字：安静返回（PC 亦然）
        lua_pop(state, 1);
        return 0;
    }
    const int listIndex = lua_gettop(state);
    const lua_Integer count = static_cast<lua_Integer>(lua_rawlen(state, listIndex));
    for (lua_Integer index = 1; index <= count; ++index) {
        lua_rawgeti(state, listIndex, index);       // [.. list entry]
        if (!lua_istable(state, -1)) {
            lua_pop(state, 1);
            continue;
        }
        const int entryIndex = lua_gettop(state);
        lua_getfield(state, entryIndex, "Function");// [.. list entry fn]
        if (!lua_isfunction(state, -1)) {
            lua_pop(state, 2);
            continue;
        }
        // 过滤值单独取出来比、**比完立刻弹掉**：它必须出现在
        // `lua_pcallk` 的"函数 + 实参"那一段**之外**，否则回调会多收到一个参数，
        // 而回调签名是 `function(mod, ...)` —— 多一个参数会让第二个形参错位
        // （`ChallengeAPI` 的 `onChallengeStart(_mod, challenge, isContinue)` 正是这种形状：
        //  错位之后 `isContinue` 会收到 `challenge` 表，恒真）。
        lua_getfield(state, entryIndex, "OptionalArg");   // [.. list entry fn filter]
        const int filterSlot = lua_gettop(state);
        const bool allowed = CallbackParamMatches(state, filterSlot, filterIndex);
        lua_pop(state, 1);                          // [.. list entry fn]
        if (!allowed) {
            lua_pop(state, 2);                      // 弹 fn + entry
            continue;
        }
        lua_getfield(state, entryIndex, "Mod");     // [.. list entry fn mod]
        // 回调签名是 `function(mod, ...)`：第一个参数永远是它自己的 Mod 对象，
        // 之后是调用方透传的实参。
        for (int argument = firstArgument; argument <= lastArgument; ++argument) {
            lua_pushvalue(state, argument);
        }
        const int argumentCount = (lastArgument - firstArgument + 1) + 1;
        if (lua_pcallk(state, argumentCount, 1, 0, 0, nullptr) != LUA_OK) {
            // 错误原样上抛：调用方（`Isaac.RunCallback*`）只负责把深度计数还回去。
            lua_remove(state, listIndex);
            return lua_error(state);
        }
        if (!lua_isnil(state, -1)) {
            // PC："breaking on the first return" —— 留下这个返回值交给 Lua。
            return 1;
        }
        lua_pop(state, 2);                          // 返回值 + entry
    }
    lua_settop(state, lastArgument);
    return 0;
}

int RunNamedCallbacks(lua_State* state, const char* name, int firstArgument) {
    return RunNamedCallbacksWithFilter(state, name, 0, firstArgument);
}


} // namespace isaac::runtime

// --- 回调登记普查 ---------------------------------------------------------
//
// 这段实现原来单独放在 `source/callback_registration_stats.cpp`，但**根目录下的新
// `source/*.cpp` 不会被打包构建自动收集**（构建只扫描 `source/` 的子目录与 `src/`），
// 结果是链接期留下未定义符号、真机加载时才会以 PC=0 的形式炸掉（`test_runtime_elf_symbols`
// 专门拦这种形态）。放回本文件——它本来就是唯一调用方，且一定被编译。
// 注意必须写成 `::LuaRuntime`：本文件在 `isaac::runtime` 命名空间里，不限定的话
// 定义会落进 `isaac::runtime::LuaRuntime`，与 `lua_runtime_state.hpp` 的声明（全局
// `LuaRuntime`）不是同一个符号 —— 链接期表现为未定义符号、真机加载时 PC=0。
namespace LuaRuntime {
namespace {

std::atomic<std::uint64_t> g_RegisteredLow{0};
std::atomic<std::uint64_t> g_RegisteredHigh{0};
std::atomic<std::uint32_t> g_Dispatchable{0};
std::atomic<std::uint32_t> g_Unhooked{0};

} // namespace

void RecordCallbackRegistration(std::uint32_t callbackId, bool hasDispatchSite) noexcept {
    if (callbackId < 64) {
        g_RegisteredLow.fetch_or(1ULL << callbackId, std::memory_order_release);
    } else if (callbackId < 128) {
        g_RegisteredHigh.fetch_or(1ULL << (callbackId - 64), std::memory_order_release);
    }
    if (hasDispatchSite) {
        g_Dispatchable.fetch_add(1, std::memory_order_relaxed);
    } else {
        g_Unhooked.fetch_add(1, std::memory_order_relaxed);
    }
}

std::uint64_t RegisteredCallbackKindMaskLow() noexcept {
    return g_RegisteredLow.load(std::memory_order_acquire);
}

std::uint64_t RegisteredCallbackKindMaskHigh() noexcept {
    return g_RegisteredHigh.load(std::memory_order_acquire);
}

std::uint32_t DispatchableCallbackRegistrationCount() noexcept {
    return g_Dispatchable.load(std::memory_order_acquire);
}

std::uint32_t UnhookedCallbackRegistrationCount() noexcept {
    return g_Unhooked.load(std::memory_order_acquire);
}

} // namespace LuaRuntime

namespace isaac::runtime {int Api700IsaacRemoveModData(lua_State*state){return ModRemoveData(state);}}
