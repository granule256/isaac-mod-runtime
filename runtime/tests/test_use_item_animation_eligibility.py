"""使用真实入口、Lua回调和动画handler验证原始flags/variant决定动画资格。"""
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from . import test_support
from . import test_use_item_rng as rng

ROOT = Path(__file__).resolve().parents[2]
PRE = r'''
#include "infrastructure/relay/entry_relay_binding.hpp"
#include "infrastructure/call/engine_call_access.hpp"
#include "use_item_internal_hook.hpp"
#include "interfaces/lua/isaac_api.hpp"
#include <cassert>
#include <cstring>
unsigned nativeCalls{},animationCalls{};
std::uintptr_t rngBytes{};
bool nativePostprocessed{},cleanStack{};
extern "C" void AnimationEligibilityHost(std::uintptr_t player,std::int32_t item,const char* anim,const char* sprite){
 assert(player==AddressOf(g_PlayerBytes)&&item==1);
 assert(std::strcmp(anim,"UseItem")==0&&std::strcmp(sprite,"PlayerPickupSparkle")==0);
 assert(!nativePostprocessed&&nativeCalls==1);
 std::uint32_t seed{};std::memcpy(&seed,reinterpret_cast<void*>(rngBytes),4);assert(seed==124);
 ++animationCalls;
}
std::uint64_t OriginalUse(void* player,std::uint32_t item,std::uint32_t flags,std::int32_t slot,std::int32_t custom){
 assert(player==g_PlayerBytes.data()&&item==1&&(flags==4||flags==5)&&slot==0&&custom==77);
 ++nativeCalls;
 isaac::runtime::relay::InternalHookContext ctx{};
 ctx.x[27]=reinterpret_cast<std::uintptr_t>(player);ctx.x[20]=1;ctx.x[22]=1;
 ctx.originalSp=ctx.x[27]+0x400;
 // +58被原生道具分支复用；脏数据不能变成NoAnim判据。
 WriteAt<std::uint32_t>(g_PlayerBytes,0x458,cleanStack?0:0x12345678);
 isaac::runtime::UseItemNativeBoundaryBinding binding{true,false};
 isaac::runtime::UseItemNativeBoundaryCallback(ctx,&binding);
 isaac::runtime::UseItemNativeBoundaryCallback(ctx,&binding);
 std::uint32_t seed{};std::memcpy(&seed,reinterpret_cast<void*>(rngBytes),4);assert(seed==124);
 nativePostprocessed=true;++seed;std::memcpy(reinterpret_cast<void*>(rngBytes),&seed,4);
 return (ctx.x[20]<<8)|ctx.x[22];
}
namespace isaac::runtime {std::uintptr_t EntryRelayFallbackEntry(HookId id)noexcept{return id==HookId::UseActiveItem?engine_call::AddressOfFunction(&OriginalUse):0;}}
'''
MAIN = r'''
int main(int argc,char**argv){
 assert(argc==2);const std::string mode=argv[1];assert(mode=="dirty_stack"||mode=="clean_stack"||mode=="boolean_true"||mode=="no_anim"||mode=="nonmain");
 PublishFakeMemory();WriteAt<std::uint8_t>(g_PlayerBytes,kEntityExistsOffset,1);
 WriteAt<std::uint32_t>(g_PlayerBytes,kEntityVariantOffset,mode=="nonmain"?1:0);
 WriteAt<std::uint32_t>(g_PlayerBytes,0x19d4,0);
 LuaRuntime::ObserveGameThread();LuaRuntime::SetGameBindings(AddressOf(g_OwnerSlotBytes),0x2222);
 LuaRuntime::SetRngBindings(reinterpret_cast<std::uintptr_t>(&HostSetSeed),reinterpret_cast<std::uintptr_t>(&HostNext));
 std::vector<unsigned char> vector(32);WriteAt<std::uint32_t>(vector,16,123);rngBytes=AddressOf(vector)+16;
 WriteAt<std::uintptr_t>(g_PlayerBytes,kEntityPlayerCollectibleRngVectorOffset,AddressOf(vector));
 WriteAt<std::uintptr_t>(g_PlayerBytes,kEntityPlayerCollectibleRngVectorOffset+8,AddressOf(vector)+vector.size());
 g_TestRoom.assign(kRoomDoorObjectTableOffset+8*sizeof(std::uintptr_t)+32,0);
 FROZEN_ANIMATION
 cleanStack=mode!="dirty_stack";
 const unsigned flags=mode=="no_anim"?5:4;
 const std::string script="local m=RegisterMod('animation-eligibility',1);m:AddCallback(1,function()end);useCount=0;preCount=0;m:AddCallback(23,function(_,id,r,p,f,s,c)assert(id==1 and f=="+std::to_string(flags)+" and s==0 and c==77 and r:GetSeed()==123);preCount=preCount+1 end);m:AddCallback(3,function(_,id,r,p,f,s,c)assert(id==1 and f=="+std::to_string(flags)+" and s==0 and c==77);assert(r:GetSeed()==123,'callback must precede native postprocessing');useCount=useCount+1;r:Next();return "+(mode=="boolean_true"?"true":"{ShowAnim=true,Remove=false}")+" end)";
 assert(LuaRuntime::InitializeFromBuffer(script.data(),script.size(),"@use-animation-eligibility.lua")==LuaRuntime::LuaInitResult::Success);
 const auto result=EntryRelayUseActiveItemCallback(g_PlayerBytes.data(),1,flags,0,77);
 if(LuaRuntime::TakeCallbackError()){LuaRuntime::LuaErrorHistoryEntryView errors[8]{};const auto count=LuaRuntime::CopyLuaErrorHistory(errors,8);for(std::size_t i=0;i<count;++i)std::printf("%s\n",errors[i].text);return 5;}
 double count{},pre{};assert(LuaRuntime::ReadLuaGlobalNumber("useCount",&count)&&count==1);assert(LuaRuntime::ReadLuaGlobalNumber("preCount",&pre)&&pre==1);
 assert(nativeCalls==1&&nativePostprocessed&&Seed(vector,16)==125&&result==(mode=="boolean_true"?0x101U:1U));
 assert(animationCalls==(mode=="dirty_stack"||mode=="clean_stack"||mode=="boolean_true"?1U:0U));
 assert(isaac::runtime::ActiveUseItemFrame()==nullptr);
}
'''


