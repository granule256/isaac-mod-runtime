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
namespace LuaRuntime {
struct RejectTrinketAllocation {lua_Alloc allocator;void* context;};
void* NoTrinketGrowth(void* context,void* block,size_t oldSize,size_t newSize){
 auto* a=static_cast<RejectTrinketAllocation*>(context);
 return newSize>oldSize?nullptr:a->allocator(a->context,block,oldSize,newSize);
}
extern "C" bool ProbeTrinketSnapshotOOM(){
 if(!lua_checkstack(g_LuaState,100))return false;
 const int top=lua_gettop(g_LuaState);
 const auto owner=g_ErrorContextOwner,id=g_ErrorContextCallbackId;
 const auto scope=InManagedCallbackScope();const auto manager=g_CurrentCallbackManager.load();
 std::array<std::uint8_t,16> snapshot{};snapshot[0]=100;
 void* context=nullptr;auto allocator=lua_getallocf(g_LuaState,&context);
 RejectTrinketAllocation reject{allocator,context};lua_setallocf(g_LuaState,NoTrinketGrowth,&reject);
 const auto failed=DispatchGetTrinket(41,snapshot);
 lua_setallocf(g_LuaState,allocator,context);
 const bool restored=failed==0&&lua_gettop(g_LuaState)==top&&g_ErrorContextOwner==owner&&
  g_ErrorContextCallbackId==id&&g_CurrentCallbackManager.load()==manager&&InManagedCallbackScope()==scope;
 const auto retry=DispatchGetTrinket(41,snapshot);
 return restored&&retry==47&&lua_gettop(g_LuaState)==top;
}
}
'''
DRIVER=r'''
#include "lua_runtime.hpp"
#include <cstring>
extern "C" bool ProbeTrinketSnapshotOOM();
int main(){
 const char* script="local m=RegisterMod('trinket-oom',1);m:AddCallback(1,function() end);_probe={count=0};m:AddCallback(66,function(_,selected,rng) assert(selected==41 and rng:GetSeed()==100);_probe.count=_probe.count+1;return 47 end)";
 if(LuaRuntime::InitializeFromBuffer(script,std::strlen(script),"@trinket-oom.lua")!=LuaRuntime::LuaInitResult::Success)return 1;
 if(!ProbeTrinketSnapshotOOM()||!LuaRuntime::TakeCallbackError())return 2;
 double n=0;if(LuaRuntime::ReadLuaTableNumber("_probe","count",&n)||n!=1)return 3;
}
'''
class TrinketSnapshotOOMTests(unittest.TestCase):
    def test_rng_userdata_oom_recovers_before_next_dispatch(self):
        with tempfile.TemporaryDirectory(prefix='isaac-trinket-oom-') as tmp:
            p=Path(tmp);copy=p/'instrumented_runtime.cpp';copy.write_text((SOURCE/'lua_runtime.cpp').read_text()+BRIDGE)
            sources=tuple(copy if source==SOURCE/'lua_runtime.cpp' else source for source in test_support.layered_lua_runtime_sources(SOURCE))
            with mock.patch.object(test_support,'layered_lua_runtime_sources',return_value=sources):
                binary=test_support.build_lua_harness(source_root=SOURCE,workdir=p,harness_source=DRIVER)
            r=subprocess.run([str(binary)],capture_output=True,text=True)
            self.assertEqual(r.returncode,0,r.stdout+r.stderr)

if __name__=='__main__':unittest.main()
