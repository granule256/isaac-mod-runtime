"""21经完整PC回调表取得参数，并进入真正的shader顶点绘制消费者。"""
import subprocess,tempfile,unittest,re
from pathlib import Path
from .test_support import build_lua_harness
ROOT=Path(__file__).resolve().parents[2]
SOURCE=ROOT/'runtime/source'
MAIN=r'''
#include "lua_runtime.hpp"
#include "application/shader/shader_pipeline.hpp"
#include <string>
using namespace isaac::runtime;
unsigned shaderQueries=0,shaderDraws=0;bool shaderValid=true;ShaderTarget target{};float lastAmount=0;
bool Compile(const ShaderProgramView& v,void** p){*p=const_cast<char*>(v.name);return true;}
void Destroy(void*){}
bool Frame(ShaderFrameInfo* f){*f={{},32,16,2,true};return true;}
bool Create(unsigned,unsigned,const char*,ShaderTarget* t){t->image=new unsigned(1);t->control=nullptr;return true;}
void Release(ShaderTarget*t){delete static_cast<unsigned*>(t->image);*t={};}
void Target(const ShaderTarget&t,bool){target=t;}
void Clear(){}
bool Vertices(const ShaderTarget&,const ShaderFrameInfo&,float* p,std::size_t stride){for(unsigned i=0;i<4;++i)for(unsigned j=0;j<14;++j)p[i*stride+j]=float(j);return true;}
void Draw(const ShaderTarget&,void*,const float*p,unsigned n,unsigned bytes){if(n!=4||bytes!=18*4)shaderValid=false;for(unsigned i=0;i<4;++i){if(p[i*18+14]!=p[14]||p[i*18+15]!=1||p[i*18+16]!=2||p[i*18+17]!=3)shaderValid=false;}lastAmount=p[14];++shaderDraws;}
void Drain(){}
int main(){
 const char* xml=R"xml(<shaders><shader name="Actual"><parameters><param name="Amount" type="float"/><param name="PositionIn" type="vec3"/></parameters><vertex><![CDATA[attribute vec3 Position; uniform mat4 Transform;void main(){gl_Position=Transform*vec4(Position,1.);}]]></vertex><fragment><![CDATA[void main(){gl_FragColor=vec4(1.);}]]></fragment></shader></shaders>)xml";
 ShaderBackend port{Compile,Destroy,Frame,Create,Release,Target,Clear,Vertices,Draw,Drain};if(!LoadShaderXml("test",xml,port))return 1;
 std::string script=R"lua(local m=RegisterMod('shader-native-consumer',1);_shader={first=0,second=0,fields=0};m:AddCallback(21,function(_,name)assert(name=='Actual');_shader.first=_shader.first+1;return setmetatable({PositionIn={1,2,3}},{__index=function(_,key)assert(key=='Amount');_shader.fields=_shader.fields+1;return 2.5 end})end);m:AddCallback(21,function()_shader.second=_shader.second+1;return {Amount=99}end))lua";
 if(LuaRuntime::InitializeFromBuffer(script.data(),script.size(),"@shader-lua.lua")!=LuaRuntime::LuaInitResult::Success)return 2;
 if(!BeginShaderFrame()||!CaptureShaderScreenTarget())return 3;FinishShaderFrame(777);if(LuaRuntime::TakeCallbackError()||!shaderValid||shaderDraws!=1||lastAmount!=2.5||target.image)return 4;
 double first{},second{},fields{};if(LuaRuntime::ReadLuaTableNumber("_shader","first",&first)||LuaRuntime::ReadLuaTableNumber("_shader","second",&second)||LuaRuntime::ReadLuaTableNumber("_shader","fields",&fields))return 5;
 if(first!=1||second!=0||fields!=4)return 6;UnloadShaderPrograms();return 0;
}
'''
class ShaderLuaConsumerTests(unittest.TestCase):
 def test_pc_callback_table_values_reach_four_native_vertices(self):
  with tempfile.TemporaryDirectory(prefix='isaac-shader-lua-') as d:
   exe=build_lua_harness(source_root=SOURCE,workdir=Path(d),harness_source=MAIN)
   r=subprocess.run([str(exe)],capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
