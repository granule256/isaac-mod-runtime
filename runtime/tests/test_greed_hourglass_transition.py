"""实际调用生产转发单元，验证首层贪婪沙漏的错误房规则及守卫。

判据依据（全部可在固定 NRO 上复核，见 `dist/auri-greed-fix-20261026/`）：
`Game::StartRoomTransition` 在 `Animation==12 && Level.Stage==1 && GameStateFlag4==0` 时
固定转 `StartStageTransition(false, 6, nullptr)`（`0x353D08-0x353D40`）；全库 8 个
`StartStageTransition` 调用点里只有这一处是 `(false, 6, nullptr)`。
"""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HARNESS = r'''
#include <array>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include "infrastructure/call/engine_call_access.hpp"
#if __has_include("application/game/greed_hourglass_transition.hpp")
#include "application/game/greed_hourglass_transition.hpp"
#else
namespace isaac::runtime {
using StageTransitionFn=void(*)(void*,bool,int,void*);
using RoomTransitionFn=void(*)(void*,int,int,int,void*,int);
enum class HourglassTransitionResult {Forwarded,Rerouted,StateUnreadable,RoomUnavailable,OriginalUnavailable};
struct HourglassFieldOffsets {std::uintptr_t stage,difficulty,stateFlags,playerBegin,playerEnd;};
HourglassTransitionResult DispatchGreedHourglassTransition(void*g,bool up,int a,void*p,
 StageTransitionFn original,RoomTransitionFn,HourglassFieldOffsets,engine_memory::ReadableCheck){
 if(!original)return HourglassTransitionResult::OriginalUnavailable;
 original(g,up,a,p);return HourglassTransitionResult::Forwarded;
}
}
#endif
using namespace isaac::runtime;
static std::array<std::uint32_t,0x2f0028/4+1> bytes{};
static std::uintptr_t playerSlot[1]={0};
static int reads=0,originalCalls=0,roomCalls=0;
static bool readable=true,difficultyReadable=true;
static void* expectedGame=nullptr;static void* expectedForwardPlayer=nullptr;
static void* expectedRoomPlayer=nullptr;
static bool expectedUp=false;static int expectedAnimation=6;
static bool argsOk=true;
static bool Readable(std::uintptr_t a,std::size_t n){
 ++reads;
 const auto b=engine_memory::AddressOf(bytes.data());
 const auto slot=engine_memory::AddressOf(playerSlot);
 if(a>=slot&&a-slot<=sizeof(playerSlot)&&n<=sizeof(playerSlot)-(a-slot))return readable;
 return readable&&(difficultyReadable||a!=b+0x2f0028)&&a>=b&&a-b<=sizeof(bytes)&&n<=sizeof(bytes)-(a-b);
}
static void Original(void*g,bool up,int a,void*p){++originalCalls;
 argsOk &= g==expectedGame&&up==expectedUp&&a==expectedAnimation&&p==expectedForwardPlayer;}
static void Room(void*g,int idx,int dir,int anim,void*p,int dimension){
 ++roomCalls;
 argsOk &= g==expectedGame&&idx==-2&&dir==-1&&anim==3&&p==expectedRoomPlayer&&dimension==-1;
}
static void Reset(){
 reads=0;originalCalls=0;roomCalls=0;argsOk=true;readable=true;difficultyReadable=true;
 std::memset(bytes.data(),0,sizeof(bytes));
 bytes[0]=1;bytes[0x2f0028/4]=2;
 *reinterpret_cast<std::uintptr_t*>(reinterpret_cast<std::uint8_t*>(bytes.data())+0x25c50)=
  engine_memory::AddressOf(playerSlot);
 *reinterpret_cast<std::uintptr_t*>(reinterpret_cast<std::uint8_t*>(bytes.data())+0x25c58)=
  engine_memory::AddressOf(playerSlot)+sizeof(playerSlot);
}
int main(int argc,char**argv){
 if(argc!=2)return 90;const char* mode=argv[1];
 Reset();
 int playerToken=0;playerSlot[0]=engine_memory::AddressOf(&playerToken);
 auto original=&Original;auto room=&Room;
 expectedGame=bytes.data();expectedForwardPlayer=nullptr;expectedRoomPlayer=&playerToken;
 HourglassTransitionResult expected=HourglassTransitionResult::Forwarded;
 if(!std::strcmp(mode,"greed")||!std::strcmp(mode,"greedier")){
  expected=HourglassTransitionResult::Rerouted;
  if(!std::strcmp(mode,"greedier"))bytes[0x2f0028/4]=3;
 }else if(!std::strcmp(mode,"normal"))bytes[0x2f0028/4]=0;
 else if(!std::strcmp(mode,"hard"))bytes[0x2f0028/4]=1;
 else if(!std::strcmp(mode,"unknown-difficulty"))bytes[0x2f0028/4]=4;
 else if(!std::strcmp(mode,"other-stage"))bytes[0]=2;
 else if(!std::strcmp(mode,"left-starting-room"))
  reinterpret_cast<std::uint8_t*>(bytes.data())[0x26fa50]=0x10;
 else if(!std::strcmp(mode,"mod-call-with-player"))expectedForwardPlayer=&playerToken;
 else if(!std::strcmp(mode,"no-player")){playerSlot[0]=0;expected=HourglassTransitionResult::StateUnreadable;}
 else if(!std::strcmp(mode,"unreadable-difficulty")){difficultyReadable=false;expected=HourglassTransitionResult::StateUnreadable;}
 else if(!std::strcmp(mode,"animation")){expectedAnimation=3;}
 else if(!std::strcmp(mode,"up")){expectedUp=true;}
 else if(!std::strcmp(mode,"unreadable")){readable=false;expected=HourglassTransitionResult::StateUnreadable;}
 else if(!std::strcmp(mode,"room-unavailable")){room=nullptr;expected=HourglassTransitionResult::RoomUnavailable;}
 else if(!std::strcmp(mode,"original-unavailable")){original=nullptr;expected=HourglassTransitionResult::OriginalUnavailable;}
 else return 91;
 const auto result=DispatchGreedHourglassTransition(expectedGame,expectedUp,expectedAnimation,
  expectedForwardPlayer,original,room,
  {0,0x2f0028,0x26fa50,0x25c50,0x25c58},&Readable);
 if(result!=expected){std::fprintf(stderr,"%s: expected decision %d got %d\n",mode,int(expected),int(result));return 1;}
 const int wantOriginal=expected==HourglassTransitionResult::Forwarded?1:0;
 const int wantRoom=expected==HourglassTransitionResult::Rerouted?1:0;
 if(!argsOk||originalCalls!=wantOriginal||roomCalls!=wantRoom){std::fprintf(stderr,"wrong forwarded ABI/parameters or call count\n");return 2;}
 // 普通过渡（向上 / 非 6 号动画 / 模组自带玩家）必须在**读任何游戏字段之前**就转发。
 if((expectedUp||expectedAnimation!=6||expectedForwardPlayer!=nullptr)&&reads!=0){
  std::fprintf(stderr,"ordinary transition read game fields (%d)\n",reads);return 3;}
 return 0;
}
'''

class GreedHourglassTransitionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='isaac-hourglass-')
        source = Path(cls.temp.name) / 'main.cpp'
        source.write_text(HARNESS)
        cls.binary = Path(cls.temp.name) / 'test'
        result = subprocess.run([shutil.which('clang++') or 'c++', '-std=c++17', '-Wall',
                                 '-Wextra', '-Werror', '-I', str(ROOT / 'runtime/src'),
                                 str(source), '-o', str(cls.binary)],
                                capture_output=True, text=True)
        if result.returncode:
            raise RuntimeError(result.stdout + result.stderr)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def check(self, mode):
        result = subprocess.run([str(self.binary), mode], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_greed_goes_to_native_error_room(self):
        self.check('greed')

    def test_greedier_goes_to_native_error_room(self):
        self.check('greedier')

    def test_normal_home_is_forwarded(self):
        self.check('normal')

    def test_hard_home_is_forwarded(self):
        self.check('hard')

    def test_other_difficulty_is_forwarded(self):
        self.check('unknown-difficulty')

    def test_other_stage_is_forwarded(self):
        self.check('other-stage')

    def test_left_starting_room_is_forwarded(self):
        # GameStateFlag 4 = "left from starting room" 已置位 ⇒ 不是首层沙漏。
        self.check('left-starting-room')

    def test_mod_call_with_player_is_forwarded_without_reads(self):
        # 模组经 Lua 显式调用必须带 Player ⇒ 不许被改道（PC 上那是合法的"去 Home"）。
        self.check('mod-call-with-player')

    def test_missing_player_fails_explicitly(self):
        self.check('no-player')

    def test_unreadable_difficulty_fails_explicitly(self):
        self.check('unreadable-difficulty')

    def test_other_animation_is_forwarded_without_reads(self):
        self.check('animation')

    def test_going_up_is_forwarded_without_reads(self):
        self.check('up')

    def test_unreadable_fields_fail_explicitly_without_dangerous_home(self):
        self.check('unreadable')

    def test_unavailable_room_entry_fails_explicitly(self):
        self.check('room-unavailable')

    def test_unavailable_original_fails_explicitly(self):
        self.check('original-unavailable')
