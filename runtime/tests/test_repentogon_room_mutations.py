"""Immediate grid deletion and backdrop setup preserve native side effects and arguments."""
import subprocess
import tempfile
import unittest
from pathlib import Path
from . import test_support
from .test_repentogon_world_api import BEHAVIOR, SOURCE

EXTRA = r'''
static int removeCalls{},backdropCalls{};
static void Remove(void* room,std::int32_t index,std::int32_t trail,bool keep){
 assert(room==g_RoomBytes.data());assert((index==4&&trail==-2&&keep)||(index==-1&&trail==0&&!keep));++removeCalls;
}
static void Backdrop(void* backdrop,std::uint32_t id,bool change){
 assert(backdrop==g_RoomBytes.data()+0x1fe0);assert(id==3&&change);++backdropCalls;
}
'''
SCRIPT = r'''
room:RemoveGridEntityImmediate(4,-2,true)
room:RemoveGridEntityImmediate(-1,0)
assert(not pcall(room.RemoveGridEntityImmediate,room,1,{}))
room:SetBackdropType(3,1)
assert(not pcall(room.SetBackdropType,room,-1,1))
assert(not pcall(room.SetBackdropType,room,1,{}))
assert(not pcall(room.SetBackdropType,room,61,1))
room:SetRail(0,5)
room:SetRail(3,15)
assert(not pcall(room.SetRail,room,-1,0))
assert(not pcall(room.SetRail,room,4,0))
assert(not pcall(room.SetRail,room,0,16))
assert(not pcall(room.SetRail,room,0))
'''


class RoomMutationsTests(unittest.TestCase):
    def test_native_receivers_arguments_and_missing_owner(self):
        driver = '#include "interfaces/lua/repentogon_room_mutations.hpp"\n' + BEHAVIOR.replace('int main() {', EXTRA + '\nint main() {')
        driver = driver.replace('    PublishNativeState();', r'''
    PublishNativeState();
    const unsigned char removeGuard[]={0x3f,0xfc,0x06,0x71,0x08,0x01,0x00,0x54,0x09,0x4c,0x21,0x8b,0x28,0x0d,0x43,0xf8};
    const unsigned char backdropGuard[]={0xff,0x03,0x01,0xd1,0xfd,0x7b,0x01,0xa9,0xfd,0x43,0x00,0x91,0xf5,0x13,0x00,0xf9};
    std::memcpy(g_ModuleBytes.data()+0x4883c0,removeGuard,16);
    std::memcpy(g_ModuleBytes.data()+0x26e80,backdropGuard,16);
    WriteAt<std::int32_t>(g_RoomBytes,kRoomGridWidthOffset,2);
    WriteAt<std::int32_t>(g_RoomBytes,kRoomGridHeightOffset,2);
    isaac::runtime::SetRepentogonRoomMutationNativeTestBindings({Remove,Backdrop});
''')
        driver = driver.replace('        lua_pop(lua, 2);', r'''
        lua_pushcfunction(lua,isaac::runtime::RepentogonRoomRemoveGridEntityImmediate);
        lua_setfield(lua,-2,"RemoveGridEntityImmediate");
        lua_pushcfunction(lua,isaac::runtime::RepentogonRoomSetBackdropType);
        lua_setfield(lua,-2,"SetBackdropType");
        lua_pushcfunction(lua,isaac::runtime::RepentogonRoomSetRail);
        lua_setfield(lua,-2,"SetRail");
        lua_pop(lua, 2);
''')
        driver = driver.replace('_installRoomMethods(room)', '_installRoomMethods(room)\n' + SCRIPT)
        driver = driver.replace('if (result == LuaRuntime::LuaInitResult::Success) return 0;',
                                'if (result == LuaRuntime::LuaInitResult::Success) {assert(removeCalls==2&&backdropCalls==1);assert(g_RoomBytes[0x7c80]==5&&g_RoomBytes[0x7c83]==15);return 0;}')
        with tempfile.TemporaryDirectory(prefix='room-mutations-') as folder:
            extra = SOURCE.parent / 'src/interfaces/lua/repentogon_room_mutations.cpp'
            added = () if extra in test_support.layered_lua_runtime_sources(SOURCE) else (extra,)
            binary = test_support.build_lua_harness(source_root=SOURCE,workdir=Path(folder),
                                                    harness_source=driver,extra_sources=added)
            result = subprocess.run([str(binary)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
