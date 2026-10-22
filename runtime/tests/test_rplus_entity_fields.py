"""原生旗标两半、虚拟伤害setter与价格/轨迹字段的真实Lua消费者。"""
import unittest, subprocess, tempfile, re
from pathlib import Path
from . import test_lua_entity_query as fixture
from .test_support import build_lua_harness
ROOT=Path(__file__).resolve().parents[2]
MAIN=r'''#include "interfaces/lua/rplus_entity_fields.hpp"
static int bombs=0,tears=0,damageCalls=0;
void BombFlags(void* self,isaac::runtime::BitSet128Value flags){memcpy(static_cast<char*>(self)+0x428,&flags,16);*(static_cast<char*>(self)+0x457)=1;++bombs;}
void TearFlags(void* self,isaac::runtime::BitSet128Value flags){memcpy(static_cast<char*>(self)+0x418,&flags,16);++tears;}
void Damage(void* self,float value){memcpy(static_cast<char*>(self)+0x35c,&value,4);++damageCalls;}
int main(){static_cast<void>(kScriptTemplate);static_cast<void>(&HarnessHasCollectible);static_cast<void>(&BuildPrelude);static_cast<void>(&ExpectNumber);
 CreateBlocks();FillEntities();auto base=g_EngineBase;
 auto type=[&](EntitySlot slot,unsigned t,std::uintptr_t vt){WriteWord(g_Entities[slot],0,base+vt);WriteAt<unsigned>(g_Entities[slot],kEntityTypeOffset,t);g_Entities[slot][kEntityExistsOffset]=1;};
 type(kTearNear,2,kEntityTearVtableOffset);type(kEnemyA,8,kEntityKnifeVtableOffset);type(kFamiliar,7,kEntityLaserVtableOffset);type(kSizeOnly,4,kEntityBombVtableOffset);
 PublishLists();PublishGame();PublishEntityList(g_RoomBytes,true);LuaRuntime::SetEngineModuleBase(base);LuaRuntime::SetGameBindings(AddressOf(g_OwnerSlotBytes),0x2222);
 isaac::runtime::SetRPlusEntityFieldNativeTestBindings({TearFlags,BombFlags,Damage});
 std::string s=R"lua(local m=RegisterMod('rplus-fields',1);m:AddCallback(1,function()
 local tear=Isaac.FindByType(2)[1]:ToTear();local bomb=Isaac.FindByType(4)[1]:ToBomb();local knife=Isaac.FindByType(8)[1]:ToKnife();local laser=Isaac.FindByType(7)[1]:ToLaser();local pickup=Isaac.FindByType(5)[1]:ToPickup();local high=BitSet128(4,1)
 tear.TearFlags=high;bomb:AddTearFlags(high);knife:AddTearFlags(high);laser:AddTearFlags(high)
 assert(tear.TearFlags==high and bomb.Flags==high and knife.TearFlags==high and laser.TearFlags==high)
 tear.CollisionDamage=7.5;assert(tear.CollisionDamage==7.5);laser.CollisionDamage=9;assert(laser.CollisionDamage==9)
 tear.FallingSpeed=-4;tear.FallingAcceleration=.125;assert(tear.FallingSpeed==-4 and tear.FallingAcceleration==.125)
 pickup.AutoUpdatePrice=false;assert(pickup.AutoUpdatePrice==false);pickup.AutoUpdatePrice=0;assert(pickup.AutoUpdatePrice==true)
 _fields_ok=1
 end))lua";
 if(LuaRuntime::InitializeFromBuffer(s.data(),s.size(),"@rplus-fields.lua")!=LuaRuntime::LuaInitResult::Success)return 1;LuaRuntime::DispatchPostUpdate();if(LuaRuntime::TakeCallbackError())return 2;
 if(bombs!=1||tears!=1||damageCalls!=2||g_Entities[kSizeOnly][0x457]!=1)return 3;
 return ExpectNumber("_fields_ok",1)?0:4;
}'''
class EntityFieldConsumerTests(unittest.TestCase):
 def test_flags_high_bits_native_side_effects_and_fields(self):
  with tempfile.TemporaryDirectory(prefix='rplus-fields-') as work:
   s=fixture.HARNESS[:fixture.HARNESS.index('int main(')]+MAIN
   s=re.sub(r'namespace GameFileReader \{\nTextReadResult[\s\S]*?\n\}\n\}', '',s,count=1)
   exe=build_lua_harness(source_root=fixture.SOURCE,workdir=Path(work),harness_source=s)
   r=subprocess.run([str(exe)],capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
