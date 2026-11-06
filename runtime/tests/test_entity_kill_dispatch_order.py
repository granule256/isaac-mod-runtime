"""Death listeners observe a completed native death and can revive the entity."""
from pathlib import Path
import subprocess,tempfile,unittest
ROOT=Path(__file__).resolve().parents[2]
PROGRAM=r'''
#include <cstdio>
#if __has_include("application/callback/entity_kill_dispatch.hpp")
#include "application/callback/entity_kill_dispatch.hpp"
#else
namespace isaac::runtime {
template<class ReadDead,class Kill,class Dispatch>
void CompleteEntityKill(const ReadDead&,const Kill& kill,const Dispatch& dispatch) {
 dispatch();kill();
}
}
#endif
int main(){
 bool dead=false;int nativeCalls=0,callbacks=0,reads=0;bool observedDead=false;
 auto read=[&]{++reads;return dead;};auto kill=[&]{++nativeCalls;dead=true;};
 auto revive=[&]{++callbacks;observedDead=dead;dead=false;};
 isaac::runtime::CompleteEntityKill(read,kill,revive);
 if(dead||!observedDead||callbacks!=1||nativeCalls!=1){
  std::puts("native death overwrote callback revival or listener observed living entity");return 1;
 }
 dead=true;
 isaac::runtime::CompleteEntityKill(read,kill,revive);
 if(!dead||callbacks!=1||nativeCalls!=2)return 2;
 dead=false;
 isaac::runtime::CompleteEntityKill(read,kill,[&]{++callbacks;});
 if(!dead||callbacks!=2||nativeCalls!=3)return 3;
 // Native blood effects may themselves revive it. PC still dispatches the
 // death event, using the original snapshot rather than a second dead read.
 dead=false;
 isaac::runtime::CompleteEntityKill(read,[&]{dead=true;dead=false;},[&]{++callbacks;});
 return callbacks==3&&reads==4?0:4;
}
'''
class EntityKillDispatchOrderTests(unittest.TestCase):
 def test_native_death_precedes_revive_and_repeated_kill_does_not_redispatch(self):
  with tempfile.TemporaryDirectory(prefix='isaac-kill-order-')as temp:
   p=Path(temp);(p/'test.cpp').write_text(PROGRAM)
   subprocess.run(['c++','-std=c++20','-Wall','-Wextra','-Werror','-I',str(ROOT/'runtime/src'),str(p/'test.cpp'),'-o',str(p/'test')],check=True,capture_output=True)
   r=subprocess.run([str(p/'test')],capture_output=True,text=True)
   self.assertEqual(r.returncode,0,r.stdout+r.stderr)
