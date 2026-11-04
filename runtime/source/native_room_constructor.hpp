#pragma once

#include "infrastructure/memory/engine_field_access.hpp"
#include "runtime_constants.hpp"

namespace isaac::runtime {

// The supported native Room constructor leaves its descriptor uninitialized.
// Set the initial member value before construction, so any native assignment wins.
template<class Constructor>
void ConstructNativeRoom(std::uintptr_t room, const Constructor& original) {
    static_cast<void>(engine_memory::WriteField(room, kRoomDescriptorPointerOffset,
                                               std::uintptr_t{0},
                                               &engine_memory::EngineMemoryWritable));
    original(room);
}

}  // namespace isaac::runtime
