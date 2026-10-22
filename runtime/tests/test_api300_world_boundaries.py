"""第三批world35的独立边界判据；复用夹具，始终走生产Attach/Catalog。"""
import re, subprocess, tempfile, unittest
from pathlib import Path
from . import test_lua_entity_query as fixture
from . import test_api300_world as original
from .test_support import build_lua_harness

def _scene_main(source):
    return source.replace("int main(){", 'int main(int argc,char**argv){if(argc!=2)return 99;const std::string scene=argv[1];', 1).replace(
        '#include "lua_object_handles.hpp"',
        '#include "lua_object_handles.hpp"\n#include "interfaces/lua/entity_lifetime.hpp"\n#include "interfaces/lua/bitset128_api.hpp"')

def _replace_script(source, script):
    return re.sub(r' const char\*script=R"LUA\([\s\S]*?\)LUA";', lambda _: ' const char*script=R"LUA('+script+')LUA";', source, count=1)

NATIVE_MAIN = _scene_main(original.EXTRA_BASELINE_MAIN)
NATIVE_MAIN = NATIVE_MAIN.replace('assert(i==23);return true;', 'assert(i==23||i==0);return i==23;').replace('assert(i==17);return true;', 'assert(i==17||i==0);return i==17;')
NATIVE_MAIN = NATIVE_MAIN.replace('assert(p==wantNpc&&distance==12.5F);return {11,29};', 'assert(p==wantNpc&&(distance==12.5F||distance==0));return distance==0?LuaRuntime::VectorHandle{0,0}:LuaRuntime::VectorHandle{11,29};')
NATIVE_MAIN = NATIVE_MAIN.replace('assert(p==wantNpc&&v.x==3&&v.y==4);return true;', 'assert(p==wantNpc&&((v.x==3&&v.y==4)||(v.x==0&&v.y==0)));return v.x!=0;')
NATIVE_MAIN = NATIVE_MAIN.replace('static unsigned calls[13]{};', 'static unsigned calls[13]{};static bool positive=true;static unsigned baseZCalls{};')
NATIVE_MAIN = NATIVE_MAIN.replace('assert(p==wantNpc);return true;', 'assert(p==wantNpc);return positive;').replace('assert(p==wantNpc);return 17;', 'assert(p==wantNpc);return positive?17:-7;')
NATIVE_MAIN = NATIVE_MAIN.replace('static void Delete(void*p)', 'static std::uint32_t BaseZ(void*p){assert(p==wantKnife||p==wantLaser);++baseZCalls;return 0xf0000003U;}\nstatic void Delete(void*p)')
NATIVE_MAIN = NATIVE_MAIN.replace('SetApi300WorldNativeTestBindings(bindings);', 'bindings.methods[12]=engine_call::AddressOfFunction(&BaseZ);SetApi300WorldNativeTestBindings(bindings);')
NATIVE_MAIN = NATIVE_MAIN.replace('fill(guard::kSeedComboLayoutEntry,guard::kSeedComboLayoutGuard);', 'fill(guard::kSeedComboLayoutEntry,guard::kSeedComboLayoutGuard);fill(guard::kEntityGetRenderZEntry,guard::kEntityGetRenderZGuard);')
NATIVE_MAIN = NATIVE_MAIN.replace('lua_pop(L,1);static_cast<void>(RegisterIsaacApi(L));', 'lua_pop(L,1);luaL_requiref(L,LUA_STRLIBNAME,luaopen_string,1);lua_pop(L,1);static_cast<void>(RegisterIsaacApi(L));')
native_lua = r'''
npc=Isaac.FindByType(20)[1]:ToNPC();assert(npc and knife and laser)
assert(EntityEffect.IsPlayerCreep("23") and not EntityEffect.IsPlayerCreep(0))
assert(ItemConfig.IsValidCollectible("17") and not ItemConfig.IsValidCollectible(0))
assert(npc:CanReroll());assert(npc:CanBeDamagedFromVelocity(Vector(3,4)));assert(not npc:CanBeDamagedFromVelocity(Vector(0,0)))
local target=npc:CalcTargetPosition(12.5);assert(target.X==11 and target.Y==29)
target=npc:CalcTargetPosition(0);assert(target.X==0 and target.Y==0)
assert(npc:GetAliveEnemyCount()==17)
assert(knife:GetRenderZ()==0xf0000001 and laser:GetRenderZ()==0xf0000002)
for _,v in ipairs({false,true,{},1.5,"bad"})do
 assert(not pcall(function()EntityEffect.IsPlayerCreep(v)end));assert(not pcall(function()ItemConfig.IsValidCollectible(v)end))
end
for _,n in ipairs({"CanReroll","GetAliveEnemyCount","CalcTargetPosition","CanBeDamagedFromVelocity"})do
 local f=npc[n];assert(not pcall(function()f(knife,Vector(3,4))end));assert(not pcall(function()f({},Vector(3,4))end))
end
assert(not pcall(function()npc:CalcTargetPosition(false)end));assert(not pcall(function()npc:CalcTargetPosition()end))
assert(not pcall(function()npc:CanBeDamagedFromVelocity({X=3,Y=4})end));assert(not pcall(function()npc:CanBeDamagedFromVelocity(nil)end))
assert(not pcall(function()knife.GetRenderZ(laser)end));assert(not pcall(function()laser.GetRenderZ(npc)end))
'''
NATIVE_MAIN = _replace_script(NATIVE_MAIN, native_lua)
# 删旧夹具收尾判据，用本边界实际调用次数；原文件不改。
start = NATIVE_MAIN.index('for(unsigned i:{0U,1U,2U')
NATIVE_MAIN = NATIVE_MAIN[:start] + r'''
if(scene=="badguard"){for(auto n:calls)if(n)return 90;lua_close(L);return 0;}
if(calls[0]!=2||calls[1]!=2||calls[2]!=2||calls[3]!=2||calls[4]!=1||calls[5]!=1||calls[6]!=1||calls[7]!=1)return 91;
positive=false;if(luaL_dostring(L,"assert(not npc:CanReroll());assert(npc:GetAliveEnemyCount()==-7)"))return 92;
WriteWord(g_ModuleBytes,kEntityKnifeVtableOffset+0x68,g_EngineBase+guard::kEntityGetRenderZEntry);
WriteWord(g_ModuleBytes,kEntityLaserVtableOffset+0x68,g_EngineBase+guard::kEntityGetRenderZEntry);
if(luaL_dostring(L,"assert(knife:GetRenderZ()==0xf0000003 and laser:GetRenderZ()==0xf0000003)"))return 93;
if(baseZCalls!=2)return 94;
if(scene=="dead"){
 RetireEntityLifetime(AddressOf(g_Entities[kEnemyA]));
 if(luaL_dostring(L,"for _,n in ipairs({'CanReroll','GetAliveEnemyCount','CalcTargetPosition','CanBeDamagedFromVelocity'})do assert(not pcall(function()npc[n](npc,Vector(3,4))end))end"))return 95;
}
if(scene=="crossbase"){
 std::vector<unsigned char> changed=g_ModuleBytes;const auto base=AddressOf(changed);
 WriteWord(g_Entities[kEnemyA],0,base+(GenericEntityVtable()-g_EngineBase));
 WriteWord(knife,0,base+kEntityKnifeVtableOffset);WriteWord(laser,0,base+kEntityLaserVtableOffset);
 WriteWord(changed,kEntityKnifeVtableOffset+0x68,base+guard::kEntityGetRenderZEntry);
 WriteWord(changed,kEntityLaserVtableOffset+0x68,base+guard::kEntityGetRenderZEntry);
 LuaRuntime::SetEngineModuleBase(base);
''' + '\n'.join(' changed[guard::k'+n+'Entry]^=1;' for n in (
'EntityEffectIsPlayerCreep','ItemConfigIsValidCollectible','EntityNPCCalcTargetPosition','EntityNPCCanBeDamagedFromVelocity','EntityNPCCanReroll','EntityNPCGetAliveEnemyCount','EntityKnifeGetRenderZ','EntityLaserGetRenderZ','EntityGetRenderZ')) + r'''
 if(luaL_dostring(L,R"LUA(local function denied(f)local ok,e=pcall(f);assert(not ok and string.find(e,"guard"),tostring(e))end
 denied(function()EntityEffect.IsPlayerCreep(23)end);denied(function()ItemConfig.IsValidCollectible(17)end)
 denied(function()npc:CalcTargetPosition(12.5)end);denied(function()npc:CanBeDamagedFromVelocity(Vector(3,4))end)
 denied(function()npc:CanReroll()end);denied(function()npc:GetAliveEnemyCount()end)
 denied(function()knife:GetRenderZ()end);denied(function()laser:GetRenderZ()end)
)LUA")){std::fprintf(stderr,"%s\n",lua_tostring(L,-1));return 96;}
}
if(calls[4]!=2||calls[5]!=2||baseZCalls!=2)return 97;lua_close(L);return 0;}
'''
native_bad = r'''
npc=Isaac.FindByType(20)[1]:ToNPC();assert(npc and knife and laser)
local function denied(f)local ok,e=pcall(f);assert(not ok and string.find(e,"guard"),tostring(e))end
denied(function()EntityEffect.IsPlayerCreep(23)end);denied(function()ItemConfig.IsValidCollectible(17)end)
denied(function()npc:CalcTargetPosition(12.5)end);denied(function()npc:CanBeDamagedFromVelocity(Vector(3,4))end)
denied(function()npc:CanReroll()end);denied(function()npc:GetAliveEnemyCount()end)
denied(function()knife:GetRenderZ()end);denied(function()laser:GetRenderZ()end)
'''
point = 'const char*script=R"LUA('
# guard损坏必须在第一次API调用前；新scene进程没有旧成功缓存。
insert = 'if(scene=="badguard"){\n'+'\n'.join(' g_ModuleBytes[guard::k'+n+'Entry]^=1;'for n in (
'EntityEffectIsPlayerCreep','ItemConfigIsValidCollectible','EntityNPCCalcTargetPosition','EntityNPCCanBeDamagedFromVelocity','EntityNPCCanReroll','EntityNPCGetAliveEnemyCount','EntityKnifeGetRenderZ','EntityLaserGetRenderZ'))+'\n}\n '
NATIVE_MAIN = NATIVE_MAIN.replace(point, insert+point, 1)
NATIVE_MAIN=NATIVE_MAIN.replace('if(scene=="badguard"){\n', 'if(scene=="badbaseguard"){g_ModuleBytes[guard::kEntityGetRenderZEntry]^=1;WriteWord(g_ModuleBytes,kEntityKnifeVtableOffset+0x68,g_EngineBase+guard::kEntityGetRenderZEntry);WriteWord(g_ModuleBytes,kEntityLaserVtableOffset+0x68,g_EngineBase+guard::kEntityGetRenderZEntry);}\n if(scene=="badguard"){\n',1)
NATIVE_MAIN=NATIVE_MAIN.replace('if(scene=="badguard"){for(auto n:calls)', 'if(scene=="badbaseguard"){for(auto n:calls)if(n)return 89;if(baseZCalls)return 88;lua_close(L);return 0;}\nif(scene=="badguard"){for(auto n:calls)',1)
NATIVE_MAIN=NATIVE_MAIN.replace('if(scene=="dead"){', 'if(scene=="badvirtual"){WriteWord(g_ModuleBytes,kEntityKnifeVtableOffset+0x68,g_EngineBase+0x1000);WriteWord(g_ModuleBytes,kEntityLaserVtableOffset+0x68,0);if(luaL_dostring(L,"assert(not pcall(function()knife:GetRenderZ()end));assert(not pcall(function()laser:GetRenderZ()end))"))return 87;}\nif(scene=="dead"){',1)

