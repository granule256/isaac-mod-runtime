"""Base pool loads merge enabled mod pools; append loads never recurse."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
PROGRAM = r'''
#include <cstring>
#if __has_include("application/mod/mod_itempool_loading.hpp")
#include "application/mod/mod_itempool_loading.hpp"
#else
namespace isaac::runtime {
struct ModItemPoolBindings {
    using Load = void (*)(void*, const char*, bool);
    using Append = void (*)(void*);
    Load load; Append append;
};
inline void LoadItemPoolsWithMods(const ModItemPoolBindings& b, void* p,
                                 const char* path, bool append) {
    b.load(p, path, append);
}
}
#endif
#include <cstdio>
struct Pool {int order=0;int items=0;bool append=false;};
void Base(void* p,const char* path,bool append) {
    auto& pool=*static_cast<Pool*>(p);
    if(std::strcmp(path,"base.xml"))__builtin_trap();
    pool.order=pool.order*10+1;pool.items=1;pool.append=append;
}
void Mods(void* p) {
    auto& pool=*static_cast<Pool*>(p);
    if(pool.items!=1)__builtin_trap();
    pool.order=pool.order*10+2;pool.items=2;
}
int main() {
    isaac::runtime::ModItemPoolBindings b{Base,Mods};
    Pool pool;
    isaac::runtime::LoadItemPoolsWithMods(b,&pool,"base.xml",false);
    if(pool.order!=12||pool.items!=2||pool.append) {
        std::puts("mod item missing after base pool load");return 1;
    }
    Pool append;
    isaac::runtime::LoadItemPoolsWithMods(b,&append,"base.xml",true);
    if(append.order!=1||!append.append)return 2;
    // Restart/base reload must re-append, rather than using a process-wide latch.
    pool={};isaac::runtime::LoadItemPoolsWithMods(b,&pool,"base.xml",false);
    if(pool.order!=12)return 3;
    b.append=nullptr;pool={};
    isaac::runtime::LoadItemPoolsWithMods(b,&pool,"base.xml",false);
    return pool.order==1?0:4;
}
'''


class ModItemPoolLoadingTests(unittest.TestCase):
    def test_base_load_appends_mods_once_before_consumers_and_reload_repeats(self):
        with tempfile.TemporaryDirectory(prefix="isaac-mod-pools-") as temp:
            source=Path(temp)/"test.cpp";source.write_text(PROGRAM)
            binary=Path(temp)/"test"
            subprocess.run(["c++","-std=c++20","-Wall","-Wextra","-Werror",
                            "-I",str(ROOT/"runtime/src"),str(source),"-o",str(binary)],
                           check=True,capture_output=True)
            result=subprocess.run([str(binary)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
