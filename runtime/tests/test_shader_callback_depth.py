"""Shader callbacks must draw above the captured image without erasing its color.

The software backend models reverse depth with GREATER: a fullscreen pass has
already written the depth used by the next first sprite. Native sprite batches
advance depth for later quads, explaining why only the first one disappears.
"""
import subprocess
import tempfile
import unittest
from pathlib import Path
from .test_shader_pipeline import ROOT, COPY_VERTEX, COPY_FRAGMENT

HARNESS = r'''
#include "application/shader/shader_pipeline.hpp"
#include <cassert>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <iterator>
#include <string>
#include <vector>
using namespace isaac::runtime;
struct Image {unsigned color=0,stencil=0xa5;float depth=0;};
struct Batch {Image* target;unsigned color;float depth;};
static Image screen;
static Image* current=&screen;
static std::vector<Batch> pending;
static float nextDepth=1;
static bool depthEnabled=true,failed=false;
static unsigned queries=0,prepares=0,draws=0,expected=3;
static std::string mode,overlay;
static std::string order;
bool Compile(const ShaderProgramView&v,void**out){*out=new std::string(v.name);return true;}
void Destroy(void*p){delete static_cast<std::string*>(p);}
bool Frame(ShaderFrameInfo*out){*out={{&screen,nullptr},320,180,1,true,320,180};return true;}
bool Create(unsigned,unsigned,const char*,ShaderTarget*out){*out={new Image,nullptr};return true;}
void Release(ShaderTarget*t){delete static_cast<Image*>(t->image);*t={};}
void Target(const ShaderTarget&t,bool){current=t.image?static_cast<Image*>(t.image):&screen;}
void Clear(){current->color=0;current->depth=0;}
bool Vertices(const ShaderTarget&,const ShaderFrameInfo&,float*out,std::size_t stride){
 for(unsigned i=0;i<4;++i)for(unsigned j=0;j<14;++j)out[i*stride+j]=j>=3&&j<7?1.f:float(j);
 return true;
}
void Flush(){
 for(const auto& b:pending)if(!depthEnabled||b.depth>b.target->depth){b.target->color|=b.color;b.target->depth=b.depth;}
 pending.clear();nextDepth=1;
}
void Prepare(){
 // Submit old scene batches before clearing depth, preserving color and stencil.
 Flush();const auto color=current->color,stencil=current->stencil;const bool enabled=depthEnabled;
 current->depth=0;++prepares;
 assert(current->color==color&&current->stencil==stencil&&depthEnabled==enabled);
}
void Draw(const ShaderTarget&source,void*,const float*,unsigned,unsigned){
 assert(pending.empty());current->color=static_cast<Image*>(source.image)->color;
 current->depth=1;++draws;
}
void Drain(){}
bool Values(const ShaderProgramView&v,float*,std::uintptr_t){
 ++queries;order+=v.name;order+=';';
 if(overlay==v.name){
  pending.push_back({current,4,nextDepth});nextDepth+=.01f;
  pending.push_back({current,8,nextDepth});nextDepth+=.01f;
  expected|=12;
  if(mode=="cleanup")UnloadShaderPrograms();
  if(mode=="fail"){failed=true;return false;}
 }
 return true;
}
template<class Backend>void BindPrepare(Backend&b){if constexpr(requires{b.prepareCallbackDraw;})b.prepareCallbackDraw=Prepare;}
int main(int argc,char**argv){
 assert(argc==4);mode=argv[1];overlay=argv[3];
 std::ifstream file(argv[2]);std::string xml{std::istreambuf_iterator<char>(file),{}};
 ShaderBackend backend{Compile,Destroy,Frame,Create,Release,Target,Clear,Vertices,Draw,Drain,Flush};BindPrepare(backend);
 if(!LoadShaderXml("depth fixture",xml,backend))return 1;
 SetShaderValueProvider(mode=="no_values"?nullptr:Values);
 assert(BeginShaderFrame()&&CaptureShaderScreenTarget());
 current->color=1;current->depth=1;
 // A still-pending scene batch must be committed before the depth reset.
 pending.push_back({current,2,1.005f});nextDepth=1;
 FinishShaderFrame(0);
 const auto stats=ShaderPipelineStatsSnapshot();
 if(screen.color!=expected){std::fprintf(stderr,"first callback quad lost: color=%u expected=%u prepares=%u\n",screen.color,expected,prepares);return 2;}
 if(current!=&screen||!pending.empty()||screen.stencil!=0xa5||!depthEnabled)return 3;
 if(prepares!=(mode=="no_values"?0:queries)||stats.valueFailures!=(failed?1:0))return 4;
 if(mode=="cleanup"){if(order!="a-effect;")return 5;}
 else if(overlay=="a-effect"&&order!="a-effect;")return 6;
 else if(overlay=="b-effect"&&order!="a-effect;b-effect;c-effect;")return 7;
 else if(overlay=="b-copy"&&order!="a-effect;b-copy;c-effect;")return 8;
 else if(overlay=="z-copy"&&order!="a-effect;z-copy;")return 9;
 else if(mode=="no_values"&&queries)return 10;
 if(overlay=="b-copy"&&draws!=2)return 11;
 if(overlay=="z-copy"&&draws!=2)return 12;
 UnloadShaderPrograms();if(ShaderPipelineStatsSnapshot().programs)return 13;
 return 0;
}
'''


class ShaderCallbackDepthTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory(prefix='shader-callback-depth-');cls.work=Path(cls.tmp.name)
  cpp=cls.work/'depth.cpp';cpp.write_text(HARNESS);cls.binary=cls.work/'depth'
  r=subprocess.run(['c++','-std=c++20','-O2','-Wall','-Wextra','-Werror','-I'+str(ROOT/'runtime/src'),
      str(cpp),str(ROOT/'runtime/src/application/shader/shader_pipeline.cpp'),'-o',str(cls.binary)],capture_output=True,text=True)
  if r.returncode:raise AssertionError(r.stdout+r.stderr)
 @classmethod
 def tearDownClass(cls):cls.tmp.cleanup()
 def check(self,mode,names,overlay):
  shaders=[]
  for name in names:
   vertex=COPY_VERTEX if name.endswith('copy') else 'void main(){gl_Position=vec4(1.);}'
   fragment=COPY_FRAGMENT if name.endswith('copy') else 'void main(){gl_FragColor=vec4(.5);}'
   shaders.append(f'<shader name="{name}"><vertex><![CDATA[{vertex}]]></vertex><fragment><![CDATA[{fragment}]]></fragment></shader>')
  path=self.work/'input.xml';path.write_text('<shaders>'+''.join(shaders)+'</shaders>')
  r=subprocess.run([str(self.binary),mode,str(path),overlay],capture_output=True,text=True)
  self.assertEqual(r.returncode,0,r.stdout+r.stderr)
 def test_first_provider_preserves_scene_and_first_quad(self):self.check('first',['a-effect'],'a-effect')
 def test_middle_provider_keeps_pass_order_and_first_quad(self):self.check('middle',['a-effect','b-effect','c-effect'],'b-effect')
 def test_identity_and_final_copy_preserve_callback_draws(self):
  self.check('identity',['a-effect','b-copy','c-effect'],'b-copy')
  self.check('identity',['a-effect','z-copy'],'z-copy')
 def test_callback_failure_and_deferred_unload_keep_draws(self):
  self.check('fail',['a-effect'],'a-effect');self.check('cleanup',['a-effect','b-effect'],'a-effect')
 def test_absent_value_provider_keeps_optional_backend_behavior(self):self.check('no_values',['a-effect'],'')
