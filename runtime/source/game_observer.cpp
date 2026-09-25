#include "game_observer.hpp"

#include <atomic>

#include "lib/nx/nx.h"

// 引擎内存访问层（架构重建阶段 1）：偏移算术、对齐检查、取值都收在这一层里，本文件
// 只写"读哪个字段"。用法与红线见 `docs/加一个功能模块的做法.md` 第三节。
//
// **本文件仍然是"这段内存可读吗"的提供方**：层不引 libnx（vendored 与 devkitpro 的
// `MemoryInfo` 布局不同），平台判定留在各自 TU —— 本文件的 `IsReadableNonExecutableMapping`
// 就是本文件那一份判定，按原有语义（要求带 `Perm_R` 且**不带** `Perm_X`）逐条不变。
#include "infrastructure/memory/engine_field_access.hpp"

#if defined(__GNUC__) && !defined(__clang__)
#pragma GCC optimize ("Os")
#endif

namespace {
// 匿名命名空间内起个别名，让下面的调用点短一些；它指向的是 `src/` 那一层。
namespace engine_memory = isaac::runtime::engine_memory;

std::atomic<u32> g_GameObserved{false};
std::atomic<u32> g_GameUpdateObserverEntered{false};
std::atomic<u32> g_GameUpdateObserved{false};
std::atomic<u32> g_GameState2ObserverEntered{false};
std::atomic<u32> g_GameState2Observed{false};
std::atomic<u32> g_GameRenderObserverEntered{false};
std::atomic<u32> g_GameRenderObserved{false};
std::atomic<GameOwnerObservation> g_DeepestGameOwnerObservation{
    GameOwnerObservation::OwnerNull};
constexpr size_t kGameIsPausedThunkWindowSize = 16;
constexpr uintptr_t kGameItemPoolOffset = 0x242C0;
constexpr uintptr_t kLevelCurrentRoomOffset = 0x21550;
constexpr uintptr_t kLevelCurrentRoomIndexOffset = 0x21558;
constexpr uintptr_t kLevelCurrentRoomDimensionOffset = 0x21560;
// `Level + 0x00` = `eLevelStage`、`Level + 0x04` = `eStageType`（`Level::SetStage` 的落点，
// 证据见 `runtime_constants.hpp`）。`Level` 与 `Game` 同一地址，所以还是同一个 base。
constexpr uintptr_t kLevelStageOffset = 0x00;
constexpr uintptr_t kLevelStageTypeOffset = 0x04;
constexpr uintptr_t kRoomTypeOffset = 0x10;
constexpr uintptr_t kRoomDescriptorOffset = 0x8;
constexpr uintptr_t kDescriptorCandidateWord0cOffset = 0xc;
constexpr uintptr_t kDescriptorCandidateWord50Offset = 0x50;
// 渲染偏移的两个分量（语义与取证见 `game_observer.hpp` 的 `GameRenderOffset` 注释，
// 以及 `room_layout.hpp` / `game_layout.hpp` 的 confirmed 行）。
constexpr uintptr_t kRoomRenderScrollOffsetOffset = 0x1938;
constexpr uintptr_t kGameToScreenAdjustOffset = 0x24F9B0;

bool IsReadableNonExecutableMapping(uintptr_t address, size_t length) {
    if (length == 0 || address > UINTPTR_MAX - length) return false;
    MemoryInfo info{};
    u32 pageInfo = 0;
    if (R_FAILED(svcQueryMemory(&info, &pageInfo, address)) || info.size == 0 ||
        info.addr > UINTPTR_MAX - info.size) {
        return false;
    }
    const uintptr_t end = address + length;
    return address >= info.addr && end <= info.addr + info.size &&
           (info.perm & Perm_R) != 0 && (info.perm & Perm_X) == 0;
}

bool IsMappedRxModuleCodeWindow(uintptr_t address, size_t length) {
    if (length == 0 || address > UINTPTR_MAX - length) return false;
    MemoryInfo info{};
    u32 pageInfo = 0;
    if (R_FAILED(svcQueryMemory(&info, &pageInfo, address)) || info.size == 0 ||
        info.addr > UINTPTR_MAX - info.size) {
        return false;
    }
    const uintptr_t end = address + length;
    return address >= info.addr && end <= info.addr + info.size &&
           (info.type & MemState_Type) == MemType_ModuleCodeStatic && info.perm == Perm_Rx;
}

void RecordGameOwnerObservation(GameOwnerObservation observation) {
    auto current = g_DeepestGameOwnerObservation.load(std::memory_order_relaxed);
    while (current < observation &&
           !g_DeepestGameOwnerObservation.compare_exchange_weak(
               current, observation, std::memory_order_release, std::memory_order_relaxed)) {}
}
}

