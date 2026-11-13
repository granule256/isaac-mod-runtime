"""The native panel can dispatch completions without linking a Lua VM."""
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ConsoleAutocompletePortTests(unittest.TestCase):
    def test_unbound_bound_and_reset_panel_dispatch(self):
        code = r'''
#include "infrastructure/console/console_panel.hpp"
#include <cassert>
#include <cstring>
using namespace isaac::runtime::console;
static unsigned calls;
static bool Collect(void* user,const char* text,std::size_t length,
                    const char* description,std::size_t descriptionLength) {
    assert(user==&calls && length==5 && !std::memcmp(text,"stage",5));
    assert(descriptionLength==4 && !std::memcmp(description,"desc",4));
    return true;
}
static bool Complete(const char* command,std::size_t length,
                     const char* parameters,std::size_t parameterLength,
                     AutocompleteVisitor visitor,void* user) noexcept {
    ++calls;assert(length==3 && !std::memcmp(command,"cmd",3));
    assert(parameterLength==1 && parameters[0]=='s');
    return visitor(user,"stage",5,"desc",4);
}
int main() {
    assert(!DispatchPanelAutocomplete("cmd",3,"s",1,Collect,&calls));
    SetAutocompleteDispatch(Complete);
    assert(DispatchPanelAutocomplete("cmd",3,"s",1,Collect,&calls));
    assert(calls==1);
    SetAutocompleteDispatch(nullptr);
    assert(!DispatchPanelAutocomplete("cmd",3,"s",1,Collect,&calls));
    assert(calls==1);
}
'''
        with tempfile.TemporaryDirectory(prefix='console-completion-port-') as folder:
            source = Path(folder) / 'test.cpp'
            source.write_text(code)
            binary = Path(folder) / 'test'
            build = subprocess.run(
                ['c++', '-std=c++20', '-Wall', '-Wextra', '-Werror',
                 '-I'+str(ROOT/'src'), '-I'+str(ROOT/'source'),
                 str(source), '-o', str(binary)], capture_output=True, text=True)
            self.assertEqual(build.returncode, 0, build.stdout + build.stderr)
            result = subprocess.run([str(binary)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
