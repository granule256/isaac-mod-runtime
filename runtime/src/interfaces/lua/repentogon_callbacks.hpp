#pragma once

#include <cstdint>

namespace isaac::runtime { struct RepentogonBatch; struct ExtendedCallbackState; struct Api600MultiShotParams; }

namespace isaac::runtime::repentogon {
struct Vector { float x{}, y{}; };
struct Sound {
    std::int32_t id{};
    float volume{};
    std::int32_t delay{};
    bool loop{};
    float pitch{}, pan{};
};
enum class EventKind {
    Global, Entity, EntityRender, Grid, GridRender, Collision, Sound, IntegerPair, AddCollectible,
    SaveSlot, RoomDescriptor, Number, LevelGenerator, LevelGeneratorRoom, BossPool, CollectibleRemoved,
    Boolean, FiredEntity, PlayerActiveMinUsableCharge, PlayerHudActive,
    PlayerAddHearts, ShopItemPrice, ItemText, PlayerLifecycle, NpcTarget,
    UseCard, MusicPlay, PickupMorph, WeaponFired, CustomCache, PickupVoid,
    PlayerHudHearts, LegacyMultiShot, PlayerGridCollision, ActiveMaxCharge,
    PlayerHeartLimit, PlayerHealthType, TrinketAdded, PickupLootList
};
struct Event {
    std::uint32_t id{};
    EventKind kind{EventKind::Global};
    std::uintptr_t object{}, collider{};
    const Vector* offset{};
    bool low{};
    Sound* sound{};
    std::int32_t first{}, second{}, third{}, fourth{};
    float number{};
    const Vector* chargeBar{};
    float scale{};
    const char* title{};
    const char* subtitle{};
    std::uint64_t damageFlags{};
    Api600MultiShotParams* multiShot{};
    const char* customCacheTag{};
    double customCacheValue{};
    std::uintptr_t lootList{}, lootRng{};
};
struct Result {
    bool hasBoolean{}, boolean{}, hasOffset{}; Vector offset{};
    bool hasIntegerPair{};std::int32_t first{},second{};
    bool hasNumber{};float number{};
    bool hasObject{};std::uintptr_t object{};
    bool hasInteger{};std::int32_t integer{};
    bool failed{},hasTable{};
    std::int32_t tableLength{},third{},fourth{};
    bool firstFlag{},secondFlag{},thirdFlag{};
    bool hasCustomCacheValue{};
    double customCacheValue{};
};
Result Dispatch(const Event&) noexcept;
const ExtendedCallbackState* FindCallbackState(std::uint32_t id) noexcept;
bool Listening(std::uint32_t id) noexcept;
struct NativePort {
    bool (*ready)() noexcept;
    bool (*install)() noexcept;
    bool (*spriteAlive)(std::uintptr_t) noexcept{};
    bool (*updatePaused)() noexcept{};
    void (*resetCustomCacheRun)() noexcept{};
};
bool UpdatePaused() noexcept;
bool HasSpriteValidator() noexcept;
bool CallbackSpriteAlive(std::uintptr_t) noexcept;
void SetNativePort(const NativePort*) noexcept;
extern const RepentogonBatch kCallbackBatch;
const RepentogonBatch& CallbackBatch() noexcept;
bool HasNativePort() noexcept;
bool HasNativePortAvailable() noexcept;
} // namespace isaac::runtime::repentogon