GameOwnerObservation ObserveGameOwnerChain(uintptr_t ownerSlot) {
    if (ownerSlot == 0) {
        RecordGameOwnerObservation(GameOwnerObservation::OwnerUnreadable);
        return GameOwnerObservation::OwnerUnreadable;
    }
    if ((ownerSlot & (alignof(uintptr_t) - 1)) != 0 ||
        !IsReadableNonExecutableMapping(ownerSlot, sizeof(uintptr_t))) {
        RecordGameOwnerObservation(GameOwnerObservation::OwnerUnreadable);
        return GameOwnerObservation::OwnerUnreadable;
    }
    const uintptr_t owner = *reinterpret_cast<const uintptr_t*>(ownerSlot);
    if (owner == 0) {
        RecordGameOwnerObservation(GameOwnerObservation::OwnerNull);
        return GameOwnerObservation::OwnerNull;
    }
    if ((owner & (alignof(uintptr_t) - 1)) != 0 ||
        !IsReadableNonExecutableMapping(owner, sizeof(uintptr_t))) {
        RecordGameOwnerObservation(GameOwnerObservation::OwnerUnreadable);
        return GameOwnerObservation::OwnerUnreadable;
    }
    const uintptr_t game = *reinterpret_cast<const uintptr_t*>(owner);
    if (game == 0) {
        RecordGameOwnerObservation(GameOwnerObservation::GameNull);
        return GameOwnerObservation::GameNull;
    }
    if ((game & (alignof(uintptr_t) - 1)) != 0 ||
        !IsReadableNonExecutableMapping(game, sizeof(uintptr_t))) {
        RecordGameOwnerObservation(GameOwnerObservation::GameUnreadable);
        return GameOwnerObservation::GameUnreadable;
    }
    RecordGameOwnerObservation(GameOwnerObservation::Success);
    return GameOwnerObservation::Success;
}

GameOwnerObservation DeepestGameOwnerObservation() {
    return g_DeepestGameOwnerObservation.load(std::memory_order_acquire);
}

GameIsPausedObservation ObserveGameIsPaused(uintptr_t ownerSlot, uintptr_t isPausedAddress) {
    if (isPausedAddress == 0 || (isPausedAddress & 3) != 0 ||
        !IsMappedRxModuleCodeWindow(isPausedAddress, kGameIsPausedThunkWindowSize)) {
        return GameIsPausedObservation::ThunkUnavailable;
    }
    if (ownerSlot == 0 || (ownerSlot & (alignof(uintptr_t) - 1)) != 0 ||
        !IsReadableNonExecutableMapping(ownerSlot, sizeof(uintptr_t))) {
        RecordGameOwnerObservation(GameOwnerObservation::OwnerUnreadable);
        return GameIsPausedObservation::OwnerUnreadable;
    }
    const uintptr_t owner = *reinterpret_cast<const uintptr_t*>(ownerSlot);
    if (owner == 0) {
        RecordGameOwnerObservation(GameOwnerObservation::OwnerNull);
        return GameIsPausedObservation::OwnerNull;
    }
    if ((owner & (alignof(uintptr_t) - 1)) != 0 ||
        !IsReadableNonExecutableMapping(owner, sizeof(uintptr_t))) {
        RecordGameOwnerObservation(GameOwnerObservation::OwnerUnreadable);
        return GameIsPausedObservation::OwnerUnreadable;
    }
    const uintptr_t gameAddress = *reinterpret_cast<const uintptr_t*>(owner);
    if (gameAddress == 0) {
        RecordGameOwnerObservation(GameOwnerObservation::GameNull);
        return GameIsPausedObservation::GameNull;
    }
    if ((gameAddress & (alignof(uintptr_t) - 1)) != 0 ||
        !IsReadableNonExecutableMapping(gameAddress, sizeof(uintptr_t))) {
        RecordGameOwnerObservation(GameOwnerObservation::GameUnreadable);
        return GameIsPausedObservation::GameUnreadable;
    }

    using GameIsPausedFunction = bool (*)(const IsaacRepentance::Game*);
    const auto* game = reinterpret_cast<const IsaacRepentance::Game*>(gameAddress);
    const auto isPaused = reinterpret_cast<GameIsPausedFunction>(isPausedAddress);
    RecordGameOwnerObservation(GameOwnerObservation::Success);
    return isPaused(game) ? GameIsPausedObservation::PausedTrue
                          : GameIsPausedObservation::PausedFalse;
}

