"""用真实Lua派发和入口wrapper证明3号发生在原生后处理之前。"""
import subprocess,tempfile,unittest
from pathlib import Path
from . import test_use_item_rng as rng
from .test_support import build_lua_harness
ROOT=Path(__file__).resolve().parents[2]
PRE=r'''
#include "infrastructure/relay/entry_relay_binding.hpp"
#include "infrastructure/call/engine_call_access.hpp"
#include "infrastructure/memory/engine_field_access.hpp"
#include <cassert>
#include <thread>
#if __has_include("use_item_internal_hook.hpp")
#include "use_item_internal_hook.hpp"
#include "interfaces/lua/isaac_api.hpp"
#endif
unsigned nativeCalls{};std::uintptr_t rngBytes{};bool defaultDischarge=true,mutateState=false,refreshCache=false;
extern "C" {extern std::uint32_t g_HostEngineCallTrampolineCalls;extern std::uintptr_t g_HostEngineCallTrampolineLastTarget;extern std::uint64_t g_HostEngineCallTrampolineLastIntegers[8];}
std::uint64_t OriginalUse(void* player,std::uint32_t,std::uint32_t,std::int32_t,std::int32_t){
 ++nativeCalls;std::uint64_t result=0x101;
#if __has_include("use_item_internal_hook.hpp")
 isaac::runtime::relay::InternalHookContext ctx{};ctx.x[27]=reinterpret_cast<std::uintptr_t>(player);ctx.x[20]=1;ctx.x[22]=1;ctx.originalSp=ctx.x[27]+0x400;
 isaac::runtime::UseItemNativeBoundaryBinding binding{defaultDischarge,refreshCache};ctx.x[23]=ctx.x[27]+0x600;ctx.x[8]=0x11223344;
 isaac::runtime::UseItemNativeBoundaryCallback(ctx,&binding);isaac::runtime::UseItemNativeBoundaryCallback(ctx,&binding);if(refreshCache)assert(ctx.x[8]==0x1a2b3c4dU);result=(ctx.x[20]<<8)|ctx.x[22];
#else
 (void)player;
#endif
 // 原生后处理由独立观测量表示；回调必须在这里之前读到seed123。
 auto* seed=reinterpret_cast<std::uint32_t*>(rngBytes);++*seed;return result;
}
namespace isaac::runtime {std::uintptr_t EntryRelayFallbackEntry(HookId id)noexcept{return id==HookId::UseActiveItem?engine_call::AddressOfFunction(&OriginalUse):0;}}
'''
MAIN=r'''
int main(int argc,char**argv){assert(argc==2);const std::string mode=argv[1];PublishFakeMemory();WriteAt<std::uint8_t>(g_PlayerBytes,kEntityExistsOffset,1);LuaRuntime::ObserveGameThread();LuaRuntime::SetGameBindings(AddressOf(g_OwnerSlotBytes),0x2222);LuaRuntime::SetRngBindings(reinterpret_cast<std::uintptr_t>(&HostSetSeed),reinterpret_cast<std::uintptr_t>(&HostNext));
 refreshCache=mode=="config-refresh";const bool mapped=mode=="mapped";const unsigned item=mapped?59:1,postItem=mapped?34:1;std::vector<unsigned char> vector(60*16);WriteAt<std::uint32_t>(vector,item*16,123);WriteAt<std::uint32_t>(vector,postItem*16,123);rngBytes=AddressOf(vector)+postItem*16;WriteAt<std::uintptr_t>(g_PlayerBytes,kEntityPlayerCollectibleRngVectorOffset,AddressOf(vector));WriteAt<std::uintptr_t>(g_PlayerBytes,kEntityPlayerCollectibleRngVectorOffset+8,AddressOf(vector)+vector.size());g_TestRoom.assign(kRoomDoorObjectTableOffset+8*sizeof(std::uintptr_t)+32,0);
 const bool offthread=mode=="offthread";const bool noCallback=mode=="no-callback-owned";const bool owned=mode=="owned"||noCallback;const unsigned flags=owned?68:4;
 const bool gate=mode=="state-gated",special=mode=="special-default",explicitTrue=gate||mode=="state-change-gated";
 defaultDischarge=!special;mutateState=mode=="state-change-gated"||mode=="state-change-allow";
 WriteAt<std::uint32_t>(g_PlayerBytes,0x19d4,gate||mode=="state-change-allow"?2:0);
 FROZEN_REMOVE
 WriteAt<std::uint32_t>(g_PlayerBytes,0x654,0x11223344);
 std::string source="local m=RegisterMod('boundary',1);m:AddCallback(1,function()end);useCount=0;preCount=0;m:AddCallback(23,function(_,id,r)assert(id=="+std::to_string(item)+" and r:GetSeed()==123);preCount=preCount+1 end);";
 if(!noCallback){source+="m:AddCallback(3,function(_,id,r,p,flags,slot,custom)assert(id=="+std::to_string(postItem)+" and flags=="+std::to_string(flags)+" and slot==0 and custom==77);assert(r:GetSeed()==123,'3号晚于原生后处理');useCount=useCount+1;r:Next();return ";
  source+=owned?"{Remove=true}":explicitTrue||mode=="state-change-allow"?"{Discharge=true,Remove=false}":special?"nil":"{Discharge=false,Remove=false}";source+=" end)";}
 assert(LuaRuntime::InitializeFromBuffer(source.data(),source.size(),"@native-use-boundary.lua")==LuaRuntime::LuaInitResult::Success);
 std::uint64_t result{};auto call=[&](){result=EntryRelayUseActiveItemCallback(g_PlayerBytes.data(),item,flags,0,77);};if(offthread){std::thread thread(call);thread.join();}else call();
 if(LuaRuntime::TakeCallbackError()){LuaRuntime::LuaErrorHistoryEntryView e[8]{};auto n=LuaRuntime::CopyLuaErrorHistory(e,8);for(std::size_t i=0;i<n;++i)std::printf("%s\n",e[i].text);return 5;}
 const auto expected=offthread?0x101U:owned||mode=="state-change-allow"?1U:special?0x100U:0U;
 double count{},pre{};assert(LuaRuntime::ReadLuaGlobalNumber("useCount",&count)&&count==(noCallback||offthread?0:1));assert(LuaRuntime::ReadLuaGlobalNumber("preCount",&pre)&&pre==(offthread?0:1));
 assert(result==expected&&nativeCalls==1&&Seed(vector,postItem*16)==(noCallback||offthread?124:125));
 assert(isaac::runtime::ActiveUseItemFrame()==nullptr);
 if(owned){assert(g_HostEngineCallTrampolineCalls==1&&g_HostEngineCallTrampolineLastTarget==g_EngineBase+0x299b50);auto* v=g_HostEngineCallTrampolineLastIntegers;assert(v[0]==AddressOf(g_PlayerBytes)&&v[1]==postItem&&v[2]==0&&static_cast<std::int32_t>(v[3])==-1&&v[4]==1);}
 else assert(g_HostEngineCallTrampolineCalls==0);
}
'''

