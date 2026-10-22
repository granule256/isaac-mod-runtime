"""执行生产查询/句柄校验：TMTRAINER的u32和signed ID必须指向同一真实配置。"""
import subprocess,tempfile,unittest
from pathlib import Path
from .test_firetear_installed_relay import function
ROOT=Path(__file__).resolve().parents[2]
class ProceduralConfig(unittest.TestCase):
 def test_generated_and_normal_entries_and_stale_handles(self):
  src=(ROOT/'runtime/src/interfaces/lua/isaac_api.cpp').read_text()
  helper=function(src,'bool ReadProceduralItem(') if 'bool ReadProceduralItem(' in src else ''
  body=function(src,'int ItemConfigGetCollectible(lua_State* state) {')
  validate=function(src,'std::uintptr_t ValidatedItem(const ItemConfigItemHandle* handle) noexcept {')
  code=r'''
#include <cstdint>
#include <cstddef>
#include <cstring>
#include <cassert>
#include <cstdio>
#include <vector>
using lua_Integer=long long;
struct ItemConfigItemHandle{void*item;void*items;std::uint32_t beginOffset,index;};
struct lua_State{lua_Integer requested;bool nil=true;ItemConfigItemHandle out{};};
struct ItemVectorView{std::uintptr_t begin,end;std::size_t count;};
namespace engine_memory{std::uintptr_t AddressOf(void*p){return reinterpret_cast<std::uintptr_t>(p);}}
static std::vector<unsigned char> game(0x346000),config(32);
static std::uintptr_t gamePtr=reinterpret_cast<std::uintptr_t>(game.data());
constexpr std::uintptr_t kItemConfigCollectibleBeginOffset=0,kItemConfigCollectibleEndOffset=8;
constexpr std::uint32_t kProceduralItemConfigOffset=UINT32_MAX;
static std::uintptr_t ResolveGameAddress(){return gamePtr;}
static std::uintptr_t ResolveItemConfig(){return reinterpret_cast<std::uintptr_t>(config.data());}
template<class T>bool ReadEngine(std::uintptr_t p,T*v){if(!p)return false;std::memcpy(v,reinterpret_cast<void*>(p),sizeof(T));return true;}
static bool ReadItemVector(std::uintptr_t p,std::uintptr_t b,std::uintptr_t e,ItemVectorView*v){std::uintptr_t x=0,y=0;ReadEngine(p+b,&x);ReadEngine(p+e,&y);if(y<x||(y-x)%8||(y-x)/8>65536)return false;*v={x,y,(y-x)/8};return true;}
static void*CheckItemConfigHandle(lua_State*,int){return config.data();}
static std::uintptr_t ValidatedItemConfig(void*){return ResolveItemConfig();}
static bool ReadItemId(lua_State*L,int,lua_Integer*v){*v=L->requested;return true;}
static void RecordFilterChain(unsigned){}static void RecordItemConfigResult(bool){}
static void lua_pushnil(lua_State*L){L->nil=true;}
static void PushItemConfigItemHandle(lua_State*L,std::uintptr_t p,std::uintptr_t b,std::uintptr_t a,std::size_t i){L->nil=false;L->out={reinterpret_cast<void*>(p),reinterpret_cast<void*>(a),static_cast<std::uint32_t>(b),static_cast<std::uint32_t>(i)};}
static int ItemConfigGetEntry(lua_State*L,std::uintptr_t b,std::uintptr_t e){ItemVectorView v{};ReadItemVector(ResolveItemConfig(),b,e,&v);if(L->requested<0||static_cast<unsigned long long>(L->requested)>=v.count){lua_pushnil(L);return 1;}std::uintptr_t p=0;ReadEngine(v.begin+L->requested*8,&p);if(p)PushItemConfigItemHandle(L,p,b,v.begin,L->requested);return 1;}
HELPER
VALIDATE
BODY
int main(){std::uintptr_t item=0x123400,other=0x123500,desc=reinterpret_cast<std::uintptr_t>(&item),entries[]={desc};
std::uintptr_t begin=reinterpret_cast<std::uintptr_t>(entries),end=begin+8;std::memcpy(game.data()+0x345f18,&begin,8);std::memcpy(game.data()+0x345f20,&end,8);
std::uintptr_t normals[]={0,other};auto nb=reinterpret_cast<std::uintptr_t>(normals);auto ne=nb+16;std::memcpy(config.data(),&nb,8);std::memcpy(config.data()+8,&ne,8);
for(auto id:{4294967295LL,-1LL}){lua_State L{id};ItemConfigGetCollectible(&L);if(L.nil){std::fprintf(stderr,"generated id %lld returned nil\n",id);return 1;}assert(engine_memory::AddressOf(L.out.item)==item);assert(ValidatedItem(&L.out)==item);auto h=L.out;std::uintptr_t expanded[]={desc,desc};auto eb=reinterpret_cast<std::uintptr_t>(expanded);auto ee=eb+16;std::memcpy(game.data()+0x345f18,&eb,8);std::memcpy(game.data()+0x345f20,&ee,8);assert(ValidatedItem(&h)==item);std::memcpy(game.data()+0x345f18,&begin,8);std::memcpy(game.data()+0x345f20,&end,8);item=other;assert(ValidatedItem(&h)==0);item=0x123400;auto saved=gamePtr;gamePtr=0;assert(ValidatedItem(&h)==0);gamePtr=saved;entries[0]=0;assert(ValidatedItem(&h)==0);entries[0]=desc;}
for(auto id:{4294967294LL,-2LL,2147483648LL,4294967296LL,-4294967297LL}){lua_State L{id};ItemConfigGetCollectible(&L);assert(L.nil);}
lua_State normal{1};ItemConfigGetCollectible(&normal);assert(!normal.nil&&ValidatedItem(&normal.out)==other);
}
'''.replace('HELPER',helper).replace('VALIDATE',validate).replace('BODY',body)
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);(p/'t.cpp').write_text(code)
   r=subprocess.run(['c++','-std=c++17',str(p/'t.cpp'),'-o',str(p/'t')],capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stderr)
   r=subprocess.run([str(p/'t')],capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
