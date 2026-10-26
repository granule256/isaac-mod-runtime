"""真实原生事件适配器：三例外、线程/层隔离、调用重放与LR。"""
from pathlib import Path
import subprocess,tempfile,unittest
ROOT=Path(__file__).resolve().parents[2]
STUB=r'''#pragma once
#include "domain/callback/use_item_result.hpp"
namespace LuaRuntime {
bool IsOnGameThread() noexcept;
void DispatchUseCard(std::uintptr_t,std::int32_t,std::int32_t);
std::uintptr_t EngineModuleBase();
isaac::runtime::UseItemCallbackResult DispatchUseItemAtNativeBoundary(std::uintptr_t,std::int32_t,std::int32_t,std::int32_t,std::int32_t,std::uint64_t,bool);
}
'''
SOURCE=r'''
#include "use_item_internal_hook.hpp"
#include "domain/callback/use_item_result.hpp"
#include "infrastructure/call/engine_call_access.hpp"
#include "infrastructure/relay/entry_relay_binding.hpp"
#include <cassert>
#include <cstring>
using namespace isaac::runtime;
bool gameThread=true;unsigned shakes{},replacements{},cardCalls{},cardPosts{};
std::uintptr_t hostCaller=0x100000+0x310824;
void OriginalCard(void* p,std::uint32_t card,std::uint32_t flags){assert(p==reinterpret_cast<void*>(0x100)&&card==48&&flags==384);++cardCalls;}
namespace isaac::runtime {std::uintptr_t EntryRelayFallbackEntry(HookId id)noexcept{assert(id==HookId::UseCard);return engine_call::AddressOfFunction(&OriginalCard);}}
namespace LuaRuntime {
bool IsOnGameThread()noexcept{return gameThread;}
std::uintptr_t EngineModuleBase(){return 0x100000;}
void DispatchUseCard(std::uintptr_t p,std::int32_t c,std::int32_t f){assert(p==0x100&&c==48&&f==384&&cardCalls==cardPosts+1);++cardPosts;}
UseItemCallbackResult DispatchUseItemAtNativeBoundary(std::uintptr_t,std::int32_t,std::int32_t,std::int32_t,std::int32_t,std::uint64_t,bool){return {};}
}

void Shake(std::uintptr_t game,std::int32_t n){assert(game==0xabc&&n==15);++shakes;}
void Replace(std::uintptr_t m,std::uintptr_t a,std::uintptr_t b){assert(m==0xabc&&a==0x100&&b==0x200);++replacements;}
CARD_WRAPPER
int main(){
 static_assert(sizeof(UseItemCallFrame)==40);
 auto& head=ActiveUseItemFrame();assert(!head);
 relay::InternalHookContext c{};for(unsigned i=0;i<31;++i)c.x[i]=1000+i;
 c.x[0]=0xabc;c.x[1]=15;c.x[27]=0x100;
 UseItemAnimationEventBinding shake{engine_call::AddressOfFunction(&Shake),0x300,UseItemAnimationEvent::TammyLaser};
 {UseItemCallScope s(head,0x100,38,0,0,0,true);auto before=c;
  assert(s.frame().animationAllowed);UseItemAnimationEventCallback(c,&shake);assert(!s.frame().animationAllowed&&shakes==1);
  before.x[30]=0x300;assert(!std::memcmp(&c,&before,sizeof(c)));}
 {UseItemCallScope s(head,0x100,38,0,0,0,true);gameThread=false;UseItemAnimationEventCallback(c,&shake);gameThread=true;assert(s.frame().animationAllowed&&shakes==2);}
 {UseItemCallScope s(head,0x101,38,0,0,0,true);UseItemAnimationEventCallback(c,&shake);assert(s.frame().animationAllowed);}
 {UseItemCallScope s(head,0x100,39,0,0,0,true);UseItemAnimationEventCallback(c,&shake);assert(s.frame().animationAllowed);}
 {UseItemCallScope s(head,0x100,38,0,0,0,true);s.frame().dispatched=true;UseItemAnimationEventCallback(c,&shake);assert(s.frame().animationAllowed);}
 c.x[1]=0x100;c.x[2]=0x200;c.x[20]=0x200;
 UseItemAnimationEventBinding flip{engine_call::AddressOfFunction(&Replace),0x400,UseItemAnimationEvent::FlipReplace};
 {UseItemCallScope s(head,0x100,711,0,0,0,true);auto before=c;UseItemAnimationEventCallback(c,&flip);assert(!s.frame().animationAllowed&&replacements==1);before.x[30]=0x400;assert(!std::memcmp(&c,&before,sizeof(c)));}
 {UseItemCallScope s(head,0x100,711,0,0,0,true);c.x[20]=0;UseItemAnimationEventCallback(c,&flip);assert(s.frame().animationAllowed&&replacements==2);}
 constexpr std::uintptr_t base=0x100000;
 {UseItemCallScope s(head,0x100,286,0,0,0,true);
  NoteUseItemCardAnimation(head,0x100,47,base+0x310824,base);assert(s.frame().animationAllowed);
  NoteUseItemCardAnimation(head,0x101,48,base+0x310824,base);assert(s.frame().animationAllowed);
  NoteUseItemCardAnimation(head,0x100,48,base+0x310828,base);assert(s.frame().animationAllowed);
  NoteUseItemCardAnimation(head,0x100,48,0x310824,0);assert(s.frame().animationAllowed);
  {UseItemCallScope inner(head,0x100,1,0,0,0,true);NoteUseItemCardAnimation(head,0x100,48,base+0x310824,base);assert(inner.frame().animationAllowed&&s.frame().animationAllowed);}
  NoteUseItemCardAnimation(head,0x100,48,base+0x310824,base);assert(!s.frame().animationAllowed);}
 {UseItemCallScope s(head,0x100,286,0,0,0,true);EntryRelayUseCardCallback(reinterpret_cast<void*>(0x100),48,384);assert(!s.frame().animationAllowed&&cardCalls==1&&cardPosts==1);}
 {UseItemCallScope s(head,0x100,286,0,0,0,true);hostCaller+=4;EntryRelayUseCardCallback(reinterpret_cast<void*>(0x100),48,384);assert(s.frame().animationAllowed&&cardCalls==2&&cardPosts==2);}
 {UseItemCallScope s(head,0x100,286,0,0,0,true);hostCaller-=4;gameThread=false;EntryRelayUseCardCallback(reinterpret_cast<void*>(0x100),48,384);gameThread=true;assert(s.frame().animationAllowed&&cardCalls==3&&cardPosts==3);}
 assert(!head);
}
'''
class UseItemAnimationEventTests(unittest.TestCase):
 def test_actual_native_event_adapters(self):
  with tempfile.TemporaryDirectory(prefix='use-animation-events-')as tmp:
   p=Path(tmp);(p/'lua_runtime.hpp').write_text(STUB);hook=(ROOT/'runtime/source/hook_manager.cpp').read_text()
   start=hook.index('extern "C" void EntryRelayUseCardCallback(');end=hook.index('extern "C" void EntryRelayUsePillCallback',start)
   wrapper=hook[start:end];boundary='__builtin_extract_return_addr(__builtin_return_address(0))'
   self.assertEqual(wrapper.count(boundary),1)
   # 宿主无ARM原生调用点；仅替换返回地址观测值，保留完整入口/原生调用/派发。
   wrapper=wrapper.replace(boundary,'reinterpret_cast<void*>(hostCaller)')
   (p/'main.cpp').write_text(SOURCE.replace('CARD_WRAPPER',wrapper))
   r=subprocess.run(['c++','-std=c++20','-Wall','-Wextra','-Werror','-I',str(p),'-I',str(ROOT/'runtime/source'),'-I',str(ROOT/'runtime/src'),str(p/'main.cpp'),str(ROOT/'runtime/src/interfaces/lua/use_item_native_boundary.cpp'),'-o',str(p/'test')],capture_output=True,text=True)
   self.assertEqual(r.returncode,0,r.stdout+r.stderr)
   r=subprocess.run([str(p/'test')],capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
