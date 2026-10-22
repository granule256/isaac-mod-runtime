"""完整生产登记→回查→PNG转码→Feed：同名图片必须保留模组目录身份。"""
import re
import struct
import subprocess
import tempfile
import unittest
import zlib
from pathlib import Path

try:
    from .test_startup_mod_image_resources import DRIVER, ROOT
except ImportError:
    from test_startup_mod_image_resources import DRIVER, ROOT


ROUTE_DRIVER = DRIVER.split('int main(int argc,char** argv){',1)[0]
ROUTE_DRIVER = ROUTE_DRIVER.replace('std::map<std::string,std::vector<unsigned char>> files;', '''std::map<std::string,std::vector<unsigned char>> files;
std::map<std::string,std::string> aliases;
std::vector<std::string> opens;''')
ROUTE_DRIVER = ROUTE_DRIVER.replace('if(!files.count(p))return nullptr;', 'if(aliases.count(p))p=aliases.at(p); if(!files.count(p))return nullptr;')
ROUTE_DRIVER = ROUTE_DRIVER.replace('f.path=s;f.cursor=0;', 'f.path=s;f.cursor=0;opens.push_back(s);')
ROUTE_DRIVER += r'''
std::vector<unsigned char> ConvertReference(const std::vector<unsigned char>& png) {
    std::uint8_t* bytes=nullptr;std::size_t n=0;
    if(!content::PngToPcx(png.data(),png.size(),ImagePcxInflateOne,&bytes,&n))return {};
    std::vector<unsigned char> result(bytes,bytes+n);delete[] bytes;return result;
}
std::string Clean(std::string p) {
    for(char& c:p) { if(c=='/')c='\\';else if(c>='a'&&c<='z')c=char(c-'a'+'A'); }
    return p;
}
#define CHECK(x) do { if(!(x)) { std::fprintf(stderr,"FAIL line %d: %s\n",__LINE__,#x);return 1; } } while(0)
int main(int argc,char** argv) {
    if(argc!=5)return 90;
    const std::string scenario=argv[1];
    TargetModule module{};module.base=0x10000000;module.textSize=0x700000;module.buildId=kTargetBuildId;
    Startup(module);
    CHECK(g_engineBindings!=nullptr && g_fileBindings!=nullptr);
    const bool viaPng=scenario.rfind("png-",0)==0;
    const bool cleaned=scenario.find("clean")!=std::string::npos;
    const bool repeated=scenario.find("repeat")!=std::string::npos;
    const bool unknown=scenario.find("unknown")!=std::string::npos;
    const bool longPaths=scenario.find("long")!=std::string::npos;
    const bool actual=scenario.find("actual")!=std::string::npos;
    const bool originalRequest=scenario.find("request")!=std::string::npos;
    const char* owners[]={"Babyl","RepTemplate","TemplateChar"};
    std::string requests[3], resolved[3], synthetic[3];
    std::vector<unsigned char> expected[3];
    for(int i=0;i<3;++i) {
        // 三者前255字节完全相同、后段模组目录不同；截断路由或缓存键会被抓住。
        const std::string leading=longPaths ? std::string(280,'x')+"/" : "";
        requests[i]="isaac_mods/mods/"+leading+owners[i]+"/content/gfx/charactermenu"+(viaPng?".png":".pcx");
        resolved[i]="rom:/isaac_mods/mods/"+leading+owners[i]+"/ResolvedAssets/gfx/charactermenu.png";
        files[resolved[i]]=Load(argv[i+2]);
        expected[i]=ConvertReference(files[resolved[i]]);CHECK(!expected[i].empty());
        auto pngRequest=requests[i];pngRequest.replace(pngRequest.size()-4,4,".png");
        aliases["rom:/"+pngRequest]=resolved[i];
        const char* returned=viaPng ? RouteModPngThroughPcx(requests[i].c_str()) : EntryRelayContentGetMountedFilePathCallback(reinterpret_cast<void*>(1),requests[i].c_str());
        CHECK(returned!=nullptr);
        synthetic[i]=returned;
        CHECK(synthetic[i] != requests[i] || !viaPng);
        DeleteArray(const_cast<char*>(returned));
        const std::string expectedReturn=viaPng ? requests[i].substr(0,requests[i].size()-4)+".pcx" : resolved[i].substr(0,resolved[i].size()-4)+".pcx";
        CHECK(synthetic[i]==expectedReturn);
    }
    CHECK(viaPng ? g_imagePcxDiag.pngRouted==3 : g_imagePcxDiag.mountSynth==3);
    if(repeated) {
        // 同一完整虚拟键重新解析到同一模组的新实际PNG，必须取最新登记。
        if(viaPng) {
            const auto replacement=resolved[1].substr(0,resolved[1].find("ResolvedAssets"))+"UpdatedAssets/gfx/charactermenu.png";
            files[replacement]=files[resolved[2]];
            aliases["rom:/"+requests[1]]=replacement;
            const char* returned=RouteModPngThroughPcx(requests[1].c_str());
            CHECK(returned && synthetic[1]==returned);DeleteArray(const_cast<char*>(returned));
            resolved[1]=replacement;expected[1]=expected[2];
        } else {
            char* returned=EntryRelayContentGetMountedFilePathCallback(reinterpret_cast<void*>(1),requests[1].c_str());
            CHECK(returned && synthetic[1]==returned);DeleteArray(returned);
        }
    }
    // PNG入口会预转码，清空它保证这里也走真实读取/转码，而非只验登记。
    g_ImagePcxCache=decltype(g_ImagePcxCache)(ImagePcxCacheBytesOf{},kImagePcxCacheBudgetBytes);
    opens.clear();
    if(unknown) {
        Image image{};const int before=feeds;
        const auto misses=g_imagePcxDiag.ringMiss;
        const auto absent="rom:/isaac_mods/mods/UnknownOwner/content/gfx/charactermenu.pcx";
        CHECK(!EntryRelayImagePcxLoadCallback(&image,absent));
        CHECK(feeds==before && image.bytes.empty() && opens.empty());
        CHECK(g_imagePcxDiag.ringMiss==misses+1);
        CHECK(!EntryRelayImagePcxLoadCallback(&image,"charactermenu.pcx"));
        CHECK(feeds==before && opens.empty());
        std::puts("UNKNOWN_OWNER_NOT_OPENED");return 0;
    }
    for(int pass=0;pass<2;++pass)for(int i=0;i<3;++i) {
        const auto consumerPath=originalRequest ? requests[i].substr(0,requests[i].size()-4)+".pcx" : synthetic[i];
        const auto query=cleaned ? Clean(consumerPath) : consumerPath;
        const auto count=opens.size();
        Image image{};CHECK(EntryRelayImagePcxLoadCallback(&image,query.c_str()));
        if(image.bytes!=expected[i]) { std::fprintf(stderr,"WRONG_OWNER %s pass=%d\n",owners[i],pass);return 2; }
        if(pass==0) {
            CHECK(opens.size()>count);
            for(std::size_t n=count;n<opens.size();++n)CHECK(opens[n]==resolved[i]);
        } else CHECK(opens.size()==count);
        // 第一轮真实转码；第二轮真实缓存Feed，二者都不得串图。
        std::printf("OWNER_OK %s pass=%d pcxBytes=%zu\n",owners[i],pass,image.bytes.size());
        if(pass==0 && !actual && !repeated) {
            std::ofstream(std::string(owners[i])+".pcx",std::ios::binary).write(reinterpret_cast<const char*>(image.bytes.data()),image.bytes.size());
        }
    }
    CHECK(g_imagePcxDiag.cacheConversions==3 && g_imagePcxDiag.cacheHits==3 && feeds==6);
    std::puts("FULL_PATH_ROUTE_OK");return 0;
}
'''


