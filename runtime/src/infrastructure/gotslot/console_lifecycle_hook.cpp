#include "console_lifecycle_hook.hpp"
#include "infrastructure/console/console_panel_guards.hpp"
#include "infrastructure/console/console_panel_storage.hpp"
#include "lua_runtime_state.hpp"
#include "runtime_constants.hpp"
#include "infrastructure/memory/engine_field_access.hpp"
#include "infrastructure/call/engine_call_access.hpp"
#include "lib/util/sys/rw_pages.hpp"
#include <cstdlib>
#include <cstring>

namespace isaac::runtime {
namespace {
namespace native = console::native_panel;
using console::GameFrameFunction;
std::atomic<std::uintptr_t> s_ConsoleBase{};
std::atomic<LuaRuntime::FontDrawStringFn> s_OriginalFontDraw{};
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

bool HasMultibyteUtf8(const char* text) noexcept {
    if (!text) return false;
    bool multibyte = false;
    const auto* bytes = reinterpret_cast<const unsigned char*>(text);
    while (*bytes) {
        const auto lead = *bytes++;
        if (lead < 0x80) continue;
        if (lead < 0xC2 || lead > 0xF4) return false;
        const unsigned length = lead < 0xE0 ? 1 : lead < 0xF0 ? 2 : 3;
        const auto first = *bytes;
        if ((lead == 0xE0 && first < 0xA0) || (lead == 0xED && first >= 0xA0) ||
            (lead == 0xF0 && first < 0x90) || (lead == 0xF4 && first >= 0x90))
            return false;
        for (unsigned i = 0; i < length; ++i)
            if ((*bytes++ & 0xC0) != 0x80) return false;
        multibyte = true;
    }
    return multibyte;
}

void* ConsoleCjkFont() noexcept {
    // The console and font belong to the single Repentance module in the process.
    static void* font{};
    static bool attempted{};
    if (attempted) return font;
    const auto construct = LuaRuntime::FontCtorThunk();
    const auto destroy = LuaRuntime::FontDestructorThunk();
    const auto load = LuaRuntime::FontLoadThunk();
    if (!construct || !destroy || !load) return nullptr;
    attempted = true;
    void* allocation = std::malloc(kFontObjectSize + 15);
    if (!allocation) return nullptr;
    const auto address = (engine_memory::AddressOf(allocation) + 15) & ~std::uintptr_t{15};
    auto* object = engine_memory::AsObject(address);
    construct(object);
    if (!load(object, "font/cjk/lanapixel.fnt", nullptr)) {
        destroy(object);
        std::free(allocation);
        return nullptr;
    }
    font = object;
    return font;
}

bool TryDrawConsoleUtf8(std::uintptr_t returnOffset, const char* text, float x, float y,
                       const void* color, int width, bool center) noexcept {
    bool consoleCall = false;
    for (const auto site : native::kConsoleFontDrawSites)
        consoleCall |= returnOffset == site + 4;
    if (!consoleCall || !HasMultibyteUtf8(text)) return false;
    const auto draw = LuaRuntime::FontDrawStringUTF8Thunk();
    if (!draw) return false;
    auto* font = ConsoleCjkFont();
    if (!font) return false;
    draw(font, text, x, y, color, width, center);
    return true;
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
extern "C" void IsaacModRuntime_ConsoleFontDraw(void* font, const char* text, float x, float y,
                                               const void* color, int width, bool center) {
    const auto base = s_ConsoleBase.load(std::memory_order_acquire);
    if (!base) __builtin_trap();
    const auto caller = engine_memory::AddressOf(__builtin_return_address(0));
    if (TryDrawConsoleUtf8(caller - base, text, x, y, color, width, center)) return;
    const auto draw = s_OriginalFontDraw.load(std::memory_order_acquire);
    draw(font, text, x, y, color, width, center);
}

bool InstallConsoleFontDraw(const HookTarget& t, LuaRuntime::FontDrawStringFn original) noexcept {
    namespace n=console::native_panel;
    if (!original || !Guard(t,n::kFontDrawPltOffset,n::kFontDrawPltBytes) ||
        !Window(t,n::kFontDrawGot,sizeof(std::uintptr_t))) return false;
    for (const auto site : n::kConsoleFontDrawSites) {
        const auto branch = 0x94000000U | static_cast<std::uint32_t>((n::kFontDrawPltOffset-site)/4);
        const std::array<std::uint8_t,4> bytes{
            static_cast<std::uint8_t>(branch),static_cast<std::uint8_t>(branch>>8),
            static_cast<std::uint8_t>(branch>>16),static_cast<std::uint8_t>(branch>>24)};
        if (!Guard(t,site,bytes)) return false;
    }
    const auto slot = t.base + n::kFontDrawGot;
    const auto previous=__atomic_load_n(static_cast<const std::uintptr_t*>(engine_memory::AsObject(slot)),__ATOMIC_ACQUIRE);
    if (previous != engine_call::AddressOfFunction(original) && previous != t.base+kPltResolverOffset)
        return false;
    s_OriginalFontDraw.store(original,std::memory_order_release);
    return Exchange(slot,previous,engine_call::AddressOfFunction(&IsaacModRuntime_ConsoleFontDraw));
}

void console::PrepareConsoleFontRendering() noexcept {
    static bool attempted{};
    if (attempted || !Panel().hooksReady) return;
    const auto base = s_ConsoleBase.load(std::memory_order_acquire);
    const auto draw = LuaRuntime::FontDrawStringThunk();
    if (!base || !draw) return;
    attempted = true;
    // The lifecycle installer has already checked the module build ID.
    static_cast<void>(InstallConsoleFontDraw(
        {base,kGameModuleRangeCheckSize,kGameModuleRangeCheckSize,kTargetBuildId}, draw));
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
