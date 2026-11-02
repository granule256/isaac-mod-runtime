"""Exercise real shader pass selection with an instrumented graphics backend.

Set ISAAC_TEST_SHADER_FIXTURE to an original Fiend shaders.xml to additionally
exercise its complete-source fingerprint without redistributing the mod source.
"""
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
HARNESS = r'''
#include "application/shader/shader_pipeline.hpp"
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <iterator>
#include <string>
using namespace isaac::runtime;
unsigned queries=0,draws=0,actual=0;bool unloadInValues=false;
float amount=0;bool changeColor=false,changeOne=false,failValues=false;
std::string wanted="effect";ShaderTarget current{};
bool Compile(const ShaderProgramView&v,void**p){*p=new std::string(v.name);return true;}
void Destroy(void*p){delete static_cast<std::string*>(p);}
bool Frame(ShaderFrameInfo*f){*f={{},320,180,1,true,320,180};return true;}
bool Create(unsigned,unsigned,const char*,ShaderTarget*t){t->image=new int(1);return true;}
void Release(ShaderTarget*t){delete static_cast<int*>(t->image);*t={};}
void Target(const ShaderTarget&t,bool){current=t;}
void Clear(){}
bool Vertices(const ShaderTarget&,const ShaderFrameInfo&,float*p,std::size_t stride){
 for(unsigned i=0;i<4;++i)for(unsigned j=0;j<14;++j)p[i*stride+j]=j>=3&&j<7?1.f:float(j);
 return true;
}
void Draw(const ShaderTarget&,void*n,const float*,unsigned,unsigned){++draws;if(*static_cast<std::string*>(n)==wanted)++actual;}
void Drain(){}
bool Values(const ShaderProgramView&v,float*p,std::uintptr_t){
 ++queries;
 for(unsigned i=0;i<4;++i){
  for(std::size_t j=0;j<v.parameterCount;++j)if(!std::strcmp(v.parameters[j].name,"ActiveIn"))
   p[i*v.strideFloats+v.parameters[j].offset]=changeOne&&i==3?1.f:amount;
  if(changeColor)p[i*v.strideFloats+3]=.5f;
 }
 if(unloadInValues)UnloadShaderPrograms();
 return !failValues;
}
ShaderBackend backend{Compile,Destroy,Frame,Create,Release,Target,Clear,Vertices,Draw,Drain};
int main(int argc,char**argv){
 std::string xml="<shaders><shader name='effect'><vertex>void main(){gl_Position=vec4(1.);}</vertex><fragment>void main(){gl_FragColor=vec4(.5);}</fragment></shader></shaders>";
 if(argc>1){std::ifstream f(argv[1]);xml={std::istreambuf_iterator<char>(f),{}};}
 if(argc>2)wanted=argv[2];if(argc>3)amount=std::stof(argv[3]);
 if(argc>4){changeColor=!std::strcmp(argv[4],"color");changeOne=!std::strcmp(argv[4],"one");failValues=!std::strcmp(argv[4],"fail");}
 if(!LoadShaderXml("fixture",xml,backend))return 2;
 SetShaderValueProvider(Values);
 if(!BeginShaderFrame()||!CaptureShaderScreenTarget())return 3;
 FinishShaderFrame(0);
 std::printf("%u %u %u\n",queries,draws,actual);UnloadShaderPrograms();return 0;
}
'''
COPY_VERTEX = '''attribute vec3 Position; attribute vec4 Color; attribute vec2 TexCoord;
varying vec4 Color0; varying vec2 TexCoord0; uniform mat4 Transform;
void main(void) {Color0=Color;TexCoord0=TexCoord;gl_Position=Transform*vec4(Position.xyz,1.0);}'''
COPY_FRAGMENT = '''varying lowp vec4 Color0; varying mediump vec2 TexCoord0;
uniform sampler2D Texture0;
void main(void) {vec4 col=texture2D(Texture0,TexCoord0);gl_FragColor=Color0*col;}'''


class ShaderPipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory(prefix='shader-passes-')
        cls.work = Path(cls.folder.name)
        cpp = cls.work/'pipeline.cpp';cpp.write_text(HARNESS)
        cls.exe = cls.work/'pipeline'
        cmd = ['c++','-std=c++20','-O2','-Wall','-Wextra','-Werror',
               '-I'+str(ROOT/'runtime/src'),str(cpp),
               str(ROOT/'runtime/src/application/shader/shader_pipeline.cpp'),'-o',str(cls.exe)]
        result=subprocess.run(cmd,capture_output=True,text=True)
        if result.returncode:raise AssertionError(result.stdout+result.stderr)

    @classmethod
    def tearDownClass(cls):
        cls.folder.cleanup()

    def run_shader(self, root, amount='0', mode=''):
        path=self.work/'input.xml';ET.ElementTree(root).write(path,encoding='unicode')
        name=root.find('shader').attrib['name']
        result=subprocess.run([str(self.exe),str(path),name,str(amount),mode],capture_output=True,text=True,timeout=5)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        return tuple(map(int,result.stdout.split()))

    def copy(self):
        root=ET.Element('shaders');s=ET.SubElement(root,'shader',name='renamed-copy')
        ET.SubElement(s,'vertex').text=COPY_VERTEX;ET.SubElement(s,'fragment').text=COPY_FRAGMENT
        return root

    def fiend(self):
        path=os.environ.get('ISAAC_TEST_SHADER_FIXTURE')
        if not path:self.skipTest('original shader fixture not configured')
        return ET.parse(path).getroot()

    def test_copy_variant_keeps_callback_but_skips_effect_draw(self):
        self.assertEqual(self.run_shader(self.copy()),(1,1,0))

    def test_unterminated_comment_falls_back_without_hanging(self):
        for stage in ['vertex', 'fragment']:
            with self.subTest(stage=stage):
                root=self.copy();root.find('shader/'+stage).text += '\n/* truncated'
                self.assertEqual(self.run_shader(root),(1,1,1))

    def test_copy_changes_and_callback_failure_keep_effect_draw(self):
        for mode in ['color','fail']:
            with self.subTest(mode=mode):self.assertEqual(self.run_shader(self.copy(),mode=mode),(1,1,1))
        root=self.copy();root.find('shader/fragment').text=COPY_FRAGMENT.replace('Color0*col','Color0*col*0.5')
        self.assertEqual(self.run_shader(root),(1,1,1))

    def test_inactive_fixture_preserves_active_and_modified_cases(self):
        root=self.fiend();self.assertEqual(self.run_shader(root),(1,1,0))
        for value in ['0.5','1.5','1.75','nan']:
            with self.subTest(value=value):self.assertEqual(self.run_shader(root,value),(1,1,1))
        for mode in ['color','one','fail']:
            with self.subTest(mode=mode):self.assertEqual(self.run_shader(root,mode=mode),(1,1,1))
        root.find('shader').set('name','another-name')
        self.assertEqual(self.run_shader(root),(1,1,0))
        root.find('shader/fragment').text += '\n// formatting only\n'
        self.assertEqual(self.run_shader(root),(1,1,0))
        root.find('shader/fragment').text=root.find('shader/fragment').text.replace('gl_FragColor = Color;','gl_FragColor = Color * 0.5;')
        self.assertEqual(self.run_shader(root),(1,1,1))

    def test_fixture_parameter_order_and_interface_validation(self):
        root=self.fiend();params=root.find('shader/parameters');active=params.find("param[@name='ActiveIn']")
        params.remove(active);params.append(active)
        self.assertEqual(self.run_shader(root),(1,1,0))
        self.assertEqual(self.run_shader(root,'1.5'),(1,1,1))
        active.set('type','vec2')
        self.assertEqual(self.run_shader(root),(1,1,1))
