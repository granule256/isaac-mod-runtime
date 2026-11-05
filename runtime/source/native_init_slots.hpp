#pragma once
#include <array>
#include <cstddef>
#include <cstdint>

namespace isaac::runtime {
struct NativeInitSlotIo {
    void* context{};
    std::uintptr_t (*load)(const void*, std::uintptr_t){};
    bool (*compareExchange)(void*, std::uintptr_t, std::uintptr_t, std::uintptr_t){};
};
enum class NativeInitSlotFailure { None, InvalidPlan, GuardMismatch, WriteFailed, RollbackFailed };

// Validate the complete family before publishing any pointer. Rollback only our
// own value: a foreign concurrent writer must never be overwritten.
template<std::size_t N>
NativeInitSlotFailure InstallNativeInitSlotPlan(const NativeInitSlotIo& io,
    const std::array<std::uintptr_t, N>& sites,
    const std::array<std::uintptr_t, N>& expected, std::uintptr_t callback) noexcept {
    if (N == 0 || io.load == nullptr || io.compareExchange == nullptr || callback == 0)
        return NativeInitSlotFailure::InvalidPlan;
    for (std::size_t i = 0; i < N; ++i) {
        if (io.load(io.context, sites[i]) != expected[i]) return NativeInitSlotFailure::GuardMismatch;
    }
    std::size_t committed{};
    for (std::size_t i = 0; i < N; ++i) {
        const bool changed = io.compareExchange(io.context, sites[i], expected[i], callback);
        if (changed) ++committed;
        if (!changed || io.load(io.context, sites[i]) != callback) {
            bool restored = true;
            while (committed != 0) {
                --committed;
                const bool undone = io.compareExchange(io.context, sites[committed], callback, expected[committed]);
                if (!undone || io.load(io.context, sites[committed]) != expected[committed]) restored = false;
            }
            return restored ? NativeInitSlotFailure::WriteFailed : NativeInitSlotFailure::RollbackFailed;
        }
    }
    return NativeInitSlotFailure::None;
}
}
