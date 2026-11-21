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
unsigned validations=0;
std::uintptr_t ValidatedEntity(EntityHandle*h){++validations;return h->valid?1:0;}
std::uintptr_t ValidatedEntityPlayer(EntityHandle*h){return ValidatedEntity(h);}
std::uintptr_t ValidatedTypedEntity(EntityHandle*h,int,int){return ValidatedEntity(h);}
constexpr int kEntityBombVtableOffset=0,kEntityTypeBomb=0,kEntityBombIsFetusOffset=0,kEntityTearVtableOffset=0,kEntityTypeTear=0,kEntityTearScaleOffset=0;
constexpr int kEntityNpcCanShutDoorsOffset=0,kEntityNpcCanShutDoorsMethodOffset=0,kEntityNpcCanShutDoorsExpectedBytes=0;
bool IsNpcFamilyEntity(std::uintptr_t){return false;}
void PushNil(lua_State*L){lua_pushnil(L);}
void PushEntityHandle(lua_State*L,std::uintptr_t,const char*){lua_pushnil(L);}
template<class T>std::uintptr_t EntityMethodByExpectedBytes(std::uintptr_t,const T&){return 0;}
template<class T>bool ReadEngine(std::uintptr_t,T*){return false;}
bool IsFamiliarOrbitField(const char*){return false;}
int PushFamiliarOrbitField(lua_State*,EntityHandle*,const char*){return 0;}
int probes=0,fieldValue=7;bool readable=true;
int Probe(lua_State*,std::uintptr_t,const char*){++probes;return 0;}
#define TryPushApi400EffectMethod Probe
#define TryPushApi400EntityField Probe
#define TryPushRPlusEntityField Probe
#define TryPushExtendedEntityField Probe
#define TryPushApi500EntityField Probe
#define TryPushApi600EntityField Probe
#define TryPushApi600ExtraEntityField Probe
#define TryPushApi600PlayerField Probe
bool PushEntityField(lua_State*L,std::uintptr_t,const char*k,bool){++probes;if(readable&&(!std::strcmp(k,"HitPoints")||!std::strcmp(k,"ControllerIndex")||!std::strcmp(k,"FrameCount")||!std::strcmp(k,"Position")||!std::strcmp(k,"Velocity")||!std::strcmp(k,"Type")||!std::strcmp(k,"Variant")||!std::strcmp(k,"SubType"))){lua_pushinteger(L,fieldValue);return true;}return false;}
bool PushEntityPickupField(lua_State*,std::uintptr_t,const char*){++probes;return false;}
bool PushEntityProjectileField(lua_State*,std::uintptr_t,const char*){++probes;return false;}
bool PushEntityNpcField(lua_State*,std::uintptr_t,const char*){++probes;return false;}
std::atomic<unsigned long long>g_EntityStringFieldReads{},g_LastEntityStringFieldHead{};
int EntityIndex(lua_State*);
'''
  body=function(source,'bool PushMethodFromMetatable(')+'\n'+function(source,'bool PushMethodFrom(')+'\n'+function(source,'int IndexEntity(')+'\n'+function(source,'int EntityToNpc(lua_State* state) {')+'\nint EntityIndex(lua_State*L){return IndexEntity(L,EntityView::Base);}\nint PlayerIndex(lua_State*L){return IndexEntity(L,EntityView::Player);}\n'
  main=r'''