NATIVE_MAIN = NATIVE_MAIN.replace(')LUA";if(luaL_dostring(L,script))', ')LUA";if(scene=="badguard")script=R"LUA('+native_bad+')LUA";if(luaL_dostring(L,script))', 1)

NATIVE_MAIN=NATIVE_MAIN.replace('if(luaL_dostring(L,script))', 'if(scene=="badbaseguard")script=R"LUA(local function denied(f)local ok,e=pcall(f);assert(not ok and string.find(e,"guard"),tostring(e))end;denied(function()knife:GetRenderZ()end);denied(function()laser:GetRenderZ()end))LUA";if(luaL_dostring(L,script))',1)

FLAGS_MAIN = _scene_main(original.FLAGS_BASELINE_MAIN)
FLAGS_MAIN = FLAGS_MAIN.replace('static unsigned flagCalls[2]{};', 'static unsigned flagCalls[2]{};static void*wantBomb{};')
FLAGS_MAIN = FLAGS_MAIN.replace('++flagCalls[1];', 'assert(self==wantBomb);++flagCalls[1];')
FLAGS_MAIN = FLAGS_MAIN.replace('const BitSet128Value flags{3,8};', 'wantBomb=bomb.data();const BitSet128Value flags{0x8000000000000003ULL,0x8000000000000008ULL};')
flags_lua = r'''
tear=Isaac.FindByType(2)[1]:ToTear();assert(tear and bomb and knife and laser,"all four real families required")
local views={tear,bomb,knife,laser};local seen=0
for i,e in ipairs(views)do
 seen=seen+1;assert(e:HasTearFlags(BitSet128(4,8))) -- ANY，高位相交即可
 assert(not e:HasTearFlags(BitSet128(4,0)));assert(e:HasTearFlags(1));assert(e:HasTearFlags(0x8000000000000000))
 assert(not pcall(function()e:HasTearFlags("1")end))
 for _,bad in ipairs({false,true,{},1.5,"bad"})do assert(not pcall(function()e:HasTearFlags(bad)end));assert(not pcall(function()e:ClearTearFlags(bad)end))end
 assert(not pcall(function()e:HasTearFlags(nil)end));assert(not pcall(function()e:ClearTearFlags()end))
 assert(select("#",e:ClearTearFlags(BitSet128(1,8)))==0)
 assert(e:HasTearFlags(BitSet128(2,0)));assert(e:HasTearFlags(BitSet128(0,0x8000000000000000)))
 assert(not e:HasTearFlags(BitSet128(1,8)))
 e:ClearTearFlags(1) -- 公开PC ~int再转bitset：high=0，不能当128位取反
 assert(not e:HasTearFlags(BitSet128(0,0x8000000000000000)))
 assert(e:HasTearFlags(2));e:ClearTearFlags("2") -- Lua~接受numeric string，Has不接受
 assert(not e:HasTearFlags(2));assert(e:HasTearFlags(0x8000000000000000))
 assert(not pcall(function()e.ClearTearFlags({},1)end));assert(not pcall(function()e.HasTearFlags({},1)end))
end
assert(seen==4)
'''
FLAGS_MAIN = _replace_script(FLAGS_MAIN, flags_lua)
FLAGS_MAIN = re.sub(r'assert\(flagCalls\[0\]==1&&flagCalls\[1\]==1\);[\s\S]*$', lambda _: r'''
if(scene=="badguard"){assert(flagCalls[0]==0&&flagCalls[1]==0);lua_close(L);return 0;}
assert(flagCalls[0]==3&&flagCalls[1]==3);
for(auto item:{std::pair<void*,std::size_t>{g_Entities[kTearNear].data(),kEntityTearFlagsOffset},{bomb.data(),kEntityBombTearFlagsOffset},{knife.data(),kEntityKnifeTearFlagsOffset},{laser.data(),kEntityLaserTearFlagsOffset}}){
 BitSet128Value v{};std::memcpy(&v,static_cast<unsigned char*>(item.first)+item.second,16);assert(v.low==0x8000000000000000ULL&&v.high==0);
}
if(scene=="dead"){
 for(auto p:{AddressOf(g_Entities[kTearNear]),AddressOf(bomb),AddressOf(knife),AddressOf(laser)})RetireEntityLifetime(p);
 if(luaL_dostring(L,"for _,e in ipairs({tear,bomb,knife,laser})do assert(not pcall(function()e:HasTearFlags(1)end));assert(not pcall(function()e:ClearTearFlags(1)end))end"))return 92;
}
if(scene=="crossbase"){
 std::vector<unsigned char>changed=g_ModuleBytes;const auto base=AddressOf(changed);
 WriteWord(g_Entities[kTearNear],0,base+kEntityTearVtableOffset);WriteWord(bomb,0,base+kEntityBombVtableOffset);
 WriteWord(knife,0,base+kEntityKnifeVtableOffset);WriteWord(laser,0,base+kEntityLaserVtableOffset);
 changed[guard::kTearFlagsSetterEntry]^=1;changed[guard::kBombFlagsSetterEntry]^=1;LuaRuntime::SetEngineModuleBase(base);
 if(luaL_dostring(L,"for _,e in ipairs({tear,bomb})do local ok,err=pcall(function()e:ClearTearFlags(1)end);assert(not ok and string.find(err,'guard'),tostring(err))end;knife:ClearTearFlags(-1);laser:ClearTearFlags('-1');assert(not knife:HasTearFlags(0x8000000000000000) and not laser:HasTearFlags(0x8000000000000000))"))return 93;
}
assert(flagCalls[0]==3&&flagCalls[1]==3);lua_close(L);return 0;}
''', FLAGS_MAIN)
FLAGS_MAIN = FLAGS_MAIN.replace('lua_pop(L,1);static_cast<void>(RegisterIsaacApi(L));', 'lua_pop(L,1);luaL_requiref(L,LUA_STRLIBNAME,luaopen_string,1);lua_pop(L,1);static_cast<void>(RegisterIsaacApi(L));')
FLAGS_MAIN = FLAGS_MAIN.replace(point, 'if(scene=="badguard"){g_ModuleBytes[guard::kTearFlagsSetterEntry]^=1;g_ModuleBytes[guard::kBombFlagsSetterEntry]^=1;}\n '+point,1)
flag_bad = r'''
tear=Isaac.FindByType(2)[1]:ToTear();assert(tear and bomb and knife and laser)
for _,e in ipairs({tear,bomb})do
 assert(e:HasTearFlags(1))
 local ok,err=pcall(function()e:ClearTearFlags(BitSet128(1,8))end);assert(not ok and string.find(err,"guard"),tostring(err))
end
knife:ClearTearFlags(1);laser:ClearTearFlags("1")
assert(not knife:HasTearFlags(BitSet128(0,8)));assert(not laser:HasTearFlags(BitSet128(0,8)))
'''
FLAGS_MAIN = FLAGS_MAIN.replace(')LUA";if(luaL_dostring(L,script))', ')LUA";if(scene=="badguard")script=R"LUA('+flag_bad+')LUA";if(luaL_dostring(L,script))',1)

