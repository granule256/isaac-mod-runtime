"""真实生产输入派发的Entity来源与三条短入口回放。"""
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]

def function(source,signature):
    start=source.index(signature);brace=source.index('{',start);end=brace+1;depth=1
    while depth:
        depth+=(source[end]=='{')-(source[end]=='}');end+=1
    return source[start:end]

class InputEntityContextTests(unittest.TestCase):
    def compile_run(self,source):
        with tempfile.TemporaryDirectory(prefix='input-entity-') as tmp:
            p=Path(tmp);(p/'main.cpp').write_text(source)
            r=subprocess.run(['c++','-std=c++20','-Wall','-Wextra','-Werror','-I'+str(ROOT/'runtime/source'),'-I'+str(ROOT/'runtime/src'),str(p/'main.cpp'),'-o',str(p/'probe')],capture_output=True,text=True)
            self.assertEqual(r.returncode,0,r.stdout+r.stderr)
            r=subprocess.run([str(p/'probe')],capture_output=True,text=True)
            self.assertEqual(r.returncode,0,r.stdout+r.stderr)

    def test_dispatch_keeps_actual_nil_player_and_other_entity(self):
        body=function((ROOT/'runtime/source/lua_runtime.cpp').read_text(),'InputActionOutcome DispatchInputAction(')
        self.compile_run(r'''
#include <cassert>
#include <cstdint>
#include <type_traits>
#include "interfaces/lua/input_action_map.hpp"
struct Args {std::uintptr_t entity{};bool nil{};std::int64_t values[2]{};int count{};
 void AddEntity(std::uintptr_t e){entity=e;} void AddNil(){nil=true;}
 void AddInteger(std::int64_t n){values[count++]=n;}};
struct LuaCallbackInvoker {Args arguments;LuaCallbackInvoker(int,bool,bool){}};
static Args received{};static int calls{},resolvedPlayers{};static std::int64_t lastFilter{};
static bool ready=true,enabled=true;
namespace isaac::runtime {
 bool ShouldDispatchManagedCallbacks(){return ready;} bool BuiltinCallbackEnabled(unsigned){return enabled;}
 constexpr unsigned kCallbackInputAction=13;enum class ThreadAffinity{Any};
 void EngineGuardEnterDispatch(){} void EngineGuardLeaveDispatch(){}
 [[maybe_unused]] std::uintptr_t ResolveEnginePlayerAt(int){++resolvedPlayers;return 0x11110000;}
 struct CallbackDispatchOutcome {bool anyNonNil{},hasNumber{},hasInteger{},anyTruthy{};double number{};std::int64_t integer{};};
 struct CallbackDispatcher {LuaCallbackInvoker&invoker;CallbackDispatcher(int,LuaCallbackInvoker&i):invoker(i){}
 CallbackDispatchOutcome DispatchModifying(unsigned id,ThreadAffinity,std::int64_t filter){assert(id==13);received=invoker.arguments;lastFilter=filter;++calls;return {};}};
}
namespace LuaRuntime {
static void*g_LuaState=reinterpret_cast<void*>(1);static int g_CallbackRegistry{};
bool IsReady(){return ready;}constexpr int kInputHookGetActionValue=2;
struct InputActionOutcome {bool overridden{},boolean{};float value{};};
BODY
}
template<class F>auto dispatch(F f,std::uintptr_t entity){
 if constexpr(std::is_invocable_v<F,unsigned,unsigned,int,std::uintptr_t>)return f(17,33,0,entity);
 else return f(17,33,0);
}
int main(){
 for(auto e:{std::uintptr_t{0},std::uintptr_t{0x22220000},std::uintptr_t{0x33330000}}){
  const auto answer=dispatch(&LuaRuntime::DispatchInputAction,e);
  assert(!answer.overridden);assert(received.entity==e && received.nil==(e==0));
  assert(received.count==2 && received.values[0]==0 && received.values[1]==20 && lastFilter==0);
 }
 assert(resolvedPlayers==0 && calls==3);
 enabled=false;dispatch(&LuaRuntime::DispatchInputAction,0);assert(calls==3);
 ready=false;dispatch(&LuaRuntime::DispatchInputAction,0);assert(calls==3);
}
'''.replace('#include <cassert>','#include <cassert>\n#include <initializer_list>').replace('BODY',body))

    def test_real_input_glue_relocates_without_changing_slot_size(self):
        self.compile_run(r'''
#include <cassert>
#include <cstdint>
#include <cstring>
#include <limits>
#include "runtime_constants.hpp"
#include "relay/entry_relay.hpp"
using namespace isaac::runtime;using namespace isaac::runtime::relay;
std::uint64_t quad(const std::uint8_t*p){std::uint64_t v{};for(unsigned i=0;i<8;++i)v|=std::uint64_t(p[i])<<(i*8);return v;}
std::int64_t sign(std::uint32_t n,unsigned bits){return n&(1u<<(bits-1))?std::int64_t(n)-(1LL<<bits):n;}
int main(){
 static_assert(kSlotBytes==0x40 && kSlotStride==0x40 && kArenaBytes==0x1000);
 const std::uint8_t* entries[]={kManagerIsActionPressedExpectedBytes.data(),kManagerIsActionTriggeredExpectedBytes.data(),kManagerGetActionValueExpectedBytes.data()};
 const std::uintptr_t offsets[]={kManagerIsActionPressedOffset,kManagerIsActionTriggeredOffset,kManagerGetActionValueOffset};
 const std::uintptr_t tails[]={0x678990,0x671510,0x67cb80};
 for(unsigned j=0;j<3;++j){
  const std::uintptr_t base=0x187ca3c000ULL,slot=0x5f02781000ULL,target=base+offsets[j];
  assert(EvaluateEntryRelayPreconditions(target,slot,entries[j],entries[j],0)==EntryRelayFailure::None);
  std::uint8_t image[kSlotBytes]{};BuildSlotImage(image,target,entries[j],0x5f02800000ULL);
  assert(quad(image+kSlotReservedOffset)==base+0xaac768);
  assert(quad(image+kSlotFallbackTargetOffset)==base+tails[j]);
  assert(quad(image+kSlotCallbackOffset)==0x5f02800000ULL);
  // 独立解码回放指令。两次更换全局Manager值，回放必须现读而不是固定旧指针。
  for(std::uint64_t manager:{0x77770000ULL,0x88880000ULL}){
   std::uint64_t regs[32]{};regs[1]=17;regs[2]=33;regs[3]=0x22220000;regs[30]=0x12345678;
   std::uintptr_t pc=slot+kSlotFallbackOffset;
   auto load=[&](std::uint64_t a){if(a==base+0xaac768)return manager;assert(a>=slot&&a+8<=slot+kSlotBytes);return quad(image+(a-slot));};
   for(unsigned step=0;step<5;++step){
    const auto w=LoadLittleEndianWord(image,(pc-slot)/4);const auto rt=w&31u;
    if((w&0xff000000u)==0x58000000u)regs[rt]=load(pc+sign((w>>5)&0x7ffffu,19)*4);
    else if((w&0xffc00000u)==0xf9400000u)regs[rt]=load(regs[(w>>5)&31u]+((w>>10)&4095u)*8);
    else if(w==0xaa1f03e3u)regs[3]=0;
    else {assert((w&0xfffffc1fu)==0xd61f0000u);assert(regs[(w>>5)&31u]==base+tails[j]);}
    pc+=4;
   }
   assert(regs[0]==manager&&regs[1]==17&&regs[2]==33&&regs[3]==0&&regs[30]==0x12345678);
  }
  std::uint8_t bad[16];std::memcpy(bad,entries[j],16);bad[8]^=1;
  assert(EvaluateEntryRelayPreconditions(target,slot,bad,bad,0)==EntryRelayFailure::PcRelativeInstruction);
  assert(EvaluateEntryRelayPreconditions(UINTPTR_MAX & ~std::uintptr_t{4095},slot,entries[j],entries[j],0)==EntryRelayFailure::PcRelativeInstruction);
 }
}
'''.replace('#include <cassert>','#include <cassert>\n#include <initializer_list>'))

    def test_relay_forwards_entity_native_return_and_raw_bypass(self):
        s=(ROOT/'runtime/source/hook_manager.cpp').read_text()
        a=s.index('#define ISAAC_RUNTIME_INPUT_ACTION_RELAY(')
        b=s.index('#undef ISAAC_RUNTIME_INPUT_ACTION_RELAY',a)
        self.compile_run(r'''
#include <cassert>
#include <cstdint>
#include <type_traits>
#include "domain/runtime/hook_catalog.hpp"
static bool raw{},replace{};static int nativeCalls{},dispatchCalls{};
static void*const entity=reinterpret_cast<void*>(0x22220000);
bool NativeBool(void*m,unsigned a,unsigned c,void*e){assert(m==reinterpret_cast<void*>(1)&&a==17&&c==33&&e==entity);++nativeCalls;return true;}
float NativeFloat(void*m,unsigned a,unsigned c,void*e){NativeBool(m,a,c,e);return .625F;}
namespace isaac::runtime {
template<class F>F Original(HookId){if constexpr(std::is_same_v<F,float(*)(void*,unsigned,unsigned,void*)>)return NativeFloat;else return NativeBool;}
}
namespace LuaRuntime {
struct InputActionOutcome{bool overridden{},boolean{};float value{};};
bool IsRawEngineInputQuery(){return raw;}
InputActionOutcome DispatchInputAction(unsigned a,unsigned c,int h,std::uintptr_t e){assert(a==17&&c==33&&h>=0&&h<=2&&e==reinterpret_cast<std::uintptr_t>(entity));++dispatchCalls;return {replace,false,.75F};}
}
constexpr int kInputHookIsActionPressed=0,kInputHookIsActionTriggered=1,kInputHookGetActionValue=2;
BODY
int main(){
 using Bool=bool(*)(void*,unsigned,unsigned,void*);
 Bool queries[]={EntryRelayManagerIsActionPressedCallback,EntryRelayManagerIsActionTriggeredCallback};
 for(auto query:queries){
  nativeCalls=dispatchCalls=0;raw=false;replace=false;assert(query(reinterpret_cast<void*>(1),17,33,entity));assert(nativeCalls==1&&dispatchCalls==1);
  raw=true;replace=true;assert(query(reinterpret_cast<void*>(1),17,33,entity));assert(nativeCalls==2&&dispatchCalls==1);
  raw=false;assert(!query(reinterpret_cast<void*>(1),17,33,entity));assert(nativeCalls==2&&dispatchCalls==2);
 }
 nativeCalls=dispatchCalls=0;raw=false;replace=false;
 assert(EntryRelayManagerGetActionValueCallback(reinterpret_cast<void*>(1),17,33,entity)==.625F);
 assert(nativeCalls==1&&dispatchCalls==1);replace=true;
 assert(EntryRelayManagerGetActionValueCallback(reinterpret_cast<void*>(1),17,33,entity)==.75F);
 assert(nativeCalls==1&&dispatchCalls==2);raw=true;
 assert(EntryRelayManagerGetActionValueCallback(reinterpret_cast<void*>(1),17,33,entity)==.625F);
 assert(nativeCalls==2&&dispatchCalls==2);
}
'''.replace('BODY',s[a:b]))

    def test_binding_recheck_only_accepts_our_matching_installed_hook(self):
        s=(ROOT/'runtime/source/hook_manager.cpp').read_text()
        body=function(s,'bool IsInstalledManagerInputEntry(')
        self.compile_run(r'''
#include <cassert>
#include <cstdint>
#include <cstring>
#include "domain/runtime/hook_catalog.hpp"
#include "relay/entry_relay.hpp"
static bool installed=false;
namespace isaac::runtime {
bool EntryRelayInstalled(HookId id){return installed&&id==HookId::ManagerIsActionPressed;}
std::uintptr_t EntryRelayFallbackEntry(HookId){return 0x5f02781020ULL;}
}
BODY
int main(){
 using isaac::runtime::HookId;
 std::uint8_t entry[16]{};isaac::runtime::relay::BuildEntryPatch(entry,0x5f02781000ULL);
 assert(!IsInstalledManagerInputEntry(HookId::ManagerIsActionPressed,0x18003f9b6cULL,entry));
 installed=true;assert(IsInstalledManagerInputEntry(HookId::ManagerIsActionPressed,0x18003f9b6cULL,entry));
 assert(!IsInstalledManagerInputEntry(HookId::ManagerIsActionTriggered,0x18003f9b7cULL,entry));
 entry[8]^=1;assert(!IsInstalledManagerInputEntry(HookId::ManagerIsActionPressed,0x18003f9b6cULL,entry));
}
'''.replace('BODY',body))

if __name__=='__main__':unittest.main()
