"""直接编译生产中继体，核对三态原生返回、过滤字段、实参转发与NPC渲染先后顺序。"""
import re
import subprocess
import tempfile
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
FAMILIES=['Pickup','Familiar','Npc','Player','Tear','Projectile','Knife','Bomb']
def function(text,name):
 a=text.index('extern "C"',text.index(name)-50)
 b=text.index('{',a);depth=1;i=b+1
 while depth:
  depth += (text[i]=='{')-(text[i]=='}');i+=1
 return text[a:i]
class CollisionRelayBehaviorTests(unittest.TestCase):
 def test_adapter_declarations_match_callback_return_types(self):
  definitions=(ROOT/'runtime/source/hook_manager.cpp').read_text()
  declarations=(ROOT/'runtime/src/infrastructure/relay/entry_relay_hook_adapter.cpp').read_text()
  parse=lambda source,ending:dict((name,ret.strip()) for ret,name in re.findall(
   r'extern "C"\s+([\w:]+)\s+(EntryRelay\w+Callback)\([^;{}]*\)\s*'+ending,source))
  actual=parse(definitions,r'\{');declared=parse(declarations,';')
  for name,ret in declared.items():
   if name in actual:self.assertEqual(ret,actual[name],name)
 def test_actual_production_relays_preserve_abi_and_tristate(self):
  cpp=(ROOT/'runtime/source/hook_manager.cpp').read_text()
  funcs='\n'.join(function(cpp,'EntryRelay'+f+'CollisionCallback') for f in FAMILIES)+ '\n'+function(cpp,'EntryRelayNpcRenderCallback')
  driver=r'''
#include <cassert>
#include <cstdint>
#include <type_traits>
#include "domain/runtime/hook_catalog.hpp"
#include "domain/callback/callback_descriptor.hpp"
#include "infrastructure/memory/engine_field_access.hpp"
static int calls=0,order=0,lastFilter=0;
static unsigned lastId=0;
static void* expectedEntity=reinterpret_cast<void*>(0x1000);
static void* expectedCollider=reinterpret_cast<void*>(0x2000);
static const void* expectedOffset=reinterpret_cast<void*>(0x3000);
static std::uint64_t fakeCollision(void* e,void* c,std::uint32_t low) {
 assert(e==expectedEntity&&c==expectedCollider&&low==1);++calls;return 0x123456789abcdef1ULL;
}
static void fakeRender(void* e,const void* offset){assert(e==expectedEntity&&offset==expectedOffset);order=1;}
namespace isaac::runtime {
 template<class Fn> Fn Original(HookId) {
  if constexpr(std::is_same_v<Fn,void(*)(void*,const void*)>)return fakeRender;
  else return fakeCollision;
 }
 bool ReadEntityIdentity(std::uintptr_t e,std::uint32_t* type,std::uint32_t* variant) {
  assert(e==0x1000);*type=123;*variant=456;return true;
 }
 bool ReadEntitySubType(std::uintptr_t e,std::uint32_t* subtype){assert(e==0x1000);*subtype=789;return true;}
}
namespace LuaRuntime {
 enum class CollisionOverride : std::int8_t {Continue=-1,Collide=0,Ignore=1};
 static CollisionOverride decision=CollisionOverride::Continue;
 CollisionOverride DispatchPreEntityCollision(std::uint32_t id,std::uintptr_t e,std::uintptr_t c,bool low,std::int32_t filter){
  assert(e==0x1000&&c==0x2000&&low);lastId=id;lastFilter=filter;return decision;
 }
 void DispatchPostNpcRender(std::uintptr_t e,const void* offset){assert(e==0x1000&&offset==expectedOffset&&order==1);order=2;}
}
FUNCTIONS
int main(){
 using Fn=std::uint64_t(*)(void*,void*,std::uint32_t);
 Fn functions[]={FUNCTION_ARRAY};
 unsigned ids[]={38,26,30,33,42,46,53,60};
 int filters[]={456,456,123,456,456,456,789,456};
 for(unsigned i=0;i<8;++i){
  for(auto d:{LuaRuntime::CollisionOverride::Continue,LuaRuntime::CollisionOverride::Collide,LuaRuntime::CollisionOverride::Ignore}){
   calls=0;LuaRuntime::decision=d;
   auto answer=functions[i](expectedEntity,expectedCollider,1);
   assert(lastId==ids[i]&&lastFilter==filters[i]);
   if(d==LuaRuntime::CollisionOverride::Continue)assert(calls==1&&answer==0x123456789abcdef1ULL);
   else assert(calls==0&&answer==(d==LuaRuntime::CollisionOverride::Ignore?1:0));
  }
 }
 EntryRelayNpcRenderCallback(expectedEntity,expectedOffset);assert(order==2);
}
'''.replace('FUNCTIONS',funcs).replace('FUNCTION_ARRAY',','.join('EntryRelay'+f+'CollisionCallback' for f in FAMILIES))
  driver=driver.replace('#include <type_traits>','#include <type_traits>\n#include <initializer_list>')
  with tempfile.TemporaryDirectory() as td:
   source,binary=Path(td)/'main.cpp',Path(td)/'probe';source.write_text(driver)
   r=subprocess.run(['c++','-std=c++20','-Wall','-Wextra','-Werror','-I',str(ROOT/'runtime/src'),str(source),'-o',str(binary)],capture_output=True,text=True)
   self.assertEqual(r.returncode,0,r.stderr)
   r=subprocess.run([str(binary)],capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stderr)
if __name__=='__main__':unittest.main()
