"""ProceduralItemManager/Item/Effect behavior over the Switch-native layout."""

from __future__ import annotations

import re
import subprocess
import tempfile
import unittest
from pathlib import Path

from . import test_support


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "runtime/source"
HEADER = ROOT / "runtime/src/interfaces/lua/procedural_item_api.hpp"
IMPLEMENTATION = ROOT / "runtime/src/interfaces/lua/procedural_item_api.cpp"

HANDLERS = (
    "ProceduralItemManagerGetProceduralItem",
    "ProceduralItemGetTargetItem",
    "ProceduralItemGetEffectCount",
    "ProceduralItemGetEffect",
    "ProceduralItemGetSpeed",
    "ProceduralItemGetFireDelay",
    "ProceduralItemGetDamage",
    "ProceduralItemGetRange",
    "ProceduralItemGetShotSpeed",
    "ProceduralItemGetLuck",
    "ProceduralEffectGetConditionType",
    "ProceduralEffectGetConditionProperty",
    "ProceduralEffectGetActionType",
    "ProceduralEffectGetActionProperty",
)


DRIVER = r'''
#include "interfaces/lua/isaac_api.hpp"
#include "interfaces/lua/procedural_item_api.hpp"
#include "interfaces/lua/repentogon_environment.hpp"
#include "infrastructure/memory/engine_field_access.hpp"
#include "infrastructure/native/world_content_mutations.hpp"
#include "lua_object_handles.hpp"
#include "lua_runtime.hpp"
#include "lua_runtime_state.hpp"

extern "C" {
#include <lauxlib.h>
#include <lualib.h>
}

#include <array>
#include <cassert>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <limits>
#include <thread>

using namespace isaac::runtime;

namespace {

constexpr const char* kItemMt = "IsaacRuntime.ItemConfig_Item";

struct Manager {
    std::uintptr_t begin{};
    std::uintptr_t end{};
    std::uintptr_t capacity{};
};

struct Wrapper {
    alignas(8) std::array<unsigned char, 0x50> bytes{};

    void Pointer(std::size_t offset, std::uintptr_t value) {
        std::memcpy(bytes.data() + offset, &value, sizeof(value));
    }
    void U32(std::size_t offset, std::uint32_t value) {
        std::memcpy(bytes.data() + offset, &value, sizeof(value));
    }
    void F32(std::size_t offset, float value) {
        std::memcpy(bytes.data() + offset, &value, sizeof(value));
    }
    std::uintptr_t Pointer(std::size_t offset) const {
        std::uintptr_t value{};
        std::memcpy(&value, bytes.data() + offset, sizeof(value));
        return value;
    }
};

struct Effect {
    alignas(8) std::array<unsigned char, 0x68> bytes{};

    void U32(std::size_t offset, std::uint32_t value) {
        std::memcpy(bytes.data() + offset, &value, sizeof(value));
    }
    void I16Pair(std::size_t offset, std::int16_t first, std::int16_t second) {
        std::memcpy(bytes.data() + offset, &first, sizeof(first));
        std::memcpy(bytes.data() + offset + sizeof(first), &second, sizeof(second));
    }
    void F32(std::size_t offset, float value) {
        std::memcpy(bytes.data() + offset, &value, sizeof(value));
    }
    void U64(std::size_t offset, std::uint64_t value) {
        std::memcpy(bytes.data() + offset, &value, sizeof(value));
    }
};

struct Fixture {
    alignas(8) Manager manager{};
    alignas(8) std::array<std::uintptr_t, 2> items{};
    alignas(8) Wrapper wrapper0{};
    alignas(8) Wrapper wrapper1{};
    alignas(8) std::array<unsigned char, 0xF8> targetConfig{};
    alignas(8) std::array<unsigned char, 0xF8> fakeTarget{};
    alignas(8) std::array<std::uintptr_t, 8> collectibleItems{};
    alignas(8) std::array<std::uintptr_t, 4> trinketItems{};
    alignas(8) std::array<std::uintptr_t, 6> effectPointers{};
    alignas(8) std::array<Effect, 6> effects{};
};

Fixture fixture{};
Manager otherManager{};
alignas(8) std::array<std::uintptr_t, 2> otherItems{};
alignas(8) std::array<unsigned char, 0xAAC650> module{};
alignas(8) std::uintptr_t managerSlot{};
alignas(8) std::array<unsigned char, 0x36578> manager{};

constexpr std::uintptr_t kManagerGlobalSlotOffset = 0xAAC648;
constexpr std::uintptr_t kManagerItemConfigOffset = 0x36538;
constexpr std::uintptr_t kCollectibleBeginOffset = 0x00;
constexpr std::uintptr_t kCollectibleEndOffset = 0x08;
constexpr std::uintptr_t kTrinketBeginOffset = 0x18;
constexpr std::uintptr_t kTrinketEndOffset = 0x20;

void PutPointer(unsigned char* base, std::size_t offset, std::uintptr_t value) {
    std::memcpy(base + offset, &value, sizeof(value));
}

void PutU32(unsigned char* base, std::size_t offset, std::uint32_t value) {
    std::memcpy(base + offset, &value, sizeof(value));
}

void SetManager(Manager* manager, std::array<std::uintptr_t, 2>* items, std::size_t count) {
    const auto begin = reinterpret_cast<std::uintptr_t>(items->data());
    manager->begin = count ? begin : 0;
    manager->end = count ? begin + count * sizeof(std::uintptr_t) : 0;
    manager->capacity = manager->end;
}

void SetManagerRaw(Manager* manager, std::uintptr_t* items, std::size_t count) {
    const auto begin = reinterpret_cast<std::uintptr_t>(items);
    manager->begin = count ? begin : 0;
    manager->end = count ? begin + count * sizeof(std::uintptr_t) : 0;
    manager->capacity = manager->end;
}

void ResetFixture() {
    fixture = {};
    otherManager = {};
    otherItems = {};
    module.fill(0);
    manager.fill(0);
    managerSlot = reinterpret_cast<std::uintptr_t>(manager.data());
    PutPointer(module.data(), kManagerGlobalSlotOffset,
               reinterpret_cast<std::uintptr_t>(&managerSlot));
    auto* config = manager.data() + kManagerItemConfigOffset;
    fixture.collectibleItems[3] = reinterpret_cast<std::uintptr_t>(fixture.targetConfig.data());
    PutPointer(config, kCollectibleBeginOffset,
               reinterpret_cast<std::uintptr_t>(fixture.collectibleItems.data()));
    PutPointer(config, kCollectibleEndOffset,
               reinterpret_cast<std::uintptr_t>(fixture.collectibleItems.data() +
                                                fixture.collectibleItems.size()));
    PutPointer(config, kTrinketBeginOffset,
               reinterpret_cast<std::uintptr_t>(fixture.trinketItems.data()));
    PutPointer(config, kTrinketEndOffset,
               reinterpret_cast<std::uintptr_t>(fixture.trinketItems.data() +
                                                fixture.trinketItems.size()));
    PutU32(fixture.targetConfig.data(), 0x00, 1);
    PutU32(fixture.targetConfig.data(), 0x04, 3);
    PutU32(fixture.fakeTarget.data(), 0x00, 1);
    PutU32(fixture.fakeTarget.data(), 0x04, 3);

    fixture.wrapper0.Pointer(0x00,
                             reinterpret_cast<std::uintptr_t>(fixture.targetConfig.data()));
    fixture.wrapper0.U32(0x08, 17);
    fixture.wrapper0.Pointer(0x18,
                             reinterpret_cast<std::uintptr_t>(fixture.targetConfig.data()));
    fixture.wrapper0.F32(0x20, 1.25f);
    fixture.wrapper0.F32(0x24, 2.5f);
    fixture.wrapper0.F32(0x28, 3.75f);
    fixture.wrapper0.F32(0x2C, 4.25f);
    fixture.wrapper0.F32(0x30, 5.5f);
    fixture.wrapper0.F32(0x34, 6.75f);
    for (std::size_t index = 0; index < fixture.effects.size(); ++index) {
        fixture.effectPointers[index] =
            reinterpret_cast<std::uintptr_t>(&fixture.effects[index]);
    }
    fixture.wrapper0.Pointer(0x38, reinterpret_cast<std::uintptr_t>(fixture.effectPointers.data()));
    fixture.wrapper0.Pointer(
        0x40, reinterpret_cast<std::uintptr_t>(fixture.effectPointers.data() +
                                               fixture.effectPointers.size()));
    fixture.wrapper0.Pointer(
        0x48, reinterpret_cast<std::uintptr_t>(fixture.effectPointers.data() +
                                               fixture.effectPointers.size()));

    // Condition ENTITY_SPAWN + action USE_ACTIVE_ITEM.
    fixture.effects[0].U32(0x00, 6);
    fixture.effects[0].U32(0x04, 0);
    fixture.effects[0].I16Pair(0x0C, 123, 321);
    fixture.effects[0].U32(0x10, 456);
    // Action ADD_TEMPRORY_EFFECT.
    fixture.effects[1].U32(0x00, 1);
    fixture.effects[1].U32(0x04, 1);
    fixture.effects[1].U32(0x10, 88);
    // Action CONVERT_ENTITIES.
    fixture.effects[2].U32(0x00, 2);
    fixture.effects[2].U32(0x04, 2);
    fixture.effects[2].I16Pair(0x10, 10, 11);
    fixture.effects[2].I16Pair(0x14, 20, 21);
    // Action AREA_DAMAGE, including the 64-bit flags emitted upstream.
    fixture.effects[3].U32(0x00, 3);
    fixture.effects[3].U32(0x04, 3);
    fixture.effects[3].F32(0x18, 7.5f);
    fixture.effects[3].F32(0x1C, 9.25f);
    fixture.effects[3].U64(0x20, 0x1122334455667788ull);
    fixture.effects[3].U64(0x28, 0x2233445566778899ull);
    // Action SPAWN_ENTITY.
    fixture.effects[4].U32(0x00, 4);
    fixture.effects[4].U32(0x04, 4);
    fixture.effects[4].I16Pair(0x10, 31, 32);
    // Action FART.
    fixture.effects[5].U32(0x00, 8);
    fixture.effects[5].U32(0x04, 5);
    fixture.effects[5].F32(0x10, 0.75f);
    fixture.effects[5].F32(0x1C, 12.5f);
    fixture.effects[5].F32(0x30, 0.5f);
    fixture.effects[5].F32(0x60, 13.5f);

    fixture.items[0] = reinterpret_cast<std::uintptr_t>(&fixture.wrapper0);
    fixture.items[1] = reinterpret_cast<std::uintptr_t>(&fixture.wrapper1);
    SetManager(&fixture.manager, &fixture.items, 2);
    otherItems[0] = fixture.items[0];
    SetManager(&otherManager, &otherItems, 1);
}

int TargetPointer(lua_State* state) {
    lua_pushinteger(
        state, static_cast<lua_Integer>(isaac::runtime::ItemConfigPointerArgument(state, 1)));
    return 1;
}

int TargetIsExpected(lua_State* state) {
    lua_pushboolean(
        state, isaac::runtime::ItemConfigPointerArgument(state, 1) ==
                   reinterpret_cast<std::uintptr_t>(fixture.targetConfig.data()));
    return 1;
}

const RepentogonApiBinding kApis[] = {
    {{0x0E020100, ApiDomain::Isaac, "ProceduralItemManager", "GetProceduralItem", {}, 0,
      ThreadAffinity::Any, ApiMaturity::Experimental}, &ProceduralItemManagerGetProceduralItem},
    {{0x0E020101, ApiDomain::Isaac, "ProceduralItem", "GetTargetItem", {}, 0,
      ThreadAffinity::Any, ApiMaturity::Experimental}, &ProceduralItemGetTargetItem},
    {{0x0E020102, ApiDomain::Isaac, "ProceduralItem", "GetEffectCount", {}, 0,
      ThreadAffinity::Any, ApiMaturity::Experimental}, &ProceduralItemGetEffectCount},
    {{0x0E020103, ApiDomain::Isaac, "ProceduralItem", "GetEffect", {}, 0,
      ThreadAffinity::Any, ApiMaturity::Experimental}, &ProceduralItemGetEffect},
    {{0x0E020104, ApiDomain::Isaac, "ProceduralItem", "GetSpeed", {}, 0,
      ThreadAffinity::Any, ApiMaturity::Experimental}, &ProceduralItemGetSpeed},
    {{0x0E020105, ApiDomain::Isaac, "ProceduralItem", "GetFireDelay", {}, 0,
      ThreadAffinity::Any, ApiMaturity::Experimental}, &ProceduralItemGetFireDelay},
    {{0x0E020106, ApiDomain::Isaac, "ProceduralItem", "GetDamage", {}, 0,
      ThreadAffinity::Any, ApiMaturity::Experimental}, &ProceduralItemGetDamage},
    {{0x0E020107, ApiDomain::Isaac, "ProceduralItem", "GetRange", {}, 0,
      ThreadAffinity::Any, ApiMaturity::Experimental}, &ProceduralItemGetRange},
    {{0x0E020108, ApiDomain::Isaac, "ProceduralItem", "GetShotSpeed", {}, 0,
      ThreadAffinity::Any, ApiMaturity::Experimental}, &ProceduralItemGetShotSpeed},
    {{0x0E020109, ApiDomain::Isaac, "ProceduralItem", "GetLuck", {}, 0,
      ThreadAffinity::Any, ApiMaturity::Experimental}, &ProceduralItemGetLuck},
    {{0x0E02010A, ApiDomain::Isaac, "ProceduralEffect", "GetConditionType", {}, 0,
      ThreadAffinity::Any, ApiMaturity::Experimental}, &ProceduralEffectGetConditionType},
    {{0x0E02010B, ApiDomain::Isaac, "ProceduralEffect", "GetConditionProperty", {}, 0,
      ThreadAffinity::Any, ApiMaturity::Experimental}, &ProceduralEffectGetConditionProperty},
    {{0x0E02010C, ApiDomain::Isaac, "ProceduralEffect", "GetActionType", {}, 0,
      ThreadAffinity::Any, ApiMaturity::Experimental}, &ProceduralEffectGetActionType},
    {{0x0E02010D, ApiDomain::Isaac, "ProceduralEffect", "GetActionProperty", {}, 0,
      ThreadAffinity::Any, ApiMaturity::Experimental}, &ProceduralEffectGetActionProperty},
};

const RepentogonBatch kBatch{
    "procedural-items", kApis, std::size(kApis), nullptr, 0, nullptr, 0,
    &RegisterProceduralItemApi, nullptr, nullptr,
};
const RepentogonCatalog kCatalog{&kBatch, 1, nullptr};

void Run(lua_State* state, const char* script) {
    if (luaL_dostring(state, script) != LUA_OK) {
        std::fprintf(stderr, "%s\n", lua_tostring(state, -1));
        std::abort();
    }
}

lua_State* Start() {
    lua_State* state = luaL_newstate();
    assert(state != nullptr);
    for (const auto& library : {
             std::pair<const char*, lua_CFunction>{"_G", luaopen_base},
             std::pair<const char*, lua_CFunction>{"table", luaopen_table},
             std::pair<const char*, lua_CFunction>{"string", luaopen_string},
             std::pair<const char*, lua_CFunction>{"math", luaopen_math}}) {
        luaL_requiref(state, library.first, library.second, 1);
        lua_pop(state, 1);
    }
    luaL_newmetatable(state, kItemMt);
    lua_pushliteral(state, "ItemConfig_Item");
    lua_setfield(state, -2, "__type");
    lua_pop(state, 1);
    lua_pushcfunction(state, TargetPointer);
    lua_setglobal(state, "TargetPointer");
    lua_pushcfunction(state, TargetIsExpected);
    lua_setglobal(state, "TargetIsExpected");
    LuaRuntime::ObserveGameThread();
    LuaRuntime::SetEngineModuleBase(reinterpret_cast<std::uintptr_t>(module.data()));
    BeginRepentogonEnvironment(state, true, kCatalog);
    CompleteRepentogonEnvironment(state);
    return state;
}

void Close(lua_State* state) {
    SuspendRepentogonEnvironment(state);
    lua_close(state);
    EndRepentogonEnvironment(state);
}

}  // namespace

int main() {
    ResetFixture();
    SetProceduralItemManagerForHostTesting(reinterpret_cast<std::uintptr_t>(&fixture.manager));
    lua_State* state = Start();
    Run(state, R"lua(
assert(type(ProceduralItemManager)=='table')
assert(getmetatable(ProceduralItemManager).__type=='ProceduralItemManager')
assert(getmetatable(ProceduralItemManager).__class=='ProceduralItemManager')
item=ProceduralItemManager.GetProceduralItem(0)
assert(getmetatable(item).__type=='ProceduralItem')
assert(getmetatable(item).__class=='ProceduralItem')
assert(type(getmetatable(item).GetDamage)=='function')
assert(item:GetDamage()==1.25 and item:GetFireDelay()==2.5 and item:GetSpeed()==3.75)
assert(item:GetRange()==4.25 and item:GetShotSpeed()==5.5 and item:GetLuck()==6.75)
assert(item:GetEffectCount()==6)

target=item:GetTargetItem()
assert(getmetatable(target).__type=='ItemConfig_Item')
assert(TargetIsExpected(target))
assert(ProceduralItemManager.GetProceduralItem(0.0):GetDamage()==1.25)
assert(ProceduralItemManager.GetProceduralItem("0"):GetDamage()==1.25)

e0=item:GetEffect(0)
assert(getmetatable(e0).__type=='ProceduralEffect')
assert(getmetatable(e0).__class=='ProceduralEffect')
assert(type(getmetatable(e0).GetActionType)=='function')
assert(item:GetEffect(0.0):GetActionType()==0)
assert(e0:GetConditionType()==6 and e0:GetActionType()==0)
local cp=e0:GetConditionProperty()
assert(cp.type==321 and cp.variant==123)
local ap=e0:GetActionProperty()
assert(ap.id==456 and ap.type==nil and ap.variant==nil)
assert(item:GetEffect(1):GetActionProperty().id==88)
local convert=item:GetEffect(2):GetActionProperty()
assert(convert.fromType==11 and convert.fromVariant==10)
assert(convert.toType==21 and convert.toVariant==20)
local area=item:GetEffect(3):GetActionProperty()
assert(area.radius==7.5 and area.damage==9.25)
assert(area.flags1==0x1122334455667788)
assert(area.flags2==0x2233445566778899)
local spawn=item:GetEffect(4):GetActionProperty()
assert(spawn.type==32 and spawn.variant==31)
local fart=item:GetEffect(5):GetActionProperty()
assert(math.abs(fart.scale-4.5)<1e-6)
assert(math.abs(fart.radius-(12.5*6/85))<1e-6)
assert(item:GetEffect(6)==nil)

assert(ProceduralItemManager.GetProceduralItem(-1)==nil)
assert(ProceduralItemManager.GetProceduralItem(2147483648)==nil)
assert(item:GetEffect(-1)==nil)
assert(item:GetEffect(2147483648)==nil)
local ok,e=pcall(ProceduralItemManager.GetProceduralItem,'x')
assert(not ok)
ok,e=pcall(item.GetDamage,item,1)
assert(not ok)
ok,e=pcall(item.GetEffect,item,'x')
assert(not ok)

)lua");

    // Same wrapper, expanded/moved manager storage: the live borrow remains valid.
    alignas(8) std::array<std::uintptr_t, 8> expanded{};
    expanded[0] = fixture.items[0];
    expanded[1] = fixture.items[1];
    SetManagerRaw(&fixture.manager, expanded.data(), 3);
    Run(state, "assert(item:GetDamage()==1.25 and item:GetEffectCount()==6);assert(TargetIsExpected(target))");

    // A replaced wrapper at the same index is stale.
    fixture.items[0] = reinterpret_cast<std::uintptr_t>(&fixture.wrapper1);
    SetManager(&fixture.manager, &fixture.items, 2);
    Run(state, "local ok=pcall(item.GetDamage,item);assert(not ok);assert(TargetPointer(target)==0)");
    fixture.items[0] = reinterpret_cast<std::uintptr_t>(&fixture.wrapper0);
    SetManager(&fixture.manager, &fixture.items, 2);

    // A different game/manager is also stale.
    SetProceduralItemManagerForHostTesting(reinterpret_cast<std::uintptr_t>(&otherManager));
    Run(state, "local ok=pcall(item.GetDamage,item);assert(not ok);assert(TargetPointer(target)==0)");
    SetProceduralItemManagerForHostTesting(reinterpret_cast<std::uintptr_t>(&fixture.manager));

    // Legal empty vectors yield nil / zero, not corruption errors.
    fixture.manager.end = fixture.manager.begin;
    Run(state, "assert(ProceduralItemManager.GetProceduralItem(0)==nil)");
    SetManager(&fixture.manager, &fixture.items, 2);
    fixture.wrapper0.Pointer(0x38, 0);
    fixture.wrapper0.Pointer(0x40, 0);
    fixture.wrapper0.Pointer(0x48, 0);
    Run(state, "assert(item:GetEffectCount()==0 and item:GetEffect(0)==nil)");
    fixture.wrapper0.Pointer(0x38, reinterpret_cast<std::uintptr_t>(fixture.effectPointers.data()));
    fixture.wrapper0.Pointer(
        0x40, reinterpret_cast<std::uintptr_t>(fixture.effectPointers.data() +
                                               fixture.effectPointers.size()));

    // Malformed manager/effect vectors are errors, not empty/degraded results.
    fixture.manager.end = fixture.manager.begin - 8;
    Run(state, "local ok=pcall(ProceduralItemManager.GetProceduralItem,0);assert(not ok)");
    SetManager(&fixture.manager, &fixture.items, 2);
    fixture.manager.capacity = fixture.manager.begin;
    Run(state, "local ok=pcall(ProceduralItemManager.GetProceduralItem,0);assert(not ok)");
    SetManager(&fixture.manager, &fixture.items, 2);
    fixture.wrapper0.Pointer(0x40, fixture.wrapper0.Pointer(0x38) - 8);
    Run(state, "local ok=pcall(item.GetEffectCount,item);assert(not ok)");
    fixture.wrapper0.Pointer(
        0x40, reinterpret_cast<std::uintptr_t>(fixture.effectPointers.data() +
                                               fixture.effectPointers.size()));
    fixture.wrapper0.Pointer(0x48, fixture.wrapper0.Pointer(0x38));
    Run(state, "local ok=pcall(item.GetEffectCount,item);assert(not ok)");
    fixture.wrapper0.Pointer(
        0x48, reinterpret_cast<std::uintptr_t>(fixture.effectPointers.data() +
                                               fixture.effectPointers.size()));

    // An effect borrow resolves parent wrapper + effect[index] every call.
    fixture.effectPointers[0] =
        reinterpret_cast<std::uintptr_t>(&fixture.effects[1]);
    Run(state, "local ok=pcall(e0.GetActionType,e0);assert(not ok)");
    fixture.effectPointers[0] =
        reinterpret_cast<std::uintptr_t>(&fixture.effects[0]);
    Run(state, "assert(e0:GetActionType()==0)");

    // The target userdata borrows the real ItemConfig::Item and is retired when target changes.
    fixture.wrapper0.Pointer(0x18, 0);
    Run(state, "assert(TargetPointer(target)==0)");
    fixture.wrapper0.Pointer(0x18,
                             reinterpret_cast<std::uintptr_t>(fixture.targetConfig.data()));
    Run(state, "assert(TargetPointer(target)==TargetPointer(target))");
    assert(fixture.wrapper0.Pointer(0x18) ==
           reinterpret_cast<std::uintptr_t>(fixture.targetConfig.data()));
    fixture.collectibleItems[3] = 0;
    Run(state, "assert(TargetPointer(target)==0)");
    fixture.collectibleItems[3] =
        reinterpret_cast<std::uintptr_t>(fixture.targetConfig.data());

    // A readable object that is not the current vector[id] is not ItemConfig.
    fixture.wrapper0.Pointer(0x18,
                             reinterpret_cast<std::uintptr_t>(fixture.fakeTarget.data()));
    Run(state, "local ok=pcall(item.GetTargetItem,item);assert(not ok)");
    fixture.wrapper0.Pointer(0x18,
                             reinterpret_cast<std::uintptr_t>(fixture.targetConfig.data()));

    // Type 2 resolves through the trinket vector, also by ID (not by scanning).
    PutU32(fixture.targetConfig.data(), 0x00, 2);
    PutU32(fixture.targetConfig.data(), 0x04, 1);
    fixture.trinketItems[1] =
        reinterpret_cast<std::uintptr_t>(fixture.targetConfig.data());
    Run(state, "assert(TargetIsExpected(target))");
    fixture.trinketItems[1] = 0;
    Run(state, "assert(TargetPointer(target)==0)");
    fixture.trinketItems[1] =
        reinterpret_cast<std::uintptr_t>(fixture.targetConfig.data());
    PutU32(fixture.targetConfig.data(), 0x00, 1);
    PutU32(fixture.targetConfig.data(), 0x04, 3);

    // The world epoch is the ABA barrier for a new run even if all addresses repeat.
    isaac::runtime::BeginWorldContentRun();
    Run(state, R"lua(
assert(not pcall(item.GetDamage,item))
assert(TargetPointer(target)==0)
assert(not pcall(e0.GetActionType,e0))
newItem=ProceduralItemManager.GetProceduralItem(0)
newTarget=newItem:GetTargetItem()
newEffect=newItem:GetEffect(0)
assert(newItem:GetDamage()==1.25)
assert(TargetIsExpected(newTarget))
assert(newEffect:GetActionType()==0)
)lua");

    // All public entries reject a non-game thread, even at top-level Lua.
    std::thread offThread([&] {
        const auto targetAddress =
            reinterpret_cast<std::uintptr_t>(fixture.targetConfig.data());
        assert(!ProceduralTargetItemBelongs(targetAddress));
        assert(!ValidateProceduralTargetItem(
            reinterpret_cast<std::uintptr_t>(&fixture.manager),
            reinterpret_cast<std::uintptr_t>(&fixture.wrapper0), 0,
            CaptureWorldContentSnapshot().worldEpoch, targetAddress));
        lua_State* off = luaL_newstate();
        assert(off != nullptr);
        const lua_CFunction calls[] = {
            &ProceduralItemManagerGetProceduralItem,
            &ProceduralItemGetTargetItem,
            &ProceduralItemGetEffectCount,
            &ProceduralItemGetEffect,
            &ProceduralItemGetSpeed,
            &ProceduralItemGetFireDelay,
            &ProceduralItemGetDamage,
            &ProceduralItemGetRange,
            &ProceduralItemGetShotSpeed,
            &ProceduralItemGetLuck,
            &ProceduralEffectGetConditionType,
            &ProceduralEffectGetConditionProperty,
            &ProceduralEffectGetActionType,
            &ProceduralEffectGetActionProperty,
        };
        for (lua_CFunction call : calls) {
            lua_settop(off, 0);
            lua_pushcfunction(off, call);
            assert(lua_pcall(off, 0, 0, 0) != LUA_OK);
            assert(std::strstr(lua_tostring(off, -1), "game thread") != nullptr);
        }
        lua_close(off);
    });
    offThread.join();

    Close(state);
    LuaRuntime::SetEngineModuleBase(0);
    SetProceduralItemManagerForHostTesting(0);
    std::puts("procedural item native layout, Lua schema, and stale borrows verified");
}
'''


