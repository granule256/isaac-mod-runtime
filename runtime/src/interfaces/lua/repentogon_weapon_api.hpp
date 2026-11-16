#pragma once

#include <cstdint>

struct lua_State;

namespace isaac::runtime {

void RegisterRepentogonWeaponApi(lua_State* state);

// The firing relay borrows the exact engine weapon for this synchronous
// dispatch. A retained handle cannot read the pointer after the relay returns.
struct WeaponCallbackScope {
    WeaponCallbackScope() = default;
    WeaponCallbackScope(const WeaponCallbackScope&) = delete;
    WeaponCallbackScope& operator=(const WeaponCallbackScope&) = delete;
    ~WeaponCallbackScope();

    void Begin(std::uintptr_t weapon, std::uintptr_t owner, int type) noexcept;
    void Push(lua_State* state) const;

private:
    const WeaponCallbackScope* previous{};
    std::uint64_t generation{};
    std::uintptr_t weapon{};
    std::uintptr_t owner{};
    int type{};

    friend struct WeaponCallbackAccess;
};

}
