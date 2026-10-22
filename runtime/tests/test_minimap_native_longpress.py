"""Apple ARM64 CPU执行游戏原件计数/长短按状态机，不以C++复制状态转移。
冻结来源：主目录游戏dump，Afterbirth+1.7.9b [010021C000B6A800][v524288]
Program #0/1/.nro/Repentance.nro；文件偏移与模块偏移相同。
counter.bin=0x41ce60..0x41ce8c（末端不含），state.bin=0x41cf00..0x41d0e0。
仅替代外部ShowName调用为记录次数/参数的局部stub，以及片段末端/0x41d0f4返回。
调用者提供原w20按住/命中信号；本测试不运行前段触摸矩形几何或GoodTrip Lua、传送代码。
传送区间用例验证同一地图对象跨两个持续按住区间的计数保持；不冒称真实传送验收。
"""
import hashlib
import platform
import subprocess
import tempfile
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
FIXTURES=Path(__file__).parent/'fixtures/minimap_native_longpress'
ASSEMBLY=r'''
.text
.globl _RunCode
.p2align 2
_RunCode:
 sub sp, sp, #0x400
 stp x19, x20, [sp, #0x10]
 stp x25, x26, [sp, #0x20]
 stp x27, x28, [sp, #0x30]
 str x30, [sp, #0x40]
 mov x9, x0
 mov x19, x1
 mov w20, w2
 str w3, [sp, #0x3c0]
 mov x25, x4
 mov x26, x5
 adr x28, 1f
 blr x9
1:
 ldp x19, x20, [sp, #0x10]
 ldp x25, x26, [sp, #0x20]
 ldp x27, x28, [sp, #0x30]
 ldr x30, [sp, #0x40]
 add sp, sp, #0x400
 ret
'''
DRIVER=r'''
#include "patch/minimap_touch_gate.hpp"
#include <sys/mman.h>
#include <pthread.h>
#include <libkern/OSCacheControl.h>
#include <cstdio>
#include <cstdint>
#include <cstring>
#include <fstream>
#include <vector>
#include <string>
extern "C" void RunCode(void*,void*,unsigned,unsigned,void*,void*);
std::vector<unsigned char> Read(const char* p){std::ifstream f(p,std::ios::binary);return {std::istreambuf_iterator<char>(f),{}};}
unsigned Get(const void* p,int offset){unsigned v;std::memcpy(&v,static_cast<const unsigned char*>(p)+offset,4);return v;}
void Put(void* p,int offset,unsigned v){std::memcpy(static_cast<unsigned char*>(p)+offset,&v,4);}
#define CHECK(x) do{if(!(x)){std::fprintf(stderr,"FAIL %s line=%d: %s mode=%u flag=%u counter=%u shown=%u\n",scenario.c_str(),__LINE__,#x,Get(map,0),map[4],Get(map,8),game[0]);return 1;}}while(0)
int main(int argc,char** argv){
 if(argc!=4)return 90;std::string scenario=argv[1];
 auto counter=Read(argv[2]),state=Read(argv[3]);if(counter.size()!=44 || state.size()!=480)return 91;
 void* code=mmap(nullptr,4096,PROT_READ|PROT_WRITE|PROT_EXEC,MAP_ANON|MAP_PRIVATE|MAP_JIT,-1,0);
 if(code==MAP_FAILED){perror("MAP_JIT");return 92;}
 pthread_jit_write_protect_np(0);
 std::memcpy(code,counter.data(),counter.size());
 Put(code,8,isaac::runtime::kMinimapTouchGatePatches[2].patched);
 // 0x41ce88 bl跳向测试ShowName；末端ret x28保留wrapper返回地址（外部bl会改x30）。
 Put(code,40,0x94000006);Put(code,44,0xd65f0380);
 unsigned stub[]={0xb9400008,0x11000508,0xb9000008,0xb9000401,0xd65f03c0};
 std::memcpy(static_cast<unsigned char*>(code)+64,stub,sizeof(stub));
 std::memcpy(static_cast<unsigned char*>(code)+0x100,state.data(),state.size());
 Put(code,0x2e0,0xd65f03c0);Put(code,0x2f4,0xd65f03c0);
 pthread_jit_write_protect_np(1);sys_icache_invalidate(code,4096);
 alignas(16) unsigned char map[0xb30]={};unsigned game[2]={};void* gamePointer=game;
 std::vector<unsigned char> manager(0x36500);float opacity=0.8f;std::memcpy(manager.data()+0x364f0,&opacity,4);void* managerPointer=manager.data();
 auto count=[&](bool held,unsigned touch){RunCode(code,map,held,touch,&gamePointer,&managerPointer);};
 auto frame=[&](bool held,unsigned touch=0){count(held,touch);RunCode(static_cast<unsigned char*>(code)+0x100,map,held,touch,&gamePointer,&managerPointer);};
 if(scenario=="long-release"){
  for(int i=0;i<30;++i)frame(true);CHECK(Get(map,0)==1);
  std::printf("LONG_HOLD_COUNTER %u\n",Get(map,8));
  frame(false);CHECK(Get(map,0)==0);CHECK(Get(map,8)==0);
 }else if(scenario=="duration-boundary"){
  for(int i=0;i<8;++i)frame(true);frame(false);CHECK(Get(map,0)==2);CHECK(map[4]==1);
  std::memset(map,0,sizeof(map));std::memset(game,0,sizeof(game));
  for(int i=0;i<9;++i)frame(true);frame(false);CHECK(Get(map,0)==0);CHECK(map[4]==0);
 }else if(scenario=="show-name-map-key"){
  for(int i=0;i<9;++i)frame(true);CHECK(game[0]==0);
  frame(true);CHECK(game[0]==1);CHECK(game[1]==1);
  for(int i=0;i<20;++i)frame(true);CHECK(game[0]==1);
  frame(false);CHECK(Get(map,0)==0);
 }else if(scenario=="short-toggle"){
  for(int i=0;i<3;++i)frame(true);frame(false);CHECK(Get(map,0)==2);CHECK(map[4]==1);
 }else if(scenario=="fixed-big-long-release"){
  Put(map,0,2);map[4]=1;for(int i=0;i<30;++i)frame(true);frame(false);CHECK(Get(map,0)==2);CHECK(map[4]==1);
 }else if(scenario=="continuous-held-intervals"){
  for(int i=0;i<15;++i)frame(true);CHECK(Get(map,8)==15);
  // 在传送前/后相同对象持续按住；不人为复位原生计数。
  for(int i=0;i<15;++i)frame(true);CHECK(Get(map,8)==30);frame(false);CHECK(Get(map,0)==0);
 }else if(scenario=="show-name-local-touch"){
  for(int i=0;i<9;++i)frame(true,1);CHECK(Get(map,8)==9);CHECK(game[0]==0);
  frame(true,1);CHECK(Get(map,8)==10);CHECK(game[0]==1);CHECK(game[1]==1);
  for(int i=0;i<20;++i)frame(true,1);CHECK(game[0]==1);frame(false);CHECK(Get(map,0)==0);
 }else if(scenario=="outside-touch"){
  for(int i=0;i<30;++i){frame(false,1);CHECK(Get(map,0)==0);CHECK(Get(map,8)==0);}
  frame(false);CHECK(Get(map,0)==0);CHECK(game[0]==0);
 }else return 93;
 munmap(code,4096);std::printf("NATIVE_MAP_OK %s\n",scenario.c_str());return 0;
}
'''
class MinimapNativeLongpressTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  if platform.system()!='Darwin' or platform.machine()!='arm64':raise unittest.SkipTest('需要Apple ARM64 CPU与MAP_JIT')
  for name,expected in {'counter.bin':'fb7c37c82b7d3cc9d92618fa82e89d212c2e5f23f1c3a583f1c71fcbcb4c6897',
                        'state.bin':'cc0740332f6e6a72c5621b9c238da665a79c687bd9ca431e8a6a685d5765cd0c'}.items():
   assert hashlib.sha256((FIXTURES/name).read_bytes()).hexdigest()==expected, '原生机器码夹具被改动'
  cls.tmp=tempfile.TemporaryDirectory(prefix='minimap-native-longpress-');cls.addClassCleanup(cls.tmp.cleanup)
  work=Path(cls.tmp.name);(work/'driver.cpp').write_text(DRIVER);(work/'entry.s').write_text(ASSEMBLY)
  cls.binary=work/'test'
  result=subprocess.run(['c++','-std=c++20','-O0','-I',str(ROOT/'runtime/source'),str(work/'driver.cpp'),str(work/'entry.s'),'-o',str(cls.binary)],text=True,capture_output=True)
  assert result.returncode==0,result.stdout+result.stderr
 def run_case(self,name):
  result=subprocess.run([str(self.binary),name,str(FIXTURES/'counter.bin'),str(FIXTURES/'state.bin')],text=True,capture_output=True)
  print(result.stdout+result.stderr,end='');self.assertEqual(result.returncode,0,result.stdout+result.stderr)
 def test_long_press_release_returns_small(self):self.run_case('long-release')
 def test_eight_frames_toggle_but_nine_frames_release_small(self):self.run_case('duration-boundary')
 def test_map_key_tenth_frame_shows_name_once(self):self.run_case('show-name-map-key')
 def test_short_press_still_toggles(self):self.run_case('short-toggle')
 def test_preexisting_fixed_big_mode_is_preserved(self):self.run_case('fixed-big-long-release')
 def test_continuous_hold_across_intervals_releases_small(self):self.run_case('continuous-held-intervals')
 def test_tenth_local_touch_frame_calls_show_name_once(self):self.run_case('show-name-local-touch')
 def test_outside_touch_never_toggles(self):self.run_case('outside-touch')
if __name__=='__main__':unittest.main()
