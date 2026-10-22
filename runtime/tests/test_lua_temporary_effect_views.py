"""三个效果查询与列表返回真实引擎数据，重排后旧句柄失效，清空实参匹配PC。"""
import subprocess,tempfile,unittest
from pathlib import Path
from .test_support import build_lua_harness
from .test_lua_entity_player import HARNESS,SOURCE
MAIN=r'''
extern "C" {extern std::uintptr_t g_HostEngineCallTrampolineLastTarget;extern std::uint64_t g_HostEngineCallTrampolineLastIntegers[8];}
int main(int argc, char**){
 static_cast<void>(&HarnessHasCollectible);static_cast<void>(&ExpectNumber);
 static_cast<void>(&CorruptVtable);static_cast<void>(kScriptTemplate);
 CreateBlocks();FillPlayer(true);LuaRuntime::SetEngineModuleBase(g_EngineBase);
 PublishOwnerSlot(AddressOf(g_OwnerSlotBytes));WriteWord(g_OwnerSlotBytes,0,AddressOf(g_GameBytes));PublishPlayers({AddressOf(g_PlayerBytes)});
 PublishNullCostumes();
 std::vector<unsigned char> configs[3],items(24),effects(48),replacement(32);
 for(int i=0;i<3;++i){configs[i].assign(256,0);WriteAt<std::uint32_t>(configs[i],0,i==0?1:(i==1?2:0));WriteAt<std::int32_t>(configs[i],4,7);
 WriteAt<std::uintptr_t>(items,8*i,AddressOf(configs[i]));WriteAt<std::uintptr_t>(effects,16*i,AddressOf(configs[i]));
 WriteAt<std::int32_t>(effects,16*i+8,2+i);WriteAt<std::int32_t>(effects,16*i+12,-1-i);}
 for(int i=0;i<3;++i){auto begin=i==0?kItemConfigCollectibleBeginOffset:(i==1?kItemConfigTrinketBeginOffset:kItemConfigNullItemBeginOffset);
 WriteAt<std::uintptr_t>(g_ManagerBytes,kManagerItemConfigOffset+begin,AddressOf(items)+8*i);
 WriteAt<std::uintptr_t>(g_ManagerBytes,kManagerItemConfigOffset+begin+8,AddressOf(items)+8*i+8);}
 auto publish=[&](std::vector<unsigned char>& v){WriteAt<std::uintptr_t>(g_PlayerBytes,0x18d8+8,AddressOf(v));WriteAt<std::uintptr_t>(g_PlayerBytes,0x18d8+16,AddressOf(v)+v.size());};publish(effects);
 const unsigned char clearBytes[]={CLEAR_BYTES};std::memcpy(g_ModuleBytes.data()+0x4a6e60,clearBytes,16);
 if(argc>1){
  const std::uint32_t word=0xD100C3FF;
  const std::uintptr_t offsets[]={0x4a6ba0,0x4a6c00,0x4a6c60};
  for(auto off:offsets)std::memcpy(g_ModuleBytes.data()+off,&word,4);
  const char* removeScript=R"lua(
local m=RegisterMod('remove-effects',1);local step=0
local methods={'RemoveCollectibleEffect','RemoveTrinketEffect','RemoveNullEffect'}
m:AddCallback(1,function()
 step=step+1;local e=Isaac.GetPlayer(0):GetEffects();local name=methods[(step-1)%3+1]
 if step<=3 then e[name](e,7,-1) else e[name](e,7) end
end)
)lua";
  if(LuaRuntime::InitializeFromBuffer(removeScript,std::strlen(removeScript),"@remove-effects.lua")!=LuaRuntime::LuaInitResult::Success)return 40;
  for(int i=0;i<6;++i){LuaRuntime::DispatchPostUpdate();if(LuaRuntime::TakeCallbackError())return 41;
   if(g_HostEngineCallTrampolineLastTarget!=g_EngineBase+offsets[i%3]||g_HostEngineCallTrampolineLastIntegers[0]!=AddressOf(g_PlayerBytes)+0x18d8||g_HostEngineCallTrampolineLastIntegers[1]!=7||g_HostEngineCallTrampolineLastIntegers[2]!=(i<3?0xffffffffU:1U))return 42;
  }
  return 0;
 }
 const char* script=R"lua(
local m=RegisterMod('effects',1);_probe={step=0}
local e,list,old
m:AddCallback(1,function()
 _probe.step=_probe.step+1
 if _probe.step==1 then
  e=Isaac.GetPlayer(0):GetEffects();list=e:GetEffectsList();old=e:GetCollectibleEffect(7)
  assert(type(old)=='userdata' and old.Count==2 and old.Cooldown==-1 and old.Item.ID==7 and old.Item.Type==1)
  assert(e:GetTrinketEffect(7).Count==3 and e:GetNullEffect(7).Count==4)
  assert(e:GetCollectibleEffect(999)==nil and e:GetNullEffect(999)==nil)
  assert(getmetatable(TemporaryEffect).__class==getmetatable(old) and getmetatable(EffectList).__class==getmetatable(list))
  assert(type(list)=='userdata' and list.Size==3 and #list==3 and list:Get(0).Count==2 and list:Get(2).Cooldown==-3)
  assert(not pcall(function() list:Get(-1) end) and not pcall(function() list:Get(3) end))
  assert(not pcall(function() old.Count=9 end) and not pcall(function() list.Size=9 end))
 elseif _probe.step==2 then assert(old.Count==9 and old.Cooldown==-8)
 elseif _probe.step==3 then assert(old.Count==nil and list.Size==2 and list:Get(0).Count==3)
 elseif _probe.step==4 then assert(e:GetTrinketEffect(7)==nil and list.Size==2)
 elseif _probe.step==5 then e:ClearEffects()
 elseif _probe.step==6 then e:ClearEffects(true)
 elseif _probe.step==7 then e:ClearEffects(nil)
 elseif _probe.step==8 then assert(not pcall(function() e:ClearEffects() end))
 elseif _probe.step==9 then _probe.compacted=list:Get(0)
 elseif _probe.step==10 then assert(_probe.compacted.Count==nil and list:Get(0).Count==4)
 elseif _probe.step==11 then assert(not pcall(function() return list.Size end))
 elseif _probe.step==12 then assert(not pcall(function() return #list end))
 end
end)
)lua";
 if(LuaRuntime::InitializeFromBuffer(script,std::strlen(script),"@effects.lua")!=LuaRuntime::LuaInitResult::Success)return 1;
 auto run=[](){LuaRuntime::DispatchPostUpdate();return !LuaRuntime::TakeCallbackError();};
 if(!run())return 2;
 WriteAt<std::int32_t>(effects,8,9);WriteAt<std::int32_t>(effects,12,-8);if(!run())return 3;
 std::memcpy(replacement.data(),effects.data()+16,32);publish(replacement);if(!run())return 4;
 WriteAt<std::uint8_t>(g_PlayerBytes,0x18d8+0x21,1);if(!run())return 5;
 if(!run())return 6;
 if(g_HostEngineCallTrampolineLastIntegers[1]!=0)return 9;
 if(!run())return 10;
 if(g_HostEngineCallTrampolineLastTarget!=g_EngineBase+0x4a6e60||g_HostEngineCallTrampolineLastIntegers[0]!=AddressOf(g_PlayerBytes)+0x18d8||g_HostEngineCallTrampolineLastIntegers[1]!=1)return 7;
 if(!run()||g_HostEngineCallTrampolineLastIntegers[1]!=0)return 11;
 g_ModuleBytes[0x4a6e60]^=1;if(!run())return 8;
 if(!run())return 12;
 std::memcpy(replacement.data(),replacement.data()+16,16);if(!run())return 13;
 WriteAt<std::uintptr_t>(g_PlayerBytes,0x18d8+16,AddressOf(replacement)+31);if(!run())return 14;
 CorruptVtable();if(!run())return 15;
 return 0;
}
'''
class TemporaryEffectViewTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory(prefix='isaac-temp-effects-')
  # 原生指纹独立从镜像读取；没有真镜像时不能假装本层证据通过。
  root=SOURCE.parents[1]
  nro=root/'The Binding of Isaac_ Afterbirth+ 1.7.9b [010021C000B6A800][v524288][UPD]/Program #0/1/.nro/Repentance.nro'
  if not nro.is_file():raise unittest.SkipTest('需要已审计游戏镜像')
  clear=','.join(str(v) for v in nro.read_bytes()[0x4a6e60:0x4a6e70])
  cls.binary=build_lua_harness(source_root=SOURCE,workdir=Path(cls.tmp.name),harness_source=HARNESS[:HARNESS.index('int main(')].replace('namespace GameFileReader {\nTextReadResult ReadTextFile(const Bindings&, const char*, u8*, std::size_t, std::size_t*) {\n    return TextReadResult::OpenFailed;\n}\n}\n', '')+MAIN.replace('CLEAR_BYTES',clear))
 @classmethod
 def tearDownClass(cls):cls.tmp.cleanup()
 def test_real_values_filter_and_lifetime(self):
  r=subprocess.run([str(self.binary)],capture_output=True,text=True)
  self.assertEqual(r.returncode,0,r.stdout+r.stderr)
 def test_remove_all_and_defaults(self):
  r=subprocess.run([str(self.binary),'remove'],capture_output=True,text=True)
  self.assertEqual(r.returncode,0,r.stdout+r.stderr)
if __name__=='__main__' :unittest.main()
