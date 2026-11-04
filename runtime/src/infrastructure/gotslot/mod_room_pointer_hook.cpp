#include "mod_room_hook.hpp"
#include "mod_room_guards.hpp"
#include "native_room_events.hpp"
#include "mod_menu_native.hpp"
#include "runtime_constants.hpp"
#include "infrastructure/memory/engine_field_access.hpp"
#include "infrastructure/call/engine_call_access.hpp"
#include "lib/util/sys/rw_pages.hpp"
#include <atomic>
#include <cstring>
namespace isaac::runtime {
namespace {
std::atomic<std::uintptr_t> s_ModRoomBase{};
std::atomic<std::uintptr_t> s_LevelRoomBase{};
std::atomic<std::uintptr_t> s_LevelInitBase{};
bool Window(const HookTarget& t,std::uintptr_t offset,std::size_t size) {
    const auto limit=t.imageSize?t.imageSize:t.codeSize;
    return t.base && offset<=limit && size<=limit-offset && t.base<=UINTPTR_MAX-offset-size &&
        engine_memory::EngineMemoryReadable(t.base+offset,size);
}
template<std::size_t N> bool Guard(const HookTarget& t,std::uintptr_t offset,const std::array<std::uint8_t,N>& bytes) {
    return Window(t,offset,N)&&!std::memcmp(engine_memory::AsObject(t.base+offset),bytes.data(),N);
}
}
extern "C" bool IsaacModRuntime_ModRoomPointerIntercept(void* config,int stage,int mode) {
    const auto base=s_ModRoomBase.load(std::memory_order_acquire);
    if(!base)__builtin_trap();
    const ModRoomLoadBindings native{
        engine_call::AsFunction<ModRoomLoadBindings::Load>(base+mod_rooms::kLoadOffset),
        &modmenu::LoadEngineModRoomsAfterStage};
    return LoadStageRoomsWithMods(native,config,stage,mode);
}
Status InstallModRoomPointerHook(const HookTarget& t) noexcept {
    if(t.buildId!=kTargetBuildId || !Guard(t,mod_rooms::kLoadOffset,mod_rooms::kLoadBytes) ||
       !Guard(t,mod_rooms::kUpdateOffset,mod_rooms::kUpdateBytes) ||
       !Guard(t,mod_rooms::kPltOffset,mod_rooms::kPltBytes) ||
       !Window(t,mod_rooms::kGotOffset,8) || ((t.base+mod_rooms::kGotOffset)&7))return Status{StatusCode::Rejected};
    const auto address=t.base+mod_rooms::kGotOffset;
    auto expected=__atomic_load_n(static_cast<const std::uintptr_t*>(engine_memory::AsObject(address)),__ATOMIC_ACQUIRE);
    if(expected!=t.base+mod_rooms::kLoadOffset&&expected!=t.base+kPltResolverOffset)return Status{StatusCode::Rejected};
    const auto previous=s_ModRoomBase.load(std::memory_order_acquire);
    if(previous&&previous!=t.base)return Status{StatusCode::Rejected};
    s_ModRoomBase.store(t.base,std::memory_order_release);
    const auto replacement=engine_call::AddressOfFunction(&IsaacModRuntime_ModRoomPointerIntercept);
    bool changed=false;
    if(engine_memory::EngineMemoryWritable(address,8))
        changed=__atomic_compare_exchange_n(static_cast<std::uintptr_t*>(engine_memory::AsObject(address)),
            &expected,replacement,false,__ATOMIC_RELEASE,__ATOMIC_RELAXED);
    else {
        exl::util::RwPages pages(address,8);
        changed=__atomic_compare_exchange_n(static_cast<std::uintptr_t*>(engine_memory::AsObject(pages.GetRw())),
            &expected,replacement,false,__ATOMIC_RELEASE,__ATOMIC_RELAXED);pages.Flush();
    }
    return changed?Status::Ok():Status{StatusCode::Rejected};
}
extern "C" void IsaacModRuntime_LevelRoomPointerIntercept(void* level) {
    const auto base=s_LevelRoomBase.load(std::memory_order_acquire);
    if(!base)__builtin_trap();
    CompleteNativeRoomLoad(engine_call::AsFunction<void(*)(void*)>(base+native_room::kLoadOffset),level);
}
Status InstallLevelRoomPointerHook(const HookTarget& t) noexcept {
    if(t.buildId!=kTargetBuildId || !Guard(t,native_room::kLoadOffset,native_room::kLoadBytes) ||
       !Guard(t,native_room::kTailOffset,native_room::kTailBytes) ||
       !Guard(t,native_room::kPltOffset,native_room::kPltBytes) ||
       !Window(t,native_room::kGotOffset,8) || ((t.base+native_room::kGotOffset)&7))return Status{StatusCode::Rejected};
    const auto address=t.base+native_room::kGotOffset;
    auto expected=__atomic_load_n(static_cast<const std::uintptr_t*>(engine_memory::AsObject(address)),__ATOMIC_ACQUIRE);
    if(expected!=t.base+native_room::kLoadOffset&&expected!=t.base+kPltResolverOffset)return Status{StatusCode::Rejected};
    const auto previous=s_LevelRoomBase.load(std::memory_order_acquire);
    if(previous&&previous!=t.base)return Status{StatusCode::Rejected};
    s_LevelRoomBase.store(t.base,std::memory_order_release);
    const auto replacement=engine_call::AddressOfFunction(&IsaacModRuntime_LevelRoomPointerIntercept);
    bool changed=false;
    if(engine_memory::EngineMemoryWritable(address,8))
        changed=__atomic_compare_exchange_n(static_cast<std::uintptr_t*>(engine_memory::AsObject(address)),
            &expected,replacement,false,__ATOMIC_RELEASE,__ATOMIC_RELAXED);
    else {
        exl::util::RwPages pages(address,8);
        changed=__atomic_compare_exchange_n(static_cast<std::uintptr_t*>(engine_memory::AsObject(pages.GetRw())),
            &expected,replacement,false,__ATOMIC_RELEASE,__ATOMIC_RELAXED);pages.Flush();
    }
    return changed?Status::Ok():Status{StatusCode::Rejected};
}
extern "C" void IsaacModRuntime_LevelInitPointerIntercept(void* level) {
    const auto base=s_LevelInitBase.load(std::memory_order_acquire);
    if(!base)__builtin_trap();
    CompleteNativeLevelInit(engine_call::AsFunction<void(*)(void*)>(base+native_level::kInitOffset),level);
}
Status InstallLevelInitPointerHook(const HookTarget& t) noexcept {
    if(t.buildId!=kTargetBuildId || !Guard(t,native_level::kInitOffset,native_level::kInitBytes) ||
       !Guard(t,native_level::kPltOffset,native_level::kPltBytes) ||
       !Window(t,native_level::kGotOffset,8) || ((t.base+native_level::kGotOffset)&7))return Status{StatusCode::Rejected};
    const auto address=t.base+native_level::kGotOffset;
    auto expected=__atomic_load_n(static_cast<const std::uintptr_t*>(engine_memory::AsObject(address)),__ATOMIC_ACQUIRE);
    if(expected!=t.base+native_level::kInitOffset&&expected!=t.base+kPltResolverOffset)return Status{StatusCode::Rejected};
    const auto previous=s_LevelInitBase.load(std::memory_order_acquire);
    if(previous&&previous!=t.base)return Status{StatusCode::Rejected};
    s_LevelInitBase.store(t.base,std::memory_order_release);
    const auto replacement=engine_call::AddressOfFunction(&IsaacModRuntime_LevelInitPointerIntercept);
    bool changed=false;
    if(engine_memory::EngineMemoryWritable(address,8))
        changed=__atomic_compare_exchange_n(static_cast<std::uintptr_t*>(engine_memory::AsObject(address)),
            &expected,replacement,false,__ATOMIC_RELEASE,__ATOMIC_RELAXED);
    else {
        exl::util::RwPages pages(address,8);
        changed=__atomic_compare_exchange_n(static_cast<std::uintptr_t*>(engine_memory::AsObject(pages.GetRw())),
            &expected,replacement,false,__ATOMIC_RELEASE,__ATOMIC_RELAXED);pages.Flush();
    }
    return changed?Status::Ok():Status{StatusCode::Rejected};
}
}
