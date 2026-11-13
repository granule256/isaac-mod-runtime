#pragma once

#include "ports/console_autocomplete_port.hpp"

#include <cstddef>
#include <cstdint>

namespace LuaRuntime {

inline constexpr std::uint32_t kConsoleAutocompleteCallbackId = 1120;

using ConsoleAutocompleteVisitor = isaac::runtime::console::AutocompleteVisitor;

[[nodiscard]] bool DispatchConsoleAutocomplete(
    const char* command, std::size_t commandLength,
    const char* parameters, std::size_t parameterLength,
    ConsoleAutocompleteVisitor visitor, void* user) noexcept;

}  // namespace LuaRuntime