GameLevelStageObservation ReadCurrentGameLevelStage(uintptr_t ownerSlot, std::uint32_t* stage) {
    uintptr_t owner = 0;
    uintptr_t game = 0;
    if (stage == nullptr ||
        !engine_memory::LoadPointer(ownerSlot, &owner, &IsReadableNonExecutableMapping)) {
        return GameLevelStageObservation::OwnerUnreadable;
    }
    if (owner == 0) return GameLevelStageObservation::OwnerNull;
    if (!engine_memory::LoadPointer(owner, &game, &IsReadableNonExecutableMapping)) {
        return GameLevelStageObservation::OwnerUnreadable;
    }
    if (game == 0) return GameLevelStageObservation::GameNull;
    // 原判据对 base 用的是 8 字节对齐（`alignof(uintptr_t)`）而字段是 4 字节 —— 逐条照旧。
    std::uint32_t value = 0;
    if (!engine_memory::ReadField(game, kLevelStageOffset, &value, &IsReadableNonExecutableMapping,
                                 alignof(uintptr_t))) {
        return GameLevelStageObservation::GameUnreadable;
    }
    *stage = value;
    return GameLevelStageObservation::Success;
}

// 当前房间的维度（`Level + 0x21560`）。与 `ReadCurrentGameLevelStage` 逐句同形：
// `Level` 与 `Game` 同一地址，所以是同一条"槽 → owner → Game*"链，只是读的字段不同。
// 判据与证据见 `runtime_constants.hpp` 的 `kMirrorWorldDimension`。
GameLevelStageObservation ReadCurrentGameRoomDimension(uintptr_t ownerSlot,
                                                       std::uint32_t* dimension) {
    uintptr_t owner = 0;
    uintptr_t game = 0;
    if (dimension == nullptr ||
        !engine_memory::LoadPointer(ownerSlot, &owner, &IsReadableNonExecutableMapping)) {
        return GameLevelStageObservation::OwnerUnreadable;
    }
    if (owner == 0) return GameLevelStageObservation::OwnerNull;
    if (!engine_memory::LoadPointer(owner, &game, &IsReadableNonExecutableMapping)) {
        return GameLevelStageObservation::OwnerUnreadable;
    }
    if (game == 0) return GameLevelStageObservation::GameNull;
    std::uint32_t value = 0;
    if (!engine_memory::ReadField(game, kLevelCurrentRoomDimensionOffset, &value,
                                 &IsReadableNonExecutableMapping)) {
        return GameLevelStageObservation::GameUnreadable;
    }
    *dimension = value;
    return GameLevelStageObservation::Success;
}

GameItemPoolObservation ReadCurrentGameItemPool(uintptr_t ownerSlot, void** itemPool) {
    uintptr_t owner = 0;
    uintptr_t game = 0;
    if (itemPool == nullptr ||
        !engine_memory::LoadPointer(ownerSlot, &owner, &IsReadableNonExecutableMapping)) {
        return GameItemPoolObservation::OwnerUnreadable;
    }
    if (owner == 0) return GameItemPoolObservation::OwnerNull;
    if (!engine_memory::LoadPointer(owner, &game, &IsReadableNonExecutableMapping)) {
        return GameItemPoolObservation::OwnerUnreadable;
    }
    if (game == 0) return GameItemPoolObservation::GameNull;
    if (!engine_memory::PointerUsable(game, &IsReadableNonExecutableMapping)) {
        return GameItemPoolObservation::GameUnreadable;
    }
    // 这里返回的是那一段的**地址**（不是它的值），所以走"解地址"而不是"读字段"。
    const std::uintptr_t candidate = engine_memory::FieldAddress(
        game, kGameItemPoolOffset, sizeof(uintptr_t), alignof(uintptr_t),
        &IsReadableNonExecutableMapping);
    if (candidate == 0) {
        return GameItemPoolObservation::ItemPoolUnreadable;
    }
    *itemPool = engine_memory::AsObject(candidate);
    return GameItemPoolObservation::Success;
}

