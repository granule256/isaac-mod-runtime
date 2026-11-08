"""FF 2.8.8's actual helper versus the opt-in, mod-owned type index."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from runtime.tests.test_support import lua_harness_objects


PUBLIC = Path(__file__).resolve().parents[1]
ADAPTER = PUBLIC / "mods/isaac_performance_helpers/scripts/fiend_folio.lua"
REFERENCE = os.environ.get("ISAAC_FF_REFERENCE_MAIN")
ORIGINAL = Path(REFERENCE) if REFERENCE else None
DRIVER = r'''
extern "C" {
#include "lua.h"
#include "lauxlib.h"
#include "lualib.h"
}
#include <cstdio>
int ProxyIndex(lua_State* L){lua_getuservalue(L,1);lua_pushvalue(L,2);lua_gettable(L,-2);return 1;}
int ProxyNewIndex(lua_State* L){lua_getuservalue(L,1);lua_pushvalue(L,2);lua_pushvalue(L,3);lua_settable(L,-3);return 0;}
int ProxyMod(lua_State* L){
 lua_newuserdata(L,1);lua_pushvalue(L,1);lua_setuservalue(L,-2);lua_newtable(L);
 lua_pushcfunction(L,ProxyIndex);lua_setfield(L,-2,"__index");
 lua_pushcfunction(L,ProxyNewIndex);lua_setfield(L,-2,"__newindex");lua_setmetatable(L,-2);return 1;
}
int main(int argc, char** argv) {
 auto* L=luaL_newstate();
 luaL_requiref(L,"_G",luaopen_base,1);lua_pop(L,1);
 luaL_requiref(L,"table",luaopen_table,1);lua_pop(L,1);
 luaL_requiref(L,"math",luaopen_math,1);lua_pop(L,1);
 lua_pushcfunction(L,ProxyMod);lua_setglobal(L,"proxy_mod");
 const int result=argc!=2 || luaL_dofile(L,argv[1]);
 if(result) std::fprintf(stderr,"%s\n",lua_tostring(L,-1));
 lua_close(L); return result;
}
'''

SETUP = r'''
local makeOriginal = dofile(ORIGINAL_PATH)
local names = {'creepSpawnerCount','countFlies','fireEntities',
               'fireEntitiesFriend','playerPositions','playerVelocities','RoomEntitiesCache'}
local function world(proxy)
 local counts, room, challenge, fallbackCalls = {}, {}, 0, 0
 local function hit(key) counts[key]=(counts[key] or 0)+1 end
 local ff = {
  modVersionNumber='2.8.8', FF={Snagger={ID=999}}, challenges={dirtyBubble=77},
  creepLeavingEnemies={{32,0},{32,0},{40,1}},
  customFlies={{13},{13,0},{14,2},{15},{16},{17},{18}},
  fireTypes={{33},{13,0},{13,0,2},{1000,51,1},{1000,1}},
  specialFireTypes={{13,0},{13},{40,1}},
  playerFireTypes={{13},{13,0},{13,0,2},{1000,51}},
 }
 if proxy then ff=proxy_mod(ff) end
 FiendFolio=ff
 Isaac={GetRoomEntities=function()
  hit('GetRoomEntities'); local fresh={}; for i,e in ipairs(room) do fresh[i]=e end; return fresh
 end, GetChallenge=function() hit('GetChallenge'); return challenge end}
 ff.ShootBubble=function(...) hit('ShootBubble') end
 local function entity(id,t,v,s,dead,flaming)
  return {id=id,Type=t,Variant=v or 0,SubType=s or 0,HitPoints=2,
   Velocity={id=id..':velocity'},
   IsDead=function() hit('IsDead'); hit('dead:'..id); return dead or false end,
   GetData=function() hit('GetData'); return {flaming=flaming} end,
   IsEnemy=function() hit('IsEnemy'); return false end,
   ToPlayer=function(self) hit('ToPlayer'); return self end,
  }
 end
 local real=makeOriginal(ff)
 local function original(...) fallbackCalls=fallbackCalls+1; return real(...) end
 ff.GetRoomEntities=original
 return {ff=ff,room=room,entity=entity,original=original,
  counts=function()return counts end,reset=function()counts={};fallbackCalls=0 end,
  fallbacks=function()return fallbackCalls end,challenge=function(c)challenge=c end}
end
local function compare(w)
 w.reset(); w.original()
 local before, baseline = {}, w.counts()
 for _,name in ipairs(names)do before[name]=w.ff[name] end
 local delirium=w.ff.IsDeliriumRoom
 w.reset(); w.ff.GetRoomEntities()
 for _,name in ipairs(names)do
  local old,now=before[name],w.ff[name]
  assert(old~=now,'must return fresh '..name)
  assert(#old==#now,'length '..name..': '..#old..' ~= '..#now)
  for i=1,#old do assert(old[i]==now[i],name..' order/duplicates at '..i)end
 end
 assert(w.ff.IsDeliriumRoom==delirium,'sticky delirium flag')
 return baseline,w.counts()
end
-- Ordinary classification must neither consume RNG nor mutate entities.
math.random=function()error('unexpected RNG')end
RandomVector=function()error('unexpected RandomVector')end
'''


class PerformanceHelperTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if ORIGINAL is None or not ORIGINAL.is_file():
            raise unittest.SkipTest("Set ISAAC_FF_REFERENCE_MAIN to a Fiend Folio 2.8.8 main.lua")
        cls.temp = tempfile.TemporaryDirectory(prefix="ff-performance-")
        cls.addClassCleanup(cls.temp.cleanup)
        cls.directory = Path(cls.temp.name)
        text = ORIGINAL.read_text(encoding="utf-8")
        function = text.split("function mod.GetRoomEntities()", 1)[1].split(
            "\nfunction mod.PlayFlySound()", 1
        )[0]
        cls.fixture = cls.directory / "original.lua"
        cls.fixture.write_text(
            "return function(mod)\nfunction mod.GetRoomEntities()" + function
            + "\nreturn mod.GetRoomEntities\nend\n", encoding="utf-8"
        )
        source = PUBLIC / "runtime/source"
        cpp = cls.directory / "runner.cpp"
        cpp.write_text(DRIVER, encoding="utf-8")
        cls.runner = cls.directory / "lua"
        result = subprocess.run([
            "c++", "-std=c++17", "-I" + str(source / "third_party/lua-5.3.3/src"),
            str(cpp), *map(str, lua_harness_objects(source, cls.directory)),
            "-o", str(cls.runner),
        ], capture_output=True, text=True)
        if result.returncode:
            raise AssertionError(result.stdout + result.stderr)

    def run_lua(self, checks, *, adapter=True):
        if adapter:
            self.assertTrue(ADAPTER.is_file(), "FF performance adapter is not implemented")
        script = self.directory / (self._testMethodName + ".lua")
        script.write_text(
            "ORIGINAL_PATH=" + json.dumps(str(self.fixture)) + "\n"
            + ("local Adapter=dofile(" + json.dumps(str(ADAPTER)) + ")\n" if adapter else "")
            + SETUP + checks, encoding="utf-8"
        )
        result = subprocess.run([str(self.runner), str(script)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result.stdout

    def test_reference_helper_calls_isdead_for_each_rain_particle_and_fly_rule(self):
        self.run_lua(r'''
local w=world();for i=1,80 do w.room[i]=w.entity('rain'..i,1000,135)end
w.original();assert(w.counts().IsDead==80*#w.ff.customFlies)
assert(w.ff.creepSpawnerCount[1]==0 and #w.ff.creepSpawnerCount==1)
''', adapter=False)

    def test_plain_classification_duplicates_order_vectors_and_native_budget(self):
        self.run_lua(r'''
local w=world()
for _,e in ipairs({w.entity('p',1),w.entity('creep',32),w.entity('fly',13,0,2,false,true),
 w.entity('dead',13,0,2,true,true),w.entity('fire',33),w.entity('special',40,1,0,false,true),
 w.entity('boss',412),w.entity('effect',1000,51,1)})do w.room[#w.room+1]=e end
local p=Adapter.attach(w.ff);assert(p and p.status().enabled)
local old,new=compare(w);assert(w.fallbacks()==0)
assert(new.IsDead<old.IsDead);assert(new.GetData==old.GetData)
assert(new.GetRoomEntities==1 and new.GetChallenge==1)
assert(w.ff.creepSpawnerCount[1]==0 and #w.ff.creepSpawnerCount==4)
assert(#w.ff.countFlies==2 and #w.ff.fireEntitiesFriend==7)
local pos,vel=w.ff.playerPositions[1],w.ff.playerVelocities[1]
assert(pos==w.room[1] and vel==w.room[1].Velocity)
table.remove(w.room,7);w.ff.GetRoomEntities();assert(w.ff.IsDeliriumRoom==true)
''')

    def test_rain_avoids_all_custom_fly_death_checks_and_does_not_cache_entities(self):
        output = self.run_lua(r'''
local w=world();for i=1,80 do w.room[i]=w.entity('rain'..i,1000,135)end
Adapter.attach(w.ff);local old,new=compare(w)
assert(old.IsDead==560 and (new.IsDead or 0)==0 and w.fallbacks()==0)
print('rain entities=80 original IsDead='..old.IsDead..' optimized IsDead='..(new.IsDead or 0))
w.room[1]=w.entity('new-fly',13);w.reset();w.ff.GetRoomEntities()
assert(w.ff.countFlies[1]==w.room[1] and #w.ff.countFlies==2)
assert(w.counts().GetRoomEntities==1)
''')
        self.assertIn("original IsDead=560 optimized IsDead=0", output)

    def test_native_rain_skips_unused_subtype_reads_but_keeps_the_full_room_list(self):
        output = self.run_lua(r'''
local w=world();local reads=0
for i=1,80 do
 local e=w.entity('rain'..i,1000,135);e.SubType=nil
 setmetatable(e,{__index=function(_,key)if key=='SubType'then reads=reads+1;return 0 end end})
 w.room[i]=e
end
w.original();local originalReads=reads;assert(originalReads==80)
Adapter.attach(w.ff);reads=0;w.reset();w.ff.GetRoomEntities()
assert(reads==0,'unclassified rain still reads SubType '..reads..' times')
assert((w.counts().IsDead or 0)==0 and (w.counts().GetData or 0)==0)
assert(#w.ff.RoomEntitiesCache==80 and w.ff.RoomEntitiesCache[80]==w.room[80])
assert(w.ff.creepSpawnerCount[1]==0 and #w.ff.creepSpawnerCount==1)
assert(#w.ff.countFlies==0 and #w.ff.fireEntities==0 and #w.ff.fireEntitiesFriend==0)
print('native rain=80 original SubType='..originalReads..' optimized SubType='..reads)
''')
        self.assertIn('original SubType=80 optimized SubType=0',output)

    def test_rain_rule_addition_edit_and_removal_disable_and_restore_the_shortcut(self):
        self.run_lua(r'''
local w=world();local reads=0
local rain=w.entity('rain',1000,135,0,false,true);rain.SubType=nil
setmetatable(rain,{__index=function(_,key)if key=='SubType'then reads=reads+1;return 0 end end})
w.room[1]=rain;Adapter.attach(w.ff)
for _,name in ipairs({'creepLeavingEnemies','customFlies','fireTypes','specialFireTypes','playerFireTypes'})do
 local list=w.ff[name];list[#list+1]={1000,135};compare(w)
 reads=0;w.ff.GetRoomEntities();assert(reads>0,'rain rule was ignored: '..name)
 list[#list][2]=136;compare(w)
 reads=0;w.ff.GetRoomEntities();assert(reads==0,'rain rule edit not observed: '..name)
 list[#list][2]=135;table.remove(list);compare(w)
 reads=0;w.ff.GetRoomEntities();assert(reads==0,'rain rule removal not observed: '..name)
end
for _,name in ipairs({'customFlies','fireTypes','specialFireTypes','playerFireTypes'})do
 local list=w.ff[name];list[#list+1]={1000};compare(w)
 reads=0;w.ff.GetRoomEntities();assert(reads>0,'type wildcard rain rule ignored: '..name)
 table.remove(list)
end
''')

    def test_rules_add_remove_replace_and_edit_are_visible_on_next_call(self):
        self.run_lua(r'''
local w=world();w.room[1]=w.entity('fly',13,0,2,false,true)
Adapter.attach(w.ff);compare(w)
for _,name in ipairs({'creepLeavingEnemies','customFlies','fireTypes','specialFireTypes','playerFireTypes'})do
 local list=w.ff[name]
 list[#list+1]={13,0,2};compare(w)
 list[#list]={14,0,2};compare(w)
 list[#list][1]=13;compare(w)
 list[#list][2]=1;compare(w)
 list[#list][2]=0;list[#list][3]=3;compare(w)
 list[#list][3]=2;compare(w)
 table.remove(list,1);compare(w)
 local replacement={};for i,row in ipairs(list)do replacement[i]=row end
 w.ff[name]=replacement;compare(w)
 w.ff[name]={};compare(w)
end
''')

    def test_optional_false_and_zero_fields_match_original_lua_truthiness(self):
        self.run_lua(r'''
local w=world();w.room[1]=w.entity('zero',13,0,0,false,true)
for _,name in ipairs({'creepLeavingEnemies','customFlies','fireTypes','specialFireTypes','playerFireTypes'})do
 w.ff[name]={{13},{13,false},{13,0},{13,0,0},{13,false,0},{13,0,false}}
end
Adapter.attach(w.ff);compare(w);assert(w.fallbacks()==0)
''')

    def test_indexable_userdata_mod_reference_is_supported(self):
        self.run_lua(r'''
local w=world(true);assert(type(w.ff)=='userdata')
w.room[1]=w.entity('fly',13,0,2,false,true)
local p=Adapter.attach(w.ff);assert(p and p.status().enabled)
compare(w);assert(w.fallbacks()==0)
p.disable();assert(w.ff.GetRoomEntities==w.original)
''')

    def test_special_modes_and_version_change_delegate_to_original(self):
        self.run_lua(r'''
local w=world();w.room[1]=w.entity('player',1);w.room[2]=w.entity('rain',1000,9000)
local p=Adapter.attach(w.ff)
local function fallback()compare(w);assert(w.fallbacks()==1)end
w.ff.FiendishEffects={};fallback();w.ff.FiendishEffects=nil
w.ff.FlickerspiritInRoom=true;fallback();w.ff.FlickerspiritInRoom=nil
local savedPrint=print;print=function()end
w.ff.PrintEnts=true;fallback();w.ff.PrintEnts=nil;print=savedPrint
w.challenge(77);fallback();w.challenge(0)
w.ff.modVersionNumber='2.8.9';fallback()
p.disable();local original=w.ff.GetRoomEntities
local unsupported=Adapter.attach(w.ff);assert(w.ff.GetRoomEntities==original)
assert(not unsupported.status().enabled)
''')

    def test_metatables_sparse_and_malformed_rules_fall_back_without_swallowing_errors(self):
        self.run_lua(r'''
local w=world();w.room[1]=w.entity('fly',13)
Adapter.attach(w.ff)
setmetatable(w.ff.customFlies,{});compare(w);assert(w.fallbacks()==1)
setmetatable(w.ff.customFlies,nil)
setmetatable(w.ff.customFlies[1],{});compare(w);assert(w.fallbacks()==1)
setmetatable(w.ff.customFlies[1],nil)
w.ff.customFlies={[1]={13},[3]={13}};compare(w);assert(w.fallbacks()==1)
w.ff.customFlies={{13,0,0,'unexpected'}};compare(w);assert(w.fallbacks()==1)
w.ff.customFlies={{'13'}};compare(w);assert(w.fallbacks()==1)
local marker={};w.ff.customFlies=setmetatable({}, {__index=function()error(marker)end})
local ok,err=pcall(w.ff.GetRoomEntities);assert(not ok and err==marker)
''')

    def test_disable_enable_and_other_wrappers_are_preserved(self):
        self.run_lua(r'''
local w=world();w.room[1]=w.entity('rain',1000,9000)
local p=Adapter.attach(w.ff);local wrapper=w.ff.GetRoomEntities
assert(Adapter.attach(w.ff)==p)
p:disable();assert(w.ff.GetRoomEntities==w.original and not p:status().enabled)
w.reset();w.ff.GetRoomEntities();assert(w.fallbacks()==1)
assert(p:enable());assert(w.ff.GetRoomEntities==wrapper);compare(w);assert(w.fallbacks()==0)
local replacement=function()return 'another mod' end;w.ff.GetRoomEntities=replacement
p.disable();assert(w.ff.GetRoomEntities==replacement)
assert(not p.enable() and w.ff.GetRoomEntities==replacement)
local marker={};w.ff.GetRoomEntities=w.original;w.ff.FiendishEffects={}
w.ff.customFlies=setmetatable({}, {__index=function()error(marker)end})
assert(p.enable());local ok,err=pcall(w.ff.GetRoomEntities);assert(not ok and err==marker)
''')


if __name__ == "__main__":
    unittest.main()
