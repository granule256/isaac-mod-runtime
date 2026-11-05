"""World changes have independent, retryable consumers outside PC callbacks."""
import subprocess
import tempfile
import unittest
from pathlib import Path

from .test_support import LUA_SOURCE_RELATIVE, lua_harness_objects

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'runtime/source'
DRIVER = r'''
#include <cassert>
#include <cstdio>
#include <cstdlib>
#if __has_include("interfaces/lua/compatibility_adapter_runtime.hpp")
#include "interfaces/lua/compatibility_adapter_runtime.hpp"
#include "infrastructure/native/world_content_mutations.hpp"
#include "native_room_events.hpp"
extern "C" {
#include "lua.h"
#include "lauxlib.h"
#include "lualib.h"
}
using namespace isaac::runtime;
struct Allocator {bool fail{}; unsigned allocations{};};
void* Allocate(void* context,void* old,size_t,size_t size){
    if(!size){std::free(old);return nullptr;}
    auto& a=*static_cast<Allocator*>(context);++a.allocations;
    return a.fail?nullptr:std::realloc(old,size);
}
void Run(lua_State* L,const char* script){
    if(luaL_dostring(L,script)!=LUA_OK){std::fprintf(stderr,"%s\n",lua_tostring(L,-1));std::abort();}
}
int Mutation(lua_State*){RecordWorldContentMutation(WorldContentMutation::PickupsRerolled);return 0;}
int ChangeFloor(lua_State*){
    BeginWorldContentFloor();RecordWorldContentMutation(WorldContentMutation::CollectiblesRerolled);return 0;
}
void NestedInit(void*){RecordWorldContentMutation(WorldContentMutation::CollectiblesRerolled);}
void OuterInit(void* level){CompleteNativeLevelInit(NestedInit,level);}
template<class Diagnostic> bool WasSkipped(const Diagnostic& d){
    if constexpr(requires {d.skipped;d.applications;d.lastResult;d.reason;})
        return d.skipped==1&&d.applications==0&&
               d.lastResult==decltype(d.lastResult)::NotApplicable&&d.reason[0];
    return false;
}
template<class Diagnostic> bool WasAppliedAfterSkip(const Diagnostic& d){
    if constexpr(requires {d.skipped;d.applications;d.lastResult;d.reason;})
        return d.skipped==1&&d.applications==1&&
               d.lastResult==decltype(d.lastResult)::Applied&&!d.reason[0];
    return false;
}
int main(){
    BeginWorldContentRun();
    auto start=CaptureWorldContentSnapshot();
    WorldContentCursor first{start},second{start};
    CompleteWorldContentMutation(WorldContentMutation::PickupsRerolled,[](){
        CompleteWorldContentMutation(WorldContentMutation::PickupsRerolled,[](){});
    });
    auto nested=CaptureWorldContentSnapshot();
    assert(nested.version==start.version+2);
    assert(ChangesSince(first,nested).pickupsChanged&&ChangesSince(second,nested).pickupsChanged);
    first.snapshot=nested;
    assert(!ChangesSince(first,nested).Any()&&ChangesSince(second,nested).Any());
    BeginWorldContentFloor();
    auto floor=CaptureWorldContentSnapshot();
    assert(floor.worldEpoch==nested.worldEpoch&&floor.floorEpoch!=nested.floorEpoch);
    assert(!ChangesSince(second,floor).Any());
    RecordWorldContentMutation(WorldContentMutation::CollectiblesRerolled);
    assert(ChangesSince(second,CaptureWorldContentSnapshot()).collectiblesChanged);
    WorldContentCursor beforeInit{CaptureWorldContentSnapshot()};
    RecordWorldContentMutation(WorldContentMutation::PickupsRerolled);
    std::uint32_t level[]{3,0};CompleteNativeLevelInit(OuterInit,level);
    auto afterInit=CaptureWorldContentSnapshot();
    assert(afterInit.floorEpoch==beforeInit.snapshot.floorEpoch+1);
    assert(!ChangesSince(beforeInit,afterInit).pickupsChanged);
    assert(ChangesSince(beforeInit,afterInit).collectiblesChanged);
    Allocator allocator;auto* L=lua_newstate(Allocate,&allocator);assert(L);
    luaL_requiref(L,"_G",luaopen_base,1);lua_pop(L,1);assert(lua_checkstack(L,80));
    lua_pushcfunction(L,Mutation);lua_setglobal(L,"mutate");
    lua_pushcfunction(L,ChangeFloor);lua_setglobal(L,"changeFloor");
    Run(L,R"lua(
      countA=0;countB=0; fail=true;reenter=false
      function adapterA(p,c,w,f)
        assert(p or c);assert(w>0 and f>0);countA=countA+1
        if fail then error('retry me') end
        if reenter then reenter=false;mutate() end
        if scopeChange then scopeChange=false;changeFloor() end
      end
      function adapterB(p,c) countB=countB+1;lastBP=p;lastBC=c end
    )lua");
    CompatibilityAdapterId a{},b{};
    lua_getglobal(L,"adapterA");assert(RegisterCompatibilityAdapter(L,"A",-1,&a));lua_pop(L,1);
    lua_getglobal(L,"adapterB");assert(RegisterCompatibilityAdapter(L,"B",-1,&b));lua_pop(L,1);
    Run(L,"adapterA=nil;adapterB=nil;collectgarbage()"); // only private refs retain closures
    int top=lua_gettop(L);unsigned calls=allocator.allocations;
    allocator.fail=true;PumpCompatibilityAdapters(L);assert(allocator.allocations==calls);allocator.fail=false;
    RecordWorldContentMutation(WorldContentMutation::PickupsRerolled);
    PumpCompatibilityAdapters(L);assert(lua_gettop(L)==top);
    Run(L,"assert(countA==1 and countB==1)");
    assert(HasPendingCompatibilityAdapters());
    auto diagnostic=GetCompatibilityAdapterDiagnostics(a);
    assert(diagnostic.failures==1&&diagnostic.lastStatus!=LUA_OK);
    Run(L,"fail=false;reenter=true");
    PumpCompatibilityAdapters(L);
    assert(HasPendingCompatibilityAdapters()); // mutation inside successful A stays pending
    PumpCompatibilityAdapters(L);
    Run(L,"assert(countA==3 and countB==2)");
    assert(!HasPendingCompatibilityAdapters());
    RecordWorldContentMutation(WorldContentMutation::CollectiblesRerolled);
    BeginWorldContentFloor();
    PumpCompatibilityAdapters(L);Run(L,"assert(countA==3 and countB==2)");
    RecordWorldContentMutation(WorldContentMutation::PickupsRerolled);
    PumpCompatibilityAdapters(L);Run(L,"assert(countA==4 and countB==3)");
    Run(L,"scopeChange=true");
    RecordWorldContentMutation(WorldContentMutation::PickupsRerolled);
    PumpCompatibilityAdapters(L);
    Run(L,"assert(not lastBP and lastBC,'old scope crossed between consumers')");
    assert(HasPendingCompatibilityAdapters());
    PumpCompatibilityAdapters(L);assert(!HasPendingCompatibilityAdapters());
    Run(L,"adapterA=function() local x={} for i=1,20000 do x[i]=i end end");
    ResetCompatibilityAdapters(L);
    lua_getglobal(L,"adapterA");assert(RegisterCompatibilityAdapter(L,"oom",-1,&a));lua_pop(L,1);
    RecordWorldContentMutation(WorldContentMutation::PickupsRerolled);
    allocator.fail=true;PumpCompatibilityAdapters(L);allocator.fail=false;
    assert(HasPendingCompatibilityAdapters()&&GetCompatibilityAdapterDiagnostics(a).lastStatus==LUA_ERRMEM);
    PumpCompatibilityAdapters(L);assert(!HasPendingCompatibilityAdapters());
    lua_gc(L,LUA_GCCOLLECT,0);
    ResetCompatibilityAdapters(L);assert(!HasPendingCompatibilityAdapters());
    assert(GetCompatibilityAdapterDiagnostics(a).attempts==0);
    Run(L,R"lua(
      version=99
      function versionedAdapter()
        if version~=59 and version~=62 then return false,'unsupported version' end
        return true
      end
    )lua");
    lua_getglobal(L,"versionedAdapter");assert(RegisterCompatibilityAdapter(L,"versioned",-1,&a));lua_pop(L,1);
    RecordWorldContentMutation(WorldContentMutation::PickupsRerolled);PumpCompatibilityAdapters(L);
    if(!WasSkipped(GetCompatibilityAdapterDiagnostics(a))){
        std::fprintf(stderr,"not-applicable result lacks distinct diagnostics\n");return 1;
    }
    assert(!HasPendingCompatibilityAdapters()&&GetCompatibilityAdapterDiagnostics(a).failures==0);
    Run(L,"version=62");
    RecordWorldContentMutation(WorldContentMutation::CollectiblesRerolled);PumpCompatibilityAdapters(L);
    assert(WasAppliedAfterSkip(GetCompatibilityAdapterDiagnostics(a)));
    ResetCompatibilityAdapters(L);lua_close(L);
}
#else
int main(){std::fprintf(stderr,"world content consumer model is missing\n");return 1;}
#endif
'''


class WorldContentAdapterTests(unittest.TestCase):
    def test_independent_retry_reentry_scope_and_lua_allocation_failure(self):
        with tempfile.TemporaryDirectory(prefix='isaac-world-adapters-') as temporary:
            work = Path(temporary)
            (work / 'driver.cpp').write_text(DRIVER)
            objects = lua_harness_objects(SOURCE, work)
            paths = [ROOT / 'runtime/src/interfaces/lua/compatibility_adapter_runtime.cpp',
                     ROOT / 'runtime/src/infrastructure/native/world_content_mutations.cpp']
            result = subprocess.run([
                'clang++', '-std=c++23', '-Wall', '-Wextra', '-Werror',
                '-I', str(ROOT / 'runtime/src'), '-I', str(SOURCE),
                '-I', str(SOURCE / LUA_SOURCE_RELATIVE), str(work / 'driver.cpp'),
                *[str(path) for path in paths if path.exists()],
                *map(str, objects), '-o', str(work / 'driver')
            ], text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            result = subprocess.run([str(work / 'driver')], text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
