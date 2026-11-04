import pathlib
import shutil
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
HARNESS = r'''
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <string>
#include <vector>
#if __has_include("infrastructure/content/pcx_cache_codec.hpp")
#include "infrastructure/content/pcx_cache_codec.hpp"
using isaac::runtime::content::PackPcxCachePlanes;
using isaac::runtime::content::UnpackPcxCachePlanes;
using isaac::runtime::content::MeasurePcxCachePlanes;
#else
bool PackPcxCachePlanes(const std::uint8_t*,std::size_t,std::uint8_t*,std::size_t,std::size_t*){return false;}
bool UnpackPcxCachePlanes(const std::uint8_t*,std::size_t,std::uint8_t*,std::size_t){return false;}
std::size_t MeasurePcxCachePlanes(const std::uint8_t*,std::size_t){return 0;}
#endif
using Bytes=std::vector<std::uint8_t>;
void word(Bytes& b,std::size_t at,unsigned v){b[at]=v;b[at+1]=v>>8;}
Bytes image(bool color,bool runs) {
 const unsigned width=129,height=9;
 Bytes b(128);b[0]=10;b[1]=5;b[2]=1;b[3]=8;b[65]=4;word(b,8,width-1);word(b,10,height-1);word(b,66,width);
 for(unsigned y=0;y<height;++y)for(unsigned p=0;p<4;++p) {
  Bytes plane(width);
  for(unsigned x=0;x<width;++x)plane[x]=runs?(p<3?240:7):(color?(x*47+y*31+p*43)&255:((p<3?x+y:x*5+y)&255));
  for(unsigned x=0;x<width;) {
   unsigned n=1;while(x+n<width&&n<63&&plane[x+n]==plane[x])++n;
   if(n>1||plane[x]>=192)b.push_back(192|n);
   b.push_back(plane[x]);x+=n;
  }
 }
 return b;
}
int main(int argc,char**argv) {
 const std::string mode=argv[1];auto source=image(mode=="color",mode=="runs");auto saved=source;
 Bytes packed(source.size()+32,0xa5);std::size_t length=0;
 if(mode=="capacity") {
  assert(!PackPcxCachePlanes(source.data(),source.size(),packed.data(),128,&length));
  for(std::size_t i=128;i<packed.size();++i)assert(packed[i]==0xa5);
  assert(source==saved);return 0;
 }
 if(mode=="invalid_input") {
  source[65]=3;assert(!PackPcxCachePlanes(source.data(),source.size(),packed.data(),packed.size(),&length));
  source=saved;source[128]=192;assert(!PackPcxCachePlanes(source.data(),source.size(),packed.data(),packed.size(),&length));return 0;
 }
 assert(PackPcxCachePlanes(source.data(),source.size(),packed.data(),packed.size(),&length));
 assert(MeasurePcxCachePlanes(source.data(),source.size())==length);
 assert(source==saved);
 if(mode=="gray")assert(length<source.size()*3/5);
 Bytes result(source.size()+16,0xa5);
 if(mode=="corrupt") {
  packed[128]|=1;assert(!UnpackPcxCachePlanes(packed.data(),length,result.data(),source.size()));return 0;
 }
 if(mode=="truncated") {
  assert(!UnpackPcxCachePlanes(packed.data(),length-1,result.data(),source.size()));
  assert(!UnpackPcxCachePlanes(packed.data(),length,result.data(),source.size()-1));return 0;
 }
 assert(UnpackPcxCachePlanes(packed.data(),length,result.data(),source.size()));
 assert(std::memcmp(source.data(),result.data(),source.size())==0);
 for(std::size_t i=source.size();i<result.size();++i)assert(result[i]==0xa5);
 return 0;
}
'''

class PcxCacheCodecTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        source = pathlib.Path(cls.tmp.name) / 'codec.cpp'
        source.write_text(HARNESS)
        cls.binary = source.with_suffix('')
        subprocess.run([shutil.which('clang++') or 'c++', '-std=c++17', '-O2',
                        '-I', str(ROOT / 'src'), str(source), '-o', str(cls.binary)], check=True)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_lossless_rows_and_failure_bounds(self):
        for mode in ['gray', 'color', 'runs', 'capacity', 'invalid_input', 'corrupt', 'truncated']:
            with self.subTest(mode=mode):
                run = subprocess.run([str(self.binary), mode], capture_output=True, text=True)
                self.assertEqual(run.returncode, 0, run.stderr)

if __name__ == '__main__':
    unittest.main()
