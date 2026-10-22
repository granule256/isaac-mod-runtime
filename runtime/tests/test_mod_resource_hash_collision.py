"""执行生产重定向，重现真机怀表候选与左手文件的DJB2碰撞。"""
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DRIVER = r'''
#include "mod_resource_redirect.hpp"
#include <cstdlib>
#include <cstring>
#include <string>
#include <set>
using namespace isaac::runtime::bridge;
std::set<void*> live;
unsigned frees=0;
char* Copy(const char* s){auto* p=new char[std::strlen(s)+1];std::strcpy(p,s);live.insert(p);return p;}
void Release(void* p){if(live.erase(p)!=1)std::abort();++frees;delete[] static_cast<char*>(p);}
unsigned Hash(const std::string& s){unsigned h=5381;for(unsigned char c:s){if(c=='\\')c='/';if(c>='A'&&c<='Z')c+=32;h=h*33+c;}return h;}
const char* watch="gfx/items/collectibles/collectibles_232_stopwatch.pcx";
const char* left="gfx/items/trinkets/trinket_061_thelefthand.pcx";
const char* candidate="isaac_mods/mods/goodtripfixed/resources/gfx/items/collectibles/collectibles_232_stopwatch.pcx";
int mode=0;
char* Probe(void*,const char* q){
 if(mode==0 || mode==1){
  // 与原生FileMap相同：只比较哈希，错误地返回原版左手。
  if(Hash(q)==Hash(left))return Copy("rom:/resources/gfx/items/trinkets/trinket_061_thelefthand.pcx");
  if(mode==1 && std::string(q)==std::string("isaac_mods/mods/real/resources/")+watch)
   return Copy((std::string("rom:/")+q).c_str());
 }else if(std::strcmp(q,candidate)==0){
  if(mode==2)return Copy("rom:/ISAAC_MODS\\MODS\\GOODTRIPFIXED\\RESOURCES\\GFX\\ITEMS\\COLLECTIBLES\\COLLECTIBLES_232_STOPWATCH.PCX");
  if(mode==3)return Copy((std::string("rom:/")+q+".other").c_str());
 }
 return nullptr;
}
int main(int argc,char** argv){
 mode=std::atoi(argv[1]);
 if(Hash(candidate)!=Hash(left) || Hash(candidate)!=0x2cdc96e3u)return 20;
 const char* roots[]={"isaac_mods/mods/goodtripfixed","isaac_mods/mods/real"};
 PublishModResourceRedirectList(roots,2);
#ifdef WITH_RELEASE_API
 char* result=TryRedirectModResource(watch,nullptr,Probe,Release);
#else
 char* result=TryRedirectModResource(watch,nullptr,Probe);
#endif
 if(mode==0 || mode==3){if(result!=nullptr)return 21;if(frees!=1 || !live.empty())return 22;}
 if(mode==1){if(!result || std::string(result)!=std::string("rom:/isaac_mods/mods/real/resources/")+watch)return 23;if(frees!=1 || live.size()!=1)return 24;Release(result);}
 if(mode==2){if(!result || frees!=0 || live.size()!=1)return 25;Release(result);}
 return live.empty()?0:26;
}
'''


class ModResourceHashCollisionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        source = Path(cls.temp.name) / 'main.cpp'
        source.write_text(DRIVER)
        cls.exe = Path(cls.temp.name) / 'probe'
        header = (ROOT / 'runtime/source/mod_resource_redirect.hpp').read_text()
        flags = ['-DWITH_RELEASE_API'] if 'ReleaseMountedFilePathFn' in header else []
        subprocess.run(['c++', '-std=c++20', '-O2', *flags, '-I'+str(ROOT/'runtime/source'),
                        str(source), str(ROOT/'runtime/source/mod_resource_redirect.cpp'),
                        '-o', str(cls.exe)], check=True, capture_output=True)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def run_mode(self, mode):
        result = subprocess.run([str(self.exe), str(mode)], capture_output=True)
        self.assertEqual(result.returncode, 0, f'场景{mode}，返回码{result.returncode}')

    def test_real_watch_left_hand_collision_is_not_a_mod_override(self):
        self.run_mode(0)

    def test_collision_is_released_and_search_continues_to_real_override(self):
        self.run_mode(1)

    def test_case_and_slash_normalization_keeps_real_override_and_ownership(self):
        self.run_mode(2)

    def test_matching_prefix_with_extra_filename_suffix_is_rejected(self):
        self.run_mode(3)


if __name__ == '__main__':
    unittest.main()