class UseItemNativeBoundaryTests(unittest.TestCase):
 def test_callback_runs_before_native_postprocessing(self):
  hook=(ROOT/'runtime/source/hook_manager.cpp').read_text();start=hook.index('extern "C" std::uint64_t EntryRelayUseActiveItemCallback(');end=hook.index('extern "C" void EntryRelayUseCardCallback',start);wrapper=hook[start:end]
  source=rng.fixture.HARNESS[:rng.fixture.HARNESS.index('GameRoomObservation ReadCurrentGameRoom(')]+rng.refs.MAIN[:rng.refs.MAIN.index('int main(')]+PRE+wrapper+MAIN
  source=source.replace('void HostNext(void* object){','extern bool mutateState,refreshCache;void HostNext(void* object){if(refreshCache)WriteAt<std::uint32_t>(g_PlayerBytes,0x654,0x1a2b3c4d);if(mutateState){std::uint32_t old{};std::memcpy(&old,g_PlayerBytes.data()+0x19d4,4);WriteAt<std::uint32_t>(g_PlayerBytes,0x19d4,old==0?2:0);}')
  nro=next(Path('/Users/kelinls/code/github/isaac mod').glob('The Binding*Afterbirth*/*/1/.nro/Repentance.nro')).read_bytes()
  source=source.replace('FROZEN_REMOVE','const unsigned char removalGuard[]={'+','.join(map(str,nro[0x299b50:0x299b60]))+'};std::memcpy(g_ModuleBytes.data()+0x299b50,removalGuard,16);')
  for name in ('CURRENT_TINT','CURRENT_SHIFT','DEFAULT_TINT','SPLAT_TINT'):
   for i,v in enumerate(getattr(rng.fixture,name)):source=source.replace(f'{name}_{i}',repr(v))
  for name in ('COLLECTIBLE_COUNT','TRINKET_COUNT','ENTITY_DEFAULT_COLOR_OFFSET','ENTITY_SPLAT_COLOR_OFFSET'):source=source.replace(name,str(getattr(rng.fixture,name)))
  with tempfile.TemporaryDirectory(prefix='use-native-boundary-')as tmp:
   binary=build_lua_harness(source_root=rng.fixture.SOURCE,workdir=Path(tmp),harness_source=source)
   for mode in ('normal','special-default','state-gated','state-change-gated','state-change-allow','mapped','owned','no-callback-owned','offthread','config-refresh'):
    with self.subTest(mode=mode):
     r=subprocess.run([str(binary),mode],capture_output=True,text=True);print(mode,r.returncode,r.stdout+r.stderr,flush=True);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
