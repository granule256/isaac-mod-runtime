"""REPENTOGON sprite/animation views use live native ownership and fields."""
import subprocess
import tempfile
import unittest
from pathlib import Path

from . import test_support

RUNTIME = Path(__file__).resolve().parents[1]
SOURCE = RUNTIME / "source"
SPRITE_API = RUNTIME / "src/interfaces/lua/repentogon_sprite_api.cpp"

DRIVER = r'''
#include "interfaces/lua/repentogon_callbacks.hpp"
#include "interfaces/lua/repentogon_environment.hpp"
#include "interfaces/lua/repentogon_sprite_api.hpp"
#include "interfaces/lua/sprite_api.hpp"
#include "interfaces/lua/class_metadata.hpp"
#include "interfaces/lua/vector_api.hpp"
#include "lua_runtime.hpp"
#include "lua_object_handles.hpp"
#include "runtime_constants.hpp"
extern "C" {
#include <lauxlib.h>
#include <lualib.h>
}
#include <array>
#include <cassert>
#include <cstdio>
#include <cstring>
#include <iterator>
#include <thread>
#include <utility>

using namespace isaac::runtime;
using namespace isaac::runtime::repentogon;

static bool ready = true;
static bool installed = true;
static bool alive = true;
static bool Ready() noexcept { return ready; }
static bool Install() noexcept { return installed; }

alignas(16) static std::array<unsigned char, 0x400> anm2{};
alignas(16) static std::array<unsigned char, 0x150 * 3> animationSlots{};
alignas(16) static std::array<unsigned char, 0x150> reloadStorage{};
static unsigned char* const data = animationSlots.data();
static unsigned char* const currentData = animationSlots.data() + 0x150;
static unsigned char* const reloadData = animationSlots.data() + 0x2a0;
alignas(16) static std::array<unsigned char, 0x30> dataLayers{};
alignas(16) static std::array<unsigned char, 0x30> currentLayers{};
alignas(16) static std::array<unsigned char, 0x18> currentNullLayers{};
alignas(16) static std::array<unsigned char, 0x30> alternateLayers{};
alignas(16) static std::array<unsigned char, 0x18> alternateNullLayers{};
alignas(16) static std::array<unsigned char, 0xd8> dataFrames{};
alignas(16) static std::array<unsigned char, 0xd8> currentFrames{};
alignas(16) static std::array<unsigned char, 0xd8> alternateFrames{};
alignas(16) static std::array<unsigned char, 0x160> layerStates{};
alignas(16) static std::array<unsigned char, 0x160> reloadLayerStates{};
alignas(16) static std::array<unsigned char, 0x54> nullFrame{};
alignas(16) static std::array<unsigned char, 0x54> reloadNullFrame{};

static void* gNamedData = data;
static void* gNullFrame = nullFrame.data();
static std::uintptr_t gLayerStateBase = reinterpret_cast<std::uintptr_t>(layerStates.data());
static unsigned animationLookups{};
static unsigned layerNameLookups{};
static unsigned nullFrameLookups{};
// Literal pinned-NRO offsets are intentionally independent of production constants.
static constexpr std::size_t kFrameStride = 0x6c;
static constexpr std::size_t kLayerStride = 0x18;
static constexpr std::size_t kLayerStateStride = 0xb0;

static bool SpriteAlive(std::uintptr_t address) noexcept {
    return alive && address == reinterpret_cast<std::uintptr_t>(anm2.data());
}
template<class T, std::size_t N>
static void Put(std::array<unsigned char, N>& bytes, std::size_t offset, T value) {
    assert(offset + sizeof(value) <= bytes.size());
    std::memcpy(bytes.data() + offset, &value, sizeof(value));
}
template<class T>
static void Put(unsigned char* bytes, std::size_t offset, T value) {
    assert(bytes != nullptr && offset + sizeof(value) <= 0x150);
    std::memcpy(bytes + offset, &value, sizeof(value));
}
template<class T, std::size_t N>
static T At(const std::array<unsigned char, N>& bytes, std::size_t offset) {
    assert(offset + sizeof(T) <= bytes.size());
    T value{};
    std::memcpy(&value, bytes.data() + offset, sizeof(value));
    return value;
}

static constexpr RepentogonApiBinding Api(std::uint32_t sequence, const char* owner,
                                          const char* name, lua_CFunction handler) {
    return {{0x0DFF0000U | sequence, ApiDomain::Sprite, owner, name, {}, 0,
             ThreadAffinity::ManagedCallback, ApiMaturity::Experimental},
            handler};
}

static constexpr RepentogonApiBinding kSpriteApis[] = {
    Api(0x001, "Sprite", "GetLayerFrameData", RepentogonSpriteGetLayerFrameData),
    Api(0x002, "Sprite", "GetNullFrame", RepentogonSpriteGetNullFrame),
    Api(0x003, "Sprite", "GetCurrentAnimationData", RepentogonSpriteGetCurrentAnimationData),
    Api(0x004, "Sprite", "GetAnimationData", RepentogonSpriteGetAnimationData),
    Api(0x005, "Sprite", "GetLayer", RepentogonSpriteGetLayer),
    Api(0x006, "AnimationFrame", "GetStartFrame", RepentogonAnimationFrameGetStartFrame),
    Api(0x007, "AnimationFrame", "GetPivot", RepentogonAnimationFrameGetPivot),
    Api(0x008, "AnimationFrame", "GetWidth", RepentogonAnimationFrameGetWidth),
    Api(0x009, "NullFrame", "GetPos", RepentogonNullFrameGetPos),
    Api(0x00A, "NullFrame", "GetScale", RepentogonNullFrameGetScale),
    Api(0x00B, "AnimationData", "GetLength", RepentogonAnimationDataGetLength),
    Api(0x00C, "AnimationData", "GetLayer", RepentogonAnimationDataGetLayer),
    Api(0x00D, "AnimationLayer", "GetFrame", RepentogonAnimationLayerGetFrame),
    Api(0x00E, "LayerState", "SetVisible", RepentogonLayerStateSetVisible),
    Api(0x00F, "LayerState", "SetPos", RepentogonLayerStateSetPos),
    Api(0x010, "LayerState", "SetColor", RepentogonLayerStateSetColor),
    Api(0x011, "LayerState", "GetBlendMode", RepentogonLayerStateGetBlendMode),
    Api(0x012, "BlendMode", "Flag1", RepentogonBlendModeGetFlag1),
    Api(0x013, "BlendMode", "Flag2", RepentogonBlendModeGetFlag2),
    Api(0x014, "BlendMode", "Flag3", RepentogonBlendModeGetFlag3),
    Api(0x015, "BlendMode", "Flag4", RepentogonBlendModeGetFlag4),
};

static constexpr RepentogonBatch kSpriteBatch{
    "sprite-views", kSpriteApis, std::size(kSpriteApis), nullptr, 0, nullptr, 0,
    RegisterRepentogonSpriteViews, nullptr, Ready,
};
static constexpr RepentogonCatalog kSpriteCatalog{&kSpriteBatch, 1, nullptr};

static void InitLayerState(std::array<unsigned char, 0x160>& bytes, std::size_t base,
                           float visibleProbe) {
    Put(bytes, base + 0x00,
        reinterpret_cast<std::uintptr_t>(bytes.data()) + 0x1000 + base);
    Put(bytes, base + 0x47, std::uint8_t{0xa5});
    Put(bytes, base + 0x7c, std::uint8_t{1});
    Put(bytes, base + 0x7b, std::uint8_t{0xa3});
    Put(bytes, base + 0x7d, std::uint8_t{0xa4});
    Put(bytes, base + 0x48, 1.25F);
    Put(bytes, base + 0x4c, -2.5F);
    Put(bytes, base + 0x50, 0.25F);
    Put(bytes, base + 0x54, 0.5F);
    Put(bytes, base + 0x58, 0.75F);
    Put(bytes, base + 0x5c, 1.0F);
    Put(bytes, base + 0x80 + 0x00, std::uint32_t{1});
    Put(bytes, base + 0x80 + 0x04, std::uint32_t{7});
    Put(bytes, base + 0x80 + 0x08, std::uint32_t{2});
    Put(bytes, base + 0x80 + 0x0c, std::uint32_t{6});
    Put(bytes, base + 0x90, std::uint32_t{0x5a});
    static_cast<void>(visibleProbe);
}

static void InitFixture() {
    for (auto* animation : {data, currentData, reloadData}) {
        for (std::size_t i = 0; i < 64; ++i) {
            Put(animation, 0x4c + i * sizeof(std::int32_t), -1);
        }
        Put(animation, 0x20, std::int32_t{1});
    }
    Put(data, 0x18, reinterpret_cast<std::uintptr_t>(dataLayers.data()));
    Put(data, 0x20, std::int32_t{2});
    Put(data, 0x44, std::int32_t{73});
    Put(data, 0x4c + 1 * static_cast<std::size_t>(sizeof(std::int32_t)), 1);
    Put(data, 0x4c + 8 * static_cast<std::size_t>(sizeof(std::int32_t)), 0);

    Put(currentData, 0x18, reinterpret_cast<std::uintptr_t>(currentLayers.data()));
    Put(currentData, 0x44, std::int32_t{19});
    Put(currentData, 0x4c + 8 * static_cast<std::size_t>(sizeof(std::int32_t)), 0);
    Put(currentData, 0x28, reinterpret_cast<std::uintptr_t>(currentNullLayers.data()));
    Put(currentData, 0x30, std::int32_t{1});
    Put(currentNullLayers, 0x08, reinterpret_cast<std::uintptr_t>(nullFrame.data()));
    Put(currentNullLayers, 0x10, std::int32_t{1});

    Put(reloadData, 0x18, reinterpret_cast<std::uintptr_t>(currentLayers.data()));
    Put(reloadData, 0x44, std::int32_t{101});
    Put(reloadData, 0x4c + 8 * static_cast<std::size_t>(sizeof(std::int32_t)), 0);

    Put(dataLayers, 0 * kLayerStride + 0x00, std::int32_t{8});
    Put(dataLayers, 0 * kLayerStride + 0x08, reinterpret_cast<std::uintptr_t>(dataFrames.data()));
    Put(dataLayers, 0 * kLayerStride + 0x10, std::int32_t{2});
    Put(dataLayers, 0 * kLayerStride + 0x14, std::uint8_t{1});
    Put(dataLayers, 1 * kLayerStride + 0x00, std::int32_t{1});
    Put(dataLayers, 1 * kLayerStride + 0x08, reinterpret_cast<std::uintptr_t>(dataFrames.data()));
    Put(dataLayers, 1 * kLayerStride + 0x10, std::int32_t{2});
    Put(dataLayers, 1 * kLayerStride + 0x14, std::uint8_t{1});

    Put(currentLayers, 0x00, std::int32_t{8});
    Put(currentLayers, 0x08, reinterpret_cast<std::uintptr_t>(currentFrames.data()));
    Put(currentLayers, 0x10, std::int32_t{2});
    Put(currentLayers, 0x14, std::uint8_t{1});

    for (std::size_t i = 0; i < 2; ++i) {
        const auto base = i * kFrameStride;
        Put(dataFrames, base + 0x08, i == 0 ? 24.0F : 31.0F);
        Put(dataFrames, base + 0x0c, i == 0 ? 12.0F : 17.0F);
        Put(dataFrames, base + 0x20, i == 0 ? 6.0F : 9.0F);
        Put(dataFrames, base + 0x24, i == 0 ? 7.0F : 10.0F);
        Put(dataFrames, base + 0x28, std::int32_t{1});
        Put(dataFrames, base + 0x2c, std::uint8_t{1});
        Put(dataFrames, base + 0x64, i == 0 ? 0 : 1);
        Put(dataFrames, base + 0x68, i == 0 ? 1 : 3);

        Put(currentFrames, base + 0x08, i == 0 ? 21.0F : 22.0F);
        Put(currentFrames, base + 0x0c, 10.0F);
        Put(currentFrames, base + 0x20, i == 0 ? 4.0F : 5.0F);
        Put(currentFrames, base + 0x24, 6.0F);
        Put(currentFrames, base + 0x28, std::int32_t{2});
        Put(currentFrames, base + 0x64, i == 0 ? 0 : 2);
        Put(currentFrames, base + 0x68, i == 0 ? 2 : 4);

        Put(alternateFrames, base + 0x08, i == 0 ? 40.0F : 41.0F);
        Put(alternateFrames, base + 0x0c, 10.0F);
        Put(alternateFrames, base + 0x20, i == 0 ? 12.0F : 13.0F);
        Put(alternateFrames, base + 0x24, 14.0F);
        Put(alternateFrames, base + 0x28, std::int32_t{2});
        Put(alternateFrames, base + 0x64, i == 0 ? 0 : 2);
        Put(alternateFrames, base + 0x68, i == 0 ? 2 : 4);
    }
    Put(alternateLayers, 0x00, std::int32_t{8});
    Put(alternateLayers, 0x08, reinterpret_cast<std::uintptr_t>(alternateFrames.data()));
    Put(alternateLayers, 0x10, std::int32_t{2});
    Put(alternateLayers, 0x14, std::uint8_t{1});
    Put(alternateNullLayers, 0x08,
        reinterpret_cast<std::uintptr_t>(reloadNullFrame.data()));
    Put(alternateNullLayers, 0x10, std::int32_t{1});

    Put(anm2, 0x98, reinterpret_cast<std::uintptr_t>(animationSlots.data()));
    Put(anm2, 0xa0, std::int32_t{3});
    Put(anm2, 0x30 + 0x08, reinterpret_cast<std::uintptr_t>(currentData));
    Put(anm2, 0x30 + 0x10, reinterpret_cast<std::uintptr_t>(
        []() -> std::int32_t* {
            static std::array<std::int32_t, 2> positions{1, 0};
            return positions.data();
        }()));
    Put(anm2, 0xa8, gLayerStateBase);
    Put(anm2, 0xb0, std::int32_t{2});

    InitLayerState(layerStates, 0 * kLayerStateStride, 1.0F);
    InitLayerState(layerStates, 1 * kLayerStateStride, 2.0F);
    InitLayerState(reloadLayerStates, 0 * kLayerStateStride, 3.0F);
    InitLayerState(reloadLayerStates, 1 * kLayerStateStride, 4.0F);

    Put(nullFrame, 0x00, 12.5F);
    Put(nullFrame, 0x04, -4.25F);
    Put(nullFrame, 0x10, 2.0F);
    Put(nullFrame, 0x14, 3.0F);
    Put(reloadNullFrame, 0x00, 99.0F);
    Put(reloadNullFrame, 0x04, 98.0F);
    Put(reloadNullFrame, 0x10, 8.0F);
    Put(reloadNullFrame, 0x14, 9.0F);
    std::memcpy(reloadStorage.data(), reloadData, reloadStorage.size());
}

static int TestVectorIndex(lua_State* state) {
    auto* value = TryVectorArgument(state, 1);
    if (!value) return luaL_error(state, "Vector expected");
    const char* field = luaL_checkstring(state, 2);
    if (std::strcmp(field, "X") == 0) {
        lua_pushnumber(state, value->x);
        return 1;
    }
    if (std::strcmp(field, "Y") == 0) {
        lua_pushnumber(state, value->y);
        return 1;
    }
    lua_pushnil(state);
    return 1;
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
static int MakeColor(lua_State* state) {
    auto* value = static_cast<LuaRuntime::ColorHandle*>(
        lua_newuserdata(state, sizeof(LuaRuntime::ColorHandle)));
    *value = {};
    for (int index = 1; index <= 7; ++index) {
        const auto number = static_cast<float>(luaL_checknumber(state, index));
        switch (index) {
            case 1: value->red = number; break;
            case 2: value->green = number; break;
            case 3: value->blue = number; break;
            case 4: value->alpha = number; break;
            case 5: value->offsetRed = number; break;
            case 6: value->offsetGreen = number; break;
            case 7: value->offsetBlue = number; break;
        }
    }
    luaL_getmetatable(state, LuaRuntime::kColorMetatable);
    lua_setmetatable(state, -2);
    return 1;
}
static void InstallSupportTypes(lua_State* state) {
    luaL_newmetatable(state, LuaRuntime::kSpriteMetatable);
    lua_newtable(state);
    lua_setfield(state, -2, "__methods");
    lua_pushcfunction(state, NativeClassMethodIndex);
    lua_setfield(state, -2, "__index");
    lua_pop(state, 1);

    luaL_newmetatable(state, LuaRuntime::kVectorMetatable);
    lua_pushcfunction(state, TestVectorIndex);
    lua_setfield(state, -2, "__index");
    lua_pop(state, 1);
    RegisterVectorReferenceMetatable(state);

    luaL_newmetatable(state, LuaRuntime::kColorMetatable);
    lua_pop(state, 1);
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
        {LUA_UTF8LIBNAME, luaopen_utf8},
        {LUA_COLIBNAME, luaopen_coroutine},
    };
    for (const auto& library : libraries) {
        luaL_requiref(state, library.name, library.open, 1);
        lua_pop(state, 1);
    }
}

static const void* FakeGetAnimationData(const void*, const char* name) noexcept {
    ++animationLookups;
    return name && std::strcmp(name, "highlights") == 0 ? gNamedData : nullptr;
}
static void* FakeGetLayerInt(void*, int id) noexcept {
    if (id < 0 || id >= 2) return nullptr;
    return reinterpret_cast<void*>(gLayerStateBase + static_cast<std::size_t>(id) * kLayerStateStride);
}
static void* FakeGetLayerName(void*, const char* name) noexcept {
    ++layerNameLookups;
    if (!name) return nullptr;
    if (std::strcmp(name, "default") == 0) return FakeGetLayerInt(nullptr, 0);
    if (std::strcmp(name, "second") == 0) return FakeGetLayerInt(nullptr, 1);
    return nullptr;
}
static const void* FakeGetNullFrame(const void*, const char* name) noexcept {
    ++nullFrameLookups;
    return name && std::strcmp(name, "Stage") == 0 ? gNullFrame : nullptr;
}

static int MakeSprite(lua_State* state) {
    PushCallbackSpriteHandle(state, reinterpret_cast<std::uintptr_t>(anm2.data()), LUA_NOREF);
    return 1;
}
static int Native(lua_State* state) {
    const auto op = static_cast<int>(luaL_checkinteger(state, 1));
    if (op == 1) {
        gNamedData = reloadStorage.data();
        Put(anm2, 0x98, reinterpret_cast<std::uintptr_t>(reloadStorage.data()));
        Put(anm2, 0xa0, std::int32_t{1});
        Put(anm2, 0x30 + 0x08, reinterpret_cast<std::uintptr_t>(reloadStorage.data()));
    }
    if (op == 2) Put(anm2, 0x30 + 0x08, reinterpret_cast<std::uintptr_t>(reloadData));
    if (op == 3) {
        gLayerStateBase = reinterpret_cast<std::uintptr_t>(reloadLayerStates.data());
        Put(anm2, 0xa8, gLayerStateBase);
    }
    if (op == 4) {
        gNullFrame = reloadNullFrame.data();
        Put(currentNullLayers, 0x08,
            reinterpret_cast<std::uintptr_t>(reloadNullFrame.data()));
    }
    if (op == 5) {
        gNamedData = data;
        Put(anm2, 0x98, reinterpret_cast<std::uintptr_t>(animationSlots.data()));
        Put(anm2, 0xa0, std::int32_t{3});
        Put(anm2, 0x30 + 0x08, reinterpret_cast<std::uintptr_t>(currentData));
    }
    if (op == 6) Put(anm2, 0x30 + 0x08, reinterpret_cast<std::uintptr_t>(currentData));
    if (op == 7) {
        gLayerStateBase = reinterpret_cast<std::uintptr_t>(layerStates.data());
        Put(anm2, 0xa8, gLayerStateBase);
    }
    if (op == 8) {
        gNullFrame = nullFrame.data();
        Put(currentNullLayers, 0x08,
            reinterpret_cast<std::uintptr_t>(nullFrame.data()));
    }
    if (op == 9) alive = false;
    if (op == 10) alive = true;
    if (op == 11) {
        Put(currentLayers, 0x08,
            reinterpret_cast<std::uintptr_t>(alternateFrames.data()));
    }
    if (op == 12) {
        Put(currentData, 0x18,
            reinterpret_cast<std::uintptr_t>(alternateLayers.data()));
    }
    if (op == 13) {
        gNullFrame = reloadNullFrame.data();
        Put(currentData, 0x28,
            reinterpret_cast<std::uintptr_t>(alternateNullLayers.data()));
    }
    if (op == 14) {
        Put(currentLayers, 0x08,
            reinterpret_cast<std::uintptr_t>(currentFrames.data()));
    }
    if (op == 15) {
        Put(currentData, 0x18,
            reinterpret_cast<std::uintptr_t>(currentLayers.data()));
    }
    if (op == 16) {
        gNullFrame = nullFrame.data();
        Put(currentData, 0x28,
            reinterpret_cast<std::uintptr_t>(currentNullLayers.data()));
    }
    return 0;
}
static int U8(lua_State* state) {
    const auto which = static_cast<int>(luaL_checkinteger(state, 1));
    const auto offset = static_cast<std::size_t>(luaL_checkinteger(state, 2));
    const auto& bytes = which == 0 ? layerStates : reloadLayerStates;
    lua_pushinteger(state, static_cast<lua_Integer>(At<std::uint8_t>(bytes, offset)));
    return 1;
}
static int F32(lua_State* state) {
    const auto which = static_cast<int>(luaL_checkinteger(state, 1));
    const auto offset = static_cast<std::size_t>(luaL_checkinteger(state, 2));
    const auto& bytes = which == 0 ? layerStates : reloadLayerStates;
    lua_pushnumber(state, static_cast<lua_Number>(At<float>(bytes, offset)));
    return 1;
}
static int ShortView(lua_State* state) {
    const char* metatable = luaL_checkstring(state, 1);
    static_cast<void>(lua_newuserdata(state, 1));
    luaL_getmetatable(state, metatable);
    lua_setmetatable(state, -2);
    return 1;
}
static int LookupCounts(lua_State* state) {
    lua_pushinteger(state, animationLookups);
    lua_pushinteger(state, layerNameLookups);
    lua_pushinteger(state, nullFrameLookups);
    return 3;
}
static void InstallHelpers(lua_State* state) noexcept {
    lua_pushcfunction(state, MakeSprite);
    lua_setglobal(state, "_newSprite");
    lua_pushcfunction(state, Native);
    lua_setglobal(state, "_native");
    lua_pushcfunction(state, U8);
    lua_setglobal(state, "_u8");
    lua_pushcfunction(state, F32);
    lua_setglobal(state, "_f32");
    lua_pushcfunction(state, ShortView);
    lua_setglobal(state, "_short");
    lua_pushcfunction(state, MakeVector);
    lua_setglobal(state, "_vector");
    lua_pushcfunction(state, MakeColor);
    lua_setglobal(state, "_color");
    lua_pushcfunction(state, LookupCounts);
    lua_setglobal(state, "_lookupCounts");
}

int main() {
    InitFixture();
    SetRepentogonSpriteNativeTestBindings({
        &FakeGetAnimationData, &FakeGetLayerInt, &FakeGetLayerName, &FakeGetNullFrame});
    LuaRuntime::ObserveGameThread();
    const NativePort port{Ready, Install, SpriteAlive};
    SetNativePort(&port);
    auto* state = luaL_newstate();
    assert(state);
    OpenLibraries(state);
    InstallSupportTypes(state);
    BeginRepentogonEnvironment(state, true, kSpriteCatalog);
    CompleteRepentogonEnvironment(state);
    assert(RepentogonEnvironmentActive());
    InstallHelpers(state);

    const char* script = R"lua(
assert(type(AnimationData) == 'table')
assert(type(AnimationLayer) == 'table')
assert(type(AnimationFrame) == 'table')
assert(type(NullFrame) == 'table')
assert(type(LayerState) == 'table')
assert(type(BlendMode) == 'table')
assert(BlendMode.Flag1 == nil)

local sprite = _newSprite()
assert(type(sprite.GetLayerFrameData) == 'function')
assert(type(sprite.GetNullFrame) == 'function')
assert(type(sprite.GetCurrentAnimationData) == 'function')
assert(type(sprite.GetAnimationData) == 'function')
assert(type(sprite.GetLayer) == 'function')

local frame = sprite:GetLayerFrameData(8)
assert(type(frame) == 'userdata')
assert(frame:GetStartFrame() == 2)
assert(frame:GetWidth() == 22.0)
local pivot = frame:GetPivot()
assert(pivot.X == 5.0 and pivot.Y == 6.0)
assert(getmetatable(pivot) ~= getmetatable(_vector(0, 0)))
assert(not pcall(function() pivot.X = 99.0 end))
assert(not pcall(pivot.Normalize, pivot))

local current = sprite:GetCurrentAnimationData()
assert(type(current) == 'userdata')
assert(current:GetLength() == 19)
local currentLayer = current:GetLayer(8)
local currentFrame = currentLayer:GetFrame(3)
assert(currentFrame:GetWidth() == 22.0)
assert(currentFrame:GetPivot().X == 5.0)

local highlights = sprite:GetAnimationData('highlights')
assert(type(highlights) == 'userdata')
assert(highlights:GetLength() == 73)
assert(highlights:GetLayer(1):GetFrame(1):GetWidth() == 31.0)
assert(highlights:GetLayer(1):GetFrame(-1):GetWidth() == 24.0)
assert(highlights:GetLayer(1):GetFrame(99):GetWidth() == 31.0)
assert(highlights:GetLayer(-1) == nil)
assert(highlights:GetLayer(63) == nil)

local nullFrame = sprite:GetNullFrame('Stage')
assert(type(nullFrame) == 'userdata')
local nullPos = nullFrame:GetPos()
local nullScale = nullFrame:GetScale()
assert(nullPos.X == 12.5 and nullPos.Y == -4.25)
assert(nullScale.X == 2.0 and nullScale.Y == 3.0)

local byName = sprite:GetLayer('default')
local byId = sprite:GetLayer(0)
assert(type(byName) == 'userdata' and type(byId) == 'userdata')
assert(sprite:GetLayer(2) == nil)
assert(sprite:GetLayer('missing') == nil)
assert(sprite:GetAnimationData('missing') == nil)
assert(sprite:GetNullFrame('missing') == nil)
assert(sprite:GetLayerFrameData(-1) == nil)

byName:SetVisible(false)
assert(_u8(0, 0x7c) == 0)
assert(_u8(0, 0x7b) == 0xa3 and _u8(0, 0x7d) == 0xa4)
byName:SetVisible(0)
assert(_u8(0, 0x7c) == 1)
byName:SetVisible()
assert(_u8(0, 0x7c) == 0)
byName:SetVisible({})
assert(_u8(0, 0x7c) == 1)
assert(not pcall(byName.SetVisible, byName, nil))
byName:SetPos(_vector(3.5, -2.0))
assert(_f32(0, 0x48) == 3.5 and _f32(0, 0x4c) == -2.0)
assert(_u8(0, 0x47) == 0xa5)
byName:SetColor(_color(0.5, 0.25, 0.75, 1.0, 2.0, -2.0, 4.0))
assert(_f32(0, 0x50) == 0.5 and _f32(0, 0x54) == 0.25)
assert(_f32(0, 0x58) == 0.75 and _f32(0, 0x5c) == 1.0)
assert(_f32(0, 0x60) == 0.0 and _f32(0, 0x6c) == 0.0)
assert(_f32(0, 0x70) == 2.0 and _f32(0, 0x74) == -2.0 and _f32(0, 0x78) == 4.0)

local blend = byName:GetBlendMode()
assert(type(blend) == 'userdata')
assert(blend.Flag1 == 1 and blend.Flag2 == 7 and blend.Flag3 == 2 and blend.Flag4 == 6)
blend.Flag1 = 4
blend.Flag2 = 5
blend.Flag3 = 3
blend.Flag4 = 2
assert(_u8(0, 0x80) == 4 and _u8(0, 0x84) == 5)
assert(_u8(0, 0x88) == 3 and _u8(0, 0x8c) == 2)
assert(_u8(0, 0x90) == 0x5a)
local blendAgain = byName:GetBlendMode()
assert(blendAgain.Flag1 == 4 and blendAgain.Flag4 == 2)
assert(not pcall(function() blend.Flag1 = 15 end))
assert(not pcall(function() blend.Flag1 = true end))

local a0, l0, n0 = _lookupCounts()
for i = 1, 16 do
    assert(highlights:GetLength() == 73)
    assert(current:GetLayer(8):GetFrame(3):GetWidth() == 22.0)
    byName:SetPos(_vector(i, -i))
    assert(nullFrame:GetScale().X == 2.0)
end
local a1, l1, n1 = _lookupCounts()
assert(a0 == a1 and l0 == l1 and n0 == n1)

-- Inner frame/null arrays are validated independently from their outer arrays.
local heldFrame = currentLayer:GetFrame(3)
_native(11)
assert(not pcall(heldFrame.GetWidth, heldFrame))
assert(currentLayer:GetFrame(3):GetWidth() == 41.0)
_native(14)

local heldLayer = current:GetLayer(8)
_native(12)
assert(not pcall(current.GetLength, current))
assert(not pcall(heldLayer.GetFrame, heldLayer))
local currentWithAlternateLayers = sprite:GetCurrentAnimationData()
assert(currentWithAlternateLayers:GetLayer(8):GetFrame(3):GetWidth() == 41.0)
_native(15)
assert(not pcall(currentWithAlternateLayers.GetLength, currentWithAlternateLayers))
assert(current:GetLength() == 19)

local innerNull = sprite:GetNullFrame('Stage')
_native(4)
assert(not pcall(innerNull.GetPos, innerNull))
assert(sprite:GetNullFrame('Stage'):GetPos().X == 99.0)
_native(8)

local outerNull = sprite:GetNullFrame('Stage')
_native(13)
assert(not pcall(outerNull.GetPos, outerNull))
assert(sprite:GetNullFrame('Stage'):GetPos().X == 99.0)
_native(16)
assert(outerNull:GetPos().X == 12.5)

local methods = {
    sprite.GetLayerFrameData, sprite.GetNullFrame, sprite.GetCurrentAnimationData,
    sprite.GetAnimationData, sprite.GetLayer, frame.GetStartFrame, frame.GetPivot,
    frame.GetWidth, nullFrame.GetPos, nullFrame.GetScale, current.GetLength,
    current.GetLayer, currentLayer.GetFrame, byName.SetVisible, byName.SetPos,
    byName.SetColor, byName.GetBlendMode,
}
for _, method in ipairs(methods) do
    assert(not pcall(method, {}, 1))
end
assert(not pcall(frame.GetStartFrame, _short('IsaacRuntime.AnimationFrame')))
assert(not pcall(nullFrame.GetPos, _short('IsaacRuntime.NullFrame')))
assert(not pcall(current.GetLength, _short('IsaacRuntime.AnimationData')))
assert(not pcall(currentLayer.GetFrame, _short('IsaacRuntime.AnimationLayer'), 0))
assert(not pcall(byName.GetBlendMode, _short('IsaacRuntime.LayerState')))
assert(not pcall(function() return _short('IsaacRuntime.BlendMode').Flag1 end))
assert(not pcall(sprite.GetLayer, _short('IsaacRuntime.Sprite'), 0))

-- A child strongly retains its owner userdata, not just the native address.
local retained
do
    local owner = _newSprite()
    retained = owner:GetAnimationData('highlights')
    owner = nil
end
collectgarbage('collect')
assert(retained:GetLength() == 73)

-- Changing the current animation keeps the old AnimationData element borrowed
-- from the same table valid, as upstream does.
_native(2)
assert(current:GetLength() == 19)
assert(nullFrame:GetPos().X == 12.5)
local currentChanged = sprite:GetCurrentAnimationData()
assert(currentChanged:GetLength() == 101)
_native(6)

-- Reloading the animation table invalidates every old element view without a
-- stale dereference.
_native(1)
assert(not pcall(retained.GetLength, retained))
assert(not pcall(current.GetLength, current))
assert(not pcall(currentChanged.GetLength, currentChanged))
assert(not pcall(nullFrame.GetPos, nullFrame))
local reloaded = sprite:GetAnimationData('highlights')
local currentReloaded = sprite:GetCurrentAnimationData()
assert(reloaded:GetLength() == 101 and currentReloaded:GetLength() == 101)
_native(5)
assert(not pcall(reloaded.GetLength, reloaded))
assert(not pcall(currentReloaded.GetLength, currentReloaded))
assert(sprite:GetNullFrame('Stage'):GetPos().X == 12.5)

_native(3)
assert(not pcall(byName.GetBlendMode, byName))
assert(not pcall(function() return blend.Flag1 end))
local layerReloaded = sprite:GetLayer('default')
assert(layerReloaded:GetBlendMode().Flag1 == 1)
_native(7)

-- Entity-backed pause sprites reject retired native owners and all later children.
_native(9)
assert(not pcall(sprite.GetLayer, sprite, 0))
assert(not pcall(reloaded.GetLength, reloaded))
assert(not pcall(currentReloaded.GetLength, currentReloaded))
_native(10)
)lua";

    if (luaL_loadbuffer(state, script, std::strlen(script),
                        "@repentogon-sprite-api.lua") != LUA_OK ||
        lua_pcall(state, 0, 0, 0) != LUA_OK) {
        std::fprintf(stderr, "%s\n", lua_tostring(state, -1));
        return 1;
    }

    std::thread worker([] {
        auto* state = luaL_newstate();
        const lua_CFunction handlers[] = {
            RepentogonSpriteGetLayerFrameData,
            RepentogonSpriteGetNullFrame,
            RepentogonSpriteGetCurrentAnimationData,
            RepentogonSpriteGetAnimationData,
            RepentogonSpriteGetLayer,
            RepentogonAnimationFrameGetStartFrame,
            RepentogonAnimationFrameGetPivot,
            RepentogonAnimationFrameGetWidth,
            RepentogonNullFrameGetPos,
            RepentogonNullFrameGetScale,
            RepentogonAnimationDataGetLength,
            RepentogonAnimationDataGetLayer,
            RepentogonAnimationLayerGetFrame,
            RepentogonLayerStateSetVisible,
            RepentogonLayerStateSetPos,
            RepentogonLayerStateSetColor,
            RepentogonLayerStateGetBlendMode,
            RepentogonBlendModeGetFlag1,
            RepentogonBlendModeGetFlag2,
            RepentogonBlendModeGetFlag3,
            RepentogonBlendModeGetFlag4,
        };
        for (const auto handler : handlers) {
            lua_pushcfunction(state, handler);
            lua_pushnil(state);
            const auto result = lua_pcall(state, 1, 0, 0);
            const char* message = lua_tostring(state, -1);
            assert(result != LUA_OK && message && std::strstr(message, "game thread"));
            lua_pop(state, 1);
        }
        lua_close(state);
    });
    worker.join();

    EndRepentogonEnvironment(state);
    lua_close(state);
    SetNativePort(nullptr);
    SetRepentogonSpriteNativeTestBindings({});
}
'''


class RepentogonSpriteApiTests(unittest.TestCase):
    def test_nested_views_layers_blend_and_lifetime(self):
        with tempfile.TemporaryDirectory(prefix="repentogon-sprite-api-") as folder:
            extra_sources = (
                () if SPRITE_API in test_support.layered_lua_runtime_sources(SOURCE)
                else (SPRITE_API,)
            )
            binary = test_support.build_lua_harness(
                source_root=SOURCE,
                workdir=Path(folder),
                harness_source=DRIVER,
                extra_sources=extra_sources,
            )
            result = subprocess.run([str(binary)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
