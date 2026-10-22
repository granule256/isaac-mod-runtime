#pragma once
#include <cstddef>
#include <cstdint>
struct lua_State;
namespace isaac::runtime {
struct EngineStringView {std::uintptr_t data;std::size_t size;};
bool ResolveEngineStringView(std::uintptr_t object,EngineStringView* view) noexcept;
int Api100LevelGetName(lua_State*);
int Api100LevelGetCurseName(lua_State*);
// Nontrivial for calls: AArch64 returns this libc++ object through x8, never x0/x1.
struct Api100NativeString {
 alignas(8) unsigned char bytes[24]{};
 Api100NativeString()=default;
 Api100NativeString(const Api100NativeString& other) noexcept;
};
static_assert(sizeof(Api100NativeString)==24);
// Shared protected x8 return: attach engine-release GC before the callback allocates.
using Api100NativeStringCallback=Api100NativeString(*)(void*);
int PushApi100NativeStringResult(lua_State*,Api100NativeStringCallback,void*);
#if !defined(__SWITCH__)
struct Api100StringNativeTestBindings {std::uintptr_t getName;std::uintptr_t getCurseName;};
void SetApi100StringNativeTestBindings(Api100StringNativeTestBindings) noexcept;
#endif
}
