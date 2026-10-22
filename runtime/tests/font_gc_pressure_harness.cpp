
#include "lua_runtime.hpp"
#include "game_file_reader.hpp"
#include "game_observer.hpp"

#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>

// The observation seams belong to other families; the Lua runtime links them, so the harness
// answers "unavailable" exactly like the other Lua runtime tests.
GameIsPausedObservation ObserveGameIsPaused(uintptr_t, uintptr_t) {
    return GameIsPausedObservation::ThunkUnavailable;
}
GameLevelStageObservation ReadCurrentGameLevelStage(uintptr_t, std::uint32_t*) {
    return GameLevelStageObservation::GameUnreadable;
}
GameIsGreedModeObservation ObserveGameIsGreedMode(uintptr_t, uintptr_t) {
    return GameIsGreedModeObservation::MethodUnavailable;
}
GameIsAscentObservation ObserveLevelIsAscent(uintptr_t, uintptr_t) {
    return GameIsAscentObservation::MethodUnavailable;
}
GameItemPoolObservation ReadCurrentGameItemPool(uintptr_t, void**) {
    return GameItemPoolObservation::GameUnreadable;
}
GameRoomObservation ReadCurrentGameRoom(uintptr_t, void**) {
    return GameRoomObservation::RoomUnreadable;
}
GameRoomObservation ReadCurrentGameRoomType(uintptr_t, std::uint32_t*) {
    return GameRoomObservation::RoomUnreadable;
}
// --- Fake `KAGE::Graphics::Font` ------------------------------------------------------------
//
// The Hook installation publishes the real entry points; the harness replaces them so the Lua
// script can assert what the handlers do *around* the native call: the object the Runtime
// allocated is the object the native constructor wrote, `Load` receives the second-argument NULL,
// every measurement passes its own arguments through, and the release path runs the destructor
// exactly once.
namespace {

constexpr std::uint32_t kFakeFontMagic = 0x4B414745;  // 'KAGE'

int g_ctorCalls = 0;
int g_dtorCalls = 0;
std::uint32_t g_missingCharacter = 0xFFFFu;

// Only the first bytes of the 0x20050-byte block are written: the point of the fake is the
// lifecycle, not the layout.
struct FakeFont {
    std::uint32_t magic;
    bool loaded;
    std::uint32_t missingCharacter;
};

void FakeCtor(void* font) {
    if((reinterpret_cast<std::uintptr_t>(font)&15)!=0)std::abort();
    if((reinterpret_cast<std::uintptr_t>(font)&15)!=0)std::abort();
    ++g_ctorCalls;
    auto* fake = static_cast<FakeFont*>(font);
    fake->magic = kFakeFontMagic;
    fake->loaded = false;
    fake->missingCharacter = 0xFFFFu;
}

void FakeDestructor(void* font) {
    ++g_dtorCalls;
    auto* fake = static_cast<FakeFont*>(font);
    if (fake->magic != kFakeFontMagic) {
        std::exit(4);
    }
    fake->loaded = false;
    fake->magic = 0;
}

bool FakeLoad(void* font, const char* path, const char* extension) {
    auto* fake = static_cast<FakeFont*>(font);
    if (fake->magic != kFakeFontMagic) {
        return false;
    }
    // The handler must forward the caller's second argument verbatim: NULL when the Mod
    // passed one argument (which is what all 32 in-module call sites pass), and the given
    // string when it passed one -- External Item Descriptions calls `font:Load(path, "")`.
    // Anything else is a value the native Load would interpret, so the fake rejects it.
    if (extension != nullptr && extension[0] != '\0') {
        fake->loaded = false;
        return false;
    }
    if (path == nullptr || path[0] == '\0') {
        fake->loaded = false;
        return false;
    }
    fake->loaded = true;
    return true;
}

void FakeUnload(void* font) {
    auto* fake = static_cast<FakeFont*>(font);
    if (fake->magic != kFakeFontMagic) {
        std::exit(5);
    }
    fake->loaded = false;
}

bool FakeIsLoaded(const void* font) {
    return static_cast<const FakeFont*>(font)->loaded;
}

int FakeGetStringWidth(const void* font, const char* text) {
    if (static_cast<const FakeFont*>(font)->magic != kFakeFontMagic) {
        std::exit(6);
    }
    return static_cast<int>(text == nullptr ? 0 : std::strlen(text)) * 10;
}

// Deliberately different from the single-byte measurement, so a swapped binding is visible.
int FakeGetStringWidthUTF8(const void* font, const char* text) {
    if (static_cast<const FakeFont*>(font)->magic != kFakeFontMagic) {
        std::exit(7);
    }
    return static_cast<int>(text == nullptr ? 0 : std::strlen(text)) * 4 + 1;
}

std::uint16_t FakeGetLineHeight(const void*) { return 42; }
std::uint16_t FakeGetBaselineHeight(const void*) { return 31; }

int FakeGetCharacterWidth(const void* font, char character) {
    if (static_cast<const FakeFont*>(font)->magic != kFakeFontMagic) {
        std::exit(8);
    }
    return 5 + static_cast<int>(character);
}

void FakeSetMissingCharacter(void* font, std::uint16_t character) {
    g_missingCharacter = character;
    static_cast<FakeFont*>(font)->missingCharacter = character;
}

// Records what the native entry received, so the test can assert the whole marshalling path
// (string, two floats, the Runtime-owned colour block, box width and the centre flag).
struct FakeDrawStringCall {
    char text[64];
    float x;
    float y;
    float scaleX;
    float scaleY;
    float red;
    float green;
    float blue;
    float alpha;
    int boxWidth;
    int center;
    int calls;
};
FakeDrawStringCall g_drawString{};

void FakeFontDrawString(void* font, const char* text, float x, float y, const void* color,
                        int boxWidth, bool center) {
    if (font == nullptr || color == nullptr) {
        std::exit(21);
    }
    const auto* rgba = static_cast<const float*>(color);
    std::snprintf(g_drawString.text, sizeof(g_drawString.text), "%s", text == nullptr ? "" : text);
    g_drawString.x = x;
    g_drawString.y = y;
    g_drawString.red = rgba[0];
    g_drawString.green = rgba[1];
    g_drawString.blue = rgba[2];
    g_drawString.alpha = rgba[3];
    g_drawString.boxWidth = boxWidth;
    g_drawString.center = center ? 1 : 0;
    ++g_drawString.calls;
}

// 三个绘制变体各记一份：缩放走 s2/s3、UTF8 变体走各自的入口，参数其余部分与 `DrawString`
// 完全一致。harness 逐项断言，证明"多出来的两个 float 与入口选择"都被如实传递。
FakeDrawStringCall g_drawStringScaled{};
FakeDrawStringCall g_drawStringUTF8{};
FakeDrawStringCall g_drawStringScaledUTF8{};

void FakeFontDrawStringScaled(void* font, const char* text, float x, float y, float scaleX,
                              float scaleY, const void* color, int boxWidth, bool center) {
    if (font == nullptr || color == nullptr) {
        std::exit(22);
    }
    const auto* rgba = static_cast<const float*>(color);
    std::snprintf(g_drawStringScaled.text, sizeof(g_drawStringScaled.text), "%s",
                  text == nullptr ? "" : text);
    g_drawStringScaled.x = x;
    g_drawStringScaled.y = y;
    g_drawStringScaled.scaleX = scaleX;
    g_drawStringScaled.scaleY = scaleY;
    g_drawStringScaled.red = rgba[0];
    g_drawStringScaled.green = rgba[1];
    g_drawStringScaled.blue = rgba[2];
    g_drawStringScaled.alpha = rgba[3];
    g_drawStringScaled.boxWidth = boxWidth;
    g_drawStringScaled.center = center ? 1 : 0;
    ++g_drawStringScaled.calls;
}

// 每个入口各记一份：不复用 `DrawString` 的记录，否则后调的变体会把前者断言用的字段覆盖掉
// （这正是第一版测试写错、被 `text=Bye` 断言当场抓住的地方）。
void RecordCall(FakeDrawStringCall* record, void* font, const char* text, float x, float y,
                float scaleX, float scaleY, const void* color, int boxWidth, bool center,
                int exitCode) {
    if (font == nullptr || color == nullptr) {
        std::exit(exitCode);
    }
    const auto* rgba = static_cast<const float*>(color);
    std::snprintf(record->text, sizeof(record->text), "%s", text == nullptr ? "" : text);
    record->x = x;
    record->y = y;
    record->scaleX = scaleX;
    record->scaleY = scaleY;
    record->red = rgba[0];
    record->green = rgba[1];
    record->blue = rgba[2];
    record->alpha = rgba[3];
    record->boxWidth = boxWidth;
    record->center = center ? 1 : 0;
    ++record->calls;
}

void FakeFontDrawStringUTF8(void* font, const char* text, float x, float y, const void* color,
                            int boxWidth, bool center) {
    RecordCall(&g_drawStringUTF8, font, text, x, y, 0.0f, 0.0f, color, boxWidth, center, 23);
}

void FakeFontDrawStringScaledUTF8(void* font, const char* text, float x, float y, float scaleX,
                                  float scaleY, const void* color, int boxWidth, bool center) {
    RecordCall(&g_drawStringScaledUTF8, font, text, x, y, scaleX, scaleY, color, boxWidth, center,
               24);
}

void PublishFakeBindings() {
    LuaRuntime::LuaFontBindings bindings{};
    bindings.ctor = &FakeCtor;
    bindings.destructor_ = &FakeDestructor;
    bindings.load = &FakeLoad;
    bindings.unload = &FakeUnload;
    bindings.isLoaded = &FakeIsLoaded;
    bindings.getStringWidth = &FakeGetStringWidth;
    bindings.getStringWidthUTF8 = &FakeGetStringWidthUTF8;
    bindings.getLineHeight = &FakeGetLineHeight;
    bindings.getBaselineHeight = &FakeGetBaselineHeight;
    bindings.getCharacterWidth = &FakeGetCharacterWidth;
    bindings.setMissingCharacter = &FakeSetMissingCharacter;
    bindings.drawString = &FakeFontDrawString;
    bindings.drawStringScaled = &FakeFontDrawStringScaled;
    bindings.drawStringUTF8 = &FakeFontDrawStringUTF8;
    bindings.drawStringScaledUTF8 = &FakeFontDrawStringScaledUTF8;
    LuaRuntime::SetFontBindings(bindings);
}

[[maybe_unused]] const char* kUnavailableScript = R"lua(
local mod = RegisterMod('Font without bindings', 1)
mod:AddCallback(ModCallbacks.MC_POST_UPDATE, function()
  local ok, err = pcall(Font)
  if ok then error('Font() succeeded without native bindings') end
  if not string.find(tostring(err), 'unavailable', 1, true) then
    error('unexpected error: ' .. tostring(err))
  end
end)
)lua";

