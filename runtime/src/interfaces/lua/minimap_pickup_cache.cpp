#include "interfaces/lua/minimap_pickup_cache.hpp"

extern "C" {
#include "lua.h"
}

namespace isaac::runtime {
namespace {
// Native notifications and managed flushes run on the game thread.
unsigned g_PendingRerolls{};

void RawField(lua_State* state, int table, const char* field) {
    table = lua_absindex(state, table);
    lua_pushstring(state, field);
    lua_rawget(state, table);
}

bool IntegerField(lua_State* state, int table, const char* field, lua_Integer* value) {
    RawField(state, table, field);
    int valid{};
    *value = lua_tointegerx(state, -1, &valid);
    lua_pop(state, 1);
    return valid != 0;
}

bool AffectedDefinition(lua_State* state, int definition, unsigned kinds) {
    lua_Integer type{}, variant{}, subtype{};
    if (!IntegerField(state, definition, "Type", &type) || type != 5 ||
        !IntegerField(state, definition, "Variant", &variant)) return false;
    // Entity_Pickup::CanReroll(int,int), native 0x276cd0.
    if (variant == 41 || variant == 340 || variant == 370 || variant == 380 ||
        variant == 390) return false;
    if (variant == 100) {
        if ((kinds & static_cast<unsigned>(MinimapPickupReroll::Collectibles)) == 0)
            return false;
        return !IntegerField(state, definition, "SubType", &subtype) ||
               (subtype != 0 && subtype != 668);
    }
    if (variant == -1) {
        // A wildcard may describe an unaffected collectible or quest pickup.
        return false;
    }
    return (kinds & static_cast<unsigned>(MinimapPickupReroll::Pickups)) != 0;
}

void AddIcon(lua_State* state, int definition, int set) {
    RawField(state, definition, "IconID");
    if (lua_type(state, -1) == LUA_TSTRING) {
        lua_pushboolean(state, true);
        lua_rawset(state, set);
    } else {
        lua_pop(state, 1);
    }
}

void AddDefinitions(lua_State* state, int definitions, int affected, int preserved,
                    unsigned kinds, bool grid) {
    if (!lua_istable(state, definitions)) return;
    lua_pushnil(state);
    while (lua_next(state, definitions) != 0) {
        if (lua_istable(state, -1)) {
            const int definition = lua_gettop(state);
            const bool invalidate = !grid && AffectedDefinition(state, definition, kinds);
            AddIcon(state, definition, invalidate ? affected : preserved);
        }
        lua_pop(state, 1);
    }
}

bool ContainsIcon(lua_State* state, int set, int icon) {
    lua_pushvalue(state, icon);
    lua_rawget(state, set);
    const bool contains = lua_toboolean(state, -1);
    lua_pop(state, 1);
    return contains;
}

void InvalidateRoom(lua_State* state, int room, int affected, int preserved) {
    if (!lua_istable(state, room)) return;
    RawField(state, room, "NoUpdate");
    const bool noUpdate = lua_toboolean(state, -1);
    lua_pop(state, 1);
    if (noUpdate) return;
    RawField(state, room, "Descriptor");
    const bool hasDescriptor = !lua_isnil(state, -1) && lua_toboolean(state, -1);
    lua_pop(state, 1);
    if (!hasDescriptor) return;
    RawField(state, room, "ItemIcons");
    if (!lua_istable(state, -1)) {
        lua_pop(state, 1);
        return;
    }
    const int icons = lua_gettop(state);
    const auto count = static_cast<lua_Integer>(lua_rawlen(state, icons));
    lua_Integer kept{};
    for (lua_Integer index = 1; index <= count; ++index) {
        lua_rawgeti(state, icons, index);
        const bool remove = lua_type(state, -1) == LUA_TSTRING &&
                            ContainsIcon(state, affected, lua_gettop(state)) &&
                            !ContainsIcon(state, preserved, lua_gettop(state));
        if (remove) {
            lua_pop(state, 1);
        } else {
            ++kept;
            if (kept != index) lua_rawseti(state, icons, kept);
            else lua_pop(state, 1);
        }
    }
    for (lua_Integer index = kept + 1; index <= count; ++index) {
        lua_pushnil(state);
        lua_rawseti(state, icons, index);
    }
    lua_pop(state, 1);
}

int InvalidateProtected(lua_State* state) {
    const unsigned kinds = static_cast<unsigned>(lua_tointeger(state, 1));
    lua_pushglobaltable(state);
    RawField(state, -1, "MinimapAPI");
    if (!lua_istable(state, -1)) return 0;
    const int api = lua_gettop(state);
    // Build both sets before mutating room snapshots. A shared ID with any grid
    // or unaffected entity definition has ambiguous provenance and is retained.
    lua_newtable(state);
    const int affected = lua_gettop(state);
    lua_newtable(state);
    const int preserved = lua_gettop(state);
    RawField(state, api, "PickupList");
    AddDefinitions(state, lua_gettop(state), affected, preserved, kinds, false);
    lua_pop(state, 1);
    RawField(state, api, "GridEntityList");
    AddDefinitions(state, lua_gettop(state), affected, preserved, kinds, true);
    lua_pop(state, 1);
    RawField(state, api, "Levels");
    if (!lua_istable(state, -1)) return 0;
    const int levels = lua_gettop(state);
    lua_pushnil(state);
    while (lua_next(state, levels) != 0) {
        if (lua_istable(state, -1)) {
            const int rooms = lua_gettop(state);
            lua_pushnil(state);
            while (lua_next(state, rooms) != 0) {
                InvalidateRoom(state, lua_gettop(state), affected, preserved);
                lua_pop(state, 1);
            }
        }
        lua_pop(state, 1);
    }
    return 0;
}
} // namespace

void NoteMinimapPickupReroll(MinimapPickupReroll kind) noexcept {
    g_PendingRerolls |= static_cast<unsigned>(kind);
}

bool HasPendingMinimapPickupReroll() noexcept { return g_PendingRerolls != 0; }

void ResetMinimapPickupCache() noexcept { g_PendingRerolls = 0; }

bool FlushMinimapPickupCache(lua_State* state) noexcept {
    if (g_PendingRerolls == 0) return true;
    if (state == nullptr || !lua_checkstack(state, 3)) return false;
    const int top = lua_gettop(state);
    const unsigned kinds = g_PendingRerolls;
    lua_pushcfunction(state, InvalidateProtected);
    lua_pushinteger(state, kinds);
    const bool success = lua_pcall(state, 1, 0, 0) == LUA_OK;
    lua_settop(state, top);
    if (success) g_PendingRerolls &= ~kinds;
    return success;
}
} // namespace isaac::runtime
