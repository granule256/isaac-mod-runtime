"""Bag-of-crafting and active-item views use pinned player layouts."""

import subprocess
import tempfile
import unittest
from pathlib import Path

from . import test_support
from .test_repentogon_in_game import PREFIX

SOURCE = Path(__file__).resolve().parents[1] / "source"
DRIVER = PREFIX + r'''
#include "interfaces/lua/repentogon_boc_api.hpp"
#include "interfaces/lua/isaac_api.hpp"
#include "infrastructure/call/engine_call_access.hpp"
#include "lua_object_handles.hpp"
#include "runtime_constants.hpp"

#include <cstdint>
#include <cstdio>
#include <cstring>
#include <vector>

static std::vector<unsigned char> module;
static std::vector<unsigned char> player;
static int calls;

static std::int32_t Calculate(void* unused, const void* content, bool verbose) {
    assert(unused == nullptr && !verbose);
    assert(content != nullptr);
    const auto* pickups = static_cast<const std::int8_t*>(content);
    for (int index = 0; index < 8; ++index) {
        assert(pickups[index] == index + 1);
    }
    ++calls;
    return 422;
}

template <class T>
static void Put(std::size_t offset, T value) {
    assert(offset + sizeof(value) <= player.size());
    std::memcpy(player.data() + offset, &value, sizeof(value));
}

static int Mutate(lua_State*) {
    Put<std::int32_t>(0x197c, 19);
    return 0;
}

static void Extensions(lua_State* state) noexcept {
    isaac::runtime::PushEntityCallbackArgument(
        state, reinterpret_cast<std::uintptr_t>(player.data()));
    lua_setglobal(state, "player");
    lua_pushcfunction(state, Mutate);
    lua_setglobal(state, "_mutate");
}

int main() {
    module.assign(0x3000, 0);
    player.assign(0x3000, 0);
    const auto base = reinterpret_cast<std::uintptr_t>(module.data());
    const auto vtable = base + kEntityPlayerVtableOffset;
    std::memcpy(player.data(), &vtable, sizeof(vtable));
    Put<std::uint32_t>(kEntityTypeOffset, kEntityTypePlayer);

    for (int index = 0; index < 8; ++index) {
        Put<std::int8_t>(0x2690 + index, static_cast<std::int8_t>(index + 1));
    }
    Put<std::int32_t>(0x2698, 313);

    constexpr std::size_t slot0 = kEntityPlayerActiveItemOffset;
    Put<std::int32_t>(slot0 + 0x00, 105);
    Put<std::int32_t>(slot0 + 0x04, 2);
    Put<std::int32_t>(slot0 + 0x08, 3);
    Put<std::int32_t>(slot0 + 0x0c, 4);
    Put<std::int32_t>(slot0 + 0x10, 5);
    Put<float>(slot0 + 0x14, 0.5f);
    Put<std::int32_t>(slot0 + 0x18, 6);

    constexpr std::size_t slot3 =
        kEntityPlayerActiveItemOffset + 3 * kEntityPlayerActiveItemStride;
    Put<std::int32_t>(slot3 + 0x00, 422);
    Put<std::int32_t>(slot3 + 0x18, 77);

    LuaRuntime::SetEngineModuleBase(base);
    LuaRuntime::ObserveGameThread();
    Files files(true);
    SetSessionSaveFilePort(&files);
    const isaac::runtime::repentogon::NativePort port{Ready, Ready};
    isaac::runtime::repentogon::SetNativePort(&port);
    isaac::runtime::SetRepentogonBocNativeTestBindings(
        {&Calculate});
    LuaRuntime::SetRuntimeExtensionInstaller(Extensions);

    const char* script = R"lua(
assert(type(EntityPlayer.CalculateBagOfCraftingOutput) == 'function')
local collectible, pool = EntityPlayer.CalculateBagOfCraftingOutput({1,2,3,4,5,6,7,8})
assert(collectible == 422 and pool == nil)
assert(not pcall(function() EntityPlayer.CalculateBagOfCraftingOutput({1,2,3}) end))
assert(not pcall(function() EntityPlayer.CalculateBagOfCraftingOutput({1,2,3,4,5,6,7,30}) end))
assert(not pcall(function() EntityPlayer.CalculateBagOfCraftingOutput('x') end))

local content = player:GetBagOfCraftingContent()
assert(#content == 8)
for index = 1, 8 do assert(content[index] == index) end
assert(player:GetBagOfCraftingOutput() == 313)
assert(not pcall(function() player:GetBagOfCraftingContent(1) end))
assert(not pcall(function() player:GetBagOfCraftingOutput(1) end))

local desc = player:GetActiveItemDesc()
assert(desc.Item == 105 and desc.Charge == 2 and desc.SubCharge == 3)
assert(desc.BatteryCharge == 4 and desc.TimedRechargeCooldown == 5)
assert(desc.PartialCharge == 0.5 and desc.VarData == 6)
assert(desc.Unknown == nil)
desc.VarData = 12
desc.PartialCharge = 0.75
assert(desc.VarData == 12 and desc.PartialCharge == 0.75)
assert(not pcall(function() desc.Unknown = 1 end))

local third = player:GetActiveItemDesc(3)
assert(third.Item == 422 and third.VarData == 77)
assert(not pcall(function() player:GetActiveItemDesc(4) end))
assert(not pcall(function() player:GetActiveItemDesc(-1) end))

_mutate()
assert(desc.VarData == 19)
)lua";
    if (LuaRuntime::InitializeFromBuffer(script, std::strlen(script),
                                         "@boc-api.lua") !=
        LuaRuntime::LuaInitResult::Success) {
        char error[2048]{};
        static_cast<void>(LuaRuntime::CopyLastLuaErrorText(error, sizeof(error)));
        std::fprintf(stderr, "%s\n", error);
        return 1;
    }
    assert(calls == 1);
    assert(LuaRuntime::ShutdownForModReload());
    LuaRuntime::SetRuntimeExtensionInstaller(nullptr);
    isaac::runtime::SetRepentogonBocNativeTestBindings({});
    isaac::runtime::repentogon::SetNativePort(nullptr);
    SetSessionSaveFilePort(nullptr);
}
'''


class RepentogonBocApiTests(unittest.TestCase):
    def test_bag_and_active_item_desc(self):
        with tempfile.TemporaryDirectory(prefix="repentogon-boc-") as folder:
            binary = test_support.build_lua_harness(
                source_root=SOURCE, workdir=Path(folder), harness_source=DRIVER)
            result = subprocess.run([str(binary)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
