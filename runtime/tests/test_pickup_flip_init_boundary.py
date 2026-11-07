"""Flip observers need PICKUP_INIT between the main and ghost pool selections.

This independent consumer models EID's documented event sequence without
shipping author scripts or reading any private Flip state from the pickup.
"""
import re
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from . import test_lua_entity_query as fixture
from .test_support import build_lua_harness

MAIN = r'''
#include "entity_init_hook.hpp"
#include "interfaces/lua/entity_lifetime.hpp"
#include "native_room_events.hpp"
#include <cassert>
#include <fstream>
#include <iterator>
GameRoomObservation ReadCurrentGameRoom(uintptr_t,void**out){*out=g_RoomBytes.data();return GameRoomObservation::Success;}
GameRoomObservation ReadGameLocationKey(uintptr_t,GameLocationKey*out){*out={84,0,1,0};return GameRoomObservation::Success;}
static void Native(void* entity,std::uint32_t type,std::uint32_t variant,std::uint32_t subtype,std::uint32_t seed){
 assert(entity==g_Entities[kPickup].data());
 isaac::runtime::ReinitializeEntityLifetime(reinterpret_cast<std::uintptr_t>(entity));
 WriteAt<unsigned>(g_Entities[kPickup],kEntityTypeOffset,type);
 WriteAt<unsigned>(g_Entities[kPickup],kEntityVariantOffset,variant);
 WriteAt<unsigned>(g_Entities[kPickup],kEntitySubTypeOffset,subtype);
 WriteAt<unsigned>(g_Entities[kPickup],kEntityInitSeedOffset,seed);
}
template<class Kind>static void Init(void* entity,unsigned subtype,unsigned seed){
 const isaac::runtime::EntityInitNativeBindings bindings{Native};
 if constexpr(requires{Kind::Pickup;})isaac::runtime::RunNativeEntityInit(&bindings,Kind::Pickup,entity,5,100,subtype,seed);
 else bindings.init(entity,5,100,subtype,seed);
}
static double Number(const char*name){double n{};assert(LuaRuntime::ReadLuaGlobalNumber(name,&n));return n;}
int main(int argc,char**argv){
 assert(argc==2||argc==3);const bool fixed=std::strcmp(argv[1],"fixed")==0;
 static_cast<void>(kScriptTemplate);static_cast<void>(&HarnessHasCollectible);static_cast<void>(&BuildPrelude);static_cast<void>(&ExpectNumber);
 CreateBlocks();FillEntities();PublishLists();PublishGame();PublishEntityList(g_RoomBytes,true);
 WriteWord(g_Entities[kPickup],0,g_EngineBase+kEntityPickupVtableOffset);
 WriteAt<unsigned>(g_GameBytes,kLevelCurrentRoomIndexOffset,84);
 LuaRuntime::SetEngineModuleBase(g_EngineBase);LuaRuntime::SetGameBindings(g_EngineBase+kGameOwnerGlobalSlotOffset,0x2222);
 const char*script=R"lua(
local m=RegisterMod('Flip event consumer',1)
local first,flip,mainItem,lastSeed,lastFrame,grid
local positions={}
initCount,observedGhost,wrong=0,0,0
m:AddCallback(71,function(_,t,v,s,index)
 if t==5 and v==100 then
  first=s==0;flip=false;mainItem=s~=0 and s or nil
  lastFrame=Isaac.GetFrameCount();grid=index
 end
end)
m:AddCallback(63,function(_,item)
 if Isaac.GetFrameCount()==lastFrame then
  if first then mainItem=item
  elseif flip and mainItem then positions[lastSeed]={item,grid} end
 end
 first=false;flip=false
end)
m:AddCallback(34,function(_,p)
 assert(p.Type==5 and p.Variant==100 and p.InitSeed~=0)
 assert(p:GetData().old==nil,'base Init must clear the prior GetData')
 first=false;flip=true;lastSeed=p.InitSeed;initCount=initCount+1
end,100)
m:AddCallback(34,function()wrong=wrong+1 end,999)
m:AddCallback(19,function()
 first=false;flip=false
 for _,p in ipairs(Isaac.FindByType(5,100))do
  local entry=positions[p.InitSeed]
  if entry then p:GetData().FlipItemID=entry[1];observedGhost=entry[1] end
 end
end)
)lua";
 std::string source=script;
 if(argc==3){std::ifstream file(argv[2]);source={std::istreambuf_iterator<char>(file),{}};}
 if(LuaRuntime::InitializeFromBuffer(source.data(),source.size(),"@flip-init-boundary.lua")!=LuaRuntime::LuaInitResult::Success)return 1;
 const auto pre=LuaRuntime::DispatchPreRoomEntitySpawnModifying(5,100,fixed?101:0,42,77);static_cast<void>(pre);
 if(!fixed)static_cast<void>(LuaRuntime::DispatchPostGetCollectible(nullptr,1,77,0,101));
 Init<isaac::runtime::NativeEntityInitKind>(g_Entities[kPickup].data(),101,12345);
 // Room::spawn_entity calls InitFlipState only after derived Init returns.
 static_cast<void>(LuaRuntime::DispatchPostGetCollectible(nullptr,1,99,0,202));
 isaac::runtime::NoteNativeRoomLoaded();LuaRuntime::NoteGameStarted(false);LuaRuntime::DispatchPostUpdate();
 if(Number("observedGhost")!=202){std::fprintf(stderr,"Flip ghost ID was not captured before NEW_ROOM: %g\n",Number("observedGhost"));return 2;}
 if(Number("initCount")!=1||Number("wrong")||LuaRuntime::TakeCallbackError())return 3;
 LuaRuntime::DispatchPostUpdate();
 if(Number("initCount")!=1)return 4;
 // Reinitializing the same object is a new Init, not a frame-scan discovery.
 static_cast<void>(LuaRuntime::DispatchPreRoomEntitySpawnModifying(5,100,101,42,78));
 Init<isaac::runtime::NativeEntityInitKind>(g_Entities[kPickup].data(),101,54321);
 static_cast<void>(LuaRuntime::DispatchPostGetCollectible(nullptr,1,100,0,303));
 isaac::runtime::NoteNativeRoomLoaded();LuaRuntime::DispatchPostUpdate();
 if(Number("observedGhost")!=303||Number("initCount")!=2||LuaRuntime::TakeCallbackError())return 5;
 return 0;
}
'''


class PickupFlipInitBoundaryTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory(prefix='pickup-flip-init-')
  prefix=fixture.HARNESS.split('int main(',1)[0]
  prefix=prefix.replace('GameRoomObservation ReadCurrentGameRoom(uintptr_t, void**) {\n    return GameRoomObservation::RoomUnreadable;\n}', '')
  prefix=re.sub(r'namespace GameFileReader \{\nTextReadResult[\s\S]*?\n\}\n\}', '',prefix,count=1)
  cls.binary=build_lua_harness(source_root=fixture.SOURCE,workdir=Path(cls.tmp.name),harness_source=prefix+MAIN,
      extra_sources=(fixture.SOURCE/'entity_init_hook.cpp',))
 @classmethod
 def tearDownClass(cls):cls.tmp.cleanup()
 def check(self,mode,script=None):
  args=[str(self.binary),mode]
  if script is not None:
   path=Path(self.tmp.name)/'consumer.lua';path.write_text(script);args.append(str(path))
  r=subprocess.run(args,capture_output=True,text=True)
  self.assertEqual(r.returncode,0,r.stdout+r.stderr)
 def test_random_pedestal_captures_flip_selection_before_room_entry(self):self.check('random')
 def test_fixed_pedestal_and_same_address_reinitialization(self):self.check('fixed')
 def test_original_eid_flip_consumers_when_explicitly_supplied(self):
  path=os.environ.get('ISAAC_TEST_EID_MAIN')
  if not path:self.skipTest('original EID main.lua not configured')
  text=Path(path).read_text()
  start=text.index('local initialItemNext = false')
  end=text.index('-- MC_PRE_USE_ITEM callback to watch for Void absorbing active items',start)
  def function(name):
   match=re.search(r'(?m)^([ \t]*)function EID:'+name+r'\(',text);self.assertIsNotNone(match,name)
   close=re.search(r'(?m)^'+re.escape(match[1])+r'end[ \t]*$',text[match.end():]);self.assertIsNotNone(close,name)
   return text[match.start():match.end()+close.end()]
  script='''
local game=Game();EID=RegisterMod('original EID Flip consumer',1);EID.isRepentance=true
EID.Config={DisplayFlipItemDescriptions=true};EID.BoC={};EID.CraneItemType={}
function EID:getEntityData(e,key)return e:GetData()[key]end
function EID:setEntityData(e,key,value)e:GetData()[key]=value end
initCount,observedGhost,wrong=0,0,0
assert(not REPENTOGON)
'''+text[start:end]+function('AssignFlipItems')+'\n'+function('onNewFloor')+'''
EID:AddCallback(18,EID.onNewFloor)
EID:AddCallback(34,function(_,p)initCount=initCount+1 end,100)
EID:AddCallback(34,function()wrong=wrong+1 end,999)
EID:AddCallback(19,function()
 EID:AssignFlipItems()
 for _,p in ipairs(Isaac.FindByType(5,100))do
  local id=EID:getEntityData(p,'EID_FlipItemID');if id then observedGhost=id end
 end
end)
'''
  for mode in ('random','fixed'):
   with self.subTest(mode=mode):self.check(mode,script)
