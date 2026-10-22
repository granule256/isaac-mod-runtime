#pragma once
#include <cstdint>
namespace isaac::runtime {
// 外部只读采样：offscreen/screen × Flush/Sync/Acquire × count/ticks/max。
extern std::uint64_t g_NativeShaderClearDetail[2][3][3];
// 0=尚未安装，1=等待动态链接，2=守卫拒绝，3=替换失败已回滚，4=已安装。
extern std::uint32_t g_NativeShaderClearDetailInstallState;
bool InstallNativeClearProbe(std::uintptr_t base) noexcept;
class NativeClearProbeScope {
 int previous_;
 bool active_;
public:
 explicit NativeClearProbeScope(bool offscreen) noexcept;
 ~NativeClearProbeScope();
 NativeClearProbeScope(const NativeClearProbeScope&)=delete;
 NativeClearProbeScope& operator=(const NativeClearProbeScope&)=delete;
};
}
