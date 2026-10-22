#pragma once
#include "ports/hook_port.hpp"
#include "domain/console/console_panel_state.hpp"
namespace isaac::runtime {
Status InstallConsoleLifecycleHook(const HookTarget&) noexcept;
namespace console {
using GameFrameFunction=void(*)(void*);
void RenderConsoleAfterGame() noexcept;
inline void RunConsoleGameInput(void* game,GameFrameFunction original) noexcept {
    if (!ConsoleCapturesInput()) original(game);
}
inline void RunConsoleGameUpdate(void* game,GameFrameFunction original) noexcept {
    if (!ConsolePaused()) original(game);
}
inline void RunConsoleGameRender(void* game,GameFrameFunction original) noexcept {
    original(game);
    RenderConsoleAfterGame();
}
}
}
