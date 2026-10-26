"""编译生产同步加载驱动，复现未完成步返回false导致只执行Prepare的问题。"""
from pathlib import Path
import subprocess,tempfile,unittest
ROOT=Path(__file__).resolve().parents[2]
class DefaultManifestSyncReloadTests(unittest.TestCase):
 def test_production_driver_finishes_pending_steps_and_preserves_failures(self):
  text=(ROOT/'runtime/source/hook_manager.cpp').read_text();start=text.index('bool InitializeDefaultManifestMod(u32* failureDetail) {');end=text.index('// File-scope so nothing depends',start);function=text[start:end]
  harness=r'''
#include <cstdint>
#include <cassert>
using u32=std::uint32_t;
enum class DefaultManifestFailureDetail:u32{None=0};
int steps=0,target=0;bool finished=false,success=false;
bool DefaultManifestLoadFinished(){return finished;}
bool LoadDefaultManifestModThroughService(u32* detail){++steps;if(steps==target){finished=true;*detail=success?0:77;return success;}return false;}
'''+function+r'''
int main(){
 u32 detail=123;
 for(int n: {1,5,37}) {steps=0;target=n;finished=false;success=true;assert(InitializeDefaultManifestMod(&detail));assert(finished&&steps==n&&detail==0);}
 steps=0;target=3;finished=false;success=false;assert(!InitializeDefaultManifestMod(&detail));assert(finished&&steps==3&&detail==77);
 steps=0;target=999;finished=false;success=true;assert(!InitializeDefaultManifestMod(&detail));assert(!finished&&steps==64);
}
'''
  harness='#include <initializer_list>\n'+harness
  with tempfile.TemporaryDirectory()as tmp:
   src=Path(tmp)/'main.cpp';binary=Path(tmp)/'check';src.write_text(harness)
   r=subprocess.run(['c++','-std=c++17','-Wall','-Wextra','-Werror',str(src),'-o',str(binary)],capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
   r=subprocess.run([str(binary)],capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
if __name__=='__main__':unittest.main()
