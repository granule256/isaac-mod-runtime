"""真实派发器不得在层号先变、原生房间尚未加载时消费新层身份。"""
import subprocess,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from . import test_game_start_callback_order as startup
from . import test_support
class NativeLevelReadyTests(unittest.TestCase):
 def test_stage_and_type_wait_for_matching_native_completion(self):
  main=startup.MAIN.replace('bool locationReady=true;','bool locationReady=true;std::uint32_t observedStage=1,observedType=0;')
  main=main.replace('*key={84,0,1,0};','*key={84,0,observedStage,observedType};')
  main=main.replace("assert(trace=='9,19,','NEW_LEVEL before NEW_ROOM')","assert(_start.room>_start.level,'NEW_LEVEL before NEW_ROOM')")
  main=main.replace("assert(trace=='9,19,18,15,','POST_UPDATE before startup callbacks: '..trace)","assert(_start.started==1,'POST_UPDATE before startup callbacks')")
  marker=' return 0;\n}'
  checks=r'''
 std::uint32_t nativeLevel[]={1,0};
 isaac::runtime::CompleteNativeRoomLoad([](void*){},nativeLevel);
 LuaRuntime::DispatchPostUpdate();if(errors())return 30; // genuine same-index load
 if(!number("room",2)||!number("level",1))return 31;
 observedStage=2;
 LuaRuntime::DispatchPostUpdate();if(errors())return 32;
 if(!number("room",2)||!number("level",1)){
  std::puts("NEW_LEVEL delivered while native room still belongs to old floor");return 33;
 }
 LuaRuntime::DispatchPostUpdate();if(errors())return 34;
 if(!number("room",2)||!number("level",1))return 35;
 // A completion for a different stage type is not the observed floor.
 nativeLevel[0]=2;nativeLevel[1]=1;
 isaac::runtime::CompleteNativeRoomLoad([](void*){},nativeLevel);
 LuaRuntime::DispatchPostUpdate();if(errors())return 36;
 if(!number("room",2)||!number("level",1))return 37;
 nativeLevel[1]=0;
 isaac::runtime::CompleteNativeRoomLoad([](void*){},nativeLevel);
 LuaRuntime::DispatchPostUpdate();if(errors())return 38;
 if(!number("room",3)||!number("level",2)||!number("started",1))return 39;
 LuaRuntime::DispatchPostUpdate();if(errors())return 40;
 if(!number("room",3)||!number("level",2))return 41;
 // Read failure must not consume a ready subsequent stage either.
 observedStage=3;nativeLevel[0]=3;
 isaac::runtime::CompleteNativeRoomLoad([](void*){},nativeLevel);
 locationReady=false;LuaRuntime::DispatchPostUpdate();if(errors())return 42;
 if(!number("room",3)||!number("level",2))return 43;
 locationReady=true;LuaRuntime::DispatchPostUpdate();if(errors())return 44;
 if(!number("room",4)||!number("level",3))return 45;
'''
  assert marker in main;main=main.replace(marker,checks+marker,1)
  code='#include "native_room_events.hpp"\n'+startup.fixture.HARNESS.split('int main(',1)[0]+main
  flags=tuple(f for f in test_support.HARNESS_COMPILE_FLAGS if not f.startswith('-DEXL_DIAGNOSTIC_STAGE='))
  with tempfile.TemporaryDirectory(prefix='isaac-native-level-ready-')as d:
   with patch.object(test_support,'HARNESS_COMPILE_FLAGS',flags):
    binary=test_support.build_lua_harness(source_root=startup.fixture.SOURCE,workdir=Path(d),harness_source=code)
   r=subprocess.run([str(binary),'fresh'],capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