FIELD_MAIN = _scene_main(original.BASELINE_MAIN).replace('#include "interfaces/lua/game_api.hpp"', '#include "interfaces/lua/game_api.hpp"\n#include <cassert>')
FIELD_MAIN = FIELD_MAIN.replace('lua_pop(L,1);static_cast<void>(RegisterIsaacApi(L));', 'lua_pop(L,1);luaL_requiref(L,LUA_STRLIBNAME,luaopen_string,1);lua_pop(L,1);static_cast<void>(RegisterIsaacApi(L));')
field_lua = r'''
game=Game();level=game:GetLevel();seed=game:GetSeeds();npc=Isaac.FindByType(20)[1]:ToNPC();path=npc.Pathfinder
assert(level and seed and npc and path)
assert(level:GetRoomCount()==11 and level:GetAngelRoomChance()==0.25 and level:GetDungeonPlacementSeed()==0xf1234567)
assert(seed:IsInitialized() and seed:GetPlayerInitSeed()==0xf1234567 and seed:CountSeedEffects()==2)
assert(path:HasDirectPath() and path:GetEvadeMovementCountdown()==23)
level:AddAngelRoomChance(-0.5);assert(level:GetAngelRoomChance()==-0.25)
level:SetCanSeeEverything(0);level:SetCanSeeEverything(false);seed:ClearStartSeed();assert(not seed:IsInitialized() and seed:CountSeedEffects()==2)
path:SetCanCrushRocks(0);path:SetCanCrushRocks(false)
for _,v in ipairs({false,true,{},"bad"})do assert(not pcall(function()level:AddAngelRoomChance(v)end))end
for _,f in ipairs({level.GetRoomCount,seed.IsInitialized,path.HasDirectPath})do assert(not pcall(function()f({})end))end
'''
FIELD_MAIN=FIELD_MAIN.replace('static int GameCtor(', 'static int CheckBools(lua_State*L){const bool level=g_GameBytes[0x11]!=0;const bool path=g_Entities[kEnemyA][kEntityNpcPathfinderOffset+0x73c]!=0;assert(level==(lua_toboolean(L,1)!=0));assert(path==(lua_toboolean(L,2)!=0));return 0;}\nstatic int GameCtor(',1)
FIELD_MAIN=FIELD_MAIN.replace(' const char*script=', ' lua_pushcfunction(L,CheckBools);lua_setglobal(L,"checkBools");\n const char*script=',1)
field_lua=field_lua.replace('level:SetCanSeeEverything(0);level:SetCanSeeEverything(false);', 'level:SetCanSeeEverything(0);path:SetCanCrushRocks(0);checkBools(true,true);level:SetCanSeeEverything(false);path:SetCanCrushRocks(false);checkBools(false,false);')

