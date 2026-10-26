"""离线执行生产重载协调器：顺序、失败、重入与重复退出。"""
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HARNESS = r'''
#include "mod_reload_cycle.hpp"
#include <cassert>
#include <string>
using namespace isaac::runtime;
struct Operations {
 ModReloadState* state{};std::string trace;unsigned fail{};bool nested{};
 bool Step(unsigned n,char value){trace+=value;if(nested&&n==6){nested=false;assert(!ApplyModMenuReload(true,*state,*this));}return n!=fail;}
 bool Preflight(){return Step(1,'P');}
 bool Save(){return Step(2,'S');}
 bool CloseLua(){return Step(3,'C');}
 bool CreateLua(){return Step(4,'I');}
 bool ReleaseNative(){return Step(5,'U');}
 bool Load(){return Step(6,'L');}
};
int main(){
 ModReloadState state{};Operations ops{};ops.state=&state;
 assert(ApplyModMenuReload(false,state,ops)&&ops.trace.empty()&&state.attempts==0);
 assert(ApplyModMenuReload(true,state,ops));assert(ops.trace=="PSCIUL"&&state.completed==1&&!state.running);
 // A second ordinary exit does nothing. Editing back to the original value is still edited.
 ops.trace.clear();assert(ApplyModMenuReload(false,state,ops)&&ops.trace.empty());
 assert(ApplyModMenuReload(true,state,ops)&&state.completed==2);
 for(unsigned fail=1;fail<=6;++fail){
  ops.trace.clear();ops.fail=fail;const auto completed=state.completed;
  assert(!ApplyModMenuReload(true,state,ops));
  assert(ops.trace==std::string("PSCIUL").substr(0,fail));
  assert(state.failure==fail&&state.completed==completed&&!state.running);
  ops.fail=0;ops.trace.clear();assert(ApplyModMenuReload(true,state,ops));
 }
 ops.trace.clear();ops.nested=true;const auto before=state.attempts;
 assert(ApplyModMenuReload(true,state,ops));assert(state.attempts==before+1&&ops.trace=="PSCIUL");
 // No per-frame polling work: another thousand unedited exits never call the backend.
 ops.trace.clear();for(unsigned i=0;i<1000;++i)assert(ApplyModMenuReload(false,state,ops));
 assert(ops.trace.empty());
}
'''

class ModReloadCycleTests(unittest.TestCase):
 def test_real_cycle_order_failure_and_reentry(self):
  header=ROOT/'runtime/source/mod_reload_cycle.hpp'
  self.assertTrue(header.exists(), '缺少退出菜单整轮重载协调器')
  with tempfile.TemporaryDirectory(prefix='isaac-mod-reload-cycle-') as folder:
   source=Path(folder)/'main.cpp';source.write_text(HARNESS)
   binary=Path(folder)/'check'
   compiled=subprocess.run(['c++','-std=c++17','-Wall','-Wextra','-Werror',
    '-I',str(header.parent),str(source),'-o',str(binary)],capture_output=True,text=True)
   self.assertEqual(compiled.returncode,0,compiled.stdout+compiled.stderr)
   result=subprocess.run([str(binary)],capture_output=True,text=True)
   self.assertEqual(result.returncode,0,result.stdout+result.stderr)
