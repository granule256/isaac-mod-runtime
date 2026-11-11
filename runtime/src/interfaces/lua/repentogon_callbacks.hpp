#pragma once

#include <cstdint>

namespace isaac::runtime { struct RepentogonBatch; struct ExtendedCallbackState; }

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
    SaveSlot
};
struct Event {
    std::uint32_t id{};
    EventKind kind{EventKind::Global};
    std::uintptr_t object{}, collider{};
    const Vector* offset{};
    bool low{};
    Sound* sound{};
    std::int32_t first{}, second{}, third{}, fourth{};
};
struct Result {
    bool hasBoolean{}, boolean{}, hasOffset{}; Vector offset{};
    bool hasIntegerPair{};std::int32_t first{},second{};
};
Result Dispatch(const Event&) noexcept;
const ExtendedCallbackState* FindCallbackState(std::uint32_t id) noexcept;
bool Listening(std::uint32_t id) noexcept;
struct NativePort {
    bool (*ready)() noexcept;
    bool (*install)() noexcept;
    bool (*spriteAlive)(std::uintptr_t) noexcept{};
    bool (*updatePaused)() noexcept{};
};
bool UpdatePaused() noexcept;
bool HasSpriteValidator() noexcept;
bool CallbackSpriteAlive(std::uintptr_t) noexcept;
void SetNativePort(const NativePort*) noexcept;
extern const RepentogonBatch kCallbackBatch;
const RepentogonBatch& CallbackBatch() noexcept;
bool HasNativePort() noexcept;
} // namespace isaac::runtime::repentogon