[[maybe_unused]] const char* kResourcesScript = R"lua(
local mod = RegisterMod('Font resources', 1)
mod:AddCallback(ModCallbacks.MC_POST_UPDATE, function()
  if type(Font) ~= 'function' then error('Font is not a global constructor') end

  -- 1) A Font can be constructed and its metatable carries every catalog method.
  local font = Font()
  if type(font) ~= 'userdata' then error('Font() did not return userdata') end
  local metatable = getmetatable(font)
  if type(metatable) ~= 'table' then error('Font has no metatable') end
  if type(metatable.__gc) ~= 'function' then error('Font metatable has no __gc') end
  if type(metatable.__index) ~= 'table' then error('Font metatable has no __index table') end
  for _, name in ipairs({'Load', 'Unload', 'IsLoaded', 'GetStringWidth', 'GetStringWidthUTF8',
                         'GetLineHeight', 'GetBaselineHeight', 'GetCharacterWidth',
                         'SetMissingCharacter'}) do
    if type(metatable.__index[name]) ~= 'function' then error('missing Font method ' .. name) end
    if type(font[name]) ~= 'function' then error('Font method is not reachable: ' .. name) end
  end

  -- 2) A fresh Font is not loaded and refuses every measurement instead of dispatching into
  --    fields that `Load` has not initialised yet.
  if font:IsLoaded() ~= false then error('a fresh Font reports IsLoaded') end
  for _, call in ipairs({
      function() return font:GetStringWidth('a') end,
      function() return font:GetStringWidthUTF8('a') end,
      function() return font:GetLineHeight() end,
      function() return font:GetBaselineHeight() end,
      function() return font:GetCharacterWidth(65) end,
    }) do
    if pcall(call) then error('an unloaded Font answered a measurement') end
  end

  -- 3) Load reports success and failure, and IsLoaded follows.
  if font:Load('font/terminus.fnt') ~= true then error('Load did not succeed') end
  -- Real Mods pass the native second argument as well: External Item Descriptions calls
  -- `font:Load(path, "")`. A handler that insisted on exactly one argument would reject it.
  if font:Load('font/terminus.fnt', '') ~= true then error('Load with an extension argument') end
  if pcall(function() font:Load('font/terminus.fnt', 7) end) then
    error('Load accepted a non-string extension')
  end
  if font:IsLoaded() ~= true then error('IsLoaded after Load') end
  if font:Load('') ~= false then error('Load accepted an empty path') end
  if font:IsLoaded() ~= false then error('IsLoaded after a failed Load') end
  if font:Load('font/terminus.fnt') ~= true then error('reload did not succeed') end

  -- 4) Every measurement passes its own arguments through, with a distinct value per entry point.
  if font:GetStringWidth('abcd') ~= 40 then error('GetStringWidth') end
  if font:GetStringWidth('') ~= 0 then error('GetStringWidth of the empty string') end
  if font:GetStringWidthUTF8('abcd') ~= 17 then error('GetStringWidthUTF8') end
  if font:GetLineHeight() ~= 42 then error('GetLineHeight') end
  if font:GetBaselineHeight() ~= 31 then error('GetBaselineHeight') end
  if font:GetCharacterWidth(65) ~= 70 then error('GetCharacterWidth') end

  -- 5) SetMissingCharacter validates its range and reaches the native setter.
  font:SetMissingCharacter(63)
  if pcall(function() font:SetMissingCharacter(-1) end) then error('negative missing character') end
  if pcall(function() font:SetMissingCharacter(70000) end) then error('missing character overflow') end
  if pcall(function() font:SetMissingCharacter(1.5) end) then error('fractional missing character') end
  if pcall(function() font:SetMissingCharacter() end) then error('missing character without an argument') end

  -- 6) Unload clears the loaded state and measurements are refused again.
  font:Unload()
  if font:IsLoaded() ~= false then error('IsLoaded after Unload') end
  if pcall(function() return font:GetStringWidth('a') end) then error('measured after Unload') end
  if pcall(function() return font:GetLineHeight() end) then error('line height after Unload') end

  -- 7) `__gc` is idempotent, and a released handle stays inert instead of calling through null.
  font:Load('font/terminus.fnt')
  metatable.__gc(font)
  metatable.__gc(font)
  if pcall(function() return font:GetStringWidth('a') end) then error('a released Font measured') end
  if pcall(function() font:Unload() end) then error('a released Font accepted Unload') end

  -- 8) The native `char` form of GetCharacterWidth sign-extends its argument, so only ASCII may
  --    reach it; non-ASCII needs the unicode overload this batch does not publish.
  local ascii = Font()
  if ascii:Load('font/terminus.fnt') ~= true then error('second Font did not load') end
  if pcall(function() return ascii:GetCharacterWidth(200) end) then error('non-ASCII width') end
  if pcall(function() return ascii:GetCharacterWidth(-1) end) then error('negative width') end
  if pcall(function() return ascii:GetCharacterWidth('A') end) then error('string width argument') end

  -- 9) Constructor and argument shape: `Font()` takes no argument, methods need their own object.
  if pcall(Font, 'font/terminus.fnt') then error('Font accepted an argument') end
  if pcall(function() return ascii:GetLineHeight(1) end) then error('GetLineHeight accepted an argument') end
  if pcall(function() return ascii:GetStringWidth({}) end) then error('GetStringWidth accepted a table') end
  if pcall(function() return ascii.Load({}, 'font/terminus.fnt') end) then error('method accepted a table') end
