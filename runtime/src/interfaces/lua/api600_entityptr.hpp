#pragma once
struct lua_State;
namespace isaac::runtime {
int Api600EntityPtrConstructor(lua_State*);
void RegisterApi600EntityPtr(lua_State*);
int Api600EntityPtrSetReference(lua_State*);
}
