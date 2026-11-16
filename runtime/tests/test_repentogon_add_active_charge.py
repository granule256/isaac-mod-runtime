"""EntityPlayer:AddActiveCharge preserves the REPENTOGON argument contract."""

import subprocess
import tempfile
import unittest
from pathlib import Path

from . import test_support
from .test_repentogon_in_game import PREFIX


PUBLIC_ROOT = Path(__file__).resolve().parents[2]
SOURCE = PUBLIC_ROOT / "runtime" / "source"
API_SOURCE = (
    PUBLIC_ROOT
    / "runtime"
    / "src"
    / "interfaces"
    / "lua"
    / "repentogon_player_api.cpp"
)
DRIVER = PREFIX + r'''
#include "interfaces/lua/repentogon_player_api.hpp"
#include "interfaces/lua/isaac_api.hpp"
#include "lua_object_handles.hpp"
#include "lua_runtime.hpp"
#include "runtime_constants.hpp"

#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <vector>

using namespace isaac::runtime;

static std::vector<unsigned char> moduleBytes;
static std::vector<unsigned char> player;
static int calls;
static int step;
static int substep;
static int maxQueries;

static std::int32_t Maximum(void* object, std::int32_t slot) {
    assert(object == player.data());
    ++maxQueries;
    return 10 + slot;
}

static std::int32_t Added(void* object, std::int32_t charge, std::int32_t slot,
                          bool flashHUD, bool overcharge, bool force) {
    assert(object == player.data());
    ++calls;
    if (step == 4 || step == 6) ++substep;
    switch (step) {
        case 1:
            assert(charge == -1 && slot == 1 && !flashHUD && overcharge && !force);
            return 1;
        case 2:
            assert(charge == 2 && slot == 0 && flashHUD && !overcharge && !force);
            return 2;
        case 3:
            assert(charge == 3 && slot == 0 && flashHUD && !overcharge && !force);
            return 0;
        case 4:
            assert(charge == 4 && slot == substep - 1 &&
                   flashHUD && !overcharge && force);
            return 1;
        case 5:
            assert(charge == 5 && slot == 3 && flashHUD && !overcharge && !force);
            return 5;
        case 6:
            assert(charge == 6 && slot == substep - 1 &&
                   flashHUD && !overcharge && !force);
            return slot + 1;
        case 7:
            assert(charge == -1 && slot == 0 &&
                   !flashHUD && !overcharge && !force);
            return -1;
        default:
            assert(false && "unexpected AddActiveCharge call");
            return 0;
    }
}

static int SetStep(lua_State* state) {
    step = static_cast<int>(luaL_checkinteger(state, 1));
    substep = 0;
    return 0;
}

static void Extensions(lua_State* state) noexcept {
    PushEntityCallbackArgument(state, reinterpret_cast<std::uintptr_t>(player.data()));
    lua_setglobal(state, "player");
    lua_pushcfunction(state, SetStep);
    lua_setglobal(state, "_step");
}

int main() {
    moduleBytes.assign(kEntityPlayerVtableOffset + 16, 0);
    player.assign(0x3000, 0);
    const auto base = reinterpret_cast<std::uintptr_t>(moduleBytes.data());
    const auto vptr = base + kEntityPlayerVtableOffset;
    std::memcpy(player.data(), &vptr, sizeof(vptr));
    const std::uint32_t type = kEntityTypePlayer;
    std::memcpy(player.data() + kEntityTypeOffset, &type, sizeof(type));
    const unsigned char maxChargeGuard[]={0xfd,0x7b,0xbe,0xa9,0xf3,0x0b,0x00,0xf9,
                                          0xfd,0x03,0x00,0x91,0x3f,0x0c,0x00,0x71};
    std::memcpy(moduleBytes.data() + 0x27f828, maxChargeGuard, sizeof(maxChargeGuard));

    LuaRuntime::SetEngineModuleBase(base);
    LuaRuntime::ObserveGameThread();
    Files files(true);
    SetSessionSaveFilePort(&files);
    const repentogon::NativePort port{Ready, Ready};
    repentogon::SetNativePort(&port);
    SetRepentogonPlayerAddActiveChargeHost(&Added);
    SetRepentogonPlayerActiveMaxChargeHost(&Maximum);
    LuaRuntime::SetRuntimeExtensionInstaller(Extensions);

    const char* script = R"lua(
assert(type(player.GetActiveMaxCharge)=='function', 'EntityPlayer:GetActiveMaxCharge was not registered')
assert(player:GetActiveMaxCharge() == 10 and player:GetActiveMaxCharge(nil) == 10)
assert(player:GetActiveMaxCharge(2) == 12 and player:GetActiveMaxCharge(3) == 13)
local ok, err=pcall(player.GetActiveMaxCharge, player, -1)
assert(not ok and err:find('Invalid ActiveSlot -1', 1, true))
assert(not pcall(player.GetActiveMaxCharge, player, 4))
assert(not pcall(player.GetActiveMaxCharge, player, 1.5))
_step(1); assert(player:AddActiveCharge(-1, 1, false, true, false) == 1)
_step(2); assert(player:AddActiveCharge(2) == 2)
_step(3); assert(player:AddActiveCharge(3, nil, nil, nil, nil) == 0)
_step(4); assert(player:AddActiveCharge(4, -1, true, false, true) == 4)
_step(5); assert(player:AddActiveCharge(5, 3) == 5)
_step(6); assert(player:AddActiveCharge(6, -2) == 10)
_step(7); assert(player:AddActiveCharge(-1, 0, false, false, false) == -1)
assert(player:AddActiveCharge(-1, 0, false, false, false, 1) == -1)
assert(not pcall(function() player:AddActiveCharge() end))
assert(not pcall(function() player:AddActiveCharge(1, 4) end))
assert(not pcall(function() player:AddActiveCharge({}) end))
assert(not pcall(function() player:AddActiveCharge(1, {}) end))
)lua";

    if (LuaRuntime::InitializeFromBuffer(script, std::strlen(script),
                                         "@add-active-charge.lua") !=
        LuaRuntime::LuaInitResult::Success) {
        char error[2048]{};
        static_cast<void>(LuaRuntime::CopyLastLuaErrorText(error, sizeof(error)));
        std::fprintf(stderr, "%s\n", error);
        return 1;
    }
    assert(calls == 14);
    assert(maxQueries == 4);
    assert(LuaRuntime::ShutdownForModReload());
    SetRepentogonPlayerAddActiveChargeHost(nullptr);
    SetRepentogonPlayerActiveMaxChargeHost(nullptr);
    repentogon::SetNativePort(nullptr);
    SetSessionSaveFilePort(nullptr);
    LuaRuntime::SetRuntimeExtensionInstaller(nullptr);
}
'''


