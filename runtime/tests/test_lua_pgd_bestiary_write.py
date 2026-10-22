"""真实Lua三种图鉴写入/查询：原生ABI、可选Variant、同PGD对象与失效保护。"""
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from . import test_lua_persistent_game_data as pgd
from . import test_support

ROOT=Path(__file__).resolve().parents[2]
FIXTURE=pgd.fixture

MAIN=r'''
static unsigned calls=0;static std::uintptr_t lastTarget=0;static std::uint64_t args[8]{};
static bool killResult=true;
extern "C" void EngineCallTrampoline(std::uintptr_t target,const std::uint64_t* integers,
 const double* floats,std::uint64_t* integerResult,double* floatResult)noexcept{
 ++calls;lastTarget=target;std::memcpy(args,integers,sizeof(args));
 for(unsigned i=0;i<8;++i)if(floats[i]!=0)std::abort();
 if(integers[0]!=AddressOf(g_ManagerBytes)+0x18)std::abort();
 if(target==g_EngineBase+0x43ac5c){
  for(unsigned i=3;i<8;++i)if(integers[i])std::abort();
  *integerResult=killResult?1:0;
 }else if(target==g_EngineBase+0x439a40){
  for(unsigned i=2;i<8;++i)if(integers[i])std::abort();
  if(integers[1]<1||integers[1]>103)std::abort();
  // 宿主模型只验证写入同一原对象并读取同一byte；真实解锁副作用由原NS函数负责。
  if(!g_ManagerBytes[0x19])g_ManagerBytes[0x18+0xd87+integers[1]]=1;
  *integerResult=0xdeadbeef;
 }else std::abort();
 *floatResult=0;
}
int main(int argc,char** argv){
 if(argc!=2)return 99;std::string scenario=argv[1];
 PublishFakeMemory();LuaRuntime::SetGameBindings(AddressOf(g_OwnerSlotBytes),0x2222);
 const unsigned char guards[2][16]={PGD_WRITE_BYTES};
 std::memcpy(g_ModuleBytes.data()+0x43ac5c,guards[0],16);std::memcpy(g_ModuleBytes.data()+0x439a40,guards[1],16);
 std::string body;
 unsigned wantCalls=0,wantType=10,wantVariant=0,wantBoss=1;
 bool isKill=false;
 if(scenario=="kill_default"||scenario=="kill_nil"||scenario=="kill_false"||scenario=="kill_strings"||scenario=="kill_float"){
  isKill=true;wantCalls=1;killResult=scenario!="kill_false";
  std::string expression="data:AddBestiaryKill(10)";
  if(scenario=="kill_nil")expression="data:AddBestiaryKill(10,nil)";
  if(scenario=="kill_strings"){expression="data:AddBestiaryKill('4294967294','4294967297')";wantType=0xfffffffeU;wantVariant=1;}
  if(scenario=="kill_float"){expression="data:AddBestiaryKill(10.0,20.0)";wantVariant=20;}
  body="local returned=table.pack("+expression+");assert(returned.n==1 and type(returned[1])=='boolean' and returned[1]=="+(killResult?"true":"false")+")";
 }else if(scenario=="boss1"||scenario=="boss103"||scenario=="boss_strings"||scenario=="boss_low32"||scenario=="readonly"){
  wantCalls=1;wantBoss=(scenario=="boss103"||scenario=="boss_strings")?103:1;
  const std::string id=scenario=="boss_strings"?"'103'":(scenario=="boss_low32"?"4294967297":std::to_string(wantBoss));
  if(scenario=="readonly")g_ManagerBytes[0x19]=1;
  body="assert(not data:IsBossKilled("+id+"));assert(select('#',data:AddBossKilled("+id+"))==0);assert(data:IsBossKilled("+id+")=="+(scenario=="readonly"?"false":"true")+")";
 }else if(scenario=="boss_both"){
  wantCalls=2;wantBoss=103;
  body="for _,id in ipairs({1,103}) do assert(not data:IsBossKilled(id));assert(select('#',data:AddBossKilled(id))==0);assert(data:IsBossKilled(id)) end";
 }else if(scenario=="bad_kill"){
  body="for _,a in ipairs({{},false,'bad',1.5}) do assert(not pcall(data.AddBestiaryKill,data,a)) end;assert(not pcall(data.AddBestiaryKill,data));assert(not pcall(data.AddBestiaryKill,data,10,{}))";
 }else if(scenario=="bad_boss"){
  body="for _,id in ipairs({0,104,-1,4294967400,{},false,'bad',1.5}) do assert(not pcall(data.AddBossKilled,data,id));assert(not pcall(data.IsBossKilled,data,id)) end;assert(not pcall(data.AddBossKilled,data));assert(not pcall(data.IsBossKilled,data))";
 }else if(scenario=="entry_kill"){
  g_ModuleBytes[0x43ac5c+15]^=1;body="assert(not pcall(data.AddBestiaryKill,data,10))";
 }else if(scenario=="entry_boss"){
  g_ModuleBytes[0x439a40+15]^=1;body="assert(not pcall(data.AddBossKilled,data,1));assert(not pcall(data.IsBossKilled,data,1))";
 }else if(scenario=="unknown_module"){
  body="assert(not pcall(data.AddBestiaryKill,data,10));assert(not pcall(data.AddBossKilled,data,1));assert(not pcall(data.IsBossKilled,data,1))";
 }else if(scenario=="owner_lost"||scenario=="owner_replaced"){
  body="assert(not pcall(data.AddBestiaryKill,data,10));assert(not pcall(data.AddBossKilled,data,1));assert(not pcall(data.IsBossKilled,data,1))";
 }else return 98;
 std::string script="local data=Isaac.GetPersistentGameData();for _,name in ipairs({'AddBestiaryKill','AddBossKilled','IsBossKilled'}) do assert(type(data[name])=='function',name..' missing') end;local m=RegisterMod('pgd-write',1);m:AddCallback(1,function() "+body+" end)";
 if(LuaRuntime::InitializeFromBuffer(script.data(),script.size(),"@pgd-write.lua")!=LuaRuntime::LuaInitResult::Success){std::puts("missing PGD write method");return 1;}
 if(scenario=="owner_lost")WriteAt<std::uintptr_t>(g_ManagerSlotBytes,0,0);
 if(scenario=="owner_replaced")WriteAt<std::uintptr_t>(g_ManagerSlotBytes,0,AddressOf(g_ManagerBytes)+8);
 if(scenario=="unknown_module")LuaRuntime::SetEngineModuleBase(0);
 LuaRuntime::DispatchPostUpdate();
 if(LuaRuntime::TakeCallbackError()){std::fprintf(stderr,"PGD write Lua failed %s\n",scenario.c_str());return 2;}
 if(calls!=wantCalls)return 3;
 if(wantCalls){
  if(lastTarget!=g_EngineBase+(isKill?0x43ac5c:0x439a40))return 4;
  if(isKill?(args[1]!=wantType||args[2]!=wantVariant):(args[1]!=wantBoss))return 5;
 }
 return 0;
}
'''

class PgdBestiaryWriteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(prefix='isaac-pgd-write-')
        source=FIXTURE.HARNESS[:FIXTURE.HARNESS.index('int main(')]+MAIN
        source='#include <cstdlib>\n#include <string>\n'+source
        nro=next(ROOT.glob('The Binding of Isaac_ Afterbirth+*/Program #0/1/.nro/Repentance.nro')).read_bytes()
        source=source.replace('PGD_WRITE_BYTES',','.join('{'+','.join(str(b) for b in nro[o:o+16])+'}' for o in [0x43ac5c,0x439a40]))
        for name in ('CURRENT_TINT','CURRENT_SHIFT','DEFAULT_TINT','SPLAT_TINT'):
            for i,v in enumerate(getattr(FIXTURE,name)):source=source.replace(f'{name}_{i}',repr(v))
        for name in ('COLLECTIBLE_COUNT','TRINKET_COUNT','ENTITY_DEFAULT_COLOR_OFFSET','ENTITY_SPLAT_COLOR_OFFSET'):
            source=source.replace(name,str(getattr(FIXTURE,name)))
        # 用记录ABI和原对象写入的宿主模型替代通用零返回桩，生产代码仍是真handler。
        sources=[p for p in test_support.layered_lua_runtime_sources(FIXTURE.SOURCE) if p.name!='engine_call_trampoline_host_stub.cpp']
        with mock.patch.object(test_support,'layered_lua_runtime_sources',return_value=sources):
            cls.binary=test_support.build_lua_harness(source_root=FIXTURE.SOURCE,workdir=Path(cls.tmp.name),harness_source=source)

    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()

    def run_scenarios(self,scenarios):
        for scenario in scenarios:
            with self.subTest(scenario=scenario):
                r=subprocess.run([str(self.binary),scenario],capture_output=True,text=True)
                self.assertEqual(r.returncode,0,r.stdout+r.stderr)

    def test_add_bestiary_optional_variant_integer_conversion_and_boolean(self):
        self.run_scenarios(('kill_default','kill_nil','kill_false','kill_strings','kill_float','bad_kill'))

    def test_add_and_query_boss_share_real_pgd_bytes_and_void_return(self):
        self.run_scenarios(('boss1','boss103','boss_strings','boss_low32','boss_both','readonly','bad_boss'))

    def test_changed_entry_unknown_module_and_stale_owner_reject(self):
        self.run_scenarios(('entry_kill','entry_boss','unknown_module','owner_lost','owner_replaced'))

if __name__=='__main__':unittest.main()