end)
)lua";
[[maybe_unused]] const char* kGcScript = R"lua(
local mod = RegisterMod('Font collection', 1)
mod:AddCallback(ModCallbacks.MC_POST_UPDATE, function()
  -- Three objects that simply go out of scope: each must be finalized exactly once.
  for _ = 1, 3 do
    local dropped = Font()
    dropped:Load('font/terminus.fnt')
    if dropped:GetStringWidth('ab') ~= 20 then error('dropped Font measurement') end
  end
  collectgarbage('collect')
  collectgarbage('collect')

  -- One object released by hand, twice: the second release must not run the destructor again, and
  -- neither may the collector's own finalizer run for that object.
  local released = Font()
  released:Load('font/terminus.fnt')
  local metatable = getmetatable(released)
  metatable.__gc(released)
  metatable.__gc(released)
  collectgarbage('collect')
end)
)lua";
[[maybe_unused]] const char* kCallbackScript = R"lua(
local mod = RegisterMod('Callback probe', 1)
-- POST_UPDATE 回调**故意报错**：模拟"在游戏未就绪时调用 Game 相关 API"的 Mod。
mod:AddCallback(ModCallbacks.MC_POST_UPDATE, function()
  error('update callback failed on purpose')
end)
-- POST_RENDER 只计数：它必须存活下来。
mod:AddCallback(ModCallbacks.MC_POST_RENDER, function()
  _G['CB_RENDER_RUNS'] = (_G['CB_RENDER_RUNS'] or 0) + 1
end)
)lua";
[[maybe_unused]] const char* kDrawScript = R"lua(
local mod = RegisterMod('Font draw', 1)
mod:AddCallback(ModCallbacks.MC_POST_UPDATE, function()
  local font = Font()
  if not font:Load('font/eid_default.fnt') then error('Load failed') end
  local color = KColor(0.25, 0.5, 0.75, 1.0)
  -- PC 文档与 EID 实际使用的都是长名 Red/Green/Blue/Alpha；短名 R/G/B/A 属于另一个类 Color，
  -- 只作为别名接受。这里两种拼法都读一遍，任一读不出来就报错。
  if math.abs(color.Red - 0.25) > 0.001 then error('KColor.Red') end
  if math.abs(color.Green - 0.5) > 0.001 then error('KColor.Green') end
  if math.abs(color.Blue - 0.75) > 0.001 then error('KColor.Blue') end
  if math.abs(color.Alpha - 1.0) > 0.001 then error('KColor.Alpha') end
  if math.abs(color.R - 0.25) > 0.001 or math.abs(color.A - 1.0) > 0.001 then
    error('KColor short-name aliases')
  end
  -- 字段可写（EID 的彩虹/闪烁/淡出就是 `color.Alpha = ...`）
  color.Alpha = 0.5
  if math.abs(color.Alpha - 0.5) > 0.001 then error('KColor.Alpha must be writable') end
  if pcall(function() color.Alpha = 'x' end) then error('KColor.Alpha accepted a string') end
  if pcall(function() color.Nope = 1 end) then error('KColor accepted an unknown field') end
  -- 文档化的类常量，且每次读取都是新值（改常量不能影响别人）
  local white = KColor.White
  if math.abs(white.Red - 1) > 0.001 or math.abs(white.Alpha - 1) > 0.001 then
    error('KColor.White')
  end
  white.Alpha = 0
  if math.abs(KColor.White.Alpha - 1) > 0.001 then error('KColor.White must not be mutated') end
  local transparent = KColor.Transparent
  if math.abs(transparent.Alpha) > 0.001 then error('KColor.Transparent') end
  color.Alpha = 1.0
  -- 默认参数路径：BoxWidth=0、Center=false
  font:DrawString('Hi', 10.5, 20.25, color)
  -- 显式参数路径
  font:DrawString('Bye', 1.0, 2.0, KColor(1, 0, 0), 40, true)
  -- 三个绘制变体：缩放走 s2/s3，UTF8 走各自入口
  font:DrawStringScaled('Scaled', 3.0, 4.0, 0.5, 2.0, KColor(0, 0, 1), 7, false)
  font:DrawStringUTF8('Utf8', 5.0, 6.0, KColor(0, 1, 0))
  font:DrawStringScaledUTF8('ScaledUtf8', 7.0, 8.0, 1.5, 1.5, KColor(1, 1, 1), 0, true)
  -- 未 Load 的字体不得绘制
  local fresh = Font()
  local ok = pcall(function() fresh:DrawString('x', 0, 0, color) end)
  if ok then error('DrawString succeeded on an unloaded Font') end
  font:Unload()
end)
)lua";

} // namespace


