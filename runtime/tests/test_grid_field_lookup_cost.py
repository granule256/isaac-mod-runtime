"""Unknown grid methods do not linearly scan unrelated world-field names."""
from pathlib import Path
import subprocess
import tempfile
import unittest

from .test_lua_api_method_lookup_cost import function

ROOT = Path(__file__).resolve().parents[2]


class GridFieldLookupCostTests(unittest.TestCase):
    def test_real_grid_owner_preserves_types_without_linear_name_scan(self):
        source = (ROOT / 'runtime/src/interfaces/lua/api600_world.cpp').read_text()
        start = source.index('enum class Kind:')
        end = source.index('\n};', start) + 3
        declarations = source[start:end]
        hash_function = function(source, 'constexpr std::uint32_t Hash(')
        lookup = function(source, 'const Field* Find(')
        if 'const Field* FindField(' in source:
            lookup = function(source, 'const Field* FindField(') + '\n' + lookup
        owner = function(source, 'const char* GridOwner(')
        driver = r'''
#include <cstdint>
#include <cstring>
#include <cassert>
#include <cstdio>
#include <stdexcept>
#include <initializer_list>
struct lua_State {};
unsigned comparisons{}, reads{}, validations{};
bool live = true;
std::uintptr_t vtable = 101;
int CountedCompare(const char* a,const char* b) { ++comparisons;return std::strcmp(a,b); }
bool IsLiveGridEntityPointer(std::uintptr_t){++validations;return live;}
int luaL_error(lua_State*,const char*){throw std::runtime_error("stale grid");}
template<class T>T Read(lua_State*,std::uintptr_t,unsigned){++reads;return static_cast<T>(vtable);}
namespace LuaRuntime {std::uintptr_t EngineModuleBase(){return 100;}}
constexpr unsigned kGridEntity_DoorVtableOffset=1,kGridEntity_PoopVtableOffset=2;
constexpr unsigned kGridEntity_PressurePlateVtableOffset=3,kGridEntity_RockVtableOffset=4;
'''
        main = r'''
int main() {
 lua_State state;
 for(const char* name : {"GetSaveState","GetRNG","GetSaveStateExtra","State",
                         "CollisionClass","GetType","Position","GreedModeWave",""}) {
  comparisons=reads=validations=0;
  assert(!GridOwner(&state,1,name));
  if(comparisons>1){std::fprintf(stderr,"%s scanned %u field names",name,comparisons);return 1;}
  assert(reads==0 && validations==0);
 }
 for(const auto& field:kFields) {
  if(field.owner[0]!='G'||field.owner[1]!='r')continue;
  vtable=!std::strcmp(field.owner,"GridEntityDoor")?101:
         !std::strcmp(field.owner,"GridEntityPoop")?102:
         !std::strcmp(field.owner,"GridEntityPressurePlate")?103:104;
  comparisons=reads=validations=0;
  auto* result=GridOwner(&state,1,field.name);
  assert(result && !std::strcmp(result,field.owner));
  assert(reads==1 && validations==1);
  vtable=999;assert(!GridOwner(&state,1,field.name));
 }
 live=false;
 try{GridOwner(&state,1,"OpenAnimation");return 2;}catch(const std::runtime_error&){}
 assert(!GridOwner(&state,1,"GetSaveState"));
 assert(Find("Level","GreedModeWave") && !Find("Game","GreedModeWave"));
}
'''
        body = (lookup + '\n' + owner).replace('std::strcmp', 'CountedCompare')
        with tempfile.TemporaryDirectory(prefix='isaac-grid-field-cost-') as folder:
            cpp = Path(folder) / 'driver.cpp'
            binary = Path(folder) / 'driver'
            cpp.write_text(driver + declarations + '\n' + hash_function + '\n' + body + '\n' + main)
            result = subprocess.run(['c++', '-std=c++17', str(cpp), '-o', str(binary)],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            result = subprocess.run([str(binary)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
