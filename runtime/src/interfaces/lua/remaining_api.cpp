#include "interfaces/lua/field_api.hpp"
#include "interfaces/lua/remaining_api.hpp"
#include "interfaces/lua/vector_api.hpp"

#include "room_layout.hpp"

#include "interfaces/lua/api_sequence_probe.hpp"
#include "infrastructure/call/engine_call_access.hpp"
#include "infrastructure/memory/engine_field_access.hpp"
#include "infrastructure/memory/engine_memory_guard.hpp"
#include "interfaces/lua/engine_method_lookup.hpp"
// 批次 028：`ItemPool:GetPillEffect` 的可空 `EntityPlayer` 实参要经 `EntityPointerArgument`
// 解析（"什么算一个实体句柄"的唯一实现在那个 TU 里），所以这里显式包含它 —— 与本文件里
// `sprite_api` 用 `IsLiveEntityPointer` 的理由相同：不写第二份判据。
#include "interfaces/lua/isaac_api.hpp"
#include "interfaces/lua/lua_integer_argument.hpp"
#include "interfaces/lua/owner_binding.hpp"

#include "game_observer.hpp"
#include "lua_object_handles.hpp"
#include "level_start_room.hpp"
#include "lua_runtime_state.hpp"
#include "runtime_constants.hpp"

#include <atomic>
#include <cstdint>
#include <cstring>
#include <limits>

#if defined(__SWITCH__)
#include "lib/nx/nx.h"
#endif

extern "C" {
#include <lauxlib.h>
}

