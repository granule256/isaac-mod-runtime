"""Nested native death dispatch must retain its caller's permission cache."""
import subprocess
import tempfile
import unittest
from pathlib import Path
from .test_input_dispatch_scope import definition

ROOT = Path(__file__).resolve().parents[2]


class DeathDispatchScopeTests(unittest.TestCase):
    def test_real_death_dispatch_preserves_nested_and_cleans_owned_windows(self):
        text = (ROOT/'runtime/source/lua_runtime.cpp').read_text()
        scope = definition(text, 'class ManagedEngineDispatchScope final') + ';'
        body = definition(text, 'void DispatchPostEntityKill(') + '\n' + definition(
            text, 'void DispatchPostNpcDeath(')
        source = r'''
#include <cassert>
#include <cstdint>
#include <cstring>
#include "infrastructure/memory/engine_memory_guard.hpp"
static bool ready=true,enabled=true,world=true,failed=false,reenter=false;
static unsigned calls{},failures{};
struct LuaCallbackInvoker {
 static LuaCallbackInvoker ForEntity(std::uintptr_t p){assert(p==0x1234);return {};}
};
namespace LuaRuntime {
void DispatchPostEntityKill(std::uintptr_t,std::int32_t);
void DispatchPostNpcDeath(std::uintptr_t,std::int32_t);
}
namespace isaac::runtime {
bool BuiltinCallbackEnabled(unsigned){return enabled;}
bool ShouldDispatchManagedCallbacks(){return world;}
constexpr unsigned kCallbackPostEntityKill=68,kCallbackPostNpcDeath=29;
enum class ThreadAffinity{Any};
struct DispatchReport{unsigned invoked{},failed{};};
struct CallbackDispatcher {
 CallbackDispatcher(int,LuaCallbackInvoker&){}
 DispatchReport DispatchFiltered(unsigned id,ThreadAffinity,std::int64_t filter){
  assert(EngineGuardDispatchActive().load()==1&&filter==20);++calls;
  EngineGuardRegionCache().Insert(0x5000,0x6000);
  EngineGuardRememberWritable(0x7000,0x8000);
  if(reenter){reenter=false;
   if(id==68)LuaRuntime::DispatchPostNpcDeath(0x1234,20);
   else LuaRuntime::DispatchPostEntityKill(0x1234,20);
  }
  // The real Lua invoker catches errors at its existing pcall and returns a
  // failed report, rather than unwinding through these native functions.
  if(failed){++failures;return {0,1};}return {1,0};
 }
};
}
namespace LuaRuntime {
static void* g_LuaState=reinterpret_cast<void*>(1);
static int g_CallbackRegistry{};static bool g_InPostEntityKillDispatch=false;
bool IsReady(){return ready;}
SCOPE
BODY
}
int main(int argc,char**argv){
 assert(argc==2);using namespace isaac::runtime;
 const auto dispatch=std::strcmp(argv[1],"kill")==0
  ? LuaRuntime::DispatchPostEntityKill:LuaRuntime::DispatchPostNpcDeath;
 EngineGuardEnterDispatch();EngineGuardRegionCache().Insert(0x1000,0x2000);
 EngineGuardRememberWritable(0x3000,0x4000);
 const auto epoch=EngineGuardDispatchEpoch().load();
 const auto preserved=[&]{
  assert(EngineGuardDispatchActive().load()==1&&"nested death closed its caller's window");
  assert(EngineGuardDispatchEpoch().load()==epoch&&"nested death replaced its caller's epoch");
  assert(EngineGuardLookupCached(0x1100,4)&&EngineGuardLookupWritable(0x3100,4));
 };
 dispatch(0x1234,20);assert(calls==1);preserved();
 failed=true;dispatch(0x1234,20);assert(calls==2&&failures==1);preserved();failed=false;
 ready=false;dispatch(0x1234,20);assert(calls==2);preserved();ready=true;
 enabled=false;dispatch(0x1234,20);assert(calls==2);preserved();enabled=true;
 world=false;dispatch(0x1234,20);assert(calls==2);preserved();world=true;
 LuaRuntime::g_LuaState=nullptr;dispatch(0x1234,20);assert(calls==2);preserved();
 LuaRuntime::g_LuaState=reinterpret_cast<void*>(1);
 LuaRuntime::g_InPostEntityKillDispatch=true;LuaRuntime::DispatchPostEntityKill(0x1234,20);
 assert(calls==2);preserved();LuaRuntime::g_InPostEntityKillDispatch=false;
 reenter=true;dispatch(0x1234,20);assert(calls==4);preserved();
 EngineGuardLeaveDispatch();
 const auto closed=[&]{
  assert(EngineGuardDispatchActive().load()==0);
  assert(!EngineGuardRegionCache().Covers(0x1100,4));
  assert(!EngineGuardWritableRegionCache().Covers(0x3100,4));
  assert(!EngineGuardRegionCache().Covers(0x5100,4));
  assert(!EngineGuardWritableRegionCache().Covers(0x7100,4));
  assert(!LuaRuntime::g_InPostEntityKillDispatch);
 };
 dispatch(0x1234,20);assert(calls==5);closed();
 failed=true;dispatch(0x1234,20);assert(calls==6&&failures==2);closed();failed=false;
 const auto beforeEarly=EngineGuardDispatchEpoch().load();
 world=false;dispatch(0x1234,20);assert(calls==6);closed();world=true;
 enabled=false;dispatch(0x1234,20);assert(calls==6);closed();enabled=true;
 assert(EngineGuardDispatchEpoch().load()==beforeEarly);
}
'''.replace('SCOPE', scope).replace('BODY', body)
        with tempfile.TemporaryDirectory(prefix='death-dispatch-scope-') as folder:
            path = Path(folder)
            (path/'test.cpp').write_text(source)
            build = subprocess.run(['c++','-std=c++20','-Wall','-Wextra','-Werror',
                                    '-I'+str(ROOT/'runtime/source'),'-I'+str(ROOT/'runtime/src'),
                                    str(path/'test.cpp'),'-o',str(path/'test')],capture_output=True,text=True)
            self.assertEqual(build.returncode,0,build.stdout+build.stderr)
            for mode in ('kill','npc'):
                with self.subTest(mode=mode):
                    run = subprocess.run([str(path/'test'),mode],capture_output=True,text=True)
                    self.assertEqual(run.returncode,0,run.stdout+run.stderr)
