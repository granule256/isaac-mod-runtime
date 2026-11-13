#include "interfaces/lua/repentogon_console_api.hpp"

#include "domain/console/console_commands.hpp"
#include "infrastructure/console/console_panel.hpp"
#include "interfaces/lua/owner_binding.hpp"
#include "lua_runtime.hpp"

#include <cstring>
#include <string>
#include <string_view>

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

int RepentogonConsoleRegisterCommand(lua_State* state) {
    RequireGameThread(state, "Console.RegisterCommand");
    const auto text = [state](int index, const char* name) {
        const char* value = luaL_checkstring(state, index);
        if (!value) {
            luaL_error(state, "%s expects a string", name);
        }
        return std::string_view(value, std::strlen(value));
    };
    const auto name = text(1, "Console.RegisterCommand");
    const auto description = text(2, "Console.RegisterCommand");
    const auto help = text(3, "Console.RegisterCommand");
    const bool showOnMenu = lua_gettop(state) >= 4 && lua_toboolean(state, 4) != 0;
    const auto autocomplete = static_cast<std::uint32_t>(
        luaL_optnumber(state, 5, static_cast<lua_Number>(
            console::ConsoleAutocompleteType::None)));
    switch (console::RegisterConsoleCommand(name, description, help, showOnMenu,
                                            autocomplete)) {
        case console::ConsoleCommandRegistration::Added:
        case console::ConsoleCommandRegistration::Duplicate:
            return 0;
    }
    return 0;
}

int RegisterRepentogonConsoleApi(lua_State* state) {
    console::ResetConsoleCommands();
    lua_newtable(state);
    static_cast<void>(AttachOwnerMethods(state, "Console", nullptr, 0));
    lua_setglobal(state, "Console");
    lua_newtable(state);
    constexpr const char* names[] = {
        "NONE", "ENTITY", "GOTO", "STAGE", "GRID", "DEBUG_FLAG", "ITEM",
        "CHALLENGE", "COMBO", "CUTSCENE", "MACRO", "SFX", "CURSE", "METRO",
        "DELIRIOUS", "PLAYER", "ACHIEVEMENT", "MODFOLDER", "CUSTOM", "EFFECT"};
    for(std::size_t index=0;index<sizeof(names)/sizeof(names[0]);++index) {
        lua_pushinteger(state,static_cast<lua_Integer>(index));
        lua_setfield(state,-2,names[index]);
    }
    lua_setglobal(state, "AutocompleteType");
    return 0;
}

}
