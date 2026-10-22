"""rewind缺失分派的离线复现：控制台入口必须执行原版回退与重载链。"""
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

HARNESS = r'''
#include "infrastructure/console/console_bridge.hpp"
#if __has_include("infrastructure/console/rewind_command.hpp")
#define HAS_REWIND 1
#include "infrastructure/console/rewind_command.hpp"
#endif
#include <cstdio>
#include <cstring>
#include <vector>
#include <string>
namespace c = isaac::runtime::console;
namespace em = isaac::runtime::engine_memory;
std::vector<unsigned char> module(0xAAC700), game(0x350000), manager(0x1D8000);
std::uintptr_t gamePtr, managerPtr, player=0x1234;
std::string order;
int nativeCalls=0, room=7, coins=5;
bool writable=true, snapshot=true, fadeWritable=true;
void Ctor(void*) {}
void Init(void*) {}
void Native(void*,const void*,void*,void*) { ++nativeCalls; }
void Restore(void* self,void* actor) {
 if (self!=game.data() || actor!=nullptr) std::abort();
 if(game[0x2F0058]!=0)std::abort();
 order+='R'; if(snapshot) {room=6; coins=10;game[0x25D40]=0xA5;}
}
void Restart(void* self,const void* seeds,bool a,bool b) {
 if(self!=manager.data() || seeds!=game.data()+0x25D40 || a || b) std::abort();
 if(game[0x2F0058]!=0)std::abort();
 order+='S';manager[0x1D7309]=0;manager[0x1D74B0]=0;manager[0x1D7318]=0xCC;
}
void* Copy(void* to,const void* from) {
 if(to!=manager.data()+0x1D7318 || from!=game.data()+0x25D40) std::abort();
 if(game[0x2F0058]!=0 || manager[0x1D7309]!=0 || manager[0x1D74B0]!=0)std::abort();
 order+='C';std::memcpy(to,from,0x70);return to;
}
bool Readable(std::uintptr_t a,std::size_t n) {return a!=0 && n!=0;}
bool Writable(std::uintptr_t a,std::size_t n) {return writable && Readable(a,n) && (fadeWritable || a!=em::AddressOf(game.data())+0x2F0058);}
template<class T> void Put(std::vector<unsigned char>& v,std::size_t off,T value) {
 std::memcpy(v.data()+off,&value,sizeof(value));
}
int main(int argc,char**argv) {
 if(argc!=2)return 90;
 const std::string scenario=argv[1];
 gamePtr=em::AddressOf(game.data());managerPtr=em::AddressOf(manager.data());
 if(scenario=="no-manager")managerPtr=0;
 Put(module,0xAAC698,em::AddressOf(&gamePtr));
 Put(module,0xAAC648,em::AddressOf(&managerPtr));
 Put(game,0x25C50,em::AddressOf(&player));
 Put(game,0x25C58,em::AddressOf(&player)+sizeof(player));
 if(scenario=="no-player")player=0;
 if(scenario=="disabled")c::Storage().switchEnabled=false;
 if(scenario=="readonly")writable=false;
 if(scenario=="fade-readonly")fadeWritable=false;
 game[0x2F0057]=0xA7;game[0x2F0059]=0xA9;game[0x2F005C]=0xAC;
 if(scenario=="no-snapshot")snapshot=false;
 game[0x25D40]=0x55;
#ifdef HAS_REWIND
 c::RewindEntries re{&Restore,&Restart,&Copy};
 if(scenario=="missing-binding")re.copySeeds=nullptr;
 if(scenario=="missing-restore")re.restore=nullptr;
 if(scenario=="missing-restart")re.restart=nullptr;
 c::SetRewindHostBindings(re,&Readable,&Writable,scenario!="missing-fade-layout");
#endif
 c::EngineEntries entries{};entries.consoleCtor=&Ctor;entries.consoleInit=&Init;entries.runCommand=&Native;
 const char* cmd="rewind";
 if(scenario=="ordinary")cmd="spawn 5.100.12";
 if(scenario=="prefix")cmd="rewindx";
 if(scenario=="args")cmd="rewind ignored";
 if(scenario=="leading-space")cmd="  rewind ";
 if(scenario=="case")cmd="Rewind";
 if(scenario=="tab")cmd="rewind\t";
 const auto out=c::ExecuteCommand(entries,em::AddressOf(module.data()),cmd,std::strlen(cmd));
 const bool success=scenario=="rewind" || scenario=="args" || scenario=="leading-space" || scenario=="no-snapshot";
 if(success) {
  if(room!=(snapshot?6:7) || coins!=(snapshot?10:5) || order!="RSC" || nativeCalls!=0 ||
    manager[0x1D7318]!=(snapshot?0xA5:0x55) ||
    manager[0x1D7309]!=1 || manager[0x1D74B0]!=1 || game[0x2F0058]!=1 || out.status!=c::ExecStatus::kOk) {
   std::printf("FAIL room=%d coins=%d order=%s native=%d load=%u save=%u status=%u\n",room,coins,order.c_str(),nativeCalls,manager[0x1D7309],manager[0x1D74B0],unsigned(out.status));return 1;
  }
 } else if(scenario=="ordinary" || scenario=="prefix" || scenario=="case" || scenario=="tab") {
  if(nativeCalls!=1 || !order.empty() || room!=7)return 2;
 } else {
  if(!order.empty() || nativeCalls!=0 || room!=7 || coins!=5 || out.status==c::ExecStatus::kOk)return 3;
 }
 if(game[0x2F0057]!=0xA7 || game[0x2F0059]!=0xA9 || game[0x2F005C]!=0xAC)return 4;
 if(!success && game[0x2F0058]!=0)return 5;
 std::puts("OK");return 0;
}
'''


class ConsoleRewindTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="console-rewind-")
        cls.addClassCleanup(cls.tmp.cleanup)
        source = Path(cls.tmp.name) / "driver.cpp"
        source.write_text(HARNESS)
        cls.exe = source.with_suffix("")
        r = subprocess.run(["c++", "-std=c++23", "-Wall", "-Wextra", "-Werror",
            "-I", str(ROOT / "runtime/src"), "-I", str(ROOT / "runtime/source"),
            str(source), "-o", str(cls.exe)], text=True, capture_output=True)
        if r.returncode:
            raise AssertionError(r.stdout + r.stderr)

    def test_rewind_restores_state_and_requests_reload_through_shared_console_entry(self):
        for scenario in ("rewind", "args", "leading-space", "no-snapshot", "ordinary",
                         "prefix", "case", "tab", "missing-binding", "missing-restore",
                         "missing-restart", "missing-fade-layout", "readonly", "fade-readonly", "disabled", "no-player", "no-manager"):
            with self.subTest(scenario=scenario):
                r = subprocess.run([str(self.exe), scenario], text=True, capture_output=True)
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()


class RewindLayoutGuardTests(unittest.TestCase):
    def test_real_consumer_guards_reject_changed_fadein_or_update(self):
        source=r'''#include "infrastructure/console/rewind_command.hpp"
#include <vector>
#include <cassert>
using namespace isaac::runtime;
int main(){
 std::vector<unsigned char> image(kGameModuleRangeCheckSize);auto base=engine_memory::AddressOf(image.data());
 auto set=[&](auto offset,const auto& bytes){std::memcpy(image.data()+offset,bytes.data(),bytes.size());};
 set(kGameRestoreGlowingHourGlassStateOffset,kGameRestoreGlowingHourGlassStateExpectedBytes);
 set(kManagerConsoleRestartGameOffset,kManagerConsoleRestartGameExpectedBytes);
 set(kConsoleSeedsAssignOffset,kConsoleSeedsAssignExpectedBytes);
 set(kApi200GameFadeinOffset,kApi200GameFadeinExpectedBytes);
 const std::array<unsigned char,16> update={0x56,0xf3,0x40,0x39,0x96,0x01,0x00,0x35,0x05,0x7a,0x0c,0x94,0xc8,0x3a,0x00,0xf0};set(0x351f44,update);
 assert(console::ResolveRewindEntries(base).Ready());
 for(auto offset:{kApi200GameFadeinOffset,std::uintptr_t{0x351f44}})for(unsigned i=0;i<16;++i){image[offset+i]^=1;assert(!console::ResolveRewindEntries(base).Ready());image[offset+i]^=1;}
}
'''
        with tempfile.TemporaryDirectory(prefix='rewind-layout-')as tmp:
            p=Path(tmp);(p/'test.cpp').write_text(source)
            r=subprocess.run(['c++','-std=c++23','-Wall','-Wextra','-Werror','-I',str(ROOT/'runtime/src'),'-I',str(ROOT/'runtime/source'),str(p/'test.cpp'),'-o',str(p/'test')],capture_output=True,text=True)
            self.assertEqual(r.returncode,0,r.stdout+r.stderr)
            r=subprocess.run([str(p/'test')],capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
