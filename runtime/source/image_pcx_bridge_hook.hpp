#pragma once

#include "game_file_reader.hpp"

#include <cstring>

namespace isaac::runtime::bridge {

// 挂载解析出来的路径是不是**模组自己的文件**（`rom:/isaac_mods/…`）。
//
// 为什么需要它（2026-09-21，用户装的 `visible tinted rocks` 一个像素都不显示）：
// PC 模组的贴图是 PNG，而它要覆盖的目标在 Switch 版本体是**已存在的 `.pcx`**；
// 桥过去只要 `original(path)` 答得出来就直接交回 ⇒ 模组的 PNG **被静默忽略**。
// 新规则要区分"这个 `.pcx` 是模组自带的（那就用它）"与"这是本体那份（那就该让位给模组的 PNG）"，
// 判据就是这个路径形状。
//
// 依据：`IContentManager::GetMountedFilePath` 返回的是带 `rom:/` 前缀的完整挂载路径，
// 模组文件都在 `rom:/isaac_mods/` 下（Stage147 真机读数，见 `docs/问题与解决记录.md:4872`）。
[[nodiscard]] inline bool IsModMountedPath(const char* mounted) noexcept {
    constexpr char kModsRoot[] = "rom:/isaac_mods/";
    return mounted != nullptr && std::strncmp(mounted, kModsRoot, sizeof(kModsRoot) - 1) == 0;
}

// 把两组绑定交给贴图桥（安装期调用一次）。
//
//   * `fileBindings`   = 读文件那一组（用来读 `.png` 的字节）；
//   * `engineBindings` = 引擎入口那一组（对象级内存加载 / zlib / 路径解析 / 分配释放）。
//
// 传的是 `hook_manager.cpp` 里那两个**静态绑定对象的地址**：桥在回调里现读，
// 所以绑定之后被（重新）发布时不需要再通知，也不会有"拷贝过期"的问题。
// 任一为 nullptr 时桥处于"未挂上"状态：所有回调直接放弃（绝不盲开、绝不乱调引擎）。
void Attach(const GameFileReader::Bindings* fileBindings,
            const GameFileReader::ImagePcxBindings* engineBindings) noexcept;

} // namespace isaac::runtime::bridge