#include "interfaces/lua/font_api.hpp"
#include <chrono>
extern "C" {
#include <lualib.h>
#include <lauxlib.h>
}
struct AllocationTest { lua_Alloc original; void* opaque; int rejected=0; };
void* DenyNativeBlock(void* context,void* ptr,size_t oldSize,size_t newSize) {
    auto* test=static_cast<AllocationTest*>(context);
    if(newSize>100000 && newSize>oldSize) { ++test->rejected; return nullptr; }
    return test->original(test->opaque,ptr,oldSize,newSize);
}
int main() {
PublishFakeBindings();
// 内存耗尽必须经Lua标准错误返回，并发生紧急回收后的重试，不能泄露原生对象。
auto* allocationState=luaL_newstate();
AllocationTest allocation{};
allocation.original=lua_getallocf(allocationState,&allocation.opaque);
lua_pushcfunction(allocationState,isaac::runtime::CreateFontHandle);
lua_setallocf(allocationState,&DenyNativeBlock,&allocation);
auto status=lua_pcall(allocationState,0,1,0);
lua_setallocf(allocationState,allocation.original,allocation.opaque);
if(status!=LUA_ERRMEM || allocation.rejected<2 || g_ctorCalls!=0 || isaac::runtime::FontStorageLiveBlocks()!=0)return 6;
lua_close(allocationState);

const char* script=R"diag(
Pinned=string.rep('P',8*1024*1024)
collectgarbage('collect')
local before=collectgarbage('count')
Held={}
for i=1,64 do Held[i]=Font() end
print('FONT64_LUA_ACCOUNTED_KIB='..(collectgarbage('count')-before))
local mod=RegisterMod('Font storm observation',1)
mod:AddCallback(ModCallbacks.MC_POST_UPDATE,function() local tmp=Font() end)
)diag";

