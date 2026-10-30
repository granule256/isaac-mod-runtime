"""Fast host checks for locale selection, actual resource lifecycle, and read-state changes."""
import shutil,subprocess,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
HARNESS=r'''
#include "title_notice_language.hpp"
#include "title_notice_state.hpp"
#include <cstdio>
#include <vector>
using namespace isaac::runtime::notice;
int errors=0;void check(bool x,const char*message){if(!x){std::printf("FAIL %s\n",message);++errors;}}
struct Ops{
 bool ready=true;unsigned live=0,maxLive=0,constructs=0,destroys=0,loads=0,assigned=0,failAt=99;
 std::vector<char> order;
 bool BindingsReady(){return ready;}
 void AssignPath(unsigned){++assigned;order.push_back('p');}
 void Construct(unsigned){++live;++constructs;if(live>maxLive)maxLive=live;order.push_back('c');}
 bool Load(unsigned i){++loads;order.push_back('l');return i!=failAt;}
 void Destroy(unsigned){--live;++destroys;order.push_back('d');}
};
void tick(State&s,unsigned key=0,unsigned n=1,unsigned pages=3){while(n--)s.Tick(key,true,true,pages);}
int main(){
 const char*codes[]={"en","de","es","fr","jp","kr","ru","zh"};
 for(unsigned i=0;i<8;++i)check(LanguageIndex(codes[i])==i,"all native language codes");
 check(LanguageIndex("ja")==4&&LanguageIndex("ko")==5,"common aliases");
 check(LanguageIndex(nullptr)==0&&LanguageIndex("")==0&&LanguageIndex("x")==0&&LanguageIndex("xx")==0,"unknown to English");
 {ResourceCycle r;Ops o;o.ready=false;check(!r.Select(7,o)&&o.constructs==0,"wait for bindings without allocation");o.ready=true;
  check(r.Select(7,o)&&o.live==5&&r.generation==1,"first language loads five native sprites");
  for(int i=0;i<120;++i)check(r.Select(7,o),"same locale remains ready");
  check(o.loads==5&&o.assigned==1,"steady frames never load or assign paths");
  auto start=o.order.size();check(r.Select(0,o),"switch language");
  check(o.destroys==5&&o.constructs==10&&o.live==5&&o.maxLive==5,"release old before constructing new");
  check(o.order[start]=='d'&&o.order[start+4]=='d'&&o.order[start+5]=='p',"release precedes path assignment");
  o.failAt=1;check(!r.Select(3,o)&&o.live==0,"partial failure cleans all native objects");
  auto calls=o.loads;check(!r.Select(3,o)&&o.loads==calls,"failure is not retried every frame");
  o.failAt=99;check(r.Select(1,o)&&o.live==5,"another language may recover");r.Release(o);check(o.live==0,"explicit release");}
 {State s;s.SetSeenVersion(false);tick(s,0,30);tick(s,Right);tick(s,0,12);tick(s,Back,20);
  s.ResetForLanguage();check(s.phase==Phase::Opening&&s.page==0&&s.requiresHold&&s.ViewedPagesMask()==0&&s.holdTicks==0,"automatic locale change resets read progress");
  tick(s,0,30,4);tick(s,Back,80,4);check(s.phase==Phase::Reading&&!s.ConsumeAcknowledgement(),"old visited pages cannot unlock new four-page translation");}
 {State s;s.SetSeenVersion(true);tick(s);s.ResetForLanguage();tick(s,0,60);check(s.phase==Phase::Hidden,"seen version never reopens just for language change");
  tick(s,Right);tick(s);tick(s,Confirm);tick(s,0,30);tick(s,Right);s.ResetForLanguage();
  check(s.phase==Phase::Opening&&!s.requiresHold,"manual mode survives locale change");
  tick(s,Back);tick(s,0,60);check(s.phase==Phase::Hidden&&!s.ConsumeAcknowledgement(),"manual B still closes without full reading or save write");}
 return errors?1:0;
}
'''
class NoticeLanguageTests(unittest.TestCase):
 def test_mapping_resource_release_and_read_progress(self):
  self.assertTrue((ROOT/'runtime/source/title_notice_language.hpp').exists(),'locale support missing')
  with tempfile.TemporaryDirectory(prefix='notice-language-')as tmp:
   p=Path(tmp);(p/'test.cpp').write_text(HARNESS)
   r=subprocess.run([shutil.which('c++'),'-std=c++17','-Wall','-Wextra','-Werror','-I',str(ROOT/'runtime/source'),str(p/'test.cpp'),'-o',str(p/'test')],capture_output=True,text=True)
   self.assertEqual(r.returncode,0,r.stdout+r.stderr)
   r=subprocess.run([str(p/'test')],capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
if __name__=='__main__':unittest.main()
