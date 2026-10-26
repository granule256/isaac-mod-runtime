"""剩余世界调用：公开入口→生产解析→独立NS目标/接收者/ABI和结果。

已有真实通过证据只索引，不把降级/方法存在当覆盖。只替换三条最终AsFunction目标。
两条版本候选独立记录UNRESOLVED，不制造生产入口。运行前须由主线程冻结生产源码。
"""
import hashlib
import json
import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from . import test_lua_entity_query as fixture
from . import test_support

ROOT=Path(__file__).resolve().parents[2]
SOURCE=ROOT/'runtime/source'
EVIDENCE=ROOT/'dist/api-remaining-recovery-20261025'
EXISTING_EVIDENCE={
    'Room:Render':{'test':'runtime/tests/test_api600_native.py','log':'dist/api-half-recovery-20261025/test_api600_native-run.log','scope':'真实Room this/原生Render调用计数'},
    'Seeds:InitSeedInfo':{'test':'runtime/tests/test_api200_main.py','log':'dist/api-half-recovery-20261025/test_api200_main-run.log','scope':'公开静态Seeds.InitSeedInfo→真实void原生桩；错误guard和跨base'},
    'Game:ChangeRoom':{'test':'runtime/tests/test_room_change_defaults.py','log':'dist/change-archive-20261017/005-room-change-default-dimension/resume-room-defaults-green.log','scope':'默认dimension=-1，nil/false/0/完整显式实参通过真实寄存器观察'},
}
# 固定目标和owner来自NRO具名动态符号；不可读取生产同行产生期望。
ENTRIES=(
    ('Game:Update',0x351884,'game'),
    ('Level:Update',0x3d08a4,'game'),
    ('Room:Update',0x46d788,'room'),
    ('Room:DestroyGrid',0x454cf4,'room'),
    ('Room:TurnGold',0x4649f8,'room'),
    ('Room:SpawnClearAward',0x456810,'room'),
    ('Room:PlayMusic',0x451834,'room'),
    ('EntityNPC:Morph',0x10faf4,'npc'),
    ('EntityPickup:Morph',0x26bd14,'pickup'),
    ('ItemPool:GetLastPool',0,'pool'),
    ('ItemPool:RemoveCollectible',0x3c61f0,'pool'),
    ('ItemPool:GetPillEffect',0x3c857c,'pool'),
    ('Game:SpawnParticles',0x3598f8,'game'),
    ('Room:GetRandomPosition',0x456110,'room'),
    ('Isaac:GetRandomPosition',0x456110,'room'),
    ('Isaac:ScreenToWorld',0,'room'),
)
UNRESOLVED={
    'EntityPlayer:SetTargetTrapDoor': '在线文档有候选；固定PC exe无逐字字符串/注册引用，完整PC main.lua也无入口，不能凭文档制造。',
    'Room:TryPlaceLadder': '在线文档有候选；固定PC exe无逐字字符串/注册引用，完整PC main.lua也无入口，不能凭文档制造。',
}
SCENES={
    'game_update':(0,"assert(select('#',g:Update())==0);CheckWorld(0)","g:Update()","assert(not pcall(g.Update,g,1))"),
    'level_update':(1,"assert(select('#',level:Update())==0);CheckWorld(1)","level:Update()","assert(not pcall(level.Update,level,1))"),
    'room_update':(2,"assert(select('#',room:Update())==0);CheckWorld(2)","room:Update()","assert(not pcall(room.Update,room,1))"),
    'destroy_grid':(3,"ResultWorld(1);assert(room:DestroyGrid(-7)==true);CheckWorld(3,-7,0,0);ResultWorld(0);assert(room:DestroyGrid(0x100000002,0,false)==false);CheckWorld(3,2,1,0)","room:DestroyGrid(-7)","assert(not pcall(room.DestroyGrid,room,{}));assert(not pcall(room.DestroyGrid,room,1.5))"),
    'turn_gold':(4,"assert(select('#',room:TurnGold())==0);CheckWorld(4)","room:TurnGold()","assert(not pcall(room.TurnGold,room,1))"),
    'clear_award':(5,"assert(select('#',room:SpawnClearAward())==0);CheckWorld(5)","room:SpawnClearAward()","assert(not pcall(room.SpawnClearAward,room,1))"),
    'play_music':(6,"assert(select('#',room:PlayMusic())==0);CheckWorld(6)","room:PlayMusic()","assert(not pcall(room.PlayMusic,room,1))"),
    'npc_morph':(7,"ResultWorld(1);assert(npc:Morph(0x100000002,-7,9,-1)==true);CheckWorld(7,2,-7,9,-1);ResultWorld(0);assert(npc:Morph(2,3,4,-1)==false);CheckWorld(7,2,3,4,-1)","npc:Morph(2,3,4,-1)","assert(not pcall(npc.Morph,npc,{},3,4,-1));assert(not pcall(npc.Morph,npc,2,3,4))"),
    'pickup_morph':(8,"assert(select('#',pickup:Morph(0x100000002,-7,9))==0);CheckWorld(8,2,-7,9,0,0,0);pickup:Morph(5,100,2,0,false,true);CheckWorld(8,5,100,2,1,0,1)","pickup:Morph(5,100,2)","assert(not pcall(pickup.Morph,pickup,{},3,4));assert(not pcall(pickup.Morph,pickup,5,100))"),
    'last_pool':(9,"assert(pool:GetLastPool()==23);LastPoolWorld();assert(pool:GetLastPool()==17);NoWorld()","pool:GetLastPool()","assert(not pcall(pool.GetLastPool,pool,1));assert(not pcall(pool.GetLastPool,{}))"),
    'remove_pool_collectible':(10,"ResultWorld(1);assert(pool:RemoveCollectible(0x100000002)==true);CheckWorld(10,2,0,0);ResultWorld(0);assert(pool:RemoveCollectible(-7,0,true)==false);CheckWorld(10,-7,1,1)","pool:RemoveCollectible(2)","assert(not pcall(pool.RemoveCollectible,pool,{}));assert(not pcall(pool.RemoveCollectible,pool,1.5))"),
    'pill_effect':(11,"assert(pool:GetPillEffect(0xfffffffe)==-37);CheckWorld(11,-2,0);assert(pool:GetPillEffect(2,p)==-37);CheckWorld(11,2,1);assert(pool:GetPillEffect(3,nil)==-37);CheckWorld(11,3,0)","pool:GetPillEffect(2)","assert(not pcall(pool.GetPillEffect,pool,{}));assert(not pcall(pool.GetPillEffect,pool))"),
    # PC main.lua:541 color or Default / height or100000 / subtype or0，不止省略，还含nil/false。
    'particles':(12,"assert(select('#',g:SpawnParticles(v,2,3,4.25))==0);CheckWorld(12,0);assert(select('#',g:SpawnParticles(v,2,3,4.25,Color(.25,.5,.75,.875,.125,.25,.375),-13.5,0x100000002))==0);CheckWorld(12,1);assert(select('#',g:SpawnParticles(v,2,3,4.25,nil,nil,nil))==0);CheckWorld(12,0);assert(select('#',g:SpawnParticles(v,2,3,4.25,false,false,false))==0);CheckWorld(12,0)","g:SpawnParticles(v,2,3,4.25)","assert(not pcall(g.SpawnParticles,g,{},2,3,4));assert(not pcall(g.SpawnParticles,g,v,2,3,{}))"),
    'room_random':(13,"local r=room:GetRandomPosition('-7.25');assert(getmetatable(r)==getmetatable(Vector(0,0)) and r.X==17.5 and r.Y==-23.25);r.X=99;CheckWorld(13,-7.25)","room:GetRandomPosition(-7.25)","assert(not pcall(room.GetRandomPosition,room,{}));assert(not pcall(room.GetRandomPosition,room))"),
    # PC80bb00从Manager取Room后margin=0调用7d9b50；不是对缺失方法返回nil的成功断言。
    'isaac_random':(14,"local r=Isaac.GetRandomPosition();assert(getmetatable(r)==getmetatable(Vector(0,0)) and r.X==17.5 and r.Y==-23.25);CheckWorld(14,0)","Isaac.GetRandomPosition()","assert(not pcall(Isaac.GetRandomPosition,{}))"),
    'screen_world':(15,"local source=Vector(1000,600);local result=Isaac.ScreenToWorld(source);assert(math.abs(result.X-89.230769230769)<0.0001 and math.abs(result.Y-218.461538461538)<0.0001);result.X=0;assert(source.X==1000 and source.Y==600);NoWorld()","Isaac.ScreenToWorld(v)","assert(not pcall(Isaac.ScreenToWorld,{}));assert(not pcall(Isaac.ScreenToWorld))"),
}
MOCKS=r'''
#include <cstdint>
extern "C" void WorldNativeTarget(std::uintptr_t);
extern "C" void WorldParticles(void*,const void*,int,int,float,const void*,float,unsigned);
extern "C" void WorldRandom(const void*,float,float*,float*);
extern "C" int WorldPill(void*,int,void*);
template<class F>struct WorldMock;
template<class V,class C>struct WorldMock<void(*)(void*,const V*,int,int,float,const C*,float,unsigned)>{static void Call(void*s,const V*v,int a,int b,float speed,const C*c,float h,unsigned sub){static_assert(sizeof(C)==44);WorldParticles(s,v,a,b,speed,c,h,sub);}};
template<class R>struct WorldMock<R(*)(const void*,float)>{static R Call(const void*s,float m){static_assert(sizeof(R)==8);R result{};WorldRandom(s,m,&result.x,&result.y);return result;}};
template<>struct WorldMock<int(*)(void*,int,void*)>{static int Call(void*s,int color,void*p){return WorldPill(s,color,p);}};
template<class F>F WorldHost(std::uintptr_t target){WorldNativeTarget(target);return &WorldMock<F>::Call;}
'''
MAIN=r'''
#include "interfaces/lua/entity_lifetime.hpp"
#include <cmath>
#include <cassert>
#include <cstdlib>
namespace LuaRuntime {void InstallWorldProbes();}
extern "C" {
#include <lauxlib.h>
extern std::uint32_t g_HostEngineCallTrampolineCalls;
extern std::uintptr_t g_HostEngineCallTrampolineLastTarget;
extern std::uint64_t g_HostEngineCallTrampolineLastIntegers[8];
extern std::uint64_t g_HostEngineCallTrampolineIntegerResult;
}
using namespace isaac::runtime;static std::vector<unsigned char> worldPool(0x1300),displayGlobals(16);static bool worldReady=true;
void* WorldRoom(){return worldReady?g_RoomBytes.data():nullptr;}void* WorldPool(){return worldReady?worldPool.data():nullptr;}
static const unsigned targets[]={FROZEN_OFFSETS};static unsigned directs{},beforeDirect{},beforeShared{};static std::uintptr_t directTarget{},receiver{},pillPlayer{};static int pillColor{},particleVariant{},particleCount{};static unsigned particleSubtype{};static float randomMargin{},particleSpeed{},particleHeight{},particleColor[11]{};
extern "C" void WorldNativeTarget(std::uintptr_t target){directTarget=target;}
extern "C" void WorldParticles(void*self,const void*position,int variant,int count,float speed,const void*color,float height,unsigned subtype){++directs;receiver=reinterpret_cast<std::uintptr_t>(self);float vector[2]{};std::memcpy(vector,position,8);assert(vector[0]==3.25F&&vector[1]==-7.5F);particleVariant=variant;particleCount=count;particleSpeed=speed;particleHeight=height;particleSubtype=subtype;std::memcpy(particleColor,color,44);}
extern "C" void WorldRandom(const void*self,float margin,float*x,float*y){++directs;receiver=reinterpret_cast<std::uintptr_t>(self);randomMargin=margin;*x=17.5F;*y=-23.25F;}
extern "C" int WorldPill(void*self,int color,void*player){++directs;receiver=reinterpret_cast<std::uintptr_t>(self);pillColor=color;pillPlayer=reinterpret_cast<std::uintptr_t>(player);return -37;}
int BeginWorld(lua_State*){beforeDirect=directs;beforeShared=g_HostEngineCallTrampolineCalls;return 0;}
int NoWorld(lua_State*L){if(directs!=beforeDirect||g_HostEngineCallTrampolineCalls!=beforeShared)return luaL_error(L,"unexpected native call");return 0;}
int ResultWorld(lua_State*L){g_HostEngineCallTrampolineIntegerResult=static_cast<std::uint64_t>(luaL_checkinteger(L,1));return 0;}
int LastPoolWorld(lua_State*){WriteAt<unsigned>(worldPool,0x8c0,17);return 0;}
int CheckWorld(lua_State*L){const unsigned index=static_cast<unsigned>(luaL_checkinteger(L,1));assert(index<16);
 const std::uintptr_t selves[]={AddressOf(g_GameBytes),AddressOf(g_GameBytes),AddressOf(g_RoomBytes),AddressOf(g_RoomBytes),AddressOf(g_RoomBytes),AddressOf(g_RoomBytes),AddressOf(g_RoomBytes),AddressOf(g_Entities[kEnemyA]),AddressOf(g_Entities[kPickup]),AddressOf(worldPool),AddressOf(worldPool),AddressOf(worldPool),AddressOf(g_GameBytes),AddressOf(g_RoomBytes),AddressOf(g_RoomBytes),0};
 if(index<=8||index==10){if(g_HostEngineCallTrampolineCalls!=beforeShared+1||directs!=beforeDirect)return luaL_error(L,"shared call count");if(g_HostEngineCallTrampolineLastTarget!=g_EngineBase+targets[index]||g_HostEngineCallTrampolineLastIntegers[0]!=selves[index])return luaL_error(L,"shared target/receiver");const unsigned count=index==3||index==10?3:index==7?4:index==8?6:0;for(unsigned i=0;i<count;++i)if(static_cast<std::uint32_t>(g_HostEngineCallTrampolineLastIntegers[i+1])!=static_cast<std::uint32_t>(luaL_checkinteger(L,static_cast<int>(i)+2)))return luaL_error(L,"native integer/bool/default at register %d",i+1);
 }else if(index==11||index==12||index==13||index==14){if(directs!=beforeDirect+1||g_HostEngineCallTrampolineCalls!=beforeShared)return luaL_error(L,"direct call count");if(directTarget!=g_EngineBase+targets[index]||receiver!=selves[index])return luaL_error(L,"direct target/receiver");
 if(index==11){const auto player=luaL_checkinteger(L,3)?AddressOf(g_Entities[kPlayer]):0;if(static_cast<std::uint32_t>(pillColor)!=static_cast<std::uint32_t>(luaL_checkinteger(L,2))||pillPlayer!=player)return luaL_error(L,"pill color/player");}
 if(index==13||index==14){if(randomMargin!=static_cast<float>(luaL_checknumber(L,2)))return luaL_error(L,"random margin");}
 if(index==12){const bool custom=luaL_checkinteger(L,2)!=0;assert(particleVariant==2&&particleCount==3&&particleSpeed==4.25F);assert(particleHeight==(custom?-13.5F:100000.0F)&&particleSubtype==(custom?2U:0U));const float expected[]={.25F,.5F,.75F,.875F,0,0,0,0,.125F,.25F,.375F};for(unsigned i=0;i<11;++i){const float want=custom?expected[i]:(i<4?1.0F:0.0F);if(particleColor[i]!=want)return luaL_error(L,"native ColorMod field %d",i);}}
 }else return luaL_error(L,"bad direct test index");return BeginWorld(L);}
int main(int argc,char**argv){if(argc!=3)return 90;const std::string scene=argv[1],mode=argv[2];static_cast<void>(kScriptTemplate);static_cast<void>(&HarnessHasCollectible);static_cast<void>(&BuildPrelude);static_cast<void>(&ExpectNumber);
 CreateBlocks();g_ModuleBytes.resize(0xabc000);g_EngineBase=AddressOf(g_ModuleBytes);g_GameBytes.resize(0x320000);FillEntities();WriteWord(g_Entities[kEnemyA],0,g_EngineBase+kEntityNpcVtableOffset);PublishLists();PublishGame();PublishEntityList(g_RoomBytes,true);LuaRuntime::SetEngineModuleBase(g_EngineBase);LuaRuntime::SetGameBindings(g_EngineBase+kGameOwnerGlobalSlotOffset,0x2222);
 const unsigned char guards[][16]={FROZEN_GUARDS};for(unsigned i=0;i<16;++i)if(targets[i])std::memcpy(g_ModuleBytes.data()+targets[i],guards[i],16);
 WriteAt<unsigned>(worldPool,0x8c0,23);WriteAt<float>(displayGlobals,0,1280);WriteAt<float>(displayGlobals,4,720);WriteAt<float>(displayGlobals,8,2);WriteWord(g_ModuleBytes,0xaac650,AddressOf(displayGlobals));WriteWord(g_ModuleBytes,0xaac658,AddressOf(displayGlobals)+4);WriteWord(g_ModuleBytes,0xaac7b0,AddressOf(displayGlobals)+8);WriteAt<float>(g_RoomBytes,0x1938,10);WriteAt<float>(g_RoomBytes,0x193c,-20);
 const char*names[]={SCENE_NAMES};const char*valid[]={SCENE_VALID};const char*first[]={SCENE_FIRST};const char*invalid[]={SCENE_INVALID};const unsigned ids[]={SCENE_IDS};unsigned selected=99;for(unsigned i=0;i<16;++i)if(scene==names[i])selected=i;if(selected==99)return 91;const auto index=ids[selected];
 const std::string body=mode=="valid"?valid[selected]:mode=="invalid"?std::string(invalid[selected])+";NoWorld()":"pcall(function() "+std::string(first[selected])+" end);NoWorld()";
 std::string script="local g=Game();local room=g:GetRoom();local level=g:GetLevel();local pool=g:GetItemPool();local p=Isaac.GetPlayer();local npc=Isaac.FindByType(20)[1]:ToNPC();local pickup=Isaac.FindByType(5)[1]:ToPickup();local v=Vector(3.25,-7.5);assert(room and level and pool and npc and pickup);local m=RegisterMod('remaining world native',1);m:AddCallback(1,function() BeginWorld();"+body+";_world_done={ok=1} end)";
 if(LuaRuntime::InitializeFromBuffer(script.data(),script.size(),"@world-native.lua")!=LuaRuntime::LuaInitResult::Success){char e[512]{};static_cast<void>(LuaRuntime::CopyLastLuaErrorText(e,sizeof(e)));std::puts(e);return 1;}LuaRuntime::InstallWorldProbes();
 // 首次解析前损坏入口，不能在同base成功缓存之后自改代码制造假红。
 if(mode=="guard"&&targets[index])g_ModuleBytes[targets[index]]^=1;
 if(mode=="owner"){worldReady=false;WriteWord(g_ModuleBytes,kGameOwnerGlobalSlotOffset,0);RetireEntityLifetime(AddressOf(g_Entities[kEnemyA]));RetireEntityLifetime(AddressOf(g_Entities[kPickup]));}
 LuaRuntime::DispatchPostUpdate();if(LuaRuntime::TakeCallbackError()){char e[512]{};static_cast<void>(LuaRuntime::CopyLastLuaErrorText(e,sizeof(e)));std::puts(e);return 2;}double done{};return LuaRuntime::ReadLuaTableNumber("_world_done","ok",&done)==0&&done==1?0:3;}
'''


