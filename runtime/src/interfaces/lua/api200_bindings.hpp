#pragma once
#include <cstddef>
struct lua_State;
namespace isaac::runtime{std::size_t AttachApi200Methods(lua_State*,const char*)noexcept;}

namespace isaac::runtime{void PublishApi200Statics(lua_State*,const char*owner);}
