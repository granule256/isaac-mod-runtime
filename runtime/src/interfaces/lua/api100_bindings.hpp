#pragma once
#include <cstddef>
struct lua_State;
namespace isaac::runtime{std::size_t AttachApi100Methods(lua_State*,const char*) noexcept;}
