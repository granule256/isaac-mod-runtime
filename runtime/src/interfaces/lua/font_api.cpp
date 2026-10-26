#include "infrastructure/memory/engine_field_access.hpp"
#include <string>
#include <string_view>
#include "interfaces/lua/runtime_perf.hpp"
#include "interfaces/lua/api_sequence_probe.hpp"
#include "interfaces/lua/font_api.hpp"
#include "interfaces/lua/font_width_cache.hpp"
#include "interfaces/lua/color_api.hpp"

#include "interfaces/lua/lua_integer_argument.hpp"
#include "interfaces/lua/owner_binding.hpp"

#include "lua_object_handles.hpp"
#include "lua_runtime_state.hpp"
#include "lua_runtime.hpp"
#include "runtime_constants.hpp"

// 批次 415：Font 存储改走 **Lua 状态自己的分配器**（`lua_getallocf`）—— 不再需要额外头文件
// （`lua_getallocf` / `lua_Alloc` 由 `lua.h` 提供，已经通过 `lauxlib.h` 拿得到）。

#include <atomic>
#include <cstddef>
#include <cstdint>
#include <cstdlib>

extern "C" {
#include <lauxlib.h>
#include "probe_gate.hpp"
}

// 271-perf：贴图桥里的"`Font::Load` 窗口"开关（定义在 `source/image_pcx_bridge_hook.cpp`）。
// 作用：把引擎这次字体加载**包成一个时间窗口**，好让贴图桥那边能回答
// "窗口内我们自己的图像层花了多少、引擎自己花多少"。跨 TU 只走函数调用（数据 GOT 那条坑见
// `interfaces/lua/runtime_perf.hpp` 顶部）。
//
// ★ 挂在 `EXL_DIAGNOSTIC_PROBES` 门控里（与批次 262 把诊断开销收进门控同一口径）：
//   这是纯量具，正式包不需要；而且宿主夹具里**只链 Lua 运行时、不链贴图桥**
//   （`test_lua_font_resources` 的 harness 就是这么编的），不加门控会直接链接失败。
#if EXL_DIAGNOSTIC_PROBES
extern "C" void IsaacRuntime_FontLoadWindowBegin() noexcept;
extern "C" void IsaacRuntime_FontLoadWindowEnd(std::uint32_t micros, std::uint32_t glyphCount,
                                               std::uint32_t charsSpan) noexcept;
#endif

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

