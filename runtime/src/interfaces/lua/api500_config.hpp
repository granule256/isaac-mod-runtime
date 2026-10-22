#pragma once
#include <cstdint>
struct lua_State;
namespace isaac::runtime {
int TryPushApi500ConfigField(lua_State*,std::uintptr_t,std::uint32_t,const char*);
bool TryWriteApi500ConfigField(lua_State*,std::uintptr_t,std::uint32_t,const char*);
int Api500ItemConfigCardIsCard(lua_State*);
// 共享实现位于isaac_api.cpp，复用唯一libc++字符串解析器。
void Api500AssignConfigString(lua_State*,std::uintptr_t);
int Api500PushConfigString(lua_State*,std::uintptr_t);
#if !defined(__SWITCH__)
using Api500ConfigStringAssignment=void*(*)(void*,const void*);
void SetApi500ConfigStringAssignmentForTesting(Api500ConfigStringAssignment) noexcept;
#endif
}
