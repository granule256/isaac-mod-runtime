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
#include "infrastructure/memory/engine_field_access.hpp"

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
    std::memcpy(&actual, engine_memory::AsObject(address), sizeof(actual));
    return actual == entryWord;
}

// 主动调用仍走原入口，但已安装的中继会改写序言；只接受登记过的回退入口与完整原始指纹。
// fallback由入口中继注册表给出，不能凭ldr/br两条指令就接受陌生补丁。
template <bool (*IsReadable)(std::uintptr_t, std::size_t)>
[[nodiscard]] inline bool EngineEntryOrRelayMatches(std::uintptr_t address,
    const unsigned char* expected, std::size_t bytes, std::uintptr_t fallback) noexcept {
    if (address == 0 || expected == nullptr || bytes != 16 || !IsReadable(address, bytes)) return false;
    if (std::memcmp(engine_memory::AsObject(address), expected, bytes) == 0) return true;
    if (fallback < 32 || !IsReadable(fallback, bytes)) return false;
    std::uint32_t words[2];
    std::uintptr_t slot=0;
    std::memcpy(words, engine_memory::AsObject(address), sizeof(words));
    std::memcpy(&slot, engine_memory::AsObject(address+8), sizeof(slot));
    return words[0] == 0x58000050U && words[1] == 0xD61F0200U && slot == fallback-32 &&
           std::memcmp(engine_memory::AsObject(fallback), expected, bytes) == 0;
}

// 批次 428（2026-10-11）：把"**已通过判据的入口地址**"按**模块基址**缓存起来。
//
// 为什么要有它：API 层归因（`docs/分析-API层归因-三家模组调了哪些接口-20261011.md`）量出
// `EntityPlayer:HasCollectible` **44,744 次/秒**、`EntityPlayer.__index` **65,368 次/秒** ——
// 这两条每秒要重做十几万次"读模块基址 + 判可读（+ 比入口指纹）"。同一个基址下，这些判据的
// **结论恒定**；真正会变的只有"模块被重载/重映射"这一件事，而那件事**一定会换基址**。
//
// 安全边界（三条，缺一不可 —— 这是"把判据换成缓存"，必须说清它凭什么安全）：
//   1. **键是模块基址**：基址变了（重载/重映射/换版本）⇒ 整个作废，重新逐条跑原判据；
//   2. 缓存里只存"**已经通过全部原判据**"的地址 ⇒ 首次调用仍然逐字核对，判据没有少做，
//      只是**结果被记住**；
//   3. 判据不过时返回 0（与不缓存时一字不差），且**不缓存失败** —— 失败每次照原样重新判、
//      照原样记 `EngineRowReject`，所以诊断计数不受影响。
//
// 与既有成例同一口径：`isaac_api.cpp` 里 `Isaac.ExecuteCommand` 的
// `static entries; static resolvedBase; static resolved`（批次 3xx）。
//
// ★ 用法：**每个调用点自己持有一个 `EngineEntrySlot`（静态、零初始化）**，
//   不共享、不上锁 —— Lua 只在托管回调里单线程执行（与去重表同一条理由）。
//   ★★ 结构体刻意**不写成员初始值**：`static EngineEntrySlot slot{};` 走零初始化 ⇒
//   常量初始化 ⇒ 不会生成 `__cxa_guard*`（`-nostartfiles` 模块里的动态初始化会真机黑屏）。
struct EngineEntrySlot {
    std::uintptr_t base;
    std::uintptr_t offset;
    std::uintptr_t address;
    std::uint32_t entryWord;
    bool resolved;
};

//: 取"已校验的入口地址"。同一个 `slot`、同一个 `offset`、同一个基址 ⇒ 直接返回上次的结论。
//: `entryWord != 0` 时做入口指纹核对（`AddCollectibleMethod` 那一类"会改状态"的调用点用它）。
template <bool (*IsReadable)(std::uintptr_t, std::size_t)>
[[nodiscard]] inline std::uintptr_t EngineEntryAddressCached(EngineEntrySlot& slot,
                                                             std::uintptr_t offset,
                                                             std::uint32_t entryWord) noexcept {
    const std::uintptr_t base = LuaRuntime::EngineModuleBase();
    if (base == 0) {
        return 0;
    }
    if (slot.resolved && slot.base == base && slot.offset == offset &&
        slot.entryWord == entryWord) {
        return slot.address;
    }
    const std::uintptr_t address = EngineOffsetAddress<IsReadable>(offset);
    if (address == 0) {
        return 0;                       // ★ 失败不入缓存：下次照原样重判（诊断计数不受影响）
    }
    if (entryWord != 0 && !EngineEntryWordMatches(address, entryWord)) {
        return 0;                       // 同上：入口指纹不符也不入缓存
    }
    slot.base = base;
    slot.offset = offset;
    slot.address = address;
    slot.entryWord = entryWord;
    slot.resolved = true;
    return address;
}

}  // namespace isaac::runtime
