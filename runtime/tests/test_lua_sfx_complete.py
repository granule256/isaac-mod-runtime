"""剩余七个音效接口必须真调用对应入口并正确传参。"""
import subprocess
import tempfile
import unittest
from pathlib import Path
from .test_support import build_lua_harness
from .test_lua_batch408_sfx_play_real import HARNESS, SOURCE

EXTRA = r'''
int calls = 0;
void* receiver = nullptr;
int soundId = 0;
float arg0 = 0, arg1 = 0;
void FakePair(void* self, int id, float value) { ++calls; receiver=self; soundId=id; arg0=value; }
void FakeSingle(void* self, int id) { ++calls; receiver=self; soundId=id; }
void FakeNone(void* self) { ++calls; receiver=self; }
void FakeAmbient(void* self, int id, float volume, float pitch) { ++calls; receiver=self; soundId=id; arg0=volume; arg1=pitch; }
float FakeVolume(void* self, int id) { ++calls; receiver=self; soundId=id; return 0.625F; }
'''

class SfxCompleteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="isaac-sfx-complete-")
        prelude = HARNESS[:HARNESS.index("int main(int argc, char** argv)")].replace("void FakeSfxPlay", "[[maybe_unused]] void FakeSfxPlay").replace("float BitsToFloat", "[[maybe_unused]] float BitsToFloat")
        main = r'''
int main(int argc, char** argv) {
 if (argc != 2) return 90;
 const char* name=argv[1];
 std::uintptr_t fn=0, offset=0;
 if (!std::strcmp(name,"AdjustPitch")) {fn=reinterpret_cast<std::uintptr_t>(&FakePair); offset=kSoundEffectsAdjustPitchOffset;}
 if (!std::strcmp(name,"AdjustVolume")) {fn=reinterpret_cast<std::uintptr_t>(&FakePair); offset=kSoundEffectsAdjustVolumeOffset;}
 if (!std::strcmp(name,"Preload")) {fn=reinterpret_cast<std::uintptr_t>(&FakeSingle); offset=kSoundEffectsPreloadOffset;}
 if (!std::strcmp(name,"Stop")) {fn=reinterpret_cast<std::uintptr_t>(&FakeSingle); offset=kSoundEffectsStopOffset;}
 if (!std::strcmp(name,"StopLoopingSounds")) {fn=reinterpret_cast<std::uintptr_t>(&FakeNone); offset=kSoundEffectsStopLoopingSoundsOffset;}
 if (!std::strcmp(name,"SetAmbientSound")) {fn=reinterpret_cast<std::uintptr_t>(&FakeAmbient); offset=kSoundEffectsSetAmbientSoundOffset;}
 if (!std::strcmp(name,"GetAmbientSoundVolume")) {fn=reinterpret_cast<std::uintptr_t>(&FakeVolume); offset=kSoundEffectsGetAmbientSoundVolumeOffset;}
 if (!fn) return 91;
 LuaRuntime::SetEngineModuleBase(fn-offset);
 char script[1024];
 const char* args=!std::strcmp(name,"StopLoopingSounds") ? "" : "23";
 if (!std::strcmp(name,"AdjustPitch") || !std::strcmp(name,"AdjustVolume")) args="23,0.375";
 if (!std::strcmp(name,"SetAmbientSound")) args="23,0.375,1.25";
 const char* prefix=!std::strcmp(name,"GetAmbientSoundVolume") ? "assert(" : "";
 const char* suffix=!std::strcmp(name,"GetAmbientSoundVolume") ? "==0.625)" : "";
 std::snprintf(script,sizeof(script),"local m=RegisterMod('Sfx',1); m:AddCallback(ModCallbacks.MC_POST_RENDER,function() %sSFXManager():%s(%s)%s end)",prefix,name,args,suffix);
 if (LuaRuntime::InitializeFromBuffer(script,std::strlen(script),"@sfx.lua") != LuaRuntime::LuaInitResult::Success) return 1;
 LuaRuntime::DispatchPostRender(reinterpret_cast<std::uintptr_t>(&g_Manager));
 if (LuaRuntime::TakeCallbackError()) return 2;
 if (calls!=1 || reinterpret_cast<std::uintptr_t>(receiver)!=ExpectedSoundEffects()) return 3;
 if (std::strcmp(name,"StopLoopingSounds") && soundId!=23) return 4;
 if ((!std::strcmp(name,"AdjustPitch") || !std::strcmp(name,"AdjustVolume") || !std::strcmp(name,"SetAmbientSound")) && !Near(arg0,0.375F)) return 5;
 if (!std::strcmp(name,"SetAmbientSound") && !Near(arg1,1.25F)) return 6;
 return 0;
}
'''
        cls.binary=build_lua_harness(source_root=SOURCE,workdir=Path(cls.temp.name),harness_source='#include <cstdio>\n'+prelude+EXTRA+main)
    @classmethod
    def tearDownClass(cls): cls.temp.cleanup()
    def test_native_receivers_and_arguments(self):
        for name in ('AdjustPitch','AdjustVolume','GetAmbientSoundVolume','Preload','SetAmbientSound','Stop','StopLoopingSounds'):
            with self.subTest(method=name):
                result=subprocess.run([str(self.binary),name],capture_output=True,text=True)
                self.assertEqual(result.returncode,0,result.stdout+result.stderr+f"exit={result.returncode}")

if __name__ == '__main__': unittest.main()
