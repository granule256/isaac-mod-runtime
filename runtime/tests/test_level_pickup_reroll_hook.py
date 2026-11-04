"""Native level rerolls preserve entries and notify only after the original returns."""
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from .test_support import LUA_SOURCE_RELATIVE, lua_harness_objects

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'runtime/source'
HOOK = ROOT / 'runtime/src/infrastructure/gotslot/level_pickup_reroll_hook.cpp'

DRIVER = r'''
#include "ports/hook_port.hpp"
#include "interfaces/lua/minimap_pickup_cache.hpp"
#include "runtime_constants.hpp"
extern "C" {
#include "lua.h"
#include "lauxlib.h"
#include "lualib.h"
}
#include <cassert>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <vector>
namespace isaac::runtime {
// A missing installer remains a runtime rejection in the RED baseline.
Status InstallLevelPickupRerollPointerHook(HookId,const HookTarget&) noexcept __attribute__((weak));
Status InstallLevelPickupRerollPointerHook(HookId,const HookTarget&) noexcept {return Status{StatusCode::Rejected};}
}
using namespace isaac::runtime;
constexpr std::uintptr_t pickupsGot=0xa9f4f8,collectiblesGot=0xa9f500;
constexpr std::uintptr_t pickupsPlt=0x672b20,collectiblesPlt=0x672b30;
constexpr std::array<std::uint8_t,16> pickupsPltBytes={0x70,0x21,0x00,0xb0,0x11,0x7e,0x42,0xf9,0x10,0xe2,0x13,0x91,0x20,0x02,0x1f,0xd6};
constexpr std::array<std::uint8_t,16> collectiblesPltBytes={0x70,0x21,0x00,0xb0,0x11,0x82,0x42,0xf9,0x10,0x02,0x14,0x91,0x20,0x02,0x1f,0xd6};
std::uintptr_t mappedBase{};
unsigned pickupCalls{},collectibleCalls{};
int game{};
void Pickups(void* self,std::uint32_t seed){
    assert(self==&game&&seed==0xffffffffU&&!HasPendingMinimapPickupReroll());
    ++pickupCalls;
}
void Collectibles(void* self){
    assert(self==&game&&!HasPendingMinimapPickupReroll());++collectibleCalls;
}
// Only ARM engine entry execution is substituted; production installer/interceptors
// and the real pending cache helper are linked and exercised below.
std::uintptr_t TestEngineAddress(std::uintptr_t address) noexcept {
    if(address==mappedBase+kApi200GameRerollLevelPickupsOffset)return reinterpret_cast<std::uintptr_t>(&Pickups);
    if(address==mappedBase+kApi200GameRerollLevelCollectiblesOffset)return reinterpret_cast<std::uintptr_t>(&Collectibles);
    return address;
}
Status Install(HookId id,const HookTarget& target){
    auto* installer=&InstallLevelPickupRerollPointerHook;
    return installer?installer(id,target):Status{StatusCode::Rejected};
}
void Run(lua_State* L,const char* script){
    if(luaL_dostring(L,script)!=LUA_OK){std::fprintf(stderr,"%s\n",lua_tostring(L,-1));std::abort();}
}
int main(){
    std::vector<std::uint8_t> image(0xab0000);mappedBase=reinterpret_cast<std::uintptr_t>(image.data());
    const auto base=mappedBase;
    auto copy=[&](auto offset,const auto& bytes){std::memcpy(image.data()+offset,bytes.data(),bytes.size());};
    copy(kApi200GameRerollLevelPickupsOffset,kApi200GameRerollLevelPickupsExpectedBytes);
    copy(kApi200GameRerollLevelCollectiblesOffset,kApi200GameRerollLevelCollectiblesExpectedBytes);
    copy(pickupsPlt,pickupsPltBytes);copy(collectiblesPlt,collectiblesPltBytes);
    HookTarget t{};t.base=base;t.codeSize=0x68d000;t.imageSize=image.size();t.buildId=kTargetBuildId;
    auto write=[&](auto slot,auto value){std::memcpy(image.data()+slot,&value,sizeof(value));};
    auto read=[&](auto slot){std::uintptr_t value{};std::memcpy(&value,image.data()+slot,sizeof(value));return value;};
    write(pickupsGot,base+kApi200GameRerollLevelPickupsOffset);
    write(collectiblesGot,base+kPltResolverOffset);
    assert(!Install(HookId::ManagerPresent,t).ok());
    auto* L=luaL_newstate();assert(L);luaL_requiref(L,"_G",luaopen_base,1);lua_pop(L,1);
    const HookId ids[]={HookId::GameRerollLevelPickups,HookId::GameRerollLevelCollectibles};
    const std::uintptr_t entries[]={kApi200GameRerollLevelPickupsOffset,kApi200GameRerollLevelCollectiblesOffset};
    const std::uintptr_t plts[]={pickupsPlt,collectiblesPlt};
    const std::uintptr_t slots[]={pickupsGot,collectiblesGot};
    for(unsigned kind=0;kind<2;++kind){
        const auto id=ids[kind];const auto slot=slots[kind];
        const auto original=read(slot);
        auto rejected=[&](const HookTarget& target){assert(!Install(id,target).ok()&&read(slot)==original);};
        for(auto offset:{entries[kind],plts[kind]})for(unsigned byte=0;byte<16;++byte){
            image[offset+byte]^=1;rejected(t);image[offset+byte]^=1;
        }
        auto wrong=t;wrong.buildId[0]^=1;rejected(wrong);
        wrong=t;wrong.imageSize=slot+7;rejected(wrong);
        wrong=t;wrong.base=0;rejected(wrong);
        wrong=t;wrong.base=UINTPTR_MAX-16;rejected(wrong);
        wrong=t;wrong.imageSize=0;rejected(wrong);
        write(slot,std::uintptr_t{123});assert(!Install(id,t).ok()&&read(slot)==123);write(slot,original);
        if(!Install(id,t).ok()){
            std::fprintf(stderr,"guarded valid native reroll GOT slot was not installed\n");return 1;
        }
        assert(read(slot)!=original&&read(slot)!=base+entries[kind]);
        // Installation replaces only this GOT pointer; Lua API entry guards stay intact.
        assert(std::memcmp(image.data()+kApi200GameRerollLevelPickupsOffset,kApi200GameRerollLevelPickupsExpectedBytes.data(),16)==0);
        assert(std::memcmp(image.data()+kApi200GameRerollLevelCollectiblesOffset,kApi200GameRerollLevelCollectiblesExpectedBytes.data(),16)==0);
        assert(!Install(id,t).ok());
        ResetMinimapPickupCache();
        Run(L,"MinimapAPI={PickupList={{Type=5,Variant=20,IconID='Coin'},{Type=5,Variant=100,IconID='Item'}},Levels={[0]={{Descriptor={},ItemIcons={'Coin','Item'}}}}}");
        if(kind==0)reinterpret_cast<void(*)(void*,std::uint32_t)>(read(slot))(&game,0xffffffffU);
        else reinterpret_cast<void(*)(void*)>(read(slot))(&game);
        assert(HasPendingMinimapPickupReroll());
        assert(pickupCalls==1&&collectibleCalls==kind);
        assert(FlushMinimapPickupCache(L)&&!HasPendingMinimapPickupReroll());
        Run(L,kind==0?"assert(#MinimapAPI.Levels[0][1].ItemIcons==1 and MinimapAPI.Levels[0][1].ItemIcons[1]=='Item')":"assert(#MinimapAPI.Levels[0][1].ItemIcons==1 and MinimapAPI.Levels[0][1].ItemIcons[1]=='Coin')");
    }
    lua_close(L);
}
'''


