#include <string>
#include <string_view>
#include "interfaces/lua/runtime_perf.hpp"
#include "interfaces/lua/api_sequence_probe.hpp"
#include "interfaces/lua/font_api.hpp"

#include "interfaces/lua/lua_integer_argument.hpp"
#include "interfaces/lua/owner_binding.hpp"

#include "lua_object_handles.hpp"
#include "lua_runtime_state.hpp"
#include "runtime_constants.hpp"

#include <atomic>
#include <cstddef>
#include <cstdint>
#include <cstdlib>

extern "C" {
#include <lauxlib.h>
}

namespace isaac::runtime {

// 绘制调用计数（探针读）：`DrawString*` 四个变体共用这里，所以它回答的是
// "Mod 到底有没有走到把文字交给引擎这一步" —— 这是"描述构建完成但没画"与
// "描述根本没构建出来"的分界点（2026-09-12：屏幕上只出现 EID 的问号指示、
// 没有描述文字，需要这条读数才能继续定位）。
//
// ⚠️ 2026-09-18 修正前它**只记未缩放的两个变体**（计数点写在 `else` 分支里），
// 于是"画字 0 次"被误读成"屏幕上一个字都没画"（实际 EID/q4/菜单/我们的 RenderScaledText
// 全都走缩放变体）。现在四条变体共用，口径与注释一致。
std::atomic<std::uint32_t> g_FontDrawCalls{0};
std::atomic<std::uint32_t> g_FontDrawBytes{0};
// 字体链的四个读数（2026-09-12，真机报告 `01789214465` 之后的下一步）：
// 文字一次都没画出来，而 EID 的 `renderString` 用的就是 `EID.font:DrawStringScaledUTF8`。
// 要分清"没走到绘制"与"画了但看不见"，必须知道：字体装没装上、绘制时用的颜色与缩放是多少。
std::atomic<std::uint32_t> g_FontLoadCalls{0};
std::atomic<std::uint32_t> g_FontLoadResult{0};
std::atomic<std::uint32_t> g_FontIsLoadedCalls{0};
std::atomic<std::uint32_t> g_FontIsLoadedResult{0};
std::atomic<std::uint32_t> g_FontDrawAlpha{0};
std::atomic<std::uint32_t> g_FontDrawScaleX{0};

namespace {

using LuaRuntime::FontHandle;
using LuaRuntime::kFontMetatable;

// --- Instance storage ------------------------------------------------------
//
// `Font` is the first family whose native object belongs to the Runtime. The Stage148 audit
// proves why that is safe: `~Font()` only releases the Font's internal buffers (delete[] of the
// glyph record array, ImageManager::FreeImage for the page images, free of the kerning block),
// it never deletes `this` and it never unregisters anything global, so nothing but this module
// can release the block we hand to the constructor.
//
// The block comes from this module's own `malloc`/`free` rather than `operator new`/`new[]`:
//   * the module's link line is `LIBS := -lnx`, nothing in it references libstdc++'s allocating
//     `operator new`, while the Lua state itself already proves that `malloc`/`free` work on the
//     exlaunch fake heap;
//   * over-aligned `operator new` (which `alignas(16)` would select) is likewise not part of
//     this module's proven link surface;
//   * the pointer stays a plain `void*`, which keeps "never copy a Font by value" explicit.
//
// Alignment: the audit proves `alignof(Font) >= 8` (plain 8-byte `str`/`ldr` at +0x38/+0x48) and
// every instance the game constructs is 16-byte aligned, so we keep 16. `malloc` only promises 8
// here, therefore the block carries one alignment slot plus room for the raw pointer, which is
// stored in the 8 bytes immediately before the object and read back on release.
constexpr std::size_t kFontAlignment = 16;
constexpr std::size_t kFontStorageSlack = kFontAlignment + sizeof(void*);

void* AllocateFontStorage() noexcept {
    void* raw = std::malloc(kFontObjectSize + kFontStorageSlack);
    if (raw == nullptr) {
        return nullptr;
    }
    const std::uintptr_t rawAddress = reinterpret_cast<std::uintptr_t>(raw);
    // The object starts at least `sizeof(void*)` bytes into the block, so the raw pointer always
    // fits in front of it, and the slack above covers the worst-case alignment offset.
    const std::uintptr_t aligned =
        (rawAddress + sizeof(void*) + (kFontAlignment - 1)) &
        ~(static_cast<std::uintptr_t>(kFontAlignment) - 1);
    *reinterpret_cast<void**>(aligned - sizeof(void*)) = raw;
    return reinterpret_cast<void*>(aligned);
}

void ReleaseFontStorage(void* font) noexcept {
    if (font == nullptr) {
        return;
    }
    void* raw = *reinterpret_cast<void**>(reinterpret_cast<std::uintptr_t>(font) - sizeof(void*));
    std::free(raw);
}

// --- Shared preludes -------------------------------------------------------

// Resolves method argument 1 to this module's Font instance. `luaL_checkudata` rejects a foreign
// value with Lua's standard message; a handle that `__gc` already released is unreachable in
// normal use, but a null object must never reach a native call. Returns 0 when the call may
// proceed, otherwise the Lua error code to return verbatim.
int ResolveFont(lua_State* state, const char* apiName, void** font) {
    auto* handle = static_cast<FontHandle*>(luaL_checkudata(state, 1, kFontMetatable));
    if (handle->font == nullptr) {
        return luaL_error(state, "%s was called on a released Font", apiName);
    }
    *font = handle->font;
    return 0;
}

// Shared prelude of the five measurement methods.
//
// This is a hard requirement and not a convenience. The game's measurement functions do not check
// `IsLoaded()` themselves, and on an object that never completed a `Load` the fields they read are
// uninitialised: `+0x14` (line height) and `+0x16` (baseline height) are only written when the
// `.fnt` common record is parsed, and neither `Font()` nor `Unload()` initialises them; the glyph
// index table is only sentinel-filled up to +0x24E by the default constructor, so a query at a
// code point >= 255 can follow an uninitialised index into the glyph arrays. The Runtime therefore
// refuses the call instead of returning a number the game never computed.
int RequireLoadedFont(lua_State* state, void* font, const char* apiName) {
    const LuaRuntime::FontIsLoadedFn isLoaded = LuaRuntime::FontIsLoadedThunk();
    if (isLoaded == 0) {
        return luaL_error(state, "%s native binding is unavailable", apiName);
    }
    if (!isLoaded(font)) {
        return luaL_error(state, "%s requires a loaded Font", apiName);
    }
    return 0;
}

// --- Handlers --------------------------------------------------------------

int FontLoad(lua_State* state);
int FontUnload(lua_State* state);
int FontIsLoaded(lua_State* state);
int FontGetStringWidth(lua_State* state);
int FontGetStringWidthUTF8(lua_State* state);
int FontGetLineHeight(lua_State* state);
int FontGetBaselineHeight(lua_State* state);
int FontGetCharacterWidth(lua_State* state);
int FontSetMissingCharacter(lua_State* state);
int FontDrawString(lua_State* state);
int FontDrawStringScaled(lua_State* state);
int FontDrawStringUTF8(lua_State* state);
int FontDrawStringScaledUTF8(lua_State* state);

constexpr LuaHandlerBinding kFontHandlers[] = {
    {0x0B010001, &FontLoad},
    {0x0B010002, &FontUnload},
    {0x0B010003, &FontIsLoaded},
    {0x0B010004, &FontGetStringWidth},
    {0x0B010005, &FontGetStringWidthUTF8},
    {0x0B010006, &FontGetLineHeight},
    {0x0B010007, &FontGetBaselineHeight},
    {0x0B010008, &FontGetCharacterWidth},
    {0x0B010009, &FontSetMissingCharacter},
    {0x0B01000A, &FontDrawString},
    {0x0B01000B, &FontDrawStringScaled},
    {0x0B01000C, &FontDrawStringUTF8},
    {0x0B01000D, &FontDrawStringScaledUTF8},
};

constexpr char kFontOwner[] = "Font";

// 把 Mod 自拼的资源路径归一化成**内容挂载点相对**的名字。
//
// 为什么需要（真机 01789203805 + 宿主复现）：EID 用 `debug.getinfo().source` 拼出自己的
// mod 路径，再拼 `/../resources/font/eid_default.fnt`，于是交给 `Font:Load` 的是
//   rom:/isaac_mods/mods/external item descriptions_836319872/main.lua/../resources/font/eid_default.fnt
// 而引擎自己的调用点用的是**内容挂载点相对名**（`font/terminus.fnt`）。我们已经把该 Mod 的
// `resources/` 注册成 KAGE 内容挂载点（真机已验证：纯贴图 Mod 的图标就是靠它画出来的），
// 所以只要把路径规整成 `font/eid_default.fnt`，引擎就能在自己的挂载点里找到它。
//
// 怎么算（2026-09-12 定案）：**先按锚切出挂载点相对名，再在相对名内部折叠 `.` / `..`**。
//
// 锚是 `resources/` 或 `content/` 这两条**整段**路径分量（含两侧 `/`；只按子串找会把
// `MyResourcesMod` 这类目录名截错）。为什么锚优先、而不是先折叠再找锚：引擎自己的资源解析
// 是把**挂载点字符串直接拼在名字前面**去试（实证见 `content_mount_service.hpp` 里
// `resources/gfx` 那段注释），所以"锚之后的相对名"才是引擎真正认的形状；先折叠会把锚本身挪走。
//
// 只对**确实指向本 Mod 内容树**的两种写法做换算（真机证据 `01789205321` + 宿主 harness）：
//   1. 绝对：`rom:/isaac_mods/mods/<dir>/.../resources/...`
//      —— EID 用 `debug.getinfo().source` 拼出来的就是这一种，中间带 `main.lua/../`。
//   2. 相对：`../mods/<dir>/.../resources/...`
//      —— EID 的兜底路径（`main.lua:169`）。游戏在 `rom:/` 下、Mod 树在
//      `rom:/isaac_mods/mods/` 下，这条相对路径**永远解析不到**，不换算的话兜底必然再失败一次。
// 其余（`font/eid_default.fnt` 这种已经是挂载点相对名、或引擎本该自己处理的其它路径）
// **原样返回**，绝不改写成猜测值。
//
// 为什么这一处值得写这么长：它是"字体装不上 ⇒ EID 顶层 `return` ⇒ 屏幕全空"的唯一决定点，
// 而它此前连续三轮真机都没被盯住 —— 前两版写法（按字符区间 `erase`、以及先折叠后找锚）
// 在本工程的宿主工具链上给出过自相矛盾的读数。现在两件事都换了写法：锚用整段匹配、
// 折叠改成按**段**重建字符串，语义直接可读。回归测试见
// `runtime/tests/test_font_resource_path_normalization.py`（真机那两条取值都在里面）。
std::string_view NormalizeModResourcePath(const char* path, std::string& storage) {
    if (path == nullptr) return {};
    const std::string_view view{path};
    constexpr std::string_view kModPrefix = "rom:/isaac_mods/mods/";
    constexpr std::string_view kRelativeModPrefix = "../mods/";
    // 需要折叠的形态：段内出现 `.` 或 `..`（`a/./b`、`a/../b`），或整条路径以 `..` / `.` 开头。
    // **先算它**：`refersToModTree` 的"相对写法"判据要用到同一件事（见下），两处分别实现
    // 就会漏掉 `../mods/<dir>/gfx/../gfx/x.png` 这种"相对 + 段内上跳"的组合 —— 真机那一类
    // 失败正是"同一语义在两处各写一遍、只改了一处"造成的。
    const bool needsCollapse =
        view.find("/./") != std::string_view::npos ||
        view.find("/../") != std::string_view::npos ||
        (view.size() >= 1 && view.compare(0, 1, ".") == 0) ||
        (view.size() >= 2 && view.compare(view.size() - 2, 2, "/.") == 0) ||
        (view.size() >= 3 && view.compare(view.size() - 3, 3, "/..") == 0);
    const bool looksRelative = view.rfind(kRelativeModPrefix, 0) == 0;
    const bool refersToModTree =
        view.rfind(kModPrefix, 0) == 0 ||
        (looksRelative && (view.find("/resources/") != std::string_view::npos ||
                           view.find("/content/") != std::string_view::npos ||
                           needsCollapse));
    if (refersToModTree) {
        for (const std::string_view leaf : {"resources", "content"}) {
            const std::size_t found = view.find("/" + std::string{leaf} + "/");
            if (found == std::string_view::npos) {
                continue;
            }
            // 锚之后的部分要做"挂载点内部"的路径折叠：`resources/../gfx/y.png` 在本 Mod 的
            // 内容树里就是 `gfx/y.png`。按**段**折叠（`..` 会吃掉前一段），而不是按字符区间删，
            // 这样不会碰到任何与下标有关的歧义；一旦 `..` 想跳出挂载点根，就**原样返回**、
            // 不做猜测性改写（宁可让引擎按原路径去试，也不编一个自己都不确定的名字）。
            std::string relative{view.substr(found + leaf.size() + 2)};
            // 锚之后还有 `.` / `..` 分量时按段折叠（判据与上面同一套，见 `needsCollapse`）。
            const bool collapseRelative =
                relative.find("/./") != std::string::npos ||
                relative.find("/../") != std::string::npos ||
                (relative.size() >= 1 && relative.compare(0, 1, ".") == 0) ||
                (relative.size() >= 2 && relative.compare(relative.size() - 2, 2, "/.") == 0) ||
                (relative.size() >= 3 && relative.compare(relative.size() - 3, 3, "/..") == 0);
            if (collapseRelative) {
                std::string collapsed;
                bool escaped = false;
                std::size_t cursor = 0;
                while (cursor <= relative.size()) {
                    const std::size_t slash = relative.find('/', cursor);
                    const std::size_t end =
                        slash == std::string::npos ? relative.size() : slash;
                    const std::string_view segment{relative.data() + cursor, end - cursor};
                    if (segment == "..") {
                        // `..` 只能吃掉**锚之后**已经写出来的那一段：`resources/../gfx` 里
                        // 那个 `..` 指的就是挂载点根自己。它要是想再往上跳（锚后没有段可吃），
                        // 说明这条路径出了挂载点，按"不猜"原则整条原样返回。
                        if (collapsed.empty()) {
                            escaped = true;
                            break;
                        }
                        const std::size_t keep = collapsed.rfind('/');
                        collapsed.erase(keep == std::string::npos ? 0 : keep);
                    } else if (!segment.empty() && segment != ".") {
                        if (!collapsed.empty()) {
                            collapsed.push_back('/');
                        }
                        collapsed.append(segment);
                    }
                    if (slash == std::string::npos) {
                        break;
                    }
                    cursor = slash + 1;
                }
                if (escaped) {
                    storage.assign(view);
                    return storage;
                }
                storage = std::move(collapsed);
                return storage;
            }
            storage = std::move(relative);
            return storage;
        }
    }
    storage.assign(view);
    return storage;
}

int FontLoad(lua_State* state) {
    void* font = nullptr;
    if (const int error = ResolveFont(state, "Font:Load", &font); error != 0) {
        return error;
    }
    // PC documents `void Load(string FilePath)`, but real Mods pass the native second argument
    // too: External Item Descriptions calls `font:Load(path, "")` because some builds "want a
    // string as the second argument". So the path is required and the page-image extension is
    // optional; when it is absent the Runtime passes NULL, which is what all 32 in-module call
    // sites (and the `Font(char const*)` constructor) do.
    const int argumentCount = lua_gettop(state);
    // `lua_isstring` is true for numbers as well (Lua converts them on demand), so the
    // extension is checked with `lua_type`: a number there would reach the native Load as
    // the string "7" and be interpreted as a page-image extension.
    if ((argumentCount != 2 && argumentCount != 3) || !lua_isstring(state, 2) ||
        (argumentCount == 3 && lua_type(state, 3) != LUA_TSTRING)) {
        return luaL_error(state, "Font:Load accepts a path and an optional extension string");
    }
    const char* extension = argumentCount == 3 ? lua_tostring(state, 3) : nullptr;
    const LuaRuntime::FontLoadFn method = LuaRuntime::FontLoadThunk();
    if (method == 0) {
        return luaL_error(state, "Font:Load native binding is unavailable");
    }
    // The path is handed to the game verbatim: the game's own call sites use
    // content-mount-relative names such as `font/terminus.fnt` and redirect them through
    // `ModManager::TryRedirectPath` first, which this batch does not bind.
    // 归一化后再交给引擎（见 `NormalizeModResourcePath`）：引擎只认内容挂载点相对名。
    std::string normalizedStorage;
    const std::string_view normalized =
        NormalizeModResourcePath(lua_tostring(state, 2), normalizedStorage);
    const char* handedToEngine = normalized.empty() ? lua_tostring(state, 2) : normalized.data();
    const bool loaded = method(font, handedToEngine, extension);
    // 探针读数（见 `RecordFontLoadForProbe`）：名字与引擎侧结果是"字体到底装没装上"的唯一判据。
    RecordFontLoadForProbe(handedToEngine != nullptr ? std::string_view{handedToEngine}
                                                     : std::string_view{},
                           loaded);
    g_FontLoadCalls.fetch_add(1, std::memory_order_relaxed);
    g_FontLoadResult.store(loaded ? 1U : 0U, std::memory_order_relaxed);
    lua_pushboolean(state, loaded ? 1 : 0);
    return 1;
}

int FontUnload(lua_State* state) {
    void* font = nullptr;
    if (const int error = ResolveFont(state, "Font:Unload", &font); error != 0) {
        return error;
    }
    if (lua_gettop(state) != 1) {
        return luaL_error(state, "Font:Unload accepts no arguments");
    }
    const LuaRuntime::FontUnloadFn method = LuaRuntime::FontUnloadThunk();
    if (method == 0) {
        return luaL_error(state, "Font:Unload native binding is unavailable");
    }
    method(font);
    return 0;
}

int FontIsLoaded(lua_State* state) {
    void* font = nullptr;
    if (const int error = ResolveFont(state, "Font:IsLoaded", &font); error != 0) {
        return error;
    }
    if (lua_gettop(state) != 1) {
        return luaL_error(state, "Font:IsLoaded accepts no arguments");
    }
    const LuaRuntime::FontIsLoadedFn method = LuaRuntime::FontIsLoadedThunk();
    if (method == 0) {
        return luaL_error(state, "Font:IsLoaded native binding is unavailable");
    }
    // Reads `+0x00` only, so it is safe on an unloaded object -- which is exactly what makes it
    // usable as the gate for the measurement methods.
    const bool loaded = method(font);
    g_FontIsLoadedCalls.fetch_add(1, std::memory_order_relaxed);
    g_FontIsLoadedResult.store(loaded ? 1U : 0U, std::memory_order_relaxed);
    lua_pushboolean(state, loaded ? 1 : 0);
    return 1;
}

int FontGetStringWidth(lua_State* state) {
    void* font = nullptr;
    if (const int error = ResolveFont(state, "Font:GetStringWidth", &font); error != 0) {
        return error;
    }
    if (lua_gettop(state) != 2 || !lua_isstring(state, 2)) {
        return luaL_error(state, "Font:GetStringWidth accepts a string");
    }
    const LuaRuntime::FontGetStringWidthFn method = LuaRuntime::FontGetStringWidthThunk();
    if (method == 0) {
        return luaL_error(state, "Font:GetStringWidth native binding is unavailable");
    }
    if (const int error = RequireLoadedFont(state, font, "Font:GetStringWidth"); error != 0) {
        return error;
    }
    lua_pushinteger(state, static_cast<lua_Integer>(
                               method(font, lua_tostring(state, 2))));
    return 1;
}

int FontGetStringWidthUTF8(lua_State* state) {
    void* font = nullptr;
    if (const int error = ResolveFont(state, "Font:GetStringWidthUTF8", &font); error != 0) {
        return error;
    }
    if (lua_gettop(state) != 2 || !lua_isstring(state, 2)) {
        return luaL_error(state, "Font:GetStringWidthUTF8 accepts a string");
    }
    const LuaRuntime::FontGetStringWidthUTF8Fn method = LuaRuntime::FontGetStringWidthUTF8Thunk();
    if (method == 0) {
        return luaL_error(state, "Font:GetStringWidthUTF8 native binding is unavailable");
    }
    if (const int error = RequireLoadedFont(state, font, "Font:GetStringWidthUTF8"); error != 0) {
        return error;
    }
    // The native function converts UTF-8 into a module-static 512-unit UTF-16 buffer before
    // measuring, so it is not reentrant and silently truncates longer strings; both properties
    // belong to the game and are not something this handler can repair.
    lua_pushinteger(
        state, static_cast<lua_Integer>(
                   method(font, lua_tostring(state, 2))));
    return 1;
}

int FontGetLineHeight(lua_State* state) {
    void* font = nullptr;
    if (const int error = ResolveFont(state, "Font:GetLineHeight", &font); error != 0) {
        return error;
    }
    if (lua_gettop(state) != 1) {
        return luaL_error(state, "Font:GetLineHeight accepts no arguments");
    }
    const LuaRuntime::FontGetLineHeightFn method = LuaRuntime::FontGetLineHeightThunk();
    if (method == 0) {
        return luaL_error(state, "Font:GetLineHeight native binding is unavailable");
    }
    if (const int error = RequireLoadedFont(state, font, "Font:GetLineHeight"); error != 0) {
        return error;
    }
    lua_pushinteger(state, static_cast<lua_Integer>(method(font)));
    return 1;
}

int FontGetBaselineHeight(lua_State* state) {
    void* font = nullptr;
    if (const int error = ResolveFont(state, "Font:GetBaselineHeight", &font); error != 0) {
        return error;
    }
    if (lua_gettop(state) != 1) {
        return luaL_error(state, "Font:GetBaselineHeight accepts no arguments");
    }
    const LuaRuntime::FontGetBaselineHeightFn method = LuaRuntime::FontGetBaselineHeightThunk();
    if (method == 0) {
        return luaL_error(state, "Font:GetBaselineHeight native binding is unavailable");
    }
    if (const int error = RequireLoadedFont(state, font, "Font:GetBaselineHeight"); error != 0) {
        return error;
    }
    lua_pushinteger(state,
                    static_cast<lua_Integer>(method(font)));
    return 1;
}

int FontGetCharacterWidth(lua_State* state) {
    void* font = nullptr;
    if (const int error = ResolveFont(state, "Font:GetCharacterWidth", &font); error != 0) {
        return error;
    }
    if (lua_gettop(state) != 2 || !isaac::runtime::IsIntegerArgument(state, 2)) {
        return luaL_error(state, "Font:GetCharacterWidth accepts a character integer");
    }
    const lua_Integer character = lua_tointegerx(state, 2, nullptr);
    // The native `GetCharacterWidth(char)` computes its table displacement as `w1, sxtb`: a byte
    // >= 0x80 sign-extends into a *negative* displacement and reads in front of the glyph table
    // (Stage148 ABI audit). Every in-module caller passes an ASCII byte, so the handler accepts
    // 0..0x7F and refuses the rest instead of dispatching a wild read. Non-ASCII queries need the
    // unicode overload `GetCharacterWidth(unsigned short)` (0x4CE968), which this batch does not
    // publish yet.
    if (character < 0 || character > 0x7F) {
        return luaL_error(state, "Font:GetCharacterWidth accepts an ASCII character (0-127)");
    }
    const LuaRuntime::FontGetCharacterWidthFn method = LuaRuntime::FontGetCharacterWidthThunk();
    if (method == 0) {
        return luaL_error(state, "Font:GetCharacterWidth native binding is unavailable");
    }
    if (const int error = RequireLoadedFont(state, font, "Font:GetCharacterWidth"); error != 0) {
        return error;
    }
    lua_pushinteger(state, static_cast<lua_Integer>(method(
                               font, static_cast<char>(character))));
    return 1;
}

int FontSetMissingCharacter(lua_State* state) {
    void* font = nullptr;
    if (const int error = ResolveFont(state, "Font:SetMissingCharacter", &font); error != 0) {
        return error;
    }
    if (lua_gettop(state) != 2 || !isaac::runtime::IsIntegerArgument(state, 2)) {
        return luaL_error(state, "Font:SetMissingCharacter accepts a character integer");
    }
    const lua_Integer character = lua_tointegerx(state, 2, nullptr);
    if (character < 0 || character > 0xFFFF) {
        return luaL_error(state, "Font:SetMissingCharacter accepts a uint16 character");
    }
    const LuaRuntime::FontSetMissingCharacterFn method = LuaRuntime::FontSetMissingCharacterThunk();
    if (method == 0) {
        return luaL_error(state, "Font:SetMissingCharacter native binding is unavailable");
    }
    // Deliberately *not* gated on `IsLoaded()`: the native function writes the single
    // `glyphIndex[0xFFFF]` slot at +0x2004E, which `Font()` initialises and `Unload()` resets, and
    // it dereferences no glyph record. The unsafe combination -- a missing character >= 255 set on
    // an object that was never loaded -- is contained by the `IsLoaded()` gate on every
    // measurement method above, which is the only path that would follow the index.
    method(font, static_cast<std::uint16_t>(character));
    return 0;
}

// `DrawString` 与它的三个变体共用参数解析与守卫，只有三处不同：是否多收 `ScaleX`/`ScaleY`
// （走 s2/s3）、调哪个原生入口、以及错误信息里的方法名。
//
//   PC: DrawString            (Text, X, Y,               KColor, BoxWidth = 0, Center = false)
//       DrawStringScaled      (Text, X, Y, ScaleX, ScaleY, KColor, BoxWidth = 0, Center = false)
//       DrawStringUTF8        (Text, X, Y,               KColor, BoxWidth = 0, Center = false)
//       DrawStringScaledUTF8  (Text, X, Y, ScaleX, ScaleY, KColor, BoxWidth = 0, Center = false)
//
// 四个原生入口紧挨在一起（`0x4CEEF0`/`0x4CEF6C`/`0x4CF2A4`/`0x4CFAB8`），反汇编核对过：
// 坐标在 s0/s1、缩放在 s2/s3、颜色走整数寄存器 x2（不可见引用）、w3 = boxWidth、w4 = center。


int DrawStringVariant(lua_State* state, const char* apiName, bool scaled, bool unicode) {
    // 批次 087/093：整个处理器由**挂载处的中央包装**计时；这里只保留 apiId，
    // 用来给"**引擎调用那一段**"单独记一笔（键盘高位标记区分，见 `runtime_perf.hpp`）。
    // catalog id：`DrawString`=0x0B01000A、`+1` 缩放、`+2` UTF-8（与本文件的绑定表一致，门禁核对）。
    const std::uint32_t apiId =
        0x0B01000AU + (scaled ? 1U : 0U) + (unicode ? 2U : 0U);
    void* font = nullptr;
    if (const int error = ResolveFont(state, apiName, &font); error != 0) {
        return error;
    }
    // 栈布局（1 = self）：DrawString 的 color 在第 5 位；带缩放的变体多了 ScaleX/ScaleY 两位，
    // 所以 color 在第 7 位。
    const int colorIndex = scaled ? 7 : 5;
    const int argumentCount = lua_gettop(state);
    if (argumentCount < colorIndex || argumentCount > colorIndex + 2 ||
        !lua_isstring(state, 2) || !lua_isnumber(state, 3) || !lua_isnumber(state, 4) ||
        (scaled && (!lua_isnumber(state, 5) || !lua_isnumber(state, 6)))) {
        return luaL_error(state,
                          "%s accepts text, x, y%s, KColor and optional boxWidth/center", apiName,
                          scaled ? ", scaleX, scaleY" : "");
    }
    // The colour is a Runtime-owned 16-byte RGBA block; the engine takes `Color` through an
    // invisible reference (its class has a user-defined copy constructor), so the pointer is
    // exactly what the native call expects.
    auto* color = static_cast<LuaRuntime::ColorHandle*>(
        luaL_checkudata(state, colorIndex, LuaRuntime::kColorMetatable));
    int boxWidth = 0;
    if (argumentCount >= colorIndex + 1) {
        if (!isaac::runtime::IsIntegerArgument(state, colorIndex + 1)) {
            return luaL_error(state, "%s boxWidth must be an integer", apiName);
        }
        boxWidth = static_cast<int>(lua_tointeger(state, colorIndex + 1));
    }
    bool center = false;
    if (argumentCount == colorIndex + 2) {
        if (lua_type(state, colorIndex + 2) != LUA_TBOOLEAN) {
            return luaL_error(state, "%s center must be a boolean", apiName);
        }
        center = lua_toboolean(state, colorIndex + 2) != 0;
    }
    // 四个变体（缩放与否 × UTF-8 与否）**签名不同**：缩放版多两个 float，所以不是同一个类型，
    // 不能塞进一个变量里选。这里按分支各自取、各自调，类型来自 `lua_runtime_state.hpp` 里
    // 那一份声明（参数个数与类型由编译器核对；此前是各自写一份 `using` 再 reinterpret_cast）。
    const LuaRuntime::FontDrawStringScaledFn scaledMethod = unicode
        ? LuaRuntime::FontDrawStringScaledUTF8Thunk()
        : LuaRuntime::FontDrawStringScaledThunk();
    const LuaRuntime::FontDrawStringFn plainMethod =
        unicode ? LuaRuntime::FontDrawStringUTF8Thunk() : LuaRuntime::FontDrawStringThunk();
    if (scaled ? scaledMethod == nullptr : plainMethod == nullptr) {
        return luaL_error(state, "%s native binding is unavailable", apiName);
    }
    // Drawing an object that never completed `Load` would read the uninitialised glyph tables,
    // so the same gate the measurement methods use applies here.
    if (const int error = RequireLoadedFont(state, font, apiName); error != 0) {
        return error;
    }
    const char* text = lua_tostring(state, 2);
    const float x = static_cast<float>(lua_tonumber(state, 3));
    const float y = static_cast<float>(lua_tonumber(state, 4));
    // ★ 2026-09-18 批次 037 修正：这几条读数以前写在**未缩放**那个分支里，于是
    // `Font:DrawStringScaled*`（EID、q4-items、自带菜单、我们自己的 `Isaac.RenderScaledText`
    // **全都走这条**）一次都不计数 ⇒ 读数里永远是"画字 0 次"，而它被当成过"屏幕上什么都没画"
    // 的证据（当天差点把一个探针自身的毛病误判成运行时缺陷）。现在四条变体**共用**这几个计数点，
    // 由 API 序列位区分用的是哪一个变体。
    std::size_t textLength = 0;
    static_cast<void>(lua_tolstring(state, 2, &textLength));
    g_FontDrawCalls.fetch_add(1, std::memory_order_relaxed);
    g_FontDrawBytes.fetch_add(static_cast<std::uint32_t>(textLength),
                              std::memory_order_relaxed);
    // API 序列：`DrawString`(32) / `DrawStringScaled`(33) / `DrawStringUTF8`(34) /
    // `DrawStringScaledUTF8`(35) —— 四个变体分别记位，"用了哪一个"本身就是判据。
    RecordApiSequence(32U + (scaled ? 1U : 0U) + (unicode ? 2U : 0U));
    RecordApiSequenceDraw(textLength);
    // 颜色 alpha 与缩放：alpha=0 或 scale=0 都会"画了但看不见"，必须能从报告上分辨。
    g_FontDrawAlpha.store(static_cast<std::uint32_t>(color->alpha * 1000.0F) & 0xFFFFu,
                          std::memory_order_relaxed);
    if (scaled && lua_isnumber(state, 5)) {
        g_FontDrawScaleX.store(
            static_cast<std::uint32_t>(static_cast<float>(lua_tonumber(state, 5)) * 1000.0F) &
                0xFFFFu,
            std::memory_order_relaxed);
    }
    // 批次 087：单独量"引擎调用那一段"。有了它就能算
    // `整个 handler 的耗时 − 引擎调用耗时 = 我们自己（解析 / 守卫 / 搬运）的开销`。
    const std::uint64_t engineStart = isaac::runtime::RuntimePerfTick();
    if (scaled) {
        const float scaleX = static_cast<float>(lua_tonumber(state, 5));
        const float scaleY = static_cast<float>(lua_tonumber(state, 6));
        scaledMethod(font, text, x, y, scaleX, scaleY, color, boxWidth, center);
    } else {
        plainMethod(font, text, x, y, color, boxWidth, center);
    }
    // `IsaacRuntime_PerfNoteApiCall` 是**全局作用域**的 `extern "C"` 契约函数
    // （声明在 `runtime_perf.hpp` 的 `extern "C"` 块里，不在 `isaac::runtime` 命名空间内）。
    static_cast<void>(IsaacRuntime_PerfNoteApiCall(
        isaac::runtime::RuntimePerfApiBucketKey(apiId, true), engineStart));
    return 0;
}

int FontDrawString(lua_State* state) {
    return DrawStringVariant(state, "Font:DrawString", false, false);
}

int FontDrawStringScaled(lua_State* state) {
    return DrawStringVariant(state, "Font:DrawStringScaled", true, false);
}

int FontDrawStringUTF8(lua_State* state) {
    return DrawStringVariant(state, "Font:DrawStringUTF8", false, true);
}

int FontDrawStringScaledUTF8(lua_State* state) {
    return DrawStringVariant(state, "Font:DrawStringScaledUTF8", true, true);
}

} // namespace

// --- `Isaac.RenderScaledText` 用的"运行时默认字体"（批次 026）------------------------
//
// PC 上 `Isaac.RenderScaledText(str, X, Y, ScaleX, ScaleY, R, G, B, A)`（`Isaac.md:545`）
// 用**游戏默认字体**在屏幕上画一段文字。我们没有"游戏默认字体"的证据，所以这里加载一份
// **运行时自己的**默认字体：候选路径与内置模组菜单是同一批（游戏自带的三个 `.fnt`），
// 顺序也一致 —— 那批路径在本项目里已经用真机验证过能加载。
//
// ⚠️ 已知差异（与内置菜单同一件事）：游戏自带字体**没有中文字形**
// （`tools/fnt_glyph_report.py` 实测 `font/droid.fnt` 191 个字形、码位上限 0xFF、中日韩 0 个）
// ⇒ 用中文调用它只会画出空白。PC 的默认字体同样不是中文字体，所以这不是"我们比 PC 差"，
// 但**必须写下来**，免得以后有人拿它调中文然后查"为什么不显示"。
namespace {
constexpr char kDefaultScreenFontRegistryKey[] = "IsaacRuntime.DefaultScreenFont";
constexpr const char* kDefaultScreenFontPaths[] = {
    "font/teammeatfont12.fnt",
    "font/droid.fnt",
    "font/terminus.fnt",
};

// 把运行时默认字体压到栈顶（命中缓存时直接压缓存那份）。**要求调用前栈是空的**
// （`Font()` 构造器 `CreateFontHandle` 就是这么要求的），失败返回 false 并保持空栈。
bool PushDefaultScreenFont(lua_State* state) {
    if (state == nullptr || lua_gettop(state) != 0) {
        return false;
    }
    lua_getfield(state, LUA_REGISTRYINDEX, kDefaultScreenFontRegistryKey);
    if (lua_type(state, -1) == LUA_TUSERDATA) {
        return true;  // 缓存命中：栈顶就是它
    }
    lua_pop(state, 1);
    for (const char* path : kDefaultScreenFontPaths) {
        if (CreateFontHandle(state) != 1) {  // 栈：font
            lua_settop(state, 0);
            return false;
        }
        lua_pushstring(state, path);         // 栈：font, path
        // `FontLoad` 是 Lua 侧那个处理器（`Font:Load`）：它**不消费实参**，只把结果压栈
        // ⇒ 返回后栈是 [font, path, bool]，三样都要自己收干净（这是本函数唯一容易写错的地方）。
        if (FontLoad(state) != 1) {          // 栈：font, path, bool
            lua_settop(state, 0);
            return false;
        }
        const bool loaded = lua_toboolean(state, -1) != 0;
        lua_pop(state, 2);                   // 栈：font
        if (loaded) {
            // 缓存进 registry（存的是同一个 userdata 的引用；`__gc` 仍然只跑一次）。
            lua_pushvalue(state, -1);
            lua_setfield(state, LUA_REGISTRYINDEX, kDefaultScreenFontRegistryKey);
            return true;
        }
        lua_pop(state, 1);                   // 这个路径装不上，试下一个
    }
    return false;
}
} // namespace

bool DrawScaledTextWithDefaultFont(lua_State* state, const char* text, std::size_t length,
                                   float x, float y, float scaleX, float scaleY, float red,
                                   float green, float blue, float alpha) {
    if (state == nullptr || text == nullptr || lua_gettop(state) != 0) {
        return false;
    }
    // ① 字体（此时栈空）。② 之后的顺序就是 `DrawStringVariant` 要求的那个栈布局：
    //    [font, text, x, y, scaleX, scaleY, color]。
    if (!PushDefaultScreenFont(state)) {
        lua_settop(state, 0);
        return false;
    }
    lua_pushlstring(state, text, length);
    lua_pushnumber(state, static_cast<lua_Number>(x));
    lua_pushnumber(state, static_cast<lua_Number>(y));
    lua_pushnumber(state, static_cast<lua_Number>(scaleX));
    lua_pushnumber(state, static_cast<lua_Number>(scaleY));
    // ③ 颜色：**不能用 `CreateColorHandle`**（那是 Lua 侧 `KColor(...)` 的构造器，它按栈位
    //    1..4 取参数，而这里第 1 位是字体）；直接造同一份 `ColorHandle` + 同一个元表，
    //    值与 Lua 构造出来的完全等价。
    auto* color =
        static_cast<LuaRuntime::ColorHandle*>(lua_newuserdata(state, sizeof(LuaRuntime::ColorHandle)));
    color->red = red;
    color->green = green;
    color->blue = blue;
    color->alpha = alpha;
    color->offsetRed = 0.0F;
    color->offsetGreen = 0.0F;
    color->offsetBlue = 0.0F;
    luaL_getmetatable(state, LuaRuntime::kColorMetatable);
    lua_setmetatable(state, -2);
    // ④ 走**同一条**绘制路径：参数校验、四个变体的选择、绘制探针（调用次数/文本字节/
    //    alpha/缩放）全都在里面，不另写一份。它按 `unicode` 决定用哪条引擎入口，而
    //    `DrawStringVariant` 只认 bool 参数 —— 这里用"文本里有没有非 ASCII 字节"来选，
    //    UTF-8 文本走 UTF8 变体（与 EID 自己 `font:DrawStringScaledUTF8` 的选择口径一致）。
    bool unicode = false;
    for (std::size_t index = 0; index < length; ++index) {
        if (static_cast<unsigned char>(text[index]) >= 0x80) {
            unicode = true;
            break;
        }
    }
    if (unicode) {
        static_cast<void>(FontDrawStringScaledUTF8(state));
    } else {
        static_cast<void>(FontDrawStringScaled(state));
    }
    lua_settop(state, 0);
    return true;
}

int CreateFontHandle(lua_State* state) {
    if (lua_gettop(state) != 0) {
        return luaL_error(state, "Font accepts no arguments");
    }
    const LuaRuntime::FontCtorFn ctor = LuaRuntime::FontCtorThunk();
    const LuaRuntime::FontDestructorFn destructorMethod = LuaRuntime::FontDestructorThunk();
    if (ctor == 0 || destructorMethod == 0) {
        return luaL_error(state, "Font native binding is unavailable");
    }
    // The userdata is created first and starts unbound, so an allocation failure below unwinds
    // through `luaL_error` with nothing to release and no `__gc` installed yet.
    auto* handle = static_cast<FontHandle*>(lua_newuserdata(state, sizeof(FontHandle)));
    handle->font = nullptr;
    void* font = AllocateFontStorage();
    if (font == nullptr) {
        return luaL_error(state, "Font could not allocate its native object");
    }
    ctor(font);
    handle->font = font;
    luaL_getmetatable(state, kFontMetatable);
    lua_setmetatable(state, -2);
    return 1;
}

int DestroyFontHandle(lua_State* state) {
    auto* handle = static_cast<FontHandle*>(luaL_checkudata(state, 1, kFontMetatable));
    if (handle->font == nullptr) {
        // Idempotent: Lua may collect a userdata that failed to construct, and a double release of
        // this block would be a use-after-free.
        return 0;
    }
    const LuaRuntime::FontDestructorFn destructorMethod = LuaRuntime::FontDestructorThunk();
    if (destructorMethod != 0) {
        // `~Font()` is a tail-jump to `Unload()`: it releases the Font's internal buffers and does
        // not delete `this`, so the storage below is released here and nowhere else. The
        // destructor binding cannot be zero on this path -- `CreateFontHandle` refuses to hand out
        // a handle without it -- but a missing binding must not make `__gc` raise.
        destructorMethod(handle->font);
    }
    ReleaseFontStorage(handle->font);
    handle->font = nullptr;
    return 0;
}

std::size_t AttachFontMethods(lua_State* state) noexcept {
    return AttachOwnerMethods(state, kFontOwner, kFontHandlers,
                              sizeof(kFontHandlers) / sizeof(kFontHandlers[0]));
}

// `Font:Load` 最近一次交给引擎的**名字与结果**（探针读；声明见 `font_api.hpp`）。
//
// 为什么必须留在 `.cpp` 里：`FontLoad` 在这个 TU 内部；把观测点写进探针 TU 就只能靠复刻一份
// 归一化去猜（本轮已经吃过一次这个亏）。这里只是把本 TU 已经算出来的事实**记下来**，
// 不参与任何判断，生产构建里也没有调用方（`--gc-sections` 会回收）。
namespace {
std::atomic<std::uint32_t> g_LastFontLoadWord{0};
}

std::uint32_t FontDrawCallCountForProbe() noexcept {
    return g_FontDrawCalls.load(std::memory_order_acquire);
}

std::uint32_t FontDrawByteCountForProbe() noexcept {
    return g_FontDrawBytes.load(std::memory_order_acquire);
}

FontChainProbe FontChainProbeSnapshot() noexcept {
    FontChainProbe probe{};
    probe.loadCalls = g_FontLoadCalls.load(std::memory_order_relaxed);
    probe.loadResult = g_FontLoadResult.load(std::memory_order_relaxed);
    probe.isLoadedCalls = g_FontIsLoadedCalls.load(std::memory_order_relaxed);
    probe.isLoadedResult = g_FontIsLoadedResult.load(std::memory_order_relaxed);
    probe.drawAlphaMilli = g_FontDrawAlpha.load(std::memory_order_relaxed);
    probe.drawScaleXMilli = g_FontDrawScaleX.load(std::memory_order_relaxed);
    return probe;
}

void RecordFontLoadForProbe(const std::string_view handedToEngine, bool accepted) noexcept {
    // 一个字：
    //   bit0        引擎侧接受了这个名字（`Font:Load` 的返回值）
    //   bit1        名字是非空内容挂载点相对名（不含 `rom:/`、不以 `/` 开头、不含 `/../`）
    //   bits 8..15  名字长度（>255 截断；正常名字 20 字节上下）
    //   bits 16..47 名字前 4 字节（ASCII），用来与宿主逐字比对
    std::uint32_t word = accepted ? 1u : 0u;
    if (!handedToEngine.empty() && handedToEngine.rfind("rom:/", 0) != 0 &&
        handedToEngine.front() != '/' && handedToEngine.find("/../") == std::string_view::npos) {
        word |= 1u << 1;
    }
    const std::uint32_t length = static_cast<std::uint32_t>(handedToEngine.size());
    word |= (length > 0xFFu ? 0xFFu : length) << 8;
    for (std::size_t index = 0; index < 4 && index < handedToEngine.size(); ++index) {
        word |= static_cast<std::uint32_t>(
                    static_cast<unsigned char>(handedToEngine[index]))
                << (16 + 8 * index);
    }
    g_LastFontLoadWord.store(word, std::memory_order_release);
}

std::uint32_t LastFontLoadWordForProbe() noexcept {
    return g_LastFontLoadWord.load(std::memory_order_acquire);
}

// 宿主验证通道用的归一化出口（声明见 `font_api.hpp` 的注释）。
//
// 它调用的是 `FontLoad` 用的**同一个**内部实现，所以宿主读到的就是真机的行为；生产构建里
// 只有宿主 harness 链接得到它（`eid_host_load.py`），Runtime 自身不引用，`--gc-sections`
// 在真机产物里也不会因为多这几十字节而改变布局判断（RAM/体积门禁照旧跑）。
std::string_view NormalizeModResourcePathForProbe(const char* path,
                                                  std::string& storage) noexcept {
    return NormalizeModResourcePath(path, storage);
}

} // namespace isaac::runtime
