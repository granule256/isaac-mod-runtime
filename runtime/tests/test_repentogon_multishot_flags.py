"""REPENTOGON MultiShotParams shooting-direction getters and environment gating."""

import unittest

from .test_api400_params import run_main


MAIN = r'''
#include "interfaces/lua/api600_player.hpp"
#include "interfaces/lua/repentogon_callbacks.hpp"
#include "interfaces/lua/repentogon_environment.hpp"

#include <cassert>
#include <cstdio>
#include <cstdlib>
#include <cstring>

extern "C" {
#include <lauxlib.h>
#include <lualib.h>
}

using namespace isaac::runtime;

static const RepentogonCatalog& Catalog() {
    static RepentogonApiBinding flags[2]{};
    bool haveSideways = false;
    bool haveBackwards = false;
    const auto& all = repentogon::CallbackBatch();
    for (std::size_t i = 0; i < all.apiCount; ++i) {
        const auto& api = all.apis[i];
        if (api.descriptor.id == 0x0E020127) {
            haveSideways = !std::strcmp(api.descriptor.owner, "MultiShotParams") &&
                           !std::strcmp(api.descriptor.name, "IsShootingSideways") &&
                           api.handler && !api.field && !api.method;
            flags[0] = api;
        } else if (api.descriptor.id == 0x0E020128) {
            haveBackwards = !std::strcmp(api.descriptor.owner, "MultiShotParams") &&
                            !std::strcmp(api.descriptor.name, "IsShootingBackwards") &&
                            api.handler && !api.field && !api.method;
            flags[1] = api;
        }
    }
    if (!haveSideways || !haveBackwards) {
        std::fprintf(stderr, "REPENTOGON MultiShotParams flag APIs are missing\n");
        std::abort();
    }
    static const RepentogonBatch batch{"multishot-flags", flags, 2};
    static const RepentogonCatalog catalog{&batch, 1, nullptr};
    return catalog;
}

static void Run(lua_State* state, const char* script) {
    if (luaL_dostring(state, script) != LUA_OK) {
        std::fprintf(stderr, "%s\n", lua_tostring(state, -1));
        std::abort();
    }
}

static lua_State* Open(bool requested) {
    lua_State* state = luaL_newstate();
    assert(state);
    luaL_requiref(state, "_G", luaopen_base, 1);
    lua_pop(state, 1);
    BeginRepentogonEnvironment(state, requested, Catalog());
    RegisterApi600PlayerTypes(state);
    CompleteRepentogonEnvironment(state);
    return state;
}

static void PublishParams(lua_State* state, std::uint8_t backwards,
                          std::uint8_t sideways) {
    Api600MultiShotParams params{};
    params.bytes[0x1D] = backwards;
    params.bytes[0x1E] = sideways;
    assert(PushApi600MultiShotParamsSnapshot(state, params));
    lua_setglobal(state, "params");
}

static void Close(lua_State* state) {
    SuspendRepentogonEnvironment(state);
    lua_close(state);
    EndRepentogonEnvironment(state);
    assert(!RepentogonEnvironmentActive());
}

int main() {
    static_cast<void>(kScriptTemplate);
    static_cast<void>(&HarnessHasCollectible);
    static_cast<void>(&BuildPrelude);
    static_cast<void>(&ExpectNumber);
    static_cast<void>(CreateBlocks);
    static_cast<void>(FillEntities);
    static_cast<void>(PublishEntityList);
    static_cast<void>(PublishLists);
    static_cast<void>(PublishGame);

    auto* state = Open(false);
    PublishParams(state, 1, 1);
    Run(state, R"lua(
assert(params.IsShootingSideways == nil)
assert(params.IsShootingBackwards == nil)
assert(not pcall(function() return params:IsShootingSideways() end))
assert(not pcall(function() return params:IsShootingBackwards() end))
)lua");
    Close(state);

    state = Open(true);
    PublishParams(state, 1, 0);
    Run(state, R"lua(
assert(type(params:IsShootingSideways()) == 'boolean')
assert(type(params:IsShootingBackwards()) == 'boolean')
assert(params:IsShootingSideways() == false)
assert(params:IsShootingBackwards() == true)
)lua");
    Close(state);

    state = Open(true);
    PublishParams(state, 0, 1);
    Run(state, R"lua(
assert(params:IsShootingSideways() == true)
assert(params:IsShootingBackwards() == false)
)lua");
    Close(state);

    state = Open(false);
    PublishParams(state, 1, 1);
    Run(state, "assert(params.IsShootingSideways == nil and params.IsShootingBackwards == nil)");
    Close(state);
}
'''


class RepentogonMultiShotFlagTests(unittest.TestCase):
    def test_gated_sideways_and_backwards_getters(self):
        result = run_main(MAIN)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
