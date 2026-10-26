#pragma once
#include "native_resource_reload.hpp"
struct TargetModule;
namespace isaac::runtime {
// 固定NRO适配器：调用方负责游戏线程、菜单安全点及GPU完成。
bool PrepareNativeGameResourceReload(const TargetModule& module) noexcept;
bool ReleaseNativeGameResources() noexcept;
bool RestoreNativeGameResources() noexcept;
extern "C" NativeResourceReloadState g_NativeGameResourceReloadState;
} // namespace isaac::runtime
