#pragma once
#include <cstddef>
#include <cstdint>
struct lua_State;
namespace isaac::runtime {
// 只能在真实配置装载完成的边界调用；查询不隐式重扫配置。
bool RefreshRuntimeContentNames() noexcept;
void ClearRuntimeContentNames() noexcept;
int RuntimeGetPillEffectByName(lua_State*);
int RuntimeGetEntityTypeByName(lua_State*);
int RuntimeGetEntityVariantByName(lua_State*);
struct RuntimeContentNameStats {
    std::size_t entries{},nameBytes{},allocationBytes{};
    std::uint64_t refreshes{};
    bool ready{};
};
RuntimeContentNameStats RuntimeContentNameStatsSnapshot() noexcept;
#if !defined(__SWITCH__)
void SetRuntimeContentNameAllocationFailureForTest(bool) noexcept;
#endif
}
