"""固定PC PillEffect class/subclass是signed-char拥有值，不能按文档伪造整数。"""
from pathlib import Path
from unittest import mock
import hashlib,json,os,re,subprocess,tempfile,unittest
from . import test_lua_entity_query as fixture
from . import test_support
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'dist/api-remaining-recovery-20261025'
MAIN=r'''
#include "interfaces/lua/api500_config.hpp"
#include <cassert>
#include <cstdlib>
extern "C" {
#include <lauxlib.h>
#include <lualib.h>
}
using namespace isaac::runtime;
void Run(lua_State*L,const char*s){if(luaL_dostring(L,s)){std::fprintf(stderr,"%s\n%s\n",lua_tostring(L,-1),s);std::exit(10);}}
unsigned Byte(lua_State*L,const char*name){lua_getglobal(L,name);assert(lua_type(L,-1)==LUA_TUSERDATA&&lua_rawlen(L,-1)==1);const auto byte=*static_cast<const unsigned char*>(lua_touserdata(L,-1));lua_pop(L,1);return byte;}
int main(int argc,char**argv){if(argc!=2)return 90;const std::string scene=argv[1];static_cast<void>(kScriptTemplate);static_cast<void>(&HarnessHasCollectible);static_cast<void>(&BuildPrelude);static_cast<void>(&ExpectNumber);
 CreateBlocks();FillEntities();PublishLists();PublishGame();PublishEntityList(g_RoomBytes,true);LuaRuntime::SetEngineModuleBase(g_EngineBase);LuaRuntime::SetGameBindings(g_EngineBase+kGameOwnerGlobalSlotOffset,0x2222);
 std::vector<unsigned char> manager(kManagerItemConfigOffset+0x100),slot(8),pill(0x58),pills(16);
 WriteWord(slot,0,AddressOf(manager));WriteWord(g_ModuleBytes,kGameManagerGlobalSlotOffset,AddressOf(slot));WriteWord(pills,8,AddressOf(pill));WriteWord(manager,kManagerItemConfigOffset+0x60,AddressOf(pills));WriteWord(manager,kManagerItemConfigOffset+0x68,AddressOf(pills)+16);
 for(unsigned i=0;i<pill.size();++i)pill[i]=static_cast<unsigned char>(0x51+i%29);WriteAt<unsigned>(pill,0,1);pill[0x4c]=0x81;pill[0x4d]=0x27;
 const unsigned char nativeGuard[]={FROZEN_GUARD};std::memcpy(g_ModuleBytes.data()+0x3bef48,nativeGuard,16);
 auto*L=luaL_newstate();luaL_requiref(L,"_G",luaopen_base,1);lua_pop(L,1);assert(RegisterIsaacApi(L));Run(L,"pill=Isaac.GetItemConfig():GetPillEffect(1);assert(type(pill)=='userdata')");auto before=pill;
 if(scene=="guard")g_ModuleBytes[0x3bef48]^=1;
 if(scene=="guard"){Run(L,"assert(not pcall(function()return pill.EffectClass end));assert(not pcall(function()return pill.EffectSubClass end));assert(not pcall(function()pill.EffectClass=2 end))");assert(pill==before);lua_close(L);return 0;}
 Run(L,"a=pill.EffectClass;b=pill.EffectSubClass;assert(type(a)=='userdata' and type(b)=='userdata','Pill classes must be owned one-byte values');assert(getmetatable(a)==getmetatable(b));assert(GetPtrHash(a)~=0 and GetPtrHash(a)~=GetPtrHash(b))");assert(Byte(L,"a")==0x81&&Byte(L,"b")==0x27&&pill==before);
 Run(L,"pill.EffectClass=b;copy=pill.EffectClass;assert(copy~=b)");auto expected=before;expected[0x4c]=0x27;assert(pill==expected&&Byte(L,"copy")==0x27&&Byte(L,"a")==0x81);
 lua_getglobal(L,"a");*static_cast<unsigned char*>(lua_touserdata(L,-1))=0xe1;lua_pop(L,1);Run(L,"pill.EffectSubClass=a;second=pill.EffectSubClass");expected[0x4d]=0xe1;assert(pill==expected&&Byte(L,"second")==0xe1);
 Run(L,"assert(not pcall(function()pill.EffectClass=9 end));assert(not pcall(function()pill.EffectSubClass={}end));assert(not pcall(function()pill.EffectClass=pill end))");assert(pill==expected);
 if(scene=="owner")WriteWord(pills,8,0);else if(scene=="base")LuaRuntime::SetEngineModuleBase(g_EngineBase+8);else if(scene!="normal")return 91;
 if(scene!="normal"){Run(L,"local ok,v=pcall(function()return pill.EffectClass end);assert(not ok or v==nil);local ok2,v2=pcall(function()return pill.EffectSubClass end);assert(not ok2 or v2==nil);pcall(function()pill.EffectClass=b end);pcall(function()pill.EffectSubClass=a end);assert(GetPtrHash(a)~=0)");assert(pill==expected&&Byte(L,"a")==0xe1);}
 lua_close(L);return 0;}
'''
class PillEffectClassValues(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory(prefix='pill-class-values-');cls.addClassCleanup(cls.tmp.cleanup);cls.prefix=os.environ.get('ISAAC_PILL_CLASS_PREFIX','main-pill-class-red');cls.paths=tuple(sorted(set(test_support.layered_lua_runtime_sources(fixture.SOURCE))|set((ROOT/'runtime/src').rglob('*.hpp'))|set(fixture.SOURCE.rglob('*.hpp'))));cls.before=cls.snapshot();(OUT/(cls.prefix+'-input-before.json')).write_text(json.dumps(cls.before,indent=2));cls.addClassCleanup(cls.stable)
  nro=next(Path('/Users/kelinls/code/github/isaac mod').glob('The Binding*/Program #0/1/.nro/Repentance.nro')).read_bytes();guard=','.join(map(str,nro[0x3bef48:0x3bef58]));prefix=fixture.HARNESS[:fixture.HARNESS.index('int main(')];prefix=re.sub(r'namespace GameFileReader \{\nTextReadResult[\s\S]*?\n\}\n}', '',prefix,count=1);source=prefix+MAIN.replace('FROZEN_GUARD',guard);(OUT/(cls.prefix+'-harness.cpp')).write_text(source);cls.binary=test_support.build_lua_harness(source_root=fixture.SOURCE,workdir=Path(cls.tmp.name),harness_source=source)
 @classmethod
 def snapshot(cls):return {str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in cls.paths}
 @classmethod
 def stable(cls):
  after=cls.snapshot();(OUT/(cls.prefix+'-input-after.json')).write_text(json.dumps(after,indent=2));assert cls.before==after,'生产输入变化'
 def test_byte_value_copy_write_neighbors_and_owner(self):
  for scene in ['normal','owner','base','guard']:
   with self.subTest(scene=scene):
    r=subprocess.run([str(self.binary),scene],capture_output=True,text=True);print(scene,r.returncode,r.stdout+r.stderr,flush=True);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
