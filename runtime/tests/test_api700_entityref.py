"""第七批EntityRef三字段，实际Lua getter/setter与const视图。"""
import unittest
from .test_api700_player import MAIN,run
SCRIPT=r"""
local r=EntityRef();assert(r.Position.X==0 and r.Position.Y==0 and r.IsFriendly==false and r.IsCharmed==false)
r.Position=Vector(8,9);assert(r.Position.X==8 and r.Position.Y==9);local v=r.Position;v.X=77;assert(r.Position.X==8)
r.IsFriendly=0;r.IsCharmed=true;assert(r.IsFriendly and r.IsCharmed);r.IsFriendly=false;assert(not r.IsFriendly and r.IsCharmed);r.IsCharmed=nil;assert(not r.IsCharmed)
assert(not pcall(function()r.Position={}end));assert(not pcall(function()r.Type=5 end));assert(not pcall(function()r.Unknown=true end))
local cb=callbackSnapshot;assert(cb.Position.X==2 and cb.IsFriendly and cb.IsCharmed);cb.IsFriendly=false;cb.IsCharmed=false;assert(not cb.IsFriendly and not cb.IsCharmed);cb.Position=Vector(5,6);checkOwned(cb)
local live=p:GetLastDamageSource();assert(live.Position.X==2 and live.Position.Y==3 and live.IsCharmed and live.IsFriendly)
local copy=live.Position;copy.X=99;assert(live.Position.X==2);assert(not pcall(function()live.IsCharmed=false end));assert(not pcall(function()live.Position=Vector(4,5)end))
local snapshot=EntityRef(live.Entity);assert(type(snapshot.IsFriendly)=='boolean' and type(snapshot.IsCharmed)=='boolean' and type(snapshot.Position.X)=='number')
"""
class EntityRefFields(unittest.TestCase):
 def test_public_ref_fields(self):
  main=MAIN.replace('static int Advance(', 'static int CheckOwned(lua_State*L){auto*p=static_cast<unsigned char*>(EntityRefBufferAt(L,1));std::uint32_t flags{};std::memcpy(&flags,p+0x20,4);assert(flags==0xf0000000);LuaRuntime::VectorHandle v{};std::memcpy(&v,p+0x10,8);assert(v.x==5&&v.y==6);return 0;}\nstatic int Advance(')
  main=main.replace('const char*script=R"lua(', 'const char*script=R"lua('+SCRIPT)
  main=main.replace('lua_pushcfunction(L,EntityRefIndex);', 'lua_pushcfunction(L,EntityRefNewIndex);lua_setfield(L,-2,"__newindex");lua_pushcfunction(L,EntityRefIndex);')
  main=main.replace('namespace G=api700_player;', 'WriteAt<LuaRuntime::VectorHandle>(g_Entities[kPlayer],0x1a80,{2,3});WriteAt<std::uint32_t>(g_Entities[kPlayer],0x1a90,0xf0000003);namespace G=api700_player;')
  main=main.replace('const char*script=R"lua(', 'PushEntityRefArgument(L,AddressOf(g_Entities[kPlayer])+0x1a70);lua_setglobal(L,"callbackSnapshot");lua_pushcfunction(L,CheckOwned);lua_setglobal(L,"checkOwned");const char*script=R"lua(')
  r=run(main=main);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
