"""Compile the actual player entry wrapper with the real scoped middle bridge."""
from pathlib import Path
import subprocess
import tempfile
import unittest

from .test_lua_api_method_lookup_cost import function
from .test_player_damage_internal_hook import SOURCE, UNITS

PREFIX=r'''
#include "player_damage_internal_hook.hpp"
#include "infrastructure/memory/engine_field_access.hpp"
#include <array>
#include <cassert>
#include <cstring>
static bool inNative{}, reachesBoundary{}, cancel{};
static unsigned originalCalls{}, dispatchCalls{}, replays{};
std::uint64_t FakeNative(void*,float,std::uint64_t,const void*,std::int32_t);
namespace LuaRuntime {
bool DispatchEntityTakeDamage(std::uintptr_t player,float hearts,std::uint64_t flags,
    std::uintptr_t source,std::int32_t countdown,std::int32_t type) {
    assert(inNative && "player callback must not run at function entry");
    ++dispatchCalls;
    assert(player==0x123400 && hearts==2 && flags==0x100000003ULL);
    assert(source==0x432100 && countdown==17 && type==1);
    return cancel;
}
}
namespace isaac::runtime {
enum class HookId {EntityPlayerTakeDamage};
template<class Fn>Fn Original(HookId){return &FakeNative;}
bool ReadEntityIdentity(std::uintptr_t,std::uint32_t*t,std::uint32_t*v){*t=1;*v=0;return true;}
}
'''
MAIN=r'''
static bool Replay(void*){++replays;return false;}
std::uint64_t FakeNative(void* player,float amount,std::uint64_t flags,const void* source,std::int32_t countdown){
    ++originalCalls;inNative=true;
    assert(reinterpret_cast<std::uintptr_t>(player)==0x123400 && amount==1.25F);
    assert(flags==0x100000003ULL && reinterpret_cast<std::uintptr_t>(source)==0x432100 && countdown==17);
    if(reachesBoundary){
        alignas(16)std::array<unsigned char,0x80> stack{};
        const std::int32_t hearts=2;std::memcpy(stack.data()+0x4c,&hearts,4);
        isaac::runtime::relay::InternalHookContext ctx{};
        ctx.x[0]=ctx.x[19]=reinterpret_cast<std::uintptr_t>(player);
        ctx.x[20]=flags;ctx.x[22]=reinterpret_cast<std::uintptr_t>(source);
        ctx.originalSp=reinterpret_cast<std::uintptr_t>(stack.data());
        isaac::runtime::PlayerDamageNativeBindings native{Replay,LuaRuntime::DispatchEntityTakeDamage};
        if(isaac::runtime::PlayerDamageInternalCallback(ctx,&native)){inNative=false;return 0;}
    }
    inNative=false;return 7;
}
static std::uint64_t Invoke(){return EntryRelayEntityPlayerTakeDamageCallback(
    reinterpret_cast<void*>(0x123400),1.25F,0x100000003ULL,reinterpret_cast<void*>(0x432100),17);}
int main(){
    reachesBoundary=false;assert(Invoke()==7 && originalCalls==1 && dispatchCalls==0);
    reachesBoundary=true;assert(Invoke()==7 && originalCalls==2 && dispatchCalls==1 && replays==1);
    cancel=true;assert(Invoke()==0 && originalCalls==3 && dispatchCalls==2 && replays==1);
    // The wrapper must have unwound its scope even after cancellation.
    alignas(16)std::array<unsigned char,0x80> stack{};
    isaac::runtime::relay::InternalHookContext ctx{};
    ctx.x[0]=ctx.x[19]=0x123400;ctx.x[22]=0x432100;
    ctx.originalSp=reinterpret_cast<std::uintptr_t>(stack.data());
    isaac::runtime::PlayerDamageNativeBindings native{Replay,LuaRuntime::DispatchEntityTakeDamage};
    assert(isaac::runtime::PlayerDamageInternalCallback(ctx,&native)==0 && dispatchCalls==2 && replays==2);
}
'''


class PlayerDamageEntryScopeTests(unittest.TestCase):
    def test_actual_entry_only_preserves_native_call_context(self):
        path=SOURCE/'hook_manager.cpp'
        if not path.is_file():
            self.skipTest('entry wrapper requires the assembled private hook adapter')
        text=path.read_text()
        common='template<class Fn>\n'+function(text,'std::uint64_t RunEntityTakeDamageRelay(')
        wrapper=function(text,'extern "C" std::uint64_t EntryRelayEntityPlayerTakeDamageCallback(')
        with tempfile.TemporaryDirectory(prefix='player-damage-entry-') as tmp:
            work=Path(tmp);driver=work/'entry.cpp'
            driver.write_text(PREFIX+common+'\n'+wrapper+'\n'+MAIN)
            result=subprocess.run(['c++','-std=c++20','-Wall','-Wextra','-Werror',
                '-I'+str(SOURCE),'-I'+str(UNITS),str(driver),str(SOURCE/'player_damage_internal_hook.cpp'),
                '-o',str(work/'entry')],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            result=subprocess.run([str(work/'entry')],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
