#pragma once
#include <cstdint>
extern "C" {
#include <lua.h>
}
namespace isaac::runtime {
struct BitSet128Value { std::uint64_t low, high; };
inline constexpr const char* kBitSet128Metatable = "IsaacRuntime.BitSet128";
void PushBitSet128(lua_State*, const BitSet128Value&);
[[nodiscard]] bool ReadBitSet128(lua_State*, int, BitSet128Value*);
void RegisterBitSet128Api(lua_State*);
}
