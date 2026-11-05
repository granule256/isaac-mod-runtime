"""The native restart chord must use the same callback override as PC actions."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
HOOK = ROOT/'runtime/src/infrastructure/gotslot/restart_input_hook.cpp'

DRIVER = r'''
#include "ports/hook_port.hpp"
#include "runtime_constants.hpp"
#include "lua_runtime.hpp"
#include <cassert>
#include <cstdio>
#include <cstring>
#include <vector>
namespace isaac::runtime {
Status InstallNativeRestartInputHook(const HookTarget&) noexcept __attribute__((weak));
Status InstallNativeRestartInputHook(const HookTarget&) noexcept {return Status{StatusCode::Rejected};}
bool QueryNativeRestartInput(std::uintptr_t,void*,unsigned,unsigned,void*) noexcept;
}
static std::uintptr_t imageBase{};
static unsigned held{},rawCalls{},callbacks{};
static bool overrideEnabled{},overrideValue{};
static int manager{};
bool Raw(void* m,unsigned code,unsigned controller,void* out){
 assert(m==&manager&&controller==0xffffffffU&&!out);++rawCalls;
 return (held&(1u<<code))!=0;
}
std::uintptr_t TestEngineAddress(std::uintptr_t address) noexcept {
 return address==imageBase+0x4f9504?reinterpret_cast<std::uintptr_t>(&Raw):address;
}
namespace LuaRuntime {
InputActionOutcome DispatchLogicalInputAction(unsigned action,int hook,std::uintptr_t entity){
 assert(action==18&&hook==0&&entity==0);++callbacks;
 return {overrideEnabled,overrideValue,0};
}
}
int main(){
 using namespace isaac::runtime;
 std::vector<unsigned char> image(0xab0000);imageBase=reinterpret_cast<std::uintptr_t>(image.data());
 const auto base=imageBase;
 const unsigned char entry[]={0xfd,0x7b,0xbc,0xa9,0xf8,0x5f,0x01,0xa9,0xfd,0x03,0x00,0x91,0xf6,0x57,0x02,0xa9};
 const unsigned char plt[]={0x70,0x21,0x00,0xb0,0x11,0xfe,0x44,0xf9,0x10,0xe2,0x27,0x91,0x20,0x02,0x1f,0xd6};
 const unsigned char context[]={CONTEXT};
 std::memcpy(image.data()+0x4f9504,entry,16);std::memcpy(image.data()+0x671520,plt,16);
 std::memcpy(image.data()+0x351658,context,sizeof(context));
 auto* slot=reinterpret_cast<std::uintptr_t*>(image.data()+0xa9e9f8);*slot=base+0x4f9504;
 HookTarget t{};t.base=base;t.codeSize=0x68d000;t.imageSize=image.size();t.buildId=kTargetBuildId;
 for(auto offset:{0x4f9504,0x671520,0x351674,0x3516c8}){
  image[offset]^=1;assert(!InstallNativeRestartInputHook(t).ok()&&*slot==base+0x4f9504);image[offset]^=1;
 }
 auto bad=t;bad.buildId[0]^=1;assert(!InstallNativeRestartInputHook(bad).ok());
 bad=t;bad.imageSize=0xa9e9ff;assert(!InstallNativeRestartInputHook(bad).ok());
 *slot=123;assert(!InstallNativeRestartInputHook(t).ok()&&*slot==123);*slot=base+0x4f9504;
 if(!InstallNativeRestartInputHook(t).ok()){
  std::fprintf(stderr,"valid native restart input hook was not installed\n");return 1;
 }
 assert(*slot!=base+0x4f9504);assert(!InstallNativeRestartInputHook(t).ok());
 assert(!std::memcmp(image.data()+0x4f9504,entry,16));
 auto query=[&](unsigned site,unsigned code){return QueryNativeRestartInput(base+site,&manager,code,0xffffffffU,nullptr);};
 // Other raw button consumers, including Lua Input.*, remain untouched.
 held=1u<<13;assert(query(0x1234,13)&&callbacks==0&&rawCalls==1);
 constexpr unsigned chord=(1u<<8)|(1u<<11)|(1u<<10)|(1u<<13);
 held=chord;assert(query(0x351678,8)&&callbacks==1&&rawCalls==5);
 assert(query(0x351694,11)&&query(0x3516b0,10)&&query(0x3516cc,13));
 assert(callbacks==1&&rawCalls==5);
 overrideEnabled=true;overrideValue=false;
 assert(!query(0x351678,8)&&callbacks==2);
 // A true override must work through the entire native conjunction.
 held=0;overrideValue=true;assert(query(0x351678,8)&&callbacks==3);
 assert(query(0x351694,11)&&query(0x3516b0,10)&&query(0x3516cc,13));
 assert(callbacks==3);
 overrideEnabled=false;assert(!query(0x351678,8)&&callbacks==4);
 assert(!query(0x1234,13)&&callbacks==4);
}
'''


class NativeRestartHookTests(unittest.TestCase):
    def test_native_query_override_and_exact_got_installation(self):
        # Instruction guards are read from the explicit local game input.
        nro = next(ROOT.glob('The Binding of Isaac_*/Program #0/1/.nro/Repentance.nro')).read_bytes()
        context = ','.join(str(x) for x in nro[0x351658:0x3516d8])
        with tempfile.TemporaryDirectory(prefix='isaac-restart-hook-') as temporary:
            path = Path(temporary)
            (path/'lua_runtime.hpp').write_text('#pragma once\n#include <cstdint>\nnamespace LuaRuntime {struct InputActionOutcome{bool overridden{},boolean{};float value{};};InputActionOutcome DispatchLogicalInputAction(unsigned,int,std::uintptr_t);}\n')
            shim = path/'lib/util/sys/rw_pages.hpp';shim.parent.mkdir(parents=True)
            shim.write_text('#pragma once\n#include <cstdint>\n#include <cstddef>\nnamespace exl::util {struct RwPages{std::uintptr_t p;RwPages(std::uintptr_t a,std::size_t):p(a){}std::uintptr_t GetRw()const{return p;}void Flush(){}};}\n')
            calls = path/'infrastructure/call/engine_call_access.hpp';calls.parent.mkdir(parents=True)
            calls.write_text('#pragma once\n#include <cstdint>\nstd::uintptr_t TestEngineAddress(std::uintptr_t) noexcept;\nnamespace isaac::runtime::engine_call {template<class T>T AsFunction(std::uintptr_t p)noexcept{return reinterpret_cast<T>(TestEngineAddress(p));}template<class T>std::uintptr_t AddressOfFunction(T p)noexcept{return reinterpret_cast<std::uintptr_t>(p);}}\n')
            (path/'test.cpp').write_text(DRIVER.replace('CONTEXT', context))
            # The RED baseline rejects a valid installation before any query.
            sources = [str(HOOK)] if HOOK.exists() else []
            if not sources:
                (path/'test.cpp').write_text((path/'test.cpp').read_text().replace(
                    'bool QueryNativeRestartInput(std::uintptr_t,void*,unsigned,unsigned,void*) noexcept;',
                    'bool QueryNativeRestartInput(std::uintptr_t,void*,unsigned,unsigned,void*) noexcept {return false;}'))
            result = subprocess.run(['c++','-std=c++20','-Wall','-Wextra','-Werror',
                '-I'+str(path),'-I'+str(ROOT/'runtime/source'),'-I'+str(ROOT/'runtime/src'),
                str(path/'test.cpp'),*sources,'-o',str(path/'test')],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            result = subprocess.run([str(path/'test')],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
