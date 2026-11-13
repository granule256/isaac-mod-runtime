#pragma once

#include <cstddef>

namespace isaac::runtime::console {

using AutocompleteVisitor = bool (*)(
    void* user, const char* text, std::size_t textLength,
    const char* description, std::size_t descriptionLength);
using AutocompleteDispatch = bool (*)(
    const char* command, std::size_t commandLength,
    const char* parameters, std::size_t parameterLength,
    AutocompleteVisitor visitor, void* user) noexcept;

// Composition installs this adapter for the live VM, then clears it before GC.
inline AutocompleteDispatch& AutocompleteDispatchSlot() noexcept {
    static AutocompleteDispatch dispatch{};
    return dispatch;
}
inline void SetAutocompleteDispatch(AutocompleteDispatch dispatch) noexcept {
    AutocompleteDispatchSlot() = dispatch;
}
inline bool DispatchAutocomplete(
    const char* command, std::size_t commandLength,
    const char* parameters, std::size_t parameterLength,
    AutocompleteVisitor visitor, void* user) noexcept {
    const auto dispatch = AutocompleteDispatchSlot();
    return dispatch && dispatch(command, commandLength, parameters,
                                parameterLength, visitor, user);
}

}  // namespace isaac::runtime::console
