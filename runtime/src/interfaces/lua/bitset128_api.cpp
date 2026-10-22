#include "interfaces/lua/bitset128_api.hpp"
#include "interfaces/lua/owner_binding.hpp"
#include "program/tear_flags_data.hpp"
#include "program/bitset128_bootstrap.hpp"

#include <cstdio>
#include <cstring>

extern "C" {
#include <lauxlib.h>
}

namespace isaac::runtime {
namespace {
using Wide = unsigned __int128;

BitSet128Value* Check(lua_State* state, int index) {
    return static_cast<BitSet128Value*>(luaL_checkudata(state, index, kBitSet128Metatable));
}

Wide Value(const BitSet128Value& value) {
    return (static_cast<Wide>(value.high) << 64) | value.low;
}

int PushWide(lua_State* state, Wide value) {
    PushBitSet128(state, {static_cast<std::uint64_t>(value),
                         static_cast<std::uint64_t>(value >> 64)});
    return 1;
}

int Constructor(lua_State* state) {
    // __call receives the class table first; each signed Lua word keeps all 64 bits.
    PushBitSet128(state, {static_cast<std::uint64_t>(luaL_optinteger(state, 2, 0)),
                         static_cast<std::uint64_t>(luaL_optinteger(state, 3, 0))});
    return 1;
}

int Bor(lua_State* state) {
    return PushWide(state, Value(*Check(state, 1)) | Value(*Check(state, 2)));
}
int Band(lua_State* state) {
    return PushWide(state, Value(*Check(state, 1)) & Value(*Check(state, 2)));
}
int Bxor(lua_State* state) {
    return PushWide(state, Value(*Check(state, 1)) ^ Value(*Check(state, 2)));
}
int Bnot(lua_State* state) {
    return PushWide(state, ~Value(*Check(state, 1)));
}
int Eq(lua_State* state) {
    lua_pushboolean(state, Value(*Check(state, 1)) == Value(*Check(state, 2)));
    return 1;
}
int Lt(lua_State* state) {
    lua_pushboolean(state, Value(*Check(state, 1)) < Value(*Check(state, 2)));
    return 1;
}
int Le(lua_State* state) {
    lua_pushboolean(state, Value(*Check(state, 1)) <= Value(*Check(state, 2)));
    return 1;
}

int Shift(lua_State* state, bool left) {
    const auto value = Value(*Check(state, 1));
    const auto shift = luaL_checkinteger(state, 2);
    auto magnitude = static_cast<std::uint64_t>(shift);
    if (shift < 0) {
        left = !left;
        magnitude = 0 - magnitude; // Unsigned subtraction also handles LUA_MININTEGER.
    }
    return PushWide(state, magnitude >= 128 ? 0 :
                    (left ? value << magnitude : value >> magnitude));
}
int Shl(lua_State* state) { return Shift(state, true); }
int Shr(lua_State* state) { return Shift(state, false); }

int Get(lua_State* state) {
    const auto* value = Check(state, 1);
    const auto bit = luaL_checkinteger(state, 2);
    if (bit < 0 || bit >= 128) return luaL_error(state, "BitSet128 bit index out of range");
    lua_pushboolean(state, ((Value(*value) >> bit) & 1) != 0);
    return 1;
}

int Set(lua_State* state) {
    auto* value = Check(state, 1);
    const auto bit = luaL_checkinteger(state, 2);
    if (bit < 0 || bit >= 128) return luaL_error(state, "BitSet128 bit index out of range");
    const Wide mask = static_cast<Wide>(1) << bit;
    const Wide updated = lua_toboolean(state, 3) ? Value(*value) | mask : Value(*value) & ~mask;
    *value = {static_cast<std::uint64_t>(updated), static_cast<std::uint64_t>(updated >> 64)};
    return 0;
}

int String(lua_State* state) {
    const auto* value = Check(state, 1);
    char text[64];
    std::snprintf(text, sizeof(text), "BitSet128: %016llx%016llx",
                  static_cast<unsigned long long>(value->high),
                  static_cast<unsigned long long>(value->low));
    lua_pushstring(state, text);
    return 1;
}

int Index(lua_State* state) {
    const auto* value = Check(state, 1);
    const char* key = lua_tostring(state, 2);
    if (key != nullptr && std::strcmp(key, "l") == 0) {
        lua_pushinteger(state, static_cast<lua_Integer>(value->low));
        return 1;
    }
    if (key != nullptr && std::strcmp(key, "h") == 0) {
        lua_pushinteger(state, static_cast<lua_Integer>(value->high));
        return 1;
    }
    luaL_getmetatable(state, kBitSet128Metatable);
    lua_pushvalue(state, 2);
    lua_rawget(state, -2);
    return 1;
}

int NewIndex(lua_State* state) {
    auto* value = Check(state, 1);
    const char* key = lua_tostring(state, 2);
    if (key == nullptr || (std::strcmp(key, "l") != 0 && std::strcmp(key, "h") != 0))
        return luaL_error(state, "unknown BitSet128 field");
    const auto word = static_cast<std::uint64_t>(luaL_checkinteger(state, 3));
    if (*key == 'l') value->low = word;
    else value->high = word;
    return 0;
}

constexpr LuaHandlerBinding kBitSet128Handlers[] = {
    {0x0E01010C, &Get},
    {0x0E01010D, &Set},
};
} // namespace

void PushBitSet128(lua_State* state, const BitSet128Value& value) {
    auto* handle = static_cast<BitSet128Value*>(lua_newuserdata(state, sizeof(value)));
    *handle = value;
    luaL_getmetatable(state, kBitSet128Metatable);
    lua_setmetatable(state, -2);
}

bool ReadBitSet128(lua_State* state, int index, BitSet128Value* value) {
    const auto* handle = static_cast<BitSet128Value*>(luaL_testudata(state, index, kBitSet128Metatable));
    if (handle == nullptr || value == nullptr) return false;
    *value = *handle;
    return true;
}

void RegisterBitSet128Api(lua_State* state) {
    luaL_newmetatable(state, kBitSet128Metatable);
    const luaL_Reg methods[] = {
        {"__bor", Bor}, {"__band", Band}, {"__bxor", Bxor}, {"__bnot", Bnot},
        {"__eq", Eq}, {"__lt", Lt}, {"__le", Le}, {"__shl", Shl}, {"__shr", Shr},
        {"__tostring", String}, {"__index", Index}, {"__newindex", NewIndex},
        {nullptr, nullptr},
    };
    luaL_setfuncs(state, methods, 0);
    static_cast<void>(AttachOwnerMethods(state, "BitSet128", kBitSet128Handlers,
                                         sizeof(kBitSet128Handlers) / sizeof(kBitSet128Handlers[0])));
    lua_pop(state, 1);

    lua_newtable(state);
    lua_newtable(state);
    lua_pushcfunction(state, Constructor);
    lua_setfield(state, -2, "__call");
    luaL_getmetatable(state, kBitSet128Metatable);
    lua_setfield(state, -2, "__class");
    lua_setmetatable(state, -2);
    lua_setglobal(state, "BitSet128");

    // 固定PC在native注册后运行main.lua覆写这些元方法；它才是模组真正看到的行为。
    // 完整保留原Lua区块，包括number转换、signed比较、构造缺省和实际移位规则。
    if (luaL_loadbuffer(state, kBitSet128Bootstrap, sizeof(kBitSet128Bootstrap) - 1,
                        "@pc-bitset128-bootstrap.lua") != LUA_OK) {
        lua_error(state);
    }
    lua_call(state, 0, 0);

    lua_newtable(state);
    for (const auto& row : kTearFlagConstants) {
        if (row.bit == -2) {
            lua_pushinteger(state, row.scalar);
        } else {
            const Wide value = row.bit < 0 ? 0 : static_cast<Wide>(1) << row.bit;
            PushWide(state, value);
        }
        lua_setfield(state, -2, row.name);
    }
    // PC aliases share the same mutable value object, rather than a fresh copy.
    lua_getfield(state, -1, "TEAR_MULLIGAN");
    lua_setfield(state, -2, "TEAR_MIGAN");
    lua_getfield(state, -1, "TEAR_BOOMERANG");
    lua_setfield(state, -2, "TEAR_BOMBERANG");
    lua_setglobal(state, "TearFlags");
}
} // namespace isaac::runtime
