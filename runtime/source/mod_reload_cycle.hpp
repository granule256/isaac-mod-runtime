#pragma once
#include <cstdint>

namespace isaac::runtime {
// 阶段号同时是失败码，保留在独立状态面，旧模组菜单读数布局不移动。
struct ModReloadState {
    std::uint32_t phase{};
    std::uint32_t failure{};
    std::uint32_t attempts{};
    std::uint32_t completed{};
    bool running{};
};

// 只在菜单退出的游戏线程安全点调用。后端负责真实Lua/原生对象，协调器不分配或轮询。
template<class Operations>
bool ApplyModMenuReload(bool edited, ModReloadState& state, Operations& operations) noexcept {
    if (state.running) return false;
    if (!edited) return true;
    state.running = true;
    ++state.attempts;
    state.failure = 0;
    const auto step = [&](std::uint32_t phase, bool result) noexcept {
        if (!result) { state.failure = phase; state.running = false; }
        return result;
    };
    state.phase = 1; if (!step(1, operations.Preflight())) return false;
    state.phase = 2; if (!step(2, operations.Save())) return false;
    state.phase = 3; if (!step(3, operations.CloseLua())) return false;
    state.phase = 4; if (!step(4, operations.CreateLua())) return false;
    state.phase = 5; if (!step(5, operations.ReleaseNative())) return false;
    state.phase = 6; if (!step(6, operations.Load())) return false;
    state.phase = 7;
    ++state.completed;
    state.running = false;
    return true;
}
} // namespace isaac::runtime