GameRoomObservation ReadCurrentGameRoom(uintptr_t ownerSlot, void** room) {
    uintptr_t owner = 0;
    uintptr_t game = 0;
    uintptr_t currentRoom = 0;
    if (room == nullptr ||
        !engine_memory::LoadPointer(ownerSlot, &owner, &IsReadableNonExecutableMapping)) {
        return GameRoomObservation::OwnerUnreadable;
    }
    if (owner == 0) return GameRoomObservation::OwnerNull;
    if (!engine_memory::LoadPointer(owner, &game, &IsReadableNonExecutableMapping)) {
        return GameRoomObservation::OwnerUnreadable;
    }
    if (game == 0) return GameRoomObservation::GameNull;
    // 回绕比较与原实现同档（它归在 `GameUnreadable` 里，不能让它掉进下一档）。
    if (!engine_memory::PointerUsable(game, &IsReadableNonExecutableMapping) ||
        game > UINTPTR_MAX - kLevelCurrentRoomOffset) {
        return GameRoomObservation::GameUnreadable;
    }
    // 槽本身在这里校；槽里的值下一句再校 —— 与原顺序一致。
    if (!engine_memory::LoadPointerAt(game, kLevelCurrentRoomOffset, alignof(uintptr_t),
                                      &currentRoom, &IsReadableNonExecutableMapping)) {
        return GameRoomObservation::RoomUnreadable;
    }
    if (currentRoom == 0) return GameRoomObservation::RoomNull;
    if (!engine_memory::PointerUsable(currentRoom, &IsReadableNonExecutableMapping)) {
        return GameRoomObservation::RoomUnreadable;
    }
    *room = engine_memory::AsObject(currentRoom);
    return GameRoomObservation::Success;
}

GameRoomObservation ReadCurrentGameRoomType(uintptr_t ownerSlot, std::uint32_t* roomType) {
    if (roomType == nullptr) return GameRoomObservation::RoomUnreadable;
    void* room = nullptr;
    const GameRoomObservation result = ReadCurrentGameRoom(ownerSlot, &room);
    if (result != GameRoomObservation::Success) return result;
    std::uint32_t value = 0;
    if (!engine_memory::ReadField(engine_memory::AddressOf(room), kRoomTypeOffset, &value,
                                  &IsReadableNonExecutableMapping)) {
        return GameRoomObservation::RoomUnreadable;
    }
    *roomType = value;
    return GameRoomObservation::Success;
}

GameRoomObservation ReadGameRoomTypeFromGame(const IsaacRepentance::Game* game, std::uint32_t* roomType) {
    if (game == nullptr || roomType == nullptr) return GameRoomObservation::GameNull;
    const uintptr_t gameAddress = engine_memory::AddressOf(game);
    uintptr_t room = 0;
    if (!engine_memory::PointerUsable(gameAddress, &IsReadableNonExecutableMapping) ||
        gameAddress > UINTPTR_MAX - kLevelCurrentRoomOffset) {
        return GameRoomObservation::GameUnreadable;
    }
    if (!engine_memory::LoadPointerAt(gameAddress, kLevelCurrentRoomOffset, alignof(uintptr_t),
                                      &room, &IsReadableNonExecutableMapping)) {
        return GameRoomObservation::RoomUnreadable;
    }
    if (room == 0) return GameRoomObservation::RoomNull;
    // 这里对 `room` 的判据是"8 字节对齐 + `room + 0x10` 那 4 字节可读"（**不**检查 room 自身可读）
    // ⇒ 用 `ReadField`（对齐 + 回绕 + 字段区间可读 + 取值）而不是 `PointerUsable` 那一档。
    std::uint32_t value = 0;
    if (!engine_memory::ReadField(room, kRoomTypeOffset, &value, &IsReadableNonExecutableMapping,
                                  alignof(uintptr_t))) {
        return GameRoomObservation::RoomUnreadable;
    }
    *roomType = value;
    return GameRoomObservation::Success;
}

