"""Exercise the real redirect resolver: mods cannot shadow runtime-owned notices."""
import shutil,subprocess,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
class NoticeNamespaceTests(unittest.TestCase):
 def test_owned_notice_paths_bypass_mod_candidates_only(self):
  body=r'''
#include "mod_resource_redirect.hpp"
#include <cstring>
#include <string>
using namespace isaac::runtime::bridge;
unsigned probes=0;std::string answer;
char* probe(void*,const char* candidate){++probes;answer="rom:/";answer+=candidate;return answer.data();}
void release(void*){}
int main(){
 const char* roots[]={"isaac_mods/mods/example"};if(!PublishModResourceRedirectList(roots,1))return 1;
 const char* owned[]={"gfx/ui/main menu/isaac-switch/nnotice_zh.pcx","GFX\\UI\\MAIN MENU\\ISAAC-SWITCH\\NNOTICE_EN.ANM2","gfx/ui/main menu/isaac-switch/nnotice.manifest","rom:/rp_patch/resources.zh/gfx/ui/main menu/isaac-switch/nnotice_zh.pcx","ROM:/RP_PATCH/RESOURCES/GFX/UI/MAIN MENU/ISAAC-SWITCH/NNOTICE_EN.PNG"};
 for(auto* name:owned)if(TryRedirectModResource(name,nullptr,probe,release)||probes)return 2;
 if(!TryRedirectModResource("gfx/items/normal.pcx",nullptr,probe,release)||probes!=1)return 3;
 return 0;
}
'''
  with tempfile.TemporaryDirectory(prefix='notice-owned-')as tmp:
   p=Path(tmp);(p/'test.cpp').write_text(body)
   r=subprocess.run([shutil.which('c++'),'-std=c++17','-Wall','-Werror','-I',str(ROOT/'runtime/source'),str(p/'test.cpp'),str(ROOT/'runtime/source/mod_resource_redirect.cpp'),'-o',str(p/'test')],capture_output=True,text=True)
   self.assertEqual(r.returncode,0,r.stdout+r.stderr)
   r=subprocess.run([str(p/'test')],capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
if __name__=='__main__':unittest.main()
