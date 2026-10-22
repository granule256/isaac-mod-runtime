"""StageAPI实际查询形状、PGD真实对象位置、整数ABI和入口拒绝。"""
import subprocess,tempfile,unittest
from pathlib import Path
from . import test_lua_batch343_get_color_and_lists as fixture
from .test_support import build_lua_harness
MAIN=r'''
extern "C" {
 extern std::uint32_t g_HostEngineCallTrampolineCalls;
 extern std::uintptr_t g_HostEngineCallTrampolineLastTarget;
 extern std::uint64_t g_HostEngineCallTrampolineLastIntegers[8];
 extern std::uint64_t g_HostEngineCallTrampolineIntegerResult;
}
int main(){
 PublishFakeMemory();LuaRuntime::SetGameBindings(AddressOf(g_OwnerSlotBytes),0x2222);
 const unsigned char bytes[16]={UNLOCKED_BYTES};std::memcpy(g_ModuleBytes.data()+0x439654,bytes,16);
 const char* script=R"lua(
 local m=RegisterMod('pgd',1);local data=Isaac.GetPersistentGameData();local step=0
 assert(type(data)=='userdata')
 m:AddCallback(1,function()
  step=step+1
  if step==1 then assert(not data:Unlocked(4))
  elseif step==2 then assert(data:Unlocked('4'))
  elseif step==3 then assert(data:Unlocked(-2))
  elseif step==4 then assert(data:Unlocked(4294967295))
  elseif step==5 then assert(not pcall(function() data:Unlocked('bad') end))
  elseif step==6 then assert(not pcall(function() data:Unlocked(4) end))
  elseif step==7 then assert(not pcall(function() data:Unlocked(4) end) and Isaac.GetPersistentGameData()==nil)
  end
 end)
 )lua";
 if(LuaRuntime::InitializeFromBuffer(script,std::strlen(script),"@pgd.lua")!=LuaRuntime::LuaInitResult::Success)return 1;
 auto run=[](){LuaRuntime::DispatchPostUpdate();return !LuaRuntime::TakeCallbackError();};
 if(!run())return 2;
 if(g_HostEngineCallTrampolineLastTarget!=g_EngineBase+0x439654||g_HostEngineCallTrampolineLastIntegers[0]!=AddressOf(g_ManagerBytes)+0x18||g_HostEngineCallTrampolineLastIntegers[1]!=4)return 3;
 g_HostEngineCallTrampolineIntegerResult=1;if(!run())return 4;
 if(!run()||g_HostEngineCallTrampolineLastIntegers[1]!=0xfffffffeU)return 5;
 if(!run()||g_HostEngineCallTrampolineLastIntegers[1]!=0xffffffffU)return 6;
 auto calls=g_HostEngineCallTrampolineCalls;
 if(!run()||g_HostEngineCallTrampolineCalls!=calls)return 7;
 g_ModuleBytes[0x439654]^=1;if(!run()||g_HostEngineCallTrampolineCalls!=calls)return 8;
 WriteAt<std::uintptr_t>(g_ManagerSlotBytes,0,0);if(!run()||g_HostEngineCallTrampolineCalls!=calls)return 9;
 return 0;
}
'''
class PersistentGameDataTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory(prefix='isaac-pgd-')
  source=fixture.HARNESS[:fixture.HARNESS.index('int main(')]+MAIN
  root=fixture.SOURCE.parents[1]
  nro=root/'The Binding of Isaac_ Afterbirth+ 1.7.9b [010021C000B6A800][v524288][UPD]/Program #0/1/.nro/Repentance.nro'
  if not nro.exists():raise unittest.SkipTest('需要已审计游戏镜像核对入口')
  source=source.replace('UNLOCKED_BYTES',','.join(str(v) for v in nro.read_bytes()[0x439654:0x439664]))
  for name in ('CURRENT_TINT','CURRENT_SHIFT','DEFAULT_TINT','SPLAT_TINT'):
   for i,v in enumerate(getattr(fixture,name)):source=source.replace(f'{name}_{i}',repr(v))
  for name in ('COLLECTIBLE_COUNT','TRINKET_COUNT','ENTITY_DEFAULT_COLOR_OFFSET','ENTITY_SPLAT_COLOR_OFFSET'):source=source.replace(name,str(getattr(fixture,name)))
  cls.binary=build_lua_harness(source_root=fixture.SOURCE,workdir=Path(cls.tmp.name),harness_source=source)
 @classmethod
 def tearDownClass(cls):cls.tmp.cleanup()
 def test_real_owner_native_query_and_failures(self):
  r=subprocess.run([str(self.binary)],capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
if __name__=='__main__':unittest.main()
