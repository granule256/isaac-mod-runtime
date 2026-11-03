"""The actual Lua damage dispatcher must preserve flags above bit 31."""
from pathlib import Path
import subprocess
import tempfile
import unittest

from . import test_lua_entity_query as fixture
from .test_support import build_lua_harness

MAIN=r'''
#include <cassert>
int main(){
    static_cast<void>(kScriptTemplate);static_cast<void>(&HarnessHasCollectible);
    static_cast<void>(&BuildPrelude);static_cast<void>(&ExpectNumber);
    CreateBlocks();FillEntities();PublishLists();PublishGame();PublishEntityList(g_RoomBytes,true);
    LuaRuntime::SetEngineModuleBase(g_EngineBase);
    LuaRuntime::SetGameBindings(g_EngineBase+kGameOwnerGlobalSlotOffset,0x2222);
    const char* script=R"lua(
        _damageFlags={count=0}
        local expected={0x80000000,0x100000000,0x100000003,0x123456789ab}
        local mod=RegisterMod('damage-flags',1)
        mod:AddCallback(11,function(_,entity,amount,flags,source,countdown)
            _damageFlags.count=_damageFlags.count+1
            assert(flags==expected[_damageFlags.count],'damage flags must retain their full width')
            assert(amount==2 and countdown==17)
            return false
        end,1)
    )lua";
    assert(LuaRuntime::InitializeFromBuffer(script,std::strlen(script),"@damage-flags.lua")==LuaRuntime::LuaInitResult::Success);
    for(auto flags:{0x80000000ULL,0x100000000ULL,0x100000003ULL,0x123456789abULL}){
        assert(LuaRuntime::DispatchEntityTakeDamage(AddressOf(g_Entities[kPlayer]),2.0F,flags,0,17,1));
        assert(!LuaRuntime::TakeCallbackError());
    }
    double count=0;assert(!LuaRuntime::ReadLuaTableNumber("_damageFlags","count",&count)&&count==4);
}
'''


class DamageCallbackFlagsTests(unittest.TestCase):
    def test_lua_receives_full_width_flags(self):
        with tempfile.TemporaryDirectory(prefix='damage-callback-flags-') as tmp:
            binary=build_lua_harness(source_root=fixture.SOURCE,workdir=Path(tmp),
                harness_source=fixture.HARNESS[:fixture.HARNESS.index('int main(')]+MAIN)
            result=subprocess.run([str(binary)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
