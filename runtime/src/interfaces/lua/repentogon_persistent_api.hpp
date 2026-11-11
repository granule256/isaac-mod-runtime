#pragma once

extern "C" {
#include <lua.h>
}

namespace isaac::runtime {
int RepentogonPersistentGameDataGetEventCounter(lua_State* state);
int RepentogonPersistentGameDataIsItemInCollection(lua_State* state);
}
