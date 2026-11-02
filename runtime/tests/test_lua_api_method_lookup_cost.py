"""真实Lua调用生产IndexEntity：方法查找不扫描字段，覆写及继承仍即时生效。"""
from pathlib import Path
import subprocess,tempfile,unittest
from .test_support import lua_harness_objects
ROOT=Path(__file__).resolve().parents[2]
def function(source,name):
 start=source.index(name);brace=source.index('{',start);depth=1;i=brace+1
 while depth:
  depth+=(source[i]=='{')-(source[i]=='}');i+=1
 return source[start:i]
class MethodLookupCostTests(unittest.TestCase):
 def test_production_index_preserves_lookup_and_skips_field_probes(self):
  source=(ROOT/'runtime/src/interfaces/lua/isaac_api.cpp').read_text()
  pre=r'''
#include <atomic>
#include <cstdint>
#include <cstring>
#include <cstdio>
#include <initializer_list>
extern "C" {
#include "lua.h"
#include "lauxlib.h"
#include "lualib.h"
}
struct EntityHandle {bool valid;};
enum class EntityView {Base,Player,Pickup,Projectile,Tear,Laser,Npc,Familiar,Bomb,Knife};
constexpr const char* kEntityMetatable="Entity";
const char* EntityViewMetatable(EntityView v){return v==EntityView::Base?"Entity":"Player";}
EntityHandle* CheckEntityHandle(lua_State* L,int i){return static_cast<EntityHandle*>(lua_touserdata(L,i));}
std::uintptr_t ValidatedEntity(EntityHandle*h){return h->valid?1:0;}
std::uintptr_t ValidatedEntityPlayer(EntityHandle*h){return ValidatedEntity(h);}
std::uintptr_t ValidatedTypedEntity(EntityHandle*h,int,int){return ValidatedEntity(h);}
constexpr int kEntityBombVtableOffset=0,kEntityTypeBomb=0,kEntityBombIsFetusOffset=0,kEntityTearVtableOffset=0,kEntityTypeTear=0,kEntityTearScaleOffset=0;
template<class T>bool ReadEngine(std::uintptr_t,T*){return false;}
bool IsFamiliarOrbitField(const char*){return false;}
int PushFamiliarOrbitField(lua_State*,EntityHandle*,const char*){return 0;}
int probes=0,fieldValue=7;
int Probe(lua_State*,std::uintptr_t,const char*){++probes;return 0;}
#define TryPushApi400EffectMethod Probe
#define TryPushApi400EntityField Probe
#define TryPushRPlusEntityField Probe
#define TryPushExtendedEntityField Probe
#define TryPushApi500EntityField Probe
#define TryPushApi600EntityField Probe
#define TryPushApi600ExtraEntityField Probe
#define TryPushApi600PlayerField Probe
bool PushEntityField(lua_State*L,std::uintptr_t,const char*k,bool){++probes;if(!std::strcmp(k,"HitPoints")){lua_pushinteger(L,fieldValue);return true;}return false;}
bool PushEntityPickupField(lua_State*,std::uintptr_t,const char*){++probes;return false;}
bool PushEntityProjectileField(lua_State*,std::uintptr_t,const char*){++probes;return false;}
bool PushEntityNpcField(lua_State*,std::uintptr_t,const char*){++probes;return false;}
std::atomic<unsigned long long>g_EntityStringFieldReads{},g_LastEntityStringFieldHead{};
int EntityIndex(lua_State*);
'''
  body=function(source,'bool PushMethodFrom(')+'\n'+function(source,'int IndexEntity(')+'\nint EntityIndex(lua_State*L){return IndexEntity(L,EntityView::Base);}\nint PlayerIndex(lua_State*L){return IndexEntity(L,EntityView::Player);}\n'
  main=r'''
int main(){auto*L=luaL_newstate();luaL_requiref(L,"_G",luaopen_base,1);lua_pop(L,1);
 for(const char*n:{"Entity","Player"}){luaL_newmetatable(L,n);lua_pushcfunction(L,!std::strcmp(n,"Entity")?EntityIndex:PlayerIndex);lua_setfield(L,-2,"__index");lua_newtable(L);lua_setfield(L,-2,"__methods");lua_setglobal(L,!std::strcmp(n,"Entity")?"base":"sub");}
 auto*h=static_cast<EntityHandle*>(lua_newuserdata(L,sizeof(EntityHandle)));h->valid=true;luaL_getmetatable(L,"Player");lua_setmetatable(L,-2);lua_setglobal(L,"p");
 const char*script=R"lua(
 for _,k in ipairs({'GetData','ToPlayer','GetEffects','HasCollectible','GetSprite','IsDead','HasTrinket'})do
  base.__methods[k]=function()return 10 end
  assert(p[k](p)==10)
  sub.__methods[k]=function()return 20 end;assert(p[k](p)==20)
  sub.__methods[k]=false;assert(p[k]==false)
  sub.__methods[k]=nil;base.__methods[k]=function()return 30 end;assert(p[k](p)==30)
  base.__methods[k]=nil;assert(p[k]==nil)
 end
 )lua";
 if(luaL_loadstring(L,script)||lua_pcall(L,0,0,0)){std::fprintf(stderr,"%s",lua_tostring(L,-1));return 2;}
 if(probes){std::fprintf(stderr,"method-only lookup entered field probes %d times",probes);return 1;}
 if(luaL_loadstring(L,"assert(p.HitPoints==7);base.__index=function(o,k)return k=='GetData' and 99 or nil end;assert(p.GetData==99)")||lua_pcall(L,0,0,0)){std::fprintf(stderr,"%s",lua_tostring(L,-1));return 3;}
 fieldValue=8;if(luaL_loadstring(L,"assert(p.HitPoints==8)")||lua_pcall(L,0,0,0))return 4;
 h->valid=false;probes=0;if(luaL_loadstring(L,"assert(p.HitPoints==nil);assert(p.GetData==99)")||lua_pcall(L,0,0,0)||probes)return 5;
 lua_close(L);return 0;}
'''
  with tempfile.TemporaryDirectory()as tmp:
   work=Path(tmp);objects=lua_harness_objects(ROOT/'runtime/source',work)
   (work/'host.cpp').write_text(pre+body+main)
   r=subprocess.run(['c++','-std=c++17','-I'+str(ROOT/'runtime/source/third_party/lua-5.3.3/src'),str(work/'host.cpp'),*[str(p)for p in objects],'-o',str(work/'host')],capture_output=True,text=True)
   self.assertEqual(r.returncode,0,r.stdout+r.stderr)
   r=subprocess.run([str(work/'host')],capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