int main(){auto*L=luaL_newstate();luaL_requiref(L,"_G",luaopen_base,1);lua_pop(L,1);
 for(const char*n:{"Entity","Player"}){luaL_newmetatable(L,n);lua_pushcfunction(L,!std::strcmp(n,"Entity")?EntityIndex:PlayerIndex);lua_setfield(L,-2,"__index");lua_newtable(L);lua_setfield(L,-2,"__methods");lua_setglobal(L,!std::strcmp(n,"Entity")?"base":"sub");}
 auto*h=static_cast<EntityHandle*>(lua_newuserdata(L,sizeof(EntityHandle)));h->valid=true;luaL_getmetatable(L,"Player");lua_setmetatable(L,-2);lua_setglobal(L,"p");
 lua_pushcfunction(L,EntityToNpc);lua_setglobal(L,"productionToNPC");
 const char*script=R"lua(
 for _,k in ipairs({'GetActiveItem','GetCollectibleRNG','GetName','GetMainTwin','GetCollectibleNum','AreControlsEnabled','IsSubPlayer','IsCoopGhost','HasCurseMistEffect','GetPlayerType','GetData','ToPlayer','GetEffects','HasCollectible','GetSprite','IsDead','HasTrinket','ToNPC','ToPickup','ToEffect','ToFamiliar','ToTear','ToLaser','ToProjectile','ToBomb','ToKnife'})do
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
 if(validations){std::fprintf(stderr,"method-only lookup performed %u unused native validations",validations);return 10;}
 if(luaL_loadstring(L,"assert(p.HitPoints==7);base.__index=function(o,k)return (k=='GetData' or k=='ToNPC') and 99 or nil end;assert(p.GetData==99 and p.ToNPC==99)")||lua_pcall(L,0,0,0)){std::fprintf(stderr,"%s",lua_tostring(L,-1));return 3;}
 fieldValue=8;if(luaL_loadstring(L,"assert(p.HitPoints==8)")||lua_pcall(L,0,0,0))return 4;
 h->valid=false;probes=0;if(luaL_loadstring(L,"assert(p.HitPoints==nil);assert(p.GetData==99 and p.ToNPC==99)")||lua_pcall(L,0,0,0)||probes)return 5;
 lua_getglobal(L,"base");lua_pushcfunction(L,EntityIndex);lua_setfield(L,-2,"__index");lua_pop(L,1);
 h->valid=true;probes=0;
 if(luaL_dostring(L,"base.__methods.Type=123;assert(p.Type==8 and p.Variant==8 and p.SubType==8)"))return 6;
 if(probes!=3){std::fprintf(stderr,"identity fields entered %d probes instead of 3",probes);return 7;}
 probes=0;
 if(luaL_dostring(L,"assert(p.ControllerIndex==8 and p.FrameCount==8 and p.Position==8 and p.Velocity==8)"))return 15;
 if(probes!=4){std::fprintf(stderr,"player fields entered %d probes instead of 4",probes);return 16;}
 readable=false;
 if(luaL_dostring(L,"assert(p.Type==123);assert(p.Variant==nil)"))return 8;
 h->valid=false;
 if(luaL_dostring(L,"assert(p.Type==123)"))return 9;
 // A stale receiver can still retrieve a method; its production body validates
 // at execution and refuses to turn the retired identity into an NPC.
 probes=0;validations=0;
 if(luaL_dostring(L,"base.__methods.ToNPC=productionToNPC;assert(p.ToNPC==productionToNPC)"))return 11;
 if(probes||validations)return 12;
 if(luaL_dostring(L,"assert(p:ToNPC()==nil)"))return 13;
 if(probes||validations!=1)return 14;
 const char* fallback=R"lua(
 local keys={}
 setmetatable(sub.__methods,{__index=function(_,k) keys[#keys+1]=k;return k=='GetData' and 123 or nil end})
 assert(p['GetData\0suffix']==123 and keys[1]=='GetData')
 local f=sub.__index
 assert(not pcall(f,{},'GetData'))
 assert(f(p,'GetData','extra')==123)
 )lua";
 if(luaL_dostring(L,fallback))return 17;
 g_EntityStringFieldReads=0;g_LastEntityStringFieldHead=0;
 if(luaL_dostring(L,"assert(p.GetData==123)"))return 18;
#if EXL_DIAGNOSTIC_PROBES
 if(g_EntityStringFieldReads!=1||g_LastEntityStringFieldHead!=0x61746144746547ULL){
  std::fprintf(stderr,"diagnostic lookup did not record the key");return 19;
 }
#else
 if(g_EntityStringFieldReads||g_LastEntityStringFieldHead){
  std::fprintf(stderr,"production lookup updated diagnostic counters");return 20;
 }
#endif
 lua_close(L);return 0;}
'''
  with tempfile.TemporaryDirectory()as tmp:
   work=Path(tmp);objects=lua_harness_objects(ROOT/'runtime/source',work)
   (work/'host.cpp').write_text(pre+body+main)
   for diagnostics in (0,1):
    with self.subTest(diagnostics=diagnostics):
     r=subprocess.run(['c++','-std=c++17',f'-DEXL_DIAGNOSTIC_PROBES={diagnostics}','-I'+str(ROOT/'runtime/source/third_party/lua-5.3.3/src'),str(work/'host.cpp'),*[str(p)for p in objects],'-o',str(work/'host')],capture_output=True,text=True)
     self.assertEqual(r.returncode,0,r.stdout+r.stderr)
     r=subprocess.run([str(work/'host')],capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
