"""弹幕公开属性和加法方法：逐步独立核对完整实体字节，拒绝写入不得改邻居。"""
import re
import subprocess
import tempfile
import unittest
from pathlib import Path
from . import test_lua_entity_query as fixture
from .test_support import build_lua_harness

MAIN = r'''
#include "interfaces/lua/api400_entities.guards.hpp"
#include "interfaces/lua/api400_fields.guards.hpp"
#include "interfaces/lua/rplus_extended_fields_guards.hpp"
#include "interfaces/lua/entity_lifetime.hpp"
#include <cassert>
extern "C" {
#include <lauxlib.h>
#include <lualib.h>
}
using namespace isaac::runtime;
static void Run(lua_State* L, const char* script) {
    if (luaL_dostring(L, script)) {
        std::fprintf(stderr, "%s\nScript:\n%s\n", lua_tostring(L, -1), script);
        std::abort();
    }
}
template<class T> static void Change(lua_State* L, const char* script,
                                     unsigned offset, T expected) {
    auto bytes = g_Entities[kBullet];
    std::memcpy(bytes.data() + offset, &expected, sizeof(expected));
    Run(L, script);
    assert(bytes == g_Entities[kBullet]);
}
int main() {
    static_cast<void>(kScriptTemplate);static_cast<void>(&HarnessHasCollectible);
    static_cast<void>(&BuildPrelude);static_cast<void>(&ExpectNumber);
    CreateBlocks();FillEntities();
    WriteWord(g_Entities[kBullet], 0, g_EngineBase + kEntityProjectileVtableOffset);
    PublishLists();PublishGame();PublishEntityList(g_RoomBytes, true);
    LuaRuntime::SetEngineModuleBase(g_EngineBase);
    LuaRuntime::SetGameBindings(g_EngineBase+kGameOwnerGlobalSlotOffset, 0x2222);
    namespace A=api400_entities;namespace F=api400_fields;namespace E=extended_fields;
#define GUARD(ns, name) std::memcpy(g_ModuleBytes.data()+ns::k##name##Entry, ns::k##name##Guard.data(),ns::k##name##Guard.size())
    GUARD(A, ProjectileLayout);GUARD(A, ProjectileUpdate);GUARD(F, Projectile);
    GUARD(E, Projectile0);GUARD(E, Entity0);GUARD(E, Entity1);GUARD(E, Entity2);
#undef GUARD
    // 在已经有效的独立实体中填充非零邻居，不能让越界写被全零缓冲掩盖。
    for (unsigned i=0x400;i<0x460;++i) g_Entities[kBullet][i]=0xa5;
    auto* L=luaL_newstate();luaL_requiref(L,"_G",luaopen_base,1);lua_pop(L,1);
    luaL_requiref(L,LUA_STRLIBNAME,luaopen_string,1);lua_pop(L,1);
    assert(RegisterIsaacApi(L));
    PushEntityCallbackArgument(L,AddressOf(g_Entities[kBullet]));lua_setglobal(L,"p");
    Change(L,"p.Acceleration=1.25;assert(p.Acceleration==1.25)",0x41c,1.25F);
    Change(L,"p.ChangeVelocity=2.5;assert(p.ChangeVelocity==2.5)",0x440,2.5F);
    Change(L,"p.CurvingStrength=-0.125;assert(p.CurvingStrength==-0.125)",0x418,-0.125F);
    Change(L,"p.HomingStrength=0.75;assert(p.HomingStrength==0.75)",0x414,0.75F);
    Change(L,"p.FallingAccel=0.125;assert(p.FallingAccel==0.125)",0x408,0.125F);
    Change(L,"p.FallingSpeed=-3.5;assert(p.FallingSpeed==-3.5)",0x404,-3.5F);
    Change(L,"p.Height=-23.25;assert(p.Height==-23.25)",0x400,-23.25F);
    Change(L,"p.Scale=1.5;assert(p.Scale==1.5)",0x410,1.5F);
    Change(L,"p.DepthOffset=-7.25;assert(p.DepthOffset==-7.25)",0x32c,-7.25F);
    Change(L,"p.ChangeTimeout=0xffffffff;assert(p.ChangeTimeout==-1)",0x444,std::int32_t{-1});
    Change(L,"p.WiggleFrameOffset=0x100000001;assert(p.WiggleFrameOffset==1)",0x434,std::int32_t{1});
    Change(L,"p.ChangeFlags=0x8000000000000001;assert(p.ChangeFlags==0x8000000000000001)",0x438,std::uint64_t{0x8000000000000001ULL});
    Change(L,"p:AddChangeFlags(0x2000000000000002);assert(p.ChangeFlags==0xa000000000000003)",0x438,std::uint64_t{0xa000000000000003ULL});
    Change(L,"p:AddChangeFlags(0x2000000000000002)",0x438,std::uint64_t{0xa000000000000003ULL});
    Change(L,"p:AddFallingAccel(-0.5);assert(p.FallingAccel==-0.375)",0x408,-0.375F);
    Change(L,"p:AddFallingSpeed(1.25);assert(p.FallingSpeed==-2.25)",0x404,-2.25F);
    Change(L,"p:AddHeight(2.5);assert(p.Height==-20.75)",0x400,-20.75F);
    Change(L,"p:AddScale(-0.25);assert(p.Scale==1.25)",0x410,1.25F);
    Change(L,"p.ProjectileFlags=0x300000000;assert(p.ProjectileFlags==0x300000000, 'high projectile flags truncated');assert(p:HasProjectileFlags(0x100000000));assert(not p:HasProjectileFlags(0x400000000))",0x428,std::uint64_t{0x300000000ULL});
    Change(L,"p.ProjectileFlags=0x8000000000000001;assert(p.ProjectileFlags==0x8000000000000001);assert(p:HasProjectileFlags(0x8000000000000000))",0x428,std::uint64_t{0x8000000000000001ULL});
    Change(L,"p.ProjectileFlags=0x80000000;assert(p.ProjectileFlags==0x80000000)",0x428,std::uint64_t{0x80000000ULL});
    auto before=g_Entities[kBullet];
    Run(L,R"lua(
      for _,name in ipairs({'Acceleration','ChangeVelocity','CurvingStrength','HomingStrength',
          'FallingAccel','FallingSpeed','Height','Scale','DepthOffset','ChangeTimeout','WiggleFrameOffset','ChangeFlags'}) do
        assert(not pcall(function()p[name]={}end),name)
      end
      for _,name in ipairs({'ChangeTimeout','WiggleFrameOffset','ChangeFlags'}) do
        assert(not pcall(function()p[name]=1.5 end),name)
      end
      for _,name in ipairs({'AddChangeFlags','AddFallingAccel','AddFallingSpeed','AddHeight','AddScale'}) do
        assert(not pcall(function()p[name](p,{})end),name)
        assert(not pcall(function()p[name](p)end),name)
      end
      assert(not pcall(function()p:AddChangeFlags(1.5)end))
    )lua");
    assert(before==g_Entities[kBullet]);
    // 原生侧独立改数后，公开 getter 必须读取新值，排除 Lua 影子字段。
    WriteAt<float>(g_Entities[kBullet],0x404,6.25F);
    WriteAt<std::uint64_t>(g_Entities[kBullet],0x438,0x4000000000000001ULL);
    Run(L,"assert(p.FallingSpeed==6.25 and p.ChangeFlags==0x4000000000000001)");
    Run(L,"cachedHeight=p.AddHeight;cachedFlags=p.AddChangeFlags");
    RetireEntityLifetime(AddressOf(g_Entities[kBullet]));
    before=g_Entities[kBullet];
    Run(L,R"lua(
      assert(p.FallingSpeed==nil)
      p.Height=-3
      assert(not pcall(function()p:AddChangeFlags(1)end))
      assert(not pcall(function()p:AddHeight(1)end))
      assert(not pcall(function()cachedHeight(p,1)end))
      assert(not pcall(function()cachedFlags(p,1)end))
    )lua");
    assert(before==g_Entities[kBullet]);
    lua_close(L);return 0;
}
'''

class ProjectileMemoryContract(unittest.TestCase):
    def test_public_fields_and_additions_preserve_other_bytes(self):
        prefix=fixture.HARNESS[:fixture.HARNESS.index('int main(')]
        prefix=re.sub(r'namespace GameFileReader \{\nTextReadResult[\s\S]*?\n\}\n\}', '', prefix, count=1)
        with tempfile.TemporaryDirectory(prefix='projectile-memory-') as d:
            binary=build_lua_harness(source_root=fixture.SOURCE,workdir=Path(d),harness_source=prefix+MAIN)
            result=subprocess.run([str(binary)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
