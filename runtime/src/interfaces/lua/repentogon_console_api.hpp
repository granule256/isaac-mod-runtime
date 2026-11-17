#pragma once

struct lua_State;

namespace isaac::runtime {

int RegisterRepentogonConsoleApi(lua_State* state);
int RepentogonConsolePrintError(lua_State* state);
int RepentogonConsolePrintWarning(lua_State* state);
int RepentogonConsoleGetHistory(lua_State* state);
int RepentogonConsoleRegisterCommand(lua_State* state);
int RepentogonConsoleRegisterMacro(lua_State* state);

}
