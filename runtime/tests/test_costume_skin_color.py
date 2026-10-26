"""固定PC eSkinColor拥有值：公开Costume入口、非零原生、邻字节及owner寿命。"""
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
EVIDENCE=ROOT/'dist/api-remaining-recovery-20261025'
MAIN=r'''
#include "interfaces/lua/api500_config.hpp"
#include <cassert>
#include <cstdlib>
extern "C" {
#include <lauxlib.h>
#include <lualib.h>
}
using namespace isaac::runtime;
static void Run(lua_State*L,const char*s){if(luaL_dostring(L,s)){fprintf(stderr,"%s\n%s\n",lua_tostring(L,-1),s);std::exit(10);}}
static unsigned Value(lua_State*L,const char*name){lua_getglobal(L,name);assert(lua_type(L,-1)==LUA_TUSERDATA&&lua_rawlen(L,-1)==4);unsigned value{};std::memcpy(&value,lua_touserdata(L,-1),4);lua_pop(L,1);return value;}
int main(int argc,char**argv){
 if(argc!=2)return 90;std::string scene=argv[1];static_cast<void>(kScriptTemplate);static_cast<void>(&HarnessHasCollectible);static_cast<void>(&BuildPrelude);static_cast<void>(&ExpectNumber);
 CreateBlocks();FillEntities();PublishLists();PublishGame();PublishEntityList(g_RoomBytes,true);LuaRuntime::SetEngineModuleBase(g_EngineBase);LuaRuntime::SetGameBindings(g_EngineBase+kGameOwnerGlobalSlotOffset,0x2222);
 std::vector<unsigned char>manager(kManagerItemConfigOffset+0x100),slot(8),item(0x200),items(16);
 WriteWord(slot,0,AddressOf(manager));WriteWord(g_ModuleBytes,kGameManagerGlobalSlotOffset,AddressOf(slot));WriteWord(items,8,AddressOf(item));WriteWord(manager,kManagerItemConfigOffset,AddressOf(items));WriteWord(manager,kManagerItemConfigOffset+8,AddressOf(items)+16);
 WriteAt<int>(item,0,1);WriteAt<int>(item,4,1);for(unsigned i=0xa0;i<0xb0;++i)item[i]=static_cast<unsigned char>(0x61+i%31);WriteAt<unsigned>(item,0xa8,0xf1234567U);
 FROZEN_GUARDS
 auto*L=luaL_newstate();luaL_requiref(L,"_G",luaopen_base,1);lua_pop(L,1);assert(RegisterIsaacApi(L));
 Run(L,"item=Isaac.GetItemConfig():GetCollectible(1);costume=item.Costume;assert(type(costume)=='userdata')");
 const auto before=item;
 if(scene=="guard_read"||scene=="guard_write"){
  // 初次SkinColor访问前损坏已有布局守卫，不能在缓存命中后制造假红。
  g_ModuleBytes[0x3ba074]^=1;
  Run(L,scene=="guard_read"?"assert(not pcall(function()return costume.SkinColor end))":"assert(not pcall(function()costume.SkinColor=17 end))");assert(item==before);lua_close(L);return 0;
 }
 Run(L,"saved=costume.SkinColor;assert(type(saved)=='userdata','SkinColor must be owned opaque eSkinColor');assert(getmetatable(saved).__type=='eSkinColor');assert(getmetatable(saved).__class==getmetatable(saved))");assert(Value(L,"saved")==0xf1234567U);assert(item==before);
 // Lua拥有值与源对象独立；模拟外部值消费者，只核实际4B值，不伪造Lua数值成员。
 lua_getglobal(L,"saved");const unsigned replacement=0x9123456aU;std::memcpy(lua_touserdata(L,-1),&replacement,4);lua_pop(L,1);assert(item==before);
 Run(L,"costume.SkinColor=saved;copied=costume.SkinColor;assert(copied~=saved)");auto expected=before;WriteAt<unsigned>(expected,0xa8,replacement);assert(item==expected);assert(Value(L,"copied")==replacement);
 Run(L,"assert(not pcall(function()costume.SkinColor=7 end));assert(not pcall(function()costume.SkinColor={}end));assert(not pcall(function()costume.SkinColor=item end))");assert(item==expected);
 // 另外取得的同类型值可回写，且只改目标4B。
 WriteAt<unsigned>(item,0xa8,0x10293847U);Run(L,"second=costume.SkinColor;costume.SkinColor=saved");assert(Value(L,"second")==0x10293847U);assert(item==expected);
 if(scene=="owner")WriteWord(items,8,0);else if(scene=="base")LuaRuntime::SetEngineModuleBase(g_EngineBase+8);else if(scene!="normal")return 91;
 if(scene!="normal"){Run(L,"assert(not pcall(function()return costume.SkinColor end));assert(not pcall(function()costume.SkinColor=saved end))");assert(item==expected);assert(Value(L,"saved")==replacement);assert(Value(L,"second")==0x10293847U);}
 lua_close(L);return 0;
}
'''

class CostumeSkinColorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(prefix='costume-skin-');cls.addClassCleanup(cls.tmp.cleanup)
        cls.prefix=os.environ.get('ISAAC_SKIN_ARTIFACT_PREFIX','delegated-skin-red')
        cls.paths=tuple(sorted(set(test_support.layered_lua_runtime_sources(fixture.SOURCE))|set((ROOT/'runtime/src').rglob('*.hpp'))|set(fixture.SOURCE.rglob('*.hpp'))));cls.before=cls.snapshot();EVIDENCE.mkdir(parents=True,exist_ok=True)
        (EVIDENCE/(cls.prefix+'-input-before.json')).write_text(json.dumps(cls.before,indent=2)+'\n');cls.addClassCleanup(cls.stable)
        nro=next(Path('/Users/kelinls/code/github/isaac mod').glob('The Binding of Isaac_ Afterbirth+*/Program #0/1/.nro/Repentance.nro')).read_bytes()
        guards='\n'.join('const unsigned char b'+str(i)+'[]={'+','.join(map(str,nro[o:o+16]))+'};std::memcpy(g_ModuleBytes.data()+'+hex(o)+',b'+str(i)+',16);' for i,o in enumerate((0x3ba064,0x3ba074)))
        prefix=fixture.HARNESS[:fixture.HARNESS.index('int main(')];prefix=re.sub(r'namespace GameFileReader \{\nTextReadResult[\s\S]*?\n\}\n\}', '',prefix,count=1)
        source=prefix+MAIN.replace('FROZEN_GUARDS',guards);(EVIDENCE/(cls.prefix+'-harness.cpp')).write_text(source)
        cls.binary=test_support.build_lua_harness(source_root=fixture.SOURCE,workdir=Path(cls.tmp.name),harness_source=source)
    @classmethod
    def snapshot(cls):return {str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in cls.paths}
    @classmethod
    def stable(cls):
        after=cls.snapshot();(EVIDENCE/(cls.prefix+'-input-after.json')).write_text(json.dumps(after,indent=2)+'\n')
        if cls.before!=after:raise AssertionError('生产输入在编译/执行期间变化')
    def test_skin_owned_value(self):
        for scene in ('normal','owner','base','guard_read','guard_write'):
            with self.subTest(scene=scene):
                r=subprocess.run([str(self.binary),scene],text=True,capture_output=True);print(f'{scene}: exit={r.returncode} {r.stdout}{r.stderr}',flush=True);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
