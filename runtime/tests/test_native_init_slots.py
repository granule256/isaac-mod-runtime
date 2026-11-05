"""Native Init completes before Lua publication; data slots leave code untouched."""
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

SLOTS = r'''
#include "native_init_slots.hpp"
#include <cassert>
using namespace isaac::runtime;
struct Memory {std::array<std::uintptr_t,2> words{0x1000,0x2000};unsigned swaps{};int fail{-1};bool foreign{};};
static std::uintptr_t Read(const void* p,std::uintptr_t a){return static_cast<const Memory*>(p)->words[a];}
static bool Swap(void* p,std::uintptr_t a,std::uintptr_t old,std::uintptr_t value){
 auto& m=*static_cast<Memory*>(p);++m.swaps;
 if(value==0x8888&&static_cast<int>(a)==m.fail){if(m.foreign)m.words[0]=0x9999;return false;}
 if(m.words[a]!=old)return false;m.words[a]=value;return true;
}
int main(){
 const std::array<std::uintptr_t,2> sites{0,1},expected{0x1000,0x2000};
 for(int fail:{-1,0,1}){
  Memory m;m.fail=fail;NativeInitSlotIo io{&m,Read,Swap};
  assert(InstallNativeInitSlotPlan(io,sites,expected,0x8888)==
   (fail==-1?NativeInitSlotFailure::None:NativeInitSlotFailure::WriteFailed));
  for(unsigned i=0;i<2;++i)assert(m.words[i]==(fail==-1?0x8888:expected[i]));
 }
 Memory m;NativeInitSlotIo io{&m,Read,Swap};m.words[1]=0x7777;
 assert(InstallNativeInitSlotPlan(io,sites,expected,0x8888)==NativeInitSlotFailure::GuardMismatch&&m.swaps==0);
 m={};m.fail=1;m.foreign=true;
 assert(InstallNativeInitSlotPlan(io,sites,expected,0x8888)==NativeInitSlotFailure::RollbackFailed);
 assert(m.words[0]==0x9999&&m.words[1]==0x2000);
 assert(InstallNativeInitSlotPlan(io,sites,expected,0)==NativeInitSlotFailure::InvalidPlan);
}
'''

BOUNDARY = r'''
#include "entity_init_hook.hpp"
#include <cassert>
#include <vector>
using namespace isaac::runtime;
struct Entity {bool fields{},added{},updated{};unsigned init{};} entity;
static std::vector<int> events;
static bool reenter{};
static void Native(void* p,std::uint32_t type,std::uint32_t variant,std::uint32_t subtype,std::uint32_t seed){
 assert(p==&entity&&type==2&&variant==7&&subtype==3&&seed==42);
 events.push_back(1);entity.fields=true;++entity.init;
}
static EntityInitNativeBindings bindings{Native};
namespace isaac::runtime {
void ReinitializeEntityLifetime(std::uintptr_t p) noexcept {assert(p==reinterpret_cast<std::uintptr_t>(&entity));events.push_back(2);}
}
namespace LuaRuntime {
void DispatchNativeTearInit(std::uintptr_t p) noexcept {
 assert(p==reinterpret_cast<std::uintptr_t>(&entity)&&entity.fields&&!entity.added&&!entity.updated);
 events.push_back(3);
 if(reenter){reenter=false;RunNativeEntityInit(&bindings,NativeEntityInitKind::Tear,&entity,2,7,3,42);}
}
void DispatchNativeEffectInit(std::uintptr_t p) noexcept {
 assert(p==reinterpret_cast<std::uintptr_t>(&entity)&&entity.fields&&!entity.added&&!entity.updated);events.push_back(4);
}
}
int main(){
 // The same wrapper is installed into virtual and PLT slots; each actual call emits once.
 for(auto kind:{NativeEntityInitKind::Tear,NativeEntityInitKind::Effect}){
  entity={};events.clear();
  RunNativeEntityInit(&bindings,kind,&entity,2,7,3,42);
  assert((events==std::vector<int>{1,kind==NativeEntityInitKind::Tear?3:4}));
  entity.added=true;events.push_back(5);entity.updated=true;events.push_back(6);
  assert(events[1]<events[2]);
 }
 entity={};events.clear();RunNativeEntityInit(&bindings,NativeEntityInitKind::Base,&entity,2,7,3,42);
 assert((events==std::vector<int>{1,2}));
 // Child tears do not require FireTear. Repeated Init and Lua reentry are real separate events.
 entity={};events.clear();reenter=true;
 RunNativeEntityInit(&bindings,NativeEntityInitKind::Tear,&entity,2,7,3,42);
 RunNativeEntityInit(&bindings,NativeEntityInitKind::Tear,&entity,2,7,3,42);
 assert(entity.init==3&&(events==std::vector<int>{1,3,1,3,1,3}));
}
'''


class NativeInitSlotTests(unittest.TestCase):
    def compile_run(self, driver, *sources):
        with tempfile.TemporaryDirectory(prefix='native-init-') as directory:
            work = Path(directory)
            (work / 'main.cpp').write_text(driver)
            result = subprocess.run(['clang++', '-std=c++23', '-Wall', '-Wextra', '-Werror',
                '-I', str(ROOT / 'runtime/source'), '-I', str(ROOT / 'runtime/src'),
                str(work / 'main.cpp'), *map(str, sources), '-o', str(work / 'test')],
                text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            result = subprocess.run([str(work / 'test')], text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_atomic_guard_failure_rollback_and_foreign_writes(self):
        self.compile_run(SLOTS)

    def test_real_derived_completion_repeated_calls_and_reentry(self):
        self.compile_run(BOUNDARY, ROOT / 'runtime/source/entity_init_hook.cpp')
