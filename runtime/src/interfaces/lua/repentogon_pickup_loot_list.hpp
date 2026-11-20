#pragma once

#include <cstddef>
#include <cstdint>

struct lua_State;

namespace isaac::runtime {

inline constexpr char kRepentogonLootListMetatable[] =
    "IsaacRuntime.LootList";
inline constexpr char kRepentogonLootListEntryMetatable[] =
    "IsaacRuntime.LootListEntry";

// Pinned Switch std::deque<LootList::Entry> layout.
inline constexpr std::size_t kRepentogonLootListNativeSize = 0x30;
inline constexpr std::size_t kRepentogonLootListEntrySize = 0x18;
inline constexpr std::size_t kRepentogonLootListBlockEntries = 170;

// The active 1334 callback context is the only source of an RNG pointer that
// may be stored in a native LootList entry. A list captures the context at
// LootList() construction. An omitted/nil PushEntry RNG remains null even in a
// scope; a supplied RNG must be an RngHandle that resolves to the same captured
// DropRNG, otherwise PushEntry rejects it.
[[nodiscard]] std::uintptr_t SetRepentogonPickupLootListDropRng(
    std::uintptr_t dropRng) noexcept;

// Registers the native-backed Lua LootList class. The shared callback/API
// registrars remain responsible for calling this at the correct bootstrap
// phase.
void RegisterRepentogonPickupLootList(lua_State* state);

// Moves a native LootList returned by Entity_Pickup::GetLootList into Lua
// ownership. The source object is zeroed on success.
[[nodiscard]] bool PushRepentogonPickupLootList(
    lua_State* state, std::uintptr_t nativeList,
    std::uintptr_t dropRng) noexcept;

// Replaces the native destination with the Lua-built list and zeroes the Lua
// source on success. The destination must be an 8-byte-aligned, valid native
// LootList or an all-zero uninitialized buffer. Before touching the
// destination, every source entry with a non-null RNG must reference both the
// currently active pickup DropRNG and the list's captured DropRNG; otherwise
// the move is rejected.
[[nodiscard]] bool MoveRepentogonPickupLootListToNative(
    lua_State* state, int index, std::uintptr_t destination) noexcept;

#if !defined(__SWITCH__)
struct RepentogonPickupLootListTestBindings {
    std::uintptr_t moduleBase{};
    void (*addBackCapacity)(void*) noexcept{};
    void (*destroy)(void*) noexcept{};
};
void SetRepentogonPickupLootListTestBindings(
    RepentogonPickupLootListTestBindings bindings) noexcept;
#endif

}  // namespace isaac::runtime
