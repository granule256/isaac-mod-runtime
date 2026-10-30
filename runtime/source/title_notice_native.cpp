#include "title_notice_native.hpp"
#include "notice_integrity_native.hpp"

extern "C" { std::uint32_t g_TitleNoticeState[24]{}; }

#if defined(EXL_DIAGNOSTIC_STAGE) || defined(EXL_STARTUP_PROBE_STAGE)
namespace isaac::runtime::notice {
void Update(std::uint32_t, float, float, ActionQuery, const char*, void*) noexcept {}
void Render() noexcept {}
void ConfigureComposite(std::uintptr_t, std::size_t) noexcept {}
bool BlocksTitleConfirm() noexcept { return false; }
}
#else

#include "title_notice_state.hpp"
#include "title_notice_language.hpp"
#include "title_notice_composite.hpp"
#include "title_notice_store.hpp"
#include "title_notice_generated.hpp"
#include "lua_runtime_state.hpp"
#include "runtime_constants.hpp"
#include "infrastructure/memory/engine_field_access.hpp"
#include "infrastructure/call/engine_call_access.hpp"
#include "lib/util/sys/rw_pages.hpp"
#include <cstdio>
#include <cstring>
#include <atomic>
#include <cstdlib>

namespace isaac::runtime::notice {
namespace {
struct alignas(16) Sprite { unsigned char storage[kSpriteObjectSize]{}; };
enum SpriteIndex : unsigned { Paper, Entry, Footer, Dim, Progress, SpriteCount };
Sprite g_Sprites[SpriteCount]{};
// assign owns one game-allocator string buffer for the session; never pass a
// libstdc++ std::string into the game's libc++ ABI, or recreate it per frame.
alignas(8) unsigned char g_Path[24]{};
State g_State{};
ResourceCycle g_Resources{};
const LocaleAssets* g_Assets = &kLocaleAssets[0];
static_assert(kLocaleCount == 8 && SpriteCount == ResourceCycle::kSprites);
std::atomic<std::uintptr_t> g_CompositeReturn{};
std::atomic<LuaRuntime::SpriteRenderFn> g_OriginalRender{};
bool g_Loaded{}, g_LoadFailed{}, g_SeenRead{}, g_Title{};
float g_Width{}, g_Height{};
LuaRuntime::SpriteSetFrameNamedFn g_Frame{};
LuaRuntime::SpriteRenderFn g_Render{};
LuaRuntime::SpriteCtorFn g_Ctor{};
LuaRuntime::SpriteDestructorFn g_Destroy{};
LuaRuntime::SpriteLoadFn g_Load{};
LuaRuntime::LibcxxStringAssignFn g_Assign{};
void* g_SystemFont{};
void* g_ErrorFont{};
void* g_ErrorFontAllocation{};
bool g_ErrorFontAttempted{};
unsigned g_ErrorLanguage{};

unsigned PageCount() noexcept { return g_Assets->pageCount; }

bool Held(ActionQuery query, unsigned action) noexcept {
    // Menu_Title::Update itself uses controller -1, including nonzero controller
    // IDs. Use that native aggregate query rather than 64 redundant probes per
    // action on every idle title frame.
    return query(nullptr, action, 0xFFFFFFFFU, nullptr);
}

void Scale(SpriteIndex index, float x, float y) noexcept {
    // These are this component's own aligned ANM2 objects, using the same
    // verified Scale field as Sprite.Scale. Never alter an engine-owned sprite.
    std::memcpy(g_Sprites[index].storage + kSpriteScaleOffset, &x, sizeof(x));
    std::memcpy(g_Sprites[index].storage + kSpriteScaleOffset + sizeof(x), &y, sizeof(y));
}

struct NativeOperations {
    bool BindingsReady() noexcept {
        const auto ctor = LuaRuntime::SpriteCtorThunk();
        const auto destroy = LuaRuntime::SpriteDestructorThunk();
        const auto load = LuaRuntime::SpriteLoadThunk();
        const auto assign = LuaRuntime::LibcxxStringAssignThunk();
        const auto frame = LuaRuntime::SpriteSetFrameNamedThunk();
        const auto render = LuaRuntime::SpriteRenderThunk();
        if (!ctor || !destroy || !load || !assign || !frame || !render) return false;
        g_Ctor = ctor; g_Destroy = destroy; g_Load = load; g_Assign = assign;
        g_Frame = frame; g_Render = render;
        g_TitleNoticeState[15] = 1;
        return true;
    }
    void AssignPath(unsigned language) noexcept { g_Assign(g_Path, kLocaleAssets[language].assetPath); }
    void Construct(unsigned index) noexcept { g_Ctor(g_Sprites[index].storage); }
    bool Load(unsigned index) noexcept {
        g_Load(g_Sprites[index].storage, g_Path, true);
        return g_Sprites[index].storage[kSpriteLoadedFlagOffset] != 0;
    }
    void Destroy(unsigned index) noexcept { g_Destroy(g_Sprites[index].storage); }
};

bool Prepare(unsigned language) noexcept {
    if (g_Resources.generation && g_Resources.language != language &&
        !integrity::VerifyLocale(language)) return false;
    const auto previous = g_Resources.language;
    const auto generation = g_Resources.generation;
    NativeOperations operations;
    g_Loaded = g_Resources.Select(language, operations);
    g_LoadFailed = g_Resources.failedLanguage == language;
    g_TitleNoticeState[5] = g_LoadFailed ? 2U : (g_Loaded ? 1U : 0U);
    if (!g_Loaded) return false;
    g_Assets = &kLocaleAssets[language];
    if (generation != 0 && previous != language) g_State.ResetForLanguage();
    g_TitleNoticeState[15] = 2;
    return true;
}

void SetFrames() noexcept {
    g_Frame(g_Sprites[Entry].storage, g_State.focused ? "EntrySelected" : "Entry", 0);
    if (g_State.phase == Phase::Hidden) return;
    static constexpr const char* names[] = {"", "Open", "Idle", "FlipOut", "FlipIn", "Close"};
    char animation[32]{};
    std::snprintf(animation, sizeof(animation), "%s_%u", names[static_cast<unsigned>(g_State.phase)],
                  g_State.page);
    const unsigned frame = g_State.phase == Phase::Reading ? 0 : g_State.phaseTicks / 2;
    g_Frame(g_Sprites[Paper].storage, animation, static_cast<int>(frame));
    const char* footer = !g_State.requiresHold ? "FooterManual" :
        (g_State.AllPagesViewed(PageCount()) ? "FooterAuto" : "FooterLocked");
    g_Frame(g_Sprites[Footer].storage, footer, 0);
    g_Frame(g_Sprites[Dim].storage, "Dim", 0);
    g_Frame(g_Sprites[Progress].storage, "Progress", 0);
    Scale(Dim, g_Width, g_Height);
    const auto held = g_State.holdTicks < kHoldTicks ? g_State.holdTicks : kHoldTicks;
    Scale(Progress, static_cast<float>(held) / kHoldTicks, 1.0F);
}

void Draw(SpriteIndex index, float x, float y) noexcept {
    const float position[2]{x, y}, clamp[2]{};
    g_Render(g_Sprites[index].storage, position, clamp, clamp);
}

void PrepareError(unsigned language) noexcept {
    g_ErrorLanguage = language;
    if (g_ErrorFontAttempted) return;
    const auto ctor = LuaRuntime::FontCtorThunk();
    const auto load = LuaRuntime::FontLoadThunk();
    if (!ctor || !load) return;
    g_ErrorFontAttempted = true;
    g_ErrorFontAllocation = std::malloc(kFontObjectSize + 15);
    if (!g_ErrorFontAllocation) return;
    const auto address = (engine_memory::AddressOf(g_ErrorFontAllocation) + 15) & ~std::uintptr_t{15};
    g_ErrorFont = engine_memory::AsObject(address);
    ctor(g_ErrorFont);
    // This is the original game's font, not any notice image under validation.
    if (!load(g_ErrorFont, "font/cjk/lanapixel.fnt", nullptr)) {
        if (const auto destroy = LuaRuntime::FontDestructorThunk()) destroy(g_ErrorFont);
        std::free(g_ErrorFontAllocation);
        g_ErrorFontAllocation = g_ErrorFont = nullptr;
    }
}

void DrawError() noexcept {
    const auto draw = LuaRuntime::FontDrawStringScaledUTF8Thunk();
    const auto width = LuaRuntime::FontGetStringWidthUTF8Thunk();
    const auto loaded = LuaRuntime::FontIsLoadedThunk();
    if (!draw || !width || !loaded) return;
    void* font = g_ErrorFont && loaded(g_ErrorFont) ? g_ErrorFont : g_SystemFont;
    if (!font || !loaded(font)) return;
    static constexpr const char* messages[8][3] = {
        {"Compatibility layer disabled", "Notice files are missing or have been modified.", "Reinstall the complete official free package."},
        {"Kompatibilitätsschicht deaktiviert", "Hinweisdateien fehlen oder wurden verändert.", "Das komplette offizielle Gratispaket neu installieren."},
        {"Capa de compatibilidad desactivada", "Faltan archivos del aviso o han sido modificados.", "Reinstala el paquete oficial completo y gratuito."},
        {"Couche de compatibilité désactivée", "Des fichiers de l'avis manquent ou ont été modifiés.", "Réinstallez le paquet officiel complet et gratuit."},
        {"互換レイヤーは停止しました", "お知らせのファイルが不足または変更されています。", "公式の無料パッケージを再インストールしてください。"},
        {"호환 계층이 중지되었습니다", "안내 파일이 없거나 수정되었습니다.", "공식 무료 패키지 전체를 다시 설치하세요."},
        {"Слой совместимости отключён", "Файлы уведомления отсутствуют или изменены.", "Установите полный официальный бесплатный пакет."},
        {"兼容层已停止", "公告文件缺失或被改动。", "请重新安装完整的官方免费版本。"}
    };
    const unsigned language = font == g_ErrorFont ? g_ErrorLanguage : 0;
    static constexpr float white[4]{1.0F, 1.0F, 1.0F, 1.0F};
    static constexpr float red[4]{1.0F, 0.35F, 0.35F, 1.0F};
    for (unsigned i = 0; i < 3; ++i) {
        const char* message = messages[language][i];
        const int pixels = width(font, message);
        if (pixels <= 0 || pixels > 2000) continue;
        float scale = i == 0 ? 1.4F : 1.05F;
        if (pixels * scale > g_Width - 30) scale = (g_Width - 30) / pixels;
        draw(font, message, (g_Width - pixels * scale) / 2,
             g_Height / 2 + i * 24.0F, scale, scale, i ? white : red, 0, false);
    }
    char code[32]{};
    std::snprintf(code, sizeof(code), "N%u", g_NoticeIntegrityState[1]);
    draw(font, code, 12.0F, g_Height - 18.0F, 1.0F, 1.0F, white, 0, false);
    ++g_NoticeIntegrityState[14];
}

// Exact native ABI: void ANM2::Render(Vector2 const&, Vector2 const&,
// Vector2 const&). All four arguments are addresses, with no HFA or x8 result.
// Our own sprites use the verified direct thunk and never reenter this GOT slot.
__attribute__((noinline)) void CompositeRender(void* sprite, const void* position,
                                              const void* topLeft, const void* bottomRight) {
    const auto caller = engine_memory::AddressOf(__builtin_return_address(0));
    const auto original = g_OriginalRender.load(std::memory_order_acquire);
    if (original) original(sprite, position, topLeft, bottomRight);
    if (g_Title) {
        CompositeAfterForeground(caller, g_CompositeReturn.load(std::memory_order_acquire), &Render);
    }
}
} // namespace

void ConfigureComposite(std::uintptr_t base, std::size_t textSize) noexcept {
    // 91C73FDD MenuManager::Render: this last foreground draw runs with either
    // value of OptionsConfig+0x5E. Unlike the later conditional Present, it is
    // also independent of the optional MC_POST_RENDER interception.
    static constexpr unsigned char expected[16]{
        0xA1,0x23,0x01,0xD1,0xE0,0x03,0x14,0xAA,
        0xE3,0x03,0x02,0xAA,0x66,0xC4,0x09,0x94};
    constexpr std::uintptr_t offset = kMenuForegroundReturnOffset - 16;
    constexpr std::uintptr_t slotOffset = 0xA9DDE0; // Exact Render overload's jmprel relocation.
    if (base == 0 || textSize < offset + sizeof(expected) || base > UINTPTR_MAX - textSize ||
        base > UINTPTR_MAX - slotOffset - sizeof(std::uintptr_t) ||
        !engine_memory::EngineMemoryReadable(base + offset, sizeof(expected)) ||
        std::memcmp(engine_memory::AsObject(base + offset), expected, sizeof(expected)) != 0) return;
    const auto original = engine_call::ResolveFunction<LuaRuntime::SpriteRenderFn>(
        base, textSize, kSpriteRenderOffset, kSpriteRenderExpectedBytes,
        &engine_memory::EngineMemoryReadable);
    std::uintptr_t current{};
    const auto slot = base + slotOffset;
    if (!original || !engine_memory::ReadAt(slot, &current, &engine_memory::EngineMemoryReadable) || !current)
        return;
    g_OriginalRender.store(original, std::memory_order_release);
    const auto callback = engine_call::AddressOfFunction(&CompositeRender);
    if (engine_memory::EngineMemoryWritable(slot, sizeof(callback))) {
        __atomic_store_n(static_cast<std::uintptr_t*>(engine_memory::AsObject(slot)),
                         callback, __ATOMIC_RELEASE);
    } else {
        exl::util::RwPages pages(slot, sizeof(callback));
        __atomic_store_n(static_cast<std::uintptr_t*>(engine_memory::AsObject(pages.GetRw())),
                         callback, __ATOMIC_RELEASE);
        pages.Flush();
    }
    if (engine_memory::ReadAt(slot, &current, &engine_memory::EngineMemoryReadable) && current == callback)
        g_CompositeReturn.store(base + kMenuForegroundReturnOffset, std::memory_order_release);
}

void Update(std::uint32_t menuState, float width, float height, ActionQuery query,
            const char* language, void* systemFont) noexcept {
    g_Title = menuState == 1 && g_CompositeReturn.load(std::memory_order_acquire) != 0;
    if (!g_Title) {
        g_State.Tick(0, false, false, PageCount());
        g_TitleNoticeState[0] = static_cast<unsigned>(g_State.phase);
        return; // In-game: no input polling, animation, allocation or file access.
    }
    ++g_TitleNoticeState[8];
    g_Width = width;
    g_Height = height;
    g_SystemFont = systemFont;
    const unsigned wanted = LanguageIndex(language);
    if (!integrity::RuntimeAllowed()) {
        if (integrity::Blocked()) PrepareError(wanted);
        return;
    }
    if (!query || width < kPaperWidth || height < kPaperHeight || !Prepare(wanted)) return;
    if (!g_SeenRead) {
        auto* files = SessionSaveFilePort();
        if (!files) return; // The loader publishes this only on the game thread.
        bool seen = false;
        const auto status = ReadSeenVersion(*files, kVersion, &seen);
        ++g_TitleNoticeState[10];
        g_TitleNoticeState[6] = static_cast<unsigned>(status.code());
        g_State.SetSeenVersion(status.ok() && seen);
        g_SeenRead = true; // A failed read also displays the notice, without I/O polling.
    }
    unsigned keys = 0;
    constexpr unsigned actions[] = {14, 15, 17, 18, 19, 20, 21, 22};
    for (unsigned i = 0; i < sizeof(actions) / sizeof(actions[0]); ++i)
        if (Held(query, actions[i])) keys |= 1U << i;
    g_State.Tick(keys, true, true, PageCount());
    if (g_State.ConsumeAcknowledgement()) {
        auto* files = SessionSaveFilePort();
        const auto status = files ? WriteSeenVersion(*files, kVersion) : Status{StatusCode::Unsupported};
        ++g_TitleNoticeState[11];
        g_TitleNoticeState[7] = static_cast<unsigned>(status.code());
    }
    SetFrames();
    g_TitleNoticeState[0] = static_cast<unsigned>(g_State.phase);
    g_TitleNoticeState[1] = g_State.page;
    g_TitleNoticeState[2] = g_State.requiresHold;
    g_TitleNoticeState[3] = g_State.holdTicks;
    g_TitleNoticeState[4] = g_State.focused;
    g_TitleNoticeState[13] = static_cast<unsigned>(width);
    g_TitleNoticeState[14] = static_cast<unsigned>(height);
    g_TitleNoticeState[16] = g_State.ViewedPagesMask();
    g_TitleNoticeState[17] = g_State.AllPagesViewed(PageCount());
    g_TitleNoticeState[18] = g_Resources.language;
    g_TitleNoticeState[19] = PageCount();
    g_TitleNoticeState[20] = g_Resources.generation;
    g_TitleNoticeState[21] = g_Resources.constructed;
    g_TitleNoticeState[22] = g_Resources.failedLanguage;
    g_TitleNoticeState[23] = wanted;
}

void Render() noexcept {
    if (g_Title && integrity::Blocked()) { DrawError(); return; }
    if (!g_Title || !g_Loaded || !g_SeenRead) return;
    ++g_TitleNoticeState[9];
    Draw(Entry, g_Width - 66.0F, g_Height - 17.0F);
    if (g_State.phase == Phase::Hidden) return;
    Draw(Dim, 0.0F, 0.0F);
    Draw(Paper, g_Width / 2, g_Height / 2);
    if (g_State.phase == Phase::Reading) {
        Draw(Footer, g_Width / 2, g_Height / 2);
        if (g_State.requiresHold && g_State.holdTicks)
            Draw(Progress, g_Width / 2 - 30.0F, g_Height / 2 + 101.0F);
    }
}

bool BlocksTitleConfirm() noexcept {
    if (g_Title && !integrity::RuntimeAllowed()) return true;
    if (!g_Title || g_LoadFailed) return false;
    // While loading, retain the title until its mandatory first notice is ready.
    // This also covers the first title-update tick before the sprite thunks exist.
    const bool blocked = !g_SeenRead || g_State.BlocksTitleConfirm();
    if (blocked) ++g_TitleNoticeState[12];
    return blocked;
}
} // namespace isaac::runtime::notice
#endif
