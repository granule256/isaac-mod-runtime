"""Publish mod detection only after the enabled native environment is ready."""
import subprocess
import tempfile
import unittest
from pathlib import Path

from . import test_support


SOURCE = Path(__file__).resolve().parents[1] / 'source'
DRIVER = r'''
#include "lua_runtime.hpp"
#include "interfaces/lua/repentogon_callbacks.hpp"
#include "interfaces/lua/repentogon_environment.hpp"
#include "ports/save_file_port.hpp"
extern "C" {
#include <lauxlib.h>
}
#include <cassert>
#include <cstdio>
#include <cstring>
#include <string>
using namespace isaac::runtime;
static bool ready=true, install=true;
static unsigned installs;
static bool Ready() noexcept {return ready;}
static bool Install() noexcept {++installs;return install;}
struct Files final : ISaveFilePort {
    std::string value;
    explicit Files(bool enabled):value(enabled?"isaac-repentogon 1\nenabled 1\n":"isaac-repentogon 1\nenabled 0\n"){}
    Status Read(std::string_view,char* out,std::size_t cap,std::size_t* size) noexcept override {
        *size=value.size();assert(cap>=value.size());std::memcpy(out,value.data(),value.size());return Status::Ok();
    }
    Status Write(std::string_view,std::string_view bytes) noexcept override {value=bytes;return Status::Ok();}
    Status Remove(std::string_view) noexcept override {return Status{StatusCode::Unsupported};}
    Status Exists(const char*,bool*) noexcept override {return Status{StatusCode::Unsupported};}
};
static constexpr char kDetected[]=R"lua(
assert(type(REPENTOGON)=='table', 'enabled native environment must publish detection')
assert(REPENTOGON.Real==true and REPENTOGON.Name=='REPENTOGON')
assert(REPENTOGON.Version=='0.0.0' and REPENTOGON.Implementation=='isaac-switch-runtime')
assert(REPENTOGON.FullCompatibility==false)
assert(type(REPENTOGON.Extras)=='table' and type(REPENTOGON.Extras.Misc)=='table')
assert(REPENTOGON.MeetsVersion('0.0.0') and not REPENTOGON.MeetsVersion('1.0.0'))
assert(not REPENTOGON.MeetsVersion('999.0.0'))
assert(not pcall(REPENTOGON.MeetsVersion,'1..0'))
assert(type(XMLData.GetEntryById)=='function' and type(Console.RegisterCommand)=='function')
assert(type(getmetatable(Level).__class.TryPlaceRoom)=='function')
-- Exercise author-style gates with self-authored consumers, not mod code.
local mod=RegisterMod('identity consumer',1)
if REPENTOGON then
    assert(ModCallbacks.MC_PRE_MEGA_SATAN_ENDING==1201)
    mod:AddCallback(ModCallbacks.MC_POST_MODS_LOADED,function()end)
end
local isRepentogon=REPENTOGON~=nil
assert(isRepentogon and RuntimeMods.GetRepentogonState().Active)
REPENTOGON.Extras.Misc.identityProbe=true
)lua";
static void Start(const char* script) {
    const auto result=LuaRuntime::InitializeFromBuffer(script,std::strlen(script),"@identity.lua");
    if(result!=LuaRuntime::LuaInitResult::Success){
        char error[2048]{};static_cast<void>(LuaRuntime::CopyLastLuaErrorText(error,sizeof(error)));
        std::fprintf(stderr,"%s\n",error);assert(false);
    }
    assert(isaac::runtime::console::AutocompleteDispatchSlot()!=nullptr);
}
int main(int argc,char** argv) {
    assert(argc==2);const std::string mode=argv[1];
    Files files(mode!="off");SetSessionSaveFilePort(&files);LuaRuntime::ObserveGameThread();
    const repentogon::NativePort port{Ready,Install};
    repentogon::SetNativePort(mode=="none"?nullptr:&port);
    ready=mode!="unready";install=mode!="install_fail";
    if(!ready||!install){
        constexpr char author[]="error('author must not run')";
        assert(LuaRuntime::InitializeFromBuffer(author,sizeof(author)-1,"@identity-failure.lua")!=LuaRuntime::LuaInitResult::Success);
        assert(!RepentogonEnvironmentActive());
        assert(isaac::runtime::console::AutocompleteDispatchSlot()==nullptr);
        assert(installs==(ready?1u:0u));
        static_cast<void>(LuaRuntime::ShutdownForModReload());
        ready=install=true;Start(kDetected);
    }else if(mode=="off"||mode=="none"){
        Start("assert(REPENTOGON==nil and not RuntimeMods.GetRepentogonState().Active)");
        assert(installs==0);
    }else{
        Start(kDetected);assert(installs==1);
        assert(LuaRuntime::ShutdownForModReload());assert(!RepentogonEnvironmentActive());
        assert(isaac::runtime::console::AutocompleteDispatchSlot()==nullptr);
        Start("assert(REPENTOGON and REPENTOGON.Extras.Misc.identityProbe==nil)");
        assert(installs==2);
    }
    assert(LuaRuntime::ShutdownForModReload());assert(!RepentogonEnvironmentActive());
    assert(isaac::runtime::console::AutocompleteDispatchSlot()==nullptr);
    repentogon::SetNativePort(nullptr);SetSessionSaveFilePort(nullptr);
}
'''


class RepentogonIdentityTests(unittest.TestCase):
    def test_detection_gates_failure_retry_and_vm_reload(self):
        with tempfile.TemporaryDirectory(prefix='repentogon-identity-') as folder:
            binary = test_support.build_lua_harness(
                source_root=SOURCE, workdir=Path(folder), harness_source=DRIVER)
            for mode in ('enabled', 'off', 'none', 'unready', 'install_fail'):
                with self.subTest(mode=mode):
                    result = subprocess.run([str(binary), mode], capture_output=True, text=True)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
