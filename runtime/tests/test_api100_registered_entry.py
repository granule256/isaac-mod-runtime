"""API entry caches accept only a fully verified installed extension relay."""
from pathlib import Path
import subprocess,tempfile,unittest
from . import test_support
ROOT=Path(__file__).resolve().parents[1]
DRIVER=r'''
#include "interfaces/lua/api100_native.hpp"
#include "infrastructure/call/engine_call_access.hpp"
#include <cassert>
using namespace isaac::runtime;
static std::array<std::uint8_t,16> original,patched,image;
static std::uintptr_t base;
static unsigned failures,checks;
namespace LuaRuntime {std::uintptr_t EngineModuleBase()noexcept{return base;} int ReportAndRecordLuaError(lua_State*,const char*,...){++failures;return 0;}}
extern "C" int luaL_error(lua_State*,const char*,...){++failures;return 0;}
static bool Verify(std::uintptr_t a,const std::uint8_t* bytes,std::size_t n,engine_call::ReadableCheck read)noexcept{
 ++checks;return n==16&&a==base+64&&read(a,n)&&std::memcmp(bytes,original.data(),16)==0&&std::memcmp(engine_memory::AsObject(a),patched.data(),16)==0;
}
int main(){
 original.fill(1);patched.fill(2);image=patched;base=engine_memory::AddressOf(image.data())-64;
 api100_native::Entry entry{64,original.data()};api100_native::Cache cache{};
 assert(api100_native::Resolve(nullptr,entry,cache)==0&&failures==1);
 engine_call::SetInstalledEntryVerifier(Verify);
 assert(api100_native::Resolve(nullptr,entry,cache)==base+64&&checks==1);
 assert(api100_native::Resolve(nullptr,entry,cache)==base+64&&checks==1);
 image[5]^=1;api100_native::Cache bad{};assert(api100_native::Resolve(nullptr,entry,bad)==0&&failures==2);
 engine_call::SetInstalledEntryVerifier(nullptr);
}
'''
class Api100RegisteredEntryTests(unittest.TestCase):
 def test_registered_relay_and_foreign_patch_rejection(self):
  with tempfile.TemporaryDirectory(prefix='api100-entry-')as tmp:
   p=test_support.prepare_harness_directory(Path(tmp));(p/'test.cpp').write_text(DRIVER)
   includes=[p/'compatibility',ROOT/'source',ROOT/'src',ROOT/'source/third_party/lua-5.3.3/src']
   cmd=['c++',*test_support.HARNESS_COMPILE_FLAGS,*[f'-I{x}'for x in includes],str(p/'test.cpp'),str(ROOT/'src/interfaces/lua/api100_native.cpp'),'-o',str(p/'test')]
   r=subprocess.run(cmd,capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
   r=subprocess.run([str(p/'test')],capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
