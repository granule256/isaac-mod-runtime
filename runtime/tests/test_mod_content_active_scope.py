"""实际开关过滤后的批次，必须同时决定脚本与原生内容的加载资格。"""
import re, subprocess, tempfile, unittest
from pathlib import Path
from .test_support import build_lua_harness
ROOT=Path(__file__).resolve().parents[2]
MAIN=r'''
#include "interfaces/lua/mod_menu_api.hpp"
#include "application/mod/mod_toggle_service.hpp"
#include <cstring>
#include <string>
using namespace isaac::runtime;
struct Files:ISaveFilePort {
 unsigned queries=0;
 Status Read(std::string_view,char*,std::size_t,std::size_t*)noexcept override{return Status{StatusCode::NotFound};}
 Status Write(std::string_view,std::string_view)noexcept override{return Status::Ok();}
 Status Remove(std::string_view)noexcept override{return Status::Ok();}
 Status Exists(const char* p,bool* out)noexcept override{++queries;*out=std::string(p).find("Twitch/disable.it")!=std::string::npos;return Status::Ok();}
};
int main(){
 Files files;ModToggleService toggles(files);ModMenuAttachToggles(&toggles);
 ResolvedManifestModBatch batch{};
 const char* roots[]={"rom:/isaac_mods/mods/StageAPI","rom:/isaac_mods/mods/Twitch","rom:/isaac_mods/mods/AssetsOnly","rom:/isaac_mods/mods/SavedOff"};
 batch.count=4;for(unsigned i=0;i<4;++i){std::strcpy(batch.paths[i].modRoot.data(),roots[i]);batch.mods[i].modRoot=batch.paths[i].modRoot.data();}
 if(!toggles.SetEnabled("SavedOff",false).ok())return 10;
 ModMenuPublishDiscovered(batch);if(toggles.ApplyToBatch(&batch)!=2)return 11;ModMenuMarkActive(batch);
 // 菜单开关表示下次启动的意图；内容只允许使用本次过滤后的结果。
 if(!toggles.SetEnabled("SavedOff",true).ok()||!toggles.SetEnabled("StageAPI",false).ok())return 12;
 const unsigned before=files.queries;
 unsigned loaded=0;const std::size_t modCount=ModMenuDiscoveredCount();
 @SNAPSHOT@
 for(std::size_t index=0;index<modCount;++index){
  const char* directory=ModMenuDiscoveredDirectory(index);
  if(@CONDITION@)continue;
  if(!std::strcmp(directory,"Twitch")||!std::strcmp(directory,"SavedOff"))return 81;
  ++loaded;
 }
 if(loaded!=2||files.queries!=before)return 82;
 return 0;
}
'''
class ModContentActiveScopeTests(unittest.TestCase):
 def test_native_content_obeys_filtered_batch_including_resource_only_mods(self):
  source=(ROOT/'runtime/source/mod_menu_native.cpp').read_text()
  start=source.index('const std::size_t modCount = isaac::runtime::ModMenuDiscoveredCount();',source.index('bool LoadEngineModContent('))
  end=source.index('const std::size_t directoryLength',start)
  consumer=source[start:end]
  condition=re.search(r'if \((.*?)\) \{\s*continue;',consumer,re.S).group(1)
  snapshot=consumer.split('for (std::size_t index',1)[0].replace('const std::size_t modCount = isaac::runtime::ModMenuDiscoveredCount();','')
  main=MAIN.replace('@SNAPSHOT@',snapshot).replace('@CONDITION@',condition)
  with tempfile.TemporaryDirectory(prefix='mod-content-active-')as folder:
   exe=build_lua_harness(source_root=ROOT/'runtime/source',workdir=Path(folder),harness_source=main)
   result=subprocess.run([str(exe)],capture_output=True,text=True)
   self.assertEqual(result.returncode,0,result.stdout+result.stderr)
