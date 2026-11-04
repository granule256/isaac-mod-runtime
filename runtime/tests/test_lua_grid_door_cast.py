"""A grid cast to a door exposes door methods and fields used by collision callbacks."""
import subprocess
import tempfile
import unittest
from pathlib import Path

from .test_lua_grid_entity_cast_batch276 import HARNESS, SOURCE
from .test_support import build_lua_harness

MAIN = r'''
#include <cstdio>
int main() {
    PublishFakeRoom();
    LuaRuntime::SetGameBindings(AddressOf(g_OwnerSlotBytes),0x2222);
    g_EntityBytes.resize(0x400);
    WriteAt<std::uintptr_t>(g_EntityBytes,0,AddressOf(g_ModuleBytes)+kGridEntity_DoorVtableOffset);
    WriteAt<std::uint32_t>(g_EntityBytes,kGridEntityTypeOffset,16);
    WriteAt<std::int32_t>(g_EntityBytes,kGridEntityDoorSlotOffset,6);
    WriteAt<std::uint32_t>(g_EntityBytes,kGridEntityDoorTargetRoomTypeOffset,11);
    WriteAt<std::uintptr_t>(g_RoomBytes,kRoomGridEntityTableOffset+20*8,AddressOf(g_EntityBytes));
    const char* script=R"lua(
        local mod=RegisterMod('DoorCast',1)
        mod:AddCallback(ModCallbacks.MC_POST_UPDATE,function()end)
        local grid=Game():GetRoom():GetGridEntity(20)
        local door=grid:ToDoor()
        assert(door and not door:IsOpen())
        assert(door.TargetRoomType==11 and door:GetType()==16)
        assert(door:ToRock()==nil and type(door.Open)=='function')
    )lua";
    auto result=LuaRuntime::InitializeFromBuffer(script,std::strlen(script),"@door-cast.lua");
    if(result!=LuaRuntime::LuaInitResult::Success){
        char error[1024]{};(void)LuaRuntime::CopyLastLuaErrorText(error,sizeof(error));
        std::printf("%s\n",error);return 1;
    }
    WriteAt<std::uint32_t>(g_EntityBytes,kGridEntityDoorFlagsOffset,0x10);
    const char* opened="assert(Game():GetRoom():GetGridEntity(20):ToDoor():IsOpen())";
    return LuaRuntime::InitializeFromBuffer(opened,std::strlen(opened),"@opened.lua")==
        LuaRuntime::LuaInitResult::Success?0:2;
}
'''


class GridDoorCastTests(unittest.TestCase):
    def test_cast_door_supports_open_state_target_type_and_inherited_grid_methods(self):
        source = HARNESS[:HARNESS.index("int main(")] + MAIN
        with tempfile.TemporaryDirectory(prefix="isaac-door-cast-") as temporary:
            binary = build_lua_harness(source_root=SOURCE, workdir=Path(temporary),
                                       harness_source=source)
            result = subprocess.run([str(binary)], text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
