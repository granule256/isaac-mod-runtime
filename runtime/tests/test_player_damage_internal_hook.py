"""玩家中段桥：真实C++参数、续接、嵌套作用域及安装守卫；不执行引擎伤害。"""
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "runtime/source"
UNITS = ROOT / "runtime/src"
HEADER = SOURCE / "player_damage_internal_hook.hpp"
INSTALLER = UNITS / "infrastructure/internal/player_damage_hook_installer.cpp"


def original_nro():
    for project in (ROOT, *ROOT.parents):
        config = project / "data/local/build-inputs.json"
        if config.is_file():
            return project / json.loads(config.read_text())["nro"]
    return None


NRO = original_nro()

HELPER_DRIVER = r'''
#include "player_damage_internal_hook.hpp"
#include <array>
#include <cassert>
#include <cstring>
#include <type_traits>
using namespace isaac::runtime;
using isaac::runtime::relay::InternalHookContext;
static_assert(!std::is_copy_constructible_v<PlayerDamageCallScope>);
static_assert(!std::is_move_constructible_v<PlayerDamageCallScope>);
static unsigned dispatched{},replayed{},depth{};
static bool cancel{},nativeResult{},nest{};
static std::uintptr_t expectedPlayer=0x12345678,expectedSource=0x87654320,nativePlayer{};
static std::int32_t expectedCountdown=17;
static PlayerDamageNativeBindings native{};
static bool Replay(void* p){++replayed;nativePlayer=reinterpret_cast<std::uintptr_t>(p);return nativeResult;}
static unsigned Flow(bool scope=true,bool mismatched=false,bool invalidStack=false);
static bool Dispatch(std::uintptr_t p,float hp,std::uint64_t flags,std::uintptr_t source,
                     std::int32_t countdown,std::int32_t type){
 ++dispatched;assert(p==expectedPlayer&&source==expectedSource&&countdown==expectedCountdown);
 assert(type==1&&hp==3.0F&&flags==0x10000000003ULL);
 if(nest&&!depth){
  ++depth;expectedCountdown=-91;
  assert(Flow()==(cancel?1U:0U));
  expectedCountdown=17;--depth;
 }
 return cancel;
}
static unsigned Flow(bool scope,bool mismatched,bool invalidStack){
 alignas(16) std::array<unsigned char,0x80> stack{},stackBefore{};
 std::int32_t hp=3;std::memcpy(stack.data()+0x4c,&hp,4);stackBefore=stack;
 InternalHookContext ctx;std::memset(&ctx,0xa5,sizeof(ctx));
 ctx.x[0]=0x11223344;ctx.x[19]=expectedPlayer;ctx.x[20]=0x10000000003ULL;ctx.x[22]=expectedSource;
 ctx.originalSp=invalidStack?UINTPTR_MAX-0x4b:reinterpret_cast<std::uintptr_t>(stack.data());
 float raw=99.25F;std::memcpy(&ctx.q[9].low,&raw,4);
 const auto before=ctx;
 unsigned result{};
 if(scope){PlayerDamageCallScope call(expectedPlayer,mismatched?expectedSource+8:expectedSource,expectedCountdown);
  result=PlayerDamageInternalCallback(ctx,&native);
 }else result=PlayerDamageInternalCallback(ctx,&native);
 auto want=before;
 if(!result)want.x[0]=nativeResult?1:0;
 assert(std::memcmp(&ctx,&want,sizeof(ctx))==0&&stack==stackBefore);
 assert(result<=1);return result;
}
int main(){
 native.tryEndAstralProjection=Replay;native.dispatch=Dispatch;
 for(bool n:{false,true})for(bool c:{false,true}){
  nativeResult=n;cancel=c;dispatched=replayed=0;
  assert(Flow()==(c?1U:0U));assert(dispatched==1&&replayed==(c?0U:1U));
  if(!c)assert(nativePlayer==0x11223344);
 }
 cancel=true;dispatched=replayed=0;
 assert(Flow(false)==0&&dispatched==0&&replayed==1);
 assert(Flow(true,true)==0&&dispatched==0&&replayed==2);
 assert(Flow(true,false,true)==0&&dispatched==0&&replayed==3);
 // 内层作用域不能借用外层countdown；退出后外层必须恢复。
 {PlayerDamageCallScope outer(expectedPlayer,expectedSource,17);
  assert(Flow(true,true)==0&&dispatched==0&&replayed==4);
  alignas(16) std::array<unsigned char,0x80> stack{};std::int32_t hp=3;
  std::memcpy(stack.data()+0x4c,&hp,4);InternalHookContext ctx{};
  ctx.x[19]=expectedPlayer;ctx.x[20]=0x10000000003ULL;ctx.x[22]=expectedSource;
  ctx.originalSp=reinterpret_cast<std::uintptr_t>(stack.data());
  assert(PlayerDamageInternalCallback(ctx,&native)==1&&dispatched==1);
 }
 dispatched=replayed=0;nest=true;
 assert(Flow()==1&&dispatched==2&&replayed==0);
 nest=false;assert(Flow(false)==0&&dispatched==2&&replayed==1);
}
'''

