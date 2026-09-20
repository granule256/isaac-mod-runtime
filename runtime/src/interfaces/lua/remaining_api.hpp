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

[[nodiscard]] std::size_t AttachLevelMethods(lua_State* state) noexcept;
[[nodiscard]] std::size_t AttachRoomMethods(lua_State* state) noexcept;
//: `GridEntity` 族（批次 12，2026-09-16）：`Room:GetGridEntity()` 的返回值。
[[nodiscard]] std::size_t AttachGridEntityMethods(lua_State* state) noexcept;
// `Room:GetDoor(slot)` 的返回值是 `GridEntity_Door`（同时是 `GridEntity`）：
// 它的元表 `__index` 要先按门的字段答、答不上再落到 `GridEntity` 的方法表，所以实现要在
// `lua_runtime.cpp` 建元表时可见。
int GridEntityDoorIndex(lua_State* state);
// 地基二期（2026-09-15）：`RoomDescriptor` 的字段访问与列表的 `Size`/`Get`。
// 两者的 `__index` 都是函数（同时服务字段与方法），由 `lua_runtime.cpp` 注册元表时接线。
int RoomDescriptorIndex(lua_State* state);
int RoomDescriptorListIndex(lua_State* state);
[[nodiscard]] std::size_t AttachRoomDescriptorListMethods(lua_State* state) noexcept;
[[nodiscard]] std::size_t AttachItemPoolMethods(lua_State* state) noexcept;

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

// --- `Level`/`Game` 句柄的 `__newindex`（批次 061，2026-09-19）-----------------------
//
// **为什么必须有**：PC 的 `Level`/`Game` 是引擎对象，模组可以直接给字段赋值；
// 我们这边是 userdata，元表没有 `__newindex` 时**赋值直接抛 Lua 错误**。
// 真机代价（2026-09-19）：GoodTrip 的传送路径 `scripts/trip.lua:123-124` 第一句就是
// `floor.level.EnterDoor = -1` / `LeaveDoor = -1` ⇒ 整条传送在这一句断掉，
// 真机原文 `trip.lua:123: attempt to index a IsaacRuntime.Level value (field 'level')`，
// 而屏幕上表现为"按了方向键、光标能动，但怎么都不传送"（**看起来像功能缺失**）。
//
// **口径**：**接受并忽略**字段写入 —— 形状先对齐 PC（我们不许比 PC 严），语义留给以后：
// `EnterDoor`/`LeaveDoor` 的偏移在布局表里**没有证据**，而"猜一个偏移写进引擎"比"不写"危险得多
// （会踩坏引擎状态）。为了不把拼错的字段名完全吞掉，被忽略的写入会记一个计数与最后那个字段名，
// 调试桩读得到（见 `g_IsaacIgnoredFieldWriteCount` / `g_IsaacLastIgnoredFieldName`）。
//
// **已知偏离**：`EnterDoor`/`LeaveDoor` 置 -1（PC 上表示"到站不走门的开合动画"）在我们这里不生效，
// 所以传送到达时的门动画可能按引擎默认走。取证到偏移后应改成真写。
[[nodiscard]] int IgnoredObjectFieldWrite(lua_State* state);

} // namespace isaac::runtime
