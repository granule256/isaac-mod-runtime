#pragma once
#include <cstdint>
#include <type_traits>
struct lua_State;
namespace isaac::runtime::api100_native {
struct Entry {std::uintptr_t offset;const std::uint8_t* guard;};
struct Cache {std::uintptr_t base;bool valid;};
static_assert(std::is_trivial_v<Cache>);
// One shared guard body keeps 100 constant-argument handlers from duplicating it at -O3.
std::uintptr_t Resolve(lua_State*,const Entry&,Cache&,std::uintptr_t host=0);
}
