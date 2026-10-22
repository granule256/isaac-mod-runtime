"""66 RNG userdata分配失败在保护内退出，恢复作用域并允许下一次正常派发。"""
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from . import test_support

ROOT=Path(__file__).resolve().parents[2]
SOURCE=ROOT/'runtime/source'
BRIDGE=r'''
#include "card_hook.hpp"
namespace LuaRuntime {
struct RejectCardAllocation {lua_Alloc allocator;void* context;};
void* NoCardGrowth(void* context,void* block,size_t oldSize,size_t newSize){
 auto* a=static_cast<RejectCardAllocation*>(context);
 return newSize>oldSize?nullptr:a->allocator(a->context,block,oldSize,newSize);
}
static unsigned destroyed=0;
static std::uint32_t OriginalCard(const void*,std::uint32_t,bool,bool,bool){return 41;}
static void ConstructCard(void* p,std::uint32_t seed,std::uint32_t shift){if(shift!=35)__builtin_trap();std::uint32_t words[4]={seed,5,9,7};std::memcpy(p,words,16);}
static void DestroyCard(void*){++destroyed;}
extern "C" bool ProbeCardBorrowOOM(){
 if(!lua_checkstack(g_LuaState,100))return false;
 const int top=lua_gettop(g_LuaState);
 const auto owner=g_ErrorContextOwner,id=g_ErrorContextCallbackId;
 const auto scope=InManagedCallbackScope();ObserveGameThread();const auto manager=g_CurrentCallbackManager.load();
 isaac::runtime::CardNativeBindings native{OriginalCard,ConstructCard,DestroyCard};
 void* context=nullptr;auto allocator=lua_getallocf(g_LuaState,&context);
 RejectCardAllocation reject{allocator,context};lua_setallocf(g_LuaState,NoCardGrowth,&reject);
 const auto failed=isaac::runtime::RunCardIntercept(&native,nullptr,100,false,true,true);
 lua_setallocf(g_LuaState,allocator,context);
 const bool restored=failed==41&&destroyed==1&&g_CardRngScopes.top==nullptr&&lua_gettop(g_LuaState)==top&&g_ErrorContextOwner==owner&&
  g_ErrorContextCallbackId==id&&g_CurrentCallbackManager.load()==manager&&InManagedCallbackScope()==scope;
 const auto retry=isaac::runtime::RunCardIntercept(&native,nullptr,100,false,true,true);
 return restored&&retry==47&&destroyed==2&&g_CardRngScopes.top==nullptr&&lua_gettop(g_LuaState)==top;
}
}
'''
DRIVER=r'''
#include "lua_runtime.hpp"
#include <cstring>
extern "C" bool ProbeCardBorrowOOM();
int main(){
 const char* script="local m=RegisterMod('card-oom',1);m:AddCallback(1,function() end);_probe={count=0};m:AddCallback(20,function(_,rng,selected) assert(selected==41 and rng:GetSeed()==100);_probe.count=_probe.count+1;return 47 end)";
 if(LuaRuntime::InitializeFromBuffer(script,std::strlen(script),"@card-oom.lua")!=LuaRuntime::LuaInitResult::Success)return 1;
 if(!ProbeCardBorrowOOM()||!LuaRuntime::TakeCallbackError())return 2;
 double n=0;if(LuaRuntime::ReadLuaTableNumber("_probe","count",&n)||n!=1)return 3;
}
'''
class CardBorrowOOMTests(unittest.TestCase):
    def test_rng_userdata_oom_recovers_before_next_dispatch(self):
        with tempfile.TemporaryDirectory(prefix='isaac-card-oom-') as tmp:
            p=Path(tmp);copy=p/'instrumented_runtime.cpp';copy.write_text((SOURCE/'lua_runtime.cpp').read_text()+BRIDGE)
            sources=tuple(copy if source==SOURCE/'lua_runtime.cpp' else source for source in test_support.layered_lua_runtime_sources(SOURCE))
            with mock.patch.object(test_support,'layered_lua_runtime_sources',return_value=sources):
                binary=test_support.build_lua_harness(source_root=SOURCE,workdir=p,harness_source=DRIVER,extra_sources=(SOURCE/"card_hook.cpp",))
            r=subprocess.run([str(binary)],capture_output=True,text=True)
            self.assertEqual(r.returncode,0,r.stdout+r.stderr)

if __name__=='__main__':unittest.main()