class LevelPickupRerollHookTests(unittest.TestCase):
    def test_original_then_notify_and_guarded_single_slot_installation(self):
        shim = '''#pragma once
#include <cstdint>
#include <cstddef>
namespace exl::util {struct RwPages {std::uintptr_t p;RwPages(std::uintptr_t a,std::size_t):p(a){}std::uintptr_t GetRw()const{return p;}void Flush(){}};}
'''
        calls = '''#pragma once
#include <cstdint>
std::uintptr_t TestEngineAddress(std::uintptr_t) noexcept;
namespace isaac::runtime::engine_call {
template<class Fn> Fn AsFunction(std::uintptr_t p) noexcept {return reinterpret_cast<Fn>(TestEngineAddress(p));}
template<class Fn> std::uintptr_t AddressOfFunction(Fn f) noexcept {return reinterpret_cast<std::uintptr_t>(f);}
}
'''
        with tempfile.TemporaryDirectory(prefix='isaac-level-reroll-') as temporary:
            work = Path(temporary)
            (work / 'lib/util/sys').mkdir(parents=True)
            (work / 'lib/util/sys/rw_pages.hpp').write_text(shim)
            (work / 'infrastructure/call').mkdir(parents=True)
            (work / 'infrastructure/call/engine_call_access.hpp').write_text(calls)
            (work / 'driver.cpp').write_text(DRIVER)
            objects = lua_harness_objects(SOURCE, work)
            sources = [HOOK] if HOOK.is_file() else []
            result = subprocess.run([
                'clang++', '-std=c++23', '-Wall', '-Wextra', '-Werror',
                '-I', str(work), '-I', str(ROOT / 'runtime/src'), '-I', str(SOURCE),
                '-I', str(SOURCE / LUA_SOURCE_RELATIVE), str(work / 'driver.cpp'),
                *map(str, sources), str(ROOT / 'runtime/src/interfaces/lua/minimap_pickup_cache.cpp'),
                *map(str, objects), '-o', str(work / 'driver')
            ], text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            result = subprocess.run([str(work / 'driver')], text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_nro_relocations_and_pinned_plt_bytes(self):
        sys.path.insert(0, str(ROOT / 'tools'))
        from gen_engine_symbol_signatures import NRO
        from nro_symbols import parse_dynamic_relocations
        blob = NRO.read_bytes()
        _, rows = parse_dynamic_relocations(blob)
        header = HOOK.with_suffix('.hpp').read_text()
        for name, symbol, slot, plt in [
            ('Pickups', '_ZN15IsaacRepentance4Game18RerollLevelPickupsEj', 0xa9f4f8, 0x672b20),
            ('Collectibles', '_ZN15IsaacRepentance4Game23RerollLevelCollectiblesEv', 0xa9f500, 0x672b30)
        ]:
            self.assertEqual([(row.offset, row.relocation_type) for row in rows[symbol]], [(slot, 1026)])
            self.assertRegex(header, 'k' + name + r'GotOffset\s*=\s*0x' + format(slot, 'x'))
            self.assertRegex(header, 'k' + name + r'PltOffset\s*=\s*0x' + format(plt, 'x'))
            match = re.search('k' + name + r'PltBytes\s*=\s*\{(.*?)\}', header, re.S)
            self.assertIsNotNone(match)
            expected = bytes(int(value, 16) for value in re.findall(r'0x([0-9a-f]{2})', match.group(1)))
            self.assertEqual(expected, blob[plt:plt + 16])
