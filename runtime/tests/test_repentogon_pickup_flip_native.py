"""Native pickup flip-state factory, SmartPointer ownership, and graphics ABI."""
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

from . import test_support

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "runtime/source"
PICKUP_FLIP = ROOT / "runtime/src/interfaces/lua/pickup_flip_api.cpp"
NRO = (ROOT.parent.parent / "data/games/The Binding of Isaac_ Afterbirth+ 1.7.9b "
       "[010021C000B6A800][v524288][UPD]/Program #0/1/.nro/Repentance.nro")

DRIVER = r'''
#include "interfaces/lua/pickup_flip_api.hpp"
#include "infrastructure/memory/engine_field_access.hpp"
#include "lua_runtime.hpp"
#include "runtime_constants.hpp"

#include <array>
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <vector>

using namespace isaac::runtime;
using namespace isaac::runtime::pickup_flip;

namespace {
constexpr std::uintptr_t kFlipState = 0x610;
constexpr std::uintptr_t kFlipReference = 0x618;
constexpr std::uintptr_t kAltSprite = 0x620;
constexpr std::size_t kStateSize = 0x78;
constexpr std::size_t kControlSize = 0x48;
constexpr std::size_t kAnm2Size = 0x158;

std::vector<unsigned char> module(0x1000);
std::vector<unsigned char> game(0x22000);
std::vector<unsigned char> room(0x100);
std::vector<unsigned char> pickup(0x800);
std::array<unsigned char, 0x150> animation{};
std::uintptr_t roomAddress{};
std::uintptr_t copiedSource{};
std::uintptr_t copiedDestination{};
std::uintptr_t swappedLeft{};
std::uintptr_t swappedRight{};
std::uintptr_t destroyedSprite{};
std::uintptr_t graphicsSprite{};
std::uint32_t graphicsLayer{};
std::int32_t graphicsCollectible{};
std::uint32_t graphicsSeed{};
bool graphicsBlind{true};
char playedName[32]{};
bool playedLoop{};
unsigned canRerollCalls{};
unsigned allocateCalls{};
unsigned nextSeedCalls{};
unsigned seededCalls{};
unsigned setFlipCalls{};
unsigned resetCalls{};
unsigned copyCalls{};
unsigned swapCalls{};
unsigned destroyCalls{};
unsigned setupCalls{};
unsigned loadGraphicsCalls{};
unsigned playCalls{};
unsigned updateCalls{};
unsigned decrementCalls{};
unsigned freedControls{};
std::uint32_t nextSeedInput{};
std::uint32_t nextSeedOutput{};
bool canRerollResult{true};
std::uint32_t excludedRandomPoolRolls{};
std::uint32_t seededInput{};
void* seededRoom{};

template<class T> T At(const void* object, std::size_t offset) {
    T value{};
    std::memcpy(&value, static_cast<const unsigned char*>(object) + offset, sizeof(value));
    return value;
}
template<class T> void Put(void* object, std::size_t offset, const T& value) {
    std::memcpy(static_cast<unsigned char*>(object) + offset, &value, sizeof(value));
}
std::uintptr_t Address(const void* object) {
    return engine_memory::AddressOf(object);
}

std::uint16_t& References(void* control) {
    return *reinterpret_cast<std::uint16_t*>(static_cast<unsigned char*>(control) + 8);
}

bool CanReroll(const void* object) {
    ++canRerollCalls;
    assert(object == pickup.data());
    return canRerollResult;
}
void* Allocate(std::size_t size) {
    ++allocateCalls;
    assert(size == kStateSize || size == kControlSize);
    return std::calloc(1, size);
}
void Deallocate(void* object) {
    std::free(object);
}
void MutexCtor(void*) {}
void MutexInit(void*) {}
std::uint32_t NextSeed(std::uint32_t seed) {
    ++nextSeedCalls;
    nextSeedInput = seed;
    nextSeedOutput = seed ^ 0x9e3779b9U;
    return nextSeedOutput;
}
std::int32_t SeededCollectible(void* roomObject, std::uint32_t seed) {
    ++seededCalls;
    seededRoom = roomObject;
    seededInput = seed;
    return 406;
}
bool Decrement(void* control) {
    ++decrementCalls;
    if (control == nullptr || References(control) == 0) {
        return true;
    }
    --References(control);
    if (References(control) == 0) {
        std::free(At<void*>(control, 0x40));
        std::free(control);
        ++freedControls;
    }
    return true;
}
void SetFlip(void* object, const SaveStatePointer& value) {
    ++setFlipCalls;
    assert(object == pickup.data());
    assert(value.saveState != nullptr && value.reference != nullptr);
    assert(At<void*>(value.reference, 0x40) == value.saveState);

    if (value.reference != nullptr) {
        ++References(value.reference);
    }
    void* oldReference = At<void*>(object, kFlipReference);
    Put(object, kFlipState, value.saveState);
    Put(object, kFlipReference, value.reference);
    if (oldReference != nullptr) {
        Decrement(oldReference);
    }
    ++resetCalls;  // Native SetFlipState resets the alternate pedestal ANM2.
}
void CopyAnm2(void* destination, const void* source) {
    ++copyCalls;
    copiedDestination = Address(destination);
    copiedSource = Address(source);
    Put(destination, 0x150, std::uint32_t{0x7777});
}
void SwapAnm2(void* left, void* right) {
    ++swapCalls;
    swappedLeft = Address(left);
    swappedRight = Address(right);
    std::array<unsigned char, kAnm2Size> temporary{};
    std::memcpy(temporary.data(), left, temporary.size());
    std::memcpy(left, right, temporary.size());
    std::memcpy(right, temporary.data(), temporary.size());
}
void DestroyAnm2(void* object) {
    ++destroyCalls;
    destroyedSprite = Address(object);
    std::memset(object, 0, kAnm2Size);
}
void SetupGraphics(void* sprite, std::uint32_t layer, std::int32_t collectible,
                   std::uint32_t seed, bool blind) {
    ++setupCalls;
    graphicsSprite = Address(sprite);
    graphicsLayer = layer;
    graphicsCollectible = collectible;
    graphicsSeed = seed;
    graphicsBlind = blind;
}
void LoadGraphics(void* sprite) {
    ++loadGraphicsCalls;
    assert(Address(sprite) == Address(static_cast<unsigned char*>(pickup.data()) + kAltSprite));
}
void Play(void*, const char* name, bool loop) {
    ++playCalls;
    std::snprintf(playedName, sizeof(playedName), "%s", name);
    playedLoop = loop;
}
void Update(void* sprite) {
    ++updateCalls;
    assert(Address(sprite) == Address(static_cast<unsigned char*>(pickup.data()) + kAltSprite));
}

NativeBindings Bindings() {
    NativeBindings value{};
    value.canReroll = CanReroll;
    value.allocate = Allocate;
    value.deallocate = Deallocate;
    value.mutexCtor = MutexCtor;
    value.mutexInit = MutexInit;
    value.nextSeed = NextSeed;
    value.seededCollectible = SeededCollectible;
    value.setFlipState = SetFlip;
    value.decrementReference = Decrement;
    value.copyAnm2 = CopyAnm2;
    value.swapAnm2 = SwapAnm2;
    value.resetAnm2 = [](void* object) {
        ++resetCalls;
        assert(object == pickup.data() + kAltSprite);
    };
    value.destroyAnm2 = DestroyAnm2;
    value.setupCollectibleGraphics = SetupGraphics;
    value.loadGraphics = LoadGraphics;
    value.play = Play;
    value.update = Update;
    return value;
}

void ResetRecords() {
    canRerollCalls = allocateCalls = nextSeedCalls = seededCalls = setFlipCalls = 0;
    resetCalls = copyCalls = swapCalls = destroyCalls = setupCalls = 0;
    loadGraphicsCalls = playCalls = updateCalls = decrementCalls = freedControls = 0;
    copiedSource = copiedDestination = swappedLeft = swappedRight = destroyedSprite = 0;
    graphicsSprite = 0;
    graphicsLayer = graphicsCollectible = graphicsSeed = 0;
    graphicsBlind = true;
    playedName[0] = '\0';
    playedLoop = false;
    nextSeedInput = nextSeedOutput = seededInput = 0;
    seededRoom = nullptr;
    excludedRandomPoolRolls = 0;
}

void ClearFlip() {
    void* reference = At<void*>(pickup.data(), kFlipReference);
    if (reference != nullptr) {
        Decrement(reference);
    }
    Put(pickup.data(), kFlipState, static_cast<void*>(nullptr));
    Put(pickup.data(), kFlipReference, static_cast<void*>(nullptr));
}

void ExpectState(std::int32_t collectible, std::uint32_t seed) {
    void* state = At<void*>(pickup.data(), kFlipState);
    void* reference = At<void*>(pickup.data(), kFlipReference);
    assert(state != nullptr && reference != nullptr);
    assert(At<std::uint32_t>(state, 0x00) == 5);
    assert(At<std::uint32_t>(state, 0x04) == 100);
    assert(At<std::int32_t>(state, 0x08) == collectible);
    assert(At<std::uint64_t>(state, 0x18) == UINT64_MAX);
    assert(At<std::uint32_t>(state, 0x34) == seed);
    assert(At<std::uint32_t>(state, 0x44) == 0x42700000U);
    assert(At<std::uint32_t>(state, 0x48) == 0x3f800000U);
    assert(At<std::uint8_t>(state, 0x50) == 1);
    assert(At<void*>(reference, 0x40) == state);
    assert(References(reference) == 1);
}
}  // namespace

int main() {
    const auto gameAddress = engine_memory::AddressOf(game.data());
    roomAddress = Address(room.data());
    Put(game.data(), kGameRoomPointerOffset, roomAddress);
    Put(pickup.data(), 0x00, std::uintptr_t{0});  // No owner path is consulted.
    Put(pickup.data(), kEntityTypeOffset, std::uint32_t{5});
    Put(pickup.data(), kEntityVariantOffset, std::uint32_t{100});
    Put(pickup.data(), kEntityInitSeedOffset, std::uint32_t{0x11223344});
    Put(pickup.data(), kAltSprite + 0x150, std::uint32_t{0x2222});

    unsigned char* primary = pickup.data() + kEntitySpriteOffset;
    Put(primary, kAnim2AnimationArrayOffset, Address(animation.data()));
    Put(primary, kAnim2AnimationCountOffset, std::uint32_t{1});
    animation[0] = 8;  // libc++ short string, length 4.
    std::memcpy(animation.data() + 1, "Idle", 4);

    module.resize(static_cast<std::size_t>(kGameOwnerGlobalSlotOffset + sizeof(std::uintptr_t)));
    Put(module.data(), kGameOwnerGlobalSlotOffset, gameAddress);
    LuaRuntime::SetEngineModuleBase(Address(module.data()));
    SetNativeTestBindings(Bindings());

    ResetRecords();
    assert(InitializeFlipState(pickup.data(), 0, true) == InitResult::Success);
    assert(canRerollCalls == 1);
    assert(allocateCalls == 2 && nextSeedCalls == 1 && seededCalls == 1);
    assert(nextSeedInput == 0x11223344 && nextSeedOutput == (0x11223344U ^ 0x9e3779b9U));
    assert(seededRoom == room.data() && seededInput == nextSeedOutput);
    ExpectState(406, nextSeedOutput);
    assert(setFlipCalls == 1 && resetCalls == 2);
    assert(copyCalls == 1 && copiedSource == Address(primary) &&
           copiedDestination != Address(primary));
    assert(swapCalls == 1 && swappedLeft == Address(pickup.data() + kAltSprite));
    assert(destroyCalls == 1 && destroyedSprite == copiedDestination);
    assert(At<std::uint32_t>(pickup.data(), kAltSprite + 0x150) == 0x7777);
    assert(setupCalls == 1 && loadGraphicsCalls == 1 && playCalls == 1 && updateCalls == 1);
    assert(graphicsSprite == Address(pickup.data() + kAltSprite));
    assert(graphicsLayer == 1 && graphicsCollectible == 406 && graphicsSeed == nextSeedOutput);
    assert(!graphicsBlind && std::strcmp(playedName, "Idle") == 0 && playedLoop);

    ResetRecords();
    ClearFlip();
    ResetRecords();
    assert(InitializeFlipState(pickup.data(), 654, false) == InitResult::Success);
    assert(canRerollCalls == 1 && nextSeedCalls == 1 && seededCalls == 0);
    ExpectState(654, nextSeedOutput);
    assert(copyCalls == 0 && swapCalls == 0 && destroyCalls == 0 && setupCalls == 0);
    assert(loadGraphicsCalls == 0 && playCalls == 0 && updateCalls == 0);

    ResetRecords();
    void* retainedState = At<void*>(pickup.data(), kFlipState);
    void* retainedReference = At<void*>(pickup.data(), kFlipReference);
    canRerollResult = false;
    assert(InitializeFlipState(pickup.data(), 0, true) == InitResult::Ineligible);
    assert(At<void*>(pickup.data(), kFlipState) == retainedState);
    assert(At<void*>(pickup.data(), kFlipReference) == retainedReference);
    assert(allocateCalls == 0 && setFlipCalls == 0 && resetCalls == 0);

    ResetRecords();
    ClearFlip();
    canRerollResult = true;
    Put(pickup.data(), kEntityVariantOffset, std::uint32_t{99});
    assert(InitializeFlipState(pickup.data(), 0, true) == InitResult::Ineligible);
    assert(canRerollCalls == 0 && allocateCalls == 0 && setFlipCalls == 0);
    Put(pickup.data(), kEntityVariantOffset, std::uint32_t{100});

    ResetRecords();
    assert(InitializeFlipState(pickup.data(), 0, false) == InitResult::Success);
    void* firstControl = At<void*>(pickup.data(), kFlipReference);
    assert(References(firstControl) == 1);
    assert(InitializeFlipState(pickup.data(), 321, false) == InitResult::Success);
    assert(freedControls == 1);  // SetFlip released the replaced member reference.
    assert(References(At<void*>(pickup.data(), kFlipReference)) == 1);
    ExpectState(321, nextSeedOutput);

    ClearFlip();
    SetNativeTestBindings({});
    LuaRuntime::SetEngineModuleBase(0);
    return 0;
}
'''


