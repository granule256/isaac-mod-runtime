"""使用实际native后端，验证全屏四顶点通过原生反向深度和逻辑坐标投影。"""
import subprocess,tempfile,unittest
from pathlib import Path
from .test_native_shader_buffers import ROOT,MEMORY,CALL,HARNESS

EXTRA=r'''unsigned ModelWidth(void*){return 1280;}
unsigned ModelHeight(void*){return 720;}
'''
EXTRA+=r'''void ModelDrawWinding(void* source,NativeBlend blend,void* shader,const void* vertices,int count,unsigned stride,const unsigned short* indices,int indexCount){
 ModelDraw(source,blend,shader,vertices,count,stride,indices,indexCount);
 const auto* bytes=static_cast<const unsigned char*>(vertices);
 for(int i=0;i<indexCount;i+=3){const auto* a=reinterpret_cast<const float*>(bytes+indices[i]*stride);const auto* b=reinterpret_cast<const float*>(bytes+indices[i+1]*stride);const auto* c=reinterpret_cast<const float*>(bytes+indices[i+2]*stride);const float area=(b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0]);if(!(area<0)){std::fputs("fullscreen triangle faces away from native front face and is culled\n",stderr);std::exit(64);}}
}
'''
MAIN=r'''int main(int argc,char** argv){
 g_VerifiedBase=base();ShaderTarget source{image.data(),nullptr};ShaderFrameInfo frame{};frame.width=1280;frame.height=720;frame.scale=3;frame.projectionWidth=1280.f/3;frame.projectionHeight=240;
 float vertices[4*17]{};if(!NativeShaderBackend().standardVertices(source,frame,vertices,17))return 60;
 if(argc==2 && !std::strcmp(argv[1],"winding")){void* graphics=image.data();std::memcpy(module.data()+0xaac6e8,&graphics,8);NativeProgram program{image.data()};NativeShaderBackend().clear();NativeShaderBackend().draw(source,&program,vertices,4,17*sizeof(float));return 0;}
 if(argc==1){for(unsigned i=0;i<4;++i){const float clipDepth=-0.001f*vertices[i*17+2];if(!(clipDepth>0 && clipDepth<=1)){std::fputs("fullscreen vertex fails native GREATER depth test after zero clear\n",stderr);return 61;}}}
 else {const float expected[4][2]={{0,0},{1280.f/3,0},{1280.f/3,240},{0,240}};for(unsigned i=0;i<4;++i)for(unsigned j=0;j<2;++j)if(vertices[i*17+j]!=expected[i][j]){std::fputs("fullscreen position uses pixels instead of projection points\n",stderr);return 62;}}
 for(unsigned i=0;i<4;++i){auto* v=vertices+i*17;if(v[9]!=1280||v[10]!=720||v[11]!=1280||v[12]!=720||v[13]!=3)return 63;}
 return 0;
}
'''
class NativeShaderVertexTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory(prefix='native-shader-vertices-');p=Path(cls.tmp.name)
  for name,text in {'infrastructure/memory/engine_field_access.hpp':MEMORY,'infrastructure/call/engine_call_access.hpp':CALL,'lua_runtime.hpp':'#pragma once\n#include <cstdint>\nnamespace LuaRuntime {std::uintptr_t EngineModuleBase();}','runtime_constants.hpp':'#pragma once\nconstexpr unsigned kIsaacPointScaleSlotOffset=0;'}.items():
   f=p/name;f.parent.mkdir(parents=True,exist_ok=True);f.write_text(text)
  source=HARNESS.split('int main(){')[0].replace('void* Resolve(std::uintptr_t a){',EXTRA+'\nvoid* Resolve(std::uintptr_t a){').replace('const auto offset=a-base();','const auto offset=a-base();\n if(offset==0x4eefe0||offset==0x4eefcc)return reinterpret_cast<void*>(ModelWidth);\n if(offset==0x4eefe8||offset==0x4eefd4)return reinterpret_cast<void*>(ModelHeight);')+MAIN
  source=source.replace('reinterpret_cast<void*>(ModelDraw);','reinterpret_cast<void*>(ModelDrawWinding);')
  (p/'test.cpp').write_text(source);cls.exe=p/'test'
  r=subprocess.run(['c++','-std=c++20','-O2','-Wall','-Wextra','-Werror','-I'+str(p),'-I'+str(ROOT/'runtime/src'),'-I'+str(ROOT/'runtime/source'),str(p/'test.cpp'),'-o',str(cls.exe)],capture_output=True,text=True)
  if r.returncode:raise AssertionError(r.stdout+r.stderr)
 @classmethod
 def tearDownClass(cls):cls.tmp.cleanup()
 def test_fullscreen_depth_survives_native_reverse_depth_clear(self):
  r=subprocess.run([str(self.exe)],capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
 def test_fullscreen_positions_use_points_and_keep_texture_sizes_in_pixels(self):
  r=subprocess.run([str(self.exe),'points'],capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stdout+r.stderr)

 def test_fullscreen_triangle_winding_matches_native_front_face(self):
  r=subprocess.run([str(self.exe),'winding'],capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
