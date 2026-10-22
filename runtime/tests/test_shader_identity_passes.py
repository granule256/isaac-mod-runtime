"""执行生产pipeline和作者真实XML，验证合并后HUD批次、效果及回调顺序仍一致。"""
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ORIGINAL = ROOT / "analysis/mod-corpus/BOIStageAPI15/content/shaders.xml"
HARNESS = r'''
#include "application/shader/shader_pipeline.hpp"
#include <cmath>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <iterator>
#include <limits>
#include <string>
#include <vector>
using namespace isaac::runtime;
struct Image {float value=0;};
struct Native {unsigned kind;};
Image screen{};ShaderTarget current{};
unsigned draws=0,clears=0,queries=0,flushes=0,destroys=0;
std::vector<unsigned> drawn;
std::string mode;
bool Compile(const ShaderProgramView& v,void** out){
 unsigned kind=!std::strcmp(v.name,"__copy_capture")?0:
   std::strstr(v.fragment,"Color * 2.0")?3:
   std::strstr(v.fragment,"OutPixelAmount")?2:1;
 *out=new Native{kind};return true;
}
void Destroy(void* p){++destroys;delete static_cast<Native*>(p);}
bool Frame(ShaderFrameInfo* f){*f={current,64,32,2,true,32,16};return true;}
bool Create(unsigned,unsigned,const char*,ShaderTarget*t){*t={new Image{},nullptr};return true;}
void Release(ShaderTarget*t){delete static_cast<Image*>(t->image);*t={};}
Image& Destination(){return current.image?*static_cast<Image*>(current.image):screen;}
void Target(const ShaderTarget&t,bool){
 if(queries!=flushes)std::exit(60);
 current=t;
}
void Clear(){Destination().value=0;++clears;}
bool Vertices(const ShaderTarget&,const ShaderFrameInfo&,float* v,std::size_t stride){
 if(mode=="final_fail"&&queries==2&&stride==14)return false;
 for(unsigned i=0;i<4;++i){
  for(unsigned j=0;j<14;++j)v[i*stride+j]=0;
  for(unsigned j=3;j<7;++j)v[i*stride+j]=1;
  v[i*stride+2]=-1;v[i*stride+13]=2;
 }
 return true;
}
void Draw(const ShaderTarget&src,void* n,const float*v,unsigned count,unsigned bytes){
 if(count!=4||queries!=flushes)std::exit(61);
 auto kind=static_cast<Native*>(n)->kind;
 if((kind==0&&bytes!=14*4)||(kind==2&&bytes!=15*4))std::exit(62);
 auto value=static_cast<Image*>(src.image)->value;
 if(kind==1){value*=v[3];if(v[7]!=0)value+=7;}
 if(kind==2&&v[14]>0.001f)value+=100;
 if(kind==3)value*=2;
 Destination().value=value;++draws;drawn.push_back(kind);
}
void Drain(){}
void Flush(){if(queries!=flushes+1)std::exit(63);++flushes;}
bool Values(const ShaderProgramView&p,float*v,std::uintptr_t manager){
 if(manager!=777||queries!=flushes)std::exit(64);
 ++queries;
 Destination().value+=p.parameterCount?5:3;
 if(mode=="unload"){UnloadShaderPrograms();if(destroys)std::exit(65);}
 if(mode=="color"&&!p.parameterCount)for(unsigned i=0;i<4;++i)v[i*p.strideFloats+3]=2;
 if(mode=="geometry"&&!p.parameterCount)v[7]=0.25f;
 if(p.parameterCount){
  float amount=mode=="active"?0.5f:mode=="edge"?0.001f:
   mode=="above"?0.00101f:mode=="nan"?std::numeric_limits<float>::quiet_NaN():0;
  for(unsigned i=0;i<4;++i)v[i*p.strideFloats+14]=amount;
  if(mode=="varying")v[3*p.strideFloats+14]=1;
  if(mode=="fail")return false;
 }
 return true;
}
int main(int argc,char**argv){
 if(argc!=3)return 2;
 mode=argv[2];std::ifstream file(argv[1]);
 std::string xml((std::istreambuf_iterator<char>(file)),{});
 ShaderBackend b{Compile,Destroy,Frame,Create,Release,Target,Clear,Vertices,Draw,Drain,Flush};
 if(!LoadShaderXml("author",xml,b))return 3;
 SetShaderValueProvider(Values);
 if(mode=="final_fail")screen.value=77;
 if(mode=="reload"){
  if(!BeginShaderFrame()||!CaptureShaderScreenTarget())return 75;
  Destination().value=10;FinishShaderFrame(777);
  if(screen.value!=18||draws!=1||clears!=2)return 76;
  const std::string old="gl_FragColor = Color;";
  auto at=xml.find(old);if(at==xml.npos)return 77;
  xml.replace(at,old.size(),"gl_FragColor = Color * 2.0;");
  if(!LoadShaderXml("author",xml,b))return 78;
  draws=clears=queries=flushes=0;drawn.clear();mode="modified";
 }
 if(!BeginShaderFrame()||!CaptureShaderScreenTarget())return 4;
 Destination().value=10;
 FinishShaderFrame(777);
 if(mode=="final_fail"){
  if(screen.value!=77||current.image||queries!=2||draws||clears!=1||
     ShaderPipelineStatsSnapshot().error!=ShaderPipelineError::Target)return 79;
  UnloadShaderPrograms();return 0;
 }
 float expected=mode=="active"||mode=="above"?118:mode=="color"||mode=="modified"?31:18;
 unsigned expectedDraws=mode=="color"||mode=="modified"?2:1;
 if(mode=="geometry"){expected=25;expectedDraws=2;}
 unsigned expectedQueries=2;
 if(mode=="unknown_before"){expected=34;expectedDraws=2;expectedQueries=3;}
 if(mode=="unknown_middle"){expected=37;expectedDraws=2;expectedQueries=3;}
 if(mode=="unknown_after"){expected=42;expectedDraws=1;expectedQueries=3;}
 if(mode=="unload"){
  if(screen.value!=13||queries!=1||flushes!=1||destroys)return 66;
  AbortShaderFrame();if(destroys!=3)return 67;return 0;
 }
 if(screen.value!=expected||current.image||queries!=expectedQueries||flushes!=expectedQueries)return 68;
 if(draws!=expectedDraws||clears!=expectedDraws+1)return 71;
 if(mode=="active"||mode=="above"||mode=="varying"||mode=="nan"||mode=="fail"){
  if(drawn.back()!=2)return 72;
 }else if(mode!="unknown_after"&&drawn.back()!=0)return 73;
 if((mode=="fail")!=(ShaderPipelineStatsSnapshot().valueFailures==1))return 74;
 UnloadShaderPrograms();return 0;
}
'''


class ShaderIdentityPassTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="shader-identity-")
        cls.folder = Path(cls.tmp.name)
        source = cls.folder / "test.cpp"
        source.write_text(HARNESS)
        cls.exe = cls.folder / "test"
        result = subprocess.run(
            ["c++", "-std=c++20", "-O2", "-Wall", "-Wextra", "-Werror",
             "-I" + str(ROOT / "runtime/src"), str(source),
             str(ROOT / "runtime/src/application/shader/shader_pipeline.cpp"),
             "-o", str(cls.exe)], capture_output=True, text=True)
        if result.returncode:
            raise AssertionError(result.stdout + result.stderr)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def run_case(self, mode, xml=None):
        path = ORIGINAL
        if xml is not None:
            path = self.folder / (mode + ".xml")
            path.write_text(xml)
        result = subprocess.run([str(self.exe), str(path), mode],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, f"{mode}: {result.stdout}{result.stderr}")

    def test_original_xml_keeps_hud_and_fuses_two_identity_passes(self):
        self.run_case("plain")

    def test_real_pixelation_keeps_the_effect(self):
        self.run_case("active")

    def test_shader_exact_boundary_and_above_boundary(self):
        self.run_case("edge")
        self.run_case("above")

    def test_nonuniform_parameters_or_nan_are_not_elided(self):
        self.run_case("varying")
        self.run_case("nan")

    def test_value_failure_is_reported_and_keeps_normal_draw(self):
        self.run_case("fail")

    def test_changed_vertex_color_keeps_its_effect(self):
        self.run_case("color")

    def test_modified_standard_vertex_data_is_not_elided(self):
        self.run_case("geometry")

    def test_failed_final_vertices_restore_target_without_clearing_screen(self):
        self.run_case("final_fail")

    def test_same_name_modified_shader_keeps_its_effect(self):
        tree = ET.fromstring(ORIGINAL.read_text())
        fragment = tree.findall("shader")[0].find("fragment")
        fragment.text = fragment.text.replace("gl_FragColor = Color;", "gl_FragColor = Color * 2.0;")
        self.run_case("modified", ET.tostring(tree, encoding="unicode"))

    def test_different_owner_and_names_still_classify_by_actual_code(self):
        tree = ET.fromstring(ORIGINAL.read_text())
        for i, shader in enumerate(tree.findall("shader")):
            shader.set("name", f"Unrelated-{i}")
        self.run_case("renamed", ET.tostring(tree, encoding="unicode"))

    def test_unload_inside_callback_preserves_lifetime_and_pixels(self):
        self.run_case("unload")

    def test_reload_reclassifies_changed_program_instead_of_using_old_result(self):
        self.run_case("reload")

    def test_real_effect_before_between_and_after_identity_programs(self):
        for mode, name in (("unknown_before", "A-Effect"),
                           ("unknown_middle", "StageAPI-Sandwich"),
                           ("unknown_after", "Z-Effect")):
            tree = ET.fromstring(ORIGINAL.read_text())
            extra = ET.fromstring(ET.tostring(tree.findall("shader")[0]))
            extra.set("name", name)
            fragment = extra.find("fragment")
            fragment.text = fragment.text.replace("gl_FragColor = Color;", "gl_FragColor = Color * 2.0;")
            tree.append(extra)
            self.run_case(mode, ET.tostring(tree, encoding="unicode"))

    def test_added_comments_do_not_change_recognition(self):
        tree = ET.fromstring(ORIGINAL.read_text())
        for shader in tree.findall("shader"):
            for name in ("vertex", "fragment"):
                node = shader.find(name)
                node.text = "// comment\n" + node.text.replace("void main", "void /* same code */ main")
        self.run_case("comments", ET.tostring(tree, encoding="unicode"))


if __name__ == "__main__":
    unittest.main()
