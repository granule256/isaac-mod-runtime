"""Color 的三个可选偏移应各自生效，未提供的后续分量保持零。"""
import subprocess
import tempfile
import unittest
from pathlib import Path

from .test_support import build_lua_harness

SOURCE = Path(__file__).resolve().parents[1] / "source"
HARNESS = r'''
#include "lua_runtime.hpp"
#include <cstdio>
#include <cstring>
int main() {
    const char* script = R"lua(
local cases = {
    {{.2,.3,.4}, {1,0,0,0}},
    {{.2,.3,.4,.5}, {.5,0,0,0}},
    {{.2,.3,.4,.5,.25}, {.5,.25,0,0}},
    {{.2,.3,.4,.5,.25,-.5}, {.5,.25,-.5,0}},
    {{.2,.3,.4,.5,.25,-.5,1.5}, {.5,.25,-.5,1.5}},
}
for i, case in ipairs(cases) do
    local color = Color(table.unpack(case[1]))
    for j, key in ipairs({'A','RO','GO','BO'}) do
        assert(math.abs(color[key]-case[2][j]) < .00001,
            'case '..i..' '..key..': '..color[key]..' expected '..case[2][j])
    end
    assert(math.abs(color.R-.2)<.00001 and math.abs(color.G-.3)<.00001
        and math.abs(color.B-.4)<.00001)
end
local a=Color(1,1,1,1,.25)
local b=Color(1,1,1,1,.75,.5)
local c=Color.Lerp(a,b,.5)
assert(c.RO==.5 and c.GO==.25 and c.BO==0)
assert(a.RO==.25 and b.RO==.75)
local defaults=Color(1,1,1,nil,.25,nil,.75)
assert(defaults.A==1 and defaults.RO==.25 and defaults.GO==0 and defaults.BO==.75)
local falses=Color(1,1,1,false,false,.5,false)
assert(falses.A==1 and falses.RO==0 and falses.GO==.5 and falses.BO==0)
local zeros=Color(1,1,1,0,0,0,0)
assert(zeros.A==0 and zeros.RO==0 and zeros.GO==0 and zeros.BO==0)
assert(not pcall(function() Color(1,1,1,1,true) end))
)lua";
    const auto result = LuaRuntime::InitializeFromBuffer(script, std::strlen(script),
                                                        "@color-optional-offsets.lua");
    if (result != LuaRuntime::LuaInitResult::Success) {
        char error[512]{};
        static_cast<void>(LuaRuntime::CopyLastLuaErrorText(error, sizeof(error)));
        std::printf("result=%u error=%s\n", static_cast<unsigned>(result), error);
        return 1;
    }
    return 0;
}
'''


class ColorOptionalOffsetsTests(unittest.TestCase):
    def test_each_optional_offset_survives_construction_and_interpolation(self):
        with tempfile.TemporaryDirectory(prefix="color-optional-offsets-") as work:
            binary = build_lua_harness(source_root=SOURCE, workdir=Path(work),
                                       harness_source=HARNESS)
            result = subprocess.run([str(binary)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
