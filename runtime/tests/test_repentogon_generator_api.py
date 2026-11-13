"""Level generator and boss-pool callback views use pinned Switch layouts."""

import subprocess
import tempfile
import unittest
from pathlib import Path

from . import test_support
from .test_repentogon_world_api import BEHAVIOR, SOURCE

EXTRA = r'''
static std::vector<unsigned char> g_GeneratorBytes;
static std::vector<unsigned char> g_GeneratorRoomBytes;
static std::vector<unsigned char> g_DeadEndIndexes;
static std::vector<unsigned char> g_NonDeadEndIndexes;
static std::vector<unsigned char> g_BossPoolBytes;
static std::vector<unsigned char> g_BossEntries;

static void PublishGeneratorFixtures() {
    g_GeneratorBytes.assign(0x400, 0);
    g_GeneratorRoomBytes.assign(0xe0, 0);
    g_DeadEndIndexes.assign(sizeof(std::int32_t), 0);
    g_NonDeadEndIndexes.assign(sizeof(std::int32_t), 0);
    g_BossPoolBytes.assign(0x48, 0);
    g_BossEntries.assign(2 * 0x14, 0);

    const auto generator = AddressOf(g_GeneratorBytes);
    const auto rooms = AddressOf(g_GeneratorRoomBytes);
    const auto room0 = rooms;
    const auto room1 = rooms + 0x60;
    const auto room0Node = rooms + 0xc0;

    WriteAt<std::uintptr_t>(g_GeneratorBytes, 0x368, rooms);
    WriteAt<std::uintptr_t>(g_GeneratorBytes, 0x370, rooms + 0xc0);
    WriteAt<std::uintptr_t>(g_GeneratorBytes, 0x378, rooms + 0xc0);
    WriteAt<std::uintptr_t>(g_GeneratorBytes, 0x380,
                            AddressOf(g_DeadEndIndexes));
    WriteAt<std::uintptr_t>(g_GeneratorBytes, 0x388,
                            AddressOf(g_DeadEndIndexes) + 4);
    WriteAt<std::uintptr_t>(g_GeneratorBytes, 0x390,
                            AddressOf(g_DeadEndIndexes) + 4);
    WriteAt<std::uintptr_t>(g_GeneratorBytes, 0x398,
                            AddressOf(g_NonDeadEndIndexes));
    WriteAt<std::uintptr_t>(g_GeneratorBytes, 0x3a0,
                            AddressOf(g_NonDeadEndIndexes) + 4);
    WriteAt<std::uintptr_t>(g_GeneratorBytes, 0x3a8,
                            AddressOf(g_NonDeadEndIndexes) + 4);

    WriteAt<std::uint32_t>(g_GeneratorRoomBytes, 0x04, 0);
    WriteAt<std::uint32_t>(g_GeneratorRoomBytes, 0x08, 2);
    WriteAt<std::uint32_t>(g_GeneratorRoomBytes, 0x0c, 4);
    WriteAt<std::uint32_t>(g_GeneratorRoomBytes, 0x18, 1);
    WriteAt<std::uint64_t>(g_GeneratorRoomBytes, 0x20, 1);
    WriteAt<std::uintptr_t>(g_GeneratorRoomBytes, 0x38, room0Node);
    WriteAt<std::uintptr_t>(g_GeneratorRoomBytes, 0x40, 0);
    WriteAt<std::uint64_t>(g_GeneratorRoomBytes, 0x48, 1);
    WriteAt<std::uint8_t>(g_GeneratorRoomBytes, 0x54, 0);

    WriteAt<std::uint64_t>(g_GeneratorRoomBytes, room0Node - rooms + 0x00, 0);
    WriteAt<std::uint64_t>(g_GeneratorRoomBytes, room0Node - rooms + 0x08, 0);
    WriteAt<std::uintptr_t>(g_GeneratorRoomBytes, room0Node - rooms + 0x10,
                            room0 + 0x40);
    WriteAt<std::int32_t>(g_GeneratorRoomBytes, room0Node - rooms + 0x1c, 1);

    WriteAt<std::uint32_t>(g_GeneratorRoomBytes, 0x64, 1);
    WriteAt<std::uint32_t>(g_GeneratorRoomBytes, 0x68, 3);
    WriteAt<std::uint32_t>(g_GeneratorRoomBytes, 0x6c, 5);
    WriteAt<std::uint32_t>(g_GeneratorRoomBytes, 0x78, 4);
    WriteAt<std::uint64_t>(g_GeneratorRoomBytes, 0x80, 2);
    WriteAt<std::uintptr_t>(g_GeneratorRoomBytes, 0x98, room1 + 0x40);
    WriteAt<std::uint64_t>(g_GeneratorRoomBytes, 0xa8, 0);
    WriteAt<std::uint8_t>(g_GeneratorRoomBytes, 0xb4, 1);

    WriteAt<std::int32_t>(g_DeadEndIndexes, 0, 1);
    WriteAt<std::int32_t>(g_NonDeadEndIndexes, 0, 0);

    const auto pool = AddressOf(g_BossPoolBytes);
    const auto entries = AddressOf(g_BossEntries);
    const char name[] = "Caves";
    g_BossPoolBytes[0] = static_cast<unsigned char>((sizeof(name) - 1) << 1);
    std::memcpy(g_BossPoolBytes.data() + 1, name, sizeof(name) - 1);
    WriteAt<std::uintptr_t>(g_BossPoolBytes, 0x18, entries);
    WriteAt<std::uintptr_t>(g_BossPoolBytes, 0x20, entries + 2 * 0x14);
    WriteAt<std::uintptr_t>(g_BossPoolBytes, 0x28, entries + 2 * 0x14);
    WriteAt<float>(g_BossPoolBytes, 0x30, 3.5F);
    WriteAt<std::uint32_t>(g_BossPoolBytes, 0x34, 0x12345678U);
    WriteAt<std::int32_t>(g_BossPoolBytes, 0x44, 3700);
    WriteAt<std::int32_t>(g_BossEntries, 0x00, 9);
    WriteAt<float>(g_BossEntries, 0x04, 1.25F);
    WriteAt<float>(g_BossEntries, 0x08, 2.5F);
    WriteAt<std::int32_t>(g_BossEntries, 0x0c, 77);
    WriteAt<std::int32_t>(g_BossEntries, 0x14, 10);
    WriteAt<float>(g_BossEntries, 0x18, 3.25F);
    WriteAt<float>(g_BossEntries, 0x1c, 4.5F);
    WriteAt<std::int32_t>(g_BossEntries, 0x20, 78);
    WriteAt<float>(g_BossEntries, 0x24, 1.0F);
    static_cast<void>(generator);
    static_cast<void>(pool);
}

static void InstallGeneratorBindings(lua_State* state) {
    isaac::runtime::RegisterRepentogonGeneratorViews(state);
    isaac::runtime::PushRepentogonLevelGeneratorHandle(
        state, g_GeneratorBytes.data());
    lua_setglobal(state, "generator");
    isaac::runtime::PushRepentogonLevelGeneratorRoomHandle(
        state, g_GeneratorBytes.data(), g_GeneratorRoomBytes.data());
    lua_setglobal(state, "generatorRoom");
    isaac::runtime::PushRepentogonBossPoolPoolHandle(
        state, g_BossPoolBytes.data());
    lua_setglobal(state, "bossPool");
}
'''

