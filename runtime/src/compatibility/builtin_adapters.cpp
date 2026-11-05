#include "compatibility/builtin_adapters.hpp"
#include "compatibility/minimapapi_pickups_adapter.hpp"

extern "C" {
#include "lua.h"
#include "lauxlib.h"
}
#include <cstring>

namespace isaac::runtime::compatibility {
namespace {
BuiltinAdapterDiagnostics g_Diagnostics{};

int InstallProtected(lua_State* state) {
    if (luaL_loadbufferx(state, kMinimapApiPickupAdapter,
                        sizeof(kMinimapApiPickupAdapter) - 1,
                        "@compatibility/minimapapi_pickups.lua", "t") != LUA_OK)
        return lua_error(state);
    lua_call(state, 0, 1);
    if (!RegisterCompatibilityAdapter(state, "minimapapi.pickups", -1,
                                      &g_Diagnostics.adapterId))
        return luaL_error(state, "cannot register optional compatibility adapter");
    g_Diagnostics.installed = 1;
    return 0;
}
} // namespace

void InstallBuiltinCompatibilityAdapters(lua_State* state) noexcept {
    g_Diagnostics = {};
    if (!state || !lua_checkstack(state, 2)) {
        g_Diagnostics.failures = 1;
        g_Diagnostics.lastStatus = LUA_ERRMEM;
        std::strcpy(g_Diagnostics.error, "cannot reserve compatibility installer stack");
        return;
    }
    const int top = lua_gettop(state);
    lua_pushcfunction(state, InstallProtected);
    g_Diagnostics.lastStatus = lua_pcall(state, 0, 0, 0);
    if (g_Diagnostics.lastStatus != LUA_OK) {
        g_Diagnostics.failures = 1;
        const auto* error = lua_type(state, -1) == LUA_TSTRING ? lua_tostring(state, -1) :
                           "compatibility installer failed";
        std::strncpy(g_Diagnostics.error, error, sizeof(g_Diagnostics.error) - 1);
        g_Diagnostics.error[sizeof(g_Diagnostics.error) - 1] = 0;
    }
    lua_settop(state, top);
}

BuiltinAdapterDiagnostics GetBuiltinAdapterDiagnostics() noexcept { return g_Diagnostics; }

} // namespace isaac::runtime::compatibility