FIELD_MAIN = _replace_script(FIELD_MAIN, field_lua)
FIELD_MAIN = FIELD_MAIN.replace('lua_close(L);return 0;}', r'''
if(scene=="badguard"){lua_close(L);return 0;}
WriteAt<std::int32_t>(g_GameBytes,0x21510,-3);WriteAt<std::uint32_t>(g_GameBytes,0x21580,0x81234567);
WriteAt<std::uint8_t>(g_Entities[kEnemyA],kEntityNpcPathfinderOffset+0x730,0);WriteAt<std::int32_t>(g_Entities[kEnemyA],kEntityNpcPathfinderOffset+0x740,-9);
WriteAt<std::uint32_t>(g_GameBytes,kGameSeedsObjectOffset+4,0);WriteAt<std::uint64_t>(g_GameBytes,kGameSeedsObjectOffset+0x68,0);
if(luaL_dostring(L,"assert(level:GetRoomCount()==-3 and level:GetDungeonPlacementSeed()==0x81234567);assert(not seed:IsInitialized() and seed:CountSeedEffects()==0);assert(not path:HasDirectPath() and path:GetEvadeMovementCountdown()==-9)"))return 92;
if(scene=="dead"){
 RetireEntityLifetime(AddressOf(g_Entities[kEnemyA]));
 if(luaL_dostring(L,"assert(not pcall(function()return path:HasDirectPath()end));assert(not pcall(function()path:SetCanCrushRocks(true)end))"))return 93;
}
if(scene=="deadgame"){
 WriteWord(g_OwnerSlotBytes,0,0);
 if(luaL_dostring(L,"assert(not pcall(function()return level:GetRoomCount()end));assert(not pcall(function()seed:ClearStartSeed()end))"))return 94;
}
if(scene=="crossbase"){
 std::vector<unsigned char>changed=g_ModuleBytes;const auto base=AddressOf(changed);
 WriteWord(g_Entities[kEnemyA],0,base+(GenericEntityVtable()-g_EngineBase));
 changed[guard::kLevelLayoutEntry]^=1;changed[guard::kSeedsLayoutEntry]^=1;changed[guard::kPathFinderLayoutEntry]^=1;
 LuaRuntime::SetEngineModuleBase(base);
 if(luaL_dostring(L,"for _,f in ipairs({function()return level:GetRoomCount()end,function()return seed:IsInitialized()end,function()return path:HasDirectPath()end})do local ok,e=pcall(f);assert(not ok and string.find(e,'guard'),tostring(e))end"))return 95;
}
lua_close(L);return 0;}
''',1)
FIELD_MAIN = FIELD_MAIN.replace(point,'if(scene=="badguard"){g_ModuleBytes[guard::kLevelLayoutEntry]^=1;g_ModuleBytes[guard::kSeedsLayoutEntry]^=1;g_ModuleBytes[guard::kPathFinderLayoutEntry]^=1;}\n '+point,1)
field_bad=r'''
game=Game();level=game:GetLevel();seed=game:GetSeeds();npc=Isaac.FindByType(20)[1]:ToNPC();path=npc.Pathfinder
assert(level and seed and path)
for _,f in ipairs({function()return level:GetRoomCount()end,function()return seed:IsInitialized()end,function()return path:HasDirectPath()end})do local ok,e=pcall(f);assert(not ok and string.find(e,"guard"),tostring(e))end
'''
FIELD_MAIN = FIELD_MAIN.replace(')LUA";if(luaL_dostring(L,script))',')LUA";if(scene=="badguard")script=R"LUA('+field_bad+')LUA";if(luaL_dostring(L,script))',1)