GameRoomObservation ReadGameCurrentRoomKeyFromGame(const IsaacRepentance::Game* game, GameRoomKey* key) {
    if (game == nullptr || key == nullptr) return GameRoomObservation::GameNull;
    const uintptr_t gameAddress = engine_memory::AddressOf(game);
    constexpr std::uintptr_t kAlignment = alignof(std::uint32_t);
    std::uint32_t roomIndex = 0;
    std::uint32_t dimension = 0;
    if (!engine_memory::ReadField(gameAddress, kLevelCurrentRoomIndexOffset, &roomIndex,
                                  &IsReadableNonExecutableMapping, kAlignment) ||
        !engine_memory::ReadField(gameAddress, kLevelCurrentRoomDimensionOffset, &dimension,
                                  &IsReadableNonExecutableMapping, kAlignment)) {
        return GameRoomObservation::GameUnreadable;
    }
    key->roomIndex = roomIndex;
    key->dimension = dimension;
    return GameRoomObservation::Success;
}

GameRoomObservation ReadGameLocationKey(uintptr_t ownerSlot, GameLocationKey* key) {
    if (key == nullptr) return GameRoomObservation::RoomUnreadable;
    uintptr_t owner = 0;
    uintptr_t game = 0;
    if (!engine_memory::LoadPointer(ownerSlot, &owner, &IsReadableNonExecutableMapping)) {
        return GameRoomObservation::OwnerUnreadable;
    }
    if (owner == 0) return GameRoomObservation::OwnerNull;
    if (!engine_memory::LoadPointer(owner, &game, &IsReadableNonExecutableMapping)) {
        return GameRoomObservation::OwnerUnreadable;
    }
    if (game == 0) return GameRoomObservation::GameNull;
    // 四个字段逐个查可读性 —— 与原实现逐条一致（那里就是四处独立检查，没有合并成一次大区间）。
    // ⚠️ 该处原有的注释写的是"四个字一次可读性检查就够…逐字检查会把调用数翻四倍"，
    // 与它下面的代码（四次独立调用）不符；本批只搬运、不改行为，把这个不一致如实记在这里。
    constexpr std::uintptr_t kAlignment = alignof(std::uint32_t);
    GameLocationKey loaded{};
    if (!engine_memory::ReadField(game, kLevelStageOffset, &loaded.stage,
                                  &IsReadableNonExecutableMapping, kAlignment) ||
        !engine_memory::ReadField(game, kLevelStageTypeOffset, &loaded.stageType,
                                  &IsReadableNonExecutableMapping, kAlignment) ||
        !engine_memory::ReadField(game, kLevelCurrentRoomIndexOffset, &loaded.roomIndex,
                                  &IsReadableNonExecutableMapping, kAlignment) ||
        !engine_memory::ReadField(game, kLevelCurrentRoomDimensionOffset, &loaded.roomDimension,
                                  &IsReadableNonExecutableMapping, kAlignment)) {
        return GameRoomObservation::GameUnreadable;
    }
    *key = loaded;
    return GameRoomObservation::Success;
}

