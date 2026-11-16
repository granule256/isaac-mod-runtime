"""PC PlayerHUD heart snapshots backed by the Switch HUD layout."""

import subprocess
import tempfile
import unittest
from pathlib import Path

from . import test_support

SOURCE = Path(__file__).resolve().parents[1] / "source"
CPP = SOURCE.parent / "src/interfaces/lua/repentogon_playerhud_hearts_api.cpp"

DRIVER = r'''
#include "interfaces/lua/repentogon_playerhud_hearts_api.hpp"
#include "interfaces/lua/field_api.hpp"
#include "interfaces/lua/isaac_api.hpp"
#include "lua_object_handles.hpp"
#include "lua_runtime.hpp"
#include "runtime_constants.hpp"
extern "C" {
#include <lauxlib.h>
}
#include <cassert>
#include <cstdarg>
#include <cstdio>
#include <cstring>

namespace {
alignas(16) unsigned char game[kGameHudObjectOffset + 8 * 0x908]{};
alignas(16) unsigned char player[kEntityPlayerIndexOffset + 8]{};
std::uintptr_t gameAddress = reinterpret_cast<std::uintptr_t>(game);
std::uintptr_t gameSlot = reinterpret_cast<std::uintptr_t>(&gameAddress);

void MakeReceiver(lua_State* state, const char* metatable, const char* name) {
    luaL_newmetatable(state, metatable);
    lua_newtable(state);
    lua_pushvalue(state, -1);
    lua_setfield(state, -3, "__methods");
    lua_setfield(state, -2, "__index");
    lua_pop(state, 1);
    lua_newuserdata(state, 8);
    luaL_setmetatable(state, metatable);
    lua_setglobal(state, name);
}
}

bool LuaRuntime::IsOnGameThread() noexcept { return true; }
int LuaRuntime::ReportAndRecordLuaError(lua_State* state, const char* format, ...) {
    std::va_list arguments;
    va_start(arguments, format);
    lua_pushvfstring(state, format, arguments);
    va_end(arguments);
    return lua_error(state);
}
std::uintptr_t LuaRuntime::GameOwnerSlot() noexcept {
    return reinterpret_cast<std::uintptr_t>(&gameSlot);
}
std::uintptr_t isaac::runtime::ResolveEngineReceiver(lua_State*, FieldReceipt receipt, int) {
    assert(receipt == FieldReceipt::EntityPlayer);
    return reinterpret_cast<std::uintptr_t>(player);
}

int main() {
    auto* state = luaL_newstate();
    assert(state);
    MakeReceiver(state, LuaRuntime::kHudMetatable, "hud");
    MakeReceiver(state, LuaRuntime::kEntityPlayerMetatable, "player");
    isaac::runtime::RegisterRepentogonPlayerHudHearts(state);

    std::uint32_t slot = 2;
    std::memcpy(player + kEntityPlayerIndexOffset, &slot, sizeof(slot));
    auto* first = game + kGameHudObjectOffset + 2 * 0x908 + 0x18;
    first[0] = 1;
    first[1] = 1;
    first[2] = 1;
    first[3] = 1;
    first[4] = 4;
    const char* normal = "FullHeart";
    const char* eternal = "EternalHeartOverlay";
    std::memcpy(first + 8, &normal, sizeof(normal));
    std::memcpy(first + 0x10, &eternal, sizeof(eternal));
    const char code[] = R"lua(
        if player:GetPlayerIndex() ~= 2 then return "index" end
        local hearts = hud:GetPlayerHUD(player:GetPlayerIndex()):GetHearts()
        if #hearts ~= 24 then return "count" end
        if not hearts[1]:IsVisible() or not hearts[1]:IsGoldenHeartOverlayVisible()
            or not hearts[1]:IsEternalHeartOverlayVisible() or not hearts[1]:IsFadingHeart()
            or hearts[1]:GetFlashType() ~= 4 then return "flags" end
        if hearts[1]:GetHeartAnim() ~= "FullHeart"
            or hearts[1]:GetHeartOverlayAnim() ~= "EternalHeartOverlay" then return "animation" end
        if hearts[24]:IsVisible() then return "last slot" end
        saved = hearts[1]
    )lua";
    if (luaL_dostring(state, code) != LUA_OK || lua_gettop(state)) {
        std::fprintf(stderr, "%s\n", lua_tostring(state, -1));
        return 1;
    }
    first[0] = 0;
    assert(luaL_dostring(state, "return saved:IsVisible()") == LUA_OK);
    assert(lua_toboolean(state, -1));
    lua_pop(state, 1);
    assert(luaL_dostring(state, "hud:GetPlayerHUD(8)") != LUA_OK);
    lua_close(state);
}
'''


class RepentogonPlayerHudHeartsTests(unittest.TestCase):
    def test_hearts_snapshot_uses_player_slot_and_renderer_fields(self):
        with tempfile.TemporaryDirectory(prefix="playerhud-hearts-") as temporary:
            workdir = test_support.prepare_harness_directory(Path(temporary))
            driver = workdir / "driver.cpp"
            driver.write_text(DRIVER, encoding="utf-8")
            lua_root = SOURCE / test_support.LUA_SOURCE_RELATIVE
            binary = workdir / "hearts"
            flags = test_support.HARNESS_COMPILE_FLAGS
            result = subprocess.run([
                "c++", *flags, "-I" + str(workdir / "compatibility"),
                "-I" + str(SOURCE), "-I" + str(SOURCE.parent / "src"),
                "-I" + str(lua_root), str(driver), str(CPP),
                *(str(obj) for obj in test_support.lua_harness_objects(SOURCE, workdir)),
                "-lm", "-o", str(binary),
            ], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            result = subprocess.run([str(binary)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
