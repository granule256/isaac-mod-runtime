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
 using namespace isaac::runtime;
 const auto beforeOwner=g_ErrorContextOwner,beforeId=g_ErrorContextCallbackId;
 const auto beforeManager=g_CurrentCallbackManager.load();
 bool beforeScope=InManagedCallbackScope();
 EngineGuardRememberReadable(0x1000,0x2000);
 EngineGuardRememberWritable(0x3000,0x4000);
 const auto epoch=EngineGuardDispatchEpoch().load();
 switch(lua_tointeger(state,1)) {
 case 0: static_cast<void>(DispatchGetPillColor(123,6));break;
 case 1: {float position[2]{};static_cast<void>(DispatchPreEntitySpawn(1000,1,0,position,position,0,123));break;}
 case 2: DispatchPostEntityRemove(0,1000);break;
 case 3: static_cast<void>(DispatchEntityTakeDamage(0,1,0,0,0,1000));break;
 case 4: DispatchEvaluateCache(0,1);break;
 }
 unsigned permissionQueries=0;
 for(unsigned i=0;i<256;++i) {
  if(!EngineGuardLookupCached(0x1100,4)) {++permissionQueries;EngineGuardRememberReadable(0x1000,0x2000);}
  if(!EngineGuardLookupWritable(0x3100,4)) {++permissionQueries;EngineGuardRememberWritable(0x3000,0x4000);}
 }
 std::printf("nested_guard mode=%lld queries=%u\n",static_cast<long long>(lua_tointeger(state,1)),permissionQueries);
 bool restored=beforeScope && InManagedCallbackScope() &&
  g_ErrorContextOwner==beforeOwner && g_ErrorContextCallbackId==beforeId &&
  g_CurrentCallbackManager.load()==beforeManager && EngineGuardDispatchActive().load()!=0 &&
  EngineGuardDispatchEpoch().load()==epoch && permissionQueries==0;
 lua_pushboolean(state,restored);return 1;
}
extern "C" void InstallReentryProbe(){lua_pushcfunction(g_LuaState,ReentryProbe);lua_setglobal(g_LuaState,"_reenter");}
extern "C" bool DispatchOuterProbe(){
 const ManagedEngineDispatchScope guard;
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
#include "infrastructure/memory/engine_memory_guard.hpp"
#include <cstring>
#include <string>
extern "C" void InstallReentryProbe();
extern "C" bool DispatchOuterProbe();
int main(int argc,char**argv){
 if(argc!=2)return 10;
 const char* script=R"lua(
local m=RegisterMod('nested',1)
_probe={fail=false,count=0,mode=MODE}
m:AddCallback(1,function() assert(_reenter(_probe.mode),'outer scope lost');_probe.count=_probe.count+1;_probe.fail=true end)
m:AddCallback(64,function() if _probe.fail then error('nested-error') end;return 4 end)
m:AddCallback(24,function() if _probe.fail then error('nested-error') end end)
m:AddCallback(67,function() if _probe.fail then error('nested-error') end end)
m:AddCallback(11,function() if _probe.fail then error('nested-error') end end)
m:AddCallback(8,function() if _probe.fail then error('nested-error') end end)
)lua";
 std::string source=script;source.replace(source.find("MODE"),4,argv[1]);
 if(LuaRuntime::InitializeFromBuffer(source.data(),source.size(),"@nested.lua")!=LuaRuntime::LuaInitResult::Success)return 1;
 InstallReentryProbe();
 if(!DispatchOuterProbe())return 2;
 if(isaac::runtime::EngineGuardDispatchActive().load()!=0)return 7;
 if(LuaRuntime::TakeCallbackError())return 3;
 if(!DispatchOuterProbe())return 4;
 if(isaac::runtime::EngineGuardDispatchActive().load()!=0)return 8;
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
   for mode in range(5):
    with self.subTest(mode=mode):
     r=subprocess.run([str(binary),str(mode)],capture_output=True,text=True)
     print(r.stdout,end='')
     self.assertEqual(r.returncode,0,r.stdout+r.stderr)
if __name__=='__main__':unittest.main()
