"""真实Font生产绑定：PC terminus8及非空Lua参数栈下的量宽。"""
import subprocess,tempfile,unittest
from pathlib import Path
from . import test_lua_font_resources as fixture
from .test_support import build_lua_harness
ROOT=Path(__file__).resolve().parents[2]
MAIN=r'''
int main(int argc,char**argv){
 if(argc!=2)return 90;
 PublishFakeBindings();
 const bool width=std::strcmp(argv[1],"width")==0;
 const char*script=width?R"lua(RegisterMod('Width',1);assert(Isaac.GetTextWidth('AB')==20,'nonempty API stack must measure');assert(Isaac.GetTextWidth(42)==20,'numeric coercion');assert(Isaac.GetTextWidth('é')==9,'UTF8 path');)lua":R"lua(RegisterMod('Font',1);Isaac.RenderText('AB',1,2,1,1,1,1);Isaac.RenderScaledText('AB',1,2,.5,.5,1,1,1,1))lua";
 auto result=LuaRuntime::InitializeFromBuffer(script,std::strlen(script),"@default-font.lua");
 char error[512]{};static_cast<void>(LuaRuntime::CopyLastLuaErrorText(error,sizeof(error)));
 if(result!=LuaRuntime::LuaInitResult::Success){std::fprintf(stderr,"%s\n",error);return 70;}
 if(std::strcmp(g_defaultLoadedPath,"font/terminus8.fnt")){std::fprintf(stderr,"wrong PC font: %s\n",g_defaultLoadedPath);return 71;}
 if(!width&&g_drawStringScaled.calls!=2)return 72;
 std::puts("PASS PC terminus8 / shared native font / API argument stack / UTF8 / numeric coercion");return 0;
}
'''
class DefaultScreenFontContractTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory(prefix='default-screen-font-')
  cpp=fixture.HARNESS[:fixture.HARNESS.index('const char* kUnavailableScript')]+'\n}\n'
  cpp=cpp.replace('bool FakeLoad(void* font,','char g_defaultLoadedPath[128]{};\nbool FakeLoad(void* font,')
  cpp=cpp.replace('    fake->loaded = true;\n    return true;','    std::strncpy(g_defaultLoadedPath,path,sizeof(g_defaultLoadedPath)-1);\n    fake->loaded = true;\n    return true;',1)
  cls.bin=build_lua_harness(source_root=fixture.SOURCE,workdir=Path(cls.tmp.name),harness_source=cpp+MAIN)
 @classmethod
 def tearDownClass(cls):cls.tmp.cleanup()
 def check_case(self,case):
  r=subprocess.run([str(self.bin),case],text=True,capture_output=True);self.assertEqual(r.returncode,0,r.stdout+r.stderr);print(r.stdout.strip())
 def test_pc_default_font_reaches_both_render_entries(self):self.check_case('font')
 def test_text_width_receives_real_api_arguments(self):self.check_case('width')
