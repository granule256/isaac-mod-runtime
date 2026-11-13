"""Focused host tests for XMLData PLAYER records."""

from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "source"


DRIVER = r'''
#include "program/xml_data_store.hpp"

#include <cassert>
#include <cstring>

using namespace isaac::runtime::xml_data;

static bool TranslatePlayer(void* context, const char* category, const char* key, char* out,
                            std::size_t capacity, std::size_t* length) noexcept {
    (void)context;
    if (std::strcmp(category, "Players") != 0) return false;
    const char* text = nullptr;
    if (std::strcmp(key, "ISAAC_NAME") == 0) text = "Isaac";
    if (std::strcmp(key, "THE_SOUL_NAME") == 0) text = "The Soul";
    if (std::strcmp(key, "ISAAC_DESC") == 0) text = "Isaac description";
    if (std::strcmp(key, "ISAAC_BIRTHRIGHT") == 0) text = "The D6";
    if (text == nullptr) return false;
    const std::size_t size = std::strlen(text);
    if (size >= capacity) return false;
    std::memcpy(out, text, size);
    out[size] = '\0';
    *length = size;
    return true;
}

static const char* Attr(const XmlRecord* record, const char* key) {
    if (record == nullptr) return nullptr;
    const auto* attr = record->FindAttribute(key);
    return attr == nullptr ? nullptr : attr->value.c_str();
}

int main() {
    static_assert(static_cast<int>(XmlDataFileKind::Players) == 2);
    const auto players = XmlDataFileKind::Players;
    const XmlNameTranslator translator{nullptr, &TranslatePlayer};
    const char base[] =
        "<players root='gfx/characters/costumes/' portraitroot='gfx/ui/boss/' "
        "nameimageroot='gfx/ui/boss/' bigportraitroot='gfx/ui/stage/'>"
        "<player id='0' name='#ISAAC_NAME' description='#ISAAC_DESC' "
        "birthright='#ISAAC_BIRTHRIGHT' bigportrait='PlayerPortraitBig_Isaac.png' "
        "hideachievement='29' nomarks='1'/>"
        "<player id='40' name='#THE_SOUL_NAME' portrait='PlayerPortrait_TheSoul.png'/>"
        "</players>";
    const char mod[] =
        "<players root='gfx/mod/' portraitroot='gfx/mod/ui/'>"
        "<player id='17' name='Mary' portrait='mary.png' bskinparent='Isaac'>"
        "<hair gfx='mary_hair.png'/></player>"
        "<player name='Peter' portrait='peter.png'/>"
        "</players>";

    ResetXmlDataStore();
    assert(IngestXmlDataFile(players, "BaseGame", false, base, std::strlen(base), translator));
    assert(IngestXmlDataFile(players, "3814598702", true, mod, std::strlen(mod), translator));

    assert(CountEntries(XmlNodeType::Player) == 4);
    const XmlRecord* isaac = FindEntryById(XmlNodeType::Player, 0);
    assert(isaac != nullptr);
    assert(std::strcmp(Attr(isaac, "id"), "0") == 0);
    assert(std::strcmp(Attr(isaac, "name"), "Isaac") == 0);
    assert(std::strcmp(Attr(isaac, "untranslatedname"), "#ISAAC_NAME") == 0);
    assert(std::strcmp(Attr(isaac, "description"), "Isaac description") == 0);
    assert(std::strcmp(Attr(isaac, "untranslateddescription"), "#ISAAC_DESC") == 0);
    assert(std::strcmp(Attr(isaac, "birthright"), "The D6") == 0);
    assert(std::strcmp(Attr(isaac, "untranslatedbirthright"), "#ISAAC_BIRTHRIGHT") == 0);
    assert(std::strcmp(Attr(isaac, "achievement"), "29") == 0);
    assert(std::strcmp(Attr(isaac, "root"), "gfx/characters/costumes/") == 0);
    assert(std::strcmp(Attr(isaac, "portraitroot"), "gfx/ui/boss/") == 0);
    assert(std::strcmp(Attr(isaac, "bigportraitroot"), "gfx/ui/stage/") == 0);
    assert(std::strcmp(Attr(isaac, "sourceid"), "BaseGame") == 0);

    const XmlRecord* soul = FindEntryById(XmlNodeType::Player, 40);
    assert(soul != nullptr);
    assert(std::strcmp(Attr(soul, "name"), "The Soul") == 0);
    assert(std::strcmp(Attr(soul, "sourceid"), "BaseGame") == 0);

    const XmlRecord* mary = FindEntryById(XmlNodeType::Player, 41);
    assert(mary != nullptr);
    assert(std::strcmp(Attr(mary, "id"), "41") == 0);
    assert(std::strcmp(Attr(mary, "relativeid"), "17") == 0);
    assert(std::strcmp(Attr(mary, "name"), "Mary") == 0);
    assert(std::strcmp(Attr(mary, "portrait"), "mary.png") == 0);
    assert(std::strcmp(Attr(mary, "bskinparent"), "Isaac") == 0);
    assert(std::strcmp(Attr(mary, "root"), "gfx/mod/") == 0);
    assert(std::strcmp(Attr(mary, "portraitroot"), "gfx/mod/ui/") == 0);
    assert(std::strcmp(Attr(mary, "sourceid"), "3814598702") == 0);
    const auto* hair = mary->FindChildren("hair");
    assert(hair != nullptr && hair->entries.size() == 1);
    assert(std::strcmp(hair->entries[0].attributes[0].value.c_str(), "mary_hair.png") == 0);

    const XmlRecord* peter = FindEntryById(XmlNodeType::Player, 42);
    assert(peter != nullptr);
    assert(std::strcmp(Attr(peter, "name"), "Peter") == 0);
    assert(Attr(peter, "relativeid") == nullptr);
    assert(FindEntryByOrder(XmlNodeType::Player, 1) == isaac);
    assert(FindEntryByOrder(XmlNodeType::Player, 4) == peter);
    assert(FindEntryByOrder(XmlNodeType::Player, 5) == nullptr);

    // A missing base read must not shift the first mod player below native 41.
    ResetXmlDataStore();
    const char onlyMod[] = "<players><player id='17' name='Mary'/></players>";
    assert(IngestXmlDataFile(players, "3814598702", true, onlyMod, std::strlen(onlyMod),
                             translator));
    const XmlRecord* reserved = FindEntryById(XmlNodeType::Player, 41);
    assert(reserved != nullptr);
    assert(std::strcmp(Attr(reserved, "relativeid"), "17") == 0);

    ResetXmlDataStore();
    assert(CountEntries(XmlNodeType::Player) == 0);
    return 0;
}
'''


class RepentogonXmlDataPlayerTests(unittest.TestCase):
    def test_player_base_and_content_ids_and_fields(self):
        with tempfile.TemporaryDirectory(prefix="xml-players-") as temporary:
            work = Path(temporary)
            driver = work / "player_driver.cpp"
            binary = work / "player_driver"
            driver.write_text(DRIVER, encoding="utf-8")
            self._run(
                [
                    "c++",
                    "-std=c++17",
                    "-Wall",
                    "-Wextra",
                    "-Werror",
                    "-I",
                    str(SOURCE),
                    str(driver),
                    str(SOURCE / "program" / "xml_data_store.cpp"),
                    "-o",
                    str(binary),
                ]
            )
            self._run([str(binary)])

    @staticmethod
    def _run(command: list[str]) -> None:
        result = subprocess.run(command, text=True, capture_output=True)
        if result.returncode != 0:
            raise AssertionError(result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
