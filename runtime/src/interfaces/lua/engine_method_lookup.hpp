#pragma once

// 批次 050（2026-09-19）：把"**模块基址 + 偏移 + 入口 4 字节指纹**"这一条判据抽成一个入口。
//
// 为什么抽：这一批一口气接了 8 个引擎方法，跨越 3 个家族 TU（`isaac_api.cpp` /
// `game_api.cpp` / `remaining_api.cpp`）。同一个判据在三个文件里各写一份，正是项目
// `AGENTS.md` 里点名的"第二份判据"风险 —— 将来判据要收紧（例如加 16 字节指纹校验）时，
// 一定会漏改其中一两处。
//
// ★ 可读性判据**按模板参数传进来**：`IsEngineMemoryReadable` 在四个 API 族里**各自有一份**
// （每个 TU 的匿名命名空间里，语义相同、实现共用 `engine_memory_guard.hpp` 的缓存），
// **不是**头文件里的公共函数 ⇒ 本头文件不能直接调它，也不该在这里再造一份。
// 调用点写：`EngineOffsetAddress<IsEngineMemoryReadable>(kXxxOffset)`。
//
// 判据本身与 `isaac_api.cpp` 里 `AddCoinsMethod()` 的那一份逐字相同：
//   1. `EngineModuleBase()` 非 0，且 `base + offset` 不溢出；
//   2. 该地址可读（调用方传进来的那个判据）；
//   3. 读出的首 4 字节 == 常量里记的入口指纹（小端整字）。
// 三条任一不成立返回 0 —— 调用方据此**什么都不做**，绝不能"反正调一下试试"：
// 偏移落到别的函数上会去改引擎状态，后果不可预期。

#include <cstdint>
#include <cstring>

#include "lua_runtime_state.hpp"

namespace isaac::runtime {

template <bool (*IsReadable)(std::uintptr_t, std::size_t)>
[[nodiscard]] inline std::uintptr_t EngineOffsetAddress(std::uintptr_t offset) noexcept {
    const std::uintptr_t base = LuaRuntime::EngineModuleBase();
    if (base == 0 || base > UINTPTR_MAX - offset) {
        return 0;
    }
    const std::uintptr_t method = base + offset;
    if (!IsReadable(method, sizeof(std::uint32_t))) {
        return 0;
    }
    return method;
}

[[nodiscard]] inline bool EngineEntryWordMatches(std::uintptr_t address,
                                                 std::uint32_t entryWord) noexcept {
    if (address == 0) {
        return false;
    }
    std::uint32_t actual = 0;
    std::memcpy(&actual, reinterpret_cast<const void*>(address), sizeof(actual));
    return actual == entryWord;
}

}  // namespace isaac::runtime
