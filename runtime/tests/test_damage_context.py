"""Damage context snapshots preserve native values and real EntityRefs."""
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "runtime/source"
UNITS = ROOT / "runtime/src"

# The real helper is exercised through the public scope and callback types.
DRIVER = r'''
#include "player_damage_internal_hook.hpp"
#include "damage_context.hpp"
#include <array>
#include <cassert>
#include <cstdint>
#include <cstring>
#include <memory>
#include <vector>

using namespace isaac::runtime;

static bool preCalled{};
static bool cancelPre{};
static bool fakePre{};
static bool replayResult{};
static unsigned replayCalls{};
static unsigned postCalls{};
static damage::Values preValue{};
static damage::Values postValue{};
static std::uintptr_t expectedSource{};

static bool Replay(void*) { ++replayCalls; return replayResult; }
static bool Pre(damage::Values& values) {
    preCalled = true;
    preValue = values;
    if (fakePre) {
        values.playerDamage = 0;
        values.amount = 0.0F;
        values.damageFlags = 1ULL << 21;
        values.countdown = 41;
    } else {
        values.playerDamage = 6;
        values.amount = 6.0F;
        values.damageFlags = 0x2000000000000001ULL;
    }
    return cancelPre;
}
static void Post(const damage::Values& values) {
    ++postCalls;
    postValue = values;
}

alignas(16) static std::array<unsigned char, 0x200> player{};
alignas(16) static std::array<unsigned char, 0x100> sourceRef{};
alignas(16) static std::array<unsigned char, 0x400> extraSource{};

template<class T> void Put(void* object, std::size_t offset, T value) {
    std::memcpy(static_cast<unsigned char*>(object) + offset, &value, sizeof(value));
}
static void SetIdentity(void* object, std::uint32_t type, std::uint32_t variant,
                        std::uintptr_t entity) {
    Put(object, 0x00, type);
    Put(object, 0x04, variant);
    Put(object, 0x28, entity);
}

static void RunOne(bool whitefire, bool cancel, bool replay) {
    preCalled = false;
    fakePre = false;
    preValue = {};
    postValue = {};
    replayCalls = 0;
    postCalls = 0;
    cancelPre = cancel;
    replayResult = replay;
    const auto playerAddress = reinterpret_cast<std::uintptr_t>(player.data());
    const auto sourceAddress = reinterpret_cast<std::uintptr_t>(sourceRef.data());
    const auto extraAddress = reinterpret_cast<std::uintptr_t>(extraSource.data());
    expectedSource = sourceAddress;
    SetIdentity(sourceRef.data(), whitefire ? 33U : 3U, whitefire ? 4U : 0U, playerAddress);
    Put(extraSource.data(), 0x38, std::uint32_t{10});
    Put(extraSource.data(), 0x3c, std::uint32_t{2});
    Put(extraSource.data(), 0x44, std::int32_t{20});
    Put(extraSource.data(), 0x48, std::uint32_t{21});
    Put(extraSource.data(), 0x310, 4.5F);
    Put(extraSource.data(), 0x314, 5.5F);
    Put(extraSource.data(), 0x334, 7.5F);
    Put(extraSource.data(), 0x338, 8.5F);
    Put(extraSource.data(), 0x1b8, std::uint64_t{0x0040000020000100ULL});
    std::array<unsigned char, 0x80> stack{};
    Put(stack.data(), 0x4c, std::int32_t{3});

    PlayerDamageCallScope scope(playerAddress, sourceAddress, 17);
    damage::ExtraSourceScope extra(sourceAddress, extraAddress);
    assert(extra.Valid());
    assert(damage::FindExtraSource(sourceAddress) == extraAddress);
    assert(scope.SetExtraSourceEntity(extraAddress));
    relay::InternalHookContext context{};
    context.x[0] = playerAddress;
    context.x[19] = playerAddress;
    context.x[20] = 0x10000000003ULL;
    context.x[22] = sourceAddress;
    context.originalSp = reinterpret_cast<std::uintptr_t>(stack.data());
    PlayerDamageNativeBindings native{Replay, nullptr, Pre, Post};
    const auto result = PlayerDamageInternalCallback(
        *reinterpret_cast<relay::InternalHookContext*>(&context), &native);
    assert(result == (cancel ? 1U : 0U));
    if (!cancel) {
        assert(preCalled);
        assert(preValue.extraSourceRef != 0);
        assert(*reinterpret_cast<std::uintptr_t*>(
            reinterpret_cast<unsigned char*>(preValue.extraSourceRef) + 0x28) ==
            extraAddress);
        assert(context.x[20] == 0x2000000000000001ULL);
        assert(reinterpret_cast<std::int32_t*>(stack.data() + 0x4c)[0] == 6);
    }
    DispatchPlayerDamagePost(!cancel, native);
    if (cancel || replay) {
        assert(postCalls == 0);
    } else if (whitefire) {
        assert(postCalls == 0);
    } else {
        assert(postCalls == 1);
        assert(postValue.playerDamage == 6 && postValue.amount == 6.0F);
        assert(postValue.sourceRef != 0 && postValue.extraSourceRef != 0);
        assert(*reinterpret_cast<std::uintptr_t*>(
            reinterpret_cast<unsigned char*>(postValue.extraSourceRef) + 0x28) ==
            extraAddress);
        const auto* extraRef = reinterpret_cast<const unsigned char*>(postValue.extraSourceRef);
        assert(*reinterpret_cast<const std::int32_t*>(extraRef + 0x08) == 20);
        assert(*reinterpret_cast<const std::uint32_t*>(extraRef + 0x0c) == 21);
        assert(*reinterpret_cast<const float*>(extraRef + 0x10) == 4.5F);
        assert(*reinterpret_cast<const float*>(extraRef + 0x14) == 5.5F);
        assert(*reinterpret_cast<const float*>(extraRef + 0x18) == 7.5F);
        assert(*reinterpret_cast<const float*>(extraRef + 0x1c) == 8.5F);
        assert(*reinterpret_cast<const std::uint32_t*>(extraRef + 0x20) == 7);
    }
}

static void RunPlayerFake() {
    preCalled = false;
    fakePre = true;
    postCalls = 0;
    cancelPre = false;
    replayResult = false;
    const auto playerAddress = reinterpret_cast<std::uintptr_t>(player.data());
    const auto sourceAddress = reinterpret_cast<std::uintptr_t>(sourceRef.data());
    SetIdentity(sourceRef.data(), 3, 0, playerAddress);
    std::array<unsigned char, 0x80> stack{};
    Put(stack.data(), 0x4c, std::int32_t{3});
    PlayerDamageCallScope scope(playerAddress, sourceAddress, 17);
    relay::InternalHookContext context{};
    context.x[0] = playerAddress;
    context.x[19] = playerAddress;
    context.x[20] = 0;
    context.x[22] = sourceAddress;
    context.originalSp = reinterpret_cast<std::uintptr_t>(stack.data());
    PlayerDamageNativeBindings native{Replay, nullptr, Pre, Post};
    assert(PlayerDamageInternalCallback(context, &native) == 0);
    assert(preCalled && preValue.playerDamage == 3);
    assert(*reinterpret_cast<std::int32_t*>(stack.data() + 0x4c) == 0);
    assert(context.x[20] == (1ULL << 21));
    postCalls = 0;
    DispatchPlayerDamagePost(true, native);
    assert(postCalls == 1);
    assert(postValue.playerDamage == 0 && postValue.countdown == 41);
    fakePre = false;
}

int main() {
    damage::SetHostReadableCheckForTest(
        [](std::uintptr_t, std::size_t) { return true; });
    RunOne(false, false, false);
    RunOne(false, true, false);
    RunOne(true, false, false);
    RunOne(false, false, true);
    RunPlayerFake();
    assert(damage::CurrentScope() == nullptr);

    // Same source: the newest nested scope wins, then unwinds to the previous one.
    alignas(16) std::array<unsigned char, 0x40> nestedSource{};
    alignas(16) std::array<unsigned char, 0x40> nestedExtraA{};
    alignas(16) std::array<unsigned char, 0x40> nestedExtraB{};
    const auto nestedPlayer = reinterpret_cast<std::uintptr_t>(player.data());
    SetIdentity(nestedSource.data(), 3, 0, nestedPlayer);
    SetIdentity(nestedExtraA.data(), 10, 0,
                reinterpret_cast<std::uintptr_t>(nestedExtraA.data()));
    SetIdentity(nestedExtraB.data(), 10, 0,
                reinterpret_cast<std::uintptr_t>(nestedExtraB.data()));
    const auto nestedSourceAddress =
        reinterpret_cast<std::uintptr_t>(nestedSource.data());
    const auto nestedExtraAAddress =
        reinterpret_cast<std::uintptr_t>(nestedExtraA.data());
    const auto nestedExtraBAddress =
        reinterpret_cast<std::uintptr_t>(nestedExtraB.data());
    {
        damage::ExtraSourceScope outer(nestedSourceAddress, nestedExtraAAddress);
        assert(outer.Valid());
        assert(damage::FindExtraSource(nestedSourceAddress) == nestedExtraAAddress);
        {
            damage::ExtraSourceScope inner(nestedSourceAddress, nestedExtraBAddress);
            assert(inner.Valid());
            assert(damage::FindExtraSource(nestedSourceAddress) == nestedExtraBAddress);
        }
        assert(damage::FindExtraSource(nestedSourceAddress) == nestedExtraAAddress);
    }
    assert(damage::FindExtraSource(nestedSourceAddress) == 0);

    // The 16 inline slots spill into a fixed region. Exhaustion is queryable and
    // cannot be mistaken for a valid "no ExtraSource" result.
    damage::ClearExtraSourceOverflow();
    std::array<std::array<unsigned char, 0x40>, damage::kExtraSourceCapacity>
        sourceRefs{};
    std::vector<std::unique_ptr<damage::ExtraSourceScope>> scopes;
    scopes.reserve(damage::kExtraSourceCapacity);
    for (std::size_t i = 0; i < damage::kExtraSourceCapacity; ++i) {
        SetIdentity(sourceRefs[i].data(), 3, 0, nestedPlayer);
        scopes.push_back(std::make_unique<damage::ExtraSourceScope>(
            reinterpret_cast<std::uintptr_t>(sourceRefs[i].data()),
            nestedPlayer + i + 1));
        assert(scopes.back()->Valid());
    }
    alignas(16) std::array<unsigned char, 0x40> overflowSource{};
    SetIdentity(overflowSource.data(), 3, 0, nestedPlayer);
    const auto overflowSourceAddress =
        reinterpret_cast<std::uintptr_t>(overflowSource.data());
    {
        damage::ExtraSourceScope overflow(overflowSourceAddress, nestedPlayer + 1000);
        assert(!overflow.Valid());
        assert(damage::ExtraSourceOverflowed());
        assert(damage::ExtraSourceOverflowedFor(overflowSourceAddress));
        bool lookupOverflow = false;
        assert(damage::FindExtraSource(overflowSourceAddress, &lookupOverflow) == 0);
        assert(lookupOverflow);
    }
    scopes.clear();
    assert(damage::ExtraSourceOverflowed());
    damage::ClearExtraSourceOverflow();
    assert(!damage::ExtraSourceOverflowed());

    // The pre callback may morph/remove the extra entity. MarkAccepted must
    // commit the EntityRef captured before pre, not rebuild it from the entity.
    alignas(16) std::array<unsigned char, 0x40> snapshotSource{};
    alignas(16) std::array<unsigned char, 0x400> snapshotExtra{};
    SetIdentity(snapshotSource.data(), 3, 0, nestedPlayer);
    SetIdentity(snapshotExtra.data(), 10, 2,
                reinterpret_cast<std::uintptr_t>(snapshotExtra.data()));
    Put(snapshotExtra.data(), 0x310, 12.0F);
    Put(snapshotExtra.data(), 0x314, 13.0F);
    Put(snapshotExtra.data(), 0x334, 14.0F);
    Put(snapshotExtra.data(), 0x338, 15.0F);
    Put(snapshotExtra.data(), 0x1b8, std::uint64_t{0x0040000020000100ULL});
    {
        damage::CallScope scope(nestedPlayer,
            reinterpret_cast<std::uintptr_t>(snapshotSource.data()), 17, false);
        assert(scope.SetExtraSourceEntity(
            reinterpret_cast<std::uintptr_t>(snapshotExtra.data())));
        damage::Values before{};
        scope.FillValues(&before);
        assert(before.extraSourceRef != 0);
        Put(snapshotExtra.data(), 0x00, std::uint32_t{99});
        Put(snapshotExtra.data(), 0x04, std::uint32_t{100});
        Put(snapshotExtra.data(), 0x310, 99.0F);
        Put(snapshotExtra.data(), 0x314, 100.0F);
        assert(scope.MarkAccepted(1.0F, 0, 0,
            reinterpret_cast<std::uintptr_t>(snapshotSource.data()), 17,
            reinterpret_cast<std::uintptr_t>(snapshotExtra.data()), 10));
        damage::Values after{};
        assert(scope.TakeAccepted(&after));
        assert(after.extraSourceRef != 0);
        assert(std::memcmp(
            reinterpret_cast<const void*>(before.extraSourceRef),
            reinterpret_cast<const void*>(after.extraSourceRef), 0x30) == 0);
    }

    {
        alignas(16) std::array<std::uint8_t, 0x400> entity{};
        alignas(16) std::array<std::uint8_t, 0x40> ref{};
        Put(entity.data(), 0x38, std::uint32_t{10});
        Put(entity.data(), 0x3c, std::uint32_t{2});
        Put(entity.data(), 0x44, std::int32_t{20});
        Put(entity.data(), 0x48, std::uint32_t{21});
        Put(entity.data(), 0x310, 4.5F);
        Put(entity.data(), 0x314, 5.5F);
        Put(entity.data(), 0x334, 7.5F);
        Put(entity.data(), 0x338, 8.5F);
        Put(entity.data(), 0x1b8, std::uint64_t{0x0040000020000100ULL});
        const auto address = reinterpret_cast<std::uintptr_t>(entity.data());
        assert(damage::BuildEntityReference(address, ref.data()));
        assert(*reinterpret_cast<const std::uint32_t*>(ref.data() + 0x00) == 10);
        assert(*reinterpret_cast<const std::uint32_t*>(ref.data() + 0x04) == 2);
        assert(*reinterpret_cast<const std::int32_t*>(ref.data() + 0x08) == 20);
        assert(*reinterpret_cast<const std::uint32_t*>(ref.data() + 0x0c) == 21);
        assert(*reinterpret_cast<const std::uint32_t*>(ref.data() + 0x20) == 7);
        assert(*reinterpret_cast<const std::uintptr_t*>(ref.data() + 0x28) == address);
    }
    damage::SetHostReadableCheckForTest(nullptr);
    return 0;
}
'''


class DamageContextTests(unittest.TestCase):
    def test_native_values_entityrefs_and_post_gate(self):
        with tempfile.TemporaryDirectory(prefix="damage-context-") as folder:
            work = Path(folder)
            source = work / "driver.cpp"
            source.write_text(DRIVER, encoding="utf-8")
            binary = work / "driver"
            command = [
                "c++", "-std=c++20", "-Wall", "-Wextra", "-Werror",
                f"-I{SOURCE}", f"-I{UNITS}",
                str(source), str(SOURCE / "damage_context.cpp"),
                str(SOURCE / "player_damage_internal_hook.cpp"), "-o", str(binary),
            ]
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            result = subprocess.run([str(binary)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