class PickupFlipNativeTests(unittest.TestCase):
    def test_factory_smart_pointer_lifetime_and_graphics_abi(self):
        with tempfile.TemporaryDirectory(prefix="pickup-flip-native-") as folder:
            extra = ()
            if PICKUP_FLIP not in test_support.layered_lua_runtime_sources(SOURCE):
                extra = (PICKUP_FLIP,)
            binary = test_support.build_lua_harness(
                source_root=SOURCE,
                workdir=Path(folder),
                harness_source=DRIVER,
                extra_sources=extra,
            )
            result = subprocess.run([str(binary)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_entry_guards_match_supported_nro(self):
        source = PICKUP_FLIP.read_text(encoding="utf-8")
        guards = {}
        for name, body in re.findall(
            r"constexpr std::array<std::uint8_t, 16> (k\w+Guard)\s*=\s*\{([^}]*)\};",
            source,
        ):
            guards[name] = bytes(int(value, 16) for value in re.findall(r"0x([0-9a-fA-F]{2})", body))
        guards["kMutexInitGuard"] = guards["kMutexCtorGuard"]
        entries = {
            "kNewGuard": 0x66FB30,
            "kDeleteGuard": 0x66FB10,
            "kMutexCtorGuard": 0x51FC40,
            "kMutexInitGuard": 0x51FD08,
            "kCanRerollGuard": 0x26AFA8,
            "kRngCtorGuard": 0x44E360,
            "kRngNextGuard": 0x44E464,
            "kRngDtorGuard": 0x44E3BC,
            "kSeededCollectibleGuard": 0x4527EC,
            "kSetFlipStateGuard": 0x26B874,
            "kDecrementGuard": 0x2779DC,
            "kCopyGuard": 0x6778,
            "kSwapGuard": 0x6CD0,
            "kResetGuard": 0x65B8,
            "kDestroyGuard": 0x71A4,
            "kSetupGraphicsGuard": 0x26C3EC,
            "kUpdateGuard": 0x86BC,
        }
        self.assertTrue(NRO.is_file(), f"missing supported NRO: {NRO}")
        image = NRO.read_bytes()
        from tools.nro_symbols import parse_dynamic_symbols
        _, symbols = parse_dynamic_symbols(image)
        entries["kLoadGraphicsGuard"] = symbols[
            "_ZN15IsaacRepentance4ANM212LoadGraphicsEv"].file_offset
        entries["kPlayGuard"] = symbols[
            "_ZN15IsaacRepentance4ANM24PlayEPKcb"].file_offset
        self.assertIn("LuaRuntime::SpriteLoadGraphicsThunk()", source)
        self.assertIn("LuaRuntime::SpritePlayThunk()", source)
        self.assertEqual(image[0x40:0x54].hex().upper(),
                         "91C73FDD575061318D68886316AFEAC72388B2AB")
        for name, offset in entries.items():
            with self.subTest(entry=name):
                self.assertEqual(guards[name], image[offset:offset + 16])
        self.assertIn("kEntitySaveStateReferenceVtableOffset = 0xa370b0", source)
        self.assertIn("kReferenceCountBaseVtableOffset = 0xa34088", source)


if __name__ == "__main__":
    unittest.main()
