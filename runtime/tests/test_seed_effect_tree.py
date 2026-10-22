"""枚举集合增删：与独立set对照，覆盖重复、缺失、根/最左/两子节点及负数。"""
import subprocess,tempfile,unittest
from pathlib import Path
from .test_clear_award_internal_adapter import helper
ROOT=Path(__file__).resolve().parents[2]
DRIVER=r'''
#include <cassert>
#include <cstdlib>
#include <set>
#if __has_include("infrastructure/memory/seed_effect_tree.hpp")
#include "infrastructure/memory/seed_effect_tree.hpp"
using namespace isaac::runtime::seed_effects;
unsigned allocations{},frees{},balances{},removals{};
Node* Allocate(std::size_t n){assert(n==32);++allocations;return static_cast<Node*>(std::malloc(n));}
void Free(Node* n){++frees;std::free(n);}
void Balance(Node* root,Node* n){assert(root&&n);++balances;}
void Remove(Node* root,Node* n){
 assert(root&&n);++removals;
 auto replace=[](Node* a,Node* b){if(a==a->parent->left)a->parent->left=b;else a->parent->right=b;if(b)b->parent=a->parent;};
 if(!n->left)replace(n,n->right);
 else if(!n->right)replace(n,n->left);
 else {Node* s=n->right;while(s->left)s=s->left;if(s->parent!=n){replace(s,s->right);s->right=n->right;s->right->parent=s;}replace(n,s);s->left=n->left;s->left->parent=s;}
}
bool Readable(const void* p,std::size_t){return p!=nullptr;}
void Check(Tree& t,const std::set<int>& expected){
 assert(t.size==expected.size());auto* end=reinterpret_cast<Node*>(&t.root);
 if(expected.empty()){assert(t.begin==end&&t.root==nullptr);return;}
 auto* n=t.root;while(n->left)n=n->left;assert(n==t.begin);
 for(int v:expected){assert(n!=end&&n->key==v);n=Next(n);}assert(n==end);
}
int main(){Tree t{};t.begin=reinterpret_cast<Node*>(&t.root);std::set<int> ref;Bindings b{Allocate,Free,Balance,Remove};
 for(int v:{10,4,17,2,6,11,21,0,-7,100}){assert(Write(t,v,true,b,Readable));ref.insert(v);Check(t,ref);}
 auto a=allocations;assert(Write(t,10,true,b,Readable)&&allocations==a);Check(t,ref);
 assert(Write(t,1000,false,b,Readable)&&frees==0);Check(t,ref);
 for(int v:{10,-7,0,4,21,2,6,11,17,100}){assert(Write(t,v,false,b,Readable));ref.erase(v);Check(t,ref);}
 assert(allocations==frees&&balances==10&&removals==10);
 assert(Write(t,5,true,b,Readable));assert(Write(t,5,false,b,Readable));Check(t,ref);
 assert(!Write(t,5,true,Bindings{},Readable));
}
#else
int main(){assert(false&&"整数种子效果增删缺失；当前Lua真机Count0仍0");}
#endif
'''
class SeedEffectTreeTests(unittest.TestCase):
 def test_native_tree_mutation_matches_set(self):
  helper.InternalHookAdapterTests().compile_run(DRIVER,[])
