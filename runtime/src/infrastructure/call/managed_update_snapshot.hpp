#pragma once
#include "domain/callback/managed_update_snapshot.hpp"
#include "infrastructure/call/engine_call_access.hpp"

namespace isaac::runtime {
// thunk已由安装器验证；对象检查和帧字段读取共用当前派发的映射缓存。
inline bool ReadNativeManagedUpdateSnapshot(std::uintptr_t game, std::uintptr_t thunk,
    std::uintptr_t frameOffset, ManagedUpdateSnapshot* snapshot,
    engine_memory::ReadableCheck readable) noexcept {
    if (!snapshot) return false;
    *snapshot = {};
    if (!thunk || !engine_memory::PointerUsable(game, readable)) return false;
    using IsPaused = bool (*)(const void*);
    if (engine_call::AsFunction<IsPaused>(thunk)(engine_memory::AsObject(game))) return false;
    std::uint32_t frame{};
    if (!engine_memory::ReadField(game, frameOffset, &frame, readable)) return false;
    *snapshot = {game, frame};
    return true;
}
}
