#pragma once
#include "domain/runtime/status.hpp"
#include <cstdint>
struct lua_State;
namespace isaac::runtime {
inline constexpr char kRuntimeOptionsFileName[]="isaac-runtime-options.ini";
// 存档端口接好后的游戏线程加载边界；同提供方已加载时幂等，绝不在getter隐式读文件。
Status LoadRuntimeOptions() noexcept;
// 保存/退出/卸载边界合并提交；失败保留dirty，供下一个明确保存边界重试。
Status FlushRuntimeOptions() noexcept;
// 仅在已完成Flush的真正会话结束或宿主模拟重启时清理。
void ClearRuntimeOptions() noexcept;
int TryPushRuntimeOption(lua_State*,const char* name);
bool TryWriteRuntimeOption(lua_State*,const char* name);
struct RuntimeOptionStats {std::int32_t mode,persisted;bool ready,dirty;std::uint64_t reads,writes;StatusCode lastStatus;};
RuntimeOptionStats RuntimeOptionStatsSnapshot() noexcept;
}
