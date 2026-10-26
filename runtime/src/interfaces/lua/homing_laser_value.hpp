#pragma once
#include <cstddef>
#include <cstdint>
struct lua_State;
namespace isaac::runtime {
int PushHomingLaserValue(lua_State*,std::uintptr_t entity);
void WriteHomingLaserValue(lua_State*,std::uintptr_t entity,int valueIndex);
#if !defined(__SWITCH__)
// 只替代跨SDK分配器关系解析；字段、布局守卫、原生内存和事务提交均使用生产路径。
void SetHomingLaserAllocatorTestBindings(void*(*allocate)(std::size_t),void(*release)(void*)) noexcept;
#endif
}
