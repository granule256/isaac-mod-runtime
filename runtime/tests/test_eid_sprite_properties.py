"""EID真实片段与共享精灵视图：赋值后无需Render就必须生效，旧视图不能回写旧值。"""
import subprocess
import tempfile
import unittest
from pathlib import Path
try:
 from .test_support import build_lua_harness
except ImportError:
 from test_support import build_lua_harness
ROOT=Path(__file__).resolve().parents[2]
HARNESS=r"""
#include "lua_runtime.hpp"
#include "lua_object_handles.hpp"
#include "interfaces/lua/sprite_api.hpp"
#include "interfaces/lua/color_api.hpp"
#include "interfaces/lua/vector_api.hpp"
#include "runtime_constants.hpp"
extern "C" {
#include <lauxlib.h>
#include <lualib.h>
}
#include <cstdio>
#include <cstring>
#include <cstdlib>
#include <string>
using namespace isaac::runtime;
alignas(16) unsigned char owner[0x300]{};
void* native=nullptr; int mode=0, draws=0, expectedOffset=0;
void Ctor(void* self) {
 std::memset(self,0,0x158);float scale[]={1,1};float color[]={1,1,1,1,0,0,0,0,0,0,0};
 std::memcpy((char*)self+0xdc,scale,8);std::memcpy((char*)self+0xe8,color,44);float speed=1;std::memcpy((char*)self+0x144,&speed,4);native=self;
}
void Dtor(void*){}
void Advance(void* self){float speed{},position{};std::memcpy(&speed,(char*)self+0x144,4);std::memcpy(&position,(char*)self+0x50,4);position+=speed;std::memcpy((char*)self+0x50,&position,4);}
int CheckSpeed(lua_State* L){float speed{},position{};std::memcpy(&speed,(char*)native+0x144,4);std::memcpy(&position,(char*)native+0x50,4);if(speed!=lua_tonumber(L,1)||position!=lua_tonumber(L,2))return luaL_error(L,"NATIVE_PLAYBACK_SPEED_WRONG");return 0;}
void Capture(void* self,const void*,const void*,const void*) {
 float raw[11];std::memcpy(raw,(char*)self+0xe8,44);
 const int wanted=expectedOffset==2 ? (draws<4?1:0) : expectedOffset;
 if(raw[8]!=wanted || raw[4]!=0 || raw[7]!=0) std::exit(20);
 ++draws;
}
void Layer(void* s,int,const void* p,const void* a,const void* b){Capture(s,p,a,b);}
int View(lua_State* L) {
 if(mode==1)return PushEngineEntitySpriteHandle(L,owner);
 if(mode==2)return PushEngineGridEntitySpriteHandle(L,owner);
 lua_getglobal(L,"owned");return 1;
}
int Check(lua_State* L) {
 float v=lua_tonumber(L,1), raw[11];std::memcpy(raw,(char*)native+0xe8,44);
 if(raw[8]!=v || raw[9]!=v || raw[10]!=v || raw[4]!=0 || raw[7]!=0)
  return luaL_error(L,"NATIVE_COLOR_NOT_IMMEDIATE got=%f expected=%f",raw[8],v);
 return 0;
}
int CheckFlip(lua_State* L) {
 if(*((unsigned char*)native+0x140)!=lua_toboolean(L,1))return luaL_error(L,"NATIVE_FLIP_NOT_IMMEDIATE");return 0;
}
int ChangeNative(lua_State*) {
 float v=.75f;std::memcpy((char*)native+0x108,&v,4);return 0;
}
void Meta(lua_State* L,const char* name,lua_CFunction index,lua_CFunction write){
 luaL_newmetatable(L,name);lua_pushcfunction(L,index);lua_setfield(L,-2,"__index");
 lua_pushcfunction(L,write);lua_setfield(L,-2,"__newindex");
}
int main(int argc,char** argv) {
 if(argc!=3)return 90;mode=std::atoi(argv[1]);std::string scenario=argv[2];
 LuaRuntime::SetEngineModuleBase(0x10000000);
 if(mode) {
  std::uintptr_t v=0x10000000+(mode==1?0xa34f58:0xa37890);std::memcpy(owner,&v,8);
  Ctor(owner+(mode==1?0x50:0x48));
 }
 LuaRuntime::LuaSpriteBindings b{};b.ctor=Ctor;b.destructor_=Dtor;b.render=Capture;b.renderLayer=Layer;b.update=Advance;LuaRuntime::SetSpriteBindings(b);
 lua_State* L=luaL_newstate();luaL_requiref(L,"_G",luaopen_base,1);lua_pop(L,1);luaL_requiref(L,"math",luaopen_math,1);lua_pop(L,1);
 Meta(L,LuaRuntime::kColorMetatable,ColorIndex,ColorNewIndex);lua_pop(L,1);
 Meta(L,LuaRuntime::kVectorMetatable,VectorIndex,VectorNewIndex);
 lua_pushcfunction(L,VectorAdd);lua_setfield(L,-2,"__add");lua_pushcfunction(L,VectorSub);lua_setfield(L,-2,"__sub");lua_pushcfunction(L,VectorDiv);lua_setfield(L,-2,"__div");lua_pop(L,1);
 Meta(L,LuaRuntime::kSpriteMetatable,SpriteIndex,SpriteNewIndex);lua_pushcfunction(L,DestroySpriteHandle);lua_setfield(L,-2,"__gc");lua_newtable(L);static_cast<void>(AttachSpriteMethods(L));lua_setfield(L,-2,"__methods");lua_pop(L,1);
 for(auto entry:{std::pair<const char*,lua_CFunction>{"Sprite",CreateSpriteHandle},{"Color",CreateColorHandle},{"Vector",CreateVectorHandle},{"view",View},{"checknative",Check},{"checkflip",CheckFlip},{"changenative",ChangeNative},{"checkspeed",CheckSpeed}}){lua_pushcfunction(L,entry.second);lua_setglobal(L,entry.first);}
 if(!mode && luaL_dostring(L,"owned=Sprite()"))return 91;
 std::string s=R"lua(
a=view(); b=view(); nullVector=Vector(0,0)
)lua";
 if(scenario=="speed") s+=R"lua(assert(a.PlaybackSpeed==1);a.PlaybackSpeed=.5;checkspeed(.5,0);assert(b.PlaybackSpeed==.5);a:Update();checkspeed(.5,.5);b:Update();checkspeed(.5,1);b.PlaybackSpeed=2;assert(a.PlaybackSpeed==2);a:Update();checkspeed(2,3);assert(not pcall(function()a.PlaybackSpeed=false end)))lua";
 if(scenario=="assign") s+=R"lua(a.Color=Color(1,1,1,1,1,1,1);checknative(1);a.Color=Color(1,1,1,1,0,0,0);checknative(0))lua";
 if(scenario=="alias") s+=R"lua(a.Color=Color(1,1,1,1,1,1,1);assert(b.Color.RO==1,'view lost color');changenative();assert(a.Color.RO==.75,'native change lost'))lua";
 if(scenario=="stale") {expectedOffset=0;s+=R"lua(a.Color=Color(1,1,1,1,1,1,1);b.Color=Color(1,1,1,1,0,0,0);a:Render(Vector(10,20));checknative(0))lua";}
 if(scenario=="flip") s+=R"lua(a.FlipX=true;checkflip(true);b.FlipX=false;checkflip(false);assert(not a.FlipX);a.Scale=Vector(2,3);assert(b.Scale.X==2 and b.Scale.Y==3))lua";
 if(scenario=="blink" || scenario=="highlight") {
  expectedOffset=scenario=="blink"?1:0;
  s+=R"lua(
 EID={Config={Indicator='@MODE@'},isRepentance=true,isMultiplayer=false};Isaac={WorldToScreen=function(p)return p end};CollectibleType={COLLECTIBLE_FLIP=0}
 function EID:IsGridEntity(e)return false end
 function EID:PlayersHaveCollectible(i)return false end
 function EID:getEntityData(e,k)return nil end
 @INDICATOR@
 @ENTITY@
 local e={Type=5,Variant=100,FrameCount=0,Position=Vector(10,20)}
 function e:GetSprite()return view()end
 function e:ToPickup()return {IsShopItem=function()return false end}end
 EID:renderIndicator(e,1);checknative(0)
 )lua";
  auto i=s.find("@MODE@");s.replace(i,6,scenario);
  // highlight四笔加亮、最后恢复，由旧颜色布局回归另行逐笔验证；本例核查结束后对象。
  if(scenario=="highlight") expectedOffset=2;
 }
 int result=luaL_dostring(L,s.c_str());if(result){std::fprintf(stderr,"%s\n",lua_tostring(L,-1));return 10;}
 if(scenario=="blink" && draws!=1)return 21;
 lua_close(L);std::puts("EID_SPRITE_PROPERTIES_OK");return 0;
}
"""
class EIDSpritePropertiesTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.temp=tempfile.TemporaryDirectory(prefix='eid-sprite-properties-')
  src=HARNESS.replace('@INDICATOR@',(ROOT/'tools/test_fixtures/eid-highlight/render-indicator.lua').read_text()).replace('@ENTITY@',(ROOT/'tools/test_fixtures/eid-highlight/render-entity.lua').read_text())
  cls.binary=build_lua_harness(source_root=ROOT/'runtime/source',workdir=Path(cls.temp.name),harness_source=src)
 @classmethod
 def tearDownClass(cls):cls.temp.cleanup()
 def test_immediate_assignment_and_live_views(self):
  for mode in range(3):
   for scenario in ('assign','alias','stale','flip','blink','highlight','speed'):
    with self.subTest(mode=mode,scenario=scenario):
     r=subprocess.run([str(self.binary),str(mode),scenario],capture_output=True,text=True)
     self.assertEqual(r.returncode,0,r.stdout+r.stderr)
