"""内部挂点：实际汇编保存上下文、宿主纯编码器与原指令指纹拒绝测试。"""
import pathlib
import platform
import re
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
HEADER = ROOT / "runtime/source/relay/internal_hook.hpp"

class InternalHookContextTests(unittest.TestCase):
    def test_invalid_continuation_traps_in_real_dispatch(self):
        driver = r'''
#include "relay/internal_hook.hpp"
using namespace isaac::runtime::relay;
extern "C" void isaac_internal_hook_dispatch(InternalHookContext*);
int main(){
 InternalHookBinding b{};b.resumeCount=1;b.resumes[0]=0x452a1c;
 b.callback=+[](InternalHookContext&,const void*)noexcept->unsigned{return 1;};
 InternalHookContext context{};context.binding=reinterpret_cast<std::uintptr_t>(&b);
 isaac_internal_hook_dispatch(&context);
 return 0;
}
'''
        with tempfile.TemporaryDirectory() as tmp:
            path=pathlib.Path(tmp);(path/'driver.cpp').write_text(driver)
            result=subprocess.run(['clang++','-std=c++20','-I',str(ROOT/'runtime/source'),'-I',str(ROOT/'runtime/src'),
                str(path/'driver.cpp'),str(ROOT/'runtime/source/relay/internal_hook_dispatch.cpp'),
                '-o',str(path/'driver')],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            result=subprocess.run([str(path/'driver')],capture_output=True,text=True)
            self.assertLess(result.returncode,0,'非法续接不能静默返回或使用默认续接点')

    def test_real_aarch64_register_restore_selection_and_nested_frames(self):
        if platform.machine() not in {"arm64", "aarch64"}:
            self.skipTest("真实寄存器执行需要AArch64宿主")
        asm_path = ROOT / "runtime/source/relay/internal_hook_context.s"
        self.assertTrue(asm_path.exists(), "内部上下文汇编尚不存在")
        asm = asm_path.read_text()
        darwin = platform.system() == "Darwin"
        if darwin:
            asm = re.sub(r'^\.section.*$', '.text', asm, flags=re.M)
            asm = re.sub(r'^\.(?:type|size).*\n', '', asm, flags=re.M)
            asm = asm.replace('isaac_internal_hook_context', '_isaac_internal_hook_context')
            asm = asm.replace('isaac_internal_hook_dispatch', '_isaac_internal_hook_dispatch')
        prefix = "_" if darwin else ""
        def addr(reg, name):
            if darwin:
                return f"adrp {reg}, _{name}@PAGE\nadd {reg}, {reg}, _{name}@PAGEOFF\n"
            return f"adrp {reg}, {name}\nadd {reg}, {reg}, :lo12:{name}\n"
        extra = f".text\n.global {prefix}TestEnter\n.align 2\n{prefix}TestEnter:\nsub sp,sp,#0x100\n"
        for pair in range(19, 29, 2): extra += f"stp x{pair},x{pair+1},[sp,#{(pair-19)*8}]\n"
        extra += "stp x29,x30,[sp,#0x50]\n"
        for q in range(8, 16, 2): extra += f"stp q{q},q{q+1},[sp,#{0x60+(q-8)*16}]\n"
        extra += "mrs x16,fpcr\nstr x16,[sp,#0xe0]\nmrs x16,fpsr\nstr x16,[sp,#0xe8]\n"
        for reg in range(31):
            if reg not in {16,18}: extra += f"mov x{reg},#{0x100+reg}\n"
        for q in range(32): extra += f"movi v{q}.16b,#{q+1}\n"
        extra += "mov x16,#0xa0000000\nmsr nzcv,x16\nmov x16,#0x1000000\nmsr fpcr,x16\nmov x16,#1\nmsr fpsr,x16\n"
        extra += addr("x16", "TestGateway") + "br x16\n"
        extra += f".global {prefix}ResumeA\n{prefix}ResumeA:\n" + addr("x16", "selected") + "mov x17,#1\nstr x17,[x16]\nbrk #0\n"
        extra += f".global {prefix}ResumeB\n{prefix}ResumeB:\n"
        extra += addr("x16", "after")
        for reg in range(31):
            if reg != 16: extra += f"str x{reg},[x16,#{reg*8}]\n"
        extra += "mov x17,sp\nstr x17,[x16,#0xf8]\nmrs x17,nzcv\nstr x17,[x16,#0x100]\nmrs x17,fpcr\nstr x17,[x16,#0x108]\nmrs x17,fpsr\nstr x17,[x16,#0x110]\n"
        for q in range(0,32,2): extra += f"stp q{q},q{q+1},[x16,#{0x140+q*16}]\n"
        extra += addr("x16", "selected") + "mov x17,#2\nstr x17,[x16]\n"
        for pair in range(19,29,2): extra += f"ldp x{pair},x{pair+1},[sp,#{(pair-19)*8}]\n"
        extra += "ldp x29,x30,[sp,#0x50]\n"
        for q in range(8,16,2): extra += f"ldp q{q},q{q+1},[sp,#{0x60+(q-8)*16}]\n"
        extra += "ldr x16,[sp,#0xe0]\nmsr fpcr,x16\nldr x16,[sp,#0xe8]\nmsr fpsr,x16\nadd sp,sp,#0x100\nret\n"
        # Mach-O禁止.text绝对指针重定位；这里只将夹具地址装载改成原生ADRP，
        # 被测生产上下文与生产dispatch逐字编译，真实JIT槽编码由另一用例核对。
        extra += f".align 3\n{prefix}TestGateway:\nstp x17,x30,[sp,#-16]!\n"
        extra += addr("x17", "binding") + addr("x16", "isaac_internal_hook_context") + "br x16\n"
        extra += f".global {prefix}Clobber\n.align 2\n{prefix}Clobber:\n"
        for reg in range(18): extra += f"mov x{reg},#0xdead\n"
        for q in range(32):
            if 8 <= q < 16: extra += f"ins v{q}.d[1],x16\n"
            else: extra += f"movi v{q}.16b,#0xff\n"
        extra += "cmp x0,x0\nmsr fpcr,xzr\nmsr fpsr,xzr\nmov w0,#1\nret\n"
        driver = r'''
#include "relay/internal_hook.hpp"
#include <cassert>
#include <cstdint>
using namespace isaac::runtime::relay;
extern "C" {
InternalHookContext after{};
std::uint64_t selected{};
InternalHookBinding binding{};
void TestEnter(); void ResumeA(); void ResumeB(); unsigned Clobber();
}
static unsigned depth = 0, calls = 0;
static std::uint64_t outerSp = 0, platformX18 = 0;
static unsigned Callback(InternalHookContext& c, const void*) noexcept {
  ++calls;
  assert((c.originalSp & 15) == 0);
  for(unsigned i=0;i<31;++i) if(i!=16 && i!=18) assert(c.x[i] == 0x100+i);
  platformX18 = c.x[18];
  assert(c.nzcv == 0xa0000000 && c.fpcr == 0x1000000 && c.fpsr == 1);
  for(unsigned i=0;i<32;++i) {
    std::uint64_t want = (i+1)*0x0101010101010101ULL;
    assert(c.q[i].low==want && c.q[i].high==want);
  }
  if(depth==0) { outerSp=c.originalSp; depth=1; TestEnter(); depth=0; }
  else assert(c.originalSp < outerSp);
  return Clobber();
}
int main() {
  binding.callback=Callback; binding.resumeCount=2;
  binding.resumes[0]=reinterpret_cast<std::uintptr_t>(&ResumeA);
  binding.resumes[1]=reinterpret_cast<std::uintptr_t>(&ResumeB);
  binding.scratch=InternalScratchPolicy::ProvedDeadX16;
  TestEnter();
  assert(calls==2 && selected==2 && after.originalSp==outerSp);
  assert(after.x[18]==platformX18);
  for(unsigned i=0;i<31;++i) if(i!=16 && i!=18) assert(after.x[i]==0x100+i);
  for(unsigned i=0;i<32;++i) {
    std::uint64_t want=(i+1)*0x0101010101010101ULL;
    assert(after.q[i].low==want && after.q[i].high==want);
  }
  assert(after.nzcv==0xa0000000 && after.fpcr==0x1000000 && after.fpsr==1);
}
'''
        with tempfile.TemporaryDirectory() as tmp:
            path=pathlib.Path(tmp)
            (path/"context.s").write_text(asm+extra)
            (path/"driver.cpp").write_text(driver)
            exe=path/"driver"
            result=subprocess.run(["clang++","-std=c++20","-O2","-Wall","-Wextra","-Werror",
                "-I",str(ROOT/"runtime/source"),"-I",str(ROOT/"runtime/src"),str(path/"driver.cpp"),str(path/"context.s"),
                str(ROOT/"runtime/source/relay/internal_hook_dispatch.cpp"),"-o",str(exe)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            result=subprocess.run([str(exe)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)

    def test_patch_targets_shared_literal_and_rejects_unproved_scratch(self):
        self.assertTrue(HEADER.exists(), "内部挂点基础设施尚不存在")
        driver = r'''
#include "relay/internal_hook.hpp"
#include <cassert>
#include <cstring>
using namespace isaac::runtime::relay;
int main() {
  unsigned char out[16]{};
  BuildInternalVeneer(out,0x123456789abc);
  unsigned long long literal = 0;
  std::memcpy(&literal,out+8,8);assert(literal==0x123456789abc);
  assert(LoadLittleEndianWord(out,0)==0x58000050);
  assert(LoadLittleEndianWord(out,1)==0xd61f0200);
  unsigned word{};
  assert(BuildInternalBranch(&word,0x452984,0x68cfd0));
  int imm=int(word<<6)>>6;
  assert(0x452984+imm*4==0x68cfd0 && (word>>26)==5);
  assert(SafeInternalBranchSource(0x94087527));
  assert(SafeInternalBranchSource(0x14000001));
  assert(!SafeInternalBranchSource(0x7100151f));
  assert(!SafeInternalBranchSource(0x52800428));
  assert(!BuildInternalBranch(&word,4,0x8000004));
  assert(!BuildInternalBranch(&word,5,0x68cfd0));
  assert(!BuildInternalBranch(&word,4,UINTPTR_MAX-3));
  unsigned char gateway[32]{};
  BuildInternalGateway(gateway,0x12345678,0x23456789);
  unsigned stp=LoadLittleEndianWord(gateway,0);
  assert((stp&31)==17 && ((stp>>10)&31)==30 && ((stp>>5)&31)==31);
  int pairImm=int(stp<<10)>>25;assert(pairImm*8==-16);
  unsigned ldr=LoadLittleEndianWord(gateway,1);assert((ldr&31)==17);
  int bindImm=int(ldr<<8)>>13;assert(4+bindImm*4==16);
  ldr=LoadLittleEndianWord(gateway,2);assert((ldr&31)==16);
  int commonImm=int(ldr<<8)>>13;assert(8+commonImm*4==24);
  InternalHookBinding binding{};
  assert(!ValidInternalBinding(binding));
  binding.callback = +[](InternalHookContext&, const void*) noexcept -> unsigned {return 0;};
  binding.resumeCount = 2;
  binding.resumes[0] = 0x452a1c; binding.resumes[1] = 0x453798;
  assert(!ValidInternalBinding(binding));
  binding.scratch = InternalScratchPolicy::ProvedDeadX16;
  assert(ValidInternalBinding(binding));
  binding.resumes[1] |= 1;
  assert(!ValidInternalBinding(binding));
}
'''
        with tempfile.TemporaryDirectory() as tmp:
            source = pathlib.Path(tmp) / "driver.cpp"
            source.write_text(driver)
            exe = pathlib.Path(tmp) / "driver"
            result = subprocess.run(["clang++", "-std=c++20", "-Wall", "-Wextra", "-Werror",
                "-I", str(ROOT / "runtime/source"), str(source), "-o", str(exe)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            result = subprocess.run([str(exe)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

if __name__ == "__main__":
    unittest.main()
