"""实际原生FrameInfo/Standard必须以引擎投影宽度保持逐像素中心不偏移。"""
import subprocess,tempfile,unittest
from pathlib import Path
from .test_native_shader_buffers import ROOT,MEMORY,CALL,HARNESS

EXTRA=r'''
unsigned windowWidth=1280,windowHeight=720;
float pointScale=3,projectionWidth=426,projectionHeight=240;
void ModelGetTarget(void*,void** image,bool* flag){*image=nullptr;*flag=true;}
unsigned ModelWidth(void*){return 1280;}
unsigned ModelHeight(void*){return 720;}
'''
MAIN=r'''
int main(){
 g_VerifiedBase=base();void* graphics=image.data();std::memcpy(module.data()+0xaac6e8,&graphics,8);
 auto slot=[](unsigned offset,void* pointer){std::memcpy(module.data()+offset,&pointer,8);};
 slot(0,&pointScale);slot(0xaac7d0,&windowWidth);slot(0xaac7d8,&windowHeight);
 slot(0xaac7c0,&projectionWidth);slot(0xaac7c8,&projectionHeight);
 ShaderFrameInfo frame{};if(!NativeShaderBackend().frameInfo(&frame))return 70;
 ShaderTarget source{image.data(),nullptr};float vertices[4*17]{};
 if(!NativeShaderBackend().standardVertices(source,frame,vertices,17))return 71;
 // Native Shader::bind uses 2/projectionWidth. Sample centers must map 1:1,
 // including x=426/853 where the user observed the strongest distortion.
 const float right=vertices[17];
 for(float pixel:{0.f,426.f,853.f,1279.f}){
  const float sourcePixel=(pixel+0.5f)*projectionWidth/right-0.5f;
  if(std::fabs(sourcePixel-pixel)>0.0002f){
   std::fprintf(stderr,"pixel %.0f samples %.6f: fullscreen width %.7f differs from native projection %.0f\n",pixel,sourcePixel,right,projectionWidth);return 72;
  }
 }
 for(unsigned i=0;i<4;++i){auto* v=vertices+i*17;if(v[9]!=1280||v[10]!=720||v[11]!=1280||v[12]!=720||v[13]!=3)return 73;}
}
'''
class NativeShaderPixelAlignmentTests(unittest.TestCase):
 def test_fractional_pixel_scale_uses_exact_native_projection(self):
  with tempfile.TemporaryDirectory(prefix='isaac-shader-pixel-')as tmp:
   p=Path(tmp)
   for name,text in {'infrastructure/memory/engine_field_access.hpp':MEMORY,'infrastructure/call/engine_call_access.hpp':CALL,'lua_runtime.hpp':'#pragma once\n#include <cstdint>\nnamespace LuaRuntime{std::uintptr_t EngineModuleBase();}','runtime_constants.hpp':'#pragma once\nconstexpr unsigned kIsaacPointScaleSlotOffset=0;'}.items():
    f=p/name;f.parent.mkdir(parents=True,exist_ok=True);f.write_text(text)
   source='#include <cmath>\n#include <initializer_list>\n'+HARNESS.split('int main(){')[0]
   source=source.replace('void* Resolve(std::uintptr_t a){',EXTRA+'\nvoid* Resolve(std::uintptr_t a){').replace('const auto offset=a-base();','const auto offset=a-base();\n if(offset==0x4ef724)return reinterpret_cast<void*>(ModelGetTarget);\n if(offset==0x4eefe0||offset==0x4eefcc)return reinterpret_cast<void*>(ModelWidth);\n if(offset==0x4eefe8||offset==0x4eefd4)return reinterpret_cast<void*>(ModelHeight);')+MAIN
   (p/'test.cpp').write_text(source)
   r=subprocess.run(['c++','-std=c++20','-O2','-Wall','-Wextra','-Werror','-I'+str(p),'-I'+str(ROOT/'runtime/src'),'-I'+str(ROOT/'runtime/source'),str(p/'test.cpp'),'-o',str(p/'test')],capture_output=True,text=True)
   self.assertEqual(r.returncode,0,r.stdout+r.stderr)
   r=subprocess.run([str(p/'test')],capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
