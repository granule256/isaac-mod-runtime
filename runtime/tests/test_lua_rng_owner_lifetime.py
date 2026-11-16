"""Borrowed player RNG lifetimes follow owner/container state, not registry membership."""

import subprocess
import tempfile
import unittest
from pathlib import Path

from .test_support import build_lua_harness
from . import test_lua_batch341_field_rows as fixture


MAIN = r'''
#include "interfaces/lua/isaac_api.hpp"

void HostSetSeed(void* object, std::uint32_t seed, std::uint32_t shift) {
    const std::uint32_t fields[4] = {seed, shift, shift + 1, shift + 2};
    std::memcpy(object, fields, sizeof(fields));
}

void HostNext(void* object) {
    std::uint32_t seed = 0;
    std::memcpy(&seed, object, sizeof(seed));
    ++seed;
    std::memcpy(object, &seed, sizeof(seed));
}

unsigned g_NativeFrame = 0;

GameIsPausedObservation ObserveGameIsPaused(uintptr_t, uintptr_t) {
    return GameIsPausedObservation::ThunkUnavailable;
}

bool Snapshot(isaac::runtime::ManagedUpdateSnapshot* out) noexcept {
    out->game = AddressOf(g_GameBytes);
    out->frame = ++g_NativeFrame;
    return true;
}

GameRoomObservation ReadCurrentGameRoom(uintptr_t, void** room) {
    if (room == nullptr) return GameRoomObservation::RoomNull;
    *room = nullptr;
    return GameRoomObservation::GameNull;
}

int main() {
    static_cast<void>(&WriteIsInvincible);
    static_cast<void>(&ReadIsInvincible);
    static_cast<void>(&WriteMaxDistance);
    static_cast<void>(&ReadMaxDistance);
    PublishFakeGame(0);
    WriteAt<std::uint8_t>(g_PlayerBytes, kEntityExistsOffset, 1);

    std::vector<unsigned char> rngVector(3 * kEntityPlayerRngVectorStride, 0);
    WriteAt<std::uint32_t>(rngVector, 2 * kEntityPlayerRngVectorStride, 123);
    WriteAt<std::uintptr_t>(g_PlayerBytes, kEntityPlayerCollectibleRngVectorOffset,
                            AddressOf(rngVector));
    WriteAt<std::uintptr_t>(g_PlayerBytes,
                            kEntityPlayerCollectibleRngVectorOffset + sizeof(std::uintptr_t),
                            AddressOf(rngVector) + rngVector.size());

    LuaRuntime::SetGameBindings(AddressOf(g_OwnerSlotBytes), 0x2222);
    LuaRuntime::SetRngBindings(reinterpret_cast<std::uintptr_t>(&HostSetSeed),
                               reinterpret_cast<std::uintptr_t>(&HostNext));
    LuaRuntime::ObserveGameThread();
    isaac::runtime::SetManagedUpdateSnapshotReaderForTest(Snapshot);

    const char* script = R"lua(
local mod = RegisterMod('rng-owner-lifetime', 1)
local step = 0
local saved
mod:AddCallback(ModCallbacks.MC_POST_UPDATE, function()
    step = step + 1
    if step == 1 then
        saved = Isaac.GetPlayer(0):GetCollectibleRNG(2)
        assert(saved and saved:GetSeed() == 123)
    elseif step == 2 then
        -- MC_POST_ENTITY_REMOVE ordering can retire registry membership first.
        assert(saved:GetSeed() == 123)
        saved:Next()
        assert(saved:GetSeed() == 124)
    elseif step == 3 then
        assert(not pcall(function() return saved:GetSeed() end))
    elseif step == 4 then
        assert(not pcall(function() return saved:GetSeed() end))
    end
end)
)lua";

    if (LuaRuntime::InitializeFromBuffer(script, std::strlen(script),
                                         "@rng-owner-lifetime.lua") !=
        LuaRuntime::LuaInitResult::Success) {
        return 1;
    }
    auto run = []() {
        LuaRuntime::DispatchPostUpdate();
        if (!LuaRuntime::TakeCallbackError()) return true;
        LuaRuntime::LuaErrorHistoryEntryView entries[4]{};
        const auto count = LuaRuntime::CopyLuaErrorHistory(entries, 4);
        for (std::size_t i = 0; i < count; ++i) std::printf("%s\n", entries[i].text);
        return false;
    };

    if (!run()) return 2;

    // The owner is no longer discoverable through Game's player registry, but it
    // still exists and still owns the same RNG vector.
    WriteAt<std::uintptr_t>(g_PlayerArrayBytes, 0, 0);
    if (!run()) return 3;

    // Re-adding the owner must not make an old vector pointer valid after the
    // owning vector reallocates.
    WriteAt<std::uintptr_t>(g_PlayerArrayBytes, 0, AddressOf(g_PlayerBytes));
    std::vector<unsigned char> replacement = rngVector;
    WriteAt<std::uintptr_t>(g_PlayerBytes, kEntityPlayerCollectibleRngVectorOffset,
                            AddressOf(replacement));
    WriteAt<std::uintptr_t>(g_PlayerBytes,
                            kEntityPlayerCollectibleRngVectorOffset + sizeof(std::uintptr_t),
                            AddressOf(replacement) + replacement.size());
    if (!run()) return 4;

    WriteAt<std::uintptr_t>(g_PlayerBytes, kEntityPlayerCollectibleRngVectorOffset,
                            AddressOf(rngVector));
    WriteAt<std::uintptr_t>(g_PlayerBytes,
                            kEntityPlayerCollectibleRngVectorOffset + sizeof(std::uintptr_t),
                            AddressOf(rngVector) + rngVector.size());
    WriteAt<std::uint8_t>(g_PlayerBytes, kEntityExistsOffset, 0);
    if (!run()) return 5;
    return 0;
}
'''


class RngOwnerLifetimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="isaac-rng-owner-lifetime-")
        source = fixture.HARNESS[:fixture.HARNESS.index("GameRoomObservation ReadCurrentGameRoom(")]
        cls.binary = build_lua_harness(
            source_root=fixture.SOURCE,
            workdir=Path(cls.temporary.name) / "harness",
            harness_source=source + MAIN,
        )

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def test_removed_registry_entry_does_not_expire_live_owner_rng(self):
        result = subprocess.run([str(self.binary)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
