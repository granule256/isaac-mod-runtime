"""NS FreeGraphicsMemory只排队：旧代与旧字体必须在GPU完成后真实归还，再允许新代分配。"""
from pathlib import Path
import subprocess,tempfile,unittest,re,struct
ROOT=Path(__file__).resolve().parents[2]
HARNESS=r'''
#include "mod_reload_native.hpp"
#include <cassert>
#include <vector>
struct Pool {
 unsigned used=900,pending=500,oldFonts=250;bool gpuBusy=true,failWait=false;std::vector<int> trace;
 bool WaitForGpu(){trace.push_back(1);if(failWait)return false;gpuBusy=false;return true;}
 void ReleaseLanguageFonts(){assert(!gpuBusy);trace.push_back(2);pending+=oldFonts;oldFonts=0;}
 bool ReclaimDeferred(){assert(!gpuBusy);trace.push_back(3);used-=pending;pending=0;return true;}
 bool Allocate(unsigned n){if(used+n>1000)return false;used+=n;return true;}
};
int main(){
 // 仍排队的旧代使新增400失败；本体250字体尚在，必须一起卸载归还。
 Pool old;assert(!old.Allocate(400));
 Pool p;assert(isaac::runtime::ReclaimModReloadGraphics(p));assert(p.used==150&&p.pending==0&&p.oldFonts==0);assert(p.Allocate(400));assert(p.Allocate(250));
 assert((p.trace==std::vector<int>{1,2,3}));
 Pool failed;failed.failWait=true;assert(!isaac::runtime::ReclaimModReloadGraphics(failed));assert(failed.used==900&&failed.pending==500&&failed.oldFonts==250);assert(failed.trace.size()==1);
 // 多轮重载不累积旧代显存；正常更新中不调用此边界。
 for(int i=0;i<20;++i){Pool cycle;assert(isaac::runtime::ReclaimModReloadGraphics(cycle));assert(cycle.Allocate(650));assert(cycle.used==800);}
}
'''
class ModReloadGraphicsReclaimTests(unittest.TestCase):
 def test_queued_old_generation_is_reclaimed_before_new_allocations(self):
  with tempfile.TemporaryDirectory(prefix='reload-gfx-')as tmp:
   p=Path(tmp);(p/'main.cpp').write_text(HARNESS)
   r=subprocess.run(['c++','-std=c++17','-Wall','-Wextra','-Werror','-I',str(ROOT/'runtime/source'),str(p/'main.cpp'),'-o',str(p/'check')],text=True,capture_output=True)
   self.assertEqual(r.returncode,0,r.stdout+r.stderr)
   r=subprocess.run([str(p/'check')],text=True,capture_output=True);self.assertEqual(r.returncode,0,r.stdout+r.stderr)

 def test_language_font_offsets_and_whole_unload_sequence_match_fixed_nro(self):
  h=(ROOT/'runtime/source/mod_reload_native.hpp').read_text()
  b=next(ROOT.glob('The Binding*/Program #0/1/.nro/Repentance.nro')).read_bytes()
  expected=[]
  for delta in [0,24,44,64,84]:
   lo,hi=struct.unpack_from('<II',b,0x3f4aa0+delta)
   self.assertEqual(lo&0xffe0001f,0x52800008)
   self.assertEqual(hi&0xffe0001f,0x72a00008)
   expected.append(((lo>>5)&0xffff)|(((hi>>5)&0xffff)<<16))
  row=re.search(r'kReloadLanguageFontOffsets\{\{([^}]+)',h)[1]
  self.assertEqual([int(x.strip(),16)for x in row.split(',')],expected)
  guard=re.search(r'kReloadLanguageFontGuard\{\{([^}]+)',h)[1]
  self.assertEqual(bytes(int(x.strip(),16)for x in guard.split(',')),b[0x3f4aa0:0x3f4b08])
 def test_production_glue_waits_before_lua_close_and_reclaims_before_loading(self):
  hook=(ROOT/'runtime/source/hook_manager.cpp').read_text()
  self.assertIn('modmenu::WaitEngineGraphicsForModReload() && LuaRuntime::ShutdownForModReload()',hook)
  src=(ROOT/'runtime/source/mod_menu_native.cpp').read_text()
  release=src[src.index('bool ReleaseModReloadNative()'):src.index('bool LoadCycleShaders(')]
  self.assertIn('ReclaimModReloadGraphics(graphics)',release)
  self.assertIn('kReloadLanguageFontGuard.data()',src)
  self.assertIn('ReloadQueueFlush)(queue)',src)
  self.assertIn('ReloadQueueSync)(queue)',src)
  self.assertIn('ReclaimGraphicsMemory)(memory)',src)
