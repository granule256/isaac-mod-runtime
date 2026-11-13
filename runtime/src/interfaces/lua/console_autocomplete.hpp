#pragma once

#include <cstddef>
#include <cstdint>

namespace LuaRuntime {

inline constexpr std::uint32_t kConsoleAutocompleteCallbackId = 1120;

using ConsoleAutocompleteVisitor = bool (*)(
    void* user, const char* text, std::size_t textLength,
    const char* description, std::size_t descriptionLength);

[[nodiscard]] bool DispatchConsoleAutocomplete(
    const char* command, std::size_t commandLength,
    const char* parameters, std::size_t parameterLength,
    ConsoleAutocompleteVisitor visitor, void* user) noexcept;

}  // namespace LuaRuntime
