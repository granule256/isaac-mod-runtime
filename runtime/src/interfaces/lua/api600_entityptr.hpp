#pragma once
#include <cstdint>
struct lua_State;
namespace isaac::runtime {
int Api600EntityPtrConstructor(lua_State*);
void RegisterApi600EntityPtr(lua_State*);
int Api600EntityPtrSetReference(lua_State*);
}

#if !defined(__SWITCH__)
namespace isaac::runtime {
void SetApi600EntityPtrNativeTestBindings(std::uintptr_t setReference, std::uintptr_t destroy) noexcept;
}
#endif
