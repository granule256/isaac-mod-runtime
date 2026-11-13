"""Only console consumers need C++ catch support in the production build."""
from pathlib import Path
import re
import subprocess
import tempfile
import unittest


COMMON = Path(__file__).resolve().parents[1] / 'misc/mk/common.mk'
RUNTIME = COMMON.parents[2]


class ConsoleExceptionBuildFlagsTests(unittest.TestCase):
    def test_command_registry_does_not_import_local_static_guards(self):
        source = r'''
#include "domain/console/console_commands.hpp"
std::size_t UseRegistry() {
    using namespace isaac::runtime::console;
    ResetConsoleCommands();
    RegisterConsoleCommand("test", "description", "help", true, 0);
    return ConsoleCommandCount();
}
'''
        with tempfile.TemporaryDirectory(prefix='console-static-guard-') as folder:
            path = Path(folder)/'test.cpp';path.write_text(source)
            obj = Path(folder)/'test.o'
            build = subprocess.run(['c++','-std=c++20','-O2','-fno-exceptions','-fno-rtti',
                                    '-I'+str(RUNTIME/'src'),'-c',str(path),'-o',str(obj)],
                                   capture_output=True,text=True)
            self.assertEqual(build.returncode,0,build.stdout+build.stderr)
            symbols = subprocess.run(['nm','-u',str(obj)],capture_output=True,text=True)
            self.assertEqual(symbols.returncode,0,symbols.stderr)
            self.assertNotIn('__cxa_guard_',symbols.stdout)

    def test_console_objects_override_the_default_without_changing_other_units(self):
        common = COMMON.read_text()
        objects = re.search(r'^CONSOLE_EXCEPTION_OBJECTS\s*:=.*$',common,re.M)
        rule = re.search(r'^\$\(CONSOLE_EXCEPTION_OBJECTS\):\s*CXXFLAGS\s*\+=.*$',common,re.M)
        policy = '\n'.join(x.group(0) for x in (objects,rule) if x)
        makefile = ('CXXFLAGS := -fno-exceptions\n'+policy+'\n'
                    'hook_manager.o isaac_api.o repentogon_console_api.o unrelated.o:\n'
                    '\t@echo $(CXXFLAGS)\n')
        with tempfile.TemporaryDirectory(prefix='console-exception-flags-') as folder:
            path = Path(folder)/'Makefile';path.write_text(makefile)
            for target in ('hook_manager.o','isaac_api.o','repentogon_console_api.o','unrelated.o'):
                with self.subTest(target=target):
                    run = subprocess.run(['make','--no-print-directory','-f',str(path),target],
                                         capture_output=True,text=True,cwd=folder)
                    self.assertEqual(run.returncode,0,run.stdout+run.stderr)
                    flags = [f for f in run.stdout.split() if f in ('-fexceptions','-fno-exceptions')]
                    self.assertEqual(flags[-1],'-fno-exceptions' if target=='unrelated.o' else '-fexceptions')
