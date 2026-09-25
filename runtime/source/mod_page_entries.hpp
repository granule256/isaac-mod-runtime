#pragma once

// **原生模组页的条目布局**（把"静态看出来的结构"固化成代码 + 门禁）。
//
// ## 这些偏移是怎么来的（可复核）
//
// `Menu_Mods::Render` 的反汇编（`tools/nro_disasm.py 0x4107C4`）逐条给出：
//
//     ldp  x9, x8, [x27]        ; x27 = g_Manager + 0x36800 → begin / end（元素 8 字节）
//     asr  x8, x8, #3           ; 个数 = (end - begin) / 8
//     ldr  x8, [x23, x19, lsl #3]   ; 取第 i 个条目指针
//     ldrb w10, [x9, #0x18]!        ; 条目的 `std::string`：字节 0 的 **bit0 = 长短标记**
//     add  x4, x9, #1               ; 短串：数据紧跟在标记后面
//     ldr  x4, [x8, #0x28]          ; 长串：数据指针在字符串 +0x10 = 条目 +0x28
//     snprintf(dst, 64, "%d.%s", i+1, x4)
//     ldrb w9, [x8, #0x138]         ; 启用位（0 走另一套颜色）
//     ldrb w8, [x8, #0x13a]         ; "旧版"位 ⇒ 名字后拼 "%s[Old]"
//
// 我们**只用长串形态**：字节 0 置 `0x01`，数据指针放 `+0x28`。理由：短串有长度上限
// （libc++ 的短串容量 22 字节），而模组名是中文/英文都可能很久，统一走长串就不用分情况；
// `Render` 只把那个指针当 **C 串**用（`%s`），所以长度字段填自洽值即可。
//
// ## 这个单元的边界
//
// 它**不管**名字从哪来（清单、`metadata.xml`、目录名都由调用方决定），也不碰文件与引擎内存 ——
// 只把"给定若干条目、把它们按上面的布局写进一块内存"这件事写对，因而能在宿主上逐字节判。

#include <cstddef>
#include <cstdint>
#include <cstring>

namespace isaac::runtime {

//: 每个条目的步长。用到的最高偏移是 `0x13a`（旧版位）⇒ 0x140 足够且对齐好看。
inline constexpr std::size_t kModPageEntryStride = 0x140;
//: `std::string` 在条目里的偏移。
inline constexpr std::size_t kModPageEntryStringOffset = 0x18;
//: 长串形态的数据指针：字符串 +0x10。
inline constexpr std::size_t kModPageEntryStringDataOffset = kModPageEntryStringOffset + 0x10;
//: 启用位 / "旧版"位。
inline constexpr std::size_t kModPageEntryEnabledOffset = 0x138;
inline constexpr std::size_t kModPageEntryOldOffset = 0x13a;

//: 调用方给的条目来源（名字必须是 NUL 结尾的 C 串；`enabled` / `outdated` 就是页面上那两个分支）。
struct ModPageEntrySource {
    const char* displayName;
    bool enabled;
    bool outdated;
};

//: 把一个条目的名字写成"libc++ 长串形态"（`Render` 读的那三处：标记位、长度、数据指针）。
//:
//: **为什么单独抽出来**（批次 126）：条目表只在进页面时造一次，而"控制台开关"那一行的名字
//: **跟着开关状态走**（`Console: ON` / `Console: OFF`）⇒ 需要一个"事后换名字"的动作。
//: 那个动作与"造条目"必须写**同一套字节**，否则两处任一处歪掉都会变成"页面上名字乱码"，
//: 而真机上很难看出是哪一处 ⇒ 合成一个函数，只有这一个地方碰那几个偏移。
//:
//: `name` 必须是**静态存储**的 C 串：`Render` 直接把那个指针当 `%s` 用，指到临时缓冲上下一帧就悬垂。
inline void SetModPageEntryName(std::uint8_t* entry, const char* name) noexcept {
    if (entry == nullptr || name == nullptr || name[0] == '\0') {
        return;  // 空名字会让页面上多一行空白；调用方给的常量不可能是空的，这里只兜"误传"
    }
    const std::size_t length = std::strlen(name);
    // libc++ `std::string` 长串形态：bit0 = 1（`Render` 就是 `tbnz w10, #0`）。
    entry[kModPageEntryStringOffset] = 0x01;
    const std::uint64_t capacity = static_cast<std::uint64_t>(length);
    std::memcpy(entry + kModPageEntryStringOffset + 0x08, &capacity, sizeof(capacity));
    const auto data = reinterpret_cast<std::uintptr_t>(name);
    std::memcpy(entry + kModPageEntryStringDataOffset, &data, sizeof(data));
}

//: 造好 `count` 个条目、写指针数组，并把 `begin/end/cap` 三个字写进 `vector`（= `g_Manager+0x36800`）。
//:
//: 返回实际写好的条目数；**空间不够时返回 0**（调用方据此放弃，绝不写半截 —— 半截的后果是
//: 页面读到野指针）。`nameArena` 用来放名字副本：条目的数据指针必须指向**稳定**的内存
//: （`std::string` 的语义是"它拥有那块内存"，让指针指向调用方的临时缓冲会在下一帧变成悬垂）。
[[nodiscard]] inline std::uint32_t BuildModPageEntries(
    std::uint8_t* entries, std::uintptr_t* pointers, std::uintptr_t* vector,
    std::uint32_t count, const ModPageEntrySource* sources, char* nameArena,
    std::size_t nameArenaSize, std::size_t* nameBytesUsed) noexcept {
    if (nameBytesUsed != nullptr) {
        *nameBytesUsed = 0;
    }
    if (entries == nullptr || pointers == nullptr || vector == nullptr || sources == nullptr ||
        nameArena == nullptr || count == 0) {
        return 0;
    }
    // 先算名字总量，放不下就整体放弃（不做"部分成功"）。
    std::size_t needed = 0;
    for (std::uint32_t i = 0; i < count; ++i) {
        const char* name = sources[i].displayName;
        if (name == nullptr || name[0] == '\0') {
            return 0;
        }
        needed += std::strlen(name) + 1;
    }
    if (needed > nameArenaSize) {
        return 0;
    }
    std::size_t arenaCursor = 0;
    for (std::uint32_t i = 0; i < count; ++i) {
        std::uint8_t* entry = entries + static_cast<std::size_t>(i) * kModPageEntryStride;
        std::memset(entry, 0, kModPageEntryStride);
        const char* name = sources[i].displayName;
        const std::size_t length = std::strlen(name);
        char* stored = nameArena + arenaCursor;
        std::memcpy(stored, name, length + 1);
        arenaCursor += length + 1;
        SetModPageEntryName(entry, stored);  // 字节写法只此一处（见上面那条注释）
        entry[kModPageEntryEnabledOffset] = sources[i].enabled ? 1 : 0;
        entry[kModPageEntryOldOffset] = sources[i].outdated ? 1 : 0;
        pointers[i] = reinterpret_cast<std::uintptr_t>(entry);
    }
    const std::uintptr_t begin = reinterpret_cast<std::uintptr_t>(&pointers[0]);
    const std::uintptr_t end = begin + sizeof(std::uintptr_t) * count;
    std::memcpy(vector, &begin, sizeof(begin));
    std::memcpy(reinterpret_cast<std::uint8_t*>(vector) + sizeof(begin), &end, sizeof(end));
    std::memcpy(reinterpret_cast<std::uint8_t*>(vector) + 2 * sizeof(begin), &end, sizeof(end));
    if (nameBytesUsed != nullptr) {
        *nameBytesUsed = arenaCursor;
    }
    return count;
}

}  // namespace isaac::runtime
