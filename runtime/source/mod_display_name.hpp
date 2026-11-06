#pragma once

// 模组**显示名**：从 `metadata.xml` 里取 `<name>`（用户要求："显示名按 PC：读 metadata.xml 里的 `<name>`"）。
//
// ## 为什么单独一个单元
//
// 它是"PC 一致"这条验收里**唯一**能离线验死的一环：模组页那张纸上的字就是它给的。
// 放进探针里写死字符串只能验"页面画得出来"，验不了"名字取得对"。所以抽成纯函数（只吃字节、
// 不碰文件），宿主上逐条判 —— 与 `frame_event_decision.hpp` 同一条做法。
//
// ## 口径（照 Isaac 自己的 `metadata.xml` 写法）
//
// * 找**第一个** `<name…>` 开标签、取到对应的 `</name>`；标签允许带属性（属性忽略）。
// * XML 区分大小写：只认小写 `name`（`<NAME>` 不算）。
// * 结果去首尾空白（含 `\r\n\t`）；`<name/>`、`<name></name>`、找不到 ⇒ 返回 false
//   （调用方退回**目录名** —— 目录名一定存在，比空名字好）。
// * 只解最常见的四个实体引用（`&amp;` `&lt;` `&gt;` `&quot;`）。引擎自己的解析器也只做这一层；
//   多做没证据的部分反而会造出"我们和 PC 不一样"的差异。
//
// ## 已知差异（写在 `api_deviation` 之外，因为这不是 Lua API）
//
// PC 读的是 `metadata.xml` 里 `<name>` 字段，而 **Switch 版引擎整条 mod 管线是死代码**
// （`ModManager::Reset` 无调用者，`ListMods` 只有它一个调用者），所以我们自己解析同一份文件。
// 文件编码按 UTF-8 处理（Isaac 的 metadata.xml 是 UTF-8）；不做编码探测。

#include <cstddef>
#include <string_view>

namespace isaac::runtime {

namespace detail {

inline bool IsXmlSpace(char c) noexcept {
    return c == ' ' || c == '\t' || c == '\r' || c == '\n';
}


}  // namespace detail

//: 把 `xml` 里第一个 `<name>` 的文本写进 `buffer`（NUL 结尾），返回是否成功。
//: 失败（找不到/空/放不下）返回 false，调用方退回目录名。`buffer` 为 nullptr 或容量为 0 也返回 false。
[[nodiscard]] inline bool ExtractModDisplayName(std::string_view xml, char* buffer,
                                               std::size_t capacity,
                                               bool trimWhitespace = true) noexcept {
    if (buffer == nullptr || capacity < 2) {
        return false;
    }
    constexpr std::string_view kOpen = "<name";
    constexpr std::string_view kClose = "</name>";
    const std::size_t open = xml.find(kOpen);
    if (open == std::string_view::npos) {
        return false;
    }
    std::size_t cursor = open + kOpen.size();
    // 开标签允许带属性：一直吃到 `>`（找不到 `>` 就是坏标签，放弃）。
    while (cursor < xml.size() && xml[cursor] != '>') {
        ++cursor;
    }
    if (cursor >= xml.size()) {
        return false;
    }
    // 小写 `name` 的硬判据：`<name` 后面必须紧跟空白或 `>`（挡住 `<names>`、`<namex>`）。
    if (cursor > open + kOpen.size() && !detail::IsXmlSpace(xml[open + kOpen.size()]) &&
        xml[open + kOpen.size()] != '>') {
        return false;
    }
    ++cursor;  // 跳过 `>`
    if (cursor < xml.size() && xml[cursor] == '/') {
        return false;  // `<name/>`：没有文本
    }
    const std::size_t end = xml.find(kClose, cursor);
    if (end == std::string_view::npos || end < cursor) {
        return false;
    }
    // 去首尾空白。
    std::size_t first = cursor;
    std::size_t last = end;
    while (trimWhitespace && first < last && detail::IsXmlSpace(xml[first])) {
        ++first;
    }
    while (trimWhitespace && last > first && detail::IsXmlSpace(xml[last - 1])) {
        --last;
    }
    if (first == last) {
        return false;  // 空名字 ⇒ 让调用方退目录名
    }
    std::size_t written = 0;
    for (std::size_t i = first; i < last; ++i) {
        const char c = xml[i];
        if (c != '&') {
            if (written + 1 >= capacity) {
                return false;
            }
            buffer[written++] = c;
            continue;
        }
        // 实体：只认四个；认不出就原样抄 `&`（与"少做事"的口径一致）。
        struct Entity {
            std::string_view name;
            char replacement;
        };
        constexpr Entity kEntities[] = {{"&amp;", '&'}, {"&lt;", '<'}, {"&gt;", '>'},
                                        {"&quot;", '"'}};
        bool matched = false;
        for (const Entity& entity : kEntities) {
            if (xml.compare(i, entity.name.size(), entity.name) == 0) {
                if (written + 1 >= capacity) {
                    return false;
                }
                buffer[written++] = entity.replacement;
                i += entity.name.size() - 1;
                matched = true;
                break;
            }
        }
        if (!matched) {
            if (written + 1 >= capacity) {
                return false;
            }
            buffer[written++] = c;
        }
    }
    buffer[written] = '\0';
    return true;
}

}  // namespace isaac::runtime
