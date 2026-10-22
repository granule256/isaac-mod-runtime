"""同一Lua权威表的Owner、返回表回收、同id手动递归观测边界。"""
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from . import test_support
ROOT=Path(__file__).resolve().parents[2]
SOURCE=ROOT/'runtime/source'
BRIDGE=r'''
namespace LuaRuntime {
struct DiagnosticAlloc {lua_Alloc original;void* context;};
void* FailDiagnosticAllocation(void* pointer,void* block,size_t oldSize,size_t newSize) {
 auto* a=static_cast<DiagnosticAlloc*>(pointer);if(newSize>oldSize)return nullptr;
 return a->original(a->context,block,oldSize,newSize);
}
extern "C" bool ProbeBatchLife(int mode) {
 const int top=lua_gettop(g_LuaState);
 LuaCallbackInvoker invoker{0x12345678,true,false};
 isaac::runtime::CallbackDispatcher dispatcher{g_CallbackRegistry,invoker};
 if(mode==0){
  const auto owner=isaac::runtime::ModHandle{3,1};
  const auto r=dispatcher.DispatchOwner(owner,1,isaac::runtime::ThreadAffinity::Any);
  return r.invoked==1&&r.failed==0&&lua_gettop(g_LuaState)==top;
 }
 if(mode==1){
  for(int i=0;i<2048;++i){auto r=dispatcher.Dispatch(1,isaac::runtime::ThreadAffinity::Any);
   if(r.invoked!=1||r.failed||lua_gettop(g_LuaState)!=top)return false;}
  lua_gc(g_LuaState,LUA_GCCOLLECT,0);lua_gc(g_LuaState,LUA_GCCOLLECT,0);
  return lua_gettop(g_LuaState)==top;
 }
 if(mode==2){
  for(int i=0;i<256;++i){
   lua_pushnil(g_LuaState);invoker.tableStackIndex=top+1;
   auto r=dispatcher.DispatchModifying(71,isaac::runtime::ThreadAffinity::Any,isaac::runtime::CallbackRegistry::kNoCallbackFilter);
   if(r.invoked!=1||r.failed||!r.hasTable||invoker.tableOwner!=0x10002||!lua_istable(g_LuaState,top+1))return false;
   lua_getfield(g_LuaState,top+1,"Type");const bool valid=lua_tointeger(g_LuaState,-1)==5;
   lua_settop(g_LuaState,top);if(!valid)return false;
  }
  lua_gc(g_LuaState,LUA_GCCOLLECT,0);lua_gc(g_LuaState,LUA_GCCOLLECT,0);return true;
 }
 if(mode==3){
  const auto before=g_RuntimePerfCallbackCalls.load();
  lua_pushnil(g_LuaState);invoker.tableStackIndex=top+1;
  auto r=dispatcher.DispatchModifying(71,isaac::runtime::ThreadAffinity::Any,isaac::runtime::CallbackRegistry::kNoCallbackFilter);
  const auto calls=g_RuntimePerfCallbackCalls.load()-before;
  lua_getfield(g_LuaState,top+1,"Type");const auto type=lua_tointeger(g_LuaState,-1);
  lua_settop(g_LuaState,top);
  return r.invoked==1&&r.failed==0&&r.hasTable&&invoker.tableOwner==0x10002&&type==5&&calls==3;
 }
 if(mode==4){
  if(!lua_checkstack(g_LuaState,100))return false;
  lua_getglobal(g_LuaState,"Isaac");lua_getfield(g_LuaState,-1,"AddPriorityCallback");
  lua_CFunction changed=nullptr;
  for(int index=1;;++index){const char* name=lua_getupvalue(g_LuaState,-1,index);if(!name)break;
   if(!std::strcmp(name,"changed"))changed=lua_tocfunction(g_LuaState,-1);lua_pop(g_LuaState,1);}
  lua_settop(g_LuaState,top);if(!changed)return false;
  const auto registrations=DispatchableCallbackRegistrationCount();
  void* context=nullptr;const auto allocator=lua_getallocf(g_LuaState,&context);
  DiagnosticAlloc failing{allocator,context};
  lua_setallocf(g_LuaState,FailDiagnosticAllocation,&failing);
  isaac::runtime::g_CallbackDiagnosticViewIncomplete=0;
  lua_pushcfunction(g_LuaState,changed);lua_pushinteger(g_LuaState,1);lua_pushboolean(g_LuaState,0);
  const int status=lua_pcall(g_LuaState,2,0,0);
  lua_setallocf(g_LuaState,allocator,context);
  if(status!=LUA_OK){lua_settop(g_LuaState,top);return false;}
  if(isaac::runtime::g_CallbackDiagnosticViewIncomplete!=1||DispatchableCallbackRegistrationCount()!=registrations)return false;
  // 预留槽刷新在allocator拒绝所有增长时仍完成，不产生中间luaL_ref泄漏。
  lua_gc(g_LuaState,LUA_GCCOLLECT,0);lua_gc(g_LuaState,LUA_GCCOLLECT,0);
  return lua_gettop(g_LuaState)==top;
 }
 if(mode==6){
  if(DispatchableCallbackRegistrationCount()!=1 || (RegisteredCallbackKindMaskLow()&(1ULL<<1))==0)return false;
  const auto r=dispatcher.Dispatch(1,isaac::runtime::ThreadAffinity::Any);
  if(r.invoked!=1||r.failed)return false;
  for(const auto& bucket:g_RuntimePerfCallbackBuckets)
   if(bucket.count && static_cast<std::uint32_t>(bucket.key)==0xffffffffU)return false;
  return true;
 }
 if(mode==5){
  if(!lua_checkstack(g_LuaState,100))return false;
  const auto owner=g_ErrorContextOwner,id=g_ErrorContextCallbackId;
  const auto manager=g_CurrentCallbackManager.load();const auto scope=InManagedCallbackScope();
  void* context=nullptr;const auto allocator=lua_getallocf(g_LuaState,&context);
  DiagnosticAlloc failing{allocator,context};lua_setallocf(g_LuaState,FailDiagnosticAllocation,&failing);
  const auto failure=dispatcher.Dispatch(1,isaac::runtime::ThreadAffinity::Any);
  lua_setallocf(g_LuaState,allocator,context);
  if(failure.failed!=1||failure.invoked!=0||lua_gettop(g_LuaState)!=top||
   g_ErrorContextOwner!=owner||g_ErrorContextCallbackId!=id||g_CurrentCallbackManager.load()!=manager||InManagedCallbackScope()!=scope)return false;
  if(!TakeCallbackError())return false;
  const auto retry=dispatcher.Dispatch(1,isaac::runtime::ThreadAffinity::Any);
  return retry.failed==0&&retry.invoked==1&&lua_gettop(g_LuaState)==top;
 }
 return false;
}
}
'''
DRIVER=r'''
#include "lua_runtime.hpp"
#include <cstring>
#include <string>
extern "C" bool ProbeBatchLife(int);
int main(int argc,char** argv){
 if(argc!=2)return 90;const int mode=std::stoi(argv[1]);const char* script=nullptr;
 if(mode==0)script=R"lua(local a=RegisterMod('one',1);local b=RegisterMod('two',1);_probe={count=0};a:AddCallback(1,function() error('wrong owner') end);b:AddCallback(1,function(self) assert(self==b);_probe.count=_probe.count+1 end))lua";
 if(mode==1)script=R"lua(local m=RegisterMod('void',1);_probe={count=0};m:AddCallback(1,function() return setmetatable({},{__gc=function() _probe.count=_probe.count+1 end}) end))lua";
 if(mode==2)script=R"lua(local m=RegisterMod('table',1);m:AddCallback(1,function() end);_probe={count=0};m:AddCallback(71,function() return setmetatable({Type=5},{__gc=function() _probe.count=_probe.count+1 end}) end))lua";
 if(mode==3)script=R"lua(local a=RegisterMod('one',1);local b=RegisterMod('two',1);a:AddCallback(1,function() end);local inner=false;a:AddCallback(71,function() if inner then return end;inner=true;local t=Isaac.RunCallback(71);assert(t.Type==9);inner=false;return {Type=5} end);b:AddCallback(71,function() return {Type=9} end))lua";
 if(mode==4)script=R"lua(local m=RegisterMod('diag-oom',1);_probe={count=0};for i=1,100 do local token=setmetatable({},{__gc=function() _probe.count=_probe.count+1 end});local fn=function() return token end;m:AddCallback(1,fn);m:RemoveCallback(1,fn) end)lua";
 if(mode==5)script=R"lua(local m=RegisterMod('matcher-oom',1);_probe={count=0};m:AddCallback(1,function() _probe.count=_probe.count+1 end);setmetatable(Isaac.GetCallbacks(1),{__matchParams=function() local allocated=string.rep('x',1000000);assert(#allocated==1000000);return true end}))lua";
 if(mode==6)script=R"lua(local m=RegisterMod('float-id',1);_probe={count=0};m:AddCallback(1.0,function() _probe.count=_probe.count+1 end);Isaac.RunCallback(1.0))lua";
 if(!script||LuaRuntime::InitializeFromBuffer(script,std::strlen(script),"@batch-life.lua")!=LuaRuntime::LuaInitResult::Success)return 1;
 if(!ProbeBatchLife(mode))return 2;if(LuaRuntime::TakeCallbackError())return 3;
 double count=0;if(mode<3||mode>=4){if(LuaRuntime::ReadLuaTableNumber("_probe","count",&count)!=0)return 4;const double expected=mode==0||mode==5?1:mode==1?2048:mode==2?256:mode==6?2:100;if(count!=expected)return 5;}
 return 0;
}
'''
class CallbackBatchLifecycleTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory(prefix='isaac-callback-life-');td=Path(cls.tmp.name)
  copied=td/'instrumented_runtime.cpp';copied.write_text((SOURCE/'lua_runtime.cpp').read_text()+BRIDGE)
  sources=tuple(copied if p==SOURCE/'lua_runtime.cpp' else p for p in test_support.layered_lua_runtime_sources(SOURCE))
  with mock.patch.object(test_support,'layered_lua_runtime_sources',return_value=sources):
   cls.binary=test_support.build_lua_harness(source_root=SOURCE,workdir=td,harness_source=DRIVER)
 @classmethod
 def tearDownClass(cls):cls.tmp.cleanup()
 def run_mode(self,mode):
  result=subprocess.run([str(self.binary),str(mode)],capture_output=True,text=True)
  self.assertEqual(result.returncode,0,result.stdout+result.stderr)
 def test_owner_dispatch_uses_real_lua_table(self):self.run_mode(0)
 def test_void_table_returns_are_collected(self):self.run_mode(1)
 def test_native_table_survives_consumer_then_is_collected(self):self.run_mode(2)
 def test_same_id_manual_recursion_keeps_batch_report_and_owner(self):self.run_mode(3)
 def test_diagnostic_refresh_needs_no_new_refs_when_allocator_rejects_growth(self):self.run_mode(4)
 def test_matcher_oom_restores_scope_and_recovers_next_dispatch(self):self.run_mode(5)
 def test_integral_float_id_preserves_registration_and_perf_metadata(self):self.run_mode(6)
if __name__=='__main__':unittest.main()
