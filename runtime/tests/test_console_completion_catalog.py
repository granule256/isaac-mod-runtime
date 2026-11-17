"""Portable console completion catalog and provider-port contract."""

from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class ConsoleCompletionCatalogTests(unittest.TestCase):
    def test_fixed_catalog_dispatch_and_portable_provider_port(self):
        code = r'''
#include "infrastructure/console/console_completion_catalog.hpp"
#include "ports/console_completion_catalog_port.hpp"

#include <cassert>
#include <cstring>
#include <string>

using namespace isaac::runtime::console;

struct Visit {
    unsigned count{};
    ConsoleAutocompleteType type{};
    bool sawEmpty{};
    std::string firstDescription;
};

static bool Count(void* user, const char* text, std::size_t textLength,
                  const char* description, std::size_t descriptionLength) {
    auto* visit = static_cast<Visit*>(user);
    (void)text;
    (void)description;
    (void)descriptionLength;
    ++visit->count;
    if (visit->count == 1 && description != nullptr)
        visit->firstDescription.assign(description, descriptionLength);
    if (textLength == 0) visit->sawEmpty = true;
    return true;
}

static bool Provider(ConsoleAutocompleteType type, AutocompleteVisitor visitor,
                     void* user) noexcept {
    auto* visit = static_cast<Visit*>(user);
    visit->type = type;
    return visitor(user, "", 0, "empty", 5);
}

static bool InGame() noexcept { return true; }
static std::uint32_t Language;
static std::uint32_t LanguageProvider() noexcept { return Language; }

static unsigned CommandCount;
static bool Commands(void*, const char* text, std::size_t textLength,
                     const char*, std::size_t) {
    ++CommandCount;
    assert(text != nullptr && textLength != 0);
    return true;
}

int main() {
    static_assert(std::size(kConsoleCompletionStageEntries) == 46);
    static_assert(std::size(kConsoleCompletionGreedStageEntries) == 15);
    static_assert(std::size(kConsoleCompletionGridEntries) == 111);
    static_assert(std::size(kConsoleCompletionDebugFlagEntries) == 14);
    static_assert(std::size(kConsoleCompletionComboEntries) == 16);
    static_assert(std::size(kConsoleCompletionDeliriousEntries) == 62);
    static_assert(std::size(kConsoleCompletionMacroEntries) == 12);
    static_assert(std::size(kConsoleBuiltinCommandMetadata) == 53);

    Visit stage{};
    assert(VisitConsoleCompletionFixedEntries(ConsoleAutocompleteType::Stage, false,
                                              Count, &stage));
    assert(stage.count == 46);
    Visit greed{};
    assert(VisitConsoleCompletionFixedEntries(ConsoleAutocompleteType::Stage, true,
                                              Count, &greed));
    assert(greed.count == 15);
    Visit grid{};
    assert(VisitConsoleCompletionFixedEntries(ConsoleAutocompleteType::Grid, false,
                                              Count, &grid));
    assert(grid.count == 111);
    Visit localizedGrid{};
    assert(VisitConsoleCompletionFixedEntries(ConsoleAutocompleteType::Grid, false,
                                              13, Count, &localizedGrid));
    assert(localizedGrid.firstDescription ==
           "Decoration A 地面装饰 A");

    assert(VisitConsoleBuiltinCommandMetadata(Commands, nullptr));
    assert(CommandCount == 53);
    const ConsoleBuiltinCommandMetadata* giveitem = nullptr;
    for (const auto& command : kConsoleBuiltinCommandMetadata) {
        if (std::strcmp(command.name, "giveitem") == 0) giveitem = &command;
    }
    assert(giveitem != nullptr);
    assert(std::strcmp(giveitem->alias, "g") == 0);
    assert(giveitem->autocompleteType == ConsoleAutocompleteType::Item);

    ResetConsoleCommands();
    EnsureBuiltinConsoleCommands();
    assert(ConsoleCommandCount() == 53);
    const ConsoleCommand* registeredGiveitem = FindConsoleCommand("giveitem");
    assert(registeredGiveitem != nullptr);
    assert(registeredGiveitem->aliases.size() == 1);
    assert(registeredGiveitem->aliases[0] == "g");
    assert(FindConsoleCommand("g") == registeredGiveitem);
    EnsureBuiltinConsoleCommands();
    assert(ConsoleCommandCount() == 53);

    ResetConsoleCommands();
    assert(RegisterConsoleCommand("giveitem", "custom", "custom", false,
                                  static_cast<std::uint32_t>(
                                      ConsoleAutocompleteType::Entity)) ==
           ConsoleCommandRegistration::Added);
    EnsureBuiltinConsoleCommands();
    assert(ConsoleCommandCount() == 53);
    const ConsoleCommand* customGiveitem = FindConsoleCommand("giveitem");
    assert(customGiveitem != nullptr);
    assert(customGiveitem->description == "custom");
    assert(customGiveitem->aliases.empty());

    Visit unbound{};
    assert(!CollectConsoleCompletionCatalog(
        ConsoleAutocompleteType::Item, Count, &unbound));
    assert(!ConsoleCompletionInGame());

    SetConsoleCompletionCatalogProvider(Provider, InGame);
    Visit bound{};
    assert(CollectConsoleCompletionCatalog(ConsoleAutocompleteType::Item,
                                           Count, &bound));
    assert(bound.type == ConsoleAutocompleteType::Item);
    assert(bound.count == 1 && bound.sawEmpty);
    assert(ConsoleCompletionInGame());
    ClearConsoleCompletionCatalogProvider();
    assert(!CollectConsoleCompletionCatalog(
        ConsoleAutocompleteType::Item, Count, &bound));
    assert(!ConsoleCompletionInGame());

    Language = 13;
    SetConsoleCatalogLanguageProvider(LanguageProvider);
    ResetConsoleCommands();
    EnsureBuiltinConsoleCommands();
    const ConsoleCommand* localizedGiveitem = FindConsoleCommand("giveitem");
    assert(localizedGiveitem != nullptr);
    assert(localizedGiveitem->description ==
           "给予角色道具、饰品、卡牌或胶囊");
}
'''
        with tempfile.TemporaryDirectory(prefix="console-completion-catalog-") as folder:
            source = Path(folder) / "test.cpp"
            source.write_text(code)
            binary = Path(folder) / "test"
            command = [
                "c++", "-std=c++20", "-Wall", "-Wextra", "-Werror",
                "-I" + str(ROOT / "src"), "-I" + str(ROOT / "source"),
                str(source), "-o", str(binary),
            ]
            build = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(build.returncode, 0, build.stdout + build.stderr)
            result = subprocess.run([str(binary)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_header_does_not_create_a_static_guard(self):
        with tempfile.TemporaryDirectory(prefix="console-completion-init-") as folder:
            source = Path(folder) / "test.cpp"
            source.write_text(
                '#include "ports/console_completion_catalog_port.hpp"\n'
                '#include "infrastructure/console/console_completion_catalog.hpp"\n'
                "int main(){return 0;}\n"
            )
            obj = Path(folder) / "test.o"
            build = subprocess.run(
                ["c++", "-std=c++20", "-O2", "-I" + str(ROOT / "src"),
                 "-I" + str(ROOT / "source"), "-c", str(source), "-o", str(obj)],
                capture_output=True, text=True)
            self.assertEqual(build.returncode, 0, build.stdout + build.stderr)
            symbols = subprocess.run(
                ["nm", "-u", str(obj)], capture_output=True, text=True, check=True)
            self.assertNotIn("__cxa_guard_", symbols.stdout)


if __name__ == "__main__":
    unittest.main()