GameRoomObservation ReadGameRenderOffset(uintptr_t ownerSlot, GameRenderOffset* offset) {
    if (offset == nullptr) return GameRoomObservation::GameUnreadable;
    // 与 `ReadGameLocationKey` 同一条链（槽 → owner → `Game*`）：不另造一份取址方式，
    // 否则两处对"Game 是谁"的理解会漂。
    uintptr_t owner = 0;
    uintptr_t game = 0;
    if (!engine_memory::LoadPointer(ownerSlot, &owner, &IsReadableNonExecutableMapping)) {
        return GameRoomObservation::OwnerUnreadable;
    }
    if (owner == 0) return GameRoomObservation::OwnerNull;
    if (!engine_memory::LoadPointer(owner, &game, &IsReadableNonExecutableMapping)) {
        return GameRoomObservation::OwnerUnreadable;
    }
    if (game == 0) return GameRoomObservation::GameNull;
    // 两段各确认一次（`game+0x21550` 那 8 字节、`game+0x24F9B0` 那 8 字节），
    // 与原来的"两次可读性检查一次做完"逐条一致 —— 都不检查 `game` 自身可读。
    uintptr_t room = 0;
    const std::uintptr_t gameAdjustAddress = engine_memory::FieldAddress(
        game, kGameToScreenAdjustOffset, 2 * sizeof(float), alignof(uintptr_t),
        &IsReadableNonExecutableMapping);
    if (!engine_memory::LoadPointerAt(game, kLevelCurrentRoomOffset, alignof(uintptr_t), &room,
                                      &IsReadableNonExecutableMapping) ||
        gameAdjustAddress == 0) {
        return GameRoomObservation::GameUnreadable;
    }
    if (room == 0) return GameRoomObservation::RoomNull;
    const std::uintptr_t roomScrollAddress = engine_memory::FieldAddress(
        room, kRoomRenderScrollOffsetOffset, 2 * sizeof(float), alignof(uintptr_t),
        &IsReadableNonExecutableMapping);
    if (roomScrollAddress == 0) {
        return GameRoomObservation::RoomUnreadable;
    }
    // 两个地址都已经确认过 8 字节可读 ⇒ 四个 float 直接取，不再重复问内核。
    float roomScrollX = 0.0F;
    float roomScrollY = 0.0F;
    float gameAdjustX = 0.0F;
    float gameAdjustY = 0.0F;
    if (!engine_memory::LoadVerified(roomScrollAddress, &roomScrollX) ||
        !engine_memory::LoadVerifiedAt(roomScrollAddress, 1, &roomScrollY) ||
        !engine_memory::LoadVerified(gameAdjustAddress, &gameAdjustX) ||
        !engine_memory::LoadVerifiedAt(gameAdjustAddress, 1, &gameAdjustY)) {
        return GameRoomObservation::RoomUnreadable;
    }
    offset->x = roomScrollX + gameAdjustX;
    offset->y = roomScrollY + gameAdjustY;
    return GameRoomObservation::Success;
}

GameRoomObservation ReadGameRoomDescriptorSnapshotFromGame(
    const IsaacRepentance::Game* game, GameRoomDescriptorSnapshot* snapshot) {
    if (game == nullptr || snapshot == nullptr) return GameRoomObservation::GameNull;
    const uintptr_t gameAddress = engine_memory::AddressOf(game);
    uintptr_t room = 0;
    uintptr_t descriptor = 0;
    if (!engine_memory::LoadPointerAt(gameAddress, kLevelCurrentRoomOffset, alignof(uintptr_t),
                                      &room, &IsReadableNonExecutableMapping)) {
        return GameRoomObservation::GameUnreadable;
    }
    if (room == 0) return GameRoomObservation::RoomNull;
    if (!engine_memory::LoadPointerAt(room, kRoomDescriptorOffset, alignof(uintptr_t), &descriptor,
                                      &IsReadableNonExecutableMapping)) {
        return GameRoomObservation::RoomUnreadable;
    }
    if (descriptor == 0) return GameRoomObservation::RoomNull;
    GameRoomDescriptorSnapshot loaded{};
    if (!engine_memory::ReadField(descriptor, kDescriptorCandidateWord0cOffset,
                                  &loaded.candidateWord0c, &IsReadableNonExecutableMapping) ||
        !engine_memory::ReadField(descriptor, kDescriptorCandidateWord50Offset,
                                  &loaded.candidateWord50, &IsReadableNonExecutableMapping)) {
        return GameRoomObservation::RoomUnreadable;
    }
    *snapshot = loaded;
    return GameRoomObservation::Success;
}

