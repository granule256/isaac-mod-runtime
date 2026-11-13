"""Fancy Menu consumes genuine Sprite graphics prerequisites, not placeholders."""
import subprocess
import tempfile
import unittest
from pathlib import Path

from . import test_support

RUNTIME = Path(__file__).resolve().parents[1]
SOURCE = RUNTIME / "source"

DRIVER = r'''
#include "interfaces/lua/class_metadata.hpp"
#include "interfaces/lua/color_api.hpp"
#include "interfaces/lua/repentogon_callbacks.hpp"
#include "interfaces/lua/repentogon_environment.hpp"
#include "interfaces/lua/repentogon_sprite_api.hpp"
#include "interfaces/lua/sprite_api.hpp"
#include "interfaces/lua/vector_api.hpp"
#include "infrastructure/memory/engine_field_access.hpp"
#include "lua_runtime.hpp"
#include "lua_object_handles.hpp"
#include "runtime_constants.hpp"
extern "C" {
#include <lauxlib.h>
#include <lualib.h>
}

#include <array>
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <string>
#include <thread>

using namespace isaac::runtime;
using namespace isaac::runtime::repentogon;

static bool ready = true;
static bool installed = true;
static bool alive = true;
static bool Ready() noexcept { return ready; }
static bool Install() noexcept { return installed; }
static int InitializeSpriteViews(lua_State* state) {
    return RegisterRepentogonSpriteViews(state);
}
static constexpr RepentogonBatch kSpriteBatch{
    "fancy-graphics", nullptr, 0, nullptr, 0, nullptr, 0,
    InitializeSpriteViews, nullptr, Ready};
static constexpr RepentogonCatalog kSpriteCatalog{&kSpriteBatch, 1, nullptr};

alignas(16) static std::array<unsigned char, 0x400> anm2{};
alignas(16) static std::array<unsigned char, 0x150 * 2> animationSlots{};
static unsigned char* const animation = animationSlots.data();
alignas(16) static std::array<unsigned char, 0x18> layer{};
alignas(16) static std::array<unsigned char, 0xd8> frames{};
alignas(16) static std::array<unsigned char, 0xb0> layerState{};
alignas(16) static std::array<unsigned char, 0x38> layerData{};
alignas(8) static std::array<std::int32_t, 1> layerPositions{};
static std::array<char, 192> layerPathText{};
static std::array<char, 192> layerDefaultPathText{};
static std::array<char, 192> assignedPathText{};

static unsigned loadCalls{};
static unsigned loadGraphicsCalls{};
static unsigned replaceCalls{};
static unsigned renderCalls{};
static unsigned setLayerFrameCalls{};
static unsigned layerLookups{};
static int lastLayer{};
static int lastFrame{};
static bool lastLoadGraphics{};

template <class T, class Bytes>
static void Put(Bytes& bytes, std::size_t offset, T value) {
    assert(offset + sizeof(value) <= bytes.size());
    std::memcpy(bytes.data() + offset, &value, sizeof(value));
}
template <class T>
static void Put(unsigned char* bytes, std::size_t offset, T value) {
    assert(bytes != nullptr);
    std::memcpy(bytes + offset, &value, sizeof(value));
}

static bool SpriteAlive(std::uintptr_t address) noexcept {
    return alive && address == reinterpret_cast<std::uintptr_t>(anm2.data());
}

static void SetEngineString(std::uintptr_t object, const char* text,
                            std::array<char, 192>& storage) {
    const std::size_t length = std::strlen(text);
    assert(length < storage.size());
    unsigned char* bytes = static_cast<unsigned char*>(engine_memory::AsObject(object));
    std::memset(bytes, 0, 24);
    if (length <= 22) {
        bytes[0] = static_cast<unsigned char>(length << 1);
        std::memcpy(bytes + 1, text, length);
        return;
    }
    bytes[0] = 1;
    const std::uint64_t nativeLength = length;
    std::memcpy(bytes + 8, &nativeLength, sizeof(nativeLength));
    std::memcpy(storage.data(), text, length + 1);
    const std::uintptr_t data =
        reinterpret_cast<std::uintptr_t>(storage.data());
    std::memcpy(bytes + 0x10, &data, sizeof(data));
}

static bool ReadEngineString(std::uintptr_t object, std::string& out) {
    const auto* bytes = static_cast<const unsigned char*>(
        engine_memory::AsObject(object));
    if ((bytes[0] & 1U) == 0) {
        const std::size_t length = bytes[0] >> 1;
        out.assign(reinterpret_cast<const char*>(bytes + 1), length);
        return true;
    }
    std::uint64_t length{};
    std::uintptr_t data{};
    std::memcpy(&length, bytes + 8, sizeof(length));
    std::memcpy(&data, bytes + 0x10, sizeof(data));
    if (data == 0) return false;
    out.assign(static_cast<const char*>(engine_memory::AsObject(data)),
               static_cast<std::size_t>(length));
    return true;
}

static void FakeCtor(void* sprite) {
    std::memset(sprite, 0, kSpriteObjectSize);
    const std::uint64_t magic{0x48534E4154524950ULL};
    std::memcpy(sprite, &magic, sizeof(magic));
}

static void FakeDtor(void*) {}

void* FakeAssign(void* object, const char* text) {
    SetEngineString(engine_memory::AddressOf(object), text, assignedPathText);
    return object;
}

void FakeDelete(void*) {}

void FakeLoad(void* sprite, const void* nativeString, bool loadGraphics) {
    ++loadCalls;
    lastLoadGraphics = loadGraphics;
    std::string path;
    assert(ReadEngineString(engine_memory::AddressOf(nativeString), path));
    assert(path == "gfx/ui/fancy menu/character.anm2");
    const auto flag = static_cast<std::uint8_t*>(sprite) + kSpriteLoadedFlagOffset;
    *flag = 1;
}

void FakeLoadGraphics(void*) {
    ++loadGraphicsCalls;
}

void FakeReplaceSpritesheet(void* sprite, int layerIndex, const void* nativeString) {
    assert(reinterpret_cast<std::uintptr_t>(sprite) != 0);
    assert(nativeString != nullptr);
    ++replaceCalls;
    lastLayer = layerIndex;
}

void FakeRender(void*, const void*, const void*, const void*) {
    ++renderCalls;
}

void FakeSetLayerFrame(void*, int layerIndex, int frame) {
    ++setLayerFrameCalls;
    lastLayer = layerIndex;
    lastFrame = frame;
}

static void* FakeGetLayerInt(void*, int id) noexcept {
    ++layerLookups;
    return id == 0 ? layerState.data() : nullptr;
}

static const void* FakeGetAnimationData(const void*, const char*) noexcept {
    return nullptr;
}

static void* FakeGetLayerName(void*, const char*) noexcept {
    return nullptr;
}

static const void* FakeGetNullFrame(const void*, const char*) noexcept {
    return nullptr;
}

static int MakeVector(lua_State* state) {
    auto* value = static_cast<LuaRuntime::VectorHandle*>(
        lua_newuserdata(state, sizeof(LuaRuntime::VectorHandle)));
    value->x = static_cast<float>(luaL_checknumber(state, 1));
    value->y = static_cast<float>(luaL_checknumber(state, 2));
    luaL_getmetatable(state, LuaRuntime::kVectorMetatable);
    lua_setmetatable(state, -2);
    return 1;
}

static int MakeSprite(lua_State* state) {
    PushCallbackSpriteHandle(
        state, reinterpret_cast<std::uintptr_t>(anm2.data()), LUA_NOREF);
    return 1;
}

static int ShortView(lua_State* state) {
    const char* metatable = luaL_checkstring(state, 1);
    static_cast<void>(lua_newuserdata(state, 1));
    luaL_getmetatable(state, metatable);
    lua_setmetatable(state, -2);
    return 1;
}

static int LayerLookupCount(lua_State* state) {
    lua_pushinteger(state, layerLookups);
    return 1;
}

static int F32(lua_State* state) {
    const auto offset = static_cast<std::size_t>(luaL_checkinteger(state, 1));
    assert(offset + sizeof(float) <= layerState.size());
    float value{};
    std::memcpy(&value, layerState.data() + offset, sizeof(value));
    lua_pushnumber(state, value);
    return 1;
}

static void InitFixture() {
    Put(anm2, 0x38, reinterpret_cast<std::uintptr_t>(animation));
    Put(anm2, 0x40, reinterpret_cast<std::uintptr_t>(layerPositions.data()));
    Put(anm2, 0x98, reinterpret_cast<std::uintptr_t>(animationSlots.data()));
    Put(anm2, 0xa0, std::int32_t{1});
    Put(anm2, 0xa8, reinterpret_cast<std::uintptr_t>(layerState.data()));
    Put(anm2, 0xb0, std::int32_t{1});

    Put(animation, 0x18, reinterpret_cast<std::uintptr_t>(layer.data()));
    Put(animation, 0x20, std::int32_t{1});
    for (std::size_t i = 0; i < 64; ++i) {
        Put(animation, 0x4c + i * sizeof(std::int32_t), -1);
    }
    Put(animation, 0x4c, std::int32_t{0});

    Put(layer, 0x08, reinterpret_cast<std::uintptr_t>(frames.data()));
    Put(layer, 0x10, std::int32_t{1});
    Put(frames, 0x2c, std::uint8_t{1});
    Put(frames, 0x10, 3.5F);
    Put(frames, 0x14, -4.25F);
    Put(frames, 0x30, 0.25F);
    Put(frames, 0x34, 0.5F);
    Put(frames, 0x38, 0.75F);
    Put(frames, 0x3c, 1.0F);
    Put(frames, 0x40, 0.0F);
    Put(frames, 0x44, 0.0F);
    Put(frames, 0x48, 0.0F);
    Put(frames, 0x4c, 0.0F);
    Put(frames, 0x64, std::int32_t{0});
    Put(frames, 0x68, std::int32_t{1});

    Put(layerData, 0x08, std::uint32_t{1});
    SetEngineString(reinterpret_cast<std::uintptr_t>(layerData.data()) + 0x20,
                    "gfx/ui/fancy menu/characters/Isaac_default.png",
                    layerDefaultPathText);
    Put(layerState, 0x00, reinterpret_cast<std::uintptr_t>(layerData.data()));
    SetEngineString(reinterpret_cast<std::uintptr_t>(layerState.data()) + 0x10,
                    "gfx/ui/fancy menu/characters/Isaac.png", layerPathText);
    Put(layerState, 0x3c, 1.0F);
    Put(layerState, 0x40, 1.0F);
    Put(layerState, 0x44, 37.0F);
    Put(layerState, 0x48, 12.0F);
    Put(layerState, 0x4c, 34.0F);
}

static void OpenLibraries(lua_State* state) {
    const struct {
        const char* name;
        lua_CFunction open;
    } libraries[] = {
        {"_G", luaopen_base},
        {LUA_TABLIBNAME, luaopen_table},
        {LUA_STRLIBNAME, luaopen_string},
        {LUA_MATHLIBNAME, luaopen_math},
    };
    for (const auto& library : libraries) {
        luaL_requiref(state, library.name, library.open, 1);
        lua_pop(state, 1);
    }
}

static void InstallSpriteAndViews(lua_State* state) {
    luaL_newmetatable(state, LuaRuntime::kSpriteMetatable);
    lua_pushcfunction(state, DestroySpriteHandle);
    lua_setfield(state, -2, "__gc");
    lua_pushcfunction(state, SpriteIndex);
    lua_setfield(state, -2, "__index");
    lua_pushcfunction(state, SpriteNewIndex);
    lua_setfield(state, -2, "__newindex");
    lua_newtable(state);
    static_cast<void>(AttachSpriteMethods(state));
    lua_setfield(state, -2, "__methods");
    lua_pop(state, 1);

    // This is the production base registration shape before REPENTOGON starts.
    lua_pushcfunction(state, CreateSpriteHandle);
    lua_setglobal(state, "Sprite");

    BeginRepentogonEnvironment(state, true, kSpriteCatalog);
    CompleteRepentogonEnvironment(state);
    assert(RepentogonEnvironmentActive());

    lua_getglobal(state, "Sprite");
    lua_pushcfunction(state, RepentogonSpriteGetLayer);
    lua_setfield(state, -2, "GetLayer");
    lua_pushcfunction(state, RepentogonSpriteGetLayerFrameData);
    lua_setfield(state, -2, "GetLayerFrameData");
    lua_pop(state, 1);

    luaL_getmetatable(state, "IsaacRuntime.LayerState");
    lua_getfield(state, -1, "__methods");
    lua_pushcfunction(state, RepentogonLayerStateSetSize);
    lua_setfield(state, -2, "SetSize");
    lua_pushcfunction(state, RepentogonLayerStateGetSpritesheetPath);
    lua_setfield(state, -2, "GetSpritesheetPath");
    lua_pushcfunction(state, RepentogonLayerStateGetDefaultSpritesheetPath);
    lua_setfield(state, -2, "GetDefaultSpritesheetPath");
    lua_pushcfunction(state, RepentogonLayerStateSetCropOffset);
    lua_setfield(state, -2, "SetCropOffset");
    lua_pop(state, 2);

    luaL_getmetatable(state, "IsaacRuntime.AnimationFrame");
    lua_getfield(state, -1, "__methods");
    lua_pushcfunction(state, RepentogonAnimationFrameIsVisible);
    lua_setfield(state, -2, "IsVisible");
    lua_pushcfunction(state, RepentogonAnimationFrameGetColor);
    lua_setfield(state, -2, "GetColor");
    lua_pushcfunction(state, RepentogonAnimationFrameGetPos);
    lua_setfield(state, -2, "GetPos");
    lua_pop(state, 2);
}

static void InstallSupportTypes(lua_State* state) {
    luaL_newmetatable(state, LuaRuntime::kColorMetatable);
    lua_pushcfunction(state, ColorIndex);
    lua_setfield(state, -2, "__index");
    lua_pushcfunction(state, ColorNewIndex);
    lua_setfield(state, -2, "__newindex");
    lua_pop(state, 1);

    RegisterVectorReferenceMetatable(state);
    luaL_newmetatable(state, LuaRuntime::kVectorMetatable);
    lua_pushcfunction(state, VectorIndex);
    lua_setfield(state, -2, "__index");
    lua_pushcfunction(state, VectorNewIndex);
    lua_setfield(state, -2, "__newindex");
    lua_pop(state, 1);
}

int main() {
    InitFixture();
    SetRepentogonSpriteNativeTestBindings({
        &FakeGetAnimationData, &FakeGetLayerInt, &FakeGetLayerName, &FakeGetNullFrame});
    LuaRuntime::ObserveGameThread();
    const NativePort port{Ready, Install, SpriteAlive};
    SetNativePort(&port);

    LuaRuntime::LuaSpriteBindings bindings{};
    bindings.ctor = &FakeCtor;
    bindings.destructor_ = &FakeDtor;
    bindings.load = &FakeLoad;
    bindings.loadGraphics = &FakeLoadGraphics;
    bindings.replaceSpritesheet = &FakeReplaceSpritesheet;
    bindings.libcxxStringAssign = &FakeAssign;
    bindings.gameOperatorDelete = &FakeDelete;
    bindings.render = &FakeRender;
    bindings.setLayerFrame = &FakeSetLayerFrame;
    LuaRuntime::SetSpriteBindings(bindings);

    auto* state = luaL_newstate();
    assert(state);
    OpenLibraries(state);
    InstallSupportTypes(state);
    InstallSpriteAndViews(state);

    lua_pushcfunction(state, MakeSprite);
    lua_setglobal(state, "_newSprite");
    lua_pushcfunction(state, MakeVector);
    lua_setglobal(state, "_vector");
    lua_pushcfunction(state, ShortView);
    lua_setglobal(state, "_short");
    lua_pushcfunction(state, LayerLookupCount);
    lua_setglobal(state, "_layerLookupCount");
    lua_pushcfunction(state, F32);
    lua_setglobal(state, "_f32");

    const char* script = R"lua(
assert(type(Sprite) == 'table', 'Sprite must be a writable class table')
assert(type(Sprite.Render) == 'function')
assert(type(Sprite.SetLayerFrame) == 'function')

local oldRender = Sprite.Render
local renderSeen = 0
function Sprite:Render(position, topLeft, bottomRight)
    renderSeen = renderSeen + 1
    return oldRender(self, position, topLeft, bottomRight)
end

local sprite = _newSprite()
assert(sprite:Render(_vector(1, 2)) == nil)
assert(renderSeen == 1)

local oldSetLayerFrame = Sprite.SetLayerFrame
local layerFrameSeen = 0
function Sprite:SetLayerFrame(layerId, frame)
    layerFrameSeen = layerFrameSeen + 1
    return oldSetLayerFrame(self, layerId, frame)
end
sprite:SetLayerFrame(4, 7)
assert(layerFrameSeen == 1)

local layer = sprite:GetLayer(0)
assert(type(layer) == 'userdata')
assert(layer:GetSpritesheetPath() == 'gfx/ui/fancy menu/characters/Isaac.png')
assert(layer:GetDefaultSpritesheetPath() == 'gfx/ui/fancy menu/characters/Isaac_default.png')
layer:SetSize(_vector(2.5, 4.5))
layer:SetCropOffset(_vector(7.25, -8.5))
assert(_f32(0x94) == 7.25 and _f32(0x98) == -8.5)

local frame = sprite:GetLayerFrameData(0)
assert(frame:IsVisible() == true)
local framePos = frame:GetPos()
assert(framePos.X == 3.5 and framePos.Y == -4.25)
assert(sprite:GetLayerFrameData(0):GetPos().X == 3.5)
local color = frame:GetColor()
assert(color.R == 0.25 and color.G == 0.5 and color.B == 0.75 and color.A == 1.0)
assert(color.RO == 0 and color.GO == 0 and color.BO == 0)

local lookups = _layerLookupCount()
for i = 1, 16 do
    assert(layer:GetSpritesheetPath() == 'gfx/ui/fancy menu/characters/Isaac.png')
    assert(layer:GetDefaultSpritesheetPath() == 'gfx/ui/fancy menu/characters/Isaac_default.png')
    layer:SetSize(_vector(i, -i))
    layer:SetCropOffset(_vector(i, -i))
    assert(frame:IsVisible())
    assert(frame:GetPos().X == 3.5)
    assert(frame:GetColor().R == 0.25)
end
assert(_layerLookupCount() == lookups)

assert(not pcall(layer.GetSpritesheetPath, _short('IsaacRuntime.LayerState')))
assert(not pcall(layer.GetDefaultSpritesheetPath, _short('IsaacRuntime.LayerState')))
assert(not pcall(layer.SetSize, _short('IsaacRuntime.LayerState'), _vector(1, 1)))
assert(not pcall(layer.SetCropOffset, _short('IsaacRuntime.LayerState'), _vector(1, 1)))
assert(not pcall(frame.IsVisible, _short('IsaacRuntime.AnimationFrame')))
assert(not pcall(frame.GetPos, _short('IsaacRuntime.AnimationFrame')))
assert(not pcall(frame.GetColor, _short('IsaacRuntime.AnimationFrame')))

local loaded, ok = Sprite('gfx/ui/fancy menu/character.anm2', true)
assert(type(loaded) == 'userdata')
assert(ok == true)
assert(getmetatable(loaded) == getmetatable(sprite))

loaded:ReplaceSpritesheet(0, 'gfx/ui/fancy menu/portrait.png')
loaded:ReplaceSpritesheet(1, 'gfx/ui/fancy menu/text.png', true)
return true
)lua";

    if (luaL_loadbuffer(state, script, std::strlen(script), "@fancy-graphics.lua") != LUA_OK ||
        lua_pcall(state, 0, 0, 0) != LUA_OK) {
        std::fprintf(stderr, "%s\n", lua_tostring(state, -1));
        return 1;
    }

    if (loadCalls != 1 || !lastLoadGraphics) return 2;
    if (replaceCalls != 2 || lastLayer != 1) return 3;
    if (loadGraphicsCalls != 1) return 4;
    if (renderCalls != 1) return 5;
    if (setLayerFrameCalls != 1 || lastFrame != 7) return 6;

    const auto* stateBytes = layerState.data();
    float sizeX{};
    float sizeY{};
    float rotation{};
    float posX{};
    float posY{};
    float cropX{};
    float cropY{};
    std::memcpy(&sizeX, stateBytes + 0x3c, sizeof(sizeX));
    std::memcpy(&sizeY, stateBytes + 0x40, sizeof(sizeY));
    std::memcpy(&rotation, stateBytes + 0x44, sizeof(rotation));
    std::memcpy(&posX, stateBytes + 0x48, sizeof(posX));
    std::memcpy(&posY, stateBytes + 0x4c, sizeof(posY));
    std::memcpy(&cropX, stateBytes + 0x94, sizeof(cropX));
    std::memcpy(&cropY, stateBytes + 0x98, sizeof(cropY));
    assert(sizeX == 16.0F && sizeY == -16.0F);
    assert(rotation == 37.0F && posX == 12.0F && posY == 34.0F);
    assert(cropX == 16.0F && cropY == -16.0F);

    EndRepentogonEnvironment(state);
    alive = false;
    lua_close(state);
    SetNativePort(nullptr);
    SetRepentogonSpriteNativeTestBindings({});
}
'''


class FancyGraphicsPrerequisiteTests(unittest.TestCase):
    def test_sprite_class_views_constructor_and_load_graphics(self):
        with tempfile.TemporaryDirectory(prefix="fancy-graphics-") as folder:
            binary = test_support.build_lua_harness(
                source_root=SOURCE,
                workdir=Path(folder),
                harness_source=DRIVER,
            )
            result = subprocess.run([str(binary)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