class World35Boundaries(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(prefix="api300-world-boundaries-")
        cls.binaries={}
    @classmethod
    def tearDownClass(cls): cls.tmp.cleanup()
    def _run(self,name,scenes):
        if name not in self.binaries:
            main={"native":NATIVE_MAIN,"flags":FLAGS_MAIN,"fields":FIELD_MAIN,"seeds":SEEDS_MAIN}[name]
            source=fixture.HARNESS[:fixture.HARNESS.index("int main(")]+main
            source=re.sub(r'namespace GameFileReader \{\nTextReadResult[\s\S]*?\n\}\n\}',"",source,count=1)
            self.binaries[name]=build_lua_harness(source_root=fixture.SOURCE,workdir=Path(self.tmp.name)/name,harness_source=source)
        for scene in scenes:
            with self.subTest(scene=scene):
                result=subprocess.run([str(self.binaries[name]),scene],capture_output=True,text=True)
                self.assertEqual(result.returncode,0,result.stdout+result.stderr)
    def test_native_registration_parameters_false_guard_cache_and_retirement(self):
        self._run("native",("normal","badguard","badbaseguard","badvirtual","crossbase","dead"))
    def test_four_real_flag_views_numeric_masks_guard_cache_and_retirement(self):
        self._run("flags",("normal","badguard","crossbase","dead"))
    def test_live_level_seed_path_fields_layout_guards_and_retirement(self):
        self._run("fields",("normal","badguard","crossbase","dead","deadgame"))

SEEDS_MAIN = _scene_main(original.EXTRA_BASELINE_MAIN)
SEEDS_MAIN = SEEDS_MAIN.replace('static unsigned calls[13]{};', 'static unsigned calls[13]{};static unsigned releases{};static bool failText{};static lua_Alloc priorAllocator{};static void*allocatorContext{};')
old = re.search(r'static Api100NativeString Text\([\s\S]*?\nstatic void Clear',SEEDS_MAIN).group()
SEEDS_MAIN = SEEDS_MAIN.replace(old, r'''
static Api100NativeString Text(std::uint32_t seed){
 ++calls[10];assert(seed==17||seed==0);Api100NativeString v{};
 if(seed==0){v.bytes[0]=0;return v;}
 static const char text[]="Long seed conversion output: 0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ";
 const std::uint64_t length=sizeof(text)-1;auto*p=std::malloc(length+1);assert(p);std::memcpy(p,text,length+1);
 const std::uint64_t capacity=(length+1)|1ULL;std::memcpy(v.bytes,&capacity,8);std::memcpy(v.bytes+8,&length,8);std::memcpy(v.bytes+16,&p,8);
 if(failText)failText=true;return v;
}
static void* FailAllocator(void*context,void*p,std::size_t oldSize,std::size_t newSize){
 if(failText&&newSize>0)return nullptr;return priorAllocator(context,p,oldSize,newSize);
}
static void Clear''')
SEEDS_MAIN = SEEDS_MAIN.replace('assert(tree==wantTree&&node==wantNode);', 'assert(tree==wantTree&&(node==wantNode||node==nullptr));')
SEEDS_MAIN = SEEDS_MAIN.replace('static void Delete(void*p){assert(p);std::free(p);}', 'static void Delete(void*p){assert(p);++releases;std::free(p);}')
SEEDS_MAIN = SEEDS_MAIN.replace('lua_pop(L,1);static_cast<void>(RegisterIsaacApi(L));','lua_pop(L,1);luaL_requiref(L,LUA_STRLIBNAME,luaopen_string,1);lua_pop(L,1);static_cast<void>(RegisterIsaacApi(L));')
# 三节点树让左右走向与ANY命中都真实消费，不用存在性代替。
SEEDS_MAIN = SEEDS_MAIN.replace('std::vector<unsigned char> knife(0x1000),laser(0x1000),effectsNode(32),comboNode(32),comboSets(3*24);','std::vector<unsigned char> knife(0x1000),laser(0x1000),effectsNode(32),comboNode(32),leftNode(32),rightNode(32),comboSets(3*24);')
SEEDS_MAIN = SEEDS_MAIN.replace('WriteAt<std::int32_t>(comboNode,0x1c,7);','WriteAt<std::int32_t>(comboNode,0x1c,7);WriteWord(comboNode,0,AddressOf(leftNode));WriteWord(comboNode,8,AddressOf(rightNode));WriteAt<std::int32_t>(leftNode,0x1c,3);WriteAt<std::int32_t>(rightNode,0x1c,9);WriteWord(comboSets,24+16,3);')
seed_lua=r'''
seeds=Game():GetSeeds();assert(seeds)
assert(seeds:GetStartSeedString()=="Long seed conversion output: 0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ")
assert(seeds:IsSeedComboBanned(1,7));assert(seeds:IsSeedComboBanned(1,3));assert(seeds:IsSeedComboBanned(1,9))
assert(not seeds:IsSeedComboBanned(1,4));assert(not seeds:IsSeedComboBanned(0,7))
assert(seeds:IsSeedComboBanned("4294967297","4294967303"))
for _,v in ipairs({false,true,{},1.5,"bad",-1,3})do assert(not pcall(function()seeds:IsSeedComboBanned(v,7)end))end
assert(not pcall(function()seeds:IsSeedComboBanned(1)end));assert(not pcall(function()seeds:IsSeedComboBanned(1,false)end))
assert(not pcall(function()seeds.GetStartSeedString({},17)end));assert(not pcall(function()seeds.ClearSeedEffects({},17)end))
seeds:ClearSeedEffects();assert(seeds:CountSeedEffects()==0 and seeds:IsInitialized())
'''
SEEDS_MAIN = _replace_script(SEEDS_MAIN,seed_lua)
start=SEEDS_MAIN.index('for(unsigned i:{0U,1U,2U')
SEEDS_MAIN=SEEDS_MAIN[:start]+r'''
if(scene=="badguard"){assert(!calls[10]&&!calls[11]&&!releases);lua_close(L);return 0;}
if(scene=="allocator-missing"){assert(!calls[10]&&!releases);lua_close(L);return 0;}
if(scene=="oom"){
 failText=false;lua_setallocf(L,priorAllocator,allocatorContext);lua_settop(L,0);lua_gc(L,LUA_GCCOLLECT,0);
 assert(calls[10]==1&&releases==1);lua_close(L);return 0;
}
assert(calls[10]==1&&releases==1&&calls[11]==1);
std::uint64_t count{},root{},begin{};std::memcpy(&count,g_GameBytes.data()+kGameSeedsObjectOffset+0x68,8);
std::memcpy(&root,g_GameBytes.data()+kGameSeedsObjectOffset+0x60,8);std::memcpy(&begin,g_GameBytes.data()+kGameSeedsObjectOffset+0x58,8);
assert(count==0&&root==0&&begin==AddressOf(g_GameBytes)+kGameSeedsObjectOffset+0x60);
assert(!std::memcmp(beforeTree.data(),g_GameBytes.data()+kGameSeedsObjectOffset,0x58));
if(luaL_dostring(L,"seeds:ClearSeedEffects();assert(seeds:CountSeedEffects()==0)"))return 91;
assert(calls[11]==2);
if(luaL_dostring(L,"seeds:ClearStartSeed();assert(not seeds:IsInitialized());assert(seeds:GetStartSeedString()==\"\")"))return 90;
assert(calls[10]==2&&releases==1);
WriteAt<std::int32_t>(rightNode,0x1c,10);
if(luaL_dostring(L,"assert(not seeds:IsSeedComboBanned(1,9));assert(seeds:IsSeedComboBanned(1,10))"))return 92;
if(scene=="malformed"){
 WriteWord(comboSets,24+16,0);
 if(luaL_dostring(L,"assert(not pcall(function()seeds:IsSeedComboBanned(1,10)end))"))return 93;
 WriteWord(comboSets,24+16,3);WriteWord(leftNode,0,AddressOf(leftNode));
 if(luaL_dostring(L,"assert(not pcall(function()seeds:IsSeedComboBanned(1,1)end))"))return 94;
 WriteWord(g_ModuleBytes,0xabd830,AddressOf(comboSets)+1);
 if(luaL_dostring(L,"assert(not pcall(function()seeds:IsSeedComboBanned(0,1)end))"))return 95;
}
if(scene=="crossbase"){
 std::vector<unsigned char>changed=g_ModuleBytes;const auto base=AddressOf(changed);
 changed[guard::kSeed2StringEntry]^=1;changed[guard::kSeedTreeDestroyEntry]^=1;changed[guard::kSeedComboLayoutEntry]^=1;
 LuaRuntime::SetEngineModuleBase(base);
 if(luaL_dostring(L,"for _,f in ipairs({function()seeds:GetStartSeedString()end,function()seeds:ClearSeedEffects()end,function()seeds:IsSeedComboBanned(1,7)end})do local ok,e=pcall(f);assert(not ok and string.find(e,'guard'),tostring(e))end"))return 96;
 assert(calls[10]==2&&releases==1&&calls[11]==2);
}
if(scene=="deadgame"){
 WriteWord(g_OwnerSlotBytes,0,0);
 if(luaL_dostring(L,"assert(not pcall(function()seeds:GetStartSeedString()end));assert(not pcall(function()seeds:ClearSeedEffects()end));assert(not pcall(function()seeds:IsSeedComboBanned(1,7)end))"))return 97;
}
lua_close(L);return 0;}
'''
point='const char*script=R"LUA('
prelude=r'''
 WriteAt<std::uint32_t>(g_GameBytes,kGameSeedsObjectOffset,0x87654321);WriteAt<std::uint32_t>(g_GameBytes,kGameSeedsObjectOffset+8,0x76543210);WriteAt<std::uint32_t>(g_GameBytes,kGameSeedsObjectOffset+0x10,0xfedcba98);
 std::vector<unsigned char>beforeTree(g_GameBytes.begin()+kGameSeedsObjectOffset,g_GameBytes.begin()+kGameSeedsObjectOffset+0x58);
 if(scene=="badguard"){g_ModuleBytes[guard::kSeed2StringEntry]^=1;g_ModuleBytes[guard::kSeedTreeDestroyEntry]^=1;g_ModuleBytes[guard::kSeedComboLayoutEntry]^=1;}
 if(scene=="allocator-missing"){LuaRuntime::LuaSpriteBindings missing{};LuaRuntime::SetSpriteBindings(missing);}
 '''
SEEDS_MAIN=SEEDS_MAIN.replace(point,prelude+point,1)
seed_cases=r'''
if(scene=="badguard")script=R"LUA(seeds=Game():GetSeeds();for _,f in ipairs({function()seeds:GetStartSeedString()end,function()seeds:ClearSeedEffects()end,function()seeds:IsSeedComboBanned(1,7)end})do local ok,e=pcall(f);assert(not ok and string.find(e,"guard"),tostring(e))end)LUA";
if(scene=="allocator-missing")script="local seeds=Game():GetSeeds();assert(not pcall(function()seeds:GetStartSeedString()end))";
if(scene=="oom"){
 if(luaL_dostring(L,"seeds=Game():GetSeeds()"))return 98;
 priorAllocator=lua_getallocf(L,&allocatorContext);lua_setallocf(L,FailAllocator,allocatorContext);
 // 仅在native返回长串之后让Lua分配失败；保护userdata必须先成功挂GC。
 script="local ok=pcall(function()seeds:GetStartSeedString()end);assert(not ok)";
}
'''
# 用flag在native callback之后开启失败，避免测试只失败于前置userdata分配。
SEEDS_MAIN=SEEDS_MAIN.replace('static bool failText{};', 'static bool failText{},armOom{};').replace('if(failText)failText=true;return v;', 'if(armOom)failText=true;return v;')
seed_cases=seed_cases.replace('script="local ok=pcall', 'armOom=true;script="local ok=pcall')
seed_cases=seed_cases.replace('priorAllocator=lua_getallocf(L,&allocatorContext);lua_setallocf(L,FailAllocator,allocatorContext);', 'lua_getglobal(L,"seeds");lua_getfield(L,-1,"GetStartSeedString");lua_pushvalue(L,-2);priorAllocator=lua_getallocf(L,&allocatorContext);lua_setallocf(L,FailAllocator,allocatorContext);')
seed_cases=seed_cases.replace('armOom=true;script="local ok=pcall(function()seeds:GetStartSeedString()end);assert(not ok)";', 'armOom=true;const auto status=lua_pcall(L,1,1,0);failText=false;lua_setallocf(L,priorAllocator,allocatorContext);assert(status==LUA_ERRMEM);lua_settop(L,0);lua_gc(L,LUA_GCCOLLECT,0);assert(calls[10]==1&&releases==1);lua_close(L);return 0;')

# Lua outer loadbuffer本身需先成功，之后callback才打开failText。
SEEDS_MAIN=SEEDS_MAIN.replace(')LUA";if(luaL_dostring(L,script))', ')LUA";'+seed_cases+'if(luaL_dostring(L,script))',1)

def _test_seeds(self):
    self._run("seeds",("normal","badguard","crossbase","malformed","deadgame","allocator-missing","oom"))
World35Boundaries.test_seed_tree_combo_string_allocator_guards_and_live_changes=_test_seeds