def _snapshot(paths):
    return {str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


class RemainingWorldNativeCalls(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(prefix='remaining-world-native-');cls.addClassCleanup(cls.tmp.cleanup);work=Path(cls.tmp.name)
        sources=list(test_support.layered_lua_runtime_sources(SOURCE))
        cls.paths=tuple(sorted(set(sources)|set((ROOT/'runtime/src').rglob('*.hpp'))|set(SOURCE.rglob('*.hpp'))));cls.before=_snapshot(cls.paths)
        EVIDENCE.mkdir(parents=True,exist_ok=True)
        (EVIDENCE/(os.environ.get('ISAAC_WORLD_EVIDENCE_PREFIX','main-world')+'-input-before.json')).write_text(json.dumps(cls.before,indent=2)+'\n');cls.addClassCleanup(cls._stable)
        original=Path('/Users/kelinls/code/github/isaac mod');nro_path=next(original.glob('The Binding of Isaac_ Afterbirth+*/Program #0/1/.nro/Repentance.nro'));nro=nro_path.read_bytes()
        quote=lambda s:json.dumps(s,ensure_ascii=True)
        main=MAIN.replace('FROZEN_OFFSETS',','.join(hex(offset) for _,offset,_ in ENTRIES))
        main=main.replace('FROZEN_GUARDS',','.join('{'+','.join(map(str,nro[offset:offset+16] if offset else bytes(16)))+'}' for _,offset,_ in ENTRIES))
        main=main.replace('SCENE_NAMES',','.join(map(quote,SCENES)))
        # 必须先替换INVALID，防止VALID子串撞名。
        main=main.replace('SCENE_INVALID',','.join(quote(value[3]) for value in SCENES.values()))
        main=main.replace('SCENE_VALID',','.join(quote(value[1]) for value in SCENES.values()))
        main=main.replace('SCENE_FIRST',','.join(quote(value[2]) for value in SCENES.values()))
        main=main.replace('SCENE_IDS',','.join(str(value[0]) for value in SCENES.values()))
        prefix=fixture.HARNESS[:fixture.HARNESS.index('int main(')]
        prefix=re.sub(r'namespace GameFileReader \{\nTextReadResult[\s\S]*?\n\}\n\}', '',prefix,count=1)
        prefix=prefix.replace('GameRoomObservation ReadCurrentGameRoom(uintptr_t, void**) {\n    return GameRoomObservation::RoomUnreadable;\n}', 'void* WorldRoom();\nGameRoomObservation ReadCurrentGameRoom(uintptr_t,void** room){*room=WorldRoom();return *room?GameRoomObservation::Success:GameRoomObservation::RoomNull;}')
        prefix=prefix.replace('GameItemPoolObservation ReadCurrentGameItemPool(uintptr_t, void**) {\n    return GameItemPoolObservation::GameUnreadable;\n}', 'void* WorldPool();\nGameItemPoolObservation ReadCurrentGameItemPool(uintptr_t,void** pool){*pool=WorldPool();return *pool?GameItemPoolObservation::Success:GameItemPoolObservation::GameUnreadable;}')
        changes={ROOT/'runtime/src/interfaces/lua/game_api.cpp':('GameSpawnParticlesFn',),ROOT/'runtime/src/interfaces/lua/remaining_api.cpp':('RoomGetRandomPositionFn','GetPillEffectFn')}
        replaced={}
        for path,aliases in changes.items():
            code=path.read_text().replace('#include "engine_color_mod.hpp"', '#include "interfaces/lua/engine_color_mod.hpp"')
            for alias in aliases:
                count=0
                for owner in ('isaac::runtime::engine_call::','engine_call::'):
                    old=f'{owner}AsFunction<{alias}>'
                    count+=code.count(old);code=code.replace(old,f'WorldHost<{alias}>')
                if count!=1:raise AssertionError(f'最终调用点不唯一: {alias}: {count}')
            target=work/('instrumented_'+path.name);target.write_text(MOCKS+code);replaced[path]=target
        runtime=SOURCE/'lua_runtime.cpp';instrumented=work/'instrumented_lua_runtime.cpp'
        instrumented.write_text(runtime.read_text()+r'''
int BeginWorld(lua_State*);int NoWorld(lua_State*);int ResultWorld(lua_State*);int LastPoolWorld(lua_State*);int CheckWorld(lua_State*);
namespace LuaRuntime {void InstallWorldProbes(){
#define B(n) lua_pushcfunction(g_LuaState,::n);lua_setglobal(g_LuaState,#n)
B(BeginWorld);B(NoWorld);B(ResultWorld);B(LastPoolWorld);B(CheckWorld);
#undef B
}}
''');replaced[runtime]=instrumented
        replacement=[replaced.get(p,p) for p in sources]
        flags=tuple(flag for flag in test_support.HARNESS_COMPILE_FLAGS if not flag.startswith('-DEXL_DIAGNOSTIC_STAGE='))
        (EVIDENCE/(os.environ.get('ISAAC_WORLD_EVIDENCE_PREFIX','main-world')+'-harness.cpp')).write_text(prefix+main)
        with mock.patch.object(test_support,'layered_lua_runtime_sources',return_value=replacement),mock.patch.object(test_support,'HARNESS_COMPILE_FLAGS',flags):
            cls.binary=test_support.build_lua_harness(source_root=SOURCE,workdir=work,harness_source=prefix+main)

    @classmethod
    def _stable(cls):
        after=_snapshot(cls.paths);(EVIDENCE/(os.environ.get('ISAAC_WORLD_EVIDENCE_PREFIX','main-world')+'-input-after.json')).write_text(json.dumps(after,indent=2)+'\n')
        if after!=cls.before:raise AssertionError('运行期间生产输入SHA改变，结果不能归属单一版本')

    def test_real_registered_world_native_contracts(self):
        selection=os.environ.get('ISAAC_WORLD_SCENES');scenes=selection.split(',') if selection else tuple(SCENES)
        self.assertTrue(all(scene in SCENES for scene in scenes))
        for scene in scenes:
            index=SCENES[scene][0]
            modes=('valid','invalid','owner') if not ENTRIES[index][1] else ('valid','invalid','guard','owner')
            # 缺失Isaac公开入口先做正向真值红检，不能把pcall(nil)失败当已验证错误闸门。
            if scene=='isaac_random':modes=('valid',)
            for mode in modes:
                with self.subTest(scene=scene,mode=mode):
                    result=subprocess.run([str(self.binary),scene,mode],capture_output=True,text=True)
                    print(f'{ENTRIES[index][0]} {mode}: exit={result.returncode} {result.stdout}{result.stderr}',flush=True)
                    self.assertEqual(result.returncode,0,result.stdout+result.stderr)
