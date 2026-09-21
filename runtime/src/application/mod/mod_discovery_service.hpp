#pragma once

#include "application/mod/manifest_service.hpp"
#include "domain/runtime/status.hpp"
#include "ports/mod_directory_port.hpp"

#include <cstddef>
#include <string_view>

namespace isaac::runtime {

// 自动发现模组（2026-09-16，方案 A）：把 `isaac_mods/mods/` 下的**每个子目录**当成一个模组。
//
// PC 的语义就是这样：`mods/` 下的文件夹就是一个模组（`metadata.xml` 是可选的），
// 玩家"把模组文件夹丢进去"就装好了。我们要让 Switch 侧也一样，**清单因此降级成可选项**：
//   * 有清单 ⇒ 按清单（顺序、开关都由清单说了算，向后兼容）；
//   * 没有清单（或读不出来/解析失败）⇒ 自己列目录，按名字升序全部加载。
//
// 这一步**只做发现与路径拼装**，不读入口脚本、不碰 Lua —— 与 `ManifestService` 同层次，
// 所以它产出的东西可以直接交给 `ModLoadService::LoadAll`（同一个 `ResolvedManifestModBatch`）。
//
// 入口脚本一律**假定存在**：真缺了（纯资源型模组）`ModLoadService` 会如实报
// `EntryAbsent` 并把内容挂载点保留 —— 这正是 PC 上"只带 resources 的模组"的行为。
class ModDiscoveryService {
public:
    explicit ModDiscoveryService(IModDirectoryPort& directories) noexcept
        : directories_(directories) {}

    // 扫 `isaac_mods/mods` 并把发现的每个子目录填进 `batch`（名字升序，保证顺序确定）。
    //
    // 失败语义：目录一个都没有 ⇒ `NotFound`（与"清单里一个 enabled 都没有"同一个口径）；
    // 个数超过 `batch` 的容量 ⇒ `CapacityExceeded`（**不截断**，见端口的注释）。
    [[nodiscard]] Status Discover(ResolvedManifestModBatch* batch) const noexcept;

    // 把清单里**没有列出**（且没有被显式关掉）的目录追加到已解析的批次后面（2026-09-21）。
    //
    // 用途：清单存在时也要让"刚拷进 `mods/` 的目录"生效（PC 语义："丢进文件夹就装好了"）。
    // 顺序：清单里的保持原样在前，追加的按名字升序在后（顺序确定，不看引擎给的顺序）。
    // 失败（列不出目录 / 装不下）时调用方按 best-effort 处理：清单那一批照常加载，错误进诊断。
    [[nodiscard]] Status AppendUnlisted(ResolvedManifestModBatch* batch) const noexcept;

private:
    IModDirectoryPort& directories_;
};

} // namespace isaac::runtime
