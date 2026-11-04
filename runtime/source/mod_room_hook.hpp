#pragma once
#include "ports/hook_port.hpp"
#include "application/mod/mod_room_loading.hpp"
namespace isaac::runtime {
Status InstallModRoomPointerHook(const HookTarget&) noexcept;
Status InstallLevelRoomPointerHook(const HookTarget&) noexcept;
Status InstallLevelInitPointerHook(const HookTarget&) noexcept;
}
