"""五条真实Lua方法、Bomb字段、typed tear返回与寿命；仅替换原生调用地址。"""
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from . import test_lua_batch330_familiar_view as fixture
from . import test_support

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'runtime/source'
MOCKS = r'''
#include <cstdint>
extern "C" void EntityMethodTarget(std::uintptr_t);
extern "C" void* EntitySpawnerHost(std::uintptr_t,std::uintptr_t);
extern "C" void EntitySourceHost(std::uintptr_t,std::uintptr_t);
extern "C" void EntityFrameHost(std::uintptr_t,const char*,int);
extern "C" void EntityResetHost(std::uintptr_t);
extern "C" void EntityScaleHost(std::uintptr_t,float);
extern "C" void EntitySoundHost(std::uintptr_t,unsigned,float,int,bool,float);
extern "C" void EntityWalkHost(std::uintptr_t,const void*,const void*,float);
extern "C" void* EntityTearHost(std::uintptr_t,const void*,float,float,unsigned,std::uintptr_t,float);
template<class Fn>struct EntityMethodMock;
template<class Self>struct EntityMethodMock<void(*)(Self,const char*,std::int32_t)>{
 static void Call(Self s,const char* n,int f){EntityFrameHost(s,n,f);}
};
template<class Self>struct EntityMethodMock<void(*)(Self)>{static void Call(Self s){EntityResetHost(s);}};
template<class Self>struct EntityMethodMock<void(*)(Self,float)>{static void Call(Self s,float v){EntityScaleHost(s,v);}};
template<class Self>struct EntityMethodMock<void(*)(Self,std::uint32_t,float,std::int32_t,bool,float)>{
 static void Call(Self s,unsigned id,float volume,int delay,bool loop,float pitch){EntitySoundHost(s,id,volume,delay,loop,pitch);}
};
template<class Self,class String>struct EntityMethodMock<void(*)(Self,const String*,const String*,float)>{
 static void Call(Self s,const String* h,const String* v,float speed){EntityWalkHost(s,h,v,speed);}
};
template<class Self,class Vec>struct EntityMethodMock<void*(*)(Self,const Vec*,Vec,std::uint32_t,std::uintptr_t,float)>{
 static void* Call(Self s,const Vec* p,Vec v,unsigned flags,std::uintptr_t source,float d){return EntityTearHost(s,p,v.x,v.y,flags,source,d);}
};
template<class Self,class Vec>struct EntityMethodMock<void*(*)(Self,std::int32_t,std::int32_t,const Vec*,const Vec*,std::uintptr_t,std::int32_t,std::int32_t,std::int32_t)>{
 static void* Call(Self self,int,int,const Vec*,const Vec*,std::uintptr_t spawner,int,int,int){return EntitySpawnerHost(self,spawner);}
};
template<class Self,class Vec,class Flags,class Color>struct EntityMethodMock<void(*)(Self,const Vec*,float,Flags,const Color*,std::uintptr_t,float,bool,unsigned long,bool)>{
 static void Call(Self self,const Vec*,float,Flags,const Color*,std::uintptr_t source,float,bool,unsigned long,bool){EntitySourceHost(self,source);}
};
template<class Fn>Fn EntityMethodHostFunction(std::uintptr_t target){EntityMethodTarget(target);return &EntityMethodMock<Fn>::Call;}
'''
MAIN = r'''
#include "interfaces/lua/entity_lifetime.hpp"
static unsigned calls[8]{};static std::uintptr_t spawnerAddress{},sourceAddress{};static std::uintptr_t target{},self{},hptr{},vptr{};
static int frame{},delay{};static unsigned sound{};static float volume{},pitch{},speed{};static bool loop{};
static std::string horizontal,vertical,name;
static std::string ReadString(const void* data){
 const auto* b=static_cast<const unsigned char*>(data);std::uint64_t n{};const char* p{};
 if(!(b[0]&1))return std::string(reinterpret_cast<const char*>(b+1),b[0]>>1);
 std::memcpy(&n,b+8,8);std::memcpy(&p,b+16,8);return std::string(p,n);
}
extern "C" void EntityMethodTarget(std::uintptr_t t){target=t;}
extern "C" void EntityFrameHost(std::uintptr_t s,const char* n,int f){++calls[0];self=s;name=n;frame=f;}
extern "C" void EntityResetHost(std::uintptr_t s){++calls[1];self=s;}
extern "C" void EntityScaleHost(std::uintptr_t s,float value){++calls[5];self=s;WriteAt<float>(g_FamiliarBytes,0x410,value);WriteAt<float>(g_FamiliarBytes,0x414,value);}
extern "C" void EntitySoundHost(std::uintptr_t s,unsigned id,float v,int d,bool l,float p){++calls[2];self=s;sound=id;volume=v;delay=d;loop=l;pitch=p;}
extern "C" void EntityWalkHost(std::uintptr_t s,const void* h,const void* v,float threshold){++calls[3];self=s;hptr=reinterpret_cast<std::uintptr_t>(h);vptr=reinterpret_cast<std::uintptr_t>(v);horizontal=ReadString(h);vertical=ReadString(v);speed=threshold;}
extern "C" void* EntityTearHost(std::uintptr_t s,const void*,float,float,unsigned,std::uintptr_t,float){++calls[4];self=s;return g_FamiliarBytes.data();}
extern "C" void* EntitySpawnerHost(std::uintptr_t,std::uintptr_t spawner){++calls[6];spawnerAddress=spawner;return g_FamiliarBytes.data();}
extern "C" void EntitySourceHost(std::uintptr_t,std::uintptr_t source){++calls[7];sourceAddress=source;}
int main(int argc,char** argv){
 if(argc!=2)return 99;std::string scene=argv[1];PublishFakeGame();LuaRuntime::SetGameBindings(AddressOf(g_OwnerSlotBytes),0x2222);
 const unsigned offsets[]={0xa65c,0x33d010,0x119998,0x1100b0,0x2a991c,0x33bf7c,0x3540d0,0x355c68};
 const unsigned char guards[][16]={METHOD_GUARDS};
 for(unsigned i=0;i<8;++i)std::memcpy(g_ModuleBytes.data()+offsets[i],guards[i],16);
 bool bomb=scene.starts_with("bomb")||scene.find("_bomb")!=std::string::npos;bool tear=scene.starts_with("tear")||scene.find("_tear")!=std::string::npos;
 WriteAt<std::uintptr_t>(g_FamiliarBytes,0,g_EngineBase+(bomb?kEntityBombVtableOffset:(tear?kEntityTearVtableOffset:kEntityNpcVtableOffset)));
 WriteAt<unsigned>(g_FamiliarBytes,kEntityTypeOffset,bomb?4:(tear?2:20));
 std::string prelude="local raw=Isaac.GetPlayer(0).Parent;local obj=raw:"+std::string(bomb?"ToBomb":(tear?"ToTear":"ToNPC"))+"();assert(obj~=nil);local m=RegisterMod('entity-method',1);";
 std::string body;unsigned method=99,want=0;
 if(scene=="frame"){method=0;want=1;body="assert(select('#',obj:SetSpriteFrame('Spikes','4294967294'))==0)";}
 else if(scene=="frame_numeric"){method=0;want=1;body="obj:SetSpriteFrame(123,7.0)";}
 else if(scene=="frame_nul"){method=0;want=1;body="obj:SetSpriteFrame('A\\0B',2)";}
 else if(scene=="sound"||scene=="sound_truth"||scene=="sound_nil"){method=2;want=1;body="assert(select('#',obj:PlaySound('4294967294','0.625','-3',"+std::string(scene=="sound_truth"?"0":(scene=="sound_nil"?"nil":"false"))+",'1.25'))==0)";}
 else if(scene=="walk"||scene=="walk_long"||scene=="walk_numeric"){method=3;want=1;body="assert(select('#',obj:AnimWalkFrame("+std::string(scene=="walk_long"?"string.rep('H',35),string.rep('V',47)":(scene=="walk_numeric"?"123,456":"'WalkH','WalkV'"))+",'0.125'))==0)";}
 else if(scene=="tear_reset"){method=1;want=1;body="obj:ResetSpriteScale();assert(obj.Scale==1.5)";WriteAt<float>(g_FamiliarBytes,0x410,1.5F);}
 else if(scene=="tear_fire"){method=1;want=1;body="local t=Isaac.GetPlayer(0):FireTear(Vector(1,2),Vector(3,4),false,true,true);assert(getmetatable(t)==getmetatable(obj));t.Scale=1.5;t:ResetSpriteScale();assert(t:GetData()==obj:GetData())";}
 else if(scene=="tear_scale_only")body="obj.Scale='1.5';assert(obj.Scale==1.5)";
 else if(scene=="tear_typed_only")body="local t=Isaac.GetPlayer(0):FireTear(Vector(1,2),Vector(3,4),false,true,true);assert(getmetatable(t)==getmetatable(obj))";
 else if(scene=="tear_scale_guard"||scene=="tear_scale_token")body="assert(not pcall(function() obj.Scale=1.5 end))";
 else if(scene=="npc_callback")body="";
 else if(scene.starts_with("source_")){
  bool stale=scene.ends_with("_stale"),reuse=scene.ends_with("_reuse");
  if(stale||reuse)body="assert(EntityRef(obj).Entity==nil);Game():Spawn(2,0,Vector(1,2),Vector(3,4),obj,0,123);assert(not pcall(Isaac.Explode,Vector(1,2),obj,10))";
  else body="local ref=EntityRef(obj);assert(ref.Type==obj.Type and ref.Entity:GetData()==obj:GetData());Game():Spawn(2,0,Vector(1,2),Vector(3,4),obj,0,123);Isaac.Explode(Vector(1,2),obj,10)";
  if(reuse)body+=";local fresh=Isaac.GetPlayer(0).Parent:"+std::string(bomb?"ToBomb":(tear?"ToTear":"ToNPC"))+"();assert(EntityRef(obj).Entity==nil);assert(EntityRef(fresh).Entity:GetData()==fresh:GetData());Game():Spawn(2,0,Vector(1,2),Vector(3,4),fresh,0,123);Isaac.Explode(Vector(1,2),fresh,10)";
 }
 else if(scene=="bomb_fields")body="assert(obj.IsFetus==false);obj.IsFetus=true;assert(obj.IsFetus==true);obj.IsFetus=0;assert(obj.IsFetus==true);obj.IsFetus=nil;assert(obj.IsFetus==false);obj.IsFetus='x';assert(obj.IsFetus==true);assert(obj:GetData()==raw:GetData());assert(obj:ToBomb(123):GetData()==obj:GetData());assert(obj.Type==4 and type(obj.GetSprite)=='function');assert(raw:ToTear()==nil)";
 else if(scene=="bomb_token"||scene=="bomb_reuse")body="assert(not pcall(function() return obj.IsFetus end));assert(not pcall(function() obj.IsFetus=true end));assert(obj:ToBomb()==nil)";
 else if(scene=="bomb_wrong"||scene=="bomb_wrong_type")body="assert(raw:ToBomb()==nil);assert(not pcall(function() return obj.IsFetus end));assert(not pcall(function() obj.IsFetus=true end))";
 else if(scene=="args")body="assert(not pcall(obj.SetSpriteFrame,obj,nil,0));assert(not pcall(obj.SetSpriteFrame,obj,'X',1.5));assert(not pcall(obj.SetSpriteFrame,obj,'X'));assert(not pcall(obj.PlaySound,obj,1,1,0,false));assert(not pcall(obj.PlaySound,obj,1,nil,0,false,1));assert(not pcall(obj.AnimWalkFrame,obj,'X','Y'));assert(not pcall(obj.AnimWalkFrame,obj,{},'Y',0))";
 else if(scene=="guard"||scene=="unknown"||scene=="token"||scene=="wrong_npc")body="assert(not pcall(obj.SetSpriteFrame,obj,'X',1));assert(not pcall(obj.PlaySound,obj,1,1,0,false,1));assert(not pcall(obj.AnimWalkFrame,obj,'X','Y',0))";
 else if(scene=="tear_guard"||scene=="tear_token"||scene=="tear_wrong"||scene=="tear_wrong_type")body="assert(not pcall(obj.ResetSpriteScale,obj))";
 else if(scene=="bomb_consumer")body="local e=raw;"+std::string(BOMB_CONSUMER)+";assert(observed==true)";
 else if(scene=="tear_consumer"){method=1;want=1;body="local player=Isaac.GetPlayer(0);local vel=Vector(3,4);"+std::string(TEAR_CONSUMER);}
 else return 98;

 if(scene=="wrong_npc")body="assert(not pcall(obj.PlaySound,obj,1,1,0,false,1));assert(not pcall(obj.AnimWalkFrame,obj,'X','Y',0))";
 if(scene=="bomb_reuse")body+=";local fresh=Isaac.GetPlayer(0).Parent:ToBomb();fresh.IsFetus=true;assert(not pcall(function() obj.IsFetus=false end));assert(fresh.IsFetus==true)";
 if(scene=="bomb_consumer")WriteAt<unsigned char>(g_FamiliarBytes,0x438,1);
 auto script=prelude+"m:AddCallback(1,function() "+body+" end)";
 if(scene=="npc_callback")script=prelude+"m:AddCallback(69,function(_,npc) assert(getmetatable(npc)==getmetatable(obj));"+std::string(YELLOW_CONSUMER)+";local ent=npc;"+std::string(CREEP_CONSUMER)+";return false end,20)";
 if(LuaRuntime::InitializeFromBuffer(script.data(),script.size(),"@entity-method.lua")!=LuaRuntime::LuaInitResult::Success){char err[512]{};static_cast<void>(LuaRuntime::CopyLastLuaErrorText(err,sizeof(err)));std::puts(err);return 1;}
 if(scene=="guard"||scene=="tear_guard")for(unsigned i=0;i<8;++i)g_ModuleBytes[offsets[i]+15]^=1;
 if(scene=="tear_scale_guard")g_ModuleBytes[offsets[5]+15]^=1;
 if(scene=="unknown")LuaRuntime::SetEngineModuleBase(0);
 if(scene=="token"||scene=="tear_token"||scene=="tear_scale_token"||scene=="bomb_token"||scene=="bomb_reuse")isaac::runtime::RetireEntityLifetime(AddressOf(g_FamiliarBytes));

 if(scene=="bomb_wrong_type"||scene=="tear_wrong_type")WriteAt<unsigned>(g_FamiliarBytes,kEntityTypeOffset,20);
 if(scene.starts_with("source_")&&(scene.ends_with("_stale")||scene.ends_with("_reuse")))isaac::runtime::RetireEntityLifetime(AddressOf(g_FamiliarBytes));
 if(scene=="wrong_npc"||scene=="tear_wrong"||scene=="bomb_wrong")WriteAt<std::uintptr_t>(g_FamiliarBytes,0,g_EngineBase+kEntityPlayerVtableOffset);
 if(scene=="npc_callback"){if(LuaRuntime::DispatchPreNpcUpdate(AddressOf(g_FamiliarBytes),20))return 13;if(calls[0]!=1||calls[2]!=1||calls[3]!=1||name!="Spikes"||frame!=0||sound!=237||horizontal!="Walk"||vertical!="Walk"||self!=AddressOf(g_FamiliarBytes))return 14;return LuaRuntime::TakeCallbackError()?15:0;}
 LuaRuntime::DispatchPostUpdate();if(LuaRuntime::TakeCallbackError()){char err[512]{};static_cast<void>(LuaRuntime::CopyLastLuaErrorText(err,sizeof(err)));std::puts(err);return 2;}
 if(scene.starts_with("source_")){const bool stale=scene.ends_with("_stale"),reuse=scene.ends_with("_reuse");if(calls[6]!=(reuse?2U:1U)||calls[7]!=(stale?0U:1U)||spawnerAddress!=(stale?0:AddressOf(g_FamiliarBytes))||(!stale&&sourceAddress!=AddressOf(g_FamiliarBytes)))return 17;}
 if(method<4){if(calls[method]!=want)return 3;const auto receiver=AddressOf(g_FamiliarBytes)+(method==0?kEntitySpriteOffset:0);if(target!=g_EngineBase+offsets[method]||self!=receiver)return 4;}
 else for(unsigned i=0;i<4;++i)if(calls[i])return 5;
 if(scene=="frame"&&(name!="Spikes"||frame!=-2))return 6;
 if(scene=="frame_numeric"&&(name!="123"||frame!=7))return 7;
 if(scene=="frame_nul"&&(name!="A"||frame!=2))return 8;
 if(scene.starts_with("sound")&&(sound!=0xfffffffeU||volume!=0.625F||delay!=-3||pitch!=1.25F||loop!=(scene=="sound_truth")))return 9;
 if(scene.starts_with("walk")){if(hptr==0||vptr==0||hptr==vptr||hptr%8||vptr%8||speed!=0.125F)return 10;if(horizontal!=(scene=="walk_long"?std::string(35,'H'):(scene=="walk_numeric"?"123":"WalkH"))||vertical!=(scene=="walk_long"?std::string(47,'V'):(scene=="walk_numeric"?"456":"WalkV")))return 11;}
 if((scene=="tear_fire"||scene=="tear_consumer")&&calls[4]!=1)return 12;
 return 0;
}
'''

class StaticEntityMethodTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(prefix='isaac-static-entity-');p=Path(cls.tmp.name)
        source='#include <string>\n'+fixture.HARNESS[:fixture.HARNESS.index('int main(')]+MAIN
        nro=next(ROOT.glob('The Binding of Isaac_ Afterbirth+*/Program #0/1/.nro/Repentance.nro')).read_bytes()
        source=source.replace('METHOD_GUARDS',','.join('{'+','.join(map(str,nro[o:o+16]))+'}' for o in (0xa65c,0x33d010,0x119998,0x1100b0,0x2a991c,0x33bf7c,0x3540d0,0x355c68)))
        # 固定闭包的原始三行调用块，只有 surrounding observed 用于确认分支进入。
        blind=(ROOT/'dist/agony-dependency-static-20261010/loaded-source/code/Items/Collectibles/BlindFaith.lua').read_text().splitlines()
        source=source.replace('BOMB_CONSUMER','R"AGONY('+ '\n'.join(blind[120:122])+" observed=b.IsFetus end" +')AGONY"')
        source=source.replace('TEAR_CONSUMER','R"AGONY('+ '\n'.join(blind[153:158])+')AGONY"')
        yellow=(ROOT/'dist/agony-dependency-static-20261010/loaded-source/code/Monsters/YellowBlock.lua').read_text().splitlines()
        creep=(ROOT/'dist/agony-dependency-static-20261010/loaded-source/code/Monsters/Creeps/SickCreep.lua').read_text().splitlines()
        source=source.replace('YELLOW_CONSUMER','R"AGONY('+ '\n'.join(yellow[46:48])+')AGONY"')
        source=source.replace('CREEP_CONSUMER','R"AGONY('+creep[202]+')AGONY"')
        path=ROOT/'runtime/src/interfaces/lua/isaac_api.cpp';code=path.read_text()
        for name in ('EntitySetSpriteFrameFn','EntityTearResetSpriteScaleFn','EntityNpcPlaySoundFn','EntityNpcAnimWalkFrameFn','EntityTearSetScaleFn','FireTearFn','SpawnExFn','BombExplosionEffectsFn'):
            code=code.replace('engine_call::AsFunction<'+name+'>','EntityMethodHostFunction<'+name+'>')
            code=code.replace('isaac::runtime::EntityMethodHostFunction','EntityMethodHostFunction')
        out=p/'instrumented_isaac_api.cpp';out.write_text(MOCKS+code)
        sources=[out if f==path else f for f in test_support.layered_lua_runtime_sources(SOURCE)]
        with mock.patch.object(test_support,'layered_lua_runtime_sources',return_value=sources):
            cls.binary=test_support.build_lua_harness(source_root=SOURCE,workdir=p,harness_source=source)

    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()

    def check_scenes(self,scenes):
        for scene in scenes:
            with self.subTest(scene=scene):
                r=subprocess.run([str(self.binary),scene],capture_output=True,text=True)
                self.assertEqual(r.returncode,0,r.stdout+r.stderr)

    def test_pc_string_integer_number_and_lua_truth_conversion(self):
        self.check_scenes(('frame','frame_numeric','frame_nul','sound','sound_truth','sound_nil','walk','walk_long','walk_numeric','args'))

    def test_typed_firetear_and_original_blindfaith_blocks(self):
        self.check_scenes(('tear_reset','tear_fire','tear_consumer','bomb_consumer','tear_scale_only','tear_typed_only','npc_callback'))

    def test_bomb_fields_inheritance_shared_data_and_lifetime(self):
        self.check_scenes(('bomb_fields','bomb_token','bomb_reuse','bomb_wrong','bomb_wrong_type'))

    def test_all_new_views_as_entityref_spawn_spawner_and_source(self):
        self.check_scenes(tuple('source_'+view+suffix for view in ('npc','tear','bomb') for suffix in ('','_stale','_reuse')))

    def test_complete_guard_token_wrong_receiver_and_module(self):
        self.check_scenes(('guard','unknown','token','wrong_npc','tear_guard','tear_token','tear_wrong','tear_wrong_type','tear_scale_guard','tear_scale_token'))

if __name__=='__main__':unittest.main()
