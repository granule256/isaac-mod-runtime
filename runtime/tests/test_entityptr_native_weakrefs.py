"""真实Lua路径必须登记原生弱引用；ClearReferences与GC不依赖D2信号。"""
import unittest
from .test_api600_entityptr import MAIN
from .entityptr_native_fixture import with_native_weak
from .test_api400_params import run_main
PROBE=r'''
if(luaL_dostring(L,"nativePtr=EntityPtr(player);assert(nativePtr.Ref~=nil)"))return 11;
// Native ClearReferences发生时，实体仍有NPC/Player vtable且lifetime token尚未退役。
ClearNativeWeak(AddressOf(g_Entities[kPlayer]));
if(luaL_dostring(L,"assert(nativePtr.Ref==nil,'native reference clear must precede D2');replacement=EntityPtr(player);assert(replacement.Ref~=nil and nativePtr.Ref==nil)")){std::fprintf(stderr,"%s\n",lua_tostring(L,-1));return 12;}
auto before=NativeWeakCount(AddressOf(g_Entities[kPlayer]));
if(luaL_dostring(L,"do local temporary=EntityPtr(player);assert(temporary.Ref)end;collectgarbage('collect');collectgarbage('collect')"))return 13;
assert(NativeWeakCount(AddressOf(g_Entities[kPlayer]))==before);
'''
class EntityPtrNativeWeakTests(unittest.TestCase):
 def test_clear_references_and_gc_before_destruction(self):
  main=with_native_weak(MAIN).replace('ClearNativeWeak(AddressOf(g_Entities[kPlayer]));\nRetireEntityLifetime',PROBE+'\nClearNativeWeak(AddressOf(g_Entities[kPlayer]));\nRetireEntityLifetime',1)
  r=run_main(main);self.assertEqual(r.returncode,0,r.stdout+r.stderr)

class EntityPtrGuardTests(unittest.TestCase):
 def test_native_guards_match_original_nro(self):
  from pathlib import Path
  import re,sys
  root=Path(__file__).resolve().parents[2];sys.path.insert(0,str(root/'tools'))
  from nro_disasm import DEFAULT_NRO
  original=Path(DEFAULT_NRO).read_bytes();source=(root/'runtime/src/interfaces/lua/api600_entityptr.guards.hpp').read_text()
  for name,offset in [('kSetGuard',0x677c0),('kDestroyGuard',0x4b1f1c)]:
   data=re.search(name+r'\[\]=\{([^}]+)\}',source).group(1);guard=bytes(int(v.strip(),16)for v in data.split(',')if v.strip())
   self.assertEqual(len(guard),16);self.assertEqual(original[offset:offset+16],guard)

class EntityPtrShutdownTests(unittest.TestCase):
 def test_real_shutdown_blocks_new_registrations_and_drains_existing(self):
  from pathlib import Path
  import tempfile
  from unittest.mock import patch
  from . import test_support
  root=Path(__file__).resolve().parents[2];source=root/'runtime/source'
  original=test_support.layered_lua_runtime_sources
  closing=r'''
LuaRuntime::ObserveGameThread();assert(LuaRuntime::ShutdownForModReload());
lua_pushcfunction(L,CloseResult);lua_setglobal(L,"closeResult");
if(luaL_dostring(L,"closeHeld=EntityPtr(newPlayer);held=setmetatable({},{__gc=function() local a,e=pcall(EntityPtr,newPlayer);local b,f=pcall(function()closeHeld:SetReference(newPlayer)end);local c=pcall(function()closeHeld:SetReference(nil)end);local d,x=pcall(EntityPtr,nil);closeResult(not a and not b and c and d and x.Ref==nil,e,f) end})")){std::fprintf(stderr,"%s\n",lua_tostring(L,-1));return 20;}
ReloadAdoptState(L);assert(LuaRuntime::ShutdownForModReload());assert(closingOK);assert(NativeWeakCount(AddressOf(g_Entities[kPlayer]))==0);return 0;}
'''
  support=r'''
extern "C" void ReloadAdoptState(lua_State*);
static bool closingOK;
static int CloseResult(lua_State* L){assert(LuaRuntime::ClosingForModReload());closingOK=lua_toboolean(L,1)&&std::strstr(lua_tostring(L,2),"shutdown")&&std::strstr(lua_tostring(L,3),"shutdown");return 0;}
'''
  main=with_native_weak(MAIN).replace('int main(){',support+'\nint main(){',1).replace('lua_close(L);return 0;}',closing)
  with tempfile.TemporaryDirectory(prefix='weakptr-real-close-')as tmp:
   copied=Path(tmp)/'lua_runtime.cpp';copied.write_text((source/'lua_runtime.cpp').read_text()+'\nnamespace LuaRuntime {extern "C" void ReloadAdoptState(lua_State* L){g_LuaState=L;g_Ready.store(true);}}\n')
   def sources(path):return tuple(copied if p==source/'lua_runtime.cpp'else p for p in original(path))
   with patch.object(test_support,'layered_lua_runtime_sources',sources):r=run_main(main)
   self.assertEqual(r.returncode,0,r.stdout+r.stderr)

if __name__=='__main__':unittest.main()
