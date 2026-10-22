"""Agony房间碰撞、NPC目标、overlay帧：真实Lua和原生签名，不能编造默认答案。"""
import re,subprocess,tempfile,unittest
from pathlib import Path
from unittest import mock
from . import test_lua_entity_query as fixture
from . import test_support
ROOT=Path(__file__).resolve().parents[2]
MOCKS=r'''
#include <cstdint>
extern "C" void QueryTarget(std::uintptr_t);
extern "C" int QueryCollision(std::uintptr_t,float,float);
extern "C" std::uintptr_t QueryNpc(std::uintptr_t);
extern "C" int QueryOverlay(void*);
template<class Fn>struct QueryNativeMock;
template<class R,class Self,class Vec>struct QueryNativeMock<R(*)(Self,Vec)>{
 static R Call(Self s,Vec v){return QueryCollision(s,v.x,v.y);}
};
template<class R>struct QueryNativeMock<R(*)(std::uintptr_t)>{
 static R Call(std::uintptr_t s){return QueryNpc(s);}
};
template<class R>struct QueryNativeMock<R(*)(void*)>{static R Call(void* s){return QueryOverlay(s);}};
template<class Fn>Fn QueryHostFunction(std::uintptr_t target){QueryTarget(target);return &QueryNativeMock<Fn>::Call;}
'''
MAIN=r'''
void* QueryCurrentRoom(){return reinterpret_cast<void*>(AddressOf(g_RoomBytes));}
static unsigned calls{};static unsigned kind{};static std::uintptr_t target{},self{};static float px{},py{};
extern "C" void QueryTarget(std::uintptr_t t){target=t;}
extern "C" int QueryCollision(std::uintptr_t s,float x,float y){++calls;self=s;px=x;py=y;return x<0?4:3;}
extern "C" std::uintptr_t QueryNpc(std::uintptr_t s){++calls;self=s;return kind==1?0:AddressOf(g_Entities[kPlayer]);}
extern "C" int QueryOverlay(void* s){++calls;self=reinterpret_cast<std::uintptr_t>(s);return kind==1?-1:9;}
int main(int argc,char**argv){
 static_cast<void>(kScriptTemplate);static_cast<void>(&HarnessHasCollectible);static_cast<void>(&BuildPrelude);static_cast<void>(&ExpectNumber);
 if(argc!=2)return 99;std::string scene=argv[1];CreateBlocks();FillEntities();PublishLists();PublishGame();PublishEntityList(g_RoomBytes,true);
 LuaRuntime::SetEngineModuleBase(g_EngineBase);LuaRuntime::SetGameBindings(AddressOf(g_OwnerSlotBytes),0x2222);
 const unsigned offsets[]={0x459d38,0x10b464,0xafe0};const unsigned char raw[][16]={GUARDS};
 for(unsigned i=0;i<3;++i)std::memcpy(g_ModuleBytes.data()+offsets[i],raw[i],16);
 const std::string prelude="local m=RegisterMod('agony-query',1);local room=Game():GetRoom();local npc=Isaac.FindByType(20)[1]:ToNPC();local sprite=npc:GetSprite();assert(type(room.GetGridCollisionAtPos)=='function');assert(type(npc.GetPlayerTarget)=='function');assert(type(sprite.GetOverlayFrame)=='function');m:AddCallback(1,function() ";
 std::string body;unsigned want=0,offset=0;std::uintptr_t receiver=0;
 if(scene=="collision"||scene=="outside"){body="assert(room:GetGridCollisionAtPos(Vector("+std::string(scene=="outside"?"-20":"80.25")+",140.5))=="+std::string(scene=="outside"?"4":"3")+")";want=1;offset=offsets[0];receiver=AddressOf(g_RoomBytes);}
 else if(scene=="npc"||scene=="nil_target"){kind=scene=="nil_target";body=kind?"assert(npc:GetPlayerTarget()==nil)":"local e=npc:GetPlayerTarget();assert(e.Type==1 and e.Position.X==80 and e:GetData()==Isaac.GetPlayer(0):GetData())";want=1;offset=offsets[1];receiver=AddressOf(g_Entities[kEnemyA]);}
 else if(scene=="overlay"||scene=="no_overlay"){kind=scene=="no_overlay";body="assert(sprite:GetOverlayFrame()=="+std::string(kind?"-1":"9")+")";want=1;offset=offsets[2];receiver=AddressOf(g_Entities[kEnemyA])+kEntitySpriteOffset;}
 else if(scene=="bad_arg")body="assert(not pcall(room.GetGridCollisionAtPos,room,{}));assert(not pcall(room.GetGridCollisionAtPos,room))";
 else if(scene=="guard"||scene=="unknown")body="assert(not pcall(room.GetGridCollisionAtPos,room,Vector(1,2)));assert(not pcall(npc.GetPlayerTarget,npc));assert(not pcall(sprite.GetOverlayFrame,sprite))";
 else return 98;
 auto script=prelude+body+" end)";
 if(LuaRuntime::InitializeFromBuffer(script.data(),script.size(),"@agony-native.lua")!=LuaRuntime::LuaInitResult::Success)return 1;
 if(scene=="guard")for(unsigned i=0;i<3;++i)g_ModuleBytes[offsets[i]+15]^=1;
 if(scene=="unknown")LuaRuntime::SetEngineModuleBase(0);
 LuaRuntime::DispatchPostUpdate();if(LuaRuntime::TakeCallbackError()){char error[512]{};static_cast<void>(LuaRuntime::CopyLastLuaErrorText(error,sizeof(error)));std::puts(error);return 2;}
 if(calls!=want)return 3;if(want&&(self!=receiver||target!=g_EngineBase+offset))return 4;
 if(scene=="collision"&&(px!=80.25F||py!=140.5F))return 5;
 if(scene=="outside"&&(px!=-20||py!=140.5F))return 6;return 0;
}
'''
class AgonyNativeQueryTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory(prefix='isaac-agony-query-');p=Path(cls.tmp.name)
  source='void* QueryCurrentRoom();\n'+fixture.HARNESS[:fixture.HARNESS.index('int main(')]+MAIN
  source=source.replace('GameRoomObservation ReadCurrentGameRoom(uintptr_t, void**) {\n    return GameRoomObservation::RoomUnreadable;\n}', 'GameRoomObservation ReadCurrentGameRoom(uintptr_t, void** out) {*out=QueryCurrentRoom();return GameRoomObservation::Success;}')
  source=re.sub(r'namespace GameFileReader \{\nTextReadResult[\s\S]*?\n\}\n\}', '', source,count=1)
  nro=next(Path('/Users/kelinls/code/github/isaac mod').glob('The Binding of Isaac_ Afterbirth+*/Program #0/1/.nro/Repentance.nro')).read_bytes()
  source=source.replace('GUARDS',','.join('{'+','.join(map(str,nro[o:o+16]))+'}' for o in (0x459d38,0x10b464,0xafe0)))
  instrumented={}
  for file,signature in [('remaining_api.cpp','AgonyRoomCollisionFn'),('isaac_api.cpp','AgonyNpcTargetFn'),('sprite_api.cpp','AgonyOverlayFrameFn')]:
   path=ROOT/'runtime/src/interfaces/lua'/file;code=path.read_text().replace('engine_call::AsFunction<'+signature+'>','QueryHostFunction<'+signature+'>')
   out=p/file;out.write_text(MOCKS+code);instrumented[path]=out
  sources=[instrumented.get(x,x) for x in test_support.layered_lua_runtime_sources(fixture.SOURCE)]
  with mock.patch.object(test_support,'layered_lua_runtime_sources',return_value=sources):
   cls.binary=test_support.build_lua_harness(source_root=fixture.SOURCE,workdir=p,harness_source=source)
 @classmethod
 def tearDownClass(cls):cls.tmp.cleanup()
 def test_original_receiver_signed_result_hfa_and_guards(self):
  for scene in ('collision','outside','npc','nil_target','overlay','no_overlay','bad_arg','guard','unknown'):
   with self.subTest(scene=scene):
    r=subprocess.run([str(self.binary),scene],capture_output=True,text=True)
    self.assertEqual(r.returncode,0,r.stdout+r.stderr)
