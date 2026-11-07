#pragma once

#include <cstddef>
#include <cstdint>

extern "C" {
#include <lua.h>
}

// Migration container for the Lua API owners that have not been split into
// their own translation unit yet: Level, Room and ItemPool. Each owner already
// owns its `descriptor id -> handler` table here and registers through the
// shared `AttachOwnerMethods` loop, so a domain can move to its own file (and
// grow past three methods) without touching the registration mechanics.
//
// The file must stay a container: as soon as one owner reaches three methods or
// 200 lines it moves to `<owner>_api.cpp`, per the design's size rules.
// MusicManager, RNG and Input already moved that way.
namespace isaac::runtime {

// 固定PC全局入口与Room方法共用原生随机位置调用，margin为0。
int IsaacGetRandomPosition(lua_State* state);

// PC Isaac.CountEnemies/CountBosses 和 Room:GetAlive*Count 使用同一对原生计数。
// 受保护读取两个 int32，按原生32位回绕相加后夹到非负；无有效房间时返回0。
[[nodiscard]] std::int32_t ReadRoomAliveCount(std::uintptr_t room,
                                            std::uintptr_t pairOffset) noexcept;

[[nodiscard]] std::size_t AttachLevelMethods(lua_State* state) noexcept;
// `Level` 元表的 `__index`。必须是个函数（PC 的类元表 `__index` 就是函数）
// —— minimapi 的 `scripts/minimapapi/apioverride.lua` 会把 `getmetatable(Level).__class.__index`
// 取出来当函数调用（`oldIndex(self, k)`，第 25 行）；把它设成"元表自己"那张表，
// 真机就报 `attempt to call a table value (upvalue 'oldIndex')`。
// 语义与"`__index` 是一张表"完全等价（Lua 对表 `__index` 做的就是 `rawget`），只是变成可调用。
// 由 `lua_runtime.cpp` 建 `kLevelMetatable` 时接线（上值 1 = 类元表自己，方法就落在它身上）。
int LevelIndex(lua_State* state);
[[nodiscard]] std::size_t AttachRoomMethods(lua_State* state) noexcept;
// `GridEntity` 族：`Room:GetGridEntity()` 的返回值。
[[nodiscard]] std::size_t AttachGridEntityMethods(lua_State* state) noexcept;
// `GridEntityDoor` 自己的方法表（`Open` / `Close` / `IsTargetRoomArcade`）。
// 挂在门元表的 `__methods` 上，由 `GridEntityDoorIndex` 在答完字段之后先查它。
[[nodiscard]] std::size_t AttachGridEntityDoorMethods(lua_State* state) noexcept;
// `GridEntity` 基类的 `__index`（2026-09-21）：先答**字段**（`Position`/`VarData`/`Desc`），
// 再落到方法表（元表的 `__methods`）。门的 `__index` 答不上来时也转调它，所以要在建元表处可见。
int GridEntityIndex(lua_State* state);
// `Room:GetDoor(slot)` 的返回值是 `GridEntity_Door`（同时是 `GridEntity`）：
// 它的元表 `__index` 要先按门的字段答、答不上再落到 `GridEntity` 的方法表，所以实现要在
// `lua_runtime.cpp` 建元表时可见。
int GridEntityDoorIndex(lua_State* state);
// 地基二期（2026-09-15）：`RoomDescriptor` 的字段访问与列表的 `Size`/`Get`。
// 两者的 `__index` 都是函数（同时服务字段与方法），由 `lua_runtime.cpp` 注册元表时接线。
// GetPtrHash共享描述符来源/可读性校验；无效或非本族对象返回0。
[[nodiscard]] std::uintptr_t ResolveRoomDescriptorArgument(lua_State* state, int index) noexcept;
int RoomDescriptorIndex(lua_State* state);
int RoomDescriptorNewIndex(lua_State* state);
int RoomDescriptorListIndex(lua_State* state);
// `RoomDescriptorList` 的 `__len` —— 让 `#rooms` 成立。
// 起因（真机读数 = `dist/gdb-report-20261004-183801.txt`）：minimapi 的
// `scripts/minimapapi/main.lua:840`（同形 `:680`）报
// `attempt to get length of a IsaacRuntime.RoomDescriptorList value (local 'rooms')` ——
// 那几行是 `for i = 0, #rooms - 1 do` 与 `MinimapAPI.CheckedRoomCount = #rooms`
// （`rooms = level:GetRooms()`）。PC 的 `RoomDescriptorList` 是列表、支持 `#`。
// 语义与它已有的 `Size` 同一个来源（`DescriptorCount`，每次现读、不缓存）。
int RoomDescriptorListLen(lua_State* state);
[[nodiscard]] std::size_t AttachRoomDescriptorListMethods(lua_State* state) noexcept;
// `RoomDescriptor.Data.Spawns` 的两个视图 ——
// `RoomConfigSpawn`（`Data.Spawns:Get(i)` 的返回值）与 `RoomConfigEntry`（`spawn:PickEntry(r)`
// 的返回值）。两者的 `__index` 都是函数（属性 + 方法表），由 `lua_runtime.cpp` 注册元表时接线；
// 方法表由 `Attach*Methods` 挂（`PickEntry` 走 `AttachOwnerMethods` 的手写绑定表那一档）。
#if !defined(__SWITCH__)
// 宿主注入：`RoomConfigSpawn:PickEntry` 在宿主上必然降级（没有引擎可调 —— 而且绝不能
// 让入口字核对通过，否则 `AsFunction` 会把假模块块里的字节当函数跳进去）。
// 但 `RoomConfigEntry` 视图的属性（尤其 `Variant`/`SubType` 的 i16 符号扩展那条决定）
// 只能靠"真的拿到一个 Entry 句柄"才验得到 ⇒ 给测试一个注入点。
// 与 `isaac_api.hpp` 里那几个 `Set*HostImplementation` 同一口径：只在宿主构建里存在，
// 设备构建里这个声明与实现都不参与编译。
using RoomConfigSpawnPickEntryHostImplementation = const void* (*)(std::uintptr_t spawn, float r);
void SetRoomConfigSpawnPickEntryHostImplementation(
    RoomConfigSpawnPickEntryHostImplementation function) noexcept;
#endif
int RoomConfigSpawnIndex(lua_State* state);
int RoomConfigEntryIndex(lua_State* state);
[[nodiscard]] std::size_t AttachRoomConfigSpawnMethods(lua_State* state) noexcept;
[[nodiscard]] std::size_t AttachRoomConfigEntryMethods(lua_State* state) noexcept;
[[nodiscard]] std::size_t AttachItemPoolMethods(lua_State* state) noexcept;

// --- （2026-10-01，语料 API 恢复的 `glue_compose` 桶）：两条由 Room 原语拼出来的
//     `Isaac` 全局表接口 ---------------------------------------------------------------
//
// 实现在 `remaining_api.cpp`（格坐标换算、网格实体表读取、`Room::SpawnGridEntity` 的入口
// 都住在那一个 TU 里），但 owner 是 `Isaac` ⇒ 绑定行挂在 `isaac_api.cpp` 的 `kIsaacHandlers`。
//
//   * `Isaac.GetFreeNearPosition(pos, step)` —— PC 的绑定函数直接调
//     `Room::FindFreePickupSpawnPosition(pos, step, false, false)`（取证见实现处）。
//   * `Isaac.GridSpawn(type, variant, position, forced)` —— 世界坐标 → 格下标 → 覆盖判定 →
//     `RandomU32()` 取种子 → `Room::SpawnGridEntity(…)` → 返回那一格的 `GridEntity`。
int IsaacGetFreeNearPosition(lua_State* state);
int IsaacGridSpawn(lua_State* state);

// --- 坐标变换------------------------------------------------
//
// 三条 API 共用同一段算术，口径逐条来自 PC 的处理函数与引擎自己的
// `Room::WorldToScreenPosition @ 0x489354`（证据规格 `analysis/api-restore-transforms/spec.json`）：
//
//   * `kWorldToRenderPosition`（`Isaac.WorldToRenderPosition`）：`GetRenderPosition(pos, true)`
//     —— 引擎的量化已经做在里面，**不加**任何相机偏移。
//   * `kWorldToScreen`（`Isaac.WorldToScreen` / `Room:WorldToScreenPosition`）：同上，
//     **再**加 `Room[0x1938]` 与 `Game[0x24F9B0]` 两处偏移。
//   * `Isaac.ScreenToWorld`：引擎里**没有**反向入口（PC 自己也是就地算）⇒ 照 PC 的算式自己算，
//     输入是**窗口像素**、`g_Game==null` 时原样返回、**不**减 `ScreenShakeOffset`。
//
// 三条都放在这个 TU 里：`Room:WorldToScreenPosition` 的实现已经在这里，而"同一段算术只有一份"
// 是本项目对坐标换算的硬要求（两处各写一份必然漂）。
enum class WorldTransformTarget : std::uint32_t {
    // `GetRenderPosition(pos, true)`，不含相机滚动与屏幕震动。
    kRenderPosition = 0,
    // 上面那一步再加 `Room[0x1938] + Game[0x24F9B0]`。
    kScreen = 1,
};

// 世界坐标 →（渲染平面 | 屏幕）坐标。`false` = 这次没算出来（入口不可用 / 读不到原生状态），
// 调用方必须据此报错，不许编一个 (0,0) 把东西画到左上角。
[[nodiscard]] bool TransformWorldPosition(const float* world, float* output,
                                          WorldTransformTarget target) noexcept;

// 窗口像素 → 世界坐标（照 PC 的算式，WIDTH/HEIGHT/POINTSCALE 运行期从引擎全局读）。
// `false` = 引擎还没进局（`g_Game` 为空）或读不到换算常量 ⇒ 调用方原样返回输入
// （这正是 PC 在 `g_Game==null` 时的行为，不是错误）。
[[nodiscard]] bool TransformScreenToWorldPosition(const float* screen, float* output) noexcept;

// 读一个"指向 float 的引擎全局"的 GOT 槽（`槽 → 指针 → float` 两步）。读不到 ⇒ `false`。
//
// 从 `remaining_api.cpp` 的匿名命名空间提出来变成公开助手：
// `Isaac.GetScreenWidth/GetScreenHeight` 用的是同两个槽
// （`kIsaacScreenWidthSlotOffset = 0xAAC650` / `kIsaacScreenHeightSlotOffset = 0xAAC658`，
// 就是引擎的 `IsaacRepentance::WIDTH` / `HEIGHT`），两处各写一份必然漂。
[[nodiscard]] bool ReadFloatGlobalSlot(std::uintptr_t slotOffset, float* out) noexcept;

// --- `Level:GetCurses()` 的探针读数（2026-09-12，动作三）----------------------------
//
// EID 的 `hasCurseBlind()`（`eid_api.lua:597`）是"隐瞒分支"四条成因之一，它的全部输入
// 就是 `Level:GetCurses()`。反汇编已证明地址链没错、但语义只做了三步里的第一步
// （`curses | permanent` 再 `& banned` 都没做），所以真机要同时看到：
//   * `raw`       —— `Level+0xC` 的原始位（现在交给 Mod 的那个值）；
//   * `permanent` —— `Game::GetSpecialSeedPermanentCurses()` 的返回值；
//   * `banned`    —— `Game::GetSpecialSeedBannedCurses()` 的返回值；
//   * `flags`     —— bit0 原始位读到了、bit1 permanent 访问器被调到（守卫通过）、
//                     bit2 banned 访问器被调到。
struct GameCursesProbe {
    std::uint32_t raw{0};
    std::uint32_t permanent{0};
    std::uint32_t banned{0};
    std::uint32_t flags{0};
    // `Level:GetCurses()` 被调用过的次数（0 = Mod 压根没走这条判定）。
    std::uint32_t reads{0};
};

[[nodiscard]] GameCursesProbe GameCursesProbeSnapshot() noexcept;

// --- `Level`/`Game` 句柄的 `__newindex`-----------------------
//
// **为什么必须有**：PC 的 `Level`/`Game` 是引擎对象，模组可以直接给字段赋值；
// 我们这边是 userdata，元表没有 `__newindex` 时**赋值直接抛 Lua 错误**。
// 真机代价（2026-09-19）：GoodTrip 的传送路径 `scripts/trip.lua:123-124` 第一句就是
// `floor.level.EnterDoor = -1` / `LeaveDoor = -1` ⇒ 整条传送在这一句断掉，
// 真机原文 `trip.lua:123: attempt to index a IsaacRuntime.Level value (field 'level')`，
// 而屏幕上表现为"按了方向键、光标能动，但怎么都不传送"（**看起来像功能缺失**）。
//
// **口径**：**有证据的字段真写，其余接受并忽略** —— 形状先对齐 PC（我们不许比 PC 严），
// 语义留给以后：`EnterDoor`/`LeaveDoor` 的偏移在布局表里**没有证据**，而"猜一个偏移写进引擎"
// 比"不写"危险得多（会踩坏引擎状态）。为了不把拼错的字段名完全吞掉，被忽略的写入会记一个
// 计数与最后那个字段名，调试桩读得到（见 `g_IsaacIgnoredFieldWriteCount` /
// `g_IsaacLastIgnoredFieldName`）。
//
// 2026-10-26（BUG-014）：`Game.TimeCounter` 从本条起是真写（PC 契约
//   `Game.md:634` 非 const；作者 TimeMachine 每帧补偿依赖它）。真写成功记在
//   `g_IsaacGameTimeCounterWriteCount` / `g_IsaacLastGameTimeCounterWrite`，
//   **不再**进忽略计数 —— "写了"与"没写"必须能分开读。
//
// **已知偏离**：`EnterDoor`/`LeaveDoor` 置 -1（PC 上表示"到站不走门的开合动画"）在我们这里不生效，
// 所以传送到达时的门动画可能按引擎默认走。取证到偏移后应改成真写。
// 同类未做：`Game.Challenge`（PC 非 const，我们仍是忽略写）。
[[nodiscard]] int IgnoredObjectFieldWrite(lua_State* state);

// 引擎自己的 `RandomU32()`（无参、返回 `unsigned`）—— 实现仍在
// `remaining_api.cpp`（只此一份），这里只是把声明提出来给跨 TU 的调用方用：
// `Isaac:Spawn` 需要"非 0 随机种子"（PC 契约 `Isaac.md:621` 明文警告种子 0 会让游戏崩），
// 而那条处理器住在 `isaac_api.cpp`。取不到引擎时返回 0（调用方自行兜底成 1）。
[[nodiscard]] std::uint32_t EngineRandomU32() noexcept;

// 显式区分绑定失败与合法随机值0；不更改既有调用方的回退口径。
[[nodiscard]] bool TryEngineRandomU32(std::uint32_t* value) noexcept;
#if !defined(__SWITCH__)
void SetRandomU32HostImplementation(std::uint32_t (*function)()) noexcept;
#endif

// 让"当前房间解析"的派发窗口内缓存立即失效。
// 换房类入口（`Game:ChangeRoom` / `Game:StartRoomTransition` / `Isaac.ExecuteCommand`）
// 各调一次 —— 保证同一派发窗口里后续的查询也会重新解析（拿到新房间）。
void InvalidateCurrentRoomCache() noexcept;

} // namespace isaac::runtime
