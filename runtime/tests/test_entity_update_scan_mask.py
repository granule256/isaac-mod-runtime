"""Render listeners must not request an update-phase entity traversal."""
from pathlib import Path
import re
import subprocess
import tempfile
import unittest
from unittest import mock

from . import test_lua_entity_query as fixture
from . import test_support
from .test_lua_api_method_lookup_cost import function

ROOT = Path(__file__).resolve().parents[2]


class EntityUpdateScanMaskTests(unittest.TestCase):
    def test_production_masks_and_effect_dispatch_keep_phases_separate(self):
        source = (ROOT / 'runtime/source/lua_runtime.cpp').read_text()
        # Accept the old name so the regression first fails on behavior.
        predicate = ('AnyEntityUpdateFamilyRegistered' if
                     'bool AnyEntityUpdateFamilyRegistered(' in source else
                     'AnyEntityFamilyRegistered')
        body = function(source, 'struct RegisteredCallbackMask {') + ';\n'
        body += function(source, f'[[nodiscard]] bool {predicate}(')
        body += function(source, '[[nodiscard]] bool AnyEntityRenderFamilyRegistered(')
        body += function(source, 'struct EntityEventScan {') + ';\n'
        for family in ('Npc', 'Familiar', 'Tear', 'Projectile', 'Laser', 'Knife', 'Bomb', 'Pickup'):
            body += f'void Dispatch{family}EntityEvents(EntityEventScan*,std::uintptr_t,std::int64_t){{}}\n'
        body += function(source, 'void DispatchEffectEntityEvents(')
        body += function(source, 'void OnEntityEvent(')
        prefix = r'''
#include "domain/callback/callback_descriptor.hpp"
#include <cstdint>
#include <cstdio>
unsigned classifications{},updateCalls{},renderCalls{};int g_CallbackRegistry{};
struct LuaCallbackInvoker {
 static LuaCallbackInvoker ForEntity(std::uintptr_t){return {};}
 static LuaCallbackInvoker ForEntityWithVector(std::uintptr_t,float,float){return {};}
};
namespace isaac::runtime {
std::uint64_t NativeRoomLoadStartGeneration(){return 0;}
std::uint64_t NativeLevelInitGeneration(){return 0;}
enum class CallbackEntityClass {None,Npc,Player,Pickup,Familiar,Tear,Projectile,Laser,Knife,Bomb,Effect};
CallbackEntityClass ClassifyCallbackEntity(std::uintptr_t,std::int64_t*p){++classifications;*p=7;return CallbackEntityClass::Effect;}
struct CallbackDispatcher {
 CallbackDispatcher(int&,LuaCallbackInvoker&){}
 int DispatchFiltered(unsigned id,ThreadAffinity,std::int64_t){
  if(id==kCallbackPostEffectUpdate)++updateCalls;
  else if(id==kCallbackPostEffectRender)++renderCalls;
  else return 1;return 0;
 }
};
}
'''
        main = r'''
void Add(RegisteredCallbackMask&mask,isaac::runtime::CallbackId id){
 if(id<64)mask.low|=1ULL<<id;else mask.high|=1ULL<<(id-64);
}
int main(){
 using namespace isaac::runtime;
 const CallbackId renders[]={kCallbackPostFamiliarRender,kCallbackPostPlayerRender,
  kCallbackPostPickupRender,kCallbackPostTearRender,kCallbackPostProjectileRender,
  kCallbackPostLaserRender,kCallbackPostKnifeRender,kCallbackPostEffectRender,kCallbackPostBombRender};
 for(auto id:renders){RegisteredCallbackMask mask{};Add(mask,id);
  if(UPDATE_PREDICATE(mask)){
   std::fprintf(stderr,"render-only callback %u requests an update scan\n",unsigned(id));return 1;
  }
  if(!AnyEntityRenderFamilyRegistered(mask))return 2;
 }
 const CallbackId updates[]={kCallbackPostPeffectUpdate,kCallbackFamiliarUpdate,kCallbackFamiliarInit,
  kCallbackPostNpcInit,kCallbackPostPlayerUpdate,kCallbackPostTearUpdate,kCallbackPostProjectileInit,
  kCallbackPostLaserInit,kCallbackPostLaserUpdate,kCallbackPostKnifeInit,kCallbackPostKnifeUpdate,
  kCallbackPostEffectUpdate,kCallbackPostBombInit,kCallbackPostBombUpdate,kCallbackPostPickupInit,
  kCallbackPostPickupUpdate,kCallbackPostPlayerInit};
 for(auto id:updates){RegisteredCallbackMask mask{};Add(mask,id);
  if(!UPDATE_PREDICATE(mask)){
   std::fprintf(stderr,"update/init callback %u lost its polling scan\n",unsigned(id));return 3;
  }
  if(AnyEntityRenderFamilyRegistered(mask))return 4;
 }
 EntityEventScan scan{};
 if(UPDATE_PREDICATE(scan.registered)||AnyEntityRenderFamilyRegistered(scan.registered))return 5;
 Add(scan.registered,kCallbackPostEffectRender);
 if(UPDATE_PREDICATE(scan.registered))OnEntityEvent(&scan,1);
 if(classifications||updateCalls||renderCalls)return 6;
 scan.renderPhase=true;
 if(AnyEntityRenderFamilyRegistered(scan.registered))OnEntityEvent(&scan,1);
 if(classifications!=1||updateCalls||renderCalls!=1)return 7;
 Add(scan.registered,kCallbackPostEffectUpdate);scan.renderPhase=false;
 if(UPDATE_PREDICATE(scan.registered))OnEntityEvent(&scan,1);
 scan.renderPhase=true;
 if(AnyEntityRenderFamilyRegistered(scan.registered))OnEntityEvent(&scan,1);
 if(classifications!=3||updateCalls!=1||renderCalls!=2)return 8;
 std::puts("PASS nine render families skip updates; polling init/update and mixed effects retained");
}
'''.replace('UPDATE_PREDICATE', predicate)
        with tempfile.TemporaryDirectory(prefix='entity-update-mask-') as tmp:
            work = Path(tmp)
            cpp = work / 'check.cpp'
            cpp.write_text(prefix + body + main)
            result = subprocess.run(['c++', '-std=c++17', '-I' + str(ROOT / 'runtime/src'),
                                     str(cpp), '-o', str(work / 'check')], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            result = subprocess.run([str(work / 'check')], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


MAIN = r'''
#include <cassert>
static unsigned nativeFrame=10,roomVisits{},playerVisits{};
extern "C" void UpdateMaskVisitRoom(){++roomVisits;}
extern "C" void UpdateMaskVisitPlayer(){++playerVisits;}
GameRoomObservation ReadGameLocationKey(uintptr_t,GameLocationKey*out){
 *out={84,0,1,0};return GameRoomObservation::Success;
}
GameRoomObservation ReadGameRenderOffset(uintptr_t,GameRenderOffset*out){
 out->x=1;out->y=2;return GameRoomObservation::Success;
}
static bool Snapshot(isaac::runtime::ManagedUpdateSnapshot*out)noexcept{
 *out={AddressOf(g_GameBytes),nativeFrame};return true;
}
static double Number(const char*name){
 double out{};assert(LuaRuntime::ReadLuaGlobalNumber(name,&out));return out;
}
int main(int argc,char**argv){
 assert(argc==2);const std::string mode=argv[1];
 static_cast<void>(kScriptTemplate);static_cast<void>(&HarnessHasCollectible);
 static_cast<void>(&BuildPrelude);static_cast<void>(&ExpectNumber);
 CreateBlocks();FillEntities();PublishLists();PublishGame();PublishEntityList(g_RoomBytes,true);
 LuaRuntime::ObserveGameThread();LuaRuntime::SetEngineModuleBase(g_EngineBase);
 LuaRuntime::SetGameBindings(g_EngineBase+kGameOwnerGlobalSlotOffset,0);
 std::string script="updates=0;renders=0\n";
 if(mode!="none")script+=R"lua(
 local m=RegisterMod('render listener',1)
 m:AddCallback(56,function(_,e,offset)assert(e.Variant==7 and offset.X==1 and offset.Y==2);renders=renders+1 end,7)
 )lua";
 if(mode=="mixed")script+="m:AddCallback(55,function(_,e)assert(e.Variant==7);updates=updates+1 end,7)\n";
 assert(LuaRuntime::InitializeFromBuffer(script.data(),script.size(),"@update-mask.lua")==LuaRuntime::LuaInitResult::Success);
 isaac::runtime::SetManagedUpdateSnapshotReaderForTest(Snapshot);
 roomVisits=playerVisits=0;
 LuaRuntime::DispatchPostUpdate();
 const unsigned expected=mode=="mixed"?1:0;
 if(roomVisits!=expected||playerVisits!=expected){
  std::fprintf(stderr,"%s update traversals: room=%u player=%u expected=%u\n",mode.c_str(),roomVisits,playerVisits,expected);return 1;
 }
 assert(Number("updates")==expected&&Number("renders")==0);
 LuaRuntime::DispatchPostRender(0x1234);
 const unsigned rendered=mode=="none"?0:1;
 assert(Number("updates")==expected&&Number("renders")==rendered);
 assert(roomVisits==expected+rendered&&playerVisits==expected+rendered);
 if(LuaRuntime::TakeCallbackError()){
  char error[2048]{};static_cast<void>(LuaRuntime::CopyLastLuaErrorText(error,sizeof(error)));
  std::fprintf(stderr,"%s\n",error);return 2;
 }
 std::printf("PASS %s: update visits=%u, effect renders=%u\n",mode.c_str(),expected,rendered);
}
'''


class EntityUpdateScanIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='entity-update-scan-')
        work = Path(cls.tmp.name)
        prefix = fixture.HARNESS.split('int main(', 1)[0]
        prefix = re.sub(r'namespace GameFileReader \{\nTextReadResult[\s\S]*?\n\}\n\}',
                        '', prefix, count=1)
        api = ROOT / 'runtime/src/interfaces/lua/isaac_api.cpp'
        api_text = api.read_text()
        for name, hook in (('VisitRoomEntities', 'UpdateMaskVisitRoom'),
                           ('VisitPlayerEntities', 'UpdateMaskVisitPlayer')):
            signature = f'void {name}(EntityVisitFn visit, void* context) noexcept {{'
            assert api_text.count(signature) == 1
            api_text = api_text.replace(signature, signature + f'\n    {hook}();')
        api_copy = work / 'api_update_scan.cpp'
        api_copy.write_text('extern "C" void UpdateMaskVisitRoom();\n'
                            'extern "C" void UpdateMaskVisitPlayer();\n' + api_text)
        original = test_support.layered_lua_runtime_sources

        def sources(root):
            return [api_copy if p.resolve() == api.resolve() else p for p in original(root)]

        flags = tuple(f for f in test_support.HARNESS_COMPILE_FLAGS
                      if not f.startswith('-DEXL_DIAGNOSTIC_STAGE='))
        with mock.patch.object(test_support, 'layered_lua_runtime_sources', side_effect=sources), \
                mock.patch.object(test_support, 'HARNESS_COMPILE_FLAGS', flags):
            cls.binary = test_support.build_lua_harness(
                source_root=fixture.SOURCE, workdir=work, harness_source=prefix + MAIN)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_update_entry_skips_render_only_and_empty_registries(self):
        for mode in ('render', 'none', 'mixed'):
            with self.subTest(mode=mode):
                result = subprocess.run([str(self.binary), mode], capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
