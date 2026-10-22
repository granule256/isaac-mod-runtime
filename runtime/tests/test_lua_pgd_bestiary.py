"""真实Lua图鉴计数：原生目标、signed返回、参数转换与失效拒绝。"""
import subprocess
import tempfile
import unittest
from pathlib import Path
from . import test_lua_persistent_game_data as pgd
from .test_support import build_lua_harness

MAIN = r'''
extern "C" {
 extern std::uint32_t g_HostEngineCallTrampolineCalls;
 extern std::uintptr_t g_HostEngineCallTrampolineLastTarget;
 extern std::uint64_t g_HostEngineCallTrampolineLastIntegers[8];
 extern std::uint64_t g_HostEngineCallTrampolineIntegerResult;
}
int main(){
 PublishFakeMemory();LuaRuntime::SetGameBindings(AddressOf(g_OwnerSlotBytes),0x2222);
 const unsigned offsets[3]={0x43b158,0x43b820,0x43b66c};
 const unsigned char bytes[3][16]={BESTIARY_BYTES};
 for(unsigned i=0;i<3;++i)std::memcpy(g_ModuleBytes.data()+offsets[i],bytes[i],16);
 const char* script=R"lua(
 local data=Isaac.GetPersistentGameData();local step=0
 local methods={'GetBestiaryKillCount','GetBestiaryDeathCount','GetBestiaryEncounterCount'}
 local mod=RegisterMod('bestiary',1)
 for _,name in ipairs(methods) do assert(type(data[name])=='function',name..' missing') end
 mod:AddCallback(1,function()
  step=step+1
  if step<=15 then
   local fn=data[methods[(step-1)//5+1]];local scene=(step-1)%5+1
   if scene==1 then assert(fn(data,10,20)==-7)
   elseif scene==2 then assert(fn(data,'10','4294967297')==-7)
   elseif scene==3 then assert(fn(data,-2,4294967295)==-7)
   elseif scene==4 then assert(not pcall(fn,data,{},20))
   else assert(not pcall(fn,data,10)) end
  elseif step<=18 then assert(not pcall(data[methods[step-15]],data,10,20))
  else assert(not pcall(data[methods[step-18]],data,10,20) and Isaac.GetPersistentGameData()==nil) end
 end)
 )lua";
 if(LuaRuntime::InitializeFromBuffer(script,std::strlen(script),"@bestiary.lua")!=LuaRuntime::LuaInitResult::Success){
  std::fprintf(stderr,"bestiary Lua initialization failed\n");return 1;
 }
 g_HostEngineCallTrampolineIntegerResult=0xfffffff9U;
 for(unsigned step=1;step<=21;++step){
  if(step==16)for(unsigned i=0;i<3;++i)g_ModuleBytes[offsets[i]+15]^=1;
  if(step==19)WriteAt<std::uintptr_t>(g_ManagerSlotBytes,0,0);
  auto before=g_HostEngineCallTrampolineCalls;
  LuaRuntime::DispatchPostUpdate();
  if(LuaRuntime::TakeCallbackError()){std::fprintf(stderr,"Lua callback error step=%u\n",step);return 2;}
  if(step<=15&&(step-1)%5<3){
   unsigned index=(step-1)/5,scene=(step-1)%5;
   auto* args=g_HostEngineCallTrampolineLastIntegers;
   if(g_HostEngineCallTrampolineCalls!=before+1||g_HostEngineCallTrampolineLastTarget!=g_EngineBase+offsets[index]||
    args[0]!=AddressOf(g_ManagerBytes)+0x18||args[1]!=(scene==2?0xfffffffeU:10U)||
    args[2]!=(scene==0?20U:(scene==1?1U:0xffffffffU)))return 3;
  }else if(g_HostEngineCallTrampolineCalls!=before)return 4;
 }
 return 0;
}
'''

class BestiaryTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory(prefix='isaac-bestiary-')
  fixture=pgd.fixture
  source=fixture.HARNESS[:fixture.HARNESS.index('int main(')]+MAIN
  roots=[fixture.SOURCE.parents[1],Path('/Users/kelinls/code/github/isaac mod')]
  nro=next((p for r in roots for p in r.glob('The Binding of Isaac_ Afterbirth+*/Program #0/1/.nro/Repentance.nro')),None)
  if nro is None:raise RuntimeError('缺少已审计NRO')
  blob=nro.read_bytes()
  source=source.replace('BESTIARY_BYTES',','.join('{'+','.join(str(v) for v in blob[o:o+16])+'}' for o in (0x43b158,0x43b820,0x43b66c)))
  for name in ('CURRENT_TINT','CURRENT_SHIFT','DEFAULT_TINT','SPLAT_TINT'):
   for i,v in enumerate(getattr(fixture,name)):source=source.replace(f'{name}_{i}',repr(v))
  for name in ('COLLECTIBLE_COUNT','TRINKET_COUNT','ENTITY_DEFAULT_COLOR_OFFSET','ENTITY_SPLAT_COLOR_OFFSET'):
   source=source.replace(name,str(getattr(fixture,name)))
  cls.binary=build_lua_harness(source_root=fixture.SOURCE,workdir=Path(cls.tmp.name),harness_source=source)
 @classmethod
 def tearDownClass(cls):cls.tmp.cleanup()
 def test_three_native_counts_and_rejection_paths(self):
  result=subprocess.run([str(self.binary)],capture_output=True,text=True)
  self.assertEqual(result.returncode,0,result.stdout+result.stderr)
