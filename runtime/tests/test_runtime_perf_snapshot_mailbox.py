from pathlib import Path
import subprocess
import tempfile
import unittest

from .test_input_slot_collision import HARNESS, SOURCE
from .test_support import build_lua_harness

DECLARATIONS = r'''
#include "interfaces/lua/runtime_perf_snapshot.hpp"
extern "C" {
extern std::uint64_t g_RuntimePerfCaptureRequest, g_RuntimePerfCaptureDone;
extern isaac::runtime::RuntimePerfSnapshot g_RuntimePerfSnapshot;
extern isaac::runtime::RuntimePerfCallbackBucket g_RuntimePerfCallbackBuckets[];
}
'''
SCENARIO = r'''
    g_RuntimePerfCallbackBuckets[511].count = 2;
    g_RuntimePerfCaptureRequest = 1;
    LuaRuntime::BeginGcFrame(1);
    Check(g_RuntimePerfCaptureDone == 1, "game thread completes requested capture");
    Check(g_RuntimePerfSnapshot.header.sequence == 1, "capture echoes sequence");
    Check(g_RuntimePerfSnapshot.callbacks[511].count == 2, "capture includes final bucket");
    g_RuntimePerfCallbackBuckets[511].count = 7;
    LuaRuntime::BeginGcFrame(2);
    Check(g_RuntimePerfSnapshot.callbacks[511].count == 2, "idle frames do not recopy counters");
    g_RuntimePerfCaptureRequest = 2;
    LuaRuntime::BeginGcFrame(3);
    Check(g_RuntimePerfCaptureDone == 2 && g_RuntimePerfSnapshot.callbacks[511].count == 7,
          "a new request produces one fresh snapshot");
'''


class RuntimePerfSnapshotMailboxTests(unittest.TestCase):
    def test_actual_frame_boundary_publishes_once_per_request(self):
        harness = HARNESS.replace('int main() {', DECLARATIONS + '\nint main() {', 1)
        harness = harness.replace('    lua_close(state);', SCENARIO + '\n    lua_close(state);', 1)
        with tempfile.TemporaryDirectory(prefix='isaac-perf-mailbox-') as folder:
            binary = build_lua_harness(source_root=SOURCE, workdir=Path(folder), harness_source=harness)
            result = subprocess.run([str(binary)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