if(LuaRuntime::InitializeFromBuffer(script,std::strlen(script),"@font-debt.lua")!=LuaRuntime::LuaInitResult::Success)return 2;
std::printf("HELD ctor=%d dtor=%d live=%u lua_bytes=%llu\n",g_ctorCalls,g_dtorCalls,isaac::runtime::FontStorageLiveBlocks(),static_cast<unsigned long long>(LuaRuntime::LuaStateMemoryBytes()));
for(unsigned frame=2;frame<40;frame+=2) {
 auto r=LuaRuntime::NudgeLuaGcIfFontBlocksHigh(frame,isaac::runtime::FontStorageLiveBlocks());
 std::printf("BASELINE frame=%u nudge=%u live=%u\n",frame,r,isaac::runtime::FontStorageLiveBlocks());
}
unsigned productive=0;
auto stormStart=std::chrono::steady_clock::now();
for(unsigned i=0;i<640;++i) {
 LuaRuntime::DispatchPostUpdate();
 if(LuaRuntime::TakeCallbackError())return 3;
 productive+=LuaRuntime::NudgeLuaGcIfFontBlocksHigh(100+i,isaac::runtime::FontStorageLiveBlocks());
}
std::printf("STORM_MICROS=%lld\n",static_cast<long long>(std::chrono::duration_cast<std::chrono::microseconds>(std::chrono::steady_clock::now()-stormStart).count()));
std::printf("AFTER_STORM ctor=%d dtor=%d live=%u nudges=%u lua_bytes=%llu raw_font_bytes=%llu\n",g_ctorCalls,g_dtorCalls,isaac::runtime::FontStorageLiveBlocks(),productive,static_cast<unsigned long long>(LuaRuntime::LuaStateMemoryBytes()),static_cast<unsigned long long>(isaac::runtime::FontStorageLiveBlocks())*(0x20050+sizeof(void*)+15));
if(g_dtorCalls<630 || isaac::runtime::FontStorageLiveBlocks()>74)return 4;
return 0;
}
