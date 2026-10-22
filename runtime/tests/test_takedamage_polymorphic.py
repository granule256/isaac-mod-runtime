"""保存的基类伤害方法接受真实子类视图，走虚表第9槽并返回原生bool。"""
import subprocess,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from . import test_lua_entity_player as fixture
from . import test_support
MAIN=r'''
namespace LuaRuntime{void InstallDamageTarget(std::uintptr_t);}
extern "C" {extern std::uint64_t g_HostEngineCallTrampolineIntegerResult;extern std::uintptr_t g_HostEngineCallTrampolineLastTarget;extern std::uint64_t g_HostEngineCallTrampolineLastIntegers[8];extern double g_HostEngineCallTrampolineLastFloats[8];}
int main(int argc,char**argv){
 if(argc!=2)return 90;
 static_cast<void>(&CorruptVtable);static_cast<void>(&PublishNullCostumes);static_cast<void>(&HarnessHasCollectible);static_cast<void>(&ExpectNumber);static_cast<void>(kScriptTemplate);
 CreateBlocks();FillPlayer(true);PublishOwnerSlot(AddressOf(g_OwnerSlotBytes));WriteWord(g_OwnerSlotBytes,0,AddressOf(g_GameBytes));PublishPlayers({AddressOf(g_PlayerBytes)});
 const int kind=std::atoi(argv[1]);
 const std::uintptr_t vtables[]={0xA34F58,0xA35DB8,0xA37110,0xA36E28,0xA35728,0xA35048,0xA35238,0xA35B48,0xA35CC0,0xA37410,0xA37638,0xA37508};
 const std::uint32_t types[]={10,46,1,5,3,4,1000,8,7,9,2,6};
 const std::uintptr_t methods[]={0x5DCA4,0x122224,0x2A34D0,0x2767B8,0xD8550,0x5DCA4,0x5DCA4,0x5DCA4,0x5DCA4,0x5DCA4,0x5DCA4,0x32FFB0};
 const std::uint32_t guards[]={0xD10343FF,0xD10203FF,0xD107C3FF,0xA9BE7BFD,0xD10203FF,0xD10343FF,0xD10343FF,0xD10343FF,0xD10343FF,0xD10343FF,0xD10343FF,0xD102C3FF};
 auto target=g_PlayerBytes;WriteWord(target,0,g_EngineBase+vtables[kind]);WriteAt<std::uint32_t>(target,kEntityTypeOffset,types[kind]);WriteAt<std::uintptr_t>(g_ModuleBytes,vtables[kind]+9*8,g_EngineBase+methods[kind]);WriteAt<std::uint32_t>(g_ModuleBytes,methods[kind],guards[kind]);
 std::memcpy(g_ModuleBytes.data()+kEntityTakeDamageOffset,kEntityTakeDamageExpectedBytes.data(),kEntityTakeDamageExpectedBytes.size());std::memcpy(g_ModuleBytes.data()+kEntityPlayerTakeDamageOffset,kEntityPlayerTakeDamageExpectedBytes.data(),kEntityPlayerTakeDamageExpectedBytes.size());
 std::memcpy(g_ModuleBytes.data()+kEntityPickupTakeDamageOffset,kEntityPickupTakeDamageExpectedBytes.data(),kEntityPickupTakeDamageExpectedBytes.size());std::memcpy(g_ModuleBytes.data()+kEntitySlotTakeDamageOffset,kEntitySlotTakeDamageExpectedBytes.data(),kEntitySlotTakeDamageExpectedBytes.size());
 LuaRuntime::SetEngineModuleBase(g_EngineBase);LuaRuntime::SetGameBindings(AddressOf(g_OwnerSlotBytes),0x2222);
 const char* script=R"lua(local m=RegisterMod('polymorphic damage',1);local step=0;m:AddCallback(1,function()
 step=step+1;local e=DamageTestTarget();local saved=e.TakeDamage;local result=saved(e,1.25,0x100000003,EntityRef(Isaac.GetPlayer()),7)
 assert(type(result)=='boolean','TakeDamage must return bool');assert(result==(step==1),'native bool must be preserved')
 _damage={ok=step}
 end))lua";
 if(LuaRuntime::InitializeFromBuffer(script,std::strlen(script),"@polymorphic-damage.lua")!=LuaRuntime::LuaInitResult::Success)return 1;LuaRuntime::InstallDamageTarget(AddressOf(target));
 for(unsigned step=0;step<2;++step){
  auto before=g_HostEngineCallTrampolineCalls;g_HostEngineCallTrampolineIntegerResult=step==0?1:0;LuaRuntime::DispatchPostUpdate();
  if(LuaRuntime::TakeCallbackError()){LuaRuntime::LuaErrorHistoryEntryView e[8]{};auto n=LuaRuntime::CopyLuaErrorHistory(e,8);for(std::size_t i=0;i<n;++i)std::printf("DAMAGE_FAIL %s\n",e[i].text);return 2;}
  if(g_HostEngineCallTrampolineCalls!=before+1||g_HostEngineCallTrampolineLastTarget!=g_EngineBase+methods[kind]||g_HostEngineCallTrampolineLastIntegers[0]!=AddressOf(target)||g_HostEngineCallTrampolineLastIntegers[1]!=0x100000003ULL||g_HostEngineCallTrampolineLastIntegers[3]!=7)return 3;
  float amount=0;std::memcpy(&amount,g_HostEngineCallTrampolineLastFloats,sizeof(amount));if(amount!=1.25f)return 4;
 }
 return 0;
}
'''
class PolymorphicDamageTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory(prefix='isaac-polymorphic-damage-');source=fixture.SOURCE/'lua_runtime.cpp';copy=Path(cls.tmp.name)/'runtime.cpp'
  copy.write_text(source.read_text()+r'''
namespace LuaRuntime {
int DamageTestTarget(lua_State*L){auto p=reinterpret_cast<std::uintptr_t>(lua_touserdata(L,lua_upvalueindex(1)));isaac::runtime::PushEntityCallbackArgument(L,p);return 1;}
void InstallDamageTarget(std::uintptr_t p){lua_pushlightuserdata(g_LuaState,reinterpret_cast<void*>(p));lua_pushcclosure(g_LuaState,DamageTestTarget,1);lua_setglobal(g_LuaState,"DamageTestTarget");}
}
''')
  sources=tuple(copy if p==source else p for p in test_support.layered_lua_runtime_sources(fixture.SOURCE));flags=tuple(f for f in test_support.HARNESS_COMPILE_FLAGS if not f.startswith('-DEXL_DIAGNOSTIC_STAGE='))
  with patch.object(test_support,'HARNESS_COMPILE_FLAGS',flags),patch.object(test_support,'layered_lua_runtime_sources',return_value=sources):cls.binary=test_support.build_lua_harness(source_root=fixture.SOURCE,workdir=Path(cls.tmp.name),harness_source=fixture.HARNESS[:fixture.HARNESS.index('int main(')]+MAIN)
 @classmethod
 def tearDownClass(cls):cls.tmp.cleanup()
 def test_saved_damage_method_uses_each_dynamic_native_target(self):
  for kind in range(12):
   with self.subTest(kind=kind):
    r=subprocess.run([str(self.binary),str(kind)],capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