def png_rgba(color):
    width=height=1024  # 生产PNG直改道的最小像素门槛，不改门槛。
    def chunk(kind,data):
        return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data)&0xffffffff)
    raw=(b'\0'+bytes(color)*width)*height
    return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',width,height,8,6,0,0,0))+chunk(b'IDAT',zlib.compress(raw))+chunk(b'IEND',b'')


def first_pixel(pcx):
    values=[];i=128
    stride=struct.unpack_from('<H',pcx,66)[0]
    while len(values)<stride*4:
        value=pcx[i];i+=1
        count=1
        if value>=192:
            count=value&63;value=pcx[i];i+=1
        values.extend([value]*count)
    # PCX每行按R/G/B/A分平面；独立取各平面的首像素核对原PNG颜色。
    return [values[plane*stride] for plane in range(4)]


class ModImageFullPathIdentityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(prefix='image-path-identity-')
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.work=Path(cls.tmp.name)
        source=(ROOT/'runtime/source/hook_manager.cpp').read_text().split('EarlyModMountOutcome MountModsBeforeHeavyWorkImpl(',1)[1]
        prefix=source[source.index('{')+1:source.index('    isaac::runtime::GameFileReaderAdapter content')]
        prefix=re.sub(r'//[^\n]*','',prefix)
        driver=cls.work/'driver.cpp'
        driver.write_text(ROUTE_DRIVER.replace('@STARTUP_PREFIX@',prefix).replace('@PREP_INCLUDE@','#include "mod_image_resources.hpp"'))
        cls.binary=cls.work/'test'
        cmd=['c++','-std=c++20','-O0','-I',str(ROOT/'runtime/source'),'-I',str(ROOT/'runtime/src'),str(driver),str(ROOT/'runtime/source/mod_resource_redirect.cpp'),str(ROOT/'runtime/src/infrastructure/content/png_to_pcx_bridge.cpp'),str(ROOT/'runtime/src/application/mod/content_mount_service.cpp'),str(ROOT/'runtime/source/mod_image_resources.cpp'),'-lz','-o',str(cls.binary)]
        result=subprocess.run(cmd,text=True,capture_output=True)
        assert result.returncode==0,result.stdout+result.stderr
        cls.colors=((211,22,33,255),(44,177,66,255),(77,88,199,255))
        cls.pngs=[]
        for i,color in enumerate(cls.colors):
            path=cls.work/f'owner{i}.png';path.write_bytes(png_rgba(color));cls.pngs.append(path)

    def run_route(self,scenario,pngs=None):
        result=subprocess.run([str(self.binary),scenario,*map(str,pngs or self.pngs)],cwd=self.work,text=True,capture_output=True)
        print(result.stdout+result.stderr,end='')
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        return result.stdout

    def test_both_registration_branches_keep_owner_pixels(self):
        for branch in ('pcx','png'):
            with self.subTest(branch=branch):
                self.run_route(branch+'-owners')
                for owner,color in zip(('Babyl','RepTemplate','TemplateChar'),self.colors):
                    self.assertEqual(first_pixel((self.work/(owner+'.pcx')).read_bytes()),list(color))

    def test_native_load_image_consumes_original_request_after_freeing_mounted_path(self):
        # 原生LoadImage@4D2140释放挂载返回值，4D214C清洗原始请求，4D2268仍将它喂给Load。
        for scenario in ('pcx-request', 'pcx-request-clean', 'pcx-request-long', 'pcx-request-repeat'):
            with self.subTest(scenario=scenario): self.run_route(scenario)

    def test_cleaned_case_and_separators(self):
        for branch in ('pcx','png'):
            with self.subTest(branch=branch): self.run_route(branch+'-clean')

    def test_duplicate_registration(self):
        for branch in ('pcx','png'):
            with self.subTest(branch=branch): self.run_route(branch+'-repeat')

    def test_unknown_owner_and_basename_do_not_open_any_image(self):
        for branch in ('pcx','png'):
            with self.subTest(branch=branch): self.run_route(branch+'-unknown')

    def test_long_directories_do_not_share_truncated_route_or_cache_keys(self):
        for branch in ('pcx','png'):
            with self.subTest(branch=branch): self.run_route(branch+'-long')

    def test_actual_three_mod_images_keep_individual_converted_bytes(self):
        fixture=ROOT/'dist/change-archive-20261012/442-console-resource-handle/character-assets-readback'
        pngs=[fixture/'Babyl/gfx/charactermenu.png',fixture/'RepTemplate/gfx/CharacterMenu.png',fixture/'TemplateChar/gfx/CharacterMenu.png']
        self.run_route('pcx-actual',pngs)


if __name__=='__main__': unittest.main()
