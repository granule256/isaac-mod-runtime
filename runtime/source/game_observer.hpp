#pragma once

#include <cstdint>

namespace IsaacRepentance {
struct Game;
struct Level;
}

enum class GameOwnerObservation : std::uint32_t {
    OwnerNull,
    OwnerUnreadable,
    GameNull,
    GameUnreadable,
    Success,
};

enum class GameIsPausedObservation : std::uint32_t {
    OwnerNull,
    OwnerUnreadable,
    GameNull,
    GameUnreadable,
    ThunkUnavailable,
    PausedFalse,
    PausedTrue,
};

enum class GameLevelStageObservation : std::uint32_t {
    OwnerNull,
    OwnerUnreadable,
    GameNull,
    GameUnreadable,
    Success,
};

enum class GameItemPoolObservation : std::uint32_t {
    OwnerNull,
    OwnerUnreadable,
    GameNull,
    GameUnreadable,
    ItemPoolUnreadable,
    Success,
};

enum class GameRoomObservation : std::uint32_t {
    OwnerNull,
    OwnerUnreadable,
    GameNull,
    GameUnreadable,
    RoomNull,
    RoomUnreadable,
    Success,
};

struct GameRoomKey {
    std::uint32_t roomIndex;
    std::uint32_t dimension;

    constexpr bool operator==(const GameRoomKey& other) const {
        return roomIndex == other.roomIndex && dimension == other.dimension;
    }
};

struct GameRoomDescriptorSnapshot {
    std::uint32_t candidateWord0c;
    std::uint32_t candidateWord50;

    constexpr bool operator==(const GameRoomDescriptorSnapshot& other) const {
        return candidateWord0c == other.candidateWord0c && candidateWord50 == other.candidateWord50;
    }
};

// 当前"在哪个房间、哪一层"的**语义身份** —— `MC_POST_NEW_ROOM` / `MC_POST_NEW_LEVEL`
// 这两个回调的判据就是它变没变。
//
// 为什么用字段而不是指针：指针会被复用（同一个地址先后待过两个不同的对象），拿指针当身份
// 会在极端情况下漏事件；而这四个字是**引擎自己**判"这是哪个房间、哪一层"的输入 ——
// `Level::GetCurrentRoomDesc` 用的就是 `+0x21558`/`+0x21560`（当前 descriptor 的索引 +
// 维度），`Level::SetStage` 写的是 `+0x00`/`+0x04`（关卡 + 关卡类型）。
// 四个字段的偏移与语义见 `runtime_constants.hpp` 的 `kLevelCurrentRoom*` / `kLevelStage*`。
struct GameLocationKey {
    std::uint32_t roomIndex;
    std::uint32_t roomDimension;
    std::uint32_t stage;
    std::uint32_t stageType;

    constexpr bool SameRoom(const GameLocationKey& other) const {
        return roomIndex == other.roomIndex && roomDimension == other.roomDimension;
    }
    constexpr bool SameLevel(const GameLocationKey& other) const {
        return stage == other.stage && stageType == other.stageType;
    }
};

// 从 `GameOwnerSlot()` 那条链（槽 → owner → `Game*`）读四个身份字。任一环不可读都返回
// 非 `Success`，调用方据此"这次不判变化"，而不是拿半截读数去比 —— 拿不可读的残留值当身份
// 会在每次读数失败时都判成"换了房间"，把回调派发成每帧一次。
GameRoomObservation ReadGameLocationKey(uintptr_t ownerSlot, GameLocationKey* key);

// 每实体渲染回调（`MC_POST_*_RENDER`）的第二个实参：PC 传的是渲染用偏移量（`Vector`）。
//
// **它是什么**：引擎把世界坐标转成屏幕坐标时加的那两项之和 —— 房间的渲染滚动偏移
// （`Room + 0x1938`，`Room:GetRenderScrollOffset()`，layout 表里 confirmed）与游戏的屏幕调整量
// （`Game + 0x24F9B0`，layout 表里 confirmed）。取证见 `room_layout.hpp` 与 `game_layout.hpp`：
// 引擎自己的 `WorldToScreenPosition` 就是"世界坐标 + 房间滚动偏移 + 游戏那一项"。
//
// ⚠️ **已知差异（未逐字核对）**：PC 传给回调的 `RenderOffset` 是否**恰好**等于这两项之和，
// 我们还没有用反汇编在 `Entity::Render` 的调用点核对过（见台账 `note`）。取这两项之和是因为
// 它是引擎自己那条换算里"除去世界坐标"的全部剩余量 —— 模组拿它重画实体会落在引擎画的位置上。
struct GameRenderOffset {
    float x;
    float y;
};

GameRoomObservation ReadGameRenderOffset(uintptr_t ownerSlot, GameRenderOffset* offset);

enum class GameIsGreedModeObservation : std::uint32_t {
    OwnerNull,
    OwnerUnreadable,
    GameNull,
    GameUnreadable,
    MethodUnavailable,
    GreedFalse,
    GreedTrue,
};

enum class GameIsAscentObservation : std::uint32_t {
    OwnerNull,
    OwnerUnreadable,
    GameNull,
    GameUnreadable,
    MethodUnavailable,
    AscentFalse,
    AscentTrue,
};

GameOwnerObservation ObserveGameOwnerChain(uintptr_t ownerSlot);
GameOwnerObservation DeepestGameOwnerObservation();
GameIsPausedObservation ObserveGameIsPaused(uintptr_t ownerSlot, uintptr_t isPausedAddress);
GameLevelStageObservation ReadCurrentGameLevelStage(uintptr_t ownerSlot, std::uint32_t* stage);
// 当前房间的**维度**（`Level + 0x21560`）。`Room:IsMirrorWorld()` 的判据是它 == 1
// （维度枚举的证据见 `runtime_constants.hpp` 的 `kMirrorWorldDimension`）。
GameLevelStageObservation ReadCurrentGameRoomDimension(uintptr_t ownerSlot,
                                                       std::uint32_t* dimension);
GameItemPoolObservation ReadCurrentGameItemPool(uintptr_t ownerSlot, void** itemPool);
GameRoomObservation ReadCurrentGameRoom(uintptr_t ownerSlot, void** room);
GameRoomObservation ReadCurrentGameRoomType(uintptr_t ownerSlot, std::uint32_t* roomType);
GameRoomObservation ReadGameRoomTypeFromGame(const IsaacRepentance::Game* game, std::uint32_t* roomType);
GameRoomObservation ReadGameCurrentRoomKeyFromGame(const IsaacRepentance::Game* game, GameRoomKey* key);
GameRoomObservation ReadGameRoomDescriptorSnapshotFromGame(
    const IsaacRepentance::Game* game, GameRoomDescriptorSnapshot* snapshot);
GameIsGreedModeObservation ObserveGameIsGreedMode(uintptr_t ownerSlot, uintptr_t methodAddress);
GameIsAscentObservation ObserveLevelIsAscent(uintptr_t ownerSlot, uintptr_t methodAddress);

void ObserveGameFrame(IsaacRepentance::Game* game);
bool HasObservedGameFrame();
void ObserveGameUpdateFrame(IsaacRepentance::Game* game);
bool HasEnteredGameUpdateObserverRelay();
bool HasObservedGameUpdateFrame();
void ObserveGameState2Frame(IsaacRepentance::Game* game);
bool HasEnteredGameState2ObserverRelay();
bool HasObservedGameState2Frame();
void ObserveGameRenderFrame(IsaacRepentance::Game* game);
bool HasEnteredGameRenderObserverRelay();
bool HasObservedGameRenderFrame();
