#pragma once

#include <cstdint>

namespace isaac::runtime { struct RepentogonBatch; }

namespace isaac::runtime::repentogon {
struct Vector { float x{}, y{}; };
struct Sound {
    std::int32_t id{};
    float volume{};
    std::int32_t delay{};
    bool loop{};
    float pitch{}, pan{};
};
enum class EventKind { Global, Entity, EntityRender, Grid, GridRender, Collision, Sound };
struct Event {
    std::uint32_t id{};
    EventKind kind{EventKind::Global};
    std::uintptr_t object{}, collider{};
    const Vector* offset{};
    bool low{};
    Sound* sound{};
};
struct Result { bool hasBoolean{}, boolean{}, hasOffset{}; Vector offset{}; };
Result Dispatch(const Event&) noexcept;
bool Listening(std::uint32_t id) noexcept;
struct NativePort { bool (*ready)() noexcept; bool (*install)() noexcept; };
void SetNativePort(const NativePort*) noexcept;
const RepentogonBatch& CallbackBatch() noexcept;
bool HasNativePort() noexcept;
} // namespace isaac::runtime::repentogon
