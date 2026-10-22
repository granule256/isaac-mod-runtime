"""真实Lua数据生存期：300活实体、房间/活表移动、生成帧改变不丢表。"""
import subprocess,tempfile,unittest,re
from pathlib import Path
from . import test_lua_entity_query as fixture
from .test_support import build_lua_harness
ROOT=Path(__file__).resolve().parents[2]
MAIN=r'''
int main(int argc,char**argv){
 static_cast<void>(kScriptTemplate);static_cast<void>(&HarnessHasCollectible);
 static_cast<void>(&BuildPrelude);static_cast<void>(&ExpectNumber);
 if(argc!=2)return 99;std::string scene=argv[1];unsigned count=scene=="capacity"?300:10;
 CreateBlocks();FillEntities();PublishLists();PublishGame();
 g_Entities.resize(kEntitySlotCount+count);
 g_LiveArrayBytes.assign(count*sizeof(std::uintptr_t)+32,0);
 for(unsigned i=0;i<count;++i){
  unsigned slot=kEntitySlotCount+i;g_Entities[slot].assign(kEntityBlockSize,0);
  FillEntity(static_cast<EntitySlot>(slot),20,i,0,10,10,5,i,950,g_EngineBase+kEntityNpcVtableOffset,0);
  WriteWord(g_LiveArrayBytes,i*sizeof(std::uintptr_t),AddressOf(g_Entities[slot]));
 }
 auto publish=[&](auto& room){PublishEntityList(room,true);
  WriteAt<std::uint32_t>(room,kRoomEntityListOffset+kEntityListLiveCountOffset,count);
  WriteAt<std::uint32_t>(room,kRoomEntityListOffset+kEntityListEffectCountOffset,0);};
 publish(g_RoomBytes);publish(g_RoomBytesSecond);
 LuaRuntime::SetEngineModuleBase(g_EngineBase);LuaRuntime::SetGameBindings(AddressOf(g_OwnerSlotBytes),0x2222);
 std::string script="local count="+std::to_string(count)+R"lua(
 local mod=RegisterMod('entity-data-lifetime',1);local step=0;local entities,data
 mod:AddCallback(1,function()
  step=step+1
  if step==1 then
   entities=Isaac.FindByType(20);assert(#entities==count);data={}
   for i,e in ipairs(entities) do data[i]=e:GetData();data[i].saved=i end
  else
   for i,e in ipairs(entities) do assert(e:GetData()==data[i] and e:GetData().saved==i,'live entity lost data '..i) end
   local aliases=Isaac.FindByType(20)
   for i,e in ipairs(aliases) do assert(e:GetData()==data[i],'entity aliases do not share data') end
  end
 end)
 )lua";
 if(LuaRuntime::InitializeFromBuffer(script.data(),script.size(),"@entity-data.lua")!=LuaRuntime::LuaInitResult::Success)return 1;
 LuaRuntime::DispatchPostUpdate();if(LuaRuntime::TakeCallbackError())return 2;
 std::vector<unsigned char> previous;
 if(scene=="room")WriteWord(g_GameBytes,kGameRoomPointerOffset,AddressOf(g_RoomBytesSecond));
 if(scene=="reorder"){previous=g_LiveArrayBytes;previous.swap(g_LiveArrayBytes);publish(g_RoomBytes);}
 if(scene=="frame")for(unsigned i=0;i<count;++i)WriteAt<unsigned>(g_Entities[kEntitySlotCount+i],kEntitySpawnFrameOffset,951);
 LuaRuntime::DispatchPostUpdate();if(LuaRuntime::TakeCallbackError()){
  char error[512]{};static_cast<void>(LuaRuntime::CopyLastLuaErrorText(error,sizeof(error)));std::printf("scene=%s error=%s\n",scene.c_str(),error);return 3;}
 return 0;
}
'''
class EntityDataLifetimeTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory(prefix='isaac-entity-data-')
  source=fixture.HARNESS[:fixture.HARNESS.index('int main(')]+MAIN
  # 旧夹具的文本reader只在另一构建条件声明；使用公共宿主桩，不复制陈旧签名。
  source=re.sub(r'namespace GameFileReader \{\nTextReadResult[\s\S]*?\n\}\n\}', '', source, count=1)
  cls.binary=build_lua_harness(source_root=fixture.SOURCE,workdir=Path(cls.tmp.name),harness_source=source)
 @classmethod
 def tearDownClass(cls):cls.tmp.cleanup()
 def test_living_entity_identity_survives_capacity_and_container_changes(self):
  for scene in ('capacity','room','reorder','frame'):
   with self.subTest(scene=scene):
    r=subprocess.run([str(self.binary),scene],capture_output=True,text=True)
    self.assertEqual(r.returncode,0,r.stdout+r.stderr)
