"""Immediate grid deletion, backdrop setup, and rails preserve native side effects."""
import subprocess
import tempfile
import unittest
from pathlib import Path
from . import test_support
from .test_repentogon_world_api import BEHAVIOR, SOURCE

EXTRA = r'''
static int removeCalls{},backdropCalls{};
static std::uint32_t backdropIds[4]{};
static std::vector<std::string> backdropStrings;
static std::vector<std::string> backdropPaths;
static void Remove(void* room,std::int32_t index,std::int32_t trail,bool keep){
 assert(room==g_RoomBytes.data());assert((index==4&&trail==-2&&keep)||(index==-1&&trail==0&&!keep));++removeCalls;
}
static void Backdrop(void* backdrop,std::uint32_t id,bool change){
 assert(backdrop==g_RoomBytes.data()+0x1fe0);assert(change);
 assert(backdropCalls<4);backdropIds[backdropCalls++]=id;
 std::memcpy(static_cast<unsigned char*>(backdrop)+0x1d0,&id,sizeof(id));
}
static void AssignBackdropString(void* object,const char* value){
 assert(object>=g_RoomBytes.data()+0x1fe0&&object<g_RoomBytes.data()+0x8000);
 backdropStrings.emplace_back(value);
}
static bool BackdropPathExists(const char* path){
 assert(path);backdropPaths.emplace_back(path);
 return std::strcmp(path,"gfx/backdrop/missing.anm2")!=0;
}
'''
SCRIPT = r'''
room:RemoveGridEntityImmediate(4,-2,true)
room:RemoveGridEntityImmediate(-1,0)
assert(not pcall(room.RemoveGridEntityImmediate,room,1,{}))
room:SetBackdropType(3,1)
assert(room:GetBackdropType()==3)
room:SetBackdropType(61,1)
assert(room:GetBackdropType()==61)
room:SetBackdropType(62,1)
assert(room:GetBackdropType()==62)
assert(not pcall(room.SetBackdropType,room,64,1))
assert(room:GetBackdropType()==62)
assert(not pcall(room.SetBackdropType,room,-1,1))
assert(not pcall(room.SetBackdropType,room,1,{}))
assert(not pcall(room.SetBackdropType,room,63,1))
assert(not pcall(room.GetBackdropType,room,1))
room:SetRail(0,5)
for _,rail in ipairs({0,6,10,16,17,32,33,80,85,96,101,112,113,144,145,160,161,255}) do
 room:SetRail(3,rail)
end
assert(not pcall(room.SetRail,room,-1,0))
assert(not pcall(room.SetRail,room,4,0))
for _,rail in ipairs({-1,11,15,18,34,79,86,95,102,114,143,146,159,162,254,256}) do
 assert(not pcall(room.SetRail,room,0,rail))
end
assert(not pcall(room.SetRail,room,0))
'''


