"""256模组的真实菜单状态、持久化、资源重定向边界行为。"""
import subprocess
import tempfile
import unittest
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DRIVER = r'''
#include "interfaces/lua/mod_menu_api.hpp"
#include "application/mod/mod_toggle_service.hpp"
#include "mod_resource_redirect.hpp"
#include <string>
#include <cstring>
#include <cstdio>
using namespace isaac::runtime;
using namespace isaac::runtime::bridge;
namespace isaac::runtime { extern std::uint64_t g_ModReadingRebuilds; }
struct Files : ISaveFilePort {
    std::string data;
    Status Read(std::string_view,char* out,std::size_t n,std::size_t* size) noexcept override {
        if(data.size()>n)return Status{StatusCode::CapacityExceeded};
        std::memcpy(out,data.data(),data.size());*size=data.size();return Status::Ok();
    }
    Status Write(std::string_view,std::string_view text) noexcept override {data=text;return Status::Ok();}
    Status Remove(std::string_view) noexcept override {return Status::Ok();}
    Status Exists(const char*,bool* yes) noexcept override {*yes=false;return Status::Ok();}
};
int failures=0;
void check(bool b,const char* text){if(!b){std::puts(text);++failures;}}
std::string expected;
char answer[512];
char* probe(void*,const char* candidate){
    if(expected!=candidate)return nullptr;
    std::strcpy(answer,"rom:/");std::strcat(answer,candidate);return answer;
}
void release(void*){}
int main(){
    static ResolvedManifestModBatch batch{};
    std::string roots[257];const char* rootPointers[257]{};
    for(unsigned i=0;i<257;++i){
        roots[i]="rom:/isaac_mods/mods/M"+std::to_string(i);
        rootPointers[i]=roots[i].c_str();
        if(i<256)batch.mods[i].modRoot=rootPointers[i];
    }
    batch.count=256;
    ModMenuPublishDiscovered(batch);ModMenuMarkActive(batch);
    Files files;ModToggleService toggles{files};ModMenuAttachToggles(&toggles);
    auto state=ModMenuDiscoveredForReading();
    check(state.count==256 && state.activeBits.words[7]==0xffffffffu,"256_menu_active");
    check(PublishModResourceRedirectList(rootPointers,256),"256_resource_publish");
    for(unsigned i:{31u,32u,63u,64u,255u}){
        const auto name="M"+std::to_string(i);
        check(ModMenuSetEnabled(name.c_str(),false),"boundary_disable");
        expected="isaac_mods/mods/"+name+"/resources/gfx/test.png";
        check(TryRedirectModResource("gfx/test.png",&files,probe,release)==answer,
              "boundary_resource_lookup");
        check(g_ModResourceRedirectState.lastHitMod==i,"boundary_resource_index");
    }
    state=ModMenuDiscoveredForReading();
    for(unsigned i:{31u,32u,63u,64u,255u})
        check(!state.enabledBits.Test(i) && state.activeBits.Test(i),"enabled_active_independent");
    check(ModMenuSaveToggles(),"save_disabled");
    ModToggleService loaded{files};check(loaded.Load().ok(),"reload_disabled");
    ModMenuAttachToggles(&loaded);
    state=ModMenuDiscoveredForReading();
    for(unsigned i:{31u,32u,63u,64u,255u}){
        check(!state.enabledBits.Test(i),"boundary_disabled_persisted");
        const auto name="M"+std::to_string(i);
        check(ModMenuSetEnabled(name.c_str(),true),"boundary_reenable");
    }
    state=ModMenuDiscoveredForReading();
    const auto rebuilds=g_ModReadingRebuilds;
    for(unsigned i=0;i<10000;++i){
        check(ModMenuEnabledCount()==256,"cached_enabled_count");
        check(ModMenuDiscoveredForReading().activeBits.Test(255),"cached_high_active_bit");
    }
    check(g_ModReadingRebuilds==rebuilds,"unchanged_frames_do_not_rebuild_names");
    check(loaded.SetEnabled("M255",false).ok(),"external_service_toggle");
    check(!ModMenuDiscoveredForReading().enabledBits.Test(255),"external_service_invalidates_cache");
    check(ModMenuEnabledCount()==255,"external_count_fresh");
    check(!PublishModResourceRedirectList(rootPointers,257),"257_resource_rejected");
    check(g_ModResourceRedirectState.modCount==256,"overflow_preserves_prior_complete_list");
    batch.count=257;
    ModMenuPublishDiscovered(batch);ModMenuMarkActive(batch);
    state=ModMenuDiscoveredForReading();
    check(state.count==256 && state.activeBits.Test(255),"overflow_menu_preserves_prior_complete_list");
    return failures?1:0;
}
'''

class ModCapacity256Tests(unittest.TestCase):
    def test_real_menu_and_resource_boundaries(self):
        with tempfile.TemporaryDirectory() as tmp:
            src=Path(tmp)/'capacity.cpp';src.write_text(DRIVER)
            binary=Path(tmp)/'capacity'
            flags=['-Wl,-dead_strip'] if sys.platform=='darwin' else ['-Wl,--gc-sections']
            sources=['runtime/src/interfaces/lua/mod_menu_api.cpp',
                     'runtime/src/application/mod/mod_toggle_service.cpp',
                     'runtime/src/domain/mod/mod_toggle_state.cpp',
                     'runtime/source/mod_resource_redirect.cpp']
            built=subprocess.run(['c++','-std=c++17','-Wall','-Wextra','-Werror',
                '-ffunction-sections','-fdata-sections','-Iruntime/src','-Iruntime/source',
                '-Iruntime/source/third_party/lua-5.3.3/src',str(src),*sources,*flags,
                '-o',str(binary)],cwd=ROOT,capture_output=True,text=True)
            self.assertEqual(built.returncode,0,built.stdout+built.stderr)
            ran=subprocess.run([str(binary)],capture_output=True,text=True)
            self.assertEqual(ran.returncode,0,ran.stdout+ran.stderr)

if __name__=='__main__':unittest.main()
