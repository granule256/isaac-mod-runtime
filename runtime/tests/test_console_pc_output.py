"""PC ExecuteCommand只删一个末LF；CHAPI逐字等待输出必须结束。"""
import subprocess,tempfile,unittest
from pathlib import Path
from . import test_console_long_commands as fixture
MAIN=r'''
int main(int argc,char**argv){
 if(argc!=2)return 90;
 std::vector<unsigned char> module(kGameOwnerGlobalSlotOffset+16),game(kGamePlayerArrayEndOffset+16);
 alignas(8) std::uintptr_t player=0x1000,gamePointer=memory::AddressOf(game.data());
 writePointer(module,kGameOwnerGlobalSlotOffset,memory::AddressOf(&gamePointer));writePointer(game,kGamePlayerArrayBeginOffset,memory::AddressOf(&player));writePointer(game,kGamePlayerArrayEndOffset,memory::AddressOf(&player)+8);
 moduleBase=memory::AddressOf(module.data());entries.consoleCtor=MockCtor;entries.consoleInit=MockInit;entries.runCommand=MockConsoleRunCommand;
 expected="debug 3";expectedLength=7;
 std::string scenario(argv[1]);
 const char* wanted="";
 if(scenario=="chapi"){mockText="Enabled debug flag.\n";wanted="Enabled debug flag.";}
 if(scenario=="double"){mockText="first\nsecond\n\n";wanted="first\nsecond\n";}
 if(scenario=="crlf"){mockText="a\r\n";wanted="a\r";}
 if(scenario=="plain"){mockText="ok";wanted="ok";}
 if(scenario=="lf"){mockText="\n";wanted="";}
 const auto result=console::ExecuteCommand(entries,moduleBase,expected,expectedLength);check(result.status==console::ExecStatus::kOk,"native command executes");
 const char* text=nullptr;std::uint32_t length=0;check(console::TakeLastOutput(&text,&length),"output returned");
 check(text&&std::string(text,length)==wanted,"PC return exact bytes");
 check(console::Storage().lastOutputLength==std::strlen(mockText)&&std::memcmp(console::Storage().lastOutput,mockText,std::strlen(mockText))==0,"raw console display retains newline");
 if(scenario=="chapi")check(std::string(text,length)=="Enabled debug flag.","author repeat-until exits after successful debug3");
 return failures?1:0;
}
'''
class ConsolePcOutputTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  compilers=fixture.host_compilers();cls.temporary=tempfile.TemporaryDirectory(prefix='isaac-console-pc-output-');p=Path(cls.temporary.name)
  (p/'stdfloat').write_text('#pragma once\nnamespace std {using float16_t=float;using float128_t=long double;}\n')
  code=fixture.HARNESS[:fixture.HARNESS.index('int main(')].replace('bool breakFence = false;','bool breakFence = false;\nconst char* mockText="";')
  code=code.replace("result[0] = 4; result[1] = 'o'; result[2] = 'k';",'result[0]=static_cast<unsigned char>(std::strlen(mockText)*2);std::memcpy(result+1,mockText,std::strlen(mockText)+1);')
  (p/'test.cpp').write_text(code+MAIN);cls.binary=p/'test'
  r=subprocess.run([compilers[1],'-std=c++23','-Wall','-Wextra','-Werror','-I',str(p),'-I',str(fixture.SOURCE),'-I',str(fixture.SOURCE.parent/'src'),str(p/'test.cpp'),'-o',str(cls.binary)],capture_output=True,text=True)
  if r.returncode:raise RuntimeError(r.stdout+r.stderr)
 @classmethod
 def tearDownClass(cls):cls.temporary.cleanup()
 def test_pc_output_exact_bytes(self):
  for scenario in ['chapi','double','crlf','plain','lf']:
   with self.subTest(scenario=scenario):
    r=subprocess.run([str(self.binary),scenario],capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
