"""执行生产Clear计时探针，验证真实PLT守卫、透传、作用域和安装失败回滚。"""
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
PROBE=ROOT/'runtime/src/application/shader/native_clear_probe.cpp'
DRIVER=r'''
#include <cassert>
#include <cstring>
#include <vector>
#include <cstdint>
#include <thread>
thread_local bool gameThread=true; unsigned calls[3]{}; void* last[3]{};
std::uint64_t ticks=0;std::uintptr_t failRw=0; bool inject=false;std::uintptr_t retainedIntercept=0;
std::uintptr_t OnRw(std::uintptr_t a){if(inject&&a==failRw){retainedIntercept=*reinterpret_cast<std::uintptr_t*>(a+0xf0);reinterpret_cast<void(*)(void*)>(retainedIntercept)(reinterpret_cast<void*>(7));*reinterpret_cast<std::uintptr_t*>(a)=0x12345678;inject=false;}return a;}
namespace LuaRuntime{bool IsOnGameThread()noexcept{return gameThread;}}
namespace isaac::runtime{std::uint64_t RuntimePerfTick()noexcept{return ++ticks;}}
void Flush(void* p){++calls[0];last[0]=p;}
void Sync(void* p){++calls[1];last[1]=p;}
void* Acquire(void* p){++calls[2];last[2]=p;return reinterpret_cast<void*>(0x34567890);}
#include "application/shader/native_clear_probe.cpp"
int main(){using namespace isaac::runtime;
 std::vector<unsigned char> image(0xab0000), graphics(0x40);
 const auto base=reinterpret_cast<std::uintptr_t>(image.data());
 const unsigned offsets[3]={0xaa68e8,0xaa67f8,0xaa6930};
 const unsigned plts[3]={0x681300,0x681120,0x681390};
 const unsigned char guards[3][16]={GUARDS};
 const std::uintptr_t originals[3]={reinterpret_cast<std::uintptr_t>(&Flush),reinterpret_cast<std::uintptr_t>(&Sync),reinterpret_cast<std::uintptr_t>(&Acquire)};
 auto slot=[&](int i)->std::uintptr_t&{return *reinterpret_cast<std::uintptr_t*>(image.data()+offsets[i]);};
 auto reset=[&](){for(int i=0;i<3;++i){memcpy(image.data()+plts[i],guards[i],16);slot(i)=originals[i];}};
 reset();assert(!InstallNativeClearProbe(0));
 for(int j=0;j<3;++j)for(int k=0;k<16;++k){image[plts[j]+k]^=1;assert(!InstallNativeClearProbe(base));for(int i=0;i<3;++i)assert(slot(i)==originals[i]);image[plts[j]+k]^=1;}
 for(int j=0;j<3;++j){slot(j)=base+kPltResolverOffset;assert(!InstallNativeClearProbe(base));for(int i=0;i<3;++i)assert(slot(i)==(i==j?base+kPltResolverOffset:originals[i]));slot(j)=originals[j];}
 // Simulate another writer changing the second slot between snapshot and CAS.
 failRw=base+offsets[1];inject=true;assert(!InstallNativeClearProbe(base));
 assert(slot(0)==originals[0]&&slot(1)==0x12345678&&slot(2)==originals[2]);
 reinterpret_cast<void(*)(void*)>(retainedIntercept)(reinterpret_cast<void*>(9));assert(calls[0]==2&&last[0]==reinterpret_cast<void*>(9));for(auto& n:calls)n=0;
 reset();assert(InstallNativeClearProbe(base));std::uintptr_t wrapped[3];for(int i=0;i<3;++i){wrapped[i]=slot(i);assert(wrapped[i]!=originals[i]);}
 assert(InstallNativeClearProbe(base));for(int i=0;i<3;++i)assert(slot(i)==wrapped[i]);
 auto invoke=[&](){reinterpret_cast<void(*)(void*)>(slot(0))(graphics.data());reinterpret_cast<void(*)(void*)>(slot(1))(graphics.data());assert(reinterpret_cast<void*(*)(void*)>(slot(2))(graphics.data())==reinterpret_cast<void*>(0x34567890));};
 invoke();for(auto& group:g_NativeShaderClearDetail)for(auto& row:group)assert(row[0]==0);
 {NativeClearProbeScope offscreen(true);invoke();{NativeClearProbeScope screen(false);invoke();}invoke();
  std::thread other([&](){gameThread=false;invoke();{NativeClearProbeScope ignored(false);invoke();}});other.join();invoke();}
 invoke();
 for(int i=0;i<3;++i){assert(calls[i]==8&&last[i]==graphics.data());assert(g_NativeShaderClearDetail[0][i][0]==3);assert(g_NativeShaderClearDetail[1][i][0]==1);assert(g_NativeShaderClearDetail[0][i][1]==3&&g_NativeShaderClearDetail[0][i][2]==1);assert(g_NativeShaderClearDetail[1][i][1]==1&&g_NativeShaderClearDetail[1][i][2]==1);}
 static_assert(sizeof(g_NativeShaderClearDetail)==144);return 0;
}
'''

