"""共享Door接收者验证：Open/Close/Arcade真实调用与错误vptr统一拒绝。"""
from pathlib import Path
from unittest import mock
import subprocess,unittest
from . import test_remaining_reference_fields as original
class LiveDoorNativeCalls(original.RemainingReferenceFieldTests):
 @classmethod
 def setUpClass(cls):
  source=original.MAIN
  extra=r'''static bool forceSeen[2]{};
static void NativeDoorClose(void*self,bool force){assert(self==doorBytes.data());assert(openCalls>=2&&openCalls<4);forceSeen[openCalls-2]=force;++openCalls;}
static bool NativeDoorArcade(const void*self){assert(self==doorBytes.data());++openCalls;return openCalls==5;}
'''
  source=source.replace('static void NativeDoorOpen(',extra+'static void NativeDoorOpen(',1)
  source=source.replace(' return original;',' if(original==g_EngineBase+0x3820f4){lastOriginal=original;return reinterpret_cast<std::uintptr_t>(&NativeDoorClose);}\n if(original==g_EngineBase+0x386038){lastOriginal=original;return reinterpret_cast<std::uintptr_t>(&NativeDoorArcade);}\n return original;',1)
  original_root=Path('/Users/kelinls/code/github/isaac mod');nro=next(original_root.glob('The Binding*/Program #0/1/.nro/Repentance.nro')).read_bytes()
  guards='\n'.join('const unsigned char doorGuard'+str(i)+'[]={'+','.join(map(str,nro[offset:offset+16]))+'};std::memcpy(g_ModuleBytes.data()+'+hex(offset)+',doorGuard'+str(i)+',16);' for i,offset in enumerate((0x3820f4,0x386038)))
  source=source.replace(' FROZEN_GUARDS',' FROZEN_GUARDS\n'+guards,1)
  source=source.replace('assert(openCalls==2&&lastOriginal==g_EngineBase+0x385894);','assert(openCalls==2&&lastOriginal==g_EngineBase+0x385894);Run(L,"assert(select(\'#\',door:Close(false))==0);assert(select(\'#\',door:Close(true))==0);assert(door:IsTargetRoomArcade()==true and door:IsTargetRoomArcade()==false)");assert(!forceSeen[0]&&forceSeen[1]&&openCalls==6&&lastOriginal==g_EngineBase+0x386038);',1)
  source=source.replace('Unchanged(L,"pcall(door.Open,door)");','Unchanged(L,"assert(not pcall(door.Open,door));assert(not pcall(door.Close,door,false));assert(not pcall(door.IsTargetRoomArcade,door))");',1)
  import os
  old=os.environ.get('ISAAC_REFERENCE_ARTIFACT_PREFIX');os.environ['ISAAC_REFERENCE_ARTIFACT_PREFIX']='main-live-door'
  cls.addClassCleanup(lambda:os.environ.pop('ISAAC_REFERENCE_ARTIFACT_PREFIX',None) if old is None else os.environ.__setitem__('ISAAC_REFERENCE_ARTIFACT_PREFIX',old))
  with mock.patch.object(original,'MAIN',source):super().setUpClass()
 def test_reference_and_world_field_native_contracts(self):
  r=subprocess.run([str(self.binary),'door_open'],capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
