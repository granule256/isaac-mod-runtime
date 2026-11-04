"""Transformation progress must consume native trinket effects, including swallowed copies."""
import subprocess
import tempfile
import unittest
from pathlib import Path

from . import test_lua_entity_query as fixture
from .test_support import build_lua_harness

MAIN = r'''
extern "C" {
extern std::uint32_t g_HostEngineCallTrampolineCalls;
extern std::uint64_t g_HostEngineCallTrampolineIntegerResult;
extern std::uintptr_t g_HostEngineCallTrampolineLastTarget;
extern std::uint64_t g_HostEngineCallTrampolineLastIntegers[8];
}
int main(int argc,char**argv) {
 if(argc!=2)return 99;
 static_cast<void>(kScriptTemplate);static_cast<void>(&HarnessHasCollectible);
 static_cast<void>(&BuildPrelude);static_cast<void>(&ExpectNumber);
 CreateBlocks();FillEntities();PublishLists();PublishGame();PublishEntityList(g_RoomBytes,true);
 const std::string scene=argv[1];
 const unsigned char guard[]={0xff,0x43,0x01,0xd1,0xfd,0x7b,0x01,0xa9,0xfd,0x43,0x00,0x91,0xf8,0x5f,0x02,0xa9};
 std::memcpy(g_ModuleBytes.data()+0x29b030,guard,sizeof(guard));
 std::vector<unsigned char> smelted(170*4);
 WriteWord(g_Entities[kPlayer],kEntityPlayerSmeltedTrinketBeginOffset,AddressOf(smelted));
 WriteWord(g_Entities[kPlayer],kEntityPlayerSmeltedTrinketEndOffset,AddressOf(smelted)+smelted.size());
 if(scene=="swallowed")WriteAt<std::int16_t>(smelted,169*4,1);
 WriteAt<std::uint32_t>(g_Entities[kPlayer],kEntityPlayerTrinketOffset,
                       scene=="golden"?0x80a9:scene=="boosted"?169:0);
 WriteAt<std::uint32_t>(g_Entities[kPlayer],kEntityPlayerTrinketOffset+4,0);
 if(scene=="badguard")g_ModuleBytes[0x29b038]^=1;
 LuaRuntime::SetEngineModuleBase(g_EngineBase);
 LuaRuntime::SetGameBindings(g_EngineBase+kGameOwnerGlobalSlotOffset,0x2222);
 g_HostEngineCallTrampolineIntegerResult=scene=="golden"||scene=="boosted"?2:1;
 const char* script=R"lua(
 local m=RegisterMod('trinket progress',1)
 m:AddCallback(1,function()
  local p=Isaac.GetPlayer(0)
  assert(p:GetTrinketMultiplier(0)==0 and p:GetTrinketMultiplier(-1)==0)
  assert(p:GetTrinketMultiplier(32767)==0)
  _trinket={ok=pcall(function()return p:GetTrinketMultiplier("169")end) and 1 or 0}
  if _trinket.ok==1 then _trinket.progress=p:GetTrinketMultiplier(169) end
 end)
 )lua";
 if(LuaRuntime::InitializeFromBuffer(script,std::strlen(script),"@trinket-progress.lua")!=LuaRuntime::LuaInitResult::Success)return 1;
 const auto before=g_HostEngineCallTrampolineCalls;
 LuaRuntime::DispatchPostUpdate();
 if(LuaRuntime::TakeCallbackError())return 2;
 double ok=0,progress=0;
 if(LuaRuntime::ReadLuaTableNumber("_trinket","ok",&ok))return 3;
 if(scene=="badguard")return ok==0&&g_HostEngineCallTrampolineCalls==before?0:4;
 if(ok!=1||LuaRuntime::ReadLuaTableNumber("_trinket","progress",&progress)||
    progress!=static_cast<double>(g_HostEngineCallTrampolineIntegerResult))return 5;
 return g_HostEngineCallTrampolineCalls==before+2&&
        g_HostEngineCallTrampolineLastTarget==g_EngineBase+0x29b030&&
        g_HostEngineCallTrampolineLastIntegers[0]==AddressOf(g_Entities[kPlayer])&&
        g_HostEngineCallTrampolineLastIntegers[1]==169?0:6;
}
'''


class TrinketMultiplierTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="isaac-trinket-multiplier-")
        cls.binary = build_lua_harness(
            source_root=fixture.SOURCE, workdir=Path(cls.tmp.name),
            harness_source=fixture.HARNESS[:fixture.HARNESS.index("int main(")] + MAIN)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_native_multiplier_and_entry_guard(self):
        for scene in ("swallowed", "golden", "boosted", "badguard"):
            with self.subTest(scene=scene):
                result = subprocess.run([str(self.binary), scene], capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
