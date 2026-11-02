"""Read-only traceback behavior used by transpiled mod error constructors."""
import re
import unittest
from .test_api400_params import run_main
from .test_api600_config import MAIN

SCRIPT = r'''
assert(type(debug.traceback)=="function")
local function capture() return debug.traceback(nil,1) end
local trace=capture()
assert(trace:find("stack traceback:",1,true) and trace:find("api600-config.lua",1,true))
local marker={}
assert(debug.traceback(marker)==marker)
local ok,message=xpcall(function()error("traceback probe")end,debug.traceback)
assert(not ok and message:find("traceback probe",1,true) and message:find("stack traceback:",1,true))
local co=coroutine.create(function()coroutine.yield()end)
assert(coroutine.resume(co))
assert(debug.traceback(co,"coroutine probe",0):find("coroutine probe",1,true))
assert(debug.sethook==nil and debug.setlocal==nil and debug.getregistry==nil)
'''


class DebugTracebackTests(unittest.TestCase):
    def test_messages_stack_levels_and_coroutines(self):
        program = re.sub(r'const char\*script=R"lua\([\s\S]*?\)lua";',
                         lambda _: 'const char*script=R"lua(' + SCRIPT + ')lua";', MAIN, count=1)
        result = run_main(program)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
