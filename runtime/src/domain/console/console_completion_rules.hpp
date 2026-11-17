#pragma once

#include "third_party/natural_sort/natural_sort.hpp"

#include <algorithm>
#include <cctype>
#include <string>
#include <string_view>
#include <vector>

namespace isaac::runtime::console {

inline bool ConsoleCommandLess(std::string_view left, std::string_view right) {
    return SI::natural::compare(left, right);
}

inline bool ConsoleCompletionLess(std::string_view left, std::string_view right) {
    std::string first(left), second(right);
    std::replace(first.begin(), first.end(), '.', '-');
    std::replace(second.begin(), second.end(), '.', '-');
    return ConsoleCommandLess(first, second);
}

// ConsoleMega splits on literal spaces and strips whitespace inside each token.
// Repeated/leading spaces produce empty tokens; a final space adds no token.
inline std::vector<std::string> ParseConsoleCompletion(std::string_view input) {
    std::vector<std::string> tokens;
    for (std::size_t start = 0; start < input.size();) {
        const auto end = input.find(' ', start);
        std::string token(input.substr(start, end == std::string_view::npos
            ? input.size() - start : end - start));
        token.erase(std::remove_if(token.begin(), token.end(),
            [](unsigned char ch) { return std::isspace(ch) != 0; }), token.end());
        tokens.push_back(std::move(token));
        if (end == std::string_view::npos) break;
        start = end + 1;
    }
    return tokens;
}

inline std::string JoinConsoleCompletionArguments(
    const std::vector<std::string>& tokens) {
    std::string result;
    for (std::size_t i = 1; i < tokens.size(); ++i) {
        if (i > 1) result.push_back(' ');
        result.append(tokens[i]);
    }
    return result;
}

inline std::size_t ConsoleCompletionUtf8Prefix(
    std::string_view text, std::size_t capacity) noexcept {
    if (text.size() <= capacity) return text.size();
    auto length = capacity;
    while (length && (static_cast<unsigned char>(text[length]) & 0xc0U) == 0x80U)
        --length;
    return length;
}

}  // namespace isaac::runtime::console
