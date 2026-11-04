#pragma once

struct lua_State;

namespace isaac::runtime {

enum class MinimapPickupReroll : unsigned { Pickups = 1, Collectibles = 2 };

// Native completion only records work; it never enters Lua or allocates.
void NoteMinimapPickupReroll(MinimapPickupReroll kind) noexcept;
bool HasPendingMinimapPickupReroll() noexcept;
void ResetMinimapPickupCache() noexcept;

// Call at a safe managed Lua boundary before room snapshots/render callbacks.
// Lua errors are protected; failed work remains pending for a later attempt.
bool FlushMinimapPickupCache(lua_State* state) noexcept;

} // namespace isaac::runtime
