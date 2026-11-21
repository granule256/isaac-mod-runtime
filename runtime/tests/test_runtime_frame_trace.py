import subprocess
import tempfile
import unittest
from pathlib import Path


class RuntimeFrameTraceTests(unittest.TestCase):
    def test_disabled_bounded_capture_and_exclusive_phase_accounting(self):
        root = Path(__file__).resolve().parents[1]
        code = r'''
#include "interfaces/lua/runtime_frame_trace.hpp"
#include <cassert>
using namespace isaac::runtime;
int main() {
    RuntimeFrameTrace t{};
    t.Boundary(10, 0, 0);
    assert(!t.active && t.count == 0);
    t.Boundary(20, 100, 4);
    assert(t.active && t.count == 0);
    auto old = t.Enter(RuntimeFramePhase::Update, 22);
    auto update = t.Enter(RuntimeFramePhase::Lua, 26);
    auto nested = t.Enter(RuntimeFramePhase::Lua, 27);
    t.Leave(nested, 29);
    t.Leave(update, 32);
    t.Leave(old, 35);
    auto render = t.Enter(RuntimeFramePhase::Render, 40);
    t.BeginSubmit(45);
    t.Leave(render, 49);
    t.Boundary(50, 100, 7);
    assert(t.count == 1 && t.rows[0].interval == 30);
    assert(t.rows[0].ticks[0] == 7 && t.rows[0].ticks[1] == 6);
    assert(t.rows[0].ticks[2] == 5 && t.rows[0].ticks[3] == 4);
    assert(t.rows[0].ticks[4] == 8 && t.rows[0].gc == 3);
    t.Boundary(101, 100, 10);
    assert(!t.active && t.count == 1 && t.completedUntil == 100);
    t.Boundary(120, 100, 11);
    assert(!t.active && t.count == 1);
    t.Boundary(130, 2000, 0);
    for (unsigned i = 0; i < kRuntimeFrameTraceCapacity; ++i)
        t.Boundary(131+i, 2000, 0);
    assert(!t.active && t.count == kRuntimeFrameTraceCapacity && t.completedUntil == 2000);
    assert(t.reason == RuntimeFrameFinish::Capacity);
    t.Boundary(1800, 2000, 0);
    assert(t.count == kRuntimeFrameTraceCapacity);
    t.Boundary(2100, 2600, 0);
    t.Boundary(2200, 2700, 0);
    assert(t.active && t.count == 0 && t.until == 2700);
    t.Boundary(2300, 2700, 1);
    t.Finish(RuntimeFrameFinish::VmReset);
    assert(t.count == 1 && t.reason == RuntimeFrameFinish::VmReset);
    t.Boundary(2400, 2700, 0);
    assert(!t.active);
}
'''
        with tempfile.TemporaryDirectory() as folder:
            exe = Path(folder) / 'trace'
            subprocess.run(['c++', '-std=c++20', '-I', str(root / 'src'), '-x', 'c++',
                            '-', '-o', str(exe)], input=code, text=True, check=True)
            subprocess.run([str(exe)], check=True)


if __name__ == '__main__':
    unittest.main()
