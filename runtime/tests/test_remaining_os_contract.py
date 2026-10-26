"""兼容层os子集与随项目固定的原始Lua5.3.3逐项对照；参考库只进入宿主。"""
from pathlib import Path
from unittest import mock
import os,re,subprocess,tempfile,unittest
from . import test_lua_entity_query as fixture
from . import test_support
ROOT=Path(__file__).resolve().parents[2]
SCRIPTS={
'clock':r"local allowed={clock=true,date=true,difftime=true,getenv=true,setlocale=true,time=true};for k in pairs(os)do assert(allowed[k])end;local x=os.clock();local y=reference_os.clock();assert(type(x)=='number' and x>=0 and y>=x);local n=0;for i=1,100000 do n=n+i end;assert(os.clock()>=x and n>0)",
'difftime':r"for _,v in ipairs({{100,23},{-3,8},{'123','-7'},{10.5,3}})do local a,x=pcall(os.difftime,v[1],v[2]);local b,y=pcall(reference_os.difftime,v[1],v[2]);assert(a==b);if a then assert(x==y)end end;assert(not pcall(os.difftime,{}))",
'getenv':r"assert(os.getenv('ISAAC_OS_CONTRACT_VALUE')==reference_os.getenv('ISAAC_OS_CONTRACT_VALUE'));assert(os.getenv('ISAAC_OS_CONTRACT_MISSING_20261025')==nil);assert(not pcall(os.getenv,{}))",
'setlocale':r"assert(os.setlocale('C')==reference_os.setlocale('C'));assert(os.setlocale('ISAAC_INVALID_LOCALE_20261025')==reference_os.setlocale('ISAAC_INVALID_LOCALE_20261025'));for _,k in ipairs({'all','collate','ctype','monetary','numeric','time'})do assert(os.setlocale(nil,k)==reference_os.setlocale(nil,k))end;assert(not pcall(os.setlocale,'C','bad_category'));assert(not pcall(os.setlocale,{}));reference_os.setlocale('C')",
'time':r"""
local function clone(t)local r={};for k,v in pairs(t)do r[k]=v end;return r end
for _,t in ipairs({{year=2020,month=1,day=2},{year=2020,month=13,day=32,hour=25},{year=2020,month='2',day='3',hour=3,min=4,sec=5,isdst=false}})do
 local r=clone(t);local a=os.time(t);local b=reference_os.time(r);assert(a==b,'timestamp differs')
 for _,k in ipairs({'year','month','day','hour','min','sec','wday','yday','isdst'})do assert(t[k]==r[k],'normalized field '..k)end
end
for _,t in ipairs({{year=2020},{year=2020,month=1},{year=2020,month=1,day=false},{year=2020.5,month=1,day=1},{year=2020,month=1,day=1,hour=1.5},false,7})do local a=pcall(os.time,t);local b=pcall(reference_os.time,t);assert(a==b and not a,'invalid time accepted')end
local a=os.time();local b=reference_os.time();assert(type(a)=='number' and math.abs(a-b)<=1)
""",
}
MAIN=r'''
extern "C" {#include <lauxlib.h>
#include <lualib.h>
int luaopen_pc_os(lua_State*);
lua_State* OsContractLuaState();}
int main(int argc,char**argv){
 static_cast<void>(kScriptTemplate);static_cast<void>(&HarnessHasCollectible);static_cast<void>(&BuildPrelude);static_cast<void>(&ExpectNumber);
 if(argc!=2)return 99;CreateBlocks();FillEntities();PublishLists();PublishGame();PublishEntityList(g_RoomBytes,true);
 const char*setup="local m=RegisterMod('os-contract',1);m:AddCallback(1,function()end)";
 if(LuaRuntime::InitializeFromBuffer(setup,std::strlen(setup),"@os-contract.lua")!=LuaRuntime::LuaInitResult::Success)return 1;
 auto*L=OsContractLuaState();luaopen_pc_os(L);lua_setglobal(L,"reference_os");
 const std::string mode=argv[1];const char*script=nullptr;
 SCRIPT_SELECTION
 if(!script)return 98;
 if(luaL_dostring(L,script)){std::fprintf(stderr,"%s\n",lua_tostring(L,-1));return 2;}
 return 0;
}
'''.replace('extern "C" {#include','extern "C" {\n#include')
class RemainingOsContract(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory(prefix='os-contract-');p=Path(cls.tmp.name)
  raw=p/'reference_os.cpp';raw.write_text('extern "C" {\n#define luaopen_os luaopen_pc_os\n#include "third_party/lua-5.3.3/src/loslib.c"\n}\n')
  runtime=fixture.SOURCE/'lua_runtime.cpp';copy=p/'instrumented_runtime.cpp';copy.write_text(runtime.read_text()+'\nextern "C" lua_State* OsContractLuaState(){return LuaRuntime::g_LuaState;}\n')
  sources=[copy if f==runtime else f for f in test_support.layered_lua_runtime_sources(fixture.SOURCE)]
  main=MAIN.replace('SCRIPT_SELECTION','\n'.join('if(mode=="'+k+'")script=R"OSCASE('+v+')OSCASE";'for k,v in SCRIPTS.items()))
  source=fixture.HARNESS[:fixture.HARNESS.index('int main(')]+main
  source=re.sub(r'namespace GameFileReader \{\nTextReadResult[\s\S]*?\n\}\n\}', '',source,count=1)
  with mock.patch.object(test_support,'layered_lua_runtime_sources',return_value=sources):
   cls.binary=test_support.build_lua_harness(source_root=fixture.SOURCE,workdir=p/'build',harness_source=source,extra_sources=(raw,))
 @classmethod
 def tearDownClass(cls):cls.tmp.cleanup()
 def run_case(self,case):
  env=os.environ.copy();env['ISAAC_OS_CONTRACT_VALUE']='native-contract-value';env.pop('ISAAC_OS_CONTRACT_MISSING_20261025',None)
  r=subprocess.run([str(self.binary),case],capture_output=True,text=True,env=env);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
 def test_clock(self):self.run_case('clock')
 def test_difftime(self):self.run_case('difftime')
 def test_getenv(self):self.run_case('getenv')
 def test_setlocale(self):self.run_case('setlocale')
 def test_time(self):self.run_case('time')
