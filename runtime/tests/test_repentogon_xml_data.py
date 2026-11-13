"""Host tests for the source-backed XMLData store and Lua facade."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "source"
LUA_ROOT = SOURCE / "third_party" / "lua-5.3.3" / "src"


STORE_DRIVER = r'''
#include "program/xml_data_store.hpp"
#include <cassert>
#include <cstring>
#include <string>

using isaac::runtime::xml_data::FindEntityByTypeVarSub;
using isaac::runtime::xml_data::FindEntryById;
using isaac::runtime::xml_data::FindEntryByOrder;
using isaac::runtime::xml_data::CountEntries;
using isaac::runtime::xml_data::IngestXmlDataFile;
using isaac::runtime::xml_data::ResetXmlDataStore;
using isaac::runtime::xml_data::XmlDataFileKind;
using isaac::runtime::xml_data::XmlNameTranslator;
using isaac::runtime::xml_data::XmlNodeType;
using isaac::runtime::xml_data::XmlRecord;

static bool Translate(void* context, const char* category, const char* key, char* out,
                      std::size_t capacity, std::size_t* length) noexcept {
    (void)context;
    if (std::strcmp(category, "Entities") != 0 || std::strcmp(key, "FROWNING_GAPER") != 0) {
        return false;
    }
    const char text[] = "Frowning Gaper";
    const std::size_t size = sizeof(text) - 1;
    if (size >= capacity) return false;
    std::memcpy(out, text, size);
    out[size] = '\0';
    *length = size;
    return true;
}

static const char* Attr(const XmlRecord* record, const char* key) {
    if (record == nullptr) return nullptr;
    for (const auto& item : record->attributes) {
        if (item.name == key) return item.value.c_str();
    }
    return nullptr;
}

static const char* ChildAttr(const isaac::runtime::xml_data::XmlChild& child,
                             const char* key) {
    for (const auto& item : child.attributes) {
        if (item.name == key) return item.value.c_str();
    }
    return nullptr;
}

int main() {
    ResetXmlDataStore();
    const XmlNameTranslator translator{nullptr, &Translate};
    const char base_entities[] =
        "\xEF\xBB\xBF<?xml version='1.0'?><entities anm2root=\"gfx/\">"
        "<!-- quotes and > inside a comment are ignored -->"
        "<entity id='1' name='Base &amp; One'><gibs amount='2'/></entity>"
        "<entity id='20' name='Base Twenty' variant='0'/>"
        "<entity id='21' name='Base Twenty One'/>"
        "</entities>";
    const char content_entities[] =
        "<entities>"
        "<entity id='1' name='Content One'>"
        "<gibs id='2' name='first' value='7'/>"
        "<gibs id='3' name='second' value='9'/>"
        "</entity>"
        "<entity id='20' name='Content Twenty'/>"
        "<entity id='30' name='#FROWNING_GAPER'/>"
        "</entities>";
    assert(IngestXmlDataFile(XmlDataFileKind::Entities, "BaseGame", false, base_entities,
                             std::strlen(base_entities), translator));
    assert(IngestXmlDataFile(XmlDataFileKind::Entities, "ModA", true, content_entities,
                             std::strlen(content_entities), translator));

    assert(CountEntries(XmlNodeType::Entity) == 6);
    const XmlRecord* base = FindEntityByTypeVarSub(1, 0, 0, true);
    assert(base && std::strcmp(Attr(base, "name"), "Base & One") == 0);
    assert(std::strcmp(Attr(base, "sourceid"), "BaseGame") == 0);
    assert(std::strcmp(Attr(base, "anm2root"), "gfx/") == 0);
    const XmlRecord* remapped = FindEntityByTypeVarSub(1, 1, 0, true);
    assert(remapped && std::strcmp(Attr(remapped, "name"), "Content One") == 0);
    assert(std::strcmp(Attr(remapped, "sourceid"), "ModA") == 0);
    assert(remapped->children.size() == 1 && remapped->children[0].tag == "gibs");
    const auto& gibs = remapped->children[0].entries;
    assert(gibs.size() == 2);
    assert(gibs[0].attributes.size() == 3);
    assert(std::strcmp(ChildAttr(gibs[0], "id"), "2") == 0);
    assert(std::strcmp(ChildAttr(gibs[0], "name"), "first") == 0);
    assert(std::strcmp(ChildAttr(gibs[0], "value"), "7") == 0);
    assert(std::strcmp(ChildAttr(gibs[1], "id"), "3") == 0);
    assert(std::strcmp(ChildAttr(gibs[1], "name"), "second") == 0);
    assert(std::strcmp(ChildAttr(gibs[1], "value"), "9") == 0);
    const XmlRecord* shifted = FindEntityByTypeVarSub(22, 0, 0, true);
    assert(shifted && std::strcmp(Attr(shifted, "name"), "Content Twenty") == 0);
    const XmlRecord* translated = FindEntityByTypeVarSub(30, 0, 0, true);
    assert(translated && std::strcmp(Attr(translated, "name"), "Frowning Gaper") == 0);
    assert(std::strcmp(Attr(translated, "untranslatedname"), "#FROWNING_GAPER") == 0);
    assert(FindEntityByTypeVarSub(999, 0, 0, false) == nullptr);
    assert(FindEntryById(XmlNodeType::Entity, 1) == FindEntityByTypeVarSub(1, 0, 0, false));
    assert(FindEntryByOrder(XmlNodeType::Entity, 1) == base);

    const char base_challenges[] =
        "<challenges version='1'><challenge id='1' name='Base One'/>"
        "<challenge id='4' name='Base Four'/></challenges>";
    const char content_challenges[] =
        "<challenges><challenge id='4' name='Mod Four'/></challenges>";
    assert(IngestXmlDataFile(XmlDataFileKind::Challenges, "BaseGame", false, base_challenges,
                             std::strlen(base_challenges), {}));
    assert(IngestXmlDataFile(XmlDataFileKind::Challenges, "ModA", true, content_challenges,
                             std::strlen(content_challenges), {}));
    assert(CountEntries(XmlNodeType::Challenge) == 3);
    const XmlRecord* challenge = FindEntryById(XmlNodeType::Challenge, 5);
    assert(challenge && std::strcmp(Attr(challenge, "relativeid"), "4") == 0);
    assert(std::strcmp(Attr(challenge, "sourceid"), "ModA") == 0);
    assert(std::strcmp(Attr(FindEntryByOrder(XmlNodeType::Challenge, 1), "name"), "Base One") == 0);
    assert(FindEntryByOrder(XmlNodeType::Challenge, 4) == nullptr);

    const char backdrops[] =
        "<backdrops gfxroot='gfx/backdrop/' gridgfxroot='gfx/grid/'>"
        "<backdrop id='1' gfx='01_Basement.png' walls='1'><prop value='one'/></backdrop>"
        "<backdrop gfx='02_Cellar.png' walls='2'/>"
        "</backdrops>";
    assert(IngestXmlDataFile(XmlDataFileKind::Backdrops, "BaseGame", false, backdrops,
                             std::strlen(backdrops), {}));
    assert(CountEntries(XmlNodeType::Backdrop) == 2);
    const XmlRecord* basement = FindEntryById(XmlNodeType::Backdrop, 1);
    assert(basement && std::strcmp(Attr(basement, "gfxroot"), "gfx/backdrop/") == 0);
    assert(std::strcmp(Attr(basement, "gridgfxroot"), "gfx/grid/") == 0);
    assert(std::strcmp(Attr(basement, "name"), "Basement") == 0);
    assert(basement->children.size() == 1 && basement->children[0].tag == "prop");
    assert(basement->children[0].entries.size() == 1);
    assert(std::strcmp(ChildAttr(basement->children[0].entries[0], "value"), "one") == 0);
    const XmlRecord* cellar = FindEntryById(XmlNodeType::Backdrop, 2);
    assert(cellar && std::strcmp(Attr(cellar, "name"), "Cellar") == 0);

    const char malformed[] = "<entities><entity id='1'";
    assert(!IngestXmlDataFile(XmlDataFileKind::Entities, "Bad", true, malformed,
                              std::strlen(malformed), {}));
    const char doctype[] =
        "<!DOCTYPE entities [<!ENTITY xxe SYSTEM 'file:///etc/passwd'>]><entities/>";
    assert(!IngestXmlDataFile(XmlDataFileKind::Entities, "Bad", true, doctype,
                              std::strlen(doctype), {}));
    assert(CountEntries(XmlNodeType::Item) == 0);
    ResetXmlDataStore();
    assert(CountEntries(XmlNodeType::Entity) == 0);
    return 0;
}
'''


LUA_DRIVER = r'''
#include "interfaces/lua/repentogon_xml_data_api.hpp"
#include "interfaces/lua/owner_binding.hpp"
#include "program/xml_data_store.hpp"
#include <cassert>
#include <cstdio>
#include <cstring>
extern "C" {
#include <lauxlib.h>
#include <lua.h>
#include <lualib.h>
}

using namespace isaac::runtime::xml_data;
namespace isaac::runtime {
std::size_t AttachOwnerMethods(lua_State* state, const char* owner,
                               const LuaHandlerBinding*, std::size_t,
                               const FieldApiRow*, std::size_t,
                               const EngineMethodRow*, std::size_t) noexcept {
    if (state == nullptr || owner == nullptr) return 0;
    if (std::strcmp(owner, "XMLData") != 0) return 0;
    const struct {
        const char* name;
        lua_CFunction handler;
    } methods[] = {
        {"GetEntityByTypeVarSub", RepentogonXmlDataGetEntityByTypeVarSub},
        {"GetEntryById", RepentogonXmlDataGetEntryById},
        {"GetEntryByOrder", RepentogonXmlDataGetEntryByOrder},
        {"GetNumEntries", RepentogonXmlDataGetNumEntries},
    };
    for (const auto& method : methods) {
        lua_pushcfunction(state, method.handler);
        lua_setfield(state, -2, method.name);
    }
    return sizeof(methods) / sizeof(methods[0]);
}
}

int main() {
    const char* entities =
        "<entities anm2root='gfx/'><entity id='1' name='Base One'><gibs amount='2'/></entity>"
        "</entities>";
    const char* content =
        "<entities><entity id='1' name='Content One'>"
        "<gibs id='2' name='first' value='7'/>"
        "<gibs id='3' name='second' value='9'/>"
        "</entity></entities>";
    const char* challenges =
        "<challenges><challenge id='1' name='Base Challenge'/></challenges>";
    const char* backdrops =
        "<backdrops gfxroot='gfx/backdrop/'><backdrop id='1' gfx='01_Basement.png'/></backdrops>";
    ResetXmlDataStore();
    assert(IngestXmlDataFile(XmlDataFileKind::Entities, "BaseGame", false, entities,
                             std::strlen(entities), {}));
    assert(IngestXmlDataFile(XmlDataFileKind::Entities, "ModA", true, content,
                             std::strlen(content), {}));
    assert(IngestXmlDataFile(XmlDataFileKind::Challenges, "BaseGame", false, challenges,
                             std::strlen(challenges), {}));
    assert(IngestXmlDataFile(XmlDataFileKind::Backdrops, "BaseGame", false, backdrops,
                             std::strlen(backdrops), {}));
    auto* state = luaL_newstate();
    luaL_requiref(state, "_G", luaopen_base, 1);
    lua_pop(state, 1);
    assert(isaac::runtime::RegisterRepentogonXmlDataApi(state) == 0);
    const char script[] = R"lua(
        assert(XMLNode.ENTITY == 1 and XMLNode.CHALLENGE == 9 and XMLNode.BACKDROP == 25)
        local base = XMLData.GetEntityByTypeVarSub(1, 0, 0)
        assert(base.name == 'Base One' and base.anm2root == 'gfx/')
        local content = XMLData.GetEntityByTypeVarSub(1, 1, 0)
        assert(content.name == 'Content One' and content.sourceid == 'ModA')
        assert(content.gibs[1].id == '2')
        assert(content.gibs[1].name == 'first')
        assert(content.gibs[1].value == '7')
        assert(content.gibs[2].id == '3')
        assert(content.gibs[2].name == 'second')
        assert(content.gibs[2].value == '9')
        assert(XMLData.GetEntityByTypeVarSub(999) == nil)
        assert(XMLData.GetEntryById(XMLNode.ENTITY, 1).name == 'Base One')
        assert(XMLData.GetNumEntries(XMLNode.CHALLENGE) == 1)
        assert(XMLData.GetEntryByOrder(XMLNode.CHALLENGE, 1).name == 'Base Challenge')
        assert(XMLData.GetEntryByOrder(XMLNode.CHALLENGE, 2) == nil)
        assert(XMLData.GetEntryById(XMLNode.BACKDROP, 1).name == 'Basement')
        assert(XMLData.GetNumEntries(XMLNode.ITEM) == 0)
    )lua";
    const int result = luaL_dostring(state, script);
    if (result != 0) std::fprintf(stderr, "%s\n", lua_tostring(state, -1));
    lua_close(state);
    ResetXmlDataStore();
    return result == 0 ? 0 : 1;
}
'''


def _run(command: list[str], *, cwd: Path | None = None) -> None:
    result = subprocess.run(command, cwd=cwd, text=True, capture_output=True)
    if result.returncode != 0:
        raise AssertionError(result.stdout + result.stderr)


def _build_store(work: Path) -> Path:
    source = work / "store_driver.cpp"
    source.write_text(STORE_DRIVER, encoding="utf-8")
    binary = work / "store_driver"
    includes = (SOURCE, ROOT / "src")
    _run([
        "c++", "-std=c++23", "-Wall", "-Wextra", "-Werror",
        *[f"-I{item}" for item in includes],
        str(source), str(SOURCE / "program" / "xml_data_store.cpp"), "-o", str(binary),
    ])
    return binary


def _build_lua(work: Path) -> Path:
    source = work / "lua_driver.cpp"
    source.write_text(LUA_DRIVER, encoding="utf-8")
    includes = (SOURCE, ROOT / "src", LUA_ROOT, work / "compatibility")
    cxx_flags = [
        "c++", "-std=c++23", "-Wall", "-Wextra", "-Werror", "-DLUA_C89_NUMBERS",
        *[f"-I{item}" for item in includes],
    ]
    objects: list[Path] = []
    for index, unit in enumerate((
        source,
        SOURCE / "program" / "xml_data_store.cpp",
        ROOT / "src" / "interfaces" / "lua" / "repentogon_xml_data_api.cpp",
    )):
        obj = work / f"unit-{index}.o"
        _run([*cxx_flags, "-c", str(unit), "-o", str(obj)])
        objects.append(obj)
    lua_flags = [
        "cc", "-std=c99", "-w", "-DLUA_C89_NUMBERS",
        *[f"-I{item}" for item in includes],
    ]
    for path in sorted(LUA_ROOT.glob("*.c")):
        if path.name in {"lua.c", "luac.c", "liolib.c", "loslib.c",
                         "loadlib.c", "ldblib.c", "linit.c"}:
            continue
        obj = work / f"lua-{path.stem}.o"
        _run([*lua_flags, "-c", str(path), "-o", str(obj)])
        objects.append(obj)
    _run(["c++", *[str(path) for path in objects], "-lm", "-o", str(work / "lua_driver")])
    return work / "lua_driver"


class RepentogonXmlDataTests(unittest.TestCase):
    def test_store_parses_contract_and_rejects_bad_input(self):
        with tempfile.TemporaryDirectory(prefix="isaac-xml-store-") as temporary:
            binary = _build_store(Path(temporary))
            _run([str(binary)])

    def test_lua_facade_exposes_all_four_handlers(self):
        facade = (
            ROOT / "src" / "interfaces" / "lua" / "repentogon_xml_data_api.cpp"
        ).read_text(encoding="utf-8")
        xml_node_global = facade.index('lua_setglobal(state, "XMLNode")')
        attach = facade.index('AttachOwnerMethods(state, "XMLData", nullptr, 0)')
        xml_data_global = facade.index('lua_setglobal(state, "XMLData")')
        self.assertLess(xml_node_global, attach)
        self.assertLess(attach, xml_data_global)
        self.assertNotIn("kXmlDataHandlers", facade)
        self.assertNotIn("lua_pushcfunction(state, RepentogonXmlData", facade)
        self.assertIn("    return 0;\n}", facade)
        with tempfile.TemporaryDirectory(prefix="isaac-xml-lua-") as temporary:
            work = Path(temporary)
            (work / "compatibility").mkdir()
            (work / "compatibility" / "stdfloat").write_text(
                "#pragma once\nnamespace std { using float16_t = float; using float128_t = long double; }\n",
                encoding="utf-8",
            )
            binary = _build_lua(work)
            _run([str(binary)])


if __name__ == "__main__":
    unittest.main()
