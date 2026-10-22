"""用本机ARM64实际执行卡上装载代理，验证它保留调用者参数。"""
import pathlib,platform,struct,subprocess,tempfile,unittest,sys
ROOT=pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"tools"))
import elf_syms
DRIVER=r"""
#include <sys/mman.h>
#include <libkern/OSCacheControl.h>
#include <pthread.h>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <vector>
static int observed=-1;
static std::uint32_t FakeOriginal(void*,const void*,void*,std::size_t,int flag) { observed=flag; return flag==7 ? 0xdead : 0; }
int main(int argc,char**argv) {
 if(argc!=2)return 100;
 std::ifstream f(argv[1],std::ios::binary);
 std::vector<char>b((std::istreambuf_iterator<char>(f)),{});
 auto*mem=(char*)mmap(nullptr,0x2c000,PROT_READ|PROT_WRITE|PROT_EXEC,MAP_PRIVATE|MAP_ANON|MAP_JIT,-1,0);
 if(mem==MAP_FAILED){perror("mmap");return 101;}
 pthread_jit_write_protect_np(0);
 std::memcpy(mem+0x8e60,b.data(),b.size());
 auto fn=&FakeOriginal;std::memcpy(mem+0x2b158,&fn,sizeof(fn));
 sys_icache_invalidate(mem+0x8e60,b.size());
 pthread_jit_write_protect_np(1);
 using Entry=std::uint32_t(*)(void*,const void*,void*,std::size_t,int);
 for(int flag: {0,1,2,3,7}) {
  observed=-1;auto rc=reinterpret_cast<Entry>(mem+0x8e60)(nullptr,nullptr,nullptr,0,flag);
  if(rc!=(flag==7 ? 0xdeadU : 0U) || observed!=flag){std::printf("flag=%d observed=%d\n",flag,observed);return 1;}
 }
 munmap(mem,0x2c000);return 0;
}
"""
class SaltyBindFlagTests(unittest.TestCase):
 def test_real_arm64_dispatcher_preserves_all_flags(self):
  if platform.machine()!="arm64" or sys.platform!="darwin":self.skipTest("需要本机Apple ARM64执行指令")
  old=ROOT/"dist/diag-fourbugs/resume/saltysd_core.device.elf"
  if not old.exists():self.skipTest("无冻结卡上原件")
  blob=old.read_bytes()
  try:
   import repair_saltysd_loadmodule_bind_flag as repair
  except ModuleNotFoundError:pass
  else:blob=repair.repair(blob)
  code=elf_syms.read_vaddr(blob,0x8e60,0xb4)
  with tempfile.TemporaryDirectory() as d:
   p=pathlib.Path(d);(p/"code.bin").write_bytes(code);(p/"test.cpp").write_text(DRIVER)
   r=subprocess.run(["c++","-std=c++17",str(p/"test.cpp"),"-o",str(p/"test")],capture_output=True,text=True)
   self.assertEqual(r.returncode,0,r.stderr)
   r=subprocess.run([str(p/"test"),str(p/"code.bin")],capture_output=True,text=True)
   self.assertEqual(r.returncode,0,r.stdout+r.stderr)
