"""宿主执行真实三条贴图包装，检查怀表/左手图片对象与持有路径生命周期。

PCX夹具来源（逐字节冻结）：主目录游戏dump
The Binding of Isaac_ Afterbirth+ 1.7.9b [010021C000B6A800][v524288][UPD]/Program #0/1/resources/
gfx/items/collectibles/collectibles_232_stopwatch.pcx -> watch232.pcx
SHA256 87784d5360a80ec86e9420cdf9afa48070cea91f5b361666d366e7e73d38fa61
 gfx/items/trinkets/trinket_061_thelefthand.pcx -> lefthand61.pcx
SHA256 2fd945f7242c04b6bbc6c7a12b0c5aae6b68687692d38e98db3fcb6cd3211f0c
PNG由测试生成不同纯色，转码参考字节由真实PngToPcx取得。
限制：原生FileManager/ImageManager/ImagePcx/ImageBase是按已知调用链写的测试替身；
并非执行Switch原生机器码。比较PCX字节身份，不验证GPU上传或ANM2动画。
释放使用毒化隔离分配器（不重用地址），可安全检查失效路径而不读取已释放内存。
"""
import re
import subprocess
import tempfile
import unittest
from pathlib import Path
try:
    from .test_startup_mod_image_resources import DRIVER, ROOT
    from .test_mod_image_full_path_identity import png_rgba
except ImportError:
    from test_startup_mod_image_resources import DRIVER, ROOT
    from test_mod_image_full_path_identity import png_rgba

