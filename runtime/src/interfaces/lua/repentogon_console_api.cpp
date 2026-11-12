#include "interfaces/lua/repentogon_console_api.hpp"

#include "infrastructure/console/console_panel.hpp"
#include "interfaces/lua/owner_binding.hpp"
#include "lua_runtime.hpp"

#include <cstring>
#include <string>

extern "C" {
#include <lauxlib.h>
}

namespace isaac::runtime {
namespace {

void RequireGameThread(lua_State* state, const char* name) {
    if (!LuaRuntime::IsOnGameThread()) {
        luaL_error(state, "%s requires the game thread", name);
    }
}

const char* Text(lua_State* state, std::size_t* length, const char* name) {
    if (lua_gettop(state) != 1) {
        luaL_error(state, "%s expects one string", name);
    }
    const auto* text = luaL_checklstring(state, 1, length);
    if (!text || *length == 0) {
        luaL_error(state, "%s expects a non-empty string", name);
    }
    return text;
}

void PushHistoryEntry(void* user, const char* text, std::size_t length) {
    auto* state = static_cast<lua_State*>(user);
    lua_pushlstring(state, text, length);
    lua_rawseti(state, -2,
                static_cast<lua_Integer>(lua_rawlen(state, -2) + 1));
}

}  // namespace

int RepentogonConsolePrintError(lua_State* state) {
    RequireGameThread(state, "Console.PrintError");
    std::size_t length{};
    const auto* text = Text(state, &length, "Console.PrintError");
    if (!console::PrintConsoleError(LuaRuntime::EngineModuleBase(), text,
                                    length)) {
        return luaL_error(state, "Console.PrintError native binding is unavailable");
    }
    return 0;
}

int RepentogonConsolePrintWarning(lua_State* state) {
    RequireGameThread(state, "Console.PrintWarning");
    std::size_t length{};
    const auto* text = Text(state, &length, "Console.PrintWarning");
    std::string warning(text, length);
    warning.push_back('\n');
    if (!console::PrintConsoleWarning(LuaRuntime::EngineModuleBase(),
                                      warning.data(), warning.size())) {
        return luaL_error(state,
                          "Console.PrintWarning native binding is unavailable");
    }
    return 0;
}

int RepentogonConsoleGetHistory(lua_State* state) {
    RequireGameThread(state, "Console.GetHistory");
    if (lua_gettop(state) != 0) {
        return luaL_error(state, "Console.GetHistory expects no arguments");
    }
    lua_newtable(state);
    if (!console::VisitConsoleHistory(LuaRuntime::EngineModuleBase(),
                                      &PushHistoryEntry, state)) {
        lua_pop(state, 1);
        return luaL_error(state, "Console history is unavailable");
    }
    return 1;
}

int RegisterRepentogonConsoleApi(lua_State* state) {
    lua_newtable(state);
    static_cast<void>(AttachOwnerMethods(state, "Console", nullptr, 0));
    lua_setglobal(state, "Console");
    return 0;
}

}
