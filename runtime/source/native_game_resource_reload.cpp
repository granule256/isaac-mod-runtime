#include "native_game_resource_reload.hpp"
#include "module_finder.hpp"
#include "infrastructure/call/engine_call_access.hpp"
#include "infrastructure/memory/engine_field_access.hpp"
#include <array>
#include <limits>

namespace isaac::runtime {
extern "C" {
NativeResourceReloadState g_NativeGameResourceReloadState{};
}
namespace {
// Game构造、Game.Init两处原指令互证；下一成员+0x24f9b0，不猜对象大小。
constexpr std::uintptr_t kGameMinimapOffset=0x24ee70;
constexpr std::size_t kGameMinimapSize=0xb40;
struct Entry { std::uintptr_t offset;std::array<std::uint8_t,16> bytes; };
constexpr std::array<Entry,3> kMinimapLifetimeEntries{{
    {0x41a814,{0xfd,0x7b,0xbe,0xa9,0xf3,0x0b,0x00,0xf9,0xfd,0x03,0x00,0x91,0xf3,0x03,0x00,0xaa}},
    {0x41a8d0,{0xfd,0x7b,0xbd,0xa9,0xf6,0x57,0x01,0xa9,0xfd,0x03,0x00,0x91,0xf4,0x4f,0x02,0xa9}},
    {0x41c63c,{0xff,0x83,0x01,0xd1,0xfd,0x7b,0x03,0xa9,0xfd,0xc3,0x00,0x91,0xf6,0x57,0x04,0xa9}},
}};
struct ConstructionGuard { std::uintptr_t offset;std::array<std::uint8_t,32> bytes; };
constexpr ConstructionGuard kGameMinimapConstruction{
    0x34b418,{0x08,0xce,0x9d,0x52,0x88,0x04,0xa0,0x72,0x80,0x02,0x08,0x8b,0xa7,0xb9,0x0c,0x94,0x08,0x36,0x9f,0x52,0x88,0x04,0xa0,0x72,0x80,0x02,0x08,0x8b,0x2f,0x93,0x0c,0x94}};
constexpr Entry kGameMinimapInitialization{
    0x34e084,{0x08,0xce,0x9d,0x52,0x88,0x04,0xa0,0x72,0x60,0x02,0x08,0x8b,0xec,0xaf,0x0c,0x94}};

using Method=void(*)(void*);
struct Bindings {
    std::uintptr_t gameSlot{};
    Method construct{},destroy{},load{};
};
Bindings g_Bindings{};

bool ReadCurrentOwner(std::uintptr_t* owner) noexcept {
    std::uintptr_t slot{},game{};
    if (!owner || !g_Bindings.gameSlot ||
        !engine_memory::ReadAt(g_Bindings.gameSlot,&slot,engine_memory::EngineMemoryReadable) || !slot ||
        !engine_memory::ReadAt(slot,&game,engine_memory::EngineMemoryReadable)) return false;
    if (!game) { *owner=0;return true; }
    if (game>std::numeric_limits<std::uintptr_t>::max()-kGameMinimapOffset) return false;
    *owner=game+kGameMinimapOffset;
    return engine_memory::EngineMemoryWritable(*owner,kGameMinimapSize);
}

struct MinimapOperations {
    void Destroy(std::uintptr_t owner) noexcept { g_Bindings.destroy(engine_memory::AsObject(owner)); }
    void Construct(std::uintptr_t owner) noexcept { g_Bindings.construct(engine_memory::AsObject(owner)); }
    bool Load(std::uintptr_t owner) noexcept {
        // Init走当前资源解析器，保持所有模组的覆盖优先级，不硬换成原版路径。
        g_Bindings.load(engine_memory::AsObject(owner));
        constexpr std::array<std::uintptr_t,5> animations{{0x18,0x1c8,0x378,0x4d0,0x628}};
        for (const auto offset:animations) {
            std::uint8_t loaded{};
            if (!engine_memory::ReadAt(owner+offset+kSpriteLoadedFlagOffset,&loaded,engine_memory::EngineMemoryReadable) || !loaded)
                return false;
        }
        return true;
    }
};
} // namespace

bool PrepareNativeGameResourceReload(const TargetModule& module) noexcept {
    auto& state=g_NativeGameResourceReloadState;
    if (module.buildId!=kTargetBuildId ||
        !module.Contains(module.base+kGameMinimapConstruction.offset,kGameMinimapConstruction.bytes.size()) ||
        !engine_call::VerifyEntryBytes(module.base+kGameMinimapConstruction.offset,
            kGameMinimapConstruction.bytes.data(),kGameMinimapConstruction.bytes.size(),engine_memory::EngineMemoryReadable) ||
        !module.Contains(module.base+kGameMinimapInitialization.offset,kGameMinimapInitialization.bytes.size()) ||
        !engine_call::VerifyEntryBytes(module.base+kGameMinimapInitialization.offset,
            kGameMinimapInitialization.bytes.data(),kGameMinimapInitialization.bytes.size(),engine_memory::EngineMemoryReadable)) {
        state.failure=6;return false;
    }
    Bindings bindings{};
    Method* methods[]{&bindings.construct,&bindings.destroy,&bindings.load};
    for (std::size_t i=0;i<kMinimapLifetimeEntries.size();++i) {
        const auto& entry=kMinimapLifetimeEntries[i];
        *methods[i]=engine_call::ResolveFunction<Method>(module.base,module.size,entry.offset,
            entry.bytes,engine_memory::EngineMemoryReadable);
        if (!*methods[i]) { state.failure=7;return false; }
    }
    if (module.size<sizeof(std::uintptr_t) || kGameOwnerGlobalSlotOffset>module.size-sizeof(std::uintptr_t)) {
        state.failure=8;return false;
    }
    bindings.gameSlot=module.base+kGameOwnerGlobalSlotOffset;
    g_Bindings=bindings;
    std::uintptr_t owner{};
    if (!ReadCurrentOwner(&owner)) { state.failure=8;return false; }
    return PrepareNativeResourceOwner(state,owner);
}

bool ReleaseNativeGameResources() noexcept {
    std::uintptr_t owner{};
    if (!g_Bindings.destroy || !g_Bindings.construct || !ReadCurrentOwner(&owner) ||
        owner!=g_NativeGameResourceReloadState.owner) {
        g_NativeGameResourceReloadState.failure=9;return false;
    }
    MinimapOperations operations;
    return ReleaseNativeResourceOwner(g_NativeGameResourceReloadState,operations);
}

bool RestoreNativeGameResources() noexcept {
    std::uintptr_t owner{};
    if (!g_Bindings.load || !ReadCurrentOwner(&owner)) {
        g_NativeGameResourceReloadState.failure=10;return false;
    }
    MinimapOperations operations;
    return RestoreNativeResourceOwner(g_NativeGameResourceReloadState,owner,operations);
}
} // namespace isaac::runtime
