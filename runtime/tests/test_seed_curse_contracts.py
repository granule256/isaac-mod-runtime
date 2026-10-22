"""显式参数实际经过生产共享解析，布尔寄存器与原生字符串解析分别核对。"""
import subprocess,tempfile,unittest,re,struct
from pathlib import Path
from .test_support import build_lua_harness
from .test_lua_batch335_player_api_rows import HARNESS,SOURCE

MAIN=r'''
#include "interfaces/lua/api400_seeds.hpp"
#include "interfaces/lua/api100_strings.hpp"
#include "interfaces/lua/api400_seeds.guards.hpp"
#include "infrastructure/memory/engine_field_access.hpp"
#include "lua_object_handles.hpp"
static unsigned decoded{};
static std::uint32_t DecodeSeed(const void* header){
 isaac::runtime::EngineStringView view{};
 if(!isaac::runtime::ResolveEngineStringView(reinterpret_cast<std::uintptr_t>(header),&view))return 17;
 const auto*text=static_cast<const char*>(isaac::runtime::engine_memory::AsObject(view.data));++decoded;
 if(view.size==0)return 0;
 return view.size==9&&!std::memcmp(text,"ABCD EFGH",9)?0xf1234567U:19;
}
int main(int argc,char**argv){
 if(argc!=2)return 90;PublishFakeWorld(true,true);
 // 独立于声明常量：原版NRO该入口的实际四字节。
 const unsigned char originalSeedEntry[4]={0xfd,0x7b,0xbe,0xa9};
 std::memcpy(g_ModuleBytes.data()+kSeedsSetStartSeedOffset,originalSeedEntry,4);
 const unsigned char dischargeEntry[4]={0xff,0xc3,0x03,0xd1};
 const unsigned char directionEntry[4]={0x00,0x34,0x43,0xbd};
 std::memcpy(g_ModuleBytes.data()+kEntityPlayerDischargeActiveItemOffset,dischargeEntry,4);
 std::memcpy(g_ModuleBytes.data()+kEntityGetMovementDirectionOffset,directionEntry,4);
 PlantEntryWord(kLevelAddCurseOffset,kLevelAddCurseEntryWord);
 const auto& guard=isaac::runtime::api400_seeds::kString2SeedGuard;
 std::memcpy(g_ModuleBytes.data()+isaac::runtime::api400_seeds::kString2SeedEntry,guard.data(),guard.size());
 isaac::runtime::SetApi400SeedsNativeTestBindings(0,reinterpret_cast<std::uintptr_t>(&DecodeSeed),0);
 LuaRuntime::SetGameBindings(reinterpret_cast<std::uintptr_t>(g_OwnerSlotBytes.data()),0x2222);
 std::string script="local l=Game():GetLevel();local s=Game():GetSeeds();";
 const char* mode=argv[1];
 if(!std::strcmp(mode,"curse_true"))script+="l:AddCurse(1,true)";
 else if(!std::strcmp(mode,"curse_false"))script+="l:AddCurse(1,false)";
 else if(!std::strcmp(mode,"seed_string"))script+="s:SetStartSeed('ABCD EFGH')";
 else if(!std::strcmp(mode,"seed_empty"))script+="s:SetStartSeed('')";
 else if(!std::strcmp(mode,"seed_badguard")){g_ModuleBytes[isaac::runtime::api400_seeds::kString2SeedEntry]^=1;script+="local ok,e=pcall(function()s:SetStartSeed('ABCD EFGH')end);assert(not ok and string.find(e,'guard'))";}
 else if(!std::strcmp(mode,"seed_number"))script+="s:SetStartSeed(1234567890)";
 else if(!std::strcmp(mode,"discharge"))script+="Isaac.GetPlayer(0):DischargeActiveItem(0)";
 else if(!std::strcmp(mode,"discharge_default"))script+="Isaac.GetPlayer(0):DischargeActiveItem()";
 else if(!std::strcmp(mode,"direction"))script+="Isaac.GetPlayer(0):GetMovementDirection()";
 else if(!std::strcmp(mode,"arguments"))script+="assert(not pcall(function()l:AddCurse(1)end));assert(not pcall(function()l:AddCurse('bad',true)end));assert(not pcall(function()s:SetStartSeed({})end));assert(not pcall(function()s:SetStartSeed(1,2)end))";
 else return 91;
 auto result=LuaRuntime::InitializeFromBuffer(script.data(),script.size(),"@seed-curse-contracts.lua");
 if(result!=LuaRuntime::LuaInitResult::Success){char e[512]{};const auto n=LuaRuntime::CopyLastLuaErrorText(e,sizeof(e));std::printf("LUA_ERROR %.*s\n",static_cast<int>(n),e);return 1;}
 std::printf("CALLS=%u X1=%llu X2=%llu DECODED=%u\n",g_HostEngineCallTrampolineCalls,static_cast<unsigned long long>(g_HostEngineCallTrampolineLastIntegers[1]),static_cast<unsigned long long>(g_HostEngineCallTrampolineLastIntegers[2]),decoded);
 return 0;
}
'''

class SeedCurseContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix='seed-curse-contract-')
        cls.binary=build_lua_harness(source_root=SOURCE,workdir=Path(cls.temp.name),harness_source=HARNESS[:HARNESS.index('int main(')]+MAIN)
    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()
    def test_seed_guard_matches_original_nro_word(self):
        root=Path(__file__).resolve().parents[2]
        blob=next(root.glob('The Binding of Isaac_*/Program #0/1/.nro/Repentance.nro')).read_bytes()
        text=(root/'runtime/source/runtime_constants.hpp').read_text()
        for name,offset in [('kSeedsSetStartSeedEntryWord',0x4a1114),('kEntityPlayerDischargeActiveItemEntryWord',0x2b9540),('kEntityGetMovementDirectionEntryWord',0x5c8ac)]:
            with self.subTest(entry=name):
                actual=struct.unpack_from('<I',blob,offset)[0]
                declared=int(re.search(name+r'\s*=\s*(0x[0-9a-fA-F]+)',text)[1],16)
                self.assertEqual(actual,declared,'入口必须按原NRO小端指令字核验')
    def test_arguments_and_native_registers(self):
        for case,expected in [('curse_true','CALLS=1 X1=1 X2=1 DECODED=0'),('curse_false','CALLS=1 X1=1 X2=0 DECODED=0'),('seed_string','CALLS=1 X1=4045620583 X2=0 DECODED=1'),('seed_empty','CALLS=1 X1=0 X2=0 DECODED=1'),('seed_badguard','CALLS=0 X1=0 X2=0 DECODED=0'),('seed_number','CALLS=1 X1=1234567890 X2=0 DECODED=0'),('discharge','CALLS=1 X1=0 X2=0 DECODED=0'),('discharge_default','CALLS=1 X1=0 X2=0 DECODED=0'),('direction','CALLS=1 X1=0 X2=0 DECODED=0'),('arguments','CALLS=0')]:
            with self.subTest(case=case):
                r=subprocess.run([str(self.binary),case],capture_output=True,text=True)
                self.assertEqual(r.returncode,0,r.stdout+r.stderr);self.assertIn(expected,r.stdout)