class UseItemAnimationEligibilityTests(unittest.TestCase):
    def test_original_flags_variant_ignore_reused_stack(self):
        hook = (ROOT / 'runtime/source/hook_manager.cpp').read_text()
        start = hook.index('extern "C" std::uint64_t EntryRelayUseActiveItemCallback(')
        end = hook.index('extern "C" void EntryRelayUseCardCallback', start)
        source = (rng.fixture.HARNESS[:rng.fixture.HARNESS.index('GameRoomObservation ReadCurrentGameRoom(')]
                  + rng.refs.MAIN[:rng.refs.MAIN.index('int main(')] + PRE + hook[start:end] + MAIN)
        nro = next(Path('/Users/kelinls/code/github/isaac mod').glob('The Binding*Afterbirth*/*/1/.nro/Repentance.nro')).read_bytes()
        fixed = nro[0x2dd150:0x2dd160]
        self.assertEqual(len(fixed), 16)
        guard = 'const unsigned char animationGuard[]={' + ','.join(map(str, fixed)) + '};std::memcpy(g_ModuleBytes.data()+0x2dd150,animationGuard,16);'
        source = source.replace('FROZEN_ANIMATION', guard)
        for name in ('CURRENT_TINT', 'CURRENT_SHIFT', 'DEFAULT_TINT', 'SPLAT_TINT'):
            for i, value in enumerate(getattr(rng.fixture, name)):
                source = source.replace(f'{name}_{i}', repr(value))
        for name in ('COLLECTIBLE_COUNT', 'TRINKET_COUNT', 'ENTITY_DEFAULT_COLOR_OFFSET', 'ENTITY_SPLAT_COLOR_OFFSET'):
            source = source.replace(name, str(getattr(rng.fixture, name)))
        original_sources = test_support.layered_lua_runtime_sources
        with tempfile.TemporaryDirectory(prefix='use-animation-eligibility-') as tmp:
            workdir = Path(tmp)
            original_tu = ROOT / 'runtime/src/interfaces/lua/isaac_api.cpp'
            production = original_tu.read_text()
            terminal = 'isaac::runtime::engine_call::AsFunction<AnimateCollectibleFn>(method)'
            self.assertEqual(production.count(terminal), 1)
            declaration = '#include <cstdint>\nextern "C" void AnimationEligibilityHost(std::uintptr_t,std::int32_t,const char*,const char*);\n'
            copied_tu = workdir / 'isaac_api_animation_endpoint.cpp'
            copied_tu.write_text(declaration + production.replace(terminal, 'static_cast<AnimateCollectibleFn>(&AnimationEligibilityHost)'))

            def sources(source_root):
                paths = original_sources(source_root)
                self.assertEqual(sum(p.resolve() == original_tu.resolve() for p in paths), 1)
                return [copied_tu if p.resolve() == original_tu.resolve() else p for p in paths]

            with mock.patch.object(test_support, 'layered_lua_runtime_sources', side_effect=sources):
                binary = test_support.build_lua_harness(source_root=rng.fixture.SOURCE, workdir=workdir,
                                                        harness_source=source)
            for mode in ('dirty_stack', 'clean_stack', 'boolean_true', 'no_anim', 'nonmain'):
                with self.subTest(mode=mode):
                    result = subprocess.run([str(binary), mode], capture_output=True, text=True)
                    print(mode, result.returncode, result.stdout + result.stderr, flush=True)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
