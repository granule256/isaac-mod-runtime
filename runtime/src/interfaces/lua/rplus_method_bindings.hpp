#pragma once
#include <cstddef>
struct lua_State;
namespace isaac::runtime {std::size_t AttachRPlusMethods(lua_State*,const char*) noexcept;}
