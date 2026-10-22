"""启动时真实shader加载器必须先解析路径；硬件文件与GPU接口用替身。"""
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HEADER = r"""
#pragma once
#include <cstddef>
namespace GameFileReader {
using ConstructFn=void(*)(void*);using OpenReadFn=bool(*)(void*,const char*);
using GetLengthFn=int(*)(const void*);using ReadFn=int(*)(void*,void*,int,int);
using CloseFn=void(*)(void*);using DestroyFn=void(*)(void*);
struct Bindings {ConstructFn construct{};OpenReadFn openRead{};GetLengthFn getLength{};
 ReadFn read{};CloseFn close{};DestroyFn destroy{};};
enum class TextReadResult {Success,InvalidArgument,OpenFailed,LengthOutOfRange,ReadMismatch};
TextReadResult ReadTextFile(const Bindings&,const char*,unsigned char*,std::size_t,std::size_t*);
}
"""
DRIVER = r"""
#include "application/shader/mod_shader_loader.hpp"
#include "application/shader/shader_pipeline.hpp"
#include "application/shader/native_shader_backend.hpp"
#include <cstring>
#include <cstdio>
#include <cstdlib>
#include <string>
#include <fstream>
#include <type_traits>
using namespace isaac::runtime;
using Resolve=bool(*)(void*,const char*,char*,std::size_t);
std::string scene,xml,root="isaac_mods/mods/Test Mod";
unsigned opens{},lookups{},compiles{},destroys{};
void Construct(void*){};bool Open(void*,const char*){return true;}
int Length(const void*){return static_cast<int>(xml.size());}
int Read(void*,void*,int,int){return 0;}void Close(void*){}void DestroyFile(void*){}
bool Compile(const ShaderProgramView& v,void**p){
 if(!std::strstr(v.vertex,"#version 430"))return false;
 *p=new int(++compiles);return true;
}
void DestroyShader(void*p){delete static_cast<int*>(p);++destroys;}
bool Frame(ShaderFrameInfo*){return false;}
bool Create(unsigned,unsigned,const char*,ShaderTarget*){return false;}
void Release(ShaderTarget*){}
void Target(const ShaderTarget&,bool){}
void Clear(){}
bool Vertices(const ShaderTarget&,const ShaderFrameInfo&,float*,std::size_t){return false;}
void Draw(const ShaderTarget&,void*,const float*,unsigned,unsigned){}
void Drain(){}
namespace isaac::runtime {const ShaderBackend& NativeShaderBackend()noexcept{
 static const ShaderBackend backend{Compile,DestroyShader,Frame,Create,Release,Target,
  Clear,Vertices,Draw,Drain};return backend;}}
bool ResolveFile(void*ctx,const char*request,char*out,std::size_t capacity){
 ++lookups;if(ctx!=&opens||request!=root+"/content/shaders.xml")std::exit(70);
 if(scene=="missing")return false;
 if(scene=="unterminated"){std::memset(out,'x',capacity);return true;}
 const auto path=scene=="unmounted"?std::string(request):"rom:/"+std::string(request);
 if(path.size()+1>capacity)return false;
 std::memcpy(out,path.c_str(),path.size()+1);return true;
}
namespace GameFileReader {
TextReadResult ReadTextFile(const Bindings&,const char*path,unsigned char*target,
 std::size_t capacity,std::size_t*length){
 ++opens;
 if(scene=="missing"||path!="rom:/"+root+"/content/shaders.xml"){
  std::fprintf(stderr,"UNSAFE_NATIVE_OPEN: %s\n",path);std::exit(41);
 }
 if(scene=="read_failure")return TextReadResult::ReadMismatch;
 if(scene=="open_failure")return TextReadResult::OpenFailed;
 if(xml.empty())return TextReadResult::LengthOutOfRange;
 *length=xml.size();if(xml.size()>capacity)return TextReadResult::LengthOutOfRange;
 std::memcpy(target,xml.data(),xml.size());return TextReadResult::Success;
}}
// 同一失败夹具可编译修复前两参入口和修复后显式解析入口，不因改签名而制造编译失败。
template<class Fn>bool Invoke(Fn fn,const GameFileReader::Bindings&files,const char*name,Resolve resolver){
 if constexpr(std::is_invocable_r_v<bool,Fn,const GameFileReader::Bindings&,const char*,Resolve,void*>)
  return fn(files,name,resolver,&opens);
 else return fn(files,name);
}
int main(int argc,char**argv){
 if(argc<2)return 90;scene=argv[1];
 xml=R"xml(<shaders><shader name="Actual"><parameters/><vertex><![CDATA[attribute vec3 Position;uniform mat4 Transform;void main(){gl_Position=Transform*vec4(Position,1.);}]]></vertex><fragment><![CDATA[void main(){gl_FragColor=vec4(1.);}]]></fragment></shader></shaders>)xml";
 if(scene=="original"){if(argc!=3)return 91;std::ifstream f(argv[2]);xml.assign(std::istreambuf_iterator<char>(f),{});}
 if(scene=="large")xml=std::string(6000,' ')+xml;
 if(scene=="empty")xml.clear();
 GameFileReader::Bindings files{Construct,Open,Length,Read,Close,DestroyFile};
 const char*name=root.c_str();Resolve resolver=ResolveFile;
 if(scene=="null_root")name=nullptr;
 if(scene=="empty_root")name="";
 if(scene=="long_root"){root.assign(700,'x');name=root.c_str();}
 if(scene=="no_resolver")resolver=nullptr;
 if(scene=="bad_bindings")files.openRead=nullptr;
 const bool result=Invoke(&LoadModShaderFile,files,name,resolver);
 const bool loaded=scene=="normal"||scene=="large"||scene=="original";
 const bool expected=loaded||scene=="missing";
 if(result!=expected){std::fprintf(stderr,"RESULT_MISMATCH %s expected=%d got=%d\n",scene.c_str(),expected,result);return 42;}
 if(loaded){if(opens!=(scene=="large"||scene=="original"&&xml.size()>4096?2u:1u)||lookups!=1||!compiles||!ShaderPipelineStatsSnapshot().programs)return 43;}
 else if(scene=="read_failure"||scene=="open_failure"||scene=="empty"){
  if(opens!=1||lookups!=1||compiles)return 44;
 }else if(opens||compiles)return 45;
 UnloadShaderPrograms();if(destroys!=compiles)return 46;
 return 0;
}
"""

class ModShaderLoaderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="isaac-shader-file-")
        work = Path(cls.temp.name)
        (work / "game_file_reader.hpp").write_text(HEADER)
        (work / "driver.cpp").write_text(DRIVER)
        cls.exe = work / "loader"
        result = subprocess.run([
            "c++", "-std=c++20", "-O2", "-Wall", "-Wextra", "-Werror",
            "-Wno-missing-field-initializers", "-Wno-logical-op-parentheses",
            "-I" + str(work), "-I" + str(ROOT / "runtime/src"),
            str(work / "driver.cpp"),
            str(ROOT / "runtime/src/application/shader/mod_shader_loader.cpp"),
            str(ROOT / "runtime/src/application/shader/shader_pipeline.cpp"),
            "-o", str(cls.exe),
        ], capture_output=True, text=True)
        if result.returncode:
            raise AssertionError(result.stdout + result.stderr)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def run_scene(self, name, *args):
        result = subprocess.run([str(self.exe), name, *map(str, args)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_absent_shader_never_opens_native_file(self):
        self.run_scene("missing")

    def test_relative_mod_root_is_resolved_before_read_and_compile(self):
        self.run_scene("normal")

    def test_present_but_failed_read_is_not_treated_as_absence(self):
        for scene in ("read_failure", "open_failure", "empty"):
            with self.subTest(scene=scene):
                self.run_scene(scene)

    def test_invalid_resolved_paths_never_reach_native_open(self):
        for scene in ("unmounted", "unterminated"):
            with self.subTest(scene=scene):
                self.run_scene(scene)

    def test_invalid_inputs_do_not_open_or_compile(self):
        for scene in ("null_root", "empty_root", "long_root", "no_resolver", "bad_bindings"):
            with self.subTest(scene=scene):
                self.run_scene(scene)

    def test_large_shader_retries_same_resolved_path(self):
        self.run_scene("large")

    def test_original_stageapi_shader_declaration_reaches_pipeline(self):
        self.run_scene("original", ROOT / "analysis/mod-corpus/BOIStageAPI15/content/shaders.xml")
