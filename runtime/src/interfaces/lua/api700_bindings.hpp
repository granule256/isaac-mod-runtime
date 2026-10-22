#pragma once
#include <cstddef>
struct lua_State;
namespace isaac::runtime{
std::size_t AttachApi700Methods(lua_State*,const char*)noexcept;
void PublishApi700Statics(lua_State*,const char*);
}
