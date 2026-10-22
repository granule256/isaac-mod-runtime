"""PC固定exe：非法玩家下标回第一玩家，RNG种子转原生uint32。"""
import subprocess,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from . import test_lua_entity_player as fixture
from . import test_support
MAIN=r'''
void HostSeed(void* object,std::uint32_t seed,std::uint32_t shift){std::uint32_t values[4]={seed,shift,shift+1,shift+2};std::memcpy(object,values,sizeof(values));}
void HostNext(void*){}
int main(int argc,char**argv){
 if(argc!=2)return 90;
 static_cast<void>(&CorruptVtable);static_cast<void>(&PublishNullCostumes);static_cast<void>(&HarnessHasCollectible);static_cast<void>(&ExpectNumber);static_cast<void>(kScriptTemplate);
 CreateBlocks();FillPlayer(true);PublishOwnerSlot(AddressOf(g_OwnerSlotBytes));WriteWord(g_OwnerSlotBytes,0,AddressOf(g_GameBytes));
 auto second=g_PlayerBytes;WriteAt<std::uint32_t>(second,kEntityPlayerTypeOffset,99);PublishPlayers({AddressOf(g_PlayerBytes),AddressOf(second)});
 LuaRuntime::SetEngineModuleBase(g_EngineBase);LuaRuntime::SetGameBindings(AddressOf(g_OwnerSlotBytes),0x2222);LuaRuntime::SetRngBindings(reinterpret_cast<uintptr_t>(&HostSeed),reinterpret_cast<uintptr_t>(&HostNext));
 std::string script="local m=RegisterMod('PC conversion',1);m:AddCallback(1,function() ";
 if(!std::strcmp(argv[1],"seed"))script+=R"lua(
 local r=RNG();r:SetSeed(4294967298,1);assert(r:GetSeed()==2,'overflow seed must wrap uint32')
 r:SetSeed(-1,1);assert(r:GetSeed()==4294967295,'negative seed must wrap uint32')
 r:SetSeed(8589934595,1);assert(r:GetSeed()==3)
 assert(not pcall(function()r:SetSeed('bad',1)end))
)lua";
 else{
 const std::string get=!std::strcmp(argv[1],"isaac")?"Isaac.GetPlayer(":"Game():GetPlayer(";
 script+="local function player(i)return "+get+"i)end;assert(player(0):GetPlayerType()==0);assert(player(1):GetPlayerType()==99);for _,i in ipairs({-20,-1,2,20,99})do assert(player(i):GetPlayerType()==0,'invalid player index must resolve first player')end;";
 }
 script+="_conversion={ok=1};end)";
 if(LuaRuntime::InitializeFromBuffer(script.data(),script.size(),"@pc-conversion.lua")!=LuaRuntime::LuaInitResult::Success)return 1;
 LuaRuntime::DispatchPostUpdate();if(LuaRuntime::TakeCallbackError()){LuaRuntime::LuaErrorHistoryEntryView e[8]{};auto n=LuaRuntime::CopyLuaErrorHistory(e,8);for(std::size_t i=0;i<n;++i)std::printf("CONVERSION_FAIL %s\n",e[i].text);return 2;}
 double ok=0;return LuaRuntime::ReadLuaTableNumber("_conversion","ok",&ok)==0&&ok==1?0:3;
}
'''
class PlayerFallbackSeedCastTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory(prefix='isaac-pc-conversion-')
  flags=tuple(f for f in test_support.HARNESS_COMPILE_FLAGS if not f.startswith('-DEXL_DIAGNOSTIC_STAGE='))
  with patch.object(test_support,'HARNESS_COMPILE_FLAGS',flags):
   cls.binary=test_support.build_lua_harness(source_root=fixture.SOURCE,workdir=Path(cls.tmp.name),harness_source=fixture.HARNESS[:fixture.HARNESS.index('int main(')]+MAIN)
 @classmethod
 def tearDownClass(cls):cls.tmp.cleanup()
 def test_pc_conversion(self):
  for case in ['isaac','game','seed']:
   with self.subTest(case=case):
    r=subprocess.run([str(self.binary),case],capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
