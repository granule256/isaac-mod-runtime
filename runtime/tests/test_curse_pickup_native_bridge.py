"""真实内部上下文：首Random资格标记，12汇合阶段，37原局部与w20重载。"""
import re,subprocess,tempfile,unittest
from pathlib import Path
from . import test_lua_entity_query as fixture
from .test_support import build_lua_harness
ROOT=Path(__file__).resolve().parents[2]
MAIN=r'''
#include "cold_callbacks_internal_hook.hpp"
static unsigned randomCalls{};static void* rngWant{};
static unsigned Random(void* self,unsigned chance){assert(self==rngWant&&chance==7);++randomCalls;return 3;}
int main(){
 static_cast<void>(kScriptTemplate);static_cast<void>(&HarnessHasCollectible);static_cast<void>(&BuildPrelude);static_cast<void>(&ExpectNumber);
 CreateBlocks();FillEntities();PublishLists();PublishGame();PublishEntityList(g_RoomBytes,true);
 LuaRuntime::SetEngineModuleBase(g_EngineBase);LuaRuntime::SetGameBindings(AddressOf(g_OwnerSlotBytes),0x2222);
 const std::string script=R"lua(
 local m=RegisterMod('native12-37',1);_cold={curse=0,pickup=0}
 m:AddCallback(12,function(_,f)_cold.curse=_cold.curse+1;assert(f==5);return 0 end)
 m:AddCallback(37,function(_,e,v,s)_cold.pickup=_cold.pickup+1;assert(e.Type==5 and v==10 and s==7);return {40,{}} end)
 )lua";
 if(LuaRuntime::InitializeFromBuffer(script.data(),script.size(),"@cold-native.lua")!=LuaRuntime::LuaInitResult::Success)return 1;
 isaac::runtime::ColdCallbackNativeBindings bindings{};bindings.random=Random;
 isaac::runtime::relay::InternalHookContext ctx{},second{};
 unsigned char rng[16]{};rngWant=rng;ctx.x[0]=reinterpret_cast<std::uintptr_t>(rng);ctx.x[1]=7;ctx.x[21]=7;
 isaac::runtime::LevelCurseFirstRandomInternalCallback(ctx,&bindings);
 if(ctx.x[0]!=3||ctx.x[21]!=(0x100000000ULL|7)||randomCalls!=1)return 2;
 alignas(8) unsigned char level[32]{};unsigned flags=5;std::memcpy(level+12,&flags,4);
 ctx.x[19]=reinterpret_cast<std::uintptr_t>(level);
 isaac::runtime::LevelCurseEvaluateInternalCallback(ctx,nullptr);std::memcpy(&flags,level+12,4);
 if(flags!=0||ctx.x[21]!=7)return 3;
 // 没到首Random的另一调用不继承全局资格，保持原flags5。
 flags=5;std::memcpy(level+12,&flags,4);second.x[19]=ctx.x[19];second.x[21]=7;
 isaac::runtime::LevelCurseEvaluateInternalCallback(second,nullptr);std::memcpy(&flags,level+12,4);if(flags!=5)return 4;
 alignas(16) unsigned char frame[64]{};auto fp=reinterpret_cast<std::uintptr_t>(frame+32);
 unsigned v=10,s=7;std::memcpy(frame+28,&v,4);std::memcpy(frame+24,&s,4);
 ctx={};ctx.x[19]=AddressOf(g_Entities[kPickup]);ctx.x[29]=fp;ctx.x[20]=10;ctx.x[27]=0xabcdef;ctx.nzcv=0xa0000000;
 isaac::runtime::PickupSelectionInternalCallback(ctx,nullptr);std::memcpy(&v,frame+28,4);std::memcpy(&s,frame+24,4);
 if(v!=40||s!=7||ctx.x[20]!=40||ctx.x[27]!=0xabcdef||ctx.nzcv!=0xa0000000||!LuaRuntime::TakeCallbackError())return 5;
 double curse{},pickup{};if(LuaRuntime::ReadLuaTableNumber("_cold","curse",&curse)||LuaRuntime::ReadLuaTableNumber("_cold","pickup",&pickup)||curse!=1||pickup!=1)return 6;
 return 0;
}
'''
class ColdNativeBridgeTests(unittest.TestCase):
 def test_real_context_and_lua_timing(self):
  header=ROOT/'runtime/source/cold_callbacks_internal_hook.hpp';self.assertTrue(header.exists(),'12/37真实上下文桥尚未实施')
  with tempfile.TemporaryDirectory() as tmp:
   source='#include <cassert>\n'+fixture.HARNESS[:fixture.HARNESS.index('int main(')]+MAIN
   source=re.sub(r'namespace GameFileReader \{\nTextReadResult[\s\S]*?\n\}\n\}', '',source,count=1)
   binary=build_lua_harness(source_root=fixture.SOURCE,workdir=Path(tmp),harness_source=source,extra_sources=(ROOT/'runtime/source/cold_callbacks_internal_hook.cpp',))
   r=subprocess.run([str(binary)],capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