class RoomMutationsTests(unittest.TestCase):
    def test_native_receivers_arguments_and_missing_owner(self):
        driver = ('#include <string>\n#include <vector>\n'
                  '#include "interfaces/lua/repentogon_room_mutations.hpp"\n'
                  '#include "program/xml_data_store.hpp"\n'
                  + BEHAVIOR.replace('int main() {', EXTRA + '\nint main() {'))
        driver = driver.replace('    PublishNativeState();', r'''
    PublishNativeState();
    const unsigned char removeGuard[]={0x3f,0xfc,0x06,0x71,0x08,0x01,0x00,0x54,0x09,0x4c,0x21,0x8b,0x28,0x0d,0x43,0xf8};
    const unsigned char backdropGuard[]={0xff,0x03,0x01,0xd1,0xfd,0x7b,0x01,0xa9,0xfd,0x43,0x00,0x91,0xf5,0x13,0x00,0xf9};
    std::memcpy(g_ModuleBytes.data()+0x4883c0,removeGuard,16);
    std::memcpy(g_ModuleBytes.data()+0x26e80,backdropGuard,16);
    WriteAt<std::int32_t>(g_RoomBytes,kRoomGridWidthOffset,2);
    WriteAt<std::int32_t>(g_RoomBytes,kRoomGridHeightOffset,2);
    const char backdropXml[] =
        "<backdrops gfxroot='gfx/backdrop/' gridgfxroot='gfx/grid/'>"
        "<backdrop id='61' reftype='1' gfx='mod.png' lfloorgfx='mod_l.png'"
        " nfloorgfx='mod_n.png' watergfx='mod_water.png' walls='7'"
        " wallvariants='8' floors='9' floorvariants='10' props='mod.anm2'"
        " rocks='mod_rocks.png' pit='mod_pit.png' waterpit='mod_waterpit.png'"
        " bridge='mod_bridge.png' door='mod_door.png' holeinwall='mod_hole.png'/>"
        "<backdrop id='62' reftype='18' gfx='valid.anm2' walls='11'/>"
        "<backdrop id='63' reftype='61' gfx='bad.png'/>"
        "<backdrop id='64' reftype='18' gfx='missing.anm2'/>"
        "</backdrops>";
    isaac::runtime::xml_data::ResetXmlDataStore();
    assert(isaac::runtime::xml_data::IngestXmlDataFile(
        isaac::runtime::xml_data::XmlDataFileKind::Backdrops,"BaseGame",false,
        backdropXml,std::strlen(backdropXml)));
    isaac::runtime::SetRepentogonRoomMutationNativeTestBindings(
        {Remove,Backdrop,AssignBackdropString,BackdropPathExists});
    isaac::runtime::SetRepentogonBackdropInitFallback(Backdrop);
''')
        driver = driver.replace('        lua_pop(lua, 2);', r'''
        lua_pushcfunction(lua,isaac::runtime::RepentogonRoomRemoveGridEntityImmediate);
        lua_setfield(lua,-2,"RemoveGridEntityImmediate");
        lua_pushcfunction(lua,isaac::runtime::RepentogonRoomSetBackdropType);
        lua_setfield(lua,-2,"SetBackdropType");
        lua_pushcfunction(lua,isaac::runtime::RepentogonRoomGetBackdropType);
        lua_setfield(lua,-2,"GetBackdropType");
        lua_pushcfunction(lua,isaac::runtime::RepentogonRoomSetRail);
        lua_setfield(lua,-2,"SetRail");
        lua_pop(lua, 2);
''')
        driver = driver.replace('_installRoomMethods(room)', '_installRoomMethods(room)\n' + SCRIPT)
        driver = driver.replace(
            'if (result == LuaRuntime::LuaInitResult::Success) return 0;',
            'if (result == LuaRuntime::LuaInitResult::Success) {'
            'assert(removeCalls==2&&backdropCalls==3);'
            'assert(backdropIds[0]==3&&backdropIds[1]==1&&backdropIds[2]==18);'
            'assert(backdropStrings.size()==22);'
            'assert(std::strcmp(backdropStrings[0].c_str(),"gfx/backdrop/mod.png")==0);'
            'assert(std::strcmp(backdropStrings[1].c_str(),"gfx/backdrop/mod_l.png")==0);'
            'assert(std::strcmp(backdropStrings[2].c_str(),"gfx/backdrop/mod_n.png")==0);'
            'assert(std::strcmp(backdropStrings[3].c_str(),"gfx/backdrop/mod_water.png")==0);'
            'assert(std::strcmp(backdropStrings[4].c_str(),"gfx/grid/mod.anm2")==0);'
            'assert(std::strcmp(backdropStrings[5].c_str(),"gfx/grid/mod_rocks.png")==0);'
            'assert(std::strcmp(backdropStrings[6].c_str(),"gfx/grid/mod_pit.png")==0);'
            'assert(std::strcmp(backdropStrings[7].c_str(),"gfx/grid/mod_waterpit.png")==0);'
            'assert(std::strcmp(backdropStrings[8].c_str(),"gfx/grid/mod_bridge.png")==0);'
            'assert(std::strcmp(backdropStrings[9].c_str(),"gfx/grid/mod_door.png")==0);'
            'assert(std::strcmp(backdropStrings[10].c_str(),"gfx/grid/mod_hole.png")==0);'
            'assert(std::strcmp(backdropStrings[11].c_str(),"gfx/backdrop/valid.anm2")==0);'
            'assert(backdropPaths.size()==2);'
            'assert(backdropPaths[0]=="gfx/backdrop/valid.anm2");'
            'assert(backdropPaths[1]=="gfx/backdrop/missing.anm2");'
            'const auto* config=g_RoomBytes.data()+0x1fe0+0x1d8+0x148;'
            'int walls{},wallVariants{},floors{},floorVariants{};'
            'std::memcpy(&walls,config+0x68,4);std::memcpy(&wallVariants,config+0x6c,4);'
            'std::memcpy(&floors,config+0x70,4);std::memcpy(&floorVariants,config+0x74,4);'
            'assert(walls==7&&wallVariants==8&&floors==9&&floorVariants==10);'
            'assert(g_RoomBytes[0x7c80]==5&&g_RoomBytes[0x7c83]==255);'
            'isaac::runtime::SetRepentogonBackdropInitFallback(nullptr);'
            'isaac::runtime::xml_data::ResetXmlDataStore();return 0;}')
        with tempfile.TemporaryDirectory(prefix='room-mutations-') as folder:
            extra = SOURCE.parent / 'src/interfaces/lua/repentogon_room_mutations.cpp'
            added = () if extra in test_support.layered_lua_runtime_sources(SOURCE) else (extra,)
            binary = test_support.build_lua_harness(source_root=SOURCE,workdir=Path(folder),
                                                    harness_source=driver,extra_sources=added)
            result = subprocess.run([str(binary)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)

    def test_installed_backdrop_fallback_rechecks_the_original_guard(self):
        source = (
            SOURCE.parent / "src" / "interfaces" / "lua" / "repentogon_room_mutations.cpp"
        ).read_text(encoding="utf-8")
        self.assertIn("g_BackdropFallbackVerifiedBase", source)
        self.assertIn("engine_call::VerifyEntryBytes(base+0x26e80", source)
        self.assertIn("kBackdropGuard,sizeof(kBackdropGuard)", source)
        self.assertLess(
            source.index("engine_call::VerifyEntryBytes(base+0x26e80"),
            source.index("ApplyRepentogonBackdropInit(engine_memory::AsObject(room+offset)"),
        )
