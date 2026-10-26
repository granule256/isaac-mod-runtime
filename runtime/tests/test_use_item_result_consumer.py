"""用真实入口回调体和真实Lua派发验证充能/移除的原生返回位。"""
import subprocess,tempfile,unittest
from pathlib import Path
from . import test_use_item_rng as rng
from .test_support import build_lua_harness
fixture=rng.fixture;ROOT=Path(__file__).resolve().parents[2]
PRE=r'''
#include "infrastructure/relay/entry_relay_binding.hpp"
#include "infrastructure/call/engine_call_access.hpp"
#include "infrastructure/memory/engine_field_access.hpp"
#include <cassert>
#include "use_item_internal_hook.hpp"
#include "interfaces/lua/isaac_api.hpp"
unsigned originalCalls{};
std::uint32_t originalItem=0xffffffffU;
std::uint64_t OriginalUse(void* p,std::uint32_t item,std::uint32_t,std::int32_t,std::int32_t){++originalCalls;originalItem=item;
 isaac::runtime::relay::InternalHookContext ctx{};ctx.x[27]=reinterpret_cast<std::uintptr_t>(p);ctx.x[20]=ctx.x[22]=1;ctx.originalSp=ctx.x[27]+0x400;
 isaac::runtime::UseItemNativeBoundaryBinding binding{true};isaac::runtime::UseItemNativeBoundaryCallback(ctx,&binding);
 return (ctx.x[20]<<8)|ctx.x[22];}
namespace isaac::runtime {std::uintptr_t EntryRelayFallbackEntry(HookId id)noexcept{return id==HookId::UseActiveItem?engine_call::AddressOfFunction(&OriginalUse):0;}}
'''
MAIN=r'''
int main(int argc,char**argv){const char* mode=argc>1?argv[1]:"false";PublishFakeMemory();LuaRuntime::ObserveGameThread();WriteAt<std::uint8_t>(g_PlayerBytes,kEntityExistsOffset,1);LuaRuntime::SetGameBindings(AddressOf(g_OwnerSlotBytes),0x2222);LuaRuntime::SetRngBindings(reinterpret_cast<std::uintptr_t>(&HostSetSeed),reinterpret_cast<std::uintptr_t>(&HostNext));
 std::vector<unsigned char> vector(32);WriteAt<std::uint32_t>(vector,16,123);WriteAt<std::uintptr_t>(g_PlayerBytes,kEntityPlayerCollectibleRngVectorOffset,AddressOf(vector));WriteAt<std::uintptr_t>(g_PlayerBytes,kEntityPlayerCollectibleRngVectorOffset+8,AddressOf(vector)+32);g_TestRoom.assign(kRoomDoorObjectTableOffset+8*sizeof(std::uintptr_t)+32,0);
 std::string source="local m=RegisterMod('use-result',1);m:AddCallback(1,function()end);";
 const char* value="{Discharge=false,Remove=false,ShowAnim=false}";std::uint64_t expected{};bool error=false;unsigned calls=1;std::uint32_t flags=4;std::uint32_t item=1;
 const bool emptyItem=!std::strcmp(mode,"zero")||!std::strcmp(mode,"zero-cancel");
 if(emptyItem){item=0;expected=0x101;source+="preCalls=0;useCalls=0;m:AddCallback(23,function()preCalls=preCalls+1;return ";source+=!std::strcmp(mode,"zero-cancel")?"true":"false";source+=" end);";}
 if(!std::strcmp(mode,"nil")){value="nil";expected=0x101;}
 if(!std::strcmp(mode,"partial")){value="{Discharge=false}";expected=0x100;}
 if(!std::strcmp(mode,"truthy")){value="{Discharge=0,Remove=false}";expected=1;}
 if(!std::strcmp(mode,"boolean")){value="true";expected=0x101;flags=1;}
 if(!std::strcmp(mode,"empty")){value="{}";expected=0x101;}
 if(!std::strcmp(mode,"cancel")){source+="m:AddCallback(23,function()return true end);";expected=1;calls=0;}
 if(!std::strcmp(mode,"metaerror")){value="setmetatable({},{__index=function(_,k)if k=='Discharge'then return false else error('bad-field')end end})";expected=0x100;error=true;}
 source+="m:AddCallback(3,function(_,id,r)useCalls=(useCalls or 0)+1;assert(r:GetSeed()==123);return ";source+=value;source+=" end)";
 assert(LuaRuntime::InitializeFromBuffer(source.data(),source.size(),"@use-result.lua")==LuaRuntime::LuaInitResult::Success);
 const auto result=EntryRelayUseActiveItemCallback(g_PlayerBytes.data(),item,flags,0,0);
 std::printf("RETURN=%llu EXPECTED=%llu ORIGINAL=%u SEED=%u\n",static_cast<unsigned long long>(result),static_cast<unsigned long long>(expected),originalCalls,Seed(vector,16));
 assert(result==expected&&originalCalls==calls&&originalItem==(calls?item:0xffffffffU));
 if(emptyItem){double n{};assert(LuaRuntime::ReadLuaGlobalNumber("preCalls",&n)&&n==0);assert(LuaRuntime::ReadLuaGlobalNumber("useCalls",&n)&&n==0);assert(Seed(vector,16)==123);}assert(LuaRuntime::TakeCallbackError()==error);

}
'''
class UseItemResultConsumerTests(unittest.TestCase):
 def test_actual_native_wrapper_consumes_lua_result(self):
  hook=(ROOT/'runtime/source/hook_manager.cpp').read_text();start=hook.index('extern "C" std::uint64_t EntryRelayUseActiveItemCallback(');end=hook.index('extern "C" void EntryRelayUseCardCallback',start);wrapper=hook[start:end]
  source=fixture.HARNESS[:fixture.HARNESS.index('GameRoomObservation ReadCurrentGameRoom(')]+rng.refs.MAIN[:rng.refs.MAIN.index('int main(')]+PRE+wrapper+MAIN
  for name in ('CURRENT_TINT','CURRENT_SHIFT','DEFAULT_TINT','SPLAT_TINT'):
   for i,v in enumerate(getattr(fixture,name)):source=source.replace(f'{name}_{i}',repr(v))
  for name in ('COLLECTIBLE_COUNT','TRINKET_COUNT','ENTITY_DEFAULT_COLOR_OFFSET','ENTITY_SPLAT_COLOR_OFFSET'):source=source.replace(name,str(getattr(fixture,name)))
  with tempfile.TemporaryDirectory(prefix='use-item-result-')as tmp:
   binary=build_lua_harness(source_root=fixture.SOURCE,workdir=Path(tmp),harness_source=source)
   for case in ('false','nil','partial','truthy','boolean','empty','cancel','metaerror','zero','zero-cancel'):
    with self.subTest(case=case):
     r=subprocess.run([str(binary),case],capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
