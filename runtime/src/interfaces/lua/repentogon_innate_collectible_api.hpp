#pragma once

#include <cstdint>
struct lua_State;

namespace isaac::runtime {
int RepentogonEntityPlayerAddInnateCollectible(lua_State*);

#if !defined(__SWITCH__)
struct InnateCollectibleTestBindings {
    std::uintptr_t (*collectible)(std::int32_t){};
    void (*addCostume)(void*, const void*, bool){};
    void (*evaluate)(void*){};
};
void SetInnateCollectibleTestBindings(InnateCollectibleTestBindings) noexcept;
#endif
}  // namespace isaac::runtime
