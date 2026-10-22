"""完整PC bootstrap所有回调均首个非nil短路，整数也取首个返回。"""
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
HARNESS=r'''
#include "application/callback/callback_dispatcher.hpp"
#include <cstdio>
using namespace isaac::runtime;
struct Invoker : ICallbackInvoker {
 int count=0;
 int result=0;
 Status Invoke(const CallbackDescriptor&) noexcept override {return Status::Ok();}
 Status InvokeCollecting(const CallbackDescriptor&,CallbackReturn* out) noexcept override {
  ++count;out->called=true;
  if(count==1){out->nonNil=result!=0;out->truthy=result==2;}
  else {out->nonNil=true;out->truthy=result!=2;}
  return Status::Ok();
 }
};
int main() {
 for(CallbackId id: {kCallbackEntityTakeDmg,kCallbackInputAction,kCallbackPrePickupCollision,kCallbackPreFamiliarCollision,kCallbackPreNpcCollision,kCallbackPrePlayerCollision,kCallbackPreTearCollision,kCallbackPreProjectileCollision,kCallbackPreKnifeCollision,kCallbackPreBombCollision}) {
  for(int value: {0,1,2}) {
   CallbackRegistry registry;
   for(int i=1;i<=3;++i){CallbackDescriptor d{};d.id=id;d.owner=ModHandle{static_cast<std::uint16_t>(i),1};d.affinity=ThreadAffinity::Any;d.luaReference=i;d.modReference=10+i;if(!registry.Register(d).ok())return 1;}
   Invoker invoker;invoker.result=value;
   CallbackDispatcher dispatcher(registry,invoker);
   const auto outcome=dispatcher.DispatchModifying(id,ThreadAffinity::Any,CallbackRegistry::kNoCallbackFilter);
   // 完整PC main.lua：nil继续，false/true均短路，Input同规则。
   int expected=value==0?2:1;
   if(invoker.count!=expected || outcome.invoked!=static_cast<unsigned>(expected)) {std::printf("id=%u value=%d count=%d expected=%d\n",id,value,invoker.count,expected);return 2;}
   if(value!=0 && outcome.anyTruthy!=(value==2))return 3;
  }
 }
 return 0;
}
'''
class CallbackReturnPolicyTests(unittest.TestCase):
 def test_damage_collision_and_input_short_circuit(self):
  with tempfile.TemporaryDirectory() as td:
   p=Path(td)/'probe.cpp';p.write_text(HARNESS);b=Path(td)/'probe';src=ROOT/'runtime/src'
   result=subprocess.run(['c++','-std=c++20','-Wall','-Wextra','-Werror','-I',str(src),str(p),str(src/'application/callback/callback_dispatcher.cpp'),str(src/'application/callback/callback_registry.cpp'),'-o',str(b)],text=True,capture_output=True)
   self.assertEqual(result.returncode,0,result.stdout+result.stderr)
   result=subprocess.run([str(b)],text=True,capture_output=True)
   self.assertEqual(result.returncode,0,result.stdout+result.stderr)
 def test_item_pool_returns_use_the_first_non_nil_integer(self):
  driver=HARNESS[:HARNESS.index('int main()')]
  driver=driver.replace('int result=0;', 'int result=0;')
  start=driver.index('  if(count==1)')
  end=driver.index('  return Status::Ok();',start)
  driver=driver[:start]+"  if(count!=2){out->nonNil=true;out->hasInteger=true;out->integer=count*100;}\n"+driver[end:]
  driver+=r'''int main(){
   for(CallbackId id:{20,62,63,64,65,66}){
    CallbackRegistry registry;
    for(int i=1;i<=3;++i){CallbackDescriptor d{};d.id=id;d.owner=ModHandle{static_cast<std::uint16_t>(i),1};d.affinity=ThreadAffinity::Any;d.luaReference=i;d.modReference=10+i;if(!registry.Register(d).ok())return 1;}
    Invoker invoker;CallbackDispatcher dispatcher(registry,invoker);
    const auto result=dispatcher.DispatchModifying(id,ThreadAffinity::Any,CallbackRegistry::kNoCallbackFilter);
    if(!result.hasInteger||result.integer!=100||invoker.count!=1){std::printf("id=%u integer=%lld\n",id,static_cast<long long>(result.integer));return 2;}
   }
  }'''
  with tempfile.TemporaryDirectory() as td:
   p=Path(td)/'probe.cpp';p.write_text(driver);b=Path(td)/'probe';src=ROOT/'runtime/src'
   r=subprocess.run(['c++','-std=c++20','-Wall','-Wextra','-Werror','-I',str(src),str(p),str(src/'application/callback/callback_dispatcher.cpp'),str(src/'application/callback/callback_registry.cpp'),'-o',str(b)],capture_output=True,text=True)
   self.assertEqual(r.returncode,0,r.stderr)
   r=subprocess.run([str(b)],capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
if __name__=='__main__':unittest.main()