SCRIPT = r'''
local generator = generator
local rooms = generator:GetAllRooms()
assert(#rooms == 2)
assert(rooms[1]:GenerationIndex() == 0)
assert(rooms[1]:Column() == 2)
assert(rooms[1]:Row() == 4)
assert(rooms[1]:Shape() == 1)
assert(rooms[1]:DoorMask() == 1)
assert(rooms[1]:IsDeadEnd() == false)
assert(rooms[1]:Neighbors()[1] == 1)
assert(rooms[2]:GenerationIndex() == 1)
assert(rooms[2]:Column() == 3)
assert(rooms[2]:Row() == 5)
assert(rooms[2]:Shape() == 4)
assert(rooms[2]:DoorMask() == 2)
assert(rooms[2]:IsDeadEnd() == true)
assert(#rooms[2]:Neighbors() == 0)
assert(generator:GetDeadEnds()[1]:GenerationIndex() == 1)
assert(generator:GetNonDeadEnds()[1]:GenerationIndex() == 0)

assert(generatorRoom:GenerationIndex() == 0)
assert(generatorRoom:Column() == 2)
assert(generatorRoom:Row() == 4)
assert(generatorRoom:Shape() == 1)
assert(generatorRoom:DoorMask() == 1)
assert(generatorRoom:Neighbors()[1] == 1)
assert(generatorRoom:IsDeadEnd() == false)

assert(bossPool:GetName() == "Caves")
assert(bossPool:GetWeight() == 3.5)
assert(bossPool:GetRNG():GetSeed() == 0x12345678)
assert(bossPool:GetDoubleTroubleRoomID() == 3700)
local entries = bossPool:GetEntries()
assert(#entries == 2 and entries[1].bossID == 9 and entries[1].weight == 2.5)
assert(entries[1].weightAlt == 2.5 and entries[1].achievementID == 77)

assert(not pcall(function() generator:GetAllRooms(1) end))
assert(not pcall(function() generatorRoom:Shape(1) end))
assert(not pcall(function() bossPool:GetName(1) end))
'''


class RepentogonGeneratorApiTests(unittest.TestCase):
    def test_generator_room_and_boss_pool_views(self):
        driver = (
            '#include "interfaces/lua/repentogon_generator_api.hpp"\n'
            + BEHAVIOR
        )
        driver = driver.replace(
            "void PublishNativeState() {",
            EXTRA + "\nvoid PublishNativeState() {",
            1,
        )
        driver = driver.replace(
            "void InstallTestBindings(lua_State* state) noexcept {",
            "void InstallTestBindings(lua_State* state) noexcept {\n"
            "    InstallGeneratorBindings(state);",
            1,
        )
        driver = driver.replace(
            "    PublishNativeState();",
            "    PublishNativeState();\n"
            "    PublishGeneratorFixtures();",
            1,
        )
        driver = driver.replace(
            "    constexpr const char* script = R\"lua(",
            "    constexpr const char* script = R\"lua(" + SCRIPT + "\n",
            1,
        )
        with tempfile.TemporaryDirectory(prefix="generator-api-") as folder:
            binary = test_support.build_lua_harness(
                source_root=SOURCE,
                workdir=Path(folder),
                harness_source=driver,
            )
            result = subprocess.run([str(binary)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
