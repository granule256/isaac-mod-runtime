#pragma once
#include "domain/console/console_completion_rules.hpp"

#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <new>
#include <string>
#include <string_view>
#include <vector>

namespace isaac::runtime::console {

enum class ConsoleAutocompleteType : std::uint8_t {
    None = 0,
    Entity,
    Goto,
    Stage,
    Grid,
    DebugFlag,
    Item,
    Challenge,
    Combo,
    Cutscene,
    Macro,
    Sfx,
    Curse,
    Metro,
    Delirious,
    Player,
    Achievement,
    ModFolder,
    Custom,
    Effect,
};

enum class ConsoleCommandRegistration : std::uint8_t {
    Added,
    Duplicate,
};

// REPENTOGONOptions [VanillaTweaks] ConsoleAutofillLimit:
// default 10, UI range 1..1000. Persisted integers are not clamped on PC.
// The central runtime-options owner is expected
// to parse the persisted value and call SetConsoleAutofillLimit at load/change
// boundaries; the panel itself never performs file I/O.
inline constexpr std::int32_t kConsoleAutofillLimitDefault = 10;
inline constexpr std::int32_t kConsoleAutofillLimitMinimum = 1;
inline constexpr std::int32_t kConsoleAutofillLimitMaximum = 1000;

inline std::int32_t& ConsoleAutofillLimitState() noexcept {
    static std::int32_t value = kConsoleAutofillLimitDefault;
    return value;
}

inline std::int32_t ConsoleAutofillLimit() noexcept {
    return ConsoleAutofillLimitState();
}

inline void SetConsoleAutofillLimit(std::int32_t value) noexcept {
    ConsoleAutofillLimitState() = value;
}

struct ConsoleCommand {
    std::string name;
    std::string description;
    std::string helpText;
    bool showOnMenu{};
    ConsoleAutocompleteType autocompleteType{ConsoleAutocompleteType::None};
    std::vector<std::string> aliases;
};

struct ConsoleMacro {
    std::string name;
    std::vector<std::string> commands;
};

inline std::vector<ConsoleMacro>& ConsoleRegisteredMacros() {
    struct Storage {
        alignas(std::vector<ConsoleMacro>) unsigned char bytes[sizeof(std::vector<ConsoleMacro>)]{};
        std::vector<ConsoleMacro>* value{};
    };
    static Storage storage{};
    if (!storage.value)
        storage.value=::new (static_cast<void*>(storage.bytes)) std::vector<ConsoleMacro>();
    return *storage.value;
}

inline std::uint64_t& ConsoleCommandRevision() noexcept {
    // Reset generation, not insertion count: upstream set insertions leave
    // the selected command and its expanded candidate cache intact.
    static std::uint64_t value{};
    return value;
}

inline std::vector<ConsoleCommand>& ConsoleCommands() {
    // The game thread owns this registry. POD storage avoids __cxa_guard's
    // pthread synchronization in the injected -nostartfiles module.
    struct Storage {
        alignas(std::vector<ConsoleCommand>) unsigned char bytes[sizeof(std::vector<ConsoleCommand>)]{};
        std::vector<ConsoleCommand>* value{};
    };
    static Storage storage{};
    if (!storage.value) {
        storage.value = ::new (static_cast<void*>(storage.bytes)) std::vector<ConsoleCommand>();
    }
    return *storage.value;
}

inline void ResetConsoleCommands() noexcept {
    ConsoleCommands().clear();
    ++ConsoleCommandRevision();
}

inline ConsoleCommandRegistration RegisterConsoleCommand(
    std::string_view name, std::string_view description, std::string_view helpText,
    bool showOnMenu, std::uint32_t autocompleteType) {
    auto& commands = ConsoleCommands();
    for (const auto& command : commands) {
        if (!ConsoleCommandLess(command.name, name) &&
            !ConsoleCommandLess(name, command.name)) {
            return ConsoleCommandRegistration::Duplicate;
        }
    }
    const auto type = autocompleteType <=
            static_cast<std::uint32_t>(ConsoleAutocompleteType::Effect)
        ? static_cast<ConsoleAutocompleteType>(autocompleteType)
        : ConsoleAutocompleteType::None;
    commands.push_back(ConsoleCommand{
        std::string(name), std::string(description), std::string(helpText),
        showOnMenu, type, {}});
    std::sort(commands.begin(), commands.end(),
              [](const auto& left, const auto& right) {
                  return ConsoleCommandLess(left.name, right.name);
              });
    return ConsoleCommandRegistration::Added;
}

inline std::size_t ConsoleCommandCount() noexcept {
    return ConsoleCommands().size();
}

inline const ConsoleCommand* ConsoleCommandAt(std::size_t index) noexcept {
    const auto& commands = ConsoleCommands();
    return index < commands.size() ? &commands[index] : nullptr;
}

inline const ConsoleCommand* FindConsoleCommand(std::string_view name) noexcept {
    for (const auto& command : ConsoleCommands()) {
        if (command.name == name ||
            std::find(command.aliases.begin(), command.aliases.end(), name) !=
                command.aliases.end()) {
            return &command;
        }
    }
    return nullptr;
}

inline std::string BuildConsoleHelp(std::string_view invocation, bool inGame) {
    const auto skipSpace = [](std::string_view text, std::size_t at) {
        while (at < text.size() && (text[at] == ' ' || text[at] == '\t' ||
                                    text[at] == '\r' || text[at] == '\n')) {
            ++at;
        }
        return at;
    };
    std::size_t at = skipSpace(invocation, 0);
    const auto wordStart = at;
    while (at < invocation.size() && invocation[at] != ' ' && invocation[at] != '\t' &&
           invocation[at] != '\r' && invocation[at] != '\n') {
        ++at;
    }
    if (invocation.substr(wordStart, at - wordStart) != "help") {
        return {};
    }
    at = skipSpace(invocation, at);
    const auto commandStart = at;
    while (at < invocation.size() && invocation[at] != ' ' && invocation[at] != '\t' &&
           invocation[at] != '\r' && invocation[at] != '\n') {
        ++at;
    }
    const auto requested = invocation.substr(commandStart, at - commandStart);

    std::vector<const ConsoleCommand*> visible;
    visible.reserve(ConsoleCommands().size());
    for (const auto& command : ConsoleCommands()) {
        if (inGame || command.showOnMenu) {
            visible.push_back(&command);
        }
    }
    std::sort(visible.begin(), visible.end(),
              [](const ConsoleCommand* left, const ConsoleCommand* right) {
                  return ConsoleCommandLess(left->name, right->name);
              });

    std::string result;
    if (!requested.empty()) {
        for (const auto* command : visible) {
            if (command->name == requested) {
                result.append(command->name).append(" - ")
                    .append(command->helpText).push_back('\n');
                break;
            }
        }
        return result;
    }
    for (const auto* command : visible) {
        result.append("  - ").append(command->name).append(" - ")
            .append(command->description).push_back('\n');
    }
    return result;
}

}  // namespace isaac::runtime::console
