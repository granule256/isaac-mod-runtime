"""同版PC真实属性的公开注册缺口：独立原生字节、错误输入与失效边界。"""
from pathlib import Path
import re,subprocess,tempfile,unittest
from . import test_lua_entity_query as fixture
from .test_support import build_lua_harness
MAIN=r'''
#include "lua_object_handles.hpp"
#include "interfaces/lua/api400_fields.guards.hpp"
#include "interfaces/lua/entity_lifetime.hpp"
#include <cassert>
extern "C" {
#include <lauxlib.h>
#include <lualib.h>
}
using namespace isaac::runtime;
void Run(lua_State*L,const char*s){if(luaL_dostring(L,s)){std::fprintf(stderr,"%s\n%s\n",lua_tostring(L,-1),s);std::abort();}}
template<class T>void Change(lua_State*L,EntitySlot slot,const char*s,unsigned offset,T value){auto expected=g_Entities;WriteAt<T>(expected[slot],offset,value);Run(L,s);assert(expected==g_Entities);}
int main(int argc,char**argv){
 assert(argc==2);
 static_cast<void>(kScriptTemplate);static_cast<void>(&HarnessHasCollectible);static_cast<void>(&BuildPrelude);static_cast<void>(&ExpectNumber);
 CreateBlocks();FillEntities();
 FillEntity(kNoQuery,7,0,2,0,0,0,0,0,g_EngineBase+kEntityLaserVtableOffset,0);
 FillEntity(kSizeOnly,8,0,0,0,0,0,0,0,g_EngineBase+kEntityKnifeVtableOffset,0);
 PublishLists();PublishGame();PublishEntityList(g_RoomBytes,true);LuaRuntime::SetEngineModuleBase(g_EngineBase);
 LuaRuntime::SetGameBindings(g_EngineBase+kGameOwnerGlobalSlotOffset,0x2222);
 namespace F=api400_fields;
 std::memcpy(g_ModuleBytes.data()+F::kLaserEntry,F::kLaserGuard.data(),F::kLaserGuard.size());
 std::memcpy(g_ModuleBytes.data()+F::kKnifeEntry,F::kKnifeGuard.data(),F::kKnifeGuard.size());
 for(auto slot:{kNoQuery,kSizeOnly})for(unsigned i=0x400;i<0x580;++i)g_Entities[slot][i]=static_cast<unsigned char>(0x91+(i%47));
 // 固定PC Knife注册807C4D/807D16，getter4C3FB0/setter59FDA0读写+388；NS EBE14/ECF68的+430送FromAngle。
 WriteAt<float>(g_Entities[kSizeOnly],0x430,123.25F);
 // 固定PC HomingType成员+424与SetHomingType448170一致；NS公开方法/Update读取+4FC。
 WriteAt<std::int32_t>(g_Entities[kNoQuery],0x4fc,3);
 auto*L=luaL_newstate();luaL_requiref(L,"_G",luaopen_base,1);lua_pop(L,1);assert(RegisterIsaacApi(L));
 PushEntityCallbackArgument(L,AddressOf(g_Entities[kNoQuery]));lua_setglobal(L,"laser");
 PushEntityCallbackArgument(L,AddressOf(g_Entities[kSizeOnly]));lua_setglobal(L,"knife");
 auto before=g_Entities;
 if(!std::strcmp(argv[1],"homing"))Run(L,"assert(laser.HomingType==3, 'missing public Laser.HomingType')");
 Run(L,"assert(knife.Rotation==123.25, 'missing public Knife.Rotation');assert(laser.HomingType==3,'missing public Laser.HomingType')");assert(before==g_Entities);
 Change<float>(L,kSizeOnly,"knife.Rotation=-37.5;assert(knife.Rotation==-37.5)",0x430,-37.5F);
 Change<std::int32_t>(L,kNoQuery,"laser.HomingType=0xffffffff;assert(laser.HomingType==-1)",0x4fc,-1);
 Change<std::int32_t>(L,kNoQuery,"laser.HomingType=0x100000002;assert(laser.HomingType==2)",0x4fc,2);
 before=g_Entities;
 Run(L,"assert(not pcall(function()knife.Rotation={}end));assert(not pcall(function()laser.HomingType={}end));assert(not pcall(function()laser.HomingType=1.5 end));assert(laser.Rotation==nil and knife.HomingType==nil)");assert(before==g_Entities);
 WriteAt<float>(g_Entities[kSizeOnly],0x430,19.75F);WriteAt<std::int32_t>(g_Entities[kNoQuery],0x4fc,1);
 Run(L,"assert(knife.Rotation==19.75 and laser.HomingType==1)");
 RetireEntityLifetime(AddressOf(g_Entities[kNoQuery]));RetireEntityLifetime(AddressOf(g_Entities[kSizeOnly]));before=g_Entities;
 Run(L,"assert(knife.Rotation==nil and laser.HomingType==nil);knife.Rotation=99;laser.HomingType=2");assert(before==g_Entities);
 lua_close(L);return 0;
}
'''
class MissingLaserKnifeProperties(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.temporary=tempfile.TemporaryDirectory(prefix='missing-laser-knife-')
  prefix=fixture.HARNESS[:fixture.HARNESS.index('int main(')]
  prefix=re.sub(r'namespace GameFileReader \{\nTextReadResult[\s\S]*?\n\}\n\}', '',prefix,count=1)
  cls.binary=build_lua_harness(source_root=fixture.SOURCE,workdir=Path(cls.temporary.name),harness_source=prefix+MAIN)
 @classmethod
 def tearDownClass(cls):cls.temporary.cleanup()
 def scenario(self,field):
  r=subprocess.run([str(self.binary),field],capture_output=True,text=True)
  self.assertEqual(r.returncode,0,r.stdout+r.stderr)
 def test_knife_rotation_read_native_write_exact_bytes_and_retire(self):self.scenario('knife')
 def test_laser_homing_type_read_native_write_exact_bytes_and_retire(self):self.scenario('homing')
