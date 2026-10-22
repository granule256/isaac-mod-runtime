"""真实shader帧必须先提交场景和Lua回调产生的批次，再清理下一目标。"""
import subprocess
import tempfile
import unittest
from pathlib import Path
from .test_shader_pipeline import HARNESS, ROOT


class ShaderDeferredFlushTests(unittest.TestCase):
    def test_scene_and_callback_batches_flush_before_destination_clear(self):
        extra = r'''
unsigned flushes=0;
void Flush(){if(queries!=flushes+1)std::exit(60);++flushes;}
template<class B> void BindFlush(B& b){
 if constexpr(requires {b.flushPending;})b.flushPending=Flush;
 else {std::fputs("missing deferred batch flush phase\n",stderr);std::exit(61);}
}
'''
        source=HARNESS.replace('int main(int argc,char**argv){',extra+'\nint main(int argc,char**argv){BindFlush(backend);')
        source=source.replace('void Target(const ShaderTarget&t,bool){current=t;}',
                              'extern unsigned flushes;void Target(const ShaderTarget&t,bool){if(queries && !unloadInValues && flushes!=queries)std::exit(62);current=t;}')
        # Target先于原声明出现；仅提前声明测试布尔值，不改变被测实现。
        source=source.replace('extern unsigned flushes;','extern unsigned flushes;extern bool unloadInValues;')
        with tempfile.TemporaryDirectory(prefix='shader-flush-') as folder:
            cpp,exe=Path(folder)/'flush.cpp',Path(folder)/'flush';cpp.write_text(source)
            r=subprocess.run(['c++','-std=c++20','-O2','-Wall','-Wextra','-Werror','-I'+str(ROOT/'runtime/src'),str(cpp),str(ROOT/'runtime/src/application/shader/shader_pipeline.cpp'),'-o',str(exe)],capture_output=True,text=True)
            self.assertEqual(r.returncode,0,r.stdout+r.stderr)
            r=subprocess.run([str(exe)],capture_output=True,text=True)
            self.assertEqual(r.returncode,0,r.stdout+r.stderr)
