#pragma once
#include <cstddef>
struct lua_State;
namespace isaac::runtime {std::size_t AttachApi300Methods(lua_State*,const char*)noexcept;void PublishApi300Statics(lua_State*,const char*);}
