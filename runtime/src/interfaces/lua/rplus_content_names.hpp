#pragma once
#include <cstddef>
#include <cstdint>
struct lua_State;
namespace isaac::runtime {
// 真实配置边界可立即刷新，或显式标记变更后由首个查询刷新一次；稳定帧不重扫。
bool RefreshRuntimeContentNames() noexcept;
void ClearRuntimeContentNames() noexcept;
void InvalidateRuntimeContentNames() noexcept;
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
