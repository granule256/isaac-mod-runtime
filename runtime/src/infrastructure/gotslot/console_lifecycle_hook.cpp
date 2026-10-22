#include "console_lifecycle_hook.hpp"
#include "infrastructure/console/console_panel_guards.hpp"
#include "infrastructure/console/console_panel_storage.hpp"
#include "runtime_constants.hpp"
#include "infrastructure/memory/engine_field_access.hpp"
#include "infrastructure/call/engine_call_access.hpp"
#include "lib/util/sys/rw_pages.hpp"
#include <cstring>

namespace isaac::runtime {
namespace {
using console::GameFrameFunction;
std::atomic<std::uintptr_t> s_ConsoleBase{};
bool Window(const HookTarget& t,std::uintptr_t offset,std::size_t size) noexcept {
    const auto limit=t.imageSize?t.imageSize:t.codeSize;
    return t.base && offset<=limit && size<=limit-offset && t.base<=UINTPTR_MAX-offset-size &&
        engine_memory::EngineMemoryReadable(t.base+offset,size);
}
template<std::size_t N> bool Guard(const HookTarget& t,std::uintptr_t offset,const std::array<std::uint8_t,N>& bytes) noexcept {
    return offset<=t.codeSize && N<=t.codeSize-offset && Window(t,offset,N) &&
        !std::memcmp(engine_memory::AsObject(t.base+offset),bytes.data(),N);
}
bool Exchange(std::uintptr_t address,std::uintptr_t expected,std::uintptr_t replacement) noexcept {
    bool changed{};
    if(engine_memory::EngineMemoryWritable(address,8))
        changed=__atomic_compare_exchange_n(static_cast<std::uintptr_t*>(engine_memory::AsObject(address)),
            &expected,replacement,false,__ATOMIC_RELEASE,__ATOMIC_RELAXED);
    else {
        exl::util::RwPages pages(address,8);
        changed=__atomic_compare_exchange_n(static_cast<std::uintptr_t*>(engine_memory::AsObject(pages.GetRw())),
            &expected,replacement,false,__ATOMIC_RELEASE,__ATOMIC_RELAXED);pages.Flush();
    }
    const auto value=__atomic_load_n(static_cast<const std::uintptr_t*>(engine_memory::AsObject(address)),__ATOMIC_ACQUIRE);
    return changed && value==replacement;
}
GameFrameFunction Original(std::uintptr_t offset) noexcept {
    const auto base=s_ConsoleBase.load(std::memory_order_acquire);
    if(!base)__builtin_trap();
    return engine_call::AsFunction<GameFrameFunction>(base+offset);
}
}
extern "C" void IsaacModRuntime_ConsoleGameInput(void* game) {
    console::RunConsoleGameInput(game,Original(console::native_panel::kGameInputOffset));
}
extern "C" void IsaacModRuntime_ConsoleGameUpdate(void* game) {
    if(console::ConsolePaused())++console::Panel().pausedUpdates;
    console::RunConsoleGameUpdate(game,Original(console::native_panel::kGameUpdateOffset));
}
extern "C" void IsaacModRuntime_ConsoleGameRender(void* game) {
    console::RunConsoleGameRender(game,Original(console::native_panel::kGameRenderOffset));
}
extern "C" void IsaacModRuntime_ConsoleGameInterpolate(void* game) {
    // Manager在正常Game::Update之外调用；Room::Interpolate还会执行玩家Update。
    console::RunConsoleGameUpdate(game,Original(console::native_panel::kGameInterpolateOffset));
}
Status InstallConsoleLifecycleHook(const HookTarget& t) noexcept {
    namespace n=console::native_panel;
    if(t.buildId!=kTargetBuildId || console::Panel().hooksReady ||
       !Guard(t,n::kGameInputOffset,n::kGameInputBytes) || !Guard(t,n::kGameInputPltOffset,n::kGameInputPltBytes) ||
       !Guard(t,n::kGameUpdateOffset,n::kGameUpdateBytes) || !Guard(t,n::kGameUpdatePltOffset,n::kGameUpdatePltBytes) ||
       !Guard(t,n::kGameRenderOffset,n::kGameRenderBytes) || !Guard(t,n::kGameRenderPltOffset,n::kGameRenderPltBytes) ||
       !Guard(t,n::kGameInterpolateOffset,n::kGameInterpolateBytes) || !Guard(t,n::kGameInterpolatePltOffset,n::kGameInterpolatePltBytes))
        return Status{StatusCode::Rejected};
    const std::uintptr_t slots[]={n::kGameInputGot,n::kGameUpdateGot,n::kGameRenderGot,n::kGameInterpolateGot};
    const std::uintptr_t targets[]={n::kGameInputOffset,n::kGameUpdateOffset,n::kGameRenderOffset,n::kGameInterpolateOffset};
    const std::uintptr_t replacements[]={engine_call::AddressOfFunction(&IsaacModRuntime_ConsoleGameInput),
        engine_call::AddressOfFunction(&IsaacModRuntime_ConsoleGameUpdate),engine_call::AddressOfFunction(&IsaacModRuntime_ConsoleGameRender),
        engine_call::AddressOfFunction(&IsaacModRuntime_ConsoleGameInterpolate)};
    constexpr std::size_t slotCount=sizeof(slots)/sizeof(slots[0]);
    static_assert(sizeof(slots)==sizeof(targets) && sizeof(slots)==sizeof(replacements));
    std::uintptr_t previous[slotCount]{};
    for(unsigned i=0;i<slotCount;++i){
        if(!Window(t,slots[i],8) || ((t.base+slots[i])&7))return Status{StatusCode::Rejected};
        previous[i]=__atomic_load_n(static_cast<const std::uintptr_t*>(engine_memory::AsObject(t.base+slots[i])),__ATOMIC_ACQUIRE);
        if(previous[i]!=t.base+targets[i] && previous[i]!=t.base+kPltResolverOffset)return Status{StatusCode::Rejected};
    }
    const auto old=s_ConsoleBase.load(std::memory_order_acquire);
    if(old && old!=t.base)return Status{StatusCode::Rejected};
    s_ConsoleBase.store(t.base,std::memory_order_release);
    for(unsigned i=0;i<slotCount;++i){
        if(Exchange(t.base+slots[i],previous[i],replacements[i]))continue;
        // 只恢复本安装器发布的槽；失败状态下不开放控制台，包装仍安全转发。
        for(unsigned j=0;j<=i;++j)static_cast<void>(Exchange(t.base+slots[j],replacements[j],previous[j]));
        return Status{StatusCode::Rejected};
    }
    console::Panel().hooksReady=true;
    return Status::Ok();
}
}
