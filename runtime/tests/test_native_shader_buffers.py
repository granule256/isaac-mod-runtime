"""执行生产native后端，观察专用图像的GPU上传准备、重用和分配上界。"""
import subprocess
import tempfile
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
MEMORY=r'''#pragma once
#include <cstddef>
#include <cstdint>
namespace isaac::runtime::engine_memory {
inline bool EngineMemoryReadable(std::uintptr_t a,std::size_t){return a!=0;}
inline void* AsObject(std::uintptr_t a){return reinterpret_cast<void*>(a);}
inline std::uintptr_t AddressOf(const void* p){return reinterpret_cast<std::uintptr_t>(p);}
}'''
CALL=r'''#pragma once
#include "infrastructure/memory/engine_field_access.hpp"
void* Resolve(std::uintptr_t);
namespace isaac::runtime::engine_call {
template<class F>F AsFunction(std::uintptr_t a){return reinterpret_cast<F>(Resolve(a));}
inline bool VerifyEntryBytes(std::uintptr_t,const void*,std::size_t,bool(*)(std::uintptr_t,std::size_t)){return true;}
}'''
HARNESS=r'''
#include <vector>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include "application/shader/native_shader_backend.cpp"
using namespace isaac::runtime;
std::vector<unsigned char> image(0x600),module(0xb00000);unsigned uploads=0,allocations=0,clears=0,drawClear=0;bool probeOffscreen=false;unsigned detailScopes=0;
std::uintptr_t base(){return reinterpret_cast<std::uintptr_t>(module.data());}
std::size_t field(void* p,unsigned o){std::size_t v{};std::memcpy(&v,static_cast<char*>(p)+o,8);return v;}
void field(void* p,unsigned o,std::size_t v){std::memcpy(static_cast<char*>(p)+o,&v,8);}
void ModelClear(void* p){if(probeOffscreen!=(field(p,0x20)!=0))std::exit(69);++clears;}
void ModelSwap(void* p){field(p,0x60,0);field(p,0x68,0);}
void ModelReserve(void* p,std::size_t bytes){if(field(p,0x58)<bytes){field(p,0x58,bytes);++allocations;}}
void ModelBlend(void* p,int){std::memset(p,0,16);}
void ModelDraw(void* source,NativeBlend,void*,const void*,int count,unsigned stride,const unsigned short* indices,int indexCount){
 if(source!=image.data()||count!=4||indexCount!=6||indices[5]!=3)std::exit(65);
 auto* v=image.data()+0x438;auto* i=image.data()+0x4a8;
 if(clears==drawClear||field(v,0x58)<count*stride||field(i,0x58)<12||field(v,0x60)||field(i,0x60)){
  std::fputs("upload buffer absent, undersized, reused before target synchronization, or offset not reset\n",stderr);std::exit(66);
 }
 drawClear=clears;field(v,0x60,count*stride);field(i,0x60,12);++uploads;
}
void* Resolve(std::uintptr_t a){
 const auto offset=a-base();
 if(offset==0x4f2fa0)return reinterpret_cast<void*>(ModelClear);
 if(offset==0x4f46e4)return reinterpret_cast<void*>(ModelSwap);
 if(offset==0x4f44f4)return reinterpret_cast<void*>(ModelReserve);
 if(offset==0x4ef048)return reinterpret_cast<void*>(ModelBlend);
 if(offset==0x4d18fc)return reinterpret_cast<void*>(ModelDraw);
 std::fprintf(stderr,"unexpected native call %zx\n",offset);std::exit(67);
}
namespace LuaRuntime {std::uintptr_t EngineModuleBase(){return base();}}
namespace isaac::runtime {bool InstallShaderScreenHook(std::uintptr_t)noexcept{return true;}
bool InstallNativeClearProbe(std::uintptr_t)noexcept{return true;}
NativeClearProbeScope::NativeClearProbeScope(bool offscreen)noexcept:previous_(-1),active_(false){probeOffscreen=offscreen;++detailScopes;}
NativeClearProbeScope::~NativeClearProbeScope(){static_cast<void>(previous_);static_cast<void>(active_);}
}
int main(){
 g_VerifiedBase=base();void* graphics=image.data();std::memcpy(module.data()+0xaac6e8,&graphics,8);
 NativeProgram program{image.data()};ShaderTarget source{image.data(),nullptr};float vertices[4*17]{};
 for(unsigned n=0;n<120;++n){field(image.data(),0x20,n%2?1:0);NativeShaderBackend().clear();NativeShaderBackend().draw(source,&program,vertices,4,n%2?68:60);}
 if(uploads!=120||detailScopes!=120||allocations!=3||field(image.data()+0x438,0x58)!=272||field(image.data()+0x4a8,0x58)!=12)return 68;
 return 0;
}
'''

class NativeShaderBufferTests(unittest.TestCase):
    def test_native_draw_prepares_and_reuses_image_upload_buffers(self):
        with tempfile.TemporaryDirectory(prefix='native-shader-buffers-') as folder:
            p=Path(folder)
            for name,text in {'infrastructure/memory/engine_field_access.hpp':MEMORY,
                              'infrastructure/call/engine_call_access.hpp':CALL,
                              'lua_runtime.hpp':'#pragma once\n#include <cstdint>\nnamespace LuaRuntime {std::uintptr_t EngineModuleBase();}',
                              'runtime_constants.hpp':'#pragma once\nconstexpr unsigned kIsaacPointScaleSlotOffset=0;'}.items():
                f=p/name;f.parent.mkdir(parents=True,exist_ok=True);f.write_text(text)
            (p/'test.cpp').write_text(HARNESS)
            r=subprocess.run(['c++','-std=c++20','-O2','-Wall','-Wextra','-Werror','-I'+str(p),'-I'+str(ROOT/'runtime/src'),'-I'+str(ROOT/'runtime/source'),str(p/'test.cpp'),'-o',str(p/'test')],capture_output=True,text=True)
            self.assertEqual(r.returncode,0,r.stdout+r.stderr)
            r=subprocess.run([str(p/'test')],capture_output=True,text=True)
            self.assertEqual(r.returncode,0,r.stdout+r.stderr)
