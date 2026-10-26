"""Damage 原生存储合约：公开 Projectile 字段、40C float 及完整邻字节。

仅验证存储/API类型与失效保护，不宣称写值会改变命中伤害。
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
static void Change(lua_State*L,float value,const char*s){auto expected=g_Entities;WriteAt<float>(expected[kBullet],0x40c,value);const auto game=g_GameBytes;Run(L,s);assert(g_Entities==expected&&g_GameBytes==game);}
int main(int argc,char**argv){
 if(argc!=2)return 90;const std::string scene=argv[1];static_cast<void>(kScriptTemplate);static_cast<void>(&HarnessHasCollectible);static_cast<void>(&BuildPrelude);static_cast<void>(&ExpectNumber);
 CreateBlocks();FillEntities();WriteWord(g_Entities[kEnemyA],0,g_EngineBase+kEntityNpcVtableOffset);FillEntity(kBullet,9,0,0,0,0,1,2,3,g_EngineBase+kEntityProjectileVtableOffset,0);PublishLists();PublishGame();PublishEntityList(g_RoomBytes,true);LuaRuntime::SetEngineModuleBase(g_EngineBase);LuaRuntime::SetGameBindings(g_EngineBase+kGameOwnerGlobalSlotOffset,0x2222);
 FROZEN_GUARD
 // 相邻原生字段使用互异值，防止把下落速度或基类碰撞伤害误认为 Damage。
 for(unsigned i=0x3f0;i<0x424;++i)g_Entities[kBullet][i]=static_cast<unsigned char>(0x41+i%53);
 WriteAt<float>(g_Entities[kBullet],0x35c,61.5F);
 WriteAt<float>(g_Entities[kBullet],0x400,21.5F);
 WriteAt<float>(g_Entities[kBullet],0x404,31.5F);
 WriteAt<float>(g_Entities[kBullet],0x408,41.5F);
 WriteAt<float>(g_Entities[kBullet],0x40c,13.25F);
 WriteAt<float>(g_Entities[kBullet],0x410,51.5F);
 auto*L=luaL_newstate();luaL_requiref(L,"_G",luaopen_base,1);lua_pop(L,1);assert(RegisterIsaacApi(L));
 PushEntityCallbackArgument(L,AddressOf(g_Entities[kBullet]));lua_setglobal(L,"projectile");PushEntityCallbackArgument(L,AddressOf(g_Entities[kPlayer]));lua_setglobal(L,"player");PushEntityCallbackArgument(L,AddressOf(g_Entities[kPickup]));lua_setglobal(L,"pickup");PushEntityCallbackArgument(L,AddressOf(g_Entities[kEnemyA]));lua_setglobal(L,"npc");
 Run(L,"assert(getmetatable(projectile).__type=='EntityProjectile')");
 if(scene=="guard_read"||scene=="guard_write"||scene=="layout_a_read"||scene=="layout_a_write"||scene=="layout_b_read"||scene=="layout_b_write"){
  // 新进程首次解析前破坏入口或指定布局守卫，不利用成功缓存。
  g_ModuleBytes[scene.find("layout_a")==0?0x31f198:scene.find("layout_b")==0?0x31f1c4:0x31f154]^=1;Unchanged(L,(scene.find("read")!=std::string::npos)?"assert(not pcall(function()return projectile.Damage end))":"assert(not pcall(function()projectile.Damage=-2.625 end))");lua_close(L);return 0;
 }
 if(scene=="native"){
  Unchanged(L,"assert(type(projectile.Damage)=='number' and projectile.Damage==13.25,'Damage must read native float at Projectile+40C');assert(projectile.Height==21.5 and projectile.FallingSpeed==31.5 and projectile.FallingAccel==41.5 and projectile.Scale==51.5 and projectile.CollisionDamage==61.5)");
  Change(L,-2.625F,"projectile.Damage=-2.625;assert(projectile.Damage==-2.625 and projectile.Height==21.5 and projectile.FallingSpeed==31.5 and projectile.FallingAccel==41.5 and projectile.Scale==51.5 and projectile.CollisionDamage==61.5)");
  Change(L,13.25F,"projectile.Damage=13.25;assert(projectile.Damage==13.25 and projectile.Height==21.5 and projectile.FallingSpeed==31.5 and projectile.FallingAccel==41.5 and projectile.Scale==51.5 and projectile.CollisionDamage==61.5)");
 }else if(scene=="types"){
  Unchanged(L,"assert(projectile.Damage==13.25);for _,v in ipairs({false,{},'not a number',projectile})do assert(not pcall(function()projectile.Damage=v end)) end;assert(not pcall(function()projectile.Damage=nil end));assert(projectile.Damage==13.25)");
 }else if(scene=="retired"){
  Unchanged(L,"assert(projectile.Damage==13.25)");RetireEntityLifetime(AddressOf(g_Entities[kBullet]));
  Unchanged(L,"local ok,v=pcall(function()return projectile.Damage end);assert(not ok or v==nil);pcall(function()projectile.Damage=-2.625 end)");
 }else if(scene=="wrong_self"){
  Unchanged(L,"local mt=getmetatable(projectile);for _,v in ipairs({false,{},13,'wrong self'})do pcall(mt.__newindex,v,'Damage',-2.625) end;pcall(mt.__newindex,nil,'Damage',-2.625);assert(projectile.Damage==13.25)");
 }else return 91;
 lua_close(L);return 0;
}
'''
class ProjectileDamageStorageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(prefix='projectile-damage-');cls.addClassCleanup(cls.tmp.cleanup)
        cls.prefix=os.environ.get('ISAAC_PROJECTILE_DAMAGE_PREFIX','projectile-damage-storage-main')
        cls.paths=tuple(p for p in sorted(set(test_support.layered_lua_runtime_sources(fixture.SOURCE))|set((ROOT/'runtime/src').rglob('*.hpp'))|set(fixture.SOURCE.rglob('*.hpp'))) if not p.is_symlink());cls.before=cls.snapshot();OUT.mkdir(parents=True,exist_ok=True)
        (OUT/(cls.prefix+'-input-before.json')).write_text(json.dumps(cls.before,indent=2)+'\n');cls.addClassCleanup(cls.stable)
        nro=next(Path('/Users/kelinls/code/github/isaac mod').glob('The Binding of Isaac_ Afterbirth+*/Program #0/1/.nro/Repentance.nro')).read_bytes()
        guard=''
        for name,offset in (('ProjectileInit',0x31f154),('ProjectileLayoutA',0x31f198),('ProjectileLayoutB',0x31f1c4)):
            fixed=nro[offset:offset+16]
            if len(fixed)!=16:raise AssertionError('固定 NRO 守卫字节不足')
            guard+='const unsigned char fixed'+name+'[]={'+','.join(map(str,fixed))+'};std::memcpy(g_ModuleBytes.data()+'+hex(offset)+',fixed'+name+',16);'
        guard+='const unsigned char existingHeightGuard[]={'+','.join(map(str,nro[0x31f18c:0x31f1a4]))+'};std::memcpy(g_ModuleBytes.data()+0x31f18c,existingHeightGuard,24);'
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
        for scene in ('native','types','retired','wrong_self','guard_read','guard_write','layout_a_read','layout_a_write','layout_b_read','layout_b_write'):
            with self.subTest(scene=scene):
                r=subprocess.run([str(self.binary),scene],text=True,capture_output=True);print(f'{scene}: exit={r.returncode} {r.stdout}{r.stderr}',flush=True);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
