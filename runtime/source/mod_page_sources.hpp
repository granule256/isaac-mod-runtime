#pragma once

// 模组清单 → 原生页条目来源：读每个模组目录的 `metadata.xml` 取 `<name>`，取不到**退目录名**。
//
// 为什么退目录名：`metadata.xml` 在 PC 上就是**可选**的（我们自己的 `mod_discovery_service.hpp`
// 也这么写），而目录名一定存在 ⇒ 退它至少不会在页面上留一行空白。
//
// 读文件走**注入**（`ModPageTextReader`）：真机上是 `GameFileReader::ReadTextFile` 的一层薄包装，
// 宿主测试里是假实现 ⇒ "路径怎么拼、读失败怎么办、名字怎么落进 arena"这些都能离线判死，
// 而真机上只需要验"读得到"这一件事（那是 `ReadTextFile` 自己的既有面）。
//
// 路径口径：`rom:/isaac_mods/mods/<目录名>/metadata.xml`（与运行时读清单的
// `kRomfsModManifestPath` 同一个根，见 `mod_manifest.hpp`）。

#include "mod_display_name.hpp"
#include "mod_page_entries.hpp"

#include <cstddef>
#include <cstdint>
#include <cstring>

namespace isaac::runtime {

//: 读文本的回调：成功时把内容写进 `buffer`（NUL 结尾）并给出长度，返回 true。
using ModPageTextReader = bool (*)(void* context, const char* path, char* buffer,
                                   std::size_t capacity, std::size_t* length);

//: 每个模组目录的 `metadata.xml` 路径都拼在这块缓冲里（用一个就覆盖一个，不长期保存）。
inline constexpr std::size_t kModPageMetadataPathCapacity = 256;
//: `metadata.xml` 的读入上限：它只有几十行，8 KiB 足够；超了就当读不到（退目录名）。
inline constexpr std::size_t kModPageMetadataCapacity = 8192;

//: "先解析挂载、再读"这条纪律的**代码化**（2026-09-19 的教训：`File::OpenRead` 对打开失败
//: 是直接 **Abort**，所以**绝不盲开**文件 —— 必须先问引擎"这个路径有没有挂载实体"）。
//:
//: 返回三态而不是 bool：调用方要能区分"文件本来就没有"（正常，退目录名）与"有文件但读失败"
//: （异常，值得记一笔）—— 混成一个 false 会让"读崩了"看起来像"这个模组没写 metadata.xml"。
enum class MountedReadResult : std::uint32_t {
    Read,             //: 解析到挂载点且读成功
    NotMounted,       //: 引擎说这个路径没有挂载实体 ⇒ 正常情况，调用方退目录名
    ReadFailed,       //: 有挂载实体但读失败（长度/内容不符）⇒ 异常
    InvalidArgument,  //: 参数不合法
};

//: `resolver` = "这个路径解析成什么挂载路径"（真机上是 `ContentGetMountedFilePath`；
//: 返回 false = 没有这个文件）。只有 resolver 说"有"时才调 `reader`。
[[nodiscard]] inline MountedReadResult ResolveThenRead(const char* path,
                                                       bool (*resolver)(void*, const char*, char*,
                                                                        std::size_t),
                                                       void* resolverContext,
                                                       ModPageTextReader reader,
                                                       void* readerContext, char* resolvedBuffer,
                                                       std::size_t resolvedCapacity, char* textBuffer,
                                                       std::size_t textCapacity,
                                                       std::size_t* textLength) noexcept {
    if (path == nullptr || resolver == nullptr || reader == nullptr || resolvedBuffer == nullptr ||
        textBuffer == nullptr) {
        return MountedReadResult::InvalidArgument;
    }
    if (!resolver(resolverContext, path, resolvedBuffer, resolvedCapacity)) {
        return MountedReadResult::NotMounted;
    }
    if (!reader(readerContext, resolvedBuffer, textBuffer, textCapacity, textLength)) {
        return MountedReadResult::ReadFailed;
    }
    return MountedReadResult::Read;
}

//: 把清单里的目录名收集成条目来源。名字写进 `nameArena`（`ModPageEntrySource::displayName`
//: 必须指向**稳定内存**，见 `mod_page_entries.hpp` 的同一条口径）。
//:
//: `enabledFlags` / `outdatedFlags` 由调用方给（它们是"我们清单里的启用状态"，
//: 与 `metadata.xml` 无关）。返回造出来的条数；任何参数不合法 ⇒ 返回 0。
[[nodiscard]] inline std::uint32_t CollectModPageSources(
    ModPageEntrySource* out, std::uint32_t capacity, const char* const* directories,
    std::uint32_t directoryCount, const bool* enabledFlags, const bool* outdatedFlags,
    ModPageTextReader reader, void* readerContext, char* nameArena, std::size_t nameArenaSize,
    char* scratchPath, char* scratchText) noexcept {
    if (out == nullptr || directories == nullptr || reader == nullptr || nameArena == nullptr ||
        scratchPath == nullptr || scratchText == nullptr || capacity == 0) {
        return 0;
    }
    if (directoryCount > capacity) {
        return 0;  // 装不下就整体放弃：半截列表比空列表更容易让人误判
    }
    std::size_t arenaCursor = 0;
    std::uint32_t written = 0;
    constexpr const char* kPrefix = "rom:/isaac_mods/mods/";
    constexpr const char* kSuffix = "/metadata.xml";
    for (std::uint32_t i = 0; i < directoryCount; ++i) {
        const char* directory = directories[i];
        if (directory == nullptr || directory[0] == '\0') {
            return 0;
        }
        // 拼路径：前缀 + 目录名 + 后缀（越界就整体放弃，不做截断）。
        std::size_t cursor = std::strlen(kPrefix);
        const std::size_t directoryLength = std::strlen(directory);
        const std::size_t suffixLength = std::strlen(kSuffix);
        if (cursor + directoryLength + suffixLength + 1 > kModPageMetadataPathCapacity) {
            return 0;
        }
        std::memcpy(scratchPath, kPrefix, cursor);
        std::memcpy(scratchPath + cursor, directory, directoryLength);
        cursor += directoryLength;
        std::memcpy(scratchPath + cursor, kSuffix, suffixLength + 1);

        std::size_t textLength = 0;
        const bool read = reader(readerContext, scratchPath, scratchText,
                                 kModPageMetadataCapacity, &textLength);
        const char* chosen = directory;  // 默认退目录名
        if (read) {
            const std::string_view xml(scratchText, textLength);
            // 注意：这里用**目录名的长度**当上界，名字超长时退目录名而不是截断。
            const std::size_t available = nameArenaSize - arenaCursor;
            char* target = nameArena + arenaCursor;
            const std::size_t need = directoryLength + 1;
            if (available < need) {
                return 0;
            }
            if (ExtractModDisplayName(xml, target, available)) {
                chosen = target;
                arenaCursor += std::strlen(target) + 1;
            }
        }
        if (chosen == directory) {
            if (nameArenaSize - arenaCursor < directoryLength + 1) {
                return 0;
            }
            std::memcpy(nameArena + arenaCursor, directory, directoryLength + 1);
            chosen = nameArena + arenaCursor;
            arenaCursor += directoryLength + 1;
        }
        out[written].displayName = chosen;
        out[written].enabled = enabledFlags != nullptr ? enabledFlags[i] : true;
        out[written].outdated = outdatedFlags != nullptr ? outdatedFlags[i] : false;
        ++written;
    }
    return written;
}

}  // namespace isaac::runtime
