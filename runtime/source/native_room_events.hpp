#pragma once
#include <atomic>
#include <cstdint>
#include <cstring>
#include "infrastructure/native/world_content_mutations.hpp"

namespace isaac::runtime {
// Native Level::load_room completion, including re-entry at the same grid index.
inline std::atomic<std::uint64_t> g_NativeRoomLoadGeneration{};
// Level开头已核的stage/type，只有原生load_room返回后才发布。
// 层号在下层过场早期就会变化，不能把它本身当作新地图已就绪。
inline std::atomic<std::uint64_t> g_NativeLoadedLevelKey{};
// Init can rebuild the same stage/type, seed and room index (five-pip dice).
inline std::atomic<std::uint64_t> g_NativeLevelInitGeneration{};
inline std::atomic<std::uint32_t> g_NativeLevelInitDepth{};
inline bool NativeLevelInitializing() noexcept {
    return g_NativeLevelInitDepth.load(std::memory_order_acquire) != 0;
}
inline std::uint64_t NativeLevelInitGeneration() noexcept {
    return g_NativeLevelInitGeneration.load(std::memory_order_acquire);
}
inline bool NativeLoadedLevelMatches(std::uint32_t stage, std::uint32_t type) noexcept {
    const auto loaded = g_NativeLoadedLevelKey.load(std::memory_order_acquire);
    return loaded != 0 && loaded == (static_cast<std::uint64_t>(type) << 32U | stage);
}
inline void NoteNativeRoomLoaded() noexcept {
    g_NativeRoomLoadGeneration.fetch_add(1, std::memory_order_release);
}
inline std::uint64_t NativeRoomLoadGeneration() noexcept {
    return g_NativeRoomLoadGeneration.load(std::memory_order_acquire);
}
inline void CompleteNativeRoomLoad(void (*original)(void*), void* level) {
    original(level);
    if (level != nullptr) {
        std::uint32_t fields[2]{};
        std::memcpy(fields, level, sizeof(fields));
        g_NativeLoadedLevelKey.store(static_cast<std::uint64_t>(fields[1]) << 32U | fields[0],
                                     std::memory_order_release);
    }
    NoteNativeRoomLoaded();
}
inline void CompleteNativeLevelInit(void (*original)(void*), void* level) {
    if (g_NativeLevelInitDepth.fetch_add(1, std::memory_order_acq_rel) == 0)
        BeginWorldContentFloor();
    // A previous completion for the same stage/type is no proof of readiness.
    g_NativeLoadedLevelKey.store(0, std::memory_order_release);
    original(level); // Init itself completes load_room before returning.
    g_NativeLevelInitGeneration.fetch_add(1, std::memory_order_release);
    g_NativeLevelInitDepth.fetch_sub(1, std::memory_order_release);
}
}
