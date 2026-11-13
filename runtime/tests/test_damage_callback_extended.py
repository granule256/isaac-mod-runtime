"""Extended MC_ENTITY_TAKE_DMG and MC_POST_ENTITY_TAKE_DMG argument paths."""
import subprocess
import tempfile
import unittest
from pathlib import Path

from . import test_lua_entity_query as fixture
from .test_support import build_lua_harness


MAIN = r'''
#include "application/callback/extended_callback_runtime.hpp"
#include "damage_context.hpp"
#include <array>
#include <cassert>
#include <cmath>
#include <cstring>

static isaac::runtime::ExtendedCallbackState g_DamageState{
    1006, false, 0, 0};
static int DeliveryEnabled(lua_State* L) {
    lua_pushboolean(L,isaac::runtime::g_ExtendedCallbackDelivery);return 1;
}
static void InstallDamageState(lua_State* L) noexcept {
    isaac::runtime::g_ExtendedCallbacks = &g_DamageState;
    isaac::runtime::g_ExtendedCallbackCount = 1;
    isaac::runtime::g_ExtendedCallbackDelivery = true;
    lua_pushcfunction(L,DeliveryEnabled);lua_setglobal(L,"_deliveryEnabled");
}

template<class T>
static void Put(void* base, std::size_t offset, T value) {
    std::memcpy(static_cast<unsigned char*>(base) + offset, &value, sizeof(value));
}

static void FillRef(void* ref, std::uint32_t type, std::uint32_t variant,
                    std::int32_t spawnerType, std::uint32_t spawnerVariant,
                    float x, float y, std::uintptr_t entity) {
    Put(ref, 0x00, type);
    Put(ref, 0x04, variant);
    Put(ref, 0x08, spawnerType);
    Put(ref, 0x0c, spawnerVariant);
    Put(ref, 0x10, x);
    Put(ref, 0x14, y);
    Put(ref, 0x18, x + 3.0F);
    Put(ref, 0x1c, y + 4.0F);
    Put(ref, 0x20, std::uint32_t{7});
    Put(ref, 0x28, entity);
}

int main() {
    static_cast<void>(kScriptTemplate);
    static_cast<void>(&HarnessHasCollectible);
    static_cast<void>(&BuildPrelude);
    static_cast<void>(&ExpectNumber);
    CreateBlocks();
    FillEntities();
    PublishLists();
    PublishGame();
    PublishEntityList(g_RoomBytes, true);
    LuaRuntime::SetEngineModuleBase(g_EngineBase);
    LuaRuntime::SetGameBindings(g_EngineBase + kGameOwnerGlobalSlotOffset, 0x2222);
    LuaRuntime::SetRuntimeExtensionInstaller(InstallDamageState);

    const char* script = R"lua(
        _damage={pre=0,post=0,args=0,postArgs=0,postDamage=0,nilArgs=0,nilPost=0}
        local mod=RegisterMod('extended-damage',1)
        local override_mt={__index=function() error('return table __index must not run') end}
        mod:AddCallback(11,function(...)
            local _,entity,damage,flags,source,countdown,extra=...
            _damage.pre=_damage.pre+1
            _damage.args=select('#',...)-1
            assert(damage==3 and flags==0x10000000003)
            assert(source.Type==3 and source.Variant==7)
            assert(source.SpawnerType==11 and source.SpawnerVariant==13)
            assert(source.Position.X==1.5 and source.Position.Y==2.5)
            assert(extra and extra.Type==10 and extra.Variant==2)
            assert(extra.SpawnerType==20 and extra.SpawnerVariant==21)
            assert(extra.Position.X==4.5 and extra.Position.Y==5.5)
            assert(countdown==17)
            return setmetatable(
                {Damage=4.6,DamageFlags=0x2000000000000001,DamageCountdown=9},
                override_mt)
        end,1)
        mod:AddCallback(11,function(...)
            local _,entity,damage,flags,source,countdown,extra=...
            _damage.nilArgs=select('#',...)-1
            assert(extra==nil and select('#',...)-1==6)
            return {Damage=2.2,DamageCountdown=6}
        end,2)
        mod:AddCallback(11,function(...)
            local _,entity,damage,flags,source,countdown=...
            assert(select('#',...)-1==5)
            assert(damage==2 and countdown==17)
            return false
        end,10)
        mod:AddCallback(11,function(...)
            assert(select('#',...)-1==5 and _deliveryEnabled())
            _damage.legacy=5
            return {Damage=100,DamageFlags=64,DamageCountdown=99}
        end,5000)
        mod:AddCallback(11,function(...)
            return {DamageFlags=2}
        end,3)
        mod:AddCallback(11,function(...)
            return {DamageFlags=64,DamageCountdown=37}
        end,5)
        mod:AddCallback(11,function(...)
            return {DamageFlags=2097152}
        end,7)
        mod:AddCallback(1006,function(...)
            local _,entity,damage,flags,source,countdown,extra=...
            _damage.post=_damage.post+1
            _damage.postArgs=select('#',...)-1
            _damage.postDamage=damage
            assert(damage==5 and flags==0x2000000000000001 and countdown==9)
            assert(source.Type==3 and extra.Type==10)
        end,1)
        mod:AddCallback(1006,function(...)
            local _,entity,damage,flags,source,countdown,extra=...
            assert(select('#',...)-1==6 and extra==nil)
            _damage.nilPost=_damage.nilPost+1
        end,2)
        Isaac.SetBuiltInCallbackState(11,true)
        Isaac.SetBuiltInCallbackState(1006,true)
    )lua";
    const auto init=LuaRuntime::InitializeFromBuffer(
        script,std::strlen(script),"@extended-damage.lua");
    if(init!=LuaRuntime::LuaInitResult::Success){
        char error[2048]{};
        static_cast<void>(LuaRuntime::CopyLastLuaErrorText(error,sizeof(error)));
        std::fprintf(stderr,"%s\n",error);
    }
    assert(init==LuaRuntime::LuaInitResult::Success);

    alignas(16) std::array<unsigned char,0x40> source{};
    alignas(16) std::array<unsigned char,0x40> extra{};
    const auto player=AddressOf(g_Entities[kPlayer]);
    FillRef(source.data(),3,7,11,13,1.5F,2.5F,player);
    FillRef(extra.data(),10,2,20,21,4.5F,5.5F,AddressOf(g_Entities[kEnemyA]));

    isaac::runtime::damage::Values values{};
    values.entity=player;
    values.amount=3;
    values.playerDamage=3;
    values.damageFlags=0x10000000003ULL;
    values.sourceRef=reinterpret_cast<std::uintptr_t>(source.data());
    values.countdown=17;
    values.extraSourceRef=reinterpret_cast<std::uintptr_t>(extra.data());
    values.entityType=1;
    values.player=true;
    values.sourceReadable=true;
    values.extraSourceReadable=true;
    assert(!LuaRuntime::DispatchEntityTakeDamageValues(values));
    assert(values.amount==5.0F&&values.playerDamage==5);
    assert(values.damageFlags==0x2000000000000001ULL&&values.countdown==9);
    LuaRuntime::DispatchPostEntityTakeDamageValues(values);

    isaac::runtime::damage::Values noExtra{};
    noExtra.entity=player;
    noExtra.amount=8;
    noExtra.damageFlags=2;
    noExtra.sourceRef=reinterpret_cast<std::uintptr_t>(source.data());
    noExtra.countdown=12;
    noExtra.entityType=2;
    assert(!LuaRuntime::DispatchEntityTakeDamageValues(noExtra));
    assert(noExtra.amount==2.2F&&noExtra.countdown==6);
    LuaRuntime::DispatchPostEntityTakeDamageValues(noExtra);

    assert(!LuaRuntime::DispatchLegacyEntityTakeDamage(
        player,8,2,reinterpret_cast<std::uintptr_t>(source.data()),12,5000));
    assert(isaac::runtime::g_ExtendedCallbackDelivery);

    const auto enemy=AddressOf(g_Entities[kEnemyA]);
    isaac::runtime::damage::Values fire{};
    fire.entity=enemy;
    fire.amount=1;
    fire.sourceRef=reinterpret_cast<std::uintptr_t>(source.data());
    fire.countdown=17;
    fire.entityType=3;
    Put(g_Entities[kEnemyA].data(),0x278,std::int32_t{0});
    Put(g_Entities[kEnemyA].data(),0x27c,std::int32_t{0});
    assert(!LuaRuntime::DispatchEntityTakeDamageValues(fire));
    assert(fire.damageFlags==2);
    std::int32_t field{};
    std::memcpy(&field,g_Entities[kEnemyA].data()+0x278,4);
    assert(field==10);
    Put(g_Entities[kEnemyA].data(),0x278,std::int32_t{1});
    fire={};
    fire.entity=enemy;
    fire.amount=1;
    fire.sourceRef=reinterpret_cast<std::uintptr_t>(source.data());
    fire.countdown=17;
    fire.entityType=3;
    assert(LuaRuntime::DispatchEntityTakeDamageValues(fire));

    Put(g_Entities[kEnemyA].data(),0x278,std::int32_t{0});
    Put(g_Entities[kEnemyA].data(),0x27c,std::int32_t{0});
    isaac::runtime::damage::Values countdown{};
    countdown.entity=enemy;
    countdown.amount=1;
    countdown.sourceRef=reinterpret_cast<std::uintptr_t>(source.data());
    countdown.countdown=17;
    countdown.entityType=5;
    assert(!LuaRuntime::DispatchEntityTakeDamageValues(countdown));
    assert(countdown.damageFlags==64&&countdown.countdown==37);
    std::memcpy(&field,g_Entities[kEnemyA].data()+0x27c,4);
    assert(field==37);
    Put(g_Entities[kEnemyA].data(),0x27c,std::int32_t{3});
    countdown={};
    countdown.entity=enemy;
    countdown.amount=1;
    countdown.sourceRef=reinterpret_cast<std::uintptr_t>(source.data());
    countdown.countdown=17;
    countdown.entityType=5;
    assert(LuaRuntime::DispatchEntityTakeDamageValues(countdown));

    isaac::runtime::damage::Values fake{};
    fake.entity=player;
    fake.amount=3;
    fake.playerDamage=3;
    fake.sourceRef=reinterpret_cast<std::uintptr_t>(source.data());
    fake.countdown=17;
    fake.entityType=7;
    fake.player=true;
    assert(!LuaRuntime::DispatchEntityTakeDamageValues(fake));
    assert(fake.playerDamage==0&&fake.amount==0);

    isaac::runtime::g_ExtendedCallbackDelivery=false;
    assert(LuaRuntime::DispatchEntityTakeDamage(
        player,2.0F,0x10000000003ULL,0,17,10));
    isaac::runtime::g_ExtendedCallbackDelivery=true;

    FillRef(source.data(),33,4,11,13,1.5F,2.5F,player);
    values.sourceType=33;
    values.sourceVariant=4;
    values.sourceReadable=true;
    LuaRuntime::DispatchPostEntityTakeDamageValues(values);

    values.extraSourceOverflow=true;
    values.extraSourceOverflowSource=values.sourceRef;
    assert(LuaRuntime::DispatchEntityTakeDamageValues(values));
    char error[256]{};
    static_cast<void>(LuaRuntime::CopyLastLuaErrorText(error,sizeof(error)));
    assert(std::strstr(error,"ExtraSource capacity exhausted")!=nullptr);
    assert(LuaRuntime::TakeCallbackError());
    values.extraSourceOverflow=false;
    values.extraSourceUnreadable=true;
    values.extraSourceOverflowSource=values.sourceRef;
    assert(LuaRuntime::DispatchEntityTakeDamageValues(values));
    static_cast<void>(LuaRuntime::CopyLastLuaErrorText(error,sizeof(error)));
    assert(std::strstr(error,"ExtraSource snapshot is unreadable")!=nullptr);
    assert(LuaRuntime::TakeCallbackError());
    values.extraSourceUnreadable=false;

    double number{};
    assert(!LuaRuntime::ReadLuaTableNumber("_damage","pre",&number)&&number==1);
    assert(!LuaRuntime::ReadLuaTableNumber("_damage","post",&number)&&number==1);
    assert(!LuaRuntime::ReadLuaTableNumber("_damage","args",&number)&&number==6);
    assert(!LuaRuntime::ReadLuaTableNumber("_damage","postArgs",&number)&&number==6);
    assert(!LuaRuntime::ReadLuaTableNumber("_damage","postDamage",&number)&&number==5);
    assert(!LuaRuntime::ReadLuaTableNumber("_damage","nilArgs",&number)&&number==6);
    assert(!LuaRuntime::ReadLuaTableNumber("_damage","nilPost",&number)&&number==1);
    assert(!LuaRuntime::ReadLuaTableNumber("_damage","legacy",&number)&&number==5);
    assert(!LuaRuntime::TakeCallbackError());
}
'''


class ExtendedDamageCallbackTests(unittest.TestCase):
    def test_extended_arguments_override_and_post_gate(self):
        with tempfile.TemporaryDirectory(prefix="extended-damage-") as tmp:
            binary = build_lua_harness(
                source_root=fixture.SOURCE,
                workdir=Path(tmp),
                harness_source=fixture.HARNESS[:fixture.HARNESS.index("int main(")] + MAIN,
            )
            result = subprocess.run([str(binary)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
