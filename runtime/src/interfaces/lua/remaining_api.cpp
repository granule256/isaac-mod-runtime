#include "interfaces/lua/api700_grid.hpp"
#include "interfaces/lua/api700_bindings.hpp"
#include "interfaces/lua/api600_bindings.hpp"
#include "interfaces/lua/api600_world.hpp"
#include "interfaces/lua/api600_containers.hpp"
#include "interfaces/lua/api500_world.hpp"
#include "interfaces/lua/api300_bindings.hpp"
#include "interfaces/lua/api200_bindings.hpp"
#include "interfaces/lua/rplus_extended_fields.hpp"
#include "interfaces/lua/rplus_method_bindings.hpp"
#include "interfaces/lua/field_api.hpp"
#include "interfaces/lua/native_state_fallback.hpp"
#include "interfaces/lua/remaining_api.hpp"
#include "interfaces/lua/api100_bindings.hpp"
#include "interfaces/lua/rng_api.hpp"
#include "interfaces/lua/vector_api.hpp"

#include "room_layout.hpp"
#include "game_layout.hpp"   // 批次 294：Level 那两个房间索引的布局表生成物（`Level` 内嵌在 `Game` 起始处）
// 批次 207（2026-09-29）：`Room:IsClear()` 读的是 `RoomDescriptor + 0x50` 的 bit0 —— 那个偏移
// 属于**布局表**（`layout::kRoomDescriptorFlagsOffset`，confirmed 行），不在 `runtime_constants.hpp`。
#include "room_descriptor_layout.hpp"

#include "interfaces/lua/api_sequence_probe.hpp"
#include "interfaces/lua/runtime_perf.hpp"   // 批次 435：子阶段探针的 tick（`RuntimePerfTick`）
#include "infrastructure/call/engine_call_access.hpp"
#include "infrastructure/memory/engine_field_access.hpp"
#include "infrastructure/memory/engine_memory_guard.hpp"
#include "interfaces/lua/engine_method_lookup.hpp"
// 批次 028：`ItemPool:GetPillEffect` 的可空 `EntityPlayer` 实参要经 `EntityPointerArgument`
// 解析（"什么算一个实体句柄"的唯一实现在那个 TU 里），所以这里显式包含它 —— 与本文件里
// `sprite_api` 用 `IsLiveEntityPointer` 的理由相同：不写第二份判据。
#include "interfaces/lua/isaac_api.hpp"
#include "interfaces/lua/sprite_api.hpp"   // 批次 298：`PushEngineGridEntitySpriteHandle`
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
#include "infrastructure/relay/entry_relay_binding.hpp"
#endif

extern "C" {
#include <lauxlib.h>
#include "probe_gate.hpp"
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
// 批次 270（2026-10-02）：`Level:QueryRoomTypeIndex(RoomType, Visited, RNG, IgnoreGroup=false)`
// —— 作业单 `needs_new_shape` 桶的最后一条。**手写**（第 3 个参数是 `RNG&`，数据行机制表达不了），
// 但**不新增 `EngineCallShape`**（手写处理器本来什么形状都能写）。
int LevelQueryRoomTypeIndex(lua_State* state);
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
// 批次 247：三个**返回 Vector** 的 Room 方法（手写，理由见实现处）。
int RoomGetCenterPos(lua_State* state);
int RoomGetGridPosition(lua_State* state);
int RoomGetRandomPosition(lua_State* state);
// 批次 259：四条**位置类**的 Room 方法（同样返回 Vector，同样手写；理由见实现处）。
int RoomFindFreePickupSpawnPosition(lua_State* state);
int RoomGetClampedPosition(lua_State* state);
int RoomFindFreeTilePosition(lua_State* state);
int RoomGetDoorSlotPosition(lua_State* state);
int RoomGetGridIndex(lua_State* state);
int RoomGetGridCollisionAtPos(lua_State* state);
// 批次 310（2026-10-03）：`Room:GetAliveBossesCount()` —— 两格相邻 int32 相加、负数清 0。
// ★★ 批次 311（2026-10-03）**修正归属**：310 把「敌人对」当成了 Boss（见常量段与实现处注释）
//    ⇒ 本条的偏移常量已改指 `0x1A60`，另一对（`0x1A58`）归 `Room:GetAliveEnemiesCount()`。
// ★ 两条共用实现 `PushRoomAliveCount`（同一段 PC 模板、只有偏移不同）。
int RoomGetAliveBossesCount(lua_State* state);
// 批次 311（2026-10-03）：`Room:GetAliveEnemiesCount()`（语料 1 处，`BOIStageAPI15`）。
int RoomGetAliveEnemiesCount(lua_State* state);
int RoomGetGridPath(lua_State* state);
int RoomGetGridEntity(lua_State* state);
// 批次 307（2026-10-03）：`Room:GetGridEntityFromPos(Vector)`（语料 4 处）。
// ★ 它复用 `Room:GetGridIndex(Vector)` 那套"世界坐标 → 格坐标"的换算
//   （`RoomGridCoordinateFromWorld` + `ReadRoomGridDimensions`）与
//   `Room:GetGridEntity(index)` 那张表 ⇒ **零新增引擎偏移**。
int RoomGetGridEntityFromPos(lua_State* state);
// 批次 046：`Room:GetDoor(slot)`（GoodTrip 运行期要它）。
int RoomGetDoor(lua_State* state);
int RoomGetRenderScrollOffset(lua_State* state);
// 批次 269（2026-10-02）：`blocked_decision` 桶剩下的渲染两条。★ 两条都是 `Placeholder` 偏离
// （Switch 侧字段偏移未取证，给的是保守值而不是编一个像真值的常量）—— 理由与后果见实现处注释。
int RoomGetRenderMode(lua_State* state);
int RoomGetRenderSurfaceTopLeft(lua_State* state);
int RoomGetWorldToScreenPosition(lua_State* state);
// 2026-09-16：`Room:GetFrameCount()`（房间已经活动了多少帧；真机上暴露的每帧报错见实现处注释）。
int RoomGetFrameCount(lua_State* state);
// 2026-09-18：`Room:IsMirrorWorld()`（当前房间是不是在镜像维度里）。判据与证据见实现处注释。
int RoomIsMirrorWorld(lua_State* state);
// 批次 207（2026-09-29）：`Room:IsClear()`（MCM 的 `modconfig.lua:231` 要用）。
int RoomIsClear(lua_State* state);
int LevelIsPreAscent(lua_State* state);
int GridEntityGetVariant(lua_State* state);
int GridEntityGetType(lua_State* state);
int GridEntityGetRng(lua_State* state);
// 批次 298（2026-10-03）：`GridEntity:GetSprite()`（14 处）+ `GridEntityRock:GetSprite()`
// —— 两条在 Switch 上读的是**同一格**（`GridEntity + 0x48` 的内嵌 ANM2），见下面的实现注释。
int GridEntityGetSprite(lua_State* state);
// 批次 272（2026-10-02）：`GridEntity:Init(int Seed)`（语料 15 处）。
int GridEntityInit(lua_State* state);
// 批次 276（2026-10-02）：`GridEntity` 的 `GetGridIndex()` 与 7 条**子类转换**（共 20 处）。
// 转换走与 `Entity:ToPlayer()` 一族**同一条 vtable 判据**（`_ZTV` 符号 + 0x10）。
int GridEntityGetGridIndex(lua_State* state);
//: 批次 342（2026-10-04）：`GridEntity:GetSaveState()`（1 处）。
//: 契约 `tools/pc_contract_docs/GridEntity.md:46`（正文 `:49` 逐字说明它与属性 `Desc` 返回**同一个**对象）。
int GridEntityGetSaveState(lua_State* state);
int GridEntityToPit(lua_State* state);
int GridEntityToRock(lua_State* state);
int GridEntityToDoor(lua_State* state);
int GridEntityToTnt(lua_State* state);
int GridEntityToPoop(lua_State* state);
int GridEntityToPressurePlate(lua_State* state);
int GridEntityToSpikes(lua_State* state);
// 批次 284（2026-10-02）：门自己的三条（`Open` / `Close(Force)` / `IsTargetRoomArcade`）。
// ★ 这三条此前被批次 273 的一句注释挡住过（"有重写的不收"）—— 本批用"扫全镜像 mangled 名字"
//   核实：三条各**只有一份实现**，那句注释是把它俩与 `Entity_NPC_HornfelDoor::Open/Close`
//   看混了（那是另一个类）。完整证据与更正写在 `runtime_constants.hpp` 的批次 284 段。
int GridEntityDoorOpen(lua_State* state);
int GridEntityDoorClose(lua_State* state);
int GridEntityDoorIsRoomType(lua_State* state);   // 批次 294
int GridEntityDoorIsTargetRoomArcade(lua_State* state);
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
    // 批次 270（2026-10-02）：`Level:QueryRoomTypeIndex`（取号：Level 域 max+1 = 0x18）。
    {0x03010018, &LevelQueryRoomTypeIndex},
};

constexpr LuaHandlerBinding kGridEntityHandlers[] = {
    // 批次 272：`GridEntity:Init(seed)`（取号 = 域内下一个空号 0x0095）。
    {0x0E010095, &GridEntityInit},
    // ---- 批次 276（2026-10-02）：`GetGridIndex` + 7 条子类转换（域内序号 0xAB..0xB2）。
    // ★ 取号注意：0xE0100A9/0xAA 已被批次 275 的实体标志位那两条占掉（不同 owner 但同一编号空间）。
    {0x0E0100AB, &GridEntityGetGridIndex},
    {0x0E0100AC, &GridEntityToPit},
    {0x0E0100AD, &GridEntityToRock},
    {0x0E0100AE, &GridEntityToDoor},
    {0x0E0100AF, &GridEntityToTnt},
    {0x0E0100B0, &GridEntityToPoop},
    {0x0E0100B1, &GridEntityToPressurePlate},
    {0x0E0100B2, &GridEntityToSpikes},
    {0x0E010052, &GridEntityGetVariant},
    {0x0E010053, &GridEntityGetType},
    {0x0E010054, &GridEntityGetRng},
    // 批次 298（2026-10-03）：域内序号 0xD0（Isaac 域当前 max = 0xCF）。
    {0x0E0100D0, &GridEntityGetSprite},
    // ---- 批次 342（2026-10-04）：域内序号 0xF1（Isaac 域当前 max = 0xF0）----
    // ★ 与属性 `GridEntity.Desc` **共用**同一份表构造（`PushGridEntityDescTable`）。
    {0x0E0100F1, &GridEntityGetSaveState},
};

//: 门的**方法表**（owner `GridEntityDoor`；批次 284 起门终于有了自己的 `__methods`）。
//: ★ 为什么门的方法要单开一张表而不是塞进 `kGridEntityHandlers`：`AttachOwnerMethods` 按
//:   **目录行的 owner** 匹配行、并按 owner 把处理器挂到对应元表上（批次 271 / 批次 028 的教训：
//:   挂错 owner 的症状是"处理器在、目录行在、门禁全绿，但模组调它是 nil"）。
//:   `GridEntityDoor` 与 `GridEntity` 在 PC 里是**两个 owner**（`GridEntityDoor.md` 自己的页），
//:   所以这里必须分开。
constexpr LuaHandlerBinding kGridEntityDoorHandlers[] = {
    // 批次 284（2026-10-02）：三条（域内序号 0xBD..0xBF —— 0xBB/0xBC 是本批 `EntityPlayer` 两条）。
    {0x0E0100BD, &GridEntityDoorOpen},
    {0x0E0100BE, &GridEntityDoorClose},
    {0x0E0100BF, &GridEntityDoorIsTargetRoomArcade},
    // 批次 294（2026-10-03）：域内序号 0xCC —— 注意 0xC0..0xCB 被 `EntityNPC`/`EntityPickup`/
    // `Entity`/`GridEntityDoor` 各批占掉了（本表只管 `GridEntityDoor` 这一个 owner 的行，
    // 但 id 在整个 `Isaac` 域里唯一 ⇒ 取号要看全仓，不能只看本表）。
    // ★ 与 `IsOpen` 不同：`IsOpen` 走的是本族的 `__index`（那是**字段视图**里的方法，
    //   为的是让 `door.IsOpen` 与 `door:IsOpen()` 两种写法都能用）；`IsRoomType` 直接登记在
    //   这里 ⇒ 由 `AttachOwnerMethods(..., "GridEntityDoor", ...)` 挂到元表上，
    //   `door:IsRoomType(t)` 直接命中，不经过 `__index`。
    {0x0E0100CC, &GridEntityDoorIsRoomType},
};

constexpr LuaHandlerBinding kRoomHandlers[] = {
    // 批次 249（2026-10-01）：三个返回 Vector 的 Room 方法（域内序号 0x1B/0x1C/0x1D）。
    {0x0401001B, &RoomGetCenterPos},
    {0x0401001C, &RoomGetGridPosition},
    {0x0401001D, &RoomGetRandomPosition},
    // 批次 259（2026-10-01）：四条**位置类**方法（域内序号 0x20..0x23）。
    {0x04010020, &RoomFindFreePickupSpawnPosition},
    {0x04010021, &RoomGetClampedPosition},
    {0x04010022, &RoomFindFreeTilePosition},
    {0x04010023, &RoomGetDoorSlotPosition},
    // 批次 269（2026-10-02）：`blocked_decision` 桶的渲染两条（域内序号 0x24/0x25）。
    // ★ 两条都是 `Placeholder`（字段偏移未取证）—— 但不实现会让模组的整条回调被摘掉，
    //   所以给保守值 + 在偏离台账里写明。详见实现处注释。
    {0x04010024, &RoomGetRenderMode},
    {0x04010025, &RoomGetRenderSurfaceTopLeft},
    {0x04010001, &RoomGetType},
    {0x04010002, &RoomGetGridWidth},
    {0x04010003, &RoomGetGridHeight},
    {0x04010004, &RoomGetGridSize},
    {0x04010005, &RoomGetGridIndex},
    {0x04010039, &RoomGetGridCollisionAtPos},
    // 批次 310（2026-10-03）：`Room:GetAliveBossesCount()`（取号 = 域内空号 0x34）。
    // ★ 批次 311 修正：它读的是**后一对**格子（Boss），前一对（敌人）在下面 0x35 那条。
    {0x04010034, &RoomGetAliveBossesCount},
    // 批次 311（2026-10-03）：`Room:GetAliveEnemiesCount()`（取号 = 域内下一个空号 0x35）。
    {0x04010035, &RoomGetAliveEnemiesCount},
    {0x04010006, &RoomGetGridPath},
    {0x04010007, &RoomGetGridEntity},
    // 批次 307（2026-10-03）：`Room:GetGridEntityFromPos(Vector)`（域内 0x0001..0x0032 已用尽
    // ⇒ 取 0x0033；与 `GetGridIndex`/`GetGridEntity` 是同一件事的两步，直接复用那两个助手）。
    {0x04010033, &RoomGetGridEntityFromPos},
    {0x04010008, &RoomGetRenderScrollOffset},
    {0x04010009, &RoomGetWorldToScreenPosition},
    {0x0401000A, &RoomGetFrameCount},
    // 0x000B：`Room:IsMirrorWorld`（2026-09-18）。Room 域此前用到 0x000A ⇒ 0x000B 是
    // **扫过整个域之后**确认的空号（见 `api_catalog.cpp` 那一行的注释）。
    {0x0401000B, &RoomIsMirrorWorld},
    // 批次 046：`Room:GetDoor`（id 取域内空号）。
    {0x0401000C, &RoomGetDoor},
    // 批次 207（2026-09-29）：`Room:IsClear()`（MCM 的 `RoomIsSafe()` 要用）。
    // 0x000D 已被 `Room:PlayMusic` 占（它是**引擎方法数据行**，不在本表里）⇒ 取 0x000E。
    {0x0401000E, &RoomIsClear},
};

constexpr LuaHandlerBinding kItemPoolHandlers[] = {
    {0x05011601, &Api500ItemPoolIdentifyPill},
    {0x05010001, &ItemPoolGetCollectible},
    {0x05010002, &ItemPoolGetLastPool},
    {0x05010003, &ItemPoolIsPillIdentified},
    // 批次 028：两条 EID 真机报错/链式缺口（取号：ItemPool 域下一个空号 = 0x04 / 0x05）。
    {0x05010004, &ItemPoolGetPillEffect},
    {0x05010005, &ItemPoolGetPoolForRoom},
};

//: 批次 254（2026-10-01）：`ItemPool` 的**引擎方法数据行**（机制见 `engine_method_api.hpp`）。
//: 接收者用本批新增的 `FieldReceipt::ItemPool`（**不从 Lua 栈上取** —— `ItemPoolHandle`
//: 与 `Room`/`Music` 同形，只放保留字节、不持引擎指针，所以按
//: `ReadCurrentGameItemPool(GameOwnerSlot(), …)` 现查，与手写 `ItemPoolGetCollectible` 同一条链）。
constexpr EngineMethodRow kItemPoolEngineRows[] = {
    // 0x0006 `RemoveCollectible(CollectibleType Collectible)`（PC 契约 `ItemPool.md:96`，
    //   `boolean`；正文「Returns true if given item did exist in the pool before.」）。
    // ★★ 引擎符号是 **3 格**（`…eCollectibleTypeEbb`），而 PC 文档只写 1 个、语料也只传 1 个
    //   （`RepentancePlus/.../main.lua:474`）⇒ 形状 `BoolIntBoolBoolOpt2`（尾部 2 个可省）。
    //   反汇编 `0x3C61F0` 证实：省略的两个 `bool`（保持 0）恰好就是 PC 描述的行为
    //   （第 2 个 = 先做有效性判定、第 3 个 = 只查不删；两者为 0 ⇒ 不判、直接删）。
    // ★ 返回值是 `bool`（`tst` + `cset w0, eq`），语料还在用这个返回值 ⇒ 形状的返回种类
    //   是 `Bool` 而不是 `Void`。
    {0x05010006, kItemPoolRemoveCollectibleOffset, kItemPoolRemoveCollectibleEntryWord,
     FieldReceipt::ItemPool, EngineCallShape::BoolIntBoolBoolOpt2, 3, 0xFF},
};

template <typename Table>
constexpr std::size_t RowCount(const Table& table) noexcept {
    return sizeof(table) / sizeof(table[0]);
}

static_assert(RowCount(kItemPoolEngineRows) == 1,
              "行数与 id 段（批次 254 的 0x05010006）要一起改");

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
        // ★ 批次 250：读不到 ⇒ **回退值 0，不报错**（口径与理由见 `native_state_fallback.hpp`）。
        // 上面那段注释（批次 043）已经承诺了"读不到时返回如实回退值"，但实现一直是抛错 ——
        // 现在按注释的口径改回来。这条正是 GoodTrip 加载期的卡点（`scripts/floor.lua:13`）。
        return PushNativeFallbackInteger(state, kFbLevelGetStage, 0);
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
    return PushNativeFallbackBoolean(state, kFbLevelIsAscent, false);
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

// 引擎那两步（`permanent` / `banned`）的结果 + "到底调到了没有"。
//
// ★ 批次 195（2026-09-29）：这两步以前**只记进探针、不进返回值**（`LevelGetCurses` 返回的是
// `Level+0x0C` 的原始位）。现在它们进返回值（见 `LevelGetCurses`），探针照旧记三格 ——
// 读数里"合成值与 raw 不同"就是"②③真的接上了"的证据（普通局里 `(raw|perm)&~banned == raw`）。
struct GameCursesComposition {
    std::uint32_t composed{0};
    std::uint32_t permanent{0};
    std::uint32_t banned{0};
    bool permanentCalled{false};
    bool bannedCalled{false};
};

// `Level::GetCurses()` 的三步合成（引擎 `0x3D57CC` 全体指令）：
//   `raw = Level + 0x0C` → `| Game::GetSpecialSeedPermanentCurses()` → `& ~GetSpecialSeedBannedCurses()`
// 两个访问器的偏移与 16 字节入口守卫在 `runtime_constants.hpp` 里都有；任一步的守卫不过
// （或 `Game*` 拿不到）⇒ 那一步按 0 参与合成（`| 0` / `& ~0` 都是恒等），**不报错** ——
// 引擎自己也没有"守卫"这个概念，而报错会把整条回调摘掉。
GameCursesComposition ComposeGameCurses(std::uint32_t raw) noexcept {
    GameCursesComposition result{};
    result.permanent = CallGameCurseAccessor(kGameSpecialSeedPermanentCursesOffset,
                                             kGameSpecialSeedPermanentCursesExpectedBytes,
                                             &result.permanentCalled);
    result.banned = CallGameCurseAccessor(kGameSpecialSeedBannedCursesOffset,
                                          kGameSpecialSeedBannedCursesExpectedBytes,
                                          &result.bannedCalled);
    result.composed = (raw | result.permanent) & ~result.banned;
    return result;
}

void RecordGameCursesReadForProbe(std::uint32_t raw,
                                  const GameCursesComposition& composition) noexcept {
    (void)raw;  // 批次 232：生产构建里这段被编译掉 ⇒ 参数必然用不上
    (void)composition;  // 批次 232：生产构建里这段被编译掉 ⇒ 参数必然用不上
#if EXL_DIAGNOSTIC_PROBES  // 批次 232 探针总开关（口径见 probe_gate.hpp）
    g_ProbeCursesReads.fetch_add(1, std::memory_order_relaxed);
    g_ProbeRawCurses.store(raw, std::memory_order_relaxed);
    std::uint32_t flags = 1U;  // bit0：原始位读到了（能走到这里就说明读到了）
    if (composition.permanentCalled) {
        flags |= 2U;  // bit1：permanent 访问器**确实被调到**（守卫通过）
    }
    if (composition.bannedCalled) {
        flags |= 4U;  // bit2：banned 访问器确实被调到
    }
    g_ProbePermanentCurses.store(composition.permanent, std::memory_order_relaxed);
    g_ProbeBannedCurses.store(composition.banned, std::memory_order_relaxed);
    g_ProbeCursesFlags.store(flags, std::memory_order_relaxed);
#endif  // EXL_DIAGNOSTIC_PROBES
}

