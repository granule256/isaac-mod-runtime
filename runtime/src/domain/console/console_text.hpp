#pragma once

// 控制台的**纯文本逻辑**：宽字符转换 + 输出行的环形缓冲。
//
// 为什么单独一层：这两件事一个字都不碰引擎（不读内存、不调函数），所以它们能在宿主机上
// 直接测（`runtime/tests/test_console_text.py`）。而"控制台输出到底被切成几行、每行多长"
// 这类事**必须能被测**——真机上看到的只是"屏幕上少了一行"，从现象反推不出来。
//
// 分层依据：`docs/加一个功能模块的做法.md` 第二节（domain = 纯逻辑/数据结构，不碰引擎）。

#include <cstddef>
#include <cstdint>

namespace isaac::runtime::console {

//: 每行最多存多少字节（含结尾的 `\0`）。控制台输出是 ASCII 命令回显，够用。
inline constexpr std::size_t kConsoleLogLineCapacity = 96;
//: 一共保留多少行（环形，最旧的被挤掉）。
inline constexpr std::size_t kConsoleLogLineCount = 12;

// 宽字符 → UTF-8。
//
// ★ 宽度是**查证过的**，不是猜的：引擎那两个软键盘回调收的都是 `wchar_t const*`，而游戏自己
// 那份实现（`Menu_Character::VirtualKeyboardUpdate @ 0x4039A4`）是按 4 字节取元素的
// （`ldr w0, [x21, x24, lsl #2]`），并用 `wcslen` / `towupper` 处理 ⇒ 本平台 `wchar_t` 是
// **4 字节 UTF-32**。所以这里按 `std::uint32_t` 读，不按 UTF-16 读（按 16 位读会把每个 ASCII
// 字符的码位拆成"字符 + NUL"，第一个 NUL 就让整串变空）。
//
// 返回写入 `destination` 的**有效字节数**（不含结尾 `\0`）。参数不合法（空指针/容量 0）返回 0。
// 输出放不下时**截断并照样以 `\0` 收尾**（绝不越界写），返回值即实际写入长度。
[[nodiscard]] inline std::size_t Utf32ToUtf8(const std::uint32_t* source, std::size_t sourceCapacity,
                                            char* destination,
                                            std::size_t destinationCapacity) noexcept {
    if (source == nullptr || destination == nullptr || destinationCapacity == 0) {
        return 0;
    }
    std::size_t written = 0;
    for (std::size_t index = 0; index < sourceCapacity; ++index) {
        const std::uint32_t codePoint = source[index];
        if (codePoint == 0) {
            break;
        }
        // 码位合法性：引擎给的是用户输入，越界码位（或代理区）一律按 U+FFFD 落一个替换字符，
        // 而不是编一个字节序列出来。
        const bool valid = codePoint <= 0x10FFFFU && !(codePoint >= 0xD800U && codePoint <= 0xDFFFU);
        const std::uint32_t point = valid ? codePoint : 0xFFFDU;
        std::uint8_t encoded[4]{};
        std::size_t length = 0;
        if (point < 0x80U) {
            encoded[length++] = static_cast<std::uint8_t>(point);
        } else if (point < 0x800U) {
            encoded[length++] = static_cast<std::uint8_t>(0xC0U | (point >> 6));
            encoded[length++] = static_cast<std::uint8_t>(0x80U | (point & 0x3FU));
        } else if (point < 0x10000U) {
            encoded[length++] = static_cast<std::uint8_t>(0xE0U | (point >> 12));
            encoded[length++] = static_cast<std::uint8_t>(0x80U | ((point >> 6) & 0x3FU));
            encoded[length++] = static_cast<std::uint8_t>(0x80U | (point & 0x3FU));
        } else {
            encoded[length++] = static_cast<std::uint8_t>(0xF0U | (point >> 18));
            encoded[length++] = static_cast<std::uint8_t>(0x80U | ((point >> 12) & 0x3FU));
            encoded[length++] = static_cast<std::uint8_t>(0x80U | ((point >> 6) & 0x3FU));
            encoded[length++] = static_cast<std::uint8_t>(0x80U | (point & 0x3FU));
        }
        if (written + length + 1 > destinationCapacity) {
            break;  // 放不下就停在这里（保留已写入的部分 + 下面补的收尾符）
        }
        for (std::size_t byte = 0; byte < length; ++byte) {
            destination[written++] = static_cast<char>(encoded[byte]);
        }
    }
    destination[written] = '\0';
    return written;
}

//: 控制台输出的行缓冲（环形，最旧的被挤掉）。
struct ConsoleLog {
    char lines[kConsoleLogLineCount][kConsoleLogLineCapacity]{};
    //: 存了多少行（≤ `kConsoleLogLineCount`）。
    std::uint32_t count{0};
    //: **最新**一行的下标。
    std::uint32_t head{0};
    //: 最新那一行还有没有在续写（`Append` 分多次喂进来时用它决定"接着写"还是"起新行"）。
    bool open{false};

    void Clear() noexcept {
        for (std::size_t line = 0; line < kConsoleLogLineCount; ++line) {
            lines[line][0] = '\0';
        }
        count = 0;
        head = 0;
        open = false;
    }

    //: 追加一段 UTF-8 文本，按 `\n` 切行（`\r` 丢掉）。**不清空旧内容**——控制台本来就是滚动的。
    void Append(const char* text, std::size_t length) noexcept {
        if (text == nullptr) {
            return;
        }
        for (std::size_t index = 0; index < length; ++index) {
            const char character = text[index];
            if (character == '\r') {
                continue;
            }
            if (character == '\n') {
                open = false;  // 这一行到此为止；下一段文本会起新行
                continue;
            }
            if (!open) {
                if (count == 0) {
                    head = 0;
                } else {
                    head = (head + 1) % static_cast<std::uint32_t>(kConsoleLogLineCount);
                }
                if (count < kConsoleLogLineCount) {
                    ++count;
                }
                lines[head][0] = '\0';
                open = true;
            }
            std::size_t used = 0;
            while (used + 1 < kConsoleLogLineCapacity && lines[head][used] != '\0') {
                ++used;
            }
            if (used + 1 < kConsoleLogLineCapacity) {
                lines[head][used] = character;
                lines[head][used + 1] = '\0';
            }
        }
    }

    //: 现在存了多少行（≤ `kConsoleLogLineCount`）。
    [[nodiscard]] std::size_t LineCount() const noexcept {
        return count;
    }

    //: `0` = 最旧的一行。越界返回空串（不返回 nullptr，调用点不必再判一次）。
    [[nodiscard]] const char* Line(std::size_t index) const noexcept {
        if (index >= count) {
            return "";
        }
        const std::size_t oldest =
            (head + kConsoleLogLineCount - (count - 1)) % kConsoleLogLineCount;
        return lines[(oldest + index) % kConsoleLogLineCount];
    }
};

}  // namespace isaac::runtime::console