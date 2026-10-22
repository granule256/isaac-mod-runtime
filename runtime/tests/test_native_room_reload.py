"""真实派发器：同索引原生加载完成也要送NEW_ROOM，读失败不消费、稳定帧不重复。"""
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from . import test_game_start_callback_order as startup
from . import test_support

class NativeRoomReloadTests(unittest.TestCase):
 def test_same_index_completion_is_delivered_once_after_read_retry(self):
  main=startup.MAIN.replace("assert(trace=='9,19,18,15,','POST_UPDATE before startup callbacks: '..trace)",
                            "assert(_start.started==1,'POST_UPDATE before startup callbacks')")
  marker=' return 0;\n}'
  checks=r'''
 isaac::runtime::NoteNativeRoomLoaded();
 locationReady=false;LuaRuntime::DispatchPostUpdate();if(errors())return 20;
 if(!number("room",1))return 21;
 locationReady=true;LuaRuntime::DispatchPostUpdate();if(errors())return 22;
 if(!number("room",2)||!number("level",1)||!number("init",1)||!number("started",1)){
  std::puts("same-index native room load did not deliver NEW_ROOM");return 23;
 }
 LuaRuntime::DispatchPostUpdate();if(errors())return 24;
 if(!number("room",2)||!number("level",1)||!number("init",1))return 25;
 // A subsequent genuine completion at the same index is a distinct entry.
 isaac::runtime::NoteNativeRoomLoaded();LuaRuntime::DispatchPostUpdate();if(errors())return 26;
 if(!number("room",3)||!number("level",1)||!number("init",1))return 27;
'''
  assert marker in main
  main=main.replace(marker,checks+marker,1)
  code='#include "native_room_events.hpp"\n'+startup.fixture.HARNESS.split('int main(',1)[0]+main
  flags=tuple(f for f in test_support.HARNESS_COMPILE_FLAGS if not f.startswith('-DEXL_DIAGNOSTIC_STAGE='))
  with tempfile.TemporaryDirectory(prefix='isaac-native-room-') as temp:
   with patch.object(test_support,'HARNESS_COMPILE_FLAGS',flags):
    binary=test_support.build_lua_harness(source_root=startup.fixture.SOURCE,workdir=Path(temp),harness_source=code)
   r=subprocess.run([str(binary),'fresh'],capture_output=True,text=True)
   self.assertEqual(r.returncode,0,r.stdout+r.stderr)
