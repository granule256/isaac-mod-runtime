"""借用容器与向量身份：真实内嵌对象、元素别名与重分配/owner失效。"""
from unittest import mock
import unittest
from . import test_api700_containers as original
class ContainerPointerIdentity(unittest.TestCase):
 def test_native_list_and_element_aliases_and_retirement(self):
  main=original.MAIN
  needle='const char*script=R"lua('
  self.assertIn(needle,main)
  setup=r'''
 lua_pushinteger(L,static_cast<lua_Integer>(AddressOf(g_Entities[kEffect])+0x478));lua_setglobal(L,"samplesObject");
 lua_pushinteger(L,static_cast<lua_Integer>(reinterpret_cast<std::uintptr_t>(samples)));lua_setglobal(L,"sampleElement");
 lua_pushinteger(L,static_cast<lua_Integer>(AddressOf(g_RoomBytes)+0x19c0));lua_setglobal(L,"entitiesObject");
'''
  main=main.replace(needle,setup+needle)
  main=main.replace('local s=laser:GetSamples();',"local s=laser:GetSamples();assert(GetPtrHash(s)==samplesObject,'VectorList must identify native vector');assert(GetPtrHash(laser:GetSamples())==GetPtrHash(s));")
  main=main.replace('local v=s:Get(0);',"local v=s:Get(0);assert(GetPtrHash(v)==sampleElement and GetPtrHash(s:Get(0))==sampleElement,'element identity must be native address');")
  main=main.replace('local entities=room:GetEntities();',"local entities=room:GetEntities();assert(GetPtrHash(entities)==entitiesObject and GetPtrHash(room:GetEntities())==entitiesObject);assert(GetPtrHash(list)~=0 and GetPtrHash(list)~=GetPtrHash(b),'owned query results have independent value storage');")
  main=main.replace('reallocate();',"reallocate();assert(GetPtrHash(v)==0 and GetPtrHash(s)==samplesObject);assert(GetPtrHash(s:Get(0))~=sampleElement and GetPtrHash(s:Get(0))~=0);")
  main=main.replace('resetArena();',"resetArena();assert(GetPtrHash(list)==0);")
  main=main.replace('changeOwner();',"changeOwner();assert(GetPtrHash(entities)==0);")
  main=main.replace('retireLaser();',"retireLaser();assert(GetPtrHash(s)==0 and GetPtrHash(raw)==0);")
  with mock.patch.object(original,'MAIN',main):
   r=original.run();self.assertEqual(r.returncode,0,r.stdout+r.stderr)
