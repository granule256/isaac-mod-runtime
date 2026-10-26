"""Room:GetEnemyDamageInflicted 的真实原生求和字段读取合约。

仅验证读取现有引擎统计，不修改伤害累计算法或回调。
"""
import hashlib
import json
import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path
from . import test_lua_entity_query as fixture
from . import test_support
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'dist/api-remaining-recovery-20261025'
MAIN=r'''
#include <cassert>
#include <cstdio>
#include <cstring>
using namespace isaac::runtime;
static void CheckUnchanged(unsigned expected){
 const auto room=g_RoomBytes;const auto game=g_GameBytes;const auto entities=g_Entities;const auto owner=g_OwnerSlotBytes;const auto module=g_ModuleBytes;
 LuaRuntime::DispatchPostUpdate();
 if(LuaRuntime::TakeCallbackError()){LuaRuntime::LuaErrorHistoryEntryView errors[8]{};auto count=LuaRuntime::CopyLuaErrorHistory(errors,8);for(std::size_t i=0;i<count;++i)std::fprintf(stderr,"CALLBACK ERROR: %s\n",errors[i].text);}
 assert(ExpectNumber("checked",expected));
 assert(room==g_RoomBytes&&game==g_GameBytes&&entities==g_Entities&&owner==g_OwnerSlotBytes&&module==g_ModuleBytes);
}
int main(int argc,char**argv){
 if(argc!=2)return 90;const std::string scene=argv[1];static_cast<void>(kScriptTemplate);static_cast<void>(&HarnessHasCollectible);static_cast<void>(&BuildPrelude);
 CreateBlocks();g_GameBytes.resize(0x360000);g_RoomBytes.resize(0x9000);FillEntities();PublishLists();PublishGame();PublishEntityList(g_RoomBytes,true);
 LuaRuntime::SetEngineModuleBase(g_EngineBase);LuaRuntime::SetGameBindings(g_EngineBase+kGameOwnerGlobalSlotOffset,0x2222);
 FROZEN_GUARD
 WriteAt<float>(g_RoomBytes,0x1a68,21.5F);WriteAt<float>(g_RoomBytes,0x1a6c,13.25F);WriteAt<float>(g_RoomBytes,0x1a70,31.5F);WriteAt<float>(g_RoomBytes,0x1a74,41.5F);
 // 错误 owner 的同偏移和主动道具计数均设置互异值。
 WriteAt<std::int32_t>(g_GameBytes,0x26fa70,97);WriteAt<std::int32_t>(g_GameBytes,0x26fa74,101);WriteAt<float>(g_GameBytes,0x1a6c,51.5F);WriteAt<float>(g_GameBytes,0x12d4,61.5F);WriteAt<float>(g_RoomBytes,0x12d4,71.5F);WriteAt<std::uint32_t>(g_Entities[kPlayer],kEntityPlayerActiveItemOffset,83);
 std::string body;
 if(scene=="native")body="assert(type(room:GetEnemyDamageInflicted())=='number' and room:GetEnemyDamageInflicted()==13.25)";
 else if(scene=="realtime")body="local values={13.25,-2.625,0};assert(room:GetEnemyDamageInflicted()==values[checked+1])";
 else if(scene=="self_table")body="assert(not pcall(getter,{}))";
 else if(scene=="self_game")body="assert(not pcall(getter,Game()))";
 else if(scene=="self_scalar")body="assert(not pcall(getter,13));assert(not pcall(getter,nil))";
 else if(scene=="owner_slot"||scene=="owner_game"||scene=="room_missing"||scene=="guard_update"||scene=="guard_store"||scene=="guard_room")body="assert(not pcall(getter,room))";
 else return 91;
 const std::string script="local mod=RegisterMod('RoomEnemyDamageStorageTest',1);local room=Game():GetRoom();local getter=room.GetEnemyDamageInflicted;assert(type(getter)=='function','public Room getter missing');checked=0;mod:AddCallback(ModCallbacks.MC_POST_UPDATE,function() "+body+";checked=checked+1 end)";
 if(LuaRuntime::InitializeFromBuffer(script.data(),script.size(),"@room-enemy-damage-stat.lua")!=LuaRuntime::LuaInitResult::Success){LuaRuntime::LuaErrorHistoryEntryView errors[8]{};const auto count=LuaRuntime::CopyLuaErrorHistory(errors,8);for(std::size_t i=0;i<count;++i)std::fprintf(stderr,"%s\n",errors[i].text);return 1;}
 // 首次 getter 解析前破坏指定守卫，或让实际 resolver 的 owner 链失效。
 if(scene=="guard_update")g_ModuleBytes[0x767c0]^=1;
 if(scene=="guard_store")g_ModuleBytes[0x76d38]^=1;
 if(scene=="guard_room")g_ModuleBytes[0x468a7c]^=1;
 if(scene=="owner_slot")WriteWord(g_ModuleBytes,kGameOwnerGlobalSlotOffset,0);
 if(scene=="owner_game")WriteWord(g_OwnerSlotBytes,0,0);
 if(scene=="room_missing")WriteWord(g_GameBytes,kGameRoomPointerOffset,0);
 CheckUnchanged(1);
 if(scene=="realtime"){
  WriteAt<float>(g_RoomBytes,0x1a6c,-2.625F);CheckUnchanged(2);
  WriteAt<float>(g_RoomBytes,0x1a6c,0.0F);CheckUnchanged(3);
 }
 return 0;
}
'''
class RoomEnemyDamageStatTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(prefix='room-enemy-damage-');cls.addClassCleanup(cls.tmp.cleanup)
        cls.prefix=os.environ.get('ISAAC_ROOM_ENEMY_DAMAGE_PREFIX','room-enemy-damage-storage-main')
        cls.paths=tuple(p for p in sorted(set(test_support.layered_lua_runtime_sources(fixture.SOURCE))|set((ROOT/'runtime/src').rglob('*.hpp'))|set(fixture.SOURCE.rglob('*.hpp'))) if not p.is_symlink());cls.before=cls.snapshot();OUT.mkdir(parents=True,exist_ok=True)
        (OUT/(cls.prefix+'-input-before.json')).write_text(json.dumps(cls.before,indent=2)+'\n');cls.addClassCleanup(cls.stable)
        nro=next(Path('/Users/kelinls/code/github/isaac mod').glob('The Binding of Isaac_ Afterbirth+*/Program #0/1/.nro/Repentance.nro')).read_bytes()
        guard=''
        for name,offset in (('EntityListUpdate',0x767c0),('EntityListStore',0x76d38),('RoomEntityList',0x468a7c)):
            fixed=nro[offset:offset+16]
            if len(fixed)!=16:raise AssertionError('固定 NRO 守卫字节不足')
            guard+='const unsigned char fixed'+name+'[]={'+','.join(map(str,fixed))+'};std::memcpy(g_ModuleBytes.data()+'+hex(offset)+',fixed'+name+',16);'
        guard+='const unsigned char existingHeightGuard[]={'+','.join(map(str,nro[0x31f18c:0x31f1a4]))+'};std::memcpy(g_ModuleBytes.data()+0x31f18c,existingHeightGuard,24);'
        prefix=fixture.HARNESS[:fixture.HARNESS.index('int main(')];prefix=re.sub(r'namespace GameFileReader \{\nTextReadResult[\s\S]*?\n\}\n\}', '',prefix,count=1)
        observer=(ROOT/'runtime/source/game_observer.cpp').read_text()
        begin=observer.index('GameRoomObservation ReadCurrentGameRoom(uintptr_t ownerSlot, void** room) {')
        end=observer.index('\nGameRoomObservation ReadCurrentGameRoomType',begin)
        actual='namespace engine_memory=isaac::runtime::engine_memory;\n'+re.search(r'constexpr uintptr_t kLevelCurrentRoomOffset = 0x[0-9a-fA-F]+;',observer).group(0)+'\n'+observer[begin:end]
        stub='GameRoomObservation ReadCurrentGameRoom(uintptr_t, void**) {\n    return GameRoomObservation::RoomUnreadable;\n}'
        assert stub in prefix
        prefix=prefix.replace(stub,'static bool IsReadableNonExecutableMapping(std::uintptr_t p,std::size_t n){return isaac::runtime::engine_memory::EngineMemoryReadable(p,n);}'+'\n'+actual)
        source='#include "infrastructure/memory/engine_field_access.hpp"\n'+prefix+MAIN.replace('FROZEN_GUARD',guard);(OUT/(cls.prefix+'-harness.cpp')).write_text(source)
        cls.binary=test_support.build_lua_harness(source_root=fixture.SOURCE,workdir=Path(cls.tmp.name),harness_source=source)
    @classmethod
    def snapshot(cls):return {str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in cls.paths}
    @classmethod
    def stable(cls):
        after=cls.snapshot();(OUT/(cls.prefix+'-input-after.json')).write_text(json.dumps(after,indent=2)+'\n')
        if cls.before!=after:raise AssertionError('生产输入在编译/执行期间改变')
    def test_native_stat_readonly_owner_and_guards(self):
        for scene in ('native','realtime','self_table','self_game','self_scalar','owner_slot','owner_game','room_missing','guard_update','guard_store','guard_room'):
            with self.subTest(scene=scene):
                r=subprocess.run([str(self.binary),scene],text=True,capture_output=True);print(f'{scene}: exit={r.returncode} {r.stdout}{r.stderr}',flush=True);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
