"""Real MultiShotParams layout and MGO-required getters/setters."""

import unittest

from .test_api400_params import run_main


MAIN = r'''
#include "interfaces/lua/api600_player.hpp"

#include <cassert>
#include <cstring>

extern "C" {
#include <lauxlib.h>
#include <lualib.h>
}

using isaac::runtime::Api600MultiShotParams;

template <class T>
static void Put(void* bytes, unsigned offset, T value) {
    std::memcpy(static_cast<std::uint8_t*>(bytes) + offset,
                &value, sizeof(value));
}

template <class T>
static T Get(const void* bytes, unsigned offset) {
    T value{};
    std::memcpy(&value, static_cast<const std::uint8_t*>(bytes) + offset,
                sizeof(value));
    return value;
}

int main() {
    static_cast<void>(kScriptTemplate);
    static_cast<void>(&HarnessHasCollectible);
    static_cast<void>(&BuildPrelude);
    static_cast<void>(&ExpectNumber);
    static_cast<void>(&CreateBlocks);
    static_cast<void>(&FillEntities);
    static_cast<void>(&PublishEntityList);
    static_cast<void>(&PublishLists);
    static_cast<void>(&PublishGame);

    lua_State* state = luaL_newstate();
    assert(state);
    luaL_requiref(state, "_G", luaopen_base, 1);
    lua_pop(state, 1);

    luaL_newmetatable(state, "IsaacRuntime.MultiShotParams");
    lua_pop(state, 1);

    Api600MultiShotParams params{};
    Put(params.bytes, 0x0, std::int16_t{5});
    Put(params.bytes, 0x2, std::int16_t{6});
    Put(params.bytes, 0x4, 2.5F);
    Put(params.bytes, 0x8, 3.5F);
    Put(params.bytes, 0xC, 4.5F);
    Put(params.bytes, 0x10, 5.5F);
    Put(params.bytes, 0x14, std::int32_t{123});

    assert(isaac::runtime::PushApi600MultiShotParamsSnapshot(state, params));
    assert(luaL_testudata(state, -1, "IsaacRuntime.MultiShotParams"));
    lua_setglobal(state, "params");

    lua_pushcfunction(state, isaac::runtime::Api600MultiShotParamsGetNumTears);
    lua_setglobal(state, "GetNumTears");
    lua_pushcfunction(state, isaac::runtime::Api600MultiShotParamsSetNumTears);
    lua_setglobal(state, "SetNumTears");
    lua_pushcfunction(state,
                      isaac::runtime::Api600MultiShotParamsGetNumLanesPerEye);
    lua_setglobal(state, "GetNumLanesPerEye");
    lua_pushcfunction(state,
                      isaac::runtime::Api600MultiShotParamsSetNumLanesPerEye);
    lua_setglobal(state, "SetNumLanesPerEye");
    lua_pushcfunction(state,
                      isaac::runtime::Api600MultiShotParamsGetSpreadAngle);
    lua_setglobal(state, "GetSpreadAngle");
    lua_pushcfunction(state,
                      isaac::runtime::Api600MultiShotParamsSetSpreadAngle);
    lua_setglobal(state, "SetSpreadAngle");

    const char* script = R"lua(
assert(GetNumTears(params) == 5)
assert(GetNumLanesPerEye(params) == 6)
SetNumTears(params, 0x100000001)
assert(GetNumTears(params) == 1)
SetNumLanesPerEye(params, 0x100000001)
assert(GetNumLanesPerEye(params) == 1)
assert(GetSpreadAngle(params, 1) == 2.5)
assert(GetSpreadAngle(params, 2) == 3.5)
assert(GetSpreadAngle(params, 4) == 5.5)
assert(GetSpreadAngle(params, 9) == 4.5)
assert(GetSpreadAngle(params, 10) == 16.5)
assert(GetSpreadAngle(params, 6) == 0)
SetSpreadAngle(params, 1, 40)
assert(GetSpreadAngle(params, 1) == 40)
assert(GetNumLanesPerEye(params) == 2)
SetSpreadAngle(params, 10, 60)
assert(GetSpreadAngle(params, 10) == 60)
assert(GetSpreadAngle(params, 4) == 20)
assert(not pcall(function() GetSpreadAngle(params, 16) end))
assert(not pcall(function() SetSpreadAngle(params, 16, 1) end))
assert(not pcall(function() SetSpreadAngle(params, 6, 1) end))
)lua";
    if (luaL_dostring(state, script) != LUA_OK) return 1;

    Api600MultiShotParams result{};
    lua_getglobal(state, "params");
    assert(isaac::runtime::ReadApi600MultiShotParamsSnapshot(
        state, -1, &result));
    lua_pop(state, 1);
    assert(Get<std::int16_t>(result.bytes, 0x0) == 1);
    assert(Get<std::int16_t>(result.bytes, 0x2) == 2);
    assert(Get<float>(result.bytes, 0x4) == 40.0F);
    assert(Get<float>(result.bytes, 0x10) == 20.0F);
    assert(Get<std::int32_t>(result.bytes, 0x14) == 123);

    lua_newuserdata(state, sizeof(Api600MultiShotParams));
    Api600MultiShotParams* invalid = &result;
    assert(!isaac::runtime::ReadApi600MultiShotParamsSnapshot(
        state, -1, invalid));
    lua_pop(state, 1);

    lua_newtable(state);
    assert(!isaac::runtime::ReadApi600MultiShotParamsSnapshot(
        state, -1, invalid));
    lua_pop(state, 1);

    lua_close(state);
    return 0;
}
'''


class MultiShotParamsTests(unittest.TestCase):
    def test_layout_and_mgo_methods(self):
        result = run_main(MAIN)
        self.assertEqual(result.returncode, 0,
                         result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
