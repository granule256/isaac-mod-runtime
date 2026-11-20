"""Targeted host coverage for SetPocketActiveItem's deferred ItemPool removal."""

import re
import subprocess
import tempfile
import unittest
from pathlib import Path

from . import test_lua_entity_query as fixture
from .test_support import build_lua_harness


ROOT = Path(__file__).resolve().parents[2]


MAIN = r'''
#include "interfaces/lua/rplus_methods_api.hpp"
#include "interfaces/lua/isaac_api.hpp"
#include "infrastructure/call/engine_call_access.hpp"

#include <cassert>
#include <cstdio>
#include <cstring>
#include <vector>

void* testItemPool{};
static void* expectedPlayer{};
static std::int32_t expectedId{};
static bool expectedKeep{};
static unsigned poolRemovalCalls{};
static std::int32_t removedId{};

static void SetPocketActiveItem(void* player,std::int32_t id,
                                std::uint32_t slot,bool keepInPools)noexcept {
    assert(player==expectedPlayer);
    assert(id==expectedId);
    assert(slot==2);
    assert(keepInPools==expectedKeep);
}

static bool RemoveCollectible(void*,std::int32_t id,bool validate,bool dryRun)noexcept {
    ++poolRemovalCalls;
    removedId=id;
    assert(id==expectedId&&!validate&&!dryRun);
    return true;
}

int main(int argc,char** argv) {
    static_cast<void>(kScriptTemplate);
    static_cast<void>(&HarnessHasCollectible);
    static_cast<void>(&BuildPrelude);
    static_cast<void>(&ExpectNumber);
    if(argc!=2)return 99;
    const std::string scene=argv[1];
    CreateBlocks();
    FillEntities();
    PublishLists();
    PublishGame();
    PublishEntityList(g_RoomBytes,true);
    expectedPlayer=g_Entities[kPlayer].data();

    std::vector<unsigned char> itemPool(0x910);
    std::vector<std::uint64_t> removedBits(16);
    testItemPool=itemPool.data();
    const std::size_t removedCount=1024;
    const std::size_t removedCapacity=removedBits.size();
    const std::uintptr_t removedBitsAddress=
        reinterpret_cast<std::uintptr_t>(removedBits.data());
    std::memcpy(itemPool.data()+0x8f8,&removedCount,sizeof(removedCount));
    std::memcpy(itemPool.data()+0x900,&removedCapacity,sizeof(removedCapacity));
    if(scene!="deferred"&&scene!="reset")
        std::memcpy(itemPool.data()+0x8f0,&removedBitsAddress,sizeof(removedBitsAddress));

    LuaRuntime::SetEngineModuleBase(g_EngineBase);
    LuaRuntime::SetGameBindings(AddressOf(g_OwnerSlotBytes),0x2222);

    isaac::runtime::RPlusMethodsNativeTestBindings native{};
    native.methods[static_cast<unsigned>(
        isaac::runtime::RPlusMethodsNative::SetPocketActiveItem)]=
        isaac::runtime::engine_call::AddressOfFunction(&SetPocketActiveItem);
    native.itemPoolRemoveCollectible=&RemoveCollectible;
    isaac::runtime::SetRPlusMethodsNativeTestBindings(native);

    std::string pocketCall;
    if(scene=="keep") {
        expectedId=1023;expectedKeep=true;
        pocketCall="player:SetPocketActiveItem(1023,2,true)";
    } else if(scene=="zero") {
        expectedId=0;expectedKeep=false;
        pocketCall="player:SetPocketActiveItem(0,false)";
    } else if(scene=="negative") {
        expectedId=-1;expectedKeep=true;
        pocketCall="player:SetPocketActiveItem(-1,false)";
    } else if(scene=="out_of_range") {
        expectedId=2048;expectedKeep=true;
        pocketCall="player:SetPocketActiveItem(2048,false)";
    } else {
        expectedId=1023;expectedKeep=scene=="deferred"||scene=="reset";
        pocketCall="player:SetPocketActiveItem(1023,false)";
    }

    std::string script=R"lua(
local mod=RegisterMod('pocket-active-pool-removal',1)
mod:AddCallback(ModCallbacks.MC_POST_UPDATE,function()
    local player=Isaac.GetPlayer()
    PLAYER_POCKET_CALL
end)
)lua";
    script.replace(script.find("PLAYER_POCKET_CALL"),18,pocketCall);
    if(LuaRuntime::InitializeFromBuffer(script.data(),script.size(),
            "@pocket-active-pool-removal.lua")!=LuaRuntime::LuaInitResult::Success)
        return 1;
    LuaRuntime::DispatchPostUpdate();
    if(LuaRuntime::TakeCallbackError())return 2;

    if(scene=="deferred"||scene=="reset") {
        if(poolRemovalCalls!=0||
           isaac::runtime::RPlusFlushDeferredPocketActivePoolRemovals())return 3;
        if(scene=="reset")
            isaac::runtime::RPlusResetDeferredPocketActivePoolRemovals();
        std::memcpy(itemPool.data()+0x8f0,&removedBitsAddress,sizeof(removedBitsAddress));
        if(!isaac::runtime::RPlusFlushDeferredPocketActivePoolRemovals())return 4;
        if(scene=="reset"&&poolRemovalCalls!=0)return 5;
        if(scene=="deferred"&&(poolRemovalCalls!=1||removedId!=1023))return 6;
    } else {
        if(!isaac::runtime::RPlusFlushDeferredPocketActivePoolRemovals()||
           poolRemovalCalls!=0)return 7;
    }
    return 0;
}
'''


class RPlusPocketActivePoolRemovalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="rplus-pocket-pool-")
        source = fixture.HARNESS[:fixture.HARNESS.index("int main(")] + MAIN
        source = source.replace(
            "GameItemPoolObservation ReadCurrentGameItemPool(uintptr_t, void**) {\n"
            "    return GameItemPoolObservation::GameUnreadable;\n"
            "}",
            r"""extern void* testItemPool;
GameItemPoolObservation ReadCurrentGameItemPool(uintptr_t,void** pool) {
    if(!pool)return GameItemPoolObservation::ItemPoolUnreadable;
    *pool=testItemPool;
    return testItemPool?GameItemPoolObservation::Success:
        GameItemPoolObservation::GameUnreadable;
}""",
        )
        source = re.sub(
            r"namespace GameFileReader \{\nTextReadResult[\s\S]*?\n\}\n\}",
            "",
            source,
            count=1,
        )
        cls.binary = build_lua_harness(
            source_root=fixture.SOURCE,
            workdir=Path(cls.tmp.name),
            harness_source=source,
        )

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_deferred_removal_only_when_bitset_is_unavailable(self):
        for scene in (
            "normal",
            "deferred",
            "reset",
            "keep",
            "zero",
            "negative",
            "out_of_range",
        ):
            with self.subTest(scene=scene):
                result = subprocess.run(
                    [str(self.binary), scene], capture_output=True, text=True
                )
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_flush_precedes_post_game_started_dispatch(self):
        runtime = (ROOT / "runtime/source/lua_runtime.cpp").read_text()
        started = runtime.index("bool DispatchPostGameStarted(bool isSave) {")
        section = runtime[started : runtime.index("\n}", started)]
        self.assertLess(
            section.index("RPlusFlushDeferredPocketActivePoolRemovals"),
            section.index("CallbackDispatcher"),
        )
        self.assertIn("RPlusResetDeferredPocketActivePoolRemovals", runtime)


if __name__ == "__main__":
    unittest.main()
