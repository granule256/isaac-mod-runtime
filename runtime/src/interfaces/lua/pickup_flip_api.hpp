#pragma once

#include <cstddef>
#include <cstdint>

namespace isaac::runtime::pickup_flip {

// The native SmartPointer is two pointers in declaration order:
// {EntitySaveState*, ReferenceCount<EntitySaveState>*}.
struct SaveStatePointer {
    void* saveState{};
    void* reference{};
};

enum class InitResult {
    Success,
    Ineligible,
    BindingUnavailable,
    RoomUnavailable,
    AllocationFailed,
};

struct NativeBindings {
    bool (*canReroll)(const void*){};
    void* (*allocate)(std::size_t){};
    void (*deallocate)(void*){};
    void (*mutexCtor)(void*){};
    void (*mutexInit)(void*){};
    std::uint32_t (*nextSeed)(std::uint32_t){};
    std::int32_t (*seededCollectible)(void*, std::uint32_t){};
    void (*setFlipState)(void*, const SaveStatePointer&){};
    bool (*decrementReference)(void*){};
    void (*copyAnm2)(void*, const void*){};
    void (*swapAnm2)(void*, void*){};
    void (*resetAnm2)(void*){};
    void (*destroyAnm2)(void*){};
    void (*setupCollectibleGraphics)(void*, std::uint32_t, std::int32_t,
                                     std::uint32_t, bool){};
    void (*loadGraphics)(void*){};
    void (*play)(void*, const char*, bool){};
    void (*update)(void*){};
};

// Restores the pinned PickupUtils factory without the Switch-only Flip-711 owner gate.
InitResult InitializeFlipState(void* pickup, std::int32_t collectible,
                               bool setupGraphics) noexcept;

#if !defined(__SWITCH__)
void SetNativeTestBindings(NativeBindings bindings) noexcept;
#endif

}  // namespace isaac::runtime::pickup_flip
