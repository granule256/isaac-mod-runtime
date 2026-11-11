#include "interfaces/lua/procedural_item_api.hpp"

#include "interfaces/lua/class_metadata.hpp"
#include "interfaces/lua/isaac_api.hpp"
#include "interfaces/lua/lua_integer_argument.hpp"
#include "interfaces/lua/object_identity_registry.hpp"
#include "interfaces/lua/owner_binding.hpp"
#include "infrastructure/memory/engine_field_access.hpp"
#include "infrastructure/native/world_content_mutations.hpp"
#include "lua_runtime.hpp"
#include "lua_runtime_state.hpp"

#include <cstddef>
#include <cstdint>
#include <limits>

extern "C" {
#include <lauxlib.h>
}

namespace isaac::runtime {
namespace {

using namespace LuaRuntime;

// Switch build 91C73FDD575061318D68886316AFEAC72388B2AB.
// The manager is the vector at Game+0x345F18; GetProceduralItem @0x448F38
// begins 4101f836092840a94a0109cbe803212a and loads end/begin from x0+8/x0.
// Item wrapper (0x50): +0x00 is the full 8-byte ItemConfig::Item*,
// +0x18 is the target ItemConfig::Item*, +0x38/+0x40/+0x48 are
// effects.begin/end/capacity. Item ctor/dtor @0x444C5C/0x444C80 and
// CreateSpecialProceduralItem @0x447ACC ('ffc304d1...') write those fields.
// The six floats are +0x20 damage, +0x24 fire delay, +0x28 speed, +0x2C range,
// +0x30 shot speed and +0x34 luck; CreateProceduralItem @0x4453E8 sets exactly
// CACHE_DAMAGE/FIREDELAY/SPEED/RANGE/SHOTSPEED/LUCK for those slots.
// ProceduralEffect is 0x68 bytes: type/action at +0/+4, condition data at +8,
// action data at +0x10, trigger scale +0x30 and score +0x60. Init @0x448264
// ('ff8303d1...') and ToString @0x44899C ('fd7bbba9...') access those offsets.
constexpr std::uintptr_t kManagerOffset = 0x345F18;
constexpr std::uintptr_t kManagerBeginOffset = 0x00;
constexpr std::uintptr_t kManagerEndOffset = 0x08;
constexpr std::uintptr_t kManagerCapacityOffset = 0x10;
constexpr std::size_t kManagerEntryBytes = sizeof(std::uintptr_t);

constexpr std::size_t kItemWrapperBytes = 0x50;
constexpr std::uintptr_t kItemTargetOffset = 0x18;
constexpr std::uintptr_t kItemEffectsBeginOffset = 0x38;
constexpr std::uintptr_t kItemEffectsEndOffset = 0x40;
constexpr std::uintptr_t kItemEffectsCapacityOffset = 0x48;
constexpr std::size_t kEffectBytes = 0x68;

constexpr std::uintptr_t kEffectConditionTypeOffset = 0x00;
constexpr std::uintptr_t kEffectActionTypeOffset = 0x04;
constexpr std::uintptr_t kEffectConditionDataOffset = 0x08;
constexpr std::uintptr_t kEffectActionDataOffset = 0x10;

constexpr char kManagerMetatable[] = "IsaacRuntime.ProceduralItemManager";
constexpr char kItemMetatable[] = "IsaacRuntime.ProceduralItem";
constexpr char kEffectMetatable[] = "IsaacRuntime.ProceduralEffect";
constexpr char kManagerOwner[] = "ProceduralItemManager";
constexpr char kItemOwner[] = "ProceduralItem";
constexpr char kEffectOwner[] = "ProceduralEffect";

struct VectorView {
    std::uintptr_t begin{};
    std::uintptr_t end{};
    std::size_t count{};
};

struct ItemHandle {
    std::uintptr_t manager{};
    std::uintptr_t wrapper{};
    std::uint32_t index{};
    std::uint32_t reserved{};
    std::uint64_t worldEpoch{};
};

struct EffectHandle {
    std::uintptr_t manager{};
    std::uintptr_t wrapper{};
    std::uintptr_t effect{};
    std::uint32_t itemIndex{};
    std::uint32_t effectIndex{};
    std::uint64_t worldEpoch{};
};

enum class Lookup : std::uint8_t {
    Ok,
    Unavailable,
    Malformed,
    OutOfRange,
    Stale,
};

#if !defined(__SWITCH__)
std::uintptr_t gHostManager{};
#endif

bool ReadPointer(std::uintptr_t address, std::uintptr_t* value) noexcept {
    return value != nullptr &&
           engine_memory::ReadAt(address, value, &engine_memory::EngineMemoryReadable);
}

bool RequireGameThread(lua_State* state) {
    if (LuaRuntime::IsOnGameThread()) {
        return true;
    }
    static_cast<void>(luaL_error(state, "procedural item access requires the game thread"));
    return false;
}

template <typename T>
bool ReadAtOffset(std::uintptr_t base, std::uintptr_t offset, T* value) noexcept {
    if (value == nullptr || offset > UINTPTR_MAX - base) {
        return false;
    }
    return engine_memory::ReadAt(base + offset, value,
                                 &engine_memory::EngineMemoryReadable);
}

bool ReadVector(std::uintptr_t owner, std::uintptr_t beginOffset, std::uintptr_t endOffset,
                std::uintptr_t capacityOffset, std::size_t entryBytes,
                VectorView* view) noexcept {
    if (view == nullptr || entryBytes == 0) {
        return false;
    }
    std::uintptr_t begin{};
    std::uintptr_t end{};
    std::uintptr_t capacity{};
    if (!ReadAtOffset(owner, beginOffset, &begin) ||
        !ReadAtOffset(owner, endOffset, &end) ||
        !ReadAtOffset(owner, capacityOffset, &capacity)) {
        return false;
    }
    if (begin == 0 && end == 0 && capacity == 0) {
        *view = {};
        return true;
    }
    if (begin == 0 || end == 0 || capacity == 0 ||
        (begin & (alignof(std::uintptr_t) - 1)) != 0 ||
        (end & (alignof(std::uintptr_t) - 1)) != 0 ||
        (capacity & (alignof(std::uintptr_t) - 1)) != 0 ||
        end < begin || capacity < end) {
        return false;
    }
    const std::uintptr_t bytes = end - begin;
    const std::uintptr_t capacityBytes = capacity - begin;
    if (bytes % entryBytes != 0 || capacityBytes % entryBytes != 0 ||
        bytes / entryBytes > std::numeric_limits<std::uint32_t>::max() ||
        (bytes != 0 &&
         !engine_memory::EngineMemoryReadable(begin, static_cast<std::size_t>(bytes)))) {
        return false;
    }
    *view = {begin, end, static_cast<std::size_t>(bytes / entryBytes)};
    return true;
}

Lookup ResolveManager(std::uintptr_t* manager) noexcept {
    if (manager == nullptr) {
        return Lookup::Malformed;
    }
#if !defined(__SWITCH__)
    if (gHostManager != 0) {
        *manager = gHostManager;
        return Lookup::Ok;
    }
#endif
    const std::uintptr_t slot = GameOwnerSlot();
    std::uintptr_t owner{};
    std::uintptr_t game{};
    if (slot == 0 || !engine_memory::LoadPointer(slot, &owner,
                                                  &engine_memory::EngineMemoryReadable)) {
        return Lookup::Unavailable;
    }
    if (owner == 0) {
        return Lookup::Unavailable;
    }
    if (!engine_memory::LoadPointer(owner, &game,
                                    &engine_memory::EngineMemoryReadable)) {
        return Lookup::Unavailable;
    }
    if (game == 0 || game > UINTPTR_MAX - kManagerOffset) {
        return Lookup::Unavailable;
    }
    if (!engine_memory::EngineMemoryReadable(game + kManagerOffset, 0x18)) {
        return Lookup::Unavailable;
    }
    *manager = game + kManagerOffset;
    return Lookup::Ok;
}

Lookup ReadManagerItems(std::uintptr_t manager, VectorView* items) noexcept {
    if (manager == 0 ||
        !engine_memory::EngineMemoryReadable(manager, 0x18) ||
        !ReadVector(manager, kManagerBeginOffset, kManagerEndOffset,
                    kManagerCapacityOffset, kManagerEntryBytes, items)) {
        return Lookup::Malformed;
    }
    return Lookup::Ok;
}

Lookup ResolveItemByIndex(std::uint32_t index, std::uintptr_t* manager,
                          std::uintptr_t* wrapper) noexcept {
    if (manager == nullptr || wrapper == nullptr) {
        return Lookup::Malformed;
    }
    std::uintptr_t currentManager{};
    Lookup result = ResolveManager(&currentManager);
    if (result != Lookup::Ok) {
        return result;
    }
    VectorView items{};
    result = ReadManagerItems(currentManager, &items);
    if (result != Lookup::Ok) {
        return result;
    }
    if (index >= items.count) {
        return Lookup::OutOfRange;
    }
    std::uintptr_t candidate{};
    if (!ReadPointer(items.begin + static_cast<std::size_t>(index) * kManagerEntryBytes,
                     &candidate)) {
        return Lookup::Malformed;
    }
    if (candidate == 0 ||
        (candidate & (alignof(std::uintptr_t) - 1)) != 0) {
        return Lookup::Malformed;
    }
    *manager = currentManager;
    *wrapper = candidate;
    return Lookup::Ok;
}

Lookup ReadItemEffects(std::uintptr_t wrapper, VectorView* effects) noexcept {
    if (wrapper == 0 ||
        !engine_memory::EngineMemoryReadable(wrapper, kItemWrapperBytes) ||
        !ReadVector(wrapper, kItemEffectsBeginOffset, kItemEffectsEndOffset,
                    kItemEffectsCapacityOffset, sizeof(std::uintptr_t), effects)) {
        return Lookup::Malformed;
    }
    return Lookup::Ok;
}

Lookup ValidateItemHandle(const ItemHandle* handle, std::uintptr_t* wrapper,
                          VectorView* effects) noexcept {
    if (!LuaRuntime::IsOnGameThread()) {
        return Lookup::Unavailable;
    }
    if (handle == nullptr) {
        return Lookup::Malformed;
    }
    if (handle->worldEpoch != CaptureWorldContentSnapshot().worldEpoch) {
        return Lookup::Stale;
    }
    std::uintptr_t manager{};
    std::uintptr_t current{};
    Lookup result = ResolveItemByIndex(handle->index, &manager, &current);
    if (result != Lookup::Ok) {
        return result;
    }
    if (manager != handle->manager || current != handle->wrapper) {
        return Lookup::Stale;
    }
    result = ReadItemEffects(current, effects);
    if (result != Lookup::Ok) {
        return result;
    }
    *wrapper = current;
    return Lookup::Ok;
}

Lookup ValidateEffectHandle(const EffectHandle* handle, std::uintptr_t* effect) noexcept {
    if (!LuaRuntime::IsOnGameThread()) {
        return Lookup::Unavailable;
    }
    if (handle == nullptr || effect == nullptr) {
        return Lookup::Malformed;
    }
    if (handle->worldEpoch != CaptureWorldContentSnapshot().worldEpoch) {
        return Lookup::Stale;
    }
    std::uintptr_t manager{};
    std::uintptr_t wrapper{};
    VectorView effects{};
    Lookup result = ResolveItemByIndex(handle->itemIndex, &manager, &wrapper);
    if (result != Lookup::Ok) {
        return result;
    }
    if (manager != handle->manager || wrapper != handle->wrapper) {
        return Lookup::Stale;
    }
    result = ReadItemEffects(wrapper, &effects);
    if (result != Lookup::Ok) {
        return result;
    }
    if (handle->effectIndex >= effects.count) {
        return Lookup::Stale;
    }
    std::uintptr_t current{};
    if (!ReadPointer(effects.begin + static_cast<std::size_t>(handle->effectIndex) *
                                         sizeof(std::uintptr_t),
                     &current)) {
        return Lookup::Malformed;
    }
    if (current != handle->effect) {
        return Lookup::Stale;
    }
    if (current == 0 || (current & (alignof(std::uintptr_t) - 1)) != 0 ||
        !engine_memory::EngineMemoryReadable(current, kEffectBytes)) {
        return Lookup::Malformed;
    }
    *effect = current;
    return Lookup::Ok;
}

int ErrorForLookup(lua_State* state, Lookup lookup, const char* reference) {
    switch (lookup) {
        case Lookup::Unavailable:
            return luaL_error(state, "%s native manager is unavailable", reference);
        case Lookup::Malformed:
            return luaL_error(state, "%s native layout is malformed", reference);
        case Lookup::OutOfRange:
        case Lookup::Stale:
            return luaL_error(state, "%s reference is no longer available", reference);
        case Lookup::Ok:
            break;
    }
    return luaL_error(state, "%s native reference is invalid", reference);
}

void PushItemHandle(lua_State* state, std::uintptr_t manager, std::uintptr_t wrapper,
                    std::uint32_t index) {
    auto* handle = static_cast<ItemHandle*>(lua_newuserdata(state, sizeof(ItemHandle)));
    *handle = {manager, wrapper, index, 0,
               CaptureWorldContentSnapshot().worldEpoch};
    luaL_getmetatable(state, kItemMetatable);
    lua_setmetatable(state, -2);
}

void PushEffectHandle(lua_State* state, std::uintptr_t manager, std::uintptr_t wrapper,
                      std::uintptr_t effect,
                      std::uint32_t itemIndex, std::uint32_t effectIndex) {
    auto* handle =
        static_cast<EffectHandle*>(lua_newuserdata(state, sizeof(EffectHandle)));
    *handle = {manager, wrapper, effect, itemIndex, effectIndex,
               CaptureWorldContentSnapshot().worldEpoch};
    luaL_getmetatable(state, kEffectMetatable);
    lua_setmetatable(state, -2);
}

ItemHandle* CheckItem(lua_State* state) {
    return static_cast<ItemHandle*>(luaL_checkudata(state, 1, kItemMetatable));
}

EffectHandle* CheckEffect(lua_State* state) {
    return static_cast<EffectHandle*>(luaL_checkudata(state, 1, kEffectMetatable));
}

std::uintptr_t ValidateItem(lua_State* state, VectorView* effects) {
    auto* handle = CheckItem(state);
    std::uintptr_t wrapper{};
    const Lookup result = ValidateItemHandle(handle, &wrapper, effects);
    if (result != Lookup::Ok) {
        static_cast<void>(ErrorForLookup(state, result, "ProceduralItem"));
    }
    return wrapper;
}

std::uintptr_t ValidateEffect(lua_State* state) {
    auto* handle = CheckEffect(state);
    std::uintptr_t effect{};
    const Lookup result = ValidateEffectHandle(handle, &effect);
    if (result != Lookup::Ok) {
        static_cast<void>(ErrorForLookup(state, result, "ProceduralEffect"));
    }
    return effect;
}

void PushIntegerField(lua_State* state, std::uintptr_t object, std::uintptr_t offset,
                      const char* field) {
    std::int32_t value{};
    if (!ReadAtOffset(object, offset, &value)) {
        static_cast<void>(luaL_error(state, "ProceduralEffect.%s is unreadable", field));
        return;
    }
    lua_pushinteger(state, static_cast<lua_Integer>(value));
    lua_setfield(state, -2, field);
}

void PushFloatField(lua_State* state, std::uintptr_t object, std::uintptr_t offset,
                    const char* field) {
    float value{};
    if (!ReadAtOffset(object, offset, &value)) {
        static_cast<void>(luaL_error(state, "ProceduralEffect.%s is unreadable", field));
        return;
    }
    lua_pushnumber(state, static_cast<lua_Number>(value));
    lua_setfield(state, -2, field);
}

void PushU64Field(lua_State* state, std::uintptr_t object, std::uintptr_t offset,
                  const char* field) {
    std::uint64_t value{};
    if (!ReadAtOffset(object, offset, &value)) {
        static_cast<void>(luaL_error(state, "ProceduralEffect.%s is unreadable", field));
        return;
    }
    lua_pushinteger(state, static_cast<lua_Integer>(value));
    lua_setfield(state, -2, field);
}

int ItemFloat(lua_State* state, std::uintptr_t offset) {
    if (lua_gettop(state) != 1) {
        return luaL_error(state, "ProceduralItem getter accepts no arguments");
    }
    VectorView effects{};
    const std::uintptr_t wrapper = ValidateItem(state, &effects);
    float value{};
    if (!ReadAtOffset(wrapper, offset, &value)) {
        return luaL_error(state, "ProceduralItem native value is unreadable");
    }
    lua_pushnumber(state, static_cast<lua_Number>(value));
    return 1;
}

int Readonly(lua_State* state) {
    return luaL_error(state, "native ProceduralItem objects are read-only");
}

std::uintptr_t ItemIdentity(lua_State* state, int index) noexcept {
    auto* handle = static_cast<ItemHandle*>(luaL_testudata(state, index, kItemMetatable));
    if (handle == nullptr || lua_rawlen(state, index) != sizeof(ItemHandle)) {
        return 0;
    }
    VectorView effects{};
    std::uintptr_t wrapper{};
    return ValidateItemHandle(handle, &wrapper, &effects) == Lookup::Ok ? wrapper : 0;
}

std::uintptr_t EffectIdentity(lua_State* state, int index) noexcept {
    auto* handle =
        static_cast<EffectHandle*>(luaL_testudata(state, index, kEffectMetatable));
    if (handle == nullptr || lua_rawlen(state, index) != sizeof(EffectHandle)) {
        return 0;
    }
    std::uintptr_t effect{};
    return ValidateEffectHandle(handle, &effect) == Lookup::Ok ? effect : 0;
}

void CreateObjectMetatable(lua_State* state, const char* metatable,
                           NativeObjectIdentityResolver identity,
                           std::size_t (*attach)(lua_State*) noexcept) {
    luaL_newmetatable(state, metatable);
    if (!RegisterNativeObjectIdentity(state, -1, identity)) {
        luaL_error(state, "native identity resolver conflicts for %s", metatable);
    }
    lua_newtable(state);
    static_cast<void>(attach(state));
    CopyClassMethods(state, -2, -1);
    lua_setfield(state, -2, "__methods");
    lua_pushcfunction(state, NativeClassMethodIndex);
    lua_setfield(state, -2, "__index");
    lua_pushcfunction(state, Readonly);
    lua_setfield(state, -2, "__newindex");
    lua_pushstring(state, metatable == kItemMetatable ? "ProceduralItem"
                                                       : "ProceduralEffect");
    lua_setfield(state, -2, "__type");
    lua_pushstring(state, metatable == kItemMetatable ? "ProceduralItem"
                                                       : "ProceduralEffect");
    lua_setfield(state, -2, "__class");
    lua_pop(state, 1);
}

}  // namespace

std::size_t AttachProceduralItemManagerMethods(lua_State* state) noexcept {
    return AttachOwnerMethods(state, kManagerOwner, nullptr, 0);
}

std::size_t AttachProceduralItemMethods(lua_State* state) noexcept {
    return AttachOwnerMethods(state, kItemOwner, nullptr, 0);
}

std::size_t AttachProceduralEffectMethods(lua_State* state) noexcept {
    return AttachOwnerMethods(state, kEffectOwner, nullptr, 0);
}

int ProceduralItemManagerGetProceduralItem(lua_State* state) {
    if (!RequireGameThread(state)) return 0;
    lua_Integer requested = 0;
    if (lua_gettop(state) != 1 || !IntegerArgumentAt(state, 1, &requested)) {
        return luaL_error(state, "ProceduralItemManager.GetProceduralItem expects one integer index");
    }
    if (requested < 0 ||
        static_cast<std::uint64_t>(requested) >
            static_cast<std::uint64_t>(std::numeric_limits<std::int32_t>::max())) {
        lua_pushnil(state);
        return 1;
    }
    const auto index = static_cast<std::uint32_t>(requested);
    std::uintptr_t manager{};
    std::uintptr_t wrapper{};
    const Lookup result = ResolveItemByIndex(index, &manager, &wrapper);
    if (result == Lookup::OutOfRange) {
        lua_pushnil(state);
        return 1;
    }
    if (result != Lookup::Ok) {
        return ErrorForLookup(state, result, "ProceduralItemManager");
    }
    VectorView effects{};
    if (ReadItemEffects(wrapper, &effects) != Lookup::Ok) {
        return ErrorForLookup(state, Lookup::Malformed, "ProceduralItem");
    }
    PushItemHandle(state, manager, wrapper, index);
    return 1;
}

int ProceduralItemGetTargetItem(lua_State* state) {
    if (!RequireGameThread(state)) return 0;
    if (lua_gettop(state) != 1) {
        return luaL_error(state, "ProceduralItem:GetTargetItem accepts no arguments");
    }
    VectorView effects{};
    const std::uintptr_t wrapper = ValidateItem(state, &effects);
    std::uintptr_t target{};
    if (!ReadAtOffset(wrapper, kItemTargetOffset, &target)) {
        return luaL_error(state, "ProceduralItem target is unreadable");
    }
    if (target == 0) {
        lua_pushnil(state);
        return 1;
    }
    if ((target & (alignof(std::uintptr_t) - 1)) != 0 ||
        !engine_memory::EngineMemoryReadable(target, sizeof(std::uintptr_t))) {
        return luaL_error(state, "ProceduralItem target pointer is malformed");
    }
    auto* handle = static_cast<ItemHandle*>(lua_touserdata(state, 1));
    if (!PushProceduralTargetItemHandle(state, target, handle->manager, wrapper,
                                        handle->index)) {
        return luaL_error(state,
                          "ProceduralItem target does not belong to the current ItemConfig");
    }
    return 1;
}

int ProceduralItemGetEffectCount(lua_State* state) {
    if (!RequireGameThread(state)) return 0;
    if (lua_gettop(state) != 1) {
        return luaL_error(state, "ProceduralItem:GetEffectCount accepts no arguments");
    }
    VectorView effects{};
    static_cast<void>(ValidateItem(state, &effects));
    lua_pushinteger(state, static_cast<lua_Integer>(effects.count));
    return 1;
}

int ProceduralItemGetEffect(lua_State* state) {
    if (!RequireGameThread(state)) return 0;
    lua_Integer requested = 0;
    if (lua_gettop(state) != 2 || !IntegerArgumentAt(state, 2, &requested)) {
        return luaL_error(state, "ProceduralItem:GetEffect expects one integer index");
    }
    if (requested < 0 ||
        static_cast<std::uint64_t>(requested) >
            static_cast<std::uint64_t>(std::numeric_limits<std::int32_t>::max())) {
        lua_pushnil(state);
        return 1;
    }
    VectorView effects{};
    const std::uintptr_t wrapper = ValidateItem(state, &effects);
    const auto index = static_cast<std::uint64_t>(requested);
    if (index >= effects.count) {
        lua_pushnil(state);
        return 1;
    }
    std::uintptr_t effect{};
    if (!ReadPointer(effects.begin + static_cast<std::size_t>(index) * sizeof(std::uintptr_t),
                     &effect)) {
        return ErrorForLookup(state, Lookup::Malformed, "ProceduralEffect");
    }
    if (effect == 0 || (effect & (alignof(std::uintptr_t) - 1)) != 0 ||
        !engine_memory::EngineMemoryReadable(effect, kEffectBytes)) {
        return ErrorForLookup(state, Lookup::Malformed, "ProceduralEffect");
    }
    auto* handle = static_cast<ItemHandle*>(lua_touserdata(state, 1));
    PushEffectHandle(state, handle->manager, wrapper, effect, handle->index,
                     static_cast<std::uint32_t>(index));
    return 1;
}

int ProceduralItemGetSpeed(lua_State* state) {
    if (!RequireGameThread(state)) return 0;
    return ItemFloat(state, 0x28);
}

int ProceduralItemGetFireDelay(lua_State* state) {
    if (!RequireGameThread(state)) return 0;
    return ItemFloat(state, 0x24);
}

int ProceduralItemGetDamage(lua_State* state) {
    if (!RequireGameThread(state)) return 0;
    return ItemFloat(state, 0x20);
}

int ProceduralItemGetRange(lua_State* state) {
    if (!RequireGameThread(state)) return 0;
    return ItemFloat(state, 0x2C);
}

int ProceduralItemGetShotSpeed(lua_State* state) {
    if (!RequireGameThread(state)) return 0;
    return ItemFloat(state, 0x30);
}

int ProceduralItemGetLuck(lua_State* state) {
    if (!RequireGameThread(state)) return 0;
    return ItemFloat(state, 0x34);
}

int ProceduralEffectGetConditionType(lua_State* state) {
    if (!RequireGameThread(state)) return 0;
    if (lua_gettop(state) != 1) {
        return luaL_error(state, "ProceduralEffect:GetConditionType accepts no arguments");
    }
    const std::uintptr_t effect = ValidateEffect(state);
    std::int32_t value{};
    if (!ReadAtOffset(effect, kEffectConditionTypeOffset, &value)) {
        return luaL_error(state, "ProceduralEffect condition type is unreadable");
    }
    lua_pushinteger(state, static_cast<lua_Integer>(value));
    return 1;
}

int ProceduralEffectGetConditionProperty(lua_State* state) {
    if (!RequireGameThread(state)) return 0;
    if (lua_gettop(state) != 1) {
        return luaL_error(state, "ProceduralEffect:GetConditionProperty accepts no arguments");
    }
    const std::uintptr_t effect = ValidateEffect(state);
    std::int32_t condition{};
    if (!ReadAtOffset(effect, kEffectConditionTypeOffset, &condition)) {
        return luaL_error(state, "ProceduralEffect condition type is unreadable");
    }
    lua_newtable(state);
    if (condition == 6) {
        std::int16_t variant{};
        std::int16_t type{};
        if (!ReadAtOffset(effect, kEffectConditionDataOffset + 4, &variant) ||
            !ReadAtOffset(effect, kEffectConditionDataOffset + 6, &type)) {
            return luaL_error(state, "ProceduralEffect condition data is unreadable");
        }
        lua_pushinteger(state, type);
        lua_setfield(state, -2, "type");
        lua_pushinteger(state, variant);
        lua_setfield(state, -2, "variant");
    }
    return 1;
}

int ProceduralEffectGetActionType(lua_State* state) {
    if (!RequireGameThread(state)) return 0;
    if (lua_gettop(state) != 1) {
        return luaL_error(state, "ProceduralEffect:GetActionType accepts no arguments");
    }
    const std::uintptr_t effect = ValidateEffect(state);
    std::int32_t value{};
    if (!ReadAtOffset(effect, kEffectActionTypeOffset, &value)) {
        return luaL_error(state, "ProceduralEffect action type is unreadable");
    }
    lua_pushinteger(state, static_cast<lua_Integer>(value));
    return 1;
}

int ProceduralEffectGetActionProperty(lua_State* state) {
    if (!RequireGameThread(state)) return 0;
    if (lua_gettop(state) != 1) {
        return luaL_error(state, "ProceduralEffect:GetActionProperty accepts no arguments");
    }
    const std::uintptr_t effect = ValidateEffect(state);
    std::int32_t action{};
    if (!ReadAtOffset(effect, kEffectActionTypeOffset, &action)) {
        return luaL_error(state, "ProceduralEffect action type is unreadable");
    }
    lua_newtable(state);
    switch (action) {
        case 0:
        case 1:
            PushIntegerField(state, effect, kEffectActionDataOffset, "id");
            return 1;
        case 2: {
            std::int16_t fromVariant{}, fromType{}, toVariant{}, toType{};
            if (!ReadAtOffset(effect, kEffectActionDataOffset, &fromVariant) ||
                !ReadAtOffset(effect, kEffectActionDataOffset + 2, &fromType) ||
                !ReadAtOffset(effect, kEffectActionDataOffset + 4, &toVariant) ||
                !ReadAtOffset(effect, kEffectActionDataOffset + 6, &toType)) {
                return luaL_error(state, "ProceduralEffect convert action data is unreadable");
            }
            lua_pushinteger(state, fromType);
            lua_setfield(state, -2, "fromType");
            lua_pushinteger(state, fromVariant);
            lua_setfield(state, -2, "fromVariant");
            lua_pushinteger(state, toType);
            lua_setfield(state, -2, "toType");
            lua_pushinteger(state, toVariant);
            lua_setfield(state, -2, "toVariant");
            return 1;
        }
        case 3:
            PushFloatField(state, effect, kEffectActionDataOffset + 8, "radius");
            PushFloatField(state, effect, kEffectActionDataOffset + 0xC, "damage");
            PushU64Field(state, effect, kEffectActionDataOffset + 0x10, "flags1");
            PushU64Field(state, effect, kEffectActionDataOffset + 0x18, "flags2");
            return 1;
        case 4: {
            std::int16_t variant{};
            std::int16_t type{};
            if (!ReadAtOffset(effect, kEffectActionDataOffset, &variant) ||
                !ReadAtOffset(effect, kEffectActionDataOffset + 2, &type)) {
                return luaL_error(state, "ProceduralEffect spawn action data is unreadable");
            }
            lua_pushinteger(state, type);
            lua_setfield(state, -2, "type");
            lua_pushinteger(state, variant);
            lua_setfield(state, -2, "variant");
            return 1;
        }
        case 5:
            {
                // Upstream LuaProceduralEffect.cpp applies these two display scales.
                float scale{};
                float radius{};
                if (!ReadAtOffset(effect, kEffectActionDataOffset, &scale) ||
                    !ReadAtOffset(effect, kEffectActionDataOffset + 0xC, &radius)) {
                    return luaL_error(state,
                                      "ProceduralEffect fart action data is unreadable");
                }
                lua_pushnumber(state, static_cast<lua_Number>(scale * 6.0f));
                lua_setfield(state, -2, "scale");
                lua_pushnumber(state, static_cast<lua_Number>(radius * 6.0f / 85.0f));
                lua_setfield(state, -2, "radius");
            }
            return 1;
        default:
            return 1;
    }
}

int RegisterProceduralItemApi(lua_State* state) {
    if (state == nullptr) {
        return 0;
    }
    lua_getglobal(state, kManagerOwner);
    const bool exists = !lua_isnil(state, -1);
    lua_pop(state, 1);
    if (exists) {
        return luaL_error(state, "ProceduralItemManager is already registered");
    }

    luaL_newmetatable(state, kManagerMetatable);
    lua_pushstring(state, kManagerOwner);
    lua_setfield(state, -2, "__type");
    lua_pushstring(state, kManagerOwner);
    lua_setfield(state, -2, "__class");
    lua_pop(state, 1);

    lua_newtable(state);
    static_cast<void>(AttachProceduralItemManagerMethods(state));
    luaL_getmetatable(state, kManagerMetatable);
    lua_setmetatable(state, -2);
    lua_setglobal(state, kManagerOwner);

    CreateObjectMetatable(state, kItemMetatable, &ItemIdentity,
                          &AttachProceduralItemMethods);
    CreateObjectMetatable(state, kEffectMetatable, &EffectIdentity,
                          &AttachProceduralEffectMethods);
    return 0;
}

bool ValidateProceduralTargetItem(std::uintptr_t manager, std::uintptr_t expectedWrapper,
                                  std::uint32_t index,
                                  std::uint64_t worldEpoch,
                                  std::uintptr_t item) noexcept {
    if (!LuaRuntime::IsOnGameThread() ||
        manager == 0 || expectedWrapper == 0 || item == 0 ||
        worldEpoch != CaptureWorldContentSnapshot().worldEpoch) {
        return false;
    }
    std::uintptr_t currentManager{};
    std::uintptr_t wrapper{};
    if (ResolveItemByIndex(index, &currentManager, &wrapper) != Lookup::Ok ||
        currentManager != manager || wrapper != expectedWrapper) {
        return false;
    }
    std::uintptr_t target{};
    return ReadAtOffset(wrapper, kItemTargetOffset, &target) && target == item;
}

#if !defined(__SWITCH__)
void SetProceduralItemManagerForHostTesting(std::uintptr_t manager) noexcept {
    gHostManager = manager;
}
#endif

}  // namespace isaac::runtime