GameIsGreedModeObservation ObserveGameIsGreedMode(uintptr_t ownerSlot, uintptr_t methodAddress) {
    if (methodAddress == 0 || (methodAddress & 3) != 0 ||
        !IsMappedRxModuleCodeWindow(methodAddress, kGameIsPausedThunkWindowSize)) {
        return GameIsGreedModeObservation::MethodUnavailable;
    }
    uintptr_t owner = 0;
    uintptr_t gameAddress = 0;
    if (!engine_memory::LoadPointer(ownerSlot, &owner, &IsReadableNonExecutableMapping)) {
        RecordGameOwnerObservation(GameOwnerObservation::OwnerUnreadable);
        return GameIsGreedModeObservation::OwnerUnreadable;
    }
    if (owner == 0) return GameIsGreedModeObservation::OwnerNull;
    if (!engine_memory::LoadPointer(owner, &gameAddress, &IsReadableNonExecutableMapping)) {
        RecordGameOwnerObservation(GameOwnerObservation::OwnerUnreadable);
        return GameIsGreedModeObservation::OwnerUnreadable;
    }
    if (gameAddress == 0) return GameIsGreedModeObservation::GameNull;
    if (!engine_memory::PointerUsable(gameAddress, &IsReadableNonExecutableMapping)) {
        RecordGameOwnerObservation(GameOwnerObservation::GameUnreadable);
        return GameIsGreedModeObservation::GameUnreadable;
    }
    using GameIsGreedModeFunction = bool (*)(const IsaacRepentance::Game*);
    RecordGameOwnerObservation(GameOwnerObservation::Success);
    return engine_memory::CallUnaryMethod<GameIsGreedModeFunction>(methodAddress, gameAddress)
               ? GameIsGreedModeObservation::GreedTrue
               : GameIsGreedModeObservation::GreedFalse;
}

GameIsAscentObservation ObserveLevelIsAscent(uintptr_t ownerSlot, uintptr_t methodAddress) {
    if (methodAddress == 0 || (methodAddress & 3) != 0 ||
        !IsMappedRxModuleCodeWindow(methodAddress, kGameIsPausedThunkWindowSize)) {
        return GameIsAscentObservation::MethodUnavailable;
    }
    uintptr_t owner = 0;
    uintptr_t gameAddress = 0;
    if (!engine_memory::LoadPointer(ownerSlot, &owner, &IsReadableNonExecutableMapping)) {
        return GameIsAscentObservation::OwnerUnreadable;
    }
    if (owner == 0) return GameIsAscentObservation::OwnerNull;
    if (!engine_memory::LoadPointer(owner, &gameAddress, &IsReadableNonExecutableMapping)) {
        return GameIsAscentObservation::OwnerUnreadable;
    }
    if (gameAddress == 0) return GameIsAscentObservation::GameNull;
    if (!engine_memory::PointerUsable(gameAddress, &IsReadableNonExecutableMapping)) {
        return GameIsAscentObservation::GameUnreadable;
    }
    using LevelIsAscentFunction = bool (*)(const IsaacRepentance::Level*);
    RecordGameOwnerObservation(GameOwnerObservation::Success);
    return engine_memory::CallUnaryMethod<LevelIsAscentFunction>(methodAddress, gameAddress)
               ? GameIsAscentObservation::AscentTrue
               : GameIsAscentObservation::AscentFalse;
}

void ObserveGameFrame(IsaacRepentance::Game* game) {
    if (game != nullptr) {
        g_GameObserved.store(true, std::memory_order_release);
    }
}

bool HasObservedGameFrame() {
    return g_GameObserved.load(std::memory_order_acquire);
}

void ObserveGameUpdateFrame(IsaacRepentance::Game* game) {
    g_GameUpdateObserverEntered.store(true, std::memory_order_release);
    if (game != nullptr) {
        g_GameUpdateObserved.store(true, std::memory_order_release);
    }
}

bool HasEnteredGameUpdateObserverRelay() {
    return g_GameUpdateObserverEntered.load(std::memory_order_acquire);
}

bool HasObservedGameUpdateFrame() {
    return g_GameUpdateObserved.load(std::memory_order_acquire);
}

void ObserveGameState2Frame(IsaacRepentance::Game* game) {
    g_GameState2ObserverEntered.store(true, std::memory_order_release);
    if (game != nullptr) {
        g_GameState2Observed.store(true, std::memory_order_release);
    }
}

bool HasEnteredGameState2ObserverRelay() {
    return g_GameState2ObserverEntered.load(std::memory_order_acquire);
}

bool HasObservedGameState2Frame() {
    return g_GameState2Observed.load(std::memory_order_acquire);
}

void ObserveGameRenderFrame(IsaacRepentance::Game* game) {
    g_GameRenderObserverEntered.store(true, std::memory_order_release);
    if (game != nullptr) g_GameRenderObserved.store(true, std::memory_order_release);
}

bool HasEnteredGameRenderObserverRelay() {
    return g_GameRenderObserverEntered.load(std::memory_order_acquire);
}

bool HasObservedGameRenderFrame() {
    return g_GameRenderObserved.load(std::memory_order_acquire);
}