// ---------------------------------------------------------------------------
// 批次 414（2026-10-08）：`Font` 的实例存储先试过"固定块池"；**415 改成走 Lua 分配器**。
// ---------------------------------------------------------------------------
// 现场与结论（414 的真机读数把根因钉出来了，见 `dist/change-archive-20261008/414-*/README.md`）：
//   414 用"固定块池 + 我们自己的 malloc"，池本身工作正常（**成功发出过 384 块**、峰值满负荷），
//   但真机上 `当前在外 = 288` 个 Font **没被回收**、`chunk 要不到 = 1194`（堆空闲 31.9 MB 但
//   没有连续 8 MiB）。⇒ 根因**不在分配器，在 GC**：那 **128 KiB 是用我们自己的 `malloc` 拿的，
//   而 Lua 的 GC 看不见它**（userdata 本身只有十几字节）⇒ GC 没有理由回收 ⇒ 越攒越多把堆吃干。
//   （PC 上同一份模组不炸：那边 OS 内存大，且 GC 被别的垃圾触发时照样收掉这些 userdata。）
//
// 415 的修法 = 这笔内存**从 Lua 状态自己的分配器拿**（`lua_getallocf`）：
//   它计入 Lua 的 GC 账 ⇒ GC 按需回收 ⇒ 288 个活 Font 那种堆积不会再发生。
//   ★★ **2026-10-10（批次 425）订正：上面那句"它计入 Lua 的 GC 账"是错的。**
//     走 `lua_getallocf` 拿到的是**裸 `frealloc`**（`lapi.c:1169` = `return G(L)->frealloc;`），
//     而 Lua **只在 `luaM_realloc_` 里更新 `g->GCdebt`**（`lmem.c:97`）⇒
//     **直接调 `frealloc` 恰好绕过了这笔账** ⇒ 这些块**不进 Lua 的用量统计** ⇒
//     GC 的触发判断（`GCdebt` 对 `GCthreshold`）**永远看不到它们**。
//     真机实证（424 那版，152 MiB 堆）：`whatsmydps` 每帧一个 Font（`MC_POST_RENDER`），
//     **存活块数锯到 507 块 = 63 MB**，而它**每约 250 帧才被收一次**（等别的分配顺手触发）。
//     ⇒ 425 的修法见 `lua_runtime_state.hpp` 的 `NudgeLuaGcIfFontBlocksHigh()`：
//       这笔内存**我们自己看得见**（`g_FontStorageLive`）⇒ 由我们把它**补报**给 GC。
//     （415 换到 Lua 分配器这条路**仍然是对的**——比自己开池子好得多，池那版连
//      "谁在还"都追不到；只是它**不足以**让 GC 主动回收。）
//   ★ 池的"固定尺寸复用"思想本身没错，但它的块**对 GC 不可见**，正好是病因 ⇒ 撤掉池接线
//     （池的实现与其用例一并删除，不留死代码）。
//
// ★ 参数与对齐口径与最早那版一致（那两条与 GC 无关，仍然成立）：
//   块对 **16 字节对齐**（`Font` 要求 16，而分配器只保证 8），**原始指针存在对象前面 8 字节**，
//   归还时读回来交给同一个分配器（`osize` 与分配时一致、`nsize = 0` = 释放）。
// ★ 探针量仍是**外部链接**（写在 `namespace {` 之前）：读数工具按符号名读
//   （技能 `isaac-switch-probe-batch` §11，本项目已因此栽过 5 次）。
std::atomic<std::uint32_t> g_FontStorageAllocations{0};  // 累计分配次数
std::atomic<std::uint32_t> g_FontStorageLive{0};         // 当前活着（未归还）的 Font 数 ★ 关键判据
std::atomic<std::uint32_t> g_FontStorageLivePeak{0};     // 峰值
std::atomic<std::uint32_t> g_FontStorageFailures{0};     // 分配失败次数（拿不到分配器 / 分配返回空）

//: ★★ 批次 425：只读壳（**外部链接**，与上面那四个计数一样写在 `namespace {` 之外）。
//: 调用方是 `mod_menu_native.cpp` 的每帧路径 —— 它把这个数交给
//: `LuaRuntime::NudgeLuaGcIfFontBlocksHigh()` 去催 GC（原因见 `font_api.hpp` 里那段）。
std::uint32_t FontStorageLiveBlocks() noexcept {
    return g_FontStorageLive.load(std::memory_order_relaxed);
}

std::uint32_t FontStorageAllocationCount() noexcept { return g_FontStorageAllocations.load(std::memory_order_relaxed); }
std::atomic<std::uint32_t> g_FontStorageDestructions{0};
std::uint32_t FontStorageDestructionCount() noexcept { return g_FontStorageDestructions.load(std::memory_order_relaxed); }