int LevelGetCurses(lua_State* state) {
    luaL_checkudata(state, 1, kLevelMetatable);
    if (lua_gettop(state) != 1) {
        return luaL_error(state, "Level:GetCurses accepts no arguments");
    }
    std::uint32_t curses = 0;
    if (!ReadGameCurses(&curses)) {
        return PushNativeFallbackInteger(state, kFbLevelGetCurses, 0);
    }
    // ★★ 批次 195（2026-09-29）：**返回三步合成的结果**（PC 契约 `Level.md:142` 那一页**没有**
    // 说明返回值的那一行，语义取自位定义 + 引擎反汇编）。旧实现只返回 `Level+0x0C` 的原始位 ⇒
    // 特殊种子的**永久诅咒**读不到、**禁用诅咒**也屏蔽不掉 —— EID 的 `hasCurseBlind()`
    //（判 `CURSE_OF_BLIND = 0x40`）在那些局面下会误判（该隐瞒的信息没隐瞒、或反之）。
    // 两个访问器在普通局里都返回 0（`(raw|0)&~0 == raw`），所以这条改动对普通局零影响。
    const GameCursesComposition composition = ComposeGameCurses(curses);
    RecordGameCursesReadForProbe(curses, composition);
    lua_pushinteger(state, static_cast<lua_Integer>(composition.composed));
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

// 批次 436（2026-10-11）：**"当前 Game + 当前 Room"的派发窗口内缓存**。
//
// 为什么（435 探针实测）：`Room:GetGridEntity` 每次 1.734 µs 里 **91% 是解析链**
// （`ResolveCurrentLevel` + `ReadCurrentGameRoom` 共 7 步读+检查；Minimap 以 ~134 次/帧调它）。
// 那个结果在整个**派发窗口**内不可能变 —— 窗口内引擎在等我们返回，没有任何东西会换房。
//
// 失效判据 = `EngineGuardDispatchEpoch()`（每进窗口 +1）：
//   * 窗口内：命中（一次本模块原子读 + 比对，几纳秒）；一次链 + 之后全部复用；
//   * 窗口切换（引擎可能在窗口之间换房）：epoch 变 ⇒ 自动重跑；
//   * **主动失效**（同窗口内的换房入口）：`Game:ChangeRoom` / `Game:StartRoomTransition`
//     （`EngineMethodHandler` 里按 id 特判）与 `Isaac.ExecuteCommand`（命令桥）各调一次
//     `InvalidateCurrentRoomCache()` —— 模组能触发换房的三条路都堵上（catalog 全表扫过）。
// ★ 失败**不入缓存**（与 428 入口缓存同一口径）。
struct CurrentRoomCacheEntry {
    std::uint32_t epoch{0};        // 0 = 空
    std::uintptr_t room{0};
};
CurrentRoomCacheEntry g_CurrentRoomCache{};
// （`InvalidateCurrentRoomCache` 的定义在**匿名 namespace 之外**（本文件中部 `}  // namespace` 之后）——
//   它是**跨 TU** 的入口（`isaac_api.cpp` 的三条换房路径调它）；放这里会得到内部链接。）

//: 解析"当前 Room 的地址"（带**派发窗口内缓存**）。拿不到 ⇒ false（调用方按原口径兜底）。
//: ★ **只走 `ReadCurrentGameRoom`**（与各调用点的**原有**口径一致）——**不叠加** `ResolveCurrentLevel`：
//:   那条链依赖 `EngineModuleBase()`（宿主 harness 里是 0）⇒ 会让"读当前房间"族的宿主门禁
//:   （B310/B311 等）全部失败；而 `ReadCurrentGameRoom` 自身已校验 owner/game 非 0
//:   （`OwnerNull`/`GameNull`），语义覆盖相同（真机上两者同由安装期发布，不存在"一有一无"）。
bool ResolveCurrentRoomCached(std::uintptr_t* roomOut) noexcept {
    if (roomOut == nullptr) {
        return false;
    }
    const std::uint32_t epoch = EngineGuardDispatchEpoch().load(std::memory_order_acquire);
    if (epoch != 0 && g_CurrentRoomCache.epoch == epoch) {
        *roomOut = g_CurrentRoomCache.room;
        return true;
    }
    void* room = nullptr;
    if (ReadCurrentGameRoom(GameOwnerSlot(), &room) != GameRoomObservation::Success ||
        room == nullptr) {
        return false;
    }
    const std::uintptr_t roomAddress = isaac::runtime::engine_memory::AddressOf(room);
    g_CurrentRoomCache.epoch = epoch;   // epoch==0（不在窗口内）⇒ 写 0 = 仍为空，下次照跑
    g_CurrentRoomCache.room = roomAddress;
    *roomOut = roomAddress;
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
    std::int32_t index = 0;
    if (!ResolveCurrentLevel(&level) ||
        !isaac::runtime::engine_memory::ReadAt(level + kLevelCurrentRoomIndexOffset, &index,
                                               &IsEngineMemoryReadable)) {
        return PushNativeFallbackInteger(state, kFbLevelGetCurrentRoomIndex, -1);
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
        // 批次 250：与 `Game:GetRoom` 同一条口径 —— 记一笔探针、然后照常给**空壳句柄**
        // （不给 nil、也不报错）。PC 在这里返回对象；`Room` 句柄不持指针，空壳是安全的。
        RecordNativeStateFallback(kFbLevelGetCurrentRoom);
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

// 解析一个引擎成员函数的入口（模块基址 + 偏移 + **16 字节**入口原文）。
// 批次 270 为 `Level:QueryRoomTypeIndex` 写的，批次 272 起 `GridEntity:Init` 也用它
// ⇒ 名字改成通用的这个（两处共用一份，别各写一份）。
//
// 与 `CallLevelIntMethod` 同一判据、只是把"偏移 → 地址"这一步也放在这里：那条路把地址交给
// `LuaRuntime::*Thunk()`（thunk 在 `hook_manager` 里按偏移 + 期望字节建好），而本批这条
// 不需要新开 thunk（会牵动 `lua_runtime_state.hpp` / `hook_manager.cpp` 三处）。
std::uintptr_t ResolveEngineMethodEntry(std::uintptr_t offset,
                                  const std::array<u8, 16>& expected) noexcept {
    const std::uintptr_t base = EngineModuleBase();
    if (base == 0 || base > UINTPTR_MAX - offset) {
        return 0;
    }
    const std::uintptr_t method = base + offset;
    if ((method & 3) != 0 || !IsEngineMemoryReadable(method, expected.size()) ||
        !isaac::runtime::engine_call::VerifyEntryBytes(method, expected.data(), expected.size(),
                                                       &IsEngineMemoryReadable)) {
        return 0;
    }
    return method;
}

// `Level:QueryRoomTypeIndex(RoomType, Visited, RNG, IgnoreGroup = false)` —— PC 契约
// `tools/pc_contract_docs/Level.md:328`，正文 `:329` 逐字
// *"IgnoreGroup: If set to `true`, includes rooms that do not have the same group ID as the
// current room (currently unused)"*。
//
// 语料只有 1 处（`RepentancePlus`），但它是作业单 `needs_new_shape` 桶的最后一条，而且
// **判据比看起来简单**：
//
//   * 引擎符号逐字存在 —— `Level::QueryRoomTypeIndex(eRoomType, bool, RNG&, bool)` @ `0x3E605C`；
//   * **`RNG` 参数不是难题**：Lua 侧的 `RNG` 句柄（`LuaRuntime::RngHandle`）本身就是
//     **16 字节的引擎 `RNG` 对象裸存储**（`std::array<u8, kRngObjectSize>`），而
//     `RNG:SetSeed` / `Next` / `RandomInt` 全都把 `storage.data()` 当 `this` 交给引擎方法
//     ⇒ 把它的地址当 `RNG&` 传出去是**同一件东西**，不是替身、也不需要新形状。
//   * 反汇编（`nro_disasm 0x3e605c 0x200`）印证了两件事：`w1` 是 `RoomType`（`and w8,w1,#0xfffffffe`
//     + `cmp w8,#0xe`、随后的 `cmp w23,#3` / `#0x16` 都围绕它分支）、`x3` 被存进 x20
//     （`mov x20, x3` @ `0x3E60D4`）⇒ 第三个参数确是指针。
//
// 失败降级（第 11 条纪律）：`Level` 解析不到 / 入口对不上 ⇒ 压 **-1** 且**不报错**。
// 为什么是 -1：**引擎自己对"没有这种房间"就是返回 -1**（`mov w19, #-0x1` @ `0x3E6094`），
// 所以 -1 与 PC 的"找不到"同形；压 0 会被模组当成"第 0 号房间"。
int LevelQueryRoomTypeIndex(lua_State* state) {
    luaL_checkudata(state, 1, kLevelMetatable);
    const int argumentCount = lua_gettop(state);
    if (argumentCount != 4 && argumentCount != 5) {
        return luaL_error(
            state,
            "Level:QueryRoomTypeIndex expects a room type, a visited flag, an RNG and an optional "
            "ignore-group flag");
    }
    if (!isaac::runtime::IsIntegerArgument(state, 2)) {
        return luaL_error(state, "Level:QueryRoomTypeIndex expects an integer room type");
    }
    const lua_Integer roomType = lua_tointegerx(state, 2, nullptr);
    const bool visited = lua_toboolean(state, 3) != 0;
    // 第 3 个参数是**必需的** `RNG`（契约里它没有缺省值）⇒ 不是 `RNG` 就报错（模组写错了）。
    auto* rng = static_cast<LuaRuntime::RngHandle*>(
        luaL_testudata(state, 4, LuaRuntime::kRngMetatable));
    if (rng == nullptr) {
        return luaL_error(state, "Level:QueryRoomTypeIndex expects an RNG");
    }
    // 第 4 个（可选）`IgnoreGroup`：PC 的缺省值是 `false`。
    const bool ignoreGroup = argumentCount == 5 && lua_toboolean(state, 5) != 0;
    std::uintptr_t level = 0;
    const std::uintptr_t method = ResolveEngineMethodEntry(kLevelQueryRoomTypeIndexOffset,
                                                     kLevelQueryRoomTypeIndexExpectedBytes);
    if (method == 0 || !ResolveCurrentLevel(&level) || level == 0) {
        return PushNativeFallbackInteger(state, kFbLevelQueryRoomTypeIndex, -1);
    }
    using QueryRoomTypeIndexFn = std::int32_t (*)(void*, std::int32_t, bool, void*, bool);
    const std::int32_t index = isaac::runtime::engine_call::AsFunction<QueryRoomTypeIndexFn>(
        method)(isaac::runtime::engine_memory::AsObject(level),
                static_cast<std::int32_t>(roomType), visited, ResolveRngObject(state, rng, true), ignoreGroup);
    lua_pushinteger(state, static_cast<lua_Integer>(index));
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
        return PushNativeFallbackInteger(state, kFbRoomGetType, 0);
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
        return PushNativeFallbackBoolean(state, kFbRoomIsMirrorWorld, false);
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
    // 批次 436：改走"派发窗口内缓存"的版本（435 探针：解析链是大头）。语义与原实现一致
    // （只 `ReadCurrentGameRoom`；拿不到 ⇒ 0）。换房入口（ChangeRoom/StartRoomTransition/
    // ExecuteCommand）已在各自处理器里让缓存失效。
    std::uintptr_t room = 0;
    if (!ResolveCurrentRoomCached(&room)) {
        return 0;
    }
    return room;
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
        return PushNativeFallbackInteger(state, kFbRoomGetFrameCount, 0);
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

// `Room:IsClear()`（批次 207，2026-09-29）—— MCM 判"这间房能不能开菜单 / 能不能传送"：
// `analysis/mod-corpus/isaac-mod-config-menu/scripts/modconfig.lua:231`
//   `if room:IsClear() and not roomHasDanger then return true end`
// PC 契约 `tools/pc_contract_docs/Room.md:642/644`：`#### boolean IsClear ( )`。
//
// 判据 = **两级解引用**后的一个位：
//   1. `Room + 0x8` → `RoomDescriptor*`（`kRoomDescriptorPointerOffset`，`Room::TriggerClear` 取证）；
//   2. 描述符 `+0x50` 的 **bit0**（`RoomDescriptor.Flags.FLAG_CLEAR`，布局表 confirmed：
//      `room_descriptor_layout.hpp:73` 那一行，另有真机读数 0→1 与 `Room::TriggerClear`
//      的 `orr …, #0x1` 两个独立锚点）。
//
// ★ 为什么**只取 bit0**、不判"非零即真"：`+0x50` 是 32 位掩码，bit1/bit3/bit10/bit16 各有别的含义
//   （压力板触发过、挑战完成、显房、Rotgut 已清）。"非零即真"会把那些也算成清房 ⇒ 菜单在
//   未清房的房间里也能开。这一条布局表的注释里专门点过（"旧实现按『非零即真』读"）。
//
// 读不到 ⇒ **报错而不是答 false**：与 `Room:IsMirrorWorld` 同一口径 —— 模组拿 false 会走
// "房间有危险、不能开菜单"的分支，静默的错答案比可见的报错难查得多。
int RoomIsClear(lua_State* state) {
    if (!RoomArgumentCountIs(state, 1, "Room:IsClear")) {
        return 0;
    }
    void* room = nullptr;
    if (ReadCurrentGameRoom(GameOwnerSlot(), &room) != GameRoomObservation::Success ||
        room == nullptr) {
        return PushNativeFallbackBoolean(state, kFbRoomIsClear, false);
    }
    const std::uintptr_t roomAddress = isaac::runtime::engine_memory::AddressOf(room);
    std::uintptr_t descriptor = 0;
    if (!engine_memory::ReadAt(roomAddress + kRoomDescriptorPointerOffset, &descriptor,
                              &IsEngineMemoryReadable) ||
        descriptor == 0) {
        return PushNativeFallbackBoolean(state, kFbRoomIsClear, false);
    }
    std::uint32_t flags = 0;
    if (!engine_memory::ReadAt(descriptor + layout::kRoomDescriptorFlagsOffset, &flags,
                               &IsEngineMemoryReadable)) {
        return PushNativeFallbackBoolean(state, kFbRoomIsClear, false);
    }
    lua_pushboolean(state, (flags & (1U << kRoomClearFlagBit)) != 0 ? 1 : 0);
    return 1;
}

int RoomGetGridWidth(lua_State* state) {
    if (!RoomArgumentCountIs(state, 1, "Room:GetGridWidth")) {
        return 0;
    }
    std::uint32_t width = 0;
    std::uint32_t height = 0;
    if (!ReadRoomGridDimensions(CurrentRoomAddress(), &width, &height)) {
        return PushNativeFallbackInteger(state, kFbRoomGetGridWidth, 0);
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
        return PushNativeFallbackInteger(state, kFbRoomGetGridHeight, 0);
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
        return PushNativeFallbackInteger(state, kFbRoomGetGridSize, 0);
    }
    // PC 返回格子总数（`width * height`）；真机标准房间是 13×7 = 91，不再是以前那个 169。
    lua_pushinteger(state, static_cast<lua_Integer>(width) * static_cast<lua_Integer>(height));
    return 1;
}

// 原Room::GetGridCollision(Vector2) x0房间、s0/s1按值两个float；保原边界与特殊房间逻辑。
struct AgonyRoomVector { float x; float y; };
static_assert(sizeof(AgonyRoomVector)==8 && offsetof(AgonyRoomVector,y)==4);
using AgonyRoomCollisionFn = std::int32_t (*)(std::uintptr_t,AgonyRoomVector);
int RoomGetGridCollisionAtPos(lua_State* state) {
    luaL_checkudata(state,1,kRoomMetatable);
    const auto* v=RequireVectorArgument(state,2);
    const auto room=CurrentRoomAddress();
    const auto method=ResolveEngineMethodEntry(kRoomGetGridCollisionAtPosOffset,kRoomGetGridCollisionAtPosExpectedBytes);
    if (room==0 || method==0) return luaL_error(state,"Room:GetGridCollisionAtPos native bindings are unavailable");
    const AgonyRoomVector position{v->x,v->y};
    lua_pushinteger(state,engine_call::AsFunction<AgonyRoomCollisionFn>(method)(room,position));
    return 1;
}

int RoomGetGridIndex(lua_State* state) {
    luaL_checkudata(state, 1, kRoomMetatable);
    const int argumentCount = lua_gettop(state);
    std::uint32_t width = 0;
    std::uint32_t height = 0;
    if (!ReadRoomGridDimensions(CurrentRoomAddress(), &width, &height)) {
        return PushNativeFallbackInteger(state, kFbRoomGetGridIndex, -1);
    }
    std::int32_t gridX = 0;
    std::int32_t gridY = 0;
    // 两个重载：`GetGridIndex(int,int)` 与 `GetGridIndex(Vector)`。EID 用的是 Vector 版
    // （`eid_api.lua:3375` 的 `room:GetGridIndex(startPos)`），但 PC 两种都有，这里都支持。
    if (argumentCount == 2) {
        auto* position =
            TryVectorArgument(state,2);
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

// `Room:GetAliveBossesCount()` —— 契约 `tools/pc_contract_docs/Room.md:86/88`
// （`#### int GetAliveBossesCount ( )`）。
//
// ★★ **PC 的绑定本体只有一条算式**（`0x448020`）：`mov edx,[ecx+0x12C4]`（第 2 格）+
//    `mov ecx,[ecx+0x12C0]`（第 1 格）→ `add` → `test` → **`cmovg`**
//    ⇒ `max(0, *(i32*)(Room + 0x12C0) + *(i32*)(Room + 0x12C4))`。
//
// ★★★ **Switch 侧有一个具名函数用的是同一个算式**：`Entity_NPC::get_alive_enemy_count() @ 0x122768`
//    —— `x20 = *(g_Game → +0x21550)`（= **Room***，正是既有的 `kGameRoomPointerOffset`）、
//    `ldr w8,[x20,#0x1a5c]` + `ldr w9,[x20,#0x1a58]` + `add` + **`bic w19,w8,w8,asr#31`**
//    （= `w8 & ~(w8>>31)` = **负数清成 0**，与 PC 的 `test`+`cmovg` 同义）。
//    ⇒ Switch 的两格是 `Room + 0x1A58` / `+0x1A5C`；两条互相印证的算式见
//      `runtime_constants.hpp` 的 `kRoomAliveBossesCountOffset` 段。★ 数值不许平移。
//
// ★ 谁在用：`BOIStageAPI15` 拿它判"这一波 Boss 打完没"（`GetAliveBossesCount() < 1 or Room:IsClear()`）、
//    `BossRushWaveCounter` 拿它数"这波还剩几个 Boss"（`aliveBossesCount > 0`，并与上一帧比较报数）。
//    **返回 nil 会让那两处的比较直接抛错、摘掉整条回调** ⇒ 降级必须答整数。
//
// ★ 为什么这条**手写**而不是数据行：PC 的语义是「**有符号**求和 + **负数清成 0**」，
//    而既有的 `FieldKind::Sum2U32` 是**无符号**相加、**不夹下限** ——
//    复用它会在"某一格是负数"时给出一个巨大的无符号数（计数正常时看不出来、出问题时才炸）。
//    为一个 API 新开一种 kind（还要动门禁四处登记）比写这十几行更贵（与批次 306 / 308 同一笔账）。
//    ★ 房间这条链**复用既有的 `CurrentRoomAddress()`**（与 `Room:GetGridIndex` / `GetGridWidth` 同源）。
//
// ★ 退化：拿不到房间 / 两格读不到 ⇒ 返回 **0**（不是 nil；而 0 在语义上就是"没有活着的 Boss"，
//    与 PC 的 `cmovg` 在零值时给出的也是 0 一致）。
// 批次 310 做、**批次 311 修正归属**：房间里「活着的敌人 / Boss」两个计数对**共用的读法**。
//
// 两对格子各是**两个相邻的 `int32`**，语义 = `max(0, a + b)` —— PC 上
// `Room:GetAliveEnemiesCount @ 0x448000` 与 `Room:GetAliveBossesCount @ 0x448020`
// 就是**同一段模板**（`add` + `test` + **`cmovg`** + `ret`），只有偏移不同
// （敌人 `0x12C0`/`0x12C4`、Boss `0x12C8`/`0x12CC`）；Switch 侧 `0x1447C4` 处两条并列出现、
// 各带同一个夹下限（`bic wN,wN,wN,asr#31`），随后**相减**（敌人 − Boss）。
//
// ★★★ **批次 310 的归属搞反了**：它把「敌人对」（Switch `+0x1A58`）当成了 Boss
//   ⇒ 模组调 `GetAliveBossesCount()` 会拿到**敌人**数。批次 311 修正：
//   **敌人 = `kRoomAliveEnemiesCountOffset`(0x1A58)、Boss = `kRoomAliveBossesCountOffset`(0x1A60)**。
int PushRoomAliveCount(lua_State* state, std::uintptr_t pairOffset) {
    const std::uintptr_t room = CurrentRoomAddress();
    std::int32_t first = 0;
    std::int32_t second = 0;
    //: ★ 本 TU 没有 `ReadEngine`（那是 `game_api.cpp` / `isaac_api.cpp` / `sprite_api.cpp` 各自的
    //:   文件局部助手）⇒ 按本文件既有写法用 `engine_memory::ReadAt`。
    if (room == 0 ||
        !isaac::runtime::engine_memory::ReadAt(room + pairOffset, &first,
                                               &IsEngineMemoryReadable) ||
        !isaac::runtime::engine_memory::ReadAt(room + pairOffset + sizeof(std::int32_t), &second,
                                               &IsEngineMemoryReadable)) {
        lua_pushinteger(state, 0);
        return 1;
    }
    //: 用 64 位做加法：两个 `int32` 相加**可能溢出**（C++ 里有符号溢出是 UB），
    //: 而 PC 的 `add ecx,edx` 是**回绕**的 —— 这里先算宽、再按 PC 的 `cmovg` 语义夹下限。
    const std::int64_t total = static_cast<std::int64_t>(first) + static_cast<std::int64_t>(second);
    const std::int32_t clamped = total > 0 ? static_cast<std::int32_t>(total & 0x7FFFFFFFLL) : 0;
    lua_pushinteger(state, clamped);
    return 1;
}

int RoomGetAliveBossesCount(lua_State* state) {
    luaL_checkudata(state, 1, kRoomMetatable);
    if (lua_gettop(state) != 1) {
        return luaL_error(state, "Room:GetAliveBossesCount accepts no arguments");
    }
    return PushRoomAliveCount(state, kRoomAliveBossesCountOffset);
}

// 批次 311（2026-10-03）：`Room:GetAliveEnemiesCount()` —— 与上一条是**孪生**（PC 上两条紧邻、
// 同一段模板），读的是**前一对**格子 `Room + 0x1A58`/`+0x1A5C`。
// ★ 这一对的归属由**具名函数** `Entity_NPC::get_alive_enemy_count() @ 0x122768` 钉死
//   （函数名自己写着 enemy，读的就是 `+0x1A58`/`+0x1A5C`）—— 详见 `runtime_constants.hpp`。
int RoomGetAliveEnemiesCount(lua_State* state) {
    luaL_checkudata(state, 1, kRoomMetatable);
    if (lua_gettop(state) != 1) {
        return luaL_error(state, "Room:GetAliveEnemiesCount accepts no arguments");
    }
    return PushRoomAliveCount(state, kRoomAliveEnemiesCountOffset);
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
        return PushNativeFallbackInteger(state, kFbRoomGetGridPath, 0);
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
        return PushNativeFallbackInteger(state, kFbRoomGetGridPath, 0);
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
        // 批次 250：读不到房间 ⇒ **nil**（与上面"槽位非法 ⇒ 没有门"同一个口径 ——
        // 这一条 PC 语义本来就允许"没有"）。
        return PushNativeFallbackNil(state, kFbRoomGetDoor);
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
//: 把一个引擎网格实体地址压成 Lua 的 `GridEntity` 句柄。
//:
//: ★ 批次 262 抽出来共用：`Room:GetGridEntity(index)` 与 `Isaac.GridSpawn(...)` 的返回值
//: 是**同一个东西**（后者在 PC 上就是"再读一次那一格的实体指针当返回值"）⇒ 只留这一份实现。
void PushGridEntityHandle(lua_State* state, std::uintptr_t entity) {
    auto* handle = static_cast<LuaRuntime::GridEntityHandle*>(
        lua_newuserdata(state, sizeof(LuaRuntime::GridEntityHandle)));
    handle->entity = isaac::runtime::engine_memory::AsObject(entity);
    luaL_getmetatable(state, LuaRuntime::kGridEntityMetatable);
    lua_setmetatable(state, -2);
}

//: 读网格实体表里第 `index` 项并压成句柄（压不出来就压 `nil`）。**总是**返回 1（压了一个值）。
//:
//: ★ 批次 307（2026-10-03）抽出来共用：`Room:GetGridEntity(index)` 与
//:   `Room:GetGridEntityFromPos(Position)` 读的是**同一张表**（PC 的 `GetGridEntityFromPos`
//:   就是"先把位置算成 index、再读那张表"）⇒ 只留这一份实现（与批次 262 把
//:   `PushGridEntityHandle` 抽出来是同一条纪律：**同一件事不写第二遍**）。
//:
//: ★ `index` 上界：`Room:GetGridEntity` 的实参**没有**范围检查（`RoomGridIndexArgument` 只判
//:   是不是整数）⇒ 这里必须自己挡回绕，否则在宿主上（可读判定恒真）会读飞内存。
int PushGridEntityAtSlot(lua_State* state, std::uintptr_t room, std::int64_t index) {
    if (index < 0) {
        lua_pushnil(state);
        return 1;
    }
    const std::uintptr_t within = kRoomGridEntityTableOffset +
                                  static_cast<std::uintptr_t>(index) * sizeof(std::uintptr_t);
    if (room == 0 || room > UINTPTR_MAX - within) {
        lua_pushnil(state);
        return 1;
    }
    std::uintptr_t entity = 0;
    if (!isaac::runtime::engine_memory::ReadAt(room + within, &entity, &IsEngineMemoryReadable) ||
        entity == 0) {
        lua_pushnil(state);
        return 1;
    }
    PushGridEntityHandle(state, entity);
    return 1;
}

// 批次 435（2026-10-11）：`Room:GetGridEntity` 的**子阶段账**（只在 `PERF_API_WRAPPER=1`
// 的诊断包里有意义；生产包宏为 0 ⇒ 三个变量与全部计时点都不存在、零成本）。
//
// 为什么：DIAG2 量出它 **1.896 µs/次 × 7992.6/s = 251 µs/帧**（Minimap 的账），
// 但"该改哪儿"还没算清 —— 431 的教训 = **热路径改前先算账**。
// 口径：① `ChainTicks` = `ResolveCurrentLevel` + `ReadCurrentGameRoom`（解析链）；
// ② `RestTicks` = 其余（读表项 + `PushGridEntityAtSlot` 里的 `lua_newuserdata` + 元表）。
// ★ `extern "C"` ⇒ 符号表里是无修饰名，`mem.*` 与 ELF 都能直接查（429/431 的教训）。
// ★ 只记**成功主路径**（失败路径罕见且提前 return）。
#if PERF_API_WRAPPER
extern "C" {
std::uint64_t g_GridEntityProbeCalls = 0;
std::uint64_t g_GridEntityProbeChainTicks = 0;
std::uint64_t g_GridEntityProbeRestTicks = 0;
}
#endif

int RoomGetGridEntity(lua_State* state) {
    luaL_checkudata(state, 1, kRoomMetatable);
    const int argumentCount = lua_gettop(state);
    if (argumentCount != 2 || !RoomGridIndexArgument(state, 2, nullptr)) {
        return luaL_error(state, "Room:GetGridEntity accepts one grid index");
    }
    // 网格实体表在 `Room + 0x30`（证据见 `kRoomGridEntityTableOffset`），按网格下标索引、
    // 每项一个 `GridEntity*`。下标越界/空项一律返回 nil（PC 语义："这里没有网格实体"）。
#if PERF_API_WRAPPER
    // ★ 口径（批次 436 起）：T0→T1 = "解析段（缓存查询 + 未命中时的链）"，不再只是"链"。
    const std::uint64_t gridProbeT0 = RuntimePerfTick();
#endif
    // 批次 436：`ReadCurrentGameRoom` 换成**带派发窗口缓存**的版本（435 探针：解析链占单次 91%）。
    // ★ 不再先跑 `ResolveCurrentLevel`：那条链与 `ReadCurrentGameRoom` 重复读同一段前缀，
    //   且依赖 `EngineModuleBase`（宿主 harness 里为 0）；`ReadCurrentGameRoom` 自身已校验
    //   owner/game 非 0（`OwnerNull`/`GameNull`）⇒ 拿不到时同样走下面的 nil 兜底。
    std::uintptr_t roomAddress = 0;
    if (!ResolveCurrentRoomCached(&roomAddress)) {
        return PushNativeFallbackNil(state, kFbRoomGetGridEntity);
    }
    lua_Integer gridIndex = 0;
    if (!RoomGridIndexArgument(state, 2, &gridIndex) || gridIndex < 0) {
        return luaL_error(state, "Room:GetGridEntity accepts one grid index");
    }
#if PERF_API_WRAPPER
    const std::uint64_t gridProbeT1 = RuntimePerfTick();
#endif
    const int gridProbeResult = PushGridEntityAtSlot(state, roomAddress, gridIndex);
#if PERF_API_WRAPPER
    const std::uint64_t gridProbeT2 = RuntimePerfTick();
    ++g_GridEntityProbeCalls;
    g_GridEntityProbeChainTicks += gridProbeT1 - gridProbeT0;
    g_GridEntityProbeRestTicks += gridProbeT2 - gridProbeT1;
#endif
    return gridProbeResult;
}

// `Room:GetGridEntityFromPos(Vector Position)` —— 契约 `tools/pc_contract_docs/Room.md:352/354`
// （`#### [GridEntity](GridEntity.md) GetGridEntityFromPos ( [Vector](Vector.md) Position )`
//   且同页带 `data-altreturn='nil'` ⇒ **"这一格没有东西"就是 nil**）。
//
// ★★ **它既不是一次字段读、也不是一次引擎调用** —— PC 的绑定本体（`0x447F80`）把
//    "世界坐标 → 格坐标"的算术**内联**了，然后**读同一张网格实体表**。逐句（`ecx` = Room）：
//
//      edx  = &Position
//      xmm1 = [0xb6aa3c] = 40.0f     xmm2 = [0xb6a480] = 0.5f
//      gx   = (int)((pos.x - 40.0f) / 40.0f + 0.5f)      ; cvttss2si = 向零截断
//      if (gx < 0 || gx >= *(int*)(this + 0xc))  return 0        ; +0xC  = 网格宽
//      ymm0 = [0xb6ab20] = **120.0f**                     ; ★ y 的起点**不是** 40 而是 120
//      gy   = (int)((pos.y - 120.0f) / 40.0f + 0.5f)
//      if (gy < 0 || gy >= *(int*)(this + 0x10)) return 0        ; +0x10 = 网格高
//      index = *(int*)(this + 0xc) * gy + gx             ; width*gy + gx
//      return *(void**)(this + 4*index + 0x24)           ; 同一张表（PC 表头在 +0x24）
//
// ★★★ **同一套算术在 Switch 侧有独立符号**：`Room::GetGridIndex(Vector2 const&) @ 0x459E3C` ——
//    `mov w8,#-0x3de00000` + `fmov` 出的正是 **-40.0f**、紧随的 `0x42200000` 是 **40.0f**、
//    `fmov s1,#0.5` 是 **0.5f**、`-0x3d100000` 是 **-120.0f**，收尾 `madd w8,w11,w10,w9`
//    就是 `width*gy + gx`，边界也同样是 `[x0+0x14]`（宽）/ `[x0+0x18]`（高）。
//    ★ 而我们**早就把这段复刻进了** `RoomGridCoordinateFromWorld`（`Room:GetGridIndex` 用的就是它）
//      与 `ReadRoomGridDimensions` ⇒ **本条零新增偏移、零新算术**，只把两个既有助手接起来。
//
// ★ 谁在用（语料 4 处）：`IsaacOnTwitchReloaded` 拿 `GetGridEntityFromPos(Vector(510, 370))` 找按钮、
//   还有一处 `== nil` 判断与一个 `while … == nil` 的寻路循环；`BOIStageAPI15` 拿 `door.Position` 找门；
//   `ChallengeAPI` 在踩板子时找格子上的实体。**返回 nil 会让它们的分支静默走错** ⇒ 这条必须真的能读。
//
// ★ 退化（与 `Room:GetGridEntity` 同一口径）：拿不到房间 / 表项读不到 / 表项是空指针
//   ⇒ **压 nil**（PC 的 `data-altreturn='nil'` 就是这个语义），**不报错**。
int RoomGetGridEntityFromPos(lua_State* state) {
    luaL_checkudata(state, 1, kRoomMetatable);
    if (lua_gettop(state) != 2) {
        return luaL_error(state, "Room:GetGridEntityFromPos accepts one Vector");
    }
    auto* position =
        TryVectorArgument(state,2);
    if (position == nullptr) {
        return luaL_error(state, "Room:GetGridEntityFromPos accepts one Vector");
    }
    const std::uintptr_t room = CurrentRoomAddress();
    std::uint32_t width = 0;
    std::uint32_t height = 0;
    if (room == 0 || !ReadRoomGridDimensions(room, &width, &height)) {
        lua_pushnil(state);
        return 1;
    }
    //: ★ 复用 `Room:GetGridIndex(Vector)` 用的那**同一个**换算（`(pos − 起点)/40 + 0.5` 向零截断）。
    const std::int32_t gridX = RoomGridCoordinateFromWorld(position->x, kRoomGridWorldOffsetX);
    const std::int32_t gridY = RoomGridCoordinateFromWorld(position->y, kRoomGridWorldOffsetY);
    if (gridX < 0 || gridY < 0 || static_cast<std::uint32_t>(gridX) >= width ||
        static_cast<std::uint32_t>(gridY) >= height) {
        lua_pushnil(state);  // 越界 = "这里没有网格实体"（PC 也是返回 0 ⇒ nil）
        return 1;
    }
    const std::int64_t index = static_cast<std::int64_t>(width) * gridY + gridX;
    return PushGridEntityAtSlot(state, room, index);
}

//: 从实参拿"引擎网格实体地址"：**`GridEntity` 与 `GridEntity_Door` 两种元表都认**。
//:
//: 为什么必须有它（批次 078 的宿主门禁当场教出来的）：PC 里门**同时是** `GridEntity`，
//: 模组会写 `door:GetVariant()`；而我们给门的是自己的元表 ⇒ 用
//: `luaL_checkudata(state, 1, kGridEntityMetatable)` 会直接抛
//: "GridEntity expected"。两种句柄的**第一个成员都是实体指针**，所以按布局取是安全的。
void* GridEntityArgument(lua_State* state, int index) {
    // ★ 批次 304（2026-10-03）：判据提到 `isaac_api.cpp` 的 `GridEntityHandleArgument` ——
    //   数据行的接收者（`FieldReceipt::GridEntity`）也要同一份，而它住在**另一个 TU**。
    //   这里保留这个名字只是"手写路径的既有叫法"，实现**只有一份**。
    return isaac::runtime::GridEntityHandleArgument(state, index);
}

//: 批次 342（2026-10-04）：`GridEntityDesc` 那**一张表**的唯一构造点 ——
//: 属性 `GridEntity.Desc` 与方法 `GridEntity:GetSaveState()` **共用它**。
//:
//: 为什么必须共用：PC 契约 `tools/pc_contract_docs/GridEntity.md:49` **逐字**写着
//: 「Both the `Desc` property and the `GetSaveState()` method return the exact same
//: `GridEntityDesc` object. The game devs advise to use `GetSaveState()` instead of `Desc`.」
//: ⇒ 两处各写一份的话，将来补一个字段就会只补一边（这正是本项目"同一份判据只有一处"的老规矩）。
//:
//: 表里**只放已取证的三个字段**（`Type` `+0x08` / `Variant` `+0x10` / `VarData` `+0x1C`）——
//: 三格都来自「`GridEntity::Init(const Desc&)` 把 `Desc[0x00..0x1F]` 拷到对象 `+0x08..+0x27`」
//: 这条结构证据（见 `kGridEntityTypeOffset` 的注释）。没取证的成员（`State`/`CollisionClass`/
//: `SpawnSeed`/`VariableSeed`）**不编值**：宁可让模组拿到 `nil`（那是"该字段没实现"的可见信号），
//: 也不能给一个恒 0 的假值。
//:
//: 返回 false = 底层对象地址不可用（实体已销毁一类）⇒ 调用方自己决定压什么。
bool PushGridEntityDescTable(lua_State*state,std::uintptr_t entity) {
    return PushApi500GridDesc(state,entity);
}

// `GridEntity:GetSaveState()`（批次 342）—— PC 的绑定本体（`0x71FF60`）只有
// `lea eax,[ecx+0x4]` + `ret` ⇒ 它是个**指针 getter**（返回 `&this->desc`），
// **不是**把 `GridEntityDesc` 按值返回 ⇒ 我们这边与 `Desc` 属性同一条路：返回那张表。
// 契约：`tools/pc_contract_docs/GridEntity.md:46`（正文 `:49` 说明两者同一个对象）。
// ★ 降级档与同族的 `GetGridIndex()`/`GetType()` 一致：拿不到实体就压 `nil`、**不抛错**
//   （报错会把整条模组回调摘掉）。★ 这个 `nil` 是**偏离**吗？不是：PC 上 `GetSaveState()`
//   在实体已销毁时同样是 `nil`（它返回的是成员地址，句柄失效时胶水层给不出对象）。
int GridEntityGetSaveState(lua_State* state) {
    if (lua_gettop(state) != 1) {
        return luaL_error(state, "GridEntity:GetSaveState accepts no arguments");
    }
    void* entityPointer = GridEntityArgument(state, 1);
    if (entityPointer == nullptr) {
        return luaL_error(state, "GridEntity:GetSaveState expects a grid entity");
    }
    const std::uintptr_t entity = isaac::runtime::engine_memory::AddressOf(entityPointer);
    if (!PushGridEntityDescTable(state, entity)) {
        lua_pushnil(state);
        return 1;
    }
    return 1;
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

// ---- 批次 276（2026-10-02）：`GridEntity` 的 `GetGridIndex()` 与 7 条子类转换 --------------------
//
// 为什么这一批能便宜地做掉：转换用的 vtable 偏移**不用一个个反汇编去找** —— 7 个子类的 `_ZTV`
// 符号都在 dynsym 里逐字可查，而「vtable 指针 = `_ZTV` 地址 + 0x10」这条式子**已经被既有常量验证过**
// （见 `runtime_constants.hpp` 批次 276 段）。判据本身与 `Entity:ToPlayer()` 一族**逐字相同**：
// 读对象首字、与 `base + <该常量>` 比。

// `GridEntity:GetGridIndex()` —— PC 契约 `tools/pc_contract_docs/GridEntity.md`，语料 4 处。
// 读 `GridEntity + 0x28`（`kGridEntityGridIndexOffset`，早有取证：网格位置由它算出来，
// 见 `runtime_constants.hpp` 里那一段与 `test_lua_grid_entity_fields.py` 的假房间夹具）。
// ★ 降级与同一族的 `GetType()` 一致：读不到就压 **`nil`**（不是 0 —— 0 是"第 0 格"这个有意义的答案）。
int GridEntityGetGridIndex(lua_State* state) {
    if (lua_gettop(state) != 1) {
        return luaL_error(state, "GridEntity:GetGridIndex accepts no arguments");
    }
    void* entityPointer = GridEntityArgument(state, 1);
    if (entityPointer == nullptr) {
        return luaL_error(state, "GridEntity:GetGridIndex expects a grid entity");
    }
    const std::uintptr_t entity = isaac::runtime::engine_memory::AddressOf(entityPointer);
    std::uint32_t index = 0;
    if (entity == 0 ||
        !isaac::runtime::engine_memory::ReadAt(entity + kGridEntityGridIndexOffset, &index,
                                               &IsEngineMemoryReadable)) {
        lua_pushnil(state);
        return 1;
    }
    lua_pushinteger(state, static_cast<lua_Integer>(index));
    return 1;
}

//: 7 条转换共同的那一段：读对象首字（vptr），与 `base + vtableOffset` 比。
//: 命中 ⇒ 压一个**基类 `GridEntity` 视图**的句柄；不命中 ⇒ 压 `nil`（与 `Entity:ToPlayer()` 同口径）。
//:
//: ★ 为什么给基类视图而不是"子类视图"：我们这套里子类视图**还不存在**
//:   （`Entity:ToFamiliar()` 也是压 `Entity` 元表的句柄 —— 同一个先例）。
//:   代价写在 `docs` 与本批存档里：`grid:ToRock():UpdateAnimFrame()` 这类**子类专有方法**
//:   仍然拿不到（那是 `needs_new_receiver` 里的另一批活儿），但语料里把转换**当真假判断**用的
//:   那些点（`if grid:ToPoop() then … elseif grid:ToTNT() then …`）从这一批起就能正常走。
int PushGridEntityCast(lua_State* state, std::uintptr_t vtableOffset, const char* api) {
    if (lua_gettop(state) != 1) {
        return luaL_error(state, "%s accepts no arguments", api);
    }
    void* entityPointer = GridEntityArgument(state, 1);
    if (entityPointer == nullptr) {
        return luaL_error(state, "%s expects a grid entity", api);
    }
    const std::uintptr_t entity = isaac::runtime::engine_memory::AddressOf(entityPointer);
    const std::uintptr_t base = EngineModuleBase();
    std::uintptr_t vtable = 0;
    if (entity == 0 || base == 0 || base > UINTPTR_MAX - vtableOffset ||
        !isaac::runtime::engine_memory::ReadAt(entity, &vtable, &IsEngineMemoryReadable) ||
        vtable != base + vtableOffset) {
        lua_pushnil(state);
        return 1;
    }
    PushGridEntityHandle(state, entity);
    return 1;
}

// 七条转换：契约形态都是 `GridEntityXxx ToXxx ( )`（0 参、返回子类视图或 `nil`）。
int GridEntityToPit(lua_State* state) {
    return PushGridEntityCast(state, kGridEntity_PitVtableOffset, "GridEntity:ToPit");
}

int GridEntityToRock(lua_State* state) {
    return PushGridEntityCast(state, kGridEntity_RockVtableOffset, "GridEntity:ToRock");
}

//: ★ `ToDoor()` 这一条也压**基类** `GridEntity` 视图（不是 `GridEntityDoor` 视图）：
//: 门的视图（`DoorHandle`）带一个 `slot`（`Room:GetDoor(slot)` 才有），而 `ToDoor()` 没有槽位可比 ——
//: 压一个槽位不明的门句柄会让 `door.TargetRoomIndex` 之类**读错格子**，比给基类视图危险得多。
int GridEntityToDoor(lua_State* state) {
    return PushGridEntityCast(state, kGridEntity_DoorVtableOffset, "GridEntity:ToDoor");
}

int GridEntityToTnt(lua_State* state) {
    return PushGridEntityCast(state, kGridEntity_TNTVtableOffset, "GridEntity:ToTNT");
}

int GridEntityToPoop(lua_State* state) {
    return PushGridEntityCast(state, kGridEntity_PoopVtableOffset, "GridEntity:ToPoop");
}

int GridEntityToPressurePlate(lua_State* state) {
    return PushGridEntityCast(state, kGridEntity_PressurePlateVtableOffset,
                              "GridEntity:ToPressurePlate");
}

int GridEntityToSpikes(lua_State* state) {
    return PushGridEntityCast(state, kGridEntity_SpikesVtableOffset, "GridEntity:ToSpikes");
}

// `GridEntity:Init(int Seed)` —— PC 契约 `tools/pc_contract_docs/GridEntity.md` 的
// `void Init ( int Seed )`，语料 15 处。
//
// 引擎入口 `GridEntity::Init(unsigned)` @ `0x37E438`，取证与三条判据写在
// `runtime_constants.hpp` 的 `kGridEntityInitOffset` 段（要点：`w1` 就是 Seed；
// 它把种子写进 `+0x18`，与批次 262 为 `Isaac.GridSpawn` 记下的那一格**互证**；
// 函数内部再走虚表分派到各子类的 `InitSubclass()` ⇒ 调基类这条正是 PC 的路径）。
//
// ★ 同址附近还有 `GridEntity::Init(Desc const&)` @ `0x37E4BC` —— 我们**只**接契约里那一参重载；
//   真有人按 `Desc` 调，会在参数闸门那一关报出来（可见，不是静默错）。
//
// 失败降级：拿不到网格实体（句柄失效）或入口对不上 ⇒ **什么都不做、不报错**（PC 返回 `void`）。
int GridEntityInit(lua_State* state) {
    if (lua_gettop(state) != 2 || !isaac::runtime::IsIntegerArgument(state, 2)) {
        return luaL_error(state, "GridEntity:Init expects a seed");
    }
    void* entityPointer = GridEntityArgument(state, 1);
    if (entityPointer == nullptr) {
        return luaL_error(state, "GridEntity:Init expects a grid entity");
    }
    const unsigned int seed = static_cast<unsigned int>(lua_tointegerx(state, 2, nullptr));
    const std::uintptr_t method =
        ResolveEngineMethodEntry(kGridEntityInitOffset, kGridEntityInitExpectedBytes);
    if (method == 0) {
        return 0;
    }
    using GridEntityInitFn = void (*)(void*, unsigned int);
    isaac::runtime::engine_call::AsFunction<GridEntityInitFn>(method)(entityPointer, seed);
    return 0;
}

// ---- 批次 284（2026-10-02）：`GridEntityDoor` 的三条 -------------------------------------------
//
// 接收者与 `GridEntity:Init` 一族**同一个助手**（`GridEntityArgument`）—— 它本来就同时接受
// `GridEntity` 与 `GridEntityDoor` 两张元表 ⇒ 这三条**不需要任何新的接收者设施**。
// 引擎入口都在 `GridEntity_Door` 上，且**各只有一份实现**（核实方法与更正写在
// `runtime_constants.hpp` 的批次 284 段）。
//
// 三条的失败口径：拿不到门（句柄失效）或入口对不上 ⇒ `Open`/`Close` **什么都不做、不报错**
// （PC 返回 `void`）；`IsTargetRoomArcade` 给 **`false`**（保守那一边）。

// `GridEntityDoor:Open()` —— PC 契约 `tools/pc_contract_docs/GridEntityDoor.md:73`，语料 1 处。
int GridEntityDoorOpen(lua_State* state) {
    if (lua_gettop(state) != 1) {
        return luaL_error(state, "GridEntityDoor:Open accepts no arguments");
    }
    void* entityPointer = GridEntityArgument(state, 1);
    if (entityPointer == nullptr) {
        return luaL_error(state, "GridEntityDoor:Open expects a door");
    }
    const std::uintptr_t method =
        ResolveEngineMethodEntry(kGridEntityDoorOpenOffset, kGridEntityDoorOpenExpectedBytes);
    if (method == 0) {
        return 0;
    }
    using GridEntityDoorOpenFn = void (*)(void*);
    isaac::runtime::engine_call::AsFunction<GridEntityDoorOpenFn>(method)(entityPointer);
    return 0;
}

// `GridEntityDoor:Close(boolean Force)` —— 同页第 33 行，语料 2 处。
// ★ `Force` **不是摆设**：反汇编 `0x382110` 是 `tbnz w1, #0, 0x382120` —— variant==1 且
//   "不强制"时直接返回，其余才真去关门（见常量段）。所以参数照传，不做任何取舍。
int GridEntityDoorClose(lua_State* state) {
    if (lua_gettop(state) != 2 || lua_type(state, 2) != LUA_TBOOLEAN) {
        return luaL_error(state, "GridEntityDoor:Close expects a boolean");
    }
    void* entityPointer = GridEntityArgument(state, 1);
    if (entityPointer == nullptr) {
        return luaL_error(state, "GridEntityDoor:Close expects a door");
    }
    const bool force = lua_toboolean(state, 2) != 0;
    const std::uintptr_t method =
        ResolveEngineMethodEntry(kGridEntityDoorCloseOffset, kGridEntityDoorCloseExpectedBytes);
    if (method == 0) {
        return 0;
    }
    using GridEntityDoorCloseFn = void (*)(void*, bool);
    isaac::runtime::engine_call::AsFunction<GridEntityDoorCloseFn>(method)(entityPointer, force);
    return 0;
}

// `GridEntityDoor:IsTargetRoomArcade()` —— 同页第 68 行，语料 2 处，返回布尔。
int GridEntityDoorIsTargetRoomArcade(lua_State* state) {
    if (lua_gettop(state) != 1) {
        return luaL_error(state, "GridEntityDoor:IsTargetRoomArcade accepts no arguments");
    }
    void* entityPointer = GridEntityArgument(state, 1);
    if (entityPointer == nullptr) {
        return luaL_error(state, "GridEntityDoor:IsTargetRoomArcade expects a door");
    }
    const std::uintptr_t method = ResolveEngineMethodEntry(
        kGridEntityDoorIsTargetRoomArcadeOffset, kGridEntityDoorIsTargetRoomArcadeExpectedBytes);
    if (method == 0) {
        lua_pushboolean(state, 0);
        return 1;
    }
    using GridEntityDoorIsTargetRoomArcadeFn = bool (*)(const void*);
    lua_pushboolean(
        state,
        isaac::runtime::engine_call::AsFunction<GridEntityDoorIsTargetRoomArcadeFn>(method)(
            entityPointer) ?
            1 :
            0);
    return 1;
}


//: 批次 294（2026-10-03）：`GridEntityDoor:IsRoomType(RoomType)`（4 处 / 3 个模组）。
//:
//: PC 的绑定本体（`tools/pc_exe_binding.py IsRoomType --disasm`，VA `0x5B7550`）只有六条指令：
//:     `mov eax, [ebp+8]`（实参）→ `cmp [ecx+0x158], eax` + `je → true`
//:     → `cmp [ecx+0x15c], eax` + `je → true` → 否则 `xor al,al`
//: 即「实参 == 门自己的房型 **或** 实参 == 门通向的房型」——**没有任何别的副作用**。
//:
//: Switch 侧那两个字段我们**早就有具名证据**（`GridEntity_Door::InitSubclass @ 0x385F98` 的存值序列、
//: 以及写方 `GridEntity_Door::SetRoomTypes(eRoomType, eRoomType) @ 0x385A78`）：
//:   `kGridEntityDoorCurrentRoomTypeOffset`（`+0x1A4`，门当前所在房间的房型）与
//:   `kGridEntityDoorTargetRoomTypeOffset`（`+0x1A8`，门通向的房间的房型）。
//: ⇒ 本函数逐条照 PC 做，**不新增偏移、不调引擎函数**（引擎里没有 `IsRoomType` 这个符号）。
//:
//: ★ 这是"手写处理器"而不是字段行：一行只有一个返回值、两个字段是"或"的关系，
//:   现有 kind 里没有"拿实参跟两个字段比"的形状（`BoolEquals` 比的是行里的常量）。
//:   代价是这条 API 花钱（≈ 100 字节代码），但同族本来就是手写视图（见 `GridEntityDoorIndex`）。
//: ★ 读不到（门句柄失效 / 内存不可读）⇒ 答 `false`、**不抛错**（与门族其它方法同口径）。
int GridEntityDoorIsRoomType(lua_State* state) {
    if (!isaac::runtime::IsIntegerArgument(state, 2)) {
        return luaL_error(state, "GridEntityDoor:IsRoomType expects one integer argument");
    }
    void* doorPointer = GridEntityArgument(state, 1);
    if (doorPointer == nullptr) {
        lua_pushboolean(state, 0);
        return 1;
    }
    const std::uintptr_t door = isaac::runtime::engine_memory::AddressOf(doorPointer);
    const std::uint32_t wanted = static_cast<std::uint32_t>(
        static_cast<std::int64_t>(lua_tointegerx(state, 2, nullptr)));
    for (const std::uintptr_t offset : {kGridEntityDoorCurrentRoomTypeOffset,
                                        kGridEntityDoorTargetRoomTypeOffset}) {
        std::uint32_t value = 0;
        if (isaac::runtime::engine_memory::ReadAt(door + offset, &value,
                                                  &IsEngineMemoryReadable) &&
            value == wanted) {
            lua_pushboolean(state, 1);
            return 1;
        }
    }
    lua_pushboolean(state, 0);
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
std::uintptr_t ResolveGridRngReference(const LuaRuntime::RngHandle* rng) noexcept {
    const auto room = CurrentRoomAddress();
    if (room == 0 || room != rng->container) { return 0; }
    if (rng->offset == kRoomDoorObjectTableOffset) {
        if (rng->index > static_cast<std::uintptr_t>(kRoomDoorSlotMaximum)) { return 0; }
    } else {
        std::uint32_t width = 0, height = 0;
        if (!ReadRoomGridDimensions(room, &width, &height) ||
            rng->index >= static_cast<std::uint64_t>(width) * height) { return 0; }
    }
    std::uintptr_t current = 0;
    if (!isaac::runtime::engine_memory::ReadAt(
        room + rng->offset + rng->index * sizeof(std::uintptr_t),
        &current, &IsEngineMemoryReadable) || current != rng->owner || current == 0) { return 0; }
    return current <= UINTPTR_MAX - kGridEntityRngOffset ? current + kGridEntityRngOffset : 0;
}

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
    rng->resolver = ResolveGridRngReference;
    rng->owner = entity;
    rng->container = CurrentRoomAddress();
    // 门可能来自Room:GetDoor，也可能经ToDoor得到基类视图；按真实门表找owner，
    // 避免依赖Lua视图类型或猜GridIndex就是DoorSlot。
    bool foundDoor = false;
    for (std::uintptr_t slot = 0; slot <= static_cast<std::uintptr_t>(kRoomDoorSlotMaximum) &&
                                  rng->container != 0; ++slot) {
        std::uintptr_t current = 0;
        if (isaac::runtime::engine_memory::ReadAt(
            rng->container + kRoomDoorObjectTableOffset + slot * sizeof(std::uintptr_t),
            &current, &IsEngineMemoryReadable) && current == entity) {
            rng->index = slot;
            rng->offset = kRoomDoorObjectTableOffset;
            foundDoor = true; break;
        }
    }
    if (!foundDoor) {
        std::int32_t gridIndex = -1;
        if (!isaac::runtime::engine_memory::ReadAt(entity + kGridEntityGridIndexOffset, &gridIndex,
                                                &IsEngineMemoryReadable) || gridIndex < 0) {
            lua_pop(state, 1); lua_pushnil(state); return 1;
        }
        rng->index = static_cast<std::uintptr_t>(gridIndex);
        rng->offset = kRoomGridEntityTableOffset;
    }
    luaL_getmetatable(state, LuaRuntime::kRngMetatable);
    lua_setmetatable(state, -2);
    return 1;
}


//: 批次 298（2026-10-03）：`GridEntity:GetSprite()`（14 处 / 1 个模组）与
//: `GridEntityRock:GetSprite()`（清单里另记 14 处，但**没有契约页、也没有接收者证据** ⇒
//: 它是同一批调用点的派生行，见 `build_api_restore_worklist.py` 的 `CONFIRMED_PSEUDO_GAPS`）。
//:
//: PC 侧两个绑定本体都是**一跳直读成员**、而且两个类偏移不同：
//:   `GridEntity:GetSprite @ 0x427440` = `lea eax,[ecx+0x3C]`；
//:   `GridEntityRock:GetSprite @ 0x427680` = `lea eax,[ecx+0x40]`。
//: ★★ **Switch 侧只有一格**：`GridEntity + 0x48` —— 证据是"引擎自己把它当 ANM2 用"
//:   （与 `Entity+0x50` 同一手法）：`GridEntity_Rock::InitSubclass @ 0x392E98` 里
//:   `add x21, x19, #0x48` → `bl ANM2::Load("gfx/grid/grid_rock.anm2")`；
//:   同一函数体的 `Render @ 0x392B1C` / `update_anim_frame @ 0x38FD88` 也用它；
//:   **另有 10 个子类的 `ANM2::Load` 写同一格**（Decoration / Door / Fire / Gravity / Lock /
//:   Poop / PressurePlate / Spikes / Stairs / TrapDoor）⇒ 基类与子类同格。
//:   ⇒ 两条 API 在我们的实现里读**同一个偏移**，所以 `rock:GetSprite()` 走同一段代码就对了
//:   （`ToRock()` 压的本来就是基类 `GridEntity` 视图）。完整证据见 `runtime_constants.hpp`
//:   的批次 298 段。
//: ★ 交出去的 `Sprite` 句柄指向**引擎网格实体内部**的内存 ⇒ 打 `kSpriteSourceEngineGridEntity`
//:   标记（`__gc` 不放手），每次访问重新做存活判据（网格实体会随炸石头/换房间销毁）。
//: ★ 降级：拿不到网格实体（句柄为空 / 已失效）⇒ 返回 **nil**、**不报错**（与 `Entity:GetSprite`
//:   同一口径：报错会把整条模组回调摘掉，而 nil 至少让 `if sprite then` 走另一条路）。
int GridEntityGetSprite(lua_State* state) {
    if (lua_gettop(state) != 1) {
        return luaL_error(state, "GridEntity:GetSprite accepts no arguments");
    }
    void* gridEntity = GridEntityArgument(state, 1);
    if (gridEntity == nullptr) {
        lua_pushnil(state);
        return 1;
    }
    const std::uintptr_t entity = isaac::runtime::engine_memory::AddressOf(gridEntity);
    if (!isaac::runtime::IsLiveGridEntityPointer(entity)) {
        lua_pushnil(state);
        return 1;
    }
    return PushEngineGridEntitySpriteHandle(state, gridEntity);
}

// `Room:GetRenderScrollOffset()`（PC 文档 `Room.md:473`，返回 `const Vector`）：
// 房间渲染的滚动偏移。EID 用它把世界坐标换算到屏幕坐标。
//
// 偏移 `+0x1938` 的证据（`tools/layout_tables/room.json`）：引擎自己的
// `Room::WorldToScreenPosition` 里先 `mov w8, #0x1938`、再 `add x1, x19, x8`，
// 把这个字段的**地址**交给 `Vector2::operator+` —— 也就是"世界→屏幕"要加上的那个向量。
// `build_layout_table.py --verify` 会重新反汇编核对这条证据。
// 批次 250：把两个 float 打包成**新的** `Vector` 句柄（正常路径与回退路径共用一份，
// 免得"每次返回新 userdata"这条口径在两处各写一遍、日后漂开）。
int PushFloatVector(lua_State* state, float x, float y) {
    auto* vector = static_cast<LuaRuntime::VectorHandle*>(
        lua_newuserdata(state, sizeof(LuaRuntime::VectorHandle)));
    vector->x = x;
    vector->y = y;
    luaL_getmetatable(state, LuaRuntime::kVectorMetatable);
    lua_setmetatable(state, -2);
    return 1;
}

// 回退出口：记一笔探针 + 给零向量（PC 这一条返回 `Vector`，给"该类型下的空值"）。
int PushNativeFallbackVector(lua_State* state, NativeFallbackApi api) {
    RecordNativeStateFallback(api);
    return PushFloatVector(state, 0.0F, 0.0F);
}

int RoomGetRenderScrollOffset(lua_State* state) {
    luaL_checkudata(state, 1, kRoomMetatable);
    if (lua_gettop(state) != 1) {
        return luaL_error(state, "Room:GetRenderScrollOffset accepts no arguments");
    }
    void* room = nullptr;
    if (ReadCurrentGameRoom(GameOwnerSlot(), &room) != GameRoomObservation::Success ||
        room == nullptr) {
        // 批次 250：读不到 ⇒ **零向量**（PC 这一条返回 `Vector`，不是可空对象 ⇒ 给值而不是 nil）。
        return PushNativeFallbackVector(state, kFbRoomGetRenderScrollOffset);
    }
    const std::uintptr_t address = isaac::runtime::engine_memory::AddressOf(room);
    float x = 0.0F;
    float y = 0.0F;
    const std::uintptr_t scrollOffset = address + layout::kRoomRenderScrollOffsetOffset;
    if (!IsEngineMemoryReadable(scrollOffset, sizeof(x) + sizeof(y))) {
        return PushNativeFallbackVector(state, kFbRoomGetRenderScrollOffset);
    }
    // 上面那次判定覆盖了整段 8 字节 ⇒ 这两个 float 只取值、不重复问内核（L1 `LoadVerifiedAt`）。
    static_cast<void>(isaac::runtime::engine_memory::LoadVerifiedAt(scrollOffset, 0, &x));
    static_cast<void>(isaac::runtime::engine_memory::LoadVerifiedAt(scrollOffset, 1, &y));
    // 每次返回**新的** `Vector` userdata：别名会让 `room:GetRenderScrollOffset().X = 1`
    // 这类写法改到下一次读取的结果上（与 `Entity.Position` 同一口径）。
    return PushFloatVector(state, x, y);
}

// `Room:GetRenderMode()` —— PC 契约 `tools/pc_contract_docs/Room.md:468`，
// 正文 `:469` 逐字：「Returns a RenderMode enum which can be used to render entities differently
// depending on context (i.e. custom water reflections).」
//
// 语料用法只有一处（`BOIStageAPI15/scripts/stageapi/grid/customdoors.lua:415`）：
//   `if shared.Room:GetRenderMode() == RenderMode.RENDER_NORMAL then …:Render(…) end`
// —— 值用在一个**相等判断**上。★ 所以"缺这个方法"的后果不是"少画一点"，而是
// `attempt to call a nil value (method 'GetRenderMode')` ⇒ **整条 `MC_POST_EFFECT_RENDER`
// 回调被摘掉**（本项目最重的一档后果）。
//
// ★★ 值为什么是常量（`Placeholder` 偏离，登记在 `api_deviation.cpp` 的 `0x04010024`）：
//   PC 侧的取值是**一条 6 字节访问器**（`tools/pc_exe_binding.py GetRenderMode` ⇒
//   绑定函数 VA `0x422DB0` = `mov eax,[ecx+0x12BC]; ret`），也就是说 PC 上它就是
//   `Room + 0x12BC` 那个字。**Switch 侧的偏移没有取证到**：
//     * 符号表里 `eRenderMode` 只出现在 `EntityList::RenderStart(eRenderMode)` 的参数上
//       （没有任何 `GetRenderMode` 之类的访问器符号）；
//     * `RenderStart` 在整份镜像里**没有一处直接 `bl`**（扫过全镜像的 BL 立即数）；
//     * **PC 的偏移不能平移过来**：PC 是 32 位（指针 4 字节）、Switch 是 64 位（8 字节），
//       同一个 `RenderScrollOffset` 在 PC 是 `0x1204`、在 Switch 是 `0x1938` —— 差值本身
//       就是证据表明两边的成员布局不同 ⇒ 按 delta 推算必错，而**读错一格会静默给错值**
//       （那正是 `Luck` 那次的形态）。
//   ⇒ 给 `RENDER_NORMAL`（`1`）。为什么是它而不是 0：0 是 `RENDER_NULL`（"当前没有在渲染房间
//   实体"），而这条 API 被调用的时机（渲染回调里）引擎**一定在渲染**；`1` 是"干燥房间里的
//   正常渲染"，也就是绝大多数房间的真值 ⇒ 模组那个相等判断在绝大多数情况下与 PC 同结论。
//   已知后果（写进偏离台账）：在**有水/反射**的房间里，模组会把自定义门的高亮多画一层。
int RoomGetRenderMode(lua_State* state) {
    luaL_checkudata(state, 1, kRoomMetatable);
    if (lua_gettop(state) != 1) {
        return luaL_error(state, "Room:GetRenderMode accepts no arguments");
    }
    // `RenderMode.RENDER_NORMAL`（`analysis/isaacdocs-snapshot/docs/enums/RenderMode.md`：1）。
    lua_pushinteger(state, 1);
    return 1;
}

// `Room:GetRenderSurfaceTopLeft()` —— PC 契约 `tools/pc_contract_docs/Room.md:478`（返回 `const
// Vector`，`.const` 徽章），正文 `:479` 逐字：「The position the floor and wall textures will be
// rendered at.」
//
// 语料用法只有一处（同一模组 `stageapi/library/misc.lua:40`）：
//   `return shared.Room:GetRenderSurfaceTopLeft() * 2 + Vector(442,286)` —— 用来推
//   `GetScreenBottomRight()`，再由它算模组自己的 `GetScreenScale()`/`GetScreenCenterPosition()`。
// ★ 同上的理由：**缺这个方法会让整段取屏幕尺寸的代码抛错**，所以给值而不是不给。
//
// ★★ 值为什么是**零向量**（`Placeholder` 偏离，登记在 `api_deviation.cpp` 的 `0x04010025`）：
//   PC 侧同样是访问器（VA `0x68F4E0` = `lea eax,[ecx+0x11fc]; ret`，返回 `Room + 0x11FC`
//   那个 Vector 的地址），PC 上它与 `RenderScrollOffset`（`+0x1204`）**相邻**；但 Switch 侧
//   这个字段没有符号、也没有可用的调用点做锚点：
//     * 扫过全镜像里 `0x1930`（按"相邻 8 字节"的假设）的访存点，它们**全部属于 `Entity_Player`**
//       （现场有 `sync_consumable_counts(Entity_Player*, …)` / `ProceduralItemInventory` /
//       `CreateWeapon` 三个独立佐证）—— 是一次**假阳性**，已排除；
//     * `Room::WorldToScreenPosition @ 0x489354` 只碰 `0x1938`，邻域里没有第二个 Vector 字段。
//   ⇒ **不编一个看起来像真值的常量**（那是本项目最忌讳的假读数），给零向量：模组的
//   `GetScreenBottomRight()` 会得到 `(442,286)`、比例约 0.92 —— **量级正确、方向正确、只是偏小**，
//   比"抛错摘掉整条回调"或"编一个像真的值"都好。取证到字段后应把这里换成真读。
int RoomGetRenderSurfaceTopLeft(lua_State* state) {
    luaL_checkudata(state, 1, kRoomMetatable);
    if (lua_gettop(state) != 1) {
        return luaL_error(state, "Room:GetRenderSurfaceTopLeft accepts no arguments");
    }
    return PushNativeFallbackVector(state, kFbRoomGetRenderSurfaceTopLeft);
}

// `Room:WorldToScreenPosition(Vector)`（批次 10）：把世界坐标换算成屏幕坐标。// PC 文档 `Room.md:974`，EID 用它把实体位置画到屏幕上。
//
// **换算方式直接来自引擎自己的实现**（`Room::WorldToScreenPosition @ 0x489354` 的反汇编）：
//   `GetRenderPosition(世界坐标, true) + Room.RenderScrollOffset + Game.ToScreenAdjust`
// 三处偏移/入口的证据见 `runtime_constants.hpp` 里那三个常量各自的注释。
//
// 失败一律报 Lua 错误（PC 返回 Vector，编一个 (0,0) 会让 Mod 把东西画到左上角）。
//
// ★ 批次 195（2026-09-29）：算术提到 `TransformWorldPosition`（**同一份实现**同时服务
//   `Isaac.WorldToScreen` / `Isaac.WorldToRenderPosition`）。这个 handler 只剩参数校验与压栈 ——
//   "两条口径的差别就是那两处偏移"这件事从此只在一处表达（两处各写一份必然漂）。
int RoomGetWorldToScreenPosition(lua_State* state) {
    luaL_checkudata(state, 1, kRoomMetatable);
    if (lua_gettop(state) != 2) {
        return luaL_error(state, "Room:WorldToScreenPosition expects a Vector");
    }
    auto* input = TryVectorArgument(state,2);
    if (input == nullptr) {
        return luaL_error(state, "Room:WorldToScreenPosition expects a Vector");
    }
    float screen[2] = {input->x, input->y};
    if (!TransformWorldPosition(&input->x, screen, WorldTransformTarget::kScreen)) {
        return luaL_error(state, "Room:WorldToScreenPosition is unavailable in this build");
    }
    auto* result = static_cast<LuaRuntime::VectorHandle*>(
        lua_newuserdata(state, sizeof(LuaRuntime::VectorHandle)));
    result->x = screen[0];
    result->y = screen[1];
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
        return PushNativeFallbackInteger(state, kFbItemPoolGetLastPool, 0);
    }
    const std::uintptr_t address = isaac::runtime::engine_memory::AddressOf(itemPool);
    std::uint32_t lastPool = 0;
    if ((address & (alignof(std::uint32_t) - 1)) != 0 ||
        address > UINTPTR_MAX - kItemPoolLastPoolOffset ||
        !isaac::runtime::engine_memory::ReadAt(address + kItemPoolLastPoolOffset, &lastPool,
                                               &IsEngineMemoryReadable)) {
        return PushNativeFallbackInteger(state, kFbItemPoolGetLastPool, 0);
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
        return PushNativeFallbackInteger(state, kFbItemPoolGetCollectible, 0);
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
        return PushNativeFallbackBoolean(state, kFbItemPoolIsPillIdentified, false);
    }
    const std::uintptr_t address = isaac::runtime::engine_memory::AddressOf(itemPool);
    std::uint8_t identified = 0;
    if (address == 0 || address > UINTPTR_MAX - kItemPoolPillIdentifiedOffset ||
        !isaac::runtime::engine_memory::ReadAt(address + kItemPoolPillIdentifiedOffset + masked,
                                               &identified, &IsEngineMemoryReadable)) {
        return PushNativeFallbackBoolean(state, kFbItemPoolIsPillIdentified, false);
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
//:
//: ★ 批次 290（2026-10-02）：常量**搬去 `runtime_constants.hpp`**（同名、同值），因为它现在
//: 同时是对外 API `Room:GetRoomShape()` 的字段偏移，而 `test_field_api_rows.py` 只认那个头文件
//: 里的具名常量。住在那里之后**语义与证据一条没变**，只是不再有两处定义。
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
    (void)descriptor;  // 批次 232：生产构建里这段被编译掉 ⇒ 参数必然用不上
#if EXL_DIAGNOSTIC_PROBES  // 批次 232 探针总开关（口径见 probe_gate.hpp）
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
#endif  // EXL_DIAGNOSTIC_PROBES
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
// ★★★ 批次 347（2026-10-04）：**换成真容器**。上面那三条"还没取证"的路本批全部取到了
// （逐条见 `runtime_constants.hpp` 的批次 347 段），于是：
//   `Size` = `Data + 0x58` 的 **u16** 计数；`Get(i)` 交回一个能调 `PickEntry` 的 `RoomConfigSpawn`。
// ★★★ **`Spawns` 不是 `std::vector`**：是「数组首地址（`Data + 0x50`）+ `u16` 计数（`Data + 0x58`）」
//   ⇒ **没有 `end`/`cap`**（J 组写"查不到"，P 组更正为"根本不存在"，因为不是 vector）。
//   写点 = `RoomConfig::parse_room_node @ 0x48F914/0x48F918`；读点四处（`Room::Init` ×2 /
//   `RespawnEnemies` / `SpawnGreedModeWave`）都是 `ldrh w8,[xN,#0x58]` + `ldr x8,[xN,#0x50]` 这一对。
//
// ★ 表的取得方式（沿用旧版）：`Get` 是**带一个上值的闭包**（上值 = `data` 的 lightuserdata），
//   每次调用**现读**首地址与计数 —— 不缓存（房间会在回调之间变）、也不放进注册表共享表
//   （共享表会把 `data` 串到一起）。`data == 0` ⇒ `Size = 0`、`Get` 恒 `nil`（与旧空容器同行为）。
std::uintptr_t RoomConfigSpawnArrayBegin(std::uintptr_t data) noexcept {
    std::uintptr_t begin = 0;
    if (data == 0 || !isaac::runtime::engine_memory::ReadAt(
                         data + kRoomConfigRoomSpawnsBeginOffset, &begin, &IsEngineMemoryReadable)) {
        return 0;
    }
    return begin;
}

std::uint32_t RoomConfigSpawnArrayCount(std::uintptr_t data) noexcept {
    std::uint16_t count = 0;
    if (data == 0 || !isaac::runtime::engine_memory::ReadAt(
                         data + kRoomConfigRoomSpawnCountOffset, &count, &IsEngineMemoryReadable)) {
        return 0;   // 读不到 ⇒ 当作空表（PC 上没有这一步，但"读不到就不编条目"是本项目口径）
    }
    return count;
}

void PushRoomConfigSpawnHandle(lua_State* state, std::uintptr_t spawn) {
    if (spawn == 0) {
        lua_pushnil(state);
        return;
    }
    auto* handle = static_cast<LuaRuntime::RoomConfigSpawnHandle*>(
        lua_newuserdata(state, sizeof(LuaRuntime::RoomConfigSpawnHandle)));
    handle->spawn = isaac::runtime::engine_memory::AsObject(spawn);
    luaL_getmetatable(state, LuaRuntime::kRoomConfigSpawnMetatable);
    lua_setmetatable(state, -2);
}

void PushRoomConfigEntryHandle(lua_State* state, std::uintptr_t entry) {
    if (entry == 0) {
        lua_pushnil(state);
        return;
    }
    auto* handle = static_cast<LuaRuntime::RoomConfigEntryHandle*>(
        lua_newuserdata(state, sizeof(LuaRuntime::RoomConfigEntryHandle)));
    handle->entry = isaac::runtime::engine_memory::AsObject(entry);
    luaL_getmetatable(state, LuaRuntime::kRoomConfigEntryMetatable);
    lua_setmetatable(state, -2);
}

[[maybe_unused]] int SpawnListGet(lua_State* state) {
    if (lua_gettop(state) != 2 || !isaac::runtime::IsIntegerArgument(state, 2)) {
        return luaL_error(state, "RoomConfigSpawns:Get expects an index");
    }
    const std::uintptr_t data =
        engine_memory::AddressOf(lua_touserdata(state, lua_upvalueindex(1)));
    const lua_Integer requested = lua_tointegerx(state, 2, nullptr);
    const std::uintptr_t begin = RoomConfigSpawnArrayBegin(data);
    const std::uint32_t count = RoomConfigSpawnArrayCount(data);
    //: PC 的 `RoomConfigSpawns` 是 ArrayProxy：越界 / 取不到 ⇒ `nil`（**不报错**）。
    if (begin == 0 || requested < 0 || static_cast<std::uint64_t>(requested) >= count) {
        lua_pushnil(state);
        return 1;
    }
    PushRoomConfigSpawnHandle(
        state, begin + static_cast<std::size_t>(requested) * kRoomConfigSpawnStride);
    return 1;
}

void PushSpawnList(lua_State* state, std::uintptr_t data) {
    PushApi600SpawnList(state,data);
}

// --- 批次 347：`RoomConfig::Spawn` 与 `RoomConfig::Entry` 两个视图 ----------------------------
//
// 与 `GridEntityDoor` / `RoomDescriptor` 同一形态：`__index` 是函数 —— 先答**属性**，
// 再查本元表的 `__methods`（只有 `RoomConfigSpawn` 有方法：`PickEntry`）。
//: `RoomConfigSpawn:PickEntry(float r)` 的手写处理器 —— 批次 347（见 `runtime_constants.hpp`
//: 的 `kRoomConfigSpawnPickEntryOffset` 段：真身 `0x494910`、入口字 `0xA9BE7BFD`）。
//: ★ 为什么手写而不是引擎方法数据行：数据行要同时新开 `EngineReturnKind` + `EngineCallShape` +
//:   `FieldReceipt` 三处枚举，而 `RoomConfigSpawn` **只有这一个方法** ⇒ 手写少动三处账。
#if !defined(__SWITCH__)
//: 宿主注入点（见 `remaining_api.hpp` 的说明）：只在宿主构建里存在，设备上不参与编译。
RoomConfigSpawnPickEntryHostImplementation g_RoomConfigSpawnPickEntryHostImplementation = nullptr;
#endif

std::uintptr_t RoomConfigSpawnPickEntryMethod() noexcept {
    const std::uintptr_t base = EngineModuleBase();
    if (base == 0 || base > UINTPTR_MAX - kRoomConfigSpawnPickEntryOffset) {
        return 0;
    }
    const std::uintptr_t method = base + kRoomConfigSpawnPickEntryOffset;
    return IsEngineMemoryReadable(method, sizeof(std::uint32_t)) ? method : 0;
}

int RoomConfigSpawnPickEntry(lua_State* state) {
    CheckApi600RoomConfigView(state,1);
    //: 冒号调用 ⇒ 栈上恰好 2 个（`self` + `r`）。少给/多给都报错（PC 的胶水层同样严格）。
    if (lua_gettop(state) != 2) {
        return luaL_error(state, "RoomConfigSpawn:PickEntry expects a number");
    }
    auto* handle = static_cast<LuaRuntime::RoomConfigSpawnHandle*>(
        luaL_checkudata(state, 1, LuaRuntime::kRoomConfigSpawnMetatable));
    if (handle == nullptr) {
        return luaL_error(state, "RoomConfigSpawn:PickEntry expects a RoomConfigSpawn");
    }
    //: `r` 必须是数字。★ **不夹取、不报域外错** —— 契约写 `r ∈ [0,1]`，但 `r` 只参与
    //: `r * SumWeights` 的比较，PC 直接透传 ⇒ 我们也透传（自作聪明加夹取就与 PC 不一致）。
    if (!lua_isnumber(state, 2)) {
        return luaL_error(state, "RoomConfigSpawn:PickEntry expects a number");
    }
    const float r = static_cast<float>(lua_tonumber(state, 2));
    const std::uintptr_t spawn = isaac::runtime::engine_memory::AddressOf(handle->spawn);
#if !defined(__SWITCH__)
    //: ★ 宿主注入优先（必须在入口字核对**之前**：宿主里那个模块块是零、核对必然不通过）。
    if (g_RoomConfigSpawnPickEntryHostImplementation != nullptr) {
        const void* injected = g_RoomConfigSpawnPickEntryHostImplementation(spawn, r);
        if (injected == nullptr) {
            lua_pushnil(state);
            return 1;
        }
        PushRoomConfigEntryHandle(state, isaac::runtime::engine_memory::AddressOf(injected));
        InheritApi600RoomConfigViewOwner(state,1,-1);
        return 1;
    }
#endif
    const std::uintptr_t method = spawn != 0 ? RoomConfigSpawnPickEntryMethod() : 0;
    //: 入口首 4 字节核对（与全族同口径）：接收者失效 / 指纹不符 ⇒ **不调引擎、不报错**，压 `nil`
    //: （PC 拿不到对象时同样给不可用引用）。
    if (spawn == 0 || method == 0 ||
        !EngineEntryWordMatches(method, kRoomConfigSpawnPickEntryEntryWord)) {
        lua_pushnil(state);
        return 1;
    }
    //: ★ 形参类型写 `float` ⇒ AAPCS64 下进 `s0`；**不经数据行跳板**，所以不踩批次 338 的
    //:   f32 位型那类坑（`AsFunction` 由编译器按签名装寄存器）。
    using PickEntryFn = const void* (*)(std::uintptr_t, float);
    const void* entry = isaac::runtime::engine_call::AsFunction<PickEntryFn>(method)(spawn, r);
    //: ★★ 引擎的"未命中兜底"**不是 `nullptr`**（它会打日志后返回 `Entries.begin`）
    //:   ⇒ 只在引擎真返回 0 时压 `nil`，**不要**"看到没命中就给 nil"。
    if (entry == nullptr) {
        lua_pushnil(state);
        return 1;
    }
    PushRoomConfigEntryHandle(state, isaac::runtime::engine_memory::AddressOf(entry));
    InheritApi600RoomConfigViewOwner(state,1,-1);
    return 1;
}

constexpr LuaHandlerBinding kRoomConfigSpawnHandlers[] = {
    // ---- 批次 347（2026-10-04）：`RoomConfigSpawn:PickEntry(float r)`（2 处 / 2 个模组）----
    // PC 契约 `tools/pc_contract_docs/RoomConfig_Spawn.md:28`（逐字 `const RoomConfigEntry
    // PickEntry(float r)`）。真身 `_ZNK15IsaacRepentance10RoomConfig5Spawn9PickEntryEf @ 0x494910`
    // （入口字 `0xA9BE7BFD`）。id 取 **Room 域下一个空号 `0x0038`** ⇒ `0x04010038`。
    {0x04010038, &RoomConfigSpawnPickEntry},
};

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
        // ★ 批次 250：**给空句柄**（既不报错、也不给 nil）—— 与批次 043 在 `PushRoomDescriptor`
        // 里立的规矩是同一条："永远给对象"。043 只覆盖了"描述符地址为 0"，**没覆盖"连 Level
        // 都解析不到"**，而模组**加载期**走的正是后者（GoodTrip 的 `scripts/floor.lua:16`），
        // 所以那次修复没救到它。空句柄的字段由 `RoomDescriptorIndex()` 给空值（-1/0/false）。
        RecordNativeStateFallback(kFbLevelGetCurrentRoomDesc);
        return PushRoomDescriptor(state, 0);
    }
    const std::uintptr_t index = CurrentRoomIndex(level);
    if (index == kUnallocatedGridIndex) {
        RecordNativeStateFallback(kFbLevelGetCurrentRoomDesc);
        return PushRoomDescriptor(state, 0);
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
        // 批次 250：给**空句柄**（既不报错、也不给 nil）—— 与 `GetCurrentRoomDesc` 同一条口径。
        RecordNativeStateFallback(kFbLevelGetRoomByIdx);
        return PushRoomDescriptor(state, 0);
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
        // 批次 250：记一笔探针，然后照常给**空列表对象**（`level` 为 0 ⇒ 长度 0、
        // `Get(i)` 给空描述符）—— 不报错、也不给 nil，同一条"永远给对象"的原则。
        RecordNativeStateFallback(kFbLevelGetRooms);
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


// --- 批次 249（2026-10-01）：`Room` 三个**返回 Vector** 的方法 -------------------------------
//
// `Room:GetCenterPos()` / `Room:GetGridPosition(int)` / `Room:GetRandomPosition(float)`。
// 它们在工作清单里是 `needs_struct_return`（"跳板只支持标量返回 ⇒ 必须手写"）。
// ★★ 清单里那条"16 字节值类型、走 x8 间接结果寄存器"**对这三条是错的**：反汇编
//   `Room::GetGridPosition(int) @ 0x454D38` 看到的是 `ldp s0, s1, [sp, #0x8]` + `ret`
//   ⇒ `Vector2` 是 **8 字节**、走 **`s0`/`s1`**（取证见 `runtime_constants.hpp` 的对应段）。
//   所以**声明一个"两个 float 的结构体"按值返回就能对上一**，不必扩跳板 ——
//   与同文件 `CallRoomDoorSlotPosition`（`Room::GetDoorSlotPosition` 也是这么返回的）同一条路。
//
// ★★★ 批次 259 修正（2026-10-01，**真实缺陷**）：这三条当时的参数个数检查**少算了 `self`**
//   （写成 `lua_gettop(state) != 0/1`），而 `AttachOwnerMethods` 挂的是**普通 `lua_CFunction`**
//   ⇒ 模组写 `room:GetCenterPos()` 等价于 `room.GetCenterPos(room)`，栈上 `[1]` 就是房间句柄
//   ⇒ 三条**每一句都必然抛错**："Room:GetCenterPos accepts no arguments" 之类。
//   后果按项目口径是**最重的那一档**：一条 Lua 错误会把整条模组回调摘掉（GoodTrip 的教训）。
//   宿主实测（`runtime/tests/test_lua_room_position_fallback.py` 的 `convention` 场景）：
//   `Room:IsMirrorWorld()`（同文件里写对了的那条）`ok`，这三条一律 `ok=false`。
//   ⇒ 本批把三处改成 `!= 1` / `!= 2` / `!= 2`，并把"参数个数要含 `self`"钉进用例。
//
//: `KAGE::Math::Vector2` 的 C++ 侧形态（两个 float）。**只服务这一批的三条 Room 方法**。
struct RoomVector2 {
    float x;
    float y;
};

//: 三条共用的取址：模块基址 + 常量 + 可读性 + 入口首字比对。失败返回 0。
std::uintptr_t ResolveRoomVectorMethod(std::uintptr_t offset, std::uint32_t entryWord) noexcept {
    const std::uintptr_t base = EngineModuleBase();
    if (base == 0 || base > UINTPTR_MAX - offset) {
        return 0;
    }
    const std::uintptr_t method = base + offset;
    if (!IsEngineMemoryReadable(method, sizeof(std::uint32_t)) ||
        !EngineEntryWordMatches(method, entryWord)) {
        return 0;
    }
    return method;
}

//: 三条共同的失败降级：**压 `Vector(0, 0)`，不报错**。
//: 口径来源是 `EngineMethodHandler` 的头注（"拿不到接收者/方法/指纹不匹配时**不报错**，
//: 按 PC 语义降级：返回 void 就什么都不做、返回整数就压 0"）—— 返回值是 Vector 时，
//: 对应的降级就是把两格压 0。★ 为什么**不压 `nil`**：模组拿到 nil 后立刻会写 `pos.X`
//: （"attempt to index a nil value"）⇒ 又会把整条回调摘掉，那比"这一帧坐标是 0"严重得多。
void PushZeroRoomVector(lua_State* state) {
    isaac::runtime::PushLuaVector(state, 0.0F, 0.0F);
}

// `Room:GetCenterPos()` —— PC 契约 `tools/pc_contract_docs/Room.md:140`（`Vector GetCenterPos ( )`）。
// 消费方：语料 4 个模组（30 处），典型用法 `room:GetCenterPos() + Vector(...)`（算"房间中心偏移"）。
int RoomGetCenterPos(lua_State* state) {
    //: ★ 栈上是 `[1]=房间句柄(self)`（方法调用）⇒ 0 个实参时 `lua_gettop == 1`。
    if (lua_gettop(state) != 1) {
        return luaL_error(state, "Room:GetCenterPos accepts no arguments");
    }
    const std::uintptr_t method =
        ResolveRoomVectorMethod(kRoomGetCenterPosOffset, kRoomGetCenterPosEntryWord);
    void* room = nullptr;
    if (method == 0 ||
        ReadCurrentGameRoom(GameOwnerSlot(), &room) != GameRoomObservation::Success ||
        room == nullptr) {
        PushZeroRoomVector(state);
        return 1;
    }
    using RoomGetCenterPosFn = RoomVector2 (*)(const void*);
    const RoomVector2 value = isaac::runtime::engine_call::AsFunction<RoomGetCenterPosFn>(method)(room);
    isaac::runtime::PushLuaVector(state, value.x, value.y);
    return 1;
}

// `Room:GetGridPosition(int GridIndex)` —— PC 契约 `Room.md:405`。
// 语义（由 `0x454D38` 的反汇编直接给出）：按 `+0x14`（每行格数）拆成行列，再乘 40.0 加 40.0
// ⇒ **格子中心的世界坐标**。
int RoomGetGridPosition(lua_State* state) {
    //: ★ `[1]=self`、`[2]=GridIndex`（方法调用 ⇒ `lua_gettop` 含 `self`）。
    if (lua_gettop(state) != 2) {
        return luaL_error(state, "Room:GetGridPosition expects a grid index");
    }
    const lua_Integer index = luaL_checkinteger(state, 2);
    const std::uintptr_t method =
        ResolveRoomVectorMethod(kRoomGetGridPositionOffset, kRoomGetGridPositionEntryWord);
    void* room = nullptr;
    if (method == 0 ||
        ReadCurrentGameRoom(GameOwnerSlot(), &room) != GameRoomObservation::Success ||
        room == nullptr) {
        PushZeroRoomVector(state);
        return 1;
    }
    using RoomGetGridPositionFn = RoomVector2 (*)(const void*, int);
    const RoomVector2 value =
        isaac::runtime::engine_call::AsFunction<RoomGetGridPositionFn>(method)(room, static_cast<int>(index));
    isaac::runtime::PushLuaVector(state, value.x, value.y);
    return 1;
}

// `Room:GetRandomPosition(float Margin)` —— PC 契约 `Room.md:451`。
int RoomGetRandomPosition(lua_State* state) {
    //: ★ `[1]=self`、`[2]=Margin`（方法调用 ⇒ `lua_gettop` 含 `self`）。
    if (lua_gettop(state) != 2) {
        return luaL_error(state, "Room:GetRandomPosition expects a margin");
    }
    const float margin = static_cast<float>(luaL_checknumber(state, 2));
    const std::uintptr_t method =
        ResolveRoomVectorMethod(kRoomGetRandomPositionOffset, kRoomGetRandomPositionEntryWord);
    void* room = nullptr;
    if (method == 0 ||
        ReadCurrentGameRoom(GameOwnerSlot(), &room) != GameRoomObservation::Success ||
        room == nullptr) {
        PushZeroRoomVector(state);
        return 1;
    }
    using RoomGetRandomPositionFn = RoomVector2 (*)(const void*, float);
    const RoomVector2 value = isaac::runtime::engine_call::AsFunction<RoomGetRandomPositionFn>(method)(room, margin);
    isaac::runtime::PushLuaVector(state, value.x, value.y);
    return 1;
}


//: `Room::GetDoorSlotPosition(eDoorSlot)` 的取址 + 调用助手：返回门的**世界坐标**
//: （两个 float 走 `s0`/`s1`）。入口指纹（`d10083ff` = `sub sp, sp, #0x20`）不过就返回 false。
//: 命名与同文件的 `CallGridEntityGetPosition` 一致。
//: ★ 批次 259 把它**再暴露成 Lua 方法** `Room:GetDoorSlotPosition(slot)`（处理器与 PC 方法同名，
//:   所以助手从 `RoomGetDoorSlotPosition` 改名为 `CallRoomDoorSlotPosition`）；原来的调用点
//:   `GridEntityDoor.Position` 字段读取仍走这里，失败时**照旧给 nil**（字段口径与"方法返回零向量"不同）。
bool CallRoomDoorSlotPosition(std::int32_t slot, RoomDoorPosition* out) noexcept {
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

// --- 批次 259（2026-10-01）：`Room` 四条**位置类**方法（都返回 `Vector2`，都手写）--------------
//
// 工作清单把这四条归在 `needs_new_shape`（"参数里有向量/枚举 ⇒ 要先扩一种形状能力"）。
// 逐条核对 **mangled 签名**之后的结论与批次 253 相同：**不需要扩任何能力** ——
// 它们的 `Vector` 参数是 **`Vector2 const&`（引用 ⇒ 指针）**，不是按值的 HFA。
//
// 仍然手写的**唯一**原因是**返回 `Vector2`**：跳板只支持标量返回（`engine_call_trampoline.hpp`
// 的能力边界），而"两个 float 的结构体按 AAPCS64 走 `s0`/`s1`" —— 与批次 249 的三条、
// 以及与 `CallRoomDoorSlotPosition` 同一条路（偏移取证见 `runtime_constants.hpp` 的批次 259 段）。
//
// 契约（`tools/pc_contract_docs/Room.md`）：
//   * `:78`  `Vector FindFreePickupSpawnPosition ( Vector Pos, float InitialStep = 0,
//             boolean AvoidActiveEntities = false, boolean AllowPits = false )`
//            —— "starting from `Pos` … if no free position is found, the original position
//            (aligned to the grid) is returned"（**失败也返回坐标，不返回 nil**）；
//   * `:152` `Vector GetClampedPosition ( Vector Pos, float Margin )`；
//   * `:83`  `Vector FindFreeTilePosition ( Vector Pos, float DistanceThreshold )`；
//   * `:291` `Vector GetDoorSlotPosition ( DoorSlot Slot )`。
//
// ★ 失败口径（作业单第三节第 11 条）：拿不到房间 / 入口指纹不匹配 / 参数类型不对时，
//   **不抛 Lua 错误**、压 `Vector(0, 0)`（与批次 249 同一口径，理由见 `PushZeroRoomVector`）。
//   唯一**照旧抛错**的是"参数个数/类型不对"—— 那是模组写错了，与 PC 上一样会报错。

//: 从 Lua 栈取一个 `Vector` 参数（引擎收 `Vector2 const&` ⇒ 我们要交一个**指针**）。
//: 传别的类型（数字 / 表 / nil）一律返回 false：把一个别的指针当坐标地址交出去会让引擎
//: 读到垃圾**且不报错**（静默的错坐标），比"这次调用降级"严重得多。
bool ReadRoomVectorArgument(lua_State* state, int stackIndex, RoomDoorPosition* out) noexcept {
    if (out == nullptr) {
        return false;
    }
    auto* vector = TryVectorArgument(state,stackIndex);
    if (vector == nullptr) {
        return false;
    }
    out->x = vector->x;
    out->y = vector->y;
    return true;
}

// `Room:FindFreePickupSpawnPosition(Vector Pos, float InitialStep = 0,
//                                  boolean AvoidActiveEntities = false, boolean AllowPits = false)`
// —— PC 契约 `tools/pc_contract_docs/Room.md:78`。
// 语料实参有 1 个（`TBOI_Better-Voiding`）、3 个（`Trinity`）、4 个（`RepentancePlus`）三种，
// 所以**必须**收下省略的尾部参数（缺省值按契约原文：0 / false / false）。
//
// ★★ 方法调用 ⇒ 栈上是 `[1]=房间句柄(self)、[2..]=实参`：**`lua_gettop` 含 `self`**。
//   （`AttachOwnerMethods` 挂的是普通 `lua_CFunction`，`room:Find…(…)` 就是 `room.Find…(room, …)`。）
int RoomFindFreePickupSpawnPosition(lua_State* state) {
    constexpr int kProvidedArgumentBase = 1;  // 栈上的 `self` 占一个位置。
    const int arguments = lua_gettop(state) - kProvidedArgumentBase;
    if (arguments < 1 || arguments > 4) {
        return luaL_error(state,
                          "Room:FindFreePickupSpawnPosition expects 1 to 4 argument(s)");
    }
    constexpr int kPositionIndex = 2;
    constexpr int kInitialStepIndex = 3;
    constexpr int kAvoidActiveEntitiesIndex = 4;
    constexpr int kAllowPitsIndex = 5;
    RoomDoorPosition position{0.0F, 0.0F};
    if (!ReadRoomVectorArgument(state, kPositionIndex, &position)) {
        return luaL_error(state, "Room:FindFreePickupSpawnPosition expects a Vector position");
    }
    float initialStep = 0.0F;
    bool avoidActiveEntities = false;
    bool allowPits = false;
    if (arguments >= 2) {
        initialStep = static_cast<float>(luaL_checknumber(state, kInitialStepIndex));
    }
    if (arguments >= 3) {
        avoidActiveEntities = lua_toboolean(state, kAvoidActiveEntitiesIndex) != 0;
    }
    if (arguments >= 4) {
        allowPits = lua_toboolean(state, kAllowPitsIndex) != 0;
    }
    void* room = nullptr;
    const std::uintptr_t method = ResolveRoomVectorMethod(kRoomFindFreePickupSpawnPositionOffset, kRoomFindFreePickupSpawnPositionEntryWord);
    if (method == 0 ||
        ReadCurrentGameRoom(GameOwnerSlot(), &room) != GameRoomObservation::Success ||
        room == nullptr) {
        PushZeroRoomVector(state);
        return 1;
    }
    // 引擎签名（mangled `…Efbb`）：`x1` = `Vector2*`、`s0` = InitialStep、`w2`/`w3` = 两个 bool。
    using RoomFindFreePickupSpawnPositionFn =
        RoomDoorPosition (*)(const void*, const RoomDoorPosition*, float, bool, bool);
    const RoomDoorPosition value =
        isaac::runtime::engine_call::AsFunction<RoomFindFreePickupSpawnPositionFn>(method)(
            room, &position, initialStep, avoidActiveEntities, allowPits);
    isaac::runtime::PushLuaVector(state, value.x, value.y);
    return 1;
}

// `Room:GetClampedPosition(Vector Pos, float Margin)` —— PC 契约 `tools/pc_contract_docs/Room.md:152`。
// ★ 引擎符号有 **5** 个参数（`…Vector2Effff`）：多出来的三个 float 是文档没写的缺省值。
//   **PC 的绑定层把 `Margin` 复制给全部四个 float**（`isaac-ng.exe` 里 `GetClampedPosition`
//   的绑定函数 `VA 0x427710` 就是 `movss xmm3,[ebp+0x10]` + 三次 `movss [esp+…]`）⇒ 我们照做。
int RoomGetClampedPosition(lua_State* state) {
    //: ★ `[1]=self`、`[2]=Pos`、`[3]=Margin`（方法调用 ⇒ `lua_gettop` 含 `self`）。
    if (lua_gettop(state) != 3) {
        return luaL_error(state, "Room:GetClampedPosition expects a Vector and a margin");
    }
    RoomDoorPosition position{0.0F, 0.0F};
    if (!ReadRoomVectorArgument(state, 2, &position)) {
        return luaL_error(state, "Room:GetClampedPosition expects a Vector position");
    }
    const float margin = static_cast<float>(luaL_checknumber(state, 3));
    void* room = nullptr;
    const std::uintptr_t method = ResolveRoomVectorMethod(kRoomGetClampedPositionOffset, kRoomGetClampedPositionEntryWord);
    if (method == 0 ||
        ReadCurrentGameRoom(GameOwnerSlot(), &room) != GameRoomObservation::Success ||
        room == nullptr) {
        PushZeroRoomVector(state);
        return 1;
    }
    using RoomGetClampedPositionFn =
        RoomDoorPosition (*)(const void*, const RoomDoorPosition*, float, float, float, float);
    const RoomDoorPosition value =
        isaac::runtime::engine_call::AsFunction<RoomGetClampedPositionFn>(method)(
            room, &position, margin, margin, margin, margin);
    isaac::runtime::PushLuaVector(state, value.x, value.y);
    return 1;
}

// `Room:FindFreeTilePosition(Vector Pos, float DistanceThreshold)` —— PC 契约 `Room.md:83`。
// 语料两处都传满 2 个参数（`DistanceThreshold` 无缺省值）。
int RoomFindFreeTilePosition(lua_State* state) {
    //: ★ `[1]=self`、`[2]=Pos`、`[3]=DistanceThreshold`。
    if (lua_gettop(state) != 3) {
        return luaL_error(state, "Room:FindFreeTilePosition expects a Vector and a threshold");
    }
    RoomDoorPosition position{0.0F, 0.0F};
    if (!ReadRoomVectorArgument(state, 2, &position)) {
        return luaL_error(state, "Room:FindFreeTilePosition expects a Vector position");
    }
    const float threshold = static_cast<float>(luaL_checknumber(state, 3));
    void* room = nullptr;
    const std::uintptr_t method = ResolveRoomVectorMethod(kRoomFindFreeTilePositionOffset, kRoomFindFreeTilePositionEntryWord);
    if (method == 0 ||
        ReadCurrentGameRoom(GameOwnerSlot(), &room) != GameRoomObservation::Success ||
        room == nullptr) {
        PushZeroRoomVector(state);
        return 1;
    }
    using RoomFindFreeTilePositionFn =
        RoomDoorPosition (*)(const void*, const RoomDoorPosition*, float);
    const RoomDoorPosition value =
        isaac::runtime::engine_call::AsFunction<RoomFindFreeTilePositionFn>(method)(room, &position,
                                                                                   threshold);
    isaac::runtime::PushLuaVector(state, value.x, value.y);
    return 1;
}

// `Room:GetDoorSlotPosition(DoorSlot Slot)` —— PC 契约 `Room.md:291`。
// ★ 取址与调用复用批次 249 就在用的助手；**失败也压 `Vector(0,0)`**（不压 nil）：
//   引擎自己在槽位越界时返回的正是 `Vector2::Zero`（`0x464B9C` 那道 `cmp w8,#9` 分支），
//   所以零向量既是降级也是 PC 语义。语料用法（`ChallengeAPI` / `BOIStageAPI15`）：
//   `room:GetDoorSlotPosition(slot)` → 坐标，或再喂给 `room:GetGridIndex(pos)`。
int RoomGetDoorSlotPosition(lua_State* state) {
    //: ★ `[1]=self`、`[2]=Slot`（方法调用 ⇒ `lua_gettop` 含 `self`）。
    if (lua_gettop(state) != 2) {
        return luaL_error(state, "Room:GetDoorSlotPosition expects a door slot");
    }
    if (!isaac::runtime::IsIntegerArgument(state, 2)) {
        return luaL_error(state, "Room:GetDoorSlotPosition expects an integer door slot");
    }
    const auto slot = static_cast<std::int32_t>(lua_tointegerx(state, 2, nullptr));
    RoomDoorPosition position{0.0F, 0.0F};
    if (!CallRoomDoorSlotPosition(slot, &position)) {
        PushZeroRoomVector(state);
        return 1;
    }
    isaac::runtime::PushLuaVector(state, position.x, position.y);
    return 1;
}


} // namespace

// 批次 436：让"当前房间解析"的**派发窗口内缓存**立即失效。
// ★ 定义必须在**匿名 namespace 之外**（本文件 116 行那个匿名 ns 在上一行才关闭；
// 2312~2888 是个嵌套匿名块，别被它误导）：这个函数是**跨 TU 入口**（`isaac_api.cpp` 的
// `EngineMethodHandler`（换房 id 特判）与 `Isaac.ExecuteCommand` 都会调它）——
// 放进匿名 ns 会得到内部链接（链接器找不到 + `-Werror=unused-function`）。
void InvalidateCurrentRoomCache() noexcept {
    g_CurrentRoomCache.epoch = 0;
}

// --- 批次 262（2026-10-01）：`Isaac` 全局表上两条**由 Room 原语拼出来**的接口 ----------------
//
// 工作清单把它们归在 `glue_compose`（"PC 在 Lua 胶水层实现 ⇒ 用现成原语自己拼"）。
// 这一次**不是靠读文档猜的** —— 直接把 PC 的绑定函数反汇编出来看它到底调了什么
// （配方 `tools/pc_exe_binding.py`：按名字找名字表项 → 名字前面那条 `push` 就是绑定函数 VA）：
//
//   * `Isaac.GetFreeNearPosition` 的绑定函数 `VA 0x80BB30` 的最后一句是 `call 0x7CF240`，
//     而 `0x7CF240` 正是 **`Room::FindFreePickupSpawnPosition` 的那条绑定函数**
//     （用"名字表项 = `push <函数VA>; push <名字VA>` 成对"这条关系反查出来的）
//     ⇒ **PC 的实现就是 `room:FindFreePickupSpawnPosition(pos, step, false, false)`**。
//     那条我们**批次 259 刚做过**。
//   * `Isaac.GridSpawn` 的绑定函数 `VA 0x80B900`，逐段读下来是：
//     ① 把世界坐标算成**格下标**：`gx = (int)((x − 40)/40 + 0.5)`、`gy = (int)((y − 120)/40 + 0.5)`
//        （常量从 `0xB6AA3C`(40.0) / `0xB6A480`(0.5) / `0xB6AB20`(120.0) 三处立即数读出，
//        与 `Room::GetGridIndex(Vector)` 是**同一个公式**）；
//     ② 负号或 `>= 网格宽/高` ⇒ **返回 0（Lua 的 nil）**；
//     ③ 那一格已有网格实体、且它的 **Type ∉ {1, 10}**（`GRID_DECORATION` / `GRID_SPIDERWEB`）、
//        且 `forced == false` ⇒ **返回 0（不覆盖）**；Type 正好是 1 或 10 时**照样往下走**
//        （这两类是可替换的装饰物/蛛网）；
//     ④ 取 `seed = RandomU32()`（`call 0x6C3D90`，PC 侧的全局随机）后调
//        `Room::SpawnGridEntity(格下标, Type, Variant, seed, VarData = 0)`（`call 0x7AA9B0`
//        —— 反查出来正是 `Room::SpawnGridEntity` 的绑定函数）；
//     ⑤ **最后再读一次那一格的实体指针当返回值**（`mov eax, [room + 4*index + 0x24]`，
//        下标 > 0x1BF 时返回 0）⇒ 返回的是"生成出来的那个网格实体"，不是 `SpawnGridEntity` 的返回值。
//
// ⇒ 两条都用**我们已经有**的原语拼得出来（格坐标换算与网格实体表读取在
//   `Room:GetGridIndex` / `Room:GetGridEntity` 里各有一份；`Room::SpawnGridEntity` 是批次 252
//   的数据行入口），**不需要新的引擎符号**。唯一新登记的是一个随机源：引擎自己的 `RandomU32()`
//   （`kRandomU32Offset`）—— 引擎创建网格实体时用的就是它，比我们自己造一个随机数更贴 PC。
//
// ★ 调用形态：`Isaac` 是**全局表**，模组按 `.` 调（`Isaac.GridSpawn(…)`）⇒ 栈上**不含 `self`**，
//   实参从 `[1]` 开始（与 `Room`/`Game` 的方法调用相反，见批次 259 的事故记录）。

//: `Isaac.GridSpawn` 里那两个"可以直接覆盖"的网格实体类型（PC 绑定函数里的两句 `cmp`，
//: 数值取自 `analysis/isaacdocs-snapshot/docs/enums/GridEntityType.md`）。
constexpr std::uint32_t kGridEntityDecorationType = 1;  // GRID_DECORATION
constexpr std::uint32_t kGridEntitySpiderWebType = 10;  // GRID_SPIDERWEB

//: 引擎自己的 `RandomU32()`（无参、返回 `unsigned`）。取不到（模块基址没有 / 入口首字不匹配）
//: 时返回 0：种子给 0 只是"这颗种子不随机"，不会让生成失败，比因此不生成好。
//: ★ 批次 340（2026-10-04）：**从匿名命名空间里提出来**（声明进 `remaining_api.hpp`）——
//: `Isaac:Spawn` 需要"非 0 随机种子"（契约 `Isaac.md:621` 明文警告种子 0 会让游戏崩），
//: 而那条处理器住在 `isaac_api.cpp`（另一个 TU）⇒ 跨 TU 可见。**只此一份实现。**
#if !defined(__SWITCH__)
static std::uint32_t (*g_RandomU32HostImplementation)() = nullptr;
void SetRandomU32HostImplementation(std::uint32_t (*function)()) noexcept {
    g_RandomU32HostImplementation = function;
}
#endif

bool TryEngineRandomU32(std::uint32_t* value) noexcept {
    if (value == nullptr) return false;
    const std::uintptr_t base = EngineModuleBase();
    if (base == 0 || base > UINTPTR_MAX - kRandomU32Offset) {
        return false;
    }
    const std::uintptr_t address = base + kRandomU32Offset;
    if (!IsEngineMemoryReadable(address, sizeof(std::uint32_t)) ||
        !EngineEntryWordMatches(address, kRandomU32EntryWord)) {
        return false;
    }
#if !defined(__SWITCH__)
    if (g_RandomU32HostImplementation == nullptr) return false;
    *value = g_RandomU32HostImplementation();
#else
    using EngineRandomU32Fn = std::uint32_t (*)();
    *value = isaac::runtime::engine_call::AsFunction<EngineRandomU32Fn>(address)();
#endif
    return true;
}

std::uint32_t EngineRandomU32() noexcept {
    std::uint32_t value = 0;
    static_cast<void>(TryEngineRandomU32(&value));
    return value;
}

// `Isaac.GetFreeNearPosition(Vector pos, float step)` —— PC 契约 `tools/pc_contract_docs/Isaac.md:263`
// （`#### [Vector](Vector.md) GetFreeNearPosition ( [Vector](Vector.md) pos, float step )`；
// **正文是空的** —— 所以语义只能从实现取，而实现已经在上面反汇编出来了）。
//
// 语料用法（`RepentancePlus` / `CyclingItemsAPI` 各 3 处）都是
// `Isaac.Spawn(5, 100, id, Isaac.GetFreeNearPosition(Player.Position, 40), Vector.Zero, nil)`
// ⇒ 拿一个"离玩家最近的空位"去生成掉落物。
//
// 失败降级：拿不到房间 / 入口首字不匹配 ⇒ 压 `Vector(0, 0)`（与批次 249/259 的 Room 位置类方法
// 同一口径；**不压 nil**，压 nil 会让模组立刻 `pos.X` 抛错、摘掉整条回调）。
int IsaacGetFreeNearPosition(lua_State* state) {
    if (lua_gettop(state) != 2) {
        return luaL_error(state, "Isaac.GetFreeNearPosition expects a Vector and a step");
    }
    RoomDoorPosition position{0.0F, 0.0F};
    if (!ReadRoomVectorArgument(state, 1, &position)) {
        return luaL_error(state, "Isaac.GetFreeNearPosition expects a Vector position");
    }
    const float step = static_cast<float>(luaL_checknumber(state, 2));
    const std::uintptr_t method = ResolveRoomVectorMethod(
        kRoomFindFreePickupSpawnPositionOffset, kRoomFindFreePickupSpawnPositionEntryWord);
    void* room = nullptr;
    if (method == 0 ||
        ReadCurrentGameRoom(GameOwnerSlot(), &room) != GameRoomObservation::Success ||
        room == nullptr) {
        PushZeroRoomVector(state);
        return 1;
    }
    using IsaacGetFreeNearPositionFn =
        RoomDoorPosition (*)(const void*, const RoomDoorPosition*, float, bool, bool);
    const RoomDoorPosition value =
        isaac::runtime::engine_call::AsFunction<IsaacGetFreeNearPositionFn>(method)(
            room, &position, step, false, false);
    isaac::runtime::PushLuaVector(state, value.x, value.y);
    return 1;
}

// `Isaac.GridSpawn(GridEntityType, int variant, Vector position, boolean forced)`
// —— PC 契约 `tools/pc_contract_docs/Isaac.md:472`。正文（含那段 `forced` 的 bug 说明）：
// 「Spawn a [GridEntity](GridEntity.md) at the given position (world coordinates).」/
// 「The "forced" argument can override the grid entity at the given location **in certain cases**.
//  For example: it won't work with a rock, but will work with a rock that's been blown up.」
// ⇒ 与反汇编读到的**三段**逻辑逐条对上：越界不生成、"未被强制且已有东西"不覆盖、
//   其余交给 `Room::SpawnGridEntity` 自己决定（"rock 不行、炸掉的 rock 行"就是引擎那层的行为）。
//
// 语料用法（4 个模组 / 17 处）：`GridSpawn(GRID_PIT, 0, pos, true)`、
// `GridSpawn(GRID_STATUE, 1, AngelPos, false)`、`GridSpawn(GRID_STAIRS, 3, room:GetCenterPos(), true)`
// —— 都用 `room:GetGridPosition(index)` 或实体位置当坐标，所以**必须**走坐标换算这条路。
//
// 失败/不生成时压 `nil`（PC 返回 0 就是 nil）—— 这里与"位置类方法压零向量"不同：
// PC 这两条的返回值天然允许"什么都没生成"，模组也都在 `if grid then` 里判。
int IsaacGridSpawn(lua_State* state) {
    if (lua_gettop(state) != 4) {
        return luaL_error(state,
                          "Isaac.GridSpawn expects a type, a variant, a Vector and a boolean");
    }
    if (!isaac::runtime::IsIntegerArgument(state, 1) || !isaac::runtime::IsIntegerArgument(state, 2)) {
        return luaL_error(state, "Isaac.GridSpawn expects integer type and variant");
    }
    const auto type = static_cast<std::int32_t>(lua_tointegerx(state, 1, nullptr));
    const auto variant = static_cast<std::int32_t>(lua_tointegerx(state, 2, nullptr));
    RoomDoorPosition position{0.0F, 0.0F};
    if (!ReadRoomVectorArgument(state, 3, &position)) {
        return luaL_error(state, "Isaac.GridSpawn expects a Vector position");
    }
    const bool forced = lua_toboolean(state, 4) != 0;

    void* room = nullptr;
    std::uint32_t width = 0;
    std::uint32_t height = 0;
    if (ReadCurrentGameRoom(GameOwnerSlot(), &room) != GameRoomObservation::Success ||
        room == nullptr) {
        lua_pushnil(state);
        return 1;
    }
    const std::uintptr_t roomAddress = isaac::runtime::engine_memory::AddressOf(room);
    if (!ReadRoomGridDimensions(roomAddress, &width, &height)) {
        lua_pushnil(state);
        return 1;
    }
    // ① 世界坐标 → 格下标（与 `Room:GetGridIndex(Vector)` 同一公式、同一对偏移常量）。
    const std::int32_t gridX = RoomGridCoordinateFromWorld(position.x, kRoomGridWorldOffsetX);
    const std::int32_t gridY = RoomGridCoordinateFromWorld(position.y, kRoomGridWorldOffsetY);
    if (gridX < 0 || gridY < 0 || static_cast<std::uint32_t>(gridX) >= width ||
        static_cast<std::uint32_t>(gridY) >= height) {
        lua_pushnil(state);
        return 1;
    }
    const auto gridIndex =
        static_cast<std::uint32_t>(width * static_cast<std::uint32_t>(gridY) +
                                   static_cast<std::uint32_t>(gridX));
    const std::uintptr_t slot = roomAddress + kRoomGridEntityTableOffset +
                                static_cast<std::uintptr_t>(gridIndex) * sizeof(std::uintptr_t);
    // ② 覆盖判定：那一格已有实体、Type ∉ {1, 10}、且没有 forced ⇒ 什么都不做、返回 nil。
    std::uintptr_t existing = 0;
    if (isaac::runtime::engine_memory::ReadAt(slot, &existing, &IsEngineMemoryReadable) &&
        existing != 0) {
        std::uint32_t existingType = 0;
        if (isaac::runtime::engine_memory::ReadAt(existing + kGridEntityTypeOffset, &existingType,
                                                 &IsEngineMemoryReadable) &&
            existingType != kGridEntityDecorationType &&
            existingType != kGridEntitySpiderWebType && !forced) {
            lua_pushnil(state);
            return 1;
        }
    }
    // ③ 生成。入口与形状见批次 252 的 `kRoomSpawnGridEntityOffset` 段
    //    （符号 `…SpawnGridEntityEiNS_15eGridEntityTypeEjji` 返回值特征为 `void`）。
    const std::uintptr_t method = ResolveRoomVectorMethod(kRoomSpawnGridEntityOffset,
                                                          kRoomSpawnGridEntityEntryWord);
    if (method == 0) {
        lua_pushnil(state);
        return 1;
    }
    using IsaacGridSpawnFn = void (*)(void*, int, int, unsigned, unsigned, int);
    isaac::runtime::engine_call::AsFunction<IsaacGridSpawnFn>(method)(
        room, static_cast<int>(gridIndex), type, static_cast<unsigned>(variant), EngineRandomU32(),
        0);
    // ④ 返回值 = **那一格现在的实体**（不是上面那次调用的返回值）。
    std::uintptr_t spawned = 0;
    if (!isaac::runtime::engine_memory::ReadAt(slot, &spawned, &IsEngineMemoryReadable) ||
        spawned == 0) {
        lua_pushnil(state);
        return 1;
    }
    PushGridEntityHandle(state, spawned);
    return 1;
}


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
    // ---- 批次 294（2026-10-03）：`Level` 的两个**房间列表索引**（合 3 处）----
    // 两条都是"读一个 `i32`"（`FieldKind::I32`），接收者是既有的 `FieldReceipt::Level`
    // （`Game`/`Level` 同一地址），偏移与四/六个具名读者的证据见 `runtime_constants.hpp`
    // 的批次 294 段、以及布局表 `tools/layout_tables/game.json` 的 `PreviousRoomIndex` /
    // `LastBossRoomListIndex` 两行（`--verify` 会重新反汇编逐条核对）。
    // ★ 降级档都是 `MinusOne`：**0 是合法的房间索引** ⇒ 读不到时**不能**答 0
    //   （那等于说"上一个房间是 0 号"）；答 -1 与"没有"同义（与 `EntityPlayer:GetFireDirection`
    //   的 `-1` = `NO_DIRECTION` 同一口径）。真机项 V45 会核对 PC 自己的取值。
    // 契约：`Level.md` 的 193（`GetPreviousRoomIndex`）/ 167（`GetLastBossRoomListIndex`）行。
    {0x03010019, kLevelPreviousRoomIndexOffset, 0, FieldKind::I32, FieldMissing::MinusOne,
     FieldReceipt::Level, 0xFF},
    {0x0301001A, kLevelLastBossRoomListIndexOffset, 0, FieldKind::I32, FieldMissing::MinusOne,
     FieldReceipt::Level, 0xFF},
    // ---- 批次 297（2026-10-03）：`Level:GetStateFlag(int Flag)`（13 处 / 4 个模组）----
    // 读 `Level + 0x215F0` 的 **`u64`** 里的**第 Flag 位** —— 位号来自 Lua 实参 ⇒ 走新种类
    // `FieldKind::BoolBitArrayOfArg`（`offset2` = 元素宽度，这里是 8）。
    // ★ 基址与位号的取证（两个具名函数各给一个位点位）：`Level::SetRedHeartDamage() @ 0x3E7F00`
    //   对 `Level+0x215F0` 做 `orr x9,#0x4`（**bit 2** = `STATE_REDHEART_DAMAGED = 2`）、
    //   `Level::ApplyCompassEffect(bool) @ 0x3E7024` 对同一格做 `orr x8,#0x80`
    //   （**bit 7** = `STATE_COMPASS_EFFECT = 7`）—— 详见 `runtime_constants.hpp` 的批次 297 段。
    // ★ 降级档 `False`：读到的是"这一位没置"，与 PC 上"读到 0"同值；越界标志号也走这一档
    //   （PC 那两条绑定**没有**边界检查，我们不去读可能落在别的字段上的地址）。
    // 契约：`tools/pc_contract_docs/Level.md` 的 `GetStateFlag` 行。
    {0x0301001B, kLevelStateFlagsOffset, 8, FieldKind::BoolBitArrayOfArg, FieldMissing::False,
     FieldReceipt::Level, 0xFF},
    // ---- 批次 300（2026-10-03）：`Level:SetStateFlag(int Flag, boolean Value)`（1 处）----
    // **写侧**（`BoolBitArrayOfWriteArg`，宽度 8 ⇒ 每 64 位 64 个标志）。PC 侧对应绑定是
    // `0x4C0540`（对 `Level+0x1C3168` 那个 64 位字数组做读改写，且**先比 `0x31`**）——
    // 与 `GetStateFlag` 的 `0x41C430` 同一格。★ 我们的护栏与读侧一致（`8*宽度*64` 位）。
    // 契约：`tools/pc_contract_docs/Level.md` 的 `SetStateFlag` 行。
    {0x0301001C, kLevelStateFlagsOffset, 8, FieldKind::BoolBitArrayOfWriteArg,
     FieldMissing::False, FieldReceipt::Level, 0xFF},
    // ---- 批次 313（2026-10-03）：`Level` 头部两个**布尔标志字节**（合 4 处 / 2 个模组）----
    // 两条都是"读一个字节、非 0 即真"（`FieldKind::Bool`），偏移与三方证据见
    // `runtime_constants.hpp` 的批次 313 段：
    //   * PC 侧各自只有两条指令：`HasBossChallenge @ 0x7FA860: movb 0x8(%ecx),%al`、
    //     `GetCanSeeEverything @ 0x7FA870: movb 0x11(%ecx),%al`（同一张 Level 布尔表簇）。
    //   * ★★ Switch 的 `Level` 头部与 PC **逐格一致**：`+0x00`/`+0x04`（`Level::SetStage` 连着写
    //     两个枚举）与 `+0x0C`（`Level::IsNextStageAvailable` 读的就是 curses 掩码）三条锚点
    //     两平台同值 ⇒ 夹在 `+0x04` 与 `+0x0C` 之间的 `+0x08` 同格。
    //   * ★ `+0x08` 与 `+0x11` 都是 `Level::StoreGameState`/`RestoreGameState` 存读的那四个
    //     字节标志之一（同一个存档区块 `+0x1B8~+0x1BB`，四格各自独立）。
    //   * ★★★ `+0x11` 的语义有具名消费者：`Level::try_display_room` 先问
    //     `PlayerManager::FirstCollectibleOwner(0x4C = COLLECTIBLE_XRAY_VISION /*透视*/)`，
    //     没有透视才去读 `[x20,#0x11]`、为 0 就不显示 —— 「有透视 **或** 这一格非 0 ⇒ 地图全开」
    //     正是 `GetCanSeeEverything` 的语义。
    // 契约：`tools/pc_contract_docs/Level.md:271`（`HasBossChallenge`）/ `:104`（`GetCanSeeEverything`）。
    // ★ 降级档 `False`：读不到时答"没置位"，与 PC 上"读到 0"同值。
    {0x0301001D, kLevelBossChallengeOffset, 0, FieldKind::Bool, FieldMissing::False,
     FieldReceipt::Level, 0xFF},
    {0x0301001E, kLevelCanSeeEverythingOffset, 0, FieldKind::Bool, FieldMissing::False,
     FieldReceipt::Level, 0xFF},
};

//: 批次 051：`Level` 的**引擎方法数据行**（机制见 `engine_method_api.hpp`）。
constexpr EngineMethodRow kLevelEngineRows[] = {
    // 0x000F `Level:AddCurse(eLevelCurse, bool)`：`x0 = this`、`w1 = 诅咒号`、`w2 = 是否显示名称`
    // bool在原生ABI上是0/1，但Lua参数仍须先按布尔取值，不能用整数参数校验拒绝true/false。
    {0x0301000F, kLevelAddCurseOffset, kLevelAddCurseEntryWord, FieldReceipt::Level,
     EngineCallShape::VoidIntBool, 2, 0xFF},
    // 0x0010 `Level:RemoveCurses(uint)`：`x0 = this`、`w1 = 诅咒位掩码`。
    {0x03010010, kLevelRemoveCursesOffset, kLevelRemoveCursesEntryWord, FieldReceipt::Level,
     EngineCallShape::Void1, 1, 0xFF},
    // ---- 批次 238：`Level:Update`（void Update ( )）
    // 符号 `_ZN15IsaacRepentance5Level6UpdateEv`；形状按符号参数表取（见 `runtime_constants.hpp` 的批次 238 段）。
    {0x03010012, kLevelUpdateOffset, kLevelUpdateEntryWord, FieldReceipt::Level,
     EngineCallShape::Void0, 0, 0xFF},
    // ---- 批次 238：`Level:UpdateVisibility`（void UpdateVisibility ( )）
    // 符号 `_ZN15IsaacRepentance5Level16UpdateVisibilityEv`；形状按符号参数表取（见 `runtime_constants.hpp` 的批次 238 段）。
    {0x03010013, kLevelUpdateVisibilityOffset, kLevelUpdateVisibilityEntryWord, FieldReceipt::Level,
     EngineCallShape::Void0, 0, 0xFF},
    // ---- 批次 239：`Level:SetStage`（void SetStage ( int StageOffset, int StageTypeOffset )）
    // 引擎符号收两个枚举（`eLevelStage` / `eStageType`）⇒ ABI 上仍是两个整数寄存器、`Void2`。
    {0x03010014, kLevelSetStageOffset, kLevelSetStageEntryWord, FieldReceipt::Level,
     EngineCallShape::Void2, 2, 0xFF},
    // ---- 批次 239：`Level:SetNextStage`（void SetNextStage ( )）
    {0x03010015, kLevelSetNextStageOffset, kLevelSetNextStageEntryWord, FieldReceipt::Level,
     EngineCallShape::Void0, 0, 0xFF},
    // ---- 批次 239：`Level:GetPlanetariumChance`（float GetPlanetariumChance ( )）
    // 返回浮点走 `d0` ⇒ 形状 `Float0`（本批唯一需要"无参 + 浮点返回"的一条）。
    {0x03010016, kLevelGetPlanetariumChanceOffset, kLevelGetPlanetariumChanceEntryWord,
     FieldReceipt::Level, EngineCallShape::Float0, 0, 0xFF},
    // ---- 批次 239：`Level:GetRandomRoomIndex`（int GetRandomRoomIndex ( boolean IAmErrorRoom, int Seed )）
    // 第 1 个参数在语料里是 Lua 布尔 ⇒ 形状 `IntBoolInt` 里该位置是 `Bool`。
    {0x03010017, kLevelGetRandomRoomIndexOffset, kLevelGetRandomRoomIndexEntryWord,
     FieldReceipt::Level, EngineCallShape::IntBoolInt, 2, 0xFF},
};

std::size_t AttachLevelMethods(lua_State* state) noexcept {
    // 字段读取型行表也挂给 `Level` 族（批次 11 起）：绑定循环按 id 匹配，不会串族；
    // 行里的 `receipt` 决定用哪套接收者校验。
    return AttachApi700Methods(state,"Level") + AttachApi300Methods(state,"Level") + AttachApi200Methods(state,"Level") + AttachApi100Methods(state,"Level") + AttachOwnerMethods(state, "Level", kLevelHandlers, RowCount(kLevelHandlers),
                              kLevelFieldApis, RowCount(kLevelFieldApis), kLevelEngineRows,
                              RowCount(kLevelEngineRows));
}

// ★★ 批次 348（2026-10-04）：`Level` 元表的 `__index` —— **必须是函数，不能是元表自己那张表**。
//: 起因（真机读数原文 = `dist/gdb-report-20261004-181018.txt`）：
//:   `minimapi/scripts/minimapapi/apioverride.lua:25: attempt to call a table value (upvalue 'oldIndex')`
//:   那一行是 `return classDat.New[k] or oldIndex(self, k)`，`oldIndex` 取自
//:   `getmetatable(Level).__class.__index`（第 22 行）。批次 284 把 `__index` 设成**元表自己**
//:   （一张表）⇒ minimapi 当函数一调就炸，而且它 `rawset` 了包装之后，**Level 实例的每一次
//:   属性查找**都会走到这条会报错的路上 ⇒ 同一条派发链上后面的模组跟着断（GoodTrip 的画地图
//:   就在其中）。
//: PC 的类元表 `__index` 是**函数** —— 本仓 `Game`（`GameIndex`）/`RoomDescriptor`/`GridEntity`
//: 族全都是函数，`Level` 是唯一一处写成了表。这里补成同形。
//: 语义与表 `__index` **等价**：Lua 对表 `__index` 做的就是 `rawget`，这里照做（上值 1 = 类元表）。
int LevelIndex(lua_State* state) {
    if(const char* key=lua_tostring(state,2);IsApi600WorldField("Level",key)){std::uintptr_t level{};if(ResolveCurrentLevel(&level))if(const int n=TryPushApi600WorldField(state,level,"Level",key))return n;}
    const char* key = lua_tostring(state, 2);
    if (key != nullptr && std::strcmp(key, "EnterDoor") == 0) {
        luaL_checkudata(state, 1, kLevelMetatable);
        std::uintptr_t level = 0;
        std::int32_t door = 0;
        if (!ResolveCurrentLevel(&level) ||
            !isaac::runtime::engine_memory::ReadAt(level + kLevelEnterDoorOffset, &door,
                                                  &IsEngineMemoryReadable)) {
            lua_pushnil(state);
        } else {
            lua_pushinteger(state, static_cast<lua_Integer>(door));
        }
        return 1;
    }
    // 上值 1 = 类元表自己（方法就落在它身上）。
    lua_pushvalue(state, lua_upvalueindex(1));
    lua_pushvalue(state, 2);
    lua_rawget(state, -2);
    lua_remove(state, -2);
    return 1;
}

//: `RoomDescriptor.Data` 暴露给 Lua 的**表**（`data == 0` ⇒ 字段全 0；见上面两处调用点）。
//: 为什么必须"建全字段"而不是漏建：漏建就是 nil，模组一索引就崩
//: （`control.lua:339` 的 `crd.Data.Type` 就是这么把回调打断的）。
void PushRoomConfigRoom(lua_State* state, std::uintptr_t data,std::uintptr_t owner=0) {
    if(data){PushApi500RoomConfig(state,data,owner);return;}
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
    // `Spawns`：**批次 347 起是真容器**（机制与取证见 `PushSpawnList` 上方的注释块）。
    // 放在字段循环之后：它的两条偏移（`+0x50` 指针 / `+0x58` u16 计数）不走那张四字节表。
    PushSpawnList(state, data);
    lua_setfield(state, -2, "Spawns");
}

int Api500PushRoomSpawns(lua_State*state,std::uintptr_t data) {
    PushSpawnList(state,data);return 1;
}

void PushEmptyRoomConfigRoom(lua_State* state) {
    PushRoomConfigRoom(state, 0);
}

// `RoomDescriptor` 的字段访问。**只服务已 confirmed 的字段**；其它一律 nil。
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
        if(const int pushed=TryPushApi500GridField(state,entity,key))return pushed;
    if(const int n=TryPushApi600GridField(state,entity,key))return n;
    if(const int n=TryPushApi700GridField(state,key))return n;
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
                return PushNativeFallbackInteger(state, kFbGridEntityVarData, 0);
            }
            lua_pushinteger(state, static_cast<lua_Integer>(value));
            return 1;
        }
        if (std::strcmp(key, "Desc") == 0) {
            // PC 里这是 `GridEntityDesc` 对象；这里给一张**只含已取证字段**的表：
            // `Type`(+0x08)、`Variant`(+0x10)、`VarData`(+0x1C) —— 三个都来自
            // "`GridEntity::Init(const Desc&)` 把 `Desc[0x00..0x1F]` 拷到对象 `+0x08..+0x27`"这条结构证据
            // （见 `kGridEntityTypeOffset` 的注释）。没取证的成员不编值。
            // ★ 批次 342：这张表的构造**抽成 `PushGridEntityDescTable`** —— 契约
            //   `GridEntity.md:49` 说 `Desc` 与 `GetSaveState()` 返回**同一个对象**，
            //   两处各写一份迟早只补一边。
            if (!PushGridEntityDescTable(state, entity)) {
                lua_pushnil(state);
                return 1;
            }
            return 1;
        }
    }
    // 落到 `GridEntity` 的方法表（`GetType`/`GetVariant`/`GetRNG`…）。
    luaL_getmetatable(state, LuaRuntime::kGridEntityMetatable);
    lua_getfield(state, -1, "__methods");
    if (lua_istable(state, -1)) {
        const char* subclass=nullptr;
        std::uintptr_t subtypeVptr{};
        if(entityPointer&&key&&(std::strcmp(key,"MakeBridge")==0||std::strcmp(key,"SetLadder")==0||std::strcmp(key,"UpdateCollision")==0||std::strcmp(key,"RespawnRedPoop")==0||std::strcmp(key,"ReduceSpawnRate")==0||std::strcmp(key,"Reward")==0)&&
           isaac::runtime::engine_memory::ReadField(isaac::runtime::engine_memory::AddressOf(entityPointer),0,&subtypeVptr,isaac::runtime::engine_memory::EngineMemoryReadable)){
            const auto base=LuaRuntime::EngineModuleBase();
            if(subtypeVptr==base+kGridEntity_PitVtableOffset)subclass="__pitMethods";
            else if(subtypeVptr==base+kGridEntity_PoopVtableOffset)subclass="__poopMethods";
            else if(subtypeVptr==base+kGridEntity_PressurePlateVtableOffset)subclass="__plateMethods";
        }
        if(subclass){lua_getfield(state,-1,subclass);lua_getfield(state,-1,key);lua_remove(state,-2);lua_remove(state,-2);lua_remove(state,-2);return 1;}
        // ToRock/ToDoor return existing Grid views; expose subclass methods only for actual types.
        const bool rockKey=key&&(std::strcmp(key,"GetRubbleAnim")==0||std::strcmp(key,"GetBigRockFrame")==0||std::strcmp(key,"SetBigRockFrame")==0||std::strcmp(key,"UpdateAnimFrame")==0);
        const bool doorKey=key&&(std::strcmp(key,"IsBusted")==0||std::strcmp(key,"IsLocked")==0||std::strcmp(key,"IsKeyFamiliarTarget")==0||std::strcmp(key,"GetSpriteOffset")==0||std::strcmp(key,"CanBlowOpen")==0||std::strcmp(key,"SetLocked")==0||std::strcmp(key,"SetRoomTypes")==0||std::strcmp(key,"SpawnDust")==0||std::strcmp(key,"TryBlowOpen")==0||std::strcmp(key,"TryUnlock")==0);
        std::uintptr_t vptr{};
        if(entityPointer&&(rockKey||doorKey)&&isaac::runtime::engine_memory::ReadField(isaac::runtime::engine_memory::AddressOf(entityPointer),0,&vptr,isaac::runtime::engine_memory::EngineMemoryReadable)&&
           vptr==LuaRuntime::EngineModuleBase()+(rockKey?kGridEntity_RockVtableOffset:kGridEntity_DoorVtableOffset)){
            lua_getfield(state,-1,rockKey?"__rockMethods":"__doorMethods");
            if(lua_istable(state,-1)){
                lua_getfield(state,-1,key);lua_remove(state,-2);lua_remove(state,-2);lua_remove(state,-2);return 1;
            }
            lua_pop(state,1);
        }
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
    if(std::strcmp(key,"Desc")==0) {
        if(!PushGridEntityDescTable(state,entity))lua_pushnil(state);
        return 1;
    }
    if(const int pushed=TryPushApi500GridField(state,entity,key))return pushed;
    if(const int n=TryPushApi600GridField(state,entity,key))return n;
    if(const int n=TryPushApi700GridField(state,key))return n;
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
        if (!CallRoomDoorSlotPosition(handle->slot, &position)) {
            lua_pushnil(state);
            return 1;
        }
        isaac::runtime::PushLuaVector(state, position.x, position.y);
        return 1;
    }
    // 批次 284：门**自己**的方法表（`Open`/`Close`/`IsTargetRoomArcade`）。
    // ★ 顺序要紧：**字段 → 门自己 → `GridEntity` 基类**。所以这一段必须在下面那次
    //   `GridEntityIndex(state)` 转调**之前**。
    // ★★ 别把它写进 `GridEntityIndex`（第一版就写错在那儿了，被 `batch284` 的用例抓到）：
    //   那样一来**石头/便便**这类普通网格实体去取 `Open` 也会命中门那张表 ⇒ 会拿一个
    //   `GridEntity_Rock*` 去调 `GridEntity_Door::Open()`，那是对别人内存的破坏。
    luaL_getmetatable(state, LuaRuntime::kGridEntityDoorMetatable);
    lua_getfield(state, -1, "__methods");
    if (lua_istable(state, -1)) {
        lua_getfield(state, -1, key == nullptr ? "" : key);
        if (!lua_isnil(state, -1)) {
            lua_remove(state, -2);
            lua_remove(state, -2);
            return 1;
        }
        lua_pop(state, 1);
    }
    lua_pop(state, 2);
    // 落到 `GridEntity` **基类**（字段 + 方法表）。2026-09-21 起基类的 `__index` 也是函数
    // （它要多答几个字段），所以这里直接转调，而不是像以前那样取一张 `__index` 表。
    return GridEntityIndex(state);
}

//: `RoomConfigSpawn` 的属性——**手写而不走字段行**：`FieldKind` 里既没有「读侧浮点」也没有
//: 「读 u8」两档（P 组 §2.7 第 3 条），而视图本来就要手写 ⇒ 手写省掉一次「新开 kind」的账。
//: ★ 读不到时给**数值零**而不是 `nil`：PC 返回的是数字，`nil` 会让语料里
//:   `local sumWeight = spawn.SumWeights` 之后的除法直接抛错。
#if !defined(__SWITCH__)
void SetRoomConfigSpawnPickEntryHostImplementation(
    RoomConfigSpawnPickEntryHostImplementation function) noexcept {
    g_RoomConfigSpawnPickEntryHostImplementation = function;
}
#endif

int RoomConfigSpawnIndex(lua_State* state) {
    CheckApi600RoomConfigView(state,1);
    auto* handle = static_cast<LuaRuntime::RoomConfigSpawnHandle*>(
        luaL_checkudata(state, 1, LuaRuntime::kRoomConfigSpawnMetatable));
    const char* key = lua_tostring(state, 2);
    if(const int n=TryPushApi600SpawnField(state,1,key))return n;
    if (handle == nullptr || key == nullptr) {
        lua_pushnil(state);
        return 1;
    }
    const std::uintptr_t spawn = isaac::runtime::engine_memory::AddressOf(handle->spawn);
    if (std::strcmp(key, "SumWeights") == 0) {
        float value = 0.0F;
        if (spawn != 0) {
            static_cast<void>(isaac::runtime::engine_memory::ReadAt(
                spawn + kRoomConfigSpawnSumWeightsOffset, &value, &IsEngineMemoryReadable));
        }
        lua_pushnumber(state, static_cast<lua_Number>(value));
        return 1;
    }
    if (std::strcmp(key, "EntryCount") == 0) {
        std::uint8_t value = 0;
        if (spawn != 0) {
            static_cast<void>(isaac::runtime::engine_memory::ReadAt(
                spawn + kRoomConfigSpawnEntryCountOffset, &value, &IsEngineMemoryReadable));
        }
        lua_pushinteger(state, static_cast<lua_Integer>(value));
        return 1;
    }
    //: ★★ 这里**故意不答 `X`/`Y`**：PC 有，但 Switch 侧那两个偏移只有 `candidate` 级证据
    //:   （无具名访问器）⇒ 按本项目口径不对外 ⇒ 模组读 `spawn.X` 得 `nil`（已并入偏离登记）。
    luaL_getmetatable(state, LuaRuntime::kRoomConfigSpawnMetatable);
    lua_getfield(state, -1, "__methods");
    if (lua_istable(state, -1)) {
        lua_getfield(state, -1, key);
        if (!lua_isnil(state, -1)) {
            lua_remove(state, -2);
            lua_remove(state, -2);
            return 1;
        }
        lua_pop(state, 1);
    }
    lua_pop(state, 2);
    lua_pushnil(state);
    return 1;
}

//: `RoomConfigEntry` 的四个属性（PC 这一页只有这四个变量，没有方法）。
//: ★★ `Variant`/`SubType` **必须按 i16 符号扩展**：PC 的类型是 `int`（`0xFFFF` ⇒ `-1`），
//:   而引擎里这两格是 **u16** —— 若按零扩展读，`-1` 会被答成 `65535`，与 PC 不一致。
//:   （既有 `ReadRoomConfigEntryFields` 是零扩展，**不能复用**；本处按 `std::int16_t` 读。）
int RoomConfigEntryIndex(lua_State* state) {
    CheckApi600RoomConfigView(state,1);
    auto* handle = static_cast<LuaRuntime::RoomConfigEntryHandle*>(
        luaL_checkudata(state, 1, LuaRuntime::kRoomConfigEntryMetatable));
    const char* key = lua_tostring(state, 2);
    if (handle == nullptr || key == nullptr) {
        lua_pushnil(state);
        return 1;
    }
    const std::uintptr_t entry = isaac::runtime::engine_memory::AddressOf(handle->entry);
    if (std::strcmp(key, "Type") == 0) {
        std::int32_t value = 0;
        if (entry != 0) {
            static_cast<void>(isaac::runtime::engine_memory::ReadAt(
                entry + kRoomConfigEntryTypeOffset, &value, &IsEngineMemoryReadable));
        }
        lua_pushinteger(state, static_cast<lua_Integer>(value));
        return 1;
    }
    if (std::strcmp(key, "Variant") == 0 || std::strcmp(key, "SubType") == 0) {
        std::int16_t value = 0;   // ★ i16 ⇒ 符号扩展（`0xFFFF` 读成 `-1`）
        if (entry != 0) {
            const std::uintptr_t offset = key[0] == 'V' ? kRoomConfigEntryVariantOffset
                                                        : kRoomConfigEntrySubTypeOffset;
            static_cast<void>(isaac::runtime::engine_memory::ReadAt(entry + offset, &value,
                                                                   &IsEngineMemoryReadable));
        }
        lua_pushinteger(state, static_cast<lua_Integer>(value));
        return 1;
    }
    if (std::strcmp(key, "Weight") == 0) {
        float value = 0.0F;
        if (entry != 0) {
            static_cast<void>(isaac::runtime::engine_memory::ReadAt(
                entry + kRoomConfigEntryWeightOffset, &value, &IsEngineMemoryReadable));
        }
        lua_pushnumber(state, static_cast<lua_Number>(value));
        return 1;
    }
    lua_pushnil(state);
    return 1;
}

std::size_t AttachRoomConfigSpawnMethods(lua_State* state) noexcept {
    return AttachOwnerMethods(state, "RoomConfigSpawn", kRoomConfigSpawnHandlers,
                              RowCount(kRoomConfigSpawnHandlers));
}

std::size_t AttachRoomConfigEntryMethods(lua_State* state) noexcept {
    //: `RoomConfigEntry` 只有四个变量、没有方法 ⇒ 方法表留空（`__index` 只答属性）。
    return AttachOwnerMethods(state, "RoomConfigEntry", nullptr, 0);
}

int RoomDescriptorNewIndex(lua_State* state) {
    auto* handle=static_cast<LuaRuntime::RoomDescriptorHandle*>(luaL_checkudata(state,1,LuaRuntime::kRoomDescriptorMetatable));
    const char* field=luaL_checkstring(state,2);const auto descriptor=engine_memory::AddressOf(handle->descriptor);
    if(TryWriteApi500DescriptorField(state,descriptor,field))return 0;
    if(TryWriteApi600WorldField(state,descriptor,"RoomDescriptor",field))return 0;
    if(descriptor&&TryWriteExtendedRoomDescriptorField(state,descriptor,field))return 0;
    return luaL_error(state,"RoomDescriptor has no writable field named %s",field);
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
    if(const int pushed=TryPushApi500DescriptorField(state,descriptor,key))return pushed;
    if(const int n=TryPushApi600WorldField(state,descriptor,"RoomDescriptor",key))return n;
    if(descriptor)if(const int pushed=TryPushExtendedRoomDescriptorField(state,descriptor,key))return pushed;
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
            // 批次 250：与上面"空句柄"分支**同一个口径**（-1），不再抛错 —— 两处口径必须一致，
            // 否则"空句柄"和"读不到"会给模组两种不同的行为，而 PC 上这两种情形都不存在。
            return PushNativeFallbackInteger(state, kFbRoomDescriptorGridIndex,
                                             kAbsentRoomGridIndex);
        }
        lua_pushinteger(state, static_cast<lua_Integer>(static_cast<std::int32_t>(value)));
        return 1;
    }
    if (std::strcmp(key, "SafeGridIndex") == 0) {
        if (!ReadDescriptorU32(descriptor, kSafeGridIndexOffset, &value)) {
            return PushNativeFallbackInteger(state, kFbRoomDescriptorSafeGridIndex,
                                             kAbsentRoomGridIndex);
        }
        lua_pushinteger(state, static_cast<lua_Integer>(static_cast<std::int32_t>(value)));
        return 1;
    }
    if (std::strcmp(key, "ListIndex") == 0) {
        if (!ReadDescriptorU32(descriptor, kListIndexOffset, &value)) {
            return PushNativeFallbackInteger(state, kFbRoomDescriptorListIndex,
                                             kAbsentRoomGridIndex);
        }
        lua_pushinteger(state, static_cast<lua_Integer>(value));
        return 1;
    }
    if (std::strcmp(key, "VisitedCount") == 0) {
        if (!ReadDescriptorU32(descriptor, kVisitedCountOffset, &value)) {
            return PushNativeFallbackInteger(state, kFbRoomDescriptorVisitedCount, 0);
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
            return PushNativeFallbackInteger(state, kFbRoomDescriptorDisplayFlags, 0);
        }
        lua_pushinteger(state, static_cast<lua_Integer>(value));
        return 1;
    }
    if (std::strcmp(key, "Flags") == 0) {
        // PC 的 `RoomDescriptor.Flags`：32 位位掩码（EID 用 `room.Flags & 1024` 做道具预测）。
        if (!ReadDescriptorU32(descriptor, kFlagsOffset, &value)) {
            return PushNativeFallbackInteger(state, kFbRoomDescriptorFlags, 0);
        }
        lua_pushinteger(state, static_cast<lua_Integer>(value));
        return 1;
    }
    if (std::strcmp(key, "Clear") == 0) {
        if (!ReadDescriptorU32(descriptor, kClearOffset, &value)) {
            return PushNativeFallbackBoolean(state, kFbRoomDescriptorClear, false);
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
        PushRoomConfigRoom(state, data,descriptor);
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
    const char* key=lua_tostring(state,2);
    const char* owner=luaL_testudata(state,1,LuaRuntime::kGameMetatable)?"Game":luaL_testudata(state,1,LuaRuntime::kLevelMetatable)?"Level":nullptr;
    if(owner&&IsApi600WorldField(owner,key)){std::uintptr_t p{};if(ResolveCurrentLevel(&p)&&TryWriteApi600WorldField(state,p,owner,key))return 0;}
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

//: 批次 349（2026-10-04）：`RoomDescriptorList.__len` —— `#rooms`。
//: 与上面的 `.Size` **同一个来源**（`DescriptorCount`，每次现读、不缓存），所以两者永远一致。
//: 为什么必须有：PC 的 `RoomDescriptorList` 是个列表，模组可以直接 `#rooms`；minimapi 就是这么写的
//: （`main.lua:680`/`:734`/`:840`/`:886` 的 `for i = 0, #rooms - 1 do` 与
//: `MinimapAPI.CheckedRoomCount = #rooms`）。没有 `__len` 时 Lua 报
//: `attempt to get length of a IsaacRuntime.RoomDescriptorList value` ——
//: 真机症状 = `MinimapAPI` 收集房间那一支被整条打断。
int RoomDescriptorListLen(lua_State* state) {
    auto* handle = static_cast<LuaRuntime::RoomDescriptorListHandle*>(
        luaL_checkudata(state, 1, LuaRuntime::kRoomDescriptorListMetatable));
    if (handle == nullptr) {
        lua_pushinteger(state, 0);
        return 1;
    }
    lua_pushinteger(state, static_cast<lua_Integer>(
        DescriptorCount(isaac::runtime::engine_memory::AddressOf(handle->level))));
    return 1;
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
    // ---- 批次 238：`Room:GetRoomConfigStage`（int GetRoomConfigStage ( )）
    // 符号 `_ZNK15IsaacRepentance4Room18GetRoomConfigStageEv`；形状按符号参数表取（见 `runtime_constants.hpp` 的批次 238 段）。
    {0x0401000F, kRoomGetRoomConfigStageOffset, kRoomGetRoomConfigStageEntryWord, FieldReceipt::Room,
     EngineCallShape::Int0, 0, 0xFF},
    // ---- 批次 238：`Room:HasCurseMist`（boolean HasCurseMist ( )）
    // 符号 `_ZNK15IsaacRepentance4Room12HasCurseMistEv`；形状按符号参数表取（见 `runtime_constants.hpp` 的批次 238 段）。
    {0x04010010, kRoomHasCurseMistOffset, kRoomHasCurseMistEntryWord, FieldReceipt::Room,
     EngineCallShape::Bool0, 0, 0xFF},
    // ---- 批次 238：`Room:IsAmbushActive`（boolean IsAmbushActive ( )）
    // 符号 `_ZNK15IsaacRepentance4Room14IsAmbushActiveEv`；形状按符号参数表取（见 `runtime_constants.hpp` 的批次 238 段）。
    {0x04010011, kRoomIsAmbushActiveOffset, kRoomIsAmbushActiveEntryWord, FieldReceipt::Room,
     EngineCallShape::Bool0, 0, 0xFF},
    // ---- 批次 238：`Room:IsCurrentRoomLastBoss`（boolean IsCurrentRoomLastBoss ( )）
    // 符号 `_ZNK15IsaacRepentance4Room21IsCurrentRoomLastBossEv`；形状按符号参数表取（见 `runtime_constants.hpp` 的批次 238 段）。
    {0x04010012, kRoomIsCurrentRoomLastBossOffset, kRoomIsCurrentRoomLastBossEntryWord, FieldReceipt::Room,
     EngineCallShape::Bool0, 0, 0xFF},
    // ---- 批次 238：`Room:RemoveDoor`（void RemoveDoor ( [DoorSlot](enums/DoorSlot.md) Slot )）
    // 符号 `_ZN15IsaacRepentance4Room10RemoveDoorENS_9eDoorSlotE`；形状按符号参数表取（见 `runtime_constants.hpp` 的批次 238 段）。
    {0x04010013, kRoomRemoveDoorOffset, kRoomRemoveDoorEntryWord, FieldReceipt::Room,
     EngineCallShape::Void1, 1, 0xFF},
    // ---- 批次 238：`Room:Update`（void Update ( )）
    // 符号 `_ZN15IsaacRepentance4Room6UpdateEv`；形状按符号参数表取（见 `runtime_constants.hpp` 的批次 238 段）。
    {0x04010014, kRoomUpdateOffset, kRoomUpdateEntryWord, FieldReceipt::Room,
     EngineCallShape::Void0, 0, 0xFF},
    // ---- 批次 239：`Room:RemoveGridEntity`（void RemoveGridEntity ( int GridIndex, int PathTrail, boolean KeepDecoration )）
    // 第 3 个参数在语料里是 Lua 布尔 ⇒ 形状 `VoidIntIntBool`；符号是 3 格、语料也传 3 个。
    {0x04010015, kRoomRemoveGridEntityOffset, kRoomRemoveGridEntityEntryWord, FieldReceipt::Room,
     EngineCallShape::VoidIntIntBool, 3, 0xFF},
    // ---- 批次 239：`Room:GetGridCollision`（GridCollisionClass GetGridCollision ( int GridIndex )）
    // 枚举返回按整数压回 ⇒ `Int1`。
    {0x04010016, kRoomGetGridCollisionOffset, kRoomGetGridCollisionEntryWord, FieldReceipt::Room,
     EngineCallShape::Int1, 1, 0xFF},
    // ---- 批次 239：`Room:SetGridPath`（boolean SetGridPath ( int Index, int Value )）
    // ★ 文档 2 个参数、符号 `SetGridPath(int, int, int)` 是 3 个 ⇒ 形状按**符号**取 3 格，
    //   语料只传 2 个（`shared.Room:SetGridPath(i, 0)`）⇒ `BoolIntIntInt` 声明尾部 1 个可省。
    {0x04010017, kRoomSetGridPathOffset, kRoomSetGridPathEntryWord, FieldReceipt::Room,
     EngineCallShape::BoolIntIntInt, 3, 0xFF},
    // ---- 批次 239：`Room:SpawnClearAward`（void SpawnClearAward ( )）
    {0x04010018, kRoomSpawnClearAwardOffset, kRoomSpawnClearAwardEntryWord, FieldReceipt::Room,
     EngineCallShape::Void0, 0, 0xFF},
    // ---- 批次 239：`Room:DestroyGrid`（boolean DestroyGrid ( int Index, boolean Immediate )）
    // ★ 文档 2 个、符号 `DestroyGrid(int, bool, bool)` 是 3 个 ⇒ 按符号取；
    //   语料只传 1 个（`room:DestroyGrid(ind)`）⇒ `BoolIntBoolBool` 声明尾部 2 个可省。
    {0x04010019, kRoomDestroyGridOffset, kRoomDestroyGridEntryWord, FieldReceipt::Room,
     EngineCallShape::BoolIntBoolBool, 3, 0xFF},
    // ---- 批次 239：`Room:TurnGold`（void TurnGold ( )）
    {0x0401001A, kRoomTurnGoldOffset, kRoomTurnGoldEntryWord, FieldReceipt::Room,
     EngineCallShape::Void0, 0, 0xFF},
    // ---- 批次 252（2026-10-01）：`Room:SpawnGridEntity`
    //   （boolean SpawnGridEntity ( int GridIndex, GridEntityType Type, int Variant, int Seed, int VarData )）
    // PC 契约 `tools/pc_contract_docs/Room.md:867`。
    // ★ 契约写返回 `boolean`，但引擎符号 `_ZN15IsaacRepentance4Room15SpawnGridEntityEiNS_15eGridEntityTypeEjji`
    //   **没有返回值特征**（`void`）⇒ 形状按**符号**取（G3 口径，不按文档）：`VoidIntIntIntIntInt`。
    // ★ 语料传满 5 个（`BOIStageAPI15/scripts/stageapi/room/roomHandler.lua:59` 的
    //   `SpawnGridEntity(index, GridEntityType.GRID_WALL, 0, 1, 0)`）且**不接返回值**。
    //   日后若发现模组拿返回值判断，再单独核实（**不猜**）。
    {0x0401001E, kRoomSpawnGridEntityOffset, kRoomSpawnGridEntityEntryWord, FieldReceipt::Room,
     EngineCallShape::VoidIntIntIntIntInt, 5, 0xFF},
    // ---- 批次 253（2026-10-01）：`Room:IsPositionInRoom`
    //   （boolean IsPositionInRoom ( Vector Pos, float Margin )），PC 契约 `Room.md:691`。
    // ★ 引擎收的是 `Vector2 const&`（mangled 里的 `RKN4KAGE4Math7Vector2E`）⇒ 走**指针**，
    //   不需要扩跳板：形状 `BoolVector2RefFloat` 会把 Lua 的 Vector 拷进我们栈上的槽再传地址。
    // 语料实参 2 个（无缺省值）：`room:IsPositionInRoom(pos, 0)`。
    {0x0401001F, kRoomIsPositionInRoomOffset, kRoomIsPositionInRoomEntryWord, FieldReceipt::Room,
     EngineCallShape::BoolVector2RefFloat, 2, 0xFF},
};

//: `Room` 族的**字段读取型 API**（批次 289，2026-10-02）。**家族的行表住在自己的 TU 里**
//: （契约门禁逐条核对），处理器 `FieldApiHandler` 是共享的那一个。
//:
//: 批次 289 那两条在引擎里**没有同名访问器**：PC 侧 `Room:GetTopLeftPos()` / `GetBottomRightPos()`
//: 的本体就是"原样返回成员"（`0x432630 mov edx,[ecx+0x14]` / `0x432650 mov edx,[ecx+0x1c]`），
//: Switch 构建里连符号都没有 ⇒ **直读引擎自己的矩形边界成员**才是与 PC 等价的做法
//: （偏移的由来与四条独立互证见 `runtime_constants.hpp` 的批次 289 段，以及
//: `tools/layout_tables/room.json` 的 `TopLeft` / `BottomRight` 两行）。
//:
//: 接收者不是从 Lua 栈上取的，而是"当前房间"（`FieldReceipt::Room`，与 `Room:PlayMusic()`
//: 同一条解析链）⇒ 栈上那**一个**参数就是冒号调用压进来的 `self`：语料里这两条全是冒号写法
//: （`room:GetTopLeftPos()`、`Game():GetRoom():GetBottomRightPos()`），
//: `FieldApiHandler` 的"恰好一个参数"闸门天然满足。
//:
//: 批次 291（2026-10-02）再加 4 条，接收者分两类：
//:   * `Room:GetBossID()` / `Room:IsFirstVisit()` —— 字段在 `Room` 自己身上 ⇒ `FieldReceipt::Room`；
//:   * `Room:IsAmbushDone()` / `Room:HasWaterPits()` —— 字段在**描述符**的 `Flags` 位掩码上
//:     ⇒ 本批新收的 `FieldReceipt::RoomDescriptor`（「当前房间 → `Room+0x8`」一跳的末端）
//:     + 本批新增的 `FieldKind::BoolBit`（单独测某一位）。
//:   ★ 两条描述符位的 `offset2` 写的是**字面位号**（3 / 5），不是具名常量 ——
//:     `test_field_api_rows.py` 的 `offset2` 解析式只认 `k…Offset` / 十六进制 / 十进制字面量，
//:     写成 `k…Bit` 那样的名字会让**这一行对门禁隐形**（行的 id/偏移/接收者就不再被校验）。
//:     位号的含义写在 `runtime_constants.hpp` 的批次 291 段与这里的行注释里。
//: 四条的证据链（PC 绑定函数本体 + Switch 侧具名消费者）全在 `runtime_constants.hpp` 的批次 291 段。
//:
//: 返回值是 `Vector`（两个 float）⇒ `FieldKind::Vector2Pair`（压真正的 Lua `Vector`，
//: 模组接着取 `.X`/`.Y` 或继续做向量运算）。
constexpr FieldApiRow kRoomFieldApis[] = {
    // 0x0026 `Room:GetTopLeftPos()` —— PC 契约 `Room.md:566`：
    // Returns the top-left position inside of the walls.（`offset2` = X + 4 = Y 那一半）
    {0x04010026, kRoomTopLeftPosOffset, 0x20, FieldKind::Vector2Pair, FieldMissing::Zero,
     FieldReceipt::Room, 0xFF},
    // 0x0027 `Room:GetBottomRightPos()` —— PC 契约 `Room.md:119`：
    // Returns bottom right position of the room, inside of the wall border.
    {0x04010027, kRoomBottomRightPosOffset, 0x28, FieldKind::Vector2Pair, FieldMissing::Zero,
     FieldReceipt::Room, 0xFF},
    // 0x0028 `Room:GetRoomShape()`（批次 290，2026-10-02）—— PC 契约 `Room.md:530`：
    // #### [RoomShape](enums/RoomShape.md) GetRoomShape ( ) （文档只给了签名与返回类型，没有散文；
    // 真正的行为在绑定函数本体里，见下）。
    //
    // ★ 接收者是**两跳指针链的末端**（`FieldReceipt::RoomConfigData`）：形状不在 `Room` 上，
    //   而在 `Room → RoomDescriptor → RoomConfig::Room` 里 —— PC 的绑定函数（`0x444C30`）与
    //   Switch 侧三条独立读者（`Room::IsLShapedRoom @ 0x48453C` / `Room::GetLRoomAreaDesc @ 0x484558` /
    //   `Room::Init @ 0x45F974`）走的是同一条链、同一个形状区间 9..12（四个 L 形）。
    //   证据链与"为什么不搬 PC 的偏移"写在 `runtime_constants.hpp` 的 `kRoomConfigShapeOffset` 处。
    //
    // ★ 降级取 `One` 而不是 `Zero`：PC 自己在两跳任一为空时答常量 **1**（`0x444C42 mov eax,0x1`），
    //   而 1 就是 `ROOMSHAPE_1x1`（见 `doc_lua_enum_data.cpp` 的 `kRoomShapeValues`）。
    {0x04010028, kRoomConfigShapeOffset, 0x00, FieldKind::U32, FieldMissing::One,
     FieldReceipt::RoomConfigData, 0xFF},
    // 0x0029 `Room:GetBossID()`（批次 291，2026-10-02）—— PC 契约 `Room.md:109`：
    // #### int GetBossID ( ) —— "Returns the boss ID of the **first boss** in the room."
    // ★ 字段在 `Room` 自己身上（`Room+0x1FC0`）：`Room::Init` 把房间里第一个非零的
    //   `EntityConfig::Entity + 0x34`（= entities2.xml 的 `bossID` 属性）写进这一格。
    // ★ 降级 `Zero`：PC 的绑定函数本体（`0x430D60`）就是 `mov eax,[ecx+0x1d1c]; ret`，
    //   没有任何空指针检查；契约也写明"不是 Boss 就返回 0" ⇒ 读不到时答 0 与 PC 同口径。
    {0x04010029, kRoomBossIdOffset, 0x00, FieldKind::U32, FieldMissing::Zero,
     FieldReceipt::Room, 0xFF},
    // 0x002A `Room:IsFirstVisit()`（批次 291，2026-10-02）—— PC 契约 `Room.md:670`：
    // #### boolean IsFirstVisit ( )（文档只给签名、没有散文；语义靠引擎自己的读者定）。
    // ★ 这是 `Room+0x1` 的**一个字节**（PC 绑定 `0x638F90` = `mov al,[ecx+1]; ret`）
    //   ⇒ `FieldKind::Bool`（读字节、非零即真），不是 `BoolNonZero`（那个读 4 字节）。
    // ★ `Room::Init` 在 `VisitedCount == 0` 时把它置 1、`Room::RespawnEnemies` 清零它
    //   （并在同一处把 `VisitedCount` 加一）⇒ 它只在"第一次进这间房"时为真。
    // ★ 降级 `False`：读不到就答"不是首次"（保守：模组会少做一次一次性初始化，
    //   而答 true 会让"每个房间都当成首次"）。
    {0x0401002A, kRoomFirstVisitOffset, 0x00, FieldKind::Bool, FieldMissing::False,
     FieldReceipt::Room, 0xFF},
    // 0x002B `Room:IsAmbushDone()`（批次 291，2026-10-02）—— PC 契约 `Room.md:639`：
    // #### boolean IsAmbushDone ( )（同样只有签名）。
    // ★ 描述符 `Flags`（`+0x50`）的 **bit3** = `CHALLENGE_DONE`。
    //   PC 绑定本体（`0x6DCE00`）：`[ecx+4]`（描述符）→ `[eax+0x44]` → `shr eax,3` → `and al,1`。
    //   Switch 侧两条具名消费者：`Ambush::StartChallenge`（bit3 置着就直接返回、不再开伏击）
    //   与 `Level::CanOpenChallengeRoom`（单独 `tbnz w9,#0x3`）。
    // ★ 接收者是**描述符**（`FieldReceipt::RoomDescriptor`），不是 `Room`：
    //   `Room+0x50` 与描述符 `+0x50` 是两个不同的字段。
    {0x0401002B, kRoomDescriptorFlagsOffset, 3, FieldKind::BoolBit, FieldMissing::False,
     FieldReceipt::RoomDescriptor, 0xFF},
    // 0x002C `Room:HasWaterPits()`（批次 291，2026-10-02）—— PC 契约 `Room.md:622`：
    // #### boolean HasWaterPits ( )。
    // ★ 同一个 `Flags` 的 **bit5** = `HAS_WATER`。PC 绑定本体（`0x4F3EC0`）：`shr eax,5` + `and al,1`。
    //   Switch 侧两条具名消费者：`Room::pre_render_pits` 与 `Room::pre_render_water`
    //   （都是 `tbz w8,#0x5` ⇒ 位没置就不渲染水坑）—— 函数名与判据一起把"水"钉在这位上。
    //   ★ 注意别拿 `Room::HasWater()`（`0x487FA0`）当锚点：那条读的是 `Room+0x7894` 的
    //     **水位浮点数**（`fcmp s0,#0.0` / `cset gt`），与"这间房的坑里有没有水"不是一回事。
    {0x0401002C, kRoomDescriptorFlagsOffset, 5, FieldKind::BoolBit, FieldMissing::False,
     FieldReceipt::RoomDescriptor, 0xFF},
    // 0x002D `Room:GetBackdropType()`（批次 292，2026-10-02）—— PC 契约 `Room.md:103`：
    // #### [BackdropType](enums/BackdropType.md) GetBackdropType ( ) ——
    // "Returns the BackdropType of the current room."
    // ★ 字段在 `Room` 自己身上（`Room+0x21B0`）：它其实是**内嵌的 `Backdrop` 子对象**里的
    //   `eBackdrop`（`Backdrop` 在 `Room+0x1FE0`、`Backdrop::Init` 把 eBackdrop 存进
    //   `Backdrop+0x1D0` ⇒ `0x1FE0+0x1D0 = 0x21B0`）。证据链见 `runtime_constants.hpp` 批次 292 段。
    // ★ 降级 `Zero`：PC 的绑定函数本体（`0x4BAEA0`）就是 `mov eax,[ecx+0x1e84]; ret`（无空指针检查），
    //   而这一格的**合法值域是 0..60**、0 就是 `BackdropType.BACKDROP_NULL`（"没有背景"）
    //   ⇒ 读不到时答 0 与"引擎里真写着 0"同值，且是枚举表里的合法成员（不会让模组索引到 nil）。
    // ★ 本批同时把 `BackdropType` 枚举表生成进运行时（`tools/pc_enum_docs/BackdropType.md` +
    //   `tools/generate_doc_enum_tables.py` 的 `TABLES`）—— 模组拿返回值直接与
    //   `BackdropType.BASEMENT` 一类比较/建表，少了表这一半它们仍然用不上（与批次 269 的
    //   `RenderMode` + `Room:GetRenderMode()` 是同一件事的两半）。
    {0x0401002D, kRoomBackdropTypeOffset, 0x00, FieldKind::U32, FieldMissing::Zero,
     FieldReceipt::Room, 0xFF},
    // 0x002E `Room:SetClear(boolean Clear)`（批次 292，2026-10-02）—— PC 契约 `Room.md:772`：
    // #### void SetClear ( boolean Clear ) ——
    // "Needed for Angel rooms so that the clear flag can be set to false when an Angel spawns."
    // ★ 语义 = **往描述符 `Flags`（`+0x50`）的 bit0 写实参**（`Room:IsClear()` 读的就是同一位，
    //   批次 207 落地）—— PC 绑定本体 `0x497800` 逐条如此：`mov edx,[ecx+4]`（描述符）→
    //   `mov ecx,[edx+0x44]` → `and eax,-2`（清 bit0）/ `or ecx,1`（置 bit0）→
    //   `cmp byte [ebp+8],0` + `cmove` → `mov [edx+0x44], ecx`。契约散文那句"Angel 出现时
    //   要能把清房标志**置回 false**"正说明"能清"是必须的。
    // ★★ **不走引擎自己的 `Room::TriggerClear(bool)`（`0x470B58`）**：那个函数除了置 bit0
    //   还会自增描述符 `+0x56` 的计数、调 `ScoreSheet::AddClearedRoom(...)`、
    //   并在 `Game+0x26FA88 == 0x1f` 时触发一串结算 —— **副作用远多于 PC 的 `SetClear`**
    //   （照它接线会"静默多做一堆事"，与本批判据'与 PC 一致'相悖）。
    // ★ 接收者是**描述符**（`FieldReceipt::RoomDescriptor`，批次 291 收的那条一跳链），
    //   不是 `Room`：`Room+0x50` 与描述符 `+0x50` 是两个不同的字段。
    // ★ 降级档写 `Zero` 只是为了满足行结构（本 kind **不返回值**，`missing` 用不上）。
    {0x0401002E, kRoomDescriptorFlagsOffset, 0, FieldKind::BoolBitWrite, FieldMissing::Zero,
     FieldReceipt::RoomDescriptor, 0xFF},
    // ---- 批次 295（2026-10-03）：房间的**两个种子**（各 8 处 = 16 处）----
    // 两条都是"读描述符上的一个 `i32`"，接收者是既有的 `FieldReceipt::RoomDescriptor`。
    // 偏移与证据（`Backdrop::SetSeed` 的喂入值 / 序列化字段表 / 硬核相关的挑格子）见
    // `runtime_constants.hpp` 的批次 295 段；布局表是 `room_descriptor.json` 的
    // `DecorationSeed` / `SpawnSeed` 两行（`--verify` 重新反汇编逐条核对）。
    // ★ 降级档 `Zero` 是**照 PC 抄的**：两条 PC 绑定本体都是
    //   「`mov eax,[ecx+4]`（描述符）→ 为空就直接返回 0」⇒ 描述符拿不到时 PC 也答 0。
    // 契约：`Room.md` 的 158（`GetDecorationSeed`）/ 556（`GetSpawnSeed`）行。
    {0x0401002F, kRoomDescriptorDecorationSeedOffset, 0, FieldKind::I32, FieldMissing::Zero,
     FieldReceipt::RoomDescriptor, 0xFF},
    {0x04010030, kRoomDescriptorSpawnSeedOffset, 0, FieldKind::I32, FieldMissing::Zero,
     FieldReceipt::RoomDescriptor, 0xFF},
    // ---- 批次 302（2026-10-03）：`Room:SetFloorColor` / `SetWallColor`（各 9 处 = 18 处）----
    // 「把一个 `Color` 句柄转成 44 字节 `ColorMod`、整块写进 `Room` 上这两个相邻成员」——
    // **本机制里第一条实参是 `Color` 的字段行**（新种类 `FieldKind::ColorModWrite`，
    // 返回 0 个值）。PC 的绑定本体各只有 12 条指令、就是"整块 44 字节拷贝"
    // （`0x7A7ED0` 的 `add ecx,0x7188`，`0x7A7F10` 的 `add ecx,0x71b4`，两条 `ret 0x2c`）。
    //
    // ★★ 为什么这两格就是地板/墙色（三条独立证据，详见 `runtime_constants.hpp` 的批次 302 段）：
    //   ① `Room::Room() @ 0x44E75C/0x44E768` 用**引擎自己的 `ColorMod::Reset()`** 分别初始化
    //      `Room+0x7968` 与 `Room+0x7994` ⇒ 两格都是 `ColorMod`，且**相距 `0x2C`**；
    //   ② `Room::Render` 把 `Room+0x7968` 的 44 字节喂给 **(a) `Backdrop::RenderFloor`**、
    //      `Room+0x7994` 的喂给 **(b) `Backdrop::RenderWalls`** ⇒ 一一对应、且这正是
    //      "真的会把它画出来"的那条调用链；
    //   ③ `Room::TurnGold @ 0x464AB0`（房间变金）写的是 **`Room+0x7994`** 那一份 ⇒ 墙色。
    //   ★ 顺序（地板在前）与间距（`0x2C`）**与 PC 完全一致**，只有绝对偏移不同（布局差异，
    //     **不许平移**）。
    // ★ 接收者用既有的 `FieldReceipt::Room`（解析"当前房间"）：语料 **18 处**全是
    //   `room = Game():GetRoom()` 之后调（逐调用点核过）⇒ 与批次 289/290/291/295 的 `Room` 族同口径。
    // ★ 降级档写 `Zero` 只为满足行结构（本 kind **不返回值**，`missing` 用不上）。
    // 契约：`Room.md` 的 783（`SetFloorColor`）/ 834（`SetWallColor`）行
    // （正文都是 "Allows you to apply a color modifier to the ... texture of the current room."）。
    {0x04010031, kRoomFloorColorModOffset, 0, FieldKind::ColorModWrite, FieldMissing::Zero,
     FieldReceipt::Room, 0xFF},
    {0x04010032, kRoomWallColorModOffset, 0, FieldKind::ColorModWrite, FieldMissing::Zero,
     FieldReceipt::Room, 0xFF},
    // ---- 批次 327（2026-10-03）：`Room:IsDoorSlotAllowed(DoorSlot)`（2 处 / 1 个模组）----
    // 语义 = **房间定义（XML）里这一个门位合不合法**（PC 契约 `Room.md:655`：
    // "Returns whether or not the supplied door slot is valid for the current room. This is
    //  contingent on the room definition in the STB/XML file ... The value returned by this
    //  method is **independent of whether or not a door currently exists** at the given slot."）
    // ⇒ 读的是 **`RoomConfig::Room.Doors`**（PC 文档 `RoomConfig_Room.md:29`：
    //   "Returns a bit mask of the positions of valid door positions in this room.
    //    It is a combination of bit flags of the DoorSlotFlag enum: LEFT0 = 1 << DoorSlot.LEFT0
    //    … DOWN1 = 1 << DoorSlot.DOWN1"）。
    //
    // ★ 接收者是既有的 `FieldReceipt::RoomConfigData`（批次 290 收的两跳链末端
    //   `Room → RoomDescriptor → RoomConfig::Room`）—— 与 `Room:GetRoomShape()` 同一条链，
    //   只差末端那一格的偏移（形状在 `Data+0x5C`、门位掩码在 `Data+0x40`）。
    // ★ 走既有的 `FieldKind::BoolBitArrayOfArg`（批次 297 立的：位号来自 Lua 实参、
    //   `offset2` = 元素宽度）。`Data+0x40` 在引擎里是按 **64 位**读的（`ldr x`，不是 `ldr w`）
    //   ⇒ 宽度写 **8**；位号就是 `DoorSlot` 自己的编号（`LEFT0`=0 … `DOWN1`=7，全落在低 8 位）。
    // ★ 偏移与四条独立证据（`Level::precalc_allowed_doors` 按门位逐位测 /
    //   `Level::get_room_neighbor_pos` 函数名即语义 / `Room::TrySpawnSecretExitEbb` 把
    //   "配置掩码"与"运行时掩码"的先后关系写死 / 十余处门逻辑同形）见
    //   `runtime_constants.hpp` 的批次 327 段；布局表是 `room_descriptor.json` 的
    //   `Data.Doors` 行（本批新加，`confirmed`，`--verify` 重新反汇编逐条核对）。
    // ★★ **别用描述符 `+0x20` 的 `RoomDescriptor.AllowedDoors` 代替它** —— 那是**运行时**那一份
    //   （由 `Level::precalc_allowed_doors` 现算、会随邻房/小 Boss 之类的事件变），
    //   与契约"与门此刻在不在无关"正相反。
    // ★ 越界口径（与 PC 的差异，**有意保留、和既有 `BoolBitArrayOfArg` 同一口径**）：
    //   PC 的护栏是 `(unsigned)(Slot+1) > 8 ⇒ false`（即 `Slot ∈ -1..7` 放行）；我们沿用
    //   "负位号 → 降级"的老口径 ⇒ **契约域 0..7 内与 PC 逐位一致**（语料那 2 处都是
    //   `for i = DoorSlot.LEFT0, DoorSlot.DOWN1` 的循环，全在域内）；`Slot < 0` 时我们答
    //   `false`（PC 那边是越界读、值无定义，不可比）。`Slot ≥ 8` 时 PC 答 `false`，我们读的是
    //   **同一个 8 字节掩码的高位** —— 引擎里这一格按 64 位读、只有低 8 位被当门位用
    //   （所有读者都只移 0..7 位）⇒ 高位恒 0 ⇒ 与 PC 的 false 同值；唯一的例外是 `Slot ≥ 64`
    //   会落到下一个元素（`Data+0x48`），那是**契约域之外**的输入。**不为这 2 处单开一种带护栏
    //   的 kind**（按批次 327 的成本账：一种新 `FieldKind` ≈ `.text` +0x40，而这一行是 0 字节），
    //   与 `Game`/`Level:GetStateFlag` 的越界口径同一档。
    // ★ 降级档 `False`：接收者链上任一环为空（没有房间/没有描述符/没有配置）时答
    //   "这个门位不合法" —— PC 的 `ja` 分支也是 `xor al,al`（答 false），口径一致。
    // 契约：`tools/pc_contract_docs/Room.md` 的 655 行。
    {0x04010036, kRoomConfigDoorsOffset, 8, FieldKind::BoolBitArrayOfArg, FieldMissing::False,
     FieldReceipt::RoomConfigData, 0xFF},
    // ---- 批次 336（2026-10-03 深夜）：`Room:GetTintedRockIdx()`（1 处 / 1 个模组）----
    // PC 契约 `Room.md:559/561`：逐字 `#### int GetTintedRockIdx ( )`（只有签名、没有散文）。
    // PC 绑定本体 `0x427750` = **`mov eax,[ecx+0x764]; ret`**（纯读一个 i32、**没有守卫**）
    // ⇒ 判法四档 ①档 ⇒ 字段数据行，接收者是既有的 `FieldReceipt::Room`（解析"当前房间"）。
    // ★ Switch 侧那一格 = **`Room + 0xE90`**（布局表 `room.json` 的 `TintedRockIdx` 行，`confirmed`）：
    //   三条独立证据（写入点是 `Room::Init` 里 `RNG::Next()`→`Room::GetRandomTileIndex()` 的返回值、
    //   具名消费者 `Room::spawn_entity` 拿它跟"当前要生成的格子索引"比、PC 侧 tinted/dungeon 两格
    //   **相邻且 tinted 在低地址**而 Switch 的 `GetDungeonRockIdx` 读 `Room+0xE94`）逐条写在
    //   `runtime_constants.hpp` 的批次 336 段。
    // ★ 降级档 `Zero`：PC 那半边**没有**兜底（它直接读那一格）；我们拿不到"当前房间"时按 0 降级
    //   —— 与同族的 `GetDecorationSeed`/`GetSpawnSeed` 同口径（那两条的 PC 兜底恰好也是 0）。
    {0x04010037, kRoomTintedRockIdxOffset, 0, FieldKind::I32, FieldMissing::Zero,
     FieldReceipt::Room, 0xFF},
};

//: 批次 291：描述符 `Flags` 的偏移在**两处**各有一个具名常量 —— 本表用的那个住在
//: `runtime_constants.hpp`（字段行的门禁只认那里，见该常量上方的说明），而布局表生成的
//: `layout::kRoomDescriptorFlagsOffset` 服务手写路径（例如批次 207 的 `Room:IsClear`）。
//: 同一个值写两遍迟早漂移，所以在这里编译期钉死：任何一边改了而另一边没改，构建直接失败。
static_assert(kRoomDescriptorFlagsOffset == layout::kRoomDescriptorFlagsOffset,
              "描述符 Flags 的偏移在 runtime_constants.hpp 与布局表生成物之间不一致");
//: 同上，批次 291 的两条新字段：布局表那两位（`Room.BossId` / `Room.FirstVisit`）是
//: `confirmed` 且带独立语义锚点（`build_layout_table.py --verify` 会重新反汇编核对），
//: 数据行用的常量则必须住在 `runtime_constants.hpp` —— 两份值不许漂移。
static_assert(kRoomBossIdOffset == layout::kRoomBossIdOffset,
              "Boss id 的偏移在 runtime_constants.hpp 与布局表生成物之间不一致");
static_assert(kRoomFirstVisitOffset == layout::kRoomFirstVisitOffset,
              "首次访问字节的偏移在 runtime_constants.hpp 与布局表生成物之间不一致");
static_assert(kRoomBackdropTypeOffset == layout::kRoomBackdropTypeOffset,
              "背景类型的偏移在 runtime_constants.hpp 与布局表生成物之间不一致");
//: 批次 302：地板/墙两个 `ColorMod` 同款（布局表那两行是 `confirmed`、`--verify` 重新反汇编核对）。
static_assert(kRoomFloorColorModOffset == layout::kRoomFloorColorModOffset,
              "地板颜色修饰的偏移在 runtime_constants.hpp 与布局表生成物之间不一致");
static_assert(kRoomWallColorModOffset == layout::kRoomWallColorModOffset,
              "墙壁颜色修饰的偏移在 runtime_constants.hpp 与布局表生成物之间不一致");
//: 批次 295：两个种子的偏移在布局表生成物里也叫同一个名字（`layout::` 命名空间下）⇒ 钉住。
static_assert(kRoomDescriptorDecorationSeedOffset == layout::kRoomDescriptorDecorationSeedOffset,
              "装饰种子的偏移在 runtime_constants.hpp 与布局表生成物之间不一致");
static_assert(kRoomDescriptorSpawnSeedOffset == layout::kRoomDescriptorSpawnSeedOffset,
              "出怪种子的偏移在 runtime_constants.hpp 与布局表生成物之间不一致");
//: 批次 294：`Level` 那两个房间索引同时住在 `game.json`（`struct: Game`，因为 `Level` 内嵌在
//: `Game` 起始处、同一地址）⇒ 生成的名字带 `Game` 前缀，与这里的 `kLevel…` 是两个名字、
//: 同一个值。同样编译期钉死不许漂移。
static_assert(kLevelPreviousRoomIndexOffset == layout::kGamePreviousRoomIndexOffset,
              "上一房间索引的偏移在 runtime_constants.hpp 与布局表生成物之间不一致");
static_assert(kLevelLastBossRoomListIndexOffset == layout::kGameLastBossRoomListIndexOffset,
              "最后 Boss 房索引的偏移在 runtime_constants.hpp 与布局表生成物之间不一致");
//: 批次 327：房间定义里的门位掩码（布局表 `room_descriptor.json` 的 `Data.Doors` 行，`confirmed`）。
//: 两份值一个是 `kRoomConfigDoorsOffset`（对外 API 用）、一个是 `layout::kRoomDescriptorDataDoorsOffset`
//: （生成物），编译期钉死不许漂移。
static_assert(kRoomConfigDoorsOffset == layout::kRoomDescriptorDataDoorsOffset,
              "房间门位掩码的偏移在 runtime_constants.hpp 与布局表生成物之间不一致");
//: 批次 336：染色石头索引（布局表 `room.json` 的 `TintedRockIdx` 行，`confirmed`，
//: `--verify` 重新反汇编逐条核对）。同一个值两处各写一遍 ⇒ 编译期钉死不许漂移。
static_assert(kRoomTintedRockIdxOffset == layout::kRoomTintedRockIdxOffset,
              "染色石头索引的偏移在 runtime_constants.hpp 与布局表生成物之间不一致");

std::size_t AttachRoomMethods(lua_State* state) noexcept {
    // 批次 051：`Room:PlayMusic()` 走引擎方法数据行（`this` = **当前房间**，
    // 所以 `receipt` 用 `Room`——它不从 Lua 栈上取接收者）。
    // 批次 289：位置类表由本批新增 —— 第 5/6 个实参就是字段行表（原来是 `nullptr, 0`）。
    // 批次 290：`GetRoomShape` 追加进同一张表（接收者换成两跳链末端的 `RoomConfigData`）。
    // 批次 291：`GetBossID` / `IsFirstVisit`（`Room` 接收者）与
    //   `IsAmbushDone` / `HasWaterPits`（新接收者 `RoomDescriptor`）四条追加进同一张表。
    return AttachApi700Methods(state,"Room") + AttachApi600Methods(state,"Room") + AttachApi300Methods(state,"Room") + AttachApi200Methods(state,"Room") + AttachApi100Methods(state,"Room") + AttachRPlusMethods(state,"Room") + AttachOwnerMethods(state, "Room", kRoomHandlers, RowCount(kRoomHandlers), kRoomFieldApis,
                              RowCount(kRoomFieldApis), kRoomEngineRows,
                              RowCount(kRoomEngineRows));
}

// `GridEntity` 族的方法表（元表在 `lua_runtime.cpp` 里建）。
//: 批次 304（2026-10-03）：`GridEntity` 的**两条虚函数**（走"按 vtable 槽号调用"，批 303 立的约定）。
//:
//: 两条都是**虚函数**：PC 的绑定本体是 `mov eax,[ecx]; jmp [eax+偏移]`
//: （PC 镜像 `0x8604E0` 起那张跳板表里，`GridEntity:Destroy` 那一档 = `0x86050c` 的 `jmp [eax+0x18]`），
//: 调哪一个实现**取决于接收者的动态类型**（`GridEntity_Door`/`_Rock`/`_Statue`/`_TNT`/`_Web`
//: 都有自己的 `Destroy`）⇒ 直调基类会**跳过子类行为**（真机上"石头炸掉不喷掉落物"就是这么来的）。
//:
//: ★ 槽号 **2 / 6** 从 `_ZTVGridEntity`（`0xA37880`）读出来：槽 i 在
//:   `对象首字 + i*8`（对象首字 = `_ZTV + 0x10` = `kGridEntityVtableOffset` = `0xA37890`）。
//:   ★★ PC 侧是第 5 / 1 条（比 Switch 小 1，两边差一个析构槽）⇒ **不许照抄 PC 的**。
//:   取证与"怎么读"见 `runtime_constants.hpp` 的批次 303/304 段。
//: ★ `Destroy(boolean Immediate)` 的实参**可以省略**（语料里 `Destroy()` 与 `Destroy(true)` 都有）
//:   ⇒ 形状用 `BoolOpt1`（`bool(this, bool 可选)`，批次 207 为 `Entity:IsActiveEnemy` 立的）。
//: ★ 接收者是新开的 `FieldReceipt::GridEntity`（栈上那个句柄），存活判据与手写路径同一份。
constexpr EngineMethodRow kGridEntityEngineRows[] = {
    {0x0E0100D5, MakeEngineVtableRowOffset(kGridEntityVtableDestroySlot), 0,
     FieldReceipt::GridEntity, EngineCallShape::BoolOpt1, 1, 0xFF},
    {0x0E0100D6, MakeEngineVtableRowOffset(kGridEntityVtablePostInitSlot), 0,
     FieldReceipt::GridEntity, EngineCallShape::Void0, 0, 0xFF},
    //: 批次 321（2026-10-03）：`GridEntity:Update()`（1 处）—— **槽 3**。
    //: ★★★ 自证：基类 `_ZTVGridEntity` 的**槽 3 是 `__cxa_pure_virtual`**（纯虚），
    //:   而每一个派生类都在槽 3 放自己的 `Update` ⇒ 这是虚函数的定义，且不可能"落到基类"
    //:   （基类那份不可调用）。★ PC 侧同规律：跳板表 `0x860507` = `jmp [eax+0x8]` ⇒ 序号 2
    //:   ⇒ Switch 槽 3（PC 序号 = Switch 槽号 − 1）。取证见 `runtime_constants.hpp` 批次 321 段。
    {0x0E0100DC, MakeEngineVtableRowOffset(kGridEntityVtableUpdateSlot), 0,
     FieldReceipt::GridEntity, EngineCallShape::Void0, 0, 0xFF},
};
static_assert(RowCount(kGridEntityEngineRows) == 3,
              "行数与 id 段（0x00D5 + 0x00D6 + 0x00DC）要一起改");

//: 批次 308（2026-10-03）：`GridEntity` 的**字段数据行**表（本家族的第一张）。
//:
//: `SetType(eGridEntityType)`：PC 的绑定本体（`0x6DAD50`）只有两条指令 ——
//:   `mov eax,[ebp+0x8]`（实参）+ `mov [ecx+0x4],eax`（写进类型那一格）+ `ret 0x4`
//:   ⇒ **不调任何引擎函数**，就是一次字段写。
//: Switch 侧的"类型"格是 `GridEntity + kGridEntityTypeOffset`（`+0x08`，**既有常量**）：
//:   * `Room::CreateGridEntity(eGridEntityType, unsigned) @ 0x37FC50`：`0x380084 str w20, [x21, #0x8]`
//:     —— 类型实参直接落在 `+0x08`；
//:   * `GridEntity::IsRock() @ 0x37FBEC` 读 `+0x08` 后按岩石族的位集判类，与文档枚举逐项吻合。
//:   ★ PC 的 `+0x4` 与 Switch 的 `+0x08` 差 4 字节 = **指针宽度差**（Switch 对象首字是 8 字节 vptr）
//:     —— 与 `Room` 网格实体表（PC `+0x24` / Switch `+0x30`）同一类；**数值不许平移**。
//: ★ 与 `GridEntity:GetType()` **读的是同一格** ⇒ "写进去再读回来"是真的往返判据。
//: ★ 条目的 id 取 Isaac 域下一个空号 `0x00D7`（`0x00D5`/`0x00D6` 被批 304 的两条虚函数占了）。
constexpr FieldApiRow kGridEntityFieldApis[] = {
    {0x0E0100D7, kGridEntityTypeOffset, 0, FieldKind::U32FromArg, FieldMissing::Zero,
     FieldReceipt::GridEntity, 0xFF},
};
static_assert(RowCount(kGridEntityFieldApis) == 1, "行数与 id 段（0x00D7）要一起改");

std::size_t AttachGridEntityMethods(lua_State* state) noexcept {
    //: 批次 304：`GridEntity` 从这一批起也有了**引擎方法数据行**（两条虚函数）。
    //: 批次 308：再加一张**字段数据行**表（`SetType`）—— 三张表都按 id 匹配，
    //: 不属于本 owner 的一处也挂不上。
    lua_newtable(state);static_cast<void>(AttachApi200Methods(state,"GridEntityPit"));lua_setfield(state,-2,"__pitMethods");
    lua_newtable(state);static_cast<void>(AttachApi700Methods(state,"GridEntityPoop"));static_cast<void>(AttachApi200Methods(state,"GridEntityPoop"));lua_setfield(state,-2,"__poopMethods");
    lua_newtable(state);static_cast<void>(AttachApi200Methods(state,"GridEntityPressurePlate"));lua_setfield(state,-2,"__plateMethods");
    lua_newtable(state);static_cast<void>(AttachApi600Methods(state,"GridEntityRock"));static_cast<void>(AttachApi100Methods(state,"GridEntityRock"));lua_setfield(state,-2,"__rockMethods");
    lua_newtable(state);static_cast<void>(AttachApi600Methods(state,"GridEntityDoor"));static_cast<void>(AttachApi100Methods(state,"GridEntityDoor"));static_cast<void>(AttachApi200Methods(state,"GridEntityDoor"));lua_setfield(state,-2,"__doorMethods");
    return AttachApi700Methods(state,"GridEntity") + AttachApi100Methods(state,"GridEntity") + AttachRPlusMethods(state,"GridEntity") + AttachOwnerMethods(state, "GridEntity", kGridEntityHandlers,
                              RowCount(kGridEntityHandlers),
                              kGridEntityFieldApis, RowCount(kGridEntityFieldApis),
                              kGridEntityEngineRows, RowCount(kGridEntityEngineRows));
}

// 批次 284：`GridEntityDoor` 自己的方法表（`Open`/`Close`/`IsTargetRoomArcade`）。
// ★ 门的方法**与 `GridEntity` 分开挂**：owner 不同（`AttachOwnerMethods` 按 owner 匹配），
//   门那张表挂在门元表的 `__methods` 上，`GridEntityDoorIndex` 答完字段后先查它、再回落
//   `GridEntity` 的方法表（字段 → 门自己 → 基类，与 `Sprite`/`Entity` 的回落链同形）。
std::size_t AttachGridEntityDoorMethods(lua_State* state) noexcept {
    return AttachApi600Methods(state,"GridEntityDoor") + AttachApi200Methods(state,"GridEntityDoor") + AttachApi100Methods(state,"GridEntityDoor") + AttachRPlusMethods(state,"GridEntityDoor") + AttachOwnerMethods(state, "GridEntityDoor", kGridEntityDoorHandlers,
                              RowCount(kGridEntityDoorHandlers));
}

std::size_t AttachItemPoolMethods(lua_State* state) noexcept {
    // 批次 254：`ItemPool` 从这一批起也有**引擎方法数据行**（`RemoveCollectible`，
    // 接收者 `FieldReceipt::ItemPool`）。`AttachOwnerMethods` 按 id 匹配，所以把整张表传进来，
    // 不属于 `ItemPool` owner 的行自然一处也挂不上 —— 与 `Room`/`Game` 同形。
    return AttachApi700Methods(state,"ItemPool") + AttachApi100Methods(state,"ItemPool") + AttachOwnerMethods(state, "ItemPool", kItemPoolHandlers, RowCount(kItemPoolHandlers),
                              nullptr, 0, kItemPoolEngineRows, RowCount(kItemPoolEngineRows));
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
        return PushNativeFallbackInteger(state, kFbItemPoolGetPillEffect, 0);
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
    std::uintptr_t installedFallback = 0;
#if defined(__SWITCH__)
    installedFallback = EntryRelayFallbackEntry(HookId::ItemPoolGetPillEffect);
#endif
    if (!EngineEntryOrRelayMatches<IsEngineMemoryReadable>(base+kItemPoolGetPillEffectOffset,
            kItemPoolGetPillEffectExpectedBytes.data(), kItemPoolGetPillEffectExpectedBytes.size(),
            installedFallback)) {
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
        return PushNativeFallbackInteger(state, kFbItemPoolGetPoolForRoom, 0);
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
        // 批次 250：给**空句柄**（与 `GetCurrentRoomDesc` 同口径）。
        RecordNativeStateFallback(kFbLevelGetLastRoomDesc);
        return PushRoomDescriptor(state, 0);
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

// ============================================================================
// 坐标变换（批次 195，2026-09-29）
// ============================================================================
//
// `Isaac.WorldToScreen` / `Isaac.WorldToRenderPosition` / `Isaac.ScreenToWorld` 与
// `Room:WorldToScreenPosition` **共用这一份算术**。三条的 PC 语义与引擎入口逐条取证见
// `analysis/api-restore-transforms/spec.json`；这里只留"为什么是这几步"的要点：
//
//   * 世界 → 渲染平面：**调引擎** `GetRenderPosition(pos, true)`。`true` 不能省 ——
//     引擎在这一步做**量化**（`floor(v*K+0.5)/K`，K = POINTSCALE × DPP），
//     PC 的 `WorldToScreen`/`WorldToRenderPosition` 两条**都**量化，差别只在后面加不加偏移。
//   * 渲染平面 → 屏幕：再加 `Room[0x1938]`（相机滚动）与 `Game[0x24F9B0]`（屏幕震动）。
//     这两条与 `Room::WorldToScreenPosition @ 0x489354` 的两条 `Vector2::operator+` 逐项对应。
//   * 屏幕 → 世界：**引擎里没有入口**（PC 自己也是就地算）⇒ 照 PC 的算式算，
//     `WIDTH`/`HEIGHT`/`POINTSCALE` **运行期从 GOT 槽读**（`ResizeWindow` 会改它们；
//     写死 480/270/2.0 就是"掌机上算错"）。
namespace {

//: 读一个"指向 float 的引擎全局"的 GOT 槽：`槽 → 指针 → 那个 float`（两步）。
//: 与 `mod_menu_native.cpp` 的 `readFloatGlobal` 逐字同形（那里用它算菜单纸的位置）。
//: 读不到 ⇒ `false`，**绝不用一个猜测值顶替**。
//: ★ 批次 207（2026-09-29）：**提出匿名命名空间**改成 `isaac::runtime` 里的公开助手 ——
//:   `isaac_api.cpp` 的 `Isaac.GetScreenWidth/GetScreenHeight` 读的是同两个槽
//:   （`kIsaacScreenWidthSlotOffset`/`kIsaacScreenHeightSlotOffset`），两处各留一份拷贝会漂移。
//:   声明在 `remaining_api.hpp`，实现紧跟在下面这个匿名命名空间**之后**。

} // namespace

bool ReadFloatGlobalSlot(std::uintptr_t slotOffset, float* out) noexcept {
    if (out == nullptr) {
        return false;
    }
    const std::uintptr_t base = EngineModuleBase();
    if (base == 0 || base > UINTPTR_MAX - slotOffset) {
        return false;
    }
    std::uintptr_t target = 0;
    if (!isaac::runtime::engine_memory::ReadAt(base + slotOffset, &target,
                                               &IsEngineMemoryReadable) ||
        target == 0) {
        return false;
    }
    float value = 0.0F;
    if (!isaac::runtime::engine_memory::ReadAt(target, &value, &IsEngineMemoryReadable)) {
        return false;
    }
    *out = value;
    return true;
}

bool TransformWorldPosition(const float* world, float* output,
                            WorldTransformTarget target) noexcept {
    if (world == nullptr || output == nullptr) {
        return false;
    }
    float rendered[2] = {world[0], world[1]};
    bool ok = false;
#if !defined(__SWITCH__)
    // 宿主：没有引擎映像，用注入的实现（与 `HasCollectible` 的宿主钩子同一形态）。
    if (LuaRuntime::GetRenderPositionHostFunction() != nullptr) {
        LuaRuntime::GetRenderPositionHostFunction()(world, rendered, true);
        ok = true;
    }
#else
    ok = CallVectorEngineMethod(LuaRuntime::GetRenderPositionThunk(),
                                kGetRenderPositionStubExpectedBytes, world, rendered, true);
#endif
    if (!ok) {
        return false;
    }
    if (target == WorldTransformTarget::kRenderPosition) {
        // `Isaac.WorldToRenderPosition`：引擎那一步就是全部结果，**不加**任何相机偏移。
        output[0] = rendered[0];
        output[1] = rendered[1];
        return true;
    }
    // `Isaac.WorldToScreen` / `Room:WorldToScreenPosition`：再加房间与 Game 各自那一份调整量。
    void* room = nullptr;
    if (ReadCurrentGameRoom(GameOwnerSlot(), &room) != GameRoomObservation::Success ||
        room == nullptr) {
        return false;
    }
    const std::uintptr_t roomAddress = isaac::runtime::engine_memory::AddressOf(room);
    const std::uintptr_t roomScroll = roomAddress + layout::kRoomRenderScrollOffsetOffset;
    std::uintptr_t game = 0;
    if (!ResolveCurrentLevel(&game) || game == 0) {
        return false;
    }
    const std::uintptr_t gameAdjust = game + kGameToScreenAdjustOffset;
    if (!IsEngineMemoryReadable(roomScroll, sizeof(float) * 2) ||
        !IsEngineMemoryReadable(gameAdjust, sizeof(float) * 2)) {
        return false;
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
    output[0] = rendered[0] + roomX + gameX;
    output[1] = rendered[1] + roomY + gameY;
    return true;
}

bool TransformScreenToWorldPosition(const float* screen, float* output) noexcept {
    if (screen == nullptr || output == nullptr) {
        return false;
    }
    // `g_Game` 为空（主菜单 / 还没进局）⇒ PC **原样返回**（`isaac-ng.exe @ 0x80c760` 的空指针保护）。
    // 这里同样返回 `false` 让调用方给原值 —— 报错会让模组在标题界面直接断掉。
    void* room = nullptr;
    if (ReadCurrentGameRoom(GameOwnerSlot(), &room) != GameRoomObservation::Success ||
        room == nullptr) {
        return false;
    }
    float width = 0.0F;
    float height = 0.0F;
    float pointScale = 0.0F;
    if (!ReadFloatGlobalSlot(kIsaacScreenWidthSlotOffset, &width) ||
        !ReadFloatGlobalSlot(kIsaacScreenHeightSlotOffset, &height) ||
        !ReadFloatGlobalSlot(kIsaacPointScaleSlotOffset, &pointScale)) {
        return false;
    }
    // `POINTSCALE == 0` ⇒ 除零（引擎还没 `ResizeWindow` 时是可能的）⇒ 按"算不出来"处理。
    if (!(pointScale > 0.0F) || !(width > 0.0F) || !(height > 0.0F)) {
        return false;
    }
    const std::uintptr_t roomAddress = isaac::runtime::engine_memory::AddressOf(room);
    const std::uintptr_t roomScroll = roomAddress + layout::kRoomRenderScrollOffsetOffset;
    if (!IsEngineMemoryReadable(roomScroll, sizeof(float) * 2)) {
        return false;
    }
    float roomX = 0.0F;
    float roomY = 0.0F;
    static_cast<void>(isaac::runtime::engine_memory::LoadVerifiedAt(roomScroll, 0, &roomX));
    static_cast<void>(isaac::runtime::engine_memory::LoadVerifiedAt(roomScroll, 1, &roomY));
    // PC 的四步算式（**减 ScreenShakeOffset 这一项在 PC 上本来就没有**，别"顺手补上"）：
    //   wx = (p.x / POINTSCALE - roomScroll.x - (WIDTH  - 338) * 0.5) / 0.65 + 60
    //   wy = (p.y / POINTSCALE - roomScroll.y - (HEIGHT - 182) * 0.5) / 0.65 + 140
    output[0] = ((screen[0] / pointScale) - roomX -
                 (width - kRenderPlaneRoomWidth) * 0.5F) /
                    kWorldToRenderScale +
                kRoomWorldOriginX;
    output[1] = ((screen[1] / pointScale) - roomY -
                 (height - kRenderPlaneRoomHeight) * 0.5F) /
                    kWorldToRenderScale +
                kRoomWorldOriginY;
    return true;
}


} // namespace isaac::runtime
