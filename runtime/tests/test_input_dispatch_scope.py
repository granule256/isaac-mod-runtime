"""Native input reentry must preserve its caller's guarded dispatch window."""
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def definition(text, signature):
    start = text.index(signature)
    end = text.index('{', start) + 1
    depth = 1
    while depth:
        depth += (text[end] == '{') - (text[end] == '}')
        end += 1
    return text[start:end]


class InputDispatchScopeTests(unittest.TestCase):
    def test_real_dispatch_preserves_nested_cache_and_closes_owned_window(self):
        text = (ROOT/'runtime/source/lua_runtime.cpp').read_text()
        scope = definition(text, 'class ManagedEngineDispatchScope final') + ';'
        body = definition(text, 'InputActionOutcome DispatchInputAction(') + '\n' + definition(
            text, 'InputActionOutcome DispatchLogicalInputAction(')
        source = r'''
#include <atomic>
#include <cassert>
#include <cstdint>
#include "infrastructure/memory/engine_memory_guard.hpp"
#include "interfaces/lua/input_action_map.hpp"
static bool ready=true,enabled=true,world=true,reenter=false;
static unsigned calls{},worldReads{};
static unsigned expectedAction=4;static bool modifying=false,truth=false;
static std::int64_t lastArgument{};
struct Arguments {void AddEntity(std::uintptr_t){} void AddNil(){} void AddInteger(std::int64_t v){lastArgument=v;}};
struct LuaCallbackInvoker {Arguments arguments;LuaCallbackInvoker(int,bool,bool){}};
namespace LuaRuntime {
struct InputActionOutcome{bool overridden{},boolean{};float value{};};
InputActionOutcome DispatchInputAction(unsigned,unsigned,int,std::uintptr_t);
InputActionOutcome DispatchLogicalInputAction(unsigned,int,std::uintptr_t);
}
namespace isaac::runtime {
bool BuiltinCallbackEnabled(unsigned){return enabled;}
bool ShouldDispatchManagedCallbacks(){++worldReads;return world;}
constexpr unsigned kCallbackInputAction=13;enum class ThreadAffinity{Any};
struct CallbackDispatchOutcome{bool anyNonNil{},hasNumber{},hasInteger{},anyTruthy{};double number{};std::int64_t integer{};};
struct CallbackDispatcher {
 CallbackDispatcher(int,LuaCallbackInvoker&){}
 CallbackDispatchOutcome DispatchModifying(unsigned,ThreadAffinity,std::int64_t){
  ++calls;assert(EngineGuardDispatchActive().load()==1);assert(lastArgument==expectedAction);
  if(reenter){reenter=false;const auto before=worldReads;
   LuaRuntime::DispatchInputAction(4,0,0,0);assert(worldReads==before);}
  return {modifying,false,false,truth,0,0};
 }
};
}
namespace LuaRuntime {
static void* g_LuaState=reinterpret_cast<void*>(1);static int g_CallbackRegistry{};
bool IsReady(){return ready;}constexpr int kInputHookGetActionValue=2;
SCOPE
BODY
}
int main(){
 using namespace isaac::runtime;
 EngineGuardEnterDispatch();EngineGuardRegionCache().Insert(0x1000,0x2000);
 EngineGuardRememberWritable(0x3000,0x4000);
 const auto epoch=EngineGuardDispatchEpoch().load();
 LuaRuntime::DispatchInputAction(4,0,0,0);
 assert(calls==1 && EngineGuardDispatchActive().load()==1);
 assert(EngineGuardDispatchEpoch().load()==epoch);
 assert(EngineGuardLookupCached(0x1100,4) && EngineGuardLookupWritable(0x3100,4));
 reenter=true;LuaRuntime::DispatchInputAction(4,0,0,0);assert(calls==2);
 assert(EngineGuardDispatchActive().load()==1);
 EngineGuardLeaveDispatch();
 LuaRuntime::DispatchInputAction(4,0,0,0);
 assert(calls==3 && EngineGuardDispatchActive().load()==0);
 assert(!EngineGuardLookupCached(0x1100,4));
 world=false;LuaRuntime::DispatchInputAction(4,0,0,0);
 assert(calls==3 && EngineGuardDispatchActive().load()==0);
 enabled=false;const auto reads=worldReads;LuaRuntime::DispatchInputAction(4,0,0,0);
 assert(worldReads==reads && EngineGuardDispatchActive().load()==0);
 enabled=true;world=true;expectedAction=20;LuaRuntime::DispatchInputAction(17,0,0,0);
 expectedAction=18;modifying=true;
 const auto blocked=LuaRuntime::DispatchLogicalInputAction(18,0,0);
 assert(blocked.overridden&&!blocked.boolean);
 truth=true;const auto forced=LuaRuntime::DispatchLogicalInputAction(18,0,0);
 assert(forced.overridden&&forced.boolean);
}
'''.replace('SCOPE', scope).replace('BODY', body)
        with tempfile.TemporaryDirectory(prefix='input-dispatch-scope-') as folder:
            path=Path(folder);(path/'test.cpp').write_text(source)
            result=subprocess.run(['c++','-std=c++20','-Wall','-Wextra','-Werror',
                '-I'+str(ROOT/'runtime/source'),'-I'+str(ROOT/'runtime/src'),str(path/'test.cpp'),
                '-o',str(path/'test')],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            result=subprocess.run([str(path/'test')],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