namespace {

using LuaRuntime::FontHandle;
using LuaRuntime::kFontMetatable;

FontWidthCache g_FontWidthCache{};

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
// ★ 2026-10-08（批次 414 → **415**）更正链：这一段最早是"`malloc` 一块、把原始指针存在对象前面
//   （`kFontStorageSlack`）"；414 改成固定块池（想治"每帧 128 KiB 撞碎片"）；**415 改成走
//   Lua 状态自己的分配器** —— 因为真机读数证明根因是 **GC 看不见这笔内存**（见文件顶部那段）。
//   **上面两段原始推导一字未删**，留着看历史；池的实现与用例已随 415 删除（不留死代码）。
constexpr std::size_t kFontAlignment = 16;
// 2026-10-13订正：Lua拥有整个原生对象，lua_newuserdata经luaM_realloc_计账。
constexpr std::size_t kFontStorageBytes = sizeof(FontHandle) + kFontObjectSize + kFontAlignment - 1;
void* AllocateFontStorage(lua_State* state) {
    auto* handle = static_cast<FontHandle*>(lua_newuserdata(state, kFontStorageBytes));
    handle->font = nullptr;
    const auto address = reinterpret_cast<std::uintptr_t>(handle) + sizeof(FontHandle);
    const auto aligned = (address + kFontAlignment - 1) & ~(static_cast<std::uintptr_t>(kFontAlignment) - 1);
    g_FontStorageAllocations.fetch_add(1, std::memory_order_relaxed);
    const auto live = g_FontStorageLive.fetch_add(1, std::memory_order_relaxed) + 1;
    auto peak = g_FontStorageLivePeak.load(std::memory_order_relaxed);
    while (live > peak && !g_FontStorageLivePeak.compare_exchange_weak(peak, live)) {}
    return reinterpret_cast<void*>(aligned);
}
void ReleaseFontStorage(lua_State*, void*) noexcept {
    // 仅记原生析构；内存直到userdata实际回收才由Lua归还，不能free内部地址。
    g_FontStorageLive.fetch_sub(1, std::memory_order_relaxed);
    g_FontStorageDestructions.fetch_add(1, std::memory_order_relaxed);
}

struct BorrowedGameFont{FontHandle value;std::uintptr_t module,game;};
bool LiveGameFont(const BorrowedGameFont*view)noexcept{
 const auto base=LuaRuntime::EngineModuleBase();std::uintptr_t slot{},game{};
 if(!base||base!=view->module||base>UINTPTR_MAX-kGameOwnerGlobalSlotOffset)return false;
 return engine_memory::ReadAt(base+kGameOwnerGlobalSlotOffset,&slot,engine_memory::EngineMemoryReadable)&&slot&&engine_memory::ReadAt(slot,&game,engine_memory::EngineMemoryReadable)&&game==view->game&&engine_memory::EngineMemoryReadable(engine_memory::AddressOf(view->value.font),kFontObjectSize);
}

// --- Shared preludes -------------------------------------------------------

// Resolves method argument 1 to this module's Font instance. `luaL_checkudata` rejects a foreign
// value with Lua's standard message; a handle that `__gc` already released is unreachable in
// normal use, but a null object must never reach a native call. Returns 0 when the call may
// proceed, otherwise the Lua error code to return verbatim.
int ResolveFont(lua_State* state, const char* apiName, void** font, bool* cacheable = nullptr) {
    auto* handle = static_cast<FontHandle*>(luaL_checkudata(state, 1, kFontMetatable));
    const std::size_t storageBytes = lua_rawlen(state, 1);
    const bool borrowed = storageBytes == sizeof(BorrowedGameFont);
    if (cacheable != nullptr) *cacheable = storageBytes == kFontStorageBytes;
    if(borrowed&&!LiveGameFont(static_cast<const BorrowedGameFont*>(lua_touserdata(state,1))))return luaL_error(state,"%s: borrowed Font owner is no longer available",apiName);
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
    g_FontWidthCache.Invalidate(state, lua_touserdata(state, 1));
#if EXL_DIAGNOSTIC_PROBES
    // 271-perf：把这次引擎 `Font::Load` 包成窗口 + 计时（回答"那 1 秒在谁的代码里"）。
    const std::uint64_t fontBeginTick = isaac::runtime::RuntimePerfTick();
    IsaacRuntime_FontLoadWindowBegin();
#endif
    const bool loaded = method(font, handedToEngine, extension);
#if EXL_DIAGNOSTIC_PROBES
    const std::uint64_t fontEndTick = isaac::runtime::RuntimePerfTick();
    std::uint32_t fontMicros = 0;
    if (fontEndTick > fontBeginTick) {
        fontMicros = static_cast<std::uint32_t>(
            (fontEndTick - fontBeginTick) * 1000000ULL /
            isaac::runtime::RuntimePerfTicksPerSecond());
    }
    // 字形数与"字形块大小 / 10"：偏移由 `KAGE::Graphics::Font::Load`(0x4cdeb8) 的反汇编推得
    // （`str w22, [x19, #0x24]` 存的是"块大小 / 20" = 字形数；`str w8, [x19, #0x30]` 存的是"块大小 / 10"）。
    // **只读**、只做对账，不参与任何判断；且只在诊断包里读（宿主用例的假 font 指针不必碰这块内存）。
    std::uint32_t glyphCount = 0;
    std::uint32_t charsSpan = 0;
    if (loaded && font != nullptr) {
        const auto* fontBytes = static_cast<const std::uint8_t*>(font);
        glyphCount = *reinterpret_cast<const std::uint32_t*>(fontBytes + 0x24);
        charsSpan = *reinterpret_cast<const std::uint32_t*>(fontBytes + 0x30);
    }
    IsaacRuntime_FontLoadWindowEnd(fontMicros, glyphCount, charsSpan);
#endif
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
    g_FontWidthCache.Invalidate(state, lua_touserdata(state, 1));
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
    bool cacheable = false;
    if (const int error = ResolveFont(state, "Font:GetStringWidth", &font, &cacheable); error != 0) {
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
    std::size_t length = 0;
    const char* text = lua_tolstring(state, 2, &length);
    const FontWidthCache::Key key{state, lua_touserdata(state, 1), font,
        reinterpret_cast<std::uintptr_t>(method), LuaRuntime::FontBindingGeneration(), false};
    int width = 0;
    if (!cacheable || !g_FontWidthCache.Find(key, text, length, &width)) {
        width = method(font, text);
        if (cacheable) g_FontWidthCache.Insert(key, text, length, width);
    }
    lua_pushinteger(state, static_cast<lua_Integer>(width));
    return 1;
}

int FontGetStringWidthUTF8(lua_State* state) {
    void* font = nullptr;
    bool cacheable = false;
    if (const int error = ResolveFont(state, "Font:GetStringWidthUTF8", &font, &cacheable); error != 0) {
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
    std::size_t length = 0;
    const char* text = lua_tolstring(state, 2, &length);
    const FontWidthCache::Key key{state, lua_touserdata(state, 1), font,
        reinterpret_cast<std::uintptr_t>(method), LuaRuntime::FontBindingGeneration(), true};
    int width = 0;
    if (!cacheable || !g_FontWidthCache.Find(key, text, length, &width)) {
        width = method(font, text);
        if (cacheable) g_FontWidthCache.Insert(key, text, length, width);
    }
    lua_pushinteger(state, static_cast<lua_Integer>(width));
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
    g_FontWidthCache.Invalidate(state, lua_touserdata(state, 1));
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
    auto* color = RequireColorArgument(state, colorIndex);
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
    // 2026-10-24：PC GetTextWidth契约点名terminus8；菜单字体不能替代默认屏幕字体。
    "font/terminus8.fnt",
};

// 把运行时默认字体压到栈顶（命中缓存时直接压缓存那份）。**要求调用前栈是空的**
// （`Font()` 构造器 `CreateFontHandle` 就是这么要求的），失败返回 false 并保持空栈。
bool PushDefaultScreenFont(lua_State* state) {
    if (state == nullptr || lua_gettop(state) != 0) {
        return false;
    }
    // ★ 批次 269：先问"原生绑定在不在"。`CreateFontHandle` 在构造/析构 thunk 缺失时会
    // **直接 `luaL_error`**（宿主 harness 与"引擎基址没解析到"都是这种情况），
    // 而这一条链要的是"没有可用字体 ⇒ false"，不是把错误抛回模组（那会摘掉整条回调）。
    if (LuaRuntime::FontCtorThunk() == 0 || LuaRuntime::FontDestructorThunk() == 0) {
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
        // ★ 批次 269：`FontLoad` **用受保护调用**，不直接调。
        // 理由：`FontLoad`（Lua 侧那个 `Font:Load` 处理器）在**原生绑定缺失**时会 `luaL_error`
        // （宿主 harness 就是这种情况：没装字体 thunk），而"这一条候选路径装不上"与
        // "整个调用出错"是两件事 —— 直接调会让错误一路抛回模组（`isaac_api.cpp` 的
        // `RenderScaledText`/`RenderText` 那条链）⇒ **摘掉调用它的整条回调**。
        // 改成受保护之后，任何一次加载失败都只是"这条路径不行、试下一条"，最后统一以
        // `false` 表示"没有可用字体"，由调用方按各 API 的降级口径处理（`RenderText` 静默不画、
        // `GetTextWidth` 给 -1）。这也是第 11 条纪律在字体这条链上的落地。
        lua_pushcfunction(state, FontLoad);  // 栈：font, path, loadFn
        lua_pushvalue(state, -3);            // 栈：…, font
        lua_pushvalue(state, -3);            // 栈：…, path
        if (lua_pcallk(state, 2, 1, 0, 0, nullptr) != LUA_OK) {
            lua_settop(state, 0);
            return false;
        }                                    // 栈：font, path, bool
        const bool loaded = lua_toboolean(state, -1);
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

// 文本里有没有非 ASCII 字节 ⇒ 决定走 `*UTF8` 那条引擎入口。
//
// ★ 抽成一个助手（批次 269）：**绘制（`Isaac.RenderText`/`RenderScaledText`）与量宽
// （`Isaac.GetTextWidth`）必须用同一个判据** —— 两处各写一份循环，将来只改一处就会
// 让"画出来的"和"量出来的"用不同字体函数对同一段文本，而那种偏差在屏幕上只表现为"对不齐"。
bool TextHasNonAsciiByte(const char* text, std::size_t length) {
    for (std::size_t index = 0; index < length; ++index) {
        if (static_cast<unsigned char>(text[index]) >= 0x80) {
            return true;
        }
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
    *color = {};
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
    if (TextHasNonAsciiByte(text, length)) {
        static_cast<void>(FontDrawStringScaledUTF8(state));
    } else {
        static_cast<void>(FontDrawStringScaled(state));
    }
    lua_settop(state, 0);
    return true;
}

// `Isaac.GetTextWidth(str)`（`Isaac.md:439`）。量宽与绘制**共用同一份默认字体**：
// 契约 `Isaac.md:441` 明说"与 `Isaac.RenderText()` 用同一个字体"，所以这里复用
// `PushDefaultScreenFont()`（同一个 registry 缓存键），**不另加载一份** ——
// 两份字体会让"量出来的宽度"与"画出来的宽度"在缩放/度量上漂。
//
// 走的是 `Font:GetStringWidth` / `Font:GetStringWidthUTF8` 两个**已有的**处理器
// （它们的引擎绑定、加载检查、UTF-8 静态缓冲区注意事项都在那两处写着），这里只负责
// 把栈摆成它们要的形状（`[font, string]`）并把结果读回来。
bool MeasureTextWithDefaultFont(lua_State* state, const char* text, std::size_t length,
                                int* width) {
    if (state == nullptr || text == nullptr || width == nullptr || lua_gettop(state) != 0) {
        return false;
    }
    if (!PushDefaultScreenFont(state)) {     // 栈：font
        lua_settop(state, 0);
        return false;
    }
    lua_pushlstring(state, text, length);    // 栈：font, text
    // ★ 批次 269：与 `PushDefaultScreenFont` 里的 `FontLoad` 同一个理由 —— 量宽的原生绑定
    // 缺失时 `Font:GetStringWidth*` 会 `luaL_error`，而这条 API 要的是"量不出来 ⇒ -1"，
    // 不是把错误抛回模组（那会摘掉调用它的整条回调）。用受保护调用把它变成 false。
    const bool unicode = TextHasNonAsciiByte(text, length);
    lua_pushcfunction(state, unicode ? FontGetStringWidthUTF8 : FontGetStringWidth);
    lua_pushvalue(state, -3);                // 栈：…, font
    lua_pushvalue(state, -3);                // 栈：…, text
    if (lua_pcallk(state, 2, 1, 0, 0, nullptr) != LUA_OK) {
        lua_settop(state, 0);
        return false;
    }                                        // 栈：font, text, width
    if (!lua_isnumber(state, -1)) {
        lua_settop(state, 0);
        return false;
    }
    *width = static_cast<int>(lua_tointeger(state, -1));
    lua_settop(state, 0);
    return true;
}

int CreateFontHandle(lua_State* state) {
    // Lua5.3关闭时不再终结__gc新建的对象，必须在申请原生所有者之前拒绝。
    if (LuaRuntime::ClosingForModReload()) {
        return luaL_error(state, "Font cannot allocate native resources during mod reload shutdown");
    }
    if (lua_gettop(state) != 0) {
        return luaL_error(state, "Font accepts no arguments");
    }
    const LuaRuntime::FontCtorFn ctor = LuaRuntime::FontCtorThunk();
    const LuaRuntime::FontDestructorFn destructorMethod = LuaRuntime::FontDestructorThunk();
    if (ctor == 0 || destructorMethod == 0) {
        return luaL_error(state, "Font native binding is unavailable");
    }
    // OOM由Lua标准内存错误传播，Lua分配器会先紧急回收再重试；尚无原生对象需析构。
    void* font = AllocateFontStorage(state);
    auto* handle = static_cast<FontHandle*>(lua_touserdata(state, -1));
    ctor(font);
    handle->font = font;
    luaL_getmetatable(state, kFontMetatable);
    lua_setmetatable(state, -2);
    return 1;
}

int DestroyFontHandle(lua_State* state) {
    auto* handle = static_cast<FontHandle*>(luaL_checkudata(state, 1, kFontMetatable));
    g_FontWidthCache.Invalidate(state, handle);
    if(lua_rawlen(state,1)==sizeof(BorrowedGameFont)){handle->font=nullptr;return 0;}
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
    ReleaseFontStorage(state, handle->font);
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
    (void)handedToEngine;  // 批次 232：生产构建里这段被编译掉 ⇒ 参数必然用不上
    (void)accepted;  // 批次 232：生产构建里这段被编译掉 ⇒ 参数必然用不上
#if EXL_DIAGNOSTIC_PROBES  // 批次 232 探针总开关（口径见 probe_gate.hpp）
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
#endif  // EXL_DIAGNOSTIC_PROBES
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

namespace isaac::runtime {
int PushBorrowedGameFont(lua_State*L,std::uintptr_t game,std::uintptr_t offset){
 auto*view=static_cast<BorrowedGameFont*>(lua_newuserdata(L,sizeof(BorrowedGameFont)));
 *view={{engine_memory::AsObject(game+offset)},LuaRuntime::EngineModuleBase(),game};
 luaL_getmetatable(L,LuaRuntime::kFontMetatable);lua_setmetatable(L,-2);return 1;
}
}

namespace isaac::runtime {
void* TryResolveFontArgument(lua_State* state,int index) noexcept {
    auto* handle=static_cast<LuaRuntime::FontHandle*>(luaL_testudata(state,index,LuaRuntime::kFontMetatable));
    if(!handle || lua_rawlen(state,index)<sizeof(LuaRuntime::FontHandle) || !handle->font)return nullptr;
    if(lua_rawlen(state,index)==sizeof(BorrowedGameFont) &&
       !LiveGameFont(static_cast<const BorrowedGameFont*>(lua_touserdata(state,index))))return nullptr;
    return engine_memory::EngineMemoryReadable(engine_memory::AddressOf(handle->font),kFontObjectSize)?handle->font:nullptr;
}
}
