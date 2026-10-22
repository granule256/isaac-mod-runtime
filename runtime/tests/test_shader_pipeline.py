"""Shader21必须有加载、顶点参数消费、多pass、重载和释放链，不能只登记回调。"""
import subprocess,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
HARNESS=r'''
#include "application/shader/shader_pipeline.hpp"
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <iterator>
#include <string>
using namespace isaac::runtime;
struct Cell{float value;};struct Native{unsigned id;};
Cell screen{};ShaderTarget current{};unsigned creates=0,destroys=0,compiles=0,draws=0,queries=0;
bool Compile(const ShaderProgramView& view,void** out){if(std::strstr(view.vertex,"attribute ")||std::strstr(view.vertex,"uniform mat4 Transform;"))return false;if(!std::strstr(view.vertex,"#version 430")||!std::strstr(view.vertex,"ProjectionMatrix"))return false;if(!std::strstr(view.fragment,"RPlusFragmentColor"))return false;if(std::strstr(view.vertex,"&lt;")||std::strstr(view.vertex,"&amp;"))return false;*out=new Native{std::strcmp(view.name,"__copy_capture")==0?0:++compiles};return true;}
void Destroy(void* p){if(static_cast<Native*>(p)->id)++destroys;delete static_cast<Native*>(p);}
bool Frame(ShaderFrameInfo* f){*f={current,64,32,2,true};return true;}
bool Create(unsigned,unsigned,const char*,ShaderTarget* t){t->image=new Cell{};t->control=nullptr;++creates;return true;}
void Release(ShaderTarget*t){if(t->image)delete static_cast<Cell*>(t->image);*t={};}
void Target(const ShaderTarget&t,bool){current=t;}
void Clear(){(current.image?static_cast<Cell*>(current.image):&screen)->value=0;}
bool Vertices(const ShaderTarget&,const ShaderFrameInfo&,float* v,std::size_t stride){for(unsigned i=0;i<4;++i){for(unsigned j=0;j<14;++j)v[i*stride+j]=float(j);v[i*stride+13]=2;}return true;}
bool unloadInValues=false;
void Draw(const ShaderTarget& source,void* native,const float* v,unsigned count,unsigned bytes){if(unloadInValues&&static_cast<Native*>(native)->id==0){if(bytes!=14*4)std::exit(43);return;} if(count!=4||bytes!=15*4)std::exit(20);for(unsigned i=0;i<4;++i)if(v[i*15+14]!=v[14]||v[i*15+13]!=2)std::exit(21);auto* dest=current.image?static_cast<Cell*>(current.image):&screen;dest->value=static_cast<Cell*>(source.image)->value*v[14];++draws;}
void Drain(){}
bool Values(const ShaderProgramView& p,float* v,std::uintptr_t manager){if(manager!=777)std::exit(22);++queries;if(unloadInValues){UnloadShaderPrograms();if(destroys!=0||!p.name)std::exit(40);return true;}for(unsigned i=0;i<4;++i)v[i*p.strideFloats+14]=std::strcmp(p.name,"Alpha")==0?1.5f:2.f;return true;}
ShaderBackend backend{Compile,Destroy,Frame,Create,Release,Target,Clear,Vertices,Draw,Drain};
int main(int argc,char**argv){
 if(argc==2 && std::strcmp(argv[1],"empty") && std::strcmp(argv[1],"unload") && std::strcmp(argv[1],"type") && std::strcmp(argv[1],"escaped")){std::ifstream file(argv[1]);std::string xml((std::istreambuf_iterator<char>(file)),{});if(!LoadShaderXml("original",xml,backend))return 8;auto stats=ShaderPipelineStatsSnapshot();if(!stats.programs)return 9;UnloadShaderPrograms();return 0;}
 const char* xml=R"xml(<shaders><shader name="Beta"><parameters><param name="Amount" type="float"/></parameters><vertex><![CDATA[attribute vec3 Position; attribute float Amount; varying float OutAmount; uniform mat4 Transform;void main(){gl_Position=Transform*vec4(Position,1.);OutAmount=Amount;}]]></vertex><fragment><![CDATA[varying float OutAmount;void main(){gl_FragColor=vec4(OutAmount);}]]></fragment></shader><shader name="Alpha"><parameters><param name="Amount" type="float"/></parameters><vertex><![CDATA[attribute vec3 Position; attribute float Amount; varying float OutAmount; uniform mat4 Transform;void main(){gl_Position=Transform*vec4(Position,1.);OutAmount=Amount;}]]></vertex><fragment><![CDATA[varying float OutAmount;void main(){gl_FragColor=vec4(OutAmount);}]]></fragment></shader></shaders>)xml";
 if(argc==2&&!std::strcmp(argv[1],"escaped")){
 const char* escaped="<shaders><shader name=\"Alpha\"><parameters/><vertex>uniform mat4 Transform;attribute vec3 Position;void main(){if(1. &lt; 2. &amp;&amp; true)gl_Position=Transform*vec4(Position,1.);}</vertex><fragment>void main(){gl_FragColor=vec4(1.);}</fragment></shader></shaders>";
 if(!LoadShaderXml("mod",escaped,backend))return 50;UnloadShaderPrograms();return 0;
 }
 if(argc==2&&!std::strcmp(argv[1],"empty")){
 if(!LoadShaderXml("mod","<shaders/>",backend))return 30;
 std::string zero=xml;auto start=zero.find("<parameters>");auto end=zero.find("</parameters>",start);zero.replace(start,end-start+13,"<parameters/>");
 if(!LoadShaderXml("mod",zero,backend))return 31;UnloadShaderPrograms();return 0;
 }
 if(argc==2&&!std::strcmp(argv[1],"type")){
 std::string bad=xml;bad.replace(bad.find("type=\"float\""),12,"type=\"mat3\"");
 if(LoadShaderXml("mod",bad,backend)||ShaderPipelineStatsSnapshot().error!=ShaderPipelineError::Type||compiles)return 32;return 0;
 }
 if(!LoadShaderXml("mod",xml,backend))return 1;SetShaderValueProvider(Values);
 if(argc==2&&!std::strcmp(argv[1],"unload")){
 unloadInValues=true;if(!BeginShaderFrame()||!CaptureShaderScreenTarget())return 41;FinishShaderFrame(777);
 if(destroys||current.image||draws)return 42;AbortShaderFrame();if(destroys!=2||ShaderPipelineStatsSnapshot().programs)return 44;return 0;
 }
 if(!BeginShaderFrame()||!CaptureShaderScreenTarget())return 2;static_cast<Cell*>(current.image)->value=10;FinishShaderFrame(777);if(screen.value!=30||draws!=2||queries!=2||creates!=2||current.image)return 3;
 if(!BeginShaderFrame()||!CaptureShaderScreenTarget())return 4;static_cast<Cell*>(current.image)->value=20;FinishShaderFrame(777);if(screen.value!=60||creates!=2)return 5;
 if(!LoadShaderXml("mod",xml,backend)||destroys!=2||ShaderPipelineStatsSnapshot().programs!=2)return 6;
 if(LoadShaderXml("mod","<shaders><shader></shaders>",backend)||ShaderPipelineStatsSnapshot().programs!=2)return 7;
 UnloadShaderPrograms();if(destroys!=4||ShaderPipelineStatsSnapshot().programs!=0||BeginShaderFrame())return 10;return 0;
}
'''
class ShaderPipelineTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory(prefix='isaac-shader-')
  src=Path(cls.tmp.name)/'h.cpp';src.write_text(HARNESS)
  cls.exe=Path(cls.tmp.name)/'shader'
  r=subprocess.run(['c++','-std=c++20','-O2','-Wall','-Wextra','-Werror','-I'+str(ROOT/'runtime/src'),str(src),str(ROOT/'runtime/src/application/shader/shader_pipeline.cpp'),'-o',str(cls.exe)],capture_output=True,text=True)
  if r.returncode:raise AssertionError(r.stdout+r.stderr)
 @classmethod
 def tearDownClass(cls):cls.tmp.cleanup()
 def test_xml_parameter_vertices_multipass_reuse_reload_and_unload(self):
  r=subprocess.run([str(self.exe)],capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
 def test_original_stageapi_xml_through_loader_and_native_compiler_consumer(self):
  p=Path('/Users/kelinls/code/github/isaac mod/analysis/mod-corpus/BOIStageAPI15/content/shaders.xml')
  r=subprocess.run([str(self.exe),str(p)],capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stdout+r.stderr)

 def test_empty_declarations_are_valid(self):
  r=subprocess.run([str(self.exe),'empty'],capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
 def test_invalid_parameter_type_is_reported_before_compilation(self):
  r=subprocess.run([str(self.exe),'type'],capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
 def test_unload_during_value_callback_keeps_program_alive_until_callback_returns(self):
  r=subprocess.run([str(self.exe),'unload'],capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stdout+r.stderr)

 def test_xml_escaped_glsl_reaches_native_compiler_decoded(self):
  r=subprocess.run([str(self.exe),'escaped'],capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
