"""真实FireTear解析函数与已安装中继组合；不执行宿主上的ARM指令。"""
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
API = ROOT/'runtime/src/interfaces/lua/isaac_api.cpp'


def function(text, signature):
    start = text.index(signature)
    opening = text.index('{', start)
    depth = 1
    end = opening+1
    while depth:
        depth += (text[end] == '{')-(text[end] == '}')
        end += 1
    return text[start:end]


class FireTearInstalledRelay(unittest.TestCase):
    def test_actual_resolver_checks_full_entry_and_registered_relay(self):
        body = function(API.read_text(), 'std::uintptr_t EntityPlayerFireTearMethod() noexcept')
        constants = (ROOT/'runtime/source/runtime_constants.hpp').read_text()
        values = re.search(r'kEntityPlayerFireTearExpectedBytes\s*=\s*\{([^}]+)', constants).group(1)
        program = r'''
#include "interfaces/lua/hooked_engine_entry.hpp"
#include "infrastructure/relay/entry_relay_binding.hpp"
#include <array>
#include <cstdio>
#include <cstring>
using namespace isaac::runtime;
alignas(16) static std::array<unsigned char,256> module{};
alignas(16) static std::array<unsigned char,relay::kSlotBytes> slot{};
static std::uintptr_t fallback{};
static std::uintptr_t EngineModuleBase(){return reinterpret_cast<std::uintptr_t>(module.data());}
static constexpr std::uintptr_t kEntityPlayerFireTearOffset=64;
static constexpr std::array<std::uint8_t,16> kEntityPlayerFireTearExpectedBytes={VALUES};
static bool IsEngineMemoryReadable(std::uintptr_t a,std::size_t n){
 auto in=[&](auto&v){auto b=reinterpret_cast<std::uintptr_t>(v.data());return a>=b&&n<=v.size()&&a-b<=v.size()-n;};
 return in(module)||in(slot);
}
namespace isaac::runtime {std::uintptr_t EntryRelayFallbackEntry(HookId id)noexcept{
 return id==HookId::FireTear?fallback:0;
}}
#define __SWITCH__ 1
RESOLVER
int main(){
 auto target=EngineModuleBase()+kEntityPlayerFireTearOffset;
 auto entry=module.data()+kEntityPlayerFireTearOffset;
 auto require=[&](bool ok,const char*name){if(!ok){std::fprintf(stderr,"%s\n",name);return false;}return true;};
 std::memcpy(entry,kEntityPlayerFireTearExpectedBytes.data(),16);
 if(!require(EntityPlayerFireTearMethod()==target,"original rejected"))return 1;
 relay::BuildSlotImage(slot.data(),target,kEntityPlayerFireTearExpectedBytes.data(),0);
 fallback=reinterpret_cast<std::uintptr_t>(slot.data())+relay::kSlotFallbackOffset;
 relay::BuildEntryPatch(entry,fallback-relay::kSlotFallbackOffset);
 if(!require(EntityPlayerFireTearMethod()==target,"registered relay rejected"))return 2;
 auto saved=fallback;fallback=0;
 if(!require(EntityPlayerFireTearMethod()==0,"foreign unregistered relay accepted"))return 3;
 fallback=saved;slot[relay::kSlotFallbackOffset]^=1;
 if(!require(EntityPlayerFireTearMethod()==0,"corrupt original accepted"))return 4;
 slot[relay::kSlotFallbackOffset]^=1;slot[relay::kSlotBytes-1]^=1;
 if(!require(EntityPlayerFireTearMethod()==0,"corrupt return target accepted"))return 5;
 slot[relay::kSlotBytes-1]^=1;entry[8]^=1;
 if(!require(EntityPlayerFireTearMethod()==0,"wrong slot accepted"))return 6;
 std::puts("original / installed / foreign / corrupt original / return / slot verified");
}
'''.replace('VALUES', values).replace('RESOLVER', body)
        with tempfile.TemporaryDirectory(prefix='firetear-relay-') as directory:
            p = Path(directory)
            (p/'test.cpp').write_text(program)
            compile = subprocess.run(['c++','-std=c++17','-Wall','-Wextra',
                '-I'+str(ROOT/'runtime/src'),'-I'+str(ROOT/'runtime/source'),
                str(p/'test.cpp'),'-o',str(p/'test')],capture_output=True,text=True)
            self.assertEqual(compile.returncode,0,compile.stdout+compile.stderr)
            run = subprocess.run([str(p/'test')],capture_output=True,text=True)
            self.assertEqual(run.returncode,0,run.stdout+run.stderr)

    def test_public_api_uses_resolver_without_rejecting_installed_entry_again(self):
        body = function(API.read_text(), 'int EntityPlayerFireTear(lua_State* state) {')
        self.assertNotRegex(body, r'EngineEntryWordMatches\s*\(method,\s*kEntityPlayerFireTearEntryWord')


if __name__ == '__main__':
    unittest.main()
