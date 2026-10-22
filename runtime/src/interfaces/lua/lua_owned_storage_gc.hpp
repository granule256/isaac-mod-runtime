#pragma once

#include <cstddef>
#include <limits>

extern "C" {
#include <lua.h>
}

namespace isaac::runtime {

// 有限堆不能等到紧急GC才处理大块finalizable userdata：紧急GC不运行__gc。
// 只推进正常增量收集，保持正在被引用的对象；显式GCSTOP与finalizer重入均尊重。
// 调用方必须位于Lua保护调用内，允许用户finalizer错误照常向该调用传播。
inline void ProgressGcBeforeOwnedStorage(lua_State* state, std::size_t bytes) {
    if (lua_gc(state, LUA_GCISRUNNING, 0) == 0) return;
    lua_gc(state, LUA_GCSTEP, 0); // GCdebt可能为负；非零STEP只增债务，不保证真正推进。
    const auto kilobytes = bytes / 1024 + (bytes % 1024 != 0 ? 1 : 0);
    const int work = kilobytes > static_cast<std::size_t>(std::numeric_limits<int>::max())
        ? std::numeric_limits<int>::max() : static_cast<int>(kilobytes);
    lua_gc(state, LUA_GCSTEP, work);
}

} // namespace isaac::runtime
