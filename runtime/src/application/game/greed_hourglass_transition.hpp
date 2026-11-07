#pragma once

#include "infrastructure/memory/engine_field_access.hpp"

namespace isaac::runtime {
using StageTransitionFn = void (*)(void*, bool, int, void*);
using RoomTransitionFn = void (*)(void*, int, int, int, void*, int);

enum class HourglassTransitionResult {
    Forwarded, Rerouted, StateUnreadable, RoomUnavailable, OriginalUnavailable
};

// 要读的引擎字段偏移。生产侧传 `runtime_constants.hpp` 的具名常量；宿主测试可以换成
// 自己那块伪造内存的偏移 —— 判定逻辑本身不写死任何偏移。
struct HourglassFieldOffsets {
    std::uintptr_t stage;        // `Level.Stage`（`Game + 0x00`）
    std::uintptr_t difficulty;   // `Game.Difficulty`
    std::uintptr_t stateFlags;   // `Game` 的状态标志位数组基址（每字节 8 个标志）
    std::uintptr_t playerBegin;  // `vector<Entity_Player*>::begin`
    std::uintptr_t playerEnd;
};

// `StageTransition::eAnimation` 的 6。PC 契约 `Game.md` 的 `StartStageTransition` 一节逐字为
// "6: Home Glowing Hourglass. Progress towards Home, regardless of the current floor."
// ⇒ 这是"发光沙漏去 Home"，与 `RoomTransitionAnim` 的 6（DEAD_CAT）不是同一个枚举。
inline constexpr int kHomeHourglassStageAnimation = 6;
// `RoomTransitionAnim::TELEPORT = 3`（枚举表 `RoomTransitionAnim.md`）。
inline constexpr int kErrorRoomTransitionAnimation = 3;
// 引擎自己的错误房传送参数：`Entity_Player::UseCard` 里 "空白卡 + 下一层可用" 的分支就是
// `StartRoomTransition(-2, -1, 3, player, -1)`（反汇编 `0x2EA1C8-0x2EA1E4`）。
// `-2` 这个房间索引的语义（是否等价于 I AM ERROR）本轮没有独立取证，
// 只确认"引擎自己在用这一组参数"；真机表现是唯一判据（见交接文档）。
inline constexpr int kErrorRoomIndex = -2;
inline constexpr int kNativeRoomDimension = -1;
// `GameStateFlag` 4：Repo 起语义是 "left from starting room"（是否离开过起始房间）。
// 引擎自己那条 Home 分流正是拿它当条件之一（`ldrb [Game+0x26FA50]; tbnz #4` 跳走）。
inline constexpr unsigned kLeftStartingRoomStateFlag = 4;

// 读一个 `GameStateFlag`（位数组，每字节 8 个标志）。
[[nodiscard]] inline bool ReadHourglassStateFlag(std::uintptr_t game, std::uintptr_t flagsOffset,
                                                unsigned flag,
                                                engine_memory::ReadableCheck readable,
                                                bool* value) noexcept {
    if (value == nullptr) {
        return false;
    }
    std::uint8_t byte = 0;
    if (!engine_memory::ReadField(game, flagsOffset + flag / 8u, &byte, readable)) {
        return false;
    }
    *value = ((byte >> (flag % 8u)) & 1u) != 0;
    return true;
}

// 取第 0 个玩家（沙漏这条路径引擎自己传的是 `nullptr`，但换房需要真实玩家）。
[[nodiscard]] inline bool ReadHourglassFirstPlayer(std::uintptr_t game,
                                                  const HourglassFieldOffsets& offsets,
                                                  engine_memory::ReadableCheck readable,
                                                  void** player) noexcept {
    if (player == nullptr) {
        return false;
    }
    *player = nullptr;
    std::uintptr_t begin = 0;
    std::uintptr_t end = 0;
    if (!engine_memory::ReadField(game, offsets.playerBegin, &begin, readable) ||
        !engine_memory::ReadField(game, offsets.playerEnd, &end, readable)) {
        return false;
    }
    if (begin == 0 || end <= begin || (end - begin) < sizeof(std::uintptr_t)) {
        return false;
    }
    std::uintptr_t first = 0;
    if (!engine_memory::ReadAt(begin, &first, readable) || first == 0) {
        return false;
    }
    *player = engine_memory::AsObject(first);
    return true;
}

// Repentance+ 公布的贪婪规则移植：只拦截"初始沙漏选中的首层 Home 过渡"。
//
// 判据全部来自固定 NRO 的反汇编（`dist/auri-greed-fix-20261026/`），逐条可复核：
//   ① `Game::StartRoomTransition` 在 `Animation == 12(GLOWING_HOURGLASS)` 且 `Level.Stage == 1`
//      且 `GameStateFlag 4 == 0` 时，固定转
//      `StartStageTransition(false, 6, nullptr)`（`0x353D08-0x353D40`）。
//   ② 全库 8 个 `StartStageTransition` 调用点里，**只有** `0x353D40` 是 `(false, 6, nullptr)`；
//      其余是 `(true,0)`、`(true,5)`、`(false,0)`、`(false,2)`、`(false,4)`、`(false,6, 非空 player)`。
//      ⇒ `player != nullptr` 一定不是这条路径（模组经 Lua 调用必须带 Player，PC 契约明说
//      不带会崩）⇒ 原样转发，不替作者决定"你要 Home 还是 ERROR 房"。
//   ③ 命中后改用引擎自己的错误房传送参数（见 `kErrorRoomIndex` 的注释）。
//
// 失败一律**明确返回原因**，不静默吞掉、也不回退到已知非法的 Home 路径。
[[nodiscard]] inline HourglassTransitionResult DispatchGreedHourglassTransition(
    void* game, bool goingUp, int animation, void* player, StageTransitionFn original,
    RoomTransitionFn roomTransition, const HourglassFieldOffsets& offsets,
    engine_memory::ReadableCheck readable) noexcept {
    if (!original) {
        return HourglassTransitionResult::OriginalUnavailable;
    }
    if (goingUp || animation != kHomeHourglassStageAnimation || player != nullptr) {
        original(game, goingUp, animation, player);
        return HourglassTransitionResult::Forwarded;
    }
    const auto address = engine_memory::AddressOf(game);
    std::uint32_t stage = 0;
    std::uint32_t difficulty = 0;
    bool leftStartingRoom = false;
    if (!engine_memory::ReadField(address, offsets.stage, &stage, readable) ||
        !engine_memory::ReadField(address, offsets.difficulty, &difficulty, readable) ||
        !ReadHourglassStateFlag(address, offsets.stateFlags, kLeftStartingRoomStateFlag, readable,
                                &leftStartingRoom)) {
        return HourglassTransitionResult::StateUnreadable;
    }
    // 贪婪（2）/ 贪婪更贪婪（3）；非首层或已离开起始房间都说明"这不是首层沙漏"。
    if (stage != 1 || (difficulty != 2 && difficulty != 3) || leftStartingRoom) {
        original(game, goingUp, animation, player);
        return HourglassTransitionResult::Forwarded;
    }
    if (!roomTransition) {
        return HourglassTransitionResult::RoomUnavailable;
    }
    void* target = nullptr;
    if (!ReadHourglassFirstPlayer(address, offsets, readable, &target) || target == nullptr) {
        return HourglassTransitionResult::StateUnreadable;
    }
    roomTransition(game, kErrorRoomIndex, -1, kErrorRoomTransitionAnimation, target,
                   kNativeRoomDimension);
    return HourglassTransitionResult::Rerouted;
}
} // namespace isaac::runtime
