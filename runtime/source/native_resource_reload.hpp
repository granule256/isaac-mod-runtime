#pragma once
#include <cstdint>

namespace isaac::runtime {
enum class NativeResourceReloadPhase : std::uint32_t { Idle, Prepared, Released, Restored };
struct NativeResourceReloadState {
    std::uintptr_t owner{};
    NativeResourceReloadPhase phase{};
    std::uint32_t failure{};
    std::uint32_t prepares{};
    std::uint32_t releases{};
    std::uint32_t restores{};
};

// 只在重载边界调用；失败后保留待恢复所有者，不能因重试重新析构空对象。
inline bool PrepareNativeResourceOwner(NativeResourceReloadState& state, std::uintptr_t owner) noexcept {
    if (state.phase==NativeResourceReloadPhase::Released) {
        if (state.owner!=owner) { state.failure=1;return false; }
        state.failure=0;
        return true;
    }
    state.owner=owner;
    state.phase=NativeResourceReloadPhase::Prepared;
    state.failure=0;
    ++state.prepares;
    return true;
}

template<class Operations>
bool ReleaseNativeResourceOwner(NativeResourceReloadState& state, Operations& operations) noexcept {
    if (state.phase==NativeResourceReloadPhase::Released) return true;
    if (state.phase!=NativeResourceReloadPhase::Prepared) { state.failure=2;return false; }
    if (state.owner) {
        operations.Destroy(state.owner);
        // 对象存储仍由Game拥有，立即原址构造为空对象，失败路径也没有已析构的成员。
        operations.Construct(state.owner);
        ++state.releases;
    }
    state.phase=NativeResourceReloadPhase::Released;
    state.failure=0;
    return true;
}

template<class Operations>
bool RestoreNativeResourceOwner(NativeResourceReloadState& state, std::uintptr_t owner,
                                Operations& operations) noexcept {
    if (state.owner!=owner) { state.failure=3;return false; }
    if (state.phase==NativeResourceReloadPhase::Restored) return true;
    if (state.phase!=NativeResourceReloadPhase::Released) { state.failure=4;return false; }
    if (state.owner) {
        if (!operations.Load(state.owner)) { state.failure=5;return false; }
        ++state.restores;
    }
    state.phase=NativeResourceReloadPhase::Restored;
    state.failure=0;
    return true;
}
} // namespace isaac::runtime
