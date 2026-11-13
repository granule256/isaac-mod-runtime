#include "interfaces/lua/repentogon_xml_data_api.hpp"
#include "interfaces/lua/owner_binding.hpp"
#include "program/xml_data_store.hpp"

#include <cstddef>

extern "C" {
#include <lauxlib.h>
#include <lua.h>
}

namespace isaac::runtime {
namespace {

using xml_data::XmlNodeType;
using xml_data::XmlRecord;

void SetIntegerField(lua_State* state, const char* name, int value) {
    lua_pushinteger(state, static_cast<lua_Integer>(value));
    lua_setfield(state, -2, name);
}

void PushRecord(lua_State* state, const XmlRecord* record) {
    if (record == nullptr) {
        lua_pushnil(state);
        return;
    }
    luaL_checkstack(state, 6, "XMLData record");
    lua_newtable(state);
    for (const xml_data::XmlAttribute& attribute : record->attributes) {
        lua_pushlstring(state, attribute.name.data(), attribute.name.size());
        lua_pushlstring(state, attribute.value.data(), attribute.value.size());
        lua_settable(state, -3);
    }
    for (const xml_data::XmlChildGroup& group : record->children) {
        lua_newtable(state);
        lua_Integer index = 1;
        for (const xml_data::XmlChild& child : group.entries) {
            lua_newtable(state);
            for (const xml_data::XmlAttribute& attribute : child.attributes) {
                lua_pushlstring(state, attribute.name.data(), attribute.name.size());
                lua_pushlstring(state, attribute.value.data(), attribute.value.size());
                lua_settable(state, -3);
            }
            lua_rawseti(state, -2, index++);
        }
        lua_setfield(state, -2, group.tag.c_str());
    }
}

int IntegerArgument(lua_State* state, int index, const char* typeName) {
    if (!lua_isnumber(state, index)) {
        return luaL_error(state, "Expected %s as parameter #%d, got %s", typeName, index,
                          lua_typename(state, lua_type(state, index)));
    }
    return static_cast<int>(lua_tonumber(state, index));
}

}  // namespace

int RepentogonXmlDataGetEntityByTypeVarSub(lua_State* state) {
    const int type = IntegerArgument(state, 1, "EntityType");
    const int variant = lua_isnoneornil(state, 2) ? 0 : IntegerArgument(state, 2, "int");
    const int subtype = lua_isnoneornil(state, 3) ? 0 : IntegerArgument(state, 3, "int");
    const bool strict = lua_toboolean(state, 4) != 0;
    PushRecord(state, xml_data::FindEntityByTypeVarSub(type, variant, subtype, strict));
    return 1;
}

int RepentogonXmlDataGetEntryById(lua_State* state) {
    const int nodeType = IntegerArgument(state, 1, "XMLNode");
    const int id = IntegerArgument(state, 2, "number");
    PushRecord(state, xml_data::FindEntryById(static_cast<XmlNodeType>(nodeType), id));
    return 1;
}

int RepentogonXmlDataGetEntryByOrder(lua_State* state) {
    const int nodeType = IntegerArgument(state, 1, "XMLNode");
    const int order = IntegerArgument(state, 2, "int");
    PushRecord(state, xml_data::FindEntryByOrder(static_cast<XmlNodeType>(nodeType), order));
    return 1;
}

int RepentogonXmlDataGetNumEntries(lua_State* state) {
    const int nodeType = IntegerArgument(state, 1, "XMLNode");
    const std::size_t count =
        xml_data::CountEntries(static_cast<XmlNodeType>(nodeType));
    lua_pushinteger(state, static_cast<lua_Integer>(count));
    return 1;
}

int RepentogonIsaacGetGiantBookIdByName(lua_State* state) {
    const auto* record = xml_data::FindGiantBookByName(luaL_checkstring(state, 1));
    lua_pushinteger(state, record ? record->id : -1);
    return 1;
}

int RepentogonIsaacGetAchievementIdByName(lua_State* state) {
    const auto* record = xml_data::FindAchievementByName(luaL_checkstring(state, 1));
    lua_pushinteger(state, record ? record->id : -1);
    return 1;
}

int RegisterRepentogonXmlDataApi(lua_State* state) noexcept {
    if (state == nullptr) return 0;

    lua_newtable(state);
    SetIntegerField(state, "MOD", static_cast<int>(XmlNodeType::Mod));
    SetIntegerField(state, "ENTITY", static_cast<int>(XmlNodeType::Entity));
    SetIntegerField(state, "PLAYER", static_cast<int>(XmlNodeType::Player));
    SetIntegerField(state, "ITEM", static_cast<int>(XmlNodeType::Item));
    SetIntegerField(state, "TRINKET", static_cast<int>(XmlNodeType::Trinket));
    SetIntegerField(state, "PILL", static_cast<int>(XmlNodeType::Pill));
    SetIntegerField(state, "CARD", static_cast<int>(XmlNodeType::Card));
    SetIntegerField(state, "MUSIC", static_cast<int>(XmlNodeType::Music));
    SetIntegerField(state, "SOUND", static_cast<int>(XmlNodeType::Sound));
    SetIntegerField(state, "CHALLENGE", static_cast<int>(XmlNodeType::Challenge));
    SetIntegerField(state, "ITEMPOOL", static_cast<int>(XmlNodeType::ItemPool));
    SetIntegerField(state, "NIGHTMARE", static_cast<int>(XmlNodeType::Nightmare));
    SetIntegerField(state, "COSTUME", static_cast<int>(XmlNodeType::Costume));
    SetIntegerField(state, "NULLCOSTUME", static_cast<int>(XmlNodeType::NullCostume));
    SetIntegerField(state, "WISP", static_cast<int>(XmlNodeType::Wisp));
    SetIntegerField(state, "WISPCOLOR", static_cast<int>(XmlNodeType::WispColor));
    SetIntegerField(state, "CURSE", static_cast<int>(XmlNodeType::Curse));
    SetIntegerField(state, "LOCUST", static_cast<int>(XmlNodeType::Locust));
    SetIntegerField(state, "LOCUSTCOLOR", static_cast<int>(XmlNodeType::LocustColor));
    SetIntegerField(state, "BOMBCOSTUME", static_cast<int>(XmlNodeType::BombCostume));
    SetIntegerField(state, "CRAFTINGRECIPE", static_cast<int>(XmlNodeType::CraftingRecipe));
    SetIntegerField(state, "BOSSPOOL", static_cast<int>(XmlNodeType::BossPool));
    SetIntegerField(state, "BOSSPORTRAIT", static_cast<int>(XmlNodeType::BossPortrait));
    SetIntegerField(state, "CUTSCENE", static_cast<int>(XmlNodeType::Cutscene));
    SetIntegerField(state, "STAGE", static_cast<int>(XmlNodeType::Stage));
    SetIntegerField(state, "BACKDROP", static_cast<int>(XmlNodeType::Backdrop));
    SetIntegerField(state, "ACHIEVEMENT", static_cast<int>(XmlNodeType::Achievement));
    SetIntegerField(state, "GIANTBOOK", static_cast<int>(XmlNodeType::GiantBook));
    SetIntegerField(state, "BOSSRUSHWAVE", static_cast<int>(XmlNodeType::BossRushWave));
    SetIntegerField(state, "PLAYERFORM", static_cast<int>(XmlNodeType::PlayerForm));
    SetIntegerField(state, "NULLITEM", static_cast<int>(XmlNodeType::NullItem));
    SetIntegerField(state, "BOSSCOLOR", static_cast<int>(XmlNodeType::BossColor));
    SetIntegerField(state, "FXLAYER", static_cast<int>(XmlNodeType::FxLayer));
    SetIntegerField(state, "FXPARAM", static_cast<int>(XmlNodeType::FxParam));
    SetIntegerField(state, "FXRAY", static_cast<int>(XmlNodeType::FxRay));
    SetIntegerField(state, "BABY", static_cast<int>(XmlNodeType::Baby));
    lua_setglobal(state, "XMLNode");

    lua_newtable(state);
    static_cast<void>(AttachOwnerMethods(state, "XMLData", nullptr, 0));
    lua_setglobal(state, "XMLData");
    return 0;
}

}  // namespace isaac::runtime
