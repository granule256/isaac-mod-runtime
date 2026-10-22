#pragma once

#include "game_file_reader.hpp"
#include "module_finder.hpp"

#include <atomic>
#include <cstdint>

namespace isaac::runtime::bridge {

// phase：0未准备 / 1正在准备 / 2完整就绪 / 3准备失败。
// failure：0成功 / 1参数或文件通道无效 / 2图片绑定验证失败 /
//          3路径解析入口缺席 / 4PCX读取入口安装失败。
struct ModImageResourcesState {
    std::atomic<std::uint32_t> calls{0};
    std::atomic<std::uint32_t> phase{0};
    std::atomic<std::uint32_t> failure{0};
    std::atomic<std::uint32_t> bindingMask{0};
    std::atomic<std::uint32_t> relayFailure{0};
};
extern ModImageResourcesState g_ModImageResourcesState;

// 调用者必须处于已完成重定位的游戏线程窗口，或既有延迟安装阶段。
// 只有完整读取链就绪后才发布绑定，不会向消费者交付无读取入口的合成文件。
[[nodiscard]] bool PrepareModImageResources(
    const TargetModule& module, const GameFileReader::Bindings* files,
    GameFileReader::ImagePcxBindings* images) noexcept;

} // namespace isaac::runtime::bridge