OBJECT_DRIVER = DRIVER.split('int main(int argc,char** argv){',1)[0]
OBJECT_DRIVER = OBJECT_DRIVER.replace('bool installed=false', '''std::string Canon(std::string p){for(char& c:p){if(c=='\\\\')c='/';else if(c>='A'&&c<='Z')c+=32;}return p;}
struct Allocation {std::size_t size;bool alive;};
std::map<void*,Allocation> allocations;
relay::SmartPointerShim Manager(void*,const char*,void*,int);
bool installed=false''')
OBJECT_DRIVER = OBJECT_DRIVER.replace('void* NewArray(std::size_t n){return new unsigned char[n];}', 'void* NewArray(std::size_t n){auto* p=new unsigned char[n];allocations[p]={n,true};return p;}')
OBJECT_DRIVER = OBJECT_DRIVER.replace('void DeleteArray(void* p){delete[] static_cast<unsigned char*>(p);}', '''void DeleteArray(void* p){if(!p)return;auto& a=allocations.at(p);if(!a.alive){std::fprintf(stderr,"DOUBLE_FREE_PATH\\n");std::abort();}a.alive=false;std::memset(p,0xdd,a.size);}''')
OBJECT_DRIVER = OBJECT_DRIVER.replace('std::string p=path;', 'std::string p=Canon(path);')
OBJECT_DRIVER = OBJECT_DRIVER.replace('f.path=s;f.cursor=0;', 'f.path=Canon(s);f.cursor=0;')
OBJECT_DRIVER = OBJECT_DRIVER.replace('struct Image{std::vector<unsigned char> bytes;};', '''struct Image{std::vector<unsigned char> bytes;char* held=nullptr;std::string identity;};
bool BaseLoad(Image& image,const char* path){
 char* held=EntryRelayContentGetMountedFilePathCallback(reinterpret_cast<void*>(1),path);
 if(!held)return false;
 image.held=held;image.identity=held;return true;
}''')
OBJECT_DRIVER = OBJECT_DRIVER.replace('bool Feed(void* p,const unsigned char* b,std::uint32_t n,const char*){++feeds;static_cast<Image*>(p)->bytes.assign(b,b+n);return true;}', '''bool Feed(void* p,const unsigned char* b,std::uint32_t n,const char* path){++feeds;auto& image=*static_cast<Image*>(p);if(!BaseLoad(image,path))return false;image.bytes.assign(b,b+n);return true;}''')
OBJECT_DRIVER = OBJECT_DRIVER.replace('bool NativePcx(void* p,const char* path){auto hit=files.find(path);if(hit==files.end())return false;static_cast<Image*>(p)->bytes=hit->second;return true;}', '''bool NativePcx(void* p,const char* path){
 char* mounted=EntryRelayContentGetMountedFilePathCallback(reinterpret_cast<void*>(1),path);
 if(!mounted)return false;auto hit=files.find(Canon(mounted));DeleteArray(mounted);
 if(hit==files.end())return false;
 auto& image=*static_cast<Image*>(p);if(!BaseLoad(image,path))return false;image.bytes=hit->second;return true;
}''')
OBJECT_DRIVER = OBJECT_DRIVER.replace('if(id==HookId::ContentGetMountedFilePath)return', 'if(id==HookId::ImageManagerLoadFile)return reinterpret_cast<std::uintptr_t>(Manager);\n if(id==HookId::ContentGetMountedFilePath)return')
OBJECT_DRIVER += r'''
#define CHECK(x) do{if(!(x)){std::fprintf(stderr,"FAIL line %d: %s\n",__LINE__,#x);return 1;}}while(0)
std::map<std::string,Image*> imageCache;
relay::SmartPointerShim Manager(void*,const char* path,void*,int){
 relay::SmartPointerShim result;
 // 原生管理器先按完整mounted路径查缓存；插入以ImageBase持有路径为键。
 char* initial=EntryRelayContentGetMountedFilePathCallback(reinterpret_cast<void*>(1),path);
 if(!initial)return result;
 std::string key=Canon(initial);DeleteArray(initial);
 if(auto hit=imageCache.find(key);hit!=imageCache.end()){
  if(Canon(hit->second->identity)!=key){std::fprintf(stderr,"CACHE_IDENTITY_MISMATCH\n");std::abort();}
  result.pointer=hit->second;return result;
 }
 auto* image=new Image;
 if(!EntryRelayImagePcxLoadCallback(image,Canon(path).c_str())){delete image;return result;}
 imageCache[Canon(image->identity)]=image;result.pointer=image;return result;
}
int ReferenceInflate(std::uint8_t* out,std::size_t n,const std::uint8_t* in,std::size_t m){uLongf size=n;int result=uncompress(out,&size,in,m);return result==Z_OK && size==n ? 0 : -1;}
std::vector<unsigned char> Reference(const std::vector<unsigned char>& png){
 std::uint8_t* p=nullptr;std::size_t n=0;
 if(!content::PngToPcx(png.data(),png.size(),ReferenceInflate,&p,&n))return {};
 std::vector<unsigned char> result(p,p+n);delete[] p;return result;
}
std::vector<unsigned char> Pixels(const std::vector<unsigned char>& bytes){
 if(bytes.size()<128)return {};
 auto word=[&](int i){return unsigned(bytes[i])|(unsigned(bytes[i+1])<<8);};
 const std::size_t height=word(10)-word(6)+1;
 const std::size_t wanted=height*word(66)*bytes[65];
 std::vector<unsigned char> pixels;pixels.reserve(wanted);
 for(std::size_t offset=128;offset<bytes.size() && pixels.size()<wanted;){
  unsigned value=bytes[offset++],count=1;
  if(value>=192){count=value&63;if(offset==bytes.size())return {};value=bytes[offset++];}
  if(count>wanted-pixels.size())return {};
  pixels.insert(pixels.end(),count,value);
 }
 return pixels.size()==wanted ? pixels : std::vector<unsigned char>{};
}
int main(int argc,char** argv){
 if(argc!=6)return 90;std::string mode=argv[1];
 const std::string query[2]={"gfx/items/collectibles/collectibles_232_stopwatch.pcx","gfx/items/trinkets/trinket_061_thelefthand.pcx"};
 std::string requests[2]={query[0],query[1]},expectedPaths[2];
 std::vector<unsigned char> expected[2]={Load(argv[2]),Load(argv[3])};
 CHECK(expected[0]!=expected[1]);
 for(int i=0;i<2;++i){files["rom:/resources/"+query[i]]=expected[i];expectedPaths[i]="rom:/resources/"+query[i];}
 const char* roots[]={"isaac_mods/mods/objectidentity"};
 bridge::PublishModResourceRedirectList(roots,1);
 for(int i=0;i<2;++i){
  const bool override=mode=="both-overlay" || mode=="direct-png" || (mode=="watch-overlay" && i==0);
  if(!override)continue;
  auto png=query[i];png.replace(png.size()-4,4,".png");
  auto real="rom:/isaac_mods/mods/objectidentity/resources/"+png;
  files[real]=Load(argv[4+i]);
  expectedPaths[i]=real.substr(0,real.size()-4)+".pcx";
  if(mode=="direct-png")requests[i]="isaac_mods/mods/objectidentity/resources/"+png;
 }
 TargetModule module{};module.base=0x10000000;module.textSize=0x700000;module.buildId=kTargetBuildId;
 Startup(module);CHECK(g_engineBindings!=nullptr && g_fileBindings!=nullptr);
 if(mode=="resolved-switch"){
  const std::string owners[2]={"isaac_mods/mods/ownerwatcha","isaac_mods/mods/ownerwatchb"};
  std::vector<unsigned char> pixels[2];Image* images[2]={nullptr,nullptr};
  auto png=query[0];png.replace(png.size()-4,4,".png");
  std::string resolved[2];
  for(int i=0;i<2;++i){
   const auto real="rom:/"+owners[i]+"/resources/"+png;
   files[real]=Load(argv[4+i]);resolved[i]=real.substr(0,real.size()-4)+".pcx";
   expected[i]=Reference(files[real]);pixels[i]=Pixels(expected[i]);CHECK(!pixels[i].empty());
  }
  CHECK(pixels[0]!=pixels[1]);
  for(int pass=0;pass<96;++pass){
   const int i=pass%2;const char* active[]={owners[i].c_str()};
   bridge::PublishModResourceRedirectList(active,1);
   std::string request=query[0];
   if(pass%3==1)for(char& c:request)if(c=='/')c='\\';
   if(pass%3==2)for(std::size_t n=0;n+4<request.size();++n)if(request[n]>='a'&&request[n]<='z')request[n]-=32;
   auto result=EntryRelayImageManagerLoadFileCallback(reinterpret_cast<void*>(2),request.c_str(),nullptr,0);
   auto* image=static_cast<Image*>(result.pointer);CHECK(image);
   if(!images[i])images[i]=image;CHECK(image==images[i]);
   CHECK(Canon(image->identity)==Canon(resolved[i]));
   CHECK(image->bytes==expected[i] && Pixels(image->bytes)==pixels[i]);
   for(int j=0;j<2;++j)if(images[j]){
    CHECK(allocations.at(images[j]->held).alive);
    CHECK(std::string(images[j]->held)==images[j]->identity);
    CHECK(Canon(images[j]->identity)==Canon(resolved[j]));
    CHECK(images[j]->bytes==expected[j]);
   }
   if(images[0] && images[1])CHECK(images[0]!=images[1]);
  }
  CHECK(imageCache.size()==2);
  for(auto& entry:imageCache){DeleteArray(entry.second->held);delete entry.second;}
  for(auto& entry:allocations)delete[] static_cast<unsigned char*>(entry.first);
  std::puts("IMAGE_OBJECT_IDENTITY_OK resolved-switch interleaved=96");return 0;
 }
 for(int i=0;i<2;++i)if(expectedPaths[i].find("isaac_mods")!=std::string::npos){expected[i]=Reference(Load(argv[4+i]));CHECK(!expected[i].empty());}
 auto pixelIdentity0=Pixels(expected[0]),pixelIdentity1=Pixels(expected[1]);
 CHECK(!pixelIdentity0.empty() && !pixelIdentity1.empty() && pixelIdentity0!=pixelIdentity1);
 Image* first[2]={nullptr,nullptr};
 for(int pass=0;pass<48;++pass)for(int turn=0;turn<2;++turn){
  int i=(pass%2)?1-turn:turn;std::string request=requests[i];
  // 两种清洗变化都经过生产Manager包装；保留小写后缀避免引入另一未证实的契约。
  if(pass%3==1)for(char& c:request)if(c=='/')c='\\';
  if(pass%3==2)for(std::size_t n=0;n+4<request.size();++n)if(request[n]>='a'&&request[n]<='z')request[n]-=32;
  auto result=EntryRelayImageManagerLoadFileCallback(reinterpret_cast<void*>(2),request.c_str(),nullptr,0);
  auto* image=static_cast<Image*>(result.pointer);CHECK(image!=nullptr);
  if(!first[i])first[i]=image;
  CHECK(image==first[i]);
  CHECK(image->bytes==expected[i]);
  CHECK(Pixels(image->bytes)==(i==0?pixelIdentity0:pixelIdentity1));
  CHECK(image->held!=nullptr && allocations.at(image->held).alive);
  CHECK(Canon(image->held)==Canon(expectedPaths[i]));
  CHECK(std::string(image->held)==image->identity);
  if(first[0] && first[1])CHECK(first[0]!=first[1]);
  // 后续所有加载结束后再验早期对象，捕获环形串覆盖或提前释放。
  for(int j=0;j<2;++j)if(first[j]){
   CHECK(allocations.at(first[j]->held).alive);
   CHECK(std::string(first[j]->held)==first[j]->identity);
   CHECK(first[j]->bytes==expected[j]);
  }
 }
 CHECK(g_imagePcxDiag.hookCalls==96);
 for(auto& entry:imageCache){DeleteArray(entry.second->held);delete entry.second;}
 for(auto& entry:allocations)delete[] static_cast<unsigned char*>(entry.first);
 std::printf("IMAGE_OBJECT_IDENTITY_OK %s interleaved=96\n",mode.c_str());return 0;
}
'''

class SharedItemImageObjectsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(prefix='shared-item-object-')
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.work=Path(cls.tmp.name)
        src=(ROOT/'runtime/source/hook_manager.cpp').read_text().split('EarlyModMountOutcome MountModsBeforeHeavyWorkImpl(',1)[1]
        prefix=src[src.index('{')+1:src.index('    isaac::runtime::GameFileReaderAdapter content')]
        prefix=re.sub(r'//[^\n]*','',prefix)
        driver=cls.work/'driver.cpp'
        driver.write_text(OBJECT_DRIVER.replace('@STARTUP_PREFIX@',prefix).replace('@PREP_INCLUDE@','#include "mod_image_resources.hpp"'))
        cls.binary=cls.work/'test'
        cmd=['c++','-std=c++20','-O0','-I',str(ROOT/'runtime/source'),'-I',str(ROOT/'runtime/src'),str(driver),str(ROOT/'runtime/source/mod_resource_redirect.cpp'),str(ROOT/'runtime/src/infrastructure/content/png_to_pcx_bridge.cpp'),str(ROOT/'runtime/src/application/mod/content_mount_service.cpp'),str(ROOT/'runtime/source/mod_image_resources.cpp'),'-lz','-o',str(cls.binary)]
        result=subprocess.run(cmd,text=True,capture_output=True)
        assert result.returncode==0,result.stdout+result.stderr
        cls.inputs=list((Path(__file__).parent/'fixtures/shared_item_images'/name) for name in ('watch232.pcx','lefthand61.pcx'))
        for i,color in enumerate(((221,31,47,255),(29,173,81,255))):
            path=cls.work/f'overlay{i}.png';path.write_bytes(png_rgba(color));cls.inputs.append(path)

    def test_native_originals_keep_distinct_objects_pixels_and_owned_paths(self):
        self.run_mode('native')
    def test_watch_png_override_does_not_change_left_hand(self):
        self.run_mode('watch-overlay')
    def test_two_png_overrides_keep_distinct_objects_pixels_and_owned_paths(self):
        self.run_mode('both-overlay')
    def test_direct_mod_png_requests_keep_distinct_objects_pixels_and_owned_paths(self):
        self.run_mode('direct-png')
    def test_same_request_resolved_to_different_mod_directories_keeps_owner_identity(self):
        self.run_mode('resolved-switch')
    def run_mode(self,mode):
        result=subprocess.run([str(self.binary),mode,*map(str,self.inputs)],text=True,capture_output=True)
        print(result.stdout+result.stderr,end='')
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)

if __name__=='__main__':unittest.main()