class RepentogonAddActiveChargeTests(unittest.TestCase):
    def test_native_branch_compiles_with_null_host_address(self) -> None:
        with tempfile.TemporaryDirectory(
                prefix="rgon-add-active-charge-compile-") as folder:
            compatibility = Path(folder) / "compatibility"
            compatibility.mkdir()
            (compatibility / "stdfloat").write_text(
                "#pragma once\n"
                "namespace std { using float16_t = float; "
                "using float128_t = long double; }\n",
                encoding="utf-8",
            )
            result = subprocess.run(
                [
                    "c++", "-std=c++23", "-D__SWITCH__",
                    "-DEXL_LAYERED_RUNTIME=1", "-DEXL_DIAGNOSTIC_STAGE=14",
                    "-DEXL_LOAD_KIND=Module", "-DEXL_LOAD_KIND_ENUM=2",
                    "-DEXL_PROGRAM_ID=0", "-fsyntax-only",
                    f"-I{compatibility}", f"-I{PUBLIC_ROOT / 'runtime' / 'src'}",
                    f"-I{SOURCE}",
                    f"-I{SOURCE / 'third_party' / 'lua-5.3.3' / 'src'}",
                    str(API_SOURCE),
                ],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_host_contract_and_argument_defaults(self):
        with tempfile.TemporaryDirectory(prefix="rgon-add-active-charge-") as folder:
            binary = test_support.build_lua_harness(
                source_root=SOURCE,
                workdir=Path(folder),
                harness_source=DRIVER,
            )
            result = subprocess.run([str(binary)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_native_guard_and_registration(self):
        implementation = (
            SOURCE.parent / "src/interfaces/lua/repentogon_player_api.cpp"
        ).read_text()
        header = (
            SOURCE.parent / "src/interfaces/lua/repentogon_player_api.hpp"
        ).read_text()
        catalog = (
            SOURCE.parent / "src/interfaces/lua/repentogon_callbacks.cpp"
        ).read_text()

        self.assertIn("kAddActiveCharge{0x2ac41c", implementation)
        self.assertIn(
            "{0xff,0x43,0x02,0xd1,0xfd,0x7b,0x03,0xa9,"
            "0xfd,0xc3,0x00,0x91,0xfc,0x6f,0x04,0xa9}",
            implementation,
        )
        self.assertIn("RepentogonEntityPlayerAddActiveCharge", header)
        self.assertIn(
            '{{0x0E02000D,ApiDomain::Isaac,"EntityPlayer","AddActiveCharge"',
            catalog,
        )
        self.assertIn("RepentogonEntityPlayerAddActiveCharge", catalog)
        self.assertIn('"EntityPlayer","GetActiveMaxCharge"', catalog)


if __name__ == "__main__":
    unittest.main()
