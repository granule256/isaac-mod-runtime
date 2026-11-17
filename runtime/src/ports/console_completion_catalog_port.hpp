#pragma once

#include "domain/console/console_commands.hpp"
#include "ports/console_autocomplete_port.hpp"

#include <cstddef>

namespace isaac::runtime::console {

// The provider emits raw, display-ready candidates only. Sorting, filtering,
// command-prefix composition, caching, limits and selection stay in the panel.
using ConsoleCompletionCatalogProvider = bool (*)(
    ConsoleAutocompleteType type, AutocompleteVisitor visitor, void* user) noexcept;
using ConsoleCompletionInGameQuery = bool (*)() noexcept;

struct ConsoleCompletionCatalogBindings {
    ConsoleCompletionCatalogProvider collect{};
    ConsoleCompletionInGameQuery inGame{};
};

// Zero-initialized POD storage: no std static constructor or __cxa_guard path.
inline ConsoleCompletionCatalogBindings& ConsoleCompletionCatalogSlot() noexcept {
    static ConsoleCompletionCatalogBindings bindings{};
    return bindings;
}

inline void SetConsoleCompletionCatalogBindings(
    ConsoleCompletionCatalogBindings bindings) noexcept {
    ConsoleCompletionCatalogSlot() = bindings;
}

inline void SetConsoleCompletionCatalogProvider(
    ConsoleCompletionCatalogProvider collect,
    ConsoleCompletionInGameQuery inGame = nullptr) noexcept {
    SetConsoleCompletionCatalogBindings({collect, inGame});
}

inline void ClearConsoleCompletionCatalogProvider() noexcept {
    SetConsoleCompletionCatalogBindings({});
}

[[nodiscard]] inline bool CollectConsoleCompletionCatalog(
    ConsoleAutocompleteType type, AutocompleteVisitor visitor, void* user) noexcept {
    if (visitor == nullptr) return false;
    const auto collect = ConsoleCompletionCatalogSlot().collect;
    return collect != nullptr && collect(type, visitor, user);
}

[[nodiscard]] inline bool ConsoleCompletionInGame() noexcept {
    const auto inGame = ConsoleCompletionCatalogSlot().inGame;
    return inGame != nullptr && inGame();
}

}  // namespace isaac::runtime::console
