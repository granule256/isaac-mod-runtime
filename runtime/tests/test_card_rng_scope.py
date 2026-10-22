import subprocess,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
class CardRngScopeTests(unittest.TestCase):
 def test_nested_expired_and_reused_scope(self):
  header=ROOT/'runtime/source/card_rng_scope.hpp'
  self.assertTrue(header.exists(),'20借用RNG作用域尚未实现')
  source=r'''#include "card_rng_scope.hpp"
#include <cassert>
using namespace isaac::runtime;
int main(){CardRngScopes scopes; CardRngScope a{},b{},c{};
assert(scopes.Enter(a,123));auto old=a.token;
assert(scopes.Resolve(123,old)==123);assert(scopes.Enter(b,123));
assert(scopes.Resolve(123,old)==123);auto inner=b.token;scopes.Leave(b);
assert(scopes.Resolve(123,inner)==0);assert(scopes.Resolve(123,old)==123);
scopes.Leave(a);assert(scopes.Resolve(123,old)==0);assert(scopes.Enter(c,123));
assert(c.token!=old&&scopes.Resolve(123,old)==0);scopes.Leave(c);
scopes.lastToken=UINT64_MAX;assert(!scopes.Enter(a,123));assert(scopes.top==nullptr);}
'''
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);(p/'test.cpp').write_text(source)
   r=subprocess.run(['c++','-std=c++17','-Wall','-Wextra','-Werror','-I',str(ROOT/'runtime/source'),str(p/'test.cpp'),'-o',str(p/'test')],capture_output=True,text=True)
   self.assertEqual(r.returncode,0,r.stderr)
   self.assertEqual(subprocess.run([str(p/'test')]).returncode,0)
