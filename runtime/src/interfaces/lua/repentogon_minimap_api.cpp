#include "interfaces/lua/repentogon_minimap_api.hpp"

#include "infrastructure/call/engine_call_access.hpp"
#include "infrastructure/memory/engine_field_access.hpp"
#include "interfaces/lua/api100_native.hpp"
#include "interfaces/lua/vector_api.hpp"
#include "lua_runtime.hpp"

#include <cstdint>

extern "C" {
#include <lauxlib.h>
}

namespace isaac::runtime {
namespace {

// The Switch Game owns the Minimap inline. Minimap::Update reads the state
// at 0x41ccd0 and updates the shake Vector2 through its address at 0x41ce98.
constexpr std::uintptr_t kGameMinimapOffset = 0x24ee70;
constexpr std::uintptr_t kStateOffset = 0;
constexpr std::uintptr_t kShakeOffset = 0x794;

constexpr std::uint8_t kDisplayedSizeGuard[] = {
    0xff, 0xc3, 0x00, 0xd1, 0xe8, 0x0b, 0x00, 0xfd,
    0xf3, 0x17, 0x00, 0xf9, 0xfd, 0xfb, 0x01, 0xa9,
};
constexpr api100_native::Entry kDisplayedSizeEntry{0x41a9cc, kDisplayedSizeGuard};
api100_native::Cache g_DisplayedSizeCache{};

// KAGE::Math::Vector2 is a homogeneous aggregate returned in s0/s1.
using DisplayedSize = RepentogonMinimapVector (*)(void*);
#if !defined(__SWITCH__)
DisplayedSize g_DisplayedSizeHost{};
#endif

std::uintptr_t CurrentMinimap(lua_State* state) {
    if (!LuaRuntime::IsOnGameThread()) {
        luaL_error(state, "Minimap requires the game thread");
    }
    std::uintptr_t ownerSlot{}, game{};
    if (!engine_memory::ReadAt(LuaRuntime::GameOwnerSlot(), &ownerSlot,
                               engine_memory::EngineMemoryReadable) ||
        !ownerSlot || !engine_memory::ReadAt(ownerSlot, &game,
                                            engine_memory::EngineMemoryReadable) ||
        !game || game > UINTPTR_MAX - kGameMinimapOffset ||
        !engine_memory::EngineMemoryReadable(
            game + kGameMinimapOffset, kShakeOffset + sizeof(RepentogonMinimapVector))) {
        luaL_error(state, "Minimap game is unavailable");
    }
    return game + kGameMinimapOffset;
}

template<class T>
T ReadMinimapField(lua_State* state, std::uintptr_t offset) {
    T value{};
    if (!engine_memory::ReadField(CurrentMinimap(state), offset, &value,
                                  engine_memory::EngineMemoryReadable)) {
        luaL_error(state, "Minimap state is unavailable");
    }
    return value;
}

int GetState(lua_State* state) {
    lua_pushinteger(state, ReadMinimapField<std::int32_t>(state, kStateOffset));
    return 1;
}

int GetShakeOffset(lua_State* state) {
    const auto shake = ReadMinimapField<RepentogonMinimapVector>(state, kShakeOffset);
    PushLuaVector(state, shake.x, shake.y);
    return 1;
}

int GetDisplayedSize(lua_State* state) {
    const auto minimap = CurrentMinimap(state);
#if !defined(__SWITCH__)
    if (!g_DisplayedSizeHost) return luaL_error(state, "Minimap native size is unavailable");
    const auto host = engine_call::AddressOfFunction(g_DisplayedSizeHost);
#else
    constexpr std::uintptr_t host = 0;
#endif
    const auto entry = api100_native::Resolve(state, kDisplayedSizeEntry,
                                              g_DisplayedSizeCache, host);
    const auto size = engine_call::AsFunction<DisplayedSize>(entry)(
        engine_memory::AsObject(minimap));
    PushLuaVector(state, size.x, size.y);
    return 1;
}

}  // namespace

void RegisterRepentogonMinimapApi(lua_State* state) {
    static const luaL_Reg methods[] = {
        {"GetDisplayedSize", GetDisplayedSize},
        {"GetShakeOffset", GetShakeOffset},
        {"GetState", GetState},
        {nullptr, nullptr},
    };
    luaL_newlib(state, methods);
    lua_setglobal(state, "Minimap");
}

#if !defined(__SWITCH__)
void SetRepentogonMinimapNativeTestBinding(DisplayedSize displayedSize) noexcept {
    g_DisplayedSizeHost = displayedSize;
    g_DisplayedSizeCache = {};
}
#endif

}  // namespace isaac::runtime
