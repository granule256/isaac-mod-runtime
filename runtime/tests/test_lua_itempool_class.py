"""ItemPool exposes the class metadata used by mods to wrap its methods."""
import subprocess
import tempfile
import unittest
from pathlib import Path

from .test_support import build_lua_harness

SOURCE = Path(__file__).resolve().parents[1] / "source"
HARNESS = r'''
#include "lua_runtime.hpp"
#include <cstdio>
#include <cstring>
int main() {
    const char* script=R"lua(
        local pool=Game():GetItemPool()
        local class=getmetatable(ItemPool).__class
        assert(class==getmetatable(pool) and class.__type=='ItemPool')
        local original=class.RemoveCollectible
        assert(type(original)=='function' and pool.RemoveCollectible==original)
        local oldIndex=class.__index
        assert(type(oldIndex)=='function')
        local calls=0
        local replacement=function(self,id)
            assert(self==pool and id==37)
            calls=calls+1
            return 73
        end
        rawset(class,'__index',function(self,key)
            if key=='RemoveCollectible' then return replacement end
            return oldIndex(self,key)
        end)
        assert(pool:RemoveCollectible(37)==73 and calls==1)
        assert(type(pool.GetCard)=='function' and pool.Unknown==nil)
        assert(class.RemoveCollectible==original)
        local mod=RegisterMod('ClassConsumer',1)
        mod:AddCallback(ModCallbacks.MC_POST_UPDATE,function()end)
    )lua";
    const auto result=LuaRuntime::InitializeFromBuffer(script,std::strlen(script),"@class.lua");
    char error[1024]{};
    (void)LuaRuntime::CopyLastLuaErrorText(error,sizeof(error));
    std::printf("status=%u error=%s\n",unsigned(result),error);
    return result==LuaRuntime::LuaInitResult::Success?0:1;
}
'''


class LuaItemPoolClassTests(unittest.TestCase):
    def test_mod_can_save_and_wrap_the_original_itempool_method(self):
        with tempfile.TemporaryDirectory(prefix="isaac-itempool-class-") as temporary:
            binary = build_lua_harness(source_root=SOURCE, workdir=Path(temporary),
                                       harness_source=HARNESS)
            result = subprocess.run([str(binary)], text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
