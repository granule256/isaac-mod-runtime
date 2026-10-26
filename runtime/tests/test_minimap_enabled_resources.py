"""执行实际早发布段：关闭的MinimapAPI不能替换本体，开启时必须能覆盖。"""
import re
import subprocess
import tempfile
import unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
DRIVER = r"""
#include "application/mod/mod_toggle_service.hpp"
#include "mod_resource_redirect.hpp"
#include <cstdio>
#include <cstdlib>
#include <cstring>
using namespace isaac::runtime;
struct Save final : ISaveFilePort {
 bool allowed=false, marker=false, missing=false, failed=false;
 int reads=0, writes=0; const char* state="isaac-switch-mods 1\noff minimapi\noff EID\n";
 void AllowFromGameThread() { allowed=true; }
 Status Read(std::string_view, char* out, std::size_t cap, std::size_t* size) noexcept override {
  ++reads; if(!allowed) return Status{StatusCode::Unsupported};
  if(failed) return Status{StatusCode::IoFailure};
  if(missing) return Status{StatusCode::NotFound};
  *size=std::strlen(state); if(*size>cap) return Status{StatusCode::CapacityExceeded};
  std::memcpy(out,state,*size); return Status::Ok();
 }
 Status Write(std::string_view,std::string_view) noexcept override {++writes; return Status::Ok();}
 Status Remove(std::string_view) noexcept override {++writes; return Status::Ok();}
 Status Exists(const char* path,bool* exists) noexcept override {
  *exists=marker && std::strstr(path,"minimapi/disable.it");return Status::Ok();
 }
} g_SaveFileAdapter;
ModToggleService g_ModToggleService{g_SaveFileAdapter};
unsigned g_ModToggleStateLoaded=0;
struct Outcome { bool attempted=false; std::size_t mountsAttempted=0,mountsFailed=0; };
struct TargetModule {};
namespace isaac::runtime::modmenu {
 bool sortOk=true; unsigned sortCalls=0;
 bool SortAndPublishDiscoveredMods(const TargetModule&, ResolvedManifestModBatch&) {
  ++sortCalls; return sortOk;
 }
}
Outcome Publish(ResolvedManifestModBatch& batch) {
 TargetModule module{};
 Outcome outcome{};
 @EARLY_SEGMENT@
}
char answer[]="rom:/isaac_mods/mods/minimapi/resources/gfx/ui/minimap1.anm2";
char* Probe(void*,const char* candidate) {
 return std::strstr(candidate,"minimapi/resources/gfx/ui/minimap1.anm2") ? answer : nullptr;
}
void Release(void*) { std::abort(); } // 本夹具只有完整匹配，所有权仍交回调用方。
int main(int argc,char** argv) {
 if(argc!=2) return 90;
 int scenario=std::atoi(argv[1]);
 if(scenario==1) g_SaveFileAdapter.state="isaac-switch-mods 1\noff EID\n";
 if(scenario==2) {g_SaveFileAdapter.missing=true;g_SaveFileAdapter.marker=true;}
 if(scenario==3) g_SaveFileAdapter.missing=true;
 if(scenario==4) g_SaveFileAdapter.failed=true;
 if(scenario==5) isaac::runtime::modmenu::sortOk=false;
 static ResolvedManifestModBatch batch{};
 const char* dirs[]={"minimapi","EID"}; batch.count=2;
 for(int i=0;i<2;++i) {
  auto& b=batch.paths[i]; std::snprintf(b.modRoot.data(),b.modRoot.size(),"rom:/isaac_mods/mods/%s",dirs[i]);
  batch.mods[i].modRoot=b.modRoot.data();batch.mods[i].hasEntry=false;
 }
 auto outcome=Publish(batch);
 if(isaac::runtime::modmenu::sortCalls!=1) return 16;
 if(scenario==5) {
  if(outcome.mountsFailed!=1 || g_SaveFileAdapter.reads || g_ModToggleStateLoaded ||
     isaac::runtime::bridge::ModResourceRedirectListPublished()) return 17;
  std::puts("SORT_FAILURE_STOPS_BEFORE_TOGGLE_IO"); return 0;
 }
 auto* result=isaac::runtime::bridge::TryRedirectModResource("gfx/ui/minimap1.anm2",nullptr,Probe,Release);
 const bool wantMod=scenario==1 || scenario==3 || scenario==4;
 if(bool(result)!=wantMod) {std::fprintf(stderr,"MINIMAP_RESOURCE_FAIL scenario=%d disabled mod took original path\n",scenario);return 10;}
 if(g_SaveFileAdapter.reads!=1 || !g_SaveFileAdapter.allowed || !g_ModToggleStateLoaded) return 11;
 if(g_SaveFileAdapter.writes!=0) return 12;
 if(scenario==4 && outcome.mountsFailed!=1) return 13;
 if(scenario==0 && (batch.count!=0 || !isaac::runtime::bridge::ModResourceRedirectListPublished())) return 14;
 if(scenario==1 && (batch.count!=1 || result!=answer)) return 15;
 std::puts("MINIMAP_RESOURCE_OK");return 0;
}
"""
class MinimapEnabledResourcesTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.temp=tempfile.TemporaryDirectory(prefix='minimap-enabled-')
  code=(ROOT/'runtime/source/hook_manager.cpp').read_text()
  body=code.split('EarlyModMountOutcome MountModsBeforeHeavyWorkImpl(',1)[1]
  body=body.split('(void)g_ModDiscoveryService.AppendUnlisted(&batch);',1)[1].split('\n    return outcome;\n}',1)[0]+'return outcome;'
  body=re.sub(r'//[^\n]*','',body)
  driver=Path(cls.temp.name)/'driver.cpp';driver.write_text(DRIVER.replace('@EARLY_SEGMENT@',body))
  cls.binary=Path(cls.temp.name)/'test'
  subprocess.run(['c++','-std=c++17','-I',str(ROOT/'runtime/src'),'-I',str(ROOT/'runtime/source'),str(driver),str(ROOT/'runtime/src/application/mod/mod_toggle_service.cpp'),str(ROOT/'runtime/src/domain/mod/mod_toggle_state.cpp'),str(ROOT/'runtime/source/mod_resource_redirect.cpp'),'-o',str(cls.binary)],check=True,capture_output=True,text=True)
 @classmethod
 def tearDownClass(cls): cls.temp.cleanup()
 def test_first_read_obeys_saved_toggle_and_marker(self):
  for scenario in range(5):
   with self.subTest(scenario=scenario):
    r=subprocess.run([str(self.binary),str(scenario)],capture_output=True,text=True)
    self.assertEqual(r.returncode,0,r.stdout+r.stderr)
 def test_sort_failure_stops_before_toggle_io_and_publication(self):
  r=subprocess.run([str(self.binary),'5'],capture_output=True,text=True)
  self.assertEqual(r.returncode,0,r.stdout+r.stderr)
  self.assertIn('SORT_FAILURE_STOPS_BEFORE_TOGGLE_IO',r.stdout)
