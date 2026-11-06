"""Real Lua Entity.Update binding: post callbacks per explicit update, not per frame.

The native trampoline records receiver/target on the host. NPC AI and projectile
callbacks are invoked separately to represent their native hooks; they must not
also be dispatched by the generic Entity.Update binding.
"""
from pathlib import Path
import subprocess
import tempfile
import unittest
from .test_lua_batch319_entity_virtual import HARNESS as VTABLE_HARNESS, SOURCE
from .test_support import build_lua_harness

PREFIX = VTABLE_HARNESS[:VTABLE_HARNESS.index('int main(')]
MAIN = r'''
#include "interfaces/lua/isaac_api.hpp"
#include "interfaces/lua/rplus_extended_fields_guards.hpp"
#include <cassert>
// This fixture has no pause thunk. Override the common weak "unreadable" seam
// exactly as the ordinary frame-update harness does; do not change real gates.
GameIsPausedObservation ObserveGameIsPaused(uintptr_t,uintptr_t){return GameIsPausedObservation::ThunkUnavailable;}
static unsigned nativeFrame=10;
static bool Snapshot(isaac::runtime::ManagedUpdateSnapshot*out)noexcept{
 out->game=AddressOf(g_GameBytes);out->frame=nativeFrame;return true;
}
static double Number(const char*name){double n{};assert(LuaRuntime::ReadLuaGlobalNumber(name,&n));return n;}
static void Check(){if(LuaRuntime::TakeCallbackError()){char e[2048]{};static_cast<void>(LuaRuntime::CopyLastLuaErrorText(e,sizeof(e)));std::fprintf(stderr,"%s\n",e);std::abort();}}
int main(int argc,char**argv){
 assert(argc==2);const std::string mode=argv[1];PublishFakeWorld(mode=="empty",false);
 namespace E=isaac::runtime::extended_fields;
 std::memcpy(g_ModuleBytes.data()+E::kEntity0Entry,E::kEntity0Guard.data(),E::kEntity0Guard.size());
 std::memcpy(g_ModuleBytes.data()+E::kEntity1Entry,E::kEntity1Guard.data(),E::kEntity1Guard.size());
 std::memcpy(g_ModuleBytes.data()+E::kEntity2Entry,E::kEntity2Guard.data(),E::kEntity2Guard.size());
 // No native pause routine exists in this host fixture. The old319 sentinel
 // is deliberately not published as a callable pause address.
 LuaRuntime::SetGameBindings(AddressOf(g_OwnerSlotBytes),0);LuaRuntime::ObserveGameThread();
 unsigned type=1,event=31,filter=0;bool parent=false;
 if(mode=="npc"){type=20;event=0;filter=20;parent=true;}
 if(mode=="tear"){type=2;event=40;filter=2;parent=true;}
 if(mode=="familiar"){type=3;event=6;filter=2;parent=true;}
 if(mode=="bomb"){type=4;event=58;filter=2;parent=true;}
 if(mode=="pickup"){type=5;event=35;filter=2;parent=true;}
 if(mode=="slot"){type=6;event=0;filter=6;parent=true;}
 if(mode=="laser"){type=7;event=48;filter=2;parent=true;}
 if(mode=="knife"){type=8;event=51;filter=4;parent=true;}
 if(mode=="projectile"){type=9;event=44;filter=2;parent=true;}
 if(mode=="effect"){type=1000;event=55;filter=2;parent=true;}
 if(parent){
  auto vt=kVtableBOffset;
  if(type==3)vt=kEntityFamiliarVtableOffset;
  if(type==5)vt=kEntityPickupVtableOffset;
  WriteAt<std::uintptr_t>(g_ParentBytes,0,g_EngineBase+vt);
  WriteAt<std::uint32_t>(g_ParentBytes,kEntityTypeOffset,type);
  WriteAt<std::uint32_t>(g_ParentBytes,kEntityVariantOffset,2);
  WriteAt<std::uint32_t>(g_ParentBytes,kEntitySubTypeOffset,4);
  SetVtableSlot(vt,4,0x5E6F0004);
 }
 std::string script="local m=RegisterMod('explicit update',1);local p=Isaac.GetPlayer(0);local e=";
 script+=parent?"p.Parent\n":"p\n";
 script+="calls=0;wrong=0;inits=0;regular=0\n";
 script+="m:AddCallback("+std::to_string(event)+",function(_,q)assert(GetPtrHash(q)==GetPtrHash(e));calls=calls+1;";
 if(mode=="nested")script+="if calls==1 then e:Update()end;";
 script+="end,"+std::to_string(filter)+")\n";
 script+="m:AddCallback("+std::to_string(event)+",function()wrong=wrong+1 end,999)\n";
 script+="m:AddCallback(9,function()inits=inits+1 end)\n";
 if(mode=="automatic"){
  script+="m:AddCallback(1,function()regular=regular+1;if regular==1 then e:Update();e:Update()end end)\n";
 }else if(mode=="twice")script+="e:Update();e:Update()\n";
 else script+="e:Update()\n";
 const auto result=LuaRuntime::InitializeFromBuffer(script.data(),script.size(),"@manual-entity-update.lua");
 if(result!=LuaRuntime::LuaInitResult::Success){char e[2048]{};static_cast<void>(LuaRuntime::CopyLastLuaErrorText(e,sizeof(e)));std::fprintf(stderr,"%s\n",e);return 2;}
 if(mode=="automatic"){
  isaac::runtime::SetManagedUpdateSnapshotReaderForTest(Snapshot);
  LuaRuntime::DispatchPostUpdate();Check();assert(Number("calls")==3&&Number("regular")==1);
  LuaRuntime::DispatchPostUpdate();Check();assert(Number("calls")==3&&Number("regular")==1);
  ++nativeFrame;LuaRuntime::DispatchPostUpdate();Check();assert(Number("calls")==4&&Number("regular")==2);
 }else if(mode=="projectile"||mode=="npc"){
  assert(Number("calls")==0); // host native stub has not reached the real tail
  if(mode=="npc")LuaRuntime::DispatchPostNpcUpdate(AddressOf(g_ParentBytes));
  else LuaRuntime::DispatchPostProjectileUpdate(AddressOf(g_ParentBytes));
  Check();assert(Number("calls")==1);
 }else{
  const double expected=(mode=="slot"||mode=="empty")?0:(mode=="twice"||mode=="nested")?2:1;
  if(Number("calls")!=expected){std::fprintf(stderr,"manual callback count %g expected %g mode=%s\n",Number("calls"),expected,mode.c_str());return 3;}
 }
 assert(Number("wrong")==0&&Number("inits")==((mode=="automatic")?1:0));
 const auto expectedNative=(mode=="empty")?0U:(mode=="twice"||mode=="nested"||mode=="automatic")?2U:1U;
 assert(g_HostEngineCallTrampolineCalls==expectedNative);
 std::printf("PASS %s callbacks=%g native=%u\n",mode.c_str(),Number("calls"),g_HostEngineCallTrampolineCalls);
}
'''


class EntityManualUpdateCallbacks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='manual-entity-update-')
        cls.binary = build_lua_harness(source_root=SOURCE, workdir=Path(cls.tmp.name),
                                      harness_source=PREFIX + MAIN)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def check_mode(self, mode):
        r = subprocess.run([str(self.binary), mode], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_twice_in_one_frame_and_bounded_recursion(self):
        for mode in ('player', 'twice', 'nested'):
            with self.subTest(mode=mode): self.check_mode(mode)

    def test_entity_families_and_filters(self):
        for mode in ('npc', 'tear', 'familiar', 'bomb', 'pickup', 'laser', 'knife', 'effect'):
            with self.subTest(mode=mode): self.check_mode(mode)

    def test_slot_missing_native_target_and_existing_projectile_tail(self):
        for mode in ('slot', 'empty', 'projectile'):
            with self.subTest(mode=mode): self.check_mode(mode)

    def test_automatic_frame_dedup_does_not_suppress_manual_updates(self):
        self.check_mode('automatic')
