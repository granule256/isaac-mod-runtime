"""Native libc++ deque uses a start index plus a count, not two indices."""
import subprocess
import tempfile
import unittest
from pathlib import Path
from . import test_console_long_commands as f

DRIVER = r'''
#include "infrastructure/console/console_panel.hpp"
#include <cassert>
#include <array>
static std::vector<std::string> texts;
static void Visit(void*,const char* text,std::size_t length) {texts.emplace_back(text,length);}
int main() {
    std::vector<unsigned char> object(0x180),block1(85*0x30),block2(85*0x30);
    std::array<std::uintptr_t,2> map{memory::AddressOf(block1.data()),memory::AddressOf(block2.data())};
    auto put=[&](std::size_t off,auto value){std::memcpy(object.data()+off,&value,sizeof(value));};
    put(0x58,memory::AddressOf(map.data()));put(0x60,memory::AddressOf(map.data())+sizeof(map));
    put(0x70,std::uint64_t{84});put(0x78,std::uint64_t{3});
    const char* values[]={"last-block", "first-block", "second"};
    unsigned char* entries[]={block1.data()+84*0x30,block2.data(),block2.data()+0x30};
    for(int i=0;i<3;++i)assert(console::BuildBorrowedCommandString(values[i],std::strlen(values[i]),entries[i]));
    assert(console::VisitConsoleHistoryObject(object.data(),Visit,nullptr));
    assert(texts==std::vector<std::string>({"last-block","first-block","second"}));
    texts.clear();put(0x78,std::uint64_t{0});
    assert(console::VisitConsoleHistoryObject(object.data(),Visit,nullptr)&&texts.empty());
    put(0x78,std::uint64_t{1000});
    assert(!console::VisitConsoleHistoryObject(object.data(),Visit,nullptr));
}
'''

class ConsoleHistoryLayoutTests(unittest.TestCase):
    def test_start_plus_count_across_native_blocks(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)
            (folder/'stdfloat').write_text('#pragma once\nnamespace std{using float16_t=float;using float128_t=long double;}\n')
            (folder/'test.cpp').write_text(f.HARNESS[:f.HARNESS.index('int main(')]+DRIVER)
            result=subprocess.run([f.host_compilers()[1],'-std=c++23','-Wall','-Wextra','-Werror',
                '-I',tmp,'-I',str(f.SOURCE),'-I',str(f.SOURCE.parent/'src'),
                str(folder/'test.cpp'),'-o',str(folder/'test')],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            result=subprocess.run([str(folder/'test')],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
