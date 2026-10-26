"""44号必须来自原生正常完成位置，Manager循环不能代替实体Update。"""
import subprocess,tempfile,unittest,re
from pathlib import Path
from . import test_lua_entity_query as fixture
from .test_support import build_lua_harness
ROOT=Path(__file__).resolve().parents[2]
MAIN=r'''
#include <cstdio>
#include <cstring>
int main(int argc,char**argv){
 if(argc!=2)return 99;const std::string mode=argv[1];
 static_cast<void>(kScriptTemplate);static_cast<void>(&HarnessHasCollectible);static_cast<void>(&BuildPrelude);static_cast<void>(&ExpectNumber);
 CreateBlocks();FillEntities();PublishLists();PublishGame();PublishEntityList(g_RoomBytes,true);
 WriteWord(g_Entities[kEnemyA],0,g_EngineBase+kEntityProjectileVtableOffset);
 WriteAt<std::uint32_t>(g_Entities[kEnemyA],kEntityTypeOffset,9);
 WriteAt<std::uint32_t>(g_Entities[kEnemyA],kEntityVariantOffset,8);
 LuaRuntime::SetEngineModuleBase(g_EngineBase);LuaRuntime::SetGameBindings(g_EngineBase+kGameOwnerGlobalSlotOffset,0x2222);
 const char*script=R"lua(
initCount=0;count=0;bad=0;order='';local m=RegisterMod("projectile-update",1)
m:AddCallback(43,function()initCount=initCount+1 end,8)
m:AddPriorityCallback(44,-10,function(_,p)order=order..'E';assert(p.Type==9 and p.Variant==8 and initCount==1);count=count+1;orderCode=(orderCode or 0)*10+1 end,8)
m:AddCallback(44,function()order=order..'L';orderCode=(orderCode or 0)*10+2 end,8)
m:AddCallback(44,function()bad=bad+1 end,99)
)lua";
 if(LuaRuntime::InitializeFromBuffer(script,std::strlen(script),"@projectile-boundary.lua")!=LuaRuntime::LuaInitResult::Success)return 1;
 for(unsigned i=0;i<8;++i)LuaRuntime::DispatchPostUpdate();
 double count{};if(!LuaRuntime::ReadLuaGlobalNumber("count",&count))return 2;
 std::printf("MANAGER_ONLY_CALLBACKS=%.0f EXPECTED=0\n",count);
 if(count!=0)return 3;
 double init{};if(!LuaRuntime::ReadLuaGlobalNumber("initCount",&init)||init!=0){std::printf("MANAGER_ONLY_INIT=%.0f EXPECTED=0\n",init);return 7;}
 if(mode=="native"){
  LuaRuntime::DispatchPostProjectileInit(AddressOf(g_Entities[kEnemyA]));
  // 同一Game帧的两次真实完成通知必须分别派发；按帧号去重会在此失败。
  for(unsigned i=0;i<2;++i)LuaRuntime::DispatchPostProjectileUpdate(AddressOf(g_Entities[kEnemyA]));
  if(!LuaRuntime::ReadLuaGlobalNumber("count",&count)||count!=2)return 4;
  if(!LuaRuntime::ReadLuaGlobalNumber("initCount",&init)||init!=1)return 8;
  double sequence{};if(!LuaRuntime::ReadLuaGlobalNumber("orderCode",&sequence)||sequence!=1212)return 9;
  double bad{};if(!LuaRuntime::ReadLuaGlobalNumber("bad",&bad)||bad)return 5;
  const char*value{};std::size_t length{};
  // Lua表和错误状态仍由实际生产派发维护。
  if(LuaRuntime::TakeCallbackError()){
   LuaRuntime::LuaErrorHistoryEntryView e[8]{};auto n=LuaRuntime::CopyLuaErrorHistory(e,8);
   for(std::size_t i=0;i<n;++i)std::fprintf(stderr,"%s\n",e[i].text);return 6;
  }
  static_cast<void>(value);static_cast<void>(length);
 }

 return 0;
}
'''
class ProjectileUpdateBoundaryTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory(prefix='projectile-boundary-')
  source=fixture.HARNESS[:fixture.HARNESS.index('int main(')]+MAIN
  source=re.sub(r'namespace GameFileReader \{\nTextReadResult[\s\S]*?\n\}\n\}', '',source,count=1)
  cls.binary=build_lua_harness(source_root=fixture.SOURCE,workdir=Path(cls.tmp.name),harness_source=source)
 @classmethod
 def tearDownClass(cls):cls.tmp.cleanup()
 def check(self,mode):
  result=subprocess.run([str(self.binary),mode],capture_output=True,text=True)
  self.assertEqual(result.returncode,0,result.stdout+result.stderr)
 def test_manager_cycles_cannot_dispatch_native_projectile_update(self):self.check('manager')
 def test_same_game_frame_native_completions_filter_and_priority(self):self.check('native')
