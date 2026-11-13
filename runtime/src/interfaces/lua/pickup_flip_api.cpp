#include "interfaces/lua/pickup_flip_api.hpp"

#include "infrastructure/call/engine_call_access.hpp"
#include "infrastructure/memory/engine_field_access.hpp"
#include "lua_runtime.hpp"
#include "runtime_constants.hpp"

#include <array>
#include <cstddef>
#include <cstdint>
#include <cstring>

namespace isaac::runtime::pickup_flip {
namespace {

constexpr std::size_t kEntitySaveStateSize = 0x78;
constexpr std::size_t kReferenceCountSize = 0x48;
constexpr std::size_t kAnm2Size = kSpriteObjectSize;
constexpr std::uint32_t kPickupVariantCollectible = 100;
constexpr std::uintptr_t kPickupFlipStateOffset = 0x610;
constexpr std::uintptr_t kPickupAltSpriteOffset = 0x620;
constexpr std::uintptr_t kEntitySaveStateTypeOffset = 0x00;
constexpr std::uintptr_t kEntitySaveStateVariantOffset = 0x04;
constexpr std::uintptr_t kEntitySaveStateSubtypeOffset = 0x08;
constexpr std::uintptr_t kEntitySaveStateInitSeedOffset = 0x34;
constexpr std::uintptr_t kReferenceStateOffset = 0x40;
constexpr std::uintptr_t kReferenceCountOffset = 0x08;
constexpr std::uint32_t kReferenceCountInitial = 0x10001U;
constexpr std::uintptr_t kEntitySaveStateReferenceVtableOffset = 0xa370b0;
constexpr std::uintptr_t kReferenceCountBaseVtableOffset = 0xa34088;
constexpr std::uintptr_t kGameRoomOffset = kGameRoomPointerOffset;
constexpr std::size_t kAnimationNameCapacity = 128;
constexpr std::uint8_t kLibcxxLongFlag = kLibcxxStringLongFlag;
constexpr std::size_t kLibcxxLongDataOffset = kLibcxxStringDataOffset;
constexpr std::size_t kLibcxxShortDataOffset = kLibcxxStringShortDataOffset;

template <class T>
void PutCandidate(void* object, std::size_t offset, const T& value) noexcept {
    std::memcpy(static_cast<unsigned char*>(object) + offset, &value, sizeof(value));
}

template <class T>
bool ReadAt(std::uintptr_t address, T* value) noexcept {
    return engine_memory::ReadAt(address, value, engine_memory::EngineMemoryReadable);
}

bool ReadLibcxxStringAt(std::uintptr_t object, char* out, std::size_t capacity) noexcept {
    if (object == 0 || out == nullptr || capacity < 2) {
        return false;
    }
    std::uint8_t header = 0;
    if (!ReadAt(object, &header)) {
        return false;
    }
    std::uintptr_t data = 0;
    std::size_t declared = 0;
    if ((header & kLibcxxLongFlag) != 0) {
        if (!ReadAt(object + kLibcxxLongDataOffset, &data) || data == 0 ||
            !ReadAt(object + 8, &declared)) {
            return false;
        }
    } else {
        data = object + kLibcxxShortDataOffset;
        declared = static_cast<std::size_t>(header >> 1);
    }
    if (declared == 0 || declared >= capacity) {
        return false;
    }
    for (std::size_t i = 0; i < declared; ++i) {
        char value = 0;
        if (!ReadAt(data + i, &value)) {
            return false;
        }
        out[i] = value;
    }
    out[declared] = '\0';
    return true;
}

bool ReadFirstAnimationName(std::uintptr_t primary, char* out, std::size_t capacity) noexcept {
    std::uintptr_t animations = 0;
    std::uint32_t count = 0;
    if (!engine_memory::ReadField(primary, kAnim2AnimationArrayOffset, &animations,
                                  engine_memory::EngineMemoryReadable) ||
        !engine_memory::ReadField(primary, kAnim2AnimationCountOffset, &count,
                                  engine_memory::EngineMemoryReadable) ||
        animations == 0 || count == 0) {
        return false;
    }
    return ReadLibcxxStringAt(animations, out, capacity);
}

std::uintptr_t ReadCurrentRoom() noexcept {
    const auto base = LuaRuntime::EngineModuleBase();
    if (base == 0) {
        return 0;
    }
    std::uintptr_t game = 0;
    std::uintptr_t room = 0;
    if (!engine_memory::ReadField(base, kGameOwnerGlobalSlotOffset, &game,
                                  engine_memory::EngineMemoryReadable) ||
        game == 0 ||
        !engine_memory::ReadField(game, kGameRoomOffset, &room,
                                  engine_memory::EngineMemoryReadable)) {
        return 0;
    }
    return room;
}

#if defined(__SWITCH__)
using AllocateFn = void* (*)(std::size_t);
using DeallocateFn = void (*)(void*);
using MutexFn = void (*)(void*);
using CanRerollFn = bool (*)(const void*);
using RngCtorFn = void (*)(void*, std::uint32_t, std::uint32_t);
using RngNextFn = std::uint32_t (*)(void*);
using RngDtorFn = void (*)(void*);
using SeededCollectibleFn = std::int32_t (*)(void*, std::uint32_t, bool);
using SetFlipStateFn = void (*)(void*, const SaveStatePointer*);
using DecrementFn = bool (*)(void*);
using Anm2CopyFn = void (*)(void*, const void*);
using Anm2SwapFn = void (*)(void*, void*);
using Anm2Fn = void (*)(void*);
using SetupGraphicsFn = void (*)(void*, std::uint32_t, std::int32_t,
                                 std::uint32_t, bool);
using LoadGraphicsFn = void (*)(void*);
using PlayFn = void (*)(void*, const char*, bool);
using UpdateFn = void (*)(void*);

struct EngineBindings {
    std::uintptr_t base{};
    AllocateFn allocate{};
    DeallocateFn deallocate{};
    MutexFn mutexCtor{};
    MutexFn mutexInit{};
    CanRerollFn canReroll{};
    RngCtorFn rngCtor{};
    RngNextFn rngNext{};
    RngDtorFn rngDtor{};
    SeededCollectibleFn seededCollectible{};
    SetFlipStateFn setFlipState{};
    DecrementFn decrementReference{};
    Anm2CopyFn copyAnm2{};
    Anm2SwapFn swapAnm2{};
    Anm2Fn resetAnm2{};
    Anm2Fn destroyAnm2{};
    SetupGraphicsFn setupGraphics{};
    LoadGraphicsFn loadGraphics{};
    PlayFn play{};
    UpdateFn update{};
};

constexpr std::array<std::uint8_t, 16> kNewGuard = {
    0x70,0x21,0x00,0xd0,0x11,0x82,0x46,0xf9,
    0x10,0x02,0x34,0x91,0x20,0x02,0x1f,0xd6};
constexpr std::array<std::uint8_t, 16> kDeleteGuard = {
    0x70,0x21,0x00,0xd0,0x11,0x7a,0x46,0xf9,
    0x10,0xc2,0x33,0x91,0x20,0x02,0x1f,0xd6};
constexpr std::array<std::uint8_t, 16> kMutexCtorGuard = {
    0xfd,0x7b,0xbe,0xa9,0xf3,0x0b,0x00,0xf9,
    0xfd,0x03,0x00,0x91,0xf3,0x03,0x00,0xaa};
constexpr std::array<std::uint8_t, 16> kMutexInitGuard = kMutexCtorGuard;
constexpr std::array<std::uint8_t, 16> kCanRerollGuard = {
    0x09,0x0c,0x47,0x39,0x69,0x00,0x00,0x34,
    0xe0,0x03,0x1f,0x2a,0xc0,0x03,0x5f,0xd6};
constexpr std::array<std::uint8_t, 16> kRngCtorGuard = {
    0xfd,0x7b,0xbe,0xa9,0xf4,0x4f,0x01,0xa9,
    0xfd,0x03,0x00,0x91,0xf4,0x03,0x02,0x2a};
constexpr std::array<std::uint8_t, 16> kRngNextGuard = {
    0xfd,0x7b,0xbe,0xa9,0xf3,0x0b,0x00,0xf9,
    0xfd,0x03,0x00,0x91,0x08,0x00,0x40,0xb9};
constexpr std::array<std::uint8_t, 16> kRngDtorGuard = {
    0xc0,0x03,0x5f,0xd6,0x01,0x00,0x00,0xb9,
    0xe8,0x32,0x00,0xf0,0x08,0x65,0x41,0xf9};
constexpr std::array<std::uint8_t, 16> kSeededCollectibleGuard = {
    0xfd,0x7b,0xbd,0xa9,0xf6,0x57,0x01,0xa9,
    0xfd,0x03,0x00,0x91,0xf4,0x4f,0x02,0xa9};
constexpr std::array<std::uint8_t, 16> kSetFlipStateGuard = {
    0xff,0x03,0x01,0xd1,0xfd,0x7b,0x01,0xa9,
    0xfd,0x43,0x00,0x91,0xf5,0x13,0x00,0xf9};
constexpr std::array<std::uint8_t, 16> kDecrementGuard = {
    0xfd,0x7b,0xbe,0xa9,0xf4,0x4f,0x01,0xa9,
    0xfd,0x03,0x00,0x91,0x14,0x40,0x00,0x91};
constexpr std::array<std::uint8_t, 16> kCopyGuard = {
    0xfd,0x7b,0xbb,0xa9,0xfa,0x67,0x01,0xa9,
    0xfd,0x03,0x00,0x91,0xf8,0x5f,0x02,0xa9};
constexpr std::array<std::uint8_t, 16> kSwapGuard = {
    0xff,0x83,0x01,0xd1,0xfd,0x7b,0x03,0xa9,
    0xfd,0xc3,0x00,0x91,0xf6,0x57,0x04,0xa9};
constexpr std::array<std::uint8_t, 16> kResetGuard = {
    0xfd,0x7b,0xbc,0xa9,0xf8,0x5f,0x01,0xa9,
    0xfd,0x03,0x00,0x91,0xf6,0x57,0x02,0xa9};
constexpr std::array<std::uint8_t, 16> kDestroyGuard = {
    0xfd,0x7b,0xbe,0xa9,0xf3,0x0b,0x00,0xf9,
    0xfd,0x03,0x00,0x91,0xf3,0x03,0x00,0xaa};
constexpr std::array<std::uint8_t, 16> kSetupGraphicsGuard = {
    0xff,0x43,0x02,0xd1,0xfd,0x7b,0x04,0xa9,
    0xfd,0x03,0x01,0x91,0xf9,0x2b,0x00,0xf9};
constexpr std::array<std::uint8_t, 16> kLoadGraphicsGuard = {
    0xe1,0x03,0x1f,0x2a,0x60,0x8e,0x19,0x14,
    0xfd,0x7b,0xbe,0xa9,0xf4,0x4f,0x01,0xa9};
constexpr std::array<std::uint8_t, 16> kPlayGuard = {
    0xfd,0x7b,0xbd,0xa9,0xf6,0x57,0x01,0xa9,
    0xfd,0x03,0x00,0x91,0xf4,0x4f,0x02,0xa9};
constexpr std::array<std::uint8_t, 16> kUpdateGuard = {
    0xe8,0x0f,0x1e,0xfc,0xfd,0xfb,0x00,0xa9,
    0xfd,0x23,0x00,0x91,0xf3,0x0f,0x00,0xf9};

EngineBindings g_Engine{};
NativeBindings g_Bindings{};
std::uintptr_t g_ResolvedBase{};
bool g_Resolved{};

template <class Fn>
bool ResolveOne(std::uintptr_t base, std::uintptr_t offset, const std::uint8_t* guard,
                Fn* output) noexcept {
    if (base == 0 || output == nullptr ||
        !engine_call::VerifyEntryBytes(base + offset, guard, 16,
                                       engine_memory::EngineMemoryReadable)) {
        return false;
    }
    *output = engine_call::AsFunction<Fn>(base + offset);
    return true;
}

std::uint32_t NextFlipSeed(std::uint32_t seed) noexcept {
    alignas(8) std::array<unsigned char, kRngObjectSize> rng{};
    g_Engine.rngCtor(rng.data(), seed, 39);
    const auto result = g_Engine.rngNext(rng.data());
    g_Engine.rngDtor(rng.data());
    return result;
}

std::int32_t GetSeededCollectible(void* room, std::uint32_t seed) noexcept {
    return g_Engine.seededCollectible(room, seed, true);
}

void SetFlipState(void* pickup, const SaveStatePointer& value) noexcept {
    g_Engine.setFlipState(pickup, &value);
}

bool DecrementReference(void* reference) noexcept {
    return g_Engine.decrementReference(reference);
}

bool ResolveNativeBindings() noexcept {
    const auto base = LuaRuntime::EngineModuleBase();
    if (base == 0) {
        return false;
    }
    if (g_Resolved && g_ResolvedBase == base) {
        return true;
    }
    g_Resolved = false;
    g_ResolvedBase = base;

    EngineBindings engine{};
    engine.base = base;
    // Sprite entries are already resolved and verified by the private binding
    // provider. Reuse that capability rather than duplicating its addresses.
    engine.loadGraphics=LuaRuntime::SpriteLoadGraphicsThunk();
    engine.play=LuaRuntime::SpritePlayThunk();
    if(!engine.loadGraphics||!engine.play||
       !engine_call::VerifyEntryBytes(engine_call::AddressOfFunction(engine.loadGraphics),
           kLoadGraphicsGuard.data(),kLoadGraphicsGuard.size(),engine_memory::EngineMemoryReadable)||
       !engine_call::VerifyEntryBytes(engine_call::AddressOfFunction(engine.play),
           kPlayGuard.data(),kPlayGuard.size(),engine_memory::EngineMemoryReadable))return false;
    if (!ResolveOne(base, 0x66fb30, kNewGuard.data(), &engine.allocate) ||
        !ResolveOne(base, 0x66fb10, kDeleteGuard.data(), &engine.deallocate) ||
        !ResolveOne(base, 0x51fc40, kMutexCtorGuard.data(), &engine.mutexCtor) ||
        !ResolveOne(base, 0x51fd08, kMutexInitGuard.data(), &engine.mutexInit) ||
        !ResolveOne(base, 0x26afa8, kCanRerollGuard.data(), &engine.canReroll) ||
        !ResolveOne(base, 0x44e360, kRngCtorGuard.data(), &engine.rngCtor) ||
        !ResolveOne(base, 0x44e464, kRngNextGuard.data(), &engine.rngNext) ||
        !ResolveOne(base, 0x44e3bc, kRngDtorGuard.data(), &engine.rngDtor) ||
        !ResolveOne(base, 0x4527ec, kSeededCollectibleGuard.data(),
                    &engine.seededCollectible) ||
        !ResolveOne(base, 0x26b874, kSetFlipStateGuard.data(), &engine.setFlipState) ||
        !ResolveOne(base, 0x2779dc, kDecrementGuard.data(), &engine.decrementReference) ||
        !ResolveOne(base, 0x6778, kCopyGuard.data(), &engine.copyAnm2) ||
        !ResolveOne(base, 0x6cd0, kSwapGuard.data(), &engine.swapAnm2) ||
        !ResolveOne(base, 0x65b8, kResetGuard.data(), &engine.resetAnm2) ||
        !ResolveOne(base, 0x71a4, kDestroyGuard.data(), &engine.destroyAnm2) ||
        !ResolveOne(base, 0x26c3ec, kSetupGraphicsGuard.data(), &engine.setupGraphics) ||
        !ResolveOne(base, 0x86bc, kUpdateGuard.data(), &engine.update)) {
        return false;
    }
    if (!engine_memory::EngineMemoryReadable(base + kReferenceCountBaseVtableOffset, 16) ||
        !engine_memory::EngineMemoryReadable(base + kEntitySaveStateReferenceVtableOffset, 16)) {
        return false;
    }

    g_Engine = engine;
    g_Bindings = {};
    g_Bindings.canReroll = engine.canReroll;
    g_Bindings.allocate = engine.allocate;
    g_Bindings.deallocate = engine.deallocate;
    g_Bindings.mutexCtor = engine.mutexCtor;
    g_Bindings.mutexInit = engine.mutexInit;
    g_Bindings.nextSeed = NextFlipSeed;
    g_Bindings.seededCollectible = GetSeededCollectible;
    g_Bindings.setFlipState = SetFlipState;
    g_Bindings.decrementReference = DecrementReference;
    g_Bindings.copyAnm2 = engine.copyAnm2;
    g_Bindings.swapAnm2 = engine.swapAnm2;
    g_Bindings.resetAnm2 = engine.resetAnm2;
    g_Bindings.destroyAnm2 = engine.destroyAnm2;
    g_Bindings.setupCollectibleGraphics = engine.setupGraphics;
    g_Bindings.loadGraphics = engine.loadGraphics;
    g_Bindings.play = engine.play;
    g_Bindings.update = engine.update;
    g_Resolved = true;
    return true;
}
#else
NativeBindings g_TestBindings{};

const NativeBindings& CurrentBindings() noexcept {
    return g_TestBindings;
}
#endif

std::uintptr_t ReadGameRoom() noexcept {
    return ReadCurrentRoom();
}

bool InitializeStateFields(void* state, std::uint32_t type, std::uint32_t variant,
                           std::int32_t collectible, std::uint32_t seed) noexcept {
    if (state == nullptr) {
        return false;
    }
    std::memset(state, 0, kEntitySaveStateSize);
    PutCandidate(state, kEntitySaveStateTypeOffset, type);
    PutCandidate(state, kEntitySaveStateVariantOffset, variant);
    PutCandidate(state, kEntitySaveStateSubtypeOffset, collectible);
    PutCandidate(state, 0x18, std::uint64_t{UINT64_MAX});
    PutCandidate(state, kEntitySaveStateInitSeedOffset, seed);
    PutCandidate(state, 0x44, std::uint32_t{0x42700000U});
    PutCandidate(state, 0x48, std::uint32_t{0x3f800000U});
    PutCandidate(state, 0x50, std::uint8_t{1});
    return true;
}

bool InitializeReference(void* reference, std::uintptr_t base, void* state,
                         const NativeBindings& bindings) noexcept {
    if (reference == nullptr || base == 0) {
        return false;
    }
    std::memset(reference, 0, kReferenceCountSize);
    PutCandidate(reference, 0, base + kReferenceCountBaseVtableOffset);
    PutCandidate(reference, kReferenceCountOffset, kReferenceCountInitial);
    bindings.mutexCtor(static_cast<unsigned char*>(reference) + 0x10);
    bindings.mutexInit(static_cast<unsigned char*>(reference) + 0x10);
    PutCandidate(reference, 0, base + kEntitySaveStateReferenceVtableOffset);
    PutCandidate(reference, kReferenceStateOffset, state);
    return true;
}

bool AllBindingsPresent(const NativeBindings& bindings, bool setupGraphics,
                        bool needsRoom) noexcept {
    if (!bindings.canReroll || !bindings.allocate || !bindings.deallocate ||
        !bindings.mutexCtor || !bindings.mutexInit || !bindings.nextSeed ||
        !bindings.setFlipState || !bindings.decrementReference ||
        !bindings.resetAnm2) {
        return false;
    }
    if (needsRoom && !bindings.seededCollectible) {
        return false;
    }
    if (setupGraphics && (!bindings.copyAnm2 || !bindings.swapAnm2 ||
                         !bindings.destroyAnm2 || !bindings.setupCollectibleGraphics ||
                         !bindings.loadGraphics || !bindings.play || !bindings.update)) {
        return false;
    }
    return true;
}

}  // namespace

InitResult InitializeFlipState(void* pickup, std::int32_t collectible,
                               bool setupGraphics) noexcept {
    if (pickup == nullptr) {
        return InitResult::BindingUnavailable;
    }

    std::uint32_t type = 0;
    std::uint32_t variant = 0;
    std::uint32_t initSeed = 0;
    const auto pickupAddress = engine_memory::AddressOf(pickup);
    if (!engine_memory::ReadField(pickupAddress, kEntityTypeOffset, &type,
                                  engine_memory::EngineMemoryReadable) ||
        !engine_memory::ReadField(pickupAddress, kEntityVariantOffset, &variant,
                                  engine_memory::EngineMemoryReadable) ||
        !engine_memory::ReadField(pickupAddress, kEntityInitSeedOffset, &initSeed,
                                  engine_memory::EngineMemoryReadable) ||
        variant != kPickupVariantCollectible) {
        return InitResult::Ineligible;
    }

#if defined(__SWITCH__)
    if (!ResolveNativeBindings()) {
        return InitResult::BindingUnavailable;
    }
    const auto& bindings = g_Bindings;
    const auto base = g_Engine.base;
#else
    const auto& bindings = CurrentBindings();
    const auto base = LuaRuntime::EngineModuleBase();
#endif
    if (!AllBindingsPresent(bindings, setupGraphics, collectible == 0)) {
        return InitResult::BindingUnavailable;
    }
    if (!bindings.canReroll(pickup)) {
        return InitResult::Ineligible;
    }

    const auto primary = engine_memory::AddressOf(pickup) + kEntitySpriteOffset;
    const auto alternate = engine_memory::AddressOf(pickup) + kPickupAltSpriteOffset;
    if (!engine_memory::EngineMemoryWritable(
            engine_memory::AddressOf(pickup) + kPickupFlipStateOffset, 16) ||
        !engine_memory::EngineMemoryWritable(alternate, kAnm2Size)) {
        return InitResult::BindingUnavailable;
    }

    std::uintptr_t room = 0;
    char animationName[kAnimationNameCapacity]{};
    if (setupGraphics) {
        if (!engine_memory::EngineMemoryReadable(primary, kAnm2Size) ||
            !ReadFirstAnimationName(primary, animationName, sizeof(animationName))) {
            return InitResult::BindingUnavailable;
        }
    }
    if (collectible == 0) {
        room = ReadGameRoom();
        if (room == 0) {
            return InitResult::RoomUnavailable;
        }
    }

    const auto seed = bindings.nextSeed(initSeed);
    const auto resolvedCollectible = collectible == 0
        ? bindings.seededCollectible(engine_memory::AsObject(room), seed)
        : collectible;

    auto* state = static_cast<unsigned char*>(bindings.allocate(kEntitySaveStateSize));
    if (state == nullptr) {
        return InitResult::AllocationFailed;
    }
    if (!InitializeStateFields(state, type, variant, resolvedCollectible, seed)) {
        bindings.deallocate(state);
        return InitResult::AllocationFailed;
    }

    auto* reference = static_cast<unsigned char*>(bindings.allocate(kReferenceCountSize));
    if (reference == nullptr) {
        bindings.deallocate(state);
        return InitResult::AllocationFailed;
    }
    if (!InitializeReference(reference, base, state, bindings)) {
        bindings.deallocate(reference);
        bindings.deallocate(state);
        return InitResult::AllocationFailed;
    }

    const SaveStatePointer value{state, reference};
    bindings.setFlipState(pickup, value);
    // SetFlipState keeps one reference in the pickup. Drop the caller's temporary
    // reference after the native swap, exactly as SmartPointer's destructor does.
    static_cast<void>(bindings.decrementReference(reference));

    bindings.resetAnm2(engine_memory::AsObject(alternate));
    if (setupGraphics) {
        alignas(16) std::array<unsigned char, kAnm2Size> copied{};
        bindings.copyAnm2(copied.data(), engine_memory::AsObject(primary));
        bindings.swapAnm2(engine_memory::AsObject(alternate), copied.data());
        bindings.setupCollectibleGraphics(
            engine_memory::AsObject(alternate), 1, resolvedCollectible, seed, false);
        bindings.loadGraphics(engine_memory::AsObject(alternate));
        bindings.play(engine_memory::AsObject(alternate), animationName, true);
        bindings.update(engine_memory::AsObject(alternate));
        bindings.destroyAnm2(copied.data());
    }
    return InitResult::Success;
}

#if !defined(__SWITCH__)
void SetNativeTestBindings(NativeBindings bindings) noexcept {
    g_TestBindings = bindings;
}
#endif

}  // namespace isaac::runtime::pickup_flip