class NativeClearProbeTests(unittest.TestCase):
 def test_production_probe_transparency_scopes_guards_and_rollback(self):
  self.assertTrue(PROBE.exists(),'production NativeClear detail probe is not implemented')
  guards=json.loads((ROOT/'dist/native-clear-profile-20261017/import-guards.json').read_text())
  rows=','.join('{'+','.join(str(n) for n in guards[key]['bytes'])+'}' for key in ('flush','sync','acquire'))
  with tempfile.TemporaryDirectory(prefix='native-clear-probe-') as tmp:
   p=Path(tmp)
   stubs={
    'infrastructure/memory/engine_field_access.hpp':'''#pragma once
#include <cstdint>
#include <cstddef>
namespace isaac::runtime::engine_memory{inline bool EngineMemoryReadable(std::uintptr_t a,std::size_t){return a!=0;}inline void* AsObject(std::uintptr_t a){return reinterpret_cast<void*>(a);}}''',
    'infrastructure/call/engine_call_access.hpp':'''#pragma once
#include <cstring>
#include <cstdint>
namespace isaac::runtime::engine_call{template<class F>F AsFunction(std::uintptr_t a){return reinterpret_cast<F>(a);}template<class F>std::uintptr_t AddressOfFunction(F f){return reinterpret_cast<std::uintptr_t>(f);}inline bool VerifyEntryBytes(std::uintptr_t a,const void* b,std::size_t n,bool(*read)(std::uintptr_t,std::size_t)){return read(a,n)&&!std::memcmp(reinterpret_cast<void*>(a),b,n);}}''',
    'lib/util/sys/rw_pages.hpp':'''#pragma once
#include <cstdint>
#include <cstddef>
std::uintptr_t OnRw(std::uintptr_t);
namespace exl::util{struct RwPages{std::uintptr_t p;RwPages(std::uintptr_t a,std::size_t):p(a){}std::uintptr_t GetRw()const{return OnRw(p);}void Flush(){}};}''',
    'lua_runtime.hpp':'#pragma once\nnamespace LuaRuntime{bool IsOnGameThread()noexcept;}',
    'interfaces/lua/runtime_perf.hpp':'#pragma once\n#include <cstdint>\nnamespace isaac::runtime{std::uint64_t RuntimePerfTick()noexcept;}',
    'runtime_constants.hpp':'#pragma once\nconstexpr unsigned kPltResolverOffset=0x66faa0;'}
   for name,text in stubs.items():
    f=p/name;f.parent.mkdir(parents=True,exist_ok=True);f.write_text(text)
   (p/'test.cpp').write_text(DRIVER.replace('GUARDS',rows))
   r=subprocess.run(['c++','-std=c++20','-O2','-Wall','-Wextra','-Werror','-I'+str(p),'-I'+str(ROOT/'runtime/src'),str(p/'test.cpp'),'-o',str(p/'test')],capture_output=True,text=True)
   self.assertEqual(r.returncode,0,r.stdout+r.stderr)
   symbols=subprocess.run(['nm','-C',str(p/'test')],capture_output=True,text=True)
   self.assertEqual(symbols.returncode,0,symbols.stderr)
   self.assertNotIn('__cxx_global_var_init',symbols.stdout)
   self.assertNotIn('_GLOBAL__sub_I',symbols.stdout)
   r=subprocess.run([str(p/'test')],capture_output=True,text=True)
   self.assertEqual(r.returncode,0,r.stdout+r.stderr)

if __name__=='__main__':unittest.main()
