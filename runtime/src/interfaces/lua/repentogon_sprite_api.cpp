#include "interfaces/lua/repentogon_sprite_api.hpp"

#include "infrastructure/call/engine_call_access.hpp"
#include "infrastructure/memory/engine_field_access.hpp"
#include "interfaces/lua/class_metadata.hpp"
#include "interfaces/lua/api100_strings.hpp"
#include "program/xml_data_store.hpp"
#include "interfaces/lua/color_api.hpp"
#include "interfaces/lua/engine_color_mod.hpp"
#include "interfaces/lua/owner_binding.hpp"
#include "interfaces/lua/sprite_api.hpp"
#include "interfaces/lua/vector_api.hpp"
#include "lua_object_handles.hpp"
#include "lua_runtime.hpp"
#include "runtime_constants.hpp"

#include <array>
#include <cstdint>
#include <cstring>
#include <cstdlib>

extern "C" {
#include <lauxlib.h>
}

namespace isaac::runtime {
namespace {

// Layouts below are taken from consumers and writers in the pinned Switch NRO;
// PC declarations are used only to name the fields those instructions address.
constexpr std::uintptr_t kAnim2MainStateOffset = 0x30;
constexpr std::uintptr_t kAnimationStateDataOffset = 0x08;
constexpr std::uintptr_t kAnimationStateLayerFramesOffset = 0x10;
constexpr std::uintptr_t kAnim2LayerStatesOffset = 0xa8;
// RenderFrame at 0x88a4 combines ANM2+0x150 with the per-layer flags.
constexpr std::uintptr_t kAnim2RenderFlagsOffset = 0x150;
static_assert(kAnim2RenderFlagsOffset + sizeof(std::uint32_t) <= kSpriteObjectSize);
// ANM2::GetNullFrame(char const*) @0xBBD0 advances x0 by 0x30 before calling
// AnimationState::GetNullFrame, and reads state._animData through [ANM2+0x38].
// AnimationState::GetLayerPosition @0x84B0 reads the same +8 data pointer,
// state layer frames at +0x10, and AnimationData's layer map at +0x4c.

constexpr std::uintptr_t kAnimationDataLayersOffset = 0x18;
constexpr std::uintptr_t kAnimationDataLayerCountOffset = 0x20;
constexpr std::uintptr_t kAnimationDataNullLayersOffset = 0x28;
constexpr std::uintptr_t kAnimationDataNullLayerCountOffset = 0x30;
constexpr std::uintptr_t kAnimationDataLengthOffset = 0x44;
constexpr std::uintptr_t kAnimationDataLayerMapOffset = 0x4c;
constexpr std::uintptr_t kAnimationDataReadableSize = 0x14c;
constexpr std::int32_t kAnimationLayerMapCount = 64;
// AnimationState::SetLayerPosition @0x8388 reads layer count +0x20 and layer
// array +0x18. AnimationState::Update @0x8504 reads the end position +0x44.

constexpr std::size_t kAnimationLayerStride = 0x18;
constexpr std::uintptr_t kAnimationLayerFramesOffset = 0x08;
constexpr std::uintptr_t kAnimationLayerFrameCountOffset = 0x10;
// SetLayerPosition walks +0x18-byte layers, reads frame count at layer+0x10,
// then dereferences the frame array pointer at layer+0x8.

constexpr std::size_t kAnimationFrameStride = 0x6c;
constexpr std::uintptr_t kAnimationFrameWidthOffset = 0x08;
constexpr std::uintptr_t kAnimationFramePosOffset = 0x10;
constexpr std::uintptr_t kAnimationFramePivotOffset = 0x20;
constexpr std::uintptr_t kAnimationFrameVisibleOffset = 0x2c;
constexpr std::uintptr_t kAnimationFrameColorOffset = 0x30;
constexpr std::uintptr_t kAnimationFrameStartOffset = 0x64;
constexpr std::uintptr_t kAnimationFrameEndOffset = 0x68;
// AnmCache::read_frames_binary @0x15E40 uses a 0x6c stride and writes the
// duration-derived start/end at +0x64/+0x68. AnimationLayer::GetDestQuad
// @0x9790 reads width/height from frame+0x8/+0xc, position from frame+0x10,
// and pivot from frame+0x20.
// AnimationLayer::RenderFrame @0x87DC rejects frame+0x2c == 0 and consumes the
// frame ColorMod at +0x30 in the same 0x6c-byte record.

constexpr std::size_t kNullFrameReadableSize = 0x54;
constexpr std::size_t kNullFrameStride = 0x54;
constexpr std::uintptr_t kNullFramePosOffset = 0x00;
constexpr std::uintptr_t kNullFrameScaleOffset = 0x10;
constexpr std::size_t kNullLayerStride = 0x18;
constexpr std::uintptr_t kNullLayerFramesOffset = 0x08;
constexpr std::uintptr_t kNullLayerCountOffset = 0x10;
// AnmCache::read_nullframes_binary @0x15C04 uses a 0x54 stride and writes the
// first vector at +0 and scale at +0x10. Entity::get_null_offset @0x65FE4
// passes the null-frame base as Vector2; get_null_capsule @0x66094 multiplies
// the vector at null-frame+0x10. AnimationState::GetNullFrame(int) @0xB008
// walks AnimationData's 0x18-byte null-layer records at +0x28/+0x30; each
// record stores its frame array/count at +0x8/+0x10. Creation performs one
// bounded record scan to capture that inner array; later getters validate it O(1).

constexpr std::size_t kLayerStateReadableSize = 0xb0;
constexpr std::uintptr_t kLayerDataDefaultSpritesheetPathOffset = 0x20;
constexpr std::uintptr_t kLayerStateSpritesheetPathOffset = 0x10;
constexpr std::uintptr_t kLayerStateSizeOffset = 0x3c;
constexpr std::uintptr_t kLayerStatePosOffset = 0x48;
constexpr std::uintptr_t kLayerStateColorOffset = 0x50;
constexpr std::uintptr_t kLayerStateVisibleOffset = 0x7c;
constexpr std::uintptr_t kLayerStateBlendModeOffset = 0x80;
constexpr std::uintptr_t kLayerStateCropOffsetOffset = 0x94;
// LayerState::LayerState @0x722C constructs position at +0x48, ColorMod at
// +0x50, BlendMode at +0x80, crop offset at +0x94, and the smart pointer ending
// at +0xb0. AnimationLayer::RenderFrame @0x87DC walks 0xb0-byte LayerStates
// from ANM2+0xa8, then reads visibility +0x7c, color +0x50, and blend +0x80.
// AnimationLayer::GetDestQuad @0x9790 adds LayerState position at +0x48.
// LayerState::LayerState @0x722C zeroes the libc++ string at +0x10, then
// constructs the size vector at +0x3c. Copy constructor @0x7404 copies both;
// ReplaceSpritesheet writes the replacement path into the same string.
// The same constructor builds crop offset at +0x94. Reset @0x7284 copies the
// LayerData default spritesheet string from LayerData+0x20.

// Switch BlendMode constructors/copy/equality operate on exactly four words
// (0x10 bytes). BlendMode(eBlendMode 0) writes {1,0,1,0} and mode 1 writes
// {1,7,1,7}; those are the upstream RGB/alpha source/destination factor fields.
// The PC-only equation word is absent from this Switch object.
constexpr std::size_t kBlendModeReadableSize = 0x10;
constexpr std::uintptr_t kBlendModeFlag1Offset = 0x00;
constexpr std::uintptr_t kBlendModeFlag2Offset = 0x04;
constexpr std::uintptr_t kBlendModeFlag3Offset = 0x08;
constexpr std::uintptr_t kBlendModeFlag4Offset = 0x0c;
constexpr std::uint32_t kBlendFactorCount = 15;

constexpr char kAnimationDataMetatable[] = "IsaacRuntime.AnimationData";
constexpr char kAnimationLayerMetatable[] = "IsaacRuntime.AnimationLayer";
constexpr char kAnimationFrameMetatable[] = "IsaacRuntime.AnimationFrame";
constexpr char kNullFrameMetatable[] = "IsaacRuntime.NullFrame";
constexpr char kLayerStateMetatable[] = "IsaacRuntime.LayerState";
constexpr char kBlendModeMetatable[] = "IsaacRuntime.BlendMode";

struct AnimationDataView {
    void* data;
    std::array<std::uint64_t, 3> nameWords;
    std::int32_t layerCount;
    std::int32_t length;
    std::uintptr_t layers;
    std::uintptr_t nullLayers;
    std::int32_t nullLayerCount;
    std::int32_t reserved;
};

struct AnimationLayerView {
    void* layer;
    std::int32_t layerId;
    std::uint32_t reserved;
};

struct AnimationFrameView {
    void* frame;
    std::int32_t frameIndex;
    std::uint32_t reserved;
};

struct NullFrameView {
    void* frame;
    std::uintptr_t frames;
    std::int32_t nullLayerIndex;
    std::int32_t frameIndex;
    std::int32_t frameCount;
    std::uint32_t reserved;
};

struct LayerStateView {
    void* layer;
    std::uintptr_t layerData;
};

struct BlendModeView {
    void* blendMode;
};

#if defined(__SWITCH__)
constexpr std::array<std::uint8_t, 16> kGetAnimationDataGuard = {
    0xFD, 0x7B, 0xBD, 0xA9, 0xF6, 0x57, 0x01, 0xA9,
    0xFD, 0x03, 0x00, 0x91, 0xF4, 0x4F, 0x02, 0xA9,
};
constexpr std::array<std::uint8_t, 16> kGetLayerIntGuard = {
    0xFD, 0x7B, 0xBE, 0xA9, 0xF4, 0x4F, 0x01, 0xA9,
    0xFD, 0x03, 0x00, 0x91, 0xF3, 0x03, 0x01, 0x2A,
};
constexpr std::array<std::uint8_t, 16> kGetLayerNameGuard = {
    0xFD, 0x7B, 0xBD, 0xA9, 0xF6, 0x57, 0x01, 0xA9,
    0xFD, 0x03, 0x00, 0x91, 0xF4, 0x4F, 0x02, 0xA9,
};
constexpr std::array<std::uint8_t, 16> kGetNullFrameGuard = {
    0x08, 0x1C, 0x40, 0xF9, 0x68, 0x00, 0x00, 0xB4,
    0x00, 0xC0, 0x00, 0x91, 0x0D, 0x92, 0x19, 0x14,
};
#else
RepentogonSpriteNativeTestBindings g_NativeTestBindings{};
#endif

void RequireGameThread(lua_State* state) {
    if (!LuaRuntime::IsOnGameThread()) {
        luaL_error(state, "REPENTOGON sprite access requires the game thread");
    }
}

template <class T>
T* CheckView(lua_State* state, int index, const char* metatable, const char* name) {
    void* raw = luaL_testudata(state, index, metatable);
    if (raw == nullptr || lua_rawlen(state, index) != sizeof(T)) {
        luaL_error(state, "%s reference is invalid", name);
        return nullptr;
    }
    return static_cast<T*>(raw);
}

void* ResolveSpriteAt(lua_State* state, int index, const char* name) {
    if (lua_rawlen(state, index) < sizeof(LuaRuntime::SpriteHandle)) {
        luaL_error(state, "%s owner Sprite is invalid", name);
        return nullptr;
    }
    void* sprite = TryResolveSpriteArgument(state, index);
    if (sprite == nullptr) {
        luaL_error(state, "%s owner Sprite is no longer available", name);
        return nullptr;
    }
    return sprite;
}

template <class T>
T ReadOrError(lua_State* state, std::uintptr_t address, const char* name) {
    T value{};
    if (!engine_memory::ReadField(address, 0, &value,
                                  engine_memory::EngineMemoryReadable)) {
        luaL_error(state, "%s is not readable", name);
        return T{};
    }
    return value;
}

template <class T>
void WriteOrError(lua_State* state, std::uintptr_t address, const T& value,
                  const char* name) {
    if (!engine_memory::WriteField(address, 0, value,
                                   engine_memory::EngineMemoryWritable)) {
        luaL_error(state, "%s is not writable", name);
    }
}

bool TryReadPointer(std::uintptr_t address, std::uintptr_t* value) noexcept {
    return engine_memory::ReadField(address, 0, value,
                                    engine_memory::EngineMemoryReadable);
}

bool Readable(std::uintptr_t address, std::size_t size) noexcept {
    return address != 0 && engine_memory::EngineMemoryReadable(address, size);
}

void CaptureAnimationDataStamp(lua_State* state, AnimationDataView* view) {
    const auto address = engine_memory::AddressOf(view->data);
    for (std::size_t index = 0; index < view->nameWords.size(); ++index) {
        view->nameWords[index] = ReadOrError<std::uint64_t>(
            state, address + index * sizeof(std::uint64_t),
            "AnimationData name");
    }
    view->layerCount = ReadOrError<std::int32_t>(
        state, address + kAnimationDataLayerCountOffset,
        "AnimationData layer count");
    view->length = ReadOrError<std::int32_t>(
        state, address + kAnimationDataLengthOffset, "AnimationData length");
    view->layers = ReadOrError<std::uintptr_t>(
        state, address + kAnimationDataLayersOffset,
        "AnimationData layer array");
    view->nullLayers = ReadOrError<std::uintptr_t>(
        state, address + kAnimationDataNullLayersOffset,
        "AnimationData null-layer array");
    view->nullLayerCount = ReadOrError<std::int32_t>(
        state, address + kAnimationDataNullLayerCountOffset,
        "AnimationData null-layer count");
}

void ValidateAnimationDataMember(lua_State* state, void* sprite,
                                 const AnimationDataView* view) {
    const auto spriteAddress = engine_memory::AddressOf(sprite);
    const auto array = ReadOrError<std::uintptr_t>(
        state, spriteAddress + kAnim2AnimationArrayOffset,
        "Sprite animation array");
    const auto count = ReadOrError<std::int32_t>(
        state, spriteAddress + kAnim2AnimationCountOffset,
        "Sprite animation count");
    if (array == 0 || count <= 0 ||
        static_cast<std::uint64_t>(count) >
            UINTPTR_MAX / static_cast<std::uintptr_t>(kAnim2AnimationStride) ||
        !Readable(array, static_cast<std::size_t>(count) * kAnim2AnimationStride)) {
        luaL_error(state, "AnimationData owner animation array is unavailable");
    }
    const auto address = engine_memory::AddressOf(view->data);
    if (address < array) {
        luaL_error(state, "AnimationData reference no longer belongs to its Sprite");
    }
    const auto delta = address - array;
    if (delta % kAnim2AnimationStride != 0 ||
        delta / kAnim2AnimationStride >= static_cast<std::uintptr_t>(count)) {
        luaL_error(state, "AnimationData reference no longer belongs to its Sprite");
    }
    AnimationDataView current{};
    current.data = view->data;
    CaptureAnimationDataStamp(state, &current);
    if (current.nameWords != view->nameWords ||
        current.layerCount != view->layerCount ||
        current.length != view->length ||
        current.layers != view->layers ||
        current.nullLayers != view->nullLayers ||
        current.nullLayerCount != view->nullLayerCount) {
        luaL_error(state, "AnimationData contents changed after the view was created");
    }
}

void CaptureLayerStateStamp(lua_State* state, LayerStateView* view) {
    view->layerData = ReadOrError<std::uintptr_t>(
        state, engine_memory::AddressOf(view->layer), "LayerState layer data");
}

void ValidateLayerStateMember(lua_State* state, void* sprite,
                              const LayerStateView* view) {
    const auto spriteAddress = engine_memory::AddressOf(sprite);
    const auto array = ReadOrError<std::uintptr_t>(
        state, spriteAddress + kAnim2LayerStatesOffset,
        "Sprite layer-state array");
    const auto count = ReadOrError<std::int32_t>(
        state, spriteAddress + kAnim2LayerCountOffset,
        "Sprite layer count");
    if (array == 0 || count <= 0 ||
        static_cast<std::uint64_t>(count) >
            UINTPTR_MAX / static_cast<std::uintptr_t>(kLayerStateReadableSize) ||
        !Readable(array, static_cast<std::size_t>(count) * kLayerStateReadableSize)) {
        luaL_error(state, "LayerState owner layer array is unavailable");
    }
    const auto address = engine_memory::AddressOf(view->layer);
    if (address < array) {
        luaL_error(state, "LayerState reference no longer belongs to its Sprite");
    }
    const auto delta = address - array;
    if (delta % kLayerStateReadableSize != 0 ||
        delta / kLayerStateReadableSize >= static_cast<std::uintptr_t>(count)) {
        luaL_error(state, "LayerState reference no longer belongs to its Sprite");
    }
    const auto layerData = ReadOrError<std::uintptr_t>(
        state, address, "LayerState layer data");
    if (layerData != view->layerData) {
        luaL_error(state, "LayerState contents changed after the view was created");
    }
}

#if defined(__SWITCH__)
template <class Function>
Function NativeEntry(lua_State* state, std::uintptr_t offset,
                     const std::array<std::uint8_t, 16>& guard, const char* name) {
    const auto base = LuaRuntime::EngineModuleBase();
    if (base == 0 || base > UINTPTR_MAX - offset ||
        !engine_memory::EngineMemoryReadable(base + offset, guard.size()) ||
        std::memcmp(engine_memory::AsObject(base + offset), guard.data(), guard.size()) != 0) {
        luaL_error(state, "%s native binding is unavailable", name);
        return {};
    }
    return engine_call::AsFunction<Function>(base + offset);
}
#endif

const void* GetAnimationDataNative(lua_State* state, const void* sprite, const char* name) {
#if defined(__SWITCH__)
    using Function = const void* (*)(const void*, const char*);
    return NativeEntry<Function>(state, 0xBAC4, kGetAnimationDataGuard,
                                 "Sprite:GetAnimationData")(sprite, name);
#else
    if (g_NativeTestBindings.getAnimationData == nullptr) {
        luaL_error(state, "Sprite:GetAnimationData host binding is unavailable");
        return nullptr;
    }
    return g_NativeTestBindings.getAnimationData(sprite, name);
#endif
}

void* GetLayerIntNative(lua_State* state, void* sprite, int id) {
#if defined(__SWITCH__)
    using Function = void* (*)(void*, int);
    return NativeEntry<Function>(state, 0xA034, kGetLayerIntGuard,
                                 "Sprite:GetLayer")(sprite, id);
#else
    if (g_NativeTestBindings.getLayerInt == nullptr) {
        luaL_error(state, "Sprite:GetLayer host binding is unavailable");
        return nullptr;
    }
    return g_NativeTestBindings.getLayerInt(sprite, id);
#endif
}

void* GetLayerNameNative(lua_State* state, void* sprite, const char* name) {
#if defined(__SWITCH__)
    using Function = void* (*)(void*, const char*);
    return NativeEntry<Function>(state, 0xBE30, kGetLayerNameGuard,
                                 "Sprite:GetLayer")(sprite, name);
#else
    if (g_NativeTestBindings.getLayerName == nullptr) {
        luaL_error(state, "Sprite:GetLayer host binding is unavailable");
        return nullptr;
    }
    return g_NativeTestBindings.getLayerName(sprite, name);
#endif
}

const void* GetNullFrameNative(lua_State* state, const void* sprite, const char* name) {
#if defined(__SWITCH__)
    using Function = const void* (*)(const void*, const char*);
    return NativeEntry<Function>(state, 0xBBD0, kGetNullFrameGuard,
                                 "Sprite:GetNullFrame")(sprite, name);
#else
    if (g_NativeTestBindings.getNullFrame == nullptr) {
        luaL_error(state, "Sprite:GetNullFrame host binding is unavailable");
        return nullptr;
    }
    return g_NativeTestBindings.getNullFrame(sprite, name);
#endif
}

void* AnimationDataCurrent(lua_State* state, void* sprite) {
    const auto stateAddress = engine_memory::AddressOf(sprite) + kAnim2MainStateOffset;
    std::uintptr_t data{};
    if (!TryReadPointer(stateAddress + kAnimationStateDataOffset, &data)) {
        luaL_error(state, "Sprite animation state is not readable");
        return nullptr;
    }
    return engine_memory::AsObject(data);
}

void* AnimationLayerById(lua_State* state, void* data, std::int32_t layerId,
                         std::int32_t* layerOrder = nullptr) {
    if (data == nullptr || layerId < 0 || layerId >= kAnimationLayerMapCount) {
        return nullptr;
    }
    const auto address = engine_memory::AddressOf(data);
    const auto order = ReadOrError<std::int32_t>(
        state, address + kAnimationDataLayerMapOffset +
                   static_cast<std::uintptr_t>(layerId) * sizeof(std::int32_t),
        "AnimationData layer map");
    const auto count = ReadOrError<std::int32_t>(
        state, address + kAnimationDataLayerCountOffset, "AnimationData layer count");
    if (layerOrder != nullptr) {
        *layerOrder = order;
    }
    if (order < 0 || order >= count) {
        return nullptr;
    }
    const auto layers = ReadOrError<std::uintptr_t>(
        state, address + kAnimationDataLayersOffset, "AnimationData layer array");
    if (layers == 0) {
        return nullptr;
    }
    const auto layer = layers + static_cast<std::uintptr_t>(order) * kAnimationLayerStride;
    return Readable(layer, kAnimationLayerStride) ? engine_memory::AsObject(layer) : nullptr;
}

bool FindNullFrameSlot(lua_State* state, void* data, void* frame,
                       NullFrameView* view) {
    const auto address = engine_memory::AddressOf(data);
    const auto layerCount = ReadOrError<std::int32_t>(
        state, address + kAnimationDataNullLayerCountOffset,
        "AnimationData null-layer count");
    const auto layers = ReadOrError<std::uintptr_t>(
        state, address + kAnimationDataNullLayersOffset,
        "AnimationData null-layer array");
    if (layerCount <= 0 || layers == 0) {
        return false;
    }
    const auto target = engine_memory::AddressOf(frame);
    for (std::int32_t layer = 0; layer < layerCount; ++layer) {
        const auto record = layers + static_cast<std::uintptr_t>(layer) * kNullLayerStride;
        if (!Readable(record, kNullLayerStride)) {
            luaL_error(state, "AnimationData null-layer array is not readable");
        }
        const auto frames = ReadOrError<std::uintptr_t>(
            state, record + kNullLayerFramesOffset,
            "AnimationData null-frame array");
        const auto count = ReadOrError<std::int32_t>(
            state, record + kNullLayerCountOffset,
            "AnimationData null-frame count");
        if (frames == 0 || count <= 0 || target < frames) {
            continue;
        }
        const auto delta = target - frames;
        if (delta % kNullFrameStride == 0 &&
            delta / kNullFrameStride < static_cast<std::uintptr_t>(count)) {
            view->frames = frames;
            view->nullLayerIndex = layer;
            view->frameIndex = static_cast<std::int32_t>(delta / kNullFrameStride);
            view->frameCount = count;
            return true;
        }
    }
    return false;
}

void* AnimationFrameByIndex(lua_State* state, void* layer, std::int32_t index) {
    if (layer == nullptr) {
        return nullptr;
    }
    const auto address = engine_memory::AddressOf(layer);
    const auto count = ReadOrError<std::int32_t>(
        state, address + kAnimationLayerFrameCountOffset, "AnimationLayer frame count");
    if (index < 0 || index >= count) {
        return nullptr;
    }
    const auto frames = ReadOrError<std::uintptr_t>(
        state, address + kAnimationLayerFramesOffset, "AnimationLayer frame array");
    if (frames == 0) {
        return nullptr;
    }
    const auto frame = frames + static_cast<std::uintptr_t>(index) * kAnimationFrameStride;
    return Readable(frame, kAnimationFrameStride) ? engine_memory::AsObject(frame) : nullptr;
}

void* ResolveAnimationDataView(lua_State* state, int index) {
    index = lua_absindex(state, index);
    auto* view = CheckView<AnimationDataView>(state, index, kAnimationDataMetatable,
                                               "AnimationData");
    const int top = lua_gettop(state);
    lua_getuservalue(state, index);
    if (!lua_istable(state, -1)) {
        luaL_error(state, "AnimationData owner metadata is unavailable");
    }
    const int owners = lua_gettop(state);
    lua_rawgeti(state, owners, 1);
    void* sprite = ResolveSpriteAt(state, -1, "AnimationData");
    lua_settop(state, top);
    if (view->data == nullptr ||
        !Readable(engine_memory::AddressOf(view->data), kAnimationDataReadableSize)) {
        luaL_error(state, "AnimationData reference no longer belongs to its Sprite");
    }
    ValidateAnimationDataMember(state, sprite, view);
    return view->data;
}

void* ResolveAnimationLayerView(lua_State* state, int index) {
    index = lua_absindex(state, index);
    auto* view = CheckView<AnimationLayerView>(state, index, kAnimationLayerMetatable,
                                                "AnimationLayer");
    const int top = lua_gettop(state);
    lua_getuservalue(state, index);
    if (!lua_istable(state, -1)) {
        luaL_error(state, "AnimationLayer owner metadata is unavailable");
    }
    lua_rawgeti(state, -1, 1);
    void* data = ResolveAnimationDataView(state, -1);
    lua_settop(state, top);
    void* layer = AnimationLayerById(state, data, view->layerId);
    if (layer == nullptr || layer != view->layer) {
        luaL_error(state, "AnimationLayer reference no longer belongs to its AnimationData");
    }
    return layer;
}

void* ResolveAnimationFrameView(lua_State* state, int index) {
    index = lua_absindex(state, index);
    auto* view = CheckView<AnimationFrameView>(state, index, kAnimationFrameMetatable,
                                                "AnimationFrame");
    const int top = lua_gettop(state);
    lua_getuservalue(state, index);
    if (!lua_istable(state, -1)) {
        luaL_error(state, "AnimationFrame owner metadata is unavailable");
    }
    lua_rawgeti(state, -1, 1);
    void* layer = ResolveAnimationLayerView(state, -1);
    lua_settop(state, top);
    void* frame = AnimationFrameByIndex(state, layer, view->frameIndex);
    if (frame == nullptr || frame != view->frame) {
        luaL_error(state, "AnimationFrame reference no longer belongs to its AnimationLayer");
    }
    return frame;
}

bool ResolveAnimationFramePivotReference(lua_State* state, int ownerIndex,
                                         std::uintptr_t address,
                                         LuaRuntime::VectorHandle* out) noexcept {
    if (!LuaRuntime::IsOnGameThread() || out == nullptr) {
        return false;
    }
    void* frame = ResolveAnimationFrameView(state, ownerIndex);
    if (engine_memory::AddressOf(frame) != address) {
        return false;
    }
    return engine_memory::ReadField(address, kAnimationFramePivotOffset, out,
                                    engine_memory::EngineMemoryReadable);
}

void* ResolveNullFrameView(lua_State* state, int index) {
    index = lua_absindex(state, index);
    auto* view = CheckView<NullFrameView>(state, index, kNullFrameMetatable, "NullFrame");
    const int top = lua_gettop(state);
    lua_getuservalue(state, index);
    if (!lua_istable(state, -1)) {
        luaL_error(state, "NullFrame owner metadata is unavailable");
    }
    const int owners = lua_gettop(state);
    lua_rawgeti(state, owners, 1);
    void* data = ResolveAnimationDataView(state, -1);
    lua_settop(state, top);
    const auto dataAddress = engine_memory::AddressOf(data);
    const auto layerCount = ReadOrError<std::int32_t>(
        state, dataAddress + kAnimationDataNullLayerCountOffset,
        "AnimationData null-layer count");
    const auto layers = ReadOrError<std::uintptr_t>(
        state, dataAddress + kAnimationDataNullLayersOffset,
        "AnimationData null-layer array");
    if (layers == 0 || view->nullLayerIndex < 0 || view->nullLayerIndex >= layerCount) {
        luaL_error(state, "NullFrame reference no longer belongs to its AnimationData");
    }
    const auto record =
        layers + static_cast<std::uintptr_t>(view->nullLayerIndex) * kNullLayerStride;
    if (!Readable(record, kNullLayerStride)) {
        luaL_error(state, "NullFrame reference no longer belongs to its AnimationData");
    }
    const auto frames = ReadOrError<std::uintptr_t>(
        state, record + kNullLayerFramesOffset, "AnimationData null-frame array");
    const auto frameCount = ReadOrError<std::int32_t>(
        state, record + kNullLayerCountOffset, "AnimationData null-frame count");
    if (frames != view->frames || frameCount != view->frameCount ||
        view->frameIndex < 0 || view->frameIndex >= frameCount) {
        luaL_error(state, "NullFrame reference no longer belongs to its AnimationData");
    }
    void* frame = engine_memory::AsObject(
        frames + static_cast<std::uintptr_t>(view->frameIndex) * kNullFrameStride);
    if (frame != view->frame ||
        !Readable(engine_memory::AddressOf(frame), kNullFrameReadableSize)) {
        luaL_error(state, "NullFrame reference no longer belongs to its Sprite");
    }
    return frame;
}

void* ResolveLayerStateView(lua_State* state, int index) {
    index = lua_absindex(state, index);
    auto* view = CheckView<LayerStateView>(state, index, kLayerStateMetatable, "LayerState");
    const int top = lua_gettop(state);
    lua_getuservalue(state, index);
    if (!lua_istable(state, -1)) {
        luaL_error(state, "LayerState owner metadata is unavailable");
    }
    const int owners = lua_gettop(state);
    lua_rawgeti(state, owners, 1);
    void* sprite = ResolveSpriteAt(state, -1, "LayerState");
    lua_settop(state, top);
    if (view->layer == nullptr ||
        !Readable(engine_memory::AddressOf(view->layer), kLayerStateReadableSize)) {
        luaL_error(state, "LayerState reference no longer belongs to its Sprite");
    }
    ValidateLayerStateMember(state, sprite, view);
    return view->layer;
}

void* ResolveBlendModeView(lua_State* state, int index) {
    index = lua_absindex(state, index);
    auto* view = CheckView<BlendModeView>(state, index, kBlendModeMetatable, "BlendMode");
    const int top = lua_gettop(state);
    lua_getuservalue(state, index);
    if (!lua_istable(state, -1)) {
        luaL_error(state, "BlendMode owner metadata is unavailable");
    }
    lua_rawgeti(state, -1, 1);
    void* layer = ResolveLayerStateView(state, -1);
    lua_settop(state, top);
    void* blend = engine_memory::AsObject(
        engine_memory::AddressOf(layer) + kLayerStateBlendModeOffset);
    if (blend != view->blendMode ||
        !Readable(engine_memory::AddressOf(blend), kBlendModeReadableSize)) {
        luaL_error(state, "BlendMode reference no longer belongs to its LayerState");
    }
    return blend;
}

void AttachOwnerTable(lua_State* state, int userdataIndex, int ownerIndex) {
    const int userdata = lua_absindex(state, userdataIndex);
    const int owner = lua_absindex(state, ownerIndex);
    lua_createtable(state, 1, 0);
    lua_pushvalue(state, owner);
    lua_rawseti(state, -2, 1);
    lua_setuservalue(state, userdata);
}

void SetSecondValue(lua_State* state, int userdataIndex, int valueIndex) {
    const int userdata = lua_absindex(state, userdataIndex);
    const int value = lua_absindex(state, valueIndex);
    lua_getuservalue(state, userdata);
    lua_pushvalue(state, value);
    lua_rawseti(state, -2, 2);
    lua_pop(state, 1);
}

int PushAnimationDataView(lua_State* state, int ownerIndex, void* data) {
    ownerIndex = lua_absindex(state, ownerIndex);
    auto* view = static_cast<AnimationDataView*>(
        lua_newuserdata(state, sizeof(AnimationDataView)));
    *view = {};
    view->data = data;
    CaptureAnimationDataStamp(state, view);
    const int userdata = lua_gettop(state);
    AttachOwnerTable(state, userdata, ownerIndex);
    luaL_getmetatable(state, kAnimationDataMetatable);
    lua_setmetatable(state, userdata);
    return 1;
}

int PushAnimationLayerView(lua_State* state, int ownerIndex, void* layer,
                           std::int32_t layerId) {
    ownerIndex = lua_absindex(state, ownerIndex);
    auto* view = static_cast<AnimationLayerView*>(
        lua_newuserdata(state, sizeof(AnimationLayerView)));
    *view = {layer, layerId, 0};
    const int userdata = lua_gettop(state);
    AttachOwnerTable(state, userdata, ownerIndex);
    lua_pushinteger(state, layerId);
    SetSecondValue(state, userdata, -1);
    lua_pop(state, 1);
    luaL_getmetatable(state, kAnimationLayerMetatable);
    lua_setmetatable(state, userdata);
    return 1;
}

int PushAnimationFrameView(lua_State* state, int ownerIndex, void* frame,
                           std::int32_t frameIndex) {
    ownerIndex = lua_absindex(state, ownerIndex);
    auto* view = static_cast<AnimationFrameView*>(
        lua_newuserdata(state, sizeof(AnimationFrameView)));
    *view = {frame, frameIndex, 0};
    const int userdata = lua_gettop(state);
    AttachOwnerTable(state, userdata, ownerIndex);
    lua_pushinteger(state, frameIndex);
    SetSecondValue(state, userdata, -1);
    lua_pop(state, 1);
    luaL_getmetatable(state, kAnimationFrameMetatable);
    lua_setmetatable(state, userdata);
    return 1;
}

int PushNullFrameView(lua_State* state, int ownerIndex, void* frame,
                      const NullFrameView& slot) {
    ownerIndex = lua_absindex(state, ownerIndex);
    auto* view = static_cast<NullFrameView*>(
        lua_newuserdata(state, sizeof(NullFrameView)));
    *view = slot;
    view->frame = frame;
    const int userdata = lua_gettop(state);
    AttachOwnerTable(state, userdata, ownerIndex);
    luaL_getmetatable(state, kNullFrameMetatable);
    lua_setmetatable(state, userdata);
    return 1;
}

int PushLayerStateView(lua_State* state, void* layer) {
    auto* view = static_cast<LayerStateView*>(
        lua_newuserdata(state, sizeof(LayerStateView)));
    *view = {};
    view->layer = layer;
    CaptureLayerStateStamp(state, view);
    const int userdata = lua_gettop(state);
    AttachOwnerTable(state, userdata, 1);
    luaL_getmetatable(state, kLayerStateMetatable);
    lua_setmetatable(state, userdata);
    return 1;
}

int PushBlendModeView(lua_State* state, void* blendMode) {
    auto* view = static_cast<BlendModeView*>(
        lua_newuserdata(state, sizeof(BlendModeView)));
    *view = {blendMode};
    const int userdata = lua_gettop(state);
    AttachOwnerTable(state, userdata, 1);
    luaL_getmetatable(state, kBlendModeMetatable);
    lua_setmetatable(state, userdata);
    return 1;
}

int BlendFlag(lua_State* state, std::uintptr_t offset) {
    RequireGameThread(state);
    void* blend = ResolveBlendModeView(state, 1);
    const auto value = ReadOrError<std::uint32_t>(
        state, engine_memory::AddressOf(blend) + offset, "BlendMode flag");
    lua_pushinteger(state, static_cast<lua_Integer>(value));
    return 1;
}

void SetBlendFlag(lua_State* state, std::uintptr_t offset) {
    void* blend = ResolveBlendModeView(state, 1);
    const auto value = luaL_checkinteger(state, 3);
    if (value < 0 || value >= kBlendFactorCount) {
        luaL_argerror(state, 3, "Invalid blend factor");
    }
    WriteOrError(state, engine_memory::AddressOf(blend) + offset,
                 static_cast<std::uint32_t>(value), "BlendMode flag");
}

int BlendModeIndex(lua_State* state) {
    RequireGameThread(state);
    if (lua_type(state, 2) != LUA_TSTRING) {
        lua_pushnil(state);
        return 1;
    }
    if (!lua_getmetatable(state, 1)) {
        lua_pushnil(state);
        return 1;
    }
    lua_getfield(state, -1, "__propget");
    lua_remove(state, -2);
    if (!lua_istable(state, -1)) {
        lua_pop(state, 1);
        lua_pushnil(state);
        return 1;
    }
    lua_pushvalue(state, 2);
    lua_rawget(state, -2);
    if (!lua_isfunction(state, -1)) {
        lua_pop(state, 2);
        lua_pushnil(state);
        return 1;
    }
    lua_pushvalue(state, 1);
    lua_call(state, 1, 1);
    return 1;
}

int BlendModeNewIndex(lua_State* state) {
    RequireGameThread(state);
    CheckView<BlendModeView>(state, 1, kBlendModeMetatable, "BlendMode");
    const char* field = luaL_checkstring(state, 2);
    if (std::strcmp(field, "Flag1") == 0) {
        SetBlendFlag(state, kBlendModeFlag1Offset);
        return 0;
    }
    if (std::strcmp(field, "Flag2") == 0) {
        SetBlendFlag(state, kBlendModeFlag2Offset);
        return 0;
    }
    if (std::strcmp(field, "Flag3") == 0) {
        SetBlendFlag(state, kBlendModeFlag3Offset);
        return 0;
    }
    if (std::strcmp(field, "Flag4") == 0) {
        SetBlendFlag(state, kBlendModeFlag4Offset);
        return 0;
    }
    return luaL_error(state, "BlendMode has no writable field named %s", field);
}

std::size_t AttachMethodsToMetatable(lua_State* state, const char* metatable,
                                     const char* owner) {
    luaL_getmetatable(state, metatable);
    if (!lua_istable(state, -1)) {
        lua_pop(state, 1);
        return 0;
    }
    lua_getfield(state, -1, "__methods");
    if (!lua_istable(state, -1)) {
        lua_pop(state, 2);
        return 0;
    }
    const std::size_t attached = AttachOwnerMethods(state, owner, nullptr, 0);
    lua_pop(state, 2);
    return attached;
}

void RegisterMethodClass(lua_State* state, const char* name, const char* metatable,
                         const char* owner) {
    const bool created = luaL_newmetatable(state, metatable) != 0;
    const int cls = lua_gettop(state);
    if (created) {
        lua_pushstring(state, name);
        lua_setfield(state, cls, "__name");
        lua_newtable(state);
        lua_setfield(state, cls, "__methods");
        lua_pushcfunction(state, NativeClassMethodIndex);
        lua_setfield(state, cls, "__index");
    }
    lua_getfield(state, cls, "__methods");
    if (!lua_istable(state, -1)) {
        lua_pop(state, 1);
        lua_newtable(state);
        lua_pushvalue(state, -1);
        lua_setfield(state, cls, "__methods");
    }
    static_cast<void>(AttachOwnerMethods(state, owner, nullptr, 0));
    lua_pop(state, 1);
    PublishNativeClass(state, name, metatable);
    lua_pop(state, 1);
}

void RegisterBlendMode(lua_State* state) {
    const bool created = luaL_newmetatable(state, kBlendModeMetatable) != 0;
    const int cls = lua_gettop(state);
    if (created) {
        lua_pushliteral(state, "BlendMode");
        lua_setfield(state, cls, "__name");
        lua_pushliteral(state, "BlendMode");
        lua_setfield(state, cls, "__type");
        lua_pushcfunction(state, BlendModeIndex);
        lua_setfield(state, cls, "__index");
        lua_pushcfunction(state, BlendModeNewIndex);
        lua_setfield(state, cls, "__newindex");
    }
    lua_getfield(state, cls, "__propget");
    if (!lua_istable(state, -1)) {
        lua_pop(state, 1);
        lua_newtable(state);
    }
    static_cast<void>(AttachOwnerMethods(state, "BlendMode", nullptr, 0));
    lua_setfield(state, cls, "__propget");
    lua_pushvalue(state, cls);
    lua_setfield(state, cls, "__class");

    lua_getglobal(state, "BlendMode");
    if (lua_isnil(state, -1)) {
        lua_pop(state, 1);
        lua_newtable(state);
        lua_newtable(state);
        lua_pushvalue(state, cls);
        lua_setfield(state, -2, "__class");
        lua_setmetatable(state, -2);
        lua_setglobal(state, "BlendMode");
    } else if (!lua_istable(state, -1)) {
        luaL_error(state, "BlendMode global class is not a table");
    } else {
        lua_pop(state, 1);
    }
    lua_pop(state, 1);
}

// PC's Sprite global is both callable and the writable class method table.
// The base runtime registers it as a bare constructor function, which makes
// `Sprite.Render = ...` fail and leaves userdata dispatch on a private table.
// Promote that function into a class table and make __methods point at it, so
// native userdata and assignments such as portraits.lua's method wrappers see
// the same function values.
void PromoteSpriteClassTable(lua_State* state) {
    const int top = lua_gettop(state);
    luaL_getmetatable(state, LuaRuntime::kSpriteMetatable);
    if (!lua_istable(state, -1)) {
        lua_settop(state, top);
        luaL_error(state, "Sprite metatable must exist before REPENTOGON registration");
    }
    const int metatable = lua_gettop(state);

    lua_getglobal(state, "Sprite");
    if (lua_isnil(state, -1)) {
        lua_pop(state, 1);
        lua_pushcfunction(state, CreateSpriteHandle);
        lua_setglobal(state, "Sprite");
        lua_getglobal(state, "Sprite");
    }
    const int global = lua_gettop(state);
    int classTable = global;
    if (lua_isfunction(state, global)) {
        const int constructor = global;
        lua_newtable(state);
        classTable = lua_gettop(state);

        lua_getfield(state, metatable, "__methods");
        if (lua_istable(state, -1)) {
            CopyClassMethods(state, classTable, -1);
        }
        lua_pop(state, 1);

        lua_newtable(state);
        lua_pushvalue(state, constructor);
        lua_setfield(state, -2, "__call");
        lua_pushvalue(state, metatable);
        lua_setfield(state, -2, "__class");
        lua_setmetatable(state, classTable);

        lua_pushvalue(state, classTable);
        lua_setglobal(state, "Sprite");
    } else if (!lua_istable(state, global)) {
        lua_settop(state, top);
        luaL_error(state, "Sprite global must be a constructor or class table");
    }

    lua_pushvalue(state, classTable);
    lua_setfield(state, metatable, "__methods");
    lua_pushliteral(state, "Sprite");
    lua_setfield(state, metatable, "__type");
    lua_pushvalue(state, metatable);
    lua_setfield(state, metatable, "__class");

    if (lua_getmetatable(state, classTable)) {
        lua_pushvalue(state, metatable);
        lua_setfield(state, -2, "__class");
        lua_pop(state, 1);
    } else {
        lua_newtable(state);
        lua_pushvalue(state, metatable);
        lua_setfield(state, -2, "__class");
        lua_setmetatable(state, classTable);
    }
    lua_settop(state, top);
}

} // namespace

int RepentogonSpriteSetRenderFlags(lua_State* state) {
    RequireGameThread(state);
    auto* sprite = ResolveSpriteAt(state, 1, "Sprite:SetRenderFlags");
    const auto flags = static_cast<std::uint32_t>(luaL_checkinteger(state, 2));
    WriteOrError(state, engine_memory::AddressOf(sprite) + kAnim2RenderFlagsOffset,
                 flags, "Sprite render flags");
    return 0;
}

int RepentogonSpriteGetLayerFrameData(lua_State* state) {
    RequireGameThread(state);
    void* sprite = ResolveSpriteAt(state, 1, "Sprite:GetLayerFrameData");
    const auto layerId = static_cast<std::int32_t>(luaL_checkinteger(state, 2));
    void* data = AnimationDataCurrent(state, sprite);
    if (data == nullptr) {
        lua_pushnil(state);
        return 1;
    }
    if (!Readable(engine_memory::AddressOf(data), kAnimationDataReadableSize)) {
        return luaL_error(state, "Sprite current AnimationData is not readable");
    }
    if (layerId < 0 || layerId >= kAnimationLayerMapCount) {
        lua_pushnil(state);
        return 1;
    }
    std::int32_t layerOrder = -1;
    void* layer = AnimationLayerById(state, data, layerId, &layerOrder);
    if (layerOrder < 0 || layer == nullptr) {
        lua_pushnil(state);
        return 1;
    }
    const auto frameCount = ReadOrError<std::int32_t>(
        state, engine_memory::AddressOf(layer) + kAnimationLayerFrameCountOffset,
        "AnimationLayer frame count");
    if (frameCount <= 0) {
        lua_pushnil(state);
        return 1;
    }
    const auto stateAddress = engine_memory::AddressOf(sprite) + kAnim2MainStateOffset;
    const auto layerFrames = ReadOrError<std::uintptr_t>(
        state, stateAddress + kAnimationStateLayerFramesOffset,
        "AnimationState layer frames");
    if (layerFrames == 0) {
        lua_pushnil(state);
        return 1;
    }
    auto frameIndex = ReadOrError<std::int32_t>(
        state, layerFrames + static_cast<std::uintptr_t>(layerOrder) * sizeof(std::int32_t),
        "AnimationState layer frame");
    if (frameIndex < 0) frameIndex = 0;
    if (frameIndex >= frameCount) frameIndex = frameCount - 1;
    void* frame = AnimationFrameByIndex(state, layer, frameIndex);
    if (frame == nullptr) {
        lua_pushnil(state);
        return 1;
    }
    const int dataView = PushAnimationDataView(state, 1, data);
    const int dataViewIndex = lua_gettop(state);
    static_cast<void>(dataView);
    const int layerView = PushAnimationLayerView(state, dataViewIndex, layer, layerId);
    const int layerViewIndex = lua_gettop(state);
    static_cast<void>(layerView);
    return PushAnimationFrameView(state, layerViewIndex, frame, frameIndex);
}

int RepentogonSpriteGetNullFrame(lua_State* state) {
    RequireGameThread(state);
    void* sprite = ResolveSpriteAt(state, 1, "Sprite:GetNullFrame");
    const char* name = luaL_checkstring(state, 2);
    void* frame = const_cast<void*>(GetNullFrameNative(state, sprite, name));
    if (frame == nullptr) {
        lua_pushnil(state);
        return 1;
    }
    if (!Readable(engine_memory::AddressOf(frame), kNullFrameReadableSize)) {
        return luaL_error(state, "Sprite NullFrame is not readable");
    }
    void* data = AnimationDataCurrent(state, sprite);
    if (data == nullptr) {
        return luaL_error(state, "Sprite current AnimationData is unavailable");
    }
    NullFrameView slot{};
    if (!FindNullFrameSlot(state, data, frame, &slot)) {
        return luaL_error(state, "Sprite NullFrame does not belong to current AnimationData");
    }
    static_cast<void>(PushAnimationDataView(state, 1, data));
    const int dataViewIndex = lua_gettop(state);
    return PushNullFrameView(state, dataViewIndex, frame, slot);
}

int RepentogonSpriteGetCurrentAnimationData(lua_State* state) {
    RequireGameThread(state);
    void* sprite = ResolveSpriteAt(state, 1, "Sprite:GetCurrentAnimationData");
    void* data = AnimationDataCurrent(state, sprite);
    if (data == nullptr) {
        lua_pushnil(state);
        return 1;
    }
    if (!Readable(engine_memory::AddressOf(data), kAnimationDataReadableSize)) {
        return luaL_error(state, "Sprite current AnimationData is not readable");
    }
    return PushAnimationDataView(state, 1, data);
}

int RepentogonSpriteGetAnimationData(lua_State* state) {
    RequireGameThread(state);
    void* sprite = ResolveSpriteAt(state, 1, "Sprite:GetAnimationData");
    const char* name = luaL_checkstring(state, 2);
    void* data = const_cast<void*>(GetAnimationDataNative(state, sprite, name));
    if (data == nullptr) {
        lua_pushnil(state);
        return 1;
    }
    if (!Readable(engine_memory::AddressOf(data), kAnimationDataReadableSize)) {
        return luaL_error(state, "Sprite AnimationData is not readable");
    }
    return PushAnimationDataView(state, 1, data);
}

int RepentogonSpriteGetLayer(lua_State* state) {
    RequireGameThread(state);
    void* sprite = ResolveSpriteAt(state, 1, "Sprite:GetLayer");
    void* layer = nullptr;
    if (lua_type(state, 2) == LUA_TSTRING) {
        layer = GetLayerNameNative(state, sprite, luaL_checkstring(state, 2));
    } else {
        const auto id = static_cast<int>(luaL_checkinteger(state, 2));
        const auto count = ReadOrError<std::int32_t>(
            state, engine_memory::AddressOf(sprite) + kAnim2LayerCountOffset,
            "Sprite layer count");
        if (id >= 0 && id < count) {
            layer = GetLayerIntNative(state, sprite, id);
        }
    }
    if (layer == nullptr) {
        lua_pushnil(state);
        return 1;
    }
    if (!Readable(engine_memory::AddressOf(layer), kLayerStateReadableSize)) {
        return luaL_error(state, "Sprite LayerState is not readable");
    }
    return PushLayerStateView(state, layer);
}

void ApplyRepentogonXmlLayerTints(lua_State* state,int spriteIndex,
                                 const xml_data::XmlChildGroup& group) {
    RequireGameThread(state);
    void* sprite=ResolveSpriteAt(state,spriteIndex,"XML giant-book tint");
    const auto count=ReadOrError<std::int32_t>(state,
        engine_memory::AddressOf(sprite)+kAnim2LayerCountOffset,"Sprite layer count");
    for (const auto& child:group.entries) {
        const xml_data::XmlAttribute* name{};
        float tint[4]{};
        for (const auto& attribute:child.attributes) {
            if (attribute.name=="name") name=&attribute;
            for (unsigned c=0;c<4;++c) {
                constexpr const char* channels[]={"r","g","b","a"};
                if (attribute.name==channels[c]) tint[c]=std::strtol(attribute.value.c_str(),nullptr,10)/255.f;
            }
        }
        if (!name) continue;
        for (int i=count;i-->0;) {
            const auto layer=engine_memory::AddressOf(GetLayerIntNative(state,sprite,i));
            const auto data=ReadOrError<std::uintptr_t>(state,layer,"LayerState data");
            if (!data) continue;
            EngineStringView view{};
            if (!ResolveEngineStringView(data+8,&view)) luaL_error(state,"LayerState name is unavailable");
            if (view.size!=name->value.size() || (view.size &&
                std::memcmp(engine_memory::AsObject(view.data),name->value.data(),view.size))) continue;
            // Upstream modifies only tint: preserve colorize and additive shift.
            auto color=ReadOrError<EngineColorMod>(state,layer+kLayerStateColorOffset,"LayerState color");
            std::memcpy(color.tint,tint,sizeof(tint));
            WriteOrError(state,layer+kLayerStateColorOffset,color,"LayerState color");
        }
    }
}

int RepentogonAnimationFrameGetStartFrame(lua_State* state) {
    RequireGameThread(state);
    void* frame = ResolveAnimationFrameView(state, 1);
    lua_pushinteger(state, ReadOrError<std::int32_t>(
        state, engine_memory::AddressOf(frame) + kAnimationFrameStartOffset,
        "AnimationFrame start frame"));
    return 1;
}

int RepentogonAnimationFrameGetPivot(lua_State* state) {
    RequireGameThread(state);
    void* frame = ResolveAnimationFrameView(state, 1);
    PushExternalVectorReference(state, 1, engine_memory::AddressOf(frame),
                                &ResolveAnimationFramePivotReference);
    return 1;
}

int RepentogonAnimationFrameGetPos(lua_State* state) {
    RequireGameThread(state);
    void* frame = ResolveAnimationFrameView(state, 1);
    const auto pos = ReadOrError<LuaRuntime::VectorHandle>(
        state, engine_memory::AddressOf(frame) + kAnimationFramePosOffset,
        "AnimationFrame position");
    PushLuaVector(state, pos.x, pos.y);
    return 1;
}

int RepentogonAnimationFrameGetWidth(lua_State* state) {
    RequireGameThread(state);
    void* frame = ResolveAnimationFrameView(state, 1);
    lua_pushnumber(state, ReadOrError<float>(
        state, engine_memory::AddressOf(frame) + kAnimationFrameWidthOffset,
        "AnimationFrame width"));
    return 1;
}

int RepentogonAnimationFrameIsVisible(lua_State* state) {
    RequireGameThread(state);
    void* frame = ResolveAnimationFrameView(state, 1);
    const auto visible = ReadOrError<std::uint8_t>(
        state, engine_memory::AddressOf(frame) + kAnimationFrameVisibleOffset,
        "AnimationFrame visibility");
    lua_pushboolean(state, visible != 0);
    return 1;
}

int RepentogonAnimationFrameGetColor(lua_State* state) {
    RequireGameThread(state);
    void* frame = ResolveAnimationFrameView(state, 1);
    const auto color = ReadOrError<EngineColorMod>(
        state, engine_memory::AddressOf(frame) + kAnimationFrameColorOffset,
        "AnimationFrame color");
    PushLuaColorFromEngineColorMod(state, color);
    return 1;
}

int RepentogonNullFrameGetPos(lua_State* state) {
    RequireGameThread(state);
    void* frame = ResolveNullFrameView(state, 1);
    const auto pos = ReadOrError<LuaRuntime::VectorHandle>(
        state, engine_memory::AddressOf(frame) + kNullFramePosOffset,
        "NullFrame position");
    PushLuaVector(state, pos.x, pos.y);
    return 1;
}

int RepentogonNullFrameGetScale(lua_State* state) {
    RequireGameThread(state);
    void* frame = ResolveNullFrameView(state, 1);
    const auto scale = ReadOrError<LuaRuntime::VectorHandle>(
        state, engine_memory::AddressOf(frame) + kNullFrameScaleOffset,
        "NullFrame scale");
    PushLuaVector(state, scale.x, scale.y);
    return 1;
}

int RepentogonAnimationDataGetLength(lua_State* state) {
    RequireGameThread(state);
    void* data = ResolveAnimationDataView(state, 1);
    lua_pushinteger(state, ReadOrError<std::int32_t>(
        state, engine_memory::AddressOf(data) + kAnimationDataLengthOffset,
        "AnimationData length"));
    return 1;
}

int RepentogonAnimationDataGetLayer(lua_State* state) {
    RequireGameThread(state);
    void* data = ResolveAnimationDataView(state, 1);
    const auto id = static_cast<std::int32_t>(luaL_checkinteger(state, 2));
    if (id < 0) {
        lua_pushnil(state);
        return 1;
    }
    void* layer = AnimationLayerById(state, data, id);
    if (layer == nullptr) {
        lua_pushnil(state);
        return 1;
    }
    return PushAnimationLayerView(state, 1, layer, id);
}

int RepentogonAnimationLayerGetFrame(lua_State* state) {
    RequireGameThread(state);
    void* layer = ResolveAnimationLayerView(state, 1);
    const auto layerAddress = engine_memory::AddressOf(layer);
    const auto count = ReadOrError<std::int32_t>(
        state, layerAddress + kAnimationLayerFrameCountOffset,
        "AnimationLayer frame count");
    if (count <= 0) {
        lua_pushnil(state);
        return 1;
    }
    auto requested = static_cast<std::int32_t>(luaL_checkinteger(state, 2));
    if (requested < 0) requested = 0;
    const auto frames = ReadOrError<std::uintptr_t>(
        state, layerAddress + kAnimationLayerFramesOffset,
        "AnimationLayer frame array");
    if (frames == 0) {
        lua_pushnil(state);
        return 1;
    }
    std::int32_t selected = count - 1;
    for (std::int32_t index = 0; index < count; ++index) {
        const auto frame = frames + static_cast<std::uintptr_t>(index) * kAnimationFrameStride;
        if (!Readable(frame, kAnimationFrameStride)) {
            return luaL_error(state, "AnimationLayer frame array is not readable");
        }
        const auto start = ReadOrError<std::int32_t>(
            state, frame + kAnimationFrameStartOffset, "AnimationFrame start frame");
        const auto end = ReadOrError<std::int32_t>(
            state, frame + kAnimationFrameEndOffset, "AnimationFrame end frame");
        if (requested >= start && requested < end) {
            selected = index;
            break;
        }
    }
    void* selectedFrame = engine_memory::AsObject(
        frames + static_cast<std::uintptr_t>(selected) * kAnimationFrameStride);
    if (!Readable(engine_memory::AddressOf(selectedFrame), kAnimationFrameStride)) {
        return luaL_error(state, "AnimationLayer selected frame is not readable");
    }
    return PushAnimationFrameView(state, 1, selectedFrame, selected);
}

int RepentogonLayerStateSetVisible(lua_State* state) {
    RequireGameThread(state);
    void* layer = ResolveLayerStateView(state, 1);
    // Upstream BOOL_CHECK_MODE_NOT_NIL rejects only an explicit nil; a missing
    // argument remains LUA_TNONE and converts to false.
    if (lua_type(state, 2) == LUA_TNIL) {
        return luaL_error(state, "LayerState:SetVisible does not accept nil");
    }
    WriteOrError(state, engine_memory::AddressOf(layer) + kLayerStateVisibleOffset,
                 static_cast<std::uint8_t>(lua_toboolean(state, 2) != 0),
                 "LayerState visibility");
    return 0;
}

int RepentogonLayerStateSetPos(lua_State* state) {
    RequireGameThread(state);
    void* layer = ResolveLayerStateView(state, 1);
    const auto* pos = RequireVectorArgument(state, 2);
    WriteOrError(state, engine_memory::AddressOf(layer) + kLayerStatePosOffset,
                 *pos, "LayerState position");
    return 0;
}

int RepentogonLayerStateGetSpritesheetPath(lua_State* state) {
    RequireGameThread(state);
    void* layer = ResolveLayerStateView(state, 1);
    EngineStringView view{};
    if (!ResolveEngineStringView(
            engine_memory::AddressOf(layer) + kLayerStateSpritesheetPathOffset,
            &view)) {
        return luaL_error(state, "LayerState spritesheet path is unavailable");
    }
    if (view.size == 0) {
        lua_pushliteral(state, "");
        return 1;
    }
    lua_pushlstring(state,
                    static_cast<const char*>(engine_memory::AsObject(view.data)),
                    view.size);
    return 1;
}

int RepentogonLayerStateGetDefaultSpritesheetPath(lua_State* state) {
    RequireGameThread(state);
    void* layer = ResolveLayerStateView(state, 1);
    const auto layerData = ReadOrError<std::uintptr_t>(
        state, engine_memory::AddressOf(layer), "LayerState layer data");
    if (layerData == 0) {
        return luaL_error(state, "LayerState default spritesheet path is unavailable");
    }
    EngineStringView view{};
    if (!ResolveEngineStringView(
            layerData + kLayerDataDefaultSpritesheetPathOffset, &view)) {
        return luaL_error(state, "LayerState default spritesheet path is unavailable");
    }
    if (view.size == 0) {
        lua_pushliteral(state, "");
        return 1;
    }
    lua_pushlstring(state,
                    static_cast<const char*>(engine_memory::AsObject(view.data)),
                    view.size);
    return 1;
}

int RepentogonLayerStateSetSize(lua_State* state) {
    RequireGameThread(state);
    void* layer = ResolveLayerStateView(state, 1);
    const auto* size = RequireVectorArgument(state, 2);
    WriteOrError(state, engine_memory::AddressOf(layer) + kLayerStateSizeOffset,
                 *size, "LayerState size");
    return 0;
}

int RepentogonLayerStateSetCropOffset(lua_State* state) {
    RequireGameThread(state);
    void* layer = ResolveLayerStateView(state, 1);
    const auto* offset = RequireVectorArgument(state, 2);
    WriteOrError(state, engine_memory::AddressOf(layer) + kLayerStateCropOffsetOffset,
                 *offset, "LayerState crop offset");
    return 0;
}

int RepentogonLayerStateSetColor(lua_State* state) {
    RequireGameThread(state);
    void* layer = ResolveLayerStateView(state, 1);
    const auto* color = RequireColorArgument(state, 2);
    const auto engineColor = EngineColorModFromHandle(*color);
    WriteOrError(state, engine_memory::AddressOf(layer) + kLayerStateColorOffset,
                 engineColor, "LayerState color");
    return 0;
}

int RepentogonLayerStateGetBlendMode(lua_State* state) {
    RequireGameThread(state);
    void* layer = ResolveLayerStateView(state, 1);
    void* blend = engine_memory::AsObject(
        engine_memory::AddressOf(layer) + kLayerStateBlendModeOffset);
    if (!Readable(engine_memory::AddressOf(blend), kBlendModeReadableSize)) {
        return luaL_error(state, "LayerState BlendMode is not readable");
    }
    return PushBlendModeView(state, blend);
}

int RepentogonBlendModeGetFlag1(lua_State* state) {
    return BlendFlag(state, kBlendModeFlag1Offset);
}

int RepentogonBlendModeGetFlag2(lua_State* state) {
    return BlendFlag(state, kBlendModeFlag2Offset);
}

int RepentogonBlendModeGetFlag3(lua_State* state) {
    return BlendFlag(state, kBlendModeFlag3Offset);
}

int RepentogonBlendModeGetFlag4(lua_State* state) {
    return BlendFlag(state, kBlendModeFlag4Offset);
}

int RegisterRepentogonSpriteViews(lua_State* state) {
    if (state == nullptr) {
        return 0;
    }

    RegisterMethodClass(state, "AnimationData", kAnimationDataMetatable, "AnimationData");
    RegisterMethodClass(state, "AnimationLayer", kAnimationLayerMetatable, "AnimationLayer");
    RegisterMethodClass(state, "AnimationFrame", kAnimationFrameMetatable, "AnimationFrame");
    RegisterMethodClass(state, "NullFrame", kNullFrameMetatable, "NullFrame");
    RegisterMethodClass(state, "LayerState", kLayerStateMetatable, "LayerState");
    RegisterBlendMode(state);

    PromoteSpriteClassTable(state);
    static_cast<void>(AttachMethodsToMetatable(
        state, LuaRuntime::kSpriteMetatable, "Sprite"));
    return 0;
}

#if !defined(__SWITCH__)
void SetRepentogonSpriteNativeTestBindings(
    RepentogonSpriteNativeTestBindings bindings) noexcept {
    g_NativeTestBindings = bindings;
}
#endif

} // namespace isaac::runtime
