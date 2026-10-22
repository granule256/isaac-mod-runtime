"""真实Lua API经原生指纹保护写集合，断言值变化而非仅探针计数。"""
import subprocess,tempfile,unittest
from pathlib import Path
from .test_support import build_lua_harness
from .test_lua_batch335_player_api_rows import HARNESS,SOURCE
MAIN=r'''
#include "interfaces/lua/seed_effects_api.hpp"
#include <cassert>
using namespace isaac::runtime::seed_effects;
Node* Allocate(std::size_t n){return static_cast<Node*>(std::malloc(n));}
void Release(Node* n){std::free(n);}
void Balance(Node* root,Node* n){assert(root==n);n->black=true;}
void Remove(Node* root,Node* n){assert(root==n);n->parent->left=nullptr;}
int main(){PublishFakeWorld(true,true);
 auto* t=reinterpret_cast<Tree*>(g_GameBytes.data()+kGameSeedsObjectOffset+kSeedsEffectTreeOffset);
 *t={};t->begin=reinterpret_cast<Node*>(&t->root);
 const unsigned offsets[]={0x66fb30,0x66fb10,0x18a20,0x18620};
 const unsigned char guards[][16]={GUARDS};
 for(unsigned i=0;i<4;++i)std::memcpy(g_ModuleBytes.data()+offsets[i],guards[i],16);
 isaac::runtime::SetSeedEffectNativeTestBindings({Allocate,Release,Balance,Remove});
 LuaRuntime::SetGameBindings(reinterpret_cast<std::uintptr_t>(g_OwnerSlotBytes.data()),0x2222);
 const char*s="local s=Game():GetSeeds();assert(not s:HasSeedEffect(10));s:AddSeedEffect(10);assert(s:HasSeedEffect(10));s:AddSeedEffect(10);assert(s:HasSeedEffect(10))";
 assert(LuaRuntime::InitializeFromBuffer(s,strlen(s),"@seed-add.lua")==LuaRuntime::LuaInitResult::Success);
 assert(t->size==1&&t->root->key==10);
 s="local s=Game():GetSeeds();s:RemoveSeedEffect(10);assert(not s:HasSeedEffect(10));s:RemoveSeedEffect(10)";
 assert(LuaRuntime::InitializeFromBuffer(s,strlen(s),"@seed-remove.lua")==LuaRuntime::LuaInitResult::Success);
 assert(t->size==0&&t->root==nullptr&&t->begin==reinterpret_cast<Node*>(&t->root));
}
'''
class SeedEffectLuaTests(unittest.TestCase):
 def test_lua_mutation_and_original_native_guards(self):
  root=Path(__file__).resolve().parents[2];nro=next(root.glob('The Binding of Isaac_*/Program #0/1/.nro/Repentance.nro')).read_bytes()
  guards=','.join('{'+','.join(str(x)for x in nro[o:o+16])+'}'for o in [0x66fb30,0x66fb10,0x18a20,0x18620])
  with tempfile.TemporaryDirectory(prefix='seed-effect-lua-')as tmp:
   binary=build_lua_harness(source_root=SOURCE,workdir=Path(tmp),harness_source=HARNESS[:HARNESS.index('int main(')]+MAIN.replace('GUARDS',guards))
   r=subprocess.run([str(binary)],capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
