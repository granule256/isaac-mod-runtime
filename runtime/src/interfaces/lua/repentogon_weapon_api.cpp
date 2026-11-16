#include "interfaces/lua/repentogon_weapon_api.hpp"

#include "infrastructure/memory/engine_field_access.hpp"
#include "interfaces/lua/entity_lifetime.hpp"
#include "lua_runtime.hpp"

extern "C" {
#include <lauxlib.h>
}

namespace isaac::runtime {
namespace {
constexpr auto kMetatable = "IsaacRuntime.Weapon";
constexpr std::uintptr_t kOwnerOffset = 0x8;
// Weapon::GetChargeBarAmount @ 0x4a89cc loads this raw charge before dividing
// it by the native max-charge result (0x4a8a04, ldr s2,[x19,#0x20]).
constexpr std::uintptr_t kChargeOffset = 0x20;
constexpr std::uintptr_t kTypeOffset = 0x38;
const WeaponCallbackScope* g_CurrentWeapon{};
std::uint64_t g_WeaponGeneration{};
struct WeaponHandle {
    const WeaponCallbackScope* scope;
    std::uint64_t generation;
    LuaRuntime::EntityLifetimeToken* ownerToken;
};
}

struct WeaponCallbackAccess {
    static int GetCharge(lua_State* state) {
        const auto* handle = static_cast<const WeaponHandle*>(
            luaL_checkudata(state, 1, kMetatable));
        if (!LuaRuntime::IsOnGameThread())
            return luaL_error(state, "Weapon access requires the game thread");
        const auto* scope = g_CurrentWeapon;
        while (scope && scope != handle->scope) scope = scope->previous;
        if (!scope || scope->generation != handle->generation ||
            !EntityLifetimeAlive(handle->ownerToken))
            return luaL_error(state, "Weapon is no longer available");
        std::uintptr_t owner{};
        int type{};
        float charge{};
        const auto read = engine_memory::EngineMemoryReadable;
        if (!engine_memory::ReadField(scope->weapon, kOwnerOffset, &owner, read) ||
            owner != scope->owner ||
            !engine_memory::ReadField(scope->weapon, kTypeOffset, &type, read) ||
            type != scope->type ||
            !engine_memory::ReadField(scope->weapon, kChargeOffset, &charge, read))
            return luaL_error(state, "Weapon is no longer available");
        lua_pushnumber(state, charge);
        return 1;
    }
};

void WeaponCallbackScope::Begin(std::uintptr_t value, std::uintptr_t entity,
                                int weaponType) noexcept {
    weapon = value;
    owner = entity;
    type = weaponType;
    generation = ++g_WeaponGeneration;
    previous = g_CurrentWeapon;
    g_CurrentWeapon = this;
}

WeaponCallbackScope::~WeaponCallbackScope() {
    if (g_CurrentWeapon == this) g_CurrentWeapon = previous;
}

void WeaponCallbackScope::Push(lua_State* state) const {
    auto* handle = static_cast<WeaponHandle*>(lua_newuserdata(state, sizeof(WeaponHandle)));
    *handle = {this, generation, PushEntityLifetimeToken(state, owner)};
    lua_setuservalue(state, -2);
    luaL_setmetatable(state, kMetatable);
}

void RegisterRepentogonWeaponApi(lua_State* state) {
    if (luaL_newmetatable(state, kMetatable)) {
        lua_pushvalue(state, -1);
        lua_setfield(state, -2, "__index");
        lua_pushcfunction(state, &WeaponCallbackAccess::GetCharge);
        lua_setfield(state, -2, "GetCharge");
        lua_pushliteral(state, "Weapon");
        lua_setfield(state, -2, "__name");
    }
    lua_pop(state, 1);
}

}