class ProceduralItemApiTests(unittest.TestCase):
    def test_declarations_cover_exactly_the_fourteen_upstream_methods(self):
        self.assertTrue(HEADER.is_file(), "procedural_item_api.hpp is missing")
        header = HEADER.read_text(encoding="utf-8")
        for name in HANDLERS:
            self.assertRegex(
                header,
                rf"\bint\s+{name}\s*\(\s*lua_State\s*\*\s*[A-Za-z_]",
                f"missing exported handler {name}",
            )
        self.assertRegex(
            header,
            r"\bint\s+RegisterProceduralItemApi\s*\(\s*lua_State\s*\*\s*[A-Za-z_]",
        )

    def test_registration_uses_central_extension_owners(self):
        self.assertTrue(IMPLEMENTATION.is_file(), "procedural_item_api.cpp is missing")
        source = IMPLEMENTATION.read_text(encoding="utf-8")
        for owner, constant in (
            ("ProceduralItemManager", "kManagerOwner"),
            ("ProceduralItem", "kItemOwner"),
            ("ProceduralEffect", "kEffectOwner"),
        ):
            self.assertIn(f'"{owner}"', source)
            self.assertRegex(
                source,
                rf'AttachOwnerMethods\s*\(\s*state\s*,\s*{constant}\s*,\s*nullptr\s*,\s*0\s*\)',
                f"{owner} must be attached through the central extension catalog",
            )
        self.assertNotRegex(source, r"lua_setfield\s*\([^;]+GetConditionType")
        self.assertNotRegex(source, r"lua_setfield\s*\([^;]+GetActionType")

    def test_real_lua_vm_contract_and_borrow_validation(self):
        self.assertTrue(IMPLEMENTATION.is_file(), "procedural_item_api.cpp is missing")
        with tempfile.TemporaryDirectory(prefix="procedural-item-api-") as temporary:
            binary = test_support.build_lua_harness(
                source_root=SOURCE,
                workdir=Path(temporary),
                harness_source=DRIVER,
            )
            result = subprocess.run([str(binary)], text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
