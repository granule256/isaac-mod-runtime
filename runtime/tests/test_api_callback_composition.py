"""公开调用不能绕开已安装事件，也不能把登记中继当陌生入口拒绝。"""
import re
import subprocess
import tempfile
import unittest
from pathlib import Path
from .test_firetear_installed_relay import function

ROOT=Path(__file__).resolve().parents[2]
SCALAR=ROOT/'runtime/src/interfaces/lua/api100_scalar.cpp'
NATIVE=ROOT/'runtime/src/interfaces/lua/api100_native.cpp'

def run(program):
    with tempfile.TemporaryDirectory(prefix='api-callback-compose-')as directory:
        p=Path(directory);(p/'test.cpp').write_text(program)
        c=subprocess.run(['c++','-std=c++17','-I'+str(ROOT/'runtime/src'),'-I'+str(ROOT/'runtime/source'),str(p/'test.cpp'),'-o',str(p/'test')],capture_output=True,text=True)
        if c.returncode:return c
        return subprocess.run([str(p/'test')],capture_output=True,text=True)

class ApiCallbackComposition(unittest.TestCase):
    def test_actual_getcard_public_body_uses_installed_dispatch_entry(self):
        body=function(SCALAR.read_text(),'int Api100ItemPoolGetCard(lua_State*state)')
        program=r'''
#include "card_hook.hpp"
#include "interfaces/lua/api100_scalar.hpp"
#include <cassert>
#include <cstdio>
using namespace isaac::runtime;
struct lua_State{long long result{};};
namespace LuaRuntime{constexpr const char*kItemPoolMetatable="pool";std::uintptr_t EngineModuleBase(){return 0x1000;}}
enum class FieldReceipt{ItemPool};
static unsigned directCalls{},interceptCalls{};
static void* Receiver(lua_State*,const char*,FieldReceipt){return reinterpret_cast<void*>(0x2000);}
static long long luaL_checkinteger(lua_State*,int){return 12345;}
static int lua_toboolean(lua_State*,int i){return i!=5;}
static void lua_pushinteger(lua_State*L,long long v){L->result=v;}
static int luaL_error(lua_State*,const char*){return -1;}
static std::uint32_t Direct(const void*p,std::uint32_t s,bool a,bool b,bool c){assert(p==reinterpret_cast<void*>(0x2000)&&s==12345&&a&&b&&!c);++directCalls;return 18;}
static std::uint32_t Intercept(const void*p,std::uint32_t s,bool a,bool b,bool c){Direct(p,s,a,b,c);++interceptCalls;return 1;}
namespace isaac::runtime {CardNativeBindings::GetCard ResolveCardApiEntry(std::uintptr_t base)noexcept{assert(base==0x1000);return &Intercept;}}
template<class Fn>Fn Native(lua_State*,Api100ScalarNative){return reinterpret_cast<Fn>(&Direct);}
template<class R,class...A>int Call(lua_State*L,Api100ScalarNative,void*p,A...a){lua_pushinteger(L,Direct(p,a...));return 1;}
#define __SWITCH__ 1
BODY
int main(){lua_State L;assert(::Api100ItemPoolGetCard(&L)==1);if(L.result!=1||interceptCalls!=1||directCalls!=1){std::fprintf(stderr,"result=%lld intercept=%u direct=%u\n",L.result,interceptCalls,directCalls);return 1;}}
'''.replace('BODY',body)
        result=run(program);self.assertEqual(result.returncode,0,result.stdout+result.stderr)

    def test_actual_entity_resolver_accepts_only_registered_use_entries(self):
        text=(ROOT/'runtime/src/interfaces/lua/isaac_api.cpp').read_text()
        # 前置声明无函数体；明确选择定义所在的末段。
        start=text.rindex('std::uintptr_t EntityMethodByExpectedBytes(std::uintptr_t offset,')
        body=function(text[start:],'std::uintptr_t EntityMethodByExpectedBytes(std::uintptr_t offset,')
        constants=(ROOT/'runtime/source/runtime_constants.hpp').read_text()
        names=['UseCard','UsePill','UseActiveItem','EvaluateItems']
        declarations=[]
        for i,name in enumerate(names):
            values=re.search(r'kEntityPlayer'+name+r'ExpectedBytes\s*=\s*\{([^}]+)',constants).group(1)
            declarations.append(f'constexpr std::uintptr_t kEntityPlayer{name}Offset={64+i*32};\nconstexpr std::array<u8,16> kEntityPlayer{name}ExpectedBytes={{{values}}};')
        program=r'''
#include "interfaces/lua/hooked_engine_entry.hpp"
#include "infrastructure/relay/entry_relay_binding.hpp"
#include <array>
#include <cassert>
#include <cstdio>
#include <cstring>
using namespace isaac::runtime;using u8=std::uint8_t;
alignas(16) static std::array<unsigned char,256> image{};
alignas(16) static std::array<unsigned char,relay::kSlotBytes> slot{};
static std::uintptr_t fallback{};
static std::uintptr_t EngineModuleBase(){return reinterpret_cast<std::uintptr_t>(image.data());}
static bool IsEngineMemoryReadable(std::uintptr_t a,std::size_t n){auto in=[&](auto&v){auto b=reinterpret_cast<std::uintptr_t>(v.data());return a>=b&&n<=v.size()&&a-b<=v.size()-n;};return in(image)||in(slot);}
namespace isaac::runtime{std::uintptr_t EntryRelayFallbackEntry(HookId)noexcept{return fallback;}}
CONSTANTS
#define __SWITCH__ 1
BODY
int main(){
const std::uintptr_t offsets[]={kEntityPlayerUseCardOffset,kEntityPlayerUsePillOffset,kEntityPlayerUseActiveItemOffset,kEntityPlayerEvaluateItemsOffset};
const std::array<u8,16> guards[]={kEntityPlayerUseCardExpectedBytes,kEntityPlayerUsePillExpectedBytes,kEntityPlayerUseActiveItemExpectedBytes,kEntityPlayerEvaluateItemsExpectedBytes};
for(unsigned i=0;i<4;++i){auto target=EngineModuleBase()+offsets[i];auto*entry=image.data()+offsets[i];fallback=0;std::memcpy(entry,guards[i].data(),16);assert(EntityMethodByExpectedBytes(offsets[i],guards[i])==target);
relay::BuildSlotImage(slot.data(),target,guards[i].data(),0);fallback=reinterpret_cast<std::uintptr_t>(slot.data())+relay::kSlotFallbackOffset;relay::BuildEntryPatch(entry,fallback-relay::kSlotFallbackOffset);
if(EntityMethodByExpectedBytes(offsets[i],guards[i])!=target){std::fprintf(stderr,"registered use entry %u rejected\n",i);return 1;}
auto saved=fallback;fallback=0;assert(EntityMethodByExpectedBytes(offsets[i],guards[i])==0);fallback=saved;slot.back()^=1;assert(EntityMethodByExpectedBytes(offsets[i],guards[i])==0);slot.back()^=1;
} }
'''.replace('CONSTANTS','\n'.join(declarations)).replace('BODY',body)
        result=run(program);self.assertEqual(result.returncode,0,result.stdout+result.stderr)

    def test_shared_resolver_accepts_registered_lifecycle_entries_only(self):
        text=NATIVE.read_text()
        body=function(text,'std::uintptr_t Resolve(lua_State* state,')
        program=r'''
#include "interfaces/lua/api100_native.hpp"
#include "interfaces/lua/hooked_engine_entry.hpp"
#include "infrastructure/relay/entry_relay_binding.hpp"
#include <array>
#include <cassert>
#include <cstdio>
#include <cstring>
#include <stdexcept>
using namespace isaac::runtime;
struct lua_State{};
alignas(16) static std::array<unsigned char,256> image{};
alignas(16) static std::array<unsigned char,relay::kSlotBytes> slot{};
static std::uintptr_t fallback{};
namespace LuaRuntime{std::uintptr_t EngineModuleBase(){return reinterpret_cast<std::uintptr_t>(image.data());}}
namespace isaac::runtime{std::uintptr_t EntryRelayFallbackEntry(HookId)noexcept{return fallback;}}
static int luaL_error(lua_State*,const char*message){throw std::runtime_error(message);}
constexpr std::uintptr_t kApi100ItemPoolGetPillOffset=64,kApi200GameEndOffset=96,kApi200GameStartStageTransitionOffset=160,kNativePlayerInitOffset=192;
#define __SWITCH__ 1
namespace isaac::runtime::api100_native{BODY}
int main(){lua_State L;const std::array<std::uint8_t,16> guard={0xff,0xc3,0,0xd1,0xfd,0x7b,1,0xa9,0xfd,0x43,0,0x91,0xf3,0x13,0,0xf9};
for(auto off:{64U,96U,160U,192U}){auto target=LuaRuntime::EngineModuleBase()+off;auto*entry=image.data()+off;api100_native::Entry spec{off,guard.data()};api100_native::Cache cache{};
fallback=0;std::memcpy(entry,guard.data(),16);assert(api100_native::Resolve(&L,spec,cache)==target);
relay::BuildSlotImage(slot.data(),target,guard.data(),0);fallback=reinterpret_cast<std::uintptr_t>(slot.data())+relay::kSlotFallbackOffset;relay::BuildEntryPatch(entry,fallback-relay::kSlotFallbackOffset);cache={};
try{if(api100_native::Resolve(&L,spec,cache)!=target)return 1;}catch(...){std::fprintf(stderr,"registered API entry %u rejected\n",off);return 2;}
auto saved=fallback;fallback=0;cache={};bool rejected=false;try{api100_native::Resolve(&L,spec,cache);}catch(...){rejected=true;}assert(rejected);fallback=saved;slot.back()^=1;cache={};rejected=false;try{api100_native::Resolve(&L,spec,cache);}catch(...){rejected=true;}assert(rejected);slot.back()^=1;
}
auto off=128U;auto target=LuaRuntime::EngineModuleBase()+off;relay::BuildSlotImage(slot.data(),target,guard.data(),0);fallback=reinterpret_cast<std::uintptr_t>(slot.data())+relay::kSlotFallbackOffset;relay::BuildEntryPatch(image.data()+off,fallback-relay::kSlotFallbackOffset);api100_native::Entry unknown{off,guard.data()};api100_native::Cache cache{};bool rejected=false;try{api100_native::Resolve(&L,unknown,cache);}catch(...){rejected=true;}assert(rejected);
}
'''.replace('BODY',body)
        result=run(program);self.assertEqual(result.returncode,0,result.stdout+result.stderr)


if __name__=='__main__':unittest.main()