INSTALLER_DRIVER = r'''
#include "infrastructure/internal/player_damage_hook_installer.hpp"
#include "player_damage_internal_hook.hpp"
#include "player_damage_boundary_layout.hpp"
#include <cassert>
#include <cstring>
#include <fstream>
#include <iterator>
#include <string>
#include <vector>
using namespace isaac::runtime;
static std::uintptr_t base{};static unsigned installs{};static bool fail{};
namespace LuaRuntime {
bool DispatchEntityTakeDamage(std::uintptr_t,float,std::uint64_t,std::uintptr_t,std::int32_t,std::int32_t){return false;}
}
namespace isaac::runtime::relay {
InternalHookFailure TryInstallInternalHook(const InternalHookBinding& b,const InternalHookSite& s,std::uintptr_t v){
 ++installs;assert(ValidInternalBinding(b)&&b.callback==PlayerDamageInternalCallback);
 assert(b.resumeCount==2&&b.resumes[0]==base+0x2a4b04&&b.resumes[1]==base+0x2a35e4);
 assert(s.target==base+0x2a4b00&&s.expected==0x940f4eb4&&v==base+0x68ce48);
 assert(s.veneerKind==InternalVeneerKind::Absolute16);
 const auto& n=*static_cast<const PlayerDamageNativeBindings*>(b.user);
 assert(reinterpret_cast<std::uintptr_t>(n.tryEndAstralProjection)==base+0x6785d0);
 assert(n.dispatch==LuaRuntime::DispatchEntityTakeDamage);
 if(fail)return InternalHookFailure::WriteVerifyFailed;
 std::uint32_t branch{};assert(BuildInternalBranch(&branch,s.target,v));
 std::memcpy(reinterpret_cast<void*>(s.target),&branch,4);
 return InternalHookFailure::None;
}
}
int main(int argc,char**argv){
 assert(argc==3);std::ifstream f(argv[1],std::ios::binary);
 std::vector<unsigned char> image((std::istreambuf_iterator<char>(f)),{});assert(image.size()>0x68ce60);
 base=reinterpret_cast<std::uintptr_t>(image.data());
 HookTarget target{};target.base=base;target.codeSize=image.size();target.imageSize=image.size();
 std::memcpy(target.buildId.data(),image.data()+0x40,32);
 const std::string scene=argv[2];
 auto reject=[&](){assert(!TryInstallPlayerDamageBoundary(target)&&installs==0);};
 if(scene=="guards"){
  assert(player_damage_boundary::ImageMatches(image.data(),image.size()));
  for(auto at:{0x2a34d0,0x2a34df,0x2a48d0,0x2a4b00,0x2a4b04,0x2a35e4,0x2a96d4,0x6785d0,0x6785df,0x40}){
   image[at]^=1;reject();image[at]^=1;
  }
  for(unsigned i=0;i<16;++i){image[0x68ce48+i]=1;reject();image[0x68ce48+i]=0;}
  auto size=target.codeSize;target.codeSize=0x68ce57;reject();target.codeSize=size;
  auto build=target.buildId;target.buildId[0]^=1;reject();target.buildId=build;
  target.base=0;reject();target.base=base;
  target.base=UINTPTR_MAX-16;reject();target.base=base;
 }
 if(scene=="failure"){
  fail=true;assert(!TryInstallPlayerDamageBoundary(target)&&installs==1);
  assert(g_PlayerDamageBoundaryInstallState.base==base&&g_PlayerDamageBoundaryInstallState.installed==0);
  assert(g_PlayerDamageBoundaryInstallState.failure==static_cast<unsigned>(relay::InternalHookFailure::WriteVerifyFailed));
  assert(!TryInstallPlayerDamageBoundary(target)&&installs==1);return 0;
 }
 assert(TryInstallPlayerDamageBoundary(target)&&installs==1);
 assert(g_PlayerDamageBoundaryInstallState.base==base&&g_PlayerDamageBoundaryInstallState.installed==1&&g_PlayerDamageBoundaryInstallState.failure==0);
 assert(TryInstallPlayerDamageBoundary(target)&&installs==1);
 auto other=target;other.base+=16;assert(!TryInstallPlayerDamageBoundary(other)&&installs==1);
 assert(TryInstallPlayerDamageBoundary(target)&&installs==1);
}
'''


