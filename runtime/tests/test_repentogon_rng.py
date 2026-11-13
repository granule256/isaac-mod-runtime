"""REPENTOGON SetSeed defaults stay scoped to the extension environment."""
import subprocess
import tempfile
import unittest
from pathlib import Path

from . import test_support

SOURCE = Path(__file__).resolve().parents[1] / 'source'
DRIVER = r'''
#include "lua_runtime.hpp"
#include "interfaces/lua/repentogon_callbacks.hpp"
#include "ports/save_file_port.hpp"
extern "C" {
#include <lauxlib.h>
}
#include <cassert>
#include <cstring>
using namespace isaac::runtime;
struct Files final : ISaveFilePort {
 bool enabled;
 explicit Files(bool value):enabled(value){}
 Status Read(std::string_view, char* out, std::size_t capacity, std::size_t* size) noexcept override {
  const char* value=enabled?"isaac-repentogon 1\nenabled 1\n":"isaac-repentogon 1\nenabled 0\n";
  *size=std::strlen(value);assert(capacity>=*size);std::memcpy(out,value,*size);return Status::Ok();
 }
 Status Write(std::string_view,std::string_view) noexcept override {return Status::Ok();}
 Status Remove(std::string_view) noexcept override {return Status{StatusCode::Unsupported};}
 Status Exists(const char*,bool*) noexcept override {return Status{StatusCode::Unsupported};}
};
static bool Ready() noexcept{return true;}
static unsigned calls;
static std::uint32_t lastSeed,lastShift;
static void SetSeed(void* object,std::uint32_t seed,std::uint32_t shift){
 ++calls;lastSeed=seed;lastShift=shift;std::memcpy(object,&seed,sizeof(seed));
}
int main(int argc,char**argv){
 const bool enabled=argc>1&&!std::strcmp(argv[1],"enabled");
 Files files(enabled);SetSessionSaveFilePort(&files);LuaRuntime::ObserveGameThread();
 const repentogon::NativePort port{Ready,Ready};repentogon::SetNativePort(&port);
 LuaRuntime::SetRngBindings(reinterpret_cast<std::uintptr_t>(&SetSeed),0);
 const char* script=enabled?R"lua(
assert(REPENTOGON and REPENTOGON.FullCompatibility==false)
local r=RNG()
r:SetSeed(123);assert(r:GetSeed()==123)
r:SetSeed(456,nil);assert(r:GetSeed()==456)
r:SetSeed(-1);assert(r:GetSeed()==4294967295)
r:SetSeed('789','80');assert(r:GetSeed()==789)
r:SetSeed(321,4294967331);assert(r:GetSeed()==321)
for _,args in ipairs({{}, {0}, {4294967296}, {1.5}, {1,-1}, {1,81}, {1,0.5}, {'x'}, {1,{}}}) do
 assert(not pcall(function()r:SetSeed(table.unpack(args))end))
end
r:SetSeed(1,0);assert(r:GetSeed()==1)
)lua":R"lua(
local r=RNG()
assert(not pcall(function()r:SetSeed(123)end))
assert(not pcall(function()r:SetSeed(123,nil)end))
r:SetSeed(456,7);assert(r:GetSeed()==456)
)lua";
 const auto result=LuaRuntime::InitializeFromBuffer(script,std::strlen(script),"@rng-extension.lua");
 if(result!=LuaRuntime::LuaInitResult::Success){
  char error[2048]{};static_cast<void>(LuaRuntime::CopyLastLuaErrorText(error,sizeof(error)));
  std::fprintf(stderr,"%s\n",error);return 1;
 }
 assert(calls==(enabled?6u:1u));assert(lastSeed==(enabled?1u:456u));
 assert(lastShift==(enabled?0u:7u));
 assert(LuaRuntime::ShutdownForModReload());
 repentogon::SetNativePort(nullptr);SetSessionSaveFilePort(nullptr);
}
'''


class RepentogonRngTests(unittest.TestCase):
    def test_optional_shift_and_invalid_arguments_are_extension_scoped(self):
        with tempfile.TemporaryDirectory(prefix='repentogon-rng-') as folder:
            binary = test_support.build_lua_harness(
                source_root=SOURCE, workdir=Path(folder), harness_source=DRIVER)
            for mode in ('enabled', 'disabled'):
                with self.subTest(mode=mode):
                    result = subprocess.run([str(binary), mode], capture_output=True, text=True)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
