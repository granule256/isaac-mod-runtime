"""Native listener checks reuse VM-owned callback states after one bootstrap lookup."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from . import test_support
from .test_repentogon_callbacks import RUNTIME_DRIVER,SOURCE

DRIVER=RUNTIME_DRIVER.replace('mode=="catalog"','(mode=="catalog"||mode=="cached_listeners")')
needle='''            Check();assert(Number("calls")==102&&g_ExtendedCallbackEnabledCount==102);'''
assert needle in DRIVER
DRIVER=DRIVER.replace(needle,needle+r'''
            if(mode=="cached_listeners") {
                auto* storage=g_ExtendedCallbacks;
                g_ExtendedCallbacks=reinterpret_cast<ExtendedCallbackState*>(1);
                for(unsigned pass=0;pass<1000;++pass)
                    for(const auto& callback:expected)assert(Listening(callback.id));
                g_ExtendedCallbacks=storage;
            }
''')

class NativeListenerCacheTests(unittest.TestCase):
 def test_known_ids_never_research_the_sparse_directory(self):
  with tempfile.TemporaryDirectory() as task_dir:
   binary=test_support.build_lua_harness(source_root=SOURCE,workdir=Path(task_dir),harness_source=DRIVER)
   run=subprocess.run([str(binary),'cached_listeners'],capture_output=True,text=True)
   self.assertEqual(run.returncode,0,run.stdout+run.stderr)
