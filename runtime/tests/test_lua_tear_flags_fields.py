"""玩家标志按完整128位写回，查询是值拷贝；泪弹setter走原生副作用链。"""
import subprocess,tempfile,unittest
from pathlib import Path
from . import test_lua_batch343_get_color_and_lists as f
from .test_support import build_lua_harness
MAIN=r'''
extern "C" {extern std::uint64_t g_HostEngineCallTrampolineLastIntegers[8];extern std::uintptr_t g_HostEngineCallTrampolineLastTarget;}
int main(){PublishFakeMemory();LuaRuntime::SetGameBindings(AddressOf(g_OwnerSlotBytes),0x2222);
 const unsigned char entry[16]={TEAR_BYTES};std::memcpy(g_ModuleBytes.data()+0x33baa0,entry,16);
 const char* s=R"lua(
 local m=RegisterMod('flags',1);local p=Isaac.GetPlayer(0);local step=0
 m:AddCallback(1,function()
  step=step+1
  local flags=TearFlags.TEAR_POISON|TearFlags.TEAR_FREEZE|TearFlags.TEAR_LUDOVICO
  if step==1 then
   p.TearFlags=flags;assert(p.TearFlags==flags)
   local copy=p.TearFlags;copy:Set(90,true);assert(not p.TearFlags:Get(90))
  elseif step==2 then
   p:ToTear().TearFlags=flags;assert(p:ToTear().TearFlags:Get(4))
  end
 end)
 )lua";
 if(LuaRuntime::InitializeFromBuffer(s,std::strlen(s),"@tear-fields.lua")!=LuaRuntime::LuaInitResult::Success)return 1;
 LuaRuntime::DispatchPostUpdate();if(LuaRuntime::TakeCallbackError())return 2;
 std::uint64_t lo=0,hi=0;std::memcpy(&lo,g_PlayerBytes.data()+0x1858,8);std::memcpy(&hi,g_PlayerBytes.data()+0x1860,8);if(lo!=48||hi!=0x8000000000000000ULL)return 3;
 WriteAt<std::uintptr_t>(g_PlayerBytes,0,g_EngineBase+kEntityTearVtableOffset);WriteAt<std::uint32_t>(g_PlayerBytes,kEntityTypeOffset,2);WriteAt<std::uint64_t>(g_PlayerBytes,0x418,16);
 LuaRuntime::DispatchPostUpdate();if(LuaRuntime::TakeCallbackError())return 4;
 if(g_HostEngineCallTrampolineLastTarget!=g_EngineBase+0x33baa0||g_HostEngineCallTrampolineLastIntegers[0]!=AddressOf(g_PlayerBytes)||g_HostEngineCallTrampolineLastIntegers[1]!=48||g_HostEngineCallTrampolineLastIntegers[2]!=0x8000000000000000ULL)return 5;
 return 0;
}
'''
class TearFlagFieldTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory(prefix='isaac-tearflags-fields-');source=f.HARNESS[:f.HARNESS.index('int main(')]+MAIN
  nro=f.SOURCE.parents[1]/'The Binding of Isaac_ Afterbirth+ 1.7.9b [010021C000B6A800][v524288][UPD]/Program #0/1/.nro/Repentance.nro';source=source.replace('TEAR_BYTES',','.join(str(b) for b in nro.read_bytes()[0x33baa0:0x33bab0]))
  for name in ('CURRENT_TINT','CURRENT_SHIFT','DEFAULT_TINT','SPLAT_TINT'):
   for i,v in enumerate(getattr(f,name)):source=source.replace(f'{name}_{i}',repr(v))
  for name in ('COLLECTIBLE_COUNT','TRINKET_COUNT','ENTITY_DEFAULT_COLOR_OFFSET','ENTITY_SPLAT_COLOR_OFFSET'):source=source.replace(name,str(getattr(f,name)))
  cls.binary=build_lua_harness(source_root=f.SOURCE,workdir=Path(cls.tmp.name),harness_source=source)
 @classmethod
 def tearDownClass(cls):cls.tmp.cleanup()
 def test_full_flags_write_copy_and_native_setter(self):
  r=subprocess.run([str(self.binary)],capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
if __name__=='__main__':unittest.main()
