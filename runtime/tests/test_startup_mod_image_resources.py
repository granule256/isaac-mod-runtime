"""首次加载执行真实路径回调、PCX读取回调与PNG转码，使用模组原始透明图片。"""
import re
import subprocess
import tempfile
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
DRIVER=r"""
#include "image_pcx_bridge_hook.cpp"
#include "mod_resource_redirect.hpp"
@PREP_INCLUDE@
#include <fstream>
#include <vector>
#include <map>
#include <string>
#include <zlib.h>
#include <new>
using namespace isaac::runtime;
std::map<std::string,std::vector<unsigned char>> files;
bool installed=false, rejectBindings=false, rejectInstall=false;
int installs=0, feeds=0;
void* NewArray(std::size_t n){return new unsigned char[n];}
void DeleteArray(void* p){delete[] static_cast<unsigned char*>(p);}
char* Probe(void*,const char* path){
 std::string p=path; if(p.rfind("rom:/",0)!=0)p=(p.rfind("gfx/",0)==0?"rom:/resources/":"rom:/")+p;
 if(!files.count(p))return nullptr;
 char* out=static_cast<char*>(NewArray(p.size()+1));std::memcpy(out,p.c_str(),p.size()+1);return out;
}
struct File{std::string path;std::size_t cursor=0;};
void Construct(void* p){new(p)File;}
bool Open(void* p,const char* s){auto& f=*static_cast<File*>(p);f.path=s;f.cursor=0;return files.count(f.path);}
int Length(const void* p){return files.at(static_cast<const File*>(p)->path).size();}
int Read(void* p,void* out,int size,int count){auto& f=*static_cast<File*>(p);auto& b=files.at(f.path);std::size_t n=std::min(std::size_t(size*count),b.size()-f.cursor);std::memcpy(out,b.data()+f.cursor,n);f.cursor+=n;return n/size;}
void Close(void*){}
void Destroy(void* p){static_cast<File*>(p)->~File();}
struct Image{std::vector<unsigned char> bytes;};
bool Feed(void* p,const unsigned char* b,std::uint32_t n,const char*){++feeds;static_cast<Image*>(p)->bytes.assign(b,b+n);return true;}
bool NativePcx(void* p,const char* path){auto hit=files.find(path);if(hit==files.end())return false;static_cast<Image*>(p)->bytes=hit->second;return true;}
int Init(void* p,int bits,const char* ver,int n){return inflateInit2_(static_cast<z_stream*>(p),bits,ver,n);}
int Inflate(void* p,int flags){return inflate(static_cast<z_stream*>(p),flags);}
int End(void* p){return inflateEnd(static_cast<z_stream*>(p));}
namespace GameFileReader {
bool VerifyBindings(const TargetModule&,Bindings* out){*out={Construct,Open,Length,Read,Close,Destroy};return true;}
bool VerifyImagePcxBindings(const TargetModule&,ImagePcxBindings* out){
 *out={};if(rejectBindings)return false;
 out->inMemoryLoad=Feed;out->inflateInit2=Init;out->inflate=Inflate;out->inflateEnd=End;
 out->contentManager=reinterpret_cast<void*>(1);out->operatorNewArray=NewArray;out->operatorDeleteArray=DeleteArray;return true;
}
std::uint32_t LastImagePcxBindingMask()noexcept{return rejectBindings?1:0;}
}
namespace isaac::runtime {
std::uintptr_t EntryRelayFallbackEntry(HookId id)noexcept{
 if(id==HookId::ContentGetMountedFilePath)return reinterpret_cast<std::uintptr_t>(Probe);
 if(id==HookId::ImagePcxLoad && (installed || rejectInstall))return reinterpret_cast<std::uintptr_t>(NativePcx);return 0;
}
bool EntryRelayInstalledEarly(HookId id)noexcept{return id==HookId::ImagePcxLoad && installed;}
bool EntryRelayInstalled(HookId id)noexcept{return id==HookId::ContentGetMountedFilePath || (id==HookId::ImagePcxLoad && installed);}
bool TryInstallEntryRelayEarly(HookId id,const HookTarget&,std::uintptr_t* entry)noexcept{
 if(id!=HookId::ImagePcxLoad)std::abort();++installs;
 if(rejectInstall)return false;installed=true;*entry=reinterpret_cast<std::uintptr_t>(NativePcx);return true;
}
}
namespace isaac::runtime::relay {std::uint32_t LastFailure(){return rejectInstall?2:0;}}
GameFileReader::Bindings g_DefaultManifestBindings{};
GameFileReader::ImagePcxBindings g_ImagePcxBindings{};
struct EarlyModMountOutcome{bool attempted=false;std::size_t mountsAttempted=0,mountsFailed=0;};
EarlyModMountOutcome Startup(const TargetModule& module){
@STARTUP_PREFIX@
return outcome;
}
std::vector<unsigned char> Load(const char* filename){std::ifstream f(filename,std::ios::binary);return {std::istreambuf_iterator<char>(f),{}};}
int main(int argc,char** argv){
 if(argc!=4)return 90;std::string scenario=argv[1];
 auto native=Load(argv[2]);auto png=Load(argv[3]);
 files["rom:/resources/gfx/ui/minimap_questionmark.pcx"]=native;
 files["rom:/resources/gfx/ui/pause_screen.pcx"]=native;
 if(scenario=="late-existing")installed=true;
 if(scenario!="missing")files["rom:/isaac_mods/mods/minimapi/resources/gfx/ui/minimap_questionmark.png"]=png;
 // 第二个逻辑名字证明没有问号专用分支，使用同一原始PNG作为任意资源替换。
 if(scenario=="generic")files["rom:/isaac_mods/mods/minimapi/resources/gfx/ui/custom_marker.png"]=png;
 const char* roots[]={"isaac_mods/mods/minimapi"};
 if(scenario=="closed")isaac::runtime::bridge::PublishModResourceRedirectList(nullptr,0);
 else isaac::runtime::bridge::PublishModResourceRedirectList(roots,1);
 rejectBindings=scenario=="bindings-fail";rejectInstall=scenario=="install-fail";
 TargetModule module{};module.base=0x10000000;module.textSize=0x700000;module.buildId=kTargetBuildId;
 auto first=Startup(module);
 if(rejectBindings || rejectInstall){
  if(first.mountsFailed!=1 || g_engineBindings!=nullptr)return 31;
  if(rejectBindings && installs!=0)return 32;
  std::puts("PREPARE_FAILURE_REPORTED");return 0;
 }
 if(!installed || g_engineBindings==nullptr || g_fileBindings==nullptr){std::fprintf(stderr,"STARTUP_IMAGE_NOT_READY\n");return 10;}
 auto again=Startup(module);(void)again;if(installs!=(scenario=="late-existing"?0:1))return 11;
 if(scenario=="snapshot"){g_DefaultManifestBindings.openRead=nullptr;g_ImagePcxBindings.inMemoryLoad=nullptr;}
 const char* query=scenario=="generic"?"gfx/ui/custom_marker.pcx":"gfx/ui/minimap_questionmark.pcx";
 char* path=EntryRelayContentGetMountedFilePathCallback(reinterpret_cast<void*>(1),query);if(!path)return 12;
 Image image{};if(!EntryRelayImagePcxLoadCallback(&image,path))return 13;DeleteArray(path);
 bool override=scenario!="closed" && scenario!="missing";
 if(override && (image.bytes.size()<128 || image.bytes[8]!=(scenario=="opaque"?31:0) || image.bytes[10]!=(scenario=="opaque"?31:0) || feeds!=1))return 14;
 if(!override && image.bytes!=native)return 15;
 // 暂停菜单原版文件没有模组替换，必须逐字节保持原版，不产生取图空指针。
 char* pause=EntryRelayContentGetMountedFilePathCallback(reinterpret_cast<void*>(1),"gfx/ui/pause_screen.pcx");
 Image pauseImage{};if(!pause || !EntryRelayImagePcxLoadCallback(&pauseImage,pause) || pauseImage.bytes!=native)return 16;DeleteArray(pause);
 std::ofstream("result.pcx",std::ios::binary).write(reinterpret_cast<char*>(image.bytes.data()),image.bytes.size());
 std::puts("STARTUP_IMAGE_OK");return 0;
}
"""
class StartupModImageResourcesTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory(prefix='startup-mod-images-');cls.work=Path(cls.tmp.name)
  src=(ROOT/'runtime/source/hook_manager.cpp').read_text().split('EarlyModMountOutcome MountModsBeforeHeavyWorkImpl(',1)[1]
  prefix=src[src.index('{')+1:src.index('    isaac::runtime::GameFileReaderAdapter content')]
  prefix=re.sub(r'//[^\n]*','',prefix)
  prep=ROOT/'runtime/source/mod_image_resources.cpp'
  driver=cls.work/'driver.cpp';driver.write_text(DRIVER.replace('@STARTUP_PREFIX@',prefix).replace('@PREP_INCLUDE@','#include "mod_image_resources.hpp"' if prep.exists() else ''))
  cmd=['c++','-std=c++20','-O0','-I',str(ROOT/'runtime/source'),'-I',str(ROOT/'runtime/src'),str(driver),str(ROOT/'runtime/source/mod_resource_redirect.cpp'),str(ROOT/'runtime/src/infrastructure/content/png_to_pcx_bridge.cpp'),str(ROOT/'runtime/src/application/mod/content_mount_service.cpp')]
  if prep.exists():cmd.append(str(prep))
  cls.binary=cls.work/'test';cmd+=['-lz','-o',str(cls.binary)]
  r=subprocess.run(cmd,capture_output=True,text=True);assert r.returncode==0,r.stdout+r.stderr
 @classmethod
 def tearDownClass(cls):cls.tmp.cleanup()
 def test_first_load_and_failures(self):
  fixture=ROOT/'dist/change-archive-20261012/440-minimap-curse-questionmark-diagnosis'
  for scenario in ('enabled','closed','missing','generic','opaque','snapshot','late-existing','bindings-fail','install-fail'):
   with self.subTest(scenario=scenario):
    r=subprocess.run([str(self.binary),scenario,str(fixture/'native-questionmark.pcx'),str(fixture/('mod-drawn-questionmark.png' if scenario=='opaque' else 'mod-transparent-original.png'))],cwd=self.work,capture_output=True,text=True)
    self.assertEqual(r.returncode,0,r.stdout+r.stderr)
    if scenario in ('enabled','generic'):
     raw=(self.work/'result.pcx').read_bytes();decoded=[];i=128
     while i<len(raw):
      v=raw[i];i+=1
      if v>=192:n=v&63;v=raw[i];i+=1
      else:n=1
      decoded.extend([v]*n)
     self.assertEqual(decoded[:4],[255,255,255,0], '实际原生接收图必须保留透明像素')
