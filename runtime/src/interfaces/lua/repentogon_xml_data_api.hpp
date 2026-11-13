#pragma once

struct lua_State;

namespace isaac::runtime {

// Publishes the XMLData global table and the XMLNode enum in the current VM.
// The central REPENTOGON registration owner calls this before author scripts.
int RegisterRepentogonXmlDataApi(lua_State* state) noexcept;

int RepentogonXmlDataGetEntityByTypeVarSub(lua_State* state);
int RepentogonXmlDataGetEntryById(lua_State* state);
int RepentogonXmlDataGetEntryByOrder(lua_State* state);
int RepentogonXmlDataGetNumEntries(lua_State* state);
int RepentogonIsaacGetGiantBookIdByName(lua_State* state);

}  // namespace isaac::runtime
