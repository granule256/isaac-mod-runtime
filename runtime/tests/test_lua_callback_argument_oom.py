"""参数userdata分配失败必须落入受保护调用，不能panic或泄漏外层状态。"""
import subprocess,tempfile,unittest
from pathlib import Path
from unittest import mock
from . import test_support
ROOT=Path(__file__).resolve().parents[2];SOURCE=ROOT/'runtime/source'
BRIDGE=r'''
namespace LuaRuntime {
struct FailingAlloc {lua_Alloc original;void* context;};
void* RejectAllocation(void* context,void* block,size_t oldSize,size_t newSize){
 auto* a=static_cast<FailingAlloc*>(context);
 if(newSize>oldSize)return nullptr;
 return a->original(a->context,block,oldSize,newSize);
}
extern "C" bool ProbeArgumentOOM(){
 if(!lua_checkstack(g_LuaState,100))return false;
 const int top=lua_gettop(g_LuaState);
 const auto owner=g_ErrorContextOwner,id=g_ErrorContextCallbackId;
 const auto manager=g_CurrentCallbackManager.load();const auto scope=InManagedCallbackScope();
 void* context=nullptr;const auto allocator=lua_getallocf(g_LuaState,&context);
 FailingAlloc failing{allocator,context};lua_setallocf(g_LuaState,RejectAllocation,&failing);
 LuaCallbackInvoker invoker{0x12345678,true,false};invoker.arguments.AddVector(1,2);
 isaac::runtime::CallbackDispatcher dispatcher{g_CallbackRegistry,invoker};
 const auto report=dispatcher.Dispatch(isaac::runtime::kCallbackPostUpdate,isaac::runtime::ThreadAffinity::Any);
 lua_setallocf(g_LuaState,allocator,context);
 const bool restored=report.failed==1 && lua_gettop(g_LuaState)==top &&
  g_ErrorContextOwner==owner && g_ErrorContextCallbackId==id &&
  g_CurrentCallbackManager.load()==manager && InManagedCallbackScope()==scope;
 const auto retry=dispatcher.Dispatch(isaac::runtime::kCallbackPostUpdate,isaac::runtime::ThreadAffinity::Any);
 return restored && retry.failed==0 && retry.invoked==1 && lua_gettop(g_LuaState)==top;
}
}
'''
DRIVER=r'''
#include "lua_runtime.hpp"
#include <cstring>
extern "C" bool ProbeArgumentOOM();
int main(){
 const char* script=R"lua(local m=RegisterMod('oom',1);_probe={count=0};m:AddCallback(1,function(_,offset) assert(offset.X==1 and offset.Y==2);_probe.count=_probe.count+1 end))lua";
 if(LuaRuntime::InitializeFromBuffer(script,std::strlen(script),"@oom.lua")!=LuaRuntime::LuaInitResult::Success)return 1;
 if(!ProbeArgumentOOM())return 2;
 if(!LuaRuntime::TakeCallbackError())return 3;
 double count=0;if(LuaRuntime::ReadLuaTableNumber("_probe","count",&count)!=0||count!=1)return 4;
}
'''
class CallbackArgumentOOMTests(unittest.TestCase):
 def test_argument_oom_is_caught_and_next_callback_works(self):
  with tempfile.TemporaryDirectory(prefix='isaac-callback-oom-') as td:
   td=Path(td);copy=td/'instrumented_runtime.cpp';copy.write_text((SOURCE/'lua_runtime.cpp').read_text()+BRIDGE)
   sources=tuple(copy if p==SOURCE/'lua_runtime.cpp' else p for p in test_support.layered_lua_runtime_sources(SOURCE))
   with mock.patch.object(test_support,'layered_lua_runtime_sources',return_value=sources):
    binary=test_support.build_lua_harness(source_root=SOURCE,workdir=td,harness_source=DRIVER)
   r=subprocess.run([str(binary)],capture_output=True,text=True)
   self.assertEqual(r.returncode,0,r.stdout+r.stderr)
if __name__=='__main__':unittest.main()
