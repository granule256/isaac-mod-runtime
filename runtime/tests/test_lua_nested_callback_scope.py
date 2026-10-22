"""嵌套真实Lua派发返回后恢复外层权限、manager及错误归属，成功/失败都不泄漏。"""
import subprocess,tempfile,unittest
from pathlib import Path
from unittest import mock
from . import test_support
ROOT=Path(__file__).resolve().parents[2]
SOURCE=ROOT/'runtime/source'
BRIDGE=r'''
namespace LuaRuntime {
int ReentryProbe(lua_State* state) {
 const auto beforeOwner=g_ErrorContextOwner,beforeId=g_ErrorContextCallbackId;
 const auto beforeManager=g_CurrentCallbackManager.load();
 bool beforeScope=InManagedCallbackScope();
 static_cast<void>(DispatchGetPillColor(123,6));
 bool restored=beforeScope && InManagedCallbackScope() &&
  g_ErrorContextOwner==beforeOwner && g_ErrorContextCallbackId==beforeId &&
  g_CurrentCallbackManager.load()==beforeManager;
 lua_pushboolean(state,restored);return 1;
}
extern "C" void InstallReentryProbe(){lua_pushcfunction(g_LuaState,ReentryProbe);lua_setglobal(g_LuaState,"_reenter");}
extern "C" bool DispatchOuterProbe(){
 const auto owner=g_ErrorContextOwner,id=g_ErrorContextCallbackId;
 const auto manager=g_CurrentCallbackManager.load();bool scope=InManagedCallbackScope();
 LuaCallbackInvoker invoker{0x12345678,true,false};
 isaac::runtime::CallbackDispatcher dispatcher{g_CallbackRegistry,invoker};
 const auto result=dispatcher.Dispatch(isaac::runtime::kCallbackPostUpdate,isaac::runtime::ThreadAffinity::Any);
 return result.failed==0 && g_ErrorContextOwner==owner && g_ErrorContextCallbackId==id &&
  g_CurrentCallbackManager.load()==manager && InManagedCallbackScope()==scope;
}
}
'''
DRIVER=r'''
#include "lua_runtime.hpp"
#include <cstring>
extern "C" void InstallReentryProbe();
extern "C" bool DispatchOuterProbe();
int main(){
 const char* script=R"lua(
local m=RegisterMod('nested',1)
_probe={fail=false,count=0}
m:AddCallback(1,function() assert(_reenter(),'outer scope lost');_probe.count=_probe.count+1;_probe.fail=true end)
m:AddCallback(64,function() if _probe.fail then error('nested-error') end;return 4 end)
)lua";
 if(LuaRuntime::InitializeFromBuffer(script,std::strlen(script),"@nested.lua")!=LuaRuntime::LuaInitResult::Success)return 1;
 InstallReentryProbe();
 if(!DispatchOuterProbe())return 2;
 if(LuaRuntime::TakeCallbackError())return 3;
 if(!DispatchOuterProbe())return 4;
 if(!LuaRuntime::TakeCallbackError())return 5;
 double count=0;if(LuaRuntime::ReadLuaTableNumber("_probe","count",&count)!=0||count!=2)return 6;
}
'''
class NestedCallbackScopeTests(unittest.TestCase):
 def test_success_and_error_restore_outer_scope(self):
  with tempfile.TemporaryDirectory(prefix='isaac-nested-') as td:
   td=Path(td);copy=td/'instrumented_runtime.cpp'
   copy.write_text((SOURCE/'lua_runtime.cpp').read_text()+BRIDGE)
   sources=tuple(copy if p==SOURCE/'lua_runtime.cpp' else p for p in test_support.layered_lua_runtime_sources(SOURCE))
   with mock.patch.object(test_support,'layered_lua_runtime_sources',return_value=sources):
    binary=test_support.build_lua_harness(source_root=SOURCE,workdir=td,harness_source=DRIVER)
   r=subprocess.run([str(binary)],capture_output=True,text=True)
   self.assertEqual(r.returncode,0,r.stdout+r.stderr)
if __name__=='__main__':unittest.main()
