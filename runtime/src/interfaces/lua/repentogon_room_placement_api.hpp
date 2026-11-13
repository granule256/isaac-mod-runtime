#pragma once

#include <cstdint>

struct lua_State;

namespace isaac::runtime {

int RepentogonLevelTryPlaceRoom(lua_State* state);
int RepentogonLevelTryPlaceRoomAtDoor(lua_State* state);
int RegisterRepentogonRoomPlacementApi(lua_State* state);

struct RepentogonRoomPlacementVector {
    std::int32_t x{};
    std::int32_t y{};
};

#if !defined(__SWITCH__)
struct RepentogonRoomPlacementNativeTestBindings {
    const void* (*getRoomByIdx)(const void*, std::int32_t, std::int32_t){};
    const std::int32_t* const* (*getRoomPlacementOffsets)(std::int32_t){};
    bool (*hasShapeSlot)(std::int32_t, std::int32_t, bool){};
    RepentogonRoomPlacementVector (*getDoorSource)(
        const RepentogonRoomPlacementVector*, std::int32_t, std::int32_t,
        bool){};
    RepentogonRoomPlacementVector (*getDoorTarget)(
        const RepentogonRoomPlacementVector*, std::int32_t, std::int32_t,
        bool){};
    bool (*placeRoom)(void*, const void*, const void*, std::uint32_t,
                      std::int32_t){};
    bool (*hasPhotoDoor)(const void*){};
    void (*makeDoor)(void*, std::int32_t){};
    void (*updateVisibility)(void*){};
    void (*setRoomTypes)(void*, std::int32_t, std::int32_t){};
    void (*playAnimation)(void*){};
    void (*removeEntity)(void*){};
};

void SetRepentogonRoomPlacementNativeTestBindings(
    RepentogonRoomPlacementNativeTestBindings bindings) noexcept;
#endif

}  // namespace isaac::runtime
