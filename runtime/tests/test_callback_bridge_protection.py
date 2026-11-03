"""Count real Lua protection boundaries; exercise nested errors and batch recovery."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock
from . import test_support

ROOT=Path(__file__).resolve().parents[2]
SOURCE=ROOT/'runtime/source'
BRIDGE=r'''
extern "C" {
#include "lstate.h"
}
namespace LuaRuntime {
int ProtectionDepth(lua_State* state) {
 unsigned count=0;auto* link=state->errorJmp;
 while(link){++count;std::memcpy(&link,link,sizeof(std::uintptr_t));}
 lua_pushinteger(state,count);return 1;
}
bool g_BridgeBodyEntered{};
int MarkBridgeBody(lua_State*){g_BridgeBodyEntered=true;return 0;}
int RootBridgeContext(lua_State* state){lua_pushboolean(state,g_ErrorContextOwner==0x10002&&g_ErrorContextCallbackId==1);return 1;}
extern "C" void InstallProtectionProbe(){
 lua_pushcfunction(g_LuaState,ProtectionDepth);lua_setglobal(g_LuaState,"protection_depth");
 lua_pushcfunction(g_LuaState,MarkBridgeBody);lua_setglobal(g_LuaState,"mark_body");
 lua_pushcfunction(g_LuaState,RootBridgeContext);lua_setglobal(g_LuaState,"root_context");
}
extern "C" double BenchmarkCallbackBridge(unsigned repeats) {
 LuaCallbackInvoker invoker{0,false,false};
 isaac::runtime::CallbackDispatcher dispatcher{g_CallbackRegistry,invoker};
 const auto start=std::chrono::steady_clock::now();
 for(unsigned i=0;i<repeats;++i){auto r=dispatcher.Dispatch(1,isaac::runtime::ThreadAffinity::Any);if(r.invoked!=22||r.failed)return -1;}
 return std::chrono::duration<double,std::nano>(std::chrono::steady_clock::now()-start).count()/(repeats*22);
}
struct BridgeFailingAlloc {lua_Alloc original;void* context;};
void* RejectBridgeAllocation(void* pointer,void* block,size_t oldSize,size_t newSize) {
 auto* alloc=static_cast<BridgeFailingAlloc*>(pointer);
 return newSize>oldSize?nullptr:alloc->original(alloc->context,block,oldSize,newSize);
}
extern "C" bool ProbeProtectedDispatch(int mode) {
 const int top=lua_gettop(g_LuaState);
 const auto owner=g_ErrorContextOwner,id=g_ErrorContextCallbackId;
 const auto manager=g_CurrentCallbackManager.load();const auto scope=InManagedCallbackScope();
 auto before=g_RuntimePerfCallbackCalls.load();
 LuaCallbackInvoker invoker{0x1234,true,false};
 isaac::runtime::CallbackDispatcher dispatcher{g_CallbackRegistry,invoker};
 void* allocContext=nullptr;const auto allocator=lua_getallocf(g_LuaState,&allocContext);
 BridgeFailingAlloc failing{allocator,allocContext};
 if(mode==7){
  if(!lua_checkstack(g_LuaState,128))return false;
  const auto warm=dispatcher.Dispatch(1,isaac::runtime::ThreadAffinity::Any);
  if(warm.failed||warm.invoked!=1)return false;
  before=g_RuntimePerfCallbackCalls.load();g_BridgeBodyEntered=false;
  lua_setallocf(g_LuaState,RejectBridgeAllocation,&failing);
 }
 const auto report=dispatcher.Dispatch(1,isaac::runtime::ThreadAffinity::Any);
 if(mode==7)lua_setallocf(g_LuaState,allocator,allocContext);
 const bool failed=mode==1||mode==3||mode==4||mode==7;
 const unsigned expectedInvoked=mode==1?1:failed?0:1;
 if(report.failed!=unsigned(failed)||report.invoked!=expectedInvoked){std::fprintf(stderr,"report failed=%u invoked=%u expected=%u/%u\n",report.failed,report.invoked,unsigned(failed),expectedInvoked);return false;}
 const unsigned expectedCalls=mode==0||mode==1||mode==2||mode==6||mode==8?2:1;
 if(g_RuntimePerfCallbackCalls.load()-before!=expectedCalls){std::fprintf(stderr,"perf calls=%llu expected=%u\n",static_cast<unsigned long long>(g_RuntimePerfCallbackCalls.load()-before),expectedCalls);return false;}
 if(lua_gettop(g_LuaState)!=top||g_ErrorContextOwner!=owner||g_ErrorContextCallbackId!=id||
    g_CurrentCallbackManager.load()!=manager||InManagedCallbackScope()!=scope||g_ActiveCallbackBatch){std::fprintf(stderr,"scope/owner/stack not restored\n");return false;}
 if(failed){
  if(!TakeCallbackError())return false;
  bool found=false;
  for(const auto& error:g_LuaErrorHistory)if(error.text[0]&&error.owner==(mode==3?0:0x10002)&&error.callbackId==1)found=true;
  if(!found){for(const auto& e:g_LuaErrorHistory)if(e.text[0])std::fprintf(stderr,"error owner=%x id=%u text=%s\n",e.owner,e.callbackId,e.text);return false;}
 }
 if(mode==7){
  if(!g_BridgeBodyEntered)return false;
  const auto retry=dispatcher.Dispatch(1,isaac::runtime::ThreadAffinity::Any);
  if(retry.failed||retry.invoked!=1||lua_gettop(g_LuaState)!=top||g_ActiveCallbackBatch){std::fprintf(stderr,"retry failed=%u invoked=%u\n",retry.failed,retry.invoked);return false;}
 }
 return true;
}
}
'''
DRIVER=r'''
#include "lua_runtime.hpp"
#include <cstring>
#include <string>
#include <cstdio>
#include <chrono>
extern "C" void InstallProtectionProbe();
extern "C" bool ProbeProtectedDispatch(int);
extern "C" double BenchmarkCallbackBridge(unsigned);
int main(int argc,char**argv) {
 if(argc!=2)return 90;
 if(!std::strcmp(argv[1],"bench")){
  const char* script="local m=RegisterMod('bridge-bench',1);for i=1,22 do m:AddCallback(1,function()end)end";
  if(LuaRuntime::InitializeFromBuffer(script,std::strlen(script),"@bridge-bench.lua")!=LuaRuntime::LuaInitResult::Success)return 91;
  if(BenchmarkCallbackBridge(1000)<0)return 92;
  for(unsigned trial=0;trial<7;++trial){const auto value=BenchmarkCallbackBridge(6000);if(value<0)return 93;std::printf("BRIDGE %u %.3f\n",trial,value);}return 0;
 }
 const auto mode=std::stoi(argv[1]);const char* body=nullptr;
 const char* setup="local m=RegisterMod('protected-cost',1);_probe={count=0};m:AddCallback(1,function()end)";
 if(LuaRuntime::InitializeFromBuffer(setup,std::strlen(setup),"@protection-setup.lua")!=LuaRuntime::LuaInitResult::Success)return 1;
 InstallProtectionProbe();
 if(mode==0)body=R"lua(
local m=Isaac.GetCallbacks(1)[1].Mod
local errors={};m:AddCallback('inner',function() assert(protection_depth()==3);error(errors) end)
Isaac.GetCallbacks(1)[1].Function=function()
 assert(protection_depth()==1,"native depth "..protection_depth())
 local ok,e=pcall(Isaac.RunCallback,'inner');assert(not ok and e==errors)
 assert(protection_depth()==1,"native depth "..protection_depth());_probe.count=_probe.count+1
end
)lua";
 if(mode==1)body=R"lua(
local m=Isaac.GetCallbacks(1)[1].Mod
Isaac.GetCallbacks(1)[1].Function=function()_probe.count=_probe.count+1 end
m:AddCallback(1,function()error('direct-root-failure')end)
m:AddCallback(1,function()error('must-not-run')end)
)lua";
 if(mode==2)body=R"lua(
local m=Isaac.GetCallbacks(1)[1].Mod
m:AddCallback('matcher-inner',function()error('caught-matcher-inner')end)
setmetatable(Isaac.GetCallbacks(1),{__matchParams=function()
 local ok,e=pcall(Isaac.RunCallback,'matcher-inner');assert(not ok and e:find('caught-matcher-inner',1,true));return true
end})
Isaac.GetCallbacks(1)[1].Function=function()assert(protection_depth()==1,"native depth "..protection_depth());_probe.count=_probe.count+1 end
)lua";
 if(mode==3)body=R"lua(
local entry=Isaac.GetCallbacks(1)[1];entry.Function=nil
setmetatable(entry,{__index=function(_,key)if key=='Function'then error('function-getter-failure')end end})
)lua";
 if(mode==4)body=R"lua(
Isaac.GetCallbacks(1)[1].Function=setmetatable({},{__call=function()error('callable-table-failure')end})
)lua";
 if(mode==5)body=R"lua(
local m=Isaac.GetCallbacks(1)[1].Mod
local err={}
m:AddCallback('manual-only',function()assert(protection_depth()==3);error(err)end)
local ok,e=pcall(Isaac.RunCallback,'manual-only');assert(not ok and e==err)
)lua";
 if(mode==6)body=R"lua(
local entry=Isaac.GetCallbacks(1)[1];local m=entry.Mod;local err={}
m:AddCallback('getter-inner',function()assert(protection_depth()==3);error(err)end)
local fn=function()assert(protection_depth()==1);_probe.count=_probe.count+1 end
entry.Function=nil
setmetatable(entry,{__index=function(_,key)
 if key=='Function' then local ok,e=pcall(Isaac.RunCallback,'getter-inner');assert(not ok and e==err);return fn end
end})
)lua";
 if(mode==7)body=R"lua(
Isaac.GetCallbacks(1)[1].Function=function()mark_body();local value=string.rep('x',1000000);assert(#value==1000000)end
)lua";
 if(mode==8)body=R"lua(
local m=Isaac.GetCallbacks(1)[1].Mod;local err={}
m:AddCallback('coroutine-inner',function()assert(protection_depth()>=2);error(err)end)
Isaac.GetCallbacks(1)[1].Function=function()
 assert(protection_depth()==1 and root_context())
 local co=coroutine.create(function()
  local ok,e=pcall(Isaac.RunCallback,'coroutine-inner');assert(not ok and e==err)
 end)
 local ok,e=coroutine.resume(co);assert(ok,e)
 assert(protection_depth()==1 and root_context())
end
)lua";
 if(!body||LuaRuntime::InitializeFromBuffer(body,std::strlen(body),"@protection-cases.lua")!=LuaRuntime::LuaInitResult::Success)return 2;
 // Repeat failures as well: pending timing, depth and owner must always clear.
 for(unsigned i=0;i<8;++i)if(!ProbeProtectedDispatch(mode)){char e[512]{};static_cast<void>(LuaRuntime::CopyLastLuaErrorText(e,sizeof(e)));std::fprintf(stderr,"mode %d: %s",mode,e);return 3;}
 if(LuaRuntime::TakeCallbackError())return 4;
}
'''

class CallbackProtectionCostTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(prefix='callback-protection-');p=Path(cls.tmp.name)
        runtime=p/'instrumented_runtime.cpp';runtime.write_text('#include <chrono>\n'+(SOURCE/'lua_runtime.cpp').read_text()+BRIDGE)
        sources=tuple(runtime if f==SOURCE/'lua_runtime.cpp' else f for f in test_support.layered_lua_runtime_sources(SOURCE))
        with mock.patch.object(test_support,'layered_lua_runtime_sources',return_value=sources):
            cls.binary=test_support.build_lua_harness(source_root=SOURCE,workdir=p,harness_source=DRIVER)
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def mode(self,n):
        result=subprocess.run([str(self.binary),str(n)],capture_output=True,text=True,timeout=20)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
    def test_native_batch_has_one_boundary_and_caught_manual_error_restores_it(self):self.mode(0)
    def test_direct_failure_stops_remaining_callbacks_and_restores_batch(self):self.mode(1)
    def test_matcher_catches_manual_error_before_native_callback(self):self.mode(2)
    def test_function_getter_error_is_caught_and_batch_recovers(self):self.mode(3)
    def test_callable_table_error_keeps_attribution(self):self.mode(4)
    def test_manual_dispatch_retains_independent_protection(self):self.mode(5)
    def test_coroutine_manual_error_restores_native_owner(self):self.mode(8)
    def test_callback_body_oom_restores_and_retries(self):self.mode(7)
    def test_function_getter_catches_manual_error_inside_native_entry(self):self.mode(6)