class PlayerDamageInternalHookTests(unittest.TestCase):
    def test_bridge_and_installer_exist(self):
        self.assertTrue(HEADER.exists(), "玩家中段桥尚未实现")
        self.assertTrue(INSTALLER.exists(), "玩家中段安装器尚未实现")

    def build(self, folder, driver, sources, shim=False):
        folder = Path(folder)
        (folder / "driver.cpp").write_text(driver)
        if shim:
            (folder / "lua_runtime.hpp").write_text(
                "#pragma once\n#include <cstdint>\nnamespace LuaRuntime { bool DispatchEntityTakeDamage(std::uintptr_t,float,std::uint64_t,std::uintptr_t,std::int32_t,std::int32_t); }\n"
            )
        binary = folder / "driver"
        result = subprocess.run(
            ["clang++", "-std=c++20", "-Wall", "-Wextra", "-Werror", "-I", str(folder),
             "-I", str(SOURCE), "-I", str(UNITS), str(folder / "driver.cpp"),
             *map(str, sources), "-o", str(binary)], capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return binary

    def test_real_helper_parameters_cancellation_replay_nested_scope_and_registers(self):
        if not HEADER.exists():
            self.skipTest("等待玩家中段桥")
        with tempfile.TemporaryDirectory(prefix="isaac-player-damage-") as folder:
            binary = self.build(folder, HELPER_DRIVER, [SOURCE / "player_damage_internal_hook.cpp"])
            result = subprocess.run([str(binary)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_real_installer_guards_publication_and_idempotence(self):
        if not INSTALLER.exists():
            self.skipTest("等待玩家中段安装器")
        self.assertTrue(NRO is not None and NRO.is_file(), "缺少固定NS原件，不能伪造函数指纹")
        with tempfile.TemporaryDirectory(prefix="isaac-player-damage-install-") as folder:
            binary = self.build(folder, INSTALLER_DRIVER, [INSTALLER, SOURCE / "player_damage_internal_hook.cpp"], shim=True)
            for scene in ["guards", "failure", "normal"]:
                with self.subTest(scene=scene):
                    result = subprocess.run([str(binary), str(NRO), scene], capture_output=True, text=True)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
