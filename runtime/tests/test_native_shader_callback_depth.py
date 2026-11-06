"""Execute the native callback preparation and validate its clear/rebind ABI."""
import subprocess
import tempfile
import unittest
from pathlib import Path
from .test_native_shader_buffers import ROOT, MEMORY, CALL, HARNESS

EXTRA = r'''
static std::vector<unsigned char> graphicsBytes(0x6000),commandBytes(0x100);
static unsigned sequence=0,color=0x12345678,stencil=0xa5;
static float depth=1;
static bool colorBound=true,viewportRestored=true;
static void* command(){return commandBytes.data();}
static void* depthView(){return graphicsBytes.data()+0x37f8;}
void ModelFlushPending(void* graphics){
 if(graphics!=graphicsBytes.data()||sequence!=0)std::exit(71);sequence=1;
}
void ModelClearDepth(void* cmd,const void* view,float value,int clearStencil,unsigned mode,const void* range){
 if(cmd!=command()||view!=depthView()||value!=0||clearStencil!=0||mode!=1||range||sequence!=1)std::exit(72);
 depth=value; // Independently verified mode 1 has a zero stencil write mask.
 colorBound=false;viewportRestored=false;sequence=2;
}
void ModelSetTargets(void* cmd,int count,const void* const* views,const void* view){
 if(cmd!=command()||count!=1||views[0]!=image.data()+0x530||view!=depthView()||sequence!=2)std::exit(73);
 colorBound=true;sequence=3;
}
void ModelViewport(void* cmd,const void* state){
 if(cmd!=command()||state!=image.data()+0x578||sequence!=3)std::exit(74);
 viewportRestored=true;sequence=4;
}
template<class Backend>bool PrepareCallbacks(const Backend&b){
 if constexpr(requires{b.prepareCallbackDraw;}){if(!b.prepareCallbackDraw)return false;b.prepareCallbackDraw();return true;}
 return false;
}
'''
MAIN = r'''
int main(){
 g_VerifiedBase=base();void* graphics=graphicsBytes.data();std::memcpy(module.data()+0xaac6e8,&graphics,8);
 field(graphics,0x20,reinterpret_cast<std::uintptr_t>(image.data()));
 field(graphics,0x3a30,reinterpret_cast<std::uintptr_t>(command()));
 graphicsBytes[0x5c1b]=1;
 if(!PrepareCallbacks(NativeShaderBackend())){std::fputs("missing native callback depth preparation\n",stderr);return 70;}
 if(sequence!=4||depth!=0||color!=0x12345678||stencil!=0xa5||!colorBound||!viewportRestored||graphicsBytes[0x5c1b]!=1||clears)return 75;
 return 0;
}
'''


class NativeShaderCallbackDepthTests(unittest.TestCase):
 def test_only_depth_is_cleared_and_render_target_state_is_restored(self):
  with tempfile.TemporaryDirectory(prefix='native-shader-callback-depth-') as folder:
   p=Path(folder)
   for name,text in {'infrastructure/memory/engine_field_access.hpp':MEMORY,
       'infrastructure/call/engine_call_access.hpp':CALL,
       'lua_runtime.hpp':'#pragma once\n#include <cstdint>\nnamespace LuaRuntime {std::uintptr_t EngineModuleBase();}',
       'runtime_constants.hpp':'#pragma once\nconstexpr unsigned kIsaacPointScaleSlotOffset=0;'}.items():
    target=p/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_text(text)
   source=HARNESS.split('int main(){',1)[0].replace('void* Resolve(std::uintptr_t a){',EXTRA+'\nvoid* Resolve(std::uintptr_t a){')+MAIN
   source=source.replace('const auto offset=a-base();','''const auto offset=a-base();
 if(offset==0x4ef7dc)return reinterpret_cast<void*>(ModelFlushPending);
 if(offset==0x6813f0)return reinterpret_cast<void*>(ModelClearDepth);
 if(offset==0x681410)return reinterpret_cast<void*>(ModelSetTargets);
 if(offset==0x6813d0)return reinterpret_cast<void*>(ModelViewport);''')
   cpp=p/'test.cpp';cpp.write_text(source);binary=p/'test'
   r=subprocess.run(['c++','-std=c++20','-O2','-Wall','-Wextra','-Werror','-I'+str(p),
       '-I'+str(ROOT/'runtime/src'),'-I'+str(ROOT/'runtime/source'),str(cpp),'-o',str(binary)],capture_output=True,text=True)
   self.assertEqual(r.returncode,0,r.stdout+r.stderr)
   r=subprocess.run([str(binary)],capture_output=True,text=True)
   self.assertEqual(r.returncode,0,r.stdout+r.stderr)