namespace isaac::runtime {
extern "C" {
// ============================================================================
// 房间描述符**解析现场**（批次 074，2026-09-19）
// ============================================================================
//
// 为什么要有它：用户报"从部分房间回到**两格房**时小地图不出现"。GoodTrip 的地图绘制
// 依赖 `floor.grid_room[floor.crd.SafeGridIndex] ~= nil`（`rules.lua` 的 `check_teleble`）——
// 也就是说，**只要那一个格子的描述符我们解析不出来，整张地图就不画**（而且不报错，
// 因为它是条件为假、不是异常）。多格房间（1x2 / 2x1 / 2x2 / L 形）里
// `SafeGridIndex` 与 `GridIndex` 锚在不同的格子，所以"另一个格子解析不出来"正是最可能的形态。
//
// 这几格就是用来一次读数分清"是哪一种失败"的：
//   * `Calls` / `Empty`：解析了多少次、其中多少次给了空句柄；
//   * `RejectedFootprint`：命中了候选、但被**足迹校验**（差值必须是 0/±1/±13/±14）挡掉的次数
//     —— 这一格非零就直接说明"校验太严"；
//   * `EngineMapUsed`：扫描没命中、改用引擎自己的映射表才找到的次数；
//   * `LastRequest` / `LastResolved*`：最后一次请求的格子与解析结果的三个字段。
std::atomic<std::uint32_t> g_IsaacRoomIdxCalls{0};
std::atomic<std::uint32_t> g_IsaacRoomIdxEmpty{0};
std::atomic<std::uint32_t> g_IsaacRoomIdxRejectedFootprint{0};
std::atomic<std::uint32_t> g_IsaacRoomIdxEngineMapUsed{0};
std::atomic<std::uint32_t> g_IsaacRoomIdxLastRequest{0xFFFFFFFFu};
std::atomic<std::uint32_t> g_IsaacRoomIdxLastResolvedGrid{0xFFFFFFFFu};
std::atomic<std::uint32_t> g_IsaacRoomIdxLastResolvedSafe{0xFFFFFFFFu};
std::atomic<std::uint32_t> g_IsaacRoomIdxLastResolvedList{0xFFFFFFFFu};
//: **被足迹校验挡掉时的具体数字**（批次 075）：最后一次的请求格子、那个槽位描述符的 `+0x00`、
//: 以及两者的差值（存成 `delta + 64`，避免负数进无符号）。没有这三格就只能猜"是校验太严还是
//: 映射表给错了房间"，有了它一眼就能分辨。
std::atomic<std::uint32_t> g_IsaacRoomIdxLastRejectRequest{0xFFFFFFFFu};
std::atomic<std::uint32_t> g_IsaacRoomIdxLastRejectAnchor{0xFFFFFFFFu};
std::atomic<std::uint32_t> g_IsaacRoomIdxLastRejectDeltaBias{0xFFFFFFFFu};
//: 引擎映射表给了**有效槽位**、但槽位越界或那一格没房间（我们的前两道校验）的次数。
//: 与"被足迹校验挡掉"分开记，才能分清"表给错了房间"与"表给了一个还没分配的槽位"。
std::atomic<std::uint32_t> g_IsaacRoomIdxMapSlotRejected{0x0u};
//: 批次 076：把"映射表给的槽位"分成四类，并记下**最后一次接受**的现场。
//: 为什么要拆：074/075 两次读数里"映射表给了有效槽位却被挡掉"高达 4971/8844（56%），
//: 而"被足迹校验挡掉"只有 152 —— 说明**大头是那道 `槽位 >= 元素个数` 的检查**，
//: 而引擎自己（`Level::GetRoomByIdx` @ `0x3dc5b0`）**根本没有这道检查**（槽号只判负数）。
std::atomic<std::uint32_t> g_IsaacRoomIdxAccepted{0x0u};
std::atomic<std::uint32_t> g_IsaacRoomIdxSlotNegative{0x0u};
std::atomic<std::uint32_t> g_IsaacRoomIdxUnallocatedAnchor{0x0u};
std::atomic<std::uint32_t> g_IsaacRoomIdxSlotBeyondCount{0x0u};
std::atomic<std::uint32_t> g_IsaacRoomIdxLastAcceptedRequest{0xFFFFFFFFu};
std::atomic<std::uint32_t> g_IsaacRoomIdxLastAcceptedSlot{0xFFFFFFFFu};
std::atomic<std::uint32_t> g_IsaacRoomIdxLastAcceptedAnchor{0xFFFFFFFFu};
std::atomic<std::uint32_t> g_IsaacRoomIdxLastAcceptedSafe{0xFFFFFFFFu};
//: 批次 077：**直接调引擎 `Level::GetRoomByIdx`** 的次数、回落次数，以及最后一次的入参。
std::atomic<std::uint32_t> g_IsaacRoomIdxNativeCalls{0x0u};
std::atomic<std::uint32_t> g_IsaacRoomIdxNativeFallbacks{0x0u};
std::atomic<std::uint32_t> g_IsaacRoomIdxNativeLastIndex{0xFFFFFFFFu};
std::atomic<std::uint32_t> g_IsaacRoomIdxNativeLastDimension{0xFFFFFFFFu};
std::atomic<std::uint32_t> g_IsaacRoomDescDataMisses{0};
std::atomic<std::uint32_t> g_IsaacRoomDescDataGridIndex{0};
std::atomic<std::uint32_t> g_IsaacRoomDescDataSafeGridIndex{0};
std::atomic<std::uint32_t> g_IsaacRoomDescDataListIndex{0};
std::atomic<std::uint32_t> g_IsaacRoomDescDataDescriptorLow{0};
}

// 供 `lua_runtime.cpp` 注册元表时调用（必须在这个 TU 之外可见，所以不能放在匿名命名空间里）。
int RoomDescriptorIndex(lua_State* state);
int RoomDescriptorListIndex(lua_State* state);
[[nodiscard]] std::size_t AttachRoomDescriptorListMethods(lua_State* state) noexcept;

// 批次 028（2026-09-18 夜）：EID 真的在调、而我们缺的 ItemPool / Level 成员。
// 声明放在匿名命名空间**之外**（与定义一致），实现的注释写在文件末尾各自的定义处。
int ItemPoolGetPillEffect(lua_State* state);
int ItemPoolGetPoolForRoom(lua_State* state);
int LevelGetLastRoomDesc(lua_State* state);

namespace {

using LuaRuntime::GameOwnerSlot;
using LuaRuntime::InManagedCallbackScope;
using LuaRuntime::ItemPoolGetCollectibleThunk;
using LuaRuntime::ItemPoolHandle;
using LuaRuntime::kItemPoolMetatable;
using LuaRuntime::kLevelMetatable;
using LuaRuntime::kGridEntityDoorMetatable;
using LuaRuntime::kRoomMetatable;
using LuaRuntime::EngineModuleBase;
using LuaRuntime::LevelIsAscentThunk;
using LuaRuntime::ValidateItemPoolGetCollectibleBinding;

int LevelGetStage(lua_State* state);
int LevelIsAscent(lua_State* state);
int LevelGetCurses(lua_State* state);
// 批次 8（2026-09-15）：`Level` 家族四个新成员（依据见各自实现处的长注释）。
int LevelGetCurrentRoomIndex(lua_State* state);
int LevelGetCurrentRoom(lua_State* state);
int LevelGetStartingRoomIndex(lua_State* state);
int LevelGetAbsoluteStage(lua_State* state);
int LevelIsNextStageAvailable(lua_State* state);
// 地基二期（2026-09-15）：房间描述符三件套。字段偏移全部来自布局表 + 真机行为验证，
// 见 `lua_object_handles.hpp` 里 `RoomDescriptorHandle` 上方那段说明。
int LevelGetCurrentRoomDesc(lua_State* state);
int LevelGetRoomByIdx(lua_State* state);
int LevelGetRooms(lua_State* state);
// `RoomDescriptorList.__index` / 方法（`Size` 与 `:Get(i)`）。
int RoomDescriptorListGet(lua_State* state);
int RoomGetType(lua_State* state);
// 批次 7（2026-09-12）：EID 在**网格/寻路**路径上无条件调用的一批 `Room` 成员
// （`features/eid_api.lua:3351` 的 `EID:EvaluateLocation`、`3371` 的 `HasPathToPosition`、
// `2593` 的网格实体查询）。缺任何一个都是 "attempt to call a nil value" ⇒ 整条回调被
// 派发器静默摘除 —— 与之前 `EntityPlayer.GetPill`、`Vector:__sub`、`Sprite:GetTexel` 同一类
// 缺口（真机报告 `01789218953` 就是在贪婪模式商店触发了一次同类错误，但错误文本只有一个
// `.`，无法定位到具体调用点，所以按"补齐已知缺口"处理）。
int RoomGetGridWidth(lua_State* state);
int RoomGetGridHeight(lua_State* state);
int RoomGetGridSize(lua_State* state);
int RoomGetGridIndex(lua_State* state);
int RoomGetGridPath(lua_State* state);
int RoomGetGridEntity(lua_State* state);
// 批次 046：`Room:GetDoor(slot)`（GoodTrip 运行期要它）。
int RoomGetDoor(lua_State* state);
int RoomGetRenderScrollOffset(lua_State* state);
int RoomGetWorldToScreenPosition(lua_State* state);
// 2026-09-16：`Room:GetFrameCount()`（房间已经活动了多少帧；真机上暴露的每帧报错见实现处注释）。
int RoomGetFrameCount(lua_State* state);
// 2026-09-18：`Room:IsMirrorWorld()`（当前房间是不是在镜像维度里）。判据与证据见实现处注释。
int RoomIsMirrorWorld(lua_State* state);
int LevelIsPreAscent(lua_State* state);
int GridEntityGetVariant(lua_State* state);
int GridEntityGetType(lua_State* state);
int GridEntityGetRng(lua_State* state);
int ItemPoolGetLastPool(lua_State* state);
int ItemPoolGetCollectible(lua_State* state);
int ItemPoolIsPillIdentified(lua_State* state);

constexpr LuaHandlerBinding kLevelHandlers[] = {
    {0x03010001, &LevelGetStage},
    {0x03010002, &LevelIsAscent},
    {0x03010003, &LevelGetCurses},
    {0x03010004, &LevelGetCurrentRoomIndex},
    {0x03010005, &LevelGetCurrentRoom},
    // 批次 106：`Level:GetStartingRoomIndex()`（EID 的 `eid_holdmapdesc` 用它判断"玩家是不是在
    // 起始房间"）。引擎里没有这个符号 ⇒ 取值是**派生**的（本层第一次被看到的房间），
    // 理由、取证边界与已知偏离见 `level_start_room.hpp` 顶部与 `api_deviation.cpp`。
    {0x03010011, &LevelGetStartingRoomIndex},
    {0x03010006, &LevelGetAbsoluteStage},
    {0x03010007, &LevelIsNextStageAvailable},
    {0x03010008, &LevelGetCurrentRoomDesc},
    {0x03010009, &LevelGetRoomByIdx},
    {0x0301000A, &LevelGetRooms},
    {0x0301000D, &LevelIsPreAscent},
    // 批次 028：`Level:GetLastRoomDesc()`（取号：Level 域下一个空号 = 0x0E，扫号得到）。
    {0x0301000E, &LevelGetLastRoomDesc},
};

constexpr LuaHandlerBinding kGridEntityHandlers[] = {
    {0x0E010052, &GridEntityGetVariant},
    {0x0E010053, &GridEntityGetType},
    {0x0E010054, &GridEntityGetRng},
};

constexpr LuaHandlerBinding kRoomHandlers[] = {
    {0x04010001, &RoomGetType},
    {0x04010002, &RoomGetGridWidth},
    {0x04010003, &RoomGetGridHeight},
    {0x04010004, &RoomGetGridSize},
    {0x04010005, &RoomGetGridIndex},
    {0x04010006, &RoomGetGridPath},
    {0x04010007, &RoomGetGridEntity},
    {0x04010008, &RoomGetRenderScrollOffset},
    {0x04010009, &RoomGetWorldToScreenPosition},
    {0x0401000A, &RoomGetFrameCount},
    // 0x000B：`Room:IsMirrorWorld`（2026-09-18）。Room 域此前用到 0x000A ⇒ 0x000B 是
    // **扫过整个域之后**确认的空号（见 `api_catalog.cpp` 那一行的注释）。
    {0x0401000B, &RoomIsMirrorWorld},
    // 批次 046：`Room:GetDoor`（id 取域内空号）。
    {0x0401000C, &RoomGetDoor},
};

constexpr LuaHandlerBinding kItemPoolHandlers[] = {
    {0x05010001, &ItemPoolGetCollectible},
    {0x05010002, &ItemPoolGetLastPool},
    {0x05010003, &ItemPoolIsPillIdentified},
    // 批次 028：两条 EID 真机报错/链式缺口（取号：ItemPool 域下一个空号 = 0x04 / 0x05）。
    {0x05010004, &ItemPoolGetPillEffect},
    {0x05010005, &ItemPoolGetPoolForRoom},
};

template <typename Table>
constexpr std::size_t RowCount(const Table& table) noexcept {
    return sizeof(table) / sizeof(table[0]);
}

int LevelGetStage(lua_State* state) {
    RecordApiSequenceSecondary(17U);
    luaL_checkudata(state, 1, kLevelMetatable);
    if (lua_gettop(state) != 1) {
        return luaL_error(state, "Level:GetStage accepts no arguments");
    }
    // ★ 2026-09-19（批次 043）：这里原本有一道 `InManagedCallbackScope()` 守卫，
    // 不在托管回调里就直接抛错（"… is only available during a Runtime callback"）。
    // **PC 没有这条限制**：模组在**加载期**读引擎状态是常见写法（GoodTrip 的
    // `scripts/floor.lua:11-17` 就在加载期读 `Game():GetLevel()`/`GetRoom()`/`Level:GetStage()`），
    // 而报错会让整个模组的功能**整块消失**（真机现象："模组像没装"）。
    // 所以守卫已删除：允许读，读不到时由各自实现返回**如实回退值**。
    // 证据与理由见 `docs/改动日志-20260919.md`（042·补二 / 043）。
    std::uint32_t stage = 0;
    if (ReadCurrentGameLevelStage(GameOwnerSlot(), &stage) != GameLevelStageObservation::Success) {
        return luaL_error(state, "Level:GetStage could not read the native Level state");
    }
    lua_pushinteger(state, static_cast<lua_Integer>(stage));
    return 1;
}

int LevelIsAscent(lua_State* state) {
    luaL_checkudata(state, 1, kLevelMetatable);
    if (lua_gettop(state) != 1) {
        return luaL_error(state, "Level:IsAscent accepts no arguments");
    }
    const GameIsAscentObservation observation =
        ObserveLevelIsAscent(GameOwnerSlot(), LevelIsAscentThunk());
    if (observation == GameIsAscentObservation::AscentFalse) {
        lua_pushboolean(state, 0);
        return 1;
    }
    if (observation == GameIsAscentObservation::AscentTrue) {
        lua_pushboolean(state, 1);
        return 1;
    }
    return luaL_error(state, "Level:IsAscent could not read the native Level state");
}

// `Level:GetCurses()`（批次 4）：读 `Level + 0x0C`（u32 诅咒位掩码）。
//
// **`Level*` 就是 `Game*`**：`Level` 内嵌在 `Game` 起始处（`docs/问题与解决记录.md` 批次 4
// 的"更正旧记录"——`Level+0x21550` 与 `Game+0x21550` 是同一个地址，而 `Game+0x21550` 正是
// `kGameRoomPointerOffset` 那个 Room 指针）。所以这里与 `Level:GetStage` 走同一条链。
//
// ★ **语义偏差（必须写明）**：PC 版 `Level:GetCurses()` 是三步
// `curses | 永久诅咒 & ~禁用诅咒`（"永久诅咒"与"禁用诅咒"来自另外两个引擎来源）。那两次
// 取值的函数地址本轮**没有定位**，所以本实现**只返回字段值**，不做那两步合成 ——
// 结果是：本局临时诅咒（`AddCurse`）能读到，`持久/禁用` 两侧的修正读不到。
// 这条差异写在注释里也写在交付报告里，不做任何猜测性补齐。
//
// 引擎内存读取原语与 `isaac_api.cpp`/`game_api.cpp` 同一形态（设备侧先 `svcQueryMemory` 确认
// 可读，宿主侧只排除空地址）：拿不到就报 Lua 错误——PC 里 `Level:GetCurses()` 返回 int，
// 编一个 0 会让 Mod 以为"这一层没有诅咒"。
// 「这段地址可读吗」：**唯一实现在引擎内存访问层里**（2026-09-24 批次 102 收敛）。
// 此前四个 API 族各有一份逐字相同的拷贝（去掉注释后各 781 字符）；判决条件一条没改，
// 只是"实现在几处"从 4 变成了 1。**函数名保留** —— `test_lua_missing_members_batch028`
// 按这个名字核对四个手写处理器体里有没有做可读性检查。
bool IsEngineMemoryReadable(std::uintptr_t address, std::size_t length) noexcept {
    return isaac::runtime::engine_memory::EngineMemoryReadable(address, length);
}

bool ReadGameCurses(std::uint32_t* curses) noexcept {
    if (curses == nullptr) {
        return false;
    }
    const std::uintptr_t base = EngineModuleBase();
    if (base == 0 || base > UINTPTR_MAX - kGameOwnerGlobalSlotOffset) {
        return false;
    }
    // 两级解引用：槽里是**指针变量**，`*(u64*)槽` 才是 `Game*`（与 `Isaac.GetPlayer` 同链）。
    std::uintptr_t ownerSlot = 0;
    std::uintptr_t game = 0;
    // 这一支的每一处读写都走引擎内存访问层（L1）：判定与取值同一次调用，失败时不写出参。
    if (!isaac::runtime::engine_memory::ReadAt(base + kGameOwnerGlobalSlotOffset, &ownerSlot,
                                               &IsEngineMemoryReadable)) {
        return false;
    }
    if (ownerSlot == 0 ||
        !isaac::runtime::engine_memory::ReadAt(ownerSlot, &game, &IsEngineMemoryReadable)) {
        return false;
    }
    if (game == 0 || game > UINTPTR_MAX - kLevelCursesOffset ||
        !isaac::runtime::engine_memory::ReadAt(game + kLevelCursesOffset, curses,
                                               &IsEngineMemoryReadable)) {
        return false;
    }
    return true;
}

// --- `Level:GetCurses()` 的读数探针（2026-09-12，动作三）--------------------------
//
// 为什么要它：EID 的 `hasCurseBlind()`（`eid_api.lua:597`）是"隐瞒分支"四条成因之一，
// 而它的全部输入就是 `Level:GetCurses()` 的返回值。反汇编已经证明我们的**地址链**没错、
// 但**语义**只做了三步里的第一步（见 `runtime_constants.hpp` 的
// `kGameSpecialSeedPermanentCursesOffset` 注释）。真机读数要同时回答两件事：
//   * 这一层的原始诅咒位到底是多少（`raw`）；
//   * 引擎自己的两步合成结果是多少（`permanent`/`banned`），以及调用是否成功（`flags`）。
// 有了这两个数就能判定"误判是位读错，还是缺了合成"。
std::atomic<std::uint32_t> g_ProbeRawCurses{0};
std::atomic<std::uint32_t> g_ProbePermanentCurses{0};
std::atomic<std::uint32_t> g_ProbeBannedCurses{0};
std::atomic<std::uint32_t> g_ProbeCursesFlags{0};
std::atomic<std::uint32_t> g_ProbeCursesReads{0};

// 调引擎的 `Game::GetSpecialSeedPermanentCurses()` / `GetSpecialSeedBannedCurses()`
// （都是 `unsigned int() const`，`this` 在 x0）。与其它引擎调用同一口径：
// **先验 16 字节守卫**，不符就返回 0 且**不调用**，绝不调用未校验的地址。
//
// `Game*` 的取法与 `ReadGameCurses` 完全一致：`GameOwnerSlot()` 是**指针变量**的地址
// （`SetGameBindings` 发布的那个全局槽），所以 `*(u64*)slot` 才是 `Game*`。
std::uint32_t CallGameCurseAccessor(std::uintptr_t offset,
                                    const std::array<u8, 16>& expected,
                                    bool* called) noexcept {
    if (called != nullptr) {
        *called = false;
    }
    const std::uintptr_t base = EngineModuleBase();
    if (base == 0 || offset > UINTPTR_MAX - base) {
        return 0;
    }
    const std::uintptr_t target = base + offset;
    // 入口序言核对走引擎调用层（L2）的 `VerifyEntryBytes`：判定 + 逐字节比较，与原三句逐条同义。
    if (!isaac::runtime::engine_call::VerifyEntryBytes(target, expected.data(), expected.size(),
                                                       &IsEngineMemoryReadable)) {
        return 0;
    }
    const std::uintptr_t ownerSlot = GameOwnerSlot();
    std::uintptr_t game = 0;
    if (ownerSlot == 0 ||
        !isaac::runtime::engine_memory::ReadAt(ownerSlot, &game, &IsEngineMemoryReadable)) {
        return 0;
    }
    if (game == 0) {
        return 0;
    }
    using AccessorFn = std::uint32_t (*)(void*);
    const std::uint32_t value = isaac::runtime::engine_call::AsFunction<AccessorFn>(target)(
        isaac::runtime::engine_memory::AsObject(game));
    if (called != nullptr) {
        *called = true;
    }
    return value;
}

void RecordGameCursesReadForProbe(std::uint32_t raw) noexcept {
    g_ProbeCursesReads.fetch_add(1, std::memory_order_relaxed);
    g_ProbeRawCurses.store(raw, std::memory_order_relaxed);
    std::uint32_t flags = 1U;  // bit0：原始位读到了（能走到这里就说明读到了）
    bool permanentCalled = false;
    bool bannedCalled = false;
    const std::uint32_t permanent = CallGameCurseAccessor(
        kGameSpecialSeedPermanentCursesOffset, kGameSpecialSeedPermanentCursesExpectedBytes,
        &permanentCalled);
    const std::uint32_t banned = CallGameCurseAccessor(kGameSpecialSeedBannedCursesOffset,
                                                       kGameSpecialSeedBannedCursesExpectedBytes,
                                                       &bannedCalled);
    if (permanentCalled) {
        flags |= 2U;  // bit1：permanent 访问器**确实被调到**（守卫通过）
    }
    if (bannedCalled) {
        flags |= 4U;  // bit2：banned 访问器确实被调到
    }
    g_ProbePermanentCurses.store(permanent, std::memory_order_relaxed);
    g_ProbeBannedCurses.store(banned, std::memory_order_relaxed);
    g_ProbeCursesFlags.store(flags, std::memory_order_relaxed);
}

int LevelGetCurses(lua_State* state) {
    luaL_checkudata(state, 1, kLevelMetatable);
    if (lua_gettop(state) != 1) {
        return luaL_error(state, "Level:GetCurses accepts no arguments");
    }
    std::uint32_t curses = 0;
    if (!ReadGameCurses(&curses)) {
        return luaL_error(state, "Level:GetCurses could not read the native Level state");
    }
    RecordGameCursesReadForProbe(curses);
    lua_pushinteger(state, static_cast<lua_Integer>(curses));
    return 1;
}

// --- 批次 8（2026-09-15）：`Level` 家族另外四个成员 ------------------------------
//
// 缺口来源：`tools/eid_api_gap_report.py` 的高置信表（`missing_in_runtime`）。EID 在
// **描述构建**路径上无条件调用它们，缺一个就是 "attempt to call a nil value" ⇒ 整条描述回调
// 在报错处中断（`features/eid_modifiers.lua:197/200` 的潘多拉魔盒条目就是这一处）。
//
// 指针链与 `ReadGameCurses` 逐句相同：`GameOwnerSlot()` 是**指针变量**的地址，
// `*(u64*)slot` 才是 `Game*`；而 `Level` 就内嵌在 `Game` 起始处（同一地址），所以
// `Level*` 与 `Game*` 是同一个值 —— 这不是新假设，`Level:GetStage`/`GetCurses` 走的就是这条链。
//
// **引擎方法（两个）**：入口地址由安装期 16 字节守卫校验后发布（`...Thunk()`，0 = 不可用），
// handler 调用前**再验一次**同一份守卫 —— 与 `CallGameCurseAccessor` 同一口径：
// 宁可报"不可用"，也绝不调用一个没校验过的地址。
bool ResolveCurrentLevel(std::uintptr_t* level) noexcept {
    if (level == nullptr) {
        return false;
    }
    const std::uintptr_t base = EngineModuleBase();
    if (base == 0 || base > UINTPTR_MAX - kGameOwnerGlobalSlotOffset) {
        return false;
    }
    std::uintptr_t ownerSlot = 0;
    if (!isaac::runtime::engine_memory::ReadAt(base + kGameOwnerGlobalSlotOffset, &ownerSlot,
                                               &IsEngineMemoryReadable)) {
        return false;
    }
    std::uintptr_t game = 0;
    if (ownerSlot == 0 ||
        !isaac::runtime::engine_memory::ReadAt(ownerSlot, &game, &IsEngineMemoryReadable)) {
        return false;
    }
    if (game == 0) {
        return false;
    }
    *level = game;
    return true;
}

// 调用一个"只吃 `this`、返回 int"的 `Level` 成员（当前只有 `GetAbsoluteStage`）。
// 返回 false 表示"这次没有真的调用到引擎"，调用方必须据此报错而不是编一个值。
bool CallLevelIntMethod(std::uintptr_t method, const std::array<u8, 16>& expected,
                        std::int32_t* value) noexcept {
    if (value == nullptr || method == 0 || (method & 3) != 0 ||
        !isaac::runtime::engine_call::VerifyEntryBytes(method, expected.data(), expected.size(),
                                                       &IsEngineMemoryReadable)) {
        return false;
    }
    std::uintptr_t level = 0;
    if (!ResolveCurrentLevel(&level)) {
        return false;
    }
    using LevelIntMethod = std::int32_t (*)(const void*);
    *value = isaac::runtime::engine_call::AsFunction<LevelIntMethod>(method)(
        isaac::runtime::engine_memory::AsObject(level));
    return true;
}

// 调"向量进、向量出"的引擎函数（`GetRenderPosition(const Vector2&, bool)`）。
//
// 与 `CallLevelIntMethod` 同一形态：**先核对入口 16 字节**再调用 —— 只认"这个地址上确实是
// 那一串指令"，不认"地址恰好落在模块里"。返回值是 8 字节的结构体（两个 float），
// AAPCS64 下走 `s0/s1`，所以直接按 `Vec2` 值返回即可。
[[maybe_unused]] bool CallVectorEngineMethod(std::uintptr_t method,
                                            const std::array<u8, 16>& expected,
                            const float* input, float* output, bool argument) noexcept {
    if (method == 0 || input == nullptr || output == nullptr || (method & 3) != 0 ||
        !isaac::runtime::engine_call::VerifyEntryBytes(method, expected.data(), expected.size(),
                                                       &IsEngineMemoryReadable)) {
        return false;
    }
    struct Vector2Value {
        float x;
        float y;
    };
    using Method = Vector2Value (*)(const Vector2Value&, bool);
    const Vector2Value value{input[0], input[1]};
    const Vector2Value result =
        isaac::runtime::engine_call::AsFunction<Method>(method)(value, argument);
    output[0] = result.x;
    output[1] = result.y;
    return true;
}

bool CallLevelBoolMethod(std::uintptr_t method, const std::array<u8, 16>& expected,
                         bool* value) noexcept {
    if (value == nullptr || method == 0 || (method & 3) != 0 ||
        !isaac::runtime::engine_call::VerifyEntryBytes(method, expected.data(), expected.size(),
                                                       &IsEngineMemoryReadable)) {
        return false;
    }
    std::uintptr_t level = 0;
    if (!ResolveCurrentLevel(&level)) {
        return false;
    }
    using LevelBoolMethod = bool (*)(const void*);
    *value = isaac::runtime::engine_call::AsFunction<LevelBoolMethod>(method)(
        isaac::runtime::engine_memory::AsObject(level));
    return true;
}

int LevelGetCurrentRoomIndex(lua_State* state) {
    luaL_checkudata(state, 1, kLevelMetatable);
    if (lua_gettop(state) != 1) {
        return luaL_error(state, "Level:GetCurrentRoomIndex accepts no arguments");
    }
    std::uintptr_t level = 0;
    std::uint32_t index = 0;
    if (!ResolveCurrentLevel(&level) ||
        !isaac::runtime::engine_memory::ReadAt(level + kLevelCurrentRoomIndexOffset, &index,
                                               &IsEngineMemoryReadable)) {
        return luaL_error(state, "Level:GetCurrentRoomIndex could not read the native Level state");
    }
    lua_pushinteger(state, static_cast<lua_Integer>(index));
    return 1;
}

// `Level:GetStartingRoomIndex()`（PC 文档 `Level.md:258`：`int GetStartingRoomIndex()`，
// "Returns the gridindex of the starting room of the current level"）。
//
// ★ 引擎里**没有**这个符号/字段（取证见 `level_start_room.hpp` 顶部）⇒ 取值是派生的：
//   **本层第一次被看到的那个房间索引**。这里在取值前先"懒观察"一次（自己读一次当前层与当前房间），
//   于是不依赖有没有模组登记帧事件族；已经记过本层时它什么都不改。
int LevelGetStartingRoomIndex(lua_State* state) {
    luaL_checkudata(state, 1, kLevelMetatable);
    if (lua_gettop(state) != 1) {
        return luaL_error(state, "Level:GetStartingRoomIndex accepts no arguments");
    }
    LuaRuntime::NoteCurrentLocationForStartRoom();
    const std::uint32_t index = LuaRuntime::StartingRoomIndexForCurrentLevel();
    if (index == LuaRuntime::LevelStartRoomTracker::kUnknownRoomIndex) {
        // 还没观察到任何一层（例如在菜单里调用）⇒ 给 -1。刻意**不报错**：PC 上它返回一个整数，
        // 而模组会拿它去比较（`GetStartingRoomIndex() ~= GetCurrentRoomIndex()`），-1 会判成
        // "不是起始房间"，正是"还没进局"时最合理的答案（PC 也不会说"你在起始房间"）。
        lua_pushinteger(state, -1);
        return 1;
    }
    lua_pushinteger(state, static_cast<lua_Integer>(index));
    return 1;
}

// `Level:GetCurrentRoom()` —— PC 语义是"当前房间对象"，与 `Game:GetRoom()` 返回同一个 `Room`。
// 复用 `ReadCurrentGameRoom`（`Game + 0x21550`，已上机验证）与 `Game:GetRoom` 完全相同的句柄编组，
// 所以这里不引入新的偏移假设。
int LevelGetCurrentRoom(lua_State* state) {
    luaL_checkudata(state, 1, kLevelMetatable);
    if (lua_gettop(state) != 1) {
        return luaL_error(state, "Level:GetCurrentRoom accepts no arguments");
    }
    void* room = nullptr;
    if (ReadCurrentGameRoom(GameOwnerSlot(), &room) != GameRoomObservation::Success) {
        return luaL_error(state, "Level:GetCurrentRoom could not read the native Room state");
    }
    auto* handle = static_cast<LuaRuntime::RoomHandle*>(
        lua_newuserdata(state, sizeof(LuaRuntime::RoomHandle)));
    handle->reserved = 0;
    luaL_getmetatable(state, kRoomMetatable);
    lua_setmetatable(state, -2);
    return 1;
}

int LevelGetAbsoluteStage(lua_State* state) {
    luaL_checkudata(state, 1, kLevelMetatable);
    if (lua_gettop(state) != 1) {
        return luaL_error(state, "Level:GetAbsoluteStage accepts no arguments");
    }
    std::int32_t stage = 0;
    if (!CallLevelIntMethod(LuaRuntime::LevelGetAbsoluteStageThunk(),
                            kLevelGetAbsoluteStageExpectedBytes, &stage)) {
        return luaL_error(state, "Level:GetAbsoluteStage is unavailable in this build");
    }
    lua_pushinteger(state, static_cast<lua_Integer>(stage));
    return 1;
}

int LevelIsNextStageAvailable(lua_State* state) {
    luaL_checkudata(state, 1, kLevelMetatable);
    if (lua_gettop(state) != 1) {
        return luaL_error(state, "Level:IsNextStageAvailable accepts no arguments");
    }
    bool available = false;
    if (!CallLevelBoolMethod(LuaRuntime::LevelIsNextStageAvailableThunk(),
                             kLevelIsNextStageAvailableExpectedBytes, &available)) {
        return luaL_error(state, "Level:IsNextStageAvailable is unavailable in this build");
    }
    lua_pushboolean(state, available ? 1 : 0);
    return 1;
}

int RoomGetType(lua_State* state) {
    RecordApiSequenceSecondary(16U);
    luaL_checkudata(state, 1, kRoomMetatable);
    if (lua_gettop(state) != 1) {
        return luaL_error(state, "Room:GetType accepts no arguments");
    }
    std::uint32_t roomType = 0;
    if (ReadCurrentGameRoomType(GameOwnerSlot(), &roomType) != GameRoomObservation::Success) {
        return luaL_error(state, "Room:GetType could not read the native Room state");
    }
    lua_pushinteger(state, static_cast<lua_Integer>(roomType));
    return 1;
}

// 前置声明：`RoomArgumentCountIs` 的**定义**在下面的"批次 7"那一段（它依赖 `kRoomMetatable`）。
// 本函数用到它，所以在这里先声明一下 —— 否则要先读几百行才知道顺序要求。
bool RoomArgumentCountIs(lua_State* state, int expected, const char* apiName);

// `Room:IsMirrorWorld()` —— PC 文档说"Returns true if the player is inside the mirror
// dimension"（`Room.md`），返回 boolean。
//
// **判据：当前房间的维度 == `kMirrorWorldDimension`(1)**，读的是 `Level + 0x21560`
// —— 就是引擎判"当前房间属于哪个维度"的那个字（`Level::GetCurrentRoomDesc` 把它当
// `GetRoomByIdx(index, dimension)` 的第 2 个实参）。维度枚举的含义（0 主维度 / **1 次级维度
// = Downpour·Dross 的镜子维度** / 2 死亡证明维度）出自 PC 文档快照 `RoomDescriptor.md`。
// 全部证据链写在 `runtime_constants.hpp` 的 `kMirrorWorldDimension` 那里。
//
// ⚠️ **已知过宽**：矿坑逃脱序列也用维度 1 ⇒ 那一幕也会答 true（与判据的粒度有关，
// 不是 bug；要细分得另找引擎判据，目前没有）。
//
// 为什么读"当前维度"而不是"传进来的那个 Room 对象的维度"：PC 的说明是"**玩家**在镜像维度里"
// （以玩家/当前关卡为准）；而模组的用法正是 `level:GetCurrentRoom():IsMirrorWorld()`
// （EID `main.lua:839`），两者一致。真要按"某个 Room 对象自己的维度"，得读它的
// `Descriptor->Dimension` —— 那个字段在我们的布局表里**还没取证**，不能猜。
int RoomIsMirrorWorld(lua_State* state) {
    if (!RoomArgumentCountIs(state, 1, "Room:IsMirrorWorld")) {
        return 0;
    }
    std::uint32_t dimension = 0;
    if (ReadCurrentGameRoomDimension(GameOwnerSlot(), &dimension) !=
        GameLevelStageObservation::Success) {
        // 读不到就报错而不是答 false：EID 用它的结果决定"要不要隐藏描述"，
        // 编一个 false 会让它的行为在镜像维度里反向 —— 报错至少是可见的。
        return luaL_error(state, "Room:IsMirrorWorld could not read the native Room state");
    }
    lua_pushboolean(state, dimension == kMirrorWorldDimension ? 1 : 0);
    return 1;
}

// --- 批次 7：`Room` 的网格与寻路成员 -----------------------------------------
//
// **2026-09-20（批次 098）这一族从"保守占位"改成了真实现**，起因是一个**用户可见**的缺陷：
// 用户报"走到地上药丸/卡片旁边只显示一个问号"。追下去发现 EID 有两条画问号的分支，其中
// "够不到就不给看"那条的判据就是本族 API：
//
//   `eid_api.lua:3351` 的 `EID:EvaluateLocation`：`collision = room:GetGridPath(gridIndex)`，
//   然后 `return collision <= 900`；`3371` 的 `EID:HasPathToPosition` 用它跑 `EID.Pathfinder`
//   （`features/pathfinder/luafinding.lua`，纯 Lua A*），没路就 `return false`；
//   `main.lua:1639-1648`（药丸）与 `1614-1622`（卡片）据此走隐瞒分支、只画问号。
//
// 旧的占位实现里 `GetGridPath` 恒返回 1000（> 900 ⇒ 恒"不可走"）⇒ **地上每一颗药丸、每一张
// 卡片都恒判"够不到"** ⇒ 问号。当时（批次 7）把副作用评估成"只是不画路径提示"，漏看了它在
// 药丸/卡片上等于"藏掉整条描述" —— 这是"占位实现的副作用没按模组实际用法评估"的又一例。
//
// 真实现的证据（`tools/nro_disasm.py`，三条互相印证，细节见 `runtime_constants.hpp`）：
//   * `Room::GetGridPath(int,int) @ 0x484120`：`+0x14` 是宽度上限、`+0x18` 是高度上限、
//     数组在 `+0xE98`（int32/格、下标 `W*y + x`），越界返回 0；
//   * `Room::GetGridIndex(Vector2) @ 0x459e3c` 与 `GetGridIndex(int,int) @ 0x45a264`：
//     `W*gy + gx`，越界 −1；
//   * **下标口径不用猜**：`luafinding.lua` 的 `Initialize` 写的是 `FindVector(start.Y, start.X)`
//     —— 寻路器内部把 X/Y 换了一次 —— 所以 EID 的 `x*width + y` 恰好就是引擎的 `W*gy + gx`，
//     即 `GetGridPath(index)` 必须**按引擎那张表的下标直读、不做任何转置**。
//
// 宿主侧的行为证据（不花真机）：`tools/room_grid_reachability_probe.py` 用**EID 自己的寻路器**
// 跑合成网格 —— 旧口径四个场景（全可走 / 目标被围死 / 竖墙隔开 / 高代价但可走）**全判"没路"**
// （宿主上复现症状），新口径与 PC 判据一致（全可走=有路、围死=没路、墙=没路、900=有路）。
//
// 仍然存在的偏离（已登记在 `api_deviation.cpp`）：PC 的 Lua `GetGridPath(Index)` 是**直接按下标
// 读数组**，越界会读进相邻内存；我们**不做越界读**，越界一律回答 0（= 引擎自己对越界坐标的答案）。
// 网格尺寸的合法范围（真机标准房间是 13×7）。读出来的宽高不在这个区间 ⇒ 当作"没读到"并报错，
// 而不是把垃圾值当尺寸交出去 —— 尺寸错了，EID 的下标会算出别的格子，"条件为假、不报错"最难查。
constexpr std::uint32_t kRoomGridDimensionMaximum = 64;

//: 读 `Room + 0x14`/`+0x18` 两个尺寸字段（批次 098）。两个都读到、且都在合法区间才算成功。
bool ReadRoomGridDimensions(std::uintptr_t room, std::uint32_t* width, std::uint32_t* height) {
    if (room == 0 || width == nullptr || height == nullptr ||
        room > UINTPTR_MAX - kRoomGridHeightOffset - sizeof(std::uint32_t)) {
        return false;
    }
    std::uint32_t readWidth = 0;
    std::uint32_t readHeight = 0;
    if (!isaac::runtime::engine_memory::ReadAt(room + kRoomGridWidthOffset, &readWidth,
                                               &IsEngineMemoryReadable) ||
        !isaac::runtime::engine_memory::ReadAt(room + kRoomGridHeightOffset, &readHeight,
                                               &IsEngineMemoryReadable)) {
        return false;
    }
    if (readWidth == 0 || readHeight == 0 || readWidth > kRoomGridDimensionMaximum ||
        readHeight > kRoomGridDimensionMaximum) {
        return false;
    }
    *width = readWidth;
    *height = readHeight;
    return true;
}

//: 世界坐标 → 格坐标，逐字复刻 `Room::GetGridIndex(Vector2) @ 0x459e3c` 的算术：
//: `(int)((pos − offset) / 40 + 0.5)`，其中 `(int)` 是 AArch64 `fcvtzs` = **向零截断**。
//: C++ 的浮点→整型转换本身就是向零截断，所以这里只补两端钳位（超范围转换是 UB），
//: NaN 会被下面第一条判断兜住（NaN 的比较恒为 false）并落到最小值 ⇒ 调用方的越界检查会拒它。
std::int32_t RoomGridCoordinateFromWorld(float world, float origin) {
    const float value = (world - origin) / kRoomGridCellSize + 0.5F;
    if (!(value > -2147483648.0F)) {
        return -2147483648;
    }
    if (value >= 2147483648.0F) {
        return 2147483647;
    }
    return static_cast<std::int32_t>(value);
}

//: `Room*` → 当前房间对象（与 `RoomGetFrameCount` 同一条链）。读不到时返回 0。
std::uintptr_t CurrentRoomAddress() {
    void* room = nullptr;
    if (ReadCurrentGameRoom(GameOwnerSlot(), &room) != GameRoomObservation::Success) {
        return 0;
    }
    return isaac::runtime::engine_memory::AddressOf(room);
}

bool RoomArgumentCountIs(lua_State* state, int expected, const char* apiName) {
    luaL_checkudata(state, 1, kRoomMetatable);
    if (lua_gettop(state) != expected) {
        luaL_error(state, "%s accepts %d argument(s)", apiName, expected - 1);
        return false;
    }
    return true;
}

// Lua 5.3 distinguishes integer and float subtypes. EID computes grid indexes from Vector
// coordinates, so an integral value can arrive as `5.0`; accept any number that converts
// losslessly to an integer, matching the PC C API's integer parameter contract.
bool RoomGridIndexArgument(lua_State* state, int index, lua_Integer* value) {
    int isNumber = 0;
    const lua_Integer converted = lua_tointegerx(state, index, &isNumber);
    if (!isNumber) {
        return false;
    }
    if (value != nullptr) {
        *value = converted;
    }
    return true;
}

// --- 2026-09-16：`Room:GetFrameCount()` -----------------------------------------
//
// PC 语义（`analysis/isaacdocs-snapshot/docs/Room.md`）："Returns the amount of frames the room has
// been active for. Resets to 0 when the player leaves the room or the run is exited."
//
// 为什么要补：EID 的背包合成渲染路径里有 `game:GetRoom():GetFrameCount() < 2`
// （`features/eid_bagofcrafting.lua:967`）。这个 API 之前**完全不存在** ⇒ 只要玩家拿着背包合成，
// 那句就每帧抛 `attempt to call a nil value (method 'GetFrameCount')`，**EID 的描述渲染整段被打断**
// —— 这是 2026-09-16 真机上（`g_LastLuaErrorText`）暴露出来的用户可见缺陷。
//
// 实现口径：调引擎自己的 `Room::GetFrameCount()`（`0x470B0C`，只有 `this` 一个参数）。
// 调用前**再核对一次入口 16 字节**（与 `CallLevelIntMethod` 同一形态：只认"这串指令在"，
// 不认"地址恰好落在模块里"）。绑定为 0（安装期守卫没过）时**报 Lua 错误**而不是返回 0 ——
// 返回 0 会让上面那句判断恒成立，把合成结果显示静默跳过，属于最难查的一类缺陷。
bool CallRoomIntMethod(void* room, std::uintptr_t method,
                       const std::array<u8, 16>& expected, std::int32_t* value) noexcept {
    if (room == nullptr || value == nullptr || method == 0 || (method & 3) != 0 ||
        !isaac::runtime::engine_call::VerifyEntryBytes(method, expected.data(), expected.size(),
                                                       &IsEngineMemoryReadable)) {
        return false;
    }
    using RoomIntMethod = std::int32_t (*)(const void*);
    *value = isaac::runtime::engine_call::AsFunction<RoomIntMethod>(method)(room);
    return true;
}

int RoomGetFrameCount(lua_State* state) {
    if (!RoomArgumentCountIs(state, 1, "Room:GetFrameCount")) {
        return 0;
    }
    void* room = nullptr;
    if (ReadCurrentGameRoom(GameOwnerSlot(), &room) != GameRoomObservation::Success ||
        room == nullptr) {
        return luaL_error(state, "Room:GetFrameCount could not read the native Room state");
    }
    const std::uintptr_t method = LuaRuntime::RoomGetFrameCountThunk();
    std::int32_t frames = 0;
#if !defined(__SWITCH__)
    // 宿主：没有引擎映像，用注入的替身（与 `Room:WorldToScreenPosition` 的宿主钩子同一形态）。
    // 没注入替身、也没发布绑定 ⇒ 走下面那条"绑定不可用"，**不编造帧数**。
    const auto host = LuaRuntime::GetRoomGetFrameCountHostFunction();
    if (host != nullptr) {
        frames = host(room);
    } else if (!CallRoomIntMethod(room, method, kRoomGetFrameCountExpectedBytes, &frames)) {
        return luaL_error(state, "Room:GetFrameCount binding is unavailable");
    }
#else
    if (!CallRoomIntMethod(room, method, kRoomGetFrameCountExpectedBytes, &frames)) {
        return luaL_error(state, "Room:GetFrameCount binding is unavailable");
    }
#endif
    lua_pushinteger(state, static_cast<lua_Integer>(frames));
    return 1;
}

int RoomGetGridWidth(lua_State* state) {
    if (!RoomArgumentCountIs(state, 1, "Room:GetGridWidth")) {
        return 0;
    }
    std::uint32_t width = 0;
    std::uint32_t height = 0;
    if (!ReadRoomGridDimensions(CurrentRoomAddress(), &width, &height)) {
        return luaL_error(state, "Room:GetGridWidth could not read the native grid dimensions");
    }
    lua_pushinteger(state, static_cast<lua_Integer>(width));
    return 1;
}

int RoomGetGridHeight(lua_State* state) {
    if (!RoomArgumentCountIs(state, 1, "Room:GetGridHeight")) {
        return 0;
    }
    std::uint32_t width = 0;
    std::uint32_t height = 0;
    if (!ReadRoomGridDimensions(CurrentRoomAddress(), &width, &height)) {
        return luaL_error(state, "Room:GetGridHeight could not read the native grid dimensions");
    }
    lua_pushinteger(state, static_cast<lua_Integer>(height));
    return 1;
}

int RoomGetGridSize(lua_State* state) {
    if (!RoomArgumentCountIs(state, 1, "Room:GetGridSize")) {
        return 0;
    }
    std::uint32_t width = 0;
    std::uint32_t height = 0;
    if (!ReadRoomGridDimensions(CurrentRoomAddress(), &width, &height)) {
        return luaL_error(state, "Room:GetGridSize could not read the native grid dimensions");
    }
    // PC 返回格子总数（`width * height`）；真机标准房间是 13×7 = 91，不再是以前那个 169。
    lua_pushinteger(state, static_cast<lua_Integer>(width) * static_cast<lua_Integer>(height));
    return 1;
}

int RoomGetGridIndex(lua_State* state) {
    luaL_checkudata(state, 1, kRoomMetatable);
    const int argumentCount = lua_gettop(state);
    std::uint32_t width = 0;
    std::uint32_t height = 0;
    if (!ReadRoomGridDimensions(CurrentRoomAddress(), &width, &height)) {
        return luaL_error(state, "Room:GetGridIndex could not read the native grid dimensions");
    }
    std::int32_t gridX = 0;
    std::int32_t gridY = 0;
    // 两个重载：`GetGridIndex(int,int)` 与 `GetGridIndex(Vector)`。EID 用的是 Vector 版
    // （`eid_api.lua:3375` 的 `room:GetGridIndex(startPos)`），但 PC 两种都有，这里都支持。
    if (argumentCount == 2) {
        auto* position =
            static_cast<LuaRuntime::VectorHandle*>(luaL_testudata(state, 2, LuaRuntime::kVectorMetatable));
        if (position == nullptr) {
            return luaL_error(state, "Room:GetGridIndex accepts a Vector");
        }
        gridX = RoomGridCoordinateFromWorld(position->x, kRoomGridWorldOffsetX);
        gridY = RoomGridCoordinateFromWorld(position->y, kRoomGridWorldOffsetY);
    } else if (argumentCount == 3 && isaac::runtime::IsIntegerArgument(state, 2) &&
               isaac::runtime::IsIntegerArgument(state, 3)) {
        const lua_Integer x = lua_tointegerx(state, 2, nullptr);
        const lua_Integer y = lua_tointegerx(state, 3, nullptr);
        if (x > std::numeric_limits<std::int32_t>::max() ||
            x < std::numeric_limits<std::int32_t>::min() ||
            y > std::numeric_limits<std::int32_t>::max() ||
            y < std::numeric_limits<std::int32_t>::min()) {
            return luaL_error(state, "Room:GetGridIndex integer coordinates are out of range");
        }
        gridX = static_cast<std::int32_t>(x);
        gridY = static_cast<std::int32_t>(y);
    } else {
        return luaL_error(state, "Room:GetGridIndex accepts a Vector or two integers");
    }
    // PC 语义（`analysis/isaacdocs-snapshot/docs/Room.md`）："Returns -1 for invalid index."
    // —— 越界是**合法输入**、答案是 −1，不是报错（EID 拿它当"这一格不合法"用）。
    if (gridX < 0 || gridY < 0 || static_cast<std::uint32_t>(gridX) >= width ||
        static_cast<std::uint32_t>(gridY) >= height) {
        lua_pushinteger(state, -1);
        return 1;
    }
    lua_pushinteger(state, static_cast<lua_Integer>(width) * gridY + gridX);
    return 1;
}

int RoomGetGridPath(lua_State* state) {
    luaL_checkudata(state, 1, kRoomMetatable);
    if (lua_gettop(state) != 2 || !RoomGridIndexArgument(state, 2, nullptr)) {
        return luaL_error(state, "Room:GetGridPath accepts one grid index");
    }
    const lua_Integer index = lua_tointegerx(state, 2, nullptr);
    std::uint32_t width = 0;
    std::uint32_t height = 0;
    if (!ReadRoomGridDimensions(CurrentRoomAddress(), &width, &height)) {
        return luaL_error(state, "Room:GetGridPath could not read the native grid dimensions");
    }
    // 越界（负数、或 >= W*H）：按**引擎自己对越界坐标的答案**（`Room::GetGridPath(int,int)`
    // 在参数越界时返回 0），而不是像 PC 的 Lua 那样直接按下标读、读进相邻内存。
    // 这条口径写进了 `api_deviation.cpp`（唯一残留的那条偏离）。
    const std::uint64_t cellCount = static_cast<std::uint64_t>(width) * height;
    if (index < 0 || static_cast<std::uint64_t>(index) >= cellCount) {
        lua_pushinteger(state, 0);
        return 1;
    }
    const std::uintptr_t room = CurrentRoomAddress();
    const std::uintptr_t address =
        room + kRoomGridPathArrayOffset + static_cast<std::uintptr_t>(index) * sizeof(std::int32_t);
    std::int32_t collision = 0;
    if (room == 0 || room > UINTPTR_MAX - kRoomGridPathArrayOffset - cellCount * sizeof(std::int32_t) ||
        !isaac::runtime::engine_memory::ReadAt(address, &collision, &IsEngineMemoryReadable)) {
        return luaL_error(state, "Room:GetGridPath could not read the native grid path table");
    }
    lua_pushinteger(state, static_cast<lua_Integer>(collision));
    return 1;
}

// `Room:GetDoor(int DoorSlot)` —— PC 返回那一格的 `GridEntityDoor`（没有门时返回 nil）。
//
// ★ 现状（2026-09-19 批次 046）：**方法存在、但恒返回 nil**（如实降级）。
//   为什么先这样：真机 `goodtripfixed/scripts/floor.lua:223` 报
//   `attempt to call a nil value (method 'GetDoor')` —— 那是"**方法根本不存在**"，
//   与"返回 nil"是两件事：PC 上这个方法的返回**本来就可以是 nil**（没有门的槽位），
//   模组是按 PC 写的、会判空；而"方法不存在"会让它的运行期回调每帧抛错、**整块功能被派发器摘掉**
//   （本项目最难查的形态）。所以第一步先让**形状**与 PC 一致。
//   取证完成前**不编造门对象**：PC 里 `GridEntityDoor` 带 `TargetRoomIndex`/`TargetRoomType`/
//   `Direction`/`IsOpen()`，编一份假门会让模组画出**错误的房间连通图**（传送会去错房间），
//   比"暂时没有门"更糟。取证路线见 `docs/改动日志-20260919.md` 046。
// `Room:GetDoor(slot)`（批次 078 起是真实现；046~077 是"恒返回 nil"的降级）。
//
// 为什么它是**传送能不能用**的关键：GoodTrip 的连通图完全建立在它之上
// （`floor.sweep_doors()` → `floor.linked()` → `rules.check_teleble()`）。返回 nil 时
// 连通图是空的，我们只能靠临时钉子 `AllowAnyRoom = true` 让传送可用 —— 而那个钉子的副作用
// 就是**能传送到没去过的房间**（用户实测反馈）。
//
// 取门路线（证据见 `runtime_constants.hpp` 的 `kRoomDoorGridIndexTableOffset` 那一段）：
//   ① `Room + 0xE70 + slot*4` = 该槽位门的**网格下标**（有符号；-1 或越界表示这个槽位没有门）；
//   ② `Room + 0x30` 的网格实体表取出 `GridEntity_Door*`；
//   ③ 包成 `DoorHandle`（同时记住槽位，`door.Position` 要用它问引擎）。
int RoomGetDoor(lua_State* state) {
    luaL_checkudata(state, 1, kRoomMetatable);
    if (lua_gettop(state) != 2 || !isaac::runtime::IsIntegerArgument(state, 2)) {
        return luaL_error(state, "Room:GetDoor expects a door slot");
    }
    const lua_Integer slot = lua_tointegerx(state, 2, nullptr);
    if (slot < kRoomDoorSlotMinimum || slot > kRoomDoorSlotMaximum) {
        // PC 语义：槽位非法 ⇒ 没有门（`GetDoorSlotPosition` 对越界槽位也返回 Zero）。
        lua_pushnil(state);
        return 1;
    }
    void* room = nullptr;
    if (ReadCurrentGameRoom(GameOwnerSlot(), &room) != GameRoomObservation::Success ||
        room == nullptr) {
        return luaL_error(state, "Room:GetDoor could not read the native Room state");
    }
    const std::uintptr_t roomAddress = isaac::runtime::engine_memory::AddressOf(room);
    // `Room + 0xE30 + slot*8` = **该槽位的门对象**（`Room::make_door` 存的就是这里）。
    // 比"先取网格下标（`+0xE70`）、再查网格实体表"短一步；那张网格下标表仍然有用
    // （`Room::GetDoorSlotPosition` 用它算坐标），但不是取门的最短路径。
    const std::uintptr_t entitySlot = roomAddress + kRoomDoorObjectTableOffset +
                                      static_cast<std::uintptr_t>(slot) * sizeof(std::uintptr_t);
    std::uintptr_t entity = 0;
    if (!isaac::runtime::engine_memory::ReadAt(entitySlot, &entity, &IsEngineMemoryReadable)) {
        lua_pushnil(state);
        return 1;
    }
    if (entity == 0) {
        lua_pushnil(state);
        return 1;
    }
    auto* handle = static_cast<LuaRuntime::DoorHandle*>(
        lua_newuserdata(state, sizeof(LuaRuntime::DoorHandle)));
    handle->entity = isaac::runtime::engine_memory::AsObject(entity);
    handle->slot = static_cast<std::int32_t>(slot);
    handle->reserved = 0;
    luaL_getmetatable(state, LuaRuntime::kGridEntityDoorMetatable);
    lua_setmetatable(state, -2);
    return 1;
}

// `GridEntity_Door` 的字段访问（`Room:GetDoor(slot)` 的返回值）。
//
// 形状：**先按门的字段答，答不上再落到 `GridEntity` 的方法表**（PC 里门同时是 `GridEntity`，
// `door:GetType()`/`door:GetVariant()` 都要能用）。实现在 `remaining_api.hpp` 里导出，
// 因为元表要在 `lua_runtime.cpp` 建。
//
// 只答**有证据**的字段（证据见 `runtime_constants.hpp` 的门族那一段）：
//   * `TargetRoomType` -> `+0x1A8`（`SetRoomTypes` 写、`IsTargetRoomArcade` 读）
//   * `Direction`      -> `+0x1AC`（`SetDirection` 写、`InitSubclass` 初始化成 -1）
//   * `Desc`           -> 一张**只含 Type/Variant 的表**（`+0x18`/`+0x10`）。PC 那边它是
//     `GridEntityDesc` 对象；这里给表是有意的降级，理由：GoodTrip 只用 `Desc.Variant`
//     （判断隐藏门），而 `GridEntityDesc` 的完整布局没有取证 —— 编一张假对象比给表更危险。
//   * `Position`       -> 问引擎（`Room::GetDoorSlotPosition(槽位)`，返回两个 float）
//   * `IsOpen()`       -> **方法**，调引擎的 `CanEnter()`（`(variant == 2) XOR 标志 bit4`）
//
// `TargetRoomIndex`(+0x30C) 与 `VarData`(+0x1C) 的偏移在批次 078 取证完成（证据见
// `runtime_constants.hpp` 的门族那一段），所以现在都返回真值。
int RoomGetGridEntity(lua_State* state) {
    luaL_checkudata(state, 1, kRoomMetatable);
    const int argumentCount = lua_gettop(state);
    if (argumentCount != 2 || !RoomGridIndexArgument(state, 2, nullptr)) {
        return luaL_error(state, "Room:GetGridEntity accepts one grid index");
    }
    std::uintptr_t level = 0;
    if (!ResolveCurrentLevel(&level) || level == 0) {
        return luaL_error(state, "Room:GetGridEntity could not read the native Level state");
    }
    // 网格实体表在 `Room + 0x30`（证据见 `kRoomGridEntityTableOffset`），按网格下标索引、
    // 每项一个 `GridEntity*`。下标越界/空项一律返回 nil（PC 语义："这里没有网格实体"）。
    void* room = nullptr;
    if (ReadCurrentGameRoom(GameOwnerSlot(), &room) != GameRoomObservation::Success ||
        room == nullptr) {
        return luaL_error(state, "Room:GetGridEntity could not read the native Room state");
    }
    const std::uintptr_t roomAddress = isaac::runtime::engine_memory::AddressOf(room);
    lua_Integer gridIndex = 0;
    if (!RoomGridIndexArgument(state, 2, &gridIndex) || gridIndex < 0) {
        return luaL_error(state, "Room:GetGridEntity accepts one grid index");
    }
    const std::uintptr_t slot = roomAddress + kRoomGridEntityTableOffset +
                                static_cast<std::uintptr_t>(gridIndex) * sizeof(std::uintptr_t);
    std::uintptr_t entity = 0;
    if (!isaac::runtime::engine_memory::ReadAt(slot, &entity, &IsEngineMemoryReadable)) {
        lua_pushnil(state);
        return 1;
    }
    if (entity == 0) {
        lua_pushnil(state);
        return 1;
    }
    auto* handle = static_cast<LuaRuntime::GridEntityHandle*>(
        lua_newuserdata(state, sizeof(LuaRuntime::GridEntityHandle)));
    handle->entity = isaac::runtime::engine_memory::AsObject(entity);
    luaL_getmetatable(state, LuaRuntime::kGridEntityMetatable);
    lua_setmetatable(state, -2);
    return 1;
}

//: 从实参拿"引擎网格实体地址"：**`GridEntity` 与 `GridEntity_Door` 两种元表都认**。
//:
//: 为什么必须有它（批次 078 的宿主门禁当场教出来的）：PC 里门**同时是** `GridEntity`，
//: 模组会写 `door:GetVariant()`；而我们给门的是自己的元表 ⇒ 用
//: `luaL_checkudata(state, 1, kGridEntityMetatable)` 会直接抛
//: "GridEntity expected"。两种句柄的**第一个成员都是实体指针**，所以按布局取是安全的。
void* GridEntityArgument(lua_State* state, int index) {
    if (void* raw = luaL_testudata(state, index, LuaRuntime::kGridEntityMetatable)) {
        return static_cast<LuaRuntime::GridEntityHandle*>(raw)->entity;
    }
    if (void* raw = luaL_testudata(state, index, LuaRuntime::kGridEntityDoorMetatable)) {
        return static_cast<LuaRuntime::DoorHandle*>(raw)->entity;
    }
    return nullptr;
}

// `GridEntity:GetVariant()`（批次 12）：读 `GridEntity + 0x10`（证据见 `kGridEntityVariantOffset`：
// 便便的 `InitSubclass`/`Update` 反复把该字段与 1000 比较，而便便 variant 正是 1000 起）。
int GridEntityGetVariant(lua_State* state) {
    if (lua_gettop(state) != 1) {
        return luaL_error(state, "GridEntity:GetVariant accepts no arguments");
    }
    void* entityPointer = GridEntityArgument(state, 1);
    if (entityPointer == nullptr) {
        return luaL_error(state, "GridEntity:GetVariant expects a grid entity");
    }
    const std::uintptr_t entity = isaac::runtime::engine_memory::AddressOf(entityPointer);
    std::uint32_t variant = 0;
    if (entity == 0 ||
        !isaac::runtime::engine_memory::ReadAt(entity + kGridEntityVariantOffset, &variant,
                                               &IsEngineMemoryReadable)) {
        lua_pushnil(state);
        return 1;
    }
    lua_pushinteger(state, static_cast<lua_Integer>(variant));
    return 1;
}

// `GridEntity:GetType()`：读 `GridEntity + 0x18`（`GridEntity::Init(eGridEntityType)` 的第一条存值）。
int GridEntityGetType(lua_State* state) {
    if (lua_gettop(state) != 1) {
        return luaL_error(state, "GridEntity:GetType accepts no arguments");
    }
    void* entityPointer = GridEntityArgument(state, 1);
    if (entityPointer == nullptr) {
        return luaL_error(state, "GridEntity:GetType expects a grid entity");
    }
    const std::uintptr_t entity = isaac::runtime::engine_memory::AddressOf(entityPointer);
    std::uint32_t type = 0;
    if (entity == 0 ||
        !isaac::runtime::engine_memory::ReadAt(entity + kGridEntityTypeOffset, &type,
                                               &IsEngineMemoryReadable)) {
        lua_pushnil(state);
        return 1;
    }
    lua_pushinteger(state, static_cast<lua_Integer>(type));
    return 1;
}

// `GridEntity:GetRNG()`（批次 13，2026-09-16）：PC 文档 `GridEntity.md:38` 返回该网格实体自己的
// `RNG`（`RNG.md:18` 也把它列进 "RNG 从哪里来" 的清单）。EID 的用法是
// `features/eid_itemprediction.lua:120` 的 `spikes:GetRNG():GetSeed()` —— 拿血契尖刺当前的种子，
// 再用自己的 RNG 步骤推出下一次结果。
//
// 偏移（`GridEntity + 0x30`）与 RNG 内部布局（16 字节、种子在头 4 字节）的证据见
// `runtime_constants.hpp` 的 `kGridEntityRngOffset` / `kRngObjectSize`。
//
// ★ 这里交回 Lua 的是**调用瞬间那 16 字节的一份快照**，不是引擎里那个 RNG 的活引用（PC 返回引用）。
//   取舍的理由：网格实体会随时被销毁（石头炸掉、尖刺消耗、换房间重建），而本句柄只存实体地址、
//   拿不到网格下标（`EntityHandle`/`SpriteHandle` 那种"每次访问重新解析并校验"的做法在这里无从
//   落地），让 Lua 长期握着一个"引擎对象内部成员"的指针就等于把"写已释放内存"的口子开给模组。
//   读语义上快照与引用逐值相同（`GetSeed`/`Next`/`RandomInt` 在取到的那一刻完全一致），
//   差别只在"从返回对象上改状态会不会影响引擎" —— 已按项目规矩登记为偏离（见 `api_deviation.cpp`
//   里 `0x0E010054` 那条），不是悄悄换掉。
int GridEntityGetRng(lua_State* state) {
    if (lua_gettop(state) != 1) {
        return luaL_error(state, "GridEntity:GetRNG accepts no arguments");
    }
    void* entityPointer = GridEntityArgument(state, 1);
    if (entityPointer == nullptr) {
        return luaL_error(state, "GridEntity:GetRNG expects a grid entity");
    }
    const std::uintptr_t entity = isaac::runtime::engine_memory::AddressOf(entityPointer);
    if (entity == 0 || entity > UINTPTR_MAX - kGridEntityRngOffset ||
        !IsEngineMemoryReadable(entity + kGridEntityRngOffset, kRngObjectSize)) {
        lua_pushnil(state);
        return 1;
    }
    auto* rng = static_cast<LuaRuntime::RngHandle*>(
        lua_newuserdata(state, sizeof(LuaRuntime::RngHandle)));
    *rng = {};
    // 上面那次判定覆盖了整段 `kRngObjectSize` 字节 ⇒ 这里只取值（L1 `LoadVerifiedAt`），
    // 且按 `storage` 的静态类型整段拷贝：`sizeof(std::array<...>)` 与 `kRngObjectSize` 相等。
    static_cast<void>(isaac::runtime::engine_memory::LoadVerifiedAt(
        entity + kGridEntityRngOffset, 0, &rng->storage));
    luaL_getmetatable(state, LuaRuntime::kRngMetatable);
    lua_setmetatable(state, -2);
    return 1;
}


// `Room:GetRenderScrollOffset()`（PC 文档 `Room.md:473`，返回 `const Vector`）：
// 房间渲染的滚动偏移。EID 用它把世界坐标换算到屏幕坐标。
//
// 偏移 `+0x1938` 的证据（`tools/layout_tables/room.json`）：引擎自己的
// `Room::WorldToScreenPosition` 里先 `mov w8, #0x1938`、再 `add x1, x19, x8`，
// 把这个字段的**地址**交给 `Vector2::operator+` —— 也就是"世界→屏幕"要加上的那个向量。
// `build_layout_table.py --verify` 会重新反汇编核对这条证据。
int RoomGetRenderScrollOffset(lua_State* state) {
    luaL_checkudata(state, 1, kRoomMetatable);
    if (lua_gettop(state) != 1) {
        return luaL_error(state, "Room:GetRenderScrollOffset accepts no arguments");
    }
    void* room = nullptr;
    if (ReadCurrentGameRoom(GameOwnerSlot(), &room) != GameRoomObservation::Success ||
        room == nullptr) {
        return luaL_error(state,
                          "Room:GetRenderScrollOffset could not read the native Room state");
    }
    const std::uintptr_t address = isaac::runtime::engine_memory::AddressOf(room);
    float x = 0.0F;
    float y = 0.0F;
    const std::uintptr_t scrollOffset = address + layout::kRoomRenderScrollOffsetOffset;
    if (!IsEngineMemoryReadable(scrollOffset, sizeof(x) + sizeof(y))) {
        return luaL_error(state,
                          "Room:GetRenderScrollOffset could not read the native Room state");
    }
    // 上面那次判定覆盖了整段 8 字节 ⇒ 这两个 float 只取值、不重复问内核（L1 `LoadVerifiedAt`）。
    static_cast<void>(isaac::runtime::engine_memory::LoadVerifiedAt(scrollOffset, 0, &x));
    static_cast<void>(isaac::runtime::engine_memory::LoadVerifiedAt(scrollOffset, 1, &y));
    // 每次返回**新的** `Vector` userdata：别名会让 `room:GetRenderScrollOffset().X = 1`
    // 这类写法改到下一次读取的结果上（与 `Entity.Position` 同一口径）。
    auto* vector = static_cast<LuaRuntime::VectorHandle*>(
        lua_newuserdata(state, sizeof(LuaRuntime::VectorHandle)));
    vector->x = x;
    vector->y = y;
    luaL_getmetatable(state, LuaRuntime::kVectorMetatable);
    lua_setmetatable(state, -2);
    return 1;
}

// `Room:WorldToScreenPosition(Vector)`（批次 10）：把世界坐标换算成屏幕坐标。
// PC 文档 `Room.md:974`，EID 用它把实体位置画到屏幕上。
//
// **换算方式直接来自引擎自己的实现**（`Room::WorldToScreenPosition @ 0x489354` 的反汇编）：
//   `GetRenderPosition(世界坐标, true) + Room.RenderScrollOffset + Game.ToScreenAdjust`
// 三处偏移/入口的证据见 `runtime_constants.hpp` 里那三个常量各自的注释。
//
// 失败一律报 Lua 错误（PC 返回 Vector，编一个 (0,0) 会让 Mod 把东西画到左上角）。
int RoomGetWorldToScreenPosition(lua_State* state) {
    luaL_checkudata(state, 1, kRoomMetatable);
    if (lua_gettop(state) != 2) {
        return luaL_error(state, "Room:WorldToScreenPosition expects a Vector");
    }
    auto* input = static_cast<LuaRuntime::VectorHandle*>(
        luaL_testudata(state, 2, LuaRuntime::kVectorMetatable));
    if (input == nullptr) {
        return luaL_error(state, "Room:WorldToScreenPosition expects a Vector");
    }
    void* room = nullptr;
    if (ReadCurrentGameRoom(GameOwnerSlot(), &room) != GameRoomObservation::Success ||
        room == nullptr) {
        return luaL_error(state, "Room:WorldToScreenPosition could not read the native Room state");
    }
    float screen[2] = {input->x, input->y};
    bool rendered = false;
#if !defined(__SWITCH__)
    // 宿主：没有引擎映像，用注入的实现（与 `HasCollectible` 的宿主钩子同一形态）。
    if (LuaRuntime::GetRenderPositionHostFunction() != nullptr) {
        LuaRuntime::GetRenderPositionHostFunction()(&input->x, screen, true);
        rendered = true;
    }
#else
    rendered = CallVectorEngineMethod(LuaRuntime::GetRenderPositionThunk(),
                                      kGetRenderPositionStubExpectedBytes, &input->x, screen, true);
#endif
    if (!rendered) {
        return luaL_error(state, "Room:WorldToScreenPosition is unavailable in this build");
    }
    // 再加上房间与 Game 各自那一份调整量（同一个函数里的两条 `Vector2::operator+`）。
    const std::uintptr_t roomAddress = isaac::runtime::engine_memory::AddressOf(room);
    const std::uintptr_t roomScroll = roomAddress + layout::kRoomRenderScrollOffsetOffset;
    std::uintptr_t game = 0;
    if (ResolveCurrentLevel(&game) == false || game == 0) {
        return luaL_error(state, "Room:WorldToScreenPosition could not read the native Game state");
    }
    const std::uintptr_t gameAdjust = game + kGameToScreenAdjustOffset;
    if (!IsEngineMemoryReadable(roomScroll, sizeof(float) * 2) ||
        !IsEngineMemoryReadable(gameAdjust, sizeof(float) * 2)) {
        return luaL_error(state, "Room:WorldToScreenPosition could not read the native state");
    }
    float roomX = 0.0F;
    float roomY = 0.0F;
    float gameX = 0.0F;
    float gameY = 0.0F;
    // 两处判定各自覆盖一对 float（8 字节）⇒ 四个分量只取值、不重复问内核（L1 `LoadVerifiedAt`）。
    static_cast<void>(isaac::runtime::engine_memory::LoadVerifiedAt(roomScroll, 0, &roomX));
    static_cast<void>(isaac::runtime::engine_memory::LoadVerifiedAt(roomScroll, 1, &roomY));
    static_cast<void>(isaac::runtime::engine_memory::LoadVerifiedAt(gameAdjust, 0, &gameX));
    static_cast<void>(isaac::runtime::engine_memory::LoadVerifiedAt(gameAdjust, 1, &gameY));
    auto* result = static_cast<LuaRuntime::VectorHandle*>(
        lua_newuserdata(state, sizeof(LuaRuntime::VectorHandle)));
    result->x = screen[0] + roomX + gameX;
    result->y = screen[1] + roomY + gameY;
    luaL_getmetatable(state, LuaRuntime::kVectorMetatable);
    lua_setmetatable(state, -2);
    return 1;
}


int ItemPoolGetLastPool(lua_State* state) {
    luaL_checkudata(state, 1, kItemPoolMetatable);
    if (lua_gettop(state) != 1) {
        return luaL_error(state, "ItemPool:GetLastPool accepts no arguments");
    }
    void* itemPool = nullptr;
    if (ReadCurrentGameItemPool(GameOwnerSlot(), &itemPool) != GameItemPoolObservation::Success) {
        return luaL_error(state, "ItemPool:GetLastPool could not read the native ItemPool state");
    }
    const std::uintptr_t address = isaac::runtime::engine_memory::AddressOf(itemPool);
    std::uint32_t lastPool = 0;
    if ((address & (alignof(std::uint32_t) - 1)) != 0 ||
        address > UINTPTR_MAX - kItemPoolLastPoolOffset ||
        !isaac::runtime::engine_memory::ReadAt(address + kItemPoolLastPoolOffset, &lastPool,
                                               &IsEngineMemoryReadable)) {
        return luaL_error(state, "ItemPool:GetLastPool could not read the last pool");
    }
    lua_pushinteger(state, static_cast<lua_Integer>(lastPool));
    return 1;
}

int ItemPoolGetCollectible(lua_State* state) {
    luaL_checkudata(state, 1, kItemPoolMetatable);
    const int argumentCount = lua_gettop(state);
    if ((argumentCount != 4 && argumentCount != 5) || !isaac::runtime::IsIntegerArgument(state, 2) ||
        !isaac::runtime::IsIntegerArgument(state, 4) || (argumentCount == 5 && !isaac::runtime::IsIntegerArgument(state, 5))) {
        return luaL_error(state,
                          "ItemPool:GetCollectible accepts poolType, decrease, seed and optional defaultItem");
    }
    const lua_Integer poolType = lua_tointegerx(state, 2, nullptr);
    const lua_Integer seed = lua_tointegerx(state, 4, nullptr);
    const lua_Integer defaultItem = argumentCount == 5 ? lua_tointegerx(state, 5, nullptr) : 0;
    if (poolType < 0 || static_cast<std::uint64_t>(poolType) > std::numeric_limits<std::uint32_t>::max() ||
        seed < 0 || static_cast<std::uint64_t>(seed) > std::numeric_limits<std::uint32_t>::max() ||
        defaultItem < 0 || static_cast<std::uint64_t>(defaultItem) > std::numeric_limits<std::uint32_t>::max()) {
        return luaL_error(state, "ItemPool:GetCollectible integer arguments are outside uint32 range");
    }
    void* itemPool = nullptr;
    if (ReadCurrentGameItemPool(GameOwnerSlot(), &itemPool) != GameItemPoolObservation::Success) {
        return luaL_error(state, "ItemPool:GetCollectible could not read the native ItemPool state");
    }
    const std::uintptr_t method = ItemPoolGetCollectibleThunk();
    if (!ValidateItemPoolGetCollectibleBinding(method)) {
        return luaL_error(state, "ItemPool:GetCollectible native bindings are unavailable");
    }
    using GetCollectibleFn = std::uint32_t (*)(void*, std::uint32_t, std::uint32_t, std::uint32_t,
                                               std::uint32_t);
    const auto result = isaac::runtime::engine_call::AsFunction<GetCollectibleFn>(method)(
        itemPool, static_cast<std::uint32_t>(poolType), static_cast<std::uint32_t>(seed),
        lua_toboolean(state, 3) ? 0u : 1u, static_cast<std::uint32_t>(defaultItem));
    lua_pushinteger(state, static_cast<lua_Integer>(result));
    return 1;
}

// `ItemPool:IsPillIdentified(PillColor)`（批次 13，2026-09-16）：PC 文档 `ItemPool.md:89`
// 的签名是 `boolean IsPillIdentified(PillColor PillColor)`。EID 用它决定"没识别过的药丸
// 要不要泄底"（`main.lua:1649`、`eid_itemprediction.lua:339`、`eid_holdmapdesc.lua:575`）。
//
// 底座是 `ItemPool + 0xa68 + color` 这个**每个颜色一字节**的"已识别"表，紧挨在
// `ItemPool + 0xa2c` 的 15 项药丸效果表后面（15×4 = 0x3C，0xa2c + 0x3C = 0xa68 —— 算术自洽）。
// 完整证据链见 `runtime_constants.hpp` 的 `kItemPoolPillIdentifiedOffset`：
//   * HUD 用它决定显示药丸真名还是 `#QUESTION_MARKS_NAME`（"???"）；
//   * 存档恢复（`ItemPool::RestoreGameState`）与重掷药丸效果（`ItemPool::RerollPillEffect`）都写它。
//
// 两条边界口径（都刻意与"照抄引擎"不同，写在这里免得以后当成 bug）：
//   * 颜色先按 `PILL_COLOR_MASK`（0x7ff）掩码 —— 引擎自己就是这么做的
//     （`ItemPool::GetPillEffect` 的第一条指令就是 `and w8, w1, #0x7ff`），马匹药丸把高位置 1
//     之后再掩码取本色；
//   * 掩码后 >= `NUM_PILLS`(15) 或参数为负 ⇒ 直接回答"没识别"，**不报错**。PC 那条 Lua 访问器
//     会按下标直接读（越界读进 `ItemPool` 的其它字段、得到一个没有语义的字节）；我们不复刻越界读，
//     也不抛错 —— 抛错会摘掉整条描述回调（本项目已多次踩过），而"没识别"对越界输入是安全的保守答案。
int ItemPoolIsPillIdentified(lua_State* state) {
    luaL_checkudata(state, 1, kItemPoolMetatable);
    if (lua_gettop(state) != 2 || !isaac::runtime::IsIntegerArgument(state, 2)) {
        return luaL_error(state, "ItemPool:IsPillIdentified accepts one pill colour");
    }
    const lua_Integer colour = lua_tointegerx(state, 2, nullptr);
    if (colour < 0) {
        lua_pushboolean(state, 0);
        return 1;
    }
    // **只掩码、不判"高位是否干净"**：巨大药丸（马匹药丸）的颜色就是"本色 | 0x800"，
    // 引擎自己也是先 `and w8, w1, #0x7ff` 再按下标取表（见 `ItemPool::GetPillEffect`），
    // 所以这里必须与它同口径 —— 否则 `IsPillIdentified(3 | 0x800)` 会错答 false。
    const std::uint32_t masked = static_cast<std::uint32_t>(colour) & kPillColorMask;
    if (masked >= kPillColorCount) {
        lua_pushboolean(state, 0);
        return 1;
    }
    void* itemPool = nullptr;
    if (ReadCurrentGameItemPool(GameOwnerSlot(), &itemPool) != GameItemPoolObservation::Success) {
        return luaL_error(state,
                          "ItemPool:IsPillIdentified could not read the native ItemPool state");
    }
    const std::uintptr_t address = isaac::runtime::engine_memory::AddressOf(itemPool);
    std::uint8_t identified = 0;
    if (address == 0 || address > UINTPTR_MAX - kItemPoolPillIdentifiedOffset ||
        !isaac::runtime::engine_memory::ReadAt(address + kItemPoolPillIdentifiedOffset + masked,
                                               &identified, &IsEngineMemoryReadable)) {
        return luaL_error(state, "ItemPool:IsPillIdentified could not read the pill state");
    }
    lua_pushboolean(state, identified != 0 ? 1 : 0);
    return 1;
}

// --- 地基二期（2026-09-15）：`RoomDescriptor` 与它的三件套 API -----------------------
//
// 字段偏移**全部来自布局表 + 真机行为验证**（`tools/layout_tables/room_descriptor.json`，
// 每条带可复核证据），不是从 PC 版抄的：
//
//   描述符数组：内联在 Level(=Game) 对象里，基址 `Level + 0x18`、步长 `0x100`、
//              元素个数在 `Level + 0x21510`（真机实测 11 个已分配槽位，ListIndex 恰好 0..10）；
//   `+0x00` GridIndex（网格下标）、`+0x04` SafeGridIndex、`+0x08` ListIndex、
//   `+0x10` Data（指向房间配置，其中 `Data+0x08` 是 Type）、
//   `+0x48` DisplayFlags（小地图可见性位掩码，批次 047 升为 confirmed）、
//   `+0x4c` VisitedCount、`+0x50` Clear/Flags。
//
// **只暴露已 confirmed 的字段**：未确认的（例如 `Data.Variant`）
// 一律返回 nil，并按项目规矩在文档/台账里标为未满足 —— 读错字段比读不到更糟（会给出错误内容）。
//
// `Level:GetRoomByIdx` 的定位方式：**扫描数组找 `+0x00 == 目标索引`**。
// 引擎自己那段"找起始房间"的循环（`0x3dc624`）也是扫数组；而 `Level + 0x2d18` 那张表
// 经真机验证**不是"索引→槽号"**（索引 97 读出槽号 6，可 slot6 是另一个房间），所以不依赖它。
namespace {

//: 描述符数组的几何（与布局表一致；改动必须同时改表并由 `--verify` 复核）。
constexpr std::uintptr_t kDescriptorArrayBase = 0x18;
constexpr std::uintptr_t kDescriptorStride = 0x100;
constexpr std::uintptr_t kDescriptorCountOffset = 0x21510;
//: 未分配槽位的 `+0x00` 是 0xFFFFFFFF（真机实测：11 号槽位起全是它）。
constexpr std::uint32_t kUnallocatedGridIndex = 0xFFFFFFFFu;
//: 引擎自己的"这一格没有房间"表示法就是 **-1**（真机实测，2026-09-19）：
//: 未分配槽位的 `+0x00`（GridIndex）与 `+0x04`（SafeGridIndex）都读成 `0xFFFFFFFF`。
//: ⇒ 我们**查不到当前房间时也要给 -1，不能给 nil**：模组普遍把这两个值当数字用
//: （GoodTrip 的 `scripts/floor.lua:218-220` 直接拿 `SafeGridIndex` 当表键
//:  ⇒ `link[nil]` 报 "table index is nil"，整条 `MC_POST_UPDATE` 回调每帧被打断）。
constexpr std::int32_t kAbsentRoomGridIndex = -1;
//: `Level + 0x2d18`：**引擎自己的"网格下标 → 槽位号"表**（int32，每个维度 169 项）。
//:
//: 证据（固定 NRO，`Level::GetRoomByIdx(int,int)` @ `0x3dc5b0` 起）：
//:   `mov w9, #0xa9`（169）→ `madd w9, w10, w9, w1`（= 维度×169 + 下标）→
//:   `add x9, x8, w9, uxtw #2` → `movk w10, #0x2, lsl #16`（0x2d18）→
//:   `ldrsw x9, [x9, x10]`（**有符号**取槽号）→ `add x8, x8, x9, lsl #8` → `add x8, x8, #0x18`
//:   ⇒ `描述符 = Level + 0x18 + 槽号*0x100`，槽号为负时返回引擎自己的"空描述符"。
//: `Level::GetCurrentRoomDesc()` @ `0x3dc684` 就是把 `+0x21558`/`+0x21560` 两个字段
//: 喂给它 —— 所以这就是引擎解析"当前房间"的**唯一**路径。
//: 我们以前用"扫描 `+0x00 == 下标`"代替它（见 `FindDescriptorByGridIndex` 的注释），
//: 那条路在多格房间上会**找不到**（`+0x21558` 是"从哪一格进去的"，PC 文档
//: `RoomDescriptor.md:193` 明说它与 `SafeGridIndex` 不是一回事）。
constexpr std::uintptr_t kDescriptorGridSlotTableOffset = 0x2D18;
constexpr std::uint32_t kDescriptorGridsPerDimension = 169;
constexpr std::uint32_t kDescriptorMaximumDimension = 2;
//: 描述符内部偏移。
constexpr std::uintptr_t kGridIndexOffset = 0x00;
constexpr std::uintptr_t kSafeGridIndexOffset = 0x04;
constexpr std::uintptr_t kListIndexOffset = 0x08;
constexpr std::uintptr_t kDataOffset = 0x10;
constexpr std::uintptr_t kVisitedCountOffset = 0x4C;
//: `+0x48` 是 PC 的 `RoomDescriptor.DisplayFlags`：**小地图可见性位掩码**
//: （位0 = Visible 可见、位1 = Room Shadow 房间阴影、位2 = Show Icon 显示图标）。
//: 2026-09-19 批次 047 升为 confirmed，两条独立锚点：
//:   * **静态**：引擎自己的 `Level::try_display_room`（函数名即语义："尝试让房间显示"）
//:     三处读写这一格 —— `0x3d923c` 读后 `mov w22,#0x5`+`orr` 置**位0|位2**；
//:     `0x3d9318` 读后 `orr w8,w8,#0x3` 置**位0|位1**；`0x3d95fc` 同前。
//:     两种掩码（0x3 / 0x5）与 PC 文档 `RoomDescriptor.md:66` 的
//:     `1<<0 Visible` / `1<<1 Room Shadow` / `1<<2 Show Icon` **逐位吻合**，
//:     且"位1 有独立含义"排除了"它是布尔"的可能。
//:   * **真机**：`dist/room-probe-A3.json → -C.json` 同一间房（网格 72）从 0 变成 5，
//:     正好是"它在地图上变得可见"的那一刻；同一时刻它的 `VisitedCount`=0、`Flags`=0x0
//:     ⇒ 这一格与"清房/访问次数"互不影响，只跟可见性走。
//: 证据与复核命令见 `tools/layout_tables/room_descriptor.json` 的 DisplayFlags 行。
constexpr std::uintptr_t kDisplayFlagsOffset = 0x48;
//: `+0x50` 是 PC 的 `RoomDescriptor.Flags`：**32 位位掩码**，`Clear` 只是它的**第 0 位**。
//: 2026-09-16 静态取证（`Repentance.nro`，函数@文件偏移）：
//:   * 整字读写：`GameState::read_Room @ 0x36FCA4`（`0x36FFC0 add x1,x23,#0x50` + `mov w2,#0x4`
//:     ⇒ 按 4 字节读存档；旧存档格式 <0x3f 时用六次 `ldr/orr #1|2|4|8|0x10|0x20/str` 把六个布尔
//:     **合成低六位**，正好等于 PC 的 FLAG_CLEAR/PRESSURE_PLATES_TRIGGERED/SACRIFICE_DONE/
//:     CHALLENGE_DONE/SURPRISE_MINIBOSS/HAS_WATER）；`GameState::write_Room @ 0x368688` 反着写回。
//:   * 高位另有独立用途：`Level::CanOpenChallengeRoom [email protected]` 测 bit3、
//:     `Level::try_display_room @ 0x3D95F4` 测 bit10、`Room::SetRotgutCleared @ 0x46AC70` 置 bit16
//:     —— 一个布尔字段不可能容纳 `1<<16`，所以它只能是位掩码。
//:   * 真机佐证：`dist/room-probe-C.json → room-probe-D.json` 同一宝箱房清敌后该字段 0→1（= FLAG_CLEAR）。
constexpr std::uintptr_t kFlagsOffset = 0x50;
//: 兼容旧名（`Clear` = bit0）。**语义收窄**：以前这里用"非零即真"，会把 bit3/bit10/bit16 也算成
//: 清房；现在按 PC 契约只看 bit0。
constexpr std::uintptr_t kClearOffset = kFlagsOffset;
constexpr std::uint32_t kRoomFlagClear = 1u << 0;
//: `Data` 指向的房间配置里，Type 在 +0x8（布局表 confirmed）。
constexpr std::uintptr_t kRoomConfigTypeOffset = 0x08;
//: `RoomConfig::Room.Shape`（PC：`RoomShape` 枚举，1..12）在 `Data + 0x5C`。
//: 2026-09-16 静态取证：`RoomConfig::parse_room_node @ 0x48F480` 在 `0x48F6EC str w0,[x20,#0x5c]`
//: （XML 属性名就是 `"shape"`；相邻 `strb …, #0x5b` 是 height、`#0x5a` 是 width ⇒ **宽高是 1 字节、
//: 而 +0x5C 是 4 字节**，这也是"它不可能是 Width"的反证）；`RoomConfig::read_room @ 0x491774`
//: `str w8,[x20,#0x5c]!`（二进制房间表加载器）；`Room::Init @ 0x45F97C` 读它并
//: `sub w8,w8,#9; cmp w8,#3; b.hi`（只有 9..12 四个 L 形走特判）。
constexpr std::uintptr_t kRoomConfigShapeOffset = 0x5C;
//: `RoomDescriptor.Data` 暴露给 Lua 的字段表。⚠️ 用"名字 → 偏移"的**静态表**形态，
//: 不用零散的 `lua_setfield` —— 枚举工具（`tools/eid_api_gap_report.py`）靠这种形态认
//: "这个字段已经实现了"；写成散装 setfield 会让它继续把已实现的字段报成缺口（2026-09-16 实测踩到）。
constexpr struct RoomConfigRoomField {
    const char* name;
    std::uintptr_t offset;
} kRoomConfigRoomFields[] = {
    {"Type", kRoomConfigTypeOffset},
    {"Shape", kRoomConfigShapeOffset},
};
//: 数组元素个数上限：3 个维度 × 169 个房间 + 少量特殊槽位，实际远小于 512。
constexpr std::uint32_t kDescriptorMaximumCount = 512;

// ============================================================================
// `RoomDescriptor.Data` 读不出来时的**现场记账**（批次 071，2026-09-19）
// ============================================================================
//
// 为什么要有它：真机上 `crd.Data` 返回 nil 让 GoodTrip 的 `MC_POST_NEW_ROOM` 回调每次都崩
// （`control.lua:339`），而"为什么会是 nil"只能靠猜（是描述符不对？是贪婪房没有配置对象？）。
// 这几个量把现场留下来：**发生了多少次**、以及最后一次的描述符头三个字与它的地址低位 ——
// 下次读数就能分清"槽位没填（GridIndex = -1）"与"房间确实没有配置对象"。
// 与批次 069 同一种做法：全部住 bss，加多少代码都不变；读数工具按 `extern "C"` 名字直读。

void RecordRoomDescriptorDataMiss(std::uintptr_t descriptor) noexcept {
    g_IsaacRoomDescDataMisses.fetch_add(1, std::memory_order_relaxed);
    if (descriptor == 0) {
        // **空句柄**：没有现场可记（地址本来就是 0），只记次数。
        //
        // ★ 这一条不是"防御性编程"，是宿主测试当场用 SIGSEGV 教出来的：
        // `IsEngineMemoryReadable` 在**宿主**构建里没有映射表可查 —— 地址非 0、长度非 0、
        // 不回绕就返回 true（见 `isaac_api.cpp` 的那个函数）。于是 `keep(+0x04)` 会去
        // `memcpy` 地址 4 ⇒ 崩。设备侧有 `svcQueryMemory`，不会这样；但**宿主门禁会**，
        // 而门禁崩掉就等于这条路径在 CI 里从来没有被验证过。所以这里显式挡住 0。
        g_IsaacRoomDescDataGridIndex.store(0, std::memory_order_relaxed);
        g_IsaacRoomDescDataSafeGridIndex.store(0, std::memory_order_relaxed);
        g_IsaacRoomDescDataListIndex.store(0, std::memory_order_relaxed);
        g_IsaacRoomDescDataDescriptorLow.store(0, std::memory_order_relaxed);
        return;
    }
    const auto keep = [descriptor](std::uintptr_t offset, std::atomic<std::uint32_t>& slot) {
        std::uint32_t value = 0;
        // 判定 + 取值同一次调用（L1 `ReadAt`）；失败时 `value` 保留初值 0，与原来那条 if 同义。
        static_cast<void>(isaac::runtime::engine_memory::ReadAt(descriptor + offset, &value,
                                                               &IsEngineMemoryReadable));
        slot.store(value, std::memory_order_relaxed);
    };
    keep(kGridIndexOffset, g_IsaacRoomDescDataGridIndex);
    keep(kSafeGridIndexOffset, g_IsaacRoomDescDataSafeGridIndex);
    keep(kListIndexOffset, g_IsaacRoomDescDataListIndex);
    g_IsaacRoomDescDataDescriptorLow.store(static_cast<std::uint32_t>(descriptor),
                                           std::memory_order_relaxed);
}

// `Level` 就内嵌在 `Game` 起始处，所以解析链与 `ReadGameCurses` 逐字相同：
//   `GameOwnerSlot()` 是**槽的地址**（指针变量）→ 解一次得 owner → 再解一次才是 `Game*`。
// ★ 第一版直接把 `GameOwnerSlot()` 当 Level 用，少解了两层 —— 那会去读模块里的代码字节
// （真机探针上踩过同一个坑：`g_Game` 槽里存的不是对象本身）。
std::uintptr_t ResolveLevelForDescriptor() noexcept {
    const std::uintptr_t slot = GameOwnerSlot();
    std::uintptr_t owner = 0;
    if (slot == 0 ||
        !isaac::runtime::engine_memory::ReadAt(slot, &owner, &IsEngineMemoryReadable)) {
        return 0;
    }
    std::uintptr_t level = 0;
    if (owner == 0 ||
        !isaac::runtime::engine_memory::ReadAt(owner, &level, &IsEngineMemoryReadable)) {
        return 0;
    }
    return level;
}

// --- 056：`RoomDescriptor.Data.Spawns` 的**明确空容器** --------------------------
//
// **为什么必须有这个形状**：GoodTrip 的绘制路径（`widget.lua:378` 起）在读
// `rd.Data.Spawns` 之后立刻用 `spawns.Size` 与 `spawns:Get(j):PickEntry(0)`；
// 这个字段**不存在**（返回 nil）时那两个循环每帧抛
// `widget.lua:391: attempt to index a nil value (local 'spawns')`，
// 整条 `MC_POST_RENDER` 回调在"画小地图窗口"之前就被打断 ——
// 真机症状就是"按住地图键，屏幕上什么都不出现"（2026-08-19~09-19 反复复现的那一类）。
//
// **本轮给的是空容器，不是真值**：真值要走
// ① `RoomConfig::Room` 里那个 `Spawns` vector 的 begin/end 偏移（引擎没有访问器符号，
//    只能从消费者反推：例如 `Room::FixSpawnEntry(RoomConfig::Entry&, u32, u32)` @ `0x452948`），
// ② `RoomConfig::Entry` 的 `Type`/`Variant` 偏移，
// ③ `RoomConfig::Spawn::PickEntry(float)` 的返回值包装（引擎符号在 `0x494910`，签名已登记）。
// 三条都还没取证，**所以这里不编造条目**：`Size = 0`、`Get` 恒 nil ⇒ 模组那些
// `for j = 0, spawns.Size - 1` 直接跳过。
//
// **偏离后果（写清楚）**：矿井/下水道/深坑等房间的"特殊图标"（GoodTrip 的 `iid` 图标）
// 不会显示；传送、连通图、小地图本身都不受影响（它们读的是别的字段）。
//
// 表的取得方式：**每个 Lua 状态一份、存在注册表里**（`lua_rawgetp`），
// 不放进 C++ 静态变量 —— Lua 状态在每次模组重载时会被关掉重建，存 C++ 静态会拿到悬垂引用。
int EmptySpawnListGet(lua_State* state) {
    // PC 的 `RoomConfigSpawns` 是 ArrayProxy：空表上任何 `Get(i)` 都取不到元素。
    // 真值取证后这里要返回 `RoomConfig_Spawn` 对象（见上面的路线）。
    lua_pushnil(state);
    return 1;
}

void PushEmptySpawnList(lua_State* state) {
    static const char kRegistryKey = 0;   // 变量地址即注册表键，仅本 TU 使用
    lua_rawgetp(state, LUA_REGISTRYINDEX, &kRegistryKey);
    if (lua_istable(state, -1)) {
        return;
    }
    lua_pop(state, 1);
    lua_createtable(state, 0, 2);
    lua_pushinteger(state, 0);
    lua_setfield(state, -2, "Size");
    lua_pushcfunction(state, &EmptySpawnListGet);
    lua_setfield(state, -2, "Get");
    lua_pushvalue(state, -1);
    lua_rawsetp(state, LUA_REGISTRYINDEX, &kRegistryKey);
}

bool ReadDescriptorU32(std::uintptr_t descriptor, std::uintptr_t offset,
                       std::uint32_t* value) noexcept {
    if (value == nullptr || descriptor == 0 || descriptor > UINTPTR_MAX - offset) {
        return false;
    }
    // 判定 + 取值同一次调用（L1 `ReadAt`）：先可读再取值，失败时不写出参。
    return isaac::runtime::engine_memory::ReadAt(descriptor + offset, value,
                                                 &IsEngineMemoryReadable);
}

std::uintptr_t DescriptorAddress(std::uintptr_t level, std::uint32_t slot) noexcept {
    return level + kDescriptorArrayBase + static_cast<std::uintptr_t>(slot) * kDescriptorStride;
}

//: 房间数组里当前有多少个槽位（引擎自己用它做扫描边界）。
std::uint32_t DescriptorCount(std::uintptr_t level) noexcept {
    std::uint32_t count = 0;
    if (level == 0 || level > UINTPTR_MAX - kDescriptorCountOffset ||
        !isaac::runtime::engine_memory::ReadAt(level + kDescriptorCountOffset, &count,
                                               &IsEngineMemoryReadable)) {
        return 0;
    }
    // 上限只用来兜住"读到垃圾值"的情形：3 个维度 × 169 个房间 + 少量特殊槽位，实际远小于 512。
    return count > kDescriptorMaximumCount ? kDescriptorMaximumCount : count;
}

//: 引擎自己的定位法（`Level::GetRoomByIdx` 的那条链）：`槽号 = map[维度×169 + 下标]`。
//:
//: ★ 为什么在扫描之外还要这一条（2026-09-19 真机定位）：`Level + 0x21558` 是
//: **进入当前房间时的那一格**（PC 文档 `RoomDescriptor.md:193`：`Level:GetCurrentRoomIndex()`
//: 给的是"房间是从哪一格进去的"，与 `SafeGridIndex` 不是一回事）。多格房间（2x2 / L 形 / 1x2）
//: 里那个值**不等于该房间描述符的 `GridIndex`** ⇒ 只按"扫描 `+0x00 == 下标`"会**找不到**，
//: 于是 `Level:GetCurrentRoomDesc()` 返回空句柄、`SafeGridIndex` 变 nil，
//: GoodTrip 的 `floor.lua:220` 就报 "table index is nil"。
//: 引擎自己不受影响，因为它用的就是这张表。
std::uintptr_t LookupDescriptorByEngineMap(std::uintptr_t level,
                                           std::uint32_t gridIndex) noexcept {
    if (level == 0 || gridIndex >= kDescriptorGridsPerDimension) {
        return 0;
    }
    std::uint32_t dimension = 0;
    if (!ReadDescriptorU32(level, kLevelCurrentRoomDimensionOffset, &dimension) ||
        dimension > kDescriptorMaximumDimension) {
        return 0;
    }
    const std::uintptr_t entry =
        level + kDescriptorGridSlotTableOffset +
        (static_cast<std::uintptr_t>(dimension) * kDescriptorGridsPerDimension + gridIndex) * 4;
    std::uint32_t raw = 0;
    if (!ReadDescriptorU32(entry, 0, &raw)) {
        return 0;
    }
    const std::int32_t slot = static_cast<std::int32_t>(raw);
    if (slot < 0) {
        g_IsaacRoomIdxSlotNegative.fetch_add(1, std::memory_order_relaxed);
        return 0;                       // 引擎的约定：负数 = 这一格没有房间
    }
    // **只接受已分配的槽位**：引擎自己直接信这张表，但我们读到的可能来自过渡期/过期的一格
    // ⇒ 加"槽位必须落在已分配区间内、且该槽位真的有房间"两道校验。
    // 真机实测过一张会踩到这道校验的表（2026-09-19：`map[97] = 33`，而当时已分配槽位只有 7 个，
    // 33 号槽位的 `+0x00` 是 0xFFFFFFFF）⇒ 那次两边都找不到，属于"过渡期没有当前房间"，
    // 这时按 `kAbsentRoomGridIndex` 给 -1，而不是编一个房间出来。
    if (static_cast<std::uint32_t>(slot) >= DescriptorCount(level)) {
        // 只记账、**不再否决**（批次 076）：引擎自己没有这道检查（`Level::GetRoomByIdx` 只看
        // 槽号是否为负），而这道检查在真机上挡掉了 56% 的解析（4971/8844）—— 见文件顶部说明。
        g_IsaacRoomIdxSlotBeyondCount.fetch_add(1, std::memory_order_relaxed);
    }
    const std::uintptr_t candidate = DescriptorAddress(level, static_cast<std::uint32_t>(slot));
    std::uint32_t value = 0;
    if (!ReadDescriptorU32(candidate, kGridIndexOffset, &value)) {
        g_IsaacRoomIdxMapSlotRejected.fetch_add(1, std::memory_order_relaxed);
        return 0;
    }
    if (value == kUnallocatedGridIndex) {
        // 这一格是"未分配槽位"（真机实测未分配槽位的 `+0x00` 是 0xFFFFFFFF）⇒ 仍然否决：
        // 否则会把一个空槽位当成房间交给模组（比"没有房间"更糟）。只记账，便于看比例。
        g_IsaacRoomIdxUnallocatedAnchor.fetch_add(1, std::memory_order_relaxed);
        return 0;
    }
    // 第三道校验（**只有正向证据才放行**）：请求的那一格必须落在这个房间的**足迹**里。
    //   * 引擎给的最大房间是 2x2（`RoomShape` 的 1x1/1x2/2x1/2x2 与四个 L 形都在一个 2x2 框里，
    //     见 `RoomDescriptor.md` 的图例）；`Level+0x21558` 是"从哪一格进去的"，必然在足迹内。
    //   * 取**差值**判定，且两个方向都收（`±1`/`±13`/`±14`）：L 形房间的 `GridIndex` 与
    //     `SafeGridIndex` 锚在不同的角（PC 文档：LTL 的 `SafeGridIndex` 是**右上**那一格），
    //     所以"进入格在锚点的左/上"是正常情形，只收正差值会把它们全挡掉。
    //   * 为什么非要这一道：这张表**我们读到的可能是别的东西**（例如某段恰好被清零的内存 ⇒
    //     每个下标都映射到槽位 0）。那时前两道校验挡不住（槽位 0 确实是已分配的真实房间），
    //     结果会是"**给一个错误的房间**" —— 比"没有房间"糟得多（模组会传送到错的房间）。
    const std::int64_t delta = static_cast<std::int64_t>(gridIndex) -
                               static_cast<std::int64_t>(value);
    if (delta != 0 && delta != 1 && delta != -1 && delta != 13 && delta != -13 &&
        delta != 14 && delta != -14) {
        g_IsaacRoomIdxRejectedFootprint.fetch_add(1, std::memory_order_relaxed);
        g_IsaacRoomIdxLastRejectRequest.store(gridIndex, std::memory_order_relaxed);
        g_IsaacRoomIdxLastRejectAnchor.store(value, std::memory_order_relaxed);
        g_IsaacRoomIdxLastRejectDeltaBias.store(
            static_cast<std::uint32_t>(static_cast<std::int32_t>(delta) + 64),
            std::memory_order_relaxed);
        return 0;
    }
    g_IsaacRoomIdxEngineMapUsed.fetch_add(1, std::memory_order_relaxed);
    g_IsaacRoomIdxAccepted.fetch_add(1, std::memory_order_relaxed);
    g_IsaacRoomIdxLastAcceptedRequest.store(gridIndex, std::memory_order_relaxed);
    g_IsaacRoomIdxLastAcceptedSlot.store(static_cast<std::uint32_t>(slot),
                                         std::memory_order_relaxed);
    g_IsaacRoomIdxLastAcceptedAnchor.store(value, std::memory_order_relaxed);
    std::uint32_t safe = 0;
    if (ReadDescriptorU32(candidate, kSafeGridIndexOffset, &safe)) {
        g_IsaacRoomIdxLastAcceptedSafe.store(safe, std::memory_order_relaxed);
    }
    return candidate;
}

//: 批次 077：**直接问引擎**（`Level::GetRoomByIdx`），不再自己扫表。
//:
//: 返回引擎给的那个 `RoomDescriptor*`（无效格子时是引擎自己的**静态空描述符**，非空指针）。
//: 拿不到（模块基址未发布 / 入口指纹不匹配）时返回 0，调用方回落到我们手写的那条链。
//:
//: 为什么值得这么做：手写那条链在真机上解析率低、而且**从某些入口格走进多格房间时会解析成别的房间**
//: （用户实测：从银色道具房 / 贪婪最下方那间走进两格房必现，传送进去则不现）。引擎这条函数
//: 就是 PC 的 Lua 绑定走的同一条路 ⇒ 它的答案按定义就是"PC 会得到的答案"。
using LevelGetRoomByIdxFn = const void* (*)(const void* level, int index, int dimension);

std::uintptr_t LevelGetRoomByIdxMethod() noexcept {
    const std::uintptr_t base = EngineModuleBase();
    if (base == 0 || base > UINTPTR_MAX - kLevelGetRoomByIdxOffset) {
        return 0;
    }
    const std::uintptr_t method = base + kLevelGetRoomByIdxOffset;
    return IsEngineMemoryReadable(method, sizeof(std::uint32_t)) ? method : 0;
}

std::uintptr_t ResolveDescriptorNative(std::uintptr_t level, std::int32_t index,
                                       std::int32_t dimension) noexcept {
    if (level == 0) {
        return 0;
    }
    const std::uintptr_t method = LevelGetRoomByIdxMethod();
    if (method == 0 || !EngineEntryWordMatches(method, kLevelGetRoomByIdxEntryWord)) {
        g_IsaacRoomIdxNativeFallbacks.fetch_add(1, std::memory_order_relaxed);
        return 0;
    }
    const auto call = isaac::runtime::engine_call::AsFunction<LevelGetRoomByIdxFn>(method);
    const void* descriptor =
        call(isaac::runtime::engine_memory::AsObject(level), index, dimension);
    if (descriptor == nullptr) {
        g_IsaacRoomIdxNativeFallbacks.fetch_add(1, std::memory_order_relaxed);
        return 0;
    }
    g_IsaacRoomIdxNativeCalls.fetch_add(1, std::memory_order_relaxed);
    g_IsaacRoomIdxNativeLastIndex.store(static_cast<std::uint32_t>(index),
                                        std::memory_order_relaxed);
    g_IsaacRoomIdxNativeLastDimension.store(static_cast<std::uint32_t>(dimension),
                                            std::memory_order_relaxed);
    return isaac::runtime::engine_memory::AddressOf(descriptor);
}

//: 带记账的包装（批次 074）：记下"最后一次请求的格子"与"解析结果的三个字段"，
//: 供读数工具判断"是扫描没命中、被足迹校验挡掉、还是引擎映射表给的槽位无效"。
std::uintptr_t FindDescriptorByGridIndexTracked(std::uintptr_t level,
                                                std::uint32_t gridIndex) noexcept;

//: 按 `+0x00 == gridIndex` 扫描定位描述符；找不到再走引擎自己的映射表；都没有返回 0。
std::uintptr_t FindDescriptorByGridIndex(std::uintptr_t level, std::uint32_t gridIndex) noexcept {
    if (level == 0 || gridIndex == kUnallocatedGridIndex) {
        return 0;
    }
    const std::uint32_t count = DescriptorCount(level);
    for (std::uint32_t slot = 0; slot < count; ++slot) {
        const std::uintptr_t candidate = DescriptorAddress(level, slot);
        std::uint32_t value = 0;
        if (!ReadDescriptorU32(candidate, kGridIndexOffset, &value)) {
            break;                      // 这一格读不到就停（不是整表失败），再交给映射表兜底
        }
        if (value == gridIndex) {
            return candidate;
        }
    }
    return LookupDescriptorByEngineMap(level, gridIndex);
}

std::uintptr_t FindDescriptorByGridIndexTracked(std::uintptr_t level,
                                                std::uint32_t gridIndex) noexcept {
    g_IsaacRoomIdxCalls.fetch_add(1, std::memory_order_relaxed);
    g_IsaacRoomIdxLastRequest.store(gridIndex, std::memory_order_relaxed);
    const std::uintptr_t descriptor = FindDescriptorByGridIndex(level, gridIndex);
    if (descriptor == 0) {
        g_IsaacRoomIdxEmpty.fetch_add(1, std::memory_order_relaxed);
        g_IsaacRoomIdxLastResolvedGrid.store(0xFFFFFFFFu, std::memory_order_relaxed);
        g_IsaacRoomIdxLastResolvedSafe.store(0xFFFFFFFFu, std::memory_order_relaxed);
        g_IsaacRoomIdxLastResolvedList.store(0xFFFFFFFFu, std::memory_order_relaxed);
        return 0;
    }
    const auto keep = [descriptor](std::uintptr_t offset, std::atomic<std::uint32_t>& slot) {
        std::uint32_t value = 0;
        if (ReadDescriptorU32(descriptor, offset, &value)) {
            slot.store(value, std::memory_order_relaxed);
        }
    };
    keep(kGridIndexOffset, g_IsaacRoomIdxLastResolvedGrid);
    keep(kSafeGridIndexOffset, g_IsaacRoomIdxLastResolvedSafe);
    keep(kListIndexOffset, g_IsaacRoomIdxLastResolvedList);
    return descriptor;
}

std::uintptr_t CurrentRoomIndex(std::uintptr_t level) noexcept {
    std::uint32_t index = 0;
    if (!ReadDescriptorU32(level, kLevelCurrentRoomIndexOffset, &index)) {
        return kUnallocatedGridIndex;
    }
    return index;
}

int PushRoomDescriptor(lua_State* state, std::uintptr_t descriptor) {
    // ★ 2026-09-19（批次 043）：**永远给对象**，哪怕这一刻拿不到地址。
    //
    // 原来 `descriptor == 0` 时推 nil，真机代价（GoodTrip 的 `scripts/floor.lua:15-16`）：
    // 模组在**加载期**读 `M.crd = level:GetCurrentRoomDesc()`，此时描述符表还没建好
    // ⇒ 我们给 nil ⇒ 下一句 `M.crd.GridIndex` 直接 "attempt to index a nil value" ⇒
    // **模组整个加载失败**（现象："模组像没装"）。而 PC 在这一步返回的是**对象**
    //（模组作者才敢直接取字段；GoodTrip 的注释还写着初始值"reassigned on every room and
    // floor change"，本来就不重要 —— 只要**有对象**）。
    //
    // 这与 `Isaac.GetItemConfig()` 当年的定案同一条原则（`isaac_api.cpp`：
    // "链路拿到了、只是向量此刻还没建立 ⇒ 返回对象"）。字段读取由
    // `RoomDescriptorIndex()` 负责如实给 nil（读不到就说没有，不报错）。
    if (descriptor == 0) {
        auto* empty = static_cast<LuaRuntime::RoomDescriptorHandle*>(
            lua_newuserdata(state, sizeof(LuaRuntime::RoomDescriptorHandle)));
        empty->descriptor = nullptr;
        luaL_getmetatable(state, LuaRuntime::kRoomDescriptorMetatable);
        lua_setmetatable(state, -2);
        return 1;
    }
    auto* handle = static_cast<LuaRuntime::RoomDescriptorHandle*>(
        lua_newuserdata(state, sizeof(LuaRuntime::RoomDescriptorHandle)));
    handle->descriptor = isaac::runtime::engine_memory::AsObject(descriptor);
    luaL_getmetatable(state, LuaRuntime::kRoomDescriptorMetatable);
    lua_setmetatable(state, -2);
    return 1;
}

}  // namespace


int RoomDescriptorListGet(lua_State* state) {
    auto* handle = static_cast<LuaRuntime::RoomDescriptorListHandle*>(
        luaL_checkudata(state, 1, LuaRuntime::kRoomDescriptorListMetatable));
    if (handle == nullptr || !isaac::runtime::IsIntegerArgument(state, 2)) {
        return luaL_error(state, "RoomDescriptorList:Get expects an index");
    }
    const lua_Integer requested = lua_tointegerx(state, 2, nullptr);
    const std::uintptr_t level = isaac::runtime::engine_memory::AddressOf(handle->level);
    const std::uint32_t count = DescriptorCount(level);
    if (requested < 0 || static_cast<std::uint64_t>(requested) >= count) {
        lua_pushnil(state);
        return 1;
    }
    const std::uint32_t slot = static_cast<std::uint32_t>(requested);
    std::uintptr_t descriptor = DescriptorAddress(level, slot);
    std::uint32_t listIndex = 0;
    if (ReadDescriptorU32(descriptor, kListIndexOffset, &listIndex) && listIndex != slot) {
        descriptor = 0;
        for (std::uint32_t candidate = 0; candidate < count; ++candidate) {
            const std::uintptr_t address = DescriptorAddress(level, candidate);
            std::uint32_t value = 0;
            if (ReadDescriptorU32(address, kListIndexOffset, &value) && value == slot) {
                descriptor = address;
                break;
            }
        }
    }
    return PushRoomDescriptor(state, descriptor);
}

// `RoomDescriptorList` 的**方法**表（`Size` 是字段、走 `__index`；这里只有 `Get`）。
// 这一族没有 catalog id（它是 `Level:GetRooms()` 的返回值，不是 Mod 直接调用的 API），
// 所以不能用 `AttachOwnerMethods` 那套"id → handler"的绑定方式，直接按名字挂。
struct NamedHandler {
    const char* name;
    lua_CFunction handler;
};

int LevelGetCurrentRoomDesc(lua_State* state) {
    luaL_checkudata(state, 1, kLevelMetatable);
    if (lua_gettop(state) != 1) {
        return luaL_error(state, "Level:GetCurrentRoomDesc accepts no arguments");
    }
    const std::uintptr_t level = ResolveLevelForDescriptor();
    if (level == 0) {
        return luaL_error(state, "Level:GetCurrentRoomDesc could not read the native Level state");
    }
    const std::uintptr_t index = CurrentRoomIndex(level);
    if (index == kUnallocatedGridIndex) {
        return luaL_error(state, "Level:GetCurrentRoomDesc could not read the current room index");
    }
    // 批次 077：先问引擎自己（`Level::GetCurrentRoomDesc` 内部就是"读这两个字段 + 转调
    // `Level::GetRoomByIdx`"）；问不到才回落到我们手写的那条链。
    std::uint32_t dimension = 0;
    if (!ReadDescriptorU32(level, kLevelCurrentRoomDimensionOffset, &dimension)) {
        dimension = 0;
    }
    const std::uintptr_t native = ResolveDescriptorNative(
        level, static_cast<std::int32_t>(index), static_cast<std::int32_t>(dimension));
    if (native != 0) {
        return PushRoomDescriptor(state, native);
    }
    return PushRoomDescriptor(state, FindDescriptorByGridIndexTracked(
                                        level, static_cast<std::uint32_t>(index)));
}

int LevelGetRoomByIdx(lua_State* state) {
    luaL_checkudata(state, 1, kLevelMetatable);
    const int argumentCount = lua_gettop(state);
    if (argumentCount < 2 || argumentCount > 3 || !isaac::runtime::IsIntegerArgument(state, 2)) {
        return luaL_error(state, "Level:GetRoomByIdx expects an index and an optional dimension");
    }
    const lua_Integer requested = lua_tointegerx(state, 2, nullptr);
    if (argumentCount == 3 && isaac::runtime::IsIntegerArgument(state, 3)) {
        const lua_Integer dimension = lua_tointegerx(state, 3, nullptr);
        if (dimension != 0 && dimension != -1) {
            // 非 0 维度还没验证过（真机那几轮都在普通楼层，维度恒为 0）。宁可给 nil，
            // 也不把"另一个维度的房间"当成当前维度的返回给 Mod。
            lua_pushnil(state);
            return 1;
        }
    }
    const std::uintptr_t level = ResolveLevelForDescriptor();
    if (level == 0) {
        return luaL_error(state, "Level:GetRoomByIdx could not read the native Level state");
    }
    // 批次 077：**负索引也交给引擎**（`Level::GetRoomByIdx` 自带负数分支，PC 的 -1/-2/-3
    // 语义就在里面）—— 以前给 nil 是因为"负数槽位公式没有证据"，现在不用猜了。
    const std::int32_t dimension = (argumentCount == 3)
        ? static_cast<std::int32_t>(lua_tointegerx(state, 3, nullptr)) : -1;
    const std::uintptr_t native = ResolveDescriptorNative(
        level, static_cast<std::int32_t>(requested), dimension);
    if (native != 0) {
        return PushRoomDescriptor(state, native);
    }
    // 回落（引擎调用不可用时的老路径）：只支持非负索引与 -1。
    if (requested == -1) {
        const std::uintptr_t index = CurrentRoomIndex(level);
        if (index == kUnallocatedGridIndex) {
            lua_pushnil(state);
            return 1;
        }
        return PushRoomDescriptor(state, FindDescriptorByGridIndexTracked(level,
                                                                  static_cast<std::uint32_t>(index)));
    }
    if (requested < 0) {
        lua_pushnil(state);
        return 1;
    }
    return PushRoomDescriptor(
        state, FindDescriptorByGridIndexTracked(level,
                                             static_cast<std::uint32_t>(requested)));
}

int LevelGetRooms(lua_State* state) {
    luaL_checkudata(state, 1, kLevelMetatable);
    if (lua_gettop(state) != 1) {
        return luaL_error(state, "Level:GetRooms accepts no arguments");
    }
    const std::uintptr_t level = ResolveLevelForDescriptor();
    if (level == 0) {
        return luaL_error(state, "Level:GetRooms could not read the native Level state");
    }
    auto* handle = static_cast<LuaRuntime::RoomDescriptorListHandle*>(
        lua_newuserdata(state, sizeof(LuaRuntime::RoomDescriptorListHandle)));
    handle->level = isaac::runtime::engine_memory::AsObject(level);
    luaL_getmetatable(state, LuaRuntime::kRoomDescriptorListMetatable);
    lua_setmetatable(state, -2);
    return 1;
}

// `Level:IsPreAscent()`（批次 11）：PC 文档（`Level.md`）说它表示"玩家处在**通往升华**的
// 幕府/革赫那第二层"。
//
// 判据由两个已定名的字段组成：
//   * `Level + 0x00` == `STAGE4_3(9)`（幕府 II / 革赫那 II）；
//   * `Level + 0x04` 属于忏悔时代关卡 —— 引擎自己的写法是"清掉 bit0 后等于 4"，
//     正好把 `STAGETYPE_REPENTANCE(4)` 与 `STAGETYPE_REPENTANCE_B(5)` 归成一类
//     （证据见 `kLevelStageTypeOffset`）。
// ⚠ 这条判据来自**文档 + 字段证据**；真机上要走到幕府/革赫那第二层才能实测到 true，
// 普通楼层必须返回 false（这一条宿主与真机都能验）。
int LevelIsPreAscent(lua_State* state) {
    luaL_checkudata(state, 1, kLevelMetatable);
    if (lua_gettop(state) != 1) {
        return luaL_error(state, "Level:IsPreAscent accepts no arguments");
    }
    // 解析链用 `ResolveCurrentLevel`（模块偏移那条），**不要**用 `ResolveLevelForDescriptor`：
    // 后者从安装期发布的 `GameOwnerSlot()` 出发、比前者多解一层 —— 宿主夹具上直接段错误
    // （实测：把 `g_Game` 槽前 8 字节当成指针，读到的是"关卡+类型"打包成的 0x400000009）。
    // 本文件里设备验证过的 `Level:GetCurrentRoomIndex` 用的就是 `ResolveCurrentLevel`（真机 `idx=84` ✓）。
    std::uintptr_t level = 0;
    std::uint32_t stage = 0;
    std::uint32_t stageType = 0;
    if (!ResolveCurrentLevel(&level) || level == 0 ||
        !isaac::runtime::engine_memory::ReadAt(level + kLevelStageOffset, &stage,
                                               &IsEngineMemoryReadable) ||
        !isaac::runtime::engine_memory::ReadAt(level + kLevelStageTypeOffset, &stageType,
                                               &IsEngineMemoryReadable)) {
        lua_pushboolean(state, 0);
        return 1;
    }
    const bool preAscent =
        stage == kLevelStagePreAscent && (stageType & ~1U) == kStageTypeRepentanceEraMasked;
    lua_pushboolean(state, preAscent ? 1 : 0);
    return 1;
}

} // namespace


//: `Level` 族的字段读取型 API。**家族的行表住在自己的 TU 里**（契约门禁逐条核对），
//: 处理器 `FieldApiHandler` 是共享的那一个。
//:
//: 字段证据（`runtime_constants.hpp` 的 `kLevelStageTypeOffset`）：`Level::SetStage(eLevelStage,
//: eStageType)` 用 `stp w21, w20, [x19]` 把两个参数**连着**写进 `this+0x00`/`+0x04`。
constexpr FieldApiRow kLevelFieldApis[] = {
    // `Level:GetStageType()`：读 `Level + 0x04`（`eStageType`）。这条顺带让真机探针能**直接核对**
    // 这个字段（原始枚举值比一个布尔更好对照）。
    {0x0301000B, kLevelStageTypeOffset, 0, FieldKind::U32, FieldMissing::Nil,
     FieldReceipt::Level, 0xFF},
    // `Level:IsAltStage()`：PC 契约（`Level.md`）= "StageType **不是** `STAGETYPE_ORIGINAL(0)`"，
    // 判据就是 `Level + 0x04 != 0`。
    {0x0301000C, kLevelStageTypeOffset, 0, FieldKind::BoolNonZero, FieldMissing::False,
     FieldReceipt::Level, 0xFF},
};

//: 批次 051：`Level` 的**引擎方法数据行**（机制见 `engine_method_api.hpp`）。
constexpr EngineMethodRow kLevelEngineRows[] = {
    // 0x000F `Level:AddCurse(eLevelCurse, bool)`：`x0 = this`、`w1 = 诅咒号`、`w2 = 是否永久`
    // （bool 在 ABI 上就是 `w2` 的 0/1，所以用 `Void2` 传两个整数即可）。
    {0x0301000F, kLevelAddCurseOffset, kLevelAddCurseEntryWord, FieldReceipt::Level,
     EngineCallShape::Void2, 2, 0xFF},
    // 0x0010 `Level:RemoveCurses(uint)`：`x0 = this`、`w1 = 诅咒位掩码`。
    {0x03010010, kLevelRemoveCursesOffset, kLevelRemoveCursesEntryWord, FieldReceipt::Level,
     EngineCallShape::Void1, 1, 0xFF},
};

std::size_t AttachLevelMethods(lua_State* state) noexcept {
    // 字段读取型行表也挂给 `Level` 族（批次 11 起）：绑定循环按 id 匹配，不会串族；
    // 行里的 `receipt` 决定用哪套接收者校验。
    return AttachOwnerMethods(state, "Level", kLevelHandlers, RowCount(kLevelHandlers),
                              kLevelFieldApis, RowCount(kLevelFieldApis), kLevelEngineRows,
                              RowCount(kLevelEngineRows));
}

//: `RoomDescriptor.Data` 暴露给 Lua 的**表**（`data == 0` ⇒ 字段全 0；见上面两处调用点）。
//: 为什么必须"建全字段"而不是漏建：漏建就是 nil，模组一索引就崩
//: （`control.lua:339` 的 `crd.Data.Type` 就是这么把回调打断的）。
void PushRoomConfigRoom(lua_State* state, std::uintptr_t data) {
    lua_createtable(state, 0, static_cast<int>(RowCount(kRoomConfigRoomFields)) + 1);
    for (std::size_t index = 0; index < RowCount(kRoomConfigRoomFields); ++index) {
        std::uint32_t value = 0;
        if (data != 0) {
            static_cast<void>(isaac::runtime::engine_memory::ReadAt(
                data + kRoomConfigRoomFields[index].offset, &value, &IsEngineMemoryReadable));
        }
        lua_pushinteger(state, static_cast<lua_Integer>(value));
        lua_setfield(state, -2, kRoomConfigRoomFields[index].name);
    }
    // `Spawns`：**明确空容器**（机制、为什么必需、偏离后果、取证后的替换方式见
    // `PushEmptySpawnList` 上方的注释块）。放在字段循环之后：它没有偏移，不走那张表。
    PushEmptySpawnList(state);
    lua_setfield(state, -2, "Spawns");
}

void PushEmptyRoomConfigRoom(lua_State* state) {
    PushRoomConfigRoom(state, 0);
}

// `RoomDescriptor` 的字段访问。**只服务已 confirmed 的字段**；其它一律 nil。
//: `Room::GetDoorSlotPosition(eDoorSlot)`：返回门的**世界坐标**（两个 float 走 `s0`/`s1`）。
//: 入口指纹（`d10083ff` = `sub sp, sp, #0x20`）不过就返回 false，让调用方给 nil。
bool RoomGetDoorSlotPosition(std::int32_t slot, RoomDoorPosition* out) noexcept {
    if (out == nullptr) {
        return false;
    }
    const std::uintptr_t base = EngineModuleBase();
    if (base == 0 || base > UINTPTR_MAX - kRoomGetDoorSlotPositionOffset) {
        return false;
    }
    const std::uintptr_t method = base + kRoomGetDoorSlotPositionOffset;
    if (!IsEngineMemoryReadable(method, sizeof(std::uint32_t)) ||
        !EngineEntryWordMatches(method, kRoomGetDoorSlotPositionEntryWord)) {
        return false;
    }
    void* room = nullptr;
    if (ReadCurrentGameRoom(GameOwnerSlot(), &room) != GameRoomObservation::Success ||
        room == nullptr) {
        return false;
    }
    using DoorSlotPositionFn = RoomDoorPosition (*)(const void*, int);
    const auto call = isaac::runtime::engine_call::AsFunction<DoorSlotPositionFn>(method);
    *out = call(room, static_cast<int>(slot));
    return true;
}

//: `GridEntity_Door::CanEnter` 的取址（与 `EntityTakeDamageMethod` 同一种接法：
//: 常量出现在助手体内、结果经局部变量交给调用点 —— ABI 体检靠这条链把常量与签名对上）。
std::uintptr_t GridEntityDoorCanEnterMethod() noexcept {
    const std::uintptr_t base = EngineModuleBase();
    if (base == 0 || base > UINTPTR_MAX - kGridEntityDoorCanEnterOffset) {
        return 0;
    }
    const std::uintptr_t method = base + kGridEntityDoorCanEnterOffset;
    return IsEngineMemoryReadable(method, sizeof(std::uint32_t)) ? method : 0;
}

//: `GridEntityDoor:IsOpen()`：**方法**（PC 就是 `boolean IsOpen()`，GoodTrip 也是 `door:IsOpen()`）。
//:
//: ★ 批次 079 修正 078 的回归：078 把它做成了**布尔字段** ⇒ 模组按方法调用时是
//: "attempt to call a boolean value"，而 `rules.lua:12` 就在 `check_room_open()` 里这么调
//: （那条错会把整条规则回调打断）。口径见 `kGridEntityDoorCanEnterOffset`：优先调引擎自己的
//: `CanEnter()`（`(variant == 2) XOR 标志 bit4`），引擎调用不可用时退化为只看标志 bit4。
int GridEntityDoorIsOpen(lua_State* state) {
    if (lua_gettop(state) != 1) {
        return luaL_error(state, "GridEntityDoor:IsOpen accepts no arguments");
    }
    void* entityPointer = GridEntityArgument(state, 1);
    if (entityPointer == nullptr) {
        return luaL_error(state, "GridEntityDoor:IsOpen expects a door");
    }
    const std::uintptr_t entity = isaac::runtime::engine_memory::AddressOf(entityPointer);
    std::uint32_t flags = 0;
    // 判定 + 取值同一次调用（L1 `ReadAt`）；读不到时 `flags` 保留初值 0，与原 if 同义。
    static_cast<void>(isaac::runtime::engine_memory::ReadAt(entity + kGridEntityDoorFlagsOffset,
                                                            &flags, &IsEngineMemoryReadable));
    bool open = (flags & (1u << 4)) != 0;
    const std::uintptr_t method = GridEntityDoorCanEnterMethod();
    if (method != 0 && EngineEntryWordMatches(method, kGridEntityDoorCanEnterEntryWord)) {
        using CanEnterFn = bool (*)(const void*);
        open = isaac::runtime::engine_call::AsFunction<CanEnterFn>(method)(entityPointer);
    }
    lua_pushboolean(state, open ? 1 : 0);
    return 1;
}

// ─────────────────────────────────────────────────────────────────────────────
// `GridEntity` 基类字段（2026-09-21，修"EID 在献祭房不显示房间信息"）
// ─────────────────────────────────────────────────────────────────────────────
//
// PC 的 `GridEntity` 有这些**字段**（IsaacDocs `GridEntity.md` 的 Variables）：
// `Position`（`const Vector`）、`Desc`、`VarData`、`State`、`CollisionClass`。
// 我们过去给**非门的**网格实体只挂了三个**方法**（`GetType`/`GetVariant`/`GetRNG`），
// 字段一个都没有 ⇒ 读 `gridEntity.Position` 拿到 `nil`。
//
// 真机后果（用户 2026-09-21 报"EID 在特殊房间（献祭房）没有房间信息"）：
// EID 每帧为每个玩家挑"最近的实体"，对每个**有描述**的网格实体取位置
// （`main.lua:1491` `gridEntity.Position:__sub(sourcePos)`）；而 EID 只给
// `GRID_SPIKES` 注册了描述（`features/eid_grid_descriptions.lua:115/133`，条件是
// "当前房间类型 == 献祭房(13) 且 `DisplaySacrificeInfo` 开着"）⇒ 这个缺陷**只在献祭房/
// 带刺房间**露出来：取 `nil` 再 `:__sub` ⇒ 抛错 ⇒ **那一帧的描述整段不画**（不崩、无提示）。
//
// 顺带补上 `VarData`：献祭房的回调紧接着要读它（`descObj.Entity.VarData + 1`），
// 缺了它就算位置修好也会在下一行继续抛错。`Desc` 与门那条一样只给已取证的三个字段。
//
// 没取证偏移的成员（`State`/`CollisionClass`）**不编值**：宁可让模组拿到 `nil`
// （那是"该字段没实现"的可见信号），也不能给一个恒 0 的假值。

// 调 `GridEntity::GetPosition() const`（入口与 ABI 见 `runtime_constants.hpp` 的
// `kGridEntityGetPositionOffset`：只有 `this` 一个入参，`Vector2` 走 `s0/s1` 返回）。
// 返回 false = "这次没有真的调到引擎"（绑定没发布/守卫没过/内存不可读）⇒ 调用方让字段读取失败。
bool CallGridEntityGetPosition(std::uintptr_t method, const std::array<u8, 16>& expected,
                               const void* entity, float* x, float* y) noexcept {
    if (entity == nullptr || x == nullptr || y == nullptr) {
        return false;
    }
#if !defined(__SWITCH__)
    // 宿主：没有引擎映像，用注入的实现（与 `Room:WorldToScreenPosition` 的宿主钩子同一形态）。
    if (const auto host = LuaRuntime::GetGridEntityGetPositionHostFunction(); host != nullptr) {
        host(entity, x, y);
        return true;
    }
#endif
    if (method == 0 || (method & 3) != 0 ||
        !isaac::runtime::engine_call::VerifyEntryBytes(method, expected.data(), expected.size(),
                                                       &IsEngineMemoryReadable)) {
        return false;
    }
    struct Vector2Value {
        float x;
        float y;
    };
    using GetPositionFn = Vector2Value (*)(const void*);
    const Vector2Value value =
        isaac::runtime::engine_call::AsFunction<GetPositionFn>(method)(entity);
    *x = value.x;
    *y = value.y;
    return true;
}

// `GridEntity` 的 `__index`：先答基类**字段**，再落到方法表（`GetType`/`GetVariant`/`GetRNG`）。
// 两种句柄都认（门是 `GridEntity` 的子类：PC 里 `door.Position`/`door.VarData` 同样可读）。
int GridEntityIndex(lua_State* state) {
    const char* key = lua_tostring(state, 2);
    void* entityPointer = (key == nullptr) ? nullptr : GridEntityArgument(state, 1);
    if (entityPointer != nullptr) {
        const std::uintptr_t entity = isaac::runtime::engine_memory::AddressOf(entityPointer);
        if (std::strcmp(key, "Position") == 0) {
            // ★ 引擎自己算的位置（`(idx % W + 1) * 40`、`(idx / W) * 40 + 120`）——
            // 不自己按格子拼：EID 拿它算距离，口径必须与引擎一致。
            float x = 0.0F;
            float y = 0.0F;
            if (CallGridEntityGetPosition(LuaRuntime::GridEntityGetPositionThunk(),
                                          kGridEntityGetPositionExpectedBytes, entityPointer, &x,
                                          &y)) {
                isaac::runtime::PushLuaVector(state, x, y);
                return 1;
            }
            return luaL_error(state, "GridEntity.Position is unavailable in this build");
        }
        const auto readField = [entity](std::uintptr_t offset, std::uint32_t* value) {
            return isaac::runtime::engine_memory::ReadAt(entity + offset, value,
                                                         &IsEngineMemoryReadable);
        };
        std::uint32_t value = 0;
        if (std::strcmp(key, "VarData") == 0) {
            if (!readField(kGridEntityVarDataOffset, &value)) {
                return luaL_error(state, "GridEntity.VarData could not read the native state");
            }
            lua_pushinteger(state, static_cast<lua_Integer>(value));
            return 1;
        }
        if (std::strcmp(key, "Desc") == 0) {
            std::uint32_t type = 0;
            std::uint32_t variant = 0;
            std::uint32_t varData = 0;
            static_cast<void>(readField(kGridEntityTypeOffset, &type));
            static_cast<void>(readField(kGridEntityVariantOffset, &variant));
            static_cast<void>(readField(kGridEntityVarDataOffset, &varData));
            lua_createtable(state, 0, 3);
            lua_pushinteger(state, static_cast<lua_Integer>(type));
            lua_setfield(state, -2, "Type");
            lua_pushinteger(state, static_cast<lua_Integer>(variant));
            lua_setfield(state, -2, "Variant");
            lua_pushinteger(state, static_cast<lua_Integer>(varData));
            lua_setfield(state, -2, "VarData");
            return 1;
        }
    }
    // 落到 `GridEntity` 的方法表（`GetType`/`GetVariant`/`GetRNG`…）。
    luaL_getmetatable(state, LuaRuntime::kGridEntityMetatable);
    lua_getfield(state, -1, "__methods");
    if (lua_istable(state, -1)) {
        lua_getfield(state, -1, key == nullptr ? "" : key);
        lua_remove(state, -2);
        lua_remove(state, -2);
        return 1;
    }
    lua_pop(state, 2);
    lua_pushnil(state);
    return 1;
}

int GridEntityDoorIndex(lua_State* state) {
    auto* handle = static_cast<LuaRuntime::DoorHandle*>(
        luaL_checkudata(state, 1, LuaRuntime::kGridEntityDoorMetatable));
    const char* key = lua_tostring(state, 2);
    if (handle == nullptr || key == nullptr) {
        lua_pushnil(state);
        return 1;
    }
    const std::uintptr_t entity = isaac::runtime::engine_memory::AddressOf(handle->entity);
    const auto readU32 = [entity](std::uintptr_t offset, std::uint32_t* value) {
        if (entity == 0) {
            return false;
        }
        return isaac::runtime::engine_memory::ReadAt(entity + offset, value,
                                                     &IsEngineMemoryReadable);
    };
    std::uint32_t value = 0;
    if (std::strcmp(key, "TargetRoomType") == 0) {
        if (!readU32(kGridEntityDoorTargetRoomTypeOffset, &value)) {
            lua_pushnil(state);
            return 1;
        }
        lua_pushinteger(state, static_cast<lua_Integer>(value));
        return 1;
    }
    if (std::strcmp(key, "Direction") == 0) {
        if (!readU32(kGridEntityDoorDirectionOffset, &value)) {
            lua_pushnil(state);
            return 1;
        }
        lua_pushinteger(state, static_cast<lua_Integer>(value));
        return 1;
    }
    if (std::strcmp(key, "CurrentRoomType") == 0) {
        if (!readU32(kGridEntityDoorCurrentRoomTypeOffset, &value)) {
            lua_pushnil(state);
            return 1;
        }
        lua_pushinteger(state, static_cast<lua_Integer>(value));
        return 1;
    }
    if (std::strcmp(key, "IsOpen") == 0) {
        // **方法**而不是字段：PC 的签名是 `boolean IsOpen()`，模组写的是 `door:IsOpen()`。
        lua_pushcfunction(state, GridEntityDoorIsOpen);
        return 1;
    }
    if (std::strcmp(key, "TargetRoomIndex") == 0) {
        if (!readU32(kGridEntityDoorTargetRoomIndexOffset, &value)) {
            lua_pushnil(state);
            return 1;
        }
        lua_pushinteger(state, static_cast<lua_Integer>(value));
        return 1;
    }
    if (std::strcmp(key, "VarData") == 0) {
        if (!readU32(kGridEntityVarDataOffset, &value)) {
            lua_pushnil(state);
            return 1;
        }
        lua_pushinteger(state, static_cast<lua_Integer>(value));
        return 1;
    }
    if (std::strcmp(key, "Desc") == 0) {
        // PC 里这是 `GridEntityDesc` 对象；这里给一张**只含已取证字段**的表：
        // `Type`(+0x08)、`Variant`(+0x10)、`VarData`(+0x1C) —— 三个都来自
        // "`GridEntity::Init(const Desc&)` 把 `Desc[0x00..0x1F]` 拷到对象 `+0x08..+0x27`"这条结构证据
        // （见 `kGridEntityTypeOffset` 的注释）。没取证的成员不编值。
        std::uint32_t type = 0;
        std::uint32_t variant = 0;
        std::uint32_t varData = 0;
        static_cast<void>(readU32(kGridEntityTypeOffset, &type));
        static_cast<void>(readU32(kGridEntityVariantOffset, &variant));
        static_cast<void>(readU32(kGridEntityVarDataOffset, &varData));
        lua_createtable(state, 0, 3);
        lua_pushinteger(state, static_cast<lua_Integer>(type));
        lua_setfield(state, -2, "Type");
        lua_pushinteger(state, static_cast<lua_Integer>(variant));
        lua_setfield(state, -2, "Variant");
        lua_pushinteger(state, static_cast<lua_Integer>(varData));
        lua_setfield(state, -2, "VarData");
        return 1;
    }
    if (std::strcmp(key, "Position") == 0) {
        RoomDoorPosition position{0.0F, 0.0F};
        if (!RoomGetDoorSlotPosition(handle->slot, &position)) {
            lua_pushnil(state);
            return 1;
        }
        isaac::runtime::PushLuaVector(state, position.x, position.y);
        return 1;
    }
    // 落到 `GridEntity` **基类**（字段 + 方法表）。2026-09-21 起基类的 `__index` 也是函数
    // （它要多答几个字段），所以这里直接转调，而不是像以前那样取一张 `__index` 表。
    return GridEntityIndex(state);
}

int RoomDescriptorIndex(lua_State* state) {
    auto* handle = static_cast<LuaRuntime::RoomDescriptorHandle*>(
        luaL_checkudata(state, 1, LuaRuntime::kRoomDescriptorMetatable));
    const char* key = lua_tostring(state, 2);
    if (handle == nullptr || key == nullptr) {
        lua_pushnil(state);
        return 1;
    }
    const std::uintptr_t descriptor = isaac::runtime::engine_memory::AddressOf(handle->descriptor);
    // 空句柄（`descriptor == nullptr`，见 `PushRoomDescriptor` 的注释）：这一刻解析不到当前房间。
    //
    // ★ 2026-09-19 批次 049：**网格类字段给 -1，而不是 nil**。
    //   原来是"所有字段如实给 nil"，真机代价（GoodTrip `scripts/floor.lua:218-220`）：
    //   `here = lvl:GetCurrentRoomDesc().SafeGridIndex` ⇒ nil ⇒ `link[here] = ...`
    //   直接报 "table index is nil"，整条 `MC_POST_UPDATE` 回调每帧被打断。
    //   而引擎自己的"这一格没有房间"就是 **-1**（真机实测：未分配槽位的 `+0x00`/`+0x04`
    //   都是 `0xFFFFFFFF`）⇒ 给 -1 既不是编值、也不比 PC 严。
    //   其余字段仍然给 nil（它们是对象/掩码，没有"没有"这个取值可对）。
    if (descriptor == 0) {
        // ★ 2026-09-19 批次 073 修正：**数值/布尔/子对象字段也要给"没有"这个取值，不能给 nil**。
        //
        // 真机事故（用户复测"地图打不开"）：`Level:GetCurrentRoomDesc()` 在**换房那一刻**
        // （以及贪婪模式一类我们解析不到当前房间的时刻）返回**空句柄**，而这里除三个网格字段外
        // 一律给 nil ⇒ GoodTrip `scripts/control.lua:339` 的 `crd.Data.Type` 崩、
        // 环形历史里一直挂着那条错（整条 `MC_POST_NEW_ROOM` 回调被摘掉）。
        // 071 只修了"描述符有效但 `Data` 指针为 0"，**空句柄这条路没覆盖**。
        //
        // 判据照旧：PC 里这些字段都有确定类型 ⇒ 给该类型下的"空值"，
        // 而不是给 nil（`nil > 0`、`nil.Type` 都会把回调打断，而回调一断，模组那一支就整条不执行）。
        if (std::strcmp(key, "GridIndex") == 0 || std::strcmp(key, "SafeGridIndex") == 0 ||
            std::strcmp(key, "ListIndex") == 0) {
            lua_pushinteger(state, static_cast<lua_Integer>(kAbsentRoomGridIndex));
            return 1;
        }
        if (std::strcmp(key, "VisitedCount") == 0 || std::strcmp(key, "Flags") == 0 ||
            std::strcmp(key, "DisplayFlags") == 0) {
            lua_pushinteger(state, 0);
            return 1;
        }
        if (std::strcmp(key, "Clear") == 0) {
            lua_pushboolean(state, 0);
            return 1;
        }
        if (std::strcmp(key, "Data") == 0) {
            // 空句柄 = "这一刻没有房间数据" ⇒ 记一次，再给**字段全 0 的表**（与 071 同形）。
            RecordRoomDescriptorDataMiss(0);
            PushEmptyRoomConfigRoom(state);
            return 1;
        }
        lua_pushnil(state);
        return 1;
    }
    std::uint32_t value = 0;
    if (std::strcmp(key, "GridIndex") == 0) {
        if (!ReadDescriptorU32(descriptor, kGridIndexOffset, &value)) {
            return luaL_error(state, "RoomDescriptor.GridIndex could not read the native state");
        }
        lua_pushinteger(state, static_cast<lua_Integer>(value));
        return 1;
    }
    if (std::strcmp(key, "SafeGridIndex") == 0) {
        if (!ReadDescriptorU32(descriptor, kSafeGridIndexOffset, &value)) {
            return luaL_error(state, "RoomDescriptor.SafeGridIndex could not read the native state");
        }
        lua_pushinteger(state, static_cast<lua_Integer>(value));
        return 1;
    }
    if (std::strcmp(key, "ListIndex") == 0) {
        if (!ReadDescriptorU32(descriptor, kListIndexOffset, &value)) {
            return luaL_error(state, "RoomDescriptor.ListIndex could not read the native state");
        }
        lua_pushinteger(state, static_cast<lua_Integer>(value));
        return 1;
    }
    if (std::strcmp(key, "VisitedCount") == 0) {
        if (!ReadDescriptorU32(descriptor, kVisitedCountOffset, &value)) {
            return luaL_error(state, "RoomDescriptor.VisitedCount could not read the native state");
        }
        lua_pushinteger(state, static_cast<lua_Integer>(value));
        return 1;
    }
    if (std::strcmp(key, "DisplayFlags") == 0) {
        // PC 的 `RoomDescriptor.DisplayFlags`：小地图可见性**位掩码**
        // （位0 = 可见、位1 = 房间阴影、位2 = 显示图标）。
        // 为什么必须有它：GoodTrip 的绘制路径（`floor.lua:134`/`149`、`widget.lua:172`/`358`）
        // 直接读 `des.DisplayFlags`（`> 0`、`& 1`、`== 3`）—— 拿不到就是 `nil` 参与比较，
        // 每帧抛 `attempt to compare number with nil`，把整条绘制回调打断在画小地图之前
        // （真机症状：按住地图键什么都不出现）。
        if (!ReadDescriptorU32(descriptor, kDisplayFlagsOffset, &value)) {
            return luaL_error(state, "RoomDescriptor.DisplayFlags could not read the native state");
        }
        lua_pushinteger(state, static_cast<lua_Integer>(value));
        return 1;
    }
    if (std::strcmp(key, "Flags") == 0) {
        // PC 的 `RoomDescriptor.Flags`：32 位位掩码（EID 用 `room.Flags & 1024` 做道具预测）。
        if (!ReadDescriptorU32(descriptor, kFlagsOffset, &value)) {
            return luaL_error(state, "RoomDescriptor.Flags could not read the native state");
        }
        lua_pushinteger(state, static_cast<lua_Integer>(value));
        return 1;
    }
    if (std::strcmp(key, "Clear") == 0) {
        if (!ReadDescriptorU32(descriptor, kClearOffset, &value)) {
            return luaL_error(state, "RoomDescriptor.Clear could not read the native state");
        }
        // PC 契约：`Clear` 就是 `Flags` 的**第 0 位**（真机验证过：清房瞬间该位 0→1，起始房间本来就是 1）。
        lua_pushboolean(state, (value & kRoomFlagClear) != 0 ? 1 : 0);
        return 1;
    }
    if (std::strcmp(key, "Data") == 0) {
        // PC 的 `Data` 是房间配置对象；EID 只读它的 `Type`（布局表 confirmed 的 `Data+0x8`）。
        // 未确认的成员（例如 `Variant`）这里**不编值**，返回 nil 由调用方自行判断。
        //
        // ★ 批次 071 修正：**`Data` 永远不许是 nil**（PC 里它是一个内嵌结构，不是可空指针）。
        // 真机事故（2026-09-19，用户复测时仍复现）：`control.lua:339` 写的是
        // `crd.Data.Type`，而某些房间（贪婪模式等）`描述符 + 0x10` 读出来是 0 ⇒ 我们返回 nil
        // ⇒ 模组的 `MC_POST_NEW_ROOM` 回调每次都崩在那里（整条回调被摘掉，
        // "秘密房/诅咒房预缓存"那一支永远不执行）。
        // 现在：读不到就返回一张**字段全 0** 的表（= "普通房间"这个安全分支），并把这件事记进
        // 状态面（次数 + 现场几个字），下次读数就能看清"是哪种房间、描述符对不对"。
        std::uintptr_t data = 0;
        // 判定 + 取值同一次调用（L1 `ReadAt`）；读不到时 `data` 保留初值 0，与原 if 同义。
        static_cast<void>(isaac::runtime::engine_memory::ReadAt(descriptor + kDataOffset, &data,
                                                               &IsEngineMemoryReadable));
        if (data == 0) {
            RecordRoomDescriptorDataMiss(descriptor);
        }
        PushRoomConfigRoom(state, data);
        return 1;
    }
    lua_pushnil(state);
    return 1;
}

// `RoomDescriptorList.__index`：`Size` 现读（房间会随探索增加），没有别的方法落在这里。
int RoomDescriptorListIndex(lua_State* state) {
    auto* handle = static_cast<LuaRuntime::RoomDescriptorListHandle*>(
        luaL_checkudata(state, 1, LuaRuntime::kRoomDescriptorListMetatable));
    const char* key = lua_tostring(state, 2);
    if (handle == nullptr || key == nullptr) {
        lua_pushnil(state);
        return 1;
    }
    if (std::strcmp(key, "Size") == 0) {
        lua_pushinteger(state, static_cast<lua_Integer>(
            DescriptorCount(isaac::runtime::engine_memory::AddressOf(handle->level))));
        return 1;
    }
    // ★ 必须从**元表**取方法表：用 `lua_getfield(state, 1, ...)` 去索引 userdata 会再次
    // 触发 `__index`（就是本函数），直接 C 栈溢出 —— 宿主机上实测到 `C stack overflow`。
    luaL_getmetatable(state, LuaRuntime::kRoomDescriptorListMetatable);
    lua_getfield(state, -1, "__methods");
    if (!lua_istable(state, -1)) {
        lua_pop(state, 2);
        lua_pushnil(state);
        return 1;
    }
    lua_getfield(state, -1, key);
    lua_remove(state, -2);   // 弹掉 __methods
    lua_remove(state, -2);   // 弹掉元表
    return 1;
}

// `rooms:Get(i)`：EID 的用法是 `for i = 0, rooms.Size - 1 do local room = rooms:Get(i)`。
// 快路径直接取第 i 个槽位；它的 `+0x08`（ListIndex）不等于 i 时才退化为整表扫描
// （槽位顺序与 ListIndex 顺序在真机上一致，但这里不把"一致"当永久保证）。
// --- 批次 061：`Level`/`Game` 句柄的 `__newindex`（接受并忽略）-------------------------
//
// 详见 `remaining_api.hpp` 的说明。两件事要注意：
//   1. **绝不能报错**：这些赋值往往出现在绘制/传送路径上，抛错会把整条回调摘掉
//      （GoodTrip 就是这样"静默不传送"的）；
//   2. **不能猜偏移去写引擎**：`EnterDoor`/`LeaveDoor` 的偏移没有证据，猜一个写进去
//      会踩坏引擎对象；所以这里只记一笔"有人想写什么"，不动引擎。
extern "C" {
//: 被忽略的字段写入次数（诊断面）。
std::atomic<std::uint32_t> g_IsaacIgnoredFieldWriteCount{0};
//: 最后一次被忽略的字段名（截断到 23 字节 + NUL）；空串表示还没发生过。
char g_IsaacLastIgnoredFieldName[24] = {};
}

int IgnoredObjectFieldWrite(lua_State* state) {
    if (lua_gettop(state) < 3 || !lua_isstring(state, 2)) {
        return 0;
    }
    const char* name = lua_tostring(state, 2);
    if (name != nullptr) {
        std::size_t index = 0;
        for (; index + 1 < sizeof(g_IsaacLastIgnoredFieldName) && name[index] != '\0'; ++index) {
            g_IsaacLastIgnoredFieldName[index] = name[index];
        }
        g_IsaacLastIgnoredFieldName[index] = '\0';
    }
    g_IsaacIgnoredFieldWriteCount.fetch_add(1, std::memory_order_relaxed);
    return 0;
}

std::size_t AttachRoomDescriptorListMethods(lua_State* state) noexcept {
    static constexpr NamedHandler kMethods[] = {
        {"Get", &RoomDescriptorListGet},
    };
    std::size_t attached = 0;
    for (const NamedHandler& method : kMethods) {
        lua_pushcfunction(state, method.handler);
        lua_setfield(state, -2, method.name);
        ++attached;
    }
    return attached;
}

//: 批次 051：`Room` 的**引擎方法数据行**（机制见 `engine_method_api.hpp`）。
constexpr EngineMethodRow kRoomEngineRows[] = {
    // 0x000D `Room:PlayMusic()`：`x0 = this(当前房间)`，无参数、返回 void。
    {0x0401000D, kRoomPlayMusicOffset, kRoomPlayMusicEntryWord, FieldReceipt::Room,
     EngineCallShape::Void0, 0, 0xFF},
};

std::size_t AttachRoomMethods(lua_State* state) noexcept {
    // 批次 051：`Room:PlayMusic()` 走引擎方法数据行（`this` = **当前房间**，
    // 所以 `receipt` 用 `Room`——它不从 Lua 栈上取接收者）。
    return AttachOwnerMethods(state, "Room", kRoomHandlers, RowCount(kRoomHandlers), nullptr, 0,
                              kRoomEngineRows, RowCount(kRoomEngineRows));
}

// `GridEntity` 族的方法表（元表在 `lua_runtime.cpp` 里建）。
std::size_t AttachGridEntityMethods(lua_State* state) noexcept {
    return AttachOwnerMethods(state, "GridEntity", kGridEntityHandlers,
                              RowCount(kGridEntityHandlers));
}

std::size_t AttachItemPoolMethods(lua_State* state) noexcept {
    return AttachOwnerMethods(state, "ItemPool", kItemPoolHandlers, RowCount(kItemPoolHandlers));
}

// --- `Level:GetCurses()` 的探针（2026-09-12，动作三）-------------------------------
//
// 探针要一次性回答"EID 的 `hasCurseBlind()` 为什么可能误判"：
//   * `rawCurses`      —— `Level+0xC` 的原始位（也就是我们现在交给 Mod 的那个值）；
//   * `permanentCurses`/`bannedCurses` —— 引擎自己的两个 `Game` 方法的返回值
//     （PC 的完整语义是 `raw | permanent` 再 `& banned`，我们此前**一步都没做**）；
//   * `synthesisFlags` —— bit0 原始位读到了、bit1 permanent 调用成功、bit2 banned 调用成功。
//
// 为什么必须在真机上读、而不能靠反汇编推断：`Level:GetCurses()` 的**地址链**没有疑点
// （反汇编已逐条核对），但"这台机器的这一层到底有没有中盲眼诅咒"只有真机读数能说清；
// 而 `EID:hasCurseBlind()` 的真假正是"隐瞒分支"四条成因之一。
GameCursesProbe GameCursesProbeSnapshot() noexcept {
    GameCursesProbe view{};
    view.raw = g_ProbeRawCurses.load(std::memory_order_relaxed);
    view.permanent = g_ProbePermanentCurses.load(std::memory_order_relaxed);
    view.banned = g_ProbeBannedCurses.load(std::memory_order_relaxed);
    view.flags = g_ProbeCursesFlags.load(std::memory_order_relaxed);
    view.reads = g_ProbeCursesReads.load(std::memory_order_relaxed);
    return view;
}


// `ItemPool:GetPillEffect(PillColor, EntityPlayer = nil)`（PC 文档 `ItemPool.md:65`）。
//
// ★ 为什么最急：EID 在 `features/eid_api.lua:881` 调
// `pool:GetPillEffect(SubType, player) + 1`（药丸描述那条路径），真机报
// `attempt to call a nil value (method 'GetPillEffect')` ⇒ 那颗药的描述整条消失
// （不崩、屏幕上也没提示，只留一行错误 —— 与"恒返回 0 的假桩"同一族问题）。
//
// 引擎方法 `ItemPool::GetPillEffect(ePillColor, Entity_Player*)` @ `0x3C857C`，
// 入口指纹 `0xA9BD7BFD`。**颜色掩码由引擎自己做**（该函数的第一条访存前就有 `and w8, w1, #0x7ff`
// —— 与 `ItemPool:IsPillIdentified` 的注释里记的是同一条），所以这里不重复掩码。
//
// 第二个参数 PC 是可空的；我们按"不是实体句柄就传 nullptr"处理（`EntityPointerArgument` 不抛错），
// 而不是报错 —— 报错会摘掉整条回调，代价远大于"引擎拿到 nil 玩家"。
int ItemPoolGetPillEffect(lua_State* state) {
    luaL_checkudata(state, 1, kItemPoolMetatable);
    const int argumentCount = lua_gettop(state);
    if ((argumentCount != 2 && argumentCount != 3) || !isaac::runtime::IsIntegerArgument(state, 2)) {
        return luaL_error(state, "ItemPool:GetPillEffect accepts a pill colour and optional player");
    }
    const lua_Integer pillColor = lua_tointegerx(state, 2, nullptr);
    if (pillColor < 0 ||
        static_cast<std::uint64_t>(pillColor) > std::numeric_limits<std::uint32_t>::max()) {
        return luaL_error(state, "ItemPool:GetPillEffect pill colour is outside uint32 range");
    }
    void* itemPool = nullptr;
    if (ReadCurrentGameItemPool(GameOwnerSlot(), &itemPool) != GameItemPoolObservation::Success) {
        return luaL_error(state, "ItemPool:GetPillEffect could not read the native ItemPool state");
    }
    std::uintptr_t player = 0;
    if (argumentCount == 3) {
        player = isaac::runtime::EntityPointerArgument(state, 3);
    }
    const std::uintptr_t base = EngineModuleBase();
    std::uint32_t entryWord = 0;
    if (base == 0 || base > UINTPTR_MAX - kItemPoolGetPillEffectOffset ||
        !isaac::runtime::engine_memory::ReadAt(base + kItemPoolGetPillEffectOffset, &entryWord,
                                               &IsEngineMemoryReadable)) {
        return luaL_error(state, "ItemPool:GetPillEffect native binding is unavailable");
    }
    if (entryWord != kItemPoolGetPillEffectEntryWord) {
        return luaL_error(state, "ItemPool:GetPillEffect native binding does not match this build");
    }
    // 引擎签名：`int (*)(ItemPool*, int pillColor, Entity_Player*)`（颜色在 w1、玩家在 x2）。
    using GetPillEffectFn = int (*)(void*, int, void*);
    const int pillEffect = isaac::runtime::engine_call::AsFunction<GetPillEffectFn>(
        base + kItemPoolGetPillEffectOffset)(
        itemPool, static_cast<int>(pillColor), isaac::runtime::engine_memory::AsObject(player));
    lua_pushinteger(state, static_cast<lua_Integer>(pillEffect));
    return 1;
}

// `ItemPool:GetPoolForRoom(RoomType, Seed)`（PC 文档 `ItemPool.md:74`）。
// 引擎方法 `ItemPool::GetPoolForRoom(eRoomType, unsigned) const` @ `0x3C5C7C`，指纹 `0xD10103FF`。
// 返回 `ItemPoolType`（整数）。EID 在"这个房间用哪个池子"的链式调用里用它。
int ItemPoolGetPoolForRoom(lua_State* state) {
    luaL_checkudata(state, 1, kItemPoolMetatable);
    const int argumentCount = lua_gettop(state);
    if ((argumentCount != 3 && argumentCount != 4) || !isaac::runtime::IsIntegerArgument(state, 2) ||
        (argumentCount == 4 && !isaac::runtime::IsIntegerArgument(state, 4))) {
        return luaL_error(state, "ItemPool:GetPoolForRoom accepts a room type and optional seed");
    }
    const lua_Integer roomType = lua_tointegerx(state, 2, nullptr);
    const lua_Integer seed = argumentCount == 4 ? lua_tointegerx(state, 4, nullptr) : 0;
    if (roomType < 0 ||
        static_cast<std::uint64_t>(roomType) > std::numeric_limits<std::uint32_t>::max() ||
        seed < 0 || static_cast<std::uint64_t>(seed) > std::numeric_limits<std::uint32_t>::max()) {
        return luaL_error(state, "ItemPool:GetPoolForRoom integer arguments are outside uint32 range");
    }
    void* itemPool = nullptr;
    if (ReadCurrentGameItemPool(GameOwnerSlot(), &itemPool) != GameItemPoolObservation::Success) {
        return luaL_error(state, "ItemPool:GetPoolForRoom could not read the native ItemPool state");
    }
    const std::uintptr_t base = EngineModuleBase();
    std::uint32_t entryWord = 0;
    if (base == 0 || base > UINTPTR_MAX - kItemPoolGetPoolForRoomOffset ||
        !isaac::runtime::engine_memory::ReadAt(base + kItemPoolGetPoolForRoomOffset, &entryWord,
                                               &IsEngineMemoryReadable)) {
        return luaL_error(state, "ItemPool:GetPoolForRoom native binding is unavailable");
    }
    if (entryWord != kItemPoolGetPoolForRoomEntryWord) {
        return luaL_error(state, "ItemPool:GetPoolForRoom native binding does not match this build");
    }
    // 引擎签名：`int (*)(const ItemPool*, int roomType, unsigned seed)`。
    using GetPoolForRoomFn = int (*)(const void*, int, unsigned);
    const int pool = isaac::runtime::engine_call::AsFunction<GetPoolForRoomFn>(
        base + kItemPoolGetPoolForRoomOffset)(
        itemPool, static_cast<int>(roomType), static_cast<unsigned>(seed));
    lua_pushinteger(state, static_cast<lua_Integer>(pool));
    return 1;
}

// `Level:GetLastRoomDesc()`（PC 文档 `Level.md:172`：`const RoomDescriptor GetLastRoomDesc()`）。
//
// 引擎方法 `Level::GetLastRoomDesc()` @ `0x3DC69C`，指纹 `0x5282AB88`。它的函数体只有 6 条指令，
// 而且**尾调用** `Level::GetRoomByIdx(int index, int dimension)`：
//   `add x8, x0, #0x2155C` → `ldr w1, [x8]`、`ldr w2, [x8, #0x8]` → `b GetRoomByIdx`
// 也就是说它读的是"上一个房间"的（索引 `+0x2155C`、维度 `+0x21564`）—— 紧挨着我们早就用着的
// "当前房间"那一对（`+0x21558`/`+0x21560`），两条线索互相印证。返回值是 `RoomDescriptor*`，
// 直接交给现成的 `PushRoomDescriptor`（与 `Level:GetCurrentRoomDesc` 同一条交付路径）。
int LevelGetLastRoomDesc(lua_State* state) {
    luaL_checkudata(state, 1, kLevelMetatable);
    if (lua_gettop(state) != 1) {
        return luaL_error(state, "Level:GetLastRoomDesc accepts no arguments");
    }
    const std::uintptr_t level = ResolveLevelForDescriptor();
    if (level == 0) {
        return luaL_error(state, "Level:GetLastRoomDesc could not read the native Level state");
    }
    const std::uintptr_t base = EngineModuleBase();
    std::uint32_t entryWord = 0;
    if (base == 0 || base > UINTPTR_MAX - kLevelGetLastRoomDescOffset ||
        !isaac::runtime::engine_memory::ReadAt(base + kLevelGetLastRoomDescOffset, &entryWord,
                                               &IsEngineMemoryReadable)) {
        return luaL_error(state, "Level:GetLastRoomDesc native binding is unavailable");
    }
    if (entryWord != kLevelGetLastRoomDescEntryWord) {
        return luaL_error(state, "Level:GetLastRoomDesc native binding does not match this build");
    }
    // 引擎签名：`RoomDescriptor* (*)(Level*)`（`this` 在 x0）。
    using GetLastRoomDescFn = void* (*)(void*);
    void* descriptor = isaac::runtime::engine_call::AsFunction<GetLastRoomDescFn>(
        base + kLevelGetLastRoomDescOffset)(isaac::runtime::engine_memory::AsObject(level));
    if (descriptor == nullptr) {
        lua_pushnil(state);
        return 1;
    }
    return PushRoomDescriptor(state, isaac::runtime::engine_memory::AddressOf(descriptor));
}


} // namespace isaac::runtime
