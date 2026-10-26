"""CurveStrength原生存储合约：公开Laser字段、4E0 float及完整邻字节。

仅验证存储/API类型与失效保护，不宣称写值会改变曲线视觉或碰撞。
"""
import hashlib
import json
import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path
from . import test_lua_entity_query as fixture
from . import test_support
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'dist/api-remaining-recovery-20261025'
MAIN=r'''
#include "interfaces/lua/entity_lifetime.hpp"
#include "lua_object_handles.hpp"
#include <cassert>
#include <cstdlib>
extern "C" {
#include <lauxlib.h>
#include <lualib.h>
}
using namespace isaac::runtime;
static void Run(lua_State*L,const char*s){if(luaL_dostring(L,s)){fprintf(stderr,"%s\n%s\n",lua_tostring(L,-1),s);std::exit(10);}}
static void Unchanged(lua_State*L,const char*s){const auto entities=g_Entities;const auto game=g_GameBytes;Run(L,s);assert(g_Entities==entities&&g_GameBytes==game);}
static void Change(lua_State*L,float value,const char*s){auto expected=g_Entities;WriteAt<float>(expected[kSizeOnly],0x4e0,value);const auto game=g_GameBytes;Run(L,s);assert(g_Entities==expected&&g_GameBytes==game);}
int main(int argc,char**argv){
 if(argc!=2)return 90;const std::string scene=argv[1];static_cast<void>(kScriptTemplate);static_cast<void>(&HarnessHasCollectible);static_cast<void>(&BuildPrelude);static_cast<void>(&ExpectNumber);
 CreateBlocks();FillEntities();FillEntity(kSizeOnly,7,1,0,1,2,3,4,5,g_EngineBase+kEntityLaserVtableOffset,0);WriteWord(g_Entities[kEnemyA],0,g_EngineBase+kEntityNpcVtableOffset);FillEntity(kBullet,9,0,0,0,0,1,2,3,g_EngineBase+kEntityProjectileVtableOffset,0);PublishLists();PublishGame();PublishEntityList(g_RoomBytes,true);LuaRuntime::SetEngineModuleBase(g_EngineBase);LuaRuntime::SetGameBindings(g_EngineBase+kGameOwnerGlobalSlotOffset,0x2222);
 FROZEN_GUARD
 // 两侧非零原生哨兵；不把Homing内部容量地址当作CurveStrength，更不访问其数组。
 for(unsigned i=0x4c8;i<0x4f0;++i)g_Entities[kSizeOnly][i]=static_cast<unsigned char>(0x41+i%53);
 WriteAt<std::uint64_t>(g_Entities[kSizeOnly],0x4d8,0x1122334455667788ULL);WriteAt<float>(g_Entities[kSizeOnly],0x4e0,13.25F);WriteAt<float>(g_Entities[kSizeOnly],0x4e4,17.5F);
 auto*L=luaL_newstate();luaL_requiref(L,"_G",luaopen_base,1);lua_pop(L,1);assert(RegisterIsaacApi(L));
 PushEntityCallbackArgument(L,AddressOf(g_Entities[kSizeOnly]));lua_setglobal(L,"laser");PushEntityCallbackArgument(L,AddressOf(g_Entities[kPlayer]));lua_setglobal(L,"player");PushEntityCallbackArgument(L,AddressOf(g_Entities[kPickup]));lua_setglobal(L,"pickup");PushEntityCallbackArgument(L,AddressOf(g_Entities[kEnemyA]));lua_setglobal(L,"npc");PushEntityCallbackArgument(L,AddressOf(g_Entities[kBullet]));lua_setglobal(L,"projectile");
 Run(L,"assert(getmetatable(laser).__type=='EntityLaser')");
 if(scene=="guard_read"||scene=="guard_write"||scene=="layout_read"||scene=="layout_write"){
  // 新进程、首次布局解析前破坏真实Laser.Init首16B，不利用已缓存成功入口。
  g_ModuleBytes[scene[0]=='l'?0xf76f4:0xf7640]^=1;Unchanged(L,(scene=="guard_read"||scene=="layout_read")?"assert(not pcall(function()return laser.CurveStrength end))":"assert(not pcall(function()laser.CurveStrength=-2.625 end))");lua_close(L);return 0;
 }
 if(scene=="native"){
  Unchanged(L,"assert(type(laser.CurveStrength)=='number' and laser.CurveStrength==13.25,'CurveStrength must read native float at Laser+4E0');assert(laser.Radius==17.5)");
  Change(L,-2.625F,"laser.CurveStrength=-2.625;assert(laser.CurveStrength==-2.625 and laser.Radius==17.5)");
  Change(L,13.25F,"laser.CurveStrength=13.25;assert(laser.CurveStrength==13.25 and laser.Radius==17.5)");
 }else if(scene=="types"){
  Unchanged(L,"assert(laser.CurveStrength==13.25);for _,v in ipairs({false,{},'not a number',laser})do assert(not pcall(function()laser.CurveStrength=v end)) end;assert(not pcall(function()laser.CurveStrength=nil end));assert(laser.CurveStrength==13.25)");
 }else if(scene=="retired"){
  Unchanged(L,"assert(laser.CurveStrength==13.25)");RetireEntityLifetime(AddressOf(g_Entities[kSizeOnly]));
  Unchanged(L,"local ok,v=pcall(function()return laser.CurveStrength end);assert(not ok or v==nil);pcall(function()laser.CurveStrength=-2.625 end)");
 }else if(scene=="other_types"){
  Unchanged(L,"assert(getmetatable(player).__type=='EntityPlayer' and getmetatable(pickup).__type=='EntityPickup' and getmetatable(npc).__type=='EntityNPC' and getmetatable(projectile).__type=='EntityProjectile');for _,v in ipairs({player,pickup,npc,projectile})do assert(v.CurveStrength==nil);pcall(function()v.CurveStrength=-2.625 end);assert(v.CurveStrength==nil) end");
 }else return 91;
 std::uint64_t capacity{};float radius{};std::memcpy(&capacity,g_Entities[kSizeOnly].data()+0x4d8,8);std::memcpy(&radius,g_Entities[kSizeOnly].data()+0x4e4,4);assert(capacity==0x1122334455667788ULL&&radius==17.5F);lua_close(L);return 0;
}
'''
class LaserCurveStrengthTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(prefix='curve-strength-');cls.addClassCleanup(cls.tmp.cleanup)
        cls.prefix=os.environ.get('ISAAC_CURVE_STRENGTH_PREFIX','curve-strength-storage-main')
        cls.paths=tuple(sorted(set(test_support.layered_lua_runtime_sources(fixture.SOURCE))|set((ROOT/'runtime/src').rglob('*.hpp'))|set(fixture.SOURCE.rglob('*.hpp'))));cls.before=cls.snapshot();OUT.mkdir(parents=True,exist_ok=True)
        (OUT/(cls.prefix+'-input-before.json')).write_text(json.dumps(cls.before,indent=2)+'\n');cls.addClassCleanup(cls.stable)
        nro=next(Path('/Users/kelinls/code/github/isaac mod').glob('The Binding of Isaac_ Afterbirth+*/Program #0/1/.nro/Repentance.nro')).read_bytes()
        guard='const unsigned char fixedLaserInit[]={'+','.join(map(str,nro[0xf7640:0xf7650]))+'};std::memcpy(g_ModuleBytes.data()+0xf7640,fixedLaserInit,16);'
        guard+='const unsigned char fixedCurveLayout[]={'+','.join(map(str,nro[0xf76f4:0xf7704]))+'};std::memcpy(g_ModuleBytes.data()+0xf76f4,fixedCurveLayout,16);'
        prefix=fixture.HARNESS[:fixture.HARNESS.index('int main(')];prefix=re.sub(r'namespace GameFileReader \{\nTextReadResult[\s\S]*?\n\}\n\}', '',prefix,count=1)
        source=prefix+MAIN.replace('FROZEN_GUARD',guard);(OUT/(cls.prefix+'-harness.cpp')).write_text(source)
        cls.binary=test_support.build_lua_harness(source_root=fixture.SOURCE,workdir=Path(cls.tmp.name),harness_source=source)
    @classmethod
    def snapshot(cls):return {str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in cls.paths}
    @classmethod
    def stable(cls):
        after=cls.snapshot();(OUT/(cls.prefix+'-input-after.json')).write_text(json.dumps(after,indent=2)+'\n')
        if cls.before!=after:raise AssertionError('生产输入在编译/执行期间改变')
    def test_float_storage_neighbors_and_lifetime(self):
        for scene in ('native','types','retired','other_types','guard_read','guard_write','layout_read','layout_write'):
            with self.subTest(scene=scene):
                r=subprocess.run([str(self.binary),scene],text=True,capture_output=True);print(f'{scene}: exit={r.returncode} {r.stdout}{r.stderr}',flush=True);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
